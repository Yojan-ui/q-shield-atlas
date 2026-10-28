// 2D view (default): vanilla DOM + SVG, rendered only from the display model built by data.js.
const SVG = "http://www.w3.org/2000/svg";
const STATUS_COLOR = {
  applied: "var(--applied)", partially_verified: "var(--partial)", rolled_back: "var(--rolled)",
  rollback_failed: "var(--failed)", not_verified_in_lab: "var(--unverified)", planned: "var(--planned)",
};
const PLAN_STYLE = { optimized: ["var(--opt)", ""], fcfs: ["var(--fcfs)", "6 4"], greedy: ["var(--greedy)", "2 3"] };

export function sourceText(s) {
  if (!s) return "";
  return [`run_id: ${s.run_id}`, `solver/backend: ${s.solver}`, `job_id: ${s.job_id}`, `timestamp: ${s.ts}`, s.note ? `note: ${s.note}` : ""]
    .filter(Boolean).join("\n");
}

function el(tag, attrs = {}, ...kids) {
  const e = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (k === "class") e.className = v; else if (k === "text") e.textContent = v; else e.setAttribute(k, v);
  }
  for (const k of kids) if (k !== null && k !== undefined) e.append(k);
  return e;
}

function s(tag, attrs = {}) {
  const e = document.createElementNS(SVG, tag);
  for (const [k, v] of Object.entries(attrs)) e.setAttribute(k, v);
  return e;
}

// A number cell -> span with tooltip source; a missing/status cell -> muted text, never 0.
export function cellNode(cell) {
  if (!cell) return el("span", { class: "missing", text: "not yet run" });
  if (cell.kind === "number") return el("span", { class: "num", "data-src": sourceText(cell.source), tabindex: "0", text: cell.text });
  return el("span", { class: cell.kind === "status" ? "status" : "missing", text: cell.text });
}

function card(title, ...kids) {
  return el("div", { class: "card" }, el("h2", { text: title }), ...kids);
}

function chartPanel(chart, scenario, waves) {
  const W = 360, H = 220, L = 46, R = 10, T = 18, B = 40;
  const vals = chart.plans.flatMap((p) => p.series[scenario.name].map((pt) => pt.cell.value));
  const ymax = Math.max(...vals) || 1;
  const wmax = chart.weeks[chart.weeks.length - 1] || 1;
  const x = (w) => L + ((W - L - R) * w) / wmax;
  const y = (v) => T + (H - T - B) * (1 - v / ymax);
  const svg = s("svg", { viewBox: `0 0 ${W} ${H}`, role: "img", "aria-label": `Remaining exposure-years per week, ${scenario.name}` });
  svg.append(s("line", { x1: L, y1: H - B, x2: W - R, y2: H - B, stroke: "var(--line)" }));
  svg.append(s("line", { x1: L, y1: T, x2: L, y2: H - B, stroke: "var(--line)" }));
  for (const w of chart.weeks) {
    const t = s("text", { x: x(w), y: H - B + 14, "text-anchor": "middle" }); t.textContent = w; svg.append(t);
  }
  const xl = s("text", { x: (L + W - R) / 2, y: H - 4, "text-anchor": "middle" }); xl.textContent = "week"; svg.append(xl);
  const yl = s("text", { x: L + 6, y: T - 6 }); yl.textContent = "exposure-years remaining"; svg.append(yl);
  const peak = chart.plans.flatMap((p) => p.series[scenario.name]).reduce((a, b) => (b.cell.value > a.cell.value ? b : a));
  const top = s("text", { x: L - 4, y: y(ymax) + 4, "text-anchor": "end" }); top.textContent = peak.cell.text; svg.append(top);
  for (const plan of chart.plans) {
    const [color, dash] = PLAN_STYLE[plan.key];
    const pts = plan.series[scenario.name];
    svg.append(s("polyline", { points: pts.map((p) => `${x(p.week)},${y(p.cell.value)}`).join(" "), fill: "none", stroke: color, "stroke-width": 2, "stroke-dasharray": dash }));
    for (const p of pts) {
      const c = s("circle", { cx: x(p.week), cy: y(p.cell.value), r: 3.2, fill: color, "data-src": `${plan.label}, ${scenario.name}, week ${p.week}: ${p.cell.text} exposure-years\n${sourceText(p.cell.source)}`, tabindex: "0" });
      svg.append(c);
    }
  }
  for (const w of waves) {
    const m = s("rect", { x: x(w.week) - 5, y: H - B + 20, width: 10, height: 8, rx: 2, fill: STATUS_COLOR[w.status] || "var(--planned)",
      "data-src": `wave week ${w.week}: ${w.status}\n${w.assets.map((a) => `${a}: ${(w.asset_status || {})[a] || w.status}`).join("\n")}\n${sourceText(w.source)}`, tabindex: "0" });
    svg.append(m);
  }
  return el("div", {}, el("h3", { text: `${scenario.name} (CRQC in ${scenario.year})` }), svg);
}

function chartCard(m) {
  if (!m.chart.available) return el("div", { class: "card wide" }, el("h2", { text: "Remaining exposure-years per week" }), cellNode(null));
  const legend = el("div", { class: "legend" },
    ...m.chart.plans.map((p) => el("span", {}, el("span", { class: "sw", style: `border-top-color:${PLAN_STYLE[p.key][0]};border-top-style:${PLAN_STYLE[p.key][1] ? "dashed" : "solid"}` }), p.label)),
    ...Object.entries(STATUS_COLOR).filter(([k]) => m.waves.some((w) => w.status === k))
      .map(([k, c]) => el("span", {}, el("span", { class: "dot", style: `background:${c}` }), `wave: ${k.replaceAll("_", " ")}`)));
  return el("div", { class: "card wide" }, el("h2", { text: "Remaining exposure-years per week: optimised plan vs FCFS vs greedy" }),
    el("div", { class: "panels" }, ...m.chart.scenarios.map((sc) => chartPanel(m.chart, sc, m.waves))), legend,
    el("p", { class: "fine", text: "Remaining at week k = summed (unweighted) exposure-years of assets whose planned completion is after week k. The optimiser minimises the risk-weighted, scenario-weighted total, so its unweighted curve can sit above a baseline in some weeks; see the avoided-exposure card for the totals. Squares under the axis are waves, coloured by lab-gate status." }));
}

