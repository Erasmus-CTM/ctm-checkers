# Supervised lazy raw-choice stream (partial native API)

```python
from ctm_variants.streaming import choice_stream

with choice_stream(source, variables=None, attempt_limit=1000,
                   file="lesson.qmd", label="tangent",
                   variable_timeout=5, attempt_timeout=30,
                   exercise_timeout=30) as choices:
    row = next(choices)
```

This native-only context manager yields the same exact `variables`, `choices`
tape and canonical `locator` shape as `generation.execute`. It reuses the
canonical evaluator and finite domains; passing a tape back to `execute` replays
it exactly. Traversal follows the existing finite-domain order, including
dependent domains and constraints. Only structurally equal exact tapes are
deduplicated; booleans and integers remain distinct, and different tapes with
equal computed variables remain separate.

One isolated child imports once. Each consumer request authorizes traversal only
until the next distinct accepted tape or exhaustion. The child waits for the
next command after each accepted path: it does not evaluate a later path while
the caller resolves or tests the current one. The parent can discard repeated
tapes by demanding another path internally. A compact depth-first stack stores
one selected value/index per choice depth, without constructing an unchecked
candidate pool or the entire frontier. Tests take the first 25 results of a
400-million-path space using 27 actual prefix executions.

`attempt_limit` is required and must be a positive integer. It counts actual
prefix executions, including discovery of branches, rejected paths and repeated
tapes, and is an explicit resource budget. It does not count only valid
candidates and does not define a candidate population. Exceeding it raises an
error rather than silently truncating or sampling. The existing kernel's 20,000
limit on an individual finite domain remains its separate resource bound;
there is no whole-tree/frontier-size limit here.

The parent supervises each variable and prefix attempt, and an independent
absolute exercise deadline includes startup and consumer idle time. Valid
statement/attempt progress cannot reset the enclosing deadline. Startup counts
towards the first variable and attempt budgets. Received protocol boundaries,
record shapes and completion accounting are checked independently. Existing
256 KiB message/request and 32 MiB aggregate-output bounds remain explicit errors.
Errors name the file, exercise and last known source line.

Leaving the context, calling `close`, exhausting the source or encountering an
error kills/waits for the child and joins its bounded reader. Always use the
context manager when stopping early. `choices.stats` reports actual attempts,
branches, terminal paths, rejections, repeated tapes and yielded records, plus
`exhausted` and `closed`; these are traversal/resource facts, not a count of
resolved-note-distinct tested candidates. Records already yielded remain with
the caller if a later demand fails; there is no batch transaction or cursor
persistence here.

This seam does not render placeholders or extract answer markers, notes or field
labels. It does not grade candidates, make proposals, invent hashes/identities,
sample, approve, publish or wire students. A component resolver can transform
each raw row into a resolved neutral candidate before handing it to the tested
batch collector. That future composition must deduplicate resolved notes and
count only valid tested candidates, preserving all prior history; a variable
execution or grading failure must remain an error. Generate 25 more can restart
deterministic traversal and skip retained locators/notes, without a persisted
cursor framework. This partial API introduces no proposal-order policy beyond
the existing finite-domain traversal order.

Run `python tests/test_variants_streaming.py` from source and against the actual
unchanged browser wheel. The contracts cover backpressure/early close, large
spaces, dependent choices, constraints, exact replay/deduplication, malformed
protocol, and deadlines after real native worker progress.
