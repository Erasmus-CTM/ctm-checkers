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

`ctm_checkers.__version__` is the package version, `ctm_checkers.API` the
contract level (now the string `"1.1"`). A major level marks an incompatible
change; a minor level adds contracts. ctm-libs accepts an API-1 consumer
with 1.1, while ctm-stack requires `ctm.checkers.require('ctm-stack', '1.1')`.
Python 3.9 or later; SymPy 1.13 or later (the tables are
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

### STACK preparation and presentation (API 1.1)

`python -m ctm_checkers.stack.cli prepare --file questions.xml --question NAME
--id ID --variants N --seed SEED` writes one JSON payload, version 2. It
contains `common.inputs`, `common.qtests`, `common.checker` (null until H1),
`backend.{id,planSchema,stackRevision,runtimeHash,question}` and
`variants[].{n,id,hash,display,plan}`. Question-level response trees and
variant plans are opaque to the card controller. The hash binds the canonical
frozen plan; it does not approve a variant. V5 owns proposals and approved
manifest selection. The component's Lua filter owns the card shell, labels,
descriptor and safe JSON-script embedding. The old `render` command remains
for one documentation-site transition release.

Production `prepare` and ordinary `render` reject author names shared between
question-variable assignments, student inputs and a PRT's feedback variables
before producing a plan or card. The error names the source, question, name
and both scopes. Intentional reassignment within one scope and reuse of a
feedback-local name in separate PRTs remain valid; duplicate inputs are already
invalid on import. Explicit `render --diagnostics` may show an inert author
alert, never an active plan. This preflight does not change legacy
`instantiate`, `validate` or `grade` behavior.

`stack.validate`, `stack.grade` and `stack.tests` still return normal CAS
results for invalid learner input. Unsupported questions and malformed
prepared plans return `ok: false` with the existing string `error` and additive
`errorDetail: {kind: 'author', code: 'stack_question_error', message,
args: {question, location, reason}}`. Keeping the string preserves the retained
`render` consumer's diagnostic. Unexpected exceptions propagate to the
adapter as runtime failures. An author error never authorizes a restart.

Messages have `{code, args, text}`; `text` is the English fallback.
Validation adds `message`; response-tree output can add `messages`.
Response-tree `feedbackParts` preserves the exact ordered presentation boundary:
each part is either `{html: authoredCASTextHTML}` or `{message: {code,args,text}}`.
The controller localizes only message parts and keeps authored HTML in place,
even when authored text is identical to a stock message. Joining the original
English parts with spaces reproduces the retained `feedback` HTML exactly;
localization never searches or replaces substrings in that legacy HTML.
Existing STACK answer-note keys are reused where available. Unknown keys
retain the English fallback. `ATSets_wrongentries` and
`ATSets_missingentries` carry `args.elements: [{text, latex}]` rather than
interpolated Python representations. Presentation escapes argument text and
LaTeX before inserting it into HTML. None of these fields changes a score,
validity, response-tree branch or answer note. The S-20 display correction
escapes answer-test feedback and renders collection values as LaTeX; authored
CASText remains the separately validated HTML path.

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

The STACK engine and H1 custom checker contract:

```python
ctm_checkers.stack.importer: import_xml(source, *, checker=None, checker_value=1, tests=None)
ctm_checkers.stack.engine: instantiate(question, seed=1), validate(question, answers, seed=1, *, variant=None),
    grade(question, answers, seed=1, *, variant=None), run_question_tests(question, seeds=(1,), variants=None)
ctm_checkers.stack.check: check(request), preflight(question, variants)
ctm_checkers.stack.page: validate(request), grade(request), tests(request), check(request)
ctm_checkers.stack.cli: prepare(..., checker=None), render(..., checker=None), main(argv)
python -m ctm_checkers.stack.cli prepare --file F --question NAME --id ID [--checker SOURCE_FILE]
python -m ctm_checkers.stack.cli test --file F [--question NAME] [--seed S ...] [--checker SOURCE_FILE]
```

`ctm-stack` owns the card shell in Lua. `prepare` returns its payload; `render`
remains for the documentation-site transition. Block `checker:` source defines
`check(response, symbols)` and uses the shared `core.custom.execute_checker`,
math-exercise namespace and score normalizer. An implicit `checker` response
tree has weight `checker-value` (default 1). XML `PythonChecker` nodes with
`{"checker":"check"}` use the same function as a predicate, true only at
normalized status `correct`; node values are available in `response["node"]`.
Other supported names select `ctm_checkers.matrix` library predicates.

`stack.check` accepts a text-only backend request: `checker`, ordered `inputs`
with `type`, `raw`, `canonical`; `variables`, `teacher`, `assumptions`, `variant`
(`n`, `id`, `hash`) and optional `node` (`sans`, `tans`, JSON `options`). Inputs
use their admitted names. A node carries that input name in `sans`, evaluated
author text in `tans`, and the complete XML testoptions object in `options`
(`checker` and optional inner `options`). Both custom and library predicates
enter through this call. The author function receives the decoded `sans` and
`tans` values and only the inner literal options object.
Inputs
must already be validated by the backend. SymPy prints `canonical` from its
parsed written operation tree, before the planned shared JS admission.
The printer preserves precedence without adding depth to flat expressions;
canonical decoding allows bounded expansion for inserted multiplication
symbols. Learner admission retains its original size, token and depth limits.
CTM STACK's author parser decodes exact values, including matrices. Teacher
answers and variables named by the source must decode; an unused unsupported
Maxima variable may remain text. This is a contract for Maxima's continuation,
not a Maxima backend implementation.

The checker receives `kind`, positional `raw` and `expressions`, named `answers`,
`teacher`, `variables`, `inputs` and `variant`. Matrix inputs include `rows`,
`cols`, `expressions` and a SymPy `matrix`. Results accept bool, a score in
[0,1], or the math-exercise result dictionary. `valid: false` denotes an invalid
attempt with feedback and no score or assessment. Valid matrix assessments are
keyed by input name. Exceptions are author errors and retain the worker session.
The browser entry returns the same `{ok,result}` / author-error envelope as
other STACK calls. No runtime is restarted by this handler.

`python-checkers:`, the `CHECKERS` registry, `stack.checkers` and
`stack.checker_api` are removed without aliases. Frozen golden-row metadata
retains its original fixture names solely to compare the old and new engines.
Declarative `tests:` uses `ctm_checkers.testing.run_declarative` and the real
STACK grader for every generated/replayed variant; failures name the question
and test and stop publication.

Importing `ctm_checkers` or `ctm_checkers.math_exercise` imports no SymPy;
the names of `math_exercise` load their module on first use, and
`math_exercise.numeric` uses the standard library only (math-exercise's
variant generator rounds with it and needs only PyYAML).
`math_exercise.authored` imports SymPy when it runs, so its command line
reports a missing SymPy as question-tests.py did ("No module named 'sympy'"),
and stops with one message below Python 3.9.

### The checker namespace

The engine-neutral `core.custom.execute_checker` owns execution and the existing
custom-result normalization. Math prepares the response, trusted context and
namespace, and keeps its existing error handling. This extraction adds no
STACK adapter, author syntax or scoring behavior.

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

## Generated practice keys

`math_exercise.compute_key(request)` (also the browser call of that name) accepts
`{recipe, answer, vars, mode}` and returns `{key, computed: true}`. It raises on
an invalid recipe, a missing component or disagreement with the model answer.
Comparison uses the existing `math_exercise.check`; authored grading is unchanged.
`math_exercise.admit_generated` and `generated: true` on `check`/`check_custom`
apply the same restricted mathematical admission to model-derived answers.

`math_exercise.bind_data(request)` (also a browser call) binds generated givens
to an authored custom checker. The request is `{context, names, data, vars}`:
the original exact question context, the variables the author opened to
generation (math-exercise's `similar-data`), model text for exactly those names
and the exercise's variables. Each text goes through the same restricted
grammar and must keep the kind of the original value: an exact real number
stays a finite real number; an expression stays a non-constant expression in
the declared variables (with the original Symbols and their assumptions).
Values outside the exact-value codec, for example `cot`, are rejected. It
returns `{context, latex}`: the bound context (`variant: null`, teacher answers
`null`, since they belong to the original problem) and the LaTeX of each bound
value for the question text (natural logarithms as `\ln`). Matrix variables
keep their own contract.

Arguments are explicit SymPy mathematical text (`2*x`, `sin(x)`), interpreted
with a positive AST grammar. Declared variables and a curated set of mathematical
functions/constants are admitted; Python source, attributes, strings, arbitrary
calls, dunders, imports and comprehensions are rejected. Inputs, powers, orders,
matrices and selectors are bounded. This is not a route for generated checker code.

| Operation | Recipe arguments besides `op` and optional `select` |
|---|---|
| value, simplify, expand, factor | `expr` |
| diff | `expr`, declared `var`, optional integer `order` (1–12) |
| integrate | `expr`, `var`; optional `lower` and `upper` together |
| limit | `expr`, `var`, `point`, optional `direction` (`+`, `-`, `+-`) |
| series | `expr`, `var`, optional `point` (0) and `order` (6); returns the polynomial without the Order term |
| solve | `expr` (equation, zero expression or list), `var` or `variables` |
| det, inv, transpose, rank, rref, nullspace, eigenvals, norm | matrix `expr` |
| matmul, dot, cross | matrix `left` and `right` |

`select` is a list of bounded array indices or dictionary keys, never an attribute
path or Python expression. Matrices become row arrays; rref is `{matrix, pivots}`;
eigenvalues are sorted `{value, multiplicity}` records; solve returns solutions
sorted by the declared variable order, with variable-name keys. Nullspace returns
SymPy's ordered column vectors. Select one scalar for each existing answer field,
e.g. `["matrix", 0, 1]` for an rref entry, `[0, "multiplicity"]` for an eigenvalue's
multiplicity, or `[0, "x"]` for a solve component. A flat list may supply `set` mode.
Selection of a witness does not establish uniqueness: use a compatible trusted
authored checker when alternative answers are mathematically valid.

Generated-practice Check requests from the learner UI carry `learner: true`
alongside `generated: true`. Their learner response uses the original checker's
notation transformations (implicit multiplication/function application, powers,
and factorial notation) after token admission. Model keys and saved rejection
expressions still pass strict mathematical AST admission; model/candidate/key
computation requests never set the learner flag. Python names, strings, dunders
and attribute access remain excluded. The same grading options determine both
original and generated results.

### Native declarative test result verification

`stack.test-results` accepts `tests` (1–100 shared declarative cases), unique
input `fields`, a current `candidate: {id, hash}`, and one computed grading
`results` mapping per case. Each result must carry the same candidate, its
unique declaration `name`, the complete current `declaration`, a supported status and a finite numeric score.
Names/order and candidate identity must match; stale/other-seed/reordered
observations are rejected. The candidate is echoed in the envelope result and
every verified case. It returns
`{passed: true, results: [...]}` in the ordinary STACK envelope after the common
expectation verifier passes. Assertion/shape failures are author errors. It
never evaluates authored answer expressions or calls a mathematical grader;
resolving inputs and grading each case belong to the native backend. It is a
test/evidence operation, not a learner grading endpoint.
