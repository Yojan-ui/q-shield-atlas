// Proof Chain (code/API name: ledger): Merkle tower, inclusion proofs, tamper demo on a server-side copy.
import { sound } from "../sound.js";
import { h, icon } from "../dom.js";
import { provAttr } from "../components/tooltip.js";
import { stat, statSkeleton } from "../components/stat.js";
import { chip } from "../components/chip.js";
import { table, tableSkeleton } from "../components/table.js";
import { emptyState } from "../components/states.js";
import { hashCopy } from "../components/copy.js";
import { toast } from "../components/toast.js";
import { num } from "../model.js";
import { prefersReducedMotion } from "../motion.js";
import { buildLedger, TAMPER } from "../scenes/ledger.js";
import { dataView, honesty, mountScene, notRun, stage, viewCss } from "./common.js";
import { bullets, detailsList, main, nextStep, pageHead } from "../components/page.js";
import { term } from "../glossary.js";

const kv = (...pairs) => h("dl", { class: "kv" }, pairs.flatMap(([k, v]) => [h("dt", { text: k }), h("dd", {}, v)]));
const hc = (v, label, short) => hashCopy(v, { label, short });
const st = (label, ...kids) => h("div", { class: "stat" }, h("span", { class: "label", text: label }), h("div", {}, ...kids));
const mono = (t) => h("span", { class: "mono", text: t ?? "–" });

