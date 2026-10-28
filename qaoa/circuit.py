"""QAOA circuit for the QpiAI QCloud SDK (qpiai_quantum.Circuit).

QAOA on simulators. A measured cross-check against the exact optimum. No quantum advantage
claimed; the problem is small enough for brute force.

With x_k = (1 - Z_k)/2 the scaled cost exp(-i gamma H_C) becomes, up to a global phase,
  rz(k, -gamma * (h_k + sum_l J_kl / 2))   for every qubit k
  rzz(k, l, gamma * J_kl / 2)              for every coupling
using the SDK conventions rz(t) = exp(-i t/2 Z), rzz(t) = exp(-i t/2 ZZ), rx(t) = exp(-i t/2 X)
(verified against numpy in tests). Mixer: rx(k, 2 beta).
"""

from qpiai_quantum import Circuit

from .qubo import WaveQUBO


def build_circuit(q: WaveQUBO, gammas, betas, energy_scale: float, measure: bool = True) -> Circuit:
    n = q.n
    h = q.linear / energy_scale
    J = {kl: v / energy_scale for kl, v in q.quad.items() if v != 0.0}
    c = Circuit(n, name=f"qshield_qaoa_w{q.week}_p{len(gammas)}")
    for k in range(n):
        c.h(k)
    for g, b in zip(gammas, betas):
        z = [h[k] for k in range(n)]
        for (k, l), v in J.items():
            z[k] += v / 2
            z[l] += v / 2
        for k in range(n):
            c.rz(k, -g * z[k])
        for (k, l), v in J.items():
            c.rzz(k, l, g * v / 2)
        for k in range(n):
            c.rx(k, 2 * b)
    if measure:
        c.measure_all()
    return c
