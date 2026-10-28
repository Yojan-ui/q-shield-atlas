// Confirm dialog (native <dialog>: focus trap, Esc to cancel). Resolves true/false.
import { h } from "../dom.js";

export function confirmDialog({ title, body, confirm = "Confirm", cancel = "Cancel", danger = false }) {
  return new Promise((resolve) => {
    const ok = h("button", { class: `btn ${danger ? "danger" : "primary"}`, type: "button", text: confirm });
    const no = h("button", { class: "btn", type: "button", text: cancel });
    const dlg = h("dialog", { class: "confirm", "aria-labelledby": "dlg-title" },
      h("h2", { id: "dlg-title", text: title }), typeof body === "string" ? h("p", { text: body }) : body, h("div", { class: "actions" }, no, ok));
    document.body.append(dlg);
    const done = (v) => { dlg.close(); dlg.remove(); resolve(v); };
    ok.addEventListener("click", () => done(true));
    no.addEventListener("click", () => done(false));
    dlg.addEventListener("cancel", (e) => { e.preventDefault(); done(false); });
    dlg.showModal();
    no.focus();
  });
}
