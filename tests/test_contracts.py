import copy

import pytest
from jsonschema import ValidationError

from contracts import SCHEMAS, load_schema, validate

H = "ab" * 32


@pytest.mark.parametrize("name", SCHEMAS)
def test_schemas_are_valid_json_schema(name):
    load_schema(name)


LEDGER_ENTRY = {"index": 0, "type": "schedule.run", "payload_hash": H, "prev_hash": "0" * 64, "sig_mldsa": "c2ln", "ts": "2026-10-28T12:00:00Z"}


def test_ledger_entry_valid():
    validate("ledger_entry", LEDGER_ENTRY)


@pytest.mark.parametrize(
    "mutate",
    [
        lambda e: e.pop("sig_mldsa"),
        lambda e: e.update(payload_hash="xyz"),
        lambda e: e.update(index=-1),
        lambda e: e.update(extra=1),
    ],
)
def test_ledger_entry_invalid(mutate):
    entry = copy.deepcopy(LEDGER_ENTRY)
    mutate(entry)
    with pytest.raises(ValidationError):
        validate("ledger_entry", entry)


CAPTURE = {
    "schema_version": "2.0",
    "run_id": "0" * 32,
    "generated_at": "2026-10-28T12:00:00Z",
    "openssl_version": "OpenSSL 3.6.5",
    "sessions": [
        {"service_id": "hybrid", "negotiated_group": "X25519MLKEM768", "cipher": "TLS_AES_256_GCM_SHA384",
         "protocol": "TLSv1.3", "cert_alg": "RSA", "transcript_sha256": H, "timestamp": "2026-10-28T12:00:00Z"}
    ],
    "refused_attempts": [],
}


def test_capture_valid():
    validate("capture", CAPTURE)


@pytest.mark.parametrize("field", ["negotiated_group", "cipher", "protocol", "cert_alg", "transcript_sha256", "service_id"])
def test_capture_missing_session_field_rejected(field):
    doc = copy.deepcopy(CAPTURE)
    del doc["sessions"][0][field]
    with pytest.raises(ValidationError):
        validate("capture", doc)


def test_capture_payload_fields_rejected():
    doc = copy.deepcopy(CAPTURE)
    doc["sessions"][0]["ciphertext_b64"] = "AAAA"
    with pytest.raises(ValidationError):
        validate("capture", doc)


def test_capture_refused_attempt_cannot_claim_established():
    doc = copy.deepcopy(CAPTURE)
    doc["refused_attempts"] = [{"service_id": "hybrid", "client_groups_offered": "X25519", "established": True,
                                "transcript_sha256": H, "timestamp": "2026-10-28T12:00:00Z"}]
    with pytest.raises(ValidationError):
        validate("capture", doc)


def _plan(method):
    return {
        "method": method,
        "completion_week": {"a": 1},
        "per_scenario": [{"scenario": "Z2030", "year": 2030, "exposure_years": 1.0, "weighted_exposure": 2.0}],
        "expected_weighted": 2.0,
        "worst_case_weighted": 2.0,
        "makespan_weeks": 1,
        "produced_by": {"solver": "fixture", "run_ids": [], "job_ids": []},
    }


def _results():
    # Structural fixture only: exercises the contract, not a claimed result.
    return {
        "schema_version": "1.0",
        "generated_at": "2026-10-28T12:00:00Z",
        "assumptions": {"label": "ASSUMPTIONS", "sha256": H},
        "scenarios": [{"name": "Z2030", "year": 2030, "weight": 1.0}],
        "assets": [
            {"id": "a", "name": "A", "algorithm": "RSA-2048", "shelf_life_years": 1, "effort_days": 1,
             "risk_weight": 2, "depends_on": [], "status": "planned", "planned_week": 1}
        ],
        "waves": [{"week": 1, "assets": ["a"], "effort_days": 1, "status": "planned"}],
        "exposure": _plan("milp"),
        "baselines": {"fcfs": _plan("fcfs"), "greedy": _plan("greedy")},
        "avoided": {"vs_fcfs": [], "vs_greedy": []},
        "solver_runs": [
            {"run_id": "0" * 32, "ts": "2026-10-28T12:00:00Z", "stage": "s", "solver": "qpiai-opt local", "provider": "qpiai-opt",
             "package_version": "0.0.9", "mode": "local", "job_id": None,
             "job_id_reason": "local solve issues no job id", "status": "optimal",
             "inputs_sha256": H, "output_sha256": H}
        ],
        "detect": None, "handshake_evidence": None, "gates": None, "qaoa": None, "ledger_root": None,
    }


def test_results_valid():
    validate("results", _results())


def test_results_null_job_id_requires_reason():
    doc = _results()
    doc["solver_runs"][0]["job_id_reason"] = None
    with pytest.raises(ValidationError):
        validate("results", doc)


def test_results_plan_requires_solver_attribution():
    doc = _results()
    del doc["baselines"]["greedy"]["produced_by"]
    with pytest.raises(ValidationError):
        validate("results", doc)


def test_results_bad_status_fails():
    doc = _results()
    doc["assets"][0]["status"] = "done"
    with pytest.raises(ValidationError):
        validate("results", doc)
