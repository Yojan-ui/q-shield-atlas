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

Default is a free local QpiAI Opt solve, which issues no job ID: the stage is logged with
job_id = null, a reason, our own run_id and SHA-256 hashes of the exact inputs and output.
Opt-in platform mode submits one paid job per stage (see platform_guard.py) and records the
real job_id / problem_id next to the local objective for the same input.
"""

import json
from dataclasses import asdict
from importlib.metadata import version
from pathlib import Path

from qpiai_opt.opt_modeller import Binary, Continuous, Model, quicksum
from qpiai_opt.opt_solvers import Client, solve

from contracts.manifest import new_run_id, sha256_json, utc_now

from .platform_guard import PlatformBudget
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


SOLVER_LOCAL = "qpiai-opt local"
SOLVER_PLATFORM = "qpiai-opt platform"
SOLVER_FALLBACK = "qpiai-opt local (fallback: platform submission failed)"
SOLVER_SKIPPED = "qpiai-opt local (fallback: platform skipped after an earlier failure in this run)"


def objectives_match(a: float, b: float) -> bool:
    return abs(a - b) <= 1e-6 * max(1.0, abs(a), abs(b))


def solve_schedule(
    problem: Problem,
    client: Client,
    horizon: int,
    run_dir: Path | None = None,
    time_limit: float = 120.0,
    mode: str = "local",
    budget: PlatformBudget | None = None,
) -> tuple[dict[str, int], list[dict]]:
    """Return (completion week per asset, solver run records).

    mode="local": QpiAI Opt local solve only (free, no job ID).
    mode="platform": one paid QpiAI Opt platform job per stage, guarded by `budget`; the same
    model is also solved locally and both objectives are recorded side by side. If the platform
    submission fails, the stage falls back to the local result and is labelled as a fallback.
    """
    if mode not in {"local", "platform"}:
        raise ValueError("mode must be 'local' or 'platform'")
    if mode == "platform" and (budget is None or run_dir is None):
        raise ValueError("platform mode requires a PlatformBudget and a run_dir")
    pkg_version = version("qpiai-opt")
    fixed: dict[str, float] = {}
    runs: list[dict] = []
    weeks: dict[str, int] = {}
    platform_error = None  # first platform failure stops further submissions in this run
    for stage in STAGES[problem.objective]:
        run_id = new_run_id()
        stage_name = f"schedule.milp.{problem.objective}.{stage}"
        d = Path(run_dir) / run_id if run_dir is not None else None
        model, y = build_model(problem, horizon, stage, fixed)
        inputs = {"problem": problem_dict(problem, horizon), "stage": stage, "fixed": fixed, "lp": model.to_lp_string()}
        submit = mode == "platform" and platform_error is None
        if submit:
            budget.reserve(1, run_id, stage_name, d)  # refuses (forbidden / over limit) before any solve
        local = solve(model, client=client, time_limit=time_limit, mip_rel_gap=0.0)
        local_output = local.model_dump(mode="json")

        result, solver, fallback_reason, comparison = local, SOLVER_LOCAL, None, None
        if mode == "platform" and not submit:
            solver, fallback_reason = SOLVER_SKIPPED, platform_error
        if submit:
            try:
                result = solve(model, mode="platform", client=client, time_limit=time_limit, mip_rel_gap=0.0)
                solver = SOLVER_PLATFORM
                budget.record(run_id, job_id=result.job_id, problem_id=result.problem_id, status=str(result.status))
            except Exception as exc:  # labelled fallback, never silent
                fallback_reason = platform_error = f"{type(exc).__name__}: {exc}"[:500]
                solver = SOLVER_FALLBACK
                budget.record(run_id, error=fallback_reason)
                print(f"PLATFORM FAILED for {stage_name}; using local result. {fallback_reason}", flush=True)
            if solver == SOLVER_PLATFORM:
                comparison = {
                    "platform_objective": result.objective,
                    "local_objective": local.objective,
                    "abs_diff": abs(result.objective - local.objective),
                    "match": objectives_match(result.objective, local.objective),
                }
                if not comparison["match"]:
                    print(
                        f"OBJECTIVES DIFFER for {stage_name}: platform={result.objective!r} "
                        f"local={local.objective!r} (both recorded; plan uses the platform solution)",
                        flush=True,
                    )

        output = result.model_dump(mode="json")
        info = result.info()
        run = {
            "run_id": run_id,
            "ts": utc_now(),
            "stage": stage_name,
            "solver": solver,
            "provider": "qpiai-opt",
            "package_version": pkg_version,
            "mode": result.execution_mode,
            "device": None,
            "job_id": result.job_id,
            "problem_id": result.problem_id,
            "job_id_reason": None if result.job_id else JOB_ID_REASON,
            "fallback_reason": fallback_reason,
            "status": str(result.status),
            "termination": info.termination,
            "guarantee": info.guarantee,
            "objective": result.objective,
            "solver_time_s": result.solver_time_s,
            "inputs_sha256": sha256_json(inputs),
            "output_sha256": sha256_json(output),
            "local_output_sha256": sha256_json(local_output),
            "comparison": comparison,
        }
        runs.append(run)
        if d is not None:
            d.mkdir(parents=True, exist_ok=True)
            (d / "inputs.json").write_text(json.dumps(inputs, indent=1))
            (d / "solver_output.json").write_text(json.dumps(output, indent=1))
            (d / "local_solver_output.json").write_text(json.dumps(local_output, indent=1))
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


def optimize(
    problem: Problem,
    client: Client,
    horizon: int,
    run_dir: Path | None = None,
    mode: str = "local",
    budget: PlatformBudget | None = None,
) -> tuple[dict, list[dict]]:
    weeks, runs = solve_schedule(problem, client, horizon, run_dir, mode=mode, budget=budget)
    summary = evaluate(problem, weeks, f"qpiai-opt-milp-{problem.objective}")
    summary["objective"] = problem.objective
    summary["produced_by"] = {
        "solver": " + ".join(dict.fromkeys(r["solver"] for r in runs)),
        "run_ids": [r["run_id"] for r in runs],
        "job_ids": [r["job_id"] for r in runs],
    }
    return summary, runs
