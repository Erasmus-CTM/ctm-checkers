# Variants: recovered work-in-progress checkpoint

This first native slice is outside the browser wheel. It does not replace
ctm_checkers.testing, any grader, the existing math generator, or H1.

The model accepts component-normalized ordered canonical input strings. The
component must collect resolved maths placeholders (including values in prose),
ordered teacher keys and effective grading options, excluding prose wording,
translations and unused helper variables. This module cannot infer those
semantics from arbitrary author text.

The short content hash covers ordered maths, ordered teacher answers and grading.
A separate full checksum covers the retained approved snapshot, including
variable display values. Old snapshots verify independently of current source.
These checks detect inconsistent edits, not authenticate a writer.

Exact locator/hash matches reserve candidates first. Math retains a changed
existing locator. Moving decisions requires globally unambiguous old and new
content. Numbers allocate only on explicit decisions, above every historical
number; gone records remain and numbers are never recycled.

## Explicit unfinished boundaries

This is a checkpoint, not an installed variants feature or reviewed release.
No course questions/golden rows are included.

* Content-first classification is modeled, but STACK decision reconciliation is
  not implemented. Historical and resolved current locators remain distinct.
  The unique-id manifest constraint must be revisited together with global
  one-to-one matching and n-based decisions before any STACK adapter claims
  support. Changing uniqueness alone or choosing a first id/hash is insufficient.
* Native bounded generation, per-variable and per-variant subprocess budgets,
  pre-materialization limits and bounded serialization/IPC remain unimplemented.
* Accepted locators must regenerate independently of a new sampling window.
* Manifest file IO, required/default previews, approval tooling and deployment
  selection remain unimplemented.
* Math integration and plain-pool Lua identities/shared n/seed/seen selection
  remain unimplemented; plain pools must join in the approved scope.
* Direct CLI execution must use a top-level wrapper outside this package, with
  trusted absolute import paths before imports. A sibling math.py must never
  shadow the stdlib; test cwd paths with spaces and foreign math.py on Python3.9+.

Canonical payloads will continue through tools/build.py. Python3.9 is the floor.
The small workflow tests the current pure model on3.9/3.12/3.13; it is not evidence
for generation, browser parity or approval/deployment gates.

## Exact custom-checker context (bounded implementation)

The approved scope is the [variants design](https://github.com/Erasmus-CTM/ctm-assessment/blob/handoff/2026-10/docs/consolidation/2026-10-variants.md)
and [independent review](https://github.com/Erasmus-CTM/ctm-assessment/blob/handoff/2026-10/docs/consolidation/2026-10-variants-review.md).
AC decisions 13 and 19 bind named default-language answers and reuse of real
graders; decision 15's preview/publishing gates remain unfinished below.

The shared runtime `ctm_checkers.variants` encodes supported exact data as
versioned tagged JSON. Integers, rationals, Symbols with assumptions, pi/E/I,
explicit scalar expression constructors, dense matrices and nested data
containers have structural encodings. Floats, unknown SymPy types and arbitrary
constructor names fail; no strings are evaluated as Python or SymPy source.
Depth, node, text and matrix dimensions are checked before decoding constructors.
Expression reconstruction disables evaluation, including large powers.

An optional trusted request.question_context is separate from learner JSON.
The existing check_custom parses expression fields with explicit question
Symbols, then adds response.answers, variables, teacher and variant. An explicit
variable key x bound to a Symbol named x governs parser locals and checker
symbols for this context-enabled request; unrelated bindings remain unchanged.
Conflicting scalar Symbol assumptions fail. Nested data can retain same-name
distinct Symbols and never rewrites parser bindings. Answers
and teacher use ordered default-language labels, including spaces/Unicode;
expressions and checker symbols remain available. The legacy namespace still
sees the original JSON response. Learner reserved keys cannot override context.
Identity is None before a decision; supplied identities contain only n/id/hash
with positive n. Explicit resolved variables plus a named teacher mapping in
run_question use this same path; variables alone still resolve ordinary fixtures.

This first adapter accepts scalar expression responses. Graphical responses and
named matrix input responses retain their ordinary existing path, and explicitly
attaching question_context to them fails. Exact matrices/lists inside question
variables or teacher values are supported with dense matrix value semantics.
Runtime page generation and component
transport wiring remain unfinished; this is not an installed variants feature.
All payload changes must come from tools/build.py, and the existing native,
wheel and actual Pyodide harnesses exercise the same real grader.

