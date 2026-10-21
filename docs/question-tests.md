# Authored question tests

The shared runner is ctm_checkers.testing.run_declarative. A component supplies
its real grading callback; the runner resolves inputs and checks expectations.
It imports neither math-exercise nor STACK. Math uses its existing check and
check_custom, with the existing learner admission rule. Grading code and golden
rows are unchanged. STACK's XML qtests are unchanged; H1 can use the same
format with its own CAS resolver and grading adapter.

For ordinary math-exercise blocks:

    #| field-labels: derivative,tangent
    #| tests:
    #|   - name: a sign error
    #|     answers: [raw("-2*x"), raw("2*x+1")]
    #|     expect: [wrong, correct]
    #|     score: 0.5
    #|     partial: true

answers can instead be a mapping using the field labels exactly. The list
form follows rendered field order; unlabelled ordinary fields use their
one-based ordinal as a string in mappings. Labels must be unique. Teacher
keys come from scalar, vector and fixed-matrix answer markers; resolved
variants can pass the same runner a teacher mapping and exact question
variables. This PR does not replace the existing variant generator.

Each test needs a unique name, answers or response, and an expectation.
expect is an overall verdict, a field-order list, a mapping by field name,
or an object with status, score, partial and/or answer-note. Field values
can also be such objects. A top-level score/partial checks the overall
result in addition to field expectations. Scores compare within 1e-9.
Unknown keys and mismatched fields fail the build.

Expressions use the question's symbols and resolved variables, exact rational
arithmetic and SymPy functions such as diff, factor, sqrt and Matrix. They
are computed before being written in student input syntax. Use raw("...")
for the exact text a student types, including spelling, spaces and unreduced
fractions. Literal strings are never passed to sympify. Custom graphical
fixtures use response with nested values evaluated in the same environment;
literal text values use raw("..."). Numeric JSON leaves cross the same finite
IEEE754 boundary as browser JSON; resolved question variables and teacher
answers stay exact. Field verdicts for custom graders require
the real checker's assessment.fields; an overall verdict always works.

The Python test(check, symbols) form and sidecar .py files retain their existing
contract. No legacy custom runner is unified here.

Run the component's direct script, never python -m:

    python _extensions/math-exercise/question-tests.py lesson.qmd

Native declarative YAML needs SymPy and PyYAML on the render machine. The
browser wheel does not import PyYAML. The direct command and Quarto's --stdin
path use the same adapter. A failed test stops the build with the exercise
label and test name. Exercises without tests still need no native Python.

Code and the newly authored fixtures are AGPL-3.0-or-later. No course-derived
golden rows or third-party question fixtures are copied by this change.
