"""out/report.html: numbers from results.json only, 'not yet run' for gaps, offline, self-hash, signed + verified."""

import copy
import json
import re
from pathlib import Path

import pytest

from atlas.report import NOT_YET_RUN, QAOA_LABEL, build_html, finalize, self_hash_ok
from tests.test_viz import numbers_in

REPO = Path(__file__).resolve().parent.parent
SAMPLE = json.loads((REPO / "tests" / "fixtures" / "results_sample.json").read_text())
SECTIONS = ["1. Summary", "2. Inventory (detect)", "3. Migration plan (schedule)", "4. Handshake evidence", "5. Waves &amp; rollback",
            "6. Signed ledger", "7. QAOA cross-check", "8. Assumptions &amp; limits", "9. Reproduce"]


def html_for(results, tmp_path):
    text, _ = finalize(build_html(results, tmp_path / "runs", commit="test"))
    return text


def section(text, title):
    start = text.index(f"<h2>{title}</h2>")
    end = text.find("<section>", start)
    return text[start:end if end != -1 else len(text)]


def test_every_number_in_the_report_is_a_value_in_results(tmp_path):
    text = html_for(SAMPLE, tmp_path)
    values = re.findall(r'class="n" data-v="([^"]+)"', text)
    assert len(values) > 50
    present = numbers_in(SAMPLE)
    for v in values:
        assert float(v) in present, v


def test_numbers_carry_provenance_tags(tmp_path):
    text = html_for(SAMPLE, tmp_path)
    tagged = re.findall(r'class="n" data-v="[^"]+">[^<]*</span><sup class="prov">([^<]+)</sup>', text)
    assert tagged and all(t.strip() for t in tagged)
    assert f"run {SAMPLE['qaoa']['run_id'][:8]}" in text and SAMPLE["detect"]["run_id"][:8] in text


def test_all_sections_present_with_labels(tmp_path):
    text = html_for(SAMPLE, tmp_path)
    for title in SECTIONS:
        assert f"<h2>{title}</h2>" in text
    assert QAOA_LABEL in text and "No quantum advantage claimed" in text
    assert "failed: no QCloud subscription" in text or "not run: QCloud sampling is opt-in" in text
    assert "python -m ledger verify" in text
    assert "risk-weighted" in text and "unweighted" in text


@pytest.mark.parametrize("results", [None, {"schema_version": "1.0", "generated_at": "2026-10-28T00:00:00Z"}])
def test_missing_sections_show_not_yet_run(results, tmp_path):
    text = html_for(results, tmp_path)
    for title in SECTIONS[1:8]:
        assert NOT_YET_RUN in section(text, title), title
    assert 'class="n"' not in text  # no numbers invented
    assert "FAIL" in section(text, "1. Summary")


def test_qcloud_rows_show_status_text_not_numbers(tmp_path):
    r = copy.deepcopy(SAMPLE)
    for row in r["qaoa"]["table"]:
        if row["source"] == "qcloud":
            row.update(status="skipped", status_text="skipped: no QCloud subscription (attempt logged, ledger #7)", metrics=None)
    q = section(html_for(r, tmp_path), "7. QAOA cross-check")
    assert q.count("skipped: no QCloud subscription (attempt logged, ledger #7)") == 3


def test_report_has_no_external_urls_or_remote_assets(tmp_path):
    text = html_for(SAMPLE, tmp_path)
    assert not re.search(r"https?://", text)
    assert not re.search(r"<(script|link|img)[^>]+(src|href)=", text)
    assert "<style>" in text and "<script>" in text  # inline only


def test_self_hash_recomputes_and_detects_tampering(tmp_path):
    text = html_for(SAMPLE, tmp_path)
    assert self_hash_ok(text)
    assert not self_hash_ok(text.replace("Q-Shield Atlas</h1>", "Q-Shield Atlas!</h1>"))


def test_print_css_present(tmp_path):
    text = html_for(SAMPLE, tmp_path)
    assert "@media print" in text and "beforeprint" in text


def test_build_signs_report_and_ledger_still_verifies(tmp_path):
    """End to end in a temp repo: build -> sign as a ledger entry -> re-anchor -> verify."""
    from atlas.build_report import build_and_sign
    from contracts.assemble import assemble
    from ledger.backend import detect
    from ledger.ingest import ledger_summary
    from ledger.log import Ledger, read_entries

    backend = detect()
    keys, out, runs = tmp_path / "keys", tmp_path / "out", tmp_path / "runs"
    backend.generate(keys / "sk.pem", keys / "pk.pem")
    (runs / "r0").mkdir(parents=True)
    (runs / "r0" / "manifest.json").write_text('{"run": 0}')
    ledger = Ledger(out / "ledger.jsonl", backend, keys / "sk.pem", keys / "pk.pem", tmp_path)
    ledger.append("test.run", runs / "r0" / "manifest.json")
    (out / "ledger.json").write_text(json.dumps(ledger_summary(ledger, tmp_path)))
    later = ("detect", "handshake_evidence", "gates", "qaoa", "ledger", "ledger_root", "ledger_verification", "generated_at", "schema_version")
    (out / "schedule.json").write_text(json.dumps({k: v for k, v in SAMPLE.items() if k not in later}))
    (out / "results.json").write_text(json.dumps(assemble(out)))

    res = build_and_sign(out, runs, repo=tmp_path, private_key=keys / "sk.pem", public_key=keys / "pk.pem")
    assert res["ledger_entry"] == 1 and res["verify_rc"] == 0
    entries = read_entries(out / "ledger.jsonl")
    assert entries[-1]["type"] == "report.html" and entries[-1]["payload_ref"] == f"runs/{res['run_id']}/report.html"
    results = json.loads((out / "results.json").read_text())
    assert results["ledger"]["entry_count"] == 2 and results["ledger_verification"]["ok"]
    assert self_hash_ok((out / "report.html").read_text())
