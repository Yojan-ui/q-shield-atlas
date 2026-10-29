"""migration_schedule solvers: QpiAI Opt MILP and the two classical baselines (schedule/)."""

from schedule.baselines import run_baselines
from schedule.milp import optimize

from . import Solution


def _size(problem, horizon):
    n = len(problem.assets)
    return {"assets": n, "horizon_weeks": horizon, "variables": n * horizon + n * len(problem.scenarios),
            "binary_variables": n * horizon}


def milp(inst, **_):
    """inst: {problem, client, horizon, run_dir?, mode?, budget?}. record = (plan summary, solver runs)."""
    p, horizon = inst["problem"], inst["horizon"]
    summary, runs = optimize(p, inst["client"], horizon, inst.get("run_dir"), mode=inst.get("mode", "local"), budget=inst.get("budget"))
    obj = summary["worst_case_weighted"] if p.objective == "robust" else summary["expected_weighted"]
    return Solution("migration_schedule", "milp", summary["completion_week"], obj, True, 0.0, _size(p, horizon), (summary, runs))


def _baseline(name):
    def run(inst, **_):
        p = inst["problem"]
        plan = run_baselines(p)[name]
        obj = plan["worst_case_weighted"] if p.objective == "robust" else plan["expected_weighted"]
        return Solution("migration_schedule", name, plan["completion_week"], obj, True, 0.0,
                        _size(p, plan["makespan_weeks"]), plan)
    return run


SOLVERS = {"milp": milp, "fcfs": _baseline("fcfs"), "greedy": _baseline("greedy")}
