#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Versand - echte Nachrichten über vier Wege.

    telegram   Text oder Sprachnachricht
    mail       über SMTP
    imessage   Nachrichten-App per AppleScript, mit deiner eigenen Nummer
    sms        dasselbe, aber zuerst als SMS (iPhone-Weiterleitung an den Mac)
    whatsapp   über einen MCP-Server

Beim AppleScript werden Nummer und Text **als Argumente übergeben**, nicht in
den Skripttext eingebaut. Ein Text mit Anführungszeichen würde sonst das Skript
aufbrechen - und wer den Text bestimmt, bestimmte dann das Skript.

Jeder Versand nach außen braucht eine Freigabe. Die holt der Werkzeugkatalog
ein, bevor eine Methode dieses Moduls überhaupt aufgerufen wird.
"""

import os
import shutil
import subprocess

import config

# Nummer, Text und gewünschter Weg kommen über argv herein, nicht über Textersetzung.
# Seit macOS 12 heißen die Begriffe "account" und "participant", davor "service"
# und "buddy". Ein Skript mit unbekannten Begriffen lässt sich gar nicht erst
# übersetzen - deshalb zwei Skripte, das neue zuerst.
# SMS gehen nur, wenn auf dem iPhone die SMS-Weiterleitung an den Mac an ist.
IMESSAGE_SKRIPT = """on run argv
    set zielAdresse to item 1 of argv
    set nachrichtText to item 2 of argv
    set wunsch to item 3 of argv
    tell application "Messages"
        if wunsch is "SMS" then
            set reihenfolge to {SMS, iMessage}
        else
            set reihenfolge to {iMessage, SMS}
        end if
        repeat with dienstArt in reihenfolge
            set gefunden to false
            try
                set konto to 1st account whose service type = (contents of dienstArt)
                set person to participant zielAdresse of konto
                set gefunden to true
            end try
            if gefunden then
                send nachrichtText to person
                if (contents of dienstArt) is SMS then return "SMS"
                return "iMessage"
            end if
        end repeat
    end tell
    error "Kein Konto in der Nachrichten-App kann an diese Adresse schicken."
end run"""

IMESSAGE_SKRIPT_ALT = """on run argv
    set zielAdresse to item 1 of argv
    set nachrichtText to item 2 of argv
    set wunsch to item 3 of argv
    tell application "Messages"
        if wunsch is "SMS" then
            set reihenfolge to {SMS, iMessage}
        else
            set reihenfolge to {iMessage, SMS}
        end if
        repeat with dienstArt in reihenfolge
            set gefunden to false
            try
                set konto to 1st service whose service type = (contents of dienstArt)
                set person to buddy zielAdresse of konto
                set gefunden to true
            end try
            if gefunden then
                send nachrichtText to person
                if (contents of dienstArt) is SMS then return "SMS"
                return "iMessage"
            end if
        end repeat
    end tell
    error "Kein Konto in der Nachrichten-App kann an diese Adresse schicken."
