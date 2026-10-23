"""Generated static previews are data copied only after complete provenance proof."""
import base64,copy,hashlib,sys,tempfile
from pathlib import Path
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'authoring'))
from ctm_variants import preview_assets
from ctm_variants.model import VariantError,digest
from ctm_variants.review import document
from tests.test_variants_preview_export import PreviewAPI
from ctm_variants.github_bot import Recorder
from tests.test_variants_github_bot import PATHS

class BundleAPI(PreviewAPI):
    def __init__(self):
        super().__init__();self.source=b'# canonical source fixture\n'
        q=self.envelope['questions'][0];row=q['records'][0]
        url='students/q/en/index.html?ctm-review='+digest([row['id'],row['hash']])
        q.update(studentPreviews={row['id']:[{'language':'en','url':url,'hash':row['hash']}]},
                 previewSource={'file':'lesson.qmd','sha256':hashlib.sha256(self.source).hexdigest()})
        self.members.update({'students/q/en/index.html':'<main>Real component fixture</main>',
                             'students/q/en/site_libs/runtime.js':'/* generated runtime */'})
        q['previewFiles']={name:preview_assets.receipt(text.encode()) for name,text in self.members.items()}
    def request(self,method,path,value=None):
        if method=='GET' and path.endswith('/contents/lesson.qmd?ref='+'a'*40):
            return {'type':'file','encoding':'base64','content':base64.b64encode(self.source).decode()}
        return super().request(method,path,value)

