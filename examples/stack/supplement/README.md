# Supplementary questions for the golden tables

Questions written for ctm-checkers' golden tables (`tests/golden/stack/supplement.jsonl`)
where no example question reaches a rule of the engine: `score-modes.xml`
adds and subtracts branch scores beyond 1 and below 0 (a response tree's
score is clamped to [0, 1]); `input-rules.xml` has an input for each of
the input rules that no example reached: forbidden words in any case, the
numerical input's type, lowest terms with two negative numbers, and/or
precedence in the validation's LaTeX, the 64-entry matrix limit (its
answers: `PROBE_ANSWERS` in tools/golden_stack.py); `forbidden-variables.xml`
(S-01, ctm-checkers 0.3.0) has question variables (`k`, `f`, `ta`) and
feedback variables (`d`, `sa`), and its rows are only its answers that name
them (`ANSWERS_ONLY` in tools/golden_stack.py). From 0.4.0 (the review of
S-01): `forbidden-variables-prts.xml` has two response trees, the second's
feedback variables (`w`, `zz`) separated by a newline (`ANSWERS_ONLY` too);
`teacher-answer-clash.xml`'s teacher's answer uses a feedback variable's
name (`t`), so no student could enter it, and its build stops.
From 0.5.0 (S-02): `constants.xml` has Euler's number and the imaginary
unit next to the variables `E` and `I`. From 0.6.0 (S-13): `input-text.xml`
has an answer for each of STACK's rules for the text of an answer, and the
inverse trigonometric functions in its teacher's answer.
From 0.8.0 (S-05): `numerical-applicability.xml` has one input and three
response trees, NumAbsolute, NumRelative and NumDecPlaces, against the
teacher's answer `pi/4`: answers that are not numbers (a symbol, a complex
number, a list, a set, a matrix, an equation, a logical expression, `inf`)
take the false branch of each tree, a decimal literal is graded by the
number of places (its answers: `PROBE_ANSWERS` in tools/golden_stack.py;
the answer-test rows: `SUPPLEMENT`).
From 0.9.0 (S-10): `checkanswertype.xml` has eight inputs with
`checkanswertype`, one for each type of teacher's answer (an expression,
an equation, a list, a set, a matrix, a disjunction of equations, a logical
expression, a nested list); its answers enter one answer in all of them
(`PROBE_ANSWERS`).
AGPL-3.0-or-later.
