"""Review existing native proposals through the same leased manifest writer."""
import html
import json
import re
import xml.etree.ElementTree as ET
from pathlib import Path

from ctm_variants import history
from ctm_variants.model import VariantError, classify, digest
from ctm_variants.rejection_hint import rejection_hint


def teacher_display(value):
    """Validate a component's optional presentation, never its answer value.

    The exact teacher/input stays in the canonical snapshot. This accepts only
    a small MathML presentation vocabulary; printer output is not trusted HTML.
    """
    if (type(value) is not dict or set(value) != {"mathml", "latex"}
            or not all(isinstance(value[key], str) for key in value)
            or not 0 < len(value["mathml"]) <= 65536 or len(value["latex"]) > 65536):
        return None
    source = value["mathml"]
    if "<!" in source or "<?" in source:
        return None
    # SymPy uses named HTML entities such as &pi;. XML must see numeric
    # references, without unescaping < or & into executable markup.
    def entity(match):
        name = match[1] + ";"
        if name not in html.entities.html5:
            raise ValueError("unknown MathML entity")
        return "".join("&#{};".format(ord(char)) for char in html.entities.html5[name])
    try:
        source = re.sub(r"&([A-Za-z][A-Za-z0-9]+);", entity, source)
        root = ET.fromstring(source)
    except (ET.ParseError, ValueError):
        return None
    namespace = "http://www.w3.org/1998/Math/MathML"
    tags = set("math mrow mi mn mo mtext ms mfrac msqrt mroot msup msub msubsup munder mover munderover mtable mtr mtd mstyle mspace mfenced".split())
    attributes = set("display mathvariant stretchy fence separator linethickness columnalign rowalign rowspacing columnspacing width height depth accent accentunder open close separators".split())
    pending, count = [(root, 0)], 0
    while pending:
        node, depth = pending.pop()
        count += 1
        if not isinstance(node.tag, str) or depth > 64 or count > 1024:
            return None
        if node.tag.startswith("{"):
            uri, tag = node.tag[1:].split("}", 1)
            if uri != namespace:
                return None
        else:
            tag = node.tag
        if tag not in tags or any(key not in attributes or len(raw) > 64 for key, raw in node.attrib.items()):
            return None
        if tag == "mfenced":
            # Chromium implements MathML Core, which uses explicit operators.
            children = list(node)
            opening, closing = node.get("open", "("), node.get("close", ")")
            separators = node.get("separators", ",").replace(" ", "")
            node.clear()
            start = ET.SubElement(node, "mo"); start.text = opening
            for index, child in enumerate(children):
                if index and separators:
                    separator = ET.SubElement(node, "mo")
                    separator.text = separators[min(index - 1, len(separators) - 1)]
                node.append(child)
            end = ET.SubElement(node, "mo"); end.text = closing
            tag = "mrow"
        node.tag = "{" + namespace + "}" + tag
        pending.extend((child, depth + 1) for child in node)
    if root.tag != "{" + namespace + "}math":
        return None
    latex = value["latex"]
    if (any(ord(char) < 32 or char in "<>$`" for char in latex)
            or re.search(r"\\(?:href|url|html[A-Za-z]*|class|style|cssId|includegraphics|input|include|write|openout|read|csname|catcode|def|gdef|edef|newcommand|renewcommand|require)\b", latex)):
        # The native MathML can remain useful when Markdown math is unsuitable.
        latex = ""
    ET.register_namespace("", namespace)
    return {"mathml": ET.tostring(root, encoding="unicode", short_empty_elements=False), "latex": latex}


def card_id(locator):
    """Stable safe anchor shared by canonical review HTML and artifact links."""
    if not isinstance(locator, str) or not locator:
        raise VariantError("preview card requires a candidate locator")
    return "variant-" + digest(locator)


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
        if item is None and selected["status"] == "rejected":
            value = history.retire(value, records, selected["id"], selected["hash"],
                by=selected.get("by", ""), date=selected.get("date", ""), reason=selected.get("reason", ""))
            continue
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


