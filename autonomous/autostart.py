# -*- coding: utf-8 -*-
"""Dauerbetrieb auf dem Mac: LaunchAgent für AUTONOMOUS schreiben (nur die Datei – laden macht launchctl).

    python3 -m autonomous.autostart schreiben PYTHON INSTALLATIONSORDNER [PLIST_PFAD]

Der LaunchAgent (~/Library/LaunchAgents/de.autonomous.server.plist) startet AUTONOMOUS bei der Anmeldung am Mac,
startet es nach einem Absturz neu (nicht nach sauberem Beenden), arbeitet im Installationsordner und schreibt alle
Meldungen nach autonomous/daten/server.log – nur für den eigenen Benutzer lesbar (umask 077).
Erzeugt mit plistlib, damit die Datei immer gültig ist. Kein sudo, nur der eigene Benutzer.
"""

import os
import plistlib
import sys
import tempfile

LABEL = "de.autonomous.server"


def plist_pfad(home=None):
    return os.path.join(home or os.path.expanduser("~"), "Library", "LaunchAgents", LABEL + ".plist")


def plist_daten(python, ziel, port=None):
    python, ziel = str(python), str(ziel)
    if not os.path.isabs(python) or not os.path.isabs(ziel):
        raise ValueError("Python und Installationsordner bitte als absolute Pfade angeben.")
    if not (os.path.isfile(python) and os.access(python, os.X_OK)):
        raise ValueError("Python nicht gefunden oder nicht ausführbar: %s" % python)
    if not os.path.isfile(os.path.join(ziel, "autonomous", "__main__.py")):
        raise ValueError("Im Ordner %s liegt kein AUTONOMOUS (autonomous/__main__.py fehlt)." % ziel)
    umgebung = {"PYTHONUNBUFFERED": "1", "PYTHONIOENCODING": "utf-8"}
    if port is not None:
        try:
            port = int(port)
        except (TypeError, ValueError):
            raise ValueError("Port muss eine Zahl sein: %r" % (port,))
        if not 1 <= port <= 65535:
            raise ValueError("Port außerhalb von 1–65535: %d" % port)
        umgebung["AUTONOMOUS_PORT"] = str(port)
    log = os.path.join(ziel, "autonomous", "daten", "server.log")
    return {
        "Label": LABEL,
        "ProgramArguments": [python, "-m", "autonomous", "start"],
        "WorkingDirectory": ziel,
        "RunAtLoad": True,                       # bei der Anmeldung (und beim Laden) starten
        "KeepAlive": {"SuccessfulExit": False},  # nach einem Absturz neu starten, nach sauberem Beenden nicht
        "StandardOutPath": log,
        "StandardErrorPath": log,
        "Umask": 0o077,                          # alles, was entsteht, nur für den eigenen Benutzer
        "EnvironmentVariables": umgebung,
    }


def schreiben(pfad, python, ziel, port=None):
    """Schreibt die plist atomar (erst vollständig, dann umbenennen) und liest sie zur Kontrolle zurück."""
    daten = plist_daten(python, ziel, port)
    ordner = os.path.dirname(os.path.abspath(pfad))
    os.makedirs(ordner, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".autonomous-", suffix=".plist", dir=ordner)  # Modus 0600
    try:
        with os.fdopen(fd, "wb") as f:
            plistlib.dump(daten, f, fmt=plistlib.FMT_XML)
        with open(tmp, "rb") as f:
            if plistlib.load(f) != daten:
                raise ValueError("LaunchAgent-Datei ließ sich nicht fehlerfrei zurücklesen.")
        os.replace(tmp, pfad)
    except BaseException:
        if os.path.exists(tmp):
            os.remove(tmp)
        raise
    return daten


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if len(argv) not in (3, 4) or argv[0] != "schreiben":
        print(__doc__)
        return 2
    pfad = argv[3] if len(argv) == 4 else plist_pfad()
    try:
        schreiben(pfad, argv[1], argv[2], os.environ.get("AUTONOMOUS_PORT") or None)
    except (ValueError, OSError) as fehler:
        print("Autostart nicht eingerichtet: %s" % fehler, file=sys.stderr)
        return 1
    print(pfad)
    return 0


if __name__ == "__main__":
    sys.exit(main())
