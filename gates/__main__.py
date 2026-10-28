"""python -m gates  ->  out/gates.json, out/wave_status.json, runs/<run_id>/

1. Compatibility matrix: every deployment mode x every client profile (one s_server at a time).
2. Wave runner over the latest schedule (out/schedule.json).
3. One forced rollback: apply `strict` under a policy that (wrongly) requires classical clients to
   connect, so the compat gate fails and the rollback path runs for real.
Also re-evaluates the capture-time PQ handshake gate from out/capture.json if present.
"""

import argparse
import copy
import json
import tempfile
from pathlib import Path

from capture.services import REPO, managed_service, load_lab
from contracts.manifest import new_run_id, utc_now

from .compat import run_matrix
from .pq_handshake import evaluate
from .rollback import apply_with_rollback
from .wave_runner import run_waves, wave_gates


def forced_rollback_policy(lab: dict) -> dict:
    policy = copy.deepcopy(lab["compat_policy"])
    policy["strict"]["classical-only"] = {"expect": "connect", "group": "X25519"}
    return policy


def compat_all_modes(lab: dict, transcript_dir: Path) -> list[dict]:
    out = []
    for mode in lab["modes"]:
        with managed_service(f"compat-{mode}", mode, lab) as svc:
            out.append(run_matrix(svc, lab, transcript_dir))
    return out


def forced_rollback(lab: dict, transcript_dir: Path) -> dict:
    policy = forced_rollback_policy(lab)
    with managed_service("rollback-demo", "legacy", lab) as svc:
        return apply_with_rollback(svc, "strict", lambda s: wave_gates(s, lab, transcript_dir, "forced_", policy),
                                   lab, transcript_dir, "forced_")


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--schedule", type=Path, default=REPO / "out" / "schedule.json")
    ap.add_argument("--out-dir", type=Path, default=REPO / "out")
    ap.add_argument("--runs", type=Path, default=REPO / "runs")
    args = ap.parse_args(argv)

    lab = load_lab()
    run_id = new_run_id()
    run_dir = args.runs / run_id
    run_dir.mkdir(parents=True, exist_ok=True)

    matrix = compat_all_modes(lab, run_dir)
    waves = run_waves(json.loads(args.schedule.read_text()), lab, args.runs)
    rollback = forced_rollback(lab, run_dir)
    capture_path = args.out_dir / "capture.json"
    capture_gates = evaluate(json.loads(capture_path.read_text()), lab) if capture_path.exists() else None

    gates = {
        "run_id": run_id,
        "ts": utc_now(),
        "compat_matrix": matrix,
        "wave_run_id": waves["run_id"],
        "wave_asset_counts": waves["asset_counts"],
        "wave_counts": waves["wave_counts"],
        "forced_rollback": rollback,
        **({k: capture_gates[k] for k in ("pq_handshake", "pq_auth", "downgrade")} if capture_gates else {}),
    }
    args.out_dir.mkdir(parents=True, exist_ok=True)
    (args.out_dir / "gates.json").write_text(json.dumps(gates, indent=1))
    (args.out_dir / "wave_status.json").write_text(json.dumps(waves, indent=1))
    (run_dir / "manifest.json").write_text(json.dumps({k: gates[k] for k in ("run_id", "ts", "wave_run_id", "wave_asset_counts", "wave_counts")}, indent=1))

    print(f"gates run {run_id}; wave run {waves['run_id']}")
    print("\nCompatibility matrix (expected -> actual : result)")
    for m in matrix:
        print(f"  mode={m['mode']:10} gate={m['result']}")
        for c in m["cells"]:
            exp = c["expected"]["expect"] + (f" {c['expected']['group']}" if "group" in c["expected"] else "")
            act = f"connect {c['actual']['negotiated_group']} {c['actual']['protocol']}" if c["actual"]["connected"] else "refused"
            print(f"    {c['client']:15} expected {exp:24} actual {act:32} : {c['result']}")
    print(f"\nWaves (target mode {waves['target_mode']}, lab stand-ins {waves['lab_services']})")
    for w in waves["waves"]:
        per = {s: [a for a, v in w["asset_status"].items() if v == s] for s in sorted(set(w["asset_status"].values()))}
        print(f"  week {w['week']}: {w['status']:19} {per}")
    print(f"  asset counts: {waves['asset_counts']}")
    print(f"  wave counts:  {waves['wave_counts']}")
    r = rollback
    print(f"\nForced rollback ({r['from_mode']} -> {r['to_mode']} under a policy requiring classical clients): {r['status']}")
    failing = [c for c in r["gates"]["compat"]["cells"] if c["result"] == "FAIL"]
    for c in failing:
        print(f"  failing cell: {c['client']}: {c['reason']}")
    print(f"  snapshot   {r['snapshot_sha256']}")
    print(f"  applied    {r['applied_config_sha256']}")
    print(f"  restored   {r['restored_config_sha256']}  match={r['restored_config_sha256'] == r['snapshot_sha256']}")
    print(f"  health     {r['health_check']['result']} ({r['health_check']['client']} -> {r['health_check']['negotiated_group']})")


if __name__ == "__main__":
    main()
