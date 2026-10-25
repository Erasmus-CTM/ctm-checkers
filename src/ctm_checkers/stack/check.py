"""One Python checker contract for STACK backends (H1).

Backends validate learner input first and pass written CTM STACK expressions,
never Python objects or executable learner code. Trusted checker source uses
the same runner, namespace and score normalizer as math-exercise.
"""
from __future__ import annotations

import ast
from contextlib import redirect_stdout, redirect_stderr
import json
import inspect

import sympy as sp

from ..core.custom import execute_checker
from ..core.result import normalize_result
from ..core.namespace import namespace
from .expressions import Unsupported, MatrixValue, HeldList, evaluate, parse

MAX_SOURCE_BYTES = 65536
LIBRARY_CHECKERS = ('basis', 'matrix_property', 'is_hermitian',
                    'is_positive_definite', 'is_hpd')


class CheckerError(Unsupported):
    """Author configuration/execution error, never a learner wrong answer."""


class _Discard:
    def write(self, text):
        return len(text)

    def flush(self):
        pass


def validate_source(source):
    if not isinstance(source, str) or not 0 < len(source.encode('utf-8')) <= MAX_SOURCE_BYTES:
        raise CheckerError('checker: requires 1–65536 UTF-8 bytes')
    try:
        tree = ast.parse(source, filename='<STACK checker>')
    except SyntaxError as error:
        raise CheckerError('Invalid checker: ' + str(error)) from error
    if not any(isinstance(node, ast.FunctionDef) and node.name == 'check' for node in tree.body):
        raise CheckerError('checker: must define check(response, symbols)')
    return tree


def checker_spec(spec):
    try:
        config = json.loads(spec, parse_constant=lambda value: (_ for _ in ()).throw(ValueError(value)))
    except (TypeError, ValueError) as error:
        raise CheckerError('PythonChecker testoptions must be a JSON object') from error
    if (type(config) is not dict or 'checker' not in config
            or set(config) - {'checker', 'options'} or type(config.get('options', {})) is not dict):
        raise CheckerError('PythonChecker requires checker and optional options')
    name = config['checker']
    if name != 'check' and name not in LIBRARY_CHECKERS:
        raise CheckerError('Unknown PythonChecker: ' + repr(name))
    return name, config.get('options', {})


def value(source, assumptions=None):
    """Decode trusted CTM STACK author vocabulary; never sympify text."""
    if not isinstance(source, str):
        raise CheckerError('STACK checker values must be written strings')
    def convert(item):
        if isinstance(item, MatrixValue):
            return sp.ImmutableMatrix([[convert(x) for x in row.args] for row in item.args])
        if isinstance(item, (HeldList, list)):
            return [convert(x) for x in (item.args if isinstance(item, HeldList) else item)]
        # Held sets/relations keep their CTM structure, including repetitions.
        return item
    return convert(evaluate(parse(source), assumptions=assumptions))


def _referenced(source, names):
    tree = validate_source(source)
    used = {node.value for node in ast.walk(tree) if isinstance(node, ast.Constant) and isinstance(node.value, str)}
    used.update(node.id for node in ast.walk(tree) if isinstance(node, ast.Name))
    # Dynamic indexing/iteration can use every variable. Require all values to
    # decode in that case rather than passing silently undecodable objects.
    for node in ast.walk(tree):
        if isinstance(node, ast.Subscript) and isinstance(node.value, ast.Subscript):
            inner = node.value.slice
            if isinstance(inner, ast.Constant) and inner.value == 'variables' and not isinstance(node.slice, ast.Constant):
                return set(names)
    return set(names) & used


def context(request):
    source = request['checker']
    assumptions = request.get('assumptions', {})
    required = _referenced(source, request.get('variables', {}))
    variables = {}
    for name, text in request.get('variables', {}).items():
        try:
            variables[name] = value(text, assumptions)
        except Exception as error:
            if name in required:
                raise CheckerError('Cannot decode checker variable ' + name + ': ' + str(error)) from error
            variables[name] = text
    teacher = {name: value(text, assumptions) for name, text in request['teacher'].items()}
    return variables, teacher


def _normalize(result):
    if inspect.isawaitable(result) or inspect.isgenerator(result) or inspect.isasyncgen(result):
        if inspect.iscoroutine(result) or inspect.isgenerator(result):
            result.close()
        raise CheckerError('Checker must return a synchronous result')
    if isinstance(result, dict) and 'valid' in result:
        if type(result['valid']) is not bool:
            raise CheckerError('Checker valid must be a Python bool')
        if not result['valid']:
            if result.get('correct') or result.get('score', 0):
                raise CheckerError('An invalid checker result cannot have a score')
            return {'valid': False, 'feedback': str(result.get('feedback', 'Invalid answer'))}
    return {'valid': True, **normalize_result(result)}


def _assessment(result, inputs):
    for name, axes in result.get('assessment', {}).items():
        inp = inputs.get(name)
        if not inp or inp.get('type') != 'matrix' or type(axes) is not dict or not axes or set(axes) - {'rows', 'columns'}:
            raise CheckerError('Checker assessment requires a named matrix input')
        for axis, statuses in axes.items():
            if (type(statuses) is not list or len(statuses) != inp['rows' if axis == 'rows' else 'cols']
                    or any(status not in ('correct', 'incorrect', 'dependent') for status in statuses)):
                raise CheckerError('Checker assessment must match the submitted matrix dimensions')


