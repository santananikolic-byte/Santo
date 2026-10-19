// =====================================================================
//  Oberfläche: Menüs, HUDs, Touch-Steuerung, Spielablauf
// =====================================================================
const $ = (id) => document.getElementById(id);
const el = (tag, cls, html) => { const e = document.createElement(tag); if (cls) e.className = cls; if (html !== undefined) e.innerHTML = html; return e; };
const esc = (s) => String(s).replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));

const UI = {
  bannerT: 0, comboT: 0, toastT: 0, flashA: 0,
  init() {
    // Touch-Knöpfe
    document.querySelectorAll('[data-btn]').forEach((b) => {
      const name = b.dataset.btn;
      const down = (e) => { e.preventDefault(); b.setPointerCapture && b.setPointerCapture(e.pointerId); b.classList.add('on'); Input.press(name); Haptic(6); };
      const up = (e) => { e.preventDefault(); b.classList.remove('on'); Input.release(name); };
      b.addEventListener('pointerdown', down); b.addEventListener('pointerup', up); b.addEventListener('pointercancel', up); b.addEventListener('lostpointercapture', up);
    });
    // Joysticks
    document.querySelectorAll('.stick-zone').forEach((zone) => {
      const base = zone.querySelector('.stick-base'), knob = zone.querySelector('.stick-knob');
      let id = null, ox = 0, oy = 0; const R = 56;
      zone.addEventListener('pointerdown', (e) => { if (id !== null) return; e.preventDefault(); id = e.pointerId; zone.setPointerCapture(e.pointerId); const r = zone.getBoundingClientRect(); ox = e.clientX - r.left; oy = e.clientY - r.top; base.style.left = ox + 'px'; base.style.top = oy + 'px'; base.classList.add('on'); knob.style.transform = 'translate(-50%,-50%)'; });
      zone.addEventListener('pointermove', (e) => {
        if (e.pointerId !== id) return; e.preventDefault();
        const r = zone.getBoundingClientRect(); let dx = e.clientX - r.left - ox, dy = e.clientY - r.top - oy; const l = Math.hypot(dx, dy);
        if (l > R) { dx = dx / l * R; dy = dy / l * R; }
        knob.style.transform = `translate(calc(-50% + ${dx}px), calc(-50% + ${dy}px))`;
        let mx = dx / R, my = -dy / R; if (Math.abs(mx) < 0.12) mx = 0; if (Math.abs(my) < 0.12) my = 0;
        Input.move.x = mx; Input.move.y = my;
      });
      const end = (e) => { if (e.pointerId !== id) return; id = null; base.classList.remove('on'); Input.move.x = 0; Input.move.y = 0; };
      zone.addEventListener('pointerup', end); zone.addEventListener('pointercancel', end);
    });
    $('btn-pause-w').onclick = () => this.pause(true);
    $('btn-pause-k').onclick = () => this.pause(true);
    $('cs-skip').onclick = () => { if (Game.active && Game.active.skip) Game.active.skip(); };
    $('btn-interact').onclick = () => { Input.press('interact'); Input.release('interact'); };
    document.querySelectorAll('[data-go]').forEach((b) => b.addEventListener('click', () => { Audio.play('uiConfirm'); Flow.go(b.dataset.go); }));
    this.buildSettings();
  },
  show(id) { document.querySelectorAll('.screen').forEach((s) => { s.hidden = s.id !== id; }); },
  fps(v) { const f = $('fps'); f.hidden = !Settings.data.fps; f.textContent = v + ' FPS'; },
  tick(dt) {
    if (this.bannerT > 0) { this.bannerT -= dt; if (this.bannerT <= 0) $('banner').classList.remove('show'); }
    if (this.comboT > 0) { this.comboT -= dt; if (this.comboT <= 0) $('combo').classList.remove('show'); }
    if (this.toastT > 0) { this.toastT -= dt; if (this.toastT <= 0) $('toast').classList.remove('show'); }
    if (this.flashA > 0) { this.flashA = Math.max(0, this.flashA - dt * 3); $('flash').style.opacity = this.flashA; }
  },
  clearOverlays() { this.bannerT = this.comboT = this.toastT = 0; $('banner').classList.remove('show'); $('combo').classList.remove('show'); $('toast').classList.remove('show'); },
  flash(color) { const f = $('flash'); f.style.background = color; this.flashA = 0.75; f.style.opacity = 0.75; },
  fade(a) { $('fade').style.opacity = a; },
  banner(text, style, secs) { const b = $('banner'); b.textContent = text; b.className = 'banner ' + style; void b.offsetWidth; b.classList.add('show'); this.bannerT = secs; },
  combo(text) { const c = $('combo'); c.textContent = text; c.classList.remove('show'); void c.offsetWidth; c.classList.add('show'); this.comboT = 1.4; },
  toast(text) { const t = $('toast'); t.textContent = text; t.classList.add('show'); this.toastT = 3; },
  loading(info) {
    const L = $('loading');
    if (!info) { L.classList.remove('show'); return; }
    L.querySelector('.ld-title').innerHTML = info.vs ? `<span>${esc(info.vs[0])}</span><b>VS</b><span>${esc(info.vs[1])}</span>` : esc(info.title || '');
    L.querySelector('.ld-sub').textContent = info.sub || '';
    L.querySelector('.ld-tip').textContent = info.tip || '';
    L.classList.add('show');
  },
  pause(on) {
    if (on && !(Game.active instanceof WorldController || Game.active instanceof KombatController)) return;
    Game.paused = on; $('pause').hidden = !on; Input.reset();
    if (on) Audio.stopSpeech();
    $('pause-restart').hidden = !(Game.active instanceof KombatController);
  },
  // ---- Welt-HUD
  worldHud(on) { $('hud-world').hidden = !on; },
  setObjective(t) { $('w-obj').textContent = t; },
  worldUpdate(i) {
    $('w-health').style.width = (i.health * 100).toFixed(1) + '%';
    $('w-speed').textContent = i.speed;
    $('w-speed').classList.toggle('fast', i.speed > 90);
    $('w-seals').textContent = i.seals + '/' + i.sealsTotal;
    const c = $('w-combo'); c.hidden = i.combo < 2; c.textContent = i.combo + '× KOMBO';
    $('btn-web').classList.toggle('active', i.swinging);
    const hasObj = i.dist !== undefined;
    $('w-dist').textContent = hasObj ? i.dist + ' m' : '';
    $('w-arrow').style.display = hasObj ? '' : 'none';
    if (hasObj) $('w-arrow').style.transform = `rotate(${i.arrow}rad)`;
    $('btn-interact').hidden = !i.prompt;
    const mm = $('w-map'), g = mm.getContext('2d'), W = mm.width;
    g.clearRect(0, 0, W, W);
    g.fillStyle = 'rgba(8,6,10,0.65)'; g.beginPath(); g.arc(W / 2, W / 2, W / 2 - 1, 0, TAU); g.fill();
    g.strokeStyle = 'rgba(179,8,27,0.6)'; g.lineWidth = 1;
    for (let k = 1; k < 9; k++) { g.beginPath(); g.moveTo(k * W / 9, 0); g.lineTo(k * W / 9, W); g.moveTo(0, k * W / 9); g.lineTo(W, k * W / 9); g.stroke(); }
    if (i.obj) { g.fillStyle = '#ff3b2f'; g.beginPath(); g.arc(i.obj[0] * W, i.obj[1] * W, 5, 0, TAU); g.fill(); }
    g.save(); g.translate(i.hero[0] * W, i.hero[1] * W); g.rotate(-i.heading + Math.PI); g.fillStyle = '#ffcc5c'; g.beginPath(); g.moveTo(0, -7); g.lineTo(5, 5); g.lineTo(-5, 5); g.closePath(); g.fill(); g.restore();
  },
  // ---- Kombat-HUD
  kombatHud(on, p1, p2) {
    $('hud-kombat').hidden = !on;
    if (!on) return;
    $('k-n1').textContent = p1.name.toUpperCase(); $('k-n2').textContent = p2.name.toUpperCase();
    $('btn-s1').querySelector('span').textContent = p1.specials[0].name; $('btn-s2').querySelector('span').textContent = p1.specials[1].name;
    this.kombatControls(false); this.executePrompt(false);
  },
  kombatCinematic(on) { $('hud-kombat').classList.toggle('cine', on); },
  kombatControls(on) { $('k-controls').hidden = !on; if (!on) Input.reset(); },
  executePrompt(on) { $('btn-exec').hidden = !on; },
  executeTime(k) { $('exec-ring').style.setProperty('--k', k); },
  kombatUpdate(s) {
    $('k-h1').style.width = (s.h1 * 100) + '%'; $('k-h2').style.width = (s.h2 * 100) + '%';
    $('k-l1').style.width = (s.l1 * 100) + '%'; $('k-l2').style.width = (s.l2 * 100) + '%';
    $('k-m1').style.width = (Math.min(1, s.m1) * 100) + '%'; $('k-m2').style.width = (Math.min(1, s.m2) * 100) + '%';
    $('k-m1').classList.toggle('full', s.m1 >= 1);
    $('k-timer').textContent = s.timer; $('k-timer').classList.toggle('low', s.timer <= 10);
    const dots = (n) => Array.from({ length: s.toWin }, (_, k) => `<i class="${k < n ? 'won' : ''}"></i>`).join('');
    const d1 = dots(s.r1), d2 = dots(s.r2);
    if ($('k-r1').innerHTML !== d1) $('k-r1').innerHTML = d1;
    if ($('k-r2').innerHTML !== d2) $('k-r2').innerHTML = d2;
    $('btn-s1').classList.toggle('dim', !s.s1); $('btn-s2').classList.toggle('dim', !s.s2);
    $('btn-brutal').hidden = !s.brutal;
  },
  // ---- Zwischensequenz
  cutscene(on, title) { $('hud-cut').hidden = !on; this.subtitle(null); this.cutTitle(on ? title : null); if (on) this.fade(1); else this.fade(0); },
  cutTitle(t) { const e = $('cs-title'); e.textContent = t || ''; e.classList.toggle('show', !!t); },
  subtitle(speaker, text) {
    const s = $('cs-sub');
    if (!text) { s.classList.remove('show'); return; }
    s.querySelector('b').textContent = speaker ? speaker.toUpperCase() : '';
    s.querySelector('p').textContent = text;
    s.classList.remove('show'); void s.offsetWidth; s.classList.add('show');
  },
  // ---- Menüs
  buildChapters() {
    const list = $('chapter-list'); list.innerHTML = '';
    STORY.chapters.forEach((ch, i) => {
      const unlocked = i <= Progress.chapter || Progress.done;
      const opp = ROSTER.fighters[ch.opponent];
      const card = el('button', 'chapter' + (unlocked ? '' : ' locked'));
      card.style.setProperty('--sig', opp.look.glow);
      card.innerHTML = `<small>${ch.number === 0 ? 'PROLOG' : 'KAPITEL ' + ch.number}</small><h3>${esc(ch.title)}</h3><p>${esc(ch.subtitle)}</p><em>Gegner: ${esc(opp.name)} · ${esc(ARENAS[ch.arena].name)}</em>${unlocked ? '' : '<div class="lock">GESPERRT</div>'}`;
      card.onclick = () => { if (!unlocked) { Audio.play('ui'); return; } Audio.play('uiConfirm'); Flow.chapter(i); };
      list.appendChild(card);
    });
  },
  buildFighters() {
    const ids = Object.keys(ROSTER.fighters);
    const mk = (target, key) => {
      const box = $(target); box.innerHTML = '';
      ids.forEach((id) => {
        const f = ROSTER.fighters[id];
        const b = el('button', 'fighter' + (Flow.vs[key] === id ? ' sel' : ''));
        b.style.setProperty('--sig', f.look.primary);
        b.innerHTML = `<i></i><span><b>${esc(f.name)}</b><small>${esc(f.title)}</small></span>`;
        b.onclick = () => { Audio.play('ui'); Flow.vs[key] = id; this.buildFighters(); };
        box.appendChild(b);
      });
    };
    mk('fs-p1', 'p1'); mk('fs-p2', 'p2');
    const p = ROSTER.fighters[Flow.vs.p1], c = ROSTER.fighters[Flow.vs.p2];
    $('fs-vs').innerHTML = `<h3>${esc(p.name)}</h3><b>VS</b><h3>${esc(c.name)}</h3><p>${esc(c.bio)}</p><em>Deine Exekution: ${esc(p.exec.name)}</em>`;
    const ar = $('fs-arena'); if (!ar.options.length) Object.keys(ARENAS).forEach((k) => ar.add(new Option(ARENAS[k].name, k)));
    ar.value = Flow.vs.arena; ar.onchange = () => { Flow.vs.arena = ar.value; };
    const df = $('fs-diff'); df.value = Flow.vs.diff; df.onchange = () => { Flow.vs.diff = df.value; };
  },
  buildSettings() {
    const d = Settings.data;
    const bind = (id, key, num) => { const e = $(id); if (e.type === 'checkbox') e.checked = d[key]; else e.value = d[key]; e.onchange = () => { d[key] = e.type === 'checkbox' ? e.checked : (num ? parseFloat(e.value) : e.value); Settings.save(); Audio.apply(); if (key === 'quality') applyQuality(); }; };
    bind('st-quality', 'quality'); bind('st-diff', 'difficulty'); bind('st-blood', 'blood'); bind('st-voices', 'voices'); bind('st-music', 'music');
    bind('st-sfx', 'sfx', true); bind('st-mvol', 'musicVol', true); bind('st-sens', 'sens', true); bind('st-fps', 'fps');
  },
  results(r, mode) {
    $('rs-title').textContent = r.won ? 'SIEG' : 'NIEDERLAGE';
    $('rs-title').className = r.won ? 'won' : 'lost';
    $('rs-stats').innerHTML = [['RUNDEN', r.rw + ' : ' + r.rl], ['MAX. KOMBO', r.combo], ['SCHADEN', r.dmg], ['ZEIT', r.secs + ' s'], ['EXEKUTION', r.exec ? 'JA' : (r.executed ? 'ERLITTEN' : 'NEIN')]]
      .map(([k, v]) => `<div><small>${k}</small><b>${v}</b></div>`).join('');
    const btns = $('rs-buttons'); btns.innerHTML = '';
    const add = (label, fn, main) => { const b = el('button', 'menu-btn' + (main ? ' main' : ''), label); b.onclick = () => { Audio.play('uiConfirm'); fn(); }; btns.appendChild(b); };
    if (mode === 'story') {
      if (r.won) add(Flow.ci >= STORY.chapters.length - 1 ? 'EPILOG' : 'WEITER', () => Flow.next(), true);
      else { add('NOCHMAL', () => Flow.retry(), true); add('ZURÜCK IN DIE STADT', () => Flow.world()); }
    } else { add('REVANCHE', () => Flow.retry(), true); add('NEUE AUSWAHL', () => Flow.go('fighters')); }
    add('HAUPTMENÜ', () => Flow.go('title'));
    $('rs-unlock').textContent = Flow.unlocked !== null && STORY.chapters[Flow.unlocked] ? 'Freigeschaltet: ' + (Flow.unlocked === 0 ? 'Prolog' : 'Kapitel ' + Flow.unlocked) + ' · ' + STORY.chapters[Flow.unlocked].title : '';
  },
};
window.UI = UI;

