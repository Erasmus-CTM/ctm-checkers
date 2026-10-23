"""Presentation sidecars never alter neutral candidates or recording identities."""
import copy,sys,tempfile
from pathlib import Path
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'authoring'))
from ctm_variants import history
from ctm_variants.github_bot import teacher_displays
from ctm_variants.model import VariantError
from ctm_variants.producer import produce
from tests.test_variants_github_bot import FakeGitHub
from tests import test_variants_github_bot as github_fixture
from tests.test_variants_producer import CONTEXT
from tests import test_variants_producer as producer_fixture
DISPLAY={'mathml':'<math xmlns="http://www.w3.org/1998/Math/MathML"><mn>2</mn></math>','latex':'2'}
class TeacherMetadata(unittest.TestCase):
    def test_legacy_artifact_and_current_exact_candidate_fields(self):
        api=FakeGitHub();q=api.envelope['questions'][0];row=q['records'][0]
        self.assertEqual(teacher_displays(q),{})
        q['teacherDisplays']={row['id']:{'answer':DISPLAY}}
        safe=teacher_displays(q)
        self.assertEqual(safe[row['id']]['answer']['latex'],'2')
        for value in ({'absent':{'answer':DISPLAY}},{row['id']:{'wrongfield':DISPLAY}},{row['id']:{'answer':{'mathml':'<script>alert(1)</script>','latex':'2'}}}):
            bad=copy.deepcopy(q);bad['teacherDisplays']=value
            with self.assertRaises(VariantError):teacher_displays(bad)
    def test_invalid_later_metadata_prevents_recorder_mutations(self):
        api=FakeGitHub();q=copy.deepcopy(api.envelope['questions'][0]);q.update(label='later',path='_variants/later.yml');q['manifest']['question']='later';q['teacherDisplays']={'absent':{'answer':DISPLAY}}
        api.envelope['questions'].append(q)
        with self.assertRaises(VariantError):github_fixture.GitHubBotTests().run_bot(api)
        self.assertEqual(api.mutations,[])
    def test_producer_projects_sidecar_and_keeps_six_neutral_keys(self):
        fixture=producer_fixture.ProducerTests();fixture.setUp();item=fixture.item
        value=history.append_proposals(history.empty('q'),[{'record':item,'tape':[]}])
        enriched=dict(item,teacherDisplay={'Answer':DISPLAY})
        response=dict(baseHash=None,manifest=value,records=[enriched])
        with tempfile.TemporaryDirectory() as folder:
            envelope,pages=produce(folder,CONTEXT,fixture.config,definitions=[fixture.definition],resolve=lambda _:response)
        q=envelope['questions'][0]
        self.assertEqual(set(q['records'][0]),{'id','hash','note','snapshot','data','tests'})
        self.assertEqual(q['records'][0],item)
        self.assertEqual(q['teacherDisplays'][item['id']]['Answer']['latex'],'2')
        self.assertIn('<math',pages['review/q.html'])
        response['records'][0]['teacherDisplay']='malformed'
        with tempfile.TemporaryDirectory() as folder,self.assertRaises(VariantError):
            produce(folder,CONTEXT,fixture.config,definitions=[fixture.definition],resolve=lambda _:response)
if __name__=='__main__':unittest.main()
