"""Lazy native batches from supplied resolved candidates. AGPL-3.0-or-later.

This is a collector, not a sampling or template-generation implementation.
"""
import contextlib
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

from ctm_variants.generation import MAX_IPC, _read_lines

BATCH_SIZE = 25


class BatchError(ValueError):
    pass


def _record(value):
    from ctm_variants.model import candidate
    if type(value) is not dict or set(value) != {"id", "hash", "note", "snapshot", "data", "tests"}:
        raise BatchError("expected a resolved neutral candidate record, not a manifest decision")
    rebuilt = candidate(value["id"], value["snapshot"], note=value["note"],
                        data=value["data"], tests=value["tests"])
    if rebuilt != value:
        raise BatchError("candidate differs from its canonical snapshot/hash")
    return rebuilt


def collect_tested_batch(source, *, retained=(), max_source_records,
                         candidate_timeout=30.0, elapsed_limit=30.0,
                         file="<question>", label="<exercise>"):
    """Append up to 25 new note-distinct, real-grader-tested records.

    source is a trusted caller-owned iterator of already-resolved records whose
    constraints have passed. Source execution itself is not supervised here.
    Grading runs in one child with a fresh deadline for every new candidate.
    """
    where = "{}: {}".format(file, label)
    if type(max_source_records) is not int or max_source_records < 1:
        raise BatchError(where + ": max_source_records must be a positive integer")
    for value in (candidate_timeout, elapsed_limit):
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value <= 0:
            raise BatchError(where + ": time limits must be positive finite seconds")
    started = time.monotonic()
    process = reader = None
    messages, stopped = queue.Queue(maxsize=1), threading.Event()
    records, by_id, notes = [], {}, set()
    added, scanned, duplicate_ids, duplicate_notes = [], 0, 0, 0
    current = "history"
    temporary = None

    def remaining(candidate_started):
        value = min(started + elapsed_limit, candidate_started + candidate_timeout) - time.monotonic()
        if value <= 0:
            raise BatchError("candidate grading/batch boundary time budget exceeded")
        return value

    def receive(candidate_started):
        try:
            message = messages.get(timeout=remaining(candidate_started))
        except queue.Empty:
            raise BatchError("candidate grading/batch boundary time budget exceeded")
        remaining(candidate_started)
        if type(message) is not dict:
            raise BatchError("validation worker exited without a result")
        return message

    def start_worker(candidate_started):
        nonlocal process, reader, temporary
        import ctm_checkers
        import ctm_variants
        import sympy
        import mpmath
        roots = sorted({str(Path(package.__file__).resolve().parents[1])
                        for package in (ctm_checkers, ctm_variants, sympy, mpmath)})
        temporary = tempfile.TemporaryDirectory(prefix="ctm-batch-")
        request_path = Path(temporary.name) / "imports.json"
        request_path.write_text(json.dumps(roots), encoding="utf-8")
        environment = dict(os.environ)
        environment.pop("PYTHONPATH", None)
        process = subprocess.Popen([sys.executable, "-I", str(Path(__file__).resolve()), str(request_path)],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, env=environment, cwd=temporary.name)
        reader = threading.Thread(target=_read_lines, args=(process.stdout, messages, stopped),
                                  name="ctm-batch-reader", daemon=True)
        reader.start()
        if receive(candidate_started) != {"ready": True}:
            raise BatchError("invalid validation worker startup")

    try:
        for value in retained:
            row = _record(value)
            if row["id"] in by_id:
                raise BatchError("duplicate retained locator")
            records.append(row)
            by_id[row["id"]] = row
            notes.add(row["note"])
        iterator = iter(source)
        exhausted = False
        while len(added) < BATCH_SIZE:
            if time.monotonic() - started >= elapsed_limit:
                raise BatchError("batch boundary time budget exceeded")
            if scanned >= max_source_records:
                raise BatchError("source scan budget exceeded after {} records".format(scanned))
            try:
                value = next(iterator)
            except StopIteration:
                if time.monotonic() - started >= elapsed_limit:
                    raise BatchError("batch boundary time budget exceeded")
                exhausted = True
                break
            scanned += 1
            if time.monotonic() - started >= elapsed_limit:
                raise BatchError("batch boundary time budget exceeded")
            row = _record(value)
            current = row["id"]
            if row["id"] in by_id:
                if row["hash"] != by_id[row["id"]]["hash"]:
                    raise BatchError("existing candidate locator has changed content; classify it before generating more")
                duplicate_ids += 1
                continue
            # A note-duplicate path was still encountered. Reserve its locator
            # too, so another occurrence cannot present it as a fresh candidate.
            by_id[row["id"]] = row
            if row["note"] in notes:
                duplicate_notes += 1
                continue
            candidate_started = time.monotonic()
            if process is None:
                start_worker(candidate_started)
            index = len(added)
            request = json.dumps({"index": index, "record": row, "file": file, "label": label},
                                 ensure_ascii=True, allow_nan=False).encode("utf-8")
            if len(request) >= MAX_IPC:
                raise BatchError("candidate request exceeds byte limit")
            process.stdin.write(request + b"\n")
            process.stdin.flush()
            output_bytes = 0
            while True:
                message = receive(candidate_started)
                if message.get("index") != index or type(message.get("index")) is not int:
                    raise BatchError("unexpected validation worker candidate index")
                if set(message) == {"index", "output"} and isinstance(message["output"], str):
                    output_bytes += len(message["output"].encode("utf-8"))
                    if output_bytes > MAX_IPC:
                        raise BatchError("candidate author output exceeds byte limit")
                    sys.stdout.write(message["output"])
                    continue
                if set(message) == {"index", "error"} and isinstance(message["error"], str):
                    raise BatchError(message["error"])
                if set(message) != {"index", "result"} or type(message["result"]) is not dict or message["result"].get("passed") is not True:
                    raise BatchError("invalid validation worker result")
                row["tests"] = message["result"]
                row = _record(row)
                break
            records.append(row)
            added.append(row)
            by_id[row["id"]] = row
            notes.add(row["note"])
        if time.monotonic() - started >= elapsed_limit:
            raise BatchError("batch boundary time budget exceeded")
        return {"candidates": records, "added": added, "tested": len(added),
                "source_records": scanned, "duplicate_ids": duplicate_ids,
                "duplicate_notes": duplicate_notes, "exhausted": exhausted}
    except Exception as error:
        raise BatchError("{}: candidate {}: {}".format(where, current, error)) from error
    finally:
        stopped.set()
        if process is not None:
            if process.poll() is None:
                process.kill()
            process.wait()
            if process.stdin is not None:
                process.stdin.close()
        if reader is not None:
            reader.join(timeout=2)
            if reader.is_alive():
                raise BatchError(where + ": validation worker reader failed to terminate")
        if temporary is not None:
            temporary.cleanup()


