# ctm-checkers: API and packaging

ctm-checkers holds math-exercise's grading code, moved verbatim from
math-exercise 0.10.0 (0.1), and stack-sympy's STACK engine, moved as it was at
stack-sympy `f450bcd` (0.2; consolidation step 2, design in ctm-assessment
`docs/consolidation/2026-10-step2.md`). Every verdict is the same: the golden
tables ([goldens.md](goldens.md)) are reproduced by the built wheels natively
and in Pyodide.

The STACK engine (`ctm_checkers.stack`) comes in a wheel and a page script of
its own, so that pages with math-exercise never carry it (design §13 item 5):

| | ctm-checkers | its STACK engine |
|---|---|---|
| modules | `ctm_checkers` but `ctm_checkers.stack`: `browser`, `core`, `matrix`, `graph`, `testing`, `math_exercise` | `ctm_checkers.stack` |
| wheel (pip: one distribution each) | `ctm_checkers-<version>-py3-none-any.whl` (`ctm-checkers`) | `ctm_checkers_stack-<version>-py3-none-any.whl` (`ctm-checkers-stack`, requires `ctm-checkers==<version>`) |
| page script, global | `ctm-checkers.js`, `CTMCheckers` | `ctm-checkers-stack.js`, `CTMCheckersStack` (after `ctm-checkers.js`) |
| `checkers.json` | `wheel`, `sha256`, `script`, `dependency` | `parts.stack`: `name`, `wheel`, `sha256`, `script`, `dependency` |

With both wheels on `sys.path`, `ctm_checkers/__init__.py` adds the second
one's `ctm_checkers/` to the package (`pkgutil.extend_path`); installed with
pip, both land in one folder. The two engines never import each other (H2).

`ctm_checkers.__version__` is the package version, `ctm_checkers.API` (an
integer, now 1) the level of the contracts below; it rises only for an
incompatible change of `browser.call`, the request and result shapes or an
author contract. Python 3.9 or later; SymPy 1.13 or later (the tables are
recorded with 1.13.3, the version Pyodide ships); NetworkX for graph answers.

## In the page

`_extensions/ctm-checkers/ctm-checkers.js` (HTML dependency `ctm-checkers`,
loaded by ctm-libs) defines `globalThis.CTMCheckers`:

| Field | |
|---|---|
| `name`, `version`, `api` | `ctm-checkers`, the package version, the API level |
| `dependency` | the HTML dependency version: the version of a release (whose content never changes, `tools/released.json`), or for a development version `X.Y.Z.devN+<first 8 hex digits of the wheel's sha256>`, so a changed wheel gets a new path |
| `wheel`, `sha256`, `data` | the wheel's file name, its SHA-256 and the wheel itself (base64) |
| `scriptURL` | the script's own URL (for a worker that loads it with `importScripts`), or `null` |
| `install(py)` | installs the wheel into the Pyodide runtime `py`; returns a promise |

