"""Review: results awaiting a human decision, approved or rejected with a reason, signed into the Proof Chain.

Items come from the workspace's latest results.json: the migration plan, each wave's gate result, the QAOA
cross-check and the benchmark (if run). Each item is bound to its evidence by run_id and the SHA-256 of that
run's manifest, so a new run produces new items. A decision is a JSON payload under runs/reviews/, appended
with `python -m ledger append --type review.decision` (ML-DSA-65) and followed by `ledger verify`.
"""

import hashlib
import json
import subprocess
import sys
import time
from pathlib import Path

from .workspaces import WorkspaceError

ENTRY_TYPE = "review.decision"
DECISIONS = ("approve", "reject")


def _sha(p: Path) -> str | None:
    return hashlib.sha256(p.read_bytes()).hexdigest() if p.exists() else None


def _ledger_entry(results: dict, run_id: str) -> int | None:
    for e in ((results or {}).get("ledger") or {}).get("entries", []):
        if run_id in e["payload_ref"] and e["type"] != ENTRY_TYPE:
            return e["index"]
    return None


def _explain(results: dict, it: dict) -> dict:
    """What / How / Why for one item, from recorded fields only."""
    a = {x["id"]: x for x in results["assets"]}
    sr = (results.get("solver_runs") or [{}])[0]
    if it["kind"] == "plan":
        av = (results.get("avoided") or {}).get("vs_fcfs", [])
        return {"what": [f"Migrate {len(results['assets'])} systems in {len(results['waves'])} weekly waves ({results['exposure']['makespan_weeks']} weeks)."],
                "how": [f"Solver: QpiAI Opt {sr.get('mode', 'local')} MILP, {sr.get('termination')}, {sr.get('guarantee', '').replace('_', ' ')}.",
                        f"Capacity {results['assumptions']['capacity_days_per_week']} engineer-days per week (assumption)."],
                "why": ["Minimises risk- and scenario-weighted exposure-years; never worse than first-come-first-served or greedy on the same data."]
                       + [f"{x['scenario']}: {x['exposure_years_avoided']:.3f} exposure-years avoided vs first-come-first-served." for x in av]}
    if it["kind"] == "wave":
        w = next(x for x in results["waves"] if f":{x['week']}" == it["id"][it["id"].rindex(":"):])
        labs = (w.get("evidence") or {}).get("lab_services", [])
        how = [f"{x['lab_service']}: {x['from_mode']} → {x['to_mode']}; post-quantum handshake {((x.get('gates') or {}).get('pq_handshake') or {}).get('result', 'not run')}"
               f" ({((x.get('gates') or {}).get('pq_handshake') or {}).get('negotiated_group') or 'no handshake'}); status {x.get('status', '?')}" for x in labs]
        return {"what": [f"{a[i]['name']} ({i}): {a[i]['algorithm']}" for i in w["assets"] if i in a],
                "how": how or ["No lab service is mapped to these systems: not verified in the lab."],
                "why": [f"{i}: risk weight {a[i]['risk_weight']}, data shelf life {a[i]['shelf_life_years']} years, effort {a[i]['effort_days']} engineer-days"
                        + (f"; after its dependencies {', '.join(a[i]['depends_on'])}" if a[i]["depends_on"] else "") for i in w["assets"] if i in a]
                       + [f"The optimiser placed this wave in week {w['week']} to cut weighted exposure fastest within capacity."]}
    if it["kind"] == "qaoa":
        q = results["qaoa"]
        return {"what": [f"Cross-check week {q['problem']['week']}'s selection ({q['problem']['n_variables']} variables) with QAOA."],
                "how": [f"QAOA p = 1…3 on simulators ({(q.get('qpiai_local') or {}).get('device', 'numpy statevector')}); exact optimum by brute force."],
                "why": ["Measures QAOA against a known right answer; no quantum advantage is claimed."]}
    return {"what": [it["summary"]], "how": ["python -m bench: exact, MILP, random, QAOA, hybrid on the same instances."],
            "why": ["Shows solution quality, runtime and problem size side by side."]}


