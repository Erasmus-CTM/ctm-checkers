"""Fake GitHub only: no comments, commits, dispatches or network are sent."""
import base64
import copy
import hashlib
import io
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch
import urllib.request
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "authoring"))
from ctm_variants import history
from ctm_variants.bot import token
from ctm_variants.checklist import question_marker
from ctm_variants.review import card_id
from ctm_variants.github_bot import Recorder, GitHubTransport, event_request, _artifact_bytes
from ctm_variants.model import VariantError, candidate, digest, snapshot

HEAD, NEXT, BASE = "a" * 40, "b" * 40, "c" * 40
PATHS = [".github/workflows/variants.yml", ".github/scripts/ctm-variants-records.py", ".github/ctm-variants.json", "native/native.json", "native/helper.py", "pins.json"]


class FakeGitHub:
    def __init__(self):
        self.calls, self.mutations = [], []
        self.head, self.fork, self.permission, self.author = HEAD, False, "write", "ctm[bot]"
        self.stale_at, self.head_reads, self.race_at_cas = None, 0, False
        self.producer_changed, self.run_event, self.job, self.digest_bad = None, "pull_request", "success", False
        self.run_branch = 'feature/variants'
        self.comment_reads, self.change_comment = 0, False
        row = candidate("value:$(never-execute)", snapshot(["2"], {"answer": "2"}, {}), tests={"passed": True})
        self.old = history.empty("q")
        self.value = history.append_proposals(self.old, [{"record": row, "tape": []}])
        self.body = question_marker('q') + "\n- [x] answer " + token("q", row["id"], row["hash"])
        self.envelope = {"version": 1, "headSha": HEAD, "producerSha": BASE, "event": "pull_request", "expectedHead": HEAD, "runId": 20, "repositoryId": 1,
                         "pullRequest": 7, "questions": [{"label": "q", "path": "_variants/q.yml",
                             "baseHash": digest(self.old), "manifest": self.value, "records": [row],
                             "cards": {row['id']:'https://preview.test/review/q.html#'+card_id(row['id'])}}]}

    def archive(self):
        output = io.BytesIO()
        with zipfile.ZipFile(output, "w") as zipped:
            zipped.writestr("variants-records.json", json.dumps(self.envelope))
        return output.getvalue()

    def download(self, path, limit):
        self.calls.append(("DOWNLOAD", path, None))
        assert path == "/repos/org/course/actions/artifacts/30/zip"
        assert len(self.archive()) <= limit
        return self.archive()

    def request(self, method, path, value=None):
        self.calls.append((method, path, value))
        if method != "GET":
            if path == "/graphql":
                data = value["variables"]["input"]
                assert "createCommitOnBranch" in value["query"]
                assert data["expectedHeadOid"] == HEAD
                assert data["branch"] == {"repositoryNameWithOwner": "org/course", "branchName": "feature/variants"}
                if self.race_at_cas:
                    self.head = "d" * 40
                if self.head != data["expectedHeadOid"]:
                    return {"errors": [{"message": "expected head differs"}]}
                self.mutations.append((method, path, value));self.head = NEXT
                return {"data": {"createCommitOnBranch": {"commit": {"oid": NEXT}}}}
            assert path == "/repos/org/course/actions/workflows/variants.yml/dispatches"
            self.mutations.append((method, path, value));return None
        suffix = path.removeprefix("/repos/org/course")
        if suffix.startswith("/collaborators/"):
            return {"permission": self.permission}
        if suffix == "/pulls/7":
            self.head_reads += 1
            if self.stale_at == self.head_reads:self.head = "d" * 40
            repo = {"id": 1, "full_name": "org/course", "default_branch": "main"}
            return {"state": "open", "merged": False, "head": {"sha": self.head, "ref": "feature/variants", "repo": dict(repo, id=2 if self.fork else 1)}, "base": {"sha": BASE, "repo": repo}}
        if suffix == "/git/ref/heads/main":return {"object": {"sha": BASE}}
        if suffix.startswith("/contents/") and "_variants/q.yml" not in suffix:
            file, ref = suffix[len("/contents/"):].split("?ref=")
            return {"type": "file", "sha": ("different" if file == self.producer_changed and ref == HEAD else "trusted-blob")}
        if suffix == "/issues/comments/11":
            self.comment_reads += 1
            return {"id": 11, "updated_at": "2026-10-23T00:00:00Z", "user": {"login": self.author}, "body": self.body if not self.change_comment or self.comment_reads == 1 else self.body.replace('[x]', '[ ]'), "issue_url": "https://api.github.com/repos/org/course/issues/7"}
        if suffix.startswith("/actions/workflows/variants.yml/runs?"):
            return {"workflow_runs": [{"id": 20, "head_sha": HEAD, "head_branch": self.run_branch, "head_repository": {"id": 1}, "event": self.run_event, "status": "completed", "path": ".github/workflows/variants.yml", "repository": {"id": 1}, "pull_requests": [{"number": 7}] if self.run_event == 'pull_request' else []}]}
        if suffix == "/actions/runs/20/jobs?per_page=100":return {"jobs": [{"name": "variants-records", "conclusion": self.job}]}
        if suffix == "/actions/runs/20/artifacts?per_page=100":
            return {"artifacts": [{"id": 30, "name": "ctm-variants-records", "expired": False, "size_in_bytes": len(self.archive()), "digest": "wrong" if self.digest_bad else "sha256:" + hashlib.sha256(self.archive()).hexdigest()}]}
        if suffix == "/contents/_variants/q.yml?ref=" + HEAD:
            return {"type": "file", "encoding": "base64", "content": base64.b64encode(json.dumps(self.old).encode()).decode()}
        raise AssertionError((method, path, value))


