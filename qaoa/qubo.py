"""Link cutover selection QUBO for one scheduled week (solvers subproblem "link_cutover").

A "link" is one asset's TLS endpoint cutting over to post-quantum key exchange in that change window;
there is no network-transmission model.

QAOA on simulators. A measured cross-check against the exact optimum. No quantum advantage
claimed; the problem is small enough for brute force.

Decision x_i = 1: migrate candidate asset i in week k. Candidates are assets not yet migrated
before week k in the latest schedule (completion_week >= k).
  value  a_i = scenario-weighted exposure-years avoided by migrating i in week k instead of
               deferring it by `deferral_weeks` (Mosca exposure, same data as schedule/)
  objective   minimise  -sum_i r_i a_i x_i
  capacity    sum_i w_i x_i <= C  via binary slack s (ceil(log2(C+1)) bits, integer-scaled weights),
              penalty A (sum_i w_i x_i + s - C)^2
  dependency  i needs j (j not yet migrated): penalty B x_i (1 - x_j)
A = B = 1 + sum_i |c_i|: any infeasible state costs > 0 >= the empty (feasible) selection.
Variable k <-> bit k of the basis index <-> qubit k (little-endian; the rightmost character of a
counts string is variable 0).
"""

import math
from dataclasses import dataclass, field

import numpy as np


@dataclass
class WaveQUBO:
    week: int
    assets: list[str]  # variable i (i < m) -> asset id
    values: list[float]  # r_i * a_i, so objective coefficient c_i = -values[i]
    weights: list[int]  # integer-scaled efforts
    capacity: int  # integer-scaled
    weight_scale: int
    deps: list[tuple[int, int]]  # (i, j): i needs j
    slack_bits: int
    A: float
    B: float
    linear: np.ndarray  # length n
    quad: dict[tuple[int, int], float]  # k < l
    offset: float
    log: list[str] = field(default_factory=list)

    @property
    def m(self) -> int:
        return len(self.assets)

    @property
    def n(self) -> int:
        return self.m + self.slack_bits

    # ---- encoding ----
    def bits_from_index(self, idx: int) -> list[int]:
        return [(idx >> k) & 1 for k in range(self.n)]

    def bitstring(self, bits) -> str:
        """Counts-string convention: rightmost character is variable/qubit 0."""
        return "".join(str(int(b)) for b in reversed(list(bits)))

    def bits_from_bitstring(self, s: str) -> list[int]:
        if len(s) != self.n:
            raise ValueError(f"bitstring has {len(s)} bits, QUBO has {self.n}")
        return [int(c) for c in reversed(s)]

    def decode(self, s: str) -> list[str]:
        bits = self.bits_from_bitstring(s)
        return [a for a, b in zip(self.assets, bits[: self.m]) if b]

    def encode(self, selected: set[str], slack: int = 0) -> str:
        bits = [int(a in selected) for a in self.assets] + [(slack >> b) & 1 for b in range(self.slack_bits)]
        return self.bitstring(bits)

    # ---- evaluation ----
    def objective(self, xbits) -> float:
        return -float(np.dot(self.values, np.asarray(xbits[: self.m], float)))

    def feasible(self, xbits) -> bool:
        x = list(xbits[: self.m])
        if sum(w * b for w, b in zip(self.weights, x)) > self.capacity:
            return False
        return all(not (x[i] and not x[j]) for i, j in self.deps)

    def energy(self, bits) -> float:
        b = np.asarray(bits, float)
        return float(self.offset + self.linear @ b + sum(v * b[k] * b[l] for (k, l), v in self.quad.items()))

    def energies(self) -> np.ndarray:
        """QUBO energy of every basis state, indexed little-endian (vectorised)."""
        idx = np.arange(2**self.n)
        bits = ((idx[:, None] >> np.arange(self.n)) & 1).astype(float)
        e = self.offset + bits @ self.linear
        for (k, l), v in self.quad.items():
            e += v * bits[:, k] * bits[:, l]
        return e


def exposure(shelf: float, week: int, year: float, start_year: float, per_year: int) -> float:
    return max(0.0, shelf + week / per_year - (year - start_year))


def _integer_scale(values: list[float], capacity: float, log: list[str]) -> tuple[list[int], int, int]:
    for scale in (1, 10, 100):
        if all(abs(v * scale - round(v * scale)) < 1e-9 for v in values + [capacity]):
            return [int(round(v * scale)) for v in values], int(round(capacity * scale)), scale
    log.append("efforts not representable with 2 decimals; rounded at scale 100")
    return [int(round(v * 100)) for v in values], int(round(capacity * 100)), 100


