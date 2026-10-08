#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Vorschläge, die Jarvis von sich aus macht - und was der Nutzer daraus macht.

Ein Vorschlag wie "Deine Erholung ist heute niedrig, morgen stehen fünf Termine
an. Soll ich zwei verschieben?" ist keine Antwort auf eine Frage, sondern kommt
von Jarvis selbst. Damit ein späteres "ja" etwas bedeutet, passieren drei Dinge:

* Der Vorschlag wird in einer Tabelle festgehalten - mit einem Schlüssel, der
  verhindert, dass derselbe Vorschlag am selben Tag zweimal kommt.
* Er wird dem Agenten über ``meldung_vormerken`` mitgegeben. Der hängt ihn erst
  am Anfang des nächsten Gedankens ans Gespräch (nie mittendrin), damit Claude
  bei "ja" weiß, was gemeint ist.
* Wer eine Ausgabe (Stimme, Anzeige) einspeist, bekommt den Text dort gesagt.
  Ohne Ausgabe gibt der Aufrufer den Text selbst zurück, etwa ein Zeitplan-Job.

Ein Vorschlag führt nichts aus. Wer "ja" sagt - per Wort oder per Geste -, hat
nur den Vorschlag angenommen. Alles, was danach nach außen wirkt (Termine
absagen, Mails senden), fragt einzeln nach Freigabe.

