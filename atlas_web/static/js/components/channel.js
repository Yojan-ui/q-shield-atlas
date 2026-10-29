// Sender vs receiver: a replay of recorded TLS 1.3 handshakes (Move page). Every packet is one message from a
// recorded `openssl s_client -msg` transcript (GET /api/workspaces/<ws>/move, hash-checked against capture.json),
// drawn with a width proportional to its recorded byte length; key shares are drawn inside their hello.
// Nothing is simulated: a lane without a recorded session says "not run". Motion is the message order only.
import { h } from "../dom.js";
import { provAttr } from "./tooltip.js";

export const isHybrid = (g) => /MLKEM/i.test(g || "");
export const PX_PER_BYTE = 0.11;
export const packetWidth = (bytes) => Math.max(10, Math.round((bytes || 0) * PX_PER_BYTE));
export const fmtBytes = (n) => `${Number(n).toLocaleString("en-US")} B`;
const AUTH = { mldsa65: "ML-DSA-65", mldsa44: "ML-DSA-44", mldsa87: "ML-DSA-87" };
export const authName = (s) => (s && (AUTH[s.signature_type] || s.cert_alg)) || null;
const SHOWN = new Set(["ClientHello", "HelloRetryRequest", "ServerHello", "EncryptedExtensions", "Certificate", "CertificateVerify", "Finished", "Alert"]);
// ChangeCipherSpec is a 1-byte TLS 1.2 compatibility record with no meaning in TLS 1.3; it is listed, not animated
export const packetsOf = (s) => ((s && s.messages) || []).filter((m) => SHOWN.has(m.type));

// Pick the recorded sessions each lane replays. Same client in both lanes (the one that offers a hybrid group),
// so the only difference shown is the server.
export function pickLanes(move, gates = {}) {
  const ok = (s) => s && s.transcript_verified && s.messages && s.messages.length;
  const S = ((move && move.sessions) || []).filter(ok);
  const pqClient = (s) => isHybrid(s.client_groups_offered);
  const before = S.find((s) => pqClient(s) && !isHybrid(s.negotiated_group)) || S.find((s) => !isHybrid(s.negotiated_group)) || null;
  const hyb = S.filter((s) => pqClient(s) && isHybrid(s.negotiated_group));
  const after = hyb.find((s) => !/ML-DSA/i.test(s.cert_alg || "")) || hyb[0] || null;
  const pqAuth = S.find((s) => /ML-DSA/i.test(s.cert_alg || "")) || null;
  const byService = (list, id) => (list || []).find((g) => g.service_id === id) || null;
  const target = after && after.service_id;
  const refusedRec = ((move && move.refused_attempts) || []).find((s) => s.service_id === target) || null;
  const downGate = byService(gates.downgrade, target);
  let downgrade;
  if (!target) downgrade = { state: "not_run", text: "not run: no hybrid service recorded" };
  else if (refusedRec && ok(refusedRec)) downgrade = { state: "refused", session: refusedRec, gate: downGate, text: "Refused: no silent downgrade" };
  else if (downGate && downGate.result === "FAIL") downgrade = { state: "accepted", gate: downGate, text: `Accepted: ${downGate.reason}` };
  else downgrade = { state: "not_run", gate: downGate, text: "not run: no classical-only attempt recorded" };
  const auth = [after, pqAuth].filter(Boolean).map((s) => ({ session: s, gate: byService(gates.pq_auth, s.service_id) }));
  return { before, after, pqAuth, downgrade, auth };
}

// Position of packet k at replay clock t (message units): 0..1 while in flight, null otherwise.
export function flight(t, k) { const f = t - k; return f >= 0 && f < 1 ? f : null; }
const ease = (f) => (f < 0.5 ? 2 * f * f : 1 - (-2 * f + 2) ** 2 / 2);

const W = 1100, SX = 282, RX = 818, BOXW = 262;  // viewBox ~ rendered px at 1440 wide, so SVG text sizes are real px
const svg = (tag, attrs = {}, ...kids) => h(tag, { ns: "svg", ...attrs }, ...kids);

function endBox(x, y, hgt, lines, prov) {
  return svg("g", { class: "ch-box", tabindex: prov ? "0" : null, "data-prov": prov },
    svg("rect", { x, y, width: BOXW, height: hgt, rx: 2 }),
    lines.map(([cls, text], i) => svg("text", { x: x + 14, y: y + 26 + i * 23, class: cls }, text)));
}

