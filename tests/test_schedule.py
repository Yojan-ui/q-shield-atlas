import dataclasses
import itertools
import json
import random

import pytest

from contracts import validate
from contracts.assemble import assemble
from contracts.manifest import sha256_json
from schedule.__main__ import build_section
from schedule.baselines import fcfs, greedy, run_baselines
from schedule.milp import JOB_ID_REASON, optimize
from schedule.problem import Asset, Problem, Scenario, check_feasible, evaluate, load_problem
from schedule.sensitivity import horizon_for


def make_problem(assets, capacity=10, horizon=10, objective="expected", scenarios=None):
    return Problem(
        assets=tuple(assets),
        scenarios=tuple(scenarios or [Scenario("Z2030", 2030, 0.5), Scenario("Z2032", 2032, 0.5)]),
        start_year=2027.0,
        capacity_days_per_week=capacity,
        horizon_weeks=horizon,
        objective=objective,
    )


def random_problem(seed, n=7, objective="expected"):
    rng = random.Random(seed)
    assets = []
    for i in range(n):
        deps = tuple(f"a{j}" for j in range(i) if rng.random() < 0.2)
        assets.append(
            Asset(f"a{i}", f"a{i}", rng.choice([0.5, 2.5, 3.0, 5.0, 10.0]), rng.randint(1, 6), rng.randint(1, 10), deps)
        )
    return make_problem(assets, capacity=8, horizon=4, objective=objective)


# ---------- offline: model data, evaluator, baselines ----------

def test_demo_inventory_loads():
    p = load_problem()
    assert len(p.assets) == 16
    assert [s.year for s in p.scenarios] == [2030, 2032, 2035]


@pytest.mark.parametrize(
    "assets, match",
    [
        ([Asset("a", "a", 1, 1, 1, ("b",)), Asset("b", "b", 1, 1, 1, ("a",))], "cycle"),
        ([Asset("a", "a", 1, 1, 1, ("zzz",))], "unknown"),
        ([Asset("a", "a", 1, 99, 1)], "capacity"),
    ],
)
def test_invalid_problems_rejected(assets, match):
    with pytest.raises(ValueError, match=match):
        make_problem(assets)


def test_exposure_formula_by_hand():
    # X=4y, finish week 26 (0.5y), Z=2030 from 2027 (3y): 4 + 0.5 - 3 = 1.5 years; Z=2032: 0
    p = make_problem([Asset("a", "a", 4.0, 1, 2.0)])
    s = evaluate(p, {"a": 26}, "hand")
    assert s["per_scenario"][0]["exposure_years"] == pytest.approx(1.5)
    assert s["per_scenario"][0]["weighted_exposure"] == pytest.approx(3.0)
    assert s["per_scenario"][1]["exposure_years"] == 0.0
    assert s["expected_weighted"] == pytest.approx(1.5)
    assert s["worst_case_weighted"] == pytest.approx(3.0)


def test_feasibility_checker_catches_violations():
    p = make_problem([Asset("a", "a", 1, 6, 1), Asset("b", "b", 1, 6, 1, ("a",))])
    assert check_feasible(p, {"a": 1, "b": 2}) == []
    assert any("capacity" in e for e in check_feasible(p, {"a": 1, "b": 1}))
    assert any("dependency" in e for e in check_feasible(p, {"a": 2, "b": 1}))


@pytest.mark.parametrize("seed", range(5))
def test_baselines_feasible(seed):
    for p in (load_problem(), random_problem(seed)):
        for plan in (fcfs(p), greedy(p)):
            assert check_feasible(p, plan) == []


# ---------- QpiAI Opt MILP ----------

@pytest.mark.parametrize("objective", ["expected", "robust"])
def test_milp_feasible_and_never_worse_than_baselines(opt_client, objective):
    p = dataclasses.replace(load_problem(), objective=objective)
    base = run_baselines(p)
    opt, runs = optimize(p, opt_client, horizon_for(p, base))
    assert check_feasible(p, opt["completion_week"]) == []
    key = "expected_weighted" if objective == "expected" else "worst_case_weighted"
    for b in base.values():
        assert opt[key] <= b[key] + 1e-6
    assert all(r["guarantee"] == "global_optimum" for r in runs)


