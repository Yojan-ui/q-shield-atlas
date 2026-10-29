// Migration in 3D, monochrome, for a banker. Each bank (or system group) is a cluster; each endpoint / system is a
// sphere. Spheres travel from "classical" (left) to "post-quantum" (right) with their planned week and turn white
// when their wave passed its lab gate (light grey: moved by the plan, not verified in the lab). Thin gates are the
// pipeline steps; small dots flowing along the floor are transactions passing the steps. White light, grey depth,
// no colour. Click a sphere to open its Review item. Only mounted with motion on and WebGL (else the 2D lanes).
import { FLOW } from "../stages.js";

const X0 = -11, X1 = 11, CELL = 1.9, NODE = 0.42;
export const stageX = (i) => X0 + ((X1 - X0) * i) / (FLOW.length - 1);

export function nodeX(asset, week) {  // 0 before its wave, eased across its wave week, 1 after
  const t = Math.min(1, Math.max(0, week - asset.planned_week + 1));
  const e = t < 0.5 ? 2 * t * t : 1 - (-2 * t + 2) ** 2 / 2;
  return X0 + (X1 - X0) * e;
}

// bank name from "host (bank, endpoint)" (real-banks workspace), otherwise the system kind
export function clusterOf(a) {
  const m = /\(([^,()]+), (apex|www|netbanking)\)$/.exec(a.name || "");
  return m ? m[1] : a.kind || "systems";
}

export function layout(assets) {  // cluster centres on a y-z grid, members packed around them
  const groups = new Map();
  for (const a of [...assets].sort((x, y) => x.planned_week - y.planned_week)) {
    const k = clusterOf(a);
    if (!groups.has(k)) groups.set(k, []);
    groups.get(k).push(a);
  }
  const keys = [...groups.keys()], cols = Math.ceil(Math.sqrt(keys.length));
  const pos = new Map();
  keys.forEach((k, ci) => {
    const cy = Math.floor(ci / cols) * CELL, cz = ((ci % cols) - (cols - 1) / 2) * CELL;
    groups.get(k).forEach((a, i) => pos.set(a.id, { y: cy + (i % 2) * 0.55, z: cz + (Math.floor(i / 2) - 0.5) * 0.55 * Math.min(1, i), cluster: k }));
  });
  return { pos, clusters: keys.length, rows: Math.ceil(keys.length / cols), cols };
}

export function buildMigration({ THREE, world, group }, { assets, doneStages, onPick }, initialWeek) {
  const L = layout(assets);
  const height = Math.max(1, L.rows) * CELL, depth = Math.max(1, L.cols) * CELL;
  group.position.set(-3, 3.5 - height / 4, 0);
  group.add(new THREE.AmbientLight(0xffffff, 0.35));
  const key = new THREE.DirectionalLight(0xffffff, 1.6);
  key.position.set(6, 12, 10);
  group.add(key);
  const fog = world.scene.fog;
  world.scene.fog = new THREE.Fog(0x000000, 22, 70);
  const floorZ = -depth / 2 - 0.8, floorY = -0.8;
  group.add(new THREE.Line(new THREE.BufferGeometry().setFromPoints([new THREE.Vector3(X0 - 1, floorY, floorZ), new THREE.Vector3(X1 + 1, floorY, floorZ)]),
    new THREE.LineBasicMaterial({ color: 0x3a3a3a })));
  const gateGeo = new THREE.PlaneGeometry(0.04, height + 2);
  FLOW.forEach((s, i) => {
    const done = doneStages.has(s.id);
    const m = new THREE.Mesh(gateGeo, new THREE.MeshBasicMaterial({ color: done ? 0xffffff : 0x333333, transparent: true, opacity: done ? 0.5 : 0.3 }));
    m.position.set(stageX(i), floorY + (height + 2) / 2, floorZ);
    group.add(m);
  });
  // transactions: dots flowing left to right along the floor, through every pipeline step
  const N = 160, tx = new Float32Array(N * 3), seed = new Float32Array(N);
  for (let i = 0; i < N; i++) { seed[i] = (i * 0.6180339) % 1; tx[i * 3 + 1] = floorY + 0.05; tx[i * 3 + 2] = floorZ + 0.3 + ((i * 0.37) % 1) * 0.6; }
  const txGeo = new THREE.BufferGeometry();
  txGeo.setAttribute("position", new THREE.BufferAttribute(tx, 3));
  group.add(new THREE.Points(txGeo, new THREE.PointsMaterial({ color: 0xbdbdbd, size: 0.09, transparent: true, opacity: 0.75 })));
  // nodes
  const geo = new THREE.SphereGeometry(NODE, 24, 16);
  const mats = { classical: new THREE.MeshStandardMaterial({ color: 0x6e6e6e, roughness: 0.8 }),
    moved: new THREE.MeshStandardMaterial({ color: 0xb0b0b0, roughness: 0.5 }),
    verified: new THREE.MeshStandardMaterial({ color: 0xffffff, roughness: 0.3, emissive: 0x222222 }) };
  const nodes = assets.map((a) => {
    const m = new THREE.Mesh(geo, mats.classical);
    const p = L.pos.get(a.id);
    m.position.set(X0, p.y, p.z);
    m.userData.asset = a;
    group.add(m);
    return { a, m };
  });
  let week = initialWeek, shown = initialWeek;
  const place = (wk) => {
    for (const { a, m } of nodes) {
      m.position.x = nodeX(a, wk);
      m.material = wk < a.planned_week ? mats.classical : a.status === "applied" ? mats.verified : mats.moved;
    }
  };
  place(week);
  // slow dolly between the completed steps, in order
  const stops = FLOW.map((s, i) => (doneStages.has(s.id) ? i : -1)).filter((i) => i >= 0);
  let stop = 0, t = 0, clock = 0;
  const dist = 24 + Math.max(height, depth) * 0.8;
  const next = () => { if (stops.length) world.focus([stageX(stops[stop % stops.length]) * 0.25 - 3, 3.5, 0], dist); stop++; };
  next();
  return {
    pickables: nodes.map((n) => n.m),
    setWeek(w) { week = w; },
    hover(hit) { document.body.style.cursor = hit ? "pointer" : ""; },
    click(hit) { const a = hit && hit.object.userData.asset; if (a && onPick) onPick(a); },
    update(dt) {
      t += dt; clock += dt;
      if (t > 4.5) { t = 0; next(); }
      if (Math.abs(shown - week) > 1e-3) { shown += (week - shown) * Math.min(1, dt * 4); place(shown); }
      for (let i = 0; i < N; i++) tx[i * 3] = X0 - 1 + (((seed[i] + clock * 0.06) % 1) * (X1 - X0 + 2));
      txGeo.attributes.position.needsUpdate = true;
    },
    dispose() { world.scene.fog = fog; document.body.style.cursor = ""; },
  };
}
