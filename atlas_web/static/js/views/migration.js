// Migration: every system moving from classical to post-quantum encryption, week by week, in three lanes.
// Positions follow the logged plan (planned_week); the final lane follows the lab gate result. Nothing is
// claimed about production: "verified in lab" is the strongest state shown. Play animates the weeks; with
// reduced motion (OS setting or the toggle) nothing moves by itself and tiles change lane without transition.
import { h, icon } from "../dom.js";
import { chip } from "../components/chip.js";
import { emptyState } from "../components/states.js";
import { prefersReducedMotion } from "../motion.js";
import { HNDL } from "../model.js";
import { dataView, header, honesty, notRun, section, wsEyebrow } from "./common.js";

export const LANES = [
  { id: "classical", title: "Still on old encryption", sub: "quantum-exposed (RSA / ECC)", tone: "exposed" },
  { id: "migrating", title: "Moving now", sub: "in this week's wave", tone: "accent" },
  { id: "done", title: "Moved to post-quantum", sub: "by the plan; lab result on each tile", tone: "pass" },
];
const RESULT = { applied: ["PASS", "verified in lab"], partially_verified: ["partially_verified", "partly verified in lab"],
  not_verified_in_lab: ["not_verified_in_lab", "not verifiable in lab"], rolled_back: ["rolled_back", "rolled back"],
  rollback_failed: ["FAIL", "rollback failed"], planned: ["planned", "planned"] };

export function laneOf(asset, week) {
  if (week < asset.planned_week) return "classical";
  if (week === asset.planned_week) return "migrating";
  return "done";
}

export function progress(assets, week) {
  const done = assets.filter((a) => laneOf(a, week) === "done");
  return { done: done.length, total: assets.length, verified: done.filter((a) => a.status === "applied").length };
}

