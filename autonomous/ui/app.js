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
  const KONTAKT_TON = { neu: 'grau', kontaktiert: 'blau', interessiert: 'akzent', angebot: 'blau', gewonnen: 'ok', verloren: 'grau' };
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
  function ebeneText(e) {
    const t = EBENEN.find(x => x[0] === e);
    return t ? t[1] : e;
  }
  const CEO_KNOPF = { tagesplan: 'Tagesplan erstellen', kennzahlen: 'Kennzahlen berechnen', chancen_bewerten: 'Geschäftschancen bewerten' };
  const AUSSCHREIBUNG_STATUS = {
    neu: 'Neu', interessant: 'Interessant', abgelehnt: 'Abgelehnt', vorbereitet: 'Mappe vorbereitet',
    abgegeben: 'Angebot abgegeben', gewonnen: 'Gewonnen', verloren: 'Verloren',
  };
  const AUSSCHREIBUNG_TON = {
    neu: 'grau', interessant: 'akzent', abgelehnt: 'grau', vorbereitet: 'blau', abgegeben: 'blau', gewonnen: 'ok', verloren: 'grau',
  };
  const AUSSCHREIBUNG_SCHRITT = 20;
  const SUCHLAUF_TEXT = { ok: 'ok', fehler: 'Fehler', gesperrt: 'gesperrt' };
  const SUCHLAUF_TON = { ok: 'ok', fehler: 'fehler', gesperrt: 'warn' };
  const NACHRICHT_ANGEBOT = [
    ['google_profil', 'Google-Profil-Paket (Standard)'], ['webseite', 'Webseite'], ['reinigung', 'Reinigung (fester Auftrag)'],
  ];
  // Anzeigetexte für Rückmeldungen – maßgeblich sind die Listen, die das Backend liefert
  const REAKTION_TEXT = { interessiert: 'interessiert', neutral: 'neutral / unentschieden', abgelehnt: 'abgelehnt', keine_antwort: 'keine Antwort' };
  const REAKTION_TON = { interessiert: 'ok', neutral: 'grau', abgelehnt: 'fehler', keine_antwort: 'grau' };
  const GRUND_BEI = ['abgelehnt', 'neutral']; // laut Backend: nur bei diesen Reaktionen ist ein Grund erlaubt
  const GRUND_TEXT = {
    preis: 'Preis zu hoch', kein_bedarf: 'kein Bedarf', spaeter: 'später wieder melden', hat_anbieter: 'hat schon einen Anbieter',
    vertrauen: 'kennt uns noch nicht / Vertrauen fehlt', leistung_unklar: 'Leistung unklar', sonstiges: 'Sonstiges',
  };
  const KANAL_TEXT = {
    gespraech: 'persönliches Gespräch', telefon: 'Telefon', brief: 'Brief', email: 'E-Mail', vor_ort: 'vor Ort', sonstiges: 'Sonstiges',
  };
  const ANGEBOTSART_TEXT = {
    google_profil: 'Google-Profil-Paket', webseite: 'Webseiten-Paket', reinigung: 'Reinigung (fester Auftrag)', sonstiges: 'Sonstiges',
  };

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
    ausschreibungFilter: { status: '', min: '60', alle: false },
    ausschreibungAnzahl: AUSSCHREIBUNG_SCHRITT,
    kalkPositionen: 1,
    kalkOffen: null,
    fokusStelle: null,
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
    let el;
    if (art === 'fehler') {
      // Fehler verschwinden nicht von selbst – wer kurz wegsieht, soll sie trotzdem lesen können
      el = h('div', { class: 'meldung fehler mit-zu', role: 'alert' }, h('span', null, text),
        h('button', { type: 'button', class: 'knopf zweit klein', onclick: () => el.remove() }, 'Schließen'));
    } else {
      el = h('div', { class: 'meldung ' + (art || 'info'), role: 'status' }, text);
      setTimeout(() => el.remove(), 5500);
    }
    box.appendChild(el);
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
  // Grobe Formatprüfung im Browser: nur Ziffern, Punkt, Komma, Leerzeichen (und €). Die genaue Prüfung macht
  // betragNormal()/zahlNormal() – das Muster verhindert nur, dass z. B. „vierhundert“ erst nach dem Absenden auffällt.
  const MUSTER_BETRAG = '[\\d\\s.,€]*\\d[\\d\\s.,€]*';
  const MUSTER_ZAHL = '[\\d\\s.,]*\\d[\\d\\s.,]*';
  function betragFeld(name, attrs) {
    return eingabe(name, Object.assign({ inputmode: 'decimal', placeholder: 'z. B. 12,50', maxlength: 20,
      pattern: MUSTER_BETRAG, title: 'Euro-Betrag, z. B. 12,50' }, attrs || {}));
  }
  function dezimalFeld(name, attrs) {
    return eingabe(name, Object.assign({ inputmode: 'decimal', maxlength: 20, pattern: MUSTER_ZAHL, title: 'Zahl, z. B. 12,5' }, attrs || {}));
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

  /** Merkt, in welcher Karte gerade gehandelt wird – nach dem Neuaufbau kehrt der Fokus dorthin zurück. */
  function merkeFokusStelle(el) {
    const karteEl = el && el.closest ? el.closest('section.karte') : null;
    if (!karteEl) return;
    const titel = karteEl.querySelector('h2');
    zustand.fokusStelle = { pruef: karteEl.dataset.pruef || null, titel: titel ? titel.textContent : null };
  }
  function fokusStelleWiederherstellen(main) {
    const stelle = zustand.fokusStelle;
    zustand.fokusStelle = null;
    if (!stelle) return;
    const aktiv = document.activeElement;
    if (aktiv && aktiv !== document.body && main.contains(aktiv)) return; // Fokus ist noch an einer sinnvollen Stelle
    const karten = Array.from(main.querySelectorAll('section.karte'));
    const treffer = karten.find(k => stelle.pruef && k.dataset.pruef === stelle.pruef)
      || karten.find(k => { const t = k.querySelector('h2'); return t && stelle.titel && t.textContent === stelle.titel; });
    const ueberschrift = treffer ? treffer.querySelector('h2') : null;
    if (ueberschrift) {
      ueberschrift.setAttribute('tabindex', '-1');
      ueberschrift.focus({ preventScroll: true });
    } else {
      main.focus({ preventScroll: true });
    }
  }

  function formular(attrs, inhalt, aktion) {
    const form = h('form', Object.assign({ class: 'formular' }, attrs || {}), inhalt);
    form.addEventListener('submit', async (e) => {
      e.preventDefault();
      merkeFokusStelle(form);
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
  /** Zahl wie „400“, „12,5“ oder „1.000“ (Tausenderpunkt) in eine eindeutige Form „1000“ / „12.5“ bringen. */
  function zahlNormal(text) {
    const t = String(text || '').replace(/\s/g, '');
    if (/^\d{1,3}(\.\d{3})+(,\d+)?$/.test(t)) return t.replace(/\./g, '').replace(',', '.');
    if (/^\d+(,\d+)?$/.test(t)) return t.replace(',', '.');
    if (/^\d+\.\d+$/.test(t)) return t;
    return null;
  }
  function zahlPflicht(text, name) {
    const n = zahlNormal(text);
    if (n === null) throw new ApiFehler(0, (name || 'Zahl') + ': bitte eine Zahl eingeben, z. B. 12,5.');
    return n;
  }
  /** Liste aus Text: getrennt durch Komma, Semikolon oder Zeilenumbruch; doppelte Einträge entfallen. */
  function listeAus(text, klein) {
    const teile = String(text || '').split(/[,;\n]+/).map(x => x.trim()).filter(Boolean).map(x => klein ? x.toLowerCase() : x);
    return teile.filter((x, i) => teile.indexOf(x) === i);
  }
  /** Cent als Eingabetext „35,00“. */
  function euroEingabe(cent) {
    return typeof cent === 'number' && isFinite(cent) ? (cent / 100).toFixed(2).replace('.', ',') : '';
  }
  /** Frist „2026-12-08 12:00“ als „08.12.2026, 12:00 Uhr“. */
  function fristText(frist) {
    const m = /^(\d{4})-(\d{2})-(\d{2})(?:[ T](\d{2}):(\d{2}))?/.exec(String(frist || ''));
    if (!m) return String(frist || '—');
    return m[3] + '.' + m[2] + '.' + m[1] + (m[4] ? ', ' + m[4] + ':' + m[5] + ' Uhr' : '');
  }
  function tageText(t) {
    if (typeof t !== 'number' || !isFinite(t)) return '';
    if (t < 0) return 'abgelaufen';
    if (t === 0) return 'heute';
    return t === 1 ? 'noch 1 Tag' : 'noch ' + t + ' Tage';
  }
  /** Auswahlliste aus Backend-Werten: Texte, [id, text] oder {id, name}. */
  function wahlListe(liste, texte) {
    if (!Array.isArray(liste)) return [];
    return liste.map(x => {
      if (Array.isArray(x)) return [String(x[0]), String(x[1] !== undefined && x[1] !== null ? x[1] : x[0])];
      if (x && typeof x === 'object') {
        const id = x.id || x.wert || x.name;
        return [String(id), String(x.text || x.titel || x.name || (texte && texte[id]) || id)];
      }
      return [String(x), (texte && texte[x]) || String(x).replace(/_/g, ' ')];
    }).filter(o => o[0] && o[0] !== 'undefined');
  }
  /** Auf das Ende einer Aufgabe warten (für kurze Aufträge wie eine Kalkulation). */
  async function aufgabeAbwarten(id, sekunden) {
    const ende = Date.now() + (sekunden || 15) * 1000;
    while (Date.now() < ende) {
      const a = await API.get('/api/aufgaben/' + enc(id));
      if (ENDSTATUS.includes(a.status) || a.status === 'wartet_auf_freigabe') return a;
      await new Promise(r => setTimeout(r, 500));
    }
    return null;
  }

  function aktionsKnopf(text, klasse, aktion, attrs) {
    const k = h('button', Object.assign({ type: 'button', class: 'knopf ' + (klasse || '') }, attrs || {}), text);
    k.addEventListener('click', async () => {
      merkeFokusStelle(k);
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
      merkeFokusStelle(k);
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
    const [d, aus, k, an, zi] = await Promise.all([API.get('/api/dashboard'), optional('/api/ausschreibungen?min_punkte=60'),
      optional('/api/kontakte'), optional('/api/angebote'), API.get('/api/ziele')]);
    const s = d.status || {};
    aktualisiereKopfMit(s);
    const freigaben = d.offene_freigaben || [];
    if (freigaben.length) {
      z.append(h('section', { class: 'karte hervorgehoben' },
        h('h2', null, 'Wartet auf eure Entscheidung', tag(String(freigaben.length), 'warn')),
        h('div', { class: 'liste' }, freigaben.map(f => freigabeKarte(f, false)))));
    }

    // Zuerst eure Aufträge: Kontakte, Angebote, Ausschreibungen, Ziele
    const kontakte = k.fehlt ? null : (k.kontakte || []);
    const angebote = an.fehlt ? null : (an.angebote || []);
    const ziele = zi.ziele || [];
    const interessiert = kontakte ? kontakte.filter(x => x.status === 'interessiert').length : 0;
    const offeneAngebote = angebote ? angebote.filter(x => ['entwurf', 'geprueft', 'versendet'].includes(x.status)).length : 0;
    const aktiveZiele = ziele.filter(x => x.status === 'aktiv').length;
    z.append(h('div', { class: 'raster', 'data-pruef': 'dash-vertrieb' },
      kontakte ? kachel('Kontakte', zahl(kontakte.length), '', 'davon interessiert: ' + zahl(interessiert), 'dash-kontakte')
        : kachel('Kontakte', 'nicht verfügbar', '', 'In dieser Version nicht eingebaut.', 'dash-kontakte'),
      angebote ? kachel('Offene Angebote', zahl(offeneAngebote), '', 'Entwurf, geprüft oder versendet – noch nicht entschieden', 'dash-angebote')
        : kachel('Offene Angebote', 'nicht verfügbar', '', 'In dieser Version nicht eingebaut.', 'dash-angebote'),
      ausschreibungKachel(aus),
      kachel('Aktive Ziele', zahl(aktiveZiele), '', aktiveZiele ? 'in der CEO-Zentrale' : 'Noch keine Ziele festgelegt', 'dash-ziele')));

    const schritte = (kontakte || []).filter(x => x.naechster_schritt && !['gewonnen', 'verloren'].includes(x.status))
      .sort((x, y) => String(y.aktualisiert || '').localeCompare(String(x.aktualisiert || ''))).slice(0, 5);
    z.append(h('section', { class: 'karte', 'data-pruef': 'naechste-schritte' },
      h('h2', null, 'Nächste Schritte'),
      schritte.length
        ? h('ul', { class: 'liste' }, schritte.map(x => h('li', { class: 'eintrag' },
          h('div', { class: 'eintrag-kopf' }, h('span', { class: 'eintrag-titel' }, x.firma), tag(KONTAKT_STATUS[x.status] || x.status, KONTAKT_TON[x.status])),
          h('div', { class: 'text' }, x.naechster_schritt))))
        : leer(kontakte && kontakte.length ? 'Bei keinem Kontakt ist ein nächster Schritt eingetragen.' : 'Noch keine Kontakte. Im Vertrieb den ersten eintragen.'),
      h('div', { class: 'knopfreihe' }, h('a', { href: '#vertrieb', class: 'knopf zweit klein' }, 'Zum Vertrieb'))));

    // Echtes Geld zuerst und groß; das simulierte Wallet klein daneben (nie zusammengerechnet)
    const w = d.wallet || {};
    const f = d.finanzen || {};
    z.append(h('div', { class: 'raster zwei' },
      h('section', { class: 'karte' },
        h('h2', null, 'Reale Finanzen', tag('REAL', 'ok')),
        h('div', { class: 'kachel-wert' }, f.saldo || euro(f.saldo_cent)),
        h('p', { class: 'hilfe' }, 'Saldo aus echten, geprüften Buchungen.'),
        kv([
          ['Einnahmen (verifiziert)', euro(f.einnahmen_verifiziert_cent)],
          ['Offene Forderungen', (f.offene_forderungen || euro(f.offene_forderungen_cent)) + ' (noch kein Geld)'],
        ]),
        h('div', { class: 'knopfreihe' }, h('a', { href: '#finanzen', class: 'knopf zweit klein' }, 'Zu den Finanzen'))),
      h('section', { class: 'karte' },
        h('h2', null, 'Internes Wallet', tag('SIMULATION', 'sim')),
        kv([['Simuliertes Guthaben', w.stand || euro(w.stand_cent)]]),
        h('p', { class: 'hilfe' }, 'Kein echtes Geld. Beeinflusst den Betrieb nicht.'),
        h('div', { class: 'knopfreihe' }, h('a', { href: '#wallet', class: 'knopf zweit klein' }, 'Zum Wallet')))));

    const aktiv = d.aktive_aufgaben || [];
    z.append(karte('Aktive Aufgaben',
      aktiv.length ? h('ul', { class: 'liste' }, aktiv.map(a => aufgabeZeile(a, true))) : leer('Gerade läuft nichts und nichts wartet in der Warteschlange.')));

    // Technik: eingeklappt – nur was nicht stimmt, steht zusätzlich oben
    const orch = s.orchestrator || {};
    const modell = s.modell || {};
    const zahlen = s.aufgaben || {};
    const erledigt = zahlen.abgeschlossen || 0;
    const gesamt = Object.keys(zahlen).filter(x => x !== 'abgebrochen').reduce((n, x) => n + (zahlen[x] || 0), 0);
    const betriebOk = s.betrieb === 'laeuft';
    const kBetrieb = () => kachel('Betrieb', betriebOk ? 'läuft' : (s.betrieb || 'unbekannt'), betriebOk ? 'ok' : 'fehler',
      'Datenbank ' + (s.datenbank && s.datenbank.ok ? 'in Ordnung' : 'gestört'), 'betrieb');
    const kFehler = () => kachel('Fehler (24 Std.)', zahl(s.fehler_24h), s.fehler_24h ? 'fehler' : '', 'laut Protokoll');
    const kSicherung = () => kachel('Letzte Sicherung', s.letzte_sicherung ? sicherungKurz(s.letzte_sicherung) : 'noch keine', s.letzte_sicherung ? '' : 'warn',
      s.letzte_sicherung ? sicherungText(s.letzte_sicherung) + ' · täglich, solange das System läuft' : 'täglich, solange das System läuft');
    const probleme = [];
    if (!betriebOk) probleme.push(kBetrieb());
    if (s.fehler_24h) probleme.push(kFehler());
    if (!s.letzte_sicherung) probleme.push(kSicherung());
    if (probleme.length) z.append(h('div', { class: 'raster', 'data-pruef': 'dash-probleme' }, probleme));

    const warnungen = (s.warnungen || []).map(t => h('li', { class: 'eintrag' }, h('span', { class: 'text' }, t)));
    const protokoll = (d.warnungen_protokoll || []).slice().sort((a, b) => (b.id || 0) - (a.id || 0)).slice(0, 8);
    z.append(h('section', { class: 'karte', 'data-pruef': 'dash-technik-karte' },
      h('h2', null, 'Technik und Sicherung'),
      aufklapp('Details anzeigen', 'dash-technik', false,
        h('div', { class: 'raster' },
          betriebOk ? kBetrieb() : null,
          kachel('Agenten-Arbeiter', orch.laeuft ? 'aktiv' : 'gestoppt', orch.laeuft ? 'ok' : 'warn',
            orch.laeuft ? (orch.beschaeftigt + ' von ' + orch.arbeiter + ' beschäftigt · ' + zahl(orch.bearbeitet_seit_start) + ' seit Start erledigt') : 'Aufgaben werden gerade nicht abgearbeitet.'),
          kachel('Erledigte Agenten-Aufgaben', zahl(erledigt) + ' von ' + zahl(gesamt), '', 'ohne abgebrochene'),
          s.fehler_24h ? null : kFehler(),
          s.letzte_sicherung ? kSicherung() : null,
          kachel('KI-Modell', modell.anbieter === 'ollama' ? 'Ollama' : 'kein Modell', '',
            modell.verfuegbar ? (zahl(modell.aufrufe_heute) + ' von ' + zahl(modell.limit_tag) + ' Aufrufen heute') : 'Alles läuft nach festen Regeln, ohne KI'),
          kachel('Laufzeit', dauerText(s.laufzeit_sekunden), '', 'Version ' + (s.version || '?'))),
        h('h3', null, 'Aufgaben nach Status'),
        statusChips(s.aufgaben),
        h('h3', null, 'Warnungen'),
        warnungen.length || protokoll.length
          ? h('ul', { class: 'liste' }, warnungen, protokoll.map(p => h('li', { class: 'eintrag' },
            h('div', { class: 'eintrag-kopf' }, h('span', { class: 'eintrag-titel' }, p.ereignis), tag(ebeneText(p.ebene), EBENE_TON[p.ebene])),
            h('div', { class: 'meta' }, zeitText(p.zeit) + ' · ' + p.quelle))))
          : leer('Keine Warnungen.'),
        h('div', { class: 'knopfreihe' }, h('a', { href: '#aufgaben', class: 'knopf zweit klein' }, 'Zu den Aufgaben')))));
  }

  /** Kachel aus echten Daten des Auftrags-Radars: neue passende Ausschreibungen und nächste Frist. */
  function ausschreibungKachel(aus) {
    if (!aus || aus.fehlt) return kachel('Ausschreibungen', 'nicht verfügbar', '', 'Das Auftrags-Radar ist in dieser Version nicht eingebaut.', 'ausschreibungen-kachel');
    const liste = aus.ausschreibungen || [];
    const neu = liste.filter(a => a.status === 'neu').length;
    const offen = liste.filter(a => ['neu', 'interessant', 'vorbereitet'].includes(a.status) && a.frist
      && typeof a.tage_bis_frist === 'number' && a.tage_bis_frist >= 0)
      .sort((x, y) => String(x.frist).localeCompare(String(y.frist)));
    const naechste = offen[0];
    const recherche = !!(aus.einstellungen && aus.einstellungen.internet_recherche_erlaubt);
    const zusatz = 'neu und passend (ab 60 Punkten) · '
      + (naechste ? 'nächste Frist ' + fristText(naechste.frist) + ' (' + tageText(naechste.tage_bis_frist) + ')' : 'keine offene Frist')
      + (recherche ? '' : ' · Internet-Recherche aus');
    const ton = naechste && naechste.tage_bis_frist <= 3 ? 'fehler' : (neu ? 'warn' : '');
    const k = kachel('Ausschreibungen', zahl(neu), ton, zusatz, 'ausschreibungen-kachel');
    k.append(h('a', { href: '#vertrieb', class: 'knopf zweit klein kachel-link' }, 'Ansehen'));
    return k;
  }

  // ===========================================================================
  // Bereich: CEO-Zentrale
  // ===========================================================================
  async function ansichtCeo(z) {
    await agentenSicher();
    const [zielDaten, ceo, research, gedaechtnis, mb, einst] = await Promise.all([
      API.get('/api/ziele'), API.get('/api/aufgaben?rolle=ceo'), API.get('/api/aufgaben?rolle=research'), API.get('/api/gedaechtnis'),
      optional('/api/research/marktberichte'), API.get('/api/einstellungen'),
    ]);
    const ceoAufgaben = ceo.aufgaben || [];
    const eintraege = gedaechtnis.eintraege || [];
    z.append(h('p', { class: 'einleitung' }, 'Ziele und Entscheidungen legt ihr fest. Der CEO-Agent plant und bewertet nur aus echten Daten – seine Ergebnisse sind Vorschläge.'));
    z.append(ceoAuftraege(ceoAufgaben));
    z.append(zieleKarte(zielDaten.ziele || []));
    z.append(tagesplanKarte(ceoAufgaben));
    z.append(chancenKarte(research.aufgaben || [], ceoAufgaben));
    z.append(marktberichtKarte(mb, einst, research.aufgaben || []));
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

  const MARKT_KENNZAHL = {
    ausschreibungen_ted_gesamt: 'Ausschreibungen (EU, TED)',
    ausschreibungen_ausgewertet: 'davon ausgewertet',
    zuschlaege_ted_gesamt: 'Zuschläge (EU, TED)',
    zuschlaege_ausgewertet: 'davon ausgewertet',
    wettbewerber_anzahl: 'Unternehmen mit Zuschlag',
    angebote_je_los_median: 'Angebote je Los (Median)',
    angebotsfrist_median_tage: 'Angebotsfrist in Tagen (Median)',
    gesammelte_ausschreibungen: 'Eure gesammelten Ausschreibungen',
  };
  const MARKT_ZEITRAUM = [['30', '30 Tage'], ['90', '90 Tage'], ['180', '180 Tage'], ['365', '1 Jahr'], ['730', '2 Jahre']];

  /** Marktbericht des Research-Agenten aus amtlichen Daten (PDF 0/5.2) – mit Quellen, ohne Schätzungen als Fakten. */
  function marktberichtKarte(mb, einst, researchAufgaben) {
    const titel = 'Marktbericht (Research-Agent)';
    if (!mb || mb.fehlt) return nichtVerfuegbar(titel, 'Der Marktbericht ist in dieser Version des Servers noch nicht eingebaut.');
    const rechercheAn = !!((einst && einst.werte) || {}).internet_recherche_erlaubt;
    const berichte = mb.berichte || [];
    const inArbeitListe = mb.in_arbeit || [];
    const fehler = researchAufgaben.filter(a => a.typ === 'marktbericht' && a.status === 'fehlgeschlagen')
      .sort((x, y) => String(y.aktualisiert || '').localeCompare(String(x.aktualisiert || '')))[0];
    if (inArbeitListe.length) spaeterNeuLaden(5000); // Fortschritt sichtbar, ohne dass jemand neu laden muss

    const form = formular({ 'data-pruef': 'marktbericht-formular' }, [
      feld('Zeitraum', auswahl('zeitraum_tage', MARKT_ZEITRAUM, '365')),
      h('div', { class: 'knopfreihe' }, absendeKnopf(inArbeitListe.length ? 'Wird erstellt …' : 'Marktbericht erstellen',
        { 'data-pruef': 'marktbericht-erstellen', disabled: inArbeitListe.length > 0 })),
    ], async (w) => {
      const r = await API.post('/api/research/marktbericht', { zeitraum_tage: w.zeitraum_tage });
      meldung('Auftrag an den Research-Agenten übergeben (Aufgabe ' + r.aufgabe_id + '). Das kann eine Minute dauern.', 'ok');
      neuLaden();
    });
    const einschalten = rechercheAn ? null : h('div', { 'data-pruef': 'marktbericht-recherche-aus' },
      h('p', { class: 'hilfe' }, tag('Internet-Recherche aus', 'warn'), ' Der Bericht braucht die öffentlichen Ausschreibungsdaten. Erst einschalten – '
        + 'dann liest der Research-Agent nur die freigegebenen öffentlichen Quellen (nur lesen).'),
      h('div', { class: 'knopfreihe' }, sicherheitsKnopf('Internet-Recherche einschalten', 'Wirklich einschalten? Nochmal tippen', 'zweit', async () => {
        await API.post('/api/einstellungen', { schluessel: 'internet_recherche_erlaubt', wert: true });
        meldung('Internet-Recherche ist jetzt an.', 'ok');
        neuLaden();
      }, { 'data-pruef': 'marktbericht-recherche-einschalten' })));

    const kennzahlen = k => kv(Object.keys(k || {}).map(n => [MARKT_KENNZAHL[n] || schluesselText(n), typeof k[n] === 'number' ? zahl(k[n]) : String(k[n])]));
    return h('section', { class: 'karte', 'data-pruef': 'marktbericht' },
      h('h2', null, titel, tag(zahl(berichte.length) + (berichte.length === 1 ? ' Bericht' : ' Berichte'), 'grau')),
      h('p', { class: 'hilfe' }, 'Der Research-Agent wertet amtliche Daten aus: EU-Ausschreibungen und Zuschläge (TED) und eure gesammelten Ausschreibungen. '
        + 'Jede Zahl mit Quelle; Annahmen sind gekennzeichnet. Ist ein lokales KI-Modell eingestellt, kommt eine gekennzeichnete, ungeprüfte KI-Zusammenfassung dazu.'),
      einschalten,
      einschalten ? h('div', { class: 'trenner' }) : null,
      form,
      inArbeitListe.length
        ? h('p', { 'data-pruef': 'marktbericht-laeuft' }, tag('Marktbericht wird erstellt …', 'blau'), ' Das kann eine Minute dauern – die Liste aktualisiert sich von selbst.')
        : null,
      fehler && !inArbeitListe.length ? h('p', { class: 'fehlertext' }, 'Letzter Versuch fehlgeschlagen: ' + (fehler.fehler || 'unbekannt')) : null,
      berichte.length
        ? h('ul', { class: 'liste', 'data-pruef': 'marktberichte-liste' }, berichte.slice(0, 5).map(b => {
          const url = sichererLink(b.bericht_url);
          return h('li', { class: 'eintrag', 'data-pruef': 'marktbericht-eintrag' },
            h('div', { class: 'eintrag-kopf' },
              h('span', { class: 'eintrag-titel' }, 'Marktbericht · ' + (b.zeitraum_tage ? zahl(b.zeitraum_tage) + ' Tage' : 'Zeitraum unbekannt')),
              b.ki_zusammenfassung_vorhanden ? tag('mit KI-Zusammenfassung (ungeprüft)', 'akzent') : tag('ohne KI', 'grau')),
            h('div', { class: 'meta' }, 'erstellt ' + zeitText(b.erstellt)),
            kennzahlen(b.kennzahlen),
            url ? h('div', { class: 'knopfreihe' },
              h('a', { class: 'knopf klein', href: url, target: '_blank', rel: 'noopener noreferrer', 'data-pruef': 'marktbericht-ansehen' }, 'Bericht ansehen')) : null);
        }))
        : leer(inArbeitListe.length ? 'Der erste Bericht entsteht gerade.' : 'Noch kein Marktbericht. Zeitraum wählen und „Marktbericht erstellen“ antippen.'));
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
    z.append(h('p', { class: 'einleitung' }, 'Der Product-Agent erstellt Dateien zur Prüfung. Veröffentlichen braucht euer Ja – ohne euer Ja geht nichts online.'));
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
    const [k, a, p, fg, aus, rm, einst, auf] = await Promise.all([
      optional('/api/kontakte'), optional('/api/angebote'), optional('/api/produkte'), API.get('/api/freigaben'),
      optional(ausschreibungsPfad()), optional('/api/rueckmeldungen'), API.get('/api/einstellungen'), API.get('/api/aufgaben'),
    ]);
    const aufgaben = auf.aufgaben || [];
    // Neueste Freigabe je Angebot (Ziel „angebot:<id>“), damit der Versand-Stand sichtbar ist
    const versand = {};
    (fg.freigaben || []).forEach(f => {
      const m = /^angebot:(.+)$/.exec(String(f.ziel || ''));
      if (!m) return;
      const alt = versand[m[1]];
      if (!alt || String(f.zeit) > String(alt.zeit)) versand[m[1]] = f;
    });
    const ausschreibungen = aus.fehlt
      ? nichtVerfuegbar('Öffentliche Ausschreibungen', 'Das Auftrags-Radar ist in dieser Version noch nicht eingebaut.')
      : ausschreibungenKarte(aus, aufgaben);
    const kontakte = k.fehlt ? [] : (k.kontakte || []);
    const rmListe = rm.fehlt ? null : rmListen(rm);
    let kontaktTeile;
    if (k.fehlt) {
      kontaktTeile = [nichtVerfuegbar('Kontakte und Kundenstatus', 'Die Vertriebs-Schnittstelle für Kontakte ist in dieser Version noch nicht eingebaut.')];
    } else {
      const stufen = normStufen(k.stufen);
      kontaktTeile = [pipelineKarte(kontakte, stufen), kontaktFormKarte(!kontakte.length), kontakteKarte(kontakte, stufen, rmListe)];
    }
    const angebotTeile = a.fehlt
      ? [nichtVerfuegbar('Angebote', 'Die Angebots-Schnittstelle ist in dieser Version noch nicht eingebaut.')]
      : [angebotFormKarte(kontakte, p.fehlt ? [] : (p.produkte || [])), angeboteKarte(a.angebote || [], kontakte, versand)];
    const kalkulation = kalkulationKarte(einst, aufgaben, kontakte);
    const rueckmeldungen = rueckmeldungenKarte(rm, rmListe, kontakte, a.fehlt ? [] : (a.angebote || []), aufgaben);

    // Sprungziele für die Sprungleiste (Knöpfe – „#…“ wählt hier den Bereich, nicht die Karte)
    sprungZiel(kontaktTeile[0], 'kontakte');
    sprungZiel(kalkulation, 'kalkulation');
    sprungZiel(angebotTeile[0], 'angebote');
    sprungZiel(rueckmeldungen, 'rueckmeldungen');
    sprungZiel(ausschreibungen, 'ausschreibungen');
    // Ausschreibungen nur dann zuerst, wenn die Recherche an ist oder es schon Treffer gibt
    const ausVorne = !aus.fehlt && (!!(aus.einstellungen || {}).internet_recherche_erlaubt || (aus.ausschreibungen || []).length > 0);
    const sprung = [['kontakte', 'Kontakte'], ['kalkulation', 'Preis rechnen'], ['angebote', 'Angebote'], ['rueckmeldungen', 'Rückmeldungen']];
    if (ausVorne) sprung.unshift(['ausschreibungen', 'Ausschreibungen']); else sprung.push(['ausschreibungen', 'Ausschreibungen']);
    z.append(sprungleiste(sprung));
    if (ausVorne) z.append(ausschreibungen);
    z.append(...kontaktTeile, kalkulation, ...angebotTeile, rueckmeldungen);
    if (!ausVorne) z.append(ausschreibungen);
  }

  function sprungZiel(el, id) {
    if (el) el.dataset.sprung = id;
    return el;
  }
  /** Kurzwahl zu den Karten eines langen Bereichs. */
  function sprungleiste(ziele) {
    return h('nav', { class: 'knopfreihe sprungleiste', 'aria-label': 'Springen zu', 'data-pruef': 'sprungleiste' },
      ziele.map(([id, text]) => h('button', {
        type: 'button', class: 'knopf zweit klein', 'data-sprung-zu': id,
        onclick: () => {
          const ziel = document.querySelector('#inhalt [data-sprung="' + id + '"]');
          if (!ziel) return;
          ziel.scrollIntoView({ block: 'start' });
          const ueberschrift = ziel.querySelector('h2, summary');
          if (ueberschrift) {
            if (ueberschrift.tagName === 'H2') ueberschrift.setAttribute('tabindex', '-1');
            ueberschrift.focus({ preventScroll: true });
          }
        },
      }, text)));
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
        feld('Einwilligung zu Werbung', auswahl('einwilligung', [['keine', 'keine'], ['ja', 'ja, liegt vor']], 'keine'),
          'Werbung per E-Mail oder Telefon braucht in der Regel eine Einwilligung (§ 7 UWG). Ohne Einwilligung lieber Brief, Besuch oder Empfehlung.'),
        feld('Nachweis der Einwilligung', eingabe('einwilligung_nachweis', { maxlength: 300 }),
          'Nur bei „ja“: wann, wie und von wem.')),
      feld('Nächster Schritt (optional)', eingabe('naechster_schritt', { maxlength: 300 })),
      feld('Notizen (optional)', textfeld('notizen', { maxlength: 2000 }),
        'Nur Firmendaten, die ihr für die Anfrage braucht – keine privaten Telefonnummern, keine Profile von Privatpersonen. '
        + 'AUTONOMOUS versendet nichts selbst; Kundenkontakt nur nach eurer Freigabe.'),
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

  function kontakteKarte(kontakte, stufen, rmListe) {
    return karte('Kontakte',
      kontakte.length ? h('ul', { class: 'liste' }, kontakte.map(kt => kontaktZeile(kt, stufen, rmListe))) : leer('Noch keine Kontakte.'));
  }

  function kontaktZeile(kt, stufen, rmListe) {
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
    const nachrichtTeile = umschaltBereich('Nachricht entwerfen', 'zweit klein', zu => formular({ 'data-pruef': 'nachricht-formular' }, [
      h('div', { class: 'felder-2' },
        feld('Worum geht es?', auswahl('angebot', NACHRICHT_ANGEBOT, 'google_profil')),
        feld('Anlass', eingabe('anlass', { required: true, maxlength: 200, placeholder: 'z. B. Nachfassen nach dem Besuch am Montag' }))),
      h('p', { class: 'hilfe' }, 'Der Sales-Agent erstellt nur einen Entwurf. Versendet wird nichts ohne eure Freigabe.'),
      h('div', { class: 'knopfreihe' }, absendeKnopf('Entwurf erstellen lassen', { 'data-pruef': 'nachricht-absenden' }), abbrechenKnopf(zu)),
    ], async (w) => {
      const r = await API.post('/api/vertrieb/nachricht', { kontakt_id: kt.id, anlass: w.anlass, angebot: w.angebot });
      auftragGemeldet(r, 'den Sales-Agenten');
    }));
    const rueckTeile = rmListe
      ? umschaltBereich('Rückmeldung erfassen', 'zweit klein', zu => rueckmeldungForm(rmListe, {}, kt, 'kontakt-rueckmeldung-formular', zu))
      : [null, null];
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
      h('div', { class: 'knopfreihe' }, statusTeile[0], nachrichtTeile[0], rueckTeile[0], statusTeile[1], nachrichtTeile[1], rueckTeile[1]));
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
    const monatlich = inhalt.art === 'reinigung_dauerauftrag' || inhalt.abrechnung === 'monatlich';
    const positionen = Array.isArray(inhalt.positionen) && inhalt.positionen.length
      ? h('ul', { class: 'mini-liste' }, inhalt.positionen.map(p => h('li', null,
        [p.bezeichnung, typeof p.flaeche_m2 === 'number' ? p.flaeche_m2.toLocaleString('de-DE') + ' m²' : null, p.turnus].filter(Boolean).join(' · '))))
      : null;
    return kv([
      ['Nr.', inhalt.nr],
      ['Datum', inhalt.datum ? tagText(inhalt.datum) : null],
      ['Art', monatlich ? 'Reinigung, fester Auftrag (monatliche Pauschale)' : null],
      ['Position', inhalt.position],
      ['Leistungsverzeichnis', positionen],
      ['Objekt', inhalt.objekt],
      ['Leistungen', Array.isArray(inhalt.leistungen) && inhalt.leistungen.length ? wertAnzeige(inhalt.leistungen) : null],
      ['Betrag', typeof inhalt.betrag_cent === 'number' ? euro(inhalt.betrag_cent) + (monatlich ? ' pro Monat (netto)' : '') : null],
      ['Preis stammt', inhalt.preis_quelle],
      ['Vertragsbeginn', inhalt.vertragsbeginn],
      ['Laufzeit', inhalt.laufzeit],
      ['Kündigungsfrist', inhalt.kuendigungsfrist],
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
        h('span', { class: 'chips' }, betragCent !== null ? h('span', { class: 'betrag' }, euro(betragCent) + (an.abrechnung === 'monatlich' ? ' / Monat' : '')) : null, tag(ANGEBOT_STATUS[an.status] || an.status, ANGEBOT_TON[an.status]))),
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
  // Vertrieb: Auftrags-Radar (öffentliche Ausschreibungen)
  // ===========================================================================
  function ausschreibungsPfad() {
    const f = zustand.ausschreibungFilter;
    const q = [];
    if (f.status) q.push('status=' + enc(f.status));
    if (f.min && f.min !== '0') q.push('min_punkte=' + enc(f.min));
    if (f.alle) q.push('alle=1');
    return '/api/ausschreibungen' + (q.length ? '?' + q.join('&') : '');
  }

  function punkteTag(p) {
    const n = typeof p === 'number' ? p : 0;
    return tag(zahl(n) + ' Punkte', n >= 80 ? 'ok' : n >= 60 ? 'akzent' : 'grau');
  }

  function fristTag(a) {
    if (!a.frist) return tag('Frist nicht angegeben', 'grau');
    const t = a.tage_bis_frist;
    const ton = typeof t !== 'number' || t < 0 ? 'grau' : t <= 3 ? 'fehler' : t <= 7 ? 'warn' : 'akzent';
    return h('span', { class: 'tag ' + ton, 'data-pruef': 'frist', 'data-tage': typeof t === 'number' ? String(t) : '' },
      'Frist ' + fristText(a.frist) + (typeof t === 'number' ? ' – ' + tageText(t) : ''));
  }

  function ausschreibungenKarte(aus, aufgaben) {
    const f = zustand.ausschreibungFilter;
    const alle = aus.ausschreibungen || [];
    const liste = f.status ? alle : alle.filter(a => a.status !== 'abgelehnt');
    const e = aus.einstellungen || {};
    const stufen = Array.isArray(aus.stufen) && aus.stufen.length ? aus.stufen : Object.keys(AUSSCHREIBUNG_STATUS);
    const laufendeMappen = new Set(aufgaben
      .filter(a => a.typ === 'ausschreibung_vorbereiten' && !ENDSTATUS.includes(a.status))
      .map(a => a.eingabe && a.eingabe.ausschreibung_id).filter(Boolean));
    const sucheLaeuft = aufgaben.some(a => a.typ === 'ausschreibungen_suchen' && !ENDSTATUS.includes(a.status));

    const filterStatus = auswahl('filter_status', [['', 'Offen (ohne abgelehnte)']].concat(stufen.map(s => [s, AUSSCHREIBUNG_STATUS[s] || s])),
      f.status, { 'data-pruef': 'ausschreibungen-filter-status' });
    const filterMin = auswahl('filter_min', [['0', 'alle Punktzahlen'], ['40', 'ab 40 Punkten'], ['60', 'ab 60 Punkten (passend)'], ['80', 'ab 80 Punkten']],
      f.min, { 'data-pruef': 'ausschreibungen-filter-min' });
    const abgelaufen = h('input', { type: 'checkbox', id: 'filter-abgelaufen', checked: !!f.alle, 'data-pruef': 'ausschreibungen-filter-alle' });
    const filterNeu = () => {
      zustand.ausschreibungFilter = { status: filterStatus.value, min: filterMin.value, alle: abgelaufen.checked };
      zustand.ausschreibungAnzahl = AUSSCHREIBUNG_SCHRITT;
      neuLaden();
    };
    [filterStatus, filterMin, abgelaufen].forEach(el => el.addEventListener('change', filterNeu));

    const rechercheAn = !!e.internet_recherche_erlaubt;
    // Ist die Recherche aus, führt „Suchen“ sicher in eine Fehlermeldung – darum steht dann „Einschalten“ da
    const hauptKnopf = rechercheAn
      ? aktionsKnopf(sucheLaeuft ? 'Suche läuft …' : 'Jetzt suchen', '', async () => {
        const r = await API.post('/api/ausschreibungen/suchen');
        if (r && r.hinweis) meldung(r.hinweis, 'info');
        auftragGemeldet(r, 'den Akquise-Agenten');
      }, { 'data-pruef': 'ausschreibungen-suchen', disabled: sucheLaeuft })
      : sicherheitsKnopf('Internet-Recherche einschalten', 'Wirklich einschalten? Nochmal tippen', '', async () => {
        await API.post('/api/einstellungen', { schluessel: 'internet_recherche_erlaubt', wert: true });
        meldung('Internet-Recherche ist jetzt an. Die Agenten lesen nur die freigegebenen öffentlichen Ausschreibungsseiten.', 'ok');
        neuLaden();
      }, { 'data-pruef': 'recherche-einschalten' });

    const rechercheStand = rechercheAn
      ? h('p', { class: 'hilfe', 'data-pruef': 'recherche-an' }, tag('Internet-Recherche an', 'ok'), ' ',
        e.auftragssuche_taeglich ? 'Die Agenten suchen zusätzlich einmal täglich selbstständig.' : 'Tägliche Suche ist aus – gesucht wird nur auf Knopfdruck.')
      : h('p', { class: 'hilfe', 'data-pruef': 'recherche-aus' }, tag('Internet-Recherche aus', 'warn'), ' ',
        'Erst nach dem Einschalten dürfen die Agenten die öffentlichen Ausschreibungsseiten lesen (nur lesen). Weitere Einstellungen: ',
        h('a', { href: '#einstellungen' }, 'Einstellungen → Auftragssuche'), '.');
    const mitListe = rechercheAn || alle.length > 0;

    const anzahl = zustand.ausschreibungAnzahl;
    return h('section', { class: 'karte', 'data-pruef': 'ausschreibungen' },
      h('h2', null, 'Öffentliche Ausschreibungen', tag(zahl(liste.length) + ' Treffer', 'grau')),
      h('p', { class: 'hilfe' }, 'Der Akquise-Agent sucht in TED (EU-Amtsblatt), auf service.bund.de und dem Vergabemarktplatz NRW, '
        + 'bewertet jede Ausschreibung nachvollziehbar mit Punkten und erstellt auf Wunsch eine Bewerbungsmappe. '
        + 'AUTONOMOUS gibt keine Angebote ab – Abgabe macht ihr selbst auf der Vergabeplattform.'),
      rechercheStand,
      h('div', { class: 'knopfreihe' }, hauptKnopf),
      mitListe ? suchlaeufeAnzeige(aus.letzte_suche || []) : null,
      mitListe ? h('div', { class: 'felder-3 filter' },
        feld('Status', filterStatus),
        feld('Punkte', filterMin),
        h('label', { class: 'schalter filter-schalter', for: 'filter-abgelaufen' }, abgelaufen, h('span', null, 'Abgelaufene Fristen zeigen'))) : null,
      liste.length
        ? h('ul', { class: 'liste', 'data-pruef': 'ausschreibungen-liste' },
          liste.slice(0, anzahl).map(a => ausschreibungZeile(a, stufen, laufendeMappen.has(a.id))))
        : leer(alle.length ? 'Keine Treffer mit diesem Filter.'
          : 'Noch keine Ausschreibungen gespeichert. ' + (rechercheAn ? 'Mit „Jetzt suchen“ starten.' : 'Mit „Internet-Recherche einschalten“ beginnen.')),
      liste.length > anzahl
        ? h('div', { class: 'knopfreihe' }, h('button', {
          type: 'button', class: 'knopf zweit', 'data-pruef': 'ausschreibungen-mehr',
          onclick: () => { zustand.ausschreibungAnzahl += AUSSCHREIBUNG_SCHRITT; neuLaden(); },
        }, 'Weitere anzeigen (' + zahl(liste.length - anzahl) + ')'))
        : null);
  }

  function suchlaeufeAnzeige(laeufe) {
    if (!laeufe.length) return h('p', { class: 'hilfe', 'data-pruef': 'suchlaeufe' }, 'Noch keine Suche gelaufen.');
    return h('div', { 'data-pruef': 'suchlaeufe' },
      h('h3', null, 'Letzte Suche je Quelle'),
      h('ul', { class: 'liste' }, laeufe.map(s => h('li', { class: 'eintrag' },
        h('div', { class: 'eintrag-kopf' }, h('span', { class: 'eintrag-titel' }, s.quelle_name || s.quelle),
          tag(SUCHLAUF_TEXT[s.ergebnis] || s.ergebnis, SUCHLAUF_TON[s.ergebnis] || 'grau')),
        h('div', { class: 'meta' },
          h('span', null, zeitText(s.zeit)),
          h('span', null, 'gefunden ' + zahl(s.gefunden)),
          h('span', null, 'neu ' + zahl(s.neu)),
          h('span', null, 'passend ' + zahl(s.passend))),
        s.meldung ? h('p', { class: 'hilfe text' }, s.meldung) : null))));
  }

  function ausschreibungZeile(a, stufen, mappeLaeuft) {
    const link = sichererLink(a.link);
    const mappe = sichererLink(a.unterlagen_url);
    const statusSetzen = async (status, notiz, mitNotiz) => {
      const daten = { status: status };
      if (mitNotiz) daten.notiz = notiz || '';
      const r = await API.post('/api/ausschreibungen/' + enc(a.id) + '/status', daten);
      meldung('Status gespeichert: ' + (AUSSCHREIBUNG_STATUS[status] || status) + '.', 'ok');
      if (r && r.hinweis) meldung(r.hinweis, 'warn');
      neuLaden();
    };
    const wechsel = stufen.filter(s => s !== a.status);
    const statusTeile = umschaltBereich('Status ändern', 'zweit klein', zu => formular(null, [
      h('div', { class: 'felder-2' },
        feld('Neuer Status', auswahl('status', wechsel.map(s => [s, AUSSCHREIBUNG_STATUS[s] || s]), wechsel[0])),
        feld('Notiz (optional)', eingabe('notiz', { maxlength: 1000, value: a.notiz || '' }))),
      h('p', { class: 'hilfe' }, '„Angebot abgegeben“ nur wählen, wenn ihr selbst auf der Vergabeplattform abgegeben habt. „Gewonnen“ ist noch keine Einnahme.'),
      h('div', { class: 'knopfreihe' }, absendeKnopf('Speichern'), abbrechenKnopf(zu)),
    ], async (w) => { await statusSetzen(w.status, w.notiz, true); }));
    const endgueltig = ['abgelehnt', 'gewonnen', 'verloren'].includes(a.status);
    return h('li', { class: 'eintrag', 'data-pruef': 'ausschreibung', 'data-id': a.id },
      h('div', { class: 'eintrag-kopf' }, h('span', { class: 'eintrag-titel' }, a.titel),
        h('span', { class: 'chips' }, punkteTag(a.punkte), tag(AUSSCHREIBUNG_STATUS[a.status] || a.status, AUSSCHREIBUNG_TON[a.status]))),
      h('p', { class: 'frist-zeile' }, fristTag(a)),
      h('div', { class: 'meta' },
        h('span', null, a.quelle_name || a.quelle),
        a.vergabestelle ? h('span', null, a.vergabestelle) : null,
        a.ort || a.plz ? h('span', null, [a.plz, a.ort].filter(Boolean).join(' ')) : null,
        a.region ? h('span', null, 'Region ' + a.region) : null,
        a.verfahren ? h('span', null, a.verfahren) : null,
        a.veroeffentlicht ? h('span', null, 'veröffentlicht ' + tagText(a.veroeffentlicht)) : null),
      (a.begruendung || []).length
        ? h('details', { class: 'aufklapp klein', 'data-schluessel': 'begruendung-' + a.id },
          h('summary', null, 'Warum ' + zahl(a.punkte) + ' Punkte?'),
          h('ul', { class: 'mini-liste' }, a.begruendung.map(b => h('li', null, String(b)))))
        : null,
      a.notiz ? h('p', { class: 'hilfe text' }, 'Notiz: ' + a.notiz) : null,
      h('div', { class: 'knopfreihe' },
        link ? h('a', { class: 'knopf zweit klein', href: link, target: '_blank', rel: 'noopener noreferrer' }, 'Bekanntmachung öffnen') : null,
        mappe ? h('a', { class: 'knopf klein', href: mappe, target: '_blank', rel: 'noopener noreferrer', 'data-pruef': 'mappe-ansehen' }, 'Bewerbungsmappe ansehen') : null,
        !mappe && mappeLaeuft ? tag('Mappe wird erstellt …', 'blau') : null,
        !mappe && !mappeLaeuft && !endgueltig
          ? aktionsKnopf('Bewerbungsmappe erstellen', 'klein', async () => {
            const r = await API.post('/api/ausschreibungen/' + enc(a.id) + '/vorbereiten');
            auftragGemeldet(r, 'den Akquise-Agenten');
          }, { 'data-pruef': 'mappe-erstellen' })
          : null,
        a.status === 'neu' ? aktionsKnopf('Interessant', 'zweit klein', () => statusSetzen('interessant'), { 'data-pruef': 'ausschreibung-interessant' }) : null,
        a.status === 'neu' ? sicherheitsKnopf('Ablehnen', 'Wirklich ablehnen? Nochmal tippen', 'zweit klein', () => statusSetzen('abgelehnt'), { 'data-pruef': 'ausschreibung-ablehnen' }) : null,
        statusTeile[0], statusTeile[1]));
  }

  // ===========================================================================
  // Vertrieb: Preis kalkulieren (Reinigung, fester Auftrag)
  // ===========================================================================
  function positionZeile(entfernen) {
    const zeile = h('div', { class: 'positionszeile', 'data-position': '' },
      h('div', { class: 'positionszeile-kopf' },
        h('span', { class: 'positionszeile-titel' }, 'Position'),
        h('button', { type: 'button', class: 'knopf zweit klein', 'data-weg': '' }, 'Entfernen')),
      h('div', { class: 'felder-2' },
        feld('Bezeichnung', eingabe('x', { 'data-feld': 'bezeichnung', required: true, maxlength: 80, placeholder: 'z. B. Treppenhaus' })),
        feld('Fläche in m²', dezimalFeld('x', { 'data-feld': 'flaeche', required: true, placeholder: 'z. B. 400' }))),
      h('div', { class: 'felder-3' },
        feld('Leistungswert in m²/h', dezimalFeld('x', { 'data-feld': 'leistung', required: true }),
          'Wie viele m² schafft eine Kraft pro Stunde? Euer Erfahrungswert – am besten gemessen.'),
        feld('Reinigungen', dezimalFeld('x', { 'data-feld': 'anzahl', required: true, maxlength: 10, placeholder: 'z. B. 1' })),
        feld('pro', auswahl('x', [['woche', 'Woche'], ['monat', 'Monat']], 'woche', { 'data-feld': 'turnus' }))));
    zeile.querySelector('[data-weg]').addEventListener('click', entfernen);
    return zeile;
  }

  function kalkulationKarte(einst, aufgaben, kontakte) {
    const w = (einst && einst.werte) || {};
    const satz = typeof w.stundensatz_cent === 'number' ? w.stundensatz_cent : 0;
    // Die gerade gerechnete Kalkulation steht immer oben (gleiche Sekunde = gleicher Zeitstempel)
    const kalk = aufgaben.filter(a => a.typ === 'kalkulation_reinigung')
      .sort((x, y) => (y.id === zustand.kalkOffen) - (x.id === zustand.kalkOffen) || String(y.erstellt).localeCompare(String(x.erstellt)))
      .slice(0, 3);

    const positionen = h('div', { class: 'positionen', 'data-pruef': 'kalk-positionen' });
    // Namen immer lückenlos (pos-0-…, pos-1-…), damit ungespeicherte Eingaben ein Neuaufbauen überstehen
    const nummerieren = () => {
      const zeilenEl = Array.from(positionen.querySelectorAll('[data-position]'));
      zeilenEl.forEach((z, i) => {
        z.querySelector('.positionszeile-titel').textContent = 'Position ' + (i + 1);
        z.querySelector('[data-weg]').hidden = zeilenEl.length === 1;
        z.querySelectorAll('[data-feld]').forEach(el => { el.name = 'pos-' + i + '-' + el.dataset.feld; });
      });
      zustand.kalkPositionen = zeilenEl.length;
    };
    const zeileNeu = () => {
      const zeile = positionZeile(() => { zeile.remove(); nummerieren(); });
      positionen.append(zeile);
      nummerieren();
      return zeile;
    };
    for (let i = 0; i < Math.max(1, Math.min(zustand.kalkPositionen, 20)); i++) zeileNeu();

    const form = formular({ 'data-pruef': 'kalkulation-formular' }, [
      positionen,
      h('div', { class: 'knopfreihe' }, h('button', {
        type: 'button', class: 'knopf zweit klein', 'data-pruef': 'kalk-position-plus',
        onclick: () => { const z = zeileNeu(); const erstes = z.querySelector('input'); if (erstes) erstes.focus(); },
      }, 'Position hinzufügen')),
      feld('Stundensatz für diese Kalkulation in € (optional)', betragFeld('stundensatz', { placeholder: satz ? 'leer = ' + euroEingabe(satz) : '' }),
        satz ? 'Leer lassen: es gilt euer Stundensatz (' + euro(satz) + ').'
          : 'Noch kein Stundensatz festgelegt – ohne ihn bleibt der Preis offen.'),
      h('div', { class: 'felder-2' },
        feld('Material in % (optional)', dezimalFeld('material_prozent', { maxlength: 10, placeholder: 'z. B. 5' })),
        feld('Zuschlag (Wagnis/Gewinn) in % (optional)', dezimalFeld('zuschlag_prozent', { maxlength: 10, placeholder: 'z. B. 10' }))),
      h('div', { class: 'felder-2' },
        feld('Anfahrten pro Monat (optional)', dezimalFeld('anfahrten_pro_monat', { maxlength: 10, placeholder: 'z. B. 4' })),
        feld('Minuten je Anfahrt (optional)', dezimalFeld('anfahrt_minuten', { maxlength: 10, placeholder: 'z. B. 30' }))),
      h('p', { class: 'hilfe' }, 'Der Finance-Agent rechnet nur mit euren Eingaben – keine angenommenen Werte, keine Normzahlen. Alle Beträge netto.'),
      h('div', { class: 'knopfreihe' }, absendeKnopf('Preis berechnen lassen', { 'data-pruef': 'kalkulation-absenden' })),
    ], async (werte) => {
      const zeilenEl = Array.from(positionen.querySelectorAll('[data-position]'));
      const pos = zeilenEl.map((z, i) => {
        const g = name => String(z.querySelector('[data-feld="' + name + '"]').value || '').trim();
        const p = {
          bezeichnung: g('bezeichnung'),
          flaeche_m2: zahlPflicht(g('flaeche'), 'Fläche (Position ' + (i + 1) + ')'),
          leistungswert_m2_h: zahlPflicht(g('leistung'), 'Leistungswert (Position ' + (i + 1) + ')'),
        };
        const anzahl = zahlPflicht(g('anzahl'), 'Reinigungen (Position ' + (i + 1) + ')');
        if (g('turnus') === 'monat') p.reinigungen_pro_monat = anzahl;
        else p.reinigungen_pro_woche = anzahl;
        return p;
      });
      const daten = { positionen: pos };
      if (werte.stundensatz) daten.stundensatz = betragPflicht(werte.stundensatz, 'Stundensatz');
      [['material_prozent', 'Material in %'], ['zuschlag_prozent', 'Zuschlag in %'], ['anfahrten_pro_monat', 'Anfahrten pro Monat'], ['anfahrt_minuten', 'Minuten je Anfahrt']]
        .forEach(([k, name]) => { if (werte[k]) daten[k] = zahlPflicht(werte[k], name); });
      const r = await API.post('/api/kalkulation/reinigung', daten);
      meldung('Der Finance-Agent rechnet …', 'info');
      const fertig = await aufgabeAbwarten(r.aufgabe_id, 20);
      if (!fertig) {
        meldung('Die Rechnung dauert länger – das Ergebnis erscheint gleich hier und unter „Aufgaben“.', 'warn');
        spaeterNeuLaden(2000);
        return;
      }
      if (fertig.status !== 'abgeschlossen') {
        meldung('Kalkulation nicht möglich: ' + (fertig.fehler || AUFGABEN_STATUS[fertig.status] || fertig.status), 'fehler');
        neuLaden();
        return;
      }
      meldung('Kalkulation fertig.', 'ok');
      zustand.kalkOffen = r.aufgabe_id;
      neuLaden();
    });

    return h('section', { class: 'karte', 'data-pruef': 'kalkulation' },
      h('h2', null, 'Preis kalkulieren (Reinigung)'),
      h('p', { class: 'hilfe' }, 'Monatspreis für einen festen Reinigungsauftrag: Fläche ÷ Leistungswert × Reinigungen = Stunden; dazu Stundensatz, Material, Anfahrt und Zuschlag.'),
      stundensatzZeile(satz),
      aufklapp('Neue Kalkulation', 'kalkulation-neu', !kalk.length, form),
      kalk.length ? [h('h3', null, 'Letzte Kalkulationen'),
        h('div', { class: 'liste', 'data-pruef': 'kalk-ergebnisse' }, kalk.map((a, i) => kalkAufgabeAnzeige(a, i === 0, kontakte)))] : null);
  }

  /** Formular „Stundensatz festlegen“ – dieselbe Einstellung wie in den Einstellungen (stundensatz_cent). */
  function stundensatzFormular(satz, pruef, zu) {
    return formular({ 'data-pruef': pruef }, [
      feld('Stundensatz in € (netto)', betragFeld('stundensatz', { value: satz ? euroEingabe(satz) : '' }),
        'Er muss Lohn, Lohnnebenkosten, Material, Fahrzeuge, Verwaltung und Gewinn decken. Leer oder 0 = offen. '
        + 'AUTONOMOUS nimmt nie selbst einen an.'),
      h('div', { class: 'knopfreihe' }, absendeKnopf('Stundensatz speichern', { 'data-pruef': pruef + '-speichern' }), zu ? abbrechenKnopf(zu) : null),
    ], async (werte) => {
      const t = String(werte.stundensatz || '').trim();
      const cent = (t === '' || /^0+([,.]0+)?$/.test(t)) ? 0 : centAus(t, 'Stundensatz');
      if (cent > 100000) throw new ApiFehler(0, 'Stundensatz: höchstens 1.000,00 €.');
      if (cent === satz) {
        meldung('Nichts geändert.', 'info');
        return;
      }
      await API.post('/api/einstellungen', { schluessel: 'stundensatz_cent', wert: cent });
      meldung(cent ? 'Stundensatz gespeichert: ' + euro(cent) + ' pro Stunde (netto).' : 'Stundensatz ist jetzt offen.', 'ok');
      neuLaden();
    });
  }
  /** Anzeige des Stundensatzes in der Kalkulation – mit „festlegen“/„ändern“ direkt an Ort und Stelle. */
  function stundensatzZeile(satz) {
    const [auf, bereich] = umschaltBereich(satz ? 'Stundensatz ändern' : 'Stundensatz festlegen', satz ? 'zweit klein' : 'klein',
      zu => stundensatzFormular(satz, 'stundensatz-kalk', zu));
    auf.setAttribute('data-pruef', 'stundensatz-festlegen');
    return h('div', { 'data-pruef': satz ? 'stundensatz-gesetzt' : 'stundensatz-offen' },
      h('p', null, satz ? ['Euer Stundensatz: ', h('strong', null, euro(satz) + ' pro Stunde (netto)')]
        : [tag('Stundensatz offen', 'warn'), ' Ohne ihn rechnet der Agent nur die Stunden, keinen Preis.']),
      h('div', { class: 'knopfreihe' }, auf), bereich);
  }

  function kalkAufgabeAnzeige(a, offen, kontakte) {
    let inhalt;
    if (a.status === 'abgeschlossen' && a.ergebnis && typeof a.ergebnis === 'object') inhalt = kalkErgebnis(a.ergebnis, a.id, kontakte);
    else if (ENDSTATUS.includes(a.status)) inhalt = h('p', { class: 'fehlertext' }, (AUFGABEN_STATUS[a.status] || a.status) + (a.fehler ? ': ' + a.fehler : ''));
    else inhalt = h('p', { class: 'hilfe' }, 'Wird gerade gerechnet …');
    return h('details', { class: 'aufklapp', 'data-schluessel': 'kalk-' + a.id, open: offen || zustand.kalkOffen === a.id, 'data-pruef': 'kalk-ergebnis' },
      h('summary', null, zeitText(a.erstellt) + ' · ' + String(a.titel || '').replace(/^Reinigung kalkulieren:\s*/, '')), inhalt);
  }

  function kalkErgebnis(e, aufgabeId, kontakte) {
    const offenPreis = typeof e.preis_monat_cent !== 'number';
    const stunden = n => (typeof n === 'number' && isFinite(n) ? n.toLocaleString('de-DE') : '0') + ' h';
    const stundenKachel = kachel('Stunden pro Monat', stunden(e.stunden_gesamt_monat), '', 'davon Anfahrt ' + stunden(e.anfahrt && e.anfahrt.stunden_monat));
    return h('div', { class: 'kalk-ergebnis' },
      offenPreis
        ? [h('div', { class: 'raster' }, stundenKachel),
          h('div', { class: 'hinweisbox warn', 'data-pruef': 'kalk-preis-monat' },
            h('strong', null, 'Preis offen'), ' – es fehlt der Stundensatz. Oben „Stundensatz festlegen“ antippen und neu rechnen.')]
        : h('div', { class: 'raster' },
          kachel('Preis pro Monat (netto)', e.preis_monat || '—', 'ok', null, 'kalk-preis-monat'),
          kachel('Preis pro Jahr (netto)', e.preis_jahr || '—', '', null, 'kalk-preis-jahr'),
          stundenKachel,
          kachel('Stundensatz', e.stundensatz || '—', '', e.stundensatz_quelle ? 'Quelle: ' + e.stundensatz_quelle : null)),
      (e.warnungen || []).length
        ? h('div', { class: 'hinweisbox warn', 'data-pruef': 'kalk-warnungen' }, h('strong', null, 'Warnungen'),
          h('ul', { class: 'mini-liste' }, e.warnungen.map(t => h('li', null, String(t)))))
        : null,
      h('h4', null, 'Rechenweg'),
      h('ol', { class: 'rechenweg' }, (e.rechenweg || []).map(t => h('li', null, String(t)))),
      (e.hinweise || []).length
        ? h('details', { class: 'aufklapp klein', 'data-schluessel': 'kalk-hinweise-' + aufgabeId },
          h('summary', null, 'Hinweise (' + e.hinweise.length + ')'), h('ul', { class: 'mini-liste' }, e.hinweise.map(t => h('li', null, String(t)))))
        : null,
      (e.quellen || []).length
        ? h('details', { class: 'aufklapp klein', 'data-schluessel': 'kalk-quellen-' + aufgabeId },
          h('summary', null, 'Quellen'), h('ul', { class: 'mini-liste' }, e.quellen.map(t => h('li', null, String(t)))))
        : null,
      dauerauftragTeil(e, aufgabeId, kontakte));
  }

  function dauerauftragTeil(e, aufgabeId, kontakte) {
    const offenPreis = typeof e.preis_monat_cent !== 'number';
    const teile = umschaltBereich('Angebot Dauerauftrag daraus erstellen', 'klein', zu => formular({ 'data-pruef': 'dauerauftrag-formular' }, [
      h('div', { class: 'felder-2' },
        feld('Kontakt (optional)', auswahl('kontakt_id', [['', '— ohne Kontakt —']].concat(kontakte.map(k => [k.id, k.firma])), '')),
        feld('Objekt (optional)', eingabe('objekt', { maxlength: 200, placeholder: 'z. B. Musterstraße 5, Leverkusen' }))),
      offenPreis
        ? feld('Monatspreis in € (netto)', betragFeld('betrag', { required: true }),
          'Die Kalkulation hat keinen Preis (Stundensatz OFFEN). Entweder hier selbst festlegen – oder erst den Stundensatz festlegen und neu rechnen.')
        : h('p', null, 'Preis aus der Kalkulation: ', h('strong', null, (e.preis_monat || '') + ' pro Monat (netto)')),
      h('div', { class: 'felder-3' },
        feld('Vertragsbeginn (optional)', eingabe('vertragsbeginn', { maxlength: 60, placeholder: 'z. B. 01.01.2027' })),
        feld('Laufzeit (optional)', eingabe('laufzeit', { maxlength: 80, placeholder: 'z. B. 12 Monate' })),
        feld('Kündigungsfrist (optional)', eingabe('kuendigungsfrist', { maxlength: 80, placeholder: 'z. B. 3 Monate' }))),
      h('p', { class: 'hilfe' }, 'Der Sales-Agent erstellt einen ENTWURF. Offene Punkte bleiben gelb markiert. Ein Angebot ist keine Einnahme.'),
      h('div', { class: 'knopfreihe' }, absendeKnopf('Angebotsentwurf erstellen lassen', { 'data-pruef': 'dauerauftrag-absenden' }), abbrechenKnopf(zu)),
    ], async (w) => {
      const daten = ohneLeere({
        art: 'reinigung_dauerauftrag', kalkulation_aufgabe_id: aufgabeId, kontakt_id: w.kontakt_id, objekt: w.objekt,
        vertragsbeginn: w.vertragsbeginn, laufzeit: w.laufzeit, kuendigungsfrist: w.kuendigungsfrist,
      });
      if (offenPreis) daten.betrag = betragPflicht(w.betrag, 'Monatspreis');
      const r = await API.post('/api/angebote', daten);
      auftragGemeldet(r, 'den Sales-Agenten');
    }));
    teile[0].dataset.pruef = 'dauerauftrag-oeffnen';
    return h('div', { class: 'knopfreihe' }, teile[0], teile[1]);
  }

  // ===========================================================================
  // Vertrieb: Rückmeldungen (Reaktionen messen)
  // ===========================================================================
  function rmListen(rm) {
    const mitStandard = (liste, texte) => {
      const l = wahlListe(liste, texte);
      return l.length ? l : Object.entries(texte);
    };
    return {
      reaktionen: mitStandard(rm.reaktionen, REAKTION_TEXT),
      gruende: mitStandard(rm.gruende, GRUND_TEXT),
      kanaele: mitStandard(rm.kanaele, KANAL_TEXT),
      arten: mitStandard(rm.angebot_arten, ANGEBOTSART_TEXT),
    };
  }

  function rueckmeldungForm(listen, quellen, kontakt, pruef, zu) {
    const erstes = l => (l.length ? l[0][0] : '');
    const reaktion = auswahl('reaktion', listen.reaktionen, erstes(listen.reaktionen));
    const grund = auswahl('grund', [['', '— kein Grund angegeben —']].concat(listen.gruende), '');
    const grundPruefen = () => {
      const erlaubt = GRUND_BEI.includes(reaktion.value);
      grund.disabled = !erlaubt;
      if (!erlaubt) grund.value = '';
    };
    reaktion.addEventListener('change', grundPruefen);
    grundPruefen();
    return formular({ 'data-pruef': pruef }, [
      kontakt ? h('p', { class: 'hilfe' }, 'Rückmeldung von ', h('strong', null, kontakt.firma)) : h('div', { class: 'felder-2' },
        feld('Kontakt (optional)', auswahl('kontakt_id', [['', '— ohne Kontakt —']].concat((quellen.kontakte || []).map(k => [k.id, k.firma])), '')),
        feld('Angebot (optional)', auswahl('angebot_id', [['', '— ohne Angebot —']].concat((quellen.angebote || []).map(a =>
          [a.id, ((a.inhalt && a.inhalt.titel) || a.titel || a.id) + (a.kontakt_firma ? ' – ' + a.kontakt_firma : '')])), ''))),
      h('div', { class: 'felder-2' },
        feld('Worum ging es?', auswahl('angebot_art', listen.arten, erstes(listen.arten))),
        feld('Wie wart ihr in Kontakt?', auswahl('kanal', listen.kanaele, erstes(listen.kanaele))),
        feld('Reaktion', reaktion),
        feld('Grund (optional)', grund, 'Ein Grund passt nur zu „abgelehnt“ oder „neutral“.')),
      feld('Notiz (optional)', textfeld('notiz', { maxlength: 1000, rows: 2 }), 'Keine privaten Daten eintragen.'),
      h('div', { class: 'knopfreihe' }, absendeKnopf('Rückmeldung speichern', { 'data-pruef': pruef + '-absenden' }), zu ? abbrechenKnopf(zu) : null),
    ], async (w, f) => {
      const daten = ohneLeere(Object.assign({}, w, kontakt ? { kontakt_id: kontakt.id } : {}));
      await API.post('/api/rueckmeldungen', daten);
      if (!zu) { f.reset(); grundPruefen(); }
      meldung('Rückmeldung gespeichert.', 'ok');
      neuLaden();
    });
  }

  function rueckmeldungZeile(r, listen) {
    const text = (liste, id) => { const o = liste.find(x => x[0] === id); return o ? o[1] : String(id || ''); };
    return h('li', { class: 'eintrag', 'data-pruef': 'rueckmeldung' },
      h('div', { class: 'eintrag-kopf' }, h('span', { class: 'eintrag-titel' }, r.kontakt_firma || 'ohne Kontakt'),
        tag(text(listen.reaktionen, r.reaktion), REAKTION_TON[r.reaktion] || 'grau')),
      h('div', { class: 'meta' },
        r.angebot_art ? h('span', null, text(listen.arten, r.angebot_art)) : null,
        r.kanal ? h('span', null, text(listen.kanaele, r.kanal)) : null,
        r.grund ? h('span', null, 'Grund: ' + text(listen.gruende, r.grund)) : null,
        h('span', null, zeitText(r.zeit || r.erfasst || r.erstellt))),
      r.notiz ? h('p', { class: 'hilfe text' }, r.notiz) : null);
  }

  function rueckmeldungenKarte(rm, listen, kontakte, angebote, aufgaben) {
    if (!rm || rm.fehlt || !listen) {
      const k = nichtVerfuegbar('Rückmeldungen', 'Das Erfassen und Auswerten von Kundenreaktionen ist im Backend noch nicht eingebaut.');
      k.dataset.pruef = 'rueckmeldungen-nicht-verfuegbar';
      return k;
    }
    const liste = rm.rueckmeldungen || [];
    const auswertungen = aufgaben.filter(a => /rueckmeld/.test(String(a.typ || '')))
      .sort((x, y) => String(y.erstellt).localeCompare(String(x.erstellt)));
    const letzte = auswertungen.find(a => a.status === 'abgeschlossen' && a.ergebnis);
    const laeuft = auswertungen.some(a => !ENDSTATUS.includes(a.status));
    return h('section', { class: 'karte', 'data-pruef': 'rueckmeldungen' },
      h('h2', null, 'Rückmeldungen', tag(zahl(liste.length), 'grau')),
      h('p', { class: 'hilfe' }, 'Wie haben Interessenten reagiert? AUTONOMOUS zählt Reaktionen und Gründe aus euren Einträgen und macht daraus Vorschläge – Preise oder Angebote ändert es nicht selbst.'),
      aufklapp('Rückmeldung erfassen', 'rueckmeldung-neu', false, rueckmeldungForm(listen, { kontakte, angebote }, null, 'rueckmeldung-formular')),
      liste.length
        ? h('ul', { class: 'liste', 'data-pruef': 'rueckmeldungen-liste' }, liste.slice(0, 20).map(r => rueckmeldungZeile(r, listen)))
        : leer('Noch keine Rückmeldungen erfasst.'),
      h('div', { class: 'knopfreihe' }, aktionsKnopf(laeuft ? 'Auswertung läuft …' : 'Rückmeldungen auswerten', 'zweit', async () => {
        const r = await API.post('/api/rueckmeldungen/auswerten');
        meldung('Auswertung gestartet …', 'info');
        const fertig = r && r.aufgabe_id ? await aufgabeAbwarten(r.aufgabe_id, 20) : null;
        if (fertig && fertig.status === 'abgeschlossen') meldung('Auswertung fertig.', 'ok');
        else if (fertig) meldung('Auswertung: ' + (fertig.fehler || AUFGABEN_STATUS[fertig.status] || fertig.status), 'fehler');
        neuLaden();
      }, { 'data-pruef': 'rueckmeldungen-auswerten', disabled: laeuft })),
      letzte
        ? h('details', { class: 'aufklapp', 'data-schluessel': 'rueckmeldungen-auswertung', 'data-pruef': 'rueckmeldungen-auswertung' },
          h('summary', null, 'Letzte Auswertung · ' + zeitText(letzte.beendet || letzte.aktualisiert)), auswertungAnzeige(letzte.ergebnis, listen))
        : null);
  }

  /** Ergebnis der Rückmeldungs-Auswertung lesbar zeigen (unbekannte Form: allgemeine Anzeige). */
  function auswertungAnzeige(e, listen) {
    e = alsWert(e);
    if (!e || typeof e !== 'object' || !('je_angebot' in e)) return wertAnzeige(e);
    const text = (liste, id) => { const o = liste.find(x => x[0] === id); return o ? o[1] : String(id); };
    const je = e.je_angebot || {};
    return h('div', { class: 'kalk-ergebnis' },
      e.hinweis ? h('p', { class: 'hilfe' }, e.hinweis) : null,
      (e.vorschlaege || []).length
        ? h('div', { class: 'hinweisbox' }, h('strong', null, 'Vorschläge (ungeprüft – ihr entscheidet)'),
          h('ul', { class: 'mini-liste' }, e.vorschlaege.map(v => h('li', null, typeof v === 'string' ? v : wertAnzeige(v)))))
        : h('p', { class: 'hilfe' }, 'Noch keine Vorschläge.'),
      kv([['Rückmeldungen gesamt', zahl(e.gesamt)]]),
      Object.keys(je).length
        ? h('ul', { class: 'liste' }, Object.entries(je).map(([art, d]) => h('li', { class: 'eintrag' },
          h('div', { class: 'eintrag-kopf' }, h('span', { class: 'eintrag-titel' }, text(listen.arten, art)), tag(zahl(d.anzahl) + ' Rückmeldungen', 'grau')),
          h('div', { class: 'chips' }, Object.entries(d.reaktionen || {}).filter(r => r[1]).map(([r, n]) =>
            h('span', { class: 'chip' }, tag(text(listen.reaktionen, r), REAKTION_TON[r] || 'grau'), h('strong', null, zahl(n))))),
          gruendePaare(d.gruende).length
            ? h('p', { class: 'hilfe' }, 'Gründe: ' + gruendePaare(d.gruende).map(([g, n]) => text(listen.gruende, g) + ' ' + n + '×').join(', '))
            : null,
          typeof d.quote_interessiert_prozent === 'number' ? h('p', { class: 'hilfe' }, 'Anteil interessiert: ' + zahl(d.quote_interessiert_prozent) + ' %') : null,
          d.hinweis ? h('p', { class: 'hilfe' }, d.hinweis) : null)))
        : null);
  }
  /** Gründe als Paare [grund, anzahl] – das Backend liefert eine Liste von Paaren (oder ein Objekt). */
  function gruendePaare(g) {
    if (Array.isArray(g)) return g.filter(x => Array.isArray(x) && x.length >= 2);
    if (g && typeof g === 'object') return Object.entries(g);
    return [];
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
    const [e, ms] = await Promise.all([API.get('/api/einstellungen'), optional('/api/modell/status')]);
    zustand.katalog = e.aktionen || {};
    z.append(h('p', { class: 'einleitung' }, 'Hier legt ihr die wenigen Werte fest, mit denen AUTONOMOUS rechnet und sucht. Technik steht unten eingeklappt.'));
    z.append(stundensatzKarte(e));
    z.append(auftragssucheKarte(e));
    z.append(kiModellKarte(e, ms));
    z.append(sicherungKarte(e.sicherungen || []));
    z.append(h('section', { class: 'karte', 'data-pruef': 'technik' },
      h('h2', null, 'Technik (nur bei Bedarf)'),
      h('p', { class: 'hilfe' }, 'Kosten, Betrieb, Berechtigungen und Protokoll. Im Alltag müsst ihr hier nichts ändern.'),
      aufklapp('Kosten und Betrieb', 'technik-betrieb', false, kostenBetriebFormular(e)),
      aufklapp('Berechtigungen (Aktionskatalog)', 'technik-katalog', false, katalogInhalt(e.aktionen || {})),
      aufklapp('Protokoll', 'technik-protokoll', false, await protokollInhalt()),
      aufklapp('KI-Aufrufe (Protokoll)', 'technik-modellaufrufe', false, modellaufrufeInhalt(e.modellaufrufe || []))));
  }

  /** Stundensatz als eigene Karte – ohne ihn gibt es keinen Preis. */
  function stundensatzKarte(e) {
    const w = e.werte || {};
    if (!('stundensatz_cent' in w)) return nichtVerfuegbar('Stundensatz für Kalkulationen', 'Diese Einstellung gibt es in dieser Version des Servers noch nicht.');
    const satz = typeof w.stundensatz_cent === 'number' ? w.stundensatz_cent : 0;
    return h('section', { class: 'karte', 'data-pruef': 'stundensatz-karte' },
      h('h2', null, 'Stundensatz für Kalkulationen'),
      h('p', null, 'Gerade: ', satz ? h('strong', { 'data-pruef': 'stundensatz-wert' }, euro(satz) + ' pro Stunde (netto)')
        : tag('offen – noch nicht festgelegt', 'warn')),
      stundensatzFormular(satz, 'stundensatz-formular'));
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

  /** KI-Modell (lokal, optional): Status, Einstellungen und ein echter Probeaufruf. */
  function kiModellKarte(e, ms) {
    const w = e.werte || {};
    if (!ms || ms.fehlt) {
      return nichtVerfuegbar('KI-Modell (lokal, optional)', 'Die Modell-Schnittstelle gibt es in dieser Version des Servers noch nicht.');
    }
    const optionen = [
      ['keiner', 'Kein Modell', 'Alles läuft nach festen Regeln, ohne KI. Standard.'],
      ['ollama', 'Ollama auf diesem Rechner', 'Lokal und kostenlos. Ollama muss auf dem Mac installiert sein und ein Modell geladen haben.'],
    ];
    const gruppe = h('fieldset', { class: 'auswahlgruppe' }, h('legend', null, 'Welches Modell sollen die Agenten nutzen?'),
      optionen.map(([id, name, text]) => h('label', { class: 'option', for: 'anbieter-' + id },
        h('input', { type: 'radio', name: 'modell_anbieter', value: id, checked: w.modell_anbieter === id, id: 'anbieter-' + id, 'data-pruef': 'anbieter-' + id }),
        h('span', null, h('strong', null, name), h('span', { class: 'hilfe' }, text)))),
      h('div', { class: 'option gesperrt' }, h('span', null, h('strong', null, 'Externe, bezahlte KI-Dienste'),
        h('span', { class: 'hilfe' }, 'Nicht angebunden. Nur nach eurer ausdrücklichen Zustimmung und mit Preisangabe.'),
        h('span', null, tag('nicht angebunden', 'grau')))));
    const form = formular({ 'data-pruef': 'ki-formular' }, [
      gruppe,
      h('div', { class: 'felder-2' },
        feld('Modellname', eingabe('ollama_modell', { value: w.ollama_modell || '', maxlength: 60 }), 'z. B. gemma3:4b – so, wie es in Ollama heißt.'),
        feld('Adresse auf diesem Rechner', eingabe('ollama_adresse', { value: w.ollama_adresse || '', maxlength: 60 }),
          'Nur dieser Rechner ist erlaubt, z. B. http://127.0.0.1:11434.')),
      feld('Höchstens KI-Aufrufe pro Tag', zahlFeld('modell_max_aufrufe_tag', { value: w.modell_max_aufrufe_tag, min: 0, max: 1000 })),
      h('div', { class: 'knopfreihe' }, absendeKnopf('KI-Einstellungen speichern', { 'data-pruef': 'ki-speichern' })),
    ], async (werte) => {
      const neu = {
        modell_anbieter: werte.modell_anbieter || w.modell_anbieter,
        ollama_modell: werte.ollama_modell,
        ollama_adresse: werte.ollama_adresse,
        modell_max_aufrufe_tag: ganzAus(werte.modell_max_aufrufe_tag, 'KI-Aufrufe pro Tag', 0, 1000),
      };
      if (!/^[A-Za-z0-9:._-]{1,60}$/.test(neu.ollama_modell || '')) throw new ApiFehler(0, 'Modellname: nur Buchstaben, Ziffern und : . _ - (z. B. gemma3:4b).');
      if (!/^http:\/\/(127\.0\.0\.1|localhost|\[::1\]):\d{1,5}\/?$/.test(neu.ollama_adresse || '')) {
        throw new ApiFehler(0, 'Adresse: nur dieser Rechner, z. B. http://127.0.0.1:11434.');
      }
      const geaendert = Object.keys(neu).filter(k => JSON.stringify(neu[k]) !== JSON.stringify(w[k]));
      if (!geaendert.length) {
        meldung('Nichts geändert.', 'info');
        return;
      }
      for (const k of geaendert) {
        await API.post('/api/einstellungen', { schluessel: k, wert: neu[k] });
      }
      meldung('KI-Einstellungen gespeichert.', 'ok');
      neuLaden();
    });

    const ergebnis = h('div', { 'data-pruef': 'modell-test-ergebnis', 'aria-live': 'polite' });
    const testen = aktionsKnopf('Modell testen', 'zweit', async () => {
      ersetze(ergebnis, h('p', { class: 'hilfe' }, 'Frage an das Modell läuft … (kann bis zu einer Minute dauern)'));
      const r = await API.post('/api/modell/testen');
      if (r && r.ok && r.antwort) {
        ersetze(ergebnis, h('div', { class: 'hinweisbox' },
          h('div', null, tag(r.antwort.kennzeichnung || 'KI-Entwurf – ungeprüft', 'warn')),
          h('p', { class: 'text' }, 'Antwort: ', h('strong', null, String(r.antwort.text || ''))),
          h('div', { class: 'meta' }, 'Dauer: ' + zahl(r.dauer_ms) + ' ms · ' + (r.antwort.quelle || ''))));
      } else {
        ersetze(ergebnis, h('p', { class: 'fehlertext' }, 'Kein Ergebnis: ' + ((r && r.meldung) || 'unbekannt')));
      }
    }, { 'data-pruef': 'modell-testen', disabled: ms.anbieter === 'keiner' || !ms.anbieter });

    const janein = (b, ja, nein) => tag(b ? ja : nein, b ? 'ok' : 'warn');
    const installiert = Array.isArray(ms.installierte_modelle) ? ms.installierte_modelle : [];
    return h('section', { class: 'karte', 'data-pruef': 'ki-modell' },
      h('h2', null, 'KI-Modell (lokal, optional)'),
      h('p', { class: 'hilfe' }, 'KI-Ausgaben sind ungeprüfte Entwürfe und werden immer so gekennzeichnet. Ohne Modell läuft alles weiter. '
        + 'Ein externer, bezahlter KI-Dienst ist nicht angebunden.'),
      kv([
        ['Gerade eingestellt', ms.anbieter === 'ollama' ? 'Ollama' + (ms.modell ? ' · ' + ms.modell : '') : 'Kein Modell'],
        ms.anbieter === 'ollama' ? ['Erreichbar', janein(ms.erreichbar, 'ja', 'nein')] : null,
        ms.anbieter === 'ollama' ? ['Modell geladen', janein(ms.modell_vorhanden, 'ja', 'nein')] : null,
        installiert.length ? ['Auf diesem Rechner geladen', installiert.join(', ')] : null,
        ['KI-Aufrufe heute', zahl(ms.aufrufe_heute) + ' von ' + zahl(ms.limit_tag)],
        ['Hinweis', ms.hinweis],
      ]),
      h('div', { class: 'knopfreihe' }, testen),
      ms.anbieter === 'keiner' || !ms.anbieter ? h('p', { class: 'hilfe' }, '„Modell testen“ geht, sobald ihr unten „Ollama“ wählt und speichert.') : null,
      ergebnis,
      h('div', { class: 'trenner' }),
      form);
  }

  /** Kosten und Betrieb (eingeklappt unter „Technik“). */
  function kostenBetriebFormular(e) {
    const w = e.werte || {};
    const kostenSchalter = h('input', { type: 'checkbox', name: 'kostenpflichtig_erlaubt', checked: !!w.kostenpflichtig_erlaubt, id: 'kostenpflichtig' });
    const warnung = hinweis('Achtung: Damit sind kostenpflichtige Aktionen grundsätzlich möglich. Jede einzelne braucht trotzdem eure Freigabe. Empfehlung: aus lassen.', 'warn');
    warnung.hidden = !kostenSchalter.checked;
    kostenSchalter.addEventListener('change', () => { warnung.hidden = !kostenSchalter.checked; });
    return formular({ 'data-pruef': 'einstellungen-formular' }, [
      h('label', { class: 'schalter', for: 'kostenpflichtig' }, kostenSchalter,
        h('span', null, h('strong', null, 'Kostenpflichtige Aktionen zulassen'), h('br'), h('span', { class: 'hilfe' }, 'Standard: aus. Kostenpflichtige Dienste sind dann komplett gesperrt.'))),
      warnung,
      h('p', { class: 'hilfe' }, 'Ausgabengrenzen legt ihr als Budgets fest – unter „Finanzen“ (real) und „Wallet“ (Simulation).'),
      h('div', { class: 'felder-3' },
        feld('Gleichzeitig arbeitende Agenten', zahlFeld('max_parallel', { value: w.max_parallel, min: 1, max: 8 }), 'Wirkt erst nach einem Neustart.'),
        feld('Warnen, wenn das simulierte Guthaben unter … € fällt', betragFeld('wallet_warnschwelle', { value: euroEingabe(w.wallet_warnschwelle_cent) })),
        feld('Sicherungen behalten', zahlFeld('sicherung_behalten', { value: w.sicherung_behalten, min: 1, max: 365 }), 'Anzahl der neuesten Sicherungen.')),
      h('div', { class: 'knopfreihe' }, absendeKnopf('Speichern', { 'data-pruef': 'einstellungen-speichern' })),
    ], async (werte) => {
      const neu = {
        kostenpflichtig_erlaubt: !!werte.kostenpflichtig_erlaubt,
        max_parallel: ganzAus(werte.max_parallel, 'Gleichzeitig arbeitende Agenten', 1, 8),
        wallet_warnschwelle_cent: /^0+([,.]0+)?$/.test(String(werte.wallet_warnschwelle || '').trim()) ? 0 : centAus(werte.wallet_warnschwelle, 'Warnschwelle'),
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
  }

  /** Auftragssuche (öffentliche Ausschreibungen) – alles bleibt in eurer Hand. */
  function auftragssucheKarte(e) {
    const w = e.werte || {};
    if (!('internet_recherche_erlaubt' in w)) {
      return nichtVerfuegbar('Auftragssuche', 'Diese Einstellungen gibt es in dieser Version des Servers noch nicht.');
    }
    const recherche = h('input', { type: 'checkbox', name: 'internet_recherche_erlaubt', checked: !!w.internet_recherche_erlaubt, id: 'recherche-schalter', 'data-pruef': 'recherche-schalter' });
    const taeglich = h('input', { type: 'checkbox', name: 'auftragssuche_taeglich', checked: !!w.auftragssuche_taeglich, id: 'taeglich-schalter', 'data-pruef': 'taeglich-schalter' });
    const liste = x => (Array.isArray(x) ? x.join(', ') : '');
    const form = formular({ 'data-pruef': 'auftragssuche-formular' }, [
      h('label', { class: 'schalter', for: 'recherche-schalter' }, recherche,
        h('span', null, h('strong', null, 'Internet-Recherche erlauben'), h('br'),
          h('span', { class: 'hilfe' }, 'Die Agenten dürfen dann nur die freigegebenen öffentlichen Ausschreibungsseiten lesen: TED (EU-Amtsblatt), '
            + 'service.bund.de und den Vergabemarktplatz NRW. Nur lesen – nichts senden, nirgends anmelden, nichts abgeben. Standard: aus.'))),
      h('label', { class: 'schalter', for: 'taeglich-schalter' }, taeglich,
        h('span', null, h('strong', null, 'Einmal täglich selbstständig suchen'), h('br'),
          h('span', { class: 'hilfe' }, 'Höchstens einmal am Tag, solange AUTONOMOUS läuft – und nur, wenn die Internet-Recherche erlaubt ist.'))),
      h('div', { class: 'felder-2' },
        feld('Region: Postleitzahl-Bereiche', eingabe('region_plz', { value: liste(w.region_plz), maxlength: 400, inputmode: 'numeric' }),
          'Die ersten zwei Ziffern, mit Komma getrennt. Nur eine Näherung für „ca. 100 km um Leverkusen“ – keine genaue Entfernung.'),
        feld('EU-Regionen (Kürzel) für EU-Ausschreibungen', eingabe('region_nuts', { value: liste(w.region_nuts), maxlength: 200 }),
          'DEA steht für ganz Nordrhein-Westfalen.')),
      feld('Suchbegriffe', textfeld('suchbegriffe', { rows: 5, value: liste(w.suchbegriffe), maxlength: 1500 }),
        'Mit Komma getrennt. Kommt ein Begriff im Titel vor, gibt es Punkte. Für EU-Ausschreibungen sucht der Agent fest nach Reinigungsleistungen.'),
      feld('Ausschlussbegriffe', textfeld('ausschlussbegriffe', { rows: 4, value: liste(w.ausschlussbegriffe), maxlength: 1500 }),
        'Kommt ein Begriff vor, gibt es starken Abzug – z. B. Straßenreinigung oder Kanal.'),
      h('div', { class: 'knopfreihe' }, absendeKnopf('Auftragssuche speichern', { 'data-pruef': 'auftragssuche-speichern' })),
    ], async (werte) => {
      const neu = {
        internet_recherche_erlaubt: !!werte.internet_recherche_erlaubt,
        auftragssuche_taeglich: !!werte.auftragssuche_taeglich,
        region_plz: listeAus(werte.region_plz, false),
        region_nuts: listeAus(werte.region_nuts, false).map(x => x.toUpperCase()),
        suchbegriffe: listeAus(werte.suchbegriffe, true),
        ausschlussbegriffe: listeAus(werte.ausschlussbegriffe, true),
      };
      // Dieselben Regeln wie im Backend – so wird nichts nur halb gespeichert
      const pruefListe = (eintraege, muster, name, min, max) => {
        if (eintraege.length < min || eintraege.length > max) throw new ApiFehler(0, name + ': ' + min + ' bis ' + max + ' Einträge erlaubt.');
        const falsch = eintraege.filter(x => !muster.test(x));
        if (falsch.length) throw new ApiFehler(0, name + ': ungültig – ' + falsch.slice(0, 3).join(', '));
      };
      pruefListe(neu.region_plz, /^\d{2}$/, 'Postleitzahl-Bereiche (je zwei Ziffern)', 1, 60);
      pruefListe(neu.region_nuts, /^DE[A-Z0-9]{0,3}$/, 'EU-Regionen (Kürzel, z. B. DEA)', 1, 40);
      pruefListe(neu.suchbegriffe, /^[a-zäöüß0-9 -]{2,40}$/, 'Suchbegriffe (Buchstaben, Ziffern, Leerzeichen, Bindestrich)', 1, 40);
      pruefListe(neu.ausschlussbegriffe, /^[a-zäöüß0-9 -]{2,40}$/, 'Ausschlussbegriffe (Buchstaben, Ziffern, Leerzeichen, Bindestrich)', 0, 40);
      const geaendert = Object.keys(neu).filter(k => JSON.stringify(neu[k]) !== JSON.stringify(w[k]));
      if (!geaendert.length) {
        meldung('Nichts geändert.', 'info');
        return;
      }
      for (const k of geaendert) {
        await API.post('/api/einstellungen', { schluessel: k, wert: neu[k] });
      }
      meldung('Gespeichert: ' + geaendert.length + ' Einstellung(en).'
        + (geaendert.includes('internet_recherche_erlaubt') ? (neu.internet_recherche_erlaubt ? ' Internet-Recherche ist jetzt an.' : ' Internet-Recherche ist jetzt aus.') : ''), 'ok');
      neuLaden();
    });
    return h('section', { class: 'karte', 'data-pruef': 'auftragssuche' },
      h('h2', null, 'Auftragssuche'),
      kv([
        ['Internet-Recherche', w.internet_recherche_erlaubt ? 'an' : 'aus'],
        ['Tägliche Suche', w.auftragssuche_taeglich ? 'an' : 'aus'],
      ]),
      h('div', { class: 'trenner' }),
      form);
  }

  function katalogInhalt(aktionen) {
    const gruppen = { auto: [], freigabe: [], verboten: [] };
    Object.keys(aktionen).forEach(name => {
      const a = aktionen[name];
      (gruppen[a.klasse] || (gruppen[a.klasse] = [])).push([name, a.beschreibung]);
    });
    return h('div', null,
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
      h('p', { class: 'hilfe' }, 'Wiederherstellen: ', tag('in der Oberfläche noch nicht verfügbar', 'grau'), ' Nur bei gestopptem System – die Anleitung steht in autonomous/README.md im Startordner.'),
      h('h3', null, 'Vorhandene Sicherungen'),
      sicherungen.length
        ? h('ul', { class: 'liste' }, sicherungen.map(s => h('li', { class: 'eintrag' },
          h('div', { class: 'eintrag-kopf' }, h('span', { class: 'eintrag-titel' }, sicherungText(s.datei)), h('span', { class: 'meta' }, zahl(Math.round((s.groesse || 0) / 1024)) + ' KB')),
          h('div', { class: 'meta' }, h('code', null, s.datei)))))
        : leer('Noch keine Sicherung vorhanden.'));
  }

  async function protokollInhalt() {
    const huelle = h('div');
    const filter = auswahl('ebene', EBENEN, zustand.protokollEbene);
    let anzahl = 20;
    const laden = async () => {
      const daten = await API.get('/api/protokoll' + (zustand.protokollEbene ? '?ebene=' + enc(zustand.protokollEbene) : ''));
      const eintraege = daten.eintraege || [];
      const zeichne = () => {
        ersetze(huelle, eintraege.length
          ? [h('ul', { class: 'liste' }, eintraege.slice(0, anzahl).map(p => h('li', { class: 'eintrag' },
            h('div', { class: 'eintrag-kopf' }, h('span', { class: 'eintrag-titel' }, p.ereignis), tag(ebeneText(p.ebene), EBENE_TON[p.ebene])),
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
    return h('div', null, h('p', { class: 'hilfe' }, 'Fehler und kritische Aktionen – ohne Passwörter oder Schlüssel.'),
      h('div', { class: 'filter' }, feld('Ebene', filter)), huelle);
  }

  function modellaufrufeInhalt(aufrufe) {
    return h('div', null,
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
      hintergrundSperren(true);
      mehrKnopf.setAttribute('aria-expanded', 'true');
      const aktiv = blatt.querySelector('[aria-current="page"]') || blatt.querySelector('a');
      if (aktiv) aktiv.focus();
    });
    document.getElementById('mehr-zu').addEventListener('click', () => schliesseMehr(true));
    blatt.addEventListener('click', (e) => { if (e.target === blatt) schliesseMehr(true); });
    mehr.addEventListener('click', (e) => { if (e.target.closest('a')) schliesseMehr(false); });
    document.addEventListener('keydown', (e) => { if (e.key === 'Escape' && !blatt.hidden) schliesseMehr(true); });
  }

  /** Solange das „Mehr“-Blatt offen ist, bleibt Tab im Blatt (der Rest der Seite ist gesperrt). */
  function hintergrundSperren(an) {
    document.querySelectorAll('.app, #nav-unten').forEach(el => { el.inert = !!an; });
  }

  function schliesseMehr(fokusZurueck) {
    const blatt = document.getElementById('mehr-blatt');
    if (blatt.hidden) return;
    blatt.hidden = true;
    hintergrundSperren(false);
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
    if (!still) {
      main.dataset.bereich = bereich.id;
      main.dataset.status = 'laedt';
      main.replaceChildren(h('p', { class: 'laedt', role: 'status' }, 'Lädt …'));
      window.scrollTo(0, 0);
    }
    const ziel = h('div', { class: 'ansicht' });
    try {
      await bereich.render(ziel);
      if (nr !== zustand.renderNr || !zustand.angemeldet) return;
      let fokus = null;
      if (still) {
        // Erst JETZT merken (nicht vor dem Laden): Eingaben, die während des Ladens gemacht wurden, gehen nicht verloren
        const offeneDetails = new Set(Array.from(main.querySelectorAll('details[data-schluessel]')).filter(d => d.open).map(d => d.dataset.schluessel));
        const eingaben = eingabenMerken(main);
        const aktiv = document.activeElement;
        if (aktiv && main.contains(aktiv) && aktiv.form && aktiv.name && !aktiv.form.closest('.inline-form')) {
          fokus = feldSchluessel(aktiv.form, aktiv);
        }
        ziel.querySelectorAll('details[data-schluessel]').forEach(d => {
          if (offeneDetails.has(d.dataset.schluessel)) d.open = true;
        });
        eingabenZurueck(ziel, eingaben);
      }
      main.replaceChildren(ziel);
      if (fokus) {
        // Wer gerade tippt, behält das Feld
        const gleich = Array.from(ziel.querySelectorAll('form')).flatMap(f => Array.from(f.elements).filter(el => el.name && feldSchluessel(f, el) === fokus));
        if (gleich[0]) gleich[0].focus();
      }
      if (still) fokusStelleWiederherstellen(main);
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
