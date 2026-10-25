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


def supervised_seed(question,seed,timeout=30):
    """Bound the real engine per seed, including trusted custom checker code."""
    import tempfile
    code="import json,sys\np=json.load(sys.stdin); sys.path[:0]=p['paths']\nfrom ctm_checkers.stack.variants import seed_record,SeedRejected\ntry: result={'record':seed_record(p['question'],p['seed'])}\nexcept SeedRejected as error: result={'rejected':str(error)}\nprint(json.dumps(result))"
    with tempfile.TemporaryFile() as out,tempfile.TemporaryFile() as err:
        child=subprocess.Popen([sys.executable,'-I','-c',code],stdin=subprocess.PIPE,stdout=out,stderr=err,
            start_new_session=os.name!='nt')
        try:child.communicate(json.dumps({'paths':sys.path,'question':question,'seed':seed}).encode(),timeout=timeout)
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


def request(payload):
    from ctm_checkers.stack.importer import import_xml
    from ctm_checkers.stack.variants import seed_record,propose,card_data
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
    if options.get('cas',payload.get('backend','sympy'))!='sympy':raise VariantError('the Maxima variant generator is not available yet; Moodle seeds are backend-owned')
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
    checker=inside(root,os.path.normpath(str(Path(source_file).parent/options['python-checkers']))) if options.get('python-checkers') else None
    checker_bytes=checker.read_bytes() if checker else None
    questions=[q for q in import_xml(xml,python_checkers=str(checker) if checker else None) if q['name']==options.get('question')]
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
    for proposal in value['proposals']:
        tape=proposal['tape']
        if not isinstance(tape,dict) or set(tape)!={'backend','seed'} or tape['backend']!='sympy':raise VariantError('invalid SymPy STACK replay tape')
        seed=tape['seed']
        if seed in seen:continue
        if len(seen)>=1000 or time.monotonic()>deadline:raise VariantError('STACK retained replay exceeded its budget')
        seen.add(seed);record=supervised_seed(question,seed,min(30,max(.01,deadline-time.monotonic())))
        value=_retain(value,record,tape);records.append(record)
    counters={'replayed':len(records)}
    if action in ('generate','resolve-more') or not records and (approval=='optional' or mode!='publish'):
        start=max(seen,default=0)+1
        generated=propose(question,count,start=start,retained=records,attempt_limit=max(100,count*20),elapsed_limit=max(1,deadline-time.monotonic()),
            resolve_seed=lambda q,s:supervised_seed(q,s,min(30,max(.01,deadline-time.monotonic()))))
        counters.update(nextSeed=generated['nextSeed'],skipped=generated['skipped'])
        for record in generated['records']:
            value=_retain(value,record,{'backend':'sympy','seed':record['data']['plan']['seed']});records.append(record)
    if action in ('decide','decide-many'):
        selections=[payload.get('decision')] if action=='decide' else payload.get('decisions')
        value=apply_decisions(value,records,selections)
    selected=history.publication(value['decisions'],records,approval=approval,render_mode=mode,target=count)
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
        review=options.get('review')=='true' or mode=='review')
    mutation=action in ('generate','decide','decide-many')
    if (source_path.read_bytes()!=source_bytes or xml.read_bytes()!=xml_bytes or checker and checker.read_bytes()!=checker_bytes):
        raise VariantError('STACK source/XML/checker changed during resolution')
    if mutation:
        fresh=current_source(payload)
        if fresh['source']!=payload['source']:raise VariantError('STACK source changed before saving')
        token=history.write(path,value,base_hash=payload['baseHash'])
    return {'version':1,'manifest':value,'baseHash':token,'records':output,'deployableIds':selected['ids'],
        'warnings':selected['warnings'],'counters':counters,'payload':payload_data,
        'payloadJSON':json.dumps(payload_data,ensure_ascii=True)}
