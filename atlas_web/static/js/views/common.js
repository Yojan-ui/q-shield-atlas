// Shared view scaffolding: editorial header, data loading with skeleton/error, SSE-driven refresh.
import { h, stagger } from "../dom.js";
import { errorState } from "../components/states.js";
import { buildViewModel } from "../model.js";

export function header({ eyebrow, title, lede, aside = null, actions = null }) {
  return h("div", { class: "grid view-head" },
    h("div", { class: "span-7" }, h("p", { class: "eyebrow" }, eyebrow), h("h1", { text: title }), lede ? h("p", { class: "lede", text: lede }) : null,
      actions ? h("div", { class: "sg-row", style: { marginTop: "var(--s-5)" } }, actions) : null),
    aside ? h("div", { class: "start-9" }, aside) : null);
}

export function section(title, body, { aside = null, id = null } = {}) {
  return h("section", { class: "section span-12", id }, h("div", { class: "section-head" }, h("h2", { text: title }), aside), body);
}

export function wsEyebrow(ctx) {
  const w = ctx.wsInfo;
  return [h("span", { class: "accent", text: w ? w.name : ctx.ws }), w && w.read_only ? " · read-only snapshot" : ""];
}

// Load the keys a view needs, render skeleton first, then content; re-render when SSE invalidates them.
export function dataView(ctx, { keys = ["results", "scene"], skeleton, render }) {
  const body = h("div", { class: "view-body" });
  body.append(skeleton());
  let gen = 0;
  const draw = async () => {
    const my = ++gen;
    try {
      const data = await Promise.all(keys.map((k) => ctx.store.get(ctx.ws, k, { signal: ctx.signal })));
      if (my !== gen || ctx.signal.aborted) return;
      const byKey = Object.fromEntries(keys.map((k, i) => [k, data[i]]));
      const model = byKey.results ? buildViewModel(byKey.results.results, byKey.scene && byKey.scene.available ? byKey.scene : null) : null;
      const node = render({ ...byKey, model }, body);
      if (node) { body.replaceChildren(node); stagger(node); }
    } catch (err) {
      if (my !== gen || ctx.signal.aborted || err.code === "aborted") return;
      body.replaceChildren(errorState({ error: err, onRetry: draw }));
    }
  };
  draw();
  const off = ctx.store.subscribe(({ ws, keys: changed }) => { if (ws === ctx.ws && changed.some((k) => keys.includes(k))) draw(); });
  ctx.signal.addEventListener("abort", off, { once: true });
  return body;
}

export function notRun(ctx, what) {
  const can = ctx.me && ctx.me.role !== "viewer" && ctx.wsInfo && !ctx.wsInfo.read_only;
  return {
    title: `${what}: not yet run`,
    body: can ? "Run the pipeline in this workspace to produce it. Nothing is shown until a logged run exists."
      : "This workspace has no logged run yet. An operator can start one from the pipeline.",
    action: h("a", { class: "btn primary", href: `/w/${ctx.ws}/pipeline`, text: "Open pipeline" }),
  };
}

export function honesty() {
  return h("footer", { class: "foot" },
    h("span", { text: "Lab demo · local TLS lab services on 127.0.0.1" }), h("span", { text: "local single-key ML-DSA-65 test ledger" }),
    h("span", { text: "simulator-scale QAOA, no quantum advantage claimed" }),
    h("span", { text: "risk, effort and shelf-life values are assumptions" }), h("span", { text: "no decryption performed or claimed" }));
}

// A transparent window onto THE LATTICE: the persistent renderer draws only inside this element.
// Without WebGL it shows `fallback` (2D content) instead, so the route never goes blank.
export function stage(ctx, { label, fallback = null, tall = false } = {}) {
  const el = h("div", { class: `stage${tall ? " tall" : ""}`, "data-stage": "", role: "img", "aria-label": label });
  ctx.world.frameStage(el);
  ctx.stageEl = el;
  ctx.world.ready.then((w) => {
    if (!w.webgl && !ctx.signal.aborted) {
      el.classList.add("flat");
      el.replaceChildren(h("p", { class: "fine stage-note", text: "3D view unavailable (no WebGL in this browser); the same data is shown below." }), fallback);
    }
  });
  return el;
}

// Mount a layer once the scene data and the engine are both ready. build({THREE, world, group, scene}) -> layer.
export async function mountScene(ctx, name, scene, build) {
  const w = await ctx.world.ready;
  if (scene && scene.available === false && ctx.stageEl) ctx.stageEl.hidden = true;  // nothing to show: no empty black stage
  if (!w.webgl || ctx.signal.aborted || !scene || scene.available === false) return null;
  return w.mount(name, (env) => build({ ...env, scene }));
}
