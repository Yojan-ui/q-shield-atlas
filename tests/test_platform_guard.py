"""Paid QpiAI platform submissions are opt-in, announced, logged and capped."""

import json
from datetime import date, timedelta

import pytest

from schedule import __main__ as cli
from schedule import milp
from schedule.platform_guard import FORBID_ENV, PlatformBudget, PlatformRefused
from schedule.problem import load_problem


def _seed_log(path, n_today, n_yesterday=0):
    today = date.today().isoformat()  # guard uses UTC; tests run near enough for a seed
    rows = [{"event": "submit", "date": today, "n": 1} for _ in range(n_today)]
    rows += [{"event": "submit", "date": (date.today() - timedelta(days=1)).isoformat(), "n": 1}] * n_yesterday
    path.write_text("".join(json.dumps(r) + "\n" for r in rows))


@pytest.fixture
def allow_platform(monkeypatch):
    monkeypatch.delenv(FORBID_ENV, raising=False)


def test_pytest_forbids_platform(tmp_path):
    with pytest.raises(PlatformRefused, match=FORBID_ENV):
        PlatformBudget(tmp_path / "log").check(1)


def test_daily_limit_refuses_past_ten(tmp_path, allow_platform, monkeypatch):
    monkeypatch.setattr("schedule.platform_guard._today", lambda: date.today().isoformat())
    log = tmp_path / "platform_jobs.log"
    _seed_log(log, n_today=9, n_yesterday=5)
    budget = PlatformBudget(log)
    assert budget.used_today() == 9
    budget.check(1)
    with pytest.raises(PlatformRefused, match="--allow-more"):
        budget.check(2)
    PlatformBudget(log, allow_more=True).check(2)


def test_reserve_announces_and_logs(tmp_path, allow_platform, capsys):
    budget = PlatformBudget(tmp_path / "platform_jobs.log")
    budget.reserve(1, "r" * 32, "schedule.milp.expected.expected", tmp_path / "run")
    assert "Submitting 1 QpiAI jobs" in capsys.readouterr().out
    assert "Submitting 1 QpiAI jobs" in (tmp_path / "run" / "platform_submit.log").read_text()
    assert budget.used_today() == 1


def test_cli_defaults_to_local(monkeypatch, tmp_path):
    seen = {}

    def fake_build(problem, client, run_dir, with_sens, mode, budget):
        seen.update(mode=mode, budget=budget)
        raise SystemExit(0)

    monkeypatch.setattr(cli, "build_section", fake_build)
    monkeypatch.setattr(cli, "Client", lambda api_key: None)
    monkeypatch.setenv("QPIAI_OPT_API_KEY", "unused")
    with pytest.raises(SystemExit):
        cli.main(["--runs", str(tmp_path)])
    assert seen == {"mode": "local", "budget": None}


def test_cli_platform_refused_under_pytest_before_any_solve(monkeypatch, tmp_path):
    monkeypatch.setattr(cli, "build_section", lambda *a: pytest.fail("must refuse before solving"))
    with pytest.raises(PlatformRefused):
        cli.main(["--platform", "--runs", str(tmp_path)])


def test_platform_mode_never_reaches_solver_when_forbidden(monkeypatch, tmp_path):
    calls = []
    monkeypatch.setattr(milp, "solve", lambda *a, **kw: calls.append(kw.get("mode", "local")))
    budget = PlatformBudget(tmp_path / "platform_jobs.log")
    with pytest.raises(PlatformRefused):
        milp.solve_schedule(load_problem(), None, 8, tmp_path, mode="platform", budget=budget)
    assert calls == []
    assert not (tmp_path / "platform_jobs.log").exists()


def test_platform_failure_falls_back_labelled_and_stops_submitting(opt_client, monkeypatch, tmp_path):
    """Real local solves; only the platform call is stubbed to fail (no paid job is sent)."""
    monkeypatch.delenv(FORBID_ENV)
    real_solve = milp.solve

    def solve(model, mode="local", **kw):
        if mode == "platform":
            raise RuntimeError("stub: no active storage quota")
        return real_solve(model, **kw)

    monkeypatch.setattr(milp, "solve", solve)
    budget = PlatformBudget(tmp_path / "platform_jobs.log")
    p = load_problem()
    weeks, runs = milp.solve_schedule(p, opt_client, 8, tmp_path, mode="platform", budget=budget)
    assert [r["solver"] for r in runs] == [milp.SOLVER_FALLBACK, milp.SOLVER_SKIPPED]
    assert all("stub: no active storage quota" in r["fallback_reason"] for r in runs)
    assert all(r["job_id"] is None and r["comparison"] is None for r in runs)
    assert budget.used_today() == 1  # second stage did not attempt a submission
