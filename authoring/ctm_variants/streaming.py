"""Supervised lazy finite-choice traversal. AGPL-3.0-or-later.

No sampling, templates, candidate testing or approval policy lives here.
"""
import contextlib
import hashlib
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
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ctm_variants.generation import (GenerationError, Rejected, MAX_DOMAIN,
                                    MAX_IPC, _key, _read_lines, _run, _source)
from ctm_variants.enumeration import _Branch, MAX_OUTPUT


@contextlib.contextmanager
def choice_stream(source, *, attempt_limit, variables=None, file="<variables>",
                  label="<question>", variable_timeout=5.0,
                  attempt_timeout=30.0, exercise_timeout=30.0, seed=None):
    """Yield a demand-driven iterator over distinct exact choice tapes.

    Without seed, finite-domain order is the existing exhaustive order. A text
    seed permutes each finite domain lazily; no Cartesian pool is materialized.
    attempt_limit counts
    actual prefix executions, including branches, rejections and duplicates.
    Use the context manager so an early consumer stop closes the native worker.
    """
    stream = _Stream(source, attempt_limit, variables, file, label,
                     variable_timeout, attempt_timeout, exercise_timeout, seed)
    try:
        yield stream
    finally:
        stream.close()


class _Stream:
    def __init__(self, source, limit, variables, file, label, variable_timeout,
                 attempt_timeout, exercise_timeout, seed):
        self.where = "{}: {}".format(file, label)
        self.process = self.reader = self.temporary = None
        self.messages, self.stopped = queue.Queue(maxsize=1), threading.Event()
        self.closed = self.exhausted = False
        self.active, self.statement, self.line = False, 0, 1
        self.attempts = self.branches = self.paths = self.rejected = 0
        self.duplicates = self.yielded = self.request = self.output_bytes = 0
        self.frontier, self.seen = 1, set()
        self.started = self.attempt_started = self.variable_started = time.monotonic()
        self.variable_timeout, self.attempt_timeout, self.exercise_timeout = variable_timeout, attempt_timeout, exercise_timeout
        self.limit = limit
        try:
            if type(limit) is not int or limit < 1:
                raise GenerationError("attempt_limit must be a positive integer")
            if seed is not None and (not isinstance(seed, str) or len(seed) > 1024):
                raise GenerationError("seed must be text of at most 1024 characters")
            for timeout in (variable_timeout, attempt_timeout, exercise_timeout):
                if isinstance(timeout, bool) or not isinstance(timeout, (int, float)) or not math.isfinite(timeout) or timeout <= 0:
                    raise GenerationError("timeouts must be positive finite seconds")
            _, tree = _source(source)
            self.lines = [node.lineno for node in tree.body]
            if self.lines:
                self.line = self.lines[0]
            import ctm_checkers
            import ctm_variants
            import sympy
            import mpmath
            from ctm_checkers.variants import encode
            roots = sorted({str(Path(package.__file__).resolve().parents[1])
                for package in (ctm_checkers, ctm_variants, sympy, mpmath)})
            request = json.dumps({"source": source, "variables": encode(variables or {}),
                "attempt_limit": limit, "import_roots": roots, "seed": seed}, ensure_ascii=True).encode("utf-8")
            if len(request) > MAX_IPC:
                raise GenerationError("worker request exceeds byte limit")
            self.temporary = tempfile.TemporaryDirectory(prefix="ctm-choice-stream-")
            request_path = Path(self.temporary.name) / "request.json"
            request_path.write_bytes(request)
            environment = dict(os.environ)
            environment.pop("PYTHONPATH", None)
            self.process = subprocess.Popen([sys.executable, "-I", str(Path(__file__).resolve()), str(request_path)],
                stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                env=environment, cwd=self.temporary.name)
            self.reader = threading.Thread(target=_read_lines, args=(self.process.stdout, self.messages, self.stopped),
                                           name="ctm-choice-stream-reader", daemon=True)
            self.reader.start()
            ready = self.receive()
            if set(ready) != {"ready"} or ready["ready"] is not True:
                raise GenerationError("invalid worker startup")
        except Exception as error:
            self.close()
            raise GenerationError("{}: line {}: {}".format(self.where, self.line, error)) from error

    @property
    def stats(self):
        return {"attempts": self.attempts, "branches": self.branches,
                "paths": self.paths, "rejected": self.rejected,
                "duplicates": self.duplicates, "yielded": self.yielded,
                "exhausted": self.exhausted, "closed": self.closed}

    def remaining(self):
        value = min(self.started + self.exercise_timeout,
                    self.attempt_started + self.attempt_timeout,
                    self.variable_started + self.variable_timeout) - time.monotonic()
        if value <= 0:
            raise GenerationError("choice stream time budget exceeded")
        return value

    def receive(self):
        try:
            message = self.messages.get(timeout=self.remaining())
        except queue.Empty:
            raise GenerationError("choice stream time budget exceeded")
        self.remaining()
        if type(message) is not dict:
            raise GenerationError("worker exited without a result")
        self.output_bytes += len(json.dumps(message, ensure_ascii=True).encode("utf-8")) + 1
        if self.output_bytes > MAX_OUTPUT:
            raise GenerationError("choice stream output exceeds aggregate byte limit")
        return message

    def __iter__(self):
        return self

    def __next__(self):
        if self.closed:
            raise StopIteration
        try:
            from ctm_checkers.variants import decode
            while True:
                # Consumer idle time counts towards the absolute exercise limit,
                # but not towards the next prefix's fresh variable/attempt budget.
                if self.attempts:
                    self.attempt_started = self.variable_started = time.monotonic()
                self.remaining()
                self.process.stdin.write((json.dumps({"next": self.request}) + "\n").encode("utf-8"))
                self.process.stdin.flush()
                self.request += 1
                while True:
                    message = self.receive()
                    if set(message) == {"error"} and isinstance(message["error"], str):
                        raise GenerationError(message["error"])
                    if set(message) == {"attempt"}:
                        if self.active or type(message["attempt"]) is not int or message["attempt"] != self.attempts or self.attempts >= self.limit:
                            raise GenerationError("unexpected worker attempt boundary")
                        if self.attempts:
                            self.attempt_started = self.variable_started = time.monotonic()
                        self.attempts += 1
                        self.active, self.statement = True, 0
                        continue
                    if set(message) == {"statement", "line"}:
                        if (not self.active or self.statement >= len(self.lines)
                                or type(message["statement"]) is not int or message["statement"] != self.statement
                                or type(message["line"]) is not int or message["line"] != self.lines[self.statement]):
                            raise GenerationError("unexpected worker statement boundary")
                        self.line = message["line"]
                        self.statement += 1
                        if self.statement > 1:
                            self.variable_started = time.monotonic()
                        continue
                    if message.get("end") == "branch" and set(message) == {"end", "size"}:
                        if not self.active or not self.statement or type(message["size"]) is not int or not 1 <= message["size"] <= MAX_DOMAIN:
                            raise GenerationError("invalid worker branch boundary")
                        self.frontier += message["size"] - 1
                        self.branches += 1
                        self.active = False
                        continue
                    if message == {"end": "rejected"}:
                        if not self.active or not self.statement:
                            raise GenerationError("unexpected worker rejection")
                        self.active = False
                        self.frontier -= 1
                        self.paths += 1
                        self.rejected += 1
                        continue
                    if message.get("end") == "accepted" and set(message) == {"end", "result"}:
                        if not self.active or self.statement != len(self.lines):
                            raise GenerationError("unexpected worker result boundary")
                        result = decode(message["result"])
                        if type(result) is not dict or set(result) != {"variables", "choices"} or type(result["variables"]) is not dict or type(result["choices"]) is not list:
                            raise GenerationError("invalid worker result shape")
                        result["locator"] = _key(result["choices"])
                        self.remaining()
                        self.active = False
                        self.frontier -= 1
                        self.paths += 1
                        duplicate = result["locator"] in self.seen
                        if duplicate:
                            self.duplicates += 1
                        else:
                            self.seen.add(result["locator"])
                            self.yielded += 1
                        if not self.frontier:
                            self.exhausted = True
                            self.close()
                        if not duplicate:
                            return result
                        if self.closed:
                            raise StopIteration
                        break  # Demand another path; never prefetch past a yield.
                    if set(message) == {"done"}:
                        if self.active or self.frontier != 0 or type(message["done"]) is not int or message["done"] != self.attempts:
                            raise GenerationError("invalid worker completion")
                        self.exhausted = True
                        self.close()
                        raise StopIteration
                    raise GenerationError(message.get("protocol_error", "unexpected worker protocol"))
        except StopIteration:
            raise
        except Exception as error:
            self.close()
            raise GenerationError("{}: line {}: {}".format(self.where, self.line, error)) from error

    def close(self):
        if self.closed:
            return
        self.closed = True
        self.stopped.set()
        if self.process is not None:
            if self.process.poll() is None:
                self.process.kill()
            self.process.wait()
            self.process.stdin.close()
        if self.reader is not None:
            self.reader.join(timeout=2)
            if self.reader.is_alive():
                raise GenerationError(self.where + ": worker reader failed to terminate")
        if self.temporary is not None:
            self.temporary.cleanup()


