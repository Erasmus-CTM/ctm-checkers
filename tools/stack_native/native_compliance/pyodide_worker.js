/* Independent parity harness: execute the same Python adapter in the real
 * browser Pyodide runtime as the student-facing worker: Pyodide as ctm-libs'
 * page runtime loads it, ctm-checkers installed by its committed page scripts
 * (their own install code, the STACK part included), then the compliance
 * runner. ?pyodide=<index URL> serves Pyodide from elsewhere (a local copy). */
'use strict';
const PYODIDE_VERSION = '0.28.3';
const INDEX_URL = new URLSearchParams(self.location.search).get('pyodide')
  || 'https://cdn.jsdelivr.net/pyodide/v' + PYODIDE_VERSION + '/full/';
importScripts(INDEX_URL + 'pyodide.js',
              '/_extensions/ctm-checkers/ctm-checkers.js',
              '/_extensions/ctm-checkers/ctm-checkers-stack.js');

let py;
let loadedVersions;
async function initialize() {
  if (py) return loadedVersions;
  const instance = await loadPyodide({indexURL: INDEX_URL});
  await instance.loadPackage('sympy');
  if (!globalThis.CTMCheckersStack || typeof globalThis.CTMCheckersStack.install !== 'function') {
    throw new Error('The committed page scripts of ctm-checkers are missing');
  }
  await globalThis.CTMCheckersStack.install(instance);
  instance.FS.mkdirTree('/home/pyodide/native_compliance');
  instance.FS.writeFile('/home/pyodide/native_compliance/__init__.py', '');
  for (const name of ['common.py', 'python_runner.py']) {
    const response = await fetch('/tools/stack_native/native_compliance/' + name);
    if (!response.ok) throw new Error('Cannot load parity module ' + name + ': HTTP ' + response.status);
    instance.FS.writeFile('/home/pyodide/native_compliance/' + name, await response.text());
  }
  const versions = JSON.parse(await instance.runPythonAsync([
    'import json, sys, sympy',
    "sys.path.insert(0, '/home/pyodide')",
    'from native_compliance.python_runner import evaluate_case',
    'json.dumps({"sympy_version": sympy.__version__})'
  ].join('\n')));
  if (instance.version !== PYODIDE_VERSION) {
    throw new Error('Loaded Pyodide ' + instance.version + ' does not match the pinned ' + PYODIDE_VERSION);
  }
  versions.pyodide_version = instance.version;
  py = instance;
  loadedVersions = versions;
  return loadedVersions;
}

self.onmessage = async function (event) {
  const {id, type, item} = event.data;
  try {
    if (type === 'init') {
      const versions = await initialize();
      self.postMessage({id, ok: true, result: versions});
    } else if (type === 'evaluate') {
      if (!py) throw new Error('Pyodide worker was not initialized');
      py.globals.set('_parity_case_json', JSON.stringify(item));
      const result = await py.runPythonAsync([
        'import json',
        'from native_compliance.python_runner import evaluate_case',
        'json.dumps(evaluate_case(json.loads(_parity_case_json)), ensure_ascii=True)'
      ].join('\n'));
      self.postMessage({id, ok: true, result: JSON.parse(result)});
    } else {
      throw new Error('Unknown parity worker request: ' + type);
    }
  } catch (error) {
    self.postMessage({id, ok: false, error: String(error && error.stack || error)});
  }
};
