#!/usr/bin/env python3
"""Golden verdict tables of ctm-checkers: verify, record, import (docs/goldens.md).

    python tools/golden.py verify --adapter legacy --legacy DIR [--suite NAME ...] [--max-diffs N]
    python tools/golden.py verify --adapter wheel|src|installed [--wheel FILE] [--variants DIR]
    python tools/golden.py record --legacy DIR
    python tools/golden.py import-capture CAPTURE --math-exercise CHECKOUT [--record-with PYTHON ...]

Authored rows are recorded with the umbrella's parity-harness recorder
(integration/pyodide-parity/authored_record.py at the commit in
tools/pins.json; --umbrella DIR or CTM_UMBRELLA, by default _ci/ctm-assessment).

The tables are tests/golden/<module>/<suite>.jsonl, one row per line,
{"suite", "id", "call", "input", "output" | "by_python", "tags"}, in
canonical JSON (sorted keys, compact separators, non-ASCII as is) and sorted
by id. "output" is the result on every platform; "by_python" holds one result
per Python minor version, for results that carry a Python message or differ
between versions. Checker and test sources are stored once per corpus in
sources-<corpus>.jsonl and referenced as {"$source": "<sha256>"}; files that
authored tests name are under files/. A number that JSON cannot hold is
{"$float": "NaN" | "Infinity" | "-Infinity"}.

Adapters (what runs the rows):
  legacy     math-exercise 0.10.0's own code, from a checkout (--legacy DIR,
             the commit in tools/pins.json): the Python array of
             math-exercise.js decoded as question-tests.py does, installed as
             the private module _ctm_math_exercise and called through
             _math_run with the request values as the page's globals, as
             math-exercise.js calls it; question-tests.py for the authored
             tests; variants.py for its rounding helpers.
  wheel      ctm-checkers from a wheel by zipimport, as builds use it
             (--wheel FILE; default: the one in _extensions/ctm-checkers/).
  src        ctm-checkers from src/.
  installed  the ctm_checkers that is importable (in Pyodide: installed by
             the payload's own install code, tools/pyodide/verify.cjs).
  With ctm-checkers, a request goes through browser.call as the page sends
  it: one JSON request whose fields are the _math_* values' names without
  the prefix (_math_response_json as the object "response"). variants.py
  stays in math-exercise: its rows run the variants.py of --variants DIR.

This file runs in native Python (3.9 or later) and inside Pyodide
(tools/pyodide/verify.cjs): standard library only; subprocesses only for
import-capture's --record-with.
"""
import argparse
import ast
import hashlib
import json
import math
import os
from pathlib import Path
import random
import re
import runpy
import shutil
import subprocess
import sys
import tempfile
import traceback
import types
import warnings

ROOT = Path(__file__).resolve().parents[1]
GOLDEN = ROOT / 'tests' / 'golden'
MINOR = '%d.%d' % sys.version_info[:2]
FORMAT = 1


# ---------------------------------------------------------------------------
# Canonical JSON (the same text as the umbrella's capture.cjs writes)
# ---------------------------------------------------------------------------

class Raw(str):
    """A JSON number exactly as it was written."""


def loads(text):
    """Strict JSON (NaN and Infinity are not JSON); numbers are kept as written."""
    def constant(name):
        raise ValueError('not JSON: ' + name)
    return json.loads(text, parse_int=Raw, parse_float=Raw, parse_constant=constant)


def _utf16(key):
    # JavaScript sorts object keys by UTF-16 code units.
    return key.encode('utf-16-be', 'surrogatepass')


def canonical(value):
    """Sorted keys, compact separators, non-ASCII as is; numbers as written
    (Raw) or as Python writes them; non-finite numbers as {"$float": ...}."""
    if isinstance(value, Raw):
        return str(value)
    if value is None or isinstance(value, bool):
        return json.dumps(value)
    if isinstance(value, str):
        return json.dumps(value, ensure_ascii=False)
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        if math.isfinite(value):
            return repr(value)
        return canonical({'$float': 'NaN' if value != value else ('Infinity' if value > 0 else '-Infinity')})
    if isinstance(value, (list, tuple)):
        return '[' + ','.join(canonical(item) for item in value) + ']'
    if isinstance(value, dict):
        return '{' + ','.join(json.dumps(key, ensure_ascii=False) + ':' + canonical(value[key])
                              for key in sorted(value, key=_utf16)) + '}'
    raise TypeError('not JSON: ' + type(value).__name__)


def row_id(call, input_value):
    return hashlib.sha256(canonical({'call': call, 'input': input_value}).encode('utf-8')).hexdigest()[:16]


def output_of(text):
    """A call's JSON text as the capture stores it: parsed with numbers as
    Python wrote them, or {"$unparsed": text} if it is not strict JSON."""
    try:
        return loads(text)
    except ValueError:
        return {'$unparsed': text}


def raised(error):
    """An exception as the page sees it: the last line of the traceback."""
    text = ''.join(traceback.format_exception(type(error), error, error.__traceback__))
    lines = [line for line in text.strip().split('\n') if line.strip()]
    return lines[-1] if lines else str(error)


def has_message(value):
    """True for a result that holds a Python message (kept per Python version)."""
    if isinstance(value, list):
        return any(has_message(item) for item in value)
    if not isinstance(value, dict):
        return False
    if value.get('status') in ('error', 'raised') or 'message' in value or 'raised' in value:
        return True
    if isinstance(value.get('outcome'), str) and value['outcome'] != 'pass':
        return True
    return any(has_message(item) for item in value.values())


# ---------------------------------------------------------------------------
# Tables
# ---------------------------------------------------------------------------

def table_files(root=GOLDEN):
    return sorted(p for p in root.rglob('*.jsonl') if not p.name.startswith('sources-') and 'files' not in p.relative_to(root).parts)


def read_rows(path):
    rows = []
    for number, line in enumerate(path.read_text(encoding='utf-8').splitlines(), 1):
        row = loads(line)
        if canonical(row) != line:
            raise SystemExit(f'{path}:{number}: not canonical JSON')
        rows.append(row)
    if [r['id'] for r in rows] != sorted(r['id'] for r in rows) or len({r['id'] for r in rows}) != len(rows):
        raise SystemExit(f'{path}: rows must be sorted by id, each id once')
    return rows


def write_rows(path, rows):
    rows = sorted(rows, key=lambda r: r['id'])
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(''.join(canonical(r) + '\n' for r in rows), encoding='utf-8')


def read_sources(root=GOLDEN):
    sources = {}
    for path in sorted(root.rglob('sources-*.jsonl')):
        for line in path.read_text(encoding='utf-8').splitlines():
            entry = json.loads(line)
            text = entry['text']
            if hashlib.sha256(text.encode('utf-8')).hexdigest() != entry['sha256']:
                raise SystemExit(f'{path}: source {entry["sha256"][:12]} does not match its text')
            sources[entry['sha256']] = text
    return sources


