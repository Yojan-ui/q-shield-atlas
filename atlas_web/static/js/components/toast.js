// Toasts: aria-live polite region, auto-dismiss, error / success / info.
import { h, icon } from "../dom.js";

let region = null;
export function installToasts() {
  region = h("div", { class: "toasts", role: "status", "aria-live": "polite" });
  document.body.append(region);
}
export function toast(message, { tone = "info", detail = "", ms = 5000 } = {}) {
  if (!region) installToasts();
  if (tone === "error" && typeof window !== "undefined") (window.__atlasErrors ||= []).push(`toast: ${message}${detail ? ` (${detail})` : ""}`);
  const close = h("button", { class: "copy", type: "button", "aria-label": "dismiss" }, icon("cross"));
  const t = h("div", { class: `toast ${tone}` }, icon(tone === "error" ? "warn" : tone === "success" ? "check" : "info"),
    h("div", { class: "t-body" }, message, detail ? h("small", { text: detail }) : null), close);
  const remove = () => { t.classList.add("leaving"); setTimeout(() => t.remove(), 180); };
  close.addEventListener("click", remove);
  region.append(t);
  if (ms) setTimeout(remove, ms);
  return t;
}
