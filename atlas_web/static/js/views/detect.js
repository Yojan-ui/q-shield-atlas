// Detect: the codebase as a file city, inventory tables (also the no-WebGL fallback), operator intake.
import { h } from "../dom.js";
import { readCookie } from "../api.js";
import { stat, statSkeleton } from "../components/stat.js";
import { chip } from "../components/chip.js";
import { table, tableSkeleton } from "../components/table.js";
import { emptyState } from "../components/states.js";
import { field, checkbox } from "../components/form.js";
import { toast } from "../components/toast.js";
import { buildCity } from "../scenes/detect.js";
import { dataView, header, honesty, mountScene, notRun, section, stage, wsEyebrow } from "./common.js";

const say = (el, t, bad = true) => { el.textContent = t; el.classList.toggle("bad", bad); };
const out = () => h("p", { class: "fine dt-msg" }), btn = (t, cls = "btn") => h("button", { class: cls, type: "submit" }, t);
const box = (label, id, input, hint = "") => h("div", { class: "field" }, h("label", { for: id, text: label }), input, h("div", { class: "hint", text: hint }));
const watch = (ctx, keys, fn) => { const off = ctx.store.subscribe(({ ws, keys: k }) => { if (ws === ctx.ws && k.some((x) => keys.includes(x))) fn(); }); ctx.signal.addEventListener("abort", off, { once: true }); };

function city(ctx) {
  const tip = h("div", { class: "stage-tip", hidden: true }), note = h("p", { class: "fine stage-note" });
  const legend = h("div", { class: "stage-legend", hidden: true }, [["exposure", "RSA / ECC / DH / DSA finding"], ["accent", "PQC finding"], ["hairline-strong", "dark: no findings"], ["caution", "pulsing: service drift"]]
    .map(([c, t]) => h("span", {}, h("i", { class: "dt-key", style: { background: `var(--${c})` } }), t)));
  const el = stage(ctx, { label: "The scanned codebase as a city: one column per file, findings glow at their line.", fallback: h("p", { class: "fine", text: "File city needs WebGL." }) });
  el.append(note, legend, tip);
  const draw = async () => {
    const [scene, res] = await Promise.all(["scene", "results"].map((k) => ctx.store.get(ctx.ws, k, { signal: ctx.signal })));
    const F = scene && scene.files, files = F && F.verified ? F.files || [] : [], asset = {};
    note.textContent = !F ? "Scanned files: not yet run." : !F.verified ? F.status_text || "file listing not verified" : files.length ? "" : "No files scanned.";
    legend.hidden = !files.length;
    for (const a of (res && res.results && res.results.assets) || []) { asset[a.id] = a.id; for (const e of a.evidence || []) asset[e.file] ||= a.id; }
    const of = (f) => asset[f.path] || (f.service && asset[f.service]) || null;
    await mountScene(ctx, "detect", scene, ({ THREE, world, group }) => {
      if (!files.length) return {};
      const c = buildCity(THREE, group, files, world.uniforms);
      return {
        pickables: c.pickables,
        hover(hit, e) {
          const v = c.resolve(hit);
          tip.hidden = !v; el.style.cursor = v && of(v.file) ? "pointer" : "";
          if (!v) return;
          const { file: f, finding: g } = v, id = of(f), b = el.getBoundingClientRect(), x = e.clientX - b.left;
          tip.textContent = (g ? `${f.path}:${g.line} · ${g.rule} · ${g.family}` : `${f.path} · ${f.lines} lines · ${(f.findings || []).length} findings`) + (f.drift ? " · drift" : "") + (id ? ` · asset ${id}` : "");
          Object.assign(tip.style, { left: `${x > b.width - 320 ? Math.max(0, x - 320) : x + 14}px`, top: `${e.clientY - b.top + 14}px` });
        },
        click(hit) { const v = c.resolve(hit), id = v && of(v.file); if (id) ctx.navigate(`/w/${ctx.ws}/asset/${encodeURIComponent(id)}`); },
      };
    });
  };
  const run = () => draw().catch((err) => { if (err.code !== "aborted") note.textContent = `File city unavailable: ${err.message}`; });
  run(); watch(ctx, ["scene", "results"], run);
  return el;
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
  ctx.root.append(h("div", { class: "grid" },
    h("div", { class: "span-12" }, header({ eyebrow: wsEyebrow(ctx), title: "Detect", lede: "Where RSA, ECC and DH live in this system: a static scan with file:line evidence, owner-declared service manifests, and live TLS probes that catch drift between config and reality." })),
    h("div", { class: "span-12" }, city(ctx)),
    h("div", { class: "span-12" }, dataView(ctx, {
      skeleton: () => h("div", { class: "grid" }, h("div", { class: "span-12" }, statSkeleton()), h("div", { class: "span-12" }, tableSkeleton(5))),
      render: ({ model: m }) => {
        const d = m && m.detect;
        if (!d || !d.available) return emptyState(notRun(ctx, "Inventory"));
        ctx.announce(`${d.assets.text} assets to migrate, ${d.vulnerable.text} vulnerable findings in ${d.files.text} scanned files, ${d.drift.text} drift cases.`);
        return h("div", { class: "grid" },
          h("div", { class: "span-12 stats" },
            stat({ label: "files scanned", cell: d.files, unit: "code, configs, certificates" }),
            stat({ label: "vulnerable findings", cell: d.vulnerable, unit: "RSA / ECC / DH / DSA", tone: "hero exposure" }),
            stat({ label: "assets to migrate", cell: d.assets, unit: `not vulnerable: ${d.notVulnerable.join(", ") || "none"}` }),
            stat({ label: "drift", cell: d.drift, unit: "static vs live handshake" })),
          section("Services", table({ caption: "Services to migrate", rows: m.assets, rowHref: (a) => `/w/${ctx.ws}/asset/${encodeURIComponent(a.id)}`, signal: ctx.signal, columns: [
            { label: "service", render: (a) => h("span", {}, a.name, h("span", { class: "sub mono", text: a.id })) },
            { label: "kind", key: "kind", optional: true }, { label: "data class", key: "data_class", optional: true }, { label: "algorithm", key: "algorithm", mono: true, optional: true },
            { label: "findings", key: "findings", numeric: true }, { label: "status", render: (a) => chip(a.status) }] })),
          section("Live probes", d.probes.length ? table({ caption: "Live TLS probes", rows: d.probes, columns: [
            { label: "service", key: "service" }, { label: "endpoint", key: "endpoint", mono: true }, { label: "negotiated", render: (p) => p.ok ? p.group : chip("FAIL", "no handshake") },
            { label: "certificate", key: "cert", mono: true }, { label: "drift", render: (p) => p.drift.length ? h("span", {}, p.drift.map((k) => chip("HNDL-exposed", k))) : chip("PASS", "none") }] })
            : h("p", { class: "fine", text: "No live probe in this run." })),
          section("Findings", table({ caption: "Static findings", rows: d.findings, signal: ctx.signal, columns: [
            { label: "file:line", render: (f) => `${f.file}:${f.line}`, mono: true }, { label: "family", key: "family" }, { label: "use", key: "use" },
            { label: "rule", key: "rule", mono: true, optional: true }, { label: "snippet", optional: true, render: (f) => h("span", { class: "mono fine", text: (f.snippet || "").slice(0, 80) }) }] })));
      },
    })),
    intake(ctx),
    h("div", { class: "span-12" }, honesty())));
}
