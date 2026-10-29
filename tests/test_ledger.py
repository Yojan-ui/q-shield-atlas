"""ML-DSA-65-signed ledger: every tamper must fail verification at the right index with the right reason."""

import base64
import json
import random
import subprocess
from pathlib import Path

import pytest

from ledger.backend import ALG, detect
from ledger.ingest import ledger_summary
from ledger.log import Ledger, canonical, read_entries, signed_bytes
from ledger.merkle import MerkleTree, verify_proof
from ledger.verify import verify

REPO = Path(__file__).resolve().parent.parent
N = 6


@pytest.fixture(scope="module")
def backend():
    return detect()


@pytest.fixture(scope="module")
def keys(backend, tmp_path_factory):
    d = tmp_path_factory.mktemp("keys")  # ephemeral test key: the repo's signing key is never used
    backend.generate(d / "sk.pem", d / "pk.pem")
    backend.generate(d / "other_sk.pem", d / "other_pk.pem")
    return d


@pytest.fixture
def world(backend, keys, tmp_path):
    """A small repo with N run manifests ingested into a ledger, and its anchor."""
    payloads = []
    for i in range(N):
        p = tmp_path / "runs" / f"run{i}" / "manifest.json"
        p.parent.mkdir(parents=True)
        p.write_text(json.dumps({"run_id": f"run{i}", "value": i}))
        payloads.append(p)
    ledger = Ledger(tmp_path / "out" / "ledger.jsonl", backend, keys / "sk.pem", keys / "pk.pem", tmp_path)
    for i, p in enumerate(payloads):
        ledger.append(f"test.run{i}", p)
    anchor = ledger_summary(ledger, tmp_path)
    return {"root": tmp_path, "ledger": ledger, "path": ledger.path, "payloads": payloads, "anchor": anchor}


def check(world, backend, keys, public_key="pk.pem"):
    return verify(world["path"], keys / public_key, backend, world["root"], world["anchor"])


def rewrite(path, entries):
    path.write_text("".join(canonical(e).decode() + "\n" for e in entries))


def assert_fails(report, index, reason_part):
    assert not report["ok"], report
    assert report["first_failure"]["index"] == index, report
    assert reason_part in report["first_failure"]["reason"], report


# ---------- clean ----------

def test_clean_ledger_verifies(world, backend, keys):
    report = check(world, backend, keys)
    assert report["ok"] and report["entries_checked"] == N and report["root"] == world["anchor"]["root"]


def test_entries_record_backend_and_parameter_set(world):
    for e in read_entries(world["path"]):
        assert e["alg"] == ALG == "ML-DSA-65"
        assert e["backend"].startswith("openssl-cli (OpenSSL 3.")
        assert e["pubkey_fp"] == world["anchor"]["pubkey_fp"]
    assert read_entries(world["path"])[0]["prev_hash"] == "0" * 64


def test_signature_is_standard_mldsa65_cross_verified_with_cryptography(world, keys):
    """Independent implementation (pyca/cryptography) accepts the OpenSSL signatures."""
    from cryptography.hazmat.primitives.asymmetric import mldsa
    from cryptography.hazmat.primitives.serialization import load_pem_public_key

    pk = load_pem_public_key((keys / "pk.pem").read_bytes())
    assert isinstance(pk, mldsa.MLDSA65PublicKey)
    for e in read_entries(world["path"]):
        pk.verify(base64.b64decode(e["sig_mldsa"]), signed_bytes(e))  # raises on failure


def test_inclusion_proof_for_random_entry(world):
    entries = read_entries(world["path"])
    items = [canonical(e) for e in entries]
    tree = MerkleTree(items)
    i = random.Random(5).randrange(len(items))
    assert tree.root() == world["anchor"]["root"]
    assert verify_proof(items[i], i, len(items), tree.inclusion_proof(i), world["anchor"]["root"])


# ---------- tamper cases ----------

def test_edit_one_byte_in_payload_file(world, backend, keys):
    p = world["payloads"][3]
    data = bytearray(p.read_bytes())
    data[-2] ^= 0x01
    p.write_bytes(bytes(data))
    assert_fails(check(world, backend, keys), 3, "payload hash mismatch")


def test_edit_field_in_entry(world, backend, keys):
    entries = read_entries(world["path"])
    entries[2]["type"] = "test.forged"
    rewrite(world["path"], entries)
    assert_fails(check(world, backend, keys), 2, "signature does not verify")


def test_corrupt_signature(world, backend, keys):
    entries = read_entries(world["path"])
    sig = bytearray(base64.b64decode(entries[4]["sig_mldsa"]))
    sig[10] ^= 0xFF
    entries[4]["sig_mldsa"] = base64.b64encode(bytes(sig)).decode()
    rewrite(world["path"], entries)
    assert_fails(check(world, backend, keys), 4, "signature does not verify")


def test_delete_middle_entry(world, backend, keys):
    entries = read_entries(world["path"])
    del entries[2]
    rewrite(world["path"], entries)
    assert_fails(check(world, backend, keys), 2, "index mismatch: expected 2, found 3")


def test_reorder_two_entries(world, backend, keys):
    entries = read_entries(world["path"])
    entries[1], entries[3] = entries[3], entries[1]
    rewrite(world["path"], entries)
    assert_fails(check(world, backend, keys), 1, "index mismatch: expected 1, found 3")