def document(response, *, connected_endpoint=None, student_previews=None, teacher_displays=None, github_context=None, workflow_context=None, language="en"):
    """Overview with disconnected export or an explicit local connected endpoint.

    Component-resolved Markdown is shown as text. Full filter-rendered cards and
    live Check belong to the component review integration, not this native file.
    """
    generate_text = {
        "en": {"saved": "Generation saved. Rebuilding review…", "button": "Generate 25 more", "working": "Generating up to 25 more proposals…", "done": "Generation saved. Review rebuilt from current source and manifest.", "failed": "Generation not confirmed: ", "retry": "Rebuild review before trying again.", "rebuild": "Rebuild review"},
        "de": {"saved": "Generierung gespeichert. Die Übersicht wird neu erstellt…", "button": "25 weitere generieren", "working": "Bis zu 25 weitere Vorschläge werden generiert…", "done": "Generierung gespeichert. Die Übersicht wurde aus aktueller Quelle und Manifest neu erstellt.", "failed": "Generierung nicht bestätigt: ", "retry": "Vor einem weiteren Versuch die Übersicht neu erstellen.", "rebuild": "Übersicht neu erstellen"},
        "nb": {"saved": "Genereringen er lagret. Bygger oversikten på nytt…", "button": "Generer 25 til", "working": "Genererer opptil 25 nye forslag…", "done": "Genereringen er lagret. Oversikten er bygd på nytt fra gjeldende kilde og manifest.", "failed": "Genereringen er ikke bekreftet: ", "retry": "Bygg oversikten på nytt før du prøver igjen.", "rebuild": "Bygg oversikten på nytt"},
    }
    if language not in generate_text:
        raise VariantError("review language must be en, de or nb")
    if connected_endpoint is not None:
        import re
        if not isinstance(connected_endpoint, str) or not re.fullmatch(r"/[A-Za-z0-9_-]{40,}/", connected_endpoint):
            raise VariantError("connected review requires a token-bound local route")
    if workflow_context is not None:
        if (github_context is None or type(workflow_context) is not dict or set(workflow_context) != {"pullRequest", "label"}
                or type(workflow_context["pullRequest"]) is not int or workflow_context["pullRequest"] < 1
                or workflow_context["label"] != response["manifest"]["question"]):
            raise VariantError("workflow generation instructions require a verified PR and question")
    if github_context is not None:
        import re
        if (type(github_context) is not dict or set(github_context) != {"repository", "branch", "path", "head"}
                or any(not isinstance(github_context.get(key), str) for key in ("repository", "branch", "path", "head"))
                or not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", github_context.get("repository", ""))
                or not isinstance(github_context.get("branch"), str) or not github_context["branch"]
                or any(ord(char) < 32 for char in github_context["branch"])
                or not re.fullmatch(r"_variants/[A-Za-z0-9][A-Za-z0-9_.-]{0,127}\.yml", github_context.get("path", ""))
                or ".." in github_context["path"]
                or not re.fullmatch(r"[0-9a-f]{40}", github_context.get("head", ""))):
            raise VariantError("GitHub editor requires explicit repository, branch, manifest path and source head")
    student_previews = {} if student_previews is None else student_previews
    teacher_displays = {} if teacher_displays is None else teacher_displays
    if type(teacher_displays) is not dict:
        raise VariantError("teacher displays must be a candidate mapping")
    if type(student_previews) is not dict:
        raise VariantError("student previews must be a candidate mapping")
    import re
    for candidate_id, previews in student_previews.items():
        if not isinstance(candidate_id, str) or type(previews) is not list:
            raise VariantError("student previews need a candidate id and language list")
        for preview in previews:
            if (type(preview) is not dict or set(preview) != {"language", "url"}
                    or preview.get("language") not in ("en", "de", "nb", "default")
                    or not isinstance(preview.get("url"), str)
                    or not re.fullmatch(r"/[A-Za-z0-9_-]{40,}/previews/[A-Za-z0-9_-]+/" + preview["language"] + r"/index\.html", preview["url"])):
                raise VariantError("student preview requires a token-bound local language route")
    value = response["manifest"]
    classified = classify(value["decisions"], response["records"])
    previous = {row["candidate"]["id"]: row for row in classified["entries"] if row["candidate"] is not None}
    rows, items = [], []

    def text(value):
        return html.escape(str(value), quote=True)

    def answers(snapshot, displays):
        displays = displays if type(displays) is dict else {}
        label = {"en": "Input", "de": "Eingabe", "nb": "Inndata"}[language]
        rows = []
        for field, answer in snapshot["teacher"]:
            display = teacher_display(displays.get(field))
            rendered = ('<span class="teacher-math">' + display["mathml"] + '</span>') if display else ''
            rows.append('<dt>{}</dt><dd>{}<span class="teacher-input">{}: <code>{}</code></span></dd>'.format(
                text(field), rendered, text(label), text(answer)))
        return '<dl>' + ''.join(rows) + '</dl>'

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
        for student in student_previews.get(item["id"], []):
            title = "Student view — " + ("Default question" if student["language"] == "default" else student["language"])
            preview += ('<details data-student-preview><summary>{title}</summary>'
                        '<p><a href="{url}" target="_blank" rel="noopener noreferrer">Open {title}</a></p>'
                        '<iframe data-src="{url}" title="{title}" loading="lazy" '
                        'style="width:100%;height:32rem;border:1px solid #aaa"></iframe></details>').format(
                            title=text(title), url=text(student["url"]))
        teacher = answers(item["snapshot"], teacher_displays.get(item["id"], item.get("teacherDisplay", {})))
        rows.append('<tr id="{anchor}" data-index="{i}" data-needs="{needs}"><th scope="row">{number}</th><td>{state}; {status}<span class="pending"></span></td><td><code>{note}</code>{preview}</td><td>{teacher}</td><td>{verdict}</td><td><button type="button" data-index="{i}" data-status="approved" {disabled}>Approve {number}</button> <button type="button" data-index="{i}" data-status="rejected">Reject {number}</button><label>Reason for {number}<input data-reason="{i}"></label></td></tr>'.format(
            anchor=card_id(item["id"]), i=index, needs=str(status == "undecided").lower(), number=text(number), state=text(state), status=text(status),
            note=text(item["note"]), preview=preview, teacher=teacher, verdict=verdict, disabled="" if passed else "disabled"))
    for missing in classified["entries"]:
        entry = missing["entry"]
        if missing["state"] != "gone" or entry["status"] != "approved":
            continue
        index = len(items)
        retained = any(proposal["record"]["id"] == entry["id"] and proposal["record"]["hash"] == entry["hash"]
                       and all(proposal["record"]["snapshot"][key] == entry["snapshot"][key]
                               for key in ("math", "teacher", "grading")) for proposal in value["proposals"])
        number = "Variant " + str(entry["n"])
        items.append(dict(id=entry["id"], hash=entry["hash"], state="gone", status="approved", passed=False,
                          answersUnchanged=False, number=number, previousStatus="approved", absent=True))
        snapshot_view = '<details><summary>Retained approved snapshot — {}</summary><pre>{}</pre></details>'.format(
            text(number), text(json.dumps(entry["snapshot"], ensure_ascii=False, indent=2)))
        teacher = '<dl>' + ''.join('<dt>{}</dt><dd><code>{}</code></dd>'.format(text(key), text(answer))
                                  for key, answer in entry["snapshot"]["teacher"]) + '</dl>'
        action = ('<button type="button" data-index="{i}" data-status="rejected">Retire missing {number}</button>'
                  '<label>Reason for retiring {number}<input data-reason="{i}" required></label>').format(i=index, number=text(number)) if retained else 'Retained proposal is missing; native repair is required.'
        rows.append('<tr id="{anchor}" data-index="{i}" data-needs="true"><th scope="row">{number}</th>'
                    '<td>gone; approved<span class="pending"></span></td><td><code>{note}</code>{snapshot}</td>'
                    '<td>{teacher}</td><td>Absent from current source; approval is unavailable.</td><td>{action}</td></tr>'.format(
                        anchor=card_id(entry["id"]), i=index, number=text(number), note=text(entry.get("note", "")),
                        snapshot=snapshot_view, teacher=teacher, action=action))
    counts = {name: sum(item["state"] == name for item in items) for name in ("new", "changed", "current", "moved")}
    counts["gone"] = sum(row["state"] == "gone" for row in classified["entries"])
    hint = rejection_hint(value["decisions"])
    hint_html = ""
    if hint:
        hint_html = ('<aside class="variant-rejection-hint" role="note"><p>Authoring hint: {} of {} decided variants were rejected. '
            'Consider a <code>require(...)</code> condition so these cases are not proposed. '
            'No condition is applied automatically.</p><p>Rejection reasons:</p><ul>{}</ul>').format(
                hint["rejected"], hint["decided"], ''.join('<li>' + text(reason) + '</li>' for reason in hint["reasons"]))
        if hint["suggestions"]:
            hint_html += '<p>Shared rejected values absent from approvals:</p><ul>' + ''.join(
                '<li><code>' + text(suggestion) + '</code></li>' for suggestion in hint["suggestions"]) + '</ul>'
        hint_html += '</aside>'
    data = json.dumps({"baseHash": response["baseHash"], "label": value["question"], "records": response["records"],
                       "manifestJSON": json.dumps(value, ensure_ascii=False, allow_nan=False),
                       "recordsJSON": json.dumps(response["records"], ensure_ascii=False, allow_nan=False),
                       "github": github_context,
                       "workflow": workflow_context,
                       "items": items}, ensure_ascii=True).replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")
    page = '''<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Variant review</title>
<style>body{font:1rem system-ui;line-height:1.5;margin:1.5rem;max-width:90rem}table{border-collapse:collapse;width:100%}th,td{border:1px solid #aaa;padding:.5rem;text-align:left;vertical-align:top}button,input{font:inherit;margin:.2rem}pre{white-space:pre-wrap;overflow-wrap:anywhere}label{display:block}.unchanged{color:#666}.pending{font-weight:bold}button:focus-visible,input:focus-visible,summary:focus-visible{outline:3px solid #146bb5}dl{margin:0}dd{margin-left:0}.teacher-math{display:block;font-size:1.2em;margin:.2rem 0}.teacher-input{display:block}code{overflow-wrap:anywhere}details table{width:auto}</style>
<h1>Variant review: ''' + text(value["question"]) + '''</h1><p>Disconnected review: stage choices, download one decision request, then apply it with the native CLI. Nothing is saved by this page. Reloading discards choices that have not been applied.</p>
<p id="overview">''' + text(' · '.join('{} {}'.format(count, state) for state, count in counts.items())) + '''</p>''' + hint_html + '''
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
 for(const id of ['copy-file','github-editor']){const button=document.getElementById(id);if(button)button.disabled=!pending.size;}
 status.textContent=message||pending.size+' staged decision(s); nothing saved.';
}
function stage(selections,message){
 if(!selections.length){refresh(message||'No eligible passing variants.');return;}
 for(const [index,choice] of selections){
  if(base.items[index].absent&&choice==='rejected'){
   const reason=document.querySelector('[data-reason="'+index+'"]');
   reason.setCustomValidity(reason.value.trim()?'':'Provide a reason for retiring this missing variant.');
   if(!reason.reportValidity()){status.textContent='A reason is required before retiring a missing approved variant.';return;}
  }
 }
 undo.push(new Map(pending));selections.forEach(([index,status])=>pending.set(index,{id:base.items[index].id,hash:base.items[index].hash,status,reason:status==='rejected'?document.querySelector('[data-reason="'+index+'"]').value:''}));refresh(message);
}
document.querySelectorAll('button[data-index]').forEach(button=>button.addEventListener('click',()=>stage([[Number(button.dataset.index),button.dataset.status]])));
document.querySelectorAll('input[data-reason]').forEach(input=>input.addEventListener('input',()=>input.setCustomValidity('')));
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
    if github_context is not None:
        from ctm_variants.browser_manifest import SCRIPT
        exports = r'''<script>