def items(ws, results: dict | None) -> list[dict]:
    if not results or not results.get("assets"):
        return []
    runs = ws.runs
    out = []
    sr = results.get("solver_runs") or []
    if sr:
        m = results["exposure"]
        out.append({"id": f"plan:{sr[0]['run_id']}", "kind": "plan", "title": "Migration plan",
                    "summary": f"{len(results['assets'])} systems in {len(results['waves'])} waves, {m['makespan_weeks']} weeks ({sr[0]['solver']}, {sr[0].get('termination')})",
                    "run_id": sr[0]["run_id"], "evidence_sha256": _sha(runs / sr[0]["run_id"] / "manifest.json")})
    g = results.get("gates")
    if g:
        for w in results["waves"]:
            out.append({"id": f"wave:{g['wave_run_id']}:{w['week']}", "kind": "wave", "title": f"Wave {w['week']}",
                        "summary": f"{', '.join(w['assets'])}: gate status {w['status'].replace('_', ' ')}",
                        "run_id": g["wave_run_id"], "status_hint": w["status"],
                        "evidence_sha256": _sha(runs / g["wave_run_id"] / "wave_runner.json")})
    q = results.get("qaoa")
    if q:
        out.append({"id": f"qaoa:{q['run_id']}", "kind": "qaoa", "title": "QAOA cross-check",
                    "summary": f"link cutover selection, week {q['problem']['week']}, {q['problem']['n_variables']} variables; simulator only",
                    "run_id": q["run_id"], "evidence_sha256": _sha(runs / q["run_id"] / "manifest.json")})
    bf = ws.out / "bench.json"
    if bf.exists():
        b = json.loads(bf.read_text())
        out.append({"id": f"bench:{b['run_id']}", "kind": "bench", "title": "Solver benchmark",
                    "summary": f"{len(b['instances'])} instances, {len(b['rows'])} rows", "run_id": b["run_id"],
                    "evidence_sha256": _sha(runs / b["run_id"] / "manifest.json")})
    v = results.get("ledger_verification") or {}
    for it in out:
        it.update(_explain(results, it))
        it["ledger_index"] = _ledger_entry(results, it["run_id"])
        it["signature"] = ("verified" if v.get("ok") else "not verified") if it["ledger_index"] is not None else "not signed yet"
    return out


def decisions(ws, results: dict | None) -> dict[str, dict]:
    """item id -> latest signed decision (from the ledger entries' payload files)."""
    out = {}
    for e in ((results or {}).get("ledger") or {}).get("entries", []):
        if e["type"] != ENTRY_TYPE:
            continue
        p = ws.root / e["payload_ref"]
        if p.exists():
            d = json.loads(p.read_text())
            out[d["item"]] = {**{k: d[k] for k in ("decision", "reason", "by", "ts")}, "ledger_index": e["index"]}
    return out


def listing(ws, results) -> list[dict]:
    done = decisions(ws, results)
    return [{**i, "status": {"approve": "approved", "reject": "rejected"}[done[i["id"]]["decision"]] if i["id"] in done else "pending",
             "decision": done.get(i["id"])} for i in items(ws, results)]


def decide(ws, results, item_id: str, decision: str, reason: str, user: str) -> dict:
    if decision not in DECISIONS:
        raise WorkspaceError("bad_decision", "decision must be approve or reject", 422)
    reason = (reason or "").strip()
    if not 3 <= len(reason) <= 500:
        raise WorkspaceError("reason_required", "give a reason (3 to 500 characters)", 422, {"reason": "3–500 characters"})
    found = {i["id"]: i for i in listing(ws, results)}
    if item_id not in found:
        raise WorkspaceError("unknown_item", "no such item awaiting review in this workspace's latest results", 404)
    if found[item_id]["status"] != "pending":
        raise WorkspaceError("already_decided", f"already {found[item_id]['status']} (Proof Chain #{found[item_id]['decision']['ledger_index']})", 409)
    if not (ws.keys / "ledger_mldsa65.key").exists():
        raise WorkspaceError("no_signing_key", "run the pipeline first: it creates this workspace's signing key", 409)
    it = found[item_id]
    payload = {"type": ENTRY_TYPE, "item": item_id, "kind": it["kind"], "title": it["title"], "summary": it["summary"],
               "run_id": it["run_id"], "evidence_sha256": it["evidence_sha256"], "decision": decision, "reason": reason,
               "by": user, "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
    d = ws.runs / "reviews"
    d.mkdir(parents=True, exist_ok=True)
    f = d / f"{int(time.time() * 1000)}-{hashlib.sha256(item_id.encode()).hexdigest()[:12]}.json"
    f.write_text(json.dumps(payload, indent=1))
    led = ["--ledger", str(ws.out / "ledger.jsonl"), "--out-dir", str(ws.out), "--runs", str(ws.runs), "--root", str(ws.root), "--keys-dir", str(ws.keys)]
    for argv in (["append", str(f), "--type", ENTRY_TYPE, *led], ["verify", *led]):
        p = subprocess.run([sys.executable, "-m", "ledger", *argv], capture_output=True, text=True, timeout=120,
                           cwd=Path(__file__).resolve().parent.parent)
        if p.returncode != 0:
            raise WorkspaceError("ledger_failed", f"ledger {argv[0]} failed: {(p.stdout + p.stderr).strip()[-300:]}", 500)
    return payload
