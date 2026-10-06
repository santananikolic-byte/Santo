#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Ersteinrichtung - geführt, gesprochen, ohne Suchen.

Der Nutzer ist kein Entwickler. Er soll nichts nachschlagen müssen. Deshalb:

* Jeder Schritt wird **vorgelesen**, damit er nicht mitlesen muss.
* Seiten und Systemeinstellungen werden **geöffnet**, nicht beschrieben.
* Der Anthropic-Schlüssel wird **sofort mit einem echten Mini-Aufruf getestet**.
  Ein Schlüssel, der erst beim ersten Gespräch auffällt, hilft niemandem.
* Die drei Rechte werden **einzeln geprüft**, und nur die fehlenden werden
  geöffnet. Wer schon alles erlaubt hat, soll nicht drei Fenster wegklicken.
"""

import getpass
import imaplib
import json
import os
import shutil
import smtplib
import ssl
import subprocess
import sys
import time
import urllib.error
import urllib.request

import config
from modules.camera import Kamera
from modules.mcp_client import vorlage_schreiben
from modules.memory import Memory
from modules.router import gemini_testen
from modules.routines import Routines
from modules.speaker import Sprecherprofil
from modules.telefon import nummer_pruefen
from modules.voice import Stimme

ANTHROPIC_SEITE = "https://console.anthropic.com/settings/keys"

# Direktlinks in die Systemeinstellungen - beschreiben hilft ihm nicht.
EINSTELLUNG_MIKROFON = ("x-apple.systempreferences:com.apple.preference.security"
                        "?Privacy_Microphone")
EINSTELLUNG_BILDSCHIRM = ("x-apple.systempreferences:com.apple.preference.security"
                          "?Privacy_ScreenCapture")
EINSTELLUNG_BEDIENHILFEN = ("x-apple.systempreferences:com.apple.preference.security"
                            "?Privacy_Accessibility")
EINSTELLUNG_KAMERA = ("x-apple.systempreferences:com.apple.preference.security"
                      "?Privacy_Camera")
EINSTELLUNG_SPRACHE = "x-apple.systempreferences:com.apple.preference.speech"

# Kein Einzelunternehmer kennt seinen IMAP-Servernamen. Er tippt seine
# Mailadresse ein, den Rest wissen wir selbst.
MAIL_ANBIETER = {
    "gmail.com": ("imap.gmail.com", 993, "smtp.gmail.com", 587, True),
    "googlemail.com": ("imap.gmail.com", 993, "smtp.gmail.com", 587, True),
    "gmx.at": ("imap.gmx.net", 993, "mail.gmx.net", 587, False),
    "gmx.de": ("imap.gmx.net", 993, "mail.gmx.net", 587, False),
    "gmx.net": ("imap.gmx.net", 993, "mail.gmx.net", 587, False),
    "web.de": ("imap.web.de", 993, "smtp.web.de", 587, False),
    "outlook.com": ("outlook.office365.com", 993, "smtp-mail.outlook.com", 587, True),
    "hotmail.com": ("outlook.office365.com", 993, "smtp-mail.outlook.com", 587, True),
    "live.com": ("outlook.office365.com", 993, "smtp-mail.outlook.com", 587, True),
    "live.at": ("outlook.office365.com", 993, "smtp-mail.outlook.com", 587, True),
    "icloud.com": ("imap.mail.me.com", 993, "smtp.mail.me.com", 587, True),
    "me.com": ("imap.mail.me.com", 993, "smtp.mail.me.com", 587, True),
    "t-online.de": ("secureimap.t-online.de", 993, "securesmtp.t-online.de", 587, False),
    "yahoo.com": ("imap.mail.yahoo.com", 993, "smtp.mail.yahoo.com", 587, True),
    "yahoo.de": ("imap.mail.yahoo.com", 993, "smtp.mail.yahoo.com", 587, True),
    "a1.net": ("imap.a1.net", 993, "smtp.a1.net", 587, False),
    "aon.at": ("imap.a1.net", 993, "smtp.a1.net", 587, False),
}

# Drei Routinen, die von Anfang an da sind.
STARTROUTINEN = [
    ("Wochenrückblick",
     "Fasse die letzte Woche zusammen: Zahlen des Monats, gewonnene und verlorene "
     "Gespräche, offene Leads mit Volumen, fehlende Belege und was liegen geblieben "
     "ist. Nenne konkret, was diese Woche zuerst drankommt.", ""),
    ("Belege prüfen",
     "Sieh nach, zu welchen Ausgaben noch kein Beleg hinterlegt ist. Nenne Betrag, "
     "Händler und Datum der größten fehlenden Belege und erinnere daran, sie zu "
     "fotografieren.", ""),
    ("Nachfassen",
     "Zeige alle offenen Leads. Für jeden: wie lange er schon offen ist, welches "
     "Volumen dahinter steht und welcher nächste Schritt vereinbart war. Sag mir, "
     "bei wem ich heute anrufen sollte und warum.", ""),
]


class Einrichtung:
    """Führt den Nutzer Schritt für Schritt durch die Ersteinrichtung."""

    def __init__(self, stimme=None):
        self.stimme = stimme
        self.ergebnisse = {}

    # -- Ausgabe ------------------------------------------------------------

    def sagen(self, text: str):
        """Schreibt und spricht einen Satz."""
        print("\n%s" % text)
        if self.stimme is not None:
            self.stimme.sprich(text)
        elif shutil.which("say"):
            try:
                subprocess.run(["say", "-r", str(int(config.SPEECH_RATE)), text[:2000]],
                               timeout=120, shell=False,
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            except (OSError, subprocess.SubprocessError):
                pass

    @staticmethod
    def fragen(frage: str) -> str:
        """Liest eine Eingabe vom Terminal."""
        try:
            return input("%s " % frage).strip()
        except (EOFError, KeyboardInterrupt):
            return ""

    @staticmethod
    def fragen_geheim(frage: str) -> str:
        """Liest einen Schlüssel - unsichtbar, wenn ein echtes Terminal da ist.

        Was man nicht sieht, kann man nicht versehentlich fotografieren oder
        in einen Chat kopieren. Eingefügt wird trotzdem ganz normal.
        """
        try:
            if sys.stdin.isatty():
                return getpass.getpass("%s (die Eingabe bleibt unsichtbar) " % frage).strip()
            return input("%s " % frage).strip()
        except (EOFError, KeyboardInterrupt):
            return ""

    @staticmethod
    def oeffnen(ziel: str) -> bool:
        """Öffnet eine Seite oder eine Systemeinstellung."""
        if not shutil.which("open"):
            print("Bitte von Hand öffnen: %s" % ziel)
            return False
        try:
            subprocess.run(["open", ziel], timeout=20, shell=False,
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return True
        except (OSError, subprocess.SubprocessError):
            return False

    # -- Schritt 1: Stimme --------------------------------------------------

    def schritt_stimme(self) -> bool:
        """Sucht eine deutsche Systemstimme, sonst öffnet sich die Einstellung."""
        if not shutil.which("say"):
            self.ergebnisse["stimme"] = "kein say - kein Mac?"
            print("[--] Die Sprachausgabe 'say' gibt es nur auf einem Mac.")
            return False
        gefunden = ""
        try:
            ergebnis = subprocess.run(["say", "-v", "?"], capture_output=True,
                                      text=True, timeout=10, shell=False)
            for zeile in ergebnis.stdout.splitlines():
                teile = zeile.split()
                if len(teile) >= 2 and teile[1] in ("de_DE", "de_AT", "de_CH"):
                    gefunden = teile[0]
                    if teile[0] in ("Markus", "Yannick", "Petra", "Anna", "Viktor"):
                        break
        except (OSError, subprocess.SubprocessError):
            pass

        if gefunden:
            config.env_setzen("MACOS_STIMME", gefunden)
            self.ergebnisse["stimme"] = gefunden
            self.sagen("Ich habe die deutsche Stimme %s gefunden und benutze sie." % gefunden)
            return True

        self.ergebnisse["stimme"] = "keine"
        self.sagen("Auf diesem Mac ist keine deutsche Stimme installiert. Ich öffne die "
                   "Einstellung. Lade dort bitte eine deutsche Stimme herunter, zum "
                   "Beispiel Markus oder Anna.")
        self.oeffnen(EINSTELLUNG_SPRACHE)
        self.fragen("Drücke Enter, wenn du fertig bist:")
        return False

    # -- Schritt 2: Anthropic-Schlüssel ------------------------------------

    def schluessel_testen(self, schluessel: str) -> dict:
        """Prüft einen Schlüssel mit einem echten, winzigen Aufruf."""
        koerper = json.dumps({
            "model": config.CLAUDE_MODEL, "max_tokens": 8,
            "messages": [{"role": "user", "content": "Sag nur: ok"}],
        }).encode("utf-8")
        anfrage = urllib.request.Request(
            "https://api.anthropic.com/v1/messages", data=koerper, method="POST",
            headers={"x-api-key": schluessel, "anthropic-version": "2023-06-01",
                     "content-type": "application/json"})
        try:
            with urllib.request.urlopen(anfrage, timeout=45) as antwort:
                antwort.read()
            return {"ok": True, "text": "Der Schlüssel funktioniert."}
        except urllib.error.HTTPError as fehler:
            try:
                inhalt = fehler.read().decode("utf-8")
                meldung = (json.loads(inhalt).get("error") or {}).get("message", inhalt)
            except (ValueError, OSError):
                meldung = str(fehler)
            if fehler.code == 401:
                return {"ok": False, "grund": "schluessel",
                        "text": "Der Schlüssel wird abgelehnt. Vermutlich ist beim "
                                "Kopieren etwas verloren gegangen. Bitte noch einmal "
                                "vollständig kopieren."}
            if fehler.code == 400 and "credit" in meldung.lower():
                return {"ok": False, "grund": "guthaben",
                        "text": "Der Schlüssel stimmt, aber auf dem Konto ist kein "
                                "Guthaben. Bitte auf der Anthropic-Seite unter Billing "
                                "etwas aufladen."}
            if fehler.code == 429:
                return {"ok": False, "grund": "zuviel",
                        "text": "Zu viele Anfragen auf einmal. Ich warte kurz und "
                                "versuche es noch einmal."}
            if fehler.code == 404:
                return {"ok": False, "grund": "modell",
                        "text": "Das eingestellte Modell %s kennt die Schnittstelle "
                                "nicht." % config.CLAUDE_MODEL}
            return {"ok": False, "grund": "sonstiges",
                    "text": "Die Prüfung ist fehlgeschlagen: %s" % meldung[:200]}
        except (urllib.error.URLError, OSError) as fehler:
            return {"ok": False, "grund": "netz",
                    "text": "Keine Verbindung zu Anthropic. Ist das Internet da? (%s)"
                            % fehler}

    def schritt_schluessel(self) -> bool:
        """Holt den Schlüssel und prüft ihn - bis zu vier Versuche."""
        if config.ANTHROPIC_API_KEY:
            self.sagen("Ich prüfe den hinterlegten Schlüssel.")
            probe = self.schluessel_testen(config.ANTHROPIC_API_KEY)
            if probe.get("ok"):
                self.ergebnisse["schluessel"] = "vorhanden und geprüft"
                self.sagen("Der hinterlegte Schlüssel funktioniert.")
                return True
            self.sagen(probe["text"])

        self.sagen("Jetzt brauche ich deinen Anthropic-Schlüssel. Ich öffne die Seite. "
                   "Melde dich an, drücke auf Create Key, kopiere den Schlüssel und "
                   "füge ihn hier ein.")
        self.oeffnen(ANTHROPIC_SEITE)

        for versuch in range(1, 5):
            schluessel = self.fragen_geheim("Schlüssel hier einfügen und Enter drücken:")
            if not schluessel:
                self.sagen("Ich habe nichts bekommen. Versuch %d von 4." % versuch)
                continue
            if not schluessel.startswith("sk-"):
                self.sagen("Das sieht nicht nach einem Anthropic-Schlüssel aus - die "
                           "beginnen mit s k Bindestrich. Bitte noch einmal.")
                continue
            self.sagen("Ich probiere den Schlüssel aus.")
            probe = self.schluessel_testen(schluessel)
            if probe.get("ok"):
                config.env_setzen("ANTHROPIC_API_KEY", schluessel)
                self.ergebnisse["schluessel"] = "geprüft"
                self.sagen("Der Schlüssel funktioniert. Damit kann ich denken.")
                return True
            self.sagen(probe["text"])
            if probe.get("grund") == "guthaben":
                config.env_setzen("ANTHROPIC_API_KEY", schluessel)
                self.ergebnisse["schluessel"] = "gespeichert, kein Guthaben"
                self.oeffnen("https://console.anthropic.com/settings/billing")
                return False
            if probe.get("grund") == "zuviel":
                time.sleep(8)
            if probe.get("grund") == "netz":
                return False

        self.ergebnisse["schluessel"] = "fehlgeschlagen"
        self.sagen("Der Schlüssel hat nach vier Versuchen nicht funktioniert. Alles "
                   "andere richte ich trotzdem ein. Du kannst ihn später eintragen mit: "
                   "python3 jarvis.py einrichten")
        return False

    # -- Schritt 3: Die drei Rechte ----------------------------------------

    def recht_mikrofon(self) -> bool:
        """Prüft das Mikrofon, indem wirklich ein Eingabestrom geöffnet wird."""
        try:
            import sounddevice
        except (ImportError, OSError):
            self.ergebnisse["mikrofon"] = "Paket sounddevice fehlt"
            return False
        try:
            strom = sounddevice.InputStream(samplerate=16000, channels=1)
            strom.start()
            strom.stop()
            strom.close()
            self.ergebnisse["mikrofon"] = "erlaubt"
            return True
        except Exception:
            self.ergebnisse["mikrofon"] = "nicht erlaubt"
            return False

    def recht_bildschirm(self) -> bool:
        """Prüft die Bildschirmaufnahme.

        Ohne dieses Recht liefert macOS ein schwarzes Bild statt einer Fehlermeldung.
        Deshalb wird gezählt, wie viele verschiedene Farben darin vorkommen: mehr
        als drei bedeutet, dass wirklich der Bildschirm zu sehen ist.
        """
        try:
            import pyautogui
        except Exception:
            self.ergebnisse["bildschirm"] = "Paket pyautogui fehlt"
            return False
        try:
            bild = pyautogui.screenshot()
            klein = bild.convert("RGB").resize((80, 50))
            farben = {klein.getpixel((x, y)) for x in range(0, 80, 2)
                      for y in range(0, 50, 2)}
            if len(farben) > 3:
                self.ergebnisse["bildschirm"] = "erlaubt"
                return True
            self.ergebnisse["bildschirm"] = "nicht erlaubt (schwarzes Bild)"
            return False
        except Exception as fehler:
            self.ergebnisse["bildschirm"] = "nicht prüfbar: %s" % fehler
            return False

    def recht_bedienhilfen(self) -> bool:
        """Prüft die Bedienungshilfen über einen echten AppleScript-Aufruf."""
        if not shutil.which("osascript"):
            self.ergebnisse["bedienhilfen"] = "kein osascript"
            return False
        skript = ('tell application "System Events" to return count of processes')
        try:
            ergebnis = subprocess.run(["osascript", "-e", skript], capture_output=True,
                                      text=True, timeout=20, shell=False)
        except (OSError, subprocess.SubprocessError):
            self.ergebnisse["bedienhilfen"] = "nicht prüfbar"
            return False
        if ergebnis.returncode == 0 and (ergebnis.stdout or "").strip().isdigit():
            self.ergebnisse["bedienhilfen"] = "erlaubt"
            return True
        self.ergebnisse["bedienhilfen"] = "nicht erlaubt"
        return False

    def recht_kamera(self) -> bool:
        """Prüft die Kamera, indem wirklich ein Bild aufgenommen wird.

        Ein Test ist ehrlicher als ein Hinweis: Fehlt das Recht, liefert macOS
        keine Fehlermeldung, sondern eine unbrauchbare Datei.
        """
        kamera = Kamera()
        if not kamera.verfuegbar():
            self.ergebnisse["kamera"] = "kein Aufnahmeprogramm"
            return False
        ergebnis = kamera.bild_aufnehmen()
        if ergebnis.get("ok"):
            try:
                os.remove(ergebnis["pfad"])
            except OSError:
                pass
            self.ergebnisse["kamera"] = "erlaubt"
            return True
        self.ergebnisse["kamera"] = "nicht erlaubt"
        return False

    def schritt_rechte(self):
        """Prüft alle drei Rechte einzeln und öffnet nur die fehlenden."""
        self.sagen("Jetzt prüfe ich die drei Rechte, die ich brauche.")

        fehlend = []
        if self.recht_mikrofon():
            print("[ok] Mikrofon")
        else:
            print("[!!] Mikrofon: %s" % self.ergebnisse["mikrofon"])
            fehlend.append(("Mikrofon", EINSTELLUNG_MIKROFON,
                            "damit ich dich hören kann"))
        if self.recht_bildschirm():
            print("[ok] Bildschirmaufnahme")
        else:
            print("[!!] Bildschirmaufnahme: %s" % self.ergebnisse["bildschirm"])
            fehlend.append(("Bildschirmaufnahme", EINSTELLUNG_BILDSCHIRM,
                            "damit ich den Bildschirm sehen kann"))
        if self.recht_bedienhilfen():
            print("[ok] Bedienungshilfen")
        else:
            print("[!!] Bedienungshilfen: %s" % self.ergebnisse["bedienhilfen"])
            fehlend.append(("Bedienungshilfen", EINSTELLUNG_BEDIENHILFEN,
                            "damit ich klicken und tippen kann"))

        # Die Kamera ist ein eigenes Recht - ohne sie kann ich mich nicht umsehen.
        if self.recht_kamera():
            print("[ok] Kamera")
        elif self.ergebnisse["kamera"] == "kein Aufnahmeprogramm":
            print("[--] Kamera: es fehlt das Programm imagesnap")
            self.sagen("Zum Fotografieren fehlt noch ein kleines Programm. Führe "
                       "später im Terminal brew install imagesnap aus, dann kann "
                       "ich mich für dich umsehen.")
        else:
            print("[!!] Kamera: %s" % self.ergebnisse["kamera"])
            fehlend.append(("Kamera", EINSTELLUNG_KAMERA,
                            "damit ich einen Beleg oder ein Objekt ansehen kann"))

        if not fehlend:
            self.sagen("Alle drei Rechte sind bereits erteilt.")
            return

        self.sagen("Es fehlen %d Rechte. Ich öffne die Einstellungen einzeln. Setze dort "
                   "jeweils den Haken beim Terminal." % len(fehlend))
        for name, ziel, zweck in fehlend:
            self.sagen("Jetzt %s, %s." % (name, zweck))
            self.oeffnen(ziel)
            self.fragen("Enter, wenn der Haken gesetzt ist:")

    # -- Schritt 4: Angaben zur Person -------------------------------------

    def schritt_person(self):
        """Fragt Name, Firma und Ort ab."""
        name = self.fragen("Wie soll ich dich nennen? (Enter für '%s')"
                           % config.NUTZER_NAME)
        if name:
            config.env_setzen("NUTZER_NAME", name)
        firma = self.fragen("Wie heißt deine Firma? (Enter zum Überspringen)")
        if firma:
            config.env_setzen("FIRMA", firma)
        branche = self.fragen("In welcher Branche arbeitest du? Zum Beispiel Gebäudereinigung, "
                              "Gastronomie, Handwerk (Enter für '%s')" % config.BRANCHE)
        if branche:
            config.env_setzen("BRANCHE", " ".join(branche.split())[:80])
        ort = self.fragen("In welchem Ort arbeitest du? (Enter für '%s')"
                          % config.WETTER_ORT)
        if ort:
            config.env_setzen("WETTER_ORT", ort)
        mwst = self.fragen("Welcher Mehrwertsteuersatz gilt bei dir? (Enter für %g)"
                           % config.STANDARD_MWST)
        if mwst:
            try:
                config.env_setzen("STANDARD_MWST", float(mwst.replace(",", ".")))
            except ValueError:
                print("Das war keine Zahl - ich bleibe bei %g." % config.STANDARD_MWST)
        profil = self.fragen("Was soll Jarvis über dich und deinen Alltag wissen? "
                             "Ein, zwei Sätze (Enter zum Überspringen):")
        if profil:
            config.env_setzen("JARVIS_PROFIL", " ".join(profil.split()))
        stil = self.fragen("Wie soll er mit dir reden? Zum Beispiel: knapp und direkt, "
                           "mit etwas Humor (Enter für den Standard):")
        if stil:
            config.env_setzen("JARVIS_STIL", " ".join(stil.split()))
        self.ergebnisse["person"] = config.NUTZER_NAME

    # -- Gemini (freiwillig) -------------------------------------------------

    def schritt_gemini(self) -> bool:
        """Gemini ist das schnelle, gratis Gehirn. Ohne bleibt Claude allein."""
        if config.GEMINI_API_KEY:
            probe = gemini_testen(config.GEMINI_API_KEY)
            if probe.get("ok"):
                self.ergebnisse["gemini"] = "vorhanden und geprüft"
                return True
            self.sagen(probe["text"])
        antwort = self.fragen("Möchtest du Gemini dazunehmen? Das ist das schnelle, "
                              "kostenlose Gehirn für einfache Fragen. (j/N)").lower()
        if antwort not in ("j", "ja", "y", "yes"):
            self.ergebnisse["gemini"] = "übersprungen"
            return False
        self.sagen("Ich öffne Google AI Studio. Melde dich an, wähle Create API Key, "
                   "kopiere den Schlüssel und füge ihn hier ein.")
        self.oeffnen("https://aistudio.google.com/apikey")
        for versuch in range(1, 4):
            schluessel = self.fragen_geheim("Gemini-Schlüssel einfügen und Enter drücken:")
            if not schluessel:
                self.sagen("Ich habe nichts bekommen. Versuch %d von 3." % versuch)
                continue
            probe = gemini_testen(schluessel)
            self.sagen(probe["text"])
            if probe.get("ok") or probe.get("limit"):
                config.env_setzen("GEMINI_API_KEY", schluessel)
                self.ergebnisse["gemini"] = "geprüft" if probe.get("ok") else "gespeichert"
                return True
        self.ergebnisse["gemini"] = "fehlgeschlagen"
        self.sagen("Gemini lasse ich weg. Später: python3 jarvis.py zugang")
        return False

    # -- Autopilot (freiwillig) ---------------------------------------------

    def schritt_autopilot(self):
        """Fragt, ob Jarvis im Hintergrund selbst arbeiten soll."""
        self.sagen("Soll ich im Hintergrund von selbst arbeiten? Ich bereite dann "
                   "Nachfassnachrichten, Antwortentwürfe und Angebote vor und lege "
                   "sie in ein Postfach. Ich schicke nie etwas ab, ohne dass du Ja sagst.")
        antwort = self.fragen("Autopilot einschalten? (j/N)").lower()
        if antwort in ("j", "ja", "y", "yes"):
            config.env_setzen("AUTOPILOT_AN", "ja")
            self.ergebnisse["autopilot"] = "an"
        else:
            self.ergebnisse["autopilot"] = "aus (später auf der Seite Autopilot)"

    # -- Einzelner Zugang nachtragen ---------------------------------------

    ZUGAENGE = (
        ("claude", "Claude (Anthropic)", "ANTHROPIC_API_KEY", "https://console.anthropic.com/settings/keys"),
        ("gemini", "Gemini (Google)", "GEMINI_API_KEY", "https://aistudio.google.com/apikey"),
        ("stimme", "ElevenLabs (Stimme)", "ELEVENLABS_API_KEY", "https://elevenlabs.io/app/settings/api-keys"),
        ("ohren", "OpenAI (Spracherkennung)", "OPENAI_API_KEY", "https://platform.openai.com/api-keys"),
    )

    def zugang_nachtragen(self, welcher: str = "") -> bool:
        """Trägt genau einen Zugang ein oder ersetzt ihn - ohne die ganze Einrichtung."""
        welcher = (welcher or "").strip().lower()
        wahl = [z for z in self.ZUGAENGE if welcher in (z[0], z[2].lower())]
        if not wahl:
            print("Welchen Zugang möchtest du eintragen?")
            vorhanden = {"ANTHROPIC_API_KEY": config.ANTHROPIC_API_KEY,
                         "GEMINI_API_KEY": config.GEMINI_API_KEY,
                         "ELEVENLABS_API_KEY": config.ELEVENLABS_API_KEY,
                         "OPENAI_API_KEY": config.OPENAI_API_KEY}
            for nummer, z in enumerate(self.ZUGAENGE, start=1):
                print("  %d  %s%s" % (nummer, z[1],
                                       "   (schon eingetragen)" if vorhanden.get(z[2]) else ""))
            eingabe = self.fragen("Nummer:")
            if not eingabe.isdigit() or not 1 <= int(eingabe) <= len(self.ZUGAENGE):
                print("Das war keine gültige Nummer.")
                return False
            wahl = [self.ZUGAENGE[int(eingabe) - 1]]
        kennung, titel, variable, seite = wahl[0]
        print("Ich öffne die Seite für %s. Dort erzeugst du den Schlüssel." % titel)
        self.oeffnen(seite)
        schluessel = self.fragen_geheim("Schlüssel für %s einfügen und Enter drücken:" % titel)
        if not schluessel:
            print("Ich habe nichts bekommen. Es wurde nichts geändert.")
            return False
        if kennung == "claude":
            if not schluessel.startswith("sk-"):
                print("Das sieht nicht nach einem Anthropic-Schlüssel aus (sie beginnen "
                      "mit sk-). Es wurde nichts geändert.")
                return False
            probe = self.schluessel_testen(schluessel)
            if not probe.get("ok") and probe.get("grund") != "guthaben":
                print(probe["text"] + " Es wurde nichts geändert.")
                return False
            print(probe["text"] if not probe.get("ok") else "Der Schlüssel funktioniert.")
        elif kennung == "gemini":
            probe = gemini_testen(schluessel)
            print(probe["text"])
            if not probe.get("ok") and not probe.get("limit"):
                print("Es wurde nichts geändert.")
                return False
        config.env_setzen(variable, schluessel)
        print("%s ist eingetragen. Starte Jarvis neu, damit er ihn nutzt." % titel)
        return True

    # -- Schritt 5: Telegram ------------------------------------------------

    def schritt_telegram(self):
        """Richtet Telegram ein - der Weg für Freigaben unterwegs."""
        self.sagen("Telegram ist der Weg, über den ich dich um Freigaben bitte, wenn du "
                   "nicht am Rechner sitzt. Das ist freiwillig. Ohne Telegram frage ich "
                   "im Terminal.")
        antwort = self.fragen("Telegram jetzt einrichten? (ja/nein)").lower()
        if antwort not in ("ja", "j", "yes", "y"):
            self.ergebnisse["telegram"] = "übersprungen"
            return
        self.sagen("Öffne Telegram, suche den BotFather, schicke ihm slash newbot und "
                   "folge den Anweisungen. Am Ende bekommst du einen Token.")
        token = self.fragen("Bot-Token hier einfügen:")
        if not token:
            self.ergebnisse["telegram"] = "kein Token"
            return
        config.env_setzen("TELEGRAM_BOT_TOKEN", token)
        self.sagen("Schreibe deinem neuen Bot jetzt irgendeine Nachricht in Telegram, "
                   "dann drücke hier Enter.")
        self.fragen("Enter, wenn du dem Bot geschrieben hast:")
        chat_id = self._chat_id_holen(token)
        if chat_id:
            config.env_setzen("TELEGRAM_CHAT_ID", chat_id)
            self.ergebnisse["telegram"] = "eingerichtet"
            self.sagen("Telegram ist eingerichtet. Ich schicke dir eine Testnachricht.")
            self._telegram_test(token, chat_id)
        else:
            self.ergebnisse["telegram"] = "keine Nachricht gefunden"
            self.sagen("Ich habe keine Nachricht gefunden. Du kannst das später "
                       "nachholen.")

    # -- Schritt 5b: Telefon ------------------------------------------------

    def schritt_telefon(self):
        """Richtet das Telefon ein - Anrufe und SMS über Twilio."""
        self.sagen("Wenn du willst, kann ich für dich anrufen und SMS schicken - zum "
                   "Beispiel eine Terminbestätigung an einen Kunden. Das läuft über "
                   "einen Dienst namens Twilio und kostet ein paar Cent pro Anruf. "
                   "Freiwillig. Ohne das funktioniert alles andere genauso.")
        antwort = self.fragen("Telefon jetzt einrichten? (ja/nein)").lower()
        if antwort not in ("ja", "j", "yes", "y"):
            self.ergebnisse["telefon"] = "übersprungen"
            return
        self.sagen("Geh auf twilio Punkt com, melde dich an und kauf dir dort eine "
                   "Telefonnummer. Auf der Startseite stehen dann zwei Werte: Account "
                   "SID und Auth Token.")
        sid = self.fragen("Account SID (beginnt mit AC):")
        if not sid.startswith("AC"):
            self.ergebnisse["telefon"] = "SID sieht nicht richtig aus"
            self.sagen("Die SID beginnt normalerweise mit A C. Ich lasse das Telefon "
                       "erst mal aus, du kannst es später nachholen.")
            return
        token = self.fragen("Auth Token:")
        if not token:
            self.ergebnisse["telefon"] = "kein Token"
            return
        nummer = self.fragen("Deine gekaufte Twilio-Nummer (international, z.B. +43...):")
        geprueft, fehler = nummer_pruefen(nummer)
        if geprueft is None:
            self.ergebnisse["telefon"] = "Nummer unklar"
            self.sagen(fehler)
            return
        config.env_setzen("TWILIO_SID", sid)
        config.env_setzen("TWILIO_TOKEN", token)
        config.env_setzen("TWILIO_NUMMER", geprueft)
        config.TWILIO_SID, config.TWILIO_TOKEN, config.TWILIO_NUMMER = sid, token, geprueft
        self.ergebnisse["telefon"] = "eingerichtet"
        self.sagen("Das Telefon ist eingerichtet. Ich frage dich vor jedem Anruf und "
                   "vor jeder SMS um Erlaubnis.")

    @staticmethod
    def _chat_id_holen(token: str) -> str:
        """Liest die Chat-Nummer aus der ersten Nachricht an den Bot."""
        try:
            ziel = "https://api.telegram.org/bot%s/getUpdates" % token
            with urllib.request.urlopen(ziel, timeout=25) as antwort:
                daten = json.loads(antwort.read().decode("utf-8"))
            for eintrag in reversed(daten.get("result", []) or []):
                chat = ((eintrag.get("message") or {}).get("chat") or {})
                if chat.get("id"):
                    return str(chat["id"])
        except (urllib.error.URLError, OSError, ValueError):
            pass
        return ""

    @staticmethod
    def _telegram_test(token: str, chat_id: str):
        """Schickt eine Testnachricht."""
        try:
            koerper = json.dumps({"chat_id": chat_id,
                                  "text": "Jarvis ist eingerichtet. Über diesen Chat "
                                          "frage ich dich künftig um Freigaben."}
                                 ).encode("utf-8")
            anfrage = urllib.request.Request(
                "https://api.telegram.org/bot%s/sendMessage" % token, data=koerper,
                method="POST", headers={"Content-Type": "application/json"})
            urllib.request.urlopen(anfrage, timeout=20).read()
        except (urllib.error.URLError, OSError, ValueError):
            pass

    # -- Schritt 5b: E-Mail -------------------------------------------------

    def mail_testen(self, host: str, port: int, benutzer: str, passwort: str) -> dict:
        """Meldet sich wirklich am Posteingang an, statt es nur zu hoffen."""
        try:
            verbindung = imaplib.IMAP4_SSL(host, int(port),
                                           ssl_context=ssl.create_default_context())
            try:
                verbindung.login(benutzer, passwort)
                verbindung.select("INBOX")
                status, daten = verbindung.search(None, "UNSEEN")
                anzahl = len(daten[0].split()) if status == "OK" and daten[0] else 0
            finally:
                try:
                    verbindung.logout()
                except (imaplib.IMAP4.error, OSError):
                    pass
            return {"ok": True, "ungelesen": anzahl}
        except imaplib.IMAP4.error as fehler:
            meldung = str(fehler).lower()
            if "credential" in meldung or "auth" in meldung or "login" in meldung:
                return {"ok": False, "grund": "zugang",
                        "text": "Der Mailserver lehnt Benutzer oder Passwort ab."}
            return {"ok": False, "grund": "sonstiges",
                    "text": "Der Posteingang antwortet nicht wie erwartet: %s"
                            % str(fehler)[:150]}
        except (ssl.SSLError, OSError) as fehler:
            return {"ok": False, "grund": "netz",
                    "text": "Der Server %s ist nicht erreichbar: %s" % (host, fehler)}

    def schritt_mail(self):
        """Richtet Posteingang und Versand ein - mit Servererkennung aus der Adresse."""
        self.sagen("Jetzt dein Postfach. Damit lese ich morgens deine Mails und "
                   "sortiere sie vor. Das ist freiwillig.")
        antwort = self.fragen("E-Mail jetzt einrichten? (ja/nein)").lower()
        if antwort not in ("ja", "j", "yes", "y"):
            self.ergebnisse["email"] = "übersprungen"
            return

        for versuch in range(1, 4):
            adresse = self.fragen("Deine E-Mail-Adresse:")
            if "@" not in adresse:
                self.sagen("Das sieht nicht nach einer Mailadresse aus.")
                continue
            domain = adresse.split("@")[-1].strip().lower()
            bekannt = MAIL_ANBIETER.get(domain)

            if bekannt:
                imap_host, imap_port, smtp_host, smtp_port, app_passwort = bekannt
                self.sagen("Deinen Anbieter kenne ich, die Servernamen trage ich "
                           "selbst ein.")
            else:
                app_passwort = False
                self.sagen("Deinen Anbieter kenne ich nicht. Die beiden Servernamen "
                           "stehen bei deinem Anbieter unter Mail-Einstellungen.")
                imap_host = self.fragen("Posteingangs-Server (IMAP), z.B. imap.firma.at:")
                smtp_host = self.fragen("Postausgangs-Server (SMTP), z.B. smtp.firma.at:")
                imap_port, smtp_port = 993, 587
                if not imap_host or not smtp_host:
                    self.ergebnisse["email"] = "keine Server angegeben"
                    return

            if app_passwort:
                self.sagen("Wichtig bei diesem Anbieter: Das normale Passwort "
                           "funktioniert nicht. Du brauchst ein sogenanntes "
                           "App-Passwort. Ich öffne die Seite, auf der du es "
                           "erzeugst.")
                self.oeffnen({"gmail.com": "https://myaccount.google.com/apppasswords",
                              "googlemail.com": "https://myaccount.google.com/apppasswords",
                              "icloud.com": "https://account.apple.com/account/manage",
                              "me.com": "https://account.apple.com/account/manage",
                              }.get(domain, "https://account.live.com/proofs/manage"))

            passwort = self.fragen("Passwort (oder App-Passwort):")
            if not passwort:
                self.sagen("Ohne Passwort geht es nicht.")
                continue

            self.sagen("Ich melde mich einmal an, um zu sehen, ob es stimmt.")
            probe = self.mail_testen(imap_host, imap_port, adresse, passwort)
            if probe.get("ok"):
                config.env_setzen("IMAP_HOST", imap_host)
                config.env_setzen("IMAP_PORT", imap_port)
                config.env_setzen("IMAP_USER", adresse)
                config.env_setzen("IMAP_PASSWORT", passwort)
                config.env_setzen("SMTP_HOST", smtp_host)
                config.env_setzen("SMTP_PORT", smtp_port)
                config.env_setzen("SMTP_USER", adresse)
                config.env_setzen("SMTP_PASSWORT", passwort)
                config.env_setzen("SMTP_ABSENDER", adresse)
                self.ergebnisse["email"] = "eingerichtet"
                self.sagen("Das Postfach ist verbunden. Gerade liegen dort %d "
                           "ungelesene Mails." % probe["ungelesen"])
                return
            self.sagen(probe["text"])
            if probe.get("grund") == "zugang" and app_passwort:
                self.sagen("Bei diesem Anbieter ist das fast immer das normale "
                           "Passwort statt des App-Passworts. Versuch %d von 3."
                           % versuch)

        self.ergebnisse["email"] = "fehlgeschlagen"
        self.sagen("Das Postfach hat nicht funktioniert. Alles andere richte ich "
                   "trotzdem ein. Du kannst es später nachholen.")

    # -- Schritt 6: Startroutinen ------------------------------------------

    def schritt_routinen(self):
        """Legt die drei Startroutinen an."""
        routinen = Routines(Memory())
        angelegt = []
        for name, anweisung, uhrzeit in STARTROUTINEN:
            ergebnis = routinen.routine_anlegen(name, anweisung, uhrzeit)
            if ergebnis.get("ok"):
                angelegt.append(name)
        self.ergebnisse["routinen"] = angelegt
        self.sagen("Ich habe drei Routinen für dich angelegt: %s. Du rufst sie auf, "
                   "indem du einfach ihren Namen sagst." % ", ".join(angelegt))

    # -- Schritt 7: Stimmprofil --------------------------------------------

    def schritt_stimmprofil(self):
        """Bietet an, die Stimme einzulernen."""
        self.sagen("Zum Schluss kann ich deine Stimme einlernen. Dann reagiere ich "
                   "bevorzugt auf dich. Wichtig zu wissen: Das unterscheidet Sprecher "
                   "im Alltag zuverlässig, ist aber kein Schutz gegen eine abgespielte "
                   "Aufnahme. Deshalb gibt die Stimme allein nie eine Mail oder eine "
                   "Buchung frei. Sie entscheidet nur, ob ich zuhöre.")
        antwort = self.fragen("Stimme jetzt einlernen? (ja/nein)").lower()
        if antwort not in ("ja", "j", "yes", "y"):
            self.ergebnisse["stimmprofil"] = "übersprungen"
            return
        profil = Sprecherprofil()
        ergebnis = profil.einlernen(self.stimme or Stimme())
        if ergebnis.get("ok"):
            config.env_setzen("STIMMPRUEFUNG_AN", "ja")
            self.ergebnisse["stimmprofil"] = "angelegt"
            self.sagen(ergebnis.get("text", "Stimmprofil angelegt."))
        else:
            self.ergebnisse["stimmprofil"] = ergebnis.get("fehler", "fehlgeschlagen")
            self.sagen(ergebnis.get("fehler", "Das Einlernen hat nicht geklappt."))

    # -- Ablauf -------------------------------------------------------------

    def durchlaufen(self) -> dict:
        """Führt die ganze Einrichtung durch."""
        config.verzeichnisse_anlegen()
        vorlage_schreiben()

        self.sagen("Hallo. Ich bin Jarvis und richte mich jetzt einmalig ein. Das "
                   "dauert ein paar Minuten. Ich lese dir alles vor, du musst nichts "
                   "mitlesen.")

        self.schritt_stimme()
        self.schritt_person()
        self.schritt_schluessel()
        self.schritt_gemini()
        self.schritt_autopilot()
        self.schritt_rechte()
        self.schritt_telegram()
        self.schritt_telefon()
        self.schritt_mail()
        self.schritt_routinen()
        self.schritt_stimmprofil()

        config.env_setzen("EINRICHTUNG_FERTIG", "ja")

        print("\n" + "=" * 60)
        print("EINRICHTUNG ABGESCHLOSSEN")
        print("=" * 60)
        for name, wert in self.ergebnisse.items():
            print("  %-14s %s" % (name + ":", wert))
        print("=" * 60)

        self.sagen("Fertig. Eine Sache noch, und die ist wichtig: Du musst das Terminal "
                   "jetzt einmal komplett schließen und neu öffnen. Sonst greifen die "
                   "erteilten Rechte nicht. Danach startest du mich einfach wieder über "
                   "JARVIS Punkt command. Dann sag: Hey Jarvis, wie sieht mein Tag aus.")
        return self.ergebnisse


def zugang_eintragen(welcher: str = "") -> bool:
    """Trägt einen einzelnen Zugang ein: ``python3 jarvis.py zugang gemini``."""
    return Einrichtung().zugang_nachtragen(welcher)


def einrichtung_starten(stimme=None) -> dict:
    """Startet die geführte Ersteinrichtung."""
    return Einrichtung(stimme).durchlaufen()
