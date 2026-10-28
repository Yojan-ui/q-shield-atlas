// Site data layer: /api payloads -> chapter models. Pure (no DOM, no WebGL) so node tests can run it.
// Every displayed number is a cell {kind:"number", value, text, source} with value taken verbatim from the
// API; missing data is {kind:"missing", text:"not yet run"}; nothing is computed for display.

export const NOT_YET_RUN = "not yet run";
const has = (x) => x !== null && x !== undefined;
const missing = () => ({ kind: "missing", text: NOT_YET_RUN });

export function cell(value, source, digits = 3) {
  if (!has(value) || typeof value !== "number" || !Number.isFinite(value)) return missing();
  return { kind: "number", value, text: value.toFixed(digits), source };
}

const src = (run_id, solver, job_id, ts, note) =>
  ({ run_id: run_id || "n/a", solver: solver || "n/a", job_id: job_id || "none", ts: ts || "n/a", ...(note ? { note } : {}) });

function planSource(r) {
  const pb = (r.exposure || {}).produced_by || {};
  const runs = Object.fromEntries((r.solver_runs || []).map((x) => [x.run_id, x]));
  const own = (pb.run_ids || []).map((id) => runs[id]).filter(Boolean);
  const jobs = [...new Set(own.map((x) => x.job_id || "none (local solve, no platform job ID)"))].join(", ");
  return src((pb.run_ids || []).join(", "), pb.solver, jobs, own.length ? own[own.length - 1].ts : r.generated_at);
}

function harvest(r) {
  const per = (r.exposure || {}).per_scenario;
  if (!per || !r.scenarios) return { available: false };
  const s = planSource(r);
  const byScenario = {};
  per.forEach((p, i) => {
    const sc = r.scenarios.find((x) => x.name === p.scenario) || {};
    byScenario[p.scenario] = {
      year: sc.year,
      exposure: cell(p.exposure_years, { ...s, note: `optimised plan, ${p.scenario}` }),
      weighted: cell(p.weighted_exposure, { ...s, note: `risk-weighted, ${p.scenario}` }),
    };
  });
  return {
    available: true,
    scenarios: r.scenarios.map((x) => x.name),
    byScenario,
    glowMax: Math.max(...per.map((p) => p.exposure_years)), // layout only: normalises the vault glow
  };
}

function detect(r) {
  const d = r.detect;
  if (!d) return { available: false };
  const s = src(d.run_id, "static scan + live probe", null, d.ts, `tree ${d.tree_sha256.slice(0, 12)}…`);
  const files = new Map();
  for (const f of d.findings) {
    if (!files.has(f.file)) files.set(f.file, []);
    files.get(f.file).push({ line: cell(f.line, s, 0), family: f.family, use: f.use, rule: f.rule, snippet: f.snippet });
  }
  return {
    available: true,
    filesScanned: cell(d.files_scanned, s, 0),
    filesWithFindings: cell(d.summary.files_with_findings, s, 0),
    vulnerable: cell(d.summary.vulnerable_findings, s, 0),
    pqc: cell(d.summary.pqc_findings, s, 0),
    assets: cell(d.inventory.assets, s, 0),
    darkColumns: Math.max(0, d.files_scanned - d.summary.files_with_findings), // geometry only, never displayed
    files: [...files.entries()].map(([file, findings]) => ({ file, findings })),
    drift: d.probes.map((p) => ({ service: p.service, group: p.live.group, cert: p.live.cert_algorithm, kinds: p.drift.map((x) => x.kind) })),
  };
}

function schedule(r) {
  const plans = { optimized: r.exposure, fcfs: (r.baselines || {}).fcfs, greedy: (r.baselines || {}).greedy };
  if (!Object.values(plans).every((p) => p && p.remaining_by_week)) return { available: false };
  const s = planSource(r);
  const series = {};
  for (const [k, p] of Object.entries(plans)) {
    const ps = k === "optimized" ? s : src(null, p.produced_by && p.produced_by.solver, null, r.generated_at, "deterministic baseline, same inputs");
    series[k] = Object.fromEntries(p.remaining_by_week.map((sc) => [sc.scenario, sc.points.map((pt) => cell(pt.exposure_years, { ...ps, note: `${k}, ${sc.scenario}, week ${pt.week}` }))]));
  }
  const avoided = {};
  for (const [key, label] of [["vs_fcfs", "fcfs"], ["vs_greedy", "greedy"]]) {
    for (const row of (r.avoided || {})[key] || []) {
      avoided[row.scenario] = avoided[row.scenario] || {};
      avoided[row.scenario][label] = cell(row.exposure_years_avoided, { ...s, note: `optimised minus ${label}, ${row.scenario}` });
    }
  }
  return {
    available: true,
    weeks: r.exposure.remaining_by_week[0].points.map((p) => p.week),
    series,
    avoided,
    waves: (r.waves || []).map((w) => ({ week: w.week, status: w.status, assets: w.assets })),
  };
}

export function strands(group) {
  const m = /^(X25519|SecP256r1|SecP384r1)?MLKEM(\d+)$/.exec(group || "");
  if (!m) return [group || NOT_YET_RUN];
  return [m[1], `ML-KEM-${m[2]}`].filter(Boolean);
}

function handshake(h) {
  if (!h) return { available: false };
  const s = src(h.run_id, h.openssl_version, "n/a (local lab)", h.ts);
  const gate = (list, id) => ((list || []).find((g) => g.service_id === id) || {}).result || NOT_YET_RUN;
  return {
    available: true,
    note: h.note,
    services: h.sessions.map((x) => ({
      id: x.service_id,
      group: x.negotiated_group,
      kexClass: x.kex_class,
      strands: strands(x.negotiated_group),
      auth: x.auth_alg || NOT_YET_RUN,
      kexGate: gate(h.pq_handshake, x.service_id),
      authGate: gate(h.pq_auth, x.service_id),
      downgrade: gate(h.downgrade, x.service_id),
      hndl: x.label,
      source: { ...s, note: `transcript ${x.transcript_sha256.slice(0, 16)}…` },
    })),
  };
}

export function buildSite(results, ledger, handshakes) {
  const r = results || {};
  return {
    generatedAt: r.generated_at || NOT_YET_RUN,
    harvest: harvest(r),
    detect: detect(r),
    schedule: schedule(r),
    handshake: handshake(handshakes),
    ledger: ledger ? { entries: cell(ledger.entry_count, src(null, `${ledger.alg} via ${ledger.backend}`, null, null), 0), root: ledger.root } : { available: false },
  };
}

export function numberCells(model) {
  const out = [];
  const walk = (x) => {
    if (Array.isArray(x)) x.forEach(walk);
    else if (x && typeof x === "object") {
      if (x.kind === "number") out.push(x);
      else Object.values(x).forEach(walk);
    }
  };
  walk(model);
  return out;
}
