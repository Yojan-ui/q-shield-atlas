// THE LATTICE engine: ONE persistent WebGL renderer + scene for the whole app. Routes never create renderers;
// they mount a layer (a THREE.Group + per-frame update + dispose) and ask for a camera pose. The canvas is
// fixed full-screen but only draws inside the route's [data-stage] element (scissor), so 3D never sits under
// text. No WebGL / context lost -> world.webgl === false and views fall back to their 2D content.
import { MOTION, breathe, flightDuration, flightProgress, prefersReducedMotion } from "../motion.js";

const THREE_URL = "/vendor/three-0.170.0.module.min.js";

export function hasWebGL() {
  try { const c = document.createElement("canvas"); return !!(c.getContext("webgl2") || c.getContext("webgl")); } catch { return false; }
}

// Camera poses per route (scene units). Layers decide what is visible; poses only frame them.
export const POSES = {
  harvest: { pos: [14, 7, 16], at: [0, 0, -6] }, cell: { pos: [0, 1.5, 6], at: [0, 0, 0] }, pipeline: { pos: [0, 9, 20], at: [0, 0, -6] },
  detect: { pos: [0, 14, 22], at: [0, 2, 0] }, schedule: { pos: [-12, 8, 16], at: [0, 3, -4] }, handshakes: { pos: [0, 3, 14], at: [0, 1, 0] },
  ledger: { pos: [0, 6, 18], at: [0, 5, 0] }, qaoa: { pos: [10, 8, 12], at: [0, 2, 0] }, asset: { pos: [6, 4, 8], at: [0, 0, 0] },
  settings: { pos: [0, 20, 30], at: [0, 0, -6] }, void: { pos: [0, 0, 9], at: [0, 0, 0] },
};

export function createWorld(host) {
  const w = {
    host, webgl: false, THREE: null, ready: null, layer: null, pose: "void", stats: { fps: 0, worstFrameMs: 0, drawCalls: 0, dpr: 1 },
    go, mount, focus, frameStage, onPick, uniforms: null, reduced: prefersReducedMotion(),
  };
  window.__atlasWorld = w;
  if (!hasWebGL() || new URLSearchParams(location.search).has("no3d")) { w.ready = Promise.resolve(w); return w; }
  w.ready = (window.__atlasImport ? window.__atlasImport(THREE_URL) : import(THREE_URL)).then((THREE) => init(w, THREE)).catch((err) => { w.webgl = false; w.error = String(err); return w; });
  function go(name, opts) { w._go = [name, opts]; if (w._init) w._go2(name, opts); }
  function mount(name, factory) { w._mount = [name, factory]; if (w._init) return w._mount2(name, factory); return null; }
  function focus(v, d) { if (w._init) w._focus2(v, d); }
  function frameStage(el) { w.stage = el || null; }
  function onPick(fn) { w.pick = fn; }
  return w;
}

