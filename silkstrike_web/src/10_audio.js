// =====================================================================
//  Audio: synthetisierte Effekte, generative Musik, deutsche Sprachausgabe
// =====================================================================
const Audio = {
  ctx: null, master: null, sfxGain: null, musicGain: null, buffers: {}, mood: 'none', musicTimer: null, step: 0, slow: 1,
  start() {
    if (this.ctx) { if (this.ctx.state === 'suspended') this.ctx.resume(); return; }
    const AC = window.AudioContext || window.webkitAudioContext;
    if (!AC) return;
    this.ctx = new AC();
    this.master = this.ctx.createGain();
    this.master.connect(this.ctx.destination);
    const comp = this.ctx.createDynamicsCompressor();
    comp.threshold.value = -14; comp.ratio.value = 4;
    comp.connect(this.master);
    this.sfxGain = this.ctx.createGain(); this.sfxGain.connect(comp);
    this.musicGain = this.ctx.createGain(); this.musicGain.connect(comp);
    this.apply();
    this.build();
    if (this.mood !== 'none') this.setMusic(this.mood, true);
  },
  apply() {
    if (!this.ctx) return;
    const d = Settings.data;
    this.sfxGain.gain.value = d.sfx;
    this.musicGain.gain.value = d.music ? d.musicVol * 0.55 : 0;
  },
  // ---- Klangsynthese ------------------------------------------------
  make(dur, fn) {
    const sr = this.ctx.sampleRate, n = Math.floor(sr * dur);
    const b = this.ctx.createBuffer(1, n, sr), d = b.getChannelData(0);
    let lp = 0;
    for (let i = 0; i < n; i++) { const t = i / sr; d[i] = fn(t, t / dur, Math.random() * 2 - 1, (x, k) => (lp += (x - lp) * k)); }
    return b;
  },
  build() {
    const env = (p, a, r) => (p < a ? p / a : Math.pow(1 - (p - a) / (1 - a), r));
    const sin = Math.sin, PI2 = Math.PI * 2;
    const B = this.buffers, m = this.make.bind(this);
    B.punchLight = m(0.16, (t, p, n, lp) => (lp(n, 0.35) * 0.9 + sin(PI2 * (180 - 120 * p) * t) * 0.8) * env(p, 0.02, 3));
    B.punchHeavy = m(0.32, (t, p, n, lp) => (lp(n, 0.25) * 0.8 + sin(PI2 * (120 - 80 * p) * t) * 1.1 + sin(PI2 * 260 * t) * 0.2 * (1 - p)) * env(p, 0.01, 2.5));
    B.kick = m(0.22, (t, p, n, lp) => (lp(n, 0.4) * 0.7 + sin(PI2 * (150 - 90 * p) * t)) * env(p, 0.02, 2.5));
    B.block = m(0.18, (t, p, n) => (n * 0.4 + sin(PI2 * 900 * t) * 0.5 + sin(PI2 * 1370 * t) * 0.3) * env(p, 0.01, 4));
    B.whoosh = m(0.3, (t, p, n, lp) => lp(n, 0.08 + 0.3 * sin(Math.PI * p)) * sin(Math.PI * p) * 1.2);
    B.webShoot = m(0.25, (t, p, n, lp) => (sin(PI2 * (2400 - 1900 * p) * t) * 0.4 + lp(n, 0.5) * 0.4) * env(p, 0.02, 2));
    B.webZip = m(0.4, (t, p, n, lp) => (sin(PI2 * (600 + 1800 * p) * t) * 0.3 + lp(n, 0.3) * 0.5) * env(p, 0.05, 1.5));
    B.land = m(0.25, (t, p, n, lp) => (lp(n, 0.15) + sin(PI2 * (90 - 40 * p) * t)) * env(p, 0.01, 3));
    B.bodyFall = m(0.4, (t, p, n, lp) => (lp(n, 0.12) * 1.2 + sin(PI2 * (70 - 30 * p) * t)) * env(p, 0.01, 2.5));
    B.boneCrack = m(0.25, (t, p, n) => (n * (Math.random() < 0.08 ? 1 : 0.15) + sin(PI2 * 320 * t) * 0.3) * env(p, 0.005, 3));
    B.gore = m(0.5, (t, p, n, lp) => (lp(n, 0.06 + 0.1 * sin(PI2 * 9 * t)) * 1.6 + sin(PI2 * (110 - 60 * p) * t) * 0.6) * env(p, 0.02, 1.8));
    B.slice = m(0.3, (t, p, n, lp) => (n - lp(n, 0.2)) * 0.9 * env(p, 0.01, 2.5) + sin(PI2 * (3000 - 2000 * p) * t) * 0.15 * (1 - p));
    B.fire = m(0.8, (t, p, n, lp) => lp(n, 0.1) * (0.6 + 0.4 * sin(PI2 * 7 * t)) * env(p, 0.15, 1.2) * 1.3);
    B.explosion = m(1.2, (t, p, n, lp) => (lp(n, 0.05) * 1.8 + sin(PI2 * (60 - 30 * p) * t) * 0.8) * env(p, 0.01, 1.6));
    B.teleport = m(0.45, (t, p) => (sin(PI2 * (200 + 1400 * p * p) * t) * 0.5 + sin(PI2 * (220 + 1300 * p) * t) * 0.3) * env(p, 0.1, 1.5));
    B.chain = m(0.45, (t, p, n) => ((Math.floor(t * 40) % 2 ? 1 : 0.3) * (n * 0.3 + sin(PI2 * 1800 * t) * 0.3)) * env(p, 0.02, 1.5));
    B.roar = m(1.1, (t, p, n, lp) => (lp(n, 0.07) * 0.9 + sin(PI2 * (85 + 20 * sin(PI2 * 6 * t)) * t) * 0.7) * env(p, 0.15, 1.3));
    B.ui = m(0.08, (t, p) => sin(PI2 * 1200 * t) * 0.35 * env(p, 0.05, 3));
    B.uiConfirm = m(0.16, (t, p) => (sin(PI2 * 660 * t) + sin(PI2 * 990 * t) * 0.6) * 0.3 * env(p, 0.03, 2.5));
    B.heartbeat = m(0.7, (t) => sin(PI2 * 55 * t) * (Math.exp(-((t - 0.05) ** 2) / 0.0008) + 0.8 * Math.exp(-((t - 0.3) ** 2) / 0.0008)) * 1.4);
    B.thunder = m(2.5, (t, p, n, lp) => lp(n, 0.03 + 0.05 * (1 - p)) * 2.4 * env(p, 0.02, 1.4));
    B.riftHum = m(1.8, (t, p) => (sin(PI2 * 55 * t) + sin(PI2 * 82.4 * t) * 0.6 + sin(PI2 * 110.5 * t) * 0.3) * 0.5 * env(p, 0.2, 1));
    B.metalHit = m(0.5, (t, p, n) => (sin(PI2 * 420 * t) * 0.5 + sin(PI2 * 1130 * t) * 0.35 + n * 0.2) * env(p, 0.005, 2));
    B.announceBoom = m(1.4, (t, p, n, lp) => (sin(PI2 * (48 - 14 * p) * t) * 1.2 + lp(n, 0.04) * 0.6) * env(p, 0.01, 1.4));
    const alias = { swingRelease: 'whoosh', uiSelect: 'ui', uiBack: 'ui', electric: 'block', ice: 'block', crowd: 'riftHum' };
    for (const k in alias) B[k] = B[alias[k]];
  },
  play(name, vol = 1, pitch = 1) {
    if (!this.ctx || !this.buffers[name]) return;
    const s = this.ctx.createBufferSource();
    s.buffer = this.buffers[name];
    s.playbackRate.value = pitch * (0.94 + Math.random() * 0.12) * (this.slow < 1 ? 0.7 : 1);
    const g = this.ctx.createGain(); g.gain.value = vol;
    s.connect(g); g.connect(this.sfxGain);
    s.start();
  },
  // ---- Musik ---------------------------------------------------------
  setMusic(mood, force = false) {
    if (mood === this.mood && !force) return;
    this.mood = mood;
    if (!this.ctx) return;
    if (this.musicTimer) clearInterval(this.musicTimer);
    this.musicTimer = null;
    if (this.drone) { const d = this.drone; d.g.gain.setTargetAtTime(0, this.ctx.currentTime, 0.4); setTimeout(() => { try { d.o.forEach((o) => o.stop()); } catch (e) { } }, 1500); this.drone = null; }
    if (mood === 'none') return;
    const roots = { menu: 41.2, roam: 46.25, tension: 43.65, combat: 55, boss: 41.2, sad: 49, victory: 65.4 };
    const root = roots[mood] || 49;
    const g = this.ctx.createGain(); g.gain.value = 0; g.connect(this.musicGain);
    const filt = this.ctx.createBiquadFilter(); filt.type = 'lowpass'; filt.frequency.value = mood === 'victory' ? 2400 : 900; filt.connect(g);
    const o = [];
    for (const [mul, type, vol] of [[1, 'sawtooth', 0.12], [1.5, 'sawtooth', 0.07], [2.003, 'triangle', 0.09], [mood === 'victory' || mood === 'menu' ? 2.52 : 2.38, 'sine', 0.05]]) {
      const osc = this.ctx.createOscillator(); osc.type = type; osc.frequency.value = root * mul;
      const og = this.ctx.createGain(); og.gain.value = vol; osc.connect(og); og.connect(filt); osc.start(); o.push(osc);
    }
    g.gain.setTargetAtTime(1, this.ctx.currentTime, 1.2);
    this.drone = { g, o, filt };
    const bpm = { combat: 132, boss: 120, tension: 96, roam: 104, menu: 80, sad: 70, victory: 100 }[mood] || 100;
    const stepDur = 60 / bpm / 2;
    let next = this.ctx.currentTime + 0.1;
    this.step = 0;
    const perc = mood === 'combat' || mood === 'boss' || mood === 'tension' || mood === 'roam';
    this.musicTimer = setInterval(() => {
      if (!this.ctx) return;
      while (next < this.ctx.currentTime + 0.25) {
        const st = this.step % 16;
        if (perc) {
          if (st % 4 === 0 || (mood === 'combat' && st === 10)) this.hit(next, 'kick');
          if (st === 4 || st === 12) this.hit(next, 'snare');
          if (mood !== 'roam' && st % 2 === 1) this.hit(next, 'hat');
        }
        if (st % 8 === 0) this.pluck(next, root * [4, 4.76, 3.56, 4.24][(this.step / 8) % 4 | 0], mood);
        this.step++;
        next += stepDur;
      }
    }, 80);
  },
  hit(t, kind) {
    const c = this.ctx;
    if (kind === 'kick') {
      const o = c.createOscillator(), g = c.createGain();
      o.frequency.setValueAtTime(130, t); o.frequency.exponentialRampToValueAtTime(40, t + 0.18);
      g.gain.setValueAtTime(0.55, t); g.gain.exponentialRampToValueAtTime(0.001, t + 0.3);
      o.connect(g); g.connect(this.musicGain); o.start(t); o.stop(t + 0.32);
    } else {
      const s = c.createBufferSource(); s.buffer = this.buffers.punchLight;
      const f = c.createBiquadFilter(); f.type = kind === 'hat' ? 'highpass' : 'bandpass'; f.frequency.value = kind === 'hat' ? 7000 : 1800;
      const g = c.createGain(); g.gain.value = kind === 'hat' ? 0.12 : 0.35;
      s.connect(f); f.connect(g); g.connect(this.musicGain); s.start(t);
    }
  },
  pluck(t, f, mood) {
    const c = this.ctx, o = c.createOscillator(), g = c.createGain();
    o.type = mood === 'victory' || mood === 'menu' ? 'triangle' : 'square';
    o.frequency.value = f;
    g.gain.setValueAtTime(0.0001, t); g.gain.exponentialRampToValueAtTime(0.06, t + 0.02); g.gain.exponentialRampToValueAtTime(0.0001, t + 1.2);
    const fl = c.createBiquadFilter(); fl.type = 'lowpass'; fl.frequency.value = 1400;
    o.connect(fl); fl.connect(g); g.connect(this.musicGain); o.start(t); o.stop(t + 1.3);
  },
  setSlow(f) {
    this.slow = f;
    if (this.drone && this.ctx) this.drone.filt.frequency.setTargetAtTime(f < 1 ? 300 : 900, this.ctx.currentTime, 0.1);
  },
  // ---- Sprache ---------------------------------------------------------
  voice: null,
  pickVoice() {
    if (this.voice || !window.speechSynthesis) return this.voice;
    const vs = speechSynthesis.getVoices().filter((v) => v.lang && v.lang.toLowerCase().startsWith('de'));
    this.voice = vs.find((v) => /premium|enhanced/i.test(v.name)) || vs[0] || null;
    return this.voice;
  },
  speak(text, cast) {
    if (!Settings.data.voices || !window.speechSynthesis || !text) return;
    try {
      const u = new SpeechSynthesisUtterance(text.replace(/[„“”]/g, ''));
      u.lang = 'de-DE';
      const v = this.pickVoice(); if (v) u.voice = v;
      const p = castVoice(cast);
      u.pitch = p.pitch; u.rate = p.rate; u.volume = 1;
      speechSynthesis.speak(u);
    } catch (e) { }
  },
  announce(text) {
    this.play('announceBoom', 0.9);
    if (!Settings.data.voices || !window.speechSynthesis) return;
    try { const u = new SpeechSynthesisUtterance(text); u.lang = 'de-DE'; const v = this.pickVoice(); if (v) u.voice = v; u.pitch = 0.55; u.rate = 0.85; speechSynthesis.speak(u); } catch (e) { }
  },
  stopSpeech() { try { if (window.speechSynthesis) speechSynthesis.cancel(); } catch (e) { } },
};
function castVoice(cast) {
  if (!cast) return { pitch: 0.85, rate: 0.95 };
  if (cast === 'darksuit') return { pitch: 0.75, rate: 0.95 };
  if (cast === 'lena') return { pitch: 1.15, rate: 1.0 };
  if (cast === 'morgrim') return { pitch: 0.5, rate: 0.8 };
  const f = ROSTER.fighters[cast];
  if (f) return { pitch: clamp(f.pitch, 0.5, 2), rate: clamp(0.6 + f.rate * 0.8, 0.6, 1.3) };
  return { pitch: 1, rate: 1 };
}
const Haptic = (ms) => { try { if (navigator.vibrate) navigator.vibrate(ms); } catch (e) { } };
