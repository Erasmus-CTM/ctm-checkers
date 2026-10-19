# ctm-checkers

The Python checker library of [CTM Assessment](https://github.com/Erasmus-CTM/ctm-assessment):
the grading code shared by math-exercise and stack-sympy, run in the browser
(Pyodide) and at build time. It is an internal library: course authors install
CTM Assessment, which includes it.

Being set up in the October 2026 consolidation (step 2); see
[ctm-assessment `docs/consolidation/`](https://github.com/Erasmus-CTM/ctm-assessment/tree/main/docs/consolidation).

## Development

- `tests/golden/`: golden verdict tables recorded from math-exercise 0.10.0
  before any code moved; `tools/golden.py` verifies them natively and
  `tools/pyodide/verify.cjs` inside Pyodide ([docs/goldens.md](docs/goldens.md)).
- `tools/pins.json`: the commits CI uses (the legacy sources, the umbrella's
  Pyodide harness modules).
- Tests: `pip install -r ci/requirements.txt`, then `pytest tests`.

## Licence

GNU Affero General Public License, version 3 or (at your option) any later
version (AGPL-3.0-or-later); see [LICENSE](LICENSE).
