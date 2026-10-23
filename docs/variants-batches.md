# Lazy tested batches from resolved candidates (partial native API)

`ctm_variants.batches.collect_tested_batch(source, *, retained=(),
max_source_records, candidate_timeout=30, elapsed_limit=30, file="<question>",
label="<exercise>")` appends at most **25 new tested candidates**. It consumes a
trusted caller-owned iterator of already-resolved neutral `model.candidate`
records. Constraints must already have passed. There is no unchecked pool built
before selection and no sampling or choice-tree traversal in this collector.

Each supplied record's `data` has exactly `options`, `context` and
`teacher_inputs`, with the same contract as
[`validate_math_candidate`](variants-validation.md). The caller supplies resolved
question text, an exact context and separate literal student input strings; no
teacher printer or template/field extraction is added. Its snapshot, content
hash, locator and resolved note come from the existing neutral model/adapter.
Display-only values cannot be exact teacher data. This collector invents no
identity, number, hash or approval decision.

The complete prior candidate history goes in `retained`. It is trusted, already
resolved/valid history, copied without changing its records or test results.
Every prior locator and exact resolved-note string is reserved, including those
the teacher later rejected, so another tape cannot re-propose a rejected note.
Manifest decisions are separate and are not accepted as candidate records here.
A repeated locator with changed content is an error requiring classification by
the caller, rather than silently replacing history. An unchanged repeated locator
or resolved note is skipped. Notes are compared exactly; no prose normalization
is invented.

Every remaining new candidate runs the mandatory teacher-answer vector and its
authored declarative cases through the real grading adapter. A grading/test error
stops the call; it never causes resampling. Only tested, distinct resolved notes
count toward the 25. New records retain their identity/snapshot/data and receive
the actual validation result in `tests`. A future Generate 25 more action can
pass the retained history with the remaining iterator, or restart a deterministic
source and skip the retained locators/notes. Earlier records remain intact when
the source grows.

The return has `candidates` (history plus additions), `added`, `tested`,
`source_records`, `duplicate_ids`, `duplicate_notes` and `exhausted`. Consumption
stops immediately at 25 additions: no 26th record is requested. `exhausted` means
the iterator actually ended before that stop; false does not prove more records
exist. Fewer than 25 additions with exhaustion are returned explicitly. The
required positive `max_source_records` is a caller-chosen scan resource budget,
including duplicates; reaching it is an error, never a truncated population or
a definition of which candidates count as valid.

One isolated native child imports once and handles actual grading/testing.
Each new candidate has a supervised deadline, including first-child startup.
The parent kills and waits for the child and joins its bounded reader on every
exit path. Author stdout is forwarded through bounded output messages without
resetting the deadline. Requests, result messages and per-candidate author output
retain the execution kernel's 256 KiB limits. A failure returns no partial result
and does not mutate the caller's history.

`elapsed_limit` is checked at source/record boundaries and also limits child
waits. **It cannot interrupt a blocking `next(source)` or arbitrary caller source
code.** This API makes no total supervised producer guarantee. A future variable
producer needs its own supervised lazy/resumable seam; calling the existing
exhaustive API and slicing an unchecked 20,000-record result is not that seam.

No UI, persisted cursor, template extraction, approval reconciliation,
publishing-mode gate or student wiring is implemented. The caller's later
publishing layer must enforce the binding required/optional/review approval
policy. Existing exhaustive-enumeration raw-space limits remain resource bounds
of that separate API, not this collector's candidate population policy.

Run `python tests/test_variants_batches.py` from source and the actual unchanged
browser wheel. Tests cover laziness, 25 more with stable history, constraints and
note deduplication, exhaustion, explicit budgets, real grading/test failure,
deadline cleanup after actual checker entry and forwarding author output.
