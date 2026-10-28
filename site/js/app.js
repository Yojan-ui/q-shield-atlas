// The Lattice: data loaded once (+ SSE pushes), scroll drives the camera; no request happens on scroll.
import { buildSite, NOT_YET_RUN } from "./data.js";

const $ = (id) => document.getElementById(id);
const params = new URLSearchParams(location.search);
const reduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches || params.has("still");
const sections = [...document.querySelectorAll(".chapter")];
const rail = [...document.querySelectorAll("#rail a")];

const srcText = (s) => (s ? [`run_id: ${s.run_id}`, `solver/backend: ${s.solver}`, `job_id: ${s.job_id}`, `timestamp: ${s.ts}`, s.note ? `note: ${s.note}` : ""].filter(Boolean).join("\n") : "");
function num(c, big = false) {
  const el = document.createElement(big ? "b" : "span");
  if (!c || c.kind !== "number") { el.className = "missing"; el.textContent = (c && c.text) || NOT_YET_RUN; return el; }
  el.className = "num"; el.textContent = c.text; el.tabIndex = 0; el.dataset.src = srcText(c.source);
  return el;
}
const frag = (...parts) => { const f = document.createDocumentFragment(); parts.forEach((p) => f.append(p)); return f; };

async function loadData() {
  if (window.__SITE_DATA__) return window.__SITE_DATA__; // static export (later stage)
  const get = async (p) => { const r = await fetch(p, { cache: "no-store" }); return r.ok ? r.json() : null; };
  const [results, ledger, handshakes] = await Promise.all([get("/api/results"), get("/api/ledger"), get("/api/handshakes")]);
  return { results, ledger, handshakes };
}

let model = null, scenario = null, world = null;
const state = { chapter: 0, p: 0, week: 0 };

// ---------- DOM per chapter ----------
function renderDial() {
  const dial = $("dial");
  const h = model.harvest;
  if (!h.available) { dial.replaceChildren(num(null)); return; }
  dial.replaceChildren(...h.scenarios.map((s) => {
    const b = document.createElement("button");
    b.setAttribute("role", "radio");
    b.setAttribute("aria-checked", String(s === scenario));
    b.textContent = `Q-day ${h.byScenario[s].year}`;
    b.addEventListener("click", () => { scenario = s; world && world.setScenario(s); renderAll(); });
    return b;
  }));
}
function renderHarvest() {
  const h = model.harvest;
  if (!h.available) { $("harvest-stat").replaceChildren(num(null)); return; }
  const v = h.byScenario[scenario];
  $("harvest-stat").replaceChildren(frag(num(v.exposure, true), ` exposure-years still readable if Q-day is ${v.year}, even under the optimised plan (risk-weighted `, num(v.weighted), ").")
  );
  $("sum-harvest").textContent = `Harvest: with Q-day ${v.year}, ${v.exposure.text || NOT_YET_RUN} exposure-years remain readable under the optimised plan.`;
}
function renderDetect() {
  const d = model.detect;
  if (!d.available) { $("detect-stat").replaceChildren(num(null)); $("detect-drift").textContent = ""; return; }
  $("detect-stat").replaceChildren(frag(num(d.filesScanned, true), " files scanned · ", num(d.vulnerable), " vulnerable findings · ",
    num(d.pqc), " PQC · ", num(d.assets), " assets to migrate"));
  $("detect-drift").textContent = d.drift.map((x) => `live probe: ${x.service} negotiates ${x.group} with a ${x.cert} cert → ${x.kinds.join(", ") || "no drift"}`).join(" · ");
  $("sum-detect").textContent = `Detect: ${d.filesScanned.text} files scanned, ${d.vulnerable.text} vulnerable findings, ${d.assets.text} assets to migrate.`;
}
function renderSchedule() {
  const s = model.schedule;
  if (!s.available) { $("schedule-week").replaceChildren(num(null)); $("schedule-avoided").textContent = ""; return; }
  const k = Math.min(Math.floor(state.week), s.weeks.length - 1);
  const wave = s.waves.find((w) => w.week === k);
  $("schedule-week").replaceChildren(frag(`week ${s.weeks[k]} · remaining exposure-years: QpiAI Opt `, num(s.series.optimized[scenario][k], true),
    " · FCFS ", num(s.series.fcfs[scenario][k]), " · greedy ", num(s.series.greedy[scenario][k]),
    wave ? ` · wave ${wave.week}: ${wave.status.replaceAll("_", " ")}` : ""));
  const a = s.avoided[scenario] || {};
  $("schedule-avoided").replaceChildren(frag(`avoided over the whole plan (${scenario}): `, num(a.fcfs, true), " vs FCFS · ", num(a.greedy), " vs greedy exposure-years"));
  $("sum-schedule").textContent = `Schedule, week ${k}: optimised ${s.series.optimized[scenario][k].text}, FCFS ${s.series.fcfs[scenario][k].text}, greedy ${s.series.greedy[scenario][k].text} exposure-years remaining.`;
}
function renderHandshake() {
  const h = model.handshake;
  if (!h.available) { $("services").replaceChildren(num(null)); return; }
  $("services").replaceChildren(...h.services.map((s) => {
    const li = document.createElement("li");
    li.dataset.src = srcText(s.source);
    li.tabIndex = 0;
    const g = (v) => Object.assign(document.createElement("span"), { className: v === "PASS" ? "pass" : "fail", textContent: v });
    li.append(Object.assign(document.createElement("span"), { className: "svc", textContent: s.id }), ` · ${s.strands.join(" + ")} `, g(s.kexGate),
      ` · auth ${s.auth} `, g(s.authGate), ` · classical-only client ${s.downgrade === "PASS" ? "refused" : "accepted"}`);
    if (s.hndl) li.append(Object.assign(document.createElement("div"), { className: "hndl", textContent: s.hndl }));
    return li;
  }));
  $("sum-handshake").textContent = "Handshake: " + h.services.map((s) => `${s.id} ${s.group} key exchange ${s.kexGate}, auth ${s.auth} ${s.authGate}`).join("; ");
}
function renderAll() {
  renderDial(); renderHarvest(); renderDetect(); renderSchedule(); renderHandshake();
  $("gen").textContent = `results ${model.generatedAt}`;
}

