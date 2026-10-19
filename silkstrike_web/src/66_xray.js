
// ---------------------------------------------------------------- Röntgen-Sequenz: Knochenbruch-Nahaufnahmen beim Brutal-Schlag / Todesstoß
// XRay.begin(opferRig, scene, ctl) · XRay.focus(ziel, dir) · XRay.hit(ziel, dir) · XRay.update(echtDt, cam) · XRay.end()
// Ziele: 'skull' | 'jaw' | 'ribs' | 'spine' | 'neck' | 'femur' | 'arm' | Mixamo-Knochenname eines Segment-Anfangs (z. B. 'LeftUpLeg')
const XRAY_SEGS = [
  ['Hips', 'Spine', 0.024], ['Spine', 'Spine1', 0.024], ['Spine1', 'Spine2', 0.024], ['Spine2', 'Neck', 0.022], ['Neck', 'Head', 0.018],
  ['LeftShoulder', 'LeftArm', 0.012], ['RightShoulder', 'RightArm', 0.012],
  ['LeftArm', 'LeftForeArm', 0.02], ['LeftForeArm', 'LeftHand', 0.016], ['RightArm', 'RightForeArm', 0.02], ['RightForeArm', 'RightHand', 0.016],
  ['LeftUpLeg', 'LeftLeg', 0.028], ['LeftLeg', 'LeftFoot', 0.022], ['LeftFoot', 'LeftToeBase', 0.014],
  ['RightUpLeg', 'RightLeg', 0.028], ['RightLeg', 'RightFoot', 0.022], ['RightFoot', 'RightToeBase', 0.014],
  ['LeftHand', 'LeftHandMiddle1', 0.012], ['RightHand', 'RightHandMiddle1', 0.012],
];
const XRAY_KNOBS = [['Spine', 0.03], ['Spine1', 0.03], ['Spine2', 0.03], ['Neck', 0.025], ['LeftArm', 0.034], ['RightArm', 0.034], ['LeftForeArm', 0.026], ['RightForeArm', 0.026],
  ['LeftHand', 0.026], ['RightHand', 0.026], ['LeftUpLeg', 0.04], ['RightUpLeg', 0.04], ['LeftLeg', 0.036], ['RightLeg', 0.036], ['LeftFoot', 0.028], ['RightFoot', 0.028]];
const XRAY_JOINT = { Hips: 'hips', Spine: 'spine', Spine1: 'chest', Spine2: 'chest', Neck: 'neck', Head: 'head', LeftShoulder: 'neck', RightShoulder: 'neck',
  LeftArm: 'lUpper', LeftForeArm: 'lFore', LeftHand: 'lHand', RightArm: 'rUpper', RightForeArm: 'rFore', RightHand: 'rHand',
  LeftUpLeg: 'lThigh', LeftLeg: 'lShin', LeftFoot: 'lFoot', RightUpLeg: 'rThigh', RightLeg: 'rShin', RightFoot: 'rFoot' };
const XRAY_ALIAS = { spine: 'Spine1', neck: 'Neck', femur: 'LeftUpLeg', arm: 'LeftArm', shin: 'LeftLeg' };
const XRAY_VS = `#include <common>
#include <skinning_pars_vertex>
varying vec3 vN; varying vec3 vV; varying vec3 vW;
void main() {
  #include <beginnormal_vertex>
  #include <skinbase_vertex>
  #include <skinnormal_vertex>
  #include <defaultnormal_vertex>
  #include <begin_vertex>
  #include <skinning_vertex>
  #include <project_vertex>
  vN = normalize(transformedNormal); vV = -mvPosition.xyz;
  vec4 wp = vec4(transformed, 1.0);
  #ifdef USE_INSTANCING
  wp = instanceMatrix * wp;
  #endif
  vW = (modelMatrix * wp).xyz;
}`;
const XRAY_FS_SHELL = `uniform vec3 uCol; uniform vec3 uHit; uniform vec3 uHitC; uniform float uHitI; uniform float uA;
varying vec3 vN; varying vec3 vV; varying vec3 vW;
void main() {
  float d = abs(dot(normalize(vN), normalize(vV)));
  float fr = pow(1.0 - d, 2.2);
  vec3 c = uCol * (0.03 + 0.95 * fr);
  float h = uHitI * (1.0 - smoothstep(0.0, 0.3, distance(vW, uHit)));
  c = mix(c, uHitC * (0.35 + 1.1 * fr), clamp(h, 0.0, 0.9));
  gl_FragColor = vec4(c * uA, 1.0);
}`;
const XRAY_FS_BONE = `varying vec3 vN; varying vec3 vV; varying vec3 vW;
void main() {
  float d = abs(dot(normalize(vN), normalize(vV)));
  vec3 c = mix(vec3(0.08, 0.24, 0.62), vec3(0.84, 0.83, 0.8), smoothstep(0.1, 0.85, d));
  gl_FragColor = vec4(c, 1.0);
}`;

