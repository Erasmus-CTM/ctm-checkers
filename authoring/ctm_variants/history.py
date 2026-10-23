"""Versioned review history and optimistic atomic writes. AGPL-3.0-or-later."""
import copy
import json
import os
from pathlib import Path
import tempfile

from ctm_variants.model import VariantError, _candidates, canonical, decide, digest, validate_entries


def empty(question):
    if not isinstance(question, str) or not question:
        raise VariantError("history requires a question label")
    return {"version": 1, "question": question, "proposals": [], "decisions": [], "events": []}


def validate(value):
    if (type(value) is not dict or set(value) != {"version", "question", "proposals", "decisions", "events"}
            or type(value["version"]) is not int or value["version"] != 1):
        raise VariantError("invalid review history/version")
    empty(value["question"])
    validate_entries(value["decisions"])
    if type(value["proposals"]) is not list or type(value["events"]) is not list:
        raise VariantError("review history proposals/events must be lists")
    identities = set()
    for proposal in value["proposals"]:
        if type(proposal) is not dict or set(proposal) != {"record", "tape"}:
            raise VariantError("invalid proposal history record")
        record = proposal["record"]
        _candidates([record])
        identity = (record["id"], record["hash"])
        if identity in identities:
            raise VariantError("duplicate proposal version")
        identities.add(identity)
        canonical(proposal["tape"])
    replayed = []
    for event in value["events"]:
        if type(event) is not dict or set(event) != {"before", "after"}:
            raise VariantError("invalid decision event")
        validate_entries(event["before"])
        validate_entries(event["after"])
        if event["before"] != replayed:
            raise VariantError("decision history chain differs")
        replayed = event["after"]
    if replayed != value["decisions"]:
        raise VariantError("decision history does not match current decisions")
    canonical(value)
    return value


def append_proposals(value, proposals):
    result = copy.deepcopy(validate(value))
    known = {(p["record"]["id"], p["record"]["hash"]): p for p in result["proposals"]}
    for proposal in proposals:
        record = proposal["record"]
        key = (record["id"], record["hash"])
        if key in known:
            if known[key] != proposal:
                raise VariantError("existing proposal version was modified")
            continue
        result["proposals"].append(copy.deepcopy(proposal))
        known[key] = proposal
    return validate(result)


def decision(value, candidates, locator, status, **metadata):
    result = copy.deepcopy(validate(value))
    selected = next((item for item in candidates if item.get("id") == locator), None)
    if selected is None or not any(p["record"] == selected for p in result["proposals"]):
        raise VariantError("a decision requires its retained proposal and replay tape")
    updated = decide(result["decisions"], candidates, locator, status, **metadata)
    if updated != result["decisions"]:
        result["events"].append({"before": copy.deepcopy(result["decisions"]), "after": copy.deepcopy(updated)})
        result["decisions"] = updated
    return validate(result)


def publication(entries, candidates, *, approval="required", render_mode="publish", target=25):
    """Select current decisions only; changed/rejected records never deploy."""
    from ctm_variants.model import classify
    if approval not in ("required", "optional") or render_mode not in ("publish", "preview", "review"):
        raise VariantError("invalid approval/render mode")
    if type(target) is not int or target < 1:
        raise VariantError("variant target must be a positive integer")
    classified = classify(entries, candidates)
    approved, rejected = set(), set()
    for row in classified["entries"]:
        if row["candidate"] is not None and row["entry"]["status"] == "rejected":
            rejected.add(row["candidate"]["id"])
        if row["candidate"] is not None and row["state"] in ("current", "moved"):
            (approved if row["entry"]["status"] == "approved" else rejected).add(row["candidate"]["id"])
    if render_mode == "publish" and approval == "required" and not approved:
        raise VariantError("required variants publishing needs at least one current approved variant")
    selected = [item["id"] for item in candidates if item["id"] in approved or
                ((approval == "optional" or render_mode != "publish") and item["id"] not in rejected)]
    warnings = []
    if len(approved) < target:
        warnings.append("{} current approved variants; target {}".format(len(approved), target))
    if any(key not in approved for key in selected):
        warnings.append("unapproved variants are visible in explicit optional/review mode")
    return {"ids": selected, "warnings": warnings}


def load(path, question):
    path = Path(path)
    if not path.exists():
        return empty(question), None
    value = validate(json.loads(path.read_text(encoding="utf-8")))
    if value["question"] != question:
        raise VariantError("manifest belongs to another question")
    return value, digest(value)


def write(path, value, *, base_hash):
    """Reject concurrent/stale writes, then replace within the same directory."""
    validate(value)
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    lock = path.with_name(path.name + ".lock")
    try:
        handle = lock.open("x", encoding="utf-8")
    except FileExistsError as error:
        raise VariantError("manifest is locked by another writer; retry after it finishes") from error
    temporary = None
    try:
        with handle:
            current, actual = load(path, value["question"])
            if actual != base_hash:
                raise VariantError("manifest changed; reload before saving decisions")
            for field in ("proposals", "events"):
                if value[field][:len(current[field])] != current[field]:
                    raise VariantError("existing {} history cannot be rewritten".format(field))
            with tempfile.NamedTemporaryFile(mode="wb", prefix=path.name + ".", suffix=".tmp",
                                             dir=str(path.parent), delete=False) as output:
                temporary = Path(output.name)
                output.write((json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n").encode("utf-8"))
                output.flush()
                os.fsync(output.fileno())
            os.replace(str(temporary), str(path))
        return digest(value)
    finally:
        if temporary is not None and temporary.exists():
            temporary.unlink()
        lock.unlink()
