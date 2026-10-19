#!/usr/bin/env python3
"""Builds the wheel of ctm-checkers and its extension folder (docs/api.md).

    python tools/build.py             # writes _extensions/ctm-checkers/ from src/
    python tools/build.py --check     # the committed folder agrees with src/ (CI)
    python tools/build.py --release   # the release PR: also records the version in tools/released.json

_extensions/ctm-checkers/ is generated and committed; do not edit it:
  _extension.yml           a Quarto extension that only contributes metadata
                           (Quarto refuses one that contributes nothing);
                           authors never list it
  checkers.json            name, version, api, dependency, wheel, sha256, script
  ctm_checkers-<version>-py3-none-any.whl
  ctm-checkers.js          the wheel for the page (base64) with its own install
                           code: globalThis.CTMCheckers.install(py)

The wheel is pure Python: entries sorted, dist-info last, timestamps
1980-01-01, fixed modes, DEFLATE. Compressed bytes differ between zlib
builds, so --check compares contents (names, bytes, metadata) and requires the
other files to be exactly what the committed wheel gives; a rebuild keeps the
committed wheel while its contents are current. The sha256 of the committed
wheel identifies what runs in the browser and at build time. A released
version never changes (tools/released.json holds its contents, wheel and
script hashes; --check compares them), so its HTML dependency path is for one
content only; a development version (X.Y.Z.devN, above every release) gets the
HTML dependency version X.Y.Z.devN+<sha8 of the wheel>, so browsers fetch a
changed wheel although the version stayed.

Standard library only; runs on Python 3.9 or later.
"""
import argparse
import base64
import hashlib
import io
import json
from pathlib import Path
import re
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / 'src'
OUT = ROOT / '_extensions' / 'ctm-checkers'
SCRIPT = 'ctm-checkers.js'

SUMMARY = 'The Python checker library of CTM Assessment (grading in the browser and at build time).'
REQUIRES_PYTHON = '>=3.9'
DEPENDENCIES = ['sympy>=1.13']
EXTRAS = {'graph': ['networkx>=3.2']}
QUARTO_REQUIRED = '>=1.8.27'

# The Python that installs the wheel into a Pyodide runtime. It runs inside a
# function: the globals it uses for itself (the payload and the function,
# _ctm_ names) are deleted afterwards, so learner variables are never touched,
# and it looks up no other name in the page's namespace, where learner code
# may have rebound `open` or `RuntimeError` (builtins come from `builtins`).
# It checks the sha256, writes the wheel with Python's own file I/O (which
# works in a worker too), puts it first on sys.path (zipimport) and imports
# ctm_checkers; a copy imported before is replaced. It leaves the page two
# names, `_ctm_import` and `_ctm_globals` (builtins.__import__ and
# builtins.globals), for the page's call text: learner code may rebind
# `__import__` and `globals` in the namespace they share. The page script
# gives each install a payload variable of its own
# (_ctm_checkers_payload_<n>), so installs that overlap do not take each
# other's payload.
INSTALL = '''def _ctm_checkers_install(text):
    global _ctm_import, _ctm_globals
    import base64, builtins, hashlib, importlib, io, json, os, sys
    payload = json.loads(text)
    data = base64.b64decode(payload["data"])
    if hashlib.sha256(data).hexdigest() != payload["sha256"]:
        raise builtins.RuntimeError("ctm-checkers: the payload is damaged (sha256 mismatch)")
    folder = "/tmp/ctm-checkers/" + payload["sha256"][:16]
    path = folder + "/" + payload["wheel"]
    os.makedirs(folder, exist_ok=True)
    with io.open(path, "wb") as file:
        file.write(data)
    for name in [name for name in builtins.list(sys.modules) if name == "ctm_checkers" or name.startswith("ctm_checkers.")]:
        del sys.modules[name]
    sys.path[:] = [entry for entry in sys.path if not entry.startswith("/tmp/ctm-checkers/")]
    sys.path.insert(0, path)
    importlib.invalidate_caches()
    module = importlib.import_module("ctm_checkers")
    if module.__version__ != payload["version"]:
        raise builtins.RuntimeError("ctm-checkers: " + path + " has version " + module.__version__)
    _ctm_import, _ctm_globals = builtins.__import__, builtins.globals
try:
    _ctm_checkers_install(_ctm_checkers_payload)
finally:
    del _ctm_checkers_install, _ctm_checkers_payload'''


def package_info():
    text = (SRC / 'ctm_checkers' / '__init__.py').read_text(encoding='utf-8')
    version = re.search(r'^__version__ = "([^"]+)"$', text, re.M)
    api = re.search(r'^API = (\d+)$', text, re.M)
    if not version or not api:
        raise SystemExit('src/ctm_checkers/__init__.py must set __version__ = "..." and API = <int>')
    if not re.fullmatch(r'\d+\.\d+\.\d+(\.dev\d+|(a|b|rc)\d+)?', version[1]):
        raise SystemExit('Unsupported version ' + version[1] + ' (X.Y.Z, X.Y.Z.devN, X.Y.ZaN/bN/rcN)')
    return version[1], int(api[1])


