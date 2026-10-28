// QAOA cloud, 1 particle = 1/n of shots: feasible-shell share = feasible_fraction, core = p_optimal_assets.
// Positions are layout. The shader morphs between p levels via uFrom/uTo/uMix.
const VS = `attribute vec3 aDir,aCls; attribute float aSeed,aCloud;
uniform float uFrom,uTo,uMix,uTime,uPx; varying vec3 vC; varying float vA;
float at(float i){return i<.5?aCls.x:(i<1.5?aCls.y:aCls.z);}
float rad(float c){float s=fract(aSeed*7.31);return c>1.5?.1+.32*s:(c>.5?1.1+.45*s:2.2+1.5*s);}
vec3 col(float c){return c>1.5?vec3(.29,.87,.5):(c>.5?vec3(.36,.88,.9):vec3(.42,.47,.53));}
void main(){bool R=aCloud>.5;float a=R?aCls.x:at(uFrom),b=R?aCls.x:at(uTo),m=R?1.:smoothstep(0.,1.,uMix);
vec3 p=aDir*mix(rad(a),rad(b),m)*(1.+.012*sin(uTime*1.3+aSeed*40.));if(R)p.y*=.28;
vC=mix(col(a),col(b),m);vA=mix(a>.5?.95:.32,b>.5?.95:.32,m);
vec4 mv=modelViewMatrix*vec4((R?vec3(2.3,2.,-1.9):vec3(-2.3,2.,1.9))+p,1.);
gl_PointSize=uPx*(b>1.5?6.:b>.5?4.:3.)*(10./-mv.z);gl_Position=projectionMatrix*mv;}`;
const FS = `varying vec3 vC; varying float vA;
void main(){vec2 d=gl_PointCoord-.5;float q=dot(d,d);if(q>.25)discard;gl_FragColor=vec4(vC,vA*(1.-q*3.));}`;

// levels: [{feasible, opt}] for p = 1..3 (fractions); random: {feasible, opt}; n particles per cloud.
export function buildQaoaCloud(THREE, group, { levels, random, n, level = 0 }, world) {
  let s = 1007;
  const rand = () => (s = (s * 16807) % 2147483647) / 2147483647, N = n * 2;
  const dir = new Float32Array(N * 3), c = new Float32Array(N * 3), seed = new Float32Array(N), cloud = new Float32Array(N);
  const cnt = (f) => [Math.round(f.opt * n), Math.round(f.feasible * n)], cls = (k, [o, f]) => (k < o ? 2 : k < f ? 1 : 0);
  const L = [0, 1, 2].map((i) => cnt(levels[Math.min(i, levels.length - 1)])), R = cnt(random);
  for (let i = 0; i < N; i++) {
    const u = rand() * 2 - 1, th = rand() * Math.PI * 2, r = Math.sqrt(1 - u * u), k = i % n;
    dir.set([r * Math.cos(th), u, r * Math.sin(th)], i * 3);
    c.set(i >= n ? [cls(k, R), 0, 0] : L.map((x) => cls(k, x)), i * 3);
    seed[i] = rand(); cloud[i] = i >= n ? 1 : 0;
  }
  const g = new THREE.BufferGeometry(), A = (a, k) => new THREE.BufferAttribute(a, k);
  g.setAttribute("position", A(new Float32Array(N * 3), 3));
  g.setAttribute("aDir", A(dir, 3)); g.setAttribute("aCls", A(c, 3)); g.setAttribute("aSeed", A(seed, 1)); g.setAttribute("aCloud", A(cloud, 1));
  g.boundingSphere = new THREE.Sphere(new THREE.Vector3(0, 2, 0), 8);
  const U = { uTime: world.uniforms.uTime, uFrom: { value: level }, uTo: { value: level }, uMix: { value: 1 }, uPx: { value: world.renderer ? world.renderer.getPixelRatio() : 1 } };
  group.add(new THREE.Points(g, new THREE.ShaderMaterial({ vertexShader: VS, fragmentShader: FS, uniforms: U, transparent: true, depthWrite: false, blending: THREE.AdditiveBlending })));
  const pts = []; // static hairline guides at the feasible-shell and core boundaries
  for (const [cx, cz] of [[-2.3, 1.9], [2.3, -1.9]]) for (const r of [1.1, 0.45]) for (let j = 0; j < 128; j++) {
    const a = (Math.ceil(j / 2) / 64) * Math.PI * 2; pts.push(cx + r * Math.cos(a), 2, cz + r * Math.sin(a));
  }
  const lg = new THREE.BufferGeometry();
  lg.setAttribute("position", new THREE.Float32BufferAttribute(pts, 3));
  group.add(new THREE.LineSegments(lg, new THREE.LineBasicMaterial({ color: 0xffffff, transparent: true, opacity: 0.12 })));
  return {
    setLevel(i) {
      i = Math.max(0, Math.min(2, i));
      if (i === U.uTo.value && U.uMix.value >= 1) return;
      U.uFrom.value = U.uMix.value >= 0.5 ? U.uTo.value : U.uFrom.value; U.uTo.value = i;
      U.uMix.value = world.reduced ? 1 : 0;
    },
    update(dt) { if (U.uMix.value < 1) U.uMix.value = Math.min(1, U.uMix.value + dt / 0.9); },
  };
}
