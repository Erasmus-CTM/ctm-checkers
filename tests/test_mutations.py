"""The golden tables catch changes of the checks: each mutation below is
applied to a copy of src/ctm_checkers, and the tables must no longer be
reproduced. The two numeric mutations of the step-2 U1 review must fail on
the tables captured from math-exercise's examples alone; every mutation must
fail on the suites recorded here (the review of C1 found six rules that no
row reached, its second round three more; rows were added for them). The
STACK mutations must fail on the STACK tables (they stop at the first row
that differs). docs/goldens.md lists how many rows each mutation changes."""
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
# The STACK tables, recorded with stack-sympy f450bcd's code.
STACK = r'^stack/'

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
    'basis-independence': ('matrix.py', 'independence = rank / valid_count if valid_count else 0.0', 'independence = 1.0', 1,
                           (RECORDED, STACK)),
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
    # Round 2 of that review.
    'imaginary-threshold': ('math_exercise/checks.py', 'if abs(sv.imag) > 1e-9 or abs(cv.imag) > 1e-9:',
                            'if abs(sv.imag) > 1e-3 or abs(cv.imag) > 1e-3:', 1, (RECORDED,)),
    'graph-boolean-ids': ('graph.py', 'if type(node_id) is not int or node_id in known:', 'if not isinstance(node_id, int) or node_id in known:', 1,
                          (RECORDED,)),
    'js-number-small-exponent': ('math_exercise/custom.py', 'if -6 < n <= 0:', 'if -7 < n <= 0:', 1, (RECORDED,)),
    # The STACK engine (step-2 C3): answer tests, response trees, input rules, question tests, the card.
    'stack-numabsolute-inclusive': ('stack/assessment.py', 'correct = difference < abs(tolerance) + sp.Rational(1, 10**9)',
                                    'correct = difference <= abs(tolerance) + sp.Rational(1, 10**9)', 1, (STACK,)),
    'stack-numabsolute-no-guard': ('stack/assessment.py', 'correct = difference < abs(tolerance) + sp.Rational(1, 10**9)',
                                   'correct = difference < abs(tolerance)', 1, (STACK,)),
    'stack-numrelative-strict': ('stack/assessment.py',
                                 'correct = difference <= abs(teacher_number * tolerance * (1 + sp.Rational(1, 10**9)))',
                                 'correct = difference < abs(teacher_number * tolerance)', 1, (STACK,)),
    'stack-numabsolute-irrational-no-guard': ('stack/assessment.py', 'correct = difference < abs(tol) + Decimal("1e-9")',
                                              'correct = difference < abs(tol)', 1, (STACK,)),
    'stack-numrelative-irrational-strict': ('stack/assessment.py', 'correct = difference <= abs(ta * tol * (1 + Decimal("1e-9")))',
                                            'correct = difference < abs(ta * tol)', 1, (STACK,)),
    'stack-decimal-places-half-up': ('stack/assessment.py', 'teacher_decimal.quantize(quantum, rounding=ROUND_HALF_EVEN)',
                                     'teacher_decimal.quantize(quantum, rounding="ROUND_HALF_UP")', 1, (STACK,)),
    'stack-numeric-screen-margin': ('stack/equivalence.py', 'all(r > sp.Rational(1, 10000) for r in results)',
                                    'all(r > sp.Rational(1, 100) for r in results)', 1, (STACK,)),
    'stack-sets-duplicates-note': ('stack/collections.py', "notes.append('ATSets_duplicates')", 'pass', 1, (STACK,)),
    'stack-prt-mode-plus': ('stack/engine.py', 'return current + score', 'return score', 1, (STACK,)),
    'stack-prt-score-clamp': ('stack/engine.py', '"score": round(max(0.0, min(1.0, score)), 10)', '"score": round(score, 10)', 1, (STACK,)),
    'stack-qtest-penalty': ('stack/engine.py', 'observed_penalty = question["penalty"] if observed_score is not None and observed_score < 1 else 0.0',
                            'observed_penalty = 0.0', 1, (STACK,)),
    'stack-forbid-float': ('stack/engine.py', 'if inp["forbidfloat"] and any(', 'if False and any(', 1, (STACK,)),
    'stack-max-chars': ('stack/expressions.py', 'MAX_CHARS = 1200', 'MAX_CHARS = 1400', 1, (STACK,)),
    'stack-card-json-escape': ('stack/cli.py', '.replace("<", "\\\\u003c")', '', 1, (STACK,)),
    # The input rules that only stack/supplement's input-rules.xml reaches (the review of C3).
    'stack-forbidwords-case': ('stack/engine.py', 'if any(n.value.lower() in {w.lower() for w in inp["forbidwords"]}',
                               'if any(n.value in set(inp["forbidwords"])', 1, (STACK,)),
    'stack-lowest-terms-negatives': ('stack/engine.py', '\n                                                              or num < 0 and den < 0):',
                                     '):', 1, (STACK,)),
    'stack-numerical-type': ('stack/engine.py', 'if inp["type"] == "numerical" and getattr(value, "is_number", None) is not True:',
                             'if False:', 1, (STACK,)),
    'stack-max-matrix-entries': ('stack/expressions.py', 'MAX_MATRIX_ENTRIES = 64', 'MAX_MATRIX_ENTRIES = 65', 1, (STACK,)),
    'stack-logic-precedence': ('stack/expressions.py', '"or": 2, "and": 4', '"or": 4, "and": 2', 1, (STACK,)),
    # The basis checks of the course's null-space questions, which only stack/questions-course reaches
    # (with basis-independence above): assess_basis (ctm_checkers.matrix) through a PythonChecker,
    # the model answer nullspace_basis(A), the assessment colours.
    'stack-basis-dependent': ('matrix.py', 'dependent = rank < valid_count', 'dependent = False', 1, (STACK,)),
    'stack-basis-zero-vector': ('matrix.py', 'zero = vector == zeros(*vector.shape)', 'zero = False', 1, (STACK,)),
    'stack-basis-coverage': ('matrix.py', 'coverage = min(rank, target_dimension) / target_dimension', 'coverage = 1.0', 1, (STACK,)),
    'stack-basis-model-space': ('stack/matrix_models.py', 'vectors = matrix.nullspace()', 'vectors = matrix.columnspace()', 1, (STACK,)),
    'stack-checker-assessment': ('stack/checkers.py', 'result["assessment"] = {axis: list(statuses)}', 'pass', 1, (STACK,)),
    # S-01 (0.3.0): the names of question and feedback variables in student answers
    # (the feedback variables, names inside expressions and two names in one answer:
    # only stack/supplement's forbidden-variables.xml reaches them).
    'stack-s01-question-variables': ('stack/engine.py', '    names = set(env)\n', '    names = set()\n', 1, (STACK,)),
    'stack-s01-feedback-variables': ('stack/engine.py', 'names.add(match.group(1))', 'pass', 1, (STACK,)),
    'stack-s01-whole-answer-only': ('stack/engine.py', '    for node in _walk(tree):\n        if node.kind == "name" and node.value in names',
                                    '    for node in [tree]:\n        if node.kind == "name" and node.value in names', 1, (STACK,)),
    'stack-s01-first-name-only': ('stack/engine.py', '" ".join(FORBIDDEN_VARIABLE.format(name=name) for name in found)',
                                  'FORBIDDEN_VARIABLE.format(name=found[0])', 1, (STACK,)),
    'stack-s01-message': ('stack/engine.py', 'FORBIDDEN_VARIABLE = "Forbidden variable or constant: {name}."',
                          'FORBIDDEN_VARIABLE = "Forbidden variable: {name}."', 1, (STACK,)),
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


