"""Shared H1 checker results, backend wire contract and library predicates."""
from copy import deepcopy
import json
from pathlib import Path
import pytest
import sympy as sp
from ctm_checkers.stack.check import check, CheckerError, checker_spec, preflight, wire_request
from ctm_checkers.stack.assessment import answer_test
from ctm_checkers.stack.engine import grade, instantiate, validate, run_question_tests
from ctm_checkers.stack.importer import import_xml, UnsupportedQuestion
from ctm_checkers.stack.page import grade as page_grade
ROOT = Path(__file__).resolve().parents[2]
XML = ROOT / 'examples/stack/python-checker.xml'

def config(name, **options):
    return json.dumps({'checker':name, 'options':options})

def source(result):
    return 'def check(response, symbols):\n    return ' + result + '\n'

def question(code=None):
    return import_xml(XML, checker=code or (ROOT/'examples/stack/checkers.py').read_text())[0]


@pytest.mark.parametrize('value,status,score', [('True','correct',1),('False','wrong',0),
    ('0.4','partial',0.4),("{'correct':True,'feedback':'yes'}",'correct',1),
    ("{'score':0.5,'show_score':False}",'partial',0.5)])
def test_shared_normalized_results_and_weighted_checker_tree(value, status, score):
    q=question(source(value)); q['prts']=[]; q['questiontext']=q['questiontext'].replace('[[feedback:prt1]]','[[feedback:checker]]')
    result=grade(q,{'ans':'3'})
    assert result['status']=='graded' and result['score']==score
    assert result['prts']['checker']['score']==score
    assert check(wire_request(q,instantiate(q),{'ans':'3'}))['status']==status


def test_weighted_checker_score_feedback_slot_and_xml_penalty():
    q=question(source('0.5'))
    first=q['prts'][0];first['nodes'][0]['test']='AlgEquiv';first['nodes'][0]['teacher']='3'
    first['name']='one';first['value']=1
    second=deepcopy(first);second['name']='two';second['nodes'][0]['teacher']='4'
    q['prts'].append(second);q['checker_value']=2
    q['questiontext']=q['questiontext'].replace('[[feedback:prt1]]','[[feedback:checker]]')
    frozen=instantiate(q)
    assert 'class="stack-feedback" data-name="checker"' in frozen['question_html']
    result=grade(q,{'ans':'3'},variant=frozen)
    assert [result['prts'][key]['score'] for key in ('one','two','checker')]==[1,0,0.5]
    assert result['score']==0.5


def test_node_uses_complete_response_and_partial_is_false_predicate():
    q=question('''def check(response, symbols):
    if "node" in response:
        assert "ans" not in response["variables"]
        assert response["node"]["sans"] == response["answers"]["ans"]
        assert response["node"]["tans"] == response["variables"]["d"]
        assert response["node"]["options"] == {"label":"__import__('os')"}
    return 0.5
''')
    q['prts'][0]['nodes'][0]['options']=config('check',label="__import__('os')")
    result=grade(q,{'ans':'3'})
    assert result['prts']['prt1']['path'][0]['branch']=='false'
    assert result['prts']['checker']['score']==0.5
    assert result['score']==0.25


def test_wire_keeps_written_tree_and_raw_separately_and_decodes_exact_context():
    q=question('''def check(response, symbols):
    assert response["kind"] == "expressions"
    assert response["raw"] == [" 2(x + 1) "]
    assert response["inputs"]["ans"]["canonical"] == "(2*(x+1))"
    assert response["answers"]["ans"] == 2*symbols["x"]+2
    assert response["expressions"] == [response["answers"]["ans"]]
    assert response["teacher"]["ans"] == 3
    assert response["variables"]["d"] == 3
    assert response["variant"] == {"n":7,"id":"seed=1","hash":"1234567890abcdef"}
    return True
''')
    q['inputs'][0]['insertstars']=1
    q['inputs'][0]['checkanswertype']=False
    q['variables']='d:3;'
    frozen=instantiate(q);frozen.update(n=7,id='seed=1',hash='1234567890abcdef')
    assert grade(q,{'ans':' 2(x + 1) '},variant=frozen)['score']==1


