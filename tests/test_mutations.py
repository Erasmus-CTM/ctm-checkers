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
    'stack-s01-question-variables': ('stack/student_input.py', '    keys = frozenset(question_variables)\n',
                                     '    keys = frozenset()\n    author_names = set(author_names) - set(question_variables)\n', 1, (STACK,)),
    'stack-s01-feedback-variables': ('stack/engine.py',
                                     'names.update(name for name, _ in assignment_statements(prt.get("feedbackvariables", "")) if name)',
                                     'pass', 1, (STACK,)),
    # (Since S-13, 0.6.0, the names of an answer are checked in student_input.identifier_messages.)
    'stack-s01-whole-answer-only': ('stack/student_input.py', 'for index, (kind, value) in enumerate(tokens):',
                                    'for index, (kind, value) in enumerate(tokens if len(tokens) == 1 else []):', 1, (STACK,)),
    'stack-s01-first-name-only': ('stack/engine.py', '        raise InvalidAnswer(" ".join(messages))\n    return tree',
                                  '        raise InvalidAnswer(messages[0])\n    return tree', 1, (STACK,)),
    'stack-s01-message': ('stack/student_input.py', 'FORBIDDEN_VARIABLE = "Forbidden variable or constant: {name}."',
                          'FORBIDDEN_VARIABLE = "Forbidden variable: {name}."', 1, (STACK,)),
    # The review of S-01 (0.4.0): every response tree's feedback variables, the
    # assignments' separators (one grammar: expressions.assignment_statements),
    # and the build's check of the teacher's answers (stack/supplement's
    # forbidden-variables-prts.xml and teacher-answer-clash.xml).
    'stack-s01-first-prt-only': ('stack/engine.py', '        for prt in question.get("prts", []):\n            names.update(',
                                 '        for prt in question.get("prts", [])[:1]:\n            names.update(', 1, (STACK,)),
    'stack-assignment-separators': ('stack/expressions.py', 'for stmt in re.split(r"[;\\n]+", source):',
                                    'for stmt in re.split(r"[;]+", source):', 1, (STACK,)),
    'stack-s01-teacher-answer-names': ('stack/engine.py', '            _teacher_answer_names(question, inp["name"], teacher, env)\n', '', 1,
                                       (STACK,)),
    # S-02 (0.5.0): E and I are variables; the frozen variants write Euler's
    # number and the imaginary unit as %e and %i (stack/supplement's constants.xml).
    'stack-s02-E-constant': ('stack/expressions.py', '"e": sp.E, "%e": sp.E,', '"e": sp.E, "E": sp.E, "%e": sp.E,', 1, (STACK,)),
    'stack-s02-I-constant': ('stack/expressions.py', '"i": sp.I, "%i": sp.I}', '"i": sp.I, "I": sp.I, "%i": sp.I}', 1, (STACK,)),
    'stack-s02-source-euler': ('stack/expressions.py', 'return "%e"', 'return "E"', 1, (STACK,)),
    'stack-s02-source-imaginary': ('stack/expressions.py', 'return "%i"', 'return "I"', 1, (STACK,)),
    # S-13 (0.6.0): STACK's rules for the text of an answer (stack/supplement's input-text.xml and the
    # answer sets' strings), the inverse trigonometric functions, and the question tests' inputs (bound to the
    # teacher's answers, as STACK computes them; corpus AlgMap-1-6.xml types ans+1).
    'stack-s13-three-letters': ('stack/student_input.py', '    return name[-1:].isdigit()', '    return True', 1, (STACK,)),
    'stack-s13-underscore-parts': ('stack/student_input.py', 'parts = [name] if _readable(name, keys) else list(dict.fromkeys(name.split("_")))',
                                   'parts = [name]', 1, (STACK,)),
    'stack-s13-function-case': ('stack/student_input.py', 'message = _case_message(name, _FUNCTION_CASES, FUNCTION_CASE)', 'message = None', 1,
                                (STACK,)),
    'stack-s13-variable-case': ('stack/student_input.py', '            elif len(part) > 1:', '            elif False:', 1, (STACK,)),
    'stack-s13-log-in': ('stack/student_input.py', '        if name == "In":', '        if False:', 1, (STACK,)),
    'stack-s13-unicode': ('stack/student_input.py', '    for old, new in stack_data.REPLACEMENTS:', '    for old, new in ():', 1, (STACK,)),
    'stack-s13-characters': ('stack/student_input.py', 'raise InvalidAnswer(FORBIDDEN_CHAR.format(char=_CONTROL.get(character, character)))', 'pass', 1,
                             (STACK,)),
    'stack-s13-spaces': ('stack/student_input.py', '    if not fixed:', '    if True:', 1, (STACK,)),
    'stack-s13-comma': ('stack/expressions.py', '            raise InvalidAnswer(UNENCAPSULATED_COMMA)', '            pass', 1, (STACK,)),
    'stack-s13-zero-to-the-zero': ('stack/expressions.py', 'if student and simplify and a.is_zero is True and b.is_zero is True:', 'if False:', 1,
                                   (STACK,)),
    'stack-s13-arc-names': ('stack/expressions.py', '"ln": "log", **INVERSE_TRIG_SYNONYMS}', '"ln": "log"}', 1, (STACK,)),
    'stack-s13-question-tests-bound': ('stack/engine.py', '            bound[inp["name"]] = evaluate(inp["teacher"], bound, assumptions=assumptions)\n',
                                       '            pass\n', 1, (STACK,)),
    # S-07 (0.7.0): the question options the engine does not read stop the build (examples/stack/probes/options.xml sets complexno
    # and decimals; the values of multiplicationsign and matrixparens that the example questions use stay allowed).
    'stack-s07-question-options': ('stack/importer.py', '    _question_options(name, element)\n', '', 1, (STACK,)),
    'stack-s07-complexno': ('stack/importer.py', '    "complexno": ("i",),\n', '', 1, (STACK,)),
    'stack-s07-decimals': ('stack/importer.py', '    "decimals": (".",),\n', '', 1, (STACK,)),
    'stack-s07-multiplicationsign-none': ('stack/importer.py', '"multiplicationsign": ("dot", "none"),', '"multiplicationsign": ("dot",),', 1, (STACK,)),
    'stack-s07-matrixparens-round': ('stack/importer.py', '"matrixparens": ("[", "("),', '"matrixparens": ("[",),', 1, (STACK,)),
    # S-05 (0.8.0): a numerical answer test that cannot be applied to the answer is false, with its note (supplement rows,
    # examples/stack/probes/numabs-branch.xml, examples/stack/supplement/numerical-applicability.xml).
    'stack-s05-not-a-number': ('stack/assessment.py', '        if not _real_number(student_value):\n', '        if False:\n', 1, (STACK,)),
    'stack-s05-teacher-not-a-number': ('stack/assessment.py', '        if name != "NumDecPlaces" and not _real_number(teacher_value):\n',
                                       '        if False:\n', 1, (STACK,)),
    'stack-s05-cas-valid': ('stack/assessment.py', 'return {**_result(True, False, note, feedback), "cas_valid": False}',
                            'return {**_result(True, False, note, feedback), "cas_valid": True}', 1, (STACK,)),
    'stack-s05-absolute-note': ('stack/assessment.py', '    "NumAbsolute": ("ATNumerical_SA_not_number",', '    "NumAbsolute": ("ATNumerical_SA_not_a_number",', 1, (STACK,)),
    'stack-s05-relative-note': ('stack/assessment.py', '    "NumRelative": ("ATNumerical_SA_not_number",', '    "NumRelative": ("ATNumerical_SA_not_a_number",', 1, (STACK,)),
    'stack-s05-decplaces-note': ('stack/assessment.py', '"NumDecPlaces": ("ATNumDecPlaces_SA_Not_num",', '"NumDecPlaces": ("ATNumDecPlaces_SA_Not_a_num",', 1, (STACK,)),
    'stack-s05-decplaces-integer': ('stack/assessment.py', '        return _not_applicable(_NOT_A_NUMBER[name])\n    try:\n        teacher_decimal',
                                    '        return _result(False, False, "invalid", "")\n    try:\n        teacher_decimal', 1, (STACK,)),
}

