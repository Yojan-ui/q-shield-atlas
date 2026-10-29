"""data/real_ibm_qaoa/: the packaged IBM ibm_fez run matches its manifest and its own raw counts."""

import csv
import hashlib
import json
from pathlib import Path

import pytest

D = Path(__file__).resolve().parents[1] / "data" / "real_ibm_qaoa"
pytestmark = pytest.mark.skipif(not (D / "manifest.json").exists(), reason="no packaged IBM run")


def load(name):
    return json.loads((D / name).read_text(encoding="utf-8"))


def test_every_file_matches_the_manifest_and_nothing_is_unlisted():
    files = load("manifest.json")["files"]
    assert {p.relative_to(D).as_posix() for p in D.rglob("*") if p.is_file()} - {"manifest.json"} == set(files)
    for name, digest in files.items():
        assert hashlib.sha256((D / name).read_bytes()).hexdigest() == digest, name


def test_jobs_carry_ids_stats_and_reproduce_p_optimal_from_counts():
    run, saved, best = load("run.json"), load("metrics.json")["ibm"], load("problem.json")["exact"]["bitstring"]
    assert "no quantum advantage claimed" in run["label"]
    jobs = [load(f"jobs/ibm_p{p}.json") for p in (1, 2, 3)]
    assert [j["job_id"] for j in jobs] == run["job_ids"]
    for j in jobs:
        assert j["backend"] == "ibm_fez" and j["status"] == "ok" and j["job_status"] == "DONE"
        assert j["transpiled_depth"] > 0 and j["two_qubit_gates"] > 0 and len(j["physical_qubits"]) == load("problem.json")["qubo"]["n"]
        assert sum(j["counts"].values()) == j["shots_requested"] and j["submitted_at"]
        assert saved[str(j["p"])]["p_optimal"] == pytest.approx(j["counts"].get(best, 0) / j["shots_requested"])
    with (D / "table.csv").open(encoding="utf-8") as fh:
        rows = [x for x in csv.DictReader(fh) if x["source"] == "ibm" and x["status"] == "ok"]
    assert [x["hw_job_id"] for x in rows] == run["job_ids"]
