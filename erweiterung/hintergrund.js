/*
 * Jarvis-Erweiterung - Hintergrunddienst (Service Worker).
 *
 * Warum das Senden hier läuft und nicht im Popup: Ein Popup schließt sich,
 * sobald man daneben klickt - eine Anfrage, die dort hängt, wäre dann weg.
 * Der Hintergrunddienst arbeitet weiter, legt das Ergebnis in
 * chrome.storage.session ab, und das Popup zeigt es beim nächsten Öffnen.
 *
 * Das Kontextmenü "Mit Jarvis besprechen" schickt markierten Text als Frage.
 * Die Antwort erscheint in einem kleinen Kasten unten rechts in der Seite -
 * gebaut nur mit textContent in einem geschlossenen Shadow-DOM, damit weder
 * das Seitendesign noch Skripte der Seite an die Antwort kommen. Geht das
 * nicht (Browserseiten, PDF), öffnet sich das Popup bzw. ein kleines Fenster.
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

/** Kontextmenü: markierten Text als Frage an Jarvis. */
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

  // Zuerst sichtbar machen, dass Jarvis arbeitet - Denken dauert.
  const imKasten = tabId !== null && await hintergrundKasten(tabId, 'denkt',
    'Jarvis denkt nach über: „' + jarvisKuerzen(auswahl, 140) + (auswahl.length > 140 ? ' …“' : '“'));
  if (!imKasten) {
    // Erst den Stand ablegen, dann das Popup öffnen - es zeigt "denkt nach".
    await hintergrundMerken({
      kennung: 'menue', auftrag: 'frage', frage: jarvisKuerzen(auswahl, 300),
      titel: angaben.titel, adresse: angaben.adresse, zustand: 'laeuft', zeit: Date.now()
    });
    await hintergrundPopupOeffnen(tabId);
  }

  if (tabId !== null) {
    const seite = await jarvisTabLesen(tabId, false);
    if (seite.ok) {
      angaben.titel = seite.titel || angaben.titel;
      angaben.adresse = seite.adresse || angaben.adresse;
      angaben.text = seite.text;
    }
  }

  const ergebnis = await hintergrundAusfuehren('frage', angaben);
  if (imKasten) {
    const gezeigt = await hintergrundKasten(tabId, ergebnis.ok ? 'fertig' : 'fehler',
      ergebnis.ok ? ergebnis.antwort : ergebnis.fehler);
    if (!gezeigt) {
      // Die Seite wurde inzwischen verlassen - dann eben im Popup.
      await hintergrundPopupOeffnen(tabId);
    }
  }
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

/** Zeigt den Antwortkasten in der Seite oder aktualisiert ihn. */
async function hintergrundKasten(tabId, zustand, text) {
  try {
    const ergebnisse = await chrome.scripting.executeScript({
      target: { tabId: tabId },
      func: hintergrundKastenInSeite,
      args: [zustand, String(text || '')]
    });
    return Boolean(ergebnisse && ergebnisse[0] && ergebnisse[0].result);
  } catch (fehler) {
    return false;
  }
}

/**
 * Läuft IN der Seite (eigene, isolierte Welt der Erweiterung). Baut einen Kasten
 * in einem geschlossenen Shadow-DOM - nur mit textContent, nie mit innerHTML.
 * Die Stile kommen über einen CSSStyleSheet-Baustein: der greift auch auf Seiten
 * mit strenger CSP, die eingefügte <style>-Elemente verbieten.
 */
