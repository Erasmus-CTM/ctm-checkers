"""Conservative adapter for Moodle STACK XML exports.

The output contains only JSON values and retains the source for diagnostics.
Unsupported assessment semantics raise a contextual error at build time.
"""

from __future__ import annotations

import re
import math
from pathlib import Path
from xml.etree import ElementTree as ET


NAME = re.compile(r"^[A-Za-z][A-Za-z0-9_]*$")
TESTS = {"AlgEquiv", "Sets", "SameType", "EqualComAss", "FacForm", "SingleFrac", "LowestTerms",
         "NumAbsolute", "NumRelative", "NumDecPlaces"}
TESTS |= {"PythonChecker"}
INPUT_TYPES = {"algebraic", "numerical", "matrix"}

# The question-level options of a STACK question that the engine does not
# read (S-07): the values it can honour, the default first. A question that
# sets another value would be graded or displayed as if it had not, so the
# build stops. An absent option is the default. The second value of the last
# two options only changes how a question writes products and matrices; the
# engine writes both its own way, and the example questions use those values.
QUESTION_OPTIONS = {
    "complexno": ("i",),
    "decimals": (".",),
    "scientificnotation": ("*10",),
    "inversetrig": ("cos-1",),
    "logicsymbol": ("lang",),
    "sqrtsign": ("1",),
    "multiplicationsign": ("dot", "none"),
    "matrixparens": ("[", "("),
}


def _matrix_config(q, element, where):
    """Explicit port extension: bounded learner dimensions, never native options."""
    matrix = element.find("matrix")
    if matrix is None:
        return None  # Native matrix inputs use the evaluated teacher's shape.
    _check(q, where + "/matrix", not matrix.attrib and len(matrix) == 2
           and {axis.tag for axis in matrix} == {"rows", "cols"},
           "matrix requires exactly rows and cols")
    result = {}
    for axis in matrix:
        _check(q, where + "/matrix/" + axis.tag,
               set(axis.attrib) == {"initial", "min", "max", "resizable"} and not len(axis),
               "axis requires initial, min, max and resizable attributes")
        values = {}
        for key in ("initial", "min", "max"):
            raw = axis.get(key, "")
            _check(q, where + "/matrix/" + axis.tag, bool(re.fullmatch(r"[0-9]+", raw)),
                   "matrix dimensions must be positive integers")
            values[key] = int(raw)
        _check(q, where + "/matrix/" + axis.tag,
               1 <= values["min"] <= values["initial"] <= values["max"] <= 16,
               "matrix dimensions require 1 <= min <= initial <= max <= 16")
        _check(q, where + "/matrix/" + axis.tag, axis.get("resizable") in {"0", "1"},
               "resizable must be 0 or 1")
        values["auto"] = axis.get("resizable") == "1"
        _check(q, where + "/matrix/" + axis.tag,
               values["auto"] or values["min"] == values["initial"] == values["max"],
               "fixed dimensions require min = initial = max")
        result[axis.tag] = values
    _check(q, where + "/matrix", result["rows"]["max"] * result["cols"]["max"] <= 64,
           "matrix maximum dimensions exceed 64 entries")
    return result


class UnsupportedQuestion(ValueError):
    def __init__(self, question: str, location: str, reason: str):
        self.question, self.location, self.reason = question, location, reason
        super().__init__(f"{question}: {location}: {reason}")


def _text(element, path, default=""):
    found = element.find(path)
    return default if found is None or found.text is None else found.text


def _rich(element, path):
    return _text(element, f"{path}/text")


def _check(question, location, condition, reason):
    if not condition:
        raise UnsupportedQuestion(question, location, reason)


def _boolean(q, element, field, default="0"):
    value = _text(element, field, default).strip()
    _check(q, field, value in {"0", "1"}, "expected 0 or 1")
    return value == "1"


def _number(q, element, field, default="0"):
    raw = _text(element, field, default).strip()
    try:
        value = float(raw or default)
    except ValueError as exc:
        raise UnsupportedQuestion(q, field, f"invalid number {raw!r}") from exc
    _check(q, field, math.isfinite(value), "number must be finite")
    return value


def _node(q, prtname, element):
    where = f"prt[{prtname}]/node[{_text(element, 'name')} ]".replace(" ]", "]")
    test = _text(element, "answertest").strip()
    _check(q, where + "/answertest", test in TESTS, f"unsupported answer test {test!r}")
    node = {
        "name": _text(element, "name").strip(),
        "test": test,
        "student": _text(element, "sans").strip(),
        "teacher": _text(element, "tans").strip(),
        "options": _text(element, "testoptions").strip(),
        "quiet": _boolean(q, element, "quiet"),
    }
    _check(q, where + "/name", node["name"].isdigit(), "node name must be a nonnegative integer")
    for branch in ("true", "false"):
        mode = _text(element, branch + "scoremode", "=").strip()
        _check(q, where + "/" + branch + "scoremode", mode in {"=", "+", "-"}, f"unsupported scoring mode {mode!r}")
        nextnode = _text(element, branch + "nextnode", "-1").strip()
        _check(q, where + "/" + branch + "nextnode", re.fullmatch(r"-?\d+", nextnode), "invalid next node")
        penalty = _text(element, branch + "penalty").strip()
        _check(q, where + "/" + branch + "penalty", not penalty, "branch-specific penalties are unsupported")
        node[branch] = {
            "mode": mode,
            "score": _number(q, element, branch + "score"),
            "next": int(nextnode),
            "note": _text(element, branch + "answernote").strip(),
            "feedback": _rich(element, branch + "feedback"),
        }
    return node


