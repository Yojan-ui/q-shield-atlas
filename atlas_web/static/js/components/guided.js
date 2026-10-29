// Guided run (Pipeline page, non-demo workspaces): a full-width 3D stage, a terminal log on the right and a stepper of
// the seven steps along the bottom (display order from flow.js). Live: each step lights only from its own SSE events
// (step_start / step_end / line) and the log streams them; nothing is drawn that the run has not produced yet.
// Replay: once results.json holds a run, each step plays its scene from that run's real data, labelled
// "Replay of run <run_id>", then holds a one-line headline with real numbers. Missing data reads "not yet run".
// Controls: Back / Next / Autoplay (3 s per step) / Replay step; keys ← → and Space. Reduced motion: no autoplay
// motion beyond the engine's crossfade; ?no3d / no WebGL: headline, stepper and log only.
import { h, icon } from "../dom.js";
import { FLOW } from "../flow.js";
import { STAGE_OF, STEPS } from "../stages.js";
import { mountScene, stage } from "../views/common.js";
import { buildPillars } from "../scenes/pillars.js";
import { buildGraph, graphModel, layout as graphLayout, VULN } from "../scenes/graph.js";
import { buildLedger } from "../scenes/ledger.js";
import { buildLanes3d } from "../scenes/lanes3d.js";
import { pickLanes } from "./channel.js";
import { reviewItems } from "../views/review.js";
import { flowFacts } from "./overview.js";

const AUTO_MS = 3000;
const n0 = (x) => Number(x).toLocaleString("en-US");

