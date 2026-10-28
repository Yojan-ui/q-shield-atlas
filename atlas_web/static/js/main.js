// Boot: one shell, one router, one data store, one world layer. Views mount into #view and clean up on leave.
import { createApi, ApiError } from "./api.js";
import { installTooltip } from "./components/tooltip.js";
import { installToasts, toast } from "./components/toast.js";
import { installRailKeys, strip as makeStrip } from "./components/strip.js";
import { h } from "./dom.js";
import { ROUTES } from "./routes.js";
import { createTable, direction, resolve, safeNext } from "./router.js";
import { createStore } from "./store.js";
import { createWorld } from "./world.js";

const api = createApi({
  fetchImpl: (...a) => fetch(...a),
  cookie: () => document.cookie,
  onError: (err) => { if (![401, 403, 404, 409, 422].includes(err.status)) toast(err.message, { tone: "error", detail: err.code }); },
});
const store = createStore({ api, EventSourceImpl: typeof EventSource === "function" ? EventSource : null });
const table = createTable(ROUTES);
const app = { me: null, kiosk: false, demo: false, workspaces: null, ws: "demo", view: null, ctl: null, idx: 0, seq: 0 };

const world = createWorld(document.getElementById("world"));
const view = document.getElementById("view");
const live = document.getElementById("live");
const top = makeStrip({ onSignOut: signOut, onWorkspace: (id) => switchWorkspace(id), kiosk: false });
document.getElementById("strip-slot").replaceWith(top);
installTooltip();
installToasts();

function isInternal(a) {
  return a && a.origin === location.origin && !a.hasAttribute("download") && (!a.target || a.target === "_self")
    && !a.getAttribute("href").startsWith("/api/") && !a.pathname.startsWith("/assets/") && a.dataset.external === undefined;
}

export function navigate(to, { replace = false } = {}) {
  const url = new URL(to, location.origin);
  if (url.origin !== location.origin) { location.assign(url); return; }
  if (replace) history.replaceState({ idx: app.idx }, "", url.pathname + url.search + url.hash);
  else history.pushState({ idx: ++app.idx }, "", url.pathname + url.search + url.hash);
  render(replace ? "replace" : "forward");
}

export function setQuery(patch) {
  const q = new URLSearchParams(location.search);
  for (const [k, v] of Object.entries(patch)) { if (v === null || v === undefined || v === "") q.delete(k); else q.set(k, String(v)); }
  const qs = q.toString();
  history.replaceState({ idx: app.idx }, "", location.pathname + (qs ? `?${qs}` : ""));
}

document.addEventListener("click", (e) => {
  if (e.defaultPrevented || e.button !== 0 || e.metaKey || e.ctrlKey || e.shiftKey || e.altKey) return;
  const a = e.target instanceof Element ? e.target.closest("a[href]") : null;
  if (!isInternal(a)) return;
  e.preventDefault();
  if (a.pathname + a.search === location.pathname + location.search) return;
  navigate(a.pathname + a.search + a.hash);
});
addEventListener("popstate", (e) => {
  const to = e.state && typeof e.state.idx === "number" ? e.state.idx : 0;
  const dir = direction(app.idx, to);
  app.idx = to;
  render(dir);
});

async function loadWorkspaces() {
  if (!app.me) { app.workspaces = null; return; }
  try { app.workspaces = (await api.get("/api/workspaces")).workspaces; } catch { app.workspaces = [{ id: "demo", name: "Demo snapshot (DEMO.md)", read_only: true }]; }
}

function switchWorkspace(id) {
  const m = location.pathname.match(/^\/w\/[^/]+\/([^/]+)/);
  const sub = m ? (m[1] === "asset" ? "detect" : m[1]) : "pipeline";
  navigate(`/w/${encodeURIComponent(id)}/${sub}${m && m[1] !== "asset" ? location.search : ""}`);
}

async function signOut() {
  try { await api.post("/api/auth/logout", {}); } catch { /* the session is gone either way */ }
  app.me = null; app.workspaces = null;
  store.disconnect(); store.clearAll();
  navigate("/", { replace: true });
  toast("Signed out", { tone: "success" });
}

