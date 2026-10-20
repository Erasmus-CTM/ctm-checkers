"""Run probe answer-test cases through the port (CPython) and pinned native STACK/Maxima.

Usage: python tools/stack_native/dual.py cases.json out.json
cases.json: [[test, student, teacher, options], ...]

The stack-sympy audit's probes/dual.py (ctm-assessment
docs/consolidation/stack-sympy-audit-2026-10/probes), with ctm_checkers.stack
for stack-sympy's engine: the native oracle for fix pull requests (design §9).
"""
import hashlib, json, os, sys, time
from pathlib import Path
# STACK_UPSTREAM: STACK at 10d3233; STACK_NATIVE_IMAGE: the Maxima 5.46 (GCL)
# image that prepare_native_image.py builds.
ROOT = Path(__file__).resolve().parents[2]
sys.path.append(str(ROOT / 'src'))  # ctm_checkers from src/ unless one is importable (a wheel)
sys.path.insert(0, str(ROOT / 'tools/stack_native'))
from ctm_checkers.stack.assessment import answer_test
from native_compliance.maxima_runner import run_native

def port(test, s, t, o):
    t0 = time.time()
    try:
        r = answer_test(test, s, t, o, raw=s)
        out = {k: r.get(k) for k in ("valid", "correct", "cas_valid", "note", "feedback") if k in r}
    except Exception as e:
        out = {"exception": f"{type(e).__name__}: {e}"}
    out["seconds"] = round(time.time() - t0, 3)
    return out

def main():
    raw = json.loads(Path(sys.argv[1]).read_text())
    cases = []
    for i, (test, s, t, o) in enumerate(raw, 1):
        h = hashlib.sha256(json.dumps([test, s, t, o]).encode()).hexdigest()
        cases.append({"id": f"{h}-{i}", "test": test, "student": s, "teacher": t, "options": o, "ordinal": i})
    native = run_native(cases, Path(os.environ['STACK_UPSTREAM']), jobs=2, timeout=300, image=Path(os.environ['STACK_NATIVE_IMAGE']))
    by = {o["case_id"]: o for o in native["observations"]}
    rows = []
    for c in cases:
        rows.append({"test": c["test"], "student": c["student"], "teacher": c["teacher"], "options": c["options"],
                     "port": port(c["test"], c["student"], c["teacher"], c["options"]), "native": by[c["id"]]})
    Path(sys.argv[2]).write_text(json.dumps(rows, indent=1))
    for r in rows:
        p, n = r["port"], r["native"]
        pv = "EXC" if "exception" in p else ("INVALID" if not p.get("valid") else str(p.get("correct")))
        nv = n.get("status") if n.get("status") != "ok" else str(n.get("correct")) + ("" if n.get("cas_valid") else "/invalid")
        flag = "" if pv == nv.split("/")[0] else "  <== DIFF"
        print(f"{r['test']:12s} {r['student']:24s} | {r['teacher']:22s} | {r['options']:5s} port={pv:8s} native={nv:14s} note={n.get('answer_note','')!r}{flag}")

main()