const manifestArea=document.createElement('textarea');manifestArea.readOnly=true;manifestArea.rows=12;manifestArea.style.width='100%';
const manifestLabel=document.createElement('label');manifestLabel.textContent='Complete manifest file (copy all text)';manifestLabel.append(manifestArea);manifestLabel.hidden=true;status.before(manifestLabel);
const copyFile=document.createElement('button');copyFile.type='button';copyFile.id='copy-file';copyFile.textContent='Copy file';
const editor=document.createElement('button');editor.type='button';editor.id='github-editor';editor.textContent='Open in GitHub editor';
status.before(copyFile,editor);
const context=document.createElement('p');context.textContent='GitHub review snapshot: '+base.github.repository+' · '+base.github.branch+' · '+base.github.head+'. Compare the branch file before replacing it; source changes require fresh review. The human Git commit records authorship.';copyFile.before(context);
if(base.workflow){
 const more=document.createElement('p');more.id='github-generate-more';
 const link=document.createElement('a');link.textContent='Generate 25 more with GitHub Actions';link.href='https://github.com/'+base.github.repository+'/actions/workflows/variants.yml';link.target='_blank';link.rel='noopener';
 const inputs=JSON.stringify({pull_request:String(base.workflow.pullRequest),expected_head:base.github.head,generate_more:base.workflow.label},null,2);
 const instructions=document.createElement('pre');instructions.textContent='Use Run workflow on branch '+base.github.branch+' with inputs:\n'+inputs;
 const copyInputs=document.createElement('button');copyInputs.type='button';copyInputs.id='copy-workflow-inputs';copyInputs.textContent='Copy workflow inputs';copyInputs.addEventListener('click',async()=>{try{if(!navigator.clipboard?.writeText)throw Error('Clipboard unavailable; copy the visible inputs.');await navigator.clipboard.writeText(inputs);status.textContent='Workflow inputs copied. Open GitHub Actions and select the stated branch; nothing has been dispatched.';}catch(error){status.textContent=error.message;}});
 const explanation=document.createElement('span');explanation.textContent='This requests supervised tested proposals. It does not save the manifest. Refresh this review after the run, then Copy file or approve proposals to record them. No generation runs in this browser.';
 more.append(link,instructions,copyInputs,explanation);copyFile.before(more);
}
function completeManifest(){
 const content=CTMManifestExport.apply(base.manifestJSON,base.recordsJSON,[...pending.values()]);
 manifestArea.value=content;manifestLabel.hidden=false;return content;
}
copyFile.addEventListener('click',async()=>{
 try{
  const content=completeManifest();
  if(navigator.clipboard?.writeText){await navigator.clipboard.writeText(content);status.textContent='Complete manifest copied. Paste it into the selected branch file and review the Git diff before committing.';}
  else{manifestArea.focus();manifestArea.select();status.textContent='Complete manifest ready. Copy the selected text, then paste it into the GitHub editor.';}
 }catch(error){manifestArea.focus();manifestArea.select();status.textContent='Copy not confirmed: '+error.message+' Copy the complete text manually if available.';}
});
editor.addEventListener('click',()=>{
 try{
  completeManifest();
  const github=base.github,repo=github.repository.split('/').map(encodeURIComponent).join('/'),branch=encodeURIComponent(github.branch);
  const path=github.path.split('/').map(encodeURIComponent).join('/');
  const url=base.baseHash===null?'https://github.com/'+repo+'/new/'+branch+'?filename='+encodeURIComponent(github.path):'https://github.com/'+repo+'/edit/'+branch+'/'+path;
  window.open(url,'_blank','noopener,noreferrer');
  status.textContent='GitHub editor opened. Paste the complete file, compare changes and commit on this branch. This page has not saved repository files.';
 }catch(error){status.textContent='Manifest export failed: '+error.message;}
});
refresh();
</script>'''
        page = page.rsplit('</html>', 1)[0] + '<script>' + SCRIPT + '</script>' + exports + '</html>'
    if student_previews:
        lazy = '''<script>
