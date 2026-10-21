"""The STACK golden tables: the engine adapters, the calls and the inputs.

tools/golden.py runs and records the tables; this module knows the STACK
engine (stack-sympy's, moved into ctm_checkers.stack) and its inputs
(docs/goldens.md). Every row runs on the engine an adapter provides:

  legacy  stack-sympy at the commit in tools/pins.json (--stack-legacy DIR): its
          _extensions/stack-sympy/stack_sympy and scripts/native_compliance.
  ctm     ctm_checkers.stack (from src/, the wheel or the installed payload)
          and tools/stack_native/native_compliance.

Calls (a row's "call") and what they run, as stack-sympy's build (cli.py) and
its page worker (worker.js) run them:

  stack.case         python_runner.evaluate_case(case): a compliance or
                     regression fixture case (the compliance report's Python
                     observation)
  stack.answer_test  answer_test(test, student, teacher, options[, raw=...])
  stack.import       import_xml(file, python_checkers=...): the question models
  stack.instantiate  instantiate(question, seed): the frozen variant
  stack.card         cli.render(...): the card's HTML, as its SHA-256 and length
  stack.tests        run_question_tests(question, seeds=[seed], variants=[variant]),
                     the worker's "tests" request
  stack.answer       validate and grade of one answer set, the worker's
                     "validate" and "grade" requests

The page receives the question and the variant as JSON, so validate, grade
and the question tests run on JSON copies, and a result is stored as the
worker returns it (json.dumps(result, default=str)). Paths in inputs are
relative to this repository (examples/stack/...).

Standard library only at import time; runs in native Python (3.9 or later)
and inside Pyodide (tools/pyodide/verify.cjs).
"""
import copy
import hashlib
import importlib
import json
import os
from pathlib import Path
import re
import sys
import types

ROOT = Path(__file__).resolve().parents[1]

CALLS = ('stack.case', 'stack.answer_test', 'stack.import', 'stack.instantiate', 'stack.card', 'stack.tests', 'stack.answer')


def raised(error):
    """An exception of a STACK call: its class name and message (without the
    module, which the move renames: stack_sympy.importer is now
    ctm_checkers.stack.importer)."""
    return f'{type(error).__name__}: {error}'


def jsonable(value):
    """A result as the page's worker returns it: json.dumps(value, default=str), parsed."""
    return json.loads(json.dumps(value, default=str))


class Engine:
    """One STACK engine: its modules and the question cache of a run."""

    def __init__(self, name, importer, engine, assessment, cli, runner, describe):
        self.name = name
        self.importer, self.engine, self.assessment, self.cli, self.runner = importer, engine, assessment, cli, runner
        self.description = describe
        self._questions = {}
        self._variants = {}

    def describe(self):
        return self.description

    # Questions and variants, cached per run: the imported models (as the
    # build has them) and their JSON text (as the page has them).
    def questions(self, value):
        key = (value['file'], value.get('python_checkers'))
        if key not in self._questions:
            checkers = value.get('python_checkers')
            try:
                imported = self.importer.import_xml(ROOT / value['file'], python_checkers=ROOT / checkers if checkers else None)
                self._questions[key] = (imported, None)
            except Exception as error:   # the import row reports it; the other rows raise it again
                self._questions[key] = (None, error)
        imported, error = self._questions[key]
        if error is not None:
            raise error
        return imported

    def question(self, value):
        matches = [q for q in self.questions(value) if q['name'] == value['question']]
        if len(matches) != 1:
            raise ValueError(f'{value["file"]}: expected one question named {value["question"]!r}, found {len(matches)}')
        return matches[0]

    def variant(self, value):
        key = (value['file'], value.get('python_checkers'), value['question'], value['seed'])
        if key not in self._variants:
            try:
                self._variants[key] = (json.dumps(self.engine.instantiate(copy.deepcopy(self.question(value)), value['seed'])), None)
            except Exception as error:
                self._variants[key] = (None, error)
        text, error = self._variants[key]
        if error is not None:
            raise error
        return json.loads(text)

    def page_question(self, value):
        return json.loads(json.dumps(self.question(value)))


