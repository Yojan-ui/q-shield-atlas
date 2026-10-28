"""atlas_web server: only static/vendored files and the API are served, SPA fallback, JSON errors,
SSE on file change, read-only demo workspace, tamper demo never touches the real ledger."""

import hashlib
import http.client
import json
import shutil
import threading
import time
from pathlib import Path

import pytest

from .atlas_web_helpers import PASSWORD, Client, sse_events, start_server

REPO = Path(__file__).resolve().parent.parent


@pytest.fixture
def server(monkeypatch, tmp_path):
    srv = start_server(monkeypatch, tmp_path)
    for name, role in (("ada", "admin"), ("ops", "operator"), ("vic", "viewer")):
        srv.app.store.create_user(name, PASSWORD, role)
    yield srv
    srv.shutdown()
    srv.server_close()


def client(srv, user=None):
    c = Client(srv.server_address[1])
    if user:
        assert c.login(user)[0] == 200
    return c


def raw_get(port, path):
    """Send the path verbatim (no client-side normalisation)."""
    c = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
    c.putrequest("GET", path, skip_accept_encoding=True)
    c.endheaders()
    r = c.getresponse()
    body = r.read()
    c.close()
    return r.status, body


PROTECTED = ["/keys/ledger_mldsa65.key", "/keys/", "/keys", "/.env.sh", "/runs/", "/runs/platform_jobs.log", "/config/assumptions.json",
             "/config", "/out/results.json", "/out/ledger.jsonl", "/atlas_web/server.py", "/atlas_web/data/atlas.db", "/server.py",
             "/data/atlas.db", "/src/", "/workspaces/x/keys/ledger_mldsa65.key", "/assets/../server.py", "/assets/..%2fserver.py",
             "/%2e%2e/keys/ledger_mldsa65.key", "/assets/%2e%2e/%2e%2e/.env.sh", "/vendor/../../keys/ledger_mldsa65.key",
             "/vendor/MANIFEST.json", "/vendor/three-addons/../../server.py", "/.git/config", "/ledger/pubkey/ledger_mldsa65.pub.pem",
             "/assets/vendor/three-addons/MANIFEST.json", "/README.md", "/pqc_qaoa.py"]


@pytest.mark.parametrize("path", PROTECTED)
def test_protected_paths_404(server, path):
    status, body = raw_get(server.server_address[1], path)
    assert status == 404, (path, status)
    assert b"BEGIN" not in body and b"export" not in body and b"<html" not in body.lower()


def test_protected_paths_404_even_signed_in(server):
    c = client(server, "ada")
    for path in ("/keys/ledger_mldsa65.key", "/.env.sh", "/out/ledger.jsonl", "/config/atlas_web.json"):
        r, body = c.request("GET", path, raw=True)
        assert r.status == 404, path


@pytest.mark.parametrize("path", ["/", "/signin", "/w/demo/pipeline", "/w/demo/asset/web-gw", "/w/x/schedule",
                                  "/settings/users", "/no/such/route", "/w/demo/qaoa?p=2"])
def test_spa_fallback_returns_index_for_deep_links(server, path):
    status, body = raw_get(server.server_address[1], path)
    assert status == 200 and body == (REPO / "atlas_web" / "static" / "index.html").read_bytes()


def test_unknown_api_paths_are_json_404(server):
    c = client(server, "vic")
    for path in ("/api/nope", "/api/workspaces/demo/nope", "/api"):
        status, body = c.get(path)
        assert status == 404 and set(body["error"]) == {"code", "message"}, path
    status, body = client(server, "vic").get("/api/workspaces/nope/results")
    assert status == 404 and body["error"]["code"] == "not_found"


def test_security_headers(server):
    r, _ = Client(server.server_address[1]).request("GET", "/", raw=True)
    assert "default-src 'self'" in r.headers["Content-Security-Policy"] and "frame-ancestors 'none'" in r.headers["Content-Security-Policy"]
    assert r.headers["X-Content-Type-Options"] == "nosniff" and r.headers["X-Frame-Options"] == "DENY"
    assert "Python" not in r.headers["Server"]


