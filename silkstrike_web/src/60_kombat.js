// =====================================================================
//  Kombat: Arenen, Kämpfer, KI, Brutal-Schlag, Exekutionen
// =====================================================================
const ARENAS = {
  rainRooftop: { name: 'Dach im Regen', tod: 'stormNight', rain: true, accent: 0xff1a66, music: 'combat' },
  subway: { name: 'Station Kanalstraße', tod: 'night', rain: false, accent: 0x4dffcc, music: 'combat' },
  foundry: { name: 'Hale-Gießerei', tod: 'stormNight', rain: false, accent: 0xff7a1a, music: 'combat' },
  burningSquare: { name: 'Brennender Domplatz', tod: 'night', rain: false, accent: 0xff6a10, music: 'combat' },
  riftRealm: { name: 'Im Riss', tod: 'stormNight', rain: false, accent: 0xe02ad0, music: 'boss' },
  bloodTower: { name: 'Thron des Blutturms', tod: 'stormNight', rain: true, accent: 0xff0a14, music: 'boss' },
};

function buildArena(id, scene, anim) {
  const A = ARENAS[id];
  applyEnvironment(scene, A.tod, id === 'subway' ? 0.03 : 0.012);
  const root = new THREE.Group(); scene.add(root);
  const q = Settings.data.quality;
  const floorMat = {
    rainRooftop: new THREE.MeshStandardMaterial({ map: Tex.concrete(), roughness: 0.3, metalness: 0.15 }),
    subway: new THREE.MeshStandardMaterial({ map: Tex.tiles(), roughness: 0.3 }),
    foundry: new THREE.MeshStandardMaterial({ map: Tex.metal(), roughness: 0.5, metalness: 0.8 }),
    burningSquare: new THREE.MeshStandardMaterial({ map: Tex.brick(), roughness: 0.6 }),
    riftRealm: new THREE.MeshStandardMaterial({ color: 0x241826, roughness: 0.7, metalness: 0.1 }),
    bloodTower: new THREE.MeshStandardMaterial({ color: 0x0a0506, roughness: 0.08, metalness: 0.5 }),
  }[id];
  const floor = new MeshBuilder(); floor.box(-20, -0.4, -16, 20, 0, 8, 0.25); root.add(floor.mesh(floorMat, false));
  const m = new MeshBuilder(), g = new MeshBuilder();
  const lights = [];
  const point = (c, i0, d, x, y, z, flick) => { const i = i0 * 0.18; const l = new THREE.PointLight(c, i, d, 2); l.position.set(x, y, z); root.add(l); if (flick) anim.push(() => { l.intensity = i * (0.6 + Math.random() * 0.5); }); lights.push(l); return l; };
  if (id === 'rainRooftop') {
    root.add(buildSkyline(0xAC1D, q, A.tod, 25, -60));
    m.box(-20, 0, -10.5, 20, 1.1, -10, 0.3); m.box(-9, 0, -8, -6, 1.6, -6, 0.3); m.box(5, 0, -9, 9, 2.2, -6.5, 0.3); m.cyl(13, 2.5, -8, 2.4, 4, 16);
    for (let k = 0; k < 9; k++) g.box(-8 + k * 2, 5, -11, -6.6 + k * 2, 7.4, -10.8, 1);
    root.add(m.mesh(new THREE.MeshStandardMaterial({ map: Tex.metal(), roughness: 0.35, metalness: 0.7 })), g.mesh(glowMat(0xff1a5a, 1.3), false));
    point(0xff1a66, 40, 22, 0, 6, -9, true);
  } else if (id === 'subway') {
    scene.background = new THREE.Color(0x000000);
    m.box(-30, 0, -14, 30, 8, -13.5, 0.25); m.box(-30, 7.5, -14, 30, 8, 4, 0.25);
    for (let k = 0; k < 7; k++) m.box(-18 + k * 6 - 0.4, 0, -6, -18 + k * 6 + 0.4, 7.5, -5.2, 0.25);
    m.box(-4, -0.9, -12.3, 16, 3.2, -7.4, 0.2);
    for (let k = 0; k < 5; k++) { g.box(-2.5 + k * 3.6, 1.2, -7.38, -0.3 + k * 3.6, 2.4, -7.3, 1); }
    root.add(m.mesh(new THREE.MeshStandardMaterial({ map: Tex.tiles(), roughness: 0.35 })), g.mesh(glowMat(0xb0e6ff, 1.6), false));
    const tubes = new MeshBuilder(); for (let k = 0; k < 5; k++) { tubes.box(-14 + k * 7 - 1.2, 7.3, -3.1, -14 + k * 7 + 1.2, 7.42, -2.9, 1); point(0xc0fff0, 22, 14, -14 + k * 7, 7, -3, k % 2 === 1); }
    root.add(tubes.mesh(glowMat(0xd0fff4, 5), false));
  } else if (id === 'foundry') {
    g.box(-24, -0.3, -12, 24, 0.05, -8, 0.2);
    for (let k = 0; k < 6; k++) { m.box(-20 + k * 8 - 0.5, 0, -14, -20 + k * 8 + 0.5, 14, -13, 0.3); m.cyl(-17 + k * 8, 0, -16, 2.2, 4 + (k % 3) * 2, 14); }
    m.box(-24, 13, -14, 24, 14, 2, 0.2);
    root.add(m.mesh(new THREE.MeshStandardMaterial({ map: Tex.metal(), roughness: 0.55, metalness: 0.8 })), g.mesh(glowMat(0xff6a14, 4), false));
    for (let k = 0; k < 3; k++) point(0xff7a20, 60, 22, -12 + k * 12, 1.2, -9, true);
    anim.push(() => { if (Math.random() < 0.4) FX.emberAt(new V3(rand(-14, 14), 0.2, rand(-11, -8))); });
  } else if (id === 'burningSquare') {
    m.box(-14, 0, -26, 14, 24, -20, 0.2);
    for (const sx of [-1, 1]) { m.box(sx * 11 - 4, 0, -27, sx * 11 + 4, 46, -19, 0.2); m.cone(sx * 11, 46, -23, 5, 22, 4); }
    root.add(m.mesh(pbr(0x55504c, 0.85, 0)));
    const rose = new THREE.Mesh(new THREE.CircleGeometry(4, 24), glowMat(0xff8030, 3)); rose.position.set(0, 15, -19.9); root.add(rose);
    for (const [x, z] of [[-10, -7], [9, -8], [-3, -12], [14, -4]]) { g.box(x - 1.5, 0, z - 1, x + 1.5, 0.8, z + 1, 0.4); point(0xff7a20, 55, 16, x, 1.5, z, true); anim.push(() => { if (Math.random() < 0.5) FX.emberAt(new V3(x + rand(-1, 1), 0.9, z + rand(-0.6, 0.6))); }); }
    root.add(g.mesh(pbr(0x111111, 0.9, 0, 0x8a2004, 1)));
  } else if (id === 'riftRealm') {
    scene.background = new THREE.Color(0x0d0010);
    m.box(-11, -4, -8, 11, -0.4, 3, 0.2); m.box(-7, -8, -6, 7, -4, 1, 0.2);
    const r = seeded(0x21f7);
    for (let k = 0; k < (q === 'performance' ? 10 : 22); k++) { const c = [lerp(-60, 60, r()), lerp(-5, 30, r()), lerp(-80, -18, r())], s = lerp(1.5, 6, r()); m.box(c[0] - s, c[1] - s / 2, c[2] - s, c[0] + s, c[1] + s / 2, c[2] + s, 0.2); }
    for (let k = 0; k < 9; k++) g.box(-12 + k * 3, 0, -3 + (k % 3), -9.6 + k * 3, 0.02, -2.85 + (k % 3), 1);
    root.add(m.mesh(floorMat), g.mesh(glowMat(0xe01aa0, 4), false));
    const rift = FX.rift(0xe02ad0, 12); rift.position.set(0, 22, -60); root.add(rift); anim.push(rift.userData.anim);
    anim.push(() => { if (Math.random() < 0.5) FX.burst('ash', new V3(rand(-10, 10), 6, rand(-8, 2)), 0.05); });
  } else if (id === 'bloodTower') {
    for (let k = 0; k < 8; k++) g.box(-14 + k * 4 - 0.12, 0, -14, -14 + k * 4 + 0.12, 0.02, 3, 1);
    g.box(-20, 0, -1.2, 20, 0.02, -0.95, 1);
    for (let k = 0; k < 6; k++) { m.box(-15 + k * 6 - 0.9, 0, -10, -15 + k * 6 + 0.9, 16, -8.2, 0.2); m.cone(-15 + k * 6, 16, -9.1, 1.3, 3, 4); }
    m.box(-3, 0, -16, 3, 1.5, -12, 0.3); m.box(-1.8, 1.5, -15.8, 1.8, 3, -13.6, 0.3); m.box(-2, 1.5, -16, 2, 9, -15.4, 0.3);
    root.add(m.mesh(pbr(0x120c0c, 0.35, 0.85)), g.mesh(glowMat(0xe00410, 3), false));
    const sky = buildSkyline(0xB100D, q, A.tod, 60, -220); root.add(sky);
    const rift = FX.rift(0xff0a14, 14); rift.position.set(0, 35, -70); root.add(rift); anim.push(rift.userData.anim);
    point(0xff1010, 60, 24, -9, 5, -7, true); point(0xff1010, 60, 24, 9, 5, -7, true);
  }
  const key = new THREE.DirectionalLight(0xc8d0ff, 1.8);
  key.position.set(6, 12, 9); key.castShadow = q !== 'performance';
  key.shadow.mapSize.set(1024, 1024); const sc = key.shadow.camera; sc.left = -12; sc.right = 12; sc.top = 10; sc.bottom = -4; key.shadow.bias = -0.0006;
  scene.add(key);
  const rim1 = new THREE.SpotLight(A.accent, 28, 40, 0.7, 0.6); rim1.position.set(-7, 6, -9); rim1.target.position.set(0, 1, 0); scene.add(rim1, rim1.target);
  const rim2 = new THREE.SpotLight(A.accent, 28, 40, 0.7, 0.6); rim2.position.set(7, 6, -9); rim2.target.position.set(0, 1, 0); scene.add(rim2, rim2.target);
  scene.add(new THREE.HemisphereLight(0x606a90, 0x201014, 0.7));
  return { half: 8, camDist: 7, A };
}

