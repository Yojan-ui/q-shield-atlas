// Plain-language overview: one card per stage (contracts/stages.json order), one status each, the key number
// with a "what this means" line, and a colour legend. Every number is read from results.json.
import { h } from "../dom.js";
import { chip } from "./chip.js";
import { FLOW } from "../flow.js";
import { HNDL, solverLabel } from "../model.js";


export function colorLegend() {
  return h("ul", { class: "legend", "aria-label": "What the colours mean" },
    [["exposed", "Red: quantum-exposed (old RSA / ECC encryption)"], ["pqc", "Cyan: post-quantum protected"], ["pass", "Green: passed a check"],
     ["caution", "Amber: assumption or partly verified"], ["neutral", "Grey: not run, planned or not applicable"]].map(([c, t]) =>
      h("li", {}, h("span", { class: `lg-dot ${c}`, "aria-hidden": "true" }), t)));
}


// ---- the seven-step flow (contracts/stages.json "flow") as cards: what it does, what it hands on, key number, backend

export function flowFacts(r, reviews) {
  if (!r) return {};
  const f = {};
  const pl = (n, one, many) => `${n} ${n === 1 ? one : many}`;
  if (r.detect) {
    f.detect = { num: String(r.detect.summary.vulnerable_findings), mean: `places in code, config and certificates use RSA / ECC (${r.detect.files_scanned} files scanned)`, backend: "static scan + OpenSSL 3.6.5 live probes" };
    const drift = (r.detect.probes || []).reduce((n, p) => n + (p.drift || []).length, 0);
    f.inventory = { num: String(r.assets.length), mean: `to migrate · ${pl(drift, "drift alert", "drift alerts")}`, backend: "atlas-service.json manifests + scan" };
    f.detect = { num: `${r.detect.summary.vulnerable_findings} → ${r.assets.length}`, mean: `findings → systems · ${pl(drift, "drift alert", "drift alerts")} (${r.detect.files_scanned} files scanned)`, backend: f.detect.backend };
  }
  if (r.exposure) f.schedule = { num: `${r.exposure.makespan_weeks} wk`, mean: `to migrate everything in ${pl(r.waves.length, "wave", "waves")} at the assumed capacity`, backend: solverLabel(r) };
  if (r.qaoa) {
    const top = r.qaoa.runs.filter((x) => x.source === "local" && x.metrics).sort((a, b) => b.p - a.p)[0];
    const dev = (r.qaoa.qpiai_local || {}).device;
    if (top) f.waves = { num: top.metrics.approximation_ratio === 1 ? "optimal" : top.metrics.approximation_ratio.toFixed(3),
      mean: `week ${r.qaoa.problem.week} selection, ${r.qaoa.problem.n_variables} variables, checked against the exact answer`,
      backend: `${dev ? "QpiAI-QSV-Local simulator" : "numpy statevector simulator"} · QCloud: awaiting account activation` };
  }
  if (r.gates) {
    const passed = r.waves.filter((w) => w.status === "applied").length;
    f.gates = { num: `${passed} / ${r.waves.length}`, mean: "waves passed every lab gate; the rest are partly verified or not testable in the lab", backend: "OpenSSL 3.6.5 lab services on 127.0.0.1" };
  }
  if (r.ledger) {
    const v = r.ledger_verification;
    f.ledger = { num: String(r.ledger.entry_count), mean: `signed records · ${v && v.ok ? "chain verified" : "not verified"}`, backend: `${r.ledger.alg} · ${r.ledger.backend}` };
    const first = (r.ledger.entries || []).find((e) => e.type === "detect.run");
    f.proof_open = { num: first ? `#${first.index}` : String(r.ledger.entry_count), mean: first ? "the Detect evidence was signed first (detect.run)" : "signed records", backend: f.ledger.backend };
    f.proof_verified = { num: String(r.ledger.entry_count), mean: `signed records · ${v && v.ok ? "every signature and hash re-verified" : "not verified"}`, backend: f.ledger.backend };
  }
  const items = (reviews && reviews.items) || [];
  if (items.length) {
    const pending = items.filter((i) => i.status === "pending").length;
    f.review = { num: `${items.length - pending} / ${items.length}`, mean: `results decided by a person · ${pending} awaiting review`, backend: "decisions signed with ML-DSA-65" };
  }
  return f;
}

export function flowCards(ctx, r, reviews) {
  const facts = flowFacts(r, reviews);
  return h("ol", { class: "flow-cards", "aria-label": "Pipeline steps" }, FLOW.map((s, i) => {
    const f = facts[s.id];
    const [kind, word] = f ? (s.id === "review" && f.num.split(" / ")[0] !== f.num.split(" / ")[1] ? ["pending", "Waiting"] : ["PASS", "Done"]) : ["NOT_RUN", "Not run"];
    return h("li", {}, h("a", { class: "flow-card", href: `/w/${ctx.ws}/${s.route}` },
      h("p", { class: "fc-head" }, h("span", { class: "fc-num", text: String(i + 1) }), h("span", { class: "fc-name", text: s.label }), chip(kind, word)),
      h("p", { class: "fc-mean", text: s.does }),
      f ? h("p", {}, h("span", { class: "fc-num-big", text: f.num }), h("span", { class: "fc-mean", text: ` ${f.mean}` })) : h("p", { class: "fc-mean", text: "No result yet in this workspace." }),
      h("p", { class: "fc-hands", text: `Hands on: ${s.hands}` }),
      f ? h("p", { class: "fc-backend", text: f.backend }) : null));
  }));
}