def test_vendored_three_served_only_if_hash_matches(server):
    port = server.server_address[1]
    status, body = raw_get(port, "/vendor/three-0.170.0.module.min.js")
    mf = json.loads((REPO / "viz" / "vendor" / "MANIFEST.json").read_text())
    assert status == 200 and hashlib.sha256(body).hexdigest() == mf["files"]["three-0.170.0.module.min.js"]


def test_health_and_me(server):
    c = client(server)
    assert c.get("/api/health") == (200, {"ok": True, "service": "atlas_web", "time": c.get("/api/health")[1]["time"]})
    assert c.get("/api/me")[1] == {"user": None, "kiosk": False, "demo": False}


def test_errors_never_leak_tracebacks(server, monkeypatch):
    import atlas_web.server as s

    monkeypatch.setattr(s, "load_results", lambda ws: (_ for _ in ()).throw(RuntimeError("secret detail")))
    status, body = client(server, "vic").get("/api/workspaces/demo/results")
    assert status == 500 and body == {"error": {"code": "internal", "message": "internal error; see the server log"}}


# ---------------- demo workspace ----------------

def test_demo_results_public_and_read_only(server):
    anon = client(server)
    status, body = anon.get("/api/workspaces/demo/results")
    assert status == 200 and body["workspace"] == "demo"
    if (REPO / "out" / "results.json").exists():
        assert body["results"] == json.loads((REPO / "out" / "results.json").read_text())
    else:
        assert body["results"] is None and body["status_text"] == "not yet run"
    assert anon.get("/api/workspaces/demo/manifests")[0] == 401  # only the snapshot views are public
    ops = client(server, "ops")
    for path, payload in (("/api/workspaces/demo/runs", {}), ("/api/workspaces/demo/assumptions", {"horizon_weeks": 3}),
                          ("/api/workspaces/demo/calibration", {"asset_id": "x", "engineer_days": 1}),
                          ("/api/workspaces/demo/clone", {"url": "https://github.com/a/b"})):
        status, body = ops.post(path, payload)
        assert status == 403 and body["error"]["code"] == "read_only", path
    status, body = ops.request("POST", "/api/workspaces/demo/upload", b"PK", headers={"Content-Type": "application/zip"})
    assert status == 403 and body["error"]["code"] == "read_only"


def needs_demo_ledger():
    if not (REPO / "out" / "results.json").exists() or not (REPO / "out" / "ledger.jsonl").exists():
        pytest.skip("no generated out/results.json + ledger in this checkout")
    from detect.live_probe import openssl_binary

    try:
        openssl_binary()
    except Exception as exc:  # noqa: BLE001
        pytest.skip(f"no OpenSSL >= 3.5 with ML-DSA: {exc}")


def digest_out():
    return {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in (REPO / "out").iterdir() if p.is_file()}


def test_demo_ledger_payload_is_read_only(server):
    needs_demo_ledger()
    before = digest_out()
    status, body = client(server).get("/api/workspaces/demo/ledger")
    assert status == 200 and body["available"]
    r = json.loads((REPO / "out" / "results.json").read_text())
    assert body["root"] == r["ledger"]["root"] and len(body["entries"]) == r["ledger"]["entry_count"]
    assert body["live_verification"]["recorded"] is False and body["live_verification"]["ok"] is True
    status, proof = client(server, "vic").get("/api/workspaces/demo/ledger/proof/1")
    assert status == 200 and proof["verified"] is True and proof["root"] == r["ledger"]["root"]
    assert digest_out() == before


def test_tamper_demo_never_changes_the_real_ledger(server):
    needs_demo_ledger()
    before = digest_out()
    vic = client(server, "vic")
    status, body = vic.post("/api/workspaces/demo/tamper-demo", {"index": 2})
    assert status == 200, body
    assert body["index"] == 2 and "signature" in body["reason"] and body["recorded"] is False
    assert body["real_ledger_sha256_before"] == body["real_ledger_sha256_after"]
    assert digest_out() == before
    status, body = vic.post("/api/workspaces/demo/tamper-demo", {})
    assert status == 429 and body["error"]["code"] == "rate_limited"  # 1 request per second
    assert client(server).post("/api/workspaces/demo/tamper-demo", {})[0] == 401
    time.sleep(1.05)
    assert vic.post("/api/workspaces/demo/tamper-demo", {"index": 10**6})[0] == 422


# ---------------- workspaces ----------------

