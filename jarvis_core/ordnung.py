# -*- coding: utf-8 -*-
"""Ordnung - Dateien und Fotos auf dem Mac sortieren: Downloads, Bilder, Schreibtisch, Dokumente, Werkstatt.

Regeln (im Code erzwungen, nicht nur versprochen):

* Nur in diesen Ordnern. Nie in versteckten Ordnern, nie in Paketen (Fotos-Mediathek, Programme), nie über
  Verknüpfungen hinaus. Bewegt werden nur Dateien in der obersten Ebene des gewählten Ordners - vorhandene
  Unterordner bleiben, wie sie sind.
* Es wird nur VERSCHOBEN - nie gelöscht und nie überschrieben. Gibt es den Namen am Ziel schon, heißt die neue
  Datei "Name (2).jpg".
* Erst wird ein Plan gemacht, der jede einzelne Datei nennt; der Nutzer gibt ihn frei. Ausgeführt wird genau
  dieser Plan, und nur für Dateien, die sich seitdem nicht verändert haben.
* Jede Ausführung wird protokolliert und lässt sich rückgängig machen.
* Unfertige Downloads, iCloud-Platzhalter und gerade erst geänderte Dateien bleiben, wo sie sind.

Aufnahmedatum von Fotos: EXIF aus JPEG (eigener kleiner Leser, ohne Zusatzpakete), bei Videos der Filmkopf
(iPhone: com.apple.quicktime.creationdate, sonst mvhd) -> Spotlight (``mdls``, auf dem Mac, z. B. für HEIC) ->
Erstelldatum der Datei -> Änderungsdatum. Spotlight meldet ohne Kameradaten still das Erstelldatum der Datei; so ein
Wert gilt nicht als Aufnahme. Die Quelle steht in der Vorschau. Live Photos (IMG_1.HEIC, IMG_1.MOV, IMG_1.AAE)
bleiben zusammen.
"""

import datetime
import errno
import fnmatch
import json
import os
import re
import shutil
import subprocess
import time
import unicodedata
from collections import OrderedDict, namedtuple

MAC_ORDNER = OrderedDict([("downloads", "Downloads"), ("bilder", "Pictures"), ("schreibtisch", "Desktop"),
                          ("dokumente", "Documents")])
ANZEIGE = {"downloads": "Downloads", "bilder": "Bilder", "schreibtisch": "Schreibtisch", "dokumente": "Dokumente",
           "werkstatt": "Werkstatt"}
KATEGORIEN = (
    ("Bilder", ("jpg", "jpeg", "png", "heic", "heif", "gif", "webp", "tif", "tiff", "bmp", "dng", "cr2", "nef", "arw", "svg")),
    ("Videos", ("mov", "mp4", "m4v", "avi", "mkv", "3gp", "webm")),
    ("PDFs", ("pdf",)),
    ("Dokumente", ("doc", "docx", "odt", "rtf", "txt", "pages", "md")),
    ("Tabellen", ("xls", "xlsx", "csv", "numbers", "ods")),
    ("Präsentationen", ("ppt", "pptx", "key", "odp")),
    ("Archive", ("zip", "rar", "7z", "tar", "gz", "tgz", "bz2", "xz")),
    ("Installationsdateien", ("dmg", "pkg", "mpkg", "iso")),
    ("Musik und Sprachnachrichten", ("mp3", "m4a", "wav", "aac", "ogg", "opus", "flac", "aiff")),
)
VIDEO_ENDUNGEN = ("mov", "mp4", "m4v")
FOTO_ENDUNGEN = ("jpg", "jpeg", "png", "heic", "heif", "dng", "tif", "tiff", "aae") + VIDEO_ENDUNGEN
UNFERTIG = (".crdownload", ".download", ".part", ".partial", ".opdownload", ".tmp")
LAUFEND = (".crdownload", ".download", ".part")  # "Name.pdf.part" neben "Name.pdf" (Firefox): auch Name.pdf wartet
PAKET = re.compile(r"\.(photoslibrary|app|bundle|framework|download|plugin|kext|imovielibrary|fcpbundle)$", re.I)
SF_DATALESS = 0x40000000  # macOS: Datei liegt nur in iCloud (Platzhalter)
FRISCH_SEKUNDEN = 120  # gerade geänderte Dateien bleiben liegen (vielleicht noch im Download)
MAX_PLAN = 500
MAX_EINZELABFRAGEN = 300  # mdls einzeln, wenn die Sammelabfrage nicht eindeutig zuzuordnen ist
MAX_ANSEHEN = 60
_TAG = re.compile(r"^(\d{4})-(\d{2})-(\d{2})$|^(\d{1,2})\.(\d{1,2})\.(\d{4})$")

