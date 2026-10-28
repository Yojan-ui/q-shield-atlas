// 404: a single broken lattice cell drifting in the void (Stage 4 renders it in 3D).
import { h } from "../dom.js";
import { mountScene, stage } from "./common.js";

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
    h("div", { class: "start-9" }, brokenCell()), h("div", { class: "span-12" }, stage(ctx, { label: "A single broken lattice cell drifting in the void." }))));
  mountScene(ctx, "void", { available: true }, ({ THREE, group }) => {
    const box = new THREE.EdgesGeometry(new THREE.BoxGeometry(2.2, 2.2, 2.2));
    const cell = new THREE.LineSegments(box, new THREE.LineBasicMaterial({ color: 0x5ce1e6, transparent: true, opacity: 0.55 }));
    const crack = new THREE.Line(new THREE.BufferGeometry().setFromPoints([[0.2, 1.1, 1.1], [-0.1, 0.4, 1.1], [0.25, -0.1, 1.1], [-0.15, -0.7, 1.1]].map((p) => new THREE.Vector3(...p))), new THREE.LineBasicMaterial({ color: 0xff4d5e }));
    group.add(cell, crack);
    return { update(dt, t) { group.rotation.y = t * 0.15; group.position.y = Math.sin(t * 0.5) * 0.15; } };
  });
  ctx.announce("Page not found.");
}
