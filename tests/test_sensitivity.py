"""Shelf life, risk weight and effort are assumptions; check conclusions survive +/-20%."""

import pytest

from schedule.baselines import run_baselines
from schedule.milp import optimize
from schedule.problem import load_problem, scale
from schedule.sensitivity import horizon_for, run_sensitivity


def test_scale_only_touches_requested_parameter():
    p = load_problem()
    q = scale(p, shelf=1.2)
    for a, b in zip(p.assets, q.assets):
        assert b.shelf_life_years == pytest.approx(1.2 * a.shelf_life_years)
        assert (b.risk_weight, b.effort_days) == (a.risk_weight, a.effort_days)


@pytest.fixture(scope="module")
def rows(opt_client):
    return run_sensitivity(load_problem(), opt_client)


def test_sensitivity_covers_every_assumption(rows):
    assert {(r["parameter"], r["factor"]) for r in rows} == {
        (p, f) for p in ("shelf", "risk", "effort") for f in (0.8, 1.2)
    }


def test_optimized_never_worse_under_perturbation(rows):
    for r in rows:
        assert r["optimized_expected"] <= r["fcfs_expected"] + 1e-6, r
        assert r["optimized_expected"] <= r["greedy_expected"] + 1e-6, r


def test_optimal_exposure_monotone_in_shelf_life(rows, opt_client):
    # Longer shelf life can only increase every asset's exposure for any fixed plan,
    # so the optimum must be non-decreasing in the shelf-life factor.
    p = load_problem()
    nominal, _ = optimize(p, opt_client, horizon_for(p, run_baselines(p)))
    by_factor = {r["factor"]: r["optimized_expected"] for r in rows if r["parameter"] == "shelf"}
    assert by_factor[0.8] <= nominal["expected_weighted"] + 1e-6 <= by_factor[1.2] + 2e-6
