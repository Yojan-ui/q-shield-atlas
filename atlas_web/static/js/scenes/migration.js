// Migration in 3D, monochrome: one node per system on a path from "classical" (left, dark grey) to
// "post-quantum" (right, white). Node x follows the logged plan at the selected week; brightness says whether
// the wave was verified in the lab. Eight thin gates along the path are the pipeline stages; the camera dollies
// slowly between the stages that have completed (from results.json). White light, soft grey depth, no colour.
import { STAGES } from "../stages.js";

const X0 = -11, X1 = 11, ROWW = 1.3;
export const stageX = (i) => X0 + ((X1 - X0) * i) / (STAGES.length - 1);

export function nodeX(asset, week) {  // 0 before its wave, eased across its wave week, 1 after
  const t = Math.min(1, Math.max(0, week - asset.planned_week + 1));
  const e = t < 0.5 ? 2 * t * t : 1 - (-2 * t + 2) ** 2 / 2;
  return X0 + (X1 - X0) * e;
}

export function buildMigration({ THREE, world, group }, { assets, doneStages }, initialWeek) {
  group.position.set(-3, 3.5, 0);  // frame the whole path inside the stage
  group.add(new THREE.AmbientLight(0xffffff, 0.35));
  const key = new THREE.DirectionalLight(0xffffff, 1.6);
  key.position.set(6, 12, 10);
  group.add(key);
  const fog = world.scene.fog;
  world.scene.fog = new THREE.Fog(0x000000, 18, 52);
  // floor line and stage gates
  const lineMat = new THREE.LineBasicMaterial({ color: 0x3a3a3a });
  group.add(new THREE.Line(new THREE.BufferGeometry().setFromPoints([new THREE.Vector3(X0 - 1, -0.6, -2.6 * ROWW), new THREE.Vector3(X1 + 1, -0.6, -2.6 * ROWW)]), lineMat));
  const gateGeo = new THREE.PlaneGeometry(0.04, 4.5);
  STAGES.forEach((s, i) => {
    const m = new THREE.Mesh(gateGeo, new THREE.MeshBasicMaterial({ color: doneStages.has(s.id) ? 0xffffff : 0x333333, transparent: true, opacity: doneStages.has(s.id) ? 0.55 : 0.35 }));
    m.position.set(stageX(i), 1.6, -2.6 * ROWW);
    group.add(m);
  });
  // nodes
  const geo = new THREE.SphereGeometry(0.45, 24, 16);
  const mats = { classical: new THREE.MeshStandardMaterial({ color: 0x6e6e6e, roughness: 0.8 }),
    moved: new THREE.MeshStandardMaterial({ color: 0xb0b0b0, roughness: 0.5 }),
    verified: new THREE.MeshStandardMaterial({ color: 0xffffff, roughness: 0.3, emissive: 0x222222 }) };
  const nodes = assets.map((a, i) => {
    const m = new THREE.Mesh(geo, mats.classical);
    m.position.set(X0, Math.floor(i / 4) * ROWW, ((i % 4) - 1.5) * ROWW);  // a compact 4-wide block per system set
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
  // slow dolly between completed stages, in order; reduced motion never mounts this scene
  const stops = STAGES.map((s, i) => (doneStages.has(s.id) ? i : -1)).filter((i) => i >= 0);
  let stop = 0, t = 0;
  const next = () => { if (stops.length) world.focus([stageX(stops[stop % stops.length]) * 0.25, 3.2, 0], 27); stop++; };  // wide: the whole path stays in frame
  next();
  return {
    pickables: [],
    setWeek(w) { week = w; },
    update(dt) {
      t += dt;
      if (t > 4.5) { t = 0; next(); }
      if (Math.abs(shown - week) > 1e-3) { shown += (week - shown) * Math.min(1, dt * 4); place(shown); }
    },
    dispose() { world.scene.fog = fog; },
  };
}
