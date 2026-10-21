"""math-exercise's authored question tests (`#| tests:`), run at build time
and by the documented command
`python _extensions/math-exercise/question-tests.py lesson.qmd`, which calls
main() (moved from math-exercise 0.10.0's question-tests.py; its checker
namespace comes from custom.namespace instead of decoding math-exercise.js)."""
import json
from pathlib import Path
import re
import sys

# question-tests.py's usage text: main() reports it when it has no arguments.
USAGE = """Run trusted author assertions next to custom math-exercise checkers.

Usage: python _extensions/math-exercise/question-tests.py lesson.qmd [...]
Quarto invokes --stdin for a single exercise containing #| tests: |."""


def _legacy_question(options, base):
    # SymPy is imported here, not with the module: main() reports a missing
    # SymPy as question-tests.py did.
    from sympy import Symbol
    from ..testing import run_tests
    from .custom import namespace
    from .parsing import build_locals
    if options.get('mode') != 'custom' or not options.get('checker', '').strip():
        raise ValueError('Authored tests currently require mode: custom and checker: |')
    scope = namespace({'vars': options.get('vars', '')})
    symbols = {k: v for k, v in build_locals(options.get('vars', '')).items()
               if isinstance(v, Symbol)}
    exec(options['checker'], scope)
    run_tests(None, symbols, options['tests'], namespace=scope, base=base)



def _tests(value):
    if isinstance(value, list):
        return value
    if not isinstance(value, str):
        raise ValueError("tests must be Python code or a declarative list")
    if "\n" not in value and value.endswith(".py"):
        return None
    first = next((line.strip() for line in value.splitlines() if line.strip() and not line.lstrip().startswith("#")), "")
    if first.startswith(("-", "[")):
        try:
            import yaml
        except ImportError as error:
            raise ValueError("declarative question tests need PyYAML on the render machine") from error
        class UniqueKeys(yaml.SafeLoader):
            pass
        def mapping(loader, node):
            result = {}
            for key_node, value_node in node.value:
                key = loader.construct_object(key_node)
                if key in result:
                    raise ValueError("duplicate tests key: " + str(key))
                result[key] = loader.construct_object(value_node)
            return result
        UniqueKeys.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, mapping)
        return yaml.load(value, Loader=UniqueKeys)
    return None



def _question_math(text):
    """The component's existing plain-text math-delimiter transport."""
    out, position = "", 0
    while position < len(text):
        if text[position] == "\x60" and (position == 0 or text[position-1] != "\\"):
            end = text.find("\x60", position+1)
            newline = text.find("\n", position+1)
            if end > position+1 and (newline < 0 or end < newline):
                out += text[position:end+1]
                position = end+1
                continue
        if text[position] == "$" and position and text[position-1] == "\\":
            out = out[:-1] + "\ue024"
            position += 1
            continue
        if text[position] != "$":
            out += text[position]
            position += 1
            continue
        delimiter = "$" if text.startswith("$", position) else "$"
        end = text.find(delimiter, position+len(delimiter))
        while end >= 0:
            slashes, before = 0, end-1
            while before >= 0 and text[before] == "\\":
                slashes += 1
                before -= 1
            if slashes % 2 == 0:
                break
            end = text.find(delimiter, end+len(delimiter))
        if end < 0:
            out += "$"
            position += 1
            continue
        display = delimiter == "$"
        out += ("\\[" if display else "\\(") + text[position+len(delimiter):end] + ("\\]" if display else "\\)")
        position = end+len(delimiter)
    return out