def test_create_workspace_from_template(server):
    ops = client(server, "ops")
    status, ws = ops.post("/api/workspaces", {"id": "bank", "name": "Bank", "template": "mock_bank"})
    assert status == 201 and ws["lab_probes"] == ["web-gw=legacy"] and not ws["read_only"]
    assert ops.post("/api/workspaces", {"id": "bank", "template": "empty"})[0] == 409
    for bad in ("demo", "../x", "Bad", "", "a" * 40):
        assert ops.post("/api/workspaces", {"id": bad, "template": "empty"})[0] == 400, bad
    root = Path(server.app.store.path).parent / "workspaces" / "bank"
    assert (root / "src" / "services").is_dir() and (root / "config" / "assumptions.json").exists()
    assert (root / "keys").stat().st_mode & 0o777 == 0o700
    status, m = ops.get("/api/workspaces/bank/manifests")
    assert status == 200 and len(m["services"]) == 17 and "tls_gateway" in m["kinds"] and "payments" in m["data_classes"]
    status, body = ops.get("/api/workspaces/bank/results")
    assert body == {"workspace": "bank", "results": None, "status_text": "not yet run"}
    status, body = ops.get("/api/workspaces/bank/ledger")
    assert body == {"available": False, "status_text": "not yet run"}


def test_manifest_editor_validates(server):
    ops = client(server, "ops")
    ops.post("/api/workspaces", {"id": "bank", "template": "mock_bank"})
    good = {"id": "new-svc", "name": "New service", "kind": "tls_gateway", "data_class": "payments", "depends_on": ["root-ca"]}
    status, body = ops.post("/api/workspaces/bank/manifests", {"dir": "services/web-gw", "manifest": {**good, "id": "web-gw"}})
    assert status == 200 and body["saved"]["id"] == "web-gw"
    status, body = ops.post("/api/workspaces/bank/manifests", {"dir": "services", "manifest": {**good, "kind": "toaster",
                                                                                                "depends_on": ["ghost"], "id": "auth"}})
    assert status == 422 and set(body["error"]["fields"]) == {"kind", "depends_on", "id"}
    for bad_dir in ("../..", "/etc", "services/nope", ""):
        status, body = ops.post("/api/workspaces/bank/manifests", {"dir": bad_dir, "manifest": good})
        assert status == 400 and body["error"]["code"] == "bad_dir", bad_dir
    assert client(server, "vic").post("/api/workspaces/bank/manifests", {"dir": "services", "manifest": good})[0] == 403


def test_assumptions_editor_validates(server):
    ops = client(server, "ops")
    ops.post("/api/workspaces", {"id": "bank", "template": "mock_bank"})
    status, body = ops.get("/api/workspaces/bank/assumptions")
    assert status == 200 and body["label"] == "assumption"
    status, body = ops.request("PUT", "/api/workspaces/bank/assumptions", {"capacity_days_per_week": 12, "effort_days_by_kind": {"hsm": 6}})
    assert status == 200 and body["assumptions"]["capacity_days_per_week"] == 12 and body["assumptions"]["effort_days_by_kind"]["hsm"] == 6
    status, body = ops.request("PUT", "/api/workspaces/bank/assumptions", {"capacity_days_per_week": -1, "effort_days_by_kind": {"x": 1},
                                                                           "scenarios": [{"name": "Z", "year": 2030, "weight": 0.5}]})
    assert status == 422 and {"capacity_days_per_week", "effort_days_by_kind.x", "scenarios"} <= set(body["error"]["fields"])
    status, body = ops.request("PUT", "/api/workspaces/bank/assumptions", {"capacity_days_per_week": 2})
    assert status == 422 and "fit in one week" in body["error"]["fields"]["capacity_days_per_week"]


