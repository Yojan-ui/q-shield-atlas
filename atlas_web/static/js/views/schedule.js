// Schedule: avoided exposure vs baselines per scenario, waves with gate status, assumptions (labelled).
import { h } from "../dom.js";
import { stat, statSkeleton } from "../components/stat.js";
import { chip } from "../components/chip.js";
import { table, tableSkeleton } from "../components/table.js";
import { emptyState } from "../components/states.js";
import { provAttr } from "../components/tooltip.js";
import { headlineAvoided } from "../model.js";
import { dataView, honesty, mountScene, notRun, section, stage, viewCss } from "./common.js";
import { buildLattice } from "../engine/lattice.js";
import { sound } from "../sound.js";
import { estimateBlock } from "../components/estimate.js";
import { bullets, detailsList, keyStats, main, nextStep, pageHead, dd } from "../components/page.js";
import { term } from "../glossary.js";
import { otherOptions, qualityBlock, whyMilp } from "../components/solvers.js";
import { runtimeChart } from "./bench.js";

// Remaining exposure-years per week for the optimised plan and both baselines (results.json remaining_by_week),
// one scenario, direct labels where the lines are furthest apart. Values are unweighted; the optimiser minimises the
// risk- and scenario-weighted total, so the lines can cross.
export function curveSeries(r, scenario) {
  const pick = (x) => ((x && x.remaining_by_week) || []).find((s) => s.scenario === scenario);
  const S = [["optimised plan (QpiAI Opt MILP)", r.exposure, "opt"], ["first-come-first-served", (r.baselines || {}).fcfs, "fcfs"], ["greedy (highest risk first)", (r.baselines || {}).greedy, "greedy"]];
  return S.map(([label, x, cls]) => ({ label, cls, points: (pick(x) || {}).points || [], produced: (x && x.produced_by) || {} })).filter((s) => s.points.length);
}

// x-axis end: the last week any line still changes, + 1 (at least 4); and the week every line has reached 0
export function axisEnd(S) {
  let active = 0, zero = 0;
  for (const s of S) {
    s.points.forEach((p, i) => { const nx = s.points[i + 1]; if (nx && nx.exposure_years !== p.exposure_years) active = Math.max(active, nx.week); });
    const z = s.points.find((p) => p.exposure_years <= 1e-9);
    zero = Math.max(zero, z ? z.week : s.points.at(-1).week);
  }
  return { end: Math.max(4, active + 1), zero };
}

// series whose points are identical are drawn once (+ an offset copy) under one merged label
export function mergeIdentical(S) {
  const same = (a, b) => a.points.length === b.points.length && a.points.every((p, i) => p.week === b.points[i].week && Math.abs(p.exposure_years - b.points[i].exposure_years) < 1e-9);
  const out = [];
  for (const s of S) {
    const twin = out.find((o) => same(o, s));
    if (twin) { twin.twins.push(s); twin.label = twin.twins.length === 2 ? "All three orders give the same plan" : `${[twin.short, ...twin.twins.map((t) => t.short)].join(" = ")} (identical plan)`; } else out.push({ ...s, twins: [] });
  }
  return out;
}

// right-hand labels at the line ends, pushed apart so they never overlap (min gap px), kept inside [top, bottom]
export function spreadLabels(ys, gap, top, bottom) {
  const o = ys.map((y, i) => ({ y, i })).sort((a, b) => a.y - b.y);
  for (let k = 1; k < o.length; k++) o[k].y = Math.max(o[k].y, o[k - 1].y + gap);
  const over = o.length ? o[o.length - 1].y - bottom : 0;
  if (over > 0) for (const x of o) x.y -= over;
  for (let k = 0; k < o.length; k++) o[k].y = Math.max(o[k].y, top + k * gap);
  const res = []; for (const x of o) res[x.i] = x.y; return res;
}

const SHORT = { opt: "Optimised", fcfs: "FCFS", greedy: "Greedy" };

