"""Authored tests, shared by component adapters. AGPL-3.0-or-later.

run_tests preserves the legacy Python test(check, symbols) contract.
run_declarative resolves author inputs, calls the adapter's real grader and
checks only declared expectations; it never implements grading.
"""
import ast
import math
import io
import tokenize
from pathlib import Path


class Raw(str):
    """A student's literal input; do not compute or simplify it."""


def raw(value):
    if not isinstance(value, str):
        raise ValueError("raw() needs one string")
    return Raw(value)


def expression(value, variables=None):
    """Evaluate a test expression without feeding strings to sympify.

    Names come from question variables and a small SymPy function catalogue.
    This is author data, not a new student parser. raw() bypasses this step.
    """
    import sympy as sp
    if isinstance(value, Raw):
        return value
    if not isinstance(value, str):
        if isinstance(value, bool) or value is None:
            return value
        if isinstance(value, (int, float)):
            return sp.Rational(str(value))
        return value
    names = {name: getattr(sp, name) for name in (
        "sqrt", "sin", "cos", "tan", "asin", "acos", "atan", "atan2",
        "exp", "log", "Abs", "floor", "ceiling", "Min", "Max", "gcd",
        "lcm", "diff", "integrate", "expand", "factor", "simplify",
        "together", "cancel", "apart", "Matrix", "Rational", "Integer")}
    names.update(abs=sp.Abs, ln=sp.log, pi=sp.pi, E=sp.E, I=sp.I, oo=sp.oo)
    names.update(variables or {})
    # Rewrite only operator tokens: raw("x^2") must remain byte-for-byte text.
    tokens = tokenize.generate_tokens(io.StringIO(value).readline)
    source = tokenize.untokenize((kind, "**" if kind == tokenize.OP and text == "^" else text)
                                for kind, text, *_ in tokens)
    tree = ast.parse(source, mode="eval")
    if isinstance(tree.body, ast.Call) and isinstance(tree.body.func, ast.Name) and tree.body.func.id == "raw":
        node = tree.body
        if len(node.args) == 1 and not node.keywords and isinstance(node.args[0], ast.Constant) and isinstance(node.args[0].value, str):
            return raw(node.args[0].value)
        raise ValueError("raw() needs one literal string")

    def computed(item):
        if isinstance(item, str):
            raise ValueError("strings and raw() cannot be used inside computed expressions")
        if isinstance(item, (list, tuple)):
            for child in item: computed(child)
        if isinstance(item, dict):
            for key, child in item.items():
                computed(key)
                computed(child)
        return item
    if len(list(ast.walk(tree))) > 300:
        raise ValueError("test expression is too large")

    def visit(node):
        if isinstance(node, ast.Constant):
            if isinstance(node.value, bool) or node.value is None:
                return node.value
            if isinstance(node.value, (int, float)):
                return sp.Rational(ast.get_source_segment(source, node))
            raise ValueError("literal strings need raw('...')")
        if isinstance(node, ast.Name) and node.id in names:
            return computed(names[node.id])
        if isinstance(node, (ast.List, ast.Tuple)):
            return [visit(item) for item in node.elts]
        if isinstance(node, ast.Dict):
            return {visit(key): visit(item) for key, item in zip(node.keys, node.values)}
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.UAdd, ast.USub)):
            v = visit(node.operand)
            computed(v)
            return v if isinstance(node.op, ast.UAdd) else -v
        if isinstance(node, ast.BinOp):
            left, right = computed(visit(node.left)), computed(visit(node.right))
            if isinstance(node.op, ast.Add): return left + right
            if isinstance(node.op, ast.Sub): return left - right
            if isinstance(node.op, ast.Mult): return left * right
            if isinstance(node.op, ast.Div): return left / right
            if isinstance(node.op, ast.Mod): return left % right
            if isinstance(node.op, ast.Pow):
                if getattr(right, "is_number", False) and abs(right) > 100:
                    raise ValueError("test exponent exceeds 100")
                return left ** right
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            name = node.func.id
            if name == "raw":
                raise ValueError("raw() is allowed only as a complete fixture value")
            fn = names.get(name)
            if callable(fn) and not node.keywords:
                return fn(*[computed(visit(arg)) for arg in node.args])
        raise ValueError("unsupported test expression: " + ast.dump(node, include_attributes=False))
    return visit(tree.body)


def input_text(value):
    """A computed value in math-exercise's existing student input syntax."""
    import sympy as sp
    if isinstance(value, Raw):
        return str(value)
    if isinstance(value, sp.MatrixBase):
        raise ValueError("matrix answers need one value per field or a response with inputs")
    return sp.sstr(value).replace("**", "^")


def _expect(actual, expected, where):
    if isinstance(expected, str):
        # partial is a semantic verdict; the detailed native status is retained.
        status = actual.get("status")
        matches = (status == expected
                   or (expected == "invalid" and status == "error")
                   or (expected == "partial" and status in ("not_exact", "not_form") and actual.get("score", 0) > 0)
                   or (expected == "wrong" and status in ("not_exact", "not_form", "rejected") and actual.get("score") == 0))
        if not matches:
            raise AssertionError("{}: expected {}, got {}".format(where, expected, actual))
        return
    if not isinstance(expected, dict) or not expected:
        raise ValueError(where + ": expectation must be a verdict or nonempty mapping")
    unknown = set(expected) - {"status", "score", "partial", "answer-note"}
    if unknown:
        raise ValueError(where + ": unknown expectation keys " + ", ".join(sorted(unknown)))
    if "status" in expected:
        _expect(actual, expected["status"], where)
    if "score" in expected:
        score = expected["score"]
        if isinstance(score, bool) or not isinstance(score, (int, float)) or not math.isfinite(score) or not 0 <= score <= 1:
            raise ValueError(where + ": expected score must be between 0 and 1")
        found = actual.get("score")
        if isinstance(found, bool) or not isinstance(found, (int, float)) or not math.isfinite(found) or abs(found - score) > 1e-9:
            raise AssertionError("{}: expected score {}, got {}".format(where, score, actual))
    if "partial" in expected:
        partial = expected["partial"]
        if not isinstance(partial, bool):
            raise ValueError(where + ": partial must be true or false")
        observed_partial = (actual.get("status") == "partial" or
                            actual.get("status") in ("not_exact", "not_form") and actual.get("score", 0) > 0)
        if observed_partial != partial:
            raise AssertionError(where + ": partial verdict differs: " + repr(actual))
    if "answer-note" in expected and actual.get("answer-note") != expected["answer-note"]:
        raise AssertionError(where + ": answer note differs: " + repr(actual))



