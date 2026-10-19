// =====================================================================
//  Skin: echte Meshes mit Skelett über dem prozeduralen Rig
//  Die Posen des Rigs werden pro Frame auf die Knochen übertragen.
//  Modelle: Anzug (Helden/Masken), Panzer-Kämpfer, Frau/Zivil.
// =====================================================================
const SKIN_MODELS = {
  suit: Assets.need('model', 'chars/hero.glb'),
  armor: Assets.need('model', 'chars/soldier.glb'),
  woman: Assets.need('model', 'chars/michelle.glb'),
};
const SUIT_NOR = Assets.need('tex', 'tex/suit/suit_nor_gl.jpg');
const SUIT_ROUGH = Assets.need('tex', 'tex/suit/suit_rough.jpg');
const SKIN_KIND = { lena: 'woman', civilian: 'woman', saya: 'woman', inferna: 'woman', brutus: 'armor', vex: 'armor', malrek: 'armor', cultist: 'armor' };

const SkinLib = {
  gltf: {}, geoCache: new Map(),
  load(done) {
    for (const k in SKIN_MODELS) { const g = Assets.gltf(SKIN_MODELS[k]); if (g) this.gltf[k] = g; }
    Mocap.init();
    if (this.gltf.suit || typeof SKIN_GLB === 'undefined' || !SKIN_GLB) { done(); return; }
    // Ersatz: eingebettetes Anzug-Modell
    let called = false;
    const fin = () => { if (!called) { called = true; done(); } };
    try {
      const bin = atob(SKIN_GLB), buf = new Uint8Array(bin.length);
      for (let i = 0; i < bin.length; i++) buf[i] = bin.charCodeAt(i);
      new GLTFLoader().parse(buf.buffer, '', (g) => { this.gltf.suit = g; fin(); }, (e) => { console.warn('skin', e); fin(); });
    } catch (e) { console.warn('skin', e); fin(); }
    setTimeout(fin, 8000);
  },
  kindFor(cast) { const k = SKIN_KIND[cast] || 'suit'; return this.gltf[k] ? k : 'suit'; },
};

// Rig-Gelenk -> Knochen (in Hierarchie-Reihenfolge)
const SKIN_MAP = [
  ['Hips', 'hips'], ['Spine', 'spine'], ['Spine1', 'chest'], ['Spine2', 'chest'], ['Neck', 'neck'], ['Head', 'head'],
  ['LeftArm', 'lUpper'], ['LeftForeArm', 'lFore'], ['LeftHand', 'lHand'],
  ['RightArm', 'rUpper'], ['RightForeArm', 'rFore'], ['RightHand', 'rHand'],
  ['LeftUpLeg', 'lThigh'], ['LeftLeg', 'lShin'], ['LeftFoot', 'lFoot'],
  ['RightUpLeg', 'rThigh'], ['RightLeg', 'rShin'], ['RightFoot', 'rFoot'],
];
const RIG_PARENT = { spine: 'hips', chest: 'spine', neck: 'chest', head: 'neck', lUpper: 'chest', lFore: 'lUpper', lHand: 'lFore', rUpper: 'chest', rFore: 'rUpper', rHand: 'rFore', lThigh: 'hips', lShin: 'lThigh', lFoot: 'lShin', rThigh: 'hips', rShin: 'rThigh', rFoot: 'rShin' };
const boneKey = (n) => n.replace('mixamorig:', '').replace('mixamorig', '');

// Vertex-Farben nach dominantem Knochen (färbt Anzug/Kleidung pro Kämpfer)
function boneColorGeometry(geo, skeleton, colorOf) {
  const cat = skeleton.bones.map((b) => colorOf(boneKey(b.name)));
  const si = geo.attributes.skinIndex, sw = geo.attributes.skinWeight, n = si.count;
  const col = new Float32Array(n * 3);
  for (let i = 0; i < n; i++) {
    let best = 0, bw = -1;
    const ws = [sw.getX(i), sw.getY(i), sw.getZ(i), sw.getW(i)], is = [si.getX(i), si.getY(i), si.getZ(i), si.getW(i)];
    for (let k = 0; k < 4; k++) if (ws[k] > bw) { bw = ws[k]; best = is[k]; }
    const c = cat[best] || cat[0];
    col[i * 3] = c.r; col[i * 3 + 1] = c.g; col[i * 3 + 2] = c.b;
  }
  const g = geo.clone();
  g.setAttribute('color', new THREE.BufferAttribute(col, 3));
  return g;
}