class GitHubBotTests(unittest.TestCase):
    def run_bot(self, api):
        return Recorder(api, repository="org/course", bot_login="ctm[bot]", producer_paths=PATHS).record(pull_request=7, comment_id=11, sender="teacher")

    def test_records_only_yaml_through_atomic_expected_head_and_dispatches_exact_head(self):
        api = FakeGitHub();result = self.run_bot(api)
        self.assertEqual(result["head"], NEXT)
        self.assertIn("unverified", result["statusAttachment"])
        self.assertEqual(len(api.mutations), 2)
        input = api.mutations[0][2]["variables"]["input"]
        self.assertEqual(set(input["fileChanges"]), {"additions"})
        addition, = input["fileChanges"]["additions"]
        self.assertEqual(addition["path"], "_variants/q.yml")
        updated = json.loads(base64.b64decode(addition["contents"]))
        self.assertEqual(updated["decisions"][0]["by"], "teacher")
        self.assertEqual(updated["decisions"][0]["id"], "value:$(never-execute)")
        self.assertEqual(api.mutations[1][2], {"ref": "feature/variants", "inputs": {"expected_head": NEXT, "pull_request": "7"}})
        self.assertGreaterEqual(api.head_reads, 3)
        for path in PATHS:
            self.assertGreaterEqual(sum(call[1] == "/repos/org/course/contents/" + path + "?ref=" + BASE for call in api.calls), 2)

    def test_permission_fork_comment_producer_and_run_faults_make_no_writes(self):
        faults = [("permission", "read"), ("fork", True), ("author", "forged"), ("producer_changed", "native/helper.py"),
                  ("producer_changed", ".github/workflows/variants.yml"), ("run_event", "pull_request_target"),
                  ("job", "failure"), ("digest_bad", True), ("change_comment", True)]
        for field, value in faults:
            with self.subTest(field=field, value=value):
                api = FakeGitHub();setattr(api, field, value)
                with self.assertRaises(VariantError):self.run_bot(api)
                self.assertEqual(api.mutations, [])

    def test_artifact_provenance_paths_and_leases_fail_closed(self):
        for mutate in [lambda x:x.update(headSha=NEXT), lambda x:x.update(producerSha=NEXT), lambda x:x.update(repositoryId=9),
                       lambda x:x.update(runId=21), lambda x:x.update(expectedHead=NEXT), lambda x:x.update(event='workflow_dispatch'),
                       lambda x:x["questions"][0].update(path=".github/workflows/attack.yml"),
                       lambda x:x["questions"][0].update(baseHash="stale")]:
            api = FakeGitHub();mutate(api.envelope)
            with self.assertRaises(VariantError):self.run_bot(api)
            self.assertEqual(api.mutations, [])
        api = FakeGitHub()
        api.envelope["questions"][0]["manifest"] = history.decision(api.value, api.envelope["questions"][0]["records"], "value:$(never-execute)", "approved")
        with self.assertRaisesRegex(VariantError, "history"):self.run_bot(api)
        self.assertEqual(api.mutations, [])

    def test_explicit_dispatch_artifact_can_feed_next_approval_without_pr_run_link(self):
        api=FakeGitHub();api.run_event='workflow_dispatch';api.envelope['event']='workflow_dispatch'
        self.assertTrue(self.run_bot(api)['changed'])
        for changed in ['branch','event','expectedHead']:
            api=FakeGitHub();api.run_event='workflow_dispatch';api.envelope['event']='workflow_dispatch'
            if changed=='branch':api.run_branch='other-branch'
            elif changed=='event':api.envelope['event']='pull_request'
            else:api.envelope['expectedHead']=NEXT
            with self.subTest(changed=changed),self.assertRaises(VariantError):self.run_bot(api)
            self.assertEqual(api.mutations,[])

    def test_head_changes_before_record_or_inside_atomic_cas_never_overwrite(self):
        for before, inside in [(2, False), (None, True)]:
            api=FakeGitHub();api.stale_at=before;api.race_at_cas=inside
            with self.assertRaises(VariantError):self.run_bot(api)
            self.assertEqual(api.mutations, [])
            self.assertFalse(any(call[1].endswith('/dispatches') for call in api.calls))

    def test_zip_payload_is_not_extracted_and_event_sender_is_not_an_input(self):
        for name in ("../variants-records.json", "source.py"):
            output=io.BytesIO()
            with zipfile.ZipFile(output,'w') as archive:archive.writestr(name,'{}')
            with self.assertRaises(VariantError):_artifact_bytes(output.getvalue())
        event={"repository":{"full_name":"org/course"},"sender":{"login":"actual"},"inputs":{"pull_request":"7","comment_id":"11","sender":"spoof"}}
        self.assertEqual(event_request(event,"org/course")["sender"],"actual")
        with self.assertRaises(VariantError):event_request(event,"other/course")
        with self.assertRaises(VariantError):Recorder(FakeGitHub(),repository="org/course",bot_login="ctm[bot]",producer_paths=[])

    def test_transport_redirects_strip_bearer_and_reject_other_hosts_without_network(self):
        handlers=[]
        class Response:
            def __enter__(self):return self
            def __exit__(self,*args):return False
            def read(self,limit):return b'{}'
        class Opener:
            def open(self,request,timeout):
                self.request=request
                return Response()
        opener=Opener()
        with patch('urllib.request.build_opener',side_effect=lambda handler:(handlers.append(handler) or opener)):
            self.assertEqual(GitHubTransport('private-token').request('GET','/repos/org/course'),{})
        self.assertEqual(opener.request.get_header('Authorization'),'Bearer private-token')
        redirected=handlers[0].redirect_request(opener.request,None,302,'Found',{},'https://safe.blob.core.windows.net/archive')
        self.assertIsNone(redirected.get_header('Authorization'))
        for target in ['https://attacker.invalid/archive','http://safe.blob.core.windows.net/archive','https://user@safe.blob.core.windows.net/archive']:
            with self.subTest(target=target),self.assertRaises(VariantError):
                handlers[0].redirect_request(opener.request,None,302,'Found',{},target)

    def test_inactive_workflow_uses_trusted_code_and_serial_event_file_adapter(self):
        root=Path(__file__).resolve().parents[1]
        text=(root/'templates/variants-decide.yml').read_text()
        self.assertIn('cancel-in-progress: false',text)
        self.assertIn('github.event.repository.default_branch',text)
        self.assertIn('persist-credentials: false',text)
        self.assertIn('GITHUB_EVENT_PATH:',text)
        self.assertNotIn('github.event.comment.body',text)
        self.assertNotIn('pull_request_target',text)
        self.assertNotIn('uses: actions/checkout@v',text)


if __name__ == "__main__":unittest.main()
