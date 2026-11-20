/*
 * AUTONOMOUS – Weboberfläche (Version 1)
 *
 * Grundsätze:
 * - Alle Werte kommen aus echten Backend-Routen. Keine Demo-Daten, keine erfundenen Zahlen.
 * - Fehlt eine Route (z. B. Produkte/Vertrieb vor dem Ausbau), zeigt der Bereich sichtbar
 *   „noch nicht verfügbar“ statt einer Attrappe.
 * - Texte aus der API werden nur als Text eingefügt (textContent), nie als HTML.
 * - Keine Inline-Skripte und keine Inline-Stile (strenge Content-Security-Policy).
 * - Simuliertes Wallet und reale Finanzen werden nie zusammengerechnet.
 */
(function () {
  'use strict';

  // ===========================================================================
  // DOM-Hilfen
  // ===========================================================================
  const SVG_NS = 'http://www.w3.org/2000/svg';
  const BOOL_EIGENSCHAFTEN = ['checked', 'selected', 'disabled', 'hidden', 'open', 'required', 'multiple'];
  let feldZaehler = 0;

  function h(tag, attrs, ...kinder) {
    const el = document.createElement(tag);
    if (attrs) {
      for (const name of Object.keys(attrs)) {
        const wert = attrs[name];
        if (wert === null || wert === undefined || wert === false) continue;
        if (name.slice(0, 2) === 'on' && typeof wert === 'function') {
          el.addEventListener(name.slice(2), wert);
        } else if (name === 'class') {
          el.className = wert;
        } else if (name === 'value') {
          if (tag === 'textarea') el.defaultValue = String(wert);
          else el.setAttribute('value', String(wert));
          el.value = wert;
        } else if (name === 'checked') {
          el.defaultChecked = Boolean(wert);
          el.checked = Boolean(wert);
        } else if (BOOL_EIGENSCHAFTEN.includes(name)) {
          el[name] = Boolean(wert);
        } else if (name === 'href') {
          const ziel = sichererLink(wert);
          if (ziel) el.setAttribute('href', ziel);
        } else if (name === 'style' || name === 'innerHTML') {
          // bewusst nicht unterstützt: CSP und Schutz vor eingeschleustem HTML
        } else {
          el.setAttribute(name, wert === true ? '' : String(wert));
        }
      }
    }
    kinder.forEach(k => anhaengen(el, k));
    return el;
  }

  function anhaengen(el, kind) {
    if (kind === null || kind === undefined || kind === false || kind === true) return;
    if (Array.isArray(kind)) { kind.forEach(k => anhaengen(el, k)); return; }
    el.appendChild(kind instanceof Node ? kind : document.createTextNode(String(kind)));
  }

  /** Inhalt eines Elements ersetzen – nimmt auch (verschachtelte) Listen von Elementen an. */
  function ersetze(el, inhalt) {
    el.replaceChildren();
    anhaengen(el, inhalt);
  }

  /** Nur sichere Ziele: Sprungmarken, Pfade dieser Seite oder externe https-Adressen. */
  function sichererLink(url) {
    const s = String(url || '').trim();
    if (/^#[\w-]*$/.test(s)) return s;
    if (/^\/(?!\/)[^\s"'<>\\]*$/.test(s)) return s;
    if (/^https:\/\/[^\s"'<>\\]+$/i.test(s)) return s;
    return null;
  }

  const enc = encodeURIComponent;

  // Eigene, einfache Symbole (24×24, nur Linien)
  const ICONS = {
    dashboard: [['path', 'M4 4h7v7H4zM13 4h7v4h-7zM13 10h7v10h-7zM4 13h7v7H4z']],
    ceo: [['path', 'M5 21V4'], ['path', 'M5 4h11l-2.5 4L16 12H5']],
    agenten: [['circle', 9, 8, 3.2], ['path', 'M3 20c0-3.3 2.7-6 6-6s6 2.7 6 6'], ['path', 'M16 5.2a3 3 0 0 1 0 5.6'], ['path', 'M18 14.4c1.8.8 3 2.6 3 4.6']],
    wallet: [['path', 'M4 7h14a2 2 0 0 1 2 2v9a2 2 0 0 1-2 2H5a1 1 0 0 1-1-1z'], ['path', 'M4 7l11-3v3'], ['path', 'M16 13.5h2']],
    finanzen: [['path', 'M4 20V11'], ['path', 'M10 20V5'], ['path', 'M16 20v-6'], ['path', 'M3 20h18']],
    produkte: [['path', 'M12 3l8 4.5v9L12 21l-8-4.5v-9z'], ['path', 'M4 7.5l8 4.5 8-4.5'], ['path', 'M12 12v9']],
    vertrieb: [['path', 'M4 10v4h3l6 4V6l-6 4z'], ['path', 'M16.5 9a4 4 0 0 1 0 6'], ['path', 'M19 6.5a8 8 0 0 1 0 11']],
    aufgaben: [['path', 'M10 6h10M10 12h10M10 18h10'], ['path', 'M4 6l1.2 1.2L7.5 5M4 12l1.2 1.2L7.5 11M4 18l1.2 1.2L7.5 17']],
    einstellungen: [['path', 'M4 7h9M17 7h3M4 17h3M11 17h9'], ['circle', 15, 7, 2], ['circle', 9, 17, 2]],
    mehr: [['circle', 5, 12, 1.5], ['circle', 12, 12, 1.5], ['circle', 19, 12, 1.5]],
  };

  function icon(name) {
    const svg = document.createElementNS(SVG_NS, 'svg');
    svg.setAttribute('viewBox', '0 0 24 24');
    svg.setAttribute('class', 'icon');
    svg.setAttribute('aria-hidden', 'true');
    svg.setAttribute('focusable', 'false');
    for (const teil of ICONS[name] || []) {
      const el = document.createElementNS(SVG_NS, teil[0]);
      if (teil[0] === 'path') {
        el.setAttribute('d', teil[1]);
      } else {
        el.setAttribute('cx', teil[1]);
        el.setAttribute('cy', teil[2]);
        el.setAttribute('r', teil[3]);
      }
      svg.appendChild(el);
    }
    return svg;
  }

  // ===========================================================================
  // Formatierung und Texte
  // ===========================================================================
  const EUR = new Intl.NumberFormat('de-DE', { style: 'currency', currency: 'EUR' });

  function euro(cent) {
    return typeof cent === 'number' && isFinite(cent) ? EUR.format(cent / 100) : '—';
  }
  function zahl(n) {
    return typeof n === 'number' && isFinite(n) ? n.toLocaleString('de-DE') : '—';
  }
  function zeitText(iso) {
    if (!iso) return '—';
    const d = new Date(iso);
    return isNaN(d.getTime()) ? String(iso) : d.toLocaleString('de-DE', { dateStyle: 'short', timeStyle: 'short' });
  }
  function tagText(iso) {
    if (!iso) return '—';
    const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(String(iso));
    return m ? m[3] + '.' + m[2] + '.' + m[1] : String(iso);
  }
  function heuteIso() {
    const d = new Date();
    d.setMinutes(d.getMinutes() - d.getTimezoneOffset());
    return d.toISOString().slice(0, 10);
  }
  function dauerText(sek) {
    if (typeof sek !== 'number' || !isFinite(sek)) return '—';
    if (sek < 60) return sek + ' Sek.';
    const min = Math.floor(sek / 60);
    if (min < 60) return min + ' Min.';
    const std = Math.floor(min / 60);
    if (std < 48) return std + ' Std. ' + (min % 60) + ' Min.';
    return Math.floor(std / 24) + ' Tage';
  }
  function sicherungText(datei) {
    const m = /(\d{4})(\d{2})(\d{2})-(\d{2})(\d{2})(\d{2})/.exec(datei || '');
    return m ? m[3] + '.' + m[2] + '.' + m[1] + ', ' + m[4] + ':' + m[5] + ' Uhr' : (datei || '—');
  }

  function sicherungKurz(datei) {
    const m = /(\d{4})(\d{2})(\d{2})-(\d{2})(\d{2})/.exec(datei || '');
    if (!m) return datei || '—';
    const tagDatum = new Date(Number(m[1]), Number(m[2]) - 1, Number(m[3]));
    const heute = new Date();
    heute.setHours(0, 0, 0, 0);
    const abstand = Math.round((heute - tagDatum) / 86400000);
    if (abstand === 0) return 'heute, ' + m[4] + ':' + m[5];
    if (abstand === 1) return 'gestern, ' + m[4] + ':' + m[5];
    return m[3] + '.' + m[2] + '.' + m[1];
  }

  const AUFGABEN_STATUS = {
    geplant: 'Geplant', bereit: 'Bereit', laufend: 'Läuft', wartet_auf_freigabe: 'Wartet auf Freigabe',
    abgeschlossen: 'Abgeschlossen', fehlgeschlagen: 'Fehlgeschlagen', abgebrochen: 'Abgebrochen',
  };
  const STATUS_REIHE = ['geplant', 'bereit', 'laufend', 'wartet_auf_freigabe', 'abgeschlossen', 'fehlgeschlagen', 'abgebrochen'];
  const ENDSTATUS = ['abgeschlossen', 'fehlgeschlagen', 'abgebrochen'];
  const STATUS_TON = {
    geplant: 'grau', bereit: 'akzent', laufend: 'blau', wartet_auf_freigabe: 'warn',
    abgeschlossen: 'ok', fehlgeschlagen: 'fehler', abgebrochen: 'grau',
  };
  const FREIGABE_STATUS = {
    offen: 'Offen', erteilt: 'Erlaubt (noch nicht ausgeführt)', abgelehnt: 'Abgelehnt (endgültig)', verbraucht: 'Erlaubt und verwendet',
  };
  const FREIGABE_TON = { offen: 'warn', erteilt: 'akzent', abgelehnt: 'fehler', verbraucht: 'ok' };
  const KLASSE_TEXT = { auto: 'Automatisch erlaubt', freigabe: 'Nur mit eurer Freigabe', verboten: 'Verboten' };
  const KLASSE_TON = { auto: 'ok', freigabe: 'warn', verboten: 'fehler' };
  const WALLET_ART = {
    startwert: 'Startwert', einnahme: 'Einnahme (simuliert)', ausgabe: 'Ausgabe', reservierung: 'Reservierung',
    reservierung_aufloesen: 'Reservierung aufgelöst', gebuehr: 'Gebühr', gegenbuchung: 'Gegenbuchung',
  };
  const WALLET_BUCHUNGSARTEN = [
    ['ausgabe', 'Ausgabe'], ['einnahme', 'Einnahme (simuliert)'], ['reservierung', 'Reservierung'],
    ['reservierung_aufloesen', 'Reservierung auflösen'], ['gebuehr', 'Gebühr'],
  ];
  const REAL_ART = { einnahme: 'Einnahme', ausgabe: 'Ausgabe', gegenbuchung: 'Gegenbuchung' };
  const FORDERUNG_STATUS = { offen: 'offen', bezahlt: 'bezahlt', storniert: 'storniert' };
  const GEDAECHTNIS_ART = {
    fakt: 'Fakt (bestätigt)', entscheidung: 'Entscheidung', hypothese: 'Hypothese (ungeprüft)', vorschlag: 'Vorschlag (automatisch, ungeprüft)',
  };
  const GEDAECHTNIS_TON = { fakt: 'ok', entscheidung: 'akzent', hypothese: 'warn', vorschlag: 'grau' };
  const PRIO_OPTIONEN = [['1', '1 – sehr hoch'], ['2', '2 – hoch'], ['3', '3 – normal'], ['4', '4 – niedrig'], ['5', '5 – sehr niedrig']];
  const ZIEL_STATUS = { aktiv: 'aktiv', erreicht: 'erreicht', verworfen: 'verworfen' };
  const ZIEL_TON = { aktiv: 'akzent', erreicht: 'ok', verworfen: 'grau' };
  const KONTAKT_STATUS = {
    neu: 'Neu', kontaktiert: 'Kontaktiert', interessiert: 'Interessiert', angebot: 'Angebot', gewonnen: 'Gewonnen', verloren: 'Verloren',
  };
  const KONTAKT_TON = { neu: 'grau', kontaktiert: 'blau', interessiert: 'akzent', angebot: 'warn', gewonnen: 'ok', verloren: 'grau' };
  const ANGEBOT_STATUS = {
    entwurf: 'Entwurf', geprueft: 'Geprüft', versendet: 'Versendet', angenommen: 'Angenommen', abgelehnt: 'Abgelehnt',
  };
  const ANGEBOT_TON = { entwurf: 'grau', geprueft: 'akzent', versendet: 'blau', angenommen: 'ok', abgelehnt: 'fehler' };
  const PRODUKT_STATUS = {
    entwurf: 'Entwurf', qualitaet_ok: 'Qualität geprüft', qualitaet_mangel: 'Mängel gefunden', beispiel: 'Beispiel',
  };
  const PRODUKT_TON = { entwurf: 'grau', qualitaet_ok: 'ok', qualitaet_mangel: 'fehler', beispiel: 'akzent' };
  const EBENEN = [['', 'Alle Ebenen'], ['info', 'Info'], ['warnung', 'Warnung'], ['fehler', 'Fehler'], ['kritisch', 'Kritisch'], ['audit', 'Audit (Prüfspur)']];
  const EBENE_TON = { info: 'grau', warnung: 'warn', fehler: 'fehler', kritisch: 'fehler', audit: 'akzent' };
  const CEO_KNOPF = { tagesplan: 'Tagesplan erstellen', kennzahlen: 'Kennzahlen berechnen', chancen_bewerten: 'Geschäftschancen bewerten' };

  const SCHLUESSEL_TEXT = {
    einnahmen_verifiziert: 'Einnahmen (verifiziert, REAL)',
    offene_forderungen: 'Offene Forderungen (REAL, noch kein Geld)',
    wallet_simulation: 'Wallet (SIMULATION)',
    erfolgsquote_prozent: 'Erfolgsquote in %',
    kontakte_nach_status: 'Kontakte nach Status',
    angebote_nach_status: 'Angebote nach Status',
    preis_vorschlag_eur: 'Preisvorschlag (€)',
    feld_id: 'Feld',
    begruendung: 'Begründung',
    hinweis: 'Hinweis',
    quelle: 'Quelle',
    quellen: 'Quellen',
    wartet_auf_freigabe: 'Wartet auf Freigabe',
    naechster_schritt: 'Nächster Schritt',
    erloes_je_stunde: 'Erlös je Stunde',
    lohnt_sich: 'Lohnt sich',
    saldo_real_cent: 'Saldo real (Cent)',
    erwartet_aus_forderungen_cent: 'Erwartet aus Forderungen (Cent)',
  };
  function schluesselText(k) {
    if (SCHLUESSEL_TEXT[k]) return SCHLUESSEL_TEXT[k];
    const t = String(k).replace(/_/g, ' ');
    return t.charAt(0).toUpperCase() + t.slice(1);
  }

  // ===========================================================================
  // Schnittstelle zum Server
  // ===========================================================================
  class ApiFehler extends Error {
    constructor(status, meldung) {
      super(meldung);
      this.status = status;
      this.meldung = meldung;
    }
  }

  async function anfrage(methode, pfad, daten) {
    const optionen = { method: methode, credentials: 'same-origin', cache: 'no-store', headers: { Accept: 'application/json' } };
    if (methode !== 'GET') {
      optionen.headers['Content-Type'] = 'application/json';
      optionen.body = JSON.stringify(daten || {});
    }
    let antwort;
    try {
      antwort = await fetch(pfad, optionen);
    } catch (e) {
      setzePille('fehler', 'nicht erreichbar');
      throw new ApiFehler(0, 'Server nicht erreichbar – läuft AUTONOMOUS noch?');
    }
    let inhalt = null;
    try { inhalt = await antwort.json(); } catch (e) { inhalt = null; }
    if (antwort.status === 401) {
      zeigeAnmeldung();
      throw new ApiFehler(401, 'Nicht angemeldet');
    }
    if (!antwort.ok) {
      throw new ApiFehler(antwort.status, (inhalt && inhalt.fehler) || ('Fehler ' + antwort.status));
    }
    return inhalt || {};
  }

  const API = {
    get: pfad => anfrage('GET', pfad),
    post: (pfad, daten) => anfrage('POST', pfad, daten),
  };

  /** Eine Route, die (noch) nicht existiert, meldet der Server mit 404 „Nicht gefunden“ oder 405. */
  function istFehlendeRoute(f) {
    return !!f && (f.status === 405 || (f.status === 404 && f.meldung === 'Nicht gefunden'));
  }

  async function optional(pfad) {
    try {
      return await API.get(pfad);
    } catch (f) {
      if (istFehlendeRoute(f)) return { fehlt: true };
      throw f;
    }
  }

  function fehlerText(f) {
    if (!f) return 'Unbekannter Fehler';
    if (istFehlendeRoute(f)) return 'Diese Funktion ist noch nicht verfügbar.';
    return f.meldung || f.message || String(f);
  }

  /** Wandelt JSON-Text aus der Datenbank (z. B. dateien='[...]') in Werte um. */
  function alsWert(x) {
    if (typeof x === 'string' && /^\s*[[{]/.test(x)) {
      try { return JSON.parse(x); } catch (e) { return x; }
    }
    return x;
  }

  // ===========================================================================
  // Zustand
  // ===========================================================================
  const zustand = {
    bereich: null,
    renderNr: 0,
    angemeldet: true,
    agenten: [],
    agentenNamen: {},
    katalog: {},
    filter: { status: '', rolle: '' },
    protokollEbene: '',
    gedaechtnisArt: '',
  };

  function merkeAgenten(liste) {
    zustand.agenten = Array.isArray(liste) ? liste : [];
    zustand.agentenNamen = {};
    zustand.agenten.forEach(a => { zustand.agentenNamen[a.rolle] = a.name; });
  }
  /** Rollenliste nachladen, falls der Start sie nicht holen konnte. */
  async function agentenSicher() {
    if (zustand.agenten.length) return;
    const ag = await API.get('/api/agenten');
    merkeAgenten((ag.agenten || []).filter(a => a.rolle !== 'supervisor'));
  }
  function agentName(rolle) {
    return zustand.agentenNamen[rolle] || rolle || '—';
  }
  function akteurName(a) {
    return { eigentuemer: 'Eigentümer', system: 'System', orchestrator: 'Orchestrator', supervisor: 'Supervisor' }[a] || agentName(a);
  }
  function aktionText(aktion) {
    const k = zustand.katalog[aktion];
    return k ? k.beschreibung : aktion;
  }

  // ===========================================================================
  // Bausteine
  // ===========================================================================
  function meldung(text, art) {
    const box = document.getElementById('meldungen');
    const el = h('div', { class: 'meldung ' + (art || 'info'), role: art === 'fehler' ? 'alert' : 'status' }, text);
    box.appendChild(el);
    setTimeout(() => el.remove(), art === 'fehler' ? 9000 : 5500);
    while (box.children.length > 4) box.firstChild.remove();
  }

  function karte(titel, ...inhalt) {
    return h('section', { class: 'karte' }, titel ? h('h2', null, titel) : null, inhalt);
  }
  function kachel(titel, wert, ton, zusatz, pruef, extra) {
    return h('div', { class: 'kachel' + (ton ? ' ton-' + ton : '') },
      h('div', { class: 'kachel-titel' }, titel),
      h('div', { class: 'kachel-wert', 'data-pruef': pruef || null }, wert),
      extra || null,
      zusatz ? h('div', { class: 'kachel-zusatz' }, zusatz) : null);
  }
  function tag(text, ton) {
    return h('span', { class: 'tag' + (ton ? ' ' + ton : '') }, text);
  }
  function kv(paare) {
    const dl = h('dl', { class: 'kv' });
    for (const paar of paare) {
      if (!paar) continue;
      const wert = paar[1];
      if (wert === null || wert === undefined || wert === '') continue;
      dl.append(h('dt', null, paar[0]), h('dd', null, wert instanceof Node ? wert : String(wert)));
    }
    return dl;
  }
  function leer(text) {
    return h('p', { class: 'leer-hinweis' }, text);
  }
  function hinweis(text, ton) {
    return h('div', { class: 'hinweisbox' + (ton ? ' ' + ton : '') }, text);
  }
  function nichtVerfuegbar(titel, text) {
    return h('section', { class: 'karte nicht-verfuegbar', 'data-pruef': 'nicht-verfuegbar' },
      h('h2', null, titel, tag('noch nicht verfügbar', 'grau')),
      h('p', null, text));
  }
  function aufklapp(titel, schluessel, offen, ...inhalt) {
    return h('details', { class: 'aufklapp', 'data-schluessel': schluessel, open: !!offen }, h('summary', null, titel), inhalt);
  }
  function statusChips(zahlen, texte, toene) {
    const eintraege = Object.entries(zahlen || {}).filter(e => typeof e[1] === 'number');
    if (!eintraege.length) return leer('Noch nichts gezählt.');
    const reihe = (texte === AUFGABEN_STATUS || !texte) ? STATUS_REIHE : Object.keys(texte);
    eintraege.sort((a, b) => {
      const ia = reihe.indexOf(a[0]); const ib = reihe.indexOf(b[0]);
      return (ia < 0 ? 99 : ia) - (ib < 0 ? 99 : ib);
    });
    return h('div', { class: 'chips' }, eintraege.map(([k, n]) =>
      h('span', { class: 'chip' }, tag((texte || AUFGABEN_STATUS)[k] || k, (toene || STATUS_TON)[k]), h('strong', null, zahl(n)))));
  }
  function aufgabenStatusTag(s) {
    return tag(AUFGABEN_STATUS[s] || s, STATUS_TON[s]);
  }

  /** Beliebige JSON-Werte sicher und lesbar darstellen. */
  function wertAnzeige(v, tiefe) {
    tiefe = tiefe || 0;
    v = alsWert(v);
    if (v === null || v === undefined || v === '') return h('span', { class: 'leer' }, '—');
    if (typeof v === 'boolean') return tag(v ? 'ja' : 'nein', v ? 'ok' : 'fehler');
    if (typeof v === 'number') return document.createTextNode(v.toLocaleString('de-DE'));
    if (typeof v === 'string') {
      if (/^https:\/\/[^\s"'<>\\]+$/i.test(v)) {
        return h('a', { href: v, target: '_blank', rel: 'noopener noreferrer' }, v);
      }
      return h('span', { class: 'text' }, v);
    }
    if (tiefe > 4) return h('pre', { class: 'json' }, JSON.stringify(v, null, 2));
    if (Array.isArray(v)) {
      if (!v.length) return h('span', { class: 'leer' }, '—');
      return h('ul', { class: 'werteliste' },
        v.slice(0, 100).map(x => h('li', null, wertAnzeige(x, tiefe + 1))),
        v.length > 100 ? h('li', null, '… und ' + (v.length - 100) + ' weitere') : null);
    }
    const eintraege = Object.entries(v);
    if (!eintraege.length) return h('span', { class: 'leer' }, '—');
    const dl = h('dl', { class: 'kv' });
    eintraege.forEach(([k, w]) => dl.append(h('dt', null, schluesselText(k)), h('dd', null, wertAnzeige(w, tiefe + 1))));
    return dl;
  }

  // ---- Formulare --------------------------------------------------------------
  function feld(beschriftung, steuer, hilfe) {
    if (!steuer.id) steuer.id = 'feld-' + (++feldZaehler);
    let hilfeEl = null;
    if (hilfe) {
      hilfeEl = h('div', { class: 'hilfe', id: steuer.id + '-hilfe' }, hilfe);
      steuer.setAttribute('aria-describedby', hilfeEl.id);
    }
    return h('div', { class: 'feld' }, h('label', { for: steuer.id }, beschriftung), steuer, hilfeEl);
  }
  function eingabe(name, attrs) {
    return h('input', Object.assign({ name: name, type: 'text', autocomplete: 'off' }, attrs || {}));
  }
  function betragFeld(name, attrs) {
    return eingabe(name, Object.assign({ inputmode: 'decimal', placeholder: 'z. B. 12,50', maxlength: 20 }, attrs || {}));
  }
  function zahlFeld(name, attrs) {
    return eingabe(name, Object.assign({ type: 'number', inputmode: 'numeric', step: '1' }, attrs || {}));
  }
  function auswahl(name, optionen, wert, attrs) {
    const s = h('select', Object.assign({ name: name }, attrs || {}),
      optionen.map(o => h('option', { value: o[0] }, o[1])));
    if (wert !== undefined && wert !== null) {
      s.value = String(wert);
      Array.from(s.options).forEach(o => { o.defaultSelected = o.value === String(wert); });
    }
    return s;
  }
  function textfeld(name, attrs) {
    return h('textarea', Object.assign({ name: name, rows: 3 }, attrs || {}));
  }
  function absendeKnopf(text, attrs) {
    return h('button', Object.assign({ type: 'submit', class: 'knopf' }, attrs || {}), text);
  }

  function formular(attrs, inhalt, aktion) {
    const form = h('form', Object.assign({ class: 'formular' }, attrs || {}), inhalt);
    form.addEventListener('submit', async (e) => {
      e.preventDefault();
      const knopf = form.querySelector('button[type="submit"]');
      if (knopf) knopf.disabled = true;
      try {
        await aktion(formWerte(form), form);
      } catch (f) {
        meldung(fehlerText(f), 'fehler');
      } finally {
        if (knopf) knopf.disabled = false;
      }
    });
    return form;
  }

  function formWerte(form) {
    const werte = {};
    for (const el of form.elements) {
      if (!el.name || el.disabled) continue;
      if (el.type === 'checkbox') werte[el.name] = el.checked;
      else if (el.type === 'radio') { if (el.checked) werte[el.name] = el.value; }
      else werte[el.name] = typeof el.value === 'string' ? el.value.trim() : el.value;
    }
    return werte;
  }

  function ohneLeere(o) {
    const r = {};
    Object.keys(o).forEach(k => {
      const v = o[k];
      if (v === '' || v === null || v === undefined) return;
      if (Array.isArray(v) && !v.length) return;
      r[k] = v;
    });
    return r;
  }

  /** Euro-Eingaben wie „12,50“, „1.250,00“ oder „12.5“ in eine eindeutige Form „12.50“ bringen. */
  function betragNormal(text) {
    const t = String(text || '').replace(/€/g, '').replace(/\s/g, '');
    if (/^\d{1,3}(\.\d{3})+(,\d{1,2})?$/.test(t)) return t.replace(/\./g, '').replace(',', '.');
    if (/^\d+(,\d{1,2})?$/.test(t)) return t.replace(',', '.');
    if (/^\d+\.\d{1,2}$/.test(t)) return t;
    return null;
  }
  function betragPflicht(text, name) {
    const n = betragNormal(text);
    if (n === null) throw new ApiFehler(0, (name || 'Betrag') + ': bitte als Euro-Betrag eingeben, z. B. 12,50.');
    return n;
  }
  function zeilen(text) {
    return String(text || '').split(/\r?\n/).map(s => s.trim()).filter(Boolean);
  }

  function aktionsKnopf(text, klasse, aktion, attrs) {
    const k = h('button', Object.assign({ type: 'button', class: 'knopf ' + (klasse || '') }, attrs || {}), text);
    k.addEventListener('click', async () => {
      k.disabled = true;
      try { await aktion(); } catch (f) { meldung(fehlerText(f), 'fehler'); } finally { k.disabled = false; }
    });
    return k;
  }

  /** Knopf mit zweitem Tippen zur Bestätigung (für endgültige oder folgenreiche Schritte). */
  function sicherheitsKnopf(text, frage, klasse, aktion, attrs) {
    const k = h('button', Object.assign({ type: 'button', class: 'knopf ' + (klasse || '') }, attrs || {}), text);
    let scharf = false;
    let uhr = null;
    const entschaerfen = () => {
      scharf = false;
      k.textContent = text;
      k.classList.remove('bestaetigen');
    };
    k.addEventListener('click', async () => {
      if (!scharf) {
        scharf = true;
        k.textContent = frage;
        k.classList.add('bestaetigen');
        uhr = setTimeout(entschaerfen, 5000);
        return;
      }
      clearTimeout(uhr);
      k.disabled = true;
      try {
        await aktion();
      } catch (f) {
        meldung(fehlerText(f), 'fehler');
      } finally {
        k.disabled = false;
        entschaerfen();
      }
    });
    return k;
  }

  function umschaltBereich(knopfText, knopfKlasse, inhaltBauen) {
    const bereich = h('div', { class: 'inline-form', hidden: true });
    const auf = h('button', { type: 'button', class: 'knopf ' + (knopfKlasse || 'zweit klein'), 'aria-expanded': 'false' }, knopfText);
    const zu = () => { bereich.hidden = true; auf.hidden = false; auf.setAttribute('aria-expanded', 'false'); auf.focus(); };
    auf.addEventListener('click', () => {
      bereich.replaceChildren(inhaltBauen(zu));
      bereich.hidden = false;
      auf.hidden = true;
      auf.setAttribute('aria-expanded', 'true');
      const erstes = bereich.querySelector('input, select, textarea');
      if (erstes) erstes.focus();
    });
    return [auf, bereich];
  }
  function abbrechenKnopf(zu) {
    return h('button', { type: 'button', class: 'knopf zweit', onclick: zu }, 'Abbrechen');
  }

  function auftragGemeldet(r, wer) {
    if (r && r.aufgabe_id) {
      meldung('Auftrag an ' + wer + ' übergeben (Aufgabe ' + r.aufgabe_id + '). Fortschritt unter „Aufgaben“.', 'ok');
      spaeterNeuLaden(1500);
    } else {
      meldung('Gespeichert.', 'ok');
      neuLaden();
    }
  }

  // ---- Freigaben ---------------------------------------------------------------
  function freigabeKarte(f, mitNotiz) {
    let nutzlast = alsWert(f.nutzlast);
    if (typeof nutzlast === 'string') nutzlast = nutzlast ? { inhalt: nutzlast } : null;
    const notiz = mitNotiz ? eingabe('notiz', { maxlength: 500, placeholder: 'z. B. Grund für die Entscheidung' }) : null;
    const entscheiden = async (ja) => {
      await API.post('/api/freigaben/' + enc(f.id) + '/entscheiden',
        { entscheidung: ja ? 'ja' : 'nein', notiz: notiz ? notiz.value.trim() : '' });
      meldung(ja ? 'Erlaubt – gilt für genau eine Ausführung.' : 'Abgelehnt – diese Aktion bleibt dauerhaft gesperrt.', 'ok');
      neuLaden();
    };
    const katalog = zustand.katalog[f.aktion];
    return h('article', { class: 'freigabe', 'data-pruef': 'freigabe' },
      h('div', { class: 'freigabe-kopf' }, tag('Freigabe nötig', 'warn'), h('strong', null, aktionText(f.aktion))),
      kv([
        ['Aktion', h('code', null, f.aktion)],
        ['Ziel', f.ziel],
        ['Mögliche Kosten', f.kosten_cent ? euro(f.kosten_cent) : 'keine angegeben'],
        ['Datenumfang', f.datenumfang],
        ['Folgen', f.folgen],
        ['Angefragt von', agentName(f.agent)],
        ['Angefragt am', zeitText(f.zeit)],
        ['Risikoklasse', KLASSE_TEXT[f.risiko] || (katalog ? KLASSE_TEXT[katalog.klasse] : f.risiko)],
        f.aufgabe_id ? ['Zu Aufgabe', f.aufgabe_id] : null,
      ]),
      nutzlast && Object.keys(nutzlast).length
        ? h('details', { class: 'aufklapp klein', 'data-schluessel': 'nutzlast-' + f.id }, h('summary', null, 'Genauer Inhalt ansehen'), wertAnzeige(nutzlast))
        : null,
      notiz ? feld('Notiz (optional)', notiz) : null,
      h('div', { class: 'knopfreihe' },
        sicherheitsKnopf('Ja, einmalig erlauben', 'Wirklich erlauben? Nochmal tippen', 'ok', () => entscheiden(true), { 'data-pruef': 'freigabe-ja' }),
        sicherheitsKnopf('Nein', 'Endgültig ablehnen? Nochmal tippen', 'gefahr', () => entscheiden(false), { 'data-pruef': 'freigabe-nein' })),
      h('p', { class: 'hilfe' }, 'Ein Ja gilt nur für genau diese eine Ausführung. Ein Nein ist endgültig: dieselbe Aktion wird danach automatisch blockiert – auch wenn ein anderer Agent fragt.'));
  }

  // ---- Aufgaben ------------------------------------------------------------------
  function aufgabeZeile(a, kompakt) {
    const zeile = h('li', { class: 'eintrag' },
      h('div', { class: 'eintrag-kopf' }, h('span', { class: 'eintrag-titel' }, a.titel), aufgabenStatusTag(a.status)),
      h('div', { class: 'meta' },
        h('span', null, agentName(a.verantwortlich)),
        h('span', null, 'Typ: ' + a.typ),
        h('span', null, 'Priorität ' + a.prioritaet),
        h('span', null, 'angelegt ' + zeitText(a.erstellt)),
        a.versuche ? h('span', null, 'Versuch ' + a.versuche + ' von ' + a.max_versuche) : null,
        a.naechster_versuch && a.status === 'bereit' ? h('span', null, 'nächster Versuch ' + zeitText(a.naechster_versuch)) : null),
      a.fehler && a.status !== 'abgeschlossen' ? h('p', { class: 'fehlertext' }, a.fehler) : null);
    if (kompakt) return zeile;

    const details = h('div', { class: 'details-inhalt', hidden: true });
    const detailKnopf = h('button', { type: 'button', class: 'knopf zweit klein', 'aria-expanded': 'false' }, 'Details');
    detailKnopf.addEventListener('click', async () => {
      if (!details.hidden) {
        details.hidden = true;
        detailKnopf.setAttribute('aria-expanded', 'false');
        detailKnopf.textContent = 'Details';
        return;
      }
      detailKnopf.disabled = true;
      try {
        const voll = await API.get('/api/aufgaben/' + enc(a.id));
        ersetze(details, aufgabeDetails(voll));
        details.hidden = false;
        detailKnopf.setAttribute('aria-expanded', 'true');
        detailKnopf.textContent = 'Details ausblenden';
      } catch (f) {
        meldung(fehlerText(f), 'fehler');
      } finally {
        detailKnopf.disabled = false;
      }
    });
    const knoepfe = h('div', { class: 'knopfreihe' }, detailKnopf);
    if (a.status === 'geplant') {
      knoepfe.append(aktionsKnopf('Starten', 'zweit klein', async () => {
        await API.post('/api/aufgaben/' + enc(a.id) + '/freigeben');
        meldung('Aufgabe ist bereit und wird abgearbeitet.', 'ok');
        neuLaden();
      }));
    }
    if (a.status === 'fehlgeschlagen') {
      knoepfe.append(aktionsKnopf('Neu anstoßen', 'zweit klein', async () => {
        await API.post('/api/aufgaben/' + enc(a.id) + '/freigeben');
        meldung('Aufgabe neu angestoßen.', 'ok');
        neuLaden();
      }));
    }
    if (!ENDSTATUS.includes(a.status)) {
      knoepfe.append(sicherheitsKnopf('Abbrechen', 'Wirklich abbrechen?', 'gefahr klein', async () => {
        await API.post('/api/aufgaben/' + enc(a.id) + '/abbrechen', { grund: 'in der Oberfläche abgebrochen' });
        meldung('Aufgabe abgebrochen.', 'ok');
        neuLaden();
      }));
    }
    zeile.append(knoepfe, details);
    return zeile;
  }

  function aufgabeDetails(a) {
    const ergebnis = alsWert(a.ergebnis);
    return [
      kv([
        ['ID', a.id],
        ['Angelegt von', akteurName(a.ersteller)],
        ['Gestartet', a.gestartet ? zeitText(a.gestartet) : null],
        ['Beendet', a.beendet ? zeitText(a.beendet) : null],
        ['Übergeordnete Aufgabe', a.eltern_id],
        ['Freigabe', a.freigabe_id],
      ]),
      h('h4', null, 'Eingabe'),
      wertAnzeige(a.eingabe),
      h('h4', null, 'Ergebnis'),
      ergebnis ? wertAnzeige(ergebnis) : leer(a.status === 'abgeschlossen' ? 'Kein Ergebnis gespeichert.' : 'Noch kein Ergebnis.'),
      ergebnis ? h('details', { class: 'aufklapp klein' }, h('summary', null, 'Rohdaten (JSON)'), h('pre', { class: 'json' }, JSON.stringify(ergebnis, null, 2))) : null,
      a.fehler ? [h('h4', null, 'Fehler'), h('p', { class: 'fehlertext' }, a.fehler)] : null,
      h('h4', null, 'Verlauf'),
      (a.verlauf || []).length
        ? h('ol', { class: 'verlauf' }, a.verlauf.map(v => h('li', null,
          h('div', null, (v.von_status ? (AUFGABEN_STATUS[v.von_status] || v.von_status) + ' → ' : '') + (AUFGABEN_STATUS[v.nach_status] || v.nach_status)),
          h('div', { class: 'meta' }, zeitText(v.zeit) + ' · ' + akteurName(v.akteur)),
          v.notiz ? h('div', { class: 'hilfe text' }, v.notiz) : null)))
        : leer('Kein Verlauf.'),
    ];
  }

  // ---- Geld ---------------------------------------------------------------------
  function budgetKarte(bereich, budgets) {
    const sim = bereich === 'wallet';
    budgets = budgets || [];
    const liste = budgets.length
      ? h('ul', { class: 'liste' }, budgets.map(b => {
        const verbraucht = b.verbraucht_cent || 0;
        const ueber = typeof b.ueberschritten === 'boolean' ? b.ueberschritten : verbraucht > b.limit_cent;
        const maximum = Math.max(b.limit_cent || 0, 1);
        return h('li', { class: 'eintrag' },
          h('div', { class: 'eintrag-kopf' },
            h('span', { class: 'eintrag-titel' }, b.kategorie === '*' ? 'Alle Kategorien' : b.kategorie),
            h('span', { class: 'chips' }, tag(b.zeitraum === 'monat' ? 'pro Monat' : 'gesamt', 'grau'), ueber ? tag('überschritten', 'fehler') : null)),
          h('div', { class: 'meta' }, euro(verbraucht) + ' von ' + euro(b.limit_cent) + (sim ? ' · SIMULATION' : ' · REAL')),
          h('progress', { max: maximum, value: Math.min(verbraucht, maximum), class: ueber ? 'ueber' : null, 'aria-label': 'Verbrauch des Budgets' }));
      }))
      : leer('Noch keine Budgets festgelegt.');
    const form = formular(null, [
      h('div', { class: 'felder-3' },
        feld('Kategorie', eingabe('kategorie', { required: true, value: '*', maxlength: 60 }), '„*“ steht für alle Kategorien.'),
        feld('Grenze in €', betragFeld('limit', { required: true })),
        feld('Zeitraum', auswahl('zeitraum', [['monat', 'pro Monat'], ['gesamt', 'gesamt']], 'monat'))),
      h('div', { class: 'knopfreihe' }, absendeKnopf('Budget speichern')),
    ], async (w, f) => {
      await API.post('/api/budgets', { bereich: bereich, kategorie: w.kategorie, limit: betragPflicht(w.limit, 'Grenze'), zeitraum: w.zeitraum });
      f.reset();
      meldung('Budget gespeichert.', 'ok');
      neuLaden();
    });
    return karte(sim ? 'Budgets (SIMULATION)' : 'Budgets (REAL)',
      h('p', { class: 'hilfe' }, sim
        ? 'Eine Überschreitung erzeugt eine Warnung. Gesperrt oder abgeschaltet wird dadurch nichts.'
        : 'Zeigt, wie viel von der Grenze schon tatsächlich ausgegeben wurde.'),
      liste,
      aufklapp('Budget festlegen oder ändern', 'budget-' + bereich, false, form));
  }

  function buchungZeile(b, o) {
    const sim = o.sim;
    const betrag = h('span', { class: 'betrag ' + (b.betrag_cent < 0 ? 'minus' : 'plus') }, (b.betrag_cent > 0 ? '+' : '') + euro(b.betrag_cent));
    const zeile = h('li', { class: 'eintrag' },
      h('div', { class: 'eintrag-kopf' },
        h('span', { class: 'eintrag-titel' }, (sim ? WALLET_ART[b.art] : REAL_ART[b.art]) || b.art),
        betrag),
      h('div', { class: 'meta' },
        h('span', null, 'Nr. ' + b.nr),
        h('span', null, sim ? zeitText(b.zeit) : tagText(b.datum)),
        h('span', null, 'Kategorie: ' + b.kategorie),
        b.gegenpartei ? h('span', null, b.gegenpartei) : null,
        sim ? tag('SIMULATION', 'sim') : tag('REAL', 'ok')),
      h('p', { class: 'text' }, b.begruendung),
      !sim && b.art === 'einnahme' ? h('p', { class: 'hilfe' }, 'Zahlungsnachweis: ' + b.zahlungsnachweis + ' · geprüft von ' + b.verifiziert_von) : null,
      b.beleg ? h('p', { class: 'hilfe' }, 'Beleg: ' + b.beleg) : null,
      b.gegenbuchung_zu ? h('p', { class: 'hilfe' }, 'Korrigiert Buchung ' + b.gegenbuchung_zu) : null,
      o.gegengebucht ? h('p', { class: 'hilfe' }, tag('durch Gegenbuchung ausgeglichen', 'grau')) : null);
    if (b.art !== 'gegenbuchung' && !o.gegengebucht) {
      const teile = umschaltBereich('Gegenbuchung', 'zweit klein', zu => formular(null, [
        feld('Begründung der Korrektur', eingabe('begruendung', { required: true, maxlength: 500 })),
        h('div', { class: 'knopfreihe' }, absendeKnopf('Gegenbuchen'), abbrechenKnopf(zu)),
      ], async (w) => {
        await API.post(o.pfad, { begruendung: w.begruendung });
        meldung('Gegenbuchung gespeichert.', 'ok');
        neuLaden();
      }));
      zeile.append(h('div', { class: 'knopfreihe' }, teile));
    }
    return zeile;
  }

  // ===========================================================================
  // Bereich: Dashboard
  // ===========================================================================
  async function ansichtDashboard(z) {
    const d = await API.get('/api/dashboard');
    const s = d.status || {};
    aktualisiereKopfMit(s);
    const freigaben = d.offene_freigaben || [];
    if (freigaben.length) {
      z.append(h('section', { class: 'karte hervorgehoben' },
        h('h2', null, 'Wartet auf eure Entscheidung', tag(String(freigaben.length), 'warn')),
        h('div', { class: 'liste' }, freigaben.map(f => freigabeKarte(f, false)))));
    }

    const orch = s.orchestrator || {};
    const modell = s.modell || {};
    const prozent = typeof s.fortschritt_prozent === 'number' ? s.fortschritt_prozent : 0;
    const betriebOk = s.betrieb === 'laeuft';
    z.append(h('div', { class: 'raster' },
      kachel('Betrieb', betriebOk ? 'läuft' : (s.betrieb || 'unbekannt'), betriebOk ? 'ok' : 'fehler',
        'Datenbank ' + (s.datenbank && s.datenbank.ok ? 'in Ordnung' : 'gestört') + (s.datenbank ? ' · Schema ' + s.datenbank.schema_version : ''), 'betrieb'),
      kachel('Agenten-Arbeiter', orch.laeuft ? 'aktiv' : 'gestoppt', orch.laeuft ? 'ok' : 'warn',
        orch.laeuft ? (orch.beschaeftigt + ' von ' + orch.arbeiter + ' beschäftigt · ' + zahl(orch.bearbeitet_seit_start) + ' seit Start erledigt') : 'Aufgaben werden gerade nicht abgearbeitet.'),
      kachel('Fortschritt', prozent + ' %', '', 'Anteil abgeschlossener Aufgaben (ohne abgebrochene)', null,
        h('progress', { max: 100, value: Math.max(0, Math.min(100, prozent)), 'aria-label': 'Fortschritt' })),
      kachel('Offene Freigaben', zahl(s.offene_freigaben), s.offene_freigaben ? 'warn' : '', s.offene_freigaben ? 'Bitte entscheiden' : 'Nichts offen'),
      kachel('Fehler (24 Std.)', zahl(s.fehler_24h), s.fehler_24h ? 'fehler' : '', 'laut Protokoll'),
      kachel('Letzte Sicherung', s.letzte_sicherung ? sicherungKurz(s.letzte_sicherung) : 'noch keine', s.letzte_sicherung ? '' : 'warn',
        s.letzte_sicherung ? sicherungText(s.letzte_sicherung) + ' · täglich, solange das System läuft' : 'täglich, solange das System läuft'),
      kachel('Modell', (modell.anbieter_info && modell.anbieter_info.name) || modell.anbieter || '—', '',
        modell.verfuegbar ? (zahl(modell.aufrufe_heute) + ' von ' + zahl(modell.limit_tag) + ' Aufrufen heute') : 'Kernfunktionen arbeiten ohne Modell'),
      kachel('Laufzeit', dauerText(s.laufzeit_sekunden), '', 'Version ' + (s.version || '?') + ' · ' + zahl(s.agenten) + ' Agentenrollen')));

    z.append(karte('Aufgaben nach Status', statusChips(s.aufgaben),
      h('div', { class: 'knopfreihe' }, h('a', { href: '#aufgaben', class: 'knopf zweit klein' }, 'Zu den Aufgaben'))));

    const warnungen = (s.warnungen || []).map(t => h('li', { class: 'eintrag' }, h('span', { class: 'text' }, t)));
    const protokoll = (d.warnungen_protokoll || []).slice().sort((a, b) => (b.id || 0) - (a.id || 0)).slice(0, 8);
    z.append(karte('Warnungen',
      warnungen.length || protokoll.length
        ? h('ul', { class: 'liste' }, warnungen, protokoll.map(p => h('li', { class: 'eintrag' },
          h('div', { class: 'eintrag-kopf' }, h('span', { class: 'eintrag-titel' }, p.ereignis), tag(p.ebene, EBENE_TON[p.ebene])),
          h('div', { class: 'meta' }, zeitText(p.zeit) + ' · ' + p.quelle))))
        : leer('Keine Warnungen.')));

    const aktiv = d.aktive_aufgaben || [];
    z.append(karte('Aktive Aufgaben',
      aktiv.length ? h('ul', { class: 'liste' }, aktiv.map(a => aufgabeZeile(a, true))) : leer('Gerade läuft nichts und nichts wartet in der Warteschlange.')));

    // Simulation und Realität getrennt – nie zusammengerechnet
    const w = d.wallet || {};
    const f = d.finanzen || {};
    z.append(h('div', { class: 'raster zwei' },
      h('section', { class: 'karte' },
        h('h2', null, 'Internes Wallet', tag('SIMULATION', 'sim')),
        h('div', { class: 'kachel-wert' }, w.stand || euro(w.stand_cent)),
        h('p', { class: 'hilfe' }, 'Kein echtes Geld. Beeinflusst den Betrieb nicht.'),
        h('a', { href: '#wallet', class: 'knopf zweit klein' }, 'Zum Wallet')),
      h('section', { class: 'karte' },
        h('h2', null, 'Reale Finanzen', tag('REAL', 'ok')),
        kv([
          ['Einnahmen (verifiziert)', euro(f.einnahmen_verifiziert_cent)],
          ['Saldo', f.saldo || euro(f.saldo_cent)],
          ['Offene Forderungen', (f.offene_forderungen || euro(f.offene_forderungen_cent)) + ' (noch kein Geld)'],
        ]),
        h('a', { href: '#finanzen', class: 'knopf zweit klein' }, 'Zu den Finanzen'))));
  }

  // ===========================================================================
  // Bereich: CEO-Zentrale
  // ===========================================================================
  async function ansichtCeo(z) {
    await agentenSicher();
    const [zielDaten, ceo, research, gedaechtnis] = await Promise.all([
      API.get('/api/ziele'), API.get('/api/aufgaben?rolle=ceo'), API.get('/api/aufgaben?rolle=research'), API.get('/api/gedaechtnis'),
    ]);
    const ceoAufgaben = ceo.aufgaben || [];
    const eintraege = gedaechtnis.eintraege || [];
    z.append(h('p', { class: 'einleitung' }, 'Ziele und Entscheidungen legt ihr fest. Der CEO-Agent plant und bewertet nur aus echten Daten – seine Ergebnisse sind Vorschläge.'));
    z.append(ceoAuftraege(ceoAufgaben));
    z.append(zieleKarte(zielDaten.ziele || []));
    z.append(tagesplanKarte(ceoAufgaben));
    z.append(chancenKarte(research.aufgaben || [], ceoAufgaben));
    z.append(kennzahlenKarte(ceoAufgaben));
    z.append(entscheidungenKarte(eintraege.filter(e => e.art === 'entscheidung')));
    z.append(gedaechtnisKarte(eintraege));
  }

  function neuestes(aufgaben, typ) {
    return aufgaben
      .filter(a => a.typ === typ && a.status === 'abgeschlossen' && a.ergebnis)
      .sort((x, y) => String(y.beendet || y.aktualisiert).localeCompare(String(x.beendet || x.aktualisiert)))[0] || null;
  }
  function inArbeit(aufgaben, typ) {
    return aufgaben.some(a => a.typ === typ && !ENDSTATUS.includes(a.status));
  }

  function ceoAuftraege(ceoAufgaben) {
    const ceo = zustand.agenten.find(a => a.rolle === 'ceo');
    if (!ceo) return nichtVerfuegbar('CEO-Agent beauftragen', 'Der CEO-Agent ist nicht registriert.');
    const typen = Object.keys(ceo.aufgabentypen || {}).filter(t => t !== 'auftrag_verteilen');
    return karte('CEO-Agent beauftragen',
      h('div', { class: 'knopfreihe' }, typen.map(t => aktionsKnopf(CEO_KNOPF[t] || ceo.aufgabentypen[t], 'zweit', async () => {
        const r = await API.post('/api/aufgaben', { rolle: 'ceo', typ: t, prioritaet: 2 });
        meldung('Aufgabe angelegt (' + r.id + '). Der CEO-Agent arbeitet sie ab.', 'ok');
        spaeterNeuLaden(1500);
      }, { title: ceo.aufgabentypen[t] }))),
      typen.some(t => inArbeit(ceoAufgaben, t)) ? h('p', { class: 'hilfe' }, 'Mindestens ein Auftrag ist noch in Arbeit.') : null);
  }

  function zieleKarte(ziele) {
    const liste = ziele.length
      ? h('ul', { class: 'liste', 'data-pruef': 'ziele-liste' }, ziele.map(zielZeile))
      : leer('Noch keine Ziele. Legt fest, worauf AUTONOMOUS hinarbeiten soll.');
    const form = formular({ 'data-pruef': 'ziel-formular' }, [
      h('div', { class: 'felder-2' },
        feld('Ziel', eingabe('titel', { required: true, maxlength: 200, placeholder: 'z. B. Erstes Angebot an 5 Betriebe', 'data-pruef': 'ziel-titel' })),
        feld('Priorität', auswahl('prioritaet', PRIO_OPTIONEN, 3))),
      feld('Beschreibung (optional)', textfeld('beschreibung', { maxlength: 2000 })),
      h('div', { class: 'knopfreihe' }, absendeKnopf('Ziel anlegen', { 'data-pruef': 'ziel-absenden' })),
    ], async (w, f) => {
      await API.post('/api/ziele', { titel: w.titel, beschreibung: w.beschreibung, prioritaet: Number(w.prioritaet) });
      f.reset();
      meldung('Ziel angelegt.', 'ok');
      neuLaden();
    });
    return karte('Ziele und Prioritäten', liste,
      h('details', { class: 'aufklapp', 'data-schluessel': 'ziel-neu', open: !ziele.length },
        h('summary', { 'data-pruef': 'ziel-neu-auf' }, 'Neues Ziel anlegen'), form));
  }

  function zielZeile(ziel) {
    const status = async (neu) => {
      await API.post('/api/ziele/' + enc(ziel.id) + '/status', { status: neu });
      meldung('Ziel ist jetzt „' + ZIEL_STATUS[neu] + '“.', 'ok');
      neuLaden();
    };
    return h('li', { class: 'eintrag' },
      h('div', { class: 'eintrag-kopf' }, h('span', { class: 'eintrag-titel' }, ziel.titel),
        h('span', { class: 'chips' }, tag('Priorität ' + ziel.prioritaet, ziel.prioritaet <= 2 ? 'warn' : 'grau'), tag(ZIEL_STATUS[ziel.status] || ziel.status, ZIEL_TON[ziel.status]))),
      ziel.beschreibung ? h('p', { class: 'text' }, ziel.beschreibung) : null,
      h('div', { class: 'meta' }, 'angelegt ' + zeitText(ziel.erstellt)),
      h('div', { class: 'knopfreihe' }, ziel.status === 'aktiv'
        ? [aktionsKnopf('Erreicht', 'zweit klein', () => status('erreicht')), aktionsKnopf('Verwerfen', 'zweit klein', () => status('verworfen'))]
        : aktionsKnopf('Wieder aktiv', 'zweit klein', () => status('aktiv'))));
  }

  function tagesplanKarte(ceoAufgaben) {
    const letzte = neuestes(ceoAufgaben, 'tagesplan');
    const titel = 'Tagesplan';
    if (!letzte) {
      return karte(titel, leer(inArbeit(ceoAufgaben, 'tagesplan') ? 'Der Tagesplan wird gerade erstellt …' : 'Noch kein Tagesplan. Oben „Tagesplan erstellen“ antippen.'));
    }
    const e = alsWert(letzte.ergebnis) || {};
    const punkte = Array.isArray(e.punkte) ? e.punkte : [];
    return karte([titel, tag('Vorschlag', 'grau')],
      h('div', { class: 'meta' }, 'erstellt ' + zeitText(letzte.beendet) + (e.quelle ? ' · ' + e.quelle : '')),
      punkte.length
        ? h('ol', { class: 'punkte' }, punkte.map(p => h('li', null, tag(p.art || '–', p.art === 'Entscheidung' ? 'warn' : p.art === 'Fehler' ? 'fehler' : 'grau'), ' ', p.text)))
        : leer('Nichts offen.'));
  }

  function chancenKarte(researchAufgaben, ceoAufgaben) {
    const letzte = neuestes(researchAufgaben, 'marktbewertung');
    const titel = 'Geschäftschancen (Research-Agent)';
    if (!letzte) {
      const laeuft = inArbeit(researchAufgaben, 'marktbewertung') || inArbeit(ceoAufgaben, 'chancen_bewerten');
      const fehler = researchAufgaben.filter(a => a.typ === 'marktbewertung' && a.status === 'fehlgeschlagen')[0];
      return karte(titel,
        leer(laeuft ? 'Die Bewertung läuft gerade …' : 'Noch keine Bewertung. „Geschäftschancen bewerten“ startet sie.'),
        fehler ? h('p', { class: 'fehlertext' }, 'Letzter Versuch fehlgeschlagen: ' + fehler.fehler) : null);
    }
    const e = alsWert(letzte.ergebnis) || {};
    const empf = e.empfehlung_aus_recherche || {};
    const preis = empf.preis_vorschlag_eur;
    let preisText = null;
    if (preis && typeof preis === 'object' && (preis.min !== undefined || preis.max !== undefined)) {
      preisText = [preis.min, preis.max].filter(x => x !== undefined && x !== null).map(x => zahl(Number(x))).join(' – ') + ' €' + (preis.status ? ' (' + preis.status + ')' : '');
    }
    const rangliste = Array.isArray(e.rangliste) ? e.rangliste : [];
    return karte([titel, tag('Vorschlag', 'grau')],
      h('div', { class: 'meta' }, 'Stand der Recherche: ' + (e.stand || '—') + ' · berechnet ' + zeitText(letzte.beendet)),
      e.einordnung ? hinweis(e.einordnung, 'warn') : null,
      empf.angebot || preisText || empf.begruendung
        ? [h('h3', null, 'Empfehlung der Recherche'), kv([
          ['Angebot', empf.angebot],
          ['Preisvorschlag', preisText || (preis ? wertAnzeige(preis) : null)],
          ['Begründung', empf.begruendung],
        ])]
        : null,
      rangliste.length
        ? [h('h3', null, 'Rangliste nach Gewichtung'), h('ol', { class: 'rangliste' }, rangliste.map(r => h('li', null,
          h('div', { class: 'eintrag-kopf' }, h('span', { class: 'eintrag-titel' }, r.name || r.id),
            h('span', { class: 'chips' }, tag(r.wert === null || r.wert === undefined ? 'ohne Wert' : zahl(r.wert) + ' von 5', 'akzent'), tag('Beleg: ' + (r.belegstatus || 'unbekannt'), r.belegstatus === 'belegt' ? 'ok' : 'warn'))),
          typeof r.wert === 'number' ? h('progress', { max: 5, value: Math.max(0, Math.min(5, r.wert)), 'aria-label': 'Bewertung' }) : null,
          h('div', { class: 'meta' },
            h('span', null, zahl((r.quellen || []).length) + ' Quellen, davon ' + zahl(r.quellen_gut || 0) + ' gut'),
            (r.fehlende_kriterien || []).length ? h('span', null, 'ohne Wert: ' + r.fehlende_kriterien.join(', ')) : null),
          (r.quellen || []).length ? h('details', { class: 'aufklapp klein' }, h('summary', null, 'Quellen ansehen'), wertAnzeige(r.quellen)) : null)))]
        : leer('Die Recherche enthält keine bewerteten Felder.'),
      e.gewichte ? h('details', { class: 'aufklapp klein' }, h('summary', null, 'Gewichtung der Kriterien'), wertAnzeige(e.gewichte)) : null);
  }

  function kennzahlenKarte(ceoAufgaben) {
    const letzte = neuestes(ceoAufgaben, 'kennzahlen');
    if (!letzte) {
      return karte('Kennzahlen', leer(inArbeit(ceoAufgaben, 'kennzahlen') ? 'Werden gerade berechnet …' : 'Noch nicht berechnet. Oben „Kennzahlen berechnen“ antippen.'));
    }
    const e = Object.assign({}, alsWert(letzte.ergebnis) || {});
    const aufgaben = e.aufgaben;
    delete e.aufgaben;
    return karte('Kennzahlen',
      h('div', { class: 'meta' }, 'berechnet ' + zeitText(letzte.beendet)),
      aufgaben ? [h('h3', null, 'Aufgaben'), statusChips(aufgaben)] : null,
      h('h3', null, 'Werte'),
      wertAnzeige(e));
  }

  function entscheidungenKarte(liste) {
    const form = formular(null, [
      feld('Thema', eingabe('thema', { required: true, maxlength: 200, placeholder: 'z. B. Erstes Angebot' })),
      feld('Entscheidung', textfeld('inhalt', { required: true, maxlength: 20000, placeholder: 'Was habt ihr entschieden – und warum?' })),
      h('div', { class: 'knopfreihe' }, absendeKnopf('Entscheidung festhalten')),
    ], async (w, f) => {
      await API.post('/api/gedaechtnis', { art: 'entscheidung', thema: w.thema, inhalt: w.inhalt, quelle: 'Eigentümer (Oberfläche)' });
      f.reset();
      meldung('Entscheidung gespeichert.', 'ok');
      neuLaden();
    });
    return karte('Entscheidungen',
      h('p', { class: 'hilfe' }, 'Entscheidungen trefft nur ihr. Agenten können hier nichts eintragen.'),
      liste.length ? h('ul', { class: 'liste' }, liste.map(gedaechtnisZeile)) : leer('Noch keine Entscheidungen festgehalten.'),
      aufklapp('Entscheidung festhalten', 'entscheidung-neu', false, form));
  }

  function gedaechtnisZeile(e) {
    return h('li', { class: 'eintrag' },
      h('div', { class: 'eintrag-kopf' }, h('span', { class: 'eintrag-titel' }, e.thema), tag(GEDAECHTNIS_ART[e.art] || e.art, GEDAECHTNIS_TON[e.art])),
      h('p', { class: 'text' }, e.inhalt),
      h('div', { class: 'meta' }, h('span', null, zeitText(e.zeit)), h('span', null, 'von ' + akteurName(e.autor)), h('span', null, 'Quelle: ' + e.quelle)));
  }

  function gedaechtnisKarte(eintraege) {
    const listenHuelle = h('div');
    const filter = auswahl('art', [['', 'Alle'], ['fakt', 'Fakten'], ['entscheidung', 'Entscheidungen'], ['hypothese', 'Hypothesen'], ['vorschlag', 'Vorschläge']], zustand.gedaechtnisArt);
    const zeichne = () => {
      const auswahlListe = eintraege.filter(e => !zustand.gedaechtnisArt || e.art === zustand.gedaechtnisArt);
      ersetze(listenHuelle, auswahlListe.length
        ? h('ul', { class: 'liste' }, auswahlListe.slice(0, 60).map(gedaechtnisZeile))
        : leer('Keine Einträge.'));
    };
    filter.addEventListener('change', () => { zustand.gedaechtnisArt = filter.value; zeichne(); });
    zeichne();
    const form = formular(null, [
      h('div', { class: 'felder-2' },
        feld('Art', auswahl('art', [['fakt', 'Fakt (bestätigt)'], ['hypothese', 'Hypothese (Annahme)']], 'fakt')),
        feld('Thema', eingabe('thema', { required: true, maxlength: 200 }))),
      feld('Inhalt', textfeld('inhalt', { required: true, maxlength: 20000 })),
      feld('Quelle (optional)', eingabe('quelle', { maxlength: 500, placeholder: 'z. B. Handelsregister, eigene Erfahrung' })),
      h('div', { class: 'knopfreihe' }, absendeKnopf('Speichern')),
    ], async (w, f) => {
      await API.post('/api/gedaechtnis', ohneLeere({ art: w.art, thema: w.thema, inhalt: w.inhalt, quelle: w.quelle }));
      f.reset();
      meldung('Im Gedächtnis gespeichert.', 'ok');
      neuLaden();
    });
    return karte('Gedächtnis',
      h('div', { class: 'legende' },
        h('span', null, tag(GEDAECHTNIS_ART.fakt, 'ok'), ' belegt'),
        h('span', null, tag(GEDAECHTNIS_ART.entscheidung, 'akzent'), ' von euch'),
        h('span', null, tag(GEDAECHTNIS_ART.hypothese, 'warn'), ' Annahme'),
        h('span', null, tag(GEDAECHTNIS_ART.vorschlag, 'grau'), ' von Agenten')),
      h('div', { class: 'filter' }, feld('Anzeigen', filter)),
      listenHuelle,
      aufklapp('Fakt oder Annahme festhalten', 'gedaechtnis-neu', false, form));
  }

  // ===========================================================================
  // Bereich: Agenten
  // ===========================================================================
  async function ansichtAgenten(z) {
    const [ag, es] = await Promise.all([API.get('/api/agenten'), API.get('/api/einstellungen')]);
    const liste = ag.agenten || [];
    merkeAgenten(liste.filter(a => a.rolle !== 'supervisor'));
    zustand.katalog = es.aktionen || {};
    const rollen = liste.filter(a => a.rolle !== 'supervisor');
    z.append(h('p', { class: 'einleitung' },
      rollen.length + ' Rollen arbeiten (die Architektur erlaubt bis zu ' + zahl(ag.max_rollen) + '). '
      + 'Die Rechte stehen im Code – kein Agent kann sie erweitern. Jede Aktion prüft der Supervisor.'));
    z.append(aufgabeGebenKarte(rollen));
    z.append(h('div', { class: 'legende' },
      h('span', null, tag('grün', 'ok'), ' automatisch erlaubt'),
      h('span', null, tag('gelb', 'warn'), ' nur mit eurer Freigabe')));
    z.append(h('div', { class: 'raster karten' }, liste.map(agentKarte)));
  }

  function rechteChips(rechte) {
    if (!rechte || !rechte.length) return leer('Keine eigenen Rechte.');
    return h('div', { class: 'chips' }, rechte.map(r => {
      const k = zustand.katalog[r];
      return h('span', { class: 'tag ' + (k ? KLASSE_TON[k.klasse] : 'grau'), title: k ? k.beschreibung + ' – ' + KLASSE_TEXT[k.klasse] : r }, r);
    }));
  }

  function agentKarte(a) {
    const istSupervisor = a.rolle === 'supervisor';
    const typen = Object.entries(a.aufgabentypen || {});
    const statusText = { bereit: 'bereit', beschaeftigt: 'beschäftigt' }[a.status] || a.status;
    return h('article', { class: 'karte' },
      h('h2', null, a.name, tag(statusText, a.status === 'beschaeftigt' ? 'blau' : 'ok')),
      h('div', { class: 'meta' }, 'Rolle: ' + a.rolle),
      h('p', null, a.beschreibung),
      istSupervisor
        ? h('p', { class: 'hilfe' }, 'Nimmt selbst keine Aufgaben an, sondern prüft jede Aktion und jedes Ergebnis der anderen Rollen.')
        : [
          h('h3', null, 'Rechte'), rechteChips(a.rechte),
          h('h3', null, 'Aufgabentypen'),
          typen.length
            ? h('ul', { class: 'typen' }, typen.map(([t, b]) => h('li', null, h('code', null, t), ' – ', b)))
            : h('p', { class: 'hilfe' }, tag('noch nicht verfügbar', 'grau'), ' Diese Rolle hat noch keine Aufgabentypen.'),
        ],
      a.zahlen && Object.keys(a.zahlen).length ? [h('h3', null, 'Aufgaben'), statusChips(a.zahlen)] : null,
      (a.letzte_aufgaben || []).length
        ? [h('h3', null, 'Zuletzt'), h('ul', { class: 'mini-liste' }, a.letzte_aufgaben.map(x => h('li', null,
          aufgabenStatusTag(x.status), ' ', x.titel, h('span', { class: 'meta' }, zeitText(x.aktualisiert)))))]
        : null,
      istSupervisor && (a.entscheidungen || []).length
        ? [h('h3', null, 'Letzte Prüfungen'), h('ul', { class: 'mini-liste' }, a.entscheidungen.map(e => h('li', null,
          h('span', null, e.ereignis), h('span', { class: 'meta' }, zeitText(e.zeit)))))]
        : null);
  }

  // Freundliche Felder für bekannte Aufgabentypen (ergänzen das JSON-Feld)
  const FREUNDLICH = {
    'finance.wirtschaftlichkeit': [
      { name: 'preis', text: 'Preis in €', art: 'betrag', pflicht: true },
      { name: 'stunden', text: 'Arbeitsstunden', art: 'zahl' },
      { name: 'stundensatz', text: 'Soll-Stundensatz in € (leer = noch offen)', art: 'betrag' },
      { name: 'kosten', text: 'Direkte Kosten in €', art: 'betrag' },
    ],
    'finance.liquiditaet': [{ name: 'tage', text: 'Zeitraum in Tagen', art: 'ganzzahl', platzhalter: '30' }],
    'finance.simulation_buchen': [
      { name: 'art', text: 'Art (SIMULATION)', art: 'auswahl', optionen: WALLET_BUCHUNGSARTEN, pflicht: true },
      { name: 'betrag', text: 'Betrag in €', art: 'betrag', pflicht: true },
      { name: 'kategorie', text: 'Kategorie', pflicht: true },
      { name: 'begruendung', text: 'Begründung', pflicht: true },
    ],
    'ceo.auftrag_verteilen': [
      { name: 'rolle', text: 'An Rolle', art: 'rolle', pflicht: true },
      { name: 'typ', text: 'Aufgabentyp dieser Rolle', pflicht: true },
      { name: 'titel', text: 'Titel' },
    ],
  };

  function freundlichUmwandeln(f, roh) {
    if (f.art === 'betrag') return betragPflicht(roh, f.text);
    if (f.art === 'zahl') {
      const n = Number(String(roh).replace(',', '.'));
      if (!isFinite(n)) throw new ApiFehler(0, f.text + ': bitte eine Zahl eingeben.');
      return n;
    }
    if (f.art === 'ganzzahl') {
      if (!/^\d+$/.test(roh)) throw new ApiFehler(0, f.text + ': bitte eine ganze Zahl eingeben.');
      return parseInt(roh, 10);
    }
    return roh;
  }

  function aufgabeGebenKarte(rollen) {
    const mitTypen = rollen.filter(a => Object.keys(a.aufgabentypen || {}).length);
    if (!mitTypen.length) return nichtVerfuegbar('Einer Rolle eine Aufgabe geben', 'Keine Rolle hat bisher Aufgabentypen.');
    const rolleWahl = auswahl('rolle', mitTypen.map(a => [a.rolle, a.name]), mitTypen[0].rolle);
    const typWahl = h('select', { name: 'typ' });
    const typHilfe = h('div', { class: 'hilfe' });
    const freundlich = h('div', { class: 'felder-2' });
    const json = textfeld('eingabe_json', { rows: 3, placeholder: '{}', spellcheck: 'false', class: 'mono' });
    let felder = [];

    const freundlichFuellen = () => {
      const agent = mitTypen.find(a => a.rolle === rolleWahl.value);
      typHilfe.textContent = agent ? (agent.aufgabentypen[typWahl.value] || '') : '';
      felder = FREUNDLICH[rolleWahl.value + '.' + typWahl.value] || [];
      ersetze(freundlich, felder.map(f => {
        let steuer;
        if (f.art === 'auswahl') steuer = auswahl('frei_' + f.name, f.optionen, f.optionen[0][0]);
        else if (f.art === 'rolle') steuer = auswahl('frei_' + f.name, mitTypen.map(a => [a.rolle, a.name]), mitTypen[0].rolle);
        else if (f.art === 'betrag') steuer = betragFeld('frei_' + f.name, { required: !!f.pflicht });
        else steuer = eingabe('frei_' + f.name, { required: !!f.pflicht, placeholder: f.platzhalter || '', maxlength: 500 });
        return feld(f.text, steuer);
      }));
      freundlich.hidden = !felder.length;
    };
    const typenFuellen = () => {
      const agent = mitTypen.find(a => a.rolle === rolleWahl.value) || mitTypen[0];
      typWahl.replaceChildren(...Object.keys(agent.aufgabentypen).map(t => h('option', { value: t }, t)));
      freundlichFuellen();
    };
    rolleWahl.addEventListener('change', typenFuellen);
    typWahl.addEventListener('change', freundlichFuellen);
    typenFuellen();

    const form = formular({ 'data-pruef': 'aufgabe-formular' }, [
      h('div', { class: 'felder-2' }, feld('Rolle', rolleWahl), feld('Aufgabentyp', typWahl)),
      typHilfe,
      freundlich,
      feld('Weitere Eingaben als JSON (optional)', json, 'Für Fortgeschrittene, z. B. {"tage": 30}. Felder oben haben Vorrang.'),
      h('div', { class: 'felder-2' },
        feld('Titel (optional)', eingabe('titel', { maxlength: 200 })),
        feld('Priorität', auswahl('prioritaet', PRIO_OPTIONEN, 3))),
      h('div', { class: 'knopfreihe' }, absendeKnopf('Aufgabe übergeben')),
    ], async (w, f) => {
      let daten = {};
      if (w.eingabe_json) {
        try {
          daten = JSON.parse(w.eingabe_json);
        } catch (e) {
          throw new ApiFehler(0, 'Das JSON ist ungültig: ' + e.message);
        }
        if (!daten || typeof daten !== 'object' || Array.isArray(daten)) {
          throw new ApiFehler(0, 'Das JSON muss ein Objekt sein, z. B. {"tage": 30}.');
        }
      }
      for (const fd of felder) {
        const roh = w['frei_' + fd.name];
        if (roh === undefined || roh === '') {
          if (fd.pflicht) throw new ApiFehler(0, 'Bitte ausfüllen: ' + fd.text);
          continue;
        }
        daten[fd.name] = freundlichUmwandeln(fd, roh);
      }
      const r = await API.post('/api/aufgaben', ohneLeere({
        rolle: w.rolle, typ: w.typ, titel: w.titel, prioritaet: Number(w.prioritaet), eingabe: daten,
      }));
      f.reset();
      typenFuellen();
      meldung('Aufgabe übergeben (' + r.id + '). Fortschritt unter „Aufgaben“.', 'ok');
    });
    return karte('Einer Rolle eine Aufgabe geben', form);
  }

  // ===========================================================================
  // Bereich: Wallet (SIMULATION)
  // ===========================================================================
  async function ansichtWallet(z) {
    const w = await API.get('/api/wallet');
    const historie = w.historie || [];
    z.append(h('section', { class: 'banner simulation', role: 'note', 'data-pruef': 'wallet-banner' },
      h('div', { class: 'gross' }, 'SIMULATION – kein echtes Geld'),
      h('p', null, w.hinweis || 'Internes Simulationsguthaben.'),
      h('p', null, 'Ein Stand von 0 € oder weniger schaltet nichts ab. Echte Einnahmen und Ausgaben stehen nur unter „Finanzen“.')));
    z.append(h('div', { class: 'raster' },
      kachel('Simulierter Stand', w.stand || euro(w.stand_cent), (w.stand_cent || 0) < 0 ? 'fehler' : 'sim', 'SIMULATION', 'wallet-stand'),
      kachel('Davon reserviert', euro(w.reserviert_cent), 'sim', 'SIMULATION'),
      kachel('Buchungen', zahl(w.buchungen), '', 'unveränderbar – Korrektur nur per Gegenbuchung')));

    const form = formular({ 'data-pruef': 'wallet-formular' }, [
      h('div', { class: 'felder-2' },
        feld('Art', auswahl('art', WALLET_BUCHUNGSARTEN, 'ausgabe', { 'data-pruef': 'wallet-art' })),
        feld('Betrag in €', betragFeld('betrag', { required: true, 'data-pruef': 'wallet-betrag' }))),
      h('div', { class: 'felder-2' },
        feld('Kategorie', eingabe('kategorie', { required: true, maxlength: 60, placeholder: 'z. B. Werbung', 'data-pruef': 'wallet-kategorie' })),
        feld('Begründung', eingabe('begruendung', { required: true, maxlength: 500, 'data-pruef': 'wallet-begruendung' }))),
      h('div', { class: 'knopfreihe' }, absendeKnopf('Simuliert buchen', { 'data-pruef': 'wallet-absenden' })),
    ], async (werte, f) => {
      const r = await API.post('/api/wallet/buchung', {
        art: werte.art, betrag: betragPflicht(werte.betrag), kategorie: werte.kategorie, begruendung: werte.begruendung,
      });
      f.reset();
      meldung('Simulierte Buchung gespeichert. Neuer Stand: ' + euro(r.stand_cent) + ' (SIMULATION)', 'ok');
      (r.warnungen || []).forEach(t => meldung(t, 'warn'));
      neuLaden();
    });
    z.append(karte('Simulierte Buchung', h('p', { class: 'hilfe' }, 'Nur intern zum Planen und Üben. Es fließt kein Geld.'), form));
    z.append(budgetKarte('wallet', w.budgets));

    const ausgeglichen = new Set(historie.filter(b => b.gegenbuchung_zu).map(b => b.gegenbuchung_zu));
    z.append(karte('Buchungen (SIMULATION)',
      h('p', { class: 'hilfe' }, 'Die Historie ist unveränderbar. Fehler werden durch eine Gegenbuchung ausgeglichen.'),
      historie.length
        ? h('ul', { class: 'liste' }, historie.map(b => buchungZeile(b, {
          sim: true, gegengebucht: ausgeglichen.has(b.id), pfad: '/api/wallet/' + enc(b.id) + '/gegenbuchung',
        })))
        : leer('Noch keine Buchungen.')));
  }

  // ===========================================================================
  // Bereich: Finanzen (REAL)
  // ===========================================================================
  async function ansichtFinanzen(z) {
    const f = await API.get('/api/finanzen');
    const liq = f.liquiditaet || {};
    z.append(h('section', { class: 'banner real', role: 'note', 'data-pruef': 'finanzen-banner' },
      h('div', { class: 'gross' }, 'REAL – tatsächliche Geschäftsfinanzen'),
      h('p', null, f.hinweis || ''),
      h('p', null, 'Das simulierte Wallet wird hier nie mitgerechnet. Agenten können hier nichts buchen – nur ihr.')));
    z.append(h('div', { class: 'raster' },
      kachel('Einnahmen (verifiziert)', euro(f.einnahmen_verifiziert_cent), 'ok', 'nur mit Zahlungsnachweis'),
      kachel('Ausgaben', euro(f.ausgaben_cent), '', 'erfasste echte Ausgaben'),
      kachel('Korrekturen', euro(f.korrekturen_cent), '', 'Summe der Gegenbuchungen'),
      kachel('Saldo (real)', f.saldo || euro(f.saldo_cent), (f.saldo_cent || 0) < 0 ? 'fehler' : '', 'Einnahmen − Ausgaben ± Korrekturen'),
      kachel('Offene Forderungen', f.offene_forderungen || euro(f.offene_forderungen_cent), 'warn', 'noch kein Geld – erst bei Zahlung eine Einnahme'),
      kachel('Erwartet in ' + (liq.zeitraum_tage || 30) + ' Tagen', euro(liq.erwartet_aus_forderungen_cent), '', liq.status_erwartet || 'ERWARTET – nicht bestätigt')));

    const ausgabe = formular(null, [
      h('div', { class: 'felder-2' },
        feld('Betrag in €', betragFeld('betrag', { required: true })),
        feld('Kategorie', eingabe('kategorie', { required: true, maxlength: 60, placeholder: 'z. B. Material' })),
        feld('Empfänger', eingabe('gegenpartei', { required: true, maxlength: 200 })),
        feld('Datum', eingabe('datum', { type: 'date', value: heuteIso() }))),
      feld('Begründung', eingabe('begruendung', { required: true, maxlength: 500 })),
      feld('Beleg (optional)', eingabe('beleg', { maxlength: 200, placeholder: 'z. B. Rechnungsnummer' })),
      h('div', { class: 'knopfreihe' }, absendeKnopf('Ausgabe buchen')),
    ], async (w, form) => {
      await API.post('/api/finanzen/ausgabe', ohneLeere(Object.assign({}, w, { betrag: betragPflicht(w.betrag) })));
      form.reset();
      meldung('Ausgabe gebucht (REAL).', 'ok');
      neuLaden();
    });

    const einnahme = formular({ 'data-pruef': 'einnahme-formular' }, [
      hinweis('Nur Zahlungen buchen, die tatsächlich eingegangen sind und die ihr geprüft habt (z. B. auf dem Kontoauszug). '
        + 'Ohne Zahlungsnachweis wird nichts gebucht. Eine Rechnung oder ein Angebot ist noch keine Einnahme – dafür „Forderung anlegen“.', 'warn'),
      h('div', { class: 'felder-2' },
        feld('Betrag in €', betragFeld('betrag', { required: true })),
        feld('Kategorie', eingabe('kategorie', { required: true, maxlength: 60, placeholder: 'z. B. Webseiten' })),
        feld('Zahlender Kunde', eingabe('gegenpartei', { required: true, maxlength: 200 })),
        feld('Eingangsdatum', eingabe('datum', { type: 'date', value: heuteIso() }))),
      feld('Begründung', eingabe('begruendung', { required: true, maxlength: 500 })),
      h('div', { class: 'felder-2' },
        feld('Zahlungsnachweis (Pflicht)', eingabe('zahlungsnachweis', { required: true, maxlength: 200, placeholder: 'z. B. Kontoauszug 21.11., Ref. 4711' })),
        feld('Geprüft von (Pflicht)', eingabe('verifiziert_von', { required: true, maxlength: 100, placeholder: 'Wer hat den Eingang geprüft?' }))),
      feld('Beleg (optional)', eingabe('beleg', { maxlength: 200, placeholder: 'z. B. Rechnungsnummer' })),
      h('div', { class: 'knopfreihe' }, absendeKnopf('Geprüfte Einnahme buchen')),
    ], async (w, form) => {
      await API.post('/api/finanzen/einnahme', ohneLeere(Object.assign({}, w, { betrag: betragPflicht(w.betrag) })));
      form.reset();
      meldung('Einnahme gebucht (REAL, mit Nachweis).', 'ok');
      neuLaden();
    });

    const forderung = formular(null, [
      h('div', { class: 'felder-2' },
        feld('Kunde', eingabe('kunde', { required: true, maxlength: 200 })),
        feld('Betrag in €', betragFeld('betrag', { required: true })),
        feld('Fällig am (optional)', eingabe('faellig', { type: 'date' })),
        feld('Rechnungsnummer (optional)', eingabe('rechnung_ref', { maxlength: 100 }))),
      feld('Notiz (optional)', eingabe('notiz', { maxlength: 500 })),
      h('div', { class: 'knopfreihe' }, absendeKnopf('Forderung anlegen')),
    ], async (w, form) => {
      await API.post('/api/forderungen', ohneLeere(Object.assign({}, w, { betrag: betragPflicht(w.betrag) })));
      form.reset();
      meldung('Forderung angelegt – sie zählt erst als Einnahme, wenn die Zahlung da ist.', 'ok');
      neuLaden();
    });

    z.append(karte('Buchen',
      aufklapp('Ausgabe erfassen', 'fin-ausgabe', false, ausgabe),
      aufklapp('Einnahme erfassen (nur mit Zahlungsnachweis)', 'fin-einnahme', false, einnahme),
      aufklapp('Forderung anlegen (Rechnung gestellt, Geld noch nicht da)', 'fin-forderung', false, forderung)));

    const forderungen = f.forderungen || [];
    z.append(karte('Forderungen',
      forderungen.length ? h('ul', { class: 'liste' }, forderungen.map(forderungZeile)) : leer('Keine Forderungen.')));

    const buchungen = f.buchungen || [];
    const ausgeglichen = new Set(buchungen.filter(b => b.gegenbuchung_zu).map(b => b.gegenbuchung_zu));
    z.append(karte('Buchungen (REAL)',
      h('p', { class: 'hilfe' }, 'Unveränderbar. Korrekturen nur durch Gegenbuchung.'),
      buchungen.length
        ? h('ul', { class: 'liste' }, buchungen.map(b => buchungZeile(b, {
          sim: false, gegengebucht: ausgeglichen.has(b.id), pfad: '/api/finanzen/' + enc(b.id) + '/gegenbuchung',
        })))
        : leer('Noch keine echten Buchungen.')));
    z.append(budgetKarte('real', f.budgets));
  }

  function forderungZeile(fo) {
    const zeile = h('li', { class: 'eintrag' },
      h('div', { class: 'eintrag-kopf' }, h('span', { class: 'eintrag-titel' }, fo.kunde), h('span', { class: 'betrag' }, euro(fo.betrag_cent))),
      h('div', { class: 'meta' },
        tag(FORDERUNG_STATUS[fo.status] || fo.status, fo.status === 'offen' ? 'warn' : fo.status === 'bezahlt' ? 'ok' : 'grau'),
        fo.faellig ? h('span', null, 'fällig ' + tagText(fo.faellig)) : null,
        fo.rechnung_ref ? h('span', null, 'Rechnung ' + fo.rechnung_ref) : null,
        h('span', null, 'angelegt ' + zeitText(fo.erstellt))),
      fo.notiz ? h('p', { class: 'text' }, fo.notiz) : null);
    if (fo.status === 'offen') {
      const teile = umschaltBereich('Zahlung ist eingegangen', 'zweit klein', zu => formular(null, [
        hinweis('Nur buchen, wenn das Geld wirklich auf dem Konto ist und ihr den Eingang geprüft habt.', 'warn'),
        h('div', { class: 'felder-2' },
          feld('Zahlungsnachweis', eingabe('zahlungsnachweis', { required: true, maxlength: 200, placeholder: 'z. B. Kontoauszug 21.11., Ref. 4711' })),
          feld('Geprüft von', eingabe('verifiziert_von', { required: true, maxlength: 100 }))),
        feld('Eingangsdatum', eingabe('datum', { type: 'date', value: heuteIso() })),
        h('div', { class: 'knopfreihe' }, absendeKnopf('Als Einnahme buchen'), abbrechenKnopf(zu)),
      ], async (w) => {
        await API.post('/api/forderungen/' + enc(fo.id) + '/bezahlt', ohneLeere(w));
        meldung('Zahlung als Einnahme gebucht (REAL).', 'ok');
        neuLaden();
      }));
      zeile.append(h('div', { class: 'knopfreihe' },
        teile[0],
        sicherheitsKnopf('Stornieren', 'Wirklich stornieren?', 'gefahr klein', async () => {
          await API.post('/api/forderungen/' + enc(fo.id) + '/stornieren');
          meldung('Forderung storniert.', 'ok');
          neuLaden();
        }),
        teile[1]));
    }
    return zeile;
  }

  // ===========================================================================
  // Bereich: Produkte
  // ===========================================================================
  const PRODUKT_TYP = { webseite: 'Webseite', verkaufsseite: 'Verkaufsseite', google_profil_paket: 'Google-Profil-Paket' };

  async function ansichtProdukte(z) {
    const [p, ag] = await Promise.all([optional('/api/produkte'), API.get('/api/agenten')]);
    if (p.fehlt) {
      z.append(nichtVerfuegbar('Produkte',
        'Die Produkt-Schnittstelle (Kunden-Webseiten, Verkaufsseite, Qualitätsprüfung) ist in dieser Version noch nicht eingebaut. '
        + 'Sobald sie da ist, erscheint sie hier automatisch.'));
      return;
    }
    // Kann der Product-Agent schon Google-Profil-Pakete? (Aufgabentypen kommen aus dem Code des Agenten)
    const produktAgent = (ag.agenten || []).find(a => a.rolle === 'product');
    const googleDa = !!produktAgent && Object.keys(produktAgent.aufgabentypen || {}).some(t => /google|profil/i.test(t));
    const produkte = p.produkte || [];
    z.append(h('p', { class: 'einleitung' }, 'Der Product-Agent erstellt Dateien zur Prüfung. Veröffentlichen ist freigabepflichtig – ohne euer Ja geht nichts online.'));
    z.append(googleProfilKarte(googleDa, !produkte.length));
    z.append(webseiteKarte(!googleDa && !produkte.length), verkaufsseiteKarte(googleDa));
    z.append(karte(['Erstellte Produkte', tag(String(produkte.length), 'grau')],
      produkte.length ? h('div', { class: 'liste' }, produkte.map(produktKarte)) : leer('Noch keine Produkte erstellt.')));
  }

  function leistungenAus(text, hoechstens) {
    const liste = zeilen(text);
    if (liste.length > hoechstens) throw new ApiFehler(0, 'Bitte höchstens ' + hoechstens + ' Leistungen angeben (eine pro Zeile).');
    return liste;
  }

  /**
   * Google-Profil-Paket (laut Marktanalyse empfohlenes erstes Angebot).
   * Ob der Product-Agent es schon kann, steht in seinen Aufgabentypen. Fehlt die Route trotzdem
   * (404/405 beim Absenden), wird das Formular sichtbar als „noch nicht verfügbar“ gesperrt.
   */
  function googleProfilKarte(verfuegbar, offen) {
    const titelTag = tag('noch nicht verfügbar', 'grau');
    const erklaerung = h('p', { class: 'hilfe' },
      'Der Product-Agent kann Google-Profil-Pakete in dieser Version noch nicht erstellen. Sobald er es kann, ist das Formular hier freigeschaltet.');
    const satz = h('fieldset', { class: 'formular-satz', disabled: !verfuegbar },
      h('div', { class: 'felder-2' },
        feld('Firmenname', eingabe('firma', { required: true, maxlength: 80 })),
        feld('Branche', eingabe('branche', { required: true, maxlength: 60, placeholder: 'z. B. Gebäudereinigung' })),
        feld('Ort', eingabe('ort', { required: true, maxlength: 60 })),
        feld('Einzugsgebiet (optional)', eingabe('einzugsgebiet', { maxlength: 200, placeholder: 'z. B. Leverkusen und Umgebung' }))),
      feld('Leistungen', textfeld('leistungen', { required: true, rows: 4, placeholder: 'Eine Leistung pro Zeile (höchstens 12)' })),
      h('div', { class: 'felder-2' },
        feld('Adresse (optional)', eingabe('adresse', { maxlength: 200, placeholder: 'Straße, PLZ Ort' })),
        feld('Telefon (optional)', eingabe('telefon', { type: 'tel', maxlength: 40 })),
        feld('E-Mail (optional)', eingabe('email', { type: 'email', maxlength: 120 })),
        feld('Webseite (optional)', eingabe('webseite', { inputmode: 'url', maxlength: 200, placeholder: 'z. B. www.firma.de' })),
        feld('Gründungsjahr (optional)', eingabe('gruendungsjahr', { inputmode: 'numeric', maxlength: 4, pattern: '[0-9]{4}', placeholder: 'z. B. 2015' }))),
      feld('Öffnungszeiten (optional)', textfeld('oeffnungszeiten', { rows: 3, maxlength: 200, placeholder: 'z. B. Mo–Fr 7–17 Uhr' })),
      feld('Besonderheiten (optional)', textfeld('besonderheiten', { rows: 3, maxlength: 600, placeholder: 'z. B. Familienbetrieb, kurzfristige Termine' })),
      hinweis('Das Paket entsteht als Dateien zur Prüfung. AUTONOMOUS hat keinen Zugang zu Google-Konten – eintragen müsst ihr selbst. Nur Geschäftsdaten angeben.'),
      h('div', { class: 'knopfreihe' }, absendeKnopf('Google-Profil-Paket erstellen lassen', { 'data-pruef': 'google-profil-absenden' })));
    const kopf = h('h2', null, 'Google-Profil-Paket', verfuegbar ? null : titelTag);
    const karteEl = h('section', { class: 'karte empfohlen', 'data-pruef': verfuegbar ? 'google-profil' : 'google-profil-nicht-verfuegbar' },
      kopf,
      h('div', { class: 'empfehlung-kopf' },
        tag('Empfohlen als erstes Angebot', 'akzent'),
        h('span', { class: 'hilfe' }, 'laut Marktanalyse – ein Vorschlag, entscheiden müsst ihr')),
      verfuegbar ? null : erklaerung);
    const sperren = () => {
      satz.disabled = true;
      karteEl.dataset.pruef = 'google-profil-nicht-verfuegbar';
      if (!titelTag.isConnected) kopf.append(titelTag);
      if (!erklaerung.isConnected) kopf.after(erklaerung);
    };
    const form = formular({ 'data-pruef': 'google-profil-formular' }, [satz], async (w, f) => {
      const daten = ohneLeere(Object.assign({}, w, { leistungen: leistungenAus(w.leistungen, 12) }));
      let r;
      try {
        r = await API.post('/api/produkte/google_profil', daten);
      } catch (fehler) {
        if (!istFehlendeRoute(fehler)) throw fehler;
        sperren();
        meldung('Google-Profil-Paket: noch nicht verfügbar – die Schnittstelle fehlt noch.', 'warn');
        return;
      }
      f.reset();
      auftragGemeldet(r, 'den Product-Agenten');
    });
    karteEl.append(aufklapp(verfuegbar ? 'Google-Profil-Paket erstellen' : 'Formular ansehen', 'google-profil-neu', verfuegbar && offen, form));
    return karteEl;
  }

  function webseiteKarte(offen) {
    const form = formular({ 'data-pruef': 'webseite-formular' }, [
      h('div', { class: 'felder-2' },
        feld('Firmenname', eingabe('firma', { required: true, maxlength: 80 })),
        feld('Branche', eingabe('branche', { required: true, maxlength: 60, placeholder: 'z. B. Gebäudereinigung' })),
        feld('Ort', eingabe('ort', { required: true, maxlength: 60 })),
        feld('Einzugsgebiet (optional)', eingabe('einzugsgebiet', { maxlength: 200, placeholder: 'z. B. Leverkusen und Umgebung' }))),
      feld('Leistungen', textfeld('leistungen', { required: true, rows: 4, placeholder: 'Eine Leistung pro Zeile (höchstens 12)' })),
      h('div', { class: 'felder-2' },
        feld('Telefon (optional)', eingabe('telefon', { type: 'tel', maxlength: 40 })),
        feld('E-Mail (optional)', eingabe('email', { type: 'email', maxlength: 120 })),
        feld('Leitsatz (optional)', eingabe('slogan', { maxlength: 160 }))),
      feld('Öffnungszeiten (optional)', textfeld('oeffnungszeiten', { rows: 3, maxlength: 200, placeholder: 'z. B. Mo–Fr 7–17 Uhr' })),
      feld('Über uns (optional)', textfeld('ueber_uns', { rows: 3, maxlength: 1200 })),
      hinweis('Nur Geschäftsdaten eintragen, die auf die Webseite sollen – keine privaten Angaben.'),
      h('div', { class: 'knopfreihe' }, absendeKnopf('Webseite erstellen lassen')),
    ], async (w, f) => {
      const daten = ohneLeere(Object.assign({}, w, { leistungen: leistungenAus(w.leistungen, 12) }));
      const r = await API.post('/api/produkte/webseite', daten);
      f.reset();
      auftragGemeldet(r, 'den Product-Agenten');
    });
    return h('section', { class: 'karte' }, aufklapp('Kunden-Webseite erstellen', 'webseite-neu', offen, form));
  }

  function verkaufsseiteKarte(googleDa) {
    const angebote = googleDa
      ? [['google_profil', 'Google-Profil-Paket (empfohlen)'], ['webseite', 'Webseiten-Paket']]
      : [['webseite', 'Webseiten-Paket']];
    const form = formular({ 'data-pruef': 'verkaufsseite-formular' }, [
      feld('Angebot', auswahl('angebot', angebote, angebote[0][0]),
        googleDa ? 'Für welches Angebot soll die Seite werben?' : 'Google-Profil-Paket: noch nicht verfügbar.'),
      h('div', { class: 'felder-2' },
        feld('Preis in € (optional)', betragFeld('preis'), 'Leer lassen, solange ihr den Preis nicht festgelegt habt.'),
        feld('Lieferzeit (optional)', eingabe('lieferzeit', { maxlength: 60, placeholder: 'z. B. 5 Werktage' })),
        feld('Hinweis zum Preis (optional)', eingabe('preis_hinweis', { maxlength: 160 })),
        feld('Anbieter (euer Firmenname, optional)', eingabe('anbieter', { maxlength: 80 })),
        feld('Region (optional)', eingabe('region', { maxlength: 60, placeholder: 'NRW' })),
        feld('Telefon (optional)', eingabe('telefon', { type: 'tel', maxlength: 40 })),
        feld('E-Mail (optional)', eingabe('email', { type: 'email', maxlength: 120 }))),
      h('div', { class: 'knopfreihe' }, absendeKnopf('Verkaufsseite erstellen lassen')),
    ], async (w, f) => {
      const daten = ohneLeere(Object.assign({}, w, { preis: w.preis ? betragPflicht(w.preis, 'Preis') : '' }));
      const r = await API.post('/api/produkte/verkaufsseite', daten);
      f.reset();
      auftragGemeldet(r, 'den Product-Agenten');
    });
    return h('section', { class: 'karte' }, aufklapp('Verkaufsseite für das eigene Angebot erstellen', 'verkaufsseite-neu', false, form));
  }

  /** Link auf eine erzeugte Datei: /produkte/<ordner>/<datei>, jeder Teil einzeln kodiert. */
  function produktUrl(ordner, datei) {
    const teile = (String(ordner || '') + '/' + String(datei || '')).split('/').filter(Boolean);
    if (teile.length < 2 || teile.some(t => t === '.' || t === '..')) return null;
    return sichererLink('/produkte/' + teile.map(enc).join('/'));
  }

  function produktKarte(p) {
    const ansehen = sichererLink(p.ansehen_url);
    const einschraenkungen = alsWert(p.einschraenkungen) || [];
    const qualitaet = alsWert(p.qualitaet);
    const dateien = alsWert(p.dateien) || [];
    const bestanden = qualitaet && typeof qualitaet === 'object' ? qualitaet.bestanden : undefined;
    return h('article', { class: 'eintrag', 'data-pruef': 'produkt' },
      h('div', { class: 'eintrag-kopf' }, h('span', { class: 'eintrag-titel' }, p.name || p.id),
        tag(PRODUKT_STATUS[p.status] || p.status || 'unbekannt', PRODUKT_TON[p.status])),
      h('div', { class: 'meta' },
        p.typ ? h('span', null, PRODUKT_TYP[p.typ] || p.typ) : null,
        p.erstellt ? h('span', null, 'erstellt ' + zeitText(p.erstellt)) : null,
        typeof bestanden === 'boolean' ? h('span', null, 'Qualitätsprüfung ' + (bestanden ? 'bestanden' : 'nicht bestanden')) : null),
      Array.isArray(dateien) && dateien.length
        ? [h('h4', null, 'Dateien'), h('ul', { class: 'dateiliste' }, dateien.map(d => {
          const name = typeof d === 'string' ? d : (d && (d.name || d.datei)) || '';
          const url = produktUrl(p.ordner, name);
          return h('li', null, url ? h('a', { href: url, target: '_blank', rel: 'noopener noreferrer' }, name) : name);
        }))]
        : null,
      Array.isArray(einschraenkungen) && einschraenkungen.length
        ? [h('h4', null, 'Bekannte Einschränkungen'), h('ul', { class: 'werteliste' }, einschraenkungen.map(e => h('li', null, wertAnzeige(e))))]
        : null,
      qualitaet && typeof qualitaet === 'object' && Object.keys(qualitaet).length
        ? h('details', { class: 'aufklapp klein', 'data-schluessel': 'qualitaet-' + p.id }, h('summary', null, 'Ergebnis der Qualitätsprüfung'), wertAnzeige(qualitaet))
        : null,
      h('div', { class: 'knopfreihe' },
        ansehen ? h('a', { class: 'knopf klein', href: ansehen, target: '_blank', rel: 'noopener noreferrer' }, 'Ansehen') : null,
        aktionsKnopf('Qualität erneut prüfen', 'zweit klein', async () => {
          const r = await API.post('/api/produkte/' + enc(p.id) + '/pruefen');
          auftragGemeldet(r, 'den Product-Agenten');
        })));
  }

  // ===========================================================================
  // Bereich: Vertrieb
  // ===========================================================================
  // Vom Eigentümer setzbare Angebotsstatus (der Server prüft die Wechsel noch einmal)
  const ANGEBOT_WECHSEL = {
    entwurf: ['geprueft', 'abgelehnt'],
    geprueft: ['versendet', 'abgelehnt'],
    versendet: ['angenommen', 'abgelehnt'],
    angenommen: [],
    abgelehnt: [],
  };
  const ANGEBOT_WAHL_TEXT = {
    geprueft: 'Geprüft – Inhalt und Preis stimmen',
    versendet: 'Versendet – ihr habt es selbst verschickt',
    angenommen: 'Angenommen',
    abgelehnt: 'Abgelehnt',
  };

  async function ansichtVertrieb(z) {
    const [k, a, p, fg] = await Promise.all([
      optional('/api/kontakte'), optional('/api/angebote'), optional('/api/produkte'), API.get('/api/freigaben'),
    ]);
    // Neueste Freigabe je Angebot (Ziel „angebot:<id>“), damit der Versand-Stand sichtbar ist
    const versand = {};
    (fg.freigaben || []).forEach(f => {
      const m = /^angebot:(.+)$/.exec(String(f.ziel || ''));
      if (!m) return;
      const alt = versand[m[1]];
      if (!alt || String(f.zeit) > String(alt.zeit)) versand[m[1]] = f;
    });
    z.append(hinweis('AUTONOMOUS versendet nichts selbst – Kundenkontakt nur nach eurer Freigabe. Werbung per E-Mail oder Telefon '
      + 'braucht in der Regel eine Einwilligung (§ 7 UWG); ohne Einwilligung lieber Brief, Besuch oder Empfehlung. '
      + 'Nur Firmendaten speichern, die ihr wirklich braucht.'));
    const kontakte = k.fehlt ? [] : (k.kontakte || []);
    if (k.fehlt) {
      z.append(nichtVerfuegbar('Kontakte und Kundenstatus', 'Die Vertriebs-Schnittstelle für Kontakte ist in dieser Version noch nicht eingebaut.'));
    } else {
      const stufen = normStufen(k.stufen);
      z.append(pipelineKarte(kontakte, stufen), kontaktFormKarte(!kontakte.length), kontakteKarte(kontakte, stufen));
    }
    if (a.fehlt) {
      z.append(nichtVerfuegbar('Angebote', 'Die Angebots-Schnittstelle ist in dieser Version noch nicht eingebaut.'));
    } else {
      z.append(angebotFormKarte(kontakte, p.fehlt ? [] : (p.produkte || [])), angeboteKarte(a.angebote || [], kontakte, versand));
    }
  }

  function normStufen(stufen) {
    let liste = [];
    if (Array.isArray(stufen)) {
      liste = stufen.map(x => typeof x === 'string'
        ? [x, KONTAKT_STATUS[x] || x]
        : [x.id || x.wert || x.status || x.name, x.name || x.titel || x.label || KONTAKT_STATUS[x.id] || x.id]);
    } else if (stufen && typeof stufen === 'object') {
      liste = Object.entries(stufen).map(([id, t]) => [id, typeof t === 'string' ? t : (KONTAKT_STATUS[id] || id)]);
    }
    liste = liste.filter(s => s[0]);
    return liste.length ? liste : Object.entries(KONTAKT_STATUS);
  }

  function pipelineKarte(kontakte, stufen) {
    const zahlen = {};
    stufen.forEach(s => { zahlen[s[0]] = 0; });
    kontakte.forEach(kt => { zahlen[kt.status] = (zahlen[kt.status] || 0) + 1; });
    return karte(['Kundenstatus', tag(kontakte.length + ' Kontakte', 'grau')],
      h('div', { class: 'chips' }, Object.entries(zahlen).map(([s, n]) =>
        h('span', { class: 'chip' }, tag((stufen.find(x => x[0] === s) || [s, KONTAKT_STATUS[s] || s])[1], KONTAKT_TON[s]), h('strong', null, zahl(n))))));
  }

  function kontaktFormKarte(offen) {
    const form = formular({ 'data-pruef': 'kontakt-formular' }, [
      h('div', { class: 'felder-2' },
        feld('Firma', eingabe('firma', { required: true, maxlength: 120 })),
        feld('Ansprechpartner (optional)', eingabe('ansprechpartner', { maxlength: 120 })),
        feld('Branche (optional)', eingabe('branche', { maxlength: 80 })),
        feld('Ort (optional)', eingabe('ort', { maxlength: 80 }))),
      feld('Woher kennt ihr den Kontakt?', eingabe('quelle', { required: true, maxlength: 200, placeholder: 'z. B. Empfehlung, Messe, Handelsregister' })),
      h('div', { class: 'felder-2' },
        feld('Einwilligung zu Werbung', auswahl('einwilligung', [['keine', 'keine'], ['ja', 'ja, liegt vor']], 'keine')),
        feld('Nachweis der Einwilligung', eingabe('einwilligung_nachweis', { maxlength: 300, placeholder: 'nur bei „ja“: wann, wie, von wem' }))),
      feld('Nächster Schritt (optional)', eingabe('naechster_schritt', { maxlength: 300 })),
      feld('Notizen (optional)', textfeld('notizen', { maxlength: 2000 })),
      hinweis('Keine privaten Telefonnummern, keine Profile von Privatpersonen. Nur Firmendaten, die ihr für die Anfrage braucht.', 'warn'),
      h('div', { class: 'knopfreihe' }, absendeKnopf('Kontakt speichern')),
    ], async (w, f) => {
      if (w.einwilligung === 'ja' && !w.einwilligung_nachweis) throw new ApiFehler(0, 'Bei „Einwilligung: ja“ bitte den Nachweis angeben.');
      await API.post('/api/kontakte', ohneLeere(w));
      f.reset();
      meldung('Kontakt gespeichert.', 'ok');
      neuLaden();
    });
    return h('section', { class: 'karte' }, aufklapp('Neuen Kontakt anlegen', 'kontakt-neu', offen, form));
  }

  function kontakteKarte(kontakte, stufen) {
    return karte('Kontakte',
      kontakte.length ? h('ul', { class: 'liste' }, kontakte.map(kt => kontaktZeile(kt, stufen))) : leer('Noch keine Kontakte.'));
  }

  function kontaktZeile(kt, stufen) {
    const stufeText = (stufen.find(s => s[0] === kt.status) || [kt.status, KONTAKT_STATUS[kt.status] || kt.status])[1];
    const statusTeile = umschaltBereich('Status ändern', 'zweit klein', zu => formular(null, [
      h('div', { class: 'felder-2' },
        feld('Status', auswahl('status', stufen, kt.status)),
        feld('Nächster Schritt', eingabe('naechster_schritt', { maxlength: 300, value: kt.naechster_schritt || '' }))),
      h('div', { class: 'knopfreihe' }, absendeKnopf('Speichern'), abbrechenKnopf(zu)),
    ], async (w) => {
      await API.post('/api/kontakte/' + enc(kt.id) + '/status', { status: w.status, naechster_schritt: w.naechster_schritt || '' });
      meldung('Status gespeichert.', 'ok');
      neuLaden();
    }));
    const nachrichtTeile = umschaltBereich('Nachricht entwerfen', 'zweit klein', zu => formular(null, [
      feld('Anlass', eingabe('anlass', { required: true, maxlength: 300, placeholder: 'z. B. Nachfassen nach dem Besuch am Montag' })),
      h('p', { class: 'hilfe' }, 'Der Sales-Agent erstellt nur einen Entwurf. Versendet wird nichts ohne eure Freigabe.'),
      h('div', { class: 'knopfreihe' }, absendeKnopf('Entwurf erstellen lassen'), abbrechenKnopf(zu)),
    ], async (w) => {
      const r = await API.post('/api/vertrieb/nachricht', { kontakt_id: kt.id, anlass: w.anlass });
      auftragGemeldet(r, 'den Sales-Agenten');
    }));
    return h('li', { class: 'eintrag' },
      h('div', { class: 'eintrag-kopf' }, h('span', { class: 'eintrag-titel' }, kt.firma), tag(stufeText, KONTAKT_TON[kt.status])),
      h('div', { class: 'meta' },
        kt.ansprechpartner ? h('span', null, kt.ansprechpartner) : null,
        kt.branche ? h('span', null, kt.branche) : null,
        kt.ort ? h('span', null, kt.ort) : null,
        kt.quelle ? h('span', null, 'Quelle: ' + kt.quelle) : null),
      h('p', null, kt.einwilligung === 'ja'
        ? [tag('Einwilligung: ja', 'ok'), ' ', kt.einwilligung_nachweis || '']
        : [tag('keine Einwilligung', 'warn'), ' nur Brief, Besuch oder Empfehlung']),
      kt.naechster_schritt ? h('p', null, h('strong', null, 'Nächster Schritt: '), kt.naechster_schritt) : null,
      kt.notizen ? h('p', { class: 'text hilfe' }, kt.notizen) : null,
      h('div', { class: 'knopfreihe' }, statusTeile[0], nachrichtTeile[0], statusTeile[1], nachrichtTeile[1]));
  }

  function angebotFormKarte(kontakte, produkte) {
    const form = formular({ 'data-pruef': 'angebot-formular' }, [
      h('div', { class: 'felder-2' },
        feld('Kontakt (optional)', auswahl('kontakt_id', [['', '— ohne Kontakt —']].concat(kontakte.map(k => [k.id, k.firma])), '')),
        feld('Produkt (optional)', auswahl('produkt_id', [['', '— ohne Produkt —']].concat(produkte.map(p => [p.id, p.name || p.id])), ''))),
      h('div', { class: 'felder-2' },
        feld('Titel (optional)', eingabe('titel', { maxlength: 120 })),
        feld('Betrag in €', betragFeld('betrag', { required: true })),
        feld('Lieferzeit (optional)', eingabe('lieferzeit', { maxlength: 80, placeholder: 'z. B. 5 Werktage' }))),
      feld('Leistungen (optional)', textfeld('leistungen', { rows: 3, placeholder: 'Eine Leistung pro Zeile (höchstens 15)' })),
      h('details', { class: 'aufklapp klein' }, h('summary', null, 'Weitere Angaben für das Angebot (optional)'),
        h('div', { class: 'felder-2' },
          feld('Gültig bis', eingabe('gueltig_bis', { maxlength: 40, placeholder: 'z. B. 31.12.2026' })),
          feld('Hinweis zum Preis', eingabe('preis_hinweis', { maxlength: 160 })),
          feld('Anbieter (euer Firmenname)', eingabe('anbieter', { maxlength: 120 })),
          feld('Anschrift des Anbieters', eingabe('anbieter_anschrift', { maxlength: 200 })),
          feld('Kontakt des Anbieters', eingabe('anbieter_kontakt', { maxlength: 200, placeholder: 'Telefon oder E-Mail' })))),
      hinweis('Der Sales-Agent erstellt einen Entwurf. Preise und Termine erst zusagen, wenn ihr sie geprüft habt.'),
      h('div', { class: 'knopfreihe' }, absendeKnopf('Angebotsentwurf erstellen lassen')),
    ], async (w, f) => {
      const daten = ohneLeere(Object.assign({}, w, { betrag: betragPflicht(w.betrag), leistungen: leistungenAus(w.leistungen, 15) }));
      const r = await API.post('/api/angebote', daten);
      f.reset();
      auftragGemeldet(r, 'den Sales-Agenten');
    });
    return h('section', { class: 'karte' }, aufklapp('Neues Angebot', 'angebot-neu', false, form));
  }

  function angeboteKarte(angebote, kontakte, versand) {
    const firmen = {};
    kontakte.forEach(k => { firmen[k.id] = k.firma; });
    return karte('Angebote',
      h('p', { class: 'hilfe' }, 'Ablauf: Entwurf → von euch geprüft → Versand nur nach eurer Freigabe. „Angenommen“ ist noch keine Einnahme – gebucht wird erst unter „Finanzen“, wenn das Geld da ist.'),
      angebote.length ? h('ul', { class: 'liste' }, angebote.map(an => angebotZeile(an, firmen, (versand || {})[an.id]))) : leer('Noch keine Angebote.'));
  }

  function angebotInhalt(inhalt) {
    inhalt = alsWert(inhalt);
    if (!inhalt || typeof inhalt !== 'object' || Array.isArray(inhalt)) return wertAnzeige(inhalt);
    return kv([
      ['Nr.', inhalt.nr],
      ['Datum', inhalt.datum ? tagText(inhalt.datum) : null],
      ['Position', inhalt.position],
      ['Leistungen', Array.isArray(inhalt.leistungen) && inhalt.leistungen.length ? wertAnzeige(inhalt.leistungen) : null],
      ['Betrag', typeof inhalt.betrag_cent === 'number' ? euro(inhalt.betrag_cent) : null],
      ['Lieferzeit', inhalt.lieferzeit],
      ['Gültig bis', inhalt.gueltig_bis],
      ['Hinweis zum Preis', inhalt.preis_hinweis],
      ['Anbieter', inhalt.anbieter],
    ]);
  }

  function angebotZeile(an, firmen, versandFreigabe) {
    const ansehen = sichererLink(an.ansehen_url);
    const betragCent = typeof an.betrag_cent === 'number' ? an.betrag_cent : null;
    const wechsel = ANGEBOT_WECHSEL[an.status] || Object.keys(ANGEBOT_WAHL_TEXT).filter(s => s !== an.status);
    const statusTeile = wechsel.length ? umschaltBereich('Status ändern', 'zweit klein', zu => formular(null, [
      feld('Neuer Status', auswahl('status', wechsel.map(s => [s, ANGEBOT_WAHL_TEXT[s] || ANGEBOT_STATUS[s] || s]), wechsel[0])),
      h('p', { class: 'hilfe' }, '„Versendet“ nur wählen, wenn ihr das Angebot selbst verschickt habt.'),
      h('div', { class: 'knopfreihe' }, absendeKnopf('Speichern'), abbrechenKnopf(zu)),
    ], async (w) => {
      const r = await API.post('/api/angebote/' + enc(an.id) + '/status', { status: w.status });
      meldung('Status gespeichert.', 'ok');
      if (r && r.hinweis) meldung(r.hinweis, 'warn');
      neuLaden();
    })) : [null, null];
    return h('li', { class: 'eintrag', 'data-pruef': 'angebot' },
      h('div', { class: 'eintrag-kopf' }, h('span', { class: 'eintrag-titel' }, (an.inhalt && an.inhalt.titel) || an.titel || an.id),
        h('span', { class: 'chips' }, betragCent !== null ? h('span', { class: 'betrag' }, euro(betragCent)) : null, tag(ANGEBOT_STATUS[an.status] || an.status, ANGEBOT_TON[an.status]))),
      h('div', { class: 'meta' },
        an.kontakt_id ? h('span', null, 'für ' + (an.kontakt_firma || firmen[an.kontakt_id] || an.kontakt_id)) : null,
        an.erstellt ? h('span', null, 'erstellt ' + zeitText(an.erstellt)) : null),
      an.inhalt ? h('details', { class: 'aufklapp klein', 'data-schluessel': 'angebot-' + an.id }, h('summary', null, 'Inhalt ansehen'), angebotInhalt(an.inhalt)) : null,
      an.status === 'entwurf' ? h('p', { class: 'hilfe' }, 'Erst prüfen („Status ändern“ → Geprüft), dann kann der Versand zur Freigabe vorgelegt werden.') : null,
      versandStand(versandFreigabe),
      h('div', { class: 'knopfreihe' },
        ansehen ? h('a', { class: 'knopf klein', href: ansehen, target: '_blank', rel: 'noopener noreferrer' }, 'Ansehen') : null,
        versandFreigabe && versandFreigabe.status === 'offen' ? h('a', { class: 'knopf zweit klein', href: '#aufgaben' }, 'Zur Freigabe') : null,
        statusTeile[0],
        an.status === 'geprueft' && !versandFreigabe ? sicherheitsKnopf('Versand anfragen', 'Zur Freigabe vorlegen? Nochmal tippen', 'zweit klein', async () => {
          const r = await API.post('/api/angebote/' + enc(an.id) + '/versenden');
          meldung('Der Versand wartet gleich auf eure Freigabe unter „Aufgaben“.', 'warn');
          auftragGemeldet(r, 'den Sales-Agenten');
        }, { 'data-pruef': 'angebot-versenden' }) : null,
        statusTeile[1]));
  }

  /** Stand der Versand-Freigabe eines Angebots, falls es schon eine gibt. */
  function versandStand(f) {
    if (!f) return null;
    if (f.status === 'offen') return h('p', null, tag('Versand wartet auf eure Freigabe', 'warn'));
    if (f.status === 'abgelehnt') return h('p', null, tag('Versand abgelehnt (endgültig)', 'fehler'), ' ', h('span', { class: 'hilfe' }, 'am ' + zeitText(f.entschieden_zeit)));
    return h('p', null, tag('Versand erlaubt', 'ok'), ' ', h('span', { class: 'hilfe' }, 'Was danach passiert ist, steht in der Aufgabe unter „Aufgaben“.'));
  }

  // ===========================================================================
  // Bereich: Aufgaben
  // ===========================================================================
  async function ansichtAufgaben(z) {
    await agentenSicher();
    const [fg, liste] = await Promise.all([API.get('/api/freigaben'), API.get('/api/aufgaben')]);
    const alleFreigaben = fg.freigaben || [];
    const offen = alleFreigaben.filter(f => f.status === 'offen');
    z.append(h('section', { class: 'karte' + (offen.length ? ' hervorgehoben' : ''), 'data-pruef': 'freigaben' },
      h('h2', null, 'Freigaben', tag(String(offen.length) + ' offen', offen.length ? 'warn' : 'grau')),
      offen.length
        ? h('div', { class: 'liste' }, offen.map(f => freigabeKarte(f, true)))
        : leer('Keine offenen Freigaben. Sobald ein Agent etwas nach außen tun will, erscheint es hier.')));

    const aufgaben = liste.aufgaben || [];
    const rollenOptionen = [['', 'Alle Rollen']].concat(zustand.agenten.map(a => [a.rolle, a.name]));
    aufgaben.forEach(a => {
      if (!rollenOptionen.some(o => o[0] === a.verantwortlich)) rollenOptionen.push([a.verantwortlich, a.verantwortlich]);
    });
    const filterStatus = auswahl('status', [['', 'Alle'], ['offen', 'Alle offenen']].concat(STATUS_REIHE.map(s => [s, AUFGABEN_STATUS[s]])), zustand.filter.status);
    const filterRolle = auswahl('rolle', rollenOptionen, zustand.filter.rolle);
    const huelle = h('div');
    const zeichne = () => {
      const st = zustand.filter.status;
      const ro = zustand.filter.rolle;
      const treffer = aufgaben.filter(a => (!st || (st === 'offen' ? !ENDSTATUS.includes(a.status) : a.status === st)) && (!ro || a.verantwortlich === ro));
      ersetze(huelle, treffer.length
        ? h('ul', { class: 'liste' }, treffer.map(a => aufgabeZeile(a, false)))
        : leer(st === 'offen' ? 'Keine offenen Aufgaben.' : 'Keine Aufgaben für diese Auswahl.'));
    };
    filterStatus.addEventListener('change', () => { zustand.filter.status = filterStatus.value; zeichne(); });
    filterRolle.addEventListener('change', () => { zustand.filter.rolle = filterRolle.value; zeichne(); });
    zeichne();
    z.append(karte('Warteschlange und Verlauf',
      statusChips(liste.zahlen),
      h('div', { class: 'felder-2 filter' }, feld('Status', filterStatus), feld('Rolle', filterRolle)),
      aufgaben.length >= 300 ? h('p', { class: 'hilfe' }, 'Gezeigt werden höchstens 300 Aufgaben (offene zuerst).') : null,
      huelle));

    const entschieden = alleFreigaben.filter(f => f.status !== 'offen');
    z.append(karte('Entschiedene Freigaben',
      entschieden.length
        ? h('ul', { class: 'liste' }, entschieden.slice(0, 100).map(f => h('li', { class: 'eintrag' },
          h('div', { class: 'eintrag-kopf' }, h('span', { class: 'eintrag-titel' }, aktionText(f.aktion)), tag(FREIGABE_STATUS[f.status] || f.status, FREIGABE_TON[f.status])),
          h('div', { class: 'meta' },
            h('span', null, 'Ziel: ' + f.ziel),
            h('span', null, 'von ' + agentName(f.agent)),
            f.entschieden_zeit ? h('span', null, 'entschieden ' + zeitText(f.entschieden_zeit)) : null),
          f.notiz ? h('p', { class: 'text hilfe' }, 'Notiz: ' + f.notiz) : null)))
        : leer('Noch keine Entscheidungen.')));
  }

  // ===========================================================================
  // Bereich: Einstellungen
  // ===========================================================================
  async function ansichtEinstellungen(z) {
    const e = await API.get('/api/einstellungen');
    zustand.katalog = e.aktionen || {};
    z.append(einstellungenKarte(e));
    z.append(katalogKarte(e.aktionen || {}));
    z.append(sicherungKarte(e.sicherungen || []));
    z.append(await protokollKarte());
    z.append(modellaufrufeKarte(e.modellaufrufe || []));
  }

  function centAus(text, name) {
    const t = String(text || '').trim();
    if (t === '' ) throw new ApiFehler(0, name + ': bitte einen Betrag eingeben.');
    const n = betragNormal(t);
    if (n === null) throw new ApiFehler(0, name + ': bitte als Euro-Betrag eingeben, z. B. 3,00.');
    return Math.round(parseFloat(n) * 100);
  }
  function ganzAus(text, name, min, max) {
    if (!/^\d+$/.test(String(text || '').trim())) throw new ApiFehler(0, name + ': bitte eine ganze Zahl eingeben.');
    const n = parseInt(text, 10);
    if (n < min || n > max) throw new ApiFehler(0, name + ': erlaubt sind ' + min + ' bis ' + max + '.');
    return n;
  }

  function einstellungenKarte(e) {
    const w = e.werte || {};
    const anbieter = e.anbieter || {};
    const modell = e.modell || {};
    const anbieterGruppe = h('fieldset', { class: 'auswahlgruppe' }, h('legend', null, 'Modell für die Agenten'),
      Object.keys(anbieter).map(id => {
        const info = anbieter[id] || {};
        const waehlbar = id === 'keiner' || id === 'ollama';
        const radio = h('input', { type: 'radio', name: 'modell_anbieter', value: id, checked: w.modell_anbieter === id, disabled: !waehlbar, id: 'anbieter-' + id });
        return h('label', { class: 'option' + (waehlbar ? '' : ' gesperrt'), for: 'anbieter-' + id }, radio,
          h('span', null,
            h('strong', null, info.name || id),
            h('span', { class: 'hilfe' }, 'Kosten: ' + (info.kosten || '—')),
            h('span', { class: 'hilfe' }, info.status || ''),
            waehlbar ? null : h('span', null, tag('nicht angebunden', 'grau'))));
      }));
    const kostenSchalter = h('input', { type: 'checkbox', name: 'kostenpflichtig_erlaubt', checked: !!w.kostenpflichtig_erlaubt, id: 'kostenpflichtig' });
    const warnung = hinweis('Achtung: Damit sind kostenpflichtige Aktionen grundsätzlich möglich. Jede einzelne braucht trotzdem eure Freigabe. Empfehlung: aus lassen.', 'warn');
    warnung.hidden = !kostenSchalter.checked;
    kostenSchalter.addEventListener('change', () => { warnung.hidden = !kostenSchalter.checked; });

    const form = formular({ 'data-pruef': 'einstellungen-formular' }, [
      anbieterGruppe,
      h('div', { class: 'felder-2' },
        feld('Lokales Modell (Ollama)', eingabe('ollama_modell', { value: w.ollama_modell || '', maxlength: 60 }), 'Nur wirksam, wenn Ollama auf diesem Rechner installiert ist.'),
        feld('Höchstens Modellaufrufe pro Tag', zahlFeld('modell_max_aufrufe_tag', { value: w.modell_max_aufrufe_tag, min: 0, max: 1000 }),
          'Heute: ' + zahl(modell.aufrufe_heute) + ' Aufrufe.')),
      h('h3', null, 'Kosten'),
      h('label', { class: 'schalter', for: 'kostenpflichtig' }, kostenSchalter,
        h('span', null, h('strong', null, 'Kostenpflichtige Aktionen zulassen'), h('br'), h('span', { class: 'hilfe' }, 'Standard: aus. Kostenpflichtige Dienste sind dann komplett gesperrt.'))),
      warnung,
      h('p', { class: 'hilfe' }, 'Ausgabengrenzen legt ihr als Budgets fest – unter „Finanzen“ (real) und „Wallet“ (Simulation).'),
      h('h3', null, 'Betrieb'),
      h('div', { class: 'felder-3' },
        feld('Gleichzeitig arbeitende Agenten', zahlFeld('max_parallel', { value: w.max_parallel, min: 1, max: 8 }), 'Wirkt erst nach einem Neustart.'),
        feld('Wallet-Warnschwelle in €', betragFeld('wallet_warnschwelle', { value: euro(w.wallet_warnschwelle_cent).replace(/\s*€/, '').replace(/ /g, '') }), 'Warnung, wenn das simulierte Guthaben darunter fällt.'),
        feld('Sicherungen behalten', zahlFeld('sicherung_behalten', { value: w.sicherung_behalten, min: 1, max: 365 }), 'Anzahl der neuesten Sicherungen.')),
      h('div', { class: 'knopfreihe' }, absendeKnopf('Einstellungen speichern', { 'data-pruef': 'einstellungen-speichern' })),
    ], async (werte) => {
      const neu = {
        modell_anbieter: werte.modell_anbieter || w.modell_anbieter,
        ollama_modell: werte.ollama_modell,
        modell_max_aufrufe_tag: ganzAus(werte.modell_max_aufrufe_tag, 'Modellaufrufe pro Tag', 0, 1000),
        kostenpflichtig_erlaubt: !!werte.kostenpflichtig_erlaubt,
        max_parallel: ganzAus(werte.max_parallel, 'Gleichzeitig arbeitende Agenten', 1, 8),
        wallet_warnschwelle_cent: werte.wallet_warnschwelle === '0' ? 0 : centAus(werte.wallet_warnschwelle, 'Wallet-Warnschwelle'),
        sicherung_behalten: ganzAus(werte.sicherung_behalten, 'Sicherungen behalten', 1, 365),
      };
      const geaendert = Object.keys(neu).filter(k => JSON.stringify(neu[k]) !== JSON.stringify(w[k]));
      if (!geaendert.length) {
        meldung('Nichts geändert.', 'info');
        return;
      }
      for (const k of geaendert) {
        await API.post('/api/einstellungen', { schluessel: k, wert: neu[k] });
      }
      meldung('Gespeichert: ' + geaendert.length + ' Einstellung(en).' + (geaendert.includes('max_parallel') ? ' Die Anzahl der Agenten wirkt nach einem Neustart.' : ''), 'ok');
      neuLaden();
    });
    return karte('Modellzugang, Kosten und Betrieb',
      kv([['Modell gerade', (modell.anbieter_info && modell.anbieter_info.name) || modell.anbieter], ['Aufrufe heute', zahl(modell.aufrufe_heute) + ' von ' + zahl(modell.limit_tag)]]),
      h('div', { class: 'trenner' }),
      form);
  }

  function katalogKarte(aktionen) {
    const gruppen = { auto: [], freigabe: [], verboten: [] };
    Object.keys(aktionen).forEach(name => {
      const a = aktionen[name];
      (gruppen[a.klasse] || (gruppen[a.klasse] = [])).push([name, a.beschreibung]);
    });
    return karte('Berechtigungen (Aktionskatalog)',
      h('p', { class: 'hilfe' }, 'Nur zur Ansicht. Die Regeln stehen im Code; unbekannte Aktionen gelten immer als verboten.'),
      Object.keys(gruppen).filter(k => gruppen[k].length).map(k =>
        h('details', { class: 'aufklapp', 'data-schluessel': 'katalog-' + k },
          h('summary', null, tag(KLASSE_TEXT[k] || k, KLASSE_TON[k]), ' ' + gruppen[k].length + ' Aktionen'),
          h('ul', { class: 'liste' }, gruppen[k].map(([name, text]) => h('li', { class: 'eintrag' },
            h('div', null, text),
            h('div', { class: 'meta' }, h('code', null, name))))))));
  }

  function sicherungKarte(sicherungen) {
    return karte('Sicherung und Export',
      h('div', { class: 'knopfreihe' },
        aktionsKnopf('Sicherung jetzt erstellen', '', async () => {
          const r = await API.post('/api/sicherung');
          meldung('Sicherung erstellt: ' + r.datei, 'ok');
          neuLaden();
        }, { 'data-pruef': 'sicherung-jetzt' }),
        aktionsKnopf('Daten exportieren (JSON)', 'zweit', async () => {
          const r = await API.post('/api/export');
          meldung('Export gespeichert im Ordner autonomous/daten/export/: ' + r.datei, 'ok');
        })),
      h('p', { class: 'hilfe' }, 'Herunterladen über die Oberfläche: ', tag('noch nicht verfügbar', 'grau'), ' Die Dateien liegen im Ordner autonomous/daten/.'),
      h('p', { class: 'hilfe' }, 'Wiederherstellen: ', tag('in der Oberfläche noch nicht verfügbar', 'grau'), ' Nur bei gestopptem System im Terminal: python3 -m autonomous wiederherstellen DATEINAME'),
      h('h3', null, 'Vorhandene Sicherungen'),
      sicherungen.length
        ? h('ul', { class: 'liste' }, sicherungen.map(s => h('li', { class: 'eintrag' },
          h('div', { class: 'eintrag-kopf' }, h('span', { class: 'eintrag-titel' }, sicherungText(s.datei)), h('span', { class: 'meta' }, zahl(Math.round((s.groesse || 0) / 1024)) + ' KB')),
          h('div', { class: 'meta' }, h('code', null, s.datei)))))
        : leer('Noch keine Sicherung vorhanden.'));
  }

  async function protokollKarte() {
    const huelle = h('div');
    const filter = auswahl('ebene', EBENEN, zustand.protokollEbene);
    let anzahl = 20;
    const laden = async () => {
      const daten = await API.get('/api/protokoll' + (zustand.protokollEbene ? '?ebene=' + enc(zustand.protokollEbene) : ''));
      const eintraege = daten.eintraege || [];
      const zeichne = () => {
        ersetze(huelle, eintraege.length
          ? [h('ul', { class: 'liste' }, eintraege.slice(0, anzahl).map(p => h('li', { class: 'eintrag' },
            h('div', { class: 'eintrag-kopf' }, h('span', { class: 'eintrag-titel' }, p.ereignis), tag(p.ebene, EBENE_TON[p.ebene])),
            h('div', { class: 'meta' }, zeitText(p.zeit) + ' · ' + p.quelle),
            p.details ? h('details', { class: 'aufklapp klein' }, h('summary', null, 'Details'), wertAnzeige(alsWert(p.details))) : null))),
          eintraege.length > anzahl ? h('div', { class: 'knopfreihe' }, h('button', {
            type: 'button', class: 'knopf zweit klein', onclick: () => { anzahl += 30; zeichne(); },
          }, 'Weitere zeigen')) : null]
          : leer('Keine Einträge.'));
      };
      zeichne();
    };
    filter.addEventListener('change', async () => {
      zustand.protokollEbene = filter.value;
      anzahl = 20;
      try { await laden(); } catch (f) { meldung(fehlerText(f), 'fehler'); }
    });
    await laden();
    return karte('Protokoll', h('p', { class: 'hilfe' }, 'Fehler und kritische Aktionen – ohne Passwörter oder Schlüssel.'),
      h('div', { class: 'filter' }, feld('Ebene', filter)), huelle);
  }

  function modellaufrufeKarte(aufrufe) {
    return karte('Modellaufrufe',
      aufrufe.length
        ? h('ul', { class: 'liste' }, aufrufe.map(m => h('li', { class: 'eintrag' },
          h('div', { class: 'eintrag-kopf' }, h('span', { class: 'eintrag-titel' }, m.anbieter + ' · ' + m.modell), tag(m.ergebnis, m.ergebnis === 'ok' ? 'ok' : 'warn')),
          h('div', { class: 'meta' }, zeitText(m.zeit) + ' · ' + agentName(m.agent) + ' · Kosten ' + euro(m.kosten_cent)))))
        : leer('Noch keine Modellaufrufe.'));
  }

  // ===========================================================================
  // Navigation und Ablauf
  // ===========================================================================
  const BEREICHE = [
    { id: 'dashboard', titel: 'Dashboard', kurz: 'Start', icon: 'dashboard', render: ansichtDashboard },
    { id: 'ceo', titel: 'CEO-Zentrale', kurz: 'CEO', icon: 'ceo', render: ansichtCeo },
    { id: 'agenten', titel: 'Agenten', kurz: 'Agenten', icon: 'agenten', render: ansichtAgenten },
    { id: 'wallet', titel: 'Wallet', kurz: 'Wallet', icon: 'wallet', render: ansichtWallet },
    { id: 'finanzen', titel: 'Finanzen', kurz: 'Finanzen', icon: 'finanzen', render: ansichtFinanzen },
    { id: 'produkte', titel: 'Produkte', kurz: 'Produkte', icon: 'produkte', render: ansichtProdukte },
    { id: 'vertrieb', titel: 'Vertrieb', kurz: 'Vertrieb', icon: 'vertrieb', render: ansichtVertrieb },
    { id: 'aufgaben', titel: 'Aufgaben', kurz: 'Aufgaben', icon: 'aufgaben', render: ansichtAufgaben },
    { id: 'einstellungen', titel: 'Einstellungen', kurz: 'Einstellungen', icon: 'einstellungen', render: ansichtEinstellungen },
  ];
  const UNTEN = ['dashboard', 'aufgaben', 'produkte', 'vertrieb'];

  function zaehlerEl() {
    return h('span', { class: 'zaehler', 'data-zaehler': 'freigaben', hidden: true, title: 'offene Freigaben' });
  }

  function baueNavigation() {
    const seite = document.getElementById('nav-seite');
    const unten = document.getElementById('nav-unten');
    const mehr = document.getElementById('nav-mehr');
    BEREICHE.forEach(b => {
      seite.appendChild(h('a', { href: '#' + b.id, class: 'nav-link', 'data-nav': b.id },
        icon(b.icon), h('span', null, b.titel), b.id === 'aufgaben' ? zaehlerEl() : null));
      mehr.appendChild(h('a', { href: '#' + b.id, class: 'blatt-link', 'data-nav': b.id },
        icon(b.icon), h('span', null, b.titel), b.id === 'aufgaben' ? zaehlerEl() : null));
    });
    UNTEN.forEach(id => {
      const b = BEREICHE.find(x => x.id === id);
      unten.appendChild(h('a', { href: '#' + b.id, class: 'unten-link', 'data-nav': b.id },
        h('span', { class: 'icon-huelle' }, icon(b.icon), b.id === 'aufgaben' ? zaehlerEl() : null),
        h('span', null, b.kurz)));
    });
    const mehrKnopf = h('button', {
      type: 'button', class: 'unten-link', id: 'mehr-auf', 'aria-haspopup': 'dialog', 'aria-expanded': 'false', 'aria-controls': 'mehr-blatt',
    }, h('span', { class: 'icon-huelle' }, icon('mehr')), h('span', null, 'Mehr'));
    unten.appendChild(mehrKnopf);

    const blatt = document.getElementById('mehr-blatt');
    mehrKnopf.addEventListener('click', () => {
      blatt.hidden = false;
      mehrKnopf.setAttribute('aria-expanded', 'true');
      const aktiv = blatt.querySelector('[aria-current="page"]') || blatt.querySelector('a');
      if (aktiv) aktiv.focus();
    });
    document.getElementById('mehr-zu').addEventListener('click', () => schliesseMehr(true));
    blatt.addEventListener('click', (e) => { if (e.target === blatt) schliesseMehr(true); });
    mehr.addEventListener('click', (e) => { if (e.target.closest('a')) schliesseMehr(false); });
    document.addEventListener('keydown', (e) => { if (e.key === 'Escape' && !blatt.hidden) schliesseMehr(true); });
  }

  function schliesseMehr(fokusZurueck) {
    const blatt = document.getElementById('mehr-blatt');
    if (blatt.hidden) return;
    blatt.hidden = true;
    const k = document.getElementById('mehr-auf');
    k.setAttribute('aria-expanded', 'false');
    if (fokusZurueck) k.focus();
  }

  function markiereNavigation(id) {
    document.querySelectorAll('[data-nav]').forEach(el => {
      if (el.dataset.nav === id) el.setAttribute('aria-current', 'page');
      else el.removeAttribute('aria-current');
    });
    const mehrKnopf = document.getElementById('mehr-auf');
    if (mehrKnopf) mehrKnopf.classList.toggle('aktiv', !UNTEN.includes(id));
  }

  function setzePille(art, text) {
    const pille = document.getElementById('systempille');
    pille.className = 'pille' + (art ? ' ' + art : '');
    pille.textContent = text;
  }

  function aktualisiereKopfMit(s) {
    if (!s || !zustand.angemeldet) return;
    const ok = s.betrieb === 'laeuft';
    setzePille(ok ? 'ok' : 'fehler', ok ? 'läuft' : 'gestört');
    const n = s.offene_freigaben || 0;
    document.querySelectorAll('[data-zaehler="freigaben"]').forEach(el => {
      el.textContent = String(n);
      el.hidden = !n;
    });
    document.getElementById('seitenleiste-fuss').replaceChildren(
      h('div', null, 'AUTONOMOUS ' + (s.version || '')),
      h('div', null, 'Python ' + (s.python || '?') + ' · ' + zahl(s.agenten) + ' Rollen'),
      h('div', null, 'Stand ' + zeitText(s.zeit)));
  }

  async function kopfAktualisieren() {
    try {
      aktualisiereKopfMit(await API.get('/api/status'));
    } catch (f) {
      // Die Pille zeigt den Zustand bereits an
    }
  }

  function zeigeAnmeldung() {
    if (!zustand.angemeldet) return;
    zustand.angemeldet = false;
    setzePille('fehler', 'nicht angemeldet');
    const main = document.getElementById('inhalt');
    main.dataset.status = 'anmeldung';
    main.replaceChildren(h('section', { class: 'karte anmeldung' },
      h('h2', null, 'Bitte über den Startlink öffnen'),
      h('p', null, 'Bitte über den Startlink öffnen (AUTONOMOUS-starten.command zeigt ihn). Aus Sicherheitsgründen braucht die Oberfläche einen Zugangsschlüssel – er steckt im Startlink.'),
      h('ol', null,
        h('li', null, 'Doppelklick auf „AUTONOMOUS-starten.command“ – das Fenster zeigt den Startlink.'),
        h('li', null, 'Den Link öffnen. Er beginnt mit http://127.0.0.1 und enthält „?k=“.'),
        h('li', null, 'Danach merkt sich dieser Browser den Zugang.')),
      h('p', { class: 'hilfe' }, 'Im Terminal geht es auch: python3 -m autonomous link')));
  }

  function fehlerKarte(f, nochmal) {
    return h('section', { class: 'karte' },
      h('h2', null, 'Das hat nicht geklappt', tag(f && f.status ? 'Fehler ' + f.status : 'Fehler', 'fehler')),
      h('p', { class: 'text' }, fehlerText(f)),
      h('div', { class: 'knopfreihe' }, h('button', { type: 'button', class: 'knopf', onclick: nochmal }, 'Erneut versuchen')));
  }

  function aktuelleId() {
    const id = (location.hash || '').replace(/^#/, '');
    return BEREICHE.some(b => b.id === id) ? id : 'dashboard';
  }

  async function zeige(id, optionen) {
    if (!zustand.angemeldet) return;
    const still = !!(optionen && optionen.still) && zustand.bereich === id;
    const bereich = BEREICHE.find(b => b.id === id) || BEREICHE[0];
    const nr = ++zustand.renderNr;
    const main = document.getElementById('inhalt');
    zustand.bereich = bereich.id;
    markiereNavigation(bereich.id);
    document.getElementById('seitentitel').textContent = bereich.titel;
    document.title = bereich.titel + ' · AUTONOMOUS';
    let offeneDetails = new Set();
    let eingaben = {};
    if (still) {
      offeneDetails = new Set(Array.from(main.querySelectorAll('details[data-schluessel]')).filter(d => d.open).map(d => d.dataset.schluessel));
      eingaben = eingabenMerken(main);
    } else {
      main.dataset.bereich = bereich.id;
      main.dataset.status = 'laedt';
      main.replaceChildren(h('p', { class: 'laedt', role: 'status' }, 'Lädt …'));
      window.scrollTo(0, 0);
    }
    const ziel = h('div', { class: 'ansicht' });
    try {
      await bereich.render(ziel);
      if (nr !== zustand.renderNr || !zustand.angemeldet) return;
      if (still) {
        ziel.querySelectorAll('details[data-schluessel]').forEach(d => {
          if (offeneDetails.has(d.dataset.schluessel)) d.open = true;
        });
        eingabenZurueck(ziel, eingaben);
      }
      main.replaceChildren(ziel);
      main.dataset.bereich = bereich.id;
      main.dataset.status = 'fertig';
    } catch (f) {
      if (nr !== zustand.renderNr || !zustand.angemeldet) return;
      if (still) return; // alter Inhalt bleibt stehen, die Pille zeigt den Zustand
      main.replaceChildren(fehlerKarte(f, () => zeige(bereich.id)));
      main.dataset.status = 'fehler';
    }
  }

  function neuLaden() {
    kopfAktualisieren();
    return zeige(zustand.bereich, { still: true });
  }

  /** Später aktualisieren – aber nur, wenn man noch im selben Bereich ist und gerade nichts eingibt. */
  function spaeterNeuLaden(ms) {
    const bereich = zustand.bereich;
    setTimeout(() => {
      if (zustand.bereich !== bereich || nutzerIstDran()) return;
      neuLaden();
    }, ms || 1500);
  }

  // Ungespeicherte Eingaben überstehen das Neuaufbauen einer Ansicht
  function formSchluessel(form) {
    return form.dataset.pruef || Array.from(form.elements).map(e => e.name).filter(Boolean).join(',');
  }
  function feldSchluessel(form, el) {
    return formSchluessel(form) + '|' + el.name + (el.type === 'radio' ? '|' + el.value : '');
  }
  function eingabenMerken(wurzel) {
    const gemerkt = {};
    wurzel.querySelectorAll('form').forEach(form => {
      if (form.closest('.inline-form')) return;
      Array.from(form.elements).forEach(el => {
        if (!el.name) return;
        let geaendert;
        if (el.type === 'checkbox' || el.type === 'radio') geaendert = el.checked !== el.defaultChecked;
        else if (el.tagName === 'SELECT') geaendert = Array.from(el.options).some(o => o.selected !== o.defaultSelected);
        else geaendert = el.value !== el.defaultValue;
        if (geaendert) gemerkt[feldSchluessel(form, el)] = (el.type === 'checkbox' || el.type === 'radio') ? el.checked : el.value;
      });
    });
    return gemerkt;
  }
  function eingabenZurueck(wurzel, gemerkt) {
    if (!Object.keys(gemerkt).length) return;
    wurzel.querySelectorAll('form').forEach(form => {
      if (form.closest('.inline-form')) return;
      // Erst Auswahlfelder (sie können weitere Felder neu aufbauen), dann der Rest
      for (const nurAuswahl of [true, false]) {
        Array.from(form.elements).forEach(el => {
          if (!el.name || (el.tagName === 'SELECT') !== nurAuswahl) return;
          const k = feldSchluessel(form, el);
          if (!(k in gemerkt)) return;
          if (el.type === 'checkbox' || el.type === 'radio') el.checked = gemerkt[k];
          else el.value = gemerkt[k];
          if (nurAuswahl) el.dispatchEvent(new Event('change'));
        });
      }
    });
  }

  /** Während jemand tippt oder eine Bestätigung offen ist, wird nicht neu aufgebaut. */
  function nutzerIstDran() {
    const main = document.getElementById('inhalt');
    const a = document.activeElement;
    if (a && main.contains(a) && /^(INPUT|TEXTAREA|SELECT)$/.test(a.tagName)) return true;
    if (main.querySelector('.knopf.bestaetigen')) return true;
    if (main.querySelector('.inline-form:not([hidden])')) return true;
    return false;
  }

  async function ladeGrunddaten() {
    const [ag, es, st] = await Promise.all([API.get('/api/agenten'), API.get('/api/einstellungen'), API.get('/api/status')]);
    merkeAgenten((ag.agenten || []).filter(a => a.rolle !== 'supervisor'));
    zustand.katalog = es.aktionen || {};
    aktualisiereKopfMit(st);
  }

  async function start() {
    baueNavigation();
    try {
      await ladeGrunddaten();
    } catch (f) {
      if (!zustand.angemeldet) return;
      // Server nicht erreichbar o. Ä.: zeige() meldet den Fehler mit „Erneut versuchen“
    }
    window.addEventListener('hashchange', () => {
      schliesseMehr(false);
      zeige(aktuelleId());
    });
    zeige(aktuelleId());

    // Dashboard: alle 5 Sekunden, nur wenn sichtbar
    setInterval(() => {
      if (document.visibilityState !== 'visible' || !zustand.angemeldet) return;
      const main = document.getElementById('inhalt');
      if (zustand.bereich === 'dashboard' && main.dataset.status === 'fertig' && !nutzerIstDran()) {
        zeige('dashboard', { still: true });
      }
    }, 5000);
    // Kopfzeile (Status, offene Freigaben) in den anderen Bereichen alle 15 Sekunden
    setInterval(() => {
      if (document.visibilityState !== 'visible' || !zustand.angemeldet || zustand.bereich === 'dashboard') return;
      kopfAktualisieren();
    }, 15000);
    document.addEventListener('visibilitychange', () => {
      if (document.visibilityState === 'visible' && zustand.angemeldet) kopfAktualisieren();
    });
  }

  document.addEventListener('DOMContentLoaded', start);
})();
