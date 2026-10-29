// The lattice of services from scene.json. Every visual maps to a data field:
//   crystal colour/flicker = status (classical amber-red flicker until its wave, cyan cell once its stand-in
//   passed the gates, ghost = not_verified_in_lab, caution = rolled_back); red beam height = that asset's
//   exposure-years in the selected scenario (off once migrated); conduit pulse = dependency order (week);
//   halo = PQ authentication (ML-DSA) on its stand-in. State lives in shader uniforms (uWeek, uScenario).
// Last lattice shown (workspace + node positions), so switching workspace morphs instead of cutting.
let memory = null;

export const STATE = { classical: 0, hybrid: 1, ghost: 2, rolled_back: 3, rollback_failed: 3, clean: 4 };

const CRYSTAL_VS = `
attribute float aState; attribute float aWeek; attribute vec3 aExp; attribute float aSeed; attribute vec3 aFrom; attribute float aIdx;
uniform float uTime; uniform float uWeek; uniform float uMorph; uniform float uIntro; uniform float uFocus; uniform float uLift;
varying vec3 vColor; varying float vAlpha; varying vec3 vN; varying vec3 vV;
void main() {
  bool migrated = aState == 1.0 && aWeek > 0.0 && uWeek >= aWeek;
  vec3 red = vec3(1.0, 0.30, 0.37), amber = vec3(0.96, 0.62, 0.29), cyan = vec3(0.36, 0.88, 0.90);
  float flick = 0.5 + 0.5 * sin(uTime * 2.3 + aSeed * 17.0);
  vColor = mix(red, amber, 0.35 * flick); vAlpha = 1.0;
  float s = 1.0 + 0.04 * sin(uTime * 3.1 + aSeed * 9.0);
  if (migrated) { vColor = cyan; s = 1.0; }
  else if (aState == 2.0) { vColor = vec3(0.55, 0.6, 0.66); vAlpha = 0.28; s = 1.0; }
  else if (aState == 3.0) { vColor = vec3(0.96, 0.72, 0.29); }
  else if (aState == 4.0) { vColor = vec3(0.35, 0.42, 0.5); vAlpha = 0.7; s = 0.8; }
  float m = smoothstep(0.0, 1.0, uMorph);
  vColor = mix(vec3(0.35, 0.42, 0.5), vColor, m);  // workspace switch: colours tween in from neutral
  s *= smoothstep(aSeed * 0.7, aSeed * 0.7 + 0.3, uIntro);  // title sequence: crystals ignite one by one
  bool focused = uFocus >= 0.0 && abs(aIdx - uFocus) < 0.5;
  if (uFocus >= 0.0 && !focused) vAlpha *= 0.3;            // focus mode: everything else dims to 30 %
  vec4 wp = modelMatrix * instanceMatrix * vec4(position * s, 1.0);
  if (focused) wp.y += 0.35 * uLift;                        // hovered crystal lifts on a spring
  wp.xyz += (mat3(modelMatrix) * (aFrom - instanceMatrix[3].xyz)) * (1.0 - m);  // positions tween from the previous workspace
  vN = normalize(mat3(modelMatrix * instanceMatrix) * normal);
  vV = normalize(cameraPosition - wp.xyz);
  gl_Position = projectionMatrix * viewMatrix * wp;
}`;
const CRYSTAL_FS = `
varying vec3 vColor; varying float vAlpha; varying vec3 vN; varying vec3 vV;
void main() {
  float l = 0.4 + 0.5 * max(dot(vN, normalize(vec3(0.4, 0.8, 0.5))), 0.0);
  float rim = pow(1.0 - max(dot(normalize(vN), vV), 0.0), 3.0);  // fresnel rim light on the facets
  gl_FragColor = vec4(vColor * (l * 1.2 + rim * 0.9), vAlpha);
}`;
const BEAM_VS = `
attribute float aState; attribute float aWeek; attribute vec3 aExp; attribute vec3 aFrom; attribute float aSeed;
uniform float uWeek; uniform float uScenario; uniform float uBeamScale; uniform float uMorph; uniform float uIntro; uniform float uFocus;
varying float vY; varying float vOn;
void main() {
  bool migrated = aState == 1.0 && aWeek > 0.0 && uWeek >= aWeek;
  float e = uScenario < 1.0 ? mix(aExp.x, aExp.y, uScenario) : mix(aExp.y, aExp.z, clamp(uScenario - 1.0, 0.0, 1.0));  // live while dragging the Q-Day dial
  e *= smoothstep(aSeed * 0.7 + 0.15, aSeed * 0.7 + 0.5, uIntro) * (uFocus >= 0.0 ? 0.3 : 1.0);
  vOn = (migrated || aState == 4.0) ? 0.0 : 1.0;
  float m = smoothstep(0.0, 1.0, uMorph);
  vec3 p = position; p.y *= e * uBeamScale * vOn * m; vY = position.y;
  vec4 wp = modelMatrix * instanceMatrix * vec4(p, 1.0);
  wp.xyz += (mat3(modelMatrix) * (aFrom - instanceMatrix[3].xyz)) * (1.0 - m);
  gl_Position = projectionMatrix * viewMatrix * wp;
}`;
const BEAM_FS = `
varying float vY; varying float vOn;
void main() { if (vOn < 0.5) discard; gl_FragColor = vec4(1.0, 0.30, 0.37, 0.55 * (1.0 - vY)); }`;
const EDGE_VS = `
attribute float aOrder; attribute vec2 aEnds; uniform float uWeek; uniform float uTime; uniform float uFocus; uniform float uIntro; varying float vGlow;
void main() {
  float lit = step(aOrder, uWeek);
  vGlow = (0.18 + 0.5 * lit * (0.5 + 0.5 * sin(uTime * 2.0 - aOrder))) * uIntro;
  if (uFocus >= 0.0) vGlow = (abs(aEnds.x - uFocus) < 0.5 || abs(aEnds.y - uFocus) < 0.5) ? 0.95 : vGlow * 0.3;  // focused node's conduits
  gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0);
}`;
const EDGE_FS = `varying float vGlow; void main() { gl_FragColor = vec4(0.36, 0.88, 0.90, vGlow); }`;