def _permutation(size, seed, prefix):
    if seed is None or size == 1:
        return 0, 1
    bits = hashlib.sha256((seed + ":" + _key(prefix)).encode("utf-8")).digest()
    offset = int.from_bytes(bits[:16], "big") % size
    stride = 1 + int.from_bytes(bits[16:], "big") % size
    for unused in range(1024):
        if math.gcd(stride, size) == 1:
            return offset, stride
        stride = stride % size + 1
    return offset, 1  # Still a complete permutation, with bounded setup work.


def _worker(request_path):
    def emit(message):
        text = json.dumps(message, ensure_ascii=True)
        if len(text.encode("utf-8")) >= MAX_IPC:
            raise GenerationError("worker output exceeds byte limit")
        print(text, flush=True)

    request = json.loads(Path(request_path).read_bytes())
    sys.path[:0] = request["import_roots"]
    from ctm_checkers.variants import encode, decode
    source, variables = request["source"], decode(request["variables"])
    prefix, frames, attempts, command = [], [], 0, 0
    advance = False

    def advance_path():
        while frames:
            domain, index, offset, stride = frames[-1]
            if index + 1 < domain.size:
                frames[-1][1] += 1
                prefix[-1] = domain.at((offset + stride * (index + 1)) % domain.size)
                return True
            frames.pop()
            prefix.pop()
        return False

    emit({"ready": True})
    for line in iter(lambda: sys.stdin.buffer.readline(MAX_IPC + 1), b""):
        try:
            if len(line) > MAX_IPC:
                raise GenerationError("worker command exceeds byte limit")
            incoming = json.loads(line)
            if set(incoming) != {"next"} or type(incoming["next"]) is not int or incoming["next"] != command:
                raise GenerationError("unexpected choice-stream command")
            command += 1
            if advance and not advance_path():
                emit({"done": attempts})
                continue
            advance = False
            while True:
                if attempts >= request["attempt_limit"]:
                    raise GenerationError("actual prefix attempt limit exceeded after {} attempts".format(attempts))
                emit({"attempt": attempts})
                attempts += 1
                def choose(index, domain):
                    if index == len(prefix):
                        raise _Branch(domain)
                    if index > len(prefix) or not domain.contains(prefix[index]):
                        raise GenerationError("choice prefix is absent from current domain")
                    return prefix[index]
                try:
                    result = _run(source, variables, "", None,
                        lambda index, number: emit({"statement": index, "line": number}), choose)
                except _Branch as branch:
                    offset, stride = _permutation(branch.domain.size, request["seed"], prefix)
                    frames.append([branch.domain, 0, offset, stride])
                    prefix.append(branch.domain.at(offset))
                    emit({"end": "branch", "size": branch.domain.size})
                except Rejected:
                    emit({"end": "rejected"})
                    if not advance_path():
                        emit({"done": attempts})
                        break
                else:
                    emit({"end": "accepted", "result": encode(result)})
                    advance = True
                    break
        except Exception as error:
            emit({"error": str(error)})
            break


if __name__ == "__main__":
    _worker(sys.argv[1])
