// Asset drill-down: profile, findings, exposure per scenario, stand-in handshake + gates, ledger proofs. Camera focuses the crystal.
import { h } from "../dom.js";
import { stat, statSkeleton } from "../components/stat.js";
import { chip } from "../components/chip.js";
import { table, tableSkeleton } from "../components/table.js";
import { hashCopy } from "../components/copy.js";
import { emptyState } from "../components/states.js";
import { HNDL, num } from "../model.js";
import { buildLattice } from "../engine/lattice.js";
import { dataView, header, honesty, mountScene, notRun, section, stage, wsEyebrow } from "./common.js";

const kv = (pairs) => h("dl", { class: "kv" }, pairs.filter(Boolean).map(([k, v]) => [h("dt", { text: k }), h("dd", {}, v)]));
const mono = (t) => h("span", { class: "mono", text: t ?? "not recorded" });
const hash = (v, label) => (v ? hashCopy(v, { label }) : mono(null));
const isHndl = (s) => s && (s.hndl_exposed || s.kex_class === "classical");

export async function mount(ctx) {
  const id = ctx.params.assetId;
  const href = (x) => `/w/${ctx.ws}/asset/${encodeURIComponent(x)}`;
  const links = (ids) => (ids.length ? h("span", { class: "as-links" }, ids.map((x) => h("a", { href: href(x), text: x }))) : h("span", { class: "fine", text: "none" }));
  let scenario = ctx.query.get("scenario"), lattice = null;
  const headEl = h("div", { class: "span-12" }, header({ eyebrow: wsEyebrow(ctx), title: id, lede: "Asset drill-down." }));
  const stageEl = stage(ctx, { label: `The lattice focused on ${id}: crystal, HNDL beam (exposure-years, selected scenario), dependency conduits.`,
    fallback: h("p", { class: "fine", text: "Facts, evidence and gates follow." }) });

  ctx.store.get(ctx.ws, "scene", { signal: ctx.signal }).then((scene) => mountScene(ctx, "asset", scene, ({ THREE, world, group }) => {
    lattice = buildLattice(THREE, group, scene, world.uniforms);
    if (scenario) lattice.setScenario(scenario);
    const hit = lattice.byId[id];
    if (hit) {
      const ring = new THREE.Mesh(new THREE.TorusGeometry(0.85, 0.02, 6, 64), new THREE.MeshBasicMaterial({ color: 0x5ce0e6 }));
      ring.position.set(...hit.pos); ring.rotation.x = Math.PI / 2;
      group.add(ring);
      queueMicrotask(() => { if (!ctx.signal.aborted) world.focus(hit.pos, 6); });
    }
    return {};
  })).catch(() => {});

  const back = h("a", { class: "btn", href: `/w/${ctx.ws}/detect`, text: "Back to the inventory" });
  const body = dataView(ctx, {
    skeleton: () => h("div", { class: "grid" }, h("div", { class: "span-12" }, statSkeleton()), h("div", { class: "span-12" }, tableSkeleton(4))),
    render: ({ model: m, scene }) => {
      if (!m || !m.results) return emptyState(notRun(ctx, "Asset"));
      const r = m.results, a = m.assets.find((x) => x.id === id);
      const node = scene && scene.available && (scene.nodes || []).find((n) => n.id === id);
      if (!a) {
        return node && node.status === "not_vulnerable"
          ? emptyState({ title: `${id}: not vulnerable`, body: "Detect found no quantum-vulnerable RSA/ECC on this service, so it is not scheduled.", action: back })
          : emptyState({ title: `No asset ${id}`, body: "This workspace's inventory has no service with that id.", action: back });
      }
      headEl.querySelector("h1").textContent = a.name;
      headEl.querySelector(".lede").textContent = `${a.id} · ${a.kind} · ${a.data_class} · ${a.algorithm}`;
      document.title = `${a.name} · ${ctx.ws} · Q-Shield Atlas`;

      const scen = m.scenarios;
      if (!scen.some((s) => s.name === scenario)) scenario = scen[0] && scen[0].name;
      if (lattice && scenario) lattice.setScenario(scenario);
      const wave = (r.waves || []).find((w) => (w.assets || []).includes(id));
      const labs = (r.waves || []).flatMap((w) => ((w.evidence || {}).lab_services || []).filter((e) => (e.assets || []).includes(id)));
      const dependents = m.assets.filter((x) => x.depends_on.includes(id)).map((x) => x.id);

      const statsEl = h("div", { class: "stats" });
      const picker = h("div", { class: "sg-row", role: "radiogroup", "aria-label": "CRQC scenario" });
      const draw = () => {
        const cell = a.exposure && a.exposure[scenario] ? a.exposure[scenario] : num(null);
        statsEl.replaceChildren(
          stat({ label: "planned week", cell: a.week, unit: "optimised plan" }),
          stat({ label: `exposure · ${scenario}`, cell, unit: "exposure-years at the planned week", tone: "exposure" }),
          stat({ label: "shelf life", cell: a.shelf, unit: "years · assumption" }),
          stat({ label: "effort", cell: a.effort, unit: "engineer-days · assumption" }));
        picker.replaceChildren(...scen.map((s) => h("button", { class: `btn${s.name === scenario ? " primary" : ""}`, type: "button", role: "radio", "aria-checked": String(s.name === scenario),
          onclick: () => { scenario = s.name; ctx.setQuery({ scenario }); if (lattice) lattice.setScenario(scenario); draw(); }, text: `${s.name} · CRQC ${s.year}` })));
      };
      draw();
      ctx.announce(`${a.name}: ${a.status.replaceAll("_", " ")}, planned week ${a.week.text}.`);
      const expRows = scen.map((s) => ({ name: s.name, year: s.year, cell: a.exposure && a.exposure[s.name] ? a.exposure[s.name] : num(null) }));
      const prov = (scene && scene.provenance && scene.provenance.exposure_years) || "schedule.problem.exposure_years";

      const lab = labs[labs.length - 1];
      const sess = lab && (((r.handshake_evidence || {}).sessions || []).find((s) => s.service_id === lab.lab_service) || (lab.gates || {}).pq_handshake);
      const auth = lab && ((sess && sess.auth_alg) || ((lab.gates || {}).pq_auth || {}).auth_alg);
      const handshake = a.standin ? h("div", {},
        kv([["lab stand-in", mono(a.standin.lab_service)], ["outcome", chip(a.standin.status || "NOT_RUN")],
          ["pq_handshake", chip(a.standin.pq_handshake || "NOT_RUN")], ["pq_auth", a.standin.pq_auth ? chip(a.standin.pq_auth) : h("span", { class: "fine", text: "not run for this stand-in" })],
          ["negotiated group", mono(sess && sess.negotiated_group)], ["key exchange", mono(sess && sess.kex_class)],
          ["auth algorithm", auth ? mono(auth) : h("span", { class: "fine", text: "not recorded for this stand-in" })],
          ["transcript", hash(sess && sess.transcript_sha256, "transcript sha256")],
          isHndl(sess) && ["exposure", chip("HNDL-exposed", HNDL)]]),
        h("p", { class: "fine", text: `Session from ${sess && sess.gate ? "the wave runner's pq_handshake gate" : "handshake_evidence"}. Metadata only; no decryption performed.` }))
        : h("p", {}, chip("not_verified_in_lab", "not_verified_in_lab — never shown as fixed"), h("span", { class: "fine", text: ` No TLS lab stand-in exists for kind ${a.kind}.` }));

      const gates = labs.length ? labs.map((e) => {
        const g = e.gates || {};
        const single = Object.entries(g).filter(([k, v]) => k !== "compat" && v && typeof v === "object" && "result" in v);
        const cells = (g.compat && g.compat.cells) || [];
        return h("div", { class: "as-gate" },
          h("h3", { class: "eyebrow as-sub", text: `${e.lab_service} · ${e.from_mode} → ${e.to_mode} · wave ${wave ? wave.week : "?"}` }),
          kv([["status", chip(e.status || "NOT_RUN")], ["all gates", chip(g.passed ? "PASS" : "FAIL")],
            ["snapshot", hash(e.snapshot_sha256, "snapshot sha256")], ["applied config", hash(e.applied_config_sha256, "config sha256")],
            e.restored_config_sha256 && ["restored config", hash(e.restored_config_sha256, "restored config sha256")],
            ...single.map(([k, v]) => [k, h("span", {}, chip(v.result), " ", h("span", { class: "fine", text: v.reason || "" }), v.transcript_sha256 ? [" ", hash(v.transcript_sha256, `${k} transcript`)] : null)])]),
          cells.length ? table({ caption: `compatibility matrix for ${e.lab_service}`, rows: cells, columns: [
            { label: "client", key: "client", mono: true }, { label: "negotiated", render: (c) => (c.actual && c.actual.negotiated_group) || "refused", mono: true },
            { label: "protocol", render: (c) => (c.actual && c.actual.protocol) || "–", mono: true, optional: true },
            { label: "result", render: (c) => chip(c.result) }, { label: "transcript", render: (c) => hash(c.transcript_sha256, "transcript sha256") }] }) : null,
          cells.some(isHndl) ? h("p", { class: "fine", text: `HNDL-exposed rows: ${HNDL}.` }) : null);
      }) : h("p", { class: "fine", text: a.standin ? "No wave runner record for this stand-in." : "No gates ran: not_verified_in_lab, never shown as fixed." });

      const runIds = [wave && wave.evidence && wave.evidence.run_id, ...(((r.exposure || {}).produced_by || {}).run_ids || []), (r.detect || {}).run_id,
        a.standin && (r.handshake_evidence || {}).run_id, a.standin && (r.gates || {}).run_id].filter(Boolean);
      const entries = ((r.ledger || {}).entries || []).filter((e) => runIds.some((x) => (e.payload_ref || "").includes(x)));
      const ledger = entries.length ? h("ul", { class: "as-ledger" }, entries.map((e) => {
        const out = h("div", { class: "as-proof", hidden: true, "aria-live": "polite" });
        const btn = h("button", { class: "btn", type: "button", "aria-expanded": "false", text: "inclusion proof" });
        let loaded = false;
        btn.addEventListener("click", async () => {
          const open = out.hidden;
          out.hidden = !open; btn.setAttribute("aria-expanded", String(open));
          if (!open || loaded) return;
          out.replaceChildren("verifying against the signed root…");
          try {
            const p = await ctx.api.get(`/api/workspaces/${ctx.ws}/ledger/proof/${e.index}`, { signal: ctx.signal, quiet: true });
            loaded = true;
            out.replaceChildren(h("span", { class: p.verified ? "ok" : "bad", text: p.verified ? "✔ verified" : "✖ not verified" }),
              ` · ${(p.proof || []).length} sibling hashes · tree size ${p.tree_size ?? "not recorded"} · root `, hash(p.root, "ledger root"));
          } catch (err) {
            if (err.code !== "aborted") out.replaceChildren(h("span", { class: "bad", text: "✖ " }), err.message || "proof unavailable");
          }
        }, { signal: ctx.signal });
        return h("li", {}, h("div", { class: "as-row" }, h("span", { class: "num", text: `#${e.index}` }), mono(e.type), h("span", { class: "ref", text: e.payload_ref }), btn), out);
      })) : h("p", { class: "fine", text: "No ledger entry references this asset's runs." });

      return h("div", { class: "grid" },
        h("div", { class: "span-12 as-top" }, chip(a.status), picker), h("div", { class: "span-12" }, statsEl),
        section("Exposure-years per CRQC scenario", h("div", {},
          table({ caption: "exposure-years per scenario", rows: expRows, columns: [{ label: "scenario", key: "name", mono: true }, { label: "CRQC year", key: "year", numeric: true },
            { label: "exposure-years", render: (x) => x.cell, numeric: true }] }),
          h("p", { class: "fine", text: `Computed by ${prov}. Shelf lives and scenario years are assumptions.` }))),
        section("Profile", kv([["kind", mono(a.kind)], ["data class", mono(a.data_class)], ["algorithm", mono(a.algorithm)],
          ["planned wave", wave ? h("span", { class: "mono", text: `week ${wave.week}` }) : h("span", { class: "fine", text: "not in a wave" })],
          ["wave gate status", wave ? h("span", {}, chip(wave.status), " ", chip((wave.asset_status || {})[id] || "NOT_RUN")) : chip("NOT_RUN")],
          ["regulatory deadline status", h("span", {}, chip("NOT_RUN", "not configured"), h("span", { class: "fine", text: ` No regulatory deadline is configured for data class ${a.data_class} (assumptions in config/assumptions.json).` }))]])),
        ...reviewAndProbes(scene, a, id),
        section("Findings", table({ caption: "file:line evidence", rows: a.evidence, empty: "no static findings", columns: [
          { label: "file:line", render: (f) => `${f.file}:${f.line}`, mono: true }, { label: "family", key: "family" }, { label: "use", key: "use" },
          { label: "rule", key: "rule", mono: true }, { label: "snippet", key: "snippet", mono: true, optional: true }] })),
        section("Dependencies", kv([["depends on", links(a.depends_on)], ["dependents", links(dependents)]])),
        section("Handshake evidence", handshake, { aside: a.standin ? mono(a.standin.lab_service) : null }),
        section("Gates", h("div", {}, gates), { aside: wave && wave.evidence ? mono(`wave run ${String(wave.evidence.run_id).slice(0, 12)}…`) : null }),
        section("Ledger entries", ledger, { aside: h("span", { class: "fine", text: (r.ledger || {}).alg || "" }) }));
    },
  });
  ctx.root.append(h("div", { class: "grid" }, headEl, h("div", { class: "span-12" }, stageEl), h("div", { class: "span-12" }, body), h("div", { class: "span-12" }, honesty())));
}