function skinPalette(kind, L) {
  const P = new THREE.Color(L.primary), S = new THREE.Color(L.secondary), K = new THREE.Color(L.skin), W = new THREE.Color(1, 1, 1);
  if (kind === 'suit') {
    const isHuman = L.eyes === 'human';
    const headC = (L.mask || !isHuman) ? P : K, handC = L.mask ? S : K;
    return (n) => /Head|Neck|Eye/.test(n) ? headC : /Hand/.test(n) ? handC : /Foot|Toe|ForeArm|^(Left|Right)Leg/.test(n) ? S : P;
  }
  // Texturierte Modelle: Textur behalten, Kleidung einfärben (aufgehellt, damit Details sichtbar bleiben)
  const lift = (c, k) => { const h = {}; c.getHSL(h); return new THREE.Color().setHSL(h.h, Math.min(1, h.s * 1.1), clamp(h.l * 1.6 + 0.12, 0.18, 0.9)).lerp(W, 1 - k); };
  const tP = lift(P, 0.75), tS = lift(S, 0.7);
  if (kind === 'woman') return (n) => /Head|Neck|Eye|Hand/.test(n) ? W : /Foot|Toe|^(Left|Right)Leg/.test(n) ? tS : tP;
  return (n) => /Foot|Toe|ForeArm|^(Left|Right)Leg|Hand/.test(n) ? tS : tP;
}

function attachSkin(rig) {
  const kind = SkinLib.kindFor(rig.cast);
  const G = SkinLib.gltf[kind];
  if (!G) return;
  const L = rig.look;
  const model = SkeletonUtils.clone(G.scene);
  const B = {};
  const meshes = [];
  model.traverse((o) => { if (o.isBone) B[boneKey(o.name)] = o; if (o.isSkinnedMesh) meshes.push(o); });
  if (!B.Hips || !meshes.length) return;
  const pal = skinPalette(kind, L);
  for (const o of meshes) {
    o.frustumCulled = false; o.castShadow = true; o.receiveShadow = true;
    const mname = (o.material && o.material.name) || '';
    if (kind === 'suit' && /Joint/i.test(o.name + mname)) { o.material = rig.trimMat; continue; }
    if (kind === 'armor' && /visor/i.test(o.name + mname)) {
      const vm = rig.mat('#05070a', 0.08, 0.6, L.glow, 1.6); o.material = vm; continue;
    }
    const key = kind + '|' + o.name + '|' + rig.cast + L.primary + L.secondary + L.skin;
    let geo = SkinLib.geoCache.get(key);
    if (!geo) { geo = boneColorGeometry(o.geometry, o.skeleton, pal); SkinLib.geoCache.set(key, geo); }
    o.geometry = geo;
    let m;
    if (kind === 'suit' && L.suit && L.suit.phys) { // Anzug-Hook: physikalisches Material (Klarlack/Schimmer/Irisieren)
      m = suitMaterial(rig, L, Assets.tex(SUIT_NOR), Assets.tex(SUIT_ROUGH));
    } else if (kind === 'suit') {
      m = rig.mat('#ffffff', Math.max(0.3, L.rough * 0.9), L.metal);
      const nor = Assets.tex(SUIT_NOR), ro = Assets.tex(SUIT_ROUGH);
      if (nor) { m.normalMap = nor.clone(); m.normalMap.repeat.set(6, 6); m.normalMap.needsUpdate = true; m.normalScale.set(0.9, 0.9); }
      if (ro) { m.roughnessMap = ro.clone(); m.roughnessMap.repeat.set(6, 6); m.roughnessMap.needsUpdate = true; }
    } else {
      m = o.material.clone();
      m.userData.base = { color: m.color.clone(), rough: m.roughness, metal: m.metalness, emissive: m.emissive.clone(), ei: m.emissiveIntensity };
      rig.mats.push(m);
    }
    m.vertexColors = true;
    o.material = m;
  }
  // Größe: Hüfthöhe angleichen
  model.updateMatrixWorld(true);
  const hipW = B.Hips.getWorldPosition(new V3());
  model.scale.multiplyScalar(rig.j.hips.userData.rest.y / Math.max(0.01, hipW.y));
  model.updateMatrixWorld(true);
  // Kalibrierung: Knochen-Orientierung im Root-Raum, Arme nach unten gedreht (Rig-Ruhepose)
  const rootQ = (o) => { const q = new THREE.Quaternion(); const chain = []; for (let x = o; x && x !== model; x = x.parent) chain.push(x); for (let i = chain.length - 1; i >= 0; i--) q.multiply(chain[i].quaternion); return model.quaternion.clone().multiply(q); };
  const calib = {};
  for (const [b] of SKIN_MAP) if (B[b]) calib[b] = rootQ(B[b]);
  const inv = model.matrixWorld.clone().invert();
  const posR = (o) => o.getWorldPosition(new V3()).applyMatrix4(inv);
  const align = (bones, from, to, target) => {
    if (!B[from] || !B[to]) return;
    const dir = posR(B[to]).sub(posR(B[from])).normalize();
    const d = new THREE.Quaternion().setFromUnitVectors(dir, target);
    for (const b of bones) if (calib[b]) calib[b] = d.clone().multiply(calib[b]);
  };
  const down = new V3(0, -1, 0);
  for (const side of ['Left', 'Right']) {
    align([side + 'Arm', side + 'ForeArm', side + 'Hand'], side + 'Arm', side + 'ForeArm', down);
    align([side + 'UpLeg', side + 'Leg', side + 'Foot'], side + 'UpLeg', side + 'Leg', down);
  }
  // Wirbelsäule aufrecht ausrichten
  align(['Spine', 'Spine1', 'Spine2', 'Neck', 'Head'], 'Hips', 'Neck', new V3(0, 1, 0));
  rig.root.add(model);
  rig.skin = { model, B, calib, kind, hipBindY: B.Hips.position.y, hipRestY: rig.j.hips.userData.rest.y, on: true };
  mocapCalibrate(rig);
  // Prozedurale Körperteile ausblenden; bei echten Gesichtern/Helmen auch Augen und Haare
  rig.bodyMeshes = [];
  rig.root.traverse((o) => { if (o.isMesh && (o.userData.body || (kind !== 'suit' && o.userData.face))) rig.bodyMeshes.push(o); });
  setSkin(rig, true);
}

