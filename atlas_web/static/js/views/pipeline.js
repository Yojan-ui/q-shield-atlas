// Pipeline: the 11 run_demo.sh steps as stations. Run streams SSE step events; failure shows the log tail.
import { h, icon } from "../dom.js";
import { chip } from "../components/chip.js";
import { logConsole } from "../components/log.js";
import { lines } from "../components/states.js";
import { toast } from "../components/toast.js";
import { provAttr } from "../components/tooltip.js";
import { confirmDialog } from "../components/dialog.js";
import { num, missing, solverLabel, source, STEPS, stationsModel } from "../model.js";
import { header, honesty, mountScene, section, stage, wsEyebrow } from "./common.js";
import { buildLattice } from "../engine/lattice.js";

export async function mount(ctx) {
  const ro = !ctx.wsInfo || ctx.wsInfo.read_only;
  const canRun = ctx.me.role !== "viewer" && !ro;
  const runBtn = h("button", { class: "btn primary", type: "button", disabled: !canRun }, icon("play"), "Run pipeline");
  const why = h("p", { class: "fine", text: ro ? "The demo workspace is the read-only DEMO.md snapshot. Create a workspace to run on your own data."
    : ctx.me.role === "viewer" ? "Viewers can watch runs; an operator starts them." : "Local only: no QpiAI platform or QCloud jobs are submitted." });
  const stationsEl = h("ol", { class: "stations", "aria-label": "Pipeline stations" });
  const solverEl = h("p", { class: "mono", style: { margin: 0 } });
  const log = logConsole({ label: "pipeline output", signal: ctx.signal });
  const status = h("div", { class: "sg-row" });
  const tail = h("div");
  const pre = h("div", {}, lines(4));
  let current = {}; // step -> {status, duration}

  const drawStations = (model) => {
    stationsEl.replaceChildren(...model.map((s) => h("li", { class: `station ${s.status}`, "aria-label": `${s.step}: ${s.status}` },
      h("span", { class: "s-idx", text: String(s.index).padStart(2, "0") }), h("span", { class: "s-name", text: s.step }),
      s.duration.kind === "number" ? h("span", { class: "s-dur num", tabindex: "0", "data-prov": provAttr(s.duration.source, `${s.step} duration`), text: `${s.duration.text} s` })
        : h("span", { class: "s-dur", text: s.duration.text }))));
  };

  const load = async () => {
    const [res, runs] = await Promise.all([ctx.store.get(ctx.ws, "results", { signal: ctx.signal }),
      ro ? Promise.resolve({ runs: [], active: null }) : ctx.store.get(ctx.ws, "runs", { signal: ctx.signal })]);
    const r = res.results;
    const sr = r && r.solver_runs && r.solver_runs[0];
    solverEl.replaceChildren(sr ? h("span", { class: "num", tabindex: "0", "data-prov": provAttr(source(r, { run_id: sr.run_id, solver: sr.solver, job_id: sr.job_id, job_id_reason: sr.job_id_reason, ts: sr.ts }), "schedule solver record"), text: solverLabel(r) })
      : h("span", { class: "fine", text: "schedule: not yet run" }));
    const last = runs.runs[0];
    if (ro) {
      log.replaceWith(h("p", { class: "fine", style: { padding: "var(--s-4) 0" }, text: "This snapshot was produced by ./run_demo.sh in a terminal (its step logs are in out/demo_logs/). Runs started from this page stream their output here, line by line." }));
      drawStations(STEPS.map((step, i) => ({ step, index: i + 1, status: r ? "ok" : "idle", duration: missing(r ? "snapshot" : "not yet run") })));
      status.replaceChildren(r ? chip("recorded", `snapshot from ./run_demo.sh, results.json ${r.generated_at}`) : chip("not yet run"));
    } else {
      drawStations(stationsModel(runs));
      status.replaceChildren(last ? chip(["PASS", "running", "INTERRUPTED"].includes(last.status) ? last.status : "FAIL", `${last.kind} run ${last.id} · ${last.status}`) : chip("not yet run", "no run in this workspace yet"));
      if (last && !["PASS", "running"].includes(last.status) && last.detail.tail) showTail(last.detail.tail);
      if (runs.active) follow(runs.active);
    }
  };

  const showTail = (lns) => {
    tail.replaceChildren(h("p", { class: "eyebrow", style: { color: "var(--exposure)" }, text: "last 40 lines of the failed step" }),
      h("pre", { class: "log", style: { height: "auto", maxHeight: "320px", padding: "var(--s-3)", margin: 0, whiteSpace: "pre-wrap" }, text: lns.join("\n") }));
  };

  let es = null;
  const follow = (runId) => {
    if (es) es.close();
    log.clear(); tail.replaceChildren();
    current = Object.fromEntries(STEPS.map((s) => [s, { status: "pending" }]));
    es = new EventSource(`/api/workspaces/${ctx.ws}/runs/${runId}/events`);
    const draw = () => drawStations(STEPS.map((step, i) => ({ step, index: i + 1, status: current[step].status,
      duration: current[step].dur !== undefined ? num(current[step].dur, { run_id: runId, solver: "atlas_web runner", job_id: "none", ledger_index: "n/a", ts: new Date().toISOString() }, 1) : missing(current[step].status) })));
    draw();
    runBtn.disabled = true;
    es.addEventListener("step_start", (e) => { const d = JSON.parse(e.data); if (current[d.step]) { current[d.step].status = "running"; draw(); } log.push(`$ python ${d.argv.join(" ")}`, d.step); });
    es.addEventListener("line", (e) => { const d = JSON.parse(e.data); log.push(d.text, d.step); });
    es.addEventListener("step_end", (e) => { const d = JSON.parse(e.data); if (current[d.step]) { current[d.step] = { status: d.exit_code === 0 ? "ok" : "fail", dur: d.duration_s }; draw(); ctx.announce(`${d.step} ${d.exit_code === 0 ? "done" : "failed"} in ${d.duration_s} seconds`); } });
    es.addEventListener("run_end", (e) => {
      const d = JSON.parse(e.data);
      es.close(); es = null;
      runBtn.disabled = !canRun;
      status.replaceChildren(chip(d.status, `run ${runId} · ${d.status} in ${d.duration_s} s`));
      if (d.status !== "PASS") showTail(d.tail);
      toast(d.status === "PASS" ? "Pipeline finished: PASS" : "Pipeline failed", { tone: d.status === "PASS" ? "success" : "error" });
      ctx.store.invalidate(ctx.ws, ["results", "scene", "ledger", "runs", "calibration"]);
    });
    es.onerror = () => { if (es && es.readyState === EventSource.CLOSED) { es = null; runBtn.disabled = !canRun; } };
  };
  ctx.signal.addEventListener("abort", () => { if (es) es.close(); });

  runBtn.addEventListener("click", async () => {
    const ok = await confirmDialog({ title: "Run the pipeline?", body: `Runs the 11 steps of run_demo.sh in workspace ${ctx.ws}: lab TLS services start on 127.0.0.1 and stop afterwards. Local only; no QpiAI credits are used.`, confirm: "Run" });
    if (!ok) return;
    try {
      const res = await ctx.api.post(`/api/workspaces/${ctx.ws}/runs`, {});
      follow(res.run_id);
    } catch (err) { toast(err.message, { tone: "error", detail: err.code }); }
  }, { signal: ctx.signal });

  const preflight = async () => {
    if (ctx.me.role === "viewer") { pre.replaceChildren(h("p", { class: "fine", text: "Preflight checks are visible to operators and admins." })); return; }
    try {
      const p = await ctx.api.get(`/api/preflight${ro ? "" : `?ws=${ctx.ws}`}`, { signal: ctx.signal });
      pre.replaceChildren(h("ul", { class: "checks" }, p.checks.map((c) => h("li", {}, chip(c.ok ? "PASS" : "FAIL", c.ok ? "ok" : "fix"),
        h("div", {}, h("span", { text: c.detail }), c.fix ? h("span", { class: "fix", text: c.fix }) : null))),
        ...["opt", "qcloud"].map((k) => h("li", {}, chip(p.platform[k].enabled ? "PASS" : "NOT_RUN", p.platform[k].enabled ? "enabled" : "disabled"),
          h("div", {}, h("span", { text: k === "opt" ? "QpiAI Opt platform (paid, admin-only)" : "QCloud QAOA sampling (paid, admin-only)" }),
            p.platform[k].status_text ? h("span", { class: "fix", style: { color: "var(--text-2)" }, text: p.platform[k].status_text }) : null)))));
    } catch (err) { if (err.code !== "aborted") pre.replaceChildren(h("p", { class: "fine", text: `preflight unavailable: ${err.message}` })); }
  };

  const stageEl = stage(ctx, { label: "The workspace's services in THE LATTICE; the world reflects the latest results of this workspace." });
  ctx.store.get(ctx.ws, "scene", { signal: ctx.signal }).then((scene) => mountScene(ctx, "pipeline", scene, ({ THREE, world, group }) => {
    buildLattice(THREE, group, scene, world.uniforms); world.uniforms.uWeek.value = 1e6; return {};
  })).catch(() => {});
  ctx.root.append(h("div", { class: "grid" },
    h("div", { class: "span-12" }, header({ eyebrow: wsEyebrow(ctx), title: "Pipeline", lede: "The eleven steps of run_demo.sh, run as the existing module CLIs with this workspace's paths. Each station lights when its step completes.",
      aside: h("div", { class: "hero-figure" }, h("p", { class: "eyebrow", text: "schedule solver" }), solverEl, why), actions: [runBtn, status] })),
    section("Stations", stationsEl),
    h("div", { class: "span-12" }, stageEl),
    h("div", { class: "span-8" }, section("Output", h("div", {}, log, tail))),
    h("div", { class: "start-9" }, section("Preflight", pre)),
    h("div", { class: "span-12" }, honesty())));
  drawStations(STEPS.map((step, i) => ({ step, index: i + 1, status: "idle", duration: missing("…") })));
  try { await load(); } catch (err) { if (err.code !== "aborted") status.replaceChildren(chip("FAIL", err.message)); }
  preflight();
  const off = ctx.store.subscribe(({ ws, keys }) => { if (ws === ctx.ws && (keys.includes("results") || keys.includes("runs")) && !es) load().catch(() => {}); });
  ctx.signal.addEventListener("abort", off);
  ctx.announce(`Pipeline for workspace ${ctx.ws}: eleven stations.`);
}
