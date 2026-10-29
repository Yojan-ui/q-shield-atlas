// Route table. `rail` = position in the route rail (keys 1–6). Views are lazy-loaded modules.
export const ROUTES = [
  { name: "landing", path: "/", title: "Post-quantum migration, proven", view: "landing", camera: "harvest" },
  { name: "signin", path: "/signin", title: "Sign in", view: "signin", guestOnly: true, camera: "cell" },
  { name: "pipeline", path: "/w/:ws/pipeline", title: "Pipeline", view: "pipeline", auth: true, rail: 1, label: "Pipeline", short: "Pipeline", camera: "pipeline" },
  { name: "detect", path: "/w/:ws/detect", title: "Detect", view: "detect", auth: true, rail: 2, label: "Detect", short: "Detect", camera: "detect" },
  { name: "schedule", path: "/w/:ws/schedule", title: "Schedule", view: "schedule", auth: true, rail: 4, label: "Schedule", short: "Plan", camera: "schedule" },
  { name: "handshakes", path: "/w/:ws/handshakes", title: "Handshakes", view: "handshakes", auth: true, rail: 5, label: "Handshakes", short: "TLS", camera: "handshakes" },
  { name: "ledger", path: "/w/:ws/ledger", title: "Proof Chain", view: "ledger", auth: true, rail: 3, label: "Proof Chain", short: "Proof", camera: "ledger" },
  { name: "qaoa", path: "/w/:ws/qaoa", title: "QAOA cross-check", view: "qaoa", auth: true, rail: 6, label: "QAOA", short: "QAOA", camera: "qaoa" },
  { name: "asset", path: "/w/:ws/asset/:assetId", title: "Asset", view: "asset", auth: true, camera: "asset" },
  { name: "users", path: "/settings/users", title: "Users", view: "users", auth: true, role: "admin", camera: "settings" },
  { name: "styleguide", path: "/styleguide", title: "Styleguide", view: "styleguide", dev: true, camera: "settings" },
  { name: "notfound", path: "*", title: "Not found", view: "notfound", camera: "void" },
];
export const RAIL = ROUTES.filter((r) => r.rail).sort((a, b) => a.rail - b.rail);
