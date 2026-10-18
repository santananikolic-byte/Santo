// =====================================================================
//  Effekte: Partikel (Blut, Funken, Feuer, Schatten…), Blutlachen, Netze,
//  Regen, Riss-Portale, Kamerawackeln
// =====================================================================
class ParticleLayer {
  constructor(cap, additive) {
    this.cap = cap; this.n = 0;
    this.pos = new Float32Array(cap * 3); this.col = new Float32Array(cap * 3); this.alpha = new Float32Array(cap); this.size = new Float32Array(cap);
    this.vel = new Float32Array(cap * 3); this.life = new Float32Array(cap); this.max = new Float32Array(cap); this.grav = new Float32Array(cap); this.drag = new Float32Array(cap); this.grow = new Float32Array(cap); this.fade = new Float32Array(cap);
    const g = new THREE.BufferGeometry();
    this.aPos = new THREE.BufferAttribute(this.pos, 3); this.aPos.setUsage(THREE.DynamicDrawUsage);
    this.aCol = new THREE.BufferAttribute(this.col, 3); this.aCol.setUsage(THREE.DynamicDrawUsage);
    this.aAlpha = new THREE.BufferAttribute(this.alpha, 1); this.aAlpha.setUsage(THREE.DynamicDrawUsage);
    this.aSize = new THREE.BufferAttribute(this.size, 1); this.aSize.setUsage(THREE.DynamicDrawUsage);
    g.setAttribute('position', this.aPos); g.setAttribute('color', this.aCol); g.setAttribute('alpha', this.aAlpha); g.setAttribute('size', this.aSize);
    g.setDrawRange(0, 0);
    this.mat = new THREE.ShaderMaterial({
      uniforms: { map: { value: Tex.sprite(additive ? 'soft' : 'drop') }, scale: { value: 600 } },
      vertexShader: `attribute float alpha; attribute float size; varying vec3 vC; varying float vA; uniform float scale;
        void main(){ vC = color; vA = alpha; vec4 mv = modelViewMatrix * vec4(position,1.0); gl_PointSize = size * scale / max(0.1, -mv.z); gl_Position = projectionMatrix * mv; }`,
      fragmentShader: `uniform sampler2D map; varying vec3 vC; varying float vA;
        void main(){ vec4 t = texture2D(map, gl_PointCoord); if (t.a * vA < 0.01) discard; gl_FragColor = vec4(vC * t.rgb, t.a * vA); }`,
      transparent: true, depthWrite: false, vertexColors: true,
      blending: additive ? THREE.AdditiveBlending : THREE.NormalBlending,
    });
    this.points = new THREE.Points(g, this.mat);
    this.points.frustumCulled = false;
    this.points.renderOrder = additive ? 3 : 2;
  }
  emit(p, v, color, size, life, grav = 0, drag = 0, grow = 0, alpha = 1) {
    if (this.n >= this.cap) return;
    const i = this.n++;
    this.pos[i * 3] = p.x; this.pos[i * 3 + 1] = p.y; this.pos[i * 3 + 2] = p.z;
    this.vel[i * 3] = v.x; this.vel[i * 3 + 1] = v.y; this.vel[i * 3 + 2] = v.z;
    this.col[i * 3] = color.r; this.col[i * 3 + 1] = color.g; this.col[i * 3 + 2] = color.b;
    this.size[i] = size; this.life[i] = life; this.max[i] = life; this.grav[i] = grav; this.drag[i] = drag; this.grow[i] = grow; this.alpha[i] = alpha; this.fade[i] = alpha;
  }
  update(dt, floor) {
    let i = 0;
    while (i < this.n) {
      this.life[i] -= dt;
      if (this.life[i] <= 0) { this.copy(this.n - 1, i); this.n--; continue; }
      const k = i * 3, d = Math.max(0, 1 - this.drag[i] * dt);
      this.vel[k] *= d; this.vel[k + 1] = this.vel[k + 1] * d - this.grav[i] * dt; this.vel[k + 2] *= d;
      this.pos[k] += this.vel[k] * dt; this.pos[k + 1] += this.vel[k + 1] * dt; this.pos[k + 2] += this.vel[k + 2] * dt;
      if (this.grav[i] > 0 && this.pos[k + 1] < floor) { this.pos[k + 1] = floor; this.vel[k] *= 0.3; this.vel[k + 1] = 0; this.vel[k + 2] *= 0.3; }
      this.size[i] += this.grow[i] * dt;
      const t = this.life[i] / this.max[i];
      this.alpha[i] = this.fade[i] * Math.min(1, t * 2.5);
      i++;
    }
    this.points.geometry.setDrawRange(0, this.n);
    this.aPos.needsUpdate = true; this.aCol.needsUpdate = true; this.aAlpha.needsUpdate = true; this.aSize.needsUpdate = true;
  }
  copy(a, b) {
    for (let c = 0; c < 3; c++) { this.pos[b * 3 + c] = this.pos[a * 3 + c]; this.vel[b * 3 + c] = this.vel[a * 3 + c]; this.col[b * 3 + c] = this.col[a * 3 + c]; }
    this.size[b] = this.size[a]; this.life[b] = this.life[a]; this.max[b] = this.max[a]; this.grav[b] = this.grav[a]; this.drag[b] = this.drag[a]; this.grow[b] = this.grow[a]; this.alpha[b] = this.alpha[a]; this.fade[b] = this.fade[a];
  }
  clear() { this.n = 0; this.points.geometry.setDrawRange(0, 0); }
}

