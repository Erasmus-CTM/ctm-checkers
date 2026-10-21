import unittest
from pathlib import Path

from ctm_checkers.stack.importer import UnsupportedQuestion, import_xml
from ctm_checkers.stack.engine import instantiate


ROOT = Path(__file__).resolve().parents[2]


class ImporterTests(unittest.TestCase):
    def test_unmodified_stack_exports(self):
        for path in (ROOT / "examples/stack/upstream/algmap-6-1.xml",
                     ROOT / "examples/stack/upstream/bodmas.xml",
                     ROOT / "examples/stack/upstream/rounding-three-dp.xml"):
            with self.subTest(path=path.name):
                question, = import_xml(path)
                self.assertTrue(question["inputs"])
                self.assertTrue(question["prts"])
                self.assertTrue(question["qtests"])

    def test_insertstars_modes_and_unsupported_diagnostic(self):
        xml = (ROOT / "examples/stack/polynomial-expansion.xml").read_text()
        self.assertEqual(import_xml(xml)[0]["inputs"][0]["insertstars"], 1)
        strict = xml.replace("<insertstars>1</insertstars>", "<insertstars>0</insertstars>")
        self.assertEqual(import_xml(strict)[0]["inputs"][0]["insertstars"], 0)
        for mode in ("2", "3", "4", "6", "bogus"):
            with self.subTest(mode=mode), self.assertRaisesRegex(
                    UnsupportedQuestion, r"input\[ans\]/insertstars.*only 0.*and 1"):
                import_xml(xml.replace("<insertstars>1</insertstars>", f"<insertstars>{mode}</insertstars>"))

    def test_reject_unsupported_answer_test_with_location(self):
        path = ROOT / "examples/stack/upstream/bodmas.xml"
        xml = path.read_text().replace("<answertest>NumRelative</answertest>",
                                       "<answertest>Diff</answertest>")
        with self.assertRaisesRegex(UnsupportedQuestion, r"1\.1\.4\.T2 BODMAS: prt\[prt1\]/node\[0\]/answertest"):
            import_xml(xml)

    def test_reject_cycle_and_dangling_node(self):
        path = ROOT / "examples/stack/upstream/bodmas.xml"
        xml = path.read_text().replace("<truenextnode>-1</truenextnode>", "<truenextnode>0</truenextnode>")
        with self.assertRaisesRegex(UnsupportedQuestion, "cycle in response tree"):
            import_xml(xml)
        xml = path.read_text().replace("<truenextnode>-1</truenextnode>", "<truenextnode>99</truenextnode>")
        with self.assertRaisesRegex(UnsupportedQuestion, "dangling next node"):
            import_xml(xml)

    def test_categories_and_descriptions_are_not_assessments(self):
        xml = '<quiz><question type="category"><category><text>x</text></category></question>' \
              '<question type="description"><name><text>Intro</text></name></question></quiz>'
        self.assertEqual(import_xml(xml), [])

    def test_reject_form_loss_in_equalcomass_and_unsimplified_variables(self):
        path = ROOT / "examples/stack/upstream/algmap-6-1.xml"
        xml = path.read_text().replace("<sans>ans</sans>", "<sans>ans+0</sans>")
        with self.assertRaisesRegex(UnsupportedQuestion, "EqualComAss requires a direct input"):
            import_xml(xml)
        xml = path.read_text().replace("<questionsimplify>1</questionsimplify>",
                                       "<questionsimplify>0</questionsimplify>")
        xml = xml.replace("ta:ev(a*x+b*y-c*x-d*y+5,simp);", "ta:x+x;")
        with self.assertRaisesRegex(UnsupportedQuestion, "loses unsimplified answer form"):
            instantiate(import_xml(xml)[0], 17)

    def test_facform_requires_direct_input_and_variable_option(self):
        path = ROOT / "examples/stack/corpus/AlgMap-10-1.xml"
        xml = path.read_text().replace("<sans>ans</sans>", "<sans>ans+0</sans>", 1)
        with self.assertRaisesRegex(UnsupportedQuestion, r"node\[0\]/sans: FacForm requires a direct input"):
            import_xml(xml)
        question = import_xml(path)[0]
        node = question["prts"][0]["nodes"][0]
        self.assertEqual(node["options"], "v")
        instantiate(question, question["deployedseeds"][0])
        for option, reason in (("", "FacForm requires a polynomial variable option"),
                               ("1", "FacForm requires a single polynomial variable"),
                               ("x+", "invalid FacForm variable option")):
            with self.subTest(option=option), self.assertRaisesRegex(
                    UnsupportedQuestion, rf"node\[0\]/testoptions: {reason}"):
                node["options"] = option
                instantiate(question, question["deployedseeds"][0])

    def test_reject_forward_assignment_and_nonfinite_scoring(self):
        path = ROOT / "examples/stack/upstream/algmap-6-1.xml"
        xml = path.read_text().replace("a:rand(9)+2;", "a:b+1;")
        with self.assertRaisesRegex(UnsupportedQuestion, "forward or cyclic assignment reference"):
            instantiate(import_xml(xml)[0], 17)
        xml = path.read_text().replace("<defaultgrade>1</defaultgrade>",
                                       "<defaultgrade>NaN</defaultgrade>")
        with self.assertRaisesRegex(UnsupportedQuestion, "number must be finite"):
            import_xml(xml)