def run(engine, call, value, raised=raised):
    """A row's result (a JSON value); `raised(error)` writes an exception."""
    if call == 'stack.case':
        return jsonable(engine.runner.evaluate_case(dict(value)))
    if call == 'stack.answer_test':
        options = {'raw': value['raw']} if 'raw' in value else {}
        return jsonable(engine.assessment.answer_test(value['test'], value['student'], value['teacher'], value['options'], **options))
    if call == 'stack.import':
        return jsonable(copy.deepcopy(engine.questions(value)))
    if call == 'stack.instantiate':
        return engine.variant(value)
    if call == 'stack.card':
        checkers = value.get('python_checkers')
        text = engine.cli.render(str(ROOT / value['file']), value['question'], value['id'], value['variants'], value['seed'],
                                 value['review'], value['diagnostics'], str(ROOT / checkers) if checkers else None)
        data = text.encode('utf-8')
        return {'sha256': hashlib.sha256(data).hexdigest(), 'length': len(data)}
    if call == 'stack.tests':
        variant = engine.variant(value)
        return jsonable(engine.engine.run_question_tests(engine.page_question(value), seeds=[variant['seed']], variants=[variant]))
    if call == 'stack.answer':
        out = {}
        for name in ('validate', 'grade'):
            try:
                out[name] = jsonable(getattr(engine.engine, name)(engine.page_question(value), dict(value['answers']),
                                                                  variant=engine.variant(value)))
            except Exception as error:
                out[name] = {'raised': raised(error)}
        return out
    raise SystemExit('Unknown call: ' + call)


# ---------------------------------------------------------------------------
# Engines
# ---------------------------------------------------------------------------

def _fresh(prefixes):
    for name in [n for n in sys.modules if any(n == p or n.startswith(p + '.') for p in prefixes)]:
        del sys.modules[name]


def legacy(folder):
    """stack-sympy's own code at the pinned commit (a checkout, --stack-legacy DIR)."""
    folder = Path(folder).resolve()
    extension = folder / '_extensions' / 'stack-sympy'
    if not (extension / 'stack_sympy' / 'engine.py').is_file() or not (folder / 'scripts' / 'native_compliance').is_dir():
        raise SystemExit(f'{folder}: not a stack-sympy checkout (no _extensions/stack-sympy/stack_sympy, scripts/native_compliance)')
    _fresh(('stack_sympy', 'native_compliance'))
    for path in (folder / 'scripts', extension):
        if str(path) in sys.path:
            sys.path.remove(str(path))
        sys.path.insert(0, str(path))
    importlib.invalidate_caches()
    helper = importlib.import_module('stack_sympy.basis_helper')
    # The example checker files import assess_basis from ctm_checkers.matrix,
    # its one home since the move; stack-sympy had the same function as
    # stack_sympy.basis_helper (design §6.3: import shims, so that the same
    # inputs run on the old and the new code).
    package = sys.modules.get('ctm_checkers')
    if package is not None and not getattr(package, '_ctm_legacy_shim', False):
        raise SystemExit('The legacy STACK adapter needs ctm_checkers.matrix as a shim, but ctm_checkers is imported')
    if package is None:
        package = types.ModuleType('ctm_checkers')
        package.__path__ = []
        package._ctm_legacy_shim = True
        sys.modules['ctm_checkers'] = package
    sys.modules['ctm_checkers.matrix'] = helper
    package.matrix = helper
    module = lambda name: importlib.import_module(name)
    sources = sorted((extension / 'stack_sympy').glob('*.py'))
    digest = hashlib.sha256(b''.join(p.name.encode() + b'\0' + p.read_bytes() for p in sources)).hexdigest()
    return Engine('legacy', module('stack_sympy.importer'), module('stack_sympy.engine'), module('stack_sympy.assessment'),
                  module('stack_sympy.cli'), module('native_compliance.python_runner'),
                  {'stack-sympy': str(folder), 'stack_sympy_sha256': digest})


def ctm():
    """ctm_checkers.stack, from whatever ctm_checkers is imported (None without it)."""
    try:
        stack = importlib.import_module('ctm_checkers.stack')
    except ImportError as error:
        if getattr(error, 'name', None) not in ('ctm_checkers.stack',):
            raise
        return None
    tools = ROOT / 'tools' / 'stack_native'
    _fresh(('native_compliance',))
    if str(tools) not in sys.path:
        sys.path.insert(0, str(tools))
    module = lambda name: importlib.import_module(name)
    return Engine('ctm', module('ctm_checkers.stack.importer'), module('ctm_checkers.stack.engine'),
                  module('ctm_checkers.stack.assessment'), module('ctm_checkers.stack.cli'),
                  module('native_compliance.python_runner'), {'stack': stack.__file__})