Datei = namedtuple("Datei", "pfad name endung groesse mtime kategorie")


class OrdnungFehler(Exception):
    """Fehler, den der Nutzer verstehen soll."""


# ------------------------------------------------------------------ Ordner ---

def heim():
    return os.path.realpath(os.environ.get("JARVIS_HEIM") or os.path.expanduser("~"))  # JARVIS_HEIM nur für Tests


def ordner_pfad(konfig, name):
    """Pfad eines verwalteten Ordners. Wirft OrdnungFehler, wenn der Ordner nicht freigegeben ist."""
    if name == "werkstatt":
        os.makedirs(konfig.werkstatt_pfad, exist_ok=True)
        return os.path.realpath(konfig.werkstatt_pfad)
    if name not in MAC_ORDNER or name not in konfig.verwaltete_ordner:
        erlaubt = ["werkstatt"] + [n for n in MAC_ORDNER if n in konfig.verwaltete_ordner]
        raise OrdnungFehler("Den Ordner %r verwaltet JARVIS nicht. Möglich: %s." % (name, ", ".join(erlaubt)))
    return os.path.realpath(os.path.join(heim(), MAC_ORDNER[name]))


def relativ_pruefen(angabe, feld="Ordner", leer_erlaubt=True):
    """Ein Unterordner wie "Baustellen/Berger/1 vorher": relativ, ohne "..", nicht versteckt, kein Paket, kein ":"."""
    angabe = (angabe or "").strip().strip("/")
    if not angabe:
        if leer_erlaubt:
            return ""
        raise OrdnungFehler("%s fehlt." % feld)
    teile = [t.strip() for t in angabe.replace("\\", "/").split("/")]
    if len(teile) > 6:
        raise OrdnungFehler("%s ist zu tief verschachtelt (höchstens 6 Ebenen)." % feld)
    for teil in teile:
        if not teil or teil in (".", ".."):
            raise OrdnungFehler("%s darf weder leer sein noch \"..\" enthalten." % feld)
        if teil.startswith(".") or ":" in teil or "\x00" in teil or len(teil) > 80:
            raise OrdnungFehler("%s %r ist nicht erlaubt (versteckt, \":\" oder zu lang)." % (feld, teil))
        if PAKET.search(teil):
            raise OrdnungFehler("In Pakete wie die Fotos-Mediathek oder Programme greift JARVIS nicht ein.")
    return "/".join(teile)


def _innerhalb(basis, pfad):
    pfad = os.path.realpath(pfad)
    return pfad == basis or pfad.startswith(basis + os.sep)


def verzeichnis(konfig, ordner, unterordner=""):
    basis = ordner_pfad(konfig, ordner)
    unter = relativ_pruefen(unterordner, "Unterordner")
    pfad = os.path.realpath(os.path.join(basis, unter)) if unter else basis
    if not _innerhalb(basis, pfad):
        raise OrdnungFehler("Der Pfad führt aus dem Ordner heraus.")
    if not os.path.isdir(pfad):
        raise OrdnungFehler("%s gibt es nicht." % ("%s/%s" % (ANZEIGE.get(ordner, ordner), unter) if unter else ANZEIGE.get(ordner, ordner)))
    return basis, pfad


def datei_aufloesen(konfig, angabe):
    """ "bilder:Baustellen/IMG_1.jpg" oder "praesentationen/x.html" (= Werkstatt) -> (Ordnername, echter Pfad, Endung).

    Nur Dateien in der Werkstatt und den verwalteten Mac-Ordnern, nie in Paketen, nie über Verknüpfungen."""
    ordner, trenner, rest = (angabe or "").partition(":")
    if not trenner or "/" in ordner:
        ordner, rest = "werkstatt", angabe
    ordner = ordner.strip().lower()
    basis = ordner_pfad(konfig, ordner)
    relativ = relativ_pruefen(rest, "Dateiangabe", leer_erlaubt=False)
    pfad = os.path.realpath(os.path.join(basis, relativ))
    if not _innerhalb(basis, pfad) or os.path.islink(os.path.join(basis, relativ)):
        raise OrdnungFehler("%r liegt außerhalb des Ordners." % angabe)
    if not os.path.isfile(pfad):
        raise OrdnungFehler("Die Datei %r gibt es nicht." % angabe)
    endung = pfad.rsplit(".", 1)[-1].lower() if "." in os.path.basename(pfad) else ""
    return ordner, pfad, endung


