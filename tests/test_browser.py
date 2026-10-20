"""browser.call: the request leaves the page's namespace, the dunder rule,
the guard around each call (design §2.2)."""
import json
import sys
import types

import pytest

from ctm_checkers import browser

CHECK = {'student': 'x^2+2*x+1', 'correct': '(x+1)^2', 'vars': 'x', 'mode': 'equivalent', 'reject': '', 'tolerance': '',
         'decplaces': '', 'sigfigs': '', 'form': '', 'partial_credit': False, 'form_credit': 0.5}


def call(name, request, **namespace):
    caller = dict(namespace, _ctm_request=json.dumps(request))
    return caller, browser.call(name, caller)


def test_the_request_leaves_the_namespace():
    caller, text = call('math_exercise.check', CHECK, learner=1)
    assert json.loads(text) == {'status': 'correct', 'score': 1.0}
    assert caller == {'learner': 1}
    # Python's default JSON text, as math-exercise 0.10.0 returned it.
    assert text == '{"status": "correct", "score": 1.0}'


@pytest.mark.parametrize('request_, name', [
    (dict(CHECK, student='x.__class__'), 'math_exercise.check'),
    ({'checker': 'def check(r, s):\n    return True\n', 'vars': '', 'response': {'kind': 'expressions', 'raw': ['__import__("os")'], 'inputs': {}}},
     'math_exercise.check_custom'),
    ({'checker': 'def check(r, s):\n    return True\n', 'vars': '',
      'response': {'kind': 'expressions', 'raw': [], 'inputs': {'M': {'type': 'matrix', 'rows': 1, 'cols': 1, 'raw': ['a.__dict__']}}}},
     'math_exercise.check_custom'),
])
def test_dunders_in_learner_strings_are_rejected(request_, name):
    caller = {'_ctm_request': json.dumps(request_)}
    with pytest.raises(ValueError, match='SyntaxError: unsupported input'):
        browser.call(name, caller)
    assert caller == {}


def test_string_answers_and_authors_may_use_dunders():
    _, text = call('math_exercise.check', dict(CHECK, mode='string', student='__x__', correct='__x__'))
    assert json.loads(text)['status'] == 'correct'
    _, text = call('math_exercise.check_custom', {'checker': 'import os\n__all__ = []\ndef check(r, s):\n    return True\n', 'vars': '',
                                                  'response': {'kind': 'expressions', 'raw': ['1'], 'inputs': {}}})
    assert json.loads(text)['status'] == 'correct'


def test_unknown_calls_raise():
    with pytest.raises(KeyError):
        browser.call('math_exercise.nothing', {'_ctm_request': '{}'})


def test_a_call_without_a_request_raises():
    caller = {'learner': 1}
    with pytest.raises(RuntimeError, match=r"browser\.call\('math_exercise\.check'\): no request: the caller sets _ctm_request"):
        browser.call('math_exercise.check', caller)
    assert caller == {'learner': 1}


def test_the_guard_restores_after_every_call(monkeypatch):
    events = []
    guard = types.ModuleType('_ctm_guard')
    guard.snapshot = lambda: events.append('snapshot') or 'state'
    guard.restore = lambda state: events.append('restore ' + state)
    monkeypatch.setitem(sys.modules, '_ctm_guard', guard)
    monkeypatch.setattr(browser, '_ctm_guard', None)   # installed after this module was imported
    call('math_exercise.check', CHECK)
    assert events == ['snapshot', 'restore state']
    # A result that is not JSON raises to the page, after the restore.
    with pytest.raises(TypeError):
        call('math_exercise.check_custom', {'checker': 'def check(r, s):\n    return {"score": 1, "assessment": {"x": object()}}\n',
                                            'vars': '', 'response': {'kind': 'expressions', 'raw': [], 'inputs': {}}})
    assert events[-1] == 'restore state'
    # The dunder rule runs before the guard's snapshot, as before.
    events.clear()
    with pytest.raises(ValueError):
        call('math_exercise.check', dict(CHECK, student='__x'))
    assert events == []
