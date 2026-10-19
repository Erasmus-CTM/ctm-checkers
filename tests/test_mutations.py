"""The golden tables catch a change of the numeric comparison: the two
mutations of the step-2 U1 review (rounding half to even instead of half up;
the tolerance test `<` instead of `<=`) make the tables that were captured
from math-exercise's own examples fail on their own, without the suites
recorded here; the rounding grid and the supplementary requests catch them
too. The mutations are applied to a copy of src/ctm_checkers."""
import os
import re
import shutil
import subprocess
import sys

import pytest

from conftest import ROOT

# name: (module, text, replacement, occurrences)
MUTATIONS = {
    'round-half-even': ('math_exercise/numeric.py', 'ROUND_HALF_UP', 'ROUND_HALF_EVEN', 2),
    'tolerance-strict': ('math_exercise/checks.py', 'return abs(sv - cv) <= parse_tolerance(', 'return abs(sv - cv) < parse_tolerance(', 1),
}
# The tables captured from math-exercise's examples (export/ of the umbrella's harness).
EXPORTED = r'^math_exercise/(requests|custom-probes|authored)-math-exercise\.jsonl$'
RECORDED = r'^math_exercise/(rounding|requests-supplement)\.jsonl$'

# A few minutes: CI runs them in a step of their own (CTM_MUTATION_TESTS=1).
pytestmark = pytest.mark.skipif(not os.environ.get('CTM_MUTATION_TESTS') or bool(os.environ.get('CTM_CHECKERS_WHEEL')),
                                reason='set CTM_MUTATION_TESTS=1 (runs on a copy of src/)')


def package(tmp_path, mutation=None):
    folder = tmp_path / (mutation or 'unchanged')
    shutil.copytree(ROOT / 'src' / 'ctm_checkers', folder / 'ctm_checkers', ignore=shutil.ignore_patterns('__pycache__'))
    if mutation:
        module, text, replacement, occurrences = MUTATIONS[mutation]
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
    match = re.search(r'^(\d+) rows, (\d+) reproduced, (\d+) not\.$', result.stdout, re.M)
    assert match, result.stdout + result.stderr
    assert result.returncode == (1 if int(match[3]) else 0)
    return int(match[1]), int(match[3])


def test_the_unchanged_copy_reproduces_the_exported_tables(tmp_path):
    rows, different = verify(package(tmp_path), EXPORTED)
    assert rows > 1500 and different == 0


@pytest.mark.parametrize('mutation', sorted(MUTATIONS))
def test_each_mutation_fails_on_the_exported_tables_alone(tmp_path, mutation):
    rows, different = verify(package(tmp_path, mutation), EXPORTED)
    print(f'{mutation}: {different} of {rows} exported rows differ')
    assert different > 0


@pytest.mark.parametrize('mutation', sorted(MUTATIONS))
def test_each_mutation_fails_on_the_recorded_suites(tmp_path, mutation):
    rows, different = verify(package(tmp_path, mutation), RECORDED)
    print(f'{mutation}: {different} of {rows} recorded rows differ')
    assert different > 0
