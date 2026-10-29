// Overview: the seven pipeline steps as cards (what each does, hands on, key number, backend), three key numbers and
// the run controls. Stations, the live log and preflight sit in the collapsed details. Runs stream SSE step events.
import { h, icon } from "../dom.js";
import { chip } from "../components/chip.js";
import { logConsole } from "../components/log.js";
import { lines } from "../components/states.js";
import { toast } from "../components/toast.js";
import { provAttr } from "../components/tooltip.js";
import { confirmDialog } from "../components/dialog.js";
import { num, missing, solverLabel, source, STAGE_OF, STEPS, stationsModel } from "../model.js";
import { honesty, mountScene, stage, viewCss } from "./common.js";
import { FLOW } from "../flow.js";
import { buildPillars } from "../scenes/pillars.js";
import { guidedRun } from "../components/guided.js";
import { flowCards, flowFacts } from "../components/overview.js";
import { bullets, detailsList, keyStats, main, nextStep, pageHead } from "../components/page.js";
import { term } from "../glossary.js";

// station model (step -> status) -> one state per flow step: fail > running > ok (all steps ok) > idle
const STATE = { ok: "ok", fail: "fail", running: "running", pending: "idle", idle: "idle" };
export function flowStates(model) {
  return FLOW.map((f) => {
    const st = model.filter((s) => f.stages.includes(s.stage.id)).map((s) => STATE[s.status] || "idle");
    return !st.length ? "missing" : st.includes("fail") ? "fail" : st.includes("running") ? "running" : st.every((x) => x === "ok") ? "ok" : "idle";
  });
}

// no run recorded in this workspace's run log (e.g. a snapshot or a copied workspace): what results.json holds
export const resultStates = (facts) => FLOW.map((f) => (facts[f.id] ? "ok" : "missing"));