// ---------------------------------------------------------------- Spielablauf
const TIPS = ['Halte NETZ gedrückt, um zu schwingen – lass im tiefsten Punkt los, um am weitesten zu fliegen.', 'ZIP zieht dich blitzschnell dorthin, wohin die Kamera zeigt.',
  'Blocken fängt fast den ganzen Schaden ab – Würfe brechen aber jede Deckung.', 'Ist deine Brutal-Leiste voll, erscheint der BRUTAL-Knopf.', 'Bei „VOLLENDE ES!“ bleiben dir 6 Sekunden für die Exekution.',
  'Auf den Dächern von Neo-Haven liegen 40 Blutsiegel versteckt.', 'Ducken + Schlag ist ein Uppercut, Ducken + Tritt ein Feger.', 'Schlag, Schlag, Tritt ist die Dreierkette.'];
const Flow = {
  mode: 'story', ci: 0, lastSetup: null, unlocked: null,
  vs: { p1: 'silkstrike', p2: 'vex', arena: 'templeGarden', diff: 'normal' },
  tip() { return TIPS[Math.floor(Math.random() * TIPS.length)]; },
  transition(info, build, delay = 350) {
    UI.loading(info || {});
    Game.paused = false; $('pause').hidden = true;
    setTimeout(() => {
      Game.teardown();
      try { Game.setController(build()); }
      catch (e) { console.error(e); Game.setController(new TitleController()); UI.show('title'); }
      setTimeout(() => UI.loading(null), 250);
    }, delay);
  },
  go(screen) {
    if (screen !== 'settings' && screen !== 'settingsBack' && screen !== 'resume') Audio.stopSpeech();
    if (screen === 'title' || screen === 'chapters' || screen === 'fighters' || screen === 'credits') { Game.paused = false; $('pause').hidden = true; }
    const toMenu = () => { if (!(Game.active instanceof TitleController)) this.transition({}, () => new TitleController()); Audio.setMusic('menu'); };
    if (screen === 'title') { toMenu(); UI.show('title'); this.refreshTitle(); }
    else if (screen === 'chapters') { toMenu(); UI.buildChapters(); UI.show('chapters'); }
    else if (screen === 'fighters') { toMenu(); this.mode = 'versus'; UI.buildFighters(); UI.show('fighters'); }
    else if (screen === 'settings') { this.settingsFromPause = Game.paused; $('pause').hidden = true; UI.buildSettings(); UI.show('settings'); }
    else if (screen === 'settingsBack') { if (this.settingsFromPause) { UI.show('none'); $('pause').hidden = false; } else { UI.show('title'); this.refreshTitle(); } this.settingsFromPause = false; }
    else if (screen === 'credits') { toMenu(); $('credits-roll').innerHTML = STORY.credits.map((l, i) => `<p class="${i === 0 ? 'big' : ''}">${esc(l) || '&nbsp;'}</p>`).join(''); UI.show('credits'); }
    else if (screen === 'free') this.free();
    else if (screen === 'continue') this.chapter(Math.min(Progress.chapter, STORY.chapters.length - 1));
    else if (screen === 'versus') this.versus();
    else if (screen === 'resume') UI.pause(false);
    else if (screen === 'restart') { UI.pause(false); this.retry(); }
  },
  refreshTitle() {
    const c = $('btn-continue');
    const ch = STORY.chapters[Math.min(Progress.chapter, STORY.chapters.length - 1)];
    c.hidden = !(Progress.chapter > 0 && !Progress.done);
    if (ch) c.querySelector('small').textContent = (ch.number === 0 ? 'Prolog' : 'Kapitel ' + ch.number) + ' · ' + ch.title;
  },
  chapter(i) {
    this.mode = 'story'; this.ci = i; this.unlocked = null;
    const ch = STORY.chapters[i];
    UI.show('none');
    this.cutscene(ch.intro, { title: ch.number === 0 ? 'PROLOG' : 'KAPITEL ' + ch.number, sub: ch.title, tip: ch.subtitle }, () => this.world());
  },
  cutscene(id, info, then) {
    UI.show('none');
    this.transition(info, () => new CutsceneController(id, () => then()));
  },
  worldDark(i) { return i > 0 && STORY.chapters[i - 1].dark; },
  world() {
    const ch = STORY.chapters[this.ci];
    UI.show('none');
    this.transition({ title: 'NEO-HAVEN', sub: ch.objectiveText, tip: this.tip() }, () => new WorldController({ chapter: ch, dark: this.worldDark(this.ci), onObjective: () => setTimeout(() => this.prefight(), 50) }));
  },
  free() {
    this.mode = 'free'; UI.show('none');
    this.transition({ title: 'FREIES SCHWINGEN', sub: 'Neo-Haven gehört dir', tip: this.tip() }, () => new WorldController({ chapter: null, dark: false }));
  },
  prefight() {
    const ch = STORY.chapters[this.ci];
    if (ch.pre && STORY.cutscenes[ch.pre]) this.cutscene(ch.pre, {}, () => this.storyFight()); else this.storyFight();
  },
  storyFight() {
    const ch = STORY.chapters[this.ci];
    this.fight({ player: 'silkstrike', cpu: ch.opponent, arena: ch.arena, dark: ch.dark, ai: Math.min(1.2, ch.ai * DIFF[Settings.data.difficulty]), story: true, toWin: 2, seconds: 90 });
  },
  versus() {
    this.mode = 'versus';
    this.fight({ player: this.vs.p1, cpu: this.vs.p2, arena: this.vs.arena, dark: false, ai: Math.min(1.2, 0.85 * DIFF[this.vs.diff]), story: false, toWin: 2, seconds: 90 });
  },
  fight(setup) {
    this.lastSetup = setup; UI.show('none');
    const a = ROSTER.fighters[setup.player], b = ROSTER.fighters[setup.cpu];
    setup.onEnd = (r) => setTimeout(() => this.matchEnd(r), 30);
    this.transition({ vs: [a.name.toUpperCase(), b.name.toUpperCase()], sub: ARENAS[setup.arena].name, tip: this.tip() }, () => new KombatController(setup), 1000);
  },
  retry() { if (this.lastSetup) this.fight(Object.assign({}, this.lastSetup)); else this.go('title'); },
  matchEnd(r) {
    this.lastResult = r;
    if (this.mode === 'story' && r.won) {
      if (this.ci + 1 < STORY.chapters.length) { if (Progress.chapter < this.ci + 1) { Progress.chapter = this.ci + 1; this.unlocked = this.ci + 1; } }
      else Progress.done = true;
      Progress.save();
      const ch = STORY.chapters[this.ci];
      this.cutscene(ch.outro, {}, () => { this.transition({}, () => new TitleController()); Audio.setMusic('victory'); UI.results(r, 'story'); UI.show('results'); });
    } else {
      Audio.setMusic(r.won ? 'victory' : 'sad');
      UI.results(r, this.mode === 'story' ? 'story' : 'versus'); UI.show('results');
    }
  },
  next() {
    if (this.ci + 1 < STORY.chapters.length) this.chapter(this.ci + 1);
    else this.cutscene('epilogue', { title: 'EPILOG', sub: 'Sonnenaufgang über Neo-Haven' }, () => { this.go('credits'); Audio.setMusic('victory'); });
  },
};
