"""Migration scheduling problem and an independent plan evaluator.

Mosca-style exposure: data harvested today must stay secret for X_i years (shelf life).
If asset i finishes migrating t_i years from the start year and a CRQC arrives in year Z,
the data is exposed for e_i = max(0, X_i + t_i - (Z - start_year)) years.

Every plan (MILP or baseline) is scored by `evaluate`, never by a solver's own objective.
"""

import json
import math
from dataclasses import dataclass, field, replace
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
DEFAULT_ASSUMPTIONS = REPO / "config" / "assumptions.json"
DEFAULT_INVENTORY = REPO / "schedule" / "data" / "mock_bank_assets.json"


@dataclass(frozen=True)
class Asset:
    id: str
    name: str
    shelf_life_years: float  # X_i, assumption
    effort_days: float  # w_i, assumption
    risk_weight: float  # r_i, assumption
    depends_on: tuple[str, ...] = ()
    kind: str = ""
    data_class: str = ""
    algorithm: str = ""
    evidence: tuple = ()  # file:line findings from detect/, if the inventory came from a scan


@dataclass(frozen=True)
class Scenario:
    name: str
    year: float
    weight: float


@dataclass(frozen=True)
class Problem:
    assets: tuple[Asset, ...]
    scenarios: tuple[Scenario, ...]
    start_year: float
    capacity_days_per_week: float
    horizon_weeks: int
    weeks_per_year: int = 52
    objective: str = "expected"
    raw_assumptions: dict = field(default_factory=dict, compare=False, repr=False)

    def __post_init__(self):
        ids = [a.id for a in self.assets]
        if len(set(ids)) != len(ids):
            raise ValueError("asset ids must be unique")
        known = set(ids)
        for a in self.assets:
            if missing := set(a.depends_on) - known:
                raise ValueError(f"{a.id} depends on unknown assets {sorted(missing)}")
            if a.effort_days > self.capacity_days_per_week:
                raise ValueError(
                    f"{a.id} effort {a.effort_days} d exceeds weekly capacity "
                    f"{self.capacity_days_per_week} d; split the asset"
                )
        if self.objective not in {"expected", "robust"}:
            raise ValueError("objective must be 'expected' or 'robust'")
        if not self.scenarios or any(s.weight < 0 for s in self.scenarios):
            raise ValueError("need at least one scenario with non-negative weight")
        topo_order(self)  # raises on cycles

    def by_id(self) -> dict[str, Asset]:
        return {a.id: a for a in self.assets}


def load_problem(assumptions_path=DEFAULT_ASSUMPTIONS, inventory_path=DEFAULT_INVENTORY) -> Problem:
    cfg = json.loads(Path(assumptions_path).read_text())
    inventory = json.loads(Path(inventory_path).read_text())
    return problem_from_dicts(cfg, inventory)


def problem_from_dicts(cfg: dict, inventory: dict) -> Problem:
    classes, efforts = cfg["data_classes"], cfg["effort_days_by_kind"]
    assets = []
    for row in inventory["assets"]:
        cls = classes.get(row.get("data_class"), {})
        assets.append(
            Asset(
                id=row["id"],
                name=row.get("name", row["id"]),
                shelf_life_years=float(row.get("shelf_life_years", cls.get("shelf_life_years"))),
                effort_days=float(row.get("effort_days", efforts.get(row.get("kind")))),
                risk_weight=float(row.get("risk_weight", cls.get("risk_weight"))),
                depends_on=tuple(row.get("depends_on", ())),
                kind=row.get("kind", ""),
                data_class=row.get("data_class", ""),
                algorithm=row.get("algorithm", ""),
                evidence=tuple(row.get("evidence", ())),
            )
        )
    return Problem(
        assets=tuple(assets),
        scenarios=tuple(Scenario(s["name"], float(s["year"]), float(s["weight"])) for s in cfg["scenarios"]),
        start_year=float(cfg["start_year"]),
        capacity_days_per_week=float(cfg["capacity_days_per_week"]),
        horizon_weeks=int(cfg["horizon_weeks"]),
        weeks_per_year=int(cfg.get("weeks_per_year", 52)),
        objective=cfg.get("objective", "expected"),
        raw_assumptions=cfg,
    )


