"""data/real_banks: deterministic selection rules, documented columns, provenance on every row."""

import csv
import hashlib
import json
from pathlib import Path

from tools.scan_banks import COMMIT, MAX_HOSTS, SCAN_COLS, TARGET_COLS, excluded, select_targets

REPO = Path(__file__).resolve().parent.parent
D = REPO / "data" / "real_banks"


def rows(p):
    with p.open(newline="") as fh:
        return list(csv.DictReader(fh))


def test_exclusion_rules():
    for bad in ("uat.x.bank.in", "netbanking-dev.x.bank.in", "cug.x.bank.in", "admin2.x.bank.in", "sit.x.bank.in", "preprod.x.bank.in"):
        assert excluded(bad), bad
    for ok in ("www.x.bank.in", "netbanking.x.bank.in", "visitbank.bank.in"):
        assert not excluded(ok), ok


def test_selection_is_capped_and_public_only():
    src = [{"domain": f"{s}{b}.bank.in", "https_works": "True", "status_code": "200"} for b in ("a", "b", "c") for s in ("", "www.", "netbanking.", "uat.")]
    src += [{"domain": "www.z.bank.in", "https_works": "False", "status_code": ""}]
    t = select_targets(src)
    assert {x["endpoint"] for x in t} <= {"apex", "www", "netbanking"} and len(t) == 9
    assert not any(x["bank"] == "z" for x in t)


def test_committed_targets_and_scan_match_the_rules_and_dictionary():
    t = rows(D / "targets.csv")
    assert len(t) <= MAX_HOSTS and all(r["dataset_commit"] == COMMIT for r in t)
    assert not any(excluded(r["host"]) for r in t)
    per_bank = {}
    for r in t:
        per_bank[r["bank"]] = per_bank.get(r["bank"], 0) + 1
    assert max(per_bank.values()) <= 3
    scan = sorted(D.glob("scan_*.csv"))[-1]
    s = rows(scan)
    assert list(s[0]) == SCAN_COLS and list(t[0]) == TARGET_COLS
    assert {r["host"] for r in s} == {r["host"] for r in t}  # one handshake per target
    assert all(r["outcome"] in ("hybrid_pq", "classical", "unreachable") for r in s)
    for r in s:
        if r["outcome"] == "hybrid_pq":
            assert "MLKEM" in r["negotiated_group"] and r["kex_quantum_vulnerable"] == "false"
        elif r["outcome"] == "classical":
            assert r["kex_quantum_vulnerable"] == "true" and len(r["transcript_sha256"]) == 64
    dd = (D / "DATA_DICTIONARY.md").read_text()
    assert all(c in dd for c in SCAN_COLS + TARGET_COLS) and "planned migration — simulation" in dd


def test_manifest_hashes_the_committed_files():
    man = json.loads(sorted(D.glob("scan_*.manifest.json"))[-1].read_text())
    assert man["scan_sha256"] == hashlib.sha256((REPO / man["scan_csv"]).read_bytes()).hexdigest()
    assert man["targets_sha256"] == hashlib.sha256((D / "targets.csv").read_bytes()).hexdigest()
    assert man["probe"] == {"port": 443, "timeout_s": 8, "concurrency": 4, "handshakes_per_host": 1, "http_requests": 0}
    assert man["dataset"]["commit"] == COMMIT and man["dataset"]["license"] == "CC0 1.0"
    assert sum(man["counts"].values()) == man["hosts"]
