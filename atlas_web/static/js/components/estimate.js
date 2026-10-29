// Time estimate vs the user's deadline: GET /api/workspaces/:ws/estimate (numbers from the logged MILP plan).
// Operators on a writable workspace save the deadline; everyone else keeps it in this browser only.
import { h } from "../dom.js";
import { chip } from "./chip.js";
import { toast } from "./toast.js";
import { dd } from "./dd.js";

const KEY = (ws) => `atlas.deadline.${ws}`;
const local = { get: (ws) => { try { return localStorage.getItem(KEY(ws)); } catch { return null; } },
  set: (ws, v) => { try { v === null ? localStorage.removeItem(KEY(ws)) : localStorage.setItem(KEY(ws), String(v)); } catch { /* not remembered */ } } };

export function verdict(e, threshold) {
  if (!e.available || threshold === null || threshold === undefined) return null;
  return { exceeded: e.estimate_weeks > threshold, over: Math.max(0, e.estimate_weeks - threshold), spare: Math.max(0, threshold - e.estimate_weeks) };
}

export function estimateBlock(ctx) {
  const el = h("section", { class: "span-12 est", "aria-labelledby": "est-h" }, h("p", { class: "fine", text: "Loading the estimate…" }));
  const canSave = ctx.me && ctx.me.role !== "viewer" && ctx.wsInfo && !ctx.wsInfo.read_only;
  ctx.api.get(`/api/workspaces/${ctx.ws}/estimate`, { signal: ctx.signal }).then((e) => {
    if (!e.available) { el.replaceChildren(h("p", { class: "fine", text: `Time estimate: ${e.status_text}.` })); return; }
    const stored = canSave ? e.saved_threshold_weeks : Number(local.get(ctx.ws)) || null;
    const input = h("input", { type: "number", min: "1", max: "520", step: "1", id: "est-in", value: stored ?? "", placeholder: "e.g. 12", inputmode: "numeric" });
    const flag = h("div", { class: "est-flag", role: "status", "aria-live": "polite" });
    const draw = (t) => {
      const v = verdict(e, t);
      flag.className = `est-flag${v ? (v.exceeded ? " over" : " ok") : ""}`;
      flag.replaceChildren(!v ? h("span", { class: "fine", text: "Set a deadline to check the estimate against it." })
        : v.exceeded ? h("span", {}, chip("FAIL", `Over your deadline by ${v.over} week${v.over === 1 ? "" : "s"}`), h("span", { class: "fine", text: ` The plan needs ${e.estimate_weeks} weeks; your deadline is ${t}. Add capacity, or accept a later finish.` }))
        : h("span", {}, chip("PASS", "Within your deadline"), h("span", { class: "fine", text: ` ${v.spare} week${v.spare === 1 ? "" : "s"} to spare (plan ${e.estimate_weeks} weeks, deadline ${t}).` })));
    };
    const apply = async () => {
      const raw = input.value.trim(), t = raw === "" ? null : Number(raw);
      if (t !== null && !(Number.isInteger(t) && t >= 1 && t <= 520)) { toast("deadline must be a whole number of weeks, 1 to 520", { tone: "error" }); return; }
      if (canSave) {
        try { await ctx.api.put(`/api/workspaces/${ctx.ws}/estimate`, { threshold_weeks: t }); } catch (err) { toast(err.message, { tone: "error", detail: err.code }); return; }
      } else local.set(ctx.ws, t);
      draw(t);
      ctx.announce(t === null ? "Deadline cleared." : verdict(e, t).exceeded ? `Estimate exceeds your deadline by ${verdict(e, t).over} weeks.` : "Estimate is within your deadline.");
    };
    input.addEventListener("keydown", (ev) => { if (ev.key === "Enter") apply(); }, { signal: ctx.signal });
    const b = Object.entries(e.baselines_weeks).map(([k, w]) => `${k.toUpperCase()} ${w}`).join(" · ");
    el.replaceChildren(
      h("div", { class: "est-main" },
        h("p", { class: "eyebrow", id: "est-h", text: "How long will it take?" }),
        h("p", { class: "est-num" }, h("span", { class: "num", text: String(e.estimate_weeks) }), h("span", { class: "est-unit", text: ` weeks (≈ ${e.estimate_years.toFixed(2)} years)` })),
        dd({ read: `At ${e.capacity_days_per_week} engineer-days a week, the optimised plan finishes its last wave in week ${e.estimate_weeks}. It cannot be faster than ${e.lower_bound_weeks} weeks (${e.total_effort_days} engineer-days in total ÷ ${e.capacity_days_per_week} a week). Simple plans: ${b} weeks.` }),
        chip("assumption", "efforts and capacity are assumptions")),
      h("div", { class: "est-set" },
        h("label", { for: "est-in", class: "eyebrow", text: "Your deadline (weeks)" }),
        h("div", { class: "sg-row" }, input, h("button", { class: "btn primary", type: "button", text: canSave ? "Save deadline" : "Check", onclick: apply })),
        h("p", { class: "fine", text: canSave ? "Saved for this workspace." : "Kept in this browser only (read-only workspace or viewer)." }), flag));
    draw(stored);
  }).catch((err) => { if (err.code !== "aborted") el.replaceChildren(h("p", { class: "fine", text: `Time estimate unavailable: ${err.message}` })); });
  return el;
}
