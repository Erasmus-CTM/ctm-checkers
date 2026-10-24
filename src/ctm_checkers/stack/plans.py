"""Validate the types of a prepared author plan before processing learner data.

This is the JSON model produced by the XML importer and variant freezer, not
an admission rule for learner answers. Unknown fields remain additive.
"""
import math

from .importer import UnsupportedQuestion


def validate_plan(question, variant):
    name = question.get('name', 'STACK question') if isinstance(question, dict) else 'STACK question'
    if not isinstance(name, str):
        name = 'STACK question'

    def fail(location):
        raise UnsupportedQuestion(name, 'plan/' + location, 'Malformed prepared question plan')

    def require(condition, location):
        if not condition:
            fail(location)

    def number(value):
        try:
            return type(value) in (int, float) and math.isfinite(value)
        except OverflowError:
            return False

    def fields(value, schema, location):
        require(isinstance(value, dict), location)
        for key, kind in schema.items():
            require(key in value, location + '/' + key)
            require(number(value[key]) if kind == 'number' else type(value[key]) is kind,
                    location + '/' + key)

    fields(question, {'name': str, 'variables': str, 'inputs': list, 'prts': list,
                      'questiontext': str, 'generalfeedback': str, 'specificfeedback': str,
                      'questionnote': str, 'defaultgrade': 'number', 'penalty': 'number',
                      'simplify': bool, 'assumepositive': bool, 'assumereal': bool,
                      'qtests': list}, 'question')
    fields(variant, {'seed': int, 'env': dict, 'question_html': str,
                     'generalfeedback_html': str, 'specificfeedback_html': str,
                     'questionnote_html': str}, 'variant')
    require(all(type(key) is str and type(value) is str for key, value in variant['env'].items()), 'variant/env')
    require(bool(question['inputs']) and bool(question['prts']), 'question')
    for index, inp in enumerate(question['inputs']):
        where = 'input/' + str(index)
        fields(inp, {'name': str, 'type': str, 'teacher': str, 'boxsize': int,
                     'strictsyntax': bool, 'insertstars': int, 'forbidwords': list,
                     'forbidfloat': bool, 'requirelowestterms': bool,
                     'checkanswertype': bool, 'mustverify': bool,
                     'showvalidation': bool, 'syntaxhint': str}, where)
        require(inp['type'] in {'algebraic', 'numerical', 'matrix'}, where + '/type')
        require(inp['strictsyntax'] and inp['insertstars'] in {0, 1}, where + '/syntax')
        require(all(type(word) is str for word in inp['forbidwords']), where + '/forbidwords')
        if inp['type'] == 'matrix' and inp.get('matrix') is not None:
            fields(inp['matrix'], {'rows': dict, 'cols': dict}, where + '/matrix')
            for axis in ('rows', 'cols'):
                config = inp['matrix'][axis]
                fields(config, {'initial': int, 'min': int, 'max': int, 'auto': bool}, where + '/matrix/' + axis)
                require(1 <= config['min'] <= config['initial'] <= config['max'] <= 16,
                        where + '/matrix/' + axis)
    require(len({item['name'] for item in question['inputs']}) == len(question['inputs']), 'input/names')
    for index, prt in enumerate(question['prts']):
        where = 'prt/' + str(index)
        fields(prt, {'name': str, 'value': 'number', 'autosimplify': bool,
                     'feedbackvariables': str, 'nodes': list}, where)
        require(bool(prt['nodes']), where + '/nodes')
        for node in prt['nodes']:
            fields(node, {'name': str, 'test': str, 'student': str, 'teacher': str,
                          'options': str, 'quiet': bool, 'true': dict, 'false': dict}, where + '/node')
            for branch in ('true', 'false'):
                fields(node[branch], {'score': 'number', 'mode': str, 'next': int,
                                      'note': str, 'feedback': str}, where + '/node/' + branch)
                require(node[branch]['mode'] in {'=', '+', '-'}, where + '/node/' + branch + '/mode')
        ids = {node['name'] for node in prt['nodes']}
        require(len(ids) == len(prt['nodes']) and '0' in ids, where + '/node/names')
        edges = {node['name']: [str(node[b]['next']) for b in ('true', 'false')
                                if node[b]['next'] != -1] for node in prt['nodes']}
        require(all(dest in ids for targets in edges.values() for dest in targets), where + '/node/next')
        active, done = set(), set()
        def visit(key):
            require(key not in active, where + '/node/cycle')
            if key in done:
                return
            active.add(key)
            for dest in edges[key]:
                visit(dest)
            active.remove(key)
            done.add(key)
        visit('0')
        require(done == ids, where + '/node/unreachable')
    require(len({item['name'] for item in question['prts']}) == len(question['prts']), 'prt/names')
    for index, test in enumerate(question['qtests']):
        where = 'qtest/' + str(index)
        fields(test, {'testcase': str, 'description': str, 'inputs': dict, 'expected': dict}, where)
        require(all(type(k) is str and type(v) is str for k, v in test['inputs'].items()), where + '/inputs')
        for key, expected in test['expected'].items():
            require(type(key) is str, where + '/expected')
            fields(expected, {'score': 'number', 'penalty': 'number', 'note': str}, where + '/expected/' + key)