@pytest.mark.parametrize("seed", range(4))
def test_milp_never_worse_on_random_instances(opt_client, seed):
    p = random_problem(seed)
    base = run_baselines(p)
    opt, _ = optimize(p, opt_client, horizon_for(p, base))
    assert check_feasible(p, opt["completion_week"]) == []
    for b in base.values():
        assert opt["expected_weighted"] <= b["expected_weighted"] + 1e-6


@pytest.mark.parametrize("objective", ["expected", "robust"])
def test_milp_matches_brute_force(opt_client, objective):
    p = make_problem(
        [
            Asset("a", "a", 3.0, 4, 5),
            Asset("b", "b", 3.2, 3, 9, ("a",)),
            Asset("c", "c", 5.4, 5, 2),
            Asset("d", "d", 3.1, 2, 7),
        ],
        capacity=6,
        horizon=4,
        objective=objective,
        scenarios=[Scenario("Z2030", 2030, 0.7), Scenario("Z2031", 2031, 0.3)],
    )
    key = "expected_weighted" if objective == "expected" else "worst_case_weighted"
    best = min(
        evaluate(p, plan, "bf")[key]
        for ks in itertools.product(range(1, 5), repeat=4)
        if not check_feasible(p, plan := dict(zip("abcd", ks)), 4)
    )
    opt, _ = optimize(p, opt_client, 4)
    assert opt[key] == pytest.approx(best, abs=1e-6)


def test_solver_runs_are_logged(opt_client, tmp_path):
    p = load_problem()
    opt, runs = optimize(p, opt_client, horizon_for(p, run_baselines(p)), tmp_path)
    assert [r["stage"] for r in runs] == ["schedule.milp.expected.expected", "schedule.milp.expected.tiebreak"]
    for r in runs:
        assert r["provider"] == "qpiai-opt" and r["mode"] == "local"
        assert r["job_id"] is None and r["job_id_reason"] == JOB_ID_REASON
        d = tmp_path / r["run_id"]
        assert json.loads((d / "manifest.json").read_text()) == r
        assert sha256_json(json.loads((d / "solver_output.json").read_text())) == r["output_sha256"]
        assert sha256_json(json.loads((d / "inputs.json").read_text())) == r["inputs_sha256"]


def test_section_assembles_into_valid_results(opt_client, tmp_path):
    p = load_problem()
    section = build_section(p, opt_client, tmp_path / "runs", with_sensitivity=False)
    (tmp_path / "schedule.json").write_text(json.dumps(section))
    results = assemble(tmp_path)
    validate("results", results)
    assert results["handshake_evidence"] is None and results["ledger_root"] is None
    for b in results["baselines"].values():
        assert results["exposure"]["expected_weighted"] <= b["expected_weighted"] + 1e-6
    # avoided numbers are recomputable from the plans in the same document
    for row, b, o in zip(results["avoided"]["vs_greedy"], results["baselines"]["greedy"]["per_scenario"], results["exposure"]["per_scenario"]):
        assert row["exposure_years_avoided"] == pytest.approx(b["exposure_years"] - o["exposure_years"])


def test_remaining_series_starts_at_total_and_ends_at_zero():
    from schedule.problem import remaining_series

    p = load_problem()
    plan = greedy(p)
    total = evaluate(p, plan, "g")
    series = remaining_series(p, plan, max(plan.values()) + 2)
    for s, sc in zip(series, total["per_scenario"]):
        pts = [x["exposure_years"] for x in s["points"]]
        assert pts[0] == pytest.approx(sc["exposure_years"])
        assert pts[-1] == 0.0 and pts[max(plan.values())] == 0.0
        assert all(a >= b - 1e-12 for a, b in zip(pts, pts[1:]))  # never increases
