"""SymPy-owned STACK seed records, native authoring only (variants decision 20).

Moodle's deployed seeds are deliberately not imported here. Maxima supplies
its own generator and runtime provenance when that backend is available.
"""
from __future__ import annotations

import copy
import html
import re
import time

import sympy as sp

from .engine import (_environment, _input_uses_written_form, _qtest_answer,
                     _source, assignments, evaluate, grade, instantiate, run_question_tests)
from .stack_data import STACK_COMMIT
from .expressions import parse
from .engine import _definitions


class SeedRejected(ValueError):
    """A supported seed fails its actual authored or mandatory teacher tests."""


def finite_random_bound(question):
    """A conservative upper bound for independent literal random choices.

    This only establishes exhaustion, never changes seed generation. Dynamic
    bounds remain unknown and retain the normal attempt/time diagnostics.
    """
    total=1
    def visit(node):
        nonlocal total
        if node.kind=='call' and node.value in ('rand','rand_with_step'):
            def literal(child):
                if child.kind not in ('number','list','unary'):raise ValueError()
                for nested in child.children:literal(nested)
            for child in node.children:literal(child)
            args=[evaluate(child) for child in node.children]
            if node.value=='rand':size=len(args[0]) if isinstance(args[0],list) else int(args[0])
            else:size=len(range(int(args[0]),int(args[1])+1,int(args[2])))
            if size<1:raise ValueError()
            total*=size
        for child in node.children:visit(child)
    try:
        for source in _definitions(question).values():visit(parse(source))
    except (ValueError,TypeError,OverflowError):return None
    return total


def _math(source, env):
    return [_source(evaluate(match, env)) for match in re.findall(r"\{@(.*?)@\}", source, re.S)]


def seed_record(question, seed):
    """Resolve and test a seed using the actual STACK engine, never a surrogate."""
    from ctm_variants.model import candidate, snapshot
    if type(seed) is not int or seed < 1 or seed > 2147483647:
        raise ValueError("STACK seed must be an integer from 1 to 2147483647")
    variant = instantiate(question, seed)
    env = _environment(question, variant)
    teacher = {i['name']: _qtest_answer(question, i['teacher'], env,
        preserve_form=_input_uses_written_form(question, i['name'])) for i in question['inputs']}
    tests = run_question_tests(question, variants=[variant])
    if not tests['passed']:
        raise SeedRejected(f"seed={seed}: XML question tests failed")
    # An authored all-PRT full-mark vector can carry required written syntax
    # (for example 17.50 rather than the equal rational 35/2). The design adds
    # the synthetic teacher vector only when XML supplies no such test.
    prt_names={p['name'] for p in question['prts']}
    full_test=next((case for case in question.get('qtests',[])
        if prt_names <= case.get('expected',{}).keys()
        and all(case['expected'][name].get('score')==1 for name in prt_names)),None)
    tested_teacher=({name:_qtest_answer(question,source,env,preserve_form=_input_uses_written_form(question,name))
        for name,source in full_test['inputs'].items()} if full_test else teacher)
    teacher_grade = grade(question, tested_teacher, variant=variant)
    if (teacher_grade['status'] != 'graded' or teacher_grade['score'] != 1
            or any(p['score'] != 1 for p in teacher_grade['prts'].values())):
        raise SeedRejected(f"seed={seed}: teacher answers must score 1 on every response tree")
    segments = []
    for field in ('questiontext', 'generalfeedback', 'specificfeedback', 'questionnote'):
        segments.extend(_math(question.get(field, ''), env))
    # Question-note prose is presentation; generated values across the CASText
    # and all answer-test branches are the approval content.
    grading = {key: copy.deepcopy(value) for key, value in question.items()
        if key not in {'name','variables','questiontext','generalfeedback','specificfeedback','questionnote','deployedseeds','inputs','prts','qtests'}}
    grading.update(component='ctm-stack', backend='sympy', stackRevision=STACK_COMMIT)
    grading['inputs'] = []
    for inp in question['inputs']:
        item={key:copy.deepcopy(value) for key,value in inp.items() if key not in {'boxsize','syntaxhint','showvalidation'}}
        item['teacher']=teacher[inp['name']]; grading['inputs'].append(item)
    grading['prts'] = []
    symbolic = {**env, **{i['name']:sp.Symbol(i['name']) for i in question['inputs']}}
    for prt in question['prts']:
        penv = assignments(prt.get('feedbackvariables',''), symbolic)
        item={key:copy.deepcopy(value) for key,value in prt.items() if key not in {'nodes','feedbackvariables'}}
        item['nodes']=[]
        for node in prt['nodes']:
            resolved=copy.deepcopy(node)
            for key in ('student','teacher'):
                resolved[key]=_qtest_answer(question,node[key],penv,preserve_form=node['test']=='EqualComAss')
            for branch in ('true','false'):
                segments.extend(_math(node[branch].get('feedback',''),penv))
                resolved[branch].pop('feedback',None)
            item['nodes'].append(resolved)
        grading['prts'].append(item)
    note=html.unescape(re.sub('<[^>]*>','',variant.get('questionnote_html',''))).strip()
    probes=[]
    for inp in question['inputs']:
        if inp.get('type')!='algebraic':continue
        for answer in ('0','1'):
            if answer==teacher[inp['name']]:continue
            result=grade(question,{**tested_teacher,inp['name']:answer},variant=variant)
            probes.append({'input':inp['name'],'answer':answer,'result':result,
                'warning':result.get('score')==1})
    return candidate(f'seed={seed}',snapshot(segments,teacher,grading,variant['env']),note=note,
        data={'backend':'sympy','plan':variant,'teacherInputs':teacher},
        tests={'passed':True,'qtests':tests,'teacher':teacher_grade,'wrongProbes':probes})


