// Top strip: wordmark, workspace switcher, route rail (keys 1–6), run button, user menu.
import { h } from "../dom.js";
import { RAIL } from "../routes.js";
import { href } from "../router.js";

export function strip({ onSignOut, onWorkspace, kiosk }) {
  const wsSelect = h("select", { "aria-label": "workspace" });
  const ws = h("label", { class: "ws-switch" }, h("span", { class: "ws-label", text: "Workspace" }), wsSelect);
  const rail = h("nav", { class: "rail", "aria-label": "Routes" });
  const user = h("div", { class: "user" });
  const el = h("header", { class: "strip" },
    h("a", { class: "wordmark", href: "/", "aria-label": "Q-Shield Atlas home" }, logo(), h("span", { text: "Q-Shield Atlas" })),
    ws, rail, h("div", { class: "strip-actions" }), user);
  wsSelect.addEventListener("change", () => onWorkspace(wsSelect.value));

  el.update = ({ me, workspaces, wsId, routeName }) => {
    const signedIn = !!me;
    ws.hidden = !signedIn || !workspaces;
    if (signedIn && workspaces) {
      wsSelect.replaceChildren(...workspaces.map((w) => h("option", { value: w.id, selected: w.id === wsId }, w.read_only ? `${w.name}` : w.name)));
    }
    rail.hidden = !signedIn;
    rail.replaceChildren(...RAIL.map((r) => h("a", { href: href(r.path, { ws: wsId }), "aria-current": r.name === routeName ? "page" : null,
      "aria-keyshortcuts": String(r.rail), title: `${r.title} (key ${r.rail})` }, h("kbd", { text: String(r.rail) }),
      h("span", { class: "full", text: r.label }), h("span", { class: "short", text: r.short }))));
    user.replaceChildren(...(signedIn
      ? [h("span", { class: "who" }, h("b", { text: me.username }), ` · ${me.role}`),
         me.role === "admin" ? h("a", { class: "btn quiet users-link", href: "/settings/users", text: "Users" }) : null,
         kiosk ? null : h("button", { class: "btn quiet", type: "button", onclick: onSignOut, text: "Sign out" })]
      : [h("a", { class: "btn", href: "/signin", text: "Sign in" })]));
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