const FX = {
  scene: null, add: null, norm: null, pools: [], anim: [], lights: [], floor: 0,
  attach(scene, floor = 0) {
    const q = Settings.data.quality;
    const cap = q === 'performance' ? 1500 : 4000;
    if (!this.add || this.add.cap !== cap) { this.add = new ParticleLayer(cap, true); this.norm = new ParticleLayer(cap, false); }
    this.add.clear(); this.norm.clear();
    this.scene = scene; this.floor = floor;
    scene.add(this.add.points); scene.add(this.norm.points);
    this.pools = []; this.anim = []; this.lights = [];
    for (let k = 0; k < 3; k++) { const l = new THREE.PointLight(0xffffff, 0, 10, 2); l.position.set(0, -50, 0); scene.add(l); this.lights.push({ l, life: 0, max: 1, i: 0 }); }
  },
  mult() { const q = Settings.data.quality; return q === 'performance' ? 0.45 : q === 'balanced' ? 0.75 : 1; },
  _c: new THREE.Color(), _v: new V3(), _p: new V3(),
  spray(layer, p, n, speed, dir, spread, color, size, life, grav, drag = 1, grow = 0, alpha = 1, jitter = 0.05) {
    const cnt = Math.max(1, Math.round(n * this.mult()));
    const c = this._c.set(color);
    for (let i = 0; i < cnt; i++) {
      const v = this._v.set(rand(-1, 1), rand(-1, 1), rand(-1, 1)).normalize().multiplyScalar(spread).add(dir).normalize().multiplyScalar(speed * rand(0.4, 1.1));
      const q = this._p.set(p.x + rand(-jitter, jitter), p.y + rand(-jitter, jitter), p.z + rand(-jitter, jitter));
      layer.emit(q, v, c, size * rand(0.6, 1.3), life * rand(0.6, 1.2), grav, drag, grow, alpha);
    }
  },
  burst(kind, p, scale = 1, dir = new V3(0, 1, 0), color = null) {
    if (!this.add || !this.scene) return;
    const blood = Settings.data.blood;
    const d = dir.clone().normalize();
    const s = scale;
    switch (kind) {
      case 'bloodSpray':
        if (!blood) { this.burst('sparks', p, s, dir); return; }
        this.spray(this.norm, p, 70 * s, 6 * Math.sqrt(s), d, 0.55, color || 0x5a0006, 0.07, 1.4, 12, 0.6);
        this.spray(this.norm, p, 18 * s, 1.5, d, 1, 0x3a0003, 0.18, 0.7, 4, 2, 0.2, 0.8);
        break;
      case 'bloodBurst':
        if (!blood) { this.burst('smoke', p, s); this.burst('sparks', p, s); return; }
        this.spray(this.norm, p, 140 * s, 7 * Math.sqrt(s), new V3(0, 0.6, 0), 1.4, 0x600007, 0.08, 1.6, 12, 0.5);
        this.spray(this.norm, p, 30 * s, 2, new V3(0, 0.2, 0), 1.5, 0x2c0002, 0.3, 0.9, 2, 2, 0.4, 0.8);
        break;
      case 'bloodPool': this.pool(p, s); break;
      case 'sparks': this.spray(this.add, p, 40 * s, 8, d, 0.8, color || 0xffc070, 0.05, 0.45, 10, 1.5); break;
      case 'hitFlash':
        this.spray(this.add, p, 1, 0.01, d, 0, color || 0xfff0d0, 0.9 * s, 0.09, 0, 0, 4, 1, 0);
        this.spray(this.add, p, 12 * s, 6, d, 1.2, 0xffffff, 0.06, 0.2, 0, 3);
        this.light(p, color || 0xffe0c0, 3 * s, 6, 0.08);
        break;
      case 'fireBurst':
        this.spray(this.add, p, 60 * s, 2.5, new V3(0, 1, 0), 0.7, color || 0xff6a14, 0.35 * s, 0.7, -2, 1.5, 0.4);
        this.spray(this.add, p, 20 * s, 4, new V3(0, 1, 0), 1, 0xffd060, 0.08, 0.6, -1, 1);
        this.light(p, 0xff7a20, 4 * s, 10, 0.4);
        break;
      case 'embers': this.spray(this.add, p, 30 * s, 1.5, new V3(0, 1, 0), 1, color || 0xff8a30, 0.05, 1.6, -0.8, 0.5); break;
      case 'iceShatter': this.spray(this.add, p, 60 * s, 6, d, 1.2, color || 0xb8e4ff, 0.08, 0.9, 10, 0.8); break;
      case 'smoke': this.spray(this.norm, p, 25 * s, 1.2, new V3(0, 1, 0), 1, color || 0x2a2a2e, 0.5 * s, 1.8, -0.3, 0.8, 0.8, 0.5); break;
      case 'dust': this.spray(this.norm, p, 30 * s, 3, new V3(0, 0.15, 0), 2, 0x6a6058, 0.35 * s, 0.9, 0.5, 2.5, 0.8, 0.45); break;
      case 'shadowBurst':
        this.spray(this.norm, p, 50 * s, 3.5, new V3(0, 0.5, 0), 1.5, 0x07020c, 0.35 * s, 0.9, -0.5, 2, 0.5, 0.85);
        this.spray(this.add, p, 40 * s, 4, new V3(0, 0.5, 0), 1.5, color || 0x8a3dff, 0.12, 0.7, 0, 2);
        this.light(p, color || 0x8a3dff, 3 * s, 8, 0.3);
        break;
      case 'webHit': this.spray(this.add, p, 30 * s, 4, d, 1, 0xf0f4ff, 0.05, 0.4, 3, 2); break;
      case 'riftPortal': this.spray(this.add, p, 60 * s, 3, d, 1.5, color || 0xff1030, 0.15, 0.8, 0, 2); this.light(p, 0xff1030, 4, 12, 0.6); break;
      case 'explosion':
        this.burst('fireBurst', p, s * 1.6, dir, color);
        this.burst('smoke', p, s * 1.3);
        this.burst('sparks', p, s * 1.5, dir);
        this.light(p, 0xffa040, 8 * s, 16, 0.25);
        break;
      case 'electric': this.spray(this.add, p, 40 * s, 9, d, 1.5, color || 0x9ad8ff, 0.04, 0.25, 0, 1); break;
      case 'ash': this.spray(this.norm, p, 80 * s, 1.2, new V3(0, 1, 0), 1.5, 0x3a3634, 0.06, 2.4, -0.2, 0.6); break;
      default: this.spray(this.add, p, 20 * s, 3, d, 1, color || 0xffffff, 0.06, 0.4, 2, 1);
    }
  },
  emberAt(p) { if (this.add) this.add.emit(p, new V3(rand(-0.3, 0.3), rand(0.5, 1.5), rand(-0.3, 0.3)), this._c.set(0xff7a20), 0.07, 0.6, -0.5, 0.5, 0, 1); },
  light(p, color, intensity, dist, life) {
    if (!this.lights.length) return;
    let o = this.lights[0];
    for (const x of this.lights) if (x.life < o.life) o = x;
    o.l.color.set(color); o.l.distance = dist; o.l.position.copy(p);
    o.life = life; o.max = life; o.i = intensity * 2.5; o.l.intensity = o.i;
  },
  pool(p, s = 1) {
    if (!Settings.data.blood || !this.scene) return;
    const m = new THREE.MeshStandardMaterial({ map: Tex.splat(), transparent: true, roughness: 0.15, metalness: 0.2, color: 0xffffff, depthWrite: false, polygonOffset: true, polygonOffsetFactor: -2 });
    const mesh = new THREE.Mesh(new THREE.PlaneGeometry(1, 1), m);
    mesh.rotation.x = -Math.PI / 2; mesh.rotation.z = rand(0, TAU);
    mesh.position.set(p.x, p.y + 0.015 + this.pools.length * 0.0005, p.z);
    mesh.scale.setScalar(0.1);
    mesh.renderOrder = 1;
    this.scene.add(mesh);
    this.pools.push({ mesh, t: 0, size: 1.4 * s * rand(0.8, 1.2) });
    while (this.pools.length > 24) { const o = this.pools.shift(); o.mesh.parent && o.mesh.parent.remove(o.mesh); }
  },
  update(dt, camera) {
    if (!this.add) return;
    this.add.update(dt, this.floor); this.norm.update(dt, this.floor + 0.01);
    const sc = window.innerHeight * 0.9;
    this.add.mat.uniforms.scale.value = sc; this.norm.mat.uniforms.scale.value = sc;
    for (const pl of this.pools) { pl.t += dt; const k = Math.min(1, pl.t / 1.5); pl.mesh.scale.setScalar(Math.max(0.1, pl.size * easeOut(k))); if (pl.t > 20) pl.mesh.material.opacity = Math.max(0, 1 - (pl.t - 20) / 4); }
    for (const o of this.lights) { if (o.life > 0) { o.life -= dt; o.l.intensity = o.i * Math.max(0, o.life / o.max); } else o.l.intensity = 0; }
    for (const a of this.anim) a(dt);
  },
  rift(color = 0xff1030, scale = 1) {
    const g = new THREE.Group();
    const add = (geo, op) => { const m = new THREE.MeshBasicMaterial({ color, transparent: true, opacity: op, blending: THREE.AdditiveBlending, depthWrite: false, side: THREE.DoubleSide }); const me = new THREE.Mesh(geo, m); g.add(me); return me; };
    const disc = add(new THREE.CircleGeometry(1.1, 32), 0.35);
    const core = new THREE.Mesh(new THREE.CircleGeometry(0.75, 32), new THREE.MeshBasicMaterial({ color: 0x050005 }));
    core.position.z = -0.01; g.add(core);
    const rings = [add(new THREE.TorusGeometry(1.25, 0.05, 6, 48), 0.9), add(new THREE.TorusGeometry(1.5, 0.03, 6, 48), 0.6), add(new THREE.TorusGeometry(1.8, 0.02, 6, 48), 0.4)];
    const light = new THREE.PointLight(color, 6 * scale, 14 * scale, 2);
    g.add(light);
    g.scale.setScalar(scale);
    let t = rand(0, 10);
    const fn = (dt) => { t += dt; rings[0].rotation.z += dt * 1.2; rings[1].rotation.z -= dt * 0.8; rings[2].rotation.x = Math.sin(t * 0.7) * 0.4; disc.material.opacity = 0.3 + 0.15 * Math.sin(t * 3); light.intensity = 6 * scale * (0.8 + 0.3 * Math.sin(t * 4)); g.lookAtCam && g.lookAtCam(); };
    g.userData.anim = fn;
    return g;
  },
};

