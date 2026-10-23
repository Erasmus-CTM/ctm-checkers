"""Verified HTML export uses fake API downloads, never a live publisher."""
import hashlib,io,json,sys,tempfile,zipfile
from pathlib import Path
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'authoring'))
from ctm_variants.github_bot import Recorder
from ctm_variants.model import VariantError
from ctm_variants.review import card_id
from tests.test_variants_github_bot import FakeGitHub,PATHS,HEAD
class PreviewAPI(FakeGitHub):
    def __init__(self):
        super().__init__();q=self.envelope['questions'][0];row=q['records'][0]
        q['cards']={row['id']:'https://org.github.io/course/previews/variants-7/review/q.html#'+card_id(row['id'])}
        self.special_type=None;self.members={'q.html':'<main id="'+card_id(row['id'])+'">Escaped content</main>'};self.bad_digest=False
    def review_archive(self):
        out=io.BytesIO()
        with zipfile.ZipFile(out,'w') as archive:
            for name,text in self.members.items():
                info=zipfile.ZipInfo(name)
                if self.special_type is not None:info.external_attr=self.special_type << 16
                archive.writestr(info,text)
        return out.getvalue()
    def request(self,method,path,value=None):
        if method=='GET' and path.endswith('/actions/runs/20/artifacts?per_page=100'):
            base=super().request(method,path,value);data=self.review_archive()
            base['artifacts'].append({'id':31,'name':'ctm-variants-review','size_in_bytes':len(data),'digest':'bad' if self.bad_digest else 'sha256:'+hashlib.sha256(data).hexdigest(),'expired':False});return base
        return super().request(method,path,value)
    def download(self,path,limit):
        if path.endswith('/actions/artifacts/31/zip'):return self.review_archive()
        return super().download(path,limit)
class PreviewExport(unittest.TestCase):
    def exporter(self,api):return Recorder(api,repository='org/course',bot_login='ctm[bot]',producer_paths=PATHS)
    def test_exact_run_fixed_destination_and_only_html_files(self):
        api=PreviewAPI()
        with tempfile.TemporaryDirectory() as d:
            result=self.exporter(api).export_review(20,Path(d)/'out')
            self.assertEqual(result,dict(head=HEAD,pullRequest=7,destination='previews/variants-7',publish=True))
            self.assertEqual((Path(d)/'out/review/q.html').read_text(),api.members['q.html'])
            self.assertEqual(api.mutations,[])
    def test_bad_archive_provenance_or_route_fails_before_writes(self):
        for kind in ('traversal','extra','missing','digest','anchor','route','stale','symlink','fifo'):
            api=PreviewAPI()
            if kind=='traversal':api.members={'../q.html':'bad'}
            if kind=='extra':api.members['extra.html']='bad'
            if kind=='missing':api.members={}
            if kind=='digest':api.bad_digest=True
            if kind=='anchor':api.members={'q.html':'no anchor'}
            if kind=='route':api.envelope['questions'][0]['cards']={k:v.replace('variants-7','variants-8') for k,v in api.envelope['questions'][0]['cards'].items()}
            if kind=='stale':api.stale_at=2
            if kind=='symlink':api.special_type=0o120777
            if kind=='fifo':api.special_type=0o010600
            with self.subTest(kind=kind),tempfile.TemporaryDirectory() as d:
                output=Path(d)/'out'
                with self.assertRaises(VariantError):self.exporter(api).export_review(20,output)
                self.assertFalse(output.exists());self.assertEqual(api.mutations,[])
    def test_output_reuse_refused_and_empty_question_artifact_does_not_publish(self):
        api=PreviewAPI()
        with tempfile.TemporaryDirectory() as d:
            Path(d,'existing').write_text('keep')
            with self.assertRaises(VariantError):self.exporter(api).export_review(20,d)
            self.assertEqual(Path(d,'existing').read_text(),'keep')
            api.envelope['questions']=[]
            self.assertFalse(self.exporter(api).export_review(20,Path(d)/'out')['publish'])
            self.assertFalse(Path(d,'out').exists())
if __name__=='__main__':unittest.main()
