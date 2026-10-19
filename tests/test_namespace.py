"""The `#| checker:` namespace (design §2.3; frozen by the golden probe
math_exercise/namespace) and the page's JSON text of the response."""
import json
import math

import sympy

from ctm_checkers.math_exercise import custom

# JSON.stringify's output for values JSON.parse gave it (Node 22): numbers in
# JavaScript's spelling, escapes, non-ASCII, lone surrogates.
JAVASCRIPT = [
    '0.5',
    '-0.5',
    '1.5',
    '0.1',
    '0.30000000000000004',
    '0.3333333333333333',
    '-0.6666666666666666',
    '1e-7',
    '1.5e-7',
    '0.000025',
    '0.000001',
    '0.000001234',
    '123.456',
    '1e+21',
    '1.5e+21',
    '100000000000000000000',
    '123456789012345680000',
    '1.7976931348623157e+308',
    '5e-324',
    '-1e-7',
    '12345000000000',
    '0.001',
    '999999999999999900000',
    '1e-300',
    '0.00003',
    '4.35',
    '1e-7',
    '"plain"',
    '"é ü 漢字 😀"',
    '"quote \\" back \\\\ slash"',
    '"ctrl \\u0001 \\u001f \\b \\f \\n \\r \\t"',
    '"\u2028\u2029"',
    '"\\ud800 lone"',
    '"end \\udfff"',
    '"<script>&"',
]


def test_page_json_is_what_json_stringify_writes():
    for text in JAVASCRIPT:
        assert custom.page_json(json.loads(text)) == text
    response = {'kind': 'expressions', 'raw': ['x + y', 'ä'], 'inputs': {'M': {'type': 'matrix', 'rows': 1, 'cols': 1, 'raw': ['2']}},
                'points': [[0.5, -1e-07], [1e21, 3]]}
    assert custom.page_json(response) == ('{"kind":"expressions","raw":["x + y","ä"],"inputs":{"M":{"type":"matrix","rows":1,'
                                         '"cols":1,"raw":["2"]}},"points":[[0.5,-1e-7],[1e+21,3]]}')


def test_names_and_request_values():
    scope = custom.namespace({'vars': 'x y', 'checker': 'pass', 'response': {'raw': ['1']}})
    assert scope['floor'] is math.floor and scope['gcd'] is math.gcd and scope['log10'] is math.log10
    assert scope['Matrix'] is sympy.Matrix and scope['simplify'] is sympy.simplify
    assert scope['_math_vars'] == 'x y' and scope['_math_checker'] == 'pass' and scope['_math_response_json'] == '{"raw":["1"]}'
    assert sorted(scope['_build_locals']()) == ['inf', 'x', 'y']
    assert scope['__name__'] == '_ctm_math_exercise'
    assert {'assess_basis', 'graph_from_response', 'parse_expr', 'standard_transformations',
            'implicit_multiplication_application', 'convert_xor'} <= set(scope)


def test_each_call_gets_a_fresh_namespace():
    first = custom.namespace({'vars': 'x'})
    exec('Matrix = None\nsymbols = None\nresult = 1', first)
    second = custom.namespace({'vars': 'y'})
    assert second['Matrix'] is sympy.Matrix and second['symbols'] is sympy.symbols and 'result' not in second
    assert 'check' not in custom.namespace()


def test_a_checker_sees_the_request():
    result = custom.check_custom({'vars': 'a, b', 'checker': 'def check(response, symbols):\n'
                                  '    return {"score": 1, "feedback": _math_vars + "|" + _math_response_json + "|" + ",".join(sorted(symbols))}\n',
                                  'response': {'kind': 'expressions', 'raw': ['a*b'], 'inputs': {}}})
    assert result['feedback'] == 'a, b|{"kind":"expressions","raw":["a*b"],"inputs":{}}|a,b'


def test_the_request_is_not_changed():
    request = {'vars': 'x', 'checker': 'def check(response, symbols):\n    response["raw"].append("y")\n    return True\n',
               'response': {'kind': 'expressions', 'raw': ['x'], 'inputs': {}}}
    custom.check_custom(request)
    assert request['response'] == {'kind': 'expressions', 'raw': ['x'], 'inputs': {}}
