// Detect: the codebase as a file city, inventory tables (also the no-WebGL fallback), operator intake.
import { append, h, icon } from "../dom.js";
import { readCookie } from "../api.js";
import { stat, statSkeleton } from "../components/stat.js";
import { chip } from "../components/chip.js";
import { table, tableSkeleton } from "../components/table.js";
import { emptyState } from "../components/states.js";
import { field, checkbox } from "../components/form.js";
import { toast } from "../components/toast.js";
import { buildGraph, classicalSig, CLASSES, graphModel, layout, VULN } from "../scenes/graph.js";
import { provAttr } from "../components/tooltip.js";
import { prefersReducedMotion } from "../motion.js";
import { num } from "../model.js";
import { bullets, detailsList, keyStats, main, nextStep, pageHead, dd } from "../components/page.js";
import { term } from "../glossary.js";
import { dataView, honesty, mountScene, notRun, section, stage, viewCss } from "./common.js";

const say = (el, t, bad = true) => { el.textContent = t; el.classList.toggle("bad", bad); };
const out = () => h("p", { class: "fine dt-msg" }), btn = (t, cls = "btn") => h("button", { class: cls, type: "submit" }, t);
const box = (label, id, input, hint = "") => h("div", { class: "field" }, h("label", { for: id, text: label }), input, h("div", { class: "hint", text: hint }));
const watch = (ctx, keys, fn) => { const off = ctx.store.subscribe(({ ws, keys: k }) => { if (ws === ctx.ws && k.some((x) => keys.includes(x))) fn(); }); ctx.signal.addEventListener("abort", off, { once: true }); };

// ---- the hero: the inventory as a 3D dependency graph (scenes/graph.js); flat 2D SVG without WebGL or on request
export function flatGraph(G, L, onPick) {
  const P = L.pos, n = G.nodes.length, R = L.radius || 1, W = 1000, H = 560, sx = (x) => W * 0.34 + (x / R) * (W * 0.3), sy = (y) => H / 2 - (y / R) * (H / 2 - 30);  // left: the panel sits on the right
  const maxRisk = Math.max(1e-9, ...G.nodes.map((x) => x.risk));
  const svg = h("svg", { viewBox: `0 0 ${W} ${H}`, class: "gr-flat", role: "img", "aria-label": `Flat dependency graph: ${n} systems, ${G.edges.length} dependencies` });
  for (const [a, b] of G.edges) svg.append(h("line", { ns: "svg", x1: sx(P[a * 3]), y1: sy(P[a * 3 + 1]), x2: sx(P[b * 3]), y2: sy(P[b * 3 + 1]), class: "gr-edge" }));
  const order = G.nodes.map((x, i) => i).sort((a, b) => (G.nodes[a].cls === "exposed" ? 0 : 1) - (G.nodes[b].cls === "exposed" ? 0 : 1));  // red first, others on top
  order.forEach((i) => {
    const x = G.nodes[i], r = 9 + 14 * Math.sqrt(Math.max(0, x.risk) / maxRisk);
    const g = h("g", { ns: "svg", class: `gr-node ${x.cls}`, tabindex: "0", role: "button", "data-id": x.id, "aria-label": `${x.name}: ${CLASSES[x.cls].label}` },
      h("circle", { ns: "svg", cx: sx(P[i * 3]), cy: sy(P[i * 3 + 1]), r }),
      x.drift ? h("circle", { ns: "svg", cx: sx(P[i * 3]), cy: sy(P[i * 3 + 1]), r: r + 6, class: "gr-drift" }) : null,
      h("title", { ns: "svg", text: x.name }));
    g.addEventListener("click", () => onPick(x));
    g.addEventListener("keydown", (e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); onPick(x); } });
    svg.append(g);
  });
  return svg;
}

