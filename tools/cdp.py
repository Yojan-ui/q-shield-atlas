"""Minimal Chrome DevTools Protocol client (stdlib only): launch headless Chrome, one websocket to the
browser, flat sessions per page target. Used by tools/route_check.py and tools/perf_check.py."""

import base64
import itertools
import json
import os
import queue
import shutil
import socket
import struct
import subprocess
import tempfile
import threading
import time
import urllib.request
from pathlib import Path

CHROME_CANDIDATES = [
    os.environ.get("CHROME", ""),
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "/Applications/Chromium.app/Contents/MacOS/Chromium",
    shutil.which("google-chrome") or "", shutil.which("chromium") or "", shutil.which("chromium-browser") or "",
]


def chrome_binary() -> str | None:
    return next((c for c in CHROME_CANDIDATES if c and Path(c).exists()), None)


class WebSocket:
    def __init__(self, url: str):
        assert url.startswith("ws://")
        hostport, _, path = url[5:].partition("/")
        host, _, port = hostport.partition(":")
        self.sock = socket.create_connection((host, int(port)), timeout=30)
        key = base64.b64encode(os.urandom(16)).decode()
        req = (f"GET /{path} HTTP/1.1\r\nHost: {hostport}\r\nUpgrade: websocket\r\nConnection: Upgrade\r\n"
               f"Sec-WebSocket-Key: {key}\r\nSec-WebSocket-Version: 13\r\n\r\n")
        self.sock.sendall(req.encode())
        buf = b""
        while b"\r\n\r\n" not in buf:
            buf += self.sock.recv(4096)
        head, _, rest = buf.partition(b"\r\n\r\n")
        if b" 101 " not in head.split(b"\r\n")[0]:
            raise RuntimeError(f"websocket handshake failed: {head[:200]!r}")
        self.buf = rest
        self.lock = threading.Lock()

    def send(self, text: str) -> None:
        data = text.encode()
        mask = os.urandom(4)
        n = len(data)
        hdr = bytes([0x81])
        if n < 126:
            hdr += bytes([0x80 | n])
        elif n < 65536:
            hdr += bytes([0x80 | 126]) + struct.pack(">H", n)
        else:
            hdr += bytes([0x80 | 127]) + struct.pack(">Q", n)
        masked = bytes(b ^ mask[i % 4] for i, b in enumerate(data))
        with self.lock:
            self.sock.sendall(hdr + mask + masked)

    def _read(self, n: int) -> bytes:
        while len(self.buf) < n:
            chunk = self.sock.recv(1 << 20)
            if not chunk:
                raise ConnectionError("websocket closed")
            self.buf += chunk
        out, self.buf = self.buf[:n], self.buf[n:]
        return out

    def recv(self) -> str | None:
        parts = []
        while True:
            b0, b1 = self._read(2)
            op, n = b0 & 0x0F, b1 & 0x7F
            if n == 126:
                n = struct.unpack(">H", self._read(2))[0]
            elif n == 127:
                n = struct.unpack(">Q", self._read(8))[0]
            payload = self._read(n)
            if op == 0x8:
                return None
            if op == 0x9:
                continue
            parts.append(payload)
            if b0 & 0x80:
                return b"".join(parts).decode()