def _invalid_expected(actual, expected, fields):
    """Invalid input is never implicitly a zero-score/wrong answer."""
    def explicit(result, wanted):
        if isinstance(wanted, dict):
            wanted = wanted.get("status")
        return wanted == result.get("status") or (result.get("status") == "error" and wanted == "invalid")
    if explicit(actual, expected):
        return True
    wanted = dict(zip(fields, expected)) if isinstance(expected, list) else expected
    if not isinstance(wanted, dict):
        return False
    invalid = {name: result for name, result in actual.get("fields", {}).items()
               if result.get("status") in ("invalid", "error", "empty")}
    return bool(invalid) and all(name in wanted and explicit(result, wanted[name])
                                 for name, result in invalid.items())


def run_declarative(tests, grade, *, fields=(), variables=None, resolve=None):
    """Run the common format using a component-supplied real grading adapter.

    grade receives {"answers": {field: resolved input}} or {"response": ...}
    and returns {status, score, fields?: {field: {status, score}}}.
    STACK can supply its own CAS resolver; there is no engine import here.
    """
    if not isinstance(tests, list) or not tests:
        raise ValueError("tests must be a nonempty list")
    fields = list(fields)
    resolve = resolve or (lambda value: expression(value, variables))
    results, names = [], set()
    for index, case in enumerate(tests, 1):
        if not isinstance(case, dict):
            raise ValueError("test {} must be a mapping".format(index))
        name = case.get("name")
        if not isinstance(name, str) or not name.strip() or name in names:
            raise ValueError("each test needs a unique, nonempty name")
        names.add(name)
        where = "test " + repr(name)
        unknown = set(case) - {"name", "answers", "response", "expect", "score", "partial"}
        if unknown:
            raise ValueError(where + ": unknown keys " + ", ".join(sorted(unknown)))
        if ("answers" in case) == ("response" in case):
            raise ValueError(where + ": give answers or response, exactly one")
        if "expect" not in case and "score" not in case and "partial" not in case:
            raise ValueError(where + ": give an expectation")
        if "expect" in case and (case["expect"] is None or case["expect"] == "" or case["expect"] == [] or case["expect"] == {}):
            raise ValueError(where + ": expectation cannot be null or empty")
        def resolved(value):
            try:
                return resolve(value)
            except Exception as error:
                raise ValueError(where + ": " + str(error)) from error
        if "answers" in case:
            answers = case["answers"]
            if isinstance(answers, list):
                if len(answers) != len(fields):
                    raise ValueError(where + ": answer count does not match fields")
                answers = dict(zip(fields, answers))
            if not isinstance(answers, dict) or set(answers) != set(fields):
                raise ValueError(where + ": answers must name exactly " + repr(fields))
            payload = {"answers": {key: resolved(answers[key]) for key in fields}}
        else:
            # Map keys are author field/property names, never CAS expressions.
            def nested(value):
                if isinstance(value, dict):
                    return {key: nested(item) for key, item in value.items()}
                if isinstance(value, list):
                    return [nested(item) for item in value]
                return resolved(value)
            payload = {"response": nested(case["response"])}
        try:
            actual = grade(payload)
            expected = case.get("expect")
            if actual.get("status") in ("invalid", "error", "empty") and not _invalid_expected(actual, expected, fields):
                raise AssertionError("invalid or empty input needs an explicit verdict expectation")
            if isinstance(expected, list):
                if len(expected) != len(fields):
                    raise ValueError("expected verdict count does not match fields")
                for field, verdict in zip(fields, expected):
                    _expect(actual.get("fields", {}).get(field, {}), verdict, where + "/" + field)
            elif isinstance(expected, dict) and expected and set(expected) == set(fields) and all(isinstance(value, (str, dict)) for value in expected.values()):
                if set(expected) != set(fields):
                    raise ValueError("expected fields must match answer fields")
                for field, verdict in expected.items():
                    _expect(actual.get("fields", {}).get(field, {}), verdict, where + "/" + field)
            elif expected is not None:
                _expect(actual, expected, where)
            if "score" in case or "partial" in case:
                _expect(actual, {key: case[key] for key in ("score", "partial") if key in case}, where)
        except Exception as error:
            raise type(error)(where + ": " + str(error)) from error
        results.append({"name": name, "actual": actual, "passed": True})
    return results


def run_tests(check, symbols, tests, *, namespace, base):
    """The unchanged legacy test(check, symbols) runner."""
    if '\n' not in tests and tests.endswith('.py'):
        tests = (Path(base) / tests).read_text()
    exec(tests, namespace)
    test = namespace.get('test')
    if not callable(test):
        raise ValueError('tests: | must define test(check, symbols)')
    test(namespace['check'] if check is None else check, symbols)
