"""Generation recipes use real checker semantics and reject executable text."""
import json

import pytest

from ctm_checkers.browser import call
from ctm_checkers.math_exercise import compute_key
from ctm_checkers.math_exercise.generated import parse_math
from ctm_checkers.math_exercise.checks import check


def compute(op, answer, **recipe):
    return compute_key({'recipe': {'op': op, **recipe}, 'answer': answer, 'vars': 'x y', 'mode': 'equivalent'})


@pytest.mark.parametrize('op,answer,args', [
    ('value', '2/3', {'expr': 'Rational(2,3)'}),
    ('simplify', 'x+1', {'expr': '(x^2-1)/(x-1)'}),
    ('expand', 'x^2+2*x+1', {'expr': '(x+1)^2'}),
    ('factor', '(x-1)*(x+1)', {'expr': 'x^2-1'}),
    ('diff', '2*x', {'expr': 'x^2', 'var': 'x'}),
    ('integrate', 'x^3/3', {'expr': 'x^2', 'var': 'x'}),
    ('integrate', '1/3', {'expr': 'x^2', 'var': 'x', 'lower': '0', 'upper': '1'}),
    ('limit', '1', {'expr': 'sin(x)/x', 'var': 'x', 'point': '0'}),
    ('series', '1+x+x^2/2', {'expr': 'exp(x)', 'var': 'x', 'order': 3}),
    ('solve', '-1', {'expr': 'x^2-1', 'var': 'x', 'select': [0, 'x']}),
    ('solve', '2', {'expr': '[x+y-3,x-y-1]', 'variables': ['x','y'], 'select': [0, 'x']}),
    ('det', '-2', {'expr': 'Matrix([[1,2],[3,4]])'}),
    ('inv', '-2', {'expr': 'Matrix([[1,2],[3,4]])', 'select': [0,0]}),
    ('transpose', '3', {'expr': 'Matrix([[1,2],[3,4]])', 'select': [0,1]}),
    ('rank', '1', {'expr': 'Matrix([[1,2],[2,4]])'}),
    ('rref', '2', {'expr': 'Matrix([[1,2],[2,4]])', 'select': ['matrix',0,1]}),
    ('rref', '0', {'expr': 'Matrix([[1,2],[2,4]])', 'select': ['pivots',0]}),
    ('nullspace', '-2', {'expr': 'Matrix([[1,2],[2,4]])', 'select': [0,0,0]}),
    ('eigenvals', '2', {'expr': 'Matrix([[3,0],[0,3]])', 'select': [0,'multiplicity']}),
    ('matmul', '11', {'left': 'Matrix([[1,2]])', 'right': 'Matrix([[3],[4]])', 'select': [0,0]}),
    ('dot', '11', {'left': 'Matrix([1,2])', 'right': 'Matrix([3,4])'}),
    ('cross', '1', {'left': 'Matrix([1,0,0])', 'right': 'Matrix([0,1,0])', 'select': [2,0]}),
    ('norm', '5', {'expr': 'Matrix([3,4])'}),
])
def test_operation_and_explicit_component_agree_through_checker(op, answer, args):
    value = compute(op, answer, **args)
    assert value['computed'] is True
    assert parse_math(value['key'], 'x y') == parse_math(answer, 'x y') or op in ('simplify','expand','factor')


@pytest.mark.parametrize('text', [
    '__import__("os")', 'x.__class__', 'x.subs(x,1)', 'sin.__call__(x)',
    'open("/tmp/not-created","w")', 'eval("1")', 'sympify("1")',
    '(lambda: 1)()', '[x for x in [1]]', 'Matrix([[1]]).det()',
    'x; import os', 'getattr(x,"subs")', 'Function("f")', 'Symbol("x")',
    '2**100000', '[1]*100000', 'factorial(100000)',
])
def test_hostile_math_is_rejected_before_evaluation(text):
    with pytest.raises(ValueError):
        compute('value', '1', expr=text)
    with pytest.raises(ValueError):
        compute('value', text, expr='1')


