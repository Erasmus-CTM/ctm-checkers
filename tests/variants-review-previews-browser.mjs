// Shared card transport only: no Quarto, Python engine or grading claim.
import assert from 'node:assert/strict';
import {spawnSync} from 'node:child_process';
import http from 'node:http';
import {fileURLToPath} from 'node:url';
const root=fileURLToPath(new URL('..',import.meta.url));
const token='t'.repeat(43);
const script=`
import sys
sys.path.insert(0,'authoring')
from ctm_variants import history
from ctm_variants.model import candidate,snapshot
from ctm_variants.review import document
item=candidate('a',snapshot(['2'],{'answer':'2'},{}),tests={'passed':True})
response={'manifest':history.empty('q'),'baseHash':'lease','records':[item]}
print(document(response,student_previews={'a':[{'language':lang,'url':'/'+sys.argv[1]+'/previews/opaque/'+lang+'/index.html'} for lang in ['en','nb']]}))
`;
const result=spawnSync(process.env.QUARTO_PYTHON||'python',['-c',script,token],{cwd:root,encoding:'utf8'});
assert.equal(result.status,0,result.stderr);
const requests=[];
const server=http.createServer((request,response)=>{
 if(request.url==='/review'){response.setHeader('Content-Type','text/html; charset=utf-8');response.end(result.stdout);}
 else if(request.url.startsWith('/'+token+'/previews/')){requests.push(request.url);response.setHeader('Content-Type','text/html');response.end('<!doctype html><title>Fixture student view</title><p>Fixture only</p>');}
 else{response.writeHead(204);response.end();}
});
let browser;
try{
 await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));
 const {chromium}=await import(process.env.CTM_PLAYWRIGHT_MODULE||'playwright');
 browser=await chromium.launch({headless:true});
 const page=await browser.newPage();const errors=[];page.on('pageerror',e=>errors.push(String(e)));
 await page.goto('http://127.0.0.1:'+server.address().port+'/review');
 assert.deepEqual(requests,[],'collapsed previews trigger no iframe request');
 const details=page.locator('details[data-student-preview]');
 assert.equal(await details.count(),2);
 assert.equal(await page.getByRole('link',{name:'Open Student view — en',includeHidden:true}).count(),1);
 await Promise.all([page.waitForResponse(r=>r.url().includes('/en/index.html')),details.nth(0).locator('summary').click()]);
 assert.deepEqual(requests,['/'+token+'/previews/opaque/en/index.html']);
 assert.equal(await page.locator('iframe[title="Student view — nb"]').getAttribute('src'),null);
 await details.nth(0).locator('summary').click();await details.nth(0).locator('summary').click();
 assert.equal(requests.length,1,'reopening does not reload iframe');
 await page.locator('button[data-status="approved"]').click();
 assert.match(await page.locator('#status').textContent(),/nothing saved/i,'optional previews preserve disconnected decisions');
 assert.deepEqual(errors,[]);
 console.log(JSON.stringify({passed:5,scope:'shared lazy student preview card transport only',pageErrors:errors}));
}finally{if(browser)await browser.close();await new Promise(resolve=>server.close(resolve));}
