// Plain-language overview: one card per stage (contracts/stages.json order), one status each, the key number
// with a "what this means" line, and a colour legend. Every number is read from results.json.
import { h } from "../dom.js";
import { chip } from "./chip.js";
import { FLOW } from "../flow.js";
import { HNDL, solverLabel } from "../model.js";


// one fact per stage: [number text, what this means]; null when the stage has no data
export function stageFacts(r) {
  if (!r) return {};
  const pl = (n, one, many) => `${n} ${n === 1 ? one : many}`;
  const f = {};
  if (r.detect) f.detect = [String(r.assets.length), `${pl(r.assets.length, "system uses", "systems use")} encryption a future quantum computer could break (RSA, ECC). ${r.detect.summary.vulnerable_findings} places in the code and configuration show it.`];
  if (r.ledger) f.ledger = [String(r.ledger.entry_count), `${pl(r.ledger.entry_count, "signed record", "signed records")} of what was found and done. Changing any one of them is detected.`];
  if (r.exposure) f.schedule = [`${r.exposure.makespan_weeks} wk`, `Weeks to move every system to post-quantum encryption at the assumed team capacity, in ${pl(r.waves.length, "wave", "waves")}.`];
  const hs = (r.handshake_evidence || {}).sessions || [];
  if (hs.length) {
    const exposed = hs.filter((s) => s.hndl_exposed).length;
    f.capture = [`${exposed} / ${hs.length}`, `${pl(exposed, "test connection still uses", "test connections still use")} old key exchange (${HNDL}); the rest use post-quantum key exchange.`];
  }
  if (r.gates) {
    const passed = r.waves.filter((w) => w.status === "applied").length;
    f.gates = [`${passed} / ${r.waves.length}`, `Waves that passed every lab check (post-quantum connection, no downgrade, compatibility, tested rollback). The others are partly verified or not verifiable in the lab.`];
  }
  if (r.qaoa) {
    const local = r.qaoa.runs.filter((x) => x.source === "local" && x.metrics);
    const top = local.sort((a, b) => b.p - a.p)[0], rnd = r.qaoa.runs.find((x) => x.source === "random");
    if (top) f.qaoa = [top.metrics.approximation_ratio === 1 ? "matched" : (top.metrics.approximation_ratio ?? 0).toFixed(3),
      `On a simulator, QAOA found the best answer for one week's cutover choice${top.metrics.approximation_ratio === 1 ? "" : " only approximately"}. A cross-check, not an advantage${rnd && rnd.metrics.approximation_ratio === 1 ? ": random guessing found it too at this small size" : ""}.`];
  }
  const v = r.ledger_verification;
  if (v) f.seal = [v.ok ? "verified" : "FAILED", v.ok ? `Every signature and fingerprint in the record checks out (${v.entries_checked} records).` : `The record does not check out at entry #${(v.first_failure || {}).index}.`];
  const rep = ((r.ledger || {}).entries || []).some((e) => e.type === "report.html");
  if (rep) f.report = ["signed", "A report with every number above, signed into the record."];
  return f;
}


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
