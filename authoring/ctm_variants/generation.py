"""Bounded native variables execution kernel. AGPL-3.0-or-later.

Partial authoring API: execute one selection, or replay its exact choice tape.
Not yet candidate enumeration, proposals, placeholders or component wiring.
Author code has Quarto's trust level; subprocess deadlines prevent stalled builds.
"""
import ast
from collections import Counter
import hashlib
from fractions import Fraction
import io
import json
import math
import os
from pathlib import Path
import queue
import subprocess
import sys
import tempfile
import threading
import time
import tokenize

MAX_SOURCE = 16384
MAX_STATEMENTS = 128
MAX_NODES = 1000
MAX_DOMAIN = 20000
MAX_ITEMS = 128
MAX_IPC = 262144
RANDOM = {"pick", "sample", "shuffle", "rand", "rand_with_step", "rand_range",
          "rand_with_prohib", "rand_selection", "rand_selection_with_replacement"}


class GenerationError(ValueError):
    pass


class Rejected(GenerationError):
    """The selected values do not satisfy require(); do not resample here."""


def _source(source):
    if not isinstance(source, str) or len(source.encode("utf-8")) > MAX_SOURCE:
        raise GenerationError("variables source exceeds byte limit")
    tokens = tokenize.generate_tokens(io.StringIO(source).readline)
    rewritten = []
    for kind, text, *_ in tokens:
        if kind == tokenize.OP and text == "^":
            text = "**"
        elif kind == tokenize.NUMBER:
            if len(text) > 256 or text.endswith(("j", "J")):
                raise GenerationError("numeric literal exceeds supported exact size")
            if "." in text or "e" in text.lower():
                normalized = text.replace("_", "").lower()
                if "e" in normalized and abs(int(normalized.split("e")[1])) > 1000:
                    raise GenerationError("decimal exponent exceeds 1000")
                exact = Fraction(normalized)
                if exact.numerator.bit_length() > 4096 or exact.denominator.bit_length() > 4096:
                    raise GenerationError("numeric literal exceeds supported exact size")
                text = "({}/{})".format(exact.numerator, exact.denominator)
        rewritten.append((kind, text))
    source = tokenize.untokenize(rewritten)
    tree = ast.parse(source)
    if len(tree.body) > MAX_STATEMENTS or len(list(ast.walk(tree))) > MAX_NODES:
        raise GenerationError("variables source exceeds statement/AST limit")
    names = set()
    for node in tree.body:
        if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
            name = node.targets[0].id
            if name.startswith("_") or name in names or name in RANDOM or name == "require":
                raise GenerationError("line {}: reserved or repeated variable {}".format(node.lineno, name))
            names.add(name)
        elif not (isinstance(node, ast.Expr) and isinstance(node.value, ast.Call)
                  and isinstance(node.value.func, ast.Name) and node.value.func.id == "require"
                  and node.value.args and not node.value.keywords):
            raise GenerationError("line {}: expected assignment or require(condition, ...)".format(node.lineno))
    for statement in tree.body:
        for call in (item for item in ast.walk(statement) if isinstance(item, ast.Call) and isinstance(item.func, ast.Name)):
            if call.func.id == "raw":
                raise GenerationError("raw() belongs to student test fixtures, not variables")
            if call.func.id in {"pick", "sample", "shuffle"} and not (isinstance(statement, ast.Assign) and call is statement.value):
                raise GenerationError("pick/sample/shuffle must be the entire assignment expression")
    return source, tree


def _integer(value):
    import sympy as sp
    if isinstance(value, bool) or not isinstance(value, (int, sp.Integer)):
        raise GenerationError("random range and selection sizes must be integers")
    return int(value)


def _items(value):
    if not isinstance(value, (list, tuple)) or len(value) > MAX_ITEMS:
        raise GenerationError("random choices require a list of at most {} items".format(MAX_ITEMS))
    return list(value)


def _key(value):
    from ctm_checkers.variants import encode
    return json.dumps(encode(value), sort_keys=True, ensure_ascii=True, separators=(",", ":"))


def _keys(values):
    return {_key(value) for value in values}


