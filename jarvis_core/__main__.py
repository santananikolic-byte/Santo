# -*- coding: utf-8 -*-
"""Befehle: python3 -m jarvis_core serve | status | stopp | logs [anzahl]

``serve`` läuft im Vordergrund. Für den Alltag startet und stoppt man über
``./jarvis.sh``.
"""

import json
import os
import signal
import subprocess
import sys
import time
import urllib.error
import urllib.request

from . import konfig as konfig_modul
from .protokoll import Protokoll, letzte_eintraege
from .server import JarvisServer, PidFehler, pid_lesen, prozess_laeuft


def _konfig():
    try:
        return konfig_modul.laden()
    except konfig_modul.KonfigFehler as fehler:
        print("Konfigurationsfehler: %s" % fehler, file=sys.stderr)
        sys.exit(2)


def _status_abfragen(k, timeout=1):
    """Status von JARVIS - None, wenn dort nichts oder ein fremdes Programm antwortet."""
    try:
        # Die Adresse ist immer http://127.0.0.1:<port> - die Konfiguration lässt nichts anderes zu.
        with urllib.request.urlopen(k.adresse + "/status", timeout=timeout) as antwort:  # noqa: S310
            daten = json.loads(antwort.read().decode("utf-8"))
    except (urllib.error.URLError, OSError, ValueError):
        return None
    if isinstance(daten, dict) and daten.get("name") == "JARVIS" and "pid" in daten:
        return daten
    return None


def _ist_jarvis(pid, k):
    """Gehört die Prozessnummer wirklich zu JARVIS? Nach einem Absturz kann macOS sie neu vergeben haben."""
    s = _status_abfragen(k)
    if s and s.get("pid") == pid:
        return True
    try:
        befehl = subprocess.run(["ps", "-p", str(pid), "-o", "command="], capture_output=True,
                                text=True, timeout=5).stdout
    except (OSError, subprocess.SubprocessError):
        return False
    return "jarvis_core" in befehl


def serve():
    k = _konfig()
    log = Protokoll(k)
    try:
        JarvisServer(k, log).starten()
    except PidFehler as fehler:
        print(str(fehler), file=sys.stderr)
        return 1
    except OSError as fehler:
        print("Der Server konnte nicht starten: %s" % fehler, file=sys.stderr)
        return 1
    finally:
        log.schliessen()
    return 0


def status():
    k = _konfig()
    s = _status_abfragen(k)
    if not s:
        pid = pid_lesen(k.pid_datei)
        if pid and prozess_laeuft(pid):
            print("JARVIS-Prozess %d läuft, antwortet aber nicht unter %s." % (pid, k.adresse))
        else:
            print("JARVIS läuft nicht.")
        return 1
    print("JARVIS läuft  –  %s" % s["adresse"])
    print("  seit         %s (%s Sekunden)" % (s["seit"], s["laufzeit_sekunden"]))
    print("  Anfragen     %s" % s["anfragen"])
    print("  Claude Code  %s" % s["provider"]["claude_code"])
    print("  Version      %s (Phase %s), Python %s, Prozess %s" % (s["version"], s["phase"], s["python"], s["pid"]))
    print("  Daten        %s" % s["daten_ordner"])
    return 0


def stopp():
    k = _konfig()
    pid = pid_lesen(k.pid_datei)
    if not pid or not prozess_laeuft(pid) or not _ist_jarvis(pid, k):
        print("JARVIS läuft nicht.")
        if pid:
            # Veraltete Datei nach einem Absturz - der Prozess dahinter ist nicht JARVIS.
            try:
                os.remove(k.pid_datei)
            except OSError:
                pass
        return 0
    os.kill(pid, signal.SIGTERM)
    for _ in range(100):
        if not prozess_laeuft(pid):
            print("JARVIS ist gestoppt.")
            return 0
        time.sleep(0.1)
    print("JARVIS (Prozess %d) reagiert nicht auf das Stoppsignal. Notfalls: kill -9 %d" % (pid, pid))
    return 1


def logs(anzahl=20):
    k = _konfig()
    eintraege = letzte_eintraege(k.log_datei, anzahl)
    if not eintraege:
        print("Noch keine Logs in %s." % k.log_datei)
        return 0
    for e in eintraege:
        rest = {x: y for x, y in e.items() if x not in ("zeit", "stufe", "ereignis")}
        zusatz = "  " + json.dumps(rest, ensure_ascii=False) if rest else ""
        print("%s  %-7s %s%s" % (e.get("zeit", "?"), e.get("stufe", "?"), e.get("ereignis", "?"), zusatz))
    return 0


def main(argumente):
    befehl = argumente[0] if argumente else "status"
    if befehl == "serve":
        return serve()
    if befehl == "status":
        return status()
    if befehl in ("stopp", "stop"):
        return stopp()
    if befehl == "logs":
        try:
            return logs(int(argumente[1]) if len(argumente) > 1 else 20)
        except ValueError:
            print("So: python3 -m jarvis_core logs 50", file=sys.stderr)
            return 2
    print("Befehle: serve | status | stopp | logs [anzahl]", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
