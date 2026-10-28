// Landing (public): the story told from the demo snapshot. Stage 4 turns each chapter into a scene in THE LATTICE.
import { h } from "../dom.js";
import { stat, statSkeleton } from "../components/stat.js";
import { chip } from "../components/chip.js";
import { lines } from "../components/states.js";
import { headlineAvoided, HNDL, num, QAOA_LABEL } from "../model.js";
import { provAttr } from "../components/tooltip.js";
import { dataView, honesty, mountScene, stage } from "./common.js";
import { buildLattice } from "../engine/lattice.js";

export async function mount(ctx) {
  ctx.ws = "demo";
  let scenario = ctx.query.get("scenario");
  const aside = h("aside", { class: "start-9" }, lines(3));
  let lattice = null;
  const stageEl = stage(ctx, { label: "THE LATTICE: the demo inventory. Red flickering crystals rely on classical crypto; red beams rise with each asset's exposure-years in the selected Q-day scenario; cyan cells passed the lab gates.", tall: true });
  ctx.store.get("demo", "scene", { signal: ctx.signal }).then((scene) => mountScene(ctx, "landing", scene, ({ THREE, world, group }) => {
    lattice = buildLattice(THREE, group, scene, world.uniforms, { beamScale: 0.35 });
    if (scenario) lattice.setScenario(scenario);
    world.uniforms.uWeek.value = 0; // HARVEST: before any wave, everything is still classical
    return { update(dt) { if (world.uniforms.uWeek.value < 1e3) world.uniforms.uWeek.value += dt * 0.6; } };
  })).catch(() => {});
  const body = dataView(ctx, {
    keys: ["results", "scene"],
    skeleton: () => h("div", { class: "grid" }, h("div", { class: "span-12" }, statSkeleton())),
    render: ({ model: m }) => {
      const r = m.results;
      if (!r) return h("div", { class: "grid" }, h("p", { class: "span-12 fine", text: "The demo snapshot (out/results.json) is not yet run. Run ./run_demo.sh to generate it." }));
      const scen = m.scenarios.map((s) => s.name);
      if (!scen.includes(scenario)) scenario = scen[Math.min(1, scen.length - 1)];
      const figure = h("div", { class: "hero-figure" });
      const dial = h("div", { class: "sg-row", role: "radiogroup", "aria-label": "Q-day scenario" });
      const drawFigure = () => {
        const a = headlineAvoided(m, scenario);
        const s = m.scenarios.find((x) => x.name === scenario);
        figure.replaceChildren(h("p", { class: "eyebrow", text: `Q-day ${s ? s.year : ""} · exposure-years avoided vs FCFS` }),
          stat({ label: "QpiAI Opt plan vs first-come-first-served", cell: a.fcfs, unit: "exposure-years, unweighted", tone: "accent" }),
          h("p", { class: "fine" }, "vs greedy ", cellText(a.greedy), ". Small and honest: long shelf lives lock most exposure in."));
        dial.replaceChildren(...m.scenarios.map((x) => h("button", { class: `btn${x.name === scenario ? " primary" : ""}`, type: "button", role: "radio",
          "aria-checked": String(x.name === scenario), onclick: () => { scenario = x.name; ctx.setQuery({ scenario }); if (lattice) lattice.setScenario(scenario); drawFigure(); }, text: String(x.year) })));
        ctx.announce(`Scenario ${scenario}: ${a.fcfs.text} exposure-years avoided versus first-come-first-served.`);
      };
      drawFigure();
      const d = m.detect, l = m.ledger, hs = m.handshake;
      const legacy = hs.available ? hs.rows.find((x) => x.kex_class === "classical") : null;
      const hybrid = hs.available ? hs.rows.find((x) => x.kex_group === "X25519MLKEM768") : null;
      const p3 = m.qaoa.available ? m.qaoa.rows.find((x) => x.p === 3 && x.source_kind === "local" && x.cells) : null;
      const chapters = [
        ["01", "Harvest", "Recorded traffic that relies on classical key exchange can be stored today and attacked once a quantum computer exists.",
          legacy ? [chip("HNDL-exposed"), h("span", { class: "fine", text: ` ${legacy.service}: ${legacy.kex_group}` })] : null],
        ["02", "Detect", "Static scan of code, configs and certificates with file:line evidence, plus live TLS probes that catch drift.",
          d.available ? [cellNum(d.vulnerable), h("span", { class: "fine", text: " quantum-vulnerable findings in " }), cellNum(d.files), h("span", { class: "fine", text: " files" })] : null],
        ["03", "Schedule", "QpiAI Opt solves the wave plan as a MILP under capacity and dependencies; it is compared with FCFS and greedy on the same data.",
          [h("span", { class: "fine mono", text: m.solver })]],
        ["04", "Handshake", "Every wave is checked on real TLS 1.3 lab services: hybrid key exchange, no silent downgrade, tested rollback.",
          hybrid ? [chip(hybrid.kex_gate), h("span", { class: "fine mono", text: ` ${hybrid.service}: X25519MLKEM768` })] : null],
        ["05", "Ledger", "Every run is signed with ML-DSA-65 into a hash-chained log with a Merkle root; any edit fails at its index.",
          l.available ? [cellNum(l.entries), h("span", { class: "fine", text: " entries " }), chip(l.verified.symbol === "✔" ? "verified" : "NOT_RUN", l.verified.text)] : null],
        ["06", "QAOA", `A one-week wave selection as a QUBO, solved by QAOA on a simulator and measured against the brute-force optimum: ${QAOA_LABEL}.`,
          p3 ? [h("span", { class: "fine", text: "feasible fraction p=3 " }), cellNum(p3.cells.feasible_fraction)] : null],
      ];
      aside.replaceChildren(figure, dial);
      return h("div", { class: "grid" },
        h("div", { class: "span-12" }, h("div", { class: "stats" },
          stat({ label: "assets to migrate", cell: d.available ? d.assets : num(null), unit: "services with RSA/ECC/DH" }),
          stat({ label: "findings", cell: d.available ? d.vulnerable : num(null), unit: "file:line evidence" }),
          stat({ label: "weeks to migrate", cell: m.makespan, unit: "optimised wave plan" }),
          stat({ label: "ledger entries", cell: l.available ? l.entries : num(null), unit: "ML-DSA-65 signed" }))),
        h("ol", { class: "span-12 chapters", "aria-label": "How it works" }, chapters.map(([n, t, body, fact]) =>
          h("li", { class: "chapter" }, h("span", { class: "c-num mono", text: n }), h("h2", { text: t }), h("p", { text: body }), h("div", { class: "c-fact" }, fact)))),
        h("div", { class: "span-12 cta" }, h("p", { class: "h2", text: "Run it on your systems." }),
          h("p", { class: "fine", text: "Upload a repository or point it at endpoints you are authorised to test; every number stays traceable to a signed run." }),
          h("a", { class: "btn primary", href: ctx.me ? `/w/demo/pipeline` : "/signin", text: ctx.me ? "Open the workspace" : "Sign in to run it on your systems" })),
        h("p", { class: "span-12 fine", text: `${HNDL}. Data: demo snapshot, results.json generated ${r.generated_at}.` }),
        h("div", { class: "span-12" }, honesty()));
    },
  });
  ctx.root.append(h("div", { class: "grid", style: { marginBottom: "var(--s-6)" } }, hero(ctx), aside, h("div", { class: "span-12" }, stageEl)), body);
}

function hero(ctx) {
  return h("div", { class: "span-8" }, h("p", { class: "eyebrow" }, h("span", { class: "accent", text: "PQC-01" }), " · Q-Shield Atlas"),
    h("h1", { class: "display", text: "Find the crypto a quantum computer breaks. Move it in the right order. Prove every step." }),
    h("p", { class: "lede", text: "RSA, ECC and DH inventory with file:line evidence, an optimal migration schedule from QpiAI Opt, real TLS 1.3 handshake checks for every wave, and an ML-DSA-65 signed ledger." }));
}

function cellNum(c) {
  return c && c.kind === "number" ? h("span", { class: "num", tabindex: "0", "data-prov": provAttr(c.source), text: c.text }) : h("span", { class: "fine", text: (c && c.text) || "not yet run" });
}
function cellText(c) { return cellNum(c); }
