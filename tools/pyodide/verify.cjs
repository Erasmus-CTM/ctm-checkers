#!/usr/bin/env node
// The golden tables inside Pyodide, in Node: boots one Pyodide version with
// the umbrella's harness modules (ctm-assessment integration/pyodide-parity at
// the commit in tools/pins.json: runtime.cjs boots Pyodide, wheels.cjs loads
// SymPy, mpmath and NetworkX as that Pyodide version builds them, checked
// against its lock file), mounts this repository and the umbrella checkout
// (golden.py records authored rows with its authored_record.py) and runs
// `tools/golden.py verify` inside, with the same adapters as natively.
//
//   node tools/pyodide/verify.cjs --umbrella DIR --version 0.28.3 -- verify --adapter legacy --legacy DIR
//   node tools/pyodide/verify.cjs --umbrella DIR --version 0.28.3 --payload _extensions/ctm-checkers/ctm-checkers.js \
//     -- verify --adapter installed --variants DIR
//
// With --payload, the page script's own install code (CTMCheckers.install)
// installs the wheel first, through an object that offers only
// globals.set and runPythonAsync, as pyodide-interaktiv's worker proxy does.
//
// Paths after `--` are host paths; they are mounted into Pyodide's file
// system. The umbrella checkout needs `npm ci` in integration/pyodide-parity.
// PYODIDE_PARITY_WHEELS=<dir> serves the wheels from <dir>/<version>/ instead
// of jsDelivr (hashes are checked either way); PYODIDE_PARITY_CACHE: the wheel
// cache (default: a temporary folder).
'use strict';
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const vm = require('node:vm');

const ROOT = path.resolve(__dirname, '..', '..');

function parse(argv) {
  const split = argv.indexOf('--');
  const own = split < 0 ? argv : argv.slice(0, split);
  const golden = split < 0 ? [] : argv.slice(split + 1);
  const options = {umbrella: null, version: null, payload: null};
  for (let i = 0; i < own.length; i += 2) {
    const key = own[i].replace(/^--/, '');
    if (!(key in options) || own[i + 1] === undefined) throw new Error('Usage: see the header of verify.cjs');
    options[key] = own[i + 1];
  }
  if (!options.umbrella || !options.version || !golden.length) throw new Error('Usage: see the header of verify.cjs');
  return {...options, golden};
}

(async () => {
  const options = parse(process.argv.slice(2));
  const parity = path.join(path.resolve(options.umbrella), 'integration', 'pyodide-parity');
  const {boot} = require(path.join(parity, 'runtime.cjs'));
  const {ensureWheels} = require(path.join(parity, 'wheels.cjs'));
  const cache = process.env.PYODIDE_PARITY_CACHE || fs.mkdtempSync(path.join(os.tmpdir(), 'ctm-wheels-'));
  const wheels = await ensureWheels(options.version, cache);
  const {py, python} = await boot(options.version, wheels);
  py.setStdout({batched: line => console.log(line)});
  py.setStderr({batched: line => console.error(line)});
  await py.loadPackage('sympy');
  await py.loadPackage('networkx');
  console.log(`Pyodide ${options.version} (Python ${python}, SymPy ${py.runPython('import sympy; sympy.__version__')})`);
  if (options.payload) {
    const sandbox = {};
    vm.createContext(sandbox);
    vm.runInContext(fs.readFileSync(options.payload, 'utf8'), sandbox, {filename: options.payload});
    const checkers = sandbox.CTMCheckers;
    const proxy = {globals: {set: (name, value) => py.globals.set(name, value)}, runPythonAsync: code => py.runPythonAsync(code)};
    await checkers.install(proxy);
    console.log(`Installed ${checkers.wheel} (sha256 ${checkers.sha256}) with the payload's install code`);
  }

  // This repository, the umbrella checkout (golden.py records authored rows
  // with its authored_record.py) and every host path among the arguments, mounted.
  const mounts = new Map([[ROOT, '/ctm-checkers'], [fs.realpathSync(path.resolve(options.umbrella)), '/ctm-umbrella']]);
  const args = options.golden.map(arg => {
    if (arg.startsWith('-') || !fs.existsSync(arg)) return arg;
    const host = fs.realpathSync(arg);
    const stat = fs.statSync(host);
    const dir = stat.isDirectory() ? host : path.dirname(host);
    if (dir === ROOT || dir.startsWith(ROOT + path.sep)) return '/ctm-checkers' + host.slice(ROOT.length).split(path.sep).join('/');
    if (!mounts.has(dir)) mounts.set(dir, '/ctm-mount' + mounts.size);
    return mounts.get(dir) + (stat.isDirectory() ? '' : '/' + path.basename(host));
  });
  for (const [host, target] of mounts) {
    py.FS.mkdirTree(target);
    py.FS.mount(py.FS.filesystems.NODEFS, {root: host}, target);
  }
  py.globals.set('_ctm_golden_args', py.toPy(args));
  const code = await py.runPythonAsync([
    'import os, runpy, warnings',
    'os.environ["CTM_UMBRELLA"] = "/ctm-umbrella"',
    'warnings.simplefilter("ignore")',
    '_ctm_golden = runpy.run_path("/ctm-checkers/tools/golden.py", run_name="ctm_golden")',
    '_ctm_golden["main"](list(_ctm_golden_args))',
  ].join('\n'));
  process.exit(code);
})().catch(error => { console.error(error); process.exit(2); });
