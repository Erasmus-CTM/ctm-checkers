# Notes for the next pull requests of consolidation step 2

What the pull requests after ctm-checkers 0.1.0 and 0.2.0 need to know
(ctm-libs, math-exercise M1, the umbrella U2, stack-sympy S1, and the first
grading-change PR). The design is ctm-assessment
`docs/consolidation/2026-10-step2.md`.

## ctm-libs (LIB)

- `MathExerciseRuntime.ensureCheckers(py)`: the once-per-runtime bookkeeping
  (the `installed` WeakMap, which `forgetModules` clears) around
  `globalThis.CTMCheckers.install(py)`. The install code itself is in
  ctm-checkers' page script (docs/api.md). Each call installs again with a
  payload variable of its own, so two calls that overlap (two cells retrying
  at once) are safe; the install code looks up nothing in the page's
  namespace and leaves no name there. The call text is ctm-libs' own
  (`callCheckers`; docs/api.md).
- `_ctm_guard`: its kept module prefix becomes `("_ctm_", "ctm_checkers")`
  (design §13 item 4). `browser.call` imports its handlers before the
  snapshot, so a checker that removes `ctm_checkers` modules from
  `sys.modules` is undone by the restore. A learner who clears `sys.path`
  does not break lazy submodule imports (the package's `__path__` points into
  the zip).
- The HTML dependency version is `checkers.json`'s `dependency`: the version
  of a release, `X.Y.Z.devN+<sha8>` for a development version. The `+` ends
  up in a path segment (`site_libs/quarto-contrib/ctm-checkers-0.2.0.dev0+1a2b3c4d/`).
  GitHub Pages serves it, but a static host that decodes `+` in a path as a
  space (classic S3 website endpoints) would not find the file: check it in
  LIB's render fixture, and if a host matters, map `+` to `-` there.

## math-exercise (M1)

