# -*- coding: utf-8 -*-
"""Tabelle - eine eigene Tabelle für Erweiterungen und Betriebsdaten, mit sicheren Grundfunktionen.

    AUFGABEN = Tabelle("erw_beispiel", (("titel", "TEXT NOT NULL"), ("status", "TEXT NOT NULL DEFAULT 'offen'"),
                                        ("daten", "TEXT"), ("erstellt", "TEXT"), ("geaendert", "TEXT")),
                       json=("daten",), indizes=(("status",),))
    nr = AUFGABEN.anlegen(sp, titel="Angebot prüfen", daten={"quelle": "chat"})
    AUFGABEN.liste(sp, wo="status=?", werte=("offen",))

* Jede Tabelle hat eine Spalte ``id`` (fortlaufend). ``erstellt``/``geaendert`` (falls vorhanden) setzt sie selbst (UTC).
* ``json``: Spalten, die Listen und Objekte speichern (als JSON-Text, beim Lesen wieder Python-Daten).
* Alles läuft über ``speicher.sql_lesen``/``sql_schreiben`` - die nur Tabellen ``erw_*``/``betrieb_*`` erlauben.
* SQL-Texte entstehen nur aus geprüften Namen (Tabelle, Spalten, Ordnung - siehe oben); Werte gehen immer als
  Platzhalter ``?`` an SQLite (deshalb die noqa-Vermerke S608).
* WICHTIG: ``wo`` ist ein SQL-Baustein aus dem eigenen Code. Nie Text vom Nutzer, vom Modell oder aus dem Internet
  hineinsetzen - Werte immer als ``werte`` (Platzhalter ``?``) übergeben.
"""

import json
import re

from . import zeit

NAME = re.compile(r"^(erw|betrieb)_[a-z0-9_]{1,60}$")
SPALTE = re.compile(r"^[a-z][a-z0-9_]{0,40}$")
TYP = re.compile(r"^(TEXT|INTEGER|REAL)( NOT NULL)?( DEFAULT (-?\d+(\.\d+)?|'[^']{0,40}'))?( UNIQUE)?$")
ORDNUNG = re.compile(r"^[a-z][a-z0-9_]{0,40}( (ASC|DESC))?(, ?[a-z][a-z0-9_]{0,40}( (ASC|DESC))?){0,3}$", re.IGNORECASE)
RESERVIERT = ("id", "order", "group", "select", "where", "from", "table", "index", "values", "default", "check")


class TabellenFehler(ValueError):
    """Falsch aufgebaute Tabelle oder falscher Aufruf - ein Programmierfehler, keine Nutzereingabe."""


