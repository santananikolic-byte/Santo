/*
 * Jarvis-Erweiterung - das Popup hinter dem Jarvis-Symbol.
 *
 * Das Popup liest die offene Seite aus (chrome.scripting im aktiven Tab) und
 * reicht den Auftrag an den Hintergrunddienst weiter. Der schickt ihn an
 * Jarvis und legt das Ergebnis ab - so geht keine Antwort verloren, wenn das
 * Popup zwischendurch zugeht. Beim nächsten Öffnen steht sie wieder da.
 *
 * Alles, was von der Seite oder von Jarvis kommt, landet nur per textContent
 * im Popup, nie als HTML: Ein Seitentitel wie "<img onerror=...>" bleibt Text.
 */
'use strict';

const popupTeile = {
  einstellungen: document.getElementById('einstellungen'),
  seitentitel: document.getElementById('seitentitel'),
  seitenhinweis: document.getElementById('seitenhinweis'),
  zusammenfassen: document.getElementById('zusammenfassen'),
  kontakte: document.getElementById('kontakte'),
  formular: document.getElementById('frageformular'),
  frage: document.getElementById('frage'),
  senden: document.getElementById('senden'),
  bereich: document.getElementById('antwortbereich'),
  marke: document.getElementById('antwortmarke'),
  vorlesen: document.getElementById('vorlesen'),
  antwortfrage: document.getElementById('antwortfrage'),
  antwort: document.getElementById('antwort'),
  verbindung: document.getElementById('verbindung')
};

const POPUP_NAMEN = { zusammenfassen: 'Zusammenfassung', kontakte: 'Kontakte', frage: 'Antwort' };
const POPUP_WARTETEXTE = {
  zusammenfassen: 'Jarvis liest die Seite …',
  kontakte: 'Jarvis sucht die Kontaktdaten …',
  frage: 'Jarvis denkt nach …'
};
// Ältere Antworten zeigt das Popup nicht mehr an - sie gehören zu einer anderen Seite.
const POPUP_ALTER_MS = 30 * 60 * 1000;
// Ein "läuft" ohne Ergebnis nach so langer Zeit heißt: der Dienst wurde beendet.
const POPUP_HAENGT_MS = 5 * 60 * 1000;

let popupTab = null;
let popupSeiteLesbar = false;
let popupBeschaeftigt = false;
let popupSpricht = false;

popupStarten();

async function popupStarten() {
  const parameter = new URLSearchParams(location.search);
  if (parameter.get('fenster') === '1') {
    document.body.classList.add('fenster');
  }
  popupTeile.zusammenfassen.addEventListener('click', function () { popupAuftrag('zusammenfassen'); });
  popupTeile.kontakte.addEventListener('click', function () { popupAuftrag('kontakte'); });
  popupTeile.formular.addEventListener('submit', function (ereignis) {
    ereignis.preventDefault();
    popupAuftrag('frage');
  });
  popupTeile.frage.addEventListener('keydown', function (ereignis) {
    if (ereignis.key === 'Enter' && !ereignis.shiftKey && !ereignis.isComposing) {
      ereignis.preventDefault();
      popupAuftrag('frage');
    }
  });
  popupTeile.vorlesen.addEventListener('click', popupVorlesen);
  popupTeile.einstellungen.addEventListener('click', function () {
    chrome.runtime.openOptionsPage();
  });
  if (window.speechSynthesis) {
    // Chrome lädt die Stimmen erst nach - einmal anstoßen.
    window.speechSynthesis.getVoices();
  }

  popupVerbindungZeigen();
  popupTab = await popupZielTab(parameter.get('tab'));
  await popupSeitePruefen();
  await popupLetzteZeigen();
  try {
    chrome.storage.onChanged.addListener(function (aenderungen, bereich) {
      if (bereich === 'session' && aenderungen[JARVIS_ABLAGE_LETZTE] && !popupBeschaeftigt) {
        const eintrag = aenderungen[JARVIS_ABLAGE_LETZTE].newValue;
        if (eintrag) {
          popupZeigen(eintrag);
        }
      }
    });
  } catch (fehler) {
    // Ohne Ablage keine Nachträge.
  }
  popupTeile.frage.focus();
}

