"""Review presentation never changes the canonical teacher input or trusts HTML."""
import sys
from pathlib import Path
import unittest
import xml.etree.ElementTree as ET
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'authoring'))
from ctm_variants.review import teacher_display,document
from ctm_variants import history
from ctm_variants.model import candidate,snapshot

class TeacherDisplayTests(unittest.TestCase):
    def test_mathml_core_fractions_matrix_and_entities(self):
        projection=teacher_display({'mathml':'<math><mfrac><mn>1</mn><mn>3</mn></mfrac><mfenced open="[" close="]"><mtable><mtr><mtd><mi>&pi;</mi></mtd></mtr></mtable></mfenced></math>','latex':r'\frac{1}{3}'})
        self.assertIsNotNone(projection)
        self.assertIn('http://www.w3.org/1998/Math/MathML',projection['mathml'])
        self.assertNotIn('mfenced',projection['mathml'])
        root=ET.fromstring(projection['mathml']);ns={'m':'http://www.w3.org/1998/Math/MathML'}
        self.assertEqual(root.find('.//m:mi',ns).text,'π')
        self.assertEqual([node.text for node in root.findall('.//m:mo',ns)],['[',']'])

    def test_malformed_foreign_active_and_deep_mathml_is_rejected(self):
        attacks=['<math><mi><script>alert(1)</script></mi></math>',
            '<math><mi><img src=x onerror=alert(1)></mi></math>',
            '<math onload="alert(1)"><mn>1</mn></math>',
            '<math><mi style="color:red">x</mi></math>',
            '<math><svg xmlns="http://www.w3.org/2000/svg"/></math>',
            '<!DOCTYPE math [<!ENTITY x "attack">]><math><mi>&x;</mi></math>',
            '<math><mi>&unknown;</mi></math>', '<math>'+'<mrow>'*70+'1'+'</mrow>'*70+'</math>']
        for source in attacks:self.assertIsNone(teacher_display({'mathml':source,'latex':'1'}),source)
        safe=teacher_display({'mathml':'<math><mtext>&lt;img src=x&gt;</mtext></math>','latex':'x'})
        self.assertIn('&lt;img src=x&gt;',safe['mathml'])

    def test_unsafe_markdown_math_is_omitted_without_losing_safe_mathml(self):
        for latex in [r'\href{javascript:alert(1)}{x}','x$outside',r'\htmlStyle{color:red}{x}','line\nbreak','<img>']:
            self.assertEqual(teacher_display({'mathml':'<math><mi>x</mi></math>','latex':latex})['latex'],'')

    def test_overview_rendered_math_and_input_fallback_share_one_validator(self):
        item=candidate('one',snapshot(['1/3'],{'Answer':'1/3'},{}))
        response={'manifest':history.empty('q'),'baseHash':None,'records':[item]}
        display={'mathml':'<math><mfrac><mn>1</mn><mn>3</mn></mfrac></math>','latex':r'\frac{1}{3}'}
        page=document(response,teacher_displays={'one':{'Answer':display}})
        self.assertIn('<math xmlns="http://www.w3.org/1998/Math/MathML">',page)
        self.assertIn('Input: <code>1/3</code>',page)
        legacy=document(response);self.assertIn('Input: <code>1/3</code>',legacy);self.assertNotIn('<math ',legacy)
        item['teacherDisplay']={'Answer':{'mathml':'<math><script>bad()</script></math>','latex':'1'}}
        hostile=document(response);self.assertNotIn('<script>bad()',hostile);self.assertNotIn('class="teacher-math"',hostile);self.assertIn('Input: <code>1/3</code>',hostile)
        self.assertEqual(item['snapshot']['teacher'],[['Answer','1/3']])

if __name__=='__main__':unittest.main()