def expected_output(row, minor=MINOR):
    """(found, value): the row's result for this Python minor version."""
    if 'output' in row:
        return True, row['output']
    if minor in row['by_python']:
        return True, row['by_python'][minor]
    return False, None


# ---------------------------------------------------------------------------
# Inputs
# ---------------------------------------------------------------------------

FLOATS = {'NaN': float('nan'), 'Infinity': float('inf'), '-Infinity': float('-inf')}


def resolve(value, sources):
    """Sources by hash and non-finite numbers; other values unchanged."""
    if isinstance(value, dict) and set(value) == {'$source'}:
        return sources[value['$source']]
    if isinstance(value, dict) and set(value) == {'$float'}:
        return FLOATS[value['$float']]
    return value


def page_value(value, sources):
    """A request value as Pyodide received it from the page (py.globals.set):
    a JavaScript number is an int when it is a safe integer, else a float."""
    value = resolve(value, sources)
    if isinstance(value, Raw):
        number = float(value)
        return int(number) if number.is_integer() and abs(number) <= 2 ** 53 - 1 else number
    return value


def python_value(value, sources=None):
    """A value of a recorded row as Python wrote it (int or float literal)."""
    value = resolve(value, sources or {})
    if isinstance(value, Raw):
        return int(value) if re.fullmatch(r'-?[0-9]+', value) else float(value)
    if isinstance(value, list):
        return [python_value(item, sources) for item in value]
    return value


# ---------------------------------------------------------------------------
# Authored question tests: recorded by the umbrella's parity harness's own
# recorder, integration/pyodide-parity/authored_record.py (the one copy; the
# harness defines the capture), loaded from the ctm-assessment checkout at the
# commit in tools/pins.json, as tools/pyodide/verify.cjs loads runtime.cjs and
# wheels.cjs: --umbrella DIR or CTM_UMBRELLA, by default _ci/ctm-assessment.
# ---------------------------------------------------------------------------

RECORDER = 'integration/pyodide-parity/authored_record.py'
_recorder = None


def umbrella_folder():
    return Path(os.environ.get('CTM_UMBRELLA') or ROOT / '_ci' / 'ctm-assessment').resolve()


def use_umbrella(folder=None):
    """--umbrella DIR, else CTM_UMBRELLA, made absolute before anything changes
    the current folder (authored rows run in their question's folder), for
    record's subprocesses too."""
    folder = folder or os.environ.get('CTM_UMBRELLA')
    if folder:
        os.environ['CTM_UMBRELLA'] = str(Path(folder).resolve())


def recorder():
    """The umbrella's authored_record module (checked against the pin's sha256)."""
    global _recorder
    if _recorder is None:
        path = umbrella_folder() / RECORDER
        pin = json.loads((ROOT / 'tools' / 'pins.json').read_text(encoding='utf-8'))['ctm-assessment']
        if not path.is_file():
            raise SystemExit(f'{path}: not found. Authored rows are recorded with the umbrella\'s {RECORDER}: check out '
                             f'Erasmus-CTM/ctm-assessment at {pin["commit"][:12]} (tools/pins.json) into _ci/ctm-assessment, '
                             f'or give its folder with --umbrella or CTM_UMBRELLA')
        source = path.read_bytes()
        if hashlib.sha256(source).hexdigest() != pin['authored_record_sha256']:
            raise SystemExit(f'{path} is not the recorder of ctm-assessment {pin["commit"][:12]} (tools/pins.json): '
                             f'check out that commit')
        module = types.ModuleType('ctm_umbrella_authored_record')
        module.__file__ = str(path)
        exec(compile(source, str(path), 'exec'), module.__dict__)
        _recorder = module
    return _recorder


def authored_output(run_question, options, base):
    """An authored row's result: the umbrella's record() of the question, run
    in its source folder (as the harness runs it) and in canonical form."""
    record = recorder().record   # loaded before the folder changes: a relative CTM_UMBRELLA is relative to where golden.py runs
    here = os.getcwd()
    if Path(base).is_dir():
        os.chdir(base)
    try:
        result = record(run_question, options, base)
    finally:
        os.chdir(here)
    return loads(json.dumps(result, sort_keys=True, ensure_ascii=False, separators=(',', ':')))


# ---------------------------------------------------------------------------
# Adapters
# ---------------------------------------------------------------------------

LIBRARY = re.compile(r"var source = \[\n(.*?)\n    \]\.join\('\\n'\);", re.S)


def legacy_folder(path):
    # Absolute: authored tests run in their own folder (os.chdir).
    path = Path(path).resolve()
    for folder in (path, path / '_extensions' / 'math-exercise'):
        if (folder / 'math-exercise.js').is_file():
            return folder
    raise SystemExit(f'{path}: no math-exercise.js (give a math-exercise checkout or its _extensions/math-exercise folder)')


def legacy_library(folder):
    """The checker library in math-exercise.js, decoded as question-tests.py decodes it."""
    return decode_library((folder / 'math-exercise.js').read_text(encoding='utf-8'))


def decode_library(text):
    match = LIBRARY.search(text)
    if not match:
        raise SystemExit('Cannot locate the math-exercise Python bootstrap')
    lines = ast.literal_eval('[' + match[1] + ']')
    if not all(isinstance(line, str) for line in lines):
        raise SystemExit('Expected a literal Python bootstrap')
    return '\n'.join(lines)


class Legacy:
    """math-exercise 0.10.0's own code (see the module docstring)."""
    name = 'legacy'

    def __init__(self, path):
        self.folder = legacy_folder(path)
        self.library = legacy_library(self.folder)
        # As ctm-libs' installModule installs it on the page: a private module.
        module = types.ModuleType('_ctm_math_exercise')
        exec(self.library, module.__dict__)
        sys.modules['_ctm_math_exercise'] = module
        self.module = module
        self._question_tests = self._variants = None

    def describe(self):
        return {'adapter': self.name, 'library_sha256': hashlib.sha256(self.library.encode('utf-8')).hexdigest()}

    def runs(self, rows):
        return True

    def call(self, name, values):
        # math-exercise.js sets the values as the interpreter's globals and runs
        # `__import__("_ctm_math_exercise")._math_run("_math_<name>", globals())`.
        caller = dict(values)
        return self.module._math_run('_math_' + name, caller)

    def run_question(self, options, base):
        if self._question_tests is None:
            functions = runpy.run_path(str(self.folder / 'question-tests.py'), run_name='_ctm_question_tests')
            self._question_tests = (functions, functions['runtime_namespace']())
        functions, runtime = self._question_tests
        functions['run_question'](options, runtime, Path(base))

    def numeric(self, name, args):
        if name == 'round_places':
            return self.module._round_places(*args)
        if name == 'sigfigs_round':
            return self.module._sigfigs_round(*args)
        if self._variants is None:
            self._variants = runpy.run_path(str(self.folder / 'variants.py'), run_name='_ctm_variants')
        return self._variants[name.split('.', 1)[1]](*args)


