// QAOA: measured cross-check vs brute force; cloud per p (?p=); QCloud rows show status_text only.
import { h } from "../dom.js";
import { stat, statSkeleton } from "../components/stat.js";
import { chip } from "../components/chip.js";
import { table, tableSkeleton } from "../components/table.js";
import { emptyState } from "../components/states.js";
import { num, QAOA_LABEL } from "../model.js";
import { dataView, honesty, mountScene, notRun, stage } from "./common.js";
import { buildQaoaCloud } from "../scenes/qaoa.js";
import { quantumPanel } from "../components/quantum.js";
import { bullets, detailsList, main, nextStep, pageHead, whyBlock, dd } from "../components/page.js";
import { term } from "../glossary.js";

const pct = (x) => `${(x * 100).toFixed(2)} %`;
const bars = (rows) => h("div", { class: "qa-bars" }, rows.map(([name, m]) => h("div", { class: "qa-bar" }, h("span", { class: "eyebrow", text: name }),
  [["feasible", m.feasible_fraction, ""], ["P(opt set)", m.p_optimal_assets, " core"]].map(([k, v, c]) => h("div", { class: "qa-track" },
    h("div", { class: "qa-rail" }, h("span", { class: `qa-fill${c}`, style: { width: `${Math.max(0.4, v * 100)}%` } })), h("span", { class: "fine num", text: `${k} ${pct(v)}` }))))));

