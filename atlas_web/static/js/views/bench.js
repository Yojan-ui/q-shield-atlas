// Benchmark, two tabs. Cryptography: classical vs hybrid vs post-quantum TLS measured on lab services (bench/crypto.py).
// Optimizers: FCFS, greedy, QpiAI Opt MILP, QAOA on both simulators and hybrid vs the exact optimum (python -m bench).
// Every number comes from out/bench*.json, signed into the Proof Chain.
import { h, icon } from "../dom.js";
import { chip } from "../components/chip.js";
import { table, tableSkeleton } from "../components/table.js";
import { emptyState } from "../components/states.js";
import { toast } from "../components/toast.js";
import { confirmDialog } from "../components/dialog.js";
import { dataView, honesty, mountScene, stage, viewCss } from "./common.js";
import { buildPillars } from "../scenes/pillars.js";
import { bullets, detailsList, keyStats, main, nextStep, pageHead, dd } from "../components/page.js";
import { term } from "../glossary.js";
import { qualityBlock } from "../components/solvers.js";

// monochrome (colour is reserved for pass / fail / warn): series differ by grey level and dash pattern, and every
// line is labelled directly at its end
export const SERIES = [
  { key: "exact", label: "Exact (brute force)", color: "#FFFFFF", dash: null, family: "classical" },
  { key: "milp", label: "MILP (QpiAI Opt)", color: "#CFCFCF", dash: "2 3", family: "classical" },
  { key: "random", label: "Random sampling", color: "#8C8C8C", dash: "8 4", family: "baseline" },
  { key: "qaoa1", label: "QAOA p=1 (numpy simulator)", color: "#B0B0B0", dash: null, family: "quantum (simulator)" },
  { key: "qaoa_sdk1", label: "QAOA p=1 (QpiAI-QSV-Local)", color: "#9A9A9A", dash: "1 2", family: "quantum (simulator)" },
  { key: "hybrid", label: "Hybrid (QAOA + repair)", color: "#E0E0E0", dash: "6 4", family: "hybrid" },
];
export const seriesKey = (r) => (r.solver === "qaoa" || r.solver === "qaoa_sdk" ? `${r.solver}${r.p}` : r.solver);
const fmt = (x, d = 3) => (x === null || x === undefined ? "–" : Number(x).toFixed(d));
const secs = (x) => (x === null || x === undefined ? "–" : x < 0.01 ? `${(x * 1000).toFixed(2)} ms` : `${x.toFixed(2)} s`);