Werkzeuge schreiben nie selbst in den Gesprächsverlauf: Sie geben einen
Vorschlag als Text zurück. Der Verlauf bleibt so zwischen Werkzeugaufruf und
Ergebnis unberührt.
"""

import json
import sqlite3
import threading
from datetime import datetime, timedelta

import config
from modules.memory import Memory, db_schema_anlegen

SCHEMA_VORSCHLAEGE = """
CREATE TABLE IF NOT EXISTS vorschlaege (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    schluessel TEXT UNIQUE,
    quelle TEXT,
    text TEXT,
    aktion TEXT DEFAULT '',
    argumente TEXT DEFAULT '{}',
    status TEXT DEFAULT 'offen',
    angelegt TEXT,
    beantwortet TEXT DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_vorschlaege_status ON vorschlaege(status, angelegt);
"""

# Wie lange ein Vorschlag gilt, damit ein Daumen hoch ihn noch annimmt: wer eine
# Stunde später "ja" zeigt, meint meist etwas anderes.
LETZTER_VORSCHLAG_MINUTEN = 15
# Mehr als so viele offene Vorschläge auf einmal sind ohnehin nicht lesbar.
MAX_OFFENE_VORSCHLAEGE = 20
MAX_VORSCHLAG_ZEICHEN = 4000

_VORSCHLAG_ZEITFORMAT = "%Y-%m-%d %H:%M:%S"


def _vorschlaege_an() -> bool:
    """Ist die Funktion eingeschaltet? Fehlt der Schlüssel in der Konfiguration: ja."""
    try:
        return bool(config.VORSCHLAEGE_AN)
    except (AttributeError, NameError):
        return True


def _vorschlag_wahrheit(wert) -> bool:
    """Ein Ja/Nein aus einem Werkzeugaufruf: nur echtes Ja zählt, "false" ist kein Ja."""
    if isinstance(wert, str):
        return wert.strip().lower() in ("true", "ja", "1", "yes", "j", "wahr")
    return bool(wert)


class Vorschlaege:
    """Hält fest, was Jarvis von sich aus vorgeschlagen hat und wie der Nutzer antwortete."""

    def __init__(self, memory: Memory = None, agent=None, ausgabe=None, uhr=None):
        """``memory``: das Gedächtnis (die Tabelle liegt in dessen Datenbank).

        ``agent``: nimmt Vorschläge über ``meldung_vormerken`` entgegen (wird
        später mit ``agent_setzen`` gesetzt). ``ausgabe``: Funktion, die den Text
        sagt. ``uhr``: Funktion, die ein ``datetime`` liefert - für Prüfungen.
        """
        self.memory = memory or Memory()
        self.agent = agent
        self.ausgabe = ausgabe
        self._uhr = uhr or datetime.now
        self._sperre = threading.Lock()
        db_schema_anlegen(SCHEMA_VORSCHLAEGE, self.memory.db_pfad)

    # -- Hilfen ---------------------------------------------------------------

    def _jetzt(self) -> str:
        return self._uhr().strftime(_VORSCHLAG_ZEITFORMAT)

    def _vor(self, abstand: timedelta) -> str:
        return (self._uhr() - abstand).strftime(_VORSCHLAG_ZEITFORMAT)

    @staticmethod
    def _zeile(zeile: dict) -> dict:
        """Eine Tabellenzeile als Wörterbuch, die Argumente wieder als Wörterbuch."""
        eintrag = dict(zeile)
        try:
            argumente = json.loads(eintrag.get("argumente") or "{}")
        except (TypeError, ValueError):
            argumente = {}
        eintrag["argumente"] = argumente if isinstance(argumente, dict) else {}
        return eintrag

    def _nach_schluessel(self, schluessel: str):
        zeilen = self.memory._lesen("SELECT * FROM vorschlaege WHERE schluessel=?", (schluessel,))
        return self._zeile(zeilen[0]) if zeilen else None

    # -- Einbringen -----------------------------------------------------------

    def einbringen(self, schluessel: str, text: str, quelle: str = "vorschlag",
                   aktion: str = "", argumente: dict = None) -> dict:
        """Hält einen Vorschlag fest und bringt ihn ins Gespräch.

        Gibt ``{"ok", "id", "doppelt"}`` zurück. Ist die Funktion ausgeschaltet
        (``VORSCHLAEGE_AN``), kommt ``{"ok": False, "aus": True}`` und nichts
        wird gespeichert. Kennt die Tabelle den Schlüssel schon - gleich ob der
        Vorschlag noch offen oder längst beantwortet ist -, kommt
        ``doppelt: True`` und nichts wird noch einmal gesagt.

        ``aktion`` und ``argumente`` merken sich, was bei einem Ja gemeint war
        (etwa ``termine_absagen``). Ausgeführt wird dadurch nichts.
        """
        if not _vorschlaege_an():
            return {"ok": False, "aus": True}
        text = str(text or "").strip()[:MAX_VORSCHLAG_ZEICHEN]
        if not text:
            return {"ok": False, "fehler": "Ein Vorschlag braucht einen Text."}
        quelle = str(quelle or "vorschlag").strip()[:30] or "vorschlag"
        schluessel = str(schluessel or "").strip()[:200]
        if not schluessel:
            return {"ok": False, "fehler": "Ein Vorschlag braucht einen Schlüssel."}
        try:
            argument_text = json.dumps(argumente if isinstance(argumente, dict) else {},
                                       ensure_ascii=False, default=str)[:4000]
            json.loads(argument_text)  # ein abgeschnittenes JSON wäre keines mehr
        except (TypeError, ValueError):
            argument_text = "{}"

        with self._sperre:
            vorhanden = self._nach_schluessel(schluessel)
            if vorhanden is not None:
                return {"ok": True, "id": vorhanden["id"], "doppelt": True}
            try:
                nummer = self.memory._schreiben(
                    "INSERT INTO vorschlaege (schluessel, quelle, text, aktion, argumente, "
                    "status, angelegt) VALUES (?,?,?,?,?,'offen',?)",
                    (schluessel, quelle, text, str(aktion or "")[:80], argument_text,
                     self._jetzt()))
            except sqlite3.IntegrityError:
                # Ein anderer Prozess war schneller - dann ist es eben doppelt.
                vorhanden = self._nach_schluessel(schluessel)
                return {"ok": True, "id": vorhanden["id"] if vorhanden else 0, "doppelt": True}

        # Außerhalb der Sperre: Weder der Agent noch die Ausgabe sollen sie halten.
        vormerken = getattr(self.agent, "meldung_vormerken", None)
        if callable(vormerken):
            try:
                vormerken(text, quelle)
            except Exception as fehler:
                print("[vorschlaege] Vormerken fehlgeschlagen: %s" % fehler)
        if self.ausgabe is not None:
            try:
                self.ausgabe(text)
            except Exception as fehler:
                print("[vorschlaege] Ausgabe fehlgeschlagen: %s" % fehler)
        return {"ok": True, "id": nummer, "doppelt": False}

    # -- Lesen ----------------------------------------------------------------

    def offene(self, tage: int = 3) -> list:
        """Die offenen Vorschläge der letzten ``tage`` Tage, der neueste zuerst."""
        try:
            tage = max(0.0, float(tage))
        except (TypeError, ValueError):
            tage = 3.0
        zeilen = self.memory._lesen(
            "SELECT * FROM vorschlaege WHERE status='offen' AND angelegt>=? "
            "ORDER BY angelegt DESC, id DESC LIMIT ?",
            (self._vor(timedelta(days=tage)), MAX_OFFENE_VORSCHLAEGE))
        return [self._zeile(zeile) for zeile in zeilen]

    def letzter_offener(self):
        """Der jüngste offene Vorschlag der letzten 15 Minuten - oder ``None``.

        Darauf antwortet eine Geste: Wer gerade einen Vorschlag gehört hat und
        den Daumen hebt, meint ihn. Ein älterer gilt nicht mehr.
        """
        zeilen = self.memory._lesen(
            "SELECT * FROM vorschlaege WHERE status='offen' AND angelegt>=? "
            "ORDER BY angelegt DESC, id DESC LIMIT 1",
            (self._vor(timedelta(minutes=LETZTER_VORSCHLAG_MINUTEN)),))
        return self._zeile(zeilen[0]) if zeilen else None

    # -- Beantworten ----------------------------------------------------------

    def beantworten(self, id, angenommen) -> dict:
        """Hält fest, ob ein Vorschlag angenommen oder abgelehnt wurde.

        Führt selbst nichts aus. Eine schon beantwortete Antwort lässt sich nicht
        umdrehen - sonst könnte ein spätes "nein" ein gültiges "ja" überschreiben.
        """
        try:
            nummer = int(id)
        except (TypeError, ValueError):
            return {"ok": False, "fehler": "Mir fehlt die Nummer des Vorschlags."}
        angenommen = _vorschlag_wahrheit(angenommen)
        with self._sperre:
            zeilen = self.memory._lesen("SELECT * FROM vorschlaege WHERE id=?", (nummer,))
            if not zeilen:
                return {"ok": False, "fehler": "Einen Vorschlag mit dieser Nummer kenne ich nicht."}
            if zeilen[0]["status"] != "offen":
                return {"ok": False, "id": nummer, "status": zeilen[0]["status"],
                        "fehler": "Dieser Vorschlag ist schon beantwortet (%s)."
                                  % zeilen[0]["status"]}
            status = "angenommen" if angenommen else "abgelehnt"
            self.memory._schreiben(
                "UPDATE vorschlaege SET status=?, beantwortet=? WHERE id=? AND status='offen'",
                (status, self._jetzt(), nummer))
        if angenommen:
            text = ("Vermerkt: Vorschlag %d ist angenommen. Das führt selbst nichts aus - "
                    "was dafür nötig ist, frage ich einzeln nach." % nummer)
        else:
            text = "Vermerkt: Vorschlag %d ist abgelehnt." % nummer
        return {"ok": True, "id": nummer, "status": status, "text": text}