export async function mount(ctx) {
  let reduced = prefersReducedMotion(), timer = 0;
  const body = dataView(ctx, {
    keys: ["results"],
    skeleton: () => h("p", { class: "fine", text: "Loading the plan…" }),
    render: ({ model: m }) => {
      const r = m && m.results;
      if (!r || !r.assets || !r.assets.length) return emptyState(r && r.assets ? { title: "Nothing to migrate", body: "The scan found no RSA / ECC to replace in this workspace.", action: null } : notRun(ctx, "Migration"));
      const assets = [...r.assets].sort((a, b) => a.planned_week - b.planned_week || a.id.localeCompare(b.id));
      const last = Math.max(...assets.map((a) => a.planned_week)) + 1;
      let week = Math.min(last, Math.max(0, Number(ctx.query.get("week") ?? last)));
      const lanes = Object.fromEntries(LANES.map((l) => [l.id, h("ul", { class: "mg-tiles", "aria-label": l.title })]));
      const tiles = new Map(assets.map((a) => {
        const res = RESULT[a.status] || RESULT.planned;
        const t = h("li", { class: "mg-tile", "data-id": a.id },
          h("a", { href: `/w/${ctx.ws}/asset/${encodeURIComponent(a.id)}`, class: "mg-name", text: a.name }),
          h("span", { class: "mg-meta fine", text: `${a.algorithm} · wave ${a.planned_week}` }),
          h("span", { class: "mg-res" }, chip(...res)));
        return [a.id, t];
      }));
      const bar = h("div", { class: "mg-bar", role: "progressbar", "aria-valuemin": "0", "aria-valuemax": String(assets.length) }, h("span", { class: "mg-fill" }), h("span", { class: "mg-fill verified" }));
      const label = h("p", { class: "mg-progress" }), mean = h("p", { class: "fine" });
      const barKey = h("ul", { class: "legend", "aria-label": "Progress bar colours" }, [["pass", "verified in lab"], ["accent", "moved by the plan"], ["exposed", "still on old encryption"]].map(([c, t]) =>
        h("li", {}, h("span", { class: `lg-dot ${c}`, "aria-hidden": "true" }), t)));
      const range = h("input", { type: "range", min: "0", max: String(last), step: "1", value: String(week), "aria-label": "week of the plan" });
      const wk = h("output", { class: "num" });
      const play = h("button", { class: "btn", type: "button" }, icon("play"), "Play");
      const motionBtn = h("button", { class: "btn", type: "button", "aria-pressed": String(reduced) });
      const draw = () => {
        const rects = reduced ? null : new Map([...tiles].map(([id, t]) => [id, t.getBoundingClientRect()]));
        for (const a of assets) {
          const t = tiles.get(a.id), lane = laneOf(a, week);
          t.dataset.lane = lane;
          t.querySelector(".mg-res").hidden = lane !== "done";
          if (t.parentElement !== lanes[lane]) lanes[lane].append(t);
        }
        if (rects) for (const [id, t] of tiles) {  // FLIP: slide each tile from its old place
          const a = rects.get(id), b = t.getBoundingClientRect();
          if (a.width && (a.left !== b.left || a.top !== b.top)) t.animate([{ transform: `translate(${a.left - b.left}px, ${a.top - b.top}px)` }, { transform: "none" }], { duration: 520, easing: "cubic-bezier(.2,.7,.2,1)" });
        }
        const p = progress(assets, week);
        wk.textContent = week === 0 ? "start" : week >= last ? `week ${last - 1} done` : `week ${week}`;
        bar.setAttribute("aria-valuenow", String(p.done));
        bar.setAttribute("aria-valuetext", `${p.done} of ${p.total} systems moved, ${p.verified} verified in lab`);
        bar.children[0].style.width = `${(p.done / p.total) * 100}%`;
        bar.children[1].style.width = `${(p.verified / p.total) * 100}%`;
        label.replaceChildren(h("span", { class: "num", text: `${p.done} / ${p.total}` }), " systems moved by the plan · ", h("span", { class: "num", text: String(p.verified) }), " verified in the lab");
        const left = p.total - p.done;
        mean.textContent = left ? `What this means: at this point in the plan, ${left} system${left === 1 ? " still uses" : "s still use"} encryption a future quantum computer could break, so traffic recorded from ${left === 1 ? "it" : "them"} today is at risk (${HNDL}).`
          : `What this means: by the end of the plan every system has moved; ${p.verified} of ${p.total} passed every lab check, the rest are partly verified or not verifiable in the lab.`;
        motionBtn.replaceChildren(icon(reduced ? "dash" : "spin"), reduced ? "Motion off" : "Motion on");
        motionBtn.setAttribute("aria-pressed", String(reduced));
      };
      const stop = () => { clearInterval(timer); timer = 0; play.replaceChildren(icon("play"), "Play"); };
      const set = (w) => { week = w; range.value = String(w); ctx.setQuery({ week: String(w) }); draw(); };
      range.addEventListener("input", () => { stop(); set(Number(range.value)); }, { signal: ctx.signal });
      play.addEventListener("click", () => {
        if (timer) return stop();
        if (week >= last) set(0);
        play.replaceChildren(icon("dash"), "Pause");
        timer = setInterval(() => { if (week >= last) return stop(); set(week + 1); ctx.announce(wk.textContent); }, reduced ? 1600 : 1100);
      }, { signal: ctx.signal });
      motionBtn.addEventListener("click", () => { reduced = !reduced; draw(); }, { signal: ctx.signal });
      ctx.signal.addEventListener("abort", stop, { once: true });
      draw();
      const sessions = (r.handshake_evidence || {}).sessions || [];
      return h("div", { class: "grid" },
        h("div", { class: "span-12 mg-head" }, label, bar, barKey, mean,
          h("div", { class: "sg-row mg-controls" }, play, h("label", { class: "sg-row week-scrub" }, h("span", { class: "eyebrow", style: { margin: 0 }, text: "week" }), range, wk), motionBtn)),
        h("div", { class: "span-12 mg-lanes" }, LANES.map((l) => h("section", { class: `mg-lane ${l.tone}`, "aria-label": l.title },
          h("p", { class: "mg-lane-h" }, h("span", { class: `lg-dot ${l.tone}`, "aria-hidden": "true" }), l.title), h("p", { class: "fine", text: l.sub }), lanes[l.id]))),
        sessions.length ? section("Connections tested in the lab", h("ul", { class: "mg-sessions" }, sessions.map((s) => h("li", {},
          chip(s.hndl_exposed ? "HNDL-exposed" : "hybrid", s.hndl_exposed ? "old key exchange" : "post-quantum key exchange"),
          h("span", { class: "mono", text: ` ${s.service_id}: ${s.negotiated_group}` }), h("span", { class: "fine", text: s.hndl_exposed ? ` · ${HNDL}` : " · recorded handshake, real TLS 1.3" })))),
          { aside: h("span", { class: "fine", text: "measured handshakes, not simulated traffic" }) }) : null,
        h("p", { class: "span-12 fine", text: "Lanes follow the logged plan (each system's planned week). The tile badge is the lab gate result for its wave. Nothing here says a production system has migrated." }));
    },
  });
  ctx.root.append(h("div", { class: "grid" },
    h("div", { class: "span-12" }, header({ eyebrow: wsEyebrow(ctx), title: "Migration", lede: "Every system moving from old, quantum-exposed encryption to post-quantum encryption, wave by wave. Press Play or drag the week." })),
    h("div", { class: "span-12" }, body), h("div", { class: "span-12" }, honesty())));
}
