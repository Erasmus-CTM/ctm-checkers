"""Trusted-base GitHub recording adapter. No checkout, imports or course execution.

Transport is injectable for deterministic safety tests. Artifact contents are
neutral JSON records, validated against an exact GitHub-observed run and head.
"""
import base64
import hashlib
import io
import json
import re
import zipfile

from ctm_variants.bot import plan
from ctm_variants.model import VariantError, canonical, digest, classify
from ctm_variants import history
from ctm_variants.review import apply_decisions
from ctm_variants.checklist import QUESTION, question_marker, render as render_checklist, _url
from ctm_variants.review import card_id

MAX_ARTIFACT = 16 * 1024 * 1024
SHA = re.compile(r"[0-9a-f]{40}")
LABEL = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}")


def _positive(value, what):
    if type(value) is not int or value <= 0:
        raise VariantError("invalid " + what)
    return value


def _artifact_bytes(data):
    if not isinstance(data, bytes) or len(data) > MAX_ARTIFACT:
        raise VariantError("artifact archive exceeds budget")
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            files = archive.infolist()
            if (len(files) != 1 or files[0].filename != "variants-records.json"
                    or files[0].file_size > MAX_ARTIFACT or files[0].flag_bits & 1):
                raise VariantError("artifact must contain one bounded neutral records file")
            with archive.open(files[0]) as source:
                content = source.read(MAX_ARTIFACT + 1)
            if len(content) > MAX_ARTIFACT:
                raise VariantError("neutral records file exceeds budget")
            return json.loads(content)
    except (ValueError, UnicodeError, zipfile.BadZipFile, RuntimeError) as error:
        raise VariantError("invalid neutral records artifact") from error


