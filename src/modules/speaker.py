#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Stimmprofil - erkennt, ob gerade der Nutzer spricht.

**Ehrliche Einordnung, die auch so in der Anleitung steht:** Das unterscheidet
Sprecher im Alltag zuverlässig, ist aber *kein* Schutz gegen eine abgespielte
Aufnahme. Wer eine Sprachaufnahme des Nutzers besitzt, kommt hier durch.

Deshalb gilt im ganzen Programm: Die Stimme entscheidet nur, **ob Jarvis
zuhört**. Sie gibt niemals eine Mail, eine Buchung oder eine Bildschirmaktion
frei - dafür ist ausschließlich die ausdrückliche Freigabe zuständig.
"""

import json
import os
import time

import config

try:
    import numpy as np
except ImportError:
    np = None

try:
    from resemblyzer import VoiceEncoder, preprocess_wav
except ImportError:
    VoiceEncoder = None
    preprocess_wav = None

PROFIL_DATEI = "stimmprofil.json"
PROBEN_ANZAHL = 5

# Sätze, die der Nutzer beim Einlernen nachspricht - unterschiedlich lang und
# klanglich verschieden, das macht das Profil stabiler.
LERNSAETZE = [
    "Hey Jarvis, wie sieht mein Tag aus?",
    "Ich war heute bei einem Kunden und wir haben über den Preis gesprochen.",
    "Erfass bitte die Quittung von der Tankstelle.",
    "Was ist diese Woche noch offen bei mir?",
    "Feierabend, mach den Abendrückblick.",
]


class Sprecherprofil:
    """Legt ein Stimmprofil an und vergleicht spätere Aufnahmen damit."""

    def __init__(self, verzeichnis=None):
        self.verzeichnis = str(verzeichnis or config.PROFIL_VERZEICHNIS)
        self.pfad = os.path.join(self.verzeichnis, PROFIL_DATEI)
        self._encoder = None
        self.profil = self._profil_laden()

    # -- Verfügbarkeit ------------------------------------------------------

    def verfuegbar(self) -> bool:
        """Ist die Stimmerkennung technisch nutzbar?"""
        return VoiceEncoder is not None and np is not None

    def eingelernt(self) -> bool:
        """Liegt bereits ein Profil vor?"""
        return bool(self.profil)

    def zustand(self) -> dict:
        """Kurzer Überblick für den Selbsttest."""
        return {"paket_da": self.verfuegbar(), "profil_da": self.eingelernt(),
                "schwelle": config.STIMM_SCHWELLE, "pfad": self.pfad,
                "aktiv": bool(config.STIMMPRUEFUNG_AN)}

    # -- Profil laden und speichern ----------------------------------------

    def _profil_laden(self):
        """Liest ein vorhandenes Profil von der Platte."""
        try:
            if os.path.exists(self.pfad):
                with open(self.pfad, "r", encoding="utf-8") as datei:
                    daten = json.load(datei)
                vektor = daten.get("vektor")
                if vektor and np is not None:
                    return np.array(vektor, dtype="float32")
                return vektor
        except (OSError, ValueError) as fehler:
            print("[stimme] Stimmprofil nicht lesbar: %s" % fehler)
        return None

    def _profil_speichern(self, vektor) -> bool:
        """Schreibt das Profil auf die Platte."""
        try:
            os.makedirs(self.verzeichnis, exist_ok=True)
            with open(self.pfad, "w", encoding="utf-8") as datei:
                json.dump({"vektor": [float(wert) for wert in vektor],
                           "angelegt": time.strftime("%Y-%m-%d %H:%M:%S")},
                          datei)
            return True
        except (OSError, ValueError) as fehler:
            print("[stimme] Stimmprofil nicht speicherbar: %s" % fehler)
            return False

    def profil_loeschen(self) -> bool:
        """Verwirft das Stimmprofil."""
        self.profil = None
        try:
            if os.path.exists(self.pfad):
                os.remove(self.pfad)
            return True
        except OSError:
            return False

    # -- Einlernen ----------------------------------------------------------

    def _encoder_holen(self):
        """Lädt das Sprechermodell einmalig."""
        if self._encoder is None and VoiceEncoder is not None:
            self._encoder = VoiceEncoder()
        return self._encoder

    def vektor_aus_datei(self, wav_pfad: str):
        """Rechnet eine Aufnahme in einen Stimmvektor um."""
        if not self.verfuegbar() or not wav_pfad or not os.path.exists(wav_pfad):
            return None
        try:
            welle = preprocess_wav(wav_pfad)
            return self._encoder_holen().embed_utterance(welle)
        except Exception as fehler:
            print("[stimme] Aufnahme nicht auswertbar: %s" % fehler)
            return None

    def einlernen(self, stimme=None) -> dict:
        """Nimmt fünf Proben auf, mittelt die Vektoren und legt das Profil ab."""
        if not self.verfuegbar():
            return {"ok": False,
                    "fehler": "Für die Stimmerkennung fehlt das Paket resemblyzer. "
                              "Ohne sie funktioniert alles andere weiter."}
        if stimme is None:
            return {"ok": False, "fehler": "Zum Einlernen brauche ich das Mikrofon."}
        if not stimme.mikrofon_bereit():
            return {"ok": False,
                    "fehler": "Das Mikrofon ist nicht verfügbar. Bitte in den "
                              "Systemeinstellungen unter Datenschutz freigeben."}

        vektoren = []
        stimme.sprich("Ich lerne jetzt deine Stimme. Sprich mir bitte fünf Sätze nach.")
        for nummer in range(PROBEN_ANZAHL):
            satz = LERNSAETZE[nummer % len(LERNSAETZE)]
            stimme.sprich("Satz %d von %d. %s" % (nummer + 1, PROBEN_ANZAHL, satz))
            pfad = stimme.aufnehmen_bis_pause()
            if not pfad:
                stimme.sprich("Da war nichts zu hören. Ich versuche es noch einmal.")
                pfad = stimme.aufnehmen_bis_pause()
            vektor = self.vektor_aus_datei(pfad) if pfad else None
            if pfad:
                try:
                    os.remove(pfad)
                except OSError:
                    pass
            if vektor is None:
                stimme.sprich("Diese Probe war unbrauchbar, ich überspringe sie.")
                continue
            vektoren.append(vektor)

        if len(vektoren) < 3:
            return {"ok": False,
                    "fehler": "Ich habe nur %d brauchbare Proben bekommen. Bitte in "
                              "einer ruhigeren Umgebung noch einmal versuchen."
                              % len(vektoren)}

        gemittelt = np.mean(np.stack(vektoren), axis=0)
        gemittelt = gemittelt / (np.linalg.norm(gemittelt) + 1e-9)
        self.profil = gemittelt
        gespeichert = self._profil_speichern(gemittelt)
        return {"ok": gespeichert, "proben": len(vektoren),
                "text": "Stimmprofil aus %d Proben angelegt. Ab jetzt reagiere ich "
                        "bevorzugt auf deine Stimme." % len(vektoren)}

    # -- Prüfen -------------------------------------------------------------

    def aehnlichkeit(self, wav_pfad: str):
        """Kosinus-Ähnlichkeit einer Aufnahme zum Profil, oder ``None``."""
        if self.profil is None or not self.verfuegbar():
            return None
        vektor = self.vektor_aus_datei(wav_pfad)
        if vektor is None:
            return None
        try:
            a = np.asarray(vektor, dtype="float32")
            b = np.asarray(self.profil, dtype="float32")
            wert = float(np.dot(a, b) / ((np.linalg.norm(a) * np.linalg.norm(b)) + 1e-9))
            return wert
        except Exception:
            return None

    def ist_der_nutzer(self, wav_pfad: str) -> dict:
        """Entscheidet, ob die Aufnahme vom Nutzer stammt.

        Ohne Profil oder ohne Paket lautet die Antwort immer ja - die Prüfung
        darf niemand aussperren, den sie gar nicht beurteilen kann.
        """
        if not config.STIMMPRUEFUNG_AN or self.profil is None or not self.verfuegbar():
            return {"erkannt": True, "wert": None, "grund": "Stimmprüfung ist nicht aktiv."}
        wert = self.aehnlichkeit(wav_pfad)
        if wert is None:
            return {"erkannt": True, "wert": None,
                    "grund": "Die Aufnahme war nicht auswertbar - ich höre trotzdem zu."}
        erkannt = wert >= float(config.STIMM_SCHWELLE)
        return {"erkannt": erkannt, "wert": round(wert, 3),
                "grund": ("Stimme passt (%.2f)" % wert) if erkannt
                         else ("Fremde Stimme (%.2f unter Schwelle %.2f)"
                               % (wert, config.STIMM_SCHWELLE))}
