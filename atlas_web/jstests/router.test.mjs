import test from "node:test";
import assert from "node:assert/strict";
import { compile, createTable, direction, guard, href, match, resolve, safeNext } from "../static/js/router.js";
import { ROUTES, RAIL } from "../static/js/routes.js";

const T = createTable(ROUTES);
const loc = (pathname, search = "") => ({ pathname, search });
const admin = { username: "a", role: "admin" }, viewer = { username: "v", role: "viewer" };

test("compile + match with params", () => {
  const c = compile("/w/:ws/asset/:assetId");
  assert.deepEqual(c.keys, ["ws", "assetId"]);
  const m = match(T, "/w/bank/asset/web-gw");
  assert.equal(m.route.name, "asset");
  assert.deepEqual(m.params, { ws: "bank", assetId: "web-gw" });
  assert.equal(match(T, "/w/bank/pipeline/").route.name, "pipeline"); // trailing slash
  assert.equal(match(T, "/").route.name, "landing");
});

test("every brief route resolves", () => {
  for (const [p, name] of [["/", "landing"], ["/signin", "signin"], ["/w/demo/pipeline", "pipeline"], ["/w/demo/detect", "detect"],
    ["/w/demo/schedule", "schedule"], ["/w/demo/handshakes", "handshakes"], ["/w/demo/ledger", "ledger"], ["/w/demo/qaoa", "qaoa"],
    ["/w/demo/asset/x", "asset"], ["/settings/users", "users"]]) assert.equal(match(T, p).route.name, name, p);
});

test("unknown and unsafe paths fall to 404", () => {
  for (const p of ["/nope", "/w/demo", "/w/demo/unknown", "/w/de%2Fmo/pipeline", "/w/%3Cscript%3E/detect", "/w/%E0%A4%A/detect"]) {
    assert.equal(resolve(T, loc(p), admin).route.name, "notfound", p);
  }
});

test("guards: unauthenticated -> /signin?next=", () => {
  const r = resolve(T, loc("/w/bank/schedule", "?scenario=Z2032&week=7"), null);
  assert.equal(r.decision.action, "redirect");
  assert.equal(r.decision.to, "/signin?next=%2Fw%2Fbank%2Fschedule%3Fscenario%3DZ2032%26week%3D7");
  assert.equal(resolve(T, loc("/"), null).decision.action, "ok"); // landing is public
  assert.equal(resolve(T, loc("/signin"), null).decision.action, "ok");
});

test("guards: role-gated -> forbidden, signed-in on /signin -> next", () => {
  assert.deepEqual(resolve(T, loc("/settings/users"), viewer).decision, { action: "forbidden", need: "admin" });
  assert.equal(resolve(T, loc("/settings/users"), admin).decision.action, "ok");
  assert.deepEqual(guard(T.find((r) => r.name === "signin"), viewer, loc("/signin", "?next=/w/bank/ledger")), { action: "redirect", to: "/w/bank/ledger" });
  assert.deepEqual(guard(T.find((r) => r.name === "signin"), viewer, loc("/signin", "?next=//evil.example")), { action: "redirect", to: "/w/demo/pipeline" });
});

test("styleguide only with ?dev", () => {
  assert.equal(resolve(T, loc("/styleguide"), null).route.name, "notfound");
  assert.equal(resolve(T, loc("/styleguide", "?dev"), null).route.name, "styleguide");
});

test("safeNext blocks open redirects", () => {
  for (const bad of ["//evil.example", "https://evil.example", "/\\evil", "javascript:alert(1)", "/api/me", null, 3]) assert.equal(safeNext(bad), null, String(bad));
  assert.equal(safeNext("/w/bank/ledger?x=1"), "/w/bank/ledger?x=1");
});

test("href, direction, rail", () => {
  assert.equal(href("/w/:ws/asset/:assetId", { ws: "b", assetId: "a b" }, { scenario: "Z2032", week: 7, p: null }), "/w/b/asset/a%20b?scenario=Z2032&week=7");
  assert.equal(direction(3, 2), "back");
  assert.equal(direction(2, 3), "forward");
  assert.equal(direction(2, 2), "replace");
  assert.deepEqual(RAIL.map((r) => r.rail), [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11]);
  assert.deepEqual(RAIL.filter((r) => r.step).map((r) => r.step), [1, 1, 2, 3, 4, 5, 7]);  // sidebar follows the 7-step flow (Inventory is part of 1, Proof chain is 2 and 6)
  assert.ok(ROUTES.every((r) => r.title && r.view && r.camera));
});