// ---------------------------------------------------------------- Moves
const MOVES = {
  jab: { name: 'jab', clip: 'punch', s: 0.07, a: 0.06, r: 0.17, dmg: 45, reach: 1.3, lvl: 'high', kd: false, launch: false, lunge: 1.0 },
  cross: { name: 'cross', clip: 'punch2', s: 0.08, a: 0.07, r: 0.2, dmg: 55, reach: 1.35, lvl: 'mid', kd: false, launch: false, lunge: 1.4 },
  chainKick: { name: 'chainKick', clip: 'kick2', s: 0.12, a: 0.08, r: 0.32, dmg: 90, reach: 1.7, lvl: 'mid', kd: true, launch: false, lunge: 1.8 },
  kick: { name: 'kick', clip: 'kick', s: 0.12, a: 0.07, r: 0.26, dmg: 70, reach: 1.65, lvl: 'mid', kd: false, launch: false, lunge: 0.8 },
  roundhouse: { name: 'roundhouse', clip: 'kick2', s: 0.14, a: 0.08, r: 0.32, dmg: 85, reach: 1.75, lvl: 'high', kd: true, launch: false, lunge: 1.0 },
  kickPunch: { name: 'kickPunch', clip: 'uppercut', s: 0.1, a: 0.08, r: 0.34, dmg: 80, reach: 1.3, lvl: 'mid', kd: false, launch: true, lunge: 1.6 },
  uppercut: { name: 'uppercut', clip: 'uppercut', s: 0.1, a: 0.09, r: 0.38, dmg: 95, reach: 1.3, lvl: 'mid', kd: false, launch: true, lunge: 0.6 },
  sweep: { name: 'sweep', clip: 'sweep', s: 0.12, a: 0.08, r: 0.36, dmg: 70, reach: 1.7, lvl: 'low', kd: true, launch: false, lunge: 0.4 },
  jumpKick: { name: 'jumpKick', clip: 'jumpKick', s: 0.06, a: 0.25, r: 0.1, dmg: 75, reach: 1.5, lvl: 'overhead', kd: false, launch: false, lunge: 0 },
  jumpPunch: { name: 'jumpPunch', clip: 'punch', s: 0.05, a: 0.2, r: 0.1, dmg: 55, reach: 1.3, lvl: 'overhead', kd: false, launch: false, lunge: 0 },
  throw: { name: 'throw', clip: 'grab', s: 0.08, a: 0.06, r: 0.5, dmg: 110, reach: 1.25, lvl: 'unblockable', kd: true, launch: false, lunge: 0.4 },
};
const CHAINS = { 'jab:P': 'cross', 'cross:K': 'chainKick', 'kick:K': 'roundhouse', 'kick:P': 'kickPunch' };

class Fighter {
  constructor(id, cast, isPlayer, x) {
    this.def = ROSTER.fighters[id]; this.id = id; this.isPlayer = isPlayer;
    this.rig = new Rig(cast);
    this.x = x; this.y = 0; this.vx = 0; this.vy = 0; this.facing = x < 0 ? 1 : -1;
    this.max = this.def.stats.hp; this.hp = this.max; this.lag = this.max; this.meter = 0;
    this.state = 'idle'; this.t = 0; this.move = null; this.moveHit = false; this.connected = false;
    this.stun = 0; this.juggled = false; this.blockLow = false; this.inv = 0; this.cd = [0, 0];
    this.sp = 0; this.spStep = 0; this.spDone = false; this.counter = 0; this.comboTaken = 0; this.comboDealt = 0; this.maxCombo = 0; this.dealt = 0; this.rounds = 0;
  }
  set(s) { this.state = s; this.t = 0; }
  get grounded() { return this.y <= 0.001; }
  get down() { return this.state === 'knockdown' || this.state === 'getUp'; }
  reset(x) {
    this.x = x; this.y = 0; this.vx = 0; this.vy = 0; this.hp = this.max; this.lag = this.max; this.set('idle'); this.move = null; this.stun = 0; this.juggled = false; this.inv = 0; this.counter = 0; this.comboTaken = 0; this.comboDealt = 0; this.cd = [0, 0];
    this.rig.resetBody(); this.rig.root.visible = true; this.rig.play('fightIdle', null, true);
  }
}

class KombatAI {
  constructor(level, boss) { this.level = clamp(level, 0.2, 1.25); this.boss = boss; this.t = 0.6; this.block = 0; this.blockLow = false; this.walk = 0; this.walkT = 0; this.queue = []; this.qt = 0; }
  think(dt, me, opp, incoming) {
    const I = {};
    const dx = opp.x - me.x, dist = Math.abs(dx), tw = dx >= 0 ? 1 : -1;
    this.block -= dt; this.walkT -= dt; this.t -= dt;
    if (this.queue.length) { this.qt -= dt; if (this.qt <= 0) { const p = this.queue.shift(); this.apply(p, I, tw); this.qt = this.queue.length ? this.gap() : 0; } }
    if (this.t <= 0 && !this.queue.length) { this.t = lerp(0.5, 0.11, clamp(this.level, 0, 1.2) / 1.2) * rand(0.8, 1.3); this.decide(me, opp, dist, tw, incoming); }
    if (this.block > 0) { I.block = true; I.crouch = this.blockLow; } else if (this.walkT > 0 && !this.queue.length) I.moveX = this.walk;
    return I;
  }
  gap() { return lerp(0.24, 0.11, clamp(this.level, 0, 1.2) / 1.2); }
  apply(p, I, tw) {
    if (p === 'P') I.punch = true; else if (p === 'K') I.kick = true;
    else if (p === 'dP') { I.crouch = true; I.punch = true; } else if (p === 'dK') { I.crouch = true; I.kick = true; }
    else if (p === 'S1') I.s1 = true; else if (p === 'S2') I.s2 = true; else if (p === 'J') { I.jump = true; I.moveX = tw; }
    else if (p === 'T') { I.block = true; I.punch = true; } else if (p === 'B') I.brutal = true;
  }
  decide(me, opp, dist, tw, incoming) {
    const r = Math.random(), L = this.level, bc = clamp(0.12 + 0.62 * L, 0, 0.88);
    if ((opp.state === 'attack' || opp.state === 'special') && dist < 2.6 && r < bc) { this.block = 0.45; this.blockLow = opp.move && opp.move.lvl === 'low'; return; }
    if (incoming && r < bc) { if (Math.random() < 0.4 * L) this.queue = ['J']; else { this.block = 0.5; this.blockLow = false; } return; }
    if (opp.state === 'air' && dist < 2.6 && r < 0.75 * L) { this.queue = ['dP']; return; }
    if (me.meter >= 100 && dist < 2 && r < 0.65 * L) { this.queue = ['B']; return; }
    const sp = me.def.specials;
    if (dist > 3.2) {
      const q = Math.random();
      if (me.cd[0] <= 0 && dist < sp[0].range && q < 0.3 + 0.25 * L) this.queue = ['S1'];
      else if (me.cd[1] <= 0 && dist < sp[1].range && q < 0.25 + 0.2 * L) this.queue = ['S2'];
      else if (q < 0.12 + (this.boss ? 0.1 : 0)) this.queue = ['J', 'K'];
      else { this.walk = tw; this.walkT = 0.4; }
      return;
    }
    if (dist > 1.5) {
      const q = Math.random();
      if (q < 0.55 + (this.boss ? 0.2 : 0)) { this.walk = tw; this.walkT = 0.3; }
      else if (q < 0.7 && me.cd[1] <= 0 && dist < sp[1].range) this.queue = ['S2'];
      else if (q < 0.82) { this.walk = -tw; this.walkT = 0.25; }
      else this.queue = ['K'];
      return;
    }
    const q = Math.random(), s = clamp(L, 0, 1.2);
    if (opp.state === 'block' && q < 0.35 * s) this.queue = ['T'];
    else if (q < 0.28 + 0.2 * s) this.queue = ['P', 'P', 'K'];
    else if (q < 0.45 + 0.15 * s) this.queue = ['K', 'K'];
    else if (q < 0.58) this.queue = ['dK'];
    else if (q < 0.68) this.queue = ['dP'];
    else if (q < 0.76 && me.cd[0] <= 0) this.queue = ['S1'];
    else if (q < 0.88) { this.block = 0.35; this.blockLow = Math.random() < 0.4; }
    else { this.walk = -tw; this.walkT = 0.3; }
    this.qt = 0;
  }
}