# The request fields of browser.call for the values math-exercise.js set.
REQUEST_FIELDS = {'_math_student': 'student', '_math_correct': 'correct', '_math_vars': 'vars', '_math_mode': 'mode',
                  '_math_reject': 'reject', '_math_tolerance': 'tolerance', '_math_decplaces': 'decplaces',
                  '_math_sigfigs': 'sigfigs', '_math_form': 'form', '_math_partial_credit': 'partial_credit',
                  '_math_form_credit': 'form_credit', '_math_response_json': 'response', '_math_checker': 'checker'}


def default_wheel():
    folder = ROOT / '_extensions' / 'ctm-checkers'
    manifest = json.loads((folder / 'checkers.json').read_text(encoding='utf-8'))
    return folder / manifest['wheel']


class CtmCheckers:
    """ctm-checkers (see the module docstring)."""

    def __init__(self, mode, wheel=None, variants=None):
        import importlib
        self.name = mode
        location = None
        if mode == 'src':
            location = ROOT / 'src'
        elif mode == 'wheel':
            location = Path(wheel).resolve() if wheel else default_wheel()
        elif mode != 'installed':
            raise SystemExit('Unknown adapter: ' + mode)
        if location is not None:
            if not location.exists():
                raise SystemExit(f'{location}: not found')
            for name in [n for n in sys.modules if n == 'ctm_checkers' or n.startswith('ctm_checkers.')]:
                del sys.modules[name]
            sys.path.insert(0, str(location))
        package = importlib.import_module('ctm_checkers')
        if location is not None and not os.path.abspath(package.__file__).startswith(os.path.abspath(str(location)) + os.sep):
            raise SystemExit(f'ctm_checkers was imported from {package.__file__}, not from {location}')
        self.package = package
        self.browser = importlib.import_module('ctm_checkers.browser')
        self.authored = importlib.import_module('ctm_checkers.math_exercise.authored')
        self.rounding = importlib.import_module('ctm_checkers.math_exercise.numeric')
        self.variants_folder = legacy_folder(variants) if variants else None
        self._variants = None

    def describe(self):
        return {'adapter': self.name, 'version': self.package.__version__, 'file': self.package.__file__,
                'variants': str(self.variants_folder) if self.variants_folder else None}

    def runs(self, rows):
        # variants.py stays in math-exercise: its rows need --variants.
        return bool(self.variants_folder) or not any(row['call'].startswith('variants.') for row in rows)

    def call(self, name, values):
        request = {REQUEST_FIELDS[key]: (json.loads(value) if key == '_math_response_json' else value)
                   for key, value in values.items()}
        caller = {'_ctm_request': json.dumps(request, allow_nan=False)}
        try:
            return self.browser.call('math_exercise.' + name, caller)
        finally:
            if '_ctm_request' in caller:
                raise AssertionError('browser.call left the request in the namespace')

    def run_question(self, options, base):
        self.authored.run_question(options, Path(base))

    def numeric(self, name, args):
        if name == 'round_places':
            return self.rounding.round_places(*args)
        if name == 'sigfigs_round':
            return self.rounding.sigfigs_round(*args)
        if self._variants is None:
            self._variants = runpy.run_path(str(self.variants_folder / 'variants.py'), run_name='_ctm_variants')
        return self._variants[name.split('.', 1)[1]](*args)


def make_adapter(options):
    if options.adapter == 'legacy':
        if not options.legacy:
            raise SystemExit('--adapter legacy needs --legacy DIR (a math-exercise checkout at the commit in tools/pins.json)')
        return Legacy(options.legacy)
    return CtmCheckers(options.adapter, options.wheel, options.variants)


# ---------------------------------------------------------------------------
# Running rows
# ---------------------------------------------------------------------------

# Rounding calls and their arguments, in order.
NUMERIC = {'round_places': ('x', 'd'), 'sigfigs_round': ('x', 'n'),
           'variants.round_half_up': ('x', 'digits'), 'variants.sigfig': ('x', 'n')}


def run_row(adapter, row, sources):
    """The row's result with this adapter, in the form the table stores."""
    call, value = row['call'], row['input']
    if call in ('check', 'check_custom'):
        values = {key: page_value(item, sources) for key, item in value.items()}
        random.seed(0)   # as the harness seeds it before each grading call
        try:
            return output_of(adapter.call(call, values))
        except Exception as error:
            return {'raised': raised(error)}
    if call == 'authored':
        options = {key: resolve(item, sources) for key, item in value['options'].items()}
        return authored_output(adapter.run_question, options, GOLDEN / 'math_exercise' / 'files')
    if call in NUMERIC:
        args = [python_value(value[key]) for key in NUMERIC[call]]
        try:
            result = adapter.numeric(call, args)
        except Exception as error:
            return {'raised': raised(error)}
        return loads(canonical({'value': result}))
    raise SystemExit('Unknown call: ' + call)


def annotate(path, message):
    # In GitHub Actions, a difference is an error annotation on the table (readable without the log).
    if os.environ.get('GITHUB_ACTIONS') == 'true':
        text = message.replace('%', '%25').replace('\r', '%0D').replace('\n', '%0A')
        print(f'::error file={path.relative_to(ROOT).as_posix()},title=Golden row differs::{text}', flush=True)


def selected(files, patterns):
    if not patterns:
        return files
    return [f for f in files if any(re.search(p, f.relative_to(GOLDEN).as_posix()) for p in patterns)]


