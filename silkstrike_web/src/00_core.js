// =====================================================================
//  SILKSTRIKE – Blutturnier (Web) · Kern: Renderer, Schleife, Eingabe, Mathe
// =====================================================================
import * as THREE from 'three';
import { EffectComposer } from 'three/addons/postprocessing/EffectComposer.js';
import { RenderPass } from 'three/addons/postprocessing/RenderPass.js';
import { UnrealBloomPass } from 'three/addons/postprocessing/UnrealBloomPass.js';
import { OutputPass } from 'three/addons/postprocessing/OutputPass.js';
import { ShaderPass } from 'three/addons/postprocessing/ShaderPass.js';
import { GLTFLoader } from 'three/addons/loaders/GLTFLoader.js';
import * as SkeletonUtils from 'three/addons/utils/SkeletonUtils.js';

const V3 = THREE.Vector3;
const TAU = Math.PI * 2;
const clamp = (v, a, b) => Math.max(a, Math.min(b, v));
const lerp = (a, b, t) => a + (b - a) * t;
const damp = (c, t, l, dt) => lerp(c, t, 1 - Math.exp(-l * dt));
const wrapAngle = (a) => { while (a > Math.PI) a -= TAU; while (a < -Math.PI) a += TAU; return a; };
const dampAngle = (c, t, l, dt) => c + wrapAngle(t - c) * (1 - Math.exp(-l * dt));
const rand = (a, b) => a + Math.random() * (b - a);
const easeInOut = (x) => { x = clamp(x, 0, 1); return x < 0.5 ? 4 * x * x * x : 1 - Math.pow(-2 * x + 2, 3) / 2; };
const easeOut = (x) => 1 - Math.pow(1 - clamp(x, 0, 1), 3);
const smooth = (x) => { x = clamp(x, 0, 1); return x * x * (3 - 2 * x); };
function seeded(seed) {
  let s = seed >>> 0 || 1;
  return () => { s ^= s << 13; s >>>= 0; s ^= s >> 17; s ^= s << 5; s >>>= 0; return s / 4294967296; };
}
const yawOf = (x, z) => Math.atan2(x, z);

// ---------------------------------------------------------------- Einstellungen
const Settings = {
  data: { quality: 'balanced', blood: true, voices: true, music: true, sfx: 0.9, musicVol: 0.5, difficulty: 'normal', sens: 1.0, fps: false },
  load() {
    try {
      const raw = localStorage.getItem('silkstrike.web.settings');
      if (raw) Object.assign(this.data, JSON.parse(raw));
      else this.data.quality = (navigator.hardwareConcurrency || 4) >= 6 ? 'ultra' : 'balanced';
    } catch (e) { /* kein Speicher verfügbar */ }
  },
  save() { try { localStorage.setItem('silkstrike.web.settings', JSON.stringify(this.data)); } catch (e) { } },
};
Settings.load();
const DIFF = { easy: 0.55, normal: 0.8, hard: 1.0, brutal: 1.2 };
const Progress = {
  chapter: 0, done: false, seals: [],
  load() { try { const r = JSON.parse(localStorage.getItem('silkstrike.web.progress') || '{}'); Object.assign(this, r); } catch (e) { } },
  save() { try { localStorage.setItem('silkstrike.web.progress', JSON.stringify({ chapter: this.chapter, done: this.done, seals: this.seals })); } catch (e) { } },
};
Progress.load();

// ---------------------------------------------------------------- Renderer
const canvas = document.getElementById('game');
const renderer = new THREE.WebGLRenderer({ canvas, antialias: true, powerPreference: 'high-performance' });
renderer.toneMapping = THREE.ACESFilmicToneMapping;
renderer.toneMappingExposure = 1.05;
renderer.outputColorSpace = THREE.SRGBColorSpace;
renderer.shadowMap.enabled = true;
renderer.shadowMap.type = THREE.PCFSoftShadowMap;

