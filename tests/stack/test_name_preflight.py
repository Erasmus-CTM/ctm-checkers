"""Cross-scope names fail authoring before plans/HTML; legacy grading is intact."""
import copy
import os
from pathlib import Path
import subprocess
import sys
import xml.etree.ElementTree as ET

import pytest

ROOT=Path(__file__).resolve().parents[2]
from ctm_checkers.stack import cli
from ctm_checkers.stack.engine import grade, instantiate
from ctm_checkers.stack.importer import import_xml, UnsupportedQuestion
from ctm_checkers.stack.names import name_collisions, preflight_names


def question():return import_xml(ROOT/'examples/stack/polynomial-expansion.xml')[0]


def collide(q,kind):
    if kind=='generator-input':q['variables']+='\nans:5;'
    if kind=='generator-feedback':q['prts'][0]['feedbackvariables']='a:5;'
    if kind=='input-feedback':q['prts'][0]['feedbackvariables']='ans:5;'
    return q


@pytest.mark.parametrize('kind,name,scopes',[
    ('generator-input','ans',['questionvariables','student inputs']),
    ('generator-feedback','a',['questionvariables','prt[prt1]/feedbackvariables']),
    ('input-feedback','ans',['student inputs','prt[prt1]/feedbackvariables'])])
def test_each_cross_scope_pair_names_source_question_and_both_scopes(kind,name,scopes):
    q=collide(question(),kind)
    assert {'name':name,'scopes':scopes} in name_collisions(q)
    with pytest.raises(UnsupportedQuestion) as found:preflight_names(q,source='course/questions.xml')
    text=str(found.value)
    assert all(part in text for part in ['course/questions.xml',q['name'],name,*scopes])


def test_same_scope_reassignment_and_sibling_prt_local_reuse_are_allowed():
    q=question();q['variables']+='\na:6;a:5;'
    q['prts'][0]['feedbackvariables']='local:1;local:2;'
    second=copy.deepcopy(q['prts'][0]);second['name']='second';q['prts'].append(second)
    assert name_collisions(q)==[]
    assert preflight_names(q,source='q.xml') is None


def test_free_cas_symbols_are_not_declarations_and_no_expression_is_executed():
    q=question();q['variables']+='\nunused:1/0;'
    q['prts'][0]['feedbackvariables']='local:ans+x;'
    assert name_collisions(q)==[]  # AST syntax only; no division or CAS evaluation.


def test_existing_assignment_ast_reports_syntax_with_scope_and_source():
    q=question();q['prts'][0]['feedbackvariables']='local:(;'
    with pytest.raises(UnsupportedQuestion) as found:preflight_names(q,source='broken.xml')
    text=str(found.value)
    assert 'broken.xml' in text and 'prt[prt1]/feedbackvariables/statement[1]' in text


def xml_fixture(tmp_path,kind):
    tree=ET.parse(ROOT/'examples/stack/polynomial-expansion.xml')
    root=tree.getroot();element=next(q for q in root.findall('question') if q.get('type')=='stack')
    if kind=='generator-input':element.find('questionvariables/text').text+='\nans:5;'
    if kind=='generator-feedback':element.find('prt/feedbackvariables/text').text='a:5;'
    if kind=='input-feedback':element.find('prt/feedbackvariables/text').text='ans:5;'
    target=tmp_path/'colliding.xml';tree.write(target,encoding='unicode');return target


@pytest.mark.parametrize('kind',['generator-input','generator-feedback','input-feedback'])
@pytest.mark.parametrize('command',['prepare','render'])
def test_native_cli_collision_emits_no_plan_or_html(tmp_path,kind,command):
    path=xml_fixture(tmp_path,kind)
    result=subprocess.run([sys.executable,'-m','ctm_checkers.stack.cli',command,'--file',str(path),
                           '--question',question()['name'],'--id','card'],cwd=tmp_path,
                          env={**os.environ,'PYTHONPATH':str(ROOT/'src')},capture_output=True,text=True)
    assert result.returncode==2 and result.stdout==''
    assert str(path) in result.stderr and question()['name'] in result.stderr
    assert 'name collision' in result.stderr
    assert 'questionvariables' in result.stderr or 'prt[prt1]/feedbackvariables' in result.stderr


def test_prepare_guard_runs_before_instantiate(tmp_path,monkeypatch):
    path=xml_fixture(tmp_path,'generator-feedback');calls=[]
    def forbidden(*args,**kwargs):calls.append(True);raise AssertionError('must never instantiate')
    monkeypatch.setattr(cli,'instantiate',forbidden)
    with pytest.raises(UnsupportedQuestion,match='name collision'):
        cli.prepare(str(path),question()['name'],'card')
    assert calls==[]




def test_legacy_engine_scoped_semantics_remain_unchanged():
    q=question();q['variables']+='\nk:5;';q['prts'][0]['feedbackvariables']='a:ans;z:a;'
    q['prts'][0]['nodes'][0]['teacher']='z'
    plan=instantiate(q,17)
    assert grade(q,{'ans':'7'},variant=plan)['score']==1
    with pytest.raises(UnsupportedQuestion,match='name collision'):preflight_names(q,source='q.xml')
    q['prts'][0]['feedbackvariables']='a:ans;z:k;'
    assert grade(q,{'ans':'7'},variant=plan)['score']==0


def test_duplicate_input_declarations_still_fail_existing_importer(tmp_path):
    tree=ET.parse(ROOT/'examples/stack/polynomial-expansion.xml');element=next(q for q in tree.getroot().findall('question') if q.get('type')=='stack')
    element.append(copy.deepcopy(element.find('input')))
    path=tmp_path/'duplicate.xml';tree.write(path,encoding='unicode')
    with pytest.raises(UnsupportedQuestion,match='unique'):import_xml(path)


@pytest.mark.parametrize('source',[None,'a:1;'*5001],ids=['not-text','over-20000'])
def test_assignment_source_bound_precedes_declaration_iteration(source,monkeypatch):
    import ctm_checkers.stack.names as names
    q=question();q['variables']=source;calls=[]
    def forbidden(*args,**kwargs):calls.append(True);raise AssertionError('must not iterate')
    monkeypatch.setattr(names,'assignment_statements',forbidden)
    with pytest.raises(UnsupportedQuestion) as found:preflight_names(q,source='bounded.xml')
    text=str(found.value)
    assert 'bounded.xml' in text and q['name'] in text and 'questionvariables' in text
    assert 'Assignment source' in text and calls==[]