def verify(adapter, patterns=(), max_diffs=20, out=print):
    """Runs every row; returns the number of rows that do not reproduce."""
    sources = read_sources()
    failures = total = 0
    # Deprecation warnings of SymPy (set up when it is imported) are not results.
    warnings.simplefilter('ignore')
    out(f'Golden tables with {adapter.name} on Python {sys.version.split()[0]} ({sys.platform}): '
        + json.dumps(adapter.describe(), sort_keys=True))
    pythons = read_manifest().get('python', {})
    known = sorted(set(pythons.get('captured', [])) | set(pythons.get('recorded', [])), key=version_key)
    unknown = MINOR not in known
    if unknown:
        out(f'Python {MINOR} has no results of its own in the tables (recorded: {", ".join(known)}): the rows that keep '
            f'results per version count as missing. Verify with one of those versions, or record this one (tools/golden.py record).')
    skipped = []
    for path in selected(table_files(), patterns):
        rows = read_rows(path)
        if not adapter.runs(rows):
            skipped.append(path.relative_to(GOLDEN).as_posix())
            out(f'{skipped[-1]}: {len(rows)} rows; skipped: they run math-exercise\'s variants.py (--variants DIR)')
            continue
        counts = {'reproduced': 0, 'different': 0, 'missing': 0}
        for row in rows:
            found, expected = expected_output(row)
            if not found:
                counts['missing'] += 1
                failures += 1
                if failures <= max_diffs and not unknown:
                    out(f'  missing {row["suite"]} {row["id"]}: no result for Python {MINOR}')
                continue
            actual = run_row(adapter, row, sources)
            if canonical(actual) == canonical(expected):
                counts['reproduced'] += 1
                continue
            counts['different'] += 1
            failures += 1
            if failures <= max_diffs:
                out(f'  DIFFERENT {row["suite"]} {row["id"]} ({row["call"]})\n    expected {canonical(expected)[:600]}\n    actual   {canonical(actual)[:600]}')
                annotate(path, f'{row["suite"]} {row["id"]} ({row["call"]}) on Python {MINOR}: expected {canonical(expected)[:900]} '
                               f'| actual {canonical(actual)[:900]} | input {canonical(row["input"])[:600]}')
        total += len(rows)
        out(f'{path.relative_to(GOLDEN).as_posix()}: {len(rows)} rows; ' + ', '.join(f'{k} {v}' for k, v in counts.items()))
    out(f'{total} rows, {total - failures} reproduced, {failures} not.' + (f' Skipped: {", ".join(skipped)}.' if skipped else ''))
    return failures


# ---------------------------------------------------------------------------
# Recording
# ---------------------------------------------------------------------------

# The probe of the `#| checker:` namespace (suite math_exercise/namespace):
# a custom checker that reports the public names it sees with their origins,
# and the current request's values (step-2 design §2.3, §13).
NAMESPACE_PROBE = '''_ctm_probe_names = dict(globals())

def check(response, symbols):
    import types as _types
    def origin(value):
        if isinstance(value, _types.ModuleType):
            return "module " + value.__name__
        if isinstance(value, type) or callable(value):
            module = getattr(value, "__module__", None)
            name = getattr(value, "__qualname__", None) or getattr(value, "__name__", None)
            if isinstance(module, str) and isinstance(name, str):
                if module == "_ctm_math_exercise" or module.split(".")[0] == "ctm_checkers":
                    module = "(library)"
                return module + "." + name
        return "instance of " + type(value).__module__ + "." + type(value).__qualname__
    names = {name: origin(value) for name, value in _ctm_probe_names.items() if not name.startswith("_")}
    values = {name: _ctm_probe_names.get(name) for name in ("_math_response_json", "_math_vars", "_math_checker")}
    return {"score": 1.0, "show_score": False, "feedback": "",
            "assessment": {"names": names, "request": values, "symbols": sorted(symbols)}}
'''


def namespace_rows():
    response = json.dumps({'kind': 'expressions', 'raw': ['x + y'], 'inputs': {}}, separators=(',', ':'))
    value = {'_math_checker': NAMESPACE_PROBE, '_math_response_json': response, '_math_vars': 'x y'}
    return [{'suite': 'math_exercise/namespace', 'id': row_id('check_custom', value), 'call': 'check_custom',
             'input': value, 'tags': ['namespace']}]


GRID = [0.0, -0.0, 0.5, 1.5, 2.5, -0.5, -1.5, -2.5, 0.125, 0.375, -0.125, 1.005, 2.675, 5.395, 1.05 * 1.9,
        0.045, 1.115, 8.345, 0.1 + 0.2, 1 / 3, 2 / 3, -2 / 3, 12345.6785, 99.995, 9.995, 0.995,
        123456789.125, 1e-7, 2.5e-7, 1.25e-5, -3.14159265358979, 2.718281828459045, 1e15 + 0.5, 1e16,
        1e30, -1e30, 1.5e300, 5e-324, 1e-300, 7.0, -7.0, 1234.0, float('inf'), float('-inf'), float('nan'),
        3, -3, 0, 12345, -98765, 10 ** 20]


def grid_rows(suite, calls):
    out = {}
    for x in GRID:
        for call, argument, values in calls:
            for value in values:
                row = loads(canonical({'x': x, argument: value}))   # numbers as Python writes them
                out.setdefault(row_id(call, row), {'suite': suite, 'id': row_id(call, row), 'call': call, 'input': row, 'tags': ['rounding']})
    return list(out.values())


def numeric_grid():
    """The rounding rule of the checks (round_places, sigfigs_round) on a grid
    of ties at many places, binary noise, negatives, large and small
    magnitudes, integers and non-finite values."""
    return grid_rows('math_exercise/rounding', [('round_places', 'd', (-2, -1, 0, 1, 2, 3, 4, 6, 10, 15, 20, 30)),
                                                ('sigfigs_round', 'n', (1, 2, 3, 4, 6, 10, 15, 17))])


def variants_grid():
    """The same grid through math-exercise's variants.py (round_half_up,
    sigfig), which stays in math-exercise and rounds by the same rule."""
    return grid_rows('math_exercise/rounding-variants', [('variants.round_half_up', 'digits', (None, -1, 0, 1, 2, 3, 6)),
                                                         ('variants.sigfig', 'n', (1, 2, 3, 6))])