def semver(version):
    """The version in the form Quarto's _extension.yml uses (0.2.0.dev0: 0.2.0-dev.0)."""
    match = re.fullmatch(r'(\d+\.\d+\.\d+)(?:\.(dev)(\d+)|(a|b|rc)(\d+))?', version)
    base, dev, devn, pre, pren = match.groups()
    if dev:
        return f'{base}-dev.{devn}'
    if pre:
        label = {'a': 'alpha', 'b': 'beta', 'rc': 'rc'}[pre]
        return f'{base}-{label}.{pren}'
    return base


def metadata(version):
    lines = ['Metadata-Version: 2.1', 'Name: ctm-checkers', f'Version: {version}', f'Summary: {SUMMARY}',
             'Author: CTM team', 'License: AGPL-3.0-or-later',
             'Project-URL: Source, https://github.com/Erasmus-CTM/ctm-checkers',
             'Classifier: License :: OSI Approved :: GNU Affero General Public License v3 or later (AGPLv3+)',
             'Classifier: Programming Language :: Python :: 3', f'Requires-Python: {REQUIRES_PYTHON}']
    lines += [f'Requires-Dist: {d}' for d in DEPENDENCIES]
    for extra, requirements in EXTRAS.items():
        lines.append(f'Provides-Extra: {extra}')
        lines += [f'Requires-Dist: {d}; extra == "{extra}"' for d in requirements]
    return '\n'.join(lines) + '\n\n' + 'Generated by ctm-checkers tools/build.py from src/.\n'


WHEEL = 'Wheel-Version: 1.0\nGenerator: ctm-checkers tools/build.py\nRoot-Is-Purelib: true\nTag: py3-none-any\n'


def record_hash(data):
    return 'sha256=' + base64.urlsafe_b64encode(hashlib.sha256(data).digest()).rstrip(b'=').decode('ascii')


def wheel_name(version):
    return f'ctm_checkers-{version}-py3-none-any.whl'


def wheel_contents(version):
    """{archive name: bytes} in archive order."""
    files = {}
    for path in sorted((SRC / 'ctm_checkers').rglob('*.py')):
        if '__pycache__' not in path.parts:
            files[path.relative_to(SRC).as_posix()] = path.read_bytes()
    dist = f'ctm_checkers-{version}.dist-info'
    files[f'{dist}/LICENSE'] = (ROOT / 'LICENSE').read_bytes()
    files[f'{dist}/METADATA'] = metadata(version).encode('utf-8')
    files[f'{dist}/WHEEL'] = WHEEL.encode('utf-8')
    record = ''.join(f'{name},{record_hash(data)},{len(data)}\n' for name, data in files.items()) + f'{dist}/RECORD,,\n'
    files[f'{dist}/RECORD'] = record.encode('utf-8')
    return files


def wheel_bytes(files):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, 'w') as archive:
        for name, data in files.items():
            info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.create_system = 3
            info.external_attr = 0o644 << 16
            archive.writestr(info, data, compresslevel=9)
    return buffer.getvalue()


def read_wheel(data):
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        return {name: archive.read(name) for name in archive.namelist()}


def dependency_version(version, data):
    return f'{version}+{hashlib.sha256(data).hexdigest()[:8]}' if '.dev' in version else version


