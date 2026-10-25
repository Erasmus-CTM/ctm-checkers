"""Unprivileged trusted-code records/preview producer and publication gate.

Authored questions are data until the supervised component resolver is called.
This module is never invoked by the privileged recording/sticky-write job.
"""
import copy
import hashlib
import json
import os
from pathlib import Path
import re
import runpy
import subprocess
import sys

from ctm_variants import history, preview_assets
from ctm_variants.batches import _record
from ctm_variants.checklist import _url
from ctm_variants.github_bot import LABEL, SHA, MAX_ARTIFACT, GitHubTransport, teacher_displays
from ctm_variants.model import VariantError, digest, classify
from ctm_variants.review import card_id, document

NEUTRAL = ("id", "hash", "note", "snapshot", "data", "tests")
ARTIFACT_BUDGET = MAX_ARTIFACT - 65536  # Reserve envelope/ZIP framing bytes.
REVIEW_BUDGET = 32 * 1024 * 1024


def inside(root, name):
    root = Path(root).resolve()
    if not isinstance(name, str) or Path(name).is_absolute() or ".." in Path(name).parts:
        raise VariantError("producer path must stay inside its checkout")
    path = root / name
    if not path.resolve().is_relative_to(root) or any(item.is_symlink() for item in [path, *path.parents] if item != root and item.is_relative_to(root)):
        raise VariantError("producer paths must not escape through symlinks")
    return path


def _ast(text):
    quarto = os.environ.get("CTM_VARIANTS_QUARTO", "quarto")
    result = subprocess.run([quarto, "pandoc", "--from", "commonmark_x", "--to", "json"],
                            input=text, capture_output=True, text=True, timeout=15)
    if result.returncode or len(result.stdout.encode()) > 8 * 1024 * 1024:
        raise VariantError("native producer Pandoc extraction failed or exceeded its budget")
    return json.loads(result.stdout)


def discover(project, patterns, parse_source, *, ast=_ast):
    """Discover every native variant block under reviewed source globs.

    The trusted inventory defines coverage, not a frozen list of question names.
    New files/questions under those globs are discovered without editing CI code.
    """
    if type(patterns) is not list or not patterns or any(not isinstance(p, str) or p.startswith("/") or ".." in p.split("/") for p in patterns):
        raise VariantError("reviewed sourceGlobs are required")
    project = Path(project).resolve()
    paths = sorted({path.relative_to(project).as_posix() for pattern in patterns for path in project.glob(pattern)
                    if path.is_file() and not any(part in ("_extensions", ".git", ".quarto", "_site", "_variants-review") for part in path.relative_to(project).parts)})
    if len(paths) > 1000:
        raise VariantError("source discovery file budget exceeded")
    found, labels = [], set()
    def walk(node, file):
        if isinstance(node, dict):
            if node.get("t") == "CodeBlock":
                classes, raw = node["c"][0][1], node["c"][1]
                stack = any(name.strip('{}.') == 'stack-question' for name in classes)
                if "{math-exercise}" in classes or stack:
                    options, question = parse_source(raw)
                    if not stack and "variables" not in options and options.get("pool") not in (True, "true"):
                        return
                    label = options.get("label")
                    if not isinstance(label, str) or not LABEL.fullmatch(label) or ".." in label or label in labels:
                        raise VariantError(file + ": native variant questions require distinct safe labels")
                    labels.add(label)
                    found.append({"file": file, "label": label, "source": raw.rstrip("\r\n"),
                                  "options": options, "question": question})
                    if stack:
                        found[-1]['component'] = 'ctm-stack'
                    if len(found) > 250:
                        raise VariantError("source discovery question budget exceeded")
            else:
                for child in node.values():walk(child, file)
        elif isinstance(node, list):
            for child in node:walk(child, file)
    for name in paths:
        path = inside(project, name)
        if path.stat().st_size > 1024 * 1024:
            raise VariantError(name + ": source exceeds 1 MiB")
        walk(ast(path.read_text(encoding="utf-8")).get("blocks", []), name)
    return found


