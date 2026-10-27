import pytest
from ctm_checkers.stack.page import test_results as verify


def payload(status='correct',score=1):
    return {'tests':[{'name':'teacher','answers':{'ans':'x+x'},'expect':'correct'}],
        'fields':['ans'],'results':[{'status':status,'score':score}]}


def test_native_expectations_use_the_shared_verdict_contract():
    assert verify(payload())['result']['passed']
    failure=verify(payload('wrong',0))
    assert not failure['ok'] and failure['errorDetail']['kind']=='author'
    assert 'teacher' in failure['error']


def test_invalid_is_never_implicitly_a_wrong_zero():
    request=payload('invalid',0);request['tests'][0]['expect']='wrong'
    assert not verify(request)['ok']
    request['tests'][0]['expect']='invalid'
    assert verify(request)['ok']


def test_native_result_cardinality_and_field_shapes_fail_closed():
    for change in [{'results':[]},{'fields':['ans','ans']},{'results':[None]}]:
        assert not verify(dict(payload(),**change))['ok']


def test_result_verifier_never_evaluates_authored_expression_text():
    request=payload();request['tests'][0]['answers']['ans']='system("must never run")'
    assert verify(request)['ok']
