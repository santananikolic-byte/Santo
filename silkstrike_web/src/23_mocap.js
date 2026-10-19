// =====================================================================
//  Motion-Capture: echte Bewegungen (CMU-Datenbank) auf den Skin-Knochen
//  clips.json: q = Knochen-Rotation (Charakterraum) relativ zur kanonischen
//  T-Pose, p = Hüftposition in Metern. Figur schaut nach +Z, links = +X.
// =====================================================================
const MOCAP_PATH = Assets.need('json', 'mocap/clips.json');
const MOCAP_CHILD = {
  Hips: 'Spine', Spine: 'Spine1', Spine1: 'Spine2', Spine2: 'Neck', Neck: 'Head', Head: 'HeadTop_End',
  LeftShoulder: 'LeftArm', LeftArm: 'LeftForeArm', LeftForeArm: 'LeftHand', LeftHand: 'LeftHandMiddle1',
  RightShoulder: 'RightArm', RightArm: 'RightForeArm', RightForeArm: 'RightHand', RightHand: 'RightHandMiddle1',
  LeftUpLeg: 'LeftLeg', LeftLeg: 'LeftFoot', LeftFoot: 'LeftToeBase', LeftToeBase: 'LeftToe_End',
  RightUpLeg: 'RightLeg', RightLeg: 'RightFoot', RightFoot: 'RightToeBase', RightToeBase: 'RightToe_End',
};
const mocapCanonDir = (b) => /^Left(Shoulder|Arm|ForeArm|Hand)$/.test(b) ? new V3(1, 0, 0)
  : /^Right(Shoulder|Arm|ForeArm|Hand)$/.test(b) ? new V3(-1, 0, 0)
  : /UpLeg|^(Left|Right)Leg$/.test(b) ? new V3(0, -1, 0)
  : /Foot|Toe/.test(b) ? new V3(0, 0, 1) : new V3(0, 1, 0);
// Treffer-Zeitpunkt im Spiel (Anteil der Clip-Dauer), auf den der Mocap-Treffer gelegt wird
const MOCAP_HIT_AT = 0.36;

const Mocap = {
  lib: null, fps: 30, hip: 0.95,
  init() {
    const d = Assets.json(MOCAP_PATH);
    if (!d || !d.clips || !d.bones) return;
    this.lib = d; this.fps = d.fps || 30;
    // Stehhöhe der Hüfte aus 'idle' (sonst Annahme)
    const c = d.clips.idle || d.clips.walkForward;
    if (c && c.p && c.n) { let s = 0; for (let i = 0; i < c.n; i++) s += c.p[i * 3 + 1]; this.hip = clamp(s / c.n, 0.8, 1.1); }
  },
  clip(name) { return this.lib ? this.lib.clips[name] || null : null; },
};

// Kanonische T-Pose des Modells (je Knochen) und Hüft-Umrechnung; Modell steht dabei noch in der Bind-Pose
function mocapCalibrate(rig) {
  const S = rig.skin, B = S.B, model = S.model;
  rig.root.updateMatrixWorld(true);
  const invRoot = rig.root.matrixWorld.clone().invert();
  const posR = (o) => o.getWorldPosition(new V3()).applyMatrix4(invRoot);
  const rootQ = (o) => { const chain = []; for (let x = o; x && x !== rig.root; x = x.parent) chain.push(x); const q = new THREE.Quaternion(); for (let i = chain.length - 1; i >= 0; i--) q.multiply(chain[i].quaternion); return q; };
  S.canon = {};
  for (const b in MOCAP_CHILD) {
    if (!B[b]) continue;
    const q = rootQ(B[b]), c = B[MOCAP_CHILD[b]];
    if (c) {
      const dir = posR(c).sub(posR(B[b]));
      if (dir.lengthSq() > 1e-10) { S.canon[b] = new THREE.Quaternion().setFromUnitVectors(dir.normalize(), mocapCanonDir(b)).multiply(q); continue; }
    }
    S.canon[b] = q;
  }
  S.hipRootBind = posR(B.Hips);
  // Root-Raum -> lokaler Raum des Hüft-Elternknotens
  S.hipParentInv = invRoot.clone().multiply(B.Hips.parent.matrixWorld).invert();
  S.modelQ = model.quaternion;
}

const _mqa = new THREE.Quaternion(), _mqb = new THREE.Quaternion(), _mv = new V3();
function mocapApply(rig) {
  const S = rig.skin, L = Mocap.lib;
  if (!S || !S.canon || !L) return false;
  const c = L.clips[rig.clip];
  if (!c || !c.n) return false;
  let f;
  if (c.loop) f = (rig.clipT * Mocap.fps) % c.n;
  else {
    let p = clamp(rig.clipT / Math.max(0.01, rig.clipDur), 0, 1);
    if (c.hit != null) { const h = clamp(c.hit, 0.05, 0.95); p = p < MOCAP_HIT_AT ? p / MOCAP_HIT_AT * h : h + (p - MOCAP_HIT_AT) / (1 - MOCAP_HIT_AT) * (1 - h); }
    f = p * (c.n - 1);
  }
  const f0 = Math.floor(f) % c.n, f1 = c.loop ? (f0 + 1) % c.n : Math.min(c.n - 1, f0 + 1), k = f - Math.floor(f);
  const nb = L.bones.length, B = S.B;
  const bq = new Map();
  const bQ = (o) => { if (o === rig.root) return new THREE.Quaternion(); if (bq.has(o)) return bq.get(o); const q = bQ(o.parent).clone().multiply(o.quaternion); bq.set(o, q); return q; };
  for (let i = 0; i < nb; i++) {
    const name = L.bones[i], bone = B[name], cq = S.canon[name];
    if (!bone || !cq) continue;
    _mqa.fromArray(c.q, (f0 * nb + i) * 4); _mqb.fromArray(c.q, (f1 * nb + i) * 4); _mqa.slerp(_mqb, k);
    const want = _mqa.clone().multiply(cq);
    bone.quaternion.copy(bQ(bone.parent)).invert().multiply(want);
    bq.set(bone, want);
  }
  if (c.p) {
    const sc = S.hipRestY / Mocap.hip, a = f0 * 3, b = f1 * 3;
    _mv.set(S.hipRootBind.x + lerp(c.p[a], c.p[b], k) * sc, lerp(c.p[a + 1], c.p[b + 1], k) * sc, S.hipRootBind.z + lerp(c.p[a + 2], c.p[b + 2], k) * sc);
    B.Hips.position.copy(_mv.applyMatrix4(S.hipParentInv));
  }
  return true;
}