def produce(project, context, config, *, definitions, resolve, github_context=None, generate_more=None, workflow_enabled=False, export_previews=None):
    """Resolve through trusted supervised component code, then emit neutral data.

    resolve is injectable for source-only tests; the CLI supplies the installed
    trusted component wrapper. It is not configurable from authored JSON/code.
    """
    project = Path(project).resolve()
    if github_context is not None and (type(github_context) is not dict or set(github_context) != {"repository", "branch", "head"}
                                       or github_context["head"] != context["headSha"]):
        raise VariantError("producer editor context must name the verified source head")
    if generate_more is not None:
        if (context["event"] != "workflow_dispatch" or not isinstance(generate_more, str)
                or not LABEL.fullmatch(generate_more) or ".." in generate_more
                or sum(item["label"] == generate_more and ('variables' in item['options'] or item.get('component') == 'ctm-stack') for item in definitions) != 1):
            raise VariantError("generate_more must name one discovered native variable question in an exact-head dispatch")
    preview = config["previewBase"].replace("{pullRequest}", str(context["pullRequest"])).replace("{headSha}", context["headSha"])
    _url(preview)
    if "{" in preview or "}" in preview:
        raise VariantError("previewBase has an unknown placeholder")
    questions, pages, seen, pool_checks = [], {}, set(), []
    artifact_bytes = len(json.dumps({**context, "version": 1, "questions": []}, ensure_ascii=False, indent=2).encode())
    review_bytes = 0
    bundle_bytes = 0
    for definition in definitions:
        label, file = definition["label"], definition["file"]
        if not LABEL.fullmatch(label) or ".." in label or label in seen:
            raise VariantError("producer requires distinct safe question labels")
        seen.add(label)
        source_path, source_bytes = None, None
        if export_previews is not None:
            source_path = inside(project, file)
            source_bytes = source_path.read_bytes()
            if len(source_bytes) > 1024 * 1024:
                raise VariantError("student preview source exceeds 1 MiB")
        if definition["options"].get("pool") in (True, "true") and "variables" not in definition["options"]:
            receipt = resolve(dict(copy.deepcopy(definition), version=1, projectRoot=str(project),
                                   sourceFile=file, action="check-pool"))
            if (type(receipt) is not dict or receipt.get("version") != 1 or receipt.get("kind") != "pool"
                    or receipt.get("label") != label or receipt.get("passed") is not True
                    or type(receipt.get("count")) is not int or receipt["count"] < 1
                    or type(receipt.get("tasks")) is not list or len(receipt["tasks"]) != receipt["count"]):
                raise VariantError("handwritten pool requires successful supervised teacher/authored checks")
            for number, task in enumerate(receipt["tasks"], 1):
                if (type(task) is not dict or set(task) != {"n", "teacher", "tests"} or task["n"] != number
                        or type(task["teacher"]) is not dict or task["teacher"].get("passed") is not True
                        or type(task["tests"]) is not list
                        or any(type(test) is not dict or test.get("passed") is not True for test in task["tests"])):
                    raise VariantError("handwritten pool requires passing teacher/authored task receipts")
            pool_checks.append(receipt)
            if len(json.dumps(pool_checks, ensure_ascii=False, allow_nan=False).encode()) > ARTIFACT_BUDGET:
                raise VariantError("aggregate handwritten pool receipt budget exceeded")
            continue
        path = "_variants/" + label + ".yml"
        manifest_path = inside(project, path)
        old, lease = history.load(manifest_path, label)
        payload = dict(copy.deepcopy(definition), version=1, projectRoot=str(project), sourceFile=file,
                       manifest=path, approval="required", renderMode="review", action="resolve-more" if label == generate_more else "resolve")
        response = resolve(payload)
        if source_path is not None and source_path.read_bytes() != source_bytes:
            raise VariantError("source changed during records resolution")
        # Resolution is read-only; never publish a response that changed history
        # under the producer or rewrote existing decisions/proposals in memory.
        if history.load(manifest_path, label) != (old, lease) or response.get("baseHash") != lease:
            raise VariantError("read-only records resolution changed its manifest lease")
        value = history.validate(response["manifest"])
        if (value["question"] != label or value["decisions"] != old["decisions"] or value["events"] != old["events"]
                or value["proposals"][:len(old["proposals"])] != old["proposals"]):
            raise VariantError("resolved records rewrote retained history")
        records = [_record({key: item[key] for key in NEUTRAL}) for item in response["records"]]
        if len({item["id"] for item in records}) != len(records):
            raise VariantError("resolved records have duplicate identities")
        for record in records:
            if type(record["tests"]) is not dict or record["tests"].get("passed") is not True:
                raise VariantError("records producer requires actual passing teacher/authored tests")
            if not any(p["record"]["id"] == record["id"] and p["record"]["hash"] == record["hash"] for p in value["proposals"]):
                raise VariantError("resolved candidate lacks retained proposal/tape")
        cards = {record["id"]: preview.rstrip("/") + "/" + label + ".html#" + card_id(record["id"]) for record in records}
        question = {"label": label, "path": path, "baseHash": lease, "manifest": value, "records": records, "cards": cards}
        supplied_displays = {item["id"]: item["teacherDisplay"] for item in response["records"]
                             if "teacherDisplay" in item}
        if supplied_displays:
            question["teacherDisplays"] = teacher_displays({**question, "teacherDisplays": supplied_displays})
        generated = {}
        if export_previews is not None:
            rendered = export_previews(copy.deepcopy(payload), copy.deepcopy(response))
            if (type(rendered) is not dict or set(rendered) != {"studentPreviews", "files"}
                    or type(rendered["files"]) is not dict):
                raise VariantError("student exporter requires routes and generated files")
            if history.load(manifest_path, label) != (old, lease) or source_path.read_bytes() != source_bytes:
                raise VariantError("student export changed source or manifest bytes")
            question["studentPreviews"] = rendered["studentPreviews"]
            question["previewSource"] = {"file": file, "sha256": hashlib.sha256(source_bytes).hexdigest()}
            generated = rendered["files"]
            for name, content in generated.items():
                preview_assets.asset_path(name, label)
                if name == label + ".html" or type(content) is not bytes or len(content) > preview_assets.MAX_FILE_BYTES:
                    raise VariantError("student exporter must return only bounded generated static assets")
            if len(generated) > preview_assets.MAX_FILES or sum(map(len, generated.values())) > preview_assets.MAX_BYTES:
                raise VariantError("generated student assets exceed budget")
        page = document({**response, "records": records}, teacher_displays=question.get("teacherDisplays", {}),
                        student_previews=question.get("studentPreviews", {}),
                        github_context={**github_context, "path": path} if github_context else None,
                        workflow_context={"pullRequest": context["pullRequest"], "label": label} if github_context and workflow_enabled else None)
        review_bytes += len(page.encode())
        if review_bytes > REVIEW_BUDGET:
            raise VariantError("aggregate review HTML budget exceeded")
        if export_previews is not None:
            question["previewFiles"] = {name: preview_assets.receipt(content) for name, content in generated.items()}
            question["previewFiles"][label + ".html"] = preview_assets.receipt(page.encode())
            preview_assets.inventory([*questions, question])
        bundle_bytes += len(page.encode()) + sum(map(len, generated.values()))
        if bundle_bytes > preview_assets.MAX_BYTES:
            raise VariantError("aggregate review asset budget exceeded")
        encoded = json.dumps(question, ensure_ascii=False, indent=2, allow_nan=False).encode()
        artifact_bytes += len(encoded) + encoded.count(b"\n") * 4 + 6
        if artifact_bytes > ARTIFACT_BUDGET:
            raise VariantError("aggregate neutral records artifact budget exceeded")
        questions.append(question)
        pages["review/" + label + ".html"] = page
        pages.update({"review/" + name: content for name, content in generated.items()})
    envelope = {**context, "version": 1, "questions": questions}
    if len(json.dumps(envelope, ensure_ascii=False, indent=2).encode()) > ARTIFACT_BUDGET:
        raise VariantError("aggregate neutral records artifact budget exceeded")
    if pool_checks:
        pages["pool-checks.json"] = json.dumps({"version": 1, "headSha": context["headSha"], "pools": pool_checks},
                                               ensure_ascii=False, indent=2, allow_nan=False) + "\n"
    return envelope, pages


