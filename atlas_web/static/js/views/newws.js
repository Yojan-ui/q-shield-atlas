// New workspace from a public repo (operators): create (template "empty"), then clone. Nothing runs yet.
import { h } from "../dom.js";
import { field } from "../components/form.js";
import { honesty } from "./common.js";
import { pageHead } from "../components/page.js";

const slug = (u) => (u.replace(/\.git$/, "").split("/").filter(Boolean).pop() || "repo").toLowerCase().replace(/[^a-z0-9-]/g, "-").slice(0, 40);

export async function mount(ctx) {
  const url = field({ label: "Public GitHub repository URL", name: "url", type: "url", value: ctx.query.get("url") || "", placeholder: "https://github.com/org/repo", hint: "public https only; cloned read-only into a new workspace", required: true,
    validate: (v) => (/^https:\/\/[^\s]+$/.test(v) ? "" : "must start with https://") });
  const name = field({ label: "Workspace name", name: "name", placeholder: "defaults to the repository name" });
  const msg = h("p", { class: "mv-note", "aria-live": "polite" }), btn = h("button", { class: "btn primary", type: "submit", text: "Create workspace and clone" });
  const canMake = ctx.me && ["operator", "admin"].includes(ctx.me.role);
  const form = h("form", { class: "dt-form nw-form", onsubmit: async (e) => {
    e.preventDefault();
    if (!url.check()) return;
    const u = url.value().trim(), id = slug(u);
    btn.disabled = true; msg.textContent = "Creating the workspace…";
    try {
      await ctx.api.post("/api/workspaces", { id, name: name.value().trim() || id, template: "empty" }, { quiet: true, signal: ctx.signal });
      msg.textContent = "Cloning the repository (this can take a minute)…";
      await ctx.api.post(`/api/workspaces/${id}/clone`, { url: u }, { quiet: true, signal: ctx.signal, timeout: 180000 });
      msg.textContent = "Suggesting service manifests (review them on the next page)…";
      await ctx.api.post(`/api/workspaces/${id}/manifests/suggest`, {}, { quiet: true, signal: ctx.signal, timeout: 120000 });
      await ctx.refreshWorkspaces();
      ctx.navigate(`/w/${id}/detect`);
    } catch (err) {
      if (err.code === "aborted") return;
      const why = err.status === 408 || /timeout|timed out/i.test(err.message) ? "the clone timed out (the repository may be very large or the network slow)"
        : /auth|403|404|not found|could not read/i.test(err.message) ? "the repository is private or does not exist (only public https repositories can be cloned)" : err.message;
      msg.textContent = `Not done: ${why}.`; btn.disabled = false;
    }
  } }, url, name, h("div", { class: "sg-row" }, btn, msg));
  ctx.root.append(h("div", { class: "grid" }, h("div", { class: "span-12" },
    pageHead(ctx, { route: "new-workspace", title: "Scan your own repo", headline: "Point Atlas at a public repository: it is cloned into a new workspace, then you review the suggested services and run the pipeline." }),
    canMake ? form : h("p", { class: "mv-note", text: "Creating a workspace needs the operator role. Ask an admin to upgrade your account." }), honesty())));
  if (canMake) requestAnimationFrame(() => url.input ? url.input.focus() : form.querySelector("input").focus());
}
