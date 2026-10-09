/*
 * Jarvis-Erweiterung - gemeinsame Teile für Popup, Einstellungen und Hintergrund.
 *
 * Warum eine eigene Datei: Popup und Hintergrunddienst (Service Worker) reden
 * beide mit Jarvis und lesen beide Webseiten aus. Steht der Code nur einmal da,
 * verhalten sich beide Wege gleich - gleiche Kürzung, gleiche Fehlermeldungen,
 * gleiche Behandlung des Zugangsschlüssels.
 *
 * Sicherheit: Die Erweiterung redet nur mit Jarvis auf diesem Rechner
 * (localhost bzw. 127.0.0.1, Port 8765). Genau das steht auch in den
 * host_permissions und in der CSP des Manifests. Eine andere Adresse in den
 * Einstellungen wird abgelehnt - sonst ließen sich Seiteninhalte unbemerkt an
 * einen fremden Server schicken.
 *
 * Alle Namen beginnen mit "jarvis", weil Popup und Einstellungen diese Datei
 * als normales Skript laden und sie sich den globalen Namensraum teilen.
 */
'use strict';

const JARVIS_STANDARD_ADRESSE = 'http://localhost:8765';
const JARVIS_ERLAUBTE_ADRESSEN = ['http://localhost:8765', 'http://127.0.0.1:8765'];
const JARVIS_AUFTRAEGE = ['zusammenfassen', 'kontakte', 'frage'];
const JARVIS_GRENZEN = { text: 15000, auswahl: 4000, frage: 2000, titel: 300, adresse: 2000 };
// Jarvis denkt mit Werkzeugen mitunter lange nach - aber nicht ewig.
const JARVIS_WARTEZEIT_MS = 240000;
const JARVIS_MELDUNG_AUS = 'Jarvis läuft nicht - starte JARVIS.command.';
const JARVIS_ABLAGE_LETZTE = 'jarvisLetzte';

/** Macht aus einer Eingabe eine erlaubte Jarvis-Adresse - oder sagt, warum nicht. */
function jarvisAdresseSaeubern(roh) {
  let text = String(roh == null ? '' : roh).trim();
  if (!text) {
    return { ok: true, adresse: JARVIS_STANDARD_ADRESSE };
  }
  if (!/^[a-z][a-z0-9+.-]*:\/\//i.test(text)) {
    text = 'http://' + text;
  }
  let ziel;
  try {
    ziel = new URL(text);
  } catch (fehler) {
    return { ok: false, fehler: 'Das ist keine gültige Adresse.' };
  }
  const sauber = (ziel.protocol + '//' + ziel.host).toLowerCase();
  if (ziel.username || ziel.password || JARVIS_ERLAUBTE_ADRESSEN.indexOf(sauber) < 0) {
    return {
      ok: false,
      fehler: 'Erlaubt sind nur http://localhost:8765 und http://127.0.0.1:8765 - '
        + 'Jarvis läuft auf diesem Rechner.'
    };
  }
  return { ok: true, adresse: sauber };
}

/** Prüft den Zugangsschlüssel. Er geht als HTTP-Kopf mit, also nur druckbares ASCII. */
function jarvisSchluesselSaeubern(roh) {
  const text = String(roh == null ? '' : roh).replace(/\s+/g, '');
  if (text.length > 200) {
    return { ok: false, fehler: 'Der Zugangsschlüssel ist zu lang.' };
  }
  if (!/^[\x21-\x7e]*$/.test(text)) {
    return { ok: false, fehler: 'Der Zugangsschlüssel enthält ungültige Zeichen.' };
  }
  return { ok: true, schluessel: text };
}

/** Liest Adresse und Schlüssel aus chrome.storage.local - mit sicheren Vorgaben. */
async function jarvisEinstellungenLesen() {
  let gespeichert = {};
  try {
    gespeichert = (await chrome.storage.local.get(['jarvisAdresse', 'jarvisSchluessel'])) || {};
  } catch (fehler) {
    gespeichert = {};
  }
  const adresse = jarvisAdresseSaeubern(gespeichert.jarvisAdresse);
  const schluessel = jarvisSchluesselSaeubern(gespeichert.jarvisSchluessel);
  return {
    adresse: adresse.ok ? adresse.adresse : JARVIS_STANDARD_ADRESSE,
    schluessel: schluessel.ok ? schluessel.schluessel : ''
  };
}

