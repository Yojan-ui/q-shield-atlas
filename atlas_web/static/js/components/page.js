// One page template for every route:
//   1 headline (one plain sentence)  2 at most 3 key numbers, each with "what this means"
//   3 the main visual or table        4 details, collapsed: How it works / Why this method / Evidence & sources / Limits
//   5 next step: one button to the next pipeline step
// Details are native <details> (keyboard and screen-reader accessible) and hidden in Beginner mode.
import { h, icon } from "../dom.js";
import { stat } from "./stat.js";
import { FLOW } from "../flow.js";

export const DETAIL_TITLES = ["How it works", "Why this method", "Evidence & sources", "Limits"];

export function flowIndex(routeName) { return FLOW.findIndex((f) => f.route === routeName); }

export function breadcrumbs(ctx, routeName, title) {
  const i = flowIndex(routeName);
  return h("nav", { class: "crumbs", "aria-label": "Breadcrumb" }, h("ol", {},
    h("li", {}, h("a", { href: `/w/${ctx.ws}/pipeline`, text: (ctx.wsInfo && ctx.wsInfo.name) || ctx.ws })),
    i >= 0 ? h("li", { text: `Step ${i + 1} of ${FLOW.length}` }) : null,
    h("li", { "aria-current": "page", text: title })));
}

export function pageHead(ctx, { route, title, headline, actions = null, aside = null }) {
  return h("header", { class: "pg-head" },
    breadcrumbs(ctx, route, title),
    h("div", { class: "pg-title" }, h("div", {}, h("h1", { text: title }), h("p", { class: "pg-headline", text: headline })),
      aside ? h("div", { class: "pg-aside" }, aside) : null),
    actions ? h("div", { class: "pg-actions" }, actions) : null);
}

// [{label, cell, unit, mean, tone}] -> at most three stats, each with its plain-language line
export function keyStats(items) {
  return h("div", { class: "pg-stats" }, items.slice(0, 3).map((it) => h("div", { class: "pg-stat" },
    stat({ label: it.label, cell: it.cell, unit: it.unit || "", tone: it.tone || "" }),
    h("p", { class: "pg-mean", text: it.mean }))));
}

// [{title, summary, body}] ; title one of DETAIL_TITLES (others allowed for page-specific detail)
export function detailsList(items) {
  return h("div", { class: "pg-details tech" }, items.filter(Boolean).map((d) =>
    h("details", { class: "acc" }, h("summary", {}, h("span", { class: "acc-title", text: d.title }), h("span", { class: "acc-sum", text: d.summary }), icon("chevron")),
      h("div", { class: "acc-body" }, d.body))));
}

export function bullets(items) { return h("ul", { class: "pg-list" }, items.filter(Boolean).map((t) => h("li", {}, t))); }

export function nextStep(ctx, route, label = null) {
  const i = flowIndex(route);
  const nxt = i >= 0 ? FLOW[i + 1] : null;
  const target = label ? { route: label.route, label: label.text } : nxt ? { route: nxt.route, label: `Next: ${nxt.label}` } : { route: "migration", label: "Next: see the migration" };
  return h("div", { class: "pg-next" }, h("a", { class: "btn primary", href: `/w/${ctx.ws}/${target.route}` }, target.label, icon("arrow")));
}

export function main(node, { title = null } = {}) {
  return h("section", { class: "pg-main" }, title ? h("h2", { class: "pg-h2", text: title }) : null, node);
}
