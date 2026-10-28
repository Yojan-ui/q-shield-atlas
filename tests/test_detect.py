import json
import os
from pathlib import Path

import pytest

from contracts import validate
from contracts.assemble import assemble
from detect import __main__ as cli
from detect.drift import compare
from detect.inventory import build_inventory
from detect.live_probe import probe
from detect.static_scan import scan
from schedule.problem import problem_from_dicts
from tests.tls_server import free_port, tls_server

REPO = Path(__file__).resolve().parent.parent
SAMPLE = REPO / "detect" / "fixtures" / "sample_services"
BANK = REPO / "detect" / "fixtures" / "mock_bank"


def key(f):
    return (f["file"], f["line"], f["family"], f["use"])


# ---------- static scan ----------

def test_sample_services_match_ground_truth_exactly():
    expected = {tuple(x) for x in json.loads((SAMPLE / "expected.json").read_text())["findings"]}
    got = {key(f) for f in scan(SAMPLE)["findings"]}
    assert got - expected == set(), "false positives"
    assert expected - got == set(), "missed findings"


def test_evidence_points_at_real_lines():
    for root in (SAMPLE, BANK):
        for f in scan(root)["findings"]:
            if f["rule"] == "cert-public-key":
                continue
            line = (root / f["file"]).read_text().splitlines()[f["line"] - 1]
            assert f["snippet"] == line.strip()[:157] + ("..." if len(line.strip()) > 160 else "") or f["snippet"] == line.strip()


def test_private_key_bodies_are_never_copied(tmp_path):
    body = "MIIEpAIBAAKCAQEAsecretsecretsecretsecret"
    (tmp_path / "svc.key").write_text(f"-----BEGIN RSA PRIVATE KEY-----\n{body}\n-----END RSA PRIVATE KEY-----\n")
    out = json.dumps(scan(tmp_path))
    assert "pem-rsa-private" in out and body not in out


def test_binary_files_and_symlinks_skipped(tmp_path):
    (tmp_path / "blob.py").write_bytes(b"\0\0rsa.generate_private_key(")
    (tmp_path / "real.py").write_text("k = rsa.generate_private_key(65537, 2048)\n")
    os.symlink(tmp_path / "real.py", tmp_path / "link.py")
    files = {f["file"] for f in scan(tmp_path)["findings"]}
    assert files == {"real.py"}


def test_tree_hash_changes_when_a_file_changes(tmp_path):
    (tmp_path / "a.conf").write_text("ssl_ecdh_curve X25519;\n")
    before = scan(tmp_path)["tree_sha256"]
    (tmp_path / "a.conf").write_text("ssl_ecdh_curve X25519MLKEM768;\n")
    assert scan(tmp_path)["tree_sha256"] != before


# ---------- inventory ----------

def test_mock_bank_inventory_matches_schedule_demo_data():
    inv = build_inventory(BANK, scan(BANK))
    demo = json.loads((REPO / "schedule" / "data" / "mock_bank_assets.json").read_text())["assets"]
    fields = ("kind", "data_class")
    assert {a["id"]: ({k: a[k] for k in fields}, sorted(a["depends_on"])) for a in inv["assets"]} == {
        a["id"]: ({k: a[k] for k in fields}, sorted(a["depends_on"])) for a in demo
    }
    assert [x["id"] for x in inv["not_vulnerable"]] == ["status-page"]
    assert all(a["evidence"] for a in inv["assets"])


def test_inventory_feeds_schedule():
    inv = build_inventory(BANK, scan(BANK))
    cfg = json.loads((REPO / "config" / "assumptions.json").read_text())
    problem = problem_from_dicts(cfg, inv)
    assert len(problem.assets) == 16
    assert all(a.evidence for a in problem.assets)


# ---------- live probe (real openssl s_server on localhost) ----------

def test_probe_classical_server(tmp_path):
    with tls_server(tmp_path, "X25519") as (host, port):
        live = probe(host, port)
    assert live["handshake_ok"]
    assert (live["group"], live["kex_family"], live["cert_algorithm"]) == ("X25519", "ECC", "RSA-2048")
    assert live["kex_quantum_vulnerable"] and live["auth_quantum_vulnerable"]


def test_probe_hybrid_server(tmp_path):
    with tls_server(tmp_path, "X25519MLKEM768") as (host, port):
        live = probe(host, port)
    assert live["handshake_ok"]
    assert (live["group"], live["kex_family"]) == ("X25519MLKEM768", "PQC")
    assert not live["kex_quantum_vulnerable"]
    assert live["auth_quantum_vulnerable"]  # hybrid KEM does not fix the RSA certificate


def _bank_findings(service):
    return [f for f in scan(BANK)["findings"] if f["file"].startswith(f"services/{service}/")]


def test_drift_pqc_claimed_but_classical_negotiated(tmp_path):
    with tls_server(tmp_path, "X25519") as (host, port):
        report = compare("web-gw", _bank_findings("web-gw"), probe(host, port))
    assert [d["kind"] for d in report["drift"]] == ["pqc_claimed_not_negotiated"]


def test_no_drift_when_live_matches_config(tmp_path):
    with tls_server(tmp_path, "X25519MLKEM768") as (host, port):
        report = compare("web-gw", _bank_findings("web-gw"), probe(host, port))
    assert report["drift"] == []


def test_drift_undeclared_live_certificate(tmp_path):
    # ops-dash config only shows ECDH groups; the live endpoint presents an RSA certificate
    with tls_server(tmp_path, "X25519") as (host, port):
        report = compare("ops-dash", _bank_findings("ops-dash"), probe(host, port))
    assert [d["kind"] for d in report["drift"]] == ["undeclared_live_cert"]


def test_probe_failure_is_reported_not_hidden():
    live = probe("127.0.0.1", free_port())
    assert not live["handshake_ok"]
    assert compare("x", [], live)["drift"][0]["kind"] == "probe_failed"


# ---------- CLI -> contracts ----------

def test_cli_outputs_validate_in_results(tmp_path, opt_client):
    from schedule.__main__ import build_section
    from schedule.problem import load_problem

    with tls_server(tmp_path, "X25519") as (host, port):
        cli.main(["--probe", f"web-gw={host}:{port}", "--out-dir", str(tmp_path), "--runs", str(tmp_path / "runs")])
    detect = json.loads((tmp_path / "detect.json").read_text())
    assert detect["drift_count"] == 1
    assert (tmp_path / "runs" / detect["run_id"] / "probe_web-gw.txt").exists()
    problem = load_problem(inventory_path=tmp_path / "inventory.json")
    section = build_section(problem, opt_client, tmp_path / "runs", with_sensitivity=False)
    (tmp_path / "schedule.json").write_text(json.dumps(section))
    results = assemble(tmp_path)
    validate("results", results)
    assert results["detect"]["run_id"] == detect["run_id"]
    assert all(a["evidence"] for a in results["assets"])


def test_openssl_lookup_prefers_env_then_config_and_requires_pqc(monkeypatch, tmp_path):
    from detect import live_probe

    fake = tmp_path / "openssl"
    fake.write_text("#!/bin/sh\necho 'OpenSSL 1.0 fake'\n")
    fake.chmod(0o755)
    monkeypatch.setenv("QSHIELD_OPENSSL", str(fake))
    cands = live_probe.openssl_candidates()
    assert cands[0] == str(fake)
    cfg = json.loads((REPO / "config" / "lab.json").read_text())["openssl"]["path"]
    assert cands.index(cfg) == 1
    assert not live_probe._supports_pqc(str(fake))  # a binary without ML-KEM/ML-DSA is skipped
    assert live_probe._supports_pqc(cfg)
