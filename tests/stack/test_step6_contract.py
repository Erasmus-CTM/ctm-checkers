"""Step 6's JSON preparation, error origins and safe presentation boundary."""
import hashlib
import json
from pathlib import Path

import pytest

from ctm_checkers import API
from ctm_checkers.stack import page
from ctm_checkers.stack.cli import main, prepare, render
from ctm_checkers.stack.engine import grade, instantiate
from ctm_checkers.stack.importer import import_xml
from ctm_checkers.stack.messages import feedback_html, message

ROOT = Path(__file__).resolve().parents[2]
XML = ROOT / 'examples/stack/polynomial-expansion.xml'
NAME = 'Expand a product (form-sensitive)'


def request():
    q = import_xml(XML)[0]
    return {'question': q, 'variant': instantiate(q, 17), 'answers': {'ans': 'x^2+8*x+15'}}


def test_prepare_has_no_card_shell_and_retains_the_real_model():
    data = prepare(str(XML), NAME, 'q', 2, 17, True)
    old = render(str(XML), NAME, 'q', 2, 17, True)
    legacy = json.loads(old.split('class="stack-sympy-data">')[1].split('</script>')[0])
    assert data['version'] == 2 and data['backend']['planSchema'] == 1
    assert data['backend']['id'] == 'sympy' and data['backend']['runtimeHash'] is None
    assert data['backend']['question'] == legacy['question']
    assert data['common'] == {'inputs': legacy['question']['inputs'],
                              'qtests': legacy['question']['qtests'], 'checker': None}
    assert [v['plan'] for v in data['variants']] == legacy['variants']
    for index, variant in enumerate(data['variants'], 1):
        assert variant['n'] == index and variant['id'] == str(16 + index)
        canonical = json.dumps(variant['plan'], sort_keys=True, ensure_ascii=False, separators=(',', ':'))
        assert variant['hash'] == hashlib.sha256(canonical.encode()).hexdigest()
        assert variant['display']['question_html'] == variant['plan']['question_html']
    assert set(data) == {'version', 'id', 'common', 'backend', 'variants', 'review'}
    assert API == '1.1'


def test_prepare_cli_only_writes_json_or_an_error(capsys):
    args = ['prepare', '--file', str(XML), '--question', NAME, '--id', 'q', '--variants', '1']
    assert main(args) == 0
    captured = capsys.readouterr()
    assert json.loads(captured.out)['version'] == 2 and captured.err == ''
    args[args.index('--question') + 1] = 'missing question'
    assert main(args) == 2
    captured = capsys.readouterr()
    assert captured.out == '' and 'expected exactly one question' in captured.err


def test_learner_author_and_runtime_faults_keep_distinct_origins(monkeypatch):
    value = request()
    value['answers']['ans'] = '('
    invalid = page.grade(value)
    assert invalid['ok'] and invalid['result']['status'] == 'invalid'
    assert invalid['result']['inputs']['ans']['message']['code'] == 'stack_input_invalid'
    value = request()
    value['question']['prts'][0]['nodes'][0]['test'] = 'UnsupportedTest'
    error = page.grade(value)['errorDetail']
    assert error['kind'] == 'author' and error['code'] == 'stack_question_error'
    assert error['args']['question'] == NAME
    assert 'node[0]' in error['args']['location']
    def broken(*args, **kwargs):
        raise TypeError('internal implementation failure')
    monkeypatch.setattr('ctm_checkers.stack.engine.answer_test', broken)
    with pytest.raises(TypeError, match='internal implementation'):
        page.grade(request())


def test_malformed_present_plan_is_an_author_error():
    value = request()
    del value['question']['prts']
    for call in (page.validate, page.grade, page.tests):
        error = call(value)['errorDetail']
        assert error['kind'] == 'author' and error['args']['location'] == 'plan/question/prts'


