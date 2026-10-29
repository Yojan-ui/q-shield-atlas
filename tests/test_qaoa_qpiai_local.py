"""--qpiai-local: the final QAOA circuits sampled on the QpiAI SDK's in-process simulator (free, no network).

QAOA on simulators. A measured cross-check against the exact optimum. No quantum advantage claimed.
"""

import json
import socket
from pathlib import Path

import numpy as np
import pytest

from contracts import validate
from qaoa import local_sim, qpiai_local
from qaoa.__main__ import build, run
from qaoa.circuit import build_circuit
from qaoa.table import build_table

REPO = Path(__file__).resolve().parent.parent
SAMPLE = json.loads((REPO / "tests" / "fixtures" / "results_sample.json").read_text())
CFG = json.loads((REPO / "config" / "qaoa.json").read_text())


@pytest.fixture
def no_network(monkeypatch):
    def refuse(*a, **k):
        raise AssertionError("network access attempted")

    monkeypatch.setattr(socket.socket, "connect", refuse)
    monkeypatch.setattr(socket, "create_connection", refuse)
    monkeypatch.delenv("QCLOUD_API_KEY", raising=False)
    monkeypatch.delenv("QPIAI_OPT_API_KEY", raising=False)


def angles(p):
    r = next(x for x in SAMPLE["qaoa"]["runs"] if x["source"] == "local" and x["p"] == p)
    return {"p": p, **r["angles"], "energy_scale": r["energy_scale"]}


def test_sdk_statevector_equals_numpy_exactly(no_network):
    """Same circuit, same angles: the SDK's exact output distribution equals our numpy QAOA state."""
    from qpiai_quantum.simulator import StatevectorSimulator

    q = build(SAMPLE, CFG)
    E = q.energies()
    for p in (1, 2, 3):
        a = angles(p)
        psi = local_sim.statevector(E / a["energy_scale"], a["gammas"], a["betas"])
        res = StatevectorSimulator().run(build_circuit(q, a["gammas"], a["betas"], a["energy_scale"], measure=False), shots=16, seed=1)
        sv = np.asarray(res.statevector, dtype=complex)
        assert np.allclose(np.abs(sv) ** 2, np.abs(psi) ** 2, atol=1e-9), p  # qubit k = bit k of the basis index


def test_records_offline_with_provenance(no_network, tmp_path):
    q = build(SAMPLE, CFG)
    recs = qpiai_local.run(q, [angles(1)], CFG, "a" * 32, tmp_path)
    r = recs[0]
    assert r["status"] == "ok" and r["job_id"] is None and r["job_id_reason"] == "local SDK simulation issues no job ID"
    assert r["backend"] == "qpiai-quantum local simulator (QpiAI-QSV-Local)" and r["sdk_version"] == "0.3.0"
    assert sum(r["counts"].values()) == CFG["shots"] and len(r["inputs_sha256"]) == 64 and len(r["outputs_sha256"]) == 64
    saved = json.loads((tmp_path / "qpiai_local_p1.json").read_text())
    assert saved["inputs"]["device"] == "QpiAI-QSV-Local" and saved["outputs_sha256"] == r["outputs_sha256"]
    again = qpiai_local.run(q, [angles(1)], CFG, "b" * 32, tmp_path)[0]
    assert again["outputs_sha256"] == r["outputs_sha256"]  # seeded: reproducible


def test_full_run_rows_validate_and_agree_with_numpy(no_network, tmp_path):
    section = run(SAMPLE, CFG, tmp_path, qcloud=False, budget=None, sdk_local=True)
    rows = build_table(section)
    sdk_rows = [r for r in rows if r["source"] == "qpiai_local"]
    assert [r["p"] for r in sdk_rows] == [1, 2, 3]
    assert all(r["status"] == "ok" and r["job_ids"] == [] and r["job_id"] is None and r["job_id_reason"] for r in sdk_rows)
    qcloud = [r for r in rows if r["source"] == "qcloud"]
    assert all(r["status"] == "not_requested" and r["metrics"] is None and r["status_text"] for r in qcloud)
    results = {**SAMPLE, "qaoa": {**section, "table": rows, "ledger_index": None}}
    validate("results", results)
    # statistical tolerance: two independent 2048-shot samples of the same distribution agree within compare_sigma
    cmps = [c for c in section["comparisons"] if c["against"] == "qpiai_local"]
    assert len(cmps) == 3
    for c in cmps:
        assert not c["differs"], c
        assert all(abs(z) <= CFG["compare_sigma"] for z in c["z_scores"].values()), c
    for r in sdk_rows:
        assert r["comparison"]["z_scores"] == next(c for c in cmps if c["p"] == r["p"])["z_scores"]


def test_schema_rejects_a_job_id_or_missing_reason_on_sdk_rows(no_network, tmp_path):
    section = run(SAMPLE, CFG, tmp_path, sdk_local=True)
    rows = build_table(section)
    bad = [dict(r) for r in rows]
    i = next(k for k, r in enumerate(bad) if r["source"] == "qpiai_local")
    bad[i]["job_ids"] = ["fake-job"]
    with pytest.raises(Exception):
        validate("results", {**SAMPLE, "qaoa": {**section, "table": bad, "ledger_index": None}})
    bad[i] = {k: v for k, v in rows[i].items() if k != "job_id_reason"}
    with pytest.raises(Exception):
        validate("results", {**SAMPLE, "qaoa": {**section, "table": bad, "ledger_index": None}})
