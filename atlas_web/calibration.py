"""Calibration: record actual engineer-days per migrated asset, propose new effort_days_by_kind and weekly
capacity as medians of the actuals (assumed vs measured with n). Never applied automatically: applying
writes the workspace assumptions.json, records a payload under runs/, and the run re-plans and signs it."""

import json
import statistics
import time
from pathlib import Path

from contracts.manifest import new_run_id, sha256_hex, utc_now

from .workspaces import Workspace, WorkspaceError

LABEL = "calibrated from your measurements"


def _path(ws: Workspace) -> Path:
    return ws.config / "calibration_actuals.json"


def actuals(ws: Workspace) -> list[dict]:
    p = _path(ws)
    return json.loads(p.read_text()) if p.exists() else []


def _assets(ws: Workspace) -> dict:
    try:
        r = json.loads(ws.results.read_text())
    except (OSError, ValueError):
        return {}
    weeks = {a: w["week"] for w in r.get("waves", []) for a in w.get("assets", [])}
    return {a["id"]: {"kind": a.get("kind"), "status": a.get("status"), "week": weeks.get(a["id"]),
                      "assumed_effort_days": a.get("effort_days")} for a in r.get("assets", [])}


def record(ws: Workspace, asset_id: str, engineer_days, user: str, note: str = "") -> dict:
    assets = _assets(ws)
    if asset_id not in assets:
        raise WorkspaceError("unknown_asset", f"asset {asset_id!r} is not in this workspace's results.json; run the pipeline first", 422)
    try:
        days = float(engineer_days)
    except (TypeError, ValueError):
        days = -1
    if not 0 < days <= 365:
        raise WorkspaceError("invalid_actual", "engineer_days must be a number between 0 and 365", 422, {"engineer_days": "0 < days ≤ 365"})
    rows = [a for a in actuals(ws) if a["asset_id"] != asset_id]  # latest measurement per asset wins
    row = {"asset_id": asset_id, "kind": assets[asset_id]["kind"], "week": assets[asset_id]["week"],
           "engineer_days": days, "recorded_by": user, "ts": utc_now(), "note": str(note)[:200]}
    rows.append(row)
    _path(ws).write_text(json.dumps(rows, indent=1))
    return row


def proposal(ws: Workspace) -> dict:
    a = json.loads(ws.assumptions.read_text())
    rows = actuals(ws)
    kinds = []
    for kind, assumed in sorted(a["effort_days_by_kind"].items()):
        vals = [r["engineer_days"] for r in rows if r["kind"] == kind]
        kinds.append({"kind": kind, "assumed": assumed, "n": len(vals),
                      "measured_median": statistics.median(vals) if vals else None})
    per_week: dict = {}
    for r in rows:
        if r["week"] is not None:
            per_week[r["week"]] = per_week.get(r["week"], 0) + r["engineer_days"]
    cap = {"assumed": a["capacity_days_per_week"], "n_weeks": len(per_week),
           "measured_median": statistics.median(per_week.values()) if per_week else None,
           "definition": "median over weeks of the summed actual engineer-days of assets completed that week"}
    return {"label": LABEL, "actuals": rows, "effort_days_by_kind": kinds, "capacity_days_per_week": cap,
            "assets": _assets(ws), "note": "Assumed values are planning assumptions (config/assumptions.json); "
            "measured values are medians of the actuals you recorded. Nothing is applied until you apply it."}