/** Speichert die Einstellungen - nur, wenn beide Werte in Ordnung sind. */
async function jarvisEinstellungenSpeichern(adresseRoh, schluesselRoh) {
  const adresse = jarvisAdresseSaeubern(adresseRoh);
  if (!adresse.ok) {
    return adresse;
  }
  const schluessel = jarvisSchluesselSaeubern(schluesselRoh);
  if (!schluessel.ok) {
    return schluessel;
  }
  try {
    await chrome.storage.local.set({
      jarvisAdresse: adresse.adresse,
      jarvisSchluessel: schluessel.schluessel
    });
  } catch (fehler) {
    return { ok: false, fehler: 'Die Einstellungen ließen sich nicht speichern.' };
  }
  return {
    ok: true,
    adresse: adresse.adresse,
    text: 'Gespeichert. Jarvis wird unter ' + adresse.adresse + ' erreicht'
      + (schluessel.schluessel ? ', mit Zugangsschlüssel.' : ', ohne Zugangsschlüssel.')
  };
}

/** Kürzt einen Wert auf eine Höchstlänge - und macht aus allem einen Text. */
function jarvisKuerzen(wert, grenze) {
  const text = String(wert == null ? '' : wert).trim();
  return text.length > grenze ? text.slice(0, grenze) : text;
}

/**
 * Baut den Körper für POST /api/seite.
 * Felder laut Absprache: auftrag, frage, adresse, titel, text, auswahl.
 * "kontaktlinks" ist eine freiwillige Zugabe (mailto:/tel:-Links der Seite).
 */
function jarvisKoerperBauen(auftrag, angaben) {
  const quelle = angaben || {};
  const koerper = {
    auftrag: auftrag,
    frage: jarvisKuerzen(quelle.frage, JARVIS_GRENZEN.frage),
    adresse: jarvisKuerzen(quelle.adresse, JARVIS_GRENZEN.adresse),
    titel: jarvisKuerzen(quelle.titel, JARVIS_GRENZEN.titel),
    text: jarvisKuerzen(quelle.text, JARVIS_GRENZEN.text),
    auswahl: jarvisKuerzen(quelle.auswahl, JARVIS_GRENZEN.auswahl)
  };
  if (Array.isArray(quelle.kontaktlinks) && quelle.kontaktlinks.length) {
    koerper.kontaktlinks = quelle.kontaktlinks.slice(0, 20).map(function (link) {
      return jarvisKuerzen(link, 200);
    });
  }
  return koerper;
}

/** Deutet die Antwort von Jarvis. Rein, ohne Netz - damit lässt sie sich prüfen. */
function jarvisAntwortDeuten(status, daten) {
  const fehlertext = daten && typeof daten.fehler === 'string' ? daten.fehler.trim() : '';
  if (status === 404) {
    return {
      ok: false,
      fehler: 'Diese Jarvis-Version kennt die Erweiterung noch nicht (/api/seite fehlt). '
        + 'Bitte Jarvis aktualisieren.'
    };
  }
  if (!daten || typeof daten !== 'object' || Array.isArray(daten)) {
    return {
      ok: false,
      fehler: 'Unter dieser Adresse antwortet etwas, aber nicht Jarvis (Status ' + status + ').'
    };
  }
  if (status === 403) {
    const hinweis = /schl(ü|ue)ssel/i.test(fehlertext)
      ? ' Trag den Zugangsschlüssel in den Einstellungen der Erweiterung ein.'
      : '';
    return { ok: false, fehler: (fehlertext || 'Jarvis lässt die Erweiterung nicht herein.') + hinweis };
  }
  const antworttext = typeof daten.antwort === 'string' ? daten.antwort.trim()
    : (typeof daten.text === 'string' ? daten.text.trim() : '');
  if (daten.ok === true && status < 400) {
    return { ok: true, antwort: antworttext || 'Jarvis hat geantwortet, aber nichts gesagt.' };
  }
  return {
    ok: false,
    fehler: fehlertext || antworttext || ('Jarvis meldet einen Fehler (Status ' + status + ').')
  };
}

/**
 * Schickt einen Auftrag an Jarvis: POST <adresse>/api/seite.
 * Gibt immer {ok: true, antwort} oder {ok: false, fehler} zurück - nie eine Ausnahme.
 */
