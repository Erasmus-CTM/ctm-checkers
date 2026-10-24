"""Actual-child retained replay, lazy tested batches and history contracts."""
import copy
import pathlib
import sys
import threading
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "authoring"), str(ROOT / "src")]
from ctm_checkers.variants import encode, question_context
from ctm_variants import history
from ctm_variants.generation import GenerationError, ReplayUnavailable, execute
from ctm_variants.model import candidate, digest, snapshot
from ctm_variants.orchestration import generate, reconcile


def resolve(execution):
    number = execution["variables"]["a"]
    text = str(number)
    return candidate(digest(encode(execution["choices"])),
        snapshot([text], {"Answer": text}, {"mode": "equivalent"},
                 {name: str(value) for name, value in execution["variables"].items()}),
        note=text, data={"options": {"mode": "equivalent", "field-labels": ["Answer"], "tests": []},
        "context": question_context(["Answer"], execution["variables"], {"Answer": number}),
        "teacher_inputs": {"Answer": text}})


class OrchestrationTests(unittest.TestCase):
    def tearDown(self):
        self.assertFalse(any(thread.name in {"ctm-choice-stream-reader", "ctm-generation-reader", "ctm-batch-reader"}
                             for thread in threading.enumerate()))

    def test_generate25more_counts_tested_distinct_preserves_rejections_and_stops_at25(self):
        first = generate(history.empty("q"), "a=pick(1,60)", resolve, current=[],
                         attempt_limit=100, max_source_records=100, seed="q", elapsed_limit=60)
        self.assertEqual(first["tested"], 25)
        self.assertEqual(first["stream"]["yielded"], 25)
        self.assertEqual(len(first["manifest"]["proposals"]), 25)
        self.assertTrue(all(row["tests"]["passed"] for row in first["added"]))
        manifest = history.decision(first["manifest"], first["records"], first["records"][0]["id"],
                                    "rejected", reason="retain this rejected note")
        saved = copy.deepcopy(manifest)
        more = generate(manifest, "a=pick(1,100)", resolve, current=first["records"],
                        attempt_limit=200, max_source_records=200, seed="q", elapsed_limit=60)
        self.assertEqual(more["tested"], 25)
        self.assertEqual(more["records"][:25], first["records"])
        self.assertEqual(len({row["note"] for row in more["records"]}), 50)
        self.assertEqual(more["manifest"]["proposals"][:25], saved["proposals"])
        self.assertEqual(more["manifest"]["decisions"], saved["decisions"])
        self.assertEqual(more["manifest"]["events"], saved["events"])
        self.assertEqual(manifest, saved)

    def test_retained_replay_growth_incidental_changes_and_gone_are_independent(self):
        first = generate(history.empty("q"), "a=pick(1,2)", resolve, current=[],
                         attempt_limit=10, max_source_records=10, seed="q")
        decided = history.decision(first["manifest"], first["records"], first["records"][0]["id"], "approved")
        current = reconcile(decided, "a=pick(1,100)\nunused=123", resolve, max_records=10)
        self.assertEqual(current["manifest"], decided)
        self.assertEqual(current["classification"]["entries"][0]["state"], "current")
        # Semantic identity survives incidental display/unused-variable edits.
        updated = history.decision(current["manifest"], current["records"], first["records"][0]["id"], "approved")
        self.assertEqual(updated["decisions"][0]["n"], 1)
        gone = reconcile(decided, "a=pick(1,1)", resolve, max_records=10)
        self.assertEqual(len(gone["records"]), 1)
        self.assertEqual(gone["gone"], 1)
        self.assertEqual(gone["manifest"]["proposals"], decided["proposals"])
        def changed(execution):
            modified = copy.deepcopy(execution)
            modified["variables"]["a"] += 10
            return resolve(modified)
        corrected = reconcile(decided, "a=pick(1,2)", changed, max_records=10)
        self.assertEqual(corrected["classification"]["entries"][0]["state"], "changed")
        self.assertEqual(corrected["manifest"]["proposals"][:2], decided["proposals"])
        self.assertEqual(len(corrected["manifest"]["proposals"]), 4)
        self.assertEqual(corrected["manifest"]["decisions"], decided["decisions"])
        with self.assertRaisesRegex(ValueError, "at least one"):
            history.publication(corrected["manifest"]["decisions"], corrected["records"])
        with self.assertRaises(ReplayUnavailable):
            execute("a=pick(1,1)", replay=[2])

    def test_constraints_duplicates_test_and_execution_errors_never_resample_to_success(self):
        def repeated(execution):
            row = resolve(execution)
            row["note"] = "one resolved note"
            return row
        result = generate(history.empty("q"), "a=pick(1,4)\nrequire(a!=2)", repeated, current=[],
                          attempt_limit=10, max_source_records=10, seed="q")
        self.assertEqual(result["tested"], 1)
        self.assertEqual(result["duplicate_notes"], 2)
        self.assertTrue(result["exhausted"])
        def failed(execution):
            row = resolve(execution)
            row["data"]["teacher_inputs"]["Answer"] = "999"
            return row
        empty = history.empty("q")
        with self.assertRaisesRegex(ValueError, "teacher answers"):
            generate(empty, "a=pick(1,3)", failed, current=[], attempt_limit=10, max_source_records=10)
        self.assertEqual(empty, history.empty("q"))
        first = generate(empty, "a=pick(1,2)", resolve, current=[], attempt_limit=10, max_source_records=10)
        with self.assertRaises(GenerationError):
            reconcile(first["manifest"], "a=pick(1,2)\nb=1/0", resolve, max_records=10)
        with self.assertRaisesRegex(ValueError, "resource budget"):
            reconcile(first["manifest"], "a=pick(1,2)", resolve, max_records=1)


if __name__ == "__main__":
    unittest.main()