def render_previews(project, trusted, wrapper, payload, response):
    """Run only the trusted sibling exporter in an isolated unprivileged child."""
    import tempfile
    exporter = inside(trusted, str(Path(wrapper).with_name("variants-review.py").relative_to(trusted)))
    module = runpy.run_path(str(exporter), run_name="ctm_trusted_student_exporter")
    with tempfile.TemporaryDirectory(prefix="ctm-g1-student-export-") as folder:
        root = Path(folder)
        response_path, output = root / "response.json", root / "site"
        encoded = json.dumps(response, ensure_ascii=True, allow_nan=False).encode()
        if len(encoded) > MAX_ARTIFACT:
            raise VariantError("student export response exceeds budget")
        response_path.write_bytes(encoded)
        command = [sys.executable, "-I", str(exporter), "--project", str(project),
                   "--file", payload["file"], "--label", payload["label"],
                   "--export-student-previews", str(output), "--response-json", str(response_path),
                   "--url-prefix", "students/" + payload["label"]]
        raw = module["Review"].render_command(command, trusted, dict(os.environ),
                timeout=1800, output_limit=MAX_ARTIFACT, return_output=True)
        result = json.loads(raw)
        if type(result) is not dict or set(result) != {"studentPreviews"}:
            raise VariantError("trusted student exporter returned invalid route metadata")
        if not output.is_dir() or output.is_symlink():
            raise VariantError("student exporter produced no ordinary generated output")
        files, total = {}, 0
        for path in sorted(output.rglob("*")):
            if path.is_symlink():
                raise VariantError("student exporter output cannot contain symbolic links")
            if path.is_dir():
                continue
            if not path.is_file():
                raise VariantError("student exporter output must contain ordinary generated files")
            name = "students/" + payload["label"] + "/" + path.relative_to(output).as_posix()
            preview_assets.asset_path(name, payload["label"])
            if path.stat().st_size > preview_assets.MAX_FILE_BYTES:
                raise VariantError("generated student file exceeds budget")
            with path.open("rb") as source:
                content = source.read(preview_assets.MAX_FILE_BYTES + 1)
            total += len(content)
            if len(content) > preview_assets.MAX_FILE_BYTES or total > preview_assets.MAX_BYTES or len(files) >= preview_assets.MAX_FILES:
                raise VariantError("generated student output exceeds aggregate budget")
            files[name] = content
        return {"studentPreviews": result["studentPreviews"], "files": files}


