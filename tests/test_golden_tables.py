"""The golden tables themselves: format, provenance, completeness (docs/goldens.md)."""
import hashlib
import json

import golden

PYTHONS_TESTED = ['3.9', '3.12', '3.13']   # CI: native 3.9, 3.12, 3.13; Pyodide 0.27.2 (3.12), 0.28.3 (3.13)


def tables():
    return {path.relative_to(golden.GOLDEN).as_posix(): golden.read_rows(path) for path in golden.table_files()}


def test_rows_are_canonical_sorted_and_complete():
    sources = golden.read_sources()
    for name, rows in tables().items():
        assert rows, name
        for row in rows:
            assert set(row) in ({'suite', 'id', 'call', 'input', 'output', 'tags'}, {'suite', 'id', 'call', 'input', 'by_python', 'tags'}), (name, row['id'])
            assert name == row['suite'] + '.jsonl', (name, row['id'])
            if 'by_python' in row:
                # Every Python version CI runs has its result.
                assert set(PYTHONS_TESTED) <= set(row['by_python']), (name, row['id'], sorted(row['by_python']))
            for value in json.dumps(row['input']).split('"$source": "')[1:]:
                assert value[:64] in sources, (name, row['id'])


def test_recorded_rows_have_their_ids():
    for name, rows in tables().items():
        if name.startswith('math_exercise/') and name.split('/')[1].rsplit('.', 1)[0] in ('namespace', 'rounding', 'requests-supplement'):
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
        if name.endswith('-math-exercise.jsonl'):
            continue
        assert name in ('namespace.jsonl', 'rounding.jsonl', 'requests-supplement.jsonl'), name
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
