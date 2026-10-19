// =====================================================================
//  Kombat: Arenen, Kämpfer, KI, Brutal-Schlag, Exekutionen
// =====================================================================
// Laufzeit-Patch (64_roster.js ist generiert): der Endgegner im Sturm-Turm erhält das Donnergericht
if (ROSTER.fighters.malrek) ROSTER.fighters.malrek.exec = Object.assign({}, ROSTER.fighters.malrek.exec, { kind: 'thunderJudgement', name: 'Donnergericht' });
const ARENAS = {
  rainRooftop: { name: 'Dach im Regen', tod: 'stormNight', rain: true, accent: 0xff1a66, music: 'combat' },
  subway: { name: 'Station Kanalstraße', tod: 'night', rain: false, accent: 0x4dffcc, music: 'combat' },
  foundry: { name: 'Hale-Gießerei', tod: 'stormNight', rain: false, accent: 0xff7a1a, music: 'combat' },
  burningSquare: { name: 'Brennender Domplatz', tod: 'night', rain: false, accent: 0xff6a10, music: 'combat' },
  riftRealm: { name: 'Im Riss', tod: 'stormNight', rain: false, accent: 0xe02ad0, music: 'boss' },
  bloodTower: { name: 'Thron des Blutturms', tod: 'stormNight', rain: true, accent: 0xff0a14, music: 'boss' },
  templeGarden: { name: 'Kirschblütentempel', tod: 'day', rain: false, accent: 0xffb48c, music: 'combat' },
};

// Kirschblütentempel: prozedurale Texturen (Pflaster mit Blüten, Ziegel, Stein, Gras, Laub, Bergkulisse)
function templeTex(kind) {
  const wrapDraw = (w, h, x, y, m, fn) => { for (const ox of [-w, 0, w]) for (const oy of [-h, 0, h]) { const px = x + ox, py = y + oy; if (px > -m && px < w + m && py > -m && py < h + m) fn(px, py); } };
  const petal = (g, x, y, rx, ry, a, col) => { g.save(); g.translate(x, y); g.rotate(a); g.fillStyle = col; g.beginPath(); g.ellipse(0, 0, rx, ry, 0, 0, TAU); g.fill(); g.fillStyle = 'rgba(255,255,255,0.25)'; g.beginPath(); g.ellipse(-rx * 0.25, -ry * 0.2, rx * 0.45, ry * 0.4, 0, 0, TAU); g.fill(); g.restore(); };
  const PINK = ['#f8b6cc', '#f3a2bf', '#fbd3e1', '#ea8db1', '#fde4ec'];
  if (kind === 'pavers') return canvasTex('tgPavers', 512, 512, (g, w, h) => {
    const r = seeded(0x7e3a);
    g.fillStyle = '#4e4b40'; g.fillRect(0, 0, w, h);
    for (let row = 0; row < 4; row++) {
      let x = r() * 120; const y = row * 128, end = x + w;
      while (x < end - 40) {
        const pw = Math.min(end - x, 100 + r() * 110), v = 128 + r() * 46, tint = r() * 10;
        wrapDraw(w, h, x, y, 260, (px, py) => {
          g.fillStyle = `rgb(${v + 8 + tint},${v * 0.95 + 4},${v * 0.84 - tint})`; g.fillRect(px + 3, py + 3, pw - 6, 122);
          g.fillStyle = 'rgba(255,255,240,0.14)'; g.fillRect(px + 3, py + 3, pw - 6, 3); g.fillRect(px + 3, py + 3, 3, 122);
          g.fillStyle = 'rgba(0,0,0,0.22)'; g.fillRect(px + 3, py + 121, pw - 6, 4); g.fillRect(px + pw - 6, py + 3, 3, 122);
        });
        x += pw;
      }
    }
    for (let i = 0; i < 5000; i++) { const v = Math.floor(r() * 255); g.fillStyle = `rgba(${v},${v},${v * 0.9},${0.12 * r()})`; const s = 1 + r() * 3; g.fillRect(r() * w, r() * h, s, s); }
    g.strokeStyle = 'rgba(30,25,20,0.45)'; g.lineWidth = 1.2;
    for (let i = 0; i < 9; i++) { g.beginPath(); let x = r() * w, y = r() * h; g.moveTo(x, y); for (let k = 0; k < 7; k++) { x += (r() - 0.5) * 30; y += (r() - 0.5) * 30; g.lineTo(x, y); } g.stroke(); }
    for (let i = 0; i < 26; i++) { const x = r() * w, y = r() * h, s = 10 + r() * 30; wrapDraw(w, h, x, y, 40, (px, py) => { const mg = g.createRadialGradient(px, py, 0, px, py, s); mg.addColorStop(0, 'rgba(70,88,40,0.22)'); mg.addColorStop(1, 'rgba(70,88,40,0)'); g.fillStyle = mg; g.fillRect(px - s, py - s, s * 2, s * 2); }); }
    const cl = []; for (let i = 0; i < 10; i++) cl.push([r() * w, r() * h]);
    for (let i = 0; i < 340; i++) {
      const c = cl[i % cl.length], u = i < 220;
      const x = u ? c[0] + (r() + r() + r() - 1.5) * 60 : r() * w, y = u ? c[1] + (r() + r() + r() - 1.5) * 60 : r() * h;
      const rx = 3 + r() * 2.5, ry = 2 + r() * 1.5, a = r() * TAU, col = PINK[Math.floor(r() * PINK.length)];
      wrapDraw(w, h, ((x % w) + w) % w, ((y % h) + h) % h, 8, (px, py) => petal(g, px, py, rx, ry, a, col));
    }
  });
  if (kind === 'roof') return canvasTex('tgRoof', 256, 256, (g, w, h) => {
    const r = seeded(0x2f00f);
    g.fillStyle = '#1d5a4e'; g.fillRect(0, 0, w, h);
    for (let x = 0; x < w; x += 16) { const gr = g.createLinearGradient(x, 0, x + 16, 0); gr.addColorStop(0, '#123d35'); gr.addColorStop(0.4, '#4aa58e'); gr.addColorStop(0.55, '#3a917c'); gr.addColorStop(1, '#0f342d'); g.fillStyle = gr; g.fillRect(x, 0, 16, h); }
    for (let y = 0; y < h; y += 32) { const gr = g.createLinearGradient(0, y, 0, y + 32); gr.addColorStop(0, 'rgba(0,0,0,0.4)'); gr.addColorStop(0.2, 'rgba(0,0,0,0)'); gr.addColorStop(0.85, 'rgba(255,255,255,0.08)'); gr.addColorStop(1, 'rgba(0,0,0,0.25)'); g.fillStyle = gr; g.fillRect(0, y, w, 32); }
    for (let i = 0; i < 1500; i++) { g.fillStyle = r() < 0.5 ? `rgba(20,30,25,${r() * 0.25})` : `rgba(180,210,190,${r() * 0.12})`; g.fillRect(r() * w, r() * h, 1 + r() * 3, 1 + r() * 3); }
  });
  if (kind === 'stone') return canvasTex('tgStone', 256, 256, (g, w, h) => {
    noiseFill(g, w, h, '#a29c90', 0.22, 4000, 17);
    const r = seeded(0x51);
    for (let i = 0; i < 30; i++) { const x = r() * w, y = r() * h, s = 8 + r() * 40, moss = r() < 0.4; const mg = g.createRadialGradient(x, y, 0, x, y, s); mg.addColorStop(0, moss ? 'rgba(80,100,48,0.28)' : 'rgba(40,38,30,0.18)'); mg.addColorStop(1, 'rgba(0,0,0,0)'); g.fillStyle = mg; g.fillRect(x - s, y - s, s * 2, s * 2); }
    g.strokeStyle = 'rgba(40,35,30,0.35)'; for (let i = 0; i < 6; i++) { g.beginPath(); let x = r() * w, y = r() * h; g.moveTo(x, y); for (let k = 0; k < 6; k++) { x += (r() - 0.5) * 24; y += r() * 14; g.lineTo(x, y); } g.stroke(); }
  });
  if (kind === 'grass') return canvasTex('tgGrass', 256, 256, (g, w, h) => {
    const r = seeded(0x6a55); g.fillStyle = '#56763a'; g.fillRect(0, 0, w, h);
    const C = ['#6b8f45', '#45652d', '#7aa050', '#3b5a26', '#8aa860'];
    for (let i = 0; i < 6000; i++) { g.fillStyle = C[Math.floor(r() * C.length)]; g.globalAlpha = 0.3 + r() * 0.5; g.fillRect(r() * w, r() * h, 1 + r() * 2, 2 + r() * 3); }
    g.globalAlpha = 1;
  });
  if (kind === 'blossom' || kind === 'leaf') return canvasTex('tg' + kind, 256, 256, (g, w, h) => {
    const r = seeded(kind === 'leaf' ? 0x1eaf : 0xb10e);
    const C = kind === 'leaf' ? ['#5c8f3a', '#2c5222', '#6fa548', '#24451c', '#4a7a30'] : ['#fbd9e5', '#f7c2d4', '#e98aac', '#ffffff', '#d9799c', '#f2b3c8'];
    g.fillStyle = kind === 'leaf' ? '#3e6a2c' : '#f0b0c6'; g.fillRect(0, 0, w, h);
    for (let i = 0; i < 1400; i++) { const x = r() * w, y = r() * h, s = 2 + r() * 4; g.fillStyle = r() < 0.15 ? (kind === 'leaf' ? 'rgba(10,30,10,0.35)' : 'rgba(140,50,85,0.3)') : C[Math.floor(r() * C.length)]; g.beginPath(); g.arc(x, y, s, 0, TAU); g.fill(); }
  });
  if (kind === 'mountains') return canvasTex('tgMountains', 3072, 384, (g, w, h) => {
    const mpd = (rough, seed) => { const r = seeded(seed), N = 4096, a = new Float32Array(N + 1); a[0] = r() * 2 - 1; a[N] = r() * 2 - 1; let step = N, amp = 1; while (step > 1) { const hf = step >> 1; for (let i = hf; i < N; i += step) a[i] = (a[i - hf] + a[i + hf]) / 2 + (r() * 2 - 1) * amp; amp *= rough; step = hf; } return (x) => a[clamp(Math.floor(x / w * N), 0, N)]; };
    const layer = (seed, base, amp, peaks, ph0, ph1, pw0, pw1) => {
      const n = mpd(0.56, seed), r = seeded(seed * 7 + 1), P = [];
      for (let k = 0; k < peaks; k++) P.push([(k + 0.2 + r() * 0.6) / peaks * w, lerp(ph0, ph1, r()), lerp(pw0, pw1, r())]);
      return (x) => { let v = base + n(x) * amp; for (const [px, hh, pw] of P) { const d = Math.abs(x - px) / pw; if (d < 1) v += hh * Math.pow(1 - d, 1.25); } return clamp(v, 8, h - 8); };
    };
    const paint = (Hf, top, bottom, snowLine, snowLit, snowSh, seed) => {
      g.beginPath(); g.moveTo(0, h); for (let x = 0; x <= w; x += 2) g.lineTo(x, h - Hf(x)); g.lineTo(w, h); g.closePath();
      const gr = g.createLinearGradient(0, h - 270, 0, h); gr.addColorStop(0, top); gr.addColorStop(1, bottom); g.fillStyle = gr; g.fill();
      const sn = mpd(0.7, seed + 99);
      for (let x = 0; x < w; x++) {
        const hx = Hf(x), y0 = h - hx, sl = (Hf(x + 6) - Hf(x - 6)) / 12, lit = clamp(0.5 - sl * 1.4, 0, 1);
        const c = lit > 0.5 ? '255,250,238' : '28,40,72', a = Math.abs(lit - 0.5) * (lit > 0.5 ? 0.5 : 0.7);
        for (let k = 0; k < 3; k++) { g.fillStyle = `rgba(${c},${a * (1 - k * 0.32)})`; g.fillRect(x, y0 + k * 30, 1, 30); }
        if (snowLine && hx > snowLine) {
          const depth = (hx - snowLine) * (0.45 + 0.55 * (sn(x) * 0.5 + 0.5)) + 4;
          g.fillStyle = lit > 0.45 ? snowLit : snowSh; g.fillRect(x, y0, 1, depth);
          g.fillStyle = 'rgba(255,255,255,0.35)'; if (lit > 0.6) g.fillRect(x, y0, 1, Math.min(depth, 3));
        }
      }
    };
    paint(layer(0xA1, 112, 26, 7, 35, 100, 160, 380), '#7590b4', '#b4cae0', 178, '#eef4fb', '#a4b7d2', 3);
    paint(layer(0xB2, 74, 20, 9, 20, 62, 110, 260), '#5c7899', '#a9c0d6', 136, '#e6eef7', '#97abc6', 5);
    paint(layer(0xC3, 44, 14, 0, 0, 0, 1, 1), '#5c7a7a', '#a9c2cf', 0, '', '', 7);
  }, false);
  return null;
}