const composer = new EffectComposer(renderer);
const renderPass = new RenderPass(new THREE.Scene(), new THREE.PerspectiveCamera());
const bloomPass = new UnrealBloomPass(new THREE.Vector2(256, 256), 0.7, 0.4, 0.9);
composer.addPass(renderPass);
composer.addPass(bloomPass);
composer.addPass(new OutputPass());
// Kino-Grading (Display-sRGB): Filmkurve, Teal/Orange-Split-Toning, Sättigung, Vignette, Korn, chromatische Aberration
const gradePass = new ShaderPass({
  uniforms: { tDiffuse: { value: null }, uTime: { value: 0 }, uRes: { value: new THREE.Vector2(1, 1) }, uGrain: { value: 0.04 }, uCA: { value: 1.0 }, uVig: { value: 0.34 } },
  vertexShader: 'varying vec2 vUv; void main(){ vUv = uv; gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0); }',
  fragmentShader: `
    uniform sampler2D tDiffuse; uniform float uTime, uGrain, uCA, uVig; uniform vec2 uRes; varying vec2 vUv;
    float hash(vec2 p) { p = fract(p * vec2(443.897, 441.423)); p += dot(p, p.yx + 19.19); return fract((p.x + p.y) * p.x); }
    void main() {
      vec2 c = vUv - 0.5; float r2 = dot(c, c);
      vec3 col;
      if (uCA > 0.0) { vec2 o = c * r2 * uCA * 0.012; col = vec3(texture2D(tDiffuse, vUv + o).r, texture2D(tDiffuse, vUv).g, texture2D(tDiffuse, vUv - o).b); }
      else col = texture2D(tDiffuse, vUv).rgb;
      col = clamp(col, 0.0, 1.0);
      col = mix(col, col * col * (3.0 - 2.0 * col), 0.3);
      float l = dot(col, vec3(0.2126, 0.7152, 0.0722));
      col += vec3(-0.018, 0.012, 0.04) * (1.0 - smoothstep(0.0, 0.45, l)) + vec3(0.045, 0.016, -0.03) * smoothstep(0.4, 1.0, l);
      l = dot(col, vec3(0.2126, 0.7152, 0.0722));
      col = mix(vec3(l), col, 1.1);
      col *= 1.0 - uVig * smoothstep(0.08, 0.5, r2);
      if (uGrain > 0.0) col += (hash(floor(vUv * uRes) + fract(uTime * 7.13) * vec2(97.3, 61.7)) - 0.5) * uGrain * (1.0 - 0.6 * l);
      gl_FragColor = vec4(clamp(col, 0.0, 1.0), 1.0);
    }`,
});
composer.addPass(gradePass);

function qualityScale() {
  const dpr = window.devicePixelRatio || 1;
  const q = Settings.data.quality;
  if (q === 'ultra') return Math.min(dpr, 2.5);
  if (q === 'balanced') return Math.min(dpr, 1.6);
  return Math.min(dpr, 1.1);
}
function applyQuality() {
  const q = Settings.data.quality;
  renderer.setPixelRatio(qualityScale());
  renderer.shadowMap.enabled = q !== 'performance';
  bloomPass.enabled = true;
  bloomPass.strength = q === 'performance' ? 0.45 : 0.7;
  gradePass.uniforms.uGrain.value = q === 'performance' ? 0 : 0.04;
  gradePass.uniforms.uCA.value = q === 'performance' ? 0 : 1.0;
  onResize();
}
function onResize() {
  const w = window.innerWidth, h = window.innerHeight;
  renderer.setSize(w, h, false);
  composer.setPixelRatio(qualityScale());
  composer.setSize(w, h);
  bloomPass.resolution.set(w * 0.5, h * 0.5);
  gradePass.uniforms.uRes.value.set(w * qualityScale(), h * qualityScale());
  if (Game.active && Game.active.camera) {
    Game.active.camera.aspect = w / Math.max(1, h);
    Game.active.camera.updateProjectionMatrix();
  }
}
window.addEventListener('resize', onResize);