def check(request):
    """Text-only backend entry; author exceptions propagate as CheckerError."""
    try:
        variables, teacher = context(request)
        inputs, answers, raw = {}, {}, []
        assumptions = request.get('assumptions', {})
        for name, inp in request['inputs'].items():
            answer = value(inp['canonical'], assumptions)
            answers[name] = answer
            raw.append(inp['raw'])
            item = dict(inp)
            if inp['type'] == 'matrix':
                if not isinstance(answer, sp.MatrixBase):
                    raise CheckerError('Validated matrix input did not decode as a matrix')
                item.update(rows=answer.rows, cols=answer.cols,
                            expressions=list(answer), matrix=answer)
            inputs[name] = item
        response = dict(kind='expressions', raw=raw, expressions=list(answers.values()),
                        answers=answers, inputs=inputs, variables=variables, teacher=teacher,
                        variant=dict(request.get('variant', {})))
        node = request.get('node')
        if node is not None:
            response['node'] = dict(sans=value(node['sans'], assumptions),
                                    tans=value(node['tans'], assumptions), options=node.get('options', {}))
        symbols = {}
        def collect(item):
            if isinstance(item, dict):
                for child in item.values():
                    collect(child)
            elif isinstance(item, (list, tuple)):
                for child in item:
                    collect(child)
            else:
                for symbol in getattr(item, 'free_symbols', ()):
                    previous = symbols.get(symbol.name)
                    if previous is not None and previous != symbol:
                        raise CheckerError('Conflicting checker symbol assumptions: ' + symbol.name)
                    symbols[symbol.name] = symbol
        collect([answers, teacher, variables])
        with redirect_stdout(_Discard()), redirect_stderr(_Discard()):
            result = execute_checker(request['checker'], response, symbols, namespace(), normalize=_normalize)
        _assessment(result, inputs)
        return result
    except CheckerError:
        raise
    except (Exception, SystemExit) as error:
        raise CheckerError('STACK checker failed (' + type(error).__name__ + '): ' + str(error)) from error


def wire_request(question, variant, answers, *, node=None):
    """SymPy adapter: canonical comes from the engine's written AST form."""
    from .engine import _assumptions, _environment, _source
    from .student_input import student_text
    env = _environment(question, variant)
    assumptions = _assumptions(question)
    # The engine admits text first. Re-print that parsed tree without algebraic
    # simplification: identity factors, decimals and input order remain visible.
    from .expressions import written_text
    inputs = {inp['name']: {'type': inp['type'], 'raw': answers.get(inp['name'], ''),
              'canonical': written_text(parse(student_text(answers.get(inp['name'], '')), insertstars=inp['insertstars']))}
              for inp in question['inputs']}
    return dict(checker=question.get('checker', ''), inputs=inputs,
        teacher={inp['name']: _source(evaluate(inp['teacher'], env, assumptions=assumptions)) for inp in question['inputs']},
        variables={name: _source(item) for name, item in env.items()},
        assumptions=assumptions, backend='sympy', node=node,
        variant={'n': variant.get('n'), 'id': variant.get('id', 'seed=' + str(variant['seed'])), 'hash': variant.get('hash')})


def invoke_node(question, variant, answers, node, env):
    from .engine import _source, evaluate, _assumptions
    name, options = checker_spec(node['options'])
    if name == 'check':
        request = wire_request(question, variant, answers,
            node={'sans': _source(evaluate(node['student'], env, assumptions=_assumptions(question))),
                  'tans': _source(evaluate(node['teacher'], env, assumptions=_assumptions(question))), 'options': options})
        result = check(request)
        return dict(result, correct=result.get('status') == 'correct', note='', implementation='python-checker-h1')
    student = value(_source(evaluate(node['student'], env, assumptions=_assumptions(question))), _assumptions(question))
    teacher = value(_source(evaluate(node['teacher'], env, assumptions=_assumptions(question))), _assumptions(question))
    result = library_test(node['options'], student, teacher)
    assessment = result.get('assessment', {})
    if assessment:
        result['assessment'] = {node['student']: assessment}
    return result


def library_test(spec, student, teacher):
    """Library predicate leaf; custom blocks need the complete engine context."""
    from .. import matrix
    name, options = checker_spec(spec)
    if name == 'check':
        raise CheckerError('PythonChecker check requires a block checker and the STACK grade context')
    def convert(item):
        return sp.ImmutableMatrix([list(row.args) for row in item.args]) if isinstance(item, MatrixValue) else item
    student, teacher = convert(student), convert(teacher)
    try:
        result = _normalize(getattr(matrix, name)(student, teacher, options))
        return dict(result, correct=result.get('status') == 'correct', note='', implementation='python-checker-h1')
    except Exception as error:
        raise CheckerError('Library checker ' + name + ': ' + str(error)) from error


def preflight(question, variants):
    from .engine import _environment, _qtest_answer, _input_uses_written_form, grade
    from .importer import UnsupportedQuestion
    if not question.get('checker') and not any(n['test'] == 'PythonChecker' for p in question['prts'] for n in p['nodes']):
        return
    for variant in variants:
        try:
            env = _environment(question, variant)
            if question.get('checker'):
                context(wire_request(question, variant,
                    {i['name']: _qtest_answer(question, i['teacher'], env, preserve_form=_input_uses_written_form(question, i['name'])) for i in question['inputs']}))
            answers = {i['name']: _qtest_answer(question, i['teacher'], env,
                preserve_form=_input_uses_written_form(question, i['name'])) for i in question['inputs']}
            result = grade(question, answers, variant=variant)
            if result['status'] != 'graded':
                raise CheckerError('Teacher answers must produce valid grading')
        except (CheckerError, ValueError) as error:
            raise UnsupportedQuestion(question['name'], 'checker/model', str(error)) from error
