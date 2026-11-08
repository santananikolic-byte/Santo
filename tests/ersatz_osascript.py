#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Ersatz für ``osascript`` mit der Mail-App - nur für Tests. Es wird kein AppleScript ausgeführt.

Der Ersatz erkennt an der Kennzeile ("-- JARVIS:postfach" …), welches Skript gemeint ist, und spielt
die Mail-App aus einer JSON-Datei nach - so, wie die echte sich verhält, soweit wir es wissen:
mehrere Konten, Nummern gelten nur innerhalb eines Kontos, Reihenfolge nicht nach Datum.
Jeder Aufruf wird protokolliert (Skripttext und Argumente), damit Tests prüfen können, dass
Nutzertext nur als Argument übergeben wird.

    FAKE_MAIL            JSON-Zustand: {"nachrichten": [...], "ordner": [[konto, pfad], ...], "gesendet": [],
                         "entwuerfe": [], "fehler": null | "-1743" | "9100" | ..., "aendern_einmal": false}
    FAKE_MAIL_PROTOKOLL  Datei, in die jeder Aufruf als JSON-Zeile geschrieben wird

Eine Nachricht: {"konto": "Arbeit", "id": 1, "absender": "…", "an": ["…"], "betreff": "…",
"datum": "2026-11-08T09:00:00", "gelesen": false, "inhalt": "…", "ordner": "INBOX"}.
"""

import datetime
import json
import os
import sys

US, RS = "\x1f", "\x1e"
FEHLER = {
    "-1743": "execution error: Nicht berechtigt, Apple-Events an „Mail“ zu senden. (-1743)",  # deutscher Mac
    "-600": "execution error: Mail got an error: Application isn’t running. (-600)",
    "-1712": "execution error: Mail got an error: AppleEvent timed out. (-1712)",
    "9100": "execution error: kein Konto (9100)",
}


def _fehler(text, code=1):
    sys.stderr.write(text + "\n")
    sys.exit(code)


def main():
    args = sys.argv[1:]
    if len(args) < 2 or args[0] != "-e":
        _fehler("usage: osascript -e statement [argument ...]", 2)
    skript, argv = args[1], args[2:]
    pfad = os.environ.get("FAKE_MAIL")
    with open(pfad, "r", encoding="utf-8") as f:
        stand = json.load(f)
    protokoll = os.environ.get("FAKE_MAIL_PROTOKOLL")
    op = skript.splitlines()[0].replace("-- JARVIS:", "").strip() if skript.startswith("-- JARVIS:") else "?"
    if protokoll:
        with open(protokoll, "a", encoding="utf-8") as f:
            f.write(json.dumps({"op": op, "skript": skript, "argv": argv}, ensure_ascii=False) + "\n")
    if not argv or argv[0] != "JARVIS":
        _fehler("Testfehler: das feste erste Argument JARVIS fehlt", 3)
    werte = argv[1:]
    if stand.get("fehler"):
        _fehler(FEHLER.get(stand["fehler"], "execution error: %s" % stand["fehler"]))

    def posteingang(konto):
        if konto not in {m["konto"] for m in stand["nachrichten"]} | {k for k, _ in stand.get("ordner", [])}:
            _fehler("execution error: Mail got an error: Can’t get account \"%s\". (-1728)" % konto)
        return [m for m in stand["nachrichten"] if m["konto"] == konto and m.get("ordner", "INBOX") == "INBOX"]

    adressen = stand.get("adressen") or {"Arbeit": ["chef@firma.example"], "Gmail": ["chef@gmail.example"]}

    if op == "postfach":
        if stand.get("aendern_einmal"):
            stand["aendern_einmal"] = False
            with open(pfad, "w", encoding="utf-8") as f:
                json.dump(stand, f, ensure_ascii=False)
            _fehler("execution error: Posteingang hat sich geaendert (9001)")
        grenze, tage = int(werte[0]), int(werte[1])
        seit = datetime.datetime.now() - datetime.timedelta(days=tage)
        konten = []
        for m in stand["nachrichten"]:
            if m["konto"] not in konten:
                konten.append(m["konto"])
        zeilen = ["UEBERSPRUNGEN" + US + k for k in stand.get("ohne_posteingang", [])]
        for konto in konten:
            for m in posteingang(konto)[:grenze]:  # "messages 1 thru n": interne Reihenfolge, nicht nach Datum
                if datetime.datetime.strptime(m["datum"], "%Y-%m-%dT%H:%M:%S") > seit:
                    zeilen.append(US.join([konto, str(m["id"]), m["absender"], m["betreff"], m["datum"],
                                           "true" if m.get("gelesen") else "false"]))
        print(RS.join(zeilen))
    elif op == "lesen":
        konto, mid, hoechstens = werte[0], int(werte[1]), int(werte[2])
        m = next((x for x in posteingang(konto) if x["id"] == mid), None)
        if m is None:
            _fehler("execution error: nicht gefunden (9404)")
        print(US.join([m["absender"], ", ".join(m.get("an", [])), m["betreff"], m["datum"], m.get("inhalt", "")[:hoechstens]]))
    elif op == "koepfe":
        konto, ids = werte[0], werte[1:]
        zeilen = []
        for mid in ids:
            m = next((x for x in posteingang(konto) if x["id"] == int(mid)), None)
            zeilen.append(US.join([mid, m["absender"] if m else "", m["betreff"] if m else "(nicht im Posteingang gefunden)"]))
        print(RS.join(zeilen))
    elif op == "ordner":
        konten = ["KONTO" + US + k + US + ", ".join(a) for k, a in adressen.items()]
        print(RS.join(konten + ["%s%s%s" % (k, US, n) for k, n in stand.get("ordner", [])]))
    elif op == "nachricht":
        modus, betreff, inhalt, von, an = werte[0], werte[1], werte[2], werte[3], werte[4:]
        alle = [a for liste in adressen.values() for a in liste]
        if von and von not in alle:  # die echte Mail-App ignoriert unbekannte Absender still - das Skript merkt es und bricht ab
            _fehler("execution error: Absender passt nicht: %s (9410)" % alle[0])
        absender = von or alle[0]
        eintrag = {"an": an, "betreff": betreff, "inhalt": inhalt}
        if von:
            eintrag["von"] = von
        stand.setdefault("gesendet" if modus == "senden" else "entwuerfe", []).append(eintrag)
        print(("gesendet" if modus == "senden" else "entwurf") + US + absender)
    elif op == "verschieben":
        konto, ziel, ids = werte[0], werte[1], werte[2:]
        if [konto, ziel] not in stand.get("ordner", []):
            _fehler("execution error: Mail got an error: Can’t get mailbox \"%s\" of account \"%s\". (-1728)" % (ziel, konto))
        zeilen = []
        for mid in ids:
            m = next((x for x in posteingang(konto) if x["id"] == int(mid)), None)
            if m is None:
                zeilen.append(mid + US + "nicht im Posteingang")
            else:
                m["ordner"] = ziel
                zeilen.append(mid + US + "ok")
        print(RS.join(zeilen))
    else:
        _fehler("Testfehler: unbekanntes Skript %r" % op, 4)
    with open(pfad, "w", encoding="utf-8") as f:
        json.dump(stand, f, ensure_ascii=False)


if __name__ == "__main__":
    main()