// ---------------------------------------------------------------- Eingabe
const Input = {
  move: { x: 0, y: 0 },
  look: { x: 0, y: 0 },
  down: new Set(),
  pressed: new Map(),
  press(b) { if (!this.down.has(b)) { this.down.add(b); this.pressed.set(b, performance.now()); } },
  release(b) { this.down.delete(b); },
  isDown(b) { return this.down.has(b); },
  consume(b) {
    const t = this.pressed.get(b);
    if (t === undefined) return false;
    this.pressed.delete(b);
    return performance.now() - t < 450;
  },
  takeLook() { const l = { x: this.look.x, y: this.look.y }; this.look.x = 0; this.look.y = 0; return l; },
  reset() { this.down.clear(); this.pressed.clear(); this.move.x = 0; this.move.y = 0; this.look.x = 0; this.look.y = 0; },
};
// Tastatur (Desktop/iPad mit Tastatur)
const KEYMAP = { Space: ['jump'], KeyJ: ['attack', 'punch'], KeyK: ['kick', 'web'], KeyL: ['block'], ShiftLeft: ['web', 'block'],
  KeyQ: ['zip'], KeyE: ['interact', 'execute'], KeyU: ['special1'], KeyI: ['special2'], KeyO: ['brutal'], KeyF: ['execute'], Escape: ['pause'], Enter: ['skip'] };
const keysHeld = new Set();
function keyMove() {
  let x = 0, y = 0;
  if (keysHeld.has('KeyA') || keysHeld.has('ArrowLeft')) x -= 1;
  if (keysHeld.has('KeyD') || keysHeld.has('ArrowRight')) x += 1;
  if (keysHeld.has('KeyW') || keysHeld.has('ArrowUp')) y += 1;
  if (keysHeld.has('KeyS') || keysHeld.has('ArrowDown')) y -= 1;
  if (x || y || keysHeld.size) { Input.move.x = x; Input.move.y = y; }
}
window.addEventListener('keydown', (e) => {
  if (e.repeat) return;
  keysHeld.add(e.code);
  (KEYMAP[e.code] || []).forEach((b) => Input.press(b));
  if (e.code.startsWith('Key') || e.code.startsWith('Arrow')) keyMove();
});
window.addEventListener('keyup', (e) => {
  keysHeld.delete(e.code);
  (KEYMAP[e.code] || []).forEach((b) => Input.release(b));
  keyMove();
  if (!keysHeld.size) { Input.move.x = 0; Input.move.y = 0; }
});
// Kamera ziehen (Maus / freier Finger auf der rechten Seite)
let lookPointer = null;
canvas.addEventListener('pointerdown', (e) => {
  if (lookPointer !== null) return;
  lookPointer = { id: e.pointerId, x: e.clientX, y: e.clientY };
});
window.addEventListener('pointermove', (e) => {
  if (!lookPointer || e.pointerId !== lookPointer.id) return;
  Input.look.x += e.clientX - lookPointer.x;
  Input.look.y += e.clientY - lookPointer.y;
  lookPointer.x = e.clientX; lookPointer.y = e.clientY;
});
const endLook = (e) => { if (lookPointer && e.pointerId === lookPointer.id) lookPointer = null; };
window.addEventListener('pointerup', endLook);
window.addEventListener('pointercancel', endLook);

