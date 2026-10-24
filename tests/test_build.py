"""tools/build.py: the generated folder is current; the wheel is well formed;
the install code installs it and leaves no names behind but the two the call
text uses; released versions never change."""
import base64
import hashlib
import io
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import zipfile

import pytest

import build
from tests.conftest import ROOT


def test_the_committed_folder_is_current():
    assert build.main(['--check']) == 0


def test_versions_and_dependency_versions():
    assert build.semver('0.1.0') == '0.1.0'
    assert build.semver('0.2.0.dev0') == '0.2.0-dev.0'
    assert build.semver('1.0.0rc2') == '1.0.0-rc.2'
    assert build.dependency_version('0.1.0', b'wheel') == '0.1.0'
    assert build.dependency_version('0.2.0.dev0', b'wheel') == '0.2.0.dev0+' + hashlib.sha256(b'wheel').hexdigest()[:8]


def committed():
    manifest = json.loads((build.OUT / 'checkers.json').read_text())
    return manifest, (build.OUT / manifest['wheel']).read_bytes()


def test_the_wheel_records_its_files():
    manifest, data = committed()
    version, api = build.package_info()
    assert (manifest['version'], manifest['api']) == (version, api)
    assert manifest['sha256'] == hashlib.sha256(data).hexdigest()
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        infos = archive.infolist()
        names = [info.filename for info in infos]
        record = archive.read(f'ctm_checkers-{version}.dist-info/RECORD').decode()
        for line in record.splitlines():
            name, digest, size = line.rsplit(',', 2)
            if digest:
                content = archive.read(name)
                assert digest == build.record_hash(content) and int(size) == len(content), name
        assert sorted(line.rsplit(',', 2)[0] for line in record.splitlines()) == sorted(names)
        assert all(info.date_time == (1980, 1, 1, 0, 0, 0) and info.external_attr >> 16 == 0o644 for info in infos)
        assert names[-1].endswith('.dist-info/RECORD') and not any(n.endswith('.pyc') for n in names)


def test_the_stack_wheel_carries_stacks_licence_and_the_base_wheel_does_not():
    # stack_data.py is STACK's data (GPL-3.0-or-later) in an AGPL-3.0-or-later package: the STACK wheel is
    # licensed under both and holds the GPL's text; the base wheel (math pages) holds neither.
    manifest, _ = committed()
    version, _ = build.package_info()
    stack_wheel = (build.OUT / manifest['parts']['stack']['wheel']).read_bytes()
    with zipfile.ZipFile(io.BytesIO(stack_wheel)) as archive:
        dist = f'ctm_checkers_stack-{version}.dist-info'
        metadata = archive.read(f'{dist}/METADATA').decode()
        gpl = archive.read(f'{dist}/licenses/{build.GPL_NAME}')
        names = archive.namelist()
        assert 'ctm_checkers/stack/stack_data.py' in names
        header = ' '.join(archive.read('ctm_checkers/stack/stack_data.py').decode().split('"""')[1].split())
    assert 'License: AGPL-3.0-or-later AND GPL-3.0-or-later\n' in metadata
    assert gpl == build.GPL_TEXT.read_bytes() and gpl.startswith(b'                    GNU GENERAL PUBLIC LICENSE\n                       Version 3, 29 June 2007')
    assert f'{dist}/LICENSE' in names                              # the AGPL, too
    for notice in ('University of Edinburgh', 'Aalto University', 'GPL-3.0-or-later', 'section 13',
                   'AGPL-3.0-or-later AND GPL-3.0-or-later'):
        assert notice in header, notice
    base_wheel = (build.OUT / manifest['wheel']).read_bytes()
    with zipfile.ZipFile(io.BytesIO(base_wheel)) as archive:
        assert 'License: AGPL-3.0-or-later\n' in archive.read(f'ctm_checkers-{version}.dist-info/METADATA').decode()
        assert not any('GPL-3.0-STACK' in name or 'stack_data' in name for name in archive.namelist())
    script_header = ' '.join((build.OUT / manifest['parts']['stack']['script']).read_text()[:1500].split())
    assert 'AGPL-3.0-or-later AND GPL-3.0-or-later' in script_header and 'stack_data.py' in script_header


def test_the_page_script_carries_the_committed_wheel():
    manifest, data = committed()
    script = (build.OUT / manifest['script']).read_text()
    assert f"data: '{base64.b64encode(data).decode()}'" in script
    assert script.startswith('/* ctm-checkers ') and 'do not edit' in script.split('*/')[0]


# Names learner code may have rebound in the page's namespace.
LEARNER = ('open', 'RuntimeError', 'list', 'len', 'isinstance', 'str', 'Exception', 'io', 'os', 'json', 'base64', 'hashlib',
           'importlib', 'builtins', '__import__', 'globals')
