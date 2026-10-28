// Handshakes: TLS 1.3 evidence per lab service, downgrade refusal, compatibility matrix, tested rollback.
import { h } from "../dom.js";
import { chip } from "../components/chip.js";
import { table, tableSkeleton } from "../components/table.js";
import { emptyState } from "../components/states.js";
import { hashCopy } from "../components/copy.js";
import { HNDL } from "../model.js";
import { provAttr } from "../components/tooltip.js";
import { dataView, header, honesty, notRun, section, wsEyebrow } from "./common.js";

export async function mount(ctx) {
  const body = dataView(ctx, {
    keys: ["results"],
    skeleton: () => tableSkeleton(5, 3),
    render: ({ model: m }) => {
      const hs = m && m.handshake;
      if (!hs || !hs.available) return emptyState(notRun(ctx, "Handshake evidence"));
      const g = m.results.gates || {};
      const fr = g.forced_rollback;
      ctx.announce(hs.rows.map((r) => `${r.service}: ${r.kex_group}, pq_handshake ${r.kex_gate}`).join(". "));
      return h("div", { class: "grid" },
        section("Lab services", table({ caption: "TLS 1.3 handshake evidence", rows: hs.rows, columns: [
          { label: "service", render: (r) => h("span", { tabindex: "0", "data-prov": provAttr(r.source, r.service), class: "num", text: r.service }) },
          { label: "key exchange", render: (r) => h("span", {}, h("span", { class: "mono", text: r.kex_group }), r.kex_class === "classical" ? h("span", { class: "sub", text: HNDL }) : null) },
          { label: "pq_handshake", render: (r) => chip(r.kex_gate) }, { label: "authentication", key: "auth_alg", mono: true },
          { label: "pq_auth", render: (r) => chip(r.auth_gate) }] })),
        section("Downgrade", table({ caption: "Classical-only client", rows: g.downgrade || [], empty: "not yet run", columns: [
          { label: "service", key: "service_id" }, { label: "result", render: (d) => chip(d.result) }, { label: "detail", render: (d) => h("span", { class: "fine", text: d.detail || d.reason || "" }) }] })),
        section("Compatibility", table({ caption: "Modes and clients", rows: g.compat_matrix || [], empty: "not yet run", columns: [
          { label: "mode", key: "mode", mono: true }, { label: "gate", render: (c) => chip(c.result) },
          { label: "cells", render: (c) => h("span", { class: "fine mono", text: Object.entries(c.counts || {}).map(([k, v]) => `${k} ${v}`).join(" · ") }) }] })),
        section("Tested rollback", fr ? h("dl", { class: "kv" },
          h("dt", { text: "service" }), h("dd", { class: "mono", text: `${fr.service_id}: ${fr.from_mode} → ${fr.to_mode}` }),
          h("dt", { text: "outcome" }), h("dd", {}, chip(fr.status || (fr.restored_config_sha256 === fr.snapshot_sha256 ? "rolled_back" : "rollback_failed"))),
          h("dt", { text: "snapshot" }), h("dd", {}, hashCopy(fr.snapshot_sha256, { label: "snapshot hash" })),
          h("dt", { text: "restored" }), h("dd", {}, hashCopy(fr.restored_config_sha256, { label: "restored hash" })))
          : h("p", { class: "fine", text: "not yet run" })),
        h("p", { class: "span-12 fine", text: hs.note }));
    },
  });
  ctx.root.append(h("div", { class: "grid" },
    h("div", { class: "span-12" }, header({ eyebrow: wsEyebrow(ctx), title: "Handshakes", lede: "Real TLS 1.3 handshakes against local openssl s_server lab services: which group each one negotiates, whether a classical-only client is refused, and a rollback that restores the exact config hash." })),
    h("div", { class: "span-12" }, body), h("div", { class: "span-12" }, honesty())));
}
