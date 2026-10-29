// Detect graph: every inventoried system is a node, every declared dependency (depends_on) an edge.
// Colour = what the scan found (red RSA/ECC/DH/DSA, amber needs a live probe, cyan PQC/hybrid only, grey nothing
// vulnerable); size = the risk weight from the plan (an assumption, config/assumptions.json); a white ring marks
// static-vs-live drift from the recorded probe. Layout is a deterministic force layout (seeded, no randomness).
// One instanced mesh per mark type, no per-frame allocation; labels only for hovered / selected / top risk.
export const VULN = new Set(["RSA", "ECC", "DH", "DSA"]);
export const CLASSES = {
  exposed: { label: "Red: RSA / ECC / DH found (quantum-exposed)", color: 0xff4d5e, css: "exposed" },
  caution: { label: "Amber: TLS on library defaults (needs a live probe)", color: 0xf5b84b, css: "caution" },
  pqc: { label: "Cyan: hybrid or post-quantum key exchange already", color: 0x5ed3f3, css: "pqc" },
  safe: { label: "Grey: nothing vulnerable found", color: 0x8c8c8c, css: "neutral" },
};

// Red when the scan found RSA/ECC/DH/DSA, except when key exchange is already PQC/hybrid and the only classical
// finding is a signature (certificate): that is cyan, and the panel says the signature is still classical.
export function classify(evidence = [], needsProbe = false) {
  const vuln = evidence.filter((e) => VULN.has(e.family));
  const pqKex = evidence.some((e) => e.family === "PQC" && e.use !== "sig");
  if (vuln.length && !(pqKex && vuln.every((e) => e.use === "sig"))) return "exposed";
  if (needsProbe) return "caution";
  if (pqKex || evidence.some((e) => e.family === "PQC")) return "pqc";
  return "safe";
}
export const classicalSig = (evidence = []) => [...new Set(evidence.filter((e) => VULN.has(e.family) && e.use === "sig").map((e) => e.family))];

// bank name from "host (bank, endpoint)" (real-banks workspace), else the system kind
export function clusterOf(a) {
  const m = /\(([^,()]+), (apex|www|netbanking)\)$/.exec(a.name || "");
  return m ? m[1] : a.kind || "not in plan";
}

// results.json -> {nodes, edges}. Nodes: the planned assets plus inventory.not_vulnerable; nothing else.
// `inventory` (out/inventory.json) supplies the not-vulnerable entries' evidence; results.json lists only their ids.
export function graphModel(results, observed = {}, inventory = null) {
  const r = results || {}, d = r.detect || {}, inv = d.inventory || {};
  const full = new Map(((inventory && inventory.not_vulnerable) || []).map((x) => [x.id, x]));
  const drift = new Map();
  for (const p of d.probes || []) if ((p.drift || []).length) drift.set(p.service, p.drift);
  const nodes = [];
  for (const a of r.assets || []) {
    nodes.push({ id: a.id, name: a.name || a.id, kind: a.kind, data_class: a.data_class, risk: a.risk_weight ?? 1, depends_on: a.depends_on || [],
      evidence: a.evidence || [], cls: classify(a.evidence, a.needs_live_probe), drift: drift.get(a.id) || null, observed: observed[a.id] || null,
      algorithm: a.algorithm, planned_week: a.planned_week, inPlan: true });
  }
  for (const raw of Array.isArray(inv.not_vulnerable) ? inv.not_vulnerable : []) {
    const n = typeof raw === "string" ? full.get(raw) || { id: raw } : raw;
    nodes.push({ id: n.id, name: n.name || n.id, kind: n.kind || "not in plan", data_class: n.data_class || null, risk: 0, depends_on: n.depends_on || [],
      evidence: n.evidence || [], cls: classify(n.evidence, n.needs_live_probe), drift: drift.get(n.id) || null, observed: observed[n.id] || null, inPlan: false });
  }
  const bank = nodes.some((n) => n.observed);
  nodes.forEach((n) => { n.cluster = bank ? clusterOf(n) : n.kind || "other"; n.families = [...new Set(n.evidence.map((e) => e.family))]; });
  const idx = new Map(nodes.map((n, i) => [n.id, i]));
  const edges = [];
  nodes.forEach((n, i) => { for (const dep of n.depends_on) if (idx.has(dep)) edges.push([i, idx.get(dep)]); });
  return { nodes, edges, bank };
}

