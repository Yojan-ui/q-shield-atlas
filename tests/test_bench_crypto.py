"""bench.crypto: real TLS 1.3 handshakes on lab services; classical, hybrid and pure post-quantum all negotiate."""

import json

import pytest

from bench.crypto import bench, handshake_bytes


def test_message_byte_parser():
    t = ">>> TLS 1.3, Handshake [length 0010], ClientHello\n<<< TLS 1.3, Handshake [length 0020], ServerHello\n<<< TLS 1.2, RecordHeader [length 0005]\n"
    assert handshake_bytes(t) == {"client_to_server": 16, "server_to_client": 32, "messages": {"ClientHello": 16, "ServerHello": 32}, "total": 48}


@pytest.fixture(scope="module")
def section(tmp_path_factory):
    return bench(2, tmp_path_factory.mktemp("runs"))


def test_every_configuration_negotiates_its_group(section):
    got = {r["id"]: r["negotiated_group"] for r in section["handshakes"]}
    assert got == {"classical-rsa": "X25519", "classical-ecdsa": "X25519", "hybrid": "X25519MLKEM768", "pq": "MLKEM768"}
    assert not section["not_measured"]
    pq, cl = (next(r for r in section["handshakes"] if r["id"] == k) for k in ("pq", "classical-ecdsa"))
    assert pq["handshake_bytes"]["total"] > cl["handshake_bytes"]["total"]  # ML-KEM keys + ML-DSA certificate are larger
    assert all(r["handshake_ms_median"] > 0 and len(r["transcript_sha256"]) == 64 for r in section["handshakes"])


def test_sizes_are_measured_and_security_levels_are_cited(section):
    p = section["primitives"]
    assert p["ML-DSA-65"]["signature_bytes"] > p["ECDSA P-256"]["signature_bytes"]
    assert p["ML-KEM-768"]["ciphertext_bytes"] and p["X25519"]["public_key_der_bytes"]
    assert all("ref" in v["security"] for v in p.values())
    assert "not QKD" in section["label"] or "QKD" in section["label"]
    json.dumps(section)
