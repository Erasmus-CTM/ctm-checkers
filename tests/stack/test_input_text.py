"""S-13 (ctm-checkers 0.6.0): STACK's rules for the text of a student's
answer, with STACK's messages (student_input.py): names of three letters or
more (sinx, sin*x, abc; part by part at underscores; alpha and the other
names STACK knows, and names ending in a digit, are allowed), case (Sin(x),
SQRT(x), PI, In(x)), Unicode (π is pi, x² is an error), a comma between terms
(3,5), spaces between terms (2 x), 0^0, and the inverse trigonometric
functions (asin, and STACK's arcsin).

The expected messages are native STACK's (10d3233): its PHP input
validation (tools/stack_native/validation.php) of each answer with the
question variable k, 21 Oct 2026; 0^0 is Maxima's CAS error (5.46)."""
from pathlib import Path
import os

import pytest
import sympy as sp

from ctm_checkers.stack import engine, stack_data, student_input
from ctm_checkers.stack.assessment import answer_test
from ctm_checkers.stack.engine import grade, instantiate, run_question_tests, validate
from ctm_checkers.stack.expressions import evaluate
from ctm_checkers.stack.importer import import_xml

ROOT = Path(__file__).resolve().parents[2]

# (answer, STACK's validation message; '' = valid), with the question variable k.
NATIVE = [
    ('sinx', 'Forbidden variable or constant: sinx.'),
    ('sin*x', 'Forbidden variable or constant: sin.'),
    ('abc', 'Forbidden variable or constant: abc.'),
    ('abc+xyz', 'Forbidden variable or constant: abc. Forbidden variable or constant: xyz.'),
    ('abc1', ''),
    ('alpha', ''),
    ('theta+Theta', ''),
    ('x_abc', 'Forbidden variable or constant: abc.'),
    ('x_1', ''),
    ('area', 'Forbidden variable or constant: area.'),
    ('ln*x', 'Forbidden variable or constant: ln.'),
    ('In*x', ''),
    ('Sin(x)', 'Input is case sensitive: Sin is an unknown function. Did you mean sin?'),
    ('SQRT(x)', 'Input is case sensitive: SQRT is an unknown function. Did you mean sqrt?'),
    ('Exp(x)', 'Input is case sensitive: Exp is an unknown function. Did you mean exp?'),
    ('Ln(x)', 'Input is case sensitive: Ln is an unknown function. Did you mean ln?'),
    ('In(x)', 'You have typed in the expression In.  The natural logarithm is entered as ln in lower case.  ("Lima November" not "India November")'),
    ('Diff(x)', 'Input is case sensitive: Diff is an unknown function. Did you mean diff?'),
    ('PI', 'Input is case sensitive: PI is an unknown variable. Did you mean Pi, pi?'),
    ('pI', 'Input is case sensitive: pI is an unknown variable. Did you mean Pi, pi?'),
    ('XI', 'Input is case sensitive: XI is an unknown variable. Did you mean Xi, xi?'),
    ('Xi', ''),
    ('ALPHA', 'Input is case sensitive: ALPHA is an unknown variable. Did you mean Alpha, alpha?'),
    ('Sin(x)*abc', 'Input is case sensitive: Sin is an unknown function. Did you mean sin? Forbidden variable or constant: abc.'),
    ('x²', 'CAS commands may not contain the following characters: ².'),
    ('x²+y³', 'CAS commands may not contain the following characters: ².'),
    ('π', ''),
    ('πr', 'Forbidden variable or constant: pir.'),
    ('α+θ', ''),
    ('x−1', ''),
    ('2×x', ''),
    ('2·x', 'CAS commands may not contain the following characters: ·.'),
    ('√x', 'CAS commands may not contain the following characters: √.'),
    ('3,5', 'A comma in your expression appears in a strange way.  Commas are used to separate items in lists, sets etc.  You need to use a decimal point, not a comma, in floating point numbers.'),
    ('x,y', 'A comma in your expression appears in a strange way.  Commas are used to separate items in lists, sets etc.  You need to use a decimal point, not a comma, in floating point numbers.'),
    ('2 x', 'Illegal spaces found in expression 2_x.'),
    ('x y', 'Illegal spaces found in expression x_y.'),
    ('2  x+3 y', 'Illegal spaces found in expression 2_x+3_y.'),
    ('sin x', 'Illegal spaces found in expression sin_x. To apply a trig function to its arguments you must use brackets, not spaces.  For example use sin(...) instead.'),
    ('sin (x)', 'Illegal spaces found in expression sin_(x). To apply a trig function to its arguments you must use brackets, not spaces.  For example use sin(...) instead.'),
    ('cos x + sin y', 'Illegal spaces found in expression cos_x+sin_y. To apply a trig function to its arguments you must use brackets, not spaces.  For example use cos(...) instead. To apply a trig function to its arguments you must use brackets, not spaces.  For example use sin(...) instead.'),
    ('(x+1) (x-1)', 'Illegal spaces found in expression (x+1)_(x-1).'),
    ('x + 1', ''),
    ('not x', ''),
    ('a and b', ''),
    ('asin(x)', ''),
    ('arcsin(x)', ''),
    ('atan(1)', ''),
    ('arctan(1)', ''),
    ('asinh(x)', ''),
    ('arsinh(x)', ''),
    ('arccosec(x)', ''),
    ('k*x', 'Forbidden variable or constant: k.'),
    ('k_1', ''),
    # Names that no student may use anywhere (Maxima's own: the globally forbidden words).
    ('error', 'The expression error is forbidden.'),
    ('lisp', 'The expression lisp is forbidden.'),
    ('x+error', 'The expression error is forbidden.'),
]


