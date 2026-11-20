"""math-exercise's rounding rule and tolerances.

Moved verbatim from math-exercise 0.10.0 (_round_places, _sigfigs_round,
_parse_tol); its variants.py rounds with the same rule (round_half_up,
sigfig).

Exact authoring helpers import SymPy lazily; legacy grading remains usable
with the standard library alone. AGPL-3.0-or-later.
"""
from math import floor, log10


# Rounds the decimal value (15 significant digits, so binary noise in a
# computed key such as 1.05*1.9 does not count) half away from zero:
# round(5.395, 2) is 5.39 for the binary float, but 5.40 here.
def round_places(x, d):
    from decimal import Decimal, ROUND_HALF_UP, InvalidOperation
    try:
        return float(Decimal(format(float(x), '.15g')).quantize(Decimal(1).scaleb(-d), rounding=ROUND_HALF_UP))
    except (InvalidOperation, ValueError, OverflowError):
        return round(x, d)


def sigfigs_round(x, n):
    if x == 0: return 0.0
    d = n - int(floor(log10(abs(x)))) - 1
    return round_places(x, d)


def parse_tolerance(spec, ref):
    spec = spec.strip()
    if spec.endswith("%"):
        return abs(ref) * float(spec[:-1]) / 100.0
    return float(spec)


# GR-1: |student - key| <= tolerance is decided exactly. The answer and the key
# are parsed again with decimal literals as rationals (1.1 is 11/10, as
# written), and the tolerance as written (an absolute value or a percentage
# of the key). A rational difference is compared exactly, any other (pi,
# sqrt(2)) at 60 significant digits. In binary floating point 1.1 - 1 is
# 0.10000000000000009, so 1.1 was wrong and 0.9 correct for key 1 and
# tolerance 0.1; reading values at 15 digits instead (the first fix) loosened
# keys of more than 15 digits (audit of 20 Nov, finding 3). When the exact
# comparison cannot be made (an infinite or complex value, a tolerance that
# is not a number) the floating-point comparison of the values decides.
def exact_within_tolerance(student, correct, spec, local):
    """True or False, or None when the exact comparison does not apply."""
    import sympy as sp
    from sympy.parsing.sympy_parser import rationalize
    from .parsing import TRANSFORMATIONS, parse_expr
    from decimal import Decimal, DecimalException
    try:
        text = spec.strip()
        percent = text.endswith("%")
        number = text[:-1].strip() if percent else text
        # A tolerance is author data, but bound it: Rational("1e999999999")
        # would build a billion-digit integer.
        written = Decimal(number)
        if not written.is_finite() or abs(written.as_tuple().exponent) > 64 or len(written.as_tuple().digits) > 64:
            return None
        tolerance = sp.Rational(number)
        # The same bound on the literals of the answer and the key: as
        # rationals, 1e999999999 would be a billion-digit integer.
        import re
        for literal in re.findall(r"(?:\d+\.?\d*|\.\d+)(?:[eE][+-]?\d+)?", student + " " + correct):
            mantissa, _, exponent = literal.lower().partition("e")
            if len(mantissa) > 64 or (exponent and abs(int(exponent)) > 64):
                return None
        transformations = TRANSFORMATIONS + (rationalize,)
        s = parse_expr(student, local_dict=dict(local), transformations=transformations)
        c = parse_expr(correct, local_dict=dict(local), transformations=transformations)
        if percent:
            tolerance = sp.Abs(c) * tolerance / 100
        if tolerance.is_negative or not (s.is_number and c.is_number):
            return None
        margin = sp.Abs(s - c) - tolerance
        if margin.is_Rational:
            return bool(margin <= 0)
        value = margin.evalf(60)
        if not (value.is_real and value.is_finite):
            return None
        return bool(value <= 0)
    except (Exception, DecimalException):
        return None


def within_tolerance(sv, cv, spec):
    """The floating-point comparison of the values (abs(sv - cv) <= tolerance)."""
    return abs(sv - cv) <= parse_tolerance(spec, cv)


def _exact_real(value):
    import sympy as sp
    if type(value) is int:
        value = sp.Integer(value)
    if (not isinstance(value, sp.Expr) or value.has(sp.Float)
            or value.is_number is not True or value.is_real is not True
            or value.is_finite is not True):
        raise ValueError("rounding needs a finite exact real number")
    return value


def _exact_integer(value):
    import sympy as sp
    if type(value) is not int and not isinstance(value, sp.Integer):
        raise ValueError("rounding precision must be an integer")
    return int(value)


def round_exact(value, places=0):
    """Round an exact finite real to decimal places, half away from zero.

    Returns a SymPy Integer or Rational, never a float. Negative places round
    to tens, hundreds, etc. Strings, floats and unresolved symbols are rejected.
    If SymPy cannot determine the exact rounding boundary, fail explicitly.
    """
    import sympy as sp
    value, places = _exact_real(value), _exact_integer(places)
    scale = sp.Integer(10)**places
    magnitude = sp.floor(sp.Abs(value)*scale + sp.Rational(1, 2))
    result = sp.sign(value)*magnitude
    if not isinstance(result, sp.Integer):
        raise ValueError("cannot determine exact rounding boundary")
    return result/scale


def sigfig_exact(value, figures):
    """Round an exact finite real to positive significant figures.

    Uses the same half-away rule as round_exact, including exact transcendental
    expressions such as sin(pi/7). Zero returns exact zero.
    """
    import sympy as sp
    value, figures = _exact_real(value), _exact_integer(figures)
    if figures <= 0:
        raise ValueError("significant figures must be positive")
    if value.is_zero is True:
        return sp.Integer(0)
    exponent = sp.floor(sp.log(sp.Abs(value), 10))
    if not isinstance(exponent, sp.Integer):
        raise ValueError("cannot determine exact decimal magnitude")
    return round_exact(value, figures - exponent - 1)
