// Data layer: fetch wrapper (timeout, GET retry, CSRF, error envelope), cache + SSE invalidation/backoff/resync, model cells.
import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { ApiError, createApi, readCookie } from "../static/js/api.js";
import { backoffMs, createStore, INVALIDATES } from "../static/js/store.js";
import { buildViewModel, numberCells, solverLabel, stationsModel, HNDL } from "../static/js/model.js";

const res = (status, body) => ({ ok: status < 400, status, text: async () => (body === undefined ? "" : JSON.stringify(body)) });

test("GET retries once on 5xx / network, then reports once", async () => {
  let calls = 0; const errors = [];
  const api = createApi({ fetchImpl: async () => { calls++; return calls === 1 ? res(503, { error: { code: "x", message: "busy" } }) : res(200, { ok: 1 }); }, sleep: async () => {} });
  assert.deepEqual(await api.get("/api/x"), { ok: 1 }); assert.equal(calls, 2);
  calls = 0;
  const api2 = createApi({ fetchImpl: async () => { calls++; throw new TypeError("net"); }, onError: (e) => errors.push(e.code), sleep: async () => {} });
  await assert.rejects(api2.get("/api/x"), (e) => e instanceof ApiError && e.code === "network");
  assert.equal(calls, 2); assert.deepEqual(errors, ["network"]);
});

test("POST never retries, sends CSRF from the cookie and JSON", async () => {
  let seen; let calls = 0;
  const api = createApi({ fetchImpl: async (p, o) => { calls++; seen = o; return res(500, { error: { code: "internal", message: "boom" } }); }, cookie: () => "a=1; atlas_csrf=tok123", sleep: async () => {} });
  await assert.rejects(api.post("/api/x", { a: 1 }), (e) => e.status === 500 && e.code === "internal");
  assert.equal(calls, 1); assert.equal(seen.headers["X-CSRF-Token"], "tok123"); assert.equal(seen.body, '{"a":1}');
  assert.equal(readCookie("x=1; atlas_csrf=a=b", "atlas_csrf"), "a=b");
});

test("4xx is not retried and carries code + fields; quiet suppresses the report", async () => {
  let calls = 0; const errors = [];
  const api = createApi({ fetchImpl: async () => { calls++; return res(422, { error: { code: "invalid_manifest", message: "bad", fields: { kind: "one of" } } }); }, onError: (e) => errors.push(e) });
  await assert.rejects(api.get("/api/x", { quiet: true }), (e) => e.fields.kind === "one of");
  assert.equal(calls, 1); assert.equal(errors.length, 0);
});

test("timeout -> ApiError timeout", async () => {
  const api = createApi({ fetchImpl: (p, o) => new Promise((_, rej) => o.signal.addEventListener("abort", () => rej(Object.assign(new Error("a"), { name: "AbortError" })))), timeoutMs: 10, sleep: async () => {} });
  await assert.rejects(api.get("/api/slow", { retry: 0 }), (e) => e.code === "timeout");
});

class FakeES {
  static all = [];
  constructor(url) { this.url = url; this.l = {}; FakeES.all.push(this); this.closed = false; }
  addEventListener(t, f) { (this.l[t] ||= []).push(f); }
  emit(t, data) { (this.l[t] || []).forEach((f) => f({ data: JSON.stringify(data) })); }
  close() { this.closed = true; }
}

test("cache: one fetch per key; SSE invalidates exactly the changed keys; no refetch otherwise", async () => {
  const hits = [];
  const api = { get: async (p) => { hits.push(p); return { p }; } };
  const timers = [];
  const store = createStore({ api, EventSourceImpl: FakeES, setTimer: (f, ms) => { timers.push([f, ms]); return timers.length; }, clearTimer: () => {} });
  await store.get("bank", "results"); await store.get("bank", "results"); await store.get("bank", "ledger");
  assert.deepEqual(hits, ["/api/workspaces/bank/results", "/api/workspaces/bank/ledger"]);
  const notes = []; store.subscribe((n) => notes.push(n));
  store.connect("bank");
  const es = FakeES.all.at(-1);
  assert.equal(es.url, "/api/events?ws=bank");
  es.emit("hello", {});
  es.emit("update", { workspace: "bank", changed: ["results"] });
  assert.deepEqual(notes.at(-1), { ws: "bank", keys: INVALIDATES.results });
  await store.get("bank", "results"); await store.get("bank", "ledger");
  assert.deepEqual(hits.slice(2), ["/api/workspaces/bank/results"]); // ledger still cached
  // error -> backoff reconnect -> hello -> resync of every key
  es.onerror();
  assert.ok(es.closed); assert.equal(timers.at(-1)[1], 1000);
  timers.at(-1)[0]();
  const es2 = FakeES.all.at(-1);
  assert.notEqual(es2, es);
  es2.emit("hello", {});
  assert.ok(notes.at(-1).keys.includes("ledger") && notes.at(-1).keys.includes("runs"));
  assert.deepEqual([0, 1, 2, 5, 10].map(backoffMs), [1000, 2000, 4000, 30000, 30000]);
});

test("failed fetches are not cached", async () => {
  let n = 0;
  const store = createStore({ api: { get: async () => { n++; if (n === 1) throw new Error("x"); return 1; } } });
  await assert.rejects(store.get("w", "results"));
  assert.equal(await store.get("w", "results"), 1);
});

const sample = JSON.parse(readFileSync(new URL("../../tests/fixtures/results_sample.json", import.meta.url), "utf8"));

test("view model: every number cell is a value present in results.json, with a source", () => {
  const m = buildViewModel(sample);
  const cells = numberCells(m);
  assert.ok(cells.length > 50);
  const values = new Set();
  const walk = (x) => { if (typeof x === "number") values.add(x); else if (x && typeof x === "object") Object.values(x).forEach(walk); };
  walk(sample);
  for (const c of cells) {
    assert.ok(c.source && c.source.run_id && c.source.solver && c.source.job_id, JSON.stringify(c));
    assert.ok(values.has(c.value), `value ${c.value} (${c.text}) not in results.json`);
  }
});

test("view model: missing data is 'not yet run', never 0; solver label from recorded fields", () => {
  const m = buildViewModel(null);
  assert.equal(numberCells(m).length, 0);
  assert.equal(m.detect.text, "not yet run");
  assert.equal(solverLabel(sample), "QpiAI Opt · local MILP · optimal · global optimum");
  assert.equal(HNDL, "HNDL-exposed: recorded traffic relies on classical key exchange");
  const st = stationsModel({ runs: [] });
  assert.equal(st.length, 11); assert.ok(st.every((s) => s.status === "idle" && s.duration.kind === "missing"));
});
