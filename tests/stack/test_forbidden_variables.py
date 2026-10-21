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


STACK_PARTS = {"ta_perimeter": "perimeter", "ta_area": "area"}


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
            # STACK checks ta_perimeter part by part and forbids perimeter, a
            # name of three letters or more (S-13, 0.6.0; before: ta_perimeter).
            named = STACK_PARTS.get(text, text)
            assert checked["inputs"][key] == {"valid": False, "latex": "", "feedback": message(named)}
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


@pytest.mark.parametrize("answer, score", [("6*x+1", 1.0), ("6x+1", 1.0), ("TA", 0.0), ("ta1", 0.0), ("D", 0.0), ("x", 0.0)])
def test_other_names_stay_answers(answer, score):
    # Names are compared exactly (TA and ta1 are
    # no question variable; tab, a name of three letters, is forbidden since S-13).
    q = question(SUPPLEMENT)
    graded = grade(q, {"ans1": answer}, variant=instantiate(q, 1))
    assert graded["status"] == "graded" and graded["score"] == score


def test_the_supplements_question_tests_use_the_names():
    q = question(SUPPLEMENT)
    result = run_question_tests(q)
    assert result["passed"] and [r["inputs"]["ans1"] for r in result["results"]] == ["6*x + 1", "3*x**2 + x"]


PRTS = "supplement/forbidden-variables-prts.xml"   # prt1: d; sa (semicolons); prt2: w, zz (a newline)


@pytest.mark.parametrize("answer, names", [
    ("w", ["w"]), ("zz", ["zz"]),                  # the second response tree's, separated by a newline
    ("sa+zz", ["sa", "zz"]), ("d*w", ["d", "w"]),  # both trees' at once
])
def test_the_feedback_variables_of_every_response_tree(answer, names):
    # The review of S-01: reading only the first tree's feedback variables, or
    # splitting them only at semicolons, left w and zz typeable (w scored 0.5).
    q = question(PRTS)
    variant = instantiate(q, 1)
    assert validate(q, {"ans1": answer}, variant=variant)["inputs"]["ans1"] == {"valid": False, "latex": "", "feedback": message(*names)}
    assert engine._author_names(q, variant["env"]) == {"k", "f", "ta", "d", "sa", "w", "zz"}
    assert run_question_tests(q)["passed"]


@pytest.mark.parametrize("source, statements", [
    ("a:1; b:2", [("a", "1"), ("b", "2")]),
    ("a:1\nb:2", [("a", "1"), ("b", "2")]),
    ("a:1;\n\n b : x+1 ;", [("a", "1"), ("b", "x+1")]),
    ("a:1; 2+3", [("a", "1"), (None, "2+3")]),
])
def test_assignment_statements(source, statements):
    # One grammar for the assignments and the names they write (_author_names).
    from ctm_checkers.stack.expressions import assignment_statements
    assert list(assignment_statements(source)) == statements


CLASH = "supplement/teacher-answer-clash.xml"   # ta: t^2+1 with a feedback variable t


def clash_question(variables, feedback, teacher="ta"):
    q = question(CLASH)
    q["variables"] = variables
    q["prts"][0]["feedbackvariables"] = feedback
    q["inputs"][0]["teacher"] = teacher
    return q


@pytest.mark.parametrize("variables, feedback, teacher, names", [
    ("ta:t^2+1;", "t:2; sa:ans1;", "ta", "t"),                         # a feedback variable (the supplement question)
    ("ta:[t,{u+1}];", "t:2\nu:3", "ta", "t, u"),                        # inside collections, newline-separated
    ("k:2;", "sa:ans1; t:1;", "matrix([1,t],[0,k])", "t"),             # a matrix teacher's answer
])
def test_a_teacher_answer_a_student_cannot_type_stops_the_build(variables, feedback, teacher, names):
    # The review of S-01 (should-fix 3): such a question had no answer a
    # student could enter; the build now says so (before: only if a question
    # test happened to cover it).
    q = clash_question(variables, feedback, teacher)
    with pytest.raises(engine.UnsupportedQuestion, match=r"input\[ans1\]/tans: the teacher's answer uses " + names + ","):
        instantiate(q, 1)


def test_a_teacher_answer_with_other_names_builds():
    q = clash_question("ta:t^2+1;", "s:2; sa:ans1;")
    variant = instantiate(q, 1)
    assert grade(q, {"ans1": "t^2+1"}, variant=variant)["score"] == 1.0


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
                # Only the build of a question whose teacher's answer uses such a name (0.4.0).
                assert "S-01" not in row.get("changes", []) or (
                    row["call"] == "stack.instantiate" and "(S-01)" in row["output"].get("raised", "")), row["id"]
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
                    # Each name, or with S-13 (0.6.0) the part STACK forbids (ta_perimeter: perimeter).
                    feedback = checked[name]["feedback"]
                    assert not checked[name]["valid"] and checked[name]["latex"] == "", row["id"]
                    assert all(any(message(part) in feedback for part in [n] + n.split("_")) for n in found), row["id"]
            assert ("S-01" in row.get("changes", [])) <= any(used.values()), row["id"]
            rows += any(used.values())
    assert rows >= 372
