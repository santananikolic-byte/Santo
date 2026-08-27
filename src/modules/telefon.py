#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Telefon - anrufen und SMS schicken über Twilio.

Bewusst ohne das Paket ``twilio``: Die Schnittstelle ist gewöhnliches HTTP mit
Basic-Auth. Ein Paket weniger, das bei der Installation schiefgehen kann.

Was hier geht und was nicht, ehrlich:

* **Anrufen und etwas ansagen** geht. Jarvis ruft eine Nummer an und spricht
  einen Text - etwa eine Terminerinnerung an einen Kunden.
* **Ein Gespräch führen** geht damit noch nicht. Dafür müsste Twilio den
  Rechner von außen erreichen können, und der steht hinter dem Router. Das
  braucht eine öffentliche Adresse; solange die fehlt, sagt das Modul das,
  statt so zu tun.
* **SMS** geht.

Jeder Anruf und jede SMS ist eine Wirkung nach außen und braucht deshalb eine
Freigabe. Die holt der Werkzeugkatalog ein, bevor hier etwas passiert.
"""

import json
import urllib.error
import urllib.parse
import urllib.request
import xml.sax.saxutils
from base64 import b64encode

import config
from modules.memory import Memory, db_schema_anlegen, zeitstempel

TWILIO_BASIS = "https://api.twilio.com/2010-04-01"

SCHEMA_TELEFON = """
CREATE TABLE IF NOT EXISTS anrufe (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    richtung TEXT DEFAULT 'raus',
    nummer TEXT NOT NULL,
    art TEXT DEFAULT 'anruf',
    text TEXT DEFAULT '',
    kennung TEXT DEFAULT '',
    status TEXT DEFAULT '',
    angelegt TEXT NOT NULL
);
"""


def nummer_pruefen(nummer: str):
    """Prüft eine Telefonnummer und bringt sie in die internationale Form.

    Twilio nimmt nur E.164, also ``+43664...``. Eine Nummer mit 0 vorne wird
    sonst kommentarlos abgelehnt - deshalb wird hier übersetzt, solange die
    Landesvorwahl bekannt ist.
    """
    eingabe = str(nummer or "").strip()
    if not eingabe:
        return None, "Es fehlt die Telefonnummer."
    roh = "".join(z for z in eingabe if z.isdigit() or z == "+")
    if not roh:
        return None, ("In '%s' steckt keine einzige Ziffer - das ist keine "
                      "Telefonnummer." % eingabe[:60])
    if roh.startswith("+"):
        ziffern = roh[1:]
        if not (8 <= len(ziffern) <= 15):
            return None, "Die Nummer %s hat keine plausible Länge." % nummer
        return "+" + ziffern, ""
    if roh.startswith("00"):
        return nummer_pruefen("+" + roh[2:])
    if roh.startswith("0"):
        vorwahl = (config.LANDESVORWAHL or "").strip()
        if not vorwahl:
            return None, ("Die Nummer %s beginnt mit null. Ich brauche die "
                          "Landesvorwahl - trag LANDESVORWAHL in die "
                          "Einstellungen ein, zum Beispiel +43." % nummer)
        return nummer_pruefen(vorwahl + roh[1:])
    return None, ("Die Nummer %s verstehe ich nicht. Schreib sie international, "
                  "zum Beispiel +43664123456." % nummer)


class Telefon:
    """Ruft an und schickt SMS. Ohne Zugangsdaten meldet sich alles sauber ab."""

    def __init__(self, memory: Memory = None):
        self.memory = memory or Memory()
        db_schema_anlegen(SCHEMA_TELEFON, self.memory.db_pfad)

    # -- Verfügbarkeit ------------------------------------------------------

    def verfuegbar(self) -> bool:
        """Ist Twilio eingerichtet?"""
        return bool(config.TWILIO_SID and config.TWILIO_TOKEN
                    and config.TWILIO_NUMMER)

    def zustand(self) -> dict:
        """Kurzer Überblick für den Selbsttest."""
        return {"eingerichtet": self.verfuegbar(),
                "eigene_nummer": config.TWILIO_NUMMER or "nicht gesetzt",
                "gespraech_moeglich": False,
                "hinweis": "Ansagen und SMS gehen. Für ein echtes Gespräch "
                           "bräuchte Twilio eine öffentliche Adresse zu diesem "
                           "Rechner."}

    # -- Schnittstelle ------------------------------------------------------

    def _aufruf(self, pfad: str, felder: dict) -> dict:
        """Ruft die Twilio-Schnittstelle auf."""
        if not self.verfuegbar():
            return {"ok": False,
                    "fehler": "Das Telefon ist nicht eingerichtet. In den "
                              "Einstellungen TWILIO_SID, TWILIO_TOKEN und "
                              "TWILIO_NUMMER eintragen."}
        ziel = "%s/Accounts/%s/%s" % (TWILIO_BASIS, config.TWILIO_SID, pfad)
        zugang = b64encode(("%s:%s" % (config.TWILIO_SID, config.TWILIO_TOKEN))
                           .encode("utf-8")).decode("ascii")
        anfrage = urllib.request.Request(
            ziel, data=urllib.parse.urlencode(felder).encode("utf-8"),
            method="POST",
            headers={"Authorization": "Basic %s" % zugang,
                     "Content-Type": "application/x-www-form-urlencoded"})
        try:
            with urllib.request.urlopen(anfrage, timeout=30) as antwort:
                return {"ok": True, "daten": json.loads(antwort.read().decode("utf-8"))}
        except urllib.error.HTTPError as fehler:
            try:
                inhalt = json.loads(fehler.read().decode("utf-8"))
                meldung = inhalt.get("message", str(fehler))
                code = inhalt.get("code")
            except (ValueError, OSError):
                meldung, code = str(fehler), None
            if fehler.code == 401:
                return {"ok": False,
                        "fehler": "Twilio lehnt die Zugangsdaten ab. Bitte SID und "
                                  "Token neu kopieren."}
            if code == 21608:
                return {"ok": False,
                        "fehler": "Dein Twilio-Konto ist noch ein Testkonto. Es darf "
                                  "nur an Nummern anrufen, die du dort bestätigt hast."}
            if code == 21211:
                return {"ok": False,
                        "fehler": "Twilio hält die Nummer für ungültig."}
            return {"ok": False, "fehler": "Twilio meldet: %s" % meldung[:200]}
        except (urllib.error.URLError, OSError, ValueError) as fehler:
            return {"ok": False, "fehler": "Twilio ist nicht erreichbar: %s" % fehler}

    # -- Anrufen ------------------------------------------------------------

    def anrufen(self, nummer: str, ansage: str) -> dict:
        """Ruft eine Nummer an und sagt einen Text an.

        Die Freigabe holt der Werkzeugkatalog ein, bevor diese Methode läuft.
        """
        ansage = (ansage or "").strip()
        if not ansage:
            return {"ok": False, "fehler": "Was soll ich am Telefon sagen?"}
        ziel, fehler = nummer_pruefen(nummer)
        if ziel is None:
            return {"ok": False, "fehler": fehler}

        # Der Text wird als XML übergeben - er muss maskiert werden, sonst
        # zerlegt ein Kundenname mit Ampersand die ganze Ansage.
        sicher = xml.sax.saxutils.escape(ansage[:1500])
        twiml = ('<?xml version="1.0" encoding="UTF-8"?><Response>'
                 '<Pause length="1"/>'
                 '<Say language="de-DE" voice="Polly.Vicki">%s</Say>'
                 '<Pause length="1"/>'
                 '<Say language="de-DE" voice="Polly.Vicki">%s</Say>'
                 '</Response>' % (sicher, sicher))

        ergebnis = self._aufruf("Calls.json", {
            "To": ziel, "From": config.TWILIO_NUMMER, "Twiml": twiml})
        if not ergebnis.get("ok"):
            self._merken("raus", ziel, "anruf", ansage, "", "fehlgeschlagen")
            return ergebnis

        kennung = (ergebnis["daten"] or {}).get("sid", "")
        self._merken("raus", ziel, "anruf", ansage, kennung,
                     (ergebnis["daten"] or {}).get("status", "gestartet"))
        return {"ok": True, "nummer": ziel, "kennung": kennung,
                "text": "Ich rufe %s an und sage die Nachricht zweimal an." % ziel}

    def sms_senden(self, nummer: str, text: str) -> dict:
        """Schickt eine SMS."""
        text = (text or "").strip()
        if not text:
            return {"ok": False, "fehler": "Die SMS ist leer."}
        ziel, fehler = nummer_pruefen(nummer)
        if ziel is None:
            return {"ok": False, "fehler": fehler}

        ergebnis = self._aufruf("Messages.json", {
            "To": ziel, "From": config.TWILIO_NUMMER, "Body": text[:1500]})
        if not ergebnis.get("ok"):
            self._merken("raus", ziel, "sms", text, "", "fehlgeschlagen")
            return ergebnis
        kennung = (ergebnis["daten"] or {}).get("sid", "")
        self._merken("raus", ziel, "sms", text, kennung, "gesendet")
        return {"ok": True, "nummer": ziel, "kennung": kennung,
                "text": "SMS an %s ist raus." % ziel}

    def anrufliste(self, limit: int = 20) -> dict:
        """Was zuletzt telefoniert wurde."""
        zeilen = self.memory._lesen(
            "SELECT * FROM anrufe ORDER BY id DESC LIMIT ?", (limit,))
        return {"ok": True, "anzahl": len(zeilen),
                "anrufe": [{"nummer": z["nummer"], "art": z["art"],
                            "status": z["status"], "zeit": z["angelegt"],
                            "text": (z["text"] or "")[:120]} for z in zeilen],
                "text": ("Zuletzt: %s" % ", ".join(
                    "%s an %s" % (z["art"], z["nummer"]) for z in zeilen[:4]))
                        if zeilen else "Es wurde noch nicht telefoniert."}

    def _merken(self, richtung, nummer, art, text, kennung, status):
        """Schreibt einen Anruf ins Protokoll."""
        self.memory._schreiben(
            "INSERT INTO anrufe (richtung, nummer, art, text, kennung, status, "
            "angelegt) VALUES (?,?,?,?,?,?,?)",
            (richtung, nummer, art, (text or "")[:2000], kennung, status,
             zeitstempel()))
