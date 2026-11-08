#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Ersatz für macOS ``mdls`` (Spotlight-Metadaten) - nur für Tests.

Aufruf wie JARVIS ihn macht: mdls -raw -name kMDItemContentCreationDate DATEI1 DATEI2 …
Ausgabe wie das echte mdls mit -raw und mehreren Dateien: die Werte ohne Zeilenumbruch, durch NUL getrennt;
"(null)", wenn Spotlight kein Datum kennt.

    FAKE_MDLS       JSON {Dateiname: "2026-11-05 07:30:00 +0000" | null | "FEHLT"}
                    "FEHLT": wie eine Datei, die mdls nicht lesen kann - Meldung auf stderr, kein Wert (die Ausgabe
                    passt dann nicht mehr zur Zahl der Dateien)
    FAKE_MDLS_ENDE  1 = jeder Wert endet mit NUL (auch der letzte) - die zweite mögliche Form der Ausgabe
"""

import json
import os
import sys


def main():
    args = sys.argv[1:]
    if args[:3] != ["-raw", "-name", "kMDItemContentCreationDate"]:
        sys.stderr.write("Testfehler: unerwarteter Aufruf %r\n" % args)
        sys.exit(2)
    with open(os.environ["FAKE_MDLS"], encoding="utf-8") as f:
        karte = json.load(f)
    werte = []
    for pfad in args[3:]:
        wert = karte.get(os.path.basename(pfad))
        if wert == "FEHLT":
            sys.stderr.write("%s: could not find %s.\n" % (sys.argv[0], pfad))
            continue
        werte.append(wert or "(null)")
    if os.environ.get("FAKE_MDLS_ENDE") == "1":
        sys.stdout.write("".join(w + "\x00" for w in werte))
    else:
        sys.stdout.write("\x00".join(werte))


if __name__ == "__main__":
    main()