# ---------------------------------------------------------------------------
# Inputs (recording only; tools/golden.py record)
# ---------------------------------------------------------------------------

# The files of the inputs, by table: what each table's rows are made from,
# and the licence of what they are derived from (tests/golden/PROVENANCE.md).
TABLES = {
    'stack/compliance': ('STACK answer-test fixture rows (tests/stack/native_compliance/fixtures.json: STACK '
                         '10d3233 tests/fixtures/answertestfixtures.class.php) through the compliance runner',
                         'GPL-3.0-or-later (STACK); tests/stack/native_compliance/COPYING.txt'),
    'stack/regressions': ("stack-sympy's port regression cases (tests/stack/port_regressions/fixtures.json)",
                          'AGPL-3.0-or-later'),
    'stack/reference': ("stack-sympy's reference cases for the native comparison (tests/stack/reference_cases.json)",
                        'AGPL-3.0-or-later'),
    'stack/questions-project': ("stack-sympy's own example questions (examples/stack/*.xml) with their checker files, "
                                "and the answers of the stack-sympy audit's leak.py (S-01)",
                                'the questions CC-BY-SA-4.0 as each file states (determinant-one.xml AGPL-3.0-or-later); '
                                'the checker files and the answers AGPL-3.0-or-later'),
    'stack/questions-library': ('STACK sample questions: the corpus (examples/stack/corpus), the corrected teaching '
                                'copies (examples/stack/corrected) and AlgMap-6.1 (examples/stack/upstream)',
                                'CC-BY-SA-4.0; examples/stack/corpus/COPYING.txt, examples/stack/upstream/COPYING.txt'),
    'stack/questions-helm': ('HELM sample questions from STACK (examples/stack/upstream/bodmas.xml, rounding-three-dp.xml); '
                             'test data only, see below',
                             'CC-BY-NC-4.0 (NonCommercial; test data only, not the AGPL-3.0-or-later of the code); '
                             'examples/stack/upstream/HELM-COPYING.txt'),
    'stack/questions-course': ('course material: the STACK questions derived from the course ingmat3a_ntnu '
                               '(examples/stack/course-b-rank-pivots.xml, course-b-nullspace.xml, course-c-nullspace.xml); '
                               'see below',
                               'the questions CC-BY-SA-4.0 (course material, Andrey Chesnokov; '
                               'examples/stack/course-examples-provenance.json); the checker file '
                               'examples/stack/matrix-checkers.py and the answers AGPL-3.0-or-later'),
    'stack/probes': ('answer-test probes of the stack-sympy audit (ctm-assessment docs/consolidation/stack-sympy-audit-2026-10/'
                     'probes: cases1-4.json, perf*.py) with the native verdicts of STACK 10d3233 and Maxima 5.46 (out1-4.json)',
                     'AGPL-3.0-or-later; the "native" values are output of STACK (GPL-3.0-or-later) and Maxima'),
    'stack/probe-questions': ('question probes of the stack-sympy audit (examples/stack/probes/*.xml with the answers of its '
                              'qprobe.py, crash.py and overflow.cjs)', 'AGPL-3.0-or-later'),
    'stack/supplement': ('inputs written for these tables (tools/golden_stack.py SUPPLEMENT, examples/stack/supplement/): '
                         'rules that no other row reached (the reviews of C3 and S-01)', 'AGPL-3.0-or-later'),
}

# Questions derived from course material (examples/stack/course-examples-provenance.json):
# their rows are the table stack/questions-course, and no other table has any
# (AC, 20 Oct 2026: these fixed files get their own table, labelled as course
# material; rows generated from the course repositories stay in the umbrella,
# design §13 item 7). course-b-rank-pivots.xml is S-01's test case.
COURSE_DERIVED = ('examples/stack/course-b-rank-pivots.xml', 'examples/stack/course-b-nullspace.xml',
                  'examples/stack/course-c-nullspace.xml')
