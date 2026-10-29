// Provenance tooltip: any element with data-prov (JSON {run_id, solver, job_id, ledger_index, ts, note, title})
// shows its source on hover, keyboard focus or tap. One instance for the whole app.
import { append, h } from "../dom.js";

const FIELDS = [["run_id", "run"], ["solver", "solver"], ["job_id", "job id"], ["ledger_index", "ledger"], ["ts", "time"], ["note", "note"]];

export function provAttr(source, title = "") {
  return source ? JSON.stringify({ title, ...source }) : null;
}

export function installTooltip(root = document) {
  const tip = h("div", { class: "tip", role: "tooltip", id: "prov-tip", hidden: true });
  document.body.append(tip);
  let pinned = null, current = null;
  const render = (el) => {
    let p;
    try { p = JSON.parse(el.getAttribute("data-prov")); } catch { return false; }
    tip.replaceChildren(); // append() skips null children (replaceChildren would print "null")
    append(tip, [p.title ? h("p", { class: "tip-title", text: p.title }) : null,
      h("dl", {}, FIELDS.filter(([k]) => p[k] !== undefined && p[k] !== null).map(([k, label]) => [h("dt", { text: label }), h("dd", { text: String(p[k]) })]))]);
    return true;
  };
  const place = (el) => {
    const r = el.getBoundingClientRect();
    tip.hidden = false;
    const w = tip.offsetWidth, ht = tip.offsetHeight;
    let x = Math.min(Math.max(8, r.left), innerWidth - w - 8);
    let y = r.bottom + 8;
    if (y + ht > innerHeight - 8) y = Math.max(8, r.top - ht - 8);
    tip.style.left = `${x}px`; tip.style.top = `${y}px`;
  };
  const show = (el) => { if (el === current && !tip.hidden) return; if (render(el)) { current = el; el.setAttribute("aria-describedby", "prov-tip"); place(el); } };
  const hide = () => { if (current) current.removeAttribute("aria-describedby"); tip.hidden = true; current = null; };
  const target = (e) => e.target instanceof Element ? e.target.closest("[data-prov]") : null;
  root.addEventListener("pointerover", (e) => { if (pinned || e.pointerType === "touch") return; const t = target(e); if (t) show(t); });
  root.addEventListener("pointerout", (e) => { if (pinned) return; const t = target(e); if (t && !t.contains(e.relatedTarget)) hide(); });
  root.addEventListener("focusin", (e) => { const t = target(e); if (t) show(t); });
  root.addEventListener("focusout", () => { if (!pinned) hide(); });
  root.addEventListener("click", (e) => {
    const t = target(e);
    if (t && t.matches(".prov, .num, [data-prov-tap]")) { pinned = pinned === t ? null : t; if (pinned) show(t); else hide(); }
    else if (pinned) { pinned = null; hide(); }
  });
  addEventListener("keydown", (e) => { if (e.key === "Escape") { pinned = null; hide(); } });
  addEventListener("scroll", () => { if (current) place(current); }, { passive: true });
  return { hide };
}
