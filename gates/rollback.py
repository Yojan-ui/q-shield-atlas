"""Apply a deployment mode with a tested rollback.

1. Snapshot the service config file and record its SHA-256.
2. Write the new mode, restart, run the gates.
3. If any gate fails (or the restart fails): restore the snapshot, verify the restored config's
   SHA-256 equals the snapshot's, restart, and run a health-check handshake with the configured
   health-check client (classical-only by default, i.e. existing legacy clients still work).
Status: applied | rolled_back | rollback_failed. "applied" only when every gate passed.
"""

import shutil
from pathlib import Path

from capture.handshake import record
from contracts.manifest import sha256_hex, utc_now


def health_check(svc, lab: dict, transcript_dir: Path, tag: str) -> dict:
    client = lab["clients"][lab["health_check_client"]]
    rec = record(svc.service_id, svc.host, svc.port, client["groups"], transcript_dir, f"{tag}{svc.service_id}_health",
                 lab["timeouts_s"]["handshake"], None if client["tls"] == "auto" else client["tls"])
    return {
        "client": lab["health_check_client"],
        "result": "PASS" if rec["established"] else "FAIL",
        "negotiated_group": rec.get("negotiated_group"),
        "transcript_sha256": rec["transcript_sha256"],
    }


def apply_with_rollback(svc, new_mode: str, run_gates, lab: dict, transcript_dir: Path, tag: str = "", before_restore=None) -> dict:
    """`run_gates(svc) -> {"passed": bool, ...}`. `before_restore(snapshot_path)` is a test hook."""
    snapshots = svc.workdir / "snapshots"
    snapshots.mkdir(exist_ok=True)
    from_mode = svc.mode
    snapshot_path = snapshots / f"{tag or 'snap'}{utc_now().replace(':', '')}.json"
    shutil.copyfile(svc.config_path, snapshot_path)
    snapshot_sha = sha256_hex(snapshot_path.read_bytes())
    out = {
        "service_id": svc.service_id,
        "from_mode": from_mode,
        "to_mode": new_mode,
        "snapshot_sha256": snapshot_sha,
        "started_at": utc_now(),
    }

    svc.write_config(new_mode)
    out["applied_config_sha256"] = svc.config_sha256()
    try:
        svc.restart()
        gates = run_gates(svc)
    except Exception as exc:  # a failed restart is a failed gate
        gates = {"passed": False, "error": f"{type(exc).__name__}: {exc}"}
    out["gates"] = gates
    if gates["passed"]:
        return {**out, "status": "applied", "finished_at": utc_now()}

    # ---- rollback ----
    if before_restore is not None:
        before_restore(snapshot_path)
    shutil.copyfile(snapshot_path, svc.config_path)
    out["restored_config_sha256"] = svc.config_sha256()
    problems = []
    if out["restored_config_sha256"] != snapshot_sha:
        problems.append("restored config SHA-256 does not match the snapshot taken before apply")
    try:
        svc.restart()
        out["health_check"] = health_check(svc, lab, transcript_dir, tag)
        if out["health_check"]["result"] != "PASS":
            problems.append("health-check handshake failed after restore")
    except Exception as exc:
        out["health_check"] = {"result": "FAIL", "error": f"{type(exc).__name__}: {exc}"}
        problems.append("service did not restart after restore")
    status = "rollback_failed" if problems else "rolled_back"
    return {**out, "status": status, "rollback_problems": problems, "finished_at": utc_now()}
