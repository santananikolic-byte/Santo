// Usage: NODE_PATH=$(npm root -g) node shot.js out.png "<JS setup expression>" [waitSeconds]
// Renders index.html in headless Chromium (software GL, ~2 fps) and saves a screenshot.
// Files under assets/ are served from this folder. Globals: __silk = { Flow, Game, Input, UI, Settings, Assets }.
// Examples: "__silk.Flow.vs.arena='rainRooftop'; __silk.Flow.go('versus')"   "__silk.Flow.go('free')"
const { chromium } = require('playwright');
const path = require('path'), fs = require('fs');
const [out, setup = '', wait = '12'] = process.argv.slice(2);
(async () => {
  const browser = await chromium.launch({ proxy: { server: process.env.HTTPS_PROXY }, args: ['--use-gl=angle', '--use-angle=swiftshader', '--enable-unsafe-swiftshader', '--ignore-gpu-blocklist'] });
  const page = await (await browser.newContext({ viewport: { width: 800, height: 370 }, ignoreHTTPSErrors: true })).newPage();
  const errs = [];
  page.on('console', (m) => { if (m.type() === 'error' || /asset fehlt/.test(m.text())) errs.push('console: ' + m.text()); });
  page.on('pageerror', (e) => errs.push('PAGEERROR: ' + e.message + ' | ' + (e.stack || '').split('\n').slice(1, 3).join(' | ')));
  await page.route('https://silk.test/**', (r) => {
    const rel = decodeURIComponent(new URL(r.request().url()).pathname).replace(/^\//, '') || 'index.html';
    const f = path.join(__dirname, rel);
    if (fs.existsSync(f)) r.fulfill({ path: f }); else r.fulfill({ status: 404, body: 'missing' });
  });
  await page.goto('https://silk.test/index.html', { waitUntil: 'load', timeout: 60000 });
  await page.waitForFunction(() => { const b = document.getElementById('start-btn'); return b && !b.disabled; }, null, { timeout: 120000 });
  await page.click('#start-btn', { force: true });
  await page.waitForTimeout(500);
  if (setup) await page.evaluate(setup);
  await page.waitForTimeout(+wait * 1000);
  await page.screenshot({ path: out });
  console.log(errs.length ? errs.join('\n') : 'NO_ERRORS');
  await browser.close();
})();
