"""Review existing native proposals through the same leased manifest writer."""
import html
import json
from pathlib import Path

from ctm_variants import history
from ctm_variants.model import VariantError, classify


def _path(root, name):
    root = Path(root).resolve()
    path = (root / name).resolve()
    try:
        path.relative_to(root)
    except ValueError as error:
        raise VariantError("manifest path must stay inside projectRoot") from error
    return path


def apply_decisions(value, records, selections):
    """Apply explicit current selections in memory; caller owns the one lease.

    Shared by the recording CLI and component wrappers after source
    reconciliation, so a changed source version need not be saved separately
    merely to approve it. No file access or source execution occurs here.
    """
    if len({item["id"] for item in records}) != len(records):
        raise VariantError("component must select one current version per proposal id")
    if type(selections) is not list or not selections:
        raise VariantError("bulk decisions require a nonempty list")
    seen = set()
    for selected in selections:
        if (type(selected) is not dict or not {"id", "hash", "status"}.issubset(selected)
                or set(selected) - {"id", "hash", "status", "by", "date", "reason"}):
            raise VariantError("invalid decision request")
        if not isinstance(selected["id"], str) or selected["id"] in seen:
            raise VariantError("decision locators must be distinct strings")
        seen.add(selected["id"])
        item = next((item for item in records if item["id"] == selected["id"]), None)
        if item is None or item["hash"] != selected["hash"]:
            raise VariantError("decision id/hash differs from current candidate")
        value = history.decision(value, records, selected["id"], selected["status"],
            by=selected.get("by", ""), date=selected.get("date", ""), reason=selected.get("reason", ""))
    return value


def request(payload):
    """Read/decide previously generated records; never execute question source."""
    if type(payload) is not dict or payload.get("version") != 1:
        raise VariantError("invalid review request/version")
    action = payload.get("action", "resolve")
    if action not in ("resolve", "decide", "decide-many"):
        raise VariantError("review action must be resolve, decide or decide-many")
    path = _path(payload["projectRoot"], payload["manifest"])
    value, token = history.load(path, payload["label"])
    # Current versions are supplied by the component resolver. No source is
    # executed in the recording path (also used by trusted-base bot scripts).
    if "records" not in payload:
        raise VariantError("review requires component-resolved current records; history alone cannot establish current/gone")
    records = payload["records"]
    if len({item["id"] for item in records}) != len(records):
        raise VariantError("component must select one current version per proposal id")
    if action in ("decide", "decide-many"):
        if "baseHash" not in payload:
            raise VariantError("deciding requires a baseHash lease")
        selections = [payload.get("decision")] if action == "decide" else payload.get("decisions")
        value = apply_decisions(value, records, selections)
        # The complete batch validates before the one leased atomic write. A
        # bad later selection cannot persist an earlier approval.
        token = history.write(path, value, base_hash=payload["baseHash"])
    return {"version": 1, "manifest": value, "baseHash": token,
            "classification": classify(value["decisions"], records), "records": records}


