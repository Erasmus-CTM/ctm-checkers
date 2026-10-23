"""Teacher rejection commands are data scoped to a verified bot question."""
import sys
from pathlib import Path
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'authoring'))
from ctm_variants import history
from ctm_variants.bot import plan,token
from ctm_variants.model import candidate,snapshot,VariantError
from ctm_variants.review import apply_decisions

class RejectCommands(unittest.TestCase):
    def setUp(self):
        self.row=candidate('opaque candidate',snapshot(['2'],{'answer':'2'},{}))
        self.value=history.append_proposals(history.empty('q'),[{'record':self.row,'tape':[]}])
        self.args=dict(label='q',records=[self.row],decisions=[],retained=self.value['proposals'],sender='teacher',permission='write',comment_author='bot',bot_login='bot',head_repository_id=1,base_repository_id=1)
    def test_new_id_rejection_without_approval_verdict(self):
        result=plan('/variants reject id:"opaque candidate" "Incorrect example"',**self.args)['decisions']
        updated=apply_decisions(self.value,[self.row],result)
        self.assertEqual(updated['decisions'][0]['n'],1)
        self.assertEqual(updated['decisions'][0]['status'],'rejected')
    def test_stable_number_and_gone_retirement(self):
        value=history.decision(self.value,[self.row],self.row['id'],'approved')
        args=dict(self.args,records=[],decisions=value['decisions'])
        selected=plan('/variants reject 1 "Source removed"',**args)['decisions']
        retired=apply_decisions(value,[],selected)
        self.assertEqual(retired['decisions'][0]['n'],1)
        self.assertEqual(retired['decisions'][0]['status'],'rejected')
        self.assertEqual(plan('/variants reject 1 "Source removed"',**dict(args,decisions=retired['decisions']))['decisions'],[])
    def test_invalid_numbers_reason_ids_or_duplicate_selection_fail(self):
        for body in ('/variants reject 0 "x"','/variants reject New1 "x"','/variants reject 1 x','/variants reject id:absent "x"','/variants reject q q 1 "x"','/variants reject id:"opaque candidate" id:"opaque candidate" "x"'):
            with self.subTest(body=body),self.assertRaises(VariantError):plan(body,**self.args)
    def test_examples_do_not_execute_and_auth_is_unchanged(self):
        body='/variants reject id:"opaque candidate" "x"'
        for example in ('```\n'+body+'\n```','> '+body,'    '+body,'~~~\n'+body+'\n~~~python\n'+body):
            self.assertEqual(plan(example,**self.args)['decisions'],[])
        tick='- [x] '+token('q',self.row['id'],self.row['hash'])
        for prefix in ('    ','\t',' \t'):
            self.assertEqual(plan(prefix+tick,**self.args)['decisions'],[])
        for field,value in (('permission','read'),('comment_author','teacher'),('head_repository_id',2)):
            with self.assertRaises(VariantError):plan(body,**dict(self.args,**{field:value}))
class RejectTransport(unittest.TestCase):
    def test_verified_artifact_records_rejection_and_gone_retirement(self):
        import base64,json
        from tests.test_variants_github_bot import FakeGitHub,GitHubBotTests
        from ctm_variants.checklist import question_marker
        for gone in (False,True):
            api=FakeGitHub();q=api.envelope['questions'][0];row=q['records'][0]
            if gone:
                value=history.decision(api.value,[row],row['id'],'approved')
                api.old=api.value=value;q.update(manifest=value,baseHash=__import__('ctm_variants.model',fromlist=['digest']).digest(value),records=[],cards={})
                selector='1'
            else:selector='id:'+json.dumps(row['id'])
            api.body=question_marker('q')+'\n/variants reject '+selector+' "Incorrect or removed"'
            GitHubBotTests().run_bot(api)
            addition=api.mutations[0][2]['variables']['input']['fileChanges']['additions'][0]
            updated=json.loads(base64.b64decode(addition['contents']))
            self.assertEqual(updated['decisions'][0]['status'],'rejected')
            self.assertEqual(updated['decisions'][0]['reason'],'Incorrect or removed')

if __name__=='__main__':unittest.main()
