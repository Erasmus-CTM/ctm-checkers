"""The recording CLI never imports from a lesson directory or runs its code."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "authoring"))
from ctm_variants import history
from ctm_variants.model import VariantError, candidate, snapshot
from ctm_variants.review import request, document


class ReviewTests(unittest.TestCase):
    def test_recorded_decision_safe_cli_and_html_escape(self):
        with tempfile.TemporaryDirectory(prefix="lesson with spaces ") as folder:
            root = Path(folder)
            item = candidate("</script>", snapshot(["2"], {"answer": "2"}, {}), note="<b>unsafe</b>")
            value = history.append_proposals(history.empty("q"), [{"record": item, "tape": []}])
            token = history.write(root / "q.yml", value, base_hash=None)
            payload = {"version": 1, "action": "resolve", "projectRoot": folder,
                       "manifest": "q.yml", "label": "q", "records": [item]}
            response = request(payload)
            markup = document(response)
            self.assertIn("&lt;b&gt;unsafe&lt;/b&gt;", markup)
            self.assertNotIn('"</script>"', markup)
            self.assertIn('aria-live="polite"', markup)
            (root / "json.py").write_text("raise RuntimeError('foreign json import')", encoding="utf-8")
            (root / "math.py").write_text("raise RuntimeError('foreign math import')", encoding="utf-8")
            env = dict(os.environ, PYTHONPATH=folder)
            completed = subprocess.run([sys.executable, str(ROOT / "authoring" / "ctm-variants.py"), "--stdin"],
                input=json.dumps(payload), text=True, encoding="utf-8", capture_output=True,
                cwd=folder, env=env, timeout=10)
            self.assertEqual(completed.returncode, 0, completed.stderr)
            self.assertEqual(json.loads(completed.stdout)["baseHash"], token)
            payload.update(action="decide", baseHash=token,
                           decision={"id": item["id"], "hash": item["hash"], "status": "approved"})
            response = request(payload)
            self.assertEqual(response["manifest"]["decisions"][0]["n"], 1)
            with self.assertRaisesRegex(VariantError, "changed"):
                request(payload)

    def test_path_escape_and_missing_current_records_fail(self):
        with tempfile.TemporaryDirectory() as folder:
            payload = {"version": 1, "action": "resolve", "projectRoot": folder,
                       "manifest": "../outside.yml", "label": "q", "records": []}
            with self.assertRaisesRegex(VariantError, "inside"):
                request(payload)
            payload["manifest"] = "q.yml"
            del payload["records"]
            with self.assertRaisesRegex(VariantError, "current records"):
                request(payload)


if __name__ == "__main__":
    unittest.main()
