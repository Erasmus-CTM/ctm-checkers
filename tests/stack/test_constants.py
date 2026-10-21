"""S-02 (ctm-checkers 0.5.0): only e, pi, Pi, PI and i are constants, as in
STACK (stackmaxima.mac:45-50: e: exp(1), pi/Pi/PI: %pi, i: %i), with Maxima's
%e, %pi and %i. I and E are variables: a current I and an energy E. Before,
the port read I as the imaginary unit and E as Euler's number, so the
answer -R scored full marks for P = I^2*R (the stack-sympy audit's
probes/q/physics-I.xml).

Native STACK (tools/stack_native/dual.py, Maxima 5.46 and STACK 10d3233)
gives the verdicts of the answer tests below."""
from pathlib import Path

import pytest
import sympy as sp

from ctm_checkers.stack.assessment import answer_test
from ctm_checkers.stack.engine import _source, grade, instantiate, run_question_tests, validate
from ctm_checkers.stack.expressions import assignments, evaluate, parse, source_text
from ctm_checkers.stack.importer import import_xml

ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.parametrize("student, teacher, correct", [
    # The answers native STACK gives (dual.py, 21 Oct 2026).
    ("-R", "I^2*R", False), ("I^2*R", "I^2*R", True),
    ("E", "exp(1)", False), ("E*x", "%e*x", False), ("E", "e", False), ("E^2", "exp(2)", False), ("log(E)", "1", False),
    ("e*x", "%e*x", True), ("e", "exp(1)", True), ("log(e)", "1", True),
    ("I^2", "-1", False), ("abs(I)", "1", False), ("1/I", "-I", False), ("exp(I*pi)", "-1", False), ("3+4*I", "3+4*%i", False),
    ("%i^2", "-1", True), ("i^2", "-1", True), ("3+4*i", "3+4*%i", True), ("exp(i*pi)", "-1", True), ("1/i", "-i", True),
    ("sqrt(-1)", "i", True), ("sqrt(-1)", "I", False),
    ("PI", "pi", True), ("Pi", "%pi", True),
])
def test_algequiv_as_native_stack(student, teacher, correct):
    result = answer_test("AlgEquiv", student, teacher, "", raw=student)
    assert result["valid"] and result["correct"] is correct


@pytest.mark.parametrize("name, value", [
    ("e", sp.E), ("%e", sp.E), ("i", sp.I), ("%i", sp.I), ("pi", sp.pi), ("%pi", sp.pi), ("Pi", sp.pi), ("PI", sp.pi),
    ("E", sp.Symbol("E")), ("I", sp.Symbol("I")),
])
def test_constants_and_variables(name, value):
    assert evaluate(name) == value
    assert evaluate(name, student=True) == value


def test_authors_may_name_variables_e_and_i_in_capitals():
    # Reserved names stay reserved (e, i, pi, ...); E and I are ordinary variables now.
    env = assignments("E: 5; I: 2; P: I^2*E")
    assert env["P"] == 20
    with pytest.raises(ValueError):
        assignments("e: 5")
    with pytest.raises(ValueError):
        assignments("i: 2")


@pytest.mark.parametrize("value, text", [
    (sp.E, "%e"), (sp.I, "%i"), (3 + 4 * sp.I, "3 + 4*%i"), (sp.E * sp.Symbol("x"), "%e*x"), (sp.exp(sp.I * sp.pi / 3), "exp(%i*pi/3)"),
    (sp.Symbol("I") ** 2 * sp.Symbol("R"), "I**2*R"), (sp.Symbol("E") + sp.E, "E + %e"), ([sp.I, sp.Symbol("I")], "[%i,I]"),
])
def test_values_are_written_back_as_the_same_value(value, text):
    # Frozen variants and question tests' inputs are text that is parsed again:
    # Euler's number and the imaginary unit are written %e and %i, since E and
    # I would now be read as variables.
    assert _source(value) == text
    assert evaluate(text) == (value if not isinstance(value, list) else evaluate(text))
    if not isinstance(value, list):
        assert evaluate(source_text(value)) == value


def test_the_physics_probe():
    # The audit's probe: P = I^2*R. Before S-02, -R scored 1.
    q = import_xml(ROOT / "examples" / "stack" / "probes" / "physics-I.xml")[0]
    variant = instantiate(q, 1)
    assert variant["env"] == {"ta": "I**2*R"}
    assert grade(q, {"ans1": "-R"}, variant=variant)["score"] == 0.0
    assert grade(q, {"ans1": "I^2*R"}, variant=variant)["score"] == 1.0
    assert grade(q, {"ans1": "R*I^2"}, variant=variant)["score"] == 1.0
    assert validate(q, {"ans1": "I^2*R"}, variant=variant)["inputs"]["ans1"]["latex"] == "I^{2} \\cdot R"
    assert run_question_tests(q)["passed"]


def test_complex_numbers_in_frozen_variants():
    # Complex_Convert_1's z1 and the questions that ask for %i keep their values.
    q = import_xml(ROOT / "examples" / "stack" / "symmetric-positive-definite.xml",
                   python_checkers=ROOT / "examples" / "stack" / "matrix-checkers.py")[0]
    variant = instantiate(q, 1)
    assert grade(q, {"ansm": "matrix([2,%i],[-%i,2])"}, variant=variant)["score"] == 1.0
    assert grade(q, {"ansm": "matrix([2,i],[-i,2])"}, variant=variant)["score"] == 1.0
    assert grade(q, {"ansm": "matrix([2,I],[-I,2])"}, variant=variant)["status"] == "invalid"   # I is a variable
    assert run_question_tests(q)["passed"]
    corpus = import_xml(ROOT / "examples" / "stack" / "corpus" / "Complex_Convert_1.xml")[0]
    frozen = instantiate(corpus, 2023109718)
    assert frozen["env"]["z1"] == "sqrt(2)/2 - sqrt(2)*%i/2"
    assert evaluate(frozen["env"]["z1"]) == sp.sqrt(2) / 2 - sp.sqrt(2) * sp.I / 2


def test_complex_logarithms_name_only_i():
    # log(I*x) is an ordinary logarithm of a product of two variables now.
    assert answer_test("AlgEquiv", "log(I*x)", "log(I)+log(x)", "", raw="log(I*x)")["valid"]
    assert parse("log(%i*x)")