export function solverLine(r) {
  const sr = (r.solver_runs || []).find((x) => /^schedule\.milp/.test(x.stage || "")) || (r.solver_runs || [])[0];
  if (!sr) return "Solved with: not yet run";
  const t = typeof sr.solver_time_s === "number" ? (sr.solver_time_s < 1 ? `${(sr.solver_time_s * 1000).toFixed(0)} ms` : `${sr.solver_time_s.toFixed(2)} s`) : "time not recorded";
  return `Solved with: ${sr.solver}${sr.mode ? ` (${sr.mode})` : ""}, status ${sr.status}, ${t}, job_id ${sr.job_id ?? `null (${sr.job_id_reason || "no reason recorded"})`}`;
}

// plain-words headline from the recorded comparison for one scenario
export function planHeadline(fcfs, greedy, scenario) {
  const f = fcfs && typeof fcfs.value === "number" ? fcfs.value : null, g = greedy && typeof greedy.value === "number" ? greedy.value : null;
  if (f === null) return "Plan comparison: not yet run";
  const fx = f.toFixed(3);
  if (Math.abs(f) < 5e-4 && (g === null || Math.abs(g) < 5e-4)) return `On this data all three orders leave the same exposure (Q-Day scenario ${scenario}); the optimised plan is never worse.`;
  if (g !== null && Math.abs(g) < 5e-4) return `On this data the optimal plan equals the simple risk-first plan; both avoid ${fx} exposure-years compared with first-come-first-served (${scenario}).`;
  return `The optimised plan avoids ${fx} exposure-years compared with first-come-first-served, and ${g === null ? "–" : g.toFixed(3)} compared with risk-first greedy (${scenario}).`;
}

function curves(r, scenario) {
  const S0 = curveSeries(r, scenario).map((s) => ({ ...s, short: SHORT[s.cls] }));
  if (!S0.length) return h("p", { class: "mv-note", text: "Exposure curves: not yet run" });
  const { end, zero } = axisEnd(S0);
  const cut = (s) => ({ ...s, points: s.points.filter((p) => p.week <= end) });
  const S = mergeIdentical(S0).map((s) => ({ ...cut(s), twins: s.twins.map(cut) }));
  const W = 1100, H = 420, L = 92, R = 400, T = 20, B = 54;  // wide right margin: end labels never clip
  const maxY = Math.max(...S.flatMap((s) => s.points.map((p) => p.exposure_years)), 1e-9);
  const X = (w) => L + (w / end) * (W - L - R), Y = (v) => T + (1 - v / maxY) * (H - T - B);
  const svg = h("svg", { viewBox: `0 0 ${W} ${H}`, class: "pl-chart", role: "img", "aria-label": `Remaining exposure-years by week, scenario ${scenario}: ${S.map((s) => s.label).join(", ")}` });
  for (let i = 0; i <= 4; i++) { const v = (maxY * i) / 4; svg.append(h("line", { ns: "svg", x1: L, x2: W - R, y1: Y(v), y2: Y(v), class: "bn-grid" }), h("text", { ns: "svg", x: L - 10, y: Y(v) + 5, "text-anchor": "end" }, v.toFixed(maxY < 1 ? 3 : maxY < 10 ? 1 : 0))); }
  for (let w = 0; w <= end; w += Math.max(1, Math.ceil(end / 12))) svg.append(h("text", { ns: "svg", x: X(w), y: H - B + 26, "text-anchor": "middle" }, String(w)));
  svg.append(h("text", { ns: "svg", x: (L + W - R) / 2, y: H - 4, "text-anchor": "middle" }, "week of the migration"),
    h("text", { ns: "svg", x: 14, y: T + (H - T - B) / 2, transform: `rotate(-90 14 ${T + (H - T - B) / 2})`, "text-anchor": "middle" }, "exposure-years still ahead"));
  const pts = (s, dy = 0) => s.points.map((p) => `${X(p.week).toFixed(1)},${(Y(p.exposure_years) + dy).toFixed(1)}`).join(" ");
  S.forEach((s) => {
    svg.append(h("polyline", { ns: "svg", class: `pl-line ${s.cls}`, points: pts(s) }));
    s.twins.forEach((t, k) => svg.append(h("polyline", { ns: "svg", class: `pl-line ${t.cls}`, points: pts(t, -4 * (k + 1)) })));  // identical plan: drawn offset, same data
    s.points.forEach((p) => svg.append(h("circle", { ns: "svg", class: `pl-pt ${s.cls}`, cx: X(p.week), cy: Y(p.exposure_years), r: 5, tabindex: "0",
      "data-prov": provAttr({ run_id: (s.produced.run_ids || []).join(", ") || "n/a", solver: s.produced.solver || "n/a", job_id: "none (local solve, no platform job ID)", ts: r.generated_at, note: `${scenario} · week ${p.week}: ${p.exposure_years.toFixed(2)} exposure-years` }, s.label) })));
  });
  const ends = S.map((s) => Y(s.points.at(-1).exposure_years));
  spreadLabels(ends, S.some((s) => s.twins.length) ? 52 : 30, T + 10, H - B - 16).forEach((y, k) => {
    const s = S[k];
    svg.append(h("line", { ns: "svg", x1: X(end) + 4, y1: ends[k], x2: X(end) + 16, y2: y - 5, class: "bn-grid" }),
      s.twins.length === 1 ? h("text", { ns: "svg", class: `pl-lab ${s.cls}`, x: X(end) + 20, y: y - 10 }, h("tspan", { ns: "svg", text: s.label.replace(" (identical plan)", "") }),
        h("tspan", { ns: "svg", x: X(end) + 20, dy: 24, text: "(identical plan)" })) : h("text", { ns: "svg", class: `pl-lab ${s.cls}`, x: X(end) + 20, y }, s.label));
  });
  const makespan = r.exposure && r.exposure.makespan_weeks;
  return h("div", {}, svg, dd({ shows: `All systems migrated by week ${makespan ?? "–"} (optimised plan); exposure still ahead reaches 0 by week ${zero}.`, read: `The axis stops at week ${end}, after which no line changes.` }));
}

