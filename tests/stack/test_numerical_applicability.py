"""S-05 (ctm-checkers 0.8.0): a numerical answer test (NumAbsolute, NumRelative,
NumDecPlaces) that cannot be applied to an answer because it is not a number
is false, and the response tree takes its false branch with the test's answer
note, as in STACK (numericaltest.mac: StackBasicReturn(false, false,
"ATNumerical_SA_not_number"), prt.class.php: the branch follows the second
flag). Before, the answer was "invalid" and the response tree stopped
(a symbolic or complex answer, `inf`), or the grading raised an author error
(a list, a set, a matrix, an equation or a logical expression).

Native STACK (tools/stack_native/dual.py, Maxima 5.46 and STACK 10d3233; the
PHP oracle of STACK 4.13.1 and 4.14.0 for the response trees) gives the
verdicts and notes below (its notes end with a period, `ATNumerical_SA_not_number.`)."""
from pathlib import Path

import pytest

from ctm_checkers.stack.assessment import answer_test
from ctm_checkers.stack.engine import grade, instantiate, run_question_tests
from ctm_checkers.stack.expressions import InvalidAnswer, Unsupported
from ctm_checkers.stack.importer import import_xml

ROOT = Path(__file__).resolve().parents[2]
SA = ("ATNumerical_SA_not_number", "Your answer should be a floating point number, but is not.")
SB = ("ATNumerical_SB_not_number", "The value supplied for the teacher's answer should be a floating point number, "
                                  "but is not. This is an internal error with the test.  Please ask your teacher about this.")
DP = ("ATNumDecPlaces_SA_Not_num", "Your answer must be a floating point number, but is not.")


def not_applicable(*args):
    result = answer_test(*args, raw=args[1])
    assert (result["valid"], result["correct"], result["cas_valid"]) == (True, False, False), result
    return result["note"], result["feedback"]


@pytest.mark.parametrize("test", ["NumAbsolute", "NumRelative"])
@pytest.mark.parametrize("student", [
    "45*x", "x", "3+4*%i", "sqrt(-4)", "inf", "[1,2]", "{1}", "matrix([1,2],[3,4])", "x=1", "a and b", "[]", "{}",
])
def test_an_answer_that_is_not_a_number_is_false_with_the_note(test, student):
    # Native: [false, false, "ATNumerical_SA_not_number."] for each of these (dual.py).
    assert not_applicable(test, student, "pi/4", "0.01") == SA


@pytest.mark.parametrize("test, student, teacher, options, correct", [
    ("NumAbsolute", "1.05", "1", "0.1", True), ("NumAbsolute", "1.2", "1", "0.1", False),
    ("NumAbsolute", "pi/4", "0.785", "0.01", True), ("NumAbsolute", "-1", "1", "0.1", False),
    ("NumRelative", "1.4", "1", "0.5", True), ("NumRelative", "2", "1", "0.5", False),
    ("NumRelative", "sqrt(2)", "1.41", "0.01", True),
])
def test_numbers_are_unchanged(test, student, teacher, options, correct):
    result = answer_test(test, student, teacher, options, raw=student)
    assert (result["valid"], result["correct"], result["note"]) == (True, correct, "")
    assert result.get("cas_valid", True) is True


def test_the_teachers_answer_that_is_not_a_number():
    # Native: ATNumerical_SB_not_number once the answer is a number; the answer is checked first.
    assert not_applicable("NumAbsolute", "1", "x", "0.1") == SB
    assert not_applicable("NumRelative", "1", "x+1", "0.1") == SB
    assert not_applicable("NumRelative", "x", "x", "0.1") == SA


@pytest.mark.parametrize("student", [
    "1", "1/2", "x", "sqrt(2)", "pi", "[0.5]", "matrix([0.5])", "3+4*%i", "x=1", "a and b",
])
def test_decimal_places_of_an_answer_that_is_not_a_float(student):
    # Native: "ATNumDecPlaces_SA_Not_num." for each (not floatnump); before: invalid, or Unsupported for the last three.
    assert not_applicable("NumDecPlaces", student, "0.5", "1") == DP


def test_decimal_places_of_floats_are_unchanged():
    for student, correct, note in (("0.785", True, ""), ("0.79", False, "wrong_decimal_places"), ("0.7850", False, "wrong_decimal_places"),
                                   ("-0.785", False, "wrong_value")):
        result = answer_test("NumDecPlaces", student, "pi/4", "3", raw=student)
        assert (result["valid"], result["correct"], result["note"]) == (True, correct, note)


