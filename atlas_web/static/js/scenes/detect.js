// Detect layer: one column per scanned file, grouped by service; one marker per finding at line/lines,
// red RSA/ECC/DH/DSA, cyan PQC; files without findings dark; drift services pulse (uTime). 3 draw calls.
const VS = (b) => `attribute float aK; attribute float aD; attribute float aS; attribute vec3 aC;
uniform float uTime; varying vec3 vC; varying vec3 vN; varying float vY;
void main() { ${b} vN = normalize(mat3(modelMatrix * instanceMatrix) * normal);
gl_Position = projectionMatrix * viewMatrix * modelMatrix * instanceMatrix * vec4(position, 1.0); }`;
const COL = VS(`vec3 c = vec3(0.07, 0.085, 0.11);
if (aK == 1.0) c = mix(c, vec3(1.0, 0.3, 0.37), 0.22); if (aK == 2.0) c = mix(c, vec3(0.36, 0.88, 0.9), 0.18);
if (aD > 0.5) c += vec3(0.96, 0.72, 0.29) * (0.18 + 0.18 * sin(uTime * 3.0 + aS * 6.28)); vC = c; vY = position.y;`);
const MARK = VS("vC = aC * (1.1 + 0.25 * sin(uTime * 2.0 + aS * 6.28)); vY = 2.0;");
const FS = `varying vec3 vC; varying vec3 vN; varying float vY;
void main() { float l = 0.55 + 0.45 * max(dot(vN, normalize(vec3(0.4, 0.8, 0.5))), 0.0); gl_FragColor = vec4(vC * mix(1.0, l * (0.7 + 0.5 * vY), step(vY, 1.5)), 1.0); }`;
const RED = [1, 0.3, 0.37], fam = (f) => (f === "PQC" ? [0.36, 0.88, 0.9] : ["RSA", "ECC", "DH", "DSA"].includes(f) ? RED : [0.55, 0.6, 0.66]);

export function buildCity(THREE, group, files, uniforms) {
  const S = 0.55, G = S * 1.5, by = new Map(), xz = [], rects = [], marks = [], m = new THREE.Matrix4();
  files.forEach((f, i) => { const k = f.service || "~"; by.set(k, [...(by.get(k) || []), i]); });
  const maxW = Math.max(6, Math.sqrt(files.length) * S * 3.4);
  let x = 0, z = 0, rowD = 0;
  for (const [, idx] of [...by].sort((a, b) => a[0].localeCompare(b[0]))) {
    const c = Math.ceil(Math.sqrt(idx.length)), w = c * S, d = Math.ceil(idx.length / c) * S;
    if (x > 0 && x + w > maxW) { x = 0; z += rowD + G; rowD = 0; }
    idx.forEach((fi, j) => { xz[fi] = [x + (j % c) * S + S / 2, z + Math.floor(j / c) * S + S / 2]; });
    rects.push([x - 0.1, z - 0.1, w + 0.2, d + 0.2]); x += w + G; rowD = Math.max(rowD, d);
  }
  const W = Math.max(...rects.map((r) => r[0] + r[2])), D = z + rowD, k = Math.min(1.6, 18 / Math.max(W, D, 1));
  const city = new THREE.Group();
  city.scale.setScalar(k); city.position.set((-W / 2) * k, 0, (-D / 2) * k); group.add(city);
  const maxL = Math.max(1, ...files.map((f) => f.lines || 1)), H = files.map((f) => 0.25 + (3 / k) * Math.sqrt((f.lines || 1) / maxL));
  const mesh = (geo, vs, n, at) => {
    const o = new THREE.InstancedMesh(geo, new THREE.ShaderMaterial({ vertexShader: vs, fragmentShader: FS, uniforms }), Math.max(1, n));
    for (const [name, arr, s] of at) o.geometry.setAttribute(name, new THREE.InstancedBufferAttribute(arr, s));
    o.count = n; o.frustumCulled = false; city.add(o); return o;
  };
  const n = files.length, K = new Float32Array(n), Dr = new Float32Array(n), Se = new Float32Array(n);
  files.forEach((f, i) => {
    const fs = (f.findings || []).map((g) => g.family);
    K[i] = fs.some((g) => fam(g) === RED) ? 1 : fs.includes("PQC") ? 2 : 0; Dr[i] = f.drift ? 1 : 0; Se[i] = (i * 0.618) % 1;
    (f.findings || []).forEach((g, j) => marks.push([i, j]));
  });
  const cols = mesh(new THREE.BoxGeometry(S * 0.62, 1, S * 0.62).translate(0, 0.5, 0), COL, n, [["aK", K, 1], ["aD", Dr, 1], ["aS", Se, 1]]);
  files.forEach((f, i) => cols.setMatrixAt(i, m.makeScale(1, H[i], 1).setPosition(xz[i][0], 0, xz[i][1])));
  const q = Math.max(1, marks.length), C = new Float32Array(q * 3), MS = new Float32Array(q);
  marks.forEach(([i, j], p) => { C.set(fam(files[i].findings[j].family), p * 3); MS[p] = (p * 0.37) % 1; });
  const mk = mesh(new THREE.BoxGeometry(S * 0.78, 0.06 / k, S * 0.78), MARK, marks.length, [["aC", C, 3], ["aS", MS, 1]]);
  marks.forEach(([i, j], p) => {
    const f = files[i], t = Math.min(1, Math.max(0, (f.findings[j].line || 0) / Math.max(1, f.lines || 1)));
    mk.setMatrixAt(p, m.makeTranslation(xz[i][0], H[i] * t, xz[i][1]));
  });
  const pts = [];
  for (const [a, b, w, d] of rects) pts.push(a, 0, b, a + w, 0, b, a + w, 0, b, a + w, 0, b + d, a + w, 0, b + d, a, 0, b + d, a, 0, b + d, a, 0, b);
  const g = new THREE.BufferGeometry();
  g.setAttribute("position", new THREE.Float32BufferAttribute(pts, 3));
  city.add(new THREE.LineSegments(g, new THREE.LineBasicMaterial({ color: 0x2a323c })));
  const resolve = (hit) => {
    if (hit && hit.object === mk && marks[hit.instanceId]) { const [i, j] = marks[hit.instanceId]; return { file: files[i], finding: files[i].findings[j] }; }
    return hit && hit.object === cols && files[hit.instanceId] ? { file: files[hit.instanceId], finding: null } : null;
  };
  return { pickables: marks.length ? [mk, cols] : [cols], resolve };
}
