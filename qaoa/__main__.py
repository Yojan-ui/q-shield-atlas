"""python -m qaoa [--qpiai-local] [--qcloud] [--ibm] [--allow-more] | --ibm-fetch | --ibm-import DIR  ->  out/qaoa.json, runs/<run_id>/

QAOA on simulators. A measured cross-check against the exact optimum. No quantum advantage
claimed; the problem is small enough for brute force.

Builds the link cutover selection QUBO (solvers subproblem "link_cutover") for one week of the latest schedule (out/schedule.json), solves it
exactly by brute force, runs local statevector QAOA for each p, samples it, and compares with the
same number of uniformly random bitstrings. --qcloud additionally samples the final circuits on
a QpiAI QCloud simulator (paid, guarded, opt-in); --ibm samples them on IBM Quantum hardware
(config/qaoa.json "ibm", guarded, opt-in) and --ibm-fetch re-polls jobs that were still queued.
--ibm-import DIR attaches a packaged IBM run (tools/export_ibm_run.py) without IBM access (qaoa/ibm_import.py).
"""

import argparse
import json
from pathlib import Path

import numpy as np

import solvers
from contracts.manifest import new_run_id, sha256_json, utc_now
from schedule.platform_guard import DAILY_LIMIT, PlatformBudget

from . import ibm_import, ibm_run, local_sim, metrics, qcloud_run, qpiai_local
from .qubo import build
from .table import build_table

REPO = Path(__file__).resolve().parent.parent
LABEL = ("QAOA on simulators. A measured cross-check against the exact optimum. "
         "No quantum advantage claimed; the problem is small enough for brute force.")


