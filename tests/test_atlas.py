"""python -m atlas announce: computed module status, provenance, 'not yet run' for missing data."""

import copy
import json
import subprocess
import sys
from pathlib import Path

from atlas.announce import FOOTER, NOT_YET_RUN, collect, junit_counts, module_status

REPO = Path(__file__).resolve().parent.parent
SAMPLE = json.loads((REPO / "tests" / "fixtures" / "results_sample.json").read_text())


def junit(tmp_path, cases):
    body = "".join(
        f'<testcase classname="tests.{mod}" name="t{i}">{"<failure/>" if outcome == "fail" else "<skipped/>" if outcome == "skip" else ""}</testcase>'
        for i, (mod, outcome) in enumerate(cases))
    p = tmp_path / "junit.xml"
    p.write_text(f'<testsuites><testsuite name="pytest">{body}</testsuite></testsuites>')
    return junit_counts(p)


def test_module_status_is_computed(tmp_path):
    counts = junit(tmp_path, [("test_detect", "pass"), ("test_ledger", "fail"), ("test_merkle", "pass"), ("test_qaoa", "skip")])
    rows = {r["module"]: r for r in module_status(SAMPLE, counts)}
    assert rows["detect"]["mark"] == "✔"
    assert rows["ledger"]["mark"] == "✖" and rows["ledger"]["failed"] == 1
    assert rows["schedule"]["mark"] == "…" and "tests not run" in rows["schedule"]["status"]
    assert rows["qaoa"]["skipped"] == 1


def test_missing_results_print_not_yet_run(tmp_path):
    counts = junit(tmp_path, [("test_detect", "pass")])
    data = collect(None, counts)
    for key in ("avoided", "handshake", "qaoa", "ledger"):
        assert data[key] == NOT_YET_RUN
    assert data["assets"]["found"] == NOT_YET_RUN
    assert data["crypto"]["openssl"] == NOT_YET_RUN
    assert next(r for r in data["modules"] if r["module"] == "detect")["status"].endswith(NOT_YET_RUN)
    assert data["footer"] == FOOTER and "no quantum advantage claimed" in FOOTER


def test_numbers_come_from_results_with_provenance(tmp_path):
    data = collect(SAMPLE, {})
    assert data["assets"]["found"] == len(SAMPLE["assets"])
    assert data["solver"]["run_ids"] == SAMPLE["exposure"]["produced_by"]["run_ids"]
    assert data["avoided"]["vs_fcfs"][0]["exposure_years_avoided"] == SAMPLE["avoided"]["vs_fcfs"][0]["exposure_years_avoided"]
    assert {h["service"] for h in data["handshake"]} == {"legacy", "hybrid", "pq-auth"}
    cloud = [r for r in data["qaoa"]["rows"] if r["source"] == "qcloud"]
    assert all(isinstance(r["values"], str) for r in cloud)  # status_text, not numbers
    assert data["crypto"]["kem_group"] == ["X25519MLKEM768"] and data["crypto"]["pq_auth"] == ["ML-DSA"]


def test_ledger_verified_state(tmp_path):
    stale = copy.deepcopy(SAMPLE)
    stale["ledger_verification"] = None
    assert collect(stale, {})["ledger"]["verified"] == "not verified since last ingest"


def test_ledger_file_check_detects_mismatch(tmp_path):
    r = copy.deepcopy(SAMPLE)
    r["ledger"]["ledger_ref"] = "nope/ledger.jsonl"
    assert "missing" in collect(r, {}, repo=tmp_path)["ledger"]["file_check"]["text"]


def test_cli_json_fast_runs_without_results(tmp_path):
    out = subprocess.run([sys.executable, "-m", "atlas", "announce", "--fast", "--json", "--results", str(tmp_path / "none.json")],
                         cwd=REPO, capture_output=True, text=True, timeout=60, check=True)
    data = json.loads(out.stdout)
    assert data["qaoa"] == NOT_YET_RUN and "Post-Quantum Cryptography · PQC-01" in data["track"]


def test_cli_screen_renders_sample(tmp_path):
    p = tmp_path / "results.json"
    p.write_text(json.dumps(SAMPLE))
    out = subprocess.run([sys.executable, "-m", "atlas", "announce", "--fast", "--results", str(p)],
                         cwd=REPO, capture_output=True, text=True, timeout=60, check=True, env={"COLUMNS": "160", "PATH": "/usr/bin:/bin"})
    for text in ("PQC-01", "Modules", "X25519MLKEM768", "no quantum advantage claimed", "QAOA cross-check"):
        assert text in out.stdout, text
