// Focused disconnected native review UI: no CDN, Python browser runtime or course.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const {spawnSync} = require('node:child_process');
const http = require('node:http');
const {chromium} = require('playwright');
const root = path.resolve(__dirname, '..');
const folder = fs.mkdtempSync(path.join(os.tmpdir(), 'ctm-review-'));
function python(code, args=[]) {
  const run=spawnSync(process.env.QUARTO_PYTHON || 'python', ['-c', code, ...args], {cwd:root, encoding:'utf8'});
  assert.equal(run.status,0,run.stderr);return run.stdout;
}
const fixture = `
import sys,json
from pathlib import Path
sys.path.insert(0,'authoring')
from ctm_variants import history
from ctm_variants.model import candidate,snapshot
from ctm_variants.review import request,document
folder=Path(sys.argv[1]);value=history.empty('review-q')
def item(id,variable,answer,passed=True):
 return candidate(id,snapshot([variable],{'Answer':answer},{},{'x':variable}),note='Note '+id+' </script>',data={'options':{'question':'Student '+id+' <img src=x onerror=alert(1)>','solution':'Solution '+answer}},tests={'passed':passed})
old=[item('same-answer','1','2'),item('new-answer','1','2'),item('rejected','1','2')]
for row in old:
 value=history.append_proposals(value,[{'record':row,'tape':[]}]);value=history.decision(value,old,row['id'],'rejected' if row['id']=='rejected' else 'approved')
records=[item('new','1','2'),item('same-answer','2','2'),item('new-answer','2','3'),old[2],item('failed','1','2',False),item('untested','1','2')]
records[-1]['tests']=[]
for row in records:value=history.append_proposals(value,[{'record':row,'tape':[]}])
history.write(folder/'q.yml',value,base_hash=None)
response=request({'version':1,'projectRoot':str(folder),'manifest':'q.yml','label':'review-q','records':records})
(folder/'review.html').write_text(document(response))
print(response['baseHash'])
`;
(async()=>{
 let browser,server;
 try {
  const token=python(fixture,[folder]).trim();
  server=http.createServer((request,response)=>{response.setHeader('Content-Type','text/html; charset=utf-8');response.end(fs.readFileSync(path.join(folder,'review.html')));});
  await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));
  browser=await chromium.launch({headless:true,executablePath:process.env.CHROMIUM_EXECUTABLE || undefined});
  const page=await browser.newPage();const errors=[];page.on('pageerror',error=>errors.push(String(error)));
  await page.goto('http://127.0.0.1:'+server.address().port+'/review.html');
  assert.match(await page.locator('#overview').textContent(),/3 new · 2 changed · 1 current/);
  assert.equal(await page.locator('tr[data-index="3"]').isVisible(),false);
  assert.equal(await page.locator('button[data-index="4"][data-status="approved"]').isDisabled(),true);
  assert.equal(await page.locator('button[data-index="5"][data-status="approved"]').isDisabled(),true);
  await page.locator('tr[data-index="1"] summary').click();
  assert.match(await page.locator('tr[data-index="1"] details').textContent(),/Student same-answer <img/);
  assert.equal(await page.locator('img').count(),0,'preview is escaped, never executable HTML');
  assert.equal(await page.locator('tr[data-index="1"] .unchanged').count(),1);
  assert.match(await page.locator('tr[data-index="1"] details').textContent(),/Was → now/);
  await page.locator('#again').focus();await page.keyboard.press('Enter');
  assert.equal(await page.locator('.pending').filter({hasText:'staged'}).count(),1);
  await page.locator('#undo').click();assert.equal(await page.locator('.pending').filter({hasText:'staged'}).count(),0);
  await page.locator('[data-reason="0"]').fill('Needs revision');await page.locator('button[data-index="0"][data-status="rejected"]').click();
  await page.locator('#bulk').click();
  assert.match(await page.locator('tr[data-index="0"] .pending').textContent(),/rejected/,'bulk preserves staged rejection');
  assert.equal(await page.locator('.pending').filter({hasText:'approved'}).count(),2);
  assert.match(await page.locator('#status').textContent(),/New 5, New 6/);
  await page.locator('#root').fill(folder);await page.locator('#path').fill('q.yml');
  const downloadPromise=page.waitForEvent('download');await page.locator('#download').click();
  const download=await downloadPromise;const requestPath=path.join(folder,'decisions.json');await download.saveAs(requestPath);
  const payload=JSON.parse(fs.readFileSync(requestPath,'utf8'));
  assert.equal(payload.action,'decide-many');assert.equal(payload.baseHash,token);assert.equal(payload.decisions.length,3);
  assert.deepEqual(payload.decisions.find(item=>item.id==='new'),{id:'new',hash:payload.records[0].hash,status:'rejected',reason:'Needs revision'});
  assert.equal(payload.decisions.some(item=>['failed','untested','rejected'].includes(item.id)),false);
  assert.match(await page.locator('#status').textContent(),/nothing saved/i);
  python(`import sys,json;sys.path.insert(0,'authoring');from ctm_variants.review import request;from ctm_variants.model import VariantError;p=json.load(open(sys.argv[1]));r=request(p);assert len(r['manifest']['decisions'])==4\ntry:request(p)\nexcept VariantError as e:assert 'changed' in str(e)\nelse:raise AssertionError('stale lease accepted')`,[requestPath]);
  assert.deepEqual(errors,[]);console.log('PASS: disconnected overview, escaped previews, changed snapshots, keyboard bulk/undo, rejection retention, real leased batch apply and stale-write rejection');
 } finally {if(browser)await browser.close();if(server)await new Promise(resolve=>server.close(resolve));fs.rmSync(folder,{recursive:true,force:true});}
})().catch(error=>{console.error(error);process.exitCode=1;});
