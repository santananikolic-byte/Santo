// =====================================================================
//  Start
// =====================================================================
UI.init();
applyQuality();
const startBtn = $('start-btn'), startLabel = startBtn.textContent;
startBtn.disabled = true; startBtn.textContent = 'LADE GRAFIK … 0%';
Assets.preload((k) => { startBtn.textContent = 'LADE GRAFIK … ' + Math.round(k * 100) + '%'; })
  .then(() => new Promise((r) => SkinLib.load(r)))
  .then(() => { startBtn.disabled = false; startBtn.textContent = startLabel; Game.setController(new TitleController()); requestAnimationFrame(frame); });
const rot = $('rotate');
const checkRotate = () => rot.classList.toggle('need', innerHeight > innerWidth);
window.addEventListener('resize', checkRotate); checkRotate();
$('start-btn').addEventListener('click', () => {
  Audio.start();
  try { if (window.speechSynthesis) { const u = new SpeechSynthesisUtterance(' '); u.volume = 0; speechSynthesis.speak(u); } } catch (e) { }
  try { const de = document.documentElement; if (de.requestFullscreen) de.requestFullscreen().catch(() => { }); } catch (e) { }
  try { if (navigator.wakeLock) navigator.wakeLock.request('screen').catch(() => { }); } catch (e) { }
  $('start').hidden = true;
  Audio.setMusic('menu');
  UI.show('title');
  Flow.refreshTitle();
});
document.addEventListener('visibilitychange', () => {
  if (document.hidden) { UI.pause(true); if (Audio.ctx) Audio.ctx.suspend(); }
  else if (Audio.ctx) Audio.ctx.resume();
});
window.__silk = { Flow, Game, Input, UI, Settings, Assets };
