# Changelog

Versions follow semantic versioning; while `0.x`, a release that changes any
verdict (a golden row) or the API is a MINOR release, everything else a PATCH
release. Every grading change is listed under "Grading changes" with the
finding or decision it implements, its test and the summary of its golden
diff (docs/goldens.md).

## 0.3.0 (21 October 2026)

STACK: a student answer may no longer name a question variable or a
feedback variable (S-01, the stack-sympy audit's critical finding; step-2
design §9, order 1). A MINOR release, as every release that changes a
verdict while `0.x`; stack-sympy pins it. math-exercise's tables do not
change (H2).

### Grading changes

- **S-01: the names of question and feedback variables in student
  answers.** Before, student input read the question's frozen variables
  (`expressions.py` `evaluate`, `engine.py` `_input_validation`): `ta` in
  `polynomial-expansion.xml` previewed as `x^2+7x+12` and scored 1, as did
  `r` and `P` in `course-b-rank-pivots.xml`, `T` in `determinant-one.xml`
  and `d` in `python-checker.xml`; a feedback variable leaked the same way
  through the answer tests (`d` in the new supplement question scored 1).
  Now validation rejects such an answer before evaluating it, as STACK does
  (`question.php:430-441`, `cassecurity.class.php:373-376`): the input is
  invalid with STACK's message for each name, in order
  (`stackCas_forbiddenVariable`: "Forbidden variable or constant: ta."),
  with no preview and no response tree. Question tests still resolve the
  names on the author's side (`_qtest_answer`): no `stack.tests` row
  changes. Feedback variables are forbidden too, although STACK 4.13.1 does
  not forbid them (`question.php:436`, a TO-DO there): this engine's answer
  tests evaluate the student's expression where they are defined.
  Tests: `tests/stack/test_forbidden_variables.py` (the audit's leak cases,
  their question tests, feedback variables, names inside expressions,
  names that only look alike, every golden answer row); five mutations
  (`tests/test_mutations.py`, docs/goldens.md).
  - **Native STACK.** `tools/stack_native/check_validation.py` (new; the
    `native` job of `native-stack.yml`) validates every golden answer that
    names a variable with STACK's own PHP input validation (STACK
    `10d3233`, PHP 8, no Maxima): of 373 such inputs, 356 get the same
    verdict and message; 15 the same verdict (`forbiddenVariable`) with
    other names in STACK's message (14 S-13 cases: STACK checks
    `ta_perimeter` part by part and names `perimeter`, an unknown name of
    three letters or more; and `d+0*f`, where STACK names only `f`); 2 name
    only a feedback variable, which STACK accepts.
  - **Golden diff** (`tools/golden.py diff --base 8c3db5e`): 366 rows
    changed and 6 added, all `stack.answer` rows in which an answer names a
    question or feedback variable (the generated answer sets have every
    question variable's name in each input since 0.2.0, and leak.py's
    answers); no row removed, no other call, no `math_exercise` table.
    372 rows name S-01 (`changes`) and keep stack-sympy's result as
    `legacy`.

    | Table | Changed | Added | Before → after (rows) |
    |---|---|---|---|
    | `stack/questions-project` | 127 | 0 | graded 1.0 → invalid 27; graded 0.6666666667 → invalid 14; graded 0.0 → invalid 8; invalid → invalid 78 |
    | `stack/questions-library` | 140 | 0 | graded 1.0 → invalid 37; graded 0.5 → invalid 2; graded 0.0 → invalid 63; invalid → invalid 38 |
    | `stack/questions-helm` | 64 | 0 | graded 1.0 → invalid 1; graded 0.0 → invalid 3; invalid → invalid 60 |
    | `stack/questions-course` | 16 | 0 | graded 1.0 → invalid 4; graded 0.0 → invalid 2; invalid → invalid 10 |
    | `stack/probe-questions` | 13 | 0 | graded 1.0 → invalid 8; graded 0.6666666 → invalid 3; graded 0.5 → invalid 2 |
    | `stack/supplement` | 6 | 6 | graded 1.0 → invalid 2; graded 0.8 → invalid 3; invalid → invalid 1; new: invalid (the legacy code: graded 1.0 5, graded 0.0 1) |

    In the 367 inputs that changed, 265 were valid and previewed the
    variable's value; 102 were invalid with a message computed from that
    value, which told the student something about it too ("Enter a
    matrix", "Use the same collection type as the teacher answer", the
    matrix dimensions, "Enter a numerical answer"). Each is now
    "Forbidden variable or constant: …". The "invalid → invalid" rows had
    such an input, or another input that was invalid already. By question
    file (rows; the names typed; the result before):

    | Table | File (examples/stack/) | Rows | Names typed | Before |
    |---|---|---|---|---|
    | `probe-questions` | `probes/thirds.xml` | 3 | `ta` | graded 0.6666666 ×3 |
    | `probe-questions` | `probes/quiet.xml` | 1 | `ta` | graded 1.0 ×1 |
    | `probe-questions` | `probes/twoparts.xml` | 4 | `a`, `b` | graded 0.5 ×2, graded 1.0 ×2 |
    | `probe-questions` | `probes/numabs-branch.xml` | 1 | `ta` | graded 1.0 ×1 |
    | `probe-questions` | `probes/options.xml` | 1 | `ta` | graded 1.0 ×1 |
    | `probe-questions` | `probes/eqtype.xml` | 1 | `ta` | graded 1.0 ×1 |
    | `probe-questions` | `probes/physics-I.xml` | 1 | `ta` | graded 1.0 ×1 |
    | `probe-questions` | `probes/crash.xml` | 1 | `ta` | graded 1.0 ×1 |
    | `questions-course` | `course-b-rank-pivots.xml` | 12 | `B`, `P`, `r` | graded 1.0 ×4, invalid 0.0 ×8 |
    | `questions-course` | `course-b-nullspace.xml` | 2 | `A` | graded 0.0 ×2 |
    | `questions-course` | `course-c-nullspace.xml` | 2 | `A` | invalid 0.0 ×2 |
    | `questions-helm` | `upstream/rounding-three-dp.xml` | 60 | `a1`, `a2`, `a3`, `a4`, `ta1`, `ta2`, `ta3`, `ta4`, `ta5`, `ta6` | invalid 0.0 ×60 |
    | `questions-helm` | `upstream/bodmas.xml` | 4 | `a1`, `a2`, `a3`, `ta` | graded 0.0 ×3, graded 1.0 ×1 |
    | `questions-library` | `corpus/AlgMap-4-13.xml` | 6 | `A`, `B`, `C`, `D`, `p`, `ta` | graded 0.0 ×4, graded 1.0 ×2 |
    | `questions-library` | `corrected/AlgMap-6-4.xml` | 2 | `p`, `ta` | graded 0.0 ×1, graded 1.0 ×1 |
    | `questions-library` | `corpus/AlgMap-11-8.xml` | 1 | `ta` | graded 1.0 ×1 |
    | `questions-library` | `corrected/7-3-26-(Write-sim-eqns-with-matrices).xml` | 28 | `a1`, `a2`, `a3`, `a4`, `a5`, `a6`, `a7`, `a8`, `a9`, `b1`, `b2`, `b3`, `ta1`, `ta2` | graded 1.0 ×2, invalid 0.0 ×26 |
    | `questions-library` | `corpus/AlgMap-8-10.xml` | 8 | `a`, `b`, `c`, `d`, `fta`, `ta`, `u`, `v` | graded 0.0 ×6, graded 1.0 ×2 |
    | `questions-library` | `corpus/AlgMap-13-1-.xml` | 6 | `a`, `b`, `cf1`, `cf2`, `ta`, `v` | graded 0.0 ×5, graded 1.0 ×1 |
    | `questions-library` | `corpus/Complex_Convert_1.xml` | 9 | `argset`, `argsol`, `modsol`, `n1`, `principaltheta`, `rval`, `x`, `y`, `z1` | graded 0.0 ×1, invalid 0.0 ×8 |
    | `questions-library` | `corpus/LinearAlgebra_elementary_3.xml` | 3 | `avar`, `correctanswer`, `wronganswer1` | graded 0.0 ×1, graded 1.0 ×1, invalid 0.0 ×1 |
    | `questions-library` | `corpus/AlgMap-9-6.xml` | 2 | `ta`, `v` | graded 0.0 ×1, graded 1.0 ×1 |
    | `questions-library` | `corpus/Logs_1.xml` | 5 | `a`, `correctanswer`, `n`, `wronganswer1`, `wronganswer2` | graded 0.0 ×4, graded 1.0 ×1 |
    | `questions-library` | `corpus/AlgMap-4-1.xml` | 4 | `a`, `b`, `c`, `ta` | graded 0.0 ×3, graded 1.0 ×1 |
    | `questions-library` | `corpus/AlgMap-1-5.xml` | 4 | `a`, `b`, `p`, `ta` | graded 0.0 ×2, graded 1.0 ×2 |
    | `questions-library` | `corpus/AlgMap-14-1.xml` | 7 | `cf1`, `cf2`, `f`, `k1`, `ta`, `ta2`, `v` | graded 0.0 ×5, graded 1.0 ×2 |
    | `questions-library` | `corpus/AlgMap-9-1.xml` | 5 | `cf1`, `k1`, `k2`, `ta`, `v` | graded 0.0 ×4, graded 1.0 ×1 |
    | `questions-library` | `corpus/AlgMap-10-1.xml` | 5 | `cf1`, `fac`, `k1`, `ta`, `v` | graded 0.0 ×4, graded 1.0 ×1 |
    | `questions-library` | `corrected/AlgMap-1-5.xml` | 4 | `a`, `b`, `p`, `ta` | graded 0.0 ×2, graded 1.0 ×2 |
    | `questions-library` | `corpus/AlgMap-11-1.xml` | 4 | `ta1`, `ta2` | graded 0.5 ×2, graded 1.0 ×2 |
    | `questions-library` | `corpus/AlgMap-2-1.xml` | 2 | `n`, `ta` | graded 0.0 ×2 |
    | `questions-library` | `corpus/AlgMap-6-7.xml` | 4 | `a`, `b`, `ta`, `v` | graded 0.0 ×3, graded 1.0 ×1 |
    | `questions-library` | `corpus/LinearAlgebra_elementary_1.xml` | 3 | `avar`, `correctanswer`, `wronganswer1` | graded 0.0 ×1, graded 1.0 ×1, invalid 0.0 ×1 |
    | `questions-library` | `upstream/algmap-6-1.xml` | 5 | `a`, `b`, `c`, `d`, `ta` | graded 0.0 ×4, graded 1.0 ×1 |
    | `questions-library` | `corpus/AlgMap-1-6.xml` | 4 | `a`, `b`, `c`, `ta` | graded 0.0 ×3, graded 1.0 ×1 |
    | `questions-library` | `corrected/AlgMap-2-5.xml` | 4 | `a`, `b`, `c`, `ta` | graded 0.0 ×3, graded 1.0 ×1 |
    | `questions-library` | `corpus/LinearAlgebra_elementary_4.xml` | 3 | `avar`, `correctanswer`, `wronganswer1` | graded 0.0 ×1, graded 1.0 ×1, invalid 0.0 ×1 |
    | `questions-library` | `corpus/LinearAlgebra_elementary_2.xml` | 3 | `avar`, `correctanswer`, `wronganswer1` | graded 0.0 ×1, graded 1.0 ×1, invalid 0.0 ×1 |
    | `questions-library` | `corpus/AlgMap-2-5.xml` | 4 | `a`, `b`, `c`, `ta` | graded 1.0 ×4 |
    | `questions-library` | `corpus/AlgMap-7-1.xml` | 2 | `a`, `ta1` | graded 0.0 ×1, graded 1.0 ×1 |
    | `questions-library` | `corpus/AlgMap-6-4.xml` | 2 | `p`, `ta` | graded 0.0 ×1, graded 1.0 ×1 |
    | `questions-library` | `corpus/AlgMap-8-5.xml` | 1 | `ta` | graded 1.0 ×1 |
    | `questions-project` | `finite-author-helpers.xml` | 54 | `a`, `common`, `converted`, `difference`, `ordered`, `present`, `size`, `sub`, `unordered` | graded 0.6666666667 ×12, graded 1.0 ×6, invalid 0.0 ×36 |
    | `questions-project` | `determinant-one.xml` | 2 | `T` | graded 1.0 ×2 |
    | `questions-project` | `rational-equivalence.xml` | 6 | `m`, `n`, `ta` | graded 0.0 ×4, graded 1.0 ×2 |
    | `questions-project` | `numerical-measurement.xml` | 25 | `p`, `q`, `ta_area`, `ta_perimeter` | invalid 0.0 ×25 |
    | `questions-project` | `finite-collections.xml` | 18 | `a`, `ordered`, `unordered` | graded 1.0 ×6, invalid 0.0 ×12 |
    | `questions-project` | `nested-collections.xml` | 6 | `a` | graded 0.6666666667 ×2, invalid 0.0 ×4 |
    | `questions-project` | `python-checker.xml` | 2 | `d` | graded 1.0 ×2 |
    | `questions-project` | `zero-product.xml` | 2 | `ta` | graded 1.0 ×2 |
    | `questions-project` | `hyperbolic-equivalence.xml` | 2 | `ta` | graded 1.0 ×2 |
    | `questions-project` | `polynomial-expansion.xml` | 6 | `a`, `b`, `ta` | graded 0.0 ×4, graded 1.0 ×2 |
    | `questions-project` | `boolean-equivalence.xml` | 2 | `ta` | graded 1.0 ×2 |
    | `questions-project` | `bounded-matrices.xml` | 2 | `M`, `a` | graded 1.0 ×1, invalid 0.0 ×1 |
    | `supplement` | `supplement/input-rules.xml` | 5 | `M` | graded 0.8 ×3, graded 1.0 ×1, invalid 0.0 ×1 |
    | `supplement` | `supplement/score-modes.xml` | 1 | `ta` | graded 1.0 ×1 |
    | `supplement` | `supplement/forbidden-variables.xml` | 6 (new) | `d`, `f`, `k`, `sa`, `ta` | graded 0.0 ×1, graded 1.0 ×5 |

    The new rows are S-01's own question,
    `examples/stack/supplement/forbidden-variables.xml` (question variables
    `k`, `f`, `ta`; feedback variables `d`, `sa`): only its six answers,
    each naming a variable (`ta`, `d`, `sa`, `2ta-ta`, `k*2*x+1`, `d+0*f`),
    so that the diff holds no other row (`golden_stack.ANSWERS_ONLY`).

