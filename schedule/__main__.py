"""python -m schedule  ->  out/schedule.json (schedule section of results.json) + runs/<run_id>/."""

import argparse
import json
import os
from pathlib import Path

from qpiai_opt.opt_solvers import Client

from contracts.manifest import sha256_json

from .baselines import run_baselines
from .milp import optimize
from .problem import DEFAULT_ASSUMPTIONS, DEFAULT_INVENTORY, REPO, load_problem
from .sensitivity import horizon_for, run_sensitivity


def avoided(baseline: dict, optimized: dict) -> list[dict]:
    return [
        {
            "scenario": b["scenario"],
            "exposure_years_avoided": b["exposure_years"] - o["exposure_years"],
            "weighted_avoided": b["weighted_exposure"] - o["weighted_exposure"],
        }
        for b, o in zip(baseline["per_scenario"], optimized["per_scenario"])
    ]


def build_section(problem, client, run_dir, with_sensitivity=True) -> dict:
    baselines = run_baselines(problem)
    optimized, runs = optimize(problem, client, horizon_for(problem, baselines), run_dir)
    weeks = optimized["completion_week"]
    return {
        "assumptions": {**problem.raw_assumptions, "sha256": sha256_json(problem.raw_assumptions)},
        "scenarios": [{"name": s.name, "year": s.year, "weight": s.weight} for s in problem.scenarios],
        "assets": [
            {
                "id": a.id,
                "name": a.name,
                "kind": a.kind,
                "data_class": a.data_class,
                "algorithm": a.algorithm,
                "shelf_life_years": a.shelf_life_years,
                "effort_days": a.effort_days,
                "risk_weight": a.risk_weight,
                "depends_on": list(a.depends_on),
                "status": "planned",
                "planned_week": weeks[a.id],
            }
            for a in problem.assets
        ],
        "waves": optimized["waves"],
        "exposure": optimized,
        "baselines": baselines,
        "avoided": {"vs_fcfs": avoided(baselines["fcfs"], optimized), "vs_greedy": avoided(baselines["greedy"], optimized)},
        "solver_runs": runs,
        "sensitivity": run_sensitivity(problem, client, run_dir) if with_sensitivity else None,
    }


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--assumptions", default=DEFAULT_ASSUMPTIONS)
    ap.add_argument("--inventory", default=DEFAULT_INVENTORY)
    ap.add_argument("--out", default=REPO / "out" / "schedule.json")
    ap.add_argument("--runs", default=REPO / "runs")
    ap.add_argument("--no-sensitivity", action="store_true")
    args = ap.parse_args()

    problem = load_problem(args.assumptions, args.inventory)
    client = Client(api_key=os.environ["QPIAI_OPT_API_KEY"])
    section = build_section(problem, client, Path(args.runs), not args.no_sensitivity)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(section, indent=1))
    print(f"wrote {out}")
    for name in ("fcfs", "greedy"):
        for row in section["avoided"][f"vs_{name}"]:
            print(f"  vs {name:6} {row['scenario']}: {row['exposure_years_avoided']:.3f} exposure-years avoided")


if __name__ == "__main__":
    main()
