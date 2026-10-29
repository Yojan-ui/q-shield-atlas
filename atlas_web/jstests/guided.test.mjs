import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { liveStates, stepRunId, stepScene } from "../static/js/components/guided.js";
import { FLOW } from "../static/js/flow.js";

const results = JSON.parse(readFileSync(new URL("../../out/results.json", import.meta.url)));
const opts = { labelsEl: null, stageEl: null, reduced: true };

test("every step's headline comes from recorded results; nothing recorded = not yet run", () => {
  for (const f of FLOW) assert.equal(stepScene(f.id, {}, opts).headline, "not yet run", f.id);
  const d = { results };
  const s = results.detect.summary;
  assert.match(stepScene("detect", d, opts).headline, new RegExp(`^${s.vulnerable_findings} RSA / ECC / DH findings and ${s.pqc_findings} PQC in ${results.detect.files_scanned} files`));
  assert.match(stepScene("schedule", d, opts).headline, new RegExp(`${results.assets.length} systems in ${results.waves.length} weekly waves, ${results.exposure.makespan_weeks} weeks`));
  assert.match(stepScene("schedule", d, opts).headline, new RegExp(results.avoided.vs_fcfs[0].exposure_years_avoided.toFixed(3)));
  assert.equal(stepScene("gates", d, opts).headline, "not yet run");  // needs the recorded handshakes (move payload)
  assert.equal(stepRunId("waves", d), results.qaoa.run_id);
});

test("live: each step lights only from its own SSE step events", () => {
  const st = liveStates({ detect: "ok", ledger_open: "ok", schedule: "running" });
  const at = (id) => st[FLOW.findIndex((f) => f.id === id)];
  assert.equal(at("detect"), "ok");
  assert.equal(at("schedule"), "running");
  assert.equal(at("proof_open"), "ok");  // ledger_open: its own step
  assert.equal(at("proof_verified"), "pending");  // ledger_ingest / ledger_verify not reached yet
  assert.equal(at("gates"), "pending");
  assert.equal(at("review"), "pending");
  assert.equal(liveStates({ ledger_ingest: "ok", ledger_verify: "ok" })[FLOW.findIndex((f) => f.id === "proof_verified")], "ok");
});
