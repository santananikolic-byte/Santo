// =====================================================================
//  Neo-Haven: prozedurale Stadt mit Kollision, Schwing-Ankern und Verkehr
// =====================================================================
const CITY = { pitch: 100, street: 20, blocks: 9 };

class City {
  constructor(tod, quality) {
    this.root = new THREE.Group();
    this.size = CITY.blocks * CITY.pitch;
    this.boxes = []; this.grid = new Map(); this.landmarks = {}; this.collect = []; this.spawns = []; this.anim = [];
    this.towerActive = false;
    this.build(tod, quality);
  }
  key(x, z) { return (x + 1000) * 4000 + (z + 1000); }
  register(b) {
    const i = this.boxes.length; this.boxes.push(b);
    for (let gx = Math.floor(b.x0 / 50); gx <= Math.floor(b.x1 / 50); gx++) for (let gz = Math.floor(b.z0 / 50); gz <= Math.floor(b.z1 / 50); gz++) {
      const k = this.key(gx, gz); if (!this.grid.has(k)) this.grid.set(k, []); this.grid.get(k).push(i);
    }
  }
  near(x, z, r) {
    const out = [], seen = new Set();
    for (let gx = Math.floor((x - r) / 50); gx <= Math.floor((x + r) / 50); gx++) for (let gz = Math.floor((z - r) / 50); gz <= Math.floor((z + r) / 50); gz++) {
      const l = this.grid.get(this.key(gx, gz)); if (!l) continue;
      for (const i of l) if (!seen.has(i)) { seen.add(i); out.push(this.boxes[i]); }
    }
    if (this.towerActive) out.push(this.towerBox);
    return out;
  }
  surface(p) {
    let best = 0;
    for (const b of this.near(p.x, p.z, 2)) if (p.x >= b.x0 && p.x <= b.x1 && p.z >= b.z0 && p.z <= b.z1 && b.y1 <= p.y + 0.5) best = Math.max(best, b.y1);
    return best;
  }
  collide(pos, vel, r, h) {
    const info = { ground: false, roof: false, wall: false, n: new V3() };
    for (const b of this.near(pos.x, pos.z, r + 4)) {
      if (pos.y >= b.y1 - 0.001 || pos.y + h <= b.y0) continue;
      const cx = clamp(pos.x, b.x0, b.x1), cz = clamp(pos.z, b.z0, b.z1);
      const dx = pos.x - cx, dz = pos.z - cz, d2 = dx * dx + dz * dz;
      if (d2 >= r * r) continue;
      const depth = b.y1 - pos.y;
      const inside = pos.x > b.x0 && pos.x < b.x1 && pos.z > b.z0 && pos.z < b.z1;
      if (depth < 1.6 && vel.y <= 0.5 && (inside || depth < 0.6)) { pos.y = b.y1; if (vel.y < 0) vel.y = 0; info.ground = info.roof = true; continue; }
      let nx = 0, nz = 0, push = 0;
      if (d2 > 1e-8) { const d = Math.sqrt(d2); nx = dx / d; nz = dz / d; push = r - d; }
      else {
        const o = [[pos.x - b.x0, -1, 0], [b.x1 - pos.x, 1, 0], [pos.z - b.z0, 0, -1], [b.z1 - pos.z, 0, 1]].sort((a, c) => a[0] - c[0])[0];
        nx = o[1]; nz = o[2]; push = o[0] + r;
      }
      pos.x += nx * push; pos.z += nz * push;
      const vn = vel.x * nx + vel.z * nz;
      if (vn < 0) { vel.x -= nx * vn; vel.z -= nz * vn; }
      info.wall = true; info.n.set(nx, 0, nz);
    }
    if (pos.y <= 0) { pos.y = 0; if (vel.y < 0) vel.y = 0; info.ground = true; }
    const lim = this.size / 2 + 180;
    pos.x = clamp(pos.x, -lim, lim); pos.z = clamp(pos.z, -lim, lim);
    return info;
  }
  anchor(p, vel, aim) {
    const fa = new V3(aim.x, 0, aim.z).normalize();
    const fv = new V3(vel.x, 0, vel.z); if (fv.lengthSq() > 0.01) fv.normalize(); else fv.copy(fa);
    const dir = fa.multiplyScalar(0.65).add(fv.multiplyScalar(0.35)).normalize();
    const probe = p.clone().addScaledVector(dir, 32);
    let best = null, bs = -1e9;
    for (const b of this.near(probe.x, probe.z, 60)) {
      const y = Math.min(b.y1, p.y + 34);
      if (y < p.y + 6) continue;
      let cx = clamp(probe.x, b.x0, b.x1), cz = clamp(probe.z, b.z0, b.z1);
      if (probe.x > b.x0 && probe.x < b.x1 && probe.z > b.z0 && probe.z < b.z1) { cx = clamp(p.x, b.x0, b.x1); cz = clamp(p.z, b.z0, b.z1); }
      const c = new V3(cx, y, cz);
      const ox = cx - (b.x0 + b.x1) / 2, oz = cz - (b.z0 + b.z1) / 2, ol = Math.hypot(ox, oz) || 1;
      c.x += ox / ol * 0.3; c.z += oz / ol * 0.3;
      const d = c.distanceTo(p);
      if (d < 12 || d > 75) continue;
      const hz = new V3(c.x - p.x, 0, c.z - p.z).normalize();
      const fwd = hz.dot(dir);
      if (fwd < 0.15) continue;
      const sc = fwd * 2.2 - Math.abs(d - 34) / 30 + (c.y - p.y) / 45;
      if (sc > bs) { bs = sc; best = c; }
    }
    return best;
  }
  raycast(o, dir, max) {
    const d = dir.clone().normalize();
    let tb = max, hit = false;
    const mid = o.clone().addScaledVector(d, max / 2);
    for (const b of this.near(mid.x, mid.z, max / 2 + 5)) {
      let t0 = 0, t1 = tb, ok = true;
      for (const [oo, dd, lo, hi] of [[o.x, d.x, b.x0, b.x1], [o.y, d.y, b.y0, b.y1], [o.z, d.z, b.z0, b.z1]]) {
        if (Math.abs(dd) < 1e-6) { if (oo < lo || oo > hi) { ok = false; break; } }
        else { let a = (lo - oo) / dd, c = (hi - oo) / dd; if (a > c) [a, c] = [c, a]; t0 = Math.max(t0, a); t1 = Math.min(t1, c); if (t0 > t1) { ok = false; break; } }
      }
      if (ok && t0 > 0.01 && t0 < tb) { tb = t0; hit = true; }
    }
    if (d.y < -1e-4) { const tg = -o.y / d.y; if (tg > 0 && tg < tb) { tb = tg; hit = true; } }
    return hit ? o.clone().addScaledVector(d, tb) : null;
  }
  setTower(on) { this.towerActive = on; this.tower.visible = on; }
  update(dt) { this.t = (this.t || 0) + dt; this.traffic(dt); this.anim.forEach((a) => a(dt)); }