async function jarvisSenden(auftrag, angaben) {
  if (JARVIS_AUFTRAEGE.indexOf(auftrag) < 0) {
    return { ok: false, fehler: 'Diesen Auftrag kennt die Erweiterung nicht.' };
  }
  const koerper = jarvisKoerperBauen(auftrag, angaben);
  if (auftrag === 'frage' && !koerper.frage) {
    return { ok: false, fehler: 'Bitte zuerst eine Frage eingeben.' };
  }
  const einstellungen = await jarvisEinstellungenLesen();
  const koepfe = { 'Content-Type': 'application/json' };
  if (einstellungen.schluessel) {
    koepfe['X-Jarvis-Schluessel'] = einstellungen.schluessel;
  }
  const abbruch = new AbortController();
  const uhr = setTimeout(function () { abbruch.abort(); }, JARVIS_WARTEZEIT_MS);
  try {
    let antwort;
    try {
      antwort = await fetch(einstellungen.adresse + '/api/seite', {
        method: 'POST',
        headers: koepfe,
        body: JSON.stringify(koerper),
        signal: abbruch.signal,
        credentials: 'omit',
        cache: 'no-store',
        redirect: 'error',
        referrerPolicy: 'no-referrer'
      });
    } catch (fehler) {
      if (fehler && fehler.name === 'AbortError') {
        return { ok: false, fehler: 'Jarvis hat nach vier Minuten nicht geantwortet. Versuch es bitte noch einmal.' };
      }
      return { ok: false, fehler: JARVIS_MELDUNG_AUS, nicht_erreichbar: true };
    }
    let daten = null;
    try {
      daten = await antwort.json();
    } catch (fehler) {
      if (fehler && fehler.name === 'AbortError') {
        return { ok: false, fehler: 'Jarvis hat nach vier Minuten nicht geantwortet. Versuch es bitte noch einmal.' };
      }
      daten = null;
    }
    return jarvisAntwortDeuten(antwort.status, daten);
  } finally {
    clearTimeout(uhr);
  }
}

/** Fragt Jarvis, ob er da ist (GET /api/zustand) - für "Verbindung testen". */
async function jarvisVerbindungTesten(adresseRoh, schluesselRoh) {
  const adresse = jarvisAdresseSaeubern(adresseRoh);
  if (!adresse.ok) {
    return adresse;
  }
  const schluessel = jarvisSchluesselSaeubern(schluesselRoh);
  if (!schluessel.ok) {
    return schluessel;
  }
  const koepfe = {};
  if (schluessel.schluessel) {
    koepfe['X-Jarvis-Schluessel'] = schluessel.schluessel;
  }
  const abbruch = new AbortController();
  const uhr = setTimeout(function () { abbruch.abort(); }, 15000);
  try {
    const antwort = await fetch(adresse.adresse + '/api/zustand', {
      headers: koepfe, signal: abbruch.signal, credentials: 'omit', cache: 'no-store',
      redirect: 'error', referrerPolicy: 'no-referrer'
    });
    let daten = null;
    try {
      daten = await antwort.json();
    } catch (fehler) {
      daten = null;
    }
    if (antwort.status === 403) {
      return { ok: false, fehler: 'Jarvis läuft, aber der Zugangsschlüssel fehlt oder stimmt nicht.' };
    }
    if (!antwort.ok || !daten || typeof daten !== 'object') {
      return { ok: false, fehler: 'Unter dieser Adresse antwortet etwas, aber nicht Jarvis.' };
    }
    if (daten.einsatzbereit === false) {
      return {
        ok: true,
        text: 'Jarvis läuft, hat aber noch kein Gehirn. Trag im Startfenster von Jarvis einen Schlüssel ein.'
      };
    }
    return { ok: true, text: 'Jarvis ist erreichbar und bereit.' };
  } catch (fehler) {
    return { ok: false, fehler: JARVIS_MELDUNG_AUS, nicht_erreichbar: true };
  } finally {
    clearTimeout(uhr);
  }
}

/**
 * Liest die offene Webseite aus. Läuft IN der Seite (chrome.scripting.executeScript)
 * und darf deshalb nichts von außen benutzen: alles, was sie braucht, steht hier drin.
 *
 * Geliefert werden Titel, Adresse, markierter Text und der sichtbare Haupttext -
 * ohne script/style/nav/footer und Verstecktes, auf 15000 Zeichen gekürzt.
 * Mit mitFusszeile=true kommt die Fußzeile getrennt dazu: Impressum, Telefon und
 * Mailadresse stehen fast immer dort, und genau die braucht "Kontakte übernehmen".
 */
