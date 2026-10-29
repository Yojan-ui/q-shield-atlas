// Landing (public): the story told from the demo snapshot. Stage 4 turns each chapter into a scene in THE LATTICE.
import { h, stagger } from "../dom.js";
import { statSkeleton } from "../components/stat.js";
import { headlineAvoided, HNDL, num } from "../model.js";
import { provAttr } from "../components/tooltip.js";
import { dataView, honesty, mountScene, stage, viewCss } from "./common.js";
import { FLOW } from "../flow.js";
import { rollNumber } from "../motion.js";
import { buildLattice } from "../engine/lattice.js";

export async function mount(ctx) {
  await viewCss("landing");
  ctx.ws = "demo";
  let scenario = ctx.query.get("scenario");
  let lattice = null;
  const stageEl = stage(ctx, { tall: true, label: "THE LATTICE: the demo inventory. Red flickering crystals rely on classical crypto; red beams rise with each asset's exposure-years in the selected Q-day scenario; cyan cells passed the lab gates.", tall: true });
  // Title sequence (<= 3 s, any input skips, reduced motion = instant): crystals ignite red one by one with beams
  // rising, the headline wipes in, then the waves turn crystals cyan in plan order (red threat -> system -> cyan).
  const reveal = () => { if (ctx.root.classList.contains("intro-hold")) { ctx.root.classList.remove("intro-hold"); stagger(heroEl); } };
  // the headline paints at once (no hold): the 3D title sequence plays behind it
  const skip = () => { if (ctx.world.uniforms) ctx.world.uniforms.uIntro.value = 1; reveal(); };
  for (const ev of ["pointerdown", "keydown", "wheel"]) addEventListener(ev, skip, { once: true, signal: ctx.signal });
  setTimeout(reveal, 1700);
  ctx.store.get("demo", "scene", { signal: ctx.signal }).then((scene) => mountScene(ctx, "landing", scene, ({ THREE, world, group }) => {
    lattice = buildLattice(THREE, group, scene, world.uniforms, { beamScale: 0.35 });
    if (scenario) lattice.setScenario(scenario);
    world.uniforms.uWeek.value = 0; // HARVEST: before any wave, everything is still classical
    world.uniforms.uIntro.value = world.reduced ? 1 : 0;
    if (world.reduced) reveal();
    return { ...lattice.hooks(ctx, stageEl), update(dt) {
      const u = world.uniforms;
      if (u.uIntro.value < 1) { u.uIntro.value = Math.min(1, u.uIntro.value + dt / 2.6); if (u.uIntro.value > 0.6) reveal(); }
      else if (u.uWeek.value < 1e3) u.uWeek.value += dt * 0.6;
    } };
  })).catch(reveal);
  const go = (to) => (ctx.me ? to : `/signin?next=${encodeURIComponent(to)}`);
  const body = dataView(ctx, {
    keys: ["results", "scene"],
    skeleton: () => h("div", { class: "ld-nums" }, statSkeleton()),
    render: ({ model: m }) => {
      const r = m.results;
      if (!r) return h("p", { class: "mv-note", text: "The demo snapshot (out/results.json) is not yet run. Run ./run_demo.sh to generate it." });
      const scen = m.scenarios.map((x) => x.name);
      if (!scen.includes(scenario)) scenario = scen[Math.min(1, scen.length - 1)];
      if (lattice) lattice.setScenario(scenario);
      const a = headlineAvoided(m, scenario), d = m.detect, l = m.ledger;
      const verified = l.available && l.verified && l.verified.symbol === "✔";
      // three real numbers, counted up from 0 (reduced motion: shown at once)
      const big = (cell, digits, label, unit) => {
        const v = h("span", { class: "ld-num num", tabindex: cell && cell.kind === "number" ? "0" : null, "data-prov": cell && cell.source ? provAttr(cell.source, label) : null });
        if (cell && cell.kind === "number") { v._value = 0; v.textContent = (0).toFixed(digits); requestAnimationFrame(() => rollNumber(v, cell.value, digits)); } else v.textContent = "not yet run";
        return h("div", { class: "ld-stat" }, v, h("p", { class: "ld-k", text: label }), h("p", { class: "mv-note", text: unit }));
      };
      const steps = h("ol", { class: "ld-steps", "aria-label": "The pipeline, in order" }, FLOW.map((f, i) => h("li", {}, h("a", { href: go(`/w/demo/${f.route}`) }, h("span", { class: "num", text: String(i + 1) }), f.label))));
      return h("div", { class: "ld-below" },
        h("div", { class: "ld-nums" },
          big(d.available ? d.assets : num(null), 0, "systems found exposed", "use RSA / ECC / DH today (demo bank)"),
          big(a.fcfs, 3, "exposure-years avoided", `optimised plan vs first-come-first-served, Q-Day ${(m.scenarios.find((x) => x.name === scenario) || {}).year || ""}`),
          big(l.available ? l.entries : num(null), 0, "signed proof records", verified ? "ML-DSA-65, every signature re-verified" : "ML-DSA-65 · not verified")),
        steps,
        h("p", { class: "ld-honest", text: "Lab demo. Real public data where marked. Migrations are simulated. No quantum advantage claimed." }),
        h("p", { class: "mv-note", text: `${HNDL}. Data: demo snapshot, results.json generated ${r.generated_at}.` }),
        honesty());
    },
  });
  const heroEl = h("header", { class: "ld-hero" },
    h("p", { class: "eyebrow" }, h("span", { class: "accent", text: "PQC-01" }), " · Q-Shield Atlas"),
    h("h1", { class: "ld-h1", text: "Find quantum-breakable crypto. Fix it in order. Prove it." }),
    h("p", { class: "ld-lede", text: "A future quantum computer can break RSA and ECC, so traffic recorded today can be read later; Atlas finds that crypto, schedules the move and proves every step." }),
    h("div", { class: "sg-row ld-cta" }, h("a", { class: "btn primary", href: go("/w/demo/pipeline?guided=1"), text: "See it run" }), h("a", { class: "btn", href: go("/settings/new-workspace"), text: "Scan your own repo" })));
  // the Proof Chain forming: one block per real demo ledger entry, appended in order, green once verified
  const chain = h("ol", { class: "ld-chain", "aria-label": "Proof Chain entries" });
  ctx.store.get("demo", "ledger", { signal: ctx.signal }).then((L) => {
    if (!L || !L.available) { chain.replaceChildren(h("li", { class: "mv-note", text: "Proof Chain: not yet run" })); return; }
    const ok = L.live_verification && L.live_verification.ok === true;
    chain.replaceChildren(...L.entries.map((e, i) => h("li", { class: `ld-blk${ok ? " ok" : ""}`, style: { animationDelay: `${Math.min(i, 80) * 35}ms` }, title: `#${e.index} ${e.type}` })));
    chain.setAttribute("aria-label", `Proof Chain: ${L.entries.length} signed entries${ok ? ", all verified" : ""}`);
  }).catch(() => {});
  ctx.root.append(h("div", { class: "ld" }, heroEl, h("div", { class: "ld-stage" }, stageEl, chain,
    h("p", { class: "mv-how", text: "The demo bank's systems: red crystals still rely on classical crypto and turn cyan as each planned wave passes its lab gate. Below: the signed Proof Chain, one block per record." })), body));
}
