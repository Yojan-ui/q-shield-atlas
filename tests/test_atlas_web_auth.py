"""atlas_web auth: no default user, scrypt hashes only, rate limit, expiry, CSRF, roles."""

import sqlite3
import subprocess
import sys

import pytest

from atlas_web.auth import SCRYPT, Store, has_role, token_hash

from .atlas_web_helpers import PASSWORD, Client, start_server


@pytest.fixture
def server(monkeypatch, tmp_path):
    srv = start_server(monkeypatch, tmp_path)
    store = srv.app.store
    for name, role in (("ada", "admin"), ("ops", "operator"), ("vic", "viewer")):
        store.create_user(name, PASSWORD, role)
    yield srv
    srv.shutdown()
    srv.server_close()


def test_no_default_user(tmp_path):
    store = Store(tmp_path / "a.db")
    assert store.list_users() == []
    with pytest.raises(Exception):
        store.login("admin", "admin")


def test_cli_list_users_says_none(tmp_path):
    env = {"ATLAS_WEB_DATA": str(tmp_path), "PATH": "/usr/bin:/bin"}
    out = subprocess.run([sys.executable, "-m", "atlas_web", "list-users"], capture_output=True, text=True, env=env, timeout=60)
    assert out.returncode == 0 and "no users yet" in out.stdout


def test_only_scrypt_hashes_and_token_hashes_stored(tmp_path):
    store = Store(tmp_path / "a.db")
    store.create_user("ada", PASSWORD, "admin")
    s = store.login("ada", PASSWORD)
    raw = (tmp_path / "a.db").read_bytes()
    assert PASSWORD.encode() not in raw and s["token"].encode() not in raw
    c = sqlite3.connect(tmp_path / "a.db")
    salt, pw = c.execute("SELECT salt, pw_hash FROM users").fetchone()
    assert len(salt) == 16 and len(pw) == SCRYPT["dklen"] and SCRYPT["n"] == 2**14 and (SCRYPT["r"], SCRYPT["p"]) == (8, 1)
    assert c.execute("SELECT token_hash FROM sessions").fetchone()[0] == token_hash(s["token"])
    assert (tmp_path / "a.db").stat().st_mode & 0o777 == 0o600


def test_password_rules(tmp_path):
    store = Store(tmp_path / "a.db")
    with pytest.raises(ValueError):
        store.create_user("ada", "short", "admin")
    with pytest.raises(ValueError):
        store.create_user("ada", PASSWORD, "root")
    with pytest.raises(ValueError):
        store.create_user("Ada Lovelace!", PASSWORD, "admin")


def test_rate_limit_five_failures_per_five_minutes(tmp_path):
    store = Store(tmp_path / "a.db")
    store.create_user("ada", PASSWORD, "admin")
    for _ in range(5):
        with pytest.raises(Exception) as e:
            store.login("ada", "wrong password", now=1000.0)
        assert e.value.code == "bad_credentials"
    with pytest.raises(Exception) as e:
        store.login("ada", PASSWORD, now=1001.0)  # even the right password is refused now
    assert e.value.code == "rate_limited" and e.value.status == 429
    assert store.login("ada", PASSWORD, now=1000.0 + 301)["username"] == "ada"  # window passed


def test_session_expires_after_8_hours(tmp_path):
    store = Store(tmp_path / "a.db")
    store.create_user("ada", PASSWORD, "admin")
    s = store.login("ada", PASSWORD, now=0.0)
    assert store.session(s["token"], now=8 * 3600 - 1)["username"] == "ada"
    assert store.session(s["token"], now=8 * 3600) is None
    assert store.session(s["token"], now=1.0) is None  # expired sessions are deleted


def test_roles_rank():
    assert has_role({"role": "admin"}, "operator") and has_role({"role": "operator"}, "viewer")
    assert not has_role({"role": "viewer"}, "operator") and not has_role(None, "viewer")


def test_login_sets_httponly_strict_cookie(server):
    c = Client(server.server_address[1])
    r, body = c.request("POST", "/api/auth/login", {"username": "ada", "password": PASSWORD}, raw=True)
    assert r.status == 200
    cookies = r.headers.get_all("Set-Cookie")
    sess = next(x for x in cookies if x.startswith("atlas_session="))
    assert "HttpOnly" in sess and "SameSite=Strict" in sess and "Max-Age=28800" in sess
    csrf = next(x for x in cookies if x.startswith("atlas_csrf="))
    assert "HttpOnly" not in csrf and "SameSite=Strict" in csrf


def test_bad_login_is_generic_and_json(server):
    c = Client(server.server_address[1])
    for user in ("ada", "nobody"):
        status, body = c.login(user, "wrong password")
        assert status == 401 and body == {"error": {"code": "bad_credentials", "message": "username or password is incorrect"}}
    status, body = c.request("POST", "/api/auth/login", b"username=ada", headers={"Content-Type": "application/x-www-form-urlencoded"})
    assert status == 415  # form posts (cross-site without preflight) are refused


def test_csrf_required_on_post(server):
    c = Client(server.server_address[1])
    c.login("ops")
    status, body = c.post("/api/workspaces", {"id": "w1", "template": "empty"}, csrf=False)
    assert status == 403 and body["error"]["code"] == "csrf"
    status, body = c.post("/api/workspaces", {"id": "w1", "template": "empty"}, headers={"X-CSRF-Token": "forged"})
    assert status == 403 and body["error"]["code"] == "csrf"
    status, body = c.post("/api/workspaces", {"id": "w1", "template": "empty"})
    assert status == 201 and body["id"] == "w1"


def test_cross_origin_post_refused(server):
    c = Client(server.server_address[1])
    c.login("ops")
    status, body = c.post("/api/workspaces", {"id": "w2", "template": "empty"}, headers={"Origin": "http://evil.example"})
    assert status == 403 and body["error"]["code"] == "bad_origin"


def test_role_gates(server):
    port = server.server_address[1]
    anon = Client(port)
    assert anon.get("/api/workspaces")[0] == 401
    assert anon.get("/api/me")[1]["user"] is None
    vic = Client(port)
    vic.login("vic")
    assert vic.get("/api/me")[1]["user"]["role"] == "viewer"
    assert vic.get("/api/workspaces")[0] == 200
    assert vic.post("/api/workspaces", {"id": "w3"})[0] == 403
    assert vic.get("/api/users")[0] == 403
    assert vic.get("/api/preflight")[0] == 403
    ops = Client(port)
    ops.login("ops")
    assert ops.get("/api/users")[0] == 403
    ada = Client(port)
    ada.login("ada")
    status, body = ada.get("/api/users")
    assert status == 200 and {u["username"] for u in body["users"]} == {"ada", "ops", "vic"}
    assert all(set(u) == {"username", "role", "created"} for u in body["users"])  # never hashes


def test_admin_user_management_api(server):
    ada = Client(server.server_address[1])
    ada.login("ada")
    assert ada.post("/api/users", {"username": "new", "password": "x", "role": "viewer"})[0] == 422
    assert ada.post("/api/users", {"username": "new", "password": PASSWORD, "role": "viewer"})[0] == 201
    assert ada.request("DELETE", "/api/users/ada")[0] == 422  # not yourself
    assert ada.request("DELETE", "/api/users/new")[0] == 200
    assert ada.request("DELETE", "/api/users/new")[0] == 404


def test_logout_revokes_session(server):
    c = Client(server.server_address[1])
    c.login("vic")
    token = c.cookies["atlas_session"]
    assert c.post("/api/auth/logout")[0] == 200
    c.cookies["atlas_session"] = token
    assert c.get("/api/workspaces")[0] == 401
