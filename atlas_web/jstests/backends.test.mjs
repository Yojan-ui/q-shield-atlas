import { test } from "node:test";
import assert from "node:assert/strict";
import { existsSync, readFileSync } from "node:fs";
import { backendRows } from "../static/js/components/backends.js";

const read = (p) => JSON.parse(readFileSync(new URL(p, import.meta.url)));
const sample = read("../../tests/fixtures/results_sample.json");
const DEMO = new URL("../../out/results.json", import.meta.url);
const demo = existsSync(DEMO) ? read(DEMO) : null;
const skip = demo ? false : "out/results.json not present (run ./run_demo.sh)";

test("backend rows: Opt, QSV-Local and QCloud from recorded data; no IBM row without ibm data", { skip }, () => {
  const noIbm = { ...demo, qaoa: { ...demo.qaoa, table: demo.qaoa.table.filter((r) => r.source !== "ibm") } };  // run_demo.sh may import IBM rows
  const rows = backendRows(noIbm);
  assert.deepEqual(rows.map((r) => r.backend), ["QpiAI Opt (local MILP)", "QpiAI QSV-Local simulator", "QpiAI QCloud"]);
  const opt = demo.solver_runs.find((s) => s.stage.endsWith(".expected.expected"));
  assert.equal(rows[0].expand.run_id, opt.run_id);
  assert.equal(rows[0].expand.hash, opt.output_sha256);
  assert.equal(rows[0].result, `${(opt.solver_time_s * 1000).toFixed(0)} ms solve`);
  assert.match(rows[0].expand.why, /^job_id: null \(/);
  assert.equal(rows[1].expand.run_id, demo.qaoa.run_id);
  assert.match(rows[1].result, /^P\(opt set\) [\d.]+ % vs random [\d.]+ % · p = 3$/);
  assert.match(rows[2].chips[0][1], /not requested|not run/);
});

test("QCloud row shows the recorded blocker text and live device count from /api/quantum/status", { skip }, () => {
  const status = { fallback_reason: 'QCloud job creation was rejected: "an active subscription is required to run jobs" (2026-10-28).', checked_at: "2026-10-30T00:00:00Z",
    cloud: { reachable: true, enabled: false, sdk_version: "0.3.0", device: "QpiAI-QSV-Simulator", devices: [{ name: "QpiAI-QSV-Simulator", status: "active" }, { name: "QpiAI-Indus-1", status: "maintenance" }] } };
  const q = backendRows(demo, status).find((r) => r.backend === "QpiAI QCloud");
  assert.deepEqual(q.chips.map((c) => c[1]), ["login ok", "jobs disabled"]);
  assert.equal(q.result, "1 device active");
  assert.match(q.expand.why, /an active subscription is required to run jobs/);
});

test("IBM row only when results carry source ibm rows, with their job IDs", { skip }, () => {
  const ibm = { ...demo.qaoa.table.find((r) => r.source === "qpiai_local"), source: "ibm", backend: "ibm_fez", job_ids: ["job-a"] };
  const rows = backendRows({ ...demo, qaoa: { ...demo.qaoa, table: [...demo.qaoa.table.filter((r) => r.source !== "ibm"), ibm] } });
  const hw = rows.find((r) => r.backend === "IBM ibm_fez");
  assert.ok(hw);
  assert.equal(hw.chips[0][1], "real hardware");
  assert.match(hw.expand.why, /job-a/);
});

test("backend rows from the committed fixture: every row has 1-2 chips and an expand panel", () => {
  const rows = backendRows(sample);
  assert.ok(rows.some((r) => r.backend === "QpiAI QCloud"));
  for (const r of rows) assert.ok(r.chips.length >= 1 && r.chips.length <= 2 && r.expand, r.backend);
});
