# Golden verdict tables

Every verdict of ctm-checkers is pinned by tables recorded from the code it
replaces, before any code moved (consolidation step 2, design §6 and §13 in
[ctm-assessment `docs/consolidation/2026-10-step2.md`](https://github.com/Erasmus-CTM/ctm-assessment/blob/main/docs/consolidation/2026-10-step2.md)).
A change that alters a verdict shows up as a diff of `tests/golden/`.

## The tables

`tests/golden/math_exercise/`, recorded from math-exercise 0.10.0:

| Table | Rows | What |
|---|---|---|
| `requests-math-exercise.jsonl` | 672 | Every grading call that math-exercise.js makes for the exercises with answer keys on math-exercise's example site: the keys, perturbations of each key (for a custom checker also every key wrong at once), the October 2026 audit's challenge answers, boundary probes of numeric cells (the half-way values next to the key's rounding, answers exactly at, just inside and just outside the tolerance) and every generated variant's fixtures. |
| `custom-probes-math-exercise.jsonl` | 932 | Exercises that decide without answer keys (custom checkers, dynamic matrices) or take their response from a diagram: teacher answers, a fixed probe set per field, the challenge answers, the responses that their authored tests give the checker as the page would send them, and their variants' fixtures. |
| `authored-math-exercise.jsonl` | 33 | Every `#\| tests:` question: its outcome, the result of every `check()` call (other number types than Python's with their type) and the response passed to each, as the page would send it. |
| `sources-math-exercise.jsonl` | 61 | Checker and test sources, stored once by SHA-256. |
| `files/` | 13 | The test files that authored tests name (`#\| tests: _includes/tests/….py`). |
| `namespace.jsonl` | 1 | A probe checker reporting the public names of the `#\| checker:` namespace with their origins and the request values it sees (`_math_response_json`, `_math_vars`, `_math_checker`). |
| `requests-supplement.jsonl` | 88 | Requests for rules the examples do not reach: the reject rule, form credit, every rule and error of the custom result, matrix dimensions, the dunder rule on each kind of learner string, the equivalence and set tolerances, the default numeric tolerance for small keys, the imaginary part and its threshold, `inf`, brackets in set answers, duplicate graph edges and boolean node identifiers, dependent basis vectors, the spelling of numbers in `_math_response_json`. |
| `rounding.jsonl` | 1020 | The rounding rule of the checks (`round_places`, `sigfigs_round`) on a grid of ties, binary noise, signs, magnitudes, integers and non-finite values. |
| `rounding-variants.jsonl` | 561 | The same grid through variants.py's `round_half_up` and `sigfig` (math-exercise's variant generator, which stays in math-exercise and rounds by the same rule). |

The first four were captured by the umbrella's parity harness
(`integration/pyodide-parity/run.cjs --capture`, ctm-assessment PR #14) at
the runtime boundary of math-exercise.js: the request values the page set
and the JSON text the checker returned (or the error it raised), graded in
jsdom under Pyodide 0.27.2 and 0.28.3 with `PYTHONHASHSEED` 0 and `random`
seeded before every call (the umbrella's CI captures again with seed 1 and
requires the same rows). Only math-exercise's own examples (AGPL-3.0-or-later) are
committed here; rows derived from courses and from the umbrella's example site
stay in the umbrella (design §13 item 7). The last three are recorded here
with the same legacy code (`tools/golden.py record`). `PROVENANCE.md` and
`manifest.json` name the commits, runtimes and licences.

### STACK

`tests/golden/stack/`, recorded from stack-sympy's engine at `f450bcd` before
it moved into `ctm_checkers.stack` (design §6.2 and §6.3), with stack-sympy's
own code (`tools/golden.py record --stack-legacy`) on Python 3.9 to 3.13, and
verified with the same code in Pyodide 0.27.2 and 0.28.3. Each row runs one of
the calls of `tools/golden_stack.py`, which also writes the inputs: the
compliance runner on a fixture case (`stack.case`), an answer test
(`stack.answer_test`), and for a question file the import, a frozen variant,
the card the build writes (its SHA-256 and length), the question tests and
one answer set validated and graded, as stack-sympy's build and page worker
run them (`stack.import`, `stack.instantiate`, `stack.card`, `stack.tests`,
`stack.answer`).

| Table | Rows | What |
|---|---|---|
| `compliance.jsonl` | 2303 | Every answer-test row of STACK's own fixtures (`tests/stack/native_compliance/fixtures.json`, STACK `10d3233`) through the compliance report's Python runner; `native` holds STACK's expected score and answer note. |
| `regressions.jsonl` | 170 | stack-sympy's port regression cases (`tests/stack/port_regressions/fixtures.json`). |
| `reference.jsonl` | 65 | The cases stack-sympy compares with native STACK in Maxima (`tests/stack/reference_cases.json`). |
| `questions-project.jsonl` | 1178 | stack-sympy's own example questions (`examples/stack/*.xml`): each file's import; the cards of stack-sympy's site; for every seed the site uses and seeds 1 to 3 (stack-sympy's default card) the variant and the question tests; and answer sets: the teacher's answers, the question tests' inputs and, for the site's first seed and seed 1, for each input its sign, offsets, double, factored, expanded and decimal forms, every question variable's name (S-01) and strings the input rules must handle (empty, `x+`, `sin(`, `2 x`, `x²`, `π`, `3,5`, `__import__('os')`, 1300 characters); also the answers of the audit's leak.py. |
| `questions-library.jsonl` | 1049 | The same for the STACK sample questions (`examples/stack/corpus`, `corrected`, `upstream/algmap-6-1.xml`), with the seeds of the corpus replay (the first three deployed seeds, else 17, 29, 47). |
| `questions-helm.jsonl` | 179 | **NonCommercial test data** (CC BY-NC 4.0, below): the same for the two HELM questions (`examples/stack/upstream`). |
| `questions-course.jsonl` | 232 | **Course material** (CC BY-SA 4.0; the checker file and the answers AGPL-3.0-or-later, below): the same as `questions-project` for the three questions derived from the course ingmat3a_ntnu (`examples/stack/course-*.xml`), among them S-01's test case `course-b-rank-pivots.xml` (`r` and `P` accepted as answers). |
| `probes.jsonl` | 207 | The stack-sympy audit's answer-test probes with STACK's and Maxima's native verdicts (`native`), and its performance probes. |
| `probe-questions.jsonl` | 285 | The audit's question probes (`examples/stack/probes/`) with its answers. |
| `supplement.jsonl` | 159 | Rules that only the mutation tests reached (below): NumAbsolute's strict bound with STACK's 1e-9 guard and NumRelative's inclusive one, for exact and irrational numbers; AlgEquiv's numeric rejection screen (1e-4 margin); response-tree scores beyond [0, 1] (`examples/stack/supplement/score-modes.xml`); the input rules of `examples/stack/supplement/input-rules.xml` (forbidden words in any case, the numerical input's type, lowest terms with two negative numbers, and/or precedence in the validation's LaTeX, the 64-entry matrix limit), with the answer sets of the example questions and the answers in `golden_stack.PROBE_ANSWERS`; S-01's question `examples/stack/supplement/forbidden-variables.xml` (0.3.0): only its six answers that name question and feedback variables, alone, inside an expression, with implied multiplication, twice, and two names at once (`golden_stack.ANSWERS_ONLY`). |

`excluded.json` lists the inputs that run longer than 20 s (S-12:
`sin(exp(exp(exp(5))))`, `sin(x)^99*cos(x)^99` against `(sin(2*x)/2)^99`):
they are not rows until S-12 bounds them. A table holds rows of one kind of
source, under that source's licence (`PROVENANCE.md`).

`questions-helm.jsonl` is licensed CC BY-NC 4.0 (Attribution-NonCommercial),
like the two HELM questions of STACK's sample library it is derived from
(`examples/stack/upstream/HELM-COPYING.txt`); `PROVENANCE.md` gives it its
own licence notice. It is test data only: no wheel or page script contains
it, and the NonCommercial condition does not apply to ctm-checkers' code,
which is AGPL-3.0-or-later. AC decided on 20 October 2026 to keep it,
clearly labelled.

`questions-course.jsonl` is course material, labelled as such in
`PROVENANCE.md` with its provenance and licence notice: its rows are derived
from the three STACK questions that CTM wrote from Andrey Chesnokov's course
ingmat3a_ntnu (`examples/stack/course-*.xml`, with the excerpts and the
source record `course-examples-provenance.json`) and are licensed CC BY-SA
4.0, like those questions; as in `questions-project`, the checker file they
use (`examples/stack/matrix-checkers.py`, whose source the imports of the two
null-space questions hold) and the generated answers are AGPL-3.0-or-later. AC decided on 20 October 2026 that these
committed files have their own table. No other table holds a row of them
(`tests/test_golden_tables.py`), and rows generated from the course
repositories (ctm-demo, ingmat3a) stay in the umbrella (design §13 item 7).

A STACK row stores the result as stack-sympy's worker returns it
(`json.dumps(result, default=str)`); an exception is `{"raised": "<class
name>: <message>"}`, without the module (the move renames
`stack_sympy.importer` to `ctm_checkers.stack.importer`). The inputs name files
of this repository; the legacy adapter runs them with stack-sympy's code,
which finds `ctm_checkers.matrix` (imported by `examples/stack/matrix-checkers.py`)
as its own `stack_sympy.basis_helper` (design §6.3: import shims). No row
differs between Python versions or between native Python and Pyodide.
Rows that a grading change after the move changed keep stack-sympy's result
as `legacy` (below, "Grading changes").

## Rows

One row per line, in canonical JSON (sorted keys, compact separators,
non-ASCII as is), sorted by id; `id` is the first 16 hex digits of the SHA-256
of the row's canonical `{call, input}`:

```json
{"call":"check","id":"…","input":{"_math_correct":"x","_math_mode":"equivalent",…},"output":{"score":1.0,"status":"correct"},"suite":"math_exercise/requests-math-exercise","tags":["keys"]}
```

- `call`: `check` or `check_custom` (math-exercise's two grading calls),
  `authored`, or a rounding function. `input` holds the values as the page
  set them (`_math_*`; a JavaScript number arrives in Python as an `int` when
  it is a safe integer, as Pyodide converts it), sources as
  `{"$source": "<sha256>"}`, numbers that JSON cannot hold as
  `{"$float": "NaN"}`.
- `output`: the result, with numbers spelled as Python wrote them (`1.0`
  stays `1.0`); an error raised to the page is `{"raised": "<last line>"}`.
- `by_python` instead of `output`: one result per Python minor version, for
  results that hold a Python message (error messages change between versions:
  Python 3.9 says "unexpected EOF while parsing" where 3.12 says "invalid
  syntax") or that differ between versions. Captured results come from
  Pyodide 0.27.2 (Python 3.12) and 0.28.3 (Python 3.13); every Python from
  3.9 to 3.13 is also recorded natively with the legacy code (3.12 and 3.13
  give the Pyodide results; 3.10 and 3.11 those of 3.12; 3.9 words 60 parse
  errors differently). Every version CI runs must be present.
- `legacy` and `changes`, on a row that a grading change changed after the
  row was recorded: `legacy` is the legacy code's result (what it was
  recorded with, and what the legacy adapter still verifies), `changes` the
  grading changes that changed it, as the CHANGELOG names them (`["S-01"]`).
  A new row whose legacy result differs from `output` has them too.

## Grading changes

A change of ctm-checkers that changes a verdict changes golden rows, and the
golden diff in its pull request is the evidence (design §6.6):

```sh
# after the change of src/: run every row with it and write what changed
python tools/golden.py update --change S-01 --stack-legacy _ci/stack-sympy
python tools/golden.py diff --base origin/main --rows     # the summary for the PR and the CHANGELOG
python tools/golden.py check-changelog --base origin/main # what CI checks on a pull request
```

`update` runs every row with `ctm_checkers` from `src/` (one Python; then
`verify` on each Python CI runs). A row whose result changes keeps its
recorded result as `legacy` and names the change in `changes`; a row that
gives its legacy result again loses both. For the STACK tables it also
writes the inputs again with today's code (`tools/golden_stack.py`, with the
site pages of the stack-sympy checkout) and adds the rows they add, with
the legacy code's result in a process of its own; it writes nothing when a
row kept per Python version changes or when a table holds a row that
today's inputs no longer give (the inputs depend on the code: such a change
records the table again). `manifest.json` `changes` names each change with
its version.

`check-changelog` (CI, on pull requests): STACK's and math-exercise's
tables never change in one pull request (H2); every changed result names a
new grading change in `changes`; the version is a new MINOR one or above
(0.x); and the CHANGELOG section of that version names each change under
"Grading changes". `diff` writes the rows per table, the transitions of
the results (`graded 1.0 → invalid 0.0`), the changes named, the rows with a
native STACK verdict that now agree or disagree with it and, with `--rows`,
each changed STACK answer row.

Where a change is about STACK's verdict, native STACK checks it (design §9):
answer tests with `tools/stack_native/dual.py` (STACK's answer-test
functions in Maxima), input validation with
`tools/stack_native/check_validation.py` (STACK's own PHP validation of the
golden rows' answers that name question variables; `native-stack.yml`).

## Verifying

```sh
pip install -r ci/requirements.txt         # SymPy 1.13.3, mpmath 1.3.0, NetworkX as Pyodide ships them
git clone https://github.com/Erasmus-CTM/math-exercise _ci/math-exercise
git -C _ci/math-exercise checkout <math-exercise commit in tools/pins.json>
git clone https://github.com/Erasmus-CTM/ctm-assessment _ci/ctm-assessment
git -C _ci/ctm-assessment checkout <ctm-assessment commit in tools/pins.json>
python tools/golden.py verify --adapter legacy --legacy _ci/math-exercise
# the STACK tables with stack-sympy's code:
git clone https://github.com/Erasmus-CTM/stack-sympy _ci/stack-sympy
git -C _ci/stack-sympy checkout <stack-sympy commit in tools/pins.json>
python tools/golden.py verify --adapter legacy --stack-legacy _ci/stack-sympy
```

Any Python from 3.9 to 3.13 verifies every row; another version has no
results of its own in the rows kept per version and says so once.

Authored rows are recorded with the umbrella's own recorder,
`integration/pyodide-parity/authored_record.py`: the harness records the
capture with it, and `golden.py` loads the same file from the ctm-assessment
checkout at the commit in `tools/pins.json` (which also pins its SHA-256), as
`tools/pyodide/verify.cjs` loads the harness's `runtime.cjs` and
`wheels.cjs`. `--umbrella DIR` or `CTM_UMBRELLA` name another checkout of
that commit; by default it is `_ci/ctm-assessment`.

Adapters: `legacy` (below); `wheel` (the built wheels, imported from the
zips as builds import them; `--wheel`, repeatable, also takes a folder that
contains `ctm_checkers`), `src`, and `installed` (in Pyodide, the copy that
the page scripts' install code installed: both for every table,
`ctm-checkers.js` alone for math-exercise's, as on a math page). With ctm-checkers a request goes through
`browser.call` as the page will send it (docs/api.md). `rounding-variants`
runs math-exercise's `variants.py` (`--variants DIR`, a math-exercise
checkout; math-exercise passes its own when it rounds with ctm-checkers);
without it that table is skipped.

The legacy adapter runs math-exercise 0.10.0's own code as the page ran it
(the pin, `905d06f` on math-exercise's `main`, has changes after 0.10.0
elsewhere; its checker library, `question-tests.py` and `variants.py` are
those of 0.10.0, which `import-capture` checks):
the Python array of `math-exercise.js`, decoded as `question-tests.py` decodes
it, installed as the private module `_ctm_math_exercise` and called through
`_math_run` with the request values as the page's globals; authored tests
through `question-tests.py`; the rounding helpers of `variants.py` from that
file.

Inside Pyodide (Node 22; the umbrella's harness modules at the commit in
`tools/pins.json`, after `npm ci` in its `integration/pyodide-parity`;
`verify.cjs` mounts that checkout for `golden.py`):

```sh
node tools/pyodide/verify.cjs --umbrella _ci/ctm-assessment --version 0.28.3 -- verify --adapter legacy --legacy _ci/math-exercise --stack-legacy _ci/stack-sympy
```

CI runs both: `Tests` on Python 3.9, 3.10, 3.11, 3.12 and 3.13 (legacy and
the built wheel), `Pyodide` on 0.27.2 and 0.28.3 (the page script's install
code, then the installed wheel and the legacy code), on every pull request,
weekly and on demand.

## Sensitivity

`tests/test_mutations.py` (CI sets `CTM_MUTATION_TESTS=1`) applies each
mutation below to a copy of `src/ctm_checkers` and requires that the tables
no longer reproduce: the two numeric mutations of the step-2 U1 review on
the captured tables alone, every mutation on the suites recorded here. Rows
that differ (captured tables: 1637 rows; recorded: `rounding`,
`requests-supplement` and `namespace`, 1109 rows):

| Mutation | Captured | Recorded |
|---|---|---|
| `round_places` rounds half to even instead of half up (U1 review) | 6 | 26 |
| the tolerance test `<` instead of `<=` (U1 review; 2 requests in 4 harness cases) | 2 | 1 |
| significant figures one place off | 4 | 85 |
| `round_places` reads 17 digits instead of 15 | 3 | 36 |
| a custom result's `show_score` ignored | 167 | 5 |
| `assess_basis` without its independence factor | 10 | 1 |
| set answers: extra items not counted | 1 | 2 |
| exact mode: unreduced fractions not caught | 1 | 3 |
| `correct` only at a score of exactly 1 | 0 | 1 |
| the checker namespace with SymPy's `floor` and `gcd` | 0 | 1 |
| the dunder rule also on string answers | 0 | 1 |
| `lowest_terms`: unreduced numeric fractions not caught | 0 | 1 |
| `string_ci` without lower-casing | 0 | 1 |
| `_math_response_json` with spaces | 0 | 3 |
| matrix dimensions not checked | 0 | 1 |
| equivalence tolerance 1e-6 instead of 1e-10 | 0 | 1 |
| default numeric tolerance `1e-8 * abs(key)` instead of `1e-8 * max(1, abs(key))` | 0 | 1 |
| numeric mode: imaginary parts not rejected | 0 | 2 |
| `inf` no longer `oo` | 0 | 2 |
| `[` and `{` no longer protect commas in set answers | 0 | 3 |
| undirected graphs: `[1, 2]` and `[2, 1]` not a duplicate | 0 | 1 |
| numeric mode: imaginary parts up to 1e-3 accepted instead of 1e-9 | 0 | 1 |
| graph node identifiers: booleans accepted as integers | 0 | 1 |
| `_math_response_json` writes 1e-7 as `0.0000001` (JSON.stringify: `1e-7`) | 0 | 1 |

The last sixteen are caught by the supplementary requests (and the
namespace probe) only: the examples never reach those rules. The review of
C1 found the last nine with no row at all (six in its first round, three in
its second) and rows were added for them. One more mutation of its first
round, the reject rule comparing expressions instead of their text, changes
no verdict SymPy can produce here and is not listed.

Mutations of the STACK engine must fail the STACK tables (the test stops at
the first row that differs). Rows that differ in all (of 5,827), by table:

| Mutation | Rows | Tables |
|---|---|---|
| NumAbsolute: `<=` instead of `<` at its bound (exact numbers) | 1 | supplement |
| NumAbsolute without STACK's 1e-9 guard (exact numbers) | 6 | compliance 1, probes 2, supplement 3 |
| NumRelative: `<` without its 1e-9 factor (exact numbers) | 15 | compliance 6, probes 3, questions-helm 2, supplement 4 |
| NumAbsolute without the guard (irrational numbers) | 1 | supplement |
| NumRelative: `<` without the factor (irrational numbers) | 1 | supplement |
| NumDecPlaces rounds the teacher's value half up instead of half to even | 10 | probes |
| AlgEquiv's numeric screen with a 1e-2 margin instead of 1e-4 | 2 | supplement |
| Sets: no `ATSets_duplicates` note | 7 | compliance 3, probes 1, regressions 3 |
| response trees: `+` sets the branch score instead of adding it | 42 | probe-questions 33, questions-library 2, supplement 7 |
| response trees: scores not clamped to [0, 1] | 16 | supplement |
| question tests: no penalty for a wrong first attempt | 138 | questions-project 60, questions-library 59, questions-helm 1, questions-course 12, probe-questions 3, supplement 3 |
| `forbidfloat` ignored | 11 | questions-library 8, questions-helm 1, questions-course 2 |
| the 1,200-character input limit raised to 1,400 | 104 | questions-project 41, questions-library 31, questions-helm 7, questions-course 8, probe-questions 11, supplement 6 |
| the card's JSON without `<` escaped | 46 | questions-project 16, questions-library 25, questions-helm 2, questions-course 3 |
| forbidden words compared with their case | 1 | supplement |
| lowest terms: two negative numbers accepted | 1 | supplement |
| a numerical input accepts a non-number | 1 | supplement |
| the matrix limit raised from 64 to 65 entries | 1 | supplement |
| the validation's LaTeX with `or` binding tighter than `and` | 82 | supplement |
| `assess_basis` without its independence factor (also on the recorded math tables, above) | 16 | questions-course |
| `assess_basis`: dependent vectors not marked | 20 | questions-course |
| `assess_basis`: a zero vector counted as a basis vector | 16 | questions-course |
| `assess_basis` without its coverage factor | 8 | questions-course |
| the model answer `nullspace_basis(A)` gives a column-space basis | 75 | questions-course |
| a PythonChecker's assessment (the vector colours) dropped | 64 | questions-course |
| S-01: question variables not forbidden | 370 | questions-project 127, questions-library 140, questions-helm 64, questions-course 16, probe-questions 13, supplement 10 |
| S-01: feedback variables not forbidden | 3 | supplement |
| S-01: only an answer that is the name itself is forbidden, not a name inside it | 3 | supplement |
| S-01: only the first forbidden name in the message | 1 | supplement |
| S-01: another message than STACK's | 372 | questions-project 127, questions-library 140, questions-helm 64, questions-course 16, probe-questions 13, supplement 12 |

Since 0.3.0 (S-01) some answers that reached a rule name a question variable
and stop at validation, so five mutations above change fewer rows than in
0.2.0 (NumRelative 16, `+` 48, the clamp 17, the numerical type 2, the
colours 66); each is still caught. Only `supplement`'s
`forbidden-variables.xml` reaches the second to fourth S-01 mutations.

The rows of `supplement` were added for the first seven and for the five
input rules after the card's JSON: the tables recorded first reached no row
of those rules (NumAbsolute's guard and NumRelative's bound only for exact
numbers, as the compliance runner's fixtures do; the five input rules, found
by the review of C3, only pytest or nothing reached). Only `questions-course`
reaches the last six: the basis checks of a STACK question (`assess_basis`
through a PythonChecker, `nullspace_basis`, the colours), which no other
STACK question meets with a dependent, zero or incomplete answer. Two
mutations of the page's calls change no row and no answer, so no test can catch them: `stack.tests` with `seeds=[1]` (the
engine's `run_question_tests` uses the card's variant and ignores `seeds`
when it gets variants) and math-exercise's admission rule on the `stack.*`
calls (it reads math-exercise's request fields, which a STACK request does
not have). `tests/stack/test_page.py` catches the others: the envelope for
every exception, and a variant of seed 1 instead of the card's.

## Refreshing the capture

When the umbrella's harness grades more (new probes, new examples), take its
capture and import it with one command:

```sh
# in ctm-assessment: build the corpora and capture (docs/development.md there),
# or download the artifact goldens-export of its workflow "Pyodide parity and goldens"
node integration/pyodide-parity/run.cjs … --capture /tmp/goldens

# here, with Python 3.13 and each other Python version that CI tests (all with ci/requirements.txt):
python tools/golden.py import-capture /tmp/goldens --math-exercise ~/math-exercise \
    --record-with python3.9 --record-with python3.10 --record-with python3.11 --record-with python3.12
```

`import-capture` takes a capture folder (it reads `export/` with its own
manifest) or the artifact (the `export/` folder, or its zip), refuses files of
any corpus not marked for export, checks that math-exercise's checker library,
`question-tests.py` and `variants.py` at the captured commit are those of the
legacy pin (`tools/pins.json`; the checkout must contain both commits),
replaces the tables, copies the files that authored tests name, records the
supplementary suites and every Python version's results with the legacy code,
and writes `manifest.json` and `PROVENANCE.md`. The authored rows hold what
the harness's recorder (`authored_record.py`, above) records around each
`check()` call. Recording them again with the legacy code and the recorder at
the pin stops the import on any row it does not reproduce, so a capture taken
with another recorder shows there: move the pin (`tools/pins.json`, the
commit and `authored_record_sha256`) to the capture's umbrella commit when its
recorder changed. A row that today's code grades
differently on another platform is kept per version and reported (a parity
finding); a result that differs for a version already in the table stops the
import.

## What the tables do not cover

- Exercises the harness cannot grade: a diagram cell without authored tests or
  fixtures; matrix inputs at shapes other than the default; authored responses
  that are not JSON.
- Checker branches that neither the probes, the challenge answers, the
  authored responses nor the supplementary requests reach.
- Page history: each row runs on its own request. math-exercise 0.10.0 kept
  the values of earlier requests in its module, where a custom checker could
  see them; ctm-checkers does not reproduce them (design §2.3).
- What a checker prints, timing, and the interpreter guard of ctm-libs
  (`_ctm_guard`), which protects the page around each call.
