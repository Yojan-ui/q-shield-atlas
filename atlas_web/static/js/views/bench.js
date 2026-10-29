// Benchmark: the same link cutover instances solved by classical (exact, MILP), quantum (QAOA, simulator) and
// hybrid solvers (python -m bench -> out/bench.json, signed into the Proof Chain). Every number is from that file.
import { h, icon } from "../dom.js";
import { chip } from "../components/chip.js";
import { table, tableSkeleton } from "../components/table.js";
import { emptyState } from "../components/states.js";
import { toast } from "../components/toast.js";
import { confirmDialog } from "../components/dialog.js";
import { dataView, header, honesty, section, wsEyebrow } from "./common.js";

// categorical, fixed order (validated: dark surface, adjacent CVD ΔE >= 8.4, normal-vision >= 19.3)
export const SERIES = [
  { key: "exact", label: "Exact (brute force)", color: "#3987e5", family: "classical" },
  { key: "milp", label: "MILP (QpiAI Opt)", color: "#d95926", family: "classical" },
  { key: "random", label: "Random sampling", color: "#199e70", family: "baseline" },
  { key: "qaoa1", label: "QAOA p=1 (simulator)", color: "#c98500", family: "quantum (simulator)" },
  { key: "hybrid", label: "Hybrid (QAOA + repair)", color: "#d55181", family: "hybrid" },
];
export const seriesKey = (r) => (r.solver === "qaoa" ? `qaoa${r.p}` : r.solver);
const fmt = (x, d = 3) => (x === null || x === undefined ? "–" : Number(x).toFixed(d));
const secs = (x) => (x === null || x === undefined ? "–" : x < 0.01 ? `${(x * 1000).toFixed(2)} ms` : `${x.toFixed(2)} s`);

// runtime (log scale) against problem size, one line per solver; a <title> on every point is its tooltip
export function runtimeChart(rows, instances) {
  const W = 640, H = 300, L = 56, R = 150, T = 16, B = 40;
  const xs = instances.map((i) => i.n_variables), x0 = Math.min(...xs), x1 = Math.max(...xs);
  const pts = rows.filter((r) => r.status === "ok" && r.runtime_s > 0 && SERIES.some((s) => s.key === seriesKey(r)));
  const lo = Math.floor(Math.log10(Math.min(...pts.map((r) => r.runtime_s)))), hi = Math.ceil(Math.log10(Math.max(...pts.map((r) => r.runtime_s))));
  const X = (n) => L + ((n - x0) / Math.max(1, x1 - x0)) * (W - L - R);
  const Y = (t) => T + (1 - (Math.log10(t) - lo) / Math.max(1, hi - lo)) * (H - T - B);
  const svg = h("svg", { viewBox: `0 0 ${W} ${H}`, class: "bn-chart", role: "img", "aria-label": "Runtime against problem size per solver, log scale" });
  for (let e = lo; e <= hi; e++) {
    svg.append(h("line", { ns: "svg", x1: L, x2: W - R, y1: Y(10 ** e), y2: Y(10 ** e), class: "bn-grid" }),
      h("text", { ns: "svg", x: L - 8, y: Y(10 ** e) + 4, class: "bn-tick", "text-anchor": "end" }, e >= 0 ? `${10 ** e} s` : `${10 ** (e + 3)} ms`));
  }
  for (const n of xs) svg.append(h("text", { ns: "svg", x: X(n), y: H - B + 18, class: "bn-tick", "text-anchor": "middle" }, String(n)));
  svg.append(h("text", { ns: "svg", x: (L + W - R) / 2, y: H - 6, class: "bn-axis", "text-anchor": "middle" }, "problem size (QUBO variables)"));
  const ends = [];
  for (const s of SERIES) {
    const line = pts.filter((r) => seriesKey(r) === s.key).sort((a, b) => a.n_variables - b.n_variables);
    if (!line.length) continue;
    // hybrid reuses QAOA p=1 samples, so the two lines can coincide: hybrid is dashed so both stay visible
    svg.append(h("polyline", { ns: "svg", points: line.map((r) => `${X(r.n_variables)},${Y(r.runtime_s)}`).join(" "), class: "bn-line", stroke: s.color,
      "stroke-dasharray": s.key === "hybrid" ? "6 4" : null }));
    for (const r of line) svg.append(h("circle", { ns: "svg", cx: X(r.n_variables), cy: Y(r.runtime_s), r: 4, fill: s.color, class: "bn-dot" },
      h("title", { ns: "svg" }, `${s.label} · n = ${r.n_variables}: ${secs(r.runtime_s)}, objective ${fmt(r.objective, 4)} (optimum ${fmt(r.optimum, 4)})`)));
    const last = line[line.length - 1];
    ends.push({ x: X(last.n_variables) + 8, y: Y(last.runtime_s) + 4, text: s.label.split(" (")[0] });
  }
  ends.sort((a, b) => a.y - b.y).forEach((e, i, all) => { if (i && e.y - all[i - 1].y < 14) e.y = all[i - 1].y + 14; });  // no overlapping end labels
  for (const e of ends) svg.append(h("text", { ns: "svg", x: e.x, y: e.y, class: "bn-label" }, e.text));
  return svg;
}