def supplement_rows():
    """Requests for branches that the captured examples do not reach (the
    reject rule, form credit, the custom-result rules and their errors,
    matrix dimensions, the dunder rule on every learner string, the request
    values a checker sees), in math-exercise.js's request form."""
    def check(student, correct, mode='equivalent', vars='', reject='', tolerance='', decplaces='', sigfigs='', form='',
              partial=False, credit=0.5):
        return 'check', {'_math_student': student, '_math_correct': correct, '_math_vars': vars, '_math_mode': mode,
                         '_math_reject': reject, '_math_tolerance': tolerance, '_math_decplaces': decplaces,
                         '_math_sigfigs': sigfigs, '_math_form': form, '_math_partial_credit': partial, '_math_form_credit': credit}

    def custom(checker, response=None, vars='', text=None):
        # `text`: the response as the page's JSON.stringify wrote it, where Python would spell a number otherwise.
        if response is None:
            response = {'kind': 'expressions', 'raw': ['x'], 'inputs': {}}
        return 'check_custom', {'_math_checker': checker, '_math_vars': vars,
                                '_math_response_json': text if text is not None else json.dumps(response, separators=(',', ':'))}

    def returns(expression):
        return 'def check(response, symbols):\n    return ' + expression + '\n'

    matrix = {'kind': 'expressions', 'raw': ['1', '2', '3', '4'],
              'inputs': {'M': {'type': 'matrix', 'rows': 2, 'cols': 2, 'raw': ['1', '2', '3', '4']}}}
    dependent = {'kind': 'expressions', 'raw': ['1', '2', '2', '4'],
                 'inputs': {'M': {'type': 'matrix', 'rows': 2, 'cols': 2, 'raw': ['1', '2', '2', '4']}}}
    requests = [
        check('(x+1)^2', 'x^2+2*x+1', vars='x', reject='(x+1)^2'),
        check('x^2+2*x+1', 'x^2+2*x+1', vars='x', reject='(x+1)^2'),
        check('2/4', '1/2', mode='exact', partial=True),
        check('2/4', '1/2', mode='exact'),
        check('1/4 + 2/4', '3/4', mode='exact', partial=True, credit=1),
        check('(x+1)^2', 'x^2+2*x+1', mode='exact', vars='x', partial=True, credit=0.25),
        check('x^2-1', '(x-1)*(x+1)', vars='x', form='factored', partial=True, credit=1),
        check('(x-1)*(x+1)', 'x^2-1', vars='x', form='factored'),
        check('2/4', '1/2', form='lowest_terms', partial=True),
        check('x/(2*x)', '1/2', vars='x', form='lowest_terms'),
        check('1/x + 1/y', '(x+y)/(x*y)', vars='x y', form='single_fraction', partial=True),
        check('(x+1)^2', 'x^2+2*x+1', vars='x', form='expanded', partial=True, credit=0),
        check('sqrt(-1)', '1', mode='numeric'),
        check('101', '100', mode='numeric', tolerance='1%'),
        check('102', '100', mode='numeric', tolerance='1%'),
        check('5.395', '5.40', mode='numeric', decplaces='2'),
        check('1.005', '1.01', mode='numeric', decplaces='2'),
        check('12345', '12300', mode='numeric', sigfigs='3'),
        check('0.00012346', '0.000123456', mode='numeric', sigfigs='4'),
        check('1.000000001', '1', mode='numeric'),
        check('1.0001', '1', mode='numeric'),
        check('pi', '3.14159', mode='numeric', tolerance='0.00001'),
        check('1, 2, 3', '1, 2', mode='set', partial=True),
        check('1, 2, 3', '1, 2', mode='set'),
        check('1', '1, 2', mode='set', partial=True),
        check('2, 1', '1, 2', mode='set'),
        check('0.333333333333, 1', '1/3, 1', mode='set'),
        check('(1, 2), 3', '3, (1, 2)', mode='set'),
        check('Hello', 'hello', mode='string_ci'),
        check('Hello', 'hello', mode='string'),
        check('__import__("os")', '__import__("os")', mode='string'),
        check('inf', 'oo'),
        check('a*b', 'b*a', vars='a, b'),
        check('x+', 'x', vars='x'),
        check('x', '', vars='x'),
        check('x.__class__', 'x', vars='x'),
        check('sin(x)^2+cos(x)^2', '1', vars='x', reject='sin(x)^2+cos(x)^2'),
        custom(''),
        custom('answer = 1\n'),
        custom(returns('2')),
        custom(returns('"yes"')),
        custom(returns('{}')),
        custom(returns('{"correct": True, "feedback": "ok"}')),
        custom(returns('{"correct": 0}')),
        custom(returns('{"score": 0.5, "assessment": []}')),
        custom(returns('{"score": 1e-10, "show_score": 0}')),
        custom(returns('{"score": 0.9999999999}')),
        custom(returns('True')),
        custom(returns('False')),
        custom(returns('0.25')),
        custom(returns('1')),
        custom(returns('{"score": "0.5", "feedback": 7, "assessment": {"M": {"rows": ["correct"]}}}')),
        custom('def check(response, symbols):\n    raise ValueError("checker failed")\n'),
        custom(returns('{"score": 1.0, "feedback": repr(response)}'), matrix),
        custom(returns('{"score": 1.0, "feedback": repr(response)}'),
               {'kind': 'expressions', 'raw': ['1'], 'inputs': {'M': {'type': 'matrix', 'rows': 1, 'cols': 2, 'raw': ['1']}}}),
        custom(returns('{"score": 1.0, "feedback": repr(response)}'),
               {'kind': 'expressions', 'raw': [], 'inputs': {'M': {'type': 'matrix', 'rows': -1, 'cols': 2, 'raw': []}}}),
        custom(returns('{"score": 1.0, "feedback": repr(response)}'), [1, 2, 3]),
        custom(returns('{"score": 1.0, "feedback": repr(response)}'), {'kind': 'graph', 'raw': ['__x'], 'nodes': []}),
        custom(returns('True'), {'kind': 'expressions', 'raw': ['x.__class__'], 'inputs': {}}),
        custom(returns('True'), {'kind': 'expressions', 'raw': ['1'],
                                 'inputs': {'M': {'type': 'matrix', 'rows': 1, 'cols': 1, 'raw': ['__import__("os")']}}}),
        custom(returns('{"score": 1.0, "feedback": repr((floor(2.7), gcd(12, 18), log10(1000)))}')),
        custom(returns('{"score": 1.0, "feedback": " | ".join([_math_vars, _math_response_json, str(len(_math_checker))])}'),
               vars='x y'),
        custom(returns('{"score": 1.0, "feedback": repr(sorted((k, repr(v), type(v).__name__) for k, v in symbols.items()))}'),
               vars='x, y z inf'),
        custom(returns('{"score": 1.0, "feedback": repr(graph_from_response({"representation": "undirected-graph", '
                       '"nodes": [{"id": 1, "x": 0, "y": 0}], "edges": [[1, 1]]}))}')),
        custom(returns('{"score": 1.0, "feedback": repr(sorted(graph_from_response({"representation": "directed-graph", '
                       '"nodes": [{"id": 1, "x": 0, "y": 0}, {"id": 2, "x": 1, "y": 1}], "edges": [[1, 2]]}, directed=True).edges()))}')),
        custom('def check(response, symbols):\n    return assess_basis(response["inputs"]["M"]["matrix"], axis="columns", '
               'target_dimension=2, belongs=lambda v: True, name="M")\n', matrix),
        custom('def check(response, symbols):\n    return assess_basis(response["inputs"]["M"]["matrix"], axis="rows", '
               'target_dimension=0, belongs=lambda v: True, name="M", space_name="null space")\n', matrix),
        custom('def check(response, symbols):\n    return assess_basis(response["inputs"]["M"]["matrix"], axis="diagonal", '
               'target_dimension=1, belongs=lambda v: True, name="M")\n', matrix),
        custom(returns('{"score": 1.0, "feedback": repr(parse_expr("2x", transformations=standard_transformations '
                       '+ (implicit_multiplication_application, convert_xor)))}')),
        # Rules the examples do not reach (review of C1, S1):
        # the equivalence tolerance (1e-10: a difference of 3.6e-9 is wrong) and the set tolerance (1e-8);
        check('3.14159265', 'pi'),
        check('3.14159265, 1', 'pi, 1', mode='set'),
        check('3.1415926, 1', 'pi, 1', mode='set', partial=True),
        # the default numeric tolerance 1e-8 * max(1, |key|) for small keys;
        check('5e-9', '0', mode='numeric'),
        check('2e-8', '0', mode='numeric'),
        check('1.000000005e-3', '1e-3', mode='numeric'),
        # the imaginary part in numeric mode;
        check('sqrt(-1)', '0', mode='numeric'),
        check('1 + 1e-10*I', '1', mode='numeric'),
        # inf is oo unless it is a variable;
        check('1/inf', '0'),
        custom(returns('{"score": 1.0, "feedback": repr(response["expressions"])}'),
               {'kind': 'expressions', 'raw': ['inf', '-inf', '1/inf'], 'inputs': {}}),
        # brackets and braces keep their commas in set answers;
        check('[1, 2], 3', '3, [1, 2]', mode='set'),
        check('{1, 2}, 3', '3, {1, 2}', mode='set'),
        check('Matrix([1, 2]), 3', '3, Matrix([1, 2])', mode='set'),
        # an undirected graph's [1, 2] and [2, 1] are one edge (a duplicate), a directed graph's two;
        custom(returns('{"score": 1.0, "feedback": repr(graph_from_response({"representation": "undirected-graph", '
                       '"nodes": [{"id": 1, "x": 0, "y": 0}, {"id": 2, "x": 1, "y": 1}], "edges": [[1, 2], [2, 1]]}))}')),
        custom(returns('{"score": 1.0, "feedback": repr(sorted(graph_from_response({"representation": "directed-graph", '
                       '"nodes": [{"id": 1, "x": 0, "y": 0}, {"id": 2, "x": 1, "y": 1}], "edges": [[1, 2], [2, 1]]}, directed=True).edges()))}')),
        # assess_basis scores dependent vectors by its independence factor.
        custom('def check(response, symbols):\n    return assess_basis(response["inputs"]["M"]["matrix"], axis="columns", '
               'target_dimension=2, belongs=lambda v: True, name="M")\n', dependent),
        # Rules that only the round-2 review's mutations reached: an imaginary part between 1e-9 and 1e-3 is rejected;
        check('1 + 1e-6*I', '1', mode='numeric'),
        # graph node ids are integers, not booleans;
        custom(returns('{"score": 1.0, "feedback": repr(sorted(graph_from_response(response).nodes()))}'),
               {'representation': 'undirected-graph', 'nodes': [{'id': True, 'x': 0, 'y': 0}, {'id': False, 'x': 1, 'y': 1}],
                'edges': [[True, False]]}),
        # _math_response_json spells numbers as JSON.stringify does: positional from 1e-6 to below 1e21.
        custom(returns('{"score": 1.0, "feedback": _math_response_json}'), text=(
            '{"representation":"undirected-graph","nodes":[{"id":1,"x":0.000001,"y":1e-7},{"id":2,"x":-1.5e-7,"y":0.0000015}],'
            '"edges":[],"scale":[100000000000000000000,1e+21,1.23e-18,0.1,123456.789]}')),
    ]
    out = {}
    for call, value in requests:
        value = loads(canonical(value))
        out.setdefault(row_id(call, value), {'suite': 'math_exercise/requests-supplement', 'id': row_id(call, value),
                                             'call': call, 'input': value, 'tags': ['supplement']})
    return list(out.values())


