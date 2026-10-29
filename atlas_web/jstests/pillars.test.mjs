import { test } from "node:test";
import assert from "node:assert/strict";
import { FLOW } from "../static/js/stages.js";
import { STAGE_OF, STEPS } from "../static/js/model.js";
import { flowStates, resultStates } from "../static/js/views/pipeline.js";
import { pillarHeight, pillarX } from "../static/js/scenes/pillars.js";

const model = (status) => STEPS.map((step) => ({ step, stage: STAGE_OF[step], status: typeof status === "function" ? status(step) : status }));

test("Pipeline columns follow the real run status of each flow step", () => {
  assert.deepEqual(flowStates(model("ok")).filter((s) => s !== "missing"), flowStates(model("ok")).filter((s) => s === "ok"));
  assert.ok(flowStates(model("idle")).every((s) => s === "idle" || s === "missing"));
  const first = STEPS[0];
  const st = flowStates(model((s) => (s === first ? "running" : "pending")));
  assert.equal(st[FLOW.findIndex((f) => f.stages.includes(STAGE_OF[first].id))], "running");
  assert.ok(flowStates(model((s) => (s === first ? "fail" : "ok"))).includes("fail"));
});

test("without a recorded run, columns show only what results.json holds", () => {
  assert.deepEqual(resultStates({ detect: {}, schedule: {} }), FLOW.map((f) => (["detect", "schedule"].includes(f.id) ? "ok" : "missing")));
});

test("pillar geometry is bounded and centred", () => {
  assert.equal(pillarHeight(undefined), pillarHeight(0));
  assert.equal(pillarHeight(5), pillarHeight(1));
  assert.equal(pillarX(0, 3), -pillarX(2, 3));
});

import { benchItems } from "../static/js/views/bench.js";
test("Benchmark bars come only from measured runtimes; nothing measured is 'not yet run'", () => {
  assert.equal(benchItems({ bench: null, crypto: null }, "optimizers"), null);
  assert.equal(benchItems({ bench: null, crypto: null }, "crypto"), null);
  const P = { bench: { instances: [{ id: "a", n_variables: 6 }, { id: "b", n_variables: 7 }], rows: [
    { instance: "b", solver: "exact", status: "ok", runtime_s: 1e-4 }, { instance: "b", solver: "milp", status: "ok", runtime_s: 0.1 },
    { instance: "a", solver: "random", status: "ok", runtime_s: 9 }] } };
  const it = benchItems(P, "optimizers");
  const by = Object.fromEntries(it.map((x) => [x.id, x]));
  assert.ok(by.milp.h > by.exact.h);  // slower is taller (log scale)
  assert.equal(by.random.state, "missing");  // only the largest instance is shown; random has no row there
  assert.match(by.random.label, /not run/);
  const c = benchItems({ crypto: { primitives: { "ML-DSA-65": { public_key_der_bytes: 1974, signature_bytes: 3309 }, "ECDSA P-256": { public_key_der_bytes: 91, signature_bytes: 72 } } } }, "crypto");
  assert.equal(c.find((x) => x.id === "ML-DSA-65").h, 1);
});

import { reviewItems } from "../static/js/views/review.js";
test("Review blocks are coloured by the real signature status", () => {
  const it = reviewItems([{ id: "a", kind: "plan", ledger_index: 3, signature: "verified" }, { id: "b", kind: "wave", ledger_index: 4, signature: "not verified" },
    { id: "c", kind: "qaoa", ledger_index: null, signature: "not signed yet" }]);
  assert.deepEqual(it.map((x) => x.state), ["ok", "fail", "missing"]);
  assert.match(it[0].label, /plan #3/);
  assert.doesNotMatch(it[2].label, /#/);
});

import { packetLength, UNIT } from "../static/js/scenes/lanes3d.js";
test("3D packets are as long as their recorded byte size", () => {
  assert.equal(packetLength(1469), 1469 * UNIT);
  assert.ok(packetLength(1469) > 4 * packetLength(285));
  assert.equal(packetLength(1), packetLength(0));  // tiny records keep a visible minimum
});