// ---------- scroll → state ----------
function readScroll() {
  const mid = innerHeight * 0.5;
  let ch = 0;
  sections.forEach((s, i) => { if (s.getBoundingClientRect().top <= mid) ch = i; });
  const r = sections[ch].getBoundingClientRect();
  const p = Math.min(1, Math.max(0, (mid - r.top) / r.height));
  const W = model && model.schedule.available ? model.schedule.weeks.length - 1 : 0;
  const week = ch < 2 ? 0 : ch > 2 ? W : Math.min(1, Math.max(0, (p - 0.08) / 0.7)) * W;
  const changedWeek = Math.floor(week) !== Math.floor(state.week);
  const changedCh = ch !== state.chapter;
  Object.assign(state, { chapter: ch, p, week });
  if (changedWeek && model) renderSchedule();
  if (changedCh) {
    rail.forEach((a, i) => a.classList.toggle("on", i === ch));
    if (reduced) { $("gl").style.opacity = "0"; requestAnimationFrame(() => { $("gl").style.opacity = "1"; }); }
  }
}
function goTo(i) {
  const s = sections[Math.max(0, Math.min(sections.length - 1, i))];
  window.scrollTo({ top: s.offsetTop - innerHeight * 0.5 + s.offsetHeight * 0.05 + 1, behavior: reduced ? "auto" : "smooth" });
}
addEventListener("keydown", (e) => {
  if (e.target.closest && e.target.closest("button, input, select")) return;
  if (["ArrowDown", "PageDown", " "].includes(e.key)) { e.preventDefault(); goTo(state.chapter + 1); }
  if (["ArrowUp", "PageUp"].includes(e.key)) { e.preventDefault(); goTo(state.chapter - 1); }
});
rail.forEach((a, i) => a.addEventListener("click", (e) => { e.preventDefault(); goTo(i); }));

