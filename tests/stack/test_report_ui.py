"""The compliance report's pages in a browser, with synthetic observations.

Moved from stack-sympy's tests/browser.py with the report (consolidation step
2): the real report pages (reports/stack-compliance, rendered by Quarto) with
saved observations; real runner observations are checked by native-stack.yml.
Needs Quarto and Playwright with Chromium (STACK_SYMPY_CHROMIUM names another
Chromium); skipped without them. native-stack.yml runs it after the report.
"""
from __future__ import annotations

from contextlib import contextmanager
from functools import cache, partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
from threading import Thread

import pytest

ROOT = Path(__file__).resolve().parents[2]
REPORT = ROOT / "reports/stack-compliance"
sys.path.insert(0, str(ROOT / "tools/stack_native"))

sync_playwright = pytest.importorskip("playwright.sync_api").sync_playwright
QUARTO = os.environ.get("QUARTO", "quarto")
if not shutil.which(QUARTO):
    pytest.skip("the report pages are rendered by Quarto", allow_module_level=True)


@contextmanager
def serve(directory: Path):
    class QuietHandler(SimpleHTTPRequestHandler):
        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), partial(QuietHandler, directory=str(directory)))
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}"
    finally:
        server.shutdown()
        thread.join(timeout=5)
        server.server_close()


@cache
def render_report_shell(name):
    """Render the actual report page instead of slicing its HTML at a marker."""
    with tempfile.TemporaryDirectory(prefix="stack_report_render_") as temporary:
        project = Path(temporary)
        (project / "_quarto.yml").write_text("project:\n  type: default\nfilters: []\n")
        (project / "test.qmd").write_text((REPORT / f"{name}.qmd").read_text())
        result = subprocess.run([QUARTO, "render"], cwd=project, text=True,
                                capture_output=True, timeout=90)
        assert result.returncode == 0, result.stdout + result.stderr
        return (project / "test.html").read_text()


def write_report(tmp_path, ordinals):
    """The real report page with synthetic saved observations of the cases (by ordinal)."""
    fixture = json.loads((ROOT/'tests/stack/native_compliance/fixtures.json').read_text())
    policy = json.loads((ROOT/'tests/stack/native_compliance/policy.json').read_text())
    rows = []
    for ordinal in ordinals:
        case = next(c for c in fixture['cases'] if c['ordinal'] == ordinal)
        entry = policy['cases'][case['id']]
        observed = {'kind':'result','valid':True,'cas_valid':True,'correct':False}
        rows.append({**case, 'discussion':entry['discussion'],
            'python':{**observed,'reason':entry['reason'],
                      'desired':{'kind':'result','correct':True}},
            'native':{'status':'ok','cas_valid':True,'correct':ordinal == 50},
            'parity':{'python':observed,'pyodide':observed},
            'desired_status':'known_defect',
            'native_status':'known_port_defect' if ordinal == 50 else 'match',
            'native_mark_status':'mismatch' if ordinal == 50 else 'match',
            'native_applicability_status':'match','native_desired_status':'matches_desired',
            'parity_status':'match'})
    report = {'cases':rows,'summary':{'desired':{'known_defect':len(rows)}},
              'results':{'python':{'passed':True},'compatibility':{'passed':True}},
              'provenance':{'code_sha':'0'*40},'scope':'synthetic UI fixture'}
    (tmp_path/'report.json').write_text(json.dumps(report))
    for name in ('report-ui.js','report.js'):
        (tmp_path/name).write_text((REPORT/name).read_text())
    (tmp_path/'index.html').write_text(render_report_shell('index'))
    return rows


def chromium_options():
    options = {'headless':True}
    if os.environ.get('STACK_SYMPY_CHROMIUM'):
        options['executable_path'] = os.environ['STACK_SYMPY_CHROMIUM']
    return options


def test_browser_legacy_report_explains_differences_without_marking_pass(tmp_path):
    """Synthetic saved observations exercise the real report presentation."""
    rows = write_report(tmp_path, (50, 471))
    with serve(tmp_path) as url, sync_playwright() as pw:
        browser = pw.chromium.launch(**chromium_options())
        page = browser.new_page()
        page.goto(url+'/index.html')
        page.locator('#case-list .case').first.wait_for()
        for category in ('domain_review', 'proof_limitation'):
            page.locator('#desired-filter').select_option(category)
            assert page.locator('#case-list .case').count() == 1
            page.locator('#case-list .case summary').first.click()
            discussion = page.locator('.case-discussion')
            assert discussion.is_visible()
            assert 'Question for STACK:' in discussion.inner_text()
            assert discussion.locator('a[href^="https://github.com/maths/moodle-qtype_stack/"]').count() > 0
            outcomes = page.locator('.outcome-table').inner_text()
            assert 'Accept' in outcomes and 'Reject' in outcomes
        assert [r['desired_status'] for r in rows] == ['known_defect','known_defect']
        browser.close()


