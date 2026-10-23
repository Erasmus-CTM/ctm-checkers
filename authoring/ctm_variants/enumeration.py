"""Bounded native exhaustive choice-tree traversal. AGPL-3.0-or-later.

No sampling, proposal order, placeholders, notes or approval allocation.
"""
import json
import math
import os
from pathlib import Path
import queue
import subprocess
import sys
import tempfile
import threading
import time

if __name__ == "__main__":
    # -I removes cwd/PYTHONPATH; import only our trusted absolute authoring root.
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ctm_variants.generation import (GenerationError, Rejected, MAX_DOMAIN,
    MAX_IPC, _key, _read_lines, _run, _source)

MAX_OUTPUT = 32 * 1024 * 1024


class _Branch(BaseException):
    # Internal control flow must bypass _run's contextual author-error wrapper.
    def __init__(self, domain):
        self.domain = domain


def _enumerate(source, variables, limit, emit):
    pending, finished, attempt = [[]], 0, 0
    while pending:
        prefix = pending.pop()
        emit({"attempt": attempt})
        attempt += 1
        def choose(index, domain):
            if index == len(prefix):
                raise _Branch(domain)
            value = prefix[index]
            if not domain.contains(value):
                raise GenerationError("choice prefix is absent from current domain")
            return value
        try:
            result = _run(source, variables, "", None,
                lambda index, line: emit({"statement": index, "line": line}), choose)
        except _Branch as branch:
            # Each pending prefix represents at least one terminal execution.
            # Count before constructing any child prefixes; duplicate values and
            # rejected executions do not buy extra raw-space capacity.
            if finished + len(pending) + branch.domain.size > limit:
                raise GenerationError("raw choice space exceeds {}; sampling is unsupported".format(limit))
            for index in range(branch.domain.size-1, -1, -1):
                pending.append(prefix + [branch.domain.at(index)])
            emit({"end": "branch", "size": branch.domain.size})
        except Rejected:
            finished += 1
            emit({"end": "rejected"})
        else:
            finished += 1
            from ctm_checkers.variants import encode
            emit({"end": "accepted", "result": encode(result)})
    emit({"done": finished})