- Tools for grading changes (docs/goldens.md, "Grading changes"):
  `tools/golden.py update --change NAME` runs every row with `src/` and
  writes what changed, a changed row keeping the legacy code's result as
  `legacy` (what the legacy adapter verifies) and naming the change in
  `changes`; `diff --base REF [--rows]` writes the golden diff;
  `check-changelog --base REF` (CI, on pull requests) holds a pull request to
  the rules: STACK's and math-exercise's rows never change together (H2),
  each changed result names its change, a new MINOR version (0.x), the change
  under "Grading changes" here. `manifest.json` and `PROVENANCE.md` name
  the change and its version.
- `tools/stack_native/check_validation.py` and `validation.php`: STACK's
  own input validation as an oracle (above), with STACK's Moodle emulation
  of its API.
- Test edit: `tests/stack/test_nested_collections.py`'s learner answers
  `[d]`, `[[alias]]` and `{d}` name question variables; they are still
  invalid, now with S-01's message instead of the rule on decimal author
  aliases, which a learner can no longer reach.

## 0.2.0 (20 October 2026)

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
  nor the corpus-page test, which stay with its site), its fixtures, and its
  browser tests of the report's pages (`test_report_ui.py`, run by
  `native-stack.yml` after the report);
  `tools/stack_native/`: its native STACK comparison, compliance report,
  corpus replay and fixture import, and the stack-sympy audit's `dual.py`;
  `reports/stack-compliance/`: the report's Quarto project;
  `.github/workflows/native-stack.yml`: its CI (reusable: stack-sympy's site
  calls it at its pin and publishes the report). The report's browser parity
  runs in Pyodide 0.28.3 (ctm-libs' page runtime, which stack-sympy's worker
  now uses; before: 0.27.2) and installs the engine with the page scripts.
