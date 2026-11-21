# -*- coding: utf-8 -*-
"""Kommandozeile:  python3 -m autonomous <befehl>

  start        Server und Agenten starten (Vordergrund; Strg+C beendet sauber)
  link         Startlink mit Zugangsschlüssel ausgeben
  status       Status des laufenden Systems abfragen
  sicherung    Sicherung jetzt erstellen
  sicherungen  vorhandene Sicherungen auflisten
  wiederherstellen DATEI   Sicherung zurückspielen (nur bei gestopptem System)
  export       Wichtigste Daten als JSON exportieren
  test         Alle automatischen Tests ausführen
"""

import json
import os
import signal
import sys
import threading
import urllib.request

from . import konfig


def _url():
    return "http://127.0.0.1:%d" % konfig.PORT


def main(argv=None):
    # Alles, was AUTONOMOUS anlegt (Datenbank, Sicherungen, Exporte, Protokolle, Produkte), ist nur für den
    # eigenen Benutzer lesbar – nicht für andere Konten auf demselben Rechner.
    os.umask(0o077)
    argv = list(sys.argv[1:] if argv is None else argv)
    befehl = argv[0] if argv else "start"

    if befehl == "start":
        from .kern import Kern
        from .orchestrator import Orchestrator
        from . import server
        pid_datei = os.path.join(konfig.datenordner(), "autonomous.pid")
        kern = Kern()
        orchestrator = Orchestrator(kern)
        orchestrator.starten()
        stopp = server.hintergrund(kern)
        httpd = server.starten(kern)
        with open(pid_datei, "w") as f:
            f.write(str(os.getpid()))
        server.zugangsschluessel()  # sicherstellen, dass der Schlüssel existiert – aber nie ins Protokoll schreiben
        print("AUTONOMOUS läuft auf %s" % _url())
        print("Öffnen: Startlink mit 'python3 -m autonomous link' anzeigen (enthält den geheimen Schlüssel)")
        print("Beenden: Strg+C oder AUTONOMOUS-stoppen.command")

        def beenden(*_):
            threading.Thread(target=httpd.shutdown, daemon=True).start()
        signal.signal(signal.SIGTERM, beenden)
        signal.signal(signal.SIGINT, beenden)
        try:
            httpd.serve_forever()
        finally:
            stopp.set()
            httpd.server_close()
            kern.schliessen()
            if os.path.exists(pid_datei):
                os.remove(pid_datei)
            print("AUTONOMOUS sauber beendet.")
        return 0

    if befehl == "link":
        from . import server
        print("%s/?k=%s" % (_url(), server.zugangsschluessel()))
        return 0

    if befehl == "status":
        try:
            with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(_url() + "/status", timeout=3) as a:
                print(json.dumps(json.loads(a.read()), ensure_ascii=False, indent=1))
                return 0
        except OSError:
            print("AUTONOMOUS läuft nicht.")
            return 1

    if befehl in ("sicherung", "export"):
        from .kern import Kern
        from . import sicherung
        kern = Kern()
        try:
            print(sicherung.sichern(kern) if befehl == "sicherung" else sicherung.exportieren(kern))
        finally:
            kern.schliessen()
        return 0

    if befehl == "sicherungen":
        from . import sicherung
        for s in sicherung.liste():
            print(s["datei"], s["groesse"])
        return 0

    if befehl == "wiederherstellen":
        from . import sicherung
        if len(argv) < 2:
            print("Bitte Dateinamen der Sicherung angeben (siehe: sicherungen).")
            return 2
        if os.path.exists(os.path.join(konfig.datenordner(), "autonomous.pid")):
            print("Bitte zuerst AUTONOMOUS stoppen.")
            return 2
        print("Wiederhergestellt nach:", sicherung.wiederherstellen(argv[1]))
        return 0

    if befehl == "test":
        import unittest
        suite = unittest.defaultTestLoader.discover(os.path.join(konfig.PAKET, "tests"),
                                                    top_level_dir=konfig.PROJEKT)
        ergebnis = unittest.TextTestRunner(verbosity=1).run(suite)
        return 0 if ergebnis.wasSuccessful() else 1

    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main())
