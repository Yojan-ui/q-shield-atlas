"""Verify the ledger end to end; report the first failing index and the reason.

Per entry i, in order: schema, index == i, prev_hash chain, pubkey_fp matches the verifying key,
ML-DSA-65 signature, payload file re-hash. Then the Merkle root and entry count must equal the
values anchored in results.json. A failure past the last entry (truncation) reports index = the
number of entries found.
"""

import base64
import binascii
import hashlib
from pathlib import Path

from jsonschema import ValidationError

from contracts import validate

from .log import GENESIS, canonical, entry_hash, read_entries, signed_bytes
from .merkle import MerkleTree


def status_record(report: dict, verifying_pubkey_fp: str) -> dict:
    """What `ledger verify` writes to out/ledger_verify.json (assembled into results.json)."""
    from contracts.manifest import utc_now

    return {"ok": report["ok"], "ts": utc_now(), "entries_checked": report["entries_checked"], "root": report.get("root"),
            "verifying_pubkey_fp": verifying_pubkey_fp, "first_failure": report["first_failure"]}


def _fail(index, reason, checked):
    return {"ok": False, "first_failure": {"index": index, "reason": reason}, "entries_checked": checked}


def verify(ledger_path: Path, public_key: Path, backend, repo_root: Path, anchor: dict | None) -> dict:
    try:
        entries = read_entries(ledger_path)
    except ValueError as exc:
        return _fail(0, f"ledger is not valid JSONL: {exc}", 0)
    key_fp = backend.fingerprint(public_key)
    prev = GENESIS
    for i, e in enumerate(entries):
        try:
            validate("ledger_entry", e)
        except ValidationError as exc:
            return _fail(i, f"entry does not match the ledger schema: {exc.message}", i)
        if e["index"] != i:
            return _fail(i, f"index mismatch: expected {i}, found {e['index']} (entry deleted or reordered)", i)
        if e["prev_hash"] != prev:
            return _fail(i, "prev_hash does not match the previous entry (chain broken)", i)
        if e["pubkey_fp"] != key_fp:
            return _fail(i, f"pubkey_fp {e['pubkey_fp'][:16]}... does not match the verifying key {key_fp[:16]}...", i)
        try:
            sig = base64.b64decode(e["sig_mldsa"], validate=True)
        except binascii.Error:
            return _fail(i, "sig_mldsa is not valid base64", i)
        if not backend.verify(public_key, signed_bytes(e), sig):
            return _fail(i, "ML-DSA-65 signature does not verify", i)
        payload = Path(repo_root) / e["payload_ref"]
        if not payload.exists():
            return _fail(i, f"payload file missing: {e['payload_ref']}", i)
        if hashlib.sha256(payload.read_bytes()).hexdigest() != e["payload_hash"]:
            return _fail(i, f"payload hash mismatch: {e['payload_ref']} changed since it was signed", i)
        prev = entry_hash(e)

    root = MerkleTree([canonical(e) for e in entries]).root()
    if anchor is not None:
        if anchor["entry_count"] != len(entries) or anchor["root"] != root:
            return _fail(len(entries), f"Merkle root/entry count do not match results.json anchor "
                                       f"(anchored {anchor['entry_count']} entries, root {anchor['root'][:16]}...; "
                                       f"found {len(entries)}, root {root[:16]}...)", len(entries))
        if anchor["pubkey_fp"] != key_fp:
            return _fail(0, "results.json anchors a different public key", len(entries))
    return {"ok": True, "first_failure": None, "entries_checked": len(entries), "root": root, "anchored": anchor is not None}
