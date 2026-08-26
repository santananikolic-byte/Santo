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

import json
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request

import config
from modules.mcp_client import vorlage_schreiben
from modules.memory import Memory
from modules.routines import Routines
from modules.speaker import Sprecherprofil
from modules.voice import Stimme

ANTHROPIC_SEITE = "https://console.anthropic.com/settings/keys"

# Direktlinks in die Systemeinstellungen - beschreiben hilft ihm nicht.
EINSTELLUNG_MIKROFON = ("x-apple.systempreferences:com.apple.preference.security"
                        "?Privacy_Microphone")
EINSTELLUNG_BILDSCHIRM = ("x-apple.systempreferences:com.apple.preference.security"
                          "?Privacy_ScreenCapture")
EINSTELLUNG_BEDIENHILFEN = ("x-apple.systempreferences:com.apple.preference.security"
                            "?Privacy_Accessibility")
EINSTELLUNG_SPRACHE = "x-apple.systempreferences:com.apple.preference.speech"

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
            schluessel = self.fragen("Schlüssel hier einfügen und Enter drücken:")
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
        self.ergebnisse["person"] = config.NUTZER_NAME

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
        self.schritt_rechte()
        self.schritt_telegram()
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


def einrichtung_starten(stimme=None) -> dict:
    """Startet die geführte Ersteinrichtung."""
    return Einrichtung(stimme).durchlaufen()
