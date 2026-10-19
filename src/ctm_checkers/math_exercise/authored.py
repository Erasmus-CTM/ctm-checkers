"""math-exercise's authored question tests (`#| tests:`), run at build time
and by the documented command
`python _extensions/math-exercise/question-tests.py lesson.qmd`, which calls
main() (moved from math-exercise 0.10.0's question-tests.py; its checker
namespace comes from custom.namespace instead of decoding math-exercise.js)."""
import json
from pathlib import Path
import re
import sys

# question-tests.py's usage text: main() reports it when it has no arguments.
USAGE = """Run trusted author assertions next to custom math-exercise checkers.

Usage: python _extensions/math-exercise/question-tests.py lesson.qmd [...]
Quarto invokes --stdin for a single exercise containing #| tests: |."""


def run_question(options, base):
    # SymPy is imported here, not with the module: main() reports a missing
    # SymPy as question-tests.py did.
    from sympy import Symbol
    from ..testing import run_tests
    from .custom import namespace
    from .parsing import build_locals
    if options.get('mode') != 'custom' or not options.get('checker', '').strip():
        raise ValueError('Authored tests currently require mode: custom and checker: |')
    scope = namespace({'vars': options.get('vars', '')})
    symbols = {k: v for k, v in build_locals(options.get('vars', '')).items()
               if isinstance(v, Symbol)}
    exec(options['checker'], scope)
    run_tests(None, symbols, options['tests'], namespace=scope, base=base)


def authored_questions(path):
    for block in re.findall(r'^```\{math-exercise\}\n(.*?)^```\s*$', path.read_text(), re.M | re.S):
        options = {}
        lines = block.splitlines()
        i = 0
        while i < len(lines):
            match = re.match(r'^#\|\s*([^:]+):\s*(.*?)\s*$', lines[i])
            i += 1
            if not match:
                continue
            key, value = match.groups()
            if value == '|':
                body = []
                while i < len(lines) and (lines[i].startswith('#|   ') or lines[i].strip() == '#|'):
                    body.append(lines[i][5:] if lines[i].startswith('#|   ') else '')
                    i += 1
                value = '\n'.join(body)
            options[key] = value
        yield options


def run(argv):
    # SymPy first, as question-tests.py built its checker runtime before
    # reading anything: without it, the one message is "No module named 'sympy'".
    from . import custom  # noqa: F401
    if argv == ['--stdin']:
        questions = [(None, json.load(sys.stdin))]
    else:
        if len(argv) == 0:
            raise ValueError(USAGE)
        questions = [(path, question) for path in map(Path, argv) for question in authored_questions(path)]
    tested = untested = 0
    for path, options in questions:
        if not options.get('tests', '').strip():
            untested += options.get('mode') == 'custom'
            continue
        label = options.get('label', '(unlabelled exercise)')
        try:
            run_question(options, Path(options.get('tests-base', Path.cwd())))
        except Exception as error:
            raise RuntimeError(f'{path or "Quarto"}: {label}: {type(error).__name__}: {error}') from error
        tested += 1
    print(f'{tested} authored question tests passed; {untested} custom questions without tests.')


def main(argv=None):
    """question-tests.py's command line: `--stdin` (one question as JSON, as
    Quarto passes it) or .qmd files. Returns the exit status and prints the
    messages question-tests.py printed."""
    if sys.version_info < (3, 9):
        print(f'math-exercise question tests failed: ctm-checkers needs Python 3.9 or later, not {sys.version.split()[0]}', file=sys.stderr)
        return 1
    try:
        run(sys.argv[1:] if argv is None else list(argv))
    except Exception as error:
        print(f'math-exercise question tests failed: {error}', file=sys.stderr)
        return 1
    return 0
