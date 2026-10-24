"""Bounded data-only contract for generated GitHub student review assets."""
import hashlib
import re
from pathlib import PurePosixPath
from urllib.parse import urlsplit
from ctm_variants.model import VariantError, digest

MAX_FILES = 4096
MAX_BYTES = 64 * 1024 * 1024
MAX_HTML_BYTES = 32 * 1024 * 1024
MAX_FILE_BYTES = 16 * 1024 * 1024
FIELDS = {'studentPreviews', 'previewFiles', 'previewSource'}
LANGUAGES = {'default', 'en', 'de', 'nb'}
SHA256 = re.compile(r'[0-9a-f]{64}\Z')
# Only browser/runtime assets belong in a published generated review tree.
EXTENSIONS = {'.html', '.js', '.css', '.json', '.map', '.wasm', '.whl', '.woff', '.woff2',
              '.ttf', '.eot', '.svg', '.png', '.jpg', '.jpeg', '.gif', '.webp', '.ico',
              '.mp3', '.ogg', '.wav'}
FORBIDDEN = {'_extensions', 'native-authoring', '_variants', '.git', '.quarto', '__pycache__'}


def relative_path(value):
    if (not isinstance(value, str) or not value or value.startswith('/') or '\\' in value
            or any(ord(char) < 32 or char in ':?#%' for char in value)
            or any(part in ('', '.', '..') for part in value.split('/'))):
        raise VariantError('preview paths must be scheme-free relative paths')
    return value


def asset_path(value, label):
    relative_path(value)
    if value == label + '.html':
        return value
    parts = value.split('/')
    if (len(parts) < 4 or parts[:2] != ['students', label] or parts[2] not in LANGUAGES
            or any(part.startswith('.') or part in FORBIDDEN for part in parts)
            or any(not re.fullmatch(r'[A-Za-z0-9_.+-]+', part) for part in parts)
            or PurePosixPath(value).suffix.lower() not in EXTENSIONS):
        raise VariantError('preview asset is outside the generated static question subtree')
    return value


def path_closure(names):
    """Every listed member is a regular file, so no file may be an ancestor."""
    folded = {name.casefold() for name in names}
    if len(folded) != len(names):
        raise VariantError('preview inventory has duplicate case-folded paths')
    for name in folded:
        parts = name.split('/')
        if any('/'.join(parts[:index]) in folded for index in range(1, len(parts))):
            raise VariantError('preview inventory file path collides with an ancestor file')


def route_path(locator, preview, label, content_hash):
    if (type(preview) is not dict or set(preview) != {'language', 'url', 'hash'}
            or not isinstance(preview['language'], str) or preview['language'] not in LANGUAGES or preview['hash'] != content_hash
            or not isinstance(preview['url'], str)):
        raise VariantError('preview route differs from current candidate hash or language')
    expected = 'students/' + label + '/' + preview['language'] + '/index.html'
    parsed = urlsplit(preview['url'])
    if (parsed.scheme or parsed.netloc or parsed.fragment or parsed.path != expected
            or parsed.query != 'ctm-review=' + digest([locator, content_hash])):
        raise VariantError('preview URL must select its exact review-only candidate')
    asset_path(expected, label)
    return expected


def validate(question):
    present = FIELDS.intersection(question)
    if not present:
        return None
    if present != FIELDS:
        raise VariantError('student preview metadata must include source, routes and file inventory')
    label = question['label']
    source, files, routes = (question[key] for key in ('previewSource', 'previewFiles', 'studentPreviews'))
    if (type(source) is not dict or set(source) != {'file', 'sha256'}
            or not isinstance(source.get('sha256'), str) or not SHA256.fullmatch(source['sha256'])):
        raise VariantError('preview source requires an exact file digest')
    relative_path(source['file'])
    if type(files) is not dict or not files or len(files) > MAX_FILES or label + '.html' not in files:
        raise VariantError('preview inventory must include its outer review page within the file budget')
    folded, total, html_total = set(), 0, 0
    for name, receipt in files.items():
        asset_path(name, label)
        if name.casefold() in folded:
            raise VariantError('preview inventory has duplicate case-folded paths')
        folded.add(name.casefold())
        if (type(receipt) is not dict or set(receipt) != {'bytes', 'sha256'}
                or type(receipt['bytes']) is not int or not 0 <= receipt['bytes'] <= MAX_FILE_BYTES
                or not isinstance(receipt['sha256'], str) or not SHA256.fullmatch(receipt['sha256'])):
            raise VariantError('invalid preview asset size or digest')
        total += receipt['bytes']
        if name.lower().endswith('.html'):
            html_total += receipt['bytes']
    path_closure(files)
    if total > MAX_BYTES or html_total > MAX_HTML_BYTES:
        raise VariantError('aggregate preview assets or HTML exceed budget')
    current = {row['id']: row for row in question['records']}
    if type(routes) is not dict or set(routes) != set(current):
        raise VariantError('preview routes must cover the exact current candidate identities')
    expected_languages = None
    for locator, previews in routes.items():
        if type(previews) is not list or not previews:
            raise VariantError('each current candidate requires named language previews')
        languages = set()
        for preview in previews:
            if (type(preview) is not dict or set(preview) != {'language', 'url', 'hash'}
                    or not isinstance(preview['language'], str) or preview['language'] not in LANGUAGES or preview['language'] in languages
                    or preview['hash'] != current[locator]['hash'] or not isinstance(preview['url'], str)):
                raise VariantError('preview route differs from current candidate hash or language')
            languages.add(preview['language'])
            expected = route_path(locator, preview, label, current[locator]['hash'])
            if expected not in files:
                raise VariantError('preview route requires an inventoried page')
        if expected_languages is not None and languages != expected_languages:
            raise VariantError('candidate preview language coverage differs')
        expected_languages = languages
    return files


def receipt(content):
    return {'bytes': len(content), 'sha256': hashlib.sha256(content).hexdigest()}


def inventory(questions):
    """Return the exact archive closure, retaining legacy HTML-only artifacts."""
    files, folded, total, html_total = {}, set(), 0, 0
    for question in questions:
        expected = validate(question)
        expected = {question['label'] + '.html': None} if expected is None else expected
        for name, item in expected.items():
            if name.casefold() in folded:
                raise VariantError('review inventory has duplicate case-folded paths')
            folded.add(name.casefold())
            files[name] = item
            if item is not None:
                total += item['bytes']
                if name.lower().endswith('.html'):
                    html_total += item['bytes']
    path_closure(files)
    if len(files) > MAX_FILES or total > MAX_BYTES or html_total > MAX_HTML_BYTES:
        raise VariantError('aggregate review asset inventory exceeds budget')
    return files
