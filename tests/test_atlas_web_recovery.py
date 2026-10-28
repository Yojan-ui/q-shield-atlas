"""Kill the atlas_web server (SIGKILL) in the middle of a pipeline run and restart it: the interrupted run is
closed as INTERRUPTED (its event log ends with run_end), its step process group and lab services are gone,
and a new run starts and passes."""

import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

import pytest

from .atlas_web_helpers import PASSWORD, Client, sse_events

REPO = Path(__file__).resolve().parent.parent


def start(data, port):
    env = {**os.environ, "ATLAS_WEB_DATA": str(data), "QSHIELD_FORBID_PLATFORM": "1"}
    p = subprocess.Popen([sys.executable, "-m", "atlas_web", "--port", str(port), "--no-browser"], cwd=REPO, env=env,
                         stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    for _ in range(100):
        try:
            if Client(port).get("/api/health")[0] == 200:
                return p
        except OSError:
            time.sleep(0.1)
    p.kill()
    raise RuntimeError("server did not start")


def free_port():
    import socket

    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def lab_servers():
    import psutil

    return [p.pid for p in psutil.process_iter(["cmdline"]) if (p.info["cmdline"] or [""])[0].endswith("openssl")
            and "s_server" in p.info["cmdline"] and any("qshield-" in c for c in p.info["cmdline"])]


def test_kill_and_restart_mid_run_recovers(tmp_path):
    if not os.environ.get("QPIAI_OPT_API_KEY"):
        pytest.skip("QPIAI_OPT_API_KEY not set")
    from detect.live_probe import openssl_binary

    try:
        openssl_binary()
    except Exception as exc:  # noqa: BLE001
        pytest.skip(f"OpenSSL >= 3.5 missing: {exc}")
    data = tmp_path / "data"
    os.environ["ATLAS_WEB_DATA"] = str(data)
    try:
        from atlas_web.auth import Store

        Store(data / "atlas.db").create_user("ops", PASSWORD, "operator")
    finally:
        os.environ.pop("ATLAS_WEB_DATA", None)
    port = free_port()
    srv = start(data, port)
    try:
        c = Client(port)
        c.login("ops")
        assert c.post("/api/workspaces", {"id": "bank", "template": "mock_bank"})[0] == 201
        status, res = c.post("/api/workspaces/bank/runs", {})
        assert status == 202
        rid = res["run_id"]
        sse_events(port, f"/api/workspaces/bank/runs/{rid}/events", c.cookies,
                   lambda e, d: e == "step_start" and d.get("step") == "capture", timeout=300)
        f = data / "active_step.json"
        for _ in range(50):
            if f.exists() and json.loads(f.read_text() or "{}").get("step") == "capture":
                break
            time.sleep(0.05)
        active = json.loads(f.read_text())
        srv.send_signal(signal.SIGKILL)  # no cleanup at all
        srv.wait(timeout=10)
        srv = start(data, port)
        c = Client(port)
        c.login("ops")
        runs = c.get("/api/workspaces/bank/runs")[1]
        assert runs["active"] is None
        row = next(r for r in runs["runs"] if r["id"] == rid)
        assert row["status"] == "INTERRUPTED" and "interrupted" in row["detail"]["tail"][0]
        evs = sse_events(port, f"/api/workspaces/bank/runs/{rid}/events", c.cookies, lambda e, d: e == "run_end", timeout=30)
        assert evs[-1][1]["status"] == "INTERRUPTED"
        time.sleep(0.5)
        with pytest.raises(ProcessLookupError):
            os.killpg(active["pgid"], 0)  # the interrupted step's process group is gone
        assert lab_servers() == []
        assert not (data / "active_step.json").exists()
        status, res = c.post("/api/workspaces/bank/runs", {})
        assert status == 202
        end = sse_events(port, f"/api/workspaces/bank/runs/{res['run_id']}/events", c.cookies, lambda e, d: e == "run_end", timeout=900)
        assert end[-1][1]["status"] == "PASS", end[-1][1]["tail"]
    finally:
        srv.kill()
        srv.wait(timeout=10)
