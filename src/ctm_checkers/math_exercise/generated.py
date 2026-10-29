"""Admitted mathematics for generated problems. No Python source is evaluated.

The AST interpreter intentionally has a smaller vocabulary than authored SymPy.
It is also used before the legacy checker parses model-derived answer strings.
"""
import ast
import math
import io
import tokenize
import re

import sympy as sp

from .parsing import split_top

_FUNCTIONS = {name: getattr(sp, name) for name in (
    'sin cos tan cot sec csc asin acos atan acot asec acsc atan2 sinh cosh tanh asinh acosh atanh '
    'exp log sqrt Abs sign floor ceiling factorial binomial gamma erf '
    'conjugate re im Min Max Eq Rational Matrix').split()}
_CONSTANTS = {'pi': sp.pi, 'E': sp.E, 'I': sp.I, 'oo': sp.oo, 'inf': sp.oo}
_MODES = {'equivalent', 'exact', 'numeric', 'string', 'string_ci', 'set'}


def symbols(text=''):
    if not isinstance(text, str) or len(text) > 256:
        raise ValueError('Invalid generated variables')
    names = text.replace(',', ' ').split()
    if len(names) > 16 or len(names) != len(set(names)):
        raise ValueError('Invalid generated variables')
    for name in names:
        if not re.fullmatch(r'[A-Za-z][A-Za-z0-9_]{0,31}', name) or '__' in name or name in _FUNCTIONS or name in _CONSTANTS:
            raise ValueError('Invalid generated variable name')
    return {name: sp.Symbol(name) for name in names}


def parse_math(text, variables=''):
    """Interpret a bounded expression using only explicitly admitted operations."""
    if not isinstance(text, str) or not text.strip() or len(text) > 4096 or '__' in text:
        raise ValueError('Unsupported generated mathematics')
    local = symbols(variables)
    try:
        tree = ast.parse(text.replace('^', '**').strip(), mode='eval')
    except (SyntaxError, RecursionError) as error:
        raise ValueError('Unsupported generated mathematics') from error
    if sum(1 for _ in ast.walk(tree)) > 512:
        raise ValueError('Generated expression is too large')

    def visit(node, depth=0):
        if depth > 32:
            raise ValueError('Generated expression is too deep')
        child = lambda value: visit(value, depth + 1)
        if isinstance(node, ast.Constant):
            if type(node.value) is int and node.value.bit_length() <= 512:
                return sp.Integer(node.value)
            if type(node.value) is float and math.isfinite(node.value):
                return sp.Rational(str(node.value))
        elif isinstance(node, ast.Name):
            if node.id in local: return local[node.id]
            if node.id in _CONSTANTS: return _CONSTANTS[node.id]
        elif isinstance(node, (ast.List, ast.Tuple)) and len(node.elts) <= 64:
            return [child(value) for value in node.elts]
        elif isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.UAdd, ast.USub)):
            value = child(node.operand)
            return value if isinstance(node.op, ast.UAdd) else -value
        elif isinstance(node, ast.BinOp) and isinstance(node.op, (ast.Add, ast.Sub, ast.Mult, ast.Div, ast.Pow)):
            left, right = child(node.left), child(node.right)
            if isinstance(left, list) or isinstance(right, list):
                raise ValueError('Use Matrix for matrix arithmetic')
            if isinstance(node.op, ast.Pow):
                if not right.is_number or abs(right) > 100:
                    raise ValueError('Generated exponent is out of bounds')
                return left ** right
            if isinstance(node.op, ast.Add): return left + right
            if isinstance(node.op, ast.Sub): return left - right
            if isinstance(node.op, ast.Mult): return left * right
            return left / right
        elif isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in _FUNCTIONS and not node.keywords and len(node.args) <= 16:
            values = [child(value) for value in node.args]
            name = node.func.id
            if name == 'Matrix':
                if len(values) != 1 or not isinstance(values[0], list):
                    raise ValueError('Matrix requires a list')
                value = sp.Matrix(values[0])
                if value.rows > 12 or value.cols > 12:
                    raise ValueError('Generated matrix is too large')
                return value
            if any(isinstance(value, (list, sp.MatrixBase)) for value in values):
                raise ValueError('Scalar function requires scalar arguments')
            if name in ('factorial', 'binomial') and any(not v.is_Integer or not 0 <= v <= 100 for v in values):
                raise ValueError('Combinatorial argument is out of bounds')
            return _FUNCTIONS[name](*values)
        raise ValueError('Unsupported generated syntax or mathematical name')

    try:
        return visit(tree.body)
    except (TypeError, AttributeError, ZeroDivisionError, OverflowError) as error:
        raise ValueError('Invalid generated mathematics') from error


