// Bounded UI routing contract. Generation backend is a lease-checking fixture.
import assert from 'node:assert/strict';
import {spawnSync} from 'node:child_process';
import http from 'node:http';
import {fileURLToPath} from 'node:url';
const root=fileURLToPath(new URL('..',import.meta.url));
const pages={};
for(const language of ['en','de','nb']){
 const result=spawnSync(process.env.QUARTO_PYTHON||'python',['-c',`
import sys
sys.path.insert(0,'authoring')
from ctm_variants import history
from ctm_variants.review import document
language=sys.argv[1]
print(document({'manifest':history.empty('q'),'baseHash':'a'*64,'records':[]},connected_endpoint='/'+language*24+'/',language=language))
`,language],{cwd:root,encoding:'utf8'});assert.equal(result.status,0,result.stderr);pages['/'+language.repeat(24)+'/']=result.stdout;
}
const requests=[];let lease='a'.repeat(64),generated=0;
const server=http.createServer((request,response)=>{
 response.setHeader('Content-Type','text/html; charset=utf-8');
 if(request.method==='GET'){if(!pages[request.url]){response.writeHead(204);response.end();return;}response.end(pages[request.url].replaceAll('a'.repeat(64),lease));return;}
 let body='';request.on('data',chunk=>body+=chunk);request.on('end',()=>{
  const value=JSON.parse(body);requests.push(value);response.setHeader('Content-Type','application/json');
  if(value.action!=='generate25more'||value.baseHash!==lease){response.writeHead(409);response.end(JSON.stringify({error:'stale lease'}));return;}
  generated++;lease='b'.repeat(64);response.end(JSON.stringify({saved:true}));
 });
});
let browser;
try{
 await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));
 const {chromium}=await import(process.env.CTM_PLAYWRIGHT_MODULE||'playwright');browser=await chromium.launch({headless:true});
 const errors=[];const page=await browser.newPage(),stale=await browser.newPage();for(const p of [page,stale])p.on('pageerror',e=>errors.push(String(e)));
 const base='http://127.0.0.1:'+server.address().port;
 await page.goto(base+'/'+'en'.repeat(24)+'/');await stale.goto(page.url());
 const button=page.getByRole('button',{name:'Generate 25 more',exact:true});await button.focus();
 await Promise.all([page.waitForEvent('load'),page.keyboard.press('Enter')]);
 assert.equal(generated,1);assert.deepEqual(requests[0],{action:'generate25more',baseHash:'a'.repeat(64)});
 assert.match(await page.locator('#status').textContent(),/Generation saved.*rebuilt/);
 await stale.getByRole('button',{name:'Generate 25 more',exact:true}).click();
 await stale.waitForFunction(()=>document.getElementById('status').textContent.startsWith('Generation not confirmed:'));
 assert.equal(generated,1);assert.deepEqual(requests[1],requests[0],'stale intent retains original lease');
 assert.equal(await stale.locator('#generate-more').isDisabled(),true);assert.equal(await stale.getByRole('button',{name:'Rebuild review',exact:true}).isEnabled(),true);
 for(const [language,label] of [['de','25 weitere generieren'],['nb','Generer 25 til']]){
  await page.goto(base+'/'+language.repeat(24)+'/');assert.equal(await page.getByRole('button',{name:label,exact:true}).getAttribute('lang'),language);
 }
 assert.deepEqual(errors,[]);
 console.log(JSON.stringify({passed:7,scope:'keyboard/localized generation UI and original-lease routing with fixture backend; no native generation rerun',pageErrors:errors}));
}finally{if(browser)await browser.close();await new Promise(resolve=>server.close(resolve));}