// Gamepad (Safari unterstützt PS/Xbox-Controller)
function pollGamepad() {
  const pads = navigator.getGamepads ? navigator.getGamepads() : [];
  const p = pads && Array.from(pads).find((g) => g);
  if (!p) return;
  const ax = (i) => (Math.abs(p.axes[i] || 0) > 0.15 ? p.axes[i] : 0);
  if (ax(0) || ax(1)) { Input.move.x = ax(0); Input.move.y = -ax(1); }
  else if (pollGamepad.used) { Input.move.x = 0; Input.move.y = 0; }
  pollGamepad.used = !!(ax(0) || ax(1));
  Input.look.x += ax(2) * 14; Input.look.y += ax(3) * 14;
  const map = [['jump', 'kick'], ['zip', 'special2'], ['attack', 'punch'], ['interact', 'special1'], ['web', 'execute'], ['web', 'block'], ['zip', 'brutal'], ['web', 'block']];
  map.forEach((names, i) => {
    const b = p.buttons[i];
    const was = pollGamepad.prev[i];
    const now = !!(b && b.pressed);
    if (now && !was) names.forEach((n) => Input.press(n));
    if (!now && was) names.forEach((n) => Input.release(n));
    pollGamepad.prev[i] = now;
  });
  const start = p.buttons[9] && p.buttons[9].pressed;
  if (start && !pollGamepad.prev[9]) Input.press('pause');
  if (!start && pollGamepad.prev[9]) Input.release('pause');
  pollGamepad.prev[9] = start;
}
pollGamepad.prev = [];
pollGamepad.used = false;

// ---------------------------------------------------------------- Spielschleife
const Game = {
  active: null, paused: false, time: 0, fps: 60,
  // Alte Szene abbauen, BEVOR die neue gebaut wird (sonst blendet dispose() die neuen Anzeigen aus)
  teardown() {
    const old = this.active;
    this.active = null;
    if (old && old.dispose) old.dispose();
    Input.reset();
    if (window.UI && UI.clearOverlays) UI.clearOverlays();
  },
  setController(c) {
    if (this.active && this.active !== c) this.teardown();
    this.active = c;
    if (c) { renderPass.scene = c.scene; renderPass.camera = c.camera; onResize(); }
  },
};
let last = performance.now();
let fpsAcc = 0, fpsFrames = 0;
function frame(now) {
  requestAnimationFrame(frame);
  let dt = (now - last) / 1000;
  last = now;
  if (!(dt > 0)) dt = 1 / 60;
  fpsAcc += Math.min(dt, 1); fpsFrames++;
  dt = Math.min(dt, 1 / 20);
  if (fpsAcc > 0.5) { Game.fps = Math.round(fpsFrames / fpsAcc); fpsAcc = 0; fpsFrames = 0; if (window.UI) UI.fps(Game.fps); }
  pollGamepad();
  if (window.UI) UI.tick(dt);
  const c = Game.active;
  if (c) {
    if (!Game.paused) { Game.time += dt; c.update(dt); }
    renderPass.scene = c.scene; renderPass.camera = c.camera;
    gradePass.uniforms.uTime.value = now / 1000;
    composer.render(dt);
  }
}

