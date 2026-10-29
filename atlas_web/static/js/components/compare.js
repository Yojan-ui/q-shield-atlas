// Classical vs quantum vs hybrid, from bench.json only: gap to the exact optimum and runtime against problem size,
// plus a scorecard. Wave-selection rows (small QUBO, Exact feasible) draw the charts; schedule_rows (FCFS / Greedy on
// the full plan) join the scorecard. QAOA is a simulator cross-check; no quantum advantage is claimed.
import { h } from "../dom.js";
import { chip } from "./chip.js";
import { table } from "./table.js";
import { dd } from "./dd.js";

const M = [
  ["fcfs", "FCFS", "classical", "#8C8C8C", "4 3"], ["greedy", "Greedy", "classical", "#A6A6A6", "4 3"], ["random", "Random", "classical", "#707070", "8 4"],
  ["milp", "MILP (QpiAI Opt)", "classical", "var(--pqc)", null], ["exact", "Exact", "classical", "#FFFFFF", null],
  ["qaoa1", "QAOA p=1 (numpy)", "quantum", "#D9D9D9", "2 3"], ["qaoa2", "QAOA p=2 (numpy)", "quantum", "#BDBDBD", "2 3"], ["qaoa3", "QAOA p=3 (numpy)", "quantum", "#9E9E9E", "2 3"],
  ["qaoa_sdk1", "QAOA p=1 (QpiAI-QSV-Local)", "quantum", "#C8C8C8", "1 3"], ["hybrid", "Hybrid (QAOA + repair)", "hybrid", "#E6E6E6", "6 2 1 2"],
].map(([key, label, family, color, dash]) => ({ key, label, family, color, dash }));
const FAM = { classical: "Classical", quantum: "Quantum (simulator)", hybrid: "Hybrid" };
const key = (r) => (/^qaoa/.test(r.solver) ? `${r.solver}${r.p}` : r.solver);
const secs = (x) => (x == null ? "–" : x < 0.01 ? `${(x * 1000).toFixed(2)} ms` : `${x.toFixed(2)} s`);
const gapOf = (r) => (r && r.status === "ok" && typeof r.approximation_ratio === "number" ? Math.max(0, 1 - r.approximation_ratio) : null);
const pct = (g) => (g == null ? "–" : `${(g * 100).toFixed(1)} %`);

function chart(lines, { title, log, fmt }) {
  const W = 560, H = 260, L = 64, R = 150, T = 12, B = 40;
  const pts = lines.flatMap((l) => l.pts);
  const xs = [...new Set(pts.map((p) => p.x))].sort((a, b) => a - b), x0 = xs[0], x1 = xs.at(-1);
  const ys = pts.map((p) => p.y).filter((y) => (log ? y > 0 : true));
  const lo = log ? Math.floor(Math.log10(Math.min(...ys))) : 0, hi = log ? Math.ceil(Math.log10(Math.max(...ys))) : Math.max(1, ...ys);
  const X = (x) => L + ((x - x0) / Math.max(1, x1 - x0)) * (W - L - R);
  const Y = (y) => T + (1 - (log ? (Math.log10(y) - lo) / Math.max(1, hi - lo) : y / hi)) * (H - T - B);
  const svg = h("svg", { viewBox: `0 0 ${W} ${H}`, class: "bn-chart", role: "img", "aria-label": title });
  for (const t of log ? Array.from({ length: hi - lo + 1 }, (_, i) => 10 ** (lo + i)) : [0, hi / 2, hi])
    svg.append(h("line", { ns: "svg", x1: L, x2: W - R, y1: Y(t), y2: Y(t), class: "bn-grid" }), h("text", { ns: "svg", x: L - 6, y: Y(t) + 4, class: "bn-tick", "text-anchor": "end" }, fmt(t)));
  for (const x of xs) svg.append(h("text", { ns: "svg", x: X(x), y: H - B + 18, class: "bn-tick", "text-anchor": "middle" }, String(x)));
  svg.append(h("text", { ns: "svg", x: (L + W - R) / 2, y: H - 4, class: "bn-axis", "text-anchor": "middle" }, "problem size (variables)"));
  const ends = [];
  for (const l of lines) {
    const p = l.pts.filter((q) => !log || q.y > 0);
    if (!p.length) continue;
    svg.append(h("polyline", { ns: "svg", points: p.map((q) => `${X(q.x)},${Y(q.y)}`).join(" "), class: "bn-line", stroke: l.m.color, "stroke-dasharray": l.m.dash, "stroke-width": l.m.key === "milp" ? 3 : 2 }));
    for (const q of p) svg.append(h("circle", { ns: "svg", cx: X(q.x), cy: Y(q.y), r: l.m.key === "milp" && !log && q.y === 0 ? 6 : 4, fill: l.m.key === "milp" && !log && q.y === 0 ? "none" : l.m.color, stroke: l.m.color, "stroke-width": 2 },
      h("title", { ns: "svg" }, `${l.m.label} · ${q.x} variables: ${fmt(q.y)}`)));
    ends.push({ y: Y(p.at(-1).y) + 4, x: X(p.at(-1).x) + 8, text: l.m.label.split(" (")[0] });
  }
  // lines ending at the same point share one label; labels 18 px apart, kept inside the plot
  const groups = [];
  for (const e of ends.sort((a, b) => a.y - b.y)) { const g = groups.find((x) => Math.abs(x.y - e.y) < 1 && x.x === e.x); if (g) g.n.push(e.text); else groups.push({ ...e, n: [e.text] }); }
  groups.forEach((g, i) => { if (i && g.y - groups[i - 1].y < 18) g.y = groups[i - 1].y + 18; });
  for (let i = groups.length - 1; i >= 0; i--) groups[i].y = Math.min(groups[i].y, i === groups.length - 1 ? H - B + 4 : groups[i + 1].y - 18);
  for (const g of groups) svg.append(h("text", { ns: "svg", x: g.x, y: g.y, class: "bn-label" }, g.n.length > 2 ? `${g.n.length} methods` : g.n.join(" = ")));
  return h("figure", { class: "cmp-fig" }, h("figcaption", { class: "pl-h3", text: title }), svg);
}

