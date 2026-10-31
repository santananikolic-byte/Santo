#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Startet einen abgeschotteten JARVIS-Server mit Ersatz-Claude und Ersatz-say für die Oberflächenprüfung (ui_pruefung.js).

Gibt als erste Zeile JSON aus: {"port": …, "token": …, "ordner": …}. Beendet sich bei SIGTERM sauber.
"""

import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from tests.hilfen import ERSATZ_CLAUDE, ERSATZ_SAY, ausfuehrbar, freier_port  # noqa: E402

PLAN = {"titel": "Prüfliste für neue Firmen", "schritte": [
    {"rolle": "dokumentation", "titel": "Prüfliste schreiben", "anweisung": "Schreibe eine kurze Checkliste zur Firmenprüfung.",
     "kriterium": "Die Datei notizen/pruefliste.md existiert und nennt das Handelsregister.", "datei": "notizen/pruefliste.md",
     "abhaengig_von": []}]}
SCHREIBEN = ('Ich lege die Liste an.\n<aktion werkzeug="datei_schreiben" pfad="notizen/pruefliste.md">'
             '# Prüfliste\n- Firma im Handelsregister prüfen\n- Rückruf nur über die offizielle Nummer</aktion>')
DREHBUCH = [
    {"system": "unabhängige Prüfer", "antwort": json.dumps({"erfuellt": True, "begruendung": "Datei vorhanden, Handelsregister genannt."})},
    {"system": "Planer von JARVIS", "antwort": json.dumps(PLAN)},
    {"stdin": "[SCHRITT 1 von 1", "antwort": SCHREIBEN},
    {"stdin": "Aktualisiere a.md", "max": 1, "antwort": 'Ich überschreibe die Datei, wenn du es erlaubst.\n<aktion werkzeug="datei_schreiben" pfad="a.md">neuer Inhalt</aktion>'},
    {"stdin": "Hallo Jarvis", "max": 1, "antwort": "Hallo! Ich bin JARVIS. Ich helfe dir, mehr Aufträge zu gewinnen, Firmen vor einem Auftrag zu prüfen und "
     "deine Aufgaben im Blick zu behalten. Womit fangen wir an?"},
]


def main():
    ordner = tempfile.mkdtemp(prefix="jarvis_ui_")
    port = freier_port()
    say = os.path.join(ordner, "say-ersatz")
    ausfuehrbar(say, ERSATZ_SAY % {"python": sys.executable})
    drehbuch = os.path.join(ordner, "drehbuch.json")
    with open(drehbuch, "w", encoding="utf-8") as f:
        json.dump(DREHBUCH, f, ensure_ascii=False)
    os.environ.update({
        "JARVIS_DATEN": os.path.join(ordner, "daten"), "JARVIS_PORT": str(port), "JARVIS_CLAUDE": ERSATZ_CLAUDE, "JARVIS_SAY": say,
        "JARVIS_WERKSTATT": os.path.join(ordner, "werkstatt"), "SAY_LOG": os.path.join(ordner, "say.log"), "FAKE_DREHBUCH": drehbuch,
        "FAKE_STAND": os.path.join(ordner, "stand.json"), "FAKE_PROTOKOLL": os.path.join(ordner, "aufrufe.jsonl"),
    })
    os.chmod(ERSATZ_CLAUDE, 0o755)  # noqa: S103 - Ersatzprogramm muss ausführbar sein
    os.makedirs(os.path.join(ordner, "werkstatt"), exist_ok=True)
    with open(os.path.join(ordner, "werkstatt", "a.md"), "w", encoding="utf-8") as f:
        f.write("alter Inhalt")

    from jarvis_core import auth
    from jarvis_core import konfig as konfig_modul
    from jarvis_core.protokoll import Protokoll
    from jarvis_core.server import JarvisServer

    konfig = konfig_modul.laden()
    log = Protokoll(konfig)
    token = auth.token_holen(konfig)
    print(json.dumps({"port": port, "token": token, "ordner": ordner}), flush=True)
    JarvisServer(konfig, log).starten(signale=True)
    log.schliessen()


if __name__ == "__main__":
    main()
