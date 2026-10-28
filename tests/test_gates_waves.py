"""Compatibility matrix, tested rollback and the wave runner on real local TLS services."""

import copy
import json
from pathlib import Path

import pytest

from capture.services import load_lab, managed_service
from contracts import validate
from detect.live_probe import openssl_binary, openssl_info
from gates.__main__ import forced_rollback_policy
from gates.compat import judge, run_matrix
from gates.rollback import apply_with_rollback
from gates.wave_runner import NOT_VERIFIED, run_waves, wave_gates, wave_status

REPO = Path(__file__).resolve().parent.parent
LAB = load_lab()
INFO = openssl_info(openssl_binary())
pytestmark = pytest.mark.skipif(not INFO["ml_kem"], reason=f"{INFO['version']} has no ML-KEM (need OpenSSL >= 3.5, conda env pqc)")


def _cell(matrix, client):
    return next(c for c in matrix["cells"] if c["client"] == client)


@pytest.fixture(scope="module")
def matrices(tmp_path_factory):
    d = tmp_path_factory.mktemp("compat")
    out = {}
    for mode in ("transition", "strict"):
        with managed_service(f"t-{mode}", mode, LAB) as svc:
            out[mode] = run_matrix(svc, LAB, d)
    return out


# ---------- compatibility matrix ----------

def test_transition_pq_client_gets_x25519mlkem768(matrices):
    c = _cell(matrices["transition"], "pq-capable")
    assert c["actual"]["negotiated_group"] == "X25519MLKEM768" and c["result"] == "PASS"


@pytest.mark.parametrize("client, protocol", [("classical-only", "TLSv1.3"), ("tls1.2-only", "TLSv1.2")])
def test_transition_classical_client_connects_flagged_hndl(matrices, client, protocol):
    c = _cell(matrices["transition"], client)
    assert c["actual"]["connected"] and c["actual"]["negotiated_group"] == "X25519"
    assert c["actual"]["protocol"] == protocol
    assert c["result"] == "HNDL-exposed" and c["hndl_exposed"]
    assert c["result"] != "PASS"


@pytest.mark.parametrize("client", ["classical-only", "tls1.2-only"])
def test_strict_classical_client_refused(matrices, client):
    c = _cell(matrices["strict"], client)
    assert not c["actual"]["connected"] and c["result"] == "PASS"


def test_silent_downgrade_fails_even_if_policy_allows_it():
    policy = copy.deepcopy(LAB["compat_policy"])
    policy["transition"]["pq-capable"] = {"expect": "connect", "group": "X25519"}  # a bad policy
    result, reason = judge("transition", "pq-capable", {"connected": True, "negotiated_group": "X25519"}, LAB, policy)
    assert result == "FAIL" and "silent downgrade" in reason


def test_classical_connection_is_never_pass_even_if_policy_expects_it():
    result, _ = judge("legacy", "pq-capable", {"connected": True, "negotiated_group": "X25519"}, LAB, LAB["compat_policy"])
    assert result == "HNDL-exposed"


# ---------- rollback ----------

def _forced(svc, tmp_path, before_restore=None):
    policy = forced_rollback_policy(LAB)  # strict + "classical clients must connect" -> compat FAIL
    return apply_with_rollback(svc, "strict", lambda s: wave_gates(s, LAB, tmp_path, "t_", policy), LAB, tmp_path, "t_", before_restore)


def test_injected_gate_failure_rolls_back_and_restores_config(tmp_path):
    with managed_service("rb", "legacy", LAB) as svc:
        before = svc.config_sha256()
        res = _forced(svc, tmp_path)
        assert res["status"] == "rolled_back"
        assert res["gates"]["passed"] is False
        assert res["snapshot_sha256"] == before == res["restored_config_sha256"] == svc.config_sha256()
        assert res["applied_config_sha256"] != before
        assert res["health_check"]["result"] == "PASS" and res["health_check"]["negotiated_group"] == "X25519"
        assert svc.mode == "legacy" and svc.process.poll() is None


def test_corrupted_snapshot_reports_rollback_failed(tmp_path):
    def corrupt(snapshot: Path):
        snapshot.write_text(snapshot.read_text().replace('"legacy"', '"strict"'))

    with managed_service("rb-corrupt", "legacy", LAB) as svc:
        res = _forced(svc, tmp_path, before_restore=corrupt)
    assert res["status"] == "rollback_failed"
    assert res["restored_config_sha256"] != res["snapshot_sha256"]
    assert any("does not match the snapshot" in p for p in res["rollback_problems"])


