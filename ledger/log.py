"""Append-only JSONL ledger of ML-DSA-65-signed entries.

Entry: {index, type, payload_hash, payload_ref, prev_hash, ts, alg, backend, pubkey_fp, sig_mldsa}
- Canonical bytes: json.dumps(sort_keys=True, separators=(",", ":"), ensure_ascii=False), UTF-8.
- sig_mldsa signs the canonical bytes of the entry *without* sig_mldsa.
- prev_hash = SHA-256 of the previous entry's canonical bytes *with* its signature; genesis = 64 zeros.
- Appends hold an exclusive file lock (fcntl.flock) for read-last + write.
"""

import base64
import fcntl
import hashlib
import json
from contextlib import contextmanager
from pathlib import Path

from contracts import validate
from contracts.manifest import utc_now

from .backend import ALG

GENESIS = "0" * 64


def canonical(obj) -> bytes:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def signed_bytes(entry: dict) -> bytes:
    return canonical({k: v for k, v in entry.items() if k != "sig_mldsa"})


def entry_hash(entry: dict) -> str:
    return hashlib.sha256(canonical(entry)).hexdigest()


def read_entries(path: Path) -> list[dict]:
    path = Path(path)
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


@contextmanager
def _locked(path: Path):
    lock = Path(str(path) + ".lock")
    lock.parent.mkdir(parents=True, exist_ok=True)
    with lock.open("w") as fh:
        fcntl.flock(fh, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(fh, fcntl.LOCK_UN)


class Ledger:
    def __init__(self, path: Path, backend, private_key: Path, public_key: Path, repo_root: Path):
        self.path, self.backend = Path(path), backend
        self.private_key, self.public_key, self.repo_root = Path(private_key), Path(public_key), Path(repo_root)
        self.pubkey_fp = backend.fingerprint(self.public_key)

    def entries(self) -> list[dict]:
        return read_entries(self.path)

    def append(self, entry_type: str, payload_path: Path) -> dict:
        payload_path = Path(payload_path).resolve()
        payload_hash = hashlib.sha256(payload_path.read_bytes()).hexdigest()
        with _locked(self.path):
            existing = self.entries()
            entry = {
                "index": len(existing),
                "type": entry_type,
                "payload_hash": payload_hash,
                "payload_ref": payload_path.relative_to(self.repo_root.resolve()).as_posix(),
                "prev_hash": entry_hash(existing[-1]) if existing else GENESIS,
                "ts": utc_now(),
                "alg": ALG,
                "backend": self.backend.label,
                "pubkey_fp": self.pubkey_fp,
            }
            entry["sig_mldsa"] = base64.b64encode(self.backend.sign(self.private_key, signed_bytes(entry))).decode()
            validate("ledger_entry", entry)
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self.path.open("a", encoding="utf-8") as fh:
                fh.write(canonical(entry).decode("utf-8") + "\n")
        return entry