function setSkin(rig, on) {
  const S = rig.skin; if (!S) return;
  S.on = on; S.model.visible = on;
  for (const m of rig.bodyMeshes) m.visible = !on;
  if (!on) for (const [j] of SKIN_SNAP) { const g = rig.j[j]; if (g && !g.userData.detached) g.position.copy(g.userData.rest); }
}

const _sq = new THREE.Quaternion();
function retarget(rig) {
  const S = rig.skin;
  if (!S || !S.on) return;
  const J = rig.j, B = S.B;
  const jq = {};
  const jQ = (n) => { if (jq[n]) return jq[n]; const p = RIG_PARENT[n]; const q = p ? jQ(p).clone().multiply(J[n].quaternion) : J[n].quaternion.clone(); jq[n] = q; return q; };
  const bq = new Map();
  const bQ = (o) => { if (o === S.model) return S.model.quaternion; if (bq.has(o)) return bq.get(o); const q = bQ(o.parent).clone().multiply(o.quaternion); bq.set(o, q); return q; };
  for (const [b, j] of SKIN_MAP) {
    const bone = B[b];
    if (!bone || !J[j]) continue;
    const want = jQ(j).clone().multiply(S.calib[b]);
    bone.quaternion.copy(bQ(bone.parent)).invert().multiply(want);
    bq.set(bone, want);
  }
  B.Hips.position.y = S.hipBindY * (J.hips.position.y / S.hipRestY);
}