# HELM sample questions of STACK's library, CC BY-NC 4.0 (examples/stack/upstream/sources.json):
# their rows are the table stack/questions-helm. AC (20 Oct 2026): kept, clearly labelled as
# NonCommercial test data; the code stays AGPL-3.0-or-later.
HELM = ('examples/stack/upstream/bodmas.xml', 'examples/stack/upstream/rounding-three-dp.xml')

# Strings a learner may type that the input rules must handle (design §6.2).
INVALID = ['', 'x+', 'sin(', '2 x', 'x²', 'π', '3,5', "__import__('os')", 'x+' * 650]


def question_table(path):
    if path in COURSE_DERIVED:
        return 'stack/questions-course'
    if path.startswith('examples/stack/supplement/'):
        return 'stack/supplement'
    if path in HELM:
        return 'stack/questions-helm'
    if path.startswith(('examples/stack/corpus/', 'examples/stack/corrected/', 'examples/stack/upstream/')):
        return 'stack/questions-library'
    if path.startswith('examples/stack/probes/'):
        return 'stack/probe-questions'
    return 'stack/questions-project'


def site_blocks(folder):
    """The stack-question blocks of stack-sympy's site (its .qmd pages), with
    their files as paths in examples/stack/."""
    blocks = []
    for page in sorted(list(folder.glob('*.qmd')) + list((folder / 'docs').glob('*.qmd'))):
        text = page.read_text(encoding='utf-8')
        # The block's attributes in any order: {.stack-question #id} or {#id .stack-question}.
        for match in re.finditer(r'^```\{([^}\n]*?(?<![\w-])\.stack-question(?![\w-])[^}\n]*)\}\n(.*?)^```', text, re.M | re.S):
            options = dict(re.findall(r'^#\|\s*([\w-]+):\s*(.*?)\s*$', match[2], re.M))
            if 'file' not in options:
                continue
            def path(name):
                resolved = os.path.normpath(os.path.join(os.path.relpath(page.parent, folder), name))
                if not resolved.startswith('questions' + os.sep):
                    return None
                return 'examples/stack/' + Path(resolved).relative_to('questions').as_posix()
            file = path(options['file'])
            if file is None:
                continue
            identifier = re.search(r'#([\w-]+)', match[1])
            blocks.append({'file': file, 'question': options['question'],
                           'python_checkers': path(options['python-checkers']) if 'python-checkers' in options else None,
                           'variants': int(options.get('variants', 1)), 'seed': int(options.get('seed', 1)),
                           'review': options.get('review') == 'true', 'diagnostics': options.get('diagnostics') == 'true',
                           'id': identifier[1] if identifier else 'stack-sympy-card'})
    return blocks


CHECKER_FILES = {'examples/stack/python-checker.xml': 'examples/stack/checkers.py'}


def checkers_of(path, blocks):
    named = {b['python_checkers'] for b in blocks if b['file'] == path and b['python_checkers']}
    if path in CHECKER_FILES:
        named.add(CHECKER_FILES[path])
    if not named and (ROOT / path).read_text(encoding='utf-8').count('PythonChecker'):
        named.add('examples/stack/matrix-checkers.py')
    if len(named) > 1:
        raise SystemExit(f'{path}: more than one checker file on the site: {sorted(named)}')
    return named.pop() if named else None


def corpus_seeds(folder):
    """The corpus replay's seeds (scripts/check_corpus.py seeds_for): the first
    three deployed seeds, or 17, 29, 47."""
    manifest = json.loads((ROOT / 'examples' / 'stack' / 'corpus' / 'manifest.json').read_text(encoding='utf-8'))
    return {'examples/stack/corpus/' + q['file']: list(q['deployed_seeds'][:3]) or [17, 29, 47] for q in manifest['questions']}


