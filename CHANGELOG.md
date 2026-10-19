# Changelog

Versions follow semantic versioning; while `0.x`, a release that changes any
verdict (a golden row) or the API is a MINOR release, everything else a PATCH
release. Every grading change is listed under "Grading changes" with the
finding or decision it implements, its test and the summary of its golden
diff (docs/goldens.md).

## Unreleased

- Golden verdict tables for math-exercise, recorded from math-exercise 0.10.0
  before any code moves: every grading call of math-exercise's own examples as
  the umbrella's parity harness captured it at the runtime boundary, the
  authored question tests, the `#| checker:` namespace and the rounding rule.
  `tools/golden.py` verifies them against the legacy code or ctm-checkers, in
  native Python and in Pyodide.
