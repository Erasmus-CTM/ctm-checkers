"""Import rules of the package (design §1.2): import-light roots, no import
between the engines (H2), shared modules below the engines."""
import ast
import os
import subprocess
import sys

from tests.conftest import PACKAGE, PACKAGES, ROOT

SRC = ROOT / 'src' / 'ctm_checkers'


def imports(path):
    tree = ast.parse(path.read_text(encoding='utf-8'))
    package = '.'.join(path.relative_to(SRC.parent).with_suffix('').parts)
    if path.name == '__init__.py':
        package = package.rsplit('.', 1)[0] + '.__init__'
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                yield alias.name
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                base = package.split('.')[:-node.level]
                yield '.'.join(base + ([node.module] if node.module else []))
            else:
                yield node.module


def modules(folder):
    return [p for p in (SRC / folder).rglob('*.py')] if (SRC / folder).is_dir() else []


def test_engines_do_not_import_each_other():
    engines = ['math_exercise', 'stack']
    for engine in engines:
        for path in modules(engine):
            for name in imports(path):
                for other in engines:
                    if other != engine:
                        assert not name.startswith('ctm_checkers.' + other), (path, name)


def test_shared_modules_do_not_import_engines():
    shared = [SRC / 'browser.py']  # the entry may name handlers; it imports them by name only
    for path in [SRC / 'matrix.py', SRC / 'graph.py', SRC / 'testing.py', *modules('core')]:
        for name in imports(path):
            assert not name.startswith(('ctm_checkers.math_exercise', 'ctm_checkers.stack')), (path, name)
    for path in shared:
        for name in imports(path):
            assert not name.startswith(('ctm_checkers.math_exercise', 'ctm_checkers.stack')), (path, name)


def run(code):
    env = dict(os.environ, PYTHONPATH=os.pathsep.join(PACKAGES))
    return subprocess.run([sys.executable, '-c', code], capture_output=True, text=True, env=env, check=True).stdout.strip()


def test_roots_and_numeric_import_no_sympy():
    # variants.py (math-exercise) rounds with numeric and needs only PyYAML.
    assert run('import sys, ctm_checkers, ctm_checkers.math_exercise, ctm_checkers.math_exercise.numeric, ctm_checkers.core.result, ctm_checkers.core.custom, '
               'ctm_checkers.math_exercise.authored; '
               'print(sorted(m for m in ("sympy", "networkx", "mpmath") if m in sys.modules))') == '[]'


def test_lazy_names_load_their_modules():
    assert run('import sys; from ctm_checkers import math_exercise as m; f = m.check; '
               'print(f.__module__, "sympy" in sys.modules)') == 'ctm_checkers.math_exercise.checks True'


def test_package_version():
    import ctm_checkers
    assert isinstance(ctm_checkers.API, int)
    assert ctm_checkers.__file__.startswith(PACKAGE)


def test_the_stack_engine_comes_from_the_package_under_test():
    # With the wheels: ctm_checkers.stack from the STACK engine's wheel (pkgutil.extend_path in ctm_checkers/__init__.py).
    found = run('import ctm_checkers, ctm_checkers.stack.engine as e; print(e.__file__)')
    assert any(found.startswith(path + os.sep) for path in PACKAGES), found
    assert found.startswith(PACKAGES[-1] + os.sep), found
