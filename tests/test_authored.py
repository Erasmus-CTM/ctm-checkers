"""The authored question tests' command (question-tests.py's main): output
lines, exit statuses, --stdin; with CTM_LEGACY_MATH_EXERCISE (a math-exercise
checkout at the pin), the same runs of math-exercise 0.10.0's
question-tests.py give the same output."""
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from tests.conftest import PACKAGE

LESSON = '''# A lesson

```{math-exercise}
#| label: sum
#| mode: custom
#| vars: x, y
#| checker: |
#|   def check(response, symbols):
#|       return response["expressions"][0] == symbols["x"] + symbols["y"]
#| tests: |
#|   def test(check, symbols):
#|       x, y = symbols["x"], symbols["y"]
#|       assert check({"expressions": [x + y]}, symbols) is True
#|       assert check({"expressions": [x]}, symbols) is False
Write x plus y.
```

```{math-exercise}
#| label: untested
#| mode: custom
#| checker: |
#|   def check(response, symbols):
#|       return True
Anything.
```

```{math-exercise}
#| label: file-tests
#| mode: custom
#| checker: |
#|   def check(response, symbols):
#|       return {"score": 0.5, "feedback": str(floor(2.5))}
#| tests: tests/half.py
Half.
```
'''
HALF = 'def test(check, symbols):\n    assert check({}, symbols)["feedback"] == "2"\n'
FAILING = LESSON.replace('is False', 'is True')

SHIM = ('import sys\nsys.path.insert(0, sys.argv.pop(1))\n'
        'from ctm_checkers.math_exercise import authored\nsys.exit(authored.main(sys.argv[1:]))\n')


def lesson(tmp_path, text=LESSON):
    (tmp_path / 'tests').mkdir(exist_ok=True)
    (tmp_path / 'tests' / 'half.py').write_text(HALF)
    path = tmp_path / 'lesson.qmd'
    path.write_text(text)
    return path


def new(tmp_path, *args, stdin=None, env=None):
    return subprocess.run([sys.executable, '-c', SHIM, PACKAGE, *args], cwd=tmp_path, input=stdin,
                          capture_output=True, text=True, env=dict(os.environ, **(env or {})))


def legacy(tmp_path, *args, stdin=None, env=None):
    folder = Path(os.environ['CTM_LEGACY_MATH_EXERCISE']).resolve() / '_extensions' / 'math-exercise'
    return subprocess.run([sys.executable, str(folder / 'question-tests.py'), *args], cwd=tmp_path, input=stdin,
                          capture_output=True, text=True, env=dict(os.environ, **(env or {})))


def outcome(result):
    return result.returncode, result.stdout, result.stderr


def test_a_passing_lesson(tmp_path):
    result = new(tmp_path, str(lesson(tmp_path)))
    assert outcome(result) == (0, '2 authored question tests passed; 1 custom questions without tests.\n', '')


def test_a_failing_lesson(tmp_path):
    result = new(tmp_path, str(lesson(tmp_path, FAILING)))
    assert result.returncode == 1 and result.stdout == ''
    assert result.stderr.startswith('math-exercise question tests failed: ')
    assert 'lesson.qmd: sum: AssertionError' in result.stderr


def test_stdin_and_usage(tmp_path):
    question = {'label': 'q', 'mode': 'custom', 'checker': 'def check(r, s):\n    return True\n',
                'tests': 'def test(check, symbols):\n    assert check({}, symbols)\n', 'tests-base': str(tmp_path)}
    assert outcome(new(tmp_path, '--stdin', stdin=json.dumps(question)))[0:2] == (0, '1 authored question tests passed; 0 custom questions without tests.\n')
    usage = new(tmp_path)
    assert usage.returncode == 1 and 'Usage: python _extensions/math-exercise/question-tests.py lesson.qmd [...]' in usage.stderr


def no_sympy(tmp_path):
    # A Python without SymPy: a sympy package that cannot be imported, first on the path.
    folder = tmp_path / 'no-sympy' / 'sympy'
    folder.mkdir(parents=True)
    (folder / '__init__.py').write_text('raise ModuleNotFoundError("No module named \'sympy\'", name="sympy")\n')
    return {'PYTHONPATH': str(folder.parent)}


@pytest.mark.skipif(not os.environ.get('CTM_LEGACY_MATH_EXERCISE'), reason='needs CTM_LEGACY_MATH_EXERCISE')
@pytest.mark.parametrize('case', ['passing', 'failing', 'stdin', 'usage', 'missing', 'no-sympy'])
def test_the_same_output_as_math_exercise_0_10(tmp_path, case):
    question = {'label': 'q', 'mode': 'custom', 'checker': 'def check(r, s):\n    return False\n',
                'tests': 'def test(check, symbols):\n    assert check({}, symbols), "never"\n', 'tests-base': str(tmp_path)}
    args, stdin = {
        'passing': ([str(lesson(tmp_path))], None),
        'failing': ([str(lesson(tmp_path, FAILING))], None),
        'stdin': (['--stdin'], json.dumps(question)),
        'usage': ([], None),
        'missing': ([str(tmp_path / 'missing.qmd')], None),
        'no-sympy': ([str(lesson(tmp_path))], None),
    }[case]
    env = no_sympy(tmp_path) if case == 'no-sympy' else {}
    result = outcome(new(tmp_path, *args, stdin=stdin, env=env))
    assert result == outcome(legacy(tmp_path, *args, stdin=stdin, env=env))
    if case == 'no-sympy':
        assert result == (1, '', "math-exercise question tests failed: No module named 'sympy'\n")


def test_symbols_and_run_tests():
    from ctm_checkers.math_exercise import namespace, symbols
    from ctm_checkers.testing import run_tests
    assert sorted(symbols('x, y')) == ['x', 'y'] and sorted(symbols('')) == []
    scope = namespace({'vars': 'x'})
    exec('def check(response, symbols):\n    return response == 1\n', scope)
    seen = []
    run_tests(None, symbols('x'), 'def test(check, symbols):\n    assert check(1, symbols)\n    seen.append(sorted(symbols))\n',
              namespace=dict(scope, seen=seen), base='.')
    run_tests(lambda response, symbols: True, {}, 'def test(check, symbols):\n    assert check(0, symbols)\n', namespace=scope, base='.')
    with pytest.raises(AssertionError):
        run_tests(None, {}, 'def test(check, symbols):\n    assert check(0, symbols)\n', namespace=scope, base='.')
    assert seen == [['x']]
