// /styleguide?dev: every component in every state. Not linked anywhere; 404 without ?dev.
import { h, icon } from "../dom.js";
import { chip, chipKinds } from "../components/chip.js";
import { stat, statSkeleton } from "../components/stat.js";
import { table, tableSkeleton } from "../components/table.js";
import { logConsole } from "../components/log.js";
import { field, checkbox } from "../components/form.js";
import { confirmDialog } from "../components/dialog.js";
import { toast } from "../components/toast.js";
import { emptyState, errorState, lines } from "../components/states.js";
import { hashCopy } from "../components/copy.js";
import { header, section } from "./common.js";

// Sample cells for the styleguide only: clearly labelled as samples, never shown on data routes.
const SRC = { run_id: "sample-run", solver: "styleguide sample (not data)", job_id: "none", ledger_index: "n/a", ts: "n/a" };
const cell = (value, digits = 0) => ({ kind: "number", value, text: value.toFixed(digits), digits, source: SRC });

export async function mount(ctx) {
  const rolling = stat({ label: "rolling value (sample)", cell: cell(12.5, 3), unit: "click to change" });
  let v = 12.5;
  const roll = h("button", { class: "btn", type: "button", text: "Change sample value", onclick: () => { v = v > 20 ? 3.2 : v * 1.9; rolling.update(cell(v, 3)); } });
  const rows = Array.from({ length: 1000 }, (_, i) => ({ i, name: `row-${i}`, value: cell(i * 0.731, 3) }));
  const log = logConsole({ label: "sample log", height: 200, signal: ctx.signal });
  for (let i = 0; i < 2000; i++) log.push(i % 97 === 0 ? `step failed (sample line ${i})` : `sample output line ${i}`, i % 2 ? "detect" : "schedule", i % 97 === 0 ? "err" : "");
  const invalid = field({ label: "Endpoint", name: "sg-ep", value: "web-gw=host", hint: "SERVICE=HOST:PORT" });
  invalid.setError("use SERVICE=HOST:PORT, e.g. web-gw=example.com:443");
  ctx.root.append(h("div", { class: "grid" },
    h("div", { class: "span-12" }, header({ eyebrow: "Design system · dev only", title: "Styleguide", lede: "Every component in every state. Values on this page are samples, labelled as such; data routes only render values from the API." })),
    section("Type", h("div", {}, h("p", { class: "display", text: "64 Display" }), h("p", { class: "h1", text: "40 Heading" }), h("p", { class: "h2", text: "20 Section" }),
      h("p", { text: "14 Body: HNDL-exposed: recorded traffic relies on classical key exchange." }), h("p", { class: "fine", text: "12 Fine print" }), h("p", { class: "eyebrow", text: "11 eyebrow label" }),
      h("p", { class: "mono", text: "0123456789 X25519MLKEM768 ML-DSA-65" }))),
    section("Buttons", h("div", { class: "sg-row" }, h("button", { class: "btn primary", type: "button", text: "Primary" }), h("button", { class: "btn", type: "button", text: "Secondary" }),
      h("button", { class: "btn quiet", type: "button", text: "Quiet" }), h("button", { class: "btn danger", type: "button", text: "Danger" }),
      h("button", { class: "btn", type: "button", disabled: true, text: "Disabled" }), h("button", { class: "btn", type: "button" }, icon("play"), "With icon"))),
    section("Status chips", h("div", { class: "sg-row" }, chipKinds.map((k) => chip(k)))),
    section("Stat blocks", h("div", {}, h("div", { class: "stats" }, rolling, stat({ label: "exposure tone (sample)", cell: cell(90.077, 3), unit: "exposure-years", tone: "exposure" }),
      stat({ label: "missing", cell: null, unit: "never 0" }), stat({ label: "status text", cell: { kind: "status", text: "skipped: no QCloud subscription" } })),
      h("div", { style: { marginTop: "var(--s-3)" } }, roll), h("div", { style: { marginTop: "var(--s-4)" } }, statSkeleton()))),
    section("Data table · 1000 rows, virtualised", table({ caption: "virtualised sample", rows, signal: ctx.signal, columns: [
      { label: "#", key: "i", numeric: true }, { label: "name", key: "name", mono: true }, { label: "value", key: "value", numeric: true }] })),
    section("Table: empty and loading", h("div", {}, table({ caption: "empty", rows: [], columns: [{ label: "a", key: "a" }], empty: "not yet run" }), tableSkeleton(3, 3))),
    section("Log console · 2000 lines", log),
    section("Form fields", h("div", { class: "form-row" }, field({ label: "Username", name: "sg-user", hint: "lower case" }), invalid,
      field({ label: "Data class", name: "sg-dc", options: ["payments", "customer_pii", "auth_session"] }), checkbox({ label: "I own or am authorised to test these endpoints", name: "sg-auth" }))),
    section("Dialog and toast", h("div", { class: "sg-row" },
      h("button", { class: "btn", type: "button", text: "Open confirm dialog", onclick: () => confirmDialog({ title: "Submit QpiAI jobs?", body: "Credits may be consumed. Sample dialog.", confirm: "Submit", danger: true }) }),
      h("button", { class: "btn", type: "button", text: "Info toast", onclick: () => toast("Sample info toast") }),
      h("button", { class: "btn", type: "button", text: "Success toast", onclick: () => toast("Pipeline finished: PASS", { tone: "success" }) }),
      h("button", { class: "btn", type: "button", text: "Error toast", onclick: () => toast("Sample error", { tone: "error", detail: "network" }) }))),
    section("Hash", hashCopy("e8b64d3a7cdb5f6d7c5b2c9accf50d9d26c9aa024f83f1916d482cf2e1d7c616", { label: "sample hash" })),
    section("States", h("div", { class: "grid" }, h("div", { class: "span-4" }, emptyState({ title: "Inventory: not yet run", body: "Sample empty state." })),
      h("div", { class: "span-4" }, errorState({ error: { message: "cannot reach the Atlas server (sample)" }, onRetry: () => toast("retry (sample)") })),
      h("div", { class: "span-4" }, h("div", { class: "state" }, lines(4)))))));
}
