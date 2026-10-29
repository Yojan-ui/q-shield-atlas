import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { breathe, cubicBezier, easeInOutCubic, flightDuration, flightProgress, MOTION, rollValue, staggerDelay } from "../static/js/motion.js";

const css = readFileSync(new URL("../static/css/tokens.css", import.meta.url), "utf8");
const token = (name) => css.match(new RegExp(`--${name}:\\s*([^;]+);`))[1].trim();

test("tokens.css mirrors motion.js", () => {
  assert.equal(token("dur-overlay"), `${MOTION.overlayMs}ms`);
  assert.equal(token("dur-exit"), `${MOTION.exitMs}ms`);
  assert.equal(token("dur-stagger"), `${MOTION.staggerMs}ms`);
  assert.equal(token("dur-roll"), `${MOTION.rollMs}ms`);
  assert.equal(token("dur-shot"), `${MOTION.shotMs}ms`);
  assert.equal(token("rise"), `${MOTION.riseIn}px`);
  assert.equal(token("ease-overlay"), `cubic-bezier(${MOTION.overlayEase.join(", ")})`);
  assert.deepEqual(MOTION.overlayEase, [0.2, 0.8, 0.2, 1]);
  assert.equal(MOTION.overlayMs, 280); assert.equal(MOTION.exitMs, 180); assert.equal(MOTION.staggerMs, 40); assert.equal(MOTION.riseIn, 24);
});

test("easing", () => {
  assert.equal(easeInOutCubic(0), 0); assert.equal(easeInOutCubic(1), 1); assert.equal(easeInOutCubic(0.5), 0.5);
  const b = cubicBezier(0.2, 0.8, 0.2, 1);
  assert.ok(Math.abs(b(0)) < 1e-6 && Math.abs(b(1) - 1) < 1e-6 && b(0.5) > 0.8);
  for (let t = 0; t < 1; t += 0.05) assert.ok(b(t + 0.05) >= b(t) - 1e-9, "monotone");
});

test("camera flight: 1.1-1.6 s, soft overshoot settle, ends exactly at 1", () => {
  assert.equal(flightDuration(0), 1100); assert.equal(flightDuration(1e9), 1600);
  assert.ok(flightDuration(20) > 1100 && flightDuration(20) < 1600);
  assert.equal(flightProgress(0), 0); assert.equal(flightProgress(1), 1);
  const peak = Math.max(...Array.from({ length: 101 }, (_, i) => flightProgress(i / 100)));
  assert.ok(peak > 1 && peak <= 1 + MOTION.settleOvershoot + 1e-9);
});

test("rolling numbers never jump (except reduced motion) and land on the target", () => {
  assert.equal(rollValue(0, 10, 0), 0); assert.equal(rollValue(0, 10, MOTION.rollMs), 10); assert.equal(rollValue(0, 10, 1e6), 10);
  assert.ok(rollValue(0, 10, 100) > 0 && rollValue(0, 10, 100) < 10);
  assert.equal(rollValue(0, 10, 0, MOTION.rollMs, true), 10);
  assert.equal(rollValue(undefined, 10, 0), 10);
});

test("idle breathing <= 1.5 %, none when reduced", () => {
  for (let t = 0; t < 16000; t += 250) { const s = breathe(t); assert.ok(s >= 1 && s <= 1.015 + 1e-12); }
  assert.equal(breathe(4000, true), 1);
  assert.equal(staggerDelay(3), 120);
});
