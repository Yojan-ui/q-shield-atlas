import { test } from "node:test";
import assert from "node:assert/strict";
import { readdirSync, readFileSync, statSync } from "node:fs";
import { join } from "node:path";

// Visible "How to read this" captions are gone: explanations live in one closed "Details ▾" per section.
const ROOT = new URL("../static/js/", import.meta.url).pathname;
const files = (d) => readdirSync(d).flatMap((f) => (statSync(join(d, f)).isDirectory() ? files(join(d, f)) : f.endsWith(".js") ? [join(d, f)] : []));

test("no page renders text starting with 'How to read this'", () => {
  for (const f of files(ROOT)) {
    const src = readFileSync(f, "utf8");
    assert.doesNotMatch(src, /["'`]\s*How to read this/i, f);
    assert.doesNotMatch(src, /class:\s*"mv-how"/, f);
  }
});

test("Details disclosure is closed by default", async () => {
  const s = readFileSync(join(ROOT, "components/dd.js"), "utf8");
  assert.match(s, /h\("details", \{ class: "dd" \}/);
  assert.doesNotMatch(s, /class: "dd", open/);
});
