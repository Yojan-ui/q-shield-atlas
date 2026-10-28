"""Real TLS 1.3 handshake evidence and the PQ handshake gate. No decryption anywhere."""

import copy
import json
import re
import socket
from pathlib import Path

import psutil
import pytest
from jsonschema import ValidationError

from capture.__main__ import capture_all, handshake_evidence
from capture.handshake import cert_alg_from_signature, parse_brief
from capture.services import HOST, lab_service, load_lab
from contracts import validate
from detect.live_probe import openssl_binary, openssl_info
from gates.pq_handshake import evaluate

REPO = Path(__file__).resolve().parent.parent
LAB = load_lab()
INFO = openssl_info(openssl_binary())
needs_mlkem = pytest.mark.skipif(not INFO["ml_kem"], reason=f"{INFO['version']} has no ML-KEM (need OpenSSL >= 3.5, conda env pqc)")


@pytest.fixture(scope="module")
def capture(tmp_path_factory):
    if not INFO["ml_kem"]:
        pytest.skip(f"{INFO['version']} has no ML-KEM (need OpenSSL >= 3.5, conda env pqc)")
    return capture_all(LAB, tmp_path_factory.mktemp("runs"))


@pytest.fixture(scope="module")
def gates(capture):
    return evaluate(capture, LAB)


def _gate(gates, kind, sid):
    return next(g for g in gates[kind] if g["service_id"] == sid)


def _session(capture, sid, groups):
    return next(s for s in capture["sessions"] if s["service_id"] == sid and s["client_groups_offered"] == groups)


# ---------- handshake outcomes and gate ----------

def test_legacy_negotiates_x25519_gate_fails_hndl_exposed(capture, gates):
    assert _session(capture, "legacy", LAB["client_groups"])["negotiated_group"] == "X25519"
    g = _gate(gates, "pq_handshake", "legacy")
    assert (g["result"], g["kex_class"], g["hndl_exposed"]) == ("FAIL", "classical", True)
    assert g["label"] == "HNDL-exposed: recorded traffic relies on classical key exchange"


def test_hybrid_negotiates_x25519mlkem768_gate_passes(capture, gates):
    s = _session(capture, "hybrid", LAB["client_groups"])
    assert (s["negotiated_group"], s["protocol"]) == ("X25519MLKEM768", "TLSv1.3")
    g = _gate(gates, "pq_handshake", "hybrid")
    assert (g["result"], g["kex_class"], g["hndl_exposed"], g["label"]) == ("PASS", "hybrid-pq", False, None)


def test_classical_only_client_refused_by_hybrid(capture, gates):
    classical = LAB["classical_only_client_groups"]
    assert not any(s["service_id"] == "hybrid" and s["client_groups_offered"] == classical for s in capture["sessions"])
    attempt = next(a for a in capture["refused_attempts"] if a["service_id"] == "hybrid")
    assert attempt["client_groups_offered"] == classical and attempt["established"] is False
    assert _gate(gates, "downgrade", "hybrid")["result"] == "PASS"
    assert _gate(gates, "downgrade", "legacy")["result"] == "FAIL"  # legacy accepts classical, as expected


def test_downgrade_not_run_is_reported_not_passed(capture):
    doc = copy.deepcopy(capture)
    doc["refused_attempts"] = []
    doc["sessions"] = [s for s in doc["sessions"] if s["client_groups_offered"] == LAB["client_groups"]]
    assert {g["result"] for g in evaluate(doc, LAB)["downgrade"]} == {"NOT_RUN"}


def test_evidence_labels_and_no_decryption_claim(capture, gates):
    ev = handshake_evidence(capture, gates)
    assert {s["service_id"]: s["hndl_exposed"] for s in ev["sessions"]} == {"legacy": True, "hybrid": False}
    assert "No decryption" in ev["note"]


# ---------- contract ----------

def test_capture_validates(capture):
    validate("capture", capture)


def test_capture_missing_negotiated_group_rejected(capture):
    doc = copy.deepcopy(capture)
    del doc["sessions"][0]["negotiated_group"]
    with pytest.raises(ValidationError):
        validate("capture", doc)


def test_capture_with_evidence_assembles_into_results(capture, gates, tmp_path, opt_client):
    from contracts.assemble import assemble
    from schedule.__main__ import build_section
    from schedule.problem import load_problem

    (tmp_path / "schedule.json").write_text(json.dumps(build_section(load_problem(), opt_client, tmp_path / "r", with_sensitivity=False)))
    (tmp_path / "handshake_evidence.json").write_text(json.dumps(handshake_evidence(capture, gates)))
    (tmp_path / "gates.json").write_text(json.dumps(gates))
    results = assemble(tmp_path)
    assert results["handshake_evidence"]["capture_sha256"]
    assert "attack" not in results


# ---------- process hygiene: loopback only, always cleaned up ----------

def _listen_addrs(pid):
    return {c.laddr.ip for c in psutil.Process(pid).net_connections(kind="inet") if c.status == psutil.CONN_LISTEN}


@needs_mlkem
def test_services_bind_loopback_only_and_are_cleaned_up():
    with lab_service("hybrid", "X25519MLKEM768", lab=LAB) as svc:
        proc = svc.process
        assert svc.host == HOST == "127.0.0.1"
        assert _listen_addrs(proc.pid) == {"127.0.0.1"}
        port = svc.port
    assert proc.poll() is not None
    with pytest.raises(OSError):
        socket.create_connection((HOST, port), timeout=0.5).close()


@needs_mlkem
def test_service_cleaned_up_when_body_raises():
    with pytest.raises(RuntimeError):
        with lab_service("legacy", "X25519", lab=LAB) as svc:
            proc = svc.process
            raise RuntimeError("boom")
    assert proc.poll() is not None


def test_lab_code_never_binds_all_interfaces():
    for folder in ("capture", "gates", "detect", "tests"):
        for path in (REPO / folder).rglob("*.py"):
            text = path.read_text()
            if path.name == "test_capture_gates.py":
                text = text.replace('"0.0.0.0"', "")  # this assertion's own literal
            assert "0.0.0.0" not in text, path
            assert not re.search(r"bind\(\(\s*['\"]{2}", text), f"{path} binds to '' (all interfaces)"


# ---------- parser (offline, recorded output) ----------

HYBRID_BRIEF = """CONNECTION ESTABLISHED
Protocol version: TLSv1.3
Ciphersuite: TLS_AES_256_GCM_SHA384
Signature type: rsa_pss_rsae_sha256
Negotiated TLS1.3 group: X25519MLKEM768
DONE
"""


def test_parse_brief_hybrid_and_refused():
    p = parse_brief(HYBRID_BRIEF)
    assert (p["established"], p["negotiated_group"], p["cipher"], p["protocol"], p["cert_alg"]) == (
        True, "X25519MLKEM768", "TLS_AES_256_GCM_SHA384", "TLSv1.3", "RSA")
    r = parse_brief("error:0A000410:SSL routines:ssl3_read_bytes:ssl/tls alert handshake failure:...:SSL alert number 40\n")
    assert not r["established"] and r["negotiated_group"] is None


@pytest.mark.parametrize("sig, fam", [("rsa_pss_rsae_sha256", "RSA"), ("ecdsa_secp256r1_sha256", "ECDSA"), ("ed25519", "Ed25519"), ("mldsa65", "ML-DSA")])
def test_cert_alg_from_signature(sig, fam):
    assert cert_alg_from_signature(sig) == fam
