"""Test helpers for atlas_web: a live server on a free 127.0.0.1 port with its own temp data dir."""

import http.client
import json
import threading
import time
from http.cookies import SimpleCookie

PASSWORD = "correct horse battery"


class Client:
    def __init__(self, port: int):
        self.port = port
        self.cookies: dict = {}

    def request(self, method, path, body=None, headers=None, raw=False, csrf=True):
        h = dict(headers or {})
        data = body
        if isinstance(body, (dict, list)):
            data = json.dumps(body).encode()
            h.setdefault("Content-Type", "application/json")
        if self.cookies:
            h["Cookie"] = "; ".join(f"{k}={v}" for k, v in self.cookies.items())
        if csrf and method != "GET" and "atlas_csrf" in self.cookies:
            h.setdefault("X-CSRF-Token", self.cookies["atlas_csrf"])
        c = http.client.HTTPConnection("127.0.0.1", self.port, timeout=60)
        c.request(method, path, body=data, headers=h)
        r = c.getresponse()
        payload = r.read()
        for v in r.headers.get_all("Set-Cookie") or []:
            sc = SimpleCookie(v)
            for k, m in sc.items():
                if m.value:
                    self.cookies[k] = m.value
                else:
                    self.cookies.pop(k, None)
        c.close()
        if raw:
            return r, payload
        try:
            return r.status, json.loads(payload)
        except ValueError:
            return r.status, payload

    def get(self, path, **kw):
        return self.request("GET", path, **kw)

    def post(self, path, body=None, **kw):
        return self.request("POST", path, body if body is not None else {}, **kw)

    def login(self, username, password=PASSWORD):
        return self.post("/api/auth/login", {"username": username, "password": password})


def start_server(monkeypatch, tmp_path, **kw):
    monkeypatch.setenv("ATLAS_WEB_DATA", str(tmp_path / "data"))
    from atlas_web.server import make_server

    srv = make_server("127.0.0.1", 0, **kw)
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    return srv


def sse_events(port, path, cookies, until, timeout=30.0):
    """Read an SSE stream until `until(event, data)` is true; returns the (event, data) list."""
    c = http.client.HTTPConnection("127.0.0.1", port, timeout=timeout)
    c.request("GET", path, headers={"Cookie": "; ".join(f"{k}={v}" for k, v in cookies.items())})
    r = c.getresponse()
    assert r.status == 200, r.read()
    assert r.headers["Content-Type"].startswith("text/event-stream")
    out, event, deadline = [], None, time.monotonic() + timeout
    try:
        while time.monotonic() < deadline:
            line = r.fp.readline().decode()
            if not line:
                break
            line = line.rstrip("\n")
            if line.startswith(":"):
                out.append(("heartbeat", None))
                if until("heartbeat", None):
                    return out
            elif line.startswith("event: "):
                event = line[7:]
            elif line.startswith("data: "):
                data = json.loads(line[6:])
                out.append((event, data))
                if until(event, data):
                    return out
        raise AssertionError(f"SSE condition not met; got {out[-5:]}")
    finally:
        c.close()