def _prt(q, element):
    name = _text(element, "name").strip()
    _check(q, "prt/name", bool(NAME.fullmatch(name)), f"invalid response tree name {name!r}")
    nodes = [_node(q, name, n) for n in element.findall("node")]
    ids = {n["name"] for n in nodes}
    _check(q, f"prt[{name}]", bool(nodes) and len(nodes) == len(ids) and "0" in ids,
           "requires unique node names and root node 0")
    _check(q, f"prt[{name}]/feedbackstyle", _text(element, "feedbackstyle", "1").strip() == "1",
           "unsupported feedback style")
    edges = {}
    for node in nodes:
        edges[node["name"]] = []
        for branch in ("true", "false"):
            nextnode = node[branch]["next"]
            _check(q, f"prt[{name}]/node[{node['name']}]/{branch}nextnode",
                   nextnode == -1 or str(nextnode) in ids, "dangling next node")
            if nextnode >= 0:
                edges[node["name"]].append(str(nextnode))
    active, done = set(), set()
    def visit(identifier):
        _check(q, f"prt[{name}]/node[{identifier}]", identifier not in active, "cycle in response tree")
        if identifier in done:
            return
        active.add(identifier)
        for dest in edges[identifier]:
            visit(dest)
        active.remove(identifier)
        done.add(identifier)
    visit("0")
    _check(q, f"prt[{name}]", len(done) == len(nodes), "unreachable node")
    return {"name": name, "value": _number(q, element, "value", "1"),
            "autosimplify": _boolean(q, element, "autosimplify", "1"),
            "feedbackvariables": _rich(element, "feedbackvariables"), "nodes": nodes}


def _input(q, element):
    name = _text(element, "name").strip()
    where = f"input[{name}]"
    typ = _text(element, "type").strip()
    _check(q, where, bool(NAME.fullmatch(name)) and typ in INPUT_TYPES,
           f"unsupported input name or type {name!r}/{typ!r}")
    stars = _text(element, "insertstars", "0").strip()
    _check(q, where + "/insertstars", stars in {"0", "1"},
           f"unsupported multiplication insertion mode {stars!r}; only 0 (explicit *) and 1 (adjacent implied products) are supported")
    _check(q, where + "/strictsyntax", _text(element, "strictsyntax", "1").strip() == "1", "non-strict syntax is unsupported")
    _check(q, where + "/allowwords", not _text(element, "allowwords").strip(), "allowwords is unsupported")
    _check(q, where + "/syntaxattribute", _text(element, "syntaxattribute", "0").strip() == "0", "syntax attributes are unsupported")
    _check(q, where + "/options", not _text(element, "options").strip(), "input-specific options are unsupported")
    forbidwords = [x for x in re.split(r"[,\s]+", _text(element, "forbidwords").strip()) if x]
    box = _text(element, "boxsize", "15").strip()
    _check(q, where + "/boxsize", bool(re.fullmatch(r"\d+", box)) and 1 <= int(box) <= 200,
           "boxsize must be an integer between 1 and 200")
    show = _text(element, "showvalidation", "1").strip()
    _check(q, where + "/showvalidation", show in {"0", "1", "3"}, f"unsupported validation style {show!r}")
    result = {"name": name, "type": typ, "teacher": _text(element, "tans").strip(),
            "boxsize": int(box),
            "strictsyntax": _boolean(q, element, "strictsyntax", "1"),
            "insertstars": int(stars),
            "forbidwords": forbidwords,
            "forbidfloat": _boolean(q, element, "forbidfloat"),
            "requirelowestterms": _boolean(q, element, "requirelowestterms"),
            "checkanswertype": _boolean(q, element, "checkanswertype"),
            "mustverify": _boolean(q, element, "mustverify"),
            "showvalidation": show != "0",
            "syntaxhint": _text(element, "syntaxhint")}
    if element.find("matrix") is not None:
        _check(q, where, typ == "matrix", "matrix configuration requires matrix input type")
    if typ == "matrix":
        result["matrix"] = _matrix_config(q, element, where)
    return result