- The question-tests.py shim puts the wheel first on `sys.path`, then imports
  `ctm_checkers.math_exercise.authored` inside a try, so that a missing wheel
  ends with the install message ("math-exercise question tests need
  ctm-checkers, part of CTM Assessment…"), and calls
  `sys.exit(authored.main(sys.argv[1:]))`. `authored.main` imports SymPy when
  it runs, so a missing SymPy still ends with "math-exercise question tests
  failed: No module named 'sympy'"; below Python 3.9 it stops with one
  message naming the version. Run it as a script, never with `python -m`.
- Requests: the fields of docs/api.md. Send `response` as the value that
  JSON.stringify would have written as `_math_response_json` (the same key
  order: `page_json` rebuilds that text for the checker namespace). Keep the
  `formCredit` clamp (`math-exercise.js:1406-1407`): JSON.stringify sends NaN
  as `null`, where Pyodide passed NaN as a float.
- The call text is ctm-libs' (`MathExerciseRuntime.callCheckers`, docs/api.md);
  math-exercise calls through it, so the reinstall retry is ctm-libs' too
  (a request still in the namespace after a failure).
- variants.py rounds with `ctm_checkers.math_exercise.numeric`:
  `python <ctm-checkers>/tools/golden.py verify --adapter wheel --variants <math-exercise> --suite rounding-variants`
  checks it against the rounding rows recorded from 0.10.0.

## The umbrella (U2)

- `tools/build.py --check` in the builder's `--test`; the package copies
  `_extensions/ctm-checkers/` (wheel, script, `checkers.json`,
  `_extension.yml`).
- `integration/pyodide-parity/authored_record.py` is the one copy of the
  authored-question recorder: the harness's capture and ctm-checkers'
  `golden.py` both use it (ctm-checkers pins the umbrella commit and the
  file's SHA-256 in `tools/pins.json`, with `runtime.cjs` and `wheels.cjs`).
  A change of the recorder is a change of the authored rows: ctm-checkers
  moves its pin with the next capture it imports. The pin is ctm-assessment's
  merge of PR #14 (`9ed46a4`).

## ctm-libs and the STACK engine (0.2.0)

- The STACK engine has its own wheel and page script (docs/api.md):
  `checkers.json` `parts.stack` names them. Pages with math-exercise load
  `ctm-checkers.js` only, so `ensureCheckers`' walk of the installed package
  (`pkgutil.walk_packages`) finds no STACK module there and nothing in
  ctm-libs needs limiting.
- A component that grades STACK questions needs (a small ctm-libs change):
  `ctm.checkers.use("stack")` (the HTML dependency `ctm-checkers-stack`,
  version `parts.stack.dependency`, after `ctm-checkers`) and
  `ctm.checkers.environment(env, "stack")` (both wheels on `PYTHONPATH`).
  `CTMCheckersStack.install(py)` installs both wheels, so
  `ensureCheckers(py, CTMCheckersStack)` and
  `callCheckers(py, "stack.grade", request, CTMCheckersStack)` serve it; where
  one runtime gets both payloads, the once-per-runtime bookkeeping is per
  payload (`checkers.name`), else the second payload is never installed.

## stack-sympy (S1)

- Build: `ctm.checkers.require("stack-sympy", 1)`, then
  `python -m ctm_checkers.stack.cli render …` (the arguments of
  `stack_sympy.cli render`, the same card HTML) in
  `ctm.checkers.environment(nil, "stack")`.
- Worker: `importScripts` of ctm-libs' runtime (`MathExerciseRuntime.scriptURL`)
  and of both page scripts (`CTMCheckers.scriptURL`,
  `CTMCheckersStack.scriptURL`); `ensurePyodide()`, `loadPackage('sympy')`,
  then `callCheckers(py, 'stack.<validate|grade|tests>', {question, variant,
  answers}, CTMCheckersStack)`: the same envelope as before.
- Examples: `examples/stack/` of the pinned ctm-checkers is copied to
  `questions/` before rendering (it is the same files; `matrix-checkers.py`
  imports `ctm_checkers.matrix`, so cards that embed it differ in that line).
- The compliance report: `uses: Erasmus-CTM/ctm-checkers/.github/workflows/native-stack.yml@<pin>`
  with `ctm-checkers-ref: <pin>`; its artifact `native-compliance-html` is the
  report to publish under `/compliance`.

## AC's decisions on 0.2.0 (20 October 2026)

After the independent review of C3 (ctm-checkers #4), AC decided:

- **A. Course-derived STACK questions.** `course-b-rank-pivots.xml` (S-01's
  test case), `course-b-nullspace.xml` and `course-c-nullspace.xml` have
  their own golden table, `stack/questions-course`, labelled as course
  material under CC BY-SA 4.0 with a provenance and licence notice
  (`tests/golden/PROVENANCE.md`); the checker file the questions use
  (`examples/stack/matrix-checkers.py`) and the generated answers stay
  AGPL-3.0-or-later, as in the project table. No other table holds course rows, and
  rows generated from the course repositories (ctm-demo, ingmat3a) stay in
  the umbrella (design §13 item 7). The H2 rule (below) is unchanged.
- **B. HELM samples.** The two HELM questions and their 179 rows
  (`stack/questions-helm`, CC BY-NC 4.0) stay, with a licence notice of
  their own wherever the licence is stated: test data only; the code is
  AGPL-3.0-or-later.
- **C. Accepted:**
  - the second STACK wheel and page script (`ctm-checkers-stack`, about
    150 KB in every course's `_extensions/ctm-checkers/`, never loaded on
    math pages);
  - the compliance report's browser parity on Pyodide 0.28.3 (ctm-libs'
    runtime; it was 0.27.2 in stack-sympy), the goldens still verified on
    both;
  - the native-image validation (native STACK in Maxima, `native-stack.yml`)
    in ctm-checkers;
  - the CTM-authored example XML in `examples/stack/` keeps CC BY-SA 4.0.

## Grading changes (fixes, B rows), from 0.3.0

- 0.3.0 (S-01, design §9 order 1) is the first grading change. Its pull
  request brought the tools the next ones use (docs/goldens.md, "Grading
  changes"): `tools/golden.py update --change NAME` writes the changed rows
  (the legacy code's result kept as `legacy`, the change named in
  `changes`), `diff --base REF [--rows]` the summary for the pull request and
  the CHANGELOG, and `check-changelog --base REF`, which CI runs on every
  pull request: STACK's and math-exercise's rows never change together
  (H2), each changed result names its change, the version is a new MINOR one
  (0.x) and the CHANGELOG names the change under "Grading changes".
- STACK fixes about input validation can be checked against native STACK's
  own PHP validation: `tools/stack_native/check_validation.py` (STACK's API
  emulation of Moodle, PHP 8, no Maxima; the `native` job of
  `native-stack.yml`). It takes the golden rows whose answers name a question
  variable; since 0.6.0 (S-13) it also compares every golden answer with
  STACK's verdict and, for the rules S-13 follows, its message. Its one
  "other message" of S-01 is `d+0*f`, which also names a feedback variable
  (S-01).
- 0.4.0 (the review of S-01), 0.5.0 (S-02, `I` and `E`) and 0.6.0 (S-13,
  input rules) followed as one set. The next fixes, one pull request each in
  §9's order: S-07, S-05, S-10, S-11, S-12, S-04, S-08, S-09, then S-06 (a
  plain fix, AC 19 Oct); S-03 stays as it is until the STACK author answers.
