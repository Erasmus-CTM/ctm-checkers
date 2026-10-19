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
| `requests-supplement.jsonl` | 69 | Requests for branches the examples do not reach: the reject rule, form credit, every rule and error of the custom result, matrix dimensions, the dunder rule on each kind of learner string. |
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
  Pyodide 0.27.2 (Python 3.12) and 0.28.3 (Python 3.13); Python 3.9, which has
  no Pyodide build, is recorded natively with the legacy code. Every version
  CI runs must be present.

## Verifying

```sh
pip install -r ci/requirements.txt         # SymPy 1.13.3, mpmath 1.3.0, NetworkX as Pyodide ships them
git clone https://github.com/Erasmus-CTM/math-exercise _ci/math-exercise
git -C _ci/math-exercise checkout <math-exercise commit in tools/pins.json>
python tools/golden.py verify --adapter legacy --legacy _ci/math-exercise
```

Adapters: `legacy` (below); `wheel` (the built wheel, imported from the zip
as builds import it; `--wheel` also takes a folder that contains
`ctm_checkers`), `src`, and `installed` (in Pyodide, the copy that the page
script's install code installed). With ctm-checkers a request goes through
`browser.call` as the page will send it (docs/api.md). `rounding-variants`
runs math-exercise's `variants.py` (`--variants DIR`, a math-exercise
checkout; math-exercise passes its own when it rounds with ctm-checkers);
without it that table is skipped.

The legacy adapter runs math-exercise 0.10.0's own code as the page ran it:
the Python array of `math-exercise.js`, decoded as `question-tests.py` decodes
it, installed as the private module `_ctm_math_exercise` and called through
`_math_run` with the request values as the page's globals; authored tests
through `question-tests.py`; the rounding helpers of `variants.py` from that
file.

Inside Pyodide (Node 22; the umbrella's harness modules at the commit in
`tools/pins.json`, after `npm ci` in its `integration/pyodide-parity`):

```sh
node tools/pyodide/verify.cjs --umbrella _ci/ctm-assessment --version 0.28.3 -- verify --adapter legacy --legacy _ci/math-exercise
```

CI runs both: `Tests` on Python 3.9, 3.12 and 3.13 (legacy and the built
wheel), `Pyodide` on 0.27.2 and 0.28.3 (the page script's install code, then
the installed wheel and the legacy code; on changed paths, weekly in full and
on demand).

## Sensitivity

`tests/test_mutations.py` (CI sets `CTM_MUTATION_TESTS=1`) applies the two
numeric mutations of the step-2 U1 review to a copy of `src/ctm_checkers` and
requires that the tables fail, the captured tables alone included:

| Mutation | Captured tables (1637 rows) | Recorded suites (`rounding`, `requests-supplement`) |
|---|---|---|
| `round_places` rounds half to even instead of half up | 6 rows differ | 26 rows differ |
| the tolerance test `<` instead of `<=` | 2 rows differ (4 cases of the harness: the same two requests in two variants) | 1 row differs |

## Refreshing the capture

When the umbrella's harness grades more (new probes, new examples), take its
capture and import it with one command:

```sh
# in ctm-assessment: build the corpora and capture (docs/development.md there),
# or download the artifact goldens-export of its workflow "Pyodide parity and goldens"
node integration/pyodide-parity/run.cjs … --capture /tmp/goldens

# here, with Python 3.13 and each other Python version that CI tests (all with ci/requirements.txt):
python tools/golden.py import-capture /tmp/goldens --math-exercise ~/math-exercise \
    --record-with python3.9 --record-with python3.12
```

`import-capture` takes a capture folder (it reads `export/` with its own
manifest) or the artifact (the `export/` folder, or its zip), refuses files of
any corpus not marked for export, checks that math-exercise's checker library,
`question-tests.py` and `variants.py` at the captured commit are those of the
legacy pin (`tools/pins.json`; the checkout must contain both commits),
replaces the tables, copies the files that authored tests name, records the
supplementary suites and every Python version's results with the legacy code,
and writes `manifest.json` and `PROVENANCE.md`. The authored rows hold what
the harness records around each `check()` call (worker.cjs, `AUTHORED`);
`golden.py` records it the same way (`AUTHORED_WRAP`, `_ctm_plain`,
`_ctm_page_shaped`), and recording with the legacy code during the import
stops on any row it does not reproduce, so a change of the harness's
recording shows there. A row that today's code grades
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
