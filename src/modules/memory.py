#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Gedächtnis, Ebene 0 - Notizen, Kontakte, Kennzahlen, offene Punkte, Protokoll.

Alles liegt lokal in einer SQLite-Datei. Supabase wird, falls konfiguriert,
nur zusätzlich gespiegelt: Die Wahrheit steht immer auf dem Rechner des Nutzers.
"""

import json
import sqlite3
import threading
import urllib.error
import urllib.request
from datetime import datetime, timedelta

import config

_DB_SPERRE = threading.Lock()

SCHEMA_MEMORY = """
CREATE TABLE IF NOT EXISTS notizen (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    text TEXT NOT NULL,
    kategorie TEXT DEFAULT 'allgemein',
    angelegt TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS kontakte (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    firma TEXT DEFAULT '',
    telefon TEXT DEFAULT '',
    email TEXT DEFAULT '',
    adresse TEXT DEFAULT '',
    notiz TEXT DEFAULT '',
    angelegt TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS kennzahlen (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    wert REAL NOT NULL,
    einheit TEXT DEFAULT '',
    datum TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS offene_punkte (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    text TEXT NOT NULL,
    faellig TEXT DEFAULT '',
    erledigt INTEGER DEFAULT 0,
    angelegt TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS aktionen (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    werkzeug TEXT NOT NULL,
    argumente TEXT DEFAULT '',
    ergebnis TEXT DEFAULT '',
    status TEXT DEFAULT 'ok',
    zeit TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS verlauf (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    rolle TEXT NOT NULL,
    text TEXT NOT NULL,
    zeit TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_notizen_text ON notizen(text);
CREATE INDEX IF NOT EXISTS idx_verlauf_zeit ON verlauf(zeit);
"""


def zeitstempel() -> str:
    """Aktuelle Zeit als ``JJJJ-MM-TT HH:MM:SS``."""
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def heute_datum() -> str:
    """Heutiges Datum als ``JJJJ-MM-TT``."""
    return datetime.now().strftime("%Y-%m-%d")


def db_verbindung(pfad: str = None) -> sqlite3.Connection:
    """Öffnet eine SQLite-Verbindung mit Zeilen-Zugriff über Spaltennamen."""
    verbindung = sqlite3.connect(pfad or config.DB_PFAD, timeout=15,
                                 check_same_thread=False)
    verbindung.row_factory = sqlite3.Row
    verbindung.execute("PRAGMA journal_mode=WAL")
    return verbindung


def db_schema_anlegen(schema: str, pfad: str = None):
    """Legt die Tabellen eines Moduls an, falls sie noch fehlen."""
    with _DB_SPERRE:
        verbindung = db_verbindung(pfad)
        try:
            verbindung.executescript(schema)
            verbindung.commit()
        finally:
            verbindung.close()


def zeilen_zu_liste(zeilen) -> list:
    """Wandelt SQLite-Zeilen in gewöhnliche Wörterbücher um."""
    return [dict(zeile) for zeile in zeilen]


class Memory:
    """Das Kurzzeit- und Sachgedächtnis: Notizen, Kontakte, Zahlen, Protokoll."""

    def __init__(self, db_pfad: str = None):
        self.db_pfad = db_pfad or config.DB_PFAD
        db_schema_anlegen(SCHEMA_MEMORY, self.db_pfad)

    # -- Grundlagen ---------------------------------------------------------

    def _schreiben(self, sql: str, werte: tuple = ()) -> int:
        with _DB_SPERRE:
            verbindung = db_verbindung(self.db_pfad)
            try:
                zeiger = verbindung.execute(sql, werte)
                verbindung.commit()
                return zeiger.lastrowid
            finally:
                verbindung.close()

    def _lesen(self, sql: str, werte: tuple = ()) -> list:
        verbindung = db_verbindung(self.db_pfad)
        try:
            return zeilen_zu_liste(verbindung.execute(sql, werte).fetchall())
        finally:
            verbindung.close()

    # -- Notizen ------------------------------------------------------------

    def notiz_speichern(self, text: str, kategorie: str = "allgemein") -> dict:
        """Hält eine Notiz fest und gibt sie mit ihrer Nummer zurück."""
        text = (text or "").strip()
        if not text:
            return {"ok": False, "fehler": "Die Notiz ist leer."}
        nummer = self._schreiben(
            "INSERT INTO notizen (text, kategorie, angelegt) VALUES (?,?,?)",
            (text, kategorie or "allgemein", zeitstempel()))
        self._spiegeln("notizen", {"text": text, "kategorie": kategorie})
        return {"ok": True, "id": nummer, "text": text, "kategorie": kategorie}

    def notizen_suchen(self, begriff: str, limit: int = 20) -> list:
        """Sucht Notizen, deren Text den Begriff enthält."""
        begriff = (begriff or "").strip()
        if not begriff:
            return self.notizen_letzte(limit)
        return self._lesen(
            "SELECT * FROM notizen WHERE text LIKE ? OR kategorie LIKE ? "
            "ORDER BY id DESC LIMIT ?",
            ("%%%s%%" % begriff, "%%%s%%" % begriff, limit))

    def notizen_letzte(self, limit: int = 10) -> list:
        """Die zuletzt angelegten Notizen."""
        return self._lesen("SELECT * FROM notizen ORDER BY id DESC LIMIT ?", (limit,))

    def notiz_loeschen(self, nummer: int) -> bool:
        """Löscht eine Notiz anhand ihrer Nummer."""
        vorher = self._lesen("SELECT id FROM notizen WHERE id=?", (nummer,))
        if not vorher:
            return False
        self._schreiben("DELETE FROM notizen WHERE id=?", (nummer,))
        return True

    # -- Kontakte -----------------------------------------------------------

    def kontakt_anlegen(self, name: str, firma: str = "", telefon: str = "",
                        email: str = "", adresse: str = "", notiz: str = "") -> dict:
        """Legt einen Kontakt an oder ergänzt einen bereits vorhandenen."""
        name = (name or "").strip()
        if not name:
            return {"ok": False, "fehler": "Ohne Namen kann ich keinen Kontakt anlegen."}
        vorhanden = self._lesen(
            "SELECT * FROM kontakte WHERE lower(name)=lower(?) LIMIT 1", (name,))
        if vorhanden:
            alt = vorhanden[0]
            neu = {
                "firma": firma or alt["firma"],
                "telefon": telefon or alt["telefon"],
                "email": email or alt["email"],
                "adresse": adresse or alt["adresse"],
                "notiz": (alt["notiz"] + " | " + notiz).strip(" |") if notiz else alt["notiz"],
            }
            self._schreiben(
                "UPDATE kontakte SET firma=?, telefon=?, email=?, adresse=?, notiz=? "
                "WHERE id=?",
                (neu["firma"], neu["telefon"], neu["email"], neu["adresse"],
                 neu["notiz"], alt["id"]))
            return {"ok": True, "id": alt["id"], "name": name, "aktualisiert": True}
        nummer = self._schreiben(
            "INSERT INTO kontakte (name, firma, telefon, email, adresse, notiz, angelegt) "
            "VALUES (?,?,?,?,?,?,?)",
            (name, firma, telefon, email, adresse, notiz, zeitstempel()))
        self._spiegeln("kontakte", {"name": name, "firma": firma})
        return {"ok": True, "id": nummer, "name": name, "aktualisiert": False}

    def kontakt_suchen(self, begriff: str, limit: int = 20) -> list:
        """Sucht Kontakte über Name, Firma, Telefon, E-Mail oder Notiz."""
        begriff = (begriff or "").strip()
        if not begriff:
            return self._lesen("SELECT * FROM kontakte ORDER BY name LIMIT ?", (limit,))
        muster = "%%%s%%" % begriff
        return self._lesen(
            "SELECT * FROM kontakte WHERE name LIKE ? OR firma LIKE ? OR telefon LIKE ? "
            "OR email LIKE ? OR notiz LIKE ? ORDER BY name LIMIT ?",
            (muster, muster, muster, muster, muster, limit))

    def kontakte_alle(self) -> list:
        """Alle Kontakte, alphabetisch."""
        return self._lesen("SELECT * FROM kontakte ORDER BY name")

    # -- Kennzahlen ---------------------------------------------------------

    def kennzahl_setzen(self, name: str, wert: float, einheit: str = "") -> dict:
        """Hält eine Kennzahl mit Datum fest (Verlauf bleibt erhalten)."""
        try:
            wert = float(wert)
        except (TypeError, ValueError):
            return {"ok": False, "fehler": "Der Wert ist keine Zahl."}
        nummer = self._schreiben(
            "INSERT INTO kennzahlen (name, wert, einheit, datum) VALUES (?,?,?,?)",
            (name, wert, einheit, heute_datum()))
        return {"ok": True, "id": nummer, "name": name, "wert": wert, "einheit": einheit}

    def kennzahlen(self, limit: int = 30) -> list:
        """Der jeweils jüngste Stand jeder Kennzahl."""
        return self._lesen(
            "SELECT name, wert, einheit, datum FROM kennzahlen k WHERE id = "
            "(SELECT max(id) FROM kennzahlen WHERE name = k.name) "
            "ORDER BY name LIMIT ?", (limit,))

    # -- Offene Punkte ------------------------------------------------------

    def punkt_anlegen(self, text: str, faellig: str = "") -> dict:
        """Merkt sich etwas, das noch zu erledigen ist."""
        text = (text or "").strip()
        if not text:
            return {"ok": False, "fehler": "Der offene Punkt ist leer."}
        nummer = self._schreiben(
            "INSERT INTO offene_punkte (text, faellig, erledigt, angelegt) VALUES (?,?,0,?)",
            (text, faellig, zeitstempel()))
        return {"ok": True, "id": nummer, "text": text, "faellig": faellig}

    def punkte_offen(self, tage: int = 14, limit: int = 25) -> list:
        """Offene Punkte der letzten ``tage`` Tage."""
        grenze = (datetime.now() - timedelta(days=tage)).strftime("%Y-%m-%d 00:00:00")
        return self._lesen(
            "SELECT * FROM offene_punkte WHERE erledigt=0 AND angelegt>=? "
            "ORDER BY id DESC LIMIT ?", (grenze, limit))

    def punkt_erledigen(self, nummer: int) -> bool:
        """Hakt einen offenen Punkt ab."""
        vorher = self._lesen("SELECT id FROM offene_punkte WHERE id=? AND erledigt=0",
                             (nummer,))
        if not vorher:
            return False
        self._schreiben("UPDATE offene_punkte SET erledigt=1 WHERE id=?", (nummer,))
        return True

    # -- Protokoll ----------------------------------------------------------

    def aktion_protokollieren(self, werkzeug: str, argumente=None, ergebnis: str = "",
                              status: str = "ok") -> int:
        """Schreibt jede ausgeführte Aktion mit - Grundlage für das Dashboard."""
        try:
            argument_text = json.dumps(argumente, ensure_ascii=False)[:2000]
        except (TypeError, ValueError):
            argument_text = str(argumente)[:2000]
        return self._schreiben(
            "INSERT INTO aktionen (werkzeug, argumente, ergebnis, status, zeit) "
            "VALUES (?,?,?,?,?)",
            (werkzeug, argument_text, str(ergebnis)[:2000], status, zeitstempel()))

    def protokoll(self, limit: int = 30) -> list:
        """Die zuletzt ausgeführten Aktionen."""
        return self._lesen("SELECT * FROM aktionen ORDER BY id DESC LIMIT ?", (limit,))

    # -- Gesprächsverlauf ---------------------------------------------------

    def verlauf_anhaengen(self, rolle: str, text: str) -> int:
        """Hängt eine Äußerung an den dauerhaften Verlauf an."""
        return self._schreiben(
            "INSERT INTO verlauf (rolle, text, zeit) VALUES (?,?,?)",
            (rolle, (text or "")[:8000], zeitstempel()))

    def verlauf_letzte(self, limit: int = 20) -> list:
        """Die letzten Äußerungen, in zeitlicher Reihenfolge."""
        zeilen = self._lesen("SELECT * FROM verlauf ORDER BY id DESC LIMIT ?", (limit,))
        return list(reversed(zeilen))

    def verlauf_zeitraum(self, von: str, bis: str, begriff: str = "",
                         limit: int = 500) -> list:
        """Äußerungen zwischen zwei Zeitstempeln, in zeitlicher Reihenfolge.

        Mit ``begriff`` kommen nur Zeilen, in denen der Begriff vorkommt - egal,
        wer gesprochen hat.
        """
        sql = "SELECT * FROM verlauf WHERE zeit BETWEEN ? AND ?"
        werte = [von, bis]
        begriff = (begriff or "").strip()
        if begriff:
            sql += " AND text LIKE ?"
            werte.append("%%%s%%" % begriff)
        sql += " ORDER BY id DESC LIMIT ?"
        werte.append(int(limit))
        return list(reversed(self._lesen(sql, tuple(werte))))

    def aktionen_zeitraum(self, von: str, bis: str, limit: int = 500) -> list:
        """Ausgeführte Aktionen zwischen zwei Zeitstempeln, in zeitlicher Reihenfolge."""
        zeilen = self._lesen(
            "SELECT * FROM aktionen WHERE zeit BETWEEN ? AND ? ORDER BY id DESC LIMIT ?",
            (von, bis, int(limit)))
        return list(reversed(zeilen))

    def aeusserungen_suchen(self, begriff: str, limit: int = 8) -> list:
        """Sucht in früheren Äußerungen des Nutzers."""
        begriff = (begriff or "").strip()
        if not begriff:
            return []
        return self._lesen(
            "SELECT * FROM verlauf WHERE rolle='user' AND text LIKE ? "
            "ORDER BY id DESC LIMIT ?", ("%%%s%%" % begriff, limit))

    # -- Übersicht ----------------------------------------------------------

    def statistik(self) -> dict:
        """Zählt, was im Gedächtnis liegt."""
        ergebnis = {}
        for tabelle in ("notizen", "kontakte", "kennzahlen", "aktionen", "verlauf"):
            try:
                zeilen = self._lesen("SELECT count(*) AS n FROM %s" % tabelle)
                ergebnis[tabelle] = zeilen[0]["n"] if zeilen else 0
            except sqlite3.Error:
                ergebnis[tabelle] = 0
        ergebnis["offene_punkte"] = len(self.punkte_offen())
        return ergebnis

    # -- Optionale Spiegelung ----------------------------------------------

    def _spiegeln(self, tabelle: str, daten: dict):
        """Spiegelt einen Datensatz nach Supabase - scheitert lautlos, nie blockierend."""
        if not (config.SUPABASE_URL and config.SUPABASE_KEY):
            return
        try:
            ziel = "%s/rest/v1/%s" % (config.SUPABASE_URL.rstrip("/"), tabelle)
            anfrage = urllib.request.Request(
                ziel, data=json.dumps(daten).encode("utf-8"), method="POST",
                headers={
                    "apikey": config.SUPABASE_KEY,
                    "Authorization": "Bearer %s" % config.SUPABASE_KEY,
                    "Content-Type": "application/json",
                    "Prefer": "return=minimal",
                })
            urllib.request.urlopen(anfrage, timeout=5).read()
        except (urllib.error.URLError, OSError, ValueError):
            pass