RECORDED = {'math_exercise/namespace': namespace_rows, 'math_exercise/rounding': numeric_grid,
            'math_exercise/rounding-variants': variants_grid, 'math_exercise/requests-supplement': supplement_rows}


def suite_path(suite):
    return GOLDEN / (suite + '.jsonl')


def record(adapter, out=print):
    """Adds this Python's results with the legacy code. The recorded suites
    are created if absent. A row kept per version gains this version's result.
    A row with one result that this version does not reproduce becomes per
    version: a platform difference of today's code, reported. A result that
    differs from one this version already has (or, for a captured row, from
    the Pyodide build of the same version) is a conflict: nothing is changed
    for that row and the command fails."""
    sources = read_sources()
    manifest = read_manifest()
    environment = record_environment(manifest)
    warnings.simplefilter('ignore')
    pythons = manifest.setdefault('python', {})
    pythons.setdefault('environments', {})[MINOR] = environment
    captured = pythons.setdefault('captured', [])
    recorded_before = list(pythons.setdefault('recorded', []))
    recorded = manifest.setdefault('recorded', {})
    findings, conflicts, created = [], [], set()
    for suite, make in RECORDED.items():
        path = suite_path(suite)
        if path.exists():
            continue
        rows = []
        for row in make():
            result = run_row(adapter, row, sources)
            if has_message(result):
                row['by_python'] = {MINOR: result}
            else:
                row['output'] = result
            rows.append(row)
        write_rows(path, rows)
        recorded[suite] = {'python': [MINOR], 'rows': len(rows)}
        created.add(suite)
        out(f'{suite}: recorded {len(rows)} rows on Python {MINOR}')
    for path in table_files():
        rows = read_rows(path)
        suite = rows[0]['suite'] if rows else ''
        if suite in created:
            continue
        # The versions a single result stands for.
        single = recorded[suite]['python'] if suite in recorded else sorted(set(captured) | set(recorded_before), key=version_key)
        changed = False
        for row in rows:
            result = run_row(adapter, row, sources)
            if 'output' in row:
                if canonical(result) == canonical(row['output']):
                    continue
                if MINOR in single:
                    conflicts.append((row, row['output'], result))
                    continue
                row['by_python'] = {version: row['output'] for version in single}
                del row['output']
                row['by_python'][MINOR] = result
                findings.append(row)
                changed = True
            elif MINOR in row['by_python']:
                if canonical(result) != canonical(row['by_python'][MINOR]):
                    conflicts.append((row, row['by_python'][MINOR], result))
            else:
                row['by_python'][MINOR] = result
                changed = True
        if changed:
            write_rows(path, rows)
        if suite in recorded and MINOR not in recorded[suite]['python']:
            recorded[suite]['python'] = sorted(recorded[suite]['python'] + [MINOR], key=version_key)
    for row in findings:
        others = sorted(set(row['by_python']) - {MINOR}, key=version_key)
        out(f'PLATFORM DIFFERENCE {row["suite"]} {row["id"]}: Python {MINOR} differs from {", ".join(others)}; kept per version:\n'
            f'    {MINOR}: {canonical(row["by_python"][MINOR])[:600]}\n    {others[0]}: {canonical(row["by_python"][others[0]])[:600]}')
    for row, before, result in conflicts:
        out(f'CONFLICT {row["suite"]} {row["id"]}: Python {sys.version.split()[0]} gives\n    {canonical(result)[:600]}\n'
            f'  where the table has for {MINOR}\n    {canonical(before)[:600]}')
    if MINOR not in pythons['recorded']:
        pythons['recorded'] = sorted(pythons['recorded'] + [MINOR], key=version_key)
    write_manifest(manifest)
    out(f'Recorded on Python {sys.version.split()[0]}: {len(findings)} platform differences, {len(conflicts)} conflicts.')
    return len(conflicts)


