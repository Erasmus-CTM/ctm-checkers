"""The single entry from the page (Pyodide): `call(name, caller)`.

The page puts one request into the interpreter's namespace as `_ctm_request`
(JSON text) and runs

    __import__("ctm_checkers.browser", fromlist=["call"]).call("math_exercise.check", globals())

`call` takes the request out of that namespace, so learner code sharing it
sees nothing left behind; applies the call's admission rule; runs the
handler, restoring the interpreter state that ctm-libs' guard (`_ctm_guard`)
protects for the other components on the page; and returns the result as
JSON text. Exceptions reach the page as they did in math-exercise 0.10.0
(_math_run).
"""
import importlib
import json

try:
    import _ctm_guard
except ImportError:  # native Python (build time) has no page to protect
    _ctm_guard = None

# name: (handler, admission rule), each "module:function".
CALLS = {
    "math_exercise.check": ("ctm_checkers.math_exercise.checks:check", "ctm_checkers.math_exercise.inputs:admit"),
    "math_exercise.check_custom": ("ctm_checkers.math_exercise.custom:check_custom", "ctm_checkers.math_exercise.inputs:admit"),
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
    handler, admission = (_function(path) for path in CALLS[name])
    request = json.loads(text) if text is not None else {}
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
