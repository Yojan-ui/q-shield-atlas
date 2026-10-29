"""tools/export_ibm_run.py: package a logged IBM Quantum QAOA run as REAL data in data/real_ibm_qaoa/.

out/ and runs/ are git-ignored, so everything needed to reproduce the IBM rows without IBM access is copied
here from the logged run (nothing typed by hand) and can travel to another machine through git:

    run.json                 run_id, executed_at, schedule hash, ledger entry, label, file list
    schedule.json            the out/schedule.json the QUBO was built from (byte copy)
    qaoa_config.json         config/qaoa.json used for the run (byte copy)
    problem.json             candidates, QUBO (offset, linear, quadratic terms), exact optimum
    angles.json              simulator-tuned angles per p (the circuits sent to IBM)
    jobs/ibm_p<p>.json       per job: job ID, backend, shots, raw counts, transpile stats (depth, 2q gates,
                             op counts, physical-qubit layout), QPU seconds, logged submit/result timestamps
    metrics.json             metrics computed at run time (ibm, local, random) and the comparisons
    qaoa_section.json        the full out/qaoa.json section of that run
    table.csv                qaoa.table rows, flat
    versions.json            Python and package versions
    manifest.json            SHA-256 of every file above

Imported elsewhere with `python -m qaoa --ibm-import data/real_ibm_qaoa`. No credentials are read or written.

    python tools/export_ibm_run.py [--results out/results.json] [--runs runs] [--out-dir data/real_ibm_qaoa]
"""

import argparse
import csv
import hashlib
import importlib.metadata as md
import json
import platform
import shutil
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from contracts.manifest import sha256_json  # noqa: E402
from qaoa.qubo import build  # noqa: E402

OUT_DIR = REPO / "data" / "real_ibm_qaoa"
METRICS = ("feasible_fraction", "best_feasible_objective", "approximation_ratio", "energy_ratio", "p_optimal", "p_optimal_assets")
HW = ("job_id", "backend", "transpiled_depth", "two_qubit_gates", "qpu_seconds")
PACKAGES = ("numpy", "scipy", "qiskit", "qiskit-ibm-runtime", "qpiai-quantum", "qpiai-opt", "truststore")
LABEL = ("REAL. IBM Quantum hardware run of the QAOA wave-selection cross-check. A measured cross-check against the "
         "exact optimum; no quantum advantage claimed.")


def sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def dump(path: Path, obj) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=1, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")


