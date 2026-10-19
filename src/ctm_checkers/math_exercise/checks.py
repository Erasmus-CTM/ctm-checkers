"""math-exercise's checks of typed answers: string, set, numeric,
equivalent and exact modes, forms and the reject rule (moved verbatim from
math-exercise 0.10.0's _math_check; the request's fields replace the
_math_* globals that the page set)."""
from sympy import cancel, expand, factor, simplify, together

from .numeric import parse_tolerance, round_places, sigfigs_round
from .parsing import TRANSFORMATIONS, build_locals, numeric_not_reduced, parse_expr, split_top


def canon_form(expr, form):
    if form == "factored":        return factor(expr)
    if form == "expanded":        return expand(expr)
    if form == "single_fraction": return together(expr)
    if form == "lowest_terms":    return cancel(expr)
    return expr


def num_equal(sv, cv, request):
    if request["decplaces"].strip():
        n = int(request["decplaces"])
        return round_places(sv, n) == round_places(cv, n)
    if request["sigfigs"].strip():
        n = int(request["sigfigs"])
        return sigfigs_round(sv, n) == sigfigs_round(cv, n)
    if request["tolerance"].strip():
        return abs(sv - cv) <= parse_tolerance(request["tolerance"], cv)
    return abs(sv - cv) <= 1e-8 * max(1.0, abs(cv))


def check(request):
    try:
        mode = request["mode"]
        if mode in ("string", "string_ci"):
            s, c = request["student"], request["correct"]
            if mode == "string_ci": s, c = s.lower(), c.lower()
            ok = s == c
            return {"status": "correct" if ok else "wrong", "score": 1.0 if ok else 0.0}

        _local = build_locals(request["vars"])

        if mode == "set":
            s_items = [parse_expr(p, local_dict=_local, transformations=TRANSFORMATIONS) for p in split_top(request["student"])]
            c_items = [parse_expr(p, local_dict=_local, transformations=TRANSFORMATIONS) for p in split_top(request["correct"])]
            unmatched = list(c_items)
            matched = 0
            for si in s_items:
                found = None
                for ci in unmatched:
                    d = simplify(si - ci)
                    if d == 0 or (d.is_number and abs(complex(d.evalf())) < 1e-8):
                        found = ci
                        break
                if found is not None:
                    unmatched.remove(found)
                    matched += 1
            exact = matched == len(c_items) == len(s_items)
            if exact:
                return {"status": "correct", "score": 1.0}
            extra = len(s_items) - matched
            score = (max(0.0, matched - extra) / len(c_items)) if (request["partial_credit"] and c_items) else 0.0
            return {"status": "partial" if score > 0 else "wrong", "score": score}

        _ms = parse_expr(request["student"], local_dict=_local, transformations=TRANSFORMATIONS)
        _mc = parse_expr(request["correct"],  local_dict=_local, transformations=TRANSFORMATIONS)

        if mode == "numeric":
            sv, cv = complex(_ms.evalf()), complex(_mc.evalf())
            if abs(sv.imag) > 1e-9 or abs(cv.imag) > 1e-9:
                return {"status": "wrong", "score": 0.0}
            ok = num_equal(sv.real, cv.real, request)
            return {"status": "correct" if ok else "wrong", "score": 1.0 if ok else 0.0}

        _d  = simplify(_ms - _mc)
        _eq = (_d == 0) or (_d.is_number and abs(complex(_d.evalf())) < 1e-10)
        if not _eq:
            return {"status": "wrong", "score": 0.0}
        if mode == "exact":
            if str(_ms) != str(_mc):
                return {"status": "not_exact", "score": request["form_credit"] if request["partial_credit"] else 0.0}
            # SymPy auto-reduces Rationals on parse, so an un-reduced
            # numeric fraction (e.g. "2/4" inside "1/4 + 2/4") is
            # invisible to the string check above; "exact" is meant to
            # be the strictest mode, so catch it on the raw text too.
            if not _ms.free_symbols and numeric_not_reduced(request["student"]):
                return {"status": "not_exact", "score": request["form_credit"] if request["partial_credit"] else 0.0}
        if request["form"].strip():
            if request["form"] == "lowest_terms" and not _ms.free_symbols:
                if numeric_not_reduced(request["student"]):
                    return {"status": "not_form", "score": request["form_credit"] if request["partial_credit"] else 0.0}
            elif _ms != canon_form(_ms, request["form"]):
                return {"status": "not_form", "score": request["form_credit"] if request["partial_credit"] else 0.0}
        if request["reject"].strip():
            _mr  = parse_expr(request["reject"], local_dict=_local, transformations=TRANSFORMATIONS)
            if str(_ms) == str(_mr):
                return {"status": "rejected", "score": 0.0}
        return {"status": "correct", "score": 1.0}
    except Exception as _me:
        return {"status": "error", "message": str(_me)}
