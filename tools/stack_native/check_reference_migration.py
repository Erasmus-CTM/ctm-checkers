"""Audit the STACK 4.13.1 -> 4.14.0 reference migration against Git blobs.

This is a provenance/structural audit. Fresh PHP/Maxima observations and golden
replay are separate gates; this script never substitutes recorded CAS results.
"""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
from xml.etree import ElementTree as ET

ROOT = Path(__file__).resolve().parents[2]
BEFORE = '10d323311b7f39fb7b092dd10ce75f7d8632f525'
AFTER = '33383047af39c204bf4442802a058f8b918b2b1b'
BASE = 'aae41a65ad29cf7db50e3381a6b3a8e962da2fa6'
INPUTS = ('stack/cas/security-map.json', 'stack/maximaparser/unicode/symbols-stack.json',
          'stack/maximaparser/unicode/letters-stack.json', 'tests/fixtures/answertestfixtures.class.php')


def blob(repository, revision, name):
    return subprocess.check_output(['git', '-C', str(repository), 'show', revision + ':' + name])


def structure(element):
    # Ignore indentation and only the two newly added metadata elements. All
    # question text, grading code, seeds, tests and attributes remain compared.
    return (element.tag, sorted(element.attrib.items()),
            element.text if element.text and element.text.strip() else None,
            [structure(child) for child in element if child.tag not in {'metadata', 'prescribedmetadata'}])


def audit(stack):
    sys.path.insert(0, str(ROOT / 'src'))
    from ctm_checkers.stack.importer import import_xml
    from ctm_checkers.stack.stack_data import STACK_COMMIT
    assert STACK_COMMIT == AFTER
    records = []
    for name in INPUTS:
        before, after = blob(stack, BEFORE, name), blob(stack, AFTER, name)
        assert before == after, 'Native input/fixture source changed: ' + name
        records.append({'path': name, 'sha256': hashlib.sha256(after).hexdigest(), 'identical': True})
    data_path = 'src/ctm_checkers/stack/stack_data.py'
    before_data = blob(ROOT, BASE, data_path).decode()
    assert (ROOT / data_path).read_text() == before_data.replace(BEFORE, AFTER).replace(BEFORE[:12], AFTER[:12])
    fixture_path = 'tests/stack/native_compliance/fixtures.json'
    before_fixture = json.loads(blob(ROOT, BASE, fixture_path))
    after_fixture = json.loads((ROOT / fixture_path).read_bytes())
    assert before_fixture['cases'] == after_fixture['cases']
    assert before_fixture['inventory'] == after_fixture['inventory']
    assert after_fixture['upstream']['commit'] == AFTER
    assert before_fixture['upstream']['sha256'] == after_fixture['upstream']['sha256']
    manifest = json.loads((ROOT / 'examples/stack/corpus/manifest.json').read_bytes())
    assert manifest['commit'] == AFTER and len(manifest['questions']) == 35
    corpus = []
    def model(body):
        try:
            return {'questions': import_xml(body.decode())}
        except ValueError as error:
            return {'exception': type(error).__name__, 'message': str(error)}
    for row in manifest['questions']:
        before = blob(stack, BEFORE, row['upstream_path'])
        after = blob(stack, AFTER, row['upstream_path'])
        stored = (ROOT / 'examples/stack/corpus' / row['file']).read_bytes()
        assert stored == after and hashlib.sha256(stored).hexdigest() == row['sha256'], row['file']
        assert structure(ET.fromstring(before)) == structure(ET.fromstring(after)), row['file']
        assert model(before) == model(after), 'Imported question changed: ' + row['file']
        corpus.append({'file': row['file'], 'sha256': row['sha256'], 'metadataOnly': True, 'sameImportedModel': True})
    before_baseline = json.loads(blob(ROOT, BASE, 'examples/stack/corpus/baseline.json'))
    after_baseline = json.loads((ROOT / 'examples/stack/corpus/baseline.json').read_bytes())
    for key in ('summary', 'questions', 'timeout_seconds_per_file', 'seed_policy'):
        assert before_baseline[key] == after_baseline[key], 'Corpus replay changed: ' + key
    changed_maxima = subprocess.check_output(
        ['git', '-C', str(stack), 'diff', '--name-only', BEFORE, AFTER, '--', 'stack/maxima'], text=True).splitlines()
    return {'schema': 1, 'before': BEFORE, 'after': AFTER, 'base': BASE,
            'identicalSources': records, 'fixtureRows': len(after_fixture['cases']),
            'corpus': corpus, 'sameCorpusReplay': True,
            'changedMaximaSourcesAndTests': changed_maxima, 'passed': True}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--stack-source', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    result = audit(args.stack_source)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, indent=2) + '\n')
    print('Migration audited: 4 identical sources, 2303 unchanged fixture rows, 35 metadata-only XMLs and unchanged corpus replay.')
