"""Actual sticky API glue against fake GitHub; no real messages or dispatches."""
import copy
from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'authoring'))
from ctm_variants.github_bot import Recorder
from ctm_variants.checklist import question_marker
from ctm_variants.model import VariantError
from tests.test_variants_github_bot import FakeGitHub,PATHS,HEAD


class PreviewAPI(FakeGitHub):
    def __init__(self):
        super().__init__();self.exists=False;self.tick_during_refresh=False;self.duplicate=False
        self.body=self.body.replace('[x]','[ ]')
    def comment(self):
        return {'id':11,'updated_at':'2026-10-23T00:00:00Z','user':{'login':self.author},'body':self.body,'issue_url':'https://api.github.com/repos/org/course/issues/7'}
    def request(self,method,path,value=None):
        if '/issues/7/comments?per_page=' in path:
            self.calls.append((method,path,value));return [self.comment()]*(2 if self.duplicate else 1) if self.exists else []
        if method=='POST' and path.endswith('/issues/7/comments'):
            self.mutations.append((method,path,value));self.exists=True;self.body=value['body'];return self.comment()
        if method=='PATCH' and path.endswith('/issues/comments/11'):
            self.mutations.append((method,path,value));self.body=value['body'];return self.comment()
        if method=='GET' and path.endswith('/issues/comments/11') and self.tick_during_refresh and self.comment_reads==1:
            self.body=self.body.replace('- [ ] answer','- [x] answer')
        return super().request(method,path,value)


class StickyTransportTests(unittest.TestCase):
    def bot(self,api):return Recorder(api,repository='org/course',bot_login='ctm[bot]',producer_paths=PATHS)

    def test_first_run_creates_without_comment_ids_and_recording_uses_fetched_marker(self):
        api=PreviewAPI()
        self.assertNotIn('commentId',api.envelope['questions'][0])
        result=self.bot(api).refresh_run(20)
        self.assertEqual(result['questions']['q']['commentId'],11)
        self.assertEqual([item[0] for item in api.mutations],['POST'])
        self.assertIn(question_marker('q'),api.body)
        self.assertIn('Evidence: head `'+HEAD+'`',api.body)
        self.assertFalse(self.bot(api).record(pull_request=7,comment_id=11,sender='teacher')['changed'])
        api.body=api.body.replace('- [ ] New 1','- [x] New 1')
        self.assertTrue(self.bot(api).record(pull_request=7,comment_id=11,sender='teacher')['changed'])

    def test_refresh_merges_new_tick_from_latest_authenticated_body(self):
        api=PreviewAPI();api.exists=True;api.tick_during_refresh=True
        result=self.bot(api).refresh_preview(7,run_id=20)
        self.assertEqual(result['questions']['q']['preserved'],1)
        self.assertIn('- [x] New 1',api.body)
        self.assertIn('- [ ] Approve all',api.body)
        self.assertEqual(api.mutations[0][0],'PATCH')

    def test_wrong_run_duplicate_own_comments_forged_marker_and_cards_fail_closed(self):
        api=PreviewAPI()
        with self.assertRaises(VariantError):self.bot(api).refresh_preview(7,run_id=21)
        self.assertEqual(api.mutations,[])

        api=PreviewAPI();api.exists=True;api.duplicate=True
        with self.assertRaises(VariantError):self.bot(api).refresh_preview(7,run_id=20)
        self.assertEqual(api.mutations,[])
        api=PreviewAPI();api.body=api.body.replace(question_marker('q'),question_marker('other'))
        with self.assertRaises(VariantError):self.bot(api).record(pull_request=7,comment_id=11,sender='teacher')
        self.assertEqual(api.mutations,[])
        api=PreviewAPI();api.envelope['questions'][0]['cards']={}
        with self.assertRaises(VariantError):self.bot(api).refresh_preview(7,run_id=20)
        self.assertEqual(api.mutations,[])

    def test_malformed_later_question_is_rejected_before_any_sticky_effect(self):
        api=PreviewAPI()
        second=copy.deepcopy(api.envelope['questions'][0])
        second.update(label='second',path='_variants/second.yml')
        second['manifest']['question']='second'
        second['records'][0]['hash']='f'*16
        api.envelope['questions'].append(second)
        with self.assertRaises(VariantError):self.bot(api).refresh_preview(7,run_id=20)
        self.assertEqual(api.mutations,[])


if __name__=='__main__':unittest.main()