@pytest.mark.parametrize('recipe', [
    {'op': 'exec', 'expr':'1'}, {'op':'value','expr':'1','python':'pass'},
    {'op':'diff','expr':'x','var':'x','order':1000},
    {'op':'integrate','expr':'x','var':'x','lower':'0'},
    {'op':'limit','expr':'x','var':'x','point':'0','direction':'bad'},
    {'op':'rref','expr':'Matrix([[1]])','select':['__class__']},
    {'op':'value','expr':'[1,2]'},
])
def test_recipe_schema_and_output_shape_are_bounded(recipe):
    with pytest.raises(ValueError):
        compute_key({'recipe':recipe,'answer':'1','vars':'x'})


def test_disagreement_never_becomes_an_unverified_key():
    with pytest.raises(ValueError, match='disagrees'):
        compute('diff', '3*x', expr='x^2', var='x')


def test_generated_admission_covers_both_sides_and_variables_without_changing_authored_strings():
    request = dict(student='1',correct='1',vars='',mode='equivalent',reject='',tolerance='',decplaces='',sigfigs='',form='',partial_credit=False,form_credit=.5,generated=True)
    for changed in ({'student':'x.subs(x,1)'},{'correct':'__import__("os")'},{'vars':'__builtins__'},{'reject':'x.subs(x,1)'}):
        with pytest.raises(ValueError): check({**request,**changed})
    assert check({**request,'mode':'string','student':'__text__','correct':'__text__'})['status']=='correct'


def test_native_and_browser_dispatch_share_recipe_admission_and_json_result():
    request = {'recipe': {'op':'diff','expr':'x^2','var':'x'},'answer':'2*x','vars':'x'}
    caller = {'_ctm_request':json.dumps(request)}
    assert json.loads(call('math_exercise.compute_key', caller)) == compute_key(request)
    assert caller == {}
    caller = {'_ctm_request':json.dumps({**request,'answer':'x.subs(x,1)'})}
    with pytest.raises(ValueError): call('math_exercise.compute_key',caller)
    assert caller == {}

@pytest.mark.parametrize('text,key,variables', [('21x','21*x','x'), ('2(x+1)','2*x+2','x'), ('(x+1)(x-1)','x**2-1','x'), ('2sin(x)','2*sin(x)','x'), ('sin x','sin(x)','x'), ('xy','x*y','x y'), ('cot x','cot(x)','x'), ('3!','6','')])
def test_generated_learner_notation_matches_original(text,key,variables):
    request=dict(student=text,correct=key,vars=variables,mode='equivalent',reject='',tolerance='',decplaces='',sigfigs='',form='',partial_credit=False,form_credit=.5)
    assert check(request)['status'] == 'correct'
    assert check({**request,'generated':True,'learner':True}) == check(request)

@pytest.mark.parametrize('text', ['2__import__("os")', '2(x.__class__)', '2open("file")', '2eval(x)', 'x.subs(x,1)', '2x # comment'])
def test_learner_route_still_rejects_python_syntax(text):
    from ctm_checkers.math_exercise.generated import admit_learner
    with pytest.raises(ValueError): admit_learner(text,'x')

def test_learner_route_never_relaxes_model_key_admission():
    from ctm_checkers.math_exercise.generated import admit_generated_check
    with pytest.raises(ValueError):
        admit_generated_check(dict(student='21x',correct='__import__("os")',vars='x',generated=True,learner=True))

@pytest.mark.parametrize('changes', [
    {'mode':'exact','student':'2/4','correct':'1/2'},
    {'form':'lowest_terms','student':'2/4','correct':'1/2'},
    {'mode':'numeric','student':'1.01','correct':'1','tolerance':'0.02'},
    {'mode':'numeric','student':'1.01','correct':'1','decplaces':'1'},
    {'mode':'numeric','student':'1.01','correct':'1','sigfigs':'1'},
    {'student':'x+x','correct':'2*x','reject':'2*x'},
    {'mode':'set','student':'1,3','correct':'1,2','partial_credit':True},
])
def test_generated_learner_grading_options_match_original(changes):
    request=dict(student='1',correct='1',vars='x',mode='equivalent',reject='',tolerance='',decplaces='',sigfigs='',form='',partial_credit=False,form_credit=.5)
    request.update(changes)
    assert check({**request,'generated':True,'learner':True}) == check(request)


