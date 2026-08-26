#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Bildschirmsteuerung - sehen, klicken, tippen.

Vier Dinge, an denen die üblichen Anleitungen auf dem Mac scheitern:

1. **Retina-Skalierung.** Ein MacBook-Screenshot hat die doppelte Pixelzahl der
   logischen Bildschirmgröße. Ohne Umrechnung landet jeder Klick bei der Hälfte
   der Koordinate, also im linken oberen Viertel. Das ist der häufigste Grund,
   warum solche Skripte auf dem Mac scheinbar grundlos danebenklicken. Der
   Faktor wird gemessen (``bild.width / pyautogui.size().width``), nicht geraten.
2. **Bestätigung vor jedem Schritt.** Ein frei klickender Agent verschickt sonst
   etwas, bevor der Nutzer überhaupt reagieren kann.
3. **Kostenbremse.** Der Screenshot wird vor dem Senden auf 1400 Pixel Breite
   verkleinert. Ein Vollbild in Originalgröße kostet ein Vielfaches, ohne dass
   der Agent mehr erkennt. Ein Screenshot pro Schritt, nicht mehrere.
4. **Selbstabbruch.** Sieht der Agent eine Login-Maske, einen Bezahlvorgang oder
   eine Warnung, hält er an, statt weiterzuklicken.
"""

import base64
import io
import json
import os
import sys
import tempfile
import time

try:
    import pyautogui
except Exception:
    # Ohne Bildschirm (etwa auf einem Server) wirft pyautogui beim Import.
    pyautogui = None

try:
    from PIL import Image
except ImportError:
    Image = None

MAX_BREITE = 1400
MAX_SCHRITTE = 12

ERLAUBTE_AKTIONEN = ("click", "doubleclick", "type", "press", "hotkey",
                     "scroll", "wait", "done", "abbruch")

# Begriffe, bei denen der Agent von sich aus stehen bleibt.
STOPP_BEGRIFFE = ["passwort", "password", "anmelden", "login", "sign in",
                  "kreditkarte", "credit card", "bezahlen", "zahlung", "checkout",
                  "cvv", "iban", "zwei-faktor", "verifizierungscode", "warnung",
                  "endgültig löschen", "unwiderruflich"]

STEUER_PROMPT = """Du steuerst einen Mac über Screenshots. Du siehst das Bild und
gibst genau einen nächsten Schritt zurück.

Antworte ausschließlich als JSON, ohne Fließtext:
{"gedanke": "was du siehst und warum dieser Schritt", "aktion": "click",
 "x": 100, "y": 200, "text": "", "tasten": [], "richtung": 0}

Mögliche Aktionen:
  click        x und y setzen
  doubleclick  x und y setzen
  type         text setzen
  press        text ist der Tastenname, etwa enter oder tab
  hotkey       tasten als Liste, etwa ["command","s"]
  scroll       richtung negativ für nach unten
  wait         kurz warten
  done         Ziel erreicht, text enthält das Ergebnis
  abbruch      du kommst nicht weiter oder es wird heikel, text enthält den Grund

Koordinaten beziehen sich auf das Bild, das du gerade siehst.

Halte sofort mit abbruch an, wenn du eine Login-Maske, eine Passwortabfrage,
einen Bezahlvorgang oder eine Warnung vor unwiderruflichen Änderungen siehst.
Klicke niemals darüber hinweg.