export function buildLattice(THREE, group, scene, uniforms, { beamScale = 0.5, grid = true } = {}) {
  const nodes = scene.nodes || [];
  const scen = (scene.scenarios || []).map((s) => s.name);
  const U = { ...uniforms, uBeamScale: { value: beamScale } };
  const byId = {};
  nodes.forEach((n, i) => { byId[n.id] = { index: i, pos: n.pos, node: n }; });
  const n = Math.max(1, nodes.length);
  const attrs = (count) => ({ state: new Float32Array(count), week: new Float32Array(count), exp: new Float32Array(count * 3), seed: new Float32Array(count), from: new Float32Array(count * 3) });
  const a = attrs(n);
  const m = new THREE.Matrix4();
  const crystals = new THREE.InstancedMesh(new THREE.OctahedronGeometry(0.42, 0),
    new THREE.ShaderMaterial({ vertexShader: CRYSTAL_VS, fragmentShader: CRYSTAL_FS, uniforms: U, transparent: true }), n);
  const beams = new THREE.InstancedMesh(new THREE.BoxGeometry(0.05, 1, 0.05).translate(0, 0.5, 0),
    new THREE.ShaderMaterial({ vertexShader: BEAM_VS, fragmentShader: BEAM_FS, uniforms: U, transparent: true, depthWrite: false, blending: THREE.AdditiveBlending }), n);
  nodes.forEach((node, i) => {
    m.makeTranslation(...node.pos);
    crystals.setMatrixAt(i, m);
    m.makeTranslation(node.pos[0], node.pos[1] + 0.4, node.pos[2]);
    beams.setMatrixAt(i, m);
    a.state[i] = STATE[node.state] ?? 0;
    a.week[i] = node.week ?? 0;
    a.seed[i] = (i * 0.618) % 1;
    scen.slice(0, 3).forEach((s, k) => { a.exp[i * 3 + k] = node.exposure_years ? node.exposure_years[s] || 0 : 0; });
    const prev = memory && memory.ws !== scene.workspace && memory.pos.length ? memory.pos[i % memory.pos.length] : node.pos;
    a.from.set(prev, i * 3);
  });
  const switching = !!(memory && memory.ws !== scene.workspace && memory.pos.length);
  if (U.uMorph) U.uMorph.value = switching ? 0 : 1;
  memory = { ws: scene.workspace, pos: nodes.map((x) => x.pos) };
  if (!nodes.length) { crystals.count = 0; beams.count = 0; }
  for (const mesh of [crystals, beams]) {
    mesh.geometry.setAttribute("aState", new THREE.InstancedBufferAttribute(a.state, 1));
    mesh.geometry.setAttribute("aWeek", new THREE.InstancedBufferAttribute(a.week, 1));
    mesh.geometry.setAttribute("aExp", new THREE.InstancedBufferAttribute(a.exp, 3));
    mesh.geometry.setAttribute("aSeed", new THREE.InstancedBufferAttribute(a.seed, 1));
    mesh.geometry.setAttribute("aFrom", new THREE.InstancedBufferAttribute(a.from, 3));
    mesh.geometry.setAttribute("aIdx", new THREE.InstancedBufferAttribute(Float32Array.from({ length: n }, (_, i) => i), 1));
    mesh.frustumCulled = false;
    group.add(mesh);
  }
  // dependency conduits: one line segment per edge; aOrder = the dependent's planned week (pulse in dependency order)
  const edges = (scene.edges || []).filter((e) => byId[e.from] && byId[e.to]);
  if (edges.length) {
    const pos = new Float32Array(edges.length * 6), ord = new Float32Array(edges.length * 2), ends = new Float32Array(edges.length * 4);
    edges.forEach((e, i) => {
      pos.set(byId[e.to].pos, i * 6); pos.set(byId[e.from].pos, i * 6 + 3);
      ord[i * 2] = byId[e.to].node.week ?? 0; ord[i * 2 + 1] = byId[e.from].node.week ?? 0;
      ends.set([byId[e.to].index, byId[e.from].index, byId[e.to].index, byId[e.from].index], i * 4);
    });
    const g = new THREE.BufferGeometry();
    g.setAttribute("position", new THREE.BufferAttribute(pos, 3));
    g.setAttribute("aOrder", new THREE.BufferAttribute(ord, 1));
    g.setAttribute("aEnds", new THREE.BufferAttribute(ends, 2));
    group.add(new THREE.LineSegments(g, new THREE.ShaderMaterial({ vertexShader: EDGE_VS, fragmentShader: EDGE_FS, uniforms: U, transparent: true, depthWrite: false })));
  }
  // PQ-authentication halos (ML-DSA on the stand-in)
  const halos = nodes.filter((x) => x.pq_auth);
  if (halos.length) {
    const ring = new THREE.InstancedMesh(new THREE.TorusGeometry(0.62, 0.015, 6, 48), new THREE.MeshBasicMaterial({ color: 0xe6edf3 }), halos.length);
    halos.forEach((x, i) => { m.makeRotationX(Math.PI / 2).setPosition(...x.pos); ring.setMatrixAt(i, m); });
    group.add(ring);
  }
  if (grid) group.add(latticeGrid(THREE, nodes));
  if (U.uFocus) U.uFocus.value = -1;
  const setScenario = (name) => { U.uScenario.value = Math.max(0, scen.indexOf(name)); };
  return { crystals, beams, byId, uniforms: U, scenarios: scen, setScenario, setScenarioValue: (v) => { U.uScenario.value = v; },
    hooks: (ctx, stageEl) => hooks(ctx, stageEl, nodes, U, crystals, scen) };
}