def test_bind_data_binds_declared_givens_with_their_kinds():
    import sympy as sp
    from ctm_checkers.math_exercise import bind_data
    from ctm_checkers.variants import decode_context, question_context
    x = sp.Symbol('x', positive=True)
    context = question_context(['y'], {'h': x*sp.log(x), 'x0': sp.E, 'k': sp.Integer(2)}, {'y': 2*x - sp.E})
    request = {'names': ['h', 'x0'], 'data': {'h': 'x^2*log(x)', 'x0': '1/2'}, 'context': context, 'vars': 'x e'}
    bound = bind_data(request)
    fields, values, teacher, variant = decode_context(bound['context'])
    assert values['h'] == x**2*sp.log(x) and values['x0'] == sp.Rational(1, 2) and values['k'] == 2
    assert values['h'].free_symbols == {x}          # the original Symbol, assumptions included
    assert teacher == {'y': None} and variant is None
    assert bound['latex'] == {'h': r'x^{2} \ln{\left(x \right)}', 'x0': r'\frac{1}{2}'}
    # Through the browser entry with the same request.
    assert json.loads(call('math_exercise.bind_data', {'_ctm_request': json.dumps(request)}))['latex'] == bound['latex']


@pytest.mark.parametrize('names,data,reason', [
    (['h', 'x0'], {'h': 'x*log(x)'}, 'Supply exactly'),
    (['h'], {'h': 'x', 'x0': '1'}, 'Supply exactly'),
    (['k2'], {'k2': '1'}, 'not a declared'),
    (['h', 'x0'], {'h': '3', 'x0': '1'}, 'expression in'),
    (['h', 'x0'], {'h': 'x*log(x)', 'x0': 'x'}, 'exact real number'),
    (['h', 'x0'], {'h': 'x*log(x)', 'x0': 'I'}, 'exact real number'),
    (['h', 'x0'], {'h': 'x*log(x)', 'x0': 'oo'}, 'exact real number'),
    (['h', 'x0'], {'h': 'y*log(y)', 'x0': '1'}, 'Unsupported'),
    (['h', 'x0'], {'h': '__import__("os")', 'x0': '1'}, 'Unsupported'),
    (['h', 'x0'], {'h': 'x.__class__', 'x0': '1'}, 'Unsupported'),
    (['h', 'x0'], {'h': 'cot(x)', 'x0': '1'}, 'unsupported exact value'),
    (['h', 'x0'], {'h': ['x'], 'x0': '1'}, 'mathematical text'),
    (['A'], {'A': '1'}, 'not a declared'),
])
def test_bind_data_rejects_other_givens(names, data, reason):
    import sympy as sp
    from ctm_checkers.math_exercise import bind_data
    from ctm_checkers.variants import question_context
    x = sp.Symbol('x')
    context = question_context(['y'], {'h': x*sp.log(x), 'x0': sp.E, 'A': sp.Matrix([[1, 2]])}, {'y': 2*x - sp.E})
    with pytest.raises(ValueError, match=reason):
        bind_data({'names': names, 'data': data, 'context': context, 'vars': 'x'})


@pytest.mark.parametrize('text', ['(((9**100)**100)**100)**100', '((2^100)^100)^100', 'gamma(10**9)', 'gamma(-10**9)', 'Rational(1, 3**100)**100'])
def test_parse_math_bounds_growing_numbers(text):
    with pytest.raises(ValueError):
        parse_math(text, 'x')


@pytest.mark.parametrize('text', ['2^100', '(1/3)^20', 'gamma(5)', 'gamma(x)', 'x^(2^5)', 'E^100'])
def test_parse_math_keeps_ordinary_powers(text):
    parse_math(text, 'x')