end run"""

KANAELE = ("telegram", "mail", "imessage", "sms", "whatsapp")


class Messenger:
    """Verschickt Nachrichten über den jeweils passenden Weg."""

    def __init__(self, telegram=None, mail=None, mcp=None, stimme=None):
        self.telegram = telegram
        self.mail = mail
        self.mcp = mcp
        self.stimme = stimme

    def zustand(self) -> dict:
        """Welche Wege stehen offen?"""
        return {
            "telegram": bool(self.telegram and self.telegram.verfuegbar()),
            "mail": bool(self.mail and self.mail.senden_moeglich()),
            "imessage": bool(shutil.which("osascript")),
            "whatsapp": bool(self._whatsapp_werkzeug()),
        }

    # -- Hauptzugang --------------------------------------------------------

    def nachricht_senden(self, kanal: str, an: str, text: str,
                         als_sprache: bool = False, betreff: str = "") -> dict:
        """Verschickt eine Nachricht über den gewählten Kanal."""
        kanal = (kanal or "").strip().lower()
        text = (text or "").strip()
        if not text:
            return {"ok": False, "fehler": "Die Nachricht ist leer."}
        wunsch = "iMessage"
        if kanal in ("sms", "nachrichten"):
            wunsch = "SMS" if kanal == "sms" else wunsch
            kanal = "imessage"
        if kanal in ("email", "e-mail"):
            kanal = "mail"
        if kanal not in KANAELE:
            return {"ok": False,
                    "fehler": "Den Kanal '%s' kenne ich nicht. Möglich sind: %s."
                              % (kanal, ", ".join(KANAELE))}

        if kanal == "telegram":
            return self._telegram(an, text, als_sprache)
        if kanal == "mail":
            return self._mail(an, betreff, text)
        if kanal == "imessage":
            return self._imessage(an, text, wunsch)
        return self._whatsapp(an, text)

    # -- Die einzelnen Wege -------------------------------------------------

    def _telegram(self, an: str, text: str, als_sprache: bool) -> dict:
        """Telegram, wahlweise als Sprachnachricht."""
        if self.telegram is None or not self.telegram.verfuegbar():
            return {"ok": False, "fehler": "Telegram ist nicht eingerichtet."}
        if als_sprache and self.stimme is not None:
            pfad = self.stimme.sprachdatei_erzeugen(text)
            if pfad:
                ergebnis = self.telegram.datei_senden(pfad, "sendVoice", "voice", an or "")
                try:
                    os.remove(pfad)
                except OSError:
                    pass
                if ergebnis.get("ok"):
                    return {"ok": True, "kanal": "telegram",
                            "text": "Sprachnachricht ist raus."}
                # Klappt die Sprachnachricht nicht, geht wenigstens der Text raus.
                print("[versand] Sprachnachricht fehlgeschlagen: %s"
                      % ergebnis.get("fehler"))
        ergebnis = self.telegram.senden(text, an or "")
        if ergebnis.get("ok"):
            return {"ok": True, "kanal": "telegram", "text": "Nachricht ist raus."}
        return ergebnis

    def _mail(self, an: str, betreff: str, text: str) -> dict:
        """E-Mail über SMTP."""
        if self.mail is None or not self.mail.senden_moeglich():
            return {"ok": False, "fehler": "Der Mailversand ist nicht eingerichtet."}
        if not an:
            return {"ok": False, "fehler": "Ich brauche eine Empfängeradresse."}
        ergebnis = self.mail.senden(an, betreff or "Nachricht von %s" % config.NUTZER_NAME,
                                    text)
        if ergebnis.get("ok"):
            ergebnis["kanal"] = "mail"
        return ergebnis

    def _imessage(self, an: str, text: str, wunsch: str = "iMessage") -> dict:
        """iMessage oder SMS über die Nachrichten-App - mit deiner eigenen Nummer."""
        if not shutil.which("osascript"):
            return {"ok": False,
                    "fehler": "iMessage und SMS über den Mac gibt es nur auf einem Mac "
                              "mit der Nachrichten-App."}
        if not an:
            return {"ok": False,
                    "fehler": "Ich brauche eine Telefonnummer oder Apple-ID."}
        meldung = ""
        for skript in (IMESSAGE_SKRIPT, IMESSAGE_SKRIPT_ALT):
            try:
                # Das Skript kommt über stdin, Nummer, Text und Weg als eigene Argumente.
                ergebnis = subprocess.run(
                    ["osascript", "-", str(an), str(text), wunsch],
                    input=skript, capture_output=True, text=True,
                    timeout=45, shell=False)
            except (OSError, subprocess.SubprocessError) as fehler:
                return {"ok": False, "fehler": "Die Nachrichten-App antwortet nicht: %s" % fehler}
            if ergebnis.returncode == 0:
                weg = (ergebnis.stdout or "iMessage").strip() or "iMessage"
                return {"ok": True, "kanal": "imessage", "weg": weg,
                        "text": "Nachricht an %s über %s ist raus." % (an, weg)}
            meldung = (ergebnis.stderr or "").strip()[:300]
            if "not allowed" in meldung.lower() or "1743" in meldung:
                return {"ok": False,
                        "fehler": "Die Nachrichten-App verweigert den Zugriff. In den "
                                  "Systemeinstellungen unter Datenschutz, Automation dem "
                                  "Terminal die Steuerung von Nachrichten erlauben."}
            # Nur wenn das Skript gar nicht übersetzt werden konnte (ältere Begriffe),
            # wird das zweite versucht - sonst könnte eine Nachricht doppelt rausgehen.
            if "-2741" not in meldung and "-2740" not in meldung:
                break
        if "Kein Konto" in meldung and wunsch == "SMS":
            meldung = ("Für SMS muss auf dem iPhone unter Einstellungen, Nachrichten, "
                       "SMS-Weiterleitung dieser Mac eingeschaltet sein.")
        return {"ok": False, "fehler": "Die Nachricht ging nicht raus: %s" % meldung}

    def _whatsapp_werkzeug(self) -> str:
        """Sucht ein Sende-Werkzeug beim WhatsApp-MCP-Server."""
        if self.mcp is None:
            return ""
        for werkzeug in self.mcp.alle_werkzeuge():
            name = werkzeug.get("name", "")
            if name.startswith("mcp__whatsapp__") and "send" in name.lower():
                return name
        return ""

    def _whatsapp(self, an: str, text: str) -> dict:
        """WhatsApp über den MCP-Server."""
        werkzeug = self._whatsapp_werkzeug()
        if not werkzeug:
            return {"ok": False,
                    "fehler": "WhatsApp läuft über einen MCP-Dienst. In "
                              "config/mcp_servers.json den Eintrag 'whatsapp' auf "
                              "\"aus\": false stellen."}
        if not an:
            return {"ok": False, "fehler": "Ich brauche eine Telefonnummer."}
        ergebnis = self.mcp.aufrufen(werkzeug, {"recipient": an, "message": text})
        if ergebnis.get("ok"):
            return {"ok": True, "kanal": "whatsapp",
                    "text": "WhatsApp-Nachricht an %s ist raus." % an}
        return ergebnis