# ----------------------------------------------------------------- Dateien ---

def kategorie(endung):
    for name, endungen in KATEGORIEN:
        if endung in endungen:
            return name
    return "Sonstiges"


def dateien(pfad, jetzt=None):
    """Dateien in der obersten Ebene von ``pfad``: (bewegbar, übersprungen mit Grund, Unterordner)."""
    jetzt = jetzt or time.time()
    bewegbar, uebersprungen, unterordner = [], [], []
    try:
        namen = sorted(os.listdir(pfad), key=str.lower)
    except PermissionError:
        raise OrdnungFehler("macOS erlaubt den Zugriff noch nicht. Beim ersten Mal fragt der Mac – dann „OK“. Sonst: "
                            "Systemeinstellungen → Datenschutz & Sicherheit → Dateien und Ordner → Terminal.") from None
    laufend = {n[:-len(e)].lower() for n in namen for e in LAUFEND if n.lower().endswith(e)}
    for name in namen:
        voll = os.path.join(pfad, name)
        if name.startswith("."):
            continue  # versteckt, auch iCloud-Platzhalter (".Name.pdf.icloud")
        try:
            st = os.lstat(voll)
        except OSError:
            continue
        if os.path.islink(voll):
            uebersprungen.append((name, "Verknüpfung"))
            continue
        if os.path.isdir(voll):
            unterordner.append(name)
            continue
        if name.lower().endswith(UNFERTIG) or name.lower() in laufend:
            uebersprungen.append((name, "Download läuft noch"))
            continue
        if name.startswith("~$"):
            uebersprungen.append((name, "Sperrdatei - das Dokument ist gerade geöffnet"))
            continue
        if getattr(st, "st_flags", 0) & SF_DATALESS:
            uebersprungen.append((name, "liegt nur in iCloud"))
            continue
        if jetzt - st.st_mtime < FRISCH_SEKUNDEN:
            uebersprungen.append((name, "gerade erst geändert"))
            continue
        endung = name.rsplit(".", 1)[-1].lower() if "." in name else ""
        bewegbar.append(Datei(voll, name, endung, st.st_size, st.st_mtime, kategorie(endung)))
    return bewegbar, uebersprungen, unterordner


# ----------------------------------------------------------- Aufnahmedatum ---

def _exif_block(daten):
    """Der TIFF-Teil des EXIF-Blocks einer JPEG-Datei - oder None."""
    if daten[:2] != b"\xff\xd8":
        return None
    i = 2
    while i + 4 <= len(daten):
        if daten[i] != 0xFF:
            return None
        marker = daten[i + 1]
        if marker == 0xFF:  # Füllbyte
            i += 1
            continue
        if marker in (0xD9, 0xDA):  # Bildende oder Bilddaten: keine Metadaten mehr
            return None
        laenge = int.from_bytes(daten[i + 2:i + 4], "big")
        if laenge < 2:
            return None
        if marker == 0xE1 and daten[i + 4:i + 10] == b"Exif\x00\x00":
            return daten[i + 10:i + 2 + laenge]
        i += 2 + laenge
    return None


def _tiff_datum(tiff):
    """DateTimeOriginal (sonst DateTimeDigitized, sonst DateTime) aus einem TIFF/EXIF-Block."""
    if len(tiff) < 8 or tiff[:2] not in (b"II", b"MM"):
        return None
    reihenfolge = "little" if tiff[:2] == b"II" else "big"

    def zahl(stelle, laenge):
        return int.from_bytes(tiff[stelle:stelle + laenge], reihenfolge)

    def eintraege(stelle):
        if stelle <= 0 or stelle + 2 > len(tiff):
            return {}
        ergebnis = {}
        for k in range(min(zahl(stelle, 2), 300)):
            p = stelle + 2 + 12 * k
            if p + 12 > len(tiff):
                break
            ergebnis[zahl(p, 2)] = (zahl(p + 2, 2), zahl(p + 4, 4), p + 8)
        return ergebnis

    ifd0 = eintraege(zahl(4, 4))
    kandidaten = []
    if 0x8769 in ifd0:
        exif = eintraege(zahl(ifd0[0x8769][2], 4))
        kandidaten += [exif[t] for t in (0x9003, 0x9004) if t in exif]
    if 0x0132 in ifd0:
        kandidaten.append(ifd0[0x0132])
    for typ, anzahl, stelle in kandidaten:
        if typ != 2 or anzahl < 19:
            continue
        start = zahl(stelle, 4) if anzahl > 4 else stelle
        text = tiff[start:start + 19].decode("ascii", "replace")
        try:
            return datetime.datetime.strptime(text, "%Y:%m:%d %H:%M:%S")
        except ValueError:
            continue
    return None


