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
    with pytest.raises(ValueError,match='backend mismatch: requested maxima, active sympy'):request(dict(p,backend='maxima'))


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


def test_approval_rechecks_assigned_checker_identity_before_saving(tmp_path):
    p=payload(tmp_path)
    p['source']+='\n#| checker: |\n#|   def check(response, symbols):\n#|       return response["variant"]["n"] is None\n'
    p['options'],p['question']=parse_source(p['source'])
    (tmp_path/'page.qmd').write_text('```{.stack-question}\n'+p['source']+'\n```\n')
    generated=request(dict(p,action='generate',baseHash=None,renderMode='review'))
    row=generated['records'][0]
    path=tmp_path/p['manifest'];before=path.read_bytes()
    with pytest.raises(ValueError,match='teacher answers must score 1'):
        request(dict(p,action='decide',baseHash=generated['baseHash'],
            decision={'id':row['id'],'hash':row['hash'],'status':'approved'}))
    assert path.read_bytes()==before


def test_assigned_identity_checker_keeps_the_per_seed_deadline():
    q=import_xml(XML,checker='''def check(response,symbols):
    if response["variant"]["n"] is not None:
        while True:
            pass
    return True
''')[0]
    with pytest.raises(ValueError,match='time budget'):
        supervised_seed(q,1,timeout=.05,identity={'n':1,'id':'seed=1','hash':'0'*16})

class NativeStub:
    id='maxima'
    supports_authored_tests=True
    def __init__(self,mutate=None,resource_failure=False):
        self.seeds=[];self.mutate=mutate;self.resource_failure=resource_failure
    def __enter__(self):return self
    def __exit__(self,*args):pass
    def load_question(self,source,title,options,*,authored_tests=None):
        self.authored=authored_tests
        return {'source':source.read_text(),'tests':authored_tests}
    def seed_record(self,question,seed,timeout=30,*,identity=None):
        from ctm_variants.model import candidate,snapshot
        self.seeds.append(seed)
        row=candidate('seed='+str(seed),snapshot([str(seed)],{'ans':'1'},
            {'component':'ctm-stack','backend':self.id}),data={'backend':self.id,'plan':{'seed':seed}},
            tests={'passed':True})
        identity={key:row[key] for key in ('id','hash')}
        row['tests']['authored']={'passed':True,'candidate':identity,'results':[
            {'name':case['name'],'declaration':copy.deepcopy(case),'candidate':dict(identity),'passed':True}
            for case in question['tests'] or []]}
        if self.mutate:self.mutate(row)
        return row
    def propose(self,question,count,*,start,resolve_seed,**kwargs):
        return {'records':[resolve_seed(question,start)],'skipped':[],'nextSeed':start+1}
    def card_data(self,question,records,entries,*,identifier,identity_verifier,**kwargs):
        from ctm_variants.model import classify
        rows=classify(entries,records)['entries'];out=[]
        for record in records:
            row=next((r for r in rows if r['candidate']==record),None)
            n=row['entry']['n'] if row and row['state'] in ('current','moved') else None
            identity={'n':n,'id':record['id'],'hash':record['hash']}
            assert identity_verifier(question,record['data']['plan']['seed'],identity)['hash']==record['hash']
            out.append(dict(identity,proposal=n is None))
        return {'common':{},'variants':out}
    def runtime_resources(self):
        if self.resource_failure:raise ValueError('runtime resources unavailable')
        return {'root':'stub-runtime'}


def native_payload(tmp_path):
    p=payload(tmp_path);p['source']+='\n#| cas: maxima\n#| variants: 1'
    p['options'],p['question']=parse_source(p['source'])
    (tmp_path/'page.qmd').write_text('```{.stack-question}\n'+p['source']+'\n```\n')
    return p


