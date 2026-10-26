"""The single entry from the page (Pyodide): `call(name, caller)`.

The page puts one request into the interpreter's namespace as `_ctm_request`
(JSON text) and runs, in that namespace (ctm-libs' call text, docs/api.md),

    import builtins as _ctm_builtins
    _ctm_builtins.__import__("ctm_checkers.browser", fromlist=["call"]).call("math_exercise.check", _ctm_builtins.globals())

`call` takes the request out of that namespace (a call without one is an
error), so learner code sharing it sees nothing left behind; applies the
call's admission rule; runs the handler, restoring the interpreter state that
ctm-libs' guard (`_ctm_guard`) protects for the other components on the page;
and returns the result as JSON text. Exceptions reach the page as they did in
math-exercise 0.10.0 (_math_run) and in stack-sympy's worker (worker.js).
"""
import importlib
import json

try:
    import _ctm_guard
except ImportError:  # native Python (build time) has no page to protect
    _ctm_guard = None

# name: (handler, admission rule or None), each "module:function". STACK's
# grammar never evaluates learner text as Python: its calls need no admission rule.
CALLS = {
    "math_exercise.compute_key": ("ctm_checkers.math_exercise.keys:compute_key", None),
    "math_exercise.admit_generated": ("ctm_checkers.math_exercise.generated:admit_generated", None),
    "math_exercise.check": ("ctm_checkers.math_exercise.checks:check", "ctm_checkers.math_exercise.inputs:admit"),
    "math_exercise.check_custom": ("ctm_checkers.math_exercise.custom:check_custom", "ctm_checkers.math_exercise.inputs:admit"),
    "stack.validate": ("ctm_checkers.stack.page:validate", None),
    "stack.grade": ("ctm_checkers.stack.page:grade", None),
    "stack.tests": ("ctm_checkers.stack.page:tests", None),
    "stack.check": ("ctm_checkers.stack.page:check", None),
}


def _function(path):
    module, _, name = path.partition(":")
    return getattr(importlib.import_module(module), name)


def _guard():
    # The guard ctm-libs installs before the first call (also when this
    # module was imported before it).
    global _ctm_guard
    if _ctm_guard is None:
        try:
            import _ctm_guard as guard
        except ImportError:
            return None
        _ctm_guard = guard
    return _ctm_guard


def call(name, caller):
    # Move this request out of the shared namespace.
    text = caller.pop("_ctm_request", None)
    handler, admission = (_function(path) if path else None for path in CALLS[name])
    if text is None:
        raise RuntimeError("ctm_checkers.browser.call(" + repr(name) + "): no request: the caller sets _ctm_request "
                           "(JSON text) in the namespace it passes, before each call (docs/api.md)")
    request = json.loads(text)
    if admission is not None:
        admission(request)
    # Whatever the parsed answer or checker does, other components on the
    # page keep their interpreter state.
    guard = _guard()
    state = guard.snapshot() if guard is not None else None
    try:
        return json.dumps(handler(request))
    finally:
        if state is not None:
            guard.restore(state)
