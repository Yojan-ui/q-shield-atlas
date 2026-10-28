// Log console: monospace, virtualised (fixed 20 px lines), follows the tail unless the user scrolled up.
import { h } from "../dom.js";

const LINE_H = 20;

export function logConsole({ label = "run log", height = 320, signal = null } = {}) {
  const lines = [];
  const inner = h("div", { class: "lines" });
  const el = h("div", { class: "log", role: "log", "aria-label": label, "aria-live": "off", tabindex: "0", style: { height: `${height}px` } }, inner);
  let follow = true, queued = false;
  const empty = h("div", { class: "empty-log", text: "No output yet." });
  inner.append(empty);
  const draw = () => {
    queued = false;
    inner.style.height = `${lines.length * LINE_H}px`;
    if (follow) el.scrollTop = el.scrollHeight;
    const first = Math.max(0, Math.floor(el.scrollTop / LINE_H) - 10);
    const last = Math.min(lines.length, first + Math.ceil(el.clientHeight / LINE_H) + 20);
    const nodes = [];
    for (let i = first; i < last; i++) {
      const l = lines[i];
      nodes.push(h("div", { class: `line ${l.tone || ""}`, style: { top: `${i * LINE_H}px` } }, l.step ? h("span", { class: "step", text: l.step }) : null, l.text));
    }
    inner.replaceChildren(...(lines.length ? nodes : [empty]));
  };
  const schedule = () => { if (!queued) { queued = true; requestAnimationFrame(draw); } };
  el.addEventListener("scroll", () => { follow = el.scrollTop + el.clientHeight >= el.scrollHeight - LINE_H; schedule(); }, { passive: true, ...(signal ? { signal } : {}) });
  el.push = (text, step = "", tone = "") => { lines.push({ text, step, tone }); schedule(); };
  el.clear = () => { lines.length = 0; follow = true; schedule(); };
  el.lines = lines;
  return el;
}
