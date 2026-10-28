"""Run-manifest helpers: canonical hashing, run IDs and timestamps.

Every number that reaches results.json must trace back to a manifest built here.
"""

import hashlib
import json
import uuid
from datetime import datetime, timezone


def canonical_json(obj) -> bytes:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_json(obj) -> str:
    return sha256_hex(canonical_json(obj))


def new_run_id() -> str:
    return uuid.uuid4().hex


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
