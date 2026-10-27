"""Safe bounded STACK expression and answer-test subset for Quarto."""

__all__ = ["InvalidAnswer", "Node", "Unsupported", "assignments", "canonical_form", "evaluate", "parse", "answer_test"]


def __getattr__(name):
    # Structural XML import and native Maxima preparation do not need SymPy.
    # Keep the existing public mathematical exports lazy, as the package root
    # already does for its other engines.
    if name not in __all__:
        raise AttributeError(name)
    from importlib import import_module
    module = import_module('.assessment' if name == 'answer_test' else '.expressions', __name__)
    value = getattr(module, name)
    globals()[name] = value
    return value


def __dir__():
    return sorted(set(globals()) | set(__all__))
