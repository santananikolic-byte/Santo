#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Routinen - gespeicherte Abläufe, die der Nutzer per Sprache anlegt.

Eine Routine ist kein starres Skript, sondern eine Anweisung an Claude selbst.
Er liest sie und entscheidet mit seinen Werkzeugen, wie er sie umsetzt. Das ist
robuster als eine feste Schrittfolge: ändert sich etwas, passt Claude sich an.

Namen trifft die Spracherkennung selten wortgenau. Deshalb wird dreistufig
gesucht: exakt, dann Teiltreffer, dann einzelne Wörter.
"""

import re

from modules.memory import Memory, db_schema_anlegen, heute_datum, zeitstempel

SCHEMA_ROUTINEN = """
CREATE TABLE IF NOT EXISTS routinen (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    anweisung TEXT NOT NULL,
    uhrzeit TEXT DEFAULT '',
    tage TEXT DEFAULT 'taeglich',
    aktiv INTEGER DEFAULT 1,
    zuletzt TEXT DEFAULT '',
    laeufe INTEGER DEFAULT 0,
    angelegt TEXT NOT NULL
);
"""

UHRZEIT_MUSTER = re.compile(r"^([01]?\d|2[0-3])[:.]?([0-5]\d)?$")


def name_normalisieren(name: str) -> str:
    """Kleinschreibung, Umlaute ausgeschrieben, Sonderzeichen weg."""
    text = (name or "").strip().lower()
    for alt, neu in (("ä", "ae"), ("ö", "oe"), ("ü", "ue"), ("ß", "ss")):
        text = text.replace(alt, neu)
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9 ]+", " ", text)).strip()


def name_kompakt(name: str) -> str:
    """Wie :func:`name_normalisieren`, aber ohne jedes Leerzeichen."""
    return name_normalisieren(name).replace(" ", "")


def uhrzeit_normalisieren(uhrzeit: str) -> str:
    """Macht aus '18', '18 Uhr', '1800' oder '18:00' ein sauberes 'HH:MM'."""
    roh = (uhrzeit or "").strip().lower()
    if not roh:
        return ""
    roh = roh.replace("uhr", "").strip()
    roh = re.sub(r"[^0-9:.]", "", roh)
    if not roh:
        return ""
    if ":" in roh or "." in roh:
        teile = re.split(r"[:.]", roh)
        stunde = teile[0]
        minute = teile[1] if len(teile) > 1 and teile[1] else "00"
    elif len(roh) == 4:
        stunde, minute = roh[:2], roh[2:]
    else:
        stunde, minute = roh, "00"
    try:
        stunde_zahl, minute_zahl = int(stunde), int(minute)
    except ValueError:
        return ""
    if not (0 <= stunde_zahl <= 23 and 0 <= minute_zahl <= 59):
        return ""
    return "%02d:%02d" % (stunde_zahl, minute_zahl)


class Routines:
    """Verwaltet gespeicherte Abläufe und findet sie auch bei ungenauem Namen."""

    def __init__(self, memory: Memory = None):
        self.memory = memory or Memory()
        db_schema_anlegen(SCHEMA_ROUTINEN, self.memory.db_pfad)

    # -- Anlegen und pflegen ------------------------------------------------

    def routine_anlegen(self, name: str, anweisung: str, uhrzeit: str = "",
                        tage: str = "taeglich") -> dict:
        """Legt eine Routine an oder überschreibt eine gleichnamige."""
        name = (name or "").strip()
        anweisung = (anweisung or "").strip()
        if not name:
            return {"ok": False, "fehler": "Die Routine braucht einen Namen."}
        if not anweisung:
            return {"ok": False,
                    "fehler": "Sag mir, was die Routine tun soll, dann lege ich sie an."}
        zeit = uhrzeit_normalisieren(uhrzeit)
        if uhrzeit and not zeit:
            return {"ok": False,
                    "fehler": "Die Uhrzeit '%s' verstehe ich nicht. Sag sie zum Beispiel "
                              "als 18 Uhr oder 18:30." % uhrzeit}

        vorhanden = self._exakt(name)
        if vorhanden:
            self.memory._schreiben(
                "UPDATE routinen SET anweisung=?, uhrzeit=?, tage=?, aktiv=1 WHERE id=?",
                (anweisung, zeit, tage, vorhanden["id"]))
            return {"ok": True, "id": vorhanden["id"], "name": name, "uhrzeit": zeit,
                    "ersetzt": True,
                    "text": "Die Routine %s ist aktualisiert.%s"
                            % (name, (" Sie läuft künftig um %s." % zeit) if zeit else "")}

        nummer = self.memory._schreiben(
            "INSERT INTO routinen (name, anweisung, uhrzeit, tage, aktiv, zuletzt, laeufe, "
            "angelegt) VALUES (?,?,?,?,1,'',0,?)",
            (name, anweisung, zeit, tage, zeitstempel()))
        return {"ok": True, "id": nummer, "name": name, "uhrzeit": zeit, "ersetzt": False,
                "text": "Routine %s angelegt.%s"
                        % (name, (" Sie läuft täglich um %s." % zeit) if zeit
                           else " Sag einfach ihren Namen, dann führe ich sie aus.")}

    def routine_loeschen(self, name: str) -> dict:
        """Löscht eine Routine - auch bei ungenauem Namen."""
        treffer = self.routine_finden(name)
        if not treffer:
            return {"ok": False, "fehler": "Eine Routine namens '%s' kenne ich nicht." % name}
        self.memory._schreiben("DELETE FROM routinen WHERE id=?", (treffer["id"],))
        return {"ok": True, "text": "Die Routine %s ist gelöscht." % treffer["name"]}

    def routinen_liste(self, nur_aktive: bool = True) -> list:
        """Alle Routinen."""
        wo = "WHERE aktiv=1" if nur_aktive else ""
        return self.memory._lesen("SELECT * FROM routinen %s ORDER BY name" % wo)

    def geplante_routinen(self) -> list:
        """Routinen mit Uhrzeit - genau die hängen sich in den Zeitplan."""
        return self.memory._lesen(
            "SELECT * FROM routinen WHERE aktiv=1 AND uhrzeit<>'' ORDER BY uhrzeit")

    # -- Suchen -------------------------------------------------------------

    def _exakt(self, name: str):
        """Stufe 1: der normalisierte Name stimmt genau überein."""
        gesucht = name_normalisieren(name)
        for zeile in self.memory._lesen("SELECT * FROM routinen"):
            if name_normalisieren(zeile["name"]) == gesucht:
                return zeile
        return None

    def routine_finden(self, name: str):
        """Findet eine Routine dreistufig: exakt, Teiltreffer, einzelne Wörter.

        Damit findet 'den Tages Bericht' die Routine 'tagesbericht'.
        """
        if not name or not str(name).strip():
            return None
        alle = self.memory._lesen("SELECT * FROM routinen WHERE aktiv=1")
        if not alle:
            return None

        gesucht = name_normalisieren(name)
        gesucht_kompakt = name_kompakt(name)

        # Stufe 1: exakt
        for zeile in alle:
            if name_normalisieren(zeile["name"]) == gesucht:
                return zeile

        # Stufe 2: Teiltreffer, auch ohne Leerzeichen ("dentagesbericht" enthält
        # "tagesbericht")
        beste, bestwert = None, 0
        for zeile in alle:
            kompakt = name_kompakt(zeile["name"])
            if not kompakt:
                continue
            if kompakt in gesucht_kompakt or gesucht_kompakt in kompakt:
                wert = len(kompakt)
                if wert > bestwert:
                    beste, bestwert = zeile, wert
        if beste is not None:
            return beste

        # Stufe 3: einzelne Wörter ab 4 Zeichen
        woerter = [w for w in gesucht.split() if len(w) >= 4]
        if not woerter:
            return None
        beste, bestwert = None, 0
        for zeile in alle:
            kompakt = name_kompakt(zeile["name"])
            treffer = sum(1 for wort in woerter if wort in kompakt)
            if treffer > bestwert:
                beste, bestwert = zeile, treffer
        return beste if bestwert > 0 else None

    # -- Ausführen ----------------------------------------------------------

    def routine_ausfuehren(self, name: str, agent=None) -> dict:
        """Übergibt die Anweisung der Routine an Claude - er entscheidet das Wie."""
        treffer = self.routine_finden(name)
        if not treffer:
            vorhandene = ", ".join(z["name"] for z in self.routinen_liste()) or "keine"
            return {"ok": False,
                    "fehler": "Eine Routine namens '%s' kenne ich nicht. Ich habe: %s."
                              % (name, vorhandene)}

        self.memory._schreiben(
            "UPDATE routinen SET zuletzt=?, laeufe=laeufe+1 WHERE id=?",
            (zeitstempel(), treffer["id"]))

        if agent is None or not getattr(agent, "einsatzbereit", lambda: False)():
            return {"ok": False, "name": treffer["name"], "anweisung": treffer["anweisung"],
                    "fehler": "Ohne Anthropic-Schlüssel kann ich die Routine %s nicht "
                              "ausführen." % treffer["name"]}

        auftrag = ("Führe jetzt die gespeicherte Routine '%s' aus. Das ist die Anweisung:\n\n%s\n\n"
                   "Nutze dafür deine Werkzeuge und melde am Ende kurz, was du getan hast."
                   % (treffer["name"], treffer["anweisung"]))
        antwort = agent.denken(auftrag, protokollieren=False, anzeigen=False)
        return {"ok": True, "name": treffer["name"], "text": antwort}

    def statistik(self) -> dict:
        """Wie viele Routinen es gibt und welche geplant sind."""
        alle = self.routinen_liste()
        geplant = self.geplante_routinen()
        return {"anzahl": len(alle), "geplant": len(geplant),
                "namen": [z["name"] for z in alle],
                "zeiten": {z["name"]: z["uhrzeit"] for z in geplant}}