# Mutations that no golden row reaches and that tests/ catch: the pytest files of the test column must fail on the
# mutated copy of src/. S-13: the globally forbidden names (error, lisp), the names that Maxima's syntax reserves
# (do), the S-01 name check for further question-variable names (alpha, a_b, v_0, ...), and the question tests'
# inputs validated as the unsimplified value (abc*0+ta) and written as a student writes them (abs, mod).
TESTS = {
    'stack-s13-globally-forbidden-names': ('stack/student_input.py', '        if name in stack_data.GLOBALLY_FORBIDDEN:', '        if False:', 1,
                                           ('tests/stack/test_input_text.py',)),
    'stack-s13-reserved-names': ('stack/student_input.py', '    if name in stack_data.UNREADABLE:\n        return False\n', '', 1,
                                 ('tests/stack/test_input_text.py',)),
    'stack-s01-names-a': ('stack/student_input.py', '        if name in author_names and len(messages) == before:',
                          '        if name in author_names and not _readable(name, keys) and len(messages) == before:', 1,
                          ('tests/stack/test_input_text.py',)),
    'stack-s01-names-b': ('stack/student_input.py', '        if name in author_names and len(messages) == before:',
                          '        if any(part in author_names for part in name.split("_")) and len(messages) == before:', 1,
                          ('tests/stack/test_input_text.py',)),
    'stack-s13-question-tests-unsimplified': ('stack/engine.py', '        for text in ([displayed[key]] if displayed and key in displayed else []) + [answers.get(key, "")]:',
                                              '        for text in [answers.get(key, "")]:', 1, ('tests/stack/test_question_test_inputs.py',)),
    'stack-s13-question-tests-computed': ('stack/engine.py', '            actual = grade(question, raw, variant=variant, displayed=displayed)',
                                           '            actual = grade(question, {key: "x" for key in raw}, variant=variant, displayed=displayed)', 1,
                                           ('tests/stack/test_question_test_inputs.py',)),
    'stack-s13-question-tests-abs': ('stack/expressions.py', 'return f"abs({self._print(expr.args[0])})"', 'return f"Abs({self._print(expr.args[0])})"', 1,
                                     ('tests/stack/test_question_test_inputs.py',)),
    'stack-s13-question-tests-mod': ('stack/expressions.py', 'return f"mod({self._print(expr.args[0])}, {self._print(expr.args[1])})"',
                                     'return f"Mod({self._print(expr.args[0])}, {self._print(expr.args[1])})"', 1,
                                     ('tests/stack/test_question_test_inputs.py',)),
    # S-07 (0.7.0): the options that no golden question sets, the empty value, and every unsupported option named.
    'stack-s07-scientificnotation': ('stack/importer.py', '    "scientificnotation": ("*10",),\n', '', 1, ('tests/stack/test_importer.py',)),
    'stack-s07-inversetrig': ('stack/importer.py', '    "inversetrig": ("cos-1",),\n', '', 1, ('tests/stack/test_importer.py',)),
    'stack-s07-logicsymbol': ('stack/importer.py', '    "logicsymbol": ("lang",),\n', '', 1, ('tests/stack/test_importer.py',)),
    'stack-s07-sqrtsign': ('stack/importer.py', '    "sqrtsign": ("1",),\n', '', 1, ('tests/stack/test_importer.py',)),
    'stack-s07-empty-value': ('stack/importer.py', 'if found is not None and (found.text or "").strip() not in supported:',
                              'if found is not None and (found.text or "").strip() and (found.text or "").strip() not in supported:', 1,
                              ('tests/stack/test_importer.py',)),
    'stack-s07-first-option-only': ('stack/importer.py', 'unsupported.append((option, (found.text or "").strip(), supported))',
                                    'unsupported.append((option, (found.text or "").strip(), supported))\n            break', 1,
                                    ('tests/stack/test_importer.py',)),
    # S-05 (0.8.0): what no golden row reaches.
    'stack-s05-option-first': ('stack/assessment.py',
                               '        option = _numerical_option(name, options, env, assumptions)\n        if not _real_number(student_value):\n'
                               '            return _not_applicable(_NOT_A_NUMBER[name])\n',
                               '        if not _real_number(student_value):\n            return _not_applicable(_NOT_A_NUMBER[name])\n'
                               '        option = _numerical_option(name, options, env, assumptions)\n', 1,
                               ('tests/stack/test_numerical_applicability.py',)),
    'stack-s05-collection-teacher': ('stack/assessment.py', 'and not isinstance(teacher_value, MatrixValue) and not is_collection(teacher_value) \\\n            and not is_logical(teacher_value):',
                                     ':', 1, ('tests/stack/test_numerical_applicability.py',)),
}

