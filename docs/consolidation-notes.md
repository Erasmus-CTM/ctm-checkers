# Notes for the next pull requests of consolidation step 2

What the pull requests after ctm-checkers 0.1.0 need to know (ctm-libs LIB,
math-exercise M1, the umbrella U2, and the first grading-change PR). The
design is ctm-assessment `docs/consolidation/2026-10-step2.md`.

## ctm-libs (LIB)

- `MathExerciseRuntime.ensureCheckers(py)`: the once-per-runtime bookkeeping
  (the `installed` WeakMap, which `forgetModules` clears) around
  `globalThis.CTMCheckers.install(py)`. The install code itself is in
  ctm-checkers' page script (docs/api.md). Each call installs again with a
  payload variable of its own, so two calls that overlap (two cells retrying
  at once) are safe, and the install code looks up nothing in the page's
  namespace.
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
- The reinstall retry (`math-exercise.js:1284`) also matches
  `No module named 'ctm_checkers` (the message `tests/pyodide/payload.cjs`
  checks) and `has no attribute 'call'`.
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
  moves its pin with the next capture it imports.

## Before the first grading-change pull request (fixes, B rows)

- `tools/golden.py diff --base origin/main` (the summary of a golden diff:
  rows per table, status transitions) and `check-changelog` (a pull request
  that changes rows needs a "Grading changes" entry), design §6.4 and §7,
  are not implemented: 0.1.0 has no grading changes. They must exist before
  the first fix or B-row pull request relies on golden diffs as evidence.
- The first change after 0.1.0 sets a development version
  (`tools/released.json`, docs/api.md).