def document(response):
    """Disconnected overview and explicit leased batch export; never save files.

    Component-resolved Markdown is shown as text. Full filter-rendered cards and
    live Check belong to the component review integration, not this native file.
    """
    value = response["manifest"]
    classified = classify(value["decisions"], response["records"])
    previous = {row["candidate"]["id"]: row for row in classified["entries"] if row["candidate"] is not None}
    rows, items = [], []

    def text(value):
        return html.escape(str(value), quote=True)

    def changes(before, after):
        rows = []
        for category in ("variables", "teacher"):
            old = dict(before[category])
            new = dict(after[category])
            for key in dict.fromkeys([*old, *new]):
                unchanged = key in old and key in new and old[key] == new[key]
                rows.append('<tr class="{}"><th scope="row">{}: {}</th><td>{}</td><td>{}</td></tr>'.format(
                    "unchanged" if unchanged else "changed", text(category), text(key),
                    text(old.get(key, "(absent)")), text(new.get(key, "(absent)"))))
        return '<table><caption>Was → now: approved snapshot</caption><thead><tr><th>Value</th><th>Was</th><th>Now</th></tr></thead><tbody>' + ''.join(rows) + '</tbody></table>'

    for index, item in enumerate(response["records"]):
        row = previous.get(item["id"])
        entry = row["entry"] if row else None
        state = row["state"] if row else "new"
        status = entry["status"] if entry and state in ("current", "moved") else "undecided"
        number = str(entry["n"]) if entry else "New " + str(index + 1)
        tests = item.get("tests")
        passed = type(tests) is dict and tests.get("passed") is True
        verdict = "Tests pass" if passed else "Tests failed" if type(tests) is dict and tests.get("passed") is False else "Tests not verified"
        # A changed snapshot can be reapproved in bulk only when its answer
        # mapping is identical, and the current candidate passed actual tests.
        unchanged_answers = bool(entry and dict(entry["snapshot"]["teacher"]) == dict(item["snapshot"]["teacher"]))
        items.append({"id": item["id"], "hash": item["hash"], "state": state, "status": status,
                      "passed": passed, "answersUnchanged": unchanged_answers, "number": number,
                      "previousStatus": entry["status"] if entry else None})
        options = item.get("data", {}).get("options", {})
        preview = '<details><summary>Student view and solution — {}</summary><p>Resolved Markdown text preview; this file does not run the exercise.</p><h3>Student view</h3><pre>{}</pre><h3>Worked solution</h3><pre>{}</pre><h3>Variables</h3><pre>{}</pre><h3>Test details</h3><pre>{}</pre>{}</details>'.format(
            text(number), text(options.get("question", "No student preview supplied by the component.")),
            text(options.get("solution", "No worked solution supplied by the component.")),
            text(json.dumps(item["snapshot"]["variables"], ensure_ascii=False, indent=2)),
            text(json.dumps(item["tests"], ensure_ascii=False, indent=2)),
            changes(entry["snapshot"], item["snapshot"]) if state == "changed" else "")
        teacher = '<dl>' + ''.join('<dt>{}</dt><dd><code>{}</code></dd>'.format(text(key), text(answer)) for key, answer in item["snapshot"]["teacher"]) + '</dl>'
        rows.append('<tr data-index="{i}" data-needs="{needs}"><th scope="row">{number}</th><td>{state}; {status}<span class="pending"></span></td><td><code>{note}</code>{preview}</td><td>{teacher}</td><td>{verdict}</td><td><button type="button" data-index="{i}" data-status="approved" {disabled}>Approve {number}</button> <button type="button" data-index="{i}" data-status="rejected">Reject {number}</button><label>Reason for {number}<input data-reason="{i}"></label></td></tr>'.format(
            i=index, needs=str(status == "undecided").lower(), number=text(number), state=text(state), status=text(status),
            note=text(item["note"]), preview=preview, teacher=teacher, verdict=verdict, disabled="" if passed else "disabled"))
    counts = {name: sum(item["state"] == name for item in items) for name in ("new", "changed", "current", "moved")}
    counts["gone"] = sum(row["state"] == "gone" for row in classified["entries"])
    data = json.dumps({"baseHash": response["baseHash"], "label": value["question"], "records": response["records"],
                       "items": items}, ensure_ascii=True).replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")
    return '''<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Variant review</title>
<style>body{font:1rem system-ui;line-height:1.5;margin:1.5rem;max-width:90rem}table{border-collapse:collapse;width:100%}th,td{border:1px solid #aaa;padding:.5rem;text-align:left;vertical-align:top}button,input{font:inherit;margin:.2rem}pre{white-space:pre-wrap;overflow-wrap:anywhere}label{display:block}.unchanged{color:#666}.pending{font-weight:bold}button:focus-visible,input:focus-visible,summary:focus-visible{outline:3px solid #146bb5}dl{margin:0}dd{margin-left:0}code{overflow-wrap:anywhere}details table{width:auto}</style>
<h1>Variant review: ''' + text(value["question"]) + '''</h1><p>Disconnected review: stage choices, download one decision request, then apply it with the native CLI. Nothing is saved by this page. Reloading discards choices that have not been applied.</p>
<p id="overview">''' + text(' · '.join('{} {}'.format(count, state) for state, count in counts.items())) + '''</p>
<p><label>Project root <input id="root" required></label> <label>Manifest path <input id="path" required></label></p>
<p><label><input type="checkbox" id="problems" checked>Show only variants needing a decision</label>
<button type="button" id="bulk">Approve all passing variants of this question</button>
<button type="button" id="again">Approve again: changed, answers unchanged</button>
<button type="button" id="undo" disabled>Undo last staged action</button>
<button type="button" id="download" disabled>Download decision request</button></p>
<table><caption>Candidate overview — teacher answers in canonical input notation</caption><thead><tr><th>Number</th><th>Status</th><th>Note and preview</th><th>Teacher answers</th><th>Tests</th><th>Decision</th></tr></thead><tbody>''' + ''.join(rows) + '''</tbody></table>
<p role="status" aria-live="polite" id="status">No staged decisions.</p><script>
const base=''' + data + ''';
let pending=new Map();const undo=[];
const status=document.getElementById('status');
function refresh(message){
 document.querySelectorAll('tr[data-index]').forEach(row=>{const choice=pending.get(Number(row.dataset.index));row.querySelector('.pending').textContent=choice?' → '+choice.status+' (staged)':'';row.hidden=document.getElementById('problems').checked&&row.dataset.needs!=='true'&&!choice;});
 document.getElementById('undo').disabled=!undo.length;document.getElementById('download').disabled=!pending.size;
 status.textContent=message||pending.size+' staged decision(s); nothing saved.';
}
function stage(selections,message){
 if(!selections.length){refresh(message||'No eligible passing variants.');return;}
 undo.push(new Map(pending));selections.forEach(([index,status])=>pending.set(index,{id:base.items[index].id,hash:base.items[index].hash,status,reason:status==='rejected'?document.querySelector('[data-reason="'+index+'"]').value:''}));refresh(message);
}
document.querySelectorAll('button[data-index]').forEach(button=>button.addEventListener('click',()=>stage([[Number(button.dataset.index),button.dataset.status]])));
document.getElementById('problems').addEventListener('change',()=>refresh());
document.getElementById('bulk').addEventListener('click',()=>{
 const selected=base.items.flatMap((item,index)=>item.passed&&item.previousStatus!=='rejected'&&pending.get(index)?.status!=='rejected'?[[index,'approved']]:[]);
 const excluded=base.items.filter(item=>!item.passed).map(item=>item.number);
 stage(selected,selected.length+' passing variant(s) staged. Not approved because tests did not pass: '+(excluded.join(', ')||'none')+'. Nothing saved. Existing rejections are preserved.');
});
document.getElementById('again').addEventListener('click',()=>stage(base.items.flatMap((item,index)=>item.state==='changed'&&item.previousStatus!=='rejected'&&item.answersUnchanged&&item.passed&&pending.get(index)?.status!=='rejected'?[[index,'approved']]:[])));
document.getElementById('undo').addEventListener('click',()=>{if(undo.length){pending=undo.pop();refresh('Last staged action undone. '+pending.size+' staged decision(s); nothing saved.');}});
document.getElementById('download').addEventListener('click',()=>{
 const root=document.getElementById('root'),path=document.getElementById('path');
 if(!root.reportValidity()||!path.reportValidity()||!pending.size)return;
 const request={version:1,action:'decide-many',projectRoot:root.value,manifest:path.value,label:base.label,baseHash:base.baseHash,records:base.records,decisions:[...pending.values()]};
 const url=URL.createObjectURL(new Blob([JSON.stringify(request,null,2)+'\\n'],{type:'application/json'}));
 const link=document.createElement('a');link.href=url;link.download='variant-decisions.json';link.click();setTimeout(()=>URL.revokeObjectURL(url),1000);
 status.textContent=pending.size+' decision(s) downloaded; nothing saved. Apply with the native CLI, then regenerate this review before another download. The baseHash lease rejects stale writes.';
});
refresh();</script></html>'''