class Tabelle:
    def __init__(self, name, spalten, json=(), indizes=()):  # noqa: A002 - "json" ist hier der Name der Option
        if not NAME.match(name or ""):
            raise TabellenFehler("Tabellenname %r: erw_… oder betrieb_…, nur a-z, 0-9 und _." % name)
        self.name = name
        self.spalten = tuple((str(s), str(t)) for s, t in spalten)
        self.namen = tuple(s for s, _ in self.spalten)
        if not self.namen or len(set(self.namen)) != len(self.namen):
            raise TabellenFehler("Tabelle %s: mindestens eine Spalte, keine doppelt." % name)
        for spalte, typ in self.spalten:
            if not SPALTE.match(spalte) or spalte in RESERVIERT:
                raise TabellenFehler("Tabelle %s: ungültiger Spaltenname %r." % (name, spalte))
            if not TYP.match(typ):
                raise TabellenFehler("Tabelle %s, Spalte %s: Typ %r nicht erlaubt (TEXT, INTEGER, REAL, optional "
                                     "NOT NULL, DEFAULT, UNIQUE)." % (name, spalte, typ))
        self.json = frozenset(json)
        if not self.json <= set(self.namen):
            raise TabellenFehler("Tabelle %s: json nennt Spalten, die es nicht gibt." % name)
        self.indizes = tuple(tuple(i) for i in indizes)
        for index in self.indizes:
            if not index or not set(index) <= set(self.namen):
                raise TabellenFehler("Tabelle %s: Index über unbekannte Spalten %r." % (name, index))

    def sql(self):
        """CREATE TABLE/INDEX IF NOT EXISTS - Namen und Typen sind oben geprüft."""
        teile = ["id INTEGER PRIMARY KEY AUTOINCREMENT"] + ["%s %s" % (s, t) for s, t in self.spalten]
        befehle = ["CREATE TABLE IF NOT EXISTS %s (%s);" % (self.name, ", ".join(teile))]
        for nr, index in enumerate(self.indizes, 1):
            befehle.append("CREATE INDEX IF NOT EXISTS %s_i%d ON %s (%s);" % (self.name, nr, self.name, ", ".join(index)))
        return "\n".join(befehle)

    # ------------------------------------------------------------ intern ---

    def _kodieren(self, felder):
        unbekannt = set(felder) - set(self.namen)
        if unbekannt:
            raise TabellenFehler("Tabelle %s kennt keine Spalte %s." % (self.name, ", ".join(sorted(unbekannt))))
        werte = {}
        for spalte, wert in felder.items():
            if spalte in self.json and wert is not None:
                wert = json.dumps(wert, ensure_ascii=False)
            werte[spalte] = wert
        return werte

    def _dekodieren(self, zeile):
        for spalte in self.json:
            wert = zeile.get(spalte)
            if isinstance(wert, str):
                try:
                    zeile[spalte] = json.loads(wert)
                except ValueError:
                    zeile[spalte] = None
        return zeile

    @staticmethod
    def _wo(wo):
        return " WHERE %s" % wo if wo else ""

    # -------------------------------------------------------- öffentlich ---

    def anlegen(self, sp, **felder):
        """Neue Zeile. Gibt die id zurück."""
        jetzt = zeit.jetzt()
        for spalte in ("erstellt", "geaendert"):
            if spalte in self.namen:
                felder.setdefault(spalte, jetzt)
        werte = self._kodieren(felder)
        if not werte:
            return sp.sql_schreiben("INSERT INTO %s DEFAULT VALUES" % self.name)[0]
        sql = "INSERT INTO %s (%s) VALUES (%s)" % (self.name, ", ".join(werte), ", ".join("?" * len(werte)))  # noqa: S608
        return sp.sql_schreiben(sql, tuple(werte.values()))[0]

    def holen(self, sp, zeile_id):
        zeilen = sp.sql_lesen("SELECT * FROM %s WHERE id=?" % self.name, (zeile_id,))  # noqa: S608
        return self._dekodieren(zeilen[0]) if zeilen else None

    def liste(self, sp, wo="", werte=(), ordnung="id DESC", limit=200):
        if not ORDNUNG.match(ordnung or ""):
            raise TabellenFehler("ordnung %r: nur Spaltennamen mit ASC/DESC." % ordnung)
        sql = "SELECT * FROM %s%s ORDER BY %s LIMIT ?" % (self.name, self._wo(wo), ordnung)  # noqa: S608
        return [self._dekodieren(z) for z in sp.sql_lesen(sql, tuple(werte) + (max(1, int(limit)),))]

    def erste(self, sp, wo="", werte=(), ordnung="id DESC"):
        treffer = self.liste(sp, wo, werte, ordnung, limit=1)
        return treffer[0] if treffer else None

    def setzen(self, sp, zeile_id, **felder):
        """Ändert Felder einer Zeile. Gibt True zurück, wenn es die Zeile gab."""
        if not felder:
            return False
        if "geaendert" in self.namen:
            felder.setdefault("geaendert", zeit.jetzt())
        werte = self._kodieren(felder)
        sql = "UPDATE %s SET %s WHERE id=?" % (self.name, ", ".join("%s=?" % s for s in werte))  # noqa: S608
        return sp.sql_schreiben(sql, tuple(werte.values()) + (zeile_id,))[1] > 0

    def loeschen(self, sp, zeile_id):
        return sp.sql_schreiben("DELETE FROM %s WHERE id=?" % self.name, (zeile_id,))[1] > 0  # noqa: S608

    def zaehlen(self, sp, wo="", werte=()):
        return sp.sql_lesen("SELECT COUNT(*) AS n FROM %s%s" % (self.name, self._wo(wo)), tuple(werte))[0]["n"]  # noqa: S608

    def summe(self, sp, spalte, wo="", werte=()):
        """Summe einer Zahlenspalte (0, wenn nichts passt)."""
        if spalte not in self.namen:
            raise TabellenFehler("Tabelle %s kennt keine Spalte %s." % (self.name, spalte))
        zeile = sp.sql_lesen("SELECT COALESCE(SUM(%s), 0) AS s FROM %s%s" % (spalte, self.name, self._wo(wo)),  # noqa: S608
                             tuple(werte))[0]
        return zeile["s"]