// ---------------------------------------------------------------- Zeitstrahl für Kinosequenzen
class Timeline {
  constructor(a, v, ctl) {
    this.a = a; this.v = v; this.ctl = ctl; this.t = 0; this.cues = []; this.shots = []; this.tweens = []; this.next = 0; this.lines = [];
    this.facing = v.root.position.x >= a.root.position.x ? 1 : -1;
    const mid = a.root.position.clone().add(v.root.position).multiplyScalar(0.5);
    this.cam = { pos: mid.clone().add(new V3(0, 1.6, 6)), look: mid.clone().add(new V3(0, 1, 0)), fov: 45 };
  }
  get vp() { return this.v.root.position; }
  get ap() { return this.a.root.position; }
  cue(t, fn) { this.cues.push({ t, fn }); }
  shot(t0, t1, from, to) { this.shots.push({ t0, t1, from, to }); }
  tween(t0, t1, fn) { this.tweens.push({ t0, t1, fn }); }
  c(side, h, z, lh, fov, around) { const c = (around || this.vp).clone(); return { pos: c.clone().add(new V3(side * this.facing, h, z)), look: c.add(new V3(0, lh, 0)), fov }; }
  line(from, to, color, r = 0.02) { const w = new WebLine(color, r); w.set(from, to); this.ctl.scene.add(w.mesh); this.lines.push(w); return w; }
  clearLines() { this.lines.forEach((w) => w.mesh.parent && w.mesh.parent.remove(w.mesh)); this.lines = []; }
  sort() { this.cues.sort((x, y) => x.t - y.t); this.shots.sort((x, y) => x.t0 - y.t0); }
  advance(dt, dur) {
    this.t += dt;
    while (this.next < this.cues.length && this.cues[this.next].t <= this.t) { this.cues[this.next].fn(); this.next++; }
    for (const tw of this.tweens) if (this.t >= tw.t0) tw.fn(easeInOut((this.t - tw.t0) / Math.max(0.001, tw.t1 - tw.t0)));
    let s = null; for (const x of this.shots) if (this.t >= x.t0) s = x;
    if (s) { const k = easeInOut((this.t - s.t0) / Math.max(0.001, s.t1 - s.t0)); this.cam = { pos: s.from.pos.clone().lerp(s.to.pos, k), look: s.from.look.clone().lerp(s.to.look, k), fov: lerp(s.from.fov, s.to.fov, k) }; }
    this.a.update(dt); this.v.update(dt);
    if (this.t >= dur) { this.clearLines(); this.cues = []; this.tweens = []; return true; }
    return false;
  }
}

