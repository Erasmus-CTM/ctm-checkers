"""Concrete native goldens call the real authored runner with exact context."""
import copy
from types import SimpleNamespace

import pytest
import sympy as sp

import golden
from ctm_checkers.math_exercise import authored
from ctm_checkers.variants import question_context


def case():
    return {'options': {'mode': 'custom', 'field-labels': 'a', 'question': '_[2]',
        'checker': 'def check(response, symbols):\n    return response["expressions"][0] == response["variables"]["k"] and response["variant"]["n"] == 7\n',
        'tests': [{'name': 'wrong', 'answers': {'a': '3'}, 'expect': 'wrong'}]},
        'context': question_context(['a'], {'k': sp.Integer(2)}, {'a': sp.Integer(2)},
            {'n': 7, 'id': 'seed=17', 'hash': '0123456789abcdef'}), 'teacherInputs': {'a': '2'}}


def run(value, monkeypatch, tmp_path):
    # Only bypass the recorder's external-file lookup; retain the real grader,
    # raw teacher vector and authored assertions in the replay callback.
    monkeypatch.setattr(golden, 'authored_output', lambda callback, options, base: callback(options, base))
    return golden.native_authored_output(SimpleNamespace(authored=authored), value, {}, tmp_path)


def test_exact_variables_identity_and_teacher_vector_reach_the_real_checker(monkeypatch, tmp_path):
    reports = run(case(), monkeypatch, tmp_path)
    assert [item['actual']['status'] for item in reports] == ['correct', 'wrong']


def test_wrong_teacher_and_changed_identity_fail_instead_of_reusing_output(monkeypatch, tmp_path):
    value = case(); value['teacherInputs']['a'] = '99'
    with pytest.raises(AssertionError):
        run(value, monkeypatch, tmp_path)
    value = case(); value['context']['variant']['n'] = 8
    with pytest.raises(AssertionError):
        run(value, monkeypatch, tmp_path)


def test_missing_teacher_field_and_unsupported_adapter_fail(monkeypatch, tmp_path):
    value = case(); value['teacherInputs'] = {}
    with pytest.raises(ValueError, match='every field'):
        run(value, monkeypatch, tmp_path)
    with pytest.raises(ValueError, match='ctm-checkers adapter'):
        golden.native_authored_output(object(), case(), {}, tmp_path)