function graphHero(ctx, r, observed, inventory) {
  const G = graphModel(r, observed, inventory), L = layout(G.nodes, G.edges), d = r.detect || {};
  const count = (c) => G.nodes.filter((x) => x.cls === c).length;
  const src = (note) => provAttr({ run_id: d.run_id || "n/a", solver: "detect: static scan + live probe", job_id: "none (local scan, no backend job)", ts: d.ts || "n/a", note });
  const panel = h("aside", { class: "gr-panel", "aria-live": "polite" });
  const empty = () => panel.replaceChildren(h("p", { class: "gr-p-k", text: "Select a system" }), h("p", { class: "mv-note", text: "Click or tap a node (or Tab to it in the flat view) to see what the scan found and where." }));
  const show = (x) => {
    if (!x) return empty();
    panel.replaceChildren();
    append(panel, [
      h("p", { class: "gr-p-k", text: CLASSES[x.cls].label }),
      h("h3", { class: "gr-p-name", text: x.name }),
      h("p", { class: "mv-note", text: [x.kind, x.data_class, x.inPlan ? `risk weight ${x.risk} (assumption)` : "not in the migration plan"].filter(Boolean).join(" · ") }),
      x.families.length ? h("p", {}, x.families.map((f) => chip(VULN.has(f) ? "HNDL-exposed" : f === "PQC" ? "hybrid" : "NOT_RUN", f))) : null,
      x.cls === "pqc" && classicalSig(x.evidence).length ? h("p", { class: "mv-note", text: `Key exchange is already post-quantum; the certificate signature is still ${classicalSig(x.evidence).join(" / ")} (replace before a quantum computer exists; not an HNDL exposure).` }) : null,
      x.drift ? h("div", { class: "gr-p-drift" }, h("p", { class: "gr-p-k", text: "Drift: static scan and live handshake disagree" }), x.drift.map((z) => h("p", { tabindex: "0", "data-prov": src(z.kind), text: z.detail }))) : null,
      x.observed ? h("p", { class: "mv-note", tabindex: "0", "data-prov": src(x.observed.source), text: `observed once: ${x.observed.negotiated_group} · ${x.observed.tls_version} · cert ${x.observed.cert_key_algorithm}` }) : null,
      h("p", { class: "gr-p-k", text: `Evidence (${x.evidence.length})` }),
      h("ul", { class: "gr-ev" }, x.evidence.slice(0, 12).map((e) => h("li", { tabindex: "0", "data-prov": src(`${e.rule}: ${e.snippet || ""}`.slice(0, 160)) },
        h("span", { class: "mono", text: `${e.file}:${e.line}` }), h("span", { class: "mv-note", text: ` ${e.family} · ${e.use} · ${e.rule}` })))),
      x.evidence.length > 12 ? h("p", { class: "mv-note", text: `+ ${x.evidence.length - 12} more on the asset page` }) : null,
      x.inPlan ? h("a", { class: "btn", href: `/w/${ctx.ws}/asset/${encodeURIComponent(x.id)}` }, "Open asset", icon("arrow")) : null]);
  };
  empty();
  const labels = h("div", { class: "gr-labels", "aria-hidden": "true" });
  let flat = null, layer = null, mode = ctx.query.get("view") === "2d" ? "2d" : "3d";
  const pick = (x) => { show(x); if (layer && layer.select) layer.select(x ? x.id : null); if (flat) flat.querySelectorAll(".gr-node").forEach((g) => g.classList.toggle("on", !!x && g.dataset.id === x.id)); };
  flat = flatGraph(G, L, pick);
  const el = stage(ctx, { label: `Dependency graph of ${G.nodes.length} systems: ${count("exposed")} quantum-exposed, ${count("caution")} need a live probe, ${count("pqc")} post-quantum, ${count("safe")} not vulnerable.`, fallback: flat, tall: true });
  el.classList.add("gr-stage");
  el.append(labels);
  const flatWrap = h("div", { class: "gr-flatwrap", hidden: true });
  const resetBtn = h("button", { class: "btn", type: "button" }, icon("rewind"), "Reset view");
  const modeBtn = h("button", { class: "btn", type: "button" });
  const mount3d = () => mountScene(ctx, "detect", { available: true }, (env) => buildGraph(env, G, L, { reduced: prefersReducedMotion(), labelsEl: labels, stageEl: el, onSelect: show }))
    .then((l) => { layer = l; if (!l) { mode = "2d"; apply(); } });
  const apply = () => {
    modeBtn.replaceChildren(icon(mode === "3d" ? "dash" : "lattice"), mode === "3d" ? "Flat 2D graph" : "3D graph");
    resetBtn.hidden = mode !== "3d";
    if (mode === "2d") {
      if (layer) { ctx.world.mount("detect", null); layer = null; }
      el.hidden = true; flatWrap.hidden = false; flatWrap.append(flat);
    } else { el.hidden = false; flatWrap.hidden = true; if (!el.classList.contains("flat")) mount3d(); }
  };
  resetBtn.addEventListener("click", () => { if (layer) layer.reset(); pick(null); }, { signal: ctx.signal });
  modeBtn.addEventListener("click", () => { mode = mode === "3d" ? "2d" : "3d"; ctx.setQuery({ view: mode === "2d" ? "2d" : null }); apply(); }, { signal: ctx.signal });
  apply();
  const legend = h("ul", { class: "legend gr-legend", "aria-label": "What the node colours mean" }, Object.entries(CLASSES).map(([k, c]) =>
    h("li", {}, h("span", { class: `lg-dot ${c.css}`, "aria-hidden": "true" }), `${c.label} `, h("span", { class: "num", text: String(count(k)) }))),
    h("li", {}, h("span", { class: "lg-ring", "aria-hidden": "true" }), "White ring: drift (static scan and live handshake disagree) ", h("span", { class: "num", text: String(G.nodes.filter((x) => x.drift).length) })));
  return h("section", { class: "gr" }, legend,
    h("div", { class: "gr-body" }, h("div", { class: "gr-view" }, el, flatWrap), panel),
    h("div", { class: "gr-bar" }, dd({ read: `${G.nodes.length} systems from the inventory, ${G.edges.length} declared dependencies (lines). Node size is the risk weight (an assumption). ${G.bank ? "Clusters are banks." : "Clusters are system kinds."} Drag to turn, ⌥-scroll to zoom.` }),
      h("div", { class: "sg-row" }, resetBtn, modeBtn)));
}

