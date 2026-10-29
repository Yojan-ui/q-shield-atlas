// Display order of the seven pipeline steps (sidebar, Overview cards, stepper, guided run, "Step N of 7").
// The backend runs detect -> ledger_open -> schedule -> capture -> gates -> qaoa -> ledger_ingest/verify -> report
// (contracts/stages.json, generated into stages.js). Order here is presentation only: each step is lit only from its
// own stages' real status / SSE events (FLOW[i].stages), never from its position.
import { FLOW as SOURCE } from "./stages.js";

export const DISPLAY_ORDER = ["detect", "inventory", "ledger", "schedule", "waves", "gates", "review"];
export const FLOW = [...DISPLAY_ORDER.map((id) => SOURCE.find((f) => f.id === id)).filter(Boolean), ...SOURCE.filter((f) => !DISPLAY_ORDER.includes(f.id))];
