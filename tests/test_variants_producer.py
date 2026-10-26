"""Trusted producer boundary with fake AST/resolver/API; no authored execution."""
import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'authoring'))
from ctm_variants import history
from ctm_variants.model import VariantError,candidate,snapshot
from ctm_variants.producer import produce,discover,check,verify_context,inside
from ctm_variants.review import card_id

HEAD,BASE='a'*40,'b'*40
CONTEXT=dict(headSha=HEAD,producerSha=BASE,event='pull_request',expectedHead=HEAD,runId=20,repositoryId=1,pullRequest=7)


class MetadataAPI:
    def __init__(self):self.fork=False;self.head=HEAD;self.producer=BASE;self.calls=[]
    def request(self,method,path):
        self.calls.append((method,path));assert method=='GET'
        if path.endswith('/git/ref/heads/main'):return {'object':{'sha':self.producer}}
        assert path=='/repos/org/course/pulls/7'
        return {'state':'open','head':{'sha':self.head,'ref':'feature/teacher-question','repo':{'id':2 if self.fork else 1,'full_name':'fork/course' if self.fork else 'org/course'}},'base':{'repo':{'id':1,'full_name':'org/course','default_branch':'main'}}}


class ProducerTests(unittest.TestCase):
    def setUp(self):
        self.item=candidate('question:$(never-execute)',snapshot(['2'],{'Answer':'2'},{},{'x':'2'}),
            data={'options':{'question':'Escaped student <script>','solution':'Worked solution'},'context':{},'teacher_inputs':{}},tests={'passed':True})
        self.config={'previewBase':'https://preview.test/previews/variants-{pullRequest}/review'}
        self.definition={'label':'q','file':'lesson.qmd','source':'not executed','options':{'variables':'raise Exception("must not run in this test")'},'question':'Student text'}

    def test_real_neutral_artifact_and_canonical_html_are_read_only_then_gate_zero(self):
        with tempfile.TemporaryDirectory() as folder:
            value=history.append_proposals(history.empty('q'),[{'record':self.item,'tape':[]}])
            response={'version':1,'baseHash':None,'manifest':value,'records':[dict(self.item,n=None,question='enriched')],'warnings':[]}
            captured=[]
            envelope,pages=produce(folder,CONTEXT,self.config,definitions=[self.definition],resolve=lambda payload:(captured.append(payload) or response))
            question=envelope['questions'][0]
            self.assertNotIn('commentId',question)
            self.assertEqual(set(question['records'][0]),{'id','hash','note','snapshot','data','tests'})
            self.assertIn('id="'+card_id(self.item['id'])+'"',pages['review/q.html'])
            self.assertEqual(question['cards'][self.item['id']],'https://preview.test/previews/variants-7/review/q.html#'+card_id(self.item['id']))
            self.assertFalse((Path(folder)/'_variants/q.yml').exists())
            self.assertEqual(captured[0]['action'],'resolve');self.assertEqual(captured[0]['renderMode'],'review')
            with self.assertRaisesRegex(VariantError,'approved'):check(envelope)
            approved=history.decision(value,[self.item],self.item['id'],'approved')
            history.write(Path(folder)/'_variants/q.yml',approved,base_hash=None)
            response.update(manifest=approved,baseHash=history.load(Path(folder)/'_variants/q.yml','q')[1])
            envelope,_=produce(folder,CONTEXT,self.config,definitions=[self.definition],resolve=lambda _:response)
            self.assertIn('target 25',check(envelope)[0])

    def test_bad_test_lease_and_rewritten_history_fail_without_resampling(self):
        with tempfile.TemporaryDirectory() as folder:
            value=history.append_proposals(history.empty('q'),[{'record':self.item,'tape':[]}])
            response={'baseHash':None,'manifest':value,'records':[self.item]}
            for kind in ['tests','lease','history']:
                bad=copy.deepcopy(response)
                if kind=='tests':bad['records'][0]['tests']={'passed':False}
                elif kind=='lease':bad['baseHash']='stale'
                else:bad['manifest']=history.decision(value,[self.item],self.item['id'],'approved')
                calls=[]
                with self.subTest(kind=kind),self.assertRaises(VariantError):
                    produce(folder,CONTEXT,self.config,definitions=[self.definition],resolve=lambda payload:(calls.append(payload) or bad))
                self.assertEqual(len(calls),1)
                self.assertFalse((Path(folder)/'_variants/q.yml').exists())

    def test_discovery_covers_added_questions_and_selects_stack_component(self):
        def parse(raw):return {'label':raw,'variables':'not executed'},'question'
        def ast(text):return {'blocks':[{'t':'CodeBlock','c':[['',['{math-exercise}'],[]],text]}]}
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);(root/'one.qmd').write_text('one')
            self.assertEqual([item['label'] for item in discover(root,['**/*.qmd'],parse,ast=ast)],['one'])
            (root/'two.qmd').write_text('two')
            self.assertEqual({item['label'] for item in discover(root,['**/*.qmd'],parse,ast=ast)},{'one','two'})
            (root/'_extensions').mkdir();(root/'_extensions/example.qmd').write_text('excluded')
            self.assertEqual(len(discover(root,['**/*.qmd'],parse,ast=ast)),2)
            stack=discover(root,['one.qmd'],parse,ast=lambda _: {'blocks':[{'t':'CodeBlock','c':[['',['{.stack-question}'],[]],'stack']} ]})
            self.assertEqual(stack[0]['component'],'ctm-stack')
            (root/'duplicate.qmd').write_text('one')
            with self.assertRaisesRegex(VariantError,'distinct'):discover(root,['**/*.qmd'],parse,ast=ast)
            with self.assertRaises(VariantError):inside(root,'../escape')

    def test_context_rejects_stale_source_producer_dispatch_and_privileged_fork(self):
        api=MetadataAPI();event={'repository':{'full_name':'org/course'},'pull_request':{'number':7,'head':{'sha':HEAD}}}
        args=dict(repository='org/course',event_name='pull_request',event=event,run_id='20',source_head=HEAD,producer_head=BASE)
        self.assertEqual(verify_context(api,**args),CONTEXT)
        api.fork=True
        self.assertEqual(verify_context(api,**args)['pullRequest'],7,'unprivileged fork checks remain available')
        dispatch=dict(args,event_name='workflow_dispatch',event={'repository':{'full_name':'org/course'},'inputs':{'pull_request':'7','expected_head':HEAD}})
        with self.assertRaises(VariantError):verify_context(api,**dispatch)
        api.fork=False
        self.assertEqual(verify_context(api,**dispatch)['event'],'workflow_dispatch')
        for fault in [dict(source_head='c'*40),dict(producer_head='c'*40),dict(event={**dispatch['event'],'inputs':{'pull_request':'7','expected_head':'c'*40}})]:
            with self.subTest(fault=fault),self.assertRaises(VariantError):verify_context(api,**dict(dispatch,**fault))

    def test_github_file_editor_context_comes_from_verified_head_including_forks(self):
        api=MetadataAPI();api.fork=True;editor={}
        event={'repository':{'full_name':'org/course'},'pull_request':{'number':7,'head':{'sha':HEAD}}}
        context=verify_context(api,repository='org/course',event_name='pull_request',event=event,run_id='20',source_head=HEAD,producer_head=BASE,editor_out=editor)
        self.assertEqual(editor,{'repository':'fork/course','branch':'feature/teacher-question','head':HEAD})
        self.assertEqual(context,CONTEXT,'editor metadata does not change the artifact provenance schema')
        with tempfile.TemporaryDirectory() as folder:
            value=history.append_proposals(history.empty('q'),[{'record':self.item,'tape':[]}])
            response={'baseHash':None,'manifest':value,'records':[self.item]}
            _,pages=produce(folder,context,self.config,definitions=[self.definition],resolve=lambda _:response,github_context=editor)
            self.assertIn('GitHub review snapshot:',pages['review/q.html'])
            self.assertIn('fork/course',pages['review/q.html'])
            self.assertIn('feature/teacher-question',pages['review/q.html'])
            with self.assertRaisesRegex(VariantError,'verified source head'):
                produce(folder,context,self.config,definitions=[self.definition],resolve=lambda _:response,github_context=dict(editor,head='c'*40))

    def test_workflow_split_never_executes_authored_checkout_privileged(self):
        records=(ROOT/'templates/variants.yml').read_text()
        preview=(ROOT/'templates/variants-preview.yml').read_text()
        self.assertNotIn('pull-requests: write',records)
        self.assertNotIn('contents: write',records)
        self.assertIn('path: trusted',records);self.assertIn('path: authored',records)
        self.assertIn('trusted/.github/scripts/ctm-variants-records.py',records)
        self.assertIn('expected_head:',records);self.assertIn('variants / check',records)
        self.assertIn('workflow_run:',preview);self.assertIn('--refresh-preview',preview)
        self.assertNotIn('path: authored',preview);self.assertNotIn('workflow_run.head_sha',preview)
        self.assertNotIn('download-artifact@',preview,'privileged job never extracts run archives')

    def test_aggregate_artifact_and_review_budgets_fail_before_returning_partial_output(self):
        with tempfile.TemporaryDirectory() as folder:
            def resolve(payload):
                value=history.append_proposals(history.empty(payload['label']),[{'record':self.item,'tape':[]}])
                return {'version':1,'baseHash':None,'manifest':value,'records':[self.item]}
            definitions=[self.definition,dict(self.definition,label='second')]
            envelope,pages=produce(folder,CONTEXT,self.config,definitions=definitions[:1],resolve=resolve)
            budget=len(json.dumps(envelope,ensure_ascii=False,indent=2).encode())+256
            with patch('ctm_variants.producer.ARTIFACT_BUDGET',budget),self.assertRaisesRegex(VariantError,'aggregate neutral'):
                produce(folder,CONTEXT,self.config,definitions=definitions,resolve=resolve)
            budget=len(next(iter(pages.values())).encode())+256
            with patch('ctm_variants.producer.REVIEW_BUDGET',budget),self.assertRaisesRegex(VariantError,'aggregate review'):
                produce(folder,CONTEXT,self.config,definitions=definitions,resolve=resolve)
            self.assertEqual(list(Path(folder).iterdir()),[])


if __name__=='__main__':unittest.main()
