// Motion system: defined once, used everywhere. Mirrored as CSS custom properties in tokens.css
// (checked by jstests/motion.test.mjs). Pure functions so they run under node.
export const MOTION = {
  flightMinMs: 1100,
  flightMaxMs: 1600,
  overlayMs: 240,
  exitMs: 180,
  staggerMs: 40,
  shotMs: 300,
  riseIn: 8,
  rollMs: 300,
  overlayEase: [0.2, 0.8, 0.2, 1],
  exitEase: [0.4, 0, 1, 1],
  breathe: { amplitude: 0.015, periodMs: 8000 },
  parallaxMaxDeg: 2,
  settleOvershoot: 0.035,
};

export const clamp01 = (t) => (t < 0 ? 0 : t > 1 ? 1 : t);
export const easeInOutCubic = (t) => { t = clamp01(t); return t < 0.5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2; };
export const easeOutCubic = (t) => 1 - Math.pow(1 - clamp01(t), 3);

// Camera progress with a soft settle: ease-in-out-cubic to 1 + overshoot at ~85 %, then back to exactly 1.
export function flightProgress(t, overshoot = MOTION.settleOvershoot) {
  t = clamp01(t);
  const split = 0.85;
  if (t <= split) return easeInOutCubic(t / split) * (1 + overshoot);
  const u = (t - split) / (1 - split);
  return 1 + overshoot * (1 - easeInOutCubic(u));
}

// Flight duration scales with distance (scene units) inside the 1.1–1.6 s band.
export function flightDuration(distance, maxDistance = 40) {
  const k = clamp01(distance / maxDistance);
  return Math.round(MOTION.flightMinMs + (MOTION.flightMaxMs - MOTION.flightMinMs) * k);
}

// cubic-bezier(x1,y1,x2,y2) evaluated at x (Newton + bisection), for JS-driven overlays.
export function cubicBezier(x1, y1, x2, y2) {
  const cx = 3 * x1, bx = 3 * (x2 - x1) - cx, ax = 1 - cx - bx;
  const cy = 3 * y1, by = 3 * (y2 - y1) - cy, ay = 1 - cy - by;
  const sx = (t) => ((ax * t + bx) * t + cx) * t, sy = (t) => ((ay * t + by) * t + cy) * t;
  const dsx = (t) => (3 * ax * t + 2 * bx) * t + cx;
  return (x) => {
    x = clamp01(x);
    let t = x;
    for (let i = 0; i < 8; i++) { const d = sx(t) - x; const dd = dsx(t); if (Math.abs(d) < 1e-6 || Math.abs(dd) < 1e-6) break; t -= d / dd; }
    let lo = 0, hi = 1;
    for (let i = 0; i < 20 && Math.abs(sx(t) - x) > 1e-6; i++) { if (sx(t) < x) lo = t; else hi = t; t = (lo + hi) / 2; }
    return sy(t);
  };
}
export const overlayEase = cubicBezier(...MOTION.overlayEase);

// Rolling numbers: value at time t (ms) between old and new; never jumps unless reduced motion.
export function rollValue(from, to, elapsedMs, durationMs = MOTION.rollMs, reduced = false) {
  if (reduced || from === null || from === undefined || !Number.isFinite(from)) return to;
  return from + (to - from) * easeOutCubic(elapsedMs / durationMs);
}

// Idle breathing scale (≤ 1.5 %), 0 when reduced motion.
export function breathe(timeMs, reduced = false) {
  if (reduced) return 1;
  return 1 + MOTION.breathe.amplitude * 0.5 * (1 - Math.cos((2 * Math.PI * timeMs) / MOTION.breathe.periodMs));
}

export function staggerDelay(i) { return i * MOTION.staggerMs; }

export function prefersReducedMotion() {
  return typeof matchMedia === "function" && matchMedia("(prefers-reduced-motion: reduce)").matches;
}

// Animate a stat element's number from its last value to the new one (rAF, no layout work).
export function rollNumber(el, to, digits, reduced = prefersReducedMotion()) {
  const from = el._value;
  el._value = to;
  if (typeof requestAnimationFrame !== "function" || reduced || from === undefined || from === to) {
    el.textContent = to.toFixed(digits);
    return;
  }
  const t0 = performance.now();
  const step = (now) => {
    if (el._value !== to) return; // superseded by a newer value
    const v = rollValue(from, to, now - t0);
    el.textContent = v.toFixed(digits);
    if (now - t0 < MOTION.rollMs) requestAnimationFrame(step);
    else el.textContent = to.toFixed(digits);
  };
  requestAnimationFrame(step);
}
