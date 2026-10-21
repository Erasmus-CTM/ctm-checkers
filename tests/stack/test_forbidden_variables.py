"""S-01 (ctm-checkers 0.3.0): a student may not use the names of question
variables or feedback variables. STACK: "If the teacher defines 'ta' to be
the answer, the student could type in 'ta'! We forbid this."
(question.php:430-441, cassecurity.class.php:373-376), with the validation
error "Forbidden variable or constant: …" and no preview. Question tests
still resolve those names on the author's side (_qtest_answer).

tools/stack_native/check_validation.py compares the golden rows of such
answers with native STACK's own validation (native-stack.yml)."""
import json
from pathlib import Path

import pytest

import golden
from ctm_checkers.stack import engine
from ctm_checkers.stack.engine import grade, instantiate, run_question_tests, validate
from ctm_checkers.stack.expressions import parse
from ctm_checkers.stack.importer import import_xml

ROOT = Path(__file__).resolve().parents[2]
STACK = ROOT / "examples" / "stack"


def message(*names):
    return " ".join(f"Forbidden variable or constant: {name}." for name in names)


def question(name, checkers=None):
    return import_xml(STACK / name, python_checkers=STACK / checkers if checkers else None)[0]


# The leak cases of the stack-sympy audit (probes/leak.py): each answer scored
# full marks and its preview showed the variable's value.
LEAKS = [
    ("polynomial-expansion.xml", None, {"ans": "ta"}),
    ("rational-equivalence.xml", None, {"ans": "ta"}),
    ("zero-product.xml", None, {"ans": "ta"}),
    ("numerical-measurement.xml", None, {"perimeter": "ta_perimeter", "area": "ta_area"}),
    ("course-b-rank-pivots.xml", None, {"rankans": "r", "pivots": "P"}),
    ("determinant-one.xml", "matrix-checkers.py", {"ans": "T"}),
    ("python-checker.xml", "checkers.py", {"ans": "d"}),
]


@pytest.mark.parametrize("name, checkers, answers", LEAKS, ids=[case[0] for case in LEAKS])
def test_the_leak_cases_are_invalid_without_a_preview(name, checkers, answers):
    q = question(name, checkers)
    variant = instantiate(q, 1)
    answers = {**{i["name"]: answers.get(i["name"], "1") for i in q["inputs"]}, **answers}
    checked = validate(q, answers, variant=variant)
    graded = grade(q, answers, variant=variant)
    assert checked["status"] == "invalid" and graded["status"] == "invalid" and graded["score"] == 0.0
    assert graded["prts"] == {}
    for key, text in answers.items():
        if text in variant["env"]:
            assert checked["inputs"][key] == {"valid": False, "latex": "", "feedback": message(text)}
            assert graded["inputs"][key] == checked["inputs"][key]


@pytest.mark.parametrize("name, checkers, answers", LEAKS, ids=[case[0] for case in LEAKS])
def test_question_tests_still_pass(name, checkers, answers):
    # Their inputs name question variables (polynomial-expansion's ta,
    # rational-equivalence's m and n, ...) or give values; both still pass.
    q = question(name, checkers)
    for seed in (1, 2, 3):
        assert run_question_tests(q, seeds=[seed])["passed"], seed


SUPPLEMENT = "supplement/forbidden-variables.xml"   # k, f, ta; feedback variables d, sa


@pytest.mark.parametrize("answer, names", [
    ("ta", ["ta"]), ("k*2*x+1", ["k"]), ("2ta-ta", ["ta"]),         # alone, inside, implied product, twice
    ("d", ["d"]), ("sa", ["sa"]),                                    # feedback variables
    ("d+0*f", ["d", "f"]), ("[f,ta]", ["f", "ta"]), ("x=k", ["k"]),  # in order of appearance
])
def test_question_and_feedback_variables(answer, names):
    q = question(SUPPLEMENT)
    variant = instantiate(q, 1)
    checked = validate(q, {"ans1": answer}, variant=variant)["inputs"]["ans1"]
    assert checked == {"valid": False, "latex": "", "feedback": message(*names)}
    assert grade(q, {"ans1": answer}, variant=variant)["status"] == "invalid"


@pytest.mark.parametrize("answer, score", [("6*x+1", 1.0), ("6x+1", 1.0), ("TA", 0.0), ("tab", 0.0), ("D", 0.0), ("x", 0.0)])
def test_other_names_stay_answers(answer, score):
    # Names are compared exactly, as STACK's forbidden keys are (TA and tab are no question variable).
    q = question(SUPPLEMENT)
    graded = grade(q, {"ans1": answer}, variant=instantiate(q, 1))
    assert graded["status"] == "graded" and graded["score"] == score


def test_the_supplements_question_tests_use_the_names():
    q = question(SUPPLEMENT)
    result = run_question_tests(q)
    assert result["passed"] and [r["inputs"]["ans1"] for r in result["results"]] == ["6*x + 1", "3*x**2 + x"]


def test_the_message_is_stacks():
    # lang/en/qtype_stack.php: $string['stackCas_forbiddenVariable'] = 'Forbidden variable or constant: {$a->forbid}.';
    assert engine.FORBIDDEN_VARIABLE.format(name="ta") == "Forbidden variable or constant: ta."


def names_of(text, insertstars):
    try:
        tree = parse(text, insertstars=insertstars)
    except Exception:
        return []
    return [node.value for node in engine._walk(tree) if node.kind == "name"]


def test_golden_answer_rows():
    # The golden tables: an answer that names a question or feedback variable is
    # invalid with that message, and S-01 changed no other row.
    questions, variants, rows = {}, {}, 0
    for path in golden.table_files():
        if not path.relative_to(golden.GOLDEN).as_posix().startswith("stack/"):
            continue
        for row in golden.read_rows(path):
            if row["call"] != "stack.answer":
                assert "S-01" not in row.get("changes", []), row["id"]
                continue
            value = row["input"]
            key = (value["file"], value.get("python_checkers"))
            if key not in questions:
                checkers = value.get("python_checkers")
                questions[key] = {q["name"]: q for q in import_xml(ROOT / value["file"], python_checkers=ROOT / checkers if checkers else None)}
            q = questions[key][value["question"]]
            if key + (q["name"], value["seed"]) not in variants:
                variants[key + (q["name"], value["seed"])] = instantiate(q, value["seed"])
            variant = variants[key + (q["name"], value["seed"])]
            forbidden = engine._author_names(q, variant["env"])
            inputs = {i["name"]: i for i in q["inputs"]}
            used = {name: [n for n in names_of(text, inputs[name].get("insertstars", 0)) if n in forbidden]
                    for name, text in value["answers"].items() if name in inputs}
            checked = row["output"]["validate"]["inputs"]
            for name, found in used.items():
                if found:
                    assert checked[name] == {"valid": False, "latex": "", "feedback": message(*dict.fromkeys(found))}, row["id"]
                else:
                    assert not checked[name]["feedback"].startswith("Forbidden variable"), row["id"]
            assert ("S-01" in row.get("changes", [])) <= any(used.values()), row["id"]
            rows += any(used.values())
    assert rows >= 372
