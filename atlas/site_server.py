"""Backend for the showcase site (python -m atlas site): read-only, stdlib only, 127.0.0.1.

Serves site/ plus read-only JSON built from the current out/results.json and ledger:
  /api/results     results.json as is
  /api/ledger      entries (index, type, payload_ref, ts), root, alg/backend, and a read-only verify
  /api/handshakes  handshake evidence + pq_handshake / pq_auth / downgrade gates + compat matrix
  /api/events      Server-Sent Events: pushes {"changed": [...]} when results.json or the ledger file changes
Also serves the vendored three.js (hash-checked, from viz/vendor) and the 2D viz as the no-WebGL fallback.
Nothing is ever written: verification runs in memory (it does not record out/ledger_verify.json), and
every other path (repo root, keys/, .env.sh, runs/, out/ledger.jsonl) is 404.
"""

import argparse
import json
import posixpath
import threading
import time
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlsplit

from contracts.manifest import sha256_hex

REPO = Path(__file__).resolve().parent.parent
HOST = "127.0.0.1"  # loopback only, never all interfaces
SITE = REPO / "site"
VIZ = REPO / "viz"
TYPES = {".html": "text/html; charset=utf-8", ".js": "text/javascript; charset=utf-8", ".css": "text/css; charset=utf-8",
         ".json": "application/json", ".txt": "text/plain; charset=utf-8"}


