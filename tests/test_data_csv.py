"""data/: real and synthetic CSVs are separate, labelled, documented, and traceable to their sources."""

import csv
import hashlib
import json
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
DATA = REPO / "data"


def rows(name):
    with (DATA / name).open(newline="") as fh:
        return list(csv.DictReader(fh))


def dictionary_columns(section):
    text = (DATA / "DATA_DICTIONARY.md").read_text().split(f"## {section}")[1].split("\n## ")[0]
    return [ln.split("|")[1].strip() for ln in text.splitlines() if ln.startswith("| ") and not ln.startswith("| Column")]


def test_every_column_is_in_the_dictionary_in_order():
    from tools.export_csv import REAL_COLUMNS, SYNTH_COLUMNS

    assert dictionary_columns("real_crypto_observations.csv") == REAL_COLUMNS == list(rows("real_crypto_observations.csv")[0])
    assert dictionary_columns("SYNTHETIC_mock_bank_assets.csv") == SYNTH_COLUMNS


def test_synthetic_is_labelled_and_never_in_the_real_file():
    synth = rows("SYNTHETIC_mock_bank_assets.csv")
    assert synth and all(r["synthetic"] == "true" for r in synth)
    mock = json.loads((REPO / "schedule" / "data" / "mock_bank_assets.json").read_text())
    assert "Fictional" in mock["label"] and [r["asset_id"] for r in synth] == [a["id"] for a in mock["assets"]]
    real = rows("real_crypto_observations.csv")
    assert not {r["source_name"] for r in real} & {r["asset_id"] for r in synth}
    assert all("mock" not in (r["source_url"] + r["file"]) for r in real)
    assert all(not r["endpoint"].startswith("127.") for r in real)  # lab services are not a dataset


def test_real_rows_have_provenance():
    real = rows("real_crypto_observations.csv")
    pinned = {r["name"]: r for r in json.loads((REPO / "detect" / "real_repos.json").read_text())["repos"]}
    for r in real:
        assert len(r["run_id"]) == 32 and r["observed_at_utc"].endswith("Z")
        if r["record_type"] == "static_finding":
            assert r["source_commit"] == pinned[r["source_name"]]["commit"] and int(r["line"]) >= 1
        else:
            assert r["record_type"] == "live_handshake" and len(r["handshake_transcript_sha256"]) == 64 and r["key_exchange_group"]
        assert r["quantum_vulnerable"] in {"true", "false", "unknown"}


def test_outputs_match_sources_json():
    src = json.loads((DATA / "sources.json").read_text())
    for o in src["outputs"]:
        assert hashlib.sha256((REPO / o["path"]).read_bytes()).hexdigest() == o["sha256"], o["path"]


def test_regenerates_identically_when_the_sources_are_present():
    from tools.export_csv import REAL_COLUMNS, real_rows

    src = json.loads((DATA / "sources.json").read_text())["real"]
    paths = [REPO / s["path"] for s in src]
    if not all(p.exists() and hashlib.sha256(p.read_bytes()).hexdigest() == s["sha256"] for p, s in zip(paths, src)):
        pytest.skip("source runs (git-ignored out/ and workspace data) not present or regenerated since export")
    scans = [p for p in paths if "real_repos" in p.parts]
    probes = [p for p in paths if p not in scans]
    regen = [{c: str(r.get(c, "")) for c in REAL_COLUMNS} for r in real_rows(scans, probes)]
    assert regen == rows("real_crypto_observations.csv")