def _teacher_fields(question):
    """Extract author keys in scalar/vector/fixed-matrix field order."""
    from .parsing import split_top
    question = _question_math(question)
    keys, position = [], 0
    while position < len(question):
        match = re.match(r"(_+|vec|mat)\[", question[position:])
        if not match or (match[1] in ("vec", "mat") and position and re.match(r"[A-Za-z0-9_]", question[position-1])):
            position += 1
            continue
        start, depth, index = position + len(match[0]), 1, position + len(match[0])
        while index < len(question) and depth:
            if question[index] == "[": depth += 1
            elif question[index] == "]": depth -= 1
            index += 1
        if depth:
            position += 1
            continue
        content = question[start:index-1].replace("\ue024", "$")
        if match[1] == "vec":
            keys.extend(split_top(content))
        elif match[1] == "mat":
            rows = [split_top(row) for row in split_top(content, ";")]
            if rows and len({len(row) for row in rows}) != 1:
                raise ValueError("matrix rows have different lengths")
            keys.extend(item for row in rows for item in row)
        else:
            keys.append(content)
        position = index
    return keys


def run_question(options, base, *, variables=None, teacher=None):
    """Declarative cases use real grading; legacy assertions stay unchanged.

    variables/teacher are resolved question data from the variants adapter.
    This runner neither generates variants nor unifies custom runners.
    """
    from ..testing import Raw, input_text, run_declarative
    from sympy import Number
    import math
    from . import check, check_custom
    from .inputs import admit
    from .parsing import build_locals
    tests = _tests(options["tests"])
    if tests is None:
        return _legacy_question(options, base)
    mode = options.get("mode", "equivalent")
    if mode not in ("equivalent", "numeric", "exact", "set", "string", "string_ci", "custom"):
        raise ValueError("unknown math-exercise mode: " + mode)
    local = build_locals(options.get("vars", ""))
    local.update(variables or {})
    local.update(options.get("question-variables", {}))
    keys = teacher if teacher is not None else options.get("teacher")
    if keys is None:
        keys = _teacher_fields(options.get("question", ""))
    labels = options.get("field-labels", "")
    labels = [item.strip() for item in labels.split(",")] if isinstance(labels, str) and labels else list(labels)
    if isinstance(keys, dict):
        fields = list(keys)
        keys = list(keys.values())
    else:
        keys = list(keys)
        fields = labels or [str(n) for n in range(1, len(keys) + 1)]
    if len(fields) != len(keys) or any(not field for field in fields) or len(set(fields)) != len(fields):
        raise ValueError("field-labels must give one unique label per answer field")
    teacher_text = [str(value) if isinstance(value, str) else input_text(value) for value in keys]
    defaults = {key: str(options.get(key, "")) for key in (
        "vars", "reject", "tolerance", "decplaces", "sigfigs", "form")}
    partial = options.get("partial-credit", False) in (True, "true")
    try:
        form_credit = float(options.get("form-credit", 0.5))
    except (TypeError, ValueError):
        form_credit = 0.5
    if not math.isfinite(form_credit) or not 0 <= form_credit <= 1:
        form_credit = 0.5
    if mode == "custom" and not options.get("checker", "").strip():
        raise ValueError("mode custom requires a checker")

    def grade(payload):
        if mode == "custom":
            response = payload.get("response")
            if response is None:
                response = {"kind": "expressions", "raw": [input_text(payload["answers"][field]).strip() for field in fields], "inputs": {}}
            if isinstance(response, dict) and response.get("kind") == "expressions" and not options.get("response"):
                response = dict(response, raw=[str(value).strip() for value in response.get("raw", [])])
                values = response["raw"]
                if (not values and not response.get("inputs")) or any(not value for value in values):
                    return {"status": "empty", "score": 0, "fields": {}}
            def literal(value):
                if isinstance(value, Raw): return str(value)
                if isinstance(value, dict): return {key: literal(item) for key, item in value.items()}
                if isinstance(value, list): return [literal(item) for item in value]
                if isinstance(value, Number):
                    # JSON numbers cross the browser's IEEE754 boundary before
                    # reaching Python; exact question variables stay outside it.
                    number = float(value)
                    if not math.isfinite(number):
                        raise ValueError("custom response numbers must be finite")
                    return int(number) if number.is_integer() else number
                return value
            request = {"vars": defaults["vars"], "response": literal(response), "checker": options["checker"]}
            admit(request)
            result = check_custom(request)
            if result.get("status") == "error":
                result["score"] = 0
            result["fields"] = result.get("assessment", {}).get("fields", {})
            return result
        if "response" in payload:
            raise ValueError("response fixtures require mode custom")
        checked = {}
        for field, correct in zip(fields, teacher_text):
            request = dict(defaults, mode=mode, student=input_text(payload["answers"][field]).strip(),
                           correct=correct, partial_credit=partial, form_credit=form_credit)
            if not request["student"]:
                checked[field] = {"status": "empty", "score": 0}
                continue
            try:
                admit(request)
                checked[field] = check(request)
            except ValueError as error:
                checked[field] = {"status": "error", "message": str(error)}
        if not checked:
            raise ValueError("declarative built-in tests need answer fields")
        if any(result["status"] in ("error", "empty") for result in checked.values()):
            return {"status": "invalid", "score": 0, "fields": checked}
        score = (sum(result.get("score", 0) for result in checked.values()) / len(checked)
                 if partial else float(all(result["status"] == "correct" for result in checked.values())))
        status = "correct" if score >= 1-1e-9 else "wrong" if score <= 1e-9 else "partial"
        return {"status": status, "score": score, "fields": checked}
    return run_declarative(tests, grade, fields=fields, variables=local)


