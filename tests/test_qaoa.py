"""QAOA cross-check: QUBO correctness, bit order, reproducibility, metrics, contracts. No QCloud calls."""

import itertools
import json
from pathlib import Path

import numpy as np
import pytest

from qaoa import local_sim, metrics
from qaoa.qubo import build, exact_optimum
from schedule.baselines import run_baselines
from schedule.problem import load_problem

REPO = Path(__file__).resolve().parent.parent
CFG = json.loads((REPO / "config" / "qaoa.json").read_text())
SMALL = {**CFG, "reps": [1], "restarts": 2, "cobyla_maxiter": 60, "shots": 512}


def schedule_doc(problem=None):
    """Solver-free stand-in for out/schedule.json (greedy plan) with the fields qaoa/ reads."""
    p = problem or load_problem()
    plan = run_baselines(p)["greedy"]
    return {
        "assumptions": p.raw_assumptions,
        "scenarios": [{"name": s.name, "year": s.year, "weight": s.weight} for s in p.scenarios],
        "assets": [{"id": a.id, "kind": a.kind, "shelf_life_years": a.shelf_life_years, "effort_days": a.effort_days,
                    "risk_weight": a.risk_weight, "depends_on": list(a.depends_on)} for a in p.assets],
        "exposure": plan,
        "waves": plan["waves"],
    }


@pytest.fixture(scope="module")
def q():
    return build(schedule_doc(), CFG)


# ---------- QUBO ----------

def test_variable_budget_and_penalty_weights(q):
    assert q.m <= CFG["max_assets"] and q.n <= CFG["max_variables"]
    assert q.slack_bits == int(np.ceil(np.log2(q.capacity + 1)))
    assert q.A > sum(abs(v) for v in q.values) and q.B > sum(abs(v) for v in q.values)


@pytest.mark.parametrize("week", [1, 2, 3])
def test_qubo_minimum_equals_brute_force_constrained_optimum(week):
    qq = build(schedule_doc(), {**CFG, "week": week})
    E = qq.energies()
    ex = exact_optimum(qq)
    i = int(np.argmin(E))
    bits = qq.bits_from_index(i)
    assert qq.feasible(bits)
    assert E[i] == pytest.approx(ex["objective"], abs=1e-9)
    assert qq.objective(bits) == pytest.approx(ex["objective"], abs=1e-9)
    assert int(ex["bitstring"], 2) == i or E[int(ex["bitstring"], 2)] == pytest.approx(E[i], abs=1e-9)


def test_infeasible_states_are_never_optimal(q):
    E = q.energies()
    ex = exact_optimum(q)
    idx = np.arange(2**q.n)
    for xi in range(2**q.m):
        x = [(xi >> k) & 1 for k in range(q.m)]
        if q.feasible(x):
            continue
        rows = idx[(idx & ((1 << q.m) - 1)) == xi]  # this asset choice with every slack value
        assert E[rows].min() > 0 >= ex["objective"]  # every slack value: costs more than the empty selection


def test_energy_vector_matches_scalar_energy(q):
    E = q.energies()
    rng = np.random.default_rng(1)
    for i in rng.integers(0, 2**q.n, 50):
        assert E[i] == pytest.approx(q.energy(q.bits_from_index(int(i))))


# ---------- bit order ----------

def test_decode_round_trip_and_explicit_endianness(q):
    s = "0" * (q.n - 1) + "1"  # rightmost character = variable 0
    assert q.decode(s) == [q.assets[0]]
    s = "1" + "0" * (q.n - 1)  # leftmost = highest slack bit, no asset
    assert q.decode(s) == []
    chosen = {q.assets[1], q.assets[-1]}
    assert set(q.decode(q.encode(chosen, slack=5))) == chosen
    assert int(q.encode(chosen, 5), 2) == sum(1 << q.assets.index(a) for a in chosen) + (5 << q.m)


def test_sdk_counts_put_qubit0_rightmost():
    from qpiai_quantum import Circuit
    from qpiai_quantum.simulator import StatevectorSimulator

    c = Circuit(4)
    c.x(0)
    c.measure_all()
    assert StatevectorSimulator().run(c, shots=8).counts == {"0001": 8}


def test_qcloud_circuit_equals_numpy_qaoa_state(q):
    """The circuit sent to QCloud reproduces the local statevector (in-process SDK simulator, no cloud)."""
    from qpiai_quantum.simulator import StatevectorSimulator

    from qaoa.circuit import build_circuit

    E = q.energies()
    sc = local_sim.energy_scale(E)
    g, b = [0.41, 1.3], [0.77, 0.2]
    psi = local_sim.statevector(E / sc, g, b)
    sv = np.asarray(StatevectorSimulator().run(build_circuit(q, g, b, sc), shots=1).statevector, complex).ravel()
    assert abs(np.vdot(psi, sv)) == pytest.approx(1.0, abs=1e-9)


# ---------- local QAOA ----------

def test_p1_local_run_is_reproducible(q):
    E = q.energies()
    a = local_sim.optimise(E, 1, 2, 7, 60)
    b = local_sim.optimise(E, 1, 2, 7, 60)
    assert a["gammas"] == b["gammas"] and a["betas"] == b["betas"]
    assert local_sim.sample(a["probabilities"], 256, 3, q.n) == local_sim.sample(b["probabilities"], 256, 3, q.n)