def check(envelope):
    """Run strict CI approval checks after the successful records artifact.

    Keeping this separate lets zero-approved questions produce review evidence
    while the required check still fails; no authored code is executed here.
    """
    warnings = []
    for question in envelope["questions"]:
        records = question["records"]
        value = history.validate(question["manifest"])
        stale = [row for row in classify(value["decisions"], records)["entries"]
                 if row["entry"]["status"] == "approved" and row["state"] in ("changed", "gone")]
        if stale:
            details = "; ".join("Variant {} ({}) is {}".format(row["entry"]["n"],
                row["entry"]["id"], row["state"]) for row in stale)
            raise VariantError(question["label"] + ": strict variants check needs review: " + details)
        target = records[0].get("data", {}).get("options", {}).get("variants", 25) if records else 25
        if isinstance(target, str) and target.isdecimal():target = int(target)
        selected = history.publication(value["decisions"], records, approval="required", render_mode="publish", target=target)
        warnings += [question["label"] + ": " + warning for warning in selected["warnings"]]
    return warnings


def verify_context(api, *, repository, event_name, event, run_id, source_head, producer_head, editor_out=None, workflow_out=None):
    """Authenticate run selectors against GitHub; strings never become commands."""
    if (not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repository or "")
            or event.get("repository", {}).get("full_name") != repository
            or event_name not in ("pull_request", "workflow_dispatch")
            or not SHA.fullmatch(source_head) or not SHA.fullmatch(producer_head)):
        raise VariantError("invalid records producer context")
    try:
        number = event["pull_request"]["number"] if event_name == "pull_request" else int(event["inputs"]["pull_request"])
        run_id = int(run_id)
    except (KeyError, ValueError, TypeError) as error:raise VariantError("records producer needs PR/run metadata") from error
    if type(number) is not int or number <= 0 or run_id <= 0:
        raise VariantError("records producer needs positive PR/run metadata")
    pull = api.request("GET", "/repos/" + repository + "/pulls/" + str(number))
    if (pull.get("state") != "open" or pull["head"]["sha"] != source_head
            or pull["base"]["repo"]["full_name"] != repository
            or (event_name == "workflow_dispatch" and pull["head"]["repo"]["id"] != pull["base"]["repo"]["id"])):
        raise VariantError("producer checkout is not the current permitted PR head")
    expected = event["pull_request"]["head"]["sha"] if event_name == "pull_request" else event["inputs"].get("expected_head")
    if expected != source_head:
        raise VariantError("dispatch/event expected head differs from checked out source")
    from urllib.parse import quote
    trusted = api.request("GET", "/repos/" + repository + "/git/ref/heads/" + quote(pull["base"]["repo"]["default_branch"], safe="/"))
    if trusted["object"]["sha"] != producer_head:
        raise VariantError("producer checkout differs from the API-observed trusted default SHA")
    if editor_out is not None:
        if type(editor_out) is not dict or not isinstance(pull["head"].get("ref"), str):
            raise VariantError("GitHub editor metadata requires an observed PR branch")
        editor_out.clear()
        editor_out.update(repository=pull["head"]["repo"]["full_name"], branch=pull["head"]["ref"], head=source_head)
    if workflow_out is not None:
        if type(workflow_out) is not dict:
            raise VariantError("workflow metadata requires a dictionary")
        workflow_out.clear()
        if pull["head"]["repo"]["id"] == pull["base"]["repo"]["id"]:
            workflow_out.update(repository=repository, branch=pull["head"]["ref"])
    return {"headSha": source_head, "producerSha": producer_head, "event": event_name, "expectedHead": expected,
            "runId": run_id, "repositoryId": pull["base"]["repo"]["id"], "pullRequest": number}


