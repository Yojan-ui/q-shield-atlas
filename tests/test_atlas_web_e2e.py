"""End to end through atlas_web: new workspace -> upload detect/fixtures/mock_bank as a .zip -> manifests ->
run -> every route renders the results (headless Chrome, zero errors) -> calibration -> re-run.
Local only (QSHIELD_FORBID_PLATFORM=1); the repo's out/, runs/ and keys/ must be unchanged."""

import io
import json
import os
import shutil
import sys
import zipfile
from pathlib import Path

import pytest

from .atlas_web_helpers import PASSWORD, Client, sse_events, start_server
from .test_atlas_web_pipeline import STEPS, repo_state

REPO = Path(__file__).resolve().parent.parent
ROUTES = ["pipeline", "detect", "schedule", "handshakes", "ledger", "qaoa"]


def zip_tree(root: Path) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for p in sorted(root.rglob("*")):
            if p.is_file():
                z.write(p, f"mock_bank/{p.relative_to(root).as_posix()}")
    return buf.getvalue()


def run(srv, c, path, body):
    status, res = c.post(path, body)
    assert status == 202, res
    evs = sse_events(srv.server_address[1], f"/api/workspaces/e2e/runs/{res['run_id']}/events", c.cookies, lambda e, d: e == "run_end", timeout=900)
    assert evs[-1][1]["status"] == "PASS", evs[-1][1]["tail"]
    return res, evs


def browser_check(port, cookies, paths):
    sys.path.insert(0, str(REPO / "tools"))
    from cdp import Browser, chrome_binary
    from route_check import driver_noise

    if not chrome_binary():
        return None
    b = Browser()
    problems = {}
    try:
        for path in paths:
            page = b.new_page(b.new_context())
            try:
                for d in ("Runtime", "Log", "Network", "Page"):
                    page.send(f"{d}.enable")
                for k, v in cookies.items():
                    page.send("Network.setCookie", {"name": k, "value": v, "url": f"http://127.0.0.1:{port}"})
                page.send("Page.navigate", {"url": f"http://127.0.0.1:{port}{path}"})
                page.wait_for("document.body && document.body.dataset.ready === '1'", 20)
                page.wait_for("!document.querySelector('.skel')", 10)
                info = page.eval("({route: document.body.dataset.route, empty: !!document.querySelector('.state.empty, .state.error'),"
                                 " errors: window.__atlasErrors || []})")
                bad = list(info["errors"])
                if info["empty"]:
                    bad.append("empty/error state shown although the workspace has results")
                for m, p in page.events:
                    if m == "Runtime.exceptionThrown" or (m == "Runtime.consoleAPICalled" and p["type"] in ("error", "warning")):
                        bad.append(f"{m}: {str(p)[:200]}")
                    elif m == "Log.entryAdded" and p["entry"]["level"] in ("error", "warning") and not driver_noise(p["entry"]):
                        bad.append(f"log: {p['entry'].get('text', '')[:200]}")
                    elif m == "Network.responseReceived" and p["response"]["status"] >= 400:
                        bad.append(f"HTTP {p['response']['status']} {p['response']['url']}")
                if bad:
                    problems[path] = bad
            finally:
                page.close()
    finally:
        b.close()
    return problems


def test_e2e_upload_run_routes_calibrate_rerun(monkeypatch, tmp_path):
    if not os.environ.get("QPIAI_OPT_API_KEY"):
        pytest.skip("QPIAI_OPT_API_KEY not set; local QpiAI Opt solves verify the key online")
    from detect.live_probe import openssl_binary

    try:
        openssl_binary()
    except Exception as exc:  # noqa: BLE001
        pytest.skip(f"OpenSSL >= 3.5 with ML-KEM/ML-DSA missing: {exc}")
    assert os.environ.get("QSHIELD_FORBID_PLATFORM") == "1"
    before = repo_state()
    srv = start_server(monkeypatch, tmp_path)
    try:
        srv.app.store.create_user("ops", PASSWORD, "operator")
        c = Client(srv.server_address[1])
        c.login("ops")
        assert c.post("/api/workspaces", {"id": "e2e", "name": "E2E bank", "template": "empty"})[0] == 201
        status, up = c.request("POST", "/api/workspaces/e2e/upload", zip_tree(REPO / "detect" / "fixtures" / "mock_bank"),
                               headers={"Content-Type": "application/zip"})
        assert status == 200 and up["manifests"] == 17, up
        status, m = c.get("/api/workspaces/e2e/manifests")
        web = next(s for s in m["services"] if s["manifest"]["id"] == "web-gw")
        status, saved = c.post("/api/workspaces/e2e/manifests", {"dir": web["dir"], "manifest": {**web["manifest"], "name": "Public web gateway (edited)"}})
        assert status == 200 and saved["saved"]["name"] == "Public web gateway (edited)"

        res, evs = run(srv, c, "/api/workspaces/e2e/runs", {})
        assert [d["step"] for e, d in evs if e == "step_end" and d["station"]] == STEPS
        r = c.get("/api/workspaces/e2e/results")[1]["results"]
        assert r["detect"]["inventory"]["assets"] == 16
        assert next(a for a in r["assets"] if a["id"] == "web-gw")["name"] == "Public web gateway (edited)"
        for key in ("scene", "ledger", "manifests", "assumptions", "calibration", "runs"):
            status, body = c.get(f"/api/workspaces/e2e/{key}")
            assert status == 200, key
        assert c.get("/api/workspaces/e2e/scene")[1]["files"]["verified"] is True

        paths = [f"/w/e2e/{r_}" for r_ in ROUTES] + ["/w/e2e/asset/web-gw", "/w/e2e/schedule?scenario=Z2035&week=3"]
        problems = browser_check(srv.server_address[1], c.cookies, paths)
        if problems is not None:
            assert problems == {}, json.dumps(problems, indent=1)

        gw = next(a for a in r["assets"] if a["kind"] == "tls_gateway")
        assert c.post("/api/workspaces/e2e/calibration", {"asset_id": gw["id"], "engineer_days": 2.0})[0] == 200
        res, evs = run(srv, c, "/api/workspaces/e2e/calibration/apply", {"apply": ["effort_days_by_kind.tls_gateway"]})
        r2 = c.get("/api/workspaces/e2e/results")[1]["results"]
        assert r2["assumptions"]["effort_days_by_kind"]["tls_gateway"] == 2.0
        assert any(e["type"] == "calibration.apply" for e in r2["ledger"]["entries"])
        assert r2["ledger_verification"]["ok"] is True
        res, evs = run(srv, c, "/api/workspaces/e2e/runs", {})  # re-run after calibration
        assert c.get("/api/workspaces/e2e/results")[1]["results"]["ledger_verification"]["ok"] is True
    finally:
        srv.shutdown()
        srv.server_close()
    assert repo_state() == before
