import json
import subprocess
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
GATE_SCRIPT = REPO_ROOT / "scripts" / "qa" / "notice-parity-gates.mjs"


def run_gate(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["node", str(GATE_SCRIPT), *args],
        cwd=REPO_ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )


def parse_gate_output(result: subprocess.CompletedProcess[str]) -> dict:
    payload = result.stdout if result.returncode == 0 else result.stderr
    try:
        return json.loads(payload)
    except json.JSONDecodeError as exc:
        raise AssertionError(f"Gate output is not JSON.\nstdout={result.stdout}\nstderr={result.stderr}") from exc


def assert_gate_passes(command: str):
    result = run_gate(command)
    payload = parse_gate_output(result)
    assert result.returncode == 0, payload
    assert payload["ok"] is True


def test_gate_0_contract_snapshot_is_present_and_complete():
    assert_gate_passes("contract")


def test_dom_contract_matches_required_sentrix_ids_actions_and_assets():
    assert_gate_passes("dom")


def test_notice_css_is_scoped_to_sentrix_workspace():
    assert_gate_passes("css")


def test_notice_runtime_files_are_sentrix_data_independent():
    assert_gate_passes("data")


def test_announcements_backend_facade_and_services_exist():
    assert_gate_passes("backend")


def test_legacy_arls_notice_renderer_has_explicit_closure_evidence():
    assert_gate_passes("legacy")


def test_announcement_workspace_diff_has_only_classified_supported_differences():
    assert_gate_passes("module-diff")
