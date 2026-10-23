// Explicit gone-approval retirement UI + native export/strict-check roundtrip.
import assert from 'node:assert/strict';
import {spawnSync} from 'node:child_process';
import {mkdtempSync,readFileSync,rmSync,writeFileSync} from 'node:fs';
import {tmpdir} from 'node:os';
import {join} from 'node:path';
import http from 'node:http';
import {fileURLToPath} from 'node:url';
const root=fileURLToPath(new URL('..',import.meta.url)),folder=mkdtempSync(join(tmpdir(),'ctm-retire-'));
function python(code,args=[]){const r=spawnSync(process.env.QUARTO_PYTHON||'python',['-c',code,...args],{cwd:root,encoding:'utf8'});assert.equal(r.status,0,r.stderr);return r.stdout;}
python(`
import sys,json
from pathlib import Path
sys.path.insert(0,'authoring')
from ctm_variants import history
from ctm_variants.model import candidate,snapshot
from ctm_variants.review import document,apply_decisions
p=Path(sys.argv[1]);old,live=[candidate(name,snapshot([str(n)],{'Answer':str(n)},{}),tests={'passed':True}) for n,name in enumerate(['gone','live'],1)]
value=history.append_proposals(history.empty('q'),[{'record':row,'tape':[]} for row in [old,live]])
for row in [old,live]:value=history.decision(value,[old,live],row['id'],'approved')
context={'repository':'course/lesson','branch':'feature/variants','path':'_variants/q.yml','head':'a'*40}
(p/'review.html').write_text(document({'manifest':value,'baseHash':'a'*64,'records':[live]},github_context=context))
expected=apply_decisions(value,[live],[{'id':old['id'],'hash':old['hash'],'status':'rejected','reason':'Removed from lesson'}])
(p/'expected.json').write_text(json.dumps(expected));(p/'records.json').write_text(json.dumps([live]))
`,[folder]);
const server=http.createServer((request,response)=>{response.setHeader('Content-Type','text/html; charset=utf-8');response.end(readFileSync(join(folder,'review.html')));});
let browser;
try{
 await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));
 const {chromium}=await import(process.env.CTM_PLAYWRIGHT_MODULE||'playwright');browser=await chromium.launch({headless:true});
 const page=await browser.newPage(),errors=[];page.on('pageerror',error=>errors.push(String(error)));
 await page.addInitScript(()=>{Object.defineProperty(navigator,'clipboard',{value:{writeText:async text=>{window.__copied=text;}}});});
 await page.goto('http://127.0.0.1:'+server.address().port+'/review');
 const row=page.locator('tr[data-index="1"]');assert.equal(await row.locator('button[data-status="approved"]').count(),0);
 await row.locator('summary').click();assert.match(await row.textContent(),/Retained approved snapshot/);
 const retire=row.getByRole('button',{name:'Retire missing Variant 1'});await retire.focus();await page.keyboard.press('Enter');
 assert.equal(await page.getByRole('button',{name:'Copy file',exact:true}).isDisabled(),true);
 assert.match(await page.locator('#status').textContent(),/reason is required/);
 await row.locator('input').fill('Removed from lesson');await retire.focus();await page.keyboard.press('Enter');
 await page.getByRole('button',{name:'Copy file',exact:true}).click();await page.waitForFunction(()=>window.__copied);
 writeFileSync(join(folder,'copied.yml'),await page.evaluate(()=>window.__copied));
 python(`import sys,json;from pathlib import Path;sys.path.insert(0,'authoring');from ctm_variants import history;from ctm_variants.producer import check;p=Path(sys.argv[1]);value=history.validate(json.loads((p/'copied.yml').read_text()));assert value==json.loads((p/'expected.json').read_text());assert value['decisions'][0]['n']==1;check({'questions':[{'label':'q','manifest':value,'records':json.loads((p/'records.json').read_text())}]})`,[folder]);
 assert.deepEqual(errors,[]);console.log(JSON.stringify({passed:6,scope:'keyboard retirement, required reason, readonly old snapshot, full-file native history and strict-check roundtrip; no live GitHub action',pageErrors:errors}));
}finally{if(browser)await browser.close();await new Promise(resolve=>server.close(resolve));rmSync(folder,{recursive:true,force:true});}
