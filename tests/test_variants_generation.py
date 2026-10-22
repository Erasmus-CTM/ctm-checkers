"""Native bounded variables execution tests. AGPL-3.0-or-later."""
import pathlib
import sys
import threading
import time
import unittest
from unittest.mock import patch

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "authoring"), str(ROOT / "src")]
import sympy as sp
from ctm_variants.generation import (execute, GenerationError, Rejected, _domain,
    _source, _run, _read_lines, MAX_IPC)


class LanguageTests(unittest.TestCase):
    def test_exact_arithmetic_cas_and_helpers(self):
        x = sp.Symbol("x")
        result = execute("a=0.1000000000000000001\nb=1/3\nf=(x-2)/(x+3)\nd=factor(diff(f,x))\nv=subs(d,x,1)\nm=Matrix([[1,2],[3,4]])\nz=det(m)\nt=transpose(m)",
                         variables={"x": x})
        values = result["variables"]
        self.assertEqual(values["a"], sp.Rational("0.1000000000000000001"))
        self.assertEqual(values["b"], sp.Rational(1,3))
        self.assertEqual(values["v"], sp.Rational(5,16))
        self.assertEqual(values["z"], -2)
        self.assertEqual(values["t"], sp.Matrix([[1,3],[2,4]]))

    def test_seed_determinism_value_replay_and_range_growth(self):
        source = "a=rand(5)+2\nb=pick(-2,2,exclude=[a-2])\nrequire(a>=2, b != a-2)"
        first = execute(source, seed="label")
        second = execute(source, seed="label")
        self.assertEqual(first, second)
        self.assertEqual(execute(source, seed="another", replay=first["choices"]), first)
        replayed = execute(source.replace("rand(5)", "rand(6)"), replay=first["choices"])
        self.assertEqual(replayed, first)
        with self.assertRaisesRegex(GenerationError, "absent"):
            execute("a=rand(1)", replay=[2])
        with self.assertRaisesRegex(GenerationError, "unused"):
            execute("a=1", replay=[2])

    def test_replay_and_exclusions_use_exact_structural_values(self):
        for source, replay in [
            ("a=pick([1])", [True]), ("a=pick([True])", [1]),
            ("a=sample([1,2],1)", [[True]]), ("a=sample([True,2],1)", [[1]]),
            ("a=pick([[1]])", [[True]])]:
            with self.subTest(source=source), self.assertRaisesRegex(GenerationError,"absent"):
                execute(source,replay=replay)
        self.assertEqual(execute("a=pick([1],exclude=[True])",replay=[1])["variables"]["a"],1)
        self.assertIs(execute("a=pick([True],exclude=[1])",replay=[True])["variables"]["a"],True)
        self.assertEqual(execute("a=pick(1,1,exclude=[True])",replay=[sp.Integer(1)])["variables"]["a"],1)

    def test_require_rejects_without_resampling_and_names_source(self):
        with self.assertRaisesRegex(Rejected, "course.qmd: tangent: line 2"):
            execute("a=rand(5)\nrequire(a!=0)", replay=[0], file="course.qmd", label="tangent")
        result = execute("a=1\nrequire(a==1 or missing > 0)")
        self.assertEqual(result["variables"]["a"], 1)
        with self.assertRaisesRegex(GenerationError, "course.qmd: tangent"):
            execute("import os", file="course.qmd", label="tangent")

    def test_unsupported_source_and_dangerous_strings_fail_closed(self):
        for source in ["a=__import__('os')", "a=subs('bad',x,1)", "a=x.__class__",
                       "a=raw('x')", "for x in [1]: pass", "a=1\na=2",
                       "a=pick([1,2])+1", "sqrt=1", "a=rand(1.5)", "a=dispdp(1,2)", "a=round(1.005,2)", "a=sigfig(1,2)"]:
            with self.subTest(source=source), self.assertRaises(GenerationError):
                execute(source)
        for source in ["a=1e9999999999", "a=" + "1"*257, "a=" + "1+"*1000 + "1"]:
            with self.assertRaises(GenerationError):
                execute(source)

    def test_choices_alias_semantics_and_ordered_selection(self):
        def values(name, args, kwargs=None):
            domain = _domain(name,args,kwargs or {})
            return [domain.at(i) for i in range(domain.size)]
        self.assertEqual(values("rand",[3]), [0,1,2])
        self.assertEqual(values("rand",[[4,7]]), [4,7])
        self.assertEqual(values("rand",[[]]), [[]])
        self.assertEqual(values("rand_with_step",[5,-5,-2]),[5,3,1,-1,-3,-5])
        self.assertEqual(values("rand_with_step",[sp.Rational(1,2),sp.Rational(3,2),sp.Rational(1,3)]),
                         [sp.Rational(1,2),sp.Rational(5,6),sp.Rational(7,6),sp.Rational(3,2)])
        self.assertEqual(values("rand_with_step",[-5,3,3]), [-5,-2,1])
        self.assertEqual(values("rand_range",[-5,3,3]), [-5,-2,1])
        self.assertEqual(values("rand_with_prohib",[-2,2,[0,sp.sqrt(2)]]),[-2,-1,1,2])
        self.assertEqual(values("sample",[[1,2,3],2]),[[1,2],[1,3],[2,1],[2,3],[3,1],[3,2]])
        self.assertEqual(values("rand_selection",[[1,1,2],2]),[[1,1],[1,2],[1,1],[1,2],[2,1],[2,1]])
        self.assertEqual(values("rand_selection_with_replacement",[[1,2],2]),[[1,1],[1,2],[2,1],[2,2]])
        self.assertEqual(values("shuffle",[[1,2]]), [[1,2],[2,1]])
        self.assertEqual(values("sample",[[],0]), [[]])

    def test_domain_cardinality_checked_before_materialization(self):
        for name,args in [("shuffle",[list(range(11))]), ("sample",[list(range(128)),100]),
                          ("pick",[0,100000000]), ("rand",[0])]:
            with self.subTest(name=name), self.assertRaises(GenerationError):
                _domain(name,args,{})
        domain = _domain("rand_selection", [[1,1,2],2], {})
        self.assertTrue(domain.contains([1,1]))
        self.assertFalse(domain.contains([2,2]))
        with self.assertRaisesRegex(GenerationError, "absent"):
            execute("a=pick([1,2],exclude=[2])", replay=[2])

    def test_foreign_math_module_in_cwd_cannot_shadow_worker_imports(self):
        import os
        import tempfile
        with tempfile.TemporaryDirectory(prefix="ctm foreign cwd ") as temporary:
            (pathlib.Path(temporary) / "math.py").write_text("raise RuntimeError('foreign math imported')")
            previous = os.getcwd()
            try:
                os.chdir(temporary)
                result = execute("a=sqrt(4)")
                self.assertEqual(result["variables"]["a"],2)
            finally:
                os.chdir(previous)

    def test_single_worker_startup_is_amortized_across_variables(self):
        import ctm_variants.generation as generation
        real = generation.subprocess.Popen
        processes = []
        def launch(*args, **kwargs):
            process = real(*args, **kwargs)
            processes.append(process)
            return process
        with patch.object(generation.subprocess,"Popen",launch):
            execute("\n".join("a{}={}".format(i,i) for i in range(20)))
        self.assertEqual(len(processes), 1)
        self.assertIsNotNone(processes[0].poll())


