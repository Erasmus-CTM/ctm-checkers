"""Public author-checker namespace, shared below both engines.

Only trusted checker source uses these names. Learner values are prepared by
the engine adapter and are never passed to this Python expression parser.
"""
_NAMES = None


def public_names():
    global _NAMES
    if _NAMES is None:
        import math
        import sympy
        from sympy.parsing.sympy_parser import (parse_expr, standard_transformations,
            implicit_multiplication_application, convert_xor)
        from ..matrix import assess_basis
        from ..graph import graph_from_response
        names = {name: getattr(sympy, name) for name in sympy.__all__}
        names.update(parse_expr=parse_expr, standard_transformations=standard_transformations,
            implicit_multiplication_application=implicit_multiplication_application, convert_xor=convert_xor,
            log10=math.log10, floor=math.floor, gcd=math.gcd,
            assess_basis=assess_basis, graph_from_response=graph_from_response)
        _NAMES = names
    return dict(_NAMES)


def namespace():
    return dict(public_names(), __name__='_ctm_stack_checker', __doc__=None,
                __package__=None, __loader__=None, __spec__=None)