// step id -> { headline, build(env) | null } from real data only (d = {results, ledger, move, inventory, reviews})
export function stepScene(id, d, { labelsEl, stageEl, reduced }) {
  if (id === "proof_open" || id === "proof_verified") id = "ledger";  // both proof steps show the Proof Chain
  const r = d.results, nyr = { headline: "not yet run", build: null };
  const P = (items, opts = {}) => (env) => buildPillars(env, items, { labelsEl, stageEl, reduced, ...opts });
  if (id === "detect") {
    if (!r || !r.detect) return nyr;
    const byFile = new Map();
    for (const f of r.detect.findings || []) { const x = byFile.get(f.file) || { n: 0, vuln: false, pqc: false }; x.n++; x.vuln ||= VULN.has(f.family); x.pqc ||= f.family === "PQC"; byFile.set(f.file, x); }
    const files = [...byFile].sort((a, b) => b[1].n - a[1].n).slice(0, 24), max = Math.max(1, ...files.map(([, x]) => x.n));
    const s = r.detect.summary;
    return { headline: `${n0(s.vulnerable_findings)} RSA / ECC / DH findings and ${n0(s.pqc_findings)} PQC in ${n0(r.detect.files_scanned)} files scanned`,
      build: files.length ? P(files.map(([f, x], i) => ({ id: f, label: i < 6 ? `${f.split("/").slice(-2).join("/")}\n${x.n}` : String(x.n), h: x.n / max, state: x.vuln ? "fail" : x.pqc ? "pqc" : "idle" })), { reveal: true }) : null };
  }
  if (id === "inventory") {
    if (!r || !r.detect) return nyr;
    const G = graphModel(r, (d.move && d.move.observed) || {}, d.inventory && d.inventory.available ? d.inventory.inventory : null);
    const drift = G.nodes.filter((x) => x.drift).length;
    return { headline: `${G.nodes.filter((x) => x.inPlan).length} systems to migrate · ${G.edges.length} dependencies · ${drift} drift ${drift === 1 ? "case" : "cases"}`,
      build: G.nodes.length ? (env) => buildGraph(env, G, graphLayout(G.nodes, G.edges), { reduced, labelsEl, stageEl }) : null };
  }
  if (id === "ledger") {
    const L = d.ledger;
    if (!L || !L.available) return nyr;
    const v = L.live_verification || {};
    return { headline: `${n0(L.entry_count)} records signed with ML-DSA-65, hash-chained · chain ${v.ok === true ? "verified" : v.ok === false ? `fails at #${(v.first_failure || {}).index}` : "not verified"}`,
      build: L.entries && L.entries.length ? buildLedger(L, { stageEl, onPick: null }) : null };
  }
  if (id === "schedule") {
    if (!r || !r.exposure) return nyr;
    const cap = (r.assumptions && r.assumptions.capacity_days_per_week) || Math.max(1, ...r.waves.map((w) => w.effort_days || 0));
    const av = (r.avoided && r.avoided.vs_fcfs || [])[0];
    return { headline: `${r.assets.length} systems in ${r.waves.length} weekly waves, ${r.exposure.makespan_weeks} weeks${av ? ` · ${av.exposure_years_avoided.toFixed(3)} exposure-years avoided vs FCFS (${av.scenario})` : ""}`,
      build: P(r.waves.map((w) => ({ id: `w${w.week}`, label: `week ${w.week}\n${w.assets.length} systems`, h: (w.effort_days || 0) / cap, state: "ok" })), { reveal: true }) };
  }
  if (id === "waves") {
    const q = r && r.qaoa;
    if (!q || !q.runs) return nyr;
    const runs = q.runs.filter((x) => (x.source === "local" || x.source === "random") && x.metrics);
    const best = runs.filter((x) => x.source === "local").sort((a, b) => b.p - a.p)[0];
    return { headline: `QAOA (simulator) vs the exact answer [${(q.exact.assets || []).join(", ")}]: P(optimal set) ${best ? best.metrics.p_optimal_assets.toFixed(3) : "not run"} at p = ${best ? best.p : "–"} · no quantum advantage claimed`,
      build: runs.length ? P(runs.map((x) => ({ id: `${x.source}${x.p}`, label: `${x.source === "random" ? "random" : `QAOA p=${x.p}`}\nP(opt) ${x.metrics.p_optimal_assets.toFixed(3)}`, h: x.metrics.p_optimal_assets,
        state: x.metrics.approximation_ratio === 1 ? "ok" : "idle" }))) : null };
  }
  if (id === "gates") {
    const mv = d.move && d.move.available ? d.move : null;
    if (!mv || !r) return nyr;
    const L = pickLanes(mv, r.gates || {});
    const lanes = [{ title: `Before: ${L.before ? L.before.negotiated_group : "not run"} (HNDL-exposed)`, tone: "exp", session: L.before },
      { title: `After: ${L.after ? L.after.negotiated_group : "not run"}`, tone: "pqc", session: L.after },
      { title: `Downgrade: ${L.downgrade.state === "refused" ? "refused" : L.downgrade.text}`, tone: "neutral", session: L.downgrade.session || null }];
    const g = r.gates || {}, res = (list) => (list || []).map((x) => `${x.service_id} ${x.result}`).join(", ");
    return { headline: `pq_handshake: ${res(g.pq_handshake) || "not run"} · downgrade: ${res(g.downgrade) || "not run"}`, lanes, chips: g,
      build: (env) => buildLanes3d(env, lanes, { labelsEl, stageEl, autoplay: true, reduced }) };
  }
  if (id === "review") {
    const R = d.reviews;
    if (!R || !R.items || !R.items.length) return nyr;
    const ver = R.items.filter((i) => i.signature === "verified").length;
    return { headline: `${R.items.length} results to review · ${ver} of ${R.items.length} signatures verified in the Proof Chain`, build: P(reviewItems(R.items)) };
  }
  return nyr;
}

// the run that produced a step's recorded data (results.json), so a replay names its real source
export function stepRunId(id, d) {
  if (id === "proof_open" || id === "proof_verified") id = "ledger";
  const r = d.results || {};
  return { detect: r.detect && r.detect.run_id, inventory: r.detect && r.detect.run_id, schedule: r.solver_runs && r.solver_runs[0] && r.solver_runs[0].run_id,
    waves: r.qaoa && r.qaoa.run_id, gates: r.gates && r.gates.run_id, ledger: d.ledger && d.ledger.root && `ledger root ${d.ledger.root.slice(0, 12)}`,
    review: d.reviews && d.reviews.items && d.reviews.items[0] && d.reviews.items[0].run_id }[id] || null;
}

// live status per display step, from the run's own SSE step events only
// (done only when every one of its own steps reported ok; some done, rest not reached yet = "partial")
export function liveStates(stepStatus) {
  return FLOW.map((f) => {
    const own = STEPS.filter((s) => f.stages.includes(STAGE_OF[s].id)), st = own.map((s) => stepStatus[s]).filter(Boolean);
    return !st.length ? "pending" : st.includes("fail") ? "fail" : st.includes("running") ? "running" : st.length === own.length ? "ok" : "partial";
  });
}

