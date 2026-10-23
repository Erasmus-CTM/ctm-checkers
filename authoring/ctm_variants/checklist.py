"""Pure per-question sticky checklist rendering; no GitHub IO or source execution.

The caller authenticates the existing comment and exact-head records artifact.
Refreshing expands old bulk consent into exact individual identities, so source
growth cannot silently approve candidates that were not in the checked batch.
"""
import base64
import html
import re
import unicodedata
from urllib.parse import urlsplit

from ctm_variants.bot import TOKEN, CHECKED, _decode, token, bulk_token
from ctm_variants.model import VariantError, canonical, classify

QUESTION = re.compile(r"<!-- ctm-question:([A-Za-z0-9_-]+) -->")


def _flat(value):
    value = str(value)
    return " ".join("".join(" " if unicodedata.category(c).startswith("C") else c for c in value).split())


def _inline(value):
    # Escape markup before adding trusted checklist syntax. No authored newline,
    # task box, HTML comment or backtick can introduce another actionable row.
    value = html.escape(_flat(value), quote=True)
    return re.sub(r"([\\`*_{}\[\]()#+.!|~\-])", r"\\\1", value)


def _math(value):
    value = html.escape(_flat(value), quote=True).replace("`", "&#96;").replace("$", "&#36;")
    return "$`" + value + "`$"


def _url(value):
    if not isinstance(value, str) or not value or any(c.isspace() or ord(c) < 32 for c in value):
        raise VariantError("preview card needs a nonempty safe URL")
    parsed = urlsplit(value)
    if (parsed.scheme not in ("http", "https") or not parsed.hostname or parsed.username or parsed.password
            or any(c in value for c in '<>"`\\()')):
        raise VariantError("preview card must be an ordinary HTTP(S) URL")
    return value


def question_marker(label):
    if not isinstance(label, str) or not label:
        raise VariantError("checklist needs a question label")
    encoded = base64.urlsafe_b64encode(canonical({"label": label}).encode()).decode().rstrip("=")
    return "<!-- ctm-question:" + encoded + " -->"


def _pending(label, records, decisions):
    classified = classify(decisions, records)
    prior = {row["candidate"]["id"]: row for row in classified["entries"] if row["candidate"] is not None}
    pending, recorded = [], []
    for index, record in enumerate(records):
        row = prior.get(record["id"])
        if row and row["state"] in ("current", "moved"):
            recorded.append({"id": record["id"], "entry": row["entry"]})
            continue
        number = row["entry"]["n"] if row else None
        pending.append({"record": record, "n": number, "state": "changed" if row else "new",
                        "before": row["entry"]["snapshot"] if row else None,
                        "display": "Variant " + str(number) if number is not None else "New " + str(index + 1),
                        "identity": {"label": label, "id": record["id"], "hash": record["hash"], "n": number}})
    return pending, recorded


def _values(current, before=None):
    if before is None:
        return "; ".join(_inline(key) + "=" + _math(value) for key, value in current.items())
    values = []
    for key in dict.fromkeys([*before, *current]):
        old = _math(before[key]) if key in before else "absent"
        new = _math(current[key]) if key in current else "absent"
        values.append(_inline(key) + "=" + (new + " (unchanged)" if key in before and key in current and before[key] == current[key]
                                             else old + " → " + new))
    return "; ".join(values)