class Browser:
    def __init__(self, extra_flags=()):
        binary = chrome_binary()
        if not binary:
            raise RuntimeError("Chrome not found (set CHROME=/path/to/chrome)")
        self.profile = tempfile.mkdtemp(prefix="atlas-cdp-")
        flags = ["--headless=new", "--remote-debugging-port=0", f"--user-data-dir={self.profile}", "--no-first-run",
                 "--no-default-browser-check", "--disable-extensions", "--disable-background-networking", "--disable-sync",
                 "--mute-audio", "--hide-scrollbars", *extra_flags]
        if "--disable-gpu" in extra_flags:  # no GPU and no software GL: WebGL unavailable (tests the 2D fallback)
            flags.append("--disable-software-rasterizer")
        else:
            flags += ["--enable-unsafe-swiftshader", "--use-angle=swiftshader"]
        self.proc = subprocess.Popen([binary, *flags, "about:blank"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        port_file = Path(self.profile) / "DevToolsActivePort"
        for _ in range(200):
            try:
                if port_file.exists() and port_file.read_text().strip():
                    break
            except PermissionError:  # Windows: Chrome still holds the file open while writing it
                pass
            time.sleep(0.05)
        port = int(port_file.read_text().split()[0])
        ver = json.loads(urllib.request.urlopen(f"http://127.0.0.1:{port}/json/version", timeout=10).read())
        self.version = ver.get("Browser")
        self.ws = WebSocket(ver["webSocketDebuggerUrl"])
        self.ids = itertools.count(1)
        self.pending: dict[int, queue.Queue] = {}
        self.listeners: dict[str, list] = {}
        self.plock = threading.Lock()
        threading.Thread(target=self._loop, daemon=True).start()

    def _loop(self):
        try:
            while (msg := self.ws.recv()) is not None:
                m = json.loads(msg)
                if "id" in m:
                    with self.plock:
                        q = self.pending.pop(m["id"], None)
                    if q:
                        q.put(m)
                else:
                    for fn in list(self.listeners.get(m.get("sessionId", ""), [])):
                        fn(m["method"], m.get("params", {}))
        except (ConnectionError, OSError):
            pass

    def send(self, method, params=None, session=None, timeout=60):
        i = next(self.ids)
        q: queue.Queue = queue.Queue()
        with self.plock:
            self.pending[i] = q
        msg = {"id": i, "method": method, "params": params or {}}
        if session:
            msg["sessionId"] = session
        self.ws.send(json.dumps(msg))
        r = q.get(timeout=timeout)
        if "error" in r:
            raise RuntimeError(f"{method}: {r['error']}")
        return r.get("result", {})

    def new_context(self) -> str:
        return self.send("Target.createBrowserContext", {"disposeOnDetach": True})["browserContextId"]

    def new_page(self, context: str | None = None):
        params = {"url": "about:blank"}
        if context:
            params["browserContextId"] = context
        tid = self.send("Target.createTarget", params)["targetId"]
        sid = self.send("Target.attachToTarget", {"targetId": tid, "flatten": True})["sessionId"]
        return Page(self, tid, sid)

    def close(self):
        try:
            self.send("Browser.close", timeout=5)
        except Exception:  # noqa: BLE001
            pass
        try:
            self.proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            self.proc.kill()
        shutil.rmtree(self.profile, ignore_errors=True)


class Page:
    def __init__(self, browser: Browser, target_id: str, session: str):
        self.b, self.target, self.session = browser, target_id, session
        self.events: list[tuple[str, dict]] = []
        browser.listeners[session] = [lambda m, p: self.events.append((m, p))]

    def send(self, method, params=None, timeout=60):
        return self.b.send(method, params, self.session, timeout)

    def eval(self, expr, timeout=30):
        r = self.send("Runtime.evaluate", {"expression": expr, "returnByValue": True, "awaitPromise": True}, timeout)
        if "exceptionDetails" in r:
            raise RuntimeError(f"eval failed: {r['exceptionDetails'].get('text')} {expr[:80]}")
        return r["result"].get("value")

    def wait_for(self, expr, timeout=20.0, interval=0.05):
        end = time.monotonic() + timeout
        while time.monotonic() < end:
            if self.eval(expr):
                return True
            time.sleep(interval)
        return False

    def screenshot(self, path: Path, full=False):
        params = {"format": "png", "captureBeyondViewport": full}
        data = self.send("Page.captureScreenshot", params, timeout=60)["data"]
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(base64.b64decode(data))

    def close(self):
        try:
            self.b.send("Target.closeTarget", {"targetId": self.target}, timeout=10)
        except Exception:  # noqa: BLE001
            pass
        self.b.listeners.pop(self.session, None)
