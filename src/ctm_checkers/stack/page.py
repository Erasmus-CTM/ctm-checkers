"""The page's STACK calls: browser.call("stack.validate" | "stack.grade" |
"stack.tests", ...) with the request {"question", "variant", "answers"}.

They are stack-sympy's worker requests (its worker.js at f450bcd), moved
here: the same engine calls and the same envelope, {"ok": true, "result": ...}
or, for a question the engine does not support, {"ok": false, "error": ...};
any other exception reaches the page as before. The result holds what
json.dumps(..., default=str) wrote, as the worker returned it.
"""
import json

from .engine import grade as _grade, run_question_tests, validate as _validate
from .importer import UnsupportedQuestion


def _envelope(run):
    try:
        result = run()
    except UnsupportedQuestion as exc:
        response = {"ok": False, "error": str(exc)}
    else:
        response = {"ok": True, "result": result}
    return json.loads(json.dumps(response, default=str))


def validate(request):
    return _envelope(lambda: _validate(request["question"], request["answers"], variant=request["variant"]))


def grade(request):
    return _envelope(lambda: _grade(request["question"], request["answers"], variant=request["variant"]))


def tests(request):
    return _envelope(lambda: run_question_tests(request["question"], seeds=[request["variant"]["seed"]],
                                                variants=[request["variant"]]))