def test_browser_project_regression_report_keeps_suites_separate(tmp_path):
    """UI fixture only: real runner observations are checked by the CI job."""
    from native_compliance.port_contract import load_fixture, assemble as port_assemble
    cases = load_fixture(ROOT / 'tests/stack/port_regressions/fixtures.json')
    python = [{'case_id':c['id'],'test':c['test'],**c.get('known_defect',{}).get('observation',c['expected'])} for c in cases]
    native = {'observations':[{'case_id':c['id'],'status':'ok',**c.get('native_expected',
              {k:c['expected'][k] for k in ('cas_valid','correct')})} for c in cases if c['native_scope']]}
    parity = {'cases':[{'id':c['id'],'match':True} for c in cases]}
    project = port_assemble(cases,python,native,parity)
    project.update(available=True,provenance={'fixture':'synthetic UI test'},runners={})
    (tmp_path/'port-regressions.json').write_text(json.dumps(project))
    (tmp_path/'report-ui.js').write_text((REPORT/'report-ui.js').read_text())
    (tmp_path/'port-regressions.js').write_text((REPORT/'port-regressions.js').read_text())
    (tmp_path/'index.html').write_text(render_report_shell('port-regressions'))
    with serve(tmp_path) as url, sync_playwright() as pw:
        options = {'headless':True}
        if os.environ.get('STACK_SYMPY_CHROMIUM'):
            options['executable_path'] = os.environ['STACK_SYMPY_CHROMIUM']
        browser = pw.chromium.launch(**options)
        page = browser.new_page()
        page.goto(url+'/index.html')
        page.locator('#port-regressions-list .case').first.wait_for()
        assert page.locator('#port-regressions-list .case').count()==len(cases)
        assert page.locator('#report-provenance').count()==0
        for axis in ('port_result', 'stack_result', 'browser_result'):
            assert page.locator(f'#{axis}-filter').count() == 1
        # Known issues and input boundaries must be independently filterable.
        for status in ('pass', 'boundary_pass'):
            page.locator('#port_result-filter').select_option(status)
            assert page.locator('#port-regressions-list .case').count() == sum(
                row['python_status'] == status for row in project['cases'])
        page.locator('#clear-filters').click()
        selected = next(c for c in cases if c['id']=='port-complex-root-form')
        page.locator('#port-search').fill(selected['id'])
        assert page.locator('#port-regressions-list .case').count()==1
        page.locator('#port-regressions-list .case').first.locator('summary').first.click()
        raw = page.locator('#port-regressions-list .case-body > .technical-details')
        raw.locator('summary').first.click()
        for detail in raw.locator('details').all():
            detail.locator('summary').click()
        origin = raw.locator('pre').all_text_contents()
        assert any(json.loads(text).get('origin') == selected['origin'] for text in origin)
        page.locator('#port-search').fill('')
        page.locator('#port-group').select_option('declared boundaries')
        assert page.locator('#port-regressions-list .case').count()==sum(c['group']=='declared boundaries' for c in cases)
        browser.close()


def test_browser_report_presents_no_question_where_there_is_none(tmp_path):
    """Case 477 (atan(1/2)) fails in STACK's own fixtures too: its discussion has no question for STACK."""
    write_report(tmp_path, (477,))
    with serve(tmp_path) as url, sync_playwright() as pw:
        browser = pw.chromium.launch(**chromium_options())
        page = browser.new_page()
        page.goto(url+'/index.html')
        page.locator('#case-list .case').first.wait_for()
        page.locator('#case-list .case summary').first.click()
        discussion = page.locator('.case-discussion')
        assert discussion.is_visible()
        text = discussion.inner_text()
        assert 'Question for STACK' not in text and 'None for STACK' not in text
        assert 'expected mathematical failure' in page.locator('.case-explanation').inner_text()
        assert discussion.locator('a[href^="https://github.com/maths/moodle-qtype_stack/"]').count() > 0
        browser.close()
