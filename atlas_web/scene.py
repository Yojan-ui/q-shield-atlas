"""scene.json: everything THE LATTICE needs for one workspace, precomputed once per results.json change.

Data fields come from results.json verbatim (status, waves, remaining exposure per week, handshakes,
ledger entries). Per-asset exposure-years are computed by the scheduler's own evaluator
(schedule.problem.exposure_years) on the assets and assumptions recorded in results.json. Positions are
presentation layout (config/atlas_web.json "presentation"), not data.
"""

import hashlib
import json

from contracts.manifest import sha256_json
from detect.static_scan import iter_files
from schedule.problem import exposure_years, problem_from_dicts

from .config import settings

# asset status -> lattice state (the brief's visual language)
STATE = {"applied": "hybrid", "planned": "classical", "not_verified_in_lab": "ghost", "rolled_back": "rolled_back",
         "rollback_failed": "rollback_failed", "partially_verified": "ghost"}


def _layout(nodes: list[dict], pres: dict) -> None:
    layers = {k: i for i, layer in enumerate(pres["layers"]) for k in layer["kinds"]}
    groups: dict[int, list] = {}
    for n in nodes:
        n["layer"] = pres["layers"][layers.get(n["kind"], 1)]["id"]
        groups.setdefault(layers.get(n["kind"], 1), []).append(n)
    cell, gap = pres["cell"], pres["layer_spacing"]
    for li, group in groups.items():
        group.sort(key=lambda n: n["id"])
        cols = max(1, round(len(group) ** 0.5 + 0.49))
        rows = (len(group) + cols - 1) // cols
        for i, n in enumerate(group):
            c, r = i % cols, i // cols
            n["pos"] = [round((c - (cols - 1) / 2) * cell, 3), round(((rows - 1) / 2 - r) * cell, 3), round(-li * gap, 3)]


def scanned_files(src, detect: dict | None) -> dict:
    """Every file the scanner would read (detect.static_scan.iter_files), with line counts and its findings.
    `verified` is true only if the listing hashes to the tree_sha256 recorded by the detect run."""
    if not detect or src is None or not src.exists():
        return {"verified": False, "files": [], "status_text": "source tree not available"}
    import hashlib

    tree, files = [], []
    by_file: dict = {}
    for f in detect.get("findings", []):
        by_file.setdefault(f["file"], []).append({"line": f["line"], "family": f["family"], "rule": f["rule"], "use": f["use"]})
    drift = {p["service"] for p in detect.get("probes", []) if p.get("drift")}
    for path in iter_files(src.resolve()):
        rel = path.relative_to(src.resolve()).as_posix()
        data = path.read_bytes()
        tree.append([rel, hashlib.sha256(data).hexdigest()])
        files.append({"path": rel, "lines": data.count(b"\n") + 1, "findings": by_file.get(rel, []),
                      "service": rel.split("/")[1] if rel.startswith("services/") and rel.count("/") >= 2 else None})
    for f in files:
        f["drift"] = f["service"] in drift
    ok = sha256_json(tree) == detect.get("tree_sha256")
    return {"verified": ok, "files": files if ok else [],
            "status_text": None if ok else "the source tree changed since the last scan; re-run detect to see it"}


