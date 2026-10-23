"""Bounded exact-value transport for trusted question context.

This codec is data, never Python source. Learner response numbers do not use it.
"""
import re
import sympy as sp
from sympy.core.assumptions import _assume_defined

_VERSION = 1
_MAX_NODES = 4096
_MAX_DEPTH = 48
_MAX_TEXT = 4096
_FUNCTIONS = {name: getattr(sp, name) for name in (
    "Add", "Mul", "Pow", "sin", "cos", "tan", "asin", "acos", "atan",
    "sinh", "cosh", "tanh", "exp", "log", "Abs", "floor", "ceiling", "Min", "Max",
)}
_CONSTANTS = {"pi": sp.pi, "E": sp.E, "I": sp.I}
_INTEGER = re.compile(r"-?(0|[1-9][0-9]*)\Z")


def _integer_text(value):
    value = int(value)
    # Bound conversion itself on Python 3.9, which has no decimal-string limit.
    if value.bit_length() > 13606:
        raise ValueError("exact integer exceeds size limit")
    text = str(value)
    if len(text) > _MAX_TEXT:
        raise ValueError("exact integer exceeds size limit")
    return text


def encode(value):
    """Encode a supported exact value; unsupported types never stringify."""
    count = [0]
    def node(item, depth=0):
        count[0] += 1
        if count[0] > _MAX_NODES or depth > _MAX_DEPTH:
            raise ValueError("exact value exceeds node/depth limit")
        def child(value): return node(value, depth + 1)
        if isinstance(item, (list, tuple, dict, sp.MatrixBase)) and len(item) > _MAX_NODES:
            raise ValueError("exact value exceeds node limit")
        if item is None: return ["null"]
        if type(item) is bool: return ["bool", item]
        if type(item) is str: return ["text", item]
        if type(item) is int or isinstance(item, sp.Integer):
            return ["integer", _integer_text(item)]
        if isinstance(item, sp.Rational):
            return ["rational", _integer_text(item.p), _integer_text(item.q)]
        if type(item) is sp.Symbol:
            return ["symbol", item.name, dict(item.assumptions0)]
        for name, constant in _CONSTANTS.items():
            if item is constant: return ["constant", name]
        if isinstance(item, sp.MatrixBase):
            return ["matrix", item.rows, item.cols, [child(v) for v in item]]
        if type(item) in (list, tuple):
            return ["list" if type(item) is list else "tuple", [child(v) for v in item]]
        if type(item) is dict and all(type(k) is str for k in item):
            return ["dict", [[k, child(v)] for k, v in item.items()]]
        if isinstance(item, sp.Basic) and item.func in _FUNCTIONS.values():
            return ["expression", item.func.__name__, [child(v) for v in item.args]]
        raise ValueError("unsupported exact value: " + type(item).__name__)
    wire = {"version": _VERSION, "value": node(value)}
    _validate(wire)
    return wire


