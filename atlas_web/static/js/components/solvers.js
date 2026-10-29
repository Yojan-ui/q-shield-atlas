// Why the full plan uses a MILP, from the recorded solve (solver_runs).
import { h } from "../dom.js";
import { dd } from "./dd.js";


export function whyMilp(r) {
  const sr = (r.solver_runs || []).find((x) => /^schedule\.milp/.test(x.stage || ""));
  const t = sr && typeof sr.solver_time_s === "number" ? `${sr.solver_time_s < 1 ? `${(sr.solver_time_s * 1000).toFixed(0)} ms` : `${sr.solver_time_s.toFixed(2)} s`}` : "not recorded";
  const opt = sr && sr.guarantee === "global_optimum";
  return h("div", {}, h("div", { class: "sv-why" },
    h("div", {}, h("b", { text: "Proven optimal" }), h("p", { class: "mv-note", text: sr ? (opt ? "Gap 0, proven optimal" : `${sr.termination || sr.status}`) : "not yet run" })),
    h("div", {}, h("b", { text: "Exact constraints" }), h("p", { class: "mv-note", text: "Capacity + dependencies exact" })),
    h("div", {}, h("b", { text: "Real solve time" }), h("p", { class: "mv-note", text: `${t} local` }))),
    dd({ shows: "Why the full plan uses a MILP.", read: `termination ${sr ? sr.termination || sr.status : "n/a"}, guarantee ${sr ? sr.guarantee || "n/a" : "n/a"}; weekly capacity and every dependency hold by construction, not by repair.`,
      source: sr ? `${sr.solver} (${sr.mode || "local"}), run ${sr.run_id}` : "not yet run" }));
}
