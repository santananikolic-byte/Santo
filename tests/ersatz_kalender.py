#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Ersatz für ``osascript -l JavaScript`` mit der Kalender-App - nur für Tests. Es wird kein Skript ausgeführt.

Der Ersatz erkennt an der Kennzeile ("// JARVIS:termine" …), welches Skript gemeint ist, und spielt die Kalender-App
aus einer JSON-Datei nach. Serientermine stehen dort schon als einzelne Termine (so liefert sie EventKit). Jeder Aufruf
wird protokolliert (Skripttext und Argumente), damit Tests prüfen können, dass Nutzertext nur als Argument übergeben wird.

    FAKE_KALENDER            {"kalender": [{"name": "Arbeit", "schreibbar": true}], "standard": "Arbeit",
                              "termine": [{"titel", "beginn", "ende", "ganztag", "ort", "kalender"}],
                              "zugriff": "erlaubt" | "verweigert" | "offen", "speichern_scheitert": false}
    FAKE_KALENDER_PROTOKOLL  Datei, in die jeder Aufruf als JSON-Zeile geschrieben wird
"""

import datetime
import json
import os
import sys

ISO = "%Y-%m-%dT%H:%M:%S"


def ausgeben(daten):
    sys.stdout.write(json.dumps(daten, ensure_ascii=False) + "\n")
    sys.exit(0)


def main():
    args = sys.argv[1:]
    if args[:2] != ["-l", "JavaScript"] or len(args) < 4 or args[2] != "-e":
        sys.stderr.write("Testfehler: erwartet osascript -l JavaScript -e SKRIPT ...\n")
        sys.exit(2)
    skript, argv = args[3], args[4:]
    pfad = os.environ["FAKE_KALENDER"]
    with open(pfad, encoding="utf-8") as f:
        stand = json.load(f)
    erste = skript.splitlines()[0] if skript else ""
    op = erste.replace("// JARVIS:", "").strip() if erste.startswith("// JARVIS:") else "?"
    protokoll = os.environ.get("FAKE_KALENDER_PROTOKOLL")
    if protokoll:
        with open(protokoll, "a", encoding="utf-8") as f:
            f.write(json.dumps({"op": op, "skript": skript, "argv": argv}, ensure_ascii=False) + "\n")
    if not argv or argv[0] != "JARVIS":
        sys.stderr.write("Testfehler: das feste erste Argument JARVIS fehlt\n")
        sys.exit(3)
    werte = argv[1:]
    zugriff = stand.get("zugriff", "erlaubt")
    if zugriff != "erlaubt":
        ausgeben({"fehler": "zugriff_verweigert" if zugriff == "verweigert" else "zugriff_offen"})
    kalender = stand.get("kalender") or []

    if op == "termine":
        von, bis = (datetime.datetime.strptime(w, ISO) for w in werte[:2])
        treffer = [t for t in stand.get("termine", [])
                   if datetime.datetime.strptime(t["beginn"], ISO) < bis and datetime.datetime.strptime(t["ende"], ISO) > von]
        ausgeben({"termine": treffer, "kalender": kalender, "standard": stand.get("standard", "")})
    if op == "eintragen":
        titel, beginn, ende, ganztag, ort, notiz, name = werte[:7]
        ziel = next((k for k in kalender if k["name"] == (name or stand.get("standard"))), None)
        if ziel is None:
            ausgeben({"fehler": "kalender_unbekannt"})
        if not ziel["schreibbar"]:
            ausgeben({"fehler": "nur_lesen"})
        if stand.get("speichern_scheitert"):
            ausgeben({"fehler": "speichern"})
        stand.setdefault("termine", []).append({"titel": titel, "beginn": beginn, "ende": ende, "ganztag": ganztag == "1",
                                                "ort": ort, "notiz": notiz, "kalender": ziel["name"]})
        with open(pfad, "w", encoding="utf-8") as f:
            json.dump(stand, f, ensure_ascii=False)
        ausgeben({"ok": True, "kalender": ziel["name"]})
    sys.stderr.write("Testfehler: unbekanntes Skript %r\n" % erste)
    sys.exit(4)


if __name__ == "__main__":
    main()
