import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { flowFacts } from "../static/js/components/overview.js";
import { FLOW } from "../static/js/flow.js";

const sample = JSON.parse(readFileSync(new URL("../../tests/fixtures/results_sample.json", import.meta.url)));

test("flow facts: one key number and backend per step, from results only", () => {
  const f = flowFacts(sample, { items: [{ status: "pending" }, { status: "approved" }] });
  for (const s of FLOW) assert.ok(f[s.id], `fact for ${s.id}`);
  assert.match(f.detect.num, /^\d+ → \d+$/);
  assert.equal(f.inventory.num, String(sample.assets.length));
  assert.match(f.schedule.backend, /QpiAI Opt/);
  assert.match(f.waves.backend, /awaiting account activation/);
  assert.equal(f.review.num, "1 / 2");
  assert.deepEqual(flowFacts(null), {});
});
