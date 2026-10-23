"""S-11 (ctm-checkers 0.10.0): a valid answer that an answer test does not compare or cannot decide is not an error of the
question. Before, `answer_test` raised `Unsupported` (or the number code raised `OverflowError` and `decimal`'s errors),
the engine raised `UnsupportedQuestion` and the page showed "Could not check this answer" (or a Python traceback): the
answers `x=1` and `a and b` for a SameType node, and `exp(exp(exp(exp(10))))` for NumAbsolute. Now the test is false and
not applicable (`cas_valid` false) and the response tree takes its false branch:

* SameType is STACK's ATSameTypefun (AlgEquiv applicable to the pair, the rule of S-10); EqualComAss, FacForm and SingleFrac
  give STACK's note `ATFacForm_SA_not_expression`, `ATSingleFrac_SA_not_expression`, `ATAlgEquiv_SA_not_expression` and
  `ATAlgEquiv_TA_not_equation` for an answer that is not an expression (native STACK 10d3233: tools/stack_native/dual.py);
* a bound of the engine or a type the test does not compare gives the note `<test>_undecided`;
* an error of the author (an option, a teacher's answer, a test the engine does not have) still raises `Unsupported`."""
from pathlib import Path

import pytest

from ctm_checkers.stack import Unsupported, answer_test
from ctm_checkers.stack.expressions import InvalidAnswer
from ctm_checkers.stack.engine import grade, instantiate
from ctm_checkers.stack.importer import import_xml

ROOT = Path(__file__).resolve().parents[2]
NOT_EXPRESSION = "Your answer should be an expression, not an equation, inequality, list, set or matrix."
ENTERED_EQUATION = ('You have entered an equation, but an equation is not expected here. You may have typed something like '
                    '"y=2*x+1" when you only needed to type "2*x+1".')
UNDECIDED = "This answer could not be checked automatically."


def run(*args, **kwargs):
    result = answer_test(*args, raw=args[1], **kwargs)
    return result["valid"], result["correct"], result["cas_valid"], result["note"], result["feedback"]


@pytest.mark.parametrize("student, teacher, correct", [
    # Native STACK: false for each of these but the last three (true).
    ("x=1", "x+1", False), ("a and b", "x+1", False), ("x=1 or x=2", "x+1", False), ("[1,2]", "x+1", False),
    ("x+1", "x=1", False), ("true", "x+1", False), ("x+2", "x+1", True), ("true", "a and b", True), ("x=1", "y=2", True),
])
def test_same_type_is_decided_for_equations_and_logic(student, teacher, correct):
    assert run("SameType", student, teacher) == (True, correct, True, "", "")


@pytest.mark.parametrize("test, student, options, note, feedback", [
    ("EqualComAss", "x=1", "", "ATAlgEquiv_TA_not_equation", ENTERED_EQUATION),
    ("EqualComAss", "a and b", "", "ATAlgEquiv_SA_not_expression", NOT_EXPRESSION),
    ("EqualComAss", "x=1 or x=2", "", "ATAlgEquiv_SA_not_expression", NOT_EXPRESSION),
    ("FacForm", "x=1", "x", "ATFacForm_SA_not_expression", NOT_EXPRESSION),
    ("FacForm", "[1,2]", "x", "ATFacForm_SA_not_expression", NOT_EXPRESSION),
    ("FacForm", "a and b", "x", "ATFacForm_SA_not_expression", NOT_EXPRESSION),
    ("FacForm", "matrix([1,2])", "x", "ATFacForm_SA_not_expression", NOT_EXPRESSION),
    ("SingleFrac", "x=1", "", "ATSingleFrac_SA_not_expression", NOT_EXPRESSION),
    ("SingleFrac", "[1,2]", "", "ATSingleFrac_SA_not_expression", NOT_EXPRESSION),
    ("SingleFrac", "a and b", "", "ATSingleFrac_SA_not_expression", NOT_EXPRESSION),
])
def test_an_answer_that_is_not_an_expression_has_stacks_note(test, student, options, note, feedback):
    # Native: false, the answer note of the test, for each.
    assert run(test, student, "x+1", options) == (True, False, False, note, feedback)


