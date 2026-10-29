// Move in 3D: sender (left) and receiver (right) blocks with one lane per recorded handshake (the same lanes the
// SVG replay draws). Each packet is one recorded TLS message, as long as its recorded byte size, with its key share
// as a dark inner block; it moves on the same replay clock (t in message units) as the SVG. Red classical, green
// hybrid, white the downgrade attempt. No packet exists unless the transcript was recorded (and hash-checked).
import { flight, packetsOf } from "../components/channel.js";
import { placeLabels } from "./labels.js";

export const UNIT = 0.0036;  // scene units per recorded byte
export const packetLength = (bytes) => Math.max(0.12, (bytes || 0) * UNIT);
const SX = -6.5, RX = 6.5, LANE = 3.4, TONE = { exp: 0xff4d5e, ok: 0x4ade80, pqc: 0x5ed3f3, neutral: 0xffffff };

export function buildLanes3d({ THREE, world, group }, lanes, { labelsEl, stageEl, autoplay = false, reduced = false }) {
  group.rotation.y = Math.asin(0.6);  // square to the world.focus view direction
  group.add(new THREE.AmbientLight(0xffffff, 0.8));
  const key = new THREE.DirectionalLight(0xffffff, 1.0); key.position.set(5, 10, 8); group.add(key);
  const box = new THREE.BoxGeometry(1, 1, 1);
  const endMat = new THREE.MeshStandardMaterial({ color: 0x3a3a3a, roughness: 0.8, fog: false });
  const wire = new THREE.LineBasicMaterial({ color: 0x3a3a3a });
  const shareMat = new THREE.MeshBasicMaterial({ color: 0x000000, transparent: true, opacity: 0.45, fog: false });
  // lanes stacked vertically (top: before), so each stays separate on screen from the elevated camera
  const L = lanes.map((l, i) => {
    const y = (lanes.length - 1 - i) * LANE, z = 0;
    for (const x of [SX - 0.9, RX + 0.9]) { const m = new THREE.Mesh(box, endMat); m.scale.set(1.2, 1.4, 1.2); m.position.set(x, y + 0.4, z); group.add(m); }
    group.add(new THREE.Line(new THREE.BufferGeometry().setFromPoints([new THREE.Vector3(SX, y, z), new THREE.Vector3(RX, y, z)]), wire));
    const mat = new THREE.MeshStandardMaterial({ color: TONE[l.tone] || TONE.neutral, roughness: 0.5, fog: false });
    const pk = packetsOf(l.session).map((m) => {
      const len = Math.min(packetLength(m.bytes), RX - SX - 0.4);
      const g = new THREE.Group();
      const body = new THREE.Mesh(box, mat); body.scale.set(len, 0.5, 0.7); g.add(body);
      const share = (m.key_share || []).find((k) => k.bytes);
      if (share) { const s = new THREE.Mesh(box, shareMat); const sl = Math.min(len, packetLength(share.bytes)); s.scale.set(sl, 0.52, 0.72); s.position.x = (sl - len) / 2 * (m.dir === "c2s" ? -1 : 1); g.add(s); }
      g.visible = false; g.position.set(0, y + 0.3, z); group.add(g);
      return { m, g, len };
    });
    const title = document.createElement("span"); title.className = "pl3-label"; title.hidden = true; title.textContent = l.session ? l.title : `${l.title}: not run`; labelsEl.append(title);
    const cur = document.createElement("span"); cur.className = "pl3-label"; cur.hidden = true; labelsEl.append(cur);  // shown once placed
    return { y, z, pk, title, cur, shown: -2 };
  });
  world.fit(group, [[SX - 1.6, -0.7, -0.8], [RX + 1.6, (lanes.length - 1) * LANE + 1.9, 0.8]]);  // auto-fit, refit on resize
  const v = new THREE.Vector3();
  const LB = [...L.map((l) => ({ e: l.title, x: 0, y: 0 })), ...L.map((l) => ({ e: l.cur, x: 0, y: 0, below: true }))], placed = [];  // titles first
  const place = (k, x, y, z, b) => {
    v.set(x, y, z).applyMatrix4(group.matrixWorld).project(world.camera);
    const it = LB[k]; it.off = v.z > 1 || !it.e.textContent; it.x = ((v.x + 1) / 2) * b.width; it.y = ((1 - v.y) / 2) * b.height;
  };
  let t = 0;
  return {
    pickables: [],
    set(x) { t = x; },
    update(dt) {
      if (autoplay && !reduced) { const n = Math.max(1, ...L.map((l) => l.pk.length)); t = (t + dt * 1.1) % (n + 1.6); }  // guided run: loop the recorded messages
      const b = stageEl.getBoundingClientRect();
      group.updateMatrixWorld();
      for (const l of L) {
        l.pk.forEach(({ m, g, len }, k) => {
          const f = flight(t, k);
          g.visible = f !== null;
          if (f !== null) { const e = f < 0.5 ? 2 * f * f : 1 - (-2 * f + 2) ** 2 / 2, span = RX - SX - len; g.position.x = m.dir === "c2s" ? SX + len / 2 + e * span : RX - len / 2 - e * span; }
        });
        const k0 = Math.floor(t);
        if (k0 !== l.shown) { l.shown = k0; const p = l.pk[k0]; l.cur.textContent = p ? `${p.m.dir === "c2s" ? "→" : "←"} ${p.m.type} · ${p.m.bytes.toLocaleString("en-US")} B` : ""; }
        const k = L.indexOf(l);
        place(k, SX - 0.9, l.y + 1.45, l.z, b);
        place(L.length + k, 0, l.y - 0.55, l.z, b);  // below the wire, lower priority than the titles
      }
      placeLabels(LB, b.width, b.height, placed);
    },
    dispose() { labelsEl.replaceChildren(); },
  };
}
