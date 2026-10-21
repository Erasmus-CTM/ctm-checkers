"""STACK's rules for the text of a student's answer (S-13), with STACK's
messages, before the answer is parsed (expressions.parse).

STACK (10d3233) validates an answer in PHP before Maxima sees it
(stack/maximaparser/corrective_parser.php, stack/cas/parsingrules/): it
replaces known Unicode symbols and letters (π: pi, α: alpha, −: -, ×: *),
rejects other characters outside its ASCII set (x²: "CAS commands may not
contain the following characters: ²."), rejects spaces between two terms
("Illegal spaces found in expression 2_x."), and checks every identifier
(998_security.filter.php, cassecurity.class.php): a student may use a
variable name of one or two letters, one that ends in a digit, or one STACK
knows (alpha, theta, pi, ...); every other name of three letters or more is
forbidden ("Forbidden variable or constant: sinx."), part by part at
underscores; a function or variable that STACK knows in another case is
"case sensitive" (Sin(x), PI); In(x) is not ln(x). The question variables
are forbidden too (S-01), and here also the response trees' feedback
variables and a name that STACK lets through only part by part (a_b).

STACK's data for these rules is in stack_data.py, generated from STACK's
own files by tools/stack_native/stack_input_data.py.
"""

from __future__ import annotations

import re

from .expressions import InvalidAnswer, LOGIC_OPERATORS, _LEX
from . import stack_data

# STACK's messages (lang/en/qtype_stack.php), as plain text.
FORBIDDEN_CHAR = "CAS commands may not contain the following characters: {char}."
SPACES = "Illegal spaces found in expression {expr}."
TRIG_SPACE = "To apply a trig function to its arguments you must use brackets, not spaces.  For example use {trig} instead."
COMMA = ("A comma in your expression appears in a strange way.  Commas are used to separate items in lists, sets etc.  "
         "You need to use a decimal point, not a comma, in floating point numbers.")
FORBIDDEN_VARIABLE = "Forbidden variable or constant: {name}."
FORBIDDEN_WORD = "The expression {name} is forbidden."
VARIABLE_CASE = "Input is case sensitive: {name} is an unknown variable. Did you mean {lower}?"
FUNCTION_CASE = "Input is case sensitive: {name} is an unknown function. Did you mean {lower}?"
BAD_LOG_IN = ('You have typed in the expression In.  The natural logarithm is entered as ln in lower case.  '
              '("Lima November" not "India November")')

# corrective_parser.php: the characters an answer may contain once the
# known symbols and letters are replaced.
_ALLOWED = frozenset('0123456789,./\\%#&{}[]()$@!"\'?`^~*_+qwertyuiopasdfghjklzxcvbnmQWERTYUIOPASDFGHJKLZXCVBNM:;=>< |-')
_CONTROL = {"\n": "\\n", "\r": "\\r", "\t": "\\t", "\v": "\\v", "\x1b": "\\e", "\f": "\\f"}
# Spaces STACK keeps (logic and control flow keywords) and those it reads as
# a missing operator between two terms.
_SAFE_SPACES = [(" or ", "STACKOR"), (" and ", "STACKAND"), ("not ", "STACKNOT"), ("nounnot ", "STACKNOUNNOT"),
                (" nor ", "STACKNOR"), (" nand ", "STACKNAND"), (" xor ", "STACKXOR"), (" xnor ", "STACKXNOR"),
                (" implies ", "STACKIMPLIES"), (" nounor ", "STACKNOUNOR"), (" nounand ", "STACKNOUNAND"),
                (" else if ", "%%STACKELSEIF%%"), (" if ", "%%STACKIF%%"), (":if ", ":%%STACKIF%%"),
                (" then ", "%%STACKTHEN%%"), (" else ", "%%STACKELSE%%")]
_FIXED_SPACE = re.compile(r"([A-Za-z0-9_)]+)[ ]([A-Za-z0-9_(]+)", re.ASCII)
_MARK = "@@Is@@"


def _cases(names):
    out = {}
    for name in names:
        out.setdefault(name.lower(), []).append(name)
    return out


_VARIABLE_CASES = _cases(stack_data.VARIABLES)
_FUNCTION_CASES = _cases(stack_data.FUNCTIONS)
_FUNCTION_NAMES = frozenset(stack_data.FUNCTIONS)


def student_text(raw: str) -> str:
    """The answer as STACK reads it: known Unicode symbols and letters
    replaced (in STACK's order); any other character outside STACK's set is
    an error, which names the first such character (as STACK does)."""
    text = raw
    for old, new in stack_data.REPLACEMENTS:
        if old in text:
            text = text.replace(old, new)
    for character in text:
        if character not in _ALLOWED:
            raise InvalidAnswer(FORBIDDEN_CHAR.format(char=_CONTROL.get(character, character)))
    return text


