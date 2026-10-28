"""Exposure-minimising migration schedule solved with QpiAI Opt (local MILP).

Variables: y[i,k] = 1 if asset i migrates in week k (k = 1..T); e[i,s] >= 0 exposure years.
  sum_k y[i,k] = 1                                  each asset migrates exactly once
  sum_i w_i y[i,k] <= capacity                      weekly effort
  t_d <= t_i for each dependency d of i             with t_i = sum_k k y[i,k] (weeks)
  e[i,s] >= X_i + t_i / 52 - (Z_s - start_year)     Mosca exposure per scenario
Objectives are solved lexicographically, each stage fixing the previous optimum:
  expected: [scenario-weighted risk exposure, tie-break]
  robust:   [worst-case risk exposure, expected, tie-break]
tie-break = sum_i r_i t_i (finish high-risk assets early when exposure is already zero).

Local QpiAI Opt solves issue no job ID; each stage is logged with job_id = null, a reason,
our own run_id and SHA-256 hashes of the exact inputs and solver output.
"""

import json
from dataclasses import asdict
from importlib.metadata import version
from pathlib import Path

from qpiai_opt.opt_modeller import Binary, Continuous, Model, quicksum
from qpiai_opt.opt_solvers import Client, solve

from contracts.manifest import new_run_id, sha256_json, utc_now

from .problem import Problem, check_feasible, evaluate

JOB_ID_REASON = (
    "QpiAI Opt local solve (mode='local') issues no platform job ID; "
    "run is traceable via run_id and input/output SHA-256 hashes"
)
STAGES = {"expected": ["expected", "tiebreak"], "robust": ["worst", "expected", "tiebreak"]}


def problem_dict(problem: Problem, horizon: int) -> dict:
    d = asdict(problem)
    d.pop("raw_assumptions")
    d["milp_horizon_weeks"] = horizon
    return d


def build_model(problem: Problem, horizon: int, objective: str, fixed: dict[str, float]):
    n_assets = len(problem.assets)
    weeks = range(1, horizon + 1)
    per_year = problem.weeks_per_year
    total_weight = sum(s.weight for s in problem.scenarios) or 1.0

    y = {(n, k): Binary(f"y_{n}_{k}") for n in range(n_assets) for k in weeks}
    t = [quicksum(k * y[n, k] for k in weeks) for n in range(n_assets)]
    e = {
        (n, s): Continuous(f"e_{n}_{s}", lower_bound=0.0)
        for n in range(n_assets)
        for s in range(len(problem.scenarios))
    }

    model = Model(f"pqc_migration_{objective}")
    index = {a.id: n for n, a in enumerate(problem.assets)}
    for n, a in enumerate(problem.assets):
        model.add_constraint(quicksum(y[n, k] for k in weeks) == 1, label=f"once_{n}")
        for d in a.depends_on:
            model.add_constraint(t[index[d]] - t[n] <= 0, label=f"dep_{index[d]}_before_{n}")
        for s, sc in enumerate(problem.scenarios):
            model.add_constraint(
                e[n, s] - (1.0 / per_year) * t[n] >= a.shelf_life_years - (sc.year - problem.start_year),
                label=f"exposure_{n}_{s}",
            )
    for k in weeks:
        model.add_constraint(
            quicksum(a.effort_days * y[n, k] for n, a in enumerate(problem.assets)) <= problem.capacity_days_per_week,
            label=f"capacity_{k}",
        )

    weighted = [
        quicksum(a.risk_weight * e[n, s] for n, a in enumerate(problem.assets)) for s in range(len(problem.scenarios))
    ]
    exprs = {
        "expected": quicksum((sc.weight / total_weight) * weighted[s] for s, sc in enumerate(problem.scenarios)),
        "tiebreak": quicksum((a.risk_weight / per_year) * t[n] for n, a in enumerate(problem.assets)),
    }
    if problem.objective == "robust":
        worst = Continuous("worst_case", lower_bound=0.0)
        for s in range(len(problem.scenarios)):
            model.add_constraint(worst - weighted[s] >= 0, label=f"worst_{s}")
        exprs["worst"] = worst + 0  # as expression
    for name, value in fixed.items():
        model.add_constraint(exprs[name] <= value + 1e-7 * max(1.0, abs(value)), label=f"fix_{name}")
    model.minimize(exprs[objective])
    return model, y


def solve_schedule(
    problem: Problem,
    client: Client,
    horizon: int,
    run_dir: Path | None = None,
    time_limit: float = 120.0,
) -> tuple[dict[str, int], list[dict]]:
    """Return (completion week per asset, solver run records)."""
    pkg_version = version("qpiai-opt")
    fixed: dict[str, float] = {}
    runs: list[dict] = []
    weeks: dict[str, int] = {}
    for stage in STAGES[problem.objective]:
        model, y = build_model(problem, horizon, stage, fixed)
        inputs = {"problem": problem_dict(problem, horizon), "stage": stage, "fixed": fixed, "lp": model.to_lp_string()}
        result = solve(model, client=client, time_limit=time_limit, mip_rel_gap=0.0)
        output = result.model_dump(mode="json")
        info = result.info()
        run = {
            "run_id": new_run_id(),
            "ts": utc_now(),
            "stage": f"schedule.milp.{problem.objective}.{stage}",
            "provider": "qpiai-opt",
            "package_version": pkg_version,
            "mode": result.execution_mode,
            "device": None,
            "job_id": result.job_id,
            "job_id_reason": None if result.job_id else JOB_ID_REASON,
            "status": str(result.status),
            "termination": info.termination,
            "guarantee": info.guarantee,
            "objective": result.objective,
            "solver_time_s": result.solver_time_s,
            "inputs_sha256": sha256_json(inputs),
            "output_sha256": sha256_json(output),
        }
        runs.append(run)
        if run_dir is not None:
            d = Path(run_dir) / run["run_id"]
            d.mkdir(parents=True, exist_ok=True)
            (d / "inputs.json").write_text(json.dumps(inputs, indent=1))
            (d / "solver_output.json").write_text(json.dumps(output, indent=1))
            (d / "manifest.json").write_text(json.dumps(run, indent=1))
        if info.termination != "optimal" or not info.has_usable_solution:
            raise RuntimeError(f"MILP stage {stage} did not reach a proven optimum: {run}")
        sol = result.solution
        weeks = {
            a.id: next(k for k in range(1, horizon + 1) if sol[f"y_{n}_{k}"] > 0.5)
            for n, a in enumerate(problem.assets)
        }
        if errors := check_feasible(problem, weeks, horizon):
            raise RuntimeError(f"solver plan failed independent feasibility check: {errors}")
        fixed[stage] = result.objective
    return weeks, runs


def optimize(problem: Problem, client: Client, horizon: int, run_dir: Path | None = None) -> tuple[dict, list[dict]]:
    weeks, runs = solve_schedule(problem, client, horizon, run_dir)
    summary = evaluate(problem, weeks, f"qpiai-opt-milp-{problem.objective}")
    summary["objective"] = problem.objective
    return summary, runs
