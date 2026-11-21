#!/usr/bin/env node
/*
 * UI-Prüfung für AUTONOMOUS (Browser-Test mit Playwright/Chromium).
 *
 *   node autonomous/tests/ui_pruefung.js "http://127.0.0.1:PORT/?k=SCHLUESSEL"
 *
 * Bequemer (startet einen Testserver mit leerem Datenordner und stoppt ihn wieder):
 *
 *   python3 autonomous/tests/ui_server.py
 *
 * ACHTUNG: Nur gegen einen TESTSERVER laufen lassen – die Prüfung legt Daten an
 * (Ziel, simulierte Buchung, Aufgaben, Kontakt, Angebote, Freigaben).
 *
 * Ablauf:
 * 1. Funktionen bis ins Backend (Desktop): Ziel anlegen, simulierte Wallet-Buchung, ungültiger Betrag,
 *    Aufgabe an eine Rolle geben (mit freundlichen Feldern) und Ergebnis in den Details ansehen,
 *    Freigabe-Ablauf über die Vertriebsrouten (Karte zeigt Aktion, Ziel, Kosten, Datenumfang, Folgen,
 *    Agent; „Nein“ braucht zweimal Tippen und sperrt endgültig), Google-Profil-Formular.
 * 2. Ansicht bei 390×844 (iPhone) und 1280×800 (Desktop) – jetzt mit echten Daten:
 *    alle 9 Bereiche laden, keine Konsolenfehler, keine CSP-Verstöße, keine waagerechte Scrollleiste,
 *    kein „[object …]“, „undefined“ oder „NaN“ im Text, Tippflächen auf dem Handy ≥ 44 px,
 *    Dashboard zeigt den echten Status „läuft“, Wallet = SIMULATION, Finanzen = REAL.
 * 3. „Mehr“-Navigation auf dem Handy und Hinweis ohne Zugangsschlüssel.
 *
 * Optional: UI_BILDER=/pfad/zum/ordner speichert Bildschirmfotos je Bereich und Größe.
 */
'use strict';

const { chromium } = require('playwright');

const BEREICHE = ['dashboard', 'ceo', 'agenten', 'wallet', 'finanzen', 'produkte', 'vertrieb', 'aufgaben', 'einstellungen'];
const GROESSEN = [
  { name: 'iphone', viewport: { width: 390, height: 844 }, isMobile: true, hasTouch: true },
  { name: 'desktop', viewport: { width: 1280, height: 800 }, isMobile: false, hasTouch: false },
];
// Routen, die (noch) fehlen dürfen: Die Oberfläche zeigt dann „noch nicht verfügbar“. Der Browser meldet
// die 404/405 trotzdem in der Konsole – das zählt als Hinweis, nicht als Fehler.
const OPTIONALE_ROUTEN = /\/api\/(produkte|kontakte|angebote|vertrieb|rueckmeldungen)(\/|\?|$)/;
// Gewollte Ablehnungen des Backends, die die Oberfläche als Meldung zeigt (der Browser protokolliert sie trotzdem).
// Nur genau diese Kombination aus Status und Route – alles andere bleibt ein Fehler.
const ERWARTETE_ABLEHNUNGEN = [
  { status: 400, route: /\/api\/ausschreibungen\/suchen$/, grund: 'Suche bei ausgeschalteter Internet-Recherche' },
  { status: 400, route: /\/api\/research\/marktbericht$/, grund: 'Marktbericht bei ausgeschalteter Internet-Recherche' },
];

const fehler = [];
const hinweise = new Set();
let pruefungen = 0;
function pruefe(bedingung, text) {
  pruefungen += 1;
  if (!bedingung) fehler.push(text);
  return !!bedingung;
}

function euroAusText(text) {
  const t = String(text || '').replace(/[^\d,\-−]/g, '').replace('−', '-').replace(',', '.');
  const n = parseFloat(t);
  return isFinite(n) ? Math.round(n * 100) : null;
}

async function bereichOeffnen(seite, id) {
  // Immer frisch aufbauen – auch wenn der Bereich schon offen ist (sonst würde ein alter Stand geprüft)
  await seite.evaluate(ziel => {
    if (location.hash === '#' + ziel) window.dispatchEvent(new HashChangeEvent('hashchange'));
    else location.hash = ziel;
  }, id);
  await seite.waitForFunction(ziel => {
    const m = document.querySelector('main');
    return m && m.dataset.bereich === ziel && ['fertig', 'fehler', 'anmeldung'].includes(m.dataset.status);
  }, id, { timeout: 15000 });
  return seite.getAttribute('main', 'data-status');
}

/** API direkt aus der Seite heraus (mit dem Zugangs-Cookie) aufrufen. */
function api(seite, methode, pfad, daten) {
  return seite.evaluate(async ({ methode, pfad, daten }) => {
    const r = await fetch(pfad, {
      method: methode, credentials: 'same-origin',
      headers: methode === 'GET' ? {} : { 'Content-Type': 'application/json' },
      body: methode === 'GET' ? undefined : JSON.stringify(daten || {}),
    });
    let inhalt = null;
    try { inhalt = await r.json(); } catch (e) { inhalt = null; }
    return { status: r.status, inhalt };
  }, { methode, pfad, daten });
}

async function warteAuf(seite, beschreibung, pruefFunktion, sekunden) {
  const ende = Date.now() + (sekunden || 20) * 1000;
  while (Date.now() < ende) {
    const ergebnis = await pruefFunktion();
    if (ergebnis) return ergebnis;
    await seite.waitForTimeout(400);
  }
  fehler.push('Zeitüberschreitung: ' + beschreibung);
  return null;
}

function beobachten(seite, name) {
  const konsole = [];
  seite.on('console', m => {
    if (m.type() !== 'error') return;
    const ort = (m.location() && m.location().url) || '';
    if (/Failed to load resource/.test(m.text()) && OPTIONALE_ROUTEN.test(ort)) {
      hinweise.add('Optionale Route fehlt noch: ' + m.text().replace(/^.*status of /, '') + ' ' + ort.replace(/^https?:\/\/[^/]+/, ''));
      return;
    }
    const erwartet = ERWARTETE_ABLEHNUNGEN.find(e => new RegExp('status of ' + e.status + '\\b').test(m.text()) && e.route.test(ort));
    if (erwartet) {
      hinweise.add('Erwartete Ablehnung (als Meldung angezeigt): ' + erwartet.grund);
      return;
    }
    konsole.push(m.text() + (ort ? ' [' + ort + ']' : ''));
  });
  seite.on('pageerror', e => konsole.push('Skriptfehler: ' + e.message));
  return () => {
    pruefe(konsole.length === 0, name + ': Konsolenfehler: ' + konsole.join(' | '));
  };
}

async function neuerKontext(browser, g) {
  const kontext = await browser.newContext({
    viewport: g.viewport, isMobile: g.isMobile, hasTouch: g.hasTouch, deviceScaleFactor: 1, locale: 'de-DE',
  });
  await kontext.addInitScript(() => {
    window.__cspVerstoesse = [];
    document.addEventListener('securitypolicyviolation', e => {
      window.__cspVerstoesse.push(e.violatedDirective + ' ' + (e.blockedURI || '') + ' ' + (e.sourceFile || '') + ':' + (e.lineNumber || ''));
    });
  });
  return kontext;
}

async function cspPruefen(seite, name) {
  const csp = await seite.evaluate(() => window.__cspVerstoesse || []);
  pruefe(csp.length === 0, name + ': CSP-Verstöße: ' + csp.join(' | '));
}