def build_scene(ws_id: str, r: dict | None, src=None) -> dict:
    if not r:
        return {"workspace": ws_id, "available": False, "status_text": "not yet run"}
    pres = settings()["presentation"]
    problem = problem_from_dicts(r["assumptions"], {"assets": r["assets"]})
    weeks = r["exposure"]["completion_week"]
    plan_src = {"solver": r["exposure"]["produced_by"]["solver"], "run_ids": r["exposure"]["produced_by"]["run_ids"],
                "job_ids": r["exposure"]["produced_by"]["job_ids"],
                "job_id_reason": next((x.get("job_id_reason") for x in r.get("solver_runs", []) if x.get("job_id_reason")), None)}
    by_id = problem.by_id()
    standin = {}
    for w in r.get("waves", []):
        for e in (w.get("evidence") or {}).get("lab_services", []):
            for a in e.get("assets", []):
                standin[a] = {"lab_service": e.get("lab_service"), "status": e.get("status"),
                              "pq_handshake": ((e.get("gates") or {}).get("pq_handshake") or {}).get("result"),
                              "pq_auth": ((e.get("gates") or {}).get("pq_auth") or {}).get("result"),
                              "run_id": w["evidence"].get("run_id")}
    nodes = []
    for a in r["assets"]:
        asset = by_id[a["id"]]
        nodes.append({
            "id": a["id"], "name": a.get("name", a["id"]), "kind": a.get("kind"), "data_class": a.get("data_class"),
            "algorithm": a.get("algorithm"), "status": a.get("status", "planned"), "state": STATE.get(a.get("status"), "classical"),
            "pq_auth": (standin.get(a["id"]) or {}).get("pq_auth") == "PASS",
            "week": weeks.get(a["id"]), "week_fcfs": r["baselines"]["fcfs"]["completion_week"].get(a["id"]),
            "week_greedy": r["baselines"]["greedy"]["completion_week"].get(a["id"]),
            "exposure_years": {s.name: exposure_years(problem, asset, weeks[a["id"]], s) for s in problem.scenarios},
            "findings": len(a.get("evidence") or []), "depends_on": list(a.get("depends_on") or []),
            "standin": standin.get(a["id"]), "vulnerable": True,
        })
    for sid in ((r.get("detect") or {}).get("inventory") or {}).get("not_vulnerable", []):
        nodes.append({"id": sid, "name": sid, "kind": None, "status": "not_vulnerable", "state": "clean", "pq_auth": False,
                      "week": None, "exposure_years": None, "findings": 0, "depends_on": [], "standin": None, "vulnerable": False})
    _layout(nodes, pres)
    ids = {n["id"] for n in nodes}
    edges = [{"from": n["id"], "to": d} for n in nodes for d in n["depends_on"] if d in ids]
    plans = {"optimized": r["exposure"], "fcfs": r["baselines"]["fcfs"], "greedy": r["baselines"]["greedy"]}
    tower = {k: {s["scenario"]: [p["exposure_years"] for p in s["points"]] for s in p["remaining_by_week"]} for k, p in plans.items()}
    he = r.get("handshake_evidence") or {}
    led = r.get("ledger") or {}
    scene = {
        "workspace": ws_id, "available": True, "generated_at": r.get("generated_at"),
        "scenarios": [{"name": s.name, "year": s.year, "weight": s.weight} for s in problem.scenarios],
        "layers": [{"id": l["id"], "label": l["label"], "z": -i * pres["layer_spacing"]} for i, l in enumerate(pres["layers"])],
        "nodes": nodes, "edges": edges,
        "weeks": list(range(len(next(iter(tower["optimized"].values()), [])))),
        "tower": tower,
        "waves": [{"week": w["week"], "assets": w["assets"], "status": w["status"]} for w in r.get("waves", [])],
        "files": scanned_files(src, r.get("detect")),
        "lab_services": [{"service_id": s["service_id"], "group": s.get("negotiated_group"), "kex_class": s.get("kex_class"),
                          "auth_alg": s.get("auth_alg"), "label": s.get("label")} for s in he.get("sessions", [])],
        "ledger": {"entry_count": led.get("entry_count"), "root": led.get("root"),
                   "types": [e["type"] for e in led.get("entries", [])]} if led else None,
        "provenance": {"plan": plan_src, "exposure_years": "schedule.problem.exposure_years on results.json assets, "
                       "assumptions and the optimised plan's completion weeks", "positions": "presentation layout, not data",
                       "results_generated_at": r.get("generated_at")},
    }
    return scene


def scene_bytes(ws_id: str, r: dict | None, src=None) -> tuple[bytes, str]:
    body = json.dumps(build_scene(ws_id, r, src), separators=(",", ":")).encode()
    return body, '"' + hashlib.sha256(body).hexdigest()[:32] + '"'