def enumerate_exhaustive(source, *, variables=None, raw_path_limit=MAX_DOMAIN,
                         file="<variables>", label="<question>",
                         variable_timeout=5.0, variant_timeout=30.0,
                         exercise_timeout=30.0):
    """Return all distinct exact tapes in finite domain order, or fail entirely.

    raw_path_limit bounds raw terminal execution paths, including duplicate choices and
    require rejections. A rejected prefix stops before later choices, as execute
    does. Dynamic domains are evaluated only along reachable prefixes. No note
    or result-value deduplication is implied by exact choice-tape deduplication.
    """
    from ctm_checkers.variants import encode, decode
    where = "{}: {}: ".format(file, label)
    limit = raw_path_limit
    if type(limit) is not int or not 1 <= limit <= MAX_DOMAIN:
        raise GenerationError(where + "raw_path_limit must be an integer from 1 to {}".format(MAX_DOMAIN))
    for timeout in (variable_timeout, variant_timeout, exercise_timeout):
        if isinstance(timeout, bool) or not isinstance(timeout, (int, float)) or not math.isfinite(timeout) or timeout <= 0:
            raise GenerationError(where + "timeouts must be positive finite seconds")
    try:
        _, tree = _source(source)
        import ctm_checkers
        import ctm_variants
        import sympy
        import mpmath
        roots = sorted({str(Path(package.__file__).resolve().parents[1])
            for package in (ctm_checkers, ctm_variants, sympy, mpmath)})
        request = json.dumps({"source":source, "variables":encode(variables or {}),
            "limit":limit, "import_roots":roots}, ensure_ascii=True).encode("utf-8")
        if len(request) > MAX_IPC:
            raise GenerationError("worker request exceeds byte limit")
    except Exception as error:
        raise GenerationError(where + str(error)) from error
    records, seen = [], set()
    rejected = duplicates = completed = total_bytes = 0
    messages, stopped = queue.Queue(maxsize=1), threading.Event()
    with tempfile.TemporaryDirectory(prefix="ctm-enumeration-") as temporary:
        request_path = Path(temporary) / "request.json"
        request_path.write_bytes(request)
        environment = dict(os.environ)
        environment.pop("PYTHONPATH", None)
        started = variable_started = variant_started = time.monotonic()
        process = subprocess.Popen([sys.executable, "-I", str(Path(__file__).resolve()), str(request_path)],
            stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
            env=environment, cwd=temporary)
        reader = threading.Thread(target=_read_lines, args=(process.stdout, messages, stopped),
            name="ctm-enumeration-reader", daemon=True)
        reader.start()
        attempt, statement, active, line, pending = 0, 0, False, 1, 1
        try:
            while True:
                deadline = min(started+exercise_timeout, variant_started+variant_timeout,
                               variable_started+variable_timeout)
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise GenerationError("generation time budget exceeded")
                try:
                    message = messages.get(timeout=remaining)
                except queue.Empty:
                    raise GenerationError("generation time budget exceeded")
                if time.monotonic() > deadline:
                    raise GenerationError("generation time budget exceeded")
                if not isinstance(message, dict):
                    raise GenerationError("worker exited without a result")
                total_bytes += len(json.dumps(message, ensure_ascii=True).encode("utf-8"))
                if total_bytes > MAX_OUTPUT:
                    raise GenerationError("enumeration output exceeds byte limit")
                if set(message) == {"attempt"}:
                    if active or not pending or type(message["attempt"]) is not int or message["attempt"] != attempt:
                        raise GenerationError("unexpected worker attempt boundary")
                    if attempt:
                        variant_started = variable_started = time.monotonic()
                    attempt, statement, active = attempt+1, 0, True
                    pending -= 1
                elif set(message) == {"statement", "line"}:
                    if (not active or statement >= len(tree.body)
                            or type(message["statement"]) is not int or message["statement"] != statement
                            or type(message["line"]) is not int or message["line"] != tree.body[statement].lineno):
                        raise GenerationError("unexpected worker statement boundary")
                    line = message["line"]
                    if statement:
                        variable_started = time.monotonic()
                    statement += 1
                elif message.get("end") in ("branch", "rejected", "accepted"):
                    accepted = message["end"] == "accepted"
                    branching = message["end"] == "branch"
                    expected = {"end", "result"} if accepted else ({"end", "size"} if branching else {"end"})
                    if (not active or set(message) != expected
                            or (accepted and statement != len(tree.body))
                            or (not accepted and not statement)):
                        raise GenerationError("unexpected worker path end")
                    active = False
                    if branching:
                        size = message["size"]
                        if type(size) is not int or not 1 <= size <= MAX_DOMAIN:
                            raise GenerationError("invalid worker branch size")
                        pending += size
                    elif message["end"] == "rejected":
                        rejected += 1
                        completed += 1
                    elif accepted:
                        completed += 1
                        result = decode(message["result"])
                        if (not isinstance(result, dict) or set(result) != {"variables", "choices"}
                                or not isinstance(result["variables"], dict) or not isinstance(result["choices"], list)):
                            raise GenerationError("invalid worker result shape")
                        locator = _key(result["choices"])
                        if locator in seen:
                            duplicates += 1
                        else:
                            seen.add(locator)
                            result["locator"] = locator
                            records.append(result)
                    if completed + pending > limit:
                        raise GenerationError("raw choice space exceeds limit")
                elif set(message) == {"done"}:
                    if active or pending or not attempt or type(message["done"]) is not int or message["done"] != completed:
                        raise GenerationError("invalid worker completion")
                    return {"candidates":records, "raw_paths":completed,
                            "rejected":rejected, "duplicates":duplicates}
                elif set(message) == {"error"} and isinstance(message["error"], str):
                    raise GenerationError(message["error"])
                else:
                    raise GenerationError(message.get("protocol_error", "unexpected worker protocol"))
        except Exception as error:
            detail = str(error)
            if not detail.startswith("line "):
                detail = "line {}: {}".format(line, detail)
            raise GenerationError(where + detail) from error
        finally:
            stopped.set()
            if process.poll() is None:
                process.kill()
            process.wait()
            reader.join(timeout=2)
            if reader.is_alive():
                raise GenerationError(where + "worker reader failed to terminate")


def _worker(request_path):
    def emit(message):
        data = json.dumps(message, ensure_ascii=True)
        if len(data.encode("utf-8")) > MAX_IPC-1:
            raise GenerationError("worker output exceeds byte limit")
        print(data, flush=True)
    try:
        with open(request_path, "rb") as stream:
            request = stream.read(MAX_IPC+1)
        if len(request) > MAX_IPC:
            raise GenerationError("worker request exceeds byte limit")
        request = json.loads(request)
        sys.path[:0] = request["import_roots"]
        from ctm_checkers.variants import decode
        _enumerate(request["source"], decode(request["variables"]), request["limit"], emit)
    except Exception as error:
        emit({"error":str(error)[:4096]})


if __name__ == "__main__":
    _worker(sys.argv[1])