@pytest.mark.parametrize("test, student, teacher, options", [
    ("LowestTerms", "x=1", "x+1", ""), ("LowestTerms", "[1,2]", "x+1", ""), ("LowestTerms", "a and b", "x+1", ""),
    ("FacForm", "(x+1)^100*(x+1)^100", "1", "x"), ("FacForm", "x/x", "1", "x"), ("FacForm", "x^2-1+0*x^(-1)", "x^2-1", "x"),
    ("AlgEquiv", "cosh(x)^20-((exp(x)+exp(-x))/2)^20+x+1", "x+1", ""),
    ("EqualComAss", "cosh(x)^20-((exp(x)+exp(-x))/2)^20+x+1", "x+1", ""),
])
def test_what_the_engine_cannot_decide_is_false_with_its_note(test, student, teacher, options):
    # Native STACK decides these (LowestTerms is true for an answer that is not an expression, AlgEquiv of the hyperbolic
    # answer is true); the engine's answer is false, with its own note.
    assert run(test, student, teacher, options) == (True, False, False, f"{test}_undecided", UNDECIDED)


@pytest.mark.parametrize("test, student, options", [
    ("NumAbsolute", "exp(exp(exp(exp(10))))", "0.01"), ("NumRelative", "-exp(exp(exp(exp(10))))", "0.01"),
    ("NumAbsolute", "exp(exp(100))", "0.01"), ("NumRelative", "exp(exp(exp(exp(2))))", "0.01"),
])
def test_a_number_too_large_to_evaluate_is_undecided(test, student, options):
    # Before: OverflowError (the first two), decimal.InvalidOperation (the others), uncaught.
    assert run(test, student, "pi/4", options) == (True, False, False, f"{test}_undecided", UNDECIDED)


def test_the_errors_of_the_author_still_raise():
    for test, student, teacher, options in (
            ("FacForm", "(x+y)*(x-y)", "x^2-y^2", "x"),          # the teacher's answer is not univariate
            ("FacForm", "x^2-1", "x^2-1", ""),                    # no variable
            ("NumAbsolute", "x", "1", "x"),                       # the tolerance is not a number (InvalidAnswer)
            ("EqualComAss", "x+1", "x=1", ""),                    # an equation as the teacher's answer
            ("NumDecPlaces", "0.5", "0.5", "0"),                  # places out of range
            ("NumAbsolute", "1", "[1,2]", "0.1"),                 # a collection as the teacher's answer
            ("FacForm", "x", "[1,2]", "x"), ("LowestTerms", "x", "a and b", ""),
            ("Int", "x", "x", "")):                               # a test the engine does not have
        with pytest.raises((Unsupported, InvalidAnswer)):
            answer_test(test, student, teacher, options, raw=student)


def test_the_teachers_answer_outside_the_logic_bounds_is_an_error_of_the_author():
    teacher = " or ".join(f"{name}=0" for name in "abcdefghi")    # nine variables: beyond the bound
    with pytest.raises(Unsupported, match="The teacher's answer"):
        answer_test("AlgEquiv", "a=0", teacher, raw="a=0")
    # The same logic as the answer is undecided.
    assert run("AlgEquiv", teacher, "a=0") == (True, False, False, "AlgEquiv_undecided", UNDECIDED)


def question(name):
    return import_xml(ROOT / "examples/stack/probes" / name)[0]


@pytest.mark.parametrize("answer", ["x=1", "a and b", "x=1 or x=2", "[1,2]", "{1}", "matrix([1,2])", "true"])
def test_the_audits_crash_probe_takes_the_false_branch(answer):
    # Native (4.13.1 and 4.14.0): score 0, notes [prt1-1-F], the first node's false feedback; the input is valid.
    q = question("crash.xml")
    result = grade(q, {"ans1": answer}, variant=instantiate(q, 1))
    assert result["status"] == "graded" and result["score"] == 0.0 and result["inputs"]["ans1"]["valid"]
    assert result["prts"]["prt1"]["notes"] == ["prt1-1-F"] and result["prts"]["prt1"]["feedback"] == "<p>Give an expression.</p>"


