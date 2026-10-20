"""The golden tables themselves: format, provenance, completeness (docs/goldens.md)."""
import hashlib
import json
import os
from pathlib import Path

import pytest

import golden
import golden_stack

PYTHONS_TESTED = ['3.9', '3.10', '3.11', '3.12', '3.13']   # every Python from the floor; Pyodide 0.27.2 is 3.12, 0.28.3 3.13


def tables():
    return {path.relative_to(golden.GOLDEN).as_posix(): golden.read_rows(path) for path in golden.table_files()}


def test_rows_are_canonical_sorted_and_complete():
    sources = golden.read_sources()
    for name, rows in tables().items():
        assert rows, name
        for row in rows:
            keys = set(row) - {'native'} if name.startswith('stack/') else set(row)
            assert keys in ({'suite', 'id', 'call', 'input', 'output', 'tags'}, {'suite', 'id', 'call', 'input', 'by_python', 'tags'}), (name, row['id'])
            assert name == row['suite'] + '.jsonl', (name, row['id'])
            if 'by_python' in row:
                # Every Python version CI runs has its result.
                assert set(PYTHONS_TESTED) <= set(row['by_python']), (name, row['id'], sorted(row['by_python']))
            for value in json.dumps(row['input']).split('"$source": "')[1:]:
                assert value[:64] in sources, (name, row['id'])


def test_recorded_rows_have_their_ids():
    for name, rows in tables().items():
        if (name.startswith('stack/') or name.startswith('math_exercise/')
                and name.split('/')[1].rsplit('.', 1)[0] in ('namespace', 'rounding', 'rounding-variants', 'requests-supplement')):
            for row in rows:
                assert row['id'] == golden.row_id(row['call'], row['input'])


def test_only_math_exercise_examples_are_committed():
    # Step-2 design §13 item 7: rows derived from courses or the umbrella's
    # example site stay in the umbrella.
    manifest = golden.read_manifest()
    assert manifest['capture']['corpus']['repository'] == 'Erasmus-CTM/math-exercise'
    assert manifest['capture']['corpus']['export'] is True
    for path in golden.GOLDEN.rglob('*.jsonl'):
        name = path.name
        if path.parent.name == 'stack':
            assert 'stack/' + path.stem in golden_stack.TABLES, name
            continue
        if name.endswith('-math-exercise.jsonl'):
            continue
        assert name in ('namespace.jsonl', 'rounding.jsonl', 'rounding-variants.jsonl', 'requests-supplement.jsonl'), name
    for info in manifest['capture']['files'].values():
        assert info['corpus'] == 'math-exercise' and info['export'] is True


def test_manifest_and_provenance_match_the_tables():
    manifest = golden.read_manifest()
    for name, info in manifest['capture']['files'].items():
        lines = (golden.GOLDEN / name).read_text(encoding='utf-8').splitlines()
        assert len(lines) == info['rows'], name
    for suite, info in manifest['recorded'].items():
        assert len(golden.read_rows(golden.suite_path(suite))) == info['rows'], suite
        assert set(PYTHONS_TESTED) <= set(info['python']), suite
    for name in manifest['files']:
        assert (golden.GOLDEN / 'math_exercise' / 'files' / name).is_file(), name
    before = (golden.GOLDEN / 'PROVENANCE.md').read_text(encoding='utf-8')
    try:
        golden.write_provenance()
        assert (golden.GOLDEN / 'PROVENANCE.md').read_text(encoding='utf-8') == before, 'PROVENANCE.md is not up to date'
    finally:
        (golden.GOLDEN / 'PROVENANCE.md').write_text(before, encoding='utf-8')


def test_sources_are_stored_by_their_hash():
    for sha, text in golden.read_sources().items():
        assert hashlib.sha256(text.encode('utf-8')).hexdigest() == sha


def test_canonical_json_matches_the_capture():
    # Numbers keep their spelling, keys sort by UTF-16 code units, non-ASCII stays.
    text = '{"a":[1.0,1e-05,-0.0,100000000000000000000],"b":"é\\n\\u0001","\\ud83d\\ude00":1,"\\uffff":2}'
    value = golden.loads(text)
    assert golden.canonical(value) == '{"a":[1.0,1e-05,-0.0,100000000000000000000],"b":"é\\n\\u0001","😀":1,"￿":2}'
    assert golden.output_of('{"score": NaN}') == {'$unparsed': '{"score": NaN}'}
    assert golden.canonical(float('nan')) == '{"$float":"NaN"}'