// The module lattice itself: a cubic grid of faint edges around the services (one draw call).
export function latticeGrid(THREE, nodes, step = 2) {
  const xs = nodes.map((n) => n.pos[0]), ys = nodes.map((n) => n.pos[1]), zs = nodes.map((n) => n.pos[2]);
  const lo = [Math.min(-4, ...xs) - step, Math.min(-2, ...ys) - step, Math.min(-12, ...zs) - step];
  const hi = [Math.max(4, ...xs) + step, Math.max(2, ...ys) + step, Math.max(0, ...zs) + step];
  const pts = [];
  for (let x = lo[0]; x <= hi[0]; x += step) for (let y = lo[1]; y <= hi[1]; y += step) pts.push(x, y, lo[2], x, y, hi[2]);
  for (let x = lo[0]; x <= hi[0]; x += step) for (let z = lo[2]; z <= hi[2]; z += step) pts.push(x, lo[1], z, x, hi[1], z);
  for (let y = lo[1]; y <= hi[1]; y += step) for (let z = lo[2]; z <= hi[2]; z += step) pts.push(lo[0], y, z, hi[0], y, z);
  const g = new THREE.BufferGeometry();
  g.setAttribute("position", new THREE.BufferAttribute(new Float32Array(pts), 3));
  return new THREE.LineSegments(g, new THREE.LineBasicMaterial({ color: 0x5ce1e6, transparent: true, opacity: 0.06, depthWrite: false }));
}

// Shared interaction for every lattice route: hover = focus mode + mono tooltip with provenance, Esc clears,
// double-click flies to the crystal and opens its asset page.
function hooks(ctx, stageEl, nodes, U, crystals, scen) {
  const tip = document.createElement("div");
  tip.className = "stage-tip"; tip.hidden = true;
  if (stageEl) stageEl.append(tip);
  const clear = () => { U.uFocus.value = -1; tip.hidden = true; ctx.world.lift(false); if (stageEl) stageEl.classList.remove("hot"); };
  addEventListener("keydown", (e) => { if (e.key === "Escape") clear(); }, { signal: ctx.signal });
  return {
    pickables: [crystals],
    hover(hit, e) {
      const n = hit && hit.object === crystals ? nodes[hit.instanceId] : null;
      if (!n) { if (U.uFocus.value >= 0) clear(); return; }
      if (U.uFocus.value !== hit.instanceId) { U.uFocus.value = hit.instanceId; ctx.world.lift(true); }
      stageEl.classList.add("hot");
      const s = scen[Math.round(U.uScenario.value)] || scen[0];
      const ey = n.exposure_years ? n.exposure_years[s] : null;
      tip.textContent = [n.id, n.data_class || "not vulnerable", n.week ? `wave ${n.week}` : "no wave",
        ey === null || ey === undefined ? null : `${ey.toFixed(3)} exposure-years (${s})`, n.status.replaceAll("_", " ")].filter(Boolean).join(" · ");
      const r = stageEl.getBoundingClientRect();
      tip.style.left = `${Math.min(e.clientX - r.left + 14, r.width - 320)}px`; tip.style.top = `${e.clientY - r.top + 14}px`; tip.hidden = false;
    },
    dblclick(hit) {
      const n = hit && hit.object === crystals ? nodes[hit.instanceId] : null;
      if (!n || !n.vulnerable) return;
      ctx.world.focus(n.pos, 6);
      setTimeout(() => ctx.navigate(`/w/${ctx.ws}/asset/${encodeURIComponent(n.id)}`), 600);
    },
  };
}