// Manual-review notes (docs/detect_real_repos.md) that mention this service, plus any live probe of it.
function reviewAndProbes(scene, a, id) {
  const dirs = [...new Set((a.evidence || []).map((f) => f.file.split("/").slice(0, -1).join("/")))];
  const hits = ((scene && scene.review_notes) || []).filter((n) => n.text.includes(id) || dirs.some((d) => d && n.text.includes(d.split("/").pop())));
  const general = ((scene && scene.review_notes) || []).filter((n) => !n.paths.length && n.kind !== "fixed during review");
  const probes = ((scene && scene.probes) || []).filter((p) => p.service === id);
  const out = [];
  if (hits.length || general.length) {
    out.push(section("Manual review notes", h("div", {},
      h("ul", { class: "checks" }, [...hits, ...general].map((n) => h("li", {}, chip(n.kind === "known gap" ? "NOT_RUN" : "recorded", n.kind), h("span", { text: n.text })))),
      h("p", { class: "fine", text: `From ${(hits[0] || general[0]).source}: a human review of every finding, not computed here.` }))));
  }
  if (probes.length) {
    out.push(section("Live probe", table({ caption: "Live TLS probe of this service", rows: probes, columns: [
      { label: "endpoint", render: (p) => mono(p.endpoint) },
      { label: "key exchange", render: (p) => h("span", {}, mono(p.group || "no handshake"), p.classical ? h("span", { class: "sub", text: HNDL }) : null) },
      { label: "certificate", render: (p) => mono(p.cert || "not yet run") },
      { label: "drift", render: (p) => (p.drift.length ? h("span", {}, p.drift.map((d) => chip("NOT_RUN", d))) : chip("PASS", "none")) }] })));
  }
  return out;
}
