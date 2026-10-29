"""/api/quantum: status names the backend; a run returns a scored result and names its backend (never hardware)."""

import socket

from .atlas_web_helpers import PASSWORD, Client, start_server


def test_status_and_run_fall_back_to_the_local_simulator(monkeypatch, tmp_path):
    from atlas_web import quantum

    monkeypatch.setattr(quantum, "cloud_status", lambda timeout_s=15.0: {"sdk": "qpiai-quantum", "sdk_version": "0.3.0", "auth_env": "QCLOUD_API_KEY",
                                                                          "auth_configured": False, "reachable": False, "devices": [], "error": "QCLOUD_API_KEY is not set"})
    srv = start_server(monkeypatch, tmp_path)
    try:
        srv.app.store.create_user("vic", PASSWORD, "viewer")
        anon = Client(srv.server_address[1])
        assert anon.get("/api/quantum/status")[0] == 401
        c = Client(srv.server_address[1])
        assert c.login("vic")[0] == 200
        status, st = c.get("/api/quantum/status")
        assert status == 200 and st["backend"] == "Local simulator" and st["hardware"] is False and st["fallback_reason"]
        assert "QCLOUD_API_KEY=" not in str(st)
        real = socket.socket.connect
        monkeypatch.setattr(socket.socket, "connect", lambda self, a: real(self, a) if a[0] == "127.0.0.1" else (_ for _ in ()).throw(AssertionError("network")))
        status, r = c.post("/api/quantum/run", {"ws": "demo", "p": 1})
        assert status == 200, r
        assert r["backend"] == "Local simulator" and r["backend_id"] == "QpiAI-QSV-Local" and r["hardware"] is False
        assert r["job_id"] is None and r["job_id_reason"] and r["shots"] > 0
        assert r["best_feasible"]["objective"] >= r["exact_optimum"]["objective"] - 1e-9
        assert c.post("/api/quantum/run", {"ws": "demo", "p": 7})[0] == 422
    finally:
        srv.shutdown()
