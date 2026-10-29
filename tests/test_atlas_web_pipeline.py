"""Full mock_bank pipeline through the atlas_web API in a temp workspace (local only), then a calibration
apply that re-plans and signs the change. The repo's out/, runs/ and keys/ must be unchanged."""

import hashlib
import json
import os
from pathlib import Path

import pytest

from contracts.stages import STEPS as STAGE_STEPS

from .atlas_web_helpers import PASSWORD, Client, sse_events, start_server

REPO = Path(__file__).resolve().parent.parent
STEPS = list(STAGE_STEPS)  # contracts/stages.json


def repo_state():
    files = {}
    for d in ("out", "keys"):
        for p in sorted((REPO / d).rglob("*")) if (REPO / d).exists() else []:
            if p.is_file():
                files[str(p.relative_to(REPO))] = hashlib.sha256(p.read_bytes()).hexdigest()
    runs = sorted(p.name for p in (REPO / "runs").iterdir()) if (REPO / "runs").exists() else []
    return files, runs


@pytest.fixture
def live(monkeypatch, tmp_path):
    if not os.environ.get("QPIAI_OPT_API_KEY"):
        pytest.skip("QPIAI_OPT_API_KEY not set; local QpiAI Opt solves verify the key online")
    from detect.live_probe import openssl_binary

    try:
        openssl_binary()
    except Exception as exc:  # noqa: BLE001
        pytest.skip(f"OpenSSL >= 3.5 with ML-KEM/ML-DSA missing: {exc}")
    assert os.environ.get("QSHIELD_FORBID_PLATFORM") == "1"
    srv = start_server(monkeypatch, tmp_path)
    srv.app.store.create_user("ops", PASSWORD, "operator")
    yield srv
    srv.shutdown()
    srv.server_close()


def run_and_follow(srv, c, path, body):
    status, res = c.post(path, body)
    assert status == 202, res
    evs = sse_events(srv.server_address[1], f"/api/workspaces/bank/runs/{res['run_id']}/events", c.cookies,
                     lambda e, d: e == "run_end", timeout=900)
    return res, evs


