"""Native retained-tape reconciliation and tested Generate 25 more composition.

Components own extraction, canonical content identity and the resolver callback.
No browser or component syntax is inferred here. AGPL-3.0-or-later.
"""
import copy
import math
import time

from ctm_variants import history
from ctm_variants.batches import _record, collect_tested_batch
from ctm_variants.generation import execute, Rejected, ReplayUnavailable
from ctm_variants.model import VariantError, canonical, classify
from ctm_variants.streaming import choice_stream


def _deadline(seconds):
    if isinstance(seconds, bool) or not isinstance(seconds, (int, float)) or not math.isfinite(seconds) or seconds <= 0:
        raise VariantError("orchestration timeout must be positive finite seconds")
    return time.monotonic() + seconds


def _remaining(deadline):
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise VariantError("variant orchestration time budget exceeded")
    return remaining


def _retain(value, record, tape):
    """Keep original records when semantic content is unchanged by source edits."""
    for proposal in value["proposals"]:
        previous = proposal["record"]
        if previous["id"] == record["id"] and previous["hash"] == record["hash"]:
            if (proposal["tape"] != tape or any(previous["snapshot"][key] != record["snapshot"][key]
                    for key in ("math", "teacher", "grading"))):
                raise VariantError("retained proposal identity differs from its tape/content")
            return value
    return history.append_proposals(value, [{"record": record, "tape": tape}])


def reconcile(value, source, resolve, *, max_records, variables=None,
              file="<question>", label="<exercise>", elapsed_limit=30.0,
              variable_timeout=5.0, candidate_timeout=30.0):
    """Replay each retained tape independently before any new traversal.

    Missing-domain tapes and failed constraints become absent current records;
    execution, resolution and actual grading/test failures stop the operation.
    Original proposal/decision/event order is never rewritten. The component's
    trusted resolver returns a neutral candidate from decoded variables/choices.
    Its own expensive work must use supervised helpers (e.g. placeholders).
    """
    from ctm_checkers.variants import decode
    if type(max_records) is not int or max_records < 1:
        raise VariantError("max_records must be a positive replay resource budget")
    result = copy.deepcopy(history.validate(value))
    deadline = _deadline(elapsed_limit)
    seen, records, locators = set(), [], set()
    gone = 0
    for proposal in value["proposals"]:
        tape = proposal["tape"]
        key = canonical(tape)
        if key in seen:
            continue
        if len(seen) >= max_records:
            raise VariantError("retained tape replay resource budget exceeded")
        seen.add(key)
        try:
            execution = execute(source, variables=variables, replay=decode(tape),
                file=file, label=label, variable_timeout=min(variable_timeout, _remaining(deadline)),
                variant_timeout=min(candidate_timeout, _remaining(deadline)))
        except (Rejected, ReplayUnavailable):
            gone += 1
            continue
        record = _record(resolve(execution))
        _remaining(deadline)
        if record["id"] in locators:
            raise VariantError("component resolver mapped distinct retained tapes to one locator")
        locators.add(record["id"])
        # One supplied record is graded by the existing supervised real checker;
        # it is not trusted merely because an earlier source version passed.
        tested = collect_tested_batch([record], max_source_records=2,
            candidate_timeout=candidate_timeout, elapsed_limit=_remaining(deadline), file=file, label=label)
        record = tested["added"][0]
        result = _retain(result, record, tape)
        records.append(record)
    return {"manifest": result, "records": records, "replayed": len(seen), "gone": gone,
            "classification": classify(result["decisions"], records)}


def generate(value, source, resolve, *, current, attempt_limit, max_source_records,
             variables=None, file="<question>", label="<exercise>", seed=None,
             elapsed_limit=30.0, variable_timeout=5.0, candidate_timeout=30.0):
    """Append up to 25 actually tested, valid, distinct resolved notes.

    current is the component's reconciled current record list, normally from
    reconcile(). A complete new manifest is returned only on success. Persistence
    remains the caller's one leased history.write() after the operation returns.
    """
    from ctm_checkers.variants import encode
    result = copy.deepcopy(history.validate(value))
    deadline = _deadline(elapsed_limit)
    known = {}
    for record in current:
        record = _record(record)
        if record["id"] in known:
            raise VariantError("current candidates require distinct locators")
        if not any(p["record"]["id"] == record["id"] and p["record"]["hash"] == record["hash"]
                   for p in value["proposals"]):
            raise VariantError("current candidate requires a reconciled retained proposal")
        known[record["id"]] = record
    tapes = {}
    historical_ids = {p["record"]["id"] for p in value["proposals"]}
    reserved = [proposal["record"]["note"] for proposal in value["proposals"]]
    with choice_stream(source, attempt_limit=attempt_limit, variables=variables,
            file=file, label=label, seed=label if seed is None else seed,
            variable_timeout=variable_timeout, attempt_timeout=candidate_timeout,
            exercise_timeout=_remaining(deadline)) as stream:
        def resolved():
            for execution in stream:
                record = _record(resolve(execution))
                _remaining(deadline)
                if record["id"] in historical_ids and record["id"] not in known:
                    raise VariantError("historical locator must be reconciled before generating more")
                tape = encode(execution["choices"])
                old_tape = tapes.setdefault(record["id"], tape)
                if old_tape != tape:
                    raise VariantError("component resolver mapped distinct generated tapes to one locator")
                yield record
        batch = collect_tested_batch(resolved(), retained=current, reserved_notes=reserved,
            max_source_records=max_source_records, candidate_timeout=candidate_timeout,
            elapsed_limit=_remaining(deadline), file=file, label=label)
        stats = dict(stream.stats)
    for record in batch["added"]:
        result = _retain(result, record, tapes[record["id"]])
    _remaining(deadline)
    return {"manifest": result, "records": batch["candidates"], "added": batch["added"],
            "tested": batch["tested"], "exhausted": batch["exhausted"], "stream": stats,
            "source_records": batch["source_records"], "duplicate_ids": batch["duplicate_ids"],
            "duplicate_notes": batch["duplicate_notes"]}