function init(w, THREE) {
  const canvas = document.createElement("canvas");
  let renderer;
  try { renderer = new THREE.WebGLRenderer({ canvas, antialias: true, alpha: false, powerPreference: "high-performance" }); }
  catch { w.webgl = false; return w; }
  w.webgl = true; w.THREE = THREE; w.renderer = renderer;
  w.host.append(canvas);
  renderer.toneMapping = THREE.ACESFilmicToneMapping;
  renderer.outputColorSpace = THREE.SRGBColorSpace;
  renderer.setClearColor(0x05070a, 1);
  renderer.autoClear = false;
  const maxDpr = matchMedia("(max-width: 760px)").matches ? 1.5 : 2;
  let dpr = Math.min(devicePixelRatio || 1, maxDpr);
  renderer.setPixelRatio(dpr);
  const scene = new THREE.Scene();
  scene.fog = new THREE.FogExp2(0x05070a, 0.022);
  const camera = new THREE.PerspectiveCamera(38, 1, 0.1, 400);
  const root = new THREE.Group();
  scene.add(root);
  Object.assign(w, { scene, camera, root });
  w.uniforms = { uTime: { value: 0 }, uWeek: { value: 1e6 }, uScenario: { value: 0 }, uPulse: { value: 0 } };

  // ---- camera flights (spline, ease-in-out-cubic with soft settle; reverse arc on back) ----
  const cam = { pos: new THREE.Vector3(...POSES.void.pos), at: new THREE.Vector3(...POSES.void.at) };
  camera.position.copy(cam.pos); camera.lookAt(cam.at);
  let flight = null;
  w._go2 = (name, { direction = "forward" } = {}) => {
    const p = POSES[name] || POSES.void;
    w.pose = name;
    flyTo(new THREE.Vector3(...p.pos), new THREE.Vector3(...p.at), direction);
  };
  w._focus2 = (v, dist = 7) => {
    const at = new THREE.Vector3(...v);
    flyTo(at.clone().add(new THREE.Vector3(dist * 0.6, dist * 0.45, dist * 0.8)), at, "forward");
  };
  function flyTo(pos, at, direction) {
    if (w.reduced) { cam.pos.copy(pos); cam.at.copy(at); flight = null; fade(); return; }
    const from = cam.pos.clone(), fromAt = cam.at.clone();
    const mid = from.clone().lerp(pos, 0.5);
    const side = new THREE.Vector3().subVectors(pos, from).cross(new THREE.Vector3(0, 1, 0)).normalize().multiplyScalar((direction === "back" ? -1 : 1) * from.distanceTo(pos) * 0.18);
    mid.add(side).add(new THREE.Vector3(0, from.distanceTo(pos) * 0.12, 0));
    flight = { curve: new THREE.CatmullRomCurve3([from, mid, pos]), fromAt, at, t0: performance.now(), ms: flightDuration(from.distanceTo(pos)) };
  }
  function fade() { canvas.animate([{ opacity: 0.2 }, { opacity: 1 }], { duration: MOTION.overlayMs, easing: "ease-out" }); }

  // ---- layers ----
  w._mount2 = (name, factory) => {
    if (w.layer) { try { w.layer.dispose && w.layer.dispose(); } catch (e) { setTimeout(() => { throw e; }, 0); } disposeTree(w.layer.group); root.remove(w.layer.group); }
    w.layer = null;
    w.uniforms.uWeek.value = 1e6; w.uniforms.uScenario.value = 0; // each route starts from the recorded end state
    if (!factory) return null;
    const group = new THREE.Group();
    group.name = name;
    root.add(group);
    const layer = factory({ THREE, world: w, group }) || {};
    w.layer = { name, group, ...layer };
    return w.layer;
  };

  // ---- picking (only for pointer events over a [data-stage]) ----
  const ray = new THREE.Raycaster();
  const ndc = new THREE.Vector2();
  const pickAt = (e) => {
    if (!w.layer || !w.layer.pickables || !w.stage) return null;
    const t = e.target instanceof Element ? e.target.closest("[data-stage]") : null;
    if (!t) return null;
    const r = w.stage.getBoundingClientRect();
    ndc.set(((e.clientX - r.left) / r.width) * 2 - 1, -((e.clientY - r.top) / r.height) * 2 + 1);
    ray.setFromCamera(ndc, camera);
    const hit = ray.intersectObjects(w.layer.pickables, false)[0];
    return hit ? { object: hit.object, instanceId: hit.instanceId, point: hit.point } : null;
  };
  let parallax = [0, 0];
  addEventListener("pointermove", (e) => {
    parallax = [(e.clientX / innerWidth - 0.5) * 2, (e.clientY / innerHeight - 0.5) * 2];
    if (w.layer && w.layer.hover) w.layer.hover(pickAt(e), e);
  }, { passive: true });
  addEventListener("click", (e) => { if (w.layer && w.layer.click) { const hit = pickAt(e); if (hit) w.layer.click(hit, e); } });

  // ---- loop: paused when hidden or when no stage is on screen ----
  let last = performance.now(), frames = 0, acc = 0, worst = 0, slowFor = 0, running = false;
  const debugEl = new URLSearchParams(location.search).has("debug") ? Object.assign(document.createElement("div"), { className: "debug-hud" }) : null;
  if (debugEl) document.body.append(debugEl);
  function frame(now) {
    running = false;
    if (document.hidden) return;
    const dt = Math.min(100, now - last); last = now;
    frames++; acc += dt; worst = Math.max(worst, dt);
    if (acc >= 1000) {
      w.stats = { fps: Math.round((frames * 1000) / acc), worstFrameMs: Math.round(worst * 10) / 10, drawCalls: renderer.info.render.calls, dpr };
      if (debugEl) debugEl.textContent = `${w.stats.fps} fps · worst ${w.stats.worstFrameMs} ms · ${w.stats.drawCalls} draw calls · dpr ${dpr}`;
      frames = 0; acc = 0; worst = 0;
    }
    // adaptive quality: sustained > 20 ms frames -> lower DPR
    slowFor = dt > 20 ? slowFor + dt : 0;
    if (slowFor > 2000 && dpr > 1) { dpr = Math.max(1, dpr - 0.5); renderer.setPixelRatio(dpr); slowFor = 0; }
    w.uniforms.uTime.value = now / 1000;
    if (flight) {
      const k = Math.min(1, (now - flight.t0) / flight.ms);
      const e = flightProgress(k);
      cam.pos.copy(flight.curve.getPoint(Math.min(1, e)));
      if (e > 1) cam.pos.addScaledVector(flight.curve.getTangent(1), (e - 1) * flight.curve.getLength()); // soft overshoot, settles back
      cam.at.lerpVectors(flight.fromAt, flight.at, Math.min(1, e));
      if (k >= 1) flight = null;
    }
    const s = w.reduced ? 1 : breathe(now);
    root.scale.setScalar(s);
    camera.position.copy(cam.pos);
    if (!w.reduced) {
      const deg = (MOTION.parallaxMaxDeg * Math.PI) / 180;
      camera.position.applyAxisAngle(new THREE.Vector3(0, 1, 0), -parallax[0] * deg);
    }
    camera.lookAt(cam.at);
    if (w.layer && w.layer.update) w.layer.update(dt / 1000, now / 1000);
    render();
    loop();
  }
  function render() {
    const W = innerWidth, H = innerHeight;
    renderer.setSize(W, H, false);
    renderer.setScissorTest(false);
    renderer.clear();
    const el = w.stage && w.stage.isConnected ? w.stage : null;
    if (!el || !w.layer) return;
    const r = el.getBoundingClientRect();
    if (r.bottom <= 0 || r.top >= H || r.width < 2 || r.height < 2) return;
    const y = H - r.bottom;
    renderer.setViewport(r.left, y, r.width, r.height);
    renderer.setScissor(r.left, y, r.width, r.height);
    renderer.setScissorTest(true);
    camera.aspect = r.width / r.height;
    camera.updateProjectionMatrix();
    renderer.render(scene, camera);
  }
  function loop() { if (!running) { running = true; requestAnimationFrame(frame); } }
  document.addEventListener("visibilitychange", () => { if (!document.hidden) { last = performance.now(); loop(); } });
  canvas.addEventListener("webglcontextlost", (e) => {
    e.preventDefault(); w.webgl = false; document.body.classList.add("no-webgl");
    window.dispatchEvent(new CustomEvent("atlas:webgl-lost"));
  });
  w._init = true;
  loop();
  if (w._go) w._go2(...w._go);
  if (w._mount) w._mount2(...w._mount);
  return w;
}

export function disposeTree(obj) {
  obj.traverse((o) => {
    if (o.geometry) o.geometry.dispose();
    if (o.material) (Array.isArray(o.material) ? o.material : [o.material]).forEach((m) => m.dispose());
  });
}
