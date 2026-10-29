// Move: sender vs receiver. Two lanes replay the recorded handshakes of the same client against the old (classical)
// and the migrated (hybrid) lab service, packet by packet with their real byte sizes; a third lane replays the
// recorded classical-only attempt (refused, accepted, or "not run"). Below, the week slider walks the logged plan:
// each wave moves its systems from "old" to "moved", with that wave's recorded lab gate results. "Verified in lab"
// is the strongest state shown and only for lab stand-ins; real bank endpoints are "observed" or "planned", never
// applied. With reduced motion (OS setting or the toggle) nothing plays by itself; Step still walks the messages.
import { h, icon } from "../dom.js";
import { chip } from "../components/chip.js";
import { emptyState } from "../components/states.js";
import { prefersReducedMotion } from "../motion.js";
import { HNDL } from "../model.js";
import { provAttr } from "../components/tooltip.js";
import { authName, buildChannel, fmtBytes, packetsOf, pickLanes, sessionProv, transcriptList } from "../components/channel.js";
import { clusterOf } from "../scenes/migration.js";
import { dataView, honesty, mountScene, notRun, stage, viewCss } from "./common.js";
import { buildLanes3d } from "../scenes/lanes3d.js";
import { bullets, detailsList, nextStep, pageHead } from "../components/page.js";

export const LANES = [
  { id: "classical", title: "Still on old encryption", sub: "quantum-exposed (RSA / ECC)", tone: "exposed" },
  { id: "migrating", title: "Moving this week", sub: "in this week's wave", tone: "accent" },
  { id: "done", title: "Moved by the plan", sub: "lab result on each tile", tone: "pass" },
];
const RESULT = { applied: ["PASS", "verified in lab"], partially_verified: ["partially_verified", "partly verified in lab"],
  not_verified_in_lab: ["not_verified_in_lab", "not verified in lab"], rolled_back: ["rolled_back", "rolled back"],
  rollback_failed: ["FAIL", "rollback failed"], planned: ["planned", "planned"] };
export const GATES = ["pq_handshake", "downgrade", "pq_auth", "compat", "rollback"];
const SPEEDS = [0.5, 1, 2, 4], RATE = 1.1, HOLD = 1.6;  // messages per second at 1x; pause after the last message

export function laneOf(asset, week) {
  if (week < asset.planned_week) return "classical";
  if (week === asset.planned_week) return "migrating";
  return "done";
}

// external: real endpoints (bank mode) can be moved by the plan but are never "verified in lab"
export function progress(assets, week, external = {}) {
  const done = assets.filter((a) => laneOf(a, week) === "done");
  return { done: done.length, total: assets.length, verified: done.filter((a) => a.status === "applied" && !external[a.id]).length };
}

// "Wave 2 of 7 · 3 of 3 stand-ins verified in lab" for the selected week
export function waveStatus(waves, week, last) {
  const W = [...(waves || [])].sort((a, b) => a.week - b.week);
  const labs = (w) => ((w && w.evidence && w.evidence.lab_services) || []);
  const ok = (e) => e.status === "applied" || (e.gates && e.gates.passed === true);
  if (!W.length) return { text: "No wave in this plan", wave: null };
  if (week >= last) {
    const all = W.flatMap(labs);
    return { text: `All ${W.length} waves done · ${all.filter(ok).length} of ${all.length} stand-ins verified in lab`, wave: null };
  }
  const i = W.findIndex((w) => w.week === week);
  if (i < 0) return { text: week === 0 ? `Start · 0 of ${W.length} waves done` : `Week ${week} · no wave this week · ${W.filter((w) => w.week < week).length} of ${W.length} waves done`, wave: null };
  const L = labs(W[i]);
  return { text: `Wave ${i + 1} of ${W.length} · ${L.length ? `${L.filter(ok).length} of ${L.length} stand-in${L.length === 1 ? "" : "s"} verified in lab` : "no lab stand-in: not verified in lab"}`, wave: W[i] };
}

// one gate cell of a wave's lab stand-in: the recorded result, or "not run in this wave"
export function gateCell(e, gate) {
  const g = (e && e.gates) || {};
  const x = g[gate] || g[`${gate}_refused`];
  if (x && x.result) return { result: x.result, text: x.negotiated_group || x.auth_alg || x.mode || "" };
  if (gate === "rollback" && e && (e.status === "rolled_back" || e.status === "rollback_failed")) return { result: e.status, text: e.restored_config_sha256 ? "config restored" : "" };
  return { result: "NOT_RUN", text: "not run in this wave" };
}

