#!/usr/bin/env node
// The page script's install code in Pyodide (design §3.3, §13 items 2 and 4):
// installed through an object that offers only globals.set and
// runPythonAsync (pyodide-interaktiv's worker proxy), it leaves no name in
// the page's namespace, serves math-exercise's request protocol through
// ctm-libs' call text (which looks up no name there: learner code may rebind
// `__import__`, `globals` and `builtins`), installs again after learner code
// removed it, and refuses a damaged payload.
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
  // The page's names, read from a namespace of its own (learner code may rebind `globals` there).
  const names = () => {
    const scope = py.toPy({page: py.globals});
    try { return JSON.parse(py.runPython('import json\njson.dumps(sorted(page))', {globals: scope})); } finally { scope.destroy(); }
  };
  // Removes a name from the page's namespace without looking anything up there.
  const drop = name => {
    const scope = py.toPy({page: py.globals});
    try { py.runPython(`page.pop(${JSON.stringify(name)}, None)`, {globals: scope}); } finally { scope.destroy(); }
  };

  // Installed through the proxy; the page's namespace keeps its names, and gains none.
  py.runPython('learner = 42');
  const before = names();
  await checkers.install(proxy);
  assert.deepEqual(names(), before);
  assert.equal(py.runPython('learner'), 42);
  const file = py.runPython('import sys; sys.modules["ctm_checkers"].__file__');
  assert.ok(file.startsWith(`/tmp/ctm-checkers/${manifest.sha256.slice(0, 16)}/${manifest.wheel}/`), file);

  // math-exercise's call (docs/api.md): one request, taken out of the
  // namespace, through ctm-libs' call text, whose own name ctm-libs removes afterwards.
  const CALL = 'import builtins as _ctm_builtins\n'
    + '_ctm_builtins.__import__("ctm_checkers.browser", fromlist=["call"]).call("math_exercise.check", _ctm_builtins.globals())';
  const call = async () => { try { return await proxy.runPythonAsync(CALL); } finally { drop('_ctm_builtins'); } };
  const request = {student: '2*x', correct: 'x+x', vars: 'x', mode: 'equivalent', reject: '', tolerance: '', decplaces: '', sigfigs: '',
    form: '', partial_credit: false, form_credit: 0.5};
  await proxy.globals.set('_ctm_request', JSON.stringify(request));
  assert.deepEqual(JSON.parse(await call()), {status: 'correct', score: 1.0});
  assert.deepEqual(names(), before);

  // Learner code removes the library: the call fails before it reaches
  // browser.call (the request is still there, which tells ctm-libs to install
  // again); installing again repairs it.
  py.runPython('[sys.modules.pop(n) for n in list(sys.modules) if n.startswith("ctm_checkers")]\n'
    + 'sys.path[:] = [p for p in sys.path if not p.startswith("/tmp/ctm-checkers/")]');
  await proxy.globals.set('_ctm_request', JSON.stringify(request));
  await assert.rejects(call(), /No module named 'ctm_checkers/);
  assert.ok(names().includes('_ctm_request'));
  drop('_ctm_request');
  await checkers.install(proxy);
  await checkers.install(proxy);   // and again: idempotent
  await proxy.globals.set('_ctm_request', JSON.stringify(request));
  assert.equal(JSON.parse(await call()).status, 'correct');
  assert.deepEqual(names(), before);
  // A call without a request is an error of its own.
  await assert.rejects(call(), /RuntimeError: ctm_checkers\.browser\.call\('math_exercise\.check'\): no request/);

  // Learner code rebound builtins and module names in the page's namespace,
  // `__import__`, `globals`, `builtins` and the call text's own name
  // included: the install code looks none of them up there, and the call text
  // works (the call text of math-exercise 0.10.0 did not).
  const LEARNER = ['open', 'RuntimeError', 'list', 'len', 'isinstance', 'str', 'Exception', 'io', 'os', 'json', 'base64', 'hashlib', 'importlib',
    'builtins', '__import__', 'globals'];
  py.runPython(LEARNER.map(name => `${name} = None`).join('\n'));
  const shadowed = names();
  await checkers.install(proxy);
  assert.deepEqual(names(), shadowed);
  py.runPython('_ctm_builtins = None');
  await proxy.globals.set('_ctm_request', JSON.stringify(request));
  assert.deepEqual(JSON.parse(await call()), {status: 'correct', score: 1.0});
  assert.deepEqual(names(), shadowed);
  await proxy.globals.set('_ctm_request', JSON.stringify(request));
  await assert.rejects(proxy.runPythonAsync('__import__("ctm_checkers.browser", fromlist=["call"]).call("math_exercise.check", globals())'),
    /'NoneType' object is not callable/);
  drop('_ctm_request');
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
  console.log(`Payload of ${manifest.wheel} in Pyodide ${version} (Python ${python}): install, request, reinstall, no request, learner globals, overlapping installs, damaged: ok`);
  process.exit(0);
})().catch(error => { console.error(error); process.exit(1); });
