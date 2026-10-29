import { test } from "node:test";
import assert from "node:assert/strict";
import { packetsOf, packetWidth, pickLanes } from "../static/js/components/channel.js";
import { gateCell, progress, waveStatus } from "../static/js/views/migration.js";

const msg = (dir, type, bytes, extra = {}) => ({ dir, record: "Handshake", type, bytes, ...extra });
const sess = (service_id, offered, group, cert, messages, extra = {}) => ({ service_id, client_groups_offered: offered, negotiated_group: group, cert_alg: cert,
  transcript_sha256: `h-${service_id}-${offered}`, transcript_verified: true, messages, ...extra });
const hyMsgs = [msg("c2s", "ClientHello", 1469, { key_share: [{ group: "X25519MLKEM768", bytes: 1216 }] }), msg("s2c", "ServerHello", 1210),
  { dir: "s2c", record: "ChangeCipherSpec", type: "ChangeCipherSpec", bytes: 1 }, msg("s2c", "Finished", 52)];
const move = { run_id: "r1", sessions: [
  sess("legacy", "X25519MLKEM768:X25519", "X25519", "RSA", [msg("c2s", "ClientHello", 285)]),
  sess("legacy", "X25519:prime256v1", "X25519", "RSA", [msg("c2s", "ClientHello", 285)]),
  sess("hybrid", "X25519MLKEM768:X25519", "X25519MLKEM768", "RSA", hyMsgs),
  sess("pq-auth", "X25519MLKEM768:X25519", "X25519MLKEM768", "ML-DSA", hyMsgs, { signature_type: "mldsa65" })],
  refused_attempts: [sess("hybrid", "X25519:prime256v1", null, null, [msg("c2s", "ClientHello", 285), { dir: "s2c", record: "Alert", type: "Alert", bytes: 2, alert: "fatal handshake_failure" }])] };

test("lanes: same pq-capable client, classical server before, hybrid server after", () => {
  const L = pickLanes(move, { downgrade: [{ service_id: "hybrid", result: "PASS" }] });
  assert.equal(L.before.service_id, "legacy");
  assert.equal(L.before.client_groups_offered, L.after.client_groups_offered);
  assert.equal(L.after.service_id, "hybrid");
  assert.equal(L.pqAuth.service_id, "pq-auth");
  assert.equal(L.downgrade.state, "refused");
  assert.equal(L.downgrade.text, "Refused: no silent downgrade");
});

test("packets are exactly the recorded messages (ChangeCipherSpec listed, not animated), sized by bytes", () => {
  const p = packetsOf(move.sessions[2]);
  assert.deepEqual(p.map((m) => m.type), ["ClientHello", "ServerHello", "Finished"]);
  assert.ok(packetWidth(1469) > packetWidth(285) * 4);
});

test("downgrade without a recorded attempt is 'not run', never a pass", () => {
  const L = pickLanes({ ...move, refused_attempts: [] }, {});
  assert.equal(L.downgrade.state, "not_run");
  assert.match(L.downgrade.text, /^not run/);
  assert.equal(pickLanes({ ...move, refused_attempts: [] }, { downgrade: [{ service_id: "hybrid", result: "FAIL", reason: "completed X25519" }] }).downgrade.state, "accepted");
});

test("unverified transcripts are not replayed", () => {
  const L = pickLanes({ ...move, sessions: move.sessions.map((s) => ({ ...s, transcript_verified: false })) }, {});
  assert.equal(L.before, null); assert.equal(L.after, null);
});

test("waves: status line, gate cells, and real endpoints never count as verified", () => {
  const waves = [{ week: 1, evidence: { lab_services: [{ status: "applied", gates: { passed: true, pq_handshake: { result: "PASS", negotiated_group: "X25519MLKEM768" } } }] } }, { week: 2, evidence: { lab_services: [] } }];
  assert.equal(waveStatus(waves, 1, 3).text, "Wave 1 of 2 · 1 of 1 stand-in verified in lab");
  assert.match(waveStatus(waves, 2, 3).text, /no lab stand-in: not verified in lab/);
  assert.deepEqual(gateCell(waves[0].evidence.lab_services[0], "pq_handshake"), { result: "PASS", text: "X25519MLKEM768" });
  assert.equal(gateCell(waves[0].evidence.lab_services[0], "downgrade").result, "NOT_RUN");
  const a = [{ id: "bank-a", planned_week: 1, status: "applied" }, { id: "lab-b", planned_week: 1, status: "applied" }];
  assert.deepEqual(progress(a, 2, { "bank-a": {} }), { done: 2, total: 2, verified: 1 });
});
