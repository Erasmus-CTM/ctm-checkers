"""Execution shared by custom-checker adapters.

Adapters prepare the response, symbols and request-local namespace, and retain
their own error boundary. Execution leaves stdout and exceptions untouched.
"""
from .result import normalize_result


def execute_checker(source, response, symbols, namespace):
    """Run an author's check in the adapter's namespace and normalize its result.

    The caller supplies a fresh namespace for each request. Neither parsing nor
    engine-specific names belong here; authored prints and exceptions propagate
    to the caller exactly as they did before this shared execution seam.
    """
    exec(source, namespace)
    checker = namespace.get("check")
    if not callable(checker):
        raise ValueError("Custom checker must define check(expressions, symbols)")
    return normalize_result(checker(response, symbols))
