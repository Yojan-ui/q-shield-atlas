"""Opt-in QCloud sampling of the final optimised QAOA circuits (python -m qaoa --qcloud).

QAOA on simulators. A measured cross-check against the exact optimum. No quantum advantage
claimed; the problem is small enough for brute force.

Only the final circuit for each p is submitted (angles are optimised locally), one job per p,
at most `max_jobs_per_run`. Device must be on the simulator allowlist; QpiAI-Indus-1 (QPU) is
refused. Uses the shared platform guard: prints "Submitting N QCloud jobs", logs to
runs/platform_jobs.log, daily cap unless --allow-more, refused entirely under pytest.
"""

import json
import os
from pathlib import Path

from .circuit import build_circuit

QPU_DEVICES = {"QpiAI-Indus-1"}


def check_device(device: str, allowed) -> None:
    if device in QPU_DEVICES or device not in set(allowed):
        raise ValueError(f"device {device!r} is not an allowed QCloud simulator {sorted(allowed)}")


def run(q, angle_sets: list[dict], cfg: dict, budget, run_id: str, run_dir: Path) -> list[dict]:
    """angle_sets: [{"p", "gammas", "betas", "energy_scale"}]. Returns one record per p."""
    qc = cfg["qcloud"]
    check_device(qc["device"], qc["allowed_devices"])
    if len(angle_sets) > qc["max_jobs_per_run"]:
        raise ValueError(f"{len(angle_sets)} jobs exceed max_jobs_per_run={qc['max_jobs_per_run']}")
    budget.check(len(angle_sets))  # refuse up front rather than after a partial run

    from qpiai_quantum import QpiAIQuantumAuth

    QpiAIQuantumAuth.login(os.environ["QCLOUD_API_KEY"])
    records, failed = [], None
    for a in angle_sets:
        stage = f"qaoa.qcloud.p{a['p']}"
        if failed:
            records.append({"p": a["p"], "status": "skipped", "error": f"earlier QCloud failure: {failed}"})
            continue
        budget.reserve(1, run_id, stage, run_dir, kind="QCloud")
        circuit = build_circuit(q, a["gammas"], a["betas"], a["energy_scale"])
        try:
            res = circuit.run(shots=cfg["shots"], device_name=qc["device"], experiment_name=qc["experiment_name"],
                              timeout=qc["timeout_s"])
            counts = {str(k): int(v) for k, v in (res.counts or {}).items()}
            rec = {"p": a["p"], "status": "ok", "job_id": res.job_id, "job_status": res.job_status,
                   "device": qc["device"], "shots_requested": cfg["shots"], "credits_used": res.credits_used,
                   "execution_time_s": res.execution_time, "counts": counts}
            budget.record(run_id, stage=stage, job_id=res.job_id, credits_used=res.credits_used)
        except Exception as exc:
            failed = f"{type(exc).__name__}: {exc}"[:500]
            rec = {"p": a["p"], "status": "failed", "error": failed}
            budget.record(run_id, stage=stage, error=failed)
            print(f"QCLOUD FAILED for {stage}: {failed}", flush=True)
        (run_dir / f"qcloud_p{a['p']}.json").write_text(json.dumps(rec, indent=1))
        records.append(rec)
    return records
