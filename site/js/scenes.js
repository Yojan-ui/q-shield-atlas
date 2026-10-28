// "The Lattice": one WebGL canvas, chapters placed along -z, camera flown by scroll progress.
// Geometry is driven only by the display model from data.js; numbers are never invented here
// (sizes are scaled from real values, and labels show the model's cells).
import * as THREE from "/vendor/three-0.170.0.module.min.js";
import { NOT_YET_RUN } from "./data.js";

const CH_Z = [0, -70, -140, -210];
const X_OFF = 7; // scenes sit right of the text panel
const FAMILY_COLOR = { RSA: 0xff4a3d, ECC: 0xff8a3d, DH: 0xe05cff, DSA: 0xff4a3d, PQC: 0x46f2b0, UNKNOWN: 0xffb547 };
const easeInOut = (t) => t * t * (3 - 2 * t);
const clamp01 = (t) => Math.min(1, Math.max(0, t));

const POINT_VS = `
attribute vec3 aA; attribute vec3 aB; attribute vec4 aP; attribute vec3 aC;
uniform float uTime, uSize, uDpr; uniform int uMode;
varying vec3 vC; varying float vAlpha;
void main() {
  float t = fract(uTime * aP.y + aP.x);
  vec3 p; vAlpha = 1.0;
  if (uMode == 0) {               // packets falling into the vault
    float e = t * t;
    p = mix(aA, aB, e);
    vAlpha = smoothstep(0.0, 0.15, t) * (1.0 - smoothstep(0.92, 1.0, t));
  } else {                         // handshake strands: aP.z = braid side (-1, 0, +1), aP.w = blocked by a wall
    float tt = aP.w > 0.5 ? min(t, 0.55) : t;
    p = mix(aA, aB, tt);
    float open = 1.0 - smoothstep(0.30, 0.62, tt);
    float ph = tt * 18.0 + aP.z * 1.5708;
    p.x += aP.z * 1.7 * open + sin(ph) * 0.35 * open * abs(aP.z);
    p.y += cos(ph) * 0.35 * open * abs(aP.z);
    p += 0.10 * vec3(sin(aP.x * 91.0), cos(aP.x * 57.0), 0.0);
    if (aP.w > 0.5 && t > 0.55) vAlpha = max(0.0, 1.0 - (t - 0.55) * 7.0);
  }
  vC = aC;
  vec4 mv = modelViewMatrix * vec4(p, 1.0);
  gl_PointSize = uSize * uDpr * (60.0 / max(1.0, -mv.z));
  gl_Position = projectionMatrix * mv;
}`;
const POINT_FS = `
varying vec3 vC; varying float vAlpha;
void main() {
  float d = length(gl_PointCoord - 0.5);
  if (d > 0.5) discard;
  gl_FragColor = vec4(vC, vAlpha * (1.0 - d * 1.6));
}`;

function particleMaterial(mode, size, dpr) {
  return new THREE.ShaderMaterial({
    vertexShader: POINT_VS, fragmentShader: POINT_FS, transparent: true, depthWrite: false,
    blending: THREE.AdditiveBlending,
    uniforms: { uTime: { value: 0 }, uSize: { value: size }, uDpr: { value: dpr }, uMode: { value: mode } },
  });
}

function particleGeometry(items) {
  const n = items.length, g = new THREE.BufferGeometry();
  const A = new Float32Array(n * 3), B = new Float32Array(n * 3), P = new Float32Array(n * 4), C = new Float32Array(n * 3);
  items.forEach((it, i) => { A.set(it.a, i * 3); B.set(it.b, i * 3); P.set(it.p, i * 4); C.set(it.c, i * 3); });
  g.setAttribute("position", new THREE.BufferAttribute(A, 3)); // required by three; the shader uses aA/aB
  g.setAttribute("aA", new THREE.BufferAttribute(A, 3));
  g.setAttribute("aB", new THREE.BufferAttribute(B, 3));
  g.setAttribute("aP", new THREE.BufferAttribute(P, 4));
  g.setAttribute("aC", new THREE.BufferAttribute(C, 3));
  g.boundingSphere = new THREE.Sphere(new THREE.Vector3(), 1e4);
  return g;
}

// deterministic pseudo-random (layout only)
function rng(seed) { let s = seed >>> 0; return () => ((s = (s * 1664525 + 1013904223) >>> 0) / 4294967296); }
const rgb = (hex) => { const c = new THREE.Color(hex); return [c.r, c.g, c.b]; };

