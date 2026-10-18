// =====================================================================
//  Zwischensequenzen: Kulissen, Schauspieler, Kamerafahrten, Untertitel
// =====================================================================
const lineDur = (text) => Math.max(2.4, text.length * 0.062 + 0.9);
function camFromDef(c) {
  const v = (a) => new V3(a[0], a[1], a[2]);
  if (c.preset === 'overLeft') return { from: v([-2.3, 1.65, 1.5]), to: v([-2.1, 1.62, 1.2]), look: v([1.2, 1.5, 0]), lookTo: v([1.2, 1.5, 0]), fov: c.fov || 40, fovTo: c.fov || 40 };
  if (c.preset === 'overRight') return { from: v([2.3, 1.65, 1.5]), to: v([2.1, 1.62, 1.2]), look: v([-1.2, 1.5, 0]), lookTo: v([-1.2, 1.5, 0]), fov: c.fov || 40, fovTo: c.fov || 40 };
  if (c.preset === 'twoShot') return { from: v([0, 1.45, 5]), to: v([0, 1.5, 4]), look: v([0, 1.3, 0]), lookTo: v([0, 1.3, 0]), fov: 42, fovTo: 42 };
  if (c.preset === 'heroLow') { const x = c.x; return { from: v([x + 0.6, 0.35, 2.2]), to: v([x + 0.3, 0.45, 1.7]), look: v([x, 1.7, 0]), lookTo: v([x, 1.7, 0]), fov: 38, fovTo: 34 }; }
  return { from: v(c.from), to: v(c.to), look: v(c.look), lookTo: v(c.lookTo || c.look), fov: c.fov || 45, fovTo: c.fovTo || c.fov || 45 };
}

function buildStage(def, scene, anim) {
  const q = Settings.data.quality;
  if (def.stage === 'arena') { buildArena(def.arena, scene, anim); return; }
  applyEnvironment(scene, def.tod, def.stage === 'lab' ? 0.004 : 0.003);
  const key = new THREE.DirectionalLight(def.tod === 'dusk' ? 0xffa070 : 0xa8b4ff, def.tod === 'dusk' ? 1.6 : 1.0);
  key.position.set(-6, 10, 6); key.castShadow = q !== 'performance'; key.shadow.mapSize.set(1024, 1024);
  const sc = key.shadow.camera; sc.left = -10; sc.right = 10; sc.top = 10; sc.bottom = -10;
  scene.add(key);
  const rim = new THREE.SpotLight(0xff3040, 24, 40, 0.7, 0.6); rim.position.set(0, 6, -8); rim.target.position.set(0, 1.2, 0); scene.add(rim, rim.target);
  scene.add(new THREE.HemisphereLight(0x5a6688, 0x1a1012, 0.7));
  if (def.stage === 'cityRooftop' || def.stage === 'cityStreet') {
    scene.add(buildSkyline(7, q, def.tod, 30, -60));
    const m = new MeshBuilder();
    m.box(-12, -1, -12, 12, 0, 12, 0.2);
    scene.add(m.mesh(new THREE.MeshStandardMaterial({ map: Tex.concrete(), roughness: def.tod === 'stormNight' ? 0.15 : 0.6, metalness: 0.1 }), false));
    const p = new MeshBuilder();
    p.box(-12, 0, -12, 12, 1.1, -11.6, 0.3); p.box(-12, 0, -12, -11.6, 1.1, 12, 0.3); p.box(11.6, 0, -12, 12, 1.1, 12, 0.3);
    p.box(-6, 0, -8, -3.5, 1.5, -6, 0.3); p.box(4, 0, -9, 7.5, 2.2, -6.5, 0.3); p.cyl(-8, 2.5, 5, 2, 3.5, 16); p.cyl(8, 0, 6, 0.12, 12, 6);
    scene.add(p.mesh(new THREE.MeshStandardMaterial({ map: Tex.metal(), roughness: 0.4, metalness: 0.7 })));
    const rift = FX.rift(0xff1030, 10); rift.position.set(0, 40, -90); scene.add(rift); anim.push(rift.userData.anim);
  } else if (def.stage === 'lab') {
    const sky = buildSkyline(11, q, def.tod, 40, -120); scene.add(sky);
    const f = new MeshBuilder(); f.box(-8, -0.2, -6, 8, 0, 6, 0.25);
    scene.add(f.mesh(new THREE.MeshStandardMaterial({ map: Tex.tiles(), roughness: 0.2, metalness: 0.1 }), false));
    const w = new MeshBuilder();
    w.box(-8.2, 0, -6, -8, 4, 6, 0.25); w.box(8, 0, -6, 8.2, 4, 6, 0.25); w.box(-8, 3.8, -6, 8, 4, 6, 0.25);
    for (let k = 0; k < 5; k++) w.box(-8 + k * 4 - 0.1, 0, -6.2, -8 + k * 4 + 0.1, 4, -6, 0.25);
    w.box(-8, 0, -6.2, 8, 0.8, -6, 0.25); w.box(2.5, 0.9, -3.5, 6.5, 1.0, -2, 0.25); w.box(2.6, 0, -3.4, 2.8, 0.9, -2.1, 0.25); w.box(6.2, 0, -3.4, 6.4, 0.9, -2.1, 0.25);
    scene.add(w.mesh(pbr(0x1e1f24, 0.5, 0.4)));
    const scr = new MeshBuilder(); for (let k = 0; k < 3; k++) scr.box(3 + k * 1.2, 1.1, -3.3, 4 + k * 1.2, 1.75, -3.25, 1);
    scene.add(scr.mesh(glowMat(0x33ccff, 2.5), false));
    const tube = new THREE.Mesh(new THREE.CylinderGeometry(0.35, 0.35, 1.4, 20), new THREE.MeshStandardMaterial({ color: 0xffffff, transparent: true, opacity: 0.22, roughness: 0.02 }));
    tube.position.set(-4.5, 0.7, -3); scene.add(tube);
    const silk = new THREE.Mesh(new THREE.SphereGeometry(0.22, 20, 14), new THREE.MeshStandardMaterial({ color: 0x080010, emissive: 0x8020ff, emissiveIntensity: 1.5, roughness: 0.1, metalness: 0.4 }));
    silk.position.set(-4.5, 0.75, -3); scene.add(silk);
    anim.push(() => { const s = 1 + 0.2 * Math.sin(Game.time * 3.5); silk.scale.setScalar(s); });
    const gl = new THREE.PointLight(0x9a30ff, 6, 6, 2); gl.position.set(-4.5, 1.2, -3); scene.add(gl);
    for (const x of [-4, 0, 4]) { const l = new THREE.PointLight(0xd8ecff, 8, 9, 2); l.position.set(x, 3.6, 0); scene.add(l); }
  }
}

