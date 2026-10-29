// Tiny DOM helpers. No framework: views build nodes with h() and own their listeners via an AbortSignal.
export function h(tag, attrs = {}, ...kids) {
  const el = tag === "svg" || attrs.ns === "svg" ? document.createElementNS("http://www.w3.org/2000/svg", tag) : document.createElement(tag);
  for (const [k, v] of Object.entries(attrs || {})) {
    if (v === null || v === undefined || v === false || k === "ns") continue;
    if (k === "class") el.setAttribute("class", v);
    else if (k === "text") el.textContent = v;
    else if (k === "style" && typeof v === "object") Object.assign(el.style, v);
    else if (k.startsWith("on") && typeof v === "function") el.addEventListener(k.slice(2), v);
    else if (k === "dataset") Object.assign(el.dataset, v);
    else el.setAttribute(k, v === true ? "" : String(v));
  }
  append(el, kids);
  return el;
}

export function append(el, kids) {
  for (const k of kids.flat(Infinity)) {
    if (k === null || k === undefined || k === false) continue;
    el.append(k instanceof Node ? k : document.createTextNode(String(k)));
  }
  return el;
}

// Inline SVG icons (stroke = currentColor). Every status icon pairs with text: never colour alone.
const PATHS = {
  check: "M3 8.5 6.5 12 13 4.5",
  cross: "M4 4l8 8M12 4l-8 8",
  warn: "M8 2.5 14.5 13.5h-13zM8 6.5v3.2M8 11.6v.4",
  dash: "M3 8h10",
  ring: "M8 2.5a5.5 5.5 0 1 1 0 11 5.5 5.5 0 0 1 0-11z",
  dotted: "M8 2.5a5.5 5.5 0 1 1 0 11 5.5 5.5 0 0 1 0-11z",
  rewind: "M7 4 3 8l4 4M13 4 9 8l4 4",
  info: "M8 2.5a5.5 5.5 0 1 1 0 11 5.5 5.5 0 0 1 0-11zM8 7v4M8 5v.3",
  copy: "M5.5 5.5h7v7h-7zM3.5 10.5v-7h7",
  play: "M5 3.5v9l7-4.5z",
  arrow: "M3 8h10M9 4l4 4-4 4",
  lock: "M4.5 7.5h7v6h-7zM6 7.5V5.5a2 2 0 0 1 4 0v2",
  spin: "M8 2.5a5.5 5.5 0 1 0 5.5 5.5",
  lattice: "M2 5l6-3 6 3v6l-6 3-6-3zM2 5l6 3 6-3M8 8v6",
  chevron: "M4 6l4 4 4-4",
};
export function icon(name, cls = "") {
  const svg = h("svg", { viewBox: "0 0 16 16", fill: "none", stroke: "currentColor", "stroke-width": "1.5",
    "stroke-linecap": "round", "stroke-linejoin": "round", "aria-hidden": "true", focusable: "false", class: cls });
  const p = h("path", { ns: "svg", d: PATHS[name] || PATHS.dash });
  if (name === "dotted") p.setAttribute("stroke-dasharray", "2 2");
  svg.append(p);
  return svg;
}

export function clear(el) { el.replaceChildren(); return el; }

// Stagger children in with the overlay motion token (CSS .enter + --i).
export function stagger(container) {
  [...container.children].forEach((c, i) => c.style.setProperty("--i", String(i)));
  container.classList.add("enter");
  return container;
}
