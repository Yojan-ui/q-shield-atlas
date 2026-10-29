// Glossary: every technical term in the UI, in plain words. ?term=<id> highlights and scrolls to one entry.
import { h } from "../dom.js";
import { GLOSSARY } from "../glossary.js";
import { pageHead } from "../components/page.js";

export async function mount(ctx) {
  const want = ctx.query.get("term");
  const list = h("dl", { class: "gl-list" }, GLOSSARY.map((g) => h("div", { class: `gl-item${g.id === want ? " hl" : ""}`, id: g.id },
    h("dt", { text: g.term }), h("dd", { text: g.short }), h("dd", { text: g.long }))));
  ctx.root.append(h("div", { class: "grid" }, h("div", { class: "span-12" },
    pageHead(ctx, { route: "glossary", title: "Glossary", headline: "The technical words used in Atlas, each explained in one or two plain sentences." }), list)));
  if (want) requestAnimationFrame(() => { const el = document.getElementById(want); if (el) el.scrollIntoView({ block: "center" }); });
}