class CutsceneController {
  constructor(id, onDone) {
    this.def = STORY.cutscenes[id];
    this.onDone = onDone;
    this.scene = new THREE.Scene();
    this.camera = new THREE.PerspectiveCamera(45, innerWidth / innerHeight, 0.05, 2000);
    this.anim = []; this.actors = {}; this.shake = new Shake(); this.scale = 1;
    FX.attach(this.scene, 0);
    if (!this.def) { setTimeout(() => onDone && onDone(), 0); return; }
    buildStage(this.def, this.scene, this.anim);
    this.rain = this.def.tod === 'stormNight' && this.def.stage !== 'lab' && this.def.arena !== 'subway' ? new Rain(900) : null;
    if (this.rain) this.scene.add(this.rain.lines);
    const shown = new Set(); this.def.shots.forEach((s) => s.events.forEach((e) => { if (e[1] === 'show') shown.add(e[2]); }));
    for (const a of this.def.actors) {
      const r = new Rig(a.cast);
      r.root.position.set(a.x, 0, a.z); r.root.rotation.y = a.yaw * Math.PI / 180;
      r.play(a.clip); r.root.visible = !shown.has(a.key);
      this.scene.add(r.root); this.actors[a.key] = r;
    }
    this.shots = this.def.shots.map((s) => ({ cam: camFromDef(s.cam), lines: s.lines.map(([c, t]) => ({ cast: c, text: t, d: lineDur(t) })), events: s.events.slice().sort((x, y) => x[0] - y[0]), dur: 0, extra: s.extra }));
    this.shots.forEach((s) => { s.dur = Math.max(3, s.lines.reduce((a, l) => a + l.d, 0) + s.extra); });
    this.si = 0; this.st = 0; this.li = -1; this.lt = 0; this.ei = 0; this.fade = 0; this.out = -1; this.done = false; this.titleT = this.def.title ? 2.8 : 0;
    UI.cutscene(true, this.def.title);
    Audio.setMusic(this.def.music);
    this.applyCam(this.shots[0].cam, 0, 0);
  }
  dispose() { UI.cutscene(false); Audio.stopSpeech(); Audio.setSlow(1); }
  skip() { if (this.out < 0 && !this.done) { Audio.stopSpeech(); this.out = 0; } }
  finish() { if (this.done) return; this.done = true; UI.subtitle(null); Audio.stopSpeech(); Audio.setSlow(1); const cb = this.onDone; this.onDone = null; if (cb) cb(); }
  update(dt) {
    if (!this.def || this.done) return;
    if (Input.consume('skip') || Input.consume('pause')) this.skip();
    if (this.fade < 0.8) { this.fade += dt; if (this.out < 0) UI.fade(Math.max(0, 1 - this.fade / 0.8)); }
    if (this.titleT > 0) { this.titleT -= dt; if (this.titleT <= 0) UI.cutTitle(null); }
    if (this.out >= 0) { this.out += dt; UI.fade(Math.min(1, this.out / 0.6)); if (this.out >= 0.65) { this.finish(); return; } }
    const sdt = dt * this.scale;
    for (const k in this.actors) this.actors[k].update(sdt);
    this.anim.forEach((a) => a(sdt));
    FX.update(sdt, this.camera);
    if (this.rain) this.rain.update(dt, this.camera);
    if (this.si >= this.shots.length) { if (this.out < 0) this.out = 0; return; }
    const s = this.shots[this.si];
    this.st += sdt;
    while (this.ei < s.events.length && s.events[this.ei][0] <= this.st) { this.fire(s.events[this.ei]); this.ei++; }
    if (s.lines.length) {
      if (this.li < 0) { this.li = 0; this.lt = 0; this.say(s.lines[0]); }
      else if (this.li < s.lines.length) { this.lt += sdt; if (this.lt >= s.lines[this.li].d) { this.li++; this.lt = 0; if (this.li < s.lines.length) this.say(s.lines[this.li]); else UI.subtitle(null); } }
    }
    this.applyCam(s.cam, easeInOut(this.st / s.dur), dt);
    if (this.st >= s.dur) { this.si++; this.st = 0; this.li = -1; this.ei = 0; UI.subtitle(null); }
  }
  say(l) { UI.subtitle(castName(l.cast), l.text); Audio.stopSpeech(); Audio.speak(l.text, l.cast); }
  applyCam(c, k, dt) {
    const sh = this.shake.update(dt || 0);
    const p = c.from.clone().lerp(c.to, k), l = c.look.clone().lerp(c.lookTo, k);
    this.camera.position.copy(p).add(new V3(sh.x, sh.y, 0));
    this.camera.up.set(Math.sin(sh.roll), 1, 0);
    this.camera.lookAt(l);
    this.camera.fov = lerp(c.fov, c.fovTo, k); this.camera.updateProjectionMatrix();
  }
  fire(e) {
    const [, kind, a, b] = e;
    const r = this.actors[a];
    switch (kind) {
      case 'clip': if (r) r.play(b, null, true, 0.18); break;
      case 'show': if (r) r.root.visible = true; break;
      case 'hide': if (r) r.root.visible = false; break;
      case 'setCast': if (r) r.setLook(b); break;
      case 'sound': Audio.play(a); break;
      case 'music': Audio.setMusic(a); break;
      case 'shake': this.shake.add(a); if (a > 0.5) Haptic(30); break;
      case 'slow': this.scale = clamp(a, 0.05, 2); Audio.setSlow(this.scale); break;
      case 'flash': UI.flash(`rgb(${Math.round(a[0] * 255)},${Math.round(a[1] * 255)},${Math.round(a[2] * 255)})`); break;
      case 'effect': FX.burst(a, new V3(b[0], b[1], b[2]), 1.2); break;
    }
  }
}

