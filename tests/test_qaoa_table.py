"""The QAOA display table: rows that did not run say why; a later QCloud success needs no code change."""

import copy
import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator, ValidationError

from qaoa.__main__ import run
from qaoa.table import build_table, short_reason
from tests.test_qaoa import CFG, schedule_doc

REPO = Path(__file__).resolve().parent.parent
SUBSCRIPTION_ERROR = ("JobManagerError: Error during QASM job submission: Bad Request (400) when submitting job.\n"
                      "Server response: {'error': 'Failed to create job: an active subscription is required to run jobs'}")


def qaoa_validator():
    schema = json.loads((REPO / "contracts" / "results.schema.json").read_text())
    return Draft202012Validator({"$defs": schema["$defs"], "$ref": "#/$defs/qaoa"})


@pytest.fixture(scope="module")
def local_section(tmp_path_factory):
    cfg = {**CFG, "reps": [1, 2, 3], "restarts": 1, "cobyla_maxiter": 30, "shots": 256}
    return run(schedule_doc(), cfg, tmp_path_factory.mktemp("runs"))


def with_failed_qcloud(section):
    s = copy.deepcopy(section)
    s["qcloud"] = {"requested": True, "device": "QpiAI-QSV-Simulator", "jobs": [
        {"p": 1, "status": "failed", "job_id": None, "credits_used": None, "error": SUBSCRIPTION_ERROR},
        {"p": 2, "status": "skipped", "job_id": None, "credits_used": None, "error": f"earlier QCloud failure: {SUBSCRIPTION_ERROR}"},
        {"p": 3, "status": "skipped", "job_id": None, "credits_used": None, "error": f"earlier QCloud failure: {SUBSCRIPTION_ERROR}"},
    ]}
    return s


def with_successful_qcloud(section):
    """Simulated success (test fixture only): QCloud rows shaped exactly like qaoa/__main__.py writes them."""
    s = copy.deepcopy(section)
    s["qcloud"] = {"requested": True, "device": "QpiAI-QSV-Simulator",
                   "jobs": [{"p": p, "status": "ok", "job_id": f"job-{p}", "credits_used": 1, "error": None} for p in (1, 2, 3)]}
    for local in [r for r in section["runs"] if r["source"] == "local"]:
        s["runs"].append({**local, "source": "qcloud", "backend": "QpiAI-QSV-Simulator", "job_ids": [f"job-{local['p']}"]})
    return s


def rows(table, source):
    return {r["p"]: r for r in table if r["source"] == source}


def finish(section, ledger_index):
    s = copy.deepcopy(section)
    s["ledger_index"] = ledger_index
    s["table"] = build_table(s, ledger_index)
    return s


def test_skipped_rows_say_why_with_ledger_index(local_section):
    s = finish(with_failed_qcloud(local_section), 7)
    cloud = rows(s["table"], "qcloud")
    assert cloud[2]["status_text"] == "skipped: no QCloud subscription (attempt logged, ledger #7)"
    assert cloud[3]["status_text"] == "skipped: no QCloud subscription (attempt logged, ledger #7)"
    assert cloud[1]["status_text"] == "failed: no QCloud subscription (attempt logged, ledger #7)"
    assert all(r["metrics"] is None and r["shots"] is None and r["job_ids"] == [] for r in cloud.values())
    qaoa_validator().validate(s)


def test_before_signing_points_at_the_run_directory(local_section):
    s = finish(with_failed_qcloud(local_section), None)
    text = rows(s["table"], "qcloud")[2]["status_text"]
    assert text.startswith("skipped: no QCloud subscription (attempt logged in runs/")
    assert "not yet signed into the ledger" in text


def test_local_only_run_marks_qcloud_not_requested(local_section):
    s = finish(local_section, 3)
    cloud = rows(s["table"], "qcloud")
    assert {r["status"] for r in cloud.values()} == {"not_requested"}
    assert all("opt-in" in r["status_text"] for r in cloud.values())
    qaoa_validator().validate(s)


def test_later_qcloud_success_renders_through_the_same_path(local_section):
    s = finish(with_successful_qcloud(local_section), 9)
    cloud = rows(s["table"], "qcloud")
    for p, r in cloud.items():
        assert r["status"] == "ok" and r["status_text"] is None
        assert r["job_ids"] == [f"job-{p}"] and r["metrics"]["shots"] > 0
    assert len(s["table"]) == 3 * 2 + 1  # (local, qcloud) per p + one random baseline
    qaoa_validator().validate(s)


def test_table_rows_cover_every_p_and_source(local_section):
    table = build_table(with_failed_qcloud(local_section), 7)
    assert sorted((r["p"] or 0, r["source"]) for r in table) == sorted(
        [(p, src) for p in (1, 2, 3) for src in ("local", "qcloud")] + [(0, "random")])


@pytest.mark.parametrize("mutate", [
    lambda r: r.update(metrics={"shots": 0}),           # a non-ok row may not carry (zero) metrics
    lambda r: r.update(status_text=None),               # a non-ok row must say why
    lambda r: r.update(status_text=""),
])
def test_schema_rejects_blank_or_zero_rows(local_section, mutate):
    s = finish(with_failed_qcloud(local_section), 7)
    mutate(next(r for r in s["table"] if r["source"] == "qcloud" and r["p"] == 2))
    with pytest.raises(ValidationError):
        qaoa_validator().validate(s)


def test_schema_rejects_ok_qcloud_row_without_job_id(local_section):
    s = finish(with_successful_qcloud(local_section), 9)
    next(r for r in s["table"] if r["source"] == "qcloud")["job_ids"] = []
    with pytest.raises(ValidationError):
        qaoa_validator().validate(s)


@pytest.mark.parametrize("error, expected", [
    (SUBSCRIPTION_ERROR, "no QCloud subscription"),
    ("JobManagerError: Experiment 'x' not found. Please create the experiment first.", "QCloud experiment not found"),
    ("RuntimeError: boom", "RuntimeError: boom"),
    (None, "unknown error"),
])
def test_short_reason(error, expected):
    assert short_reason(error) == expected
