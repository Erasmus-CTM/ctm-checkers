"""Native distribution reproducibility and browser separation contracts."""
import importlib.util
import json
from pathlib import Path
import tempfile
import subprocess
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("build_authoring", ROOT / "tools" / "build_authoring.py")
producer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(producer)


class DistributionTests(unittest.TestCase):
    def test_produced_directory_executes_real_supervised_authoring(self):
        import sympy
        import mpmath
        with tempfile.TemporaryDirectory() as folder:
            output = Path(folder) / "native"
            producer.produce(output)
            roots = [str(output), str(ROOT / "src"), str(Path(sympy.__file__).resolve().parents[1]),
                     str(Path(mpmath.__file__).resolve().parents[1])]
            code = '''import json,sys
sys.path[:0]=json.loads(sys.argv[1])
from pathlib import Path
import sympy as sp
from ctm_variants.generation import execute
from ctm_variants.placeholders import render
from ctm_variants.validation import validate_math_candidate
from ctm_checkers.variants import question_context
value=execute("a=pick(1,3)",replay=[sp.Integer(2)])
assert render("{#a#}",variables=value["variables"])["text"]=="2"
result=validate_math_candidate({"field-labels":["answer"],"mode":"equivalent","question":"$__[2]$","tests":[]},
 Path.cwd(),context=question_context(["answer"],value["variables"],{"answer":sp.Integer(2)}),teacher_inputs={"answer":"2"})
assert result["passed"]
'''
            subprocess.run([sys.executable, "-I", "-B", "-c", code, json.dumps(roots)],
                           cwd=folder, check=True, timeout=30)
            self.assertEqual(producer.produce(output, check=True)["kind"], "native-authoring")

    def test_exact_source_tree_and_stale_extra_refusal(self):
        with tempfile.TemporaryDirectory() as folder:
            output = Path(folder) / "native"
            report = producer.produce(output)
            self.assertEqual(producer.produce(output, check=True), report)
            self.assertTrue((output / "ctm_variants" / "history.py").is_file())
            self.assertFalse(any(name.endswith((".whl", ".js")) for name in report["files"]))
            copied = output / "ctm_variants" / "history.py"
            copied.write_bytes(copied.read_bytes() + b"\n# corruption\n")
            with self.assertRaisesRegex(ValueError, "differs"):
                producer.produce(output, check=True)
            producer.produce(output)
            (output / "not-owned.txt").write_bytes(b"keep me")
            with self.assertRaisesRegex(ValueError, "unexpected"):
                producer.produce(output)
            self.assertEqual((output / "not-owned.txt").read_bytes(), b"keep me")


if __name__ == "__main__":
    unittest.main()