// ---------------------------------------------------------------- Texturen
const TexCache = new Map();
function canvasTex(key, w, h, draw, repeat = true) {
  if (TexCache.has(key)) return TexCache.get(key);
  const c = document.createElement('canvas');
  c.width = w; c.height = h;
  const g = c.getContext('2d');
  draw(g, w, h);
  const t = new THREE.CanvasTexture(c);
  t.colorSpace = THREE.SRGBColorSpace;
  if (repeat) { t.wrapS = t.wrapT = THREE.RepeatWrapping; }
  t.anisotropy = 4;
  TexCache.set(key, t);
  return t;
}
function noiseFill(g, w, h, base, amount, count, seed) {
  const r = seeded(seed);
  g.fillStyle = base; g.fillRect(0, 0, w, h);
  for (let i = 0; i < count; i++) {
    const v = Math.floor(r() * 255);
    g.fillStyle = `rgba(${v},${v},${v},${amount * r()})`;
    const s = 1 + r() * 3;
    g.fillRect(r() * w, r() * h, s, s);
  }
}
const Tex = {
  facade(style, lit) {
    return canvasTex('facade' + style + lit, 256, 256, (g, w, h) => {
      const r = seeded(77 + style * 31);
      const pal = [['#272b33', '#3b404a', '#0d1219'], ['#4a241b', '#6f6459', '#0c0d10'], ['#55534f', '#3a3a3a', '#101214'], ['#16141c', '#2a2433', '#08080d']][style % 4];
      if (lit) { g.fillStyle = '#000'; g.fillRect(0, 0, w, h); } else { noiseFill(g, w, h, pal[0], 0.12, 900, 5 + style); }
      const cw = w / 4, ch = h / 4;
      for (let y = 0; y < 4; y++) for (let x = 0; x < 4; x++) {
        const ww = style === 0 ? cw * 0.9 : cw * 0.56, wh = style === 0 ? ch * 0.76 : ch * 0.56;
        const px = x * cw + (cw - ww) / 2, py = y * ch + (ch - wh) * 0.6;
        const on = r() < (style === 3 ? 0.55 : 0.38);
        const warm = r() < 0.7;
        if (lit) {
          if (!on) continue;
          const grad = g.createLinearGradient(0, py, 0, py + wh);
          const c1 = warm ? 'rgba(255,190,110,' : (style === 3 ? 'rgba(255,60,150,' : 'rgba(150,200,255,');
          grad.addColorStop(0, c1 + '0.5)'); grad.addColorStop(1, c1 + '1)');
          g.fillStyle = grad; g.fillRect(px, py, ww, wh);
          if (r() < 0.4) { g.fillStyle = 'rgba(0,0,0,0.6)'; g.fillRect(px + ww * r() * 0.6, py + wh * 0.65, ww * 0.25, wh * 0.35); }
        } else {
          g.fillStyle = pal[1]; g.fillRect(px - 2, py - 2, ww + 4, wh + 4);
          g.fillStyle = on ? '#1d2531' : pal[2]; g.fillRect(px, py, ww, wh);
          g.fillStyle = 'rgba(255,255,255,0.05)'; g.fillRect(px, py, ww * 0.35, wh);
        }
      }
    });
  },
  asphalt() {
    return canvasTex('asphalt', 256, 256, (g, w, h) => {
      noiseFill(g, w, h, '#17181b', 0.25, 4000, 9);
      g.strokeStyle = 'rgba(0,0,0,0.7)'; g.lineWidth = 1;
      const r = seeded(4);
      for (let i = 0; i < 6; i++) { g.beginPath(); let x = r() * w, y = r() * h; g.moveTo(x, y); for (let k = 0; k < 10; k++) { x += (r() - 0.5) * 20; y += (r() - 0.5) * 20; g.lineTo(x, y); } g.stroke(); }
    });
  },
  concrete() { return canvasTex('concrete', 256, 256, (g, w, h) => noiseFill(g, w, h, '#5d5d5f', 0.18, 2500, 3)); },
  metal() {
    return canvasTex('metal', 256, 256, (g, w, h) => {
      noiseFill(g, w, h, '#6d7076', 0.15, 1500, 11);
      g.strokeStyle = '#2a2c30'; g.lineWidth = 3;
      for (let i = 0; i <= 4; i++) { g.beginPath(); g.moveTo(i * w / 4, 0); g.lineTo(i * w / 4, h); g.moveTo(0, i * h / 4); g.lineTo(w, i * h / 4); g.stroke(); }
    });
  },
  tiles() {
    return canvasTex('tiles', 256, 256, (g, w, h) => {
      g.fillStyle = '#3a3a3a'; g.fillRect(0, 0, w, h);
      const r = seeded(21);
      for (let y = 0; y < 8; y++) for (let x = 0; x < 8; x++) { const v = 150 + r() * 50; g.fillStyle = `rgb(${v * 0.92},${v},${v * 0.95})`; g.fillRect(x * 32 + 2, y * 32 + 2, 28, 28); }
    });
  },
  brick() {
    return canvasTex('brick', 256, 256, (g, w, h) => {
      g.fillStyle = '#2a2a2a'; g.fillRect(0, 0, w, h);
      const r = seeded(31);
      for (let y = 0; y < 16; y++) for (let x = -1; x < 9; x++) { const k = 0.75 + r() * 0.35; g.fillStyle = `rgb(${110 * k},${50 * k},${36 * k})`; g.fillRect(x * 32 + (y % 2 ? 16 : 0) + 1, y * 16 + 1, 30, 14); }
    });
  },
  sprite(kind) {
    return canvasTex('sprite' + kind, 64, 64, (g, w, h) => {
      const grd = g.createRadialGradient(32, 32, 0, 32, 32, 32);
      if (kind === 'soft') { grd.addColorStop(0, 'rgba(255,255,255,1)'); grd.addColorStop(0.4, 'rgba(255,255,255,0.6)'); grd.addColorStop(1, 'rgba(255,255,255,0)'); }
      else if (kind === 'drop') { grd.addColorStop(0, 'rgba(255,255,255,1)'); grd.addColorStop(0.55, 'rgba(255,255,255,0.95)'); grd.addColorStop(0.7, 'rgba(255,255,255,0)'); }
      else { grd.addColorStop(0, 'rgba(255,255,255,0.7)'); grd.addColorStop(0.6, 'rgba(255,255,255,0.25)'); grd.addColorStop(1, 'rgba(255,255,255,0)'); }
      g.fillStyle = grd; g.fillRect(0, 0, w, h);
    }, false);
  },
  splat() {
    return canvasTex('splat', 128, 128, (g) => {
      const r = seeded(99);
      g.fillStyle = 'rgba(90,0,4,0.95)';
      g.beginPath(); g.ellipse(64, 64, 34, 30, 0, 0, TAU); g.fill();
      for (let i = 0; i < 24; i++) { const a = r() * TAU, d = 20 + r() * 40, s = 2 + r() * 8; g.beginPath(); g.arc(64 + Math.cos(a) * d, 64 + Math.sin(a) * d, s, 0, TAU); g.fill(); }
    }, false);
  },
};

