"""Handwritten pools never acquire native variant approvals."""
import sys,tempfile,json
from pathlib import Path
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'authoring'))
from ctm_variants.producer import produce,discover,check
from ctm_variants.model import VariantError
from tests.test_variants_producer import CONTEXT
class PoolProducerTests(unittest.TestCase):
    def test_discovery_accepts_canonical_string_pool_scalar(self):
        import runpy
        wrapper=Path(__file__).resolve().parents[2]/'math-exercise/_extensions/math-exercise/question-variants.py'
        if not wrapper.is_file():self.skipTest('canonical sibling math wrapper unavailable')
        parser=runpy.run_path(str(wrapper),run_name='test_trusted_wrapper')['parse_source']
        raw='#| label: handwritten\n#| pool: true\nQuestion'
        self.assertEqual(parser(raw)[0]['pool'],'true')
        ast=lambda _: {'blocks':[{'t':'CodeBlock','c':[['',['{math-exercise}'],[]],raw]}]}
        with tempfile.TemporaryDirectory() as folder:
            Path(folder,'lesson.qmd').write_text('fixture')
            found=discover(folder,['*.qmd'],parser,ast=ast)
            self.assertEqual([item['label'] for item in found],['handwritten'])

    def test_pool_check_is_read_only_separate_and_required(self):
        definition=dict(label='pool',file='lesson.qmd',source='source',options={'pool':'true'},question='question')
        receipt=dict(version=1,kind='pool',label='pool',passed=True,count=1,tasks=[{'n':1,'teacher':{'passed':True},'tests':[{'name':'expected wrong','passed':True}]}])
        captured=[]
        with tempfile.TemporaryDirectory() as folder:
            env,pages=produce(folder,CONTEXT,{'previewBase':'https://preview.test/review'},definitions=[definition],resolve=lambda payload:(captured.append(payload) or receipt))
            self.assertEqual(env['questions'],[])
            self.assertEqual(check(env),[])
            self.assertEqual(captured[0]['action'],'check-pool')
            self.assertNotIn('manifest',captured[0])
            self.assertFalse((Path(folder)/'_variants').exists())
            self.assertEqual(json.loads(pages['pool-checks.json'])['pools'],[receipt])
            for field,value in (('passed',False),('count',0),('label','other'),('tasks',[]),('tasks',[{'n':1,'teacher':{'passed':False},'tests':[]}])):
                with self.subTest(field=field),self.assertRaises(VariantError):
                    produce(folder,CONTEXT,{'previewBase':'https://preview.test/review'},definitions=[definition],resolve=lambda _,f=field,v=value:dict(receipt,**{f:v}))
if __name__=='__main__':unittest.main()
