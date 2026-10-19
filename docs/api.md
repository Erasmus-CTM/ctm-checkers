# ctm-checkers: API and packaging

ctm-checkers 0.1.0 holds math-exercise's grading code, moved verbatim from
math-exercise 0.10.0 (consolidation step 2; design in ctm-assessment
`docs/consolidation/2026-10-step2.md`). Every verdict is the same: the golden
tables ([goldens.md](goldens.md)) are reproduced by the built wheel natively
and in Pyodide. STACK's engine follows in 0.2.0.

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
| `dependency` | the HTML dependency version: the version, or for a development version `X.Y.Z.devN+<first 8 hex digits of the wheel's sha256>` |
| `wheel`, `sha256`, `data` | the wheel's file name, its SHA-256 and the wheel itself (base64) |
| `install(py)` | installs the wheel into the Pyodide runtime `py`; returns a promise |

`install` uses only `py.globals.set` and `py.runPythonAsync`, the two calls
that every runtime on a page offers, pyodide-interaktiv's worker proxy
included. Its Python checks the SHA-256, writes the wheel to
`/tmp/ctm-checkers/<sha256[:16]>/` with Python's own file I/O, puts it first
on `sys.path` and imports `ctm_checkers` (zipimport); an earlier copy is
replaced. It runs inside a function; the payload and the function, its only
globals (`_ctm_` names), are deleted afterwards, so learner variables are
never touched. Each call installs again: the once-per-runtime bookkeeping
(and installing again after learner code removed the library, or after a
restart) belongs to ctm-libs' runtime, which is also where `ctm_checkers`
joins the module prefix that `_ctm_guard` keeps.

### `ctm_checkers.browser.call(name, caller)`

The page sets one global, `_ctm_request` (JSON text), and runs

```python
__import__("ctm_checkers.browser", fromlist=["call"]).call("math_exercise.check", globals())
```

`call` takes `_ctm_request` out of `caller` (learner code sharing the
namespace sees nothing left behind), applies the call's admission rule, runs
the handler between `_ctm_guard.snapshot()` and `restore()` when ctm-libs'
guard is installed, and returns `json.dumps(result)`. Exceptions reach the
page as before.

| `name` | Handler | Result |
|---|---|---|
| `math_exercise.check` | `math_exercise.check(request)` | `{"status", "score"}`, or `{"status": "error", "message"}` |
| `math_exercise.check_custom` | `math_exercise.check_custom(request)` | `{"status", "score", "show_score", "feedback", "assessment"}`, or `{"status": "error", "message"}` |

Statuses: `correct`, `partial`, `wrong`, `not_exact`, `not_form`, `rejected`,
`error` (`core.result.STATUSES`).

Admission (both calls): a learner string that contains `__` stops the call
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
ctm_checkers.math_exercise.learner_strings(request), admit(request)
ctm_checkers.math_exercise.round_places(x, d), sigfigs_round(x, n), parse_tolerance(spec, ref)   # standard library only
ctm_checkers.math_exercise.authored_questions(path), run_question(options, base)
ctm_checkers.math_exercise.authored.main(argv)     # question-tests.py's command line; returns the exit status
ctm_checkers.core.result.normalize_result(value), STATUSES
ctm_checkers.matrix.assess_basis(matrix, *, axis, target_dimension, belongs, name, space_name="space")
ctm_checkers.graph.graph_from_response(response, *, directed=False)
ctm_checkers.testing.run_tests(tests, namespace, symbols, base)
```

Importing `ctm_checkers` or `ctm_checkers.math_exercise` imports no SymPy;
the names of `math_exercise` load their module on first use, and
`math_exercise.numeric` uses the standard library only (math-exercise's
variant generator rounds with it and needs only PyYAML).

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
imported from the zip; authors install nothing. math-exercise's documented
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
script), the wheel and `ctm-checkers.js`. These files are generated and
committed (marked in `.gitattributes`); `python tools/build.py --check` (CI)
fails when they do not match `src/`. The wheel is deterministic in content
(sorted entries, fixed timestamps and modes); compressed bytes may differ
between zlib builds, so a rebuild keeps the committed wheel while its
contents are current, and the SHA-256 of the committed wheel identifies what
runs. The wheel also installs with pip.

Versions follow semantic versioning; while `0.x`, a release that changes a
verdict (a golden row) or the API is a MINOR release (CHANGELOG.md). Courses
get ctm-checkers through CTM Assessment, which pins a ctm-checkers commit
like every component.