class Recorder:
    def __init__(self, transport, *, repository, bot_login, producer_paths, workflow="variants.yml"):
        if not isinstance(repository, str) or not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repository):
            raise VariantError("invalid repository")
        if not isinstance(bot_login, str) or not bot_login:
            raise VariantError("configured bot login is required")
        if workflow != "variants.yml":
            raise VariantError("only the explicit variants.yml check workflow is supported")
        required = {".github/workflows/variants.yml", ".github/scripts/ctm-variants-records.py", ".github/ctm-variants.json"}
        if (type(producer_paths) is not list or not required.issubset(producer_paths)
                or len(set(producer_paths)) != len(producer_paths)
                or any(not isinstance(path, str) or not re.fullmatch(r"[A-Za-z0-9_./-]+", path)
                       or path.startswith("/") or ".." in path.split("/") for path in producer_paths)):
            raise VariantError("trusted producer closure must include workflow and entrypoint")
        self.api, self.repo, self.bot, self.workflow = transport, repository, bot_login, workflow
        self.producer_paths = producer_paths
        self.prefix = "/repos/" + repository

    def get(self, path):
        return self.api.request("GET", self.prefix + path)

    def post(self, path, value):
        return self.api.request("POST", self.prefix + path, value)

    def _head(self, number, expected=None):
        pull = self.get("/pulls/" + str(number))
        if (pull.get("state") != "open" or pull.get("merged") is True
                or pull["head"]["repo"]["id"] != pull["base"]["repo"]["id"]
                or pull["base"]["repo"]["full_name"] != self.repo
                or pull["head"]["repo"]["full_name"] != self.repo):
            raise VariantError("recording requires an open same-repository PR")
        if pull["head"]["ref"] == pull["base"]["repo"]["default_branch"]:
            raise VariantError("recording cannot write the protected default branch")
        head = pull["head"]["sha"]
        if not isinstance(head, str) or not SHA.fullmatch(head) or (expected and head != expected):
            raise VariantError("PR head changed; regenerate before recording")
        # Slash-separated Git branch names are sent as JSON data, never shell.
        branch = pull["head"]["ref"]
        if not isinstance(branch, str) or not branch or any(c in branch for c in "\r\n?#"):
            raise VariantError("invalid PR branch")
        return pull

    def _producer(self, pull):
        """Every executable producer byte must come from reviewed base code.

        The path inventory is trusted-base configuration, never artifact data.
        It must enumerate the entrypoint and its complete imported/tool closure.
        A PR can change authored exercise data, not fabricate pass verdicts by
        replacing the workflow or any code that produces those verdicts.
        """
        from urllib.parse import quote
        branch = pull["base"]["repo"]["default_branch"]
        trusted = self.get("/git/ref/heads/" + quote(branch, safe="/"))["object"]["sha"]
        if not SHA.fullmatch(trusted):
            raise VariantError("invalid trusted producer base")
        for path in self.producer_paths:
            expected = self.get("/contents/" + path + "?ref=" + trusted)
            actual = self.get("/contents/" + path + "?ref=" + pull["head"]["sha"])
            if (not expected or not actual or expected.get("type") != "file" or actual.get("type") != "file"
                    or not expected.get("sha") or actual.get("sha") != expected["sha"]):
                raise VariantError("PR changed or omitted trusted records producer: " + path)
        return trusted

    def _download_records(self, run_id):
        artifacts = self.get("/actions/runs/" + str(run_id) + "/artifacts?per_page=100")["artifacts"]
        selected = [item for item in artifacts if item.get("name") == "ctm-variants-records" and not item.get("expired")]
        if len(selected) != 1:
            raise VariantError("expected one live records artifact")
        artifact = selected[0]
        if type(artifact.get("size_in_bytes")) is not int or not 0 < artifact["size_in_bytes"] <= MAX_ARTIFACT:
            raise VariantError("artifact size exceeds budget")
        data = self.api.download(self.prefix + "/actions/artifacts/" + str(_positive(artifact["id"], "artifact id")) + "/zip", MAX_ARTIFACT)
        if artifact.get("digest") != "sha256:" + hashlib.sha256(data).hexdigest():
            raise VariantError("artifact archive digest differs or is unavailable")
        return _artifact_bytes(data)

    def _records(self, pull, number, trusted_base, run_id=None):
        head = pull["head"]["sha"]
        runs = self.get("/actions/workflows/variants.yml/runs?head_sha=" + head + "&per_page=100")["workflow_runs"]
        runs = [run for run in runs if run.get("head_sha") == head and run.get("status") == "completed"
                and run.get("path") == ".github/workflows/variants.yml"
                and run.get("repository", {}).get("id") == pull["base"]["repo"]["id"]
                and ((run.get("event") == "pull_request" and any(pr.get("number") == number for pr in run.get("pull_requests", [])))
                     or (run.get("event") == "workflow_dispatch" and run.get("head_branch") == pull["head"]["ref"]
                         and run.get("head_repository", {}).get("id") == pull["head"]["repo"]["id"]))]
        if not runs:
            raise VariantError("no exact-head variants check artifact run")
        run = next((item for item in runs if item["id"] == run_id), None) if run_id is not None else max(runs, key=lambda item: _positive(item["id"], "workflow run"))
        if run is None:
            raise VariantError("requested preview run is not the exact current head run")
        run_id = run["id"]
        jobs = self.get("/actions/runs/" + str(run_id) + "/jobs?per_page=100")["jobs"]
        if not any(job.get("name") == "variants-records" and job.get("conclusion") == "success" for job in jobs):
            raise VariantError("exact-head records producer did not succeed")
        value = self._download_records(run_id)
        if (type(value) is not dict or set(value) != {"version", "headSha", "producerSha", "event", "expectedHead", "runId", "repositoryId", "pullRequest", "questions"}
                or type(value["version"]) is not int or value["version"] != 1 or value["headSha"] != head
                or value["producerSha"] != trusted_base or value["event"] != run["event"] or value["expectedHead"] != head
                or value["runId"] != run_id or value["repositoryId"] != pull["base"]["repo"]["id"]
                or value["pullRequest"] != number or type(value["questions"]) is not list):
            raise VariantError("artifact provenance does not match GitHub run/head/PR")
        return value

    def _questions(self, artifact):
        labels, paths = set(), set()
        for question in artifact["questions"]:
            if type(question) is not dict or set(question) != {"label", "path", "baseHash", "manifest", "records", "cards"}:
                raise VariantError("invalid question artifact schema")
            label, path = question["label"], question["path"]
            if (not isinstance(label, str) or not LABEL.fullmatch(label) or ".." in label
                    or path != "_variants/" + label + ".yml" or label in labels or path in paths):
                raise VariantError("question paths must be unique canonical variant manifests")
            labels.add(label); paths.add(path)
            value = history.validate(question["manifest"])
            if value["question"] != label:
                raise VariantError("question artifact manifest label differs")
            canonical(question["records"])
            classify(value["decisions"], question["records"])
            if type(question["cards"]) is not dict or set(question["cards"]) != {item["id"] for item in question["records"]}:
                raise VariantError("preview cards differ from resolved identities")
            for locator, url in question["cards"].items():
                if not _url(url).endswith("#" + card_id(locator)):
                    raise VariantError("preview card does not use the canonical review anchor")
        return artifact["questions"]

    def _value(self, question, head):
        label, path = question["label"], question["path"]
        current_file = self.get("/contents/" + path + "?ref=" + head)
        if current_file is None:
            old, actual = history.empty(label), None
        else:
            if current_file.get("encoding") != "base64" or current_file.get("type") != "file":
                raise VariantError("manifest must be an ordinary UTF-8 JSON/YAML file")
            try:
                old = history.validate(json.loads(base64.b64decode(current_file["content"], validate=False)))
            except (ValueError, UnicodeError) as error:
                raise VariantError("invalid current manifest JSON/YAML") from error
            actual = digest(old)
        value = history.validate(question["manifest"])
        if (old["question"] != label or value["question"] != label or actual != question["baseHash"]
                or value["decisions"] != old["decisions"] or value["events"] != old["events"]
                or value["proposals"][:len(old["proposals"])] != old["proposals"]):
            raise VariantError("artifact manifest lease/history differs from exact head")
        return value

    def _comment(self, number, comment_id):
        comment = self.get("/issues/comments/" + str(comment_id))
        if (comment.get("id") != comment_id or not isinstance(comment.get("updated_at"), str)
                or comment.get("user", {}).get("login") != self.bot
                or comment.get("issue_url") != "https://api.github.com" + self.prefix + "/issues/" + str(number)):
            raise VariantError("event must refer to this PR's own bot comment")
        return comment

    def record(self, *, pull_request, comment_id, sender):
        number = _positive(pull_request, "pull request")
        comment_id = _positive(comment_id, "comment id")
        if not isinstance(sender, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9-]{0,38}(?:\[bot\])?", sender):
            raise VariantError("invalid authenticated sender")
        permission = self.get("/collaborators/" + sender + "/permission").get("permission")
        if permission not in ("write", "maintain", "admin"):
            raise VariantError("variant decisions require repository write permission")
        pull = self._head(number)
        head, branch = pull["head"]["sha"], pull["head"]["ref"]
        trusted_base = self._producer(pull)
        comment = self._comment(number, comment_id)
        artifact = self._records(pull, number, trusted_base)
        questions = self._questions(artifact)
        matched = False
        changes, excluded = [], {}
        for question in questions:
            label, path = question["label"], question["path"]
            if QUESTION.findall(comment["body"]) != QUESTION.findall(question_marker(label)):
                continue
            matched = True
            # The artifact can append tested proposals, never rewrite prior
            # decisions/events or old proposals. Current bytes come from GitHub.
            value = self._value(question, head)
            selected = plan(comment["body"], label=label, records=question["records"], decisions=value["decisions"], retained=value["proposals"],
                sender=sender, permission=permission, comment_author=self.bot, bot_login=self.bot,
                head_repository_id=pull["head"]["repo"]["id"], base_repository_id=pull["base"]["repo"]["id"])
            excluded[label] = selected["notPassing"]
            if selected["decisions"]:
                updated = apply_decisions(value, question["records"], selected["decisions"])
                changes.append({"path": path, "mode": "100644", "type": "blob",
                                "content": json.dumps(updated, ensure_ascii=False, indent=2, allow_nan=False) + "\n"})
        if not matched:
            raise VariantError("bot comment is not in the verified current artifact")
        if not changes:
            return {"changed": False, "head": head, "notPassing": excluded}
        self._head(number, head)
        # Reverify producer provenance immediately before the atomic branch CAS.
        if self._producer(pull) != trusted_base:
            raise VariantError("trusted producer base moved; retry from fresh state")
        current_comment = self.get("/issues/comments/" + str(comment_id))
        if any(current_comment.get(key) != comment.get(key) for key in ("id", "user", "body", "updated_at", "issue_url")):
            raise VariantError("checklist changed before recording; retry from current intent")
        mutation = '''mutation($input: CreateCommitOnBranchInput!) {
          createCommitOnBranch(input: $input) { commit { oid } }
        }'''
        result = self.api.request("POST", "/graphql", {"query": mutation, "variables": {"input": {
            "branch": {"repositoryNameWithOwner": self.repo, "branchName": branch},
            "expectedHeadOid": head, "message": {"headline": "Record variant decisions"},
            "fileChanges": {"additions": [{"path": item["path"], "contents": base64.b64encode(item["content"].encode()).decode()}
                                         for item in changes]}}}})
        if result.get("errors"):
            raise VariantError("atomic expected-head recording was rejected")
        new_head = result["data"]["createCommitOnBranch"]["commit"]["oid"]
        if not isinstance(new_head, str) or not SHA.fullmatch(new_head):
            raise VariantError("invalid created commit identity")
        self._head(number, new_head)
        self.post("/actions/workflows/variants.yml/dispatches", {"ref": branch,
                  "inputs": {"expected_head": new_head, "pull_request": str(number)}})
        return {"changed": True, "head": new_head, "notPassing": excluded,
                "statusAttachment": "unverified: observe dispatched variants.yml on this exact head"}

    def _own_comments(self, number):
        comments = []
        for page in range(1, 6):
            batch = self.get("/issues/" + str(number) + "/comments?per_page=100&page=" + str(page))
            comments += [item for item in batch if item.get("user", {}).get("login") == self.bot]
            if len(batch) < 100:return comments
        raise VariantError("sticky comment scan exceeded its explicit page budget")

    def refresh_run(self, run_id):
        """Trusted workflow_run entry: derive PR selector from neutral data only.

        Deriving the selector is not authorization: refresh_preview independently
        proves the exact run/head/producer/repository/PR before any comment write.
        This supports dispatch runs with no GitHub pull_requests link.
        """
        run_id = _positive(run_id, "preview workflow run")
        value = self._download_records(run_id)
        return self.refresh_preview(_positive(value.get("pullRequest"), "artifact pull request"), run_id=run_id)

    def refresh_preview(self, number, *, run_id):
        """Write only authenticated sticky comments from an exact neutral run.

        No course code or HTML artifact is executed. The latest own-comment body
        is merged immediately before update. The inactive workflow serializes
        preview refreshes; GitHub has no atomic comment-body/head transaction.
        """
        number, run_id = _positive(number, "pull request"), _positive(run_id, "preview run")
        pull = self._head(number)
        head, trusted = pull["head"]["sha"], self._producer(pull)
        artifact = self._records(pull, number, trusted, run_id=run_id)
        questions = self._questions(artifact)
        # Validate every manifest before the first side effect; a broken later
        # question cannot cause a partially refreshed report to look complete.
        values = {question["label"]: self._value(question, head) for question in questions}
        comments = self._own_comments(number)
        result = {}
        for question in questions:
            label = question["label"]
            marker = QUESTION.findall(question_marker(label))
            existing = [item for item in comments if QUESTION.findall(item.get("body", "")) == marker]
            if len(existing) > 1:
                raise VariantError("duplicate own sticky comments for one question")
            previous = self._comment(number, _positive(existing[0]["id"], "sticky comment id")) if existing else None
            rendered = render_checklist(label=label, records=question["records"], decisions=values[label]["decisions"],
                cards=question["cards"], previous_body=previous["body"] if previous else None,
                comment_author=self.bot if previous else None, bot_login=self.bot if previous else None)
            body = rendered["body"] + "\n\nEvidence: head `" + head + "`; records run " + str(run_id) + "."
            self._head(number, head)
            if self._producer(pull) != trusted:
                raise VariantError("trusted preview producer base moved")
            if previous:
                latest = self._comment(number, previous["id"])
                if any(latest.get(key) != previous.get(key) for key in ("body", "updated_at")):
                    rendered = render_checklist(label=label, records=question["records"], decisions=values[label]["decisions"],
                        cards=question["cards"], previous_body=latest["body"], comment_author=self.bot, bot_login=self.bot)
                    body = rendered["body"] + "\n\nEvidence: head `" + head + "`; records run " + str(run_id) + "."
                if latest["body"] != body:
                    saved = self.api.request("PATCH", self.prefix + "/issues/comments/" + str(previous["id"]), {"body": body})
                else:saved = latest
            else:
                if any(QUESTION.findall(item.get("body", "")) == marker for item in self._own_comments(number)):
                    raise VariantError("sticky comment appeared concurrently; retry refresh")
                saved = self.post("/issues/" + str(number) + "/comments", {"body": body})
            if saved.get("user", {}).get("login") != self.bot or saved.get("body") != body:
                raise VariantError("sticky response does not confirm the configured bot body")
            result[label] = {"commentId": _positive(saved["id"], "saved sticky comment"),
                             "preserved": len(rendered["preserved"]), "notCarried": rendered["notCarried"]}
        return {"head": head, "runId": run_id, "questions": result,
                "statusAttachment": "unverified: observe actual exact-head required check"}