export async function mount(ctx) {
  await Promise.all([viewCss("pillars"), viewCss("guided"), viewCss("graph")]);
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
  const ovEl = h("div", {}, lines(3));
  let current = {}; // step -> {status, duration}
  // guided run (non-demo workspaces): 3D stage per step + live log; replays the latest recorded run on request
  const guided = guidedRun(ctx, { canRun: !ro });  // read-only demo: replay of the recorded run only
  const replayBtn = guided ? h("button", { class: "btn", type: "button", onclick: () => guided.replay() }, icon("rewind"), "Replay last run") : null;
  // 3D: the seven steps as columns, lit from the real run status; the running step pulses (live SSE step events)
  const labels3d = h("div", { class: "gr-labels", "aria-hidden": "true" });
  const stageEl = stage(ctx, { label: "The seven pipeline steps as columns: green done, red failed, white pulsing running, grey not run.", fallback: h("span") });
  stageEl.append(labels3d);
  const items3d = FLOW.map((f, i) => ({ id: f.id, label: `${i + 1} ${f.label}`, h: 0.55, state: "idle" }));
  let layer3d = null, lastStates = items3d.map((x) => x.state);
  const mountRow = () => { ctx.world.frameStage(stageEl); ctx.stageEl = stageEl; stageEl.hidden = false;
    return mountScene(ctx, "pipeline", { available: true }, (env) => buildPillars(env, items3d, { labelsEl: labels3d, stageEl, reduced: ctx.world.reduced,
      onPick: (it) => { const f = FLOW.find((x) => x.id === it.id); if (f) ctx.navigate(`/w/${ctx.ws}/${f.route}`); } }))
      .then((l) => { layer3d = l; if (l) lastStates.forEach((st, i) => l.set(i, st)); }).catch(() => {}); };
  mountRow();
  if (guided) guided.onToggle((open) => { if (open) { layer3d = null; stageEl.hidden = true; } else mountRow(); });  // one stage owns the world at a time
  if (guided && ctx.query.get("guided")) guided.replay();  // landing "See it run"

  const drawStations = (model) => {
    lastStates = flowStates(model);
    lastStates.forEach((st, i) => { items3d[i].state = st; if (layer3d) layer3d.set(i, st); });
    stationsEl.replaceChildren(...model.map((s) => h("li", { class: `station ${s.status}`, "aria-label": `${STAGE_OF[s.step].label} stage, step ${s.step}: ${s.status}` },
      h("span", { class: "s-idx", text: String(s.index).padStart(2, "0") }),
      h("span", { class: "s-name" }, h("span", { class: "s-stage", text: STAGE_OF[s.step].label }), h("span", { class: "s-step mono", text: s.step })),
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
    const reviews = await ctx.store.get(ctx.ws, "reviews", { signal: ctx.signal }).catch(() => null);
    const v = r && r.ledger_verification, src = r ? source(r, { run_id: r.detect ? r.detect.run_id : "n/a", solver: "detect/", ts: r.generated_at }) : null;
    ovEl.replaceChildren(r ? keyStats([
      { label: "systems to migrate", cell: num(r.assets.length, src), unit: "use RSA / ECC today", mean: "Systems whose encryption a future quantum computer could break." },
      { label: "weeks to migrate", cell: r.exposure ? num(r.exposure.makespan_weeks, source(r, { run_id: (r.solver_runs[0] || {}).run_id, solver: solverLabel(r), ts: r.generated_at })) : missing(), unit: "optimised plan", mean: "How long the whole move takes at the assumed team capacity." },
      { label: "proof records", cell: r.ledger ? num(r.ledger.entry_count, src) : missing(), unit: v && v.ok ? "signed and verified" : "signed", mean: "Every result is signed; any later edit is detected." },
    ]) : null, main(flowCards(ctx, r, reviews), { title: "The seven steps" }));
    if (ro) {
      log.replaceWith(h("p", { class: "fine", style: { padding: "var(--s-4) 0" }, text: "This snapshot was produced by ./run_demo.sh in a terminal (its step logs are in out/demo_logs/). Runs started from this page stream their output here, line by line." }));
      drawStations(STEPS.map((step, i) => ({ step, stage: STAGE_OF[step], index: i + 1, status: r ? "ok" : "idle", duration: missing(r ? "snapshot" : "not yet run") })));
      status.replaceChildren(r ? chip("recorded", `snapshot from ./run_demo.sh, results.json ${r.generated_at}`) : chip("not yet run"));
    } else {
      drawStations(stationsModel(runs));
      if (!last && r) { lastStates = resultStates(flowFacts(r)); lastStates.forEach((st, i) => { items3d[i].state = st; if (layer3d) layer3d.set(i, st); }); }
      status.replaceChildren(last ? chip(["PASS", "running", "INTERRUPTED"].includes(last.status) ? last.status : "FAIL", `${last.kind} run ${last.id} · ${last.status}`) : chip("not yet run", "no run in this workspace yet"));
      if (last && !["PASS", "running"].includes(last.status) && last.detail.tail) showTail(last.detail.tail, last.detail.hint);
      if (runs.active) follow(runs.active);
    }
  };

  const showTail = (lns, hint = null) => {
    tail.replaceChildren(hint ? h("div", { class: "state error", role: "alert", style: { padding: "var(--s-4) 0" } },
      h("h2", { text: hint.title }), h("p", { text: hint.message }), h("p", { text: hint.fix }),
      hint.code === "capacity_infeasible" ? h("div", { class: "actions" }, h("a", { class: "btn primary", href: `/w/${ctx.ws}/schedule`, text: "Open assumptions" })) : null) : "",h("p", { class: "eyebrow", style: { color: "var(--exposure)" }, text: "last 40 lines of the failed step" }),
      h("pre", { class: "log", style: { height: "auto", maxHeight: "320px", padding: "var(--s-3)", margin: 0, whiteSpace: "pre-wrap" }, text: lns.join("\n") }));
  };

  let es = null;
  const follow = (runId) => {
    if (es) es.close();
    const det = ctx.root.querySelector(".pg-details");  // a live run shows its stations and log in any mode
    if (det) { det.classList.remove("tech"); det.querySelector("details").open = true; }
    log.clear(); tail.replaceChildren();
    current = Object.fromEntries(STEPS.map((s) => [s, { status: "pending" }]));
    es = new EventSource(`/api/workspaces/${ctx.ws}/runs/${runId}/events`);
    if (guided) guided.start(runId);
    const draw = () => drawStations(STEPS.map((step, i) => ({ step, stage: STAGE_OF[step], index: i + 1, status: current[step].status,
      duration: current[step].dur !== undefined ? num(current[step].dur, { run_id: runId, solver: "atlas_web runner", job_id: "none", ledger_index: "n/a", ts: new Date().toISOString() }, 1) : missing(current[step].status) })));
    draw();
    runBtn.disabled = true;
    es.addEventListener("step_start", (e) => { const d = JSON.parse(e.data); if (current[d.step]) { current[d.step].status = "running"; draw(); } log.push(`$ python ${d.argv.join(" ")}`, d.step); if (guided) guided.stepStart(d.step); });
    es.addEventListener("line", (e) => { const d = JSON.parse(e.data); log.push(d.text, d.step); if (guided) guided.line(d.text); });
    es.addEventListener("step_end", (e) => { const d = JSON.parse(e.data); if (current[d.step]) { current[d.step] = { status: d.exit_code === 0 ? "ok" : "fail", dur: d.duration_s }; draw(); ctx.announce(`${d.step} ${d.exit_code === 0 ? "done" : "failed"} in ${d.duration_s} seconds`); } if (guided) guided.stepEnd(d.step, d.exit_code, d.duration_s); });
    es.addEventListener("run_end", (e) => {
      const d = JSON.parse(e.data);
      es.close(); es = null;
      runBtn.disabled = !canRun;
      status.replaceChildren(chip(d.status, `run ${runId} · ${d.status} in ${d.duration_s} s`));
      if (d.status !== "PASS") showTail(d.tail, d.hint);
      toast(d.status === "PASS" ? "Pipeline finished: PASS" : "Pipeline failed", { tone: d.status === "PASS" ? "success" : "error" });
      ctx.store.invalidate(ctx.ws, ["results", "scene", "ledger", "runs", "calibration", "move", "inventory", "reviews"]);
      if (guided) guided.end(d.status);
    });
    es.onerror = () => { if (es && es.readyState === EventSource.CLOSED) { es = null; runBtn.disabled = !canRun; } };
  };
  ctx.signal.addEventListener("abort", () => { if (es) es.close(); });

  runBtn.addEventListener("click", async () => {
    const ok = await confirmDialog({ title: "Run the pipeline?", body: `Runs the ${STEPS.length} steps of run_demo.sh in workspace ${ctx.ws}: lab TLS services start on 127.0.0.1 and stop afterwards. Local only; no QpiAI credits are used.`, confirm: "Run" });
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

  const runDetails = detailsList([
    { title: "How it works", summary: "Each step runs an existing command-line module; results pass between them as signed JSON.", body: h("div", {},
      bullets(["Detect scans code and probes connections, then the Proof Chain signs that evidence first.",
        ["The plan is a ", term("milp", "MILP"), " solved by QpiAI Opt; one week is cross-checked with ", term("qaoa", "QAOA"), "."],
        ["Lab gates test real ", term("tls", "TLS handshakes"), "; everything is sealed into the ", term("ledger"), "."]]),
      h("p", { class: "eyebrow", text: "run stations" }), stationsEl, h("p", { class: "eyebrow", text: "run output" }), log, tail) },
    { title: "Why this method", summary: "Exact planning where it matters, measured checks everywhere else.", body: bullets([
      "Scheduling needs a proven best plan, so it uses an exact optimiser rather than a heuristic.",
      "Every claim on screen comes from a logged run with its timestamp and hash."]) },
    { title: "Evidence & sources", summary: "Solver record and preflight checks for this workspace.", body: h("div", {}, solverEl, why, h("p", { class: "eyebrow", text: "preflight" }), pre) },
    { title: "Limits", summary: "A lab demonstration: no real production system is changed.", body: bullets([
      "Lab services run on 127.0.0.1; real systems are only observed, never modified.",
      "Effort, risk and shelf-life values are assumptions in config/assumptions.json.",
      "QAOA runs on simulators; no quantum advantage is claimed."]) }]);
  ctx.root.append(h("div", { class: "grid" }, h("div", { class: "span-12" },
    pageHead(ctx, { route: "pipeline", title: "Overview", headline: "Where does each system stand on its way to post-quantum encryption, and what happens next?", actions: [runBtn, replayBtn, status] }),
    guided ? guided.el : null,
    stageEl, h("p", { class: "mv-how", text: "How to read this: one column per pipeline step, lit from this workspace's real run status: green done, red failed, white pulsing while it runs, grey not run. Click a column to open that step." }),
    ovEl, runDetails, nextStep(ctx, "pipeline", { route: "detect", text: "Start: 1 Detect" }), honesty())));
  drawStations(STEPS.map((step, i) => ({ step, stage: STAGE_OF[step], index: i + 1, status: "idle", duration: missing("…") })));
  try { await load(); } catch (err) { if (err.code !== "aborted") status.replaceChildren(chip("FAIL", err.message)); }
  preflight();
  const off = ctx.store.subscribe(({ ws, keys }) => { if (ws === ctx.ws && (keys.includes("results") || keys.includes("runs")) && !es) load().catch(() => {}); });
  ctx.signal.addEventListener("abort", off);
  ctx.announce(`Overview for workspace ${ctx.ws}: seven pipeline steps.`);
}
