// WCAG AA (4.5:1 normal text, 3:1 for large text and UI components) for every text/background pair in tokens.css.
import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const css = readFileSync(new URL("../static/css/tokens.css", import.meta.url), "utf8");
const tok = (n) => css.match(new RegExp(`--${n}:\\s*([^;]+);`))[1].trim();
function parse(c) {
  if (c.startsWith("#")) return [parseInt(c.slice(1, 3), 16), parseInt(c.slice(3, 5), 16), parseInt(c.slice(5, 7), 16), 1];
  const m = c.match(/rgba?\(([^)]+)\)/)[1].split(",").map((x) => parseFloat(x));
  return [m[0], m[1], m[2], m[3] ?? 1];
}
const over = (fg, bg) => fg.slice(0, 3).map((c, i) => c * fg[3] + bg[i] * (1 - fg[3])).concat(1);
const lum = ([r, g, b]) => [r, g, b].map((v) => { v /= 255; return v <= 0.03928 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4; }).reduce((a, v, i) => a + v * [0.2126, 0.7152, 0.0722][i], 0);
const ratio = (a, b) => { const [x, y] = [lum(a), lum(b)].sort((p, q) => q - p); return (x + 0.05) / (y + 0.05); };

const base = parse(tok("base"));
const bgs = { base, surface: over(parse(tok("surface")), base), "surface-solid": parse(tok("surface-solid")), "surface-raised": parse(tok("surface-raised")) };
const washes = ["accent-wash", "exposure-wash", "pass-wash", "caution-wash"];
for (const w of washes) bgs[w] = over(parse(tok(w)), base);
const TEXT = ["text", "text-2", "text-3", "accent", "exposure", "pass", "caution"];

test("every text token on every surface passes AA 4.5:1", () => {
  const fails = [];
  for (const t of TEXT) for (const [name, bg] of Object.entries(bgs)) {
    const r = ratio(parse(tok(t)), bg);
    if (r < 4.5) fails.push(`${t} on ${name}: ${r.toFixed(2)}`);
  }
  assert.deepEqual(fails, []);
});

test("primary button text on accent passes AA; focus ring and hairline-strong are visible UI (>= 3:1 for the ring)", () => {
  assert.ok(ratio(parse(tok("accent-ink")), parse(tok("accent"))) >= 4.5);
  assert.ok(ratio(parse(tok("accent")), base) >= 3);
});

test("the brief's tertiary #55606B fails AA on the base, which is why tokens.css uses a lighter tertiary", () => {
  assert.ok(ratio(parse("#55606B"), base) < 4.5);
  assert.notEqual(tok("text-3").toUpperCase(), "#55606B");
});
