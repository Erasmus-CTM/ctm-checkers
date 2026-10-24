"""Expected-fixture storage is lossless, fail-closed and Git-diff transparent."""
import gzip
import hashlib
import io
import json
from pathlib import Path
import subprocess

import pytest

import golden
import golden_storage as storage

RAW = b'{"call":"stack.answer","id":"01","input":{},"output":{"score":1},"suite":"stack/x","tags":[]}\n'


def fixture(root, data=RAW):
    path = root / 'stack/x.jsonl.gz'
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(storage.compress(data))
    # Independent expected byte identity, never obtained from a checker run.
    expected = {'sha256': hashlib.sha256(data).hexdigest(), 'bytes': len(data), 'rows': data.count(b'\n')}
    (root / storage.REGISTRY).write_text(json.dumps({'format': 1, 'tables': {'stack/x.jsonl': expected}}))
    return path


def test_plain_and_compressed_tables_keep_logical_identity(tmp_path, monkeypatch):
    path = fixture(tmp_path)
    monkeypatch.setattr(golden, 'GOLDEN', tmp_path)
    assert golden.table_files() == [path]
    assert golden.table_name(path) == 'stack/x.jsonl'
    assert golden.suite_path('stack/x') == path
    assert golden.selected([path], [r'^stack/x\.jsonl$']) == [path]
    assert [golden.canonical(row) for row in golden.read_rows(path)] == [RAW.decode().strip()]
    assert storage.read(tmp_path, path.with_suffix('')) == RAW
    other = tmp_path / 'math_exercise/y.jsonl'
    other.parent.mkdir()
    other.write_bytes(RAW)
    assert storage.read(tmp_path, other) == RAW


@pytest.mark.parametrize('damage', ['truncated', 'crc', 'different-raw', 'missing-hash', 'wrong-count'])
def test_damaged_or_unbound_expected_fixture_fails_closed(tmp_path, damage):
    path = fixture(tmp_path)
    if damage == 'truncated':
        path.write_bytes(path.read_bytes()[:-3])
    elif damage == 'crc':
        data = bytearray(path.read_bytes()); data[-8] ^= 1; path.write_bytes(data)
    elif damage == 'different-raw':
        path.write_bytes(storage.compress(RAW.replace(b'"score":1', b'"score":0')))
    elif damage == 'missing-hash':
        (tmp_path / storage.REGISTRY).unlink()
    else:
        meta = json.loads((tmp_path / storage.REGISTRY).read_text())
        meta['tables']['stack/x.jsonl']['rows'] = 2
        (tmp_path / storage.REGISTRY).write_text(json.dumps(meta))
    with pytest.raises((ValueError, OSError, EOFError)):
        storage.read(tmp_path, path)


def test_duplicate_and_missing_tables_cannot_reduce_or_double_the_corpus(tmp_path):
    path = fixture(tmp_path)
    plain = path.with_suffix('')
    plain.write_bytes(RAW)
    with pytest.raises(ValueError, match='Duplicate'):
        storage.files(tmp_path)
    with pytest.raises(ValueError, match='Duplicate'):
        storage.physical(tmp_path, path)
    plain.unlink(); path.unlink()
    with pytest.raises(ValueError, match='missing'):
        storage.files(tmp_path)


def test_unregistered_compressed_table_is_not_silently_discovered(tmp_path):
    path = fixture(tmp_path)
    (tmp_path / storage.REGISTRY).unlink()
    with pytest.raises(ValueError, match='no raw identity'):
        storage.files(tmp_path)


@pytest.mark.parametrize('meta', [
    {'format': 2, 'tables': {}},
    {'format': 1, 'tables': {'../outside.jsonl': {}}},
    {'format': 1, 'tables': {'stack/x.jsonl': {'sha256': '0'*64, 'bytes': True, 'rows': 1}}},
])
def test_registry_schema_and_relative_table_paths_are_strict(tmp_path, meta):
    (tmp_path / storage.REGISTRY).write_text(json.dumps(meta))
    with pytest.raises(ValueError, match='Invalid golden table'):
        storage.registry(tmp_path)


def test_recording_is_deterministic_and_unchanged_raw_does_not_recompress(tmp_path):
    path = fixture(tmp_path)
    alternative = io.BytesIO()
    with gzip.GzipFile(fileobj=alternative, mode='wb', filename='', mtime=0, compresslevel=1) as stream:
        stream.write(RAW)
    path.write_bytes(alternative.getvalue())
    before = path.read_bytes()
    storage.write(tmp_path, path, RAW)
    assert path.read_bytes() == before
    changed = RAW.replace(b'"score":1', b'"score":0')
    storage.write(tmp_path, path.with_suffix(''), changed)
    packed = path.read_bytes()
    assert packed == storage.compress(changed) == storage.compress(changed)
    assert packed[:10] == bytes.fromhex('1f8b08000000000002ff')
    assert gzip.decompress(packed) == storage.read(tmp_path, path) == changed
    assert not path.with_suffix('').exists()
    meta = json.loads((tmp_path / storage.REGISTRY).read_text())['tables']['stack/x.jsonl']
    assert meta == {'sha256': hashlib.sha256(changed).hexdigest(), 'bytes': len(changed), 'rows': 1}


def test_canonical_rows_and_order_remain_enforced_after_decompression(tmp_path, monkeypatch):
    monkeypatch.setattr(golden, 'GOLDEN', tmp_path)
    path = fixture(tmp_path, RAW.replace(b'"score":1', b'"score": 1'))
    with pytest.raises(SystemExit, match='not canonical'):
        golden.read_rows(path)
    path = fixture(tmp_path, RAW + RAW)
    with pytest.raises(SystemExit, match='each id once'):
        golden.read_rows(path)


def test_git_plain_to_gzip_change_is_not_a_golden_result_change(tmp_path, monkeypatch):
    def git(*args):
        return subprocess.check_output(['git', '-C', str(tmp_path), *args], text=True).strip()
    root = tmp_path / 'tests/golden'
    root.mkdir(parents=True)
    plain = root / 'stack/x.jsonl'; plain.parent.mkdir(); plain.write_bytes(RAW)
    git('init', '-q'); git('add', '.')
    git('-c', 'user.name=t', '-c', 'user.email=t@example.org', 'commit', '-qm', 'plain fixture')
    monkeypatch.setattr(golden, 'ROOT', tmp_path)
    monkeypatch.setattr(golden, 'GOLDEN', root)
    path = fixture(root); plain.unlink()
    assert golden.golden_diff('HEAD') == {}
    git('add', '.'); git('-c', 'user.name=t', '-c', 'user.email=t@example.org', 'commit', '-qm', 'compressed fixture')
    assert golden.git_tables('HEAD') == {'stack/x.jsonl': [golden.loads(RAW.decode())]}
    assert golden.golden_diff('HEAD') == {}
    changed = RAW.replace(b'"score":1', b'"score":0')
    storage.write(root, path, changed)
    report = golden.golden_diff('HEAD')
    assert list(report) == ['stack/x.jsonl']
    added, removed, different = report['stack/x.jsonl']
    assert added == removed == [] and len(different) == 1
    assert golden.canonical(different[0][0]['output']) == '{"score":1}'
    assert golden.canonical(different[0][1]['output']) == '{"score":0}'