def test_wire_accepts_maxima_text_contract_and_only_requires_used_variables():
    request={'backend':'maxima','checker':source('response["variables"]["a"] == Rational(1,3)'),
        'inputs':{'ans':{'type':'algebraic','raw':'1/3','canonical':'1/3'}},
        'teacher':{'ans':'1/3'},'variables':{'a':'1/3','unused':'maxima_only(2)'},
        'assumptions':{'positive':True},'variant':{'n':1,'id':'moodle=17','hash':'1234567890abcdef'}}
    assert check(request)['status']=='correct'
    request['checker']=source('response["variables"]["unused"] == 2')
    with pytest.raises(CheckerError,match='Cannot decode checker variable unused'):check(request)
    request['checker']=source('True');request['teacher']['ans']='maxima_only(2)'
    with pytest.raises(CheckerError):check(request)


@pytest.mark.parametrize('result', ['None','{}','2',"{'score':float('nan')}","{'valid':1,'correct':True}",
    "{'valid':False,'score':0.5}","{'assessment':[],'correct':True}"])
def test_malformed_results_are_author_errors_without_runtime_restart(result):
    q=question(source(result)); frozen=instantiate(q)
    response=page_grade({'question':q,'variant':frozen,'answers':{'ans':'3'}})
    assert response['ok'] is False and response['errorDetail']['kind']=='author'


def test_validation_and_instantiation_do_not_execute_checker_and_namespace_is_fresh():
    q=question('raise RuntimeError("author broke")\n'+source('True'))
    frozen=instantiate(q)
    assert validate(q,{'ans':'3'},variant=frozen)['status']=='valid'
    with pytest.raises(UnsupportedQuestion,match='author broke'):preflight(q,[frozen])
    q['checker']='count=0\ndef check(response,symbols):\n    global count\n    count+=1\n    return count == 1'
    for seed in (1,2,1):assert grade(q,{'ans':'3'},seed)['score']==1


def test_invalid_feedback_has_no_score_or_assessment_and_plain_feedback_is_escaped():
    text='<img src=x onerror=alert(1)>'
    q=question(source(repr({'valid':False,'feedback':text})));q['prts']=[]; q['questiontext']=q['questiontext'].replace('[[feedback:prt1]]','[[feedback:checker]]')
    result=check(wire_request(q,instantiate(q),{'ans':'3'}))
    assert result=={'valid':False,'feedback':text}
    assert grade(q,{'ans':'3'})['status']=='invalid'
    q['checker']=source(repr({'score':0.5,'feedback':text}))
    result=grade(q,{'ans':'3'})
    assert '<img' not in result['feedback'] and '&lt;img' in result['feedback']
    assert result['prts']['checker']['feedbackParts'][0]['message']['args']['text']==text


def test_matrix_response_and_assessment_are_named_by_input():
    q=import_xml(ROOT/'examples/stack/course-c-nullspace.xml')[0]
    q['prts']=[];q['questiontext']=q['questiontext'].replace('[[feedback:result]]','[[feedback:checker]]');q['checker']= '''def check(response,symbols):
    item=response["inputs"]["ans"]
    assert item["rows"]==3 and item["cols"]==2
    assert item["expressions"]==list(item["matrix"])
    assert item["matrix"]==response["answers"]["ans"]
    return {"score":1,"assessment":{"ans":{"columns":["correct","dependent"]}}}
'''
    result=grade(q,{'ans':'matrix([-2,-3],[1,0],[0,1])'})
    assert result['inputs']['ans']['assessment']=={'columns':['correct','dependent']}
    q['checker']=source("{'score':1,'assessment':{'ans':{'columns':['correct']}}}")
    with pytest.raises(UnsupportedQuestion,match='dimensions'):grade(q,{'ans':'matrix([-2,-3],[1,0],[0,1])'})


