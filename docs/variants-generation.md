# Native variables execution kernel (partial)

This checkpoint adds `authoring/ctm_variants/generation.py` outside the browser
wheels. It follows the [approved design and binding AC decisions](https://github.com/Erasmus-CTM/ctm-assessment/blob/handoff/2026-10/docs/consolidation/2026-10-variants.md)
and its [independent review](https://github.com/Erasmus-CTM/ctm-assessment/blob/handoff/2026-10/docs/consolidation/2026-10-variants-review.md).
It is a native execution building block, not an author-facing generation command.

`execute(source, variables=None, seed="", replay=None, file="<variables>",
label="<question>", variable_timeout=5, variant_timeout=30)` runs one selected
execution. Pass an exact symbol mapping through `variables`. It returns exact
`variables`, the ordered exact `choices` tape, and a canonical value-based
`locator`. Replaying that tape validates each choice against the current domain
and exclusions using structural exact-value codec equality (booleans stay
distinct from integers); removed values or surplus choices fail, and a failed
`require(...)` raises `Rejected`. Nothing silently resamples. The current
locator represents the tape only; it is not yet an approved candidate identity
or a manifest entry. Domain duplicates can yield the same tape and need
deduplication when candidate enumeration is implemented.

The language accepts one assignment or `require(condition, ...)` per statement,
comments, exact decimal and rational arithmetic, and `^` as power. Deterministic
expressions use the existing `ctm_checkers.testing.expression` evaluator, with
native helpers for `subs`, `det`, `inv`, `transpose`, `min`, and `max`.
Strings, attributes, imports, loops, definitions and fixture `raw()` fail explicitly.
`round`/`sigfig` remain unsupported until the shared numeric home can provide
exact authoring arithmetic while preserving legacy grading. Display-only
`dispdp`/`dispsf` are also not added by this kernel.

Finite choices support `pick(list, exclude=[])`,
`pick(low, high, step=1, exclude=[])` (inclusive), ordered `sample(list,k)`
without replacement, and `shuffle(list)`. These three calls occupy a whole
assignment right-hand side. The native STACK-name aliases follow the
[documented random-object semantics](https://docs.stack-assessment.org/en/CAS/Random/),
checked against [upstream stackmaxima.mac at 33383047](https://github.com/maths/moodle-qtype_stack/blob/33383047af39c204bf4442802a058f8b918b2b1b/stack/maxima/stackmaxima.mac):
`rand(n)` excludes n; `rand(list)` chooses an element (an empty list yields
an empty list); `rand_with_step` supports exact rational bounds and positive
or negative steps and includes the upper bound only when it lies on the step.
`rand_range` follows the upstream implementation rather than the documentation's
synonym claim: its two or three arguments are integers, its domain count is
`floor((upper-lower)/step)` without the extra one, and a zero count returns lower;
`rand_with_prohib` excludes listed values from an inclusive integer range
(an all-excluded range yields an empty list); `rand_selection` selects ordered
distinct positions (duplicate input values may remain); and
`rand_selection_with_replacement` permits repeated positions; an empty input
produces a list of empty lists, and a nonpositive count returns an empty list. Arithmetic around
these aliases is supported. Float, set and matrix forms of `rand`, and the
other random-object constructors, are explicitly unsupported in this checkpoint.
The aliases use CTM's deterministic selection, not Maxima's seeded RNG.

The supervisor starts one isolated child per execution, amortizing imports across all
variables. It invokes a trusted absolute script with `-I`, uses a private temporary
working directory, and supplies only the resolved installed package roots for
ctm-checkers, SymPy and mpmath. Arbitrary cwd/PYTHONPATH entries are not inherited. Strictly increasing expected statement boundaries reset the
per-variable deadline. The independent absolute execution deadline includes
startup, imports and serialization. A timeout, protocol failure or worker
failure kills and waits for the child, cancels and joins its bounded stdout
reader, then reports file/label/line context. Requests and output lines are
bounded to 256 KiB; source to 16 KiB, 128 statements and 1,000 AST nodes; input
lists and sample sizes to 128; and each random domain to 20,000 values.
Selection cardinality is checked before constructing any permutations; an
individual selected permutation is unranked directly. Oversized domains fail
explicitly, rather than implying that deterministic sampling exists already.

The shared structured exact-value codec is the only wire-value protocol.
There is no string `sympify`, fallback `eval`, new grader or checker protocol.
Author code retains the approved Quarto trust model; this is a resource-bound
execution tool, not a security sandbox.

Still missing: full candidate enumeration and deterministic sampling above
20,000; accepted candidate locator regeneration across source changes;
placeholder/display evaluation; automatic teacher-answer and authored-test
invocation through `run_question`; conversion into neutral model snapshots;
proposals/default-25 selection; manifests, approvals and component wiring.
Those layers must reuse this bounded execution and existing grading APIs.
No browser wheels or generated payloads change here.

Run `python tests/test_variants_generation.py`. The dedicated workflow pins
SymPy 1.13.3 on Python 3.9, 3.12 and 3.13. Native runs on other versions are
supplemental evidence only.

A supplemental Windows measurement before the final import-isolation change took
4.582 seconds for five executions with 20 simple variables each (~0.916 seconds
per execution). Serially extrapolating to 25 executions is roughly 23 seconds;
this is not a full-batch performance acceptance result. Batch execution and its
performance/deadline orchestration remain future work.
