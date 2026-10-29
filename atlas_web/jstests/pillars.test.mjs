import { test } from "node:test";
import { readFileSync } from "node:fs";
import assert from "node:assert/strict";
import { FLOW } from "../static/js/flow.js";
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

import { FLOW as BACKEND } from "../static/js/stages.js";
import { ROUTES } from "../static/js/routes.js";
test("display order follows the backend run order; every backend stage lights exactly one step", () => {
  assert.deepEqual(FLOW.map((f) => f.label), ["Detect", "Proof chain opened", "Plan", "Handshake gates", "Wave selection", "Proof verified", "Review"]);
  const order = STEPS.map((st) => STAGE_OF[st].id).filter((id, i, a) => a.indexOf(id) === i && id !== "report");
  assert.deepEqual(FLOW.flatMap((f) => f.stages), order);  // detect, ledger, schedule, capture, gates, qaoa, seal
  const byStep = ROUTES.filter((r) => r.step).sort((a, b) => a.step - b.step || a.rail - b.rail).map((r) => r.name);
  assert.deepEqual(byStep, ["detect", "inventory", "ledger", "schedule", "handshakes", "qaoa", "review"]);
});

test("a step lights only from its own stages, not its position", () => {
  const sealOnly = model((s) => (STAGE_OF[s].id === "seal" ? "running" : "idle"));
  const st = flowStates(sealOnly);
  assert.equal(st[FLOW.findIndex((f) => f.id === "proof_verified")], "running");
  assert.ok(st.every((x, i) => FLOW[i].id === "proof_verified" || x !== "running"));
});

import { axisEnd, mergeIdentical, spreadLabels } from "../static/js/views/schedule.js";
test("schedule chart: axis end, identical plans merged, labels never overlap", () => {
  const pts = (...v) => v.map((x, i) => ({ week: i, exposure_years: x }));
  const S = [{ cls: "opt", short: "Optimised", label: "o", points: pts(7, 0, 0, 0, 0, 0) }, { cls: "fcfs", short: "FCFS", label: "f", points: pts(7, 7, 0, 0, 0, 0) },
    { cls: "greedy", short: "Greedy", label: "g", points: pts(7, 0, 0, 0, 0, 0) }];
  assert.deepEqual(axisEnd(S), { end: 4, zero: 2 });  // last change at week 2 -> +1 = 3, minimum 4
  const M = mergeIdentical(S);
  assert.equal(M.length, 2);
  assert.equal(M[0].label, "Optimised = Greedy (identical plan)");
  assert.equal(mergeIdentical([S[0], S[2], { ...S[2], short: "FCFS" }])[0].label, "Optimised = Greedy = FCFS (identical plan)");
  const y = spreadLabels([300, 300, 301], 24, 20, 360);
  const sorted = [...y].sort((a, b) => a - b);
  assert.ok(sorted[1] - sorted[0] >= 24 && sorted[2] - sorted[1] >= 24 && sorted[2] <= 360);
});

import { objectiveRows, planHeadline, solverLine } from "../static/js/views/schedule.js";
test("schedule: objective per scenario, solver line and plain headline come from results.json", () => {
  const r = JSON.parse(readFileSync(new URL("../../out/results.json", import.meta.url)));
  const G = objectiveRows(r);
  assert.deepEqual(G.map((g) => g.scenario), r.scenarios.map((s) => s.name));
  const z = G[0], milp = z.bars.find((b) => b.cls === "opt"), fcfs = z.bars.find((b) => b.cls === "fcfs");
  assert.equal(milp.value, r.exposure.per_scenario[0].weighted_exposure);
  assert.ok(Math.abs(fcfs.saved - (100 * (fcfs.value - milp.value)) / fcfs.value) < 1e-9 && fcfs.saved >= 0);
  assert.match(solverLine(r), /^Solved with: qpiai-opt local \(local\), status optimal, \d+ ms, job_id null \(/);
  assert.match(planHeadline({ value: 0.173 }, { value: 0.019 }, "Z2030"), /^The optimised plan avoids 0\.173 exposure-years compared with first-come-first-served/);
  assert.match(planHeadline({ value: 0.019 }, { value: 0 }, "Z2030"), /^On this data the optimal plan equals the simple risk-first plan/);
  assert.equal(planHeadline(null, null, "Z2030"), "Plan comparison: not yet run");
  assert.equal(solverLine({}), "Solved with: not yet run");
});

import { bankShare } from "../static/js/views/landing.js";
test("landing: bank share counts only recorded observations", () => {
  assert.equal(bankShare(null), null);
  assert.equal(bankShare({ observed: {} }), null);
  assert.deepEqual(bankShare({ observed: { a: { outcome: "classical" }, b: { outcome: "hybrid_pq" }, c: { outcome: "classical" } } }), { classical: 2, total: 3 });
});