def generated(version, api, data):
    """The extension folder's files for the wheel `data`: {name: bytes}."""
    sha = hashlib.sha256(data).hexdigest()
    dependency = dependency_version(version, data)
    name = wheel_name(version)
    manifest = {'name': 'ctm-checkers', 'version': version, 'api': api, 'dependency': dependency, 'wheel': name,
                'sha256': sha, 'script': SCRIPT, 'generated': 'by tools/build.py from src/; do not edit'}
    extension = '\n'.join([
        '# Generated by ctm-checkers tools/build.py from src/; do not edit.',
        '# The wheel and the page script of ctm-checkers (checkers.json); authors',
        '# never list this extension: CTM Assessment installs it, ctm-libs loads it.',
        'title: CTM checkers',
        'author: CTM team',
        f'version: {semver(version)}',
        f'quarto-required: "{QUARTO_REQUIRED}"',
        'contributes:',
        '  metadata:',
        '    ctm-checkers:',
        f'      api: {api}',
    ]) + '\n'
    install = ',\n'.join('    ' + json.dumps(line) for line in INSTALL.split('\n'))
    script = f'''/* ctm-checkers {version}: the Python checker library of CTM Assessment for the
   page (HTML dependency "ctm-checkers", version {dependency}; ctm-libs installs
   it into the page's Pyodide). Generated by ctm-checkers tools/build.py from
   src/; do not edit. AGPL-3.0-or-later; source: https://github.com/Erasmus-CTM/ctm-checkers */
(function (root) {{
  'use strict';
  // The wheel's install code (Python): checks the sha256, writes the wheel into
  // the interpreter's file system and imports ctm_checkers from it (zipimport).
  // It runs inside a function whose two globals (_ctm_ names) are deleted; it
  // sets _ctm_import and _ctm_globals for the call text (docs/api.md).
  var INSTALL = [
{install}
  ].join('\\n');
  var installs = 0;
  var checkers = {{
    name: 'ctm-checkers',
    version: {json.dumps(version)},
    api: {api},
    dependency: {json.dumps(dependency)},
    wheel: {json.dumps(name)},
    sha256: {json.dumps(sha)},
    data: '{base64.b64encode(data).decode('ascii')}',
    // Installs the wheel into the Pyodide runtime `py` with py.globals.set and
    // py.runPythonAsync only (all that pyodide-interaktiv's worker proxy
    // offers); resolves when `import ctm_checkers` works. Each call installs
    // again, with a payload variable of its own: ctm-libs keeps the
    // once-per-runtime bookkeeping.
    install: function (py) {{
      var name = '_ctm_checkers_payload_' + (++installs);
      var payload = JSON.stringify({{version: checkers.version, wheel: checkers.wheel, sha256: checkers.sha256, data: checkers.data}});
      return Promise.resolve(py.globals.set(name, payload)).then(function () {{
        return py.runPythonAsync(INSTALL.split('_ctm_checkers_payload').join(name));
      }});
    }}
  }};
  if (!root.CTMCheckers) root.CTMCheckers = checkers;
}})(typeof globalThis !== 'undefined' ? globalThis : this);
'''
    return {'_extension.yml': extension.encode('utf-8'),
            'checkers.json': (json.dumps(manifest, indent=1) + '\n').encode('utf-8'),
            name: data,
            SCRIPT: script.encode('utf-8')}


def check_pyproject():
    text = (ROOT / 'pyproject.toml').read_text(encoding='utf-8')
    problems = []
    if f'requires-python = "{REQUIRES_PYTHON}"' not in text:
        problems.append(f'pyproject.toml: requires-python must be "{REQUIRES_PYTHON}" as in the wheel')
    if 'dependencies = [' + ', '.join(json.dumps(d) for d in DEPENDENCIES) + ']' not in text:
        problems.append('pyproject.toml: dependencies must be those of the wheel: ' + ', '.join(DEPENDENCIES))
    for extra, requirements in EXTRAS.items():
        if f'{extra} = [' + ', '.join(json.dumps(d) for d in requirements) + ']' not in text:
            problems.append(f'pyproject.toml: extra {extra} must be ' + ', '.join(requirements))
    return problems


RELEASED = ROOT / 'tools' / 'released.json'
RANKS = {'dev': 0, 'a': 1, 'b': 2, 'rc': 3, None: 4}


def version_key(version):
    """Orders X.Y.Z, X.Y.Z.devN and X.Y.Z(a|b|rc)N as PEP 440 does."""
    match = re.fullmatch(r'(\d+)\.(\d+)\.(\d+)(?:\.(dev)(\d+)|(a|b|rc)(\d+))?', version)
    major, minor, patch, dev, devn, pre, pren = match.groups()
    kind = dev or pre
    return (int(major), int(minor), int(patch), RANKS[kind], int(devn or pren or 0))


def is_release(version):
    return '.dev' not in version


def released_versions():
    return json.loads(RELEASED.read_text(encoding='utf-8'))['versions'] if RELEASED.exists() else {}


def release_entry(contents, data, script):
    """What a release is: the digest of its contents (the wheel's RECORD lists
    every file with its sha256), the wheel file and the page script."""
    record = next(text for name, text in contents.items() if name.endswith('.dist-info/RECORD'))
    return {'contents': hashlib.sha256(record).hexdigest(), 'wheel': hashlib.sha256(data).hexdigest(),
            'script': hashlib.sha256(script).hexdigest()}


def release_problems(version, contents, data, script):
    """A released version never changes; a development version is above every release."""
    versions = released_versions()
    entry = release_entry(contents, data, script)
    if is_release(version):
        if version not in versions:
            return [f'{version} is a release version without an entry in tools/released.json: the release PR adds it with '
                    f'python tools/build.py --release; otherwise set a development version ({version}.dev0 or later)']
        changed = [key for key in ('contents', 'wheel', 'script') if versions[version].get(key) != entry[key]]
        if changed:
            return [f'{version} is released (tools/released.json) and its {", ".join(changed)} changed: released code never changes; '
                    f'set the next development version (for example {next_dev(version)}) in src/ctm_checkers/__init__.py']
        return []
    above = [v for v in versions if version_key(v) >= version_key(version)]
    if above:
        return [f'{version} is not above the released {", ".join(sorted(above, key=version_key))}: set a later development version']
    return []