def test_qaoa_beats_uniform_expected_energy(q):
    E = q.energies()
    assert local_sim.optimise(E, 1, 2, 7, 60)["expected_energy"] < E.mean()


# ---------- metrics ----------

def test_metrics_on_hand_made_samples(q):
    E = q.energies()
    ex = exact_optimum(q)
    empty = q.encode(set(), slack=q.capacity)  # feasible, objective 0, zero penalty
    heavy = q.encode(set(q.assets))  # infeasible: everything selected
    counts = {ex["bitstring"]: 2, empty: 1, heavy: 1}
    m = metrics.compute(q, counts, E, ex)
    assert m["shots"] == 4
    assert m["feasible_fraction"] == pytest.approx(0.75)
    assert m["best_feasible_objective"] == pytest.approx(ex["objective"])
    assert m["approximation_ratio"] == pytest.approx(1.0)
    assert m["p_optimal"] == pytest.approx(0.5) and m["p_optimal_assets"] == pytest.approx(0.5)
    mean = (2 * E[int(ex["bitstring"], 2)] + E[int(empty, 2)] + E[int(heavy, 2)]) / 4
    assert m["mean_energy"] == pytest.approx(mean)
    assert m["energy_ratio"] == pytest.approx((E.max() - mean) / (E.max() - E.min()))


def test_approximation_ratio_sign_convention(q):
    E = q.energies()
    ex = exact_optimum(q)
    one = q.encode({ex["assets"][0]}, slack=0)
    if not q.feasible(q.bits_from_bitstring(one)):
        pytest.skip("single-asset subset infeasible here")
    m = metrics.compute(q, {one: 1}, E, ex)
    assert 0 <= m["approximation_ratio"] < 1  # a worse (less negative) objective -> ratio below 1


def test_compare_flags_large_differences_and_keeps_both():
    a = {"shots": 2048, "feasible_fraction": 0.9, "p_optimal_assets": 0.10, "mean_energy": 1.0, "mean_energy_se": 0.1}
    b = {"shots": 2048, "feasible_fraction": 0.3, "p_optimal_assets": 0.01, "mean_energy": 9.0, "mean_energy_se": 0.1}
    assert metrics.compare(a, b, 4.0)["differs"]
    assert not metrics.compare(a, dict(a), 4.0)["differs"]


# ---------- QCloud is never called from pytest ----------

def test_qcloud_refused_under_pytest_before_any_circuit_runs(monkeypatch, tmp_path):
    from qpiai_quantum import Circuit

    from qaoa import __main__ as cli
    from schedule.platform_guard import PlatformRefused

    monkeypatch.setattr(Circuit, "run", lambda *a, **k: pytest.fail("QCloud circuit submitted from pytest"))
    (tmp_path / "schedule.json").write_text(json.dumps(schedule_doc()))
    with pytest.raises(PlatformRefused):
        cli.main(["--qcloud", "--schedule", str(tmp_path / "schedule.json"), "--runs", str(tmp_path), "--out-dir", str(tmp_path)])


def test_qpu_device_refused():
    from qaoa.qcloud_run import check_device

    with pytest.raises(ValueError):
        check_device("QpiAI-Indus-1", ["QpiAI-Indus-1", "QpiAI-QSV-Simulator"])
    with pytest.raises(ValueError):
        check_device("QpiAI-QTN-Simulator", CFG["qcloud"]["allowed_devices"])
    check_device("QpiAI-QSV-Simulator", CFG["qcloud"]["allowed_devices"])


# ---------- contracts and ledger ----------

def test_qaoa_section_validates_in_results_and_ledger_verifies(tmp_path, opt_client):
    from contracts import validate
    from contracts.assemble import assemble
    from ledger.backend import detect
    from ledger.ingest import ingest
    from ledger.log import Ledger
    from ledger.verify import verify
    from qaoa.__main__ import run
    from schedule.__main__ import build_section

    schedule = build_section(load_problem(), opt_client, tmp_path / "runs", with_sensitivity=False)
    (tmp_path / "schedule.json").write_text(json.dumps(schedule))
    section = run(schedule, SMALL, tmp_path / "runs")
    (tmp_path / "qaoa.json").write_text(json.dumps(section))
    assert "No quantum advantage claimed" in section["label"]
    assert {r["source"] for r in section["runs"]} == {"local", "random"}
    results = assemble(tmp_path)
    validate("results", results)

    backend = detect()
    backend.generate(tmp_path / "k" / "sk.pem", tmp_path / "k" / "pk.pem")
    ledger = Ledger(tmp_path / "ledger.jsonl", backend, tmp_path / "k" / "sk.pem", tmp_path / "k" / "pk.pem", tmp_path)
    appended, summary = ingest(ledger, tmp_path, tmp_path / "runs")
    assert "qaoa.run" in {e["type"] for e in appended}
    assert verify(ledger.path, tmp_path / "k" / "pk.pem", backend, tmp_path, summary)["ok"]