export function guidedRun(ctx, { canRun = true } = {}) {
  const labelsEl = h("div", { class: "gr-labels", "aria-hidden": "true" });
  const stageEl = stage(ctx, { label: "Guided run: the current pipeline step in 3D", fallback: h("span") });
  stageEl.classList.add("gd-stage");
  stageEl.append(labelsEl);
  const mode = h("p", { class: "gd-mode mono" }), headline = h("p", { class: "gd-head", "aria-live": "polite" }), chips = h("div", { class: "gd-chips" });
  const logEl = h("ol", { class: "gd-log", "aria-label": "run log" });
  const stepper = h("ol", { class: "gd-steps" }, FLOW.map((f, i) => h("li", { "data-i": String(i) }, h("button", { type: "button", class: "gd-step", onclick: () => go(i) }, h("span", { class: "num", text: String(i + 1) }), f.label))));
  const back = h("button", { class: "btn", type: "button", onclick: () => go(cur - 1) }, icon("rewind"), "Back");
  const next = h("button", { class: "btn", type: "button", onclick: () => go(cur + 1) }, "Next", icon("arrow"));
  const auto = h("button", { class: "btn", type: "button", "aria-pressed": "false", onclick: () => setAuto(!autoOn) });
  const again = h("button", { class: "btn", type: "button", onclick: () => go(cur, true) }, icon("spin"), "Replay step");
  let toggled = () => {};
  const close = h("button", { class: "btn quiet", type: "button", onclick: () => { stop(); root.hidden = true; ctx.world.mount("guided", null); toggled(false); } }, "Close");
  const open = () => { if (root.hidden) { root.hidden = false; toggled(true); } ctx.world.frameStage(stageEl); ctx.stageEl = stageEl; };
  const root = h("section", { class: "gd", hidden: true, "aria-label": "Guided run" },
    h("div", { class: "gd-top" }, mode, close),
    h("div", { class: "gd-body" }, h("div", { class: "gd-view" }, stageEl, headline, chips), h("div", { class: "gd-side" }, h("p", { class: "gd-k", text: "run log" }), logEl)),
    stepper, h("div", { class: "gd-ctl" }, back, next, auto, again, h("span", { class: "mv-note", text: "keys: ← → step · Space autoplay" })));
  let cur = 0, autoOn = false, timer = 0, data = {}, live = null, runId = null, stepStatus = {};
  const reduced = () => ctx.world.reduced;
  const log = (text, tone = "") => { logEl.append(h("li", { class: tone, text })); while (logEl.children.length > 400) logEl.firstChild.remove(); logEl.scrollTop = logEl.scrollHeight; };
  const paintSteps = () => {
    const st = live ? liveStates(stepStatus) : FLOW.map(() => null);
    [...stepper.children].forEach((li, i) => { li.dataset.state = st[i] || ""; li.classList.toggle("on", i === cur); });
    back.disabled = cur <= 0; next.disabled = cur >= FLOW.length - 1;
    auto.replaceChildren(icon(autoOn ? "dash" : "play"), autoOn ? "Pause autoplay" : "Autoplay");
    auto.setAttribute("aria-pressed", String(autoOn));
  };
  const show = () => {
    const f = FLOW[cur];
    chips.replaceChildren();
    if (live) {  // live: only what this run's own events have said about this step
      const st = liveStates(stepStatus)[cur];
      mode.textContent = `Live run ${runId} · step ${cur + 1} of ${FLOW.length}: ${f.label}`;
      headline.textContent = st === "pending" ? `${f.label}: waiting for the run to reach this step` : st === "partial" ? `${f.label}: part done; its remaining steps run later in the backend order` : st === "running" ? `${f.label}: running (live events in the log)` : st === "fail" ? `${f.label}: failed (see the log)` : `${f.label}: done in this run; its scene plays when the run's results are assembled`;
      mountScene(ctx, "guided", { available: true }, (env) => buildPillars(env, FLOW.map((x, i) => ({ id: x.id, label: `${i + 1} ${x.label}`, h: 0.55, state: { ok: "ok", fail: "fail", running: "running" }[liveStates(stepStatus)[i]] || "idle" })), { labelsEl, stageEl, reduced: reduced() })).catch(() => {});
      paintSteps();
      return;
    }
    const s = stepScene(f.id, data, { labelsEl, stageEl, reduced: reduced() });
    const src = runId || stepRunId(f.id, data);
    mode.textContent = data.results && src ? `Replay of run ${src} · step ${cur + 1} of ${FLOW.length}: ${f.label}` : `Step ${cur + 1} of ${FLOW.length}: ${f.label} · not yet run`;
    headline.textContent = s.headline;
    if (s.chips) for (const [k, list] of Object.entries({ pq_handshake: s.chips.pq_handshake, downgrade: s.chips.downgrade, pq_auth: s.chips.pq_auth }))
      for (const x of list || []) chips.append(h("span", { class: `chip ${x.result === "PASS" ? "pass" : "fail"}`, text: `${k} · ${x.service_id}: ${x.result}` }));
    if (s.build) mountScene(ctx, "guided", { available: true }, s.build).catch(() => {});
    else ctx.world.mount("guided", null);
    paintSteps();
  };
  const go = (i) => { cur = Math.max(0, Math.min(FLOW.length - 1, i)); show(); if (autoOn) arm(); };
  const arm = () => { clearTimeout(timer); timer = setTimeout(() => { if (cur >= FLOW.length - 1) return setAuto(false); go(cur + 1); }, AUTO_MS); };
  const setAuto = (on) => { autoOn = on; clearTimeout(timer); if (on) arm(); paintSteps(); };
  const stop = () => { clearTimeout(timer); autoOn = false; };
  const load = async () => {
    const get = (k) => ctx.store.get(ctx.ws, k, { signal: ctx.signal }).catch(() => null);
    const [res, ledger, move, inventory, reviews, runs] = await Promise.all(["results", "ledger", "move", "inventory", "reviews", canRun ? "runs" : null].map((k) => (k ? get(k) : null)));
    data = { results: res && res.results, ledger, move, inventory, reviews };
    const last = runs && runs.runs && runs.runs[0];
    runId = last && last.status === "PASS" ? last.id : null;  // a failed run did not assemble results.json: name each step's own recorded run instead
    return last;
  };
  addEventListener("keydown", (e) => {
    if (root.hidden || (e.target instanceof Element && e.target.closest("input, textarea, select, dialog"))) return;
    if (e.key === "ArrowRight") { e.preventDefault(); go(cur + 1); }
    else if (e.key === "ArrowLeft") { e.preventDefault(); go(cur - 1); }
    else if (e.key === " " && !(e.target instanceof HTMLButtonElement)) { e.preventDefault(); setAuto(!autoOn); }
  }, { signal: ctx.signal });
  ctx.signal.addEventListener("abort", stop, { once: true });
  return {
    el: root,
    // replay the latest recorded run from results.json (no re-run)
    onToggle(fn) { toggled = fn; },
    async replay() {
      open(); live = null; logEl.replaceChildren();
      const last = await load();
      if (last && last.detail && last.detail.summary) for (const s of last.detail.summary) log(`${s.exit_code === 0 ? "✓" : "✗"} ${s.step} · exit ${s.exit_code} · ${s.duration_s} s`, s.exit_code === 0 ? "ok" : "bad");
      else log(data.results ? "recorded results (no run log in this workspace)" : "not yet run");
      cur = 0; show(); root.scrollIntoView({ block: "start" });
    },
    // a live run: started by the page; events forwarded from its EventSource
    start(id) { open(); live = true; runId = id; stepStatus = {}; logEl.replaceChildren(); log(`run ${id} started`); cur = 0; show(); root.scrollIntoView({ block: "start" }); },
    stepStart(step) {
      stepStatus[step] = "running";
      const i = FLOW.findIndex((f) => STAGE_OF[step] && f.stages.includes(STAGE_OF[step].id));
      if (i >= 0) cur = i;  // the camera follows the step the backend is actually running
      log(`▶ ${step}`); show();
    },
    stepEnd(step, code, dur) { stepStatus[step] = code === 0 ? "ok" : "fail"; log(`${code === 0 ? "✓" : "✗"} ${step} · exit ${code} · ${dur} s`, code === 0 ? "ok" : "bad"); show(); },
    line(text) { log(text); },
    async end(status) { log(`run ${runId} ${status}${status === "PASS" ? "" : ": the replay below shows the previously recorded results"}`, status === "PASS" ? "ok" : "bad"); live = null; await load(); cur = 0; show(); if (!reduced()) setAuto(true); },
  };
}
