#!/usr/bin/env node
/*
 * Safari-Prüfung (echte WebKit-Engine, iPhone-13-Emulation) – ergänzt die Chromium-Prüfung ui_pruefung.js.
 *
 *   1. Server starten:    AUTONOMOUS_DATEN=$(mktemp -d) AUTONOMOUS_PORT=8890 python3 -m autonomous start
 *   2. Prüfung:           node autonomous/tests/ui_safari_pruefung.js "http://127.0.0.1:8890/?k=SCHLÜSSEL" \
 *                              "http://127.0.0.1:8890/produkte/<ordner>/index.html" [BILDER_ORDNER]
 *
 * Voraussetzung: Playwright mit WebKit (npx playwright install --with-deps webkit).
 * Hinweis: Mit BILDER_ORDNER macht Playwright Bildschirmfotos und fügt dafür kurz einen eigenen Stil ein – WebKit
 * meldet das wegen der strengen CSP als „Refused to apply a stylesheet“. Das ist ein Messartefakt, kein Fehler von
 * AUTONOMOUS (ohne Bildschirmfotos: 0 Meldungen). Für die Fehlerprüfung deshalb ohne BILDER_ORDNER laufen lassen.
 */
const { webkit, devices } = require('playwright');
const [,, url, produktUrl, bilder] = process.argv;
(async () => {
  const browser = await webkit.launch();
  const ctx = await browser.newContext({ ...devices['iPhone 13'] });
  const seite = await ctx.newPage();
  const fehler = [];
  seite.on('console', m => { if (m.type() === 'error') fehler.push('Konsole: ' + m.text()); });
  seite.on('pageerror', e => fehler.push('Skriptfehler: ' + e.message));
  await seite.goto(url, { waitUntil: 'networkidle' });
  const bereiche = ['dashboard', 'ceo', 'agenten', 'wallet', 'finanzen', 'produkte', 'vertrieb', 'aufgaben', 'einstellungen'];
  const ergebnis = [];
  for (const b of bereiche) {
    await seite.evaluate(h => { location.hash = '#' + h; }, b);
    await seite.waitForTimeout(1200);
    const r = await seite.evaluate(() => ({
      breite: document.documentElement.scrollWidth, fenster: innerWidth,
      text: document.body.innerText.length,
      kaputt: /\[object |undefined|NaN/.test(document.body.innerText),
    }));
    ergebnis.push(`${b}: ${r.breite <= r.fenster ? 'ok' : 'WAAGERECHTE SCROLLLEISTE ' + r.breite + '>' + r.fenster}` +
                  `${r.kaputt ? ' TEXTFEHLER' : ''} (${r.text} Zeichen)`);
    if (bilder) await seite.screenshot({ path: `${bilder}/webkit-${b}.png`, fullPage: true });
  }
  // erzeugte Seite unter CSP "sandbox"
  const p = await ctx.newPage();
  const pfehler = [];
  p.on('console', m => { if (m.type() === 'error') pfehler.push(m.text()); });
  const antwort = await p.goto(produktUrl, { waitUntil: 'load' });
  const info = await p.evaluate(() => ({
    titel: document.title, h1: (document.querySelector('h1') || {}).textContent || '',
    tel: [...document.querySelectorAll('a[href^="tel:"]')].length,
    mail: [...document.querySelectorAll('a[href^="mailto:"]')].length,
    breite: document.documentElement.scrollWidth, fenster: innerWidth,
    stile: getComputedStyle(document.body).fontFamily,
  }));
  if (bilder) await p.screenshot({ path: `${bilder}/webkit-produkt.png`, fullPage: true });
  console.log('WebKit-Version:', browser.version());
  console.log(ergebnis.join('\n'));
  console.log('Fehler in der Oberfläche:', fehler.length ? fehler.join(' | ') : 'keine');
  console.log('Erzeugte Seite: HTTP', antwort.status(), '| CSP:', (antwort.headers()['content-security-policy'] || '').includes('sandbox') ? 'mit sandbox' : 'OHNE sandbox',
              '| Titel:', info.titel, '| tel-Links:', info.tel, '| mailto-Links:', info.mail,
              '| Breite ok:', info.breite <= info.fenster, '| Stile aktiv:', info.stile !== '', '| Konsolenfehler:', pfehler.length ? pfehler.join(' | ') : 'keine');
  await browser.close();
})().catch(e => { console.error('ABBRUCH:', e.message); process.exit(1); });
