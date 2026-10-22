"""Component-neutral approved variant records. AGPL-3.0-or-later.

Native authoring code, deliberately outside the browser wheel. Components
supply canonical maths/teacher/grading data; this module does not grade answers.
"""
import copy
import hashlib
import json
import re


class VariantError(ValueError):
    pass


def canonical(value):
    def validate(item):
        if isinstance(item, dict):
            if any(not isinstance(key, str) for key in item):
                raise VariantError("variant object keys must be strings")
            for child in item.values():
                validate(child)
        elif isinstance(item, (list, tuple)):
            for child in item:
                validate(child)
        elif item is not None and not isinstance(item, (str, int, float, bool)):
            raise VariantError("variant data is not JSON: " + type(item).__name__)
    validate(value)
    try:
        return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"), allow_nan=False)
    except (ValueError, TypeError) as error:
        raise VariantError(str(error)) from error


def digest(value):
    return hashlib.sha256(canonical(value).encode("utf-8")).hexdigest()


def content_hash(value):
    """Hash ordered maths/teacher data and effective grading semantics."""
    return digest({key: value[key] for key in ("math", "teacher", "grading")})[:16]


def snapshot(math_segments, teacher, grading, variables=None):
    """Retain a verifiable approval payload independently of current source.

    Content excludes variable names/unused helpers; the full checksum also
    protects stored display values. Digests detect inconsistency, not authorship.
    """
    if not isinstance(math_segments, list) or any(not isinstance(value, str) for value in math_segments):
        raise VariantError("math segments must be an ordered list of canonical strings")
    if not isinstance(teacher, dict) or any(not isinstance(key, str) or not key or not isinstance(value, str)
                                          for key, value in teacher.items()):
        raise VariantError("teacher answers must be a named mapping of canonical strings")
    if not isinstance(grading, dict):
        raise VariantError("grading options must be a mapping")
    variables = {} if variables is None else variables
    if not isinstance(variables, dict) or any(not isinstance(key, str) or not isinstance(value, str)
                                            for key, value in variables.items()):
        raise VariantError("snapshot variable values must be canonical strings")
    value = {"math": list(math_segments), "teacher": list(map(list, teacher.items())),
             "grading": copy.deepcopy(grading), "variables": dict(variables)}
    value["checksum"] = digest(value)
    return value


def validate_snapshot(value):
    if not isinstance(value, dict) or set(value) != {"math", "teacher", "grading", "variables", "checksum"}:
        raise VariantError("invalid approved snapshot schema")
    checksum = value["checksum"]
    body = {key: item for key, item in value.items() if key != "checksum"}
    if not isinstance(checksum, str) or not re.fullmatch("[0-9a-f]{64}", checksum) or digest(body) != checksum:
        raise VariantError("approved snapshot checksum differs; regenerate it with the authoring tools")
    teacher = value["teacher"]
    if (not isinstance(teacher, list) or any(not isinstance(item, list) or len(item) != 2 for item in teacher)
            or any(not isinstance(item[0], str) for item in teacher)
            or len({item[0] for item in teacher}) != len(teacher)):
        raise VariantError("invalid or duplicate snapshot teacher fields")
    rebuilt = snapshot(value["math"], dict(teacher), value["grading"], value["variables"])
    if rebuilt != value:
        raise VariantError("approved snapshot is not canonical")
    return value


def candidate(locator, approved_snapshot, *, note="", data=None, tests=None):
    if not isinstance(locator, str) or not locator:
        raise VariantError("a candidate needs a nonempty locator")
    validate_snapshot(approved_snapshot)
    if not isinstance(note, str):
        raise VariantError("variant note must be text")
    data = {} if data is None else data
    tests = {} if tests is None else tests
    if not isinstance(data, dict) or not isinstance(tests, (dict, list)):
        raise VariantError("candidate data must be a mapping and tests a mapping or list")
    canonical(data)
    canonical(tests)
    return {"id": locator, "hash": content_hash(approved_snapshot), "note": note,
            "snapshot": copy.deepcopy(approved_snapshot), "data": copy.deepcopy(data),
            "tests": copy.deepcopy(tests)}


