"""Append signed run manifests to the ledger and anchor its root in results.json.

Payloads are the immutable per-run files under runs/<run_id>/:
  schedule.solver_run  runs/<id>/manifest.json   job_id, problem_id, solver, input/output hashes
  detect.run           runs/<id>/manifest.json   tree hash, inventory hash
  capture.run          runs/<id>/manifest.json   full capture.json (transcript hashes) + gate results
  gates.run            runs/<id>/manifest.json   compat matrix summary, wave counts
  gates.wave_run       runs/<id>/wave_runner.json per-wave status, config and transcript hashes
  qaoa.run             runs/<id>/manifest.json   QUBO, exact optimum, angles, metrics, QCloud job IDs
A payload already in the ledger (same type and SHA-256) is not appended again.
"""

import hashlib
import json
from pathlib import Path

from .log import Ledger, canonical
from .merkle import MerkleTree


def run_manifests(out_dir: Path, runs_dir: Path) -> list[tuple[str, Path]]:
    def load(name):
        p = out_dir / name
        return json.loads(p.read_text()) if p.exists() else None

    items = []
    if schedule := load("schedule.json"):
        items += [("schedule.solver_run", runs_dir / r["run_id"] / "manifest.json") for r in schedule["solver_runs"]]
    if detect := load("detect.json"):
        items.append(("detect.run", runs_dir / detect["run_id"] / "manifest.json"))
    if capture := load("capture.json"):
        items.append(("capture.run", runs_dir / capture["run_id"] / "manifest.json"))
    if gates := load("gates.json"):
        items.append(("gates.run", runs_dir / gates["run_id"] / "manifest.json"))
        items.append(("gates.wave_run", runs_dir / gates["wave_run_id"] / "wave_runner.json"))
    if qaoa := load("qaoa.json"):
        items.append(("qaoa.run", runs_dir / qaoa["run_id"] / "manifest.json"))
    missing = [str(p) for _, p in items if not p.exists()]
    if missing:
        raise FileNotFoundError(f"run manifests referenced by out/ are missing: {missing}")
    return items


def ledger_summary(ledger: Ledger, repo_root: Path) -> dict:
    entries = ledger.entries()
    return {
        "root": MerkleTree([canonical(e) for e in entries]).root(),
        "entry_count": len(entries),
        "pubkey_fp": ledger.pubkey_fp,
        "alg": "ML-DSA-65",
        "backend": ledger.backend.label,
        "ledger_ref": ledger.path.resolve().relative_to(repo_root.resolve()).as_posix(),
        "entries": [{"index": e["index"], "type": e["type"], "payload_ref": e["payload_ref"]} for e in entries],
    }


def ingest(ledger: Ledger, out_dir: Path, runs_dir: Path) -> tuple[list[dict], dict]:
    seen = {(e["type"], e["payload_hash"]) for e in ledger.entries()}
    appended = []
    for entry_type, path in run_manifests(out_dir, runs_dir):
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        if (entry_type, digest) in seen:
            continue
        appended.append(ledger.append(entry_type, path))
        seen.add((entry_type, digest))
    summary = ledger_summary(ledger, ledger.repo_root)
    (out_dir / "ledger.json").write_text(json.dumps(summary, indent=1))
    return appended, summary