def version_key(version):
    return tuple(int(part) for part in version.split('.'))


def record_environment(manifest):
    """The packages of this interpreter; SymPy must be the version the capture ran."""
    import mpmath
    import sympy
    try:
        import networkx
        networkx_version = networkx.__version__
    except ImportError:
        networkx_version = None
    runtimes = ' '.join(run.get('runtime') or '' for run in manifest.get('capture', {}).get('runs') or [])
    wanted = sorted(set(re.findall(r'SymPy ([0-9.]+)', runtimes)))
    if wanted and wanted != [sympy.__version__]:
        raise SystemExit(f'Record with SymPy {", ".join(wanted)} (the capture\'s), not {sympy.__version__}: pip install -r ci/requirements.txt')
    if networkx_version is None:
        raise SystemExit('Record with NetworkX (graph checkers): pip install -r ci/requirements.txt')
    return {'python': sys.version.split()[0], 'sympy': sympy.__version__, 'mpmath': mpmath.__version__, 'networkx': networkx_version}


def read_manifest():
    path = GOLDEN / 'manifest.json'
    return json.loads(path.read_text(encoding='utf-8')) if path.exists() else {'format': FORMAT}


def write_manifest(manifest):
    (GOLDEN / 'manifest.json').write_text(json.dumps(manifest, indent=1, sort_keys=True, ensure_ascii=False) + '\n', encoding='utf-8')


# ---------------------------------------------------------------------------
# Importing the umbrella's capture
# ---------------------------------------------------------------------------

CAPTURED_KINDS = ('requests', 'custom-probes', 'authored', 'sources')
# The legacy files the tables run (the extension folder of math-exercise 0.10.0).
LEGACY_FILES = ('math-exercise.js', 'question-tests.py', 'variants.py')


def capture_files(capture):
    """The exported files {path relative to export/: bytes} and their manifest
    (its "files" keyed the same way) of a capture: a folder written by
    run.cjs --capture (export/ inside), or the goldens-export artifact (the
    export/ folder itself), as a folder or zip."""
    capture = Path(capture)
    files = {}
    if capture.is_file():
        import zipfile
        with zipfile.ZipFile(capture) as archive:
            for name in archive.namelist():
                if not name.endswith('/'):
                    files[name] = archive.read(name)
    else:
        for path in capture.rglob('*'):
            if path.is_file():
                files[path.relative_to(capture).as_posix()] = path.read_bytes()
    if 'export/manifest.json' in files:
        # run.cjs --capture: export/ has a manifest of its own.
        exported = {name[len('export/'):]: data for name, data in files.items() if name.startswith('export/')}
    elif 'manifest.json' in files and any(name.startswith('export/') for name in files):
        # An older capture: one manifest for both sides, paths with export/.
        manifest = json.loads(files['manifest.json'])
        manifest['files'] = {name[len('export/'):]: info for name, info in manifest.get('files', {}).items() if name.startswith('export/')}
        manifest['corpora'] = {name: info for name, info in manifest.get('corpora', {}).items() if info.get('export')}
        exported = {name[len('export/'):]: data for name, data in files.items() if name.startswith('export/')}
        exported['manifest.json'] = json.dumps(manifest).encode('utf-8')
    else:
        exported = files   # the artifact goldens-export
    if 'manifest.json' not in exported:
        raise SystemExit(f'{capture}: no manifest.json (expected the output of run.cjs --capture or the goldens-export artifact)')
    manifest = json.loads(exported.pop('manifest.json'))
    return exported, manifest


def git_show(checkout, commit, path):
    return subprocess.run(['git', '-C', str(checkout), 'show', f'{commit}:{path}'], check=True, capture_output=True).stdout


def import_capture(options, out=print):
    exported, captured = capture_files(options.capture)
    if captured.get('format') != FORMAT:
        raise SystemExit('Unknown capture format: ' + str(captured.get('format')))
    corpora = {name: info for name, info in captured.get('corpora', {}).items() if info.get('export')}
    if set(corpora) != {'math-exercise'}:
        raise SystemExit('Only math-exercise\'s own examples may be committed here (step-2 design §13 item 7); exported corpora: ' + ', '.join(sorted(corpora)))
    tables = {}
    for name, data in sorted(exported.items()):
        if name == 'PROVENANCE.md':
            continue
        match = re.fullmatch(r'math_exercise/(%s)-math-exercise\.jsonl' % '|'.join(CAPTURED_KINDS), name)
        info = captured.get('files', {}).get(name, {})
        if not match or not info.get('export') or info.get('corpus') != 'math-exercise':
            raise SystemExit(f'Unexpected exported file {name}: not a math-exercise suite marked for export')
        tables[name] = data.decode('utf-8')
    for kind in ('requests', 'custom-probes', 'authored', 'sources'):
        if f'math_exercise/{kind}-math-exercise.jsonl' not in tables:
            raise SystemExit(f'The capture has no {kind} suite for math-exercise')
    # Rows must be canonical and re-serialize byte for byte.
    for name, text in tables.items():
        for line in text.splitlines():
            if canonical(loads(line)) != line:
                raise SystemExit(f'{name}: a row does not re-serialize identically: {line[:200]}')
    commit = corpora['math-exercise'].get('commit')
    if not commit:
        raise SystemExit('The capture does not name the math-exercise commit')
    # The legacy code (the commit in tools/pins.json) must be the code the capture ran.
    pins = json.loads((ROOT / 'tools' / 'pins.json').read_text(encoding='utf-8'))
    pin = pins['math-exercise']['commit']
    checkout = Path(options.math_exercise)
    for sha in (commit, pin):
        if subprocess.run(['git', '-C', str(checkout), 'cat-file', '-e', sha + '^{commit}'], capture_output=True).returncode:
            raise SystemExit(f'{checkout} does not contain math-exercise {sha[:12]}: fetch it first (git -C {checkout} fetch origin)')
    for name in LEGACY_FILES:
        # math-exercise.js: its checker library; the other files as they are.
        at = [git_show(checkout, sha, '_extensions/math-exercise/' + name) for sha in (commit, pin)]
        if name == 'math-exercise.js':
            at = [decode_library(data.decode('utf-8')) for data in at]
        if at[0] != at[1]:
            raise SystemExit(f'math-exercise {name} at the captured commit {commit[:12]} differs from the legacy pin {pin[:12]}')
    legacy_dir = Path(tempfile.mkdtemp(prefix='ctm-legacy-'))
    for name in LEGACY_FILES:
        (legacy_dir / name).write_bytes(git_show(checkout, pin, '_extensions/math-exercise/' + name))
    legacy = Legacy(legacy_dir)
    # Replace the captured suites (and their sources) and the recorded ones.
    folder = GOLDEN / 'math_exercise'
    if folder.exists():
        shutil.rmtree(folder)
    folder.mkdir(parents=True)
    for name, text in tables.items():
        (GOLDEN / name).write_text(text, encoding='utf-8')
    # Files that authored tests name (`#| tests: path.py`), at the captured commit.
    sources = read_sources()
    named = set()
    for row in read_rows(folder / 'authored-math-exercise.jsonl'):
        tests = resolve(row['input']['options'].get('tests', ''), sources)
        if '\n' not in tests and tests.endswith('.py'):
            named.add(tests)
    for name in sorted(named):
        target = folder / 'files' / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(git_show(checkout, commit, name))
    manifest = {'format': FORMAT,
                'capture': {'harness': captured.get('harness'), 'umbrella': captured.get('umbrella'),
                            'runs': captured.get('runs'), 'components': captured.get('components'),
                            'corpus': corpora['math-exercise'],
                            'files': {name: captured['files'][name] for name in sorted(tables)}},
                'legacy': {'math-exercise': pin,
                           'library_sha256': hashlib.sha256(legacy.library.encode('utf-8')).hexdigest()},
                'files': sorted(named),
                'python': {'captured': sorted({minor_of(run.get('runtime') or '') for run in captured.get('runs') or []} - {''}, key=version_key),
                           'recorded': []},
                'recorded': {}}
    write_manifest(manifest)
    out(f'Imported {", ".join(f"{name} ({len(text.splitlines())} rows)" for name, text in sorted(tables.items()))} '
        f'and {len(named)} files authored tests name, captured at math-exercise {commit[:12]} by umbrella {str(captured.get("umbrella"))[:12]}.')
    try:
        problems = record(legacy, out)
        for python in options.record_with:
            out(f'Recording with {python} ...')
            result = subprocess.run([python, str(Path(__file__).resolve()), 'record', '--legacy', str(legacy_dir)])
            problems += result.returncode != 0
    finally:
        shutil.rmtree(legacy_dir, ignore_errors=True)
    write_provenance()
    return problems


