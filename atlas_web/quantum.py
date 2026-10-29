"""Quantum backend for the web app: status of QpiAI QCloud, and one live QAOA run of the link cutover step.

Backend choice, in order (every response names the backend that produced it):
  1. QpiAI Cloud (device from config/qaoa.json, a simulator: QpiAI-QSV-Simulator) only when
     config/atlas_web.json platform.qcloud_enabled is true (admin switch; jobs can consume credits) and the
     cloud login works. Guarded by schedule/platform_guard (daily cap, logged); never QpiAI-Indus-1.
  2. Otherwise QpiAI-QSV-Local: the QpiAI SDK's in-process statevector simulator (no network, no credits).
Simulator output is never called hardware. QAOA here is a cross-check against the exact optimum; no advantage.
"""

import json
import os
import tempfile
import threading
import time
from importlib import metadata as md
from pathlib import Path

from .config import PLATFORM_LOG, REPO, settings

QAOA_CFG = REPO / "config" / "qaoa.json"
AUTH_ENV = "QCLOUD_API_KEY"
STATUS_TTL_S = 60
_status_cache: dict = {}
_lock = threading.Lock()


def _key() -> str | None:
    from .runner import env_file_values

    return os.environ.get(AUTH_ENV) or env_file_values().get(AUTH_ENV)


def cloud_status(timeout_s: float = 15.0) -> dict:
    """Read-only: log in and list QCloud compute resources (creates no job, uses no credits). Cached 60 s."""
    now = time.time()
    if _status_cache and now - _status_cache["checked_at"] < STATUS_TTL_S:
        return _status_cache["value"]
    out = {"sdk": "qpiai-quantum", "sdk_version": md.version("qpiai-quantum"), "auth_env": AUTH_ENV,
           "auth_configured": bool(_key()), "reachable": False, "devices": [], "error": None}
    if out["auth_configured"]:
        res: dict = {}

        def probe():
            try:
                from qpiai_quantum import JobManager, QpiAIQuantumAuth

                QpiAIQuantumAuth.login(_key())
                res["devices"] = [{"name": d.get("device_name"), "status": d.get("status"), "method": d.get("method")}
                                  for d in JobManager().list_compute_resources()]
            except Exception as exc:  # noqa: BLE001 - reported verbatim (never the key)
                res["error"] = f"{type(exc).__name__}: {exc}"[:300].replace(_key() or "\0", "***")

        t = threading.Thread(target=probe, daemon=True)
        t.start()
        t.join(timeout_s)
        if t.is_alive():
            out["error"] = f"timed out after {timeout_s:.0f} s"
        else:
            out["devices"], out["error"] = res.get("devices", []), res.get("error")
            out["reachable"] = out["error"] is None
    else:
        out["error"] = f"{AUTH_ENV} is not set"
    _status_cache.update(checked_at=now, value=out)
    return out


def status() -> dict:
    s = settings()["platform"]
    cfg = json.loads(QAOA_CFG.read_text())
    cloud = cloud_status()
    device = cfg["qcloud"]["device"]
    use_cloud = bool(s["qcloud_enabled"] and cloud["reachable"])
    reason = None if use_cloud else (s["qcloud_blocked_reason"] if not s["qcloud_enabled"] else f"QpiAI Cloud unreachable: {cloud['error']}")
    return {"backend": f"QpiAI Cloud: {device}" if use_cloud else "Local simulator",
            "backend_id": device if use_cloud else "QpiAI-QSV-Local", "kind": "cloud simulator" if use_cloud else "local simulator",
            "hardware": False, "cloud": {**cloud, "enabled": s["qcloud_enabled"], "device": device},
            "fallback_reason": reason, "checked_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(_status_cache.get("checked_at", time.time())))}


def run(schedule: dict, p: int = 1, timeout_s: float = 90.0) -> dict:
    """One live QAOA run of the link cutover selection on `schedule`: angles tuned on the numpy simulator, final
    circuit sampled on the chosen backend, scored against the exact optimum. Not signed (a live demo run)."""
    if not _lock.acquire(blocking=False):
        raise RuntimeError("busy: a quantum run is already in progress")
    try:
        from qaoa import local_sim, metrics, qpiai_local
        from qaoa.qubo import build, exact_optimum

        st = status()
        cfg = json.loads(QAOA_CFG.read_text())
        t0 = time.perf_counter()
        q = build(schedule, cfg)
        E = q.energies()
        exact = exact_optimum(q)
        opt = local_sim.optimise(E, p, cfg["restarts"], cfg["seed"], cfg["cobyla_maxiter"])
        angles = [{"p": p, "gammas": opt["gammas"], "betas": opt["betas"], "energy_scale": opt["energy_scale"]}]
        tuned = time.perf_counter() - t0
        backend, rec, fallback = st["backend"], None, st["fallback_reason"]
        with tempfile.TemporaryDirectory() as d:
            if st["kind"] == "cloud simulator":
                from qaoa import qcloud_run
                from schedule.platform_guard import PlatformBudget

                os.environ.setdefault(AUTH_ENV, _key() or "")
                r = qcloud_run.run(q, angles, cfg, PlatformBudget(PLATFORM_LOG), "web-" + str(int(time.time())), Path(d))[0]
                if r["status"] == "ok":
                    rec = {"counts": r["counts"], "job_id": r["job_id"], "credits_used": r["credits_used"]}
                else:
                    fallback, backend = f"QpiAI Cloud run failed: {r.get('error')}", "Local simulator"
            if rec is None:
                if time.perf_counter() - t0 > timeout_s:
                    raise TimeoutError(f"timed out after {timeout_s:.0f} s")
                r = qpiai_local.run(q, angles, cfg, "web", Path(d))[0]
                rec = {"counts": r["counts"], "job_id": None, "job_id_reason": r["job_id_reason"]}
                backend = "Local simulator"
        m = metrics.compute(q, rec["counts"], E, exact)
        return {"backend": backend, "backend_id": "QpiAI-QSV-Local" if backend == "Local simulator" else cfg["qcloud"]["device"],
                "hardware": False, "fallback_reason": fallback if backend == "Local simulator" else None,
                "step": "link cutover selection (QAOA)", "week": q.week, "assets": q.assets, "n_variables": q.n, "p": p,
                "shots": m["shots"], "exact_optimum": {"objective": exact["objective"], "assets": exact["assets"]},
                "best_feasible": {"objective": m["best_feasible_objective"], "assets": m["best_feasible_assets"]},
                "approximation_ratio": m["approximation_ratio"], "feasible_fraction": m["feasible_fraction"],
                "p_optimal_assets": m["p_optimal_assets"], "job_id": rec.get("job_id"), "job_id_reason": rec.get("job_id_reason"),
                "runtime_s": round(time.perf_counter() - t0, 3), "angle_tuning_s": round(tuned, 3),
                "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                "note": "Live demo run, not signed into the Proof Chain. Simulator output; no quantum advantage claimed."}
    finally:
        _lock.release()
