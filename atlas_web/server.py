"""HTTP server for atlas_web (stdlib ThreadingHTTPServer, 127.0.0.1 by default).

Serves only atlas_web/static/, the hash-checked vendored three.js and the JSON API. Every other GET that
looks like a file, and anything under keys/, runs/, config/, out/, data/, src/ or ending in .py/.sh, is 404;
every other non-API GET returns index.html so client routes deep-link and refresh. Errors are
{"error": {"code", "message"}}, never a traceback.
"""

import hashlib
import hmac
import json
import posixpath
import re
import subprocess
import sys
import tempfile
import threading
import time
import traceback
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlsplit

from contracts.manifest import sha256_hex
from contracts.stages import STAGES

from . import calibration, intake
from . import workspaces as wsmod
from .auth import AuthError, Store, has_role
from .config import REPO, STATIC, data_dir, limits
from .config import settings
from .runner import RunManager, bench_steps, parse_probes, pipeline_steps, preflight, reference_presets
from .workspaces import WorkspaceError

VIZ_VENDOR = REPO / "viz" / "vendor"
ADDONS = STATIC / "vendor" / "three-addons"
TYPES = {".html": "text/html; charset=utf-8", ".js": "text/javascript; charset=utf-8", ".css": "text/css; charset=utf-8",
         ".json": "application/json", ".svg": "image/svg+xml", ".png": "image/png", ".txt": "text/plain; charset=utf-8",
         ".glsl": "text/plain; charset=utf-8", ".ico": "image/x-icon", ".woff2": "font/woff2"}
DENY_PREFIXES = {"keys", "runs", "config", "out", "data", "src", "atlas_web", "ledger", "tests", "detect", "schedule",
                 "capture", "gates", "qaoa", "contracts", "atlas", "site", "docs", ".git", ".cache", "workspaces"}
DENY_SUFFIXES = (".py", ".pyc", ".sh", ".env", ".key", ".pem", ".db", ".jsonl", ".log", ".zip")
CSP = ("default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data: blob:; connect-src 'self'; "
       "font-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'; form-action 'self'")
JSON_MAX = 1 << 20
SESSION_COOKIE, CSRF_COOKIE = "atlas_session", "atlas_csrf"


class ApiError(Exception):
    def __init__(self, status: int, code: str, message: str, fields: dict | None = None):
        super().__init__(message)
        self.status, self.code, self.message, self.fields = status, code, message, fields


def file_stamp(p: Path | None):
    try:
        st = p.stat()
        return st.st_mtime_ns, st.st_size
    except (OSError, AttributeError):
        return None


def vendored(name: str) -> Path | None:
    """three.js core from viz/vendor and addons from static/vendor/three-addons, served only if hashes match."""
    for base, prefix in ((VIZ_VENDOR, ""), (ADDONS, "three-addons/")):
        if not name.startswith(prefix) or (prefix == "" and "/" in name):
            continue
        rel = name.removeprefix(prefix)
        mf = base / "MANIFEST.json"
        if not mf.exists() or "/" in rel:
            continue
        files = json.loads(mf.read_text())["files"]
        f = base / rel
        if rel in files and f.is_file() and sha256_hex(f.read_bytes()) == files[rel]:
            return f
    return None


class App:
    """State shared by all requests."""

    def __init__(self, kiosk: bool = False, demo: bool = False):
        lim = limits()
        self.store = Store(data_dir() / "atlas.db", lim["session_hours"], lim["login_failures"], lim["login_window_s"])
        self.runs = RunManager(self.store)
        self.kiosk, self.demo = kiosk, demo
        self.tamper_lock = threading.Lock()
        self.tamper_last = 0.0
        self.review_lock = threading.Lock()  # one signed review decision at a time
        self.cache: dict = {}
        self.cache_lock = threading.Lock()

    def cached(self, key, stamp, fn):
        with self.cache_lock:
            hit = self.cache.get(key)
            if hit and hit[0] == stamp:
                return hit[1]
        value = fn()
        with self.cache_lock:
            self.cache[key] = (stamp, value)
        return value


# ---------------- workspace data (read-only) ----------------

def load_results(ws) -> dict | None:
    try:
        return json.loads(ws.results.read_text())
    except (OSError, ValueError):
        return None


def bench_payload(ws) -> dict:
    entries = ((load_results(ws) or {}).get("ledger") or {}).get("entries", [])

    def part(name, etype):
        f = ws.out / name
        if not f.exists():
            return None, None
        b = json.loads(f.read_text())
        ref = f"runs/{b['run_id']}/manifest.json"
        return b, next((e["index"] for e in entries if e["type"] == etype and e["payload_ref"].endswith(ref)), None)

    b, idx = part("bench.json", "bench.run")
    c, cidx = part("bench_crypto.json", "bench_crypto.run")
    missing = "not in this snapshot (python -m bench)" if ws.read_only else "not yet run"
    return {"workspace": ws.id, "bench": b, "ledger_index": idx, "crypto": c, "crypto_ledger_index": cidx,
            "status_text": None if b else missing}


def ledger_path(ws, results) -> Path | None:
    if results and results.get("ledger"):
        return ws.root / results["ledger"]["ledger_ref"]
    return None