class _Domain:
    def __init__(self, size, at, contains):
        if not 0 < size <= MAX_DOMAIN:
            raise GenerationError("random domain is empty or exceeds {}".format(MAX_DOMAIN))
        self.size, self.at, self.contains = size, at, contains


def _list_domain(values):
    values = _items(values)
    allowed = _keys(values)
    return _Domain(len(values), values.__getitem__, lambda value: _key(value) in allowed)


def _range_domain(low, high, step, exclude, empty_result=False):
    low, high, step = map(_integer, (low, high, step))
    if step <= 0 or high < low:
        raise GenerationError("random range needs low <= high and positive step")
    size = (high - low) // step + 1
    if size > MAX_DOMAIN:
        raise GenerationError("random range exceeds {}".format(MAX_DOMAIN))
    prohibited = _keys(exclude)
    values = [low + step*i for i in range(size) if _key(low + step*i) not in prohibited]
    if not values and empty_result:
        return _constant_domain([])
    return _list_domain_unbounded(values)


def _constant_domain(value):
    expected = _key(value)
    return _Domain(1, lambda index: value, lambda candidate: _key(candidate) == expected)


def _list_domain_unbounded(values):
    allowed = _keys(values)
    return _Domain(len(values), values.__getitem__, lambda value: _key(value) in allowed)


def _stepped_domain(low, high, step):
    import sympy as sp
    if any(isinstance(value, bool) or not isinstance(value, (int, sp.Rational))
           for value in (low, high, step)):
        raise GenerationError("rand_with_step needs exact rational bounds and step")
    if step == 0:
        raise GenerationError("rand_with_step needs a nonzero step")
    size = int(sp.floor((sp.Rational(high)-low)/step)) + 1
    if not 0 < size <= MAX_DOMAIN:
        raise GenerationError("stepped random domain is empty or exceeds {}".format(MAX_DOMAIN))
    return _list_domain_unbounded([low + step*i for i in range(size)])


def _rand_range_domain(args):
    low, high = map(_integer, args[:2])
    step = _integer(args[2]) if len(args) == 3 else 1
    if step == 0:
        raise GenerationError("rand_range needs a nonzero step")
    # STACK rand_range uses rand_zero(floor(...)), unlike rand_with_step's +1.
    count = (high-low)//step
    if count < 0 or count > MAX_DOMAIN:
        raise GenerationError("rand_range domain is invalid or exceeds {}".format(MAX_DOMAIN))
    return _list_domain_unbounded([low + step*i for i in range(max(1,count))])


def _selection(values, count, replacement=False):
    values, count = _items(values), _integer(count)
    if count < 0 or count > MAX_ITEMS or (not replacement and count > len(values)):
        raise GenerationError("invalid random selection size")
    # Count before building any selections, stopping before factorial growth.
    size = 1
    for i in range(count):
        size *= len(values) if replacement else len(values)-i
        if size > MAX_DOMAIN:
            raise GenerationError("selection domain exceeds {}".format(MAX_DOMAIN))
    def at(index):
        pool, result = list(values), []
        for i in range(count):
            divisor = 1
            for j in range(i+1, count):
                divisor *= len(values) if replacement else len(values)-j
            position, index = divmod(index, divisor)
            result.append(pool[position])
            if not replacement:
                pool.pop(position)
        return result
    available = Counter(_key(item) for item in values)
    def contains(value):
        if not isinstance(value, list) or len(value) != count:
            return False
        wanted = Counter(_key(item) for item in value)
        return all(key in available and (replacement or amount <= available[key])
                   for key, amount in wanted.items())
    return _Domain(size, at, contains)