- Golden tables: the STACK tables are verified with ctm_checkers.stack too
  (from `src/`, the wheels, and the page scripts in Pyodide); 25 mutations
  of the STACK engine and its basis checks must fail them
  (`tests/test_mutations.py`; six of them only the course-material table
  reaches), and
  `stack/supplement` (153 rows, recorded with stack-sympy's code) reaches the
  rules that only mutations reached: NumAbsolute's and NumRelative's bounds,
  AlgEquiv's numeric rejection screen, response-tree scores outside [0, 1],
  and input rules (forbidden words in any case, the numerical input's type,
  lowest terms with two negative numbers, and/or precedence in the
  validation's LaTeX, the 64-entry matrix limit). `tests/stack/test_page.py`
  tests the page's calls (`stack/page.py`).
- The corpus baseline (`examples/stack/corpus/baseline.json`) names the
  engine it was recorded with: only its `engine_revision`,
  `adapter_source_sha256` and `python_version` changed.

- The page's call text is ctm-libs' (`MathExerciseRuntime.callCheckers`),
  documented exactly in docs/api.md:
  `import builtins as _ctm_builtins` and then
  `_ctm_builtins.__import__("ctm_checkers.browser", fromlist=["call"]).call(name, _ctm_builtins.globals())`.
  It looks up no name in the page's namespace, which learner code shares (a
  learner's `__import__ = None` stopped every check of math-exercise 0.10.0).
  The install code leaves no name in the namespace: the `_ctm_import` and
  `_ctm_globals` that 0.1.0 (`4bd916d`, in CTM Assessment 0.10.0) left are
  gone (ctm-libs removes them after an install of 0.1.0 and keeps doing so),
  and `browser.call` without `_ctm_request` raises a
  `RuntimeError` naming the call instead of running an empty request.
- STACK golden tables (`tests/golden/stack/`, 5,821 rows in ten tables;
  docs/goldens.md), recorded from stack-sympy `f450bcd` with its own code
  before its engine moves here: STACK's answer-test fixtures through the
  compliance runner, stack-sympy's port regressions and reference cases,
  every example question (import, the cards of stack-sympy's site, variants
  at the site's seeds and, for CTM's own and the course's questions, at 1 to
  3, question tests and generated answers), and the probes of the
  stack-sympy audit with their native verdicts. The legacy
  adapter (`golden.py verify --stack-legacy`, CI on Python 3.9 to 3.13 and in
  Pyodide 0.27.2 and 0.28.3) reproduces every row. The inputs: STACK's
  example questions in `examples/stack/` (their one home from now on,
  stack-sympy's `questions/`) and its fixtures in `tests/stack/`.
- Licences of the STACK test data (AC, 20 October 2026), each with its
  notice in `tests/golden/PROVENANCE.md`, README and `examples/stack/README.md`;
  the code is AGPL-3.0-or-later whatever the licence of a table, and no
  wheel or page script contains test data:
  - `stack/questions-course` (232 rows) is course material, labelled as
    such: the three questions derived from the course ingmat3a_ntnu
    (Andrey Chesnokov), among them S-01's test case
    `course-b-rank-pivots.xml`, under CC BY-SA 4.0 with their source record;
    as in `stack/questions-project`, the checker file they use
    (`examples/stack/matrix-checkers.py`) and the generated answers are
    AGPL-3.0-or-later.
    No other table holds course rows (design §13 item 7 still holds for
    the math tables and for rows generated from course repositories).
  - `stack/questions-helm` (179 rows) and the two HELM questions are
    CC BY-NC 4.0 (NonCommercial), kept as test data only.
  - The CTM-authored example XML keeps CC BY-SA 4.0.
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