def _question_options(name, element):
    """S-07: a question option the engine does not read must be STACK's default
    (or a value that changes only how the question writes things): the build
    stops with every option that is not, and the values it supports."""
    unsupported = []
    for option, supported in QUESTION_OPTIONS.items():
        found = element.find(option)
        if found is not None and (found.text or "").strip() not in supported:
            unsupported.append((option, (found.text or "").strip(), supported))
    if unsupported:
        raise UnsupportedQuestion(
            name, "question/" + unsupported[0][0],
            "unsupported question option" + ("s: " if len(unsupported) > 1 else ": ")
            + "; ".join(f"{option} is {value!r}, the engine supports " + " and ".join(repr(v) for v in supported)
                        for option, value, supported in unsupported)
            + ". The engine does not read these options, so the question would be graded as if they were not set")


def _question(element):
    name = _text(element, "name/text", "(unnamed)").strip()
    if element.get("type") != "stack":
        raise UnsupportedQuestion(name, "question/@type", f"unsupported question type {element.get('type')!r}")
    _question_options(name, element)
    inputs = [_input(name, x) for x in element.findall("input")]
    prts = [_prt(name, x) for x in element.findall("prt")]
    _check(name, "inputs", bool(inputs) and len({x["name"] for x in inputs}) == len(inputs), "requires unique inputs")
    _check(name, "prts", len({x["name"] for x in prts}) == len(prts), "requires unique response trees")
    for prt in prts:
        for node in prt["nodes"]:
            _check(name, f"prt[{prt['name']}]/node[{node['name']}]/sans", bool(node["student"]), "empty student expression")
            if node["test"] == "PythonChecker":
                from .check import checker_spec
                try:
                    checker_spec(node["options"])
                except ValueError as exc:
                    raise UnsupportedQuestion(name, f"prt[{prt['name']}]/node[{node['name']}]/testoptions", str(exc)) from exc
                _check(name, f"prt[{prt['name']}]/node[{node['name']}]/sans",
                       node["student"] in {inp["name"] for inp in inputs},
                       "PythonChecker requires a direct input name")
            if node["test"] in {"EqualComAss", "FacForm", "SingleFrac", "LowestTerms"}:
                _check(name, f"prt[{prt['name']}]/node[{node['name']}]/sans",
                       node["student"] in {inp["name"] for inp in inputs},
                       f"{node['test']} requires a direct input to preserve answer form")
    qtests = []
    for test in element.findall("qtest"):
        qtests.append({"testcase": _text(test, "testcase"),
                       "description": _text(test, "description"),
                       "inputs": {_text(v, "name"): _text(v, "value") for v in test.findall("testinput")},
                       "expected": {_text(v, "name"): {
                           "score": _number(name, v, "expectedscore"),
                           "penalty": _number(name, v, "expectedpenalty"),
                           "note": _text(v, "expectedanswernote").strip()}
                           for v in test.findall("expected")}})
    return {"name": name, "questiontext": _rich(element, "questiontext"),
            "generalfeedback": _rich(element, "generalfeedback"),
            "specificfeedback": _rich(element, "specificfeedback"),
            "questionnote": _rich(element, "questionnote"),
            "variables": _rich(element, "questionvariables"),
            "defaultgrade": _number(name, element, "defaultgrade", "1"),
            "penalty": _number(name, element, "penalty"),
            "simplify": _boolean(name, element, "questionsimplify", "1"),
            "assumepositive": _boolean(name, element, "assumepositive"),
            "assumereal": _boolean(name, element, "assumereal"),
            "inputs": inputs, "prts": prts, "qtests": qtests,
            "deployedseeds": [int(s.text) for s in element.findall("deployedseed") if s.text]}


def import_xml(source: str | Path, *, checker: str | None = None, checker_value=1, tests=None) -> list[dict]:
    """Read a STACK Moodle XML path or XML string, omitting category entries.

    Description questions are omitted as presentational Moodle content. Every
    other unknown question type raises instead of being silently translated.
    """
    if isinstance(source, Path) or (isinstance(source, str) and not source.lstrip().startswith("<")):
        root = ET.parse(source).getroot()
    else:
        root = ET.fromstring(source)
    if root.tag != "quiz":
        raise ValueError("STACK XML requires a <quiz> root")
    if checker is not None:
        from .check import validate_source
        validate_source(checker)
        if type(checker_value) not in (int, float) or not math.isfinite(checker_value) or checker_value <= 0:
            raise ValueError('checker-value must be a positive finite number')
    result = []
    for q in root.findall("question"):
        if q.get("type") in {"category", "description"}:
            continue
        question = _question(q)
        if checker is not None:
            _check(question['name'], 'checker', not any(p['name'] == 'checker' for p in question['prts']),
                   'The checker response-tree name is reserved when a block checker is present')
            question.update(checker=checker, checker_value=checker_value)
        _check(question['name'], 'prts', bool(question['prts']) or bool(checker), 'requires response trees or a block checker:')
        if tests is not None:
            question['authored_tests'] = tests
        result.append(question)
    return result