# A few minutes: CI runs them in a step of their own (CTM_MUTATION_TESTS=1).
pytestmark = pytest.mark.skipif(not os.environ.get('CTM_MUTATION_TESTS') or bool(os.environ.get('CTM_CHECKERS_WHEEL')),
                                reason='set CTM_MUTATION_TESTS=1 (runs on a copy of src/)')


def package(tmp_path, mutation=None):
    folder = tmp_path / (mutation or 'unchanged')
    shutil.copytree(ROOT / 'src' / 'ctm_checkers', folder / 'ctm_checkers', ignore=shutil.ignore_patterns('__pycache__'))
    if mutation:
        module, text, replacement, occurrences, _ = {**MUTATIONS, **TESTS}[mutation]
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


def test_the_unchanged_copy_passes_those_tests(tmp_path):
    files = sorted({name for spec in TESTS.values() for name in spec[4]})
    result = subprocess.run([sys.executable, '-m', 'pytest', '-q', '-p', 'no:cacheprovider', *files], capture_output=True, text=True, cwd=ROOT,
                            env=dict(os.environ, CTM_CHECKERS_WHEEL=str(package(tmp_path)), CTM_MUTATION_TESTS=''))
    assert result.returncode == 0, result.stdout[-1500:] + result.stderr[-500:]


@pytest.mark.parametrize('mutation', list(TESTS))
def test_each_test_mutation_fails(tmp_path, mutation):
    """The tests of the row fail on the mutated copy (exit status 1: a test fails; not a collection error)."""
    folder = package(tmp_path, mutation)
    result = subprocess.run([sys.executable, '-m', 'pytest', '-q', '-x', '-p', 'no:cacheprovider', *TESTS[mutation][4]],
                            capture_output=True, text=True, cwd=ROOT, env=dict(os.environ, CTM_CHECKERS_WHEEL=str(folder), CTM_MUTATION_TESTS=''))
    assert result.returncode == 1, result.stdout[-1500:] + result.stderr[-500:]
    assert ' failed' in result.stdout.splitlines()[-1]
