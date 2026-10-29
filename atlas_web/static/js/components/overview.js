// Plain-language overview: one card per stage (contracts/stages.json order), one status each, the key number
// with a "what this means" line, and a colour legend. Every number is read from results.json.
import { h } from "../dom.js";
import { chip } from "./chip.js";
import { STAGES } from "../stages.js";
import { HNDL } from "../model.js";

export const PLAIN = {
  detect: "Find weak encryption", ledger: "Start the proof record", schedule: "Plan the move", capture: "Test real connections",
  gates: "Check every wave", qaoa: "Quantum cross-check", seal: "Verify the record", report: "Write the report",
};
export const STATUS_WORD = { ok: ["PASS", "Done"], running: ["running", "Running"], fail: ["FAIL", "Failed"], idle: ["NOT_RUN", "Not run"] };

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

export function stageStatus(stageId, steps, facts, run) {
  const summary = Object.fromEntries((((run || {}).detail || {}).summary || []).map((s) => [s.step, s]));
  const st = steps.map((s) => summary[s]);
  if (st.some((s) => s && s.exit_code !== 0)) return "fail";
  if (run && run.status === "running" && !st.every(Boolean)) return "running";
  return facts[stageId] ? "ok" : "idle";
}

export function colorLegend() {
  return h("ul", { class: "legend", "aria-label": "What the colours mean" },
    [["exposed", "Red: quantum-exposed (old RSA / ECC encryption)"], ["accent", "Cyan: post-quantum protected"], ["pass", "Green: passed a check"],
     ["caution", "Amber: assumption or partly verified"], ["neutral", "Grey: not run, planned or not applicable"]].map(([c, t]) =>
      h("li", {}, h("span", { class: `lg-dot ${c}`, "aria-hidden": "true" }), t)));
}

export function overview(r, run) {
  const facts = stageFacts(r);
  return h("section", { class: "ov", "aria-label": "At a glance" },
    h("ol", { class: "ov-cards" }, STAGES.map((s, i) => {
      const status = stageStatus(s.id, s.steps, facts, run), [chipKind, word] = STATUS_WORD[status], f = facts[s.id];
      return h("li", { class: `ov-card ${status}` },
        h("p", { class: "ov-head" }, h("span", { class: "ov-idx mono", text: String(i + 1) }), h("span", { class: "ov-name", text: PLAIN[s.id] }), chip(chipKind, word)),
        h("p", { class: "ov-tech fine", text: s.label }),
        f ? h("p", { class: "ov-num num", text: f[0] }) : h("p", { class: "ov-num missing", text: "–" }),
        h("p", { class: "ov-mean", text: f ? f[1] : "Not run yet in this workspace." }));
    })), colorLegend());
}
