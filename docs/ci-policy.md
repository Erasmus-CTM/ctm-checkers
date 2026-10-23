# Checker CI policy

Pull requests and pushes to main run one Python 3.12 gate. It retains the full
source and actual-wheel test suites, canonical payload and historical-release
verification, PR grading-change/changelog checks, and pip installation. The
existing `Python 3.12` check identity remains. No source tests or assertions are
removed.

A broad campaign requires AC authorization and manual workflow dispatch with the
exact confirmation `broad testing campaign`. The Tests workflow then retains the
five-version Python matrix, both full golden replays and mutation assertions.
The Pyodide workflow retains both runtime versions and all payload/golden checks.
The focused authoring workflows retain their existing three-version source and
wheel contracts and canonical artifact production. These duplicate suites no
longer run automatically. Weekly Pyodide/native schedules are removed.

This policy distinguishes repeated broad compatibility campaigns from the one
already authorized full acceptance pass for a coherent integration candidate.
Use small focused checks while wiring that candidate, then run its authorized
acceptance once; do not ask for renewed approval solely because of this policy.
ctm-demo is the integration testbox. Once its full acceptance passes and all
components are merged, ask AC to start ingmat3a migration. Special ingmat3a
branches may be prepared and tested autonomously; its student-facing main stays
protected. This checker policy does not change either course.

Native STACK compliance is deferred last. Its manual entry point requires the
same confirmation. Its existing reusable `workflow_call` API, required
`ctm-checkers-ref` input, test jobs, dependency behavior and report artifact
contract are preserved. A reusable caller is a distinct existing integration;
this policy does not pretend it was manually authorized. In particular,
stack-sympy's pinned site workflow still calls its pinned checker workflow and
requires its compliance report for publication. Editing a newer checker workflow
does not alter older pinned callers. Changing that caller or its publication
policy requires coordinated work; do not skip the report and fake success.

Repository rulesets returned an empty list during inspection. Legacy main branch
protection could not be read: the integration received HTTP 403, `Resource not
accessible by integration`. Existing required check names are therefore unknown.
AC owns settings and merging. Removing automatic matrix/Pyodide/native statuses
may require AC to update required checks; this patch changes no settings. Preserve
`Python 3.12` as the default gate and do not claim broad acceptance from its result.

This policy changes when existing tests run, not their assertions, grading rules,
release ledgers, product behavior, package pins, or deployments. Equivalent policy
changes in other repositories must respect their own reusable workflows and
publication dependencies.
