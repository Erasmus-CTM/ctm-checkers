"""Demand-driven native choice traversal. AGPL-3.0-or-later."""
import itertools
import json
import os
import pathlib
import sys
import threading
import time
import unittest
from unittest.mock import patch

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "authoring")] + (os.environ.get("CTM_CHECKERS_WHEEL") or str(ROOT / "src")).split(os.pathsep)
import sympy as sp
from ctm_checkers.variants import encode
from ctm_variants.streaming import choice_stream
from ctm_variants.generation import execute, GenerationError
from ctm_variants.enumeration import enumerate_exhaustive


class StreamTests(unittest.TestCase):
    def test_seeded_traversal_is_complete_replayable_and_label_deterministic(self):
        source = "a=pick(1,4)\nb=pick([10,20,30])"
        def rows(seed):
            with choice_stream(source, attempt_limit=100, seed=seed) as stream:
                return list(stream)
        first = rows("lesson:q")
        self.assertEqual(first, rows("lesson:q"))
        self.assertNotEqual([r["choices"] for r in first], [r["choices"] for r in rows("lesson:other")])
        self.assertEqual({tuple(r["choices"]) for r in first}, set(itertools.product(range(1,5), [10,20,30])))
        self.assertEqual(execute(source, replay=first[0]["choices"])["variables"], first[0]["variables"])

    def test_first25_of_large_cartesian_space_one_worker_no_frontier_pool(self):
        import ctm_variants.streaming as streaming
        real, children = streaming.subprocess.Popen, []
        def launch(*args, **kwargs):
            child = real(*args, **kwargs)
            children.append(child)
            return child
        with patch.object(streaming.subprocess, "Popen", launch):
            with choice_stream("a=pick(1,20000)\nb=pick(1,20000)", attempt_limit=100) as stream:
                rows = list(itertools.islice(stream, 25))
                self.assertEqual([row["choices"] for row in rows], [[1, n] for n in range(1, 26)])
                self.assertEqual(stream.stats["attempts"], 27)
                self.assertEqual(stream.stats["branches"], 2)
                self.assertEqual(stream.stats["paths"], 25)
                self.assertFalse(stream.stats["exhausted"])
                time.sleep(0.03)
                self.assertTrue(stream.messages.empty(), "no progress/next result is prefetched")
                self.assertIsNone(stream.process.poll())
        self.assertEqual(len(children), 1)
        self.assertIsNotNone(children[0].poll())
        self.assertTrue(stream.stats["closed"])
        self.assertFalse(any(t.name == "ctm-choice-stream-reader" for t in threading.enumerate()))

    def test_does_not_evaluate_a_failing_next_path_until_demanded(self):
        source = "a=pick([1,0])\nb=1/a"
        with choice_stream(source, attempt_limit=10) as stream:
            self.assertEqual(next(stream)["variables"]["b"], 1)
            time.sleep(0.03)
            self.assertTrue(stream.messages.empty())
            self.assertIsNone(stream.process.poll())
            with self.assertRaisesRegex(GenerationError, "lesson.qmd: branch: line 2"):
                # The context below is supplied on the second stream, so this
                # branch is checked separately after the no-prefetch assertion.
                with choice_stream(source, attempt_limit=10, file="lesson.qmd", label="branch") as checked:
                    next(checked)
                    next(checked)

    def test_dependent_constraints_equal_exhaustive_and_exact_replay(self):
        source = "a=pick([1,2,3])\nb=pick(1,a)\nrequire(a!=b)\nc=sigfig(sin(a/7),2)"
        expected = enumerate_exhaustive(source)["candidates"]
        with choice_stream(source, attempt_limit=30) as stream:
            rows = list(stream)
            self.assertEqual(rows, expected)
            self.assertEqual(stream.stats["rejected"], 3)
            self.assertTrue(stream.stats["exhausted"])
            self.assertTrue(stream.stats["closed"])
        for row in rows:
            self.assertEqual(row, execute(source, replay=row["choices"]))

    def test_exact_tape_dedup_preserves_boolean_integer_distinction(self):
        with choice_stream("a=pick([1,True,1,False,0,False])", attempt_limit=10) as stream:
            rows = list(stream)
            self.assertEqual(stream.stats["duplicates"], 2)
            self.assertEqual(stream.stats["paths"], 6)
            self.assertEqual(stream.stats["yielded"], 4)
        values = [row["choices"][0] for row in rows]
        self.assertIsInstance(values[0], sp.Integer)
        self.assertIs(values[1], True)
        self.assertIs(values[2], False)
        self.assertIsInstance(values[3], sp.Integer)

    def test_empty_deterministic_rejected_and_exact_initial_variables(self):
        for source in ("", "a=round(1.005,2)"):
            with choice_stream(source, attempt_limit=1) as stream:
                self.assertEqual(list(stream), [execute(source)])
                self.assertEqual(stream.stats["attempts"], 1)
        with choice_stream("require(False)\na=pick(1,20000)", attempt_limit=1) as stream:
            self.assertEqual(list(stream), [])
            self.assertEqual(stream.stats["rejected"], 1)
        x = sp.Symbol("x", positive=True)
        values = {"x": x, "M": sp.Matrix([[x, 0], [0, sp.Rational(1,3)]])}
        source = "a=pick([1,2])\nb=a*det(M)"
        with choice_stream(source, attempt_limit=10, variables=values) as stream:
            for row in stream:
                self.assertEqual(row, execute(source, variables=values, replay=row["choices"]))
                self.assertTrue(row["variables"]["x"].is_positive)

    def test_actual_attempt_budget_errors_instead_of_truncating(self):
        with choice_stream("a=pick([1,2])", attempt_limit=2) as stream:
            self.assertEqual(next(stream)["choices"], [1])
            with self.assertRaisesRegex(GenerationError, "actual prefix attempt limit exceeded after 2"):
                next(stream)
            self.assertTrue(stream.stats["closed"])
        for limit in (True, 0, -1, 1.5):
            with self.assertRaisesRegex(GenerationError, "attempt_limit"):
                with choice_stream("a=1", attempt_limit=limit):
                    pass

    def test_consumer_idle_counts_in_absolute_exercise_deadline(self):
        import ctm_variants.streaming as streaming
        real_clock = time.monotonic
        with choice_stream("a=pick([1,2])", attempt_limit=10, exercise_timeout=5) as stream:
            next(stream)
            with patch.object(streaming.time, "monotonic", lambda: real_clock() + 100):
                with self.assertRaisesRegex(GenerationError, "time budget"):
                    next(stream)
            self.assertTrue(stream.stats["closed"])

    def fake(self, messages, source="a=1", **options):
        import ctm_variants.streaming as streaming
        real, children = streaming.subprocess.Popen, []
        script = "import sys,time; print('{\"ready\":true}',flush=True); sys.stdin.readline(); "
        script += "; ".join("time.sleep(" + repr(item) + ")" if isinstance(item, float)
            else "print(" + repr(json.dumps(item)) + ",flush=True)" for item in messages)
        script += "; time.sleep(10)"
        def launch(*args, **kwargs):
            child = real([sys.executable, "-c", script], **kwargs)
            children.append(child)
            return child
        try:
            with patch.object(streaming.subprocess, "Popen", launch):
                with choice_stream(source, attempt_limit=10, **options) as stream:
                    return list(stream)
        finally:
            self.assertTrue(children and all(child.poll() is not None for child in children))
            self.assertFalse(any(t.name == "ctm-choice-stream-reader" for t in threading.enumerate()))

    def test_deadlines_after_real_native_worker_progress_kill_and_join(self):
        progress = [{"attempt": 0}, {"statement": 0, "line": 1}, 1.0]
        for key in ("variable_timeout", "attempt_timeout", "exercise_timeout"):
            with self.subTest(key=key), self.assertRaisesRegex(GenerationError, "time budget"):
                self.fake(progress, **{key:0.25})

    def test_attempt_and_exercise_budgets_do_not_reset_with_valid_progress(self):
        progress = [{"attempt":0}, {"statement":0,"line":1}, 0.3,
            {"statement":1,"line":2}, 0.3]
        with self.assertRaisesRegex(GenerationError, "time budget"):
            self.fake(progress, source="a=1\nb=2", variable_timeout=2,
                attempt_timeout=0.5, exercise_timeout=2)
        progress = [{"attempt":0},{"statement":0,"line":1},{"end":"branch","size":2},0.3,
            {"attempt":1},{"statement":0,"line":1},{"end":"rejected"},0.3,
            {"attempt":2},{"statement":0,"line":1}]
        with self.assertRaisesRegex(GenerationError, "time budget"):
            self.fake(progress, variable_timeout=2, attempt_timeout=2, exercise_timeout=0.5)

    def test_only_variable_budget_resets_at_next_valid_statement(self):
        result = encode({"variables":{"a":sp.Integer(1),"b":sp.Integer(2)},"choices":[]})
        progress = [{"attempt":0},{"statement":0,"line":1},0.3,
            {"statement":1,"line":2},0.3,{"end":"accepted","result":result}]
        rows = self.fake(progress, source="a=1\nb=2", variable_timeout=0.5,
            attempt_timeout=2, exercise_timeout=2)
        self.assertEqual(rows[0]["variables"], {"a":1,"b":2})

    def test_protocol_rejects_premature_completion_repeated_boundaries_and_shapes(self):
        cases = [
            ([{"done":0}], "completion"),
            ([{"attempt":0},{"attempt":0}], "attempt boundary"),
            ([{"attempt":0},{"statement":0,"line":1},{"statement":0,"line":1}], "statement boundary"),
            ([{"attempt":0},{"statement":0,"line":1},{"end":"branch","size":True}], "branch boundary"),
            ([{"attempt":0},{"end":"accepted","result":encode({"variables":{},"choices":[]})}], "result boundary"),
            ([{"attempt":0},{"statement":0,"line":1},{"end":"accepted","result":encode({"variables":[],"choices":[]})}], "result shape"),
        ]
        for messages, expected in cases:
            with self.subTest(expected=expected), self.assertRaisesRegex(GenerationError, expected):
                self.fake(messages)


if __name__ == "__main__":
    unittest.main()