class WebLine {
  constructor(color = 0xf0f4ff, radius = 0.015) {
    this.mesh = new THREE.Mesh(new THREE.CylinderGeometry(radius, radius, 1, 5, 1, true), new THREE.MeshBasicMaterial({ color }));
    this.mesh.visible = false;
    this.mesh.frustumCulled = false;
  }
  set(a, b) {
    const d = b.clone().sub(a), len = d.length();
    if (len < 0.01) { this.mesh.visible = false; return; }
    this.mesh.visible = true;
    this.mesh.position.copy(a).addScaledVector(d, 0.5);
    this.mesh.scale.set(1, len, 1);
    this.mesh.quaternion.setFromUnitVectors(new V3(0, 1, 0), d.divideScalar(len));
  }
  hide() { this.mesh.visible = false; }
}

class Shake {
  constructor() { this.trauma = 0; this.t = 0; }
  add(x) { this.trauma = Math.min(1, this.trauma + x); }
  update(dt) {
    this.t += dt; this.trauma = Math.max(0, this.trauma - dt * 1.3);
    const a = this.trauma * this.trauma, t = this.t * 24;
    return { x: a * 0.28 * (Math.sin(t * 1.1) + Math.sin(t * 2.3) * 0.5), y: a * 0.22 * (Math.sin(t * 1.7 + 1) + Math.sin(t * 2.9) * 0.4), roll: a * 0.06 * Math.sin(t * 1.3 + 2) };
  }
}

