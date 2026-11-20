"""GR-1: numeric mode's tolerance is inclusive on both sides of the key.

The extended audit of 30 October 2026 (ctm-assessment
docs/audit-2026-11-extended, appendix-grading.md) reproduced that
`abs(sv - cv) <= tolerance` in binary floating point rejected 6 of 20 exact
absolute 0.1 boundaries around the keys 1..10 (1.1 - 1 is
0.10000000000000009), and the same asymmetry at 10 %. AGPL-3.0-or-later.
"""
import os
import pathlib
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path[:0] = (os.environ.get("CTM_CHECKERS_WHEEL") or str(ROOT / "src")).split(os.pathsep)
from ctm_checkers.math_exercise.checks import check
from ctm_checkers.math_exercise.numeric import within_tolerance

BASE = dict(reject='', tolerance='', decplaces='', sigfigs='', form='',
            partial_credit=False, form_credit=0.5, vars='', mode='numeric')


def status(student, correct, tolerance, **extra):
    return check({**BASE, **extra, 'student': student, 'correct': correct, 'tolerance': tolerance})['status']


class InclusiveToleranceTests(unittest.TestCase):
    def test_absolute_boundaries_around_integer_keys(self):
        for key in range(1, 11):
            for sign in ('+', '-'):
                with self.subTest(key=key, sign=sign):
                    self.assertEqual(status(f'{key}{sign}0.1', str(key), '0.1'), 'correct')
                    self.assertEqual(status(f'{key}{sign}0.1000001', str(key), '0.1'), 'wrong')

    def test_percentage_boundaries_and_negative_keys(self):
        self.assertEqual(status('1.1', '1', '10%'), 'correct')
        self.assertEqual(status('0.9', '1', '10%'), 'correct')
        self.assertEqual(status('-1.1', '-1', '10%'), 'correct')
        self.assertEqual(status('-0.9', '-1', '10 %'), 'correct')
        self.assertEqual(status('-1.1000001', '-1', '10%'), 'wrong')
        self.assertEqual(status('110', '100', '10%'), 'correct')
        self.assertEqual(status('110.0001', '100', '10%'), 'wrong')

    def test_zero_tolerance_and_zero_key(self):
        self.assertEqual(status('0', '0', '0%'), 'correct')
        self.assertEqual(status('0', '0', '0'), 'correct')
        self.assertEqual(status('1e-12', '0', '0%'), 'wrong')
        self.assertEqual(status('2/4', '0.5', '0'), 'correct')

    def test_computed_answers_and_keys(self):
        # The key and the answer are read at 15 significant digits, as
        # round_places reads them, so 1.05*1.9 is 1.995.
        self.assertEqual(status('2.095', '1.05*1.9', '0.1'), 'correct')
        self.assertEqual(status('pi', '3.14', '0.0016'), 'correct')
        self.assertEqual(status('pi', '3.14', '0.0015'), 'wrong')

    def test_not_finite_and_invalid(self):
        self.assertEqual(status('oo', '1', '0.1'), 'wrong')
        self.assertEqual(status('1', '1', 'abc'), 'error')
        self.assertFalse(within_tolerance(float('inf'), 1.0, '0.1'))
        self.assertTrue(within_tolerance(1.0, 1.0, 'inf'))

    def test_compute_key_uses_the_same_rule(self):
        from ctm_checkers.math_exercise.keys import compute_key
        request = {'recipe': {'op': 'value', 'expr': '1'}, 'answer': '1.1', 'vars': '',
                   'mode': 'numeric', 'tolerance': '0.1'}
        self.assertEqual(compute_key(request), {'key': '1', 'computed': True})
        with self.assertRaises(ValueError):
            compute_key({**request, 'answer': '1.1000001'})


class ExactToleranceTests(unittest.TestCase):
    """Audit of 20 Nov 2026: reading values at 15 significant digits loosened
    keys of more than 15 digits (finding 3) and still rejected exact rational
    boundaries (finding 4). The comparison is now exact."""

    def test_more_than_fifteen_digits_is_not_loosened(self):
        self.assertEqual(status('1234567890123459', '1234567890123456', '1'), 'wrong')
        self.assertEqual(status('1234567890123457', '1234567890123456', '1'), 'correct')
        self.assertEqual(status('100000000000000400000', '1e20', '1'), 'wrong')
        self.assertEqual(status('factorial(20)+1000', 'factorial(20)', '0'), 'wrong')
        self.assertEqual(status('1.100000000000004', '1', '0.1'), 'wrong')

    def test_exact_rational_boundaries(self):
        self.assertEqual(status('41/30', '2/3', '0.7'), 'correct')
        self.assertEqual(status('1/3+1/10', '1/3', '30%'), 'correct')
        self.assertEqual(status('1/3+1/10+1/10^30', '1/3', '30%'), 'wrong')

    def test_irrational_values(self):
        self.assertEqual(status('sqrt(2)', '1.414', '0.0003'), 'correct')
        self.assertEqual(status('sqrt(2)', '1.414', '0.0002'), 'wrong')

    def test_huge_literals_do_not_build_huge_rationals(self):
        import time
        start = time.monotonic()
        # A huge tolerance (author data) is not turned into a billion-digit
        # rational. (An answer such as 1e999999999 already hangs SymPy's own
        # parse, before and after this change: Stop ends that check.)
        self.assertEqual(status('1', '1', '1e999999999%'), 'correct')
        self.assertLess(time.monotonic() - start, 5)


if __name__ == '__main__':
    unittest.main()