// Pro Frame: Mocap-Clip oder Rig-Pose übertragen, Übergänge überblenden,
// Kopf/Hände/Füße des Rigs an das sichtbare Modell heften (Effekte, Zubehör)
const SKIN_SNAP = [['head', 'Head'], ['lHand', 'LeftHand'], ['rHand', 'RightHand'], ['lFoot', 'LeftFoot'], ['rFoot', 'RightFoot']];
const SKIN_FADE = 0.14;
const SKIN_JOINT = [['hips', 'Hips'], ['spine', 'Spine'], ['chest', 'Spine2'], ['neck', 'Neck'], ['head', 'Head'],
  ['lUpper', 'LeftArm'], ['lFore', 'LeftForeArm'], ['lHand', 'LeftHand'], ['rUpper', 'RightArm'], ['rFore', 'RightForeArm'], ['rHand', 'RightHand'],
  ['lThigh', 'LeftUpLeg'], ['lShin', 'LeftLeg'], ['lFoot', 'LeftFoot'], ['rThigh', 'RightUpLeg'], ['rShin', 'RightLeg'], ['rFoot', 'RightFoot']];
function skinStep(rig, dt) {
  const S = rig.skin;
  if (!S || !S.on) return;
  const B = S.B, J = rig.j;
  if (!S.bones) { S.bones = SKIN_MAP.map(([b]) => B[b]).filter(Boolean); for (const b of ['LeftShoulder', 'RightShoulder', 'LeftToeBase', 'RightToeBase']) if (B[b]) S.bones.push(B[b]); S.last = S.bones.map((o) => o.quaternion.clone()); S.lastHip = B.Hips.position.clone(); S.from = S.bones.map((o) => o.quaternion.clone()); S.fromHip = new V3(); }
  if (rig.clip !== S.clip || rig.clipT + 1e-6 < S.clipT) {
    S.clip = rig.clip; S.fade = 0;
    S.bones.forEach((o, i) => S.from[i].copy(S.last[i])); S.fromHip.copy(S.lastHip);
  }
  S.clipT = rig.clipT;
  if (!mocapApply(rig)) retarget(rig);
  if (S.fade < SKIN_FADE) {
    S.fade += dt;
    const k = smooth(Math.min(1, S.fade / SKIN_FADE));
    S.bones.forEach((o, i) => o.quaternion.slerpQuaternions(S.from[i], o.quaternion.clone(), k));
    B.Hips.position.lerpVectors(S.fromHip, B.Hips.position.clone(), k);
  }
  S.bones.forEach((o, i) => S.last[i].copy(o.quaternion)); S.lastHip.copy(B.Hips.position);
  // Rig-Gelenke auf die sichtbaren Knochen drehen (Zubehör wie Polster, Kapuze, Umhang folgt)
  rig.root.updateMatrixWorld(true);
  const rq = rig.root.getWorldQuaternion(new THREE.Quaternion()).invert(), tq = {};
  for (const [j, b] of SKIN_JOINT) {
    const g = J[j], bone = B[b];
    if (!g || !bone || !S.calib[b] || g.userData.detached) continue;
    tq[j] = rq.clone().multiply(bone.getWorldQuaternion(new THREE.Quaternion())).multiply(S.calib[b].clone().invert());
    const pj = RIG_PARENT[j];
    g.quaternion.copy(pj && tq[pj] ? tq[pj].clone().invert().multiply(tq[j]) : tq[j]);
  }
  rig.root.updateMatrixWorld(true);
  for (const [j, b] of SKIN_SNAP) {
    const g = J[j];
    if (g && B[b] && g.parent && !g.userData.detached) g.position.copy(g.parent.worldToLocal(B[b].getWorldPosition(new V3())));
  }
}

// ---- Einhängen ins Rig
{
  const P = Rig.prototype;
  const _build = P.build, _update = P.update, _detach = P.detach, _reset = P.resetBody;
  P.build = function () { _build.call(this); this.skin = null; this.bodyMeshes = []; if (SkinLib.gltf.suit || SkinLib.gltf.armor) { try { attachSkin(this); } catch (e) { console.warn('skin attach', e); this.skin = null; } } };
  P.update = function (dt) { _update.call(this, dt); skinStep(this, dt); };
  P.detach = function (...a) { if (this.skin && this.skin.on) setSkin(this, false); return _detach.apply(this, a); };
  P.resetBody = function () { _reset.call(this); if (this.skin) setSkin(this, true); };
}
