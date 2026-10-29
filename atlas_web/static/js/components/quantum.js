// Live quantum panel: which backend runs QAOA right now (GET /api/quantum/status) and one live run of the
// link cutover step (POST /api/quantum/run). Loading, error and fallback states; simulator output is never
// called hardware.
import { h, icon } from "../dom.js";
import { chip } from "./chip.js";
import { dd } from "./dd.js";

let statusP = null;
export const quantumStatus = (api) => (statusP ||= api.get("/api/quantum/status").catch((e) => { statusP = null; throw e; }));

export function backendBadge(api) {
  const el = h("span", { class: "chip neutral qb-badge", title: "Quantum backend in use" }, "Quantum: checking…");
  quantumStatus(api).then((s) => { el.textContent = `Quantum: ${s.backend}`; el.title = s.fallback_reason ? `Fallback: ${s.fallback_reason}` : "QpiAI Cloud simulator"; })
    .catch(() => { el.textContent = "Quantum: status unavailable"; });
  return el;
}

const pct = (x) => (x === null || x === undefined ? "–" : `${(x * 100).toFixed(1)} %`);

export function quantumPanel(ctx) {
  const head = h("p", { class: "fine", text: "Checking the quantum backend…" });
  const out = h("div", { class: "qp-out", "aria-live": "polite" });
  const btn = h("button", { class: "btn primary", type: "button", disabled: true }, icon("play"), "Run QAOA now");
  quantumStatus(ctx.api).then((s) => {
    btn.disabled = false;
    head.replaceChildren(h("span", { class: "qp-backend" }, "Backend: ", h("b", { text: s.backend })),
      h("span", { class: "fine", text: s.fallback_reason ? ` · QpiAI Cloud not used: ${s.fallback_reason}` : " · QpiAI Cloud simulator, not hardware" }),
      h("span", { class: "fine", text: ` · QpiAI SDK ${s.cloud.sdk_version}; cloud login ${s.cloud.reachable ? `ok, ${s.cloud.devices.filter((d) => d.status === "active").length} devices active` : `failed: ${s.cloud.error}`}` }));
  }).catch((err) => head.replaceChildren(chip("FAIL", `backend status unavailable: ${err.message}`)));
  btn.addEventListener("click", async () => {
    btn.disabled = true;
    out.replaceChildren(h("p", { class: "fine" }, h("span", { class: "skel line" }), "Running QAOA on the backend (a few seconds)…"));
    try {
      const r = await ctx.api.post("/api/quantum/run", { ws: ctx.ws, p: 1 });
      const ok = r.approximation_ratio === 1;
      out.replaceChildren(
        h("p", {}, chip(ok ? "PASS" : "partially_verified", ok ? "found the exact best answer" : "close to the best answer"), h("b", { text: ` ${r.backend}` }),
          h("span", { class: "fine", text: ` · ${r.n_variables} qubits · ${r.shots} shots · ${r.runtime_s.toFixed(1)} s` })),
        dd({ shows: `For week ${r.week}, QAOA picked ${r.best_feasible.assets ? r.best_feasible.assets.join(", ") : "no feasible set"} to cut over; the exact optimum is ${r.exact_optimum.assets.join(", ")}. ${pct(r.p_optimal_assets)} of shots landed on it. ${r.fallback_reason ? "Ran on QpiAI's local simulator; cloud-ready." : ""}`, read: r.note, source: r.job_id ? `job ${r.job_id}` : `no job ID: ${r.job_id_reason}` }));
      ctx.announce(`QAOA run on ${r.backend}: ${ok ? "exact best answer found" : "approximate answer"}.`);
    } catch (err) {
      if (err.code === "aborted") return;
      out.replaceChildren(chip("FAIL", err.code === "busy" ? "another run is in progress; try again in a moment" : `run failed: ${err.message}`));
    } finally { btn.disabled = false; }
  }, { signal: ctx.signal });
  return h("section", { class: "span-12 qp" }, h("p", { class: "eyebrow", text: "Live quantum run" }), head, btn, out);
}