export async function mount(ctx) {
  const ro = !ctx.wsInfo || ctx.wsInfo.read_only, canRun = ctx.me.role !== "viewer" && !ro;
  const runBtn = h("button", { class: "btn primary", type: "button", disabled: !canRun }, icon("play"), "Run benchmark");
  runBtn.addEventListener("click", async () => {
    if (!(await confirmDialog({ title: "Run the benchmark?", body: "Solves every instance with exact, MILP (QpiAI Opt local, verifies the API key online), random sampling, QAOA p = 1…3 and hybrid on this machine (about 2 minutes), then signs the result into the Proof Chain. No QpiAI credits are used.", confirm: "Run" }))) return;
    try {
      const r = await ctx.api.post(`/api/workspaces/${ctx.ws}/bench`, {});
      toast(`benchmark run ${r.run_id} started; follow it on the pipeline page`, { tone: "info" });
    } catch (err) { toast(err.message, { tone: "error", detail: err.code }); }
  }, { signal: ctx.signal });
  const body = dataView(ctx, {
    keys: ["bench"],
    skeleton: () => tableSkeleton(8),
    render: ({ bench: P }) => {
      const b = P.bench;
      if (!b) return emptyState({ title: `Benchmark: ${P.status_text}`, body: ro ? "This read-only snapshot has no benchmark run. Open a workspace with a pipeline run and run it there." : "Run the pipeline, then the benchmark. Nothing is shown until a logged run exists.", action: null });
      const legend = h("ul", { class: "bn-legend", "aria-label": "Chart legend" }, SERIES.map((s) =>
        h("li", {}, h("span", { class: "bn-swatch", style: { background: s.color } }), `${s.label} · ${s.family}`)));
      const nr = (r) => h("span", { class: "fine", text: r.status_text || r.status });
      return h("div", { class: "grid" },
        h("div", { class: "span-12 bn-claim" }, chip("recorded", "measured"), h("p", { text: b.label })),
        section("Runtime against problem size", h("div", {}, runtimeChart(b.rows, b.instances), legend,
          h("p", { class: "fine", text: `Wall-clock time on this machine (${b.environment.machine}, Python ${b.environment.python}). QAOA time includes classical angle tuning (COBYLA, ${b.qaoa_config.restarts} restarts) and ${b.qaoa_config.shots} shots. Hover a point for its numbers; the table below holds them all.` })),
          { aside: h("span", { class: "fine mono", text: `run ${b.run_id.slice(0, 12)} · ${b.ts}${P.ledger_index !== null ? ` · Proof Chain #${P.ledger_index}` : " · not yet signed"}` }) }),
        section("Solution quality, runtime and size", table({ caption: "Benchmark rows", rows: b.rows, columns: [
          { label: "instance", key: "instance", mono: true },
          { label: "variables", numeric: true, render: (r) => String(r.n_variables) },
          { label: "solver", render: (r) => h("span", {}, r.solver === "qaoa" ? `QAOA p=${r.p}` : (SERIES.find((s) => s.key === r.solver) || { label: r.solver }).label.replace(" (simulator)", ""), h("span", { class: "sub", text: r.family })) },
          { label: "objective", numeric: true, render: (r) => (r.status === "ok" ? fmt(r.objective, 4) : nr(r)) },
          { label: "approx. ratio", numeric: true, render: (r) => (r.status === "ok" ? fmt(r.approximation_ratio, 3) : "–") },
          { label: "P(optimum)", numeric: true, optional: true, render: (r) => (r.p_optimal_assets === null || r.p_optimal_assets === undefined ? "–" : `${(r.p_optimal_assets * 100).toFixed(1)} %`) },
          { label: "runtime", numeric: true, render: (r) => (r.status === "ok" ? secs(r.runtime_s) : "–") },
          { label: "status", render: (r) => (r.status === "ok" ? chip("ok", r.feasible ? "feasible" : "infeasible") : chip("NOT_RUN", r.status.replaceAll("_", " "))) }] })),
        section("Where QAOA is limited", h("ul", { class: "bn-limits" }, ...b.limits.map((t) => h("li", { text: t })),
          h("li", { text: `Hardware: ${b.hardware}.` }),
          h("li", { text: `Full migration schedule (${b.full_schedule.assets} assets): MILP only. QAOA ${b.full_schedule.qaoa}.` }))),
        h("p", { class: "span-12 fine", text: `Ratio = solver objective ÷ exact optimum (1 = optimal). P(optimum) = share of shots on the optimal selection. ${b.instances.length} instances; largest uses ${Math.max(...b.instances.map((i) => i.statevector_amplitudes))} statevector amplitudes.` }),
        h("p", { class: "span-12 fine", text: `Exact optimum per instance: ${b.instances.map((i) => `n=${i.n_variables}: ${fmt(i.optimum, 4)}`).join(" · ")}.` }));
    },
  });
  ctx.root.append(h("div", { class: "grid" },
    h("div", { class: "span-12" }, header({ eyebrow: wsEyebrow(ctx), title: "Benchmark", lede: "The same link cutover instances solved by classical, quantum (simulated) and hybrid solvers: solution quality, runtime and problem size side by side.",
      actions: h("div", { class: "actions" }, runBtn, h("p", { class: "fine", text: ro ? "Read-only snapshot." : ctx.me.role === "viewer" ? "An operator runs the benchmark." : "Local only; no QpiAI credits." })) })),
    h("div", { class: "span-12" }, body), h("div", { class: "span-12" }, honesty())));
}
