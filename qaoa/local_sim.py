"""Numpy statevector QAOA (local reference simulator).

QAOA on simulators. A measured cross-check against the exact optimum. No quantum advantage
claimed; the problem is small enough for brute force.

State index is little-endian: bit k of the index is qubit k is QUBO variable k (same convention
as the qpiai_quantum simulator, verified in tests). |psi(gamma, beta)> =
  prod_layers [ prod_k RX_k(2 beta_l) ] exp(-i gamma_l H_C) |+>^n,   H_C = diag(E / scale)
Angles are optimised with scipy COBYLA on the expected energy <H_C>, from seeded restarts.
"""

import numpy as np
from scipy.optimize import minimize


def energy_scale(E: np.ndarray) -> float:
    span = float(E.max() - E.min())
    return span if span > 0 else 1.0


def statevector(E_scaled: np.ndarray, gammas, betas) -> np.ndarray:
    n = int(np.log2(E_scaled.size))
    psi = np.full(E_scaled.size, 2 ** (-n / 2), dtype=complex)
    for g, b in zip(gammas, betas):
        psi = psi * np.exp(-1j * g * E_scaled)
        c, s = np.cos(b), -1j * np.sin(b)  # RX(2b) = [[cos b, -i sin b], [-i sin b, cos b]]
        t = psi.reshape([2] * n)  # C order: axis n-1-k is qubit k
        for k in range(n):
            ax = n - 1 - k
            a0 = np.take(t, 0, axis=ax)
            a1 = np.take(t, 1, axis=ax)
            t = np.stack([c * a0 + s * a1, s * a0 + c * a1], axis=ax)
        psi = t.reshape(-1)
    return psi


def expected_energy(E: np.ndarray, psi: np.ndarray) -> float:
    return float(np.dot(np.abs(psi) ** 2, E))


def optimise(E: np.ndarray, p: int, restarts: int, seed: int, maxiter: int) -> dict:
    """Return the best angles over seeded COBYLA restarts (objective: expected energy in original units)."""
    scale = energy_scale(E)
    Es = E / scale
    rng = np.random.default_rng(seed)
    best = None
    history = []
    for r in range(restarts):
        x0 = np.concatenate([rng.uniform(0, np.pi, p), rng.uniform(0, np.pi / 2, p)])
        f = lambda x: expected_energy(E, statevector(Es, x[:p], x[p:]))
        res = minimize(f, x0, method="COBYLA", options={"maxiter": maxiter, "rhobeg": 0.3})
        history.append({"restart": r, "x0": x0.tolist(), "expected_energy": float(res.fun), "nfev": int(res.nfev)})
        if best is None or res.fun < best.fun:
            best = res
    gammas, betas = best.x[:p].tolist(), best.x[p:].tolist()
    psi = statevector(Es, gammas, betas)
    return {
        "p": p,
        "gammas": gammas,
        "betas": betas,
        "energy_scale": scale,
        "expected_energy": expected_energy(E, psi),
        "restarts": history,
        "probabilities": np.abs(psi) ** 2,
    }


def sample(probabilities: np.ndarray, shots: int, seed: int, n: int) -> dict[str, int]:
    """Draw shots; keys use the counts-string convention (rightmost char = qubit 0)."""
    rng = np.random.default_rng(seed)
    probs = probabilities / probabilities.sum()
    idx = rng.choice(probs.size, size=shots, p=probs)
    vals, cnt = np.unique(idx, return_counts=True)
    return {format(int(v), f"0{n}b"): int(c) for v, c in zip(vals, cnt)}


def uniform_samples(n: int, shots: int, seed: int) -> dict[str, int]:
    return sample(np.full(2**n, 1.0), shots, seed, n)