`ctm-checkers-stack.js` (HTML dependency `ctm-checkers-stack`, after
`ctm-checkers.js`; stack-sympy's worker loads both) defines
`globalThis.CTMCheckersStack` with the same fields for the STACK engine's
wheel (`name` `ctm-checkers-stack`, `part` `stack`). Its `install(py)`
installs ctm-checkers first (`CTMCheckers.install`, which must be on the
page at the same version; otherwise it fails naming both), then its wheel:
it checks the SHA-256 and the version of the `ctm_checkers` just installed,
writes the wheel next to the first, puts it on `sys.path` and adds its
`ctm_checkers/` to the package, with the same rules as below (a function,
its own names deleted, no lookup in the page's namespace). A math page
carries `ctm-checkers.js` alone, so the package has no `stack` module there.

`install` uses only `py.globals.set` and `py.runPythonAsync`, the two calls
that every runtime on a page offers, pyodide-interaktiv's worker proxy
included. Its Python checks the SHA-256, writes the wheel to
`/tmp/ctm-checkers/<sha256[:16]>/` with Python's own file I/O, puts it first
on `sys.path` and imports `ctm_checkers` (zipimport); an earlier copy is
replaced. It runs inside a function; the payload and the function, the
globals it uses for itself (`_ctm_` names), are deleted afterwards, so
learner variables are never touched, and it looks up no other name in the
page's namespace (where learner code may have rebound `open` or
`RuntimeError`); it leaves no name there. Each call installs again, with a
payload variable of its own (calls that overlap do not interfere): the
once-per-runtime bookkeeping (and installing again after learner code
removed the library, or after a restart) belongs to ctm-libs' runtime
(`MathExerciseRuntime.ensureCheckers`), which is also where `ctm_checkers`
joins the module prefix that `_ctm_guard` keeps.

### `ctm_checkers.browser.call(name, caller)`

The page sets one global, `_ctm_request` (JSON text), and runs the call text
in the same namespace. The call text is ctm-libs'
(`MathExerciseRuntime.callCheckers`, ctm-libs `docs/api.md`), exactly:

```python
import builtins as _ctm_builtins
_ctm_builtins.__import__("ctm_checkers.browser", fromlist=["call"]).call(name, _ctm_builtins.globals())
```

with `name` written as a JSON string (`"math_exercise.check"`). It looks up
no name in the namespace, which learner code shares and where it may have
rebound `__import__`, `globals`, `builtins` or any `_ctm_` name
(`__import__ = None` stopped every check of math-exercise 0.10.0): an
`import` statement finds the import machinery among the interpreter's
builtins, not in the namespace. Afterwards ctm-libs removes `_ctm_builtins`
(and a request still there) from the namespace. A call whose import fails
(learner code removed `ctm_checkers` from `sys.modules`: `No module named
'ctm_checkers'`) leaves the request where it was, which tells ctm-libs to
install again and repeat the call once.

`call` takes `_ctm_request` out of `caller` (learner code sharing the
namespace sees nothing left behind; without one it raises `RuntimeError`
naming the call), applies the call's admission rule, runs
the handler between `_ctm_guard.snapshot()` and `restore()` when ctm-libs'
guard is installed, and returns `json.dumps(result)`. Exceptions reach the
page as before.

| `name` | Handler | Result |
|---|---|---|
| `math_exercise.check` | `math_exercise.check(request)` | `{"status", "score"}`, or `{"status": "error", "message"}` |
| `math_exercise.check_custom` | `math_exercise.check_custom(request)` | `{"status", "score", "show_score", "feedback", "assessment"}`, or `{"status": "error", "message"}` |
| `stack.validate` | `stack.engine.validate(question, answers, variant=variant)` | `{"ok": true, "result": …}`, or `{"ok": false, "error": …}` for an unsupported question |
| `stack.grade` | `stack.engine.grade(question, answers, variant=variant)` | the same envelope |
| `stack.tests` | `stack.engine.run_question_tests(question, seeds=[variant["seed"]], variants=[variant])` | the same envelope |

The `stack.*` calls are stack-sympy's worker requests (its `worker.js` at
`f450bcd`), moved into `ctm_checkers.stack.page`: the request is
`{"question", "variant", "answers"}` as the card's data holds them, the result
what `json.dumps(…, default=str)` wrote, and any other exception reaches the
page as before. They have no admission rule: STACK's grammar never evaluates
learner text as Python. Since 0.3.0 (S-01) an answer that names a question
variable or a PRT's feedback variable is invalid, with STACK's message for
each name ("Forbidden variable or constant: ta.") and no preview; question
tests still resolve those names. Since 0.5.0 (S-02) only `e`, `pi`, `Pi`,
`PI` and `i` (and `%e`, `%pi`, `%i`) are constants in an author's
expressions, as in STACK; `E` and `I` are variables. A student writes `pi` or
`Pi`: since 0.6.0 (S-13) `PI` is rejected as the wrong case ("Input is case
sensitive: PI is an unknown variable. Did you mean Pi, pi?"). Since 0.6.0 (S-13) an answer follows STACK's rules for its
text, with STACK's messages (`ctm_checkers.stack.student_input`, its data
generated from STACK's own files): no unknown name of three letters or more
(`sinx`, `sin*x`), names in their case (`Sin(x)`, `PI`, `In(x)`), Unicode
letters and symbols replaced as STACK does (`π`, `α`, `−`) and other
characters rejected (`x²`), no decimal comma (`3,5`) and no space between
terms (`2 x`), Maxima's error for `0^0`; the inverse trigonometric functions
(`asin`, …, and STACK's `arcsin` names) are allowed. A question test's inputs
are computed as STACK computes them (`compute_response`): each input's name
stands for its teacher's answer, and the computed value is then validated as a
student's answer by these rules and S-01, or the test fails as invalid.

Statuses: `correct`, `partial`, `wrong`, `not_exact`, `not_form`, `rejected`,
`error` (`core.result.STATUSES`).

Admission (math-exercise's calls): a learner string that contains `__` stops the call
with `ValueError("SyntaxError: unsupported input")` before anything runs. The
learner strings are the answer (`student`, unless `mode` is `string` or
`string_ci`, which are never evaluated) and the response's `raw` values and
those of its `inputs`. Author data (answer keys, checkers) is not restricted.

The request carries the values math-exercise 0.10.0 set as globals, under
their names without `_math_`:

| math-exercise 0.10.0 | Request field |
|---|---|
| `_math_student`, `_math_correct`, `_math_vars`, `_math_mode`, `_math_reject`, `_math_tolerance`, `_math_decplaces`, `_math_sigfigs`, `_math_form` | `student`, `correct`, `vars`, `mode`, `reject`, `tolerance`, `decplaces`, `sigfigs`, `form` (strings) |
| `_math_partial_credit` | `partial_credit` (boolean) |
| `_math_form_credit` | `form_credit` (a finite number; an integral value arrives as `int`, as Pyodide converted it) |
| `_math_response_json` (JSON text) | `response` (the same JSON as a value) |
| `_math_checker` | `checker` |

`check` reads every field but `response` and `checker`; `check_custom` reads
`checker`, `vars` and `response`.

## Python API

```python
ctm_checkers.math_exercise.check(request)          # typed answers: string, set, numeric, equivalent, exact; forms; reject
ctm_checkers.math_exercise.check_custom(request)   # a #| checker: on a response
ctm_checkers.math_exercise.namespace(request=None) # the names a #| checker: sees (below)
ctm_checkers.math_exercise.symbols(vars)           # the symbols a checker receives for the exercise's variables
ctm_checkers.math_exercise.learner_strings(request), admit(request)
ctm_checkers.math_exercise.round_places(x, d), sigfigs_round(x, n), parse_tolerance(spec, ref)   # standard library only
ctm_checkers.math_exercise.authored_questions(path), run_question(options, base)
ctm_checkers.math_exercise.authored.main(argv)     # question-tests.py's command line; returns the exit status
ctm_checkers.core.result.normalize_result(value), STATUSES
ctm_checkers.matrix.assess_basis(matrix, *, axis, target_dimension, belongs, name, space_name="space")
ctm_checkers.graph.graph_from_response(response, *, directed=False)
ctm_checkers.testing.run_tests(check, symbols, tests, *, namespace, base)   # check=None: the namespace's check after the tests ran
```

The STACK engine, moved as it was (its modules and names are stack-sympy's
`stack_sympy` at `f450bcd` under `ctm_checkers.stack`):

```python
ctm_checkers.stack: InvalidAnswer, Node, Unsupported, assignments, canonical_form, evaluate, parse, answer_test
ctm_checkers.stack.importer: import_xml(source, *, python_checkers=None), UnsupportedQuestion
ctm_checkers.stack.engine: instantiate(question, seed=1), validate(question, answers, seed=1, *, variant=None),
    grade(question, answers, seed=1, *, variant=None), run_question_tests(question, seeds=(1,), variants=None)
ctm_checkers.stack.assessment: answer_test(name, student, teacher, options="", *, env=None, raw=None, assumptions=None, python_checkers=None)
ctm_checkers.stack.expressions: parse, evaluate, form_latex, canonical_form, ...   # the bounded STACK grammar
ctm_checkers.stack.checkers, ctm_checkers.stack.checker_api                          # PythonChecker API 1 (author checker files)
ctm_checkers.stack.cli: render(path, question, identifier, count=3, seed=1, review=False, diagnostics=False,
    python_checkers=None) -> the card's HTML; main(argv)
ctm_checkers.stack.page: validate(request), grade(request), tests(request)        # the page's stack.* calls
python -m ctm_checkers.stack.cli render --file F --question NAME --id ID [--variants N] [--seed S] [--review] [--diagnostics] [--python-checkers P]
python -m ctm_checkers.stack.cli test --file F [--question NAME] [--seed S ...] [--python-checkers P]
```

`ctm_checkers.stack.cli` still writes the card's HTML (stack-sympy's
`cli.py`): moving the card's shell into stack-sympy's Lua is left for step 6
(design §13, "Cut"). Author checker files import the shared helpers from
`ctm_checkers.matrix` (`assess_basis`) and the value vocabulary from
`ctm_checkers.stack.checker_api` (stack-sympy: `stack_sympy.basis_helper`,
`stack_sympy.checker_api`).

Importing `ctm_checkers` or `ctm_checkers.math_exercise` imports no SymPy;
the names of `math_exercise` load their module on first use, and
`math_exercise.numeric` uses the standard library only (math-exercise's
variant generator rounds with it and needs only PyYAML).
`math_exercise.authored` imports SymPy when it runs, so its command line
reports a missing SymPy as question-tests.py did ("No module named 'sympy'"),
and stops with one message below Python 3.9.

### The checker namespace

A `#| checker:` runs in a fresh dict per call (`namespace(request)`), with
the names math-exercise 0.10.0's checkers saw in its checker module (the
golden probe `math_exercise/namespace` freezes them and their origins):

- SymPy's names (`from sympy import *`); `parse_expr`,
  `standard_transformations`, `implicit_multiplication_application`,
  `convert_xor`;
- `log10`, `floor` and `gcd` from `math` (they shadow SymPy's `floor` and
  `gcd`, as before);
- `assess_basis`, `graph_from_response`;
- the request's values under their old names: `_math_vars`,
  `_math_response_json` (the response as the page's JSON text) and
  `_math_checker`.

Kept for compatibility, not part of the contract: `__name__`
(`_ctm_math_exercise`), the private helpers `_math_tf`, `_mj` (json), `_mre`
(re), `_split_top`, `_numeric_not_reduced`, `_round_places`,
`_sigfigs_round`, `_parse_tol`, `_canon_form`, `_normalize_custom_result`,
and `_build_locals()` for the request's variables. Not reproduced: the
values of earlier requests that math-exercise 0.10.0's module still held
(page history), and its own machinery (`_math_check`, `_math_check_custom`,
`_math_run`, `_num_equal`, `_learner_strings`, `_MATH_INPUTS`,
`_ctm_guard`).

## At build time

Components run Python with the wheel on `sys.path` (`PYTHONPATH`), so it is
imported from the zip; authors install nothing. A component that grades
STACK questions puts both wheels there (stack-sympy:
`python -m ctm_checkers.stack.cli render …`, as it ran `stack_sympy.cli`). math-exercise's documented
command, `python _extensions/math-exercise/question-tests.py lesson.qmd`
(Quarto: `--stdin`), stays a script that puts the wheel on `sys.path` and
calls `ctm_checkers.math_exercise.authored.main(argv)`, which prints the same
lines and returns the same exit statuses as before. Scripts are run as
scripts, never with `python -m` (that would put the current folder, a page
folder, first on `sys.path`).

## Packaging

`python tools/build.py` writes `_extensions/ctm-checkers/` from `src/`:
`_extension.yml` (an extension that only contributes metadata; authors never
list it), `checkers.json` (name, version, api, dependency, wheel, sha256,
script, and `parts.stack` for the STACK engine's wheel), the two wheels and
their page scripts `ctm-checkers.js` and `ctm-checkers-stack.js`. These files
are generated and committed (marked in `.gitattributes`);
`python tools/build.py --check` (CI) fails when they do not match `src/`. A
wheel is deterministic in content (sorted entries, fixed timestamps and
modes); compressed bytes may differ between zlib builds, so a rebuild keeps
a committed wheel while its contents are current, and the SHA-256 of a
committed wheel identifies what runs. The wheels also install with pip
(`ctm-checkers`, `ctm-checkers-stack`).

A released version never changes. There are no tags (builds pin commits),
so `tools/released.json` records each release: the SHA-256 of its contents
(the wheel's RECORD), of the wheel file and of the page script, and the same
for the STACK engine's wheel (`stack`, from 0.2.0). `build.py`
and `--check` refuse a released version whose code, wheel or script differ
from its entry, and a development version that is not above every release.
A version's dependency path (`site_libs/quarto-contrib/ctm-checkers-<version>/`)
therefore always holds the same file. CI also runs
`build.py --check --released-base <base commit>`: the releases recorded on
the base branch must be recorded unchanged, so a pull request cannot rewrite
a released entry together with the code. The release PR records its version
with `python tools/build.py --release`; the first change after it sets the
next development version (for example `0.1.1.dev0`).

Versions follow semantic versioning; while `0.x`, a release that changes a
verdict (a golden row) or the API is a MINOR release (CHANGELOG.md). Courses
get ctm-checkers through CTM Assessment, which pins a ctm-checkers commit
like every component.