def exif_datum(pfad):
    """Aufnahmedatum aus einer JPEG-Datei (Ortszeit der Kamera) - oder None."""
    try:
        with open(pfad, "rb") as f:
            daten = f.read(512 * 1024)
    except OSError:
        return None
    tiff = _exif_block(daten)
    return _tiff_datum(tiff) if tiff else None


def _mdls_programm():
    fest = os.environ.get("JARVIS_MDLS")  # nur für Tests
    if fest:
        return fest if os.path.isfile(fest) and os.access(fest, os.X_OK) else None
    return shutil.which("mdls")


def _mdls(programm, pfade):
    """Rohwerte von mdls für ein einziges Merkmal: ein Wert je Datei - oder None, wenn die Ausgabe nicht genau passt."""
    try:
        lauf = subprocess.run([programm, "-raw", "-name", "kMDItemContentCreationDate"] + pfade,  # noqa: S603
                              capture_output=True, timeout=60)
    except (OSError, subprocess.SubprocessError):
        return None
    werte = lauf.stdout.decode("utf-8", "replace").split("\x00")
    if len(werte) == len(pfade) + 1 and not werte[-1].strip():
        werte = werte[:-1]  # endet die Ausgabe mit NUL, ist das kein zusätzlicher Wert
    return werte if len(werte) == len(pfade) else None


def _spotlight_zeit(wert):
    try:
        return datetime.datetime.strptime(wert.strip(), "%Y-%m-%d %H:%M:%S %z").astimezone().replace(tzinfo=None)
    except ValueError:
        return None  # "(null)": Spotlight kennt kein Datum


def _nur_dateidatum(pfad, datum):
    """Ohne Kameradaten trägt Spotlight still das Erstelldatum der Datei ein - das ist keine Aufnahmezeit."""
    try:
        st = os.stat(pfad)
    except OSError:
        return False
    erstellt = datetime.datetime.fromtimestamp(getattr(st, "st_birthtime", None) or st.st_mtime)
    return abs((datum - erstellt).total_seconds()) < 2


def spotlight_daten(pfade):
    """Aufnahmedatum laut Spotlight (``mdls``) für mehrere Dateien: {Pfad: datetime in Ortszeit}.

    Erst gesammelt (200 je Aufruf). Passt die Ausgabe nicht genau zu den Dateien (z. B. eine war nicht lesbar), wird
    einzeln gefragt - lieber langsamer als ein Datum bei der falschen Datei."""
    programm = _mdls_programm()
    ergebnis = {}
    if not programm or not pfade:
        return ergebnis
    einzeln_frei = MAX_EINZELABFRAGEN
    for start in range(0, len(pfade), 200):
        teil = pfade[start:start + 200]
        werte = _mdls(programm, teil)
        if werte is not None:
            paare = list(zip(teil, werte))
        else:
            paare = []
            for pfad in teil[:max(einzeln_frei, 0)]:
                einzeln = _mdls(programm, [pfad])
                if einzeln is not None:
                    paare.append((pfad, einzeln[0]))
            einzeln_frei -= len(teil)
        for pfad, wert in paare:
            datum = _spotlight_zeit(wert)
            if datum and not _nur_dateidatum(pfad, datum):
                ergebnis[pfad] = datum
    return ergebnis


# Videos (MOV/MP4): Filmkopf lesen, ohne die Bilddaten (oft Gigabytes) anzufassen
QT_EPOCHE = datetime.datetime(1904, 1, 1, tzinfo=datetime.timezone.utc)
MAX_MOOV = 32 * 1024 * 1024


def _atome(daten, start=0, ende=None):
    """(Typ, Inhaltsbeginn, Ende) der Atome (Boxen) zwischen start und ende - mit Grenzprüfung."""
    ende = len(daten) if ende is None else ende
    pos = start
    while pos + 8 <= ende:
        groesse, typ, inhalt = int.from_bytes(daten[pos:pos + 4], "big"), bytes(daten[pos + 4:pos + 8]), pos + 8
        if groesse == 1:
            if pos + 16 > ende:
                return
            groesse, inhalt = int.from_bytes(daten[pos + 8:pos + 16], "big"), pos + 16
        elif groesse == 0:
            groesse = ende - pos
        if groesse < inhalt - pos or pos + groesse > ende:
            return
        yield typ, inhalt, pos + groesse
        pos += groesse


