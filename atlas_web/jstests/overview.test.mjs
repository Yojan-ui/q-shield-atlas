import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { stageFacts, stageStatus, PLAIN } from "../static/js/components/overview.js";
import { STAGES } from "../static/js/stages.js";

const sample = JSON.parse(readFileSync(new URL("../../tests/fixtures/results_sample.json", import.meta.url)));

test("every stage has a plain name, and every fact has a what-this-means line from results", () => {
  assert.deepEqual(Object.keys(PLAIN), STAGES.map((s) => s.id));
  const f = stageFacts(sample);
  for (const [k, [num, mean]] of Object.entries(f)) { assert.ok(num && mean.length > 20, k); }
  assert.equal(f.detect[0], String(sample.assets.length));
  assert.match(f.capture[1], /HNDL-exposed: recorded traffic relies on classical key exchange/);
  assert.match(f.qaoa[1], /not an advantage/);
  assert.deepEqual(stageFacts(null), {});
});

test("one status per stage: failed step wins, otherwise data present means done", () => {
  const f = stageFacts(sample);
  assert.equal(stageStatus("detect", ["detect"], f, null), "ok");
  assert.equal(stageStatus("detect", ["detect"], {}, null), "idle");
  const run = { status: "FAIL", detail: { summary: [{ step: "detect", exit_code: 0 }, { step: "ledger_open", exit_code: 1 }] } };
  assert.equal(stageStatus("ledger", ["ledger_open"], f, run), "fail");
  assert.equal(stageStatus("schedule", ["schedule"], {}, { status: "running", detail: { summary: [] } }), "running");
});
