// Inventory & drift: the systems Detect turned into migration work, and where a live connection disagrees with config.
import { h } from "../dom.js";
import { chip } from "../components/chip.js";
import { table, tableSkeleton } from "../components/table.js";
import { emptyState } from "../components/states.js";
import { num } from "../model.js";
import { term } from "../glossary.js";
import { bullets, detailsList, keyStats, main, nextStep, pageHead } from "../components/page.js";
import { dataView, honesty, notRun } from "./common.js";

export async function mount(ctx) {
  const body = dataView(ctx, {
    keys: ["results"],
    skeleton: () => tableSkeleton(5),
    render: ({ model: m }) => {
      const r = m && m.results;
      if (!r || !r.detect) return emptyState(notRun(ctx, "Inventory"));
      const src = { run_id: r.detect.run_id, solver: "detect/ (static scan + live probes)", job_id: "none (local scan)", ts: r.detect.ts };
      const drift = (r.detect.probes || []).flatMap((p) => (p.drift || []).map((d) => ({ ...d, service: p.service, endpoint: p.endpoint })));
      const inv = r.detect.inventory || {};
      return h("div", {},
        keyStats([
          { label: "systems to migrate", cell: num(r.assets.length, src), unit: "with RSA / ECC / DH", mean: "Each one needs a new, post-quantum way to exchange keys or sign." },
          { label: "already safe", cell: num((inv.not_vulnerable || []).length, src), unit: "no vulnerable crypto found", mean: "Services where the scan found nothing to replace." },
          { label: "drift alerts", cell: num(drift.length, src), unit: "live ≠ config", mean: drift.length ? "A live connection behaves differently from what its configuration says." : "Live connections match their configuration." },
        ]),
        main(table({ caption: "Inventory of systems to migrate", rows: r.assets, rowHref: (a) => `/w/${ctx.ws}/asset/${encodeURIComponent(a.id)}`, columns: [
          { label: "system", render: (a) => h("span", {}, a.name, h("span", { class: "sub", text: a.id })) },
          { label: "crypto found", key: "algorithm", mono: true },
          { label: "protects", render: (a) => a.data_class.replaceAll("_", " ") },
          { label: "evidence (lines)", numeric: true, render: (a) => String((a.evidence || []).length) },
          { label: "depends on", optional: true, render: (a) => a.depends_on.join(", ") || "–" }] }), { title: "Systems to migrate" }),
        drift.length ? main(table({ caption: "Drift", rows: drift, columns: [
          { label: "service", key: "service", mono: true },
          { label: "severity", render: (d) => chip(d.severity === "high" ? "FAIL" : "partially_verified", d.severity) },
          { label: "what differs", key: "detail" }] }), { title: "Drift: live connection vs configuration" }) : null,
        detailsList([
          { title: "How it works", summary: "Findings are grouped by the service that owns the file.", body: bullets([
            "Each service folder declares its owner facts in atlas-service.json: name, kind, the data it protects, dependencies.",
            "The crypto facts come only from the scan: file, line and rule for every finding.",
            ["Drift compares a live ", term("tls", "TLS handshake"), " with the configuration of the same service."]]) },
          { title: "Why this method", summary: "Owners know what data a system protects; the scanner knows the crypto.", body: bullets([
            "Splitting the facts keeps every crypto claim traceable to a line of code or a recorded handshake.",
            "Drift catches the common case where a config asks for post-quantum but the live service does not use it."]) },
          { title: "Evidence & sources", summary: `Detect run ${r.detect.run_id.slice(0, 12)}, inventory hash ${(inv.sha256 || "").slice(0, 12)}…`, body: bullets([
            `Scanned ${r.detect.files_scanned} files at ${r.detect.ts}.`, `Inventory SHA-256 ${inv.sha256 || "n/a"}.`, "Signed into the Proof Chain as detect.run."]) },
          { title: "Limits", summary: "A scan finds what is written down; it cannot see crypto inside closed binaries.", body: bullets([
            "Libraries using TLS defaults are flagged as \"needs live probe\", not counted as vulnerable.",
            "Data class and dependencies are declared by the owner, not inferred."]) }]),
        nextStep(ctx, "inventory"));
    },
  });
  ctx.root.append(h("div", { class: "grid" }, h("div", { class: "span-12" },
    pageHead(ctx, { route: "inventory", title: "Inventory & drift", headline: "Which systems must move to post-quantum encryption, and where does a live connection differ from its configuration?" }),
    body, honesty())));
}
