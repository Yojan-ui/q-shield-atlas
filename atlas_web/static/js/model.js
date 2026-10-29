// Display model for atlas_web views. Builds on viz/data.js (shared with the 2D viz) and adds the cells the
// routes need. Every number is a cell {kind:"number", value, text, source} taken verbatim from an API
// payload; missing data is {kind:"missing", text:"not yet run"}; rows that did not run carry status_text.
import { buildModel, NOT_YET_RUN, QAOA_LABEL } from "./vizdata.js";

export { NOT_YET_RUN, QAOA_LABEL };
export const HNDL = "HNDL-exposed: recorded traffic relies on classical key exchange";
import { STAGES, STAGE_OF, STEPS } from "./stages.js";  // generated from contracts/stages.json

export { STAGES, STAGE_OF, STEPS };

const has = (x) => x !== null && x !== undefined;
export const missing = (text = NOT_YET_RUN) => ({ kind: "missing", text });
export function num(value, source, digits = 0) {
  if (typeof value !== "number" || !Number.isFinite(value)) return missing();
  return { kind: "number", value, text: value.toFixed(digits), digits, source };
}

export function ledgerIndex(r, runId) {
  if (!runId || !r || !r.ledger) return null;
  const e = (r.ledger.entries || []).filter((x) => x.payload_ref && x.payload_ref.includes(runId));
  return e.length ? e.map((x) => x.index).join(", ") : null;
}

export function source(r, { run_id = null, solver = null, job_id = null, job_id_reason = null, ts = null, note = null } = {}) {
  const ids = String(run_id || "").split(",").map((s) => s.trim()).filter(Boolean);
  const idx = ids.map((id) => ledgerIndex(r, id)).filter(Boolean);
  return {
    run_id: ids.length ? ids.join(", ") : "n/a",
    solver: solver || "n/a",
    job_id: has(job_id) && job_id !== "" ? job_id : job_id_reason ? `none (${job_id_reason})` : "none",
    ledger_index: idx.length ? idx.join(", ") : "not signed",
    ts: ts || "n/a",
    ...(note ? { note } : {}),
  };
}

function detectModel(r) {
  const d = r && r.detect;
  if (!d) return { available: false, text: NOT_YET_RUN };
  const s = source(r, { run_id: d.run_id, solver: "detect: static scan + live probe", ts: d.ts, note: `tree ${String(d.tree_sha256).slice(0, 12)}…` });
  return {
    available: true,
    files: num(d.files_scanned, s), vulnerable: num(d.summary.vulnerable_findings, s), pqc: num(d.summary.pqc_findings, s),
    assets: num(d.inventory.assets, s), drift: num(d.drift_count, s), notVulnerable: d.inventory.not_vulnerable || [],
    findings: (d.findings || []).map((f) => ({ file: f.file, line: f.line, family: f.family, use: f.use, rule: f.rule, snippet: f.snippet })),
    probes: (d.probes || []).map((p) => ({ service: p.service, endpoint: p.endpoint, group: p.live && p.live.group,
      cert: p.live && p.live.cert_algorithm, ok: !!(p.live && p.live.handshake_ok), drift: (p.drift || []).map((x) => x.kind) })),
    source: s,
  };
}

function assetsModel(r, scene) {
  if (!r || !Array.isArray(r.assets)) return [];
  const nodes = Object.fromEntries(((scene && scene.nodes) || []).map((n) => [n.id, n]));
  const plan = r.exposure && r.exposure.produced_by;
  const runs = r.solver_runs || [];
  return r.assets.map((a) => {
    const n = nodes[a.id];
    const s = source(r, { run_id: plan && plan.run_ids.join(", "), solver: plan && plan.solver, job_id: plan && plan.job_ids.find(Boolean),
      job_id_reason: (runs[0] || {}).job_id_reason, ts: (runs[runs.length - 1] || {}).ts,
      note: "exposure-years by schedule.problem.exposure_years on the recorded plan" });
    return {
      id: a.id, name: a.name, kind: a.kind, data_class: a.data_class, algorithm: a.algorithm, status: a.status || "planned",
      week: num(r.exposure && r.exposure.completion_week ? r.exposure.completion_week[a.id] : null, s),
      findings: (a.evidence || []).length, evidence: a.evidence || [], depends_on: a.depends_on || [],
      exposure: n && n.exposure_years ? Object.fromEntries(Object.entries(n.exposure_years).map(([k, v]) => [k, num(v, s, 3)])) : null,
      shelf: num(a.shelf_life_years, { ...s, note: "assumption (config/assumptions.json)" }, 1),
      effort: num(a.effort_days, { ...s, note: "assumption (config/assumptions.json)" }, 1),
      risk: num(a.risk_weight, { ...s, note: "assumption (config/assumptions.json)" }, 0),
      standin: n ? n.standin : null,
    };
  });
}

export function solverLabel(r) {
  // only recorded fields: solver_runs[].mode / termination / guarantee (HiGHS is not recorded per run, so not shown)
  const runs = (r && r.solver_runs) || [];
  if (!runs.length) return NOT_YET_RUN;
  const x = runs[0];
  return ["QpiAI Opt", x.mode === "local" ? "local MILP" : `${x.mode || "platform"} MILP`, x.termination,
    x.guarantee === "global_optimum" ? "global optimum" : x.guarantee].filter(Boolean).join(" · ");
}

export function stationsModel(runsPayload) {
  const last = runsPayload && runsPayload.runs && runsPayload.runs[0];
  const summary = Object.fromEntries(((last && last.detail && last.detail.summary) || []).map((s) => [s.step, s]));
  return STEPS.map((step, i) => {
    const s = summary[step];
    const status = !s ? (last && last.status === "running" ? "pending" : "idle") : s.exit_code === 0 ? "ok" : "fail";
    return { step, stage: STAGE_OF[step], index: i + 1, status, duration: s ? num(s.duration_s, { run_id: last.id, solver: "atlas_web runner", job_id: "none", ledger_index: "n/a", ts: new Date(last.started * 1000).toISOString() }, 1) : missing(status === "pending" ? "pending" : "not yet run") };
  });
}

export function headlineAvoided(m, scenario) {
  const rows = (m.avoided || []).filter((a) => a.scenario === scenario);
  return { fcfs: (rows.find((a) => a.baseline === "FCFS") || {}).cell || missing(), greedy: (rows.find((a) => a.baseline === "greedy") || {}).cell || missing() };
}

export function buildViewModel(results, scene = null) {
  const r = results || null;
  const base = buildModel(r);
  return {
    ...base,
    results: r,
    detect: detectModel(r),
    assets: assetsModel(r, scene),
    solver: solverLabel(r),
    makespan: r && r.exposure ? num(r.exposure.makespan_weeks, source(r, { run_id: r.exposure.produced_by.run_ids.join(", "),
      solver: r.exposure.produced_by.solver, job_id_reason: ((r.solver_runs || [])[0] || {}).job_id_reason, ts: r.generated_at })) : missing(),
    scenarios: base.chart.available ? base.chart.scenarios : (r && r.scenarios) || [],
  };
}

// Every number cell in a view model (tests check each one exists in the API payload).
export function numberCells(model) {
  const out = [];
  const seen = new Set();
  const walk = (x) => {
    if (!x || typeof x !== "object" || seen.has(x)) return;
    seen.add(x);
    if (Array.isArray(x)) { x.forEach(walk); return; }
    if (x.kind === "number") { out.push(x); return; }
    for (const [k, v] of Object.entries(x)) if (k !== "results") walk(v);
  };
  walk(model);
  return out;
}
