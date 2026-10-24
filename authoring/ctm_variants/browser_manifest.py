"""Lossless browser export of already validated native review records.

No resolver, grading or cryptographic snapshot construction lives here. Native
consumers still validate the complete exported history and current source.
"""

SCRIPT = r'''
globalThis.CTMManifestExport=(()=>{
 class NumberToken{constructor(raw){this.raw=raw;}}
 function parse(source){
  let position=0;
  const whitespace=()=>{while(/\s/.test(source[position]||'')&&position<source.length)position++;};
  function value(){
   whitespace();const start=position,first=source[position];
   if(first==='"'){
    position++;while(position<source.length){const char=source[position++];if(char==='\\')position++;else if(char==='"')return JSON.parse(source.slice(start,position));}
    throw new Error('Unterminated JSON string');
   }
   if(first==='['||first==='{'){
    const array=first==='[',result=array?[]:Object.create(null),close=array?']':'}';position++;whitespace();
    if(source[position]===close){position++;return result;}
    while(true){
     let key;if(!array){key=value();if(typeof key!=='string'||Object.hasOwn(result,key))throw new Error('Invalid JSON object key');whitespace();if(source[position++]!==':')throw new Error('Missing colon');}
     const child=value();if(array)result.push(child);else result[key]=child;
     whitespace();const separator=source[position++];if(separator===close)return result;if(separator!==',')throw new Error('Missing JSON separator');
    }
   }
   for(const [literal,result] of [['true',true],['false',false],['null',null]])if(source.startsWith(literal,position)){position+=literal.length;return result;}
   const match=/^-?(?:0|[1-9]\d*)(?:\.\d+)?(?:[eE][+-]?\d+)?/.exec(source.slice(position));
   if(!match)throw new Error('Invalid JSON value');position+=match[0].length;return new NumberToken(match[0]);
  }
  const result=value();whitespace();if(position!==source.length)throw new Error('Trailing JSON data');return result;
 }
 function dump(value,canonical=false){
  if(value instanceof NumberToken)return value.raw;
  if(Array.isArray(value))return '['+value.map(item=>dump(item,canonical)).join(',')+']';
  if(value&&typeof value==='object'){
   const keys=Object.keys(value);if(canonical)keys.sort();
   return '{'+keys.map(key=>JSON.stringify(key)+':'+dump(value[key],canonical)).join(',')+'}';
  }
  if(value===null||typeof value==='string'||typeof value==='boolean')return JSON.stringify(value);
  throw new Error('Non-lossless JSON value');
 }
 const equal=(a,b)=>dump(a,true)===dump(b,true);
 const copy=value=>parse(dump(value));
 function moved(entries,records,locator){
  const byId=new Map(records.map(item=>[item.id,item]));
  const byHash=new Map(),oldHash=new Map(),matched=new Set(),used=new Set();
  for(const item of records){const group=byHash.get(item.hash)||[];group.push(item);byHash.set(item.hash,group);}
  for(const entry of entries){const group=oldHash.get(entry.hash)||[];group.push(entry);oldHash.set(entry.hash,group);}
  for(const entry of entries){const exact=byId.get(entry.id);if(exact&&exact.hash===entry.hash){matched.add(entry);used.add(exact.id);}}
  for(const entry of entries){const exact=byId.get(entry.id);if(!matched.has(entry)&&exact&&!used.has(exact.id)){matched.add(entry);used.add(exact.id);}}
  for(const entry of entries){
   if(matched.has(entry))continue;const same=byHash.get(entry.hash)||[];
   if(same.length===1&&oldHash.get(entry.hash).length===1&&!used.has(same[0].id)){
    if(same[0].id===locator)return entry;matched.add(entry);used.add(same[0].id);
   }
  }
  return null;
 }
 function apply(manifestJSON,recordsJSON,selections){
  const result=parse(manifestJSON),records=parse(recordsJSON);
  if(!Array.isArray(selections)||!selections.length)throw new Error('Select a decision first');
  const seen=new Set();
  for(const selection of selections){
   if(!selection||typeof selection.id!=='string'||seen.has(selection.id)||!['approved','rejected'].includes(selection.status))throw new Error('Invalid or duplicate decision');
   seen.add(selection.id);
   if(Object.keys(selection).some(key=>!['id','hash','status','by','date','reason'].includes(key)))throw new Error('Unknown decision metadata');
   for(const name of ['by','date','reason'])if(selection[name]!==undefined&&typeof selection[name]!=='string')throw new Error('Decision metadata must be text');
   let item=records.find(record=>record.id===selection.id);
   if(!item){
    const old=result.decisions.find(entry=>entry.id===selection.id&&entry.hash===selection.hash);
    if(selection.status!=='rejected'||!old||old.status!=='approved'||!selection.reason?.trim())throw new Error('Absent approved candidates require retirement with their exact retained hash and a reason');
    // A globally unambiguous move still has a current candidate and is not gone.
    const same=records.filter(record=>record.hash===old.hash),oldSame=result.decisions.filter(entry=>entry.hash===old.hash);
    if(same.length===1&&oldSame.length===1&&!result.decisions.some(entry=>entry.id===same[0].id))throw new Error('Current moved candidates cannot use absent retirement');
    item={id:old.id,hash:old.hash,snapshot:old.snapshot,note:old.note||''};
   }
   if(item.hash!==selection.hash)throw new Error('Decision differs from current candidate');
   if(selection.status==='approved'&&item.tests?.passed!==true)throw new Error('Approval requires passing recorded tests');
   if(!result.proposals.some(proposal=>proposal.record.id===item.id&&proposal.record.hash===item.hash&&['math','teacher','grading'].every(key=>equal(proposal.record.snapshot[key],item.snapshot[key]))))throw new Error('Decision lacks its retained proposal and replay tape');
   const before=result.decisions;
   const previous=before.find(entry=>entry.id===item.id)||moved(before,records,item.id);
   const number=previous?previous.n:new NumberToken((before.reduce((max,entry)=>{const n=BigInt(entry.n.raw);return n>max?n:max;},0n)+1n).toString());
   const updated={n:number,id:item.id,hash:item.hash,status:selection.status,snapshot:copy(item.snapshot),note:item.note||'',by:selection.by||'',date:selection.date||''};
   if(selection.reason)updated.reason=selection.reason;
   const after=before.filter(entry=>!previous||entry.n.raw!==previous.n.raw).concat([updated]);
   after.sort((a,b)=>BigInt(a.n.raw)<BigInt(b.n.raw)?-1:BigInt(a.n.raw)>BigInt(b.n.raw)?1:0);
   if(!equal(before,after)){result.events.push({before:copy(before),after:copy(after)});result.decisions=after;}
  }
  return dump(result)+'\n';
 }
 return {apply};
})();
'''
