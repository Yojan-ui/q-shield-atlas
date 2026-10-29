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
