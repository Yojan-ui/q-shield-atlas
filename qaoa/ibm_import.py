"""python -m qaoa --ibm-import DIR: attach the IBM hardware rows of a packaged run (tools/export_ibm_run.py) to
the QAOA section in out/qaoa.json, without IBM access and without submitting anything.

Checks, in order (any failure stops the import and changes nothing):
1. every file in DIR matches DIR/manifest.json (SHA-256);
2. qaoa.qubo.build(DIR/schedule.json, DIR/qaoa_config.json) reproduces the packaged QUBO and exact optimum;
3. the target section's problem is the same problem (assets, values, weights, capacity, dependencies, A, B, exact
   bitstring); otherwise the hardware counts would be scored against a different QUBO;
4. metrics recomputed from each job's raw counts match the metrics saved at run time.
The result is a new QAOA run (new run_id, `derived_from_run_id` = the target run) whose ibm rows carry the
provenance "IBM ibm_fez, imported from <DIR> (run executed <date> on another machine)". Local, SDK and random rows
of the target run are kept; ibm-vs-local comparisons are recomputed against them.
"""

import copy
import hashlib
import json
import math
from pathlib import Path

from contracts.manifest import new_run_id, sha256_json, utc_now

from . import metrics
from .qubo import build

PROBLEM_KEYS = ("week", "assets", "values", "weights", "capacity", "weight_scale", "slack_bits", "n_variables", "A", "B", "dependencies")
REL_TOL = 1e-9


class ImportRefused(SystemExit):
    pass


def _load(d: Path, name: str):
    return json.loads((d / name).read_text(encoding="utf-8"))


def verify_manifest(d: Path) -> dict:
    man = _load(d, "manifest.json")
    on_disk = {p.relative_to(d).as_posix() for p in d.rglob("*") if p.is_file()} - {"manifest.json"}
    if on_disk != set(man["files"]):
        raise ImportRefused(f"{d}: files differ from manifest.json (extra {sorted(on_disk - set(man['files']))}, "
                            f"missing {sorted(set(man['files']) - on_disk)})")
    for name, digest in man["files"].items():
        if hashlib.sha256((d / name).read_bytes()).hexdigest() != digest:
            raise ImportRefused(f"{d}/{name}: SHA-256 does not match manifest.json")
    return man


def same(a, b) -> bool:
    if isinstance(a, (int, float)) and isinstance(b, (int, float)) and not isinstance(a, bool):
        return math.isclose(a, b, rel_tol=REL_TOL, abs_tol=1e-12)
    if isinstance(a, (list, tuple)) and isinstance(b, (list, tuple)):
        return len(a) == len(b) and all(same(x, y) for x, y in zip(a, b))
    if isinstance(a, dict) and isinstance(b, dict):
        return a.keys() == b.keys() and all(same(a[k], b[k]) for k in a)
    return a == b


def provenance(d: Path, run: dict, backend: str) -> str:
    return f"IBM {backend}, imported from {d.as_posix()} (run executed {run['executed_at'][:10]} on another machine)"


