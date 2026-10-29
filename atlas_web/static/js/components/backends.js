// Wave selection backends table. backendRows() is pure: results.json, plus /api/quantum/status for QCloud.
import { h } from "../dom.js";
import { chip } from "./chip.js";
import { table } from "./table.js";
import { quantumStatus } from "./quantum.js";
import { main } from "./page.js";

const pct = (x) => `${(x * 100).toFixed(2)} %`;
const tbl = (q) => (q && q.table) || [];
const okRows = (q, src) => tbl(q).filter((r) => r.source === src && r.status === "ok" && r.metrics).sort((a, b) => a.p - b.p);

export function backendRows(results, status = null) {
  const r = results || {}, q = r.qaoa || null, rows = [];
  const runs = (r.solver_runs || []).filter((s) => s.provider === "qpiai-opt");
  const opt = runs.find((s) => /\.expected\.expected$/.test(s.stage || "")) || runs[0];
  if (opt) rows.push({ backend: "QpiAI Opt (local MILP)", chips: [[opt.status === "optimal" ? "ok" : "FAIL", opt.status], ["recorded", opt.mode]],
    result: opt.solver_time_s != null ? `${(opt.solver_time_s * 1000).toFixed(0)} ms solve` : "–",
    expand: { why: `job_id: ${opt.job_id === null ? `null (${opt.job_id_reason})` : opt.job_id}`, hash: opt.output_sha256, run_id: opt.run_id, ts: opt.ts,
      technical: `qpiai-opt ${opt.package_version} · stage ${opt.stage} · termination ${opt.termination} · guarantee ${opt.guarantee} · inputs SHA-256 ${opt.inputs_sha256}` } });
  const rnd = okRows(q, "random")[0];
  const sampled = (src, name, chips) => {
    const all = okRows(q, src), top = all[all.length - 1];
    if (!top) return null;
    return { backend: name, chips, result: `P(opt set) ${pct(top.metrics.p_optimal_assets)}${rnd ? ` vs random ${pct(rnd.metrics.p_optimal_assets)}` : ""} · p = ${top.p}`,
      expand: { run_id: q.run_id, ts: q.ts, all } };
  };
  const qsv = sampled("qpiai_local", "QpiAI QSV-Local simulator", [["ok", "ran"], ["recorded", "simulator"]]);
  if (qsv) rows.push({ ...qsv, expand: { ...qsv.expand, why: `job_id: null (${qsv.expand.all[0].job_id_reason})` } });
  const cloudRow = tbl(q).find((x) => x.source === "qcloud");
  const cloud = status && status.cloud;
  rows.push({ backend: "QpiAI QCloud",
    chips: cloud ? [[cloud.reachable ? "ok" : "FAIL", cloud.reachable ? "login ok" : "login failed"], [cloud.enabled ? "ok" : "NOT_RUN", cloud.enabled ? "enabled" : "jobs disabled"]]
      : [["NOT_RUN", cloudRow ? cloudRow.status.replaceAll("_", " ") : "not run"]],
    result: cloud ? (cloud.reachable ? ((n) => `${n} device${n === 1 ? "" : "s"} active`)(cloud.devices.filter((d) => d.status === "active").length) : "–") : "no QCloud job",
    expand: { why: (status && status.fallback_reason) || (cloudRow && cloudRow.status_text) || "QCloud status unavailable", ts: status ? status.checked_at : q && q.ts,
      technical: cloud ? `qpiai-quantum ${cloud.sdk_version} · device ${cloud.device} · ${cloud.devices.map((d) => `${d.name} ${d.status}`).join(", ") || cloud.error || "no devices listed"}` : null } });
  const hw = sampled("ibm", "IBM ibm_fez", [["hybrid", "real hardware"], ["ok", "measured"]]);
  if (hw) {
    const ids = hw.expand.all.flatMap((x) => x.job_ids || []);
    rows.push({ ...hw, backend: `IBM ${hw.expand.all[0].backend}`, expand: { ...hw.expand, why: `IBM job IDs: ${ids.join(", ")}. A measured cross-check; no quantum advantage claimed.` } });
  }
  const ibmOther = tbl(q).filter((x) => x.source === "ibm" && x.status !== "ok");
  if (!hw && ibmOther.length) rows.push({ backend: `IBM ${ibmOther[0].backend}`, chips: [["hybrid", "real hardware"], ["NOT_RUN", ibmOther[0].status]], result: "–",
    expand: { why: ibmOther.map((x) => `p = ${x.p}: ${x.status_text}`).join(" · "), run_id: q.run_id, ts: q.ts } });
  return rows;
}

export function backendTable(ctx, results) {
  const slot = h("div", {});
  const draw = (s) => slot.replaceChildren(table({ caption: "Quantum and optimisation backends", rows: backendRows(results, s), signal: ctx.signal,
    expand: (r) => r.expand, columns: [
      { label: "backend", render: (r) => r.backend },
      { label: "status", sortable: false, render: (r) => h("span", {}, ...r.chips.map(([k, t]) => chip(k, t))) },
      { label: "result", optional: true, render: (r) => r.result }] }));
  draw(null);
  quantumStatus(ctx.api).then(draw).catch(() => {});
  return main(slot, { title: "Quantum backends" });
}
