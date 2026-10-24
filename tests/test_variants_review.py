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
from ctm_variants.review import request, document, apply_decisions, card_id


class ReviewTests(unittest.TestCase):
    def test_gone_approved_snapshot_is_readonly_with_retirement_only(self):
        old = candidate("gone", snapshot(["2"], {"answer": "2"}, {}), note="old")
        value = history.append_proposals(history.empty("q"), [{"record": old, "tape": []}])
        value = history.decision(value, [old], old["id"], "approved")
        page = document({"manifest": value, "baseHash": "lease", "records": []})
        self.assertIn('Retained approved snapshot — Variant 1', page)
        self.assertIn('Retire missing Variant 1', page)
        self.assertNotIn('data-status="approved"', page)
        self.assertIn('Reason for retiring Variant 1', page)
        self.assertIn('required', page)
        value["proposals"] = []
        repair = document({"manifest": value, "baseHash": "lease", "records": []})
        self.assertIn('Retained proposal is missing', repair)
        self.assertNotIn('Retire missing Variant 1', repair)

    def test_github_manifest_export_requires_explicit_safe_context(self):
        item = candidate("a", snapshot(["2"], {"answer": "2"}, {}))
        response = {"manifest": history.empty("q"), "baseHash": None, "records": [item]}
        context = {"repository": "course/lesson", "branch": "feature/variants", "path": "_variants/q.yml", "head": "a" * 40}
        page = document(response, github_context=context)
        self.assertIn('Copy file', page)
        self.assertIn('Open in GitHub editor', page)
        self.assertIn('manifestJSON', page)
        self.assertIn('https://github.com/', page)
        self.assertNotIn('Copy file', document(response))
        for field, invalid in (("repository", "evil.test/a/b"), ("repository", None), ("branch", "bad\nbranch"), ("path", "../q.yml"), ("head", "moving-branch")):
            with self.assertRaises(VariantError):
                document(response, github_context=dict(context, **{field: invalid}))

    def test_component_student_previews_are_named_local_and_lazy(self):
        item = candidate("a", snapshot(["2"], {"answer": "2"}, {}))
        response = {"manifest": history.empty("q"), "baseHash": "lease", "records": [item]}
        url = "/" + "t" * 43 + "/previews/a/nb/index.html"
        page = document(response, student_previews={"a": [{"language": "nb", "url": url}]})
        self.assertIn('data-src="' + url + '"', page)
        self.assertIn('title="Student view — nb"', page)
        self.assertNotRegex(page, r'<iframe[^>]*\ssrc=')
        self.assertIn('Open Student view — nb', page)
        self.assertIn('Resolved Markdown text preview', page)
        for invalid in ("javascript:alert(1)", "https://example.com/", url.replace('/nb/', '/de/')):
            with self.assertRaises(VariantError):
                document(response, student_previews={"a": [{"language": "nb", "url": invalid}]})

    def test_connected_mode_is_explicit_and_token_route_only(self):
        item = candidate("a", snapshot(["2"], {"answer": "2"}, {}), tests={"passed": True})
        response = {"manifest": history.empty("q"), "baseHash": "lease", "records": [item]}
        self.assertNotIn("const endpoint=", document(response))
        endpoint = "/" + "a" * 43 + "/"
        page = document(response, connected_endpoint=endpoint)
        self.assertIn("Connected local review", page)
        self.assertIn("operation({baseHash:base.baseHash,decisions:[...pending.values()]},false)", page)
        self.assertIn("Save not confirmed:", page)
        self.assertIn("Rebuild the review before retrying", page)
        for invalid in ("https://example.com/", "/save", "/../", endpoint + "?x=1"):
            with self.assertRaises(VariantError):
                document(response, connected_endpoint=invalid)

    def test_connected_generation_action_uses_original_lease_and_localized_labels(self):
        response = {"manifest": history.empty("q"), "baseHash": "original", "records": []}
        endpoint = "/" + "a" * 43 + "/"
        for language, label in (("en", "Generate 25 more"), ("de", "25 weitere generieren"), ("nb", "Generer 25 til")):
            page = document(response, connected_endpoint=endpoint, language=language)
            self.assertIn(label, page)
            self.assertIn("action:'generate25more',baseHash:base.baseHash", page)
            self.assertIn("generate.type='button'", page)
        self.assertNotIn("generate.id='generate-more'", document(response))
        with self.assertRaises(VariantError):
            document(response, language="unknown")

    def test_component_can_decide_reconciled_changed_source_without_intermediate_write(self):
        first = candidate("a", snapshot(["2"], {"answer": "2"}, {}))
        value = history.append_proposals(history.empty("q"), [{"record": first, "tape": []}])
        value = history.decision(value, [first], "a", "approved")
        changed = candidate("a", snapshot(["3"], {"answer": "3"}, {}))
        reconciled = history.append_proposals(value, [{"record": changed, "tape": []}])
        decided = apply_decisions(reconciled, [changed], [{"id": "a", "hash": changed["hash"], "status": "approved"}])
        self.assertEqual(decided["decisions"][0]["n"], 1)
        self.assertEqual(decided["decisions"][0]["hash"], changed["hash"])
        self.assertEqual(reconciled["decisions"][0]["hash"], first["hash"])
        self.assertEqual(decided["proposals"], reconciled["proposals"])

    def test_bulk_decisions_are_atomic_leased_and_retain_individual_events(self):
        with tempfile.TemporaryDirectory() as folder:
            items = [candidate(str(n), snapshot([str(n)], {"answer": str(n)}, {})) for n in (2, 3)]
            value = history.append_proposals(history.empty("q"), [{"record": item, "tape": []} for item in items])
            path = Path(folder) / "q.yml"
            token = history.write(path, value, base_hash=None)
            payload = {"version": 1, "action": "decide-many", "projectRoot": folder,
                       "manifest": "q.yml", "label": "q", "records": items, "baseHash": token,
                       "decisions": [{"id": item["id"], "hash": item["hash"], "status": "approved"} for item in items]}
            payload["decisions"][1]["hash"] = "stale"
            with self.assertRaisesRegex(VariantError, "id/hash"):
                request(payload)
            self.assertEqual(history.load(path, "q"), (value, token))
            payload["decisions"][1]["hash"] = items[1]["hash"]
            response = request(payload)
            self.assertEqual([row["n"] for row in response["manifest"]["decisions"]], [1, 2])
            self.assertEqual(len(response["manifest"]["events"]), 2)
            with self.assertRaisesRegex(VariantError, "changed"):
                request(payload)
            payload.update(baseHash=response["baseHash"], decisions=[payload["decisions"][0]] * 2)
            with self.assertRaisesRegex(VariantError, "distinct"):
                request(payload)
            self.assertEqual(history.load(path, "q")[1], response["baseHash"])

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
            self.assertIn('id="' + card_id(item["id"]) + '"', markup)
            self.assertRegex(card_id(item["id"]), r"^variant-[0-9a-f]{64}$")
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
