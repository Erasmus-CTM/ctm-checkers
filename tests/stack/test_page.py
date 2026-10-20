"""The page's STACK calls (ctm_checkers.stack.page, browser.call "stack.*").

They are stack-sympy's worker requests: the engine's calls on the card's
question and variant, in the envelope {"ok": true, "result": ...}, or
{"ok": false, "error": ...} for a question the engine does not support; any
other exception reaches the page.
"""
import copy
import json
from pathlib import Path

import pytest

from ctm_checkers import browser
from ctm_checkers.stack import page
from ctm_checkers.stack.engine import grade, instantiate, run_question_tests, validate
from ctm_checkers.stack.importer import import_xml

ROOT = Path(__file__).resolve().parents[2]
QUESTION = import_xml(ROOT / "examples/stack/polynomial-expansion.xml")[0]
# A variant other than seed 1's: the calls use the card's variant, not a seed.
VARIANT = instantiate(QUESTION, 7)
ANSWERS = {"ans": "x^2+6*x+8"}


def request(**change):
    return {"question": QUESTION, "variant": VARIANT, "answers": ANSWERS, **change}


def roundtrip(value):
    return json.loads(json.dumps(value, default=str))


def test_the_calls_answer_for_the_cards_variant():
    assert VARIANT["env"] != instantiate(QUESTION, 1)["env"]
    assert page.validate(request()) == {"ok": True, "result": roundtrip(validate(QUESTION, ANSWERS, variant=VARIANT))}
    graded = page.grade(request())
    assert graded == {"ok": True, "result": roundtrip(grade(QUESTION, ANSWERS, variant=VARIANT))}
    assert graded["result"]["score"] == 1
    tests = page.tests(request(answers={}))
    assert tests == {"ok": True, "result": roundtrip(run_question_tests(QUESTION, variants=[VARIANT]))}
    assert tests["result"]["passed"] and {result["seed"] for result in tests["result"]["results"]} == {7}


def test_an_unsupported_question_is_an_envelope():
    question = copy.deepcopy(QUESTION)
    question["prts"][0]["nodes"][0]["test"] = "NumSigFigs"
    for call in (page.grade, page.tests):
        answer = call(request(question=question))
        assert answer["ok"] is False
        assert "Answer test 'NumSigFigs' is unsupported" in answer["error"]


def test_other_exceptions_reach_the_page():
    # As in stack-sympy's worker: only UnsupportedQuestion becomes an envelope.
    for call in (page.validate, page.grade):
        with pytest.raises(KeyError):
            call({"question": QUESTION, "variant": VARIANT})
    with pytest.raises(KeyError):
        page.tests({"question": QUESTION, "answers": {}})


def test_browser_call_has_no_admission_rule_for_stack():
    # STACK's grammar never evaluates learner text: a string that
    # math-exercise's admission rule rejects is the engine's to judge.
    for name in ("stack.validate", "stack.grade"):
        caller = {"_ctm_request": json.dumps(request(answers={"ans": "__import__('os')"}), default=str)}
        answer = json.loads(browser.call(name, caller))
        assert answer["ok"] is True
        assert answer["result"]["inputs"]["ans"]["valid"] is False
        assert "_ctm_request" not in caller