def reconcile(previous_body, *, label, records, decisions, comment_author, bot_login):
    """Retain unrecorded exact identities from an authenticated own comment.

    Stale/gone/recorded ticks are reported, never migrated by index or hash alone.
    The caller must compare the comment snapshot again before any GitHub update.
    """
    if not bot_login or comment_author != bot_login:
        raise VariantError("only an authenticated own bot comment can preserve ticks")
    if not isinstance(previous_body, str) or len(previous_body.encode()) > 262144:
        raise VariantError("previous checklist exceeds comment budget")
    if QUESTION.findall(previous_body) != QUESTION.findall(question_marker(label)):
        raise VariantError("sticky checklist question marker differs")
    pending, recorded = _pending(label, records, decisions)
    available = {item["record"]["id"]: item for item in pending}
    recorded_ids = {locator for item in recorded for locator in (item["id"], item["entry"]["id"])}
    preserved, not_carried, seen = [], [], {}
    for line in previous_body.splitlines():
        if not CHECKED.match(line):
            continue
        matches = TOKEN.findall(line)
        if len(matches) != 1:
            raise VariantError("checked row needs exactly one identity token")
        decoded = _decode(matches[0])
        for identity in decoded.get("all", [decoded]):
            if identity["label"] != label:
                raise VariantError("checked row belongs to another question")
            if identity["id"] in seen:
                if seen[identity["id"]] != identity:
                    raise VariantError("conflicting old checklist identities")
                continue
            seen[identity["id"]] = identity
            current = available.get(identity["id"])
            if current and current["identity"] == identity:
                tests = current["record"].get("tests")
                if type(tests) is dict and tests.get("passed") is True:
                    preserved.append(identity)
                else:
                    not_carried.append({"id": identity["id"], "hash": identity["hash"], "reason": "not passing"})
            else:
                not_carried.append({"id": identity["id"], "hash": identity["hash"],
                                    "reason": "recorded" if identity["id"] in recorded_ids else "changed or absent"})
    return {"preserved": preserved, "notCarried": not_carried}


def render(*, label, records, decisions, cards, previous_body=None, comment_author=None, bot_login=None):
    """Return one sticky body and reconciliation report, without posting it.

    cards maps each pending id to the producer's actual preview-card URL.
    Recorded current decisions are summarized; they have no actionable checkbox.
    """
    pending, recorded = _pending(label, records, decisions)
    carried = {"preserved": [], "notCarried": []} if previous_body is None else reconcile(
        previous_body, label=label, records=records, decisions=decisions,
        comment_author=comment_author, bot_login=bot_login)
    checked = {item["id"] for item in carried["preserved"]}
    lines = [question_marker(label), "### Variants: " + _inline(label),
             "{} need a decision · {} recorded current decisions. Recorded decisions have no checkboxes.".format(len(pending), len(recorded))]
    if pending:
        # Always uncheck the fresh bulk row. Prior bulk consent is represented by
        # preserved individual checks, never extended to newly generated rows.
        lines += ["", "- [ ] Approve all passing variants of this question " + bulk_token(label, [item["record"] for item in pending], decisions)]
    for item in pending:
        record = item["record"]
        tests = record.get("tests")
        verdict = "tests pass" if type(tests) is dict and tests.get("passed") is True else "tests fail" if type(tests) is dict and tests.get("passed") is False else "tests unverified"
        facts = [item["display"] + " · " + item["state"], _inline(record.get("note", ""))]
        variables = record["snapshot"]["variables"]
        before = item["before"]
        if variables or (before and before["variables"]):
            facts.append("variables " + _values(variables, before["variables"] if before else None))
        facts.append("teacher " + _values(dict(record["snapshot"]["teacher"]), dict(before["teacher"]) if before else None))
        facts += [verdict, "[Preview card](" + _url(cards.get(record["id"])) + ")"]
        lines.append("- [{}] {} {}".format("x" if record["id"] in checked else " ", " · ".join(facts),
                      token(label, record["id"], record["hash"], item["n"])))
    if carried["notCarried"]:
        lines += ["", "Not carried forward: " + "; ".join(_inline(item["id"]) + " (" + item["reason"] + ")" for item in carried["notCarried"]) + "."]
    lines += ["", "Ticks are pending decisions until recorded. Reject on the review page; rejection commands are not wired here."]
    body = "\n".join(lines)
    if len(body.encode()) > 60000:
        raise VariantError("question checklist exceeds comment budget; use the review page")
    return {"body": body, "preserved": carried["preserved"], "notCarried": carried["notCarried"], "recorded": len(recorded)}