// Nachthimmel als Hintergrund + Umgebungslicht (IBL)
const pmrem = new THREE.PMREMGenerator(renderer);
const EnvCache = {};
function skyTexture(tod) {
  return canvasTex('sky' + tod, 1024, 512, (g, w, h) => {
    const grd = g.createLinearGradient(0, 0, 0, h);
    if (tod === 'dusk') { grd.addColorStop(0, '#12131f'); grd.addColorStop(0.38, '#3b2340'); grd.addColorStop(0.5, '#c65a32'); grd.addColorStop(0.56, '#2a1a22'); grd.addColorStop(1, '#09080b'); }
    else if (tod === 'stormNight') { grd.addColorStop(0, '#05070a'); grd.addColorStop(0.42, '#1a1f22'); grd.addColorStop(0.5, '#3a2a2c'); grd.addColorStop(0.56, '#141416'); grd.addColorStop(1, '#050506'); }
    else { grd.addColorStop(0, '#03040a'); grd.addColorStop(0.4, '#0d1426'); grd.addColorStop(0.5, '#3a2638'); grd.addColorStop(0.56, '#120f16'); grd.addColorStop(1, '#040406'); }
    g.fillStyle = grd; g.fillRect(0, 0, w, h);
    const r = seeded(tod.length * 13);
    if (tod !== 'stormNight') for (let i = 0; i < 500; i++) { g.fillStyle = `rgba(255,255,255,${r() * 0.8})`; g.fillRect(r() * w, r() * h * 0.45, 1.2, 1.2); }
    // Wolken
    for (let i = 0; i < 40; i++) {
      const x = r() * w, y = h * (0.15 + r() * 0.3), s = 40 + r() * 140;
      const cg = g.createRadialGradient(x, y, 0, x, y, s);
      const a = tod === 'stormNight' ? 0.35 : 0.12;
      cg.addColorStop(0, `rgba(70,60,70,${a})`); cg.addColorStop(1, 'rgba(0,0,0,0)');
      g.fillStyle = cg; g.fillRect(x - s, y - s, s * 2, s * 2);
    }
    // Mond
    if (tod === 'night') { const mg = g.createRadialGradient(w * 0.72, h * 0.18, 0, w * 0.72, h * 0.18, 60); mg.addColorStop(0, 'rgba(255,250,235,1)'); mg.addColorStop(0.2, 'rgba(255,245,220,0.9)'); mg.addColorStop(0.35, 'rgba(200,210,255,0.15)'); mg.addColorStop(1, 'rgba(0,0,0,0)'); g.fillStyle = mg; g.fillRect(w * 0.72 - 60, h * 0.18 - 60, 120, 120); }
    // Stadtglühen am Horizont
    const hg = g.createLinearGradient(0, h * 0.44, 0, h * 0.52);
    hg.addColorStop(0, 'rgba(255,90,60,0)'); hg.addColorStop(1, tod === 'dusk' ? 'rgba(255,140,80,0.35)' : 'rgba(200,60,80,0.28)');
    g.fillStyle = hg; g.fillRect(0, h * 0.44, w, h * 0.08);
  }, false);
}
function applyEnvironment(scene, tod, fogDensity) {
  const sky = skyTexture(tod);
  sky.mapping = THREE.EquirectangularReflectionMapping;
  scene.background = sky;
  if (!EnvCache[tod]) EnvCache[tod] = pmrem.fromEquirectangular(sky).texture;
  scene.environment = EnvCache[tod];
  scene.environmentIntensity = tod === 'dusk' ? 0.9 : 0.6;
  const fogColor = tod === 'dusk' ? 0x2a1b22 : (tod === 'stormNight' ? 0x121417 : 0x0d0f18);
  scene.fog = new THREE.FogExp2(fogColor, fogDensity);
}

