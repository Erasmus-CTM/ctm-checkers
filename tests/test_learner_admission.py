"""A-01 (M3 of the 26 Oct 2026 review): a learner's answer cannot run Python.

math-exercise parses answers with SymPy's parse_expr, which evaluates the
text as Python. Before, admit() rejected only "__". AGPL-3.0-or-later.
"""
import os
import pathlib
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path[:0] = (os.environ.get("CTM_CHECKERS_WHEEL") or str(ROOT / "src")).split(os.pathsep)
from ctm_checkers.math_exercise.inputs import admit, admit_text
from ctm_checkers.math_exercise.checks import check

ATTACKS = [
    "eval('1')", "exec(chr(105))", "getattr(x, 'a')", "open(1)", "().count", "x.func", "x.subs",
    "lambda: 1", "[y for y in (1,)]", "x if 1 else 2", "sympify(1)", "lambdify(x, x)", "preview(x)",
    "var(1)", "globals()", "vars()", "type(x)", "compile(1)", "'a'", '"a"', "f'{1}'", "x # c",
    "Symbol.mro", "print(1)", "input()", "setattr(x, 1, 1)", "breakpoint()", "S.__class__",
    "dir()", "x := 1", "x = 1", "help()", "memoryview(b)", "init_printing()", "srepr(x)",
]
ANSWERS = [
    "(2x+1)/(x(x+1))", "x^2 + 2*x + 1", "sqrt(4), -2", "{1, 2}, 3", "[1, 2], 3", "Matrix([1, 2])",
    "3.14", "1e-3", "1,5", "2 x", "-x(2-x)(x+2)", "atan2(y,x)", "5+5*I", "pi*9", "exp(5)", "ln(x)",
    "abs(x)", "Abs(x)", "oo", "inf", "5!", "factorial(5)", "diff(x^2, x)", "integrate(x, x)",
    "sin x", "theta", "alpha + beta", "N/l", "e", "x +", "abc def", "1 < x",
]


class LearnerAdmissionTests(unittest.TestCase):
    def test_attacks_are_refused_before_parsing(self):
        for text in ATTACKS:
            with self.subTest(text=text):
                with self.assertRaises(ValueError):
                    admit_text(text, 'x y')

    def test_mathematical_notation_is_admitted(self):
        for text in ANSWERS:
            with self.subTest(text=text):
                self.assertIsNone(admit_text(text, 'x y'))

    def test_declared_variables_may_shadow_namespace_names(self):
        # An exercise may declare a variable whose name SymPy or Python also defines.
        self.assertIsNone(admit_text('2*var + input', 'var input'))
        with self.assertRaises(ValueError):
            admit_text('2*var', 'x')

    def test_check_and_custom_requests(self):
        with self.assertRaises(ValueError):
            admit({'student': "eval('1')", 'mode': 'equivalent', 'vars': 'x'})
        admit({'student': "eval('1')", 'mode': 'string'})  # string answers are never evaluated
        with self.assertRaises(ValueError):
            admit({'response': {'raw': ['1'], 'inputs': {'P': {'raw': ['x.func']}}}})
        admit({'response': {'raw': ['x + 1'], 'inputs': {}}, 'vars': 'x'})

    def test_verdicts_of_ordinary_answers_are_unchanged(self):
        base = dict(reject='', tolerance='', decplaces='', sigfigs='', form='', partial_credit=False,
                    form_credit=0.5, vars='x', mode='equivalent', correct='x^2+2*x+1')
        for student, expected in [('(x+1)^2', 'correct'), ('x^2+2x', 'wrong')]:
            request = {**base, 'student': student}
            admit(request)
            self.assertEqual(check(request)['status'], expected)


if __name__ == '__main__':
    unittest.main()
