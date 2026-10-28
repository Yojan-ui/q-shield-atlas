// 3D view (opt-in): the exposure tower, rendered with the vendored three.js build (no CDN).
// One floor per week; floor height = remaining exposure-years in that week (optimised plan).
// Red HNDL beams mark services still on classical key exchange at the selected week.
import * as THREE from "./vendor/three-0.170.0.module.min.js";
import { beamOn } from "./data.js";
import { sourceText } from "./render2d.js";

export function hasWebGL() {
  try {
    const c = document.createElement("canvas");
    return !!(window.WebGLRenderingContext && (c.getContext("webgl2") || c.getContext("webgl")));
  } catch {
    return false;
  }
}

export function createTower(host, tower, ui) {
  const renderer = new THREE.WebGLRenderer({ antialias: true, preserveDrawingBuffer: true });
  renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
  host.replaceChildren(renderer.domElement);
  const scene = new THREE.Scene();
  const dark = window.matchMedia && window.matchMedia("(prefers-color-scheme: dark)").matches;
  scene.background = new THREE.Color(dark ? 0x1d2024 : 0xffffff);
  const camera = new THREE.PerspectiveCamera(40, 1, 0.1, 200);
  scene.add(new THREE.AmbientLight(0xffffff, 0.7));
  const sun = new THREE.DirectionalLight(0xffffff, 1.1);
  sun.position.set(6, 12, 8);
  scene.add(sun);
  const ground = new THREE.Mesh(new THREE.CircleGeometry(9, 48), new THREE.MeshLambertMaterial({ color: dark ? 0x2a2e33 : 0xeeeeea }));
  ground.rotation.x = -Math.PI / 2;
  scene.add(ground);

  const floorsGroup = new THREE.Group();
  const beamsGroup = new THREE.Group();
  scene.add(floorsGroup, beamsGroup);
  const TOWER_H = 8; // scene units for the summed floor heights (layout only, not data)

  function build(scenario, week) {
    floorsGroup.clear();
    beamsGroup.clear();
    const floors = tower.floors[scenario];
    const total = floors.reduce((a, f) => a + f.cell.value, 0) || 1;
    let yBase = 0;
    for (const f of floors) {
      const h = Math.max((TOWER_H * f.cell.value) / total, 0.02);
      const done = f.week < week, current = f.week === week;
      const mat = new THREE.MeshLambertMaterial({
        color: current ? 0xf59e0b : done ? 0x9ca3af : 0xdc2626,
        transparent: done, opacity: done ? 0.35 : 1,
      });
      const slab = new THREE.Mesh(new THREE.BoxGeometry(2.2, h * 0.94, 2.2), mat);
      slab.position.y = yBase + h / 2;
      floorsGroup.add(slab);
      yBase += h;
    }
    tower.beams.forEach((b, i) => {
      const a = (i / tower.beams.length) * Math.PI * 2;
      const pos = new THREE.Vector3(Math.cos(a) * 4.2, 0, Math.sin(a) * 4.2);
      const post = new THREE.Mesh(new THREE.BoxGeometry(0.5, 0.5, 0.5), new THREE.MeshLambertMaterial({ color: 0x475569 }));
      post.position.copy(pos).setY(0.25);
      beamsGroup.add(post);
      if (beamOn(b, week)) {
        const beam = new THREE.Mesh(new THREE.CylinderGeometry(0.07, 0.07, TOWER_H + 3, 12),
          new THREE.MeshBasicMaterial({ color: 0xff2020, transparent: true, opacity: 0.85 }));
        beam.position.copy(pos).setY((TOWER_H + 3) / 2);
        beamsGroup.add(beam);
      }
    });
    ui(scenario, week);
  }

  let angle = 0.6;
  function frame() {
    const w = host.clientWidth || 600, h = host.clientHeight || 520;
    renderer.setSize(w, h, false);
    camera.aspect = w / h;
    camera.updateProjectionMatrix();
    camera.position.set(Math.cos(angle) * 15, 9, Math.sin(angle) * 15);
    camera.lookAt(0, 3.5, 0);
    renderer.render(scene, camera);
  }
  let dragging = false, lastX = 0;
  renderer.domElement.addEventListener("pointerdown", (e) => { dragging = true; lastX = e.clientX; });
  window.addEventListener("pointerup", () => { dragging = false; });
  window.addEventListener("pointermove", (e) => { if (dragging) { angle += (e.clientX - lastX) * 0.01; lastX = e.clientX; frame(); } });
  window.addEventListener("resize", frame);
  return { build: (scenario, week) => { build(scenario, week); frame(); } };
}

export function beamListItems(tower, week) {
  return tower.beams.map((b) => {
    const li = document.createElement("li");
    const on = beamOn(b, week);
    li.className = on ? "on" : "off";
    li.textContent = `${on ? "● beam ON" : "○ off"}  ${b.label}`;
    li.setAttribute("data-src", `${b.reason}\n${sourceText(b.source)}`);
    li.tabIndex = 0;
    return li;
  });
}
