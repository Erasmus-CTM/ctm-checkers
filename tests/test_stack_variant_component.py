"""Real source, leased review history and native STACK publication gate."""
import copy
import json
from pathlib import Path
import shutil
import sys

import pytest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'authoring'))

from ctm_variants import history
from ctm_variants.stack_component import parse_source,request,supervised_seed
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
