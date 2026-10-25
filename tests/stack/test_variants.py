"""STACK owns its RNG, proof records and content-first decision identity."""
import copy
from pathlib import Path
import sys

import pytest

sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'authoring'))

from ctm_checkers.stack.importer import import_xml
from ctm_checkers.stack.variants import propose, seed_record
from ctm_variants import history
from ctm_variants.model import candidate, classify, decide, snapshot

XML=Path(__file__).resolve().parents[2]/'examples/stack/polynomial-expansion.xml'


def question():
    q=import_xml(XML)[0]
    q['questionnote']='a={@a@}, b={@b@}'
    return q


def test_records_bind_real_question_tests_and_teacher_vectors():
    q=question();row=seed_record(q,17)
    assert row['id']=='seed=17' and len(row['hash'])==16
    assert row['tests']['passed'] and row['tests']['qtests']['passed']
    assert row['tests']['teacher']['score']==1
    assert all(p['score']==1 for p in row['tests']['teacher']['prts'].values())
    assert row['data']['plan']['seed']==17
    assert dict(row['snapshot']['teacher'])==row['data']['teacherInputs']


def test_authored_full_mark_vector_keeps_required_decimal_syntax():
    q=import_xml(XML.with_name('numerical-measurement.xml'))[0]
    row=seed_record(q,1)
    assert row['tests']['teacher']['score']==1
    assert row['data']['teacherInputs']['reported']=='35/2'
    assert row['tests']['qtests']['passed']


def test_prose_unused_helpers_and_variable_renames_preserve_approval_content():
    q=question();before=seed_record(q,17)
    changed=copy.deepcopy(q);changed['questiontext']='Typo fixed. '+changed['questiontext']
    changed['variables']+='\nunused:42;'
    assert seed_record(changed,17)['hash']==before['hash']
    import re
    def rename(value):
        if isinstance(value,str):return re.sub(r'\ba\b','renamed',value)
        if isinstance(value,list):return [rename(v) for v in value]
        if isinstance(value,dict):return {k:rename(v) for k,v in value.items()}
        return value
    renamed=rename(q)
    assert seed_record(renamed,17)['hash']==before['hash']
    changed['questiontext']+=' Extra generated value: {@unused@}.'
    assert seed_record(changed,17)['hash']!=before['hash']
    changed=copy.deepcopy(q);changed['prts'][0]['value']=2
    assert seed_record(changed,17)['hash']!=before['hash']


def test_proposals_start_at_one_deduplicate_notes_and_never_import_moodle_seeds():
    q=question();q['deployedseeds']=[999]
    batch=propose(q,3,attempt_limit=30)
    assert batch['records'][0]['id']=='seed=1'
    assert len(batch['records'])==3
    assert len({r['note'] for r in batch['records']})==3
    constant=import_xml(XML)[0]
    assert len(propose(constant)['records'])==1


def test_failed_question_tests_are_skipped_and_cannot_become_proof_records():
    q=question();q['qtests'][0]['expected']['prt1']['score']=0
    with pytest.raises(ValueError,match='question tests failed'):seed_record(q,1)
    batch=propose(q,2,attempt_limit=3)
    assert batch['records']==[] and len(batch['skipped'])==3


def test_content_first_seed_swap_retains_numbers_and_history():
    def row(seed,math):return candidate(f'seed={seed}',snapshot([math],{},dict(component='ctm-stack',backend='sympy')))
    a,b=row(1,'A'),row(2,'B')
    value=history.append_proposals(history.empty('stack'),[{'record':r,'tape':{'seed':int(r['id'][5:])}} for r in (a,b)])
    value=history.decision(value,[a,b],a['id'],'approved')
    value=history.decision(value,[a,b],b['id'],'rejected')
    x,y=row(2,'A'),row(1,'B')
    value=history.append_proposals(value,[{'record':r,'tape':{'seed':int(r['id'][5:])}} for r in (x,y)])
    rows=classify(value['decisions'],[x,y])['entries']
    assert [(r['entry']['n'],r['state'],r['candidate']['id']) for r in rows]==[(1,'moved','seed=2'),(2,'moved','seed=1')]
    value=history.decision(value,[x,y],'seed=1','approved')
    assert [(e['n'],e['id'],e['status']) for e in value['decisions']]==[(1,'seed=2','approved'),(2,'seed=1','approved')]
    history.validate(value)
    assert history.publication(value['decisions'],[x,y])['ids']==['seed=2','seed=1']


def test_gone_content_keeps_its_number_when_its_old_seed_is_reused():
    def row(seed,math):return candidate(f'seed={seed}',snapshot([math],{},dict(component='ctm-stack',backend='sympy')))
    a,b=row(1,'A'),row(2,'B');entries=decide([], [a,b],a['id'],'approved');entries=decide(entries,[a,b],b['id'],'approved')
    moved=row(2,'A');updated=decide(entries,[moved],moved['id'],'approved')
    assert [(r['entry']['n'],r['state']) for r in classify(updated,[moved])['entries']]==[(1,'current'),(2,'gone')]
