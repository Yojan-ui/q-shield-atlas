"""One interface for every optimisation subproblem: solve(subproblem, instance, solver) -> Solution.

Subproblems (config/solvers.json picks the default solver for each):
  migration_schedule  the multi-week wave plan for every asset (schedule/milp.py). |assets| x horizon binaries
                      plus continuous exposure variables: MILP territory. Default: milp.
  link_cutover        one change window (qaoa/qubo.py): which links cut over to post-quantum key exchange
                      this week under the weekly effort cap and dependencies. A "link" is one asset's TLS
                      endpoint; there is no network-transmission model. <= 16 binary variables. Default: qaoa.

Solvers:
  milp     QpiAI Opt local MILP (free; verifies the API key online; no job ID)
  fcfs, greedy   classical list-scheduling baselines (migration_schedule only)
  exact    brute force over every asset subset (link_cutover only): the reference optimum
  qaoa     QAOA on the local numpy statevector simulator; readout = best feasible sampled bitstring
  hybrid   QAOA samples, then classical repair (drop the lowest value-per-effort asset until feasible)
           and greedy fill; the quantum part only proposes candidates

QAOA runs on simulators only. No quantum advantage is claimed: at <= 16 variables brute force is exact
and fast, and statevector simulation costs 2^n memory and time.
"""

import json
import time
from dataclasses import dataclass, field
from pathlib import Path

CONFIG = Path(__file__).resolve().parent.parent / "config" / "solvers.json"
SUBPROBLEMS = ("migration_schedule", "link_cutover")


class Unsupported(ValueError):
    """This solver cannot take this subproblem (with the reason)."""


@dataclass
class Solution:
    subproblem: str
    solver: str
    assignment: dict  # migration_schedule: asset -> completion week; link_cutover: asset -> 0/1
    objective: float | None  # the subproblem's own objective (lower is better)
    feasible: bool
    runtime_s: float
    size: dict  # {"variables": n, ...}
    record: object = None  # the solver's native output (schedule plan + solver runs, QAOA metrics, ...)
    notes: list[str] = field(default_factory=list)


def default_solver(subproblem: str) -> str:
    return json.loads(CONFIG.read_text())["default"][subproblem]


def registry() -> dict:
    from . import cutover, schedule

    return {"migration_schedule": schedule.SOLVERS, "link_cutover": cutover.SOLVERS}


def solve(subproblem: str, instance, solver: str | None = None, **opts) -> Solution:
    if subproblem not in SUBPROBLEMS:
        raise ValueError(f"unknown subproblem {subproblem!r}; known: {SUBPROBLEMS}")
    solver = solver or default_solver(subproblem)
    table = registry()[subproblem]
    if solver not in table:
        reason = UNSUPPORTED.get((subproblem, solver), f"no {solver!r} solver for {subproblem}")
        raise Unsupported(reason)
    t0 = time.perf_counter()
    sol = table[solver](instance, **opts)
    sol.runtime_s = time.perf_counter() - t0
    return sol


UNSUPPORTED = {
    ("migration_schedule", "qaoa"): "the full schedule has |assets| x horizon binaries plus continuous exposure "
                                    "variables (see the milp Solution.size); QAOA here is limited to <= 16 qubits "
                                    "on a statevector simulator",
    ("migration_schedule", "hybrid"): "no hybrid solver for the full schedule; hybrid applies to link_cutover",
    ("migration_schedule", "exact"): "brute force over every week assignment is infeasible at this size; the MILP proves optimality",
}