def test_declarative_tests_replay_actual_grader_and_explicit_invalid_results():
    from ctm_checkers.stack.authored import run_tests
    q=question();q['authored_tests']=[
        {'name':'teacher','answers':{'ans':'d'},'expect':'correct'},
        {'name':'offset','answers':{'ans':'d+1'},'expect':'wrong'},
        {'name':'fraction','answers':{'ans':'raw("1/2")'},'expect':'invalid'}]
    assert len(run_tests(q,instantiate(q)))==3
    q['authored_tests'][1]['expect']='correct'
    with pytest.raises(AssertionError,match='offset'):run_tests(q,instantiate(q))


def test_registry_interface_is_retired_and_unknown_library_names_fail():
    with pytest.raises(TypeError):import_xml(XML,python_checkers='checkers.py')
    for name in ('positive_multiple','a.b','../x.py','__import__(x)',''):
        with pytest.raises(CheckerError,match='Unknown PythonChecker'):checker_spec(config(name))
    q=import_xml(XML)[0]
    with pytest.raises(UnsupportedQuestion,match='block checker'):instantiate(q)


def test_backend_continuation_entry_preserves_normalized_results_and_author_boundary():
    from ctm_checkers.browser import call
    q=question(source('0.5'))
    request=wire_request(q,instantiate(q),{'ans':'3'})
    caller={'_ctm_request':json.dumps(request),'learner':'kept'}
    result=json.loads(call('stack.check',caller))
    assert caller=={'learner':'kept'}
    assert result['ok'] and result['result']['status']=='partial' and result['result']['score']==0.5
    request['checker']='raise RuntimeError("author continuation failure")\n'+source('True')
    result=json.loads(call('stack.check',{'_ctm_request':json.dumps(request)}))
    assert not result['ok'] and result['errorDetail']['kind']=='author'
    assert 'author continuation failure' in result['error']


def test_math_checker_runs_unchanged_on_the_stack_wire_contract():
    from ctm_checkers.math_exercise.custom import check_custom
    from ctm_checkers.variants import question_context
    code='''def check(response, symbols):
    assert response["variables"]["a"] == Rational(1,3)
    assert symbols["x"].is_real is True
    assert response["inputs"] == {} or response["inputs"]["ans"]["type"] == "algebraic"
    return {"score":1 if response["answers"]["ans"] == response["teacher"]["ans"] else 0.5}
'''
    x=sp.Symbol('x',real=True)
    context=question_context(['ans'],{'a':sp.Rational(1,3),'x':x},{'ans':x+1})
    math=check_custom({'vars':'x','checker':code,'question_context':context,
        'response':{'kind':'expressions','raw':['x+1'],'inputs':{}}})
    stack=check({'checker':code,'backend':'sympy','assumptions':{'real':True},
        'variables':{'a':'1/3','x':'x'},'teacher':{'ans':'x+1'},
        'inputs':{'ans':{'type':'algebraic','raw':'x+1','canonical':'(x+1)'}}})
    assert stack==dict(math,valid=True)

@pytest.mark.parametrize('answer,correct', [
    ('matrix([1,0],[0,1])', True),
    ('matrix([2,1],[1,2])', True),
    ('matrix([1/2,1/4],[1/4,1])', True),
    ('matrix([2,%i],[-%i,2])', True),
    ('matrix([1,%i],[%i,1])', False),
    ('matrix([-1,0],[0,-1])', False),  # positive determinant is insufficient
    ('matrix([1,1],[1,1])', False),  # positive semidefinite is insufficient
    ('matrix([2,1],[0,2])', False),  # nonsymmetric, even with positive quadratic form
    ('matrix([1,2],[2,1])', False),
    ('matrix([1,0,0],[0,-1,0],[0,0,-1])', False),  # middle principal minor
    ('matrix([2,1,0],[1,2,1],[0,1,2])', True),
    ('matrix([1,0,0],[0,1,0])', False),
])
def test_spd_example_checks_symmetry_and_all_leading_principal_minors(answer, correct):
    result = answer_test('PythonChecker', answer, 'true', config('is_hpd'))
    assert result['valid'] and result['correct'] is correct
    opposite = answer_test('PythonChecker', answer, 'false', config('is_hpd'))
    assert opposite['valid'] and opposite['correct'] is not correct


