// Status chip: icon + text, never colour alone.
import { h, icon } from "../dom.js";

const MAP = {
  PASS: ["pass", "check"], applied: ["pass", "check"], ok: ["pass", "check"], verified: ["pass", "check"], hybrid: ["accent", "lattice"],
  FAIL: ["fail", "cross"], fail: ["fail", "cross"], rollback_failed: ["fail", "cross"], tampered: ["fail", "cross"],
  "HNDL-exposed": ["exposed", "warn"], classical: ["exposed", "warn"],
  rolled_back: ["caution", "rewind"], partially_verified: ["caution", "dotted"], NOT_RUN: ["neutral", "dash"], running: ["accent", "spin"],
  not_verified_in_lab: ["ghost", "dotted"], planned: ["neutral", "ring"], idle: ["neutral", "dash"], pending: ["neutral", "ring"],
  "not yet run": ["neutral", "dash"], not_vulnerable: ["neutral", "check"], assumption: ["caution", "info"], recorded: ["neutral", "info"],
};
export const chipKinds = Object.keys(MAP);

export function chip(status, text = null) {
  const [cls, ic] = MAP[status] || ["neutral", "dash"];
  return h("span", { class: `chip ${cls}`, "data-status": status }, icon(ic), text ?? String(status).replaceAll("_", " "));
}