def _validate(wire):
    if type(wire) is not dict or set(wire) != {"version", "value"} or type(wire["version"]) is not int or wire["version"] != _VERSION:
        raise ValueError("invalid exact-value envelope/version")
    count = [0]
    def text(value):
        if type(value) is not str or len(value) > _MAX_TEXT:
            raise ValueError("invalid exact-value text")
    def integer(value):
        text(value)
        if not _INTEGER.fullmatch(value): raise ValueError("invalid exact integer")
    def walk(value, depth=0, operand=False):
        count[0] += 1
        if count[0] > _MAX_NODES or depth > _MAX_DEPTH:
            raise ValueError("exact value exceeds node/depth limit")
        if type(value) is not list or not value or type(value[0]) is not str:
            raise ValueError("invalid exact-value tag")
        tag = value[0]
        arities = {"null": 1, "bool": 2, "text": 2, "integer": 2, "rational": 3,
                   "symbol": 3, "constant": 2, "matrix": 4, "list": 2, "tuple": 2,
                   "dict": 2, "expression": 3}
        if tag not in arities or len(value) != arities[tag]:
            raise ValueError("unknown or malformed exact-value tag")
        if operand and tag not in ("integer", "rational", "symbol", "constant", "expression"):
            raise ValueError("expression operand must be exact scalar")
        if tag == "bool" and type(value[1]) is not bool: raise ValueError("invalid exact boolean")
        if tag == "text": text(value[1])
        if tag == "integer": integer(value[1])
        if tag == "rational":
            integer(value[1]); integer(value[2])
            if value[2].startswith("-") or value[2] == "0": raise ValueError("invalid exact denominator")
        if tag == "symbol":
            text(value[1])
            if not value[1] or type(value[2]) is not dict or len(value[2]) > 64:
                raise ValueError("invalid exact symbol")
            for key, assumption in value[2].items():
                if type(key) is not str or key not in _assume_defined or type(assumption) is not bool:
                    raise ValueError("invalid exact symbol assumption")
        if tag == "constant" and (type(value[1]) is not str or value[1] not in _CONSTANTS): raise ValueError("unknown exact constant")
        if tag in ("list", "tuple", "matrix", "expression", "dict"):
            children = value[-1]
            if type(children) is not list or len(children) > _MAX_NODES:
                raise ValueError("invalid exact-value children")
            if tag == "matrix":
                rows, cols = value[1:3]
                if type(rows) is not int or type(cols) is not int or not 0 <= rows <= 256 or not 0 <= cols <= 256 or rows * cols != len(children):
                    raise ValueError("invalid exact matrix dimensions")
            if tag == "expression":
                if type(value[1]) is not str or value[1] not in _FUNCTIONS or not children or len(children) > 64:
                    raise ValueError("unknown or oversized exact expression")
                if value[1] == "Pow" and len(children) != 2: raise ValueError("invalid exact power")
            seen = set()
            for child in children:
                if tag == "dict":
                    if type(child) is not list or len(child) != 2: raise ValueError("invalid exact mapping entry")
                    text(child[0])
                    if child[0] in seen: raise ValueError("duplicate exact mapping key")
                    seen.add(child[0]); child = child[1]
                walk(child, depth + 1, operand=tag in ("expression", "matrix"))
    walk(wire["value"])


def decode(wire):
    """Validate the complete tree before invoking any SymPy constructor."""
    _validate(wire)
    def node(value):
        tag = value[0]
        if tag == "null": return None
        if tag in ("text", "bool"): return value[1]
        if tag == "integer": return sp.Integer(value[1])
        if tag == "rational": return sp.Rational(value[1], value[2])
        if tag == "symbol": return sp.Symbol(value[1], **value[2])
        if tag == "constant": return _CONSTANTS[value[1]]
        if tag == "matrix": return sp.Matrix(value[1], value[2], [node(v) for v in value[3]])
        if tag == "dict": return {k: node(v) for k, v in value[1]}
        if tag in ("list", "tuple"):
            values = [node(v) for v in value[1]]
            return values if tag == "list" else tuple(values)
        return _FUNCTIONS[value[1]](*(node(v) for v in value[2]), evaluate=False)
    return node(wire["value"])


def question_context(fields, variables, teacher, variant=None):
    """Build the optional trusted author envelope used by the existing grader."""
    context = {"version": 1, "fields": list(fields), "variables": encode(variables),
               "teacher": encode(teacher), "variant": variant}
    decode_context(context)
    return context


def decode_context(context):
    if type(context) is not dict or set(context) != {"version", "fields", "variables", "teacher", "variant"} or type(context["version"]) is not int or context["version"] != 1:
        raise ValueError("invalid question context/version")
    fields = context["fields"]
    if type(fields) is not list or not fields or len(fields) > 256 or any(type(v) is not str or not v or len(v) > _MAX_TEXT for v in fields) or len(set(fields)) != len(fields):
        raise ValueError("question context requires ordered unique field labels")
    identity = context["variant"]
    if identity is not None and (type(identity) is not dict or set(identity) != {"n", "id", "hash"} or type(identity["n"]) is not int or identity["n"] < 1 or any(type(identity[k]) is not str or not identity[k] or len(identity[k]) > _MAX_TEXT for k in ("id", "hash"))):
        raise ValueError("invalid variant identity")
    _validate(context["variables"])
    _validate(context["teacher"])
    variables, teacher = decode(context["variables"]), decode(context["teacher"])
    if type(variables) is not dict or type(teacher) is not dict or list(teacher) != fields:
        raise ValueError("question context requires variables and teacher keyed in field order")
    return fields, variables, teacher, dict(identity) if identity is not None else None