def validate_entries(entries):
    if not isinstance(entries, list):
        raise VariantError("manifest entries must be a list")
    numbers, ids = set(), set()
    allowed = {"n", "id", "hash", "status", "note", "snapshot", "by", "date", "reason"}
    for entry in entries:
        if not isinstance(entry, dict) or set(entry) - allowed:
            raise VariantError("unknown manifest entry keys")
        if not {"n", "id", "hash", "status", "snapshot"}.issubset(entry):
            raise VariantError("manifest entry is missing identity, status or snapshot")
        n, locator = entry["n"], entry["id"]
        if type(n) is not int or n <= 0 or n in numbers:
            raise VariantError("variant numbers must be unique positive integers")
        if not isinstance(locator, str) or not locator or locator in ids:
            raise VariantError("variant locators must be unique nonempty strings")
        numbers.add(n)
        ids.add(locator)
        if entry["status"] not in ("approved", "rejected"):
            raise VariantError("manifest status must be approved or rejected")
        for name in ("note", "by", "date", "reason"):
            if name in entry and not isinstance(entry[name], str):
                raise VariantError(name + " must be text")
        validate_snapshot(entry["snapshot"])
        if entry["hash"] != content_hash(entry["snapshot"]):
            raise VariantError("variant hash differs from the approved snapshot")
    return entries


def _candidates(items):
    if not isinstance(items, list):
        raise VariantError("candidates must be a list")
    by_id, by_hash = {}, {}
    for item in items:
        if not isinstance(item, dict) or not isinstance(item.get("id"), str) or not item["id"]:
            raise VariantError("invalid candidate identity")
        if item["id"] in by_id:
            raise VariantError("duplicate candidate locator: " + item["id"])
        validate_snapshot(item.get("snapshot"))
        if item.get("hash") != content_hash(item["snapshot"]):
            raise VariantError("candidate hash differs from its content")
        by_id[item["id"]] = item
        by_hash.setdefault(item["hash"], []).append(item)
    return by_id, by_hash


def classify(entries, candidates, *, hash_first=False):
    """Reserve exact identities, then move globally unambiguous content.

    Math retains a changed existing locator. The hash_first option models
    content-first classification only; STACK decision reconciliation is not
    implemented by this checkpoint (see the implementation notes).
    """
    validate_entries(entries)
    by_id, by_hash = _candidates(candidates)
    old_hashes = {}
    for entry in entries:
        old_hashes.setdefault(entry["hash"], []).append(entry)
    matches, used = {}, set()
    for entry in entries:
        exact = by_id.get(entry["id"])
        if exact is not None and exact["hash"] == entry["hash"]:
            matches[entry["n"]] = ("current", exact)
            used.add(exact["id"])
    if not hash_first:
        for entry in entries:
            exact = by_id.get(entry["id"])
            if entry["n"] not in matches and exact is not None and exact["id"] not in used:
                matches[entry["n"]] = ("changed", exact)
                used.add(exact["id"])
    for entry in entries:
        if entry["n"] in matches:
            continue
        same = by_hash.get(entry["hash"], [])
        if len(same) == 1 and len(old_hashes[entry["hash"]]) == 1 and same[0]["id"] not in used:
            matches[entry["n"]] = ("moved", same[0])
            used.add(same[0]["id"])
    for entry in entries:
        if entry["n"] in matches:
            continue
        exact = by_id.get(entry["id"])
        if exact is not None and exact["id"] not in used:
            matches[entry["n"]] = ("changed", exact)
            used.add(exact["id"])
        else:
            matches[entry["n"]] = ("gone", None)
    results = [{"state": matches[entry["n"]][0], "entry": copy.deepcopy(entry),
                "candidate": copy.deepcopy(matches[entry["n"]][1])} for entry in entries]
    return {"entries": results, "new": [copy.deepcopy(item) for item in candidates if item["id"] not in used]}


def decide(entries, candidates, locator, status, *, by="", date="", reason=""):
    """Update one math decision from all candidates; never recycle a number."""
    validate_entries(entries)
    by_id, unused = _candidates(candidates)
    if locator not in by_id:
        raise VariantError("decision locator is absent from the candidate set")
    if status not in ("approved", "rejected"):
        raise VariantError("decision must be approved or rejected")
    for value in (by, date, reason):
        if not isinstance(value, str):
            raise VariantError("decision metadata must be text")
    item = by_id[locator]
    previous = next((entry for entry in entries if entry["id"] == locator), None)
    if previous is None:
        rows = classify(entries, candidates)["entries"]
        previous = next((row["entry"] for row in rows
                         if row["state"] == "moved" and row["candidate"]["id"] == locator), None)
    number = previous["n"] if previous else max([entry["n"] for entry in entries] + [0]) + 1
    updated = {"n": number, "id": locator, "hash": item["hash"], "status": status,
               "snapshot": copy.deepcopy(item["snapshot"]), "note": item.get("note", ""), "by": by, "date": date}
    if reason:
        updated["reason"] = reason
    result = [copy.deepcopy(entry) for entry in entries if previous is None or entry["n"] != previous["n"]]
    result.append(updated)
    result.sort(key=lambda entry: entry["n"])
    validate_entries(result)
    return result
