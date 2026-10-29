import { test } from "node:test";
import assert from "node:assert/strict";
import { laneOf, progress } from "../static/js/views/migration.js";

test("lanes follow the planned week; verified only when the lab gate applied", () => {
  const a = [{ id: "x", planned_week: 2, status: "applied" }, { id: "y", planned_week: 3, status: "partially_verified" }];
  assert.deepEqual([0, 1, 2, 3, 4].map((w) => laneOf(a[0], w)), ["classical", "classical", "migrating", "done", "done"]);
  assert.deepEqual(progress(a, 0), { done: 0, total: 2, verified: 0 });
  assert.deepEqual(progress(a, 3), { done: 1, total: 2, verified: 1 });
  assert.deepEqual(progress(a, 4), { done: 2, total: 2, verified: 1 });
});
