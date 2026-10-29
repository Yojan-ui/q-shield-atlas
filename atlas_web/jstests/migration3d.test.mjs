import { test } from "node:test";
import assert from "node:assert/strict";
import { clusterOf, layout, nodeX, stageX } from "../static/js/scenes/migration.js";

test("nodes sit left before their wave, cross during it, and stay right after", () => {
  const a = { planned_week: 3 };
  assert.equal(nodeX(a, 0), stageX(0));
  assert.equal(nodeX(a, 2), stageX(0));
  assert.ok(nodeX(a, 2.5) > stageX(0) && nodeX(a, 2.5) < stageX(6));
  assert.equal(nodeX(a, 3), stageX(6));
  assert.equal(nodeX(a, 9), stageX(6));
});

test("banks become clusters; other systems cluster by kind", () => {
  assert.equal(clusterOf({ name: "netbanking.abc.bank.in (abc, netbanking)", kind: "tls_gateway" }), "abc");
  assert.equal(clusterOf({ name: "Payments API", kind: "api" }), "api");
  const L = layout([{ id: "a", name: "www.x.bank.in (x, www)", planned_week: 1 }, { id: "b", name: "x.bank.in (x, apex)", planned_week: 2 }, { id: "c", name: "y.bank.in (y, apex)", planned_week: 1 }]);
  assert.equal(L.clusters, 2);
  assert.equal(L.pos.get("a").cluster, L.pos.get("b").cluster);
});