def _moov_lesen(pfad):
    """Nur den Filmkopf ("moov") einer MOV/MP4-Datei lesen. Oberste Ebene: Kopf je Atom lesen und weiterspringen."""
    with open(pfad, "rb") as f:
        f.seek(0, os.SEEK_END)
        ende, pos = f.tell(), 0
        for _ in range(64):
            if pos + 8 > ende:
                return None
            f.seek(pos)
            kopf = f.read(16)
            groesse, typ, kopflaenge = int.from_bytes(kopf[:4], "big"), kopf[4:8], 8
            if groesse == 1 and len(kopf) == 16:
                groesse, kopflaenge = int.from_bytes(kopf[8:16], "big"), 16
            elif groesse == 0:
                groesse = ende - pos
            if groesse < kopflaenge or pos + groesse > ende:
                return None
            if typ == b"moov":
                if groesse > MAX_MOOV:
                    return None
                f.seek(pos + kopflaenge)
                return f.read(groesse - kopflaenge)
            pos += groesse
    return None


def _zeit_plausibel(datum):
    return datum if datum and 2000 <= datum.year <= datetime.date.today().year + 1 else None


def _apple_aufnahme(moov):
    """iPhone: "com.apple.quicktime.creationdate" (Aufnahmezeit mit Zeitzone, bleibt beim Bearbeiten erhalten)."""
    behaelter = [(moov, 0, len(moov))] + [(moov, s, e) for t, s, e in _atome(moov) if t == b"udta"]
    for daten, start, ende in behaelter:
        for typ, s, e in _atome(daten, start, ende):
            if typ != b"meta":
                continue
            kinder = {}
            for versatz in (0, 4):  # QuickTime: ohne Versionsfeld, MP4: mit
                kinder = {t: (a, b) for t, a, b in _atome(daten, s + versatz, e)}
                if b"keys" in kinder and b"ilst" in kinder:
                    break
            if b"keys" not in kinder or b"ilst" not in kinder:
                continue
            ks, ke = kinder[b"keys"]
            pos, nummer = ks + 8, None
            for nr in range(1, min(int.from_bytes(daten[ks + 4:ks + 8], "big"), 200) + 1):
                laenge = int.from_bytes(daten[pos:pos + 4], "big")
                if laenge < 8 or pos + laenge > ke:
                    break
                if daten[pos + 8:pos + laenge] == b"com.apple.quicktime.creationdate":
                    nummer = nr
                    break
                pos += laenge
            if nummer is None:
                continue
            for t, a, b in _atome(daten, *kinder[b"ilst"]):
                if int.from_bytes(t, "big") != nummer:
                    continue
                for t2, a2, b2 in _atome(daten, a, b):
                    if t2 == b"data" and b2 - a2 > 8:
                        text = daten[a2 + 8:b2].decode("utf-8", "replace").strip()
                        for muster in ("%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%dT%H:%M:%S.%f%z"):
                            try:  # Uhrzeit am Aufnahmeort, wie bei EXIF
                                return _zeit_plausibel(datetime.datetime.strptime(text, muster).replace(tzinfo=None))
                            except ValueError:
                                continue
    return None


def _mvhd_aufnahme(moov):
    """Erstellzeit im Filmkopf (Sekunden seit 1904, UTC). 0 oder Unsinn = unbekannt."""
    for typ, s, e in _atome(moov):
        if typ == b"mvhd" and e - s >= 12:
            lang = moov[s] == 1
            sekunden = int.from_bytes(moov[s + 4:s + (12 if lang else 8)], "big")
            try:
                return _zeit_plausibel((QT_EPOCHE + datetime.timedelta(seconds=sekunden)).astimezone().replace(tzinfo=None))
            except (OverflowError, OSError, ValueError):
                return None
    return None


def video_datum(pfad):
    """Aufnahmedatum eines Videos (MOV/MP4) in Ortszeit - oder None."""
    try:
        moov = _moov_lesen(pfad)
    except OSError:
        return None
    if not moov:
        return None
    return _apple_aufnahme(moov) or _mvhd_aufnahme(moov)


def _stamm(name):
    return unicodedata.normalize("NFC", name.rsplit(".", 1)[0] if "." in name else name).casefold()