export async function mount(ctx) {
  const fb = h("div", { class: "qa-fb" }), legend = h("div", { class: "fine qa-legend" });
  const stageEl = stage(ctx, { label: "Probability cloud: QAOA (left) beside a uniform random baseline (right). Cyan shell = feasible share of shots; green core = optimal-set share.", fallback: fb });
  const picker = h("div", { class: "sg-row qa-controls", role: "radiogroup", "aria-label": "QAOA depth p" });
  let cloud = null;
  const body = dataView(ctx, {
    keys: ["results"],
    skeleton: () => h("div", { class: "grid" }, h("div", { class: "span-12" }, statSkeleton()), h("div", { class: "span-12" }, tableSkeleton(7))),
    render: ({ model: m }) => {
      const q = m && m.qaoa, raw = q && q.available ? m.results.qaoa : null;
      const rows = raw ? raw.table.map((r, i) => ({ ...q.rows[i], raw: r, ok: r.status === "ok" && !!r.metrics })) : [];
      const levels = rows.filter((r) => r.source_kind === "local" && r.ok).sort((a, b) => a.p - b.p).slice(0, 3);
      const rnd = rows.find((r) => r.source_kind === "random" && r.ok);
      stageEl.hidden = picker.hidden = legend.hidden = !levels.length || !rnd;
      if (stageEl.hidden) return emptyState(notRun(ctx, "QAOA cross-check"));
      const prob = raw.problem, rm = rnd.raw.metrics;
      const n = Math.max(256, rnd.raw.shots || 0, ...levels.map((r) => r.raw.shots || 0));
      let idx = levels.findIndex((r) => r.p === Number(ctx.query.get("p")));
      if (idx < 0) idx = levels.length - 1;
      const sF = stat({ label: "feasible share", cell: null, tone: "accent" }), sO = stat({ label: "P(optimal set)", cell: null, tone: "accent" });
      const set = (el, label, cell, base) => {
        el.update(cell);
        el.querySelector(".label").firstChild.textContent = label;
        (el.querySelector(".unit") || el.lastChild.appendChild(h("div", { class: "unit" }))).textContent = `random baseline ${base.toFixed(4)}`;
      };
      const draw = () => {
        const L = levels[idx], lm = L.raw.metrics;
        picker.replaceChildren(...levels.map((r, i) => h("button", { class: `btn${i === idx ? " primary" : ""}`, type: "button", role: "radio", "aria-checked": String(i === idx), text: `p = ${r.p}`,
          onclick: () => { idx = i; ctx.setQuery({ p: r.p }); draw(); } })));
        set(sF, `feasible share · p = ${L.p}`, L.cells.feasible_fraction, rm.feasible_fraction);
        set(sO, `P(optimal set) · p = ${L.p}`, L.cells.p_optimal_assets, rm.p_optimal_assets);
        legend.replaceChildren(h("span", { text: `left: QAOA p = ${L.p} · right: uniform random baseline` }),
          ...[["shell", "feasible shell"], ["core", "optimal-set core"], ["out", "infeasible halo"]].map(([c, t]) => h("span", { class: `qa-k ${c}`, text: t })));
        fb.replaceChildren(bars([[`QAOA p = ${L.p}`, lm], ["random baseline", rm]]));
        if (cloud) cloud.setLevel(idx);
        ctx.announce(`QAOA p = ${L.p}: feasible ${pct(lm.feasible_fraction)}, optimal set ${pct(lm.p_optimal_assets)}; random baseline ${pct(rm.feasible_fraction)}, ${pct(rm.p_optimal_assets)}. ${QAOA_LABEL}.`);
      };
      draw();
      const f = (x) => ({ feasible: x.feasible_fraction, opt: x.p_optimal_assets });
      mountScene(ctx, "qaoa", { available: true }, ({ THREE, world, group }) =>
        (cloud = buildQaoaCloud(THREE, group, { levels: levels.map((r) => f(r.raw.metrics)), random: f(rm), n, level: idx }, world))).catch(() => {});
      const nr = (r) => h("span", { class: "fine", text: r.status.startsWith("not_") ? "not run" : r.status.replaceAll("_", " ") });
      const pm = (el, text) => h("div", { class: "pg-stat" }, el, ...whyBlock({ label: el.querySelector(".label") ? el.querySelector(".label").textContent : "", mean: text }));
      return h("div", {},
        h("div", { class: "pg-stats" },
          pm(stat({ label: "systems in this choice", cell: num(prob.assets.length, q.exact.objective.source), unit: `week ${prob.week} · ${prob.n_variables} QUBO variables` }),
            `Which of these ${prob.assets.length} systems should cut over in week ${prob.week}? The exact answer: ${q.exact.assets.join(", ")}.`),
          pm(sF, "Share of QAOA's answers that respect the weekly capacity and dependencies."),
          pm(sO, "Share of answers that are exactly the best choice; compare with the random baseline below it.")),
        main(h("div", {}, ctx.wsInfo && !ctx.wsInfo.read_only || ctx.ws === "demo" ? quantumPanel(ctx) : null, stageWrap,
          dd({ read: "left is QAOA on the simulator, right a uniform random guess. The bigger the shell, the more shots met the constraints; the bigger the core, the more shots hit the exact optimum." })), { title: "QAOA against the exact answer" }),
        detailsList([
          { title: "How it works", summary: "One week's choice becomes a small yes/no problem that QAOA samples.", body: bullets([
            ["The choice is written as a ", term("qubo", "QUBO"), " (at most 16 variables): value of migrating now, minus penalties for breaking capacity or dependencies."],
            ["Angles are tuned on a simulator, then the circuit is sampled 2048 times by ", term("qaoa", "QAOA"), " (p = 1…3)."],
            "Every sample is scored against the exact optimum found by checking every possible choice."]) },
          { title: "Why this method", summary: "QAOA fits small yes/no choices; the full schedule needs an exact optimiser.", body: bullets([
            "The full plan has hundreds of variables and continuous parts, far beyond today's quantum simulators.",
            "This small step lets us measure QAOA honestly against a known right answer."]) },
          { title: "Evidence & sources", summary: `QAOA run ${raw.run_id.slice(0, 12)} · ${raw.ts}`, body: h("div", {}, table({ caption: "QAOA runs versus random baseline", rows, columns: [
            { label: "p", render: (r) => (r.p === null ? "–" : String(r.p)), numeric: true },
            { label: "backend", render: (r) => h("span", {}, r.source_kind, h("span", { class: "sub", text: r.backend })) },
            { label: "shots", numeric: true, render: (r) => (r.cells ? String(r.raw.shots) : nr(r)) },
            ...q.columns.map(([k, label]) => ({ label, numeric: true, render: (r) => (r.cells ? r.cells[k] : nr(r)) })),
            { label: "status", render: (r) => (r.cells ? h("span", {}, chip("ok", "measured"), h("span", { class: "sub", text: r.raw.job_ids.length ? `job ${r.raw.job_ids.join(", ")}` : "no job ID (local)" }))
              : h("span", { class: "fine", text: r.status_cell.text })) }] }),
            dd({ read: `Particle allocation encodes each run's measured feasible fraction and P(optimal set) (${n} particles per cloud); positions are layout.` })) },
          { title: "Limits", summary: "Simulators only, 16 qubits at most; no quantum advantage is claimed.", body: bullets([
            QAOA_LABEL, "QpiAI Cloud: awaiting account activation; QpiAI-Indus-1 hardware is never used."]) }]),
        nextStep(ctx, "qaoa"));
    },
  });
  const stageWrap = h("div", {}, picker, stageEl, legend);
  ctx.root.append(h("div", { class: "grid" }, h("div", { class: "span-12" },
    pageHead(ctx, { route: "qaoa", title: "Wave selection", headline: "Is the set of systems chosen for one week the best one? A quantum algorithm cross-checks it on a simulator." }),
    body, honesty())));
}