export async function mount(ctx) {
  await viewCss("plan");
  const body = dataView(ctx, {
    keys: ["ledger", "results"],
    skeleton: () => h("div", { class: "grid" }, h("div", { class: "span-12" }, statSkeleton()), h("div", { class: "span-12" }, tableSkeleton(4))),
    render: ({ ledger: L, results: RS }) => {
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

      // the hash chain as linked blocks: green when the live check verified, red from the failing index in a tampered copy
      const blocks = L.entries.map((e) => h("li", { class: `lc-b${v.ok === true ? " ok" : ""}`, tabindex: "0", role: "button", "aria-label": `entry ${e.index}: ${e.type}`,
        "data-prov": provAttr({ ...src, ledger_index: String(e.index), ts: e.ts, note: `prev ${(e.prev_hash || "").slice(0, 16)}… · payload ${(e.payload_hash || "").slice(0, 16)}…` }, `#${e.index} ${e.type}`),
        onclick: () => select(e.index), onkeydown: (ev) => { if (ev.key === "Enter") select(e.index); } },
        h("span", { class: "num", text: `#${e.index}` }), h("span", { class: "lc-t", text: e.type }), h("span", { class: "mono lc-h", text: (e.payload_hash || "").slice(0, 8) })));
      const chainNote = h("p", { class: "mv-note", "aria-live": "polite", text: v.ok === true ? `Real ledger: all ${L.entry_count} blocks verified (signature and link to the previous block).` : v.ok === false ? `Real ledger fails verification at #${v.first_failure && v.first_failure.index}.` : `Not verified: ${v.status_text || "no check"}.` });
      const paint = (bad) => blocks.forEach((b, i) => { b.classList.toggle("ok", bad === null && v.ok === true); b.classList.toggle("bad", bad !== null && i >= bad); });
      const tamper = h("button", { class: "btn primary", type: "button", "aria-describedby": "lg-hold" }, icon("warn"), "Tamper test (temporary copy)");
      const run = async () => {
        tamper.disabled = true;
        clearTimeout(timer);
        try {
          const t = await ctx.api.post(`/api/workspaces/${ws}/tamper-demo`, { index: Math.min(2, L.entry_count - 1) });
          const reduced = prefersReducedMotion();
          layer?.tamper(t.edited_index, reduced);
          setTimeout(() => { ctx.world.shake(); sound.crack(); }, (reduced ? 0 : TAMPER.flyS) * 1000);  // the shard strikes the leaf
          out.className = "lg-out cracked";
          if (t.index !== null && t.index !== undefined) { paint(t.index); chainNote.textContent = `Temporary copy: entry #${t.edited_index} edited, so the chain breaks from #${t.index} on. The real ledger is not touched.`; }
          out.replaceChildren(chip("tampered", `copy fails verification at #${t.index ?? "?"}`),
            kv(["edited", mono(`entry #${t.edited_index}, field "${t.edited_field}" (temporary copy)`)], ["reason", mono(t.reason)]));
          ctx.announce(`Tampered copy fails at index ${t.index}: ${t.reason}. Real ledger untouched.`);
          const same = t.real_ledger_unchanged === true && t.real_ledger_sha256_before === t.real_ledger_sha256_after;
          timer = setTimeout(() => {
            out.className = "lg-out healed";
            paint(null); chainNote.textContent = same ? `Real ledger: unchanged (SHA-256 identical before and after); all ${L.entry_count} blocks verified.` : "Real ledger hash differs; see values.";
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
      // one click: the server edits a temporary copy and verifies it with the ledger CLI; the real ledger is only read
      tamper.addEventListener("click", () => { if (!tamper.disabled) run(); }, { signal: ctx.signal });
      ctx.signal.addEventListener("abort", () => clearTimeout(timer), { once: true });

      mountScene(ctx, "ledger", L, buildLedger(L, { stageEl, onPick: select })).then((l) => { layer = l; });
      ctx.announce(`${L.entry_count} signed entries, ${v.ok ? "verified" : "not verified"}.`);
      return h("div", {},
        h("div", { class: "pg-stats" },
          h("div", { class: "pg-stat" }, stat({ label: "signed records", cell: num(L.entry_count, src), unit: "ML-DSA-65, hash-chained" }),
            h("p", { class: "pg-mean", text: "Every scan, plan, gate result and review decision, in order." })),
          h("div", { class: "pg-stat" }, st("chain check",
            v.ok === true ? chip("verified", `verified, ${v.entries_checked ?? L.entry_count} records`) : v.ok === false ? chip("FAIL", `fails at #${v.first_failure && v.first_failure.index}`) : chip("NOT_RUN", v.status_text || "not verified")),
            h("p", { class: "pg-mean", text: "Every signature and fingerprint was re-checked when this page loaded." })),
          h("div", { class: "pg-stat" }, st("signing key", hc(L.pubkey_fp, "public key fingerprint")),
            h("p", { class: "pg-mean", text: "The public key anyone can use to check the signatures." }))),
        proofSections(L, (RS && RS.results) || null, ctx),
        h("section", { class: "lc" }, h("h2", { class: "mv-h2", text: "Hash chain: every block links to the one before" }), chainNote,
          h("div", { class: "sg-row" }, tamper, h("p", { id: "lg-hold", class: "mv-note", text: "Edits one record in a temporary copy and runs the read-only verifier on it. The real ledger is never touched; nothing is recorded." })), out,
          h("ol", { class: "lc-list" }, blocks),
          h("p", { class: "mv-how", text: "How to read this: each block is one signed record (scan, plan, gate, review…). Green = its ML-DSA-65 signature and its link to the previous block were re-checked when this page loaded. Edit any block and every block after it turns red." })),
        main(h("div", { class: "grid" },
          h("div", { class: "span-8 lg-stage" }, stageEl, h("div", { class: "stage-legend" }, h("span", { text: `${L.entry_count} records as leaves · root on top` }))),
          h("aside", { class: "span-4 lg-side" },
            detail)), { title: "Merkle tree: one root summarises every record" }),
        detailsList([
          { title: "How it works", summary: "Each record's hash includes the previous one; a Merkle root summarises them all.", body: bullets([
            ["Every record is signed with ", term("mldsa", "ML-DSA-65"), ", a post-quantum signature."],
            "Records are hash-chained and summarised by an RFC 6962 Merkle root.",
            "Select a leaf or a row to see its inclusion proof."]) },
          { title: "Why this method", summary: "Evidence that cannot be quietly edited, and stays safe after Q-Day.", body: bullets([
            "Changing one byte breaks verification at exactly that record.", "A post-quantum signature means the proof itself is not quantum-breakable."]) },
          { title: "Evidence & sources", summary: `Merkle root ${L.root.slice(0, 16)}… · ${L.backend}`, body: h("div", {}, st("Merkle root (RFC 6962)", hc(L.root, "Merkle root", 16)),
            table({ caption: "Proof Chain entries", rows: L.entries, signal: ctx.signal, onRow: (e) => select(e.index), columns: [
              { label: "#", key: "index", numeric: true }, { label: "type", key: "type", mono: true }, { label: "payload", key: "payload_ref", mono: true, optional: true },
              { label: "payload SHA-256", render: (e) => hc(e.payload_hash, "payload hash", 8) }, { label: "time", key: "ts", mono: true, optional: true }] })) },
          { title: "Limits", summary: "A local, single-key test ledger: no external timestamping or second witness.", body: bullets([
            "The signing key lives on this machine (keys/, never committed).", "The tamper demo edits a temporary copy only; its result is not recorded."]) }]),
        nextStep(ctx, "ledger"));
    },
  });
  ctx.root.append(h("div", { class: "grid" }, h("div", { class: "span-12" },
    pageHead(ctx, { route: "ledger", title: "Ledger (Proof Chain)", headline: "Can every result be trusted later? Each one is signed into a chain where any edit is detected." }), body, honesty())));
}

// steps 2 and 6 of the pipeline, each with its own evidence; the sidebar links open them (?section=2 / ?section=6)
function proofSections(L, r, ctx) {
  const e0 = (L.entries || []).find((e) => e.type === "detect.run");
  const v = L.live_verification || {};
  const hs = ((r && r.handshake_evidence) || {}).sessions || [];
  const pq = hs.filter((s) => /MLKEM/i.test(s.negotiated_group || ""));
  const sec = (n, title, ok, body) => h("section", { class: "lc-proof", id: `section-${n}` }, h("h2", { class: "mv-h2" }, h("span", { class: "num", text: `${n} · ` }), title),
    h("p", { class: "lc-proof-k" }, chip(ok ? "PASS" : "NOT_RUN", ok ? "done" : "not yet run")), body);
  const s2 = sec("2", "Proof: findings signed", !!e0, h("p", { class: "mv-note", text: e0
    ? `The RSA / ECC / DH findings (detect.run) were signed with ML-DSA-65 as entry #${e0.index} at ${e0.ts}, before planning; the existing chain was verified first.`
    : "not yet run: no detect.run entry in this ledger" }));
  const s6 = sec("6", "Proof: post-quantum verified", v.ok === true, h("p", { class: "mv-note", text: v.ok === true
    ? (pq.length ? `Every entry's ML-DSA-65 signature verified across the chain (${v.entries_checked ?? L.entry_count} entries); ML-KEM evidence signed: ${pq.map((s) => `${s.service_id} negotiated ${s.negotiated_group}`).join(", ")}.`
      : `Signatures verified (${v.entries_checked ?? L.entry_count} entries); no post-quantum handshake recorded.`)
    : v.ok === false ? `Verification fails at #${(v.first_failure || {}).index}.` : `not verified: ${v.status_text || "no check"}` }));
  const want = ctx.query.get("section");
  if (want) requestAnimationFrame(() => { const el = document.getElementById(`section-${want}`); if (el) el.scrollIntoView({ block: "start" }); });
  return h("div", { class: "lc-proofs" }, s2, s6);
}