def daten_bestimmen(liste, fotos=False):
    """{Pfad: (datetime, Quelle)}. Bei Fotos zuerst Kamera (EXIF) bzw. Filmkopf, dann Spotlight, sonst das Dateidatum."""
    ergebnis = {}
    offen = []
    for d in liste:
        datum = None
        if fotos and d.endung in ("jpg", "jpeg"):
            datum = exif_datum(d.pfad)
        elif fotos and d.endung in VIDEO_ENDUNGEN:
            datum = video_datum(d.pfad)
        if datum:
            ergebnis[d.pfad] = (datum, "Aufnahme")
            continue
        offen.append(d)
    spotlight = spotlight_daten([d.pfad for d in offen]) if fotos else {}
    for d in offen:
        if d.pfad in spotlight:
            ergebnis[d.pfad] = (spotlight[d.pfad], "Aufnahme")
            continue
        try:
            st = os.stat(d.pfad)
            sekunden = getattr(st, "st_birthtime", None) or st.st_mtime
        except OSError:
            sekunden = d.mtime
        ergebnis[d.pfad] = (datetime.datetime.fromtimestamp(sekunden), "Dateidatum")
    if fotos:
        # Live Photo und Bearbeitung (IMG_1.HEIC + IMG_1.MOV + IMG_1.AAE) gehören zusammen: Wer nur ein Dateidatum hat,
        # bekommt das Aufnahmedatum seines Partners - so landen sie im selben Tagesordner.
        # Nur unter Fotos, Videos und .AAE - eine "Angebot.pdf" übernimmt nie das Datum von "Angebot.jpg".
        gruppen = {}
        for d in liste:
            if d.endung in FOTO_ENDUNGEN:
                gruppen.setdefault(_stamm(d.name), []).append(d)
        for teile in gruppen.values():
            partner = next((d for d in teile if ergebnis[d.pfad][1] == "Aufnahme"), None)
            if partner is None:
                continue
            for d in teile:
                if ergebnis[d.pfad][1] == "Dateidatum":
                    ergebnis[d.pfad] = (ergebnis[partner.pfad][0], "Aufnahme laut %s" % partner.name)
    return ergebnis


def tag_pruefen(text):
    """"2026-11-03" oder "3.11.2026" -> date. Wirft OrdnungFehler."""
    t = _TAG.match((text or "").strip())
    if not t:
        raise OrdnungFehler("Datum bitte als JJJJ-MM-TT oder TT.MM.JJJJ, nicht %r." % text)
    jahr, monat, tag = (t.group(1), t.group(2), t.group(3)) if t.group(1) else (t.group(6), t.group(5), t.group(4))
    try:
        return datetime.date(int(jahr), int(monat), int(tag))
    except ValueError:
        raise OrdnungFehler("Das Datum %r gibt es nicht." % text) from None


# ------------------------------------------------------------------- Pläne ---

def _eindeutig(ziel_ordner, name, belegt):
    """Ein Name, der am Ziel noch frei ist (auch gegenüber anderen Dateien im selben Plan): "Name (2).jpg"."""
    stamm, punkt, endung = name.rpartition(".")
    if not punkt:
        stamm, endung = name, ""
    kandidat, nummer = name, 1
    while True:
        voll = os.path.join(ziel_ordner, kandidat)
        # Der Mac unterscheidet weder Groß/klein noch zwei Schreibweisen desselben Umlauts (NFC/NFD)
        schluessel = unicodedata.normalize("NFC", voll).casefold()
        if schluessel not in belegt and not os.path.lexists(voll):
            belegt.add(schluessel)
            return voll
        nummer += 1
        kandidat = "%s (%d)%s" % (stamm, nummer, "." + endung if punkt else "")


def _plan(basis, eintraege, beschreibung, uebersprungen):
    if not eintraege:
        raise OrdnungFehler("Dazu gibt es nichts zu verschieben.%s" % (
            " Übersprungen: " + "; ".join("%s (%s)" % u for u in uebersprungen[:10]) if uebersprungen else ""))
    if len(eintraege) > MAX_PLAN:
        raise OrdnungFehler("Das wären %d Dateien auf einmal – höchstens %d. Bitte kleiner fassen (Zeitraum oder Muster)."
                            % (len(eintraege), MAX_PLAN))
    return {"basis": basis, "beschreibung": beschreibung, "uebersprungen": uebersprungen[:50],
            "schritte": eintraege}