def test_a_float_that_is_written_as_an_expression_is_false():
    # Native: floatnump holds (0.5+0.25 is 0.75), but the places are counted in the text: wrong. The engine reads the
    # places from a decimal literal only, so the answer is false for the other note (the branch is the same).
    for student in ("0.5+0.25", "2.5*10^-1"):
        assert not_applicable("NumDecPlaces", student, "0.75", "2") == DP


def test_an_author_error_in_the_option_comes_before_the_answer():
    # STACK checks the option first: a symbolic answer does not hide a tolerance that is not a number.
    for test, options in (("NumAbsolute", "x"), ("NumRelative", "a+b")):
        with pytest.raises((InvalidAnswer, Unsupported)):
            answer_test(test, "x", "1", options, raw="x")
    for options in ("", "0", "51", "x", "1.5"):
        with pytest.raises(Unsupported):
            answer_test("NumDecPlaces", "x", "0.5", options, raw="x")


def test_a_collection_or_logical_teachers_answer_stays_unsupported():
    # Native STACK compares lists and sets with these tests (ATNumerical_list); the engine does not.
    for teacher in ("[1,2]", "{1}", "matrix([1,2],[3,4])", "x=1"):
        with pytest.raises(Unsupported):
            answer_test("NumAbsolute", "1", teacher, "0.1", raw="1")


def question(name):
    return import_xml(ROOT / "examples/stack/probes/numabs-branch.xml" if name == "numabs" else
                      ROOT / "examples/stack/supplement/numerical-applicability.xml")[0]


def test_the_audits_probe_takes_the_false_branch_and_its_question_test_passes():
    # numabs-branch.xml: ta = pi/4, node 0 NumAbsolute (0.01), false -> node 1 AlgEquiv(ans1, 45*x), true: 0.5.
    # Native (4.13.1 and 4.14.0): 45*x scores 0.5, answer notes [ATNumerical_SA_not_number., prt1-1-F, prt1-2-T].
    q = question("numabs")
    variant = instantiate(q, 1)
    result = grade(q, {"ans1": "45*x"}, variant=variant)
    assert result["status"] == "graded" and result["score"] == 0.5
    prt = result["prts"]["prt1"]
    assert prt["notes"] == ["prt1-1-F", "prt1-2-T"] and "Use radians" in prt["feedback"]
    assert "Not within 0.01 of the angle." in prt["feedback"]
    assert "Your answer should be a floating point number, but is not." in prt["feedback"]
    tests = run_question_tests(q, seeds=(1, 2, 3))
    assert tests["passed"] and len(tests["results"]) == 3


@pytest.mark.parametrize("answer", ["x", "45*x", "3+4*%i", "[1,2]", "{1}", "matrix([1,2],[3,4])", "x=1", "a and b", "inf"])
def test_the_three_trees_of_the_question_take_their_false_branches(answer):
    # Native (4.13.1, 4.14.0): every PRT score 0, notes <AT note>, prtN-F; the input is valid.
    q = question("applicability")
    result = grade(q, {"ans1": answer}, variant=instantiate(q, 1))
    assert result["status"] == "graded" and result["score"] == 0.0
    assert [result["prts"][p]["notes"] for p in ("prt1", "prt2", "prt3")] == [["prt1-F"], ["prt2-F"], ["prt3-F"]]
    assert "Your answer should be a floating point number, but is not." in result["prts"]["prt1"]["feedback"]
    assert "Your answer must be a floating point number, but is not." in result["prts"]["prt3"]["feedback"]


@pytest.mark.parametrize("answer, scores", [
    ("pi/4", (1, 1, 0)), ("0.785", (1, 1, 1)), ("0.79", (1, 1, 0)), ("0.7850", (1, 1, 0)), ("1", (0, 0, 0)), ("1/2", (0, 0, 0)),
    ("0.5+0.285", (1, 1, 0)), ("-0.785", (0, 0, 0)), ("2.5*10^-1", (0, 0, 0)), ("sqrt(2)", (0, 0, 0)),
])
def test_the_scores_of_the_question_are_those_of_native_stack(answer, scores):
    q = question("applicability")
    result = grade(q, {"ans1": answer}, variant=instantiate(q, 1))
    assert result["status"] == "graded"
    assert tuple(result["prts"][p]["score"] for p in ("prt1", "prt2", "prt3")) == scores


def test_the_question_tests_of_the_question_pass():
    q = question("applicability")
    tests = run_question_tests(q, seeds=(1, 2, 3))
    assert tests["passed"] and len(tests["results"]) == 6
