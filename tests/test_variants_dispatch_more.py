"""Trusted workflow input selects one read-only native generation call."""
import copy,sys,tempfile
from pathlib import Path
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'authoring'))
from ctm_variants import history
from ctm_variants.producer import produce,verify_context
from ctm_variants.model import candidate,snapshot,VariantError
from ctm_variants.review import document
from tests.test_variants_producer import CONTEXT,HEAD,BASE,MetadataAPI
class DispatchMore(unittest.TestCase):
    def test_only_named_native_question_generates_without_manifest_write(self):
        context=dict(CONTEXT,event='workflow_dispatch');seen=[]
        defs=[dict(label=name,file='lesson.qmd',source='trusted fixture',options={'variables':'x=1'},question='question') for name in ('one','two')]
        def resolve(payload):
            seen.append((payload['label'],payload['action']))
            item=candidate(payload['label'],snapshot(['2'],{'answer':'2'},{}),tests={'passed':True})
            value=history.append_proposals(history.empty(payload['label']),[{'record':item,'tape':[]}])
            return dict(baseHash=None,manifest=value,records=[item])
        with tempfile.TemporaryDirectory() as folder:
            envelope,pages=produce(folder,context,{'previewBase':'https://preview.test/previews/variants-7/review'},definitions=defs,resolve=resolve,generate_more='two',github_context={'repository':'org/course','branch':'feature/variants','head':HEAD},workflow_enabled=True)
            self.assertEqual(seen,[('one','resolve'),('two','resolve-more')])
            self.assertEqual(len(envelope['questions']),2)
            self.assertFalse((Path(folder)/'_variants').exists())
            self.assertIn('Generate 25 more with GitHub Actions',pages['review/two.html'])
            self.assertIn('"pullRequest": 7',pages['review/two.html'])
            self.assertIn('generate_more:base.workflow.label',pages['review/two.html'])
            self.assertIn('No generation runs in this browser',pages['review/two.html'])
            _,fork_pages=produce(folder,context,{'previewBase':'https://preview.test/review'},definitions=defs,resolve=resolve,github_context={'repository':'fork/course','branch':'feature/variants','head':HEAD})
            self.assertIn('"workflow": null',fork_pages['review/one.html'])
            for selected,ctx,definitions in [('absent',context,defs),('one',CONTEXT,defs),('one',context,[dict(defs[0],options={'pool':'true'})])]:
                with self.subTest(selected=selected,event=ctx['event']),self.assertRaises(VariantError):
                    produce(folder,ctx,{'previewBase':'https://preview.test/review'},definitions=definitions,resolve=resolve,generate_more=selected)
    def test_workflow_controls_only_receive_api_verified_same_repository_context(self):
        api=MetadataAPI()
        for fork in (False,True):
            api.fork=fork;editor={};workflow={}
            verify_context(api,repository='org/course',event_name='pull_request',
                           event={'repository':{'full_name':'org/course'},'pull_request':{'number':7,'head':{'sha':HEAD}}},run_id='20',
                           source_head=HEAD,producer_head=BASE,editor_out=editor,workflow_out=workflow)
            self.assertEqual(editor['repository'],'fork/course' if fork else 'org/course')
            self.assertEqual(workflow,{} if fork else {'repository':'org/course','branch':'feature/teacher-question'})

    def test_instructions_cannot_invent_pr_or_question_context(self):
        response={'manifest':history.empty('q'),'records':[],'baseHash':None}
        github={'repository':'org/course','branch':'feature/variants','path':'_variants/q.yml','head':HEAD}
        for context in ({'pullRequest':0,'label':'q'},{'pullRequest':7,'label':'wrong'}):
            with self.assertRaises(VariantError):document(response,github_context=github,workflow_context=context)
        with self.assertRaises(VariantError):document(response,workflow_context={'pullRequest':7,'label':'q'})
if __name__=='__main__':unittest.main()
