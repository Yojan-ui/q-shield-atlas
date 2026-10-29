// The seven pipeline steps as shown everywhere (sidebar, Overview, stepper, guided run, landing, presenter), in the
// backend's real order: detect -> ledger_open -> schedule -> capture/gates -> qaoa -> ledger_ingest/verify -> review.
// Each step lights only from its own stages' status / SSE events (stages = ids in contracts/stages.json).
import { FLOW as SOURCE } from "./stages.js";

const src = (id) => SOURCE.find((f) => f.id === id) || {};
export const FLOW = [
  { id: "detect", route: "detect", label: "Detect", stages: ["detect"], hands: src("detect").hands, does: "Finds RSA, ECC and DH in code, configs, certificates and live TLS, and groups the findings into systems (inventory and drift)." },
  { id: "proof_open", route: "ledger", section: "2", label: "Proof: findings signed", stages: ["ledger"], hands: "The Detect evidence, signed first", does: "The RSA / ECC / DH findings are signed with ML-DSA-65 before planning (detect.run), after the existing chain is verified." },
  { id: "schedule", route: "schedule", label: "Plan", stages: ["schedule"], hands: src("schedule").hands, does: "Plans the migration in weekly waves (QpiAI Opt MILP) within team capacity and dependencies, compared with simple orders." },
  { id: "gates", route: "handshakes", label: "Handshake gates", stages: ["capture", "gates"], hands: src("gates").hands, does: "Tests every wave on real TLS 1.3 lab services: post-quantum handshake, no silent downgrade, compatibility, rollback." },
  { id: "waves", route: "qaoa", label: "Wave selection", stages: ["qaoa"], hands: src("waves").hands, does: "Cross-checks one week's choice of systems with QAOA on a simulator against the exact answer." },
  { id: "proof_verified", route: "ledger", section: "6", label: "Proof: post-quantum verified", stages: ["seal"], hands: "Every result signed, the whole chain re-verified", does: "The ML-KEM (X25519MLKEM768) handshake and gate evidence is signed, and every entry's ML-DSA-65 signature is verified across the chain." },
  { id: "review", route: "review", label: "Review", stages: [], hands: src("review").hands, does: "A person approves or rejects each result with a reason; the decision is signed too." },
];
export const DISPLAY_ORDER = FLOW.map((f) => f.id);
