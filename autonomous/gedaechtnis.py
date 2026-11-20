# -*- coding: utf-8 -*-
"""Gedächtnis mit klarer Trennung: Fakt, Entscheidung, Hypothese, Vorschlag.

Agenten dürfen nur Hypothesen und Vorschläge anlegen. Fakten und Entscheidungen
legt ausschließlich der Eigentümer fest (oder ein Agent übernimmt einen Fakt nur
mit überprüfbarer Quelle – siehe ``fakt_mit_quelle``)."""

from .db import jetzt, neue_id

ARTEN = ("fakt", "entscheidung", "hypothese", "vorschlag")


class Gedaechtnis:
    def __init__(self, db, protokoll):
        self.db = db
        self.protokoll = protokoll

    def merken(self, art, thema, inhalt, quelle, autor, aufgabe_id=None):
        if art not in ARTEN:
            raise ValueError("Unbekannte Art: %s" % art)
        if not str(thema).strip() or not str(inhalt).strip():
            raise ValueError("Thema und Inhalt dürfen nicht leer sein.")
        if autor != "eigentuemer" and art == "entscheidung":
            raise PermissionError("Entscheidungen trifft nur der Eigentümer.")
        if autor != "eigentuemer" and art == "fakt" and not str(quelle).startswith(("http://", "https://", "datei:")):
            raise PermissionError("Agenten dürfen Fakten nur mit überprüfbarer Quelle speichern.")
        eid = neue_id("g_")
        self.db.ausfuehren("INSERT INTO gedaechtnis VALUES (?,?,?,?,?,?,?,?)",
                           (eid, jetzt(), art, str(thema)[:200], str(inhalt)[:20000], str(quelle)[:500],
                            autor, aufgabe_id))
        return eid

    def liste(self, art=None, thema=None, grenze=200):
        sql, p = "SELECT * FROM gedaechtnis WHERE 1=1", []
        if art:
            sql += " AND art=?"
            p.append(art)
        if thema:
            sql += " AND thema LIKE ?"
            p.append("%" + thema + "%")
        sql += " ORDER BY zeit DESC LIMIT ?"
        p.append(grenze)
        return self.db.alle(sql, p)


class Ziele:
    def __init__(self, db, protokoll):
        self.db = db
        self.protokoll = protokoll

    def anlegen(self, titel, beschreibung="", prioritaet=3, akteur="eigentuemer"):
        if akteur != "eigentuemer":
            raise PermissionError("Ziele legt nur der Eigentümer fest.")
        if not titel.strip():
            raise ValueError("Titel fehlt.")
        zid = neue_id("z_")
        z = jetzt()
        self.db.ausfuehren("INSERT INTO ziele VALUES (?,?,?,?,?,?,?)",
                           (zid, titel.strip()[:200], beschreibung[:2000], int(prioritaet), "aktiv", z, z))
        self.protokoll.audit("ziele", "Ziel angelegt", {"id": zid, "titel": titel})
        return zid

    def status_setzen(self, zid, status, akteur="eigentuemer"):
        if akteur != "eigentuemer":
            raise PermissionError("Ziele ändert nur der Eigentümer.")
        if status not in ("aktiv", "erreicht", "verworfen"):
            raise ValueError("Ungültiger Status.")
        if not self.db.ausfuehren("UPDATE ziele SET status=?, aktualisiert=? WHERE id=?", (status, jetzt(), zid)):
            raise KeyError("Ziel nicht gefunden.")

    def liste(self):
        return self.db.alle("SELECT * FROM ziele ORDER BY status='aktiv' DESC, prioritaet, erstellt")
