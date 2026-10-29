// Top strip: wordmark, workspace switcher, Beginner/Expert toggle, user menu; the route rail is the left sidebar
// (pipeline order, step numbers, status ticks) on wide screens and a bar elsewhere.
import { h, icon } from "../dom.js";
import { FLOW } from "../flow.js";
import { sound } from "../sound.js";
import { backendBadge } from "./quantum.js";
import { RAIL } from "../routes.js";
import { href } from "../router.js";

export function strip({ api, store, onSignOut, onWorkspace, kiosk }) {
  const wsSelect = h("select", { "aria-label": "workspace" });
  const badge = h("span", { class: "ws-badge" });
  const ws = h("label", { class: "ws-switch" }, h("span", { class: "ws-label", text: "Workspace" }), wsSelect, badge);
  const rail = h("nav", { class: "rail", "aria-label": "Pipeline steps" });
  // Beginner hides the technical "details" sections on every page; Expert shows them. Remembered per browser.
  let mode = "beginner";
  try { mode = localStorage.getItem("atlas.mode") || "beginner"; } catch { /* default */ }
  const modeBtn = h("button", { class: "btn quiet mode-toggle", type: "button" });
  const setMode = (m) => {
    mode = m; document.documentElement.dataset.mode = m;
    modeBtn.textContent = m === "expert" ? "Expert view" : "Beginner view";
    modeBtn.setAttribute("aria-pressed", String(m === "expert"));
    modeBtn.title = m === "expert" ? "Showing technical details. Switch to the beginner view." : "Technical details hidden. Switch to the expert view.";
    try { localStorage.setItem("atlas.mode", m); } catch { /* not remembered */ }
  };
  modeBtn.addEventListener("click", () => setMode(mode === "expert" ? "beginner" : "expert"));
  setMode(mode);
  const user = h("div", { class: "user" });
  const snd = h("button", { class: "btn quiet sound-toggle", type: "button", "aria-pressed": String(sound.on), title: "Sound (off by default)" }, sound.on ? "Sound on" : "Sound off");
  snd.addEventListener("click", () => { const on = sound.toggle(); snd.setAttribute("aria-pressed", String(on)); snd.textContent = on ? "Sound on" : "Sound off"; if (on && location.pathname === "/") sound.hum(true); });
  const el = h("header", { class: "strip" },
    h("a", { class: "wordmark", href: "/", "aria-label": "Q-Shield Atlas home" }, logo(), h("span", { text: "Q-Shield Atlas" })),
    ws, rail, h("div", { class: "strip-actions" }, h("button", { class: "btn quiet", type: "button", title: "Presenter mode (P)", onclick: () => dispatchEvent(new Event("atlas:present")), text: "Present" }), modeBtn, snd), user);
  let qbadge = null;  // quantum backend in use, shown once signed in (the status route needs a session)
  wsSelect.addEventListener("change", () => onWorkspace(wsSelect.value));

  el.update = ({ me, workspaces, wsId, routeName }) => {
    const signedIn = !!me;
    ws.hidden = !signedIn || !workspaces;
    if (signedIn && workspaces) {
      wsSelect.replaceChildren(...workspaces.map((w) => h("option", { value: w.id, selected: w.id === wsId }, wsLine(w))));
      const cur = workspaces.find((w) => w.id === wsId);
      badge.replaceChildren(...(cur ? [h("span", { class: "chip neutral", text: cur.type || "" }),
        cur.ledger_verified === null || cur.ledger_verified === undefined ? null
          : h("span", { class: `chip ${cur.ledger_verified ? "pass" : "fail"}`, title: "ledger verification", text: cur.ledger_verified ? "✔ ledger" : "✖ ledger" })].filter(Boolean) : []));
    }
    rail.hidden = !signedIn || routeName === "landing";  // the landing story is full width
    if (signedIn && api && !qbadge) el.querySelector(".strip-actions").prepend(qbadge = backendBadge(api));
    if (qbadge) qbadge.hidden = !signedIn;
    const link = (r, done) => h("a", { href: href(r.path, { ws: wsId }), "aria-current": r.name === routeName ? "page" : null,
      "aria-keyshortcuts": r.rail <= 9 ? String(r.rail) : null, title: r.rail <= 9 ? `${r.title} (key ${r.rail})` : r.title, class: done ? "done" : null },
      h("span", { class: "r-num", text: r.stepText || (r.step ? String(r.step) : "") }),
      h("span", { class: "full", text: r.label }), h("span", { class: "short", text: r.short }),
      done ? h("span", { class: "r-tick", "aria-label": "done" }, icon("check")) : null);
    // the 7 pipeline steps, each number once (Inventory & drift is a sub-item of 1); steps 2 and 6 open their Ledger section
    const sec = new URLSearchParams(location.search || (location.hash.split("?")[1] || "")).get("section") || "2";
    const flowLinks = (done) => FLOW.flatMap((f, i) => {
      const cur = f.route === routeName && (!f.section || f.section === sec);
      const a = h("a", { href: href(`/w/:ws/${f.route}`, { ws: wsId }) + (f.section ? `?section=${f.section}` : ""), "aria-current": cur ? "page" : null, title: f.label, class: done[f.id] ? "done" : null },
        h("span", { class: "r-num", text: String(i + 1) }), h("span", { class: "full", text: f.label }), h("span", { class: "short", text: f.label.split(":")[0] }),
        done[f.id] ? h("span", { class: "r-tick", "aria-label": "done" }, icon("check")) : null);
      if (f.id !== "detect") return [a];
      const inv = RAIL.find((r) => r.name === "inventory");
      return [a, h("a", { href: href(inv.path, { ws: wsId }), class: `sub${done.inventory ? " done" : ""}`, "aria-current": routeName === "inventory" ? "page" : null, title: inv.title },
        h("span", { class: "r-num", text: "" }), h("span", { class: "full", text: inv.label }), h("span", { class: "short", text: inv.short }), done.inventory ? h("span", { class: "r-tick", "aria-label": "done" }, icon("check")) : null)];
    });
    const draw = (done = {}) => rail.replaceChildren(
      ...RAIL.filter((r) => r.group === "start").map((r) => link(r, false)),
      h("p", { class: "r-group", text: "Pipeline" }), ...flowLinks(done),
      h("p", { class: "r-group", text: "More" }), ...RAIL.filter((r) => r.group === "more").map((r) => link(r, false)));
    draw();
    if (signedIn && store && wsId) {  // status ticks: a step is done when its recorded output exists in results.json
      Promise.all([store.get(wsId, "results"), store.get(wsId, "reviews").catch(() => null)]).then(([res, rv]) => draw(stepsDone(res.results, rv))).catch(() => {});
    }
    user.replaceChildren(...(signedIn
      ? [h("span", { class: "who" }, h("b", { text: me.username }), ` · ${me.role}`),
         me.role === "admin" ? h("a", { class: "btn quiet users-link", href: "/settings/users", text: "Users" }) : null,
         (typeof kiosk === "function" ? kiosk() : kiosk) ? null : h("button", { class: "btn quiet", type: "button", onclick: onSignOut, text: "Sign out" })]
      : [h("a", { class: "btn", href: "/signin", text: "Sign in" })]).filter(Boolean));
  };
  return el;
}

