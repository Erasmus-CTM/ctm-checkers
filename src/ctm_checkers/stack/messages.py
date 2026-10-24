"""Structured presentation messages; no grading or exception classification.

`text` is the existing English fallback. Arguments are data, never trusted
markup. Only this renderer turns a mathematical argument into escaped LaTeX.
"""
import html


def message(code, english, **args):
    return {"code": code, "args": args, "text": english}


def render_messages(messages):
    rendered = []
    for item in messages:
        code, args = item["code"], item["args"]
        if code in {"ATSets_wrongentries", "ATSets_missingentries"}:
            label = "Extra elements: " if code == "ATSets_wrongentries" else "Missing elements: "
            values = ", ".join(r"\(" + html.escape(value["latex"]) + r"\)" for value in args["elements"])
            rendered.append(label + values + ".")
        else:
            rendered.append(html.escape(item["text"]))
    return " ".join(rendered)


def feedback_html(result):
    return render_messages(result["messages"]) if result.get("messages") else html.escape(result["feedback"])


_VALIDATION = {
    "Review the parsed answers": "stack_validated",
    "Correct invalid answers before grading": "stack_invalid_answers",
    "Check your answers before grading": "stack_check_answers",
    "Enter an answer": "stack_enter_answer",
}


def decorate_result(result):
    """Add codes at the browser boundary; the engine's grading fields stay put."""
    if not isinstance(result, dict):
        return result
    if "inputs" in result:
        for item in result["inputs"].values():
            if item.get("feedback"):
                text = item["feedback"]
                code = _VALIDATION.get(text, "stack_input_invalid")
                item["message"] = message(code, text, **({"text": text} if code == "stack_input_invalid" else {}))
    if result.get("feedback") in _VALIDATION:
        text = result["feedback"]
        result["message"] = message(_VALIDATION[text], text)
    return result