// ---------- tooltips: DOM provenance + 3D hover ----------
const tip = $("tip");
let tipPinned = null;
function showTip(text, x, y) {
  tip.textContent = text; tip.hidden = false;
  tip.style.left = `${Math.min(x + 14, innerWidth - tip.offsetWidth - 8)}px`;
  tip.style.top = `${Math.min(y + 14, innerHeight - tip.offsetHeight - 8)}px`;
}
let mouse = { x: -1, y: -1 };
addEventListener("pointermove", (e) => {
  mouse = { x: e.clientX, y: e.clientY };
  world && world.setPointer((e.clientX / innerWidth) * 2 - 1, -(e.clientY / innerHeight) * 2 + 1);
  if (tipPinned) return;
  const t = e.target.closest && e.target.closest("[data-src]");
  if (t) showTip(t.dataset.src, e.clientX, e.clientY);
  else if (!tip.dataset.three) tip.hidden = true;
});
addEventListener("click", (e) => { const t = e.target.closest && e.target.closest("[data-src]"); tipPinned = t || null; if (t) showTip(t.dataset.src, e.clientX, e.clientY); else tip.hidden = true; });
addEventListener("focusin", (e) => { const t = e.target.closest && e.target.closest("[data-src]"); if (t) { const r = t.getBoundingClientRect(); showTip(t.dataset.src, r.left, r.bottom); } });

// ---------- main loop ----------
let raf = 0, frames = 0, fpsT = performance.now(), calls = 0;
const debug = params.has("debug");
function loop() {
  readScroll();
  calls = world.frame(state);
  if (state.chapter === 1 && !tipPinned) {
    const h = world.hover();
    if (h) {
      tip.dataset.three = "1";
      showTip(`${h.file}:${h.line.text}\n${h.family} · ${h.use} · ${h.rule}\n${h.snippet}\n${srcText(h.line.source)}`, mouse.x, mouse.y);
    } else if (tip.dataset.three) { delete tip.dataset.three; tip.hidden = true; }
  }
  if (debug) {
    frames++;
    const now = performance.now();
    if (now - fpsT >= 1000) { $("fps").textContent = `${Math.round((frames * 1000) / (now - fpsT))} fps · ${calls} draw calls`; frames = 0; fpsT = now; }
  }
  raf = requestAnimationFrame(loop);
}
document.addEventListener("visibilitychange", () => {
  if (document.hidden) cancelAnimationFrame(raf);
  else if (world) raf = requestAnimationFrame(loop);
});

function hasWebGL() {
  try { const c = document.createElement("canvas"); return !!(c.getContext("webgl2") || c.getContext("webgl")); } catch { return false; }
}

async function main() {
  if (!hasWebGL() || params.has("nowebgl")) { location.replace("/viz/index.html?from=site"); return; }
  const data = await loadData();
  model = buildSite(data.results, data.ledger, data.handshakes);
  scenario = (model.harvest.scenarios || [])[0];
  renderAll();
  try {
    const { createWorld } = await import("./scenes.js");
    world = createWorld($("gl"), { reduced });
    world.setModel(model, scenario);
  } catch (e) {
    console.error(e);
    location.replace("/viz/index.html?from=site&webgl=failed");
    return;
  }
  if (debug) $("fps").hidden = false;
  const at = params.get("at"); // e.g. ?at=schedule:0.6 (screenshots, deep links)
  if (at) {
    const [id, p] = at.split(":");
    const s = document.getElementById(id);
    if (s) window.scrollTo({ top: s.offsetTop - innerHeight * 0.5 + parseFloat(p || "0.05") * s.offsetHeight, behavior: "instant" });
  }
  readScroll();
  rail.forEach((a, i) => a.classList.toggle("on", i === state.chapter));
  raf = requestAnimationFrame(loop);
  if (!window.__SITE_DATA__ && window.EventSource && !params.has("nosse")) { // ?nosse: headless capture (open streams stall virtual time)
    const ev = new EventSource("/api/events");
    ev.addEventListener("update", async () => {
      const fresh = await loadData();
      model = buildSite(fresh.results, fresh.ledger, fresh.handshakes);
      world.setModel(model, scenario);
      renderAll();
    });
  }
  document.body.dataset.ready = "1";
}
main();
