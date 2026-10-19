// =====================================================================
//  Offene Welt: Schwingen, Wandlauf, Netz-Zip, Kultisten, Ziele, Blutsiegel
// =====================================================================
// Goldene Stunde: warmer Himmel mit tiefer Sonne (u/v passend zu sunDir), eigene Umgebungs-Map
const GOLDEN_SUN = new V3(0.55, 0.24, -0.8).normalize();
let goldenEnv = null;
function goldenSky() {
  return canvasTex('skyGolden', 1024, 512, (g, w, h) => {
    const grd = g.createLinearGradient(0, 0, 0, h);
    grd.addColorStop(0, '#2f4f7e'); grd.addColorStop(0.25, '#6b86a8'); grd.addColorStop(0.4, '#d6a682'); grd.addColorStop(0.47, '#ffc583');
    grd.addColorStop(0.5, '#ffd9a0'); grd.addColorStop(0.53, '#a9775a'); grd.addColorStop(1, '#2e2420');
    g.fillStyle = grd; g.fillRect(0, 0, w, h);
    const su = (Math.atan2(GOLDEN_SUN.z, GOLDEN_SUN.x) / TAU + 0.5) * w, sv = (0.5 - Math.asin(GOLDEN_SUN.y) / Math.PI) * h;
    for (const off of [-w, 0, w]) {
      g.save(); g.translate(su + off, sv); g.scale(2.2, 1);
      const sg = g.createRadialGradient(0, 0, 0, 0, 0, h * 0.42);
      sg.addColorStop(0, 'rgba(255,240,200,1)'); sg.addColorStop(0.08, 'rgba(255,215,150,0.9)'); sg.addColorStop(0.35, 'rgba(255,170,100,0.45)'); sg.addColorStop(1, 'rgba(255,140,80,0)');
      g.fillStyle = sg; g.fillRect(-h, -h, h * 2, h * 2); g.restore();
    }
    const r = seeded(31);
    for (let i = 0; i < 46; i++) { // flache, sonnenbeschienene Wolkenbänder
      const x = r() * w, y = h * (0.18 + r() * 0.26), s = 30 + r() * 110;
      g.save(); g.translate(x, y); g.scale(3.5, 0.5);
      const cg = g.createRadialGradient(0, 0, 0, 0, 0, s);
      cg.addColorStop(0, `rgba(255,${190 + Math.floor(r() * 40)},${150 + Math.floor(r() * 40)},${0.18 + r() * 0.2})`); cg.addColorStop(1, 'rgba(255,200,160,0)');
      g.fillStyle = cg; g.fillRect(-s, -s, s * 2, s * 2); g.restore();
    }
  }, false);
}
class WorldController {
  constructor(opts) {
    this.opts = opts; // { chapter, dark, onObjective }
    const ch = opts.chapter;
    this.tod = ch ? ch.tod : 'dusk'; // freies Schwingen = goldene Stunde
    this.golden = this.tod === 'dusk';
    const G = this.golden, q = Settings.data.quality;
    this.scene = new THREE.Scene();
    this.camera = new THREE.PerspectiveCamera(62, innerWidth / innerHeight, 0.15, 2600);
    applyEnvironment(this.scene, this.tod, G ? 0.0019 : 0.0016);
    // goldene Stunde: echtes Sonnenuntergangs-HDRI (schon durch applyEnvironment gesetzt), sonst gemalter Himmel
    if (G && !EnvHDR.get('dusk')) {
      const sky = goldenSky(); sky.mapping = THREE.EquirectangularReflectionMapping;
      if (!goldenEnv) goldenEnv = pmrem.fromEquirectangular(sky).texture;
      this.scene.background = sky; this.scene.environment = goldenEnv; this.scene.environmentIntensity = 0.75;
      if (this.scene.fog) this.scene.fog.color.set(0xd2a07c); // warmer Dunst zum Horizont
    }
    FX.attach(this.scene, 0);
    this.city = new City(this.tod, q);
    this.scene.add(this.city.root);
    this.city.setTower(ch && ch.objective === 'bloodTower');
    // Sonne: tief und warm (goldene Stunde), Schattenkamera folgt dem Helden
    this.sunDir = G ? GOLDEN_SUN.clone() : new V3(40, 80, 30).normalize();
    const key = new THREE.DirectionalLight(G ? 0xffb06a : 0x9fb0ff, G ? 3.4 : 0.9);
    key.position.copy(this.sunDir).multiplyScalar(220); key.castShadow = q !== 'performance';
    key.shadow.mapSize.set(q === 'ultra' ? 2048 : 1024, q === 'ultra' ? 2048 : 1024);
    const ext = q === 'ultra' ? 70 : 55;
    const sc = key.shadow.camera; sc.left = -ext; sc.right = ext; sc.top = ext; sc.bottom = -ext; sc.near = 1; sc.far = 520; key.shadow.bias = -0.0006; key.shadow.normalBias = 0.04;
    this.scene.add(key, key.target); this.key = key;
    this.scene.add(G ? new THREE.HemisphereLight(0x9db4d6, 0x5a3a26, 0.85) : new THREE.HemisphereLight(0x5a6688, 0x1a1012, 0.6));
    this.sun = null;
    if (G) { // bloom-taugliche Sonnenscheibe mit Halo
      const tex = canvasTex('sunDisc', 128, 128, (g2, w, h) => {
        const gr = g2.createRadialGradient(64, 64, 0, 64, 64, 64);
        gr.addColorStop(0, 'rgba(255,255,255,1)'); gr.addColorStop(0.1, 'rgba(255,248,230,1)'); gr.addColorStop(0.16, 'rgba(255,210,150,0.5)');
        gr.addColorStop(0.4, 'rgba(255,160,90,0.14)'); gr.addColorStop(1, 'rgba(255,120,60,0)');
        g2.fillStyle = gr; g2.fillRect(0, 0, w, h);
      }, false);
      this.sun = new THREE.Sprite(new THREE.SpriteMaterial({ map: tex, color: new THREE.Color(1, 0.82, 0.58).multiplyScalar(5), blending: THREE.AdditiveBlending, depthWrite: false, fog: false, transparent: true }));
      this.sun.scale.setScalar(560); this.scene.add(this.sun);
    }
    this.hero = new Rig(opts.dark ? 'darksuit' : 'silkstrike');
    this.scene.add(this.hero.root);
    this.web = new WebLine(0xf4f6ff, 0.018); this.scene.add(this.web.mesh);
    this.shake = new Shake();
    this.rain = this.tod === 'stormNight' ? new Rain() : null;
    if (this.rain) this.scene.add(this.rain.lines);
    this.pos = new V3(); this.vel = new V3(); this.yaw = 0; this.state = 'air'; this.health = 1;
    this.anchor = new V3(); this.rope = 20; this.wallN = new V3(); this.zipT = new V3();
    this.camYaw = 0; this.camPitch = 0.25; this.camPos = new V3(); this.camLook = new V3(); this.fov = 62; this.lookIdle = 10;
    this.hitStop = 0; this.attackCd = 0; this.combo = 0; this.comboT = 0; this.flip = false; this.lastHurt = 9; this.defeated = false;
    this.thugs = []; this.spawnT = 2; this.usedSpawn = new Set();
    this.objective = null; this.objectiveFired = false;
    if (ch) {
      const p = this.city.landmarks[ch.objective];
      const g = new THREE.Group();
      const rift = FX.rift(0xff1030, 1.8); rift.position.y = 2.6; g.add(rift); this.city.anim.push(rift.userData.anim);
      const beam = new THREE.Mesh(new THREE.CylinderGeometry(0.9, 0.9, 400, 12, 1, true), new THREE.MeshBasicMaterial({ color: 0xff1030, transparent: true, opacity: 0.28, blending: THREE.AdditiveBlending, depthWrite: false }));
      beam.position.y = 200; g.add(beam);
      g.position.copy(p); this.scene.add(g); this.objective = p; this.objRift = rift;
    }
    this.crystals = [];
    const cg = new THREE.OctahedronGeometry(0.45), cm = new THREE.MeshStandardMaterial({ color: 0x600008, emissive: 0xff1030, emissiveIntensity: 2.6, roughness: 0.15, metalness: 0.3 });
    this.city.collect.forEach((p, i) => { if (Progress.seals.includes(i)) return; const m = new THREE.Mesh(cg, cm); m.position.copy(p); this.scene.add(m); this.crystals.push({ m, i }); });
    this.respawn();
    UI.worldHud(true);
    UI.setObjective(ch ? ch.objectiveText : 'Freies Schwingen – sammle Blutsiegel und stoppe die Kultisten');
    if (ch) UI.toast((ch.number === 0 ? 'PROLOG' : 'KAPITEL ' + ch.number) + ' · ' + ch.title.toUpperCase());
    Audio.setMusic('roam');
  }
  respawn() {
    const sp = this.city.landmarks.heroApartment;
    this.pos.copy(sp).add(new V3(0, 0.2, 0)); this.vel.set(0, 0, 0); this.state = 'air'; this.health = 1; this.defeated = false;
    if (this.objective) this.yaw = yawOf(this.objective.x - this.pos.x, this.objective.z - this.pos.z);
    this.camYaw = this.yaw; this.camPitch = 0.25;
    this.camPos.copy(this.pos).add(new V3(-Math.sin(this.yaw) * 6, 3, -Math.cos(this.yaw) * 6));
    this.web.hide();
  }
  dispose() { UI.worldHud(false); Audio.stopSpeech(); }
  camForward() { return new V3(Math.sin(this.camYaw), 0, Math.cos(this.camYaw)); }
  moveDir() { const f = this.camForward(); const r = new V3(-f.z, 0, f.x); return r.multiplyScalar(Input.move.x).add(f.multiplyScalar(Input.move.y)); }
  update(dt) {
    if (this.hitStop > 0) { this.hitStop -= dt; this.render(dt * 0.05); return; }
    this.input();
    this.simulate(dt);
    this.combat(dt);
    this.render(dt);
    this.objectiveCheck();
    this.crystalCheck();
    this.city.update(dt);
    FX.update(dt, this.camera);
    if (this.rain) this.rain.update(dt, this.camera);
    this.hud();
  }
  input() {
    if (Input.consume('jump')) {
      if (this.state === 'ground') { this.vel.y = 13; this.state = 'air'; this.hero.play('jump', null, true); Audio.play('whoosh', 0.5); }
      else if (this.state === 'swing') { this.release(true); this.vel.y += 7; this.hero.play('jump', null, true); }
      else if (this.state === 'wall') { this.vel.copy(this.wallN).multiplyScalar(12).add(new V3(0, 11, 0)); this.state = 'air'; this.hero.play('jump', null, true); Audio.play('whoosh', 0.6); }
    }
    if (Input.consume('web') && this.state !== 'swing') this.startSwing();
    if (this.state === 'swing' && !Input.isDown('web')) this.release(true);
    if (Input.consume('zip')) this.startZip();
    if (Input.consume('attack')) this.attack();
    if (Input.consume('interact') && this.objective && this.pos.distanceTo(this.objective) < 14) this.fireObjective();
    if (Input.consume('pause')) UI.pause(true);
  }
  startSwing() {
    const a = this.city.anchor(this.pos.clone().add(new V3(0, 1.5, 0)), this.vel, this.camForward());
    if (!a) { Audio.play('ui', 0.4); return; }
    this.anchor.copy(a); this.rope = Math.max(8, a.distanceTo(this.pos) * 0.92); this.state = 'swing';
    this.hero.play('swing'); Audio.play('webShoot'); Haptic(10);
    if (this.vel.y < -4) this.vel.y *= 0.6;
  }
  release(boost) {
    if (this.state !== 'swing') return;
    this.state = 'air'; this.web.hide();
    if (boost) { const h = new V3(this.vel.x, 0, this.vel.z); if (h.lengthSq() > 0.01) h.normalize(); else h.copy(this.camForward()); this.vel.addScaledVector(h, 4).add(new V3(0, 5, 0)); }
    Audio.play('whoosh', 0.7);
    this.hero.play(this.vel.y > 0 ? 'jump' : 'fall', null, true);
  }
  startZip() {
    const dir = new V3().subVectors(this.camLook, this.camera.position).normalize();
    const hit = this.city.raycast(this.camera.position.clone(), dir, 140);
    if (!hit || hit.distanceTo(this.pos) < 4) return;
    if (this.state === 'swing') this.release(false);
    this.zipT.copy(hit); this.state = 'zip'; this.hero.play('zip', null, true); Audio.play('webZip'); this.fov += 8; Haptic(15);
  }
  simulate(dt) {
    const dir = this.moveDir(), g = -24, m = Math.hypot(Input.move.x, Input.move.y);
    if (this.state === 'ground') {
      const sp = m > 0.92 ? 15 : 9;
      this.vel.x = damp(this.vel.x, dir.x * sp, 10, dt); this.vel.z = damp(this.vel.z, dir.z * sp, 10, dt); this.vel.y = 0;
      if (m > 0.1) this.yaw = dampAngle(this.yaw, yawOf(dir.x, dir.z), 12, dt);
    } else if (this.state === 'air') {
      this.vel.y += g * dt; this.vel.addScaledVector(dir, 9 * dt);
      if (Math.hypot(this.vel.x, this.vel.z) > 1) this.yaw = dampAngle(this.yaw, yawOf(this.vel.x, this.vel.z), 4, dt);
    } else if (this.state === 'swing') {
      this.vel.y += g * dt; this.vel.addScaledVector(dir, 13 * dt).addScaledVector(this.camForward(), 4 * dt);
      this.rope = Math.max(8, this.rope - 1.5 * dt);
      if (Math.hypot(this.vel.x, this.vel.z) > 1) this.yaw = dampAngle(this.yaw, yawOf(this.vel.x, this.vel.z), 6, dt);
    } else if (this.state === 'wall') {
      const up = Input.move.y < -0.5 ? -4 : 11;
      const lat = dir.clone().addScaledVector(this.wallN, -dir.dot(this.wallN));
      this.vel.set(lat.x * 6, up, lat.z * 6).addScaledVector(this.wallN, -2);
      this.yaw = yawOf(-this.wallN.x, -this.wallN.z);
    } else if (this.state === 'zip') {
      const to = this.zipT.clone().sub(this.pos), d = to.length();
      if (d < 1.6) this.arriveZip(); else this.vel.copy(to.multiplyScalar(48 / d));
    }
    const sp = this.vel.length(); if (sp > 58) this.vel.multiplyScalar(58 / sp);
    const steps = Math.max(1, Math.min(8, Math.ceil(sp * dt / 0.45))), h = dt / steps;
    let ground = false, wall = false; const wn = new V3(); const fall = this.vel.y;
    for (let k = 0; k < steps; k++) {
      this.pos.addScaledVector(this.vel, h);
      if (this.state === 'swing') {
        const d = this.pos.clone().sub(this.anchor), len = d.length();
        if (len > this.rope && len > 0.001) { d.divideScalar(len); this.pos.copy(this.anchor).addScaledVector(d, this.rope); const vr = this.vel.dot(d); if (vr > 0) this.vel.addScaledVector(d, -vr); }
      }
      const info = this.city.collide(this.pos, this.vel, 0.45, 1.8);
      if (info.ground) ground = true;
      if (info.wall) { wall = true; wn.copy(info.n); }
    }
    if (this.state === 'air' || this.state === 'swing') {
      if (ground && this.vel.y <= 0.1) {
        if (this.state === 'swing') this.release(false);
        const hard = fall < -18;
        this.state = 'ground'; this.hero.play(hard ? 'land' : 'idle', null, true);
        if (hard) { FX.burst('dust', this.pos, 1.2); this.shake.add(0.35); Audio.play('land'); Haptic(20); }
      } else if (wall) {
        const hv = new V3(this.vel.x, 0, this.vel.z); if (hv.lengthSq() > 0.01) hv.normalize();
        if (hv.dot(wn.clone().negate()) > 0.3 || dir.dot(wn.clone().negate()) > 0.3) { if (this.state === 'swing') this.release(false); this.state = 'wall'; this.wallN.copy(wn); this.hero.play('wallRun'); }
      }
      if (this.state === 'swing' && this.pos.y > this.anchor.y - 1.5) this.release(true);
    } else if (this.state === 'wall') {
      const probe = this.pos.clone().addScaledVector(this.wallN, -0.25), pv = new V3();
      const info = this.city.collide(probe, pv, 0.45, 1.8);
      if (!info.wall || info.roof) { this.vel.copy(this.wallN).multiplyScalar(-5).add(new V3(0, 8, 0)); this.state = 'air'; this.hero.play('jump', null, true); }
      else if (ground && Input.move.y < -0.5) this.state = 'ground';
    } else if (this.state === 'ground' && !ground) {
      if (this.pos.y - this.city.surface(this.pos) > 0.35) { this.state = 'air'; this.hero.play('fall'); }
    }
    if (this.pos.y < -5 || !isFinite(this.pos.x)) this.respawn();
  }
  arriveZip() {
    this.web.hide();
    const top = this.city.surface(this.zipT.clone().add(new V3(0, 3, 0)));
    if (Math.abs(top - this.zipT.y) < 2.5) { this.pos.y = top; this.vel.set(0, 0, 0); this.state = 'ground'; this.hero.play('land', null, true); }
    else { const d = new V3(this.zipT.x - this.pos.x, 0, this.zipT.z - this.pos.z).normalize(); this.vel.copy(d.multiplyScalar(16)).add(new V3(0, 11, 0)); this.state = 'air'; this.hero.play('jump', null, true); }
    Audio.play('land', 0.5);
  }
  // ---- Kampf gegen Kultisten -----------------------------------------
  nearestThug(max) { let b = null, bd = max; for (const t of this.thugs) if (t.alive) { const d = t.pos.distanceTo(this.pos); if (d < bd) { bd = d; b = t; } } return b; }
  attack() {
    if (this.attackCd > 0) return;
    this.attackCd = 0.28;
    let t = this.nearestThug(7);
    if (t) {
      const to = t.pos.clone().sub(this.pos); to.y = 0; const d = to.length(); to.normalize();
      this.yaw = yawOf(to.x, to.z);
      if (d > 1.4) this.pos.addScaledVector(to, Math.min(d - 1.2, 4));
      this.combo++; this.comboT = 1.6; const heavy = this.combo % 4 === 0; this.flip = !this.flip;
      this.hero.play(heavy ? 'uppercut' : (this.flip ? 'punch' : 'kick'), null, true);
      const down = this.hitThug(t, heavy ? 55 : 32, to, heavy);
      this.hitStop = heavy || down ? 0.09 : 0.05; this.shake.add(heavy ? 0.4 : 0.2);
      Audio.play(heavy ? 'punchHeavy' : (this.flip ? 'punchLight' : 'kick')); if (heavy) Audio.play('boneCrack', 0.7);
      Haptic(heavy ? 30 : 12);
    } else if ((t = this.nearestThug(22))) {
      this.hero.play('webShoot', null, true);
      this.web.set(this.hero.worldPos('rHand'), t.pos.clone().add(new V3(0, 1.2, 0))); this.webFlash = 0.15;
      FX.burst('webHit', t.pos.clone().add(new V3(0, 1.2, 0)));
      this.hitThug(t, 20, this.pos.clone().sub(t.pos).normalize(), false);
      Audio.play('webShoot'); this.combo++; this.comboT = 1.6;
    } else { this.flip = !this.flip; this.hero.play(this.flip ? 'punch' : 'kick', null, true); Audio.play('whoosh', 0.5); }
  }
  hitThug(t, dmg, dir, heavy) {
    if (!t.alive) return false;
    t.hp -= dmg; t.rig.flashHit();
    t.vel.copy(dir).setY(0).normalize().multiplyScalar(heavy ? 9 : 4); t.vel.y = heavy ? 5 : 0;
    const chest = t.pos.clone().add(new V3(0, 1.3, 0));
    FX.burst('hitFlash', chest, heavy ? 1.2 : 0.8); FX.burst('bloodSpray', chest, heavy ? 1 : 0.6, dir.clone().add(new V3(0, 0.4, 0)));
    if (t.hp <= 0) { t.alive = false; t.state = 'down'; t.down = 0; t.rig.play('knockdown', null, true); FX.pool(new V3(t.pos.x, t.pos.y + 0.02, t.pos.z)); Audio.play('bodyFall'); return true; }
    t.state = 'stagger'; t.timer = heavy ? 0.7 : 0.4; t.rig.play('hitHigh', null, true);
    return false;
  }
  combat(dt) {
    this.attackCd -= dt; this.comboT -= dt; if (this.comboT <= 0) this.combo = 0; this.lastHurt += dt;
    if (this.webFlash > 0) { this.webFlash -= dt; if (this.webFlash <= 0 && this.state !== 'swing' && this.state !== 'zip') this.web.hide(); }
    this.spawnT -= dt;
    if (this.spawnT <= 0) { this.spawnT = 6; this.spawnGroup(); }
    let dmg = 0;
    for (const t of this.thugs) {
      t.timer -= dt; t.cd -= dt;
      const to = this.pos.clone().sub(t.pos), dist = Math.hypot(to.x, to.z), dir = new V3(to.x, 0, to.z).normalize();
      if (t.state === 'approach') {
        if (dist < 40 && Math.abs(to.y) < 4) {
          t.yaw = dampAngle(t.yaw, yawOf(dir.x, dir.z), 8, dt);
          if (dist > 1.6) { t.vel.x = dir.x * 4.2; t.vel.z = dir.z * 4.2; if (t.rig.clip !== 'run') t.rig.play('run'); }
          else { t.vel.x = t.vel.z = 0; if (t.rig.clip !== 'fightIdle') t.rig.play('fightIdle'); if (t.cd <= 0) { t.state = 'windup'; t.timer = 0.45; t.rig.play('taunt', 0.45, true); t.rig.flashHit(0xff3010); } }
        } else { t.vel.x = t.vel.z = 0; if (t.rig.clip !== 'lookAround') t.rig.play('lookAround'); }
      } else if (t.state === 'windup') { t.vel.x = t.vel.z = 0; if (t.timer <= 0) { t.state = 'strike'; t.timer = 0.3; t.rig.play('punch', null, true); Audio.play('whoosh', 0.6); if (dist < 2.2 && Math.abs(to.y) < 2) dmg += (this.state === 'swing' || this.state === 'zip') ? 0.02 : 0.08; } }
      else if (t.state === 'strike') { if (t.timer <= 0) { t.state = 'approach'; t.cd = rand(1.2, 2.4); } }
      else if (t.state === 'stagger') { if (t.timer <= 0) t.state = 'approach'; }
      else if (t.state === 'down') { t.down += dt; if (t.down > 0.8 && t.rig.clip !== 'lieDown') t.rig.play('lieDown'); }
      t.vel.y -= 24 * dt;
      if (t.state === 'stagger' || t.state === 'down') { t.vel.x *= Math.max(0, 1 - 4 * dt); t.vel.z *= Math.max(0, 1 - 4 * dt); }
      t.pos.addScaledVector(t.vel, dt);
      this.city.collide(t.pos, t.vel, 0.4, 1.8);
      t.rig.root.position.copy(t.pos); t.rig.root.rotation.y = t.yaw; t.rig.update(dt);
    }
    for (let i = this.thugs.length - 1; i >= 0; i--) { const t = this.thugs[i]; if (t.state === 'down' && t.down > 10) { this.scene.remove(t.rig.root); this.thugs.splice(i, 1); } }
    if (dmg > 0) { this.health -= dmg; this.lastHurt = 0; this.hero.flashHit(0xff3030); this.shake.add(0.3); Audio.play('punchHeavy'); Haptic(30); FX.burst('bloodSpray', this.pos.clone().add(new V3(0, 1.4, 0)), 0.5); }
    else if (this.lastHurt > 4) this.health = Math.min(1, this.health + dt * 0.05);
    if (this.health <= 0 && !this.defeated) { this.defeated = true; this.health = 0; this.hero.play('knockdown', null, true); UI.toast('Niedergeschlagen – zurück aufs Dach'); setTimeout(() => { if (Game.active === this) this.respawn(); }, 1600); }
  }
  spawnGroup() {
    if (this.thugs.filter((t) => t.alive).length >= (Settings.data.quality === 'performance' ? 4 : 7)) return;
    let bi = -1, bd = 150;
    this.city.spawns.forEach((p, i) => { if (this.usedSpawn.has(i)) return; const d = p.distanceTo(this.pos); if (d > 25 && d < bd) { bd = d; bi = i; } });
    if (bi < 0) { if (this.usedSpawn.size >= this.city.spawns.length) this.usedSpawn.clear(); return; }
    this.usedSpawn.add(bi);
    const c = this.city.spawns[bi], n = 3 + Math.floor(Math.random() * 2);
    for (let k = 0; k < n; k++) {
      const a = k / n * TAU, p = c.clone().add(new V3(Math.cos(a) * 2.5, 0, Math.sin(a) * 2.5));
      const rig = new Rig('cultist'); rig.root.position.copy(p); rig.play('lookAround'); this.scene.add(rig.root);
      this.thugs.push({ rig, pos: p, vel: new V3(), yaw: 0, hp: 100, state: 'approach', timer: 0, cd: rand(0.5, 2), down: 0, alive: true });
    }
  }
  // ---- Darstellung ----------------------------------------------------
  render(dt) {
    const H = this.hero;
    H.root.position.copy(this.pos);
    if (this.state === 'swing') {
      const up = this.anchor.clone().sub(this.pos).normalize();
      const tilt = new THREE.Quaternion().setFromUnitVectors(new V3(0, 1, 0), new V3(0, 1, 0).multiplyScalar(0.35).add(up.multiplyScalar(0.65)).normalize());
      H.root.quaternion.copy(tilt).multiply(new THREE.Quaternion().setFromAxisAngle(new V3(0, 1, 0), this.yaw));
      this.web.set(H.worldPos('rHand'), this.anchor);
    } else if (this.state === 'zip') {
      H.root.quaternion.setFromAxisAngle(new V3(0, 1, 0), yawOf(this.zipT.x - this.pos.x, this.zipT.z - this.pos.z));
      this.web.set(H.worldPos('rHand'), this.zipT);
    } else H.root.quaternion.setFromAxisAngle(new V3(0, 1, 0), this.yaw);
    const hs = Math.hypot(this.vel.x, this.vel.z);
    const one = ['jump', 'land', 'punch', 'kick', 'uppercut', 'webShoot', 'zip', 'hitHigh', 'knockdown'].includes(H.clip) && !H.finished;
    if (this.state === 'ground' && !one) { const w = hs < 0.6 ? (this.nearestThug(8) ? 'fightIdle' : 'idle') : (hs < 11 ? 'run' : 'sprint'); if (H.clip !== w) H.play(w, null, false, 0.15); }
    else if (this.state === 'air' && !one) { const w = this.vel.y < -16 ? 'dive' : 'fall'; if (H.clip !== w) H.play(w, null, false, 0.2); }
    else if (this.state === 'swing' && H.clip !== 'swing') H.play('swing');
    else if (this.state === 'wall' && H.clip !== 'wallRun') H.play('wallRun');
    H.update(dt);
    // Kamera
    const look = Input.takeLook(), k = 0.005 * Settings.data.sens;
    if (look.x || look.y) { this.camYaw = wrapAngle(this.camYaw - look.x * k); this.camPitch = clamp(this.camPitch + look.y * k * 0.8, -0.5, 1.2); this.lookIdle = 0; }
    else this.lookIdle += dt;
    if (this.lookIdle > 1.5 && hs > 3) this.camYaw = dampAngle(this.camYaw, yawOf(this.vel.x, this.vel.z), (this.state === 'swing' ? 2.4 : 1.4) * clamp((hs - 3) / 10, 0, 1), dt);
    if (this.state === 'wall' && this.lookIdle > 0.6) this.camYaw = dampAngle(this.camYaw, this.yaw, 3, dt);
    const speed = this.vel.length();
    let dist = this.state === 'swing' ? 7 + clamp(speed / 40, 0, 1) * 2.4 : this.state === 'ground' ? 5.2 : 6.4;
    const target = this.pos.clone().add(new V3(0, 1.5, 0));
    const dir = new V3(Math.sin(this.camYaw) * Math.cos(this.camPitch), -Math.sin(this.camPitch), Math.cos(this.camYaw) * Math.cos(this.camPitch));
    const hit = this.city.raycast(target, dir.clone().negate(), dist + 0.6);
    if (hit) dist = Math.max(1.2, hit.distanceTo(target) - 0.5);
    const want = target.clone().addScaledVector(dir, -dist);
    this.camPos.lerp(want, 1 - Math.exp(-12 * dt));
    this.camLook.copy(target).addScaledVector(dir, 4);
    const sh = this.shake.update(dt);
    this.camera.position.copy(this.camPos).add(new V3(sh.x, sh.y, 0));
    this.camera.up.set(Math.sin(sh.roll), 1, 0);
    this.camera.lookAt(this.camLook);
    const wantFov = 60 + clamp(speed / 45, 0, 1) * 20;
    this.fov = damp(this.fov, wantFov, 4, dt);
    this.camera.fov = this.fov; this.camera.updateProjectionMatrix();
    this.key.position.copy(this.pos).addScaledVector(this.sunDir, 220); this.key.target.position.copy(this.pos);
    if (this.sun) this.sun.position.copy(this.camera.position).addScaledVector(this.sunDir, 1900);
    for (const c of this.crystals) c.m.rotation.y += dt * 2.4;
  }
  objectiveCheck() {
    if (!this.objective) return;
    const d = this.pos.distanceTo(this.objective);
    if (d < 4) this.fireObjective();
    Audio.setMusic(d < 120 ? 'tension' : 'roam');
  }
  fireObjective() {
    if (this.objectiveFired) return;
    this.objectiveFired = true; Audio.play('riftHum'); Haptic(40);
    if (this.opts.onObjective) this.opts.onObjective();
  }
  crystalCheck() {
    const p = this.pos.clone().add(new V3(0, 1, 0));
    for (let i = this.crystals.length - 1; i >= 0; i--) {
      const c = this.crystals[i];
      if (c.m.position.distanceTo(p) < 2.6) {
        Progress.seals.push(c.i); Progress.save();
        FX.burst('shadowBurst', c.m.position, 1, undefined, 0xff1030); this.scene.remove(c.m); this.crystals.splice(i, 1);
        Audio.play('uiConfirm'); Haptic(20);
        UI.toast('Blutsiegel ' + Progress.seals.length + '/' + this.city.collect.length);
      }
    }
  }
  hud() {
    const s = this.city.size;
    const info = { health: this.health, speed: Math.round(this.vel.length() * 3.6), seals: Progress.seals.length, sealsTotal: this.city.collect.length, combo: this.combo, swinging: this.state === 'swing',
      hero: [clamp(this.pos.x / s + 0.5, 0, 1), clamp(this.pos.z / s + 0.5, 0, 1)], heading: this.yaw };
    if (this.objective) {
      info.dist = Math.round(this.pos.distanceTo(this.objective));
      info.arrow = wrapAngle(this.camYaw - yawOf(this.objective.x - this.pos.x, this.objective.z - this.pos.z));
      info.obj = [clamp(this.objective.x / s + 0.5, 0, 1), clamp(this.objective.z / s + 0.5, 0, 1)];
      info.prompt = info.dist < 14;
    }
    UI.worldUpdate(info);
  }
}