def scale(problem: Problem, *, shelf=1.0, risk=1.0, effort=1.0) -> Problem:
    """Return a copy with assumption values multiplied (used by sensitivity analysis)."""
    assets = tuple(
        replace(
            a,
            shelf_life_years=a.shelf_life_years * shelf,
            risk_weight=a.risk_weight * risk,
            effort_days=min(a.effort_days * effort, problem.capacity_days_per_week),
        )
        for a in problem.assets
    )
    return replace(problem, assets=assets)


def topo_order(problem: Problem, priority=None) -> list[str]:
    """Dependencies-first order; among ready assets, lowest `priority(asset)` goes first."""
    priority = priority or (lambda a: 0)
    assets = problem.by_id()
    remaining = {a.id: set(a.depends_on) for a in problem.assets}
    order = []
    while remaining:
        ready = [i for i, deps in remaining.items() if not deps]
        if not ready:
            raise ValueError(f"dependency cycle among {sorted(remaining)}")
        nxt = min(ready, key=lambda i: (priority(assets[i]), i))
        order.append(nxt)
        del remaining[nxt]
        for deps in remaining.values():
            deps.discard(nxt)
    return order


def check_feasible(problem: Problem, weeks: dict[str, int], horizon: int | None = None) -> list[str]:
    """Return a list of violated constraints (empty list means feasible)."""
    errors = []
    if set(weeks) != {a.id for a in problem.assets}:
        errors.append("plan must assign every asset exactly once")
        return errors
    for i, k in weeks.items():
        if not isinstance(k, int) or k < 1 or (horizon is not None and k > horizon):
            errors.append(f"{i}: week {k} outside 1..{horizon}")
    load: dict[int, float] = {}
    for a in problem.assets:
        load[weeks[a.id]] = load.get(weeks[a.id], 0.0) + a.effort_days
        for d in a.depends_on:
            if weeks[d] > weeks[a.id]:
                errors.append(f"dependency {d} (week {weeks[d]}) after dependent {a.id} (week {weeks[a.id]})")
    for k, used in sorted(load.items()):
        if used > problem.capacity_days_per_week + 1e-9:
            errors.append(f"week {k}: {used} d exceeds capacity {problem.capacity_days_per_week} d")
    return errors


def exposure_years(problem: Problem, asset: Asset, week: int, scenario: Scenario) -> float:
    t_years = week / problem.weeks_per_year
    return max(0.0, asset.shelf_life_years + t_years - (scenario.year - problem.start_year))


def evaluate(problem: Problem, weeks: dict[str, int], method: str) -> dict:
    """Score a plan; output matches the results.json `plan_summary` contract."""
    per_scenario = []
    for s in problem.scenarios:
        raw = [exposure_years(problem, a, weeks[a.id], s) for a in problem.assets]
        per_scenario.append(
            {
                "scenario": s.name,
                "year": s.year,
                "exposure_years": math.fsum(raw),
                "weighted_exposure": math.fsum(a.risk_weight * e for a, e in zip(problem.assets, raw)),
            }
        )
    total_weight = math.fsum(s.weight for s in problem.scenarios) or 1.0
    expected = math.fsum(s.weight * p["weighted_exposure"] for s, p in zip(problem.scenarios, per_scenario)) / total_weight
    return {
        "method": method,
        "completion_week": dict(weeks),
        "waves": waves(problem, weeks),
        "per_scenario": per_scenario,
        "expected_weighted": expected,
        "worst_case_weighted": max(p["weighted_exposure"] for p in per_scenario),
        "makespan_weeks": max(weeks.values(), default=0),
    }


def waves(problem: Problem, weeks: dict[str, int], status="planned") -> list[dict]:
    out: dict[int, list[Asset]] = {}
    for a in problem.assets:
        out.setdefault(weeks[a.id], []).append(a)
    return [
        {
            "week": k,
            "assets": [a.id for a in out[k]],
            "effort_days": math.fsum(a.effort_days for a in out[k]),
            "status": status,
        }
        for k in sorted(out)
    ]
