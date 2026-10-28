// Entry point: fetch out/results.json (the only data source), build the model, render 2D by default.
// URL parameters (used for screenshots): ?view=3d&week=N&scenario=NAME
import { buildModel, NOT_YET_RUN } from "./data.js";
import { cellNode, installTooltips, render2d } from "./render2d.js";

const $ = (id) => document.getElementById(id);
const params = new URLSearchParams(location.search);

function notice(text) {
  const n = $("notice");
  n.textContent = text;
  n.hidden = false;
}

function select(view) {
  $("view-2d").hidden = view !== "2d";
  $("view-3d").hidden = view !== "3d";
  $("btn-2d").setAttribute("aria-selected", String(view === "2d"));
  $("btn-3d").setAttribute("aria-selected", String(view === "3d"));
}

async function start3d(model) {
  const { createTower, hasWebGL, beamListItems } = await import("./render3d.js");
  if (!hasWebGL()) throw new Error("WebGL is not available in this browser");
  const t = model.tower;
  if (!t.available) throw new Error(`tower data ${NOT_YET_RUN}`);
  const week = $("week"), sc = $("scenario");
  week.max = String(t.weeks[t.weeks.length - 1]);
  week.min = String(t.weeks[0]);
  sc.replaceChildren(...t.scenarios.map((s) => new Option(`${s.name} (${s.year})`, s.name)));
  if (params.get("scenario")) sc.value = params.get("scenario");
  if (params.get("week")) week.value = params.get("week");
  const tower = createTower($("tower-canvas"), t, (scenario, w) => {
    $("week-out").textContent = String(w);
    const floor = t.floors[scenario].find((f) => f.week === w);
    $("tower-floor").replaceChildren(
      Object.assign(document.createElement("span"), { textContent: "remaining exposure-years" }),
      floor ? cellNode(floor.cell) : cellNode(null));
    $("beams").replaceChildren(...beamListItems(t, w));
  });
  const redraw = () => tower.build(sc.value, Number(week.value));
  week.addEventListener("input", redraw);
  sc.addEventListener("change", redraw);
  redraw();
}

async function main() {
  $("banner").textContent = "Loading…";
  installTooltips($("tip"));
  let results;
  try {
    const res = await fetch("/out/results.json", { cache: "no-store" });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    results = await res.json();
  } catch (e) {
    results = null;
    notice(`out/results.json could not be loaded (${e.message}); every section shows "${NOT_YET_RUN}".`);
  }
  const model = buildModel(results);
  $("banner").textContent = model.banner;
  $("footer").textContent = `results.json generated_at ${model.generated_at}. Hover or tap any underlined value for its source (run_id, solver/backend, job_id, timestamp).`;
  render2d($("view-2d"), model);

  let has3d = false;
  try { has3d = (await import("./render3d.js")).hasWebGL(); } catch { has3d = false; }
  const btn3d = $("btn-3d");
  if (!has3d) {
    btn3d.disabled = true;
    $("webgl-note").textContent = "3D needs WebGL (not available here); showing 2D.";
  }
  let started = false;
  const go3d = async () => {
    try {
      if (!started) { await start3d(model); started = true; }
      select("3d");
    } catch (e) {
      select("2d");
      btn3d.disabled = true;
      notice(`3D view unavailable (${e.message}). Showing the 2D view.`);
    }
  };
  $("btn-2d").addEventListener("click", () => select("2d"));
  btn3d.addEventListener("click", go3d);
  select("2d");
  if (params.get("view") === "3d") {
    if (has3d) await go3d();
    else notice("3D view requested but WebGL is not available. Showing the 2D view.");
  }
  document.body.dataset.ready = "1";
}

main();
