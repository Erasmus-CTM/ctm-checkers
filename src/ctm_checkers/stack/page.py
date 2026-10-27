"""The page's STACK calls: browser.call("stack.validate" | "stack.grade" |
"stack.tests", ...) with the request {"question", "variant", "answers"}.

An author failure has a structured error (kind, code, message, arguments).
Learner input stays a normal CAS result, including invalid input. Unexpected
exceptions reach the adapter, which owns runtime recovery. Only the adapter's
runtime failure may restart a session; an author failure must retain it.
"""
import json

from .engine import grade as _grade, run_question_tests, validate as _validate
from .importer import UnsupportedQuestion
from .messages import decorate_result
from .plans import validate_plan


def _envelope(run):
    try:
        result = run()
    except UnsupportedQuestion as exc:
        response = {"ok": False, "error": str(exc), "errorDetail": {"kind": "author", "code": "stack_question_error",
                     "message": str(exc), "args": {"question": exc.question,
                     "location": exc.location, "reason": exc.reason}}}
    else:
        response = {"ok": True, "result": decorate_result(result)}
    return json.loads(json.dumps(response, default=str))


def _plan(request):
    # Missing request fields are protocol/runtime faults. A present but malformed
    # generated question/variant is an author-plan fault, not a learner answer.
    question, variant = request["question"], request["variant"]
    validate_plan(question, variant)
    return question, variant


def validate(request):
    def run():
        answers = request["answers"]
        question, variant = _plan(request)
        return _validate(question, answers, variant=variant)
    return _envelope(run)


def grade(request):
    def run():
        answers = request["answers"]
        question, variant = _plan(request)
        return _grade(question, answers, variant=variant)
    return _envelope(run)


def tests(request):
    def run():
        question, variant = _plan(request)
        return run_question_tests(question, seeds=[variant["seed"]], variants=[variant])
    return _envelope(run)


def check(request):
    """The backend continuation uses the same author-error envelope."""
    from .check import check as run_checker, CheckerError
    def run():
        try:
            return run_checker(request)
        except CheckerError as error:
            raise UnsupportedQuestion(request.get('questionName', 'STACK checker'), 'checker', str(error)) from error
    return _envelope(run)


def test_results(request):
    """Verify named, candidate-bound observations using shared expectations."""
    from .native_tests import run as verify
    def run():
        try:return verify(request)
        except (ValueError,AssertionError) as error:
            raise UnsupportedQuestion(request.get('questionName','STACK tests'),'tests',str(error)) from error
    return _envelope(run)