def authored_questions(path):
    for block in re.findall(r'^```\{math-exercise\}\n(.*?)^```\s*$', path.read_text(), re.M | re.S):
        options = {}
        question = []
        lines = block.splitlines()
        i = 0
        while i < len(lines):
            match = re.match(r'^#\|\s*([^:]+):\s*(.*?)\s*$', lines[i])
            i += 1
            if not match:
                if not lines[i-1].startswith('#|'):
                    question.append(lines[i-1])
                continue
            key, value = match.groups()
            if value == '|' or (key == 'tests' and not value):
                body = []
                while i < len(lines) and (lines[i].startswith('#|   ') or lines[i].strip() == '#|'):
                    body.append(lines[i][5:] if lines[i].startswith('#|   ') else '')
                    i += 1
                value = '\n'.join(body)
            options[key] = value
        options['question'] = '\n'.join(question)
        yield options


def run(argv):
    # SymPy first, as question-tests.py built its checker runtime before
    # reading anything: without it, the one message is "No module named 'sympy'".
    from . import custom  # noqa: F401
    if argv == ['--stdin']:
        questions = [(None, json.load(sys.stdin))]
    else:
        if len(argv) == 0:
            raise ValueError(USAGE)
        questions = [(path, question) for path in map(Path, argv) for question in authored_questions(path)]
    tested = untested = 0
    for path, options in questions:
        if 'tests' not in options or (isinstance(options['tests'], str) and not options['tests'].strip()):
            untested += options.get('mode') == 'custom'
            continue
        label = options.get('label', '(unlabelled exercise)')
        try:
            run_question(options, Path(options.get('tests-base', Path.cwd())))
        except Exception as error:
            raise RuntimeError(f'{path or "Quarto"}: {label}: {type(error).__name__}: {error}') from error
        tested += 1
    print(f'{tested} authored question tests passed; {untested} custom questions without tests.')


def main(argv=None):
    """question-tests.py's command line: `--stdin` (one question as JSON, as
    Quarto passes it) or .qmd files. Returns the exit status and prints the
    messages question-tests.py printed."""
    if sys.version_info < (3, 9):
        print(f'math-exercise question tests failed: ctm-checkers needs Python 3.9 or later, not {sys.version.split()[0]}', file=sys.stderr)
        return 1
    try:
        run(sys.argv[1:] if argv is None else list(argv))
    except Exception as error:
        print(f'math-exercise question tests failed: {error}', file=sys.stderr)
        return 1
    return 0
