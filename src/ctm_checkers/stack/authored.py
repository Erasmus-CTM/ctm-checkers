"""STACK adapter for the shared declarative authored-test format (decision 19)."""
from ..testing import Raw, run_declarative
from .engine import _environment, _qtest_answer, _input_uses_written_form, grade


def run_tests(question, variant):
    fields = [item['name'] for item in question['inputs']]
    env = _environment(question, variant)
    # The author expression resolver is the CTM STACK author vocabulary, as
    # for XML qtests. Only raw('...') bypasses computation as student text.
    from ..testing import expression
    def resolve(source):
        if isinstance(source, Raw):
            return source
        if isinstance(source, str) and source.strip().startswith('raw('):
            result = expression(source)
            if not isinstance(result, Raw):
                raise ValueError('raw() needs one literal string')
            return result
        if isinstance(source, bool) or source is None:
            raise ValueError('STACK test answers require expressions or raw student strings')
        return _qtest_answer(question, str(source), env)
    def real_grade(payload):
        if 'answers' not in payload:
            raise ValueError('STACK tests use answers keyed by input name')
        result = grade(question, payload['answers'], variant=variant)
        score = result.get('score', 0)
        status = ('correct' if score >= 1-1e-9 else 'wrong' if score <= 1e-9 else 'partial') if result['status'] == 'graded' else result['status']
        # A named input's verdict follows its own direct response trees. Trees
        # involving several inputs and the implicit checker are overall tests.
        per_field = {}
        for name in fields:
            if not result['inputs'][name]['valid']:
                per_field[name] = {'status': 'invalid'}
                continue
            trees = [p for p in question['prts'] if all(n['student'] == name for n in p['nodes'])]
            weight = sum(p['value'] for p in trees)
            if weight and result['status'] == 'graded':
                field_score = sum(p['value']*result['prts'][p['name']]['score'] for p in trees)/weight
                per_field[name] = {'score':field_score,'status':'correct' if field_score >= 1-1e-9 else 'wrong' if field_score <= 1e-9 else 'partial'}
        notes = [p['note'] for p in result.get('prts',{}).values() if p.get('note')]
        return {'status':status,'score':score,'fields':per_field,'answer-note':' | '.join(notes)}
    return run_declarative(question['authored_tests'], real_grade, fields=fields, resolve=resolve)