def version(name: str):
    try:
        return md.version(name)
    except md.PackageNotFoundError:
        return None


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--results", type=Path, default=REPO / "out" / "results.json")
    ap.add_argument("--schedule", type=Path, default=REPO / "out" / "schedule.json")
    ap.add_argument("--config", type=Path, default=REPO / "config" / "qaoa.json")
    ap.add_argument("--runs", type=Path, default=REPO / "runs")
    ap.add_argument("--ledger", type=Path, default=REPO / "out" / "ledger.jsonl")
    ap.add_argument("--out-dir", type=Path, default=OUT_DIR)
    args = ap.parse_args(argv)

    res = json.loads(args.results.read_text(encoding="utf-8"))
    q = res.get("qaoa") or {}
    ibm_runs = [r for r in q.get("runs", []) if r["source"] == "ibm"]
    if not ibm_runs:
        sys.exit("no finished IBM runs in results.json qaoa.runs (run python -m qaoa --ibm, then --ibm-fetch)")
    schedule = json.loads(args.schedule.read_text(encoding="utf-8"))
    if sha256_json(schedule) != q["schedule_sha256"]:
        sys.exit("out/schedule.json is not the schedule this QAOA run was built from; refusing to package it")
    cfg = json.loads(args.config.read_text(encoding="utf-8"))
    qubo = build(schedule, cfg)
    if qubo.assets != q["problem"]["assets"] or qubo.n != q["problem"]["n_variables"]:
        sys.exit("config/qaoa.json no longer rebuilds this run's QUBO; refusing to package it")
    run_dir = args.runs / q["run_id"]

    out = args.out_dir
    if out.exists():
        shutil.rmtree(out)  # the package is regenerated as a whole; stale files must not survive
    (out / "jobs").mkdir(parents=True)

    shutil.copyfile(args.schedule, out / "schedule.json")
    shutil.copyfile(args.config, out / "qaoa_config.json")

    log = args.runs / "platform_jobs.log"
    events = [json.loads(x) for x in log.read_text(encoding="utf-8").splitlines() if x.strip()] if log.exists() else []
    events = [e for e in events if e.get("run_id") == q["run_id"]]
    for r in ibm_runs:
        rec = json.loads((run_dir / f"ibm_p{r['p']}.json").read_text(encoding="utf-8"))
        stage = f"qaoa.ibm.p{r['p']}"
        rec["submitted_at"] = next((e["ts"] for e in events if e.get("stage") == stage and e["event"] == "submit"), None)
        rec["job_id_logged_at"] = next((e["ts"] for e in events if e.get("stage") == stage and e["event"] == "result"), None)
        rec["timestamps_note"] = "from runs/platform_jobs.log on the executing machine (UTC)"
        dump(out / "jobs" / f"ibm_p{r['p']}.json", rec)

    dump(out / "problem.json", {
        "problem": q["problem"], "exact": q["exact"],
        "qubo": {"n": qubo.n, "offset": float(qubo.offset), "linear": [float(x) for x in qubo.linear],
                 "quadratic": [[k, l, float(v)] for (k, l), v in sorted(qubo.quad.items())]},
        "rebuild": "qaoa.qubo.build(schedule.json, qaoa_config.json) reproduces this QUBO (checked by the importer)",
    })
    dump(out / "angles.json", {str(r["p"]): {"gammas": r["angles"]["gammas"], "betas": r["angles"]["betas"],
                                             "energy_scale": r["energy_scale"], "optimizer": r.get("optimizer")}
                               for r in q["runs"] if r["source"] == "local"})
    dump(out / "metrics.json", {
        "ibm": {str(r["p"]): r["metrics"] for r in ibm_runs},
        "local": {str(r["p"]): r["metrics"] for r in q["runs"] if r["source"] == "local"},
        "qpiai_local": {str(r["p"]): r["metrics"] for r in q["runs"] if r["source"] == "qpiai_local"},
        "random": next((r["metrics"] for r in q["runs"] if r["source"] == "random"), None),
        "comparisons": q["comparisons"],
    })
    section = {k: v for k, v in q.items() if k not in ("table", "ledger_index")}
    dump(out / "qaoa_section.json", section)
    with (out / "table.csv").open("w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh, lineterminator="\n")
        w.writerow(["run_id", "p", "source", "status", "backend", "shots", *METRICS, *[f"hw_{k}" for k in HW], "status_text"])
        for r in q["table"]:
            m, hw = r.get("metrics") or {}, r.get("hardware") or {}
            w.writerow([q["run_id"], "" if r["p"] is None else r["p"], r["source"], r["status"], r["backend"],
                        "" if r["shots"] is None else r["shots"], *[m.get(k, "") for k in METRICS],
                        *[hw.get(k, "") for k in HW], r.get("status_text") or ""])
    dump(out / "versions.json", {"python": platform.python_version(), "platform": f"{platform.system()} {platform.release()}",
                                 "packages": {p: version(p) for p in PACKAGES},
                                 "note": "environment of the machine that ran the IBM jobs, recorded at export"})

    entry = None
    if args.ledger.exists():
        for line in args.ledger.read_text(encoding="utf-8").splitlines():
            e = json.loads(line)
            if e.get("type") == "qaoa.run" and q["run_id"] in json.dumps(e):
                entry = {"index": e["index"], "payload_hash": e["payload_hash"], "ts": e["ts"]}
    dump(out / "run.json", {
        "label": LABEL, "run_id": q["run_id"], "executed_at": q["ts"], "schedule_sha256": q["schedule_sha256"],
        "backend": ibm_runs[0]["backend"], "job_ids": [r["job_ids"][0] for r in ibm_runs],
        "ledger_on_executing_machine": {"qaoa_run_entry": entry, "root": (res.get("ledger") or {}).get("root"),
                                        "alg": (res.get("ledger") or {}).get("alg")},
        "import": "python -m qaoa --ibm-import data/real_ibm_qaoa",
    })
    files = sorted(p for p in out.rglob("*") if p.is_file())
    dump(out / "manifest.json", {"run_id": q["run_id"], "algorithm": "sha256",
                                 "files": {p.relative_to(out).as_posix(): sha(p) for p in files}})
    print(f"wrote {out.relative_to(REPO).as_posix()}/ ({len(files) + 1} files, {len(ibm_runs)} IBM jobs, ledger entry "
          f"{entry['index'] if entry else 'not found'})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