def test_native_backend_generate_decide_publish_with_authored_test_evidence(tmp_path):
    p=native_payload(tmp_path);p['source']+='\n#| tests: |\n#|   - name: native teacher\n#|     answers: {ans: 1}\n#|     expect: correct'
    p['options'],p['question']=parse_source(p['source'])
    (tmp_path/'page.qmd').write_text('```{.stack-question}\n'+p['source']+'\n```\n')
    stub=NativeStub();generated=request(dict(p,action='generate',baseHash=None,renderMode='review'),backend=stub)
    assert stub.authored[0]['name']=='native teacher'
    first=generated['records'][0]
    approved=request(dict(p,action='decide',baseHash=generated['baseHash'],decision={
        'id':first['id'],'hash':first['hash'],'status':'approved'}),backend=NativeStub())
    published=request(p,backend=NativeStub())
    assert published['payload']['variants']==approved['payload']['variants']
    assert published['payload']['variants'][0]['n']==1
    assert published['nativeRuntime']['root']=='stub-runtime'


@pytest.mark.parametrize('mutate,message',[
    (lambda r:r['data'].update(backend='sympy'),'backend mismatch'),
    (lambda r:r['snapshot']['grading'].update(backend='sympy'),'backend mismatch'),
    (lambda r:r['data']['plan'].update(seed=2),'seed mismatch'),
])
def test_native_backend_record_bindings_reject_generated_and_replayed_proofs(tmp_path,mutate,message):
    p=native_payload(tmp_path)
    with pytest.raises(ValueError,match=message):
        request(dict(p,action='generate',baseHash=None,renderMode='review'),backend=NativeStub(mutate))
    assert not (tmp_path/p['manifest']).exists()
    good=request(dict(p,action='generate',baseHash=None,renderMode='review'),backend=NativeStub())
    stored=(tmp_path/p['manifest']).read_bytes()
    with pytest.raises(ValueError,match=message):request(dict(p,renderMode='review'),backend=NativeStub(mutate))
    assert (tmp_path/p['manifest']).read_bytes()==stored


def test_backend_move_keeps_history_never_replays_other_backend_and_needs_approval(tmp_path):
    p=payload(tmp_path);p['source']+='\n#| variants: 1';p['options'],p['question']=parse_source(p['source'])
    (tmp_path/'page.qmd').write_text('```{.stack-question}\n'+p['source']+'\n```\n')
    generated=request(dict(p,action='generate',baseHash=None,renderMode='review'))
    first=generated['records'][0]
    approved=request(dict(p,action='decide',baseHash=generated['baseHash'],decision={
        'id':first['id'],'hash':first['hash'],'status':'approved'}))
    old=copy.deepcopy(approved['manifest'])
    p['source']+='\n#| cas: maxima';p['options'],p['question']=parse_source(p['source'])
    (tmp_path/'page.qmd').write_text('```{.stack-question}\n'+p['source']+'\n```\n')
    stub=NativeStub()
    with pytest.raises(ValueError,match='at least one current approved'):request(p,backend=stub)
    assert stub.seeds==[]
    new=request(dict(p,action='generate',renderMode='review',baseHash=approved['baseHash']),backend=NativeStub())
    assert new['manifest']['decisions']==old['decisions'] and new['manifest']['events']==old['events']
    assert new['manifest']['proposals'][:len(old['proposals'])]==old['proposals']
    assert new['records'][0]['hash']!=first['hash'] and new['records'][0]['status']=='undecided'
    with pytest.raises(ValueError,match='at least one current approved'):request(p,backend=NativeStub())
    row=new['records'][0]
    decided=request(dict(p,action='decide',baseHash=new['baseHash'],decision={
        'id':row['id'],'hash':row['hash'],'status':'approved'}),backend=NativeStub())
    assert decided['payload']['variants'][0]['n']==1
    assert decided['manifest']['events'][-1]['before']==old['decisions']
    assert decided['manifest']['decisions'][0]['snapshot']['grading']['backend']=='maxima'


def test_native_backend_must_support_tests_and_supply_per_candidate_evidence(tmp_path):
    p=native_payload(tmp_path);p['source']+='\n#| tests: |\n#|   - name: teacher\n#|     answers: {ans: 1}\n#|     expect: correct'
    p['options'],p['question']=parse_source(p['source'])
    unsupported=NativeStub();unsupported.supports_authored_tests=False
    with pytest.raises(ValueError,match='does not support authored tests'):request(dict(p,renderMode='review'),backend=unsupported)
    with pytest.raises(ValueError,match='omitted passing authored-test evidence'):
        request(dict(p,renderMode='review'),backend=NativeStub(lambda r:r.update(tests={})))


