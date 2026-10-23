"""Lazy supplied-record batch contracts. AGPL-3.0-or-later."""
import contextlib
import copy
import io
import itertools
import os
import pathlib
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "authoring")] + (os.environ.get("CTM_CHECKERS_WHEEL") or str(ROOT / "src")).split(os.pathsep)
from sympy import Integer
from ctm_checkers.variants import question_context
from ctm_variants.model import candidate, snapshot
from ctm_variants.batches import collect_tested_batch, BatchError


def record(number, *, note=None, checker=None, typed=None):
    # Fixture construction supplies the already-resolved strings; production
    # collection deliberately contains no teacher printer/template handling.
    options = {"mode": "custom" if checker else "equivalent", "field-labels": ["Answer"],
               "vars": "", "tests": []}
    if checker:
        options["checker"] = checker
    return candidate("choice-" + str(number),
        snapshot([str(number)], {"Answer": str(number)}, {"mode": options["mode"]}),
        note=str(number) if note is None else note,
        data={"options": options, "context": question_context(["Answer"],
              {"a": Integer(number)}, {"Answer": Integer(number)}),
              "teacher_inputs": {"Answer": str(number) if typed is None else typed}})


class BatchTests(unittest.TestCase):
    def test_lazy_stop_after_25_uses_one_worker_and_retains_unconsumed_source(self):
        import ctm_variants.batches as batches
        real = batches.subprocess.Popen
        children, consumed = [], []
        def launch(*args, **kwargs):
            child = real(*args, **kwargs)
            children.append(child)
            return child
        def source():
            for number in itertools.count():
                consumed.append(number)
                yield record(number)
        stream = source()
        with patch.object(batches.subprocess, "Popen", launch):
            result = collect_tested_batch(stream, max_source_records=50)
        self.assertEqual(consumed, list(range(25)))
        self.assertEqual(result["tested"], 25)
        self.assertFalse(result["exhausted"])
        self.assertEqual(result["source_records"], 25)
        self.assertEqual(next(stream)["id"], "choice-25")
        self.assertTrue(all(row["tests"]["passed"] for row in result["added"]))
        self.assertEqual(len(children), 1)
        self.assertIsNotNone(children[0].poll())
        self.assertFalse(any(t.name == "ctm-batch-reader" for t in threading.enumerate()))

    def test_generate_more_preserves_history_and_reserves_rejected_notes(self):
        retained = [record(100, note="previously rejected note"), record(101)]
        before = copy.deepcopy(retained)
        stream = itertools.chain([record(100, note="previously rejected note"),
            record(102, note="previously rejected note")], (record(n) for n in range(25)))
        result = collect_tested_batch(stream, retained=retained, max_source_records=30)
        self.assertEqual(retained, before)
        self.assertEqual(result["candidates"][:2], before)
        self.assertEqual(result["tested"], 25)
        self.assertEqual(result["duplicate_ids"], 1)
        self.assertEqual(result["duplicate_notes"], 1)
        self.assertEqual(len(result["candidates"]), 27)

    def test_constraint_filtered_source_note_dedup_and_real_exhaustion(self):
        from ctm_variants.enumeration import enumerate_exhaustive
        rows = enumerate_exhaustive("a=pick([1,2,3])\nrequire(a!=2)")["candidates"]
        source = [record(int(row["variables"]["a"]), note="same resolved note") for row in rows]
        result = collect_tested_batch(source, max_source_records=10)
        self.assertTrue(result["exhausted"])
        self.assertEqual(result["tested"], 1)
        self.assertEqual(result["source_records"], 2)
        self.assertEqual(result["duplicate_notes"], 1)
        empty = collect_tested_batch([], max_source_records=1)
        self.assertEqual(empty["added"], [])
        self.assertTrue(empty["exhausted"])

    def test_note_duplicate_also_reserves_its_encountered_locator(self):
        retained = [record(100, note="reserved")]
        result = collect_tested_batch([record(1, note="reserved"),
            record(1, note="a later occurrence"), record(2)],
            retained=retained, max_source_records=5)
        self.assertEqual(result["tested"], 1)
        self.assertEqual(result["duplicate_notes"], 1)
        self.assertEqual(result["duplicate_ids"], 1)
        self.assertEqual(result["added"][0]["id"], "choice-2")

    def test_grader_failure_is_error_without_silent_resampling_or_history_mutation(self):
        retained = [record(100)]
        before, consumed = copy.deepcopy(retained), []
        def source():
            for number in (1, 2):
                consumed.append(number)
                yield record(number, typed="wrong")
        with self.assertRaisesRegex(BatchError, "course.qmd: test: candidate choice-1.*teacher answers"):
            collect_tested_batch(source(), retained=retained, max_source_records=3,
                file="course.qmd", label="test")
        self.assertEqual(consumed, [1])
        self.assertEqual(retained, before)

    def test_authored_test_failure_stops_the_batch(self):
        row = record(1)
        row["data"]["options"]["tests"] = [{"name": "bad authored expectation", "answers": [2], "expect": "correct"}]
        with self.assertRaisesRegex(BatchError, "authored tests.*bad authored expectation"):
            collect_tested_batch([row], max_source_records=2)

    def test_changed_locator_errors_and_input_records_remain_untouched(self):
        previous, changed = record(1), record(1)
        changed["snapshot"] = snapshot(["2"], {"Answer": "2"}, {"mode": "equivalent"})
        changed = candidate(changed["id"], changed["snapshot"], note=changed["note"], data=changed["data"])
        with self.assertRaisesRegex(BatchError, "changed content"):
            collect_tested_batch([changed], retained=[previous], max_source_records=2)
        malformed = record(1)
        malformed["hash"] = "not canonical"
        with self.assertRaisesRegex(BatchError, "snapshot/hash"):
            collect_tested_batch([malformed], max_source_records=2)

    def test_scan_budget_is_an_error_not_a_truncated_candidate_population(self):
        repeated = itertools.repeat(record(1))
        with self.assertRaisesRegex(BatchError, "scan budget exceeded after 2"):
            collect_tested_batch(repeated, max_source_records=2)
        for limit in (True, 0, 1.5):
            with self.assertRaisesRegex(BatchError, "max_source_records"):
                collect_tested_batch([], max_source_records=limit)

    def test_source_elapsed_limit_is_explicitly_checked_at_boundaries(self):
        def source():
            time.sleep(0.03)
            yield record(1)
        with self.assertRaisesRegex(BatchError, "boundary time budget"):
            collect_tested_batch(source(), max_source_records=2, elapsed_limit=0.01)

    def test_hanging_grader_is_killed_and_author_output_does_not_reset_deadline(self):
        import ctm_variants.batches as batches
        real, children = batches.subprocess.Popen, []
        def launch(*args, **kwargs):
            child = real(*args, **kwargs)
            children.append(child)
            return child
        with tempfile.TemporaryDirectory() as directory:
            marker = pathlib.Path(directory) / "entered.txt"
            checker = "import time\ndef check(r,s):\n    open(" + repr(str(marker)) + ", 'w').write('entered')\n    print('author output')\n    time.sleep(10)\n    return True"
            output = io.StringIO()
            with patch.object(batches.subprocess, "Popen", launch), contextlib.redirect_stdout(output):
                with self.assertRaisesRegex(BatchError, "time budget"):
                    collect_tested_batch([record(1, checker=checker)], max_source_records=2,
                        candidate_timeout=2, elapsed_limit=10)
            self.assertEqual(marker.read_text(), "entered")
            self.assertEqual(output.getvalue(), "author output\n")
        self.assertTrue(children and all(child.poll() is not None for child in children))
        self.assertFalse(any(t.name == "ctm-batch-reader" for t in threading.enumerate()))

    def test_author_output_preserved_and_missing_resolved_data_fails_explicitly(self):
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            result = collect_tested_batch([record(1, checker="def check(r,s):\n    print('hello')\n    return True")], max_source_records=2)
        self.assertEqual(output.getvalue(), "hello\n")
        self.assertEqual(result["tested"], 1)
        row = record(1)
        row["data"].pop("teacher_inputs")
        with self.assertRaisesRegex(BatchError, "data needs"):
            collect_tested_batch([row], max_source_records=2)


if __name__ == "__main__":
    unittest.main()
