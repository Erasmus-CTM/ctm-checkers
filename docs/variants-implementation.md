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
No generated payload is changed. No course questions/golden rows are included.

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
* The exact structured runtime codec and native/browser shared custom context
  enrichment must have one home. Reuse the approved shared question-test runner
  and real graders; do not introduce another runner or string evaluator.
* Math integration and plain-pool Lua identities/shared n/seed/seen selection
  remain unimplemented; plain pools must join in the approved scope.
* Direct CLI execution must use a top-level wrapper outside this package, with
  trusted absolute import paths before imports. A sibling math.py must never
  shadow the stdlib; test cwd paths with spaces and foreign math.py on Python3.9+.

Canonical payloads will continue through tools/build.py. Python3.9 is the floor.
The small workflow tests the current pure model on3.9/3.12/3.13; it is not evidence
for generation, browser parity or approval/deployment gates.
