"""link_cutover solvers: exact brute force, QAOA (simulator), hybrid (QAOA + classical repair), MILP (QpiAI Opt).

Instance: a qaoa.qubo.WaveQUBO (one change window). Objective: -sum_i r_i a_i x_i (lower is better) subject
to the weekly effort cap and dependencies. Every solver's answer is re-checked with WaveQUBO.feasible.
"""

import json
from pathlib import Path

from qaoa import local_sim, metrics
from qaoa.qubo import exact_optimum

from . import Solution

QAOA_CFG = Path(__file__).resolve().parent.parent / "config" / "qaoa.json"


def _size(q):
    return {"variables": q.n, "asset_variables": q.m, "slack_bits": q.slack_bits, "dependencies": len(q.deps),
            "statevector_amplitudes": 2**q.n}


def _sol(q, solver, x, record, notes=()):
    x = list(x)[: q.m]
    ok = q.feasible(x)
    return Solution("link_cutover", solver, {a: int(b) for a, b in zip(q.assets, x)}, q.objective(x) if ok else None,
                    ok, 0.0, _size(q), record, list(notes))


def exact(q, **_):
    e = exact_optimum(q)
    return _sol(q, "exact", [int(a in e["assets"]) for a in q.assets], e)


def _qaoa_samples(q, p, cfg, E=None):
    E = q.energies() if E is None else E
    opt = local_sim.optimise(E, p, cfg["restarts"], cfg["seed"], cfg["cobyla_maxiter"])
    counts = local_sim.sample(opt["probabilities"], cfg["shots"], cfg["seed"] + p, q.n)
    return E, opt, counts


def qaoa(q, p=1, cfg=None, **_):
    """Readout: the best feasible bitstring among the shots (feasibility checked classically, as in qaoa/metrics.py)."""
    cfg = cfg or json.loads(QAOA_CFG.read_text())
    E, opt, counts = _qaoa_samples(q, p, cfg)
    m = metrics.compute(q, counts, E, exact_optimum(q))
    rec = {"p": p, "shots": cfg["shots"], "angles": {"gammas": opt["gammas"], "betas": opt["betas"]}, "energy_scale": opt["energy_scale"], "metrics": m,
           "backend": "numpy statevector (qaoa/local_sim.py)"}
    if m["best_feasible_assets"] is None:
        top = max(counts, key=counts.get)
        return _sol(q, "qaoa", q.bits_from_bitstring(top), rec, ["no feasible sample; most frequent bitstring returned"])
    return _sol(q, "qaoa", [int(a in m["best_feasible_assets"]) for a in q.assets], rec)


def _deps_ok(q, x):
    changed = True
    while changed:  # drop any selected asset whose prerequisite is not selected
        changed = False
        for i, j in q.deps:
            if x[i] and not x[j]:
                x[i], changed = 0, True
    return x


def repair(q, x):
    """Classical repair + greedy fill: drop dependency violators, then the lowest value-per-effort asset until
    under capacity; then add assets (highest value per effort first) while the selection stays feasible."""
    x = _deps_ok(q, list(x)[: q.m])
    ratio = sorted(range(q.m), key=lambda i: (q.values[i] / max(q.weights[i], 1), -i))  # ascending
    while sum(w * b for w, b in zip(q.weights, x)) > q.capacity:
        x[next(i for i in ratio if x[i])] = 0
        x = _deps_ok(q, x)
    for i in reversed(ratio):
        if not x[i]:
            y = x.copy()
            y[i] = 1
            if q.feasible(y):
                x = y
    return x


def hybrid(q, p=1, cfg=None, **_):
    """QAOA proposes; classical post-processing repairs every distinct sample; the best repaired one wins."""
    cfg = cfg or json.loads(QAOA_CFG.read_text())
    E, opt, counts = _qaoa_samples(q, p, cfg)
    best, raw_feasible = None, 0
    for s, c in counts.items():
        bits = q.bits_from_bitstring(s)
        raw_feasible += c * q.feasible(bits)
        x = repair(q, bits)
        obj = q.objective(x)
        if best is None or obj < best[0] - 1e-12:
            best = (obj, x)
    rec = {"p": p, "shots": cfg["shots"], "distinct_samples_repaired": len(counts),
           "raw_feasible_fraction": raw_feasible / cfg["shots"], "backend": "numpy statevector QAOA + classical repair"}
    return _sol(q, "hybrid", best[1], rec, ["quantum part proposes candidates; the classical repair decides feasibility"])


def milp(q, client=None, time_limit=60.0, **_):
    """The same knapsack-with-dependencies as a QpiAI Opt local MILP (needs QPIAI_OPT_API_KEY; verifies online)."""
    import os

    from qpiai_opt.opt_modeller import Binary, Model, quicksum
    from qpiai_opt.opt_solvers import Client, solve

    client = client or Client(api_key=os.environ["QPIAI_OPT_API_KEY"])
    x = [Binary(f"x_{i}") for i in range(q.m)]
    model = Model(f"link_cutover_week_{q.week}")
    model.add_constraint(quicksum(w * xi for w, xi in zip(q.weights, x)) <= q.capacity, label="capacity")
    for i, j in q.deps:
        model.add_constraint(x[i] - x[j] <= 0, label=f"dep_{i}_needs_{j}")
    model.minimize(quicksum(-v * xi for v, xi in zip(q.values, x)))
    res = solve(model, client=client, time_limit=time_limit, mip_rel_gap=0.0)
    info = res.info()
    if info.termination != "optimal" or not info.has_usable_solution:
        raise RuntimeError(f"link_cutover MILP did not reach a proven optimum: {info.termination}")
    bits = [int(res.solution[f"x_{i}"] > 0.5) for i in range(q.m)]
    rec = {"termination": info.termination, "guarantee": info.guarantee, "objective": res.objective,
           "solver_time_s": res.solver_time_s, "mode": res.execution_mode, "job_id": res.job_id,
           "job_id_reason": None if res.job_id else "QpiAI Opt local solve issues no platform job ID"}
    return _sol(q, "milp", bits, rec)


SOLVERS = {"exact": exact, "qaoa": qaoa, "hybrid": hybrid, "milp": milp}
