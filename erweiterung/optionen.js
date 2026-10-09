/*
 * Jarvis-Erweiterung - Einstellungen: Jarvis-Adresse und Zugangsschlüssel.
 *
 * Gespeichert wird in chrome.storage.local, also nur in diesem Browser.
 * Fremde Adressen werden abgelehnt (siehe jarvisAdresseSaeubern): Die
 * Erweiterung soll Seiteninhalte nie an einen anderen Rechner schicken.
 */
'use strict';

const optionenTeile = {
  formular: document.getElementById('formular'),
  adresse: document.getElementById('adresse'),
  schluessel: document.getElementById('schluessel'),
  zeigen: document.getElementById('zeigen'),
  testen: document.getElementById('testen'),
  meldung: document.getElementById('meldung'),
  kennung: document.getElementById('kennung')
};

optionenStarten();

async function optionenStarten() {
  const einstellungen = await jarvisEinstellungenLesen();
  optionenTeile.adresse.value = einstellungen.adresse;
  optionenTeile.schluessel.value = einstellungen.schluessel;
  optionenTeile.kennung.textContent = 'Erweiterungs-ID: ' + chrome.runtime.id;

  optionenTeile.zeigen.addEventListener('change', function () {
    optionenTeile.schluessel.type = optionenTeile.zeigen.checked ? 'text' : 'password';
  });
  optionenTeile.formular.addEventListener('submit', async function (ereignis) {
    ereignis.preventDefault();
    const ergebnis = await jarvisEinstellungenSpeichern(optionenTeile.adresse.value,
      optionenTeile.schluessel.value);
    if (ergebnis.ok) {
      optionenTeile.adresse.value = ergebnis.adresse;
    }
    optionenMelden(ergebnis);
  });
  optionenTeile.testen.addEventListener('click', async function () {
    optionenTeile.testen.disabled = true;
    optionenMelden({ ok: true, text: 'Frage Jarvis …' });
    try {
      optionenMelden(await jarvisVerbindungTesten(optionenTeile.adresse.value,
        optionenTeile.schluessel.value));
    } finally {
      optionenTeile.testen.disabled = false;
    }
  });
}

function optionenMelden(ergebnis) {
  const meldung = optionenTeile.meldung;
  meldung.classList.toggle('gut', Boolean(ergebnis.ok));
  meldung.classList.toggle('schlecht', !ergebnis.ok);
  meldung.textContent = ergebnis.ok ? (ergebnis.text || 'Erledigt.') : (ergebnis.fehler || 'Hat nicht geklappt.');
}