def import_ibm(d: Path, section: dict, label_dir: str | None = None) -> dict:
    """Return a new section = `section` + the packaged ibm rows. Raises ImportRefused on any mismatch."""
    man = verify_manifest(d)
    run, prob, angles = _load(d, "run.json"), _load(d, "problem.json"), _load(d, "angles.json")
    saved = _load(d, "metrics.json")
    schedule, cfg = _load(d, "schedule.json"), _load(d, "qaoa_config.json")
    if sha256_json(schedule) != run["schedule_sha256"]:
        raise ImportRefused("packaged schedule.json does not hash to run.json schedule_sha256")
    q = build(schedule, cfg)
    E = q.energies()
    pq = prob["qubo"]
    if not (q.n == pq["n"] and same(float(q.offset), pq["offset"]) and same([float(x) for x in q.linear], pq["linear"])
            and same([[k, l, float(v)] for (k, l), v in sorted(q.quad.items())], pq["quadratic"])):
        raise ImportRefused("the packaged schedule/config do not rebuild the packaged QUBO")
    exact = prob["exact"]
    if not same(float(E.min()), exact["objective"]) or not same(float(E[int(exact["bitstring"], 2)]), exact["objective"]):
        raise ImportRefused("the packaged exact optimum is not the minimum of the rebuilt QUBO")

    target = section["problem"]
    diff = [k for k in PROBLEM_KEYS if not same(target.get(k), prob["problem"].get(k))]
    if diff or section["exact"]["bitstring"] != exact["bitstring"]:
        raise ImportRefused(
            f"out/qaoa.json is a different QAOA problem than the packaged run ({', '.join(diff) or 'exact optimum'} differ), so the "
            f"hardware counts cannot be scored against it. Build the same problem first:\n"
            f"  python -m qaoa --qpiai-local --schedule {(label_dir or d.as_posix())}/schedule.json\n"
            f"then rerun --ibm-import.")

    jobs = sorted((_load(d, f"jobs/{p.name}") for p in (d / "jobs").glob("ibm_p*.json")), key=lambda r: r["p"])
    if not jobs:
        raise ImportRefused(f"{d}/jobs has no ibm_p*.json")
    backend = jobs[0]["backend"]
    prov = provenance(Path(label_dir) if label_dir else d, run, backend)
    new = copy.deepcopy(section)
    new["runs"] = [r for r in new["runs"] if r["source"] != "ibm"]
    new["comparisons"] = [c for c in new["comparisons"] if c.get("against") != "ibm"]
    sigma = cfg["compare_sigma"]
    for rec in jobs:
        if rec.get("status") != "ok" or not rec.get("counts"):
            raise ImportRefused(f"packaged job p={rec['p']} has no finished counts (status {rec.get('status')})")
        m = metrics.compute(q, rec["counts"], E, exact)
        if not same(m, saved["ibm"][str(rec["p"])]):
            bad = [k for k in m if not same(m[k], saved["ibm"][str(rec["p"])].get(k))]
            raise ImportRefused(f"p={rec['p']}: metrics recomputed from the raw counts differ from the saved metrics ({bad})")
        a = angles[str(rec["p"])]
        new["runs"].append({
            "p": rec["p"], "source": "ibm", "backend": backend, "shots": m["shots"],
            "angles": {"gammas": a["gammas"], "betas": a["betas"]}, "energy_scale": a["energy_scale"],
            "job_ids": [rec["job_id"]], "hardware": True, "qpu_seconds": rec["qpu_seconds"],
            "transpiled_depth": rec["transpiled_depth"], "two_qubit_gates": rec["two_qubit_gates"],
            "two_qubit_gate_names": rec["two_qubit_gate_names"], "physical_qubits": rec["physical_qubits"],
            "submitted_at": rec.get("submitted_at"), "provenance": prov,
            "imported": {"from": label_dir or d.as_posix(), "original_run_id": run["run_id"],
                         "executed_at": run["executed_at"], "manifest_sha256": sha256_json(man)},
            "metrics": m})
        local = next((r for r in new["runs"] if r["source"] == "local" and r["p"] == rec["p"]), None)
        if local is not None:
            new["comparisons"].append({"p": rec["p"], "against": "ibm",
                                       **metrics.compare(local["metrics"], m, sigma, f"IBM {backend} (imported)")})
    new["ibm"] = {"requested": True, "imported": True, "backend": backend, "provenance": prov,
                  "original_run_id": run["run_id"], "executed_at": run["executed_at"],
                  "jobs": [{"p": r["p"], "status": "ok", "job_id": r["job_id"], "job_status": r.get("job_status"),
                            "backend": backend, "shots_requested": r.get("shots_requested"), "qpu_seconds": r["qpu_seconds"],
                            "transpiled_depth": r["transpiled_depth"], "two_qubit_gates": r["two_qubit_gates"],
                            "two_qubit_gate_names": r["two_qubit_gate_names"], "physical_qubits": r["physical_qubits"],
                            "optimization_level": r.get("optimization_level"), "error": None} for r in jobs]}
    new["derived_from_run_id"] = section["run_id"]
    new["run_id"] = new_run_id()
    new["ts"] = utc_now()
    return new


def main(d: Path, out_dir: Path, runs: Path) -> dict:
    target = out_dir / "qaoa.json"
    if not target.exists():
        raise ImportRefused(f"{target} not found: run python -m qaoa --qpiai-local --schedule {d.as_posix()}/schedule.json first")
    section = json.loads(target.read_text(encoding="utf-8"))
    try:
        label = d.resolve().relative_to(Path(__file__).resolve().parent.parent).as_posix()
    except ValueError:
        label = d.as_posix()
    new = import_ibm(d, section, label_dir=label)
    run_dir = runs / new["run_id"]
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "manifest.json").write_text(json.dumps(new, indent=1))
    target.write_text(json.dumps(new, indent=1))
    for r in [x for x in new["runs"] if x["source"] == "ibm"]:
        print(f"imported IBM p={r['p']} job {r['job_ids'][0]}: feasible {r['metrics']['feasible_fraction']:.4f}, "
              f"P(opt set) {r['metrics']['p_optimal_assets']:.4f} (metrics recomputed from raw counts, match saved)")
    print(f"QAOA run {new['run_id']} (derived from {new['derived_from_run_id']}): {new['ibm']['provenance']}")
    print("next: python -m ledger ingest && python -m ledger verify && python -m contracts.assemble && python -m atlas report")
    return new
