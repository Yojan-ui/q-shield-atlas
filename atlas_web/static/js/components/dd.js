// one "Details ▾" disclosure per section (closed): what a visual shows, how to read it, where the data comes from
import { h } from "../dom.js";

export function dd({ shows = null, read = null, source = null } = {}) {
  const row = (k, v) => (v ? h("p", {}, h("b", { text: `${k}: ` }), v) : null);
  return h("details", { class: "dd" }, h("summary", {}, "Details ▾"), h("div", { class: "dd-body" }, row("What it shows", shows), row("How to read it", read), row("Source", source)));
}