const hash = (s) => { let x = 2166136261; for (let i = 0; i < s.length; i++) x = Math.imul(x ^ s.charCodeAt(i), 16777619); return ((x >>> 0) % 10007) / 10007; };

// Deterministic 3D force layout: clusters start on a Fibonacci sphere, then repulsion (spatial hash), edge springs,
// a pull to the cluster centre and to the origin. Returns Float32Array(n*3) and the radius.
export function layout(nodes, edges, iters = 90) {
  const n = nodes.length, P = new Float32Array(n * 3), F = new Float32Array(n * 3);
  const keys = [...new Set(nodes.map((x) => x.cluster))], K = keys.length, R0 = 2 + Math.sqrt(n) * 0.9;
  const centre = new Map(keys.map((k, i) => {
    const y = K === 1 ? 0 : 1 - (2 * i) / (K - 1), r = Math.sqrt(1 - y * y), t = i * 2.399963;
    return [k, [Math.cos(t) * r * R0, y * R0 * 0.75, Math.sin(t) * r * R0]];
  }));
  nodes.forEach((x, i) => { const c = centre.get(x.cluster), h = hash(x.id); P[i * 3] = c[0] + (h - 0.5) * 2; P[i * 3 + 1] = c[1] + (hash(x.id + "y") - 0.5) * 2; P[i * 3 + 2] = c[2] + (hash(x.id + "z") - 0.5) * 2; });
  const CELL = 3.2, grid = new Map();
  for (let it = 0; it < iters; it++) {
    F.fill(0); grid.clear();
    for (let i = 0; i < n; i++) {
      const k = `${Math.floor(P[i * 3] / CELL)},${Math.floor(P[i * 3 + 1] / CELL)},${Math.floor(P[i * 3 + 2] / CELL)}`;
      (grid.get(k) || grid.set(k, []).get(k)).push(i);
    }
    for (let i = 0; i < n; i++) {
      const cx = Math.floor(P[i * 3] / CELL), cy = Math.floor(P[i * 3 + 1] / CELL), cz = Math.floor(P[i * 3 + 2] / CELL);
      for (let a = -1; a <= 1; a++) for (let b = -1; b <= 1; b++) for (let c = -1; c <= 1; c++) {
        const cell = grid.get(`${cx + a},${cy + b},${cz + c}`);
        if (!cell) continue;
        for (const j of cell) {
          if (j <= i) continue;
          const dx = P[i * 3] - P[j * 3], dy = P[i * 3 + 1] - P[j * 3 + 1], dz = P[i * 3 + 2] - P[j * 3 + 2];
          const d2 = dx * dx + dy * dy + dz * dz + 0.01;
          if (d2 > CELL * CELL) continue;
          const f = 2.4 / d2;
          F[i * 3] += dx * f; F[i * 3 + 1] += dy * f; F[i * 3 + 2] += dz * f;
          F[j * 3] -= dx * f; F[j * 3 + 1] -= dy * f; F[j * 3 + 2] -= dz * f;
        }
      }
    }
    for (const [i, j] of edges) for (let a = 0; a < 3; a++) { const d = (P[j * 3 + a] - P[i * 3 + a]) * 0.04; F[i * 3 + a] += d; F[j * 3 + a] -= d; }
    nodes.forEach((x, i) => { const c = centre.get(x.cluster); for (let a = 0; a < 3; a++) F[i * 3 + a] += (c[a] - P[i * 3 + a]) * 0.012 - P[i * 3 + a] * 0.003; });
    const step = 1 - it / iters;
    for (let i = 0; i < n * 3; i++) P[i] += Math.max(-0.5, Math.min(0.5, F[i])) * step;
  }
  let R = 1;
  for (let i = 0; i < n; i++) R = Math.max(R, Math.hypot(P[i * 3], P[i * 3 + 1], P[i * 3 + 2]));
  return { pos: P, radius: R };
}