def _answer_sets(engine, question, variant, full):
    """Answer sets for one variant: the teacher's answers, the question tests'
    inputs, and for each input in turn (the others keep the teacher's answer):
    sign, offsets and a multiple of the teacher's answer, its factored,
    expanded and decimal forms, every question and feedback variable's name
    (S-01) and strings the input rules must handle. `full`: all of them; else
    the teacher's answers, the tests' inputs and the sign."""
    sp = importlib.import_module('sympy')
    eng = engine.engine
    env = eng._environment(question, variant)
    assumptions = eng._assumptions(question)
    teacher, values = {}, {}
    for inp in question['inputs']:
        try:
            teacher[inp['name']] = eng._qtest_answer(question, inp['teacher'], env)
        except Exception:
            teacher[inp['name']] = ''
        try:
            values[inp['name']] = engine.engine.evaluate(inp['teacher'], env, assumptions=assumptions)
        except Exception:
            values[inp['name']] = None
    sets = [dict(teacher)]
    try:
        tested = eng.run_question_tests(question, variants=[variant])
        sets += [dict(result['inputs']) for result in tested['results']]
    except Exception:
        pass
    for name, answer in teacher.items():
        candidates = [f'-({answer})'] if answer else []
        if full:
            value = values[name]
            if answer:
                candidates += [f'({answer})+1', f'({answer})-1', f'2*({answer})']
            if isinstance(value, sp.Expr) and not isinstance(value, sp.MatrixBase):
                for form in (sp.factor, sp.expand):
                    try:
                        candidates.append(eng._source(form(value)))
                    except Exception:
                        pass
                if value.is_number:
                    try:
                        candidates.append(str(sp.N(value, 8)))
                    except Exception:
                        pass
            # The names a student may not use (ctm-checkers 0.3.0 adds the feedback
            # variables'; stack-sympy's engine has no _author_names).
            names = eng._author_names(question, variant['env']) if hasattr(eng, '_author_names') else variant['env']
            candidates += sorted(names)
            candidates += INVALID
        for candidate in candidates:
            sets.append(dict(teacher, **{name: candidate}))
    unique, seen = [], set()
    for answers in sets:
        key = json.dumps(answers, sort_keys=True)
        if key not in seen:
            seen.add(key)
            unique.append(answers)
    return unique


_INPUT_RULES = {'ans1': 'x', 'ans2': '1/2', 'ans3': '2/3', 'ans4': 'a or b and c', 'ans5': 'matrix([1,2],[3,4])'}


# Extra answer sets of the audit's question probes (qprobe.py, crash.py,
# overflow.cjs) and leak.py (S-01), by file.
PROBE_ANSWERS = {
    'examples/stack/probes/quiet.xml': [{'ans1': '(x+2)*(x-1)'}, {'ans1': 'x^2+x-2'}],
    'examples/stack/probes/thirds.xml': [{'a': '1', 'b': '2', 'c': '3'}],
    'examples/stack/probes/physics-I.xml': [{'ans1': '-R'}],
    'examples/stack/probes/numabs-branch.xml': [{'ans1': '45*x'}, {'ans1': '0.785'}, {'ans1': 'exp(exp(exp(exp(10))))'}],
    'examples/stack/probes/options.xml': [{'ans1': '3+4*j'}, {'ans1': '3,5'}],
    'examples/stack/probes/twoparts.xml': [{'ans1': '2', 'ans2': ''}],
    'examples/stack/probes/eqtype.xml': [{'ans1': '2*x+1'}],
    'examples/stack/probes/crash.xml': [{'ans1': 'x+1'}, {'ans1': 'x=1'}, {'ans1': 'a and b'},
                                       {'ans1': 'cosh(x)^20-((exp(x)+exp(-x))/2)^20+x+1'}],
    'examples/stack/polynomial-expansion.xml': [{'ans': 'ta'}],
    'examples/stack/rational-equivalence.xml': [{'ans': 'ta'}],
    'examples/stack/numerical-measurement.xml': [{'perimeter': 'ta_perimeter', 'area': 'ta_area', 'area2': 'ta_area'}],
    'examples/stack/python-checker.xml': [{'ans': 'd'}],
    'examples/stack/zero-product.xml': [{'ans': 'ta'}],
    # S-01: question variables (k, f, ta) and feedback variables (d, sa) in
    # an answer, alone, inside an expression, with implied multiplication,
    # twice, and both kinds at once (ANSWERS_ONLY).
    'examples/stack/supplement/forbidden-variables.xml': [
        {'ans1': 'ta'}, {'ans1': 'd'}, {'ans1': 'sa'}, {'ans1': '2ta-ta'}, {'ans1': 'k*2*x+1'}, {'ans1': 'd+0*f'}],
    # S-01 (ctm-checkers 0.4.0): the feedback variables of the second
    # response tree, separated by a newline (w, zz), and both trees' at once.
    'examples/stack/supplement/forbidden-variables-prts.xml': [{'ans1': 'w'}, {'ans1': 'zz'}, {'ans1': 'sa+zz'}],
    # The input rules no other row reached (the review of C3): forbidden
    # words in any case, the numerical input's type, lowest terms with two
    # negative numbers, and/or precedence in the validation's LaTeX, the
    # 64-entry matrix limit.
    'examples/stack/supplement/input-rules.xml': [
        dict(_INPUT_RULES, **change) for change in (
            {'ans1': 'sin(x)'}, {'ans1': 'x+SIN'}, {'ans2': 'x'}, {'ans2': 'sqrt(2)'},
            {'ans3': '(-2)/(-3)'}, {'ans3': '-2/3'}, {'ans3': '2/(-3)'}, {'ans3': '(-4)/6'},
            {'ans4': '(a or b) and c'}, {'ans4': 'a and b or c'}, {'ans4': 'a and (b or c)'}, {'ans4': 'not a or b'},
            {'ans5': 'matrix(' + ','.join('[' + ','.join(['1'] * 13) + ']' for _ in range(5)) + ')'},
            {'ans5': 'matrix(' + ','.join('[' + ','.join(['1'] * 8) + ']' for _ in range(8)) + ')'})],
}