def admit_learner(text, variables=''):
    """Admit learner notation, then let the original checker transformations parse it.

    This token inspection never evaluates text. Model keys/recipes use parse_math.
    """
    if not isinstance(text, str) or not text.strip() or len(text) > 4096 or '__' in text:
        raise ValueError('Unsupported learner mathematics')
    local = symbols(variables)
    names = set(local) | set(_FUNCTIONS) | set(_CONSTANTS)
    names |= {name for name in dir(sp) if isinstance(getattr(sp, name), sp.FunctionClass)}
    try:
        tokens = list(tokenize.generate_tokens(io.StringIO(text).readline))
    except (tokenize.TokenError, IndentationError) as error:
        raise ValueError('Unsupported learner mathematics') from error
    if len(tokens) > 512: raise ValueError('Learner expression is too large')
    for token in tokens:
        if token.type == tokenize.NAME:
            if token.string not in names and not all(char in local for char in token.string):
                raise ValueError('Unsupported mathematical name')
        elif token.type == tokenize.OP:
            if token.string not in ('+', '-', '*', '/', '**', '^', '(', ')', '[', ']', ',', '!'):
                raise ValueError('Unsupported learner syntax')
        elif token.type == tokenize.ERRORTOKEN and token.string == '!':
            continue
        elif token.type not in (tokenize.NUMBER, tokenize.NL, tokenize.NEWLINE, tokenize.ENDMARKER):
            raise ValueError('Unsupported learner syntax')


def admit_generated_check(request):
    """Validate both sides before the existing checker uses parse_expr."""
    variables = request.get('vars', '')
    symbols(variables)
    mode = request.get('mode', 'equivalent')
    if mode not in _MODES:
        raise ValueError('Unsupported generated mode')
    for key in ('student', 'correct'):
        text = request.get(key, '')
        if not isinstance(text, str) or len(text) > 4096:
            raise ValueError('Invalid generated answer')
        if mode not in ('string', 'string_ci'):
            for part in split_top(text) if mode == 'set' else [text]:
                (admit_learner if key == 'student' and request.get('learner') is True else parse_math)(part, variables)
    # Saved options are data too: the legacy reject rule also parses mathematics.
    if mode not in ('string', 'string_ci') and request.get('reject'):
        parse_math(request['reject'], variables)
    return {'status': 'admitted'}


def admit_generated(request):
    """Admit a proposed answer or custom response before publication/checking."""
    if 'response' not in request:
        return admit_generated_check(request)
    symbols(request.get('vars', ''))
    response = request['response']
    if not isinstance(response, dict) or response.get('inputs'):
        raise ValueError('Generated custom responses require fixed expression fields')
    raw = response.get('raw')
    if not isinstance(raw, list) or not 1 <= len(raw) <= 64:
        raise ValueError('Invalid generated response fields')
    for text in raw:
        (admit_learner if request.get('learner') is True else parse_math)(text, request.get('vars', ''))
    return {'status': 'admitted'}


def bind_data(request):
    """Bind generated givens to the variables an authored checker declared.

    `names` are the variables the author opened to generation (math-exercise's
    `similar-data`); `data` maps each of them to model text. The text is
    interpreted by parse_math, never as Python source, and must keep the kind of
    the original value: an exact real number stays a number, an expression in
    the exercise's variables stays a non-constant expression. Matrix variables
    keep their own data contract. The original teacher answers belong to the
    original problem, so the bound context carries none. Returns the bound
    question context and the LaTeX of each bound value for the question text.
    """
    from ..variants import decode_context, question_context
    names, data = request.get('names'), request.get('data')
    if (type(names) is not list or not 1 <= len(names) <= 8 or len(set(names)) != len(names)
            or any(type(name) is not str for name in names)):
        raise ValueError('Invalid declared data names')
    if type(data) is not dict or set(data) != set(names):
        raise ValueError('Supply exactly the declared data: ' + ', '.join(names))
    variables = request.get('vars', '')
    local = set(symbols(variables).values())
    fields, values, _, _ = decode_context(request.get('context'))
    # Symbols in the original values keep their assumptions in the bound ones.
    originals = {symbol.name: symbol for value in values.values() if isinstance(value, sp.Basic)
                 for symbol in value.free_symbols}
    latex = {}
    for name in names:
        original = values.get(name)
        if not isinstance(original, sp.Expr):
            raise ValueError(name + ' is not a declared number or expression variable')
        text = data[name]
        if type(text) is not str:
            raise ValueError(name + ' must be mathematical text')
        value = parse_math(text, variables)
        if not isinstance(value, sp.Expr):
            raise ValueError(name + ' must be one number or expression')
        if original.free_symbols:
            if not value.free_symbols or not value.free_symbols <= local:
                raise ValueError(name + ' must be an expression in ' + (variables or 'the declared variables'))
        elif not (value.is_number and value.is_real is True and value.is_finite is True):
            raise ValueError(name + ' must be an exact real number')
        values[name] = value.xreplace({s: originals[s.name] for s in value.free_symbols if s.name in originals})
        latex[name] = sp.latex(values[name])
    return {'context': question_context(fields, values, {field: None for field in fields}), 'latex': latex}
