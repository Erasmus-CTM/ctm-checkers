"""Real source, leased review history and native STACK publication gate."""
import copy
import json
from pathlib import Path
import shutil
import sys

import pytest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'authoring'))

from ctm_variants import history
from ctm_variants.stack_component import current_source,parse_source,request,supervised_seed
from ctm_checkers.stack.importer import import_xml

XML=Path(__file__).resolve().parents[1]/'examples/stack/polynomial-expansion.xml'


def payload(tmp_path):
    shutil.copy2(XML,tmp_path/'question.xml')
    source='#| label: stack-one\n#| file: question.xml\n#| question: Expand a product (form-sensitive)\n#| review: true'
    (tmp_path/'page.qmd').write_text('```{.stack-question}\n'+source+'\n```\n')
    options,question=parse_source(source)
    return dict(version=1,projectRoot=str(tmp_path),file='page.qmd',sourceFile='page.qmd',label='stack-one',
        manifest='_variants/stack-one.yml',source=source,options=options,question=question)


def test_required_default_review_generation_approval_and_fresh_prose(tmp_path):
    p=payload(tmp_path)
    with pytest.raises(ValueError,match='at least one current approved'):request(p)
    review=request(dict(p,renderMode='review'))
    assert json.loads(review['payloadJSON'])==review['payload']
    assert review['records'] and all(v['proposal'] for v in review['payload']['variants'])
    assert not (tmp_path/p['manifest']).exists()
    generated=request(dict(p,action='generate',baseHash=None,renderMode='review'))
    first=generated['records'][0]
    approved=request(dict(p,action='decide',baseHash=generated['baseHash'],
        decision={'id':first['id'],'hash':first['hash'],'status':'approved'}))
    record=approved['payload']['variants'][0]
    assert record['n']==1 and record['id']=='seed=1' and len(record['hash'])==16 and not record['proposal']
    stored=(tmp_path/p['manifest']).read_bytes()
    before=record['hash']
    xml=tmp_path/'question.xml';xml.write_text(xml.read_text().replace('Expand and collect like terms:', 'Please expand and collect like terms:'))
    fresh=request(p)
    assert fresh['payload']['variants'][0]['hash']==before
    assert 'Please expand' in fresh['payload']['variants'][0]['display']['question_html']
    assert (tmp_path/p['manifest']).read_bytes()==stored
    with pytest.raises(ValueError,match='lease changed'):
        request(dict(p,action='generate',renderMode='review',baseHash=None))


def test_legacy_seed_and_unavailable_backend_are_explicit_errors(tmp_path):
    p=payload(tmp_path)
    p['source']+='\n#| seed: 17';p['options'],p['question']=parse_source(p['source'])
    with pytest.raises(ValueError,match='seed: was removed'):request(p)
    p=payload(tmp_path)
    with pytest.raises(ValueError,match='Maxima variant generator'):request(dict(p,backend='maxima'))


def test_candidate_deadline_is_a_build_failure(tmp_path):
    q=import_xml(XML)[0]
    with pytest.raises(ValueError,match='time budget'):supervised_seed(q,1,timeout=.001)


def test_quarto_absolute_source_stays_inside_project(tmp_path):
    p=payload(tmp_path)
    absolute=dict(p,sourceFile=str(tmp_path/'page.qmd'))
    fresh=current_source(absolute)
    assert fresh['file']==fresh['sourceFile']=='page.qmd'
    assert request(dict(absolute,renderMode='review'))['payload']['variants']
    outside=tmp_path.parent/'outside.qmd'
    with pytest.raises(ValueError):current_source(dict(p,sourceFile=str(outside)))
    with pytest.raises(ValueError):request(dict(p,sourceFile=str(outside),renderMode='review'))


def h1_payload(tmp_path):
    p=payload(tmp_path)
    p['source']+='''
#| checker: |
#|   def check(response, symbols):
#|       return 1 if response["answers"]["ans"] == response["teacher"]["ans"] else 0.5
#| checker-value: 2
#| tests:
#|   - name: teacher
#|     answers: {ans: 'expand(ta)'}
#|     expect: correct
#|   - name: weighted wrong answer
#|     answers: {ans: 'raw("0")'}
#|     expect: partial
#|     score: 0.3333333333
'''
    p['options'],p['question']=parse_source(p['source'])
    (tmp_path/'page.qmd').write_text('```{.stack-question}\n'+p['source']+'\n```\n')
    return p


def test_h1_native_proof_runs_declarative_tests_and_binds_runtime_identity(tmp_path):
    p=h1_payload(tmp_path)
    result=request(dict(p,renderMode='review'))
    card=result['payload'];variant=card['variants'][0]
    assert card['common']['checker']['value']==2
    assert 'def check(response, symbols)' in card['common']['checker']['source']
    assert {key:variant['plan'][key] for key in ('n','id','hash')}=={key:variant[key] for key in ('n','id','hash')}
    tests=result['records'][0]['tests']['qtests']['results']
    assert {'teacher','weighted wrong answer'} <= {row['testcase'] for row in tests}
    # A changed assertion must fail actual grading instead of changing approval
    # content or silently dropping the seed.
    p['source']=p['source'].replace('score: 0.3333333333','score: 1')
    p['options'],p['question']=parse_source(p['source'])
    with pytest.raises(ValueError,match='weighted wrong answer'):
        request(dict(p,renderMode='review'))


def test_h1_rejects_registry_option_and_invalid_weight_before_generation(tmp_path):
    p=payload(tmp_path);p['source']+='\n#| python-checkers: old.py'
    p['options'],p['question']=parse_source(p['source'])
    with pytest.raises(ValueError,match='python-checkers: was removed'):
        request(dict(p,renderMode='review'))
    p=h1_payload(tmp_path);p['source']=p['source'].replace('checker-value: 2','checker-value: 0')
    p['options'],p['question']=parse_source(p['source'])
    with pytest.raises(ValueError,match='positive finite'):
        request(dict(p,renderMode='review'))