class SupervisorTests(unittest.TestCase):
    def test_timeout_kills_and_joins_child_and_reader(self):
        import ctm_variants.generation as generation
        real = generation.subprocess.Popen
        processes = []
        def launch(*args, **kwargs):
            process = real(*args, **kwargs)
            processes.append(process)
            return process
        before = {thread.ident for thread in threading.enumerate()}
        with patch.object(generation.subprocess,"Popen",launch):
            with self.assertRaisesRegex(GenerationError, "time budget"):
                execute("a=1", variable_timeout=0.001)
        self.assertTrue(processes and all(p.poll() is not None for p in processes))
        self.assertEqual({thread.ident for thread in threading.enumerate()},before)

    def test_absolute_budget_does_not_reset_at_statement_boundaries(self):
        with self.assertRaisesRegex(GenerationError,"time budget"):
            execute("a=1\nb=2\nc=3", variable_timeout=5, variant_timeout=0.001)

    def _worker_script(self, script, source, **timeouts):
        import ctm_variants.generation as generation
        real = generation.subprocess.Popen
        children = []
        def launch(*args, **kwargs):
            process = real([sys.executable, "-c", script], **kwargs)
            children.append(process)
            return process
        try:
            with patch.object(generation.subprocess, "Popen", launch):
                return execute(source, **timeouts)
        finally:
            self.assertTrue(children and all(p.poll() is not None for p in children))
            self.assertFalse(any(t.name == "ctm-generation-reader" for t in threading.enumerate()))

    def test_variable_timeout_after_real_progress_kills_worker(self):
        script = 'import time; print(\'{"statement":0,"line":1}\',flush=True); time.sleep(10)'
        with self.assertRaisesRegex(GenerationError, "line 1: generation time budget"):
            self._worker_script(script, "a=1", variable_timeout=0.5)

    def test_repeated_boundaries_cannot_extend_budget(self):
        script = 'import time; print(\'{"statement":0,"line":1}\',flush=True); print(\'{"statement":0,"line":1}\',flush=True); time.sleep(10)'
        with self.assertRaisesRegex(GenerationError, "unexpected worker statement boundary"):
            self._worker_script(script, "a=1\nb=2")

    def test_absolute_deadline_survives_valid_progress(self):
        script = ('import time; print(\'{"statement":0,"line":1}\',flush=True); time.sleep(.2); '
                  'print(\'{"statement":1,"line":2}\',flush=True); time.sleep(10)')
        with self.assertRaisesRegex(GenerationError, "time budget"):
            self._worker_script(script, "a=1\nb=2", variable_timeout=1, variant_timeout=.5)

    def test_malformed_worker_protocol_is_contextual_and_cleans_up(self):
        import json
        from ctm_checkers.variants import encode
        for message, expected in [
            ({"result":{"version":1,"value":["unknown"]}}, "unknown"),
            ({"result":encode([])}, "result shape"),
            ({"result":encode({"variables":[],"choices":[]})}, "result shape"),
            ({"error":1,"rejected":False}, "error shape")]:
            script = "import time; print(" + repr(json.dumps({"statement":0,"line":1})) + ",flush=True); print(" + repr(json.dumps(message)) + ",flush=True); time.sleep(10)"
            with self.subTest(message=message), self.assertRaisesRegex(GenerationError,"<variables>: <question>: line 1:.*"+expected):
                self._worker_script(script,"a=1")
        script = "import time; print(" + repr(json.dumps({"statement":0,"line":True})) + ",flush=True); time.sleep(10)"
        with self.assertRaisesRegex(GenerationError,"line 1: unexpected worker statement boundary"):
            self._worker_script(script,"a=1")

    def test_blocked_reader_queue_is_cancellable(self):
        import io
        import queue
        messages, stopped = queue.Queue(maxsize=1),threading.Event()
        messages.put("full")
        reader=threading.Thread(target=_read_lines,args=(io.BytesIO(b'{"statement":0,"line":1}\n'),messages,stopped))
        reader.start()
        stopped.set()
        reader.join(1)
        self.assertFalse(reader.is_alive())

    def test_oversized_output_line_rejected_before_json(self):
        import io
        import queue
        messages,stopped=queue.Queue(maxsize=1),threading.Event()
        reader=threading.Thread(target=_read_lines,args=(io.BytesIO(b"x"*(MAX_IPC+2)),messages,stopped))
        reader.start()
        message=messages.get(timeout=1)
        reader.join(1)
        self.assertIn("protocol_error",message)
        self.assertFalse(reader.is_alive())


if __name__ == "__main__":
    unittest.main()