def test_page_values_are_converted_as_pyodide_converts_numbers():
    assert golden.page_value(golden.Raw('1'), {}) == 1 and isinstance(golden.page_value(golden.Raw('1'), {}), int)
    assert isinstance(golden.page_value(golden.Raw('0.5'), {}), float)
    assert isinstance(golden.page_value(golden.Raw('1e+21'), {}), float)
    assert golden.page_value({'$float': 'NaN'}, {}) != golden.page_value({'$float': 'NaN'}, {})


def test_messages_are_kept_per_version():
    assert golden.has_message({'status': 'error', 'message': 'invalid syntax'})
    assert golden.has_message({'raised': 'ValueError: x'})
    assert golden.has_message({'outcome': 'assertion failed: x', 'calls': []})
    assert not golden.has_message({'outcome': 'pass', 'calls': [{'score': 1}]})
    assert golden.has_message({'outcome': 'pass', 'calls': [{'message': 'm'}]})


def test_authored_rows_need_the_pinned_umbrella_recorder(tmp_path, monkeypatch):
    # golden.py records authored rows with the umbrella's authored_record.py
    # (the one copy), and only with the file of the pinned commit.
    monkeypatch.setenv('CTM_UMBRELLA', str(tmp_path))
    monkeypatch.setattr(golden, '_recorder', None)
    with pytest.raises(SystemExit, match='not found'):
        golden.recorder()
    other = tmp_path / golden.RECORDER
    other.parent.mkdir(parents=True)
    other.write_text('def record(run_question, options, base):\n    return {}\n')
    with pytest.raises(SystemExit, match='is not the recorder of ctm-assessment'):
        golden.recorder()


@pytest.mark.skipif(not (golden.umbrella_folder() / golden.RECORDER).is_file(),
                    reason='needs ctm-assessment at the commit in tools/pins.json in _ci/ctm-assessment')
def test_the_pinned_recorder_records_check_calls(tmp_path, monkeypatch):
    monkeypatch.setattr(golden, '_recorder', None)

    def run_question(options, base):   # a question whose test fails on its second check() call
        scope = {}
        exec(options['checker'], scope)
        scope['check']({'raw': ['2/4']})
        if scope['check']({'raw': ['x']})['score'] != 1:
            raise AssertionError('second call')

    checker = 'def check(response):\n    return {"score": 0.5 if response["raw"] == ["2/4"] else 0.25}\n'
    result = golden.authored_output(run_question, {'checker': checker}, str(tmp_path))
    assert golden.canonical(result) == (
        '{"calls":[{"score":0.5},{"score":0.25}],"outcome":"assertion failed: second call",'
        '"responses":[{"inputs":{},"kind":"expressions","raw":["2/4"]},{"inputs":{},"kind":"expressions","raw":["x"]}]}')


@pytest.mark.skipif(not (golden.umbrella_folder() / golden.RECORDER).is_file(),
                    reason='needs ctm-assessment at the commit in tools/pins.json in _ci/ctm-assessment')
def test_a_relative_umbrella_folder_is_relative_to_where_golden_py_runs(tmp_path, monkeypatch):
    # Review round 2: authored rows run in their question's folder; CTM_UMBRELLA=<relative> still finds the recorder.
    umbrella = golden.umbrella_folder()
    monkeypatch.chdir(umbrella.parent)
    monkeypatch.setenv('CTM_UMBRELLA', umbrella.name)
    monkeypatch.setattr(golden, '_recorder', None)
    questions = tmp_path / 'questions'
    questions.mkdir()

    def run_question(options, base):
        scope = {}
        exec(options['checker'], scope)
        scope['check']({'raw': ['1']})

    result = golden.authored_output(run_question, {'checker': 'def check(response):\n    return True\n'}, str(questions))
    assert golden.canonical(result) == '{"calls":[true],"outcome":"pass","responses":[{"inputs":{},"kind":"expressions","raw":["1"]}]}'
    # main() makes it absolute before anything changes the folder, also for record's subprocesses.
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv('CTM_UMBRELLA', 'umbrella-checkout')
    golden.use_umbrella()
    assert os.environ['CTM_UMBRELLA'] == str((tmp_path / 'umbrella-checkout').resolve())
    golden.use_umbrella('other')   # --umbrella wins
    assert os.environ['CTM_UMBRELLA'] == str((tmp_path / 'other').resolve())


def stack_files(value):
    return [value[key] for key in ('file', 'python_checkers') if key in value]