export const nodeSize = (risk, maxRisk) => 0.3 + 0.36 * Math.sqrt(Math.max(0, risk) / Math.max(1e-9, maxRisk));
export const topByRisk = (nodes, k) => nodes.map((x, i) => [x.risk, i]).sort((a, b) => b[0] - a[0] || a[1] - b[1]).slice(0, k).map((x) => x[1]);

export function buildGraph({ THREE, world, group }, G, L, { reduced, labelsEl, stageEl, onHover, onSelect }) {
  const { nodes, edges } = G, n = nodes.length, P = L.pos;
  const maxRisk = Math.max(1e-9, ...nodes.map((x) => x.risk));
  group.add(new THREE.AmbientLight(0xffffff, 1.1));
  const key = new THREE.DirectionalLight(0xffffff, 0.9); key.position.set(8, 14, 10); group.add(key);
  const graph = new THREE.Group(); group.add(graph);
  group.position.set(-L.radius * 0.35, 0, 0);  // leave room for the side panel on the right
  const m = new THREE.Matrix4(), col = new THREE.Color();
  const sphere = new THREE.SphereGeometry(1, 18, 12);
  const mesh = new THREE.InstancedMesh(sphere, new THREE.MeshBasicMaterial({ fog: false })  /* unlit: the legend colour exactly */, Math.max(1, n));
  mesh.count = n;
  nodes.forEach((x, i) => {
    const s = nodeSize(x.risk, maxRisk);
    mesh.setMatrixAt(i, m.makeScale(s, s, s).setPosition(P[i * 3], P[i * 3 + 1], P[i * 3 + 2]));
    mesh.setColorAt(i, col.setHex(CLASSES[x.cls].color));
  });
  graph.add(mesh);
  // pulsing glow on exposed nodes (shader uses the engine clock; static when reduced motion)
  const ex = nodes.map((x, i) => (x.cls === "exposed" ? i : -1)).filter((i) => i >= 0);
  const uOn = { value: reduced ? 0 : 1 };
  if (ex.length) {
    const seed = new Float32Array(ex.length).map((_, k) => (k * 0.618) % 1);
    const glow = new THREE.InstancedMesh(sphere, new THREE.ShaderMaterial({ transparent: true, depthWrite: false, blending: THREE.AdditiveBlending, fog: false,
      uniforms: { uTime: world.uniforms.uTime, uOn },
      vertexShader: `attribute float aS; uniform float uTime; uniform float uOn; varying float vA;
        void main() { float p = 0.5 + 0.5 * sin(uTime * 2.2 + aS * 6.283); vA = 0.08 + 0.12 * p * uOn;
        gl_Position = projectionMatrix * viewMatrix * modelMatrix * instanceMatrix * vec4(position * (1.3 + 0.3 * p * uOn), 1.0); }`,
      fragmentShader: "varying float vA; void main() { gl_FragColor = vec4(1.0, 0.3, 0.37, vA); }" }), ex.length);
    glow.geometry = sphere.clone();
    glow.geometry.setAttribute("aS", new THREE.InstancedBufferAttribute(seed, 1));
    ex.forEach((i, k) => { const s = nodeSize(nodes[i].risk, maxRisk); glow.setMatrixAt(k, m.makeScale(s, s, s).setPosition(P[i * 3], P[i * 3 + 1], P[i * 3 + 2])); });
    glow.frustumCulled = false;
    graph.add(glow);
  }
  // drift: a white ring around the node
  const dr = nodes.map((x, i) => (x.drift ? i : -1)).filter((i) => i >= 0);
  if (dr.length) {
    const ring = new THREE.InstancedMesh(new THREE.TorusGeometry(1, 0.05, 8, 40), new THREE.MeshBasicMaterial({ color: 0xffffff }), dr.length);
    dr.forEach((i, k) => { const s = nodeSize(nodes[i].risk, maxRisk) * 2.1; ring.setMatrixAt(k, m.makeScale(s, s, s).setPosition(P[i * 3], P[i * 3 + 1], P[i * 3 + 2])); });
    graph.add(ring);
  }
  // edges, and a highlight buffer for the selected node's edges
  const ep = new Float32Array(Math.max(1, edges.length) * 6);
  edges.forEach(([a, b], k) => { ep.set([P[a * 3], P[a * 3 + 1], P[a * 3 + 2], P[b * 3], P[b * 3 + 1], P[b * 3 + 2]], k * 6); });
  const eg = new THREE.BufferGeometry(); eg.setAttribute("position", new THREE.BufferAttribute(ep, 3)); eg.setDrawRange(0, edges.length * 2);
  graph.add(new THREE.LineSegments(eg, new THREE.LineBasicMaterial({ color: 0x9a9a9a })));
  const hp = new Float32Array(Math.max(1, edges.length) * 6), hg = new THREE.BufferGeometry();
  hg.setAttribute("position", new THREE.BufferAttribute(hp, 3)); hg.setDrawRange(0, 0);
  graph.add(new THREE.LineSegments(hg, new THREE.LineBasicMaterial({ color: 0xffffff })));
  // labels: top 8 by risk + hovered + selected, projected each frame into the stage
  const top = topByRisk(nodes, Math.min(6, n));
  const pool = Array.from({ length: top.length + 2 }, () => { const e = document.createElement("span"); e.className = "gr-label"; e.hidden = true; labelsEl.append(e); return e; });
  let hovered = -1, selected = -1, spin = !reduced;
  const v = new THREE.Vector3(), show = [...top, -1, -1], LX = new Float32Array(top.length + 2), LY = new Float32Array(top.length + 2);
  const select = (i) => {
    selected = i;
    let k = 0;
    if (i >= 0) edges.forEach(([a, b], e) => { if (a === i || b === i) { hp.set(ep.subarray(e * 6, e * 6 + 6), k * 6); k++; } });
    hg.setDrawRange(0, k * 2); hg.attributes.position.needsUpdate = true;
    if (onSelect) onSelect(i >= 0 ? nodes[i] : null);
  };
  const reset = () => { graph.rotation.set(0, 0, 0); if (world.resetOrbit) world.resetOrbit(); world.focus([0, 0, 0], L.radius * 2.6 + 6); };
  reset();
  return {
    pickables: [mesh],
    select(id) { select(nodes.findIndex((x) => x.id === id)); },
    reset,
    setSpin(on) { spin = on && !reduced; },
    hover(hit) { hovered = hit && hit.object === mesh ? hit.instanceId : -1; stageEl.style.cursor = hovered >= 0 ? "pointer" : ""; if (onHover) onHover(hovered >= 0 ? nodes[hovered] : null); },
    click(hit) { if (hit && hit.object === mesh) select(hit.instanceId); },
    update(dt) {
      if (spin && selected < 0) graph.rotation.y += dt * 0.07;
      const b = stageEl.getBoundingClientRect();
      show[top.length] = hovered; show[top.length + 1] = selected;
      graph.updateMatrixWorld();
      pool.forEach((e, k) => {
        const i = show[k];
        if (i === undefined || i < 0 || (k >= top.length && top.includes(i))) { e.hidden = true; return; }
        v.set(P[i * 3], P[i * 3 + 1] + nodeSize(nodes[i].risk, maxRisk) + 0.25, P[i * 3 + 2]).applyMatrix4(graph.matrixWorld).project(world.camera);
        if (v.z > 1) { e.hidden = true; return; }
        const x = ((v.x + 1) / 2) * b.width, y = ((1 - v.y) / 2) * b.height, pin = i === selected || i === hovered;
        LX[k] = x; LY[k] = y;
        let clash = false;  // hide a top-risk label that would overlap one already placed (hovered / selected always show)
        if (!pin) for (let q = 0; q < k; q++) if (!pool[q].hidden && Math.abs(LX[q] - x) < 190 && Math.abs(LY[q] - y) < 22) { clash = true; break; }
        if (clash) { e.hidden = true; return; }
        if (e.textContent !== nodes[i].name) e.textContent = nodes[i].name;
        e.hidden = false;
        e.classList.toggle("on", i === selected || i === hovered);
        e.style.transform = `translate(${x}px, ${y}px) translate(-50%, -100%)`;
      });
    },
    dispose() { labelsEl.replaceChildren(); stageEl.style.cursor = ""; },
  };
}
