"""python -m qaoa [--qcloud [--allow-more]]  ->  out/qaoa.json, runs/<run_id>/

QAOA on simulators. A measured cross-check against the exact optimum. No quantum advantage
claimed; the problem is small enough for brute force.

Builds the wave-selection QUBO for one week of the latest schedule (out/schedule.json), solves it
exactly by brute force, runs local statevector QAOA for each p, samples it, and compares with the
same number of uniformly random bitstrings. --qcloud additionally samples the final circuits on
a QpiAI QCloud simulator (paid, guarded, opt-in).
"""

import argparse
import json
from pathlib import Path

import numpy as np

from contracts.manifest import new_run_id, sha256_json, utc_now
from schedule.platform_guard import DAILY_LIMIT, PlatformBudget

from . import local_sim, metrics, qcloud_run
from .qubo import build, exact_optimum
from .table import build_table

REPO = Path(__file__).resolve().parent.parent
LABEL = ("QAOA on simulators. A measured cross-check against the exact optimum. "
         "No quantum advantage claimed; the problem is small enough for brute force.")


def run(schedule: dict, cfg: dict, run_root: Path, qcloud: bool = False, budget=None) -> dict:
    run_id = new_run_id()
    run_dir = run_root / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    q = build(schedule, cfg)
    E = q.energies()
    exact = {**exact_optimum(q), "run_id": run_id}
    if abs(float(E.min()) - exact["objective"]) > 1e-9:
        raise AssertionError("QUBO minimum differs from the brute-force constrained optimum")

    runs, angle_sets = [], []
    for p in cfg["reps"]:
        opt = local_sim.optimise(E, p, cfg["restarts"], cfg["seed"], cfg["cobyla_maxiter"])
        counts = local_sim.sample(opt["probabilities"], cfg["shots"], cfg["seed"] + p, q.n)
        (run_dir / f"local_p{p}_counts.json").write_text(json.dumps(counts))
        idx = int(exact["bitstring"], 2)
        runs.append({
            "p": p, "source": "local", "backend": "numpy statevector (qaoa/local_sim.py)", "shots": cfg["shots"],
            "angles": {"gammas": opt["gammas"], "betas": opt["betas"]}, "energy_scale": opt["energy_scale"],
            "optimizer": f"scipy COBYLA, {cfg['restarts']} seeded restarts (seed {cfg['seed']}), maxiter {cfg['cobyla_maxiter']}",
            "expected_energy_exact": opt["expected_energy"], "p_optimal_exact": float(opt["probabilities"][idx]),
            "job_ids": [], "metrics": metrics.compute(q, counts, E, exact),
        })
        angle_sets.append({"p": p, "gammas": opt["gammas"], "betas": opt["betas"], "energy_scale": opt["energy_scale"]})

    rnd = local_sim.uniform_samples(q.n, cfg["shots"], cfg["seed"] + 1000)
    runs.append({"p": None, "source": "random", "backend": f"uniform random bitstrings (numpy, seed {cfg['seed'] + 1000})",
                 "shots": cfg["shots"], "angles": None, "job_ids": [], "metrics": metrics.compute(q, rnd, E, exact)})

    comparisons, qcloud_status = [], {"requested": qcloud}
    if qcloud:
        records = qcloud_run.run(q, angle_sets, cfg, budget, run_id, run_dir)
        qcloud_status.update(device=cfg["qcloud"]["device"], jobs=[{k: r.get(k) for k in ("p", "status", "job_id", "credits_used", "error")} for r in records])
        for rec, a in zip(records, angle_sets):
            if rec["status"] != "ok":
                continue
            m = metrics.compute(q, rec["counts"], E, exact)
            runs.append({"p": rec["p"], "source": "qcloud", "backend": rec["device"], "shots": m["shots"],
                         "angles": {"gammas": a["gammas"], "betas": a["betas"]}, "energy_scale": a["energy_scale"],
                         "job_ids": [rec["job_id"]], "credits_used": rec["credits_used"], "metrics": m})
            local = next(r for r in runs if r["source"] == "local" and r["p"] == rec["p"])
            comparisons.append({"p": rec["p"], **metrics.compare(local["metrics"], m, cfg["compare_sigma"])})

    section = {
        "label": LABEL,
        "run_id": run_id,
        "ts": utc_now(),
        "schedule_sha256": sha256_json(schedule),
        "problem": {
            "week": q.week, "assets": q.assets, "values": q.values, "weights": q.weights,
            "capacity": q.capacity, "weight_scale": q.weight_scale, "slack_bits": q.slack_bits,
            "n_variables": q.n, "A": q.A, "B": q.B, "dependencies": [[q.assets[i], q.assets[j]] for i, j in q.deps],
            "objective_definition": "minimise -sum_i r_i * a_i * x_i; a_i = scenario-weighted exposure-years avoided by "
                                    f"migrating in week {q.week} instead of {cfg['deferral_weeks']} week(s) later",
            "bit_order": "variable k = qubit k = bit k of the basis index; counts strings have qubit 0 rightmost",
            "shrink_log": q.log,
        },
        "exact": exact,
        "runs": runs,
        "comparisons": comparisons,
        "qcloud": qcloud_status,
    }
    (run_dir / "manifest.json").write_text(json.dumps(section, indent=1))
    return section


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--schedule", type=Path, default=REPO / "out" / "schedule.json")
    ap.add_argument("--config", type=Path, default=REPO / "config" / "qaoa.json")
    ap.add_argument("--out-dir", type=Path, default=REPO / "out")
    ap.add_argument("--runs", type=Path, default=REPO / "runs")
    ap.add_argument("--qcloud", action="store_true", help="opt-in: sample final circuits on a QpiAI QCloud simulator (paid)")
    ap.add_argument("--allow-more", action="store_true", help=f"allow more than {DAILY_LIMIT} platform jobs per UTC day")
    args = ap.parse_args(argv)

    cfg = json.loads(args.config.read_text())
    budget = None
    if args.qcloud:
        qcloud_run.check_device(cfg["qcloud"]["device"], cfg["qcloud"]["allowed_devices"])
        budget = PlatformBudget(args.runs / "platform_jobs.log", allow_more=args.allow_more)
        budget.check(len(cfg["reps"]))
    section = run(json.loads(args.schedule.read_text()), cfg, args.runs, args.qcloud, budget)
    args.out_dir.mkdir(parents=True, exist_ok=True)
    (args.out_dir / "qaoa.json").write_text(json.dumps(section, indent=1))

    print(LABEL)
    print(f"run {section['run_id']}: week {section['problem']['week']}, {section['problem']['n_variables']} variables "
          f"({len(section['problem']['assets'])} assets + {section['problem']['slack_bits']} slack), A=B={section['problem']['A']:.4g}")
    ex = section["exact"]
    print(f"exact optimum (brute force): objective {ex['objective']:.6f}, assets {ex['assets']}, bitstring {ex['bitstring']}")
    print(f"\n{'p':>2} {'source':7} {'shots':>5} {'feasible':>8} {'best feas':>10} {'approx':>7} {'E ratio':>8} {'P(opt)':>7} {'P(opt set)':>10}  job_ids")
    for r in build_table(section):
        if r["status"] != "ok":
            print(f"{r['p']:>2} {r['source']:7} {r['status_text']}")
            continue
        m = r["metrics"]
        ar = f"{m['approximation_ratio']:.3f}" if m["approximation_ratio"] is not None else "n/a"
        bf = f"{m['best_feasible_objective']:.4f}" if m["best_feasible_objective"] is not None else "n/a"
        print(f"{r['p'] if r['p'] is not None else '-':>2} {r['source']:7} {r['shots']:>5} {m['feasible_fraction']:>8.3f} {bf:>10} "
              f"{ar:>7} {m['energy_ratio']:>8.4f} {m['p_optimal']:>7.4f} {m['p_optimal_assets']:>10.4f}  {r['job_ids']}")
    for c in section["comparisons"]:
        print(f"p={c['p']} local vs QCloud: {c['note']}; z={ {k: round(v, 2) for k, v in c['z_scores'].items()} }")


if __name__ == "__main__":
    main()