class PreviewAssets(unittest.TestCase):
    def recorder(self,api):return Recorder(api,repository='org/course',bot_login='ctm[bot]',producer_paths=PATHS)
    def test_exact_generated_bundle_exports_nested_assets_without_execution(self):
        api=BundleAPI();q=api.envelope['questions'][0]
        api.members['students/q/en/runtime.wasm']=b'\x00\xffwasm'
        name='students/q/en/ctm-checkers-0.6.1.dev0+build/ctm-checkers.js'
        api.members[name]='/* versioned generated runtime */'
        q['previewFiles'][name]=preview_assets.receipt(api.members[name].encode())
        q['previewFiles']['students/q/en/runtime.wasm']=preview_assets.receipt(b'\x00\xffwasm')
        self.assertEqual(set(preview_assets.inventory([q])),set(api.members))
        with tempfile.TemporaryDirectory() as folder:
            self.recorder(api).export_review(20,Path(folder)/'out')
            self.assertEqual((Path(folder)/'out/review/students/q/en/site_libs/runtime.js').read_text(),'/* generated runtime */')
            self.assertFalse((Path(folder)/'out/lesson.qmd').exists())
        self.assertEqual(api.mutations,[])
    def test_malformed_bundle_fails_before_any_copy(self):
        for kind in ('changedbytes','digest','traversal','hidden','sourcefile','missingouter','missingasset',
                     'extraasset','key','hash','language','urlscheme','sourcehash','partial','casefold','size','prefix','caseprefix'):
            api=BundleAPI();q=api.envelope['questions'][0];row=q['records'][0];preview=q['studentPreviews'][row['id']][0]
            if kind=='changedbytes':api.members['students/q/en/site_libs/runtime.js']='changed'
            if kind=='digest':q['previewFiles']['q.html']['sha256']='0'*64
            if kind=='traversal':q['previewFiles']['students/q/en/../bad.js']=preview_assets.receipt(b'')
            if kind=='hidden':q['previewFiles']['students/q/en/.env.json']=preview_assets.receipt(b'')
            if kind=='sourcefile':q['previewFiles']['students/q/en/native-authoring/code.py']=preview_assets.receipt(b'')
            if kind=='missingouter':del q['previewFiles']['q.html']
            if kind=='missingasset':del api.members['students/q/en/index.html']
            if kind=='extraasset':api.members['students/q/en/extra.js']='extra'
            if kind=='key':preview['url']=preview['url'].replace('ctm-review=','ctm-review=0')
            if kind=='hash':preview['hash']='stale'
            if kind=='language':preview['language']='fr'
            if kind=='urlscheme':preview['url']='https://evil.test/'+preview['url']
            if kind=='sourcehash':q['previewSource']['sha256']='0'*64
            if kind=='partial':del q['previewSource']
            if kind=='casefold':q['previewFiles']['students/q/en/INDEX.html']=preview_assets.receipt(b'')
            if kind=='size':q['previewFiles']['q.html']['bytes']=preview_assets.MAX_FILE_BYTES+1
            if kind in ('prefix','caseprefix'):
                name='students/q/en/'+('INDEX.html' if kind=='caseprefix' else 'index.html')+'/x.js'
                api.members[name]='/* impossible child */'
                q['previewFiles'][name]=preview_assets.receipt(api.members[name].encode())
            with self.subTest(kind=kind),tempfile.TemporaryDirectory() as folder:
                output=Path(folder)/'out'
                with self.assertRaises(VariantError):self.recorder(api).export_review(20,output)
                self.assertFalse(output.exists());self.assertEqual(api.mutations,[])
    def test_relative_ui_route_is_current_hash_bound_and_local_token_routes_remain(self):
        q=BundleAPI().envelope['questions'][0];response={'manifest':q['manifest'],'records':q['records'],'baseHash':q['baseHash']}
        page=document(response,student_previews=q['studentPreviews'])
        self.assertIn('data-src="students/q/en/index.html?ctm-review=',page)
        for change in ({'hash':'stale'},{'url':'//evil.test/index.html'},{'language':'de'}):
            bad=copy.deepcopy(q['studentPreviews']);next(iter(bad.values()))[0].update(change)
            with self.assertRaises(VariantError):document(response,student_previews=bad)
    def test_producer_binds_transient_response_routes_and_inventory_without_source_writes(self):
        from ctm_variants.producer import produce
        from tests import test_variants_producer as fixtures
        fixture=fixtures.ProducerTests();fixture.setUp();row=fixture.item
        from ctm_variants import history
        value=history.append_proposals(history.empty('q'),[{'record':row,'tape':[]}])
        response={'baseHash':None,'manifest':value,'records':[row]}
        def export(payload, resolved):
            self.assertEqual(resolved['manifest'],value)
            self.assertEqual(payload['renderMode'],'review')
            return {'studentPreviews':{row['id']:[{'language':'en','hash':row['hash'],
                'url':'students/q/en/index.html?ctm-review='+digest([row['id'],row['hash']])}]},
                'files':{'students/q/en/index.html':b'<main>Generated student</main>',
                         'students/q/en/runtime.js':b'/* runtime */'}}
        with tempfile.TemporaryDirectory() as folder:
            source=Path(folder)/'lesson.qmd';source.write_text('exact authored source')
            before=source.read_bytes()
            envelope,pages=produce(folder,fixtures.CONTEXT,fixture.config,definitions=[fixture.definition],resolve=lambda _:response,export_previews=export)
            q=envelope['questions'][0]
            self.assertEqual(q['previewFiles']['q.html'],preview_assets.receipt(pages['review/q.html'].encode()))
            self.assertEqual(q['previewSource']['sha256'],hashlib.sha256(before).hexdigest())
            self.assertEqual(q['records'][0],row)
            self.assertFalse((Path(folder)/'_variants/q.yml').exists())
            self.assertEqual(source.read_bytes(),before)
            self.assertIn('data-src="students/q/en/index.html?ctm-review=',pages['review/q.html'])
            def resolve_changed(payload):
                source.write_text('changed during resolve');return response
            with self.assertRaises(VariantError):produce(folder,fixtures.CONTEXT,fixture.config,definitions=[fixture.definition],resolve=resolve_changed,export_previews=export)
            source.write_bytes(before)
            def changed(payload,resolved):
                result=export(payload,resolved);source.write_text('changed');return result
            with self.assertRaises(VariantError):produce(folder,fixtures.CONTEXT,fixture.config,definitions=[fixture.definition],resolve=lambda _:response,export_previews=changed)

    def test_zero_current_records_have_no_student_catalog_and_retain_outer_review(self):
        from ctm_variants.producer import produce,check
        from ctm_variants import history
        from tests.test_variants_producer import CONTEXT
        definition={'label':'q','file':'lesson.qmd','source':'source','options':{'variables':'a=1'},'question':'question'}
        response={'baseHash':None,'manifest':history.empty('q'),'records':[]}
        with tempfile.TemporaryDirectory() as folder:
            Path(folder,'lesson.qmd').write_text('source')
            envelope,pages=produce(folder,CONTEXT,{'previewBase':'https://preview.test/review'},definitions=[definition],
                resolve=lambda _:response,export_previews=lambda *_:{'studentPreviews':{},'files':{}})
            q=envelope['questions'][0]
            self.assertEqual(q['studentPreviews'],{})
            self.assertEqual(set(q['previewFiles']),{'q.html'})
            self.assertNotIn('<iframe',pages['review/q.html'])
            with self.assertRaises(VariantError):check(envelope)

    def test_cli_wiring_uses_only_trusted_isolated_exporter_and_generated_output(self):
        from ctm_variants.producer import render_previews
        import json
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);trusted=root/'trusted';project=root/'authored'
            trusted.mkdir();project.mkdir();wrapper=trusted/'question-variants.py';wrapper.touch()
            (trusted/'variants-review.py').touch()
            payload={'file':'lesson.qmd','label':'q'};response={'records':[],'manifest':{},'baseHash':None}
            def command(args,cwd,environment,**limits):
                self.assertEqual(args[:3],[sys.executable,'-I',str(trusted/'variants-review.py')])
                self.assertEqual(cwd,trusted)
                self.assertEqual(limits['timeout'],1800)
                self.assertEqual(json.loads(Path(args[args.index('--response-json')+1]).read_text()),response)
                self.assertEqual(args[args.index('--url-prefix')+1],'students/q')
                output=Path(args[args.index('--export-student-previews')+1]);(output/'en').mkdir(parents=True)
                (output/'en/index.html').write_bytes(b'<main>generated</main>')
                return json.dumps({'studentPreviews':{}})
            class Exporter:render_command=staticmethod(command)
            with patch('ctm_variants.producer.runpy.run_path',return_value={'Review':Exporter}):
                result=render_previews(project,trusted,wrapper,payload,response)
            self.assertEqual(result['files'],{'students/q/en/index.html':b'<main>generated</main>'})
            self.assertEqual(result['studentPreviews'],{})
            self.assertEqual(list(project.iterdir()),[])

    def test_case_collisions_across_questions_and_global_budgets_fail(self):
        first=BundleAPI().envelope['questions'][0]
        second=copy.deepcopy(first);second['label']='Q'
        second.pop('studentPreviews');second.pop('previewFiles');second.pop('previewSource')
        with self.assertRaises(VariantError):preview_assets.inventory([first,second])
        with patch.object(preview_assets,'MAX_FILES',1):
            with self.assertRaises(VariantError):preview_assets.inventory([first])
if __name__=='__main__':unittest.main()
