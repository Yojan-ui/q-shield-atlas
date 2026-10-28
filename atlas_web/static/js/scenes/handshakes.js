// Row per session: classical = red strand + rising HNDL particles; hybrid = cyan braid; ring = pq_auth; wall = downgrade.
const L = 5, WALL = L - 0.9, NODE = L + 0.45, X0 = -L - 0.5, X1 = L + 1.2, ROW = 1.9, STOP = (WALL - X0) / (X1 - X0);
const G = `const float L=${L.toFixed(1)},S=${STOP.toFixed(4)};uniform float uTime,uMotion;`;
const CY = `vec3 R=vec3(1.,.3,.37),A=vec3(.96,.62,.29),C=vec3(.36,.88,.9);`;
const STRAND_VS = G + `attribute float aU,aType,aY,aSeed;varying vec3 vC;varying float vA;
void main(){float t=uTime*uMotion,u=fract(aU+t*.04),s=1.;${CY}vec3 p=vec3(mix(-L,L,u),aY,0.);vA=.9;
if(aType<.5){p.y+=.04*sin(u*40.+t*3.+aSeed*6.);p.z=.04*cos(u*31.+t*2.);vC=mix(R,A,.2+.2*sin(t*2.3+aSeed*17.));}
else if(aType<2.5){float ph=u*18.85-t*1.2+(aType>1.5?3.1416:0.),r=mix(.42,.15,smoothstep(0.,.55,u));p.y+=r*sin(ph);p.z=r*cos(ph);
vC=aType>1.5?mix(vec3(.75,.95,1.),C,u):mix(A,C,smoothstep(.15,.6,u));}
else{float h=fract(aSeed+t*.25);p=vec3(mix(-L,L*.85,aU),aY+.12+h*1.3,0.);vC=R;vA=.32*(1.-h);s=1.3;}
vec4 mv=modelViewMatrix*vec4(p,1.);gl_PointSize=s*80./-mv.z;gl_Position=projectionMatrix*mv;}`;
const DOT_FS = "varying vec3 vC;varying float vA;void main(){gl_FragColor=vec4(vC,vA*smoothstep(.5,.1,length(gl_PointCoord-.5)));}";
const PROBE_VS = G + `attribute float aY,aStop;varying vec3 vC;varying float vA;
void main(){float p=fract(uTime/3.2+aY*.153);vA=1.;if(uMotion<.5)p=aStop>.5?S-.01:.92;
else if(aStop>.5&&p>S){vA=1.-smoothstep(0.,.12,p-S);p=S;}vC=vec3(.96,.62,.29);
vec4 mv=modelViewMatrix*vec4(mix(${X0.toFixed(2)},${X1.toFixed(2)},p),aY,0.,1.);gl_PointSize=260./-mv.z;gl_Position=projectionMatrix*mv;}`;
const WALL_VS = G + `varying vec2 vUv;varying float vF;
void main(){float p=fract(uTime/3.2+instanceMatrix[3].y*.153);vF=uMotion>.5&&p>S?exp(-(p-S)*14.):0.;vUv=uv;
gl_Position=projectionMatrix*viewMatrix*modelMatrix*instanceMatrix*vec4(position,1.);}`;
const WALL_FS = `varying vec2 vUv;varying float vF;void main(){vec2 e=min(vUv,1.-vUv);
gl_FragColor=vec4(.36,.88,.9,.07+.35*(1.-smoothstep(0.,.03,min(e.x,e.y)))+.08*step(.92,fract(vUv.y*9.))+.45*vF);}`;

export function rowsOf(r) {
  const g = r.gates || {}, find = (list, id) => (list || []).find((x) => x.service_id === id) || null;
  return ((r.handshake_evidence || {}).sessions || []).map((s) => ({ s, classical: s.kex_class === "classical",
    kex: find(g.pq_handshake, s.service_id), auth: find(g.pq_auth, s.service_id), down: find(g.downgrade, s.service_id) }))
    .sort((a, b) => b.classical - a.classical);
}

