"""S-10 (ctm-checkers 0.9.0): `checkanswertype` refuses an answer of another type than the teacher's answer, as STACK does
(validator.mac:52: stack_validate calls ATSameTypefun, which is AlgEquiv's applicability; its message is the validation
error). Before, only a collection of another kind than the teacher's was refused: the answer `2*x+1` for the teacher's
answer `y=2*x+1` was valid and graded 0.

TABLE is native STACK's verdict and message (4.13.1 and 4.14.0, which agree) for each type of answer in each type of
teacher's answer: the question examples/stack/supplement/checkanswertype.xml in Maxima 5.46 through STACK's PHP."""
from pathlib import Path

import pytest

from ctm_checkers.stack import collections as C
from ctm_checkers.stack.engine import grade, instantiate
from ctm_checkers.stack.importer import import_xml

ROOT = Path(__file__).resolve().parents[2]
TEACHERS = ("expr", "eq", "list", "set", "mat", "disj", "logic", "nest")
# STACK's English texts (the oracle's validation errors).
SA_NOT_EQUATION = "Your answer should be an equation, but is not."
MESSAGES = {".": None, "SA_EQ": SA_NOT_EQUATION,
            "LIST": "Your answer should be a list, but is not. Note that the syntax to enter a list is to enclose the comma separated values with square brackets.",
            "SET": "Your answer should be a set, but is not. Note that the syntax to enter a set is to enclose the comma separated values with curly brackets.",
            "MAT": "Your answer should be a matrix, but is not.",
            "LOGIC": "Your answer should be an equation, inequality or a logical combination of many of these, but is not.",
            "INEQ": "Your answer should be an inequality, but is not.",
            "TA_EQ": 'You have entered an equation, but an equation is not expected here. You may have typed something like "y=2*x+1" when you only needed to type "2*x+1".',
            "EXPR": "Your answer should be an expression, not an equation, inequality, list, set or matrix.",
            # STACK adds the entries "underlined in red" and a display of the answer; the engine gives this text only.
            "LIST+entries": "Use the same collection type as the teacher answer",
            "EXPR+entries": "Use the same collection type as the teacher answer"}
TABLE = {
    "2*x+1":               (".", "SA_EQ", "LIST", "SET", "MAT", "LOGIC", "INEQ", "LIST"),
    "x":                   (".", "SA_EQ", "LIST", "SET", "MAT", "LOGIC", "INEQ", "LIST"),
    "y=2*x+1":             ("TA_EQ", ".", "LIST", "SET", "MAT", "TA_EQ", "TA_EQ", "LIST"),
    "x=1 or x=2":          ("EXPR", ".", "LIST", "SET", "MAT", ".", ".", "LIST"),
    "a and b":             ("EXPR", ".", "LIST", "SET", "MAT", ".", ".", "LIST"),
    "true":                ("EXPR", ".", "LIST", "SET", "MAT", ".", ".", "LIST"),
    "[1,2]":               ("EXPR", "SA_EQ", ".", "SET", "MAT", "LOGIC", "INEQ", "LIST+entries"),
    "[1,2,3]":             ("EXPR", "SA_EQ", ".", "SET", "MAT", "LOGIC", "INEQ", "."),
    "[1,[2,3]]":           ("EXPR", "SA_EQ", "EXPR+entries", "SET", "MAT", "LOGIC", "INEQ", "."),
    "{1,2}":               ("EXPR", "SA_EQ", "LIST", ".", "MAT", "LOGIC", "INEQ", "LIST"),
    "{1,2,3}":             ("EXPR", "SA_EQ", "LIST", ".", "MAT", "LOGIC", "INEQ", "LIST"),
    "matrix([1,2],[3,4])": ("EXPR", "SA_EQ", "LIST", "SET", ".", "LOGIC", "INEQ", "LIST"),
    "matrix([1,2])":       ("EXPR", "SA_EQ", "LIST", "SET", ".", "LOGIC", "INEQ", "LIST"),
}


@pytest.fixture(scope="module")
def kinds():
    question = import_xml(ROOT / "examples/stack/supplement/checkanswertype.xml")[0]
    return question, instantiate(question, 1)


@pytest.mark.parametrize("student", list(TABLE))
def test_every_type_of_answer_in_every_type_of_teachers_answer_is_native_stacks(kinds, student):
    question, variant = kinds
    result = grade(question, {f"in_{kind}": student for kind in TEACHERS}, variant=variant)
    for kind, code in zip(TEACHERS, TABLE[student]):
        validation = result["inputs"][f"in_{kind}"]
        assert (validation["valid"], validation["feedback"]) == (MESSAGES[code] is None, MESSAGES[code] or ""), (student, kind)


def test_type_mismatch_is_the_message_or_none():
    teachers = dict(zip(TEACHERS, ("2*x+1", "y=2*x+1", "[1,2]", "{1,2}", "matrix([1,2],[3,4])", "x=1 or x=2", "a and b", "[1,[2,3]]")))
    from ctm_checkers.stack.expressions import evaluate
    for student, row in TABLE.items():
        for kind, code in zip(TEACHERS, row):
            assert C.type_mismatch(evaluate(student, {}), evaluate(teachers[kind], {})) == MESSAGES[code], (student, kind)


def test_the_audits_probe_eqtype_refuses_an_expression_for_an_equation():
    # Native (both versions): `2*x+1`, `x` and `[1,2]` are invalid, "Your answer should be an equation, but is not.", with no
    # score; `y=2*x+1` scores 1 and `x=1 or x=2` is valid and scores 0.
    question = import_xml(ROOT / "examples/stack/probes/eqtype.xml")[0]
    variant = instantiate(question, 1)
    for answer in ("2*x+1", "x", "[1,2]"):
        result = grade(question, {"ans1": answer}, variant=variant)
        assert result["status"] == "invalid" and result["score"] == 0.0
        assert result["inputs"]["ans1"] == {"valid": False, "latex": "", "feedback": SA_NOT_EQUATION}
    assert grade(question, {"ans1": "y=2*x+1"}, variant=variant)["score"] == 1.0
    disjunction = grade(question, {"ans1": "x=1 or x=2"}, variant=variant)
    assert (disjunction["status"], disjunction["score"]) == ("graded", 0.0)


def test_the_option_off_does_not_check_the_type():
    question = import_xml(ROOT / "examples/stack/probes/eqtype.xml")[0]
    for inp in question["inputs"]:
        inp["checkanswertype"] = False
    result = grade(question, {"ans1": "2*x+1"}, variant=instantiate(question, 1))
    assert result["inputs"]["ans1"]["valid"] is True and result["status"] == "graded"


def test_the_question_tests_of_the_probe_pass():
    from ctm_checkers.stack.engine import run_question_tests
    question = import_xml(ROOT / "examples/stack/probes/eqtype.xml")[0]
    assert run_question_tests(question, seeds=(1, 2, 3))["passed"]