def test_truncate_tail_breaks_anchored_root(world, backend, keys):
    entries = read_entries(world["path"])
    rewrite(world["path"], entries[:-2])
    assert_fails(check(world, backend, keys), N - 2, "do not match results.json anchor")


def test_different_public_key(world, backend, keys):
    assert_fails(check(world, backend, keys, "other_pk.pem"), 0, "does not match the verifying key")


def test_valid_signature_from_other_key_with_forged_fingerprint(world, backend, keys):
    """Re-signing an edited entry with another key and copying the right fingerprint still fails."""
    entries = read_entries(world["path"])
    entries[1]["type"] = "test.forged"
    entries[1]["sig_mldsa"] = base64.b64encode(backend.sign(keys / "other_sk.pem", signed_bytes(entries[1]))).decode()
    rewrite(world["path"], entries)
    assert_fails(check(world, backend, keys), 1, "signature does not verify")


# ---------- keys never in the repo ----------

def test_no_private_key_tracked_in_git():
    tracked = subprocess.run(["git", "ls-files"], cwd=REPO, capture_output=True, text=True, check=True).stdout.split()
    assert not [f for f in tracked if f.startswith("keys/") or f.endswith((".key", "sk.pem"))]
    for f in tracked:
        path = REPO / f
        if path.is_file() and path.suffix in {".pem", ".key", ".der", ""}:
            assert b"PRIVATE KEY-----" not in path.read_bytes()[:200], f
    ignored = subprocess.run(["git", "check-ignore", "-q", "keys/ledger_mldsa65.key"], cwd=REPO)
    assert ignored.returncode == 0
    assert (REPO / "ledger" / "pubkey" / "ledger_mldsa65.pub.pem").exists()


def test_committed_public_key_fingerprint_matches(backend):
    pk = REPO / "ledger" / "pubkey" / "ledger_mldsa65.pub.pem"
    fp = (REPO / "ledger" / "pubkey" / "ledger_mldsa65.pub.sha256").read_text().strip()
    assert backend.fingerprint(pk) == fp and backend.key_alg(pk) == "ML-DSA-65"


def test_private_key_file_mode_is_0600(backend, tmp_path):
    backend.generate(tmp_path / "sk.pem", tmp_path / "pk.pem")
    assert (tmp_path / "sk.pem").stat().st_mode & 0o777 == 0o600


def test_keygen_never_touches_committed_public_key(monkeypatch, tmp_path):
    import ledger.__main__ as cli

    committed = (REPO / "ledger" / "pubkey" / "ledger_mldsa65.pub.pem").read_bytes()
    monkeypatch.setattr(cli, "PRIVATE_KEY", tmp_path / "keys" / "ledger_mldsa65.key")
    monkeypatch.setattr(cli, "LOCAL_PUBLIC_KEY", tmp_path / "keys" / "ledger_mldsa65.pub.pem")
    assert cli.main(["keygen"]) == 0
    assert (tmp_path / "keys" / "ledger_mldsa65.pub.pem").exists()
    assert cli.default_public_key() == tmp_path / "keys" / "ledger_mldsa65.pub.pem"
    assert (REPO / "ledger" / "pubkey" / "ledger_mldsa65.pub.pem").read_bytes() == committed
    with pytest.raises(SystemExit):
        cli.main(["keygen"])  # refuses to overwrite


def test_verifying_a_copy_never_touches_recorded_results(tmp_path):
    """Live tamper demo safety: `ledger verify --ledger COPY` must not rewrite out/ results or verify status."""
    import ledger.__main__ as cli

    out = REPO / "out"
    if not (out / "results.json").exists() or not (out / "ledger.jsonl").exists():
        pytest.skip("no generated out/results.json + ledger")
    before = {p: p.read_bytes() for p in (out / "results.json", out / "ledger_verify.json") if p.exists()}
    entries = read_entries(out / "ledger.jsonl")
    entries[min(2, len(entries) - 1)]["type"] = "forged"
    copy_path = tmp_path / "ledger.jsonl"
    copy_path.write_text("".join(canonical(e).decode() + "\n" for e in entries))
    assert cli.main(["verify", "--ledger", str(copy_path)]) == 1
    assert {p: p.read_bytes() for p in before} == before


# ---------- verify before append (ledger_open / ingest / append) ----------

def test_ingest_verifies_intact_chain_before_append(world, keys, capsys):
    import ledger.__main__ as cli
    from ledger.backend import detect as _detect

    cli.check_chain_before_append(world["path"], keys / "pk.pem", _detect(), world["root"])
    assert f"chain verified ({N} entries) before append" in capsys.readouterr().out


def test_tampered_chain_stops_before_append(world, keys):
    import ledger.__main__ as cli
    from ledger.backend import detect as _detect

    entries = read_entries(world["path"])
    entries[2]["type"] = "tampered"
    rewrite(world["path"], entries)
    before = world["path"].read_bytes()
    with pytest.raises(SystemExit) as e:
        cli.check_chain_before_append(world["path"], keys / "pk.pem", _detect(), world["root"])
    assert "Proof Chain verification FAILED at #2" in str(e.value) and "nothing was signed" in str(e.value)
    assert world["path"].read_bytes() == before  # nothing appended


def test_empty_ledger_is_fine_before_first_append(tmp_path, keys, capsys):
    import ledger.__main__ as cli
    from ledger.backend import detect as _detect

    cli.check_chain_before_append(tmp_path / "ledger.jsonl", keys / "pk.pem", _detect(), tmp_path)
    assert "nothing to verify" in capsys.readouterr().out
