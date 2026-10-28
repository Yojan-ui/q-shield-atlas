"""One-at-a-time sensitivity of the plan to the assumption values.

Shelf life, risk weight and effort are assumptions (config/assumptions.json). Each is scaled by
the configured factors while the others stay at 1.0; MILP and baselines are re-run on the
scaled data so every row is a measured comparison on identical inputs.
"""

from .baselines import run_baselines
from .milp import optimize
from .problem import Problem, scale

PARAMS = {"shelf_life_factors": "shelf", "risk_weight_factors": "risk", "effort_factors": "effort"}


def horizon_for(problem: Problem, baselines: dict) -> int:
    # The MILP horizon covers every baseline plan, so baselines are feasible MILP solutions
    # and the proven optimum can never be worse than them.
    return max(problem.horizon_weeks, *(b["makespan_weeks"] for b in baselines.values()))


def run_sensitivity(problem: Problem, client, run_dir=None) -> list[dict]:
    factors = problem.raw_assumptions.get("sensitivity", {})
    rows = []
    for key, param in PARAMS.items():
        for f in factors.get(key, []):
            if f == 1.0:
                continue
            scaled = scale(problem, **{param: f})
            base = run_baselines(scaled)
            opt, runs = optimize(scaled, client, horizon_for(scaled, base), run_dir)
            rows.append(
                {
                    "parameter": param,
                    "factor": f,
                    "optimized_expected": opt["expected_weighted"],
                    "fcfs_expected": base["fcfs"]["expected_weighted"],
                    "greedy_expected": base["greedy"]["expected_weighted"],
                    "optimized_worst": opt["worst_case_weighted"],
                    "fcfs_worst": base["fcfs"]["worst_case_weighted"],
                    "greedy_worst": base["greedy"]["worst_case_weighted"],
                    "run_ids": [r["run_id"] for r in runs],
                }
            )
    return rows
