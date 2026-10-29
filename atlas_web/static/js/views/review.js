// Review: results awaiting a human decision. Approve / reject with a reason; each decision is signed into
// the Proof Chain (ledger append --type review.decision, ML-DSA-65) and the chain is verified again.
import { h } from "../dom.js";
import { chip } from "../components/chip.js";
import { table, tableSkeleton } from "../components/table.js";
import { emptyState } from "../components/states.js";
import { toast } from "../components/toast.js";
import { dataView, header, honesty, notRun, section, wsEyebrow } from "./common.js";

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

export async function mount(ctx) {
  const body = dataView(ctx, {
    keys: ["reviews"],
    skeleton: () => tableSkeleton(4),
    render: ({ reviews: R }) => {
      if (!R.items.length) return emptyState(notRun(ctx, "Review"));
      const refresh = () => ctx.store.invalidate(ctx.ws, ["reviews", "ledger", "results"]);
      const pending = R.items.filter((i) => i.status === "pending"), done = R.items.filter((i) => i.status !== "pending");
      const why = R.read_only ? "This is the read-only demo snapshot: decisions cannot be recorded here." : !R.can_decide ? "Viewers can see decisions; an operator or admin records them." : null;
      return h("div", { class: "grid" },
        h("p", { class: "span-12 fine", text: `${pending.length} awaiting review · ${done.length} decided.${why ? ` ${why}` : ""}` }),
        section("Awaiting review", pending.length ? h("ul", { class: "rv-list" }, pending.map((i) => h("li", { class: "rv-item" },
          h("div", {}, h("p", { class: "rv-title" }, chip("pending", "awaiting review"), ` ${i.title}`), h("p", { class: "fine", text: i.summary }),
            h("p", { class: "fine mono", text: `run ${i.run_id.slice(0, 12)} · evidence ${i.evidence_sha256 ? i.evidence_sha256.slice(0, 16) + "…" : "missing"}` })),
          R.can_decide ? decisionForm(ctx, i, refresh) : null))) : h("p", { class: "fine", text: "Nothing is waiting: every result of the latest run has a decision." })),
        section("Decided", table({ caption: "Review decisions", rows: done, empty: "No decisions yet", columns: [
          { label: "item", render: (i) => h("span", {}, i.title, h("span", { class: "sub", text: i.summary })) },
          { label: "decision", render: (i) => chip(...STATUS[i.status]) },
          { label: "reason", render: (i) => i.decision.reason },
          { label: "by", render: (i) => i.decision.by, optional: true },
          { label: "when", render: (i) => i.decision.ts, mono: true, optional: true },
          { label: "Proof Chain", numeric: true, render: (i) => h("a", { href: `/w/${ctx.ws}/ledger`, text: `#${i.decision.ledger_index}` }) }] })));
    },
  });
  ctx.root.append(h("div", { class: "grid" },
    h("div", { class: "span-12" }, header({ eyebrow: wsEyebrow(ctx), title: "Review", lede: "Results of the latest run that need a person's decision. Approve or reject each one with a reason; the decision is signed into the Proof Chain with ML-DSA-65 and bound to the exact evidence it judged." })),
    h("div", { class: "span-12" }, body), h("div", { class: "span-12" }, honesty())));
}
