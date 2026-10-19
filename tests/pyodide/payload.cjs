#!/usr/bin/env node
// The page script's install code in Pyodide (design §3.3, §13 items 2 and 4):
// installed through an object that offers only globals.set and
// runPythonAsync (pyodide-interaktiv's worker proxy), it leaves no names in
// the page's namespace, serves math-exercise's request protocol, installs
// again after learner code removed it, and refuses a damaged payload.
//   node tests/pyodide/payload.cjs --umbrella DIR --version 0.28.3
'use strict';
const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const vm = require('node:vm');

const ROOT = path.resolve(__dirname, '..', '..');
const args = process.argv.slice(2);
const option = name => { const i = args.indexOf('--' + name); return i >= 0 ? args[i + 1] : null; };

function loadScript(change = text => text) {
  const manifest = JSON.parse(fs.readFileSync(path.join(ROOT, '_extensions/ctm-checkers/checkers.json'), 'utf8'));
  const sandbox = {};
  vm.createContext(sandbox);
  vm.runInContext(change(fs.readFileSync(path.join(ROOT, '_extensions/ctm-checkers', manifest.script), 'utf8')), sandbox);
  return {manifest, checkers: sandbox.CTMCheckers};
}

(async () => {
  const parity = path.join(path.resolve(option('umbrella')), 'integration', 'pyodide-parity');
  const {boot} = require(path.join(parity, 'runtime.cjs'));
  const {ensureWheels} = require(path.join(parity, 'wheels.cjs'));
  const version = option('version');
  const wheels = await ensureWheels(version, process.env.PYODIDE_PARITY_CACHE || fs.mkdtempSync(path.join(os.tmpdir(), 'ctm-wheels-')));
  const {py, python} = await boot(version, wheels);
  await py.loadPackage('sympy');
  const proxy = {globals: {set: (name, value) => py.globals.set(name, value)}, runPythonAsync: code => py.runPythonAsync(code)};
  const {manifest, checkers} = loadScript();
  assert.equal(checkers.version, manifest.version);
  assert.equal(checkers.sha256, manifest.sha256);
  const names = () => JSON.parse(py.runPython('__import__("json").dumps(sorted(globals()))'));

  // Installed through the proxy; the page's namespace keeps its names.
  py.runPython('learner = 42');
  const before = names();
  await checkers.install(proxy);
  assert.deepEqual(names(), before);
  assert.equal(py.runPython('learner'), 42);
  const file = py.runPython('import sys; sys.modules["ctm_checkers"].__file__');
  assert.ok(file.startsWith(`/tmp/ctm-checkers/${manifest.sha256.slice(0, 16)}/${manifest.wheel}/`), file);

  // math-exercise's call: one request, taken out of the namespace.
  const CALL = '__import__("ctm_checkers.browser", fromlist=["call"]).call("math_exercise.check", globals())';
  const request = {student: '2*x', correct: 'x+x', vars: 'x', mode: 'equivalent', reject: '', tolerance: '', decplaces: '', sigfigs: '',
    form: '', partial_credit: false, form_credit: 0.5};
  await proxy.globals.set('_ctm_request', JSON.stringify(request));
  assert.deepEqual(JSON.parse(await proxy.runPythonAsync(CALL)), {status: 'correct', score: 1.0});
  assert.deepEqual(names(), before);

  // Learner code removes the library: the call fails with the message that
  // math-exercise's retry recognizes; installing again repairs it.
  py.runPython('[sys.modules.pop(n) for n in list(sys.modules) if n.startswith("ctm_checkers")]\n'
    + 'sys.path[:] = [p for p in sys.path if not p.startswith("/tmp/ctm-checkers/")]');
  await proxy.globals.set('_ctm_request', JSON.stringify(request));
  await assert.rejects(proxy.runPythonAsync(CALL), /No module named 'ctm_checkers/);
  py.runPython('globals().pop("_ctm_request", None)');
  await checkers.install(proxy);
  await checkers.install(proxy);   // and again: idempotent
  await proxy.globals.set('_ctm_request', JSON.stringify(request));
  assert.equal(JSON.parse(await proxy.runPythonAsync(CALL)).status, 'correct');

  // Learner code rebound builtins and module names in the page's namespace:
  // the install code looks none of them up there.
  const LEARNER = ['open', 'RuntimeError', 'list', 'len', 'isinstance', 'str', 'Exception', 'io', 'os', 'json', 'base64', 'hashlib', 'importlib', 'builtins'];
  py.runPython(LEARNER.map(name => `${name} = None`).join('\n'));
  const shadowed = names();
  await checkers.install(proxy);
  assert.deepEqual(names(), shadowed);
  await assert.rejects(loadScript(text => text.replace(/data: '([A-Za-z0-9+\/]{24})/, (match, start) => "data: '" + [...start].reverse().join(''))).checkers.install(proxy),
    /RuntimeError: ctm-checkers: the payload is damaged/);
  // Installs that overlap (two cells retrying at once) each keep their own payload.
  await Promise.all([checkers.install(proxy), checkers.install(proxy), checkers.install(proxy)]);
  assert.deepEqual(names(), shadowed);
  py.runPython(LEARNER.map(name => `del ${name}`).join('\n'));

  // A damaged script (its wheel data changed) is refused and leaves no names behind.
  const damaged = loadScript(text => text.replace(/data: '([A-Za-z0-9+\/]{24})/, (match, start) => "data: '" + [...start].reverse().join(''))).checkers;
  assert.notEqual(damaged.data, checkers.data);
  await assert.rejects(damaged.install(proxy), /payload is damaged/);
  assert.deepEqual(names(), before);
  console.log(`Payload of ${manifest.wheel} in Pyodide ${version} (Python ${python}): install, request, reinstall, learner globals, overlapping installs, damaged: ok`);
  process.exit(0);
})().catch(error => { console.error(error); process.exit(1); });