def ordnen_planen(konfig, ordner, art, ziel="Sortiert", unterordner=""):
    """Plan: Dateien eines Ordners nach Art, nach Monat oder (Fotos) nach Aufnahmetag in Unterordner von ``ziel``."""
    basis, pfad = verzeichnis(konfig, ordner, unterordner)
    ziel = relativ_pruefen(ziel or "Sortiert", "Zielordner", leer_erlaubt=False)
    liste, uebersprungen, _ = dateien(pfad)
    if art == "fotos_nach_datum":
        liste = [d for d in liste if d.endung in FOTO_ENDUNGEN]
    elif art not in ("nach_art", "nach_datum"):
        raise OrdnungFehler("Unbekannte Art %r." % art)
    daten = daten_bestimmen(liste, fotos=(art == "fotos_nach_datum")) if art != "nach_art" else {}
    belegt, schritte = set(), []
    for d in liste:
        if art == "nach_art":
            unter, info = d.kategorie, ""
        else:
            datum, quelle = daten[d.pfad]
            unter = datum.strftime("%Y/%Y-%m-%d") if art == "fotos_nach_datum" else datum.strftime("%Y-%m")
            info = "%s %s" % (quelle, datum.strftime("%d.%m.%Y"))
        zielordner = os.path.join(pfad, ziel, unter)
        schritte.append({"von": d.pfad, "nach": _eindeutig(zielordner, d.name, belegt), "groesse": d.groesse,
                         "mtime": d.mtime, "info": info})
    namen = {"nach_art": "nach Art", "nach_datum": "nach Monat", "fotos_nach_datum": "Fotos nach Aufnahmetag"}
    return _plan(basis, schritte, "%s %s in „%s“" % (ANZEIGE.get(ordner, ordner), namen[art], ziel), uebersprungen)


def verschieben_planen(konfig, ordner, ziel, von=None, bis=None, muster="", unterordner="", nur_fotos=False):
    """Plan: ausgewählte Dateien (Zeitraum, Namensmuster) in einen Unterordner, z. B. "Baustellen/Berger/1 vorher"."""
    basis, pfad = verzeichnis(konfig, ordner, unterordner)
    ziel = relativ_pruefen(ziel, "Zielordner", leer_erlaubt=False)
    if not (von or bis or muster):
        raise OrdnungFehler("Bitte einen Zeitraum (von/bis) oder ein Namensmuster angeben - sonst wäre es der ganze Ordner.")
    liste, uebersprungen, _ = dateien(pfad)
    if nur_fotos:
        liste = [d for d in liste if d.endung in FOTO_ENDUNGEN]
    if muster:
        liste = [d for d in liste if fnmatch.fnmatch(d.name.lower(), muster.lower())]
    daten = daten_bestimmen(liste, fotos=True)
    belegt, schritte = set(), []
    zielordner = os.path.join(pfad, ziel)
    for d in liste:
        datum, quelle = daten[d.pfad]
        if (von and datum.date() < von) or (bis and datum.date() > bis):
            continue
        schritte.append({"von": d.pfad, "nach": _eindeutig(zielordner, d.name, belegt), "groesse": d.groesse,
                         "mtime": d.mtime, "info": "%s %s" % (quelle, datum.strftime("%d.%m.%Y"))})
    zeitraum = " vom %s" % von.strftime("%d.%m.%Y") if von else ""
    zeitraum += " bis %s" % bis.strftime("%d.%m.%Y") if bis else ""
    return _plan(basis, schritte, "%s%s%s nach „%s“" % (ANZEIGE.get(ordner, ordner), " (%s)" % muster if muster else "",
                                                     zeitraum, ziel), uebersprungen)


def vorschau(plan, kopf="werden VERSCHOBEN"):
    """Jede Datei, gruppiert nach Zielordner. Nichts wird ausgelassen."""
    basis = plan["basis"]
    gruppen = OrderedDict()
    for s in plan["schritte"]:
        gruppen.setdefault(os.path.relpath(os.path.dirname(s["nach"]), basis), []).append(s)
    zeilen = ["%d Datei(en) %s – %s. Nichts wird gelöscht oder überschrieben; rückgängig machbar." % (
        len(plan["schritte"]), kopf, plan["beschreibung"]), ""]
    for ordner, schritte in sorted(gruppen.items(), key=lambda g: g[0].lower()):
        zeilen.append("→ %s/ (%d)" % (ordner, len(schritte)))
        for s in schritte:
            alt, neu = os.path.basename(s["von"]), os.path.basename(s["nach"])
            zeilen.append("   %s%s%s" % (alt, " → " + neu if neu != alt else "", "  (%s)" % s["info"] if s.get("info") else ""))
    if plan.get("uebersprungen"):
        zeilen += ["", "Bleibt liegen: " + "; ".join("%s (%s)" % tuple(u) for u in plan["uebersprungen"])]
    return "\n".join(zeilen)


# -------------------------------------------------------------- Ausführen ---