def ledger_payload(ws) -> dict:
    r = load_results(ws)
    if not r or not r.get("ledger"):
        return {"available": False, "status_text": "not yet run"}
    from ledger.log import read_entries

    path = ledger_path(ws, r)
    entries = read_entries(path) if path and path.exists() else []
    out = {"available": True, **{k: r["ledger"][k] for k in ("root", "entry_count", "alg", "backend", "pubkey_fp", "ledger_ref")},
           "entries": [{k: e.get(k) for k in ("index", "type", "payload_ref", "payload_hash", "prev_hash", "ts")} for e in entries],
           "recorded_verification": r.get("ledger_verification"), "live_verification": None}
    try:  # read-only check, never recorded (the CLI's verify of the anchored ledger would rewrite results.json)
        from ledger.__main__ import default_public_key
        from ledger.backend import detect
        from ledger.verify import verify

        rep = verify(path, default_public_key(ws.keys), detect(), ws.root, r["ledger"])
        out["live_verification"] = {"ok": rep["ok"], "entries_checked": rep["entries_checked"], "root": rep.get("root"),
                                    "first_failure": rep["first_failure"], "checked_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                                    "recorded": False}
    except Exception as exc:  # noqa: BLE001 - e.g. no OpenSSL with ML-DSA: report it, don't invent a result
        out["live_verification"] = {"ok": None, "status_text": f"not verified: {type(exc).__name__}: {exc}"[:200], "recorded": False}
    return out


def workspace_summary(app, ws) -> dict:
    """Switcher metadata: type badge, last run, ledger verified, asset count (all read from recorded files)."""
    src = (ws.settings.get("source") or {}).get("kind")
    kind = "DEMO SNAPSHOT" if ws.read_only else "REAL REPO" if src == "git" else "CUSTOMER"
    r = app.cached(("results", ws.id), file_stamp(ws.results), lambda: load_results(ws))
    with app.store.db() as c:
        row = c.execute("SELECT started, status FROM runs WHERE workspace=? ORDER BY started DESC LIMIT 1", (ws.id,)).fetchone()
    v = (r or {}).get("ledger_verification")
    return {**ws.public(), "type": kind, "last_run": {"ts": row["started"], "status": row["status"]} if row else None,
            "generated_at": (r or {}).get("generated_at"), "assets": len(r["assets"]) if r else None,
            "ledger_verified": None if not v else bool(v["ok"] and v["root"] == (r.get("ledger") or {}).get("root"))}


def ledger_cli_flags(ws) -> list[str]:
    return ["--out-dir", str(ws.out), "--runs", str(ws.runs), "--root", str(ws.root), "--keys-dir", str(ws.keys)]


def proof_payload(ws, n: int) -> dict:
    r = load_results(ws)
    path = ledger_path(ws, r)
    if not path or not path.exists():
        raise ApiError(404, "no_ledger", "this workspace has no ledger yet (not yet run)")
    proc = subprocess.run([sys.executable, "-m", "ledger", "proof", str(n), "--ledger", str(path), *ledger_cli_flags(ws)],
                          cwd=REPO, capture_output=True, text=True, timeout=60)
    try:
        return json.loads(proc.stdout)
    except ValueError:
        raise ApiError(404, "no_entry", f"no ledger entry #{n}") from None


def tamper_demo(ws, index: int | None) -> dict:
    """Edit one entry in a temp COPY, verify the copy with the ledger CLI, return the failing index and reason."""
    r = load_results(ws)
    real = ledger_path(ws, r)
    if not real or not real.exists():
        raise ApiError(404, "no_ledger", "this workspace has no ledger yet (not yet run)")
    from ledger.log import canonical, read_entries

    guarded = [real, ws.results, ws.out / "ledger_verify.json", ws.out / "ledger.json"]
    before = {str(p): sha256_hex(p.read_bytes()) for p in guarded if p.exists()}
    entries = read_entries(real)
    i = min(2, len(entries) - 1) if index is None else index
    if not 0 <= i < len(entries):
        raise ApiError(422, "bad_index", f"index must be between 0 and {len(entries) - 1}")
    with tempfile.TemporaryDirectory(prefix="atlas-tamper-") as tmp:
        copy = Path(tmp) / "ledger.jsonl"
        entries[i]["type"] = f"{entries[i]['type']}-FORGED"
        copy.write_text("".join(canonical(e).decode() + "\n" for e in entries))
        proc = subprocess.run([sys.executable, "-m", "ledger", "verify", "--ledger", str(copy), *ledger_cli_flags(ws)],
                              cwd=REPO, capture_output=True, text=True, timeout=120)
    after = {str(p): sha256_hex(p.read_bytes()) for p in guarded if p.exists()}
    if after != before:  # must never happen; refuse to report a result if it did
        raise ApiError(500, "real_ledger_changed", "the real ledger or results changed during the tamper demo")
    m = re.search(r"FAIL at index (\d+): (.+)", proc.stdout)
    real_sha = before[str(real)]
    return {"edited_index": i, "edited_field": "type", "exit_code": proc.returncode,
            "index": int(m.group(1)) if m else None, "reason": m.group(2).strip() if m else proc.stdout.strip()[-300:],
            "real_ledger_sha256_before": real_sha, "real_ledger_sha256_after": after[str(real)],
            "real_ledger_unchanged": True, "recorded": False,
            "note": "verified a temporary copy; the real ledger and results.json were not touched"}


# ---------------- request handler ----------------

def make_handler(app: App):
    class Handler(BaseHTTPRequestHandler):
        server_version = "atlas_web"
        sys_version = ""
        protocol_version = "HTTP/1.1"

        def log_message(self, *a):
            pass

        # ----- plumbing -----
        def _headers(self, code, ctype, length, extra=None):
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            if length is not None:
                self.send_header("Content-Length", str(length))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("X-Frame-Options", "DENY")
            self.send_header("Referrer-Policy", "no-referrer")
            if not any(k == "Content-Security-Policy" for k, _ in (extra or [])):
                self.send_header("Content-Security-Policy", CSP)
            for k, v in (extra or []):
                self.send_header(k, v)
            self.end_headers()

        def send_body(self, code, body: bytes, ctype, extra=None):
            self._headers(code, ctype, len(body), extra)
            if self.command != "HEAD":
                self.wfile.write(body)

        def send_json(self, code, obj, extra=None):
            self.send_body(code, json.dumps(obj, ensure_ascii=False).encode(), TYPES[".json"], extra)

        def send_error_json(self, status, code, message, fields=None):
            err = {"code": code, "message": message}
            if fields:
                err["fields"] = fields
            self.send_json(status, {"error": err})

        def cookies(self) -> dict:
            c = SimpleCookie()
            try:
                c.load(self.headers.get("Cookie", ""))
            except Exception:  # noqa: BLE001
                return {}
            return {k: m.value for k, m in c.items()}

        def user(self) -> dict | None:
            if not hasattr(self, "_user"):
                self._user = app.store.session(self.cookies().get(SESSION_COOKIE))
            return self._user

        def need(self, role: str) -> dict:
            u = self.user()
            if not u:
                raise ApiError(401, "unauthenticated", "sign in first")
            if not has_role(u, role):
                raise ApiError(403, "forbidden", f"this needs the {role} role (you are {u['role']})")
            return u

        def check_csrf(self, u: dict) -> None:
            header, cookie = self.headers.get("X-CSRF-Token", ""), self.cookies().get(CSRF_COOKIE, "")
            if not (header and hmac.compare_digest(header, cookie) and hmac.compare_digest(header, u["csrf"])):
                raise ApiError(403, "csrf", "missing or invalid CSRF token; reload the page")

        def check_origin(self) -> None:
            origin = self.headers.get("Origin")
            if origin and urlsplit(origin).netloc != self.headers.get("Host"):
                raise ApiError(403, "bad_origin", "cross-origin request refused")

        def body_json(self) -> dict:
            n = int(self.headers.get("Content-Length") or 0)
            if n > JSON_MAX:
                raise ApiError(413, "too_large", "request body too large")
            if n and "application/json" not in (self.headers.get("Content-Type") or ""):
                raise ApiError(415, "json_required", "send application/json")
            try:
                data = json.loads(self.rfile.read(n) or b"{}")
            except ValueError:
                raise ApiError(400, "bad_json", "request body is not valid JSON") from None
            if not isinstance(data, dict):
                raise ApiError(400, "bad_json", "request body must be a JSON object")
            return data

        # ----- dispatch -----
        def do_GET(self):
            self._dispatch("GET")

        def do_HEAD(self):
            self._dispatch("GET")

        def do_POST(self):
            self._dispatch("POST")

        def do_PUT(self):
            self._dispatch("PUT")

        def do_DELETE(self):
            self._dispatch("DELETE")

        def _dispatch(self, method):
            url = urlsplit(self.path)
            path = unquote(url.path)
            self.query = {k: v[-1] for k, v in parse_qs(url.query).items()}
            try:
                if path.startswith("/api/") or path == "/api":
                    if method != "GET":
                        self.check_origin()
                    return self.api(method, path)
                if method != "GET":
                    raise ApiError(405, "method_not_allowed", "method not allowed")
                return self.static(path)
            except ApiError as e:
                self.send_error_json(e.status, e.code, e.message, e.fields)
            except (AuthError, WorkspaceError) as e:
                self.send_error_json(e.status, e.code, e.message, getattr(e, "fields", None))
            except (BrokenPipeError, ConnectionResetError):
                pass
            except Exception:  # noqa: BLE001 - logged server-side only
                traceback.print_exc(file=sys.stderr)
                try:
                    self.send_error_json(500, "internal", "internal error; see the server log")
                except OSError:
                    pass

        # ----- static + SPA fallback -----
        def static(self, path):
            norm = posixpath.normpath(path)
            parts = [p for p in norm.split("/") if p]
            if ".." in path.split("/") or (parts and parts[0] in DENY_PREFIXES) or norm.endswith(DENY_SUFFIXES) \
                    or any(p.startswith(".") for p in parts):
                return self.send_body(404, b"not found", TYPES[".txt"])
            if parts[:1] == ["vendor"]:
                f = vendored("/".join(parts[1:]))
                if not f:
                    return self.send_body(404, b"not found", TYPES[".txt"])
                return self.send_body(200, f.read_bytes(), TYPES.get(f.suffix, "application/octet-stream"))
            if "/".join(parts) in ("viz/data.js", "viz/render2d.js"):  # the shared viz data layer and the 2D fallback
                f = REPO / "viz" / parts[1]
                return self.send_body(200, f.read_bytes(), TYPES[".js"])
            if parts[:1] == ["assets"]:
                f = (STATIC / "/".join(parts[1:])).resolve()
                if not str(f).startswith(str(STATIC.resolve()) + "/") or not f.is_file() or f.suffix not in TYPES \
                        or "vendor" in f.relative_to(STATIC.resolve()).parts[:1]:
                    return self.send_body(404, b"not found", TYPES[".txt"])
                return self.send_body(200, f.read_bytes(), TYPES[f.suffix])
            if parts and "." in parts[-1]:  # looks like a file but is not an allowlisted asset
                return self.send_body(404, b"not found", TYPES[".txt"])
            index = STATIC / "index.html"
            return self.send_body(200, index.read_bytes(), TYPES[".html"])

        # ----- API -----
        def api(self, method, path):
            parts = [p for p in path.split("/") if p][1:]  # drop "api"
            route = (method, *parts[:1])
            if route == ("GET", "health"):
                return self.send_json(200, {"ok": True, "service": "atlas_web", "time": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())})
            if parts[:1] == ["auth"] and method == "POST" and len(parts) == 2:
                return self.auth(parts[1])
            if route == ("GET", "me"):
                u = self.user()
                return self.send_json(200, {"user": {k: u[k] for k in ("username", "role", "expires")} if u else None,
                                            "kiosk": app.kiosk, "demo": app.demo})
            if route == ("GET", "stages"):  # contracts/stages.json: the same stage ids and step names as the runner
                return self.send_json(200, {"stages": STAGES})
            if route == ("GET", "events"):
                ws = self.workspace(self.query.get("ws", "demo"))
                return self.file_events(ws)
            if method != "GET":
                self.check_csrf(self.need("viewer"))
            if route == ("GET", "preflight"):
                self.need("operator")
                ws = wsmod.get(app.store, self.query["ws"]) if self.query.get("ws") else None
                return self.send_json(200, preflight(ws))
            if route == ("GET", "reference-endpoints"):
                self.need("viewer")
                r = settings()["reference_endpoints"]
                return self.send_json(200, {"label": r["label"], "verified": r["verified"],
                                            "endpoints": [{k: e[k] for k in ("id", "service", "host", "port", "expect", "operator")} for e in r["endpoints"]]})
            if parts[:1] == ["quantum"]:  # QpiAI backend: status + one live QAOA run (cloud if enabled, else local simulator)
                from . import quantum

                self.need("viewer")
                if method == "GET" and parts[1:] == ["status"]:
                    return self.send_json(200, quantum.status())
                if method == "POST" and parts[1:] == ["run"]:
                    b = self.body_json()
                    ws = self.workspace(str(b.get("ws", "demo")))
                    f = ws.out / "schedule.json"
                    if not f.exists() or not json.loads(f.read_text()).get("assets"):
                        raise ApiError(409, "not_run", "this workspace has no migration plan to optimise yet")
                    p = b.get("p", 1)
                    if p not in (1, 2, 3):
                        raise ApiError(422, "bad_p", "p must be 1, 2 or 3")
                    box: dict = {}

                    def work():
                        try:
                            box["ok"] = quantum.run(json.loads(f.read_text()), p)
                        except Exception as exc:  # noqa: BLE001 - JSON error, never a traceback
                            box["err"] = exc

                    t = threading.Thread(target=work, daemon=True)
                    t.start()
                    t.join(120)
                    if t.is_alive():
                        raise ApiError(504, "timeout", "the quantum run took longer than 120 s")
                    if "err" in box:
                        e = box["err"]
                        raise ApiError(409 if str(e).startswith("busy") else 502, "busy" if str(e).startswith("busy") else "quantum_failed", str(e)[:300])
                    return self.send_json(200, box["ok"])
                raise ApiError(404, "not_found", "quantum routes: GET status, POST run")
            if parts[:1] == ["users"]:
                return self.users(method, parts[1:])
            if parts[:1] == ["workspaces"]:
                return self.workspaces(method, parts[1:])
            raise ApiError(404, "not_found", f"no API route {method} {path}")

        def auth(self, action):
            if action == "login":
                if "application/json" not in (self.headers.get("Content-Type") or ""):
                    raise ApiError(415, "json_required", "send application/json")
                b = self.body_json()
                s = app.store.login(str(b.get("username", "")), str(b.get("password", "")))
                age = round(s["expires"] - time.time())
                return self.send_json(200, {"user": {"username": s["username"], "role": s["role"], "expires": s["expires"]}},
                                      [("Set-Cookie", f"{SESSION_COOKIE}={s['token']}; HttpOnly; SameSite=Strict; Path=/; Max-Age={age}"),
                                       ("Set-Cookie", f"{CSRF_COOKIE}={s['csrf']}; SameSite=Strict; Path=/; Max-Age={age}")])
            if action == "logout":
                u = self.user()
                if u:
                    self.check_csrf(u)
                    app.store.logout(self.cookies().get(SESSION_COOKIE))
                return self.send_json(200, {"ok": True},
                                      [("Set-Cookie", f"{SESSION_COOKIE}=; HttpOnly; SameSite=Strict; Path=/; Max-Age=0"),
                                       ("Set-Cookie", f"{CSRF_COOKIE}=; SameSite=Strict; Path=/; Max-Age=0")])
            raise ApiError(404, "not_found", "no such auth action")

        def users(self, method, rest):
            self.need("admin")
            if method == "GET" and not rest:
                return self.send_json(200, {"users": app.store.list_users()})
            if method == "POST" and not rest:
                b = self.body_json()
                try:
                    app.store.create_user(str(b.get("username", "")), str(b.get("password", "")), str(b.get("role", "")))
                except ValueError as e:
                    raise ApiError(422, "invalid_user", str(e)) from None
                return self.send_json(201, {"users": app.store.list_users()})
            if method == "DELETE" and len(rest) == 1:
                if rest[0] == self.user()["username"]:
                    raise ApiError(422, "self_delete", "you cannot delete your own account while signed in")
                if not app.store.delete_user(rest[0]):
                    raise ApiError(404, "not_found", f"no user {rest[0]!r}")
                return self.send_json(200, {"users": app.store.list_users()})
            raise ApiError(404, "not_found", "no such users route")

        def workspace(self, ws_id, public_demo=False):
            if not (public_demo and ws_id == "demo"):
                self.need("viewer")
            return wsmod.get(app.store, ws_id)

        def workspaces(self, method, rest):
            if not rest:
                if method == "GET":
                    self.need("viewer")
                    return self.send_json(200, {"workspaces": [workspace_summary(app, w) for w in wsmod.list_all(app.store)],
                                                "templates": {k: v["label"] for k, v in wsmod.TEMPLATES.items()}})
                if method == "POST":
                    u = self.need("operator")
                    b = self.body_json()
                    ws = wsmod.create(app.store, str(b.get("id", "")), str(b.get("name", "")), str(b.get("template", "mock_bank")), u["username"])
                    return self.send_json(201, ws.public())
                raise ApiError(405, "method_not_allowed", "method not allowed")
            ws_id, sub = rest[0], rest[1:]
            # public without a session: only the demo snapshot views (the landing page tells its story from them)
            public = method == "GET" and ws_id == "demo" and sub[:1] in (["results"], ["ledger"], ["report"], ["scene"])
            ws = self.workspace(ws_id, public_demo=public)
            name = sub[0] if sub else None
            if name is None and method == "GET":
                return self.send_json(200, ws.public())
            if name == "results" and method == "GET":
                r = app.cached(("results", ws.id), file_stamp(ws.results), lambda: load_results(ws))
                return self.send_json(200, {"workspace": ws.id, "results": r, "status_text": None if r else "not yet run"})
            if name == "scene" and method == "GET" and len(sub) == 1:
                from .scene import scene_bytes

                body, etag = app.cached(("scene", ws.id), file_stamp(ws.results), lambda: scene_bytes(ws.id, load_results(ws), ws.src, ws.settings.get("source")))
                if self.headers.get("If-None-Match") == etag:
                    self._headers(304, TYPES[".json"], 0, [("ETag", etag)])
                    return
                return self.send_body(200, body, TYPES[".json"], [("ETag", etag)])
            if name == "move" and method == "GET" and len(sub) == 1:  # recorded handshakes as message lists (Move page)
                from .move import move_payload

                stamp = (file_stamp(ws.out / "capture.json"), file_stamp(ws.results))
                return self.send_json(200, app.cached(("move", ws.id), stamp, lambda: move_payload(ws, load_results(ws))))
            if name == "ledger" and method == "GET":
                if sub[1:2] == ["proof"] and len(sub) == 3:
                    if not sub[2].isdigit():
                        raise ApiError(422, "bad_index", "proof index must be a non-negative integer")
                    r = load_results(ws)
                    stamp = file_stamp(ledger_path(ws, r))
                    return self.send_json(200, app.cached(("proof", ws.id, int(sub[2])), stamp, lambda: proof_payload(ws, int(sub[2]))))
                if len(sub) == 1:
                    r = load_results(ws)
                    stamp = (file_stamp(ws.results), file_stamp(ledger_path(ws, r)))
                    return self.send_json(200, app.cached(("ledger", ws.id), stamp, lambda: ledger_payload(ws)))
            if name == "report" and method == "GET" and len(sub) == 1:
                f = ws.out / "report.html"
                if not f.exists():
                    raise ApiError(404, "not_yet_run", "no report yet (not yet run)")
                return self.send_body(200, f.read_bytes(), TYPES[".html"],
                                      [("Content-Security-Policy", "default-src 'none'; style-src 'unsafe-inline'; script-src 'unsafe-inline'; img-src data:; sandbox allow-scripts allow-modals")])
            if name == "tamper-demo" and method == "POST":
                with app.tamper_lock:
                    if time.monotonic() - app.tamper_last < 1.0:
                        raise ApiError(429, "rate_limited", "one tamper demo per second")
                    app.tamper_last = time.monotonic()
                b = self.body_json()
                idx = b.get("index")
                if idx is not None and not isinstance(idx, int):
                    raise ApiError(422, "bad_index", "index must be an integer")
                return self.send_json(200, tamper_demo(ws, idx))
            if name == "reviews" and len(sub) == 1:  # results awaiting review; decisions signed into the Proof Chain
                from . import review

                if method == "GET":
                    u = self.user()
                    return self.send_json(200, {"items": review.listing(ws, load_results(ws)), "read_only": ws.read_only,
                                                "can_decide": has_role(u, "operator") and not ws.read_only})
                if method == "POST":
                    u = self.need("operator")
                    wsmod.require_writable(ws)
                    self._no_active_run(ws)
                    b = self.body_json()
                    with app.review_lock:
                        d = review.decide(ws, load_results(ws), str(b.get("item", "")), str(b.get("decision", "")), str(b.get("reason", "")), u["username"])
                    return self.send_json(200, {"decision": d, "items": review.listing(ws, load_results(ws))})
            if name == "estimate" and len(sub) == 1:  # time estimate vs the user's threshold
                from .estimate import estimate, parse_threshold

                if method == "GET":
                    try:
                        q = parse_threshold(self.query.get("threshold_weeks"))
                    except ValueError as e:
                        raise ApiError(422, "bad_threshold", str(e))
                    t = q if q is not None else ws.settings.get("time_threshold_weeks")
                    return self.send_json(200, {**estimate(load_results(ws), t), "saved_threshold_weeks": ws.settings.get("time_threshold_weeks")})
                if method == "PUT":
                    self.need("operator")
                    wsmod.require_writable(ws)
                    try:
                        t = parse_threshold(self.body_json().get("threshold_weeks"))
                    except ValueError as e:
                        raise ApiError(422, "bad_threshold", str(e))
                    wsmod.update_settings(app.store, ws, time_threshold_weeks=t)
                    return self.send_json(200, {**estimate(load_results(ws), t), "saved_threshold_weeks": t})
            if name == "bench" and len(sub) == 1:
                if method == "GET":
                    return self.send_json(200, bench_payload(ws))
                if method == "POST":  # python -m bench, then sign it into the Proof Chain and verify the chain
                    u = self.need("operator")
                    wsmod.require_writable(ws)
                    if not (ws.out / "schedule.json").exists():
                        raise ApiError(409, "not_run", "run the pipeline first: the benchmark uses this workspace's schedule")
                    run = app.runs.start(ws, u["username"], bench_steps(ws), "bench", {"bench": True}, False,
                                         needs_keygen=not (ws.keys / "ledger_mldsa65.key").exists())
                    return self.send_json(202, {"run_id": run.id})
            if name == "manifests":
                a = json.loads(ws.assumptions.read_text())
                if method == "GET":
                    return self.send_json(200, intake.list_manifests(ws, a))
                if method == "POST" and sub[1:] == ["suggest"]:
                    self.need("operator")
                    wsmod.require_writable(ws)
                    return self.send_json(200, {**intake.suggest_manifests(ws, a), **intake.list_manifests(ws, a)})
                if method == "POST" and sub[1:] == ["confirm"]:
                    self.need("operator")
                    wsmod.require_writable(ws)
                    dirs = self.body_json().get("dirs")
                    if dirs is not None and not (isinstance(dirs, list) and all(isinstance(x, str) for x in dirs)):
                        raise ApiError(422, "bad_dirs", "dirs must be a list of directories or omitted for all")
                    res = intake.confirm_manifests(ws, dirs, a)
                    if res["confirmed"]:  # who accepted the suggestions, and when: the manifest files no longer carry the marker
                        log = ws.settings.get("manifest_confirmations", [])
                        log.append({"by": self.user()["username"], "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "dirs": res["confirmed"]})
                        wsmod.update_settings(app.store, ws, manifest_confirmations=log[-20:])
                    return self.send_json(200, {**res, **intake.list_manifests(ws, a)})
                if method == "POST":
                    self.need("operator")
                    wsmod.require_writable(ws)
                    b = self.body_json()
                    m = intake.save_manifest(ws, str(b.get("dir", "")), b.get("manifest") or {}, a)
                    return self.send_json(200, {"saved": m, **intake.list_manifests(ws, a)})
            if name == "assumptions":
                if method == "GET":
                    return self.send_json(200, {"label": "assumption", "assumptions": json.loads(ws.assumptions.read_text()),
                                                "read_only": ws.read_only})
                if method in ("PUT", "POST"):
                    self.need("operator")
                    wsmod.require_writable(ws)
                    return self.send_json(200, {"label": "assumption", "assumptions": calibration.save_assumptions(ws, self.body_json())})
            if name == "calibration":
                if method == "GET" and len(sub) == 1:
                    return self.send_json(200, calibration.proposal(ws))
                u = self.need("operator")
                wsmod.require_writable(ws)
                if method == "POST" and len(sub) == 1:
                    b = self.body_json()
                    calibration.record(ws, str(b.get("asset_id", "")), b.get("engineer_days"), u["username"], str(b.get("note", "")))
                    return self.send_json(200, calibration.proposal(ws))
                if method == "POST" and sub[1:] == ["apply"]:
                    a = app.runs.active  # checked before anything is written: one run at a time, any workspace
                    if a and a.status == "running":
                        raise ApiError(409, "run_in_progress", f"a run is in progress in workspace {a.ws_id}")
                    only = self.body_json().get("apply")
                    if only is not None and not (isinstance(only, list) and all(isinstance(k, str) for k in only)):
                        raise ApiError(422, "bad_selection", "apply must be a list of proposal keys")
                    payload = calibration.apply(ws, u["username"], only)
                    run = self._start(ws, u, kind="calibration", probes=[], calibration_payload=payload,
                                      detail={"calibration_payload": payload.relative_to(ws.root).as_posix()})
                    return self.send_json(202, {"run_id": run.id, "calibration_payload": payload.relative_to(ws.root).as_posix()})
            if name == "upload" and method == "POST":
                self.need("operator")
                wsmod.require_writable(ws)
                self._no_active_run(ws)
                return self.send_json(200, self.upload(ws))
            if name == "clone" and method == "POST":
                u = self.need("operator")
                wsmod.require_writable(ws)
                self._no_active_run(ws)
                b = self.body_json()
                res = intake.clone(ws, str(b.get("url", "")), limits()["clone_timeout_s"], b.get("commit") or None)
                wsmod.update_settings(app.store, ws, source={"kind": "git", "ref": res["url"], "commit": res["commit"],
                                                             "by": u["username"], "ts": time.time()}, lab_probes=[])
                return self.send_json(200, res)
            if name == "runs":
                if method == "GET" and len(sub) == 1:
                    with app.store.db() as c:
                        rows = c.execute("SELECT * FROM runs WHERE workspace=? ORDER BY started DESC LIMIT 50", (ws.id,)).fetchall()
                    active = app.runs.active
                    return self.send_json(200, {"runs": [{**dict(r), "detail": json.loads(r["detail"])} for r in rows],
                                                "active": active.id if active and active.status == "running" else None})
                if method == "POST" and len(sub) == 1:
                    u = self.need("operator")
                    wsmod.require_writable(ws)
                    b = self.body_json()
                    platform, qcloud = bool(b.get("platform")), bool(b.get("qcloud"))
                    probes = parse_probes(b.get("probes") or [], bool(b.get("authorised")))
                    presets = reference_presets(b.get("presets") or [])
                    detail = {"probes": probes, "presets": [p["id"] for p in presets], "platform": platform, "qcloud": qcloud}
                    if presets:
                        detail["preset_note"] = settings()["reference_endpoints"]["label"]
                    probes = probes + [f"{p['service']}={p['host']}:{p['port']}" for p in presets]
                    if probes:
                        detail["authorisation"] = {"confirmed_by": u["username"], "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                                                   "statement": "I own or am authorised to test these endpoints"}
                    run = self._start(ws, u, kind="pipeline", probes=probes, platform=platform, qcloud=qcloud,
                                      confirm=bool(b.get("confirm_credits")), detail=detail)
                    return self.send_json(202, {"run_id": run.id})
                if len(sub) >= 2 and method == "GET":
                    run = app.runs.get(sub[1])
                    if sub[2:] == ["events"]:
                        return self.run_events(ws, sub[1], run)
                    if len(sub) == 2:
                        with app.store.db() as c:
                            row = c.execute("SELECT * FROM runs WHERE id=? AND workspace=?", (sub[1], ws.id)).fetchone()
                        if not row:
                            raise ApiError(404, "not_found", "no such run")
                        return self.send_json(200, {**dict(row), "detail": json.loads(row["detail"])})
            raise ApiError(404, "not_found", f"no API route {method} /api/workspaces/{'/'.join(rest)}")

        def _no_active_run(self, ws):
            a = app.runs.active
            if a and a.status == "running" and a.ws_id == ws.id:
                raise ApiError(409, "run_in_progress", "a run is in progress in this workspace")

        def _start(self, ws, u, kind, probes, detail, platform=False, qcloud=False, confirm=False, calibration_payload=None):
            if platform or qcloud:
                from .config import settings

                if u["role"] != "admin":
                    raise ApiError(403, "forbidden", "paid QpiAI runs are admin-only")
                s = settings()["platform"]
                if platform and not s["opt_enabled"]:
                    raise ApiError(409, "platform_blocked", s["opt_blocked_reason"])
                if qcloud and not s["qcloud_enabled"]:
                    raise ApiError(409, "qcloud_blocked", s["qcloud_blocked_reason"])
                if not confirm:
                    raise ApiError(422, "confirm_required", "confirm that QpiAI credits may be consumed")
            pending = [m for m in ws.src.rglob("atlas-service.json") if '"suggested"' in m.read_text(errors="replace")] if ws.src.exists() else []
            if pending:  # suggestions are not facts: an operator confirms them before they drive a plan
                raise ApiError(409, "manifests_unconfirmed", f"{len(pending)} service manifests are suggestions; review and confirm them in Detect first")
            steps = pipeline_steps(ws, probes, platform, qcloud, calibration_payload)
            return app.runs.start(ws, u["username"], steps, kind, detail, platform or qcloud,
                                  needs_keygen=not (ws.keys / "ledger_mldsa65.key").exists())

        def upload(self, ws):
            if (self.headers.get("Content-Type") or "").split(";")[0].strip() != "application/zip":
                raise ApiError(415, "zip_required", "send the archive as an application/zip request body")
            n = int(self.headers.get("Content-Length") or 0)
            lim = limits()
            if n <= 0:
                raise ApiError(411, "length_required", "Content-Length is required")
            if n > lim["upload_max_bytes"]:
                raise ApiError(413, "too_large", f"upload limit is {lim['upload_max_bytes'] // (1 << 20)} MB")
            with tempfile.NamedTemporaryFile(dir=ws.root, suffix=".zip") as tmp:
                left = n
                while left:
                    chunk = self.rfile.read(min(left, 1 << 16))
                    if not chunk:
                        raise ApiError(400, "short_body", "upload ended early")
                    tmp.write(chunk)
                    left -= len(chunk)
                tmp.flush()
                digest = hashlib.sha256(Path(tmp.name).read_bytes()).hexdigest()
                res = intake.extract_zip(ws, Path(tmp.name), lim)
            wsmod.update_settings(app.store, ws, source={"kind": "zip", "sha256": digest, "by": self.user()["username"],
                                                         "ts": time.time()}, lab_probes=[])
            return {**res, "sha256": digest}

        # ----- SSE -----
        def _sse_start(self):
            self._headers(200, "text/event-stream", None, [("Connection", "keep-alive")])
            self.close_connection = True

        def _sse(self, event, data, ev_id=None):
            msg = (f"id: {ev_id}\n" if ev_id is not None else "") + f"event: {event}\ndata: {json.dumps(data)}\n\n"
            self.wfile.write(msg.encode())
            self.wfile.flush()

        def file_events(self, ws):
            self._sse_start()
            def stamp():
                r = load_results(ws)
                return file_stamp(ws.results), file_stamp(ledger_path(ws, r))
            last, ping = stamp(), time.monotonic()
            heartbeat = float(self.query.get("heartbeat", 15)) if self.query.get("heartbeat", "").replace(".", "").isdigit() else 15
            heartbeat = min(max(heartbeat, 0.2), 15)
            try:
                self._sse("hello", {"workspace": ws.id})
                while True:
                    cur = stamp()
                    if cur != last:
                        changed = [n for n, a, b in zip(("results", "ledger"), last, cur) if a != b]
                        last = cur
                        self._sse("update", {"workspace": ws.id, "changed": changed})
                    if time.monotonic() - ping >= heartbeat:
                        self.wfile.write(b": heartbeat\n\n")
                        self.wfile.flush()
                        ping = time.monotonic()
                    time.sleep(0.25)
            except (BrokenPipeError, ConnectionResetError, OSError):
                return

        def run_events(self, ws, run_id, run):
            if run is None or run.ws_id != ws.id:
                log = data_dir() / "runlogs" / f"{run_id}.jsonl"
                if not re.fullmatch(r"[0-9a-f]{16}", run_id) or not log.exists():
                    raise ApiError(404, "not_found", "no such run")
                with app.store.db() as c:
                    if not c.execute("SELECT 1 FROM runs WHERE id=? AND workspace=?", (run_id, ws.id)).fetchone():
                        raise ApiError(404, "not_found", "no such run")
                self._sse_start()
                for line in log.read_text().splitlines():  # finished run from an earlier server: replay
                    ev = json.loads(line)
                    self._sse(ev["type"], ev, ev["seq"])
                return
            self._sse_start()
            after = int(self.headers.get("Last-Event-ID", -1)) + 1 if (self.headers.get("Last-Event-ID") or "").isdigit() else 0
            try:
                while True:
                    evs = run.wait(after, 15)
                    if not evs:
                        self.wfile.write(b": heartbeat\n\n")
                        self.wfile.flush()
                    for ev in evs:
                        self._sse(ev["type"], ev, ev["seq"])
                        after = ev["seq"] + 1
                        if ev["type"] == "run_end":
                            return
            except (BrokenPipeError, ConnectionResetError, OSError):
                return

    return Handler


class Server(ThreadingHTTPServer):
    daemon_threads = True

    def handle_error(self, request, client_address):
        if isinstance(sys.exc_info()[1], (ConnectionResetError, BrokenPipeError, TimeoutError)):
            return  # a browser closing a keep-alive socket is not an error
        super().handle_error(request, client_address)


def make_server(host: str = "127.0.0.1", port: int = 0, kiosk: bool = False, demo: bool = False) -> ThreadingHTTPServer:
    app = App(kiosk=kiosk, demo=demo)
    srv = Server((host, port), make_handler(app))
    srv.daemon_threads = True
    srv.app = app
    return srv
