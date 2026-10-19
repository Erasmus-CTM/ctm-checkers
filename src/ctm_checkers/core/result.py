"""The result of a custom checker, normalized (math-exercise 0.10.0's
_normalize_custom_result, moved verbatim)."""

# The statuses of math-exercise's results: normalize_result gives the first
# three; math_exercise.check also gives "not_exact", "not_form" and
# "rejected"; a check that fails gives "error" with a message.
STATUSES = ("correct", "partial", "wrong", "not_exact", "not_form", "rejected", "error")


def normalize_result(result):
    feedback = ""
    assessment = {}
    show_score = True
    if isinstance(result, bool):
        score = 1.0 if result else 0.0
    elif isinstance(result, (int, float)):
        score = float(result)
    elif isinstance(result, dict):
        feedback = str(result.get("feedback", ""))
        assessment = result.get("assessment", {})
        show_score = bool(result.get("show_score", True))
        if not isinstance(assessment, dict):
            raise TypeError("Custom checker assessment must be a dictionary")
        if "score" in result:
            score = float(result["score"])
        elif "correct" in result:
            score = 1.0 if bool(result["correct"]) else 0.0
        else:
            raise ValueError("Custom checker result needs score or correct")
    else:
        raise TypeError("Custom checker must return bool, number, or dict")
    if not 0.0 <= score <= 1.0:
        raise ValueError("Custom checker score must be between 0 and 1")
    status = "correct" if score >= 1.0 - 1e-9 else ("wrong" if score <= 1e-9 else "partial")
    return {"status": status, "score": score, "show_score": show_score, "feedback": feedback, "assessment": assessment}
