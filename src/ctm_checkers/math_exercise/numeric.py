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
