#!/usr/bin/env node
/*
 * iPhone-im-WLAN-Prüfung mit der echten WebKit-Engine (Safari) – Teil von iphone_pruefung.py, das den Testserver
 * startet, den QR-Code mit einem unabhängigen Leser (ZXing) dekodiert und die Teile nacheinander aufruft:
 *
 *   node iphone_pruefung.js mac    "http://127.0.0.1:PORT/?k=…" BILD.png   → am „Mac“ (WebKit, Desktop) einschalten,
 *                                                                          QR-Code fotografieren, Link ausgeben
 *   node iphone_pruefung.js iphone "http://192.168.…:PORT/?k=…"            → „iPhone 13“ (WebKit) öffnet den Link
 *                                                                          über die WLAN-Adresse, speichert eine
 *                                                                          Einstellung, fremde Herkunft → 403
 *   node iphone_pruefung.js aus    "http://127.0.0.1:PORT/?k=…"            → am „Mac“ wieder ausschalten
 *   node iphone_pruefung.js weg    "http://192.168.…:PORT/?k=…"            → „iPhone“ kommt nicht mehr hinein
 *
 * Jeder Teil gibt eine Zeile JSON aus: {"ok": true|false, "pruefungen": […], …}.
 */
'use strict';

const { webkit, devices } = require('playwright');

const [, , teil, url, bild] = process.argv;
const pruefungen = [];
function pruefe(bedingung, text) {
  pruefungen.push({ ok: !!bedingung, text });
  return !!bedingung;
}

async function kontextMitBeobachtung(browser, optionen) {
  const ctx = await browser.newContext(Object.assign({ locale: 'de-DE' }, optionen));
  await ctx.addInitScript(() => {
    window.__csp = [];
    document.addEventListener('securitypolicyviolation', e => window.__csp.push(e.violatedDirective + ' ' + (e.blockedURI || '')));
  });
  return ctx;
}

function beobachten(seite) {
  const fehler = [];
  seite.on('console', m => { if (m.type() === 'error') fehler.push(m.text()); });
  seite.on('pageerror', e => fehler.push('Skriptfehler: ' + e.message));
  return fehler;
}

async function bereich(seite, id) {
  await seite.evaluate(z => { location.hash = z; }, id);
  await seite.waitForFunction(z => {
    const m = document.querySelector('main');
    return m && m.dataset.bereich === z && ['fertig', 'fehler', 'anmeldung'].includes(m.dataset.status);
  }, id, { timeout: 15000 });
  return seite.getAttribute('main', 'data-status');
}

async function iphoneStatus(seite) {
  return seite.evaluate(async () => (await fetch('/api/iphone', { credentials: 'same-origin' })).json());
}

async function schalten(seite, an) {
  const karte = '[data-pruef="iphone"]';
  if (an) await seite.check(karte + ' [data-pruef="iphone-schalter"]');
  else await seite.uncheck(karte + ' [data-pruef="iphone-schalter"]');
  await seite.click('[data-pruef="iphone-speichern"]');
  const ende = Date.now() + 15000;
  while (Date.now() < ende) {
    const s = await iphoneStatus(seite);
    if (s.erlaubt === an && s.aktiv === an) return s;
    await seite.waitForTimeout(300);
  }
  return null;
}

async function mac(browser) {
  const ctx = await kontextMitBeobachtung(browser, { viewport: { width: 1280, height: 800 }, deviceScaleFactor: 2 });
  const seite = await ctx.newPage();
  const fehler = beobachten(seite);
  await seite.goto(url, { waitUntil: 'networkidle' });
  pruefe(await bereich(seite, 'einstellungen') === 'fertig', 'Mac: Einstellungen laden');
  const s = await schalten(seite, true);
  if (!pruefe(!!s, 'Mac: Schalter „Zugriff aus dem eigenen WLAN erlauben“ einschalten und speichern')) return { ok: false };
  await seite.waitForSelector('[data-pruef="iphone-qr"] svg path', { timeout: 10000 });
  const link = ((await seite.textContent('[data-pruef="iphone-link"]')) || '').trim();
  pruefe(link === s.link, 'Mac: Link als Text = Link des Servers');
  pruefe((await seite.evaluate(() => window.__csp)).length === 0, 'Mac: keine CSP-Verstöße');
  pruefe(fehler.length === 0, 'Mac: keine Konsolenfehler' + (fehler.length ? ' (' + fehler.join(' | ') + ')' : ''));
  // Foto nur vom QR-Code (mit weißem Rand); ohne eingefügten Playwright-Stil (Cursor/Animationen bleiben unverändert)
  await seite.locator('[data-pruef="iphone-qr"] .qr-rahmen').screenshot({ path: bild, caret: 'initial', animations: 'allow' });
  await ctx.close();
  return { link, adressen: s.adressen };
}

