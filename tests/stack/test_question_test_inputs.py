"""Question tests compute their inputs as STACK does (questiontest.php,
compute_response; STACK 10d3233) and the computed value is a student's answer
(S-13, AC's decision of 21 Oct 2026):

1. the question variables, then every input's name bound to its teacher's
   answer (`ans1: ta`): `ans1-x^2+x^2` is `ta`, `ans1+1` is `ta+1`;
2. each test input is computed with these values, without simplifying;
3. the computed value goes through the input's validation like a student's
   answer: `sinx` and `abc*0+ta` (the unsimplified value keeps `abc`) are
   invalid, and a test that expects a score then fails as invalid.

The outcomes below are native STACK's (its question test results for the
question here, STACK 10d3233 with Maxima 5.46: tests 1 to 3 pass, 4 and 5 fail
as invalid)."""
from pathlib import Path

import pytest

from ctm_checkers.stack.engine import instantiate, run_question_tests, validate
from ctm_checkers.stack.importer import import_xml

ROOT = Path(__file__).resolve().parents[2]

HEAD = """<?xml version="1.0" encoding="UTF-8"?>
<!-- Question tests that compute their inputs from the teacher's answer. AGPL-3.0-or-later. -->
<quiz><question type="stack">
<name><text>question-test-inputs</text></name>
<questionvariables><text>k: 3; ta: k*x^2;</text></questionvariables>
<questiontext format="html"><text><![CDATA[<p>[[input:ans1]] [[validation:ans1]] [[feedback:prt1]]</p>]]></text></questiontext>
<defaultgrade>1</defaultgrade><penalty>0.1</penalty><questionsimplify>1</questionsimplify>
<input><name>ans1</name><type>algebraic</type><tans>ta</tans><insertstars>0</insertstars></input>
<prt><name>prt1</name><value>1</value><autosimplify>1</autosimplify>
<node><name>0</name><answertest>AlgEquiv</answertest><sans>ans1</sans><tans>ta</tans><truescoremode>=</truescoremode><truescore>1</truescore><truenextnode>-1</truenextnode><trueanswernote>prt1-T</trueanswernote><falsescoremode>=</falsescoremode><falsescore>0</falsescore><falsenextnode>-1</falsenextnode><falseanswernote>prt1-F</falseanswernote></node></prt>
"""
TEST = ("<qtest><testcase>{n}</testcase><testinput><name>ans1</name><value>{value}</value></testinput>"
        "<expected><name>prt1</name><expectedscore>{score}</expectedscore><expectedpenalty>{penalty}</expectedpenalty>"
        "<expectedanswernote>prt1-{note}</expectedanswernote></expected></qtest>\n")

# (test input, expected score, STACK passes the test, the input's validation message)
CASES = [
    ("ta", 1, True, ""),
    ("ans1-x^2+x^2", 1, True, ""),                 # the teacher's answer (ans1), not a symbol named ans1
    ("ans1+1", 0, True, ""),
    ("abc*0+ta", 1, False, "Forbidden variable or constant: abc."),   # the unsimplified value names abc
    ("sinx", 0, False, "Forbidden variable or constant: sinx."),
]


def question():
    xml = HEAD + "".join(TEST.format(n=n, value=value, score=score, penalty=0 if score else 0.1, note="T" if score else "F")
                         for n, (value, score, _, _) in enumerate(CASES, 1)) + "</question></quiz>"
    return import_xml(xml)[0]


@pytest.mark.parametrize("seed", [1, 2, 17])
def test_question_tests_compute_their_inputs_as_stack_does(seed):
    results = run_question_tests(question(), seeds=[seed])["results"]
    assert len(results) == len(CASES)
    for result, (value, _, passes, message) in zip(results, CASES):
        actual = result["actual"]["inputs"]["ans1"]
        assert result["passed"] is passes, value
        assert actual["valid"] is (message == ""), value
        assert actual["feedback"] == message, value
        if message:
            assert result["actual"]["status"] == "invalid" and result["actual"]["prts"] == {}, value


def test_an_input_name_is_its_teachers_answer():
    results = run_question_tests(question())["results"]
    # ans1 is k*x^2 with k = 3: the computed inputs are the teacher's answer, not the symbol ans1.
    assert results[1]["inputs"]["ans1"] == "3*x**2"
    assert results[2]["inputs"]["ans1"] == "3*x**2 + 1"
    assert results[1]["actual"]["prts"]["prt1"]["score"] == 1.0
    assert results[2]["actual"]["prts"]["prt1"]["score"] == 0.0


def test_a_student_still_may_not_type_the_question_variables():
    q = question()
    variant = instantiate(q, 1)
    for answer, message in (("ta", "Forbidden variable or constant: ta."), ("k*x^2", "Forbidden variable or constant: k.")):
        checked = validate(q, {"ans1": answer}, variant=variant)["inputs"]["ans1"]
        assert not checked["valid"] and checked["feedback"] == message, answer


def test_algmap_1_6_types_ans_plus_1_and_its_question_tests_pass():
    # The corpus question's second test types ans+1, the input's own name: the
    # computed input is the teacher's answer plus 1 (9, 9, 17 at the deployed
    # seeds), which is valid, and the test passes.
    q = import_xml(ROOT / "examples" / "stack" / "corpus" / "AlgMap-1-6.xml")[0]
    for seed, computed in ((1536647851, "9"), (1858711800, "9"), (891319547, "17")):
        tested = run_question_tests(q, seeds=[seed])
        assert tested["passed"], seed
        second = [r for r in tested["results"] if r["testcase"] == "2"][0]
        assert second["inputs"] == {"ans": computed} and second["actual"]["inputs"]["ans"]["valid"], seed
    variant = instantiate(q, 1536647851)
    assert validate(q, {"ans": "ans + 1"}, variant=variant)["inputs"]["ans"]["feedback"] == "Forbidden variable or constant: ans."
