"""python -m bench [--schedule out/schedule.json] [--out-dir out] [--runs runs] [--no-milp]  ->  out/bench.json

The same problem instances solved by classical, quantum (simulated) and hybrid solvers through solvers.solve().

QAOA on simulators. A measured cross-check against the exact optimum. No quantum advantage claimed.

Instances: the link cutover selection QUBO (solvers subproblem "link_cutover") of the latest schedule, built with
max_assets = 2, 4, ..., 12 so the variable count runs from small up to the 16-qubit simulator cap. For each one:
  exact     brute force (classical reference optimum)
  milp      QpiAI Opt local MILP (classical; verifies the API key online; --no-milp skips it)
  random    uniformly random bitstrings, same shot count, best feasible sample (the baseline QAOA must beat)
  qaoa      p = 1, 2, 3 on the numpy statevector simulator, best feasible sample
  hybrid    QAOA p=1 samples, repaired classically
The full migration schedule is listed with its MILP solve as recorded in schedule.json; QAOA cannot take it
(the reason is recorded). Hardware: not run, with the recorded reason. No number here is typed in by hand.
"""

import argparse
import json
import os
import platform
import sys
import time
from importlib.metadata import version
from pathlib import Path

import solvers
from contracts import validate
from contracts.manifest import new_run_id, sha256_json, utc_now
from qaoa import local_sim, metrics
from qaoa.qubo import build, exact_optimum

REPO = Path(__file__).resolve().parent.parent
LABEL = ("QAOA on simulators. A measured cross-check against the exact optimum. No quantum advantage claimed: "
         "at these sizes brute force and MILP are exact and faster.")
SIZES = (2, 4, 6, 8, 10, 12)  # max_assets; slack bits are added on top
FAMILY = {"exact": "classical", "milp": "classical", "random": "baseline", "qaoa": "quantum (simulator)",
          "qaoa_sdk": "quantum (simulator)", "hybrid": "hybrid (simulator + classical)", "hardware": "quantum (hardware)",
          "fcfs": "classical heuristic", "greedy": "classical heuristic"}
GUARANTEE = {"exact": "proven optimum (checks every choice)", "milp": "proven optimum (MILP gap 0)", "random": "none",
             "qaoa": "none (sampling)", "qaoa_sdk": "none (sampling)", "hybrid": "always feasible; optimum not guaranteed",
             "fcfs": "none (rule of thumb)", "greedy": "none (rule of thumb)", "hardware": "n/a"}
HARDWARE_REASON = ("not run: QpiAI QCloud job creation needs an active subscription (blocked for this account), and "
                   "this project never submits to the QpiAI-Indus-1 QPU; simulators only")
LIMITS = [
    "Statevector simulation stores 2^n complex amplitudes and every QAOA layer touches all of them, so time and "
    "memory double with each added variable; 16 variables is this project's cap.",
    "At n <= 16 the asset subsets number at most 2^12 = 4096, so a few thousand shots nearly enumerate the space: "
    "random sampling also finds the optimum. Compare P(optimum) and feasible share, not only the best sample.",
    "QAOA angles are tuned classically (COBYLA) on the exact simulated expectation; that tuning time is in the runtime.",
    "The full migration schedule (|assets| x horizon binaries plus continuous exposure) is far beyond 16 qubits.",
]


def random_solution(q, cfg, exact):
    E = q.energies()
    counts = local_sim.uniform_samples(q.n, cfg["shots"], cfg["seed"] + 1000)
    m = metrics.compute(q, counts, E, exact)
    x = [int(a in (m["best_feasible_assets"] or [])) for a in q.assets]
    return m, x


def row(inst, solver, sol=None, *, p=None, status="ok", reason=None, m=None, runtime=None, extra=None):
    opt = inst["optimum"]
    obj = sol.objective if sol else None
    return {
        "instance": inst["id"], "n_variables": inst["n_variables"], "asset_variables": inst["asset_variables"],
        "solver": solver, "family": FAMILY[solver],
        "p": p, "status": status, "status_text": reason,
        "objective": obj, "optimum": opt, "feasible": sol.feasible if sol else None,
        "approximation_ratio": (obj / opt) if (obj is not None and opt < 0) else None,
        "runtime_s": runtime if runtime is not None else (sol.runtime_s if sol else None),
        "p_optimal_assets": m["p_optimal_assets"] if m else None, "feasible_fraction": m["feasible_fraction"] if m else None,
        "guarantee": GUARANTEE[solver],
        **(extra or {}),
    }