// Build the SVG scene. lanes: [{id, title, caption, tone, session, sender, receiver, prov, end}] -> {el, set(t)}
export function buildChannel(lanes, { runId }) {
  const LANE_H = 214, TOP = 44, H = TOP + lanes.length * LANE_H;
  const root = svg("svg", { viewBox: `0 0 ${W} ${H}`, class: "ch-svg", role: "img",
    "aria-label": `Replay of recorded handshake, run ${runId}. ${lanes.map((l) => `${l.title}: ${l.session ? packetsOf(l.session).map((m) => m.type).join(", ") : "not run"}`).join(". ")}` });
  root.append(svg("text", { x: 0, y: 22, class: "ch-replay" }, `Replay of recorded handshake, run ${runId}`),
    svg("text", { x: W, y: 22, class: "ch-replay", "text-anchor": "end" }, "packet width = recorded message size"));
  const movers = [];
  lanes.forEach((l, li) => {
    const y0 = TOP + li * LANE_H, cy = y0 + 118;
    const g = svg("g", { class: `ch-lane ${l.tone}` });
    g.append(svg("text", { x: 0, y: y0 + 30, class: "ch-title" }, l.title),
      svg("text", { x: W, y: y0 + 30, class: `ch-cap ${l.tone}`, "text-anchor": "end" }, l.caption),
      endBox(0, y0 + 44, 150, l.sender, null),
      endBox(RX + 20, y0 + 44, 150, l.receiver, l.prov),
      svg("line", { x1: SX, x2: RX, y1: cy, y2: cy, class: "ch-wire" }),
      svg("text", { x: SX, y: cy + 52, class: "ch-dir" }, "→ sender to receiver"),
      svg("text", { x: RX, y: cy + 52, class: "ch-dir", "text-anchor": "end" }, "receiver to sender ←"));
    if (!l.session) g.append(svg("text", { x: (SX + RX) / 2, y: cy + 6, class: "ch-none", "text-anchor": "middle" }, "not run"));
    const pk = packetsOf(l.session);
    const els = pk.map((m) => {
      const w = Math.min(packetWidth(m.bytes), RX - SX - 20);
      const share = (m.key_share || []).find((k) => k.bytes);
      const p = svg("g", { class: `ch-pkt ${m.type === "Alert" ? "alert" : ""}`, visibility: "hidden" },
        svg("rect", { x: 0, y: -12, width: w, height: 24, class: "ch-body" }),
        share ? svg("rect", { x: 0, y: -12, width: Math.min(w, packetWidth(share.bytes)), height: 24, class: "ch-share" }) : null,
        null);
      g.append(p);
      return { m, w, p, text: `${m.dir === "c2s" ? "→" : "←"} ${m.type}${m.alert ? ` (${m.alert})` : ""} · ${fmtBytes(m.bytes)}${share ? ` · key share ${fmtBytes(share.bytes)}` : ""}` };
    });
    const endLabel = l.end ? svg("text", { x: (SX + RX) / 2, y: cy + 6, class: `ch-end ${l.end.tone}`, "text-anchor": "middle", visibility: "hidden" }, l.end.text) : null;
    if (endLabel) g.append(endLabel);
    root.append(g);
    // one packet per lane is in flight at a time: its name and size sit in one fixed place above the wire
    const cur = svg("text", { x: (SX + RX) / 2, y: cy - 30, class: "ch-plabel", "text-anchor": "middle" });
    g.append(cur);
    movers.push({ els, cy, endLabel, cur, n: els.length, shown: -1 });
  });
  const set = (t) => {
    for (const L of movers) {
      const k0 = Math.floor(t);
      if (k0 !== L.shown) { L.shown = k0; L.cur.textContent = L.els[k0] ? L.els[k0].text : ""; }
      L.els.forEach(({ m, w, p }, k) => {
        const f = flight(t, k);
        if (f === null) { p.setAttribute("visibility", "hidden"); return; }
        const e = ease(f), span = RX - SX - w;
        const x = m.dir === "c2s" ? SX + e * span : RX - w - e * span;
        p.setAttribute("transform", `translate(${x.toFixed(1)} ${L.cy})`);
        p.setAttribute("visibility", "visible");
      });
      if (L.endLabel) L.endLabel.setAttribute("visibility", t >= L.n ? "visible" : "hidden");
    }
  };
  return { el: root, set, length: Math.max(1, ...movers.map((L) => L.n)) };
}

// One row per recorded message (the same list the packets replay), current message highlighted.
export function transcriptList(session, prov) {
  if (!session) return h("p", { class: "ch-nr", text: "not run" });
  const pk = packetsOf(session);
  const rows = (session.messages || []).map((m) => h("li", { class: `ch-row ${m.dir}`, "data-k": String(pk.indexOf(m)), tabindex: "0", "data-prov": prov },
    h("span", { class: "ch-arrow", "aria-label": m.dir === "c2s" ? "sender to receiver" : "receiver to sender", text: m.dir === "c2s" ? "→" : "←" }),
    h("span", { class: "ch-type", text: `${m.type}${m.alert ? ` (${m.alert})` : ""}` }),
    h("span", { class: "ch-bytes num", text: fmtBytes(m.bytes) }),
    h("span", { class: "ch-ks", text: (m.key_share || []).map((k) => (k.requested ? `asks for ${k.group}` : `${k.group} share ${fmtBytes(k.bytes)}`)).join(", ") })));
  const list = h("ol", { class: "ch-list" }, rows);
  return { el: list, mark(t) { const k = Math.floor(t); for (const r of rows) r.classList.toggle("on", r.dataset.k === String(k)); } };
}

export const sessionProv = (move, s, title) => s ? provAttr({ run_id: move.run_id, solver: move.openssl_version || "openssl s_client -msg",
  job_id: "none (local lab capture, no backend job)", ts: s.timestamp || move.ts, note: `${s.transcript_file} · sha256 ${s.transcript_sha256.slice(0, 16)}…` }, title) : null;
