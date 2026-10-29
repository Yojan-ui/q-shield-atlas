// Route table. `rail` = position in the sidebar and keyboard key (1–9); `step` = the displayed pipeline step number
// (display order in js/flow.js; the backend order lives in contracts/stages.json); `group` = sidebar section. Views are lazy-loaded modules.
export const ROUTES = [
  { name: "landing", path: "/", title: "Post-quantum migration, proven", view: "landing", camera: "harvest" },
  { name: "signin", path: "/signin", title: "Sign in", view: "signin", guestOnly: true, camera: "cell" },
  { name: "pipeline", path: "/w/:ws/pipeline", title: "Overview", view: "pipeline", auth: true, rail: 1, label: "Overview", short: "Home", group: "start", camera: "pipeline" },
  { name: "detect", path: "/w/:ws/detect", title: "Detect", view: "detect", auth: true, rail: 2, step: 1, label: "Detect", short: "Detect", group: "flow", camera: "detect" },
  { name: "inventory", path: "/w/:ws/inventory", title: "Inventory & drift", view: "inventory", auth: true, rail: 3, step: 2, label: "Inventory & drift", short: "Inventory", group: "flow", camera: "detect" },
  { name: "ledger", path: "/w/:ws/ledger", title: "Ledger", view: "ledger", auth: true, rail: 4, step: 3, label: "Ledger", short: "Ledger", group: "flow", camera: "ledger" },
  { name: "schedule", path: "/w/:ws/schedule", title: "Schedule", view: "schedule", auth: true, rail: 5, step: 4, label: "Schedule", short: "Plan", group: "flow", camera: "schedule" },
  { name: "qaoa", path: "/w/:ws/qaoa", title: "Wave selection", view: "qaoa", auth: true, rail: 6, step: 5, label: "Wave selection", short: "QAOA", group: "flow", camera: "qaoa" },
  { name: "handshakes", path: "/w/:ws/handshakes", title: "Handshake gates", view: "handshakes", auth: true, rail: 7, step: 6, label: "Handshake gates", short: "Gates", group: "flow", camera: "handshakes" },
  { name: "review", path: "/w/:ws/review", title: "Review", view: "review", auth: true, rail: 8, step: 7, label: "Review", short: "Review", group: "flow", camera: "settings" },
  { name: "migration", path: "/w/:ws/migration", title: "Migration", view: "migration", auth: true, rail: 9, label: "Migration", short: "Move", group: "more", camera: "migration" },
  { name: "bench", path: "/w/:ws/bench", title: "Benchmark", view: "bench", auth: true, rail: 10, label: "Benchmark", short: "Bench", group: "more", camera: "settings" },
  { name: "glossary", path: "/glossary", title: "Glossary", view: "glossary", rail: 11, label: "Glossary", short: "Terms", group: "more", camera: "void" },
  { name: "asset", path: "/w/:ws/asset/:assetId", title: "Asset", view: "asset", auth: true, camera: "asset" },
  { name: "users", path: "/settings/users", title: "Users", view: "users", auth: true, role: "admin", camera: "settings" },
  { name: "styleguide", path: "/styleguide", title: "Styleguide", view: "styleguide", dev: true, camera: "settings" },
  { name: "notfound", path: "*", title: "Not found", view: "notfound", camera: "void" },
];
export const RAIL = ROUTES.filter((r) => r.rail).sort((a, b) => a.rail - b.rail);