Das Ziel: %s
"""


class Bildschirm:
    """Steuert den Mac über Screenshots - Schritt für Schritt, jeder bestätigt."""

    def __init__(self, agent=None):
        self.agent = agent
        self.letzter_fehler = ""
        if pyautogui is not None:
            # Maus in eine Bildschirmecke bricht alles ab - die Notbremse.
            pyautogui.FAILSAFE = True
            pyautogui.PAUSE = 0.3

    # -- Verfügbarkeit ------------------------------------------------------

    def verfuegbar(self) -> bool:
        """Ist die Bildschirmsteuerung technisch nutzbar?"""
        return pyautogui is not None and Image is not None

    def zustand(self) -> dict:
        """Kurzer Überblick für den Selbsttest."""
        zustand = {"pyautogui": pyautogui is not None, "pillow": Image is not None,
                   "skalierung": None, "bildschirm": None}
        if self.verfuegbar():
            try:
                groesse = pyautogui.size()
                zustand["bildschirm"] = "%dx%d" % (groesse.width, groesse.height)
                zustand["skalierung"] = self.skalierung_messen()
            except Exception as fehler:
                zustand["fehler"] = str(fehler)
        return zustand

    def skalierung_messen(self) -> float:
        """Misst den Retina-Faktor: Screenshot-Pixel geteilt durch logische Breite."""
        if not self.verfuegbar():
            return 1.0
        try:
            bild = pyautogui.screenshot()
            logisch = pyautogui.size()
            if not logisch.width:
                return 1.0
            return float(bild.width) / float(logisch.width)
        except Exception:
            return 1.0

    # -- Screenshot ---------------------------------------------------------

    def screenshot(self):
        """Nimmt einen Screenshot auf und verkleinert ihn auf 1400 Pixel Breite.

        Gibt ``(base64, faktor_bild_zu_logisch)`` zurück. Der Faktor rechnet
        Koordinaten aus dem gesendeten Bild direkt in Bildschirmkoordinaten um -
        Retina-Skalierung und Verkleinerung stecken beide darin.
        """
        if not self.verfuegbar():
            return None, 1.0
        try:
            bild = pyautogui.screenshot()
            logisch = pyautogui.size()
        except Exception as fehler:
            self.letzter_fehler = (
                "Ich kann keinen Screenshot machen: %s. In den Systemeinstellungen "
                "unter Datenschutz die Bildschirmaufnahme für das Terminal "
                "freigeben." % fehler)
            return None, 1.0

        original_breite = bild.width
        if original_breite > MAX_BREITE:
            neue_hoehe = int(bild.height * MAX_BREITE / float(original_breite))
            bild = bild.resize((MAX_BREITE, neue_hoehe), Image.LANCZOS)

        # Vom gesendeten Bild direkt auf die logische Bildschirmbreite.
        faktor = float(logisch.width) / float(bild.width)

        puffer = io.BytesIO()
        bild.convert("RGB").save(puffer, format="PNG", optimize=True)
        return base64.b64encode(puffer.getvalue()).decode("ascii"), faktor

    # -- Einzelaktionen -----------------------------------------------------

    def _aktion_ausfuehren(self, schritt: dict, faktor: float) -> str:
        """Führt genau einen Schritt aus und beschreibt, was passiert ist."""
        aktion = str(schritt.get("aktion", "")).strip().lower()
        if aktion not in ERLAUBTE_AKTIONEN:
            return "Die Aktion '%s' kenne ich nicht." % aktion

        def logisch(wert):
            """Bildkoordinate in Bildschirmkoordinate umrechnen."""
            try:
                return int(round(float(wert) * faktor))
            except (TypeError, ValueError):
                return 0

        try:
            if aktion in ("click", "doubleclick"):
                x, y = logisch(schritt.get("x")), logisch(schritt.get("y"))
                if aktion == "click":
                    pyautogui.click(x, y)
                else:
                    pyautogui.doubleClick(x, y)
                return "Auf %d, %d geklickt." % (x, y)
            if aktion == "type":
                pyautogui.typewrite(str(schritt.get("text", "")), interval=0.02)
                return "Text getippt."
            if aktion == "press":
                taste = str(schritt.get("text", "enter")).strip().lower()
                pyautogui.press(taste)
                return "Taste %s gedrückt." % taste
            if aktion == "hotkey":
                tasten = [str(t).strip().lower() for t in (schritt.get("tasten") or []) if t]
                if not tasten:
                    return "Für hotkey fehlen die Tasten."
                pyautogui.hotkey(*tasten)
                return "Tastenkombination %s ausgelöst." % "+".join(tasten)
            if aktion == "scroll":
                try:
                    richtung = int(schritt.get("richtung") or -3)
                except (TypeError, ValueError):
                    richtung = -3
                pyautogui.scroll(richtung * 100)
                return "Gescrollt."
            if aktion == "wait":
                time.sleep(1.5)
                return "Kurz gewartet."
        except Exception as fehler:
            return "Der Schritt ist fehlgeschlagen: %s" % fehler
        return ""

    @staticmethod
    def _heikel(schritt: dict) -> str:
        """Erkennt heikle Lagen im Gedanken des Agenten."""
        gedanke = ("%s %s" % (schritt.get("gedanke", ""), schritt.get("text", ""))).lower()
        for begriff in STOPP_BEGRIFFE:
            if begriff in gedanke:
                return begriff
        return ""

    # -- Hauptschleife ------------------------------------------------------

    def bedienen(self, ziel: str, schritte_max: int = MAX_SCHRITTE,
                 bestaetigen: bool = True) -> dict:
        """Arbeitet ein Ziel Schritt für Schritt ab.

        Vor jedem Schritt wird angezeigt, was geschehen soll, und auf Enter
        gewartet. Die Freigabe für den ganzen Vorgang holt der Werkzeugkatalog
        vorher ein.
        """
        if not self.verfuegbar():
            return {"ok": False,
                    "fehler": "Für die Bildschirmsteuerung fehlen die Pakete pyautogui "
                              "und pillow. Ohne sie läuft alles andere weiter."}
        if self.agent is None or not getattr(self.agent, "einsatzbereit", lambda: False)():
            return {"ok": False,
                    "fehler": "Ohne Anthropic-Schlüssel kann ich den Bildschirm nicht sehen."}

        verlauf = []
        for nummer in range(1, max(1, int(schritte_max)) + 1):
            bild, faktor = self.screenshot()
            if bild is None:
                return {"ok": False, "fehler": self.letzter_fehler,
                        "schritte": verlauf}

            auftrag = STEUER_PROMPT % ziel
            if verlauf:
                auftrag += "\nWas bisher geschah:\n" + "\n".join(verlauf[-6:])

            antwort = self.agent.json_anfrage(auftrag, bild_base64=bild,
                                              bild_typ="image/png")
            if not antwort.get("ok"):
                return {"ok": False,
                        "fehler": "Der Bildschirmagent hat nicht sauber geantwortet: %s"
                                  % antwort.get("fehler", ""), "schritte": verlauf}

            schritt = antwort["daten"]
            aktion = str(schritt.get("aktion", "")).lower()
            gedanke = str(schritt.get("gedanke", ""))[:300]

            if aktion == "abbruch":
                grund = schritt.get("text") or gedanke or "kein Grund genannt"
                return {"ok": False, "abgebrochen": True, "schritte": verlauf,
                        "text": "Ich habe abgebrochen: %s" % grund}
            if aktion == "done":
                ergebnis = schritt.get("text") or "Fertig."
                verlauf.append("Schritt %d: fertig." % nummer)
                return {"ok": True, "schritte": verlauf, "text": ergebnis}

            heikel = self._heikel(schritt)
            if heikel:
                return {"ok": False, "abgebrochen": True, "schritte": verlauf,
                        "text": "Ich halte an: Auf dem Bildschirm geht es um '%s'. "
                                "Das machst du bitte selbst." % heikel}

            beschreibung = "Schritt %d: %s (%s)" % (nummer, aktion, gedanke)
            print("\n%s" % beschreibung)
            if bestaetigen:
                if not sys.stdin or not sys.stdin.isatty():
                    return {"ok": False, "schritte": verlauf,
                            "fehler": "Ich kann den Schritt nicht bestätigen lassen und "
                                      "führe deshalb nichts aus."}
                try:
                    eingabe = input("Enter führt aus, alles andere bricht ab: ").strip()
                except (EOFError, KeyboardInterrupt):
                    eingabe = "abbruch"
                if eingabe:
                    return {"ok": False, "abgebrochen": True, "schritte": verlauf,
                            "text": "Abgebrochen."}

            ergebnis = self._aktion_ausfuehren(schritt, faktor)
            verlauf.append("%s -> %s" % (beschreibung, ergebnis))
            time.sleep(0.6)

        return {"ok": False, "schritte": verlauf,
                "text": "Nach %d Schritten bin ich nicht fertig geworden und höre auf."
                        % schritte_max}
