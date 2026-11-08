#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Ersatz für macOS ``sips`` (Bilder umwandeln) - nur für Tests.

Erwartete Aufrufe:
    sips -g pixelWidth -g pixelHeight QUELLE                         (Maße; FAKE_SIPS_MASSE="BxH", Standard 4032x3024)
    sips -s format jpeg -s formatOptions 82 [-Z 1600] QUELLE --out ZIEL
Schreibt eine winzige JPEG-Datei nach ZIEL (mit dem Quellnamen darin, damit Tests sie wiedererkennen, und ob
verkleinert wurde). Hat die Quelle EXIF-Daten (APP1), übernimmt die Ausgabe sie - wie das echte sips, das GPS behält.
FAKE_SIPS_FEHLER=1 lässt die Umwandlung scheitern.
"""

import os
import sys


def main():
    args = sys.argv[1:]
    if os.environ.get("FAKE_SIPS_FEHLER") == "1":
        sys.stderr.write("Error: Unable to render source image\n")
        sys.exit(1)
    if args[:4] == ["-g", "pixelWidth", "-g", "pixelHeight"] and len(args) == 5:
        breite, hoehe = (os.environ.get("FAKE_SIPS_MASSE") or "4032x3024").split("x")
        print("%s\n  pixelWidth: %s\n  pixelHeight: %s" % (args[4], breite, hoehe))
        return
    if args[:6] != ["-s", "format", "jpeg", "-s", "formatOptions", "82"] or "--out" not in args:
        sys.stderr.write("Testfehler: unerwarteter Aufruf %r\n" % args)
        sys.exit(2)
    rest = args[6:]
    verkleinert = rest[:2] == ["-Z", "1600"]
    quelle, ziel = rest[2 if verkleinert else 0], args[args.index("--out") + 1]
    with open(quelle, "rb") as f:
        daten = f.read()
    exif = b""
    if daten[:4] == b"\xff\xd8\xff\xe0":  # JFIF überspringen, dann EXIF übernehmen
        weiter = 4 + int.from_bytes(daten[4:6], "big")
        if daten[weiter:weiter + 2] == b"\xff\xe1":
            exif = daten[weiter:weiter + 2 + int.from_bytes(daten[weiter + 2:weiter + 4], "big")]
    kommentar = b"UMGEWANDELT:" + os.path.basename(quelle).encode("utf-8") + (
        b":verkleinert" if verkleinert else b":originalgroesse")
    with open(ziel, "wb") as f:  # Kommentar-Block (FF FE) mit Länge, wie in echten JPEGs
        f.write(b"\xff\xd8" + exif + b"\xff\xfe" + (len(kommentar) + 2).to_bytes(2, "big") + kommentar + b"\xff\xd9")


if __name__ == "__main__":
    main()
