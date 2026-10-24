// GitHub-only export contract; GitHub navigation is captured, never requested.
import assert from 'node:assert/strict';
import {spawnSync} from 'node:child_process';
import {mkdtempSync,readFileSync,rmSync,writeFileSync} from 'node:fs';
import {tmpdir} from 'node:os';
import {join} from 'node:path';
import http from 'node:http';
import {fileURLToPath} from 'node:url';
const root=fileURLToPath(new URL('..',import.meta.url));
const folder=mkdtempSync(join(tmpdir(),'ctm-g1-'));
function python(code,args=[]){const r=spawnSync(process.env.QUARTO_PYTHON||'python',['-c',code,...args],{cwd:root,encoding:'utf8'});assert.equal(r.status,0,r.stderr);return r.stdout;}
python(`
import sys,json
from pathlib import Path
sys.path.insert(0,'authoring')
from ctm_variants import history
from ctm_variants.model import candidate,snapshot
from ctm_variants.review import document,apply_decisions
folder=Path(sys.argv[1]);records=[candidate(name,snapshot([str(n)],{'Answer':str(n)},{},{'x':str(n)}),note='Norsk æ '+name+' </script>',tests={'passed':True},data={'huge':2**100}) for n,name in enumerate(['a','b'],1)]
value=history.append_proposals(history.empty('q'),[{'record':item,'tape':[2**90]} for item in records])
context={'repository':'course/lesson','branch':'feature/variants','path':'_variants/q.yml','head':'a'*40}
response={'manifest':value,'baseHash':None,'records':records}
(folder/'review.html').write_text(document(response,github_context=context))
selections=[dict(id=records[1]['id'],hash=records[1]['hash'],status='rejected',reason='Needs æ revision'),dict(id=records[0]['id'],hash=records[0]['hash'],status='approved',reason='')]
(folder/'expected.json').write_text(json.dumps(apply_decisions(value,records,selections)))
`,[folder]);
const server=http.createServer((request,response)=>{response.setHeader('Content-Type','text/html; charset=utf-8');response.end(readFileSync(join(folder,'review.html')));});
let browser;
try{
 await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));
 const {chromium}=await import(process.env.CTM_PLAYWRIGHT_MODULE||'playwright');browser=await chromium.launch({headless:true});
 const page=await browser.newPage();const errors=[];page.on('pageerror',e=>errors.push(String(e)));
 await page.addInitScript(()=>{window.__copied=null;window.__opened=null;Object.defineProperty(navigator,'clipboard',{value:{writeText:async text=>{window.__copied=text;}}});window.open=url=>{window.__opened=url;return null;};});
 await page.goto('http://127.0.0.1:'+server.address().port+'/review');
 assert.equal(await page.getByRole('button',{name:'Copy file',exact:true}).isDisabled(),true);
 await page.locator('button[data-index="0"][data-status="approved"]').click();
 await page.locator('#undo').click();assert.equal(await page.getByRole('button',{name:'Copy file',exact:true}).isDisabled(),true);
 await page.locator('[data-reason="1"]').fill('Needs æ revision');await page.locator('button[data-index="1"][data-status="rejected"]').click();
 await page.locator('#bulk').click();
 await page.getByRole('button',{name:'Copy file',exact:true}).click();
 await page.waitForFunction(()=>window.__copied!==null);
 const copied=await page.evaluate(()=>window.__copied);writeFileSync(join(folder,'copied.yml'),copied);
 assert.ok(copied.includes('1267650600228229401496703205376'),'large integer remains exact');
 python(`import sys,json;from pathlib import Path;sys.path.insert(0,'authoring');from ctm_variants import history;p=Path(sys.argv[1]);value=history.validate(json.loads((p/'copied.yml').read_text()));assert value==json.loads((p/'expected.json').read_text());history.write(p/'roundtrip.yml',value,base_hash=None);assert history.load(p/'roundtrip.yml','q')[0]==value`,[folder]);
 assert.match(await page.locator('#status').textContent(),/Complete manifest copied/);
 await page.getByRole('button',{name:'Open in GitHub editor'}).click();
 assert.equal(await page.evaluate(()=>window.__opened),'https://github.com/course/lesson/new/feature%2Fvariants?filename=_variants%2Fq.yml');
 assert.match(await page.locator('#status').textContent(),/has not saved repository files/);
 assert.deepEqual(errors,[]);
 console.log(JSON.stringify({passed:7,scope:'GitHub-only complete manifest copy, bulk/undo, lossless native roundtrip, captured editor URL; no live GitHub action',pageErrors:errors}));
}finally{if(browser)await browser.close();await new Promise(resolve=>server.close(resolve));rmSync(folder,{recursive:true,force:true});}
