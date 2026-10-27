"""Native component adapter for SymPy STACK; no Maxima seed emulation."""
import copy
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import signal
import sys
import time

from ctm_variants import history
from ctm_variants.model import VariantError, classify, digest
from ctm_variants.orchestration import _retain
from ctm_variants.producer import inside
from ctm_variants.review import apply_decisions


def _seed_child(question,seed,connection,identity=None):
    """A fresh fork inherits verified imports, never another checker's globals."""
    os.setsid()
    from ctm_checkers.stack.variants import seed_record,SeedRejected
    try:
        try:result={'record':seed_record(question,seed,identity=identity)}
        except SeedRejected as error:result={'rejected':str(error)}
        except Exception as error:result={'error':type(error).__name__+': '+str(error)}
        raw=json.dumps(result).encode()
        if len(raw)>16*1024*1024:raw=json.dumps({'error':'STACK candidate exceeds its output budget'}).encode()
        connection.send_bytes(raw)
    finally:connection.close()


def supervised_seed(question,seed,timeout=30,*,identity=None):
    """Bound the real engine per seed, including trusted custom checker code."""
    if os.name=='posix':
        # Keep the candidate process boundary without reimporting SymPy for
        # every seed. Each fork still receives a private namespace and deadline.
        import multiprocessing
        context=multiprocessing.get_context('fork')
        receiver,sender=context.Pipe(duplex=False)
        child=context.Process(target=_seed_child,args=(question,seed,sender,identity))
        child.start();sender.close()
        try:
            if not receiver.poll(timeout):raise VariantError(f'seed={seed}: STACK candidate exceeded its time budget')
            result=json.loads(receiver.recv_bytes(16*1024*1024))
            if 'error' in result:raise VariantError(f"seed={seed}: {result['error']}")
            if 'rejected' in result:
                from ctm_checkers.stack.variants import SeedRejected
                raise SeedRejected(result['rejected'])
            return result['record']
        finally:
            receiver.close()
            try:os.killpg(child.pid,signal.SIGKILL)
            except ProcessLookupError:pass
            if child.is_alive():child.kill()
            child.join(timeout=1)
    import tempfile
    code="import json,sys\np=json.load(sys.stdin); sys.path[:0]=p['paths']\nfrom ctm_checkers.stack.variants import seed_record,SeedRejected\ntry: result={'record':seed_record(p['question'],p['seed'],identity=p.get('identity'))}\nexcept SeedRejected as error: result={'rejected':str(error)}\nprint(json.dumps(result))"
    with tempfile.TemporaryFile() as out,tempfile.TemporaryFile() as err:
        child=subprocess.Popen([sys.executable,'-I','-c',code],stdin=subprocess.PIPE,stdout=out,stderr=err,
            start_new_session=os.name!='nt')
        try:child.communicate(json.dumps({'paths':sys.path,'question':question,'seed':seed,'identity':identity}).encode(),timeout=timeout)
        except subprocess.TimeoutExpired as error:
            if os.name!='nt':os.killpg(child.pid,signal.SIGKILL)
            else:subprocess.run(['taskkill','/F','/T','/PID',str(child.pid)],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,check=False)
            child.wait();raise VariantError(f'seed={seed}: STACK candidate exceeded its time budget') from error
        out.seek(0);err.seek(0);data=out.read(16*1024*1024+1);diagnostic=err.read(4096)
        if child.returncode:raise VariantError(diagnostic.decode(errors='replace').splitlines()[-1])
        if len(data)>16*1024*1024:raise VariantError('STACK candidate exceeds its output budget')
        result=json.loads(data)
        if 'rejected' in result:
            from ctm_checkers.stack.variants import SeedRejected
            raise SeedRejected(result['rejected'])
        return result['record']


