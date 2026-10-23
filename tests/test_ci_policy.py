"""CI scheduling contracts; broad assertions remain in their original workflows."""
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = ROOT / ".github" / "workflows"
PHRASE = "broad testing campaign"


def workflows():
    # BaseLoader preserves the YAML key `on` rather than reading it as a bool.
    return {path.name: yaml.load(path.read_text(), Loader=yaml.BaseLoader)
            for path in WORKFLOWS.glob("*.yml")}


def test_only_default_tests_run_automatically():
    for name, workflow in workflows().items():
        events = workflow["on"]
        if name == "test.yml":
            assert set(events) == {"push", "pull_request", "workflow_dispatch"}
            assert events["push"]["branches"] == ["main"]
        else:
            expected = {"workflow_dispatch", "workflow_call"} if name == "native-stack.yml" else {"workflow_dispatch"}
            assert set(events) == expected


def test_manual_campaign_requires_literal_confirmation_outside_shell_code():
    for name, workflow in workflows().items():
        inputs = workflow["on"]["workflow_dispatch"]["inputs"]
        assert inputs["confirmation"]["required"] == "true"
        assert inputs["confirmation"]["type"] == "string"
        job = workflow["jobs"]["python" if name == "test.yml" else "authorize"]
        step = next(step for step in job["steps"] if "CONFIRMATION" in step.get("env", {}))
        assert step["env"]["CONFIRMATION"] == "${{ inputs.confirmation }}"
        assert 'test "$CONFIRMATION" = ' + repr(PHRASE) in step["run"]
        assert "${{" not in step["run"]


def test_default_gate_keeps_full_source_wheel_and_release_checks():
    job = workflows()["test.yml"]["jobs"]["python"]
    assert job["name"] == "Python ${{ matrix.python }}"
    matrix = job["strategy"]["matrix"]["python"]
    assert "github.event_name == 'workflow_dispatch'" in matrix
    assert "inputs.confirmation == 'broad testing campaign'" in matrix
    assert "'[\"3.9\",\"3.10\",\"3.11\",\"3.12\",\"3.13\"]' || '[\"3.12\"]'" in matrix
    steps = {step.get("name"): step for step in job["steps"]}
    assert steps["Tests (src/)"]["run"] == "pytest -q tests"
    wheel = steps["Tests (the built wheels)"]
    assert "CTM_CHECKERS_WHEEL=" in wheel["run"] and "pytest -q tests" in wheel["run"]
    for name in ["Tests (src/)", "Tests (the built wheels)",
                 "The generated extension folder matches src/; the releases of the base branch are unchanged",
                 "The wheels install with pip"]:
        assert "if" not in steps[name]
    assert steps["A pull request that changes golden rows follows the rules of grading changes (H2, names, version, CHANGELOG)"]["if"] == "github.event_name == 'pull_request'"


def test_goldens_mutations_and_duplicate_matrices_are_manual_only():
    data = workflows()
    steps = data["test.yml"]["jobs"]["python"]["steps"]
    broad = [step for step in steps if "golden.py verify" in step.get("run", "")
             or "CTM_MUTATION_TESTS=1" in step.get("run", "")]
    assert len(broad) == 3
    for step in broad:
        assert step["if"] == "github.event_name == 'workflow_dispatch' && inputs.confirmation == 'broad testing campaign'"
    for name, workflow in data.items():
        if name in {"test.yml", "native-stack.yml"}:
            continue
        for job_name, job in workflow["jobs"].items():
            if job_name != "authorize":
                assert job["needs"] == "authorize"


def test_native_reusable_contract_and_failure_report_dependencies_remain():
    native = workflows()["native-stack.yml"]
    assert native["on"]["workflow_call"]["inputs"] == {
        "ctm-checkers-ref": {"description": "The ctm-checkers commit to check (the caller's pin)",
                             "required": "true", "type": "string"}}
    jobs = native["jobs"]
    authorization = jobs["authorize"]["steps"][0]
    assert authorization["env"]["CALLER_REF"] == "${{ inputs.ctm-checkers-ref }}"
    assert 'if [ -n "$CALLER_REF" ]' in authorization["run"]
    for name, job in jobs.items():
        if name == "authorize":
            continue
        assert "authorize" in job["needs"]
        if "always()" in job.get("if", ""):
            assert "needs.authorize.result == 'success'" in job["if"]
    assert set(jobs["report"]["needs"]) == {"authorize", "desired", "native", "reference", "parity", "port-regressions"}
    assert any(step.get("with", {}).get("name") == "native-compliance-html"
               for step in jobs["report"]["steps"])
