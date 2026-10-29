"""contracts/stages.json is the one stage list: runner, run_demo.sh, API and UI use the same ids, labels and steps."""

import re
from pathlib import Path

from contracts import stages
from contracts.stages import STAGES, STEPS

REPO = Path(__file__).resolve().parent.parent


def test_order_is_detect_then_proof_chain_then_the_rest():
    assert [s["id"] for s in STAGES] == ["detect", "ledger", "schedule", "capture", "gates", "qaoa", "seal", "report"]
    assert STAGES[1]["label"] == "Proof Chain"  # UI name only; code and API keep "ledger"
    assert STEPS[:3] == ("detect", "ledger_open", "schedule")
    assert all(s["plain"] and s["label"] and s["steps"] for s in STAGES)
    assert len(set(STEPS)) == len(STEPS)


def test_generated_js_is_in_sync():
    assert stages.main(["--check-js"]) == 0


def test_run_demo_runs_the_same_steps_in_order():
    sh = (REPO / "run_demo.sh").read_text()
    assert tuple(re.findall(r"^step (\w+)", sh, re.M)) == STEPS


def test_runner_matches():
    from atlas_web.runner import STEPS as RUNNER_STEPS

    assert tuple(RUNNER_STEPS) == STEPS


def test_api_serves_the_stages(monkeypatch, tmp_path):
    from .atlas_web_helpers import Client, start_server

    srv = start_server(monkeypatch, tmp_path)
    try:
        status, body = Client(srv.server_address[1]).get("/api/stages")
        assert status == 200 and body["stages"] == STAGES
    finally:
        srv.shutdown()