def test_unreadable_snapshot_reports_rollback_failed(tmp_path):
    with managed_service("rb-garbage", "legacy", LAB) as svc:
        res = _forced(svc, tmp_path, before_restore=lambda p: p.write_text("{not json"))
    assert res["status"] == "rollback_failed"
    assert res["health_check"]["result"] == "FAIL"


def test_passing_gates_apply(tmp_path):
    with managed_service("ok", "legacy", LAB) as svc:
        res = apply_with_rollback(svc, "transition", lambda s: wave_gates(s, LAB, tmp_path, "ok_"), LAB, tmp_path, "ok_")
    assert res["status"] == "applied" and res["gates"]["pq_handshake"]["result"] == "PASS"


# ---------- wave runner ----------

@pytest.fixture(scope="module")
def demo_schedule():
    from schedule.problem import load_problem
    from schedule.baselines import run_baselines

    # same waves the CLI would read from out/schedule.json, but solver-free: greedy baseline plan
    p = load_problem()
    plan = run_baselines(p)["greedy"]
    return {"assets": [{"id": a.id, "kind": a.kind} for a in p.assets], "waves": plan["waves"]}


def test_wave_runner_every_wave_has_status_and_evidence(demo_schedule, tmp_path):
    run = run_waves(demo_schedule, LAB, tmp_path)
    mapping = LAB["waves"]["lab_services_by_kind"]
    kinds = {a["id"]: a["kind"] for a in demo_schedule["assets"]}
    assert len(run["waves"]) == len(demo_schedule["waves"])
    for w in run["waves"]:
        assert w["status"] != "planned"
        evidence = {e["lab_service"]: e for e in w["evidence"]["lab_services"]}
        for asset, status in w["asset_status"].items():
            if kinds[asset] not in mapping:
                assert status == NOT_VERIFIED
                continue
            e = evidence[mapping[kinds[asset]]]
            assert status == e["status"]
            if status == "applied":  # never "applied" without passing gate evidence
                assert e["gates"]["passed"] and e["gates"]["pq_handshake"]["result"] == "PASS"
                assert e["gates"]["compat"]["result"] == "PASS"
                assert e["snapshot_sha256"] and e["applied_config_sha256"]
    unmapped = sum(k not in mapping for k in kinds.values())
    assert run["asset_counts"].get(NOT_VERIFIED, 0) == unmapped
    assert (tmp_path / run["run_id"] / "wave_runner.json").exists()


def test_wave_runner_injected_failure_rolls_back_never_applied(demo_schedule, tmp_path):
    policy = copy.deepcopy(LAB["compat_policy"])
    policy["transition"]["classical-only"] = {"expect": "refused"}  # transition admits classical -> compat FAIL
    run = run_waves(demo_schedule, LAB, tmp_path, policy_override={"edge": policy})
    edge = [a["id"] for a in demo_schedule["assets"] if LAB["waves"]["lab_services_by_kind"].get(a["kind"]) == "edge"]
    assert edge and all(run["asset_status"][a] == "rolled_back" for a in edge)
    for w in run["waves"]:
        if any(a in edge for a in w["assets"]):
            assert w["status"] == "rolled_back"


def test_wave_status_rules():
    assert wave_status([NOT_VERIFIED, NOT_VERIFIED]) == NOT_VERIFIED
    assert wave_status(["applied", NOT_VERIFIED]) == "partially_verified"
    assert wave_status(["applied", "rolled_back"]) == "rolled_back"
    assert wave_status(["applied", "rollback_failed", "rolled_back"]) == "rollback_failed"
    assert wave_status(["applied"]) == "applied"


def test_wave_run_merges_into_valid_results(demo_schedule, tmp_path, opt_client):
    from contracts.assemble import assemble
    from schedule.__main__ import build_section
    from schedule.problem import load_problem

    section = build_section(load_problem(), opt_client, tmp_path / "r", with_sensitivity=False)
    (tmp_path / "schedule.json").write_text(json.dumps(section))
    run = run_waves({"assets": section["assets"], "waves": section["waves"]}, LAB, tmp_path / "r")
    (tmp_path / "wave_status.json").write_text(json.dumps(run))
    results = assemble(tmp_path)
    validate("results", results)
    assert all(w["status"] != "planned" for w in results["waves"])
    assert {a["status"] for a in results["assets"]} <= {"applied", NOT_VERIFIED, "rolled_back", "rollback_failed"}

    bad = copy.deepcopy(results)
    bad["waves"][0]["status"] = "applied"
    del bad["waves"][0]["evidence"]
    with pytest.raises(Exception):
        validate("results", bad)
