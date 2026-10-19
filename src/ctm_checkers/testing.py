"""Authored question tests: `#| tests:` code that defines test(check, symbols)
and asserts what the checker returns (moved from math-exercise 0.10.0's
question-tests.py)."""
from pathlib import Path


def run_tests(tests, namespace, symbols, base):
    """Runs `tests` (code, or the name of a .py file under `base`) in the
    checker's `namespace` and calls its test(check, symbols) with the
    namespace's check; raises on failure."""
    if '\n' not in tests and tests.endswith('.py'):
        tests = (Path(base) / tests).read_text()
    exec(tests, namespace)
    test = namespace.get('test')
    if not callable(test):
        raise ValueError('tests: | must define test(check, symbols)')
    test(namespace['check'], symbols)