// runtime (log scale) against problem size, one line per solver; a <title> on every point is its tooltip
export function runtimeChart(rows, instances) {
  const W = 760, H = 320, L = 84, R = 190, T = 16, B = 44;  // room for "100 ms" ticks and end labels at 16px
  const xs = instances.map((i) => i.n_variables), x0 = Math.min(...xs), x1 = Math.max(...xs);
  const pts = rows.filter((r) => r.status === "ok" && r.runtime_s > 0 && SERIES.some((s) => s.key === seriesKey(r)));
  const lo = Math.floor(Math.log10(Math.min(...pts.map((r) => r.runtime_s)))), hi = Math.ceil(Math.log10(Math.max(...pts.map((r) => r.runtime_s))));
  const X = (n) => L + ((n - x0) / Math.max(1, x1 - x0)) * (W - L - R);
  const Y = (t) => T + (1 - (Math.log10(t) - lo) / Math.max(1, hi - lo)) * (H - T - B);
  const svg = h("svg", { viewBox: `0 0 ${W} ${H}`, class: "bn-chart", role: "img", "aria-label": "Runtime against problem size per solver, log scale" });
  for (let e = lo; e <= hi; e++) {
    svg.append(h("line", { ns: "svg", x1: L, x2: W - R, y1: Y(10 ** e), y2: Y(10 ** e), class: "bn-grid" }),
      h("text", { ns: "svg", x: L - 8, y: Y(10 ** e) + 4, class: "bn-tick", "text-anchor": "end" }, e >= 0 ? `${10 ** e} s` : `${10 ** (e + 3)} ms`));
  }
  for (const n of xs) svg.append(h("text", { ns: "svg", x: X(n), y: H - B + 18, class: "bn-tick", "text-anchor": "middle" }, String(n)));
  svg.append(h("text", { ns: "svg", x: (L + W - R) / 2, y: H - 6, class: "bn-axis", "text-anchor": "middle" }, "problem size (QUBO variables)"));
  const ends = [];
  for (const s of SERIES) {
    const line = pts.filter((r) => seriesKey(r) === s.key).sort((a, b) => a.n_variables - b.n_variables);
    if (!line.length) continue;
    // hybrid reuses QAOA p=1 samples, so the two lines can coincide: hybrid is dashed so both stay visible
    svg.append(h("polyline", { ns: "svg", points: line.map((r) => `${X(r.n_variables)},${Y(r.runtime_s)}`).join(" "), class: "bn-line", stroke: s.color,
      "stroke-dasharray": s.dash }));
    for (const r of line) svg.append(h("circle", { ns: "svg", cx: X(r.n_variables), cy: Y(r.runtime_s), r: 4, fill: s.color, class: "bn-dot" },
      h("title", { ns: "svg" }, `${s.label} · n = ${r.n_variables}: ${secs(r.runtime_s)}, objective ${fmt(r.objective, 4)} (optimum ${fmt(r.optimum, 4)})`)));
    const last = line[line.length - 1];
    ends.push({ x: X(last.n_variables) + 8, y: Y(last.runtime_s) + 4, text: s.label.split(" (")[0] });
  }
  ends.sort((a, b) => a.y - b.y).forEach((e, i, all) => { if (i && e.y - all[i - 1].y < 22) e.y = all[i - 1].y + 22; });  // 16px labels: 22 px apart, never overlapping
  for (const e of ends) svg.append(h("text", { ns: "svg", x: e.x, y: e.y, class: "bn-label" }, e.text));
  return svg;
}

const pct = (x) => (x === null || x === undefined ? "–" : `${(x * 100).toFixed(1)} %`);
const n0 = (x) => (x === null || x === undefined ? "–" : Math.round(x).toLocaleString("en-US"));
const cell = (value, digits, source) => ({ kind: "number", value, text: Number(value).toFixed(digits), digits, source });

// 3D bars from the measured fields only. Optimizers: runtime_s per solver on the largest instance (log scale).
// Cryptography: public key + signature / ciphertext bytes per primitive. null = not yet run.
const SHORT = { exact: "exact", milp: "MILP", random: "random", qaoa1: "QAOA p1\nnumpy", qaoa_sdk1: "QAOA p1\nQSV-Local", hybrid: "hybrid" };
export function benchItems(P, tab) {
  if (tab === "crypto") {
    const prim = P && P.crypto && P.crypto.primitives;
    if (!prim) return null;
    const rows = Object.entries(prim).map(([a, x]) => ({ a, b: (x.public_key_der_bytes || 0) + (x.signature_bytes || x.ciphertext_bytes || 0) })).filter((r) => r.b > 0);
    const max = Math.max(1, ...rows.map((r) => r.b));
    return rows.length ? rows.map((r) => ({ id: r.a, label: `${r.a}\n${r.b.toLocaleString("en-US")} B`, h: r.b / max, state: "ok" })) : null;
  }
  const b = P && P.bench;
  if (!b || !b.instances || !b.instances.length) return null;
  const big = b.instances[b.instances.length - 1];
  const rows = SERIES.map((s) => ({ s, r: b.rows.find((r) => r.instance === big.id && seriesKey(r) === s.key) }));
  const t = rows.filter((x) => x.r && x.r.status === "ok" && x.r.runtime_s > 0).map((x) => Math.log10(x.r.runtime_s));
  const lo = Math.min(...t), hi = Math.max(...t);
  return rows.map(({ s, r }) => (r && r.status === "ok" && r.runtime_s > 0
    ? { id: s.key, label: `${SHORT[s.key] || s.key}\n${secs(r.runtime_s)}`, h: 0.08 + 0.92 * (hi > lo ? (Math.log10(r.runtime_s) - lo) / (hi - lo) : 1), state: "ok" }
    : { id: s.key, label: `${SHORT[s.key] || s.key}\nnot run`, h: 0, state: "missing" }));
}

