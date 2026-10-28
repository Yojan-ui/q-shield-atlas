// Pure router core (no DOM): path patterns, matching, guards. Tested under node (jstests/router.test.mjs).
export function compile(pattern) {
  const keys = [];
  if (pattern === "*") return { re: /^.*$/, keys, pattern };
  const src = pattern.split("/").map((seg) => {
    if (seg.startsWith(":")) { keys.push(seg.slice(1)); return "([^/]+)"; }
    return seg.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  }).join("/");
  return { re: new RegExp(`^${src}/?$`), keys, pattern };
}

export function createTable(routes) {
  return routes.map((r) => ({ ...r, ...compile(r.path) }));
}

const SAFE_PARAM = /^[A-Za-z0-9._~-]{1,64}$/;

export function match(table, pathname) {
  for (const r of table) {
    const m = r.re.exec(pathname);
    if (!m) continue;
    const params = {};
    let ok = true;
    r.keys.forEach((k, i) => {
      let v;
      try { v = decodeURIComponent(m[i + 1]); } catch { ok = false; return; }
      if (!SAFE_PARAM.test(v)) ok = false;
      params[k] = v;
    });
    if (!ok) continue;
    return { route: r, params };
  }
  return null;
}

export const RANK = { viewer: 0, operator: 1, admin: 2 };

// -> {action: "ok"} | {action: "redirect", to} | {action: "forbidden", need} | {action: "notfound"}
export function guard(route, user, location) {
  if (!route || route.name === "notfound") return { action: "notfound" };
  if (route.dev && !new URLSearchParams(location.search || "").has("dev")) return { action: "notfound" };
  if (route.guestOnly && user) return { action: "redirect", to: safeNext(new URLSearchParams(location.search || "").get("next")) || "/w/demo/pipeline" };
  if (route.auth && !user) {
    const next = `${location.pathname}${location.search || ""}`;
    return { action: "redirect", to: `/signin?next=${encodeURIComponent(next)}` };
  }
  if (route.role && (!user || RANK[user.role] < RANK[route.role])) return { action: "forbidden", need: route.role };
  return { action: "ok" };
}

// Only same-origin absolute paths are accepted as ?next= targets (no open redirect).
export function safeNext(next) {
  if (typeof next !== "string" || !next.startsWith("/") || next.startsWith("//") || next.startsWith("/\\")) return null;
  if (/^\/(api|assets|vendor|viz)\//.test(next)) return null;
  return next;
}

export function resolve(table, location, user) {
  const m = match(table, location.pathname);
  const notfound = table.find((r) => r.name === "notfound");
  if (!m) return { route: notfound, params: {}, decision: { action: "notfound" } };
  const decision = guard(m.route, user, location);
  if (decision.action === "notfound") return { route: notfound, params: {}, decision };
  return { route: m.route, params: m.params, decision };
}

export function href(pattern, params = {}, query = null) {
  const path = pattern.split("/").map((s) => (s.startsWith(":") ? encodeURIComponent(params[s.slice(1)]) : s)).join("/");
  const q = query ? new URLSearchParams(Object.entries(query).filter(([, v]) => v !== null && v !== undefined && v !== "")).toString() : "";
  return q ? `${path}?${q}` : path;
}

// Direction of a history move from the stored indices: forward, back, or replace.
export function direction(fromIdx, toIdx) {
  if (toIdx === undefined || fromIdx === undefined || toIdx === fromIdx) return "replace";
  return toIdx > fromIdx ? "forward" : "back";
}