def parse_source(source):
    options,active={},None
    for line in source.splitlines():
        match=re.fullmatch(r'#\| ?(.*)',line)
        if not match:
            if line.strip():raise VariantError('STACK blocks contain #| options only')
            continue
        body=match[1]
        key=re.fullmatch(r'([\w-]+):\s*(.*?)\s*',body)
        if key:
            active,value=key.groups()
            if active in options:raise VariantError('duplicate STACK option: '+active)
            options[active]=value
        elif active and body.startswith(' '):
            options[active]=('' if options[active] in ('|','') else options[active]+'\n')+body.removeprefix('  ')
        elif body.strip():raise VariantError('invalid STACK option')
    return options,''


def current_source(payload):
    root=Path(payload['projectRoot']).resolve()
    name=Path(payload.get('sourceFile',payload.get('file','')))
    if name.is_absolute():name=name.relative_to(root)
    file=inside(root,name.as_posix())
    if file.stat().st_size>1024*1024:raise VariantError('STACK source exceeds 1 MiB')
    parsed=subprocess.run([os.environ.get('CTM_VARIANTS_QUARTO','quarto'),'pandoc','--from','commonmark_x','--to','json'],
        input=file.read_text(),text=True,capture_output=True,timeout=15,check=True)
    found=[]
    def walk(node):
        if isinstance(node,dict):
            if node.get('t')=='CodeBlock':
                classes,raw=node['c'][0][1],node['c'][1]
                if any(name.strip('{}.')=='stack-question' for name in classes):
                    opts,question=parse_source(raw)
                    if opts.get('label')==payload['label']:found.append((raw.rstrip('\r\n'),opts,question))
            else:
                for value in node.values():walk(value)
        elif isinstance(node,list):
            for value in node:walk(value)
    walk(json.loads(parsed.stdout).get('blocks',[]))
    if len(found)!=1:raise VariantError('sourceFile must contain one current STACK block with this label')
    source,options,question=found[0]
    return dict(payload,file=name.as_posix(),sourceFile=name.as_posix(),source=source,options=options,question=question)


def request(payload, *, backend=None):
    if backend is not None:
        with backend:
            return _request(payload, backend=backend)
    return _request(payload)


def _bound_record(record, seed, backend_id, authored=None):
    """Every generated/replayed proof belongs to this backend and seed."""
    if not isinstance(record,dict):raise VariantError('STACK backend returned a non-record')
    grading=record.get('snapshot',{}).get('grading',{})
    data=record.get('data',{})
    if grading.get('backend')!=backend_id or data.get('backend')!=backend_id:
        raise VariantError(f'STACK candidate backend mismatch: expected {backend_id}')
    if type(seed) is not int or not 1<=seed<=2147483647 or record.get('id')!='seed='+str(seed) or data.get('plan',{}).get('seed')!=seed:
        raise VariantError(f'STACK candidate seed mismatch: expected seed={seed}')
    if authored:
        tests=record.get('tests')
        proof=tests.get('authored',{}) if isinstance(tests,dict) else {}
        if not isinstance(proof,dict):proof={}
        rows=proof.get('results',[])
        if (proof.get('passed') is not True or not isinstance(rows,list)
            or [row.get('name') for row in rows if isinstance(row,dict)]!=[case['name'] for case in authored]
            or any(not isinstance(row,dict) or row.get('passed') is not True for row in rows)):
            raise VariantError(f'{backend_id} backend omitted passing authored-test evidence for seed={seed}')
    return record