# The page's call text: ctm-libs' (MathExerciseRuntime.callCheckers), as docs/api.md writes it.
CALL = ('import builtins as _ctm_builtins\n'
        'result = _ctm_builtins.__import__("ctm_checkers.browser", fromlist=["call"]).call("math_exercise.check", _ctm_builtins.globals())')
REQUEST = {'student': '2*x', 'correct': 'x+x', 'vars': 'x', 'mode': 'equivalent', 'reject': '', 'tolerance': '', 'decplaces': '',
           'sigfigs': '', 'form': '', 'partial_credit': False, 'form_credit': 0.5}


def install(payload, tmp_path, extra=''):
    # The install code natively (it is plain Python): in __main__, as the page
    # runs it, after learner code rebound builtins and module names there;
    # then a request through the call text.
    code = ('import sys as _t, builtins as _tb, json as _tj\n_ctm_checkers_payload = _t.stdin.read()\nlearner = 1\n'
            + ''.join(f'{name} = None\n' for name in LEARNER) + 'before = set(_tb.globals())\n'
            + build.INSTALL + '\n'
            + 'import ctm_checkers\n'
            + 'after = set(_tb.globals()) - before - {"before", "ctm_checkers"}\n'
            + '_ctm_request = ' + repr(json.dumps(REQUEST)) + '\n'
            + CALL + '\n'
            + 'print(_tj.dumps({"file": ctm_checkers.__file__, "left": sorted(after), "gone": sorted(before - set(_tb.globals())), '
              '"learner": [learner] + [_tb.globals()[name] for name in ' + repr(LEARNER) + '], "result": _tj.loads(result), '
              '"request": "_ctm_request" in _tb.globals()}))\n' + extra)
    return subprocess.run([sys.executable, '-c', code], input=json.dumps(payload), capture_output=True, text=True,
                          cwd=tmp_path, env=dict(os.environ, PYTHONPATH=''))


@pytest.fixture
def install_folder():
    # The install code writes under /tmp/ctm-checkers/<sha256[:16]>/, as in Pyodide; tidied afterwards.
    manifest, _ = committed()
    folder = Path('/tmp/ctm-checkers') / manifest['sha256'][:16]
    existed = folder.exists()
    yield folder
    if not existed:
        shutil.rmtree(folder, ignore_errors=True)
        try:
            folder.parent.rmdir()
        except OSError:
            pass


@pytest.mark.skipif(os.name != 'posix', reason='the install code writes under /tmp, as in Pyodide')
def test_the_install_code(tmp_path, install_folder):
    manifest, data = committed()
    payload = {'version': manifest['version'], 'wheel': manifest['wheel'], 'sha256': manifest['sha256'],
               'data': base64.b64encode(data).decode()}
    result = install(payload, tmp_path)
    assert result.returncode == 0, result.stderr
    report = json.loads(result.stdout)
    assert report['file'].startswith(str(install_folder / manifest['wheel']) + '/')
    # The install code leaves no name in the namespace; learner variables keep their values.
    assert report['left'] == [] and report['gone'] == ['_ctm_checkers_payload']
    assert report['learner'] == [1] + [None] * len(LEARNER)
    # The call text works although learner code rebound __import__, globals and builtins, and takes the request out.
    assert report['result'] == {'status': 'correct', 'score': 1.0} and report['request'] is False
    # Learner code removed it: installing again works.
    again = install(payload, tmp_path, extra=(
        'import sys\nfor n in [n for n in sys.modules if n.startswith("ctm_checkers")]: del sys.modules[n]\n'
        'sys.path.remove(ctm_checkers.__file__.rsplit("/ctm_checkers/", 1)[0])\n'
        '_ctm_checkers_payload = ' + repr(json.dumps(payload)) + '\n' + build.INSTALL + '\n'
        'import ctm_checkers.browser\nprint(ctm_checkers.browser.__file__)\n'))
    assert again.returncode == 0, again.stderr
    damaged = install(dict(payload, data=base64.b64encode(data[:-1] + b'x').decode()), tmp_path)
    assert damaged.returncode == 1 and 'RuntimeError: ctm-checkers: the payload is damaged' in damaged.stderr


def copy_of_repository(tmp_path):
    for name in ('src', 'tools', '_extensions'):
        shutil.copytree(ROOT / name, tmp_path / name, ignore=shutil.ignore_patterns('__pycache__'))
    for name in ('LICENSE', 'pyproject.toml'):
        shutil.copy2(ROOT / name, tmp_path / name)
    gpl = tmp_path / build.GPL_TEXT.relative_to(ROOT)    # the STACK wheel carries it
    gpl.parent.mkdir(parents=True)
    shutil.copy2(build.GPL_TEXT, gpl)
    return tmp_path


def run_build(root, *args):
    return subprocess.run([sys.executable, str(root / 'tools' / 'build.py'), *args], capture_output=True, text=True)


