// Generated from contracts/stages.json by python -m contracts.stages --write-js. Do not edit.
export const STAGES = [
 {
  "id": "detect",
  "label": "Detect",
  "plain": "Find encryption a future quantum computer could break (RSA, ECC)",
  "steps": [
   "detect"
  ]
 },
 {
  "id": "ledger",
  "label": "Proof Chain",
  "plain": "Start the signed record: the Detect evidence is signed (ML-DSA-65) before anything else runs",
  "steps": [
   "ledger_open"
  ]
 },
 {
  "id": "schedule",
  "label": "Plan",
  "plain": "Schedule the migration in weekly waves (MILP, QpiAI Opt local)",
  "steps": [
   "schedule"
  ]
 },
 {
  "id": "capture",
  "label": "Handshakes",
  "plain": "Record real TLS 1.3 handshakes from the lab services",
  "steps": [
   "capture"
  ]
 },
 {
  "id": "gates",
  "label": "Gates",
  "plain": "Check each wave: post-quantum handshake, downgrade refused, compatibility, rollback",
  "steps": [
   "gates"
  ]
 },
 {
  "id": "qaoa",
  "label": "QAOA",
  "plain": "Cross-check one link cutover window with QAOA on a simulator against the exact optimum",
  "steps": [
   "qaoa"
  ]
 },
 {
  "id": "seal",
  "label": "Seal",
  "plain": "Add every result to the Proof Chain and verify every signature and hash",
  "steps": [
   "ledger_ingest",
   "ledger_verify"
  ]
 },
 {
  "id": "report",
  "label": "Report",
  "plain": "Assemble, validate and sign the report",
  "steps": [
   "assemble",
   "validate",
   "report",
   "validate_final"
  ]
 }
];
export const STEPS = STAGES.flatMap((s) => s.steps);
export const STAGE_OF = Object.fromEntries(STAGES.flatMap((s) => s.steps.map((step) => [step, s])));