def check(answer, variables="k:2;"):
    q = import_xml(ROOT / "examples" / "stack" / "supplement" / "input-text.xml")[0]
    q["variables"] = variables + " ta:k*asin(x)+atan(k);"
    return validate(q, {"ans1": answer}, variant=instantiate(q, 1))["inputs"]["ans1"]


@pytest.mark.parametrize("answer, message", NATIVE, ids=[case[0] for case in NATIVE])
def test_as_native_stack(answer, message):
    checked = check(answer)
    assert checked["valid"] is (message == "")
    assert checked["feedback"] == message


@pytest.mark.parametrize("answer, message", [
    ("0^0", "expt: undefined: 0^0"), ("(x-x)^0", "expt: undefined: 0^0"), ("x+0^0", "expt: undefined: 0^0"),
    ("0^(1-1)", "expt: undefined: 0^0"), ("0.0^0", "expt: undefined: 0.0^0"), ("0^0.0", "expt: undefined: 0^0.0"),
    ("x^0", ""), ("0^x", ""),
])
def test_zero_to_the_zero_is_maximas_error(answer, message):
    # Maxima 5.46 with STACK: errcatch(ev([0^0], simp)) gives "expt: undefined: 0^0"
    # (SymPy: 0**0 = 1), and STACK shows it as the validation error.
    checked = check(answer)
    assert checked["valid"] is (message == "") and checked["feedback"] == message


@pytest.mark.parametrize("student, teacher, correct", [
    ("asin(x)", "arcsin(x)", True), ("atan(1)", "pi/4", True), ("acos(0)", "pi/2", True), ("asinh(x)", "arsinh(x)", True),
    ("arccosec(2)", "pi/6", True), ("atan(1)", "pi/3", False),
])
def test_inverse_trigonometric_functions(student, teacher, correct):
    result = answer_test("AlgEquiv", student, teacher, "", raw=student)
    assert result["valid"] and result["correct"] is correct


def test_the_question_graded_with_unicode_and_arc_names():
    q = import_xml(ROOT / "examples" / "stack" / "supplement" / "input-text.xml")[0]
    variant = instantiate(q, 1)
    assert grade(q, {"ans1": "2*arcsin(x)+arctan(2)"}, variant=variant)["score"] == 1.0
    assert grade(q, {"ans1": "2*asin(x)+atan(2)"}, variant=variant)["score"] == 1.0
    assert run_question_tests(q)["passed"]
    assert validate(q, {"ans1": "π"}, variant=variant)["inputs"]["ans1"] == {"valid": True, "latex": "\\pi", "feedback": ""}
    assert validate(q, {"ans1": "x−1"}, variant=variant)["inputs"]["ans1"]["latex"] == "x - 1"


def test_a_name_in_the_final_position_of_maximas_syntax_is_forbidden():
    # do is a word of Maxima's syntax: invalid here as a variable. Native STACK
    # also finds it invalid, with another message ("'do' is an invalid final
    # term in do."); the tables record this engine's.
    for answer in ("do", "x+do", "2*do"):
        checked = check(answer)
        assert checked["valid"] is False and checked["feedback"] == "Forbidden variable or constant: do."


@pytest.mark.parametrize("answer, message", [
    ("a_b", "Forbidden variable or constant: a_b."),     # question variables (S-01)
    ("alpha", "Forbidden variable or constant: alpha."),
    ("v_0", "Forbidden variable or constant: v_0."),
    ("d", "Forbidden variable or constant: d."),         # a feedback variable (S-01)
    ("a_b+v_0", "Forbidden variable or constant: a_b. Forbidden variable or constant: v_0."),
    ("k_1", ""), ("k1", ""), ("beta", ""), ("v_1", ""), ("a_c", ""),
])
def test_the_names_of_question_and_feedback_variables_are_forbidden(answer, message):
    q = import_xml(ROOT / "examples" / "stack" / "supplement" / "input-text.xml")[0]
    q["variables"] = "k:2; a_b:3; alpha:5; v_0:2; ta:k*asin(x)+atan(k);"
    q["prts"][0]["feedbackvariables"] = "d:1;"
    checked = validate(q, {"ans1": answer}, variant=instantiate(q, 1))["inputs"]["ans1"]
    assert checked["feedback"] == message and checked["valid"] is (message == "")


def test_forbidden_characters_name_the_first():
    # corrective_parser.php reports the first character outside its set.
    with pytest.raises(engine.InvalidAnswer, match="following characters: ²\\.$"):
        student_input.student_text("x²+y³")
    with pytest.raises(engine.InvalidAnswer, match="following characters: \\\\n\\.$"):
        student_input.student_text("x\n+1")
    assert student_input.student_text("2×π−α") == "2*pi-alpha"


STACK_SOURCE = Path(os.environ.get("STACK_UPSTREAM", ROOT / ".stack-upstream-reference"))


@pytest.mark.skipif(not (STACK_SOURCE / "stack" / "cas" / "security-map.json").exists(),
                    reason="STACK checkout unavailable (STACK_UPSTREAM; native-stack.yml checks it)")
def test_the_data_is_stacks():
    import subprocess, sys
    result = subprocess.run([sys.executable, str(ROOT / "tools" / "stack_native" / "stack_input_data.py"), "--stack-source",
                             str(STACK_SOURCE), "--check"], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr


def test_the_data_is_from_the_pinned_stack():
    assert stack_data.STACK_COMMIT == "33383047af39c204bf4442802a058f8b918b2b1b"
    assert {"alpha", "theta", "pi", "e", "i", "%e", "%i", "inf"} <= stack_data.READABLE
    assert "ln" in stack_data.SHORT_FUNCTIONS and "asin" in stack_data.CALLABLE