def set_version(root, version):
    path = root / 'src' / 'ctm_checkers' / '__init__.py'
    path.write_text(re.sub(r'__version__ = "[^"]+"', f'__version__ = "{version}"', path.read_text()))


def test_a_released_version_never_changes(tmp_path):
    # Review S3: without tags, tools/released.json keeps each release's contents.
    root = copy_of_repository(tmp_path)
    version, _ = build.package_info()
    assert version in json.loads((ROOT / 'tools' / 'released.json').read_text())['versions'] or '.dev' in version
    if '.dev' in version:   # release it in the copy, as its release PR will
        version = version.split('.dev')[0]
        set_version(root, version)
        result = run_build(root, '--release')
        assert result.returncode == 0 and f'Recorded the release {version}' in result.stdout, result.stderr
        assert run_build(root, '--check').returncode == 0
    module = root / 'src' / 'ctm_checkers' / 'matrix.py'
    module.write_text(module.read_text() + '\n# a change\n')
    for args in ((), ('--check',)):
        result = run_build(root, *args)
        assert result.returncode == 1 and 'is released (tools/released.json)' in result.stderr, (args, result.stderr)
    # A development version below the release is refused; the next one is built, with a dependency version per content.
    set_version(root, version + '.dev0')   # X.Y.Z.dev0 comes before X.Y.Z
    result = run_build(root, '--check')
    assert result.returncode == 1 and 'is not above the released' in result.stderr, result.stderr
    major, minor, patch = (int(part) for part in version.split('.')[:3])
    following = f'{major}.{minor}.{patch + 1}.dev0'
    set_version(root, following)
    assert run_build(root).returncode == 0 and run_build(root, '--check').returncode == 0
    manifest = json.loads((root / '_extensions' / 'ctm-checkers' / 'checkers.json').read_text())
    data = (root / '_extensions' / 'ctm-checkers' / manifest['wheel']).read_bytes()
    assert manifest['dependency'] == following + '+' + hashlib.sha256(data).hexdigest()[:8]
    assert f'version: {major}.{minor}.{patch + 1}-dev.0' in (root / '_extensions' / 'ctm-checkers' / '_extension.yml').read_text()


def test_the_wheel_is_written_as_build_writes_it(tmp_path):
    root = copy_of_repository(tmp_path)
    manifest = json.loads((root / '_extensions' / 'ctm-checkers' / 'checkers.json').read_text())
    path = root / '_extensions' / 'ctm-checkers' / manifest['wheel']
    with zipfile.ZipFile(io.BytesIO(path.read_bytes())) as archive:
        files = [(info, archive.read(info.filename)) for info in archive.infolist()]
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, 'w') as archive:
        for info, data in files:
            info.compress_type = zipfile.ZIP_STORED
            archive.writestr(info, data)
    path.write_bytes(buffer.getvalue())
    result = run_build(root, '--check')
    assert result.returncode == 1 and 'not written as tools/build.py writes them' in result.stderr, result.stderr


def test_released_entries_of_the_base_branch_stay(tmp_path):
    # Review round 2: a pull request cannot rewrite a released entry together with the code.
    base = {'0.1.0': {'contents': 'a', 'wheel': 'b', 'script': 'c'}}
    assert build.base_release_problems(base, base) == []
    assert build.base_release_problems(base, dict(base, **{'0.1.1': {'contents': 'd', 'wheel': 'e', 'script': 'f'}})) == []
    assert build.base_release_problems({}, base) == []
    assert 'differs from the base branch' in build.base_release_problems(base, {'0.1.0': dict(base['0.1.0'], script='x')})[0]
    assert 'is missing' in build.base_release_problems(base, {})[0]
    # Through Git: --check --released-base REF compares with tools/released.json at REF.
    root = copy_of_repository(tmp_path)
    git = lambda *args: subprocess.run(['git', *args], cwd=root, capture_output=True, text=True, check=True)
    git('init', '-q'); git('add', '-A')
    git('-c', 'user.name=t', '-c', 'user.email=t@example.org', 'commit', '-q', '-m', 'base')
    assert run_build(root, '--check', '--released-base', 'HEAD').returncode == 0
    path = root / 'tools' / 'released.json'
    document = json.loads(path.read_text())
    version = next(iter(document['versions']))
    document['versions'][version]['script'] = '0' * 64
    path.write_text(json.dumps(document, indent=1) + '\n')
    result = run_build(root, '--check', '--released-base', 'HEAD')
    assert result.returncode == 1 and f'the entry of the release {version} differs from the base branch' in result.stderr, result.stderr
    result = run_build(root, '--check', '--released-base', 'no-such-commit')
    assert result.returncode == 1 and 'is not a commit of this repository' in result.stderr, result.stderr
