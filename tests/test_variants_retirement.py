"""Absent mathematics can be retired but never approved."""
import sys
from pathlib import Path
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'authoring'))
from ctm_variants import history
from ctm_variants.model import candidate, snapshot, VariantError
from ctm_variants.review import apply_decisions

class RetirementTests(unittest.TestCase):
    def setUp(self):
        self.item = candidate('old', snapshot(['2'], {'answer':'2'}, {}))
        self.value = history.append_proposals(history.empty('q'), [{'record':self.item,'tape':[]}])
        self.value = history.decision(self.value,[self.item],'old','approved',by='first')
        self.selection = {'id':'old','hash':self.item['hash'],'status':'rejected','reason':'Removed source'}

    def test_retirement_preserves_proof_and_number(self):
        result = apply_decisions(self.value,[],[self.selection])
        self.assertEqual(result['proposals'],self.value['proposals'])
        old,new=self.value['decisions'][0],result['decisions'][0]
        for key in ('n','id','hash','snapshot','note'):self.assertEqual(new[key],old[key])
        self.assertEqual(new['status'],'rejected')
        self.assertEqual(new['reason'],'Removed source')
        self.assertEqual(len(result['events']),2)
        self.assertEqual(self.value['decisions'][0]['status'],'approved')

    def test_absent_approval_stale_hash_or_missing_reason_refused(self):
        for update in ({'status':'approved'},{'hash':'stale'},{'reason':''}):
            with self.subTest(update=update),self.assertRaises(VariantError):
                apply_decisions(self.value,[],[dict(self.selection,**update)])

    def test_moved_current_and_changed_are_not_historical_retirement(self):
        moved=dict(self.item,id='new')
        with self.assertRaises(VariantError):apply_decisions(self.value,[moved],[self.selection])
        changed=candidate('old',snapshot(['3'],{'answer':'3'},{}))
        with self.assertRaises(VariantError):apply_decisions(self.value,[changed],[self.selection])

if __name__=='__main__':unittest.main()