function buildExecution(kind, tl, ctl) {
  const a = tl.a, v = tl.v, f = tl.facing, blood = Settings.data.blood;
  const shake = (x) => ctl.shake.add(x), flash = (c) => UI.flash(c), slow = (s) => ctl.setScale(s), snd = (s, vol) => Audio.play(s, vol);
  const vp = tl.vp.clone();
  a.root.position.set(vp.x - f * 1.6, 0, 0); a.root.rotation.set(0, f > 0 ? Math.PI / 2 : -Math.PI / 2, 0);
  v.root.rotation.set(0, f > 0 ? -Math.PI / 2 : Math.PI / 2, 0);
  v.play('dizzy'); a.play('taunt', null, true);
  tl.shot(0, 1.2, tl.c(-2.4, 1.2, 4.5, 1.2, 50, tl.ap), tl.c(-1.2, 1.5, 2.6, 1.5, 38, tl.ap));
  tl.cue(0.1, () => snd('heartbeat'));
  const head = () => v.worldPos('head');
  let dur = 6.5;
  switch (kind) {
    case 'webDecapitate':
      tl.cue(1.2, () => { a.play('webShoot', null, true); snd('webShoot'); tl.line(a.worldPos('rHand'), head(), 0xffffff); tl.line(a.worldPos('lHand'), head(), 0xffffff); });
      tl.shot(1.2, 2.6, tl.c(0.6, 1.8, 2.2, 1.6, 35), tl.c(1.2, 1.4, 1.6, 1.6, 30));
      tl.cue(1.25, () => v.play('hitHigh', null, true));
      tl.cue(2.6, () => { slow(0.3); a.play('zip', null, true); snd('webZip'); });
      tl.cue(2.75, () => { tl.clearLines(); v.detach('head', new V3(-f * 7, 4, 0.6)); FX.burst('bloodBurst', head(), 1.4); FX.burst('bloodSpray', v.worldPos('neck'), 1.6, new V3(0, 1, 0)); shake(0.8); flash('#a00000'); snd('gore'); snd('boneCrack'); });
      tl.shot(2.6, 4.0, tl.c(2.5, 0.8, 3, 1.6, 42), tl.c(3.5, 2.2, 4.5, 1.0, 48));
      tl.cue(3.4, () => { slow(1); v.play('knockdown', null, true); });
      tl.cue(4.4, () => a.play('taunt', null, true));
      tl.shot(4.2, 6.5, tl.c(-1.5, 0.6, 3.2, 1.5, 40, tl.ap), tl.c(-2.5, 0.4, 4.2, 1.7, 46, tl.ap));
      break;
    case 'devour': {
      const tend = [];
      tl.cue(1.2, () => { a.play('cast', null, true); snd('roar'); for (let k = 0; k < 5; k++) tend.push(tl.line(a.worldPos('chest'), v.worldPos('chest').add(new V3(0, k * 0.2 - 0.4, 0)), 0x0c0012, 0.05)); });
      tl.tween(1.3, 3.2, (k) => v.setMaterialState('shadow', k));
      tl.shot(1.2, 3.2, tl.c(1.5, 1.2, 3, 1.2, 40), tl.c(0.6, 1.6, 1.8, 1.4, 30));
      tl.cue(1.4, () => { v.play('hitHigh', null, true); shake(0.3); });
      tl.cue(3.2, () => { slow(0.35); tl.clearLines(); const c = v.worldPos('chest'); v.detachAll(1.2); FX.burst('shadowBurst', c, 2); shake(1); flash('#4a0066'); snd('gore'); snd('explosion'); });
      tl.shot(3.2, 4.8, tl.c(3, 1.4, 4, 1, 50), tl.c(4, 3, 6, 0.4, 55));
      tl.cue(4.4, () => { slow(1); a.play('victory', null, true); });
      tl.shot(4.8, 6.5, tl.c(-1.2, 0.5, 3, 1.6, 38, tl.ap), tl.c(-1.8, 0.3, 4, 1.8, 44, tl.ap));
      break;
    }
    case 'splitInHalf':
      dur = 6;
      tl.cue(1.2, () => { a.play('cast', null, true); snd('chain'); tl.line(a.worldPos('rHand'), v.worldPos('hips'), 0x999999, 0.03); });
      tl.shot(1.2, 2.4, tl.c(0, 1, 3.5, 1, 40), tl.c(0.4, 1, 2.4, 1, 34));
      tl.cue(2.4, () => { slow(0.25); a.play('dashStrike', null, true); snd('slice'); flash('#ffffff'); tl.clearLines(); v.detach('upperBody', new V3(f * 1.5, 2.5, -0.6)); FX.burst('bloodBurst', v.worldPos('hips'), 1.6); FX.burst('bloodSpray', v.worldPos('hips'), 1.8, new V3(0, 1, 0)); shake(0.8); snd('gore'); });
      tl.shot(2.4, 4.0, tl.c(2.2, 0.6, 2.4, 1, 40), tl.c(3.4, 1.8, 4.2, 0.6, 48));
      tl.cue(3.4, () => { slow(1); v.play('kneel', null, true); });
      tl.cue(3.9, () => { FX.pool(new V3(tl.vp.x, 0.02, tl.vp.z), 1.6); snd('bodyFall'); });
      tl.cue(4.4, () => a.play('taunt', null, true));
      tl.shot(4.2, 6, tl.c(-1.4, 0.7, 3.2, 1.5, 40, tl.ap), tl.c(-2.2, 0.5, 4.2, 1.7, 46, tl.ap));
      break;
    case 'shadowSlice':
      dur = 6;
      tl.cue(1.1, () => { FX.burst('shadowBurst', tl.ap.clone().add(new V3(0, 1, 0)), 1.3); snd('teleport'); a.root.position.set(tl.vp.x + f * 1.3, 0, 0); a.root.rotation.y = f > 0 ? -Math.PI / 2 : Math.PI / 2; FX.burst('shadowBurst', tl.ap.clone().add(new V3(0, 1, 0)), 1.3); });
      tl.shot(1.1, 2.0, tl.c(-1, 1.4, 3.2, 1.3, 42), tl.c(-0.5, 1.5, 2.6, 1.4, 36));
      ['rightArm', 'leftArm', 'head'].forEach((limb, i) => {
        const t0 = 2 + i * 0.45;
        tl.cue(t0, () => { a.play(i % 2 ? 'punch2' : 'punch', null, true); flash('#9a66ff'); snd('slice'); });
        tl.cue(t0 + 0.08, () => { if (i === 2) slow(0.25); const sd = limb === 'leftArm' ? 0.8 : limb === 'rightArm' ? -0.8 : 0; v.detach(limb, new V3(-f * 2.5, 3.5, sd)); FX.burst('bloodSpray', v.worldPos(limb === 'head' ? 'neck' : 'chest'), 1.2, new V3(-f, 0.8, sd)); shake(0.5); snd('gore'); });
      });
      tl.shot(2, 3.6, tl.c(2, 1, 2.6, 1.4, 38), tl.c(2.8, 1.6, 3.6, 1.2, 44));
      tl.cue(3.8, () => { slow(1); v.play('knockdown', null, true); snd('bodyFall'); });
      tl.cue(4.3, () => { FX.pool(new V3(tl.vp.x, 0.02, 0), 1.6); a.play('crossArms', null, true); });
      tl.shot(3.8, 6, tl.c(-0.8, 0.6, 3.2, 1.6, 40, tl.ap), tl.c(-1.6, 0.4, 4, 1.7, 44, tl.ap));
      break;
    case 'headCrush':
      tl.cue(1.1, () => { a.play('grab', null, true); snd('metalHit'); });
      tl.tween(1.3, 2.3, (k) => { v.root.position.y = 0.5 * k; });
      tl.shot(1.1, 2.6, tl.c(1.6, 0.6, 2.8, 1.8, 40), tl.c(0.8, 1.4, 1.8, 2.0, 30));
      tl.cue(1.4, () => v.play('hitHigh', null, true));
      tl.tween(2.3, 3.4, (k) => v.j.head && v.j.head.scale.set(1 + 0.25 * k, 1 - 0.6 * k, 1 + 0.25 * k));
      tl.cue(2.6, () => { snd('boneCrack'); shake(0.3); });
      tl.cue(3.4, () => { slow(0.3); v.detach('head', new V3(0, -1, 0.4)); FX.burst('bloodBurst', head(), 1.8); flash('#a00000'); shake(0.9); snd('gore'); });
      tl.cue(4.1, () => { slow(1); a.play('throwToss', null, true); v.play('knockdown', null, true); });
      tl.tween(4.1, 4.7, (k) => { v.root.position.y = 0.5 * (1 - k); v.root.position.x += f * 0.08; });
      tl.cue(4.8, () => { snd('bodyFall'); FX.pool(new V3(tl.vp.x, 0.02, 0), 1.6); });
      tl.shot(3.4, 6.5, tl.c(2.5, 1.2, 3.6, 1.4, 44), tl.c(-2, 0.6, 4.4, 1.6, 46, tl.ap));
      break;
    case 'incinerate':
      dur = 7;
      tl.cue(1.1, () => { a.play('cast', null, true); snd('fire'); });
      for (let k = 0; k < 6; k++) tl.cue(1.3 + k * 0.45, () => { FX.burst('fireBurst', tl.vp.clone().add(new V3(0, 0.4 + (k % 3) * 0.5, 0)), 1.3); FX.burst('embers', tl.vp.clone().add(new V3(0, 1, 0))); snd('fire'); });
      tl.cue(1.4, () => { v.play('hitHigh', null, true); shake(0.3); });
      tl.cue(2.2, () => v.play('kneel', null, true));
      tl.tween(1.3, 4.0, (k) => v.setMaterialState('charred', k));
      tl.shot(1.1, 4, tl.c(1.8, 0.8, 3.4, 1, 44), tl.c(0.6, 1.2, 2, 1, 32));
      tl.cue(4.2, () => { slow(0.4); const c = v.worldPos('chest'); v.detachAll(0.35, false); FX.burst('ash', c, 2); FX.burst('smoke', c, 1.5); flash('#ff8020'); shake(0.6); snd('explosion'); });
      tl.shot(4.2, 5.4, tl.c(2.6, 1, 3.6, 0.6, 46), tl.c(3.2, 2.2, 5, 0.3, 52));
      tl.cue(5.2, () => { slow(1); a.play('taunt', null, true); });
      tl.shot(5.4, 7, tl.c(-1.2, 0.7, 3, 1.6, 40, tl.ap), tl.c(-2, 0.5, 4, 1.8, 46, tl.ap));
      break;
    case 'impaleBurst':
      tl.cue(1.1, () => { a.play('cast', null, true); snd('roar'); });
      tl.cue(1.6, () => {
        snd('gore'); shake(0.6); FX.burst('bloodSpray', tl.vp.clone().add(new V3(0, 0.1, 0)), 1.5, new V3(0, 1, 0));
        const sp = new THREE.Mesh(new THREE.ConeGeometry(0.16, 2.8, 8), new THREE.MeshStandardMaterial({ color: 0x500004, emissive: 0xc00008, emissiveIntensity: 1.5, roughness: 0.1 }));
        sp.position.copy(tl.vp).add(new V3(0, 1.0, 0)); ctl.scene.add(sp); setTimeout(() => sp.parent && sp.parent.remove(sp), 5000);
        v.play('hitHigh', null, true);
      });
      tl.tween(1.6, 3.0, (k) => { v.root.position.y = 1.4 * k; });
      tl.shot(1.1, 3, tl.c(1.2, 0.3, 3, 1.4, 46), tl.c(1, 0.2, 3.4, 2.6, 40));
      tl.cue(3.2, () => { slow(0.3); const c = v.worldPos('chest'); v.detachAll(1.4); FX.burst('bloodBurst', c, 2.2); FX.burst('explosion', c, 0.6); flash('#ff0010'); shake(1); snd('explosion'); snd('gore'); });
      tl.shot(3.2, 4.8, tl.c(3, 1.6, 4, 1.6, 50), tl.c(4, 3.2, 6, 0.6, 56));
      tl.cue(4.4, () => { slow(1); a.play('victory', null, true); });
      tl.shot(4.8, 6.5, tl.c(-1, 0.3, 3.4, 1.9, 40, tl.ap), tl.c(-1.8, 0.2, 4.6, 2.1, 46, tl.ap));
      break;
  }
  if (!blood) { /* FX ersetzt Blut automatisch durch Funken/Rauch */ }
  tl.sort();
  return dur;
}