async function popupVerbindungZeigen() {
  const einstellungen = await jarvisEinstellungenLesen();
  popupTeile.verbindung.textContent = 'Jarvis: ' + einstellungen.adresse.replace(/^https?:\/\//, '')
    + (einstellungen.schluessel ? ' · mit Zugangsschlüssel' : '');
}

/** Der Tab, um den es geht: der aktive - oder der, den der Hintergrund mitgibt. */
async function popupZielTab(tabParameter) {
  if (tabParameter && /^\d+$/.test(tabParameter)) {
    try {
      return await chrome.tabs.get(Number(tabParameter));
    } catch (fehler) {
      // Der Tab ist inzwischen zu.
    }
  }
  try {
    const eigener = await chrome.tabs.getCurrent();
    const tabs = await chrome.tabs.query({ active: true, currentWindow: true });
    const tab = tabs && tabs[0];
    // Als eigenes Fenster geöffnet, ist der "aktive Tab" das Popup selbst.
    if (!tab || (eigener && eigener.id === tab.id)) {
      return null;
    }
    return tab;
  } catch (fehler) {
    return null;
  }
}

/** Zeigt, welche Seite gemeint ist, und ob die Erweiterung sie lesen darf. */
async function popupSeitePruefen() {
  const hinweis = popupTeile.seitenhinweis;
  if (!popupTab) {
    popupTeile.seitentitel.textContent = 'Keine Seite ausgewählt';
    hinweis.textContent = 'Öffne eine Webseite und klicke dann auf das Jarvis-Symbol. Fragen gehen trotzdem.';
    popupSeiteLesbar = false;
    popupKnoepfeSetzen();
    return;
  }
  const titel = popupTab.title || popupTab.url || 'Unbenannte Seite';
  popupTeile.seitentitel.textContent = titel;
  popupTeile.seitentitel.title = titel;
  try {
    const ergebnisse = await chrome.scripting.executeScript({
      target: { tabId: popupTab.id },
      func: function () {
        let markiert = String(window.getSelection() || '').trim().length;
        const aktiv = document.activeElement;
        if (!markiert && aktiv && typeof aktiv.selectionStart === 'number'
            && (aktiv.tagName === 'TEXTAREA' || aktiv.tagName === 'INPUT') && aktiv.type !== 'password') {
          markiert = Math.abs((aktiv.selectionEnd || 0) - (aktiv.selectionStart || 0));
        }
        return { titel: document.title, adresse: location.href, markiert: markiert };
      }
    });
    const seite = ergebnisse && ergebnisse[0] && ergebnisse[0].result;
    if (!seite) {
      throw new Error('leer');
    }
    let gastgeber = '';
    try {
      gastgeber = new URL(seite.adresse).host;
    } catch (fehler) {
      gastgeber = '';
    }
    if (seite.titel) {
      popupTeile.seitentitel.textContent = seite.titel;
      popupTeile.seitentitel.title = seite.titel;
    }
    hinweis.textContent = [gastgeber, seite.markiert ? 'Markierter Text wird mitgeschickt' : '']
      .filter(Boolean).join(' · ');
    hinweis.classList.remove('warnung');
    popupSeiteLesbar = true;
  } catch (fehler) {
    hinweis.textContent = 'Diese Seite kann Jarvis nicht lesen (Browserseite, Web Store oder PDF). '
      + 'Fragen gehen trotzdem.';
    hinweis.classList.add('warnung');
    popupSeiteLesbar = false;
  }
  popupKnoepfeSetzen();
}

function popupKnoepfeSetzen() {
  popupTeile.zusammenfassen.disabled = popupBeschaeftigt || !popupSeiteLesbar;
  popupTeile.kontakte.disabled = popupBeschaeftigt || !popupSeiteLesbar;
  popupTeile.senden.disabled = popupBeschaeftigt;
  document.body.classList.toggle('beschaeftigt', popupBeschaeftigt);
  popupTeile.bereich.setAttribute('aria-busy', popupBeschaeftigt ? 'true' : 'false');
}

/** Zeigt die letzte Antwort aus dem Hintergrund, falls sie noch frisch ist. */
async function popupLetzteZeigen() {
  let eintrag = null;
  try {
    const gespeichert = await chrome.storage.session.get(JARVIS_ABLAGE_LETZTE);
    eintrag = gespeichert && gespeichert[JARVIS_ABLAGE_LETZTE];
  } catch (fehler) {
    eintrag = null;
  }
  if (!eintrag || typeof eintrag.zeit !== 'number') {
    return;
  }
  const alter = Date.now() - eintrag.zeit;
  if (alter > POPUP_ALTER_MS || (eintrag.zustand === 'laeuft' && alter > POPUP_HAENGT_MS)) {
    return;
  }
  popupZeigen(eintrag);
  if (eintrag.zustand !== 'laeuft') {
    try {
      chrome.action.setBadgeText({ text: '' });
    } catch (fehler) {
      // Nur Zierde.
    }
  }
}

/** Schreibt Stand oder Ergebnis in den Antwortbereich - nur als Text. */
function popupZeigen(eintrag) {
  const bereich = popupTeile.bereich;
  const auftrag = eintrag.auftrag || 'frage';
  popupVerstummen();
  bereich.hidden = false;
  bereich.classList.remove('denkt', 'fehler');
  if (auftrag === 'frage' && eintrag.frage) {
    popupTeile.antwortfrage.textContent = 'Frage: ' + eintrag.frage;
    popupTeile.antwortfrage.hidden = false;
  } else {
    popupTeile.antwortfrage.textContent = '';
    popupTeile.antwortfrage.hidden = true;
  }
  if (eintrag.zustand === 'laeuft') {
    bereich.classList.add('denkt');
    popupTeile.marke.textContent = POPUP_NAMEN[auftrag] || 'Antwort';
    popupTeile.antwort.textContent = POPUP_WARTETEXTE[auftrag] || 'Jarvis denkt nach …';
    popupTeile.vorlesen.hidden = true;
    return;
  }
  if (eintrag.ok) {
    popupTeile.marke.textContent = POPUP_NAMEN[auftrag] || 'Antwort';
    popupTeile.antwort.textContent = eintrag.antwort || '';
    popupTeile.vorlesen.hidden = !window.speechSynthesis || !eintrag.antwort;
  } else {
    bereich.classList.add('fehler');
    popupTeile.marke.textContent = 'Hat nicht geklappt';
    popupTeile.antwort.textContent = eintrag.fehler || 'Unbekannter Fehler.';
    popupTeile.vorlesen.hidden = true;
  }
}

/** Ein Auftrag aus dem Popup: Seite lesen, an den Hintergrund geben, Ergebnis zeigen. */
async function popupAuftrag(auftrag) {
  if (popupBeschaeftigt) {
    return;
  }
  let frage = '';
  if (auftrag === 'frage') {
    frage = popupTeile.frage.value.trim();
    if (!frage) {
      popupZeigen({ zustand: 'fertig', ok: false, auftrag: auftrag, fehler: 'Bitte zuerst eine Frage eingeben.' });
      popupTeile.frage.focus();
      return;
    }
  }
  popupBeschaeftigt = true;
  popupKnoepfeSetzen();
  popupZeigen({ zustand: 'laeuft', auftrag: auftrag, frage: frage });

  let ergebnis = null;
  let angaben = {
    frage: frage,
    titel: popupTab && popupTab.title || '',
    adresse: popupTab && popupTab.url || ''
  };
  if (popupTab && popupSeiteLesbar) {
    const seite = await jarvisTabLesen(popupTab.id, auftrag === 'kontakte');
    if (seite.ok) {
      angaben = {
        frage: frage, titel: seite.titel, adresse: seite.adresse, text: seite.text,
        auswahl: seite.auswahl, kontaktlinks: seite.kontaktlinks
      };
    } else if (auftrag !== 'frage') {
      ergebnis = seite;
    }
  } else if (auftrag !== 'frage') {
    ergebnis = { ok: false, fehler: 'Diese Seite kann Jarvis nicht lesen. Öffne eine normale Webseite.' };
  }

  if (!ergebnis) {
    try {
      ergebnis = await chrome.runtime.sendMessage({ typ: 'jarvis-senden', auftrag: auftrag, angaben: angaben });
    } catch (fehler) {
      ergebnis = null;
    }
    if (!ergebnis) {
      ergebnis = { ok: false, fehler: 'Die Verbindung zur Erweiterung ist abgebrochen. Bitte noch einmal versuchen.' };
    }
  }

  popupBeschaeftigt = false;
  popupKnoepfeSetzen();
  popupZeigen({
    zustand: 'fertig', auftrag: auftrag, frage: frage, ok: Boolean(ergebnis.ok),
    antwort: ergebnis.antwort || '', fehler: ergebnis.fehler || ''
  });
  if (ergebnis.ok) {
    if (auftrag === 'frage') {
      popupTeile.frage.value = '';
    }
    try {
      chrome.action.setBadgeText({ text: '' });
    } catch (fehler) {
      // Nur Zierde.
    }
  }
}

/** Liest die Antwort vor - deutsche Stimme, in kurzen Stücken. */
function popupVorlesen() {
  const sprechen = window.speechSynthesis;
  if (!sprechen) {
    return;
  }
  if (popupSpricht) {
    popupVerstummen();
    return;
  }
  const stuecke = jarvisVorleseStuecke(popupTeile.antwort.textContent);
  if (!stuecke.length) {
    return;
  }
  const stimme = jarvisStimmeWaehlen(sprechen.getVoices());
  sprechen.cancel();
  stuecke.forEach(function (stueck, nummer) {
    const aeusserung = new SpeechSynthesisUtterance(stueck);
    aeusserung.lang = stimme ? stimme.lang : 'de-AT';
    if (stimme) {
      aeusserung.voice = stimme;
    }
    if (nummer === stuecke.length - 1) {
      aeusserung.onend = popupVerstummen;
      aeusserung.onerror = popupVerstummen;
    }
    sprechen.speak(aeusserung);
  });
  popupSpricht = true;
  popupTeile.vorlesen.textContent = 'Stopp';
}

function popupVerstummen() {
  if (popupSpricht && window.speechSynthesis) {
    popupSpricht = false;
    window.speechSynthesis.cancel();
  }
  popupSpricht = false;
  popupTeile.vorlesen.textContent = 'Vorlesen';
}
