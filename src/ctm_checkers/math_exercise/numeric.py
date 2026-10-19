"""math-exercise's rounding rule and tolerances (standard library only:
math-exercise's variant generator uses it without SymPy).

Moved verbatim from math-exercise 0.10.0 (_round_places, _sigfigs_round,
_parse_tol); its variants.py rounds with the same rule (round_half_up,
sigfig).
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
