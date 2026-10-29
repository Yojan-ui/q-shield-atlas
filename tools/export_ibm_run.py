"""tools/export_ibm_run.py: publish a logged IBM Quantum QAOA run as REAL data under data/real_ibm_qaoa/.

out/ and runs/ are git-ignored, so the values of an `python -m qaoa --ibm` run are exported here from
those logged files only (nothing typed by hand):
    run_<id8>.json           the run: problem, exact optimum, every qaoa.table row (local, QpiAI SDK local,
                             ibm, random), hardware blocks, comparisons, raw ibm_fez counts per p,
                             ledger entry index + root
    run_<id8>_table.csv      the same table rows, flat
    run_<id8>.manifest.json  SHA-256 of every source file and of the two outputs

    python tools/export_ibm_run.py [--results out/results.json] [--runs runs] [--ledger out/ledger.jsonl]

No credentials are read or written. Refuses runs without finished IBM rows.
"""

import argparse
import csv
import hashlib
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
OUT_DIR = REPO / "data" / "real_ibm_qaoa"
METRICS = ("feasible_fraction", "best_feasible_objective", "approximation_ratio", "energy_ratio", "p_optimal", "p_optimal_assets")
HW = ("job_id", "backend", "transpiled_depth", "two_qubit_gates", "qpu_seconds")


def sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def rel(p: Path) -> str:
    try:
        return p.resolve().relative_to(REPO).as_posix()
    except ValueError:
        return p.as_posix()


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--results", type=Path, default=REPO / "out" / "results.json")
    ap.add_argument("--runs", type=Path, default=REPO / "runs")
    ap.add_argument("--ledger", type=Path, default=REPO / "out" / "ledger.jsonl")
    ap.add_argument("--out-dir", type=Path, default=OUT_DIR)
    args = ap.parse_args(argv)

    res = json.loads(args.results.read_text(encoding="utf-8"))
    q = res.get("qaoa") or {}
    ibm_ok = [r for r in q.get("table", []) if r["source"] == "ibm" and r["status"] == "ok"]
    if not ibm_ok:
        sys.exit("no finished IBM rows in results.json qaoa.table (run python -m qaoa --ibm, then --ibm-fetch)")
    run_dir = args.runs / q["run_id"]
    sources = [args.results, run_dir / "manifest.json", *[run_dir / f"ibm_p{r['p']}.json" for r in ibm_ok]]
    records = {r["p"]: json.loads((run_dir / f"ibm_p{r['p']}.json").read_text(encoding="utf-8")) for r in ibm_ok}

    entry = None
    if args.ledger.exists():
        for line in args.ledger.read_text(encoding="utf-8").splitlines():
            e = json.loads(line)
            if e.get("type") == "qaoa.run" and q["run_id"] in json.dumps(e):
                entry = {"index": e["index"], "type": e["type"], "payload_hash": e["payload_hash"], "ts": e["ts"]}
        sources.append(args.ledger)

    doc = {
        "label": "REAL. IBM Quantum hardware run of the QAOA wave-selection cross-check. A measured cross-check "
                 "against the exact optimum; no quantum advantage claimed.",
        "exported_from": [rel(s) for s in sources],
        "run_id": q["run_id"], "ts": q["ts"], "results_generated_at": res.get("generated_at"),
        "problem": q["problem"], "exact": q["exact"], "qaoa_label": q["label"],
        "table": q["table"], "comparisons": q["comparisons"],
        "ibm": {"backend": q["ibm"].get("backend"), "jobs": q["ibm"].get("jobs"),
                "counts": {str(p): rec["counts"] for p, rec in sorted(records.items())},
                "physical_qubits": {str(p): rec["physical_qubits"] for p, rec in sorted(records.items())},
                "two_qubit_gate_names": {str(p): rec["two_qubit_gate_names"] for p, rec in sorted(records.items())},
                "optimization_level": records[min(records)]["optimization_level"],
                "seed_transpiler": records[min(records)]["seed_transpiler"]},
        "ledger": {"qaoa_run_entry": entry, "root": (res.get("ledger") or {}).get("root"),
                   "alg": (res.get("ledger") or {}).get("alg"), "pubkey_fp": (res.get("ledger") or {}).get("pubkey_fp")},
    }
    args.out_dir.mkdir(parents=True, exist_ok=True)
    stem = f"run_{q['run_id'][:8]}"
    jpath, cpath = args.out_dir / f"{stem}.json", args.out_dir / f"{stem}_table.csv"
    jpath.write_text(json.dumps(doc, indent=1, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
    with cpath.open("w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh, lineterminator="\n")
        w.writerow(["run_id", "p", "source", "status", "backend", "shots", *METRICS, *[f"hw_{k}" for k in HW], "status_text"])
        for r in q["table"]:
            m, hw = r.get("metrics") or {}, r.get("hardware") or {}
            w.writerow([q["run_id"], "" if r["p"] is None else r["p"], r["source"], r["status"], r["backend"],
                        "" if r["shots"] is None else r["shots"], *[m.get(k, "") for k in METRICS],
                        *[hw.get(k, "") for k in HW], r.get("status_text") or ""])
    manifest = {"run_id": q["run_id"], "sources": {rel(s): sha(s) for s in sources},
                "outputs": {rel(jpath): sha(jpath), rel(cpath): sha(cpath)}}
    (args.out_dir / f"{stem}.manifest.json").write_text(json.dumps(manifest, indent=1) + "\n", encoding="utf-8", newline="\n")
    print(f"wrote {rel(jpath)}, {rel(cpath)}, {stem}.manifest.json ({len(ibm_ok)} IBM rows, ledger entry "
          f"{entry['index'] if entry else 'not found'})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
