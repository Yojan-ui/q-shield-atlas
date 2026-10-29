import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { stageFacts, flowFacts } from "../static/js/components/overview.js";
import { FLOW } from "../static/js/stages.js";

const sample = JSON.parse(readFileSync(new URL("../../tests/fixtures/results_sample.json", import.meta.url)));

test("every stage has a plain name, and every fact has a what-this-means line from results", () => {
  const f = stageFacts(sample);
  for (const [k, [num, mean]] of Object.entries(f)) { assert.ok(num && mean.length > 20, k); }
  assert.equal(f.detect[0], String(sample.assets.length));
  assert.match(f.capture[1], /HNDL-exposed: recorded traffic relies on classical key exchange/);
  assert.match(f.qaoa[1], /not an advantage/);
  assert.deepEqual(stageFacts(null), {});
});

test("flow facts: one key number and backend per step, from results only", () => {
  const f = flowFacts(sample, { items: [{ status: "pending" }, { status: "approved" }] });
  assert.deepEqual(Object.keys(f).sort(), FLOW.map((s) => s.id).sort());
  assert.equal(f.inventory.num, String(sample.assets.length));
  assert.match(f.schedule.backend, /QpiAI Opt/);
  assert.match(f.waves.backend, /awaiting account activation/);
  assert.equal(f.review.num, "1 / 2");
  assert.deepEqual(flowFacts(null), {});
});