def propose(question, count=25, *, start=1, retained=(), attempt_limit=5000, elapsed_limit=120, resolve_seed=seed_record):
    """Propose increasing seeds, deduplicating notes; test failures are fatal."""
    if type(count) is not int or not 1 <= count <= 100:
        raise ValueError('STACK variant batch must be between 1 and 100')
    if type(start) is not int or start < 1:
        raise ValueError('STACK proposals start at a positive seed')
    deadline=time.monotonic()+elapsed_limit
    records,skipped=[],[]
    notes={row['note'] for row in retained}
    known={row['id'] for row in retained}
    bound=finite_random_bound(question)
    target=min(count,max(0,bound-len(notes))) if bound is not None else count
    if target==0:return {'records':[],'skipped':[],'nextSeed':start}
    if notes and '{@' not in question.get('questionnote','') and '[[' not in question.get('questionnote',''):
        return {'records':[],'skipped':[],'nextSeed':start}
    for seed in range(start,start+attempt_limit):
        if time.monotonic()>deadline:
            raise ValueError('STACK variant generation exceeded its aggregate budget')
        if f'seed={seed}' in known:continue
        try:row=resolve_seed(question,seed)
        except SeedRejected as error:
            raise SeedRejected(f"{question['name']}: {error}") from error
        if row['note'] in notes:
            skipped.append({'id':row['id'],'reason':'repeated question note'});continue
        records.append(row);notes.add(row['note'])
        if len(records)==target:break
        if '{@' not in question.get('questionnote','') and '[[' not in question.get('questionnote',''):break
        # A deterministic question with no random source has just one variant.
        if not re.search(r'\brand(?:_|\s*\()',question.get('variables','')):break
    return {'records':records,'skipped':skipped,'nextSeed':seed+1}


def card_data(question, records, entries, *, identifier, review=False):
    """One backend contract; numbering is shared review history's decision."""
    from ctm_variants.model import classify,digest
    rows=classify(entries,records)['entries']
    by_id={r['candidate']['id']:r for r in rows if r['candidate'] is not None}
    variants=[]
    for record in records:
        row=by_id.get(record['id'])
        approved=row is not None and row['state'] in ('current','moved') and row['entry']['status']=='approved'
        plan=copy.deepcopy(record['data']['plan'])
        variants.append({'n':row['entry']['n'] if approved else None,'id':record['id'],'hash':record['hash'],
            'proposal':not approved,'reviewKey':digest([record['id'],record['hash']]),
            'display':{k:v for k,v in plan.items() if k.endswith('_html')},'plan':plan})
    return {'version':2,'id':identifier,'common':{'inputs':question['inputs'],'qtests':question.get('qtests',[]),'checker':None},
        'backend':{'id':'sympy','planSchema':1,'stackRevision':STACK_COMMIT,'runtimeHash':None,'question':question},
        'variants':variants,'review':review}