function cryptoTab(ctx, P) {
  const c = P.crypto;
  if (!c) return emptyState({ title: "Cryptography benchmark: not yet run", body: "Run the benchmark (python -m bench.crypto) to measure classical, hybrid and post-quantum TLS on this machine.", action: null });
  const H = Object.fromEntries(c.handshakes.map((r) => [r.id, r]));
  const prim = c.primitives;
  const src = { run_id: c.run_id, solver: c.openssl, ts: c.ts };
  const sec = (a) => (prim[a] && prim[a].security) || {};
  const extra = H.hybrid && H["classical-ecdsa"] ? H.hybrid.handshake_bytes.total - H["classical-ecdsa"].handshake_bytes.total : null;
  return h("div", {}, dd({ source: c.label }),
    keyStats([
      { label: "extra bytes for hybrid", cell: cell(extra, 0, src), unit: "bytes per handshake vs X25519 + ECDSA", mean: "What post-quantum protection of recorded traffic costs on the wire: a few kilobytes once per connection." },
      { label: "hybrid handshake time", cell: cell(H.hybrid.handshake_ms_median, 1, src), unit: `ms median vs ${H["classical-ecdsa"].handshake_ms_median.toFixed(1)} ms classical`, mean: "Measured end to end on this machine, including starting the client; compare rows, not absolute values." },
      { label: "ML-DSA-65 signature", cell: cell(prim["ML-DSA-65"].signature_bytes, 0, src), unit: `bytes vs ${prim["ECDSA P-256"].signature_bytes} for ECDSA P-256`, mean: "Post-quantum signatures are much larger; that is why hybrid key exchange comes first and certificates later." }]),
    main(table({ caption: "TLS 1.3 handshakes on lab services", rows: c.handshakes,
      expand: (r) => ({ why: `Client → server ${n0(r.handshake_bytes.client_to_server)} B, server → client ${n0(r.handshake_bytes.server_to_client)} B; median of ${r.n} handshakes.`, hash: r.transcript_sha256, run_id: c.run_id, ts: c.ts,
        technical: `negotiated ${r.established ? r.negotiated_group : "not measured"} · ${c.openssl}` }), columns: [
      { label: "configuration", render: (r) => r.label.split(": ")[1] || r.label },
      { label: "quantum", render: (r) => (r.family === "classical" ? chip("HNDL-exposed", "breakable") : chip("PASS", "protected")) },
      { label: "total (B)", numeric: true, sort: (r) => r.handshake_bytes.total, render: (r) => n0(r.handshake_bytes.total) },
      { label: "median (ms)", numeric: true, optional: true, sort: (r) => r.handshake_ms_median, render: (r) => r.handshake_ms_median.toFixed(1) }] }),
      { title: "Handshakes: bytes on the wire and time" }),
    main(table({ caption: "Algorithms: sizes and speed", rows: Object.entries(prim).map(([a, v]) => ({ a, ...v })),
      expand: (r) => ({ why: `Quantum security: ${sec(r.a).quantum || "–"}; classical ${sec(r.a).classical_bits ? `${sec(r.a).classical_bits} bits` : "–"} (cited: ${sec(r.a).ref || "–"}).`, run_id: c.run_id, ts: c.ts,
        technical: r.speed ? `${Object.entries(r.speed.ops_per_s).map(([k, v]) => `${k} ${n0(v)}`).join(" · ")} (${r.speed.command})` : "speed not measured" }), columns: [
      { label: "algorithm", render: (r) => h("span", { class: "mono", text: r.a }) },
      { label: "quantum", render: (r) => (/Shor/.test(sec(r.a).quantum || "") ? chip("HNDL-exposed", "breakable") : chip("PASS", "safe")) },
      { label: "public key (B)", numeric: true, sort: (r) => r.public_key_der_bytes ?? -1, render: (r) => n0(r.public_key_der_bytes) },
      { label: "sig / ct (B)", numeric: true, optional: true, sort: (r) => r.signature_bytes ?? r.ciphertext_bytes ?? -1, render: (r) => n0(r.signature_bytes ?? r.ciphertext_bytes) }] }), { title: "Algorithms: key and signature sizes, speed, security level" }),
    detailsList([
      { title: "How it works", summary: "Four lab servers, one per configuration; each handshake is recorded and timed.", body: bullets([c.method.split("\n").map((x) => x.trim()).filter(Boolean).join(" ")]) },
      { title: "Why this method", summary: "Real handshakes on the same machine make the configurations directly comparable.", body: bullets([
        ["Hybrid (", term("hybrid", "X25519MLKEM768"), ") is what browsers and Cloudflare deploy today; pure post-quantum is shown for comparison."],
        "Bytes and time are what operators feel; security levels are cited from the standards."]) },
      { title: "Evidence & sources", summary: `run ${c.run_id.slice(0, 12)} · ${c.openssl}${P.crypto_ledger_index !== null && P.crypto_ledger_index !== undefined ? ` · Proof Chain #${P.crypto_ledger_index}` : ""}`, body: bullets(c.handshakes.map((r) => `${r.label}: transcript SHA-256 ${r.transcript_sha256}, ${r.n} handshakes`)) },
      { title: "Limits", summary: "Loopback only; network latency and real certificate chains are not included.", body: bullets([
        "Times include starting the openssl client process, the same for every row.", "Security levels are reference values (NIST), not measurements.", c.qkd]) }]));
}

function optimizerTab(ctx, P) {
  const b = P.bench;
  const S = b.schedule_rows || [];
  const sq = Object.fromEntries(S.map((r) => [r.solver, r]));
  const big = b.instances[b.instances.length - 1];
  const at = (inst, key) => b.rows.find((r) => r.instance === inst.id && seriesKey(r) === key);
  const qaoaHits = b.instances.filter((i) => { const r = at(i, "qaoa1"); return r && r.status === "ok" && r.approximation_ratio === 1; }).length;
  const src = { run_id: b.run_id, solver: "python -m bench", ts: b.ts };
  return h("div", {},
    h("div", { class: "bn-claim" }, chip("recorded", "measured"), h("p", { text: b.label })),
    h("h3", { class: "pl-h3", text: "Solution quality (same chart as the Plan page)" }), qualityBlock(P, ctx),
    keyStats([
      sq.milp && sq.greedy ? { label: "best rule of thumb vs MILP", cell: cell(100 * Math.max(sq.greedy.approximation_ratio, sq.fcfs.approximation_ratio), 1, src), unit: "% of the optimum (100 = optimal)", mean: "How close the best simple rule (greedy or first-come-first-served) gets to QpiAI Opt's proven best plan." } : null,
      { label: "QAOA found the optimum", cell: cell(qaoaHits, 0, src), unit: `of ${b.instances.length} small wave-selection problems (p = 1)`, mean: "At these sizes random guessing finds it too; see P(optimum) in the table." },
      { label: `runtime at ${big.n_variables} variables`, cell: cell(at(big, "qaoa1").runtime_s, 2, src), unit: `s for QAOA (simulated) vs ${secs(at(big, "exact").runtime_s)} exact`, mean: "Simulating a quantum computer costs 2^n; the classical exact answer is far faster here." }].filter(Boolean)),
    S.length ? main(table({ caption: "Full migration schedule", rows: S, columns: [
      { label: "method", render: (r) => h("span", {}, { fcfs: "First-come-first-served", greedy: "Greedy (highest risk first)", milp: "QpiAI Opt MILP", qaoa: "QAOA" }[r.solver], h("span", { class: "sub", text: r.family })) },
      { label: "quality (% of optimum)", numeric: true, sort: (r) => r.approximation_ratio ?? -1, render: (r) => (r.status === "ok" ? pct(r.approximation_ratio) : "–") },
      { label: "weighted exposure", numeric: true, sort: (r) => r.objective ?? 1e9, render: (r) => fmt(r.objective, 3) },
      { label: "weeks", numeric: true, render: (r) => (r.makespan_weeks ?? "–") },
      { label: "runtime", numeric: true, sort: (r) => r.runtime_s ?? 1e9, render: (r) => secs(r.runtime_s) },
      { label: "guarantee", render: (r) => r.guarantee },
      { label: "size (binary variables)", numeric: true, render: (r) => n0(r.n_variables) },
      { label: "status", render: (r) => (r.status === "ok" ? chip("ok", "measured") : h("span", { class: "fine", text: r.status_text })) }] }), { title: "Scheduling the whole migration" }) : null,
    main(h("div", {}, runtimeChart(b.rows, b.instances), h("ul", { class: "bn-legend", "aria-label": "Chart legend" }, SERIES.map((s) =>
      h("li", {}, h("svg", { viewBox: "0 0 24 8", class: "bn-key", "aria-hidden": "true" }, h("line", { ns: "svg", x1: 0, y1: 4, x2: 24, y2: 4, stroke: s.color, "stroke-width": 2, "stroke-dasharray": s.dash })), `${s.label} · ${s.family}`))),
      dd({ read: "each line is one solver; it shows the measured runtime (log scale) as the problem grows. Lower is faster. Simulator QAOA is a cross-check, not a speed claim." }),
      table({ caption: "Wave-selection instances", rows: b.rows, columns: [
        { label: "instance", key: "instance", mono: true },
        { label: "variables", numeric: true, render: (r) => String(r.n_variables) },
        { label: "solver", render: (r) => h("span", {}, r.solver === "qaoa" ? `QAOA p=${r.p} (numpy)` : r.solver === "qaoa_sdk" ? `QAOA p=${r.p} (QpiAI-QSV-Local)` : (SERIES.find((s) => s.key === r.solver) || { label: r.solver }).label, h("span", { class: "sub", text: r.family })) },
        { label: "quality (ratio)", numeric: true, sort: (r) => r.approximation_ratio ?? -1, render: (r) => (r.status === "ok" ? fmt(r.approximation_ratio, 3) : "–") },
        { label: "P(optimum)", numeric: true, optional: true, sort: (r) => r.p_optimal_assets ?? -1, render: (r) => pct(r.p_optimal_assets) },
        { label: "runtime", numeric: true, sort: (r) => r.runtime_s ?? 1e9, render: (r) => (r.status === "ok" ? secs(r.runtime_s) : "–") },
        { label: "guarantee", optional: true, render: (r) => r.guarantee || "–" },
        { label: "status", render: (r) => (r.status === "ok" ? chip("ok", r.feasible ? "feasible" : "infeasible") : chip("NOT_RUN", r.status.replaceAll("_", " "))) }] })),
      { title: "Choosing one week's wave (small QUBO)" }),
    main(h("div", { class: "bn-why" }, bullets([
      ["Scheduling is a large problem with hundreds of yes/no choices plus continuous exposure: a ", term("milp", "MILP"), " solver like QpiAI Opt finds the proven best plan in seconds."],
      ["QAOA needs the problem as a small ", term("qubo", "QUBO"), " and, on today's simulators, at most about 16 variables; each extra variable doubles the cost."],
      "So QAOA is used only where it fits, one week's wave selection, and always checked against the exact answer.",
      "No quantum advantage is claimed; QpiAI Cloud (simulator) is awaiting account activation and hardware is never used."])), { title: "Why QpiAI Opt for scheduling, QAOA only for the small QUBO" }),
    detailsList([
      { title: "How it works", summary: "The same instances go through every solver via one interface (solvers.solve).", body: bullets(["Wave-selection instances grow from 6 to 16 variables.", "QAOA (QpiAI-QSV-Local) samples the p=1 circuit tuned on the numpy simulator.", "Schedule baselines are timed now; the MILP row is the recorded QpiAI Opt solve."]) },
      { title: "Evidence & sources", summary: `run ${b.run_id.slice(0, 12)} · ${b.ts}${P.ledger_index !== null ? ` · Proof Chain #${P.ledger_index}` : ""}`, body: bullets([`Python ${b.environment.python} on ${b.environment.machine}; numpy ${b.environment.numpy}; qpiai-opt ${b.environment.qpiai_opt}.`]) },
      { title: "Limits", summary: "Simulator-scale QAOA; hardware not run.", body: bullets([...b.limits, `Hardware: ${b.hardware}.`]) }]));
}

export async function mount(ctx) {
  await Promise.all([viewCss("pillars"), viewCss("plan")]);
  const labels3d = h("div", { class: "gr-labels", "aria-hidden": "true" }), note3d = h("div");
  const stageEl = stage(ctx, { label: "Measured benchmark values as bars", fallback: h("span") });
  stageEl.append(labels3d);
  const show3d = (P, tab) => {
    const items = benchItems(P, tab);
    note3d.replaceChildren(!items ? h("p", { class: "mv-note", text: tab === "crypto" ? "Key and signature sizes: not yet run (python -m bench.crypto)." : "Optimizer timings: not yet run (python -m bench)." })
      : dd(tab === "crypto" ? { shows: "One bar per primitive.", read: "Height is the measured public key plus signature (or ciphertext) bytes." }
        : { shows: `One bar per solver on the largest instance (${P.bench.instances.at(-1).n_variables} variables).`, read: "Height is the measured runtime on a log scale; taller is slower; a wireframe solver was not run." }));
    stageEl.hidden = !items;
    if (!items) { ctx.world.mount("bench", null); return; }
    mountScene(ctx, "bench", { available: true }, (env) => buildPillars(env, items, { labelsEl: labels3d, stageEl, reduced: ctx.world.reduced })).catch(() => {});
  };
  const ro = !ctx.wsInfo || ctx.wsInfo.read_only, canRun = ctx.me.role !== "viewer" && !ro;
  const runBtn = h("button", { class: "btn", type: "button", disabled: !canRun }, icon("play"), "Run benchmark");
  runBtn.addEventListener("click", async () => {
    if (!(await confirmDialog({ title: "Run the benchmark?", body: "Optimizers: exact, MILP (QpiAI Opt local, verifies the API key online), random, QAOA on both simulators and hybrid (about 2 minutes). Cryptography: TLS 1.3 handshakes on four lab services. Results are signed into the Proof Chain. No QpiAI credits are used.", confirm: "Run" }))) return;
    try {
      const r = await ctx.api.post(`/api/workspaces/${ctx.ws}/bench`, {});
      toast(`benchmark run ${r.run_id} started; follow it on the Overview page`, { tone: "info" });
    } catch (err) { toast(err.message, { tone: "error", detail: err.code }); }
  }, { signal: ctx.signal });
  let tab = ctx.query.get("tab") === "optimizers" ? "optimizers" : "crypto";
  const body = dataView(ctx, {
    keys: ["bench"],
    skeleton: () => tableSkeleton(8),
    render: ({ bench: P }) => {
      const panel = h("div", { role: "tabpanel", id: "bn-panel" });
      const tabs = h("div", { class: "tabs", role: "tablist", "aria-label": "Benchmark" });
      let draw = () => {
        tabs.replaceChildren(...[["crypto", "Cryptography"], ["optimizers", "Optimizers"]].map(([id, label]) => h("button", { class: "tab", type: "button", role: "tab", id: `tab-${id}`,
          "aria-selected": String(tab === id), "aria-controls": "bn-panel", tabindex: tab === id ? "0" : "-1", text: label,
          onclick: () => { tab = id; ctx.setQuery({ tab: id }); draw(); },
          onkeydown: (e) => { if (e.key === "ArrowRight" || e.key === "ArrowLeft") { tab = tab === "crypto" ? "optimizers" : "crypto"; ctx.setQuery({ tab }); draw(); tabs.querySelector('[aria-selected="true"]').focus(); } } })));
        panel.setAttribute("aria-labelledby", `tab-${tab}`);
        panel.replaceChildren(tab === "crypto" ? cryptoTab(ctx, P) : P.bench ? optimizerTab(ctx, P)
          : emptyState({ title: `Optimizer benchmark: ${P.status_text}`, body: "Run the benchmark to compare the optimizers on this workspace's plan.", action: null }));
      };
      const draw0 = draw;
      draw = () => { draw0(); show3d(P, tab); };
      draw();
      return h("div", {}, tabs, stageEl, note3d, panel, nextStep(ctx, "bench", { route: "review", text: "Next: review the steps" }));
    },
  });
  ctx.root.append(h("div", { class: "grid" }, h("div", { class: "span-12" },
    pageHead(ctx, { route: "bench", title: "Benchmark", headline: "What does post-quantum cryptography cost, and which optimizer fits which part of the plan?", actions: [runBtn] }),
    body, honesty())));
}