def test_stack_rows_name_files_here_and_course_material_only_in_its_table():
    # AC (20 Oct 2026): the questions derived from course material have a table of their own,
    # labelled as course material under CC BY-SA 4.0; no other table holds a row of them (and
    # no math_exercise table holds course rows at all: design §13 item 7, test above).
    source, licence = golden_stack.TABLES['stack/questions-course']
    assert source.startswith('course material') and licence.startswith('the questions CC-BY-SA-4.0 (course material')
    # Its rows also name, and two of them hold the source of, AGPL checker files; the generated answers are AGPL too.
    assert licence.endswith(' and the answers AGPL-3.0-or-later')
    checkers = {row['input']['python_checkers'] for row in tables()['stack/questions-course.jsonl'] if 'python_checkers' in row['input']}
    assert checkers and all(path in licence for path in checkers), checkers
    assert sorted(golden_stack.COURSE_DERIVED) == sorted(
        'examples/stack/' + q['file'] for q in json.loads((golden.ROOT / 'examples/stack/course-examples-provenance.json').read_text())['questions'])
    # AC (20 Oct 2026): the HELM samples stay, labelled as CC BY-NC 4.0 test data (the code is AGPL).
    source, licence = golden_stack.TABLES['stack/questions-helm']
    assert 'test data only' in source and licence.startswith('CC-BY-NC-4.0 (NonCommercial; test data only')
    assert all(golden_stack.question_table(path) == 'stack/questions-helm' for path in golden_stack.HELM)
    course = set()
    excluded = json.loads((golden.GOLDEN / 'stack' / 'excluded.json').read_text(encoding='utf-8'))
    listed = {(entry['suite'], entry['id']) for entry in excluded}
    for name, rows in tables().items():
        if not name.startswith('stack/'):
            continue
        for row in rows:
            assert row['call'] in golden_stack.CALLS, (name, row['id'])
            assert (row['suite'], row['id']) not in listed, (name, row['id'])
            for path in stack_files(row['input']):
                assert (golden.ROOT / path).is_file() and path.startswith('examples/stack/'), (name, row['id'], path)
                assert golden_stack.question_table(row['input']['file']) == row['suite'], (name, row['id'])
            file = row['input'].get('file')
            assert (file in golden_stack.COURSE_DERIVED) == (row['suite'] == 'stack/questions-course'), (name, row['id'], file)
            assert row['input'].get('python_checkers') not in golden_stack.COURSE_DERIVED, (name, row['id'])
            if row['suite'] == 'stack/questions-course':
                course.add((file, row['call']))
    # Every course question has its import, card, variants, question tests and answers.
    calls = ('stack.import', 'stack.card', 'stack.instantiate', 'stack.tests', 'stack.answer')
    assert course == {(path, call) for path in golden_stack.COURSE_DERIVED for call in calls}
    for entry in excluded:
        assert entry['id'] == golden.row_id(entry['call'], golden.loads(json.dumps(entry['input']))) and entry['reason']


LEGACY_STACK = os.environ.get('CTM_LEGACY_STACK_SYMPY')


@pytest.mark.skipif(not LEGACY_STACK, reason='needs CTM_LEGACY_STACK_SYMPY (stack-sympy at the commit in tools/pins.json)')
def test_stack_inputs_are_stack_sympys():
    # examples/stack/ is stack-sympy's questions/ (the STACK question XML has one home here now) and
    # tests/stack/ holds its fixtures, byte for byte; the changes: the example checker file
    # imports assess_basis from ctm_checkers.matrix, its one home (stack-sympy: stack_sympy.basis_helper),
    # the corpus baseline names the engine it was recorded with (its results are the same), and
    # the READMEs name the paths here.
    legacy = Path(LEGACY_STACK).resolve()
    pairs = [(legacy / 'questions', golden.ROOT / 'examples' / 'stack'),
             (legacy / 'tests' / 'native_compliance', golden.ROOT / 'tests' / 'stack' / 'native_compliance'),
             (legacy / 'tests' / 'port_regressions', golden.ROOT / 'tests' / 'stack' / 'port_regressions')]
    for old, new in pairs:
        for path in sorted(p for p in old.rglob('*') if p.is_file()):
            relative = path.relative_to(old)
            if relative.name == 'README.md':
                continue
            here = (new / relative).read_bytes()
            if relative.as_posix() == 'matrix-checkers.py':
                here = here.replace(b'from ctm_checkers.matrix import assess_basis', b'from stack_sympy.basis_helper import assess_basis')
            if relative.as_posix() == 'corpus/baseline.json':
                engine = ('engine_revision', 'adapter_source_sha256', 'python_version')
                here, there = (json.loads(data) for data in (here, path.read_bytes()))
                assert {k: v for k, v in here.items() if k not in engine} == {k: v for k, v in there.items() if k not in engine}
                continue
            assert here == path.read_bytes(), relative
    assert (golden.ROOT / 'tests' / 'stack' / 'reference_cases.json').read_bytes() == (legacy / 'tests' / 'reference_cases.json').read_bytes()
