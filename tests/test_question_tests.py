"""Question-test format and real grading. Inputs authored here: AGPL-3.0-or-later."""
import copy
import json
import subprocess
import sys

import pytest
from sympy import Rational, Symbol

from ctm_checkers.math_exercise.authored import run_question, _teacher_fields
from ctm_checkers.testing import Raw, expression, run_declarative


def question(mode="equivalent", **kwargs):
    return dict({"mode": mode, "question": "Answer _[x^2].", "vars": "x",
                 "field-labels": "answer", "tests": []}, **kwargs)


def case(answer, expect="correct", **kwargs):
    return dict(name="case", answers=[answer], expect=expect, **kwargs)


@pytest.mark.parametrize("mode,teacher,answer,verdict", [
    ("equivalent", "(x+1)^2", "x^2+2*x+1", "correct"),
    ("equivalent", "x", "x+1", "wrong"),
    ("numeric", "1/2", "raw('0.5')", "correct"),
    ("numeric", "1/2", "raw('0.9')", "wrong"),
    ("exact", "1/2", "raw('2/4')", "wrong"),
    ("set", "1,2,3", "raw('3,1,2')", "correct"),
    ("string", "Hello", "raw('Hello')", "correct"),
    ("string", "Hello", "raw('hello')", "wrong"),
    ("string_ci", "Hello", "raw('hello')", "correct"),
])
def test_every_builtin_mode_uses_real_grading(mode, teacher, answer, verdict):
    q = question(mode, teacher=[teacher], tests=[case(answer, verdict)])
    assert run_question(q, ".")[0]["passed"]


def test_numeric_rules_and_raw_written_form_are_not_simplified():
    q = question("numeric", teacher=["1"], tolerance="0.01",
                 tests=[case("raw('1.005')")])
    run_question(q, ".")
    q["tolerance"] = "0.001"
    with pytest.raises(AssertionError, match="case"):
        run_question(q, ".")
    q = question("exact", teacher=["1/2"], **{"partial-credit": "true", "form-credit": "0.25"},
                 tests=[case("raw('2/4')", "partial", score=0.25, partial=True)])
    assert run_question(q, ".")[0]["actual"]["fields"]["answer"]["status"] == "not_exact"


def test_field_and_overall_expectations_partial_score_and_named_keys():
    q = question(teacher=["x", "x^2"], **{"field-labels": "first,second", "partial-credit": "true"},
                 tests=[dict(name="mixed", answers={"first": "x", "second": "x+1"},
                             expect={"first": "correct", "second": "wrong"}, score=0.5, partial=True)])
    result = run_question(q, ".")[0]["actual"]
    assert result["status"] == "partial" and result["score"] == 0.5
    q["tests"][0]["expect"]["second"] = "correct"
    with pytest.raises(AssertionError, match="second"):
        run_question(q, ".")


def test_question_variables_exact_values_and_teacher_mapping():
    q = question(tests=[dict(name="computed", answers={"answer": "a*x"}, expect="correct")])
    run_question(q, ".", variables={"a": Rational(1, 3)}, teacher={"answer": Symbol("x")/3})
    assert expression("0.1+1/3") == Rational(13, 30)
    assert expression("raw('2x')") == "2x"
    with pytest.raises(ValueError):
        expression("unknown+1")
    with pytest.raises(ValueError):
        expression("sqrt('__import__(\"os\")')")


def test_custom_checkers_go_through_check_custom_not_direct_calls():
    checker = 'def check(response, symbols):\n    return {"score": 0.5, "assessment": {"fields": {"answer": {"status": "partial", "score": 0.5}}}}\n'
    q = question("custom", checker=checker,
                 tests=[case("x", {"answer": {"status": "partial", "score": 0.5}}, score=0.5)])
    result = run_question(q, ".")[0]["actual"]
    assert result["show_score"] is True and result["status"] == "partial"
    # normalize_result in the actual grader rejects an out-of-range score.
    q["checker"] = 'def check(response, symbols):\n    return 2\n'
    with pytest.raises(AssertionError):
        run_question(q, ".")


def test_custom_json_response_computes_values_without_string_substitution():
    q = question("custom", checker='def check(r, s):\n    return bool(abs(r["point"]["x"] - Rational(1, 3)) < 1e-12)\n',
                 tests=[dict(name="point", response={"point": {"x": "radius", "y": 0}}, expect="correct")])
    run_question(q, ".", variables={"radius": Rational(1, 3)})


@pytest.mark.parametrize("mutation", [
    lambda c: c.pop("name"),
    lambda c: c.update(answers=[]),
    lambda c: c.update(answers={"unknown": "x"}),
    lambda c: c.update(expect=["correct", "wrong"]),
    lambda c: c.update(response={}),
    lambda c: c.update(typo=True),
    lambda c: c.update(score=2),
    lambda c: c.update(partial="yes"),
])
def test_malformed_tests_fail_closed(mutation):
    q = question(tests=[case("x^2")])
    mutation(q["tests"][0])
    with pytest.raises((ValueError, AssertionError)):
        run_question(q, ".")


def test_component_neutral_adapter_and_answer_notes():
    seen = []
    def grade(payload):
        seen.append(payload)
        return {"status": "correct", "score": 1, "answer-note": "prt-T"}
    run_declarative([{"name": "shared", "answers": {"ans": "teacher"},
                      "expect": {"status": "correct", "score": 1, "answer-note": "prt-T"}}],
                    grade, fields=["ans"], resolve=lambda value: "STACK:" + value)
    assert seen == [{"answers": {"ans": "STACK:teacher"}}]


