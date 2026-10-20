# Supplementary questions for the golden tables

Questions written for ctm-checkers' golden tables (`tests/golden/stack/supplement.jsonl`)
where no example question reaches a rule of the engine: `score-modes.xml`
adds and subtracts branch scores beyond 1 and below 0 (a response tree's
score is clamped to [0, 1]); `input-rules.xml` has an input for each of
the input rules that no example reached: forbidden words in any case, the
numerical input's type, lowest terms with two negative numbers, and/or
precedence in the validation's LaTeX, the 64-entry matrix limit (its
answers: `PROBE_ANSWERS` in tools/golden_stack.py). AGPL-3.0-or-later.
