import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { CLASSES, classify, graphModel, layout, topByRisk } from "../static/js/scenes/graph.js";

const results = JSON.parse(readFileSync(new URL("../../out/results.json", import.meta.url)));
const inventory = JSON.parse(readFileSync(new URL("../../out/inventory.json", import.meta.url)));

test("Detect graph: node and edge counts equal the inventory", () => {
  const G = graphModel(results, {}, inventory);
  assert.equal(G.nodes.length, results.detect.inventory.assets + results.detect.inventory.not_vulnerable.length);
  assert.equal(G.nodes.length, inventory.assets.length + inventory.not_vulnerable.length);
  const ids = new Set(G.nodes.map((n) => n.id));
  const declared = inventory.assets.flatMap((a) => (a.depends_on || []).filter((d) => ids.has(d)).map((d) => [a.id, d]));
  assert.equal(G.edges.length, declared.length);
  assert.deepEqual(G.edges.map(([a, b]) => [G.nodes[a].id, G.nodes[b].id]).sort(), declared.sort());
  assert.ok(G.nodes.find((n) => n.id === "web-gw").drift, "web-gw: static vs live drift is marked");
  assert.equal(G.nodes.find((n) => n.id === "status-page").cls, "pqc");
});

test("legend colours map to the real families found", () => {
  const G = graphModel(results, {}, inventory);
  for (const n of G.nodes) {
    const fam = new Set(n.evidence.map((e) => e.family));
    if (n.cls === "exposed") assert.ok(["RSA", "ECC", "DH", "DSA"].some((f) => fam.has(f)), n.id);
    if (n.cls === "pqc") assert.ok(fam.has("PQC"), n.id);
  }
  assert.equal(classify([{ family: "RSA", use: "kex" }]), "exposed");
  assert.equal(classify([{ family: "PQC", use: "kex" }, { family: "ECC", use: "kex" }]), "exposed");  // web-gw: hybrid listed but ECC kex too
  assert.equal(classify([{ family: "PQC", use: "kex" }, { family: "ECC", use: "sig" }]), "pqc");  // kex hybrid, only the cert is classical
  assert.equal(classify([], true), "caution");
  assert.equal(classify([]), "safe");
  assert.deepEqual(Object.keys(CLASSES), ["exposed", "caution", "pqc", "safe"]);
});

test("layout is deterministic and finite at 1,000 nodes", () => {
  const nodes = Array.from({ length: 1000 }, (_, i) => ({ id: `n${i}`, cluster: `c${i % 25}`, risk: i % 7 }));
  const edges = Array.from({ length: 999 }, (_, i) => [i + 1, (i * 13) % (i + 1)]);
  const a = layout(nodes, edges, 40), b = layout(nodes, edges, 40);
  assert.deepEqual([...a.pos.slice(0, 30)], [...b.pos.slice(0, 30)]);
  assert.ok([...a.pos].every(Number.isFinite));
  assert.equal(topByRisk(nodes, 3).length, 3);
});

import { clusterOf } from "../static/js/scenes/graph.js";
test("banks become clusters; other systems cluster by kind", () => {
  assert.equal(clusterOf({ name: "netbanking.abc.bank.in (abc, netbanking)", kind: "tls_gateway" }), "abc");
  assert.equal(clusterOf({ name: "Payments API", kind: "api" }), "api");
});