# Questions whose rows are only the answers in PROBE_ANSWERS at seed 1, each of
# which uses a question or feedback variable's name: S-01's questions, so that
# the golden diffs of S-01 (ctm-checkers 0.3.0, 0.4.0) touch only such rows.
ANSWERS_ONLY = ('examples/stack/supplement/forbidden-variables.xml', 'examples/stack/supplement/forbidden-variables-prts.xml')


def question_inputs(engine, folder, out=print):
    """The question rows' inputs, by table (question_table): every XML file
    of examples/stack with the seeds stack-sympy's site and the corpus replay
    use (CTM's own and the course's questions also 1 to 3), the cards of
    stack-sympy's site, and the audit's question probes."""
    blocks = site_blocks(folder)
    corpus = corpus_seeds(folder)
    files = sorted(p.relative_to(ROOT).as_posix() for p in (ROOT / 'examples' / 'stack').rglob('*.xml'))
    rows = {}

    def add(call, value, tags):
        table = question_table(value['file'])
        rows.setdefault(table, []).append((call, value, tags))

    for path in files:
        checkers = checkers_of(path, blocks)
        base = {'file': path, **({'python_checkers': checkers} if checkers else {})}
        if path in ANSWERS_ONLY:
            for question in engine.questions(base):
                for answers in PROBE_ANSWERS[path]:
                    add('stack.answer', dict(base, question=question['name'], seed=1, answers=answers), ['answer'])
            continue
        add('stack.import', base, ['import'])
        try:
            questions = engine.questions(base)
        except Exception as error:
            out(f'  {path}: import raises {type(error).__name__}: {str(error)[:120]}')
            continue
        used = [b for b in blocks if b['file'] == path]
        for block in used:
            card = {key: block[key] for key in ('file', 'question', 'id', 'variants', 'seed', 'review', 'diagnostics')}
            if block['python_checkers']:
                card['python_checkers'] = block['python_checkers']
            add('stack.card', card, ['card'])
        for question in questions:
            seeds = []
            for block in used:
                if block['question'] == question['name']:
                    seeds += range(block['seed'], block['seed'] + block['variants'])
            seeds += corpus.get(path, [])
            # cli.py's default card: three variants from seed 1. CTM's own
            # questions (and the course's) have them too, with every answer
            # set at seed 1 as at the site's first seed.
            own = question_table(path) in ('stack/questions-project', 'stack/questions-course')
            if own or not seeds:
                seeds += [1, 2, 3]
            seeds = sorted(set(seeds), key=seeds.index)
            for number, seed in enumerate(seeds):
                value = dict(base, question=question['name'], seed=seed)
                add('stack.instantiate', value, ['instantiate'])
                try:
                    variant = engine.variant(value)
                except Exception as error:
                    out(f'  {path} seed {seed}: instantiate raises {type(error).__name__}: {str(error)[:120]}')
                    continue
                add('stack.tests', value, ['qtests'])
                sets = _answer_sets(engine, question, variant, full=number == 0 or own and seed == 1)
                if number == 0:
                    sets += [answers for answers in PROBE_ANSWERS.get(path, []) if answers not in sets]
                for answers in sets:
                    add('stack.answer', dict(value, answers=answers), ['answer'])
    return rows