function intake(ctx) {
  const ro = ctx.wsInfo && ctx.wsInfo.read_only;
  if (!(ctx.me && ["operator", "admin"].includes(ctx.me.role)) || !ctx.wsInfo || ro) return section("Bring your system", h("p", { class: "fine", text: ro ? "Read-only snapshot: source intake and probes are disabled." : "Read-only for your role. An operator can upload source, edit service manifests and start authorised probes." }));
  const ws = ctx.ws, base = `/api/workspaces/${encodeURIComponent(ws)}`;
  const post = (p, body, o = {}) => ctx.api.post(base + p, body, { quiet: true, signal: ctx.signal, ...o });
  const changed = (t) => { toast(t, { tone: "success" }); ctx.store.invalidate(ws, ["manifests"]); };
  const form = (msg, fn, ...kids) => h("form", { class: "dt-form", onsubmit: async (e) => {
    e.preventDefault(); const b = e.target.querySelector("button[type=submit]"); b.disabled = true;
    try { await fn(); } catch (err) { if (err.code !== "aborted") { if (err.onFields) err.onFields(); say(msg, err.message); } }
    b.disabled = false;
  } }, ...kids);
  // (a) .zip upload with progress (XHR for upload progress events)
  const zip = h("input", { type: "file", id: "dt-zip", accept: ".zip,application/zip" }), bar = h("progress", { max: 100, value: 0, hidden: true, "aria-label": "upload progress" }), upMsg = out();
  const upload = form(upMsg, () => new Promise((ok, fail) => {
    const f = zip.files[0];
    if (!f) return fail(new Error("Choose a .zip file first."));
    const x = new XMLHttpRequest();
    x.open("POST", `${base}/upload`);
    [["Content-Type", "application/zip"], ["Accept", "application/json"], ["X-CSRF-Token", readCookie(document.cookie, "atlas_csrf")]].forEach(([k, v]) => x.setRequestHeader(k, v));
    x.upload.onprogress = (e) => { if (e.lengthComputable) { bar.value = (e.loaded / e.total) * 100; say(upMsg, `Uploading ${Math.round(bar.value)} %`, false); } };
    x.onloadend = () => {
      bar.hidden = true; let d = null; try { d = JSON.parse(x.responseText); } catch { /* not JSON */ }
      if (x.status && x.status < 300 && d) { say(upMsg, `Source replaced: ${d.files} files, ${d.manifests} manifests.`, false); changed("Source uploaded"); ok(); }
      else fail(new Error((d && d.error && d.error.message) || (x.status ? `Upload failed (HTTP ${x.status}).` : "Cannot reach the Atlas server.")));
    };
    ctx.signal.addEventListener("abort", () => x.abort(), { once: true });
    bar.hidden = false; bar.value = 0; x.send(f);
  }), box("Upload .zip", "dt-zip", zip, "replaces the workspace source"), h("div", { class: "sg-row" }, btn("Upload .zip"), bar), upMsg);
  // (b) git clone
  const url = field({ label: "Public git URL", name: "url", type: "url", placeholder: "https://github.com/org/repo.git", hint: "public https only; replaces the workspace source", validate: (v) => (/^https:\/\//.test(v) ? "" : "must start with https://") });
  const clMsg = out();
  const clone = form(clMsg, async () => {
    if (!url.check()) return;
    say(clMsg, "Cloning…", false);
    const d = await post("/clone", { url: url.value() }, { timeout: 180000 });
    say(clMsg, `Cloned ${String(d.commit).slice(0, 12)}: ${d.files} files, ${d.manifests} manifests.`, false); changed("Repository cloned");
  }, url, h("div", { class: "sg-row" }, btn("Clone")), clMsg);
  // (c) manifest editor
  const man = h("div", {}, tableSkeleton(4, 3));
  const drawMan = (L) => {
    const svc = L.services || [], ids = svc.map((s) => s.manifest && s.manifest.id).filter(Boolean), ed = h("div", { class: "dt-form" }), opt = (a) => (a || []).map((v) => ({ value: v, label: v }));
    const edit = (s) => {
      const m = (s && s.manifest) || {}, msg = out(), sug = m.suggested ? m.suggested.basis || {} : null, F = {
        dir: field({ label: "Directory", name: "dir", value: s ? s.dir : "", options: s ? [s.dir] : [{ value: "", label: "choose a directory" }, ...opt(L.candidate_dirs)] }),
        id: field({ label: "Service id", name: "id", value: m.id || "", hint: "a-z 0-9 -", required: true }),
        name: field({ label: "Name", name: "name", value: m.name || "", required: true }),
        kind: field({ label: "Kind", name: "kind", value: m.kind || "", options: opt(L.kinds), hint: sug ? `suggested — review: ${sug.kind}` : "" }),
        data_class: field({ label: "Data class", name: "data_class", value: m.data_class || "", options: opt(L.data_classes), hint: sug ? `suggested — review: ${sug.data_class}` : "" }),
      };
      const dep = h("select", { multiple: true, id: "dt-dep", size: 4 }, ids.filter((i) => i !== m.id).map((i) => h("option", { value: i, selected: (m.depends_on || []).includes(i) }, i)));
      const depHint = sug ? `suggested — review: ${(sug.depends_on || []).join("; ")}` : "services this one depends on";
      F.depends_on = box("Depends on", "dt-dep", dep, depHint);
      F.depends_on.setError = (t) => { F.depends_on.classList.toggle("invalid", !!t); F.depends_on.lastChild.textContent = t || depHint; };
      ed.replaceChildren(h("h3", { text: s ? `Edit ${s.dir}/atlas-service.json` : "New atlas-service.json" }),
        sug ? h("p", { class: "fine" }, chip("assumption", "suggested — review"), " Every field below is a suggestion, not a fact. Saving confirms it as your review.") : null, form(msg, async () => {
        Object.values(F).forEach((x) => x.setError(""));
        const manifest = { id: F.id.value(), name: F.name.value(), kind: F.kind.value(), data_class: F.data_class.value(), depends_on: [...dep.selectedOptions].map((o) => o.value) };
        await post("/manifests", { dir: F.dir.value(), manifest }).catch((err) => {
          err.onFields = () => { Object.entries(err.fields || {}).forEach(([k, v]) => F[k] && F[k].setError(v)); if (err.code === "bad_dir") F.dir.setError(err.message); };
          throw err;
        });
        say(msg, sug ? "Confirmed." : "Saved.", false); changed(sug ? "Manifest confirmed" : "Manifest saved");
      }, h("div", { class: "form-row" }, F.dir, F.id, F.name, F.kind, F.data_class), F.depends_on, h("div", { class: "sg-row" }, btn(sug ? "Confirm manifest" : "Save manifest"), msg)));
    };
    const col = (label, k) => ({ label, render: (s) => [].concat((s.manifest || {})[k] || "").join(", ") });
    const pending = svc.filter((s) => s.manifest && s.manifest.suggested).length, bulkMsg = out();
    const bulk = (path, label) => h("button", { class: "btn", type: "button", onclick: async (e) => {
      e.target.disabled = true;
      try { const d = await post(path, {}); say(bulkMsg, path.endsWith("suggest") ? `${d.written.length} manifests suggested from ${d.service_dirs} service directories; review them before a run.` : `${d.confirmed.length} manifests confirmed.`, false); changed(label); }
      catch (err) { if (err.code !== "aborted") say(bulkMsg, err.message); }
      e.target.disabled = false;
    } }, label);
    man.replaceChildren(h("p", { class: "fine", text: L.label || "" }),
      h("div", { class: "sg-row" }, bulk("/manifests/suggest", "Suggest manifests"), pending ? bulk("/manifests/confirm", `Confirm all ${pending} suggestions`) : null, bulkMsg),
      svc.length ? table({ caption: "Service manifests", rows: svc, onRow: edit, signal: ctx.signal, columns: [{ label: "directory", key: "dir", mono: true },
        { label: "id", render: (s) => (s.manifest ? s.manifest.id : chip("FAIL", s.error || "unreadable")) }, col("kind", "kind"), col("data class", "data_class"), col("depends on", "depends_on"),
        { label: "review", render: (s) => (s.manifest && s.manifest.suggested ? chip("assumption", "suggested — review") : chip("PASS", "confirmed")) }] })
        : h("p", { class: "fine", text: "No atlas-service.json in this source yet. Suggest manifests from the service directories, then review them." }),
      h("button", { class: "btn quiet", type: "button", onclick: () => edit(null) }, "New service manifest"), ed);
  };
  const loadMan = () => ctx.store.get(ws, "manifests", { signal: ctx.signal }).then(drawMan, (err) => { if (err.code !== "aborted") man.replaceChildren(h("p", { class: "fine", text: `Manifests unavailable: ${err.message}` })); });
  loadMan(); watch(ctx, ["manifests"], loadMan);
  // (d) authorised probes -> start a run, then watch it on the pipeline
  const ta = h("textarea", { id: "dt-probes", rows: 4, placeholder: "web-gw=example.com:443", spellcheck: "false" });
  const auth = checkbox({ label: "I own or am authorised to test these endpoints", name: "authorised" }), prMsg = out();
  const presets = h("fieldset", { class: "dt-presets" }, h("legend", { class: "eyebrow", text: "Public PQ reference endpoints" }));
  ctx.api.get("/api/reference-endpoints", { signal: ctx.signal, quiet: true }).then((R) => {
    presets.append(h("p", { class: "fine", text: R.label }), ...R.endpoints.map((e) => {
      const c = checkbox({ label: `${e.host}:${e.port} — ${e.operator}; expected ${e.expect}`, name: `preset-${e.id}` });
      c.input.value = e.id;
      return c;
    }));
  }, (err) => { if (err.code !== "aborted") presets.append(h("p", { class: "fine", text: "Reference endpoints unavailable." })); });
  const probe = form(prMsg, async () => {
    const typed = ta.value.split("\n").map((s) => s.trim()).filter(Boolean);
    const chosen = [...presets.querySelectorAll("input:checked")].map((i) => i.value);
    if (typed.length && !auth.input.checked) throw new Error("Confirm that you own or are authorised to test the endpoints you typed.");
    await post("/runs", { probes: typed, authorised: auth.input.checked, presets: chosen });
    ctx.navigate(`/w/${ws}/pipeline`);
  }, presets, box("Your endpoints, one SERVICE=HOST:PORT per line", "dt-probes", ta, "leave empty to rescan without your own probes"),
  auth, h("div", { class: "sg-row" }, btn("Start run", "btn primary"), prMsg));
  return [section("Source", h("div", { class: "form-row" }, upload, clone)), section("Service manifests", man), section("Authorised probes", probe)];
}

export async function mount(ctx) {
  await viewCss("graph");
  const intakeEls = [].concat(intake(ctx));
  ctx.root.append(h("div", { class: "grid" }, h("div", { class: "span-12" },
    pageHead(ctx, { route: "detect", title: "Detect", headline: "Red nodes are systems a quantum computer could break. Lines show what depends on what." }),
    dataView(ctx, {
      keys: ["results", "scene", "move", "inventory"],
      skeleton: () => h("div", { class: "grid" }, h("div", { class: "span-12" }, statSkeleton()), h("div", { class: "span-12" }, tableSkeleton(5))),
      render: ({ model: m, move, inventory }) => {
        const d = m && m.detect;
        // not run yet (e.g. a freshly cloned repo): the intake is the next step, so it is shown here, not hidden in details
        if (!d || !d.available) return h("div", { class: "dt-fresh" }, emptyState(notRun(ctx, "Detect")), ...intakeEls);
        ctx.announce(`${d.vulnerable.text} vulnerable findings in ${d.files.text} scanned files.`);
        const r = m.results;
        return h("div", {},
          graphHero(ctx, r, (move && move.observed) || {}, inventory && inventory.available ? inventory.inventory : null),
          keyStats([
            { label: "vulnerable findings", cell: d.vulnerable, unit: "RSA / ECC / DH / DSA", tone: "exposure", mean: "Places in code, configuration or certificates that rely on quantum-breakable crypto." },
            { label: "files scanned", cell: d.files, unit: "code, configs, certificates", mean: "Everything in the source tree was read; nothing was run." },
            { label: "live connections probed", cell: num(d.probes.length, d.files.source), unit: "one TLS handshake each", mean: d.probes.length ? "Real handshakes show what a service actually negotiates." : "No live probe in this run." },
          ]),
          main(h("div", {}, table({ caption: "Static findings", rows: d.findings, signal: ctx.signal,
            expand: (f) => ({ why: `${f.family} used for ${f.use}: quantum-breakable.`, technical: h("span", { class: "mono", text: `${f.file}:${f.line} · rule ${f.rule} · ${(f.snippet || "").slice(0, 160)}` }) }), columns: [
            { label: "file", render: (f) => `${f.file.split("/").pop()}:${f.line}`, mono: true }, { label: "family", render: (f) => chip("HNDL-exposed", f.family) }, { label: "used for", render: (f) => chip("recorded", f.use) }] })), { title: "Findings" }),
          d.probes.length ? main(table({ caption: "Live TLS probes", rows: d.probes, expand: (p) => ({ why: p.drift.length ? `Drift: ${p.drift.join(", ")}` : "Live handshake matches the configuration.", technical: h("span", { class: "mono", text: `${p.endpoint} · cert ${p.cert}` }) }), columns: [
            { label: "service", key: "service" }, { label: "key exchange", render: (p) => p.ok ? chip(/MLKEM/i.test(p.group) ? "hybrid" : "HNDL-exposed", p.group) : chip("FAIL", "no handshake") },
            { label: "drift", render: (p) => p.drift.length ? chip("HNDL-exposed", `${p.drift.length} drift`) : chip("PASS", "none") }] }), { title: "Live connections" }) : null,
          detailsList([
            { title: "How it works", summary: "Pattern rules read code, configs, dependencies and certificates; probes do one handshake.", body: bullets([
              "Every finding has a file, a line and the rule that matched.",
              ["A live probe offers hybrid ", term("mlkem", "ML-KEM"), " and classical groups and records what the server picks."],
              "Nothing in the scanned source is built or executed."]) },
            { title: "Why this method", summary: "You cannot migrate what you have not found, and config can lie.", body: bullets([
              "Static evidence shows where crypto is written down.", "A live handshake shows what is actually used, which catches drift."]) },
            { title: "Evidence & sources", summary: r && r.detect ? `Detect run ${r.detect.run_id.slice(0, 12)} · tree hash ${r.detect.tree_sha256.slice(0, 12)}…` : "not yet run", body: bullets(r && r.detect ? [
              `Run ${r.detect.run_id} at ${r.detect.ts}.`, `Source tree SHA-256 ${r.detect.tree_sha256}.`, "Signed into the Proof Chain first (detect.run)."] : []) },
            { title: "Limits", summary: "Crypto hidden in closed binaries or remote services is out of reach.", body: bullets([
              "TLS on library defaults is marked \"needs live probe\", not counted.", "Probes run only against endpoints you are authorised to test."]) },
            { title: "Add your own system", summary: "Upload a repository, edit service manifests, run authorised probes (operators).", body: h("div", {}, ...intakeEls) }]),
          nextStep(ctx, "detect"));
      },
    }), honesty())));
}