def space_messages(text: str):
    """A space between two terms (2 x, sin x, (x+1) (x-1)) is an error, as in
    STACK (with or without insertstars): STACK shows the answer with an
    underscore for each such space, and a trigonometric function followed by
    a space gets its own hint. Returns the messages and the names of those
    functions."""
    collapsed = re.sub(r"\s+", " ", text.strip(), flags=re.ASCII)
    if " " not in collapsed:
        return [], set()
    marked = collapsed
    for key, placeholder in _SAFE_SPACES:
        marked = marked.replace(key, placeholder)
    fixed = False
    while _FIXED_SPACE.search(marked):
        fixed = True
        marked = _FIXED_SPACE.sub(r"\1" + _MARK + r"\2", marked)
    for key, placeholder in _SAFE_SPACES:
        marked = marked.replace(placeholder, key)
    if not fixed:
        return [], set()
    messages, trig = [SPACES.format(expr=_input_form(marked))], set()
    for name in re.findall(r"([A-Za-z0-9_%]+)" + re.escape(_MARK), marked):
        if name in stack_data.TRIG_FUNCTIONS:
            messages.append(TRIG_SPACE.format(trig=name + "(...)"))
            trig.add(name)
    return messages, trig


def _input_form(marked: str) -> str:
    """The answer as STACK prints it in the spaces message: no spaces around
    operators, an underscore for each space between two terms."""
    text = re.sub(r"\s*([-+*/^=,()\[\]{}<>])\s*", r"\1", marked)
    return text.replace(_MARK, "_")


def _readable(name: str, keys) -> bool:
    """cassecurity::is_allowed_to_read for a student (no allowed words)."""
    if name in stack_data.UNREADABLE:
        return False
    if name in stack_data.READABLE:
        return True
    if name in keys:
        return False
    if len(name) <= 2 and name not in _FUNCTION_NAMES:
        return True
    return name[-1:].isdigit()


def _callable(name: str, keys) -> bool:
    """cassecurity::is_allowed_to_call for a student (no allowed words)."""
    if name in stack_data.CALLABLE:
        return True
    if name in keys or name == "In":
        return False
    return len(name) <= 2


def _case_message(name: str, cases, template):
    spellings = cases.get(name.lower(), [])
    if spellings and name not in spellings:
        return template.format(name=name, lower=", ".join(spellings))
    return None


def identifier_messages(text: str, question_variables, author_names) -> list[str]:
    """STACK's errors for the identifiers of an answer (998_security), in its
    order: the functions' (In, case), then the variables' (forbidden,
    three letters or more, case). `question_variables` are STACK's forbidden
    keys; `author_names` (question and feedback variables, S-01) are
    forbidden here as a whole too, where STACK lets a name through part by
    part or does not forbid it (a feedback variable)."""
    try:
        tokens = [(m.lastgroup, m.group(m.lastgroup)) for m in _LEX.finditer(text)]
    except (TypeError, ValueError):
        return []
    functions, variables = [], []
    for index, (kind, value) in enumerate(tokens):
        if kind != "name" or value in LOGIC_OPERATORS or value in {"true", "false"}:
            continue
        call = index + 1 < len(tokens) and tokens[index + 1][1] == "("
        target = functions if call else variables
        if value not in target:
            target.append(value)
    keys = frozenset(question_variables)
    messages = []
    for name in functions:
        if name == "In":
            messages.append(BAD_LOG_IN)
            continue
        message = _case_message(name, _FUNCTION_CASES, FUNCTION_CASE)
        if message:
            messages.append(message)
    for name in variables:
        before = len(messages)
        if name in stack_data.GLOBALLY_FORBIDDEN:
            messages.append(FORBIDDEN_WORD.format(name=name))
            continue
        parts = [name] if _readable(name, keys) else list(dict.fromkeys(name.split("_")))
        for part in parts:
            if not (_readable(part, keys) or (part != name and _callable(part, keys))):
                messages.append(_case_message(part, _VARIABLE_CASES, VARIABLE_CASE) or FORBIDDEN_VARIABLE.format(name=part))
            elif len(part) > 1:
                message = _case_message(part, _VARIABLE_CASES, VARIABLE_CASE)
                if message:
                    messages.append(message)
        if name in author_names and len(messages) == before:
            # S-01: STACK forbids the question variables only as a whole and
            # lets a_b through when its parts are allowed; here every
            # question and feedback variable is forbidden.
            messages.append(FORBIDDEN_VARIABLE.format(name=name))
    return messages