// Titelkulisse: Silkstrike hockt vor der nächtlichen Skyline
class TitleController {
  constructor() {
    this.scene = new THREE.Scene();
    this.camera = new THREE.PerspectiveCamera(50, innerWidth / innerHeight, 0.05, 2000);
    this.anim = [];
    FX.attach(this.scene, 0);
    buildStage({ stage: 'cityRooftop', tod: 'stormNight' }, this.scene, this.anim);
    this.rain = new Rain(900); this.scene.add(this.rain.lines);
    this.hero = new Rig('silkstrike'); this.hero.root.position.set(1.4, 1.1, -11.8); this.hero.root.rotation.y = Math.PI; this.hero.play('perch');
    this.scene.add(this.hero.root);
    this.t = 0;
  }
  dispose() { }
  update(dt) {
    this.t += dt;
    this.hero.update(dt); this.anim.forEach((a) => a(dt)); FX.update(dt, this.camera); this.rain.update(dt, this.camera);
    const a = 0.25 * Math.sin(this.t * 0.08);
    this.camera.position.set(1.4 + Math.sin(a + 0.5) * 4.2, 1.9 + 0.3 * Math.sin(this.t * 0.11), -11.8 + Math.cos(a + 0.5) * 4.2);
    this.camera.lookAt(0.4, 1.9, -16);
    if (Math.random() < dt * 0.08) { UI.flash('rgba(200,210,255,0.6)'); Audio.play('thunder', 0.6); }
  }
}