function hintergrundKastenInSeite(zustand, text) {
  let ablage = window.__jarvisKasten;
  if (!ablage || !ablage.wirt.isConnected) {
    const wirt = document.createElement('jarvis-antwort');
    const schatten = wirt.attachShadow({ mode: 'closed' });
    const regeln = ':host{all:initial !important;position:fixed !important;right:16px !important;'
      + 'bottom:16px !important;z-index:2147483647 !important;display:block !important}'
      + '.kasten{box-sizing:border-box;width:min(380px,calc(100vw - 32px));max-height:min(60vh,520px);'
      + 'display:flex;flex-direction:column;background:#03080F;color:#E4F7FF;'
      + 'border:1px solid #16425C;border-radius:14px;box-shadow:0 12px 40px rgba(0,0,0,.55),'
      + '0 0 0 1px rgba(58,209,255,.08),0 0 24px rgba(58,209,255,.12);'
      + 'font:14px/1.5 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,"Helvetica Neue",Arial,sans-serif;'
      + 'text-align:left;overflow:hidden}'
      + '.kopf{display:flex;align-items:center;gap:8px;padding:10px 12px;border-bottom:1px solid #0E2A3C}'
      + '.punkt{width:9px;height:9px;border-radius:50%;background:#3AD1FF;box-shadow:0 0 8px #3AD1FF}'
      + '.kasten[data-zustand="denkt"] .punkt{animation:puls 1.1s ease-in-out infinite}'
      + '.kasten[data-zustand="fehler"] .punkt{background:#E5484D;box-shadow:0 0 8px #E5484D}'
      + '@keyframes puls{50%{opacity:.25}}'
      + '.marke{flex:1;font-size:12px;font-weight:600;letter-spacing:.18em;color:#3AD1FF}'
      + 'button{font:inherit;cursor:pointer;color:#E4F7FF;background:#071420;border:1px solid #16425C;'
      + 'border-radius:8px;padding:4px 10px}'
      + 'button:hover{border-color:#3AD1FF}'
      + 'button:focus-visible{outline:2px solid #3AD1FF;outline-offset:2px}'
      + '.zu{padding:2px 8px;font-size:16px;line-height:1}'
      + '.inhalt{padding:12px;overflow:auto;white-space:pre-wrap;overflow-wrap:anywhere;user-select:text}'
      + '.kasten[data-zustand="denkt"] .inhalt{color:#8DB4C6}'
      + '.kasten[data-zustand="fehler"] .inhalt{color:#FFB4B0}'
      + '.fuss{display:flex;justify-content:flex-end;gap:8px;padding:0 12px 12px}'
      + '[hidden]{display:none !important}';

    const kasten = document.createElement('div');
    kasten.className = 'kasten';
    kasten.setAttribute('role', 'dialog');
    kasten.setAttribute('aria-label', 'Antwort von Jarvis');
    const kopf = document.createElement('div');
    kopf.className = 'kopf';
    const punkt = document.createElement('span');
    punkt.className = 'punkt';
    const marke = document.createElement('span');
    marke.className = 'marke';
    marke.textContent = 'JARVIS';
    const zu = document.createElement('button');
    zu.className = 'zu';
    zu.type = 'button';
    zu.textContent = '×';
    zu.title = 'Schließen';
    zu.setAttribute('aria-label', 'Schließen');
    kopf.append(punkt, marke, zu);
    const inhalt = document.createElement('div');
    inhalt.className = 'inhalt';
    inhalt.setAttribute('aria-live', 'polite');
    const fuss = document.createElement('div');
    fuss.className = 'fuss';
    const vorlesen = document.createElement('button');
    vorlesen.type = 'button';
    vorlesen.textContent = 'Vorlesen';
    fuss.append(vorlesen);
    kasten.append(kopf, inhalt, fuss);

    try {
      const blatt = new CSSStyleSheet();
      blatt.replaceSync(regeln);
      schatten.adoptedStyleSheets = [blatt];
    } catch (fehler) {
      const stil = document.createElement('style');
      stil.textContent = regeln;
      schatten.append(stil);
    }
    schatten.append(kasten);

    const sprechen = window.speechSynthesis;
    function verstummen() {
      try { sprechen.cancel(); } catch (fehler) { /* nichts */ }
      vorlesen.textContent = 'Vorlesen';
    }
    zu.addEventListener('click', function () {
      verstummen();
      wirt.remove();
    });
    vorlesen.addEventListener('click', function () {
      if (!sprechen) {
        return;
      }
      if (sprechen.speaking || sprechen.pending) {
        verstummen();
        return;
      }
      const sauber = String(inhalt.textContent || '').replace(/[*_#`>|]+/g, ' ').replace(/\s+/g, ' ').trim();
      const saetze = sauber.match(/[^.!?;:]+[.!?;:]*\s*/g) || [sauber];
      const stimmen = sprechen.getVoices().filter(function (s) { return /^de([-_]|$)/i.test(s.lang || ''); });
      stimmen.sort(function (a, b) {
        function wert(s) {
          return (/^de[-_]AT/i.test(s.lang) ? 4 : 0) + (/^de[-_]DE/i.test(s.lang) ? 2 : 0)
            + (s.localService ? 3 : 0);
        }
        return wert(b) - wert(a);
      });
      const stuecke = [];
      let aktuell = '';
      saetze.forEach(function (satz) {
        if ((aktuell + satz).length > 220 && aktuell) {
          stuecke.push(aktuell);
          aktuell = '';
        }
        aktuell += satz;
      });
      if (aktuell.trim()) {
        stuecke.push(aktuell);
      }
      stuecke.forEach(function (stueck, nummer) {
        const aeusserung = new SpeechSynthesisUtterance(stueck.trim());
        aeusserung.lang = stimmen[0] ? stimmen[0].lang : 'de-AT';
        if (stimmen[0]) {
          aeusserung.voice = stimmen[0];
        }
        if (nummer === stuecke.length - 1) {
          aeusserung.onend = verstummen;
          aeusserung.onerror = verstummen;
        }
        sprechen.speak(aeusserung);
      });
      vorlesen.textContent = 'Stopp';
    });
    (document.body || document.documentElement).append(wirt);
    ablage = window.__jarvisKasten = { wirt: wirt, kasten: kasten, inhalt: inhalt, vorlesen: vorlesen };
  }
  ablage.kasten.setAttribute('data-zustand', zustand);
  ablage.inhalt.textContent = text;
  ablage.vorlesen.hidden = zustand !== 'fertig';
  return true;
}
