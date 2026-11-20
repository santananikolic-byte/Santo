# -*- coding: utf-8 -*-
"""Sicherung, Wiederherstellung und Export (Abschnitte 9 und 11)."""

import datetime
import json
import os
import shutil
import sqlite3

from . import konfig

EXPORT_TABELLEN = ("ziele", "gedaechtnis", "aufgaben", "freigaben", "wallet_buchungen", "real_buchungen",
                   "forderungen", "budgets", "kontakte", "angebote", "produkte", "agenten_rollen")


def _stempel():
    return datetime.datetime.now().strftime("%Y%m%d-%H%M%S-%f")


def sichern(kern, grund="manuell"):
    ordner = konfig.unterordner("sicherungen")
    ziel = os.path.join(ordner, "autonomous-%s.db" % _stempel())
    kern.db.sichern_nach(ziel)
    if not pruefen(ziel):
        os.remove(ziel)
        raise RuntimeError("Sicherung ist nicht lesbar – verworfen.")
    _aufraeumen(ordner, kern.einstellungen.hole("sicherung_behalten"))
    kern.protokoll.audit("sicherung", "Sicherung erstellt", {"datei": os.path.basename(ziel), "grund": grund})
    return ziel


def _aufraeumen(ordner, behalten):
    dateien = sorted(f for f in os.listdir(ordner) if f.startswith("autonomous-") and f.endswith(".db"))
    for alt in dateien[:-behalten]:
        os.remove(os.path.join(ordner, alt))


def liste():
    ordner = konfig.unterordner("sicherungen")
    return [{"datei": f, "groesse": os.path.getsize(os.path.join(ordner, f))}
            for f in sorted((f for f in os.listdir(ordner) if f.endswith(".db")), reverse=True)]


def pruefen(pfad):
    try:
        con = sqlite3.connect("file:%s?mode=ro" % pfad, uri=True)
        try:
            ok = con.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
            con.execute("SELECT COUNT(*) FROM aufgaben").fetchone()
            return ok
        finally:
            con.close()
    except sqlite3.Error:
        return False


def wiederherstellen(dateiname):
    """Nur bei gestopptem System aufrufen (Kommandozeile). Sichert vorher den aktuellen Stand."""
    ordner = konfig.unterordner("sicherungen")
    name = os.path.basename(dateiname)
    quelle = os.path.join(ordner, name)
    if not os.path.isfile(quelle) or not pruefen(quelle):
        raise ValueError("Sicherung fehlt oder ist beschädigt: %s" % name)
    db = konfig.db_pfad()
    if os.path.exists(db):
        shutil.copy2(db, os.path.join(ordner, "vor-wiederherstellung-%s.db" % _stempel()))
    for rest in (db + "-wal", db + "-shm"):
        if os.path.exists(rest):
            os.remove(rest)
    shutil.copy2(quelle, db)
    return db


def exportieren(kern):
    ordner = konfig.unterordner("export")
    daten = {"exportiert": datetime.datetime.now().astimezone().isoformat(timespec="seconds"),
             "hinweis": "wallet_buchungen = SIMULATION; real_buchungen = REALE Finanzen"}
    for t in EXPORT_TABELLEN:
        daten[t] = kern.db.alle("SELECT * FROM %s" % t)
    ziel = os.path.join(ordner, "autonomous-export-%s.json" % _stempel())
    with open(ziel, "w", encoding="utf-8") as f:
        json.dump(daten, f, ensure_ascii=False, indent=1, default=str)
    kern.protokoll.audit("sicherung", "Export erstellt", {"datei": os.path.basename(ziel)})
    return ziel