class GitHubTransport:
    """Bounded REST transport; redirects never carry the GitHub bearer token."""
    def __init__(self, token):
        if not isinstance(token, str) or not token:
            raise VariantError("GITHUB_TOKEN is required")
        self.token = token

    def _read(self, method, path, value, limit):
        import urllib.request
        import urllib.error
        from urllib.parse import urlsplit
        if not (path.startswith("/repos/") or path == "/graphql") or any(c in path for c in "\r\n"):
            raise VariantError("invalid GitHub API path")

        class Redirect(urllib.request.HTTPRedirectHandler):
            def redirect_request(self, request, response, code, message, headers, url):
                parsed = urlsplit(url)
                if (parsed.scheme != "https" or parsed.username or parsed.password or not parsed.hostname
                        or not (parsed.hostname == "api.github.com"
                                or parsed.hostname.endswith(".githubusercontent.com")
                                or parsed.hostname.endswith(".blob.core.windows.net"))):
                    raise VariantError("artifact redirect host is not allowed")
                redirected = super().redirect_request(request, response, code, message, headers, url)
                if redirected is not None:
                    redirected.remove_header("Authorization")
                return redirected

        body = None if value is None else json.dumps(value, allow_nan=False).encode()
        request = urllib.request.Request("https://api.github.com" + path, data=body, method=method,
            headers={"Authorization": "Bearer " + self.token, "Accept": "application/vnd.github+json",
                     "X-GitHub-Api-Version": "2022-11-28", "Content-Type": "application/json"})
        try:
            with urllib.request.build_opener(Redirect()).open(request, timeout=30) as response:
                data = response.read(limit + 1)
                if len(data) > limit:
                    raise VariantError("GitHub response exceeds budget")
                return data
        except urllib.error.HTTPError as error:
            if method == "GET" and error.code == 404:
                return None
            raise VariantError("GitHub API request failed with HTTP " + str(error.code)) from None

    def request(self, method, path, value=None):
        data = self._read(method, path, value, MAX_ARTIFACT)
        return None if not data else json.loads(data)

    def download(self, path, limit):
        data = self._read("GET", path, None, limit)
        if data is None:
            raise VariantError("records artifact is unavailable")
        return data


