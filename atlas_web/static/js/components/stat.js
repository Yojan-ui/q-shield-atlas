// Stat block: eyebrow label, large tabular value that rolls when it changes, unit, provenance.
import { h, icon } from "../dom.js";
import { rollNumber } from "../motion.js";
import { provAttr } from "./tooltip.js";

export function stat({ label, cell, unit = "", tone = "", title = "" }) {
  const value = h("span", { class: "value" });
  const prov = h("button", { class: "prov", type: "button", "aria-label": `source of ${label}` }, icon("info"));
  const el = h("div", { class: `stat ${tone}` }, h("span", { class: "label" }, label, prov), h("div", {}, value, unit ? h("div", { class: "unit", text: unit }) : null));
  el.update = (c) => {
    if (c && c.kind === "number") {
      value.classList.remove("missing");
      prov.hidden = false;
      prov.setAttribute("data-prov", provAttr(c.source, title || label));
      value.setAttribute("aria-label", `${label}: ${c.text}${unit ? ` ${unit}` : ""}`);
      rollNumber(value, c.value, c.digits ?? (c.text.split(".")[1] || "").length);
    } else {
      value.classList.add("missing");
      value._value = undefined;
      value.textContent = (c && c.text) || "not yet run";
      value.removeAttribute("aria-label");
      prov.hidden = true;
      prov.removeAttribute("data-prov");
    }
  };
  el.update(cell);
  return el;
}

export function stats(items) { return h("div", { class: "stats" }, items.map(stat)); }

export function statSkeleton(n = 4) {
  return h("div", { class: "stats", "aria-hidden": "true" }, Array.from({ length: n }, () =>
    h("div", { class: "stat" }, h("span", { class: "skel line", style: { width: "40%" } }), h("span", { class: "skel value" }))));
}
