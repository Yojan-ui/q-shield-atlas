// QAOA: measured cross-check against the brute-force optimum; QCloud rows show their status_text.
import { h } from "../dom.js";
import { stat, statSkeleton } from "../components/stat.js";
import { chip } from "../components/chip.js";
import { table, tableSkeleton } from "../components/table.js";
import { emptyState } from "../components/states.js";
import { num, QAOA_LABEL } from "../model.js";
import { dataView, header, honesty, notRun, section, wsEyebrow } from "./common.js";

export async function mount(ctx) {
  const body = dataView(ctx, {
    keys: ["results"],
    skeleton: () => h("div", { class: "grid" }, h("div", { class: "span-12" }, statSkeleton()), h("div", { class: "span-12" }, tableSkeleton(6))),
    render: ({ model: m }) => {
      const q = m && m.qaoa;
      if (!q || !q.available) return emptyState(notRun(ctx, "QAOA cross-check"));
      const prob = m.results.qaoa.problem;
      const src = q.exact.objective.source;
      ctx.announce(`QAOA ${QAOA_LABEL}. Exact optimum ${q.exact.objective.text}, assets ${q.exact.assets.join(", ")}.`);
      return h("div", { class: "grid" },
        h("div", { class: "span-12 stats" },
          stat({ label: "exact optimum", cell: q.exact.objective, unit: `brute force · ${q.exact.assets.join(", ")}` }),
          stat({ label: "QUBO variables", cell: num(prob.n_variables, src), unit: `${prob.assets.length} assets + ${prob.slack_bits} slack bits` }),
          stat({ label: "wave week", cell: num(prob.week, src), unit: "one week of the latest schedule" }),
          h("div", { class: "stat" }, h("span", { class: "label", text: "claim" }), h("div", {}, chip("recorded", QAOA_LABEL)))),
        section("Runs", table({ caption: "QAOA versus random baseline", rows: q.rows, columns: [
          { label: "p", render: (r) => (r.p === null ? "–" : String(r.p)), numeric: true },
          { label: "source", render: (r) => h("span", {}, r.source_kind, h("span", { class: "sub", text: r.backend })) },
          ...q.columns.map(([k, label]) => ({ label, numeric: true, render: (r) => (r.cells ? r.cells[k] : null) })),
          { label: "status", render: (r) => r.cells ? chip("ok", "measured") : h("span", { class: "fine", text: r.status_cell.text }) }] })),
        h("p", { class: "span-12 fine", text: q.full_label }));
    },
  });
  ctx.root.append(h("div", { class: "grid" },
    h("div", { class: "span-12" }, header({ eyebrow: wsEyebrow(ctx), title: "QAOA cross-check", lede: `One week's wave selection as a QUBO, sampled by QAOA (p = 1…3) on a simulator and compared with the exact brute-force optimum and a random baseline: ${QAOA_LABEL}.` })),
    h("div", { class: "span-12" }, body), h("div", { class: "span-12" }, honesty())));
}