  build(tod, quality) {
    const rnd = seeded(2077);
    const ri = (a, b) => a + Math.floor(rnd() * (b - a));
    const rf = (a, b) => a + rnd() * (b - a);
    const half = this.size / 2;
    const fac = [new MeshBuilder(), new MeshBuilder(), new MeshBuilder(), new MeshBuilder()];
    const roofs = new MeshBuilder(), metal = new MeshBuilder(), stone = new MeshBuilder(), side = new MeshBuilder();
    const glow = new MeshBuilder(), blink = new MeshBuilder(), neon = [new MeshBuilder(), new MeshBuilder(), new MeshBuilder()];
    const trees = new MeshBuilder(), trunks = new MeshBuilder(), grass = new MeshBuilder(), crane = new MeshBuilder();
    const lanes = new MeshBuilder(), posts = new MeshBuilder(), heads = new MeshBuilder();
    const tops = [];
    const S = 1 / 12;
    // Dach-Details + Bäume: eigener Zufallsstrom, damit das Stadtlayout gleich bleibt
    const rnd2 = seeded(4242), rf2 = (a, b) => a + rnd2() * (b - a);
    const wood = new MeshBuilder(), garden = new MeshBuilder(), treeAt = [];
    const waterTower = (cx, y, cz) => {
      const lh = 3.2, r = 2.1, th = 3.8;
      for (const [ox, oz] of [[-1.4, -1.4], [1.4, -1.4], [-1.4, 1.4], [1.4, 1.4]]) metal.box(cx + ox - 0.14, y, cz + oz - 0.14, cx + ox + 0.14, y + lh, cz + oz + 0.14, 0.3);
      metal.box(cx - 1.5, y + 1.4, cz - 1.45, cx + 1.5, y + 1.55, cz - 1.35, 0.3); metal.box(cx - 1.5, y + 1.4, cz + 1.35, cx + 1.5, y + 1.55, cz + 1.45, 0.3);
      metal.box(cx - 1.45, y + 1.4, cz - 1.5, cx - 1.35, y + 1.55, cz + 1.5, 0.3); metal.box(cx + 1.35, y + 1.4, cz - 1.5, cx + 1.45, y + 1.55, cz + 1.5, 0.3);
      metal.box(cx - 2.3, y + lh - 0.2, cz - 2.3, cx + 2.3, y + lh, cz + 2.3, 0.3);
      wood.cyl(cx, y + lh, cz, r, th, 14, 0.25);
      for (const b of [0.5, 1.8, 3.1]) metal.cyl(cx, y + lh + b, cz, r + 0.05, 0.12, 14, 0.3);
      metal.cone(cx, y + lh + th, cz, r + 0.25, 1.4, 14);
      metal.cyl(cx, y + lh + th + 1.25, cz, 0.1, 0.7, 5);
      metal.box(cx + r - 0.1, y + lh, cz - 0.3, cx + r + 0.12, y + lh + th, cz - 0.22, 0.3); metal.box(cx + r - 0.1, y + lh, cz + 0.22, cx + r + 0.12, y + lh + th, cz + 0.3, 0.3);
    };
    const roofDeco = (x0, y1, z0, x1, z1) => {
      const w = x1 - x0, d = z1 - z0;
      if (rnd2() < 0.5) { // Geländer auf der Brüstung
        const ry = y1 + 1.1, step = quality === 'performance' ? 7 : 3.2, e = 0.18;
        const rail = (ax, az, bx, bz) => { const n = Math.max(1, Math.round(Math.hypot(bx - ax, bz - az) / step)); for (let k = 0; k <= n; k++) { const px = lerp(ax, bx, k / n), pz = lerp(az, bz, k / n); metal.box(px - 0.05, ry, pz - 0.05, px + 0.05, ry + 1, pz + 0.05, 0.3); } };
        rail(x0 + e, z0 + e, x1 - e, z0 + e); rail(x0 + e, z1 - e, x1 - e, z1 - e); rail(x0 + e, z0 + e, x0 + e, z1 - e); rail(x1 - e, z0 + e, x1 - e, z1 - e);
        for (const hy of [0.5, 0.96]) { metal.box(x0, ry + hy, z0 + 0.12, x1, ry + hy + 0.07, z0 + 0.24, 0.3); metal.box(x0, ry + hy, z1 - 0.24, x1, ry + hy + 0.07, z1 - 0.12, 0.3); metal.box(x0 + 0.12, ry + hy, z0, x0 + 0.24, ry + hy + 0.07, z1, 0.3); metal.box(x1 - 0.24, ry + hy, z0, x1 - 0.12, ry + hy + 0.07, z1, 0.3); }
      }
      if (rnd2() < 0.6 && w > 9 && d > 9) { // Treppenhaus-Aufbau mit Tür
        const bx = x1 - 4.6 - rnd2() * Math.min(3, w * 0.2), bz = z1 - 4.4;
        roofs.box(bx, y1, bz, bx + 3.2, y1 + 2.8, bz + 3, 0.25); roofs.box(bx - 0.15, y1 + 2.8, bz - 0.15, bx + 3.35, y1 + 3, bz + 3.15, 0.25);
        metal.box(bx + 1, y1, bz - 0.06, bx + 2.1, y1 + 2.2, bz, 0.3);
      }
      if (rnd2() < 0.22 && w > 14 && d > 14 && y1 < 150) { // Dachgarten
        const gx0 = x0 + w * 0.5, gz0 = z0 + 2, gx1 = x1 - 2, gz1 = z0 + d * 0.48;
        roofs.box(gx0 - 0.3, y1, gz0 - 0.3, gx1 + 0.3, y1 + 0.5, gz1 + 0.3, 0.25);
        garden.box(gx0, y1 + 0.5, gz0, gx1, y1 + 0.58, gz1, 0.2);
        for (let k = 0; k < 5; k++) treeAt.push(rf2(gx0 + 1, gx1 - 1), y1 + 0.58, rf2(gz0 + 1, gz1 - 1), rf2(0.3, 0.55));
      }
      if (rnd2() < 0.3) for (let k = 0; k < 3; k++) metal.cyl(x0 + 1.5 + k * 0.9, y1, z1 - 1.5, 0.06, rf2(2.5, 7), 4); // Antennen
    };
    const district = (i, j) => {
      if (i === 4 && j === 4) return 'plaza';
      if ((i === 6 || i === 7) && (j === 1 || j === 2)) return 'park';
      if (i >= 3 && i <= 5 && j >= 3 && j <= 5) return 'center';
      if (i <= 2 && j <= 3) return 'old';
      if (i >= 6 && j >= 5 && j <= 7) return 'industry';
      if (j === 8) return 'harbor';
      return 'res';
    };
    const rect = (i, j) => { const x0 = -half + i * CITY.pitch + CITY.street / 2, z0 = -half + j * CITY.pitch + CITY.street / 2; return [x0, z0, x0 + CITY.pitch - CITY.street, z0 + CITY.pitch - CITY.street]; };
    const building = (x0, y0, z0, x1, y1, z1, style, props) => {
      if (x1 - x0 < 1 || z1 - z0 < 1 || y1 - y0 < 1) return;
      this.register({ x0, y0, z0, x1, y1, z1 });
      fac[style % 4].box(x0, y0, z0, x1, y1, z1, S);
      roofs.box(x0, y1, z0, x1, y1 + 0.05, z1, 0.12);
      const t = 0.35;
      roofs.box(x0, y1, z0, x1, y1 + 1.1, z0 + t, 0.25); roofs.box(x0, y1, z1 - t, x1, y1 + 1.1, z1, 0.25);
      roofs.box(x0, y1, z0, x0 + t, y1 + 1.1, z1, 0.25); roofs.box(x1 - t, y1, z0, x1, y1 + 1.1, z1, 0.25);
      tops.push(new V3((x0 + x1) / 2, y1, (z0 + z1) / 2));
      if (!props) return;
      const w = x1 - x0, d = z1 - z0;
      for (let k = 0; k < ri(1, 4); k++) { const px = rf(x0 + 2, Math.max(x0 + 2.1, x1 - 4)), pz = rf(z0 + 2, Math.max(z0 + 2.1, z1 - 4)); metal.box(px, y1, pz, px + 2.2, y1 + 1.4, pz + 1.6, 0.3); metal.cyl(px + 1.1, y1 + 1.4, pz + 0.8, 0.55, 0.1, 8, 0.3); metal.box(px - 0.5, y1, pz + 0.45, px, y1 + 0.55, pz + 1.15, 0.3); }
      if (rnd() < 0.4 && w > 12 && d > 12) waterTower(x0 + w * 0.3, y1, z0 + d * 0.65);
      roofDeco(x0, y1, z0, x1, z1);
      if (y1 > 60 && rnd() < 0.6) { const ax = x0 + w * 0.7, az = z0 + d * 0.3, h = rf(6, 18); metal.cyl(ax, y1, az, 0.15, h, 6); blink.box(ax - 0.35, y1 + h, az - 0.35, ax + 0.35, y1 + h + 0.7, az + 0.35, 1); }
      if (rnd() < 0.25) { const ny = y1 + 1.2, k = ri(0, 3); if (rnd() < 0.5) { metal.box(x0 + 2, y1, z0 + 0.4, x0 + 2.3, ny + 4, z0 + 0.7, 0.3); neon[k].box(x0 + 1, ny, z0 + 0.2, Math.min(x1 - 1, x0 + 14), ny + 3.5, z0 + 0.5, 1); } else neon[k].box(x1 + 0.05, y1 * 0.55, z0 + d * 0.4, x1 + 0.6, y1 * 0.55 + 9, z0 + d * 0.4 + 2.5, 1); }
    };
    const tower = (x0, z0, x1, z1, height, style) => {
      let h0 = 0; const tiers = height > 90 ? (height > 160 ? 3 : 2) : 1;
      for (let t = 0; t < tiers; t++) {
        const frac = tiers === 1 ? 1 : (t === tiers - 1 ? 1 : (t === 0 ? 0.55 : 0.82));
        const top = height * frac;
        building(x0, h0, z0, x1, top, z1, style, t === tiers - 1);
        h0 = top;
        const ins = Math.min(x1 - x0, z1 - z0) * 0.12; x0 += ins; z0 += ins; x1 -= ins; z1 -= ins;
      }
    };
    // Straßen
    for (let k = 0; k <= CITY.blocks; k++) {
      const c = -half + k * CITY.pitch;
      for (let s = -half; s < half; s += 8) { lanes.box(c - 0.12, 0.02, s, c + 0.12, 0.04, s + 3, 1); lanes.box(s, 0.02, c - 0.12, s + 3, 0.04, c + 0.12, 1); }
      for (let t = -half + 20; t < half; t += 50) for (const sd of [-1, 1]) for (const [px, pz] of [[c + sd * 8.5, t], [t, c + sd * 8.5]]) { posts.cyl(px, 0, pz, 0.12, 7, 5); heads.box(px - 0.4, 7, pz - 0.4, px + 0.4, 7.25, pz + 0.4, 1); }
    }
    // Blöcke
    for (let i = 0; i < CITY.blocks; i++) for (let j = 0; j < CITY.blocks; j++) {
      const [x0, z0, x1, z1] = rect(i, j);
      const dist = district(i, j);
      if (dist !== 'park') side.box(x0 - 3, 0, z0 - 3, x1 + 3, 0.15, z1 + 3, 0.25);
      if (dist !== 'park' && dist !== 'industry' && dist !== 'harbor') { // Straßenbäume entlang der Gehwege (Abstand zu Laternen)
        const sp = quality === 'performance' ? 24 : quality === 'balanced' ? 15 : 11.5;
        for (const [ax, az, bx, bz] of [[x0 - 1.7, z0, x0 - 1.7, z1], [x1 + 1.7, z0, x1 + 1.7, z1], [x0, z0 - 1.7, x1, z0 - 1.7], [x0, z1 + 1.7, x1, z1 + 1.7]]) {
          const n = Math.floor(Math.hypot(bx - ax, bz - az) / sp);
          for (let k = 0; k < n; k++) {
            const t = (k + 0.5) / n, px = lerp(ax, bx, t), pz = lerp(az, bz, t), m = ((((ax === bx ? pz : px) + half - 20) % 50) + 50) % 50;
            if (m > 3 && m < 47) treeAt.push(px, 0.15, pz, rf2(0.8, 1.15));
          }
        }
        if (dist === 'plaza') for (let k = 0; k < 7; k++) for (const [px, pz] of [[x0 + 5, z0 + 5 + k * 11.5], [x1 - 5, z0 + 5 + k * 11.5], [x0 + 5 + k * 11.5, z0 + 5]]) treeAt.push(px, 0.15, pz, rf2(0.9, 1.2));
      }
      if (dist === 'plaza') { stone.box(x0 + 10, 0.15, z0 + 10, x1 - 10, 0.6, z1 - 10, 0.2); this.landmarks.bloodTower = new V3((x0 + x1) / 2, 0.6, z1 - 6); continue; }
      if (dist === 'park') {
        grass.box(x0 - 3, 0, z0 - 3, x1 + 3, 0.2, z1 + 3, 0.1);
        for (let k = 0; k < (quality === 'performance' ? 10 : 22); k++) { const px = rf(x0, x1), pz = rf(z0, z1), h = rf(5, 10); treeAt.push(px, 0.2, pz, h / 7); }
        const cx = (x0 + x1) / 2, cz = (z0 + z1) / 2; // Parkwege + dichter Baumbestand
        side.box(x0 - 3, 0.2, cz - 1.6, x1 + 3, 0.26, cz + 1.6, 0.25); side.box(cx - 1.6, 0.2, z0 - 3, cx + 1.6, 0.26, z1 + 3, 0.25);
        for (let k = 0; k < (quality === 'performance' ? 12 : 34); k++) { const px = rf2(x0, x1), pz = rf2(z0, z1); if (Math.abs(px - cx) > 3 && Math.abs(pz - cz) > 3) treeAt.push(px, 0.2, pz, rf2(0.8, 1.5)); }
        for (const [hx, hz] of [[x0 + 4, z0 + 4], [x1 - 14, z1 - 6]]) garden.box(hx, 0.2, hz, hx + 10, 1.3, hz + 1.4, 0.2); // Hecken
        continue;
      }
      if (i === 1 && j === 1) { // Dom
        const cx = (x0 + x1) / 2, cz = (z0 + z1) / 2;
        this.register({ x0: cx - 14, y0: 0, z0: cz - 32, x1: cx + 14, y1: 30, z1: cz + 30 });
        stone.box(cx - 14, 0, cz - 32, cx + 14, 30, cz + 30, 0.15);
        for (let zz = cz - 28; zz < cz + 28; zz += 8) { stone.box(cx - 17, 0, zz, cx - 14, 22, zz + 2, 0.2); stone.box(cx + 14, 0, zz, cx + 17, 22, zz + 2, 0.2); glow.box(cx - 14.05, 8, zz + 3, cx + 14.05, 20, zz + 5, 1); }
        for (const sd of [-1, 1]) { this.register({ x0: cx + sd * 9 - 6, y0: 0, z0: cz + 30, x1: cx + sd * 9 + 6, y1: 72, z1: cz + 42 }); stone.box(cx + sd * 9 - 6, 0, cz + 30, cx + sd * 9 + 6, 72, cz + 42, 0.15); stone.cone(cx + sd * 9, 72, cz + 36, 7, 34, 4); this.collect.push(new V3(cx + sd * 9, 73.5, cz + 36)); }
        this.landmarks.cathedral = new V3(cx, 31, cz);
        continue;
      }
      if (i === 7 && j === 6) { // Gießerei
        this.register({ x0: x0 + 4, y0: 0, z0: z0 + 8, x1: x1 - 4, y1: 22, z1: z1 - 20 });
        metal.box(x0 + 4, 0, z0 + 8, x1 - 4, 22, z1 - 20, 0.08);
        glow.box(x0 + 8, 6, z1 - 19.98, x1 - 8, 12, z1 - 19.9, 1);
        for (let k = 0; k < 3; k++) { const cx = x0 + 16 + k * 22, cz = z1 - 10; this.register({ x0: cx - 3, y0: 0, z0: cz - 3, x1: cx + 3, y1: 64, z1: cz + 3 }); stone.cyl(cx, 0, cz, 3, 64, 12, 0.1); glow.cyl(cx, 61, cz, 3.1, 2.5, 12); }
        this.landmarks.foundry = new V3((x0 + x1) / 2, 22, (z0 + z1) / 2 - 6);
        continue;
      }
      if (i === 2 && j === 8) { // Hafen + Kran
        building(x0 + 2, 0, z0 + 2, x1 - 30, 14, z1 - 30, 2, true);
        const bx = x1 - 14, bz = z1 + 4;
        this.register({ x0: bx - 4, y0: 0, z0: bz - 4, x1: bx + 4, y1: 52, z1: bz + 4 });
        for (const [ox, oz] of [[-3.6, -3.6], [3.6, -3.6], [-3.6, 3.6], [3.6, 3.6]]) crane.box(bx + ox - 0.5, 0, bz + oz - 0.5, bx + ox + 0.5, 52, bz + oz + 0.5, 0.2);
        crane.box(bx - 4, 50, bz - 4, bx + 4, 53, bz + 4, 0.2); crane.box(bx - 1.2, 53, bz - 40, bx + 1.2, 55.5, bz + 26, 0.2);
        blink.box(bx - 0.4, 55.5, bz - 40, bx + 0.4, 56.3, bz - 39.2, 1);
        this.landmarks.harborCrane = new V3(bx, 53, bz);
        for (let k = 0; k < 10; k++) { const cx = x0 + 4 + (k % 5) * 7, cz = z1 - 24 + Math.floor(k / 5) * 3.2, st = 1 + (k * 7) % 3; this.register({ x0: cx, y0: 0, z0: cz, x1: cx + 6, y1: 2.6 * st, z1: cz + 2.5 }); neon[k % 3].box(cx, 0, cz, cx + 6, 2.6 * st, cz + 2.5, 0.3); }
        continue;
      }
      const w = x1 - x0, d = z1 - z0;
      const xs = rnd() < 0.6 ? [x0, x0 + w * rf(0.4, 0.6), x1] : [x0, x1];
      const zs = rnd() < 0.6 ? [z0, z0 + d * rf(0.4, 0.6), z1] : [z0, z1];
      for (let a = 0; a < xs.length - 1; a++) for (let b = 0; b < zs.length - 1; b++) {
        const lx0 = xs[a] + 1.5, lx1 = xs[a + 1] - 1.5, lz0 = zs[b] + 1.5, lz1 = zs[b + 1] - 1.5;
        if (i === 5 && j === 2) { if (a === 0 && b === 0) { tower(x0 + 6, z0 + 6, x1 - 6, z1 - 6, 185, 0); glow.box(x0 + 14, 185 * 0.82 + 2, z0 + 14, x1 - 14, 185 * 0.82 + 3, z1 - 14, 1); this.landmarks.labTower = new V3((x0 + x1) / 2, 185, (z0 + z1) / 2); } continue; }
        let h, st;
        if (dist === 'center') { h = rf(90, 210); st = rnd() < 0.6 ? 0 : 3; } else if (dist === 'old') { h = rf(16, 40); st = 1; } else if (dist === 'industry' || dist === 'harbor') { h = rf(10, 30); st = 2; } else { h = rf(25, 95); st = ri(0, 4); }
        if (i === 2 && j === 5 && a === 0 && b === 0) { building(lx0, 0, lz0, lx1, 36, lz1, 1, false); this.landmarks.heroApartment = new V3((lx0 + lx1) / 2, 36, (lz0 + lz1) / 2); continue; }
        tower(lx0, lz0, lx1, lz1, h, st);
      }
    }
    { const [x0, z0] = rect(3, 6); const px = x0 - 1, pz = z0 - 1; metal.box(px - 1.5, 0, pz - 4, px + 1.5, 3, pz, 0.3); glow.box(px - 0.8, 3, pz - 0.8, px + 0.8, 4.6, pz + 0.8, 1); this.landmarks.subwayEntrance = new V3(px - 5, 0, pz + 3); }
    { const [x0, z0] = rect(6, 1), [, , x1, z1] = rect(7, 2); const c = new V3((x0 + x1) / 2, 0.2, (z0 + z1) / 2); this.landmarks.riftCore = c; const rift = FX.rift(0xff1030, 7); rift.position.set(c.x, 70, c.z); this.root.add(rift); this.anim.push(rift.userData.anim); }
    for (const k of ['heroApartment', 'harborCrane', 'subwayEntrance', 'foundry', 'cathedral', 'riftCore', 'bloodTower', 'labTower']) if (!this.landmarks[k]) this.landmarks[k] = tops[0].clone();
    const shuffled = tops.slice().sort(() => rnd() - 0.5);
    for (const t of shuffled.slice(0, Math.max(0, 40 - this.collect.length))) this.collect.push(t.clone().add(new V3(0, 1.4, 0)));
    for (let k = 0; k < 12; k++) this.spawns.push(new V3(-half + ((k % 8) + 1) * CITY.pitch, 0, -half + (((k * 5) % 8) + 1) * CITY.pitch));
    shuffled.slice(-4).forEach((t) => this.spawns.push(t.clone()));

    // Boden + Wasser
    const ground = new MeshBuilder();
    ground.quad([-half - 150, 0, half + 10], [half + 150, 0, half + 10], [half + 150, 0, -half - 150], [-half - 150, 0, -half - 150], [0, 1, 0], [[0, 0], [130, 0], [130, 130], [0, 130]]);
    const asph = Tex.asphalt();
    const groundMat = new THREE.MeshStandardMaterial({ map: asph, roughness: tod === 'dusk' ? 0.55 : 0.28, metalness: 0.1 });
    this.root.add(ground.mesh(groundMat, false));
    const water = new MeshBuilder();
    water.quad([-half - 400, -0.6, half + 700], [half + 400, -0.6, half + 700], [half + 400, -0.6, half + 10], [-half - 400, -0.6, half + 10], [0, 1, 0], [[0, 0], [1, 0], [1, 1], [0, 1]]);
    this.root.add(water.mesh(new THREE.MeshStandardMaterial({ color: 0x02070c, roughness: 0.05, metalness: 0.9 }), false));
    const add = (b, m, sh = true) => { if (!b.empty) this.root.add(b.mesh(m, sh)); };
    const conc = new THREE.MeshStandardMaterial({ map: Tex.concrete(), roughness: 0.85 });
    add(side, conc, false); add(roofs, conc);
    add(lanes, new THREE.MeshStandardMaterial({ color: 0xcccccc, emissive: 0x333333, roughness: 0.5 }), false);
    add(posts, pbr(0x262626, 0.4, 0.8)); add(heads, glowMat(0xffc880, 4), false);
    for (let s = 0; s < 4; s++) {
      const m = new THREE.MeshStandardMaterial({ map: Tex.facade(s, false), emissiveMap: Tex.facade(s, true), emissive: 0xffffff, emissiveIntensity: tod === 'dusk' ? 0.4 : 1.7, roughness: s === 0 ? 0.25 : 0.7, metalness: s === 0 ? 0.5 : 0.05 });
      if (tod === 'dusk') m.color.setRGB(2.5, 2.2, 1.95); // Fassaden im warmen Abendlicht aufhellen
      add(fac[s], m);
    }
    add(metal, new THREE.MeshStandardMaterial({ map: Tex.metal(), roughness: 0.45, metalness: 0.7 }));
    add(stone, pbr(0x6b6661, 0.85, 0)); add(glow, glowMat(0xff8c33, 3), false);
    this.blinkMat = glowMat(0xff1a1a, 6); add(blink, this.blinkMat, false);
    const neonCols = [0xff1a73, 0x1ad9ff, 0xff9a1a];
    this.neonMats = neonCols.map((c) => glowMat(c, 2.6));
    neon.forEach((b, k) => add(b, this.neonMats[k], false));
    const golden = tod === 'dusk';
    add(grass, pbr(golden ? 0x3f5a26 : 0x122410, 0.95, 0), false); add(trees, pbr(0x0d2a12, 0.9, 0)); add(trunks, pbr(0x2a1a10, 0.9, 0)); add(crane, pbr(0xbf1f14, 0.5, 0.6));
    add(wood, new THREE.MeshStandardMaterial({ map: Tex.metal(), color: 0x9a6a42, roughness: 0.8, metalness: 0.1 }));
    add(garden, pbr(golden ? 0x4d6a2c : 0x16301a, 0.95, 0));
    // Bäume als InstancedMesh (2 Draw-Calls für die ganze Stadt)
    const nT = treeAt.length / 4;
    if (nT) {
      const fg = new THREE.SphereGeometry(1, 8, 6), fp = fg.attributes.position;
      for (let k = 0; k < fp.count; k++) { const x = fp.getX(k), y = fp.getY(k), z = fp.getZ(k), n = 1 + 0.16 * Math.sin(x * 5.1 + z * 3.7) * Math.cos(y * 4.3 + x * 2.1); fp.setXYZ(k, x * n, y * n * 0.85, z * n); }
      fg.computeVertexNormals();
      const tg = new THREE.CylinderGeometry(0.14, 0.22, 1, 5); tg.translate(0, 0.5, 0);
      const fol = new THREE.InstancedMesh(fg, new THREE.MeshStandardMaterial({ color: 0xffffff, roughness: 0.9 }), nT);
      const trk = new THREE.InstancedMesh(tg, pbr(0x3a2618, 0.9, 0), nT);
      const M = new THREE.Matrix4(), Q = new THREE.Quaternion(), P = new V3(), Sc = new V3(), C = new THREE.Color(), UPV = new V3(0, 1, 0);
      const greens = golden ? [0x5a7a2c, 0x6c8a32, 0x48682a, 0x8a7a2c, 0x7a9a3a, 0x9a6a28] : [0x1d3a1a, 0x24401c, 0x18301a];
      for (let k = 0; k < nT; k++) {
        const x = treeAt[k * 4], y = treeAt[k * 4 + 1], z = treeAt[k * 4 + 2], s = treeAt[k * 4 + 3], th = 2.6 * s, r = (2 + rnd2() * 0.6) * s;
        Q.setFromAxisAngle(UPV, rnd2() * TAU);
        M.compose(P.set(x, y, z), Q, Sc.set(s * 1.2, th, s * 1.2)); trk.setMatrixAt(k, M);
        M.compose(P.set(x, y + th + r * 0.5, z), Q, Sc.set(r, r * (0.95 + rnd2() * 0.25), r)); fol.setMatrixAt(k, M);
        fol.setColorAt(k, C.setHex(greens[Math.floor(rnd2() * greens.length)]));
      }
      fol.castShadow = trk.castShadow = quality !== 'performance'; fol.receiveShadow = true;
      fol.computeBoundingSphere(); trk.computeBoundingSphere();
      this.root.add(fol, trk);
    }
    this.anim.push(() => { const t = this.t || 0; this.blinkMat.emissiveIntensity = (t % 1.4) < 0.18 ? 6 : 0.2; this.neonMats.forEach((m, i) => { m.emissiveIntensity = Math.sin(t * (7 + i * 3.1)) + Math.sin(t * 13.7 + i) > 1.75 ? 0.4 : 2.6; }); });
    // Blutturm
    this.tower = new THREE.Group();
    const tb = this.landmarks.bloodTower, tc = new V3(0, 0, tb.z - 34);
    const body = new MeshBuilder(), veins = new MeshBuilder();
    let y = 0, r = 16;
    for (let k = 0; k < 10; k++) { body.box(tc.x - r, y, tc.z - r, tc.x + r, y + 32, tc.z + r, 0.05); veins.box(tc.x - r - 0.1, y + 10, tc.z - 0.6, tc.x + r + 0.1, y + 24, tc.z + 0.6, 1); veins.box(tc.x - 0.6, y + 10, tc.z - r - 0.1, tc.x + 0.6, y + 24, tc.z + r + 0.1, 1); y += 32; r *= 0.86; }
    body.cone(tc.x, y, tc.z, r, 40, 6);
    this.tower.add(body.mesh(pbr(0x140204, 0.3, 0.7)), veins.mesh(glowMat(0xff0a14, 5), false));
    const tr = FX.rift(0xff0a14, 9); tr.position.set(tc.x, y + 60, tc.z); this.tower.add(tr); this.anim.push(tr.userData.anim);
    this.towerBox = { x0: tc.x - 16, y0: 0, z0: tc.z - 16, x1: tc.x + 16, y1: 300, z1: tc.z + 16 };
    this.tower.visible = false;
    this.root.add(this.tower);
    // Verkehr
    this.cars = [];
    const count = quality === 'performance' ? 20 : quality === 'balanced' ? 36 : 60;
    const carGeo = new THREE.BoxGeometry(1.9, 0.75, 4.4), cabGeo = new THREE.BoxGeometry(1.7, 0.5, 2.1), lightGeo = new THREE.BoxGeometry(1.7, 0.18, 0.06);
    const paints = [0x111114, 0x6a0a0a, 0xaaaaaa, 0x0c1a40, 0xc8a020].map((c) => pbr(c, 0.25, 0.8));
    const headM = glowMat(0xfff4d8, 8), tailM = glowMat(0xff1010, 5);
    for (let k = 0; k < count; k++) {
      const g = new THREE.Group();
      const body = new THREE.Mesh(carGeo, paints[k % paints.length]); body.position.y = 0.7; g.add(body);
      const cab = new THREE.Mesh(cabGeo, paints[(k + 2) % paints.length]); cab.position.set(0, 1.3, -0.1); g.add(cab);
      const hl = new THREE.Mesh(lightGeo, headM); hl.position.set(0, 0.75, 2.22); g.add(hl);
      const tl = new THREE.Mesh(lightGeo, tailM); tl.position.set(0, 0.8, -2.22); g.add(tl);
      const alongX = k % 2 === 0, dir = rnd() < 0.5 ? 1 : -1, lane = ri(0, CITY.blocks + 1);
      const fixed = -half + lane * CITY.pitch + dir * 4;
      g.rotation.y = alongX ? (dir > 0 ? Math.PI / 2 : -Math.PI / 2) : (dir > 0 ? 0 : Math.PI);
      this.root.add(g);
      this.cars.push({ g, alongX, dir, fixed, s: rf(-half, half), v: rf(10, 19) });
    }
    this.traffic = (dt) => { for (const c of this.cars) { c.s += c.dir * c.v * dt; if (c.s > half + 40) c.s = -half - 40; if (c.s < -half - 40) c.s = half + 40; if (c.alongX) c.g.position.set(c.s, 0, c.fixed); else c.g.position.set(c.fixed, 0, c.s); } };
  }
}

