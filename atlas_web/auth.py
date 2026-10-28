"""Users, sessions and login rate limiting (SQLite, stdlib only).

Passwords: scrypt n=2**14, r=8, p=1, 16-byte salt. Session tokens: 32 random bytes, only their SHA-256
is stored. Each session carries its own CSRF token (double-submit: cookie + X-CSRF-Token header).
No default user exists: create one with `python -m atlas_web create-user --role admin`.
"""

import hashlib
import hmac
import secrets
import sqlite3
import threading
import time
from pathlib import Path

ROLES = ("viewer", "operator", "admin")
RANK = {r: i for i, r in enumerate(ROLES)}
SCRYPT = {"n": 2**14, "r": 8, "p": 1, "dklen": 32}
USERNAME_OK = set("abcdefghijklmnopqrstuvwxyz0123456789._-")
MIN_PASSWORD = 10

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (username TEXT PRIMARY KEY, role TEXT NOT NULL, salt BLOB NOT NULL,
  pw_hash BLOB NOT NULL, created REAL NOT NULL);
CREATE TABLE IF NOT EXISTS sessions (token_hash TEXT PRIMARY KEY, username TEXT NOT NULL, csrf TEXT NOT NULL,
  created REAL NOT NULL, expires REAL NOT NULL);
CREATE TABLE IF NOT EXISTS login_failures (username TEXT NOT NULL, ts REAL NOT NULL);
CREATE TABLE IF NOT EXISTS workspaces (id TEXT PRIMARY KEY, name TEXT NOT NULL, template TEXT NOT NULL,
  created_by TEXT NOT NULL, created REAL NOT NULL, settings TEXT NOT NULL DEFAULT '{}');
CREATE TABLE IF NOT EXISTS runs (id TEXT PRIMARY KEY, workspace TEXT NOT NULL, username TEXT NOT NULL,
  kind TEXT NOT NULL, started REAL NOT NULL, finished REAL, status TEXT NOT NULL, detail TEXT NOT NULL DEFAULT '{}');
"""


class AuthError(Exception):
    def __init__(self, code: str, message: str, status: int = 401):
        super().__init__(message)
        self.code, self.message, self.status = code, message, status


def hash_password(password: str, salt: bytes) -> bytes:
    return hashlib.scrypt(password.encode(), salt=salt, maxmem=64 * 1024 * 1024, **SCRYPT)


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


class Store:
    def __init__(self, path: Path, session_hours: float = 8, max_failures: int = 5, window_s: float = 300):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.session_s, self.max_failures, self.window_s = session_hours * 3600, max_failures, window_s
        self._lock = threading.Lock()
        self._dummy_salt = secrets.token_bytes(16)
        self._dummy_hash = hash_password(secrets.token_hex(16), self._dummy_salt)
        with self.db() as c:
            c.executescript(SCHEMA)
        self.path.chmod(0o600)

    def db(self) -> sqlite3.Connection:
        c = sqlite3.connect(self.path, timeout=10, isolation_level=None)
        c.row_factory = sqlite3.Row
        return c

    # ---------- users ----------
    def create_user(self, username: str, password: str, role: str) -> None:
        username = username.strip().lower()
        if not username or len(username) > 64 or not set(username) <= USERNAME_OK:
            raise ValueError("username: 1-64 characters from a-z 0-9 . _ -")
        if role not in ROLES:
            raise ValueError(f"role must be one of {', '.join(ROLES)}")
        if len(password) < MIN_PASSWORD:
            raise ValueError(f"password must be at least {MIN_PASSWORD} characters")
        salt = secrets.token_bytes(16)
        with self._lock, self.db() as c:
            if c.execute("SELECT 1 FROM users WHERE username=?", (username,)).fetchone():
                raise ValueError(f"user {username!r} already exists")
            c.execute("INSERT INTO users VALUES (?,?,?,?,?)", (username, role, salt, hash_password(password, salt), time.time()))

    def list_users(self) -> list[dict]:
        with self.db() as c:
            return [{"username": r["username"], "role": r["role"], "created": r["created"]}
                    for r in c.execute("SELECT username, role, created FROM users ORDER BY username")]

    def delete_user(self, username: str) -> bool:
        with self._lock, self.db() as c:
            c.execute("DELETE FROM sessions WHERE username=?", (username,))
            return c.execute("DELETE FROM users WHERE username=?", (username,)).rowcount > 0

    # ---------- login ----------
    def _recent_failures(self, c, username: str, now: float) -> int:
        c.execute("DELETE FROM login_failures WHERE ts < ?", (now - self.window_s,))
        return c.execute("SELECT COUNT(*) FROM login_failures WHERE username=?", (username,)).fetchone()[0]

    def login(self, username: str, password: str, now: float | None = None) -> dict:
        now = time.time() if now is None else now
        username = (username or "").strip().lower()
        with self.db() as c:
            if self._recent_failures(c, username, now) >= self.max_failures:
                raise AuthError("rate_limited", f"too many failed sign-ins; try again in {int(self.window_s // 60)} minutes", 429)
            row = c.execute("SELECT * FROM users WHERE username=?", (username,)).fetchone()
            salt, stored = (row["salt"], row["pw_hash"]) if row else (self._dummy_salt, self._dummy_hash)
            ok = hmac.compare_digest(hash_password(password or "", salt), stored) and row is not None
            if not ok:
                c.execute("INSERT INTO login_failures VALUES (?,?)", (username, now))
                raise AuthError("bad_credentials", "username or password is incorrect")
            c.execute("DELETE FROM login_failures WHERE username=?", (username,))
            token, csrf = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
            c.execute("DELETE FROM sessions WHERE expires < ?", (now,))
            c.execute("INSERT INTO sessions VALUES (?,?,?,?,?)", (token_hash(token), username, csrf, now, now + self.session_s))
            return {"token": token, "csrf": csrf, "username": username, "role": row["role"], "expires": now + self.session_s}

    def session(self, token: str | None, now: float | None = None) -> dict | None:
        if not token:
            return None
        now = time.time() if now is None else now
        with self.db() as c:
            row = c.execute("SELECT s.username, s.csrf, s.expires, u.role FROM sessions s JOIN users u USING (username) "
                            "WHERE s.token_hash=?", (token_hash(token),)).fetchone()
            if not row:
                return None
            if row["expires"] <= now:
                c.execute("DELETE FROM sessions WHERE token_hash=?", (token_hash(token),))
                return None
            return {"username": row["username"], "role": row["role"], "csrf": row["csrf"], "expires": row["expires"]}

    def logout(self, token: str | None) -> None:
        if token:
            with self.db() as c:
                c.execute("DELETE FROM sessions WHERE token_hash=?", (token_hash(token),))


def has_role(user: dict | None, role: str) -> bool:
    return bool(user) and RANK.get(user["role"], -1) >= RANK[role]
