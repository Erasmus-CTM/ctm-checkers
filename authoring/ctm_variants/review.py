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
        # The complete batch validates before the one leased atomic write. A
        # bad later selection cannot persist an earlier approval.
        token = history.write(path, value, base_hash=payload["baseHash"])
    return {"version": 1, "manifest": value, "baseHash": token,
            "classification": classify(value["decisions"], records), "records": records}


def document(response):
    """Standalone keyboard-accessible review, exporting explicit leased edits.

    This disconnected file never claims to save to disk. The native CLI applies
    its downloaded request through the same stale-base check.
    """
    value = response["manifest"]
    rows = []
    decisions = {entry["id"]: entry for entry in value["decisions"]}
    for item in response["records"]:
        entry = decisions.get(item["id"])
        status = entry["status"] if entry and entry["hash"] == item["hash"] else "undecided"
        rows.append("<tr><td>{}</td><td>{}</td><td><code>{}</code></td><td>{}</td><td>{}</td></tr>".format(
            html.escape(str(entry["n"]) if entry else "—"), html.escape(status), html.escape(item["note"]),
            html.escape(json.dumps(item["snapshot"]["teacher"], ensure_ascii=False)),
            '<button type="button" data-id="{}" data-hash="{}" data-status="approved">Approve</button> '
            '<button type="button" data-id="{}" data-hash="{}" data-status="rejected">Reject</button>'.format(
                html.escape(item["id"], quote=True), item["hash"], html.escape(item["id"], quote=True), item["hash"])))
    data = json.dumps({"baseHash": response["baseHash"], "label": value["question"],
                      "records": response["records"]}, ensure_ascii=True).replace("<", "\\u003c")
    return '''<!doctype html><html lang="en"><meta charset="utf-8"><title>Variant review</title>
<h1>Variant review</h1><p>Disconnected review: download a decision request, then apply it with the native CLI. Nothing is saved by this page.</p>
<p><label>Project root <input id="root" required></label> <label>Manifest path <input id="path" required></label></p>
<table><caption>Candidate decisions</caption><thead><tr><th>Number</th><th>Status</th><th>Note</th><th>Teacher keys</th><th>Decision</th></tr></thead><tbody>''' + "".join(rows) + '''</tbody></table>
<p role="status" aria-live="polite" id="status"></p><script>
const base=''' + data + ''';
document.querySelectorAll('button[data-id]').forEach(button=>button.addEventListener('click',()=>{
 const root=document.getElementById('root'), path=document.getElementById('path');
 if(!root.reportValidity()||!path.reportValidity())return;
 const reason=button.dataset.status==='rejected'?prompt('Reason for rejection:',''):'';
 if(reason===null)return;
 const request={version:1,action:'decide',projectRoot:root.value,manifest:path.value,label:base.label,baseHash:base.baseHash,records:base.records,
 decision:{id:button.dataset.id,hash:button.dataset.hash,status:button.dataset.status,reason}};
 const url=URL.createObjectURL(new Blob([JSON.stringify(request,null,2)+'\\n'],{type:'application/json'}));
 const a=document.createElement('a');a.href=url;a.download='variant-decision.json';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);
 document.getElementById('status').textContent='Decision request downloaded; apply it with the native CLI, then reload this review before another decision.';
}));</script></html>'''