class QuestionOptionTests(unittest.TestCase):
    """S-07: the question options the engine does not read stop the build
    unless they are STACK's default (or a value that changes only how the
    question writes products and matrices)."""

    BASE = (ROOT / "examples/stack/probes/crash.xml").read_text()

    def question(self, **options):
        tags = "".join(f"<{name}>{value}</{name}>" for name, value in options.items())
        return self.BASE.replace("<input>", tags + "<input>", 1)

    def test_the_defaults_and_absent_options_build(self):
        self.assertTrue(import_xml(self.BASE))
        defaults = dict(complexno="i", decimals=".", scientificnotation="*10", inversetrig="cos-1",
                        logicsymbol="lang", sqrtsign="1", multiplicationsign="dot", matrixparens="[")
        self.assertTrue(import_xml(self.question(**defaults)))
        for option, value in defaults.items():
            with self.subTest(option=option):
                self.assertTrue(import_xml(self.question(**{option: f" {value} "})))

    def test_each_option_with_another_value_stops_the_build(self):
        for option, value in (("complexno", "j"), ("complexno", "symi"), ("complexno", "symj"), ("decimals", ","),
                              ("scientificnotation", "E"), ("inversetrig", "acos"), ("inversetrig", "arccos"),
                              ("inversetrig", "arsinh"), ("logicsymbol", "symbol"), ("sqrtsign", "0"),
                              ("multiplicationsign", "cross"), ("multiplicationsign", "onum"),
                              ("multiplicationsign", "space"), ("matrixparens", ""), ("matrixparens", "{"),
                              ("matrixparens", "|"), ("complexno", ""), ("decimals", "x")):
            with self.subTest(option=option, value=value), self.assertRaisesRegex(
                    UnsupportedQuestion, rf"^crash: question/{option}: unsupported question option: {option} is '{value}', "
                                         r"the engine supports '.+'\. The engine does not read these options"):
                import_xml(self.question(**{option: value}))

    def test_products_and_matrices_may_be_written_as_the_example_questions_do(self):
        self.assertTrue(import_xml(self.question(multiplicationsign="none", matrixparens="(")))

    def test_every_option_that_is_not_supported_is_named(self):
        with self.assertRaisesRegex(
                UnsupportedQuestion, r"question/complexno: unsupported question options: complexno is 'j', the engine supports 'i'; "
                                     r"sqrtsign is '0', the engine supports '1'\."):
            import_xml(self.question(complexno="j", sqrtsign="0", decimals="."))

    def test_the_audit_probe_stops_with_both_of_its_options(self):
        with self.assertRaisesRegex(UnsupportedQuestion, r"complexno-j: question/complexno: .*complexno is 'j'.*decimals is ','"):
            import_xml(ROOT / "examples/stack/probes/options.xml")

    def test_the_options_of_an_input_or_a_node_are_not_question_options(self):
        # An element of another level that has an option's name is not the question's option.
        xml = self.BASE.replace("<input>", "<input><decimals>,</decimals>", 1)
        self.assertTrue(import_xml(xml))


if __name__ == "__main__":
    unittest.main()
