"""The golden tables catch changes of the checks: each mutation below is
applied to a copy of src/ctm_checkers, and the tables must no longer be
reproduced. The two numeric mutations of the step-2 U1 review must fail on
the tables captured from math-exercise's examples alone; every mutation must
fail on the suites recorded here (the review of C1 found six rules that no
row reached and added rows for them). docs/goldens.md lists how many rows
each mutation changes."""
import os
import re
import shutil
import subprocess
import sys

import pytest

from conftest import ROOT

# The tables captured from math-exercise's examples (export/ of the umbrella's harness).
EXPORTED = r'^math_exercise/(requests|custom-probes|authored)-math-exercise\.jsonl$'
# The suites recorded here with math-exercise 0.10.0's code.
RECORDED = r'^math_exercise/(rounding|requests-supplement|namespace)\.jsonl$'

# name: (module, text, replacement, occurrences, the tables that must fail on their own)
MUTATIONS = {
    # The step-2 U1 review.
    'round-half-even': ('math_exercise/numeric.py', 'ROUND_HALF_UP', 'ROUND_HALF_EVEN', 2, (EXPORTED, RECORDED)),
    'tolerance-strict': ('math_exercise/checks.py', 'return abs(sv - cv) <= parse_tolerance(', 'return abs(sv - cv) < parse_tolerance(', 1,
                         (EXPORTED, RECORDED)),
    # The review of C1.
    'sigfigs-off-by-one': ('math_exercise/numeric.py', 'd = n - int(floor(log10(abs(x)))) - 1', 'd = n - int(floor(log10(abs(x))))', 1, (RECORDED,)),
    'round-17-digits': ('math_exercise/numeric.py', "format(float(x), '.15g')", "format(float(x), '.17g')", 1, (RECORDED,)),
    'show-score-ignored': ('core/result.py', 'show_score = bool(result.get("show_score", True))', 'show_score = True', 1, (RECORDED,)),
    'basis-independence': ('matrix.py', 'independence = rank / valid_count if valid_count else 0.0', 'independence = 1.0', 1, (RECORDED,)),
    'set-extra-items': ('math_exercise/checks.py', 'max(0.0, matched - extra)', 'max(0.0, matched)', 1, (RECORDED,)),
    'exact-unreduced': ('math_exercise/checks.py', 'if not _ms.free_symbols and numeric_not_reduced(request["student"]):', 'if False:', 1,
                        (RECORDED,)),
    'status-threshold': ('core/result.py', 'score >= 1.0 - 1e-9', 'score >= 1.0', 1, (RECORDED,)),
    'namespace-floor-gcd': ('math_exercise/custom.py', 'log10=math.log10, floor=math.floor, gcd=math.gcd', 'log10=math.log10', 1, (RECORDED,)),
    'dunder-string-modes': ('math_exercise/inputs.py', 'if "student" in request and request.get("mode") not in ("string", "string_ci"):',
                            'if "student" in request:', 1, (RECORDED,)),
    'lowest-terms-numeric': ('math_exercise/checks.py', 'if request["form"] == "lowest_terms" and not _ms.free_symbols:', 'if False:', 1,
                             (RECORDED,)),
    'string-ci-case': ('math_exercise/checks.py', 'if mode == "string_ci": s, c = s.lower(), c.lower()', 'pass', 1, (RECORDED,)),
    'response-json-spaces': ('math_exercise/custom.py', 'return "{" + ",".join(_js_string(str(key)) + ":"',
                             'return "{" + ", ".join(_js_string(str(key)) + ": "', 1, (RECORDED,)),
    'matrix-dimensions': ('math_exercise/custom.py', 'if len(matrix_raw) != rows * cols:', 'if False:', 1, (RECORDED,)),
    'equivalence-tolerance': ('math_exercise/checks.py', 'abs(complex(_d.evalf())) < 1e-10', 'abs(complex(_d.evalf())) < 1e-6', 1, (RECORDED,)),
    'default-tolerance': ('math_exercise/checks.py', '1e-8 * max(1.0, abs(cv))', '1e-8 * abs(cv)', 1, (RECORDED,)),
    'imaginary-part': ('math_exercise/checks.py', 'if abs(sv.imag) > 1e-9 or abs(cv.imag) > 1e-9:', 'if False:', 1, (RECORDED,)),
    'inf-local': ('math_exercise/parsing.py', '_local.setdefault("inf", oo)', 'pass', 1, (RECORDED,)),
    'split-brackets': ('math_exercise/parsing.py', 'if ch in "([{": depth += 1', 'if ch in "(": depth += 1', 1, (RECORDED,)),
    'graph-duplicate-edges': ('graph.py', 'key = (source, target) if directed else tuple(sorted((source, target)))', 'key = (source, target)', 1,
                              (RECORDED,)),
}

# A few minutes: CI runs them in a step of their own (CTM_MUTATION_TESTS=1).
pytestmark = pytest.mark.skipif(not os.environ.get('CTM_MUTATION_TESTS') or bool(os.environ.get('CTM_CHECKERS_WHEEL')),
                                reason='set CTM_MUTATION_TESTS=1 (runs on a copy of src/)')


def package(tmp_path, mutation=None):
    folder = tmp_path / (mutation or 'unchanged')
    shutil.copytree(ROOT / 'src' / 'ctm_checkers', folder / 'ctm_checkers', ignore=shutil.ignore_patterns('__pycache__'))
    if mutation:
        module, text, replacement, occurrences, _ = MUTATIONS[mutation]
        path = folder / 'ctm_checkers' / module
        source = path.read_text()
        assert source.count(text) == occurrences, (module, text)
        path.write_text(source.replace(text, replacement))
    return folder


def verify(folder, suite):
    """(rows, rows that do not reproduce) of the tables matching `suite`."""
    result = subprocess.run([sys.executable, str(ROOT / 'tools' / 'golden.py'), 'verify', '--adapter', 'wheel', '--wheel', str(folder),
                             '--suite', suite, '--max-diffs', '0'], capture_output=True, text=True, cwd=ROOT,
                            env=dict(os.environ, GITHUB_ACTIONS=''))
    match = re.search(r'^(\d+) rows, (\d+) reproduced, (\d+) not\.', result.stdout, re.M)
    assert match, result.stdout + result.stderr
    assert result.returncode == (1 if int(match[3]) else 0)
    return int(match[1]), int(match[3])


@pytest.mark.parametrize('suite', [EXPORTED, RECORDED], ids=['exported', 'recorded'])
def test_the_unchanged_copy_reproduces_the_tables(tmp_path, suite):
    rows, different = verify(package(tmp_path), suite)
    assert rows > 1000 and different == 0


@pytest.mark.parametrize('mutation, suite', [(name, suite) for name, spec in MUTATIONS.items() for suite in spec[4]],
                         ids=[f'{name}-{"exported" if suite == EXPORTED else "recorded"}' for name, spec in MUTATIONS.items() for suite in spec[4]])
def test_each_mutation_fails(tmp_path, mutation, suite):
    rows, different = verify(package(tmp_path, mutation), suite)
    print(f'{mutation}: {different} of {rows} {"exported" if suite == EXPORTED else "recorded"} rows differ')
    assert different > 0
