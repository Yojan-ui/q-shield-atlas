// Sign-in. Success hands the session to the shell (Stage 4: key-exchange animation, then the flight to the pipeline).
import { h, icon } from "../dom.js";
import { field } from "../components/form.js";
import { safeNext } from "../router.js";

export async function mount(ctx) {
  const user = field({ label: "Username", name: "username", required: true, autocomplete: "username" });
  const pass = field({ label: "Password", name: "password", type: "password", required: true, autocomplete: "current-password" });
  const err = h("p", { class: "fine", role: "alert", style: { color: "var(--exposure)", minHeight: "20px" } });
  const submit = h("button", { class: "btn primary", type: "submit" }, icon("lock"), "Sign in");
  const form = h("form", { class: "signin-card", novalidate: true }, user, pass, err, submit);
  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    err.textContent = "";
    if (![user.check(), pass.check()].every(Boolean)) return;
    submit.disabled = true;
    try {
      const res = await ctx.api.post("/api/auth/login", { username: user.value(), password: pass.input.value }, { quiet: true });
      await ctx.signedIn(res.user, safeNext(ctx.query.get("next")));
    } catch (ex) {
      err.textContent = ex.message;
      pass.input.value = "";
      form.classList.remove("shake"); void form.offsetWidth; form.classList.add("shake");
      submit.disabled = false;
      pass.input.focus();
    }
  }, { signal: ctx.signal });
  const next = safeNext(ctx.query.get("next"));
  ctx.root.append(h("div", { class: "grid signin" },
    h("div", { class: "span-5" }, h("p", { class: "eyebrow" }, h("span", { class: "accent", text: "Q-Shield Atlas" }), " · operators"),
      h("h1", { text: "Sign in" }),
      h("p", { class: "lede", text: next ? `Sign in to continue to ${next}.` : "Viewers read results; operators run the pipeline on their own data; admins manage users." }),
      h("div", { style: { marginTop: "var(--s-6)" } }, form)),
    h("aside", { class: "start-9 signin-aside" }, h("p", { class: "eyebrow", text: "Without an account" }),
      h("p", { class: "fine", text: "The public landing page tells the story from the read-only demo snapshot." }),
      h("a", { class: "btn", href: "/", style: { marginTop: "var(--s-3)" }, text: "Back to the demo" }))));
  ctx.announce("Sign-in form.");
}
