"""Fixed SymPy key recipes for AI-generated practice. Arguments are data."""
import sympy as sp

from .generated import parse_math, symbols, admit_generated_check
from .checks import check

_OPERATIONS = {
    'value': {'expr'}, 'simplify': {'expr'}, 'expand': {'expr'}, 'factor': {'expr'},
    'diff': {'expr', 'var', 'order'}, 'integrate': {'expr', 'var', 'lower', 'upper'},
    'limit': {'expr', 'var', 'point', 'direction'}, 'series': {'expr', 'var', 'point', 'order'},
    'solve': {'expr', 'var', 'variables'},
    'det': {'expr'}, 'inv': {'expr'}, 'transpose': {'expr'}, 'rank': {'expr'},
    'rref': {'expr'}, 'nullspace': {'expr'}, 'eigenvals': {'expr'},
    'matmul': {'left', 'right'}, 'dot': {'left', 'right'}, 'cross': {'left', 'right'},
    'norm': {'expr'},
}


def _tree(value):
    if isinstance(value, sp.MatrixBase):
        return [[value[r, c] for c in range(value.cols)] for r in range(value.rows)]
    if isinstance(value, dict): return {str(k): _tree(v) for k, v in value.items()}
    if isinstance(value, (tuple, list)): return [_tree(v) for v in value]
    return value


def compute_key(request):
    recipe = request.get('recipe')
    if not isinstance(recipe, dict): raise ValueError('A recipe is required')
    op = recipe.get('op')
    if op not in _OPERATIONS or set(recipe) - _OPERATIONS[op] - {'op', 'select'}:
        raise ValueError('Unknown operation or recipe argument')
    variables = request.get('vars', '')
    local = symbols(variables)
    def expr(key='expr'):
        if key not in recipe: raise ValueError('Missing recipe argument: ' + key)
        return parse_math(recipe[key], variables)
    def var():
        name = recipe.get('var')
        if name not in local: raise ValueError('Recipe variable must be declared')
        return local[name]
    def order(default):
        value = recipe.get('order', default)
        if type(value) is not int or not 1 <= value <= 12: raise ValueError('Invalid recipe order')
        return value
    if op in ('value', 'simplify', 'expand', 'factor'):
        value = expr()
        if op != 'value': value = getattr(sp, op)(value)
    elif op == 'diff': value = sp.diff(expr(), var(), order(1))
    elif op == 'integrate':
        if ('lower' in recipe) != ('upper' in recipe): raise ValueError('Integration requires both bounds')
        value = sp.integrate(expr(), (var(), expr('lower'), expr('upper')) if 'lower' in recipe else var())
    elif op == 'limit':
        direction = recipe.get('direction', '+')
        if direction not in ('+', '-', '+-'): raise ValueError('Invalid limit direction')
        value = sp.limit(expr(), var(), expr('point'), dir=direction)
    elif op == 'series': value = sp.series(expr(), var(), parse_math(recipe.get('point', '0'), variables), order(6)).removeO()
    elif op == 'solve':
        names = recipe.get('variables', [recipe.get('var')])
        if not isinstance(names, list) or not names or len(names) > 8 or any(name not in local for name in names) or len(set(names)) != len(names):
            raise ValueError('Solve requires declared variables')
        value = sp.solve(expr(), [local[name] for name in names], dict=True)
        value = sorted(value, key=lambda item: tuple(sp.default_sort_key(item.get(local[name], local[name])) for name in names))
    elif op in ('matmul', 'dot', 'cross'):
        left, right = expr('left'), expr('right')
        if not isinstance(left, sp.MatrixBase) or not isinstance(right, sp.MatrixBase): raise ValueError('Expected matrices')
        value = left * right if op == 'matmul' else getattr(left, op)(right)
    else:
        matrix = expr()
        if not isinstance(matrix, sp.MatrixBase): raise ValueError('Expected a matrix')
        if op == 'rref':
            reduced, pivots = matrix.rref(); value = {'matrix': reduced, 'pivots': list(pivots)}
        elif op == 'eigenvals':
            value = [{'value': val, 'multiplicity': count} for val, count in sorted(matrix.eigenvals().items(), key=lambda item: sp.default_sort_key(item[0]))]
        else: value = getattr(matrix, {'inv': 'inv', 'det': 'det', 'transpose': 'transpose', 'rank': 'rank', 'nullspace': 'nullspace', 'norm': 'norm'}[op])()
    value = _tree(value)
    selection = recipe.get('select', [])
    if not isinstance(selection, list) or len(selection) > 8: raise ValueError('Invalid component selector')
    for component in selection:
        if isinstance(value, list) and type(component) is int and 0 <= component < len(value): value = value[component]
        elif isinstance(value, dict) and isinstance(component, str) and component in value: value = value[component]
        else: raise ValueError('Missing or invalid result component')
    if isinstance(value, list) and request.get('mode') == 'set' and all(not isinstance(v, (list, dict)) for v in value):
        key = ', '.join(str(v) for v in value)
    elif isinstance(value, (list, dict)):
        raise ValueError('Select a scalar component for this answer field')
    else: key = str(value)
    admitted = dict(student=request.get('answer'), correct=key, vars=variables, mode=request.get('mode', 'equivalent'))
    admit_generated_check(admitted)
    # A numeric field compares the model's answer with the computed key under
    # the field's own precision (tolerance, decimal places or significant
    # figures), as it compares a student's answer.
    precision = {}
    if admitted['mode'] == 'numeric':
        for name in ('tolerance', 'decplaces', 'sigfigs'):
            value = request.get(name, '')
            if not isinstance(value, str) or len(value) > 64:
                raise ValueError('Invalid numeric precision: ' + name)
            precision[name] = value
    checked = check({**dict(reject='', tolerance='', decplaces='', sigfigs='', form='', partial_credit=False, form_credit=0.5), **precision, **admitted, 'generated': True})
    if checked.get('status') != 'correct': raise ValueError('Computed key disagrees with model answer')
    return {'key': key, 'computed': True}
