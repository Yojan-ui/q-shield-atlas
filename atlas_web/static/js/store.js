// Client data cache: data loaded once per workspace; SSE invalidates exactly what changed and subscribers
// re-render (numbers roll). No refetch on route change. SSE reconnects with exponential backoff and, on
// reconnect, resyncs (invalidates every key for that workspace, since updates may have been missed).
export const KEYS = {
  results: (ws) => `/api/workspaces/${ws}/results`,
  ledger: (ws) => `/api/workspaces/${ws}/ledger`,
  scene: (ws) => `/api/workspaces/${ws}/scene`,
  manifests: (ws) => `/api/workspaces/${ws}/manifests`,
  assumptions: (ws) => `/api/workspaces/${ws}/assumptions`,
  calibration: (ws) => `/api/workspaces/${ws}/calibration`,
  runs: (ws) => `/api/workspaces/${ws}/runs`,
  workspace: (ws) => `/api/workspaces/${ws}`,
  bench: (ws) => `/api/workspaces/${ws}/bench`,
  reviews: (ws) => `/api/workspaces/${ws}/reviews`,
  move: (ws) => `/api/workspaces/${ws}/move`,
};
// which cached keys a file change invalidates
export const INVALIDATES = { results: ["results", "scene", "calibration", "workspace", "reviews", "move"], ledger: ["ledger", "results", "scene", "bench", "reviews"] };

export function backoffMs(attempt) { return Math.min(30000, 1000 * 2 ** Math.max(0, attempt)); }

export function createStore({ api, EventSourceImpl = null, setTimer = setTimeout, clearTimer = clearTimeout }) {
  const cache = new Map(); // "ws|key" -> Promise
  const subs = new Set();
  let es = null, esWs = null, attempt = 0, retryTimer = null, connected = false;

  const id = (ws, key) => `${ws}|${key}`;
  function get(ws, key, opts = {}) {
    const k = id(ws, key);
    if (!cache.has(k)) {
      const p = api.get(KEYS[key](ws), opts).catch((err) => { cache.delete(k); throw err; });
      cache.set(k, p);
    }
    return cache.get(k);
  }
  function peek(ws, key) { return cache.get(id(ws, key)); }
  function set(ws, key, value) { cache.set(id(ws, key), Promise.resolve(value)); notify(ws, [key]); }
  function invalidate(ws, keys) {
    for (const key of keys) cache.delete(id(ws, key));
    notify(ws, keys);
  }
  function notify(ws, keys) { for (const fn of subs) { try { fn({ ws, keys }); } catch (e) { setTimer(() => { throw e; }, 0); } } }
  function subscribe(fn) { subs.add(fn); return () => subs.delete(fn); }

  function connect(ws) {
    if (!EventSourceImpl || (esWs === ws && es)) return;
    disconnect();
    esWs = ws;
    open();
  }
  function open() {
    const ws = esWs;
    es = new EventSourceImpl(`/api/events?ws=${encodeURIComponent(ws)}`);
    es.addEventListener("hello", () => {
      const wasReconnect = attempt > 0 || connected;
      attempt = 0;
      if (wasReconnect) invalidate(ws, Object.keys(KEYS)); // resync after a gap
      connected = true;
    });
    es.addEventListener("update", (ev) => {
      let data = {};
      try { data = JSON.parse(ev.data); } catch { return; }
      const keys = [...new Set((data.changed || []).flatMap((c) => INVALIDATES[c] || []))];
      if (keys.length) invalidate(ws, keys);
    });
    es.onerror = () => {
      if (!es) return;
      es.close();
      es = null;
      const delay = backoffMs(attempt++);
      retryTimer = setTimer(() => { retryTimer = null; if (esWs === ws) open(); }, delay);
    };
  }
  function disconnect() {
    if (retryTimer) { clearTimer(retryTimer); retryTimer = null; }
    if (es) es.close();
    es = null; esWs = null; attempt = 0; connected = false;
  }
  function clearAll() { cache.clear(); }

  return { get, peek, set, invalidate, subscribe, connect, disconnect, clearAll, get connectedWs() { return esWs; } };
}