def minor_of(runtime):
    match = re.search(r'Python (\d+\.\d+)', runtime)
    return match[1] if match else ''


def write_provenance():
    manifest = read_manifest()
    capture = manifest['capture']
    corpus = capture['corpus']
    lines = ['# Provenance of the golden tables', '',
             'Generated by `tools/golden.py import-capture`; do not edit.', '',
             'Captured rows come from math-exercise\'s own examples (licence: ' + str(corpus.get('licence')) + '),',
             f'rendered at math-exercise `{corpus.get("commit")}` with CTM Assessment and graded by the umbrella\'s',
             f'parity harness (`{capture.get("harness")}`, ctm-assessment `{capture.get("umbrella")}`) at the runtime',
             'boundary of math-exercise.js under ' + ', '.join(run.get('runtime') or run.get('name') for run in capture.get('runs') or []) + '.',
             'Rows derived from courses or the umbrella\'s example site are not committed here (step-2 design §13 item 7).',
             'Inputs: each captured request is what a rendered page of math-exercise\'s example site sent to the checker library;',
             'the answers typed into the pages come from math-exercise itself (answer keys, authored tests, variant fixtures) or',
             'were written for the harness in the umbrella under AGPL-3.0-or-later (probe sets and boundary probes, the audit\'s',
             'challenge answers, teacher answers). The inputs of the recorded suites are written here (`tools/golden.py`).',
             'Recorded suites and the per-version results of Python versions without a Pyodide build were recorded with',
             f'math-exercise\'s own code at `{manifest["legacy"]["math-exercise"]}` (`tools/golden.py record`).', '',
             '| File | Rows | Source | Licence |', '|---|---|---|---|']
    for name, info in sorted(capture['files'].items()):
        lines.append(f'| `{name}` | {info.get("rows")} | captured from math-exercise `{corpus.get("commit", "")[:12]}` | {info.get("licence")} |')
    for suite, info in sorted(manifest.get('recorded', {}).items()):
        lines.append(f'| `{suite}.jsonl` | {info["rows"]} | recorded with math-exercise `{manifest["legacy"]["math-exercise"][:12]}` (Python {", ".join(info["python"])}) | AGPL-3.0-or-later |')
    for name in manifest.get('files', []):
        lines.append(f'| `math_exercise/files/{name}` | — | math-exercise `{corpus.get("commit", "")[:12]}`, named by an authored test | {corpus.get("licence")} |')
    (GOLDEN / 'PROVENANCE.md').write_text('\n'.join(lines) + '\n', encoding='utf-8')


# ---------------------------------------------------------------------------

def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    commands = parser.add_subparsers(dest='command', required=True)
    check = commands.add_parser('verify', help='run every row and compare')
    check.add_argument('--adapter', default='legacy', choices=('legacy', 'wheel', 'src', 'installed'))
    check.add_argument('--legacy', help='math-exercise checkout (legacy adapter)')
    check.add_argument('--wheel', help='the wheel (adapter wheel; default: the one in _extensions/ctm-checkers/)')
    check.add_argument('--variants', help="math-exercise checkout whose variants.py runs the rounding rows of variants.py")
    check.add_argument('--umbrella', help='ctm-assessment checkout at the commit in tools/pins.json (default: _ci/ctm-assessment)')
    check.add_argument('--suite', action='append', default=[], help='regular expression on the table path (repeatable)')
    check.add_argument('--max-diffs', type=int, default=20)
    rec = commands.add_parser('record', help="add this Python's results (legacy adapter)")
    rec.add_argument('--legacy', required=True)
    rec.add_argument('--umbrella', help='ctm-assessment checkout at the commit in tools/pins.json (default: _ci/ctm-assessment)')
    imp = commands.add_parser('import-capture', help='replace the captured suites with a new capture')
    imp.add_argument('capture', help='folder written by run.cjs --capture, or the goldens-export artifact (zip)')
    imp.add_argument('--math-exercise', required=True, metavar='CHECKOUT',
                     help='a math-exercise Git checkout that contains the captured commit and the legacy pin (tools/pins.json)')
    imp.add_argument('--record-with', action='append', default=[], metavar='PYTHON',
                     help='also record with this interpreter (each Python version CI tests)')
    imp.add_argument('--umbrella', help='ctm-assessment checkout at the commit in tools/pins.json (default: _ci/ctm-assessment)')
    options = parser.parse_args(argv)
    use_umbrella(getattr(options, 'umbrella', None))
    if options.command == 'verify':
        return 1 if verify(make_adapter(options), options.suite, options.max_diffs) else 0
    if options.command == 'record':
        return 1 if record(Legacy(options.legacy)) else 0
    return 1 if import_capture(options) else 0


if __name__ == '__main__':
    sys.exit(main())
