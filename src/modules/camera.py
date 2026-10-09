#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Kamera - ein Einzelbild aufnehmen und von Claude beschreiben lassen.

Damit sieht Jarvis den Nutzer, einen vorgehaltenen Beleg oder ein Objekt.

**Ehrliche Grenze:** Das ist ein Einzelbild auf Zuruf. Kein Dauervideo, keine
Überwachung, keine Aufzeichnung im Hintergrund. Das Bild wird nach der
Auswertung gelöscht, außer der Nutzer will es ausdrücklich behalten.

Das Kamera-Recht muss dem Terminal unter Systemeinstellungen, Datenschutz,
Kamera erteilt sein. Die Ersteinrichtung weist darauf hin.
"""

import base64
import os
import shutil
import subprocess
import time

import config


class Kamera:
    """Nimmt Einzelbilder auf und lässt sie von Claude beschreiben."""

    def __init__(self):
        self.letzter_fehler = ""

    # -- Verfügbarkeit ------------------------------------------------------

    @staticmethod
    def werkzeug_vorhanden() -> str:
        """Welches Aufnahmeprogramm ist da? ``imagesnap``, ``ffmpeg`` oder nichts."""
        if shutil.which("imagesnap"):
            return "imagesnap"
        if shutil.which("ffmpeg"):
            return "ffmpeg"
        return ""

    def verfuegbar(self) -> bool:
        """Kann überhaupt ein Bild aufgenommen werden?"""
        return bool(self.werkzeug_vorhanden())

    def zustand(self) -> dict:
        """Kurzer Überblick für den Selbsttest."""
        return {"programm": self.werkzeug_vorhanden() or "keines",
                "verfuegbar": self.verfuegbar()}

    # -- Aufnahme -----------------------------------------------------------

    def bild_aufnehmen(self, ziel: str = "") -> dict:
        """Nimmt ein Einzelbild der eingebauten Kamera auf."""
        programm = self.werkzeug_vorhanden()
        if not programm:
            self.letzter_fehler = (
                "Ich sehe über die Kamera im Browser: Sag einfach 'schau mal' oder "
                "'was siehst du' im Jarvis-Fenster, dann mache ich ein Bild.")
            return {"ok": False, "fehler": self.letzter_fehler}

        try:
            config.BELEGE_VERZEICHNIS.mkdir(parents=True, exist_ok=True)
        except OSError:
            pass
        ziel = ziel or str(config.BELEGE_VERZEICHNIS /
                           ("kamera_%d.jpg" % int(time.time())))

        if programm == "imagesnap":
            # -w wartet kurz, damit sich die Kamera an das Licht anpassen kann.
            befehl = ["imagesnap", "-q", "-w", "1", ziel]
        else:
            befehl = ["ffmpeg", "-y", "-f", "avfoundation", "-framerate", "30",
                      "-video_size", "1280x720", "-i", "0", "-frames:v", "1", ziel]

        try:
            ergebnis = subprocess.run(befehl, capture_output=True, timeout=30, shell=False)
        except subprocess.TimeoutExpired:
            self.letzter_fehler = "Die Kamera hat nicht rechtzeitig geantwortet."
            return {"ok": False, "fehler": self.letzter_fehler}
        except (OSError, subprocess.SubprocessError) as fehler:
            self.letzter_fehler = "Die Aufnahme ist fehlgeschlagen: %s" % fehler
            return {"ok": False, "fehler": self.letzter_fehler}

        if not os.path.exists(ziel) or os.path.getsize(ziel) < 1000:
            fehlertext = (ergebnis.stderr or b"").decode("utf-8", errors="replace")[-300:]
            self.letzter_fehler = (
                "Es ist kein Bild entstanden. Meist fehlt das Kamera-Recht: "
                "Systemeinstellungen, Datenschutz und Sicherheit, Kamera - dort das "
                "Terminal erlauben und das Terminal neu starten. %s" % fehlertext)
            return {"ok": False, "fehler": self.letzter_fehler}
        return {"ok": True, "pfad": ziel}

    # -- Umschauen ----------------------------------------------------------

    def umschauen(self, frage: str = "", agent=None, behalten: bool = False) -> dict:
        """Nimmt ein Bild auf und beschreibt, was darauf zu sehen ist."""
        aufnahme = self.bild_aufnehmen()
        if not aufnahme.get("ok"):
            return aufnahme
        pfad = aufnahme["pfad"]

        if agent is None or not getattr(agent, "einsatzbereit", lambda: False)():
            if not behalten:
                self._aufraeumen(pfad)
            return {"ok": False,
                    "fehler": "Ich habe ein Bild gemacht, kann es ohne Anthropic-Schlüssel "
                              "aber nicht auswerten."}

        try:
            with open(pfad, "rb") as datei:
                rohbild = base64.b64encode(datei.read()).decode("ascii")
        except OSError as fehler:
            self._aufraeumen(pfad)
            return {"ok": False, "fehler": "Das Bild ist nicht lesbar: %s" % fehler}

        auftrag = (frage or "Was ist auf diesem Bild zu sehen?").strip()
        auftrag += ("\n\nAntworte in zwei bis vier Sätzen, gesprochen, ohne Aufzählungen. "
                    "Beschreibe nur, was wirklich zu sehen ist. Bist du dir bei etwas "
                    "nicht sicher, sag das.")
        antwort = agent.text_anfrage(auftrag, bild_base64=rohbild, bild_typ="image/jpeg")

        if not behalten:
            self._aufraeumen(pfad)
        if not antwort.get("ok"):
            return {"ok": False, "fehler": antwort.get("fehler", "Auswertung fehlgeschlagen.")}
        return {"ok": True, "text": antwort["text"],
                "bild": pfad if behalten else "", "behalten": behalten}

    @staticmethod
    def _aufraeumen(pfad: str):
        """Löscht das Bild nach der Auswertung."""
        try:
            if pfad and os.path.exists(pfad):
                os.remove(pfad)
        except OSError:
            pass
