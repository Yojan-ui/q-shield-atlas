// node viz/export_model.js path/to/results.json  ->  prints the display model as JSON (used by tests)
import { readFileSync } from "node:fs";
import { buildModel, numberCells } from "./data.js";

const results = JSON.parse(readFileSync(process.argv[2], "utf8"));
const model = buildModel(results);
process.stdout.write(JSON.stringify({ model, number_cells: numberCells(model) }));
