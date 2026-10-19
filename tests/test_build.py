"""tools/build.py: the generated folder is current; the wheel is well formed;
the install code installs it and leaves no names behind."""
import base64
import hashlib
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import zipfile

import pytest

import build
from conftest import ROOT


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


def test_the_page_script_carries_the_committed_wheel():
    manifest, data = committed()
    script = (build.OUT / manifest['script']).read_text()
    assert f"data: '{base64.b64encode(data).decode()}'" in script
    assert script.startswith('/* ctm-checkers ') and 'do not edit' in script.split('*/')[0]


# Names learner code may have rebound in the page's namespace.
LEARNER = ('open', 'RuntimeError', 'list', 'len', 'isinstance', 'str', 'Exception', 'io', 'os', 'json', 'base64', 'hashlib',
           'importlib', 'builtins')


def install(payload, tmp_path, extra=''):
    # The install code natively (it is plain Python): in __main__, as the page
    # runs it, after learner code rebound builtins and module names there.
    code = ('import sys as _t\n_ctm_checkers_payload = _t.stdin.read()\nlearner = 1\n'
            + ''.join(f'{name} = None\n' for name in LEARNER) + 'before = set(globals())\n'
            + build.INSTALL + '\n'
            + 'import json as _j, ctm_checkers\n'
            + 'print(_j.dumps({"file": ctm_checkers.__file__, "left": sorted(set(globals()) - before - {"before", "ctm_checkers", "_j"}), '
              '"gone": sorted(before - set(globals())), "learner": learner}))\n' + extra)
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
    assert report['left'] == [] and report['gone'] == ['_ctm_checkers_payload'] and report['learner'] == 1
    # Learner code removed it: installing again works.
    again = install(payload, tmp_path, extra=(
        'import sys\nfor n in [n for n in sys.modules if n.startswith("ctm_checkers")]: del sys.modules[n]\n'
        'sys.path.remove(ctm_checkers.__file__.rsplit("/ctm_checkers/", 1)[0])\n'
        '_ctm_checkers_payload = ' + repr(json.dumps(payload)) + '\n' + build.INSTALL + '\n'
        'import ctm_checkers.browser\nprint(ctm_checkers.browser.__file__)\n'))
    assert again.returncode == 0, again.stderr
    damaged = install(dict(payload, data=base64.b64encode(data[:-1] + b'x').decode()), tmp_path)
    assert damaged.returncode == 1 and 'RuntimeError: ctm-checkers: the payload is damaged' in damaged.stderr
