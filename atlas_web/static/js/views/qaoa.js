// QAOA: measured cross-check vs brute force; cloud per p (?p=); QCloud rows show status_text only.
import { h } from "../dom.js";
import { stat, statSkeleton } from "../components/stat.js";
import { chip } from "../components/chip.js";
import { table, tableSkeleton } from "../components/table.js";
import { emptyState } from "../components/states.js";
import { num, QAOA_LABEL } from "../model.js";
import { dataView, header, honesty, mountScene, notRun, section, stage, wsEyebrow } from "./common.js";
import { buildQaoaCloud } from "../scenes/qaoa.js";

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
      const sF = stat({ label: "feasible share", cell: null, tone: "hero accent" }), sO = stat({ label: "P(optimal set)", cell: null, tone: "accent" });
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
      return h("div", { class: "grid" },
        h("div", { class: "span-12 stats" },
          stat({ label: "exact optimum", cell: q.exact.objective, unit: `${raw.exact.method} · ${q.exact.assets.join(", ")}` }), sF, sO,
          stat({ label: "QUBO variables", cell: num(prob.n_variables, q.exact.objective.source), unit: `${prob.assets.length} assets + ${prob.slack_bits} slack bits · week ${prob.week}` })),
        h("p", { class: "span-12 fine", text: `Particle allocation encodes each run's measured feasible fraction and P(optimal set) (${n} particles per cloud, one per 1/${n} of shots); positions are layout. results.json holds no per-bitstring counts, so none are drawn.` }),
        section("Runs", table({ caption: "QAOA runs versus random baseline", rows, columns: [
          { label: "p", render: (r) => (r.p === null ? "–" : String(r.p)), numeric: true },
          { label: "source", render: (r) => h("span", {}, r.source_kind, h("span", { class: "sub", text: r.backend })) },
          { label: "shots", numeric: true, render: (r) => (r.cells ? String(r.raw.shots) : nr(r)) },
          ...q.columns.map(([k, label]) => ({ label, numeric: true, render: (r) => (r.cells ? r.cells[k] : nr(r)) })),
          { label: "status", render: (r) => (r.cells ? h("span", {}, chip("ok", "measured"), h("span", { class: "sub", text: r.raw.job_ids.length ? `job ${r.raw.job_ids.join(", ")}` : "no job ID (local)" }))
            : h("span", { class: "fine", text: r.status_cell.text })) }] }),
        { aside: h("span", { class: "fine mono", text: `run ${raw.run_id.slice(0, 12)} · ${raw.ts}` }) }),
        h("p", { class: "span-12 fine", text: q.full_label }));
    },
  });
  ctx.root.append(h("div", { class: "grid" },
    h("div", { class: "span-12" }, header({ eyebrow: wsEyebrow(ctx), title: "QAOA cross-check",
      lede: "One week's wave selection as a QUBO, sampled by QAOA (p = 1…3) on a local statevector simulator and compared with the exact brute-force optimum and a uniform random baseline.",
      aside: h("div", { class: "qa-claim" }, h("p", { class: "eyebrow", text: "claim" }), h("p", { class: "qa-claim-text", text: QAOA_LABEL }), chip("recorded", "checked against brute force")) })),
    h("div", { class: "span-12" }, stageEl, legend, picker), h("div", { class: "span-12" }, body), h("div", { class: "span-12" }, honesty())));
}
