// Data table: sticky header, tabular numerals, row links, virtualised beyond 200 rows (fixed 40 px rows).
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

export function table({ columns, rows, caption, onRow = null, rowHref = null, empty = "No rows", signal = null }) {
  const cls = (c) => [c.numeric ? "n" : "", c.mono ? "mono" : "", c.optional ? "opt" : ""].join(" ").trim() || null;
  const thead = h("thead", {}, h("tr", {}, columns.map((c) => h("th", { scope: "col", class: cls(c), text: c.label }))));
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
