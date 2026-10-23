"""Native exhaustive enumeration contracts. AGPL-3.0-or-later."""
import os
import pathlib
import sys
import threading
import unittest
from unittest.mock import patch

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "authoring")] + (os.environ.get("CTM_CHECKERS_WHEEL") or str(ROOT / "src")).split(os.pathsep)
import sympy as sp
from ctm_variants.enumeration import enumerate_exhaustive, _enumerate
from ctm_variants.generation import execute, GenerationError


class EnumerationTests(unittest.TestCase):
    def test_dependent_tree_exact_tapes_replay_and_constraints(self):
        source = "a=pick([1,2,3])\nb=pick(1,a)\nrequire(a!=b)\nc=sigfig(sin(a/7),2)"
        result = enumerate_exhaustive(source)
        self.assertEqual(result["raw_paths"],6)
        self.assertEqual(result["rejected"],3)
        self.assertEqual(result["duplicates"],0)
        self.assertEqual([row["choices"] for row in result["candidates"]], [[2,1],[3,1],[3,2]])
        for row in result["candidates"]:
            self.assertEqual(execute(source,replay=row["choices"]),row)
        self.assertEqual(enumerate_exhaustive(source),result)

    def test_duplicate_tapes_preserve_exact_bool_integer_distinction(self):
        result = enumerate_exhaustive("a=pick([1,True,1,False,0,False])")
        self.assertEqual(result["raw_paths"],6)
        self.assertEqual(result["duplicates"],2)
        choices = [row["choices"][0] for row in result["candidates"]]
        self.assertIsInstance(choices[0],sp.Integer)
        self.assertIs(choices[1],True)
        self.assertIs(choices[2],False)
        self.assertIsInstance(choices[3],sp.Integer)
        self.assertEqual(choices[3],0)
        self.assertEqual(len({row["locator"] for row in result["candidates"]}),4)
        for row in result["candidates"]:
            self.assertEqual(execute("a=pick([1,True,1,False,0,False])",replay=row["choices"]),row)

    def test_raw_budget_counts_duplicates_and_rejections(self):
        for source in ("a=pick([1,1,1])", "a=pick([1,2,3])\nrequire(False)",
                       "a=pick([1,2])\nb=pick([1,2])"):
            with self.subTest(source=source), self.assertRaisesRegex(GenerationError,"raw choice space exceeds"):
                enumerate_exhaustive(source,raw_path_limit=2)
        self.assertEqual(enumerate_exhaustive("a=pick([1,2])",raw_path_limit=2)["raw_paths"],2)

    def test_rejected_prefix_stops_before_unreachable_choices(self):
        result = enumerate_exhaustive("a=pick([1,2])\nrequire(a==1)\nb=pick(1,a)",raw_path_limit=2)
        self.assertEqual(result["raw_paths"],2)
        self.assertEqual(result["rejected"],1)
        self.assertEqual(result["candidates"][0]["choices"],[1,1])
        self.assertEqual(enumerate_exhaustive("require(False)\na=pick(1,20000)",raw_path_limit=1)["candidates"],[])

    def test_deterministic_source_and_empty_source(self):
        result=enumerate_exhaustive("a=round(1.005,2)")
        self.assertEqual(result["raw_paths"],1)
        self.assertEqual(result["candidates"],[execute("a=round(1.005,2)")])
        self.assertEqual(enumerate_exhaustive("")["candidates"],[execute("")])

    def test_multiple_random_calls_keep_distinct_tapes_with_equal_results(self):
        result=enumerate_exhaustive("a=rand(2)+rand(2)")
        self.assertEqual(result["raw_paths"],4)
        self.assertEqual(result["duplicates"],0)
        self.assertEqual([row["choices"] for row in result["candidates"]],[[0,0],[0,1],[1,0],[1,1]])
        self.assertEqual([row["variables"]["a"] for row in result["candidates"]],[0,1,1,2])

    def test_errors_are_contextual_and_never_return_partial_candidates(self):
        for source in ("a=pick([1,0])\nb=1/a", "a=pick([1,2])\nb=missing", "import os"):
            with self.subTest(source=source), self.assertRaisesRegex(GenerationError,"course.qmd: dependent: line "):
                enumerate_exhaustive(source,file="course.qmd",label="dependent")
        for limit in (True,0,20001,1.5):
            with self.assertRaises(GenerationError):
                enumerate_exhaustive("a=1",raw_path_limit=limit)

    def test_one_worker_and_deadline_cleanup(self):
        import ctm_variants.enumeration as enumeration
        real=enumeration.subprocess.Popen
        children=[]
        def launch(*args,**kwargs):
            process=real(*args,**kwargs)
            children.append(process)
            return process
        with patch.object(enumeration.subprocess,"Popen",launch):
            self.assertEqual(len(enumerate_exhaustive("a=pick([1,2,3])")["candidates"]),3)
            for option in ("variable_timeout","variant_timeout","exercise_timeout"):
                with self.assertRaisesRegex(GenerationError,"time budget"):
                    enumerate_exhaustive("a=1",**{option:0.001})
        self.assertEqual(len(children),4)
        self.assertTrue(all(child.poll() is not None for child in children))
        self.assertFalse(any(t.name=="ctm-enumeration-reader" for t in threading.enumerate()))

    def test_raw_overflow_precedes_child_prefix_materialization(self):
        events=[]
        with self.assertRaisesRegex(GenerationError,"raw choice space exceeds"):
            _enumerate("a=pick([1,2])\nb=pick(1,20000)",{},20000,events.append)
        self.assertFalse(any(event.get("end")=="accepted" for event in events))

    def _fake_worker(self,messages,**options):
        import json
        import ctm_variants.enumeration as enumeration
        real=enumeration.subprocess.Popen
        children=[]
        script="import time; " + "; ".join(
            "time.sleep("+repr(message)+")" if isinstance(message,float)
            else "print("+repr(json.dumps(message))+",flush=True)" for message in messages) + "; time.sleep(10)"
        def launch(*args,**kwargs):
            process=real([sys.executable,"-c",script],**kwargs)
            children.append(process)
            return process
        try:
            with patch.object(enumeration.subprocess,"Popen",launch):
                return enumerate_exhaustive("a=pick([1,2])\nb=1",**options)
        finally:
            self.assertTrue(children and all(child.poll() is not None for child in children))
            self.assertFalse(any(t.name=="ctm-enumeration-reader" for t in threading.enumerate()))

    def test_deadlines_after_real_progress_kill_and_join_worker(self):
        progress=[{"attempt":0},{"statement":0,"line":1}]
        for option in ("variable_timeout","variant_timeout","exercise_timeout"):
            with self.subTest(option=option), self.assertRaisesRegex(GenerationError,"time budget"):
                self._fake_worker(progress,**{option:0.5})

    def test_protocol_rejects_repeated_boundaries_and_incomplete_frontier(self):
        for messages,expected in [
            ([{"attempt":0},{"attempt":0}],"attempt boundary"),
            ([{"attempt":0},{"statement":0,"line":1},{"statement":0,"line":1}],"statement boundary"),
            ([{"attempt":0},{"statement":0,"line":1},{"end":"branch","size":True}],"branch size"),
            ([{"attempt":0},{"statement":0,"line":1},{"end":"branch","size":2},{"done":0}],"completion"),
            ([{"attempt":0},{"statement":0,"line":1},{"end":"accepted","result":{}}],"path end")]:
            with self.subTest(expected=expected), self.assertRaisesRegex(GenerationError,expected):
                self._fake_worker(messages)

    def test_absolute_budget_survives_valid_attempt_and_statement_progress(self):
        attempts=[{"attempt":0},{"statement":0,"line":1},{"end":"branch","size":2},
                  0.3,{"attempt":1},{"statement":0,"line":1},0.3,{"done":0}]
        with self.assertRaisesRegex(GenerationError,"time budget"):
            self._fake_worker(attempts,exercise_timeout=0.5)
        statements=[{"attempt":0},{"statement":0,"line":1},0.3,
                    {"statement":1,"line":2},0.3,{"done":0}]
        with self.assertRaisesRegex(GenerationError,"time budget"):
            self._fake_worker(statements,variant_timeout=0.5)
        # Only the per-variable timer resets at a valid next statement.
        with self.assertRaisesRegex(GenerationError,"invalid worker completion"):
            self._fake_worker(statements,variable_timeout=0.5)


if __name__ == "__main__":
    unittest.main()
