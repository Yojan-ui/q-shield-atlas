// Command palette (⌘K / Ctrl+K): jump to a route, workspace or asset, run the pipeline, step the scenario.
import { h } from "../dom.js";
import { RAIL } from "../routes.js";

export function installPalette({ navigate, getState, store }) {
  const input = h("input", { type: "text", placeholder: "Jump to route, asset, workspace…", "aria-label": "command", role: "combobox", "aria-controls": "pal-list", "aria-expanded": "true" });
  const list = h("ul", { id: "pal-list", role: "listbox" });
  const dlg = h("dialog", { class: "palette", "aria-label": "Command palette" }, input, list);
  document.body.append(dlg);
  let items = [], sel = 0;
  const key = (k) => () => dispatchEvent(new KeyboardEvent("keydown", { key: k }));
  const build = async () => {
    const { me, ws, workspaces } = getState();
    const out = [{ label: "Landing", hint: "/", go: "/" }];
    if (me) {
      out.push(...RAIL.map((r) => ({ label: r.title, hint: `${r.rail} · ${ws}`, go: `/w/${ws}/${r.name}` })),
        { label: "Run pipeline", hint: "action", go: `/w/${ws}/pipeline` },
        { label: "Next scenario", hint: "]", run: key("]") }, { label: "Previous scenario", hint: "[", run: key("[") },
        ...(workspaces || []).map((w) => ({ label: `Workspace: ${w.name}`, hint: w.type || "", go: `/w/${w.id}/pipeline` })));
      if (me.role === "admin") out.push({ label: "Users", hint: "settings", go: "/settings/users" });
      try {
        const r = (await store.get(ws, "results")).results;
        out.push(...((r && r.assets) || []).map((a) => ({ label: `Asset: ${a.id}`, hint: `${a.kind} · ${a.status}`, go: `/w/${ws}/asset/${encodeURIComponent(a.id)}` })));
      } catch { /* no results yet: routes only */ }
    } else out.push({ label: "Sign in", hint: "/signin", go: "/signin" });
    return out;
  };
  const draw = () => {
    const q = input.value.toLowerCase();
    const shown = items.filter((i) => i.label.toLowerCase().includes(q)).slice(0, 40);
    sel = Math.min(sel, Math.max(0, shown.length - 1));
    list.replaceChildren(...shown.map((i, k) => h("li", { role: "option", "aria-selected": String(k === sel), onclick: () => pick(i) }, h("span", { text: i.label }), h("span", { text: i.hint }))));
    list._shown = shown;
  };
  const pick = (i) => { dlg.close(); if (i.run) i.run(); else navigate(i.go); };
  input.addEventListener("input", () => { sel = 0; draw(); });
  input.addEventListener("keydown", (e) => {
    const shown = list._shown || [];
    if (e.key === "ArrowDown") { sel = Math.min(shown.length - 1, sel + 1); draw(); e.preventDefault(); }
    else if (e.key === "ArrowUp") { sel = Math.max(0, sel - 1); draw(); e.preventDefault(); }
    else if (e.key === "Enter" && shown[sel]) pick(shown[sel]);
  });
  addEventListener("keydown", async (e) => {
    if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
      e.preventDefault();
      if (dlg.open) { dlg.close(); return; }
      input.value = ""; sel = 0; items = await build(); draw(); dlg.showModal(); input.focus();
    }
  });
}
