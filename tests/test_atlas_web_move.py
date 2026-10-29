"""Move page data: recorded transcripts parsed into TLS messages with real sizes, used only when their hash matches
capture.json; real bank endpoints are only 'observed'; the endpoint is read-only and returns no hex or randoms."""

import hashlib
import json
from pathlib import Path

import pytest

from atlas_web import workspaces
from atlas_web.move import move_payload, observed_endpoints, parse_transcript

from .atlas_web_helpers import PASSWORD, Client, start_server

REPO = Path(__file__).resolve().parent.parent


def test_demo_transcripts_parse_and_match_capture():
    cap = json.loads((REPO / "out" / "capture.json").read_text())
    p = move_payload(workspaces.demo(), None)
    assert p["available"] and p["run_id"] == cap["run_id"]
    assert len(p["sessions"]) == len(cap["sessions"]) and len(p["refused_attempts"]) == len(cap["refused_attempts"])
    for s in p["sessions"] + p["refused_attempts"]:
        assert s["transcript_verified"], s["service_id"]
        text = (REPO / s["transcript_file"]).read_text()
        assert hashlib.sha256(text.encode()).hexdigest() == s["transcript_sha256"]
        # packet list == the message lines of the recorded transcript, in order
        lines = [l for l in text.splitlines() if l.startswith((">>> TLS", "<<< TLS")) and "RecordHeader" not in l and "InnerContent" not in l]
        assert len(s["messages"]) == len(lines)
        for m, l in zip(s["messages"], lines):
            assert m["bytes"] == int(l.split("[length ")[1].split("]")[0], 16)
            assert m["dir"] == ("c2s" if l.startswith(">>>") else "s2c")
    by = {(s["service_id"], s["client_groups_offered"]): s for s in p["sessions"]}
    hy = by[("hybrid", "X25519MLKEM768:X25519")]["messages"]
    assert hy[0]["type"] == "ClientHello" and hy[0]["key_share"] == [{"group": "X25519MLKEM768", "bytes": 1216}]
    assert hy[1]["type"] == "ServerHello" and hy[1]["key_share"][0]["group"] == "X25519MLKEM768"
    leg = [m["type"] for m in by[("legacy", "X25519MLKEM768:X25519")]["messages"]]
    assert leg[1] == "HelloRetryRequest"  # the classical server asked the hybrid-offering client for X25519
    assert all(m["type"] != "Finished" for m in p["refused_attempts"][0]["messages"])
    assert not any("hex" in json.dumps(m) or "random" in m for s in p["sessions"] for m in s["messages"])


def test_hash_mismatch_is_not_replayed(tmp_path):
    cap = json.loads((REPO / "out" / "capture.json").read_text())
    rd = tmp_path / "runs" / cap["run_id"]
    rd.mkdir(parents=True)
    for f in (REPO / "runs" / cap["run_id"]).glob("transcript_*.txt"):
        (rd / f.name).write_text(f.read_text() + "edited\n")
    (tmp_path / "out").mkdir()
    (tmp_path / "out" / "capture.json").write_text(json.dumps(cap))
    ws = workspaces.Workspace("t", "t", "mock_bank", tmp_path, tmp_path / "out", tmp_path / "runs", tmp_path / "src", tmp_path, tmp_path, False, {})
    p = move_payload(ws, None)
    assert p["available"] and not any(s["transcript_verified"] or s["messages"] for s in p["sessions"])


def test_not_yet_run_and_observed(tmp_path):
    ws = workspaces.Workspace("t", "t", "mock_bank", tmp_path, tmp_path / "out", tmp_path / "runs", tmp_path / "src", tmp_path, tmp_path, False, {})
    assert move_payload(ws, None) == {"available": False, "status_text": "not yet run", "observed": {}}
    d = tmp_path / "src" / "abc" / "www"
    d.mkdir(parents=True)
    (d / "atlas-service.json").write_text(json.dumps({"id": "www-abc", "observed": {"negotiated_group": "ECDH", "tls_version": "TLSv1.2",
                                                      "cert_key_algorithm": "RSA-2048", "outcome": "classical", "transcript_sha256": "x"}}))
    assert observed_endpoints(tmp_path / "src")["www-abc"]["outcome"] == "classical"