export function logo() {
  const svg = h("svg", { viewBox: "0 0 20 20", fill: "none", stroke: "currentColor", "stroke-width": "1.4", "aria-hidden": "true" });
  svg.innerHTML = '<path d="M10 2 17 6v8l-7 4-7-4V6z"/><path d="M3 6l7 4 7-4M10 10v8"/><circle cx="10" cy="10" r="1.4" fill="currentColor" stroke="none"/>';
  return svg;
}

export function installRailKeys(navigate, getWs, signal) {
  addEventListener("keydown", (e) => {
    if (e.metaKey || e.ctrlKey || e.altKey || e.defaultPrevented) return;
    const t = e.target;
    if (t instanceof Element && t.closest("input, select, textarea, [contenteditable], dialog")) return;
    const r = RAIL.find((x) => String(x.rail) === e.key);
    const ws = getWs();
    if (r && ws) { e.preventDefault(); navigate(href(r.path, { ws })); }
  }, { signal });
}

// One line per workspace in the switcher: type badge, assets, ledger verified, last run (all from the API).
export function wsLine(w) {
  const ago = (ts) => { const m = Math.round((Date.now() / 1000 - ts) / 60); return m < 60 ? `${m} min ago` : m < 2880 ? `${Math.round(m / 60)} h ago` : `${Math.round(m / 1440)} d ago`; };
  return [w.name, w.type, w.assets === null || w.assets === undefined ? "not yet run" : `${w.assets} assets`,
    w.ledger_verified === null || w.ledger_verified === undefined ? null : w.ledger_verified ? "ledger ✔" : "ledger ✖",
    w.last_run ? `run ${ago(w.last_run.ts)} (${w.last_run.status})` : w.generated_at ? `snapshot ${w.generated_at.slice(0, 10)}` : null].filter(Boolean).join(" · ");
}

export function stepsDone(r, reviews) {
  if (!r) return {};
  const items = (reviews && reviews.items) || [];
  const signed = ((r.ledger && r.ledger.entries) || []).some((e) => e.type === "detect.run");
  return { proof_open: signed, proof_verified: !!(r.ledger_verification && r.ledger_verification.ok), gates: !!r.gates, waves: !!r.qaoa, detect: !!r.detect, inventory: !!(r.detect && r.detect.inventory), schedule: !!r.exposure, qaoa: !!r.qaoa,
    handshakes: !!r.gates, ledger: !!(r.ledger_verification && r.ledger_verification.ok),
    review: items.length > 0 && items.every((i) => i.status !== "pending") };
}