// the optimisation itself: per-wave effort against the weekly capacity (results.waves + assumptions), and the
// weighted objective the MILP minimises for the optimised plan and both baselines (expected_weighted)
function optimisation(r) {
  const waves = r.waves || [], cap = (r.assumptions || {}).capacity_days_per_week;
  if (!waves.length || !cap) return h("p", { class: "mv-note", text: "Optimisation graph: not yet run" });
  const W = 1100, H = 300, L = 70, R = 20, T = 24, B = 50;
  const maxE = Math.max(cap, ...waves.map((w) => w.effort_days || 0)), n = waves.length;
  const bw = Math.min(46, ((W - L - R) / n) * 0.7), X = (i) => L + ((i + 0.5) * (W - L - R)) / n, Y = (v) => T + (1 - v / maxE) * (H - T - B);
  const svg = h("svg", { viewBox: `0 0 ${W} ${H}`, class: "pl-chart", role: "img", "aria-label": `Effort per wave against a capacity of ${cap} engineer-days per week, ${n} waves` });
  for (let i = 0; i <= 2; i++) { const v = (maxE * i) / 2; svg.append(h("line", { ns: "svg", x1: L, x2: W - R, y1: Y(v), y2: Y(v), class: "bn-grid" }), h("text", { ns: "svg", x: L - 10, y: Y(v) + 5, "text-anchor": "end" }, v.toFixed(0))); }
  waves.forEach((w, i) => {
    svg.append(h("rect", { ns: "svg", class: "pl-bar", x: X(i) - bw / 2, y: Y(w.effort_days || 0), width: bw, height: Y(0) - Y(w.effort_days || 0), tabindex: "0",
      "data-prov": provAttr({ run_id: ((r.exposure.produced_by || {}).run_ids || []).join(", ") || "n/a", solver: (r.exposure.produced_by || {}).solver || "n/a", job_id: "none (local solve)", ts: r.generated_at, note: `week ${w.week}: ${w.assets.length} systems, ${w.effort_days} of ${cap} engineer-days` }, `wave week ${w.week}`) }));
    if (n <= 24 || i % Math.ceil(n / 24) === 0) svg.append(h("text", { ns: "svg", x: X(i), y: H - B + 24, "text-anchor": "middle" }, String(w.week)));
  });
  svg.append(h("line", { ns: "svg", class: "pl-cap", x1: L, x2: W - R, y1: Y(cap), y2: Y(cap) }), h("text", { ns: "svg", class: "pl-lab", x: W - R, y: Y(cap) - 8, "text-anchor": "end" }, `capacity ${cap} engineer-days / week (assumption)`),
    h("text", { ns: "svg", x: (L + W - R) / 2, y: H - 4, "text-anchor": "middle" }, "wave (week) · bar = assumed effort of the systems in it"));
  return h("div", {}, objectiveChart(r), h("h3", { class: "pl-h3", text: "Effort per wave vs team capacity (the real plan)" }), svg,
    dd({ read: "each bar is one weekly wave of the optimised plan; no bar may exceed the capacity line, and a system never moves before what it depends on." }));
}

