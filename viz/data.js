// Pure data layer: results.json -> display model. No DOM, no hard-coded numbers.
// Every number is a cell {kind: "number", value, text, source}; value is taken verbatim from
// results.json. Missing data is {kind: "missing", text: "not yet run"}, never 0.
// Rows that did not run are {kind: "status", text: status_text}. Used by the browser and by
// tests (node), so it must stay free of browser APIs.

export const BANNER =
  "Lab demo · local test ledger · simulator-scale QAOA · risk, effort and shelf-life values are assumptions (config/assumptions.json)";
export const QAOA_LABEL = "measured cross-check, no quantum advantage";
export const NOT_YET_RUN = "not yet run";

const missing = (text = NOT_YET_RUN) => ({ kind: "missing", text });
const status = (text) => ({ kind: "status", text });
const has = (x) => x !== null && x !== undefined;

function num(value, source, digits = 3) {
  if (!has(value) || typeof value !== "number" || !Number.isFinite(value)) return missing();
  const text = value.toFixed(digits); // fixed precision per column; counts pass digits = 0
  return { kind: "number", value, text, source };
}

function src(run_id, solver, job_id, ts, note) {
  return {
    run_id: has(run_id) && run_id !== "" ? run_id : "n/a",
    solver: solver || "n/a",
    job_id: has(job_id) && job_id !== "" ? job_id : "none",
    ts: ts || "n/a",
    ...(note ? { note } : {}),
  };
}

function scheduleSources(r) {
  const runs = r.solver_runs || [];
  const byId = Object.fromEntries(runs.map((x) => [x.run_id, x]));
  const plan = (p, fallbackNote) => {
    const pb = p && p.produced_by;
    if (!pb) return src(null, null, null, r.generated_at, fallbackNote);
    const own = (pb.run_ids || []).map((id) => byId[id]).filter(Boolean);
    const jobs = [...new Set(own.map((x) => x.job_id || `none (${x.job_id_reason || "no job id"})`))];
    const ts = own.length ? own[own.length - 1].ts : r.generated_at;
    return src((pb.run_ids || []).join(", ") || null, pb.solver, jobs.join(", ") || null, ts,
      own.length ? null : "deterministic baseline computed in the same schedule build");
  };
  return {
    optimized: plan(r.exposure),
    fcfs: plan(r.baselines && r.baselines.fcfs),
    greedy: plan(r.baselines && r.baselines.greedy),
  };
}

function chartModel(r, sources) {
  const plans = [
    ["optimized", "QpiAI Opt MILP", r.exposure],
    ["fcfs", "FCFS baseline", r.baselines && r.baselines.fcfs],
    ["greedy", "greedy baseline", r.baselines && r.baselines.greedy],
  ];
  if (!plans.every(([, , p]) => p && Array.isArray(p.remaining_by_week))) {
    return { available: false, text: NOT_YET_RUN };
  }
  const scenarios = r.exposure.remaining_by_week.map((s) => ({ name: s.scenario, year: s.year }));
  const weeks = r.exposure.remaining_by_week[0].points.map((p) => p.week);
  return {
    available: true,
    scenarios,
    weeks,
    plans: plans.map(([key, label, p]) => ({
      key,
      label,
      series: Object.fromEntries(p.remaining_by_week.map((s) => [
        s.scenario,
        s.points.map((pt) => ({ week: pt.week, cell: num(pt.exposure_years, sources[key]) })),
      ])),
    })),
  };
}

function wavesModel(r) {
  return (r.waves || []).map((w) => {
    const ev = w.evidence;
    return {
      week: w.week,
      status: w.status,
      assets: w.assets,
      asset_status: w.asset_status || null,
      source: ev ? src(ev.run_id, "lab gates: openssl s_server stand-ins", null, ev.ts) : src(null, "schedule (not yet verified in lab)", null, r.generated_at),
    };
  });
}

function avoidedModel(r, sources) {
  if (!r.avoided) return null;
  const out = [];
  for (const [key, label] of [["vs_fcfs", "FCFS"], ["vs_greedy", "greedy"]]) {
    const base = key === "vs_fcfs" ? "fcfs" : "greedy";
    for (const row of r.avoided[key] || []) {
      const s = { ...sources.optimized, note: `optimized plan minus ${label} baseline, same inputs` };
      out.push({ baseline: label, scenario: row.scenario, cell: num(row.exposure_years_avoided, s), weighted: num(row.weighted_avoided, s), base });
    }
  }
  return out;
}

function ledgerModel(r) {
  const l = r.ledger;
  if (!l) return { available: false, text: NOT_YET_RUN };
  const v = r.ledger_verification;
  let verified;
  if (!v) verified = { symbol: "", text: "not verified since last ingest" };
  else if (v.root !== l.root || v.entries_checked !== l.entry_count) verified = { symbol: "", text: "stale: verified a different root" };
  else verified = v.ok ? { symbol: "✔", text: "verified" } : { symbol: "✖", text: `failed at index ${v.first_failure && v.first_failure.index}: ${v.first_failure && v.first_failure.reason}` };
  const source = src(null, `${l.alg} via ${l.backend}`, null, v ? v.ts : r.generated_at, `pubkey ${l.pubkey_fp.slice(0, 16)}…`);
  return {
    available: true,
    root: l.root,
    root_short: `${l.root.slice(0, 12)}…`,
    entries: num(l.entry_count, source, 0),
    verified,
    source,
  };
}

