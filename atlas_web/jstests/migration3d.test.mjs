import { test } from "node:test";
import assert from "node:assert/strict";
import { nodeX, stageX } from "../static/js/scenes/migration.js";

test("nodes sit left before their wave, cross during it, and stay right after", () => {
  const a = { planned_week: 3 };
  assert.equal(nodeX(a, 0), stageX(0));
  assert.equal(nodeX(a, 2), stageX(0));
  assert.ok(nodeX(a, 2.5) > stageX(0) && nodeX(a, 2.5) < stageX(7));
  assert.equal(nodeX(a, 3), stageX(7));
  assert.equal(nodeX(a, 9), stageX(7));
});
