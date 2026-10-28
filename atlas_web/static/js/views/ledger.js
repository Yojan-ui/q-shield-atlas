// Ledger: ML-DSA-65 signed hash chain + Merkle root; "Tamper a copy" verifies an edited COPY on the server.
import { h, icon } from "../dom.js";
import { stat, statSkeleton } from "../components/stat.js";
import { chip } from "../components/chip.js";
import { table, tableSkeleton } from "../components/table.js";
import { emptyState } from "../components/states.js";
import { hashCopy } from "../components/copy.js";
import { toast } from "../components/toast.js";
import { num } from "../model.js";
import { dataView, header, honesty, notRun, section, wsEyebrow } from "./common.js";

export async function mount(ctx) {
  const result = h("div", { "aria-live": "polite" });
  const body = dataView(ctx, {
    keys: ["ledger"],
    skeleton: () => h("div", { class: "grid" }, h("div", { class: "span-12" }, statSkeleton()), h("div", { class: "span-12" }, tableSkeleton(4))),
    render: ({ ledger: L }) => {
      if (!L.available) return emptyState(notRun(ctx, "Ledger"));
      const v = L.live_verification || {};
      const src = { run_id: "n/a", solver: `${L.alg} via ${L.backend}`, job_id: "none (local ledger)", ledger_index: `0–${L.entry_count - 1}`, ts: v.checked_at || "n/a", note: `pubkey ${L.pubkey_fp.slice(0, 16)}…` };
      const tamper = h("button", { class: "btn primary", type: "button" }, icon("warn"), "Tamper a copy");
      tamper.addEventListener("click", async () => {
        tamper.disabled = true;
        try {
          const t = await ctx.api.post(`/api/workspaces/${ctx.ws}/tamper-demo`, { index: Math.min(2, L.entry_count - 1) });
          result.replaceChildren(h("dl", { class: "kv" },
            h("dt", { text: "edited" }), h("dd", { class: "mono", text: `entry #${t.edited_index}, field "${t.edited_field}" (in a temporary copy)` }),
            h("dt", { text: "verify" }), h("dd", {}, chip("FAIL", `fails at index ${t.index}`), " ", h("span", { class: "fine", text: t.reason })),
            h("dt", { text: "real ledger" }), h("dd", {}, chip("PASS", "unchanged"), " ", hashCopy(t.real_ledger_sha256_after, { label: "real ledger SHA-256" }))),
            h("p", { class: "fine", text: t.note }));
          ctx.announce(`Tampered copy fails verification at index ${t.index}: ${t.reason}. The real ledger is unchanged.`);
        } catch (err) { toast(err.message, { tone: "error", detail: err.code }); }
        finally { setTimeout(() => { tamper.disabled = false; }, 1000); }
      }, { signal: ctx.signal });
      ctx.announce(`${L.entry_count} signed entries, ${v.ok ? "verified" : "not verified"}.`);
      return h("div", { class: "grid" },
        h("div", { class: "span-12 stats" },
          stat({ label: "entries", cell: num(L.entry_count, src), unit: "ML-DSA-65 signed, hash-chained" }),
          h("div", { class: "stat" }, h("span", { class: "label", text: "Merkle root (RFC 6962)" }), h("div", {}, hashCopy(L.root, { label: "Merkle root", short: 16 }))),
          h("div", { class: "stat" }, h("span", { class: "label", text: "verification" }), h("div", {},
            v.ok === true ? chip("verified", "chain, signatures, payloads ✓") : v.ok === false ? chip("FAIL", `fails at ${v.first_failure && v.first_failure.index}`) : chip("NOT_RUN", v.status_text || "not verified"),
            h("div", { class: "unit", text: "checked read-only on load; not recorded" }))),
          h("div", { class: "stat" }, h("span", { class: "label", text: "signing key" }), h("div", {}, hashCopy(L.pubkey_fp, { label: "public key fingerprint" }), h("div", { class: "unit", text: L.backend })))),
        section("Tamper demo", h("div", {}, h("p", { class: "fine", style: { marginBottom: "var(--s-4)" }, text: "Edits one entry in a temporary copy on the server and verifies it with python -m ledger verify. The real ledger is never touched; its hash is checked before and after." }), tamper, h("div", { style: { marginTop: "var(--s-4)" } }, result))),
        section("Entries", table({ caption: "Ledger entries", rows: L.entries, signal: ctx.signal, columns: [
          { label: "#", key: "index", numeric: true }, { label: "type", key: "type", mono: true }, { label: "payload", key: "payload_ref", mono: true, optional: true },
          { label: "payload SHA-256", render: (e) => hashCopy(e.payload_hash, { label: "payload hash", short: 8 }) }, { label: "time", key: "ts", mono: true, optional: true }] })));
    },
  });
  ctx.root.append(h("div", { class: "grid" },
    h("div", { class: "span-12" }, header({ eyebrow: wsEyebrow(ctx), title: "Ledger", lede: "Every run manifest signed with ML-DSA-65 into an append-only hash chain with an RFC 6962 Merkle root. Change one byte and verification fails at exactly that entry." })),
    h("div", { class: "span-12" }, body), h("div", { class: "span-12" }, honesty())));
}