def _worker(request_path):
    roots = json.loads(Path(request_path).read_text(encoding="utf-8"))
    sys.path[:0] = roots
    from ctm_variants.validation import validate_math_candidate
    protocol = sys.stdout

    def emit(value):
        text = json.dumps(value, ensure_ascii=True, allow_nan=False)
        if len(text.encode("utf-8")) >= MAX_IPC:
            raise BatchError("validation worker output exceeds byte limit")
        protocol.write(text + "\n")
        protocol.flush()

    emit({"ready": True})
    for line in iter(lambda: sys.stdin.buffer.readline(MAX_IPC + 1), b""):
        index = None
        try:
            if len(line) > MAX_IPC:
                raise BatchError("candidate request exceeds byte limit")
            request = json.loads(line)
            index = request["index"]
            if type(index) is not int or index < 0:
                raise BatchError("invalid candidate index")
            row = _record(request["record"])
            data = row["data"]
            if set(data) != {"options", "context", "teacher_inputs"}:
                raise BatchError("resolved candidate data needs options, context and teacher_inputs")
            class ForwardOutput:
                def write(self, text):
                    emit({"index": index, "output": text})
                    return len(text)
                def flush(self):
                    pass
            with contextlib.redirect_stdout(ForwardOutput()):
                result = validate_math_candidate(data["options"], ".", context=data["context"],
                    teacher_inputs=data["teacher_inputs"], file=request["file"],
                    label=request["label"], locator=row["id"])
            emit({"index": index, "result": result})
        except Exception as error:
            emit({"index": index, "error": str(error)})


if __name__ == "__main__":
    _worker(sys.argv[1])
