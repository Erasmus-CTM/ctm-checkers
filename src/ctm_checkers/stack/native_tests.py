"""Check declared expectations against results supplied by a native backend.

This adapter never resolves or grades mathematics. The native runner has
already computed test inputs and called its real grader.
"""
from ..testing import run_declarative


def run(request):
    tests=request.get('tests')
    results=request.get('results')
    fields=request.get('fields')
    if (not isinstance(tests,list) or not tests or len(tests)>100
        or not isinstance(results,list) or len(results)!=len(tests)
        or not isinstance(fields,list) or any(not isinstance(name,str) for name in fields)
        or len(fields)!=len(set(fields))):
        raise ValueError('Native authored tests need matching bounded cases/results and unique field names')
    index=0
    def grade(payload):
        nonlocal index
        if 'answers' not in payload:raise ValueError('STACK tests use answers keyed by input name')
        actual=results[index];index+=1
        if not isinstance(actual,dict):raise ValueError('Native test result must be a mapping')
        return actual
    outcomes=run_declarative(tests,grade,fields=fields,resolve=lambda value:value)
    return {'passed':True,'results':outcomes}