// the objective the MILP minimises (risk- and scenario-weighted exposure), per Q-Day scenario, for MILP / FCFS / Greedy
export function objectiveRows(r) {
  const plans = [["opt", "MILP (QpiAI Opt)", r.exposure], ["fcfs", "FCFS", (r.baselines || {}).fcfs], ["greedy", "Greedy", (r.baselines || {}).greedy]].filter(([, , x]) => x && x.per_scenario);
  const milp = Object.fromEntries(((r.exposure || {}).per_scenario || []).map((x) => [x.scenario, x.weighted_exposure]));
  return ((r.scenarios || []).map((sc) => ({ scenario: sc.name, year: sc.year, bars: plans.map(([cls, label, x]) => {
    const v = (x.per_scenario.find((y) => y.scenario === sc.name) || {}).weighted_exposure;
    const saved = cls === "opt" || !(v > 0) || milp[sc.name] === undefined ? null : (100 * (v - milp[sc.name])) / v;
    return { cls, label, value: v, saved };
  }).filter((b) => typeof b.value === "number") })).filter((g) => g.bars.length));
}

function objectiveChart(r) {
  const G = objectiveRows(r);
  if (!G.length) return h("p", { class: "mv-note", text: "Objective by scenario: not yet run" });
  const W = 1100, H = 360, L = 80, R = 20, T = 50, B = 60;
  const maxV = Math.max(...G.flatMap((g) => g.bars.map((b) => b.value)), 1e-9), gw = (W - L - R) / G.length, bw = Math.min(110, (gw * 0.8) / 3);
  const Y = (v) => T + (1 - v / maxV) * (H - T - B);
  const svg = h("svg", { viewBox: `0 0 ${W} ${H}`, class: "pl-chart", role: "img", "aria-label": `Weighted exposure by Q-Day scenario for MILP, FCFS and Greedy` });
  for (let i = 0; i <= 2; i++) { const v = (maxV * i) / 2; svg.append(h("line", { ns: "svg", x1: L, x2: W - R, y1: Y(v), y2: Y(v), class: "bn-grid" }), h("text", { ns: "svg", x: L - 10, y: Y(v) + 5, "text-anchor": "end" }, v.toFixed(maxV < 10 ? 2 : 0))); }
  G.forEach((g, gi) => {
    const x0 = L + gi * gw + (gw - 3 * bw - 16) / 2;
    g.bars.forEach((b, bi) => {
      const x = x0 + bi * (bw + 8);
      svg.append(h("rect", { ns: "svg", class: `pl-obar ${b.cls}`, x, y: Y(b.value), width: bw, height: Y(0) - Y(b.value), tabindex: "0",
        "data-prov": provAttr({ run_id: ((((b.cls === "opt" ? r.exposure : r.baselines[b.cls]) || {}).produced_by || {}).run_ids || []).join(", ") || "n/a", solver: (((b.cls === "opt" ? r.exposure : r.baselines[b.cls]) || {}).produced_by || {}).solver || "n/a", job_id: "none (local solve)", ts: r.generated_at, note: `${g.scenario}: weighted exposure ${b.value.toFixed(3)}` }, `${b.label} · ${g.scenario}`) }),
        h("text", { ns: "svg", class: "pl-ov", x: x + bw / 2, y: Y(b.value) - 10, "text-anchor": "middle" }, b.value.toFixed(maxV < 10 ? 3 : 1)),
        h("text", { ns: "svg", class: `pl-os ${b.cls}${Y(0) - Y(b.value) > 44 ? "" : " out"}`, x: x + bw / 2, y: Y(0) - Y(b.value) > 44 ? Y(b.value) + 24 : Y(b.value) - 32, "text-anchor": "middle" }, b.cls === "opt" ? "optimal" : Math.abs(b.saved) < 0.005 ? "same" : `−${b.saved.toFixed(2)}%`),
        h("text", { ns: "svg", x: x + bw / 2, y: H - B + 22, "text-anchor": "middle" }, b.label.split(" ")[0]));
    });
    svg.append(h("text", { ns: "svg", class: "pl-lab", x: L + gi * gw + gw / 2, y: H - 8, "text-anchor": "middle" }, `Q-Day ${g.year}`));
  });
  return h("div", {}, svg, dd({ read: "bar height is the objective the MILP minimises (risk- and scenario-weighted exposure-years) for each Q-Day year; lower is better. Inside each FCFS / Greedy bar: how much lower (in %) the MILP's value is than that plan's." }));
}