// ---------------------------------------------------------------------------
// 1. Funktionen bis ins Backend
// ---------------------------------------------------------------------------
async function funktionenPruefen(browser, startUrl) {
  const g = GROESSEN[1];
  const kontext = await neuerKontext(browser, g);
  const seite = await kontext.newPage();
  const konsoleOk = beobachten(seite, 'funktionen');
  await seite.goto(startUrl);
  const st = await bereichOeffnen(seite, 'dashboard');
  if (!pruefe(st === 'fertig', 'Anmeldung über den Startlink hat nicht funktioniert (Status ' + st + ')')) return;

  // Ziel anlegen
  await bereichOeffnen(seite, 'ceo');
  const zielTitel = 'UI-Prüfung Ziel ' + Date.now();
  if (!(await seite.isVisible('[data-pruef="ziel-titel"]'))) await seite.click('[data-pruef="ziel-neu-auf"]');
  await seite.fill('[data-pruef="ziel-titel"]', zielTitel);
  await seite.click('[data-pruef="ziel-absenden"]');
  const zielSichtbar = await seite.waitForFunction(t => {
    const liste = document.querySelector('[data-pruef="ziele-liste"]');
    return liste && liste.textContent.includes(t);
  }, zielTitel, { timeout: 10000 }).then(() => true, () => false);
  pruefe(zielSichtbar, 'Ziel: erscheint nicht in der Liste');
  const ziele = await api(seite, 'GET', '/api/ziele');
  pruefe((ziele.inhalt.ziele || []).some(z => z.titel === zielTitel), 'Ziel: nicht im Backend gespeichert');

  // CEO-Agent beauftragen: Tagesplan, Kennzahlen, Geschäftschancen (über den Research-Agenten)
  for (const knopf of ['Tagesplan erstellen', 'Kennzahlen berechnen', 'Geschäftschancen bewerten']) {
    await seite.click('main button:has-text("' + knopf + '")');
    await seite.waitForTimeout(300);
  }
  const ceoFertig = await warteAuf(seite, 'CEO- und Research-Aufgaben werden nicht fertig', async () => {
    const ceo = (await api(seite, 'GET', '/api/aufgaben?rolle=ceo')).inhalt.aufgaben || [];
    const research = (await api(seite, 'GET', '/api/aufgaben?rolle=research')).inhalt.aufgaben || [];
    const ende = a => ['abgeschlossen', 'fehlgeschlagen', 'abgebrochen'].includes(a.status);
    const typen = ['tagesplan', 'kennzahlen', 'chancen_bewerten'];
    const ceoOk = typen.every(t => ceo.some(a => a.typ === t && ende(a)));
    const markt = research.find(a => a.typ === 'marktbewertung' && ende(a));
    return ceoOk && markt ? { ceo, markt } : null;
  }, 30);
  if (ceoFertig) {
    pruefe(ceoFertig.ceo.every(a => a.status === 'abgeschlossen'), 'CEO: nicht alle Aufträge abgeschlossen');
    await bereichOeffnen(seite, 'ceo');
    const text = await seite.textContent('main');
    pruefe(/Rangliste nach Gewichtung|Letzter Versuch fehlgeschlagen/.test(text), 'CEO: Geschäftschancen werden nicht angezeigt');
    if (ceoFertig.markt.status !== 'abgeschlossen') hinweise.add('Marktbewertung des Research-Agenten fehlgeschlagen: ' + ceoFertig.markt.fehler);
    pruefe(await seite.isVisible('main ol.punkte') || /Nichts offen/.test(text), 'CEO: Tagesplan wird nicht angezeigt');
    pruefe(/Erfolgsquote/.test(text), 'CEO: Kennzahlen werden nicht angezeigt');
  }

  // Simulierte Wallet-Buchung
  await bereichOeffnen(seite, 'wallet');
  const vorher = euroAusText(await seite.textContent('[data-pruef="wallet-stand"]'));
  pruefe(vorher !== null, 'Wallet: Stand nicht lesbar');
  await seite.selectOption('[data-pruef="wallet-art"]', 'ausgabe');
  await seite.fill('[data-pruef="wallet-betrag"]', '1,25');
  await seite.fill('[data-pruef="wallet-kategorie"]', 'ui-pruefung');
  await seite.fill('[data-pruef="wallet-begruendung"]', 'Automatische UI-Prüfung (Simulation)');
  await seite.click('[data-pruef="wallet-absenden"]');
  const erwartet = vorher - 125;
  const standOk = await seite.waitForFunction(e => {
    const el = document.querySelector('[data-pruef="wallet-stand"]');
    if (!el) return false;
    const t = el.textContent.replace(/[^\d,\-−]/g, '').replace('−', '-').replace(',', '.');
    return Math.round(parseFloat(t) * 100) === e;
  }, erwartet, { timeout: 10000 }).then(() => true, () => false);
  pruefe(standOk, 'Wallet: zeigt nach der Buchung nicht den neuen Stand (' + erwartet + ' Cent erwartet)');
  const w1 = await api(seite, 'GET', '/api/wallet');
  pruefe(w1.inhalt.stand_cent === erwartet, 'Wallet: Backend-Stand ' + w1.inhalt.stand_cent + ' statt ' + erwartet + ' Cent');

  // Ungültiger Betrag wird freundlich abgelehnt, nichts gebucht
  await seite.fill('[data-pruef="wallet-betrag"]', 'zwölf');
  await seite.fill('[data-pruef="wallet-kategorie"]', 'ui-pruefung');
  await seite.fill('[data-pruef="wallet-begruendung"]', 'ungültiger Betrag');
  await seite.click('[data-pruef="wallet-absenden"]');
  await seite.waitForTimeout(500);
  // Der Browser meldet das falsche Format direkt am Feld (pattern) – es wird gar nicht erst abgeschickt
  const amFeld = await seite.$eval('[data-pruef="wallet-betrag"]', el => el.validity.patternMismatch && document.activeElement === el);
  pruefe(amFeld, 'Wallet: ungültiger Betrag wird nicht am Feld gemeldet');
  const w2 = await api(seite, 'GET', '/api/wallet');
  pruefe(w2.inhalt.stand_cent === erwartet, 'Wallet: ungültiger Betrag hat trotzdem gebucht');

  // Reale Finanzen: Forderung anlegen – ungespeicherte Eingaben in anderen Formularen bleiben stehen –,
  // dann Zahlung nur mit Nachweis als Einnahme; das Wallet bleibt davon unberührt
  await bereichOeffnen(seite, 'finanzen');
  const ausgabe = 'details[data-schluessel="fin-ausgabe"]';
  const forderungForm = 'details[data-schluessel="fin-forderung"]';
  await seite.click(ausgabe + ' > summary');
  await seite.fill(ausgabe + ' input[name="begruendung"]', 'Entwurf bleibt stehen');
  await seite.click(forderungForm + ' > summary');
  await seite.fill(forderungForm + ' input[name="kunde"]', 'UI-Prüfung Kunde');
  await seite.fill(forderungForm + ' input[name="betrag"]', '1.250,50');
  await seite.click(forderungForm + ' button[type="submit"]');
  const forderung = await warteAuf(seite, 'Forderung wird nicht angelegt', async () => {
    const r = await api(seite, 'GET', '/api/finanzen');
    return (r.inhalt.forderungen || []).find(f => f.kunde === 'UI-Prüfung Kunde') || null;
  }, 10);
  if (forderung) {
    pruefe(forderung.betrag_cent === 125050, 'Finanzen: „1.250,50“ falsch übernommen (' + forderung.betrag_cent + ' Cent)');
    await seite.waitForFunction(() => Array.from(document.querySelectorAll('li.eintrag')).some(li => li.textContent.includes('UI-Prüfung Kunde')),
      null, { timeout: 10000 }).catch(() => null);
    const entwurf = await seite.inputValue(ausgabe + ' input[name="begruendung"]').catch(() => null);
    pruefe(entwurf === 'Entwurf bleibt stehen', 'Finanzen: ungespeicherte Eingabe ging beim Aktualisieren verloren (' + entwurf + ')');
    pruefe(await seite.evaluate(sel => { const d = document.querySelector(sel); return !!d && d.open; }, ausgabe), 'Finanzen: aufgeklappter Bereich ging beim Aktualisieren zu');
    const vorZahlung = (await api(seite, 'GET', '/api/finanzen')).inhalt;
    pruefe(vorZahlung.einnahmen_verifiziert_cent === 0, 'Finanzen: offene Forderung zählt als Einnahme');
    const zeileF = seite.locator('li.eintrag', { hasText: 'UI-Prüfung Kunde' });
    await zeileF.locator('button', { hasText: 'Zahlung ist eingegangen' }).click();
    await zeileF.locator('input[name="zahlungsnachweis"]').fill('Kontoauszug Test, Ref. UI-1');
    await zeileF.locator('input[name="verifiziert_von"]').fill('UI-Prüfung');
    await zeileF.locator('button[type="submit"]').click();
    await warteAuf(seite, 'Zahlung zur Forderung wird nicht als Einnahme gebucht', async () => {
      const r = (await api(seite, 'GET', '/api/finanzen')).inhalt;
      return r.einnahmen_verifiziert_cent === 125050 ? r : null;
    }, 10);
    const w3 = await api(seite, 'GET', '/api/wallet');
    pruefe(w3.inhalt.stand_cent === erwartet, 'Trennung: reale Einnahme hat das Simulations-Wallet verändert');
  }

  // Aufgabe an eine Rolle geben (freundliche Felder) und Ergebnis in den Details
  await bereichOeffnen(seite, 'agenten');
  const form = '[data-pruef="aufgabe-formular"]';
  await seite.selectOption(form + ' select[name="rolle"]', 'finance');
  await seite.selectOption(form + ' select[name="typ"]', 'wirtschaftlichkeit');
  const aufgabenTitel = 'UI-Prüfung Wirtschaftlichkeit ' + Date.now();
  await seite.fill(form + ' input[name="frei_preis"]', '500');
  await seite.fill(form + ' input[name="frei_stunden"]', '10');
  await seite.fill(form + ' input[name="titel"]', aufgabenTitel);
  await seite.click(form + ' button[type="submit"]');
  const fertig = await warteAuf(seite, 'Aufgabe „Wirtschaftlichkeit“ wird nicht abgeschlossen', async () => {
    const r = await api(seite, 'GET', '/api/aufgaben?rolle=finance');
    const a = (r.inhalt.aufgaben || []).find(x => x.titel === aufgabenTitel);
    return a && ['abgeschlossen', 'fehlgeschlagen', 'abgebrochen'].includes(a.status) ? a : null;
  });
  if (fertig) {
    pruefe(fertig.status === 'abgeschlossen', 'Aufgabe: Status ' + fertig.status + ' – ' + (fertig.fehler || ''));
    pruefe(fertig.eingabe && fertig.eingabe.preis === '500' && fertig.eingabe.stunden === 10,
      'Aufgabe: Eingaben der freundlichen Felder falsch übergeben: ' + JSON.stringify(fertig.eingabe));
    await bereichOeffnen(seite, 'aufgaben');
    const zeile = seite.locator('li.eintrag', { hasText: aufgabenTitel });
    await zeile.locator('button', { hasText: 'Details' }).click();
    const details = await seite.waitForFunction(t => {
      const li = Array.from(document.querySelectorAll('li.eintrag')).find(x => x.textContent.includes(t));
      const d = li && li.querySelector('.details-inhalt');
      return d && !d.hidden && d.textContent.includes('Deckungsbeitrag') && d.textContent.includes('Verlauf') ? d.textContent : false;
    }, aufgabenTitel, { timeout: 10000 }).then(r => r.jsonValue(), () => null);
    pruefe(!!details, 'Aufgabe: Details zeigen kein Ergebnis/keinen Verlauf');
    pruefe(details && !/\[object |undefined|NaN/.test(details), 'Aufgabe: Details enthalten „[object …]“, „undefined“ oder „NaN“');
  }

  // Freigabe-Ablauf über die Vertriebsrouten (falls vorhanden)
  const kontakteRoute = await api(seite, 'GET', '/api/kontakte');
  if (kontakteRoute.status !== 200) {
    hinweise.add('Freigabe-Ablauf nicht geprüft: /api/kontakte antwortet ' + kontakteRoute.status);
  } else {
    await freigabeAblauf(seite);
  }

  // Google-Profil-Paket: an erster Stelle, entweder nutzbar oder sichtbar „noch nicht verfügbar“
  await bereichOeffnen(seite, 'produkte');
  const erste = await seite.evaluate(() => {
    const s = document.querySelector('main .ansicht > section');
    return s ? s.dataset.pruef || '' : '';
  });
  pruefe(/^google-profil/.test(erste), 'Produkte: Google-Profil-Paket steht nicht an erster Stelle (' + erste + ')');
  if (erste === 'google-profil') {
    if (!(await seite.isVisible('[data-pruef="google-profil-formular"] input[name="firma"]'))) {
      await seite.click('[data-pruef="google-profil"] summary');
    }
    await seite.fill('[data-pruef="google-profil-formular"] input[name="firma"]', 'UI-Prüfung Reinigung');
    await seite.fill('[data-pruef="google-profil-formular"] input[name="branche"]', 'Gebäudereinigung');
    await seite.fill('[data-pruef="google-profil-formular"] input[name="ort"]', 'Leverkusen');
    await seite.fill('[data-pruef="google-profil-formular"] textarea[name="leistungen"]', 'Treppenhausreinigung\nBüroreinigung');
    await seite.click('[data-pruef="google-profil-absenden"]');
    const ausgang = await seite.waitForFunction(() => {
      const m = Array.from(document.querySelectorAll('.meldung')).map(x => x.textContent).join(' ');
      if (/übergeben/.test(m)) return 'uebergeben';
      if (document.querySelector('[data-pruef="google-profil-nicht-verfuegbar"]')) return 'nicht-verfuegbar';
      return false;
    }, null, { timeout: 10000 }).then(r => r.jsonValue(), () => null);
    pruefe(!!ausgang, 'Produkte: Google-Profil-Formular reagiert nicht');
    if (ausgang === 'nicht-verfuegbar') hinweise.add('Google-Profil-Route fehlt noch – Formular zeigt „noch nicht verfügbar“');
  } else if (erste === 'google-profil-nicht-verfuegbar') {
    const gesperrt = await seite.evaluate(() => {
      const k = document.querySelector('[data-pruef="google-profil-nicht-verfuegbar"]');
      const fs = k && k.querySelector('fieldset');
      return !!k && /noch nicht verfügbar/.test(k.textContent) && !!fs && fs.disabled;
    });
    pruefe(gesperrt, 'Produkte: Google-Profil-Formular ist nicht sichtbar als „noch nicht verfügbar“ gesperrt');
    hinweise.add('Google-Profil-Paket: Product-Agent kann es noch nicht – Formular gesperrt und gekennzeichnet');
  }

  await neueFunktionenPruefen(seite);

  await cspPruefen(seite, 'funktionen');
  konsoleOk();
  await kontext.close();
}

// ---------------------------------------------------------------------------
// 1b. Neue Funktionen: Auftrags-Radar, Einstellungen, Kalkulation, Dauerauftrag, Anschreiben, Rückmeldungen
//     (Auftrags-Radar mit TESTDATEN aus ui_server.py – kein Internet nötig)
// ---------------------------------------------------------------------------
async function meldungMit(seite, muster, sekunden) {
  const ok = await seite.waitForFunction(quelle => {
    const re = new RegExp(quelle);
    return Array.from(document.querySelectorAll('.meldung')).some(m => re.test(m.textContent));
  }, muster.source, { timeout: (sekunden || 10) * 1000 }).then(() => true, () => false);
  // Fehlermeldungen bleiben stehen, bis man sie schließt – danach schließen, damit sie keine weiteren Klicks verdecken
  await seite.$$eval('.meldung.fehler button', bs => bs.forEach(b => b.click())).catch(() => null);
  return ok;
}

async function ausschreibungenApi(seite) {
  const r = await api(seite, 'GET', '/api/ausschreibungen?alle=1');
  return r.status === 200 ? (r.inhalt.ausschreibungen || []) : null;
}

async function neueFunktionenPruefen(seite) {
  // --- Auftrags-Radar (Vertrieb) ---------------------------------------------------------
  const vorher = await ausschreibungenApi(seite);
  if (!pruefe(vorher !== null, 'Auftrags-Radar: /api/ausschreibungen antwortet nicht')) return;
  const einst0 = (await api(seite, 'GET', '/api/einstellungen')).inhalt.werte || {};
  pruefe(einst0.internet_recherche_erlaubt === false, 'Einstellungen: Internet-Recherche ist nicht standardmäßig aus');

  // --- CEO-Zentrale: Marktbericht -------------------------------------------------------
  await bereichOeffnen(seite, 'ceo');
  pruefe(await seite.isVisible('[data-pruef="marktbericht"]'), 'CEO: Karte „Marktbericht“ fehlt');
  pruefe(await seite.isVisible('[data-pruef="marktbericht-recherche-aus"]'), 'CEO: Hinweis „Internet-Recherche aus“ mit Weg zum Einschalten fehlt');
  pruefe(await seite.isVisible('[data-pruef="marktbericht-recherche-einschalten"]'), 'CEO: Knopf „Internet-Recherche einschalten“ fehlt');
  const mbText = (await seite.textContent('[data-pruef="marktbericht-eintrag"]').catch(() => '')) || '';
  pruefe(/90 Tage/.test(mbText) && /Ausschreibungen \(EU, TED\)\s*3/.test(mbText), 'CEO: Bericht (TESTDATEN) wird nicht mit Kennzahlen angezeigt: ' + mbText.slice(0, 120));
  const mbHref = await seite.getAttribute('[data-pruef="marktbericht-ansehen"]', 'href').catch(() => null);
  const mbStatus = mbHref ? await seite.evaluate(async u => (await fetch(u, { credentials: 'same-origin' })).status, mbHref) : 0;
  pruefe(mbHref === '/produkte/marktberichte/ui_test_mb/bericht.html' && mbStatus === 200, 'CEO: „Bericht ansehen“ fehlt oder nicht abrufbar (' + mbHref + ', ' + mbStatus + ')');
  await seite.click('[data-pruef="marktbericht-erstellen"]');
  pruefe(await meldungMit(seite, /Internet-Recherche ist ausgeschaltet/), 'CEO: „Marktbericht erstellen“ bei ausgeschalteter Recherche ohne Meldung des Backends');
  const mbAuf = ((await api(seite, 'GET', '/api/aufgaben?rolle=research')).inhalt.aufgaben || []).filter(a => a.typ === 'marktbericht');
  pruefe(mbAuf.length === 1, 'CEO: Marktbericht-Aufgabe trotz ausgeschalteter Recherche angelegt (' + mbAuf.length + ')');

  await bereichOeffnen(seite, 'vertrieb');
  pruefe(await seite.isVisible('[data-pruef="ausschreibungen"]'), 'Vertrieb: Karte „Öffentliche Ausschreibungen“ fehlt');
  const karteText = (await seite.textContent('[data-pruef="ausschreibungen"]')) || '';
  pruefe(/AUTONOMOUS gibt keine Angebote ab/.test(karteText), 'Vertrieb: Hinweis „AUTONOMOUS gibt keine Angebote ab“ fehlt');
  pruefe(await seite.isVisible('[data-pruef="recherche-aus"] a[href="#einstellungen"]'), 'Vertrieb: Hinweis „Recherche aus – wo einschalten“ fehlt');
  const ids = await seite.$$eval('[data-pruef="ausschreibung"]', els => els.map(e => e.dataset.id));
  pruefe(ids.join(',') === 'ui_test_1,ui_test_2,ui_test_3',
    'Vertrieb: Standardliste (ab 60 Punkten, ohne abgelaufene, nach Punkten) falsch: ' + ids.join(','));
  const frist1 = await seite.getAttribute('[data-id="ui_test_1"] [data-pruef="frist"]', 'class');
  pruefe(/\bfehler\b/.test(frist1 || ''), 'Vertrieb: Frist ≤ 3 Tage ist nicht rot markiert (' + frist1 + ')');
  const frist2 = await seite.getAttribute('[data-id="ui_test_2"] [data-pruef="frist"]', 'class');
  pruefe(!/\bfehler\b/.test(frist2 || ''), 'Vertrieb: Frist in 10 Tagen fälschlich rot');
  const link = await seite.$eval('[data-id="ui_test_1"] a[target="_blank"]', a => ({ href: a.getAttribute('href'), rel: a.getAttribute('rel') }))
    .catch(() => null);
  pruefe(link && /^https:\/\/example\.invalid\/testdaten\/TEST-1$/.test(link.href) && link.rel === 'noopener noreferrer',
    'Vertrieb: Link zur Bekanntmachung fehlt oder ist unsicher: ' + JSON.stringify(link));
  pruefe(/Vergabemarktplatz NRW[\s\S]*Fehler/.test((await seite.textContent('[data-pruef="suchlaeufe"]')) || ''),
    'Vertrieb: Suchlauf-Stand je Quelle (Fehler) wird nicht angezeigt');
  await seite.click('[data-id="ui_test_1"] summary');
  pruefe(/Frist sehr knapp/.test((await seite.textContent('[data-id="ui_test_1"]')) || ''), 'Vertrieb: Begründung der Punkte nicht aufklappbar');

  // Recherche aus → kein „Jetzt suchen“ (würde sicher scheitern), sondern „Internet-Recherche einschalten“ mit Bestätigung
  pruefe(!(await seite.isVisible('[data-pruef="ausschreibungen-suchen"]')), 'Vertrieb: „Jetzt suchen“ trotz ausgeschalteter Recherche angeboten');
  const ein = '[data-pruef="recherche-einschalten"]';
  pruefe(await seite.isVisible(ein), 'Vertrieb: Knopf „Internet-Recherche einschalten“ fehlt');
  await seite.click(ein);
  pruefe(/Nochmal tippen/.test((await seite.textContent(ein)) || ''), 'Vertrieb: Einschalten ohne Bestätigung (zweites Tippen)');
  const nochAus = (await api(seite, 'GET', '/api/einstellungen')).inhalt.werte || {};
  pruefe(nochAus.internet_recherche_erlaubt === false, 'Vertrieb: Recherche schon nach dem ersten Tippen eingeschaltet');
  await seite.click(ein);
  const eingeschaltet = await warteAuf(seite, 'Einschalten kommt nicht im Backend an', async () => {
    const w = (await api(seite, 'GET', '/api/einstellungen')).inhalt.werte || {};
    return w.internet_recherche_erlaubt === true ? w : null;
  }, 10);
  pruefe(!!eingeschaltet, 'Vertrieb: „Internet-Recherche einschalten“ wirkt nicht');
  const sucheDa = await seite.waitForSelector('[data-pruef="ausschreibungen-suchen"]', { timeout: 10000 }).then(() => true, () => false);
  pruefe(sucheDa, 'Vertrieb: nach dem Einschalten fehlt „Jetzt suchen“');
  // Sofort wieder aus (über die API) – die Prüfung soll nie ins Internet; „Jetzt suchen“ wird NICHT angetippt
  await api(seite, 'POST', '/api/einstellungen', { schluessel: 'internet_recherche_erlaubt', wert: false });
  await bereichOeffnen(seite, 'vertrieb');
  const akq = (await api(seite, 'GET', '/api/aufgaben?rolle=akquise')).inhalt.aufgaben || [];
  pruefe(!akq.some(a => a.typ === 'ausschreibungen_suchen'), 'Vertrieb: Suche angelegt, obwohl niemand gesucht hat');

  // Filter: alle Punktzahlen + abgelaufene
  await seite.selectOption('[data-pruef="ausschreibungen-filter-min"]', '0');
  await seite.waitForSelector('[data-id="ui_test_4"]', { timeout: 10000 }).catch(() => null);
  pruefe(await seite.isVisible('[data-id="ui_test_4"]'), 'Vertrieb: Filter „alle Punktzahlen“ zeigt niedrige Treffer nicht');
  pruefe(!(await seite.isVisible('[data-id="ui_test_5"]')), 'Vertrieb: abgelaufene Ausschreibung ohne Filter sichtbar');
  await seite.check('[data-pruef="ausschreibungen-filter-alle"]');
  await seite.waitForSelector('[data-id="ui_test_5"]', { timeout: 10000 }).catch(() => null);
  pruefe(await seite.isVisible('[data-id="ui_test_5"]'), 'Vertrieb: Filter „Abgelaufene zeigen“ wirkt nicht');
  await seite.uncheck('[data-pruef="ausschreibungen-filter-alle"]');
  await seite.waitForSelector('[data-id="ui_test_5"]', { state: 'detached', timeout: 10000 }).catch(() => null);
  await seite.selectOption('[data-pruef="ausschreibungen-filter-min"]', '60');
  await seite.waitForSelector('[data-id="ui_test_4"]', { state: 'detached', timeout: 10000 }).catch(() => null);

  // Status „Interessant“ bis ins Backend
  await seite.click('[data-id="ui_test_3"] [data-pruef="ausschreibung-interessant"]');
  const interessant = await warteAuf(seite, 'Status „interessant“ kommt nicht im Backend an', async () => {
    const l = await ausschreibungenApi(seite);
    return l && l.find(a => a.id === 'ui_test_3' && a.status === 'interessant');
  }, 10);
  pruefe(!!interessant, 'Vertrieb: Status „Interessant“ nicht gespeichert');

  // Bewerbungsmappe erstellen → Link erscheint, Datei ist abrufbar
  await bereichOeffnen(seite, 'vertrieb');
  await seite.click('[data-id="ui_test_1"] [data-pruef="mappe-erstellen"]');
  const mitMappe = await warteAuf(seite, 'Bewerbungsmappe entsteht nicht', async () => {
    const l = await ausschreibungenApi(seite);
    return l && l.find(a => a.id === 'ui_test_1' && a.unterlagen_url);
  }, 20);
  if (mitMappe) {
    await bereichOeffnen(seite, 'vertrieb');
    const href = await seite.getAttribute('[data-id="ui_test_1"] [data-pruef="mappe-ansehen"]', 'href').catch(() => null);
    pruefe(href === mitMappe.unterlagen_url, 'Vertrieb: Link „Bewerbungsmappe ansehen“ fehlt (' + href + ')');
    const datei = await seite.evaluate(async u => (await fetch(u, { credentials: 'same-origin' })).status, mitMappe.unterlagen_url);
    pruefe(datei === 200, 'Vertrieb: Bewerbungsmappe nicht abrufbar (' + datei + ')');
    pruefe(mitMappe.status === 'vorbereitet', 'Vertrieb: Status nach der Mappe ist nicht „vorbereitet“ (' + mitMappe.status + ')');
  }

  // --- Einstellungen: Auftragssuche und Stundensatz --------------------------------------
  await bereichOeffnen(seite, 'einstellungen');
  pruefe(await seite.isVisible('[data-pruef="auftragssuche"]'), 'Einstellungen: Karte „Auftragssuche“ fehlt');
  const kartenReihe = await seite.$$eval('main .ansicht > section.karte', ks => ks.map(k => k.dataset.pruef || ''));
  pruefe(kartenReihe[0] === 'stundensatz-karte', 'Einstellungen: Stundensatz ist nicht die erste Karte (' + kartenReihe.slice(0, 3).join(', ') + ')');
  pruefe(!(await seite.isVisible('[data-schluessel="technik-betrieb"] > [data-pruef="einstellungen-formular"]')), 'Einstellungen: Technik ist nicht eingeklappt');
  const form = '[data-pruef="auftragssuche-formular"]';
  await seite.check(form + ' [data-pruef="recherche-schalter"]');
  await seite.fill(form + ' input[name="region_plz"]', '50, 51, 53');
  await seite.fill(form + ' textarea[name="suchbegriffe"]', 'Reinigung, Treppenhaus, Glasreinigung');
  await seite.click('[data-pruef="auftragssuche-speichern"]');
  const gespeichert = await warteAuf(seite, 'Einstellungen der Auftragssuche kommen nicht im Backend an', async () => {
    const w = (await api(seite, 'GET', '/api/einstellungen')).inhalt.werte || {};
    return w.internet_recherche_erlaubt === true && JSON.stringify(w.region_plz) === '["50","51","53"]'
      && JSON.stringify(w.suchbegriffe) === '["reinigung","treppenhaus","glasreinigung"]' ? w : null;
  }, 10);
  pruefe(!!gespeichert, 'Einstellungen: Recherche/Region/Suchbegriffe nicht (als Listen) gespeichert');
  // Wieder ausschalten – die Prüfung soll nie ins Internet
  await bereichOeffnen(seite, 'einstellungen');
  await seite.uncheck(form + ' [data-pruef="recherche-schalter"]');
  await seite.click('[data-pruef="auftragssuche-speichern"]');
  const aus = await warteAuf(seite, 'Internet-Recherche lässt sich nicht wieder ausschalten', async () => {
    const w = (await api(seite, 'GET', '/api/einstellungen')).inhalt.werte || {};
    return w.internet_recherche_erlaubt === false ? w : null;
  }, 10);
  pruefe(!!aus, 'Einstellungen: Internet-Recherche nicht wieder aus');
  // Ungültige Eingabe: freundliche Meldung (bleibt stehen, mit „Schließen“), nichts halb gespeichert
  await bereichOeffnen(seite, 'einstellungen');
  await seite.fill(form + ' input[name="region_plz"]', '5, 51');
  await seite.fill(form + ' textarea[name="suchbegriffe"]', 'Reinigung, Fenster');
  await seite.click('[data-pruef="auftragssuche-speichern"]');
  await seite.waitForSelector('.meldung.fehler', { timeout: 10000 }).catch(() => null);
  pruefe(await seite.isVisible('.meldung.fehler button:has-text("Schließen")'), 'Fehlermeldung: kein „Schließen“ (sie soll stehen bleiben)');
  await seite.waitForTimeout(9500);
  pruefe(await seite.isVisible('.meldung.fehler'), 'Fehlermeldung verschwindet von selbst (soll bis zum Schließen bleiben)');
  pruefe(await meldungMit(seite, /Postleitzahl-Bereiche/), 'Einstellungen: ungültiger PLZ-Bereich ohne Meldung');
  pruefe(!(await seite.isVisible('.meldung.fehler')), 'Fehlermeldung lässt sich nicht schließen');
  const unveraendert = (await api(seite, 'GET', '/api/einstellungen')).inhalt.werte || {};
  pruefe(JSON.stringify(unveraendert.suchbegriffe) === '["reinigung","treppenhaus","glasreinigung"]' && JSON.stringify(unveraendert.region_plz) === '["50","51","53"]',
    'Einstellungen: bei ungültiger Eingabe wurde trotzdem etwas gespeichert');

  // Stundensatz-Karte: speichern bis ins Backend, danach wieder offen (die Kalkulation unten prüft den offenen Fall)
  await bereichOeffnen(seite, 'einstellungen');
  const sf = '[data-pruef="stundensatz-formular"]';
  await seite.fill(sf + ' input[name="stundensatz"]', '38,50');
  await seite.click('[data-pruef="stundensatz-formular-speichern"]');
  const satzGespeichert = await warteAuf(seite, 'Stundensatz kommt nicht im Backend an', async () => {
    const w = (await api(seite, 'GET', '/api/einstellungen')).inhalt.werte || {};
    return w.stundensatz_cent === 3850 ? w : null;
  }, 10);
  pruefe(!!satzGespeichert, 'Einstellungen: Stundensatz 38,50 € nicht gespeichert');
  // Nach dem Neuaufbau soll der Fokus in der Karte stehen, in der gespeichert wurde – nicht auf der ganzen Seite
  const fokusOk = await seite.waitForFunction(() => {
    const a = document.activeElement;
    return a && a !== document.body && !!a.closest('[data-pruef="stundensatz-karte"]');
  }, null, { timeout: 5000 }).then(() => true, () => false);
  const fokusNach = await seite.evaluate(() => (document.activeElement && (document.activeElement.tagName + ' ' + (document.activeElement.textContent || '').slice(0, 40))) || '');
  pruefe(fokusOk, 'Tastatur: Fokus geht nach dem Speichern verloren (liegt auf ' + fokusNach + ')');
  await seite.fill(sf + ' input[name="stundensatz"]', '');
  await seite.click('[data-pruef="stundensatz-formular-speichern"]');
  const satzOffen = await warteAuf(seite, 'Stundensatz lässt sich nicht wieder auf offen setzen', async () => {
    const w = (await api(seite, 'GET', '/api/einstellungen')).inhalt.werte || {};
    return w.stundensatz_cent === 0 ? w : null;
  }, 10);
  pruefe(!!satzOffen, 'Einstellungen: Stundensatz nicht wieder offen');

  // KI-Modell: Status ohne Modell; Ollama an einer Adresse, an der sicher nichts läuft → ehrlich „nicht erreichbar“
  // (die Prüfung hängt nie von einem echten Modell ab)
  await bereichOeffnen(seite, 'einstellungen');
  pruefe(await seite.isVisible('[data-pruef="ki-modell"]'), 'Einstellungen: Karte „KI-Modell“ fehlt');
  pruefe(/Kein Modell/.test((await seite.textContent('[data-pruef="ki-modell"]')) || ''), 'KI-Modell: Status „Kein Modell“ fehlt');
  pruefe(await seite.isDisabled('[data-pruef="modell-testen"]'), 'KI-Modell: „Modell testen“ ohne Modell nicht gesperrt');
  const kf0 = '[data-pruef="ki-formular"]';
  await seite.check(kf0 + ' [data-pruef="anbieter-ollama"]');
  await seite.fill(kf0 + ' input[name="ollama_adresse"]', 'http://example.com:11434');
  await seite.click('[data-pruef="ki-speichern"]');
  pruefe(await meldungMit(seite, /Adresse: nur dieser Rechner/), 'KI-Modell: fremde Adresse ohne Meldung');
  const kiUnveraendert = (await api(seite, 'GET', '/api/einstellungen')).inhalt.werte || {};
  pruefe(kiUnveraendert.modell_anbieter === 'keiner', 'KI-Modell: bei ungültiger Adresse trotzdem gespeichert');
  await seite.fill(kf0 + ' input[name="ollama_adresse"]', 'http://127.0.0.1:9');
  await seite.click('[data-pruef="ki-speichern"]');
  const kiGespeichert = await warteAuf(seite, 'KI-Einstellungen kommen nicht im Backend an', async () => {
    const w = (await api(seite, 'GET', '/api/einstellungen')).inhalt.werte || {};
    return w.modell_anbieter === 'ollama' && w.ollama_adresse === 'http://127.0.0.1:9' ? w : null;
  }, 10);
  pruefe(!!kiGespeichert, 'KI-Modell: Anbieter/Adresse nicht gespeichert');
  await bereichOeffnen(seite, 'einstellungen');
  pruefe(/Erreichbar\s*nein/.test((await seite.textContent('[data-pruef="ki-modell"]')) || ''), 'KI-Modell: „nicht erreichbar“ wird nicht angezeigt');
  await seite.click('[data-pruef="modell-testen"]');
  const testErgebnis = await seite.waitForFunction(() => {
    const el = document.querySelector('[data-pruef="modell-test-ergebnis"]');
    return el && /Kein Ergebnis/.test(el.textContent);
  }, null, { timeout: 30000 }).then(() => true, () => false);
  pruefe(testErgebnis, 'KI-Modell: „Modell testen“ zeigt bei nicht erreichbarem Modell kein ehrliches Ergebnis');
  await api(seite, 'POST', '/api/einstellungen', { schluessel: 'modell_anbieter', wert: 'keiner' });
  await api(seite, 'POST', '/api/einstellungen', { schluessel: 'ollama_adresse', wert: 'http://127.0.0.1:11434' });

  // --- Kalkulation: ohne Stundensatz → OFFEN, mit 35,00 € → 400,40 € -------------------
  await bereichOeffnen(seite, 'vertrieb');
  const kf = '[data-pruef="kalkulation-formular"]';
  if (!(await seite.isVisible(kf + ' [data-feld="bezeichnung"]'))) await seite.click('[data-schluessel="kalkulation-neu"] > summary');
  await seite.click('[data-pruef="kalk-position-plus"]');
  pruefe((await seite.$$(kf + ' [data-position]')).length === 2, 'Kalkulation: „Position hinzufügen“ wirkt nicht');
  await seite.click(kf + ' [data-position]:nth-child(2) [data-weg]');
  pruefe((await seite.$$(kf + ' [data-position]')).length === 1, 'Kalkulation: „Entfernen“ wirkt nicht');
  await seite.fill(kf + ' [data-feld="bezeichnung"]', 'Treppenhaus');
  await seite.fill(kf + ' [data-feld="flaeche"]', '400');
  await seite.fill(kf + ' [data-feld="leistung"]', '200');
  await seite.fill(kf + ' [data-feld="anzahl"]', '4');
  await seite.selectOption(kf + ' [data-feld="turnus"]', 'monat');
  await seite.fill(kf + ' input[name="material_prozent"]', '5');
  await seite.fill(kf + ' input[name="zuschlag_prozent"]', '10');
  await seite.fill(kf + ' input[name="anfahrten_pro_monat"]', '4');
  await seite.fill(kf + ' input[name="anfahrt_minuten"]', '30');
  await seite.click('[data-pruef="kalkulation-absenden"]');
  const offen = await seite.waitForFunction(() => {
    const el = document.querySelector('[data-pruef="kalk-preis-monat"]');
    return el && /Preis offen/.test(el.textContent);
  }, null, { timeout: 25000 }).then(() => true, () => false);
  pruefe(offen, 'Kalkulation: ohne Stundensatz wird nicht „Preis offen“ angezeigt');
  // Was die Oberfläche selbst zeigt (ohne den Rechenweg und die Hinweise des Agenten): „offen“ genau einmal
  const offenZahl = await seite.$$eval('[data-pruef="kalk-ergebnis"][open]', els => {
    if (!els[0]) return -1;
    const kopie = els[0].querySelector('.kalk-ergebnis').cloneNode(true);
    kopie.querySelectorAll('.rechenweg, [data-pruef="kalk-warnungen"], details, h4').forEach(x => x.remove());
    return (kopie.textContent.match(/offen/gi) || []).length;
  });
  pruefe(offenZahl === 1, 'Kalkulation: „offen“ steht ' + offenZahl + '-mal in der Anzeige (soll einmal deutlich stehen)');
  pruefe(/10 h/.test((await seite.textContent('[data-pruef="kalk-ergebnis"]')) || ''), 'Kalkulation: Stunden (8 h + 2 h Anfahrt = 10 h) fehlen');
  // Die Eingaben bleiben nach dem Neuaufbau stehen; jetzt mit Stundensatz
  if (!(await seite.isVisible(kf + ' input[name="stundensatz"]'))) await seite.click('[data-schluessel="kalkulation-neu"] > summary');
  pruefe((await seite.inputValue(kf + ' [data-feld="flaeche"]')) === '400', 'Kalkulation: Eingaben gehen beim Neuaufbau verloren');
  await seite.fill(kf + ' input[name="stundensatz"]', '35,00');
  await seite.click('[data-pruef="kalkulation-absenden"]');
  const preis = await seite.waitForFunction(() => {
    const el = document.querySelector('[data-pruef="kalk-preis-monat"]');
    return el && /400,40/.test(el.textContent);
  }, null, { timeout: 25000 }).then(() => true, () => false);
  pruefe(preis, 'Kalkulation: mit 35,00 € wird nicht 400,40 € pro Monat angezeigt');
  pruefe(/4\.804,80/.test((await seite.textContent('[data-pruef="kalk-preis-jahr"]')) || ''), 'Kalkulation: Jahrespreis 4.804,80 € fehlt');

  // --- Angebot Dauerauftrag aus der Kalkulation ------------------------------------------
  if (preis) {
    await seite.click('[data-pruef="dauerauftrag-oeffnen"]');
    await seite.fill('[data-pruef="dauerauftrag-formular"] input[name="laufzeit"]', '12 Monate');
    await seite.click('[data-pruef="dauerauftrag-absenden"]');
    const angebot = await warteAuf(seite, 'Angebot Dauerauftrag entsteht nicht', async () => {
      const r = await api(seite, 'GET', '/api/angebote');
      return (r.inhalt.angebote || []).find(a => a.abrechnung === 'monatlich' && a.betrag_cent === 40040) || null;
    }, 20);
    pruefe(!!angebot, 'Dauerauftrag: Angebot aus der Kalkulation fehlt im Backend');
    if (angebot) {
      pruefe(angebot.inhalt && angebot.inhalt.laufzeit === '12 Monate', 'Dauerauftrag: Laufzeit nicht übernommen');
      await bereichOeffnen(seite, 'vertrieb');
      pruefe(/400,40\s*€ \/ Monat/.test((await seite.textContent('[data-pruef="angebot"]')) || ''), 'Dauerauftrag: Liste zeigt die Monatspauschale nicht als „/ Monat“');
    }
  }

  // --- Eingabefehler direkt am Feld (Browser-Prüfung): „vierhundert“ wird gar nicht erst abgeschickt ---
  await bereichOeffnen(seite, 'vertrieb');
  if (!(await seite.isVisible(kf + ' [data-feld="flaeche"]'))) await seite.click('[data-schluessel="kalkulation-neu"] > summary');
  const kalkVorher = ((await api(seite, 'GET', '/api/aufgaben?rolle=finance')).inhalt.aufgaben || []).length;
  await seite.fill(kf + ' [data-feld="bezeichnung"]', 'Treppenhaus');
  await seite.fill(kf + ' [data-feld="leistung"]', '200');
  await seite.fill(kf + ' [data-feld="anzahl"]', '4');
  await seite.fill(kf + ' [data-feld="flaeche"]', 'vierhundert');
  await seite.click('[data-pruef="kalkulation-absenden"]');
  await seite.waitForTimeout(600);
  const feldFehler = await seite.$eval(kf + ' [data-feld="flaeche"]', el => ({ falsch: el.validity.patternMismatch, fokus: document.activeElement === el }));
  pruefe(feldFehler.falsch && feldFehler.fokus, 'Feld-Fehler: „vierhundert“ nicht am Feld gemeldet (' + JSON.stringify(feldFehler) + ')');
  const kalkNachher = ((await api(seite, 'GET', '/api/aufgaben?rolle=finance')).inhalt.aufgaben || []).length;
  pruefe(kalkNachher === kalkVorher, 'Feld-Fehler: trotz falscher Fläche wurde gerechnet');
  await seite.fill(kf + ' [data-feld="flaeche"]', '400');

  // --- Stundensatz direkt in der Kalkulation festlegen (ohne Seitenwechsel) ----------------
  await bereichOeffnen(seite, 'vertrieb');
  await seite.click('[data-pruef="stundensatz-festlegen"]');
  await seite.fill('[data-pruef="stundensatz-kalk"] input[name="stundensatz"]', '35,00');
  await seite.click('[data-pruef="stundensatz-kalk-speichern"]');
  const inline = await warteAuf(seite, 'Stundensatz aus der Kalkulation kommt nicht im Backend an', async () => {
    const w = (await api(seite, 'GET', '/api/einstellungen')).inhalt.werte || {};
    return w.stundensatz_cent === 3500 ? w : null;
  }, 10);
  pruefe(!!inline, 'Kalkulation: „Stundensatz festlegen“ speichert nicht');
  await seite.waitForSelector('[data-pruef="stundensatz-gesetzt"]', { timeout: 10000 }).catch(() => null);
  pruefe(await seite.isVisible('[data-pruef="stundensatz-gesetzt"]'), 'Kalkulation: gespeicherter Stundensatz wird nicht angezeigt');
  await api(seite, 'POST', '/api/einstellungen', { schluessel: 'stundensatz_cent', wert: 0 });

  // --- Sprungleiste: Knopf bringt die Karte nach oben (keine #-Links) ----------------------
  await bereichOeffnen(seite, 'vertrieb');
  pruefe(await seite.isVisible('[data-pruef="sprungleiste"]'), 'Vertrieb: Sprungleiste fehlt');
  await seite.click('[data-sprung-zu="kalkulation"]');
  await seite.waitForTimeout(400);
  const lageZiel = await seite.$eval('[data-sprung="kalkulation"]', el => Math.round(el.getBoundingClientRect().top));
  pruefe(lageZiel >= 0 && lageZiel < 200, 'Vertrieb: Sprungleiste springt nicht zur Karte (oben bei ' + lageZiel + ' px)');
  pruefe((await seite.evaluate(() => location.hash)) === '#vertrieb', 'Vertrieb: Sprungleiste verändert die Adresse');

  // --- Anschreiben mit Auswahl „Reinigung“ -----------------------------------------------
  const kontakte = (await api(seite, 'GET', '/api/kontakte')).inhalt.kontakte || [];
  if (kontakte.length) {
    await bereichOeffnen(seite, 'vertrieb');
    await seite.click('main button:has-text("Nachricht entwerfen")');
    await seite.selectOption('[data-pruef="nachricht-formular"] select[name="angebot"]', 'reinigung');
    await seite.fill('[data-pruef="nachricht-formular"] input[name="anlass"]', 'Erstkontakt Hausverwaltung');
    await seite.click('[data-pruef="nachricht-absenden"]');
    const entwurf = await warteAuf(seite, 'Anschreiben „Reinigung“ entsteht nicht', async () => {
      const l = (await api(seite, 'GET', '/api/aufgaben?rolle=sales')).inhalt.aufgaben || [];
      return l.find(a => a.typ === 'nachricht_entwurf' && a.eingabe && a.eingabe.angebot === 'reinigung' && a.status === 'abgeschlossen') || null;
    }, 20);
    pruefe(!!entwurf, 'Anschreiben: Auswahl „Reinigung“ kommt nicht im Backend an');
  } else {
    hinweise.add('Anschreiben-Auswahl nicht geprüft: kein Kontakt vorhanden');
  }

  // --- Rückmeldungen ----------------------------------------------------------------------
  const rm = await api(seite, 'GET', '/api/rueckmeldungen');
  await bereichOeffnen(seite, 'vertrieb');
  if (rm.status === 200) {
    const rf = '[data-pruef="rueckmeldung-formular"]';
    if (!(await seite.isVisible(rf + ' select[name="reaktion"]'))) await seite.click('[data-schluessel="rueckmeldung-neu"] > summary');
    await seite.selectOption(rf + ' select[name="reaktion"]', 'interessiert');
    pruefe(await seite.isDisabled(rf + ' select[name="grund"]'), 'Rückmeldungen: Grund bei „interessiert“ nicht gesperrt');
    await seite.selectOption(rf + ' select[name="reaktion"]', 'abgelehnt');
    pruefe(!(await seite.isDisabled(rf + ' select[name="grund"]')), 'Rückmeldungen: Grund bei „abgelehnt“ gesperrt');
    await seite.selectOption(rf + ' select[name="grund"]', 'preis');
    const reaktion = 'abgelehnt';
    await seite.fill(rf + ' textarea[name="notiz"]', 'UI-Prüfung Rückmeldung');
    await seite.click('[data-pruef="rueckmeldung-formular-absenden"]');
    const neu = await warteAuf(seite, 'Rückmeldung kommt nicht im Backend an', async () => {
      const r = await api(seite, 'GET', '/api/rueckmeldungen');
      return (r.inhalt.rueckmeldungen || []).find(x => x.notiz === 'UI-Prüfung Rückmeldung') || null;
    }, 10);
    const meldungenJetzt = await seite.$$eval('.meldung', ms => ms.map(m => m.textContent).join(' | '));
    pruefe(!!neu && neu.reaktion === reaktion && neu.grund === 'preis',
      'Rückmeldungen: Eintrag nicht oder falsch gespeichert (Meldungen: ' + meldungenJetzt + ')');
    await bereichOeffnen(seite, 'vertrieb');
    await seite.click('[data-pruef="rueckmeldungen-auswerten"]');
    const ausw = await seite.waitForSelector('[data-pruef="rueckmeldungen-auswertung"]', { timeout: 25000 }).then(() => true, () => false);
    pruefe(ausw, 'Rückmeldungen: Auswertung wird nicht angezeigt');
    if (ausw) {
      await seite.click('[data-pruef="rueckmeldungen-auswertung"] > summary');
      const t = (await seite.textContent('[data-pruef="rueckmeldungen-auswertung"]')) || '';
      pruefe(/Rückmeldungen gesamt/.test(t) && /Preis zu hoch 1×/.test(t), 'Rückmeldungen: Auswertung nicht lesbar aufbereitet');
    }
  } else {
    pruefe(await seite.isVisible('[data-pruef="rueckmeldungen-nicht-verfuegbar"]'),
      'Rückmeldungen: Route fehlt (' + rm.status + '), aber kein „noch nicht verfügbar“');
    hinweise.add('Rückmeldungen: Route antwortet ' + rm.status + ' – Bereich ist als „noch nicht verfügbar“ markiert');
  }

  // --- Dashboard: Kachel „Ausschreibungen“ aus echten Daten -------------------------------
  await bereichOeffnen(seite, 'dashboard');
  const passend = await api(seite, 'GET', '/api/ausschreibungen?min_punkte=60');
  const erwartet = (passend.inhalt.ausschreibungen || []).filter(a => a.status === 'neu').length;
  const wert = ((await seite.textContent('[data-pruef="ausschreibungen-kachel"]')) || '').trim();
  pruefe(wert === String(erwartet), 'Dashboard: Kachel „Ausschreibungen“ zeigt ' + wert + ' statt ' + erwartet);
}

async function freigabeAblauf(seite) {
  const firma = 'UI-Prüfung GmbH ' + Date.now();
  const k = await api(seite, 'POST', '/api/kontakte', { firma, quelle: 'automatische UI-Prüfung', ort: 'Leverkusen' });
  if (!pruefe(k.status === 200 && k.inhalt.id, 'Freigabe-Ablauf: Kontakt anlegen ' + k.status + ' ' + JSON.stringify(k.inhalt))) return;
  const titel = ['UI-Prüfung Angebot A', 'UI-Prüfung Angebot B'];
  for (const t of titel) {
    const r = await api(seite, 'POST', '/api/angebote', { kontakt_id: k.inhalt.id, betrag: '450', titel: t });
    pruefe(r.status === 200, 'Freigabe-Ablauf: Angebot anlegen ' + r.status + ' ' + JSON.stringify(r.inhalt));
  }
  const angebote = await warteAuf(seite, 'Angebotsentwürfe entstehen nicht', async () => {
    const r = await api(seite, 'GET', '/api/angebote');
    const liste = (r.inhalt.angebote || []).filter(a => a.kontakt_id === k.inhalt.id);
    return liste.length >= 2 ? liste : null;
  });
  if (!angebote) return;
  for (const a of angebote) {
    const r = await api(seite, 'POST', '/api/angebote/' + a.id + '/status', { status: 'geprueft' });
    pruefe(r.status === 200, 'Freigabe-Ablauf: Angebot prüfen ' + r.status + ' ' + JSON.stringify(r.inhalt));
    const v = await api(seite, 'POST', '/api/angebote/' + a.id + '/versenden', {});
    pruefe(v.status === 200, 'Freigabe-Ablauf: Versand anfragen ' + v.status + ' ' + JSON.stringify(v.inhalt));
  }
  const offen = await warteAuf(seite, 'Freigaben für den Versand entstehen nicht', async () => {
    const r = await api(seite, 'GET', '/api/freigaben?status=offen');
    const liste = (r.inhalt.freigaben || []).filter(f => angebote.some(a => String(f.ziel).includes(a.id)));
    return liste.length >= 2 ? liste : null;
  });
  if (!offen) return;

  // Dashboard zeigt die offenen Freigaben mit allen Angaben
  await bereichOeffnen(seite, 'dashboard');
  const karte = await seite.textContent('[data-pruef="freigabe"]');
  for (const wort of ['Ziel', 'Mögliche Kosten', 'Datenumfang', 'Folgen', 'Angefragt von', 'Sales-Agent', 'Ja, einmalig erlauben', 'Nein']) {
    pruefe((karte || '').includes(wort), 'Freigabe-Karte: „' + wort + '“ fehlt');
  }

  // In „Aufgaben“ die erste ablehnen: zweimal tippen, dann endgültig
  const ziel = offen[0];
  await bereichOeffnen(seite, 'aufgaben');
  const karteA = seite.locator('[data-pruef="freigabe"]', { hasText: ziel.ziel });
  const nein = karteA.locator('[data-pruef="freigabe-nein"]');
  await nein.click();
  const scharf = await nein.textContent();
  pruefe(/Nochmal tippen/.test(scharf || ''), 'Freigabe: „Nein“ fragt nicht nach (Text: ' + scharf + ')');
  const zwischen = await api(seite, 'GET', '/api/freigaben?status=offen');
  pruefe((zwischen.inhalt.freigaben || []).some(f => f.id === ziel.id), 'Freigabe: schon nach dem ersten Tippen entschieden');
  await nein.click();
  const entschieden = await warteAuf(seite, 'Ablehnung kommt nicht im Backend an', async () => {
    const r = await api(seite, 'GET', '/api/freigaben');
    const f = (r.inhalt.freigaben || []).find(x => x.id === ziel.id);
    return f && f.status !== 'offen' ? f : null;
  }, 10);
  if (entschieden) pruefe(entschieden.status === 'abgelehnt', 'Freigabe: Status ' + entschieden.status + ' statt abgelehnt');
  const aufgabe = await warteAuf(seite, 'Versand-Aufgabe wird nach dem Nein nicht abgebrochen', async () => {
    const r = await api(seite, 'GET', '/api/aufgaben?rolle=sales');
    const a = (r.inhalt.aufgaben || []).find(x => x.freigabe_id === ziel.id);
    return a && a.status !== 'wartet_auf_freigabe' ? a : null;
  }, 10);
  if (aufgabe) pruefe(aufgabe.status === 'abgebrochen', 'Freigabe: Versand-Aufgabe hat Status ' + aufgabe.status);
  const sichtbar = await seite.waitForFunction(t => {
    const offeneKarten = Array.from(document.querySelectorAll('[data-pruef="freigabe"]')).filter(k => k.textContent.includes(t));
    return offeneKarten.length === 0;
  }, ziel.ziel, { timeout: 10000 }).then(() => true, () => false);
  pruefe(sichtbar, 'Freigabe: abgelehnte Freigabe wird weiter als offen angezeigt');

  // Vertrieb zeigt den Versand-Stand je Angebot und bietet keinen zweiten Versand an
  await bereichOeffnen(seite, 'vertrieb');
  const zeilen = await seite.evaluate(ids => Array.from(document.querySelectorAll('[data-pruef="angebot"]'))
    .map(z => ({ text: z.textContent, knopf: !!z.querySelector('[data-pruef="angebot-versenden"]') })), null);
  const abgelehnteZeile = zeilen.filter(z => z.text.includes('Versand abgelehnt (endgültig)'));
  const wartendeZeile = zeilen.filter(z => z.text.includes('Versand wartet auf eure Freigabe'));
  pruefe(abgelehnteZeile.length === 1, 'Vertrieb: abgelehnter Versand wird nicht angezeigt (' + abgelehnteZeile.length + ')');
  pruefe(wartendeZeile.length === 1, 'Vertrieb: wartender Versand wird nicht angezeigt (' + wartendeZeile.length + ')');
  pruefe(abgelehnteZeile.concat(wartendeZeile).every(z => !z.knopf), 'Vertrieb: „Versand anfragen“ trotz bestehender Freigabe');
  // Die zweite Freigabe bleibt offen – sie erscheint in der Ansichtsprüfung auf Dashboard und Aufgaben.
}

// ---------------------------------------------------------------------------
// 2. Ansicht in beiden Größen
// ---------------------------------------------------------------------------
async function ansichtPruefen(browser, startUrl, g, bilder) {
  const kontext = await neuerKontext(browser, g);
  const seite = await kontext.newPage();
  const konsoleOk = beobachten(seite, g.name);
  await seite.goto(startUrl);
  await bereichOeffnen(seite, 'dashboard');

  for (const id of BEREICHE) {
    const status = await bereichOeffnen(seite, id);
    pruefe(status === 'fertig', g.name + '/' + id + ': Bereich lädt nicht (Status ' + status + ')');
    await seite.waitForTimeout(150);
    const lage = await seite.evaluate(() => ({
      s: document.documentElement.scrollWidth, i: window.innerWidth, text: document.querySelector('main').innerText,
    }));
    pruefe(lage.s <= lage.i, g.name + '/' + id + ': waagerechte Scrollleiste (' + lage.s + ' > ' + lage.i + ' px)');
    const kaputt = /\[object [A-Za-z]+\]|\bundefined\b|\bNaN\b/.exec(lage.text);
    pruefe(!kaputt, g.name + '/' + id + ': Darstellungsfehler im Text: „' + (kaputt && kaputt[0]) + '“');
    const titel = await seite.textContent('#seitentitel');
    pruefe(titel && titel.trim().length > 0, g.name + '/' + id + ': kein Seitentitel');
    if (id === 'dashboard') {
      const betrieb = await seite.textContent('[data-pruef="betrieb"]');
      pruefe(/läuft/.test(betrieb || ''), g.name + ': Dashboard zeigt nicht „läuft“ (sondern: ' + betrieb + ')');
      pruefe(await seite.isVisible('[data-pruef="dash-vertrieb"]'), g.name + ': Dashboard ohne Vertriebs-Kacheln');
      pruefe(await seite.isVisible('[data-pruef="naechste-schritte"]'), g.name + ': Dashboard ohne „Nächste Schritte“');
      pruefe(!/Fortschritt/.test(lage.text), g.name + ': Dashboard zeigt noch „Fortschritt“ in Prozent');
    }
    if (id === 'wallet') {
      const banner = await seite.textContent('[data-pruef="wallet-banner"]');
      pruefe(/SIMULATION/.test(banner || '') && /kein echtes Geld/.test(banner || ''), g.name + ': Wallet ist nicht deutlich als SIMULATION gekennzeichnet');
    }
    if (id === 'vertrieb') {
      pruefe(await seite.isVisible('[data-pruef="ausschreibungen"]'), g.name + ': Vertrieb ohne Auftrags-Radar');
      pruefe(await seite.isVisible('[data-pruef="kalkulation"]'), g.name + ': Vertrieb ohne Kalkulation');
    }
    if (id === 'einstellungen') {
      pruefe(await seite.isVisible('[data-pruef="auftragssuche"]'), g.name + ': Einstellungen ohne Auftragssuche');
    }
    if (id === 'finanzen') {
      const banner = await seite.textContent('[data-pruef="finanzen-banner"]');
      pruefe(/REAL/.test(banner || ''), g.name + ': Finanzen sind nicht als REAL gekennzeichnet');
    }
    if (g.isMobile) {
      const zuKlein = await seite.evaluate(() => {
        const sichtbar = el => {
          const r = el.getBoundingClientRect();
          return r.width > 0 && r.height > 0 && getComputedStyle(el).visibility !== 'hidden';
        };
        const ziele = Array.from(document.querySelectorAll(
          'main button, main a.knopf, main input:not([type=checkbox]):not([type=radio]), main select, main textarea, main summary, #nav-unten a, #nav-unten button'));
        return ziele.filter(sichtbar).filter(el => el.getBoundingClientRect().height < 43.5)
          .map(el => el.tagName.toLowerCase() + ' „' + (el.textContent || el.name || '').trim().slice(0, 30) + '“ ' + Math.round(el.getBoundingClientRect().height) + 'px');
      });
      pruefe(zuKlein.length === 0, g.name + '/' + id + ': Tippflächen unter 44 px: ' + zuKlein.slice(0, 5).join('; '));
    }
    if (bilder) await seite.screenshot({ path: bilder + '/' + g.name + '-' + id + '.png', fullPage: true });
  }

  if (g.isMobile) {
    await bereichOeffnen(seite, 'dashboard');
    await seite.click('#mehr-auf');
    await seite.waitForSelector('#mehr-blatt:not([hidden])');
    pruefe(await seite.evaluate(() => document.querySelector('.app').inert === true && document.getElementById('nav-unten').inert === true),
      g.name + ': „Mehr“-Blatt sperrt den Hintergrund nicht (Tab läuft in den verdeckten Inhalt)');
    if (bilder) await seite.screenshot({ path: bilder + '/' + g.name + '-mehr.png' });
    await seite.click('#nav-mehr a[data-nav="einstellungen"]');
    const ok = await seite.waitForFunction(() => {
      const m = document.querySelector('main');
      return m.dataset.bereich === 'einstellungen' && m.dataset.status === 'fertig' && document.getElementById('mehr-blatt').hidden;
    }, null, { timeout: 15000 }).then(() => true, () => false);
    pruefe(ok, g.name + ': Navigation über „Mehr“ funktioniert nicht');
    pruefe(await seite.evaluate(() => document.querySelector('.app').inert === false), g.name + ': nach dem Schließen bleibt der Hintergrund gesperrt');
  }

  await cspPruefen(seite, g.name);
  konsoleOk();
  await kontext.close();
}

// ---------------------------------------------------------------------------
async function main() {
  const startUrl = process.argv[2];
  if (!startUrl || !/[?&]k=/.test(startUrl)) {
    console.error('Aufruf: node ui_pruefung.js "http://127.0.0.1:PORT/?k=SCHLUESSEL"');
    process.exit(2);
  }
  const bilder = process.env.UI_BILDER || '';
  const browser = await chromium.launch();
  try {
    await funktionenPruefen(browser, startUrl);
    for (const g of GROESSEN) await ansichtPruefen(browser, startUrl, g, bilder);

    // Ohne Zugangsschlüssel: freundlicher Hinweis statt Daten
    const fremd = await browser.newContext({ viewport: { width: 390, height: 844 }, deviceScaleFactor: 1 });
    const seite = await fremd.newPage();
    await seite.goto(new URL(startUrl).origin + '/');
    const ohne = await seite.waitForFunction(() => document.querySelector('main').dataset.status === 'anmeldung', null, { timeout: 10000 })
      .then(() => true, () => false);
    pruefe(ohne, 'ohne Schlüssel: kein Anmeldehinweis');
    pruefe(/Startlink/.test((await seite.textContent('main')) || ''), 'ohne Schlüssel: Hinweis auf den Startlink fehlt');
    if (bilder) await seite.screenshot({ path: bilder + '/ohne-schluessel.png' });
    await fremd.close();
  } finally {
    await browser.close();
  }

  for (const h of hinweise) console.log('HINWEIS  ' + h);
  if (fehler.length) {
    for (const f of fehler) console.log('FEHLER   ' + f);
    console.log('\nUI-Prüfung: ' + fehler.length + ' von ' + pruefungen + ' Prüfungen fehlgeschlagen.');
    process.exit(1);
  }
  console.log('UI-Prüfung: alle ' + pruefungen + ' Prüfungen bestanden.');
}

main().catch(e => {
  console.error('UI-Prüfung abgebrochen:', e && e.stack ? e.stack : e);
  process.exit(1);
});