function handshakeModel(r) {
  const he = r.handshake_evidence;
  if (!he) return { available: false, text: NOT_YET_RUN };
  const g = r.gates || {};
  const gate = (list, sid) => (list || []).find((x) => x.service_id === sid);
  const source = src(he.run_id, he.openssl_version, "n/a (local lab)", he.ts);
  return {
    available: true,
    note: he.note,
    rows: he.sessions.map((s) => {
      const kex = gate(g.pq_handshake, s.service_id);
      const auth = gate(g.pq_auth, s.service_id);
      return {
        service: s.service_id,
        kex_group: s.negotiated_group,
        kex_class: s.kex_class,
        kex_gate: kex ? kex.result : NOT_YET_RUN,
        auth_alg: s.auth_alg || NOT_YET_RUN,
        auth_gate: auth ? auth.result : NOT_YET_RUN,
        hndl_label: s.label,
        source: { ...source, note: `transcript ${s.transcript_sha256.slice(0, 16)}…` },
      };
    }),
  };
}

const QAOA_COLUMNS = [
  ["feasible_fraction", "feasible"],
  ["approximation_ratio", "approx. ratio"],
  ["energy_ratio", "energy ratio"],
  ["p_optimal", "P(opt)"],
  ["p_optimal_assets", "P(opt set)"],
];

function qaoaModel(r) {
  const q = r.qaoa;
  if (!q || !Array.isArray(q.table)) return { available: false, text: NOT_YET_RUN, label: QAOA_LABEL };
  const rows = q.table.map((row) => {
    const source = src(q.run_id, row.backend, row.job_ids.join(", ") || null, q.ts, row.hardware && row.hardware.provenance);
    const base = { p: row.p, source_kind: row.source, status: row.status, backend: row.backend, source };
    if (row.status !== "ok" || !row.metrics) return { ...base, status_cell: status(row.status_text || NOT_YET_RUN) };
    const hw = row.hardware; // real QPU rows only: numbers of the transpiled circuit actually sent
    const hsrc = hw && src(q.run_id, `${hw.backend} (real hardware)`, hw.job_id, q.ts, hw.provenance || "transpiled circuit sent to the QPU");
    return {
      ...base, job_ids: row.job_ids, shots_cell: num(row.shots, source, 0),
      cells: Object.fromEntries(QAOA_COLUMNS.map(([k]) => [k, num(row.metrics[k], source, 4)])),
      ...(hw ? { hardware: { backend: hw.backend, job_id: hw.job_id, depth: num(hw.transpiled_depth, hsrc, 0),
        two_qubit_gates: num(hw.two_qubit_gates, hsrc, 0), qpu_seconds: num(hw.qpu_seconds, hsrc, 1) } } : {}),
    };
  });
  return {
    available: true,
    label: QAOA_LABEL,
    full_label: q.label,
    columns: QAOA_COLUMNS,
    exact: { objective: num(q.exact.objective, src(q.exact.run_id, q.exact.method, null, q.ts), 6), assets: q.exact.assets },
    rows,
  };
}

function towerModel(r, sources, chart) {
  if (!chart.available) return { available: false, text: NOT_YET_RUN };
  const floors = Object.fromEntries(r.exposure.remaining_by_week.map((s) => [
    s.scenario, s.points.map((pt) => ({ week: pt.week, cell: num(pt.exposure_years, sources.optimized) })),
  ]));
  const beams = [];
  const g = r.gates || {};
  for (const x of g.pq_handshake || []) {
    beams.push({
      id: `svc:${x.service_id}`,
      label: `${x.service_id} (lab service)`,
      off_from_week: x.result === "PASS" ? 0 : null,
      reason: `pq_handshake ${x.result}: ${x.negotiated_group || "no handshake"}`,
      source: src(r.handshake_evidence && r.handshake_evidence.run_id, "pq_handshake gate", null, r.handshake_evidence && r.handshake_evidence.ts),
    });
  }
  const standins = new Map();
  for (const w of r.waves || []) {
    for (const e of (w.evidence && w.evidence.lab_services) || []) {
      const passed = e.status === "applied" && e.gates && e.gates.pq_handshake && e.gates.pq_handshake.result === "PASS";
      const cur = standins.get(e.lab_service) || { off: null, source: null, reason: "" };
      if (passed && cur.off === null) {
        cur.off = w.week;
        cur.reason = `pq_handshake PASS (${e.gates.pq_handshake.negotiated_group}) in week ${w.week}`;
        cur.source = src(w.evidence.run_id, "wave runner gates", null, w.evidence.ts);
      } else if (!cur.source) {
        cur.reason = `pq_handshake ${(e.gates && e.gates.pq_handshake && e.gates.pq_handshake.result) || "not run"} (${e.status})`;
        cur.source = src(w.evidence.run_id, "wave runner gates", null, w.evidence.ts);
      }
      standins.set(e.lab_service, cur);
    }
  }
  for (const [name, v] of standins) {
    beams.push({ id: `wave:${name}`, label: `${name} (wave stand-in)`, off_from_week: v.off, reason: v.reason, source: v.source });
  }
  return { available: true, scenarios: chart.scenarios, weeks: chart.weeks, floors, beams };
}

export function beamOn(beam, week) {
  return beam.off_from_week === null || week < beam.off_from_week;
}

export function buildModel(results) {
  const r = results || {};
  const sources = scheduleSources(r);
  const chart = chartModel(r, sources);
  return {
    banner: BANNER,
    generated_at: r.generated_at || NOT_YET_RUN,
    chart,
    waves: wavesModel(r),
    avoided: avoidedModel(r, sources),
    ledger: ledgerModel(r),
    handshake: handshakeModel(r),
    qaoa: qaoaModel(r),
    tower: towerModel(r, sources, chart),
  };
}

// Walk the model and return every number cell (used by tests to check provenance).
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
