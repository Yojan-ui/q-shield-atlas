// node site/js/export_model.js results.json [ledger.json] [handshakes.json] -> {model, number_cells} (tests)
import { readFileSync } from "node:fs";
import { buildSite, numberCells } from "./data.js";

const load = (p) => (p && p !== "-" ? JSON.parse(readFileSync(p, "utf8")) : null);
const model = buildSite(load(process.argv[2]), load(process.argv[3]), load(process.argv[4]));
process.stdout.write(JSON.stringify({ model, number_cells: numberCells(model) }));