// Leichte Skyline-Kulisse für Arenen, Zwischensequenzen und Titel
function buildSkyline(seed, quality, tod, clear, groundY = -60) {
  const rnd = seeded(seed);
  const root = new THREE.Group();
  const fac = [new MeshBuilder(), new MeshBuilder(), new MeshBuilder(), new MeshBuilder()], roofs = new MeshBuilder(), blink = new MeshBuilder();
  const n = quality === 'performance' ? 80 : quality === 'balanced' ? 140 : 210;
  for (let i = 0; i < n; i++) {
    const a = rnd() * TAU, d = clear + 12 + rnd() * 260 * (0.3 + rnd() * 0.7);
    const cx = Math.cos(a) * d, cz = Math.sin(a) * d, w = 10 + rnd() * 18, dd = 10 + rnd() * 18, h = 30 + rnd() * (d > 150 ? 200 : 110);
    fac[Math.floor(rnd() * 4)].box(cx - w / 2, groundY, cz - dd / 2, cx + w / 2, groundY + h, cz + dd / 2, 1 / 12);
    roofs.box(cx - w / 2, groundY + h, cz - dd / 2, cx + w / 2, groundY + h + 0.6, cz + dd / 2, 0.1);
    if (h > 120 && rnd() < 0.5) blink.box(cx - 0.4, groundY + h + 4, cz - 0.4, cx + 0.4, groundY + h + 4.8, cz + 0.4, 1);
  }
  for (let s = 0; s < 4; s++) if (!fac[s].empty) root.add(fac[s].mesh(new THREE.MeshStandardMaterial({ map: Tex.facade(s, false), emissiveMap: Tex.facade(s, true), emissive: 0xffffff, emissiveIntensity: tod === 'dusk' ? 0.9 : 1.7, roughness: 0.6, metalness: 0.2 }), false));
  root.add(roofs.mesh(pbr(0x333333, 0.8, 0), false));
  if (!blink.empty) root.add(blink.mesh(glowMat(0xff1a1a, 5), false));
  const g = new MeshBuilder(); const R = clear + 600;
  g.quad([-R, groundY, R], [R, groundY, R], [R, groundY, -R], [-R, groundY, -R], [0, 1, 0], [[0, 0], [60, 0], [60, 60], [0, 60]]);
  root.add(g.mesh(new THREE.MeshStandardMaterial({ map: Tex.asphalt(), roughness: 0.35 }), false));
  return root;
}
