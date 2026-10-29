"""Opt-in IBM Quantum hardware sampling of the final optimised QAOA circuits (python -m qaoa --ibm).

QAOA on simulators and one real QPU. A measured cross-check against the exact optimum. No quantum
advantage claimed; the problem is small enough for brute force, and hardware noise is expected to
lower feasibility at this circuit depth.

Same circuits as qaoa/circuit.py (angles optimised locally), rebuilt in Qiskit, transpiled for the
backend (depth and 2-qubit gate count recorded), one Sampler job per p, at most `max_jobs_per_run`.
Backend must be on the allowlist in config/qaoa.json "ibm". Token only from $IBM_QUANTUM_TOKEN
(never printed or written). Uses the shared platform guard: prints "Submitting N IBM Quantum jobs",
logs to runs/platform_jobs.log, daily cap unless --allow-more, refused entirely under pytest.
Jobs that are still queued after `wait_s` are recorded as "queued" with their job ID and picked up
later by `python -m qaoa --ibm-fetch`.

Qiskit conventions match the QCloud SDK: rz/rzz/rx(t) = exp(-i t/2 P); counts strings have qubit 0
rightmost (verified against numpy in tests).
"""

import json
import os
import time
from pathlib import Path

from .qubo import WaveQUBO

TOKEN_ENV = "IBM_QUANTUM_TOKEN"
# Assumptions for the pre-submit QPU estimate (not IBM's billing formula): per-job fixed overhead
# and the per-shot repetition delay when the backend does not report one.
JOB_OVERHEAD_S = 5.0
DEFAULT_REP_DELAY_S = 250e-6


def use_os_trust_store() -> bool:
    """Verify TLS against the OS certificate store instead of certifi's bundle, if `truststore` is installed.

    Needed on machines where antivirus (e.g. Norton Web/Mail Shield) re-signs HTTPS with a root that only
    the OS trusts. Certificate verification stays on; without truststore nothing changes (macOS default).
    """
    try:
        import truststore
    except ImportError:
        return False
    truststore.inject_into_ssl()
    return True


def check_backend(name: str, allowed) -> None:
    if name not in set(allowed):
        raise ValueError(f"IBM backend {name!r} is not on the allowlist {sorted(allowed)} (config/qaoa.json ibm.allowed_backends)")


def build_qiskit_circuit(q: WaveQUBO, gammas, betas, energy_scale: float, measure: bool = True):
    from qiskit import QuantumCircuit

    n = q.n
    h = q.linear / energy_scale
    J = {kl: v / energy_scale for kl, v in q.quad.items() if v != 0.0}
    c = QuantumCircuit(n, name=f"qshield_qaoa_w{q.week}_p{len(gammas)}")
    c.h(range(n))
    for g, b in zip(gammas, betas):
        z = [h[k] for k in range(n)]
        for (k, l), v in J.items():
            z[k] += v / 2
            z[l] += v / 2
        for k in range(n):
            c.rz(-g * z[k], k)
        for (k, l), v in J.items():
            c.rzz(g * v / 2, k, l)
        for k in range(n):
            c.rx(2 * b, k)
    if measure:
        c.measure_all()
    return c


def circuit_stats(isa) -> dict:
    """Depth and 2-qubit gate count of the transpiled (ISA) circuit actually sent to the backend."""
    two_q = {}
    for inst in isa.data:
        if len(inst.qubits) == 2 and inst.operation.name != "barrier":
            two_q[inst.operation.name] = two_q.get(inst.operation.name, 0) + 1
    used = sorted({isa.find_bit(qb).index for inst in isa.data for qb in inst.qubits if inst.operation.name != "barrier"})
    return {"transpiled_depth": isa.depth(), "two_qubit_gates": sum(two_q.values()), "two_qubit_gate_names": two_q,
            "physical_qubits": used, "ops": {k: int(v) for k, v in isa.count_ops().items()}}


def _service(ic: dict):
    from qiskit_ibm_runtime import QiskitRuntimeService

    token = os.environ.get(TOKEN_ENV)
    if not token:
        raise RuntimeError(f"{TOKEN_ENV} not set (put it in the git-ignored .env.sh)")
    use_os_trust_store()
    return QiskitRuntimeService(channel=ic["channel"], token=token)


def estimate_qpu_seconds(isas, backend, shots: int) -> float:
    """Conservative pre-submit estimate: per job, shots x (rep delay + circuit duration) + fixed overhead."""
    rep = getattr(getattr(backend, "configuration", lambda: None)(), "default_rep_delay", None) or DEFAULT_REP_DELAY_S
    total = 0.0
    for isa in isas:
        try:
            dur = float(isa.estimate_duration(backend.target, unit="s"))
        except Exception:
            dur = 0.0
        total += shots * (rep + dur) + JOB_OVERHEAD_S
    return total


def remaining_budget_s(service):
    """Remaining instance QPU seconds as reported by IBM, or None if the API does not expose it."""
    try:
        return service.usage().get("usage_remaining_seconds")
    except Exception:
        return None