def test_the_crash_probe_still_grades_an_expression_and_the_hyperbolic_answer():
    q = question("crash.xml")
    variant = instantiate(q, 1)
    assert grade(q, {"ans1": "x+1"}, variant=variant)["score"] == 1.0
    # Native: SameType true, EqualComAss false (AlgEquiv holds, the forms differ): 0, notes [prt1-1-T, prt1-2-F].
    result = grade(q, {"ans1": "cosh(x)^20-((exp(x)+exp(-x))/2)^20+x+1"}, variant=variant)
    assert result["status"] == "graded" and result["score"] == 0.0
    assert result["prts"]["prt1"]["notes"] == ["prt1-1-T", "prt1-2-F"] and UNDECIDED in result["prts"]["prt1"]["feedback"]


@pytest.mark.parametrize("answer", ["exp(exp(exp(exp(10))))", "exp(exp(100))"])
def test_the_audits_overflow_probe_is_graded_not_raised(answer):
    q = question("numabs-branch.xml")
    result = grade(q, {"ans1": answer}, variant=instantiate(q, 1))
    assert result["status"] == "graded" and result["score"] == 0.0
    assert result["prts"]["prt1"]["notes"] == ["prt1-1-F", "prt1-2-F"] and UNDECIDED in result["prts"]["prt1"]["feedback"]


def test_a_number_too_large_in_an_answer_is_refused_not_raised(monkeypatch):
    from ctm_checkers.stack import engine
    def overflow(*args, **kwargs):
        raise OverflowError("int too large to convert to float")
    monkeypatch.setattr(engine, "evaluate", overflow)
    q = question("numabs-branch.xml")
    result = engine._input_validation(q["inputs"][0], "x", {}, {}, q)[0]
    assert result == {"valid": False, "latex": "", "feedback": "This number is too large"}


@pytest.mark.parametrize("test, student, teacher, options", [
    ("NumAbsolute", "1", "exp(exp(exp(exp(10))))", "0.01"),
    ("NumRelative", "1", "exp(exp(100))", "0.01"),
    ("NumDecPlaces", "0.50", "exp(exp(exp(exp(10))))", "2"),
    ("NumDecPlaces", "0.50", "exp(exp(100))", "2"),
    ("NumAbsolute", "1", "pi/4", "exp(exp(exp(exp(10))))"),
    ("NumAbsolute", "x", "1", "exp(exp(exp(exp(10))))"),
    ("NumRelative", "1", "pi/4", "exp(exp(100))"),
    ("NumAbsolute", "exp(exp(exp(exp(10))))", "exp(exp(exp(exp(10))))", "0.01"),
])
def test_numerical_author_overflow_is_an_error_not_student_undecided(test, student, teacher, options):
    with pytest.raises(Unsupported, match="supported bounds"):
        answer_test(test, student, teacher, options, raw=student)


def test_large_exact_rational_comparison_does_not_gain_decimal_bounds():
    import sympy as sp
    result = answer_test("NumAbsolute", "huge", "huge", "1", env={"huge": sp.Integer(10)**1000})
    assert result["valid"] and result["correct"]


@pytest.mark.parametrize("student", ["0.50", "0.5", "1"])
def test_decimal_teacher_bound_is_checked_before_student_format(student):
    import sympy as sp
    with pytest.raises(Unsupported, match="Numerical teacher answer exceeds supported bounds"):
        answer_test("NumDecPlaces", student, "huge", "2", raw=student,
                    env={"huge": sp.Integer(10)**1000})


@pytest.mark.parametrize("student, valid, note", [
    ("1", True, "ATNumDecPlaces_SA_Not_num"),
    ("0.50", False, "invalid"),
])
def test_nonnumeric_decimal_teacher_preserves_student_format_precedence(student, valid, note):
    result = answer_test("NumDecPlaces", student, "x", "2", raw=student)
    assert result["valid"] is valid and not result["correct"] and result["note"] == note
