"""python -m schedule [--platform [--allow-more]]  ->  out/schedule.json + runs/<run_id>/.

Default is local QpiAI Opt solves. --platform submits the main-plan stages as paid platform jobs.
"""

import argparse
import json
import os
from pathlib import Path

from qpiai_opt.opt_solvers import Client

from contracts.manifest import sha256_json

from .baselines import run_baselines
from .milp import STAGES, optimize
from .platform_guard import DAILY_LIMIT, PlatformBudget
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


def build_section(problem, client, run_dir, with_sensitivity=True, mode="local", budget=None) -> dict:
    baselines = run_baselines(problem)
    optimized, runs = optimize(problem, client, horizon_for(problem, baselines), run_dir, mode=mode, budget=budget)
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
                "evidence": list(a.evidence),
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


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--assumptions", default=DEFAULT_ASSUMPTIONS)
    ap.add_argument("--inventory", default=DEFAULT_INVENTORY)
    ap.add_argument("--out", default=REPO / "out" / "schedule.json")
    ap.add_argument("--runs", default=REPO / "runs")
    ap.add_argument("--no-sensitivity", action="store_true")
    ap.add_argument("--platform", action="store_true", help="opt-in: submit the main-plan MILP stages as paid QpiAI platform jobs")
    ap.add_argument("--allow-more", action="store_true", help=f"allow more than {DAILY_LIMIT} platform jobs per UTC day")
    args = ap.parse_args(argv)

    problem = load_problem(args.assumptions, args.inventory)
    mode, budget = "local", None
    if args.platform:
        mode = "platform"
        budget = PlatformBudget(Path(args.runs) / "platform_jobs.log", allow_more=args.allow_more)
        budget.check(len(STAGES[problem.objective]))  # refuse up front rather than after a partial run
    client = Client(api_key=os.environ["QPIAI_OPT_API_KEY"])
    section = build_section(problem, client, Path(args.runs), not args.no_sensitivity, mode, budget)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(section, indent=1))
    print(f"wrote {out}")
    for r in section["solver_runs"]:
        print(f"  {r['stage']}: solver={r['solver']} job_id={r['job_id']} problem_id={r['problem_id']} run_id={r['run_id']}")
        if r["comparison"]:
            c = r["comparison"]
            print(f"    objective platform={c['platform_objective']!r} local={c['local_objective']!r} match={c['match']}")
    for name in ("fcfs", "greedy"):
        for row in section["avoided"][f"vs_{name}"]:
            print(f"  vs {name:6} {row['scenario']}: {row['exposure_years_avoided']:.3f} exposure-years avoided")


if __name__ == "__main__":
    main()