function loadStudentPreview(details){
 if(!details.matches('details[data-student-preview]')||!details.open)return;
 for(const frame of details.querySelectorAll('iframe[data-src]')){
  frame.src=frame.dataset.src;delete frame.dataset.src;
 }
}
document.addEventListener('toggle',event=>loadStudentPreview(event.target),true);
document.querySelectorAll('details[data-student-preview][open]').forEach(loadStudentPreview);
</script>'''
        page = page.rsplit('</html>', 1)[0] + lazy + '</html>'
    if connected_endpoint is None:
        return page
    endpoint = json.dumps(connected_endpoint)
    bridge = '''<script>
const endpoint=ENDPOINT;
const generationText=GENERATION_TEXT;
const reviewLanguage=REVIEW_LANGUAGE;
const intro=document.querySelector('h1').nextElementSibling;
intro.textContent='Connected local review: each decision is saved through the current-source validator. Rebuild after changing source. This page shows resolved text, not a live exercise.';
for(const id of ['root','path'])document.getElementById(id).closest('p').hidden=true;
for(const id of ['download','undo'])document.getElementById(id).hidden=true;
const rebuild=document.createElement('button');rebuild.textContent=generationText.rebuild;rebuild.lang=reviewLanguage;rebuild.type='button';rebuild.onclick=()=>location.reload();status.before(rebuild);
const generate=document.createElement('button');generate.textContent=generationText.button;generate.lang=reviewLanguage;generate.type='button';generate.id='generate-more';status.before(generate);
let saving=false;
const stageDisconnected=stage;
stage=async function(selections,message){
 if(saving)return;
 stageDisconnected(selections,message);
 if(!pending.size)return;
 await operation({baseHash:base.baseHash,decisions:[...pending.values()]},false);
};
generate.addEventListener('click',()=>operation({action:'generate25more',baseHash:base.baseHash},true));
async function operation(payload,generation){
 if(saving)return;
 saving=true;
 const buttons=[...document.querySelectorAll('button')];buttons.forEach(b=>b.disabled=true);
 status.lang=generation?reviewLanguage:'en';status.textContent=generation?generationText.working:'Saving decisions…';
 try{
  const response=await fetch(endpoint,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)});
  const result=await response.json();
  if(!response.ok||result.saved!==true)throw new Error(result.error||'Unexpected save response.');
  status.textContent=generation?generationText.saved:'Saved. Rebuilding review…';
  try{sessionStorage.setItem(generation?'ctm-review-generated':'ctm-review-saved',location.pathname);}catch{}
  location.reload();
 }catch(error){
  status.textContent=generation?generationText.failed+error.message+' '+generationText.retry:'Save not confirmed: '+error.message+' Rebuild the review before retrying.';
  // A rejected or interrupted response can follow a completed native write.
  // Keep the lease terminal until a fresh GET; never silently retry it.
  rebuild.disabled=false;
 }
}
try{if(sessionStorage.getItem('ctm-review-saved')===location.pathname){sessionStorage.removeItem('ctm-review-saved');status.textContent='Saved. Review rebuilt from the current source and manifest.';}}catch{}
try{if(sessionStorage.getItem('ctm-review-generated')===location.pathname){sessionStorage.removeItem('ctm-review-generated');status.lang=reviewLanguage;status.textContent=generationText.done;}}catch{}
</script>'''.replace('ENDPOINT', endpoint).replace('GENERATION_TEXT', json.dumps(generate_text[language])).replace('REVIEW_LANGUAGE', json.dumps(language))
    if student_previews:
        bridge = bridge.replace('This page shows resolved text, not a live exercise.',
                                'Open Student view to load the component-rendered exercise.')
    return page.rsplit('</html>', 1)[0] + bridge + '</html>'