export async function mount(ctx) {
  await Promise.all([viewCss("move"), viewCss("pillars")]);
  // 3D sender / receiver lanes in the persistent world, on the same replay clock as the SVG below
  const labels3d = h("div", { class: "gr-labels", "aria-hidden": "true" });
  const stage3d = stage(ctx, { label: "3D replay of the recorded handshakes: sender on the left, receiver on the right, one lane per handshake; packet length is the recorded message size.", fallback: h("span") });
  stage3d.append(labels3d);
  let layer3d = null;
  let reduced = prefersReducedMotion();
  const body = dataView(ctx, {
    keys: ["results", "move"],
    skeleton: () => h("div", { class: "ch-stage skel" }, h("p", { class: "fine", text: "Loading the recorded handshakes…" })),
    render: ({ model: m, move }) => {
      const r = m && m.results;
      if (!r || !r.assets) return emptyState(notRun(ctx, "Migration"));
      if (!r.assets.length) return emptyState({ title: "Nothing to migrate", body: "The scan found no RSA / ECC to replace in this workspace.", action: null });
      const mv = move && move.available ? move : null, g = r.gates || {};
      const external = (move && move.observed) || {};
      const bankMode = Object.keys(external).length > 0;
      // the handshake scene for one capture (recorded, or a fresh lab run): lanes, packets, transcript lists, auth bars
      const sceneOf = (mv, g, fresh) => {
        const L = mv ? pickLanes(mv, g) : { before: null, after: null, downgrade: { state: "not_run", text: "not run" }, auth: [] };
        const gateOf = (list, s) => s && (list || []).find((x) => x.service_id === s.service_id);
        const offers = (s) => (s ? s.client_groups_offered.split(":").join(" · ") : "not run");
        const recv = (s, tone) => s ? [["ch-k", "RECEIVER (server)"], ["ch-v", `lab service: ${s.service_id}`], [`ch-big ${tone}`, s.negotiated_group || "no handshake"],
          ["ch-s", s.protocol || s.error || ""], ["ch-s", s.cipher || ""], ["ch-s", `cert ${authName(s) || "n/a"} · pq_auth ${(gateOf(g.pq_auth, s) || {}).result || "not run"}`]] : [["ch-k", "RECEIVER (server)"], ["ch-s", "not run"]];
        const down = L.downgrade, dsess = down.session || null;
        const lanes = [
          { title: `Before: classical key exchange (${L.before ? L.before.negotiated_group : "not run"})`, caption: "Recorded traffic can be harvested now and decrypted later (HNDL-exposed)", tone: "exp",
            session: L.before, sender: [["ch-k", "SENDER (client)"], ["ch-s", "offers"], ["ch-v", offers(L.before)], ["ch-s", "same client in both lanes"]], receiver: recv(L.before, "exp"),
            prov: sessionProv(mv, L.before, fresh ? "Before lane: fresh lab handshake" : "Before lane: recorded handshake"), end: L.before && { text: `Handshake done on ${L.before.negotiated_group}: HNDL-exposed`, tone: "exp" } },
          { title: `After: hybrid ${L.after ? L.after.negotiated_group : "not run"}`, caption: "Quantum-resistant key exchange", tone: "ok",
            session: L.after, sender: [["ch-k", "SENDER (client)"], ["ch-s", "offers"], ["ch-v", offers(L.after)], ["ch-s", "same client in both lanes"]], receiver: recv(L.after, "ok"),
            prov: sessionProv(mv, L.after, fresh ? "After lane: fresh lab handshake" : "After lane: recorded handshake"), end: L.after && { text: `Handshake done on ${L.after.negotiated_group}`, tone: "ok" } },
          { title: `Downgrade attempt: classical-only client to ${L.after ? L.after.service_id : "the hybrid service"}`, caption: down.state === "refused" ? "The server must refuse, not silently fall back to classical" : down.text, tone: "neutral",
            session: dsess, sender: [["ch-k", "SENDER (client)"], ["ch-s", "offers only"], ["ch-v", offers(dsess)], ["ch-s", "no post-quantum group"]],
            receiver: dsess ? [["ch-k", "RECEIVER (server)"], ["ch-v", `lab service: ${dsess.service_id}`], [`ch-big ${down.state === "refused" ? "ok" : "exp"}`, down.state === "refused" ? "refused" : "accepted"], ["ch-s", dsess.error || ""], ["ch-s", `downgrade gate ${(down.gate || {}).result || "not run"}`]] : [["ch-k", "RECEIVER (server)"], ["ch-s", down.text]],
            prov: sessionProv(mv, dsess, fresh ? "Downgrade attempt: fresh lab handshake" : "Downgrade attempt: recorded"), end: { text: down.text, tone: down.state === "refused" ? "ok" : down.state === "accepted" ? "exp" : "none" } },
        ];
        const ch = buildChannel(lanes, { runId: mv ? mv.run_id : "not yet run", title: fresh ? `Fresh lab handshake on 127.0.0.1, run ${mv.run_id} · not part of results.json, not signed` : null });
        const lists = lanes.map((l) => transcriptList(l.session, l.prov));
        // ---------- authentication (who the receiver is) ----------
        const authRows = L.auth.map(({ session: s, gate }) => {
          const pk = packetsOf(s), cert = pk.find((x) => x.type === "Certificate"), cv = pk.find((x) => x.type === "CertificateVerify");
          const tot = (cert ? cert.bytes : 0) + (cv ? cv.bytes : 0), pass = gate && gate.result === "PASS";
          return { s, gate, cert, cv, tot, pass };
        });
        const maxAuth = Math.max(1, ...authRows.map((x) => x.tot));
        const authBox = authRows.length ? h("div", { class: "mv-auth" }, authRows.map(({ s, gate, cert, cv, tot, pass }) => h("div", { class: "mv-auth-row", tabindex: "0", "data-prov": sessionProv(mv, s, `${s.service_id}: server authentication`) },
          h("p", { class: "mv-auth-h" }, h("span", { class: "mono", text: `${authName(s)}` }), ` · ${s.service_id} · `, chip(gate ? gate.result : "NOT_RUN", `pq_auth ${gate ? gate.result : "not run"}`)),
          h("div", { class: "mv-auth-bar" }, h("span", { class: pass ? "ok" : "exp", style: { width: `${(tot / maxAuth) * 100}%` } })),
          h("p", { class: "mv-note", text: `Certificate ${cert ? fmtBytes(cert.bytes) : "n/a"} + CertificateVerify ${cv ? fmtBytes(cv.bytes) : "n/a"} = ${fmtBytes(tot)}. ${gate ? gate.reason : "no pq_auth gate recorded"}` })))) : h("p", { class: "mv-note", text: "not run" });
        return { L, lanes, ch, lists, authBox };
      };
      let S = sceneOf(mv, g, false);
      // ---------- plan: weeks and waves ----------
      const banks = bankMode ? [...new Set(r.assets.map(clusterOf))].sort() : [];
      let bank = bankMode && banks.includes(ctx.query.get("bank")) ? ctx.query.get("bank") : "";
      const all = [...r.assets].sort((a, b) => a.planned_week - b.planned_week || a.id.localeCompare(b.id));
      const last = Math.max(...all.map((a) => a.planned_week)) + 1;
      let week = Math.min(last, Math.max(0, Number(ctx.query.get("week") ?? last)));
      const wr = g.wave_run_id;
      const reviewHref = (a) => `/w/${ctx.ws}/review${wr ? `?item=${encodeURIComponent(`wave:${wr}:${a.planned_week}`)}` : ""}`;
      const tileLanes = Object.fromEntries(LANES.map((l) => [l.id, h("ul", { class: "mg-tiles", "aria-label": l.title })]));
      const tiles = new Map(all.map((a) => {
        const ob = external[a.id];
        const res = ob ? ["planned", "planned: endpoint not changed"] : RESULT[a.status] || RESULT.planned;
        const t = h("li", { class: "mg-tile", "data-id": a.id, tabindex: "0",
          "data-prov": provAttr({ run_id: wr || "n/a", solver: "gates/ lab waves", job_id: "none (local lab run, no backend job)", ts: g.ts || "n/a",
            note: ob ? `observed once: ${ob.negotiated_group} ${ob.tls_version}, cert ${ob.cert_key_algorithm} (${ob.source})` : `status ${a.status}` }, a.name) },
          h("a", { href: `/w/${ctx.ws}/asset/${encodeURIComponent(a.id)}`, class: "mg-name", text: a.name }),
          h("span", { class: "mg-meta" }, `${a.algorithm} · wave ${a.planned_week} · `, h("a", { href: reviewHref(a), text: "review" })),
          ob ? h("span", { class: "mg-meta" }, chip(ob.outcome === "hybrid_pq" ? "hybrid" : "HNDL-exposed", `observed: ${ob.negotiated_group} · ${ob.tls_version}`)) : null,
          h("span", { class: "mg-res" }, chip(...res)));
        return [a.id, t];
      }));
      const bar = h("div", { class: "mg-bar", role: "progressbar", "aria-valuemin": "0" }, h("span", { class: "mg-fill" }), h("span", { class: "mg-fill verified" }));
      const status = h("p", { class: "mv-status", "aria-live": "polite" }), count = h("p", { class: "mg-progress" }), mean = h("p", { class: "mv-mean" });
      const gatesBox = h("div", { class: "mv-gates" });
      const range = h("input", { type: "range", min: "0", max: String(last), step: "1", value: String(week), "aria-label": "week of the plan" });
      const wk = h("output", { class: "num mv-week" });
      const playBtn = h("button", { class: "btn primary", type: "button" }), stepBtn = h("button", { class: "btn", type: "button" }, icon("arrow"), "Step");
      const speed = h("select", { class: "mv-speed", "aria-label": "replay speed" }, SPEEDS.map((s) => h("option", { value: String(s), selected: s === 1 ? true : null, text: `${s}×` })));
      const motionBtn = h("button", { class: "btn", type: "button" });
      const bankSel = bankMode ? h("select", { class: "mv-speed", "aria-label": "bank" }, h("option", { value: "", text: `All banks (${banks.length})` }),
        banks.map((b) => h("option", { value: b, selected: b === bank ? true : null, text: b }))) : null;
      const shown = () => (bank ? all.filter((a) => clusterOf(a) === bank) : all);
      const gateTable = (wave) => {
        const labs = (wave && wave.evidence && wave.evidence.lab_services) || [];
        if (!wave) return h("p", { class: "mv-note", text: "Move the week slider onto a wave to see its recorded gate results." });
        const noLab = (wave.assets || []).filter((id) => (wave.asset_status || {})[id] === "not_verified_in_lab");
        return h("div", {},
          h("table", { class: "data mv-gt" }, h("caption", { text: `Wave at week ${wave.week}: gate results recorded for each lab stand-in (run ${(wave.evidence || {}).run_id || "n/a"})` }),
            h("thead", {}, h("tr", {}, h("th", { text: "lab stand-in" }), h("th", { text: "systems it stands in for" }), GATES.map((x) => h("th", { text: x })))),
            h("tbody", {}, labs.length ? labs.map((e) => h("tr", {}, h("td", { class: "mono", text: `${e.lab_service}: ${e.from_mode} → ${e.to_mode}` }),
              h("td", { text: (e.assets || []).map((id) => (external[id] ? `${id} (planned)` : id)).join(", ") }),
              GATES.map((x) => { const c = gateCell(e, x); return h("td", { tabindex: "0", "data-prov": provAttr({ run_id: wave.evidence.run_id, solver: `gate ${x}`, job_id: "none (local lab run, no backend job)", ts: e.started_at || wave.evidence.ts, note: c.text || c.result }, `${e.lab_service} · ${x}`) }, chip(c.result, c.result === "NOT_RUN" ? "not run in this wave" : null), c.text && c.result !== "NOT_RUN" ? h("span", { class: "sub", text: ` ${c.text}` }) : null); })))
              : h("tr", {}, h("td", { colspan: String(2 + GATES.length), text: "no lab stand-in in this wave: not verified in lab" })))),
          g.forced_rollback ? h("p", { class: "mv-note" }, chip(g.forced_rollback.status || "NOT_RUN"), ` tested rollback (gates run ${g.run_id}): forced failure on ${g.forced_rollback.service_id}, ${g.forced_rollback.restored_config_sha256 && g.forced_rollback.restored_config_sha256 === g.forced_rollback.snapshot_sha256 ? "restored config hash equals the snapshot" : "config not restored"}`) : null,
                    noLab.length ? h("p", { class: "mv-note" }, chip("not_verified_in_lab"), ` no lab stand-in for this kind: ${noLab.join(", ")}`) : null,
          bankMode ? h("p", { class: "mv-note", text: "Bank endpoints are only observed (one recorded handshake each) and planned. The gate results above belong to the lab stand-in on 127.0.0.1, not to any bank." }) : null);
      };
      const drawPlan = () => {
        const A = shown();
        const rects = reduced ? null : new Map([...tiles].map(([id, t]) => [id, t.getBoundingClientRect()]));
        for (const a of all) {
          const t = tiles.get(a.id), lane = laneOf(a, week), on = A.includes(a);
          t.hidden = !on;
          t.dataset.lane = lane;
          t.querySelector(".mg-res").hidden = lane !== "done";
          if (t.parentElement !== tileLanes[lane]) tileLanes[lane].append(t);
        }
        if (rects) for (const [id, t] of tiles) {  // FLIP: slide each tile from its old place
          const a = rects.get(id), b = t.getBoundingClientRect();
          if (a.width && b.width && (a.left !== b.left || a.top !== b.top)) t.animate([{ transform: `translate(${a.left - b.left}px, ${a.top - b.top}px)` }, { transform: "none" }], { duration: 520, easing: "cubic-bezier(.2,.7,.2,1)" });
        }
        const p = progress(A, week, external), ws = waveStatus(r.waves, week, last);
        status.textContent = ws.text;
        wk.textContent = week === 0 ? "start" : week >= last ? `week ${last - 1} done` : `week ${week}`;
        bar.setAttribute("aria-valuemax", String(p.total));
        bar.setAttribute("aria-valuenow", String(p.done));
        bar.setAttribute("aria-valuetext", `${p.done} of ${p.total} systems moved, ${p.verified} verified in lab`);
        bar.children[0].style.width = `${(p.done / p.total) * 100}%`;
        bar.children[1].style.width = `${(p.verified / p.total) * 100}%`;
        count.replaceChildren(h("span", { class: "num", text: `${p.done} / ${p.total}` }), " systems moved by the plan · ", h("span", { class: "num", text: String(p.verified) }), " verified in the lab");
        const left = p.total - p.done;
        mean.textContent = left ? `${left} system${left === 1 ? " still uses" : "s still use"} classical key exchange at this point in the plan: traffic recorded today is at risk (${HNDL}).`
          : bankMode ? `By the end of the plan every endpoint is scheduled. Bank endpoints stay "planned": nothing outside the lab was changed.`
          : `By the end of the plan every system has moved; ${p.verified} of ${p.total} passed every lab gate, the rest are partly verified or have no lab stand-in.`;
        gatesBox.replaceChildren(gateTable(ws.wave));
      };
      // ---------- replay clock ----------
      let t = reduced ? S.ch.length + HOLD : 0, running = false, advancing = false, raf = 0, prev = 0;
      const cycle = () => S.ch.length + HOLD;
      const paint = () => { S.ch.set(t); if (layer3d) layer3d.set(t); for (const l of S.lists) if (l && l.mark) l.mark(t); };
      const mount3d = () => mountScene(ctx, "migration", { available: !!mv }, (env) => buildLanes3d(env, S.lanes, { labelsEl: labels3d, stageEl: stage3d }))
        .then((l) => { layer3d = l; if (l) l.set(t); }).catch(() => {});
      const label = () => {
        playBtn.replaceChildren(icon(running ? "dash" : "play"), running ? "Pause" : "Play the plan");
        motionBtn.replaceChildren(icon(reduced ? "dash" : "spin"), reduced ? "Motion off" : "Motion on");
        motionBtn.setAttribute("aria-pressed", String(reduced));
      };
      const setWeek = (w) => { week = w; range.value = String(w); ctx.setQuery({ week: String(w) }); drawPlan(); };
      const frame = (now) => {
        if (!running || ctx.signal.aborted) return;
        const dt = Math.min(0.1, (now - prev) / 1000); prev = now;
        t += dt * RATE * Number(speed.value);
        if (t >= cycle()) {
          t = 0;
          if (advancing) { if (week >= last) { running = false; advancing = false; t = cycle() - 0.01; label(); paint(); return; } setWeek(week + 1); ctx.announce(status.textContent); }
        }
        paint();
        raf = requestAnimationFrame(frame);
      };
      const start = (adv) => { running = true; advancing = adv; prev = performance.now(); cancelAnimationFrame(raf); raf = requestAnimationFrame(frame); label(); };
      const stop = () => { running = false; advancing = false; cancelAnimationFrame(raf); label(); };
      playBtn.addEventListener("click", () => {
        if (running && advancing) return stop();
        if (week >= last) setWeek(0);
        t = 0;
        if (reduced) { setWeek(Math.min(last, week + 1)); t = cycle() - 0.01; paint(); return; }  // no motion: one week per press
        start(true);
      }, { signal: ctx.signal });
      stepBtn.addEventListener("click", () => {
        stop();
        const k = Math.floor(t);
        t = t >= S.ch.length ? 0.5 : Math.min(S.ch.length, k + (t - k < 0.5 ? 0.5 : 1.5));  // freeze each packet mid-channel
        if (t > S.ch.length) t = S.ch.length + HOLD;
        paint();
      }, { signal: ctx.signal });
      range.addEventListener("input", () => { if (advancing) stop(); setWeek(Number(range.value)); }, { signal: ctx.signal });
      if (bankSel) bankSel.addEventListener("change", () => { bank = bankSel.value; ctx.setQuery({ bank: bank || null }); drawPlan(); }, { signal: ctx.signal });
      motionBtn.addEventListener("click", () => {
        reduced = !reduced;
        if (reduced) { stop(); t = cycle() - 0.01; paint(); } else start(false);
        label();
      }, { signal: ctx.signal });
      ctx.signal.addEventListener("abort", () => cancelAnimationFrame(raf), { once: true });
      label(); drawPlan(); mount3d(); paint();
      if (!reduced && mv) start(false);  // the handshake replay loops; weeks only advance on "Play the plan"
      const tlist = (i, title) => h("div", { class: `mv-tl ${S.lanes[i].tone}` }, h("p", { class: "mv-tl-h", text: title }), S.lists[i] && S.lists[i].el ? S.lists[i].el : S.lists[i]);
      const tlists = () => [tlist(0, "Before: messages"), tlist(1, "After: messages"), tlist(2, "Downgrade attempt: messages")];
      const stageBox = h("div", {}, S.ch.el), tlsBox = h("div", { class: "mv-tls" }, tlists()), authWrap = h("div", {}, S.authBox);
      // optional "Run fresh handshake now" (config fresh_handshake.enabled, operators): lab services on 127.0.0.1 only
      const fs = (move && move.fresh) || { enabled: false, reason: "not available" };
      const canRun = fs.enabled && ctx.me && ctx.me.role !== "viewer";
      const freshBtn = h("button", { class: "btn", type: "button", disabled: canRun ? null : true }, icon("spin"), "Run fresh handshake now");
      const backBtn = h("button", { class: "btn quiet", type: "button", hidden: true }, icon("rewind"), "Back to the recorded run");
      const freshNote = h("p", { class: "mv-note", "aria-live": "polite", text: !fs.enabled ? `Fresh handshake ${fs.reason}` : canRun ? "Starts the lab TLS services on 127.0.0.1, records one handshake per service, stops them. Never contacts another host." : "Fresh handshake: operators only." });
      const swap = (mvX, gX, fresh) => {
        S = sceneOf(mvX, gX, fresh);
        mount3d();
        stageBox.replaceChildren(S.ch.el); tlsBox.replaceChildren(...tlists()); authWrap.replaceChildren(S.authBox);
        backBtn.hidden = !fresh; t = 0; paint();
        if (!reduced) start(false); else { t = cycle() - 0.01; paint(); }
      };
      freshBtn.addEventListener("click", async () => {
        freshBtn.disabled = true; freshNote.textContent = "Running the lab handshakes on 127.0.0.1…";
        try {
          const f = await ctx.api.post(`/api/workspaces/${ctx.ws}/move/fresh`, {}, { signal: ctx.signal, quiet: true });
          swap(f, f.gates || {}, true);
          freshNote.textContent = `Fresh lab run ${f.run_id} at ${f.ts}: ${f.sessions.length} handshakes, ${f.refused_attempts.length} refused. Logged in ${f.log}; not part of results.json, not signed.`;
          ctx.announce(freshNote.textContent);
        } catch (err) {
          if (err.code !== "aborted") freshNote.textContent = `Fresh handshake failed: ${err.message}`;
        } finally { freshBtn.disabled = !canRun; }
      }, { signal: ctx.signal });
      backBtn.addEventListener("click", () => { swap(mv, g, false); freshNote.textContent = "Showing the recorded run again."; }, { signal: ctx.signal });
      return h("div", { class: "mv" },
        h("div", { class: "mv-top" }, status, count, bar,
          h("ul", { class: "legend mv-legend", "aria-label": "Progress bar colours" }, [["pass", "green: verified in lab"], ["accent", "white: moved by the plan"], ["exposed", "red: still on old encryption"]].map(([c, x]) =>
            h("li", {}, h("span", { class: `lg-dot ${c}`, "aria-hidden": "true" }), x))),
          h("div", { class: "mv-controls" }, playBtn, stepBtn, h("label", { class: "mv-lab" }, "speed", speed),
            h("label", { class: "mv-lab week-scrub" }, "week", range, wk), bankSel ? h("label", { class: "mv-lab" }, "bank", bankSel) : null, motionBtn)),
        h("section", { class: "ch-stage", "aria-label": "Replay of recorded handshakes" }, h("div", { class: "mv-fresh" }, freshBtn, backBtn, freshNote), stage3d, stageBox,
          h("p", { class: "mv-how", text: "How to read this: each block is one recorded TLS message, as wide as its real size. Same client, two servers: red uses classical X25519, green uses hybrid X25519MLKEM768 (its key share is the dark inner block). The bottom lane is a client that offers only classical groups." })),
        tlsBox,
        h("section", { class: "mv-sec" }, h("h2", { class: "mv-h2", text: "Who the receiver is: server authentication" }), authWrap,
          h("p", { class: "mv-how", text: "How to read this: bar length is the recorded certificate plus signature size. Key exchange protects recorded traffic; the signature proves the server's identity and must be replaced before a quantum computer exists." })),
        h("section", { class: "mv-sec" }, h("h2", { class: "mv-h2", text: "This week's wave: gate results" }), mean, gatesBox),
        h("section", { class: "mv-sec" }, h("h2", { class: "mv-h2", text: bank ? `Systems: ${bank}` : "Systems" }),
          h("div", { class: "mg-lanes" }, LANES.map((l) => h("section", { class: `mg-lane ${l.tone}`, "aria-label": l.title },
            h("p", { class: "mg-lane-h" }, h("span", { class: `lg-dot ${l.tone}`, "aria-hidden": "true" }), l.title), h("p", { class: "mv-note", text: l.sub }), tileLanes[l.id])))),
        detailsList([
          { title: "How it works", summary: "Packets replay recorded transcripts; tiles follow the logged plan.", body: bullets([
            "Each packet is one message from openssl s_client -msg, captured from the lab services on 127.0.0.1; its width is the recorded byte length.",
            "The transcript files are used only when their SHA-256 matches the hash recorded in capture.json.",
            "A system sits in \"old\" until its planned week, moves during it, and shows its wave's lab gate result afterwards."]) },
          { title: "Why this method", summary: "The handshake is the evidence that post-quantum key exchange is really used.", body: bullets(["Configuration alone can claim post-quantum without using it; the recorded ServerHello key share shows what was negotiated."]) },
          { title: "Evidence & sources", summary: mv ? `capture run ${mv.run_id} · ${mv.openssl_version || ""}` : "not yet run", body: mv ? bullets([...mv.sessions, ...mv.refused_attempts].map((s) =>
            `${s.service_id} (${s.client_groups_offered}): ${s.negotiated_group || s.error} · ${s.transcript_file || "transcript not found"} · sha256 ${s.transcript_sha256.slice(0, 16)}… ${s.transcript_verified ? "matches capture.json" : "not verified"}`)) : h("p", { text: "not yet run" }) },
          { title: "Limits", summary: "Replay of recorded lab handshakes. Nothing here changes a real system.", body: bullets([
            "\"Verified in lab\" is the strongest state shown, and only for lab stand-ins.",
            "Real endpoints are only observed (one handshake each) and planned, never changed.",
            "HNDL-exposed is a statement about the key exchange used; no traffic was recorded or decrypted."]) }]),
        nextStep(ctx, "migration", { route: "review", text: "Next: review the steps" }));
    },
  });
  ctx.root.append(h("div", { class: "grid" }, h("div", { class: "span-12" },
    pageHead(ctx, { route: "migration", title: "Move", headline: "Same client, two servers: red packets can be recorded now and decrypted later; green packets use quantum-resistant key exchange." }), body, honesty())));
}
