"""data/real_ibm_qaoa/: committed values of the IBM ibm_fez run match their manifest and their own raw counts."""

import csv
import hashlib
import json
from pathlib import Path

import pytest

D = Path(__file__).resolve().parents[1] / "data" / "real_ibm_qaoa"
RUNS = sorted(D.glob("run_*.json")) if D.exists() else []
RUNS = [p for p in RUNS if not p.name.endswith(".manifest.json")]
pytestmark = pytest.mark.skipif(not RUNS, reason="no exported IBM run")


@pytest.mark.parametrize("path", RUNS, ids=lambda p: p.stem)
def test_outputs_match_manifest(path):
    man = json.loads(path.with_name(path.stem + ".manifest.json").read_text(encoding="utf-8"))
    for name, digest in man["outputs"].items():
        assert hashlib.sha256((D.parents[1] / name).read_bytes()).hexdigest() == digest, name


@pytest.mark.parametrize("path", RUNS, ids=lambda p: p.stem)
def test_ibm_rows_carry_job_ids_and_reproduce_from_counts(path):
    doc = json.loads(path.read_text(encoding="utf-8"))
    assert "no quantum advantage claimed" in doc["label"]
    rows = [r for r in doc["table"] if r["source"] == "ibm" and r["status"] == "ok"]
    assert rows
    best = doc["exact"]["bitstring"]
    for r in rows:
        hw, counts = r["hardware"], doc["ibm"]["counts"][str(r["p"])]
        assert hw["backend"] == r["backend"] and r["job_ids"] == [hw["job_id"]] and hw["job_id"]
        assert hw["transpiled_depth"] > 0 and hw["two_qubit_gates"] > 0
        assert sum(counts.values()) == r["shots"]
        assert r["metrics"]["p_optimal"] == pytest.approx(counts.get(best, 0) / r["shots"])
    with path.with_name(path.stem + "_table.csv").open(encoding="utf-8") as fh:
        csv_ibm = [x for x in csv.DictReader(fh) if x["source"] == "ibm" and x["status"] == "ok"]
    assert [x["hw_job_id"] for x in csv_ibm] == [r["hardware"]["job_id"] for r in rows]
