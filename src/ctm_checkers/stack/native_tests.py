"""Verify named native observations for one explicitly identified candidate.

This endpoint resolves no mathematics. The caller supplies current declarations
and candidate identity; observations from another seed/edit/order fail closed.
"""
import math
import re
from ..testing import run_declarative


def _identity(value):
    return (isinstance(value,dict) and set(value)=={'id','hash'}
        and isinstance(value['id'],str) and re.fullmatch(r'seed=[1-9][0-9]*',value['id'])
        and isinstance(value['hash'],str) and re.fullmatch(r'[a-f0-9]{16}',value['hash']))


def _verdict(value, *, field=False):
    if not isinstance(value,dict) or value.get('status') not in {'correct','wrong','partial','invalid'}:
        raise ValueError('Native test result has an invalid status')
    score=value.get('score',0 if field and value['status']=='invalid' else None)
    if type(score) not in (int,float) or not math.isfinite(score) or not 0<=score<=1:
        raise ValueError('Native test result needs a finite numeric score in [0,1]')
    status=value['status']
    if (status=='correct' and score<1-1e-9 or status=='wrong' and score>1e-9
        or status=='partial' and not 0<score<1 or status=='invalid' and score!=0):
        raise ValueError('Native test result status differs from its score')


def run(request):
    tests,results,fields,identity=(request.get(k) for k in ('tests','results','fields','candidate'))
    if (not _identity(identity) or not isinstance(tests,list) or not tests or len(tests)>100
        or not isinstance(results,list) or len(results)!=len(tests)
        or not isinstance(fields,list) or any(not isinstance(name,str) for name in fields)
        or len(fields)!=len(set(fields))):
        raise ValueError('Native authored tests need a candidate identity, matching bounded cases/results and unique fields')
    names=[case.get('name') if isinstance(case,dict) else None for case in tests]
    if any(not isinstance(name,str) or not name for name in names) or len(set(names))!=len(names):
        raise ValueError('Native authored tests require unique nonempty names')
    for name,actual in zip(names,results):
        if not isinstance(actual,dict) or actual.get('name')!=name or actual.get('candidate')!=identity:
            raise ValueError('Native test name/order or candidate identity differs from the current request')
        _verdict(actual)
        details=actual.get('fields',{})
        if not isinstance(details,dict) or set(details)-set(fields):raise ValueError('Native test result has unknown fields')
        for detail in details.values():_verdict(detail,field=True)
    index=0
    def grade(payload):
        nonlocal index
        if 'answers' not in payload:raise ValueError('STACK tests use answers keyed by input name')
        actual=results[index];index+=1
        return actual
    outcomes=run_declarative(tests,grade,fields=fields,resolve=lambda value:value)
    return {'passed':True,'candidate':dict(identity),'results':[dict(row,candidate=dict(identity)) for row in outcomes]}