def build(schedule: dict, cfg: dict) -> WaveQUBO:
    log: list[str] = []
    a_cfg = schedule["assumptions"]
    week, defer = cfg["week"], cfg["deferral_weeks"]
    per_year, start = a_cfg["weeks_per_year"], a_cfg["start_year"]
    total_w = sum(s["weight"] for s in schedule["scenarios"]) or 1.0
    completion = schedule["exposure"]["completion_week"]
    assets = {a["id"]: a for a in schedule["assets"]}

    def avoided(a) -> float:
        return sum(
            s["weight"] / total_w
            * (exposure(a["shelf_life_years"], week + defer, s["year"], start, per_year)
               - exposure(a["shelf_life_years"], week, s["year"], start, per_year))
            for s in schedule["scenarios"]
        )

    candidates = [i for i in assets if completion[i] >= week]
    value = {i: assets[i]["risk_weight"] * avoided(assets[i]) for i in candidates}
    unmet = {i: [d for d in assets[i]["depends_on"] if completion[d] >= week] for i in candidates}
    log.append(f"week {week}: {len(candidates)} assets not yet migrated before this week")

    _, capacity, scale = _integer_scale([assets[i]["effort_days"] for i in candidates],
                                        a_cfg["capacity_days_per_week"], log)
    slack_bits = math.ceil(math.log2(capacity + 1))
    budget = min(cfg["max_assets"], cfg["max_variables"] - slack_bits)

    # shrink: highest value per effort first, each together with its unmet-dependency closure
    chosen: list[str] = []
    for i in sorted(candidates, key=lambda i: (-value[i] / assets[i]["effort_days"], i)):
        if i in chosen:
            continue
        closure, stack = [], [i]
        while stack:
            j = stack.pop()
            if j not in chosen and j not in closure:
                closure.append(j)
                stack += unmet[j]
        if len(chosen) + len(closure) > budget:
            log.append(f"dropped {i} (value {value[i]:.4g}): with unmet deps {closure[1:]} it exceeds the {budget}-asset budget")
            continue
        chosen += closure
    order = sorted(chosen, key=lambda i: candidates.index(i))
    log.append(f"kept {len(order)} candidates: {order}")
    weights = [int(round(assets[i]["effort_days"] * scale)) for i in order]
    m = len(order)
    n = m + slack_bits
    if n > cfg["max_variables"]:
        raise ValueError(f"{n} variables exceed max_variables={cfg['max_variables']}")
    vals = [value[i] for i in order]
    deps = [(order.index(i), order.index(j)) for i in order for j in unmet[i]]
    A = B = 1.0 + sum(abs(v) for v in vals)
    log.append(f"A = B = 1 + sum|c_i| = {A:.6g}; capacity {capacity} (scale {scale}), {slack_bits} slack bits, {n} variables")

    lin = np.zeros(n)
    quad: dict[tuple[int, int], float] = {}

    def addq(k, l, v):
        key = (min(k, l), max(k, l))
        quad[key] = quad.get(key, 0.0) + v

    for i in range(m):
        lin[i] -= vals[i]
    coef = weights + [2**b for b in range(slack_bits)]  # A (sum coef_k z_k - C)^2
    for k in range(n):
        lin[k] += A * (coef[k] ** 2 - 2 * capacity * coef[k])
        for l in range(k + 1, n):
            addq(k, l, 2 * A * coef[k] * coef[l])
    offset = A * capacity**2
    for i, j in deps:  # B x_i (1 - x_j)
        lin[i] += B
        addq(i, j, -B)
    return WaveQUBO(week, order, vals, weights, capacity, scale, deps, slack_bits, A, B, lin, quad, offset, log)


def exact_optimum(q: WaveQUBO) -> dict:
    """Brute force over all 2^m asset subsets with the original constraints."""
    best = None
    for idx in range(2**q.m):
        x = [(idx >> k) & 1 for k in range(q.m)]
        if q.feasible(x):
            obj = q.objective(x)
            if best is None or obj < best[0] - 1e-12:
                best = (obj, x)
    obj, x = best
    used = sum(w * b for w, b in zip(q.weights, x))
    bits = x + [((q.capacity - used) >> b) & 1 for b in range(q.slack_bits)]
    return {"objective": obj, "assets": [a for a, b in zip(q.assets, x) if b], "bitstring": q.bitstring(bits),
            "method": f"brute force over 2^{q.m} asset subsets"}
