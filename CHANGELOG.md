# Changelog

Versions follow semantic versioning; while `0.x`, a release that changes any
verdict (a golden row) or the API is a MINOR release, everything else a PATCH
release. Every grading change is listed under "Grading changes" with the
finding or decision it implements, its test and the summary of its golden
diff (docs/goldens.md).

## Unreleased (0.2.0.dev0)

stack-sympy's STACK engine moves here (consolidation step 2, C3): its Python
code as it was at stack-sympy `f450bcd`, relicensed AGPL-3.0-or-later by the
CTM team, its authors. No grading changes: every golden row is reproduced
as before, the STACK tables recorded from stack-sympy's own code included.

- `ctm_checkers.stack`: stack-sympy's `stack_sympy` package (its 14 modules
  but `basis_helper.py`, whose `assess_basis` is `ctm_checkers.matrix`'s,
  the same function), with its build-time command line
  (`python -m ctm_checkers.stack.cli render|test`, the card's HTML as
  before) and the page's calls `stack.validate`, `stack.grade` and
  `stack.tests` of `browser.call` (stack-sympy's worker requests, with their
  envelope; `ctm_checkers.stack.page`).
- A wheel and a page script of its own for the STACK engine
  (`ctm_checkers_stack-<version>-py3-none-any.whl`, `ctm-checkers-stack.js`
  with `CTMCheckersStack.install(py)`, `checkers.json` `parts.stack`), so
  that pages with math-exercise never carry it (design §13 item 5);
  ctm-libs' load of the installed package (`pkgutil.walk_packages`) sees no
  STACK module there. `ctm_checkers/__init__.py` joins the two wheels on
  `sys.path` (`pkgutil.extend_path`); pip installs them as `ctm-checkers` and
  `ctm-checkers-stack`. The page scripts give their URL (`scriptURL`) for
  workers that load them.
- `examples/stack/`: the STACK question XML, its one home (stack-sympy's
  `questions/`, which its site now copies from here), with each folder's
  licence; `matrix-checkers.py` imports `ctm_checkers.matrix`.
- `tests/stack/`: 24 of stack-sympy's 26 test modules (not its render test,
  nor the corpus-page test, which stay with its site) and its fixtures;
  `tools/stack_native/`: its native STACK comparison, compliance report,
  corpus replay and fixture import, and the stack-sympy audit's `dual.py`;
  `reports/stack-compliance/`: the report's Quarto project;
  `.github/workflows/native-stack.yml`: its CI (reusable: stack-sympy's site
  calls it at its pin and publishes the report). The report's browser parity
  runs in Pyodide 0.28.3 (ctm-libs' page runtime, which stack-sympy's worker
  now uses; before: 0.27.2) and installs the engine with the page scripts.
