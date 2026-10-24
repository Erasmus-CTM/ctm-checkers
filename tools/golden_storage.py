"""Plain or gzip storage for versioned expected JSONL test cases.

The logical table name never includes .gz. Registered raw hashes describe
reviewed fixture bytes; verification never asks the checker to supply them.
Only explicit recording/update writers change these hashes.
"""
import gzip
import hashlib
import io
import json
from pathlib import Path
import re

REGISTRY = 'table-storage.json'


def logical(path):
    path = Path(path)
    return path.with_suffix('') if path.name.endswith('.jsonl.gz') else path


def registry(root):
    path = Path(root) / REGISTRY
    data = json.loads(path.read_text(encoding='utf-8')) if path.exists() else {'format': 1, 'tables': {}}
    return validate_registry(data)


def validate_registry(data):
    if not isinstance(data, dict) or data.get('format') != 1 or not isinstance(data.get('tables'), dict):
        raise ValueError('Invalid golden table storage registry')
    for name, item in data['tables'].items():
        p = Path(name)
        if p.is_absolute() or '..' in p.parts or not name.endswith('.jsonl') or not isinstance(item, dict):
            raise ValueError('Invalid golden table storage entry: ' + name)
        if (not isinstance(item.get('sha256'), str) or not re.fullmatch('[0-9a-f]{64}', item['sha256'])
                or type(item.get('bytes')) is not int or item['bytes'] < 0
                or type(item.get('rows')) is not int or item['rows'] < 0):
            raise ValueError('Invalid golden table raw identity: ' + name)
    return data


def physical(root, path):
    plain = logical(path)
    packed = Path(str(plain) + '.gz')
    if plain.exists() and packed.exists():
        raise ValueError('Duplicate plain and compressed golden table: ' + str(plain))
    name = plain.relative_to(root).as_posix()
    registered = name in registry(root)['tables']
    if registered and plain.exists():
        raise ValueError('Registered compressed golden table is stored plain: ' + name)
    return packed if registered or packed.exists() else plain


def files(root):
    root = Path(root)
    found = list(root.rglob('*.jsonl')) + list(root.rglob('*.jsonl.gz'))
    tables = [p for p in found if not p.name.startswith('sources-') and 'files' not in p.relative_to(root).parts]
    names = {}
    entries = registry(root)['tables']
    for path in tables:
        name = logical(path).relative_to(root).as_posix()
        if name in names:
            raise ValueError('Duplicate golden table: ' + name)
        if path.name.endswith('.gz') and name not in entries:
            raise ValueError('Compressed golden table has no raw identity: ' + name)
        names[name] = path
    for name in entries:
        if names.get(name) != root / (name + '.gz'):
            raise ValueError('Registered compressed golden table is missing: ' + name)
    return [names[name] for name in sorted(names)]


def identity(data):
    return {'sha256': hashlib.sha256(data).hexdigest(), 'bytes': len(data), 'rows': data.count(b'\n')}


def decode(path, data, entries):
    """Decode source bytes (also Git blobs) with that revision's registry."""
    if not str(path).endswith('.jsonl.gz'):
        return data
    name = logical(path).as_posix()
    if name not in entries:
        raise ValueError('Compressed golden table has no raw identity: ' + name)
    raw = gzip.decompress(data)  # CRC/truncation errors fail; no filesystem extraction.
    if identity(raw) != entries[name]:
        raise ValueError('Compressed golden table raw identity differs: ' + name)
    return raw


def read(root, path):
    path = physical(root, path)
    return decode(path.relative_to(root), path.read_bytes(), registry(root)['tables'])


def compress(data):
    output = io.BytesIO()
    with gzip.GzipFile(fileobj=output, mode='wb', filename='', mtime=0, compresslevel=9) as stream:
        stream.write(data)
    return output.getvalue()


def write(root, path, data):
    path = physical(root, path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.name.endswith('.jsonl.gz'):
        path.write_bytes(data)
        return
    # Keep already-reviewed compressed bytes even across zlib versions.
    if path.exists() and read(root, path) == data:
        return
    meta = registry(root)
    name = logical(path).relative_to(root).as_posix()
    if name not in meta['tables']:
        raise ValueError('Recording a compressed table requires an explicit storage entry: ' + name)
    path.write_bytes(compress(data))
    meta['tables'][name] = identity(data)
    (Path(root) / REGISTRY).write_text(json.dumps(meta, indent=1, sort_keys=True) + '\n', encoding='utf-8')
