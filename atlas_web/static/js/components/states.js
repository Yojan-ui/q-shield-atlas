// Empty, error and loading states. Each mirrors the final layout so nothing shifts when data arrives.
import { h, icon } from "../dom.js";

export function emptyState({ title, body, action = null }) {
  return h("div", { class: "state empty" }, icon("lattice", "mark"), h("h2", { text: title }), h("p", { text: body }), action ? h("div", { class: "actions" }, action) : null);
}
export function errorState({ title = "Could not load this view", error, onRetry }) {
  const retry = onRetry ? h("button", { class: "btn", type: "button", onclick: onRetry, text: "Retry" }) : null;
  return h("div", { class: "state error", role: "alert" }, icon("warn", "mark"), h("h2", { text: title }),
    h("p", { text: error && error.message ? error.message : String(error || "unknown error") }), retry ? h("div", { class: "actions" }, retry) : null);
}
export function lines(n = 3) {
  return h("div", { "aria-hidden": "true" }, Array.from({ length: n }, (_, i) => h("span", { class: "skel line", style: { width: `${90 - i * 15}%` } })));
}