def test_marker_order_and_literal_code():
    assert _teacher_fields("_[x[0]] vec[1, sin(x)] mat[1,2;3,4] \x60_[ignored]\x60") == [
        "x[0]", "1", "sin(x)", "1", "2", "3", "4", "ignored"]


def test_yaml_and_cli_failures_name_exercise_and_case(tmp_path):
    from ctm_checkers.math_exercise import authored
    path = tmp_path / "lesson.qmd"
    path.write_text('''\x60\x60\x60{math-exercise}
#| label: named-exercise
#| mode: numeric
#| tests:
#|   - name: incorrect author expectation
#|     answers: [raw("3")]
#|     expect: correct
Answer _[2].
\x60\x60\x60
''')
    q = list(authored.authored_questions(path))[0]
    assert q["question"] == "Answer _[2]."
    with pytest.raises(RuntimeError, match="named-exercise.*incorrect author expectation"):
        authored.run([str(path)])


def test_mutating_real_grade_is_detected(monkeypatch):
    import ctm_checkers.math_exercise as math
    q = question(tests=[case("x+1", "wrong")])
    run_question(q, ".")
    monkeypatch.setattr(math, "check", lambda request: {"status": "correct", "score": 1})
    with pytest.raises(AssertionError, match="expected wrong"):
        run_question(q, ".")


def test_verdicts_for_fields_named_like_result_keys_are_not_overall_settings():
    q = question(teacher=["x", "x^2"], **{"field-labels": "status,score"},
                 tests=[dict(name="reserved labels", answers={"status": "x", "score": "x+1"},
                             expect={"status": "correct", "score": "wrong"})])
    run_question(q, ".")


def test_duplicate_yaml_expectations_are_rejected():
    q = question(tests="- name: duplicate\n  answers: [x^2]\n  expect: wrong\n  expect: correct\n")
    with pytest.raises(ValueError, match="duplicate tests key"):
        run_question(q, ".")


def test_empty_or_nan_expectation_cannot_pass():
    q = question(tests=[case("x^2", {})])
    with pytest.raises(ValueError):
        run_question(q, ".")
    with pytest.raises(AssertionError):
        run_declarative([dict(name="bad score", answers=[], score=1)],
                        lambda payload: {"status": "correct", "score": float("nan")})


@pytest.mark.parametrize("expected", [None, "", [], {}])
def test_null_or_empty_explicit_expectation_never_passes(expected):
    with pytest.raises(ValueError, match="null or empty"):
        run_declarative([dict(name="false green", response={}, expect=expected)],
                        lambda payload: {"status": "wrong", "score": 0})


@pytest.mark.parametrize("source", [
    "sqrt(raw('2+2'))", "Matrix([[raw('2+2')]])",
    "1+raw('2')", "raw('2')^2", "sqrt(value)", "Matrix(value)",
])
def test_raw_and_variable_strings_cannot_reach_sympy_functions(source):
    with pytest.raises(ValueError, match="raw|strings"):
        expression(source, {"value": ["2+2"]})


def test_raw_caret_is_literal_and_computed_power_keeps_precedence():
    assert expression('raw("a^b")') == "a^b"
    assert expression("2*3^2") == 18
    with pytest.raises(ValueError):
        expression("value", {"value": "2+2"})


@pytest.mark.parametrize("partial,expected,score", [("false", "wrong", 0), ("true", "partial", 0.5)])
def test_overall_aggregation_matches_browser_partial_credit_option(partial, expected, score):
    q = question(teacher=["x", "x^2"], **{"field-labels": "a,b", "partial-credit": partial},
                 tests=[dict(name="mixed aggregate", answers=["x", "x+1"], expect=expected, score=score)])
    run_question(q, ".")


@pytest.mark.parametrize("text", ["", "  "])
def test_empty_fields_are_not_sent_to_python_grading(text, monkeypatch):
    import ctm_checkers.math_exercise as math
    def unexpected(request):
        raise AssertionError("empty transport must not invoke a grader")
    monkeypatch.setattr(math, "check", unexpected)
    monkeypatch.setattr(math, "check_custom", unexpected)
    q = question(tests=[case(Raw(text), ["empty"])])
    run_question(q, ".")
    q = question("custom", checker="def check(r,s): return True", tests=[case(Raw(text), "empty")])
    run_question(q, ".")


def test_string_answers_are_trimmed_like_browser_fields():
    run_question(question("string", teacher=["Hello"], tests=[case('raw(" Hello ")')]), ".")


@pytest.mark.parametrize("filename", ["-assertions.py", "[assertions].py"])
def test_legacy_sidecar_names_are_not_misclassified_as_yaml(tmp_path, filename):
    (tmp_path / filename).write_text("def test(check, symbols):\n    assert check({}, symbols)\n")
    run_question(question("custom", checker="def check(r,s): return True", tests=filename), tmp_path)


@pytest.mark.parametrize("source,keys", [
    ("\x60_[1]\x60", ["1"]), ("\\_[1]", ["1"]), ("αvec[1,2]", ["1","2"]),
    ("avec[1,2] _[3]", ["3"]), ("_[unclosed _[4]", ["4"]),
])
def test_marker_extraction_matches_current_lua_renderer(source, keys):
    assert _teacher_fields(source) == keys


@pytest.mark.parametrize("credit,score", [("0", 0), ("2", 0.5), ("bad", 0.5), ("nan", 0.5), ("inf", 0.5)])
def test_form_credit_matches_browser_finite_credit(credit, score):
    q = question("exact", teacher=["1/2"], **{"partial-credit": "true", "form-credit": credit},
                 tests=[case("raw('2/4')", score=score)])
    # score=0 is wrong; otherwise the native detail remains not_exact.
    q["tests"][0]["expect"] = "wrong" if score == 0 else "partial"
    run_question(q, ".")