def sdk_row(inst, q, qaoa1, cfg, run_dir):
    """The p=1 circuit (angles tuned on numpy) sampled by the QpiAI SDK's local simulator (QpiAI-QSV-Local)."""
    from qaoa import qpiai_local

    t0 = time.perf_counter()
    a = {"p": 1, **qaoa1.record["angles"], "energy_scale": qaoa1.record["energy_scale"]}
    (run_dir / f"sdk_{inst['id']}").mkdir(parents=True, exist_ok=True)
    rec = qpiai_local.run(q, [a], cfg, "bench", run_dir / f"sdk_{inst['id']}")[0]
    m = metrics.compute(q, rec["counts"], q.energies(), exact_optimum(q))
    x = [int(s in (m["best_feasible_assets"] or [])) for s in q.assets]
    sol = solvers.Solution("link_cutover", "qaoa_sdk", dict(zip(q.assets, x)), q.objective(x) if m["best_feasible_assets"] is not None else None,
                           m["best_feasible_assets"] is not None, 0.0, {})
    return row(inst, "qaoa_sdk", sol, p=1, m=m, runtime=time.perf_counter() - t0,
               extra={"backend": rec["backend"], "note": "sampling only; angles tuned on the numpy simulator (qaoa p=1 row)"})


def schedule_rows(schedule: dict) -> list[dict]:
    """The full migration schedule: FCFS and greedy (timed now) vs the QpiAI Opt MILP optimum (recorded solve)."""
    from schedule.problem import problem_from_dicts

    p = problem_from_dicts(schedule["assumptions"], {"assets": schedule["assets"]})
    key = "worst_case_weighted" if p.objective == "robust" else "expected_weighted"
    opt = schedule["exposure"][key]
    sr = schedule.get("solver_runs") or []
    n = len(p.assets)
    horizon = schedule["exposure"]["makespan_weeks"]
    size = {"instance": f"schedule-{n}-assets", "n_variables": n * horizon, "asset_variables": n}
    out = []
    for name in ("fcfs", "greedy"):
        s = solvers.solve("migration_schedule", {"problem": p}, name)
        out.append({**size, "solver": name, "family": FAMILY[name], "guarantee": GUARANTEE[name], "p": None, "status": "ok", "status_text": None,
                    "objective": s.objective, "optimum": opt, "feasible": True, "approximation_ratio": (opt / s.objective) if s.objective else 1.0,
                    "runtime_s": s.runtime_s, "makespan_weeks": s.record["makespan_weeks"]})
    out.append({**size, "solver": "milp", "family": FAMILY["milp"], "guarantee": GUARANTEE["milp"], "p": None, "status": "ok", "status_text": None,
                "objective": opt, "optimum": opt, "feasible": True, "approximation_ratio": 1.0,
                "runtime_s": sum(r.get("solver_time_s") or 0 for r in sr), "makespan_weeks": horizon,
                "note": "recorded QpiAI Opt solve from schedule.json (solver_time_s summed over the lexicographic stages)"})
    out.append({**size, "solver": "qaoa", "family": FAMILY["qaoa"], "guarantee": "n/a", "p": None, "status": "not_run", "objective": None, "optimum": opt,
                "feasible": None, "approximation_ratio": None, "runtime_s": None,
                "status_text": "unsupported: " + solvers.UNSUPPORTED[("migration_schedule", "qaoa")]})
    return out