function avoidedCard(m) {
  if (!m.avoided) return card("Exposure-years avoided", cellNode(null));
  const rows = m.avoided.map((a) => el("tr", {}, el("td", { text: `vs ${a.baseline}` }), el("td", { text: a.scenario }), el("td", {}, cellNode(a.cell)), el("td", {}, cellNode(a.weighted))));
  return card("Exposure-years avoided by the optimised plan",
    el("div", { class: "tbl" }, el("table", {}, el("thead", {}, el("tr", {}, ...["baseline", "scenario", "exposure-years", "risk-weighted"].map((h) => el("th", { text: h })))), el("tbody", {}, ...rows))));
}

function ledgerCard(m) {
  const l = m.ledger;
  if (!l.available) return card("Evidence ledger", cellNode(null));
  return card("Evidence ledger (ML-DSA-65, local test ledger)",
    el("div", { class: "kv" },
      el("span", { text: "root" }), el("code", { "data-src": `${l.root}\n${sourceText(l.source)}`, tabindex: "0", class: "num", text: l.root_short }),
      el("span", { text: "entries" }), cellNode(l.entries),
      el("span", { text: "verified" }), el("span", { class: l.verified.symbol === "✔" ? "PASS" : l.verified.symbol === "✖" ? "FAIL" : "missing", text: `${l.verified.symbol} ${l.verified.text}`.trim() })));
}

function handshakeCard(m) {
  const h = m.handshake;
  if (!h.available) return card("TLS handshake evidence", cellNode(null));
  const rows = h.rows.map((r) => el("tr", { "data-src": sourceText(r.source), tabindex: "0" },
    el("td", { text: r.service }),
    el("td", {}, el("div", { text: r.kex_group }), r.hndl_label ? el("div", { class: "hndl", text: r.hndl_label }) : null),
    el("td", { class: r.kex_gate, text: r.kex_gate }),
    el("td", { text: r.auth_alg }),
    el("td", { class: r.auth_gate, text: r.auth_gate })));
  return el("div", { class: "card wide" }, el("h2", { text: "TLS 1.3 handshake evidence (lab services)" }),
    el("div", { class: "tbl" }, el("table", {}, el("thead", {}, el("tr", {}, ...["service", "key exchange", "pq_handshake", "authentication", "pq_auth"].map((t) => el("th", { text: t })))), el("tbody", {}, ...rows))),
    el("p", { class: "fine", text: h.note }));
}

function qaoaCard(m) {
  const q = m.qaoa;
  if (!q.available) return el("div", { class: "card wide" }, el("h2", { text: `QAOA (${q.label})` }), cellNode(null));
  const head = el("tr", {}, el("th", { text: "p" }), el("th", { text: "source" }), ...q.columns.map(([, label]) => el("th", { text: label })));
  const rows = q.rows.map((r) => {
    const lead = [el("td", { text: r.p === null ? "–" : String(r.p) }), el("td", { "data-src": sourceText(r.source), tabindex: "0", class: "num", text: r.source_kind })];
    if (r.status_cell) return el("tr", {}, ...lead, el("td", { colspan: String(q.columns.length) }, cellNode(r.status_cell)));
    return el("tr", {}, ...lead, ...q.columns.map(([k]) => el("td", {}, cellNode(r.cells[k]))));
  });
  return el("div", { class: "card wide" }, el("h2", { text: `QAOA wave selection: ${q.label}` }),
    el("p", { class: "fine" }, "Exact optimum (brute force): objective ", cellNode(q.exact.objective), `, assets ${q.exact.assets.join(", ")}`),
    el("div", { class: "tbl" }, el("table", {}, el("thead", {}, head), el("tbody", {}, ...rows))),
    el("p", { class: "fine", text: q.full_label }));
}

export function render2d(root, m) {
  root.replaceChildren(el("div", { class: "grid" }, chartCard(m), avoidedCard(m), ledgerCard(m), handshakeCard(m), qaoaCard(m)));
}

// Hover/tap tooltips for anything with data-src.
export function installTooltips(tip) {
  let pinned = null;
  const show = (t, x, y) => {
    tip.textContent = t; tip.hidden = false;
    const w = tip.offsetWidth, h = tip.offsetHeight;
    tip.style.left = `${Math.min(x + 12, window.innerWidth - w - 8)}px`;
    tip.style.top = `${Math.min(y + 12, window.innerHeight - h - 8)}px`;
  };
  const target = (e) => e.target.closest && e.target.closest("[data-src]");
  document.addEventListener("mousemove", (e) => { if (pinned) return; const t = target(e); if (t) show(t.getAttribute("data-src"), e.clientX, e.clientY); else tip.hidden = true; });
  document.addEventListener("click", (e) => { const t = target(e); if (t) { pinned = t; show(t.getAttribute("data-src"), e.clientX, e.clientY); } else { pinned = null; tip.hidden = true; } });
  document.addEventListener("focusin", (e) => { const t = target(e); if (t) { const r = t.getBoundingClientRect(); show(t.getAttribute("data-src"), r.left, r.bottom); } });
  document.addEventListener("focusout", () => { if (!pinned) tip.hidden = true; });
}