const XRay = (() => {
  const _M = new THREE.Matrix4(), _L = new THREE.Matrix4(), _I = new THREE.Matrix4(), _Q = new THREE.Quaternion(), _Q2 = new THREE.Quaternion();
  const _S = new V3(), _T = new V3(), _a = new V3(), _b = new V3(), _c = new V3(), _d = new V3(), _x = new V3(), _y = new V3(), _z = new V3();
  const Y = new V3(0, 1, 0), Z = new V3(0, 0, 1), ZERO = new V3(), HIDE = new THREE.Matrix4().makeScale(0, 0, 0);
  const easeOut = (x) => { x = clamp(x, 0, 1); return 1 - (1 - x) * (1 - x) * (1 - x); };
  const CRACK = 0.13, SHOT = 0.78, NSH = 28, NCR = 48;
  // Segment-Matrix (Einheitszylinder entlang Y) von a nach b
  const segMat = (out, a, b, r) => { _T.subVectors(b, a); const L = _T.length(); _Q.setFromUnitVectors(Y, L > 1e-5 ? _T.multiplyScalar(1 / L) : Y); _S.set(r, Math.max(L, 1e-4), r); return out.compose(_T.addVectors(a, b).multiplyScalar(0.5), _Q, _S); };
  // Drehung um Pivot (Weltraum) + Versatz
  const bend = (m, p, axis, ang, off) => { m.premultiply(_M.makeTranslation(-p.x, -p.y, -p.z)); m.premultiply(_M.makeRotationAxis(axis, ang)); m.premultiply(_M.makeTranslation(p.x + off.x, p.y + off.y, p.z + off.z)); return m; };
  const frame = (F, o, up, side) => { _y.copy(up).normalize(); _x.copy(side).addScaledVector(_y, -side.dot(_y)); if (_x.lengthSq() < 1e-8) _x.set(1, 0, 0); _x.normalize(); _z.crossVectors(_x, _y); F.makeBasis(_x, _y, _z).setPosition(o); return F; };
  const loc = (out, F, px, py, pz, sx, sy, sz, ry = 0) => { _L.compose(_T.set(px, py, pz), _Q2.setFromAxisAngle(Y, ry), _S.set(sx, sy, sz)); return out.multiplyMatrices(F, _L); };
  const col = (F, i, out) => out.setFromMatrixColumn(F, i).normalize();

  const X = {
    on: false, rig: null, scene: null, ctl: null, shot: null, brk: [], saved: [], camPos: new V3(),
    build() {
      if (this.g) return;
      this.mBone = new THREE.ShaderMaterial({ vertexShader: XRAY_VS, fragmentShader: XRAY_FS_BONE, transparent: true, depthWrite: true, side: THREE.DoubleSide });
      this.mShell = new THREE.ShaderMaterial({ vertexShader: XRAY_VS, fragmentShader: XRAY_FS_SHELL, transparent: true, depthWrite: false, blending: THREE.AdditiveBlending,
        uniforms: { uCol: { value: new THREE.Color(0x3a8cff) }, uHit: { value: new V3() }, uHitC: { value: new THREE.Color(1, 0.12, 0.05) }, uHitI: { value: 0 }, uA: { value: 1 } } });
      const g = this.g = new THREE.Group(); g.name = 'xray'; g.visible = false;
      const IM = (geo, mat, n, ro) => { const m = new THREE.InstancedMesh(geo, mat, n); m.frustumCulled = false; m.renderOrder = ro; m.instanceMatrix.setUsage(THREE.DynamicDrawUsage); for (let i = 0; i < n; i++) m.setMatrixAt(i, HIDE); g.add(m); return m; };
      const M1 = (geo, mat, ro) => { const m = new THREE.Mesh(geo, mat); m.frustumCulled = false; m.matrixAutoUpdate = false; m.renderOrder = ro; g.add(m); return m; };
      this.shafts = IM(new THREE.CylinderGeometry(1, 1, 1, 7, 1), this.mBone, XRAY_SEGS.length * 2, 901);
      this.knobs = IM(new THREE.SphereGeometry(1, 8, 6), this.mBone, XRAY_KNOBS.length + 8, 901);
      this.ribs = IM(new THREE.TorusGeometry(1, 0.09, 4, 8, 1.35).rotateX(-Math.PI / 2), this.mBone, 24, 901);
      this.skull = IM(new THREE.SphereGeometry(1, 14, 10, 0, Math.PI), this.mBone, 2, 901);
      this.jaw = M1(new THREE.TorusGeometry(1, 0.2, 4, 10, Math.PI).rotateX(Math.PI / 2), this.mBone, 901);
      this.pelvis = M1(new THREE.TorusGeometry(1, 0.3, 5, 14).rotateX(Math.PI / 2), this.mBone, 901);
      this.mCrack = new THREE.MeshBasicMaterial({ color: 0x14040a, transparent: true, fog: false });
      this.cracks = IM(new THREE.BoxGeometry(1, 1, 1), this.mCrack, NCR, 902);
      this.shards = IM(new THREE.TetrahedronGeometry(1, 0), new THREE.MeshBasicMaterial({ color: 0xf4f8ff, transparent: true, fog: false }), NSH, 902);
      this.dim = new THREE.Mesh(new THREE.SphereGeometry(9, 12, 8), new THREE.MeshBasicMaterial({ color: 0x01050e, transparent: true, opacity: 0.9, side: THREE.BackSide, depthTest: false, depthWrite: false, fog: false }));
      this.dim.renderOrder = 900; this.dim.frustumCulled = false; g.add(this.dim);
      this.F = { c: new THREE.Matrix4(), h: new THREE.Matrix4(), p: new THREE.Matrix4() };
      this.mA = new THREE.Matrix4(); this.mB = new THREE.Matrix4(); this.mT = new THREE.Matrix4();
      this.sh = []; for (let i = 0; i < NSH; i++) this.sh.push({ p: new V3(), v: new V3(), ax: new V3(1, 0, 0), w: 0, s: 0, q: new THREE.Quaternion(), on: false });
      const names = new Set(['HeadTop_End']); for (const [a, b] of XRAY_SEGS) { names.add(a); names.add(b); } for (const [n] of XRAY_KNOBS) names.add(n);
      this.names = [...names]; this.P = {}; this.ok = {}; for (const n of this.names) this.P[n] = new V3();
    },
    // ---- Positionen aus Skin-Knochen (Fallback: Rig-Gelenke)
    fetch() {
      const S = this.skin, r = this.rig, P = this.P, ok = this.ok;
      for (const n of this.names) {
        if (S) { const b = S.B[n]; ok[n] = !!b; if (b) b.getWorldPosition(P[n]); }
        else { const j = XRAY_JOINT[n]; ok[n] = !!(j && r.j[j]); if (ok[n]) r.worldPos(j, P[n]); }
      }
      if (!ok.HeadTop_End && ok.Head && ok.Neck) { P.HeadTop_End.subVectors(P.Head, P.Neck).normalize().multiplyScalar(0.21 * this.unit).add(P.Head); ok.HeadTop_End = true; }
      return ok.Hips && ok.Spine && ok.Neck && ok.Head && ok.LeftArm && ok.RightArm && ok.LeftUpLeg && ok.RightUpLeg;
    },
    begin(rig, scene, ctl) {
      this.end();
      if (!rig || !scene) return false;
      this.build();
      this.rig = rig; this.scene = scene; this.ctl = ctl || null; this.skin = rig.skin && rig.skin.on ? rig.skin : null; this.unit = 1;
      if (!this.fetch()) { this.rig = null; return false; }
      this.unit = clamp(this.P.Hips.distanceTo(this.P.Neck) / 0.5, 0.5, 2.2);
      const blood = Settings.data.blood;
      this.mShell.uniforms.uHitC.value.set(blood ? 0xff2010 : 0xbfe8ff); this.mCrack.color.set(blood ? 0x1a0306 : 0x081626);
      scene.add(this.g); this.g.visible = false; this.brk = []; this.on = true;
      return true;
    },
    target(name) {
      if (name === 'skull' || name === 'jaw') return { kind: 'skull', jaw: name === 'jaw' };
      if (name === 'ribs') return { kind: 'ribs' };
      const bn = XRAY_ALIAS[name] || name;
      let i = XRAY_SEGS.findIndex((s) => s[0] === bn);
      if (i < 0) i = 2;
      if (i === 2 && !this.skin) i = 1; // Rig-Fallback: Spine1/Spine2 fallen zusammen
      return { kind: 'seg', i };
    },
    focus(name, dir) {
      if (!this.on) return;
      if (this.shot) { if (this.shot.ht < 0) return; this.close(); }
      const tg = this.target(name), d = (dir ? dir.clone() : new V3(1, 0, 0)).normalize();
      const off = new V3(d.x * 0.4, 0.14, 1).normalize();
      this.shot = { tg, dir: d, off, t: 0, ht: -1, broke: false, dist: tg.kind === 'skull' ? 1.1 : tg.kind === 'ribs' ? 1.4 : 1.5, prev: null, tp: new V3(), b: null };
      this.saved = []; this.rig.root.traverseVisible((o) => { if (o.isMesh && !o.isInstancedMesh && o.material !== this.mShell) { this.saved.push([o, o.material]); o.material = this.mShell; } });
      this.mShell.uniforms.uHitI.value = 0; this.g.visible = true;
    },
    hit(name, dir) {
      if (!this.on) return;
      if (!this.shot || this.shot.ht >= 0) this.focus(name, dir);
      const sh = this.shot; if (!sh) return;
      sh.ht = 0; if (dir) sh.dir.copy(dir).normalize();
      const b = { tg: sh.tg, dir: sh.dir.clone(), t: 0, side: null, cr: null, hosts: [] };
      sh.b = b; this.brk.push(b);
      if (this.ctl) { sh.prev = this.ctl.scale; this.ctl.setScale(0.03); this.ctl.shake.add(0.35); }
    },
    snap(sh) {
      sh.broke = true;
      const blood = Settings.data.blood, u = this.unit;
      UI.flash(blood ? '#b0000c' : '#d8ecff'); Audio.play('boneCrack'); Audio.play('boneCrack', 0.7); if (blood) Audio.play('gore', 0.5);
      Haptic(90);
      if (this.ctl) { this.ctl.shake.add(1.1); this.ctl.setScale(0.08); }
      for (const s of this.sh) {
        s.on = true; s.p.copy(sh.tp).add(_a.set(rand(-1, 1), rand(-1, 1), rand(-1, 1)).multiplyScalar(0.012 * u));
        s.v.copy(sh.dir).multiplyScalar(rand(0.25, 0.75)).add(_a.set(rand(-1, 1), rand(-0.6, 1), rand(-1, 1)).normalize().multiplyScalar(rand(0.2, 0.55))).multiplyScalar(u);
        s.ax.set(rand(-1, 1), rand(-1, 1), rand(-1, 1)).normalize(); s.w = rand(3, 9); s.s = rand(0.004, 0.011) * u; s.q.identity();
      }
    },
    close() {
      const sh = this.shot; if (!sh) return;
      for (const [o, m] of this.saved) o.material = m;
      this.saved = []; this.g.visible = false; this.shot = null;
      for (const s of this.sh) s.on = false;
      if (this.ctl && sh.prev != null) this.ctl.setScale(sh.prev);
    },
    end() {
      this.close();
      if (this.g && this.g.parent) this.g.parent.remove(this.g);
      this.rig = null; this.scene = null; this.ctl = null; this.skin = null; this.brk = []; this.on = false;
    },
    // ---- pro Frame (Echtzeit-dt), nach dem Rig-Update; überschreibt die Kamera während einer Röntgen-Einstellung
    update(rdt, cam) {
      const sh = this.shot; if (!this.on || !sh) return;
      const dt = Math.min(rdt, 0.1);
      sh.t += dt; if (sh.ht >= 0) sh.ht += dt;
      for (const b of this.brk) b.t += dt;
      if ((sh.ht < 0 && sh.t > 1.3) || sh.ht > SHOT) { this.close(); return; }
      if (!this.fetch()) { this.close(); return; }
      this.pose(sh);
      if (sh.ht >= CRACK && !sh.broke) this.snap(sh);
      // Kamera: Nahaufnahme auf die Bruchstelle, langsame Fahrt
      const d = sh.dist * this.unit * (1 - 0.14 * Math.min(1, sh.t / 1.1));
      if (cam) { cam.look.copy(sh.tp); cam.pos.copy(sh.tp).addScaledVector(sh.off, d); cam.fov = 32; this.camPos.copy(cam.pos); }
      this.dim.position.copy(sh.tp); this.dim.updateMatrixWorld();
      const U = this.mShell.uniforms; U.uHit.value.copy(sh.tp);
      U.uHitI.value = sh.ht < 0 ? 0 : sh.ht < CRACK ? sh.ht / CRACK * 0.6 : Math.max(0.35, 1.4 - (sh.ht - CRACK) * 1.8);
      U.uA.value = Math.min(1, sh.t / 0.06);
      this.crackUpdate();
      this.shardUpdate(dt);
    },
    brkOf(kind, i) { for (const b of this.brk) if (b.tg.kind === kind && (kind !== 'seg' || b.tg.i === i)) return b; return null; },
    amt(b) { return easeOut((b.t - CRACK) / 0.3); },
    pose(sh) {
      const P = this.P, ok = this.ok, u = this.unit, F = this.F, mA = this.mA, mB = this.mB;
      frame(F.c, P.Spine, _a.subVectors(P.Neck, P.Spine), _b.subVectors(P.LeftArm, P.RightArm));
      const cx = col(F.c, 0, new V3()), cy = col(F.c, 1, new V3()), cz = col(F.c, 2, new V3());
      frame(F.h, P.Head, _a.subVectors(P.HeadTop_End, P.Head), cx);
      frame(F.p, P.Hips, _a.subVectors(P.Spine, P.Hips), _b.subVectors(P.LeftUpLeg, P.RightUpLeg));
      const tg = sh.tg;
      // Schäfte (je zwei Hälften, damit sie brechen können)
      let vk = XRAY_KNOBS.length;
      for (let i = 0; i < XRAY_SEGS.length; i++) {
        const [na, nb, r] = XRAY_SEGS[i];
        if (!ok[na] || !ok[nb]) { this.shafts.setMatrixAt(2 * i, HIDE); this.shafts.setMatrixAt(2 * i + 1, HIDE); if (i < 4) { this.knobs.setMatrixAt(vk++, HIDE); this.knobs.setMatrixAt(vk++, HIDE); } continue; }
        const a = P[na], b = P[nb], m = _c.lerpVectors(a, b, 0.5);
        segMat(mA, a, m, r * u); segMat(mB, m, b, r * u);
        const bk = this.brkOf('seg', i);
        if (bk) {
          const k = this.amt(bk), sd = _d.subVectors(b, a).normalize();
          const ax = new V3().crossVectors(sd, bk.dir); if (ax.lengthSq() < 1e-6) ax.copy(cx); ax.normalize();
          const gap = 0.007 * u * k, push = bk.dir.clone().multiplyScalar(0.006 * u * k);
          bend(mA, a, ax, 0.3 * k, push.clone().addScaledVector(sd, -gap)); bend(mB, b, ax, -0.3 * k, push.addScaledVector(sd, gap));
          bk.hosts[0] = (bk.hosts[0] || new THREE.Matrix4()).copy(mA);
        }
        if (tg.kind === 'seg' && tg.i === i) sh.tp.copy(m);
        this.shafts.setMatrixAt(2 * i, mA); this.shafts.setMatrixAt(2 * i + 1, mB);
        if (i < 4) for (const fr of [0.33, 0.66]) { // Wirbel
          const M = fr < 0.5 ? mA : mB; _T.set(0, fr < 0.5 ? fr * 2 - 0.5 : (fr - 0.5) * 2 - 0.5, 0).applyMatrix4(M);
          this.knobs.setMatrixAt(vk++, _M.compose(_T, _Q.identity(), _S.setScalar(0.021 * u)));
        }
      }
      for (let i = 0; i < XRAY_KNOBS.length; i++) {
        const [n, r] = XRAY_KNOBS[i];
        this.knobs.setMatrixAt(i, ok[n] ? _M.compose(P[n], _Q.identity(), _S.setScalar(r * u)) : HIDE);
      }
      // Brustkorb: 6 Ebenen × 2 Seiten × (hinten, vorne)
      const H = P.Neck.distanceTo(P.Spine), rb = this.brkOf('ribs');
      if (rb && rb.side == null) rb.side = cx.dot(sh.off) >= 0 ? 1 : -1;
      const rside = rb ? rb.side : cx.dot(sh.off) >= 0 ? 1 : -1;
      let ri = 0;
      for (let l = 0; l < 6; l++) {
        const bw = Math.sin(Math.PI * (l + 1.4) / 7.6), rx = u * (0.075 + 0.06 * bw), rz = u * (0.06 + 0.035 * bw), ly = H * (0.12 + 0.14 * l), lz = rz * 0.45;
        for (const s of [1, -1]) for (const zs of [1, -1]) {
          loc(this.mT, F.c, 0, ly, lz, s * rx, rx, zs * rz);
          if (zs < 0 && s === rside && l >= 1 && l <= 3) {
            if (rb) {
              const k = this.amt(rb), pv = _T.set(s * rx, ly, lz).applyMatrix4(F.c).clone();
              bend(this.mT, pv, cx, (0.35 + 0.08 * l) * k, cz.clone().multiplyScalar(0.01 * u * k).addScaledVector(cy, -0.018 * u * k).addScaledVector(rb.dir, 0.006 * u * k));
              rb.hosts[l - 1] = (rb.hosts[l - 1] || new THREE.Matrix4()).copy(this.mT);
            }
            if (l === 2 && tg.kind === 'ribs') sh.tp.set(s * rx * 0.95, ly, lz + rz * 0.2).applyMatrix4(F.c);
          }
          this.ribs.setMatrixAt(ri++, this.mT);
        }
      }
      // Schädel (zwei Hälften) + Kiefer
      const hh = P.Head.distanceTo(P.HeadTop_End), sk = this.brkOf('skull');
      const srx = 0.38 * hh, sry = 0.47 * hh, srz = 0.5 * hh, scy = 0.52 * hh, scz = 0.06 * hh;
      const hx = col(F.h, 0, new V3()), hz = col(F.h, 2, new V3());
      if (sk && sk.side == null) sk.side = 0; // Gesichtshälfte trägt die Risse
      for (let s = 0; s < 2; s++) {
        loc(this.mT, F.h, 0, scy, scz, srx, sry, srz, s ? Math.PI : 0);
        if (sk) {
          const k = this.amt(sk), pv = _T.set(0, scy - sry * 0.8, scz).applyMatrix4(F.h).clone();
          bend(this.mT, pv, hx, (s ? -1 : 1) * 0.2 * k, hz.clone().multiplyScalar((s ? -1 : 1) * 0.012 * u * k));
          if (s === sk.side) sk.hosts[0] = (sk.hosts[0] || new THREE.Matrix4()).copy(this.mT);
        }
        this.skull.setMatrixAt(s, this.mT);
      }
      if (tg.kind === 'skull') sh.tp.set(0, scy + sry * 0.15, scz).applyMatrix4(F.h);
      loc(this.jaw.matrix, F.h, 0, 0.1 * hh, 0.2 * hh, 0.3 * hh, 0.3 * hh, 0.36 * hh);
      if (sk) { const k = this.amt(sk) * (sk.tg.jaw ? 1.6 : 1); bend(this.jaw.matrix, _T.set(0, 0.16 * hh, -0.06 * hh).applyMatrix4(F.h).clone(), hx, 0.3 * k, sk.dir.clone().multiplyScalar(0.012 * u * k)); }
      loc(this.pelvis.matrix, F.p, 0, 0.02 * u, 0.01 * u, 0.115 * u, 0.075 * u, 0.085 * u);
      this.jaw.matrixWorldNeedsUpdate = true; this.pelvis.matrixWorldNeedsUpdate = true;
      for (const m of [this.shafts, this.knobs, this.ribs, this.skull]) m.instanceMatrix.needsUpdate = true;
    },
    // ---- Risslinien: zufällige Zickzack-Linien im lokalen Raum des getroffenen Knochenstücks
    genCracks(b) {
      const host = b.hosts.find(Boolean); if (!host) return null;
      const inv = _I.copy(host).invert(), cl = this.camPos.clone().applyMatrix4(inv), L = [];
      if (b.tg.kind === 'seg') {
        const th = Math.atan2(cl.z, cl.x), ring = [];
        for (let k = 0; k < 7; k++) { const a = th - 1.5 + k * 0.5 + rand(-0.12, 0.12); ring.push(new V3(Math.cos(a) * 1.12, 0.42 + rand(-0.07, 0.07), Math.sin(a) * 1.12)); }
        L.push({ h: 0, p: ring });
        for (const st of [ring[2], ring[4]]) { const br = [st.clone()]; let a = Math.atan2(st.z, st.x), y = st.y; for (let k = 0; k < 3; k++) { a += rand(-0.35, 0.35); y -= rand(0.08, 0.16); br.push(new V3(Math.cos(a) * 1.12, y, Math.sin(a) * 1.12)); } L.push({ h: 0, p: br }); }
      } else if (b.tg.kind === 'skull') {
        const seam = []; for (let k = 0; k < 8; k++) { const a = 0.35 + k * 0.35; seam.push(new V3(Math.cos(a), Math.sin(a), rand(0.03, 0.12)).normalize().multiplyScalar(1.04)); }
        L.push({ h: 0, p: seam });
        for (const st of [seam[2], seam[5]]) { const br = [st.clone()]; const p = st.clone(); for (let k = 0; k < 3; k++) { p.z += rand(0.18, 0.3); p.y -= rand(0.05, 0.2); p.x += rand(-0.15, 0.15); br.push(p.clone().normalize().multiplyScalar(1.04)); } L.push({ h: 0, p: br }); }
      } else {
        b.hosts.forEach((m, hi) => { if (!m) return; const p = [], u0 = rand(0.05, 0.1); for (let k = 0; k < 5; k++) { const t = -2.2 + k * 1.1, uu = u0 + rand(-0.03, 0.03), c = new V3(Math.cos(uu), 0, -Math.sin(uu)); p.push(c.clone().multiplyScalar(1 + Math.cos(t) * 0.11).add(new V3(0, Math.sin(t) * 0.11, 0))); } L.push({ h: hi, p }); });
      }
      return L;
    },
    crackUpdate() {
      let n = 0;
      const w = 0.006 * this.unit;
      for (const b of this.brk) {
        if (!b.cr) b.cr = this.genCracks(b);
        if (!b.cr) continue;
        let tot = 0; for (const l of b.cr) tot += l.p.length - 1;
        const vis = Math.ceil(tot * clamp(b.t / CRACK, 0, 1)); let c = 0;
        for (const l of b.cr) {
          const host = b.hosts[l.h]; if (!host) continue;
          for (let k = 0; k < l.p.length - 1 && n < NCR; k++, c++) {
            if (c >= vis) continue;
            _a.copy(l.p[k]).applyMatrix4(host); _b.copy(l.p[k + 1]).applyMatrix4(host);
            _d.subVectors(_b, _a); const len = _d.length(); if (len < 1e-5) continue;
            _Q.setFromUnitVectors(Z, _d.multiplyScalar(1 / len));
            this.cracks.setMatrixAt(n++, _M.compose(_c.addVectors(_a, _b).multiplyScalar(0.5), _Q, _S.set(w, w, len + w)));
          }
        }
      }
      for (let i = n; i < NCR; i++) this.cracks.setMatrixAt(i, HIDE);
      this.cracks.instanceMatrix.needsUpdate = true;
    },
    shardUpdate(dt) {
      for (let i = 0; i < NSH; i++) {
        const s = this.sh[i];
        if (!s.on) { this.shards.setMatrixAt(i, HIDE); continue; }
        s.v.y -= 1.1 * dt; s.v.multiplyScalar(1 - 0.6 * dt); s.p.addScaledVector(s.v, dt);
        s.q.premultiply(_Q.setFromAxisAngle(s.ax, s.w * dt));
        this.shards.setMatrixAt(i, _M.compose(s.p, s.q, _S.setScalar(s.s)));
      }
      this.shards.instanceMatrix.needsUpdate = true;
    },
  };
  return X;
})();
