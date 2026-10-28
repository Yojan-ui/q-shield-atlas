// 404: a single broken lattice cell drifting in the void (Stage 4 renders it in 3D).
import { h } from "../dom.js";

export function brokenCell() {
  const svg = h("svg", { class: "scene-mark", viewBox: "0 0 160 160", fill: "none", stroke: "currentColor", "stroke-width": "1.2", "aria-hidden": "true" });
  svg.innerHTML = '<path d="M80 22 130 50v58l-50 30-50-30V50z"/><path d="M30 50l50 28 50-28M80 78v60" stroke-dasharray="3 4"/>'
    + '<path class="crack" stroke="currentColor" d="M94 30 86 52l10 10-12 18 8 14"/>';
  return svg;
}

export async function mount(ctx) {
  ctx.root.append(h("div", { class: "grid" }, h("div", { class: "span-7" }, h("p", { class: "eyebrow", text: "404 · not in the lattice" }),
    h("h1", { text: "This cell is broken." }), h("p", { class: "lede", text: `Nothing lives at ${location.pathname}. It may have been a deep link to a workspace that no longer exists.` }),
    h("div", { class: "sg-row", style: { marginTop: "var(--s-5)" } }, h("a", { class: "btn primary", href: ctx.me ? `/w/${ctx.ws}/pipeline` : "/", text: ctx.me ? "Back to the pipeline" : "Back to the start" }))),
    h("div", { class: "start-9" }, brokenCell())));
  ctx.announce("Page not found.");
}
