#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Baut ``jarvis-mac.zip``: JARVIS als Mac-Paket zum Doppelklicken (Aufbau wie die alte Vorlage jarvis-mac).

Aufruf (aus dem Projektordner)::

    python3 mac-paket/bauen.py [Zieldatei]      # Standard: dist/jarvis-mac.zip

Was hineinkommt, steht unten in ``DATEIEN`` - nichts sonst. Das Skript bricht ab, wenn eine
Datei aussieht, als enthielte sie einen Schlüssel, oder wenn eine Datenbank dabei wäre.
Die Startdateien bekommen Ausführungsrechte, damit der Doppelklick auf dem Mac sofort geht.
"""

import datetime
import os
import re
import subprocess
import sys
import zipfile

WURZEL = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PAKET = os.path.join(WURZEL, "mac-paket")
ORDNER_IM_ZIP = "jarvis-mac"

# (Quelle relativ zum Projektordner, Ziel im Paket)
DATEIEN = [
    ("mac-paket/ANLEITUNG.txt", "ANLEITUNG.txt"),
    ("mac-paket/README.md", "README.md"),
    ("mac-paket/JARVIS.command", "JARVIS.command"),
    ("mac-paket/JARVIS-BEENDEN.command", "JARVIS-BEENDEN.command"),
    ("mac-paket/EXTRAS.command", "EXTRAS.command"),
    ("mac-paket/RECHTE_SETZEN.command", "RECHTE_SETZEN.command"),
    ("mac-paket/config/LIES-MICH.txt", "config/LIES-MICH.txt"),
    ("jarvis.sh", "jarvis.sh"),
    ("Preisrechner.html", "Preisrechner.html"),
    ("BRAIN.md", "BRAIN.md"),
    ("docs/STATUS.md", "docs/STATUS.md"),
]
PROGRAMM = "jarvis_core"
AUSFUEHRBAR = (".command", ".sh")
NIE = (".pyc", ".pyo", ".db", ".db-wal", ".db-shm", ".env", ".DS_Store")
SCHLUESSEL = re.compile(r"(sk-ant-[A-Za-z0-9_\-]{20,}|ghp_[A-Za-z0-9]{30,}|xox[bp]-[A-Za-z0-9\-]{20,})")
BOM = b"\xef\xbb\xbf"  # damit TextEdit die .txt-Dateien sicher als UTF-8 (mit Umlauten) liest


class BauFehler(Exception):
    pass


def _programmdateien():
    paare = []
    for ordner, unterordner, dateien in os.walk(os.path.join(WURZEL, PROGRAMM)):
        unterordner[:] = sorted(d for d in unterordner if d != "__pycache__" and not d.startswith("."))
        for name in sorted(dateien):
            if name.startswith(".") or name.endswith(NIE):
                continue
            quelle = os.path.relpath(os.path.join(ordner, name), WURZEL)
            paare.append((quelle, quelle))
    return paare


def _stand():
    try:
        commit = subprocess.run(["git", "-C", WURZEL, "rev-parse", "--short", "HEAD"], capture_output=True,  # noqa: S603, S607 - feste Argumente, nur lesen
                                text=True, timeout=10).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        commit = ""
    sys.path.insert(0, WURZEL)
    from jarvis_core import VERSION
    return VERSION, commit


def _pruefen(ziel, daten):
    if ziel.endswith(NIE):
        raise BauFehler("%s gehört nicht ins Paket." % ziel)
    if SCHLUESSEL.search(daten.decode("utf-8", "ignore")):
        raise BauFehler("%s sieht aus, als enthielte es einen Schlüssel - abgebrochen." % ziel)


def _eintrag(zip_datei, ziel, daten, ausfuehrbar):
    info = zipfile.ZipInfo("%s/%s" % (ORDNER_IM_ZIP, ziel), date_time=datetime.datetime.now().timetuple()[:6])
    info.create_system = 3  # Unix: damit die Rechte beim Entpacken auf dem Mac erhalten bleiben
    info.external_attr = ((0o100755 if ausfuehrbar else 0o100644) & 0xFFFF) << 16
    info.compress_type = zipfile.ZIP_DEFLATED
    zip_datei.writestr(info, daten)


def bauen(ziel_datei):
    version, commit = _stand()
    eintraege = []
    for quelle, ziel in DATEIEN + _programmdateien():
        pfad = os.path.join(WURZEL, quelle)
        if not os.path.isfile(pfad):
            raise BauFehler("Fehlt: %s" % quelle)
        with open(pfad, "rb") as f:
            daten = f.read()
        _pruefen(ziel, daten)
        if ziel.endswith(".txt") and not daten.startswith(BOM):
            daten = BOM + daten
        eintraege.append((ziel, daten, ziel.endswith(AUSFUEHRBAR)))
    stand = ("JARVIS %s\nGebaut am %s%s\n" % (version, datetime.date.today().strftime("%d.%m.%Y"),
                                               " (Stand %s)" % commit if commit else "")).encode("utf-8")
    eintraege.append(("VERSION.txt", BOM + stand, False))

    os.makedirs(os.path.dirname(os.path.abspath(ziel_datei)), exist_ok=True)
    zwischen = ziel_datei + ".neu"
    with zipfile.ZipFile(zwischen, "w") as z:
        for ziel, daten, ausfuehrbar in sorted(eintraege):
            _eintrag(z, ziel, daten, ausfuehrbar)
    os.replace(zwischen, ziel_datei)
    return {"datei": ziel_datei, "dateien": len(eintraege), "version": version, "commit": commit,
            "groesse_kb": round(os.path.getsize(ziel_datei) / 1024)}


def main(argumente):
    ziel = argumente[0] if argumente else os.path.join(WURZEL, "dist", "jarvis-mac.zip")
    try:
        ergebnis = bauen(ziel)
    except BauFehler as fehler:
        print("Nicht gebaut: %s" % fehler)
        return 1
    print("Gebaut: %(datei)s (%(dateien)d Dateien, %(groesse_kb)d KB, JARVIS %(version)s %(commit)s)" % ergebnis)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