def test_alert_and_hrr_parsing():
    t = ">>> TLS 1.3, Handshake [length 0004], Finished\n    14 00 00 00\n<<< TLS 1.3, Alert [length 0002], fatal handshake_failure\n    02 28\n"
    m = parse_transcript(t)
    assert m == [{"dir": "c2s", "record": "Handshake", "type": "Finished", "bytes": 4},
                 {"dir": "s2c", "record": "Alert", "type": "Alert", "bytes": 2, "alert": "fatal handshake_failure"}]


@pytest.fixture
def server(monkeypatch, tmp_path):
    srv = start_server(monkeypatch, tmp_path)
    srv.app.store.create_user("vic", PASSWORD, "viewer")
    yield srv
    srv.shutdown()
    srv.server_close()


def test_move_api_requires_login_and_is_read_only(server):
    c = Client(server.server_address[1])
    r, _ = c.request("GET", "/api/workspaces/demo/move", raw=True)
    assert r.status == 401
    c.request("POST", "/api/auth/login", {"username": "vic", "password": PASSWORD})
    before = hashlib.sha256((REPO / "out" / "capture.json").read_bytes()).hexdigest()
    r, body = c.request("GET", "/api/workspaces/demo/move", raw=True)
    assert r.status == 200 and json.loads(body)["available"]
    assert hashlib.sha256((REPO / "out" / "capture.json").read_bytes()).hexdigest() == before


# ---- headless browser: reduced motion and no-WebGL fallbacks (skipped when Chrome is not installed) ----

def _browser_pages(server, flags, media, paths, js):
    import sys
    sys.path.insert(0, str(REPO / "tools"))
    from cdp import Browser, chrome_binary

    if not chrome_binary():
        pytest.skip("Chrome not installed")
    c = Client(server.server_address[1])
    c.request("POST", "/api/auth/login", {"username": "vic", "password": PASSWORD})
    base = f"http://127.0.0.1:{server.server_address[1]}"
    b = Browser(flags)
    out = {}
    try:
        for path in paths:
            page = b.new_page(b.new_context())
            try:
                page.send("Runtime.enable")
                page.send("Emulation.setEmulatedMedia", {"features": [{"name": "prefers-reduced-motion", "value": media}]})
                for k, v in c.cookies.items():
                    page.send("Network.setCookie", {"name": k, "value": v, "url": base})
                page.send("Page.navigate", {"url": base + path})
                assert page.wait_for("document.body.dataset.ready === '1' && !document.querySelector('.skel')", 20)
                page.wait_for(js["ready"], 10)
                out[path] = page.eval(js["probe"])
                out[path]["exceptions"] = [p for m, p in page.events if m == "Runtime.exceptionThrown"]
            finally:
                page.close()
    finally:
        b.close()
    return out


def test_move_reduced_motion_is_a_static_frame(server):
    move = move_payload(workspaces.demo(), None)
    want = [m["type"] for s in move["sessions"] if s["service_id"] == "hybrid" and "MLKEM" in s["client_groups_offered"] for m in s["messages"]]
    r = _browser_pages(server, (), "reduce", ["/w/demo/migration"], {
        "ready": "!!document.querySelector('.ch-svg')",
        "probe": """(() => { const before = [...document.querySelectorAll('.ch-pkt')].map(p => p.getAttribute('transform'));
          return new Promise(ok => setTimeout(() => ok({
            inflight: [...document.querySelectorAll('.ch-pkt')].filter(p => p.getAttribute('visibility') === 'visible').length,
            moved: [...document.querySelectorAll('.ch-pkt')].some((p, i) => p.getAttribute('transform') !== before[i]),
            after: [...document.querySelectorAll('.mv-tl')[1].querySelectorAll('.ch-type')].map(e => e.textContent),
            replay: document.querySelector('.ch-replay').textContent, play: document.querySelector('.mv-controls .btn').textContent,
            ext: [...document.querySelectorAll('[src],[href]')].map(e => e.getAttribute('src') || e.getAttribute('href')).filter(u => /^https?:/.test(u)) }), 800)); })()"""})
    p = r["/w/demo/migration"]
    assert p["exceptions"] == []
    assert p["inflight"] == 0 and not p["moved"]  # nothing plays by itself
    assert p["after"] == [t if t != "Alert" else "Alert (warning close_notify)" for t in want]  # the recorded transcript, in order
    assert p["replay"] == f"Replay of recorded handshake, run {move['run_id']}"
    assert p["play"].strip() == "Play the plan" and p["ext"] == []