def run(schedule: dict, cfg: dict, run_root: Path, qcloud: bool = False, budget=None, sdk_local: bool = False,
        ibm: bool = False) -> dict:
    run_id = new_run_id()
    run_dir = run_root / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    q = build(schedule, cfg)
    E = q.energies()
    exact = {**solvers.solve("link_cutover", q, "exact").record, "run_id": run_id}  # the reference optimum
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
    sdk_status = {"requested": sdk_local}
    if sdk_local:  # free, in-process QpiAI SDK simulator: same final circuits, no network, no credits
        for rec in qpiai_local.run(q, angle_sets, cfg, run_id, run_dir):
            m = metrics.compute(q, rec["counts"], E, exact)
            a = next(x for x in angle_sets if x["p"] == rec["p"])
            runs.append({"p": rec["p"], "source": "qpiai_local", "backend": rec["backend"], "shots": m["shots"],
                         "angles": {"gammas": a["gammas"], "betas": a["betas"]}, "energy_scale": a["energy_scale"],
                         "job_ids": [], "job_id": None, "job_id_reason": rec["job_id_reason"], "sdk_version": rec["sdk_version"],
                         "seed": rec["seed"], "inputs_sha256": rec["inputs_sha256"], "outputs_sha256": rec["outputs_sha256"], "metrics": m})
            local = next(r for r in runs if r["source"] == "local" and r["p"] == rec["p"])
            comparisons.append({"p": rec["p"], "against": "qpiai_local",
                                **metrics.compare(local["metrics"], m, cfg["compare_sigma"], "QpiAI SDK local")})
        sdk_status.update(device=qpiai_local.BACKEND, sdk_version=runs[-1]["sdk_version"])
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
            comparisons.append({"p": rec["p"], "against": "qcloud", **metrics.compare(local["metrics"], m, cfg["compare_sigma"])})

    ibm_status = {"requested": ibm}
    if ibm:
        records = ibm_run.run(q, angle_sets, cfg, budget, run_id, run_dir)
        ibm_status.update(backend=cfg["ibm"]["backend"], jobs=[ibm_job(r) for r in records])
        add_ibm_runs(runs, comparisons, records, angle_sets, q, E, exact, cfg)

    section = {
        "label": LABEL,
        "run_id": run_id,
        "ts": utc_now(),
        "schedule_sha256": sha256_json(schedule),
        "problem": {
            "subproblem": "link_cutover",
            "subproblem_label": f"link cutover selection: which links (asset TLS endpoints) cut over to post-quantum key exchange in week {q.week}",
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
        "qpiai_local": sdk_status,
        "ibm": ibm_status,
    }
    (run_dir / "manifest.json").write_text(json.dumps(section, indent=1))
    return section


IBM_JOB_KEYS = ("p", "status", "job_id", "job_status", "backend", "shots_requested", "qpu_seconds", "transpiled_depth",
                "two_qubit_gates", "two_qubit_gate_names", "physical_qubits", "optimization_level", "error")


def ibm_job(rec: dict) -> dict:
    return {k: rec.get(k) for k in IBM_JOB_KEYS}


def add_ibm_runs(runs, comparisons, records, angle_sets, q, E, exact, cfg) -> None:
    """Append one `ibm` run (+ comparison vs the numpy row) per finished hardware job."""
    for rec in records:
        if rec["status"] != "ok":
            continue
        a = next(x for x in angle_sets if x["p"] == rec["p"])
        m = metrics.compute(q, rec["counts"], E, exact)
        runs.append({"p": rec["p"], "source": "ibm", "backend": rec["backend"], "shots": m["shots"],
                     "angles": {"gammas": a["gammas"], "betas": a["betas"]}, "energy_scale": a["energy_scale"],
                     "job_ids": [rec["job_id"]], "hardware": True, "qpu_seconds": rec["qpu_seconds"],
                     "transpiled_depth": rec["transpiled_depth"], "two_qubit_gates": rec["two_qubit_gates"],
                     "two_qubit_gate_names": rec["two_qubit_gate_names"], "physical_qubits": rec["physical_qubits"],
                     "metrics": m})
        local = next(r for r in runs if r["source"] == "local" and r["p"] == rec["p"])
        comparisons.append({"p": rec["p"], "against": "ibm",
                            **metrics.compare(local["metrics"], m, cfg["compare_sigma"], f"IBM {rec['backend']}")})


def fetch_ibm(args, cfg) -> dict:
    """--ibm-fetch: re-poll queued IBM jobs of the run in out/qaoa.json; no new submissions."""
    section = json.loads((args.out_dir / "qaoa.json").read_text())
    if not section.get("ibm", {}).get("requested"):
        raise SystemExit("out/qaoa.json has no IBM jobs (run python -m qaoa --ibm first)")
    run_dir = args.runs / section["run_id"]
    records = [json.loads((run_dir / f"ibm_p{j['p']}.json").read_text()) for j in section["ibm"]["jobs"]]
    before = {r["p"]: r["status"] for r in records}
    ibm_run.fetch(records, cfg)
    newly = [r for r in records if before[r["p"]] == "queued" and r["status"] != "queued"]
    for r in records:
        (run_dir / f"ibm_p{r['p']}.json").write_text(json.dumps(r, indent=1))
    if newly:
        schedule = json.loads(args.schedule.read_text())
        if sha256_json(schedule) != section["schedule_sha256"]:
            raise SystemExit("out/schedule.json changed since the QAOA run; refusing to attach IBM counts to a different QUBO")
        q = build(schedule, cfg)
        E = q.energies()
        angle_sets = [{"p": r["p"], **r["angles"], "energy_scale": r["energy_scale"]}
                      for r in section["runs"] if r["source"] == "local"]
        add_ibm_runs(section["runs"], section["comparisons"], newly, angle_sets, q, E, section["exact"], cfg)
    section["ibm"]["jobs"] = [ibm_job(r) for r in records]
    (run_dir / "manifest.json").write_text(json.dumps(section, indent=1))
    (args.out_dir / "qaoa.json").write_text(json.dumps(section, indent=1))
    for r in records:
        print(f"IBM p={r['p']} job {r.get('job_id')}: {r['status']} ({r.get('job_status')})")
    return section


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--schedule", type=Path, default=REPO / "out" / "schedule.json")
    ap.add_argument("--config", type=Path, default=REPO / "config" / "qaoa.json")
    ap.add_argument("--out-dir", type=Path, default=REPO / "out")
    ap.add_argument("--runs", type=Path, default=REPO / "runs")
    ap.add_argument("--qcloud", action="store_true", help="opt-in: sample final circuits on a QpiAI QCloud simulator (paid)")
    ap.add_argument("--qpiai-local", action="store_true", help="also sample the final circuits on the QpiAI SDK's in-process simulator (free, no network)")
    ap.add_argument("--ibm", action="store_true", help="opt-in: sample final circuits on IBM Quantum hardware (config/qaoa.json ibm)")
    ap.add_argument("--ibm-fetch", action="store_true", help="re-poll IBM jobs of out/qaoa.json that were still queued; submits nothing")
    ap.add_argument("--ibm-import", type=Path, metavar="DIR", help="attach the IBM rows of a packaged run (e.g. data/real_ibm_qaoa); no IBM access")
    ap.add_argument("--allow-more", action="store_true", help=f"allow more than {DAILY_LIMIT} platform jobs per UTC day")
    ap.add_argument("--platform-log", type=Path, default=None,
                    help="shared daily-cap log (default RUNS/platform_jobs.log); point every workspace at one file")
    args = ap.parse_args(argv)

    cfg = json.loads(args.config.read_text())
    if args.ibm_fetch:
        fetch_ibm(args, cfg)
        return 0
    if args.ibm_import:
        ibm_import.main(args.ibm_import, args.out_dir, args.runs)
        return 0
    schedule = json.loads(args.schedule.read_text())
    if not schedule.get("assets"):  # nothing to migrate: there is no wave to select, so no QUBO is built
        (args.out_dir / "qaoa.json").unlink(missing_ok=True)
        print("QAOA: nothing to select (the schedule has no assets); qaoa section left empty")
        return 0
    budget = None
    if args.qcloud or args.ibm:
        if args.qcloud:
            qcloud_run.check_device(cfg["qcloud"]["device"], cfg["qcloud"]["allowed_devices"])
        if args.ibm:
            ibm_run.check_backend(cfg["ibm"]["backend"], cfg["ibm"]["allowed_backends"])
        budget = PlatformBudget(args.platform_log or args.runs / "platform_jobs.log", allow_more=args.allow_more)
        budget.check(len(cfg["reps"]) * (int(args.qcloud) + int(args.ibm)))
    section = run(schedule, cfg, args.runs, args.qcloud, budget, sdk_local=args.qpiai_local, ibm=args.ibm)
    args.out_dir.mkdir(parents=True, exist_ok=True)
    (args.out_dir / "qaoa.json").write_text(json.dumps(section, indent=1))

    print(LABEL)
    print(f"run {section['run_id']}: week {section['problem']['week']}, {section['problem']['n_variables']} variables "
          f"({len(section['problem']['assets'])} assets + {section['problem']['slack_bits']} slack), A=B={section['problem']['A']:.4g}")
    ex = section["exact"]
    print(f"exact optimum (brute force): objective {ex['objective']:.6f}, assets {ex['assets']}, bitstring {ex['bitstring']}")
    print(f"\n{'p':>2} {'source':11} {'shots':>5} {'feasible':>8} {'best feas':>10} {'approx':>7} {'E ratio':>8} {'P(opt)':>7} {'P(opt set)':>10}  job_ids")
    for r in build_table(section):
        if r["status"] != "ok":
            print(f"{r['p']:>2} {r['source']:11} {r['status_text']}")
            continue
        m = r["metrics"]
        ar = f"{m['approximation_ratio']:.3f}" if m["approximation_ratio"] is not None else "n/a"
        bf = f"{m['best_feasible_objective']:.4f}" if m["best_feasible_objective"] is not None else "n/a"
        print(f"{r['p'] if r['p'] is not None else '-':>2} {r['source']:11} {r['shots']:>5} {m['feasible_fraction']:>8.3f} {bf:>10} "
              f"{ar:>7} {m['energy_ratio']:>8.4f} {m['p_optimal']:>7.4f} {m['p_optimal_assets']:>10.4f}  {r['job_ids']}")
    for c in section["comparisons"]:
        print(f"p={c['p']} numpy vs {c.get('against', 'qcloud')}: {c['note']}; z={ {k: round(v, 2) for k, v in c['z_scores'].items()} }")


if __name__ == "__main__":
    main()