export function createWorld(canvas, { reduced = false, dprCap = 2 } = {}) {
  const renderer = new THREE.WebGLRenderer({ canvas, antialias: true, powerPreference: "high-performance" });
  const dpr = Math.min(window.devicePixelRatio || 1, dprCap);
  renderer.setPixelRatio(dpr);
  const scene = new THREE.Scene();
  scene.background = new THREE.Color(0x04060a);
  scene.fog = new THREE.Fog(0x04060a, 30, 120);
  const camera = new THREE.PerspectiveCamera(50, 1, 0.1, 400);
  scene.add(new THREE.AmbientLight(0x9fb4c8, 0.55));
  const sun = new THREE.DirectionalLight(0xffffff, 1.2);
  sun.position.set(20, 40, 30);
  scene.add(sun);

  // ---- lattice (1 draw call) ----
  {
    const pts = [];
    for (let x = -40; x <= 40; x += 4) for (let y = -12; y <= 24; y += 4) for (let z = 30; z >= -250; z -= 4) pts.push(x, y, z);
    const g = new THREE.BufferGeometry();
    g.setAttribute("position", new THREE.Float32BufferAttribute(pts, 3));
    scene.add(new THREE.Points(g, new THREE.PointsMaterial({ color: 0x5f86a8, size: 0.16, transparent: true, opacity: 0.55, depthWrite: false })));
  }

  const chapters = CH_Z.map((z) => { const grp = new THREE.Group(); grp.position.set(X_OFF, 0, z); scene.add(grp); return grp; });
  const labels = []; // {el, obj, offset, chapter}
  const labelHost = document.getElementById("labels");
  function label(chapter, text, cls, pos) {
    const el = document.createElement("div");
    el.className = `lbl ${cls || ""}`;
    el.textContent = text;
    labelHost.append(el);
    labels.push({ el, pos: pos.clone(), chapter }); // local to the chapter group
  }
  function clearLabels(chapter) {
    for (let i = labels.length - 1; i >= 0; i--) if (labels[i].chapter === chapter) { labels[i].el.remove(); labels.splice(i, 1); }
  }
  const disposeGroup = (grp) => grp.traverse((o) => { o.geometry && o.geometry.dispose(); o.material && o.material.dispose(); }) || grp.clear();

  // ---- chapter 1: harvest vault + packets ----
  const ch1 = { glowTarget: 0.2, glow: 0.2 };
  function buildHarvest(m) {
    disposeGroup(chapters[0]);
    const vault = new THREE.LineSegments(new THREE.EdgesGeometry(new THREE.IcosahedronGeometry(4.2, 1)),
      new THREE.LineBasicMaterial({ color: 0x7fd3ff, transparent: true, opacity: 0.55 }));
    ch1.core = new THREE.Mesh(new THREE.IcosahedronGeometry(3.3, 2),
      new THREE.MeshBasicMaterial({ color: 0xff4a3d, transparent: true, opacity: 0.2, blending: THREE.AdditiveBlending, depthWrite: false }));
    const r = rng(7), items = [];
    for (let i = 0; i < 1800; i++) {
      const th = r() * Math.PI * 2, ph = Math.acos(2 * r() - 1), rad = 26 + r() * 22;
      const a = [Math.sin(ph) * Math.cos(th) * rad, Math.cos(ph) * rad * 0.6, Math.sin(ph) * Math.sin(th) * rad];
      items.push({ a, b: [0, 0, 0], p: [r(), 0.05 + r() * 0.08, 0, 0], c: r() < 0.5 ? rgb(0xff4a3d) : rgb(0xff8a3d) });
    }
    ch1.packets = new THREE.Points(particleGeometry(items), particleMaterial(0, 3.2, dpr));
    chapters[0].add(vault, ch1.core, ch1.packets);
    chapters[0].position.y = 1;
    ch1.vault = vault;
  }
  function setHarvest(m, scenario) {
    if (!m.available || !m.byScenario[scenario]) return;
    const c = m.byScenario[scenario].exposure;
    ch1.glowTarget = c.kind === "number" ? 0.12 + 0.68 * (c.value / m.glowMax) : 0.05;
  }

  // ---- chapter 2: the code city ----
  const ch2 = { markers: null, info: [] };
  function buildDetect(m) {
    disposeGroup(chapters[1]); clearLabels(1); ch2.info = [];
    if (!m.available) { label(1, NOT_YET_RUN, "dim", new THREE.Vector3(0, 2, 0)); return; }
    const lit = m.files, total = lit.length + m.darkColumns;
    const cols = Math.ceil(Math.sqrt(total * 1.6)), sp = 2.7, U = 0.48;
    const pos = (i) => [((i % cols) - (cols - 1) / 2) * sp, ((Math.floor(i / cols)) - (Math.ceil(total / cols) - 1) / 2) * sp];
    const order = [...lit.map((f, i) => ({ f, i })), ...Array.from({ length: m.darkColumns }, () => ({ f: null }))];
    const shuffle = rng(11); order.sort(() => shuffle() - 0.5);
    const colMesh = new THREE.InstancedMesh(new THREE.BoxGeometry(1, 1, 1), new THREE.MeshLambertMaterial({ color: 0xffffff }), total);
    const nMarkers = lit.reduce((a, f) => a + f.findings.length, 0);
    const mk = new THREE.InstancedMesh(new THREE.BoxGeometry(1.75, 0.26, 1.75), new THREE.MeshBasicMaterial({ color: 0xffffff }), Math.max(1, nMarkers));
    const M = new THREE.Matrix4(), q = new THREE.Quaternion(), S = new THREE.Vector3(), P = new THREE.Vector3(), col = new THREE.Color();
    let k = 0;
    order.forEach((o, i) => {
      const [x, z] = pos(i);
      const maxLine = o.f ? Math.max(...o.f.findings.map((x) => (x.line.kind === "number" ? x.line.value : 1))) : 0;
      const h = o.f ? (maxLine + 1.5) * U : 1.1;
      colMesh.setMatrixAt(i, M.compose(P.set(x, h / 2, z), q, S.set(1.45, h, 1.45)));
      colMesh.setColorAt(i, col.set(o.f ? 0x22344a : 0x0d141d));
      if (!o.f) return;
      for (const fd of o.f.findings) {
        const y = (fd.line.kind === "number" ? fd.line.value : 1) * U;
        mk.setMatrixAt(k, M.compose(P.set(x, y, z), q, S.set(1, 1, 1)));
        mk.setColorAt(k, col.set(FAMILY_COLOR[fd.family] || 0xffffff));
        ch2.info[k] = { file: o.f.file, ...fd };
        k++;
      }
    });
    mk.count = k;
    chapters[1].add(colMesh, mk);
    ch2.markers = mk;
    chapters[1].position.y = -3;
  }

  // ---- chapter 3: exposure towers ----
  const FLOORS = 24, TOWER_H = 13;
  const ch3 = { towers: {}, cur: {}, target: {} };
  function buildSchedule(m) {
    disposeGroup(chapters[2]); clearLabels(2); ch3.towers = {};
    if (!m.available) { label(2, NOT_YET_RUN, "dim", new THREE.Vector3(0, 2, 0)); return; }
    const spec = { fcfs: [-7.5, 0xff8a3d, 0.2, "FCFS"], optimized: [0, 0xdff4ff, 1, "QpiAI Opt"], greedy: [7.5, 0x9aa6b5, 0.2, "greedy"] };
    for (const [key, [x, color, op, name]] of Object.entries(spec)) {
      const mat = op < 1 ? new THREE.MeshBasicMaterial({ color, transparent: true, opacity: op, depthWrite: false })
        : new THREE.MeshLambertMaterial({ color, emissive: 0x0b2236 });
      const mesh = new THREE.InstancedMesh(new THREE.BoxGeometry(3.4, 1, 3.4), mat, FLOORS);
      mesh.position.x = x;
      chapters[2].add(mesh);
      ch3.towers[key] = mesh;
      label(2, name, key === "optimized" ? "" : "dim", new THREE.Vector3(x, -1.2, 0));
    }
    chapters[2].position.y = -4;
  }
  function towerHeights(m, scenario, wf) {
    if (!m.available) return null;
    const all = Object.values(m.series).flatMap((s) => (s[scenario] || []).map((c) => c.value || 0));
    const max = Math.max(...all) || 1;
    const out = {};
    for (const [k, s] of Object.entries(m.series)) {
      const pts = s[scenario] || [];
      const i = Math.min(Math.floor(wf), pts.length - 1), j = Math.min(i + 1, pts.length - 1), f = wf - i;
      const v = (pts[i] ? pts[i].value : 0) * (1 - f) + (pts[j] ? pts[j].value : 0) * f; // visual interpolation only
      out[k] = (TOWER_H * v) / max;
    }
    return out;
  }
  function drawTowers(dt) {
    const M = new THREE.Matrix4(), q = new THREE.Quaternion(), S = new THREE.Vector3(), P = new THREE.Vector3();
    const th = TOWER_H / FLOORS;
    for (const [k, mesh] of Object.entries(ch3.towers)) {
      const tgt = ch3.target[k] ?? 0;
      ch3.cur[k] = reduced ? tgt : (ch3.cur[k] ?? tgt) + (tgt - (ch3.cur[k] ?? tgt)) * Math.min(1, dt * 8);
      const H = ch3.cur[k];
      for (let f = 0; f < FLOORS; f++) {
        const y0 = f * th, t = Math.max(0, Math.min(th * 0.86, H - y0));
        mesh.setMatrixAt(f, M.compose(P.set(0, y0 + t / 2, 0), q, t > 0 ? S.set(1, t, 1) : S.set(0, 0, 0))); // empty floors vanish
      }
      mesh.instanceMatrix.needsUpdate = true;
    }
  }

  // ---- chapter 4: handshake strands ----
  const ch4 = {};
  function buildHandshake(m) {
    disposeGroup(chapters[3]); clearLabels(3);
    if (!m.available) { label(3, NOT_YET_RUN, "dim", new THREE.Vector3(0, 2, 0)); return; }
    const svcs = m.services, xs = svcs.map((_, i) => (i - (svcs.length - 1) / 2) * 11);
    const pillars = new THREE.InstancedMesh(new THREE.BoxGeometry(2.6, 6, 2.6), new THREE.MeshLambertMaterial({ color: 0xffffff }), svcs.length);
    const walls = svcs.filter((s) => s.downgrade === "PASS");
    const wallMesh = new THREE.InstancedMesh(new THREE.BoxGeometry(5.2, 4.6, 0.12),
      new THREE.MeshBasicMaterial({ color: 0x46f2b0, transparent: true, opacity: 0.2, depthWrite: false }), Math.max(1, walls.length));
    const beams = svcs.filter((s) => s.kexGate !== "PASS");
    const beamMesh = new THREE.InstancedMesh(new THREE.CylinderGeometry(0.16, 0.16, 26, 12),
      new THREE.MeshBasicMaterial({ color: 0xff2a20, transparent: true, opacity: 0.85, blending: THREE.AdditiveBlending, depthWrite: false }), Math.max(1, beams.length));
    const M = new THREE.Matrix4(), q = new THREE.Quaternion(), S = new THREE.Vector3(1, 1, 1), P = new THREE.Vector3(), col = new THREE.Color();
    const items = [], r = rng(23), zC = 24, zS = 1.4, zWall = zC + (zS - zC) * 0.55;
    let w = 0, b = 0;
    svcs.forEach((s, i) => {
      const x = xs[i];
      pillars.setMatrixAt(i, M.compose(P.set(x, 3, 0), q, S));
      pillars.setColorAt(i, col.set(s.kexGate === "PASS" ? (s.authGate === "PASS" ? 0x1f5a48 : 0x23405a) : 0x4a1f1f));
      if (s.downgrade === "PASS") wallMesh.setMatrixAt(w++, M.compose(P.set(x + 2.6, 1.9, zWall), q, S));
      if (s.kexGate !== "PASS") beamMesh.setMatrixAt(b++, M.compose(P.set(x, 13, 0), q, S));
      const hybrid = s.strands.length > 1;
      const sides = hybrid ? [-1, 1] : [0];
      sides.forEach((side, j) => {
        const c = hybrid ? (j === 0 ? rgb(0x7fd3ff) : rgb(0x46f2b0)) : rgb(0xff4a3d);
        for (let n = 0; n < 240; n++) items.push({ a: [x, 1.8, zC], b: [x, 1.8, zS], p: [r(), 0.12 + r() * 0.05, side, 0], c });
      });
      // classical-only client: blocked by a wall when the downgrade gate PASSed, else it gets through
      const blocked = s.downgrade === "PASS" ? 1 : 0;
      for (let n = 0; n < 150; n++) items.push({ a: [x + 2.6, 1.2, zC], b: [x + 2.6, 1.2, zS], p: [r(), 0.12 + r() * 0.05, 0, blocked], c: rgb(0xffb547) });
      const strandsText = s.strands.join(" + ");
      label(3, s.id, s.kexGate === "PASS" ? (s.authGate === "PASS" ? "mint" : "") : "red", new THREE.Vector3(x, 7.2, 0));
      label(3, strandsText, "dim", new THREE.Vector3(x, 0.2, zC - 2));
      if (s.downgrade === "PASS") label(3, "refused", "dim", new THREE.Vector3(x + 2.6, 4.6, zWall));
    });
    wallMesh.count = w; beamMesh.count = b;
    ch4.strands = new THREE.Points(particleGeometry(items), particleMaterial(1, 2.6, dpr));
    chapters[3].add(pillars, wallMesh, beamMesh, ch4.strands);
    chapters[3].position.y = -1;
  }

  // ---- camera path ----
  const K = CH_Z.map((z, i) => ({
    a: new THREE.Vector3(X_OFF + [10, 14, 16, 4][i], [4, 16, 7, 15][i], z + [26, 30, 26, 46][i]),
    b: new THREE.Vector3(X_OFF + [-6, 6, -6, 9][i], [2, 9, 10, 14][i], z + [16, 18, 22, 40][i]),
    look: new THREE.Vector3(X_OFF - [4, 4, 4, 8][i], [0, 0, 3, 2][i], z + [0, 0, 0, 6][i]),
  }));
  function cameraAt(chapter, p) {
    const i = Math.min(chapter, K.length - 1), next = K[Math.min(i + 1, K.length - 1)];
    const pos = new THREE.Vector3(), look = new THREE.Vector3();
    if (reduced) { pos.copy(K[i].a).lerp(K[i].b, 0.5); look.copy(K[i].look); return { pos, look }; }
    if (p < 0.78 || i === K.length - 1) {
      const e = easeInOut(clamp01(p / 0.78));
      pos.copy(K[i].a).lerp(K[i].b, e); look.copy(K[i].look);
    } else {
      const e = easeInOut((p - 0.78) / 0.22);
      pos.copy(K[i].b).lerp(next.a, e); look.copy(K[i].look).lerp(next.look, e);
    }
    return { pos, look };
  }

  // ---- hover (chapter 2 only) ----
  const ray = new THREE.Raycaster(), ptr = new THREE.Vector2(9, 9);
  function hover() {
    if (!ch2.markers || !chapters[1].visible) return null;
    ray.setFromCamera(ptr, camera);
    const hit = ray.intersectObject(ch2.markers, false)[0];
    return hit ? ch2.info[hit.instanceId] : null;
  }

  let model = null, scenario = null, t0 = performance.now(), last = t0;
  const api = {
    setModel(m, scen) {
      const first = !model;
      model = m;
      if (first) { buildHarvest(m.harvest); }
      buildDetect(m.detect); buildSchedule(m.schedule); buildHandshake(m.handshake);
      api.setScenario(scen || scenario || (m.harvest.scenarios || [])[0]);
    },
    setScenario(s) { scenario = s; if (model) setHarvest(model.harvest, s); },
    setPointer(x, y) { ptr.set(x, y); },
    hover,
    renderer,
    frame(state) { // state: {chapter, p, week}
      const now = performance.now(), dt = Math.min(0.1, (now - last) / 1000);
      last = now;
      const w = canvas.clientWidth, h = canvas.clientHeight;
      if (canvas.width !== Math.floor(w * dpr) || canvas.height !== Math.floor(h * dpr)) {
        renderer.setSize(w, h, false); camera.aspect = w / h; camera.updateProjectionMatrix();
      }
      const { pos, look } = cameraAt(state.chapter, state.p);
      camera.position.copy(pos); camera.lookAt(look);
      chapters.forEach((g, i) => { g.visible = Math.abs(camera.position.z - CH_Z[i]) < 56; }); // spacing is 70
      const time = reduced ? 3.7 : (now - t0) / 1000;
      if (ch1.packets) ch1.packets.material.uniforms.uTime.value = time;
      if (ch4.strands) ch4.strands.material.uniforms.uTime.value = time;
      ch1.glow += (ch1.glowTarget - ch1.glow) * (reduced ? 1 : Math.min(1, dt * 4));
      if (ch1.core) { ch1.core.material.opacity = ch1.glow; if (!reduced) ch1.vault.rotation.y += dt * 0.15; }
      if (model && model.schedule.available) ch3.target = towerHeights(model.schedule, scenario, state.week) || {};
      drawTowers(dt);
      renderer.render(scene, camera);
      // DOM labels for the visible chapters
      const v = new THREE.Vector3();
      for (const l of labels) {
        if (!chapters[l.chapter].visible) { l.el.style.display = "none"; continue; }
        v.copy(l.pos).add(chapters[l.chapter].position).project(camera);
        const on = v.z < 1 && Math.abs(v.x) < 1.1 && Math.abs(v.y) < 1.1;
        l.el.style.display = on ? "block" : "none";
        if (on) { l.el.style.left = `${(v.x * 0.5 + 0.5) * w}px`; l.el.style.top = `${(-v.y * 0.5 + 0.5) * h}px`; }
      }
      return renderer.info.render.calls;
    },
  };
  return api;
}
