"""Static production authoring guard; legacy engine evaluation is unchanged."""
from .expressions import assignment_statements, parse, InvalidAnswer, Unsupported
from .importer import UnsupportedQuestion


def name_collisions(question):
    """Find cross-scope declarations without evaluating author expressions.

    Question variables and inputs are page-question scopes. Each PRT has its
    own feedback-local scope; sibling PRT reuse and intentional writes within
    one scope remain valid. Only declaration names count, not free CAS symbols.
    """
    def assigned(source, scope):
        # Match assignments() before scanning declarations or parsing any RHS.
        if not isinstance(source, str) or len(source) > 20000:
            raise UnsupportedQuestion(question['name'], scope, 'Assignment source too long or not text')
        names = set()
        for number, (name, expression) in enumerate(assignment_statements(source), 1):
            where = scope + '/statement[' + str(number) + ']'
            if name is None:
                raise UnsupportedQuestion(question['name'], where, 'Only name:expression assignments are supported')
            try:
                parse(expression)  # The engine's bounded AST grammar; never execute it.
            except (InvalidAnswer, Unsupported) as error:
                raise UnsupportedQuestion(question['name'], where, str(error)) from error
            names.add(name)
        return names
    generator = assigned(question.get('variables', ''), 'questionvariables')
    inputs = {item['name'] for item in question['inputs']}
    found = []
    def overlaps(left, right, left_scope, right_scope):
        found.extend({'name': name, 'scopes': [left_scope, right_scope]} for name in sorted(left & right))
    overlaps(generator, inputs, 'questionvariables', 'student inputs')
    for prt in question['prts']:
        scope = 'prt[' + prt['name'] + ']/feedbackvariables'
        local = assigned(prt.get('feedbackvariables', ''), scope)
        overlaps(generator, local, 'questionvariables', scope)
        overlaps(inputs, local, 'student inputs', scope)
    return found


def preflight_names(question, *, source=None):
    """Reject ambiguous production declarations before any plan or HTML exists."""
    try:
        collisions = name_collisions(question)
    except UnsupportedQuestion as error:
        if source is None:
            raise
        raise UnsupportedQuestion(question['name'], 'authoring names', str(source) + ': ' + str(error)) from error
    if collisions:
        prefix = str(source) + ': ' if source is not None else ''
        detail = '; '.join(repr(item['name']) + ' is declared in both ' + ' and '.join(item['scopes'])
                           for item in collisions)
        raise UnsupportedQuestion(question['name'], 'authoring name collision', prefix + detail)