def run(schedule: dict, cfg: dict, run_root: Path, with_milp: bool = True) -> dict:
    run_id = new_run_id()
    run_dir = run_root / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    instances, rows, seen = [], [], set()
    for k in SIZES:
        q = build(schedule, {**cfg, "max_assets": k})
        key = tuple(q.assets)
        if key in seen:
            continue
        seen.add(key)
        ex = solvers.solve("link_cutover", q, "exact")
        inst = {"id": f"cutover-w{q.week}-n{q.n}", "n_variables": q.n, "asset_variables": q.m, "slack_bits": q.slack_bits,
                "assets": q.assets, "dependencies": len(q.deps), "capacity": q.capacity, "optimum": ex.objective,
                "optimum_assets": sorted(a for a, b in ex.assignment.items() if b), "statevector_amplitudes": 2**q.n}
        instances.append(inst)
        print(f"{inst['id']}: {q.m} assets + {q.slack_bits} slack bits", flush=True)
        rows.append(row(inst, "exact", ex))
        if with_milp:
            try:
                rows.append(row(inst, "milp", solvers.solve("link_cutover", q, "milp")))
            except Exception as exc:  # recorded as a status, never a number
                rows.append(row(inst, "milp", status="error", reason=f"{type(exc).__name__}: {exc}"[:300]))
        else:
            rows.append(row(inst, "milp", status="not_requested", reason="run with QpiAI Opt (drop --no-milp)"))
        t0 = time.perf_counter()
        m, x = random_solution(q, cfg, exact_optimum(q))
        rnd = solvers.Solution("link_cutover", "random", dict(zip(q.assets, x)), q.objective(x) if q.feasible(x) else None,
                               q.feasible(x), 0.0, {})
        rows.append(row(inst, "random", rnd, m=m, runtime=time.perf_counter() - t0))
        for p in cfg["reps"]:
            s = solvers.solve("link_cutover", q, "qaoa", p=p, cfg=cfg)
            rows.append(row(inst, "qaoa", s, p=p, m=s.record["metrics"]))
            if p == 1:
                qaoa1 = s
        rows.append(sdk_row(inst, q, qaoa1, cfg, run_dir))
        h = solvers.solve("link_cutover", q, "hybrid", p=1, cfg=cfg)
        rows.append(row(inst, "hybrid", h, p=1, extra={"feasible_fraction": h.record["raw_feasible_fraction"]}))
        rows.append(row(inst, "hardware", status="not_run", reason=HARDWARE_REASON))
        for r in rows[-(len(cfg["reps"]) + 6):]:
            print(f"  {r['solver']:8} p={r['p']!s:4} {r['status']:13} obj={r['objective']!s:.10} "
                  f"t={r['runtime_s'] if r['runtime_s'] is None else round(r['runtime_s'], 3)}", flush=True)

    sr = schedule.get("solver_runs") or []
    n_assets = len(schedule.get("assets", []))
    horizon = max((a["planned_week"] for a in schedule.get("assets", [])), default=0)
    full = {"subproblem": "migration_schedule", "assets": n_assets, "makespan_weeks": horizon,
            "milp_stages": [{k: r.get(k) for k in ("stage", "run_id", "objective", "solver_time_s", "termination", "guarantee")} for r in sr],
            "qaoa": "unsupported: " + solvers.UNSUPPORTED[("migration_schedule", "qaoa")]}
    section = {
        "label": LABEL, "run_id": run_id, "ts": utc_now(), "schedule_sha256": sha256_json(schedule),
        "subproblem": "link_cutover", "qaoa_config": {k: cfg[k] for k in ("reps", "restarts", "seed", "shots", "cobyla_maxiter")},
        "environment": {"python": platform.python_version(), "machine": platform.machine(), "numpy": version("numpy"),
                        "qpiai_opt": version("qpiai-opt")},
        "instances": instances, "rows": rows, "full_schedule": full, "schedule_rows": schedule_rows(schedule),
        "schedule_quality_note": "ratio = optimum / plan objective (weighted exposure, lower is better); 1 = optimal", "hardware": HARDWARE_REASON, "limits": LIMITS,
    }
    validate("bench", section)
    (run_dir / "manifest.json").write_text(json.dumps(section, indent=1))
    return section


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--schedule", type=Path, default=REPO / "out" / "schedule.json")
    ap.add_argument("--out-dir", type=Path, default=REPO / "out")
    ap.add_argument("--runs", type=Path, default=REPO / "runs")
    ap.add_argument("--no-milp", action="store_true", help="skip the QpiAI Opt MILP rows (they verify the API key online)")
    args = ap.parse_args(argv)
    schedule = json.loads(args.schedule.read_text())
    if not schedule.get("assets"):
        (args.out_dir / "bench.json").unlink(missing_ok=True)  # never leave an earlier benchmark looking current
        print("nothing to benchmark: the schedule has no assets (nothing to migrate)")
        return 0
    if not args.no_milp and not os.environ.get("QPIAI_OPT_API_KEY"):
        sys.exit("QPIAI_OPT_API_KEY not set (QpiAI Opt local solves verify the key online); or pass --no-milp")
    cfg = json.loads((REPO / "config" / "qaoa.json").read_text())
    section = run(schedule, cfg, args.runs, with_milp=not args.no_milp)
    (args.out_dir / "bench.json").write_text(json.dumps(section, indent=1))
    print(f"wrote {args.out_dir / 'bench.json'} ({len(section['rows'])} rows, run {section['run_id']})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