# Answer tests at the rules that no other row reached (the mutation tests of
# C3 found them): NumAbsolute's bound (strict, with STACK's 1e-9 guard),
# NumRelative's (inclusive, also at zero tolerance), each for exact numbers
# and, within 1e-9 of the bound, for irrational ones; AlgEquiv's numeric
# rejection screen (STACK's 1e-4 margin), which rejects before a proof that
# would exceed its expansion bound. examples/stack/supplement/score-modes.xml adds
# response-tree scores outside [0, 1] (clamped).
SUPPLEMENT = [
    ('NumAbsolute', '1.1', '1', '0.1'), ('NumAbsolute', '0.9', '1', '0.1'), ('NumAbsolute', '1.100000001', '1', '0.1'),
    ('NumAbsolute', '1.1000000011', '1', '0.1'), ('NumAbsolute', '1.1000000009', '1', '0.1'),
    ('NumRelative', '1.01', '1', '0.01'), ('NumRelative', '0.99', '1', '0.01'), ('NumRelative', '0', '0', '0'),
    ('NumRelative', '1.0100000001', '1', '0.01'), ('NumRelative', '1.01000000000999', '1', '0.01'),
    ('NumAbsolute', 'pi', '3.14159', '0.0000026535'), ('NumAbsolute', 'pi', '3.14159', '0.000002652'),
    ('NumRelative', 'pi', '3.14159', '0.00000084466457852'), ('NumRelative', 'pi', '3.14159', '0.000000844'),
    ('AlgEquiv', 'sin(x)^20', '((1-cos(2*x))/2)^10*1001/1000', ''), ('AlgEquiv', 'cosh(x)^20', '((exp(x)+exp(-x))/2)^20*1001/1000', ''),
    ('AlgEquiv', 'sin(x)^20', '((1-cos(2*x))/2)^10*(1+1/100000)', ''),
]


def supplement_inputs():
    return [('stack.answer_test', {'test': test, 'student': student, 'teacher': teacher, 'options': options, 'raw': student},
             ['supplement', test], {}) for test, student, teacher, options in SUPPLEMENT]


def case_inputs(fixture):
    """Compliance or regression cases: the fields evaluate_case reads."""
    cases = json.loads(fixture.read_text(encoding='utf-8'))['cases']
    out = []
    for case in cases:
        value = {key: case[key] for key in ('id', 'test', 'student', 'teacher', 'options') if key in case}
        extra = {}
        if 'expected_score' in case:   # the STACK fixture's own expectation
            extra['native'] = {'expected_score': case['expected_score'], 'answer_note': case['answer_note']}
        tags = [case['test']] + ([case['group']] if case.get('group') else [])
        out.append(('stack.case', value, tags, extra))
    return out


def probe_inputs(probes):
    """The audit's answer-test probes with their native verdicts, and the
    performance probes (perf*.py)."""
    out = []
    for number in range(1, 5):
        native = json.loads((probes / f'out{number}.json').read_text(encoding='utf-8'))
        for row in native:
            value = {'test': row['test'], 'student': row['student'], 'teacher': row['teacher'], 'options': row['options'],
                     'raw': row['student']}
            out.append(('stack.answer_test', value, ['probe', f'cases{number}'], {'native': row['native'], 'port_audit': row['port']}))
    for script in sorted(probes.glob('perf*.py')):
        for test, student, teacher, options in re.findall(r'\("(\w+)", "([^"]*)", "([^"]*)", "([^"]*)"\)', script.read_text(encoding='utf-8')):
            value = {'test': test, 'student': student, 'teacher': teacher, 'options': options, 'raw': student}
            out.append(('stack.answer_test', value, ['probe', script.stem], {}))
    return out
