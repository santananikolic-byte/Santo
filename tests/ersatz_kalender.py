#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Ersatz für ``osascript -l JavaScript jarvis_core/kalender.js JARVIS <befehl> …`` - nur für Tests. Es wird kein
Skript ausgeführt.

Der Ersatz liest den Befehl (termine, suchen, eintragen, details, aendern, loeschen) aus den Argumenten und spielt die
Kalender-App aus einer JSON-Datei nach - so, wie EventKit sich verhält: Serientermine als einzelne Termine mit derselben
Kennung, ein Termin wird über Kennung und Beginn gefunden. Jeder Aufruf wird protokolliert (Skripttext und Argumente),
damit Tests prüfen können, dass Nutzertext nur als Argument übergeben wird.

    FAKE_KALENDER            {"kalender": [{"name": "Arbeit", "schreibbar": true}], "standard": "Arbeit",
                              "termine": [{"titel", "beginn", "ende", "ganztag", "ort", "notiz", "kalender", "id"}],
                              "zugriff": "erlaubt" | "verweigert" | "offen" | "nur_hinzufuegen",
                              "speichern_scheitert": false, "loeschen_scheitert": false}
    FAKE_KALENDER_PROTOKOLL  Datei, in die jeder Aufruf als JSON-Zeile geschrieben wird