@pytest.mark.parametrize('checker', ['is_hermitian', 'is_positive_definite', 'is_hpd'])
@pytest.mark.parametrize('answer', [
    'matrix([x,0],[0,1])', 'matrix([sqrt(2),0],[0,1])',
    'matrix([sqrt(2)*%i,0],[0,1])',
])
def test_spd_example_explains_its_exact_rational_domain(answer, checker):
    result = answer_test('PythonChecker', answer, 'true', config(checker))
    assert not result['valid'] and not result['correct']
    assert 'integers or exact fractions' in result['feedback']


@pytest.mark.parametrize('filename', ['symmetric-positive-definite.xml',
                                     'symmetric-positive-definite-prt.xml'])
def test_spd_xml_and_filename_work_through_build_tests_and_grading(filename):
    q = import_xml(ROOT / 'examples' / 'stack' / filename)[0]
    preflight(q, [instantiate(q)])
    assert run_question_tests(q, seeds=(1,17,47))['passed']
    assert grade(q, {'ansm':'matrix([2,1],[1,2])'})['score'] == 1
    expected = 0.5 if filename.endswith('-prt.xml') else 0
    assert grade(q, {'ansm':'matrix([-1,0],[0,-1])'})['score'] == expected
    assert grade(q, {'ansm':'matrix([x,0],[0,1])'})['status'] == 'invalid'
    assert grade(q, {'ansm':'matrix([0.5,0],[0,1])'})['status'] == 'invalid'


@pytest.mark.parametrize('answer,symmetric,positive', [
    ('matrix([2,1],[1,2])', True, True),
    ('matrix([1,2],[2,1])', True, False),
    ('matrix([2,1],[0,2])', False, True),
    ('matrix([0,1],[0,0])', False, False),
    ('matrix([2,%i],[-%i,2])', True, True),
    ('matrix([1,%i],[%i,1])', False, True),
    ('matrix([1,2*%i],[-2*%i,1])', True, False),
    ('matrix([0,%i],[0,0])', False, False),
    ('matrix([1/2,%i/4],[-%i/4,1])', True, True),
    # Positive eigenvalues of a nonsymmetric matrix do not suffice.
    ('matrix([1,4],[0,1])', False, False),
    ('matrix([1,0,0],[0,-1,0],[0,0,-1])', True, False),
    ('matrix([2,1,0],[1,2,1],[0,1,2])', True, True),
    ('matrix([1,0,0],[0,1,0])', False, False),
])
def test_independent_matrix_properties_and_python_conjunction(answer, symmetric, positive):
    for checker, property_value in [('is_hermitian', symmetric),
                                     ('is_positive_definite', positive),
                                     ('is_hpd', symmetric and positive)]:
        for expected in (True, False):
            result = answer_test('PythonChecker', answer, str(expected).lower(), config(checker))
            assert result['valid']
            assert result['correct'] is (property_value == expected)


@pytest.mark.parametrize('answer,symmetric,positive', [
    ('matrix([2,1],[1,2])', True, True),
    ('matrix([1,2],[2,1])', True, False),
    ('matrix([2,1],[0,2])', False, True),
    ('matrix([0,1],[0,0])', False, False),
    ('matrix([2,%i],[-%i,2])', True, True),
    ('matrix([1,%i],[%i,1])', False, True),
    ('matrix([1,2*%i],[-2*%i,1])', True, False),
    ('matrix([0,%i],[0,0])', False, False),
    ('matrix([1/2,%i/4],[-%i/4,1])', True, True),
])
def test_prt_composition_awards_separate_marks_and_feedback(answer, symmetric, positive):
    q = import_xml(ROOT / 'examples/stack/symmetric-positive-definite-prt.xml')[0]
    result = grade(q, {'ansm': answer})
    assert result['score'] == (int(symmetric) + int(positive)) / 2
    assert result['prts']['symmetry']['score'] == int(symmetric)
    assert result['prts']['positivity']['score'] == int(positive)
    assert result['prts']['symmetry']['feedback']
    assert result['prts']['positivity']['feedback']
