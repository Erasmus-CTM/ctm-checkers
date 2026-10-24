"""Reuse a component's actual generated bundle; no Quarto or GitHub requests."""
import base64,hashlib,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT/'authoring'),str(ROOT)]
from ctm_variants import history,preview_assets
from ctm_variants.producer import produce
from ctm_variants.github_bot import Recorder
from tests.test_variants_preview_export import PreviewAPI
from tests.test_variants_github_bot import PATHS,HEAD
import runpy
fixture=Path(sys.argv[1]);output=Path(sys.argv[2]);output.mkdir(parents=True,exist_ok=True)
project=fixture/'project';source_file=project/'lesson.qmd';before=source_file.read_bytes()
response=json.loads((fixture/'response.json').read_text());export=json.loads((fixture/'result.json').read_text())
raw=source_file.read_text().splitlines();source='\n'.join(raw[1:-1]);wrapper=Path('/workspace/math-exercise/_extensions/math-exercise/question-variants.py')
options,question=runpy.run_path(str(wrapper),run_name='ctm_g1_parse')['parse_source'](source)
definition={'label':'q','file':'lesson.qmd','source':source,'options':options,'question':question}
class API(PreviewAPI):
    def request(self,method,path,value=None):
        if method=='GET' and path.endswith('/contents/lesson.qmd?ref='+HEAD):
            return {'type':'file','encoding':'base64','content':base64.b64encode(before).decode()}
        if method=='GET' and path.endswith('/contents/_variants/q.yml?ref='+HEAD):return None
        return super().request(method,path,value)
api=API();context={key:value for key,value in api.envelope.items() if key not in ('version','questions')}
assets={'students/q/'+path.relative_to(fixture/'out').as_posix():path.read_bytes()
        for path in (fixture/'out').rglob('*') if path.is_file()}
envelope,pages=produce(project,context,{'previewBase':'https://org.github.io/course/previews/variants-{pullRequest}/review'},definitions=[definition],
    resolve=lambda _:response,export_previews=lambda *_:{'studentPreviews':export['studentPreviews'],'files':assets})
api.envelope=envelope;api.members={name.removeprefix('review/'):value for name,value in pages.items()}
recorder=Recorder(api,repository='org/course',bot_login='ctm[bot]',producer_paths=PATHS)
result=recorder.export_review(20,output/'verified')
for name,content in pages.items():
    expected=content.encode() if isinstance(content,str) else content
    assert (output/'verified'/name).read_bytes()==expected
assert api.mutations==[] and source_file.read_bytes()==before and not (project/'_variants/q.yml').exists()
q=envelope['questions'][0];preview_assets.validate(q)
report={'exactSourceSHA256':hashlib.sha256(before).hexdigest(),'manifestStillAbsent':True,'sourceUnchanged':True,
        'currentRows':len(q['records']),'languages':sorted({preview['language'] for rows in q['studentPreviews'].values() for preview in rows}),
        'generatedFiles':len(assets),'completeInventoriedFiles':len(q['previewFiles']),
        'generatedBytes':sum(map(len,assets.values())),'completeBytes':sum(item['bytes'] for item in q['previewFiles'].values()),
        'copiedFilesMatchEveryByte':True,'fakeApiMutations':len(api.mutations),'export':result}
(output/'report.json').write_text(json.dumps(report,indent=2)+'\n');(output/'variants-records.json').write_text(json.dumps(envelope,indent=2)+'\n')
print(json.dumps(report,indent=2))
