"""Time estimate from the inputs + the user's threshold: flagged when the estimate exceeds it."""

import json
import math
from pathlib import Path

import pytest

from atlas_web.estimate import estimate, parse_threshold

REPO = Path(__file__).resolve().parent.parent
SAMPLE = json.loads((REPO / "tests" / "fixtures" / "results_sample.json").read_text())


def test_estimate_comes_from_the_plan_and_the_assumptions():
    e = estimate(SAMPLE)
    assert e["estimate_weeks"] == SAMPLE["exposure"]["makespan_weeks"]
    cap = SAMPLE["assumptions"]["capacity_days_per_week"]
    assert e["lower_bound_weeks"] == math.ceil(sum(a["effort_days"] for a in SAMPLE["assets"]) / cap - 1e-9)
    assert e["lower_bound_weeks"] <= e["estimate_weeks"]  # no plan beats the capacity bound
    assert "assumption" in e["label"] and e["exceeded"] is None
    assert [w["week"] for w in e["per_wave"]] == [w["week"] for w in SAMPLE["waves"]]
    assert all(w["effort_days"] <= w["capacity_days"] + 1e-9 for w in e["per_wave"])  # the plan respects weekly capacity


def test_threshold_flags():
    w = SAMPLE["exposure"]["makespan_weeks"]
    assert estimate(SAMPLE, w)["exceeded"] is False
    over = estimate(SAMPLE, w - 1)
    assert over["exceeded"] is True and over["over_by_weeks"] == 1
    assert estimate(SAMPLE, w + 5)["over_by_weeks"] == 0


def test_not_run_and_nothing_to_migrate():
    assert estimate(None)["available"] is False and estimate(None)["status_text"] == "not yet run"
    assert estimate({**SAMPLE, "assets": []})["status_text"] == "nothing to migrate"


@pytest.mark.parametrize("bad", ["x", 0, -3, 2.5, 521])
def test_threshold_validation(bad):
    with pytest.raises(ValueError):
        parse_threshold(bad)


def test_api(monkeypatch, tmp_path):
    from .atlas_web_helpers import PASSWORD, Client, start_server

    srv = start_server(monkeypatch, tmp_path)
    try:
        srv.app.store.create_user("ops", PASSWORD, "operator")
        c = Client(srv.server_address[1])
        assert c.login("ops")[0] == 200
        status, e = c.get("/api/workspaces/demo/estimate?threshold_weeks=1")
        assert status == 200 and e["available"] and e["exceeded"] == (e["estimate_weeks"] > 1)
        assert c.get("/api/workspaces/demo/estimate?threshold_weeks=abc")[0] == 422
        assert c.request("PUT", "/api/workspaces/demo/estimate", {"threshold_weeks": 4})[0] == 403  # read-only snapshot
        assert c.post("/api/workspaces", {"id": "t1", "name": "t1", "template": "mock_bank"})[0] == 201
        status, e = c.request("PUT", "/api/workspaces/t1/estimate", {"threshold_weeks": 4})
        assert status == 200 and e["saved_threshold_weeks"] == 4 and e["available"] is False  # not yet run
        assert c.get("/api/workspaces/t1/estimate")[1]["threshold_weeks"] == 4
    finally:
        srv.shutdown()