def _request(payload, *, backend=None):
    from ctm_checkers.stack.importer import import_xml
    if backend is None:
        from ctm_checkers.stack.variants import seed_record,propose,card_data
        run_seed=supervised_seed
        backend_id='sympy'
    else:
        seed_record,propose,card_data=backend.seed_record,backend.propose,backend.card_data
        run_seed=backend.seed_record
        backend_id=backend.id
    if type(payload) is not dict or payload.get('version')!=1:raise VariantError('invalid STACK request/version')
    if not isinstance(payload.get('source'),str):raise VariantError('STACK source is required')
    options,question_text=parse_source(payload['source'])
    if payload.get('options')!=options or payload.get('question')!=question_text:raise VariantError('STACK source differs from parsed options')
    label=options.get('label')
    if label!=payload.get('label') or not isinstance(label,str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]*',label) or '..' in label:
        raise VariantError('STACK variants need a unique safe #| label:')
    action=payload.get('action','resolve')
    if action not in ('resolve','resolve-more','generate','decide','decide-many'):raise VariantError('unknown STACK variants action')
    if action!='resolve':
        payload=current_source(payload);options=payload['options']
    if 'seed' in options:raise VariantError('STACK seed: was removed; generate and review variants instead')
    if options.get('cas',payload.get('backend','sympy'))!=backend_id:
        raise VariantError(f'STACK backend mismatch: requested {options.get("cas",payload.get("backend","sympy"))}, active {backend_id}')
    root=Path(payload['projectRoot']).resolve()
    source_file=Path(payload.get('sourceFile',payload.get('file','')))
    if source_file.is_absolute():source_file=source_file.relative_to(root)
    source_file=source_file.as_posix()
    payload=dict(payload,file=source_file,sourceFile=source_file)
    source_path=inside(root,source_file)
    source_bytes=source_path.read_bytes()
    xml=inside(root,os.path.normpath(str(Path(source_file).parent/options['file'])))
    xml_bytes=xml.read_bytes()
    if len(xml_bytes)>8*1024*1024:raise VariantError('STACK XML exceeds 8 MiB')
    if 'python-checkers' in options:
        raise VariantError('python-checkers: was removed; use checker: with check(response, symbols)')
    authored=None
    if 'tests' in options:
        from ctm_checkers.math_exercise.authored import _tests
        authored=_tests(options['tests'])
    if 'tests' in options and (not isinstance(authored, list) or not authored):
        raise VariantError('STACK tests: must be a nonempty declarative list')
    if 'checker-value' in options and not options.get('checker'):
        raise VariantError('checker-value requires checker:')
    if authored and backend is not None and not getattr(backend,'supports_authored_tests',False):
        raise VariantError(f'{backend_id} backend does not support authored tests:')
    questions=([backend.load_question(xml,options.get('question'),options,authored_tests=authored)] if backend is not None else
        [q for q in import_xml(xml,checker=options.get('checker'),
        checker_value=float(options.get('checker-value',1)),tests=authored) if q['name']==options.get('question')])
    if len(questions)!=1:raise VariantError('STACK XML must contain exactly one selected question')
    question=questions[0]
    count=int(options.get('variants',25))
    if not 1<=count<=100:raise VariantError('variants must be between 1 and 100')
    path=inside(root,payload['manifest'])
    value,token=history.load(path,label)
    if action in ('generate','decide','decide-many') and ('baseHash' not in payload or payload['baseHash']!=token):
        raise VariantError('manifest lease changed; reload before saving')
    approval,mode=payload.get('approval','required'),payload.get('renderMode','publish')
    if approval not in ('required','optional') or mode not in ('publish','preview','review'):raise VariantError('invalid approval/render mode')
    if action=='resolve-more' and mode!='review':raise VariantError('resolve-more requires explicit review mode')
    records=[];seen=set();deadline=time.monotonic()+120
    generated_proofs=set()
    def checked_seed(q,seed,timeout,*,identity=None):
        kwargs={} if identity is None else {'identity':identity}
        record=_bound_record(run_seed(q,seed,timeout,**kwargs),seed,backend_id,authored if backend is not None else None)
        generated_proofs.add(digest(record))
        return record

    for proposal in value['proposals']:
        tape=proposal['tape']
        if not isinstance(tape,dict) or set(tape)!={'backend','seed'} or not isinstance(tape['backend'],str):
            raise VariantError('invalid '+('SymPy' if backend_id=='sympy' else 'Maxima')+' STACK replay tape')
        seed=tape['seed']
        _bound_record(proposal['record'],seed,tape['backend'])
        # A backend move preserves decisions, but never replays old CAS tapes.
        if tape['backend']!=backend_id:continue
        if seed in seen:continue
        if len(seen)>=1000 or time.monotonic()>deadline:raise VariantError('STACK retained replay exceeded its budget')
        seen.add(seed);record=checked_seed(question,seed,min(30,max(.01,deadline-time.monotonic())))
        value=_retain(value,record,tape);records.append(record)
    counters={'replayed':len(records)}
    if action in ('generate','resolve-more') or not records and (approval=='optional' or mode!='publish'):
        start=max(seen,default=0)+1
        generated=propose(question,count,start=start,retained=records,attempt_limit=max(100,count*20),elapsed_limit=max(1,deadline-time.monotonic()),
            resolve_seed=lambda q,s:checked_seed(q,s,min(30,max(.01,deadline-time.monotonic()))))
        counters.update(nextSeed=generated['nextSeed'],skipped=generated['skipped'])
        for record in generated['records']:
            _bound_record(record,record.get('data',{}).get('plan',{}).get('seed'),backend_id,authored if backend is not None else None)
            if digest(record) not in generated_proofs:raise VariantError(f'{backend_id} propose must use the verified resolve_seed callback')
            value=_retain(value,record,{'backend':backend_id,'seed':record['data']['plan']['seed']});records.append(record)
    if action in ('decide','decide-many'):
        selections=[payload.get('decision')] if action=='decide' else payload.get('decisions')
        value=apply_decisions(value,records,selections)
    selected=history.publication(value['decisions'],records,approval=approval,render_mode=mode,target=count)
    review_candidate=payload.get('reviewCandidate')
    review_catalog=payload.get('reviewCatalog',False)
    if review_candidate is not None or review_catalog:
        if mode!='review':raise VariantError('internal candidate selection requires explicit review mode')
        selected=dict(selected,ids=[r['id'] for r in records if review_catalog or r['id']==review_candidate])
        if not selected['ids']:raise VariantError('review candidate is no longer current')
    rows=classify(value['decisions'],records)['entries']
    by_id={r['candidate']['id']:r for r in rows if r['candidate'] is not None}
    output=[]
    for record in records:
        row=by_id.get(record['id']);entry=row['entry'] if row else None
        current=row is not None and row['state'] in ('current','moved')
        output.append({**copy.deepcopy(record),'n':entry['n'] if current else None,
            'state':row['state'] if row else 'new','status':entry['status'] if current else 'undecided',
            'reviewKey':digest([record['id'],record['hash']])})
    payload_data=card_data(question,[r for r in records if r['id'] in selected['ids']],value['decisions'],identifier=label,
        review=options.get('review')=='true' or mode=='review',
        identity_verifier=lambda q,s,i:checked_seed(q,s,min(30,max(.01,deadline-time.monotonic())),identity=i))
    payload_data['common']['reviewCatalog']=bool(review_catalog)
    payload_data['common']['renderMode']=mode
    mutation=action in ('generate','decide','decide-many')
    if (source_path.read_bytes()!=source_bytes or xml.read_bytes()!=xml_bytes):
        raise VariantError('STACK source/XML/checker changed during resolution')
    native_runtime=backend.runtime_resources() if backend is not None else None
    if mutation:
        fresh=current_source(payload)
        if fresh['source']!=payload['source']:raise VariantError('STACK source changed before saving')
        token=history.write(path,value,base_hash=payload['baseHash'])
    result={'version':1,'manifest':value,'baseHash':token,'records':output,'deployableIds':selected['ids'],
        'warnings':selected['warnings'],'counters':counters,'payload':payload_data,
        'payloadJSON':json.dumps(payload_data,ensure_ascii=True)}
    if backend is not None:
        result['nativeRuntime']=native_runtime
    return result
