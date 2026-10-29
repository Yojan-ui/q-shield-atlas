// Data table: sticky header, tabular numerals, sortable columns (click a header), row links, virtualised beyond 200 rows.
import { h } from "../dom.js";
import { provAttr } from "./tooltip.js";

const ROW_H = 40, VIRTUAL_AT = 200, OVERSCAN = 8;

function cellNode(col, row) {
  const v = col.render ? col.render(row) : row[col.key];
  if (v instanceof Node) return v;
  if (v && typeof v === "object" && v.kind) {
    if (v.kind === "number") return h("span", { class: "num", tabindex: "0", "data-prov": provAttr(v.source, col.label), text: v.text });
    return h("span", { class: "fine", text: v.text });
  }
  return document.createTextNode(v === null || v === undefined ? "–" : String(v));
}

function sortValue(col, row) {
  if (col.sort) return col.sort(row);
  let v = col.key ? row[col.key] : col.render ? col.render(row) : null;
  if (v instanceof Node) v = v.textContent;
  if (v && typeof v === "object" && v.kind) v = v.kind === "number" ? v.value : v.text;
  const n = typeof v === "string" ? Number(v.replace(/[,%\s]|ms$|s$/g, "")) : v;
  return typeof v === "number" ? v : Number.isFinite(n) && v !== "" ? n : String(v ?? "").toLowerCase();
}

export function table(opts) {
  const outer = h("div", { class: "table-outer" });
  let state = { i: -1, dir: 1 };
  const build = () => {
    const col = opts.columns[state.i];
    const rows = col ? [...opts.rows].sort((a, b) => { const x = sortValue(col, a), y = sortValue(col, b); return (x < y ? -1 : x > y ? 1 : 0) * state.dir; }) : opts.rows;
    outer.replaceChildren(rawTable({ ...opts, rows, sortState: state, onSort: (i) => { state = { i, dir: state.i === i ? -state.dir : 1 }; build(); } }));
  };
  build();
  return outer;
}

function rawTable({ columns, rows, caption, onRow = null, rowHref = null, empty = "No rows", signal = null, sortState = null, onSort = null }) {
  const cls = (c) => [c.numeric ? "n" : "", c.mono ? "mono" : "", c.optional ? "opt" : ""].join(" ").trim() || null;
  const thead = h("thead", {}, h("tr", {}, columns.map((c, i) => {
    const on = sortState && sortState.i === i;
    return h("th", { scope: "col", class: cls(c), "aria-sort": on ? (sortState.dir > 0 ? "ascending" : "descending") : null },
      onSort && rows.length > 1 && c.sortable !== false ? h("button", { class: "th-sort", type: "button", onclick: () => onSort(i) }, c.label, h("span", { class: "th-dir", "aria-hidden": "true", text: on ? (sortState.dir > 0 ? " ↑" : " ↓") : "" })) : c.label);
  })));
  const tbody = h("tbody");
  const tbl = h("table", { class: "data" }, caption ? h("caption", { class: "sr-only", text: caption }) : null, thead, tbody);
  const wrap = h("div", { class: `table-wrap${rows.length > VIRTUAL_AT ? " virtual" : ""}`, tabindex: rows.length > 12 ? "0" : null,
    role: rows.length > 12 ? "region" : null, "aria-label": rows.length > 12 ? caption || "table" : null }, tbl);
  const rowNode = (row) => {
    const tr = h("tr", { class: onRow || rowHref ? "clickable" : "" }, columns.map((c) => h("td", { class: cls(c) }, cellNode(c, row))));
    if (rowHref) {
      const first = tr.querySelector("td");
      const a = h("a", { href: rowHref(row) }, ...first.childNodes);
      first.replaceChildren(a);
      tr.addEventListener("click", (e) => { if (!(e.target instanceof Element && e.target.closest("a, button, .num"))) a.click(); }, signal ? { signal } : undefined);
    } else if (onRow) tr.addEventListener("click", () => onRow(row), signal ? { signal } : undefined);
    return tr;
  };
  if (!rows.length) {
    tbody.append(h("tr", {}, h("td", { colspan: String(columns.length), class: "fine", text: empty })));
  } else if (rows.length <= VIRTUAL_AT) {
    tbody.append(...rows.map(rowNode));
  } else {
    let first = -1;
    const draw = () => {
      const top = Math.max(0, Math.floor(wrap.scrollTop / ROW_H) - OVERSCAN);
      if (top === first) return;
      first = top;
      const count = Math.ceil(wrap.clientHeight / ROW_H) + OVERSCAN * 2;
      const end = Math.min(rows.length, top + count);
      const pad = (px) => h("tr", { class: "spacer", "aria-hidden": "true" }, h("td", { colspan: String(columns.length), style: { height: `${px}px` } }));
      tbody.replaceChildren(pad(top * ROW_H), ...rows.slice(top, end).map(rowNode), pad((rows.length - end) * ROW_H));
    };
    wrap.addEventListener("scroll", () => requestAnimationFrame(draw), { passive: true, ...(signal ? { signal } : {}) });
    requestAnimationFrame(draw);
    draw();
    wrap.dataset.virtual = String(rows.length);
  }
  return wrap;
}

export function tableSkeleton(cols = 4, n = 6) {
  return h("div", { class: "table-wrap", "aria-hidden": "true" }, h("table", { class: "data" },
    h("thead", {}, h("tr", {}, Array.from({ length: cols }, () => h("th", {}, h("span", { class: "skel line", style: { width: "50%" } }))))),
    h("tbody", {}, Array.from({ length: n }, () => h("tr", {}, Array.from({ length: cols }, () => h("td", {}, h("span", { class: "skel line", style: { width: "70%" } }))))))));
}
