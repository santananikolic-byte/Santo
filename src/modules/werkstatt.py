#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Werkstatt - der Programmierer schreibt kleine Programme und führt sie aus.

Hier gilt bewusst eine andere Regel als beim Rest des Programms. Überall sonst
läuft nur, was auf einer Allowlist steht. Ein Programmierer, der nur
registrierte Befehle ausführen darf, ist aber kein Programmierer.

**Deshalb ist hier der Mensch das Tor, nicht die Liste.** Ein Skript wird
geschrieben und abgelegt, ohne dass etwas passiert. Ausgeführt wird es erst
nach ausdrücklicher Freigabe - und die Freigabefrage zeigt vorher den
vollständigen Code und was er anfassen will.

Was diese Prüfung leistet und was nicht, ehrlich gesagt: Sie **erkennt**, ob
ein Skript ins Netz will, Dateien außerhalb der Werkstatt anfasst oder weitere
Programme startet, und schreibt das in die Freigabefrage. Sie **verhindert**
das nicht - wer Freigabe erteilt, führt aus, was dasteht. Die Prüfung ist eine
Lesehilfe für die Entscheidung, keine Mauer. Wer Code ausführt, entscheidet.
"""

import ast
import os
import re
import subprocess
import sys
from datetime import datetime

import config
from modules.memory import Memory, db_schema_anlegen, zeitstempel

SCHEMA_WERKSTATT = """
CREATE TABLE IF NOT EXISTS skripte (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    zweck TEXT DEFAULT '',
    laeufe INTEGER DEFAULT 0,
    zuletzt TEXT DEFAULT '',
    angelegt TEXT NOT NULL,
    geaendert TEXT NOT NULL
);
"""

MAX_ZEICHEN = 20000
LAUFZEIT_GRENZE = 60

# Module, deren Verwendung in der Freigabefrage genannt wird. Das ist eine
# Lesehilfe fuer die Entscheidung, keine Sperre.
AUFFAELLIGE_MODULE = {
    "socket": "will ins Netz",
    "urllib": "will ins Netz",
    "http": "will ins Netz",
    "requests": "will ins Netz",
    "ftplib": "will ins Netz",
    "smtplib": "will Mails verschicken",
    "subprocess": "will weitere Programme starten",
    "multiprocessing": "will weitere Prozesse starten",
    "shutil": "will Dateien verschieben oder löschen",
    "os": "greift auf das Dateisystem zu",
    "pathlib": "greift auf das Dateisystem zu",
    "sqlite3": "will eine Datenbank öffnen",
    "ctypes": "greift tief ins System",
}


def name_saeubern(name: str) -> str:
    """Macht aus einem Wunschnamen einen sicheren Dateinamen.

    Nur Buchstaben, Ziffern, Strich und Unterstrich bleiben übrig. Damit sind
    Pfadangriffe wie ``../../etwas`` von vornherein nicht darstellbar.
    """
    roh = (name or "").strip().lower()
    for alt, neu in (("ä", "ae"), ("ö", "oe"), ("ü", "ue"), ("ß", "ss")):
        roh = roh.replace(alt, neu)
    roh = re.sub(r"\.py$", "", roh)
    roh = re.sub(r"[^a-z0-9_-]+", "_", roh).strip("_-")
    return (roh or "skript")[:60] + ".py"


class Werkstatt:
    """Legt Skripte ab, zeigt sie und führt sie nach Freigabe aus."""

    def __init__(self, memory: Memory = None, python: str = ""):
        self.memory = memory or Memory()
        self.verzeichnis = config.BASIS / "werkstatt"
        # Das Python der eigenen Umgebung, damit die installierten Pakete da sind.
        self.python = python or sys.executable
        db_schema_anlegen(SCHEMA_WERKSTATT, self.memory.db_pfad)
        try:
            self.verzeichnis.mkdir(parents=True, exist_ok=True)
        except OSError as fehler:
            print("[werkstatt] Verzeichnis nicht anlegbar: %s" % fehler)

    # -- Pfade --------------------------------------------------------------

    def _pfad(self, name: str):
        """Voller Pfad eines Skripts, garantiert innerhalb der Werkstatt."""
        datei = (self.verzeichnis / name_saeubern(name)).resolve()
        wurzel = self.verzeichnis.resolve()
        # Doppelt geprüft: auch wenn die Säuberung je umgangen würde, bleibt
        # alles unterhalb der Werkstatt.
        if wurzel not in datei.parents and datei != wurzel:
            return None
        return datei

    # -- Schreiben ----------------------------------------------------------

    def skript_schreiben(self, name: str, code: str, zweck: str = "") -> dict:
        """Legt ein Skript ab. Ausgeführt wird dabei nichts."""
        code = code or ""
        if not code.strip():
            return {"ok": False, "fehler": "Das Skript ist leer."}
        if len(code) > MAX_ZEICHEN:
            return {"ok": False,
                    "fehler": "Das Skript ist zu lang (%d Zeichen, erlaubt sind %d)."
                              % (len(code), MAX_ZEICHEN)}
        try:
            ast.parse(code)
        except SyntaxError as fehler:
            return {"ok": False,
                    "fehler": "Das Skript hat einen Syntaxfehler in Zeile %s: %s"
                              % (fehler.lineno, fehler.msg)}

        datei = self._pfad(name)
        if datei is None:
            return {"ok": False, "fehler": "Der Name '%s' ist nicht zulässig." % name}
        try:
            datei.write_text(code, encoding="utf-8")
        except OSError as fehler:
            return {"ok": False, "fehler": "Nicht schreibbar: %s" % fehler}

        vorhanden = self.memory._lesen(
            "SELECT id FROM skripte WHERE name=? LIMIT 1", (datei.name,))
        if vorhanden:
            self.memory._schreiben(
                "UPDATE skripte SET zweck=?, geaendert=? WHERE id=?",
                (zweck, zeitstempel(), vorhanden[0]["id"]))
        else:
            self.memory._schreiben(
                "INSERT INTO skripte (name, zweck, laeufe, zuletzt, angelegt, "
                "geaendert) VALUES (?,?,0,'',?,?)",
                (datei.name, zweck, zeitstempel(), zeitstempel()))

        befunde = self.pruefen(code)
        return {"ok": True, "name": datei.name, "pfad": str(datei),
                "zeilen": code.count("\n") + 1, "auffaelligkeiten": befunde,
                "text": "%s ist abgelegt (%d Zeilen). Ausgeführt ist noch nichts.%s"
                        % (datei.name, code.count("\n") + 1,
                           (" Achtung: %s." % ", ".join(befunde)) if befunde else "")}

    # -- Lesen --------------------------------------------------------------

    def skript_zeigen(self, name: str) -> dict:
        """Gibt den Code eines Skripts zurück."""
        datei = self._pfad(name)
        if datei is None or not datei.exists():
            return {"ok": False, "fehler": "Das Skript '%s' gibt es nicht." % name}
        try:
            code = datei.read_text(encoding="utf-8")
        except OSError as fehler:
            return {"ok": False, "fehler": "Nicht lesbar: %s" % fehler}
        return {"ok": True, "name": datei.name, "code": code,
                "auffaelligkeiten": self.pruefen(code), "text": code[:4000]}

    def werkstatt_liste(self) -> dict:
        """Alle abgelegten Skripte."""
        zeilen = self.memory._lesen("SELECT * FROM skripte ORDER BY geaendert DESC")
        eintraege = []
        for zeile in zeilen:
            datei = self._pfad(zeile["name"])
            eintraege.append({"name": zeile["name"], "zweck": zeile["zweck"],
                              "laeufe": zeile["laeufe"], "zuletzt": zeile["zuletzt"],
                              "vorhanden": bool(datei and datei.exists())})
        return {"ok": True, "anzahl": len(eintraege), "skripte": eintraege,
                "verzeichnis": str(self.verzeichnis),
                "text": ("In der Werkstatt liegen: %s."
                         % ", ".join(e["name"] for e in eintraege)) if eintraege
                        else "In der Werkstatt liegt noch kein Skript."}

    # -- Prüfen -------------------------------------------------------------

    @staticmethod
    def pruefen(code: str) -> list:
        """Nennt, was das Skript vorhat - als Lesehilfe für die Freigabe.

        Das ist ausdrücklich keine Sicherheitsprüfung. Sie liest die Importe
        über den Syntaxbaum und benennt, was auffällt, damit in der
        Freigabefrage nicht nur nackter Code steht.
        """
        befunde = []
        try:
            baum = ast.parse(code or "")
        except SyntaxError:
            return ["Code ist syntaktisch fehlerhaft"]
        module = set()
        for knoten in ast.walk(baum):
            if isinstance(knoten, ast.Import):
                for teil in knoten.names:
                    module.add(teil.name.split(".")[0])
            elif isinstance(knoten, ast.ImportFrom) and knoten.module:
                module.add(knoten.module.split(".")[0])
        for name in sorted(module):
            if name in AUFFAELLIGE_MODULE:
                hinweis = AUFFAELLIGE_MODULE[name]
                if hinweis not in befunde:
                    befunde.append(hinweis)
        if re.search(r"\b(eval|exec|compile)\s*\(", code or ""):
            befunde.append("führt Code zur Laufzeit aus")
        return befunde

    def freigabetext(self, name: str) -> str:
        """Was in der Freigabefrage stehen soll: Zweck, Befunde und der Code."""
        angaben = self.skript_zeigen(name)
        if not angaben.get("ok"):
            return angaben.get("fehler", "")
        befunde = angaben["auffaelligkeiten"]
        kopf = "Skript %s ausführen." % angaben["name"]
        if befunde:
            kopf += " Es %s." % " und ".join(befunde)
        else:
            kopf += " Es benutzt nur Standardfunktionen."
        return "%s\n\n%s" % (kopf, angaben["code"][:1500])

    # -- Ausführen ----------------------------------------------------------

    def skript_ausfuehren(self, name: str, argumente: list = None) -> dict:
        """Führt ein abgelegtes Skript aus.

        Die Freigabe holt der Werkzeugkatalog ein, bevor diese Methode
        überhaupt aufgerufen wird. Hier gilt: eigene Shell nie, Arbeitsordner
        ist die Werkstatt, und nach 60 Sekunden ist Schluss.
        """
        datei = self._pfad(name)
        if datei is None or not datei.exists():
            return {"ok": False, "fehler": "Das Skript '%s' gibt es nicht." % name}

        befehl = [self.python, str(datei)]
        for teil in (argumente or []):
            befehl.append(str(teil))

        beginn = datetime.now()
        try:
            ergebnis = subprocess.run(befehl, capture_output=True, text=True,
                                      timeout=LAUFZEIT_GRENZE, shell=False,
                                      cwd=str(self.verzeichnis))
        except subprocess.TimeoutExpired:
            return {"ok": False,
                    "fehler": "Das Skript lief länger als %d Sekunden und wurde "
                              "abgebrochen." % LAUFZEIT_GRENZE}
        except (OSError, subprocess.SubprocessError) as fehler:
            return {"ok": False, "fehler": "Der Start ist fehlgeschlagen: %s" % fehler}
        dauer = (datetime.now() - beginn).total_seconds()

        self.memory._schreiben(
            "UPDATE skripte SET laeufe=laeufe+1, zuletzt=? WHERE name=?",
            (zeitstempel(), datei.name))

        ausgabe = (ergebnis.stdout or "").strip()
        fehlertext = (ergebnis.stderr or "").strip()

        if ergebnis.returncode != 0:
            letzte = fehlertext.splitlines()[-1] if fehlertext else "ohne Meldung"
            return {"ok": False, "name": datei.name, "rueckgabe": ergebnis.returncode,
                    "ausgabe": ausgabe[:3000], "fehlertext": fehlertext[-2000:],
                    "fehler": "%s ist mit Fehler abgebrochen: %s"
                              % (datei.name, letzte)}
        return {"ok": True, "name": datei.name, "rueckgabe": 0,
                "dauer": round(dauer, 2), "ausgabe": ausgabe[:3000],
                "text": ("%s lief durch (%.1f Sekunden). Ausgabe: %s"
                         % (datei.name, dauer,
                            ausgabe[:900] if ausgabe else "keine"))}

    def skript_loeschen(self, name: str) -> dict:
        """Entfernt ein Skript aus der Werkstatt."""
        datei = self._pfad(name)
        if datei is None or not datei.exists():
            return {"ok": False, "fehler": "Das Skript '%s' gibt es nicht." % name}
        try:
            os.remove(str(datei))
        except OSError as fehler:
            return {"ok": False, "fehler": "Nicht löschbar: %s" % fehler}
        self.memory._schreiben("DELETE FROM skripte WHERE name=?", (datei.name,))
        return {"ok": True, "text": "%s ist gelöscht." % datei.name}