def test_detect_and_move_without_webgl(server):
    r = _browser_pages(server, ("--disable-gpu",), "no-preference", ["/w/demo/detect", "/w/demo/migration"], {
        "ready": "!!document.querySelector('.gr-flat, .ch-svg')",
        "probe": "({webgl: !!(window.__atlasWorld && window.__atlasWorld.webgl), nodes: document.querySelectorAll('.gr-flat .gr-node').length,"
                 " edges: document.querySelectorAll('.gr-flat .gr-edge').length, channel: !!document.querySelector('.ch-svg'), lanes: document.querySelectorAll('.ch-lane').length})"})
    inv = json.loads((REPO / "out" / "inventory.json").read_text())
    d, m = r["/w/demo/detect"], r["/w/demo/migration"]
    assert not d["webgl"] and d["exceptions"] == [] and m["exceptions"] == []
    assert d["nodes"] == len(inv["assets"]) + len(inv["not_vulnerable"])
    assert d["edges"] == sum(len(a.get("depends_on") or []) for a in inv["assets"])
    assert m["channel"] and m["lanes"] == 3  # the Move scene is SVG: it never needed WebGL


# ---- optional "Run fresh handshake now": flag-gated (off by default), operators only, 127.0.0.1 lab only ----

def test_fresh_handshake_refused_when_switched_off(server, monkeypatch):
    import atlas_web.config as cfg
    real = cfg.settings
    monkeypatch.setattr(cfg, "settings", lambda: {**real(), "fresh_handshake": {"enabled": False}})
    server.app.store.create_user("ops", PASSWORD, "operator")
    c = Client(server.server_address[1])
    c.request("POST", "/api/auth/login", {"username": "ops", "password": PASSWORD})
    assert json.loads(c.request("GET", "/api/workspaces/demo/move", raw=True)[1])["fresh"]["enabled"] is False
    r, body = c.request("POST", "/api/workspaces/demo/move/fresh", {}, raw=True)
    assert r.status == 403 and json.loads(body)["error"]["code"] == "fresh_disabled"


def test_fresh_handshake_when_enabled(server, monkeypatch, tmp_path):
    import atlas_web.config as cfg

    from .conftest import _lab_servers
    real = cfg.settings
    monkeypatch.setattr(cfg, "settings", lambda: {**real(), "fresh_handshake": {"enabled": True}})
    server.app.store.create_user("ops", PASSWORD, "operator")
    viewer = Client(server.server_address[1])
    viewer.request("POST", "/api/auth/login", {"username": "vic", "password": PASSWORD})
    assert viewer.request("POST", "/api/workspaces/demo/move/fresh", {}, raw=True)[0].status == 403  # operators only
    c = Client(server.server_address[1])
    c.request("POST", "/api/auth/login", {"username": "ops", "password": PASSWORD})
    guarded = [REPO / "out" / "capture.json", REPO / "out" / "results.json", REPO / "out" / "ledger.jsonl"]
    before = {p: hashlib.sha256(p.read_bytes()).hexdigest() for p in guarded}
    runs_before = set((REPO / "runs").iterdir())
    lab_before = {pid for pid, _ in _lab_servers()}
    r, body = c.request("POST", "/api/workspaces/demo/move/fresh", {}, raw=True)
    assert r.status == 200, body
    f = json.loads(body)
    assert f["fresh_run"] and f["run_id"] and "not signed" in f["note"]
    every = f["sessions"] + f["refused_attempts"]
    assert every and all(s["endpoint"].startswith("127.0.0.1:") for s in every)  # loopback lab only
    assert all(s["transcript_verified"] and s["messages"] for s in every)
    hy = next(s for s in f["sessions"] if s["service_id"] == "hybrid")
    assert hy["negotiated_group"] == "X25519MLKEM768" and hy["messages"][0]["key_share"][0]["group"] == "X25519MLKEM768"
    assert any(g["service_id"] == "hybrid" and g["result"] == "PASS" for g in f["gates"]["downgrade"])
    from atlas_web.config import data_dir
    assert (data_dir() / f["log"]).is_file()  # logged under the (git-ignored) data dir
    assert {p: hashlib.sha256(p.read_bytes()).hexdigest() for p in guarded} == before  # results, capture, ledger untouched
    assert set((REPO / "runs").iterdir()) == runs_before
    assert {pid for pid, _ in _lab_servers()} <= lab_before  # the fresh run stopped every lab s_server it started
