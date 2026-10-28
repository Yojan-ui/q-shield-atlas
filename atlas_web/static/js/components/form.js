// Form field with a label, hint and inline validation (aria-invalid + aria-describedby).
import { h } from "../dom.js";

let uid = 0;
export function field({ label, name, type = "text", value = "", hint = "", options = null, validate = null, required = false,
  autocomplete = null, inputmode = null, placeholder = null }) {
  const id = `f-${name}-${++uid}`;
  const hintEl = h("div", { class: "hint", id: `${id}-hint`, text: hint });
  const input = options
    ? h("select", { id, name, required }, options.map((o) => h("option", { value: o.value ?? o, selected: (o.value ?? o) === value }, o.label ?? o)))
    : h("input", { id, name, type, value, required, autocomplete, inputmode, placeholder, "aria-describedby": `${id}-hint` });
  if (options) input.setAttribute("aria-describedby", `${id}-hint`);
  const wrap = h("div", { class: "field" }, h("label", { for: id, text: label }), input, hintEl);
  const check = () => {
    const msg = !input.value && required ? `${label} is required` : validate ? validate(input.value) : "";
    wrap.setError(msg || "");
    return !msg;
  };
  wrap.setError = (msg) => {
    wrap.classList.toggle("invalid", !!msg);
    input.setAttribute("aria-invalid", msg ? "true" : "false");
    hintEl.textContent = msg || hint;
  };
  input.addEventListener("blur", () => { if (input.value || wrap.classList.contains("invalid")) check(); });
  input.addEventListener("input", () => { if (wrap.classList.contains("invalid")) check(); });
  wrap.input = input;
  wrap.check = check;
  wrap.value = () => input.value;
  return wrap;
}

export function checkbox({ label, name }) {
  const id = `c-${name}-${++uid}`;
  const input = h("input", { type: "checkbox", id, name });
  const wrap = h("label", { class: "check", for: id }, input, h("span", { text: label }));
  wrap.input = input;
  return wrap;
}
