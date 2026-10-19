"""Authored question tests: `#| tests:` code that defines test(check, symbols)
and asserts what the checker returns (moved from math-exercise 0.10.0's
question-tests.py; STACK's `#| tests:` will use it too)."""
from pathlib import Path


def run_tests(check, symbols, tests, *, namespace, base):
    """Runs authored tests and raises on failure: `tests` (code, or the name
    of a .py file under `base`) runs in `namespace` and must define
    test(check, symbols), which is called with `check` and `symbols`.
    check=None passes the namespace's `check` as it is after the tests ran
    (math-exercise's rule: question-tests.py took it from there)."""
    if '\n' not in tests and tests.endswith('.py'):
        tests = (Path(base) / tests).read_text()
    exec(tests, namespace)
    test = namespace.get('test')
    if not callable(test):
        raise ValueError('tests: | must define test(check, symbols)')
    test(namespace['check'] if check is None else check, symbols)
