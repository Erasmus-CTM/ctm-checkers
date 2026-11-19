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


# A-01 (M3 of the 26 Oct review): SymPy's parse_expr evaluates the text as
# Python, in a namespace with Python's builtins and `from sympy import *`.
# Rejecting "__" alone left eval, exec, getattr, open, string literals and
# attribute access (SymPy objects reach the interpreter through them). Each
# learner string is now tokenized (never evaluated) and admitted only with:
# numbers; names that are mathematics (the exercise's variables, SymPy's
# functions, classes and constants, a few builtins) or that the namespace does
# not define (parse_expr makes them symbols, as before); and the operators of
# mathematical notation. Strings, attribute access, assignment, lambda,
# comprehensions and conditional expressions, and the namespace's other names
# (builtins, sympify, lambdify, preview, var, ...) are refused with the old
# message.
_OPERATORS = frozenset(('+', '-', '*', '/', '**', '^', '(', ')', '[', ']', '{', '}', ',', '!', '%',
                        '<', '>', '<=', '>=', '==', '!=', '&', '|', '~', '//'))
_BUILTINS_ALLOWED = frozenset(('abs', 'min', 'max', 'pow', 'round', 'sum', 'divmod'))
_SYMPY_HELPERS_ALLOWED = frozenset((
    'diff', 'integrate', 'limit', 'series', 'summation', 'product', 'simplify', 'expand', 'factor',
    'cancel', 'apart', 'together', 'trigsimp', 'expand_trig', 'powsimp', 'radsimp', 'nsimplify',
    'solve', 'sqrt', 'root', 'cbrt', 'real_root', 'Rational', 'Matrix', 'Integer', 'Float', 'S', 'N',
    'binomial', 'factorial', 'gcd', 'lcm', 'floor', 'ceiling', 'Abs', 're', 'im', 'arg', 'conjugate',
    'Min', 'Max', 'Eq', 'Ne', 'Lt', 'Le', 'Gt', 'Ge', 'Interval', 'FiniteSet', 'Union', 'Intersection',
    'Complement', 'oo', 'zoo', 'nan', 'pi', 'E', 'I', 'EulerGamma', 'GoldenRatio', 'Sum', 'Product',
    'Integral', 'Derivative', 'Limit', 'det', 'trace', 'transpose', 'eye', 'zeros', 'ones', 'diag',
    'log', 'ln', 'exp', 'sign', 'Piecewise', 'Mod', 'Pow', 'Mul', 'Add', 'true', 'false'))
# Keywords that build an expression in parse_expr's eval. The others (def,
# import, while, ...) are statements, a syntax error there: nothing runs and
# the learner sees parse_expr's message, as before.
_EXPRESSION_KEYWORDS = frozenset(('lambda', 'for', 'if', 'else', 'await', 'yield', 'async'))
_NAMESPACE = None


def _namespace_names():
    """The names parse_expr's evaluation can reach: Python's builtins and
    `from sympy import *` (what parse_expr executes into its global dict)."""
    global _NAMESPACE
    if _NAMESPACE is None:
        import builtins
        namespace = {}
        exec('from sympy import *', namespace)  # SymPy's own namespace; no learner text
        names = set(namespace) | set(dir(builtins))
        _NAMESPACE = frozenset(names)
    return _NAMESPACE


def _mathematical(name):
    import sympy as sp
    if name in _SYMPY_HELPERS_ALLOWED or name in _BUILTINS_ALLOWED:
        return True
    value = getattr(sp, name, None)
    if value is None or name.startswith('_'):
        return False
    if isinstance(value, sp.FunctionClass) or isinstance(value, sp.Basic):
        return True
    return isinstance(value, type) and issubclass(value, sp.Basic)


def admit_text(text, variables=''):
    """Admits one learner string (see above); raises ValueError otherwise."""
    import io
    import tokenize
    text = str(text)
    if '__' in text or len(text) > 4096:
        raise ValueError("SyntaxError: unsupported input")
    declared = set(variables.replace(',', ' ').split()) if isinstance(variables, str) else set()
    try:
        tokens = list(tokenize.generate_tokens(io.StringIO(text).readline))
    except (tokenize.TokenError, IndentationError, SyntaxError):
        return  # parse_expr reports the syntax error, as before; nothing ran
    if len(tokens) > 2048:
        raise ValueError("SyntaxError: unsupported input")
    namespace = _namespace_names()
    for token in tokens:
        kind, value = token.type, token.string
        if kind == tokenize.NAME:
            if value in declared:
                continue
            if value in _EXPRESSION_KEYWORDS or (value in namespace and not _mathematical(value)):
                raise ValueError("SyntaxError: unsupported input")
        elif kind == tokenize.OP:
            if value not in _OPERATORS:
                raise ValueError("SyntaxError: unsupported input")
        elif kind == tokenize.ERRORTOKEN:
            # A character Python cannot tokenize (a typed "!" before 3.12, "²",
            # "√"): parse_expr fails on it, so nothing runs; a quote opens a string.
            if value in ("'", '"'):
                raise ValueError("SyntaxError: unsupported input")
        elif kind not in (tokenize.NUMBER, tokenize.NL, tokenize.NEWLINE, tokenize.ENDMARKER,
                          tokenize.INDENT, tokenize.DEDENT):
            # STRING, f-string parts, COMMENT and anything newer.
            raise ValueError("SyntaxError: unsupported input")


def admit(request):
    # Learner answers are parsed by SymPy, which evaluates Python: each must
    # pass admit_text. Author data (variants, keys, checkers) is not restricted.
    variables = request.get("vars", "") if isinstance(request.get("vars", ""), str) else ""
    for text in learner_strings(request):
        admit_text(text, variables)
