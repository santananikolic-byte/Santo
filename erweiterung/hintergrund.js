/*
 * Jarvis-Erweiterung - Hintergrunddienst (Service Worker).
 *
 * Warum das Senden hier läuft und nicht im Popup: Ein Popup schließt sich,
 * sobald man daneben klickt - eine Anfrage, die dort hängt, wäre dann weg.
 * Der Hintergrunddienst arbeitet weiter, legt das Ergebnis in
 * chrome.storage.session ab, und das Popup zeigt es beim nächsten Öffnen.
 *
 * Das Kontextmenü "Mit Jarvis besprechen" schickt markierten Text mit. Die
 * Antwort erscheint im Jarvis-Fenster der Erweiterung, nie in der Seite selbst.
 *
 * Nachrichten werden nur von den eigenen Seiten der Erweiterung angenommen;
 * Webseiten können über diese Erweiterung nichts an Jarvis schicken.
 */
'use strict';

importScripts('gemeinsam.js');

const HINTERGRUND_MENUE = 'jarvis-besprechen';
// Chrome beendet einen Hintergrunddienst, der 30 Sekunden auf eine Antwort
// wartet. Ein harmloser Aufruf alle 20 Sekunden hält ihn wach.
const HINTERGRUND_WACH_MS = 20000;

chrome.runtime.onInstalled.addListener(function () {
  chrome.contextMenus.removeAll(function () {
    chrome.contextMenus.create({
      id: HINTERGRUND_MENUE,
      title: 'Mit Jarvis besprechen',
      contexts: ['selection']
    });
  });
});

chrome.contextMenus.onClicked.addListener(function (info, tab) {
  if (info.menuItemId === HINTERGRUND_MENUE) {
    hintergrundBesprechen(info, tab);
  }
});

chrome.runtime.onMessage.addListener(function (nachricht, absender, antworten) {
  if (!hintergrundEigeneSeite(absender) || !nachricht || nachricht.typ !== 'jarvis-senden') {
    return false;
  }
  hintergrundAusfuehren(nachricht.auftrag, nachricht.angaben || {})
    .then(antworten, function () {
      antworten({ ok: false, fehler: 'In der Erweiterung ist etwas schiefgegangen.' });
    });
  return true; // Die Antwort kommt später.
});

/** Kommt die Nachricht von einer Seite dieser Erweiterung (Popup, Einstellungen)? */
function hintergrundEigeneSeite(absender) {
  if (!absender || absender.id !== chrome.runtime.id) {
    return false;
  }
  return String(absender.url || '').indexOf(chrome.runtime.getURL('')) === 0;
}

/** Schreibt den Stand der letzten Anfrage - das Popup liest ihn. */
async function hintergrundMerken(eintrag) {
  try {
    await chrome.storage.session.set({ [JARVIS_ABLAGE_LETZTE]: eintrag });
  } catch (fehler) {
    // Ohne Sitzungsablage zeigt das Popup eben nichts Altes an.
  }
}

function hintergrundAbzeichen(text) {
  try {
    chrome.action.setBadgeBackgroundColor({ color: text === '!' ? '#E5484D' : '#3AD1FF' });
    chrome.action.setBadgeText({ text: text });
  } catch (fehler) {
    // Nur Zierde.
  }
}

/** Schickt einen Auftrag an Jarvis und legt Stand und Ergebnis ab. */
async function hintergrundAusfuehren(auftrag, angaben) {
  const kennung = Date.now().toString(36) + Math.random().toString(36).slice(2, 8);
  const grund = {
    kennung: kennung,
    auftrag: auftrag,
    frage: jarvisKuerzen(angaben.frage, 300),
    titel: jarvisKuerzen(angaben.titel, 200),
    adresse: jarvisKuerzen(angaben.adresse, 400)
  };
  await hintergrundMerken(Object.assign({}, grund, { zustand: 'laeuft', zeit: Date.now() }));
  hintergrundAbzeichen('…');
  const wach = setInterval(function () {
    chrome.runtime.getPlatformInfo(function () {});
  }, HINTERGRUND_WACH_MS);
  let ergebnis;
  try {
    ergebnis = await jarvisSenden(auftrag, angaben);
  } catch (fehler) {
    ergebnis = { ok: false, fehler: 'In der Erweiterung ist etwas schiefgegangen.' };
  } finally {
    clearInterval(wach);
  }
  await hintergrundMerken(Object.assign({}, grund, {
    zustand: 'fertig',
    ok: Boolean(ergebnis.ok),
    antwort: ergebnis.ok ? ergebnis.antwort : '',
    fehler: ergebnis.ok ? '' : ergebnis.fehler,
    zeit: Date.now()
  }));
  hintergrundAbzeichen(ergebnis.ok ? '' : '!');
  return Object.assign({ kennung: kennung }, ergebnis);
}

/**
 * Kontextmenü: markierten Text mit Jarvis besprechen.
 *
 * Die Antwort erscheint nur im eigenen Fenster der Erweiterung, nie in der Seite:
 * Was Jarvis sagt, kann aus deinem Gedächtnis stammen - das hat in einer fremden
 * Seite nichts verloren, auch nicht in einem abgeschotteten Kasten.
 */
async function hintergrundBesprechen(info, tab) {
  const auswahl = jarvisKuerzen(info.selectionText, JARVIS_GRENZEN.auswahl);
  if (!auswahl) {
    return;
  }
  const tabId = tab && typeof tab.id === 'number' && tab.id >= 0 ? tab.id : null;
  // Der markierte Text ist Inhalt der Seite, kein Auftrag: Er geht als "auswahl" mit,
  // die Frage selbst ist fest. So kann eine Seite Jarvis nichts unterschieben.
  const angaben = {
    frage: 'Ich habe auf dieser Seite Text markiert. Erklär mir kurz, was da steht '
      + 'und was das für mich und meinen Betrieb heißt.',
    auswahl: auswahl,
    titel: tab && tab.title || '',
    adresse: tab && tab.url || info.pageUrl || '',
    text: ''
  };

  // Zuerst das Fenster zeigen - es steht auf "denkt nach", bis die Antwort da ist.
  await hintergrundMerken({
    kennung: 'menue', auftrag: 'frage', frage: angaben.frage,
    titel: angaben.titel, adresse: angaben.adresse, zustand: 'laeuft', zeit: Date.now()
  });
  await hintergrundPopupOeffnen(tabId);

  if (tabId !== null) {
    const seite = await jarvisTabLesen(tabId, false);
    if (seite.ok) {
      angaben.titel = seite.titel || angaben.titel;
      angaben.adresse = seite.adresse || angaben.adresse;
      angaben.text = seite.text;
    }
  }
  await hintergrundAusfuehren('frage', angaben);
}

/** Öffnet das Popup; geht das nicht, ein kleines eigenes Fenster. */
async function hintergrundPopupOeffnen(tabId) {
  try {
    if (chrome.action && typeof chrome.action.openPopup === 'function') {
      await chrome.action.openPopup();
      return true;
    }
  } catch (fehler) {
    // Ältere Browser erlauben openPopup nicht - dann ein Fenster.
  }
  try {
    const ziel = 'popup.html?fenster=1' + (tabId !== null && tabId !== undefined ? '&tab=' + tabId : '');
    await chrome.windows.create({
      url: chrome.runtime.getURL(ziel), type: 'popup', width: 420, height: 640
    });
    return true;
  } catch (fehler) {
    return false;
  }
}
