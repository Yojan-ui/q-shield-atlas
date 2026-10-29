// Review: results awaiting a human decision. Approve / reject with a reason; each decision is signed into
// the Proof Chain (ledger append --type review.decision, ML-DSA-65) and the chain is verified again.
import { h } from "../dom.js";
import { chip } from "../components/chip.js";
import { table, tableSkeleton } from "../components/table.js";
import { emptyState } from "../components/states.js";
import { toast } from "../components/toast.js";
import { dataView, honesty, notRun } from "./common.js";
import { bullets, detailsList, keyStats, main, nextStep, pageHead } from "../components/page.js";
import { term } from "../glossary.js";

const STATUS = { pending: ["pending", "awaiting review"], approved: ["PASS", "approved"], rejected: ["FAIL", "rejected"] };

function decisionForm(ctx, item, onDone) {
  const reason = h("textarea", { rows: "2", maxlength: "500", placeholder: "Reason (required, recorded in the Proof Chain)", "aria-label": `reason for ${item.title}` });
  const go = async (decision, btns) => {
    if (reason.value.trim().length < 3) { toast("give a reason (at least 3 characters)", { tone: "error" }); reason.focus(); return; }
    btns.forEach((b) => { b.disabled = true; });
    try {
      const r = await ctx.api.post(`/api/workspaces/${ctx.ws}/reviews`, { item: item.id, decision, reason: reason.value });
      const done = r.items.find((x) => x.id === item.id);
      toast(`${item.title} ${done.status}; signed as Proof Chain #${done.decision.ledger_index}`, { tone: "info" });
      ctx.announce(`${item.title} ${done.status}.`);
      onDone();
    } catch (err) {
      toast(err.message, { tone: "error", detail: err.code });
      btns.forEach((b) => { b.disabled = false; });
    }
  };
  const ok = h("button", { class: "btn primary", type: "button", text: "Approve" }), no = h("button", { class: "btn", type: "button", text: "Reject" });
  ok.addEventListener("click", () => go("approve", [ok, no]), { signal: ctx.signal });
  no.addEventListener("click", () => go("reject", [ok, no]), { signal: ctx.signal });
  return h("div", { class: "rv-form" }, reason, h("div", { class: "sg-row" }, ok, no));
}

const why3 = (i) => h("div", { class: "rv-www" }, [["What", i.what], ["How", i.how], ["Why", i.why]].map(([k, xs]) =>
  h("div", {}, h("p", { class: "eyebrow", text: k }), h("ul", { class: "pg-list" }, (xs || []).map((t) => h("li", { text: t }))))));
const proof = (ctx, i) => h("p", { class: "fine" }, i.ledger_index !== null && i.ledger_index !== undefined
  ? [h("a", { href: `/w/${ctx.ws}/ledger`, text: `Proof Chain #${i.ledger_index}` }), " · ", chip(i.signature === "verified" ? "verified" : "NOT_RUN", `signature ${i.signature}`)]
  : chip("NOT_RUN", "not signed yet"), h("span", { class: "mono", text: ` · run ${i.run_id.slice(0, 12)}` }));

export async function mount(ctx) {
  const body = dataView(ctx, {
    keys: ["reviews"],
    skeleton: () => tableSkeleton(4),
    render: ({ reviews: R }) => {
      if (!R.items.length) return emptyState(notRun(ctx, "Review"));
      const refresh = () => ctx.store.invalidate(ctx.ws, ["reviews", "ledger", "results"]);
      const pending = R.items.filter((i) => i.status === "pending"), done = R.items.filter((i) => i.status !== "pending");
      const n = (x) => ({ kind: "number", value: x, text: String(x), digits: 0, source: { run_id: "reviews", solver: "review decisions", ts: "" } });
      const why = R.read_only ? "Read-only demo snapshot: decisions cannot be recorded here." : !R.can_decide ? "Viewers can see decisions; an operator or admin records them." : null;
      const focus = ctx.query.get("item");
      return h("div", {},
        keyStats([
          { label: "awaiting review", cell: n(pending.length), unit: "results", mean: why || "Each needs a person's approve or reject, with a reason." },
          { label: "approved", cell: n(done.filter((i) => i.status === "approved").length), unit: "signed decisions", mean: "Approved steps can go ahead in the real migration plan." },
          { label: "rejected", cell: n(done.filter((i) => i.status === "rejected").length), unit: "signed decisions", mean: "Rejected steps go back for rework; the reason is kept." }]),
        main(pending.length ? h("ul", { class: "rv-list" }, pending.map((i) => h("li", { class: `rv-item${focus === i.id ? " hl" : ""}`, id: `item-${i.id.replace(/[^a-z0-9-]/gi, "-")}` },
          h("div", {}, h("p", { class: "rv-title" }, chip("pending", "awaiting review"), ` ${i.title}`), h("p", { class: "fine", text: i.summary }), why3(i), proof(ctx, i)),
          R.can_decide ? decisionForm(ctx, i, refresh) : null))) : h("p", { class: "fine", text: "Nothing is waiting: every result of the latest run has a decision." }), { title: "Awaiting review" }),
        done.length ? main(table({ caption: "Review decisions", rows: done, columns: [
          { label: "item", render: (i) => h("span", {}, i.title, h("span", { class: "sub", text: i.summary })) },
          { label: "decision", render: (i) => chip(...STATUS[i.status]) },
          { label: "reason", render: (i) => i.decision.reason },
          { label: "by", render: (i) => i.decision.by, optional: true },
          { label: "when (UTC)", render: (i) => i.decision.ts, mono: true, optional: true },
          { label: "decision record", numeric: true, render: (i) => h("a", { href: `/w/${ctx.ws}/ledger`, text: `#${i.decision.ledger_index}` }) }] }), { title: "Decided" }) : null,
        detailsList([
          { title: "How it works", summary: "Each decision is a small signed record bound to the exact evidence it judged.", body: bullets([
            "The record holds the item, its run and the SHA-256 of that run's evidence, the decision, the reason, who and when.",
            ["It is appended to the ", term("ledger", "Proof Chain"), " with ML-DSA-65, then the whole chain is verified again."]]) },
          { title: "Why this method", summary: "Automation proposes; an accountable person decides.", body: bullets([
            "Banks need a named approver and a reason for each change.", "A new run creates new items, so an old approval never covers new evidence."]) },
          { title: "Evidence & sources", summary: `${R.items.length} items from the latest run`, body: bullets(R.items.map((i) => `${i.title}: run ${i.run_id}, evidence ${i.evidence_sha256 || "missing"}`)) },
          { title: "Limits", summary: "Approval records intent; it does not change any real system.", body: bullets([
            "The migration shown is a plan tested in a lab, not a change to production.", "One signing key per workspace; no second approver yet."]) }]),
        nextStep(ctx, "review"));
    },
  });
  ctx.root.append(h("div", { class: "grid" }, h("div", { class: "span-12" },
    pageHead(ctx, { route: "review", title: "Review", headline: "Which migration steps are approved, and why? Every decision is signed and kept." }), body, honesty())));
}
