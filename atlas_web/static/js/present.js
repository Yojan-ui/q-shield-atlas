// Presenter mode: P (or the top-bar "Present" button) on any workspace tours the seven pipeline pages in display
// order. Each page holds 8 s with one large caption built from that workspace's real results; ← → move manually,
// Esc exits. While presenting, the sidebar and fine print are hidden and the 3D stage fills the screen.
// Captions and styles load lazily so the first load stays small.
import { FLOW } from "./flow.js";

const HOLD_MS = 8000;

export function installPresenter({ navigate, store, getWs }) {
  let on = false, i = 0, timer = 0, cap = null, ws = null, facts = {};
  const caption = () => {
    const f = FLOW[i], x = facts[f.id];
    cap.textContent = `${i + 1} / ${FLOW.length} · ${f.label}: ${x ? `${x.num} ${x.mean}` : f.does || "not yet run"}`;
  };
  const show = (k) => {
    i = Math.max(0, Math.min(FLOW.length - 1, k));
    navigate(`/w/${encodeURIComponent(ws)}/${FLOW[i].route}`);
    caption();
    clearTimeout(timer);
    timer = setTimeout(() => (i < FLOW.length - 1 ? show(i + 1) : (cap.textContent += " · end of tour, Esc to exit")), HOLD_MS);
  };
  const start = async () => {
    ws = getWs();
    if (on || !ws) return;
    on = true;
    if (!document.querySelector('link[data-view-css="present"]')) document.head.append(Object.assign(document.createElement("link"), { rel: "stylesheet", href: "/assets/css/views/present.css" }));
    document.querySelector('link[href="/assets/css/views/present.css"]')?.setAttribute("data-view-css", "present");
    cap = cap || Object.assign(document.createElement("div"), { className: "pr-cap" });
    cap.setAttribute("role", "status"); cap.setAttribute("aria-live", "polite");
    document.body.append(cap);
    document.body.classList.add("presenting");
    try {
      const [{ flowFacts }, res, rv] = await Promise.all([import("./components/overview.js"), store.get(ws, "results"), store.get(ws, "reviews").catch(() => null)]);
      facts = flowFacts(res.results, rv) || {};
    } catch { facts = {}; }
    show(0);
  };
  const stop = () => { on = false; clearTimeout(timer); document.body.classList.remove("presenting"); if (cap) cap.remove(); };
  addEventListener("keydown", (e) => {
    if (e.target instanceof Element && e.target.closest("input, textarea, select, dialog, [contenteditable]")) return;
    if (!on && (e.key === "p" || e.key === "P") && !e.metaKey && !e.ctrlKey && !e.altKey) { e.preventDefault(); start(); return; }
    if (!on) return;
    if (e.key === "Escape") stop();
    else if (e.key === "ArrowRight") show(i + 1);
    else if (e.key === "ArrowLeft") show(i - 1);
    else return;
    e.preventDefault(); e.stopImmediatePropagation();  // pages' own arrow keys (weeks, steps) yield to the tour
  }, { capture: true });
  addEventListener("atlas:present", start);
  return { start, stop, active: () => on };
}