function jarvisSeiteAuslesen(grenze, mitFusszeile) {
  const hoechstens = typeof grenze === 'number' && grenze > 0 ? grenze : 15000;
  const AUSLASSEN = 'script,style,noscript,template,nav,footer,svg,canvas,iframe,object,embed,'
    + 'select,option,button,dialog:not([open]),[hidden],[aria-hidden="true"],'
    + '[role="navigation"],[role="contentinfo"]';
  const BLOCK = 'p,div,section,article,main,aside,header,footer,li,dt,dd,tr,td,th,'
    + 'h1,h2,h3,h4,h5,h6,blockquote,pre,address,figcaption,table,ul,ol,form,fieldset,label';
  const sichtbarkeit = new Map();

  function sichtbar(element) {
    if (sichtbarkeit.has(element)) {
      return sichtbarkeit.get(element);
    }
    let ergebnis = true;
    try {
      if (typeof element.checkVisibility === 'function') {
        ergebnis = element.checkVisibility({ checkOpacity: true, checkVisibilityCSS: true });
      } else {
        const stil = getComputedStyle(element);
        ergebnis = stil.display !== 'none' && stil.visibility !== 'hidden'
          && element.getClientRects().length > 0;
      }
    } catch (fehler) {
      ergebnis = true;
    }
    sichtbarkeit.set(element, ergebnis);
    return ergebnis;
  }

  function sammeln(wurzel, ohne, grenzeHier) {
    const zeilen = [];
    let laenge = 0;
    let zeile = '';
    let letzterBlock = null;
    function abschliessen() {
      const sauber = zeile.replace(/\s+/g, ' ').trim();
      zeile = '';
      if (sauber.length > 1 && zeilen[zeilen.length - 1] !== sauber) {
        zeilen.push(sauber);
        laenge += sauber.length + 1;
      }
    }
    if (!wurzel) {
      return { text: '', gekuerzt: false };
    }
    const wanderer = document.createTreeWalker(wurzel, NodeFilter.SHOW_TEXT, {
      acceptNode: function (knoten) {
        const eltern = knoten.parentElement;
        if (!eltern || (ohne && eltern.closest(ohne)) || !sichtbar(eltern)) {
          return NodeFilter.FILTER_REJECT;
        }
        return NodeFilter.FILTER_ACCEPT;
      }
    });
    let knoten = wanderer.nextNode();
    while (knoten && laenge <= grenzeHier) {
      const block = knoten.parentElement.closest(BLOCK) || wurzel;
      if (block !== letzterBlock) {
        abschliessen();
        letzterBlock = block;
      }
      zeile += knoten.nodeValue;
      knoten = wanderer.nextNode();
    }
    abschliessen();
    let text = zeilen.join('\n');
    const gekuerzt = Boolean(knoten) || text.length > grenzeHier;
    if (text.length > grenzeHier) {
      text = text.slice(0, grenzeHier);
    }
    return { text: text, gekuerzt: gekuerzt };
  }

  function auswahlLesen() {
    let text = '';
    try {
      text = String(window.getSelection() || '');
    } catch (fehler) {
      text = '';
    }
    const aktiv = document.activeElement;
    if (!text.trim() && aktiv && typeof aktiv.selectionStart === 'number'
        && (aktiv.tagName === 'TEXTAREA'
          || (aktiv.tagName === 'INPUT' && /^(text|search|url|email|tel)$/i.test(aktiv.type)))) {
      try {
        text = aktiv.value.slice(aktiv.selectionStart, aktiv.selectionEnd);
      } catch (fehler) {
        text = '';
      }
    }
    return text.trim().slice(0, 4000);
  }

  function kontaktlinksLesen() {
    const gefunden = [];
    const links = document.querySelectorAll('a[href^="mailto:" i], a[href^="tel:" i]');
    for (let i = 0; i < links.length && gefunden.length < 20; i += 1) {
      let ziel = (links[i].getAttribute('href') || '').trim();
      try {
        ziel = decodeURIComponent(ziel);
      } catch (fehler) {
        // Kaputt kodiert - dann eben roh.
      }
      ziel = ziel.split('?')[0].slice(0, 200);
      if (ziel.length > 5 && gefunden.indexOf(ziel) < 0) {
        gefunden.push(ziel);
      }
    }
    return gefunden;
  }

  const koerper = document.body || document.documentElement;
  let fusszeile = '';
  if (mitFusszeile) {
    const teile = [];
    const fuesse = document.querySelectorAll('footer, [role="contentinfo"]');
    for (let i = 0; i < fuesse.length && i < 3; i += 1) {
      const stueck = sammeln(fuesse[i], 'script,style,noscript,template,svg,[hidden],[aria-hidden="true"]', 3000);
      if (stueck.text) {
        teile.push(stueck.text);
      }
    }
    fusszeile = teile.join('\n').slice(0, 3000);
  }
  const platz = hoechstens - (fusszeile ? fusszeile.length + 12 : 0);

  // Erst der Hauptbereich der Seite; ist der dürftig, die ganze Seite.
  const haupt = document.querySelector('main, [role="main"], article');
  let inhalt = haupt ? sammeln(haupt, AUSLASSEN, platz) : null;
  if (!inhalt || inhalt.text.length < 500) {
    const ganz = sammeln(koerper, AUSLASSEN, platz);
    if (!inhalt || ganz.text.length > inhalt.text.length) {
      inhalt = ganz;
    }
  }
  let text = inhalt.text;
  if (fusszeile) {
    text = (text ? text + '\n\n' : '') + 'Fußzeile:\n' + fusszeile;
  }
  return {
    ok: true,
    titel: String(document.title || '').trim().slice(0, 300),
    adresse: String(location.href || '').slice(0, 2000),
    auswahl: auswahlLesen(),
    text: text.slice(0, hoechstens),
    gekuerzt: inhalt.gekuerzt,
    kontaktlinks: kontaktlinksLesen()
  };
}

