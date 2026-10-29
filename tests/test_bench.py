"""python -m bench: same instances, every solver, numbers only from runs; non-runs carry a reason, never a number."""

import json
from pathlib import Path

import jsonschema
import pytest

from bench.__main__ import HARDWARE_REASON, run
from contracts import validate

REPO = Path(__file__).resolve().parent.parent
SAMPLE = json.loads((REPO / "tests" / "fixtures" / "results_sample.json").read_text())
CFG = {**json.loads((REPO / "config" / "qaoa.json").read_text()), "restarts": 1, "shots": 256, "reps": [1]}


@pytest.fixture(scope="module")
def section(tmp_path_factory):
    import bench.__main__ as b

    saved, b.SIZES = b.SIZES, (2, 4)  # small instances keep the test fast
    try:
        yield run(SAMPLE, CFG, tmp_path_factory.mktemp("runs"), with_milp=False)
    finally:
        b.SIZES = saved


def test_rows_cover_every_solver_per_instance(section):
    for inst in section["instances"]:
        got = {(r["solver"], r["p"]) for r in section["rows"] if r["instance"] == inst["id"]}
        assert got == {("exact", None), ("milp", None), ("random", None), ("qaoa", 1), ("hybrid", 1), ("hardware", None)}


def test_quality_is_relative_to_the_exact_optimum(section):
    for r in section["rows"]:
        if r["status"] == "ok" and r["feasible"]:
            assert r["objective"] >= r["optimum"] - 1e-9 and 0 <= r["approximation_ratio"] <= 1 + 1e-9
    assert all(r["approximation_ratio"] == pytest.approx(1) for r in section["rows"] if r["solver"] == "exact")


def test_not_run_rows_have_a_reason_and_no_numbers(section):
    hw = [r for r in section["rows"] if r["solver"] == "hardware"]
    assert hw and all(r["status"] == "not_run" and r["status_text"] == HARDWARE_REASON and r["objective"] is None for r in hw)
    milp = [r for r in section["rows"] if r["solver"] == "milp"]
    assert all(r["status"] == "not_requested" and r["runtime_s"] is None for r in milp)
    bad = json.loads(json.dumps(section))
    bad["rows"][-1]["objective"] = 1.0  # a number on a not-run row breaks the contract
    with pytest.raises(jsonschema.ValidationError):
        validate("bench", bad)


def test_honest_label_and_limits(section):
    assert "No quantum advantage claimed" in section["label"] and section["limits"]
    assert "unsupported" in section["full_schedule"]["qaoa"]


def test_ledger_ingest_signs_the_bench_manifest(tmp_path, section):
    from ledger.ingest import run_manifests

    out, runs = tmp_path / "out", tmp_path / "runs"
    out.mkdir()
    (runs / section["run_id"]).mkdir(parents=True)
    (runs / section["run_id"] / "manifest.json").write_text(json.dumps(section))
    (out / "bench.json").write_text(json.dumps(section))
    assert ("bench.run", runs / section["run_id"] / "manifest.json") in run_manifests(out, runs)


def test_api_roles_and_read_only(monkeypatch, tmp_path):
    from .atlas_web_helpers import PASSWORD, Client, start_server

    srv = start_server(monkeypatch, tmp_path)
    try:
        for name, role in (("ops", "operator"), ("vic", "viewer")):
            srv.app.store.create_user(name, PASSWORD, role)
        ops, vic = Client(srv.server_address[1]), Client(srv.server_address[1])
        assert ops.login("ops")[0] == 200 and vic.login("vic")[0] == 200
        assert ops.post("/api/workspaces", {"id": "b1", "name": "b1", "template": "mock_bank"})[0] == 201
        status, body = vic.get("/api/workspaces/b1/bench")
        assert status == 200 and body["bench"] is None and body["status_text"] == "not yet run"
        assert vic.post("/api/workspaces/b1/bench", {})[0] == 403
        status, body = ops.post("/api/workspaces/b1/bench", {})
        assert status == 409 and body["error"]["code"] == "not_run"  # no schedule yet
        assert ops.post("/api/workspaces/demo/bench", {})[0] == 403  # read-only snapshot
    finally:
        srv.shutdown()