def _collect(job, rec: dict) -> dict:
    """Fill counts and QPU seconds into `rec` from a finished job."""
    res = job.result()
    counts = res[0].data.meas.get_counts()
    rec.update(status="ok", job_status="DONE", counts={str(k): int(v) for k, v in counts.items()},
               qpu_seconds=job.usage())
    return rec


def _save(run_dir: Path, rec: dict) -> None:
    (run_dir / f"ibm_p{rec['p']}.json").write_text(json.dumps(rec, indent=1))


def run(q, angle_sets: list[dict], cfg: dict, budget, run_id: str, run_dir: Path) -> list[dict]:
    """angle_sets: [{"p", "gammas", "betas", "energy_scale"}]. Returns one record per p."""
    ic = cfg["ibm"]
    check_backend(ic["backend"], ic["allowed_backends"])
    if len(angle_sets) > ic["max_jobs_per_run"]:
        raise ValueError(f"{len(angle_sets)} jobs exceed ibm.max_jobs_per_run={ic['max_jobs_per_run']}")
    budget.check(len(angle_sets))  # refuse up front rather than after a partial run

    from qiskit.transpiler import generate_preset_pass_manager
    from qiskit_ibm_runtime import SamplerV2

    service = _service(ic)
    backend = service.backend(ic["backend"])
    pm = generate_preset_pass_manager(optimization_level=ic["optimization_level"], backend=backend,
                                      seed_transpiler=ic["seed_transpiler"])
    sampler = SamplerV2(mode=backend)
    isas = [pm.run(build_qiskit_circuit(q, a["gammas"], a["betas"], a["energy_scale"])) for a in angle_sets]
    est = estimate_qpu_seconds(isas, backend, cfg["shots"])
    left = remaining_budget_s(service)
    print(f"IBM estimate: {est:.1f} QPU s for {len(isas)} jobs x {cfg['shots']} shots on {ic['backend']}; "
          f"remaining instance budget: {'not exposed by the API' if left is None else f'{left:.0f} s'}", flush=True)
    if est > ic["max_estimated_qpu_s"]:
        raise SystemExit(f"estimate {est:.1f} s exceeds ibm.max_estimated_qpu_s={ic['max_estimated_qpu_s']}; nothing submitted")
    if left is not None and est > left:
        raise SystemExit(f"estimate {est:.1f} s exceeds the remaining {left:.0f} s; nothing submitted")
    records, jobs = [], {}
    for a, isa in zip(angle_sets, isas):
        stage = f"qaoa.ibm.p{a['p']}"
        rec = {"p": a["p"], "backend": ic["backend"], "shots_requested": cfg["shots"],
               "optimization_level": ic["optimization_level"], "seed_transpiler": ic["seed_transpiler"], **circuit_stats(isa)}
        budget.reserve(1, run_id, stage, run_dir, kind="IBM Quantum")
        try:
            job = sampler.run([isa], shots=cfg["shots"])
            rec.update(status="queued", job_id=job.job_id())
            budget.record(run_id, stage=stage, job_id=job.job_id(), backend=ic["backend"])
            jobs[a["p"]] = job
        except Exception as exc:
            rec.update(status="failed", error=f"{type(exc).__name__}: {exc}"[:500])
            budget.record(run_id, stage=stage, error=rec["error"])
            print(f"IBM SUBMIT FAILED for {stage}: {rec['error']}", flush=True)
        _save(run_dir, rec)
        records.append(rec)
    deadline = time.monotonic() + ic["wait_s"]  # one shared wait for all jobs, not per job
    for rec in records:
        job = jobs.get(rec["p"])
        if job is None:
            continue
        left_s = max(1, int(deadline - time.monotonic()))
        print(f"waiting up to {left_s} s for IBM job {rec['job_id']} (p={rec['p']})", flush=True)
        try:
            job.wait_for_final_state(timeout=left_s)
        except Exception as exc:  # timeout: still queued; --ibm-fetch picks it up later
            rec["last_check"] = f"{type(exc).__name__}: {exc}"[:300]
            _save(run_dir, rec)
            continue
        refresh(job, rec)
        _save(run_dir, rec)
    return records


def refresh(job, rec: dict) -> dict:
    status = job.status()
    status = getattr(status, "name", status)
    rec["job_status"] = str(status)
    if rec["job_status"] == "DONE":
        _collect(job, rec)
    elif rec["job_status"] in ("ERROR", "CANCELLED"):
        rec.update(status="failed", error=f"job {rec['job_status']}: {job.error_message() or ''}"[:500])
    return rec


def fetch(records: list[dict], cfg: dict) -> list[dict]:
    """Re-poll queued jobs by ID (no new submissions). Returns the updated records."""
    pending = [r for r in records if r.get("status") == "queued" and r.get("job_id")]
    if not pending:
        return records
    service = _service(cfg["ibm"])
    for rec in pending:
        refresh(service.job(rec["job_id"]), rec)
    return records