def test_calibration_medians_never_auto_applied(server):
    ops = client(server, "ops")
    ops.post("/api/workspaces", {"id": "bank", "template": "mock_bank"})
    root = Path(server.app.store.path).parent / "workspaces" / "bank"
    sample = json.loads((REPO / "tests" / "fixtures" / "results_sample.json").read_text())
    (root / "out" / "results.json").write_text(json.dumps(sample))
    gws = [a["id"] for a in sample["assets"] if a["kind"] == "tls_gateway"]
    assert ops.post("/api/workspaces/bank/calibration", {"asset_id": "ghost", "engineer_days": 2})[0] == 422
    assert ops.post("/api/workspaces/bank/calibration", {"asset_id": gws[0], "engineer_days": -2})[0] == 422
    before = (root / "config" / "assumptions.json").read_bytes()
    days = [2.0, 5.0, 4.0]
    for asset, d in zip(gws + [gws[0]] * 3, days):
        status, prop = ops.post("/api/workspaces/bank/calibration", {"asset_id": asset, "engineer_days": d})
        assert status == 200
    vals = {a["asset_id"]: a["engineer_days"] for a in prop["actuals"]}  # one (latest) measurement per asset
    gw = next(k for k in prop["effort_days_by_kind"] if k["kind"] == "tls_gateway")
    import statistics

    assert gw["n"] == len(vals) and gw["measured_median"] == statistics.median(vals.values()) and gw["assumed"] == 3
    assert next(k for k in prop["effort_days_by_kind"] if k["kind"] == "hsm")["measured_median"] is None
    assert prop["label"] == "calibrated from your measurements"
    assert prop["capacity_days_per_week"]["n_weeks"] >= 1
    assert (root / "config" / "assumptions.json").read_bytes() == before  # proposals never auto-apply


def test_file_events_push_on_change(server):
    ops = client(server, "ops")
    ops.post("/api/workspaces", {"id": "bank", "template": "mock_bank"})
    root = Path(server.app.store.path).parent / "workspaces" / "bank"
    def write_later():
        time.sleep(0.8)
        (root / "out" / "results.json").write_text("{}")
    threading.Thread(target=write_later, daemon=True).start()
    evs = sse_events(server.server_address[1], "/api/events?ws=bank", ops.cookies, lambda e, d: e == "update", timeout=15)
    assert evs[0] == ("hello", {"workspace": "bank"}) and evs[-1][1] == {"workspace": "bank", "changed": ["results"]}
    evs = sse_events(server.server_address[1], "/api/events?ws=bank&heartbeat=0.3", ops.cookies, lambda e, d: e == "heartbeat", timeout=10)
    assert evs[-1][0] == "heartbeat"
    status, _ = client(server).get("/api/events?ws=bank")
    assert status == 401


def test_platform_runs_admin_only_and_blocked(server):
    ops, ada = client(server, "ops"), client(server, "ada")
    ops.post("/api/workspaces", {"id": "bank", "template": "mock_bank"})
    status, body = ops.post("/api/workspaces/bank/runs", {"platform": True, "confirm_credits": True})
    assert status == 403
    status, body = ada.post("/api/workspaces/bank/runs", {"platform": True, "confirm_credits": True})
    assert status == 409 and "no active storage quota" in body["error"]["message"]
    status, body = ada.post("/api/workspaces/bank/runs", {"qcloud": True, "confirm_credits": True})
    assert status == 409 and "subscription" in body["error"]["message"]
    status, body = ada.get("/api/preflight?ws=bank")
    assert status == 200 and body["platform"]["opt"]["enabled"] is False and body["platform"]["opt"]["status_text"]
    assert all(c["fix"] for c in body["checks"] if not c["ok"])
    import os

    key = os.environ.get("QPIAI_OPT_API_KEY")
    if key:
        assert key not in json.dumps(body)


def test_probe_syntax_and_authorisation(server):
    ops = client(server, "ops")
    ops.post("/api/workspaces", {"id": "bank", "template": "mock_bank"})
    for bad in ("web-gw", "web-gw=host", "web-gw=host:99999", "WEB=host:443", "x=bad host:443", "x=h;rm -rf /:443"):
        status, body = ops.post("/api/workspaces/bank/runs", {"probes": [bad], "authorised": True})
        assert status == 400 and body["error"]["code"] == "bad_probe", bad
    status, body = ops.post("/api/workspaces/bank/runs", {"probes": ["web-gw=example.com:443"]})
    assert status == 422 and body["error"]["code"] == "not_authorised"


def test_runlog_replay_rejects_bad_ids(server):
    vic = client(server, "vic")
    for rid in ("../../etc", "zzzz", "0123456789abcdef"):
        status, body = vic.get(f"/api/workspaces/demo/runs/{rid}/events")
        assert status == 404, rid
