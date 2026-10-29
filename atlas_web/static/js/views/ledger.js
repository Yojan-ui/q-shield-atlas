// Ledger: Merkle tower, inclusion proofs, tamper demo on a server-side copy.
import { sound } from "../sound.js";
import { h, icon } from "../dom.js";
import { stat, statSkeleton } from "../components/stat.js";
import { chip } from "../components/chip.js";
import { table, tableSkeleton } from "../components/table.js";
import { emptyState } from "../components/states.js";
import { hashCopy } from "../components/copy.js";
import { toast } from "../components/toast.js";
import { num } from "../model.js";
import { prefersReducedMotion } from "../motion.js";
import { buildLedger, TAMPER } from "../scenes/ledger.js";
import { dataView, header, honesty, mountScene, notRun, section, stage, wsEyebrow } from "./common.js";

const kv = (...pairs) => h("dl", { class: "kv" }, pairs.flatMap(([k, v]) => [h("dt", { text: k }), h("dd", {}, v)]));
const hc = (v, label, short) => hashCopy(v, { label, short });
const st = (label, ...kids) => h("div", { class: "stat" }, h("span", { class: "label", text: label }), h("div", {}, ...kids));
const mono = (t) => h("span", { class: "mono", text: t ?? "–" });

export async function mount(ctx) {
  const body = dataView(ctx, {
    keys: ["ledger"],
    skeleton: () => h("div", { class: "grid" }, h("div", { class: "span-12" }, statSkeleton()), h("div", { class: "span-12" }, tableSkeleton(4))),
    render: ({ ledger: L }) => {
      if (!L.available) return emptyState(notRun(ctx, "Ledger"));
      const v = L.live_verification || {}, ws = ctx.ws;
      const src = { run_id: "n/a", solver: `${L.alg} via ${L.backend}`, job_id: "none (local ledger)", ledger_index: `0–${L.entry_count - 1}`, ts: v.checked_at || "n/a", note: `pubkey ${L.pubkey_fp.slice(0, 16)}…` };
      let layer = null, gen = 0, timer = 0;
      const detail = h("div", { class: "lg-detail", "aria-live": "polite" }, h("p", { class: "fine", text: "Select a leaf or a table row to see its entry and inclusion proof." }));
      const out = h("div", { class: "lg-out", "aria-live": "polite" });
      const stageEl = stage(ctx, { label: `Merkle tower of ${L.entry_count} ledger entries`, fallback: h("span") });

      const select = async (i) => {
        const e = L.entries[i];
        if (!e) return;
        const my = ++gen;
        layer?.select(i);
        const proofBox = h("div", {}, h("span", { class: "skel line" }));
        detail.replaceChildren(h("p", { class: "eyebrow", text: `entry #${e.index}` }),
          kv(["index", mono(String(e.index))], ["type", mono(e.type)], ["payload", mono(e.payload_ref)],
            ["payload hash", hc(e.payload_hash, "payload hash")], ["prev hash", hc(e.prev_hash, "previous hash")], ["time", mono(e.ts)]),
          h("p", { class: "eyebrow lg-gap", text: "inclusion proof (RFC 6962)" }), proofBox);
        try {
          const p = await ctx.api.get(`/api/workspaces/${ws}/ledger/proof/${e.index}`, { signal: ctx.signal });
          if (my !== gen) return;
          proofBox.replaceChildren(
            p.verified ? chip("verified", "proof verifies against root") : chip("FAIL", "proof does not verify"),
            kv(["tree size", mono(String(p.tree_size))], ["leaf hash", hc(p.leaf_hash, "leaf hash")], ["root", hc(p.root, "root")]),
            h("ol", { class: "lg-proof" }, (p.proof || []).map((s, k) => h("li", {}, h("span", { class: "fine", text: `sibling ${k + 1}` }), hc(s, `sibling ${k + 1}`)))),
            h("p", { class: "fine", text: `leaf to root; from python -m ledger proof ${e.index}` }));
        } catch (err) {
          if (my !== gen || err.code === "aborted") return;
          proofBox.replaceChildren(chip("NOT_RUN", `proof unavailable: ${err.message}`));
        }
      };

      const tamper = h("button", { class: "btn primary hold", type: "button", "aria-describedby": "lg-hold" }, icon("warn"), "Hold to tamper a copy");
      const run = async () => {
        tamper.disabled = true;
        clearTimeout(timer);
        try {
          const t = await ctx.api.post(`/api/workspaces/${ws}/tamper-demo`, { index: Math.min(2, L.entry_count - 1) });
          const reduced = prefersReducedMotion();
          layer?.tamper(t.edited_index, reduced);
          setTimeout(() => { ctx.world.shake(); sound.crack(); }, (reduced ? 0 : TAMPER.flyS) * 1000);  // the shard strikes the leaf
          out.className = "lg-out cracked";
          out.replaceChildren(chip("tampered", `copy fails verification at #${t.index ?? "?"}`),
            kv(["edited", mono(`entry #${t.edited_index}, field "${t.edited_field}" (temporary copy)`)], ["reason", mono(t.reason)]));
          ctx.announce(`Tampered copy fails at index ${t.index}: ${t.reason}. Real ledger untouched.`);
          const same = t.real_ledger_unchanged === true && t.real_ledger_sha256_before === t.real_ledger_sha256_after;
          timer = setTimeout(() => {
            out.className = "lg-out healed";
            out.replaceChildren(same ? chip("PASS", "Real ledger untouched (hash unchanged)") : chip("FAIL", "real ledger hash differs; see values"),
              kv(["before", hc(t.real_ledger_sha256_before, "real ledger SHA-256 before")], ["after", hc(t.real_ledger_sha256_after, "real ledger SHA-256 after")],
                ["unchanged", mono(String(t.real_ledger_unchanged))]),
              h("p", { class: "fine", text: `${t.note}. Not recorded.` }));
            if (same) sound.chord();
            }, ((reduced ? 0 : TAMPER.flyS + TAMPER.crackS) + TAMPER.holdS) * 1000);
        } catch (err) {
          if (err.status === 429) toast("one tamper demo per second", { tone: "info" });
          else if (err.code !== "aborted") toast(err.message, { tone: "error", detail: err.code });
        } finally { setTimeout(() => { tamper.disabled = false; }, 1000); }
      };
      // press-and-hold 800 ms (pointer, or Space / Enter held): a deliberate act, cancelled by releasing early
      let hold = 0;
      const start = (e) => { if (tamper.disabled || hold || (e.repeat)) return; tamper.classList.add("holding"); hold = setTimeout(() => { hold = 0; tamper.classList.remove("holding"); run(); }, 800); };
      const stop = () => { clearTimeout(hold); hold = 0; tamper.classList.remove("holding"); };
      tamper.addEventListener("pointerdown", start, { signal: ctx.signal });
      for (const ev of ["pointerup", "pointerleave", "pointercancel", "blur"]) tamper.addEventListener(ev, stop, { signal: ctx.signal });
      tamper.addEventListener("keydown", (e) => { if (e.key === " " || e.key === "Enter") { e.preventDefault(); start(e); } }, { signal: ctx.signal });
      tamper.addEventListener("keyup", (e) => { if (e.key === " " || e.key === "Enter") stop(); }, { signal: ctx.signal });
      ctx.signal.addEventListener("abort", () => clearTimeout(timer), { once: true });

      mountScene(ctx, "ledger", L, buildLedger(L, { stageEl, onPick: select })).then((l) => { layer = l; });
      ctx.announce(`${L.entry_count} signed entries, ${v.ok ? "verified" : "not verified"}.`);
      return h("div", { class: "grid" },
        h("div", { class: "span-12 stats" },
          stat({ label: "entries", cell: num(L.entry_count, src), unit: "ML-DSA-65 signed, hash-chained", tone: "hero" }),
          st("Merkle root (RFC 6962)", hc(L.root, "Merkle root", 16)),
          st("live verification",
            v.ok === true ? chip("verified", `verified, ${v.entries_checked ?? L.entry_count} entries`) : v.ok === false ? chip("FAIL", `fails at #${v.first_failure && v.first_failure.index}`) : chip("NOT_RUN", v.status_text || "not verified"),
            h("div", { class: "unit", text: "checked read-only on load; not recorded" })),
          st("signing key", hc(L.pubkey_fp, "public key fingerprint"), h("div", { class: "unit", text: L.backend }))),
        h("div", { class: "span-8 lg-stage" }, stageEl, h("div", { class: "stage-legend" }, h("span", { text: `${L.entry_count} entries as leaves · RFC 6962 split · root on top` }))),
        h("aside", { class: "span-4 lg-side" },
          h("p", { class: "eyebrow", text: "tamper demo" }),
          h("p", { class: "fine", text: "Edits one entry in a temporary copy and runs python -m ledger verify on it. The real ledger is never touched; its hash is compared before and after." }),
          tamper, h("p", { id: "lg-hold", class: "fine", text: "Press and hold for 0.8 s (mouse, touch, or Space / Enter)." }), out, detail),
        section("Entries", table({ caption: "Ledger entries", rows: L.entries, signal: ctx.signal, onRow: (e) => select(e.index), columns: [
          { label: "#", key: "index", numeric: true }, { label: "type", key: "type", mono: true }, { label: "payload", key: "payload_ref", mono: true, optional: true },
          { label: "payload SHA-256", render: (e) => hc(e.payload_hash, "payload hash", 8) }, { label: "time", key: "ts", mono: true, optional: true }] })));
    },
  });
  ctx.root.append(h("div", { class: "grid" },
    h("div", { class: "span-12" }, header({ eyebrow: wsEyebrow(ctx), title: "Ledger", lede: "Every run manifest signed with ML-DSA-65 into an append-only hash chain with an RFC 6962 Merkle root. Change one byte and verification fails at exactly that entry." })),
    h("div", { class: "span-12" }, body), h("div", { class: "span-12" }, honesty())));
}