def event_request(event, repository):
    """Use authenticated event sender, never an input-provided approval identity."""
    if event.get("repository", {}).get("full_name") != repository:
        raise VariantError("event repository differs")
    if "comment" in event:
        if event.get("action") not in ("created", "edited") or "pull_request" not in event.get("issue", {}):
            raise VariantError("only PR comment creation/edit events are supported")
        number, comment = event["issue"]["number"], event["comment"]["id"]
    else:
        try:
            number, comment = (int(event["inputs"][key]) for key in ("pull_request", "comment_id"))
        except (KeyError, TypeError, ValueError) as error:
            raise VariantError("workflow dispatch requires PR and own comment IDs") from error
    return {"pull_request": _positive(number, "pull request"), "comment_id": _positive(comment, "comment id"),
            "sender": event.get("sender", {}).get("login")}


def main(argv=None):
    import argparse
    import os
    from pathlib import Path
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository", default=os.environ.get("GITHUB_REPOSITORY"))
    parser.add_argument("--event-file", type=Path, default=os.environ.get("GITHUB_EVENT_PATH"))
    parser.add_argument("--bot-login", default="github-actions[bot]")
    parser.add_argument("--producer-manifest", type=Path, required=True,
                        help="trusted-base JSON list enumerating the full records producer closure")
    parser.add_argument("--refresh-preview", action="store_true", help="trusted workflow_run preview reconciliation")
    args = parser.parse_args(argv)
    try:
        if args.event_file is None:
            raise VariantError("event file is required")
        if args.event_file.stat().st_size > 1024 * 1024:
            raise VariantError("event exceeds budget")
        event = json.loads(args.event_file.read_text(encoding="utf-8"))
        recorder = Recorder(GitHubTransport(os.environ.get("GITHUB_TOKEN")), repository=args.repository,
                            bot_login=args.bot_login, producer_paths=json.loads(args.producer_manifest.read_text(encoding="utf-8")))
        if args.refresh_preview:
            if event.get("repository", {}).get("full_name") != args.repository or event.get("action") != "completed":
                raise VariantError("preview refresh needs this repository's completed workflow_run event")
            result = recorder.refresh_run(event.get("workflow_run", {}).get("id"))
        else:
            result = recorder.record(**event_request(event, args.repository))
        print(json.dumps(result, ensure_ascii=True, allow_nan=False))
        return 0
    except Exception as error:
        # Keep credential values and downloaded archive bodies out of logs.
        print("variant GitHub recording failed: " + str(error), file=__import__("sys").stderr)
        return 1
