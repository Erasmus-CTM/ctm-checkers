# Resolved native candidate validation (partial API)

`ctm_variants.validation.validate_math_candidate(options, base, *, context,
teacher_inputs, file="<question>", label="<exercise>", locator=None)` validates one
already-resolved Math candidate. It implements the teacher-answer and declarative
authored-test part of the [approved variants design §3.6f and binding decisions
13/19](https://github.com/Erasmus-CTM/ctm-assessment/blob/handoff/2026-10/docs/consolidation/2026-10-variants.md).
It stays outside browser wheels and adds no component author syntax.

The caller supplies an existing `question_context` envelope with ordered default
language field labels, exact variables and teacher values, and optional valid
identity. The adapter uses its canonical validator; it invents no variant number,
ID or approval hash. `options["field-labels"]` must match those ordered labels.
Resolved variables belong in context; `question-variables` cannot shadow it.

`teacher_inputs` maps exactly those labels to literal student strings supplied by
the caller. This adapter does not evaluate teacher expressions or print values.
The typed input is passed as `Raw` to the existing `run_question` real-grading
adapter. Every teacher vector must receive `correct`, and every field verdict
reported by that grader must also be `correct`. A legacy custom checker returning
only an overall result retains that contract. No additional numerical score rule
is imposed. Grading options, written-form checks and numeric tolerances stay in
the existing grader.

Then the same runner executes supplied declarative authored cases, including
raw strings, expressions in exact variables, per-field/overall expectations and
optional score/partial assertions. Absent or empty `tests` means teacher-only.
Failures raise `CandidateValidationError` naming file, exercise, optional caller
locator and phase/test. Success returns `passed`, `teacher` and `tests` results.
Input options/context are not mutated.

This is a synchronous leaf with the same trusted-author execution model as
`run_question`: custom checker code runs natively and is not sandboxed or given a
new deadline here. Batch/build orchestration must apply its supervised time
budget. Existing codec bounds remain in force; this API adds no sampling or input
truncation policy. Literal scalar/set/string/expression inputs cover the seven
existing Math modes; named matrix inputs and arbitrary custom JSON with exact
question context remain unsupported by the current grading adapter.

Python `test(check, symbols)` tests remain unchanged in the existing runner; this
new leaf accepts declarative lists only. The proposed three-argument
`test(check, symbols, variant)` bridge is not implemented. Placeholder resolution,
answer printing, note deduplication, proposals, approval/manifests, student wiring
and wrong-answer probes are outside this slice.

Run `python tests/test_variants_validation.py` from source and again with
`CTM_CHECKERS_WHEEL` pointing at the actual unchanged browser wheel.
