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
const OPTIONALE_ROUTEN = /\/api\/(produkte|kontakte|angebote|vertrieb)(\/|\?|$)/;

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
  await seite.evaluate(ziel => { location.hash = ziel; }, id);
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
  const abgelehnt = await seite.waitForSelector('.meldung.fehler', { timeout: 5000 }).then(() => true, () => false);
  pruefe(abgelehnt, 'Wallet: ungültiger Betrag wird nicht gemeldet');
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

  await cspPruefen(seite, 'funktionen');
  konsoleOk();
  await kontext.close();
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
    }
    if (id === 'wallet') {
      const banner = await seite.textContent('[data-pruef="wallet-banner"]');
      pruefe(/SIMULATION/.test(banner || '') && /kein echtes Geld/.test(banner || ''), g.name + ': Wallet ist nicht deutlich als SIMULATION gekennzeichnet');
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
    if (bilder) await seite.screenshot({ path: bilder + '/' + g.name + '-mehr.png' });
    await seite.click('#nav-mehr a[data-nav="einstellungen"]');
    const ok = await seite.waitForFunction(() => {
      const m = document.querySelector('main');
      return m.dataset.bereich === 'einstellungen' && m.dataset.status === 'fertig' && document.getElementById('mehr-blatt').hidden;
    }, null, { timeout: 15000 }).then(() => true, () => false);
    pruefe(ok, g.name + ': Navigation über „Mehr“ funktioniert nicht');
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
