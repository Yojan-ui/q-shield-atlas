// Handshakes route; every value comes from results.json.
import { h } from "../dom.js";
import { chip } from "../components/chip.js";
import { table, tableSkeleton } from "../components/table.js";
import { emptyState } from "../components/states.js";
import { hashCopy } from "../components/copy.js";
import { provAttr } from "../components/tooltip.js";
import { HNDL, NOT_YET_RUN as NR, num, source } from "../model.js";
import { dataView, honesty, mountScene, notRun, section, stage } from "./common.js";
import { buildHandshakes, rowsOf } from "../scenes/handshakes.js";
import { bullets, detailsList, keyStats, main, nextStep, pageHead, dd } from "../components/page.js";
import { term } from "../glossary.js";

const res = (x) => (x && x.result) || NR;
const hash = (v, label) => (v ? hashCopy(v, { label }) : h("span", { class: "fine", text: NR }));
const sub = (text, cls = "") => h("span", { class: `sub ${cls}`, text });
const two = (a, b) => h("span", {}, a, b);
const mono = (text) => h("span", { class: "mono", text });
const refused = (d) => (d ? (d.result === "PASS" ? "refused" : "accepted") : null);

const label = ({ s, classical, auth, down, live }) => h("div", { class: "hs-label" }, h("b", { class: "mono", text: s.service_id }), mono(` · ${s.negotiated_group}`),
  sub(classical ? HNDL : s.negotiated_group === "X25519MLKEM768" ? "hybrid: X25519 + ML-KEM-768" : s.kex_class, classical ? "exp" : ""),
  sub(live ? `live endpoint ${s.endpoint} · cert ${s.auth_alg || NR}` : [auth && auth.result === "PASS" ? `${auth.auth_alg} server auth` : null, down ? `classical-only client ${refused(down)}` : null].filter(Boolean).join(" · ")));