GIVENS_CHECKER = '''def check(response, symbols):
    x = symbols["x"]
    h, x0 = response["variables"]["h"], response["variables"]["x0"]
    line = diff(h, x).subs(x, x0)*(x - x0) + h.subs(x, x0)
    return {"score": 1 if simplify(response["expressions"][0] - line) == 0 else 0}
'''


def test_givens_give_a_custom_checker_its_data_without_variants():
    from ctm_checkers.math_exercise import check_custom
    request = {'checker': GIVENS_CHECKER, 'vars': 'x', 'givens': 'h = x*log(x)\nx0 = E\n'}
    grade = lambda answer: check_custom(dict(request, response={'kind': 'expressions', 'raw': [answer]}))['score']
    assert grade('2*x-E') == 1 and grade('x') == 0


def test_bind_data_binds_to_givens():
    from ctm_checkers.math_exercise import bind_data
    from ctm_checkers.variants import decode_context
    bound = bind_data({'givens': 'h = x*log(x)\nx0 = E', 'fields': ['Tangent'], 'names': ['h', 'x0'],
                       'data': {'h': 'x^2*log(x)', 'x0': '1'}, 'vars': 'x'})
    fields, values, teacher, _ = decode_context(bound['context'])
    assert fields == ['Tangent'] and teacher == {'Tangent': None}
    assert str(values['h']) == 'x**2*log(x)' and values['x0'] == 1


@pytest.mark.parametrize('givens,reason', [
    ('h x*log(x)', 'one "name = expression"'),
    ('h = 1\nh = 2', 'distinct names'),
    ('log = 1', 'one "name = expression"'),
    ('x = 2', 'also a variable'),
    ('', 'one to sixteen'),
    ("h = __import__('os')", 'Unsupported'),
    ('h = x.__class__', 'Unsupported'),
])
def test_givens_reject_other_text(givens, reason):
    from ctm_checkers.math_exercise.generated import givens_context
    with pytest.raises(ValueError, match=reason):
        givens_context(givens, 'x', ['Tangent'])


def test_declarative_tests_see_the_givens():
    from ctm_checkers.math_exercise import run_question
    options = {'mode': 'custom', 'vars': 'x', 'checker': GIVENS_CHECKER, 'givens': 'h = x*log(x)\nx0 = E',
               'field-labels': 'Tangent', 'question': 'Tangent: _[2*x-E]',
               'tests': [{'name': 'right', 'answers': ['raw("2*x - E")'], 'expect': 'correct'},
                         {'name': 'wrong', 'answers': ['raw("x")'], 'expect': 'wrong'}]}
    run_question(options, '.')


def test_numeric_keys_use_the_field_precision():
    recipe = {'op': 'value', 'expr': '6.0/9.81'}
    key = lambda answer, **precision: compute_key({'recipe': recipe, 'answer': answer, 'vars': '', 'mode': 'numeric', **precision})
    assert key('0.61', tolerance='2%')['key'] == str(compute_key({'recipe': recipe, 'answer': '6.0/9.81', 'vars': '', 'mode': 'numeric'})['key'])
    assert key('0.6116', sigfigs='3')['computed']
    assert key('0.612', decplaces='2')['computed']
    with pytest.raises(ValueError, match='disagrees'):
        key('0.61')                      # no precision: as close as before
    with pytest.raises(ValueError, match='disagrees'):
        key('0.65', tolerance='2%')
    with pytest.raises(ValueError, match='precision'):
        key('0.61', tolerance=0.02)


def test_legacy_tests_see_the_givens():
    from ctm_checkers.math_exercise import run_question
    tests = ("def test(check, symbols):\n"
             "    x = symbols['x']\n"
             "    assert check({'expressions': [2*x - E]}, symbols)['score'] == 1\n"
             "    assert check({'expressions': [x]}, symbols)['score'] == 0\n")
    options = {'mode': 'custom', 'vars': 'x', 'checker': GIVENS_CHECKER, 'givens': 'h = x*log(x)\nx0 = E', 'tests': tests}
    run_question(options, '.')
    with pytest.raises(AssertionError):
        run_question(dict(options, givens='h = x\nx0 = 1'), '.')
