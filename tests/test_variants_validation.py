"""Resolved native candidate validation through actual grading. AGPL-3.0-or-later."""
import copy
import os
import pathlib
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "authoring")] + (os.environ.get("CTM_CHECKERS_WHEEL") or str(ROOT / "src")).split(os.pathsep)
from sympy import Rational, Symbol
from ctm_checkers.variants import question_context
from ctm_variants.validation import validate_math_candidate, CandidateValidationError


class ValidationTests(unittest.TestCase):
    def validate(self, mode="equivalent", *, teacher=None, inputs=None, variables=None, **options):
        teacher = {"Answer": Symbol("x")} if teacher is None else teacher
        inputs = {"Answer": "x"} if inputs is None else inputs
        question = dict({"mode": mode, "vars": "x", "field-labels": list(teacher)}, **options)
        return validate_math_candidate(question, ".", context=question_context(list(teacher), variables or {}, teacher), teacher_inputs=inputs)

    def test_all_seven_modes_use_literal_teacher_inputs_and_actual_grading(self):
        for mode, value, text in [
            ("equivalent", Symbol("x")**2, "x*x"),
            ("numeric", Rational(1, 2), "0.5"),
            ("exact", Rational(1, 2), "1/2"),
            ("set", "1,2,3", "3,1,2"),
            ("string", "Hello", "Hello"),
            ("string_ci", "Hello", "hello"),
            ("custom", Symbol("x"), "x")]:
            with self.subTest(mode=mode):
                result = self.validate(mode, teacher={"Answer": value}, inputs={"Answer": text},
                    checker='def check(r,s): return r["answers"] == r["teacher"]')
                self.assertTrue(result["passed"])
                self.assertEqual(result["tests"], [])
                self.assertEqual(result["teacher"]["actual"]["status"], "correct")

    def test_every_builtin_teacher_field_must_be_correct(self):
        with self.assertRaisesRegex(CandidateValidationError, "teacher answers"):
            self.validate(teacher={"Answer": Rational(1, 2), "Other": 1},
                inputs={"Answer": "1/2", "Other": "2"})
        # An overall score of one does not excuse a noncanonical field verdict.
        with self.assertRaisesRegex(CandidateValidationError, "not_exact"):
            self.validate("exact", teacher={"Answer": Rational(1, 2)}, inputs={"Answer": "2/4"},
                **{"partial-credit": True, "form-credit": 1})

    def test_custom_aggregate_cannot_hide_bad_reported_teacher_field(self):
        checker = 'def check(r,s): return {"score":1,"assessment":{"fields":{"Answer":{"status":"wrong","score":0}}}}'
        with self.assertRaisesRegex(CandidateValidationError, "teacher answers/Answer"):
            self.validate("custom", checker=checker)
        with self.assertRaisesRegex(CandidateValidationError, "expected correct"):
            self.validate("custom", checker="def check(r,s): return False")
        # Preserve the real normalizer's near-endpoint success; no new score=1 rule.
        self.validate("custom", checker="def check(r,s): return 0.9999999995")

    def test_exact_context_named_answers_assumptions_identity_and_legacy_view(self):
        x = Symbol("x", positive=True)
        teacher = {"Svar α": x/3, "Second field": x}
        identity = {"n": 7, "id": "supplied", "hash": "supplied-hash"}
        context = question_context(list(teacher), {"a": Rational(1, 3), "x": x}, teacher, identity)
        checker = '''def check(r,s):
    assert list(r["answers"]) == ["Svar α", "Second field"]
    assert r["variables"]["a"] == Rational(1,3)
    assert r["variables"]["x"] is s["x"] and s["x"].is_positive
    assert r["expressions"] == [s["x"]/3,s["x"]]
    assert r["answers"] == r["teacher"]
    assert r["variant"] == {"n":7,"id":"supplied","hash":"supplied-hash"}
    return True
'''
        options = {"mode": "custom", "vars": "x", "field-labels": list(teacher), "checker": checker,
            "tests": [{"name": "authored exact context", "answers": ["a*x", "x"], "expect": "correct"}]}
        before = copy.deepcopy((options, context))
        result = validate_math_candidate(options, ".", context=context,
            teacher_inputs={"Svar α": "x/3", "Second field": "x"})
        self.assertEqual(len(result["tests"]), 1)
        self.assertEqual((options, context), before)

    def test_authored_raw_partial_and_failure_use_existing_test_schema(self):
        tests = [{"name": "written form", "answers": ["raw('2/4')"],
                  "expect": "partial", "score": 0.25, "partial": True}]
        self.validate("exact", teacher={"Answer": Rational(1, 2)}, inputs={"Answer": "1/2"},
            tests=tests, **{"partial-credit": True, "form-credit": 0.25})
        tests[0]["expect"] = "correct"
        with self.assertRaisesRegex(CandidateValidationError, "authored tests.*written form"):
            self.validate("exact", teacher={"Answer": Rational(1, 2)}, inputs={"Answer": "1/2"}, tests=tests)

    def test_context_and_literal_input_mismatches_fail_before_grading(self):
        context = question_context(["Answer"], {}, {"Answer": Symbol("x")})
        for options, inputs, envelope in [
            ({}, {"Answer": "x"}, context),
            ({"field-labels": ["Other"]}, {"Answer": "x"}, context),
            ({"field-labels": ["Answer"], "question-variables": {"a": 1}}, {"Answer": "x"}, context),
            ({"field-labels": ["Answer"]}, {"Answer": Symbol("x")}, context),
            ({"field-labels": ["Answer"]}, {"Other": "x"}, context),
            ({"field-labels": ["Answer"]}, {"Answer": "x"}, dict(context, variant={"n": 1})),
            ({"field-labels": ["Answer"], "tests": "def test(c,s): pass"}, {"Answer": "x"}, context)]:
            with self.subTest(options=options), self.assertRaises(CandidateValidationError):
                validate_math_candidate(options, ".", context=envelope, teacher_inputs=inputs)

    def test_no_identity_is_invented_and_diagnostics_name_source_candidate_phase(self):
        self.validate("custom", checker='def check(r,s): return r["variant"] is None')
        with self.assertRaisesRegex(CandidateValidationError, "course.qmd: tangent: candidate exact-tape: teacher answers"):
            validate_math_candidate({"mode": "custom", "vars": "x", "field-labels": ["Answer"],
                "checker": "def check(r,s): raise ValueError('author failure')"}, ".",
                context=question_context(["Answer"], {}, {"Answer": Symbol("x")}),
                teacher_inputs={"Answer": "x"}, file="course.qmd", label="tangent", locator="exact-tape")


if __name__ == "__main__":
    unittest.main()