export async function mount(ctx) {
  const body = dataView(ctx, {
    keys: ["results"],
    skeleton: () => h("div", {}, h("div", { class: "stage" }), tableSkeleton(6, 3)),
    render: ({ model: m }) => {
      const r = m && m.results;
      if (!r || !r.handshake_evidence) return emptyState(notRun(ctx, "Handshake evidence"));
      const he = r.handshake_evidence, g = r.gates || {}, rows = rowsOf(r), fr = g.forced_rollback;
      const src = (run_id, solver, ts, note) => source(r, { run_id, solver, job_id_reason: "local lab run, no backend job", ts, note });
      const labels = h("div", { class: "hs-labels", "aria-hidden": "true" }, rows.map(label));
      const said = rows.map((x) => `${x.s.service_id}: ${x.s.negotiated_group}${x.classical ? `, ${HNDL}` : ""}`).join(". ");
      const el = stage(ctx, { label: `TLS 1.3 sessions. ${said}`, fallback: h("span"), tall: rows.length > 3 });
      el.append(labels, h("div", { class: "stage-legend" }, [["exp", "single strand: classical key exchange"], ["acc", "braid: X25519 + ML-KEM-768 hybrid"],
        ["", "ring: ML-DSA server auth"], ["acc", "wall: classical-only client refused"]].map(([k, t]) => h("span", { class: `hs-k ${k}`, text: t }))));
      mountScene(ctx, "handshakes", r, (env) => buildHandshakes(env, rows, labels)).catch(() => {});
      ctx.announce(said);
      const clients = [...new Set((g.compat_matrix || []).flatMap((c) => (c.cells || []).map((x) => x.client)))];
      const waves = (r.waves || []).flatMap((w) => ((w.evidence && w.evidence.lab_services) || []).map((e) => ({ w, e, p: (e.gates || {}).pq_handshake })));
      const kv = (...pairs) => h("dl", { class: "kv hs-kv" }, pairs.map(([k, v]) => [h("dt", { text: k }), h("dd", {}, v)]));
      const liveT = section("Live endpoints", table({ caption: "Live TLS probes", rows: rows.filter((x) => x.live), empty: "no live probe in this run",
          expand: ({ s, probe, classical }) => ({ why: classical ? HNDL : "Hybrid: X25519 + ML-KEM-768.", hash: s.transcript_sha256, run_id: r.detect.run_id, ts: probe.live.ts,
            technical: h("span", { class: "mono", text: `${s.endpoint} · ${s.negotiated_group} · cert ${s.auth_alg || NR} · ${probe.live.openssl}` }) }), columns: [
          { label: "service", render: ({ s }) => s.service_id },
          { label: "key exchange", render: ({ s, classical }) => chip(classical ? "HNDL-exposed" : "hybrid", s.negotiated_group) },
          { label: "drift", render: ({ probe }) => (probe.drift.length ? chip("NOT_RUN", `${probe.drift.length} drift`) : chip("PASS", "none")) }] }));
      const labT = section("Lab services", table({ caption: "TLS 1.3 handshake sessions", rows: rows.filter((x) => !x.live), empty: NR,
          expand: ({ s, classical, down }) => ({ why: classical ? HNDL : `Negotiated ${s.negotiated_group}.${down ? ` Classical-only client: ${down.reason}` : ""}`, hash: s.transcript_sha256, run_id: he.run_id, ts: he.ts,
            technical: h("span", { class: "mono", text: `${s.negotiated_group} · cert ${s.auth_alg || NR} · ${he.openssl_version || ""}` }) }), columns: [
          { label: "service", render: ({ s }) => s.service_id },
          { label: "pq handshake", render: ({ kex }) => chip(res(kex)) },
          { label: "auth", optional: true, render: ({ auth }) => chip(res(auth)) },
          { label: "downgrade", render: ({ down }) => chip(res(down), refused(down)) }] }),
        { aside: h("span", { class: "fine mono", text: he.openssl_version || "" }) });
      const compatT = section("Compatibility", table({ caption: "Modes by client", rows: g.compat_matrix || [], empty: NR, columns: [
          { label: "mode", render: (c) => two(mono(c.mode), sub(`gate ${c.result}`)) },
          ...clients.map((cl) => ({ label: cl, render: (c) => {
            const x = (c.cells || []).find((y) => y.client === cl);
            return x ? h("span", { tabindex: "0", "data-prov": provAttr(src(g.run_id, "compat gate", x.timestamp, x.reason), `${c.mode} · ${cl}`) },
              chip(x.result), sub((x.actual && (x.actual.negotiated_group || x.actual.error)) || "")) : h("span", { class: "fine", text: "not tested" });
          } }))] }));
      const wavesT = section("Wave gates", table({ caption: "Lab services per wave", rows: waves, empty: "no wave is mapped to a lab service",
          expand: ({ w, e, p }) => ({ why: `${e.from_mode} → ${e.to_mode} for ${(e.assets || []).join(", ")}${p ? `; negotiated ${p.negotiated_group || "nothing"}` : ""}.`,
            hash: e.applied_config_sha256, run_id: w.evidence.run_id, ts: e.finished_at || w.evidence.ts, technical: p && p.transcript_sha256 ? h("span", { class: "mono", text: `transcript ${p.transcript_sha256}` }) : null }), columns: [
          { label: "week", numeric: true, render: ({ w }) => String(w.week) },
          { label: "lab service", render: ({ e }) => e.lab_service },
          { label: "status", render: ({ e }) => chip(e.status || NR) },
          { label: "pq handshake", render: ({ p }) => chip(res(p)) }] }));
      const rollT = section("Tested rollback", fr ? kv(["service", mono(`${fr.service_id}: ${fr.from_mode} → ${fr.to_mode}`)], ["outcome", chip(fr.status || NR)],
          ["snapshot", hash(fr.snapshot_sha256, "snapshot hash")],
          ["restored", two(hash(fr.restored_config_sha256, "restored hash"),
            fr.restored_config_sha256 ? sub(`restored ${fr.restored_config_sha256 === fr.snapshot_sha256 ? "equals" : "differs from"} snapshot`) : null)],
          ["health check", mono(fr.health_check ? `${fr.health_check.client}: ${fr.health_check.result} (${fr.health_check.negotiated_group || "no handshake"})` : NR)])
          : h("p", { class: "fine", text: NR }));
      const hybrid = rows.filter((x) => !x.live && !x.classical).length, lab = rows.filter((x) => !x.live).length;
      const passed = (r.waves || []).filter((w) => w.status === "applied").length;
      const gsrc = src(g.run_id || he.run_id, "gates/ lab run", g.ts || he.ts);
      return h("div", {},
        keyStats([
          { label: "lab connections on post-quantum", cell: num(hybrid, src(he.run_id, he.openssl_version, he.ts)), unit: `of ${lab} lab services`, mean: "Handshakes that used hybrid X25519 + ML-KEM-768; the rest are harvest-now-decrypt-later exposed." },
          { label: "waves passed every gate", cell: num(passed, gsrc), unit: `of ${(r.waves || []).length} waves`, mean: "A wave counts only when its handshake, downgrade, compatibility and rollback gates all pass." },
          { label: "rollback tested", cell: num(fr && fr.restored_config_sha256 === fr.snapshot_sha256 ? 1 : 0, gsrc), unit: fr ? `${fr.status}` : "not run", mean: "A forced failure was rolled back and the exact previous configuration was restored." },
        ]),
        main(h("div", {}, el, dd({ read: "each strand is one recorded lab handshake. A single red strand is classical key exchange (HNDL-exposed); a braid is hybrid X25519 + ML-KEM-768; a wall means a classical-only client was refused." }), wavesT, labT), { title: "Gates per wave" }),
        detailsList([
          { title: "How it works", summary: "Each wave is switched on real TLS 1.3 lab services and checked four ways.", body: bullets([
            ["Post-quantum handshake: the server must negotiate ", term("hybrid", "hybrid key exchange"), " (X25519MLKEM768)."],
            "Downgrade: a classical-only client must be refused in strict mode.",
            "Compatibility: every client type is tested against every mode.",
            "Rollback: a forced failure must restore the exact previous config hash."]) },
          { title: "Why this method", summary: "A migration only counts when a real handshake proves it.", body: bullets([
            "Configuration alone can claim post-quantum without using it; the handshake is the evidence.",
            ["Classical-only sessions are labelled \"", HNDL, "\"."]]) },
          { title: "Evidence & sources", summary: `${he.openssl_version || "OpenSSL"} · transcripts hashed, never keys`, body: h("div", {}, compatT, rollT, liveT, h("p", { class: "fine", text: he.note })) },
          { title: "Limits", summary: "Lab services on 127.0.0.1 stand in for production; assets without a lab service are \"not verified in lab\".", body: bullets([
            "Only the handshake is recorded (s_client -brief -msg); no keys and no traffic.", "TLS 1.3 only in strict mode, so clients cannot fall back to classical FFDHE."]) }]),
        nextStep(ctx, "handshakes"));
    },
  });
  ctx.root.append(h("div", { class: "grid" }, h("div", { class: "span-12" },
    pageHead(ctx, { route: "handshakes", title: "Handshake gates", headline: "Does each migrated wave really use post-quantum key exchange, refuse old clients, and roll back safely?" }), body, honesty())));
}