def _domain(name, args, kwargs):
    if name == "pick":
        if set(kwargs) - {"step", "exclude"}:
            raise GenerationError("unknown pick option")
        exclude = _items(kwargs.get("exclude", []))
        if len(args) == 1 and "step" not in kwargs:
            prohibited = _keys(exclude)
            return _list_domain([v for v in _items(args[0]) if _key(v) not in prohibited])
        if len(args) == 2:
            return _range_domain(*args, kwargs.get("step", 1), exclude)
    elif kwargs:
        raise GenerationError("random aliases do not accept keyword options")
    elif name == "rand" and len(args) == 1:
        if isinstance(args[0], (list, tuple)):
            if not args[0]:
                return _constant_domain([])
            return _list_domain(args[0])
        return _range_domain(0, _integer(args[0])-1, 1, [])
    elif name == "rand_with_step" and len(args) == 3:
        return _stepped_domain(*args)
    elif name == "rand_range" and len(args) in (2,3):
        return _rand_range_domain(args)
    elif name == "rand_with_prohib" and len(args) == 3:
        return _range_domain(args[0], args[1], 1, _items(args[2]), empty_result=True)
    elif name in ("sample", "rand_selection", "rand_selection_with_replacement") and len(args) == 2:
        if name == "rand_selection_with_replacement":
            values, count = _items(args[0]), _integer(args[1])
            if count > MAX_ITEMS:
                raise GenerationError("random selection size exceeds {}".format(MAX_ITEMS))
            if count <= 0:
                return _constant_domain([])
            if not values:
                return _constant_domain([[] for _ in range(count)])
        return _selection(*args, replacement=name == "rand_selection_with_replacement")
    elif name == "shuffle" and len(args) == 1:
        return _selection(args[0], len(_items(args[0])))
    raise GenerationError("unsupported random call: " + name)


def _helpers():
    import sympy as sp
    return {"subs": lambda value, symbol, replacement: value.subs(symbol, replacement),
            "det": lambda value: value.det(), "inv": lambda value: value.inv(),
            "transpose": lambda value: value.T, "min": sp.Min, "max": sp.Max,
            }


def _run(source, variables, seed, replay, progress):
    from ctm_checkers.testing import expression
    import sympy as sp
    source, tree = _source(source)
    variables = dict(variables)
    helpers = _helpers()
    protected = set(helpers) | RANDOM | {"sqrt", "sin", "cos", "tan", "asin", "acos", "atan", "atan2",
        "exp", "log", "ln", "abs", "Abs", "floor", "ceiling", "Min", "Max", "gcd", "lcm",
        "diff", "integrate", "expand", "factor", "simplify", "together", "cancel", "apart",
        "Matrix", "Rational", "Integer", "pi", "E", "I", "oo", "require", "raw"}
    if not isinstance(variables, dict) or any(not isinstance(name, str) or not name.isidentifier() or name.startswith("_") for name in variables):
        raise GenerationError("symbols must be a mapping with public identifier keys")
    if set(variables) & protected:
        raise GenerationError("symbol names collide with language functions")
    tape = []
    def resolve(node):
        class Choices(ast.NodeTransformer):
            def visit_Call(self, call):
                call = self.generic_visit(call)
                if isinstance(call.func, ast.Name) and call.func.id in RANDOM:
                    args = [expression(ast.unparse(arg), dict(helpers, **variables)) for arg in call.args]
                    if any(item.arg is None for item in call.keywords):
                        raise GenerationError("expanded keyword arguments are unsupported")
                    kwargs = {item.arg: expression(ast.unparse(item.value), dict(helpers, **variables))
                              for item in call.keywords}
                    if len(kwargs) != len(call.keywords):
                        raise GenerationError("duplicate random options")
                    domain = _domain(call.func.id, args, kwargs)
                    index = len(tape)
                    if replay is None:
                        digest = hashlib.sha256((seed + ":" + str(index)).encode("utf-8")).digest()
                        value = domain.at(int.from_bytes(digest, "big") % domain.size)
                    else:
                        if index >= len(replay) or not domain.contains(replay[index]):
                            raise GenerationError("replayed choice is absent from current domain")
                        value = replay[index]
                    tape.append(value)
                    name = "_ctm_choice_" + str(index)
                    variables[name] = value
                    return ast.copy_location(ast.Name(id=name, ctx=ast.Load()), call)
                return call
        transformed = Choices().visit(ast.fix_missing_locations(ast.parse(ast.unparse(node), mode="eval")))
        return expression(ast.unparse(transformed), dict(helpers, **variables))
    def predicate(node):
        if isinstance(node, ast.BoolOp):
            values = (predicate(item) for item in node.values)
            return all(values) if isinstance(node.op, ast.And) else any(values)
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.Not):
            return not predicate(node.operand)
        if isinstance(node, ast.Compare):
            left = resolve(node.left)
            for op, right_node in zip(node.ops, node.comparators):
                right = resolve(right_node)
                if isinstance(op, ast.Eq): okay = sp.Eq(left, right)
                elif isinstance(op, ast.NotEq): okay = sp.Ne(left, right)
                elif isinstance(op, ast.Lt): okay = left < right
                elif isinstance(op, ast.LtE): okay = left <= right
                elif isinstance(op, ast.Gt): okay = left > right
                elif isinstance(op, ast.GtE): okay = left >= right
                else: raise GenerationError("unsupported require comparison")
                if not bool(okay):
                    return False
                left = right
            return True
        value = resolve(node)
        if value not in (True, False):
            raise GenerationError("require needs a decidable Boolean condition")
        return bool(value)
    for index, node in enumerate(tree.body):
        progress(index, node.lineno)
        try:
            if isinstance(node, ast.Assign):
                name = node.targets[0].id
                if name in protected or name in variables:
                    raise GenerationError("variable name collides with a symbol or language function")
                variables[name] = resolve(node.value)
            elif not all(predicate(arg) for arg in node.value.args):
                raise Rejected("require condition is false")
        except Exception as error:
            raise type(error)("line {}: {}".format(node.lineno, error)) from error
    if replay is not None and len(tape) != len(replay):
        raise GenerationError("replay has unused choices")
    return {"variables": {key: value for key, value in variables.items() if not key.startswith("_ctm_choice_")},
            "choices": tape}