class SiteData:
    """Reads (never writes) results.json and the ledger; caches API payloads until a file changes."""

    def __init__(self, results_path: Path, ledger_path: Path | None = None, public_key: Path | None = None, repo: Path = REPO):
        self.results_path, self.repo = Path(results_path), Path(repo)
        self._ledger_path, self._public_key = ledger_path, public_key
        self.lock = threading.Lock()
        self.cache: dict[str, bytes] = {}
        self.stamp = self._stamp()

    def results(self) -> dict | None:
        try:
            return json.loads(self.results_path.read_text())
        except (OSError, ValueError):
            return None

    def ledger_path(self, results: dict | None) -> Path | None:
        if self._ledger_path:
            return Path(self._ledger_path)
        if results and results.get("ledger"):
            return self.repo / results["ledger"]["ledger_ref"]
        return None

    def _stamp(self) -> tuple:
        lp = self.ledger_path(self.results())
        def mt(p):
            try:
                return p.stat().st_mtime_ns, p.stat().st_size
            except (OSError, AttributeError):
                return None
        return mt(self.results_path), mt(lp)

    def changed(self) -> list[str]:
        new = self._stamp()
        diff = [name for name, a, b in zip(("results", "ledger"), self.stamp, new) if a != b]
        if diff:
            with self.lock:
                self.stamp = new
                self.cache.clear()
        return diff

    def payload(self, name: str) -> bytes:
        with self.lock:
            if name not in self.cache:
                self.cache[name] = json.dumps(getattr(self, f"_{name}")(), ensure_ascii=False).encode()
            return self.cache[name]

    def _results(self):
        return self.results()

    def _handshakes(self):
        r = self.results() or {}
        he, g = r.get("handshake_evidence"), r.get("gates") or {}
        if not he:
            return None
        return {"run_id": he["run_id"], "ts": he["ts"], "openssl_version": he["openssl_version"], "note": he["note"],
                "sessions": he["sessions"], **{k: g.get(k) for k in ("pq_handshake", "pq_auth", "downgrade", "compat_matrix")},
                "gates_run_id": g.get("run_id")}

    def _ledger(self):
        r = self.results()
        if not r or not r.get("ledger"):
            return None
        from ledger.log import read_entries

        path = self.ledger_path(r)
        entries = read_entries(path) if path and path.exists() else []
        out = {**{k: r["ledger"][k] for k in ("root", "entry_count", "alg", "backend", "pubkey_fp")},
               "entries": [{k: e[k] for k in ("index", "type", "payload_ref", "ts")} for e in entries],
               "recorded_verification": r.get("ledger_verification"), "live_verification": None}
        try:  # read-only check; deliberately not recorded anywhere
            from ledger.__main__ import default_public_key
            from ledger.backend import detect
            from ledger.verify import verify

            rep = verify(path, self._public_key or default_public_key(), detect(), self.repo, r["ledger"])
            out["live_verification"] = {"ok": rep["ok"], "entries_checked": rep["entries_checked"],
                                        "first_failure": rep["first_failure"], "checked_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
        except Exception as exc:  # e.g. no OpenSSL with ML-DSA: report, don't invent
            out["live_verification"] = {"ok": None, "error": f"{type(exc).__name__}: {exc}"[:200]}
        return out


def static_path(url_path: str) -> Path | None:
    """Allowlist: site/ files, vendored three.js, and the 2D viz fallback (+ results.json for it)."""
    path = posixpath.normpath(unquote(urlsplit(url_path).path))
    if ".." in path.split("/") or path.endswith((".py", ".pyc")):
        return None
    if path in ("/", "/index.html"):
        return SITE / "index.html"
    if path.startswith("/vendor/"):
        manifest = json.loads((VIZ / "vendor" / "MANIFEST.json").read_text())
        name = path.removeprefix("/vendor/")
        f = VIZ / "vendor" / name
        if name in manifest["files"] and f.exists() and sha256_hex(f.read_bytes()) == manifest["files"][name]:
            return f
        return None
    if path in ("/viz", "/viz/"):
        return VIZ / "index.html"
    if path.startswith("/viz/"):
        return VIZ / path.removeprefix("/viz/")
    if path.startswith(("/js/", "/css/")) or path in ("/style.css",):
        return SITE / path.lstrip("/")
    return None


def make_handler(data: SiteData, results_for_viz: Path):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def _send(self, code: int, body: bytes, ctype: str):
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            path = urlsplit(self.path).path
            if path in ("/api/results", "/api/ledger", "/api/handshakes"):
                return self._send(200, data.payload(path.removeprefix("/api/")), TYPES[".json"])
            if path == "/api/events":
                return self._events()
            if path == "/out/results.json":  # for the 2D viz fallback only
                body = results_for_viz.read_bytes() if results_for_viz.exists() else b"null"
                return self._send(200, body, TYPES[".json"])
            f = static_path(path)
            if f is None or not f.is_file():
                return self._send(404, b"not served", TYPES[".txt"])
            self._send(200, f.read_bytes(), TYPES.get(f.suffix, "application/octet-stream"))

        def _events(self):
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            try:
                self.wfile.write(b"event: hello\ndata: {}\n\n")
                self.wfile.flush()
                last_ping = time.monotonic()
                while True:
                    diff = data.changed()
                    if diff:
                        self.wfile.write(f"event: update\ndata: {json.dumps({'changed': diff})}\n\n".encode())
                        self.wfile.flush()
                    if time.monotonic() - last_ping > 15:
                        self.wfile.write(b": ping\n\n")
                        self.wfile.flush()
                        last_ping = time.monotonic()
                    time.sleep(0.25)
            except (BrokenPipeError, ConnectionResetError, OSError):
                return

    return Handler


def make_server(results_path: Path = REPO / "out" / "results.json", port: int = 0, **kw) -> ThreadingHTTPServer:
    data = SiteData(results_path, **kw)
    srv = ThreadingHTTPServer((HOST, port), make_handler(data, Path(results_path)))
    srv.daemon_threads = True
    srv.site_data = data
    return srv


def main(argv=None):
    ap = argparse.ArgumentParser(prog="python -m atlas site", description=__doc__)
    ap.add_argument("--port", type=int, default=0)
    ap.add_argument("--no-browser", action="store_true")
    ap.add_argument("--results", type=Path, default=REPO / "out" / "results.json")
    args = ap.parse_args(argv)
    srv = make_server(args.results, args.port)
    url = f"http://{HOST}:{srv.server_address[1]}/"
    print(f"Q-Shield Atlas site at {url} (read-only; Ctrl+C to stop)", flush=True)
    if not args.no_browser:
        threading.Timer(0.3, webbrowser.open, args=(url,)).start()
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        srv.server_close()
