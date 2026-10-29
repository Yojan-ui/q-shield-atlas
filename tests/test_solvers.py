"""solvers/: one interface for every subproblem; each solver can be swapped and is checked against the exact optimum.

QAOA on simulators. A measured cross-check against the exact optimum. No quantum advantage claimed.
"""

import json
import os
import random
from pathlib import Path

import pytest

import solvers
from qaoa.qubo import build, exact_optimum

REPO = Path(__file__).resolve().parent.parent
SAMPLE = json.loads((REPO / "tests" / "fixtures" / "results_sample.json").read_text())
CFG = json.loads((REPO / "config" / "qaoa.json").read_text())
FAST = {**CFG, "restarts": 2, "shots": 512}


@pytest.fixture(scope="module")
def q():
    return build(SAMPLE, CFG)


def test_defaults_come_from_config():
    cfg = json.loads((REPO / "config" / "solvers.json").read_text())["default"]
    assert cfg == {"migration_schedule": "milp", "link_cutover": "qaoa"}
    assert solvers.default_solver("link_cutover") == "qaoa"


def test_exact_matches_the_brute_force_reference(q):
    s = solvers.solve("link_cutover", q, "exact")
    ref = exact_optimum(q)
    assert s.feasible and s.objective == pytest.approx(ref["objective"])
    assert sorted(a for a, b in s.assignment.items() if b) == sorted(ref["assets"])
    assert s.size["variables"] == q.n and s.size["statevector_amplitudes"] == 2**q.n and s.runtime_s >= 0


@pytest.mark.parametrize("p", [1, 2])
def test_qaoa_and_hybrid_never_beat_the_optimum_and_hybrid_never_loses_to_qaoa(q, p):
    best = solvers.solve("link_cutover", q, "exact").objective
    qa = solvers.solve("link_cutover", q, "qaoa", p=p, cfg=FAST)
    hy = solvers.solve("link_cutover", q, "hybrid", p=p, cfg=FAST)
    assert hy.feasible  # repair always returns a feasible selection
    assert hy.objective >= best - 1e-9
    if qa.feasible:
        assert qa.objective >= best - 1e-9 and hy.objective <= qa.objective + 1e-9
    assert qa.record["metrics"]["shots"] == FAST["shots"]


def test_repair_is_always_feasible(q):
    from solvers.cutover import repair

    rnd = random.Random(3)
    for _ in range(300):
        x = repair(q, [rnd.randint(0, 1) for _ in range(q.m)])
        assert q.feasible(x)


def test_repair_cannot_add_to_a_full_optimum(q):
    from solvers.cutover import repair

    ref = exact_optimum(q)
    x = [int(a in ref["assets"]) for a in q.assets]
    assert q.objective(repair(q, x)) == pytest.approx(ref["objective"])


def test_unsupported_pairs_say_why():
    for name in ("qaoa", "exact", "hybrid"):
        with pytest.raises(solvers.Unsupported) as e:
            solvers.solve("migration_schedule", {}, name)
        assert str(e.value)
    with pytest.raises(ValueError):
        solvers.solve("nope", {}, "exact")


def test_registry_is_one_interface():
    for sub, table in solvers.registry().items():
        assert sub in solvers.SUBPROBLEMS and table
    assert set(solvers.registry()["link_cutover"]) == {"exact", "qaoa", "hybrid", "milp"}
    assert set(solvers.registry()["migration_schedule"]) == {"milp", "fcfs", "greedy"}


def test_baselines_through_the_interface():
    from schedule.problem import load_problem

    p = load_problem()  # config/assumptions.json + the (synthetic) mock-bank inventory
    a = solvers.solve("migration_schedule", {"problem": p}, "fcfs")
    b = solvers.solve("migration_schedule", {"problem": p}, "greedy")
    assert a.feasible and b.feasible and set(a.assignment) == {x.id for x in p.assets}


@pytest.mark.skipif(not os.environ.get("QPIAI_OPT_API_KEY"), reason="QpiAI Opt local solves verify the API key online")
def test_milp_on_the_cutover_window_equals_the_exact_optimum(q):
    s = solvers.solve("link_cutover", q, "milp")
    assert s.feasible and s.objective == pytest.approx(exact_optimum(q)["objective"], abs=1e-6)
    assert s.record["job_id"] is None and s.record["job_id_reason"]
