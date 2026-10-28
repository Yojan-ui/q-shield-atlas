"""Sample metrics for the QAOA cross-check (same definitions for local, QCloud and random samples).

QAOA on simulators. A measured cross-check against the exact optimum. No quantum advantage
claimed; the problem is small enough for brute force.

For a set of samples (bitstrings in counts-string convention):
  feasible_fraction     share of shots whose asset bits satisfy capacity and dependencies
                        (slack bits ignored: feasibility is a property of the original problem)
  best_feasible         lowest original objective (-sum r_i a_i x_i) among feasible samples
  approximation_ratio   best_feasible / exact_optimum. Both are <= 0 (minimisation of a negated
                        value), so the ratio lies in [0, 1] and 1 means the exact optimum was sampled.
                        Undefined (None) if the exact optimum is 0.
  mean_energy           average QUBO energy (with penalties) over all shots
  energy_ratio          (E_max - mean_energy) / (E_max - E_min) in [0, 1]; 1 = all shots on the QUBO
                        minimum, 0 = all on the worst state, uniform sampling gives (E_max - E_mean)/(E_max - E_min)
  p_optimal             share of shots equal to the exact optimal bitstring (assets + slack)
  p_optimal_assets      share of shots selecting the optimal asset set (any slack)
"""

import math

import numpy as np

from .qubo import WaveQUBO


def compute(q: WaveQUBO, counts: dict[str, int], E: np.ndarray, exact: dict) -> dict:
    shots = sum(counts.values())
    if shots == 0:
        raise ValueError("no samples")
    e_min, e_max = float(E.min()), float(E.max())
    feasible = 0
    best = None
    energy_sum = energy_sq = 0.0
    hit = hit_assets = 0
    opt_assets = set(exact["assets"])
    for s, c in counts.items():
        bits = q.bits_from_bitstring(s)
        e = float(E[int(s, 2)])
        energy_sum += c * e
        energy_sq += c * e * e
        if s == exact["bitstring"]:
            hit += c
        if set(q.decode(s)) == opt_assets:
            hit_assets += c
        if q.feasible(bits):
            feasible += c
            obj = q.objective(bits)
            if best is None or obj < best[0]:
                best = (obj, q.decode(s))
    mean = energy_sum / shots
    var = max(0.0, energy_sq / shots - mean**2)
    exact_obj = exact["objective"]
    return {
        "shots": shots,
        "distinct_bitstrings": len(counts),
        "feasible_fraction": feasible / shots,
        "best_feasible_objective": best[0] if best else None,
        "best_feasible_assets": best[1] if best else None,
        "approximation_ratio": (best[0] / exact_obj) if best and exact_obj < 0 else None,
        "mean_energy": mean,
        "mean_energy_se": math.sqrt(var / shots),
        "energy_ratio": (e_max - mean) / (e_max - e_min) if e_max > e_min else None,
        "p_optimal": hit / shots,
        "p_optimal_assets": hit_assets / shots,
    }


def compare(local: dict, cloud: dict, sigma: float) -> dict:
    """Two-sample z-scores; never picks a winner, only flags large differences."""
    def z_prop(a, b, n1, n2):
        p = (a * n1 + b * n2) / (n1 + n2)
        se = math.sqrt(max(p * (1 - p), 1e-12) * (1 / n1 + 1 / n2))
        return (a - b) / se

    n1, n2 = local["shots"], cloud["shots"]
    z = {
        "feasible_fraction": z_prop(local["feasible_fraction"], cloud["feasible_fraction"], n1, n2),
        "p_optimal_assets": z_prop(local["p_optimal_assets"], cloud["p_optimal_assets"], n1, n2),
        "mean_energy": (local["mean_energy"] - cloud["mean_energy"])
        / max(math.hypot(local["mean_energy_se"], cloud["mean_energy_se"]), 1e-12),
    }
    big = {k: v for k, v in z.items() if abs(v) > sigma}
    return {
        "z_scores": z,
        "sigma_threshold": sigma,
        "differs": bool(big),
        "note": ("local and QCloud sample statistics differ beyond the threshold; both are reported, neither is preferred"
                 if big else "local and QCloud sample statistics agree within the threshold"),
    }