class Rain {
  constructor(count = 1400) {
    const q = Settings.data.quality;
    this.n = Math.round(count * (q === 'performance' ? 0.4 : q === 'balanced' ? 0.7 : 1));
    const pos = new Float32Array(this.n * 6);
    this.geo = new THREE.BufferGeometry();
    this.geo.setAttribute('position', new THREE.BufferAttribute(pos, 3));
    this.lines = new THREE.LineSegments(this.geo, new THREE.LineBasicMaterial({ color: 0x9aaabb, transparent: true, opacity: 0.35 }));
    this.lines.frustumCulled = false;
    this.p = []; for (let i = 0; i < this.n; i++) this.p.push([rand(-25, 25), rand(-5, 30), rand(-25, 25)]);
  }
  update(dt, cam) {
    const a = this.geo.attributes.position.array;
    for (let i = 0; i < this.n; i++) {
      const q = this.p[i];
      q[1] -= 28 * dt; q[0] -= 3 * dt;
      if (q[1] < -8) { q[1] = rand(15, 30); q[0] = rand(-25, 25); q[2] = rand(-25, 25); }
      const x = cam.position.x + q[0], y = cam.position.y + q[1], z = cam.position.z + q[2];
      a[i * 6] = x; a[i * 6 + 1] = y; a[i * 6 + 2] = z; a[i * 6 + 3] = x + 0.08; a[i * 6 + 4] = y + 0.7; a[i * 6 + 5] = z;
    }
    this.geo.attributes.position.needsUpdate = true;
  }
}
