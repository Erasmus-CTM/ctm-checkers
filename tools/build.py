#!/usr/bin/env python3
"""Builds the wheels of ctm-checkers and its extension folder (docs/api.md).

    python tools/build.py             # writes _extensions/ctm-checkers/ from src/
    python tools/build.py --check     # the committed folder agrees with src/ (CI)
    python tools/build.py --release   # the release PR: also records the version in tools/released.json
    python tools/build.py --check --released-base REF
                                      # and the releases recorded at the Git commit REF (the base
                                      # branch) are still recorded here, unchanged (CI)

Two wheels, one page script each, so that a page with math-exercise never
carries the STACK engine (design §13 item 5):

  ctm_checkers-<version>-py3-none-any.whl          everything but ctm_checkers/stack/:
  ctm-checkers.js                                  the shared modules and math-exercise's checks
  ctm_checkers_stack-<version>-py3-none-any.whl    ctm_checkers/stack/, the STACK engine
  ctm-checkers-stack.js                            (needs the first; pip: ctm-checkers-stack)

_extensions/ctm-checkers/ is generated and committed; do not edit it:
  _extension.yml           a Quarto extension that only contributes metadata
                           (Quarto refuses one that contributes nothing);
                           authors never list it
  checkers.json            name, version, api, dependency, wheel, sha256, script
                           (the first wheel), parts.stack (the same for the second)
  the two wheels
  ctm-checkers.js          each wheel for the page (base64) with its own install
  ctm-checkers-stack.js    code: globalThis.CTMCheckers.install(py),
                           globalThis.CTMCheckersStack.install(py) (both wheels)

A wheel is pure Python: entries sorted, dist-info last, timestamps
1980-01-01, fixed modes, DEFLATE. Compressed bytes differ between zlib
builds, so --check compares contents (names, bytes, metadata) and requires the
other files to be exactly what the committed wheels give; a rebuild keeps a
committed wheel while its contents are current. The sha256 of a committed
wheel identifies what runs in the browser and at build time. A released
version never changes (tools/released.json holds its contents, wheel and
script hashes; --check compares them), so its HTML dependency paths are for one
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
import subprocess
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / 'src'
OUT = ROOT / '_extensions' / 'ctm-checkers'
SCRIPT = 'ctm-checkers.js'

SUMMARY = 'The Python checker library of CTM Assessment (grading in the browser and at build time).'
# The two wheels: part name -> (distribution, import-name prefix of the wheel file, page script, page global, summary).
PARTS = {
    'base': ('ctm-checkers', 'ctm_checkers', SCRIPT, 'CTMCheckers', SUMMARY),
    'stack': ('ctm-checkers-stack', 'ctm_checkers_stack', 'ctm-checkers-stack.js', 'CTMCheckersStack',
              'The STACK engine of ctm-checkers (ctm_checkers.stack), the checker library of CTM Assessment.'),
}
REQUIRES_PYTHON = '>=3.9'
# The STACK wheel carries STACK's data (ctm_checkers/stack/stack_data.py), which is GPL-3.0-or-later and
# combined with our AGPL-3.0-or-later code under section 13 of both licences: the wheel's licence is both, and
# the text of the GPL is in the wheel (dist-info/licenses/GPL-3.0-STACK.txt; one copy in the repository, the
# licence file of STACK's answer-test fixtures).
STACK_LICENCE = 'AGPL-3.0-or-later AND GPL-3.0-or-later'
GPL_TEXT = ROOT / 'tests' / 'stack' / 'native_compliance' / 'COPYING.txt'
GPL_NAME = 'GPL-3.0-STACK.txt'
DEPENDENCIES = ['sympy>=1.13']
EXTRAS = {'graph': ['networkx>=3.2']}
QUARTO_REQUIRED = '>=1.8.27'

# The Python that installs the wheel into a Pyodide runtime. It runs inside a
# function: the globals it uses for itself (the payload and the function,
# _ctm_ names) are deleted afterwards, so it leaves no name in the page's
# namespace and learner variables are never touched, and it looks up no other
# name there, where learner code may have rebound `open` or `RuntimeError`
# (builtins come from `builtins`). It checks the sha256, writes the wheel with
# Python's own file I/O (which works in a worker too), puts it first on
# sys.path (zipimport) and imports ctm_checkers; a copy imported before is
# replaced. The page script gives each install a payload variable of its own
# (_ctm_checkers_payload_<n>), so installs that overlap do not take each
# other's payload. The call text is the caller's (ctm-libs'; docs/api.md).
INSTALL = '''def _ctm_checkers_install(text):
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
try:
    _ctm_checkers_install(_ctm_checkers_payload)
finally:
    del _ctm_checkers_install, _ctm_checkers_payload'''

# The Python that adds a part's wheel (ctm_checkers.stack) to the ctm_checkers
# that INSTALL has just installed, with the same rules (a function, _ctm_
# names deleted, no lookup in the page's namespace). It checks the sha256 and
# the version, writes the wheel, puts it on sys.path after the first and
# extends the package's __path__ with its portion, as ctm_checkers/__init__.py
# does when both wheels are on sys.path at build time.
INSTALL_PART = '''def _ctm_checkers_install_part(text):
    import base64, builtins, hashlib, importlib, io, json, os, pkgutil, sys
    payload = json.loads(text)
    data = base64.b64decode(payload["data"])
    if hashlib.sha256(data).hexdigest() != payload["sha256"]:
        raise builtins.RuntimeError("ctm-checkers: the payload of " + payload["name"] + " is damaged (sha256 mismatch)")
    package = sys.modules.get("ctm_checkers")
    if package is None or package.__version__ != payload["version"]:
        raise builtins.RuntimeError("ctm-checkers: " + payload["name"] + " " + payload["version"] + " needs ctm-checkers "
                                    + payload["version"] + " installed first")
    folder = "/tmp/ctm-checkers/" + payload["sha256"][:16]
    path = folder + "/" + payload["wheel"]
    os.makedirs(folder, exist_ok=True)
    with io.open(path, "wb") as file:
        file.write(data)
    prefix = "ctm_checkers." + payload["part"]
    for name in [name for name in builtins.list(sys.modules) if name == prefix or name.startswith(prefix + ".")]:
        del sys.modules[name]
    if path not in sys.path:
        sys.path.append(path)
    importlib.invalidate_caches()
    package.__path__ = pkgutil.extend_path(package.__path__, "ctm_checkers")
    importlib.import_module(prefix)
try:
    _ctm_checkers_install_part(_ctm_checkers_part_payload)
finally:
    del _ctm_checkers_install_part, _ctm_checkers_part_payload'''


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


def metadata(version, part='base'):
    distribution, _, _, _, summary = PARTS[part]
    lines = ['Metadata-Version: 2.1', f'Name: {distribution}', f'Version: {version}', f'Summary: {summary}',
             'Author: CTM team', f'License: {STACK_LICENCE if part == "stack" else "AGPL-3.0-or-later"}',
             'Project-URL: Source, https://github.com/Erasmus-CTM/ctm-checkers',
             'Classifier: License :: OSI Approved :: GNU Affero General Public License v3 or later (AGPLv3+)']
    if part == 'stack':
        lines.append('Classifier: License :: OSI Approved :: GNU General Public License v3 or later (GPLv3+)')
    lines += ['Classifier: Programming Language :: Python :: 3', f'Requires-Python: {REQUIRES_PYTHON}']
    if part != 'base':
        lines.append(f'Requires-Dist: ctm-checkers=={version}')
    lines += [f'Requires-Dist: {d}' for d in DEPENDENCIES]
    if part == 'base':
        for extra, requirements in EXTRAS.items():
            lines.append(f'Provides-Extra: {extra}')
            lines += [f'Requires-Dist: {d}; extra == "{extra}"' for d in requirements]
    return '\n'.join(lines) + '\n\n' + 'Generated by ctm-checkers tools/build.py from src/.\n'


WHEEL = 'Wheel-Version: 1.0\nGenerator: ctm-checkers tools/build.py\nRoot-Is-Purelib: true\nTag: py3-none-any\n'


def record_hash(data):
    return 'sha256=' + base64.urlsafe_b64encode(hashlib.sha256(data).digest()).rstrip(b'=').decode('ascii')


def wheel_name(version, part='base'):
    return f'{PARTS[part][1]}-{version}-py3-none-any.whl'


def in_part(name, part):
    """Whether the package file `name` (ctm_checkers/...) belongs to the wheel of `part`."""
    stack = name.startswith('ctm_checkers/stack/')
    return stack if part == 'stack' else not stack


def wheel_contents(version, part='base'):
    """{archive name: bytes} in archive order. The STACK wheel starts with the
    directory entry ctm_checkers/: zipimport sees a package's portion in a
    wheel only through it (pkgutil.extend_path in ctm_checkers/__init__.py);
    RECORD lists files only."""
    files = {} if part == 'base' else {'ctm_checkers/': b''}
    for path in sorted((SRC / 'ctm_checkers').rglob('*.py')):
        name = path.relative_to(SRC).as_posix()
        if '__pycache__' not in path.parts and in_part(name, part):
            files[name] = path.read_bytes()
    dist = f'{PARTS[part][1]}-{version}.dist-info'
    files[f'{dist}/LICENSE'] = (ROOT / 'LICENSE').read_bytes()
    if part == 'stack':
        files[f'{dist}/licenses/{GPL_NAME}'] = GPL_TEXT.read_bytes()
    files[f'{dist}/METADATA'] = metadata(version, part).encode('utf-8')
    files[f'{dist}/WHEEL'] = WHEEL.encode('utf-8')
    record = ''.join(f'{name},{record_hash(data)},{len(data)}\n' for name, data in files.items()
                     if not name.endswith('/')) + f'{dist}/RECORD,,\n'
    files[f'{dist}/RECORD'] = record.encode('utf-8')
    return files


def wheel_bytes(files):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, 'w') as archive:
        for name, data in files.items():
            info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.create_system = 3
            info.external_attr = (0o40755 << 16) | 0x10 if name.endswith('/') else 0o644 << 16
            archive.writestr(info, data, compresslevel=9)
    return buffer.getvalue()


def read_wheel(data):
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        return {name: archive.read(name) for name in archive.namelist()}


def dependency_version(version, data):
    return f'{version}+{hashlib.sha256(data).hexdigest()[:8]}' if '.dev' in version else version


def _script_url():
    # The script's own URL (for a worker that loads it with importScripts); null where it has none.
    return "(typeof document !== 'undefined' && document.currentScript && document.currentScript.src) || null"


def base_script(version, api, data):
    sha = hashlib.sha256(data).hexdigest()
    dependency = dependency_version(version, data)
    install = ',\n'.join('    ' + json.dumps(line) for line in INSTALL.split('\n'))
    return f'''/* ctm-checkers {version}: the Python checker library of CTM Assessment for the
   page (HTML dependency "ctm-checkers", version {dependency}; ctm-libs installs
   it into the page's Pyodide). Generated by ctm-checkers tools/build.py from
   src/; do not edit. AGPL-3.0-or-later; source: https://github.com/Erasmus-CTM/ctm-checkers */
(function (root) {{
  'use strict';
  // The wheel's install code (Python): checks the sha256, writes the wheel into
  // the interpreter's file system and imports ctm_checkers from it (zipimport).
  // It runs inside a function whose two globals (_ctm_ names) are deleted, so
  // it leaves no name in the page's namespace (docs/api.md).
  var INSTALL = [
{install}
  ].join('\\n');
  var installs = 0;
  var checkers = {{
    name: 'ctm-checkers',
    version: {json.dumps(version)},
    api: {api},
    dependency: {json.dumps(dependency)},
    wheel: {json.dumps(wheel_name(version))},
    sha256: {json.dumps(sha)},
    data: '{base64.b64encode(data).decode('ascii')}',
    scriptURL: {_script_url()},
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


def part_script(version, api, data, part):
    distribution, _, _, name, _ = PARTS[part]
    sha = hashlib.sha256(data).hexdigest()
    dependency = dependency_version(version, data)
    install = ',\n'.join('    ' + json.dumps(line) for line in INSTALL_PART.split('\n'))
    return f'''/* {distribution} {version}: the STACK engine of ctm-checkers (ctm_checkers.{part}) for
   the page (HTML dependency "{distribution}", version {dependency}), after
   ctm-checkers.js of the same version. Generated by ctm-checkers tools/build.py
   from src/; do not edit. AGPL-3.0-or-later; source: https://github.com/Erasmus-CTM/ctm-checkers
   The wheel in this script also holds ctm_checkers/stack/stack_data.py, data of
   STACK (https://github.com/maths/moodle-qtype_stack; copyright the University
   of Edinburgh, Aalto University and STACK's other contributors), licensed
   GPL-3.0-or-later and combined with this AGPL-3.0-or-later code under section
   13 of both licences: the wheel's licence is AGPL-3.0-or-later AND
   GPL-3.0-or-later, and the GPL's text is in the wheel (dist-info/licenses). */
(function (root) {{
  'use strict';
  // The wheel's install code (Python): checks the sha256 and the version of
  // the ctm_checkers installed before, writes the wheel and adds
  // ctm_checkers.{part} from it (zipimport). It runs inside a function whose
  // two globals (_ctm_ names) are deleted, so it leaves no name in the page's
  // namespace (docs/api.md).
  var INSTALL = [
{install}
  ].join('\\n');
  var installs = 0;
  var checkers = {{
    name: {json.dumps(distribution)},
    part: {json.dumps(part)},
    version: {json.dumps(version)},
    api: {api},
    dependency: {json.dumps(dependency)},
    wheel: {json.dumps(wheel_name(version, part))},
    sha256: {json.dumps(sha)},
    data: '{base64.b64encode(data).decode('ascii')}',
    scriptURL: {_script_url()},
    // Installs ctm-checkers (ctm-checkers.js, which must be on the page, at
    // this version) and then this wheel into the Pyodide runtime `py`, with
    // py.globals.set and py.runPythonAsync only; resolves when
    // `import ctm_checkers.{part}` works. Each call installs both again.
    install: function (py) {{
      var base = root.CTMCheckers;
      if (!base || typeof base.install !== 'function') {{
        return Promise.reject(new Error({json.dumps(distribution)} + ' needs ctm-checkers.js on the page, loaded before it'));
      }}
      if (base.version !== checkers.version) {{
        return Promise.reject(new Error({json.dumps(distribution)} + ' ' + checkers.version + ' needs ctm-checkers ' + checkers.version
          + '; the page has ' + base.version));
      }}
      var name = '_ctm_checkers_{part}_payload_' + (++installs);
      var payload = JSON.stringify({{name: checkers.name, part: checkers.part, version: checkers.version, wheel: checkers.wheel,
        sha256: checkers.sha256, data: checkers.data}});
      return Promise.resolve(base.install(py)).then(function () {{
        return py.globals.set(name, payload);
      }}).then(function () {{
        return py.runPythonAsync(INSTALL.split('_ctm_checkers_part_payload').join(name));
      }});
    }}
  }};
  if (!root.{name}) root.{name} = checkers;
}})(typeof globalThis !== 'undefined' ? globalThis : this);
'''


def generated(version, api, datas):
    """The extension folder's files for the wheels `datas` ({part: bytes}): {name: bytes}."""
    data = datas['base']
    parts = {}
    for part in PARTS:
        if part != 'base':
            distribution, _, script, _, _ = PARTS[part]
            parts[part] = {'name': distribution, 'dependency': dependency_version(version, datas[part]),
                           'wheel': wheel_name(version, part), 'sha256': hashlib.sha256(datas[part]).hexdigest(), 'script': script}
    manifest = {'name': 'ctm-checkers', 'version': version, 'api': api, 'dependency': dependency_version(version, data),
                'wheel': wheel_name(version), 'sha256': hashlib.sha256(data).hexdigest(), 'script': SCRIPT, 'parts': parts,
                'generated': 'by tools/build.py from src/; do not edit'}
    extension = '\n'.join([
        '# Generated by ctm-checkers tools/build.py from src/; do not edit.',
        '# The wheels and the page scripts of ctm-checkers (checkers.json); authors',
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
    files = {'_extension.yml': extension.encode('utf-8'),
             'checkers.json': (json.dumps(manifest, indent=1) + '\n').encode('utf-8')}
    for part in PARTS:
        files[wheel_name(version, part)] = datas[part]
        files[PARTS[part][2]] = (base_script(version, api, data) if part == 'base'
                                 else part_script(version, api, datas[part], part)).encode('utf-8')
    return files


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


def release_entry(contents, datas, scripts):
    """What a release is: for each wheel the digest of its contents (its RECORD
    lists every file with its sha256), the wheel file and its page script."""
    def entry(part):
        record = next(text for name, text in contents[part].items() if name.endswith('.dist-info/RECORD'))
        return {'contents': hashlib.sha256(record).hexdigest(), 'wheel': hashlib.sha256(datas[part]).hexdigest(),
                'script': hashlib.sha256(scripts[part]).hexdigest()}
    out = entry('base')
    for part in PARTS:
        if part != 'base':
            out[part] = entry(part)
    return out


def release_problems(version, contents, datas, scripts):
    """A released version never changes; a development version is above every release."""
    versions = released_versions()
    if is_release(version):
        if version not in versions:
            return [f'{version} is a release version without an entry in tools/released.json: the release PR adds it with '
                    f'python tools/build.py --release; otherwise set a development version ({version}.dev0 or later)']
        entry = release_entry(contents, datas, scripts)
        recorded = versions[version]
        changed = [key for key in ('contents', 'wheel', 'script') if recorded.get(key) != entry[key]]
        changed += [f'{part} {key}' for part in PARTS if part != 'base'
                    for key in ('contents', 'wheel', 'script') if recorded.get(part, {}).get(key) != entry[part][key]]
        if changed:
            return [f'{version} is released (tools/released.json) and its {", ".join(changed)} changed: released code never changes; '
                    f'set the next development version (for example {next_dev(version)}) in src/ctm_checkers/__init__.py']
        return []
    above = [v for v in versions if version_key(v) >= version_key(version)]
    if above:
        return [f'{version} is not above the released {", ".join(sorted(above, key=version_key))}: set a later development version']
    return []


def base_release_problems(base, current):
    """A release recorded on the base branch stays recorded, unchanged: a pull
    request cannot rewrite a released entry together with the code."""
    problems = []
    for version, entry in base.items():
        if version not in current:
            problems.append(f'tools/released.json: the release {version} of the base branch is missing; released entries never change')
        elif current[version] != entry:
            problems.append(f'tools/released.json: the entry of the release {version} differs from the base branch; released entries never change')
    return problems


def released_at(ref):
    """The releases recorded in tools/released.json at the Git commit `ref` ({} where the file did not exist yet)."""
    found = subprocess.run(['git', 'cat-file', '-e', f'{ref}^{{commit}}'], cwd=ROOT, capture_output=True)
    if found.returncode:
        raise SystemExit(f'--released-base: {ref} is not a commit of this repository (fetch it first)')
    shown = subprocess.run(['git', 'show', f'{ref}:tools/released.json'], cwd=ROOT, capture_output=True, text=True)
    return json.loads(shown.stdout)['versions'] if shown.returncode == 0 else {}


def next_dev(version):
    major, minor, patch = (int(part) for part in re.match(r'(\d+)\.(\d+)\.(\d+)', version).groups())
    return f'{major}.{minor}.{patch + 1}.dev0'


def zip_problems(name, data):
    """The committed wheel is written as tools/build.py writes it."""
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        bad = [info.filename for info in archive.infolist()
               if info.compress_type != zipfile.ZIP_DEFLATED or info.date_time != (1980, 1, 1, 0, 0, 0)
               or info.external_attr >> 16 != (0o40755 if info.filename.endswith('/') else 0o644)]
    return [f'{name}: entries not written as tools/build.py writes them (DEFLATE, 1980-01-01, 0644): {", ".join(bad[:5])}'] if bad else []


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--check', action='store_true', help='check the committed folder instead of writing it')
    parser.add_argument('--release', action='store_true', help='also record this release version in tools/released.json')
    parser.add_argument('--released-base', metavar='REF',
                        help='with --check: the releases recorded at this Git commit (the base branch) must be recorded here unchanged')
    options = parser.parse_args(argv)
    if options.released_base and not options.check:
        parser.error('--released-base needs --check')
    version, api = package_info()
    contents = {part: wheel_contents(version, part) for part in PARTS}
    committed = {part: OUT / wheel_name(version, part) for part in PARTS}
    problems = check_pyproject()
    if options.check:
        missing = [path for path in committed.values() if not path.is_file()]
        for path in missing:
            problems.append(f'{path.relative_to(ROOT)} is missing: run python tools/build.py')
        if not missing:
            datas = {part: path.read_bytes() for part, path in committed.items()}
            for part, path in committed.items():
                found = read_wheel(datas[part])
                if list(found) != list(contents[part]):
                    problems.append(f'{path.name}: its files are not those of src/ (run python tools/build.py)')
                for name in contents[part]:
                    if name in found and found[name] != contents[part][name]:
                        problems.append(f'{path.name}: {name} differs from src/ (run python tools/build.py)')
                problems += zip_problems(path.name, datas[part])
            expected = generated(version, api, datas)
            present = sorted(p.name for p in OUT.iterdir()) if OUT.is_dir() else []
            if present != sorted(expected):
                problems.append(f'_extensions/ctm-checkers/ must hold exactly {", ".join(sorted(expected))}; it holds {", ".join(present)}')
            wheels = {path.name for path in committed.values()}
            for name, text in expected.items():
                path = OUT / name
                if name not in wheels and (not path.is_file() or path.read_bytes() != text):
                    problems.append(f'_extensions/ctm-checkers/{name} is not what the committed wheels give (run python tools/build.py)')
            scripts = {part: (OUT / PARTS[part][2]).read_bytes() if (OUT / PARTS[part][2]).is_file() else b'' for part in PARTS}
            problems += release_problems(version, contents, datas, scripts)
        elif not is_release(version):
            problems += release_problems(version, contents, {}, {})   # the order of versions needs no wheel
        if options.released_base:
            problems += base_release_problems(released_at(options.released_base), released_versions())
        for problem in problems:
            print('build --check:', problem, file=sys.stderr)
        if not problems:
            print(f'_extensions/ctm-checkers/ is current: ctm-checkers {version} (API {api}{", released" if is_release(version) else ""}), '
                  + ', '.join(f'{path.name} sha256 {hashlib.sha256(path.read_bytes()).hexdigest()}' for path in committed.values())
                  + (f'; the releases of {options.released_base} are unchanged' if options.released_base else ''))
        return 1 if problems else 0
    # Keep a committed wheel while its contents are current.
    datas = {}
    for part, path in committed.items():
        if path.is_file() and list(read_wheel(path.read_bytes()).items()) == list(contents[part].items()):
            datas[part] = path.read_bytes()
        else:
            datas[part] = wheel_bytes(contents[part])
    expected = generated(version, api, datas)
    scripts = {part: expected[PARTS[part][2]] for part in PARTS}
    versions = released_versions()
    if options.release:
        if not is_release(version):
            problems.append(f'--release: {version} is a development version')
        elif version not in versions:
            versions[version] = release_entry(contents, datas, scripts)
            document = json.loads(RELEASED.read_text(encoding='utf-8')) if RELEASED.exists() else {'versions': {}}
            document['versions'] = dict(sorted(versions.items(), key=lambda item: version_key(item[0])))
            RELEASED.write_text(json.dumps(document, indent=1) + '\n', encoding='utf-8')
            print(f'Recorded the release {version} in tools/released.json')
    if is_release(version) and version in versions:
        problems += release_problems(version, contents, datas, scripts)
    elif not is_release(version):
        problems += release_problems(version, contents, datas, scripts)
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
    print(f'Wrote _extensions/ctm-checkers/ for ctm-checkers {version} (API {api}): '
          + ', '.join(f'{wheel_name(version, part)}, {len(datas[part])} bytes, sha256 {hashlib.sha256(datas[part]).hexdigest()}'
                      for part in PARTS))
    if is_release(version) and version not in versions:
        print(f'{version} is a release version: record it with python tools/build.py --release', file=sys.stderr)
    return 0


if __name__ == '__main__':
    sys.exit(main())
