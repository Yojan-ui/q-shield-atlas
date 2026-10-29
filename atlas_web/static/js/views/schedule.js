// Schedule: avoided exposure vs baselines per scenario, waves with gate status, assumptions (labelled).
import { h } from "../dom.js";
import { stat, statSkeleton } from "../components/stat.js";
import { chip } from "../components/chip.js";
import { table, tableSkeleton } from "../components/table.js";
import { emptyState } from "../components/states.js";
import { provAttr } from "../components/tooltip.js";
import { headlineAvoided } from "../model.js";
import { dataView, header, honesty, mountScene, notRun, section, stage, viewCss, wsEyebrow } from "./common.js";
import { buildLattice } from "../engine/lattice.js";
import { sound } from "../sound.js";
import { estimateBlock } from "../components/estimate.js";
import { bullets, detailsList, keyStats, main, nextStep, pageHead } from "../components/page.js";
import { term } from "../glossary.js";

// Remaining exposure-years per week for the optimised plan and both baselines (results.json remaining_by_week),
// one scenario, direct labels where the lines are furthest apart. Values are unweighted; the optimiser minimises the
// risk- and scenario-weighted total, so the lines can cross.
export function curveSeries(r, scenario) {
  const pick = (x) => ((x && x.remaining_by_week) || []).find((s) => s.scenario === scenario);
  const S = [["optimised plan (QpiAI Opt MILP)", r.exposure, "opt"], ["first-come-first-served", (r.baselines || {}).fcfs, "fcfs"], ["greedy (highest risk first)", (r.baselines || {}).greedy, "greedy"]];
  return S.map(([label, x, cls]) => ({ label, cls, points: (pick(x) || {}).points || [], produced: (x && x.produced_by) || {} })).filter((s) => s.points.length);
}

export function labelWeek(series, k) {  // the week where series k is furthest from the others (ties: earliest)
  const own = series[k].points;
  let best = 0, bestD = -1;
  own.forEach((p, i) => {
    if (i === own.length - 1) return;
    const d = Math.min(...series.filter((_, j) => j !== k).map((o) => Math.abs((o.points[i] || o.points.at(-1)).exposure_years - p.exposure_years)));
    if (d > bestD) { bestD = d; best = i; }
  });
  return best;
}

function curves(r, scenario) {
  const S = curveSeries(r, scenario);
  if (!S.length) return h("p", { class: "mv-note", text: "Exposure curves: not yet run" });
  const W = 1100, H = 440, L = 70, R = 20, T = 20, B = 54;
  const maxW = Math.max(...S.flatMap((s) => s.points.map((p) => p.week))), maxY = Math.max(...S.flatMap((s) => s.points.map((p) => p.exposure_years)));
  const X = (w) => L + (w / Math.max(1, maxW)) * (W - L - R), Y = (v) => T + (1 - v / Math.max(1e-9, maxY)) * (H - T - B);
  const svg = h("svg", { viewBox: `0 0 ${W} ${H}`, class: "pl-chart", role: "img", "aria-label": `Remaining exposure-years by week, scenario ${scenario}: ${S.map((s) => s.label).join(", ")}` });
  for (let i = 0; i <= 4; i++) { const v = (maxY * i) / 4; svg.append(h("line", { ns: "svg", x1: L, x2: W - R, y1: Y(v), y2: Y(v), class: "bn-grid" }), h("text", { ns: "svg", x: L - 10, y: Y(v) + 5, "text-anchor": "end" }, v.toFixed(0))); }
  for (let w = 0; w <= maxW; w++) svg.append(h("text", { ns: "svg", x: X(w), y: H - B + 26, "text-anchor": "middle" }, String(w)));
  svg.append(h("text", { ns: "svg", x: (L + W - R) / 2, y: H - 4, "text-anchor": "middle" }, "week of the migration"),
    h("text", { ns: "svg", x: 14, y: T + (H - T - B) / 2, transform: `rotate(-90 14 ${T + (H - T - B) / 2})`, "text-anchor": "middle" }, "exposure-years still ahead"));
  S.forEach((s, k) => {
    svg.append(h("polyline", { ns: "svg", class: `pl-line ${s.cls}`, points: s.points.map((p) => `${X(p.week).toFixed(1)},${Y(p.exposure_years).toFixed(1)}`).join(" ") }));
    s.points.forEach((p) => svg.append(h("circle", { ns: "svg", class: `pl-pt ${s.cls}`, cx: X(p.week), cy: Y(p.exposure_years), r: 5, tabindex: "0",
      "data-prov": provAttr({ run_id: (s.produced.run_ids || []).join(", ") || "n/a", solver: s.produced.solver || "n/a", job_id: "none (local solve, no platform job ID)", ts: r.generated_at, note: `${scenario} · week ${p.week}: ${p.exposure_years.toFixed(2)} exposure-years` }, s.label) })));
    const i = labelWeek(S, k), p = s.points[i];
    svg.append(h("text", { ns: "svg", class: `pl-lab ${s.cls}`, x: X(p.week) + 12, y: Y(p.exposure_years) - 12 }, s.label));
  });
  return svg;
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
  const stageWrap = h("div", { class: "tech" }, stageEl, h("label", { class: "sg-row week-scrub" }, h("span", { class: "eyebrow", style: { margin: 0 }, text: "week" }), weekIn, weekOut));
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
      const picker = h("div", { class: "sg-row", role: "radiogroup", "aria-label": "CRQC scenario" });
      const draw = () => {
        const a = headlineAvoided(m, scenario);
        heroEl.replaceChildren(
          h("p", { class: "pl-call" }, "Exposure-years avoided vs FCFS: ", h("span", { class: "num", tabindex: "0", "data-prov": a.fcfs.source ? provAttr(a.fcfs.source, "avoided vs FCFS") : null, text: a.fcfs.text }),
            h("span", { class: "pl-sub", text: `vs greedy: ${a.greedy.text} · scenario ${scenario}` })),
          curves(m.results, scenario),
          h("p", { class: "mv-how", text: "How to read this: each line is how much exposure (years that data stays readable after Q-Day) is still ahead at each week. Lower is better; the gap at week 0 is the total avoided. Lines are unweighted exposure-years; the optimiser minimises the risk- and scenario-weighted total, so lines can cross." }));
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
        main(h("div", {}, estimateBlock(ctx), table({ caption: "Migration waves", rows: m.waves, columns: [
          { label: "week", render: (w) => h("span", { class: "num", tabindex: "0", "data-prov": provAttr(w.source, `wave week ${w.week}`), text: String(w.week) }), numeric: true },
          { label: "systems", render: (w) => h("span", {}, w.assets.map((id, i) => [i ? ", " : "", h("a", { href: `/w/${ctx.ws}/asset/${encodeURIComponent(id)}`, text: id })])) },
          { label: "effort (engineer-days)", numeric: true, render: (w) => String((m.results.waves.find((x) => x.week === w.week) || {}).effort_days ?? "–") },
          { label: "gate result", render: (w) => chip(w.status) }] })), { title: "The plan, week by week" }),
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