export function buildHandshakes({ THREE, world, group }, rows, labels) {
  const U = { uTime: world.uniforms.uTime, uMotion: { value: world.reduced ? 0 : 1 } };
  const n = rows.length, yOf = (i) => ((n - 1) / 2) * ROW - i * ROW;
  const add = (o) => { o.frustumCulled = false; group.add(o); return o; };
  const shader = (vs, fs, extra = {}) => new THREE.ShaderMaterial({ vertexShader: vs, fragmentShader: fs, uniforms: U, transparent: true,
    depthWrite: false, blending: THREE.AdditiveBlending, ...extra });
  const pts = (attrs, vs) => {
    const geo = new THREE.BufferGeometry(), count = Object.values(attrs)[0].length;
    geo.setAttribute("position", new THREE.BufferAttribute(new Float32Array(count * 3), 3));
    for (const [k, v] of Object.entries(attrs)) geo.setAttribute(k, new THREE.BufferAttribute(new Float32Array(v), 1));
    if (count) add(new THREE.Points(geo, shader(vs, DOT_FS)));
  };
  const A = { aU: [], aType: [], aY: [], aSeed: [] };
  const push = (u, type, y, sd) => { A.aU.push(u); A.aType.push(type); A.aY.push(y); A.aSeed.push(sd); };
  rows.forEach((row, i) => {
    for (let k = 0; k < 170; k++) {
      const u = k / 170, sd = (k * 0.618 + i * 0.37) % 1;
      if (row.classical) { push(u, 0, yOf(i), sd); if (k % 3 === 0) push((k * 0.7548) % 1, 3, yOf(i), sd); }
      else { push(u, 1, yOf(i), sd); push(u, 2, yOf(i), sd); }
    }
  });
  pts(A, STRAND_VS);
  const m = new THREE.Matrix4(), c = new THREE.Color(), idx = rows.map((row, i) => ({ row, i }));
  const inst = (geo, mat, list, place) => {
    if (!list.length) return null;
    const mesh = new THREE.InstancedMesh(geo, mat, list.length);
    list.forEach((x, k) => { place(x); mesh.setMatrixAt(k, m); });
    return add(mesh);
  };
  const turn = (x, i) => m.makeRotationY(Math.PI / 2).setPosition(x, yOf(i), 0);
  const nodes = inst(new THREE.OctahedronGeometry(0.28, 0), new THREE.MeshBasicMaterial(), idx, ({ i }) => m.makeTranslation(NODE, yOf(i), 0));
  if (nodes) idx.forEach(({ row }, k) => nodes.setColorAt(k, c.set(row.classical ? 0xff4d5e : 0x5ce1e6)));
  inst(new THREE.TorusGeometry(0.5, 0.012, 6, 48), new THREE.MeshBasicMaterial({ color: 0xe6edf3 }),
    idx.filter((x) => x.row.auth && x.row.auth.result === "PASS"), ({ i }) => turn(NODE, i));
  inst(new THREE.PlaneGeometry(1.1, 1.4), shader(WALL_VS, WALL_FS, { side: THREE.DoubleSide }),
    idx.filter((x) => x.row.down && x.row.down.result === "PASS"), ({ i }) => turn(WALL, i));
  const probes = idx.filter((x) => x.row.down);
  pts({ aY: probes.map(({ i }) => yOf(i)), aStop: probes.map((x) => +(x.row.down.result === "PASS")) }, PROBE_VS);

  // labels track each strand's left end: beside it when wide, above it when narrow
  const v = new THREE.Vector3(), last = [];
  return {
    pickables: [],
    update() {
      const cam = world.camera, el = labels.parentElement;
      if (!cam || !el) return;
      const fit = Math.tan((cam.fov * Math.PI) / 360) * 14 * cam.aspect * 0.92, side = fit > 11;
      const s = side ? Math.min(1.25, fit / 11) : Math.min(1, fit / (X1 + 0.2));
      group.scale.set(s, side ? s : Math.min(1, s * 1.7), s);
      group.position.set(side ? 2.4 * s : 0, side ? 0.9 : 1.5, 0);
      labels.classList.toggle("side", side);
      group.updateMatrixWorld();
      const W = el.clientWidth, H = el.clientHeight;
      labels.childNodes.forEach((lab, i) => {
        v.set(side ? -L - 0.4 : -L, yOf(i) + (side ? 0 : 0.5), 0); group.localToWorld(v).project(cam);
        const x = Math.max(8, Math.round(((v.x + 1) / 2) * W)), y = Math.round(((1 - v.y) / 2) * H), key = `${x},${y},${side}`;
        if (last[i] !== key) { last[i] = key; lab.style.transform = `translate(${x}px, ${y}px) translate(${side ? "-100%, -50%" : "0, -100%"})`; }
      });
    },
  };
}
