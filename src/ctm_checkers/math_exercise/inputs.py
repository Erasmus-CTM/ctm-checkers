"""What a math-exercise request may bring from the learner, and the rule it
must pass before anything runs (moved from math-exercise 0.10.0's
_learner_strings and _math_run; the request's fields replace the _math_*
globals)."""


def learner_strings(request):
    # Only what this request brought.
    if "student" in request and request.get("mode") not in ("string", "string_ci"):
        yield request["student"] or ""  # string answers are never evaluated
    response = request.get("response")
    if isinstance(response, dict):
        yield from response.get("raw", []) or []
        for item in (response.get("inputs") or {}).values():
            if isinstance(item, dict):
                yield from item.get("raw", []) or []


def admit(request):
    # Learner answers are parsed by SymPy (which evaluates Python): no dunder
    # access. Author data (variants, checkers) is not restricted.
    if any("__" in str(text) for text in learner_strings(request)):
        raise ValueError("SyntaxError: unsupported input")