def _verschieben_ohne_ueberschreiben(von, nach):
    """Verschiebt, ohne je etwas zu überschreiben: erst ein harter Link (scheitert, wenn das Ziel existiert),
    dann die alte Stelle lösen. Geht das auf diesem Laufwerk nicht, wird direkt vor dem Umbenennen geprüft."""
    try:
        os.link(von, nach)
    except FileExistsError:
        raise
    except OSError as fehler:
        if fehler.errno not in (errno.EPERM, errno.ENOTSUP, errno.EXDEV, errno.EMLINK, errno.EACCES,
                                getattr(errno, "EOPNOTSUPP", errno.ENOTSUP)):
            raise
        if os.path.lexists(nach):
            raise FileExistsError(nach) from None
        os.rename(von, nach)
        return
    os.unlink(von)


def ausfuehren(plan, protokoll_ordner, art="verschieben"):
    """Führt genau den freigegebenen Plan aus. Dateien, die sich seit dem Plan verändert haben, bleiben liegen."""
    os.makedirs(protokoll_ordner, mode=0o700, exist_ok=True)
    basis = plan["basis"]
    ergebnis = []
    for s in plan["schritte"]:
        von, nach = s["von"], s["nach"]
        if not (_innerhalb(basis, von) and _innerhalb(basis, os.path.dirname(nach))):
            ergebnis.append(dict(s, status="außerhalb des Ordners - übersprungen"))
            continue
        try:
            st = os.lstat(von)
        except OSError:
            ergebnis.append(dict(s, status="nicht mehr da"))
            continue
        if os.path.islink(von) or not os.path.isfile(von) or st.st_size != s["groesse"] or abs(st.st_mtime - s["mtime"]) > 1:
            ergebnis.append(dict(s, status="seit dem Plan verändert - liegen gelassen"))
            continue
        try:
            os.makedirs(os.path.dirname(nach), exist_ok=True)
            ziel = nach
            for _ in range(5):
                if os.path.lexists(ziel):  # inzwischen belegt: neuer freier Name statt Überschreiben
                    ziel = _eindeutig(os.path.dirname(nach), os.path.basename(nach), set())
                try:
                    _verschieben_ohne_ueberschreiben(von, ziel)
                    break
                except FileExistsError:
                    continue  # gleichzeitig belegt (oder gleicher Name in anderer Schreibweise): nächster Name
            else:
                raise FileExistsError(nach)
            ergebnis.append(dict(s, nach=ziel, status="ok"))
        except OSError as fehler:
            ergebnis.append(dict(s, status="Fehler: %s" % (fehler.strerror or fehler)))
    kennung = datetime.datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    with open(os.path.join(protokoll_ordner, "%s.json" % kennung), "w", encoding="utf-8") as f:
        json.dump({"kennung": kennung, "art": art, "basis": basis, "beschreibung": plan["beschreibung"],
                   "schritte": ergebnis}, f, ensure_ascii=False, indent=1)
    return kennung, ergebnis


def protokolle(protokoll_ordner):
    try:
        return sorted((n[:-5] for n in os.listdir(protokoll_ordner) if n.endswith(".json")), reverse=True)
    except OSError:
        return []


def rueckgaengig_planen(protokoll_ordner, kennung="letzte"):
    """Plan, der eine frühere Ausführung umkehrt: jede Datei zurück an ihren alten Ort (ohne zu überschreiben)."""
    vorhanden = protokolle(protokoll_ordner)
    if not vorhanden:
        raise OrdnungFehler("Es gibt noch nichts, was sich rückgängig machen ließe.")
    kennung = vorhanden[0] if kennung in ("", "letzte") else kennung
    if not re.match(r"^[0-9-]+$", kennung) or kennung not in vorhanden:
        raise OrdnungFehler("Kein Protokoll %r. Die letzten: %s." % (kennung, ", ".join(vorhanden[:5])))
    with open(os.path.join(protokoll_ordner, "%s.json" % kennung), encoding="utf-8") as f:
        alt = json.load(f)
    belegt, schritte = set(), []
    for s in alt["schritte"]:
        if s.get("status") != "ok" or not os.path.isfile(s["nach"]):
            continue
        st = os.lstat(s["nach"])
        zurueck = _eindeutig(os.path.dirname(s["von"]), os.path.basename(s["von"]), belegt)
        schritte.append({"von": s["nach"], "nach": zurueck, "groesse": st.st_size, "mtime": st.st_mtime,
                         "info": "zurück"})
    plan = _plan(alt["basis"], schritte, "Rückgängig: %s" % alt["beschreibung"], [])
    plan["protokoll"] = kennung
    return plan
