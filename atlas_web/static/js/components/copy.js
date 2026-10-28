// Hash with copy-to-clipboard and a tick confirmation.
import { h, icon } from "../dom.js";

export function hashCopy(value, { short = 12, label = "hash" } = {}) {
  const btn = h("button", { class: "copy", type: "button", "aria-label": `copy ${label}` }, icon("copy"));
  btn.addEventListener("click", async (e) => {
    e.stopPropagation();
    let ok = false;
    try { await navigator.clipboard.writeText(value); ok = true; } catch { ok = false; }
    btn.replaceChildren(icon(ok ? "check" : "cross"));
    btn.classList.toggle("done", ok);
    btn.setAttribute("aria-label", ok ? `${label} copied` : `copy failed; select the ${label} manually`);
    setTimeout(() => { btn.replaceChildren(icon("copy")); btn.classList.remove("done"); btn.setAttribute("aria-label", `copy ${label}`); }, 1500);
  });
  const text = value && value.length > short * 2 ? `${value.slice(0, short)}…${value.slice(-4)}` : value;
  return h("span", { class: "hash", title: value }, h("span", { text }), btn);
}
