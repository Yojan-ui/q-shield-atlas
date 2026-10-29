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
  await Promise.all([viewCss("landing"), viewCss("pillars")]);
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
  const labels3d = h("div", { class: "gr-labels", "aria-hidden": "true" });
  stageEl.append(labels3d);
  const resultsP = ctx.store.get("demo", "results", { signal: ctx.signal }).catch(() => null);
  ctx.store.get("demo", "scene", { signal: ctx.signal }).then((scene) => mountScene(ctx, "landing", scene, ({ THREE, world, group }) => {
    lattice = buildLattice(THREE, group, scene, world.uniforms, { beamScale: 0.35, nodeScale: 1.35 });
    if (scenario) lattice.setScenario(scenario);
    world.uniforms.uWeek.value = 0; // HARVEST: before any wave, everything is still classical
    world.uniforms.uIntro.value = world.reduced ? 1 : 0;
    if (world.reduced) reveal();
    // camera auto-fit to the scene bounds: the sphere is loose around this deep layout, so it is fitted slightly past the view edge (the data itself then fills ~80 %); refit on resize
    const pts = (scene.nodes || []).map((n) => n.pos);
    const fit = () => {
      if (!pts.length) return;
      const c = [0, 1, 2].map((k) => (Math.min(...pts.map((p) => p[k])) + Math.max(...pts.map((p) => p[k]))) / 2);
      const R = Math.max(1, ...pts.map((p) => Math.hypot(p[0] - c[0], p[1] - c[1], p[2] - c[2]))) + 0.7;
      const b = stageEl.getBoundingClientRect(), v = (world.camera.fov * Math.PI) / 360, hz = Math.atan(Math.tan(v) * (b.width / Math.max(1, b.height)));
      world.focus([c[0] + group.position.x, c[1] + group.position.y, c[2] + group.position.z], R / Math.sin(1.05 * Math.min(v, hz)) / Math.hypot(0.6, 0.45, 0.8));
    };
    fit();
    let rt = 0;
    const ro = new ResizeObserver(() => { clearTimeout(rt); rt = setTimeout(fit, 150); });
    ro.observe(stageEl);
    // labels for the three systems with the highest risk weight (results.json assets)
    const top = [], tmp = new THREE.Vector3();
    resultsP.then((res) => {
      const byId = Object.fromEntries((scene.nodes || []).map((n) => [n.id, n]));
      const ranked = [...((res && res.results && res.results.assets) || [])].filter((x) => byId[x.id]).sort((x, y) => (y.risk_weight || 0) - (x.risk_weight || 0)).slice(0, 3);
      for (const x of ranked) { const e = h("span", { class: "pl3-label", text: x.name }); labels3d.append(e); top.push({ e, pos: byId[x.id].pos }); }
    });
    const base = lattice.hooks(ctx, stageEl);
    return { ...base, update(dt) {
      const u = world.uniforms;
      if (u.uIntro.value < 1) { u.uIntro.value = Math.min(1, u.uIntro.value + dt / 2.6); if (u.uIntro.value > 0.6) reveal(); }
      else if (u.uWeek.value < 1e3) u.uWeek.value += dt * 0.6;
      if (top.length) {
        const b = stageEl.getBoundingClientRect();
        group.updateMatrixWorld();
        for (const t of top) {
          tmp.set(t.pos[0], t.pos[1] + 0.9, t.pos[2]).applyMatrix4(group.matrixWorld).project(world.camera);
          t.e.hidden = tmp.z > 1;
          t.e.style.transform = `translate(${((tmp.x + 1) / 2) * b.width}px, ${((1 - tmp.y) / 2) * b.height}px) translate(-50%, -100%)`;
        }
      }
    }, dispose() { ro.disconnect(); clearTimeout(rt); labels3d.replaceChildren(); if (base.dispose) base.dispose(); } };
  })).catch(reveal);
  const go = (to) => (ctx.me ? to : `/signin?next=${encodeURIComponent(to)}`);
  const numsEl = h("div", { class: "ld-nums" }, statSkeleton());
  const body = dataView(ctx, {
    keys: ["results", "scene"],
    skeleton: () => h("span"),
    render: ({ model: m }) => {
      const r = m.results;
      if (!r) { numsEl.replaceChildren(h("p", { class: "mv-note", text: "Demo numbers: not yet run" })); return h("p", { class: "mv-note", text: "The demo snapshot (out/results.json) is not yet run. Run ./run_demo.sh to generate it." }); }
      const scen = m.scenarios.map((x) => x.name);
      if (!scen.includes(scenario)) scenario = scen[Math.min(1, scen.length - 1)];
      if (lattice) lattice.setScenario(scenario);
      const a = headlineAvoided(m, scenario), d = m.detect, l = m.ledger;
      const verified = l.available && l.verified && l.verified.symbol === "✔";
      // three real numbers, counted up from 0 (reduced motion: shown at once)
      const big = (cell, digits, label, unit) => {
        const v = h("span", { class: "ld-num num", tabindex: cell && cell.kind === "number" ? "0" : null, "data-prov": cell && cell.source ? provAttr(cell.source, label) : null });
        if (cell && cell.kind === "number") { v._value = 0; v.textContent = (0).toFixed(digits); requestAnimationFrame(() => rollNumber(v, cell.value, digits)); } else v.textContent = "not yet run";
        return h("div", { class: "ld-stat" }, v, h("p", { class: "ld-k", text: label }), h("p", { class: "ld-u", text: unit }));
      };
      numsEl.replaceChildren(
        big(d.available ? d.assets : num(null), 0, "systems exposed", "RSA / ECC / DH today (demo bank)"),
        big(a.fcfs, 3, "exposure-years avoided", `vs first-come-first-served, Q-Day ${(m.scenarios.find((x) => x.name === scenario) || {}).year || ""}`),
        big(l.available ? l.entries : num(null), 0, "signed proof records", verified ? "ML-DSA-65, all verified" : "ML-DSA-65 · not verified"));
      const steps = h("ol", { class: "ld-steps", "aria-label": "The pipeline, in order" }, FLOW.map((f, i) => h("li", {}, h("a", { href: go(`/w/demo/${f.route}`) }, h("span", { class: "num", text: String(i + 1) }), f.label))));
      return h("div", { class: "ld-below" }, steps,
        h("p", { class: "ld-honest", text: "Lab demo. Real public data where marked. Migrations are simulated. No quantum advantage claimed." }),
        h("p", { class: "mv-note", text: `${HNDL}. Data: demo snapshot, results.json generated ${r.generated_at}.` }),
        honesty());
    },
  });
  const heroEl = h("header", { class: "ld-hero" },
    h("p", { class: "eyebrow" }, h("span", { class: "accent", text: "PQC-01" }), " · Q-Shield Atlas"),
    h("h1", { class: "ld-h1", text: "Find quantum-breakable crypto. Fix it in order. Prove it." }),
    h("p", { class: "ld-lede", text: "A future quantum computer can break RSA and ECC, so traffic recorded today can be read later. Atlas finds that crypto, schedules the move and proves every step." }),
    h("div", { class: "sg-row ld-cta" }, h("a", { class: "btn primary", href: go("/w/demo/pipeline?guided=1"), text: "See it run" }), h("a", { class: "btn", href: go("/settings/new-workspace"), text: "Scan your own repo" })));
  // Proof chain strip: a label with the real count and one row of small blocks (one per signed record)
  const chainLabel = h("p", { class: "ld-chain-k", text: "Proof chain: loading…" });
  const chain = h("ol", { class: "ld-chain", "aria-hidden": "true" });
  ctx.store.get("demo", "ledger", { signal: ctx.signal }).then((L) => {
    if (!L || !L.available) { chainLabel.textContent = "Proof chain: not yet run"; return; }
    const ok = L.live_verification && L.live_verification.ok === true;
    chainLabel.textContent = `Proof chain: ${L.entries.length} signed records${ok ? ", all verified" : ", not verified"}`;
    chain.replaceChildren(...L.entries.map((e, i) => h("li", { class: `ld-blk${ok ? " ok" : ""}`, style: { animationDelay: `${Math.min(i, 80) * 25}ms` } })));
  }).catch(() => { chainLabel.textContent = "Proof chain: not yet run"; });
  ctx.root.append(h("div", { class: "ld" },
    h("section", { class: "ld-top", "aria-label": "Q-Shield Atlas" }, h("div", { class: "ld-left" }, heroEl, numsEl),
      h("div", { class: "ld-right" }, stageEl, h("div", { class: "ld-chainrow" }, chainLabel, chain))),
    body));
}