"""

import datetime
import json
import os
import sys

ISO = "%Y-%m-%dT%H:%M:%S"
SCHRITT = {"taeglich": datetime.timedelta(days=1), "woechentlich": datetime.timedelta(weeks=1)}


def ausgeben(daten):
    sys.stdout.write(json.dumps(daten, ensure_ascii=False) + "\n")
    sys.exit(0)


def zeit(text):
    return datetime.datetime.strptime(text, ISO)


def main():
    args = sys.argv[1:]
    if args[:2] != ["-l", "JavaScript"] or len(args) < 4 or not args[2].endswith("kalender.js") \
            or not os.path.isfile(args[2]):
        sys.stderr.write("Testfehler: erwartet osascript -l JavaScript .../kalender.js JARVIS BEFEHL ...\n")
        sys.exit(2)
    with open(args[2], encoding="utf-8") as f:
        skript = f.read()
    argv = args[3:]
    pfad = os.environ["FAKE_KALENDER"]
    with open(pfad, encoding="utf-8") as f:
        stand = json.load(f)
    op = argv[1] if len(argv) > 1 else "?"
    protokoll = os.environ.get("FAKE_KALENDER_PROTOKOLL")
    if protokoll:
        with open(protokoll, "a", encoding="utf-8") as f:
            f.write(json.dumps({"op": op, "skript": skript, "argv": argv}, ensure_ascii=False) + "\n")
    if not argv or argv[0] != "JARVIS":
        sys.stderr.write("Testfehler: das feste erste Argument JARVIS fehlt\n")
        sys.exit(3)
    werte = argv[2:]
    zugriff = stand.get("zugriff", "erlaubt")
    if zugriff != "erlaubt":
        ausgeben({"fehler": {"verweigert": "zugriff_verweigert", "offen": "zugriff_offen",
                             "nur_hinzufuegen": "nur_hinzufuegen"}[zugriff]})
    kalender = stand.get("kalender") or []
    termine = stand.setdefault("termine", [])
    for i, t in enumerate(termine):
        t.setdefault("id", "ID-%d" % i)
        t.setdefault("notiz", "")
        t.setdefault("serie", False)

    def speichern():
        with open(pfad, "w", encoding="utf-8") as f:
            json.dump(stand, f, ensure_ascii=False)

    def schreibbar(name):
        return next((k["schreibbar"] for k in kalender if k["name"] == name), False)

    def finde(kennung, beginn):
        return next((t for t in termine if t["id"] == kennung and t["beginn"] == beginn), None)

    def nach_name(name):
        gleich = [k for k in kalender if k["name"] == name]
        if len(gleich) > 1:
            ausgeben({"fehler": "kalender_mehrdeutig"})
        if not gleich:
            ausgeben({"fehler": "kalender_unbekannt"})
        if not gleich[0]["schreibbar"]:
            ausgeben({"fehler": "nur_lesen"})
        return gleich[0]

    if op in ("termine", "suchen"):
        von, bis = zeit(werte[0]), zeit(werte[1])
        treffer = [t for t in termine if zeit(t["beginn"]) < bis and zeit(t["ende"]) > von]
        if op == "suchen":
            wort = werte[2].lower()
            if len(wort) < 2:
                ausgeben({"fehler": "suchwort"})
            treffer = [t for t in treffer if wort in (t["titel"] + "\n" + t.get("ort", "") + "\n" + t["notiz"]).lower()]
        ausgeben({"termine": treffer, "kalender": kalender, "standard": stand.get("standard", "")})

    if op == "eintragen":
        titel, beginn, ende, ganztag, ort, notiz, name = werte[:7]
        extras = json.loads(werte[7]) if len(werte) > 7 and werte[7] else {}
        ziel = nach_name(name or stand.get("standard"))
        if ende <= beginn:
            ausgeben({"fehler": "datum"})
        if stand.get("speichern_scheitert"):
            ausgeben({"fehler": "speichern"})
        kennung = "NEU-%d" % (len(termine) + 1)
        neu = {"titel": titel, "beginn": beginn, "ende": ende, "ganztag": ganztag == "1", "ort": ort, "notiz": notiz,
               "kalender": ziel["name"], "id": kennung, "serie": bool(extras.get("wiederholen")),
               "erinnerungen": [extras["erinnerung"]] if "erinnerung" in extras else []}
        if extras.get("wiederholen"):
            neu["regel"] = {k: extras.get(k) for k in ("wiederholen", "intervall", "bis", "anzahl")}
            schritt = SCHRITT.get(extras["wiederholen"], datetime.timedelta(days=30)) * int(extras.get("intervall") or 1)
            start, dauer = zeit(beginn), zeit(ende) - zeit(beginn)
            grenze = zeit(extras["bis"]) if extras.get("bis") else None
            anzahl = int(extras.get("anzahl") or 60)
            n = 0
            while n < min(anzahl, 60) and (grenze is None or start <= grenze):
                termine.append(dict(neu, beginn=start.strftime(ISO), ende=(start + dauer).strftime(ISO)))
                start += schritt
                n += 1
        else:
            termine.append(neu)
        speichern()
        ausgeben({"ok": True, "kalender": ziel["name"], "id": kennung})

    if op == "details":
        t = finde(werte[0], werte[1])
        if t is None:
            ausgeben({"fehler": "nicht_gefunden"})
        ausgeben({"termin": dict(t, schreibbar=schreibbar(t["kalender"]), regel=t.get("regel"),
                                 erinnerungen=t.get("erinnerungen", []))})

    if op == "aendern":
        kennung, beginn, alle, aend = werte[0], werte[1], werte[2] == "1", json.loads(werte[3])
        t = finde(kennung, beginn)
        if t is None:
            ausgeben({"fehler": "nicht_gefunden"})
        if not schreibbar(t["kalender"]):
            ausgeben({"fehler": "nur_lesen"})
        if stand.get("speichern_scheitert"):
            ausgeben({"fehler": "speichern"})
        vorher = dict(t)
        betroffen = [x for x in termine if x["id"] == kennung and (x is t or (alle and x["beginn"] >= beginn))]
        verschiebung = zeit(aend["beginn"]) - zeit(t["beginn"]) if "beginn" in aend else None
        dauer = zeit(aend["ende"]) - zeit(aend["beginn"]) if "beginn" in aend else None
        for x in betroffen:
            for feld in ("titel", "ort", "notiz", "ganztag"):
                if feld in aend:
                    x[feld] = aend[feld]
            if "kalender" in aend:
                x["kalender"] = nach_name(aend["kalender"])["name"]
            if "erinnerung" in aend:
                x["erinnerungen"] = [] if aend["erinnerung"] < 0 else [aend["erinnerung"]]
            if verschiebung is not None:
                start = zeit(x["beginn"]) + verschiebung
                x["beginn"], x["ende"] = start.strftime(ISO), (start + dauer).strftime(ISO)
        speichern()
        ausgeben({"ok": True, "vorher": vorher, "nachher": t})

    if op == "loeschen":
        kennung, beginn, alle = werte[0], werte[1], werte[2] == "1"
        t = finde(kennung, beginn)
        if t is None:
            ausgeben({"fehler": "nicht_gefunden"})
        if not schreibbar(t["kalender"]):
            ausgeben({"fehler": "nur_lesen"})
        if stand.get("loeschen_scheitert"):
            ausgeben({"fehler": "loeschen"})
        stand["termine"] = [x for x in termine if not (x["id"] == kennung and (x is t or (alle and x["beginn"] >= beginn)))]
        speichern()
        ausgeben({"ok": True})

    ausgeben({"fehler": "aufruf"})


if __name__ == "__main__":
    main()
