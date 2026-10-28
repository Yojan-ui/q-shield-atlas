"""Run the scheduled migration waves against local lab services, gate each one, keep or roll back.

Reads waves and assets from the latest schedule output (out/schedule.json). Each asset kind with a
TLS stand-in maps to one lab service (config/lab.json "waves.lab_services_by_kind"); at most
"max_processes" s_server processes run at once, all closed at the end. For every wave, each lab
service it touches is moved to the target mode with `apply_with_rollback`, gated by
pq_handshake + compat. Assets with no lab service are "not_verified_in_lab", never passed.

Asset/wave status: applied | rolled_back | rollback_failed | not_verified_in_lab, and for a wave
mixing verified and unverified assets, partially_verified.
"""

import contextlib
import json
import tempfile
from pathlib import Path

from contracts.manifest import new_run_id, sha256_json, utc_now

from .compat import run_matrix
from .pq_handshake import check_live
from .rollback import apply_with_rollback

NOT_VERIFIED = "not_verified_in_lab"


def wave_gates(svc, lab: dict, transcript_dir: Path, tag: str, policy: dict | None = None) -> dict:
    pq = check_live(svc, lab, transcript_dir, tag)
    compat = run_matrix(svc, lab, transcript_dir, policy, tag)
    return {"passed": pq["result"] == "PASS" and compat["result"] == "PASS", "pq_handshake": pq, "compat": compat}


def wave_status(asset_statuses: list[str]) -> str:
    verified = [s for s in asset_statuses if s != NOT_VERIFIED]
    if not verified:
        return NOT_VERIFIED
    for bad in ("rollback_failed", "rolled_back"):
        if bad in verified:
            return bad
    return "applied" if len(verified) == len(asset_statuses) else "partially_verified"


def run_waves(schedule: dict, lab: dict, run_dir: Path, policy_override: dict | None = None) -> dict:
    """`policy_override` (tests) maps lab service -> compat policy used when gating it."""
    cfg = lab["waves"]
    run_id = new_run_id()
    out_dir = run_dir / run_id
    out_dir.mkdir(parents=True, exist_ok=True)
    kinds = {a["id"]: a.get("kind", "") for a in schedule["assets"]}
    mapping = cfg["lab_services_by_kind"]
    needed = sorted({mapping[k] for k in kinds.values() if k in mapping})
    if len(needed) > cfg["max_processes"]:
        raise ValueError(f"{len(needed)} lab services exceed max_processes={cfg['max_processes']}")

    from capture.services import ManagedService

    waves_out, asset_status = [], {}
    with contextlib.ExitStack() as stack:
        pool = {}
        for name in needed:
            workdir = Path(stack.enter_context(tempfile.TemporaryDirectory(prefix=f"qshield-wave-{name}-")))
            svc = ManagedService(name, cfg["initial_mode"], lab, workdir)
            stack.callback(svc.close)
            svc.start()
            pool[name] = svc
        for wave in schedule["waves"]:
            touched = sorted({mapping[kinds[a]] for a in wave["assets"] if kinds[a] in mapping})
            evidence = []
            for name in touched:
                svc = pool[name]
                tag = f"w{wave['week']}_"
                policy = (policy_override or {}).get(name)
                res = apply_with_rollback(svc, cfg["target_mode"], lambda s: wave_gates(s, lab, out_dir, tag, policy), lab, out_dir, tag)
                evidence.append({"lab_service": name, "assets": [a for a in wave["assets"] if mapping.get(kinds[a]) == name], **res})
            by_service = {e["lab_service"]: e["status"] for e in evidence}
            statuses = {a: by_service[mapping[kinds[a]]] if kinds[a] in mapping else NOT_VERIFIED for a in wave["assets"]}
            asset_status.update(statuses)
            waves_out.append({
                "week": wave["week"],
                "assets": wave["assets"],
                "effort_days": wave["effort_days"],
                "status": wave_status(list(statuses.values())),
                "asset_status": statuses,
                "evidence": {"run_id": run_id, "ts": utc_now(), "lab_services": evidence},
            })
    counts = {}
    for s in asset_status.values():
        counts[s] = counts.get(s, 0) + 1
    result = {
        "run_id": run_id,
        "ts": utc_now(),
        "schedule_sha256": sha256_json(schedule),
        "target_mode": cfg["target_mode"],
        "lab_services": needed,
        "waves": waves_out,
        "asset_status": asset_status,
        "asset_counts": dict(sorted(counts.items())),
        "wave_counts": {s: sum(w["status"] == s for w in waves_out) for s in sorted({w["status"] for w in waves_out})},
        "note": "Lab verification uses local s_server stand-ins per asset kind; assets without one are not_verified_in_lab.",
    }
    (out_dir / "wave_runner.json").write_text(json.dumps(result, indent=1))
    return result
