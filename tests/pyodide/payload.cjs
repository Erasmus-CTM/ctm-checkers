#!/usr/bin/env node
// The page script's install code in Pyodide (design §3.3, §13 items 2 and 4):
// installed through an object that offers only globals.set and
// runPythonAsync (pyodide-interaktiv's worker proxy), it leaves no name in
// the page's namespace, serves math-exercise's request protocol through
// ctm-libs' call text (which looks up no name there: learner code may rebind
// `__import__`, `globals` and `builtins`), installs again after learner code
// removed it, and refuses a damaged payload. A math page's script carries no
// STACK engine; stack-sympy's worker adds ctm-checkers-stack.js, whose install
// installs both, serves its requests (stack.validate, stack.grade,
// stack.tests) and refuses a damaged payload, another version or a page
// without ctm-checkers.js.
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

// ctm-checkers.js and then ctm-checkers-stack.js, as stack-sympy's worker loads them.
function loadStackScripts(changeBase = text => text, changeStack = text => text, withBase = true) {
  const manifest = JSON.parse(fs.readFileSync(path.join(ROOT, '_extensions/ctm-checkers/checkers.json'), 'utf8'));
  const sandbox = {};
  vm.createContext(sandbox);
  if (withBase) vm.runInContext(changeBase(fs.readFileSync(path.join(ROOT, '_extensions/ctm-checkers', manifest.script), 'utf8')), sandbox);
  vm.runInContext(changeStack(fs.readFileSync(path.join(ROOT, '_extensions/ctm-checkers', manifest.parts.stack.script), 'utf8')), sandbox);
  return {manifest, base: sandbox.CTMCheckers, stack: sandbox.CTMCheckersStack};
}
const DAMAGE = text => text.replace(/data: '([A-Za-z0-9+\/]{24})/, (match, start) => "data: '" + [...start].reverse().join(''));

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

  // Generated mathematics uses the same admission in native and Pyodide calls.
  const keyCall = async request => {
    await proxy.globals.set('_ctm_request', JSON.stringify(request));
    return proxy.runPythonAsync('__import__("ctm_checkers.browser", fromlist=["call"]).call("math_exercise.compute_key", globals())');
  };
  assert.deepEqual(JSON.parse(await keyCall({recipe:{op:'diff',expr:'x^2',var:'x'},answer:'2*x',vars:'x'})), {key:'2*x',computed:true});
  await assert.rejects(keyCall({recipe:{op:'value',expr:'x.subs(x,1)'},answer:'1',vars:'x'}), /Unsupported generated/);
  await assert.rejects(keyCall({recipe:{op:'value',expr:'1'},answer:'__import__("os")',vars:''}), /Unsupported generated/);
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

  // Python run in a namespace of its own (the page's stays as it is).
  const inspect = (code, values = {}) => {
    const scope = py.toPy(values);
    try { return JSON.parse(py.runPython(code, {globals: scope})); } finally { scope.destroy(); }
  };
  // Exact rounding contracts execute from the wheel installed by the real page script.
  assert.deepEqual(inspect('import json\nfrom sympy import Rational, sin, pi\n'
    + 'from ctm_checkers.math_exercise.numeric import round_exact, sigfig_exact, round_places\n'
    + 'values=[round_exact(Rational("1.005"),2), round_exact(Rational("-1.005"),2), '
    + 'round_exact(Rational("1.00499999999999999999999999999"),2), '
    + 'sigfig_exact(sin(Rational(1,7)),2), sigfig_exact(sin(pi/7),2), '
    + 'sigfig_exact(Rational("0.00125"),2), sigfig_exact(10**100-1,3)]\n'
    + 'assert all(isinstance(v,Rational) for v in values)\n'
    + 'assert round_places(5.395,2)==5.4\n'
    + 'json.dumps([str(v) for v in values])'),
    ['101/100', '-101/100', '1', '7/50', '43/100', '13/10000', '1' + '0'.repeat(100)]);
  assert.deepEqual(names(), before);
  // Exact author context follows the same installed browser.call path as ordinary custom checks.
  const context = inspect('import json\nfrom sympy import Symbol, Rational, Matrix\n'
    + 'from ctm_checkers.variants import question_context\nx=Symbol("x", positive=True)\n'
    + 'json.dumps(question_context(["Svar α", "Second field"], {"x": x, "a": Rational(1,3), '
    + '"pair": [Symbol("x"), x], "matrix": Matrix([[x, Rational(1,3)]])}, '
    + '{"Svar α": x/3, "Second field": x}, {"n": 1, "id": "stable", "hash": "reviewed"}))');
  const customCall = async request => {
    await proxy.globals.set('_ctm_request', JSON.stringify(request));
    try {
      return JSON.parse(await proxy.runPythonAsync('import builtins as _ctm_builtins\n'
        + '_ctm_builtins.__import__("ctm_checkers.browser", fromlist=["call"]).call("math_exercise.check_custom", _ctm_builtins.globals())'));
    } finally { drop('_ctm_builtins'); }
  };
  const contextual = {vars: 'x', question_context: context,
    response: {kind: 'expressions', raw: ['x/3', 'x'], inputs: {},
      answers: 'forged', variables: 'forged', teacher: 'forged', variant: 'forged'},
    checker: 'def check(r,s):\n'
      + '    assert list(r["answers"]) == ["Svar α", "Second field"]\n'
      + '    assert r["answers"] == r["teacher"]\n'
      + '    assert r["expressions"][1] is s["x"] and s["x"] is r["variables"]["x"]\n'
      + '    assert s["x"].is_positive and r["variables"]["a"] == Rational(1,3)\n'
      + '    assert r["variables"]["pair"][0] != r["variables"]["pair"][1]\n'
      + '    assert r["variables"]["matrix"][0,0] is s["x"]\n'
      + '    assert r["variant"] == {"n":1,"id":"stable","hash":"reviewed"}\n'
      + '    assert \'"variables":"forged"\' in _math_response_json\n'
      + '    return True'};
  assert.equal((await customCall(contextual)).status, 'correct');
  assert.equal((await customCall({...contextual, question_context: {...context, variant: null},
    checker: 'def check(r,s): return r["variant"] is None'})).status, 'correct');
  assert.equal((await customCall({vars:'x', response:{point:9007199254740992},
    checker:'def check(r,s): return r["point"] == 9007199254740992 and "variables" not in r'})).status, 'correct');
  assert.equal((await customCall({...contextual, question_context: {...context, version:true}})).status, 'error');
  assert.equal((await customCall({...contextual, response:{point:0.1}})).status, 'error');
  const structuredTeacher = inspect('import json\nfrom sympy import Matrix, Rational\n'
    + 'from ctm_checkers.variants import question_context\n'
    + 'json.dumps(question_context(["Matrix α", "List field"], {}, {"Matrix α": Matrix([[1,2]]), "List field": [Rational(1,3),2]}))');
  assert.equal((await customCall({vars:'x', question_context:structuredTeacher,
    response:{kind:'expressions', raw:['1','2'], inputs:{}},
    checker:'def check(r,s): return r["teacher"]["Matrix α"] == Matrix([[1,2]]) and r["teacher"]["List field"] == [Rational(1,3),2] and r["answers"] == {"Matrix α":1,"List field":2}'})).status, 'correct');
  assert.deepEqual(names(), before);


  const WALK = 'import json, pkgutil, ctm_checkers\njson.dumps(sorted(m.name for m in pkgutil.walk_packages(ctm_checkers.__path__, "ctm_checkers.")))';
  // A math page carries ctm-checkers.js alone: no STACK engine (design §13 item 5), also for
  // ctm-libs' load, which walks the package (MathExerciseRuntime.ensureCheckers).
  await checkers.install(proxy);
  assert.equal(inspect('import json, importlib.util as u\njson.dumps(u.find_spec("ctm_checkers.stack") is None)'), true);
  const math = inspect(WALK);
  assert.ok(math.includes('ctm_checkers.math_exercise.checks') && !math.some(name => name.startsWith('ctm_checkers.stack')), math.join());

  // stack-sympy's worker: ctm-checkers-stack.js after ctm-checkers.js; its install installs both.
  const {base, stack} = loadStackScripts();
  assert.equal(stack.version, manifest.version);
  assert.equal(stack.sha256, manifest.parts.stack.sha256);
  assert.equal(stack.wheel, manifest.parts.stack.wheel);
  await stack.install(proxy);
  await stack.install(proxy);   // and again: idempotent
  assert.deepEqual(names(), before);
  const all = inspect(WALK);
  assert.ok(all.includes('ctm_checkers.stack.engine') && all.includes('ctm_checkers.math_exercise.checks'), all.join());
  // Its requests, through ctm-libs' call text: stack-sympy's worker requests and envelope.
  const xml = fs.readFileSync(path.join(ROOT, 'examples/stack/polynomial-expansion.xml'), 'utf8');
  const prepared = inspect('import json\nfrom ctm_checkers.stack.importer import import_xml\nfrom ctm_checkers.stack.engine import instantiate\n'
    + 'q = import_xml(xml)[0]\njson.dumps({"question": q, "variant": instantiate(q, 1)})', {xml});
  const stackCall = async (name, request) => {
    await proxy.globals.set('_ctm_request', JSON.stringify(request));
    return JSON.parse(await call_(name));
  };
  const call_ = async name => {
    try {
      return await proxy.runPythonAsync('import builtins as _ctm_builtins\n'
        + `_ctm_builtins.__import__("ctm_checkers.browser", fromlist=["call"]).call(${JSON.stringify(name)}, _ctm_builtins.globals())`);
    } finally { drop('_ctm_builtins'); }
  };
  const graded = await stackCall('stack.grade', {...prepared, answers: {ans: 'x^2+7*x+12'}});
  assert.equal(graded.ok, true);
  assert.equal(graded.result.status, 'graded');
  assert.equal(graded.result.score, 1);
  assert.equal((await stackCall('stack.grade', {...prepared, answers: {ans: '(x+3)*(x+4)'}})).result.score < 1, true);
  assert.equal((await stackCall('stack.validate', {...prepared, answers: {ans: 'x^2+'}})).result.status, 'invalid');
  assert.equal((await stackCall('stack.tests', {...prepared, answers: {}})).result.passed, true);
  const unsupported = await stackCall('stack.grade', {...prepared, question: {...prepared.question, variables: 'a:1; a:2'}, answers: {ans: 'x'}});
  assert.equal(unsupported.ok, false);
  assert.match(unsupported.error, /reassigned variable is unsupported/);
  assert.deepEqual(names(), before);
  // ctm-checkers alone installed again (a math cell's retry) leaves no STACK engine until its payload installs again.
  await checkers.install(proxy);
  await proxy.globals.set('_ctm_request', JSON.stringify({...prepared, answers: {ans: 'x'}}));
  await assert.rejects(call_('stack.grade'), /No module named 'ctm_checkers.stack'/);
  drop('_ctm_request');
  await stack.install(proxy);
  assert.equal((await stackCall('stack.grade', {...prepared, answers: {ans: 'x^2+7*x+12'}})).result.score, 1);
  // Refused: a damaged payload, another version of ctm-checkers on the page, a page without ctm-checkers.js.
  await assert.rejects(loadStackScripts(text => text, DAMAGE).stack.install(proxy), /RuntimeError: ctm-checkers: the payload of ctm-checkers-stack is damaged/);
  await assert.rejects(loadStackScripts(text => text.replace(`version: ${JSON.stringify(base.version)}`, 'version: "0.0.0"')).stack.install(proxy),
    /needs ctm-checkers .* the page has 0\.0\.0/);
  await assert.rejects(loadStackScripts(undefined, undefined, false).stack.install(proxy), /needs ctm-checkers\.js on the page/);
  assert.deepEqual(names(), before);
  console.log(`Payload of ${manifest.wheel} and ${manifest.parts.stack.wheel} in Pyodide ${version} (Python ${python}): install, request, `
    + 'reinstall, no request, learner globals, overlapping installs, damaged; no STACK engine on math pages; the STACK part, its requests, '
    + 'reinstall, damaged, version, missing ctm-checkers.js: ok');
  process.exit(0);
})().catch(error => { console.error(error); process.exit(1); });
