// Pillars: one column per item on a row, used by Pipeline (stages), Benchmark (measured timings) and Review
// (ledger signature status). Height and colour come only from the caller's real fields; an item without data is a
// low wireframe column ("not yet run"). Colour means status only: green passed / verified, red failed, white running
// (pulses), grey idle. Labels are HTML, projected each frame, no per-frame allocation. Same world, same camera.
export const STATE_COLOR = { ok: 0x4ade80, fail: 0xff4d5e, running: 0xffffff, idle: 0x3a3a3a, missing: 0x9a9a9a };
export const pillarHeight = (h) => 0.35 + 5 * Math.max(0, Math.min(1, h ?? 0));
export const GAP = 2.4;
export const pillarX = (i, n) => (i - (n - 1) / 2) * GAP;

export function buildPillars({ THREE, world, group }, items, { labelsEl, stageEl, reduced, onPick }) {
  const n = items.length;
  group.rotation.y = Math.asin(0.6);  // world.focus looks along (-0.6, -0.8): turn the row square to the camera
  group.add(new THREE.AmbientLight(0xffffff, 0.7));
  const key = new THREE.DirectionalLight(0xffffff, 1.2); key.position.set(6, 12, 9); group.add(key);
  const geo = new THREE.BoxGeometry(1, 1, 1).translate(0, 0.5, 0);
  const meshes = items.map((it, i) => {
    const mat = new THREE.MeshStandardMaterial({ color: STATE_COLOR[it.state] || STATE_COLOR.idle, roughness: 0.6, emissive: 0x000000, wireframe: it.state === "missing", fog: false });
    const m = new THREE.Mesh(geo, mat);
    m.scale.set(1, pillarHeight(it.h), 1);
    m.position.set(pillarX(i, n), 0, 0);
    m.userData.i = i;
    group.add(m);
    return m;
  });
  group.add(new THREE.Line(new THREE.BufferGeometry().setFromPoints([new THREE.Vector3(pillarX(0, n) - 1, 0, 0.8), new THREE.Vector3(pillarX(n - 1, n) + 1, 0, 0.8)]),
    new THREE.LineBasicMaterial({ color: 0x3a3a3a })));
  const labels = items.map((it) => { const e = document.createElement("span"); e.className = "pl3-label"; e.textContent = it.label; labelsEl.append(e); return e; });
  const v = new THREE.Vector3();
  let clock = 0;
  world.focus([0, 2, 0], Math.max(8, n * GAP * 0.55 + 4));
  const set = (i, state) => {
    const it = items[i]; if (!it) return;
    it.state = state;
    const mat = meshes[i].material;
    mat.color.setHex(STATE_COLOR[state] || STATE_COLOR.idle); mat.wireframe = state === "missing"; mat.emissive.setHex(0x000000);
  };
  return {
    pickables: meshes,
    set,
    hover(hit) { stageEl.style.cursor = hit ? "pointer" : ""; },
    click(hit) { if (hit && onPick) onPick(items[hit.object.userData.i]); },
    update(dt) {
      clock += dt;
      const pulse = reduced ? 0.35 : 0.2 + 0.3 * (0.5 + 0.5 * Math.sin(clock * 4));
      const b = stageEl.getBoundingClientRect();
      group.updateMatrixWorld();
      for (let i = 0; i < n; i++) {
        if (items[i].state === "running") meshes[i].material.emissive.setScalar(pulse);
        const below = i % 2 === 1;  // alternate above / below so neighbouring labels never collide
        v.set(meshes[i].position.x, below ? -0.35 : pillarHeight(items[i].h) + 0.35, 0).applyMatrix4(group.matrixWorld).project(world.camera);
        const e = labels[i];
        e.hidden = v.z > 1;
        e.style.transform = `translate(${((v.x + 1) / 2) * b.width}px, ${((1 - v.y) / 2) * b.height}px) translate(-50%, ${below ? "0" : "-100%"})`;
      }
    },
    dispose() { labelsEl.replaceChildren(); stageEl.style.cursor = ""; },
  };
}