def test_runtime_resources_are_checked_before_writing_history(tmp_path):
    p=native_payload(tmp_path)
    with pytest.raises(ValueError,match='runtime resources unavailable'):
        request(dict(p,action='generate',baseHash=None,renderMode='review'),backend=NativeStub(resource_failure=True))
    assert not (tmp_path/p['manifest']).exists()


@pytest.mark.parametrize('mutate',[
    lambda p:p.pop('candidate'),
    lambda p:p['candidate'].update(hash='0'*16),
    lambda p:p['results'][0].pop('candidate'),
    lambda p:p['results'][0].update(candidate={'id':'seed=2','hash':'0'*16}),
    lambda p:p['results'][0].pop('declaration'),
    lambda p:p['results'][0]['declaration'].update(expect='wrong'),
    lambda p:p['results'].append(None),
])
def test_native_authored_evidence_is_bound_on_generation_and_replay(tmp_path,mutate):
    p=native_payload(tmp_path);p['source']+='\n#| tests: |\n#|   - name: teacher\n#|     answers: {ans: 1}\n#|     expect: correct'
    p['options'],p['question']=parse_source(p['source'])
    (tmp_path/'page.qmd').write_text('```{.stack-question}\n'+p['source']+'\n```\n')
    poison=lambda row:mutate(row['tests']['authored'])
    with pytest.raises(ValueError,match='bound to the current candidate/declarations'):
        request(dict(p,action='generate',baseHash=None,renderMode='review'),backend=NativeStub(poison))
    good=request(dict(p,action='generate',baseHash=None,renderMode='review'),backend=NativeStub())
    before=(tmp_path/p['manifest']).read_bytes()
    with pytest.raises(ValueError,match='bound to the current candidate/declarations'):
        request(dict(p,renderMode='review'),backend=NativeStub(poison))
    assert (tmp_path/p['manifest']).read_bytes()==before


def test_maxima_history_cannot_move_back_to_sympy(tmp_path):
    p=native_payload(tmp_path)
    request(dict(p,action='generate',baseHash=None,renderMode='review'),backend=NativeStub())
    before=(tmp_path/p['manifest']).read_bytes()
    p['source']=p['source'].replace('#| cas: maxima','')
    p['options'],p['question']=parse_source(p['source'])
    with pytest.raises(ValueError,match='one-way.*cannot move maxima to sympy'):
        request(dict(p,renderMode='review'))
    assert (tmp_path/p['manifest']).read_bytes()==before


def test_malformed_replay_tape_names_the_active_backend(tmp_path,monkeypatch):
    p=native_payload(tmp_path)
    generated=request(dict(p,action='generate',baseHash=None,renderMode='review'),backend=NativeStub())
    broken=copy.deepcopy(generated['manifest']);broken['proposals'][0]['tape']={'bad':1}
    monkeypatch.setattr(history,'load',lambda *_:(broken,generated['baseHash']))
    with pytest.raises(ValueError,match='invalid STACK replay tape for backend maxima'):
        request(dict(p,renderMode='review'),backend=NativeStub())


def test_backend_cannot_mutate_the_current_declaration_through_load_question(tmp_path):
    class MutatingStub(NativeStub):
        def load_question(self,*args,**kwargs):
            q=super().load_question(*args,**kwargs)
            q['tests'][0]['answers']['ans']='changed'
            return q
    p=native_payload(tmp_path);p['source']+='\n#| tests: |\n#|   - name: teacher\n#|     answers: {ans: 1}\n#|     expect: correct'
    p['options'],p['question']=parse_source(p['source'])
    with pytest.raises(ValueError,match='bound to the current candidate/declarations'):
        request(dict(p,renderMode='review'),backend=MutatingStub())