def next_dev(version):
    major, minor, patch = (int(part) for part in re.match(r'(\d+)\.(\d+)\.(\d+)', version).groups())
    return f'{major}.{minor}.{patch + 1}.dev0'


def zip_problems(name, data):
    """The committed wheel is written as tools/build.py writes it."""
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        bad = [info.filename for info in archive.infolist()
               if info.compress_type != zipfile.ZIP_DEFLATED or info.date_time != (1980, 1, 1, 0, 0, 0)
               or info.external_attr >> 16 != 0o644]
    return [f'{name}: entries not written as tools/build.py writes them (DEFLATE, 1980-01-01, 0644): {", ".join(bad[:5])}'] if bad else []


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--check', action='store_true', help='check the committed folder instead of writing it')
    parser.add_argument('--release', action='store_true', help='also record this release version in tools/released.json')
    options = parser.parse_args(argv)
    version, api = package_info()
    contents = wheel_contents(version)
    committed = OUT / wheel_name(version)
    problems = check_pyproject()
    if options.check:
        if not committed.is_file():
            problems.append(f'{committed.relative_to(ROOT)} is missing: run python tools/build.py')
        else:
            data = committed.read_bytes()
            found = read_wheel(data)
            if list(found) != list(contents):
                problems.append(f'{committed.name}: its files are not those of src/ (run python tools/build.py)')
            for name in contents:
                if name in found and found[name] != contents[name]:
                    problems.append(f'{committed.name}: {name} differs from src/ (run python tools/build.py)')
            problems += zip_problems(committed.name, data)
            expected = generated(version, api, data)
            present = sorted(p.name for p in OUT.iterdir()) if OUT.is_dir() else []
            if present != sorted(expected):
                problems.append(f'_extensions/ctm-checkers/ must hold exactly {", ".join(sorted(expected))}; it holds {", ".join(present)}')
            for name, text in expected.items():
                path = OUT / name
                if name != committed.name and (not path.is_file() or path.read_bytes() != text):
                    problems.append(f'_extensions/ctm-checkers/{name} is not what the committed wheel gives (run python tools/build.py)')
            problems += release_problems(version, contents, data, (OUT / SCRIPT).read_bytes() if (OUT / SCRIPT).is_file() else b'')
        if not committed.is_file() and not is_release(version):
            problems += release_problems(version, contents, b'', b'')   # the order of versions needs no wheel
        for problem in problems:
            print('build --check:', problem, file=sys.stderr)
        if not problems:
            print(f'_extensions/ctm-checkers/ is current: ctm-checkers {version} (API {api}{", released" if is_release(version) else ""}), '
                  f'{committed.name} sha256 {hashlib.sha256(committed.read_bytes()).hexdigest()}')
        return 1 if problems else 0
    # Keep the committed wheel while its contents are current.
    if committed.is_file() and list(read_wheel(committed.read_bytes()).items()) == list(contents.items()):
        data = committed.read_bytes()
    else:
        data = wheel_bytes(contents)
    expected = generated(version, api, data)
    versions = released_versions()
    if options.release:
        if not is_release(version):
            problems.append(f'--release: {version} is a development version')
        elif version not in versions:
            versions[version] = release_entry(contents, data, expected[SCRIPT])
            document = json.loads(RELEASED.read_text(encoding='utf-8')) if RELEASED.exists() else {'versions': {}}
            document['versions'] = dict(sorted(versions.items(), key=lambda item: version_key(item[0])))
            RELEASED.write_text(json.dumps(document, indent=1) + '\n', encoding='utf-8')
            print(f'Recorded the release {version} in tools/released.json')
    if is_release(version) and version in versions:
        problems += release_problems(version, contents, data, expected[SCRIPT])
    elif not is_release(version):
        problems += release_problems(version, contents, data, expected[SCRIPT])
    for problem in problems:
        print('build:', problem, file=sys.stderr)
    if problems:
        return 1
    OUT.mkdir(parents=True, exist_ok=True)
    for path in OUT.iterdir():
        if path.name not in expected:
            path.unlink()
    for name, text in expected.items():
        (OUT / name).write_bytes(text)
    print(f'Wrote _extensions/ctm-checkers/ for ctm-checkers {version} (API {api}): {wheel_name(version)}, '
          f'{len(data)} bytes, sha256 {hashlib.sha256(data).hexdigest()}')
    if is_release(version) and version not in versions:
        print(f'{version} is a release version: record it with python tools/build.py --release', file=sys.stderr)
    return 0


if __name__ == '__main__':
    sys.exit(main())
