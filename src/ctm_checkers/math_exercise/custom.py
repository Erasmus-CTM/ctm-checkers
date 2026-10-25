"""math-exercise's custom checkers: check_custom runs an author's
`#| checker:` on a response and normalizes its result; namespace is what the
checker's code sees (moved verbatim from math-exercise 0.10.0's
_math_check_custom; the request's fields replace the _math_* globals that the
page set)."""
import copy
import json
import math
import re

from sympy import Matrix, Symbol

from ..core.custom import execute_checker
from ..core.namespace import public_names
from ..core.result import normalize_result
from ..graph import graph_from_response
from ..matrix import assess_basis
from .checks import canon_form
from .numeric import parse_tolerance, round_places, sigfigs_round
from .parsing import (
    TRANSFORMATIONS, _FRAC_RE, build_locals, convert_xor, implicit_multiplication_application,
    numeric_not_reduced, parse_expr, split_top, standard_transformations,
)


def check_custom(request):
    try:
        if not request["checker"].strip():
            raise ValueError("mode custom requires a checker")
        _local = build_locals(request["vars"])
        context = None
        if "question_context" in request:
            from ..variants import decode_context
            context = decode_context(request["question_context"])
            for name, value in context[1].items():
                if isinstance(value, Symbol) and name == value.name:
                    _local[name] = value
            # Nested data may intentionally retain same-name distinct Symbols.
            bindings = {name: value for name, value in context[1].items()
                        if isinstance(value, Symbol) and name == value.name}
            for value in list(context[1].values()) + list(context[2].values()):
                for symbol in getattr(value, "free_symbols", ()):
                    if symbol.name in bindings and symbol != bindings[symbol.name]:
                        raise ValueError("conflicting question Symbol assumptions: " + symbol.name)
        response = copy.deepcopy(request["response"])
        if isinstance(response, dict) and response.get("kind") == "expressions":
            raw_values = response.get("raw", [])
            response["expressions"] = [parse_expr(v, local_dict=_local, transformations=TRANSFORMATIONS) for v in raw_values]
            for name, item in response.get("inputs", {}).items():
                if not isinstance(item, dict) or item.get("type") != "matrix":
                    continue
                rows, cols = int(item.get("rows", -1)), int(item.get("cols", -1))
                if rows < 0 or cols < 0:
                    raise ValueError(f"Invalid matrix dimensions for {name}")
                matrix_raw = item.get("raw", [])
                if len(matrix_raw) != rows * cols:
                    raise ValueError(f"Matrix {name} has inconsistent dimensions")
                matrix_expressions = [parse_expr(v, local_dict=_local, transformations=TRANSFORMATIONS) for v in matrix_raw]
                item["expressions"] = matrix_expressions
                item["matrix"] = Matrix(rows, cols, matrix_expressions)
        checker_symbols = {k: v for k, v in _local.items() if isinstance(v, Symbol)}
        scope = namespace(request)
        if context is not None:
            fields, variables, teacher, variant = context
            if not isinstance(response, dict) or response.get("kind") != "expressions":
                raise ValueError("question context requires an expression response")
            if response.get("inputs"):
                raise ValueError("question context with named matrix inputs is not supported yet")
            if len(response["expressions"]) != len(fields):
                raise ValueError("question context field count does not match expressions")
            response.update(answers=dict(zip(fields, response["expressions"])),
                            variables=variables, teacher=teacher, variant=variant)
        return execute_checker(request["checker"], response, checker_symbols, scope)
    except Exception as _me:
        return {"status": "error", "message": str(_me)}


def symbols(vars):
    """The symbols a checker receives for the exercise's variables `vars`
    (`check(response, symbols)`; check_custom and run_question build the same
    dict)."""
    return {k: v for k, v in build_locals(vars).items() if isinstance(v, Symbol)}


# The names every checker starts with: those of math-exercise 0.10.0's
# checker module, whose globals a checker received (docs/api.md, "The
# checker namespace"). Built once; each call gets a fresh copy.
_SHARED = None


def _shared():
    global _SHARED
    if _SHARED is None:
        names = public_names()
        # Private helpers under their old names (not part of the contract).
        names.update(_math_tf=TRANSFORMATIONS, _mj=json, _mre=re, _FRAC_RE=_FRAC_RE,
                     _numeric_not_reduced=numeric_not_reduced, _split_top=split_top, _round_places=round_places,
                     _sigfigs_round=sigfigs_round, _parse_tol=parse_tolerance, _canon_form=canon_form,
                     _normalize_custom_result=normalize_result)
        _SHARED = names
    return _SHARED


def namespace(request=None):
    """A fresh dict with the names a `#| checker:` sees: SymPy's
    (`from sympy import *`), parse_expr and its transformations, math's
    log10, floor and gcd, assess_basis and graph_from_response, and the
    request's values as math-exercise 0.10.0 named them: _math_vars,
    _math_response_json (the response as the page's JSON text) and
    _math_checker."""
    scope = {"__name__": "_ctm_math_exercise", "__doc__": None, "__package__": None, "__loader__": None, "__spec__": None}
    scope.update(_shared())
    if request is not None:
        if "vars" in request:
            variables = request["vars"]
            scope["_math_vars"] = variables
            scope["_build_locals"] = lambda: build_locals(variables)
        if "response" in request:
            scope["_math_response_json"] = page_json(request["response"])
        if "checker" in request:
            scope["_math_checker"] = request["checker"]
    return scope


def page_json(value):
    """JSON text as the page's JSON.stringify writes it (compact; numbers in
    JavaScript's spelling; keys in the order given)."""
    if value is None or isinstance(value, bool):
        return json.dumps(value)
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        return _js_number(value)
    if isinstance(value, str):
        return _js_string(value)
    if isinstance(value, (list, tuple)):
        return "[" + ",".join(page_json(item) for item in value) + "]"
    if isinstance(value, dict):
        return "{" + ",".join(_js_string(str(key)) + ":" + page_json(item) for key, item in value.items()) + "}"
    raise TypeError("not JSON: " + type(value).__name__)


def _js_string(text):
    # JSON.stringify escapes lone surrogates; Python leaves them as they are.
    return re.sub("[\ud800-\udfff]", lambda m: "\\u%04x" % ord(m.group()), json.dumps(text, ensure_ascii=False))


def _js_number(x):
    # Number::toString: the shortest digits that round-trip (as Python's
    # repr), in positional notation for exponents from -7 to 20.
    if x != x or x in (float("inf"), float("-inf")):
        return "null"
    if x == 0:
        return "0"
    sign, text = ("-", repr(-x)) if x < 0 else ("", repr(x))
    mantissa, _, exponent = text.partition("e")
    whole, _, fraction = mantissa.partition(".")
    digits = (whole + fraction).lstrip("0")
    n = len(whole) - (len(whole + fraction) - len(digits)) + int(exponent or 0)
    digits = digits.rstrip("0")
    k = len(digits)
    if k <= n <= 21:
        return sign + digits + "0" * (n - k)
    if 0 < n <= 21:
        return sign + digits[:n] + "." + digits[n:]
    if -6 < n <= 0:
        return sign + "0." + "0" * -n + digits
    e = n - 1
    return sign + digits[0] + ("." + digits[1:] if k > 1 else "") + "e" + ("+" if e >= 0 else "-") + str(abs(e))
