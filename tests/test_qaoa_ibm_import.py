"""python -m qaoa --ibm-import data/real_ibm_qaoa: re-creates the ibm_fez rows from the packaged run, offline."""

import copy
import hashlib
import json
import shutil
import sys
from pathlib import Path

import pytest

from qaoa import ibm_import
from qaoa.__main__ import main as qaoa_main, run
from qaoa.table import build_table
from tests.test_qaoa_table import qaoa_validator

PKG = Path(__file__).resolve().parents[1] / "data" / "real_ibm_qaoa"
pytestmark = pytest.mark.skipif(not (PKG / "manifest.json").exists(), reason="no packaged IBM run")


@pytest.fixture()
def pkg(tmp_path):
    d = tmp_path / "real_ibm_qaoa"
    shutil.copytree(PKG, d)
    return d


def original():
    return json.loads((PKG / "qaoa_section.json").read_text(encoding="utf-8"))


def without_ibm(section):
    s = copy.deepcopy(section)
    s["runs"] = [r for r in s["runs"] if r["source"] != "ibm"]
    s["comparisons"] = [c for c in s["comparisons"] if c.get("against") != "ibm"]
    s["ibm"] = {"requested": False}
    return s


def remanifest(d: Path):
    man = json.loads((d / "manifest.json").read_text(encoding="utf-8"))
    man["files"] = {k: hashlib.sha256((d / k).read_bytes()).hexdigest() for k in man["files"]}
    (d / "manifest.json").write_text(json.dumps(man))


@pytest.fixture()
def no_ibm_sdk(monkeypatch):
    for mod in ("qiskit", "qiskit_ibm_runtime", "truststore"):
        monkeypatch.setitem(sys.modules, mod, None)  # any import of these raises ImportError


def test_import_recreates_the_ibm_rows_from_raw_counts(pkg, no_ibm_sdk):
    src = original()
    new = ibm_import.import_ibm(pkg, without_ibm(src), label_dir="data/real_ibm_qaoa")
    got = {r["p"]: r for r in new["runs"] if r["source"] == "ibm"}
    want = {r["p"]: r for r in src["runs"] if r["source"] == "ibm"}
    assert got.keys() == want.keys() == {1, 2, 3}
    for p in got:
        assert got[p]["metrics"] == pytest.approx(want[p]["metrics"])
        assert got[p]["job_ids"] == want[p]["job_ids"] and got[p]["transpiled_depth"] == want[p]["transpiled_depth"]
    prov = got[1]["provenance"]
    assert prov.startswith("IBM ibm_fez, imported from data/real_ibm_qaoa (run executed 2026-10-29 on another machine)")
    assert new["derived_from_run_id"] == src["run_id"] and new["run_id"] != src["run_id"] and new["ibm"]["imported"]
    assert {c["p"] for c in new["comparisons"] if c["against"] == "ibm"} == {1, 2, 3}
    table = build_table(new)
    ibm = [r for r in table if r["source"] == "ibm"]
    assert [r["status"] for r in ibm] == ["ok"] * 3 and all(r["hardware"]["provenance"] == prov for r in ibm)
    qaoa_validator().validate({**new, "table": table, "ledger_index": None})


def test_tampered_file_is_refused(pkg):
    f = pkg / "jobs" / "ibm_p2.json"
    f.write_text(f.read_text(encoding="utf-8").replace('"qpu_seconds": 3', '"qpu_seconds": 1'), encoding="utf-8")
    with pytest.raises(ibm_import.ImportRefused, match="SHA-256"):
        ibm_import.import_ibm(pkg, without_ibm(original()))


def test_counts_that_do_not_reproduce_the_saved_metrics_are_refused(pkg):
    f = pkg / "jobs" / "ibm_p1.json"
    rec = json.loads(f.read_text(encoding="utf-8"))
    best = json.loads((pkg / "problem.json").read_text(encoding="utf-8"))["exact"]["bitstring"]
    rec["counts"][best] = rec["counts"].get(best, 0) + 50  # forged hits on the optimum
    other = max(rec["counts"], key=rec["counts"].get) if max(rec["counts"], key=rec["counts"].get) != best else sorted(rec["counts"])[0]
    rec["counts"][other] -= 50
    f.write_text(json.dumps(rec), encoding="utf-8")
    remanifest(pkg)  # even with a consistent manifest
    with pytest.raises(ibm_import.ImportRefused, match="differ from the saved metrics"):
        ibm_import.import_ibm(pkg, without_ibm(original()))


def test_a_different_problem_is_refused(pkg):
    s = without_ibm(original())
    s["problem"]["values"][0] *= 1.5
    with pytest.raises(ibm_import.ImportRefused, match="different QAOA problem"):
        ibm_import.import_ibm(pkg, s)


def test_cli_on_a_fresh_local_run_of_the_packaged_schedule(pkg, tmp_path, no_ibm_sdk):
    """The Mac flow: local QAOA on the packaged schedule.json, then --ibm-import; nothing contacts IBM."""
    cfg = json.loads((pkg / "qaoa_config.json").read_text(encoding="utf-8"))
    cfg = {**cfg, "restarts": 1, "cobyla_maxiter": 30, "shots": 256}
    out, runs = tmp_path / "out", tmp_path / "runs"
    out.mkdir()
    local = run(json.loads((pkg / "schedule.json").read_text(encoding="utf-8")), cfg, runs)
    (out / "qaoa.json").write_text(json.dumps(local))
    assert qaoa_main(["--ibm-import", str(pkg), "--out-dir", str(out), "--runs", str(runs)]) == 0
    new = json.loads((out / "qaoa.json").read_text(encoding="utf-8"))
    assert new["derived_from_run_id"] == local["run_id"]
    assert (runs / new["run_id"] / "manifest.json").exists()
    ibm = [r for r in build_table(new) if r["source"] == "ibm"]
    assert len(ibm) == 3 and all(r["status"] == "ok" and r["hardware"]["backend"] == "ibm_fez" for r in ibm)
