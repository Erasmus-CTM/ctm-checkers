"""Exact authoring rounding, separate from legacy float grading. AGPL-3.0-or-later."""
import pathlib
import os
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path[:0] = (os.environ.get("CTM_CHECKERS_WHEEL") or str(ROOT / "src")).split(os.pathsep)
import sympy as sp
from ctm_checkers.math_exercise.numeric import (round_exact, sigfig_exact,
    round_places, sigfigs_round, parse_tolerance)


class ExactRoundingTests(unittest.TestCase):
    def test_decimal_ties_and_neighbours_beyond_float_precision(self):
        for sign in (1, -1):
            for text, expected in [("1.005", sp.Rational(101,100)),
                    ("1.00499999999999999999999999999", sp.Integer(1)),
                    ("1.00500000000000000000000000001", sp.Rational(101,100))]:
                self.assertEqual(round_exact(sign*sp.Rational(text), 2), sign*expected)
        self.assertEqual(round_exact(sp.Rational(25,10)), 3)
        self.assertEqual(round_exact(sp.Rational(-25,10)), -3)
        self.assertEqual(round_exact(sp.Rational(1,3), 3), sp.Rational(333,1000))
        self.assertEqual(round_exact(1250, -2), 1300)
        self.assertEqual(round_exact(-1250, -2), -1300)

    def test_significant_figures_decades_carry_and_ties(self):
        for value, figures, expected in [
            (0, 2, 0), (1, 3, 1), (10, 1, 10), (1000, 2, 1000),
            (sp.Rational("0.00125"), 2, sp.Rational("0.0013")),
            (sp.Rational("9.95"), 2, 10), (sp.Rational("99.5"), 2, 100),
            (sp.Rational("0.0995"), 2, sp.Rational("0.10")),
            (10**100-1, 3, 10**100),
            (sp.Rational(1,10**100+1), 3, sp.Rational(1,10**100))]:
            for sign in (1,-1):
                with self.subTest(value=value, figures=figures, sign=sign):
                    result = sigfig_exact(sign*value, figures)
                    self.assertEqual(result, sign*expected)
                    self.assertIsInstance(result, sp.Rational)
                    self.assertFalse(result.has(sp.Float))

    def test_exact_transcendentals_algebraics_and_near_ties(self):
        self.assertEqual(round_exact(sp.sqrt(2), 3), sp.Rational(707,500))
        self.assertEqual(sigfig_exact(sp.sin(sp.pi/7), 2), sp.Rational(43,100))
        self.assertEqual(sigfig_exact(-sp.sin(sp.pi/7), 2), sp.Rational(-43,100))
        self.assertEqual(sigfig_exact(sp.pi, 3), sp.Rational(157,50))
        self.assertEqual(sigfig_exact(sp.E, 2), sp.Rational(27,10))
        delta = sp.sqrt(2)/10**60
        self.assertEqual(round_exact(sp.Rational(1,2)-delta), 0)
        self.assertEqual(round_exact(sp.Rational(1,2)+delta), 1)

    def test_invalid_values_and_precision_fail_explicitly(self):
        for value in [True, False, 1.005, sp.Float("1.005"), "1.005", sp.I,
                sp.oo, -sp.oo, sp.zoo, sp.nan, sp.Symbol("x"),
                sp.Symbol("a", real=True), sp.Matrix([[1]]), [1], None]:
            for helper in (round_exact, sigfig_exact):
                with self.subTest(value=value, helper=helper), self.assertRaises(ValueError):
                    helper(value, 2)
        for precision in [True, False, 2.0, sp.Rational(3,2), "2", sp.Symbol("n"), None]:
            for helper in (round_exact, sigfig_exact):
                with self.subTest(precision=precision, helper=helper), self.assertRaises(ValueError):
                    helper(1, precision)
        for figures in (0, -1):
            with self.assertRaisesRegex(ValueError, "positive"):
                sigfig_exact(1, figures)

    def test_legacy_float_rule_and_tolerance_are_unchanged(self):
        self.assertEqual(round_places(5.395, 2), 5.4)
        self.assertEqual(round_places(-5.395, 2), -5.4)
        self.assertEqual(sigfigs_round(1.995, 3), 2.0)
        self.assertIsInstance(round_places(1.005, 2), float)
        self.assertEqual(parse_tolerance(" 2% ", -50), 1.0)
        self.assertEqual(parse_tolerance("0.01", 50), 0.01)


if __name__ == "__main__":
    unittest.main()
