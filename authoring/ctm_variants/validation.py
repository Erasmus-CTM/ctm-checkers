"""Native validation of one supplied resolved Math candidate. AGPL-3.0-or-later.

No generation, placeholders, answer printing, approval or grading rules live here.
Like run_question, this synchronous leaf executes trusted author checker code.
"""
import copy


class CandidateValidationError(ValueError):
    pass


def validate_math_candidate(options, base, *, context, teacher_inputs,
                            file="<question>", label="<exercise>", locator=None):
    """Run the mandatory teacher vector and authored declarative cases.

    context is the existing question_context envelope; teacher_inputs maps its
    field labels to already-resolved literal student strings. In particular,
    teacher expressions are never evaluated or printed by this adapter.
    """
    from ctm_checkers.variants import decode_context
    from ctm_checkers.math_exercise.authored import run_question
    from ctm_checkers.testing import Raw, _expect

    phase = "context"
    where = "{}: {}".format(file, label)
    if locator is not None:
        where += ": candidate " + str(locator)
    try:
        fields, variables, teacher, identity = decode_context(context)
        if not isinstance(options, dict):
            raise ValueError("resolved question options must be a mapping")
        labels = options.get("field-labels")
        labels = [item.strip() for item in labels.split(",")] if isinstance(labels, str) else labels
        if labels != fields:
            raise ValueError("field-labels must equal the ordered context labels")
        if options.get("question-variables"):
            raise ValueError("resolved question variables belong in context, not question-variables")
        if (type(teacher_inputs) is not dict or set(teacher_inputs) != set(fields)
                or any(type(value) is not str for value in teacher_inputs.values())):
            raise ValueError("teacher_inputs must map every context field to a literal student string")
        tests = options.get("tests", [])
        if not isinstance(tests, list):
            raise ValueError("candidate validation supports declarative tests only; legacy Python tests are unchanged")
        resolved = copy.deepcopy(options)
        arguments = dict(variables=variables, teacher=teacher, variant=identity)
        phase = "teacher answers"
        automatic = {"name": "teacher answers", "answers": {
            field: Raw(teacher_inputs[field]) for field in fields}, "expect": "correct"}
        result = run_question(dict(resolved, tests=[automatic]), base, **arguments)[0]
        # A custom grader may return an overall success with field diagnostics.
        # Keep the common verdict assertion, including detailed form statuses;
        # inventing a new numerical score rule here would alter grading semantics.
        for field, actual in result["actual"].get("fields", {}).items():
            _expect(actual, "correct", "teacher answers/" + str(field))
        phase = "authored tests"
        authored = run_question(resolved, base, **arguments) if tests else []
        return {"passed": True, "teacher": result, "tests": authored}
    except Exception as error:
        raise CandidateValidationError("{}: {}: {}".format(where, phase, error)) from error
