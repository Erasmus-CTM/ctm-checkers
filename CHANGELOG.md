# Changelog

Versions follow semantic versioning; while `0.x`, a release that changes any
verdict (a golden row) or the API is a MINOR release, everything else a PATCH
release. Every grading change is listed under "Grading changes" with the
finding or decision it implements, its test and the summary of its golden
diff (docs/goldens.md).

## 0.6.0 (21 October 2026)

STACK: an answer follows STACK's rules for its text, with STACK's messages
(S-13; step-2 design §9, order 3), and the inverse trigonometric functions
are allowed. A MINOR release (verdicts change); math-exercise's tables do
not change (H2). The STACK wheel carries STACK's data for these rules
(`ctm_checkers/stack/stack_data.py`, GPL-3.0-or-later, with its copyright
notice and the GPL's text; the wheel's licence is `AGPL-3.0-or-later AND
GPL-3.0-or-later`): it grows from 65 to 105 kB, its page script
`ctm-checkers-stack.js` from 91 to 145 kB; math pages do not load it.

### Grading changes

- **S-13: STACK's input rules.** Before, the engine accepted what STACK
  rejects (`sinx` and other names of three letters or more, `sin*x`,
  `Sin(x)` and `SQRT(x)`, whose names it lower-cased, `0^0` as 1) and
  rejected with technical text what STACK converts or explains (`x²`, `π`:
  "Unexpected character …"; `3,5`, `2 x`: "Unexpected trailing text");
  `atan(1)` got "use atan*(...) for multiplication". Now
  `ctm_checkers.stack.student_input` applies STACK's own rules before an
  answer is parsed, with STACK's messages (STACK `10d3233`:
  `maximaparser/corrective_parser.php`,
  `cas/parsingrules/998_security.filter.php`, `cassecurity.class.php`):
  - Unicode: the letters and symbols STACK replaces are replaced (`π`: pi,
    `α`: alpha, `−`: -, `×`: *); any other character outside STACK's set
    is "CAS commands may not contain the following characters: ²." (the
    first one, as STACK).
  - Spaces between two terms (`2 x`, `sin x`, `(x+1) (x-1)`, `sin (x)`):
    "Illegal spaces found in expression 2_x." (with or without
    insertstars), and for a trigonometric function STACK's hint.
  - A comma between terms (`3,5`): STACK's message on decimal commas.
  - Names: a student may use a name of one or two letters (not a function
    name: `ln*x` is forbidden), one ending in a digit, or one STACK knows
    (`alpha`, `theta`, `pi`, `inf`, …); any other is "Forbidden variable
    or constant: sinx." (`sin*x`: sin), part by part at underscores
    (`ta_perimeter`: perimeter; before: ta_perimeter). Case:
    `Sin(x)`, `SQRT(x)`, `Diff(x)` ("Input is case sensitive: Sin is an
    unknown function. Did you mean sin?"), `PI`, `XI`, `ALPHA` (… unknown
    variable …), `In(x)` (STACK's "Lima November" message). The names of
    question and feedback variables are forbidden (S-01).
  - `0^0` (also `(x-x)^0`, `0.0^0`): Maxima's error "expt: undefined: 0^0",
    STACK's validation error (SymPy's 0**0 is 1).
  - The inverse trigonometric functions (`asin`, `acos`, `atan`, `asec`,
    `acsc`, `acot` and their hyperbolic forms) for students and authors,
    and STACK's other names for them (`arcsin`, `arsinh`, `arccosec`, …),
    which STACK replaces.
  - **Question tests** (AC's decision of 21 October): their inputs are
    computed as STACK computes them (`questiontest.php`, `compute_response`)
    and the computed value is a student's answer. Every input's name is
    bound to its teacher's answer (`ans1: ta`, in the order of the inputs),
    then each test input is computed with the question variables and these
    values: `ans1+1` is the teacher's answer plus 1, `ans1-x^2+x^2` is the
    teacher's answer. The computed value then goes through the input's
    validation like a student's answer, by S-01 and S-13: `sinx` is
    invalid, and so is `abc*0+ta`, whose unsimplified value (STACK computes
    with `simp:false`) keeps `abc`; a test that expects a score then fails as
    invalid. Both the unsimplified text and the text that is graded are
    validated; the exemption of the question tests' inputs that this
    release had before is gone. The computed value is written as a student
    writes it: `abs(x-1)` and `mod(x,3)`, not SymPy's `Abs(x - 1)` and
    `Mod(x, 3)`, which the case rule rejects (native STACK passes a test
    whose input is `abs(x-1)`, `ta` or `ans1`, with the teacher's answer
    `abs(x-1)`, or `mod(x,3)` with `mod(x,3)`); this also writes frozen
    variants and every other value the engine reads back that way. Corpus `AlgMap-1-6.xml` types `ans+1`, the
    input's own name: its inputs are now 9, 9 and 17 (it was `ans + 1`, a
    name a student may not type) and its question tests pass at the three
    deployed seeds; no other question test of `examples/stack/` changes its
    inputs or its outcome (363 runs at seeds 1 to 3 compared before and
    after: 3 differ, in the inputs of `AlgMap-1-6.xml` only; and the golden
    rows of all of them, below). Native STACK computes the same outcomes for the test
    question in `tests/stack/test_question_test_inputs.py` (`ta`,
    `ans1-x^2+x^2` and `ans1+1` pass; `abc*0+ta` and `sinx` are invalid).
  STACK's data for these rules (the identifiers by their security, the
  case variants, the Unicode replacements) is generated from STACK's own
  files by `tools/stack_native/stack_input_data.py` into
  `ctm_checkers/stack/stack_data.py` (STACK's data, copyright the
  University of Edinburgh, Aalto University and STACK's other contributors,
  GPL-3.0-or-later, combined under section 13 of the GPL and the AGPL: the
  STACK wheel's metadata licence is `AGPL-3.0-or-later AND GPL-3.0-or-later`
  and the wheel holds the GPL's text, `dist-info/licenses/GPL-3.0-STACK.txt`;
  README, "Licence"); `native-stack.yml` checks it is current. Tests:
  `tests/stack/test_input_text.py` (57 answers with native STACK's verdict
  and message, `0^0`, the inverse functions; the globally forbidden names
  `error` and `lisp`, `do`, and the question variables `a_b`, `alpha`,
  `v_0`), `tests/stack/test_question_test_inputs.py` (with `abs` and `mod`); question
  `examples/stack/supplement/input-text.xml`; twelve mutations of the
  golden tables and eight that pytest catches (docs/goldens.md, which counts
  every STACK mutation's rows anew); S-01's mutations follow the names' new
  home in `student_input`. The three S-13 entries added to
  `tests/stack/native_compliance/policy.json` (STACK's own fixtures mark
  them -3, as expected failures that the port shares) carry no question for
  STACK: the compliance report shows one only where a discussion has one.
  - **Native STACK** (`tools/stack_native/check_validation.py`, now on every
    golden answer: STACK `10d3233`'s PHP input validation; the S-13 rows
    are those that name S-13): of the 1,000 inputs of the answer rows that
    name S-13, 958 get STACK's verdict and message; 37 are valid for
    STACK's PHP and invalid here by a rule of the CAS side, which PHP alone
    does not decide (`0^0`, 3: Maxima's error, checked natively; `π` in a
    matrix or collection input, 34: "Enter a matrix", "Use the same
    collection type …"); 4 are invalid for both with this engine's message
    for a rule outside S-13 (`x+`, `sin(`, an apostrophe, an oversized
    answer); 1 adds STACK's error for a forbidden operator (HELM's
    `bodmas.xml` forbids `*`, a rule outside S-13); 0 disagree. Of all
    5,174 golden answers: 4,455 agree, 439 the other rules, 269 after
    STACK's PHP, 5 S-01 names (listed apart), 2 other message
    (two rules at once), 4 valid here but invalid for STACK by its
    forbidden operators (bodmas.xml, as before), 0 disagree. S-01's
    answers: 376 of 382 agree in verdict and message (in 0.4.0: 356 of
    376); the 14 `ta_perimeter` and `ta_area` answers now name what STACK
    names; `d+0*f` and the 5 feedback-variable answers stay as in 0.4.0.
  - **Golden diff** (`tools/golden.py diff --base` the 0.5.0 head; `update
    --change S-13 --drop-stale`): 446 rows changed, 80 added, 3 removed:

    | Table | Changed | Added | Removed |
    |---|---|---|---|
    | `stack/compliance.jsonl` | 3 | 0 | 0 |
    | `stack/probe-questions.jsonl` | 44 | 0 | 0 |
    | `stack/probes.jsonl` | 2 | 0 | 0 |
    | `stack/questions-course.jsonl` | 32 | 0 | 0 |
    | `stack/questions-helm.jsonl` | 28 | 0 | 0 |
    | `stack/questions-library.jsonl` | 127 | 3 | 3 |
    | `stack/questions-project.jsonl` | 177 | 0 | 0 |
    | `stack/supplement.jsonl` | 33 | 77 | 0 |

    | Table | Before | After | Rows |
    |---|---|---|---|
    | `stack/compliance.jsonl` | other | false | 3 |
    | `stack/probe-questions.jsonl` | invalid 0.0 | graded 0.0 | 6 |
    | `stack/probe-questions.jsonl` | invalid 0.0 | graded 0.5 | 2 |
    | `stack/probe-questions.jsonl` | invalid 0.0 | graded 0.6666666 | 3 |
    | `stack/probe-questions.jsonl` | invalid 0.0 | invalid 0.0 | 33 |
    | `stack/probes.jsonl` | invalid | true | 1 |
    | `stack/probes.jsonl` | true | invalid | 1 |
    | `stack/questions-course.jsonl` | invalid 0.0 | graded 0.5 | 2 |
    | `stack/questions-course.jsonl` | invalid 0.0 | invalid 0.0 | 30 |
    | `stack/questions-helm.jsonl` | invalid 0.0 | graded 0.0 | 1 |
    | `stack/questions-helm.jsonl` | invalid 0.0 | invalid 0.0 | 27 |
    | `stack/questions-library.jsonl` | (new) | graded 0.0 | 3 |
    | `stack/questions-library.jsonl` | invalid 0.0 | graded 0.0 | 19 |
    | `stack/questions-library.jsonl` | invalid 0.0 | graded 0.5 | 2 |
    | `stack/questions-library.jsonl` | invalid 0.0 | graded 1.0 | 1 |
    | `stack/questions-library.jsonl` | invalid 0.0 | invalid 0.0 | 100 |
    | `stack/questions-library.jsonl` | invalid 0.0 | raised | 2 |
    | `stack/questions-library.jsonl` | passed | passed | 3 |
    | `stack/questions-project.jsonl` | invalid 0.0 | graded 0.0 | 10 |
    | `stack/questions-project.jsonl` | invalid 0.0 | graded 0.6666666667 | 2 |
    | `stack/questions-project.jsonl` | invalid 0.0 | invalid 0.0 | 165 |
    | `stack/supplement.jsonl` | (new) | value | 1 |
    | `stack/supplement.jsonl` | invalid 0.0 | graded 0.0 | 1 |
    | `stack/supplement.jsonl` | invalid 0.0 | graded 0.5 | 2 |
    | `stack/supplement.jsonl` | invalid 0.0 | graded 0.8 | 5 |
    | `stack/supplement.jsonl` | invalid 0.0 | invalid 0.0 | 25 |
    | `stack/supplement.jsonl` | raised (legacy code) | graded 0.0 | 23 |
    | `stack/supplement.jsonl` | raised (legacy code) | graded 1.0 | 6 |
    | `stack/supplement.jsonl` | raised (legacy code) | invalid 0.0 | 41 |
    | `stack/supplement.jsonl` | raised (legacy code) | other | 3 |
    | `stack/supplement.jsonl` | raised (legacy code) | passed | 3 |

    By rule (inputs of changed answer rows): `x²` 106 (the new message),
    `3,5` 106, `2 x` 106, `π` 106 (valid: 72; then a matrix or collection
    input's rule: 34), `ta_perimeter` and `ta_area` 14 (STACK's names),
    `x+SIN` 1 (`input-rules.xml`:
    STACK's message instead of "Contains a forbidden word"). Two answers
    `π` in corpus `AlgMap-10-1.xml` and `AlgMap-13-1-.xml` now reach the
    response tree and raise "FacForm supports univariate rational
    polynomials", as `pi` did before (S-11). Answer tests: STACK's fixture
    rows with inverse trigonometric functions (compliance 3: from
    "unsupported" to false, as STACK, which its fixture marks -3, an
    expected mathematical failure; `tests/stack/native_compliance/
    policy.json` lists them, its scope pinned anew, and the test that the
    moved fixtures are stack-sympy's allows exactly these three entries;
    `native-stack.yml` allows 15 s a case: the third takes about 3 s), `AlgEquiv(atan(x),
    atan(x))` (probes: invalid → true), `AlgEquiv(0^0, 1)` (true →
    invalid, as STACK's CAS error). `input-text.xml` adds 77 rows.
    Question tests (above): corpus `AlgMap-1-6.xml`'s three `stack.tests`
    rows (`questions-library`, seeds 1536647851, 1858711800, 891319547) keep
    their outcome (`passed`) and change their inputs, `ans + 1` to 9, 9 and
    17; so its three answer rows with the question test's input typed as an
    answer (`ans + 1`, which S-13 made invalid because `ans` is a name a
    student may not type) are no longer generated and are removed (ids
    `14f2d3ad4ac8d581`, `36390a37664587ff`, `92f8385572a53c93`), and the
    answers 9, 9 and 17 are added (graded 0.0, as in the legacy code). No
    other question test, teacher's answer, variant or card of the corpus
    changes.

## 0.5.0 (21 October 2026)

STACK: only `e`, `pi`, `Pi`, `PI` and `i` (and Maxima's `%e`, `%pi`, `%i`)
are constants; `E` and `I` are variables, as in STACK (S-02; step-2 design
§9, order 2). A MINOR release (verdicts change); math-exercise's tables do
not change (H2).

### Grading changes

- **S-02: `E` and `I`.** Before, the engine read `I` as the imaginary unit
  and `E` as Euler's number (`expressions.py` `_NAMES`), so for
  P = I²R the answer `-R` scored 1 (the audit's
  `examples/stack/probes/physics-I.xml`), and `E` equalled `exp(1)`. STACK
  binds only `e: exp(1)`, `pi`, `Pi`, `PI` (`%pi`) and `i: %i`
  (`stackmaxima.mac:45-50`); `E` and `I` are a student's or an author's
  variables (an energy, a current). Now they are here too, in answers and
  in question variables (an author may assign `E` and `I`; `e`, `i`, `pi`
  stay reserved). Values that the engine writes as text and reads back
  (frozen variants, the question tests' inputs) write Euler's number and
  the imaginary unit as `%e` and `%i` (`expressions.source_text`): before,
  SymPy's `E` and `I`, which would now be read as the variables.
  `log(I*x)` is an ordinary logarithm now (the rule for symbolic complex
  logarithms names `i` and `%i`), and so is the rationalized-denominator
  rule's imaginary unit. Tests: `tests/stack/test_constants.py` (the
  verdicts of native STACK, the physics probe, frozen complex values);
  question `examples/stack/supplement/constants.xml` (teacher's answers
  `2*%e*x+E` and `3*%i+I`, with answers that write e and i in every way);
  four mutations (docs/goldens.md: `E` constant 42 rows, `I` constant 63,
  values written with `E` 22, with `I` 40).
  - **Native STACK** (`tools/stack_native/dual.py`, STACK `10d3233`, Maxima
    5.46): 44 answer tests with `E`, `I`, `e`, `i`, `%e`, `%i`, `pi`, `Pi`,
    `PI` (the physics probe, the audit's `E` rows, the supplement's
    answers, complex numbers): the same verdict in all 42 AlgEquiv,
    SameType, EqualComAss and FacForm tests; the two numerical tests of a
    variable (`E`, `I` in NumAbsolute/NumRelative) are invalid here and
    false there, which is S-05, not S-02. STACK adds the answer note
    `ATAlgEquiv_WrongCase` where an answer equals the teacher's up to case
    (`3+4*I` for `3+4*%i`), which this engine does not write (as before for
    `X` and `x`; the compliance table's two such rows). In
    `stack/probes`, 3 rows now agree with native STACK
    (`AlgEquiv(-R, I^2*R)`, `AlgEquiv(E, exp(1))`, `AlgEquiv(E*x, %e*x)`:
    false), none disagree: 131 of the 162 rows with a native verdict agree
    (before 128).
  - **Golden diff** (`tools/golden.py diff --base` the 0.4.0 head, with
    `update --change S-02 --drop-stale`): 29 rows changed, 100 added, 42
    removed, in four STACK tables:

    | Table | Changed | Added | Removed |
    |---|---|---|---|
    | `stack/probe-questions.jsonl` | 14 | 18 | 14 |
    | `stack/probes.jsonl` | 3 | 0 | 0 |
    | `stack/questions-library.jsonl` | 4 | 0 | 0 |
    | `stack/questions-project.jsonl` | 8 | 30 | 28 |
    | `stack/supplement.jsonl` | 0 | 52 | 0 |

    | Table | Before | After | Rows |
    |---|---|---|---|
    | `stack/probe-questions.jsonl` | (new) | graded 0.0 | 6 |
    | `stack/probe-questions.jsonl` | (new) | graded 1.0 | 3 |
    | `stack/probe-questions.jsonl` | failed | passed | 3 |
    | `stack/probe-questions.jsonl` | graded 0.0 (legacy code) | graded 0.0 | 6 |
    | `stack/probe-questions.jsonl` | graded 1.0 | graded 0.0 | 5 |
    | `stack/probe-questions.jsonl` | graded 1.0 (legacy code) | graded 1.0 | 3 |
    | `stack/probe-questions.jsonl` | other | other | 6 |
    | `stack/probes.jsonl` | true | false | 3 |
    | `stack/questions-library.jsonl` | other | other | 4 |
    | `stack/questions-project.jsonl` | (new) | graded 0.0 | 12 |
    | `stack/questions-project.jsonl` | (new) | graded 0.5 | 6 |
    | `stack/questions-project.jsonl` | (new) | graded 1.0 | 12 |
    | `stack/questions-project.jsonl` | graded 1.0 | invalid 0.0 | 2 |
    | `stack/questions-project.jsonl` | passed | passed | 6 |
    | `stack/supplement.jsonl` | (new) | value | 1 |
    | `stack/supplement.jsonl` | failed (legacy code) | passed | 3 |
    | `stack/supplement.jsonl` | graded 0.5 (legacy code) | graded 0.5 | 12 |
    | `stack/supplement.jsonl` | graded 0.5 (legacy code) | invalid 0.0 | 2 |
    | `stack/supplement.jsonl` | graded 1.0 (legacy code) | graded 0.0 | 5 |
    | `stack/supplement.jsonl` | graded 1.0 (legacy code) | graded 1.0 | 6 |
    | `stack/supplement.jsonl` | graded 1.0 (legacy code) | invalid 0.0 | 2 |
    | `stack/supplement.jsonl` | invalid 0.0 (legacy code) | invalid 0.0 | 18 |
    | `stack/supplement.jsonl` | other (legacy code) | other | 3 |

    Changed: the physics probe (`-R`: graded 1.0 → 0.0 at seeds 1-3; its
    variants `ta: -R` → `I**2*R`; its question tests now pass: failed →
    passed, 3), `options.xml` (`j: %i`; the answers `3 + 4*I`,
    `3.0 + 4.0*I`: 1.0 → 0.0, as STACK; its variants `3 + 4*I` →
    `3 + 4*%i`), `symmetric-positive-definite.xml` and its `-prt` twin (the
    answer `matrix([2,I],[-I,2])`: graded 1.0 → invalid "Use integers or
    exact fractions for the real and imaginary parts."; the question
    tests' inputs written `%i` instead of `I`, still passed), corpus
    `Complex_Convert_1.xml` (its variants' `z1` written with `%i`: 3
    `stack.instantiate` rows and 1 card; same values, same verdicts), and
    the three probes above. Added: the answer sets now generated with `%i`
    and the physics probe's new teacher's answer, the answers above that
    write `I` (`PROBE_ANSWERS`), and `constants.xml` (52 rows; its 4
    answers `ta`, `tb` are invalid by S-01 and name S-01 and S-02).
    Removed:
    the 42 answer rows generated from text that wrote the imaginary unit
    `I` or from the old `-R` (`options.xml` 8, `physics-I.xml` 6,
    `symmetric-positive-definite*.xml` 28); their answers now come as the
    `%i` rows with the same verdicts, and `3 + 4*I`,
    `matrix([2,I],[-I,2])` stay as answers of their own (above).
    No qtest outcome and no teacher's answer of the corpus changes
    (`examples/stack/corpus`, `corrected`, `upstream`): only
    `Complex_Convert_1.xml`'s frozen text.
    Removed rows (ids): `stack/probe-questions.jsonl` `050ba53f680ce59e`,
    `4e71a326b3e06f72`, `53d744a9d65e6e45`, `5e4e7516bbd0a644`,
    `692fd246817edfc0`, `7dae19be97bc25d3`, `8ee6cb6ae290a136`,
    `99c14c7573f31a4e`, `9b11a94694b72fa3`, `c49d744dc2a79af0`,
    `c6336b0451a7d363`, `cd7fcbc23844c51f`, `d1e8bf2caf6991a5`,
    `d9e714a332e95974`; `stack/questions-project.jsonl`
    `00d769b134f50e34`, `0bcea440e57bfe06`, `1ee8935d85b575bb`,
    `20e4ae7a8beae768`, `238238804237bb85`, `2ba8193d62fc62f1`,
    `3f7d165681ba47cf`, `42b964a621bb50a5`, `4e974eb94a09631e`,
    `53dc73f028976551`, `56eecf40c84de7c6`, `5edf4c66266a4a13`,
    `61f296029afddc3e`, `62261255b0d5696a`, `747f50145806d931`,
    `751bcb56560fcf0b`, `7da47c0df9c45a41`, `89a79858d43d10a3`,
    `8f1eb4aecda78ff9`, `a7200147f979efbc`, `a80b05095d453277`,
    `b41b363e2f1eb831`, `c0c8c57136e60bbb`, `d816a5290fe77926`,
    `e58c237563333898`, `f4ac380fe9772913`, `f5b937299d5b45ec`,
    `fa1c85838dd83ff2`.

- `tools/golden.py update --drop-stale`: removes the rows that today's
  inputs no longer give and lists them (the CHANGELOG names them;
  check-changelog).

## 0.4.0 (21 October 2026)

The review of S-01 (0.3.0): its follow-ups in ctm-checkers (step-2 design
§9; the first of the set S-01 follow-ups, S-02, S-13). A MINOR release: a
question whose teacher's answer no student could enter now stops the build
(a new author error), and the STACK tables gain rows. No verdict of an
existing row changes; math-exercise's tables do not change (H2).

### Grading changes

- **S-01, follow-ups (the review of S-01, should-fix 2 and 3).**
  - A teacher's answer that uses the name of a question or feedback
    variable cannot be entered by any student, since 0.3.0 forbids such
    names in answers: `instantiate` now stops the build with
    "input[…]/tans: the teacher's answer uses t, the name of a question or
    feedback variable, which a student may not type (S-01): no student could
    enter this answer". Before, the build noticed only if a question test
    happened to cover it (the code before 0.3.0 misgraded such questions
    instead). No question of `examples/stack/` has such an answer: every
    `stack.import`, `stack.instantiate`, `stack.tests` and `stack.card` row
    is unchanged. Test: `tests/stack/test_forbidden_variables.py`
    (`test_a_teacher_answer_a_student_cannot_type_stops_the_build`, also in
    collections and matrices); question
    `examples/stack/supplement/teacher-answer-clash.xml`.
  - The feedback variables of every response tree, separated by
    semicolons or newlines, are forbidden (0.3.0 did so; no row or test
    reached a second tree or a newline, so reading only the first tree, or
    splitting at semicolons only, went unnoticed). Their names now come from
    the one grammar of the assignments
    (`expressions.assignment_statements`, which `assignments` uses too)
    instead of a pattern of their own. Tests:
    `test_the_feedback_variables_of_every_response_tree`,
    `test_assignment_statements`; question
    `examples/stack/supplement/forbidden-variables-prts.xml` (its answers
    `w`, `zz`, `sa+zz`; `ANSWERS_ONLY`).
  - Mutations (`tests/test_mutations.py`, docs/goldens.md): only the first
    response tree's feedback variables (3 rows), the assignments split at
    semicolons only (180), no check of the teacher's answers (3); the S-01
    mutation of the feedback variables follows the new code (9 rows).
  - **Native STACK** (`tools/stack_native/check_validation.py`, STACK
    `10d3233`): 376 answers name a question or feedback variable: 356 agree
    in verdict and message, 15 agree in verdict with other names in STACK's
    message (S-13, as in 0.3.0), 5 name only feedback variables (`d`,
    `sa`, and the new `w`, `zz`, `sa+zz`; listed apart, S-01); 0 disagree.
  - **Golden diff** (`tools/golden.py diff --base be8caa3`): 7 rows added
    to `stack/supplement`, none changed or removed. The 3 answers of
    `forbidden-variables-prts.xml` are invalid (the legacy code graded `w`
    0.5, `zz` and `sa+zz` 0.0); `teacher-answer-clash.xml`'s import (as
    the legacy code's) and its 3 variants (seeds 1 to 3: raised; the legacy
    code built them). The 6 rows that differ from the legacy code name S-01.

- Tools (the review of S-01, should-fix 1): `golden.py check-changelog` also
  fails a pull request that removes a golden row, or changes a row in
  another field than its result (`tags`, `native`), unless the CHANGELOG
  section of the version names the row by its id; `golden.py diff` lists
  such rows. `manifest.json` keeps the first version of a grading change
  and lists every version that wrote rows naming it (`versions`); the
  STACK tables' lines of `PROVENANCE.md` say how many rows hold
  ctm-checkers' result after a grading change (should-fix 5).
- Docs (should-fix 5): docs/goldens.md no longer says that
  `course-b-rank-pivots.xml` accepts `r` and `P` as answers.

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
  changes. Feedback variables are forbidden too: this engine's answer tests
  evaluate the student's expression where they are defined.
  Tests: `tests/stack/test_forbidden_variables.py` (the audit's leak cases,
  their question tests, feedback variables, names inside expressions,
  names that only look alike, every golden answer row); five mutations
  (`tests/test_mutations.py`, docs/goldens.md).
  - **Native STACK.** `tools/stack_native/check_validation.py` (new; the
    `native` job of `native-stack.yml`) validates every golden answer that
    names a variable with STACK's own PHP input validation (STACK
    `10d3233`, PHP 8, no Maxima): of 373 such inputs, 356 get the same
    verdict and message; 15 the same verdict (`forbiddenVariable`) with
    other names in STACK's message (14 S-13 cases: STACK's message names
    `perimeter` for `ta_perimeter`, an unknown name of three letters or
    more; and `d+0*f`, which names a feedback variable); 2 name only a
    feedback variable: invalid here (S-01), listed apart.
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