def main(argv=None):
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", type=Path, required=True)
    parser.add_argument("--trusted", type=Path, required=True)
    parser.add_argument("--config", default=".github/ctm-variants.json")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args(argv)
    from ctm_variants.project_report import write_step_summary
    summary_written = False
    try:
        project, trusted = args.project.resolve(), args.trusted.resolve()
        if project.is_relative_to(trusted) or trusted.is_relative_to(project):
            raise VariantError("trusted producer and authored checkouts must be separate siblings")
        if not Path(__file__).resolve().is_relative_to(trusted):
            raise VariantError("producer executable must come from the trusted checkout")
        git_head = lambda root: subprocess.check_output(["git", "-C", str(root), "rev-parse", "HEAD"], text=True, timeout=10).strip()
        event = json.loads(Path(os.environ["GITHUB_EVENT_PATH"]).read_text())
        editor_context, workflow_context = {}, {}
        context = verify_context(GitHubTransport(os.environ.get("GITHUB_TOKEN")), repository=os.environ.get("GITHUB_REPOSITORY"),
            event_name=os.environ.get("GITHUB_EVENT_NAME"), event=event, run_id=os.environ.get("GITHUB_RUN_ID"),
            source_head=git_head(project), producer_head=git_head(trusted), editor_out=editor_context, workflow_out=workflow_context)
        artifact = args.output / "variants-records.json"
        if args.check:
            value = json.loads(artifact.read_text(encoding="utf-8"))
            if any(value.get(key) != item for key, item in context.items()):
                raise VariantError("required check artifact context differs from current run/head")
            try:
                warnings = check(value)
            except Exception:
                write_step_summary(value, state="Approval check failed; review changed, gone or unapproved variants")
                summary_written = True
                raise
            write_step_summary(value, state="Approval check passed")
            summary_written = True
            print(json.dumps({"passed": True, "warnings": warnings}))
            return 0
        config = json.loads(inside(trusted, args.config).read_text(encoding="utf-8"))
        if type(config) is not dict or set(config) != {"version", "sourceGlobs", "wrapper", "previewBase"} or config["version"] != 1:
            raise VariantError("invalid trusted producer configuration")
        wrapper = inside(trusted, config["wrapper"])
        module = runpy.run_path(str(wrapper), run_name="ctm_trusted_native_producer")
        module["install_imports"]()
        definitions = discover(project, config["sourceGlobs"], module["parse_source"])
        def resolve(payload):
            code, stdout, stderr = module["supervised"](json.dumps(payload, ensure_ascii=True).encode())
            if code:raise VariantError("supervised native records resolution failed: " + stderr.decode(errors="replace")[:4096])
            return json.loads(stdout)
        generate_more = event.get("inputs", {}).get("generate_more", "") if context["event"] == "workflow_dispatch" else ""
        envelope, pages = produce(project, context, config, definitions=definitions, resolve=resolve,
                                  github_context=editor_context, generate_more=generate_more or None, workflow_enabled=bool(workflow_context),
                                  export_previews=lambda payload, response: render_previews(project, trusted, wrapper, payload, response))
        if args.output.resolve().is_relative_to(project) or args.output.resolve().is_relative_to(trusted):
            raise VariantError("records output must be outside both source checkouts")
        args.output.mkdir(parents=True, exist_ok=True)
        if any(args.output.iterdir()):raise VariantError("records output must start empty")
        artifact.write_text(json.dumps(envelope, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
        for name, content in pages.items():
            path = args.output / name;path.parent.mkdir(parents=True, exist_ok=True);path.write_bytes(content) if isinstance(content, bytes) else path.write_text(content, encoding="utf-8")
        write_step_summary(envelope)
        summary_written = True
        print(json.dumps({"questions": len(envelope["questions"]), "head": context["headSha"], "recordsArtifact": str(artifact)}))
        return 0
    except Exception as error:
        if not summary_written:
            try:
                write_step_summary(state="Records producer or approval check failed; see the job log")
            except (OSError, ValueError):
                pass  # Keep the original failure when the runner summary is unavailable.
        print("variant records producer failed: " + str(error), file=sys.stderr)
        return 1
