import pytest
from ctm_checkers.stack.page import test_results as verify


def payload(status='correct',score=1):
    identity={'id':'seed=1','hash':'a'*16}
    declaration={'name':'teacher','answers':{'ans':'x+x'},'expect':'correct'}
    return {'candidate':identity,'tests':[declaration],
        'fields':['ans'],'results':[{'name':'teacher','candidate':identity,'declaration':declaration,'status':status,'score':score}]}


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


def test_named_results_echo_the_candidate_identity():
    request=payload();result=verify(request)['result']
    assert result['candidate']==request['candidate']
    assert result['results'][0]['name']=='teacher'
    assert result['results'][0]['candidate']==request['candidate']


def test_reordered_missing_stale_and_other_seed_observations_are_rejected():
    import copy
    request=payload();request['tests'].append(dict(request['tests'][0],name='second'))
    request['results'].append(dict(request['results'][0],name='second',declaration=request['tests'][1]))
    assert verify(request)['ok']
    reordered=copy.deepcopy(request);reordered['results'].reverse()
    assert not verify(reordered)['ok']
    for identity in [{'id':'seed=2','hash':'a'*16},{'id':'seed=1','hash':'b'*16}]:
        stale=copy.deepcopy(request);stale['results'][0]['candidate']=identity
        assert not verify(stale)['ok']
    for key in ('name','candidate'):
        missing=copy.deepcopy(request);missing['results'][0].pop(key)
        assert not verify(missing)['ok']


@pytest.mark.parametrize('change',[
    {'status':'graded'},{'status':'nonsense'},{'score':True},{'score':'1'},
    {'score':float('nan')},{'score':float('inf')},{'score':-1},{'score':2},
    {'status':'correct','score':0},{'status':'invalid','score':1},
    {'fields':{'unknown':{'status':'correct','score':1}}},
])
def test_result_shapes_fail_closed(change):
    request=payload();request['results'][0].update(change)
    assert not verify(request)['ok']


def test_a_changed_declaration_cannot_reuse_an_old_observation():
    import copy
    request=payload();request['results'][0]['declaration']=copy.deepcopy(request['tests'][0])
    request['tests'][0]['answers']['ans']='x+x+1'
    assert not verify(request)['ok']


@pytest.mark.parametrize('actual,expected,passed',[
    ('empty','empty',True),('empty','invalid',False),('empty','wrong',False),
    ('error','invalid',True),('error','wrong',False),('invalid','invalid',True),
])
def test_empty_and_error_follow_the_shared_expectation_contract(actual,expected,passed):
    request=payload(actual,0);request['tests'][0]['expect']=expected
    assert verify(request)['ok'] is passed


@pytest.mark.parametrize('status',['empty','error'])
def test_empty_and_error_still_require_zero_numeric_scores(status):
    request=payload(status,1);request['tests'][0]['expect']='invalid'
    assert not verify(request)['ok']