/** Holt den Seiteninhalt eines Tabs. Geht nicht bei Browserseiten (chrome://, Web Store). */
async function jarvisTabLesen(tabId, mitFusszeile) {
  if (typeof tabId !== 'number') {
    return { ok: false, fehler: 'Ich finde keinen offenen Tab.' };
  }
  try {
    const ergebnisse = await chrome.scripting.executeScript({
      target: { tabId: tabId },
      func: jarvisSeiteAuslesen,
      args: [JARVIS_GRENZEN.text, Boolean(mitFusszeile)]
    });
    const ergebnis = ergebnisse && ergebnisse[0] && ergebnisse[0].result;
    if (ergebnis && ergebnis.ok) {
      return ergebnis;
    }
  } catch (fehler) {
    // fällt unten durch
  }
  return {
    ok: false,
    fehler: 'Diese Seite darf die Erweiterung nicht lesen - etwa Browser-Einstellungen, '
      + 'der Web Store oder ein PDF. Öffne eine normale Webseite.'
  };
}

/** Wählt eine deutsche Stimme - bevorzugt Österreich und eine, die ohne Netz spricht. */
function jarvisStimmeWaehlen(stimmen) {
  const deutsch = (stimmen || []).filter(function (stimme) {
    return /^de([-_]|$)/i.test(stimme.lang || '');
  });
  function wert(stimme) {
    let punkte = 0;
    if (/^de[-_]AT/i.test(stimme.lang)) { punkte += 4; }
    if (/^de[-_]DE/i.test(stimme.lang)) { punkte += 2; }
    if (stimme.localService) { punkte += 3; }
    if (stimme.default) { punkte += 1; }
    return punkte;
  }
  deutsch.sort(function (a, b) { return wert(b) - wert(a); });
  return deutsch[0] || null;
}

/** Zerlegt einen Text in vorlesbare Stücke - lange Äußerungen bricht Chrome sonst ab. */
function jarvisVorleseStuecke(text) {
  const sauber = String(text || '')
    .replace(/[*_#`>|]+/g, ' ')
    .replace(/\s+/g, ' ')
    .trim();
  if (!sauber) {
    return [];
  }
  const saetze = sauber.match(/[^.!?;:]+[.!?;:]*\s*/g) || [sauber];
  const stuecke = [];
  let aktuell = '';
  saetze.forEach(function (satz) {
    if ((aktuell + satz).length > 220 && aktuell) {
      stuecke.push(aktuell.trim());
      aktuell = '';
    }
    while (satz.length > 220) {
      stuecke.push(satz.slice(0, 220).trim());
      satz = satz.slice(220);
    }
    aktuell += satz;
  });
  if (aktuell.trim()) {
    stuecke.push(aktuell.trim());
  }
  return stuecke;
}

// Für Prüfungen unter Node: dort gibt es "module", im Browser nicht.
if (typeof module !== 'undefined' && module.exports) {
  module.exports = {
    jarvisAdresseSaeubern, jarvisSchluesselSaeubern, jarvisKoerperBauen, jarvisAntwortDeuten,
    jarvisSenden, jarvisVerbindungTesten, jarvisStimmeWaehlen, jarvisVorleseStuecke,
    jarvisSeiteAuslesen, JARVIS_MELDUNG_AUS, JARVIS_GRENZEN
  };
}