// ---------------------------------------------------------------- Controller
class KombatController {
  constructor(setup) {
    this.setup = setup; // { player, cpu, arena, dark, ai, story, onEnd }
    this.scene = new THREE.Scene();
    this.camera = new THREE.PerspectiveCamera(42, innerWidth / innerHeight, 0.05, 1500);
    this.anim = [];
    FX.attach(this.scene, 0);
    this.arena = buildArena(setup.arena, this.scene, this.anim);
    this.rain = this.arena.A.rain ? new Rain(900) : null;
    if (this.rain) this.scene.add(this.rain.lines);
    const pCast = setup.dark && setup.player === 'silkstrike' ? 'darksuit' : setup.player;
    this.f = [new Fighter(setup.player, pCast, true, -2.6), new Fighter(setup.cpu, setup.cpu, false, 2.6)];
    this.f.forEach((x) => this.scene.add(x.rig.root));
    this.ai = new KombatAI(setup.ai, setup.cpu === 'malrek' || setup.cpu === 'nachtseide');
    this.shake = new Shake();
    this.proj = [];
    this.pull = new WebLine(0xffffff, 0.02); this.scene.add(this.pull.mesh); this.pullT = 0;
    this.phase = 'intro'; this.pt = 0; this.round = 1; this.timer = 90; this.tacc = 0; this.scale = 1; this.hitStop = 0;
    this.cam = { pos: new V3(-2.6, 1.4, 3.2), look: new V3(-2.6, 1.3, 0), fov: 36 };
    this.flags = new Set(); this.winner = -1; this.roundWinner = -1; this.execDone = false; this.playerExecuted = false; this.ended = false; this.time = 0; this.lastUp = false;
    UI.kombatHud(true, this.f[0].def, this.f[1].def);
    UI.kombatCinematic(true);
    Audio.setMusic(setup.cpu === 'malrek' ? 'boss' : this.arena.A.music);
    this.sync(0);
  }
  dispose() { UI.kombatHud(false); Audio.stopSpeech(); Audio.setSlow(1); }
  setScale(s) { this.scale = s; Audio.setSlow(s); }
  once(k, t) { if (this.pt >= t && !this.flags.has(k)) { this.flags.add(k); return true; } return false; }
  setPhase(p) { this.phase = p; this.pt = 0; this.flags.clear(); }
  update(rdt) {
    this.time += rdt;
    if (Input.consume('pause') && (this.phase === 'fight')) UI.pause(true);
    if (this.hitStop > 0) { this.hitStop -= rdt; this.applyCam(rdt); FX.update(rdt * 0.1); return; }
    const dt = rdt * this.scale;
    this.pt += dt;
    this.anim.forEach((a) => a(dt));
    const P = this.phase;
    if (P === 'intro') this.intro(dt);
    else if (P === 'roundIntro') this.roundIntro(dt);
    else if (P === 'fight') this.fight(dt);
    else if (P === 'brutal') this.brutalUpdate(dt);
    else if (P === 'roundOver') this.roundOver(dt);
    else if (P === 'finish') this.finishHim(dt);
    else if (P === 'exec') this.execUpdate(dt);
    else if (P === 'outro') this.outro(dt);
    if (P !== 'exec' && P !== 'brutal') { this.sync(dt); if (P !== 'intro' && P !== 'outro') this.fightCam(dt); }
    this.applyCam(rdt);
    FX.update(dt, this.camera);
    if (this.rain) this.rain.update(rdt, this.camera);
    this.hud();
  }
  intro() {
    const [p1, p2] = this.f;
    if (this.once('a', 0.05)) { Audio.speak(p1.def.intro, p1.id); p1.rig.play('taunt', null, true); }
    if (this.once('b', 2.4)) { Audio.speak(p2.def.intro, p2.id); p2.rig.play('taunt', null, true); }
    const foc = this.pt < 2.4 ? p1 : p2, loc = this.pt < 2.4 ? this.pt / 2.4 : (this.pt - 2.4) / 2.4, side = foc === p1 ? -1 : 1;
    const ang = lerp(-0.5, 0.35, loc) * side, tgt = new V3(foc.x, 1.3, 0), rad = lerp(3.4, 2.6, loc);
    this.cam.pos.set(tgt.x + Math.sin(ang) * rad, 1.4 + loc * 0.3, Math.cos(ang) * rad); this.cam.look.copy(tgt); this.cam.fov = 36;
    if (Input.consume('skip') || this.pt > 4.8) { Audio.stopSpeech(); this.startRound(); }
  }
  startRound() {
    this.f[0].reset(-2.6); this.f[1].reset(2.6); this.f[0].facing = 1; this.f[1].facing = -1;
    this.timer = this.setup.seconds || 90; this.tacc = 0; this.roundWinner = -1;
    this.proj.forEach((p) => this.scene.remove(p.mesh)); this.proj = [];
    UI.kombatCinematic(false); this.setScale(1); this.setPhase('roundIntro');
  }
  roundIntro() {
    if (this.once('r', 0.1)) { UI.banner('RUNDE ' + this.round, 'round', 1.3); Audio.announce('Runde ' + ['eins', 'zwei', 'drei', 'vier', 'fünf'][Math.min(4, this.round - 1)]); }
    if (this.once('f', 1.5)) { UI.banner('KÄMPFT!', 'fight', 0.9); Audio.announce('Kämpft!'); Haptic(30); }
    if (this.pt > 2.2) { UI.kombatControls(true); this.setPhase('fight'); }
  }
  readPlayer() {
    const m = Input.move, up = m.y > 0.6;
    const I = { moveX: Math.abs(m.x) > 0.25 ? m.x : 0, crouch: m.y < -0.55, jump: up && !this.lastUp, block: Input.isDown('block'),
      punch: Input.consume('punch'), kick: Input.consume('kick'), s1: Input.consume('special1'), s2: Input.consume('special2'), brutal: Input.consume('brutal') };
    this.lastUp = up;
    return I;
  }
  fight(dt) {
    this.tacc += dt; if (this.tacc >= 1) { this.tacc -= 1; this.timer = Math.max(0, this.timer - 1); }
    const pI = this.readPlayer();
    const aI = this.ai.think(dt, this.f[1], this.f[0], this.proj.some((p) => p.owner === 0));
    this.step(0, pI, dt); if (this.phase !== 'fight') return;
    this.step(1, aI, dt); if (this.phase !== 'fight') return;
    this.updateProj(dt); this.separate();
    if (this.pullT > 0) { this.pullT -= dt; if (this.pullT <= 0) this.pull.hide(); }
    const [p1, p2] = this.f;
    if (p1.hp <= 0 || p2.hp <= 0 || this.timer <= 0) {
      let w;
      if (p1.hp <= 0 && p2.hp <= 0) w = 0; else if (p1.hp <= 0) w = 1; else if (p2.hp <= 0) w = 0; else w = p1.hp / p1.max >= p2.hp / p2.max ? 0 : 1;
      this.endRound(w, this.timer <= 0 && p1.hp > 0 && p2.hp > 0);
    }
  }
  endRound(w, timeout) {
    this.roundWinner = w; const W = this.f[w], Lr = this.f[1 - w];
    W.rounds++; UI.kombatControls(false);
    Lr.hp = Math.max(0, Lr.hp); this.setScale(0.3); this.shake.add(0.6); UI.flash('#ffffff');
    if (!timeout) { Lr.set('knockdown'); Lr.rig.play('knockdown', null, true); Lr.vx = W.facing * 3; Audio.play('punchHeavy'); Audio.play('boneCrack'); }
    if (W.rounds >= (this.setup.toWin || 2)) this.winner = w;
    this.setPhase('roundOver');
  }
  roundOver(dt) {
    const W = this.f[this.roundWinner], Lr = this.f[1 - this.roundWinner];
    this.body(Lr, dt);
    if (this.once('s', 0.6)) this.setScale(1);
    if (this.once('b', 0.7) && this.winner < 0) { UI.banner(W.def.name.toUpperCase() + ' GEWINNT DIE RUNDE', 'info', 1.8); W.rig.play('taunt', null, true); }
    if (this.pt > 2.6) {
      if (this.winner >= 0) {
        Lr.set('dizzy'); Lr.y = 0; Lr.vx = 0; Lr.hp = 1; Lr.rig.resetBody(); Lr.rig.play('getUp', null, true); W.set('idle');
        UI.banner('VOLLENDE ES!', 'finish', 2.2); Audio.announce('Vollende es!'); Audio.setMusic('tension'); Haptic(60);
        if (W.isPlayer) { UI.executePrompt(true); UI.kombatControls(true); }
        this.setPhase('finish');
      } else { this.round++; this.startRound(); }
    }
  }
  finishHim(dt) {
    const W = this.f[this.winner], Lr = this.f[1 - this.winner];
    if (Lr.rig.clip !== 'dizzy' && Lr.rig.finished) Lr.rig.play('dizzy');
    const left = Math.max(0, 6 - this.pt);
    if (W.isPlayer) {
      UI.executeTime(left / 6);
      const I = this.readPlayer();
      if (Math.abs(I.moveX) > 0.2) { W.vx = I.moveX * W.def.stats.walk; W.rig.play(I.moveX * W.facing > 0 ? 'walkForward' : 'walkBack'); } else { W.vx = 0; if (W.rig.clip !== 'fightIdle') W.rig.play('fightIdle'); }
      W.x = clamp(W.x + W.vx * dt, -this.arena.half, this.arena.half);
      if (Input.consume('execute')) { this.startExec(this.winner); return; }
      if (left <= 0) { UI.executePrompt(false); Lr.set('knockdown'); Lr.rig.play('knockdown', null, true); Audio.play('bodyFall'); this.startOutro(); }
    } else if (this.pt > 1.8) this.startExec(this.winner);
  }
  startExec(w) {
    const A = this.f[w], Vv = this.f[1 - w];
    UI.executePrompt(false); UI.kombatControls(false); UI.kombatCinematic(true);
    let kind = A.def.exec.kind;
    if (A.isPlayer && this.setup.dark && A.id === 'silkstrike') kind = 'devour';
    this.tl = new Timeline(A.rig, Vv.rig, this);
    this.execDur = buildExecution(kind, this.tl, this);
    A.set('cinematic'); Vv.set('cinematic');
    if (A.isPlayer) this.execDone = true; else this.playerExecuted = true;
    Audio.setMusic('none');
    this.setPhase('exec');
  }
  execUpdate(dt) {
    const fin = this.tl.advance(dt, this.execDur);
    this.cam.pos.copy(this.tl.cam.pos); this.cam.look.copy(this.tl.cam.look); this.cam.fov = this.tl.cam.fov;
    if (fin) {
      this.setScale(1); this.f.forEach((x) => { x.x = x.rig.root.position.x; });
      const A = this.f[this.winner];
      UI.banner(A.def.exec.name.toUpperCase(), 'execution', 2.6); Audio.announce('Exekution!'); Haptic(80);
      this.startOutro();
    }
  }
  startOutro() {
    UI.kombatCinematic(true); UI.kombatControls(false);
    const W = this.f[this.winner];
    W.set('victory'); W.rig.play('victory', null, true);
    Audio.setMusic(W.isPlayer ? 'victory' : 'sad');
    this.setPhase('outro');
  }
  outro() {
    const W = this.f[this.winner];
    if (this.once('b', 2.4)) { UI.banner(W.isPlayer ? W.def.name.toUpperCase() + ' SIEGT' : 'NIEDERLAGE', W.isPlayer ? 'victory' : 'defeat', 3); Audio.announce(W.def.name + ' siegt'); }
    if (this.once('q', 3.6)) Audio.speak(W.def.win, W.id);
    const ang = 0.4 + this.pt * 0.12, tgt = new V3(W.x, 1.2, 0);
    this.cam.pos.set(tgt.x + Math.sin(ang) * 3.2 * -W.facing, 1.6, Math.cos(ang) * 3.2); this.cam.look.copy(tgt).add(new V3(0, 0.2, 0)); this.cam.fov = 38;
    if (this.pt > 7.5 || (this.pt > 3 && Input.consume('skip'))) this.finishMatch();
  }
  finishMatch() {
    if (this.ended) return; this.ended = true; Audio.stopSpeech();
    const [p1, p2] = this.f;
    const res = { won: this.winner === 0, exec: this.execDone, executed: this.playerExecuted, rw: p1.rounds, rl: p2.rounds, combo: p1.maxCombo, dmg: Math.round(p1.dealt), secs: Math.round(this.time) };
    if (this.setup.onEnd) this.setup.onEnd(res);
  }
  // ---- Brutal-Schlag
  tryBrutal(i) {
    const A = this.f[i], Vv = this.f[1 - i];
    if (A.meter < 100 || Math.abs(Vv.x - A.x) > 2.4 || Vv.down || !Vv.grounded) return false;
    A.meter = 0; this.bi = i; A.set('cinematic'); Vv.set('cinematic');
    UI.kombatCinematic(true); UI.kombatControls(false); UI.banner(A.def.brutal, 'brutal', 1.6);
    const tl = new Timeline(A.rig, Vv.rig, this), f = tl.facing;
    A.rig.root.position.x = Vv.rig.root.position.x - f * 1.25;
    tl.shot(0, 0.5, tl.c(-1.2, 1.4, 2.6, 1.4, 40, tl.ap), tl.c(-0.6, 1.5, 1.8, 1.5, 30, tl.ap));
    tl.cue(0, () => { this.setScale(0.4); UI.flash(A.def.look.glow); Audio.play('whoosh'); });
    const clips = ['punch', 'kick2', 'uppercut'], parts = [70, 80, 130];
    for (let k = 0; k < 3; k++) {
      const t0 = 0.5 + k * 0.8;
      tl.cue(t0, () => A.rig.play(clips[k], null, true));
      tl.cue(t0 + 0.22, () => {
        UI.flash('#ffffff'); this.shake.add(k === 2 ? 1 : 0.55);
        Vv.rig.play(k === 2 ? 'knockdown' : 'hitHigh', null, true); Vv.rig.setMaterialState('frozen', 0.65);
        Audio.play(k === 0 ? 'punchHeavy' : 'boneCrack'); Audio.play('gore', 0.7);
        FX.burst('bloodSpray', Vv.rig.worldPos(k === 1 ? 'hips' : 'head'), 1.1, new V3(f, 0.6, 0)); Haptic(50);
        const dmg = parts[k] * A.def.stats.power / Math.max(0.3, Vv.def.stats.defense);
        Vv.hp = Math.max(1, Vv.hp - dmg); A.dealt += dmg; A.comboDealt++; A.maxCombo = Math.max(A.maxCombo, A.comboDealt);
      });
      tl.cue(t0 + 0.55, () => Vv.rig.setMaterialState('normal', 0));
      const sd = k % 2 ? -1 : 1;
      tl.shot(t0, t0 + 0.8, tl.c(sd, 1.3, 1.6, k === 1 ? 0.9 : 1.6, 28), tl.c(sd * 1.4, 1.2, 2, k === 1 ? 0.9 : 1.5, 34));
    }
    tl.cue(2.9, () => this.setScale(1));
    tl.shot(2.9, 3.4, tl.c(0, 1.6, 5, 1, 45), tl.c(0, 1.6, 6, 1, 48));
    tl.sort();
    this.tl = tl; this.setPhase('brutal');
    return true;
  }
  brutalUpdate(dt) {
    const fin = this.tl.advance(dt, 3.4);
    this.cam.pos.copy(this.tl.cam.pos); this.cam.look.copy(this.tl.cam.look); this.cam.fov = this.tl.cam.fov;
    if (fin) {
      this.setScale(1);
      const A = this.f[this.bi], Vv = this.f[1 - this.bi];
      A.x = A.rig.root.position.x; Vv.x = Vv.rig.root.position.x;
      A.set('idle'); Vv.set('knockdown'); Vv.rig.play('lieDown');
      UI.kombatCinematic(false); UI.kombatControls(true); this.setPhase('fight');
    }
  }
  // ---- Kämpferlogik
  step(i, I, dt) {
    const f = this.f[i], o = this.f[1 - i];
    f.t += dt; f.inv -= dt; f.counter -= dt; f.cd[0] -= dt; f.cd[1] -= dt;
    f.lag = f.lag > f.hp ? Math.max(f.hp, f.lag - f.max * 0.35 * dt) : f.hp;
    switch (f.state) {
      case 'idle': case 'walk': case 'crouch': case 'block':
        if (f.comboTaken) f.comboTaken = 0;
        f.facing = o.x >= f.x ? 1 : -1;
        if (I.brutal && this.tryBrutal(i)) return;
        if (I.jump) { f.set('air'); f.vy = f.def.stats.jump; f.vx = (I.moveX || 0) * 3.6; f.move = null; f.rig.play('jump', null, true); Audio.play('whoosh', 0.4); }
        else if (I.s1 && f.cd[0] <= 0) this.special(f, 0);
        else if (I.s2 && f.cd[1] <= 0) this.special(f, 1);
        else if (I.punch) { if (I.block && Math.abs(o.x - f.x) < 1.5) this.startMove(f, MOVES.throw); else this.startMove(f, I.crouch ? MOVES.uppercut : MOVES.jab); }
        else if (I.kick) this.startMove(f, I.crouch ? MOVES.sweep : MOVES.kick);
        else if (I.block) { if (f.state !== 'block') f.set('block'); f.blockLow = !!I.crouch; f.vx = 0; }
        else if (I.crouch) { if (f.state !== 'crouch') f.set('crouch'); f.vx = 0; }
        else if (Math.abs(I.moveX || 0) > 0.1) { if (f.state !== 'walk') f.set('walk'); const back = I.moveX * f.facing < 0; f.vx = I.moveX * f.def.stats.walk * (back ? 0.8 : 1); }
        else { if (f.state !== 'idle') f.set('idle'); f.vx = 0; }
        break;
      case 'air':
        f.vy -= 22 * dt;
        if (!f.move && (I.kick || I.punch)) { const m = I.kick ? MOVES.jumpKick : MOVES.jumpPunch; f.move = m; f.moveHit = false; f.t = 0; f.rig.play(m.clip, m.s + m.a + m.r, true); Audio.play('whoosh', 0.5); }
        if (f.move && !f.moveHit && f.t >= f.move.s && f.t < f.move.s + f.move.a) this.tryHit(i, f.move);
        if (f.y <= 0 && f.vy <= 0) { f.y = 0; f.vy = 0; f.move = null; f.set('idle'); f.rig.play('land', null, true); FX.burst('dust', new V3(f.x, 0.02, 0), 0.5); }
        break;
      case 'attack': {
        const m = f.move; if (!m) { f.set('idle'); break; }
        const t = f.t, tot = m.s + m.a + m.r;
        if (t < m.s + m.a) f.vx = f.facing * m.lunge; else f.vx *= 0.8;
        if (!f.moveHit && t >= m.s && t < m.s + m.a) this.tryHit(i, m);
        if (f.connected && t >= m.s && t < tot - 0.03 && (I.punch || I.kick)) { const n = CHAINS[m.name + ':' + (I.punch ? 'P' : 'K')]; if (n) { this.startMove(f, MOVES[n]); return; } }
        if (t >= tot) { f.move = null; f.set('idle'); }
        break;
      }
      case 'special': this.updateSpecial(i, dt); break;
      case 'hitstun': case 'blockstun':
        f.stun -= dt;
        if (f.juggled || !f.grounded) { f.vy -= 22 * dt; if (f.y <= 0 && f.vy <= 0) { f.y = 0; f.vy = 0; f.juggled = false; f.set('knockdown'); f.rig.play('knockdown', null, true); FX.burst('dust', new V3(f.x, 0.02, 0), 0.8); Audio.play('bodyFall'); this.shake.add(0.25); } }
        else if (f.stun <= 0) f.set('idle');
        f.vx *= Math.max(0, 1 - 5 * dt);
        break;
      case 'knockdown':
        f.vx *= Math.max(0, 1 - 6 * dt);
        if (f.t > 0.5 && f.rig.clip !== 'lieDown' && f.rig.finished) f.rig.play('lieDown');
        if (f.t > 1) { f.set('getUp'); f.inv = 0.7; f.rig.play('getUp', null, true); }
        break;
      case 'getUp': if (f.t > 0.6) f.set('idle'); break;
      default: break;
    }
    this.body(f, dt);
  }
  body(f, dt) {
    if (f.y > 0 || f.juggled) { if (f.state !== 'air' && f.state !== 'hitstun' && f.state !== 'blockstun') f.vy -= 22 * dt; f.y = Math.max(0, f.y + f.vy * dt); }
    else if (f.state === 'air') f.y = Math.max(0, f.y + f.vy * dt);
    if (f.state === 'air') { /* y wird oben integriert */ }
    f.x = clamp(f.x + f.vx * dt, -this.arena.half, this.arena.half);
  }
  separate() {
    const [a, b] = this.f, dx = b.x - a.x;
    if (Math.abs(dx) < 0.75 && Math.abs(a.y - b.y) < 1.2) { const p = (0.75 - Math.abs(dx)) / 2, s = dx >= 0 ? 1 : -1; a.x = clamp(a.x - s * p, -this.arena.half, this.arena.half); b.x = clamp(b.x + s * p, -this.arena.half, this.arena.half); }
  }
  startMove(f, m) { f.set('attack'); f.move = m; f.moveHit = false; f.connected = false; f.rig.play(m.clip, m.s + m.a + m.r, true); Audio.play('whoosh', 0.45, rand(0.9, 1.15)); }
  tryHit(i, m) {
    const a = this.f[i], d = this.f[1 - i], dx = d.x - a.x;
    if (Math.abs(dx) > m.reach + 0.3) return;
    if (Math.abs(dx) > 0.25 && Math.sign(dx) !== a.facing) return;
    if (d.inv > 0 || d.down || d.state === 'cinematic' || d.state === 'dizzy') return;
    if (m.lvl === 'low' && d.y > 0.4) return;
    if (d.y - a.y > 1.6) return;
    if (m.lvl === 'high' && d.state === 'crouch') return;
    if (m.lvl === 'unblockable' && (!d.grounded || d.state === 'attack')) return;
    a.moveHit = true; a.connected = true;
    if (d.counter > 0 && m.lvl !== 'unblockable') { d.counter = 0; this.combo(d, 'KONTER!'); this.hit(1 - i, 90, true, false, 'unblockable'); d.rig.play('uppercut', null, true); return; }
    this.hit(i, m.dmg, m.kd, m.launch, m.lvl);
    if (m.name === 'throw' && d.state !== 'idle') { d.x = clamp(a.x - a.facing * 1.2, -this.arena.half, this.arena.half); a.rig.play('throwToss', null, true); FX.burst('dust', new V3(d.x, 0.05, 0), 1.2); }
  }
  hit(i, base, kd, launch, lvl) {
    const a = this.f[i], d = this.f[1 - i];
    const hp = new V3(d.x - a.facing * 0.15, d.y + (lvl === 'low' ? 0.4 : 1.35), 0);
    const blocking = d.state === 'block' || d.state === 'blockstun';
    let blocked = false;
    if (blocking) blocked = lvl === 'high' || lvl === 'mid' ? true : lvl === 'low' ? d.blockLow : lvl === 'overhead' ? !d.blockLow : false;
    if (blocked) {
      d.hp = Math.max(1, d.hp - base * 0.12 * a.def.stats.power / Math.max(0.3, d.def.stats.defense));
      d.set('blockstun'); d.stun = 0.16 + base / 900; d.vx = a.facing * 3.2; d.rig.flashHit(0x99ccff);
      FX.burst('sparks', hp, 0.7, new V3(-a.facing, 0.3, 0.5)); Audio.play('block'); a.meter = Math.min(100, a.meter + 2); d.meter = Math.min(100, d.meter + 4); this.hitStop = 0.04;
      if (a.isPlayer || d.isPlayer) Haptic(8);
      return;
    }
    d.comboTaken++; a.comboDealt = d.comboTaken; a.maxCombo = Math.max(a.maxCombo, a.comboDealt);
    const sc = Math.max(0.4, 1 - 0.08 * (d.comboTaken - 1));
    const dmg = base * a.def.stats.power / Math.max(0.3, d.def.stats.defense) * sc;
    d.hp = Math.max(0, d.hp - dmg); a.dealt += dmg; a.meter = Math.min(100, a.meter + dmg * 0.07); d.meter = Math.min(100, d.meter + dmg * 0.05);
    d.move = null; d.rig.flashHit();
    if (launch || (!d.grounded && d.state !== 'knockdown')) { d.set('hitstun'); d.juggled = true; d.vy = launch ? 8.5 : Math.max(d.vy, 5); d.y = Math.max(d.y, 0.05); d.vx = a.facing * 1.6; d.rig.play('hitHigh', null, true); }
    else if (kd) { d.set('hitstun'); d.juggled = true; d.vy = 4.5; d.y = 0.05; d.vx = a.facing * 4.5; d.rig.play('knockdown', null, true); }
    else { d.set('hitstun'); d.stun = 0.3 + base / 450; d.vx = a.facing * 2.6; d.rig.play(lvl === 'low' ? 'hitLow' : 'hitHigh', null, true); }
    const heavy = base >= 80;
    FX.burst('hitFlash', hp, heavy ? 1.3 : 0.8); FX.burst('bloodSpray', hp, heavy ? 1.1 : 0.7, new V3(a.facing, 0.5, 0.3));
    if (heavy && Math.random() < 0.5) FX.pool(new V3(d.x, 0.02, rand(-0.4, 0.4)), 0.6);
    this.hitStop = heavy ? 0.11 : 0.06; this.shake.add(heavy ? 0.45 : 0.22);
    Audio.play(heavy ? 'punchHeavy' : 'punchLight'); if (heavy) Audio.play('boneCrack', 0.6);
    if (a.isPlayer || d.isPlayer) Haptic(heavy ? 35 : 15);
    if (d.comboTaken >= 2) { const w = ['', '', '', 'BRUTAL!', 'GNADENLOS!', 'BLUTRAUSCH!', 'UNAUFHALTSAM!', 'VERNICHTEND!'][d.comboTaken] || 'LEGENDÄR!'; this.combo(a, d.comboTaken + ' TREFFER' + (w ? '  ' + w : '')); }
  }
  combo(f, text) { if (f.isPlayer) UI.combo(text); }
  special(f, k) {
    const s = f.def.specials[k];
    f.cd[k] = s.cooldown; f.set('special'); f.sp = k; f.spDone = false; f.spStep = 0; f.vx = 0;
    if (s.kind === 'dashStrike') f.rig.play('dashStrike', 0.6, true);
    else if (s.kind === 'grabSlam') f.rig.play('grab', 0.5, true);
    else if (s.kind === 'counter') { f.rig.play('block', null, true); f.counter = 0.7; }
    else f.rig.play('cast', 0.45, true);
    Audio.play(s.sound);
    if (f.isPlayer) Haptic(10);
  }
  updateSpecial(i) {
    const f = this.f[i], o = this.f[1 - i], s = f.def.specials[f.sp], t = f.t, dist = Math.abs(o.x - f.x), H = this.arena.half;
    const fin = (e) => { if (t >= e) { f.rig.root.visible = true; f.set('idle'); } };
    switch (s.kind) {
      case 'projectile': if (!f.spStep && t >= 0.18) { f.spStep = 1; this.spawnProj(i, s, false); } fin(0.5); break;
      case 'groundWave': if (!f.spStep && t >= 0.2) { f.spStep = 1; this.spawnProj(i, s, true); this.shake.add(0.2); } fin(0.55); break;
      case 'dashStrike':
        if (t >= 0.12 && t < 0.42) { f.vx = f.facing * 14; if (!f.spDone && dist < 1.4 && (o.x - f.x) * f.facing > -0.2) { f.spDone = true; f.vx = 0; this.hit(i, s.damage, true, false, 'mid'); } } else f.vx *= 0.7;
        fin(0.65); break;
      case 'teleportStrike':
        if (f.spStep === 0 && t >= 0.15) { f.spStep = 1; FX.burst('shadowBurst', new V3(f.x, 1, 0), 1, undefined, s.color); f.rig.root.visible = false; }
        if (f.spStep === 1 && t >= 0.35) { f.spStep = 2; const side = f.x < o.x ? 1 : -1; f.x = clamp(o.x + side, -H, H); f.facing = o.x >= f.x ? 1 : -1; f.rig.root.visible = true; FX.burst('shadowBurst', new V3(f.x, 1, 0), 1, undefined, s.color); Audio.play('teleport'); f.rig.play('uppercut', 0.35, true); }
        if (f.spStep === 2 && t >= 0.42 && !f.spDone) { f.spDone = true; if (Math.abs(o.x - f.x) < 1.7 && !o.down && o.state !== 'cinematic') this.hit(i, s.damage, false, true, 'overhead'); }
        fin(0.8); break;
      case 'grabSlam':
        if (!f.spDone && t >= 0.15) { f.spDone = true; if (dist < Math.min(s.range, 2.2) && o.grounded && !o.down && o.state !== 'cinematic') { o.x = clamp(f.x + f.facing * 0.9, -H, H); f.rig.play('throwToss', 0.5, true); this.hit(i, s.damage, true, false, 'unblockable'); FX.burst('dust', new V3(o.x, 0.05, 0), 1.5); this.shake.add(0.6); Audio.play('bodyFall'); } }
        fin(0.85); break;
      case 'pullIn':
        if (!f.spStep && t >= 0.15) {
          f.spStep = 1; const hand = f.rig.worldPos('rHand'); this.pull.mesh.material.color.set(s.color);
          if (dist < s.range && !o.down && o.state !== 'cinematic') {
            this.pull.set(hand, o.rig.worldPos('chest')); this.pullT = 0.35;
            if (o.state === 'block') { FX.burst('sparks', new V3(o.x, 1.2, 0)); Audio.play('block'); }
            else { o.x = clamp(f.x + f.facing * 1.1, -H, H); this.hit(i, s.damage, false, false, 'mid'); o.stun = 0.75; }
          } else { this.pull.set(hand, hand.clone().add(new V3(f.facing * s.range, 0.2, 0))); this.pullT = 0.2; }
        }
        fin(0.55); break;
      default: fin(0.75);
    }
  }
  spawnProj(i, s, low) {
    const f = this.f[i];
    const mesh = new THREE.Mesh(new THREE.SphereGeometry(low ? 0.35 : 0.22, 14, 10), new THREE.MeshBasicMaterial({ color: s.color }));
    if (low) mesh.scale.set(1.6, 0.6, 1.2);
    const y = low ? 0.2 : 1.3;
    const p = { mesh, owner: i, x: f.x + f.facing * 0.8, y, vx: f.facing * (low ? 10 : 13), dmg: s.damage, low, life: 2.2, alive: true, color: s.color };
    mesh.position.set(p.x, y, 0); this.scene.add(mesh); this.proj.push(p);
  }
  updateProj(dt) {
    for (const p of this.proj) {
      if (!p.alive) continue;
      p.x += p.vx * dt; p.life -= dt; p.mesh.position.set(p.x, p.y, 0);
      if (Math.random() < 0.6) FX.spray(FX.add, p.mesh.position, 2, 0.6, new V3(-Math.sign(p.vx), 0, 0), 0.5, p.color, 0.1, 0.3, 0, 2);
      const t = this.f[1 - p.owner];
      if (Math.abs(t.x - p.x) < 0.55 && !t.down && t.state !== 'cinematic' && t.inv <= 0 && !(p.low ? t.y > 0.3 : t.y > 1.6)) {
        p.alive = false; const a = this.f[p.owner], sf = a.facing; a.facing = p.vx >= 0 ? 1 : -1;
        this.hit(p.owner, p.dmg, p.low, false, p.low ? 'low' : 'mid'); a.facing = sf;
        FX.burst('explosion', p.mesh.position.clone(), 0.4);
      }
      if (Math.abs(p.x) > this.arena.half + 4 || p.life <= 0) p.alive = false;
    }
    const live = this.proj.filter((p) => p.alive);
    for (let a = 0; a < live.length; a++) for (let b = a + 1; b < live.length; b++) if (live[a].owner !== live[b].owner && Math.abs(live[a].x - live[b].x) < 0.6) { live[a].alive = live[b].alive = false; FX.burst('explosion', new V3((live[a].x + live[b].x) / 2, 1.2, 0), 0.6); Audio.play('explosion', 0.7); this.shake.add(0.3); }
    for (const p of this.proj) if (!p.alive) this.scene.remove(p.mesh);
    this.proj = this.proj.filter((p) => p.alive);
  }
  sync(dt) {
    for (const f of this.f) {
      if (f.state === 'cinematic') { f.rig.update(dt); continue; }
      f.rig.root.position.set(f.x, f.y, 0);
      f.rig.root.rotation.set(0, f.facing > 0 ? Math.PI / 2 : -Math.PI / 2, 0);
      const c = f.rig.clip, R = f.rig;
      if (f.state === 'idle') { const busy = ['punch', 'punch2', 'kick', 'kick2', 'uppercut', 'sweep', 'land', 'getUp', 'cast', 'grab', 'throwToss', 'dashStrike', 'taunt'].includes(c) && !R.finished; if (!busy && c !== 'fightIdle') R.play('fightIdle', null, false, 0.12); }
      else if (f.state === 'walk') { const w = f.vx * f.facing >= 0 ? 'walkForward' : 'walkBack'; if (c !== w) R.play(w, null, false, 0.1); }
      else if (f.state === 'crouch') { if (c !== 'crouch') R.play('crouch', null, false, 0.08); }
      else if (f.state === 'block') { if (c !== 'block') R.play('block', null, false, 0.06); }
      else if (f.state === 'air') { if (!f.move && f.vy < 0 && c !== 'fall' && (c !== 'jump' || R.finished)) R.play('fall', null, false, 0.15); }
      else if (f.state === 'dizzy') { if (c !== 'dizzy' && (c !== 'getUp' || R.finished)) R.play('dizzy'); }
      R.update(dt);
    }
  }
  fightCam(dt) {
    const [a, b] = this.f, mid = (a.x + b.x) / 2, span = Math.abs(a.x - b.x), my = Math.max(a.y, b.y);
    const portrait = innerHeight > innerWidth;
    const tp = new V3(mid, 1.55 + span * 0.04 + my * 0.3, this.arena.camDist + Math.max(0, span - 3) * 0.5 + (portrait ? 4 : 0));
    this.cam.pos.lerp(tp, 1 - Math.exp(-6 * dt)); this.cam.look.lerp(new V3(mid, 1.1 + my * 0.35, 0), 1 - Math.exp(-7 * dt)); this.cam.fov = damp(this.cam.fov, 42, 4, dt);
  }
  applyCam(dt) {
    const s = this.shake.update(dt);
    this.camera.position.copy(this.cam.pos).add(new V3(s.x, s.y, 0));
    this.camera.up.set(Math.sin(s.roll), 1, 0);
    this.camera.lookAt(this.cam.look);
    this.camera.fov = this.cam.fov; this.camera.updateProjectionMatrix();
  }
  hud() {
    const [a, b] = this.f;
    UI.kombatUpdate({ h1: a.hp / a.max, h2: b.hp / b.max, l1: a.lag / a.max, l2: b.lag / b.max, m1: a.meter / 100, m2: b.meter / 100, r1: a.rounds, r2: b.rounds, toWin: this.setup.toWin || 2,
      timer: this.timer, s1: a.cd[0] <= 0, s2: a.cd[1] <= 0, brutal: this.phase === 'fight' && a.meter >= 100 });
  }
}
