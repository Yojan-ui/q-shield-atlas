// Detect: inventory (stat row, services, findings with file:line). Stage 5 adds the column city and real-data intake.
import { h } from "../dom.js";
import { stat, statSkeleton } from "../components/stat.js";
import { chip } from "../components/chip.js";
import { table, tableSkeleton } from "../components/table.js";
import { emptyState } from "../components/states.js";
import { dataView, header, honesty, notRun, section, wsEyebrow } from "./common.js";

export async function mount(ctx) {
  ctx.root.append(h("div", { class: "grid" },
    h("div", { class: "span-12" }, header({ eyebrow: wsEyebrow(ctx), title: "Detect", lede: "Where RSA, ECC and DH live in this system: a static scan with file:line evidence, owner-declared service manifests, and live TLS probes that catch drift between config and reality." })),
    h("div", { class: "span-12" }, dataView(ctx, {
      skeleton: () => h("div", { class: "grid" }, h("div", { class: "span-12" }, statSkeleton()), h("div", { class: "span-12" }, tableSkeleton(5))),
      render: ({ model: m }) => {
        const d = m && m.detect;
        if (!d || !d.available) return emptyState(notRun(ctx, "Inventory"));
        ctx.announce(`${d.assets.text} assets to migrate, ${d.vulnerable.text} vulnerable findings in ${d.files.text} scanned files, ${d.drift.text} drift cases.`);
        return h("div", { class: "grid" },
          h("div", { class: "span-12 stats" },
            stat({ label: "files scanned", cell: d.files, unit: "code, configs, certificates" }),
            stat({ label: "vulnerable findings", cell: d.vulnerable, unit: "RSA / ECC / DH / DSA", tone: "exposure" }),
            stat({ label: "assets to migrate", cell: d.assets, unit: `not vulnerable: ${d.notVulnerable.join(", ") || "none"}` }),
            stat({ label: "drift", cell: d.drift, unit: "static vs live handshake" })),
          section("Services", table({ caption: "Services to migrate", rows: m.assets, rowHref: (a) => `/w/${ctx.ws}/asset/${encodeURIComponent(a.id)}`, signal: ctx.signal, columns: [
            { label: "service", render: (a) => h("span", {}, a.name, h("span", { class: "sub mono", text: a.id })) },
            { label: "kind", key: "kind", optional: true }, { label: "data class", key: "data_class", optional: true }, { label: "algorithm", key: "algorithm", mono: true, optional: true },
            { label: "findings", key: "findings", numeric: true }, { label: "status", render: (a) => chip(a.status) }] })),
          section("Live probes", d.probes.length ? table({ caption: "Live TLS probes", rows: d.probes, columns: [
            { label: "service", key: "service" }, { label: "endpoint", key: "endpoint", mono: true }, { label: "negotiated", render: (p) => p.ok ? p.group : chip("FAIL", "no handshake") },
            { label: "certificate", key: "cert", mono: true }, { label: "drift", render: (p) => p.drift.length ? h("span", {}, p.drift.map((k) => chip("HNDL-exposed", k))) : chip("PASS", "none") }] })
            : h("p", { class: "fine", text: "No live probe in this run." })),
          section("Findings", table({ caption: "Static findings", rows: d.findings, signal: ctx.signal, columns: [
            { label: "file:line", render: (f) => `${f.file}:${f.line}`, mono: true }, { label: "family", key: "family" }, { label: "use", key: "use" },
            { label: "rule", key: "rule", mono: true, optional: true }, { label: "snippet", optional: true, render: (f) => h("span", { class: "mono fine", text: (f.snippet || "").slice(0, 80) }) }] })));
      },
    })),
    h("div", { class: "span-12" }, honesty())));
}