// P = bench payload ({bench, ledger_index}); returns null when no benchmark exists
export function compareBlock(ctx, P) {
  const b = P && P.bench;
  if (!b || !b.rows || !b.instances || !b.instances.length) return null;
  const big = b.instances.at(-1);
  const ok = b.rows.filter((r) => r.status === "ok");
  const lines = M.map((m) => ({ m, rows: ok.filter((r) => key(r) === m.key).sort((x, y) => x.n_variables - y.n_variables) })).filter((l) => l.rows.length);
  const sched = (b.schedule_rows || []).filter((r) => ["fcfs", "greedy"].includes(r.solver));
  const card = [...lines.map((l) => ({ m: l.m, rows: l.rows, last: l.rows.find((r) => r.instance === big.id) || l.rows.at(-1), problem: "wave selection (QUBO)" })),
    ...sched.map((r) => ({ m: M.find((x) => x.key === r.solver), rows: [r], last: r, problem: `full schedule (${r.n_variables ?? "–"} binary variables)` }))]
    .sort((x, y) => Object.keys(FAM).indexOf(x.m.family) - Object.keys(FAM).indexOf(y.m.family));
  const at = (k) => ok.find((r) => r.instance === big.id && key(r) === k);
  const q = at("qaoa1"), ex = at("exact"), hits = b.instances.filter((i) => gapOf(ok.find((r) => r.instance === i.id && key(r) === "qaoa1")) === 0).length;
  const legend = h("ul", { class: "bn-legend cmp-legend", "aria-label": "Chart legend" }, Object.entries(FAM).map(([f, name]) => h("li", {}, h("b", { text: `${name}: ` }),
    lines.filter((l) => l.m.family === f).map((l) => h("span", { class: "cmp-key" }, h("svg", { viewBox: "0 0 24 8", class: "bn-key", "aria-hidden": "true" },
      h("line", { ns: "svg", x1: 0, y1: 4, x2: 24, y2: 4, stroke: l.m.color, "stroke-width": 2, "stroke-dasharray": l.m.dash })), l.m.label)))));
  return h("div", { class: "cmp" },
    h("div", { class: "cmp-charts" },
      chart(lines.map((l) => ({ m: l.m, pts: l.rows.map((r) => ({ x: r.n_variables, y: (gapOf(r) ?? 0) * 100 })) })), { title: "Gap to exact optimum (%, 0 = optimal)", fmt: (y) => `${+y.toFixed(1)} %` }),
      chart(lines.map((l) => ({ m: l.m, pts: l.rows.map((r) => ({ x: r.n_variables, y: r.runtime_s })) })), { title: "Runtime (log scale)", log: true, fmt: (y) => (y >= 1 ? `${y} s` : `${+(y * 1000).toPrecision(3)} ms`) })),
    legend,
    q && ex ? h("p", { class: "cmp-line" }, chip("assumption", "simulation"), ` QAOA p=1 hit the exact optimum on ${hits} of ${b.instances.length} instances; at ${big.n_variables} variables it took ${secs(q.runtime_s)} vs ${secs(ex.runtime_s)} for Exact. Cross-check only, no quantum advantage.`) : null,
    table({ caption: "Classical vs quantum vs hybrid", rows: card,
      expand: (c) => ({ why: `${c.problem}; ${c.rows.length} size${c.rows.length === 1 ? "" : "s"} measured.`, run_id: b.run_id, ts: b.ts,
        technical: c.rows.map((r) => `${r.n_variables} vars: objective ${r.objective == null ? "–" : (+r.objective).toFixed(4)}, ${secs(r.runtime_s)}`).join(" · ") }), columns: [
        { label: "method", render: (c) => c.m.label },
        { label: "family", optional: true, render: (c) => FAM[c.m.family] },
        { label: "optimal?", render: (c) => (c.rows.every((r) => gapOf(r) === 0) ? chip("PASS", "optimal") : chip("partially_verified", "not always")) },
        { label: "gap at largest", numeric: true, sort: (c) => gapOf(c.last) ?? 9, render: (c) => pct(gapOf(c.last)) },
        { label: "runtime", numeric: true, optional: true, sort: (c) => c.last.runtime_s ?? 1e9, render: (c) => secs(c.last.runtime_s) }] }),
    dd({ shows: "Every solver on the same benchmark instances.", read: "Wave-selection instances (where brute-force Exact is feasible) draw the charts; FCFS and Greedy are measured on the full schedule against the MILP optimum. Runtimes include simulating QAOA on a classical computer.",
      source: `python -m bench, run ${b.run_id}, ${b.ts}${P.ledger_index != null ? `, Proof Chain #${P.ledger_index}` : ""}` }));
}

export function runBench(ctx) {
  return h("a", { class: "btn primary", href: `/w/${ctx.ws}/bench?tab=optimizers`, text: "Run benchmark" });
}
