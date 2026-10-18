// =====================================================================
//  Skin: echtes Mesh mit Skelett über dem prozeduralen Rig
//  Die Posen des Rigs werden pro Frame auf die Knochen übertragen.
// =====================================================================
const SkinLib = {
  gltf: null, geoCache: new Map(),
  load(done) {
    let called = false;
    const fin = () => { if (!called) { called = true; done(); } };
    try {
      if (typeof SKIN_GLB === 'undefined' || !SKIN_GLB) { fin(); return; }
      const bin = atob(SKIN_GLB), buf = new Uint8Array(bin.length);
      for (let i = 0; i < bin.length; i++) buf[i] = bin.charCodeAt(i);
      new GLTFLoader().parse(buf.buffer, '', (g) => { this.gltf = g; fin(); }, (e) => { console.warn('skin', e); fin(); });
    } catch (e) { console.warn('skin', e); fin(); }
    setTimeout(fin, 8000);
  },
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

function skinColorGeometry(geo, skeleton, L) {
  const isHuman = L.eyes === 'human';
  const P = new THREE.Color(L.primary), S = new THREE.Color(L.secondary), K = new THREE.Color(L.skin);
  const headC = (L.mask || !isHuman) ? P : K, handC = L.mask ? S : K;
  const cat = skeleton.bones.map((b) => {
    const n = boneKey(b.name);
    if (/Head|Neck|Eye/.test(n)) return headC;
    if (/Hand/.test(n)) return handC;
    if (/Foot|Toe/.test(n)) return S;
    if (/ForeArm/.test(n)) return S;
    if (/^(Left|Right)Leg/.test(n)) return S;
    return P;
  });
  const si = geo.attributes.skinIndex, sw = geo.attributes.skinWeight, n = si.count;
  const col = new Float32Array(n * 3);
  for (let i = 0; i < n; i++) {
    let best = 0, bw = -1;
    for (let k = 0; k < 4; k++) { const w = sw.getComponent(i, k); if (w > bw) { bw = w; best = si.getComponent(i, k); } }
    const c = cat[best] || P;
    col[i * 3] = c.r; col[i * 3 + 1] = c.g; col[i * 3 + 2] = c.b;
  }
  const g = geo.clone();
  g.setAttribute('color', new THREE.BufferAttribute(col, 3));
  return g;
}

function attachSkin(rig) {
  const G = SkinLib.gltf;
  if (!G) return;
  const L = rig.look, s = rig.scale;
  const model = SkeletonUtils.clone(G.scene);
  const B = {};
  let surface = null;
  model.traverse((o) => {
    if (o.isBone) B[boneKey(o.name)] = o;
    if (o.isSkinnedMesh) {
      o.frustumCulled = false; o.castShadow = true; o.receiveShadow = true;
      if (/Joint/i.test(o.name) || /Joint/i.test(o.material.name)) o.material = rig.trimMat;
      else surface = o;
    }
  });
  if (!B.Hips || !surface) return;
  const key = rig.cast + '|' + L.primary + L.secondary + L.skin;
  let geo = SkinLib.geoCache.get(key);
  if (!geo) { geo = skinColorGeometry(surface.geometry, surface.skeleton, L); SkinLib.geoCache.set(key, geo); }
  surface.geometry = geo;
  const bodyM = rig.mat('#ffffff', Math.max(0.28, L.rough * 0.8), L.metal);
  bodyM.vertexColors = true;
  surface.material = bodyM;
  // Größe: Hüfthöhe angleichen
  model.updateMatrixWorld(true);
  const hipW = B.Hips.getWorldPosition(new V3());
  const k = (rig.j.hips.userData.rest.y) / Math.max(0.01, hipW.y);
  model.scale.setScalar(k);
  model.updateMatrixWorld(true);
  // Kalibrierung: Knochen-Orientierung im Root-Raum, Arme nach unten gedreht (Rig-Ruhepose)
  const rootQ = (o) => { const q = new THREE.Quaternion(); const chain = []; for (let x = o; x && x !== model; x = x.parent) chain.push(x); for (let i = chain.length - 1; i >= 0; i--) q.multiply(chain[i].quaternion); return model.quaternion.clone().multiply(q); };
  const calib = {};
  for (const [b] of SKIN_MAP) if (B[b]) calib[b] = rootQ(B[b]);
  const inv = model.matrixWorld.clone().invert();
  const posR = (o) => o.getWorldPosition(new V3()).applyMatrix4(inv);
  for (const side of ['Left', 'Right']) {
    const arm = B[side + 'Arm'], fore = B[side + 'ForeArm'];
    if (!arm || !fore) continue;
    const dir = posR(fore).sub(posR(arm)).normalize();
    const d = new THREE.Quaternion().setFromUnitVectors(dir, new V3(0, -1, 0));
    for (const b of [side + 'Arm', side + 'ForeArm', side + 'Hand']) if (calib[b]) calib[b] = d.clone().multiply(calib[b]);
  }
  rig.root.add(model);
  rig.skin = { model, B, calib, hipBindY: B.Hips.position.y, hipRestY: rig.j.hips.userData.rest.y, on: true, tmp: new THREE.Quaternion() };
  // Prozedurale Körperteile ausblenden, Zubehör bleibt
  rig.bodyMeshes = [];
  rig.root.traverse((o) => { if (o.isMesh && o.userData.body) rig.bodyMeshes.push(o); });
  setSkin(rig, true);
}

function setSkin(rig, on) {
  const S = rig.skin; if (!S) return;
  S.on = on; S.model.visible = on;
  for (const m of rig.bodyMeshes) m.visible = !on;
  if (!on && rig.j.head) rig.j.head.position.copy(rig.j.head.userData.rest);
}

function retarget(rig) {
  const S = rig.skin;
  if (!S || !S.on) return;
  const J = rig.j, B = S.B;
  // Rig-Orientierungen im Root-Raum
  const jq = {};
  const jQ = (n) => { if (jq[n]) return jq[n]; const p = RIG_PARENT[n]; const q = p ? jQ(p).clone().multiply(J[n].quaternion) : J[n].quaternion.clone(); jq[n] = q; return q; };
  // Knochen-Orientierungen im Root-Raum
  const bq = new Map();
  const bQ = (o) => { if (o === S.model) return S.model.quaternion; if (bq.has(o)) return bq.get(o); const q = bQ(o.parent).clone().multiply(o.quaternion); bq.set(o, q); return q; };
  for (const [b, j] of SKIN_MAP) {
    const bone = B[b];
    if (!bone || !J[j]) continue;
    const want = jQ(j).clone().multiply(S.calib[b]);
    const pq = bQ(bone.parent);
    bone.quaternion.copy(pq).invert().multiply(want);
    bq.set(bone, want);
  }
  B.Hips.position.y = S.hipBindY * (J.hips.position.y / S.hipRestY);
  // Kopf-Zubehör (Augen, Haare, Hörner) folgt dem echten Kopf
  if (B.Head && J.head && J.neck) {
    rig.root.updateMatrixWorld(true);
    const p = B.Head.getWorldPosition(new V3());
    J.head.position.copy(J.neck.worldToLocal(p));
  }
}

// ---- Einhängen ins Rig
{
  const P = Rig.prototype;
  const _build = P.build, _update = P.update, _detach = P.detach, _reset = P.resetBody;
  P.build = function () { _build.call(this); this.skin = null; this.bodyMeshes = []; if (SkinLib.gltf) { try { attachSkin(this); } catch (e) { console.warn('skin attach', e); this.skin = null; } } };
  P.update = function (dt) { _update.call(this, dt); retarget(this); };
  P.detach = function (...a) { if (this.skin && this.skin.on) setSkin(this, false); return _detach.apply(this, a); };
  P.resetBody = function () { _reset.call(this); if (this.skin) setSkin(this, true); };
}
