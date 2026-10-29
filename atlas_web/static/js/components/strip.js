// Top strip: wordmark, workspace switcher, route rail (keys 1–6), run button, user menu.
import { h } from "../dom.js";
import { sound } from "../sound.js";
import { backendBadge } from "./quantum.js";
import { RAIL } from "../routes.js";
import { href } from "../router.js";

export function strip({ api, onSignOut, onWorkspace, kiosk }) {
  const wsSelect = h("select", { "aria-label": "workspace" });
  const badge = h("span", { class: "ws-badge" });
  const ws = h("label", { class: "ws-switch" }, h("span", { class: "ws-label", text: "Workspace" }), wsSelect, badge);
  const rail = h("nav", { class: "rail", "aria-label": "Routes" });
  const user = h("div", { class: "user" });
  const snd = h("button", { class: "btn quiet sound-toggle", type: "button", "aria-pressed": String(sound.on), title: "Sound (off by default)" }, sound.on ? "Sound on" : "Sound off");
  snd.addEventListener("click", () => { const on = sound.toggle(); snd.setAttribute("aria-pressed", String(on)); snd.textContent = on ? "Sound on" : "Sound off"; if (on && location.pathname === "/") sound.hum(true); });
  const el = h("header", { class: "strip" },
    h("a", { class: "wordmark", href: "/", "aria-label": "Q-Shield Atlas home" }, logo(), h("span", { text: "Q-Shield Atlas" })),
    ws, rail, h("div", { class: "strip-actions" }, snd), user);
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
    rail.hidden = !signedIn;
    if (signedIn && api && !qbadge) el.querySelector(".strip-actions").prepend(qbadge = backendBadge(api));
    if (qbadge) qbadge.hidden = !signedIn;
    rail.replaceChildren(...RAIL.map((r) => h("a", { href: href(r.path, { ws: wsId }), "aria-current": r.name === routeName ? "page" : null,
      "aria-keyshortcuts": String(r.rail), title: `${r.title} (key ${r.rail})` }, h("kbd", { text: String(r.rail) }),
      h("span", { class: "full", text: r.label }), h("span", { class: "short", text: r.short }))));
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