export async function mount(ctx) {
  await viewCss("plan");
  let scenario = ctx.query.get("scenario");
  let lattice = null;
  const weekOut = h("output", { class: "num" });
  const weekIn = h("input", { type: "range", min: "0", max: "0", step: "1", value: "0", "aria-label": "week" });
  const stageEl = stage(ctx, { label: "The plan over time: scrub the week; a crystal turns cyan when its wave passed the lab gates, and its HNDL beam goes out." });
  let waveWeeks = [], lastWeek = null;
  // the stage sits under the hero stats (hero number above the fold); moved into the grid when the data renders
  const stageWrap = h("div", {}, stageEl, h("label", { class: "sg-row week-scrub" }, h("span", { class: "eyebrow", style: { margin: 0 }, text: "week" }), weekIn, weekOut));
  const setWeek = (wk) => {
    weekOut.textContent = `week ${wk}`;
    if (ctx.world.uniforms) ctx.world.uniforms.uWeek.value = wk;
    if (lastWeek !== null && waveWeeks.some((w) => (w > lastWeek && w <= wk) || (w <= lastWeek && w > wk))) sound.tick();  // a wave flipped
    lastWeek = wk;
  };
  addEventListener("keydown", (e) => {  // ←/→ weeks, [ ] scenarios
    if (e.target instanceof Element && e.target.closest("input, textarea, select, dialog")) return;
    if (e.key === "ArrowLeft" || e.key === "ArrowRight") { weekIn.value = String(Math.min(Number(weekIn.max), Math.max(0, Number(weekIn.value) + (e.key === "ArrowRight" ? 1 : -1)))); weekIn.dispatchEvent(new Event("input")); }
    if (e.key === "[" || e.key === "]") { const b = [...ctx.root.querySelectorAll("[role=radio]")], i = b.findIndex((x) => x.getAttribute("aria-checked") === "true"); const n = b[i + (e.key === "]" ? 1 : -1)]; if (n) n.click(); }
  }, { signal: ctx.signal });
  weekIn.addEventListener("input", () => { setWeek(Number(weekIn.value)); ctx.setQuery({ week: weekIn.value }); }, { signal: ctx.signal });
  ctx.store.get(ctx.ws, "scene", { signal: ctx.signal }).then((scene) => {
    if (!scene.available) return;
    waveWeeks = (scene.waves || []).map((w) => w.week);
    weekIn.max = String(scene.weeks.length - 1);
    const q = Number(ctx.query.get("week"));
    weekIn.value = String(Number.isFinite(q) && ctx.query.get("week") !== null ? Math.min(q, scene.weeks.length - 1) : scene.weeks.length - 1);
    return mountScene(ctx, "schedule", scene, ({ THREE, world, group }) => {
      lattice = buildLattice(THREE, group, scene, world.uniforms);
      world.fit(group, (scene.nodes || []).map((n) => n.pos));  // auto-fit, refit on resize
      if (scenario) lattice.setScenario(scenario);
      setWeek(Number(weekIn.value));
      return lattice.hooks(ctx, stageEl);
    });
  }).catch(() => {});
  const body = dataView(ctx, {
    skeleton: () => h("div", { class: "grid" }, h("div", { class: "span-12" }, statSkeleton()), h("div", { class: "span-12" }, tableSkeleton(4))),
    render: ({ model: m }) => {
      if (!m || !m.chart.available) return emptyState(notRun(ctx, "Migration plan"));
      const names = m.scenarios.map((s) => s.name);
      if (!names.includes(scenario)) scenario = names[0];
      const statsEl = h("div", {}), heroEl = h("section", { class: "pl-hero" });
      const benchLink = h("span");  // "Compare solvers" only when this workspace has Benchmark optimizer data
      const solversEl = h("div", { class: "sv-wrap" }, h("p", { class: "mv-note", text: "Loading the solver benchmark…" }));
      ctx.store.get(ctx.ws, "bench", { signal: ctx.signal }).then((P) => {
        if (P && P.bench) benchLink.replaceChildren(" · ", h("a", { href: `/w/${ctx.ws}/bench?tab=optimizers`, text: "Compare solvers →" }));
        solversEl.replaceChildren(qualityBlock(P, ctx),
          P && P.bench ? h("div", {}, h("h3", { class: "pl-h3", text: "Runtime vs problem size (log scale)" }), runtimeChart(P.bench.rows, P.bench.instances)) : null);
      }).catch(() => { solversEl.replaceChildren(qualityBlock(null, ctx)); });
      const picker = h("div", { class: "sg-row", role: "radiogroup", "aria-label": "CRQC scenario" });
      const draw = () => {
        const a = headlineAvoided(m, scenario);
        heroEl.replaceChildren(
          h("p", { class: "pl-head", tabindex: "0", "data-prov": a.fcfs.source ? provAttr(a.fcfs.source, "avoided vs FCFS") : null, text: planHeadline(a.fcfs, a.greedy, scenario) }),
          h("p", { class: "pl-solver mono" }, solverLine(m.results), benchLink),
          h("h2", { class: "mv-h2", text: "Comparison: exposure still ahead, week by week" }),
          curves(m.results, scenario),
          dd({ read: "each line is how much exposure (years that data stays readable after Q-Day) is still ahead at each week. Lower is better; the gap at week 0 is the total avoided. Lines are unweighted exposure-years; the optimiser minimises the risk- and scenario-weighted total, so lines can cross." }));
        heroEl.append(h("section", { class: "pl-opt" }, h("h2", { class: "mv-h2", text: "Optimisation: the objective by Q-Day scenario" }), optimisation(m.results)),
          h("section", { class: "pl-opt" }, h("h2", { class: "mv-h2", text: "Why MILP, and how the solvers compare" }), whyMilp(m.results), solversEl, otherOptions()));
        statsEl.replaceChildren(keyStats([
          { label: "weeks to migrate", cell: m.makespan, unit: "optimised plan", mean: "When the last wave finishes, at the assumed team capacity." },
          { label: "exposure avoided vs first-come-first-served", cell: a.fcfs, unit: "exposure-years", mean: "Less time that sensitive data stays readable to a future quantum computer, compared with the simple order." },
          { label: "exposure avoided vs greedy", cell: a.greedy, unit: "exposure-years", mean: "The same comparison against a smarter rule of thumb (highest risk first)." }]));
        picker.replaceChildren(...m.scenarios.map((s) => h("button", { class: `btn${s.name === scenario ? " primary" : ""}`, type: "button", role: "radio", "aria-checked": String(s.name === scenario),
          onclick: () => { scenario = s.name; ctx.setQuery({ scenario }); if (lattice) lattice.setScenario(scenario); draw(); }, text: `${s.name} · CRQC ${s.year}` })));
        ctx.announce(`Scenario ${scenario}: ${a.fcfs.text} exposure-years avoided versus FCFS, ${a.greedy.text} versus greedy.`);
      };
      draw();
      const a = m.results.assumptions;
      return h("div", {},
        h("div", { class: "pg-actions", style: { marginTop: 0, marginBottom: "var(--s-4)" } }, h("span", { class: "fine", text: "Q-Day assumption:" }), picker), heroEl, statsEl,
        main(h("div", {}, estimateBlock(ctx), table({ caption: "Migration waves", rows: m.waves,
          expand: (w) => ({ why: h("span", {}, "Systems: ", w.assets.map((id, i) => [i ? ", " : "", h("a", { href: `/w/${ctx.ws}/asset/${encodeURIComponent(id)}`, text: id })]), `. Placed in week ${w.week} to cut weighted exposure fastest within capacity.`),
            run_id: w.source && w.source.run_id, ts: w.source && w.source.ts, technical: w.source && w.source.solver }), columns: [
          { label: "week", numeric: true, render: (w) => String(w.week) },
          { label: "systems", numeric: true, render: (w) => String(w.assets.length) },
          { label: "effort (days)", numeric: true, optional: true, render: (w) => String((m.results.waves.find((x) => x.week === w.week) || {}).effort_days ?? "–") },
          { label: "gate", render: (w) => chip(w.status) }] })), { title: "The plan, week by week" }),
        stageWrap,
        detailsList([
          { title: "How it works", summary: "An exact optimiser places every system in a week, within capacity and dependencies.", body: bullets([
            ["The plan is a ", term("milp", "MILP"), " solved by QpiAI Opt locally; it reports a proven global optimum."],
            ["Exposure counts the years data stays readable after ", term("crqc", "Q-Day"), ": shelf life + time to migrate − years until Q-Day."],
            "A system never migrates before the systems it depends on."]) },
          { title: "Why this method", summary: "A proven best plan, compared on the same data with two simple rules.", body: bullets([
            "First-come-first-served and greedy are what teams do by hand; the optimiser is never worse than either.",
            "Several Q-Day years are planned for at once, because nobody knows the date."]) },
          { title: "Evidence & sources", summary: m.solver, body: h("div", {}, bullets([`Solver: ${m.solver}.`, "Each solve records job_id null (local solves issue none), a run_id and SHA-256 hashes of inputs and output."]),
            h("dl", { class: "kv" },
              h("dt", { text: "capacity" }), h("dd", { class: "mono", text: `${a.capacity_days_per_week} engineer-days / week` }),
              h("dt", { text: "start year" }), h("dd", { class: "mono", text: String(a.start_year) }),
              h("dt", { text: "scenarios" }), h("dd", { class: "mono", text: a.scenarios.map((s) => `${s.name} (w ${s.weight})`).join(" · ") }),
              h("dt", { text: "effort / kind" }), h("dd", { class: "mono", text: Object.entries(a.effort_days_by_kind).map(([k, v]) => `${k} ${v} d`).join(" · ") })), chip("assumption", "assumptions, not measurements")) },
          { title: "Limits", summary: "Effort, risk and shelf life are assumptions, not measurements.", body: bullets([
            "Record real engineer-days (calibration) to replace assumed effort.",
            "Chart values are unweighted exposure-years; the optimiser minimises the risk- and scenario-weighted total."]) }]),
        nextStep(ctx, "schedule"));
    },
  });
  ctx.root.append(h("div", { class: "grid" }, h("div", { class: "span-12" },
    pageHead(ctx, { route: "schedule", title: "Schedule", headline: "Each line is the quantum exposure still ahead, week by week: the optimised order against two simple orders on the same data." }), body, honesty())));
}
