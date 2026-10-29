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
  settings: { pos: [0, 20, 30], at: [0, 0, -6] }, migration: { pos: [-14, 6, 15], at: [0, 0.5, 0] }, void: { pos: [0, 0, 9], at: [0, 0, 0] },
};

export function createWorld(host) {
  const w = {
    host, webgl: false, THREE: null, ready: null, layer: null, pose: "void", stats: { fps: 0, worstFrameMs: 0, drawCalls: 0, dpr: 1 },
    go, mount, focus, frameStage, onPick, uniforms: null, reduced: prefersReducedMotion(), shake() {}, lift() {},
  };
  window.__atlasWorld = w;
  // three.js (~690 KB) is fetched only when a page first opens a 3D stage or mounts a layer, never on 2D-only pages.
  // Without WebGL (or with ?no3d) it is never fetched and `ready` resolves at once, so the 2D fallbacks render.
  let started = false, resolveReady;
  w.ready = new Promise((r) => { resolveReady = r; });
  function start() {
    if (started) return;
    started = true;
    (window.__atlasImport ? window.__atlasImport(THREE_URL) : import(THREE_URL)).then((THREE) => init(w, THREE)).catch((err) => { w.webgl = false; w.error = String(err); return w; }).then(resolveReady);
  }
  if (!hasWebGL() || new URLSearchParams(location.search).has("no3d")) { started = true; resolveReady(w); return w; }
  function go(name, opts) { w._go = [name, opts]; if (w._init) w._go2(name, opts); }
  function mount(name, factory) { w._mount = [name, factory]; if (factory) start(); if (w._init) return w._mount2(name, factory); return null; }
  function focus(v, d) { if (w._init) w._focus2(v, d); }
  function frameStage(el) { w.stage = el || null; if (el) start(); }
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
  const maxDpr = 1.5;  // sharp enough on retina, ~45% fewer pixels than DPR 2
  let dpr = Math.min(devicePixelRatio || 1, maxDpr);
  renderer.setPixelRatio(dpr);
  const scene = new THREE.Scene();
  scene.fog = new THREE.FogExp2(0x05070a, 0.022);
  const camera = new THREE.PerspectiveCamera(38, 1, 0.1, 400);
  const root = new THREE.Group();
  scene.add(root);
  Object.assign(w, { scene, camera, root });
  w.uniforms = { uTime: { value: 0 }, uWeek: { value: 1e6 }, uScenario: { value: 0 }, uPulse: { value: 0 }, uMorph: { value: 1 },
    uIntro: { value: 1 }, uFocus: { value: -1 }, uLift: { value: 0 } };
  // post pass: film grain 3 %, vignette, chromatic aberration <= 0.6 px at the frame edges only (no bloom on text: text is DOM)
  const rt = new THREE.WebGLRenderTarget(4, 4, { samples: 4 });
  const post = new THREE.Mesh(new THREE.PlaneGeometry(2, 2), new THREE.ShaderMaterial({
    uniforms: { tScene: { value: rt.texture }, uRes: { value: new THREE.Vector2(1, 1) }, uTime: w.uniforms.uTime, uCA: { value: 1 } },
    vertexShader: "varying vec2 vUv; void main(){ vUv = uv; gl_Position = vec4(position.xy, 0.0, 1.0); }",
    fragmentShader: `uniform sampler2D tScene; uniform vec2 uRes; uniform float uTime; uniform float uCA; varying vec2 vUv;
      void main(){ vec2 d = vUv - 0.5; float r = dot(d, d); vec2 off = d * r * uCA * 2.4 / uRes;
        vec3 c = vec3(texture2D(tScene, vUv + off).r, texture2D(tScene, vUv).g, texture2D(tScene, vUv - off).b);
        c *= 1.0 - smoothstep(0.18, 0.62, r) * 0.55;
        float g = fract(sin(dot(vUv * uRes + uTime * 61.0, vec2(12.9898, 78.233))) * 43758.5453);
        gl_FragColor = vec4(c + (g - 0.5) * 0.03, 1.0); }`, depthTest: false, depthWrite: false }));
  const postScene = new THREE.Scene(), postCam = new THREE.Camera();
  postScene.add(post);
  let fx = 2; // quality ladder: 2 = post + chromatic, 1 = post only, 0 = direct render
  // drifting dust in the fog: the only idle motion besides breathing (shader-driven, one draw call)
  const dustN = 360, dustPos = new Float32Array(dustN * 3);
  for (let i = 0; i < dustN; i++) dustPos.set([(Math.random() - 0.5) * 40, (Math.random() - 0.5) * 18, (Math.random() - 0.7) * 40], i * 3);
  const dustGeo = new THREE.BufferGeometry(); dustGeo.setAttribute("position", new THREE.BufferAttribute(dustPos, 3));
  scene.add(new THREE.Points(dustGeo, new THREE.ShaderMaterial({ uniforms: { uTime: w.uniforms.uTime }, transparent: true, depthWrite: false,
    vertexShader: "uniform float uTime; varying float vA; void main(){ vec3 p = position; p.y += sin(uTime * 0.07 + position.x) * 0.6; p.x += uTime * 0.05; p.x = mod(p.x + 20.0, 40.0) - 20.0; vec4 mv = modelViewMatrix * vec4(p, 1.0); vA = clamp(1.0 - (-mv.z) / 45.0, 0.0, 1.0); gl_PointSize = 1.6; gl_Position = projectionMatrix * mv; }",
    fragmentShader: "varying float vA; void main(){ gl_FragColor = vec4(0.55, 0.62, 0.7, 0.35 * vA); }" })));

  // ---- camera flights (spline, ease-in-out-cubic with soft settle; reverse arc on back) ----
  const cam = { pos: new THREE.Vector3(...POSES.void.pos), at: new THREE.Vector3(...POSES.void.at) };
  camera.position.copy(cam.pos); camera.lookAt(cam.at);
  let flight = null;
  const orbit = { yaw: 0, pitch: 0, vy: 0, vp: 0, dolly: 1, drag: null }, shake = { t: 0 }, spring = { x: 0, v: 0, target: 0 };
  w.shake = () => { if (!w.reduced) shake.t = 200; };
  w.lift = (on) => { spring.target = on ? 1 : 0; };
  w.resetOrbit = () => Object.assign(orbit, { yaw: 0, pitch: 0, vy: 0, vp: 0, dolly: 1 });
  w._go2 = (name, { direction = "forward" } = {}) => {
    const p = POSES[name] || POSES.void;
    Object.assign(orbit, { yaw: 0, pitch: 0, vy: 0, vp: 0, dolly: 1 });
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
  addEventListener("click", (e) => { if (w.layer && w.layer.click && !orbit.moved) { const hit = pickAt(e); if (hit) w.layer.click(hit, e); } });
  addEventListener("dblclick", (e) => { if (w.layer && w.layer.dblclick) { const hit = pickAt(e); if (hit) w.layer.dblclick(hit, e); } });
  // grab and orbit (inertia + damping); pinch / ⌥-scroll dollies (plain scroll keeps scrolling the page)
  addEventListener("pointerdown", (e) => { if (e.target instanceof Element && e.target.closest("[data-stage]") && w.layer) { orbit.drag = [e.clientX, e.clientY]; orbit.moved = false; } });
  addEventListener("pointermove", (e) => {
    if (!orbit.drag) return;
    const dx = e.clientX - orbit.drag[0], dy = e.clientY - orbit.drag[1];
    if (Math.abs(dx) + Math.abs(dy) > 3) orbit.moved = true;
    orbit.vy = -dx * 0.005; orbit.vp = dy * 0.003; orbit.drag = [e.clientX, e.clientY];
  }, { passive: true });
  addEventListener("pointerup", () => { orbit.drag = null; setTimeout(() => { orbit.moved = false; }, 0); });
  addEventListener("wheel", (e) => {
    if (!(e.ctrlKey || e.altKey) || !(e.target instanceof Element && e.target.closest("[data-stage]"))) return;
    e.preventDefault(); orbit.dolly = Math.min(1.8, Math.max(0.45, orbit.dolly * (1 + e.deltaY * 0.002)));
  }, { passive: false });

  // ---- loop: paused when hidden or when no stage is on screen ----
  let last = performance.now(), frames = 0, acc = 0, worst = 0, running = false;
  const win = { t: 0, n: 0 };
  const debugEl = new URLSearchParams(location.search).has("debug") ? Object.assign(document.createElement("div"), { className: "debug-hud" }) : null;
  if (debugEl) document.body.append(debugEl);
  const UP = new THREE.Vector3(0, 1, 0);
  function frame(now) {
    running = false;
    if (document.hidden) return;
    if (now - last < 1000 / 60 - 2) { loop(); return; }  // cap at 60 fps (high-refresh displays)
    const dt = Math.min(100, now - last); last = now;
    frames++; acc += dt; worst = Math.max(worst, dt);
    if (acc >= 1000) {
      w.stats = { fps: Math.round((frames * 1000) / acc), worstFrameMs: Math.round(worst * 10) / 10, drawCalls: renderer.info.render.calls, dpr };
      if (debugEl) debugEl.textContent = `${w.stats.fps} fps · worst ${w.stats.worstFrameMs} ms · ${w.stats.drawCalls} draw calls · dpr ${dpr}`;
      frames = 0; acc = 0; worst = 0;
    }
    // adaptive quality: if the AVERAGE frame time over a 2 s window exceeds 20 ms, lower the DPR (floor 0.75).
    // (a consecutive-slow-frames test never fires when frames alternate 16.7 / 33 ms, which is the common case)
    win.t += dt; win.n++;
    if (win.t >= 2000) {
      if (win.t / win.n > 20) {  // drop effects in order: chromatic -> post pass -> DPR (floor 0.75)
        if (fx > 0) { fx--; post.material.uniforms.uCA.value = fx === 2 ? 1 : 0; }
        else if (dpr > 0.75) { dpr = Math.max(0.75, dpr - 0.25); renderer.setPixelRatio(dpr); }
      }
      win.t = 0; win.n = 0;
    }
    w.uniforms.uTime.value = now / 1000;
    if (w.uniforms.uMorph.value < 1) w.uniforms.uMorph.value = w.reduced ? 1 : Math.min(1, w.uniforms.uMorph.value + dt / MOTION.flightMaxMs);
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
      camera.position.applyAxisAngle(UP, -parallax[0] * deg);
    }
    orbit.yaw += orbit.vy; orbit.pitch = Math.max(-0.5, Math.min(0.5, orbit.pitch + orbit.vp));
    const damp = orbit.drag ? 0.5 : 0.92; orbit.vy *= damp; orbit.vp *= damp;
    if (orbit.yaw || orbit.pitch || orbit.dolly !== 1) {
      const off = camera.position.clone().sub(cam.at).multiplyScalar(orbit.dolly);
      off.applyAxisAngle(new THREE.Vector3(0, 1, 0), orbit.yaw);
      off.applyAxisAngle(new THREE.Vector3().crossVectors(off, new THREE.Vector3(0, 1, 0)).normalize(), orbit.pitch);
      camera.position.copy(cam.at).add(off);
    }
    if (shake.t > 0) { shake.t -= dt; const k = 0.04 * (shake.t / 200); camera.position.add(new THREE.Vector3((Math.random() - 0.5) * k, (Math.random() - 0.5) * k, 0)); }
    const f = 180 * (spring.target - spring.x) - 22 * spring.v; spring.v += f * dt / 1000; spring.x += spring.v * dt / 1000;  // stiffness 180, damping 22
    w.uniforms.uLift.value = spring.x;
    camera.lookAt(cam.at);
    if (w.layer && w.layer.update && stageVisible()) w.layer.update(dt / 1000, now / 1000);  // no layer work while off-screen
    render();
    loop();
  }
  function stageVisible() {
    const el = w.stage && w.stage.isConnected ? w.stage : null;
    if (!el) return false;
    const r = el.getBoundingClientRect();
    return r.bottom > 0 && r.top < innerHeight && r.width >= 2 && r.height >= 2;
  }
  let sizeW = 0, sizeH = 0;
  function render() {
    const W = innerWidth, H = innerHeight;
    if (W !== sizeW || H !== sizeH) { renderer.setSize(W, H, false); sizeW = W; sizeH = H; }  // resizing every frame reallocates the canvas
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
    if (fx === 0 || w.reduced) { renderer.render(scene, camera); return; }
    const pw = Math.round(r.width * dpr), ph = Math.round(r.height * dpr);
    if (rt.width !== pw || rt.height !== ph) rt.setSize(pw, ph);
    renderer.setRenderTarget(rt); renderer.setScissorTest(false); renderer.clear(); renderer.render(scene, camera); renderer.setRenderTarget(null);
    renderer.setViewport(r.left, y, r.width, r.height); renderer.setScissor(r.left, y, r.width, r.height); renderer.setScissorTest(true);
    post.material.uniforms.uRes.value.set(pw, ph);
    renderer.render(postScene, postCam);
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
