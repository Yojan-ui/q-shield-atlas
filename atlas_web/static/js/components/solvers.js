// Solver quality and choice, shared by Schedule and Benchmark > Optimizers. Real data only: bench.json rows (the
// wave-selection QUBO instances, where brute-force Exact is feasible) and the recorded MILP solve (solver_runs).
import { h } from "../dom.js";
import { provAttr } from "./tooltip.js";

const NAME = { exact: "Exact (brute force)", milp: "MILP (QpiAI Opt)", random: "Random sampling", qaoa: "QAOA (simulator)", qaoa_sdk: "QAOA (QpiAI-QSV-Local)", hybrid: "Hybrid (QAOA + repair)" };
const keyOf = (r) => (r.solver === "qaoa" || r.solver === "qaoa_sdk" ? `${r.solver}${r.p}` : r.solver);

// largest instance; one row per solver that ran: objective, % of optimum, optimal badge when it equals Exact
export function qualityRows(b) {
  if (!b || !b.instances || !b.instances.length) return null;
  const big = b.instances[b.instances.length - 1];
  const seen = new Set();
  return { instance: big, rows: b.rows.filter((r) => r.instance === big.id && r.status === "ok" && typeof r.objective === "number" && !seen.has(keyOf(r)) && seen.add(keyOf(r)))
    .map((r) => ({ key: keyOf(r), label: `${NAME[r.solver] || r.solver}${r.p ? ` p=${r.p}` : ""}`, objective: r.objective, ratio: r.approximation_ratio, quantum: /qaoa|hybrid/.test(r.solver),
      optimal: Math.abs(r.objective - r.optimum) < 1e-9 && r.solver !== "exact" })) };
}

export function qualityBlock(P, ctx) {
  const Q = qualityRows(P && P.bench);
  if (!Q) return h("p", { class: "mv-note", text: "Solver comparison: not yet run. Run python -m bench (or Benchmark > Run benchmark) to compare Exact, MILP, Random and QAOA on this workspace." });
  const src = { run_id: P.bench.run_id, solver: "python -m bench", job_id: "none (local)", ts: P.bench.ts };
  return h("div", { class: "sv" },
    h("p", { class: "mv-note", text: `Wave selection, one week (${Q.instance.n_variables} variables): the subproblem where brute-force Exact is feasible. Bar = share of the optimum reached (100 % = optimal).` }),
    h("div", { class: "sv-rows" }, Q.rows.map((r) => h("div", { class: `sv-row${r.quantum ? " q" : ""}`, tabindex: "0", "data-prov": provAttr({ ...src, note: `objective ${r.objective}` }, r.label) },
      h("span", { class: "sv-l", text: r.label }), h("span", { class: "sv-bar" }, h("span", { style: { width: `${Math.max(0, Math.min(1, r.ratio ?? 0)) * 100}%` } })),
      h("span", { class: "sv-v num", text: `${((r.ratio ?? 0) * 100).toFixed(1)} %` }), r.optimal ? h("span", { class: "chip pass", text: "optimal" }) : h("span", { class: "sv-gap" })))),
    h("p", { class: "mv-note", text: "QAOA runs on a simulator and is a cross-check only: no quantum advantage is claimed. At this size Random sampling can also hit the optimum." }));
}

export function whyMilp(r) {
  const sr = (r.solver_runs || []).find((x) => /^schedule\.milp/.test(x.stage || ""));
  const t = sr && typeof sr.solver_time_s === "number" ? `${sr.solver_time_s < 1 ? `${(sr.solver_time_s * 1000).toFixed(0)} ms` : `${sr.solver_time_s.toFixed(2)} s`}` : "not recorded";
  return h("div", { class: "sv-why" },
    h("div", {}, h("b", { text: "Proven optimal" }), h("p", { class: "mv-note", text: sr ? `termination ${sr.termination || sr.status}, guarantee ${sr.guarantee || "n/a"}` : "not yet run" })),
    h("div", {}, h("b", { text: "Exact constraints" }), h("p", { class: "mv-note", text: "weekly capacity and every dependency hold by construction, not by repair" })),
    h("div", {}, h("b", { text: "Real solve time" }), h("p", { class: "mv-note", text: `${t} (${sr ? sr.solver : "QpiAI Opt"}, local)` })));
}

export function otherOptions() {
  const rows = [["Greedy / FCFS", "Fast rules of thumb; shown above on the same data; no optimality guarantee."],
    ["Simulated annealing / genetic", "Good on large rugged problems; heuristic, so no proof of optimality and constraints often need repair."],
    ["CP-SAT (constraint programming)", "A strong exact alternative for scheduling; not wired into this project."],
    ["QAOA", "Measured here on the small wave-selection QUBO on simulators; too few qubits for the full plan."],
    ["Reinforcement learning", "Needs many training episodes and gives no optimality proof; not used."]];
  return h("table", { class: "data sv-opt" }, h("thead", {}, h("tr", {}, h("th", { text: "other option" }), h("th", { text: "in one line" }))),
    h("tbody", {}, rows.map(([a, b]) => h("tr", {}, h("td", { text: a }), h("td", { text: b })))));
}