- Golden tables: the STACK tables are verified with ctm_checkers.stack too
  (from `src/`, the wheels, and the page scripts in Pyodide); 14 mutations
  of the STACK engine must fail them (`tests/test_mutations.py`), and
  `stack/supplement` (47 rows, recorded with stack-sympy's code) reaches the
  rules that only mutations reached: NumAbsolute's and NumRelative's bounds,
  AlgEquiv's numeric rejection screen, response-tree scores outside [0, 1].
- The corpus baseline (`examples/stack/corpus/baseline.json`) names the
  engine it was recorded with: only its `engine_revision`,
  `adapter_source_sha256` and `python_version` changed.

- The page's call text is ctm-libs' (`MathExerciseRuntime.callCheckers`),
  documented exactly in docs/api.md:
  `import builtins as _ctm_builtins` and then
  `_ctm_builtins.__import__("ctm_checkers.browser", fromlist=["call"]).call(name, _ctm_builtins.globals())`.
  It looks up no name in the page's namespace, which learner code shares (a
  learner's `__import__ = None` stopped every check of math-exercise 0.10.0).
  The install code leaves no name in the namespace (the `_ctm_import` and
  `_ctm_globals` of the first 0.1.1.dev0 builds are gone; no released
  version had them), and `browser.call` without `_ctm_request` raises a
  `RuntimeError` naming the call instead of running an empty request.
- STACK golden tables (`tests/golden/stack/`, 4,873 rows; docs/goldens.md),
  recorded from stack-sympy `f450bcd` with its own code before its engine
  moves here: STACK's answer-test fixtures through the compliance runner,
  stack-sympy's port regressions and reference cases, every example question
  (import, cards, variants, question tests and generated answers), and the
  probes of the stack-sympy audit with their native verdicts. The legacy
  adapter (`golden.py verify --stack-legacy`, CI on Python 3.9 to 3.13 and in
  Pyodide 0.27.2 and 0.28.3) reproduces every row. The inputs: STACK's
  example questions in `examples/stack/` (their one home from now on,
  stack-sympy's `questions/`) and its fixtures in `tests/stack/`.
- Golden tables: three supplementary requests (88 in all) for rules that
  only mutations reached in the second round of the review: an imaginary part
  between 1e-9 and 1e-3, boolean graph node identifiers, and how
  `_math_response_json` spells numbers (positional from 1e-6 to below
  1e21, as JSON.stringify); `tests/test_mutations.py` has 24 mutations.
- Tools: `build.py --check --released-base <commit>` (CI: the base commit)
  requires the releases recorded on the base branch unchanged, so a pull
  request cannot rewrite a released entry together with the code;
  `golden.py` resolves a relative `CTM_UMBRELLA` where it starts; the
  umbrella pin is ctm-assessment's merge of PR #14 (`9ed46a4`).

## 0.1.0 (19 October 2026)

The checker code of math-exercise, moved verbatim from math-exercise 0.10.0
(consolidation step 2, design in ctm-assessment
`docs/consolidation/2026-10-step2.md`). No grading changes: the built wheel
reproduces every golden row on Python 3.9 to 3.13 and in Pyodide 0.27.2 and
0.28.3, and so does math-exercise 0.10.0's own code. STACK's engine follows
in 0.2.0.

- Golden verdict tables for math-exercise, recorded from math-exercise 0.10.0
  before any code moved: every grading call of math-exercise's own examples as
  the umbrella's parity harness captured it at the runtime boundary (672
  requests, 932 custom-checker requests, 33 authored questions; capture of
  ctm-assessment 10f8c9d), the `#| checker:` namespace, 85 supplementary
  requests and the rounding rule (1020 rows, and 561 through variants.py),
  with results for every Python from 3.9 to 3.13. `tools/golden.py` verifies
  them against the legacy code or ctm-checkers, natively and in Pyodide
  (`tools/pyodide/verify.cjs`), records authored rows with the harness's own
  recorder (`authored_record.py` of the pinned umbrella commit), and imports
  a new capture with one command.
  The captured tables alone fail on both numeric mutations of the step-2
  review (rounding half to even; tolerance `<`), and the tables fail on all
  21 mutations of the checks in `tests/test_mutations.py`.
- `ctm_checkers.math_exercise`: `check`, `check_custom`, `namespace` (the
  names a `#| checker:` sees, as before), `learner_strings` and `admit` (the
  dunder rule), `round_places`, `sigfigs_round` and `parse_tolerance`
  (standard library only), the authored question tests (`authored`, with
  question-tests.py's command line), `symbols(vars)`;
  `core.result.normalize_result`, `matrix.assess_basis`,
  `graph.graph_from_response`, `testing.run_tests(check, symbols, tests, *,
  namespace, base)`.
- `ctm_checkers.browser.call(name, caller)`: the single entry from the page,
  one JSON request (`_ctm_request`) instead of thirteen `_math_*` globals.
- `_extensions/ctm-checkers/`, generated by `tools/build.py`: the wheel and
  the page script `ctm-checkers.js`, which carries the wheel and its own
  install code (`CTMCheckers.install(py)`, only `globals.set` and
  `runPythonAsync`; it looks up no name in the page's namespace, and each
  install has its own payload variable).
- `tools/released.json`: a released version never changes (`build.py
  --check`), so its HTML dependency path always holds the same script.
