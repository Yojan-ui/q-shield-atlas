"""Migration time estimate from the inputs (total and per wave), and the user's time threshold.

estimate      the optimised plan's makespan (weeks until the last wave), from schedule/ (MILP)
lower_bound   ceil(total assumed effort / weekly capacity): no plan can finish sooner under the capacity
Both come from the assumed efforts and capacity in config/assumptions.json (labelled assumptions).
"""

import math

THRESHOLD_MAX_WEEKS = 520


def estimate(results: dict | None, threshold_weeks=None) -> dict:
    if not results or not results.get("assets"):
        reason = "not yet run" if not results else "nothing to migrate"
        return {"available": False, "status_text": reason, "threshold_weeks": threshold_weeks, "exceeded": None}
    a = results["assumptions"]
    weeks = results["exposure"]["makespan_weeks"]
    effort = sum(x["effort_days"] for x in results["assets"])
    cap = a["capacity_days_per_week"]
    per_year = a["weeks_per_year"]
    sr = (results.get("solver_runs") or [{}])[0]
    out = {
        "available": True,
        "estimate_weeks": weeks,
        "estimate_years": round(weeks / per_year, 3),
        "finish_year": round(a["start_year"] + weeks / per_year, 2),
        "lower_bound_weeks": math.ceil(effort / cap - 1e-9),
        "total_effort_days": effort,
        "capacity_days_per_week": cap,
        "per_wave": [{"week": w["week"], "systems": len(w["assets"]), "effort_days": w["effort_days"],
                      "capacity_days": cap, "status": w["status"]} for w in results.get("waves", [])],
        "baselines_weeks": {k: v["makespan_weeks"] for k, v in (results.get("baselines") or {}).items()},
        "basis": "makespan of the optimised plan (QpiAI Opt MILP); lower bound = total assumed effort / weekly capacity",
        "label": "assumption-based: efforts and capacity are assumptions in config/assumptions.json",
        "source": {"run_id": sr.get("run_id"), "ts": sr.get("ts"), "solver": sr.get("solver")},
        "threshold_weeks": threshold_weeks,
        "exceeded": None,
        "over_by_weeks": None,
    }
    if threshold_weeks is not None:
        out["exceeded"] = weeks > threshold_weeks
        out["over_by_weeks"] = max(0, weeks - threshold_weeks)
    return out


def parse_threshold(value):
    """None, or an integer number of weeks in 1..THRESHOLD_MAX_WEEKS; ValueError otherwise."""
    if value in (None, ""):
        return None
    try:
        v = float(value)
    except (TypeError, ValueError):
        raise ValueError("threshold_weeks must be a number of weeks") from None
    if not (v == int(v) and 1 <= v <= THRESHOLD_MAX_WEEKS):
        raise ValueError(f"threshold_weeks must be a whole number of weeks between 1 and {THRESHOLD_MAX_WEEKS}")
    return int(v)
