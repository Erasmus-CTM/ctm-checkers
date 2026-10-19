"""math-exercise's grading semantics, moved verbatim from math-exercise 0.10.0
(docs/api.md). Importing this package imports no SymPy: each name below
loads its module when it is first used (PEP 562)."""

_EXPORTS = {
    'check': 'checks',
    'check_custom': 'custom',
    'namespace': 'custom',
    'symbols': 'custom',
    'learner_strings': 'inputs',
    'admit': 'inputs',
    'round_places': 'numeric',
    'sigfigs_round': 'numeric',
    'parse_tolerance': 'numeric',
    'authored_questions': 'authored',
    'run_question': 'authored',
}

__all__ = sorted(_EXPORTS)


def __getattr__(name):
    module = _EXPORTS.get(name)
    if module is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    from importlib import import_module
    value = getattr(import_module('.' + module, __name__), name)
    globals()[name] = value
    return value
