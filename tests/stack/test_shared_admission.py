"""Cross-language admission conformance, from source and exact wheel bytes.

Python remains the oracle until consumer adoption. These checks compare the
boundary before CAS evaluation, not the final grading result. No golden rows
are recorded or rewritten here.
"""
from dataclasses import asdict
import gzip
import hashlib
from importlib import resources
import json
import os
from pathlib import Path
import random
import shutil
import subprocess
import sys

import pytest

from ctm_checkers.stack import engine, expressions, stack_data, student_input
from tests.conftest import ROOT
from tests.stack.test_input_text import NATIVE


def reference(raw, options):
    normalized = None
    result = dict(schema=1, stackCommit=stack_data.STACK_COMMIT,
                  normalized=None, canonical=None, tree=None, feedback='')
    try:
        normalized = student_input.student_text(raw)
        question = {'prts': []}
        # _parse_answer computes the author names from the env and feedback
        # assignments. Inject those names at that boundary, without parsing a
        # second copy of the rules under test.
        from unittest.mock import patch
        with patch.object(engine, '_author_names', return_value=set(options['authorNames'])):
            tree = engine._parse_answer({'insertstars': options['insertstars']}, raw,
                                        dict.fromkeys(options['questionVariables']), question)
        result.update(status='admitted', normalized=normalized,
                      canonical=expressions.written_text(tree), tree=asdict(tree))
    except (expressions.InvalidAnswer, expressions.Unsupported) as error:
        result.update(status='unsupported' if isinstance(error, expressions.Unsupported) else 'invalid',
                      normalized=normalized, feedback=str(error))
    # Node.children are tuples; the wire holds ordinary JSON arrays.
    return json.loads(json.dumps(result))


@pytest.fixture(scope='module')
def vectors():
    texts = set()
    rows = 0
    for path in sorted((ROOT / 'tests/golden/stack').iterdir()):
        if not (path.name.endswith('.jsonl') or path.name.endswith('.jsonl.gz')):
            continue
        opener = gzip.open if path.suffix == '.gz' else open
        with opener(path, 'rt', encoding='utf-8') as stream:
            for line in stream:
                row = json.loads(line); rows += 1
                def visit(value):
                    if not isinstance(value, dict):
                        return
                    for key, item in value.items():
                        if key in ('raw', 'student') and isinstance(item, str):
                            texts.add(item)
                        elif key == 'answers' and isinstance(item, dict):
                            texts.update(v for v in item.values() if isinstance(v, str))
                        elif isinstance(item, dict):
                            visit(item)
                visit(row['input'])
    assert rows == 6193, 'Review admission coverage when the frozen inventory changes'
    texts.update(raw for raw, _ in NATIVE)
    # Every upstream replacement, identifier and casing, plus punctuation that
    # JS might accidentally treat as an object property or executable text.
    texts.update(old for old, _ in stack_data.REPLACEMENTS)
    for name in set(stack_data.VARIABLES) | set(stack_data.FUNCTIONS):
        texts.update((name, name + '(x)', name.upper(), name.upper() + '(x)'))
    texts.update(['', ' ', 'x\n+1', '\t', '\x1b', '\x00', '\ud800', '🙂', 'x²+y³', '2 x+abc', 'Sin x+abc',
                  'abc+Sin(x)', 'a_b', 'v_0', 'k_1', 'constructor', '__proto__', 'toString',
                  'constructor(x)', 'x;quit()', "'x", '"x"', '\\x', 'x+@', 'x+$', 'x[1]',
                  'x+(y+z)', 'x*(y*z)', '(x^y)^z', 'x^(y^z)', '-x^2', 'x^-2', '1.00+x+x',
                  'a=b=c', 'x+-1', '2x', '2(x+1)', '(x+1)2', 'not A and B or C',
                  '[1,{2,3},matrix([4])]', 'matrix([1,2],[3,4])',
                  '1' * expressions.MAX_DIGITS, '1' * (expressions.MAX_DIGITS + 1),
                  'x' * expressions.MAX_CHARS, 'x' * (expressions.MAX_CHARS + 1),
                  '+'.join(['x'] * 175), '+'.join(['x'] * 176),
                  '(' * 40 + 'x' + ')' * 40, '(' * 41 + 'x' + ')' * 41,
                  'not ' * 42 + 'x'])
    rng = random.Random(20261027)
    atoms = ['x', 'a', '1', '2.00', 'pi', 'sin(x)', '[1,2]', '{1,2}', 'true']
    def expression(depth):
        if depth == 0 or rng.random() < .35:
            return rng.choice(atoms)
        return '(' + expression(depth - 1) + rng.choice(['+', '-', '*', '/', '^', '=', ' and ', ' or ']) + expression(depth - 1) + ')'
    texts.update(expression(4) for _ in range(500))
    alphabet = 'xy12+*/^()[],{}_%:.!\'" '
    texts.update(''.join(rng.choice(alphabet) for _ in range(rng.randrange(1, 35))) for _ in range(500))
    cases = []
    for raw in sorted(texts):
        for insertstars in (0, 1):
            options = dict(insertstars=insertstars, questionVariables=['k', 'a_b', 'alpha', 'v_0'],
                           authorNames=['k', 'a_b', 'alpha', 'v_0', 'd', 'ta'])
            cases.append(dict(raw=raw, options=options, expected=reference(raw, options)))
    # Distinguish forbidden author feedback names from declared question keys.
    for raw in ['d', 'k', 'alpha', 'v_0', 'ta', 'a_b', 'k1', 'sin(x)', 'PI']:
        options = dict(insertstars=0, questionVariables=[], authorNames=[])
        cases.append(dict(raw=raw, options=options, expected=reference(raw, options)))
    for raw, feedback in NATIVE:
        options = dict(insertstars=0, questionVariables=['k', 'ta'], authorNames=['k', 'ta'])
        expected = reference(raw, options)
        assert expected['feedback'] == feedback
        cases.append(dict(raw=raw, options=options, expected=expected))
    return dict(goldenRows=rows, distinctTexts=len(texts), cases=cases)


