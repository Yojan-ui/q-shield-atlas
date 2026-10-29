"""Real data end to end: clone a pinned public repo -> suggested manifests (refused until confirmed) -> confirm ->
run with the public PQ reference endpoints -> results validate -> every route renders without console errors.
Plus: empty inventories give an honest empty plan, and capacity-infeasible schedules give a designed hint."""

import json
import os
import socket
import subprocess
import sys
from pathlib import Path

import pytest

from .atlas_web_helpers import PASSWORD, Client, sse_events, start_server
from .test_atlas_web_e2e import browser_check
from .test_atlas_web_pipeline import repo_state

REPO = Path(__file__).resolve().parent.parent
PIN = next(r for r in json.loads((REPO / "detect" / "real_repos.json").read_text())["repos"] if r["name"] == "online-boutique")


def online(host="github.com"):
    try:
        socket.create_connection((host, 443), timeout=5).close()
        return True
    except OSError:
        return False


def test_real_repo_clone_suggest_confirm_run_routes(monkeypatch, tmp_path):
    if not online():
        pytest.skip("offline: cannot clone the pinned public repository")
    if not os.environ.get("QPIAI_OPT_API_KEY"):
        pytest.skip("QPIAI_OPT_API_KEY not set")
    from detect.live_probe import openssl_binary

    try:
        openssl_binary()
    except Exception as exc:  # noqa: BLE001
        pytest.skip(f"OpenSSL >= 3.5 missing: {exc}")
    before = repo_state()
    srv = start_server(monkeypatch, tmp_path)
    try:
        srv.app.store.create_user("ops", PASSWORD, "operator")
        c = Client(srv.server_address[1])
        c.login("ops")
        assert c.post("/api/workspaces", {"id": "ob", "name": "Online Boutique", "template": "empty"})[0] == 201
        assert c.post("/api/workspaces/ob/clone", {"url": PIN["url"], "commit": "nothex"})[1]["error"]["code"] == "bad_commit"
        status, cl = c.post("/api/workspaces/ob/clone", {"url": PIN["url"], "commit": PIN["commit"]})
        assert status == 200 and cl["commit"] == PIN["commit"] and cl["pinned"], cl
        status, sg = c.post("/api/workspaces/ob/manifests/suggest", {})
        assert status == 200 and sg["service_dirs"] >= 10 and len(sg["written"]) == sg["service_dirs"]
        svc = {s["manifest"]["id"]: s["manifest"] for s in sg["services"]}
        assert all(m["suggested"]["status"] == "suggested — review" and m["suggested"]["basis"]["kind"] for m in svc.values())
        assert "checkoutservice" in svc["frontend"]["depends_on"]  # from kubernetes-manifests env <service>:<port>
        assert c.post("/api/workspaces/ob/manifests/suggest", {})[1]["skipped_existing"]  # never overwrites
        status, body = c.post("/api/workspaces/ob/runs", {})
        assert status == 409 and body["error"]["code"] == "manifests_unconfirmed"  # suggestions are not facts
        pre = c.get("/api/preflight?ws=ob")[1]
        assert next(x for x in pre["checks"] if x["id"] == "manifests_confirmed")["ok"] is False
        status, cf = c.post("/api/workspaces/ob/manifests/confirm", {})
        assert status == 200 and cf["still_suggested"] == 0 and len(cf["confirmed"]) == len(svc)
        assert all("suggested" not in s["manifest"] for s in cf["services"])
        assert c.get("/api/workspaces/ob")[1]["source"]["commit"] == PIN["commit"]
        assert c.post("/api/workspaces/ob/runs", {"presets": ["nope"]})[1]["error"]["code"] == "bad_preset"
        status, run = c.post("/api/workspaces/ob/runs", {"presets": ["cloudflare-pq"]})  # preset: no authorisation box needed
        assert status == 202, run
        evs = sse_events(srv.server_address[1], f"/api/workspaces/ob/runs/{run['run_id']}/events", c.cookies, lambda e, d: e == "run_end", timeout=1200)
        assert evs[-1][1]["status"] == "PASS", evs[-1][1]["tail"]
        r = c.get("/api/workspaces/ob/results")[1]["results"]
        from contracts import validate

        validate("results", r)
        assert r["detect"]["files_scanned"] > 300 and r["detect"]["summary"]["vulnerable_findings"] >= 1 and len(r["assets"]) >= 1
        probe = next(p for p in r["detect"]["probes"] if p["service"] == "ref-cloudflare-pq")
        assert probe["live"]["group"] == "X25519MLKEM768"
        scene = c.get("/api/workspaces/ob/scene")[1]
        assert scene["files"]["verified"] and any(n["kind"] == "reviewed finding" for n in scene["review_notes"])
        listing = c.get("/api/workspaces")[1]["workspaces"]
        ob = next(w for w in listing if w["id"] == "ob")
        assert ob["type"] == "REAL REPO" and ob["ledger_verified"] is True and ob["assets"] == len(r["assets"])
        asset = r["assets"][0]["id"]
        problems = browser_check(srv.server_address[1], c.cookies,
                                 [f"/w/ob/{x}" for x in ("pipeline", "detect", "schedule", "handshakes", "ledger", "qaoa")] + [f"/w/ob/asset/{asset}"])
        if problems is not None:
            assert problems == {}, json.dumps(problems, indent=1)
    finally:
        srv.shutdown()
        srv.server_close()
    assert repo_state() == before


