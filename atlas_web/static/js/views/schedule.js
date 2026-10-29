// Schedule: avoided exposure vs baselines per scenario, waves with gate status, assumptions (labelled).
import { h } from "../dom.js";
import { stat, statSkeleton } from "../components/stat.js";
import { chip } from "../components/chip.js";
import { table, tableSkeleton } from "../components/table.js";
import { emptyState } from "../components/states.js";
import { provAttr } from "../components/tooltip.js";
import { headlineAvoided } from "../model.js";
import { dataView, header, honesty, mountScene, notRun, section, stage, wsEyebrow } from "./common.js";
import { buildLattice } from "../engine/lattice.js";
import { sound } from "../sound.js";
import { estimateBlock } from "../components/estimate.js";

export async function mount(ctx) {
  let scenario = ctx.query.get("scenario");
  let lattice = null;
  const weekOut = h("output", { class: "num" });
  const weekIn = h("input", { type: "range", min: "0", max: "0", step: "1", value: "0", "aria-label": "week" });
  const stageEl = stage(ctx, { label: "The plan over time: scrub the week; a crystal turns cyan when its wave passed the lab gates, and its HNDL beam goes out." });
  let waveWeeks = [], lastWeek = null;
  // the stage sits under the hero stats (hero number above the fold); moved into the grid when the data renders
  const stageWrap = h("div", { class: "span-12" }, stageEl, h("label", { class: "sg-row week-scrub" }, h("span", { class: "eyebrow", style: { margin: 0 }, text: "week" }), weekIn, weekOut));
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
      const statsEl = h("div", { class: "span-12 stats" });
      const picker = h("div", { class: "sg-row", role: "radiogroup", "aria-label": "CRQC scenario" });
      const draw = () => {
        const a = headlineAvoided(m, scenario);
        const opt = m.chart.plans[0].series[scenario];
        statsEl.replaceChildren(
          stat({ label: "avoided vs FCFS", cell: a.fcfs, unit: "exposure-years", tone: "hero accent" }),
          stat({ label: "avoided vs greedy", cell: a.greedy, unit: "exposure-years" }),
          stat({ label: "remaining at week 0", cell: opt[0].cell, unit: "exposure-years, optimised plan", tone: "exposure" }),
          stat({ label: "weeks to migrate", cell: m.makespan, unit: "makespan of the optimised plan" }));
        picker.replaceChildren(...m.scenarios.map((s) => h("button", { class: `btn${s.name === scenario ? " primary" : ""}`, type: "button", role: "radio", "aria-checked": String(s.name === scenario),
          onclick: () => { scenario = s.name; ctx.setQuery({ scenario }); if (lattice) lattice.setScenario(scenario); draw(); }, text: `${s.name} · CRQC ${s.year}` })));
        ctx.announce(`Scenario ${scenario}: ${a.fcfs.text} exposure-years avoided versus FCFS, ${a.greedy.text} versus greedy.`);
      };
      draw();
      const a = m.results.assumptions;
      return h("div", { class: "grid" },
        h("div", { class: "span-12" }, picker), statsEl, estimateBlock(ctx), stageWrap,
        h("p", { class: "span-12 fine", text: "Chart values are unweighted exposure-years; the optimiser minimises the risk- and scenario-weighted total, so in some weeks its unweighted curve can sit above a baseline." }),
        section("Waves", table({ caption: "Migration waves", rows: m.waves, columns: [
          { label: "week", render: (w) => h("span", { class: "num", tabindex: "0", "data-prov": provAttr(w.source, `wave week ${w.week}`), text: String(w.week) }), numeric: true },
          { label: "assets", render: (w) => h("span", {}, w.assets.map((id, i) => [i ? ", " : "", h("a", { href: `/w/${ctx.ws}/asset/${encodeURIComponent(id)}`, text: id })])) },
          { label: "gate status", render: (w) => chip(w.status) }] }), { aside: h("span", { class: "fine", text: m.solver }) }),
        section("Assumptions", h("dl", { class: "kv" },
          h("dt", { text: "capacity" }), h("dd", { class: "mono", text: `${a.capacity_days_per_week} engineer-days / week` }),
          h("dt", { text: "start year" }), h("dd", { class: "mono", text: String(a.start_year) }),
          h("dt", { text: "scenarios" }), h("dd", { class: "mono", text: a.scenarios.map((s) => `${s.name} (w ${s.weight})`).join(" · ") }),
          h("dt", { text: "effort / kind" }), h("dd", { class: "mono", text: Object.entries(a.effort_days_by_kind).map(([k, v]) => `${k} ${v} d`).join(" · ") })),
        { aside: chip("assumption", "assumptions, not measurements") }));
    },
  });
  ctx.root.append(h("div", { class: "grid" },
    h("div", { class: "span-12" }, header({ eyebrow: wsEyebrow(ctx), title: "Schedule", lede: "A migration plan in weekly waves that minimises harvest-now-decrypt-later exposure under several CRQC arrival scenarios, never worse than FCFS or greedy on the same data." })),
    h("div", { class: "span-12" }, body), h("div", { class: "span-12" }, honesty())));
}