def payload(vectors):
    package = resources.files('ctm_checkers.stack')
    return dict(source=package.joinpath('admission.js').read_text(encoding='utf-8'),
                data=json.loads(package.joinpath('admission-data.json').read_text(encoding='utf-8')),
                bundle=(ROOT / '_extensions/ctm-checkers/ctm-checkers-stack.js').read_text(encoding='utf-8'),
                cases=[dict(raw=c['raw'], options=c['options']) for c in vectors['cases']])


def compare(actual, vectors, platform):
    assert len(actual) == len(vectors['cases'])
    for got, case in zip(actual, vectors['cases']):
        assert got == case['expected'], (platform, case, got)
    report = os.environ.get('CTM_ADMISSION_REPORT')
    if report:
        folder = Path(report); folder.mkdir(parents=True, exist_ok=True)
        digest = hashlib.sha256(json.dumps(vectors, sort_keys=True, ensure_ascii=True).encode()).hexdigest()
        (folder / (platform + '.json')).write_text(json.dumps(dict(
            platform=platform, goldenRowsScanned=vectors['goldenRows'],
            distinctTexts=vectors['distinctTexts'], comparisons=len(actual), mismatches=0,
            vectorSha256=digest, stackCommit=stack_data.STACK_COMMIT), indent=2) + '\n')


def test_generated_admission_data_matches_python():
    subprocess.run([sys.executable, str(ROOT / 'tools/stack_native/admission_data.py'), '--check'], check=True)


def test_node_source_wheel_and_published_payload(vectors):
    assert shutil.which('node'), 'Node 22 or 24 is required for shared admission conformance'
    program = r'''
const fs = require('node:fs'), vm = require('node:vm');
const p = JSON.parse(fs.readFileSync(0, 'utf8'));
const context = {module: {exports: {}}};
vm.runInNewContext(p.source, context, {timeout: 2000});
const api = context.module.exports(p.data);
const bundled = {};
vm.runInNewContext(p.bundle, bundled, {timeout: 2000});
const results = [api, bundled.CTMCheckersStack.admission].map(a => p.cases.map(c => a.admitExpression(c.raw, c.options)));
// Source policy is copied; caller changes cannot rewrite a live instance.
p.data.READABLE.push('constructor'); p.data.functions.push('constructor');
if (api.admitExpression('constructor').status !== 'invalid') throw Error('Mutable policy');
if (!Object.isFrozen(api)) throw Error('Mutable API');
for (const options of [{insertstars: 2}, {authorNames: '__proto__'}, {questionVariables: [null]}]) {
  let rejected = false;
  try { api.admitExpression('x', options); } catch (e) { rejected = e.name === 'TypeError'; }
  if (!rejected) throw Error('Malformed author options accepted');
}
process.stdout.write(JSON.stringify({version: process.version, results}));
'''
    result = subprocess.run(['node', '-e', program], input=json.dumps(payload(vectors)),
                            capture_output=True, text=True, timeout=90, check=True)
    out = json.loads(result.stdout)
    compare(out['results'][0], vectors, 'node-' + out['version'])
    compare(out['results'][1], vectors, 'bundle-node-' + out['version'])


@pytest.mark.parametrize('browser_name', ['chromium', 'firefox', 'webkit'])
def test_actual_browser_bundle_admission(vectors, browser_name):
    if os.environ.get('CTM_ADMISSION_BROWSER') != 'all':
        pytest.skip('Dedicated admission CI installs the three browsers')
    from playwright.sync_api import sync_playwright
    with sync_playwright() as pw:
        options = {}
        if browser_name == 'chromium' and os.environ.get('STACK_SYMPY_CHROMIUM'):
            options['executable_path'] = os.environ['STACK_SYMPY_CHROMIUM']
        browser = getattr(pw, browser_name).launch(**options)
        try:
            page = browser.new_page()
            page.add_script_tag(content=payload(vectors)['bundle'])
            # No server, Pyodide, CAS or remote module participates in admission.
            actual = page.evaluate('(cases) => cases.map(c => CTMCheckersStack.admission.admitExpression(c.raw, c.options))',
                                   payload(vectors)['cases'])
            compare(actual, vectors, browser_name)
        finally:
            browser.close()


def test_native_s13_messages_remain_independent_expectations(vectors):
    # Frozen native PHP messages, not results inferred from the new JS code.
    for raw, feedback in NATIVE:
        options = dict(insertstars=0, questionVariables=['k', 'ta'], authorNames=['k', 'ta'])
        result = reference(raw, options)
        assert result['feedback'] == feedback
        assert (result['status'] == 'admitted') == (feedback == '')
