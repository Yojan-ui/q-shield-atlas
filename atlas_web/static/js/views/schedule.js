// Schedule: avoided exposure vs baselines per scenario, waves with gate status, assumptions (labelled).
import { h } from "../dom.js";
import { stat, statSkeleton } from "../components/stat.js";
import { chip } from "../components/chip.js";
import { table, tableSkeleton } from "../components/table.js";
import { emptyState } from "../components/states.js";
import { provAttr } from "../components/tooltip.js";
import { headlineAvoided } from "../model.js";
import { dataView, header, honesty, notRun, section, wsEyebrow } from "./common.js";

export async function mount(ctx) {
  let scenario = ctx.query.get("scenario");
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
          stat({ label: "avoided vs FCFS", cell: a.fcfs, unit: "exposure-years", tone: "accent" }),
          stat({ label: "avoided vs greedy", cell: a.greedy, unit: "exposure-years" }),
          stat({ label: "remaining at week 0", cell: opt[0].cell, unit: "exposure-years, optimised plan", tone: "exposure" }),
          stat({ label: "weeks to migrate", cell: m.makespan, unit: "makespan of the optimised plan" }));
        picker.replaceChildren(...m.scenarios.map((s) => h("button", { class: `btn${s.name === scenario ? " primary" : ""}`, type: "button", role: "radio", "aria-checked": String(s.name === scenario),
          onclick: () => { scenario = s.name; ctx.setQuery({ scenario }); draw(); }, text: `${s.name} · CRQC ${s.year}` })));
        ctx.announce(`Scenario ${scenario}: ${a.fcfs.text} exposure-years avoided versus FCFS, ${a.greedy.text} versus greedy.`);
      };
      draw();
      const a = m.results.assumptions;
      return h("div", { class: "grid" },
        h("div", { class: "span-12" }, picker), statsEl,
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
