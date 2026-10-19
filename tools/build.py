#!/usr/bin/env python3
"""Builds the wheel of ctm-checkers and its extension folder (docs/api.md).

    python tools/build.py           # writes _extensions/ctm-checkers/ from src/
    python tools/build.py --check   # the committed folder agrees with src/ (CI)

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
wheel identifies what runs in the browser and at build time. A development
version (X.Y.Z.devN) gets the HTML dependency version X.Y.Z.devN+<sha8>, so
browsers fetch a changed wheel although the version stayed.

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
# function: the only globals it uses (the payload and the function, _ctm_
# names) are deleted afterwards, so learner variables are never touched. It
# checks the sha256, writes the wheel with Python's own file I/O (which works
# in a worker too), puts it first on sys.path (zipimport) and imports
# ctm_checkers; a copy imported before is replaced.
INSTALL = '''def _ctm_checkers_install(text):
    import base64, hashlib, importlib, json, os, sys
    payload = json.loads(text)
    data = base64.b64decode(payload["data"])
    if hashlib.sha256(data).hexdigest() != payload["sha256"]:
        raise RuntimeError("ctm-checkers: the payload is damaged (sha256 mismatch)")
    folder = "/tmp/ctm-checkers/" + payload["sha256"][:16]
    path = folder + "/" + payload["wheel"]
    os.makedirs(folder, exist_ok=True)
    with open(path, "wb") as file:
        file.write(data)
    for name in [name for name in sys.modules if name == "ctm_checkers" or name.startswith("ctm_checkers.")]:
        del sys.modules[name]
    sys.path[:] = [entry for entry in sys.path if not entry.startswith("/tmp/ctm-checkers/")]
    sys.path.insert(0, path)
    importlib.invalidate_caches()
    module = importlib.import_module("ctm_checkers")
    if module.__version__ != payload["version"]:
        raise RuntimeError("ctm-checkers: " + path + " has version " + module.__version__)
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
  // It runs inside a function whose two globals (_ctm_ names) are deleted.
  var INSTALL = [
{install}
  ].join('\\n');
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
    // again: ctm-libs keeps the once-per-runtime bookkeeping.
    install: function (py) {{
      var payload = JSON.stringify({{version: checkers.version, wheel: checkers.wheel, sha256: checkers.sha256, data: checkers.data}});
      return Promise.resolve(py.globals.set('_ctm_checkers_payload', payload)).then(function () {{
        return py.runPythonAsync(INSTALL);
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


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--check', action='store_true', help='check the committed folder instead of writing it')
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
            expected = generated(version, api, data)
            present = sorted(p.name for p in OUT.iterdir()) if OUT.is_dir() else []
            if present != sorted(expected):
                problems.append(f'_extensions/ctm-checkers/ must hold exactly {", ".join(sorted(expected))}; it holds {", ".join(present)}')
            for name, text in expected.items():
                path = OUT / name
                if name != committed.name and (not path.is_file() or path.read_bytes() != text):
                    problems.append(f'_extensions/ctm-checkers/{name} is not what the committed wheel gives (run python tools/build.py)')
        for problem in problems:
            print('build --check:', problem, file=sys.stderr)
        if not problems:
            print(f'_extensions/ctm-checkers/ is current: ctm-checkers {version} (API {api}), '
                  f'{committed.name} sha256 {hashlib.sha256(committed.read_bytes()).hexdigest()}')
        return 1 if problems else 0
    for problem in problems:
        print('build:', problem, file=sys.stderr)
    if problems:
        return 1
    # Keep the committed wheel while its contents are current.
    if committed.is_file() and read_wheel(committed.read_bytes()) == contents and list(read_wheel(committed.read_bytes())) == list(contents):
        data = committed.read_bytes()
    else:
        data = wheel_bytes(contents)
    OUT.mkdir(parents=True, exist_ok=True)
    expected = generated(version, api, data)
    for path in OUT.iterdir():
        if path.name not in expected:
            path.unlink()
    for name, text in expected.items():
        (OUT / name).write_bytes(text)
    print(f'Wrote _extensions/ctm-checkers/ for ctm-checkers {version} (API {api}): {wheel_name(version)}, '
          f'{len(data)} bytes, sha256 {hashlib.sha256(data).hexdigest()}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