function buildArena(id, scene, anim) {
  const A = ARENAS[id];
  applyEnvironment(scene, A.tod, id === 'subway' ? 0.03 : 0.012);
  const root = new THREE.Group(); scene.add(root);
  const q = Settings.data.quality;
  // Foto-Böden (Poly Haven CC0; Boden-UV = 4 m), prozeduraler Ersatz falls Texturen fehlen
  const photoFloor = {
    rainRooftop: ['concrete', { color: 0x8a8a90, roughness: 0.36, metal: 0.12 }], // nasser Dachbeton
    subway: ['tiles', { color: 0xc8d0d2, roughness: 0.6 }],
    foundry: ['plate', { color: 0x8e8a84, roughness: 0.85, metal: 0.85 }],
    burningSquare: ['cobble', { color: 0xa89c92, roughness: 0.9 }],
    riftRealm: ['rock', { color: 0x5e4468, roughness: 0.85 }],
    bloodTower: ['slab', { color: 0x9a3434, roughness: 0.4, metal: 0.2 }],
    templeGarden: ['flagstone', { color: 0xf0e8dc }],
  }[id];
  const floorMat = (photoFloor && photoMat(photoFloor[0], 4, photoFloor[1])) || {
    rainRooftop: new THREE.MeshStandardMaterial({ map: Tex.concrete(), roughness: 0.3, metalness: 0.15 }),
    subway: new THREE.MeshStandardMaterial({ map: Tex.tiles(), roughness: 0.3 }),
    foundry: new THREE.MeshStandardMaterial({ map: Tex.metal(), roughness: 0.5, metalness: 0.8 }),
    burningSquare: new THREE.MeshStandardMaterial({ map: Tex.brick(), roughness: 0.6 }),
    riftRealm: new THREE.MeshStandardMaterial({ color: 0x241826, roughness: 0.7, metalness: 0.1 }),
    bloodTower: new THREE.MeshStandardMaterial({ color: 0x0a0506, roughness: 0.08, metalness: 0.5 }),
    templeGarden: id === 'templeGarden' ? new THREE.MeshStandardMaterial({ map: templeTex('pavers'), roughness: 0.82 }) : null,
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
    root.add(m.mesh(photoMat('tiles', 4, { color: 0xd8dee0, roughness: 0.5 }) || new THREE.MeshStandardMaterial({ map: Tex.tiles(), roughness: 0.35 })), g.mesh(glowMat(0xb0e6ff, 1.6), false));
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
  if (id === 'templeGarden') {
    // ---- Kirschblütentempel bei Tag: Bergkulisse, Pagoden, Kirschbäume, Wächterstatuen, Steinpodest
    const perf = q === 'performance', TG = seeded(0x7e9a1e);
    const st = new MeshBuilder(), red = new MeshBuilder(), pl = new MeshBuilder(), gold = new MeshBuilder(), tk = new MeshBuilder(), br = new MeshBuilder(), pv = new MeshBuilder();
    const rf = { p: [], uv: [], i: [] };
    const limb = (b, a, c, r0, r1, seg = 6) => {
      const d = new V3().subVectors(c, a), L = d.length(); d.normalize();
      const u = (Math.abs(d.y) < 0.95 ? new V3(0, 1, 0) : new V3(1, 0, 0)).cross(d).normalize(), w = new V3().crossVectors(d, u);
      const o = b.p.length / 3;
      for (let k = 0; k <= seg; k++) {
        const an = k / seg * TAU, nx = u.x * Math.cos(an) + w.x * Math.sin(an), ny = u.y * Math.cos(an) + w.y * Math.sin(an), nz = u.z * Math.cos(an) + w.z * Math.sin(an);
        b.p.push(a.x + nx * r0, a.y + ny * r0, a.z + nz * r0, c.x + nx * r1, c.y + ny * r1, c.z + nz * r1);
        b.n.push(nx, ny, nz, nx, ny, nz); b.uv.push(k / seg, 0, k / seg, L * 0.5);
      }
      for (let k = 0; k < seg; k++) { const i0 = o + k * 2; b.i.push(i0, i0 + 2, i0 + 3, i0, i0 + 3, i0 + 1); }
    };
    // geschwungenes Walmdach mit hochgezogenen Ecken
    const roof = (cx, y0, cz, hx, hz, h, over, lift) => {
      const ex = hx + over, ez = hz + over, rx = Math.max(0.08, ex - ez), rz = 0.08, NS = 7, NT = 10;
      for (let side = 0; side < 4; side++) {
        const o = rf.p.length / 3, wide = side % 2 === 0;
        for (let a = 0; a <= NS; a++) for (let b = 0; b <= NT; b++) {
          const s = a / NS, t = b / NT * 2 - 1, ax = lerp(ex, rx, s), az = lerp(ez, rz, s);
          const y = y0 + h * Math.pow(s, 1.8) + lift * Math.pow(Math.abs(t), 4) * Math.pow(1 - s, 2);
          const P = side === 0 ? [cx + t * ax, cz + az] : side === 1 ? [cx + ax, cz - t * az] : side === 2 ? [cx - t * ax, cz - az] : [cx - ax, cz + t * az];
          rf.p.push(P[0], y, P[1]); rf.uv.push(t * (wide ? ax : az) * 0.32, s * (h + over) * 0.4);
        }
        for (let a = 0; a < NS; a++) for (let b = 0; b < NT; b++) { const i0 = o + a * (NT + 1) + b, i2 = i0 + NT + 1; rf.i.push(i0, i0 + 1, i2 + 1, i0, i2 + 1, i2); }
      }
      gold.box(cx - rx - 0.1, y0 + h - 0.08, cz - 0.16, cx + rx + 0.1, y0 + h + 0.28, cz + 0.16, 0.3);
      return y0 + h;
    };
    const S = 0.35;
    // Boden: Pflasterweg zum Tempel, Bordsteine, Grasfläche bis zum Horizont
    pv.box(-3, -0.4, -43, 3, 0.02, -16, 0.25);
    for (const sx of [-1, 1]) { st.box(sx > 0 ? 3 : -20.4, -0.4, -16.6, sx > 0 ? 20.4 : -3, 0.16, -16, S); st.box(sx * 20 - (sx > 0 ? 0 : 0.6), -0.4, -16.6, sx * 20 + (sx > 0 ? 0.6 : 0), 0.16, 8, S); }
    const grassMat = photoMat('grass', [520, 210], { color: 0xdde6cc, roughness: 0.95, normalScale: 0.8 }) || (() => { const grassT = templeTex('grass'); grassT.repeat.set(90, 36); return new THREE.MeshStandardMaterial({ map: grassT, roughness: 0.95 }); })();
    const ground = new THREE.Mesh(new THREE.PlaneGeometry(520, 210), grassMat);
    ground.rotation.x = -Math.PI / 2; ground.position.set(0, -0.03, -85); ground.receiveShadow = true; root.add(ground);
    // gemalte Bergkette mit Schneekappen weit hinten
    const mt = new THREE.Mesh(new THREE.PlaneGeometry(600, 75), new THREE.MeshBasicMaterial({ map: templeTex('mountains'), transparent: true, depthWrite: false, fog: false }));
    mt.scale.y = 1.6; mt.position.set(0, 54, -190); if (!Assets.hdr(ENV_HDRI.day.path)) root.add(mt); // echte Alpen aus dem HDRI, sonst gemalt
    // rundes Steinpodest mit Bronze-Räucherbecken
    st.cyl(0, 0, -13.5, 4.8, 0.35, 32, S); st.cyl(0, 0.35, -13.5, 4.1, 0.35, 32, S); st.cyl(0, 0.7, -13.5, 3.4, 0.3, 32, S);
    br.cyl(0, 1.0, -13.5, 0.75, 0.25, 12); br.cyl(0, 1.25, -13.5, 1.0, 0.75, 14); br.cyl(0, 2.0, -13.5, 1.15, 0.12, 14); br.cone(0, 2.12, -13.5, 0.9, 0.6, 14); br.cyl(0, 2.7, -13.5, 0.12, 0.3, 8);
    // zwei steinerne Kriegerstatuen mit gesenktem Schwert
    const statue = (cx, cz) => {
      st.box(cx - 1.7, 0, cz - 1.7, cx + 1.7, 0.45, cz + 1.7, S); st.box(cx - 1.35, 0.45, cz - 1.35, cx + 1.35, 1.7, cz + 1.35, S); st.box(cx - 1.5, 1.7, cz - 1.5, cx + 1.5, 1.95, cz + 1.5, S, true);
      if (propsHave('lion_head')) return; // echter Wächterlöwe statt prozeduraler Figur (62_props.js)
      const Y = 1.95;
      for (const sx of [-1, 1]) {
        st.box(cx + sx * 0.62 - 0.28, Y, cz - 0.35, cx + sx * 0.62 + 0.28, Y + 0.32, cz + 0.6, S);
        limb(st, new V3(cx + sx * 0.62, Y + 0.2, cz + 0.05), new V3(cx + sx * 0.36, Y + 2.0, cz), 0.3, 0.38, 8);
        st.box(cx + sx * 0.58 - 0.3, Y + 0.35, cz + 0.12, cx + sx * 0.58 + 0.3, Y + 1.15, cz + 0.42, S);
        st.cyl(cx + sx * 1.08, Y + 3.7, cz, 0.5, 0.55, 8, S); st.cone(cx + sx * 1.08, Y + 4.25, cz, 0.62, 0.35, 8);
        limb(st, new V3(cx + sx * 1.05, Y + 3.85, cz), new V3(cx + sx * 0.95, Y + 2.95, cz + 0.6), 0.27, 0.24, 7);
        limb(st, new V3(cx + sx * 0.95, Y + 2.95, cz + 0.6), new V3(cx + sx * 0.22, Y + 3.05, cz + 1.2), 0.24, 0.2, 7);
        limb(st, new V3(cx + sx * 0.35, Y + 5.15, cz + 0.12), new V3(cx + sx * 0.78, Y + 5.95, cz + 0.25), 0.09, 0.03, 5);
      }
      st.cyl(cx, Y + 1.3, cz, 0.98, 1.05, 10, S); st.box(cx - 0.55, Y + 1.0, cz + 0.8, cx + 0.55, Y + 2.3, cz + 1.0, S, true);
      st.cyl(cx, Y + 2.3, cz, 0.88, 0.32, 10, S);
      st.box(cx - 0.82, Y + 2.6, cz - 0.52, cx + 0.82, Y + 4.25, cz + 0.52, S); st.box(cx - 0.72, Y + 3.2, cz + 0.5, cx + 0.72, Y + 4.15, cz + 0.66, S); st.box(cx - 0.62, Y + 2.65, cz + 0.5, cx + 0.62, Y + 3.15, cz + 0.6, S);
      st.box(cx - 0.9, Y + 0.5, cz - 0.82, cx + 0.9, Y + 4.2, cz - 0.52, S);
      st.box(cx - 0.32, Y + 2.85, cz + 1.02, cx + 0.32, Y + 3.3, cz + 1.45, S, true);
      st.box(cx - 0.08, Y + 3.3, cz + 1.17, cx + 0.08, Y + 3.85, cz + 1.33, S); st.box(cx - 0.14, Y + 3.85, cz + 1.11, cx + 0.14, Y + 4.05, cz + 1.39, S);
      st.box(cx - 0.5, Y + 2.68, cz + 1.12, cx + 0.5, Y + 2.85, cz + 1.38, S, true); st.box(cx - 0.18, Y, cz + 1.2, cx + 0.18, Y + 2.68, cz + 1.3, S);
      st.cyl(cx, Y + 4.25, cz, 0.24, 0.3, 8, S); st.cyl(cx, Y + 4.5, cz - 0.05, 0.52, 0.22, 10, S);
      st.box(cx - 0.32, Y + 4.55, cz - 0.33, cx + 0.32, Y + 5.2, cz + 0.33, S);
      st.cyl(cx, Y + 4.95, cz, 0.42, 0.35, 10, S); st.cone(cx, Y + 5.3, cz, 0.42, 0.55, 10); st.box(cx - 0.06, Y + 5.2, cz - 0.35, cx + 0.06, Y + 6.15, cz + 0.15, S);
    };
    statue(-9.5, -12); statue(9.5, -12);
    // Steinlaternen
    const lanterns = [[-6.4, -13.2, 1.1], [6.4, -13.2, 1.1], [-15, -15, 1.25], [15, -15, 1.25], [-3.9, -21, 1], [3.9, -21, 1], [-3.9, -31, 1], [3.9, -31, 1]];
    for (const [x, z, s] of lanterns) {
      st.box(x - 0.45 * s, 0, z - 0.45 * s, x + 0.45 * s, 0.25 * s, z + 0.45 * s, S); st.cyl(x, 0.25 * s, z, 0.16 * s, 0.95 * s, 8, S);
      st.box(x - 0.38 * s, 1.2 * s, z - 0.38 * s, x + 0.38 * s, 1.32 * s, z + 0.38 * s, S, true);
      for (const [a, b] of [[-1, -1], [1, -1], [1, 1], [-1, 1]]) st.box(x + a * 0.3 * s - 0.05 * s, 1.32 * s, z + b * 0.3 * s - 0.05 * s, x + a * 0.3 * s + 0.05 * s, 1.85 * s, z + b * 0.3 * s + 0.05 * s, S);
      g.box(x - 0.24 * s, 1.34 * s, z - 0.24 * s, x + 0.24 * s, 1.8 * s, z + 0.24 * s, 1);
      st.box(x - 0.48 * s, 1.85 * s, z - 0.48 * s, x + 0.48 * s, 1.93 * s, z + 0.48 * s, S, true); st.cone(x, 1.93 * s, z, 0.66 * s, 0.42 * s, 4); st.cyl(x, 2.28 * s, z, 0.09 * s, 0.18 * s, 6);
    }
    // Tor über dem Weg
    for (const sx of [-1, 1]) { red.cyl(sx * 3.4, 0, -26, 0.32, 6.0, 12); st.cyl(sx * 3.4, 0, -26, 0.5, 0.5, 12, S); }
    red.box(-4.4, 4.9, -26.22, 4.4, 5.35, -25.78); red.box(-4.9, 5.7, -26.3, 4.9, 6.0, -25.7); gold.box(-0.7, 5.3, -25.7, 0.7, 5.75, -25.6, 0.3);
    roof(0, 6.0, -26, 4.6, 0.35, 0.65, 0.7, 0.45);
    // Haupttempel mit zwei Dachebenen
    st.box(-15, 0, -59, 15, 1.8, -44, S);
    for (let k = 0; k < 6; k++) st.box(-5, 0, -44, 5, 1.8 - k * 0.3, -43.55 + k * 0.45, S);
    for (let k = 0; k < 8; k++) { red.cyl(-10.5 + k * 3, 1.8, -45.3, 0.32, 5.0, 12); st.cyl(-10.5 + k * 3, 1.8, -45.3, 0.48, 0.3, 12, S); }
    tk.box(-11.5, 1.8, -57.5, 11.5, 6.6, -46.6, 0.2); pl.box(-11.5, 5.2, -46.68, 11.5, 6.2, -46.58, 0.2); red.box(-12, 6.2, -46.2, 12, 6.9, -44.8); gold.box(-12, 6.9, -46.2, 12, 7.0, -44.8, 0.3);
    for (let k = 0; k < 7; k++) { red.box(-10 + k * 3 - 1.05, 1.8, -46.7, -10 + k * 3 + 1.05, 2.3, -46.55); gold.box(-10 + k * 3 - 0.9, 2.3, -46.6, -10 + k * 3 + 0.9, 5.1, -46.54, 0.3); tk.box(-10 + k * 3 - 0.8, 2.4, -46.6, -10 + k * 3 + 0.8, 5.0, -46.5, 0.2); }
    red.box(-11.6, 1.8, -57.6, 11.6, 2.4, -46.5); red.box(-12, 6.6, -57.8, 12, 7.0, -46.2);
    roof(0, 6.9, -51.5, 12.4, 6.0, 3.2, 2.7, 1.1);
    red.box(-7, 7.8, -54.5, 7, 10.9, -47.5); pl.box(-6, 8.6, -47.55, 6, 10.3, -47.45, 0.2); gold.box(-7.1, 10.6, -54.6, 7.1, 10.9, -47.4, 0.3);
    const top = roof(0, 10.9, -51, 7.6, 3.6, 3.0, 2.3, 0.95);
    for (const sx of [-1, 1]) { gold.box(sx * 6.0 - 0.25, top - 0.1, -51.2, sx * 6.0 + 0.25, top + 1.0, -50.8, 0.3); gold.box(sx * 6.0 - (sx > 0 ? 0.25 : 0.6), top + 0.7, -51.15, sx * 6.0 + (sx > 0 ? 0.6 : 0.25), top + 1.0, -50.85, 0.3); }
    gold.cyl(0, top + 0.25, -51, 0.35, 0.5, 10); gold.cone(0, top + 0.75, -51, 0.35, 0.9, 10);
    // Pagoden links und rechts
    const pagoda = (cx, cz, tiers, hw0) => {
      st.box(cx - hw0 - 1.6, 0, cz - hw0 - 1.6, cx + hw0 + 1.6, 1.2, cz + hw0 + 1.6, S);
      let y = 1.2, hw = hw0;
      for (let k = 0; k < tiers; k++) {
        const hh = k === 0 ? 3.0 : 2.0;
        red.box(cx - hw, y, cz - hw, cx + hw, y + hh, cz + hw);
        pl.box(cx - hw * 0.55, y + 0.35, cz + hw, cx + hw * 0.55, y + hh - 0.45, cz + hw + 0.04, 0.2);
        for (const [a, b] of [[-1, -1], [1, -1], [1, 1], [-1, 1]]) red.cyl(cx + a * hw, y, cz + b * hw, 0.2, hh, 8);
        gold.box(cx - hw - 0.05, y + hh - 0.22, cz - hw - 0.05, cx + hw + 0.05, y + hh, cz + hw + 0.05, 0.3);
        roof(cx, y + hh, cz, hw, hw, 1.25, 1.4 + hw * 0.25, 0.75);
        y += hh + 0.3; hw *= 0.82;
      }
      y += 0.9;
      gold.cyl(cx, y - 1.0, cz, 0.13, 4.0, 8); for (let k = 0; k < 6; k++) gold.cyl(cx, y + 0.3 + k * 0.45, cz, 0.34 - k * 0.03, 0.1, 10); gold.cone(cx, y + 3.0, cz, 0.22, 0.8, 8);
    };
    pagoda(-30, -58, 5, 3.2); pagoda(34, -66, 4, 3.0);
    // Kirschbäume (Stämme gemerged, Blütenwolken instanziert)
    const blos = [], bush = [];
    const trees = [[-10.6, -3.8, 1.0], [11.2, -4.6, 1.05], [-15, -10, 1.25], [16, -11, 1.3], [-19, -17.5, 1.15], [19.5, -18.5, 1.2], [-12.5, -22, 1.0], [12.5, -23, 1.05], [-7.8, -31, 1.15], [8.2, -32, 1.1], [-19, -34, 1.4], [20, -37, 1.45], [-40, -44, 1.6], [42, -50, 1.6]];
    if (perf) trees.length = 10;
    for (const [x, z, s] of trees) {
      const tp = new V3(x + (TG() - 0.5) * 0.9 * s, 2.4 * s, z + (TG() - 0.5) * 0.5 * s);
      limb(tk, new V3(x, -0.2, z), tp, 0.32 * s, 0.2 * s, 7);
      blos.push([tp.x, tp.y + 1.7 * s, tp.z, 1.6 * s]);
      for (let b = 0; b < 4; b++) {
        const an = b / 4 * TAU + TG() * 1.2, len = (1.7 + TG() * 1.0) * s;
        const end = new V3(tp.x + Math.cos(an) * len, tp.y + (0.8 + TG() * 0.9) * s, tp.z + Math.sin(an) * len);
        limb(tk, tp, end, 0.16 * s, 0.06 * s, 5);
        blos.push([end.x, end.y + 0.25 * s, end.z, (1.15 + TG() * 0.5) * s]);
        blos.push([lerp(tp.x, end.x, 0.5) + (TG() - 0.5) * s, lerp(tp.y, end.y, 0.6) + 0.55 * s, lerp(tp.z, end.z, 0.5) + (TG() - 0.5) * s, (0.95 + TG() * 0.4) * s]);
      }
    }
    // Büsche und ferne Baumreihe
    for (const sx of [-1, 1]) {
      bush.push([sx * 9.5 - 2.2, -10.9, 0.95], [sx * 9.5 + 2.2, -11.5, 1.05], [sx * 9.5 - 1.2, -14.3, 1.15], [sx * 9.5 + 1.5, -14.5, 1.0], [sx * 5.4, -15.4, 0.7]);
      for (let k = 0; k < 7; k++) bush.push([sx * (4.2 + k * 2.4), -17.5 - (k % 2) * 0.7, 0.9 + (k % 3) * 0.25]);
      for (let k = 0; k < 4; k++) bush.push([sx * (5.5 + k * 3), -43.3 - (k % 2) * 0.4, 1.0 + (k % 2) * 0.3]);
      bush.push([sx * 18, -6, 1.1], [sx * 16.5, -27, 1.4], [sx * 24, -30, 1.6]);
    }
    for (let x = -150; x <= 150; x += perf ? 11 : 7) { const z = -80 - TG() * 14, s = 4 + TG() * 4; if (TG() < 0.22) blos.push([x, s * 0.7, z, s]); else bush.push([x, s * 0.55, z, s]); }
    for (let k = 0; k < (perf ? 6 : 12); k++) { const sx = k % 2 ? 1 : -1, x = sx * (16 + TG() * 40), z = -58 - TG() * 14, s = 3 + TG() * 3; if (TG() < 0.4) blos.push([x, s * 0.7, z, s]); else bush.push([x, s * 0.55, z, s]); }
    // Blätter-/Blütengeometrie: leicht verbeulte Kugel, glatte Normalen
    const fGeo = new THREE.IcosahedronGeometry(1, perf ? 1 : 2), fp = fGeo.attributes.position;
    for (let i = 0; i < fp.count; i++) { const x = fp.getX(i), y = fp.getY(i), z = fp.getZ(i), f = 1 + 0.16 * Math.sin(x * 5.1 + y * 3.3) * Math.cos(z * 4.7 - y * 2.1) + 0.08 * Math.sin(z * 9.3 + x * 7.7); fp.setXYZ(i, x * f, y * f, z * f); }
    const du = new THREE.Object3D(), col = new THREE.Color();
    const inst = (list, mat, colors, ys) => {
      const im = new THREE.InstancedMesh(fGeo, mat, list.length);
      list.forEach(([x, y, z, s], i) => {
        du.position.set(x, y, z); du.rotation.set(TG() * 3, TG() * 3, TG() * 3); du.scale.set(s * (0.9 + TG() * 0.3), s * ys, s * (0.9 + TG() * 0.3)); du.updateMatrix(); im.setMatrixAt(i, du.matrix);
        im.setColorAt(i, col.set(colors[Math.floor(TG() * colors.length)]));
      });
      im.castShadow = true; im.receiveShadow = true; root.add(im); return im;
    };
    inst(blos, new THREE.MeshStandardMaterial({ map: templeTex('blossom'), roughness: 0.85 }), [0xffffff, 0xffe4ee, 0xffd0e0, 0xf5c0d6, 0xffeef4], 0.72);
    inst(bush, new THREE.MeshStandardMaterial({ map: templeTex('leaf'), roughness: 0.9 }), [0xffffff, 0xd8e8c8, 0xb8d0a0, 0xe8f0d0], 0.62);
    // Blütenblätter und Blutflecken auf dem Pflaster
    const petMat = new THREE.MeshStandardMaterial({ color: 0xffffff, roughness: 0.75, side: THREE.DoubleSide });
    const FPN = perf ? 140 : 360, fpm = new THREE.InstancedMesh(new THREE.PlaneGeometry(0.085, 0.06).rotateX(-Math.PI / 2), petMat, FPN);
    for (let i = 0; i < FPN; i++) { du.position.set(lerp(-19, 19, TG()), 0.006, lerp(-15.8, 6, TG())); du.rotation.set(0, TG() * TAU, 0); du.scale.set(1, 1, 1); du.updateMatrix(); fpm.setMatrixAt(i, du.matrix); fpm.setColorAt(i, col.set([0xf8b6cc, 0xf3a2bf, 0xfbd3e1, 0xea8db1][i % 4])); }
    fpm.receiveShadow = true; root.add(fpm);
    const splatMat = new THREE.MeshStandardMaterial({ map: Tex.splat(), transparent: true, depthWrite: false, roughness: 0.3, polygonOffset: true, polygonOffsetFactor: -2 });
    const splatGeo = new THREE.PlaneGeometry(1, 1).rotateX(-Math.PI / 2);
    for (const [x, z, s] of [[-3.4, -1.7, 1.1], [2.7, 1.9, 0.75], [5.6, -6.8, 1.35]]) { const sp = new THREE.Mesh(splatGeo, splatMat); sp.position.set(x, 0.01, z); sp.rotation.y = TG() * TAU; sp.scale.set(s, 1, s * 0.8); sp.receiveShadow = true; root.add(sp); }
    // fallende Kirschblüten im Wind
    const PN = perf ? 70 : (q === 'ultra' ? 260 : 150);
    const petals = new THREE.InstancedMesh(new THREE.PlaneGeometry(0.075, 0.055), petMat, PN); petals.frustumCulled = false; root.add(petals);
    const pd = new Float32Array(PN * 7);
    for (let i = 0; i < PN; i++) { pd.set([rand(-17, 15), rand(0, 10), rand(-14, 3), rand(0.45, 0.95), rand(0, TAU), rand(1, 4), rand(1, 4)], i * 7); petals.setColorAt(i, col.set([0xf8b6cc, 0xfbd3e1, 0xf3a2bf][i % 3])); }
    let ptime = 0;
    anim.push((dt) => {
      ptime += dt;
      for (let i = 0; i < PN; i++) {
        const o = i * 7;
        pd[o + 1] -= pd[o + 3] * dt; pd[o] += (0.7 + Math.sin(ptime * 0.7 + pd[o + 4]) * 0.5) * dt; pd[o + 2] += Math.cos(ptime * 1.3 + pd[o + 4]) * 0.25 * dt;
        if (pd[o + 1] < 0.03) { pd[o + 1] = rand(8, 11); pd[o] = rand(-18, 14); pd[o + 2] = rand(-14, 3); }
        if (pd[o] > 17) pd[o] -= 34;
        du.position.set(pd[o], pd[o + 1], pd[o + 2]); du.rotation.set(ptime * pd[o + 5] + pd[o + 4], ptime * pd[o + 6], pd[o + 4]); du.scale.set(1, 1, 1); du.updateMatrix(); petals.setMatrixAt(i, du.matrix);
      }
      petals.instanceMatrix.needsUpdate = true;
    });
    // Meshes zusammenführen
    const roofGeo = new THREE.BufferGeometry();
    roofGeo.setAttribute('position', new THREE.Float32BufferAttribute(rf.p, 3)); roofGeo.setAttribute('uv', new THREE.Float32BufferAttribute(rf.uv, 2)); roofGeo.setIndex(rf.i); roofGeo.computeVertexNormals();
    const roofs = new THREE.Mesh(roofGeo, new THREE.MeshStandardMaterial({ map: templeTex('roof'), roughness: 0.5, metalness: 0.1, side: THREE.DoubleSide })); roofs.castShadow = true; roofs.receiveShadow = true;
    const stoneMat = new THREE.MeshStandardMaterial({ map: templeTex('stone'), color: 0xd6d0c4, roughness: 0.92 });
    root.add(roofs, st.mesh(stoneMat), red.mesh(pbr(0xa3221a, 0.55, 0)), pl.mesh(pbr(0xe9dfca, 0.85, 0)), gold.mesh(pbr(0xd4a640, 0.35, 0.85)), tk.mesh(pbr(0x3a2924, 0.9, 0)), br.mesh(pbr(0x6b5636, 0.45, 0.8)), pv.mesh(floorMat, false), g.mesh(glowMat(0xffb35a, 2.2), false));
  }
  propsForArena(id, root, anim, q); // echte Requisiten (62_props.js)
  const key = new THREE.DirectionalLight(0xc8d0ff, 1.8);
  key.position.set(6, 12, 9); key.castShadow = q !== 'performance';
  key.shadow.mapSize.set(1024, 1024); const sc = key.shadow.camera; sc.left = -12; sc.right = 12; sc.top = 10; sc.bottom = -4; key.shadow.bias = -0.0006;
  scene.add(key);
  const rim1 = new THREE.SpotLight(A.accent, 28, 40, 0.7, 0.6); rim1.position.set(-7, 6, -9); rim1.target.position.set(0, 1, 0); scene.add(rim1, rim1.target);
  const rim2 = new THREE.SpotLight(A.accent, 28, 40, 0.7, 0.6); rim2.position.set(7, 6, -9); rim2.target.position.set(0, 1, 0); scene.add(rim2, rim2.target);
  scene.add(new THREE.HemisphereLight(0x606a90, 0x201014, 0.7));
  if (A.tod === 'day') {
    // Tageslicht: warme Sonne mit weichen Schatten, Himmelsblau von oben, neutrale Randlichter
    key.color.set(0xffe4c4); key.intensity = 2.9; key.position.set(9, 17, 11);
    const sm = q === 'ultra' ? 2048 : 1024; key.shadow.mapSize.set(sm, sm);
    sc.left = -22; sc.right = 22; sc.top = 18; sc.bottom = -16; sc.near = 1; sc.far = 70; sc.updateProjectionMatrix();
    key.shadow.bias = -0.0004; key.shadow.normalBias = 0.03; key.shadow.radius = 3;
    for (const rl of [rim1, rim2]) { rl.color.set(0xfff3ea); rl.intensity = 3; }
    const hemi = scene.children.find((o) => o.isHemisphereLight);
    if (hemi) { hemi.color.set(0xa9cdf5); hemi.groundColor.set(0x6e6250); hemi.intensity = 0.55; }
  }
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
  // SCHWER: langsamer Anlauf, mehr Schaden
  heavy: { name: 'heavy', clip: 'kick2', s: 0.17, a: 0.08, r: 0.34, dmg: 92, reach: 1.75, lvl: 'mid', kd: false, launch: false, lunge: 1.1 },
  heavy2: { name: 'heavy2', clip: 'kick', s: 0.12, a: 0.16, r: 0.36, dmg: 58, hits: 2, reach: 1.7, lvl: 'mid', kd: true, launch: false, lunge: 1.3 },
  midKick: { name: 'midKick', clip: 'kick', s: 0.1, a: 0.08, r: 0.3, dmg: 72, reach: 1.65, lvl: 'mid', kd: false, launch: false, lunge: 1.2 },
  launcher: { name: 'launcher', clip: 'uppercut', s: 0.1, a: 0.09, r: 0.4, dmg: 85, reach: 1.35, lvl: 'mid', kd: false, launch: true, lunge: 1.4 },
  overhead: { name: 'overhead', clip: 'dashStrike', s: 0.22, a: 0.08, r: 0.3, dmg: 68, reach: 1.45, lvl: 'overhead', kd: false, launch: false, lunge: 1.6 },
  throwEnd: { name: 'throwEnd', clip: 'throwToss', s: 0, a: 0, r: 0.42, dmg: 0, reach: 0, lvl: 'mid', kd: false, launch: false, lunge: 0 },
};
// Kettentabelle: '<Technik>:<L|H>' -> Folgetechnik (L = LEICHT, H = SCHWER)
const CHAINS = { 'jab:L': 'cross', 'cross:H': 'launcher', 'jab:H': 'midKick', 'midKick:H': 'roundhouse', 'heavy:H': 'heavy2', 'overhead:L': 'cross', 'cross:L': 'chainKick' };
const BUF_KEYS = ['punch', 'kick', 's1', 's2', 'throw'], BUF_T = 0.15, EX_COST = 34;
const exGlow = (f) => f.exGlow || (f.exGlow = new THREE.Color(f.def.look.glow || '#ffcc5c').getHex());

class Fighter {
  constructor(id, cast, isPlayer, x) {
    this.def = ROSTER.fighters[id]; this.id = id; this.isPlayer = isPlayer;
    this.rig = new Rig(cast);
    this.x = x; this.y = 0; this.vx = 0; this.vy = 0; this.facing = x < 0 ? 1 : -1;
    this.max = this.def.stats.hp; this.hp = this.max; this.lag = this.max; this.meter = 0;
    this.state = 'idle'; this.t = 0; this.move = null; this.moveHit = false; this.connected = false;
    this.stun = 0; this.juggled = false; this.blockLow = false; this.inv = 0; this.cd = [0, 0];
    this.sp = 0; this.spStep = 0; this.spDone = false; this.buf = {}; this.hitIdx = 0; this.ex = false; this.exArmed = false; this.exHit = false; this.exPend = 0; this.counter = 0; this.comboTaken = 0; this.comboDealt = 0; this.maxCombo = 0; this.dealt = 0; this.rounds = 0;
  }
  set(s) { this.state = s; this.t = 0; }
  get grounded() { return this.y <= 0.001; }
  get down() { return this.state === 'knockdown' || this.state === 'getUp'; }
  reset(x) {
    this.x = x; this.y = 0; this.vx = 0; this.vy = 0; this.hp = this.max; this.lag = this.max; this.set('idle'); this.move = null; this.stun = 0; this.juggled = false; this.inv = 0; this.counter = 0; this.comboTaken = 0; this.comboDealt = 0; this.cd = [0, 0]; this.buf = {}; this.ex = false; this.exArmed = false; this.exPend = 0;
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
    if (this.block > 0) { I.block = true; I.crouch = this.blockLow; } else if (this.walkT > 0 && !this.queue.length && I.moveX === undefined) I.moveX = this.walk;
    // Wurf befreien: kurze Reaktionszeit, dann mit Glück WURF im Zeitfenster
    if (me.state === 'thrown') { if (!this.techTry && me.t > 0.07) { this.techTry = true; if (Math.random() < 0.12 + 0.4 * clamp(this.level, 0, 1.2)) I.throw = true; } } else this.techTry = false;
    return I;
  }
  gap() { return lerp(0.24, 0.11, clamp(this.level, 0, 1.2) / 1.2); }
  apply(p, I, tw) {
    if (p === 'P') I.punch = true; else if (p === 'K') I.kick = true;
    else if (p === 'dP') { I.crouch = true; I.punch = true; } else if (p === 'dK') { I.crouch = true; I.kick = true; }
    else if (p === 'S1') I.s1 = true; else if (p === 'S2') I.s2 = true; else if (p === 'J') { I.jump = true; I.moveX = tw; }
    else if (p === 'T' || p === 'W') I.throw = true; else if (p === 'B') I.brutal = true; else if (p === 'X') I.ex = true;
    else if (p === 'bK') { I.kick = true; I.moveX = -tw; } else if (p === 'fP') { I.punch = true; I.moveX = tw; }
  }
  decide(me, opp, dist, tw, incoming) {
    const r = Math.random(), L = this.level, bc = clamp(0.12 + 0.62 * L, 0, 0.88);
    if ((opp.state === 'attack' || opp.state === 'special') && dist < 2.6 && r < bc) { this.block = 0.45; this.blockLow = opp.move && opp.move.lvl === 'low'; return; }
    if (incoming && r < bc) { if (Math.random() < 0.4 * L) this.queue = ['J']; else { this.block = 0.5; this.blockLow = false; } return; }
    if (opp.state === 'air' && dist < 2.6 && r < 0.75 * L) { this.queue = ['dP']; return; }
    if (me.meter >= 100 && dist < 2 && r < 0.65 * L) { this.queue = ['B']; return; }
    const sp = me.def.specials, ex = me.meter >= EX_COST && Math.random() < 0.2 + 0.35 * clamp(L, 0, 1);
    if (dist > 3.2) {
      const q = Math.random();
      if (me.cd[0] <= 0 && dist < sp[0].range && q < 0.3 + 0.25 * L) this.queue = ex ? ['X', 'S1'] : ['S1'];
      else if (me.cd[1] <= 0 && dist < sp[1].range && q < 0.25 + 0.2 * L) this.queue = ['S2'];
      else if (q < 0.12 + (this.boss ? 0.1 : 0)) this.queue = ['J', 'K'];
      else { this.walk = tw; this.walkT = 0.4; }
      return;
    }
    if (dist > 1.5) {
      const q = Math.random();
      if (q < 0.55 + (this.boss ? 0.2 : 0)) { this.walk = tw; this.walkT = 0.3; }
      else if (q < 0.7 && me.cd[1] <= 0 && dist < sp[1].range) this.queue = ex ? ['X', 'S2'] : ['S2'];
      else if (q < 0.8) { this.walk = -tw; this.walkT = 0.25; }
      else this.queue = Math.random() < 0.5 ? ['K'] : ['fP'];
      return;
    }
    const q = Math.random(), s = clamp(L, 0, 1.2);
    if ((opp.state === 'block' || opp.state === 'crouch') && q < 0.4 * s) this.queue = ['W'];
    else if (opp.state === 'block' && opp.blockLow && q < 0.55 * s) this.queue = ['fP'];
    else if (q < 0.22 + 0.16 * s) this.queue = Math.random() < 0.5 ? ['P', 'P', 'K'] : ['P', 'K', 'K'];
    else if (q < 0.38 + 0.12 * s) this.queue = Math.random() < 0.6 ? ['K', 'K'] : ['K'];
    else if (q < 0.46) this.queue = ['bK'];
    else if (q < 0.53) this.queue = ['W'];
    else if (q < 0.6) this.queue = ['dP'];
    else if (q < 0.72 && me.cd[0] <= 0) this.queue = ex ? ['X', 'S1'] : ['S1'];
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
    case 'thunderJudgement': {
      // DONNERGERICHT: Opfer wird über den Kopf gehoben, von Blitzen aus beiden Händen gegrillt und zerrissen
      dur = 7;
      const lo = Settings.data.quality === 'performance';
      const bolt = FX.bolt(0x6cb8ff, lo ? 90 : 170);
      const ap = tl.ap.clone(), hc = new V3(ap.x, a.worldPos('head').y + 1.25, 0);
      const v0 = tl.vp.clone(), q0 = v.root.quaternion.clone();
      const cOff = Math.max(0.6, v.worldPos('hips').y - v0.y + 0.1);
      const qL = new THREE.Quaternion().setFromRotationMatrix(new THREE.Matrix4().makeBasis(new V3(0, 0, f), new V3(f, 0, 0), new V3(0, 1, 0)));
      const vT = new V3(hc.x - f * cOff, hc.y, 0), qW = new THREE.Quaternion(), eW = new THREE.Euler();
      const tg = ['chest', 'head', 'hips', 'lFore', 'rFore', 'lShin', 'rShin', 'spine'], pick = () => v.worldPos(tg[(Math.random() * tg.length) | 0]);
      let prevT = 0, acc = 1, hitT = 0, zapT = 0, on = false, dead = false, W = 1;
      const regen = () => {
        const lh = a.worldPos('lHand'), rh = a.worldPos('rHand'), vc = v.worldPos('chest'), nb = lo ? 1 : 2;
        bolt.begin();
        bolt.strike(lh, vc, { segs: 10, branches: nb + 1, width: W });
        bolt.strike(rh, tl.t > 2.4 ? v.worldPos('hips') : vc, { segs: 10, branches: nb + 1, width: W });
        for (let i = 0; i < nb; i++) bolt.strike(Math.random() < 0.5 ? lh : rh, pick(), { segs: 8, branches: nb - 1, width: W * 0.7 });
        if (tl.t > 2.4) for (let i = 0; i < nb; i++) bolt.strike(pick(), pick(), { segs: 6, branches: 0, width: 0.55, jitter: 0.3 });
        bolt.end(); bolt.flicker(rand(0.7, 1.15));
        FX.burst('electric', pick(), 0.35, new V3(rand(-1, 1), rand(-0.4, 1), rand(-1, 1)));
        FX.burst('electric', Math.random() < 0.5 ? lh : rh, 0.2, new V3(0, -0.5, 0));
        FX.light(vc.clone().add(new V3(0, -0.9, 1.1)), 0x8fd0ff, rand(1.5, 2.6) * W, 7, 0.12);
        FX.light(lh.lerp(rh, 0.5), 0x4a9cff, rand(2, 3) * W, 6, 0.12);
        FX.light(ap.clone().add(new V3(-f * 0.6, 1.8, -1.4)), 0x5aaaff, 3.5 * W, 6, 0.12);
        if (!dead && tl.t > 0.9) v.setMaterialState('frozen', clamp(0.15 + (tl.t - 0.9) * 0.1, 0, 0.5) * rand(0.5, 1));
      };
      tl.tween(0, dur, () => {
        const t = tl.t, dt = t - prevT; prevT = t;
        if (!dead && t >= 1.2) {
          const k = smooth((t - 1.2) / 1.4);
          v.root.position.lerpVectors(v0, vT, k); v.root.position.y += Math.sin(Math.PI * k) * 0.35;
          v.root.quaternion.slerpQuaternions(q0, qL, smooth((t - 1.45) / 1.15));
          if (t > 2.6) {
            const e = 0.4 + clamp((t - 2.6) / 1.7, 0, 1);
            v.root.position.x += rand(-1, 1) * 0.03 * e; v.root.position.y += rand(-1, 1) * 0.03 * e + Math.sin(t * 3) * 0.05;
            v.root.quaternion.multiply(qW.setFromEuler(eW.set(rand(-1, 1) * 0.05 * e, rand(-1, 1) * 0.05 * e, rand(-1, 1) * 0.05 * e)));
          }
        }
        if (!dead && t > 0.9 && t - hitT > 0.32) { hitT = t; v.play('hitHigh', null, true, 0.05); }
        if (on) {
          acc += dt / Math.max(0.05, ctl.scale);
          if (acc >= 0.05) { acc = 0; regen(); }
          else bolt.flicker(rand(0.55, 1.1));
          if (t - zapT > 0.28) { zapT = t; snd('electric', 0.35); }
        }
      });
      tl.cue(0.05, () => { FX.gore(ap, 2.6, 1.3); for (let i = 0; i < 4; i++) FX.pool(new V3(ap.x + rand(-2.4, 2.4), 0.02, rand(-1.1, 0.9)), rand(0.6, 1.1)); });
      tl.cue(0.9, () => { a.play('cast', null, true, 0.15); on = true; acc = 1; snd('thunder', 0.8); snd('electric'); flash('#bfe2ff'); shake(0.4); });
      tl.shot(0.9, 2.6, tl.c(-1.9, 0.35, 3.6, 1.5, 50, ap), tl.c(-1.0, 0.2, 3.1, 2.7, 54, ap));
      tl.cue(1.2, () => { snd('roar', 0.7); shake(0.25); });
      tl.cue(1.7, () => a.play('celebrate', null, true, 0.35));
      tl.cue(2.55, () => { flash('#9fd0ff'); snd('thunder'); shake(0.5); });
      tl.cue(2.7, () => slow(0.7));
      tl.shot(2.6, 4.3, tl.c(2.3, -0.7, 3.1, -0.15, 40, hc), tl.c(1.4, -0.9, 2.6, -0.1, 36, hc));
      tl.cue(3.4, () => { flash('#cfe8ff'); shake(0.35); snd('boneCrack', 0.6); FX.burst('bloodSpray', v.worldPos('chest'), 0.8, new V3(0, -1, 0)); });
      tl.cue(4.3, () => { slow(0.3); W = 1.8; flash('#ffffff'); snd('thunder'); snd('heartbeat'); shake(0.6); });
      tl.shot(4.3, 4.55, tl.c(0.3, -1.4, 3.6, -0.3, 46, hc), tl.c(0.2, -1.5, 3.1, -0.3, 44, hc));
      tl.cue(4.55, () => {
        dead = true; on = false; bolt.begin(); bolt.end();
        const c = v.worldPos('chest');
        v.setMaterialState('charred', 0.75); v.detachAll(1.35); v.root.visible = false;
        FX.burst('bloodBurst', c, 2.4); FX.burst('electric', c, 2.5); FX.burst('sparks', c, 1.6, new V3(0, 1, 0), 0xbfe6ff); FX.burst('smoke', c, 1.2);
        FX.light(c, 0xcfe8ff, 12, 18, 0.6); flash('#e8f6ff'); shake(1); slow(0.45);
        snd('explosion'); snd('gore'); snd('thunder'); snd('boneCrack');
      });
      tl.cue(4.63, () => { flash('#a00000'); const c = hc.clone(); FX.burst('bloodSpray', c, 1.8, new V3(f, -0.2, 0.3)); FX.burst('bloodSpray', c, 1.8, new V3(-f, -0.2, -0.3)); });
      tl.shot(4.55, 6.0, tl.c(2.4, -0.3, 6.4, -1.0, 56, hc), tl.c(3.2, 0.4, 7.4, -1.5, 58, hc));
      tl.cue(5.1, () => slow(1));
      tl.cue(5.6, () => { for (const d of v.detached) FX.pool(new V3(d.obj.position.x, 0.02, d.obj.position.z), rand(0.5, 0.9)); snd('bodyFall'); shake(0.3); });
      tl.cue(5.8, () => a.play('victory', null, true));
      tl.shot(6.0, 7, tl.c(-1.3, 0.3, 3.0, 1.8, 42, ap), tl.c(-2.0, 0.2, 3.9, 1.9, 46, ap));
      tl.cue(6.95, () => { on = false; bolt.remove(); });
      break;
    }
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
      punch: Input.consume('punch'), kick: Input.consume('kick'), s1: Input.consume('special1'), s2: Input.consume('special2'), brutal: Input.consume('brutal'),
      throw: Input.consume('throw'), ex: Input.consume('ex') };
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
    const A = this.f[i], Vv = this.f[1 - i], fb = A.meter < 100 && this.fatalReady(i);
    if ((A.meter < 100 && !fb) || Math.abs(Vv.x - A.x) > 2.4 || Vv.down || !Vv.grounded) return false;
    if (fb) { A.meter -= 50; (this.fatalUsed || (this.fatalUsed = []))[i] = true; } else A.meter = 0;
    this.bi = i; A.set('cinematic'); Vv.set('cinematic');
    UI.kombatCinematic(true); UI.kombatControls(false); UI.banner(fb ? 'TODESSTOSS' : A.def.brutal, 'brutal', 1.6);
    const tl = new Timeline(A.rig, Vv.rig, this), f = tl.facing;
    A.rig.root.position.x = Vv.rig.root.position.x - f * 1.25;
    tl.shot(0, 0.5, tl.c(-1.2, 1.4, 2.6, 1.4, 40, tl.ap), tl.c(-0.6, 1.5, 1.8, 1.5, 30, tl.ap));
    tl.cue(0, () => { this.setScale(0.4); UI.flash(A.def.look.glow); Audio.play('whoosh'); });
    const clips = ['punch', 'kick2', 'uppercut'], parts = [70, 80, 130], xr = ['skull', 'ribs', 'spine'];
    XRay.begin(Vv.rig, this.scene, this);
    for (let k = 0; k < 3; k++) {
      const t0 = 0.5 + k * 0.8;
      tl.cue(t0, () => A.rig.play(clips[k], null, true));
      tl.cue(t0 + 0.12, () => XRay.focus(xr[k], new V3(f, 0.1, 0)));
      tl.cue(t0 + 0.22, () => {
        UI.flash('#ffffff'); this.shake.add(k === 2 ? 1 : 0.55);
        Vv.rig.play(k === 2 ? 'knockdown' : 'hitHigh', null, true); Vv.rig.setMaterialState('frozen', 0.65);
        Audio.play(k === 0 ? 'punchHeavy' : 'boneCrack'); Audio.play('gore', 0.7);
        FX.burst('bloodSpray', Vv.rig.worldPos(k === 1 ? 'hips' : 'head'), 1.1, new V3(f, 0.6, 0)); Haptic(50);
        const dmg = parts[k] * A.def.stats.power / Math.max(0.3, Vv.def.stats.defense);
        Vv.hp = Math.max(1, Vv.hp - dmg); A.dealt += dmg; A.comboDealt++; A.maxCombo = Math.max(A.maxCombo, A.comboDealt);
        XRay.hit(xr[k], new V3(f, k === 2 ? 0.5 : 0.1, 0));
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
  fatalReady(i) { const A = this.f[i]; return A.meter >= 50 && A.hp < A.max * 0.3 && !(this.fatalUsed && this.fatalUsed[i]); }
  brutalUpdate(dt) {
    const rdt = dt / Math.max(0.001, this.scale), fin = this.tl.advance(dt, 3.4);
    this.cam.pos.copy(this.tl.cam.pos); this.cam.look.copy(this.tl.cam.look); this.cam.fov = this.tl.cam.fov;
    XRay.update(rdt, this.cam);
    if (fin) {
      XRay.end(); this.setScale(1);
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
    // Eingabepuffer: Drücke bleiben BUF_T Sekunden gültig und werden ausgeführt, sobald der Kämpfer handeln kann
    const B = f.buf;
    for (const k of BUF_KEYS) { if (I[k]) B[k] = BUF_T; else if (B[k] > 0) B[k] -= dt; I[k] = B[k] > 0; }
    if (I.ex) this.exToggle(f);
    if (f.exArmed && f.meter < EX_COST) f.exArmed = false;
    if (f.exPend > 0) { f.exPend -= dt; if (f.exPend <= 0) this.exFollow(i); }
    const fwd = (I.moveX || 0) * f.facing;
    switch (f.state) {
      case 'idle': case 'walk': case 'crouch': case 'block':
        if (f.comboTaken) f.comboTaken = 0;
        f.facing = o.x >= f.x ? 1 : -1;
        if (I.brutal && this.tryBrutal(i)) return;
        if (I.jump) { f.set('air'); f.vy = f.def.stats.jump; f.vx = (I.moveX || 0) * 3.6; f.move = null; f.rig.play('jump', null, true); Audio.play('whoosh', 0.4); }
        else if (I.s1 && f.cd[0] <= 0) { B.s1 = 0; this.special(f, 0); }
        else if (I.s2 && f.cd[1] <= 0) { B.s2 = 0; this.special(f, 1); }
        else if (I.throw || (I.punch && I.block && Math.abs(o.x - f.x) < 1.5)) { B.throw = B.punch = 0; this.startMove(f, MOVES.throw); }
        else if (I.punch) { B.punch = 0; this.startMove(f, I.crouch ? MOVES.uppercut : fwd > 0.5 ? MOVES.overhead : MOVES.jab); }
        else if (I.kick) { B.kick = 0; this.startMove(f, I.crouch || fwd < -0.5 ? MOVES.sweep : MOVES.heavy); }
        else if (I.block) { if (f.state !== 'block') f.set('block'); f.blockLow = !!I.crouch; f.vx = 0; }
        else if (I.crouch) { if (f.state !== 'crouch') f.set('crouch'); f.vx = 0; }
        else if (Math.abs(I.moveX || 0) > 0.1) { if (f.state !== 'walk') f.set('walk'); const back = I.moveX * f.facing < 0; f.vx = I.moveX * f.def.stats.walk * (back ? 0.8 : 1); }
        else { if (f.state !== 'idle') f.set('idle'); f.vx = 0; }
        break;
      case 'air':
        f.vy -= 22 * dt;
        if (!f.move && (I.kick || I.punch)) { const m = I.kick ? MOVES.jumpKick : MOVES.jumpPunch; B.kick = B.punch = 0; f.move = m; f.moveHit = false; f.t = 0; f.rig.play(m.clip, m.s + m.a + m.r, true); Audio.play('whoosh', 0.5); }
        if (f.move && !f.moveHit && f.t >= f.move.s && f.t < f.move.s + f.move.a) this.tryHit(i, f.move);
        if (f.y <= 0 && f.vy <= 0) { f.y = 0; f.vy = 0; f.move = null; f.set('idle'); f.rig.play('land', null, true); FX.burst('dust', new V3(f.x, 0.02, 0), 0.5); }
        break;
      case 'attack': {
        const m = f.move; if (!m) { f.set('idle'); break; }
        const t = f.t, tot = m.s + m.a + m.r;
        if (t < m.s + m.a) f.vx = f.facing * m.lunge; else f.vx *= 0.8;
        // Trefferzone nur in der aktiven Phase; Mehrfachtreffer teilen die aktive Phase auf
        const nh = m.hits || 1;
        if (t >= m.s && t < m.s + m.a) { const k = Math.min(nh - 1, Math.floor((t - m.s) / (m.a / nh))); if (k > f.hitIdx) { f.hitIdx = k; f.moveHit = false; } if (!f.moveHit) this.tryHit(i, m); }
        if (f.connected && t >= m.s + m.a * (nh - 1) / nh && t < tot - 0.03 && (I.punch || I.kick)) {
          const L = I.punch && CHAINS[m.name + ':L'], H = I.kick && CHAINS[m.name + ':H'], n = L || H;
          if (n) { if (L) B.punch = 0; else B.kick = 0; this.startMove(f, MOVES[n]); return; }
        }
        if (t >= tot) { f.move = null; f.set('idle'); }
        break;
      }
      case 'thrown':
        f.vx = 0;
        if (I.throw && f.t < 0.2) { B.throw = 0; this.techThrow(i); }
        else if (f.t > 0.8) f.set('idle');
        break;
      case 'throwing':
        f.vx = 0;
        if (o.state !== 'thrown') { f.set('idle'); break; }
        if (f.t >= 0.2) this.throwToss(i);
        break;
      case 'special': this.exSpecial(i, dt); break;
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
  startMove(f, m) { f.set('attack'); f.move = m; f.moveHit = false; f.connected = false; f.hitIdx = 0; f.rig.play(m.clip, m.s + m.a + m.r, true); Audio.play('whoosh', 0.45, rand(0.9, 1.15)); }
  tryHit(i, m) {
    const a = this.f[i], d = this.f[1 - i], dx = d.x - a.x;
    if (Math.abs(dx) > m.reach + 0.3) return;
    if (Math.abs(dx) > 0.25 && Math.sign(dx) !== a.facing) return;
    if (d.inv > 0 || d.down || d.state === 'cinematic' || d.state === 'dizzy') return;
    if (m.lvl === 'low' && d.y > 0.4) return;
    if (d.y - a.y > 1.6) return;
    if (m.lvl === 'high' && d.state === 'crouch') return;
    if (m.lvl === 'unblockable' && (!d.grounded || d.state === 'attack')) return;
    if (m.name === 'throw' && ['hitstun', 'blockstun', 'thrown', 'throwing', 'knockdown', 'getUp'].includes(d.state)) return;
    a.moveHit = true; a.connected = true;
    if (d.counter > 0 && m.lvl !== 'unblockable') { d.counter = 0; this.combo(d, d.ex ? 'EX-KONTER!' : 'KONTER!'); this.hit(1 - i, d.ex ? 125 : 90, true, false, 'unblockable'); d.rig.play('uppercut', null, true); if (d.ex) d.exPend = 0.2; return; }
    if (m.name === 'throw') { this.grab(i); return; }
    const last = a.hitIdx >= (m.hits || 1) - 1;
    this.hit(i, m.dmg, m.kd && last, m.launch && last, m.lvl);
  }
  // ---- Würfe: Packen, 0,2 s Befreiungsfenster (WURF drücken), dann Schleudern
  grab(i) {
    const a = this.f[i], d = this.f[1 - i], H = this.arena.half;
    a.set('throwing'); d.set('thrown'); a.vx = d.vx = 0; d.move = null;
    d.x = clamp(a.x + a.facing * 0.85, -H, H); d.facing = -a.facing;
    a.rig.play('grab', 0.4, true); d.rig.play('hitHigh', null, true); d.rig.flashHit(0xffffff);
    Audio.play('block', 0.5, 0.7); this.hitStop = 0.05;
    if (a.isPlayer || d.isPlayer) Haptic(12);
  }
  throwToss(i) {
    const a = this.f[i], d = this.f[1 - i], H = this.arena.half;
    d.x = clamp(a.x - a.facing * 1.2, -H, H);
    this.startMove(a, MOVES.throwEnd); a.moveHit = true;
    this.hit(i, MOVES.throw.dmg, true, false, 'unblockable');
    d.vx = -a.facing * 4.5;
    FX.burst('dust', new V3(d.x, 0.05, 0), 1.3); this.shake.add(0.5); Audio.play('bodyFall');
    if (a.isPlayer) UI.combo('WURF!');
  }
  techThrow(i) {
    const d = this.f[i], a = this.f[1 - i];
    for (const f of [a, d]) { f.set('blockstun'); f.stun = 0.28; f.move = null; f.vx = -f.facing * 4.2; f.rig.play('block', null, true); }
    FX.burst('sparks', new V3((a.x + d.x) / 2, 1.3, 0), 1.1); Audio.play('block'); this.shake.add(0.25); this.hitStop = 0.06;
    if (d.isPlayer) UI.combo('BEFREIT!'); else if (a.isPlayer) UI.combo('WURF ABGEWEHRT!');
    if (a.isPlayer || d.isPlayer) Haptic(20);
  }
  // ---- EX: ab EX_COST Leiste verstärkt die nächste Trick-Technik (mehr Schaden, Zusatztreffer, Leuchten)
  exToggle(f) {
    if (f.state === 'special' && !f.ex && f.t < 0.12 && f.meter >= EX_COST) { this.exStart(f); return; }
    if (f.exArmed) { f.exArmed = false; return; }
    if (f.meter >= EX_COST) { f.exArmed = true; if (f.isPlayer) Audio.play('whoosh', 0.35, 1.6); }
  }
  exStart(f) {
    f.meter -= EX_COST; f.ex = true; f.exArmed = false; f.exHit = false;
    const g = exGlow(f), p = f.rig.worldPos('chest');
    FX.burst('electric', p, 1.2, new V3(0, 1, 0), g); FX.burst('embers', p, 0.8, undefined, g); f.rig.flashHit(g);
    Audio.play('teleport', 0.6, 1.3); this.hitStop = Math.max(this.hitStop, 0.05);
    UI.kombatEx(f.isPlayer ? 0 : 1, f.def.specials[f.sp].name);
    if (f.isPlayer) Haptic(25);
  }
  exSpecial(i, dt) {
    const f = this.f[i], o = this.f[1 - i];
    if (!f.ex) { this.updateSpecial(i, dt); return; }
    const s = f.def.specials[f.sp], k = s.kind, hp0 = o.hp, st0 = o.state;
    this.dmgMul = 1.4; this.updateSpecial(i, dt);
    // Zusatztreffer: zweites Geschoss bzw. Nachschlag nach dem ersten Treffer
    if ((k === 'projectile' || k === 'groundWave') && f.state === 'special' && f.spStep === 1 && f.t >= 0.32) { f.spStep = 2; this.spawnProj(i, s, k === 'groundWave'); }
    else if (k !== 'projectile' && k !== 'groundWave' && !f.exHit && o.hp < hp0 && o.state === 'hitstun' && st0 !== 'block') { f.exHit = true; f.exPend = 0.18; }
    this.dmgMul = 1;
    if (Math.random() < 0.8) FX.spray(FX.add, f.rig.worldPos(Math.random() < 0.5 ? 'rHand' : 'chest'), 3, 1.4, new V3(0, 1, 0), 1.3, exGlow(f), 0.07, 0.35, -0.6, 1.5);
    if (f.state !== 'special') f.ex = false;
  }
  exFollow(i) {
    const f = this.f[i], o = this.f[1 - i];
    if (o.down || o.state === 'cinematic' || o.state === 'thrown' || Math.abs(o.x - f.x) > 2.8) return;
    const sf = f.facing; f.facing = o.x >= f.x ? 1 : -1;
    this.hit(i, 48, false, true, 'unblockable'); f.facing = sf;
    FX.burst('electric', o.rig.worldPos('chest'), 1, new V3(f.facing, 0.5, 0), exGlow(f));
  }
  hit(i, base, kd, launch, lvl) {
    const a = this.f[i], d = this.f[1 - i]; base *= this.dmgMul || 1;
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
    if (d.comboTaken >= 2) { const W = ['', '', '', 'BRUTAL!', 'GNADENLOS!', 'BLUTRAUSCH!', 'UNAUFHALTSAM!', 'VERNICHTEND!'], w = d.comboTaken < W.length ? W[d.comboTaken] : 'LEGENDÄR!'; this.combo(a, d.comboTaken + ' TREFFER' + (w ? '  ' + w : '')); }
  }
  combo(f, text) { if (f.isPlayer) UI.combo(text); }
  special(f, k) {
    const s = f.def.specials[k];
    f.cd[k] = s.cooldown; f.set('special'); f.sp = k; f.spDone = false; f.spStep = 0; f.vx = 0; f.ex = false;
    if (f.exArmed && f.meter >= EX_COST) this.exStart(f);
    if (s.kind === 'dashStrike') f.rig.play('dashStrike', 0.6, true);
    else if (s.kind === 'grabSlam') f.rig.play('grab', 0.5, true);
    else if (s.kind === 'counter') { f.rig.play('block', null, true); f.counter = f.ex ? 1.0 : 0.7; }
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
    if (f.ex) mesh.scale.multiplyScalar(1.35);
    const p = { mesh, owner: i, x: f.x + f.facing * 0.8, y, vx: f.facing * (low ? 10 : 13), dmg: s.damage * (this.dmgMul || 1), low, life: 2.2, alive: true, color: s.color };
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
      timer: this.timer, s1: a.cd[0] <= 0, s2: a.cd[1] <= 0, brutal: this.phase === 'fight' && (a.meter >= 100 || this.fatalReady(0)),
      ex: a.meter >= EX_COST, exOn: a.exArmed || a.ex, c1: b.comboTaken, c2: a.comboTaken });
  }
}
