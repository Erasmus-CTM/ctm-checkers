"""Parsing answers as math-exercise does (moved verbatim from math-exercise
0.10.0: _math_tf, _build_locals, _split_top, _numeric_not_reduced)."""
from math import gcd
import re

from sympy import oo, symbols
from sympy.parsing.sympy_parser import (
    parse_expr, standard_transformations,
    implicit_multiplication_application, convert_xor
)

TRANSFORMATIONS = standard_transformations + (
    implicit_multiplication_application, convert_xor,
)

_FRAC_RE = re.compile(r"(-?\d+)\s*/\s*(-?\d+)")


def numeric_not_reduced(raw):
    # True if raw contains any literal int/int fraction that is not fully
    # reduced (e.g. the "2/4" inside "1/4 + 2/4"). SymPy auto-reduces
    # Rationals as soon as they are parsed/combined, so this has to scan
    # the original text, not the parsed expression.
    for _m in _FRAC_RE.finditer(raw):
        num, den = int(_m.group(1)), int(_m.group(2))
        if den != 0 and gcd(abs(num), abs(den)) != 1:
            return True
    return False


def split_top(s, sep=","):
    parts = []
    depth = 0
    cur = ""
    for ch in s:
        if ch in "([{": depth += 1
        elif ch in ")]}": depth -= 1
        if ch == sep and depth == 0:
            parts.append(cur)
            cur = ""
        else:
            cur += ch
    parts.append(cur)
    return [p.strip() for p in parts if p.strip() != ""]


# The names an answer may use: the exercise's variables (`vars`, separated by
# spaces or commas) as symbols, and `inf` for oo unless it is a variable.
def build_locals(vars):
    _local = {}
    if vars.strip():
        for _v in vars.replace(",", " ").split():
            _v = _v.strip()
            if _v: _local[_v] = symbols(_v)
    _local.setdefault("inf", oo)
    return _local