def test_empty_inventory_gives_an_honest_empty_plan(tmp_path):
    (tmp_path / "inv.json").write_text('{"assets": []}')
    env = {**os.environ, "QSHIELD_FORBID_PLATFORM": "1", "QPIAI_OPT_API_KEY": os.environ.get("QPIAI_OPT_API_KEY", "unused-offline")}
    out = subprocess.run([sys.executable, "-m", "schedule", "--inventory", str(tmp_path / "inv.json"), "--out", str(tmp_path / "schedule.json"),
                          "--runs", str(tmp_path / "runs")], cwd=REPO, env=env, capture_output=True, text=True, timeout=120)
    assert out.returncode == 0, out.stderr[-500:]
    sec = json.loads((tmp_path / "schedule.json").read_text())
    assert sec["nothing_to_migrate"] is True and sec["assets"] == [] and sec["solver_runs"] == []
    assert sec["exposure"]["produced_by"]["solver"].startswith("none: the inventory has no quantum-vulnerable assets")
    q = subprocess.run([sys.executable, "-m", "qaoa", "--qpiai-local", "--schedule", str(tmp_path / "schedule.json"), "--out-dir", str(tmp_path),
                        "--runs", str(tmp_path / "runs")], cwd=REPO, env=env, capture_output=True, text=True, timeout=120)
    assert q.returncode == 0 and "nothing to select" in q.stdout and not (tmp_path / "qaoa.json").exists()
    from contracts import validate
    from contracts.assemble import assemble

    validate("results", assemble(tmp_path))
    sample = json.loads((REPO / "tests" / "fixtures" / "results_sample.json").read_text())
    with pytest.raises(Exception):  # zero solver runs are only valid for an empty, flagged plan
        validate("results", {**sample, "solver_runs": []})


def test_capacity_hint_names_the_asset_and_the_fix():
    from atlas_web.runner import capacity_hint

    h = capacity_hint(["Traceback ...", "ValueError: root-ca effort 12.0 d exceeds weekly capacity 10.0 d; split the asset"])
    assert h["asset"] == "root-ca" and h["effort_days"] == 12.0 and h["capacity_days"] == 10.0
    assert "capacity_days_per_week" in h["fix"] and "assumptions" in h["fix"]
    assert capacity_hint(["something else failed"]) is None
    r = capacity_hint(["qpiai_opt.opt_solvers.exceptions.AuthenticationError: The authentication service rate-limited this solve; retry later"])
    assert r["code"] == "opt_rate_limited" and "run again" in r["fix"]
