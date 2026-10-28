// 403: signed in, but the route needs a higher role.
import { h, icon } from "../dom.js";

export async function mount(ctx) {
  ctx.root.append(h("div", { class: "grid" }, h("div", { class: "span-7" }, h("p", { class: "eyebrow", text: "403 · locked cell" }),
    h("h1", { text: "Your role cannot open this." }),
    h("p", { class: "lede", text: `This needs the ${ctx.need || "admin"} role; you are signed in as ${ctx.me.username} (${ctx.me.role}). Ask an admin to change your role.` }),
    h("div", { class: "sg-row", style: { marginTop: "var(--s-5)" } }, h("a", { class: "btn primary", href: `/w/${ctx.ws}/pipeline`, text: "Back to the pipeline" }))),
    h("div", { class: "start-9" }, icon("lock", "scene-mark"))));
  ctx.announce("Not allowed for your role.");
}
