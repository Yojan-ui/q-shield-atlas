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