@pytest.mark.parametrize('change', [
    lambda r: r['question']['inputs'][0].update(teacher=None),
    lambda r: r['question']['inputs'][0].pop('forbidwords'),
    lambda r: r['variant']['env'].update(a=None),
    lambda r: r['question']['prts'][0]['nodes'][0]['true'].update(score='oops'),
    lambda r: r['question']['prts'][0]['nodes'][0]['true'].update(score=10**1000),
    lambda r: r['question']['inputs'][0].update(teacher='1/0'),
    lambda r: r['question']['inputs'][0].update(teacher='('),
    lambda r: r['variant']['env'].update(a='1/0'),
    lambda r: r['question']['inputs'][0].update(checkanswertype='false'),
    lambda r: r['question']['prts'][0]['nodes'][0]['true'].update(next=0),
    lambda r: r['question']['qtests'][0]['expected'].update(prt1={'score': 'oops', 'penalty': 0, 'note': ''}),
])
def test_author_plan_faults_are_not_learner_invalid_results(change):
    for call in (page.validate, page.grade, page.tests):
        value = request()
        value['question']['inputs'][0]['checkanswertype'] = True
        change(value)
        result = call(value)
        assert result['ok'] is False and isinstance(result['error'], str)
        assert result['error'] == result['errorDetail']['message']
        assert result['errorDetail']['kind'] == 'author'


@pytest.mark.parametrize('exception', [TypeError, ValueError, ZeroDivisionError])
def test_unexpected_parser_implementation_faults_are_not_learner_results(monkeypatch, exception):
    def broken(*args, **kwargs):
        raise exception('internal parsing failure')
    monkeypatch.setattr('ctm_checkers.stack.engine._parse_answer', broken)
    for call in (page.validate, page.grade):
        with pytest.raises(exception, match='internal parsing failure'):
            call(request())


def test_plain_messages_and_mathematical_arguments_cannot_inject_markup():
    assert feedback_html({'feedback': '<img onerror="bad">'}) == '&lt;img onerror=&quot;bad&quot;&gt;'
    item = message('ATSets_wrongentries', 'Extra elements: x**2.',
                   elements=[{'text': 'x**2', 'latex': r'x^{2}<img>'}])
    rendered = feedback_html({'feedback': item['text'], 'messages': [item]})
    assert rendered == r'Extra elements: \(x^{2}&lt;img&gt;\).'
    assert '<img>' not in rendered and '**' not in rendered


def test_real_set_feedback_keeps_verdict_and_uses_mathematical_arguments():
    question = import_xml(ROOT / 'examples/stack/finite-collections.xml')[0]
    variant = instantiate(question, 17)
    a = variant['env']['a']
    answers = {'sequence': f'[{a},2*x]', 'members': f'{{2*x,{a}}}', 'explained': '{x^2}'}
    result = grade(question, answers, variant=variant)
    prt = result['prts']['explained']
    assert result['status'] == 'graded' and prt['score'] == 0
    extra = next(item for item in prt['messages'] if item['code'] == 'ATSets_wrongentries')
    assert extra['args']['elements'] == [{'text': 'x**2', 'latex': 'x^{2}'}]
    assert r'\(x^{2}\)' in prt['feedback'] and 'x**2' not in prt['feedback']


def test_feedback_parts_preserve_authored_and_stock_message_positions():
    question = import_xml(ROOT / 'examples/stack/finite-collections.xml')[0]
    authored = 'Repeated elements were removed from the set.'
    prt = next(item for item in question['prts'] if item['name'] == 'explained')
    prt['nodes'][0]['false']['feedback'] = authored
    variant = instantiate(question, 17)
    a = variant['env']['a']
    answers = {'sequence': f'[{a},2*x]', 'members': f'{{2*x,{a}}}', 'explained': '{x^2,x^2}'}
    result = grade(question, answers, variant=variant)['prts']['explained']
    parts = result['feedbackParts']
    assert parts[0] == {'html': authored}
    assert parts[1] == {'message': {'code': 'ATSets_duplicates', 'args': {}, 'text': authored}}
    assert [part['message']['code'] for part in parts[1:]] == [
        'ATSets_duplicates', 'ATSets_wrongentries', 'ATSets_missingentries']
    rebuilt = ' '.join(part['html'] if 'html' in part else feedback_html(
        {'feedback': part['message']['text'], 'messages': [part['message']]}) for part in parts)
    assert rebuilt == result['feedback']
    assert [part['message'] for part in parts if 'message' in part] == result['messages']
