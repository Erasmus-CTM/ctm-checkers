"""The shared execution seam preserves adapters' data and observable behavior."""
import copy

import pytest
from sympy import Matrix, Rational, Symbol

from ctm_checkers.core.custom import execute_checker
from ctm_checkers.math_exercise.custom import check_custom
from ctm_checkers.variants import question_context


def test_prepared_namespace_arguments_output_and_result_are_preserved(capsys):
    response = {"answer": object()}
    symbols = {"x": object()}
    scope = {"__name__": "author_namespace", "prepared_response": response,
             "prepared_symbols": symbols, "helper": lambda value: value + 1}
    source = """print("source output")
def check(response, symbols):
    print("checker output")
    assert __name__ == "author_namespace"
    assert response is prepared_response
    assert symbols is prepared_symbols
    return {"score": helper(0.25), "feedback": "visible", "show_score": False,
            "assessment": {"part": "kept"}}
"""
    # The existing normalizer rejects this score, after both prints. The core
    # must not swallow output or replace the caller's exception boundary.
    with pytest.raises(ValueError, match="Custom checker score must be between 0 and 1"):
        execute_checker(source, response, symbols, scope)
    assert capsys.readouterr().out == "source output\nchecker output\n"
    scope["helper"] = lambda value: value
    result = execute_checker(source, response, symbols, scope)
    assert result == {"status": "partial", "score": 0.25, "show_score": False,
                      "feedback": "visible", "assessment": {"part": "kept"}}
    assert scope["prepared_response"] is response
    assert scope["prepared_symbols"] is symbols
    assert capsys.readouterr().out == "source output\nchecker output\n"


@pytest.mark.parametrize("source,error,message", [
    ("check = 3", ValueError, "Custom checker must define check(expressions, symbols)"),
    ("pass", ValueError, "Custom checker must define check(expressions, symbols)"),
    ("raise RuntimeError('source failure')", RuntimeError, "source failure"),
    ("def check(response, symbols):\n    raise TypeError('call failure')", TypeError, "call failure"),
    ("def check(response, symbols):\n    return {'assessment': []}", TypeError,
     "Custom checker assessment must be a dictionary"),
    ("def check(response, symbols):\n    return {}", ValueError,
     "Custom checker result needs score or correct"),
])
def test_execution_and_normalization_exceptions_propagate(source, error, message):
    with pytest.raises(error) as caught:
        execute_checker(source, {}, {}, {})
    assert str(caught.value) == message


def test_base_exceptions_are_not_converted_into_checker_errors():
    with pytest.raises(SystemExit) as caught:
        execute_checker("raise SystemExit(7)", {}, {}, {})
    assert caught.value.code == 7


@pytest.mark.parametrize("value,status,score", [
    (True, "correct", 1.0), (False, "wrong", 0.0), (0.4, "partial", 0.4),
    ({"correct": True, "feedback": "ok"}, "correct", 1.0),
])
def test_existing_result_forms(value, status, score):
    result = execute_checker("def check(response, symbols):\n    return authored_result",
                             {}, {}, {"authored_result": value})
    assert result["status"] == status
    assert result["score"] == score


def test_math_keeps_its_error_boundary_and_prints(capsys):
    result = check_custom({"vars": "", "response": {},
                           "checker": "print('source output')\ndef check(response, symbols):\n    print('call output')\n    raise RuntimeError('same message')"})
    assert result == {"status": "error", "message": "same message"}
    assert capsys.readouterr().out == "source output\ncall output\n"
    result = check_custom({"vars": "", "response": {}, "checker": "check = 3"})
    assert result == {"status": "error", "message": "Custom checker must define check(expressions, symbols)"}


def test_math_keeps_request_local_namespaces():
    request = {"vars": "", "response": {}, "checker": """
seen = "_request_marker" in globals()
_request_marker = True
def check(response, symbols):
    return not seen
"""}
    assert check_custom(request)["status"] == "correct"
    assert check_custom(request)["status"] == "correct"


def test_math_keeps_exact_trusted_context_and_legacy_response_json():
    x = Symbol("x", positive=True)
    context = question_context(["Svar α"], {"x": x, "a": Rational(1, 3)},
                               {"Svar α": Matrix([[1, 2]])})
    request = {"vars": "x", "question_context": context,
               "response": {"kind": "expressions", "raw": ["x"],
                            "variables": {"spoof": True}},
               "checker": """
def check(response, symbols):
    assert symbols["x"].is_positive is True
    assert response["expressions"] == [symbols["x"]]
    assert response["answers"] == {"Svar α": symbols["x"]}
    assert response["variables"]["a"] == Rational(1, 3)
    assert response["teacher"]["Svar α"] == Matrix([[1, 2]])
    assert response["variant"] is None
    assert _math_vars == "x"
    assert _mj.loads(_math_response_json)["variables"] == {"spoof": True}
    response["raw"][0] = "changed"
    return True
"""}
    untouched = copy.deepcopy(request["response"])
    assert check_custom(request)["status"] == "correct"
    assert request["response"] == untouched
