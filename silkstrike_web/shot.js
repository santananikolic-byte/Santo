// Usage: NODE_PATH=$(npm root -g) node shot.js out.png "<JS setup expression>" [waitSeconds]
// Renders index.html in headless Chromium (software GL, ~2 fps) and saves a screenshot.
// Globals for setup: __silk = { Flow, Game, Input, UI, Settings }.
// Examples: "__silk.Flow.vs.arena='rainRooftop'; __silk.Flow.go('versus')"   "__silk.Flow.chapter(0)"
const { chromium } = require('playwright');
const [out, setup = '', wait = '12'] = process.argv.slice(2);
(async () => {
  const browser = await chromium.launch({ proxy: { server: process.env.HTTPS_PROXY }, args: ['--use-gl=angle', '--use-angle=swiftshader', '--enable-unsafe-swiftshader', '--ignore-gpu-blocklist'] });
  const page = await (await browser.newContext({ viewport: { width: 800, height: 370 }, ignoreHTTPSErrors: true })).newPage();
  const errs = [];
  page.on('console', (m) => { if (m.type() === 'error') errs.push('console: ' + m.text()); });
  page.on('pageerror', (e) => errs.push('PAGEERROR: ' + e.message + ' | ' + (e.stack || '').split('\n').slice(1, 3).join(' | ')));
  await page.route('https://silk.test/**', (r) => r.fulfill({ path: __dirname + '/index.html', contentType: 'text/html' }));
  await page.goto('https://silk.test/index.html', { waitUntil: 'load', timeout: 60000 });
  await page.waitForTimeout(2500);
  await page.click('#start-btn', { force: true });
  await page.waitForTimeout(500);
  if (setup) await page.evaluate(setup);
  await page.waitForTimeout(+wait * 1000);
  await page.screenshot({ path: out });
  console.log(errs.length ? errs.join('\n') : 'NO_ERRORS');
  await browser.close();
})();
