#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""PDF ohne Zusatzprogramme - für Rechnungen, Angebote und Mahnungen.

Auf dem alten iMac soll nichts nachinstalliert werden müssen. Deshalb schreibt
dieses Modul PDF-Dateien selbst: eine A4-Seite, die Schriften Helvetica und
Helvetica-Bold, die jeder PDF-Betrachter eingebaut hat, Text, Linien und
graue Flächen. Mehr braucht ein Geschäftsbrief nicht.

Die Schrift steht in der Windows-Kodierung (WinAnsi). Darin gibt es Umlaute,
ß und das Euro-Zeichen. Zeichen außerhalb werden zu einem Fragezeichen, statt
die Datei zu zerbrechen.

Koordinaten zählen hier **von oben links** in Punkt (1 Punkt = 1/72 Zoll),
weil man Briefe von oben nach unten setzt. Ins PDF-System (unten links) wird
erst beim Schreiben umgerechnet.
"""

import unicodedata
import zlib
from datetime import datetime

PDF_SEITE_BREITE = 595.28
PDF_SEITE_HOEHE = 841.89

# Zeichenbreiten in Tausendstel der Schriftgröße, für die Zeichen 32 bis 255
# in WinAnsi - aus den Adobe-Metrikdateien (AFM) der beiden Schriften.
HELVETICA_BREITEN = (
    278, 278, 355, 556, 556, 889, 667, 191, 333, 333, 389, 584, 278, 333, 278, 278,
    556, 556, 556, 556, 556, 556, 556, 556, 556, 556, 278, 278, 584, 584, 584, 556,
    1015, 667, 667, 722, 722, 667, 611, 778, 722, 278, 500, 667, 556, 833, 722, 778,
    667, 778, 722, 667, 611, 722, 667, 944, 667, 667, 611, 278, 278, 278, 469, 556,
    333, 556, 556, 500, 556, 556, 278, 556, 556, 222, 222, 500, 222, 833, 556, 556,
    556, 556, 333, 500, 278, 556, 500, 722, 500, 500, 500, 334, 260, 334, 584, 0,
    556, 0, 222, 556, 333, 1000, 556, 556, 333, 1000, 667, 333, 1000, 0, 611, 0,
    0, 222, 222, 333, 333, 350, 556, 1000, 333, 1000, 500, 333, 944, 0, 500, 667,
    278, 333, 556, 556, 556, 556, 260, 556, 333, 737, 370, 556, 584, 333, 737, 333,
    400, 584, 333, 333, 333, 556, 537, 278, 333, 333, 365, 556, 834, 834, 834, 611,
    667, 667, 667, 667, 667, 667, 1000, 722, 667, 667, 667, 667, 278, 278, 278, 278,
    722, 722, 778, 778, 778, 778, 778, 584, 778, 722, 722, 722, 722, 667, 667, 611,
    556, 556, 556, 556, 556, 556, 889, 500, 556, 556, 556, 556, 278, 278, 278, 278,
    556, 556, 556, 556, 556, 556, 556, 584, 611, 556, 556, 556, 556, 500, 556, 500,
)
HELVETICA_FETT_BREITEN = (
    278, 333, 474, 556, 556, 889, 722, 238, 333, 333, 389, 584, 278, 333, 278, 278,
    556, 556, 556, 556, 556, 556, 556, 556, 556, 556, 333, 333, 584, 584, 584, 611,
    975, 722, 722, 722, 722, 667, 611, 778, 722, 278, 556, 722, 611, 833, 722, 778,
    667, 778, 722, 667, 611, 722, 667, 944, 667, 667, 611, 333, 278, 333, 584, 556,
    333, 556, 611, 556, 611, 556, 333, 611, 611, 278, 278, 556, 278, 889, 611, 611,
    611, 611, 389, 556, 333, 611, 556, 778, 556, 556, 500, 389, 280, 389, 584, 0,
    556, 0, 278, 556, 500, 1000, 556, 556, 333, 1000, 667, 333, 1000, 0, 611, 0,
    0, 278, 278, 500, 500, 350, 556, 1000, 333, 1000, 556, 333, 944, 0, 500, 667,
    278, 333, 556, 556, 556, 556, 280, 556, 333, 737, 370, 556, 584, 333, 737, 333,
    400, 584, 333, 333, 333, 611, 556, 278, 333, 333, 365, 556, 834, 834, 834, 611,
    722, 722, 722, 722, 722, 722, 1000, 722, 667, 667, 667, 667, 278, 278, 278, 278,
    722, 722, 778, 778, 778, 778, 778, 584, 778, 722, 722, 722, 722, 667, 667, 611,
    556, 556, 556, 556, 556, 556, 889, 556, 556, 556, 556, 556, 278, 278, 278, 278,
    611, 611, 611, 611, 611, 611, 611, 584, 611, 611, 611, 611, 611, 556, 611, 556,
)

# Häufige Zeichen ohne Platz in WinAnsi - lieber ein ähnliches als ein "?".
PDF_ERSATZZEICHEN = {" ": " ", " ": " ", "‑": "-", "−": "-",
                     "→": "->", "≤": "<=", "≥": ">=", "\t": "    ",
                     "đ": "d", "Đ": "D", "ł": "l", "Ł": "L", "ı": "i"}


def _pdf_zeichen(zeichen: str) -> str:
    """Ein Zeichen, das WinAnsi nicht kennt, ohne Akzent: ć -> c, Č -> C."""
    if zeichen in PDF_ERSATZZEICHEN:
        return PDF_ERSATZZEICHEN[zeichen]
    try:
        zeichen.encode("cp1252")
        return zeichen
    except UnicodeEncodeError:
        pass
    grund = "".join(z for z in unicodedata.normalize("NFKD", zeichen)
                    if not unicodedata.combining(z))
    try:
        grund.encode("cp1252")
        return grund or "?"
    except UnicodeEncodeError:
        return "?"


def pdf_kodieren(text) -> bytes:
    """Text in WinAnsi - unbekannte Zeichen werden ersetzt, nie zu einem Absturz."""
    text = "".join(_pdf_zeichen(z) for z in str(text or ""))
    text = text.replace("\r", "").replace("\n", " ")
    return text.encode("cp1252", errors="replace")


def pdf_textbreite(text, groesse: float, fett: bool = False) -> float:
    """Wie breit der Text in Punkt ist."""
    tabelle = HELVETICA_FETT_BREITEN if fett else HELVETICA_BREITEN
    summe = 0
    for byte in pdf_kodieren(text):
        summe += tabelle[byte - 32] if byte >= 32 else 0
    return summe * groesse / 1000.0


def pdf_umbrechen(text, breite: float, groesse: float, fett: bool = False) -> list:
    """Bricht Text in Zeilen, die in die Breite passen. Absätze bleiben erhalten."""
    zeilen = []
    for absatz in str(text or "").split("\n"):
        woerter = absatz.split()
        if not woerter:
            zeilen.append("")
            continue
        zeile = ""
        for wort in woerter:
            # Ein Wort, das allein zu lang ist (etwa eine lange Adresse), wird geteilt.
            while pdf_textbreite(wort, groesse, fett) > breite and len(wort) > 1:
                teil = len(wort) - 1
                while teil > 1 and pdf_textbreite(wort[:teil], groesse, fett) > breite:
                    teil -= 1
                if zeile:
                    zeilen.append(zeile)
                    zeile = ""
                zeilen.append(wort[:teil])
                wort = wort[teil:]
            versuch = (zeile + " " + wort) if zeile else wort
            if pdf_textbreite(versuch, groesse, fett) <= breite:
                zeile = versuch
            else:
                zeilen.append(zeile)
                zeile = wort
        zeilen.append(zeile)
    return zeilen


def _pdf_zeichenkette(text) -> bytes:
    roh = pdf_kodieren(text)
    return b"(" + roh.replace(b"\\", b"\\\\").replace(b"(", b"\\(").replace(b")", b"\\)") + b")"


def _pdf_info_text(text) -> bytes:
    """Titel und Autor als UTF-16 - so stimmen Umlaute auch in den Dateieigenschaften."""
    return b"<FEFF" + str(text or "").encode("utf-16-be").hex().upper().encode("ascii") + b">"


def _pdf_zahl(wert: float) -> bytes:
    text = ("%.2f" % wert).rstrip("0").rstrip(".")
    return (text if text not in ("", "-0") else "0").encode("ascii")


def _pdf_farbe(farbe, fuellen: bool = True) -> bytes:
    """Grauwert (eine Zahl) oder Farbe (drei Zahlen zwischen 0 und 1)."""
    if isinstance(farbe, (tuple, list)):
        teile = b" ".join(_pdf_zahl(float(f)) for f in farbe[:3])
        return teile + (b" rg" if fuellen else b" RG")
    return _pdf_zahl(float(farbe)) + (b" g" if fuellen else b" G")


class PdfDokument:
    """Ein mehrseitiges A4-Dokument. Koordinaten von oben links, in Punkt."""

    def __init__(self, titel: str = "", autor: str = ""):
        self.titel = titel
        self.autor = autor
        self.seiten = []
        self.fusszeile = None  # Aufruf (dokument, seite, seiten) beim Speichern
        self.neue_seite()

    # -- Zeichnen ------------------------------------------------------------

    def neue_seite(self):
        """Beginnt eine neue Seite; alles Weitere landet dort."""
        self.seiten.append([])
        self._seite = self.seiten[-1]

    def text(self, x: float, y: float, text, groesse: float = 10, fett: bool = False,
             ausrichtung: str = "links", farbe=0):
        """Schreibt eine Zeile. ``y`` ist die Grundlinie, von oben gemessen."""
        if text is None or str(text) == "":
            return
        if ausrichtung == "rechts":
            x -= pdf_textbreite(text, groesse, fett)
        elif ausrichtung == "mitte":
            x -= pdf_textbreite(text, groesse, fett) / 2.0
        self._seite.append(
            b"BT " + _pdf_farbe(farbe) + b" /" + (b"F2" if fett else b"F1") + b" "
            + _pdf_zahl(groesse) + b" Tf 1 0 0 1 " + _pdf_zahl(x) + b" "
            + _pdf_zahl(PDF_SEITE_HOEHE - y) + b" Tm " + _pdf_zeichenkette(text) + b" Tj ET")

    def absatz(self, x: float, y: float, text, breite: float, groesse: float = 10,
               fett: bool = False, zeilenabstand: float = 1.35, farbe=0) -> float:
        """Schreibt umbrochenen Text und gibt die Höhe der nächsten freien Zeile zurück."""
        for zeile in pdf_umbrechen(text, breite, groesse, fett):
            self.text(x, y, zeile, groesse, fett, farbe=farbe)
            y += groesse * zeilenabstand
        return y

    def linie(self, x1: float, y1: float, x2: float, y2: float, staerke: float = 0.5,
              farbe=0):
        self._seite.append(
            b"q " + _pdf_farbe(farbe, fuellen=False) + b" " + _pdf_zahl(staerke) + b" w "
            + _pdf_zahl(x1) + b" " + _pdf_zahl(PDF_SEITE_HOEHE - y1) + b" m "
            + _pdf_zahl(x2) + b" " + _pdf_zahl(PDF_SEITE_HOEHE - y2) + b" l S Q")

    def flaeche(self, x: float, y: float, breite: float, hoehe: float, farbe=0.93):
        """Ein gefülltes Rechteck; ``y`` ist die Oberkante."""
        self._seite.append(
            b"q " + _pdf_farbe(farbe) + b" " + _pdf_zahl(x) + b" "
            + _pdf_zahl(PDF_SEITE_HOEHE - y - hoehe) + b" " + _pdf_zahl(breite) + b" "
            + _pdf_zahl(hoehe) + b" re f Q")

    # -- Schreiben -----------------------------------------------------------

    def als_bytes(self) -> bytes:
        """Das fertige PDF."""
        # Die Fußzeile kommt erst jetzt dazu, weil erst jetzt die Seitenzahl feststeht.
        # Sie landet in einer eigenen Liste, damit zweimal Speichern nicht doppelt druckt.
        fertige_seiten = []
        for nummer, befehle in enumerate(self.seiten, 1):
            fuss = []
            if self.fusszeile is not None:
                self._seite = fuss
                self.fusszeile(self, nummer, len(self.seiten))
            fertige_seiten.append(befehle + fuss)
        self._seite = self.seiten[-1]

        objekte = []  # Inhalt von Objekt 1, 2, 3 ...

        def objekt(inhalt: bytes) -> int:
            objekte.append(inhalt)
            return len(objekte)

        katalog = objekt(b"")  # wird unten gefüllt, sobald die Seiten feststehen
        seitenbaum = objekt(b"")
        schrift = objekt(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica "
                         b"/Encoding /WinAnsiEncoding >>")
        schrift_fett = objekt(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold "
                              b"/Encoding /WinAnsiEncoding >>")
        jetzt = datetime.now().strftime("D:%Y%m%d%H%M%S").encode("ascii")
        info = objekt(b"<< /Title " + _pdf_info_text(self.titel) + b" /Author "
                      + _pdf_info_text(self.autor) + b" /Producer (Jarvis) /CreationDate ("
                      + jetzt + b") >>")

        seiten_nummern = []
        for befehle in fertige_seiten:
            roh = zlib.compress(b"\n".join(befehle))
            inhalt = objekt(b"<< /Length " + str(len(roh)).encode("ascii")
                            + b" /Filter /FlateDecode >>\nstream\n" + roh + b"\nendstream")
            seiten_nummern.append(objekt(
                b"<< /Type /Page /Parent " + str(seitenbaum).encode("ascii") + b" 0 R"
                b" /MediaBox [0 0 " + _pdf_zahl(PDF_SEITE_BREITE) + b" "
                + _pdf_zahl(PDF_SEITE_HOEHE) + b"] /Resources << /Font << /F1 "
                + str(schrift).encode("ascii") + b" 0 R /F2 "
                + str(schrift_fett).encode("ascii") + b" 0 R >> >> /Contents "
                + str(inhalt).encode("ascii") + b" 0 R >>"))

        objekte[katalog - 1] = (b"<< /Type /Catalog /Pages "
                                + str(seitenbaum).encode("ascii") + b" 0 R >>")
        objekte[seitenbaum - 1] = (
            b"<< /Type /Pages /Kids [" + b" ".join(str(n).encode("ascii") + b" 0 R"
                                                    for n in seiten_nummern)
            + b"] /Count " + str(len(seiten_nummern)).encode("ascii") + b" >>")

        ausgabe = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
        positionen = []
        for nummer, inhalt in enumerate(objekte, 1):
            positionen.append(len(ausgabe))
            ausgabe += str(nummer).encode("ascii") + b" 0 obj\n" + inhalt + b"\nendobj\n"
        verzeichnis = len(ausgabe)
        ausgabe += b"xref\n0 " + str(len(objekte) + 1).encode("ascii") + b"\n"
        ausgabe += b"0000000000 65535 f \n"
        for position in positionen:
            ausgabe += ("%010d 00000 n \n" % position).encode("ascii")
        ausgabe += (b"trailer\n<< /Size " + str(len(objekte) + 1).encode("ascii")
                    + b" /Root " + str(katalog).encode("ascii") + b" 0 R /Info "
                    + str(info).encode("ascii") + b" 0 R >>\nstartxref\n"
                    + str(verzeichnis).encode("ascii") + b"\n%%EOF\n")
        return bytes(ausgabe)

    def speichern(self, pfad: str) -> str:
        """Schreibt das PDF und gibt den Pfad zurück."""
        with open(pfad, "wb") as datei:
            datei.write(self.als_bytes())
        return pfad