// ---------------------------------------------------------------- Material-Helfer
const MatCache = new Map();
function pbr(color, rough = 0.6, metal = 0, emissive = null, ei = 1) {
  const key = [color, rough, metal, emissive, ei].join('|');
  if (MatCache.has(key)) return MatCache.get(key);
  const m = new THREE.MeshStandardMaterial({ color, roughness: rough, metalness: metal });
  if (emissive !== null) { m.emissive = new THREE.Color(emissive); m.emissiveIntensity = ei; }
  MatCache.set(key, m);
  return m;
}
const glowMat = (color, ei = 3) => new THREE.MeshStandardMaterial({ color: 0x050505, emissive: new THREE.Color(color), emissiveIntensity: ei, roughness: 0.5 });

// ---------------------------------------------------------------- Geometrie-Bauer (Welt-UVs)
class MeshBuilder {
  constructor() { this.p = []; this.n = []; this.uv = []; this.i = []; }
  get empty() { return this.i.length === 0; }
  quad(a, b, c, d, nrm, uvs) {
    const o = this.p.length / 3;
    for (const v of [a, b, c, d]) this.p.push(v[0], v[1], v[2]);
    for (let k = 0; k < 4; k++) this.n.push(nrm[0], nrm[1], nrm[2]);
    for (const t of uvs) this.uv.push(t[0], t[1]);
    this.i.push(o, o + 1, o + 2, o, o + 2, o + 3);
  }
  box(x0, y0, z0, x1, y1, z1, s = 0.1, bottom = false) {
    const sx = (x1 - x0) * s, sy = (y1 - y0) * s, sz = (z1 - z0) * s, ux = x0 * s, uz = z0 * s, vy = y0 * s;
    this.quad([x0, y0, z1], [x1, y0, z1], [x1, y1, z1], [x0, y1, z1], [0, 0, 1], [[ux, vy], [ux + sx, vy], [ux + sx, vy + sy], [ux, vy + sy]]);
    this.quad([x1, y0, z0], [x0, y0, z0], [x0, y1, z0], [x1, y1, z0], [0, 0, -1], [[ux, vy], [ux + sx, vy], [ux + sx, vy + sy], [ux, vy + sy]]);
    this.quad([x1, y0, z1], [x1, y0, z0], [x1, y1, z0], [x1, y1, z1], [1, 0, 0], [[uz, vy], [uz + sz, vy], [uz + sz, vy + sy], [uz, vy + sy]]);
    this.quad([x0, y0, z0], [x0, y0, z1], [x0, y1, z1], [x0, y1, z0], [-1, 0, 0], [[uz, vy], [uz + sz, vy], [uz + sz, vy + sy], [uz, vy + sy]]);
    this.quad([x0, y1, z1], [x1, y1, z1], [x1, y1, z0], [x0, y1, z0], [0, 1, 0], [[ux, uz + sz], [ux + sx, uz + sz], [ux + sx, uz], [ux, uz]]);
    if (bottom) this.quad([x0, y0, z0], [x1, y0, z0], [x1, y0, z1], [x0, y0, z1], [0, -1, 0], [[0, 0], [1, 0], [1, 1], [0, 1]]);
  }
  cyl(cx, cy, cz, r, h, seg = 10, s = 0.1) {
    for (let k = 0; k < seg; k++) {
      const a0 = k / seg * TAU, a1 = (k + 1) / seg * TAU;
      const x0 = cx + Math.sin(a0) * r, z0 = cz + Math.cos(a0) * r, x1 = cx + Math.sin(a1) * r, z1 = cz + Math.cos(a1) * r;
      const nm = [Math.sin((a0 + a1) / 2), 0, Math.cos((a0 + a1) / 2)];
      const u0 = a0 * r * s, u1 = a1 * r * s;
      this.quad([x0, cy, z0], [x1, cy, z1], [x1, cy + h, z1], [x0, cy + h, z0], nm, [[u0, cy * s], [u1, cy * s], [u1, (cy + h) * s], [u0, (cy + h) * s]]);
      const o = this.p.length / 3;
      this.p.push(cx, cy + h, cz, x0, cy + h, z0, x1, cy + h, z1);
      this.n.push(0, 1, 0, 0, 1, 0, 0, 1, 0);
      this.uv.push(0, 0, 1, 0, 0, 1);
      this.i.push(o, o + 1, o + 2);
    }
  }
  cone(cx, cy, cz, r, h, seg = 8) {
    for (let k = 0; k < seg; k++) {
      const a0 = k / seg * TAU, a1 = (k + 1) / seg * TAU;
      const o = this.p.length / 3;
      this.p.push(cx + Math.sin(a0) * r, cy, cz + Math.cos(a0) * r, cx + Math.sin(a1) * r, cy, cz + Math.cos(a1) * r, cx, cy + h, cz);
      const am = (a0 + a1) / 2, ny = r / Math.hypot(r, h);
      for (let q = 0; q < 3; q++) this.n.push(Math.sin(am), ny, Math.cos(am));
      this.uv.push(0, 0, 1, 0, 0.5, 1);
      this.i.push(o, o + 1, o + 2);
    }
  }
  mesh(material, shadows = true) {
    const g = new THREE.BufferGeometry();
    g.setAttribute('position', new THREE.Float32BufferAttribute(this.p, 3));
    g.setAttribute('normal', new THREE.Float32BufferAttribute(this.n, 3));
    g.setAttribute('uv', new THREE.Float32BufferAttribute(this.uv, 2));
    g.setIndex(this.i);
    g.computeBoundingSphere();
    const m = new THREE.Mesh(g, material);
    m.castShadow = shadows; m.receiveShadow = true;
    return m;
  }
}
