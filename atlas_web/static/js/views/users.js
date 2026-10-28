// Settings · users (admin): list, create, delete with confirmation.
import { h } from "../dom.js";
import { table, tableSkeleton } from "../components/table.js";
import { field } from "../components/form.js";
import { chip } from "../components/chip.js";
import { confirmDialog } from "../components/dialog.js";
import { toast } from "../components/toast.js";
import { errorState } from "../components/states.js";
import { header, section } from "./common.js";

export async function mount(ctx) {
  const list = h("div", {}, tableSkeleton(4, 3));
  const draw = async () => {
    try {
      const { users } = await ctx.api.get("/api/users", { signal: ctx.signal });
      list.replaceChildren(table({ caption: "Users", rows: users, columns: [
        { label: "username", key: "username", mono: true }, { label: "role", render: (u) => chip(u.role === "admin" ? "hybrid" : "planned", u.role) },
        { label: "created", render: (u) => new Date(u.created * 1000).toISOString().slice(0, 16).replace("T", " ") },
        { label: "", render: (u) => u.username === ctx.me.username ? h("span", { class: "fine", text: "you" })
          : h("button", { class: "btn quiet", type: "button", text: "Delete", onclick: async () => {
            if (!(await confirmDialog({ title: `Delete ${u.username}?`, body: "Their sessions end immediately. This cannot be undone.", confirm: "Delete user", danger: true }))) return;
            try { await ctx.api.del(`/api/users/${encodeURIComponent(u.username)}`); toast(`Deleted ${u.username}`, { tone: "success" }); draw(); } catch { /* toast shown */ }
          } }) }] }));
    } catch (err) { if (err.code !== "aborted") list.replaceChildren(errorState({ error: err, onRetry: draw })); }
  };
  const name = field({ label: "Username", name: "new-username", required: true, autocomplete: "off", validate: (v) => (/^[a-z0-9._-]{1,64}$/.test(v) ? "" : "a-z 0-9 . _ - only") });
  const pw = field({ label: "Password", name: "new-password", type: "password", required: true, autocomplete: "new-password", hint: "at least 10 characters", validate: (v) => (v.length >= 10 ? "" : "at least 10 characters") });
  const role = field({ label: "Role", name: "new-role", options: ["viewer", "operator", "admin"], value: "viewer" });
  const submit = h("button", { class: "btn primary", type: "submit", text: "Create user" });
  const form = h("form", { novalidate: true, style: { display: "grid", gap: "var(--s-4)" } }, name, pw, role, submit);
  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    if (![name.check(), pw.check()].every(Boolean)) return;
    try {
      await ctx.api.post("/api/users", { username: name.value(), password: pw.input.value, role: role.value() }, { quiet: true });
      toast(`Created ${name.value()}`, { tone: "success" }); form.reset(); draw();
    } catch (err) { name.setError(err.message); }
  }, { signal: ctx.signal });
  ctx.root.append(h("div", { class: "grid" },
    h("div", { class: "span-12" }, header({ eyebrow: "Settings", title: "Users", lede: "Viewers read results. Operators run the pipeline, upload data and calibrate. Admins manage users and, once the account allows it, paid QpiAI runs." })),
    h("div", { class: "span-8" }, section("Accounts", list)), h("div", { class: "start-9" }, section("New user", form))));
  draw();
  ctx.announce("User management.");
}
