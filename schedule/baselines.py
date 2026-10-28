"""Classical baselines, scored with the same evaluator as the MILP.

Both are list schedulers: walk assets in a dependency-respecting priority order and put each
one in the earliest week that is no earlier than its dependencies and still has capacity.
- fcfs:   priority = order of discovery in the inventory
- greedy: priority = risk_weight / effort_days, highest first (Smith's weighted-shortest-job rule)
"""

from .problem import Problem, evaluate, topo_order


def list_schedule(problem: Problem, order: list[str]) -> dict[str, int]:
    assets = problem.by_id()
    load: dict[int, float] = {}
    weeks: dict[str, int] = {}
    for i in order:
        a = assets[i]
        k = max((weeks[d] for d in a.depends_on), default=1)
        while load.get(k, 0.0) + a.effort_days > problem.capacity_days_per_week + 1e-9:
            k += 1
        weeks[i] = k
        load[k] = load.get(k, 0.0) + a.effort_days
    return weeks


def fcfs(problem: Problem) -> dict[str, int]:
    position = {a.id: n for n, a in enumerate(problem.assets)}
    return list_schedule(problem, topo_order(problem, lambda a: position[a.id]))


def greedy(problem: Problem) -> dict[str, int]:
    return list_schedule(problem, topo_order(problem, lambda a: -a.risk_weight / a.effort_days))


def run_baselines(problem: Problem) -> dict[str, dict]:
    out = {"fcfs": evaluate(problem, fcfs(problem), "fcfs"), "greedy": evaluate(problem, greedy(problem), "greedy")}
    for name, plan in out.items():
        plan["produced_by"] = {
            "solver": f"python list scheduler ({name}), scored by schedule.problem.evaluate",
            "run_ids": [],
            "job_ids": [],
        }
    return out