def apply(ws: Workspace, user: str, only: list | None = None) -> Path:
    """Write the proposed values (all, or the keys in `only`) into the workspace assumptions and record the
    change as a payload. Keys: "effort_days_by_kind.<kind>" and "capacity_days_per_week"."""
    p = proposal(ws)
    if not p["actuals"]:
        raise WorkspaceError("no_actuals", "record at least one actual before applying a calibration", 422)
    old_text = ws.assumptions.read_text()
    a = json.loads(old_text)
    proposed = {f"effort_days_by_kind.{k['kind']}": (k["assumed"], k["measured_median"])
                for k in p["effort_days_by_kind"] if k["measured_median"] is not None}
    cap = p["capacity_days_per_week"]
    if cap["measured_median"] is not None:
        proposed["capacity_days_per_week"] = (cap["assumed"], cap["measured_median"])
    if only is not None:
        unknown = [k for k in only if k not in proposed]
        if unknown or not only:
            raise WorkspaceError("bad_selection", f"nothing to apply for: {', '.join(unknown) or '(empty selection)'}", 422)
        proposed = {k: v for k, v in proposed.items() if k in only}
    changes = {}
    for key, (assumed, measured) in proposed.items():
        changes[key] = [assumed, measured]
        if key == "capacity_days_per_week":
            a["capacity_days_per_week"] = measured
        else:
            a["effort_days_by_kind"][key.split(".", 1)[1]] = measured
    too_big = [k for k, v in a["effort_days_by_kind"].items() if v > a["capacity_days_per_week"]]
    if too_big:
        raise WorkspaceError("infeasible", f"each asset must fit in one week of capacity; effort for {', '.join(too_big)} "
                             f"exceeds {a['capacity_days_per_week']} days/week", 422)
    a.setdefault("calibration", {})
    a["calibration"] = {"label": LABEL, "applied_at": utc_now(), "applied_by": user, "n_actuals": len(p["actuals"])}
    new_text = json.dumps(a, indent=2) + "\n"
    run_id = new_run_id()
    d = ws.runs / run_id
    d.mkdir(parents=True)
    payload = d / "manifest.json"
    payload.write_text(json.dumps({"run_id": run_id, "type": "calibration.apply", "ts": utc_now(), "applied_by": user,
                                   "label": LABEL, "changes": changes, "actuals": p["actuals"],
                                   "assumptions_before_sha256": sha256_hex(old_text.encode()),
                                   "assumptions_after_sha256": sha256_hex(new_text.encode())}, indent=1))
    ws.assumptions.write_text(new_text)
    return payload


ASSUMPTION_NUMBERS = ("start_year", "capacity_days_per_week", "horizon_weeks")


def save_assumptions(ws: Workspace, new: dict) -> dict:
    """Validated edit of the workspace assumptions (same structure as config/assumptions.json)."""
    cur = json.loads(ws.assumptions.read_text())
    errors = {}
    out = json.loads(json.dumps(cur))
    def pos(path, v, integer=False):
        ok = isinstance(v, (int, float)) and not isinstance(v, bool) and v > 0 and (not integer or float(v).is_integer())
        if not ok:
            errors[path] = "a positive integer" if integer else "a positive number"
        return v
    for k in ASSUMPTION_NUMBERS:
        if k in new:
            out[k] = pos(k, new[k], integer=k == "horizon_weeks")
    for kind, v in (new.get("effort_days_by_kind") or {}).items():
        if kind not in cur["effort_days_by_kind"]:
            errors[f"effort_days_by_kind.{kind}"] = "unknown kind"
        else:
            out["effort_days_by_kind"][kind] = pos(f"effort_days_by_kind.{kind}", v)
    for dc, vals in (new.get("data_classes") or {}).items():
        if dc not in cur["data_classes"]:
            errors[f"data_classes.{dc}"] = "unknown data class"
            continue
        for f in ("shelf_life_years", "risk_weight"):
            if f in (vals or {}):
                out["data_classes"][dc][f] = pos(f"data_classes.{dc}.{f}", vals[f])
    if "scenarios" in new:
        sc = new["scenarios"]
        if not isinstance(sc, list) or not sc or not all(isinstance(s, dict) and {"name", "year", "weight"} <= set(s) for s in sc):
            errors["scenarios"] = "a list of {name, year, weight}"
        else:
            for i, s in enumerate(sc):
                pos(f"scenarios.{i}.year", s["year"], integer=True)
                if not isinstance(s["weight"], (int, float)) or not 0 <= s["weight"] <= 1:
                    errors[f"scenarios.{i}.weight"] = "between 0 and 1"
            weights = [s["weight"] for s in sc if isinstance(s["weight"], (int, float))]
            if len(weights) == len(sc) and abs(sum(weights) - 1) > 1e-9:
                errors["scenarios"] = "weights must sum to 1"
            out["scenarios"] = [{"name": str(s["name"])[:16], "year": s["year"], "weight": s["weight"]} for s in sc]
    if not errors:
        too_big = [k for k, v in out["effort_days_by_kind"].items() if v > out["capacity_days_per_week"]]
        if too_big:
            errors["capacity_days_per_week"] = f"each asset must fit in one week; {', '.join(too_big)} exceed it"
    if errors:
        raise WorkspaceError("invalid_assumptions", "some assumptions are invalid", 422, errors)
    ws.assumptions.write_text(json.dumps(out, indent=2) + "\n")
    return out