def _read_lines(stream, messages, stopped):
    try:
        while not stopped.is_set():
            line = stream.readline(MAX_IPC+1)
            if not line:
                item = None
            elif len(line) > MAX_IPC:
                item = {"protocol_error": "worker output exceeds byte limit"}
            else:
                try:
                    item = json.loads(line)
                except Exception:
                    item = {"protocol_error": "invalid worker output"}
            while not stopped.is_set():
                try:
                    messages.put(item, timeout=0.05)
                    break
                except queue.Full:
                    pass
            if item is None or isinstance(item, dict) and "protocol_error" in item:
                break
    finally:
        stream.close()


def execute(source, *, variables=None, seed="", replay=None, file="<variables>", label="<question>",
            variable_timeout=5.0, variant_timeout=30.0):
    """Execute one bounded selection; replay is its exact, value-based choices list.

    Every variable and require statement has a real supervisor deadline. The
    enclosing deadline includes startup/import/serialization time. This API never
    retries failed require conditions or silently replaces missing replay values.
    """
    from ctm_checkers.variants import encode, decode
    where = "{}: {}: ".format(file, label)
    try:
        _, tree = _source(source)
    except Exception as error:
        raise GenerationError(where + str(error)) from error
    for timeout in (variable_timeout, variant_timeout):
        if isinstance(timeout, bool) or not isinstance(timeout, (int, float)) or not math.isfinite(timeout) or timeout <= 0:
            raise GenerationError("timeouts must be positive finite seconds")
    if not isinstance(seed, str) or len(seed) > 1024:
        raise GenerationError("seed must be text of at most 1024 characters")
    if replay is not None and not isinstance(replay, list):
        raise GenerationError("replay must be a choice list")
    import ctm_checkers
    import sympy
    import mpmath
    import_roots = sorted({str(Path(package.__file__).resolve().parents[1])
                           for package in (ctm_checkers, sympy, mpmath)})
    request = json.dumps({"source": source, "import_roots": import_roots, "variables": encode(variables or {}),
                          "seed": seed, "replay": None if replay is None else encode(replay)},
                         ensure_ascii=True).encode("utf-8")
    if len(request) > MAX_IPC:
        raise GenerationError("worker request exceeds byte limit")
    messages, stopped = queue.Queue(maxsize=1), threading.Event()
    with tempfile.TemporaryDirectory(prefix="ctm-generation-") as temporary:
        request_path = Path(temporary) / "request.json"
        request_path.write_bytes(request)
        environment = dict(os.environ)
        environment.pop("PYTHONPATH", None)
        started = time.monotonic()
        process = subprocess.Popen([sys.executable, "-I", str(Path(__file__).resolve()), str(request_path)],
                                   stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                                   env=environment, cwd=temporary)
        reader = threading.Thread(target=_read_lines, args=(process.stdout, messages, stopped),
                                  name="ctm-generation-reader", daemon=True)
        reader.start()
        variable_started, expected = started, 0
        line = tree.body[0].lineno if tree.body else 1
        try:
            while True:
                now = time.monotonic()
                remaining = min(started + variant_timeout, variable_started + variable_timeout) - now
                if remaining <= 0:
                    raise GenerationError("line {}: generation time budget exceeded".format(line))
                try:
                    message = messages.get(timeout=remaining)
                except queue.Empty:
                    raise GenerationError("line {}: generation time budget exceeded".format(line))
                if time.monotonic() > min(started + variant_timeout, variable_started + variable_timeout):
                    raise GenerationError("line {}: generation time budget exceeded".format(line))
                if not isinstance(message, dict):
                    raise GenerationError("worker exited without a result")
                if set(message) == {"statement", "line"}:
                    if expected >= len(tree.body) or type(message["statement"]) is not int or message["statement"] != expected or type(message["line"]) is not int or message["line"] != tree.body[expected].lineno:
                        raise GenerationError("unexpected worker statement boundary")
                    line, expected = message["line"], expected+1
                    # First boundary includes initialization in the first variable's budget.
                    if expected > 1:
                        variable_started = time.monotonic()
                elif set(message) == {"result"} and expected == len(tree.body):
                    result = decode(message["result"])
                    if not isinstance(result, dict) or set(result) != {"variables", "choices"} or not isinstance(result["variables"], dict) or not isinstance(result["choices"], list):
                        raise GenerationError("invalid worker result shape")
                    result["locator"] = json.dumps(encode(result["choices"]), sort_keys=True,
                                                    ensure_ascii=True, separators=(",", ":"))
                    return result
                elif set(message) == {"error", "rejected"}:
                    if not isinstance(message["error"], str) or type(message["rejected"]) is not bool:
                        raise GenerationError("invalid worker error shape")
                    error = Rejected if message["rejected"] else GenerationError
                    raise error(message["error"])
                else:
                    raise GenerationError(message.get("protocol_error", "unexpected worker protocol"))
        except Exception as error:
            kind = Rejected if isinstance(error, Rejected) else GenerationError
            detail = str(error)
            if not detail.startswith("line "):
                detail = "line {}: {}".format(line, detail)
            raise kind(where + detail) from error
        finally:
            stopped.set()
            if process.poll() is None:
                process.kill()
            process.wait()
            reader.join(timeout=2)
            if reader.is_alive():
                raise GenerationError(where + "worker reader failed to terminate")


def _worker(request_path):
    def emit(message):
        data = json.dumps(message, ensure_ascii=True)
        if len(data.encode("utf-8")) > MAX_IPC-1:
            raise GenerationError("worker output exceeds byte limit")
        print(data, flush=True)
    try:
        with open(request_path, "rb") as stream:
            request = stream.read(MAX_IPC+1)
        if len(request) > MAX_IPC:
            raise GenerationError("worker request exceeds byte limit")
        request = json.loads(request)
        sys.path[:0] = request["import_roots"]
        from ctm_checkers.variants import encode, decode
        result = _run(request["source"], decode(request["variables"]), request["seed"],
                      None if request["replay"] is None else decode(request["replay"]),
                      lambda index, line: emit({"statement": index, "line": line}))
        emit({"result": encode(result)})
    except Exception as error:
        emit({"error": str(error)[:4096], "rejected": isinstance(error, Rejected)})


if __name__ == "__main__":
    _worker(sys.argv[1])
