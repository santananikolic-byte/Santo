#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Versand - echte Nachrichten über vier Wege.

    telegram   Text oder Sprachnachricht
    mail       über SMTP
    imessage   Nachrichten-App per AppleScript (auch SMS)
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

# Nummer und Text kommen über argv herein, nicht über Textersetzung.
IMESSAGE_SKRIPT = """on run argv
    set zielAdresse to item 1 of argv
    set nachrichtText to item 2 of argv
    tell application "Messages"
        try
            set zielDienst to 1st service whose service type = iMessage
            set zielPerson to buddy zielAdresse of zielDienst
            send nachrichtText to zielPerson
            return "iMessage"
        on error
            set smsDienst to 1st service whose service type = SMS
            set smsPerson to buddy zielAdresse of smsDienst
            send nachrichtText to smsPerson
            return "SMS"
        end try
    end tell
end run"""

KANAELE = ("telegram", "mail", "imessage", "whatsapp")


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
        if kanal in ("sms", "nachrichten"):
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
            return self._imessage(an, text)
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

    def _imessage(self, an: str, text: str) -> dict:
        """iMessage oder SMS über die Nachrichten-App."""
        if not shutil.which("osascript"):
            return {"ok": False,
                    "fehler": "iMessage gibt es nur auf einem Mac mit der Nachrichten-App."}
        if not an:
            return {"ok": False,
                    "fehler": "Ich brauche eine Telefonnummer oder Apple-ID."}
        try:
            # Das Skript kommt über stdin, Nummer und Text als eigene Argumente.
            ergebnis = subprocess.run(
                ["osascript", "-", str(an), str(text)],
                input=IMESSAGE_SKRIPT, capture_output=True, text=True,
                timeout=45, shell=False)
        except (OSError, subprocess.SubprocessError) as fehler:
            return {"ok": False, "fehler": "Die Nachrichten-App antwortet nicht: %s" % fehler}
        if ergebnis.returncode != 0:
            meldung = (ergebnis.stderr or "").strip()[:300]
            if "not allowed" in meldung.lower() or "1743" in meldung:
                return {"ok": False,
                        "fehler": "Die Nachrichten-App verweigert den Zugriff. In den "
                                  "Systemeinstellungen unter Datenschutz, Automation dem "
                                  "Terminal die Steuerung von Nachrichten erlauben."}
            return {"ok": False, "fehler": "Die Nachricht ging nicht raus: %s" % meldung}
        weg = (ergebnis.stdout or "iMessage").strip() or "iMessage"
        return {"ok": True, "kanal": "imessage",
                "text": "Nachricht an %s über %s ist raus." % (an, weg)}

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