export async function signedIn(me, next) {
  app.me = me;
  await loadWorkspaces();
  navigate(safeNext(next) || "/w/demo/pipeline", { replace: true });
}

function announce(text) { live.textContent = ""; requestAnimationFrame(() => { live.textContent = text; }); }

async function render(dir = "replace") {
  const seq = ++app.seq;
  const loc = { pathname: location.pathname, search: location.search };
  let { route, params, decision } = resolve(table, loc, app.me);
  if (decision.action === "redirect") { history.replaceState({ idx: app.idx }, "", decision.to); return render(dir); }
  const forbidden = decision.action === "forbidden";
  const viewName = forbidden ? "forbidden" : route.view;
  if (params.ws) app.ws = params.ws;
  const wsInfo = app.workspaces && app.workspaces.find((w) => w.id === app.ws);
  top.update({ me: app.me, workspaces: app.workspaces, wsId: app.ws, routeName: route.name, readOnly: wsInfo ? wsInfo.read_only : true });
  if (app.me && params.ws) store.connect(params.ws);

  if (app.ctl) app.ctl.abort();
  if (app.view && app.view.unmount) { try { app.view.unmount(); } catch (e) { setTimeout(() => { throw e; }, 0); } }
  const ctl = new AbortController();
  app.ctl = ctl;
  world.go(forbidden ? "void" : route.camera, { direction: dir });

  let mod;
  try { mod = await import(`./views/${viewName}.js`); }
  catch (err) { mod = await import("./views/notfound.js"); }
  if (seq !== app.seq) return;
  const root = h("div", { class: "view" });
  view.replaceChildren(root);
  const title = forbidden ? "Not allowed" : route.title;
  document.title = `${title}${params.ws ? ` · ${params.ws}` : ""} · Q-Shield Atlas`;
  const ctx = { root, params, query: new URLSearchParams(location.search), me: app.me, kiosk: app.kiosk, demo: app.demo, api, store, world,
    navigate, setQuery, signal: ctl.signal, ws: params.ws || app.ws, wsInfo, workspaces: app.workspaces, announce, need: decision.need, signedIn,
    refreshWorkspaces: async () => { await loadWorkspaces(); top.update({ me: app.me, workspaces: app.workspaces, wsId: app.ws, routeName: route.name, readOnly: wsInfo ? wsInfo.read_only : true }); } };
  try {
    app.view = (await mod.mount(ctx)) || null;
  } catch (err) {
    const { errorState } = await import("./components/states.js");
    root.replaceChildren(errorState({ error: err, onRetry: () => render("replace") }));
  }
  if (seq !== app.seq) return;
  const heading = root.querySelector("h1");
  if (heading) { heading.tabIndex = -1; heading.focus({ preventScroll: true }); }
  scrollTo(0, 0);
  document.body.dataset.route = forbidden ? "forbidden" : route.name;
}

async function boot() {
  history.replaceState({ idx: 0 }, "", location.pathname + location.search + location.hash);
  try {
    const me = await api.get("/api/me", { quiet: true });
    app.me = me.user; app.kiosk = me.kiosk; app.demo = me.demo;
    top.update({ me: app.me, workspaces: null, wsId: app.ws, routeName: "", readOnly: true });
  } catch (err) {
    toast("Cannot reach the Atlas server", { tone: "error", detail: err instanceof ApiError ? err.code : "" });
  }
  if (app.kiosk) top.querySelectorAll(".user button").forEach((b) => b.remove());
  await loadWorkspaces();
  installRailKeys((to) => navigate(to), () => (app.me ? app.ws : null));
  await render("replace");
  document.body.dataset.ready = "1";
  document.body.dataset.readyAt = String(Math.round(performance.now()));
}

// Unhandled rejections are shown to the user and recorded for tools/route_check.py (window.__atlasErrors).
window.__atlasErrors = window.__atlasErrors || [];
addEventListener("unhandledrejection", (e) => {
  e.preventDefault();
  const msg = String((e.reason && e.reason.message) || e.reason);
  window.__atlasErrors.push(`unhandledrejection: ${msg}`);
  toast("Something went wrong", { tone: "error", detail: msg });
});
boot();