def verify(folder, suite, fail_fast=False):
    """(rows, rows that do not reproduce) of the tables matching `suite`."""
    result = subprocess.run([sys.executable, str(ROOT / 'tools' / 'golden.py'), 'verify', '--adapter', 'wheel', '--wheel', str(folder),
                             '--suite', suite, '--max-diffs', '0'] + (['--fail-fast'] if fail_fast else []),
                            capture_output=True, text=True, cwd=ROOT, env=dict(os.environ, GITHUB_ACTIONS=''))
    match = re.search(r'^(\d+) rows, (\d+) reproduced, (\d+) not\.', result.stdout, re.M)
    assert match, result.stdout + result.stderr
    assert result.returncode == (1 if int(match[3]) else 0)
    return int(match[1]), int(match[3])


LABELS = {EXPORTED: 'exported', RECORDED: 'recorded', STACK: 'stack'}


@pytest.mark.parametrize('suite', [EXPORTED, RECORDED, STACK], ids=['exported', 'recorded', 'stack'])
def test_the_unchanged_copy_reproduces_the_tables(tmp_path, suite):
    rows, different = verify(package(tmp_path), suite)
    assert rows > 1000 and different == 0


@pytest.mark.parametrize('mutation, suite', [(name, suite) for name, spec in MUTATIONS.items() for suite in spec[4]],
                         ids=[f'{name}-{LABELS[suite]}' for name, spec in MUTATIONS.items() for suite in spec[4]])
def test_each_mutation_fails(tmp_path, mutation, suite):
    rows, different = verify(package(tmp_path, mutation), suite, fail_fast=suite == STACK)
    print(f'{mutation}: {different} of {rows} {LABELS[suite]} rows differ' + (' (stopped at the first)' if suite == STACK else ''))
    assert different > 0
