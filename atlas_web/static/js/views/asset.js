// Asset drill-down: plan week, exposure per scenario, findings, dependencies, lab stand-in gates, ledger entries.
import { h } from "../dom.js";
import { stat, statSkeleton } from "../components/stat.js";
import { chip } from "../components/chip.js";
import { table } from "../components/table.js";
import { emptyState } from "../components/states.js";
import { num } from "../model.js";
import { dataView, header, honesty, notRun, section, wsEyebrow } from "./common.js";

export async function mount(ctx) {
  const id = ctx.params.assetId;
  const headEl = h("div", { class: "span-12" }, header({ eyebrow: wsEyebrow(ctx), title: id, lede: "Asset drill-down." }));
  const body = dataView(ctx, {
    keys: ["results", "scene"],
    skeleton: () => statSkeleton(),
    render: ({ model: m }) => {
      if (!m || !m.results) return emptyState(notRun(ctx, "Asset"));
      const a = m.assets.find((x) => x.id === id);
      if (!a) return emptyState({ title: `No asset ${id}`, body: "This workspace's inventory has no service with that id.", action: h("a", { class: "btn", href: `/w/${ctx.ws}/detect`, text: "Back to the inventory" }) });
      headEl.querySelector("h1").textContent = a.name;
      headEl.querySelector(".lede").textContent = `${a.id} · ${a.kind} · ${a.data_class} · ${a.algorithm}`;
      document.title = `${a.name} · ${ctx.ws} · Q-Shield Atlas`;
      const scen = m.scenarios.map((s) => s.name);
      const sel = scen.includes(ctx.query.get("scenario")) ? ctx.query.get("scenario") : scen[0];
      const ledgerRows = ((m.results.ledger || {}).entries || []).filter((e) => a.standin && a.standin.run_id && e.payload_ref.includes(a.standin.run_id));
      ctx.announce(`${a.name}: ${a.status.replaceAll("_", " ")}, planned week ${a.week.text}.`);
      return h("div", { class: "grid" },
        h("div", { class: "span-12" }, chip(a.status)),
        h("div", { class: "span-12 stats" },
          stat({ label: "planned week", cell: a.week, unit: "optimised plan" }),
          stat({ label: `exposure · ${sel}`, cell: a.exposure ? a.exposure[sel] : num(null), unit: "exposure-years at the planned week", tone: "exposure" }),
          stat({ label: "shelf life", cell: a.shelf, unit: "years · assumption" }),
          stat({ label: "effort", cell: a.effort, unit: "engineer-days · assumption" })),
        section("Evidence", table({ caption: "file:line evidence", rows: a.evidence, empty: "no static findings", columns: [
          { label: "file:line", render: (f) => `${f.file}:${f.line}`, mono: true }, { label: "family", key: "family" }, { label: "use", key: "use" }, { label: "rule", key: "rule", mono: true }] })),
        section("Dependencies", a.depends_on.length ? h("p", {}, a.depends_on.map((d, i) => [i ? " · " : "", h("a", { href: `/w/${ctx.ws}/asset/${encodeURIComponent(d)}`, class: "mono", text: d })])) : h("p", { class: "fine", text: "none" })),
        section("Lab stand-in", a.standin ? h("dl", { class: "kv" },
          h("dt", { text: "stand-in" }), h("dd", { class: "mono", text: a.standin.lab_service }),
          h("dt", { text: "outcome" }), h("dd", {}, chip(a.standin.status)),
          h("dt", { text: "pq_handshake" }), h("dd", {}, chip(a.standin.pq_handshake || "NOT_RUN")),
          h("dt", { text: "pq_auth" }), h("dd", {}, chip(a.standin.pq_auth || "NOT_RUN")))
          : h("p", { class: "fine", text: "No TLS stand-in for this kind: not_verified_in_lab, never shown as fixed." })),
        section("Ledger entries", table({ caption: "Signed wave evidence", rows: ledgerRows, empty: "no ledger entry for this asset's wave run", columns: [
          { label: "#", key: "index", numeric: true }, { label: "type", key: "type", mono: true }, { label: "payload", key: "payload_ref", mono: true }] })));
    },
  });
  ctx.root.append(h("div", { class: "grid" }, headEl, h("div", { class: "span-12" }, body), h("div", { class: "span-12" }, honesty())));
}
