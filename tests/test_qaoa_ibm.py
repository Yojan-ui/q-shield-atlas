"""IBM hardware path (python -m qaoa --ibm): circuit equivalence, guards, table/contract rows. Never contacts IBM."""

import copy
import json

import numpy as np
import pytest

from qaoa import local_sim
from qaoa.table import build_table
from tests.test_qaoa import CFG, q, schedule_doc  # noqa: F401  (q is a fixture)
from tests.test_qaoa_table import local_section, qaoa_validator  # noqa: F401

pytest.importorskip("qiskit")


def test_qiskit_circuit_equals_numpy_qaoa_state(q):
    """The circuit sent to IBM reproduces the local statevector (Qiskit Statevector, no network)."""
    from qiskit.quantum_info import Statevector

    from qaoa.ibm_run import build_qiskit_circuit

    E = q.energies()
    sc = local_sim.energy_scale(E)
    g, b = [0.41, 1.3], [0.77, 0.2]
    psi = local_sim.statevector(E / sc, g, b)
    sv = Statevector(build_qiskit_circuit(q, g, b, sc, measure=False)).data
    assert abs(np.vdot(psi, sv)) == pytest.approx(1.0, abs=1e-9)


def test_qiskit_counts_put_qubit0_rightmost():
    from qiskit import QuantumCircuit
    from qiskit.quantum_info import Statevector

    c = QuantumCircuit(4)
    c.x(0)
    assert Statevector(c).probabilities_dict() == {"0001": 1.0}


def test_backend_allowlist():
    from qaoa.ibm_run import check_backend

    with pytest.raises(ValueError):
        check_backend("ibm_torino", CFG["ibm"]["allowed_backends"])
    check_backend("ibm_fez", CFG["ibm"]["allowed_backends"])
    assert CFG["ibm"]["max_jobs_per_run"] <= 3


def test_ibm_refused_under_pytest_before_any_connection(monkeypatch, tmp_path):
    from qaoa import __main__ as cli
    from qaoa import ibm_run
    from schedule.platform_guard import PlatformRefused

    monkeypatch.setattr(ibm_run, "_service", lambda *a, **k: pytest.fail("IBM service contacted from pytest"))
    (tmp_path / "schedule.json").write_text(json.dumps(schedule_doc()))
    with pytest.raises(PlatformRefused):
        cli.main(["--ibm", "--schedule", str(tmp_path / "schedule.json"), "--runs", str(tmp_path), "--out-dir", str(tmp_path)])


def with_ibm(section, finished=(1, 2, 3)):
    """Test fixture only: IBM records shaped exactly like qaoa/__main__.py writes them (p not in `finished` stays queued)."""
    s = copy.deepcopy(section)
    s["ibm"] = {"requested": True, "backend": "ibm_fez", "jobs": []}
    for local in [r for r in section["runs"] if r["source"] == "local"]:
        p = local["p"]
        job = {"p": p, "job_id": f"ibmjob{p}", "backend": "ibm_fez", "status": "ok" if p in finished else "queued",
               "qpu_seconds": 2.0 if p in finished else None, "transpiled_depth": 40 * p, "two_qubit_gates": 30 * p}
        s["ibm"]["jobs"].append(job)
        if p in finished:
            s["runs"].append({**local, "source": "ibm", "backend": "ibm_fez", "job_ids": [job["job_id"]], "hardware": True,
                              "qpu_seconds": 2.0, "transpiled_depth": 40 * p, "two_qubit_gates": 30 * p,
                              "two_qubit_gate_names": {"cz": 30 * p}, "physical_qubits": list(range(5))})
    return s


def test_ibm_rows_carry_hardware_provenance_and_validate(local_section):  # noqa: F811
    s = with_ibm(local_section)
    table = build_table(s, ledger_index=4)
    ibm = [r for r in table if r["source"] == "ibm"]
    assert [r["p"] for r in ibm] == [1, 2, 3] and all(r["status"] == "ok" for r in ibm)
    assert ibm[1]["hardware"] == {"backend": "ibm_fez", "job_id": "ibmjob2", "qpu_seconds": 2.0, "transpiled_depth": 80,
                                  "two_qubit_gates": 60, "two_qubit_gate_names": {"cz": 60}, "physical_qubits": [0, 1, 2, 3, 4]}
    qaoa_validator().validate({**s, "table": table, "ledger_index": 4})


def test_queued_ibm_job_is_shown_with_its_id_and_no_numbers(local_section):  # noqa: F811
    s = with_ibm(local_section, finished=(1,))
    table = build_table(s)
    p3 = next(r for r in table if r["source"] == "ibm" and r["p"] == 3)
    assert p3["status"] == "queued" and p3["metrics"] is None and p3["job_ids"] == ["ibmjob3"]
    assert "--ibm-fetch" in p3["status_text"]
    qaoa_validator().validate({**s, "table": table, "ledger_index": None})


def test_no_ibm_rows_unless_requested(local_section):  # noqa: F811
    assert not [r for r in build_table(local_section) if r["source"] == "ibm"]


def test_truststore_is_optional_and_never_disables_verification(monkeypatch):
    """Without truststore nothing changes (macOS default); with it, the OS store is used and verification stays on."""
    import ssl
    import sys

    from qaoa.ibm_run import use_os_trust_store

    monkeypatch.setitem(sys.modules, "truststore", None)  # import raises ImportError
    assert use_os_trust_store() is False
    calls = []
    monkeypatch.setitem(sys.modules, "truststore", type("T", (), {"inject_into_ssl": staticmethod(lambda: calls.append(1))}))
    assert use_os_trust_store() is True and calls == [1]
    assert ssl.create_default_context().verify_mode == ssl.CERT_REQUIRED


def test_qpu_estimate_is_conservative_and_capped():
    from qaoa.ibm_run import JOB_OVERHEAD_S, estimate_qpu_seconds

    class Isa:
        def estimate_duration(self, target, unit="s"):
            return 1e-4

    class Backend:
        target = None

        def configuration(self):
            return type("C", (), {"default_rep_delay": 2.5e-4})()

    est = estimate_qpu_seconds([Isa(), Isa(), Isa()], Backend(), 2048)
    assert est == pytest.approx(3 * (2048 * 3.5e-4 + JOB_OVERHEAD_S))
    cfg = json.loads(open("config/qaoa.json").read())["ibm"]
    assert cfg["max_estimated_qpu_s"] == 90 and est < cfg["max_estimated_qpu_s"]
