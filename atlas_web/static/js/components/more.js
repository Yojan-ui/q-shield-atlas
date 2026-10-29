// "<label> ▾" disclosure: button (aria-expanded) + panel, opens in 200 ms
import { h } from "../dom.js";

export function more(label, ...kids) {
  const id = `mo${Math.random().toString(36).slice(2)}`;
  const btn = h("button", { class: "why-btn", type: "button", "aria-expanded": "false", "aria-controls": id }, `${label} ▾`);
  const panel = h("div", { class: "why-panel", id, hidden: true }, h("div", { class: "why-inner" }, ...kids));
  btn.addEventListener("click", () => {
    const open = btn.getAttribute("aria-expanded") !== "true";
    btn.setAttribute("aria-expanded", String(open)); btn.textContent = `${label} ${open ? "▴" : "▾"}`;
    panel.hidden = !open; if (open) requestAnimationFrame(() => panel.classList.add("on")); else panel.classList.remove("on");
  });
  return [btn, panel];
}