def test_full_pipeline_in_temp_workspace(live):
    before = repo_state()
    c = Client(live.server_address[1])
    c.login("ops")
    assert c.post("/api/workspaces", {"id": "bank", "template": "mock_bank"})[0] == 201
    status, pre = c.get("/api/preflight?ws=bank")
    assert status == 200 and pre["ok"], pre

    status, res = c.post("/api/workspaces/bank/runs", {})
    assert status == 202, res
    status, body = c.post("/api/workspaces/bank/runs", {})  # one run per workspace
    assert status == 409 and body["error"]["code"] == "run_in_progress"
    evs = sse_events(live.server_address[1], f"/api/workspaces/bank/runs/{res['run_id']}/events", c.cookies,
                     lambda e, d: e == "run_end", timeout=900)
    end = evs[-1][1]
    assert end["status"] == "PASS", end["tail"]
    stations = [d["step"] for e, d in evs if e == "step_end" and d["station"]]
    assert stations == STEPS  # exactly the run_demo.sh steps, in order
    assert any(e == "step_end" and d["step"] == "keygen" for e, d in evs)  # per-workspace key generated
    assert all(d["exit_code"] == 0 and d["duration_s"] >= 0 for e, d in evs if e == "step_end")
    status, runs = c.get("/api/workspaces/bank/runs")
    assert runs["active"] is None and runs["runs"][0]["status"] == "PASS"
    assert [s["step"] for s in runs["runs"][0]["detail"]["summary"]] == STEPS
    first = c.get("/api/workspaces/bank/results")[1]["results"]["ledger"]["entries"][0]
    assert first["type"] == "detect.run"  # Proof Chain stage: Detect evidence is signed before anything else runs
    replay = sse_events(live.server_address[1], f"/api/workspaces/bank/runs/{res['run_id']}/events", c.cookies,
                        lambda e, d: e == "run_end", timeout=30)
    assert [e for e in replay if e[0] != "heartbeat"] == [e for e in evs if e[0] != "heartbeat"]  # full event log (heartbeats are not events)

    status, body = c.get("/api/workspaces/bank/results")
    r = body["results"]
    from contracts import validate

    validate("results", r)
    assert r["detect"]["inventory"]["assets"] == 16
    assert {s["service_id"]: s["negotiated_group"] for s in r["handshake_evidence"]["sessions"]}["hybrid"] == "X25519MLKEM768"
    assert r["ledger"]["ledger_ref"] == "out/ledger.jsonl" and r["ledger_verification"]["ok"] is True
    assert all(run["job_id"] is None and run["job_id_reason"] for run in r["solver_runs"])
    root = Path(live.app.store.path).parent / "workspaces" / "bank"
    fp = (root / "keys" / "ledger_mldsa65.pub.sha256").read_text().strip()
    assert r["ledger"]["pubkey_fp"] == fp  # the workspace's own key, not the repo's

    status, led = c.get("/api/workspaces/bank/ledger")
    assert led["live_verification"]["ok"] is True and led["entry_count"] == len(led["entries"])
    real = (root / "out" / "ledger.jsonl").read_bytes()
    status, t = c.post("/api/workspaces/bank/tamper-demo", {"index": 1})
    assert status == 200 and t["index"] == 1 and (root / "out" / "ledger.jsonl").read_bytes() == real

    r2, report = c.request("GET", "/api/workspaces/bank/report", raw=True)
    assert r2.status == 200 and b"Q-Shield Atlas report" in report and r2.headers.get_all("Content-Security-Policy") == [r2.headers["Content-Security-Policy"]] \
        and "sandbox" in r2.headers["Content-Security-Policy"]

    # review: approve the plan with a reason -> signed review.decision entry, chain still verifies
    status, rv = c.get("/api/workspaces/bank/reviews")
    assert status == 200 and rv["can_decide"] and {i["kind"] for i in rv["items"]} >= {"plan", "wave", "qaoa"}
    plan = next(i for i in rv["items"] if i["kind"] == "plan")
    assert plan["status"] == "pending" and len(plan["evidence_sha256"]) == 64
    status, body = c.post("/api/workspaces/bank/reviews", {"item": plan["id"], "decision": "approve", "reason": ""})
    assert status == 422 and body["error"]["code"] == "reason_required"
    status, body = c.post("/api/workspaces/bank/reviews", {"item": plan["id"], "decision": "approve", "reason": "capacity matches the team plan"})
    assert status == 200, body
    done = next(i for i in body["items"] if i["id"] == plan["id"])
    assert done["status"] == "approved" and done["decision"]["reason"] == "capacity matches the team plan"
    r = c.get("/api/workspaces/bank/results")[1]["results"]
    entry = r["ledger"]["entries"][done["decision"]["ledger_index"]]
    assert entry["type"] == "review.decision" and r["ledger_verification"]["ok"] is True
    assert c.post("/api/workspaces/bank/reviews", {"item": plan["id"], "decision": "reject", "reason": "again"})[1]["error"]["code"] == "already_decided"
    wave = next(i for i in body["items"] if i["kind"] == "wave")
    status, body = c.post("/api/workspaces/bank/reviews", {"item": wave["id"], "decision": "reject", "reason": "not verified in the lab yet"})
    assert status == 200 and next(i for i in body["items"] if i["id"] == wave["id"])["status"] == "rejected"

    # calibration: record actuals, apply -> re-plan, change signed into the workspace ledger
    gw = next(a for a in r["assets"] if a["kind"] == "tls_gateway")
    status, prop = c.post("/api/workspaces/bank/calibration", {"asset_id": gw["id"], "engineer_days": 2.5})
    assert status == 200
    status, body = c.post("/api/workspaces/bank/calibration/apply", {})  # one actual -> capacity 2.5 d/wk: infeasible
    assert status == 422 and body["error"]["code"] == "infeasible"
    res, evs = run_and_follow(live, c, "/api/workspaces/bank/calibration/apply", {"apply": ["effort_days_by_kind.tls_gateway"]})
    end = evs[-1][1]
    assert end["status"] == "PASS", end["tail"]
    steps = [d["step"] for e, d in evs if e == "step_end"]
    assert steps.index("calibration_sign") == steps.index("ledger_ingest") + 1
    r = c.get("/api/workspaces/bank/results")[1]["results"]
    assert r["assumptions"]["effort_days_by_kind"]["tls_gateway"] == 2.5
    assert r["assumptions"]["calibration"]["label"] == "calibrated from your measurements"
    signed = [e for e in r["ledger"]["entries"] if e["type"] == "calibration.apply"]
    assert [e["payload_ref"] for e in signed] == [res["calibration_payload"]]
    assert r["ledger_verification"]["ok"] is True

    assert repo_state() == before  # repo out/, keys/ and runs/ untouched
    log = "\n".join(d["text"] for e, d in evs if e == "line")
    for k in ("QPIAI_OPT_API_KEY", "QCLOUD_API_KEY"):
        v = os.environ.get(k)
        if v and len(v) >= 8:
            assert v not in log
