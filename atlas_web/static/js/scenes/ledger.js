// Merkle tower, same RFC 6962 split as ledger/merkle.py; path/crack = uniforms vs each node's leaf range.
const split = (n) => { let k = 1; while (k * 2 < n) k *= 2; return k; };
const lvl = (n) => Math.ceil(Math.log2(Math.max(1, n)));
export const TAMPER = { flyS: 0.6, crackS: 0.8, holdS: 2.5, healS: 0.6 };

export function layout(n) {
  const W = 16, nodes = [], top = Math.max(1, lvl(n)), dy = 8 / top;
  const rec = (lo, hi) => { // [lo, hi)
    const size = hi - lo;
    if (size === 1) { const nd = { lo, hi: lo, x: -W / 2 + (lo + 0.5) * W / n, y: 1, h: 0, leaf: true }; nodes.push(nd); return nd; }
    const k = split(size), a = rec(lo, lo + k), b = rec(lo + k, hi);
    const nd = { lo, hi: hi - 1, x: (a.x + b.x) / 2, y: 1 + lvl(size) * dy, h: lvl(size) / top, kids: [a, b] };
    a.up = b.up = nd; nodes.push(nd); return nd;
  };
  const root = n ? rec(0, n) : null;
  return { nodes, root, W };
}

const HD = "attribute vec2 aR; attribute float aH; varying vec2 vR; varying float vH, vF;\n";
const VS = HD + `void main(){ vR=aR; vH=aH; vec4 p=vec4(position,1.); vec3 n=normal;
#ifdef USE_INSTANCING
p=instanceMatrix*p; n=mat3(instanceMatrix)*n;
#endif
vF=1.-abs(normalize(mat3(modelViewMatrix)*n).z); gl_Position=projectionMatrix*modelViewMatrix*p; }`;
const LVS = HD + `void main(){ vR=aR; vH=aH; vF=.5; gl_Position=projectionMatrix*modelViewMatrix*vec4(position,1.); }`;
const FS = (alpha) => `uniform float uTime,uSel,uTam,uCrack,uHeal,uHov; varying vec2 vR; varying float vH, vF;
float onP(float i){ return step(0.,i)*step(vR.x,i+.1)*step(i-.1,vR.y); }
void main(){ float s=onP(uSel), hv=onP(uHov), t=onP(uTam)*step(vH,uCrack+.001)*(1.-uHeal);
vec3 c=mix(vec3(.30,.37,.43),vec3(.36,.88,.90),max(s,hv*.6));
c=mix(c,vec3(1.,.30,.37)*(.85+.15*sin(uTime*30.+vH*40.)),t);
gl_FragColor=vec4(c*(.7+.8*vF), ${alpha}); }`;

export function buildLedger(L, { stageEl, onPick }) {
  return ({ THREE, world, group }) => {
    const n = L.entries.length, { nodes, root, W } = layout(n);
    const U = { uTime: world.uniforms.uTime, uSel: { value: -1 }, uTam: { value: -1 }, uCrack: { value: 0 }, uHeal: { value: 0 }, uHov: { value: -1 } };
    const mat = (a, vs = VS) => new THREE.ShaderMaterial({ uniforms: U, vertexShader: vs, fragmentShader: FS(a), transparent: true, depthWrite: false });
    const leaves = nodes.filter((d) => d.leaf).sort((a, b) => a.lo - b.lo), inner = nodes.filter((d) => !d.leaf);
    const inst = (geo, list, size, alpha) => {
      const m = new THREE.InstancedMesh(geo, mat(alpha), Math.max(1, list.length)), o = new THREE.Object3D();
      geo.setAttribute("aR", new THREE.InstancedBufferAttribute(new Float32Array(list.flatMap((d) => [d.lo, d.hi])), 2));
      geo.setAttribute("aH", new THREE.InstancedBufferAttribute(new Float32Array(list.map((d) => d.h)), 1));
      list.forEach((d, i) => { o.position.set(d.x, d.y, 0); o.scale.setScalar(d === root ? size * 1.8 : size); o.updateMatrix(); m.setMatrixAt(i, o.matrix); });
      m.count = list.length; group.add(m); return m;
    };
    const cell = Math.min(0.5, (W / Math.max(1, n)) * 0.72);
    const leafMesh = inst(new THREE.BoxGeometry(1, 1.4, 1), leaves, cell, ".42+.5*vF");
    inst(new THREE.OctahedronGeometry(0.5), inner, Math.max(0.16, cell * 0.8), ".55+.4*vF");
    const pos = [], R = [], H = [];
    for (const d of inner) for (const k of d.kids) { pos.push(k.x, k.y, 0, d.x, d.y, 0); R.push(k.lo, k.hi, k.lo, k.hi); H.push(k.h, d.h); }
    const eg = new THREE.BufferGeometry();
    eg.setAttribute("position", new THREE.Float32BufferAttribute(pos, 3));
    eg.setAttribute("aR", new THREE.Float32BufferAttribute(R, 2));
    eg.setAttribute("aH", new THREE.Float32BufferAttribute(H, 1));
    group.add(new THREE.LineSegments(eg, mat(".9", LVS)));
    const shard = new THREE.Mesh(new THREE.TetrahedronGeometry(0.3), new THREE.MeshBasicMaterial({ color: 0xff4d5e }));
    shard.visible = false; group.add(shard);
    group.position.y = -0.5;
    let anim = null;
    return {
      pickables: [leafMesh],
      select(i) { U.uSel.value = i ?? -1; },
      tamper(i, reduced) { anim = { i, t0: performance.now() / 1000, reduced }; U.uTam.value = i; U.uHeal.value = 0; U.uCrack.value = reduced ? 1 : 0; },
      update(dt, t) {
        group.scale.x = Math.min(1.3, (world.camera.aspect * 11.5) / W);
        if (!anim) return;
        const e = t - anim.t0, T = TAMPER, fly = anim.reduced ? 0 : T.flyS, lf = leaves[anim.i] || root;
        if (!anim.reduced) {
          shard.visible = e < fly;
          const k = Math.min(1, e / fly), q = 1 - (1 - k) ** 3;
          shard.position.set(lf.x * q, 12 - (12 - lf.y) * q, 4 * (1 - q)); shard.rotation.set(e * 9, e * 7, 0);
          U.uCrack.value = Math.min(1, Math.max(0, (e - fly) / T.crackS));
        }
        const hs = fly + T.holdS;
        U.uHeal.value = anim.reduced ? (e >= hs ? 1 : 0) : Math.min(1, Math.max(0, (e - hs) / T.healS));
        if (e > hs + T.healS) { U.uTam.value = -1; U.uHeal.value = 0; shard.visible = false; anim = null; }
      },
      hover(hit) { const i = hit && hit.object === leafMesh ? hit.instanceId : -1; U.uHov.value = i; stageEl.style.cursor = i >= 0 ? "pointer" : ""; },
      click(hit) { if (hit.object === leafMesh && hit.instanceId != null) onPick(hit.instanceId); },
      dispose() { stageEl.style.cursor = ""; },
    };
  };
}