async function iphone(browser) {
  const ctx = await kontextMitBeobachtung(browser, { ...devices['iPhone 13'] });
  const seite = await ctx.newPage();
  const fehler = beobachten(seite);
  const antwort = await seite.goto(url, { waitUntil: 'networkidle' });
  const ziel = new URL(url);
  pruefe(!!antwort && antwort.ok(), 'iPhone: Link aus dem QR-Code öffnet die Oberfläche (HTTP ' + (antwort && antwort.status()) + ')');
  pruefe(new URL(seite.url()).host === ziel.host && !/[?&]k=/.test(seite.url()), 'iPhone: über die WLAN-Adresse, Schlüssel nicht mehr in der Adresszeile');
  const cookie = (await ctx.cookies()).find(c => c.name === 'autonomous_zugang');
  pruefe(!!cookie && cookie.httpOnly && cookie.sameSite === 'Strict', 'iPhone: Zugang als HttpOnly-/SameSite=Strict-Cookie gemerkt');
  pruefe(await bereich(seite, 'dashboard') === 'fertig', 'iPhone: Dashboard lädt');
  pruefe(await bereich(seite, 'einstellungen') === 'fertig', 'iPhone: Einstellungen laden');
  const breite = await seite.evaluate(() => [document.documentElement.scrollWidth, innerWidth]);
  pruefe(breite[0] <= breite[1], 'iPhone: keine waagerechte Scrollleiste (' + breite.join(' ≤ ') + ')');

  // Eine Einstellung über die echte Oberfläche speichern – POST mit der echten Herkunft (WLAN-Adresse)
  const sf = '[data-pruef="stundensatz-formular"]';
  await seite.fill(sf + ' input[name="stundensatz"]', '41,00');
  await seite.click('[data-pruef="stundensatz-formular-speichern"]');
  let satz = null;
  for (let i = 0; i < 40 && satz !== 4100; i++) {
    await seite.waitForTimeout(250);
    satz = (await seite.evaluate(async () => (await (await fetch('/api/einstellungen', { credentials: 'same-origin' })).json()).werte.stundensatz_cent));
  }
  pruefe(satz === 4100, 'iPhone: Einstellung (Stundensatz 41,00 €) über die Oberfläche gespeichert');

  // Fremde Herkunft mit demselben gültigen Zugangs-Cookie: muss abgelehnt werden
  const fremd = await ctx.request.post(ziel.origin + '/api/einstellungen', {
    headers: { Origin: 'http://angreifer.example', 'Content-Type': 'application/json' },
    data: { schluessel: 'stundensatz_cent', wert: 1 },
  });
  pruefe(fremd.status() === 403, 'iPhone: fremde Herkunft (Origin) → 403 (war ' + fremd.status() + ')');
  const echt = await ctx.request.post(ziel.origin + '/api/einstellungen', {
    headers: { Origin: ziel.origin, 'Content-Type': 'application/json' },
    data: { schluessel: 'stundensatz_cent', wert: 4200 },
  });
  pruefe(echt.status() === 200, 'iPhone: gleiche Anfrage mit echter Herkunft → 200 (war ' + echt.status() + ')');
  const nachher = await seite.evaluate(async () => (await (await fetch('/api/einstellungen', { credentials: 'same-origin' })).json()).werte.stundensatz_cent);
  pruefe(nachher === 4200, 'iPhone: abgelehnte Anfrage hat nichts verändert (' + nachher + ' Cent)');
  pruefe((await seite.evaluate(() => window.__csp)).length === 0, 'iPhone: keine CSP-Verstöße');
  pruefe(fehler.length === 0, 'iPhone: keine Konsolenfehler' + (fehler.length ? ' (' + fehler.join(' | ') + ')' : ''));
  await ctx.close();
  return { webkit: browser.version() };
}

async function aus(browser) {
  const ctx = await kontextMitBeobachtung(browser, { viewport: { width: 1280, height: 800 } });
  const seite = await ctx.newPage();
  await seite.goto(url, { waitUntil: 'networkidle' });
  pruefe(await bereich(seite, 'einstellungen') === 'fertig', 'Mac: Einstellungen laden');
  pruefe(!!(await schalten(seite, false)), 'Mac: WLAN-Zugriff ausschalten und speichern');
  const qrWeg = await seite.waitForSelector('[data-pruef="iphone-qr"]', { state: 'detached', timeout: 10000 }).then(() => true, () => false);
  pruefe(qrWeg, 'Mac: QR-Code verschwindet nach dem Ausschalten');
  await ctx.close();
  return {};
}

async function weg(browser) {
  const ctx = await browser.newContext({ ...devices['iPhone 13'] });
  const seite = await ctx.newPage();
  let erreichbar = true;
  let meldung = '';
  try {
    await seite.goto(url, { timeout: 10000 });
  } catch (e) {
    erreichbar = false;
    meldung = String(e.message || e).split('\n')[0];
  }
  pruefe(!erreichbar, 'iPhone: nach dem Ausschalten nicht mehr erreichbar' + (meldung ? ' (' + meldung + ')' : ''));
  await ctx.close();
  return {};
}

(async () => {
  const teile = { mac, iphone, aus, weg };
  if (!teile[teil] || !url || (teil === 'mac' && !bild)) {
    console.error('Aufruf: node iphone_pruefung.js mac|iphone|aus|weg URL [BILD.png]');
    process.exit(2);
  }
  const browser = await webkit.launch();
  let zusatz = {};
  try {
    zusatz = await teile[teil](browser);
  } finally {
    await browser.close();
  }
  const ok = pruefungen.length > 0 && pruefungen.every(p => p.ok) && zusatz.ok !== false;
  console.log(JSON.stringify(Object.assign({}, zusatz, { ok, pruefungen })));
  process.exit(ok ? 0 : 1);
})().catch(e => {
  console.log(JSON.stringify({ ok: false, abbruch: String(e && e.message ? e.message : e), pruefungen }));
  process.exit(1);
});
