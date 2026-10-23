"""Native placeholder/display contracts. AGPL-3.0-or-later."""
import json
import os
from pathlib import Path
import sys
import threading
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT/"authoring")] + (os.environ.get("CTM_CHECKERS_WHEEL") or str(ROOT/"src")).split(os.pathsep)
import sympy as sp
from ctm_variants.placeholders import render,_render,_scan,_display,_input,DisplayValue
from ctm_variants.generation import GenerationError,execute
from ctm_checkers.variants import question_context
from ctm_checkers.math_exercise.parsing import parse_expr,build_locals,TRANSFORMATIONS


class PlaceholderTests(unittest.TestCase):
    def local(self,text,variables=None):
        return _render(text,variables or {},lambda *_:None)

    def test_fraction_braces_exact_values_and_native_execution(self):
        x=sp.Symbol("x")
        text=r"Find $f(x)=\dfrac{@x-p1@}{@x-p2@}$; key {#df#}; outside {@1/3@}."
        variables={"x":x,"p1":sp.Integer(-1),"p2":sp.Integer(-3),"df":2/(x+3)**2}
        result=render(text,variables=variables)
        self.assertEqual(result["text"],r"Find $f(x)=\dfrac{x + 1}{x + 3}$; key 2/(x + 3)^2; outside $\frac{1}{3}$.")
        self.assertEqual([row["value"] for row in result["resolutions"]],[x+1,x+3,2/(x+3)**2,sp.Rational(1,3)])
        self.assertEqual(result["math_segments"][0]["input"],r"f(x)=\dfrac{x + 1}{x + 3}")
        self.assertEqual(result["math_segments"][1]["input"],"1/3")

    def test_math_delimiters_escapes_and_original_offsets(self):
        source="α\n"+r"$$ {@1/3@} $$ \({@2@}\) \[{@3@}\] \${@4@} \{@missing@} \{#missing#}"
        result=self.local(source)
        self.assertEqual(result["text"],"α\n"+r"$$ {\frac{1}{3}} $$ \({2}\) \[{3}\] \$$4$ {@missing@} {#missing#}")
        spans=[row["span"] for row in result["resolutions"]]
        self.assertEqual(len(spans),4)
        for row in result["resolutions"]:
            span=row["span"]
            self.assertEqual(source[span["start"]:span["end"]],"{@"+row["expression"]+"@}")
            self.assertEqual(span["line"],2)
            self.assertEqual(span["column"],span["start"]-source.rfind("\n",0,span["start"]))

    def test_ordinary_currency_unmatched_backticks_and_code_are_preserved(self):
        for text in ["Costs $20,000 and $30,000", "unmatched ` and $", "a `literal` b", "$$ unclosed"]:
            self.assertEqual(self.local(text)["text"],text)
        text="`{@missing@}`\n```python\n{@missing@}\n```\n~~~\n{#missing#}\n~~~\n{@1@}"
        self.assertEqual(self.local(text)["text"],text[:-5]+"$1$")
        self.assertEqual(self.local("```\n{@missing@}")["text"],"```\n{@missing@}")
        self.assertEqual(self.local("` unmatched {@2@}")["text"],"` unmatched $2$")

    def test_order_duplicates_and_surrounding_operators_are_retained(self):
        result=self.local("${@a@}+{@b@}+{@a@}$",{"a":sp.Integer(2),"b":sp.Integer(3)})
        self.assertEqual([row["input"] for row in result["resolutions"]],["2","3","2"])
        self.assertEqual(result["math_segments"][0]["input"],"{2}+{3}+{2}")
        swapped=self.local("${@b@}-{@a@}+{@a@}$",{"a":sp.Integer(2),"b":sp.Integer(3)})
        self.assertNotEqual(result["math_segments"],swapped["math_segments"])
        self.assertEqual(len(self.local("{@1@} {@1@}")["math_segments"]),2)
        # Math segments alone are deliberately insufficient for B1: raw values
        # in prose must also be represented by the ordered resolution sequence.
        first=self.local("Value {#1#}")
        second=self.local("Value {#2#}")
        self.assertEqual(first["math_segments"],[])
        self.assertNotEqual(first["resolutions"],second["resolutions"])

    def test_raw_scalar_roundtrips_through_actual_math_parser(self):
        x=sp.Symbol("x")
        values=[sp.Rational(1,3),2/(x+3)**2,sp.Abs(x),sp.I,sp.pi,sp.E,
                sp.sin(x)+sp.cos(x),sp.sqrt(2),sp.Rational(-17,100)]
        for value in values:
            with self.subTest(value=value):
                text=_input(value)
                parsed=parse_expr(text,local_dict=build_locals("x"),transformations=TRANSFORMATIONS)
                self.assertEqual(sp.simplify(parsed-value),0)
        self.assertEqual(_input(sp.Abs(x)),"abs(x)")
        self.assertEqual(_input(sp.I),"I")

    def test_matrix_latex_and_explicit_unsupported_raw_types(self):
        matrix=sp.Matrix([[1,sp.Rational(1,3)],[2,3]])
        self.assertIn(r"\begin{matrix}",self.local("{@A@}",{"A":matrix})["text"])
        for value in (matrix,[1,2],{"a":1},True,False,"x",sp.Float("1.2"),sp.oo,-sp.oo,sp.zoo,sp.nan):
            with self.subTest(value=value),self.assertRaises((ValueError,GenerationError)):
                self.local("{#A#}",{"A":value})
        for expression in ("oo","-oo","1/0","raw('x')","'x'","True","[1,2]","{'a':1}"):
            with self.subTest(expression=expression),self.assertRaises((ValueError,GenerationError)):
                self.local("{#"+expression+"#}")

    def test_display_decimal_ties_zeros_carry_and_significant_notation(self):
        for expression,expected in [
            ("dispdp(1.005,2)","1.01"),("dispdp(-1.005,2)","-1.01"),
            ("dispdp(1,2)","1.00"),("dispdp(-0.00001,2)","0.00"),
            ("dispsf(0.00125,2)","0.0013"),("dispsf(9.95,2)","1.0*10^1"),
            ("dispsf(0,3)","0.00"),("dispsf(-99.5,2)","-1.0*10^2")]:
            with self.subTest(expression=expression):
                result=self.local("{#"+expression+"#}")
                self.assertEqual(result["text"],expected)
                value=result["resolutions"][0]["value"]
                self.assertIn("display",value)
        self.assertEqual(self.local("{@dispsf(9.95,2)@}")["text"],r"$1.0\times 10^{1}$")

    def test_display_cannot_enter_arithmetic_or_teacher_codec(self):
        value=_display("dispdp",sp.Integer(1),2)
        self.assertIsInstance(value,DisplayValue)
        with self.assertRaises(TypeError): value+1
        with self.assertRaisesRegex(ValueError,"unsupported exact value"):
            question_context(["a"],{}, {"a":value})
        for expression in ("dispdp(1,2)+1","sin(dispdp(1,2))","dispsf(dispdp(1,2),2)",
                "dispdp(1,-1)","dispsf(1,0)","dispdp(1,True)","dispsf(1,1.5)",
                "dispdp(1,1001)","dispdp(oo,2)"):
            with self.subTest(expression=expression),self.assertRaises((ValueError,GenerationError)):
                self.local("{@"+expression+"@}")
        with self.assertRaises(GenerationError): execute("a=dispdp(1,2)")

    def test_reserved_names_and_malformed_source_fail_contextually(self):
        for name in ("dispdp","dispsf","round","sigfig","sin","subs","raw"):
            with self.subTest(name=name),self.assertRaises((ValueError,GenerationError)):
                self.local("{@1@}",{name:sp.Integer(1)})
        for name in ("sin","True","False","None","Integer","abs","floor","sqrt","oo","inf","I","pi","E"):
            with self.subTest(symbol=name),self.assertRaisesRegex(GenerationError,"unsupported placeholder symbol name"):
                render("{#v#}",variables={"v":sp.Symbol(name)})
        for text in ("hello\n{@missing@}","hello\n{@x", "hello\n{@ @}","hello\n{@a+{@b@}@}",
                     "hello\n@}","hello\n{#__import__('os')#}","hello\n{#1e999999999#}"):
            with self.subTest(text=text),self.assertRaisesRegex(GenerationError,"course.qmd: tangent: line 2, column "):
                render(text,file="course.qmd",label="tangent")

    def test_single_worker_import_amortization_and_timeout_cleanup(self):
        import ctm_variants.placeholders as placeholders
        real=placeholders.subprocess.Popen
        children=[]
        def launch(*args,**kwargs):
            child=real(*args,**kwargs);children.append(child);return child
        with patch.object(placeholders.subprocess,"Popen",launch):
            result=render("{@1@} {#2#} {@3@}")
            self.assertEqual(result["text"],"$1$ 2 $3$")
            for option in ("placeholder_timeout","template_timeout"):
                with self.assertRaisesRegex(GenerationError,"time budget"):
                    render("{@1@}",**{option:0.001})
        self.assertEqual(len(children),3)
        self.assertTrue(all(child.poll() is not None for child in children))
        self.assertFalse(any(thread.name=="ctm-placeholder-reader" for thread in threading.enumerate()))


if __name__ == "__main__":
    unittest.main()
