#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Tests für Dateien und Fotos ordnen (jarvis_core/ordnung.py und die Werkzeuge ordner_ansehen, ordnen,
dateien_verschieben, rueckgaengig).

Der Mac ist nachgebaut: ein eigener Heimordner mit Downloads, Pictures, Desktop, Documents; Spotlight (mdls) ist
durch tests/ersatz_mdls.py ersetzt. Die JPEG-Dateien mit Kamera-Datum erzeugt der Test selbst. Das Wichtigste:
es geht nie eine Datei verloren, nichts wird überschrieben, nichts passiert ohne Freigabe.

    python3 -m unittest tests.test_ordnung -v
"""

import datetime
import hashlib
import json
import os
import struct
import time
import unicodedata
from unittest import mock

from tests.hilfen import WURZEL, AgentBasis

from jarvis_core import gehirn, ordnung  # noqa: E402
from jarvis_core.werkzeuge import FREIGABE  # noqa: E402

ERSATZ_MDLS = os.path.join(WURZEL, "tests", "ersatz_mdls.py")
GESTERN = time.time() - 86400


def jpeg_mit_datum(datum, reihenfolge="II"):
    """Eine kleine JPEG-Datei mit EXIF-Aufnahmedatum (DateTimeOriginal), so wie Kameras sie schreiben."""
    e = "<" if reihenfolge == "II" else ">"
    wert = datum.encode("ascii") + b"\x00"
    tiff = reihenfolge.encode() + struct.pack(e + "HI", 42, 8)
    tiff += struct.pack(e + "H", 1) + struct.pack(e + "HHII", 0x8769, 4, 1, 26) + struct.pack(e + "I", 0)
    tiff += struct.pack(e + "H", 1) + struct.pack(e + "HHII", 0x9003, 2, len(wert), 44) + struct.pack(e + "I", 0)
    tiff += wert
    app1 = b"Exif\x00\x00" + tiff
    return b"\xff\xd8" + b"\xff\xe0" + struct.pack(">H", 16) + b"JFIF\x00" + b"\x00" * 9 + \
        b"\xff\xe1" + struct.pack(">H", len(app1) + 2) + app1 + b"\xff\xd9"


def jpeg_mit_gps(datum="2026:11:03 09:15:00", reihenfolge="II", xmp=True):
    """Wie ein Handyfoto: EXIF mit Ausrichtung (hochkant), Aufnahmedatum und Aufnahmeort (50° 56' 15" N), dazu XMP."""
    e = "<" if reihenfolge == "II" else ">"
    wert = datum.encode("ascii") + b"\x00"
    exif_ifd = 8 + 2 + 12 * 3 + 4
    datum_stelle = exif_ifd + 2 + 12 + 4
    gps_ifd = datum_stelle + len(wert)
    breite_stelle = gps_ifd + 2 + 12 * 2 + 4
    tiff = reihenfolge.encode() + struct.pack(e + "HI", 42, 8) + struct.pack(e + "H", 3)
    tiff += struct.pack(e + "HHI", 0x0112, 3, 1) + struct.pack(e + "HH", 6, 0)  # Ausrichtung: 90° gedreht
    tiff += struct.pack(e + "HHII", 0x8769, 4, 1, exif_ifd) + struct.pack(e + "HHII", 0x8825, 4, 1, gps_ifd)
    tiff += struct.pack(e + "I", 0)
    tiff += struct.pack(e + "H", 1) + struct.pack(e + "HHII", 0x9003, 2, len(wert), datum_stelle) + struct.pack(e + "I", 0)
    tiff += wert
    tiff += struct.pack(e + "H", 2) + struct.pack(e + "HHI", 0x0001, 2, 2) + b"N\x00\x00\x00"
    tiff += struct.pack(e + "HHII", 0x0002, 5, 3, breite_stelle) + struct.pack(e + "I", 0)
    tiff += GPS_BREITE(e)
    app1 = b"Exif\x00\x00" + tiff
    xmp_block = b"http://ns.adobe.com/xap/1.0/\x00<x:xmpmeta><exif:GPSLatitude>50,56.25N</exif:GPSLatitude></x:xmpmeta>"
    jpeg = b"\xff\xd8\xff\xe0" + struct.pack(">H", 16) + b"JFIF\x00" + b"\x00" * 9
    jpeg += b"\xff\xe1" + struct.pack(">H", len(app1) + 2) + app1
    if xmp:
        jpeg += b"\xff\xe1" + struct.pack(">H", len(xmp_block) + 2) + xmp_block
    return jpeg + b"\xff\xda\x00\x02BILDDATEN\xff\xd9"


def GPS_BREITE(e):  # noqa: N802 - Wert, den der Test im Ergebnis sucht
    return struct.pack(e + "IIIIII", 50, 1, 56, 1, 1500, 100)


def atom(typ, inhalt):
    return struct.pack(">I", 8 + len(inhalt)) + typ + inhalt


def video(mvhd=None, apple=None, version=0, mp4_meta=False):
    """Eine kleine MOV-Datei: ftyp, wide, mdat (Bilddaten), moov (Filmkopf mit mvhd und Apple-Metadaten)."""
    kinder = b""
    if mvhd is not None:
        if version == 1:
            kinder += atom(b"mvhd", b"\x01\x00\x00\x00" + struct.pack(">QQ", mvhd, mvhd) + b"\x00" * 80)
        else:
            kinder += atom(b"mvhd", b"\x00\x00\x00\x00" + struct.pack(">II", mvhd, mvhd) + b"\x00" * 88)
    if apple:
        schluessel = [b"com.apple.quicktime.make", b"com.apple.quicktime.creationdate"]
        keys = atom(b"keys", b"\x00" * 4 + struct.pack(">I", 2) + b"".join(
            struct.pack(">I", 8 + len(k)) + b"mdta" + k for k in schluessel))
        ilst = atom(b"ilst", atom(struct.pack(">I", 1), atom(b"data", b"\x00\x00\x00\x01\x00\x00\x00\x00Apple")) +
                    atom(struct.pack(">I", 2), atom(b"data", b"\x00\x00\x00\x01\x00\x00\x00\x00" + apple.encode())))
        hdlr = atom(b"hdlr", b"\x00" * 8 + b"mdta" + b"\x00" * 13)
        kinder += atom(b"meta", (b"\x00" * 4 if mp4_meta else b"") + hdlr + keys + ilst)
    return (atom(b"ftyp", b"qt  \x00\x00\x00\x00qt  ") + atom(b"wide", b"") + atom(b"mdat", b"\x00" * 5000) +
            atom(b"moov", kinder))


def qt_sekunden(jahr, monat, tag, stunde, minute):
    return int((datetime.datetime(jahr, monat, tag, stunde, minute, tzinfo=datetime.timezone.utc)
                - ordnung.QT_EPOCHE).total_seconds())


class OrdnungBasis(AgentBasis):
    def setUp(self):
        super().setUp()
        self.heim = os.path.join(self.ordner, "heim")
        for name in ("Downloads", "Pictures", "Desktop", "Documents"):
            os.makedirs(os.path.join(self.heim, name))
        os.chmod(ERSATZ_MDLS, 0o755)  # noqa: S103 - Ersatzprogramm muss ausführbar sein
        self.mdls_karte = os.path.join(self.ordner, "mdls.json")
        self.spotlight({})
        os.environ.update({"JARVIS_HEIM": self.heim, "JARVIS_MDLS": ERSATZ_MDLS, "FAKE_MDLS": self.mdls_karte})

    def spotlight(self, karte):
        with open(self.mdls_karte, "w", encoding="utf-8") as f:
            json.dump(karte, f)

    def datei(self, ordner, name, inhalt=b"x", alter=GESTERN):
        pfad = os.path.join(self.heim, ordner, name)
        os.makedirs(os.path.dirname(pfad), exist_ok=True)
        with open(pfad, "wb") as f:
            f.write(inhalt if isinstance(inhalt, bytes) else inhalt.encode("utf-8"))
        os.utime(pfad, (alter, alter))
        return pfad

    def bestand(self, ordner):
        """Alle Dateien unter einem Ordner als {Prüfsumme des Inhalts: Anzahl}. Unabhängig von Namen und Ort - so fällt
        jeder Verlust und jede Veränderung auf, auch wenn eine Datei beim Verschieben einen neuen Namen bekommt."""
        zaehler = {}
        for wurzel, _, namen in os.walk(os.path.join(self.heim, ordner)):
            for n in namen:
                with open(os.path.join(wurzel, n), "rb") as f:
                    h = hashlib.sha256(f.read()).hexdigest()
                zaehler[h] = zaehler.get(h, 0) + 1
        return zaehler

    def da(self, *teile):
        return os.path.exists(os.path.join(self.heim, *teile))

    def freigeben(self, e):
        self.assertEqual((e["status"], e["stufe"]), ("freigabe_offen", FREIGABE), e)
        code, antwort = self.agent.freigabe_beantworten(e["freigabe_id"], True)
        self.assertEqual(code, 200, antwort)
        return antwort


class AufnahmedatumTest(OrdnungBasis):
    def test_exif_beide_bytereihenfolgen(self):
        for reihenfolge in ("II", "MM"):
            with self.subTest(reihenfolge=reihenfolge):
                pfad = self.datei("Pictures", "kamera_%s.jpg" % reihenfolge, jpeg_mit_datum("2026:11:03 09:15:00", reihenfolge))
                self.assertEqual(ordnung.exif_datum(pfad).strftime("%Y-%m-%d %H:%M"), "2026-11-03 09:15")

    def test_kaputte_oder_fremde_dateien_ohne_absturz(self):
        for name, inhalt in (("leer.jpg", b""), ("kaputt.jpg", b"\xff\xd8\xff\xe1\x00\x02"), ("text.jpg", b"kein bild"),
                             ("abgeschnitten.jpg", jpeg_mit_datum("2026:11:03 09:15:00")[:40])):
            with self.subTest(name=name):
                self.assertIsNone(ordnung.exif_datum(self.datei("Pictures", name, inhalt)))

    def test_spotlight_fuer_heic_und_dateidatum_als_letztes(self):
        heic = self.datei("Pictures", "IMG_0001.HEIC", b"heic")
        png = self.datei("Pictures", "skizze.png", b"png")
        self.spotlight({"IMG_0001.HEIC": "2026-11-05 07:30:00 +0000"})
        liste, _, _ = ordnung.dateien(os.path.join(self.heim, "Pictures"))
        daten = ordnung.daten_bestimmen(liste, fotos=True)
        self.assertEqual(daten[heic][1], "Aufnahme")
        self.assertEqual(daten[heic][0].date().isoformat(), "2026-11-05")
        self.assertEqual(daten[png][1], "Dateidatum")


class MacFeinheitenTest(OrdnungBasis):
    """Was die Recherche zum Mac ergeben hat (siehe docs/SELBSTPRUEFUNG.md, Stufe 15)."""

    def test_spotlight_ohne_kameradaten_ist_nur_ein_dateidatum(self):
        """Spotlight trägt ohne EXIF still das Erstelldatum der Datei als „Inhalt erstellt“ ein - das ist keine Aufnahme."""
        zeitpunkt = int(time.time()) - 5 * 86400
        bild = self.datei("Pictures", "Bildschirmfoto.png", b"png", alter=zeitpunkt)
        heic = self.datei("Pictures", "IMG_0002.HEIC", b"heic", alter=zeitpunkt)
        self.spotlight({"Bildschirmfoto.png": datetime.datetime.fromtimestamp(zeitpunkt, datetime.timezone.utc)
                        .strftime("%Y-%m-%d %H:%M:%S +0000"), "IMG_0002.HEIC": "2026-10-01 07:30:00 +0000"})
        daten = ordnung.daten_bestimmen(ordnung.dateien(os.path.join(self.heim, "Pictures"))[0], fotos=True)
        self.assertEqual(daten[bild][1], "Dateidatum")
        self.assertEqual(daten[heic][1], "Aufnahme")

    def test_spotlight_ausgabe_mit_abschliessendem_nul(self):
        os.environ["FAKE_MDLS_ENDE"] = "1"
        a, b = self.datei("Pictures", "A.HEIC", b"a"), self.datei("Pictures", "B.HEIC", b"b")
        self.spotlight({"A.HEIC": "2026-10-01 07:30:00 +0000", "B.HEIC": "2026-10-02 07:30:00 +0000"})
        daten = ordnung.spotlight_daten([a, b])
        self.assertEqual((daten[a].day, daten[b].day), (1, 2))

    def test_unlesbare_datei_verschiebt_keine_daten(self):
        """Fehlt mitten in der Sammelabfrage ein Wert, darf kein Datum bei der falschen Datei landen."""
        a, b, c = (self.datei("Pictures", n, n.encode()) for n in ("A.HEIC", "B.HEIC", "C.HEIC"))
        self.spotlight({"A.HEIC": "2026-10-01 07:30:00 +0000", "B.HEIC": "FEHLT", "C.HEIC": "2026-10-03 07:30:00 +0000"})
        daten = ordnung.spotlight_daten([a, b, c])
        self.assertEqual(daten[a].day, 1)
        self.assertEqual(daten[c].day, 3)
        self.assertNotIn(b, daten)

    def test_video_aufnahmedatum_aus_dem_filmkopf(self):
        sekunden = qt_sekunden(2026, 11, 3, 8, 15)
        erwartet = datetime.datetime(2026, 11, 3, 8, 15, tzinfo=datetime.timezone.utc).astimezone().replace(tzinfo=None)
        for name, inhalt in (("mvhd.mov", video(mvhd=sekunden)), ("lang.mov", video(mvhd=sekunden, version=1))):
            with self.subTest(name=name):
                self.assertEqual(ordnung.video_datum(self.datei("Pictures", name, inhalt)), erwartet)
        # iPhone: Aufnahmezeit mit Zeitzone hat Vorrang (bleibt beim Kürzen/Bearbeiten erhalten, mvhd nicht)
        for mp4 in (False, True):
            with self.subTest(mp4=mp4):
                pfad = self.datei("Pictures", "iphone%d.mov" % mp4, video(mvhd=qt_sekunden(2026, 11, 9, 12, 0),
                                                                          apple="2026-11-03T09:15:22+0100", mp4_meta=mp4))
                self.assertEqual(ordnung.video_datum(pfad), datetime.datetime(2026, 11, 3, 9, 15, 22))

    def test_video_ohne_oder_mit_kaputtem_kopf(self):
        kaputt = video(mvhd=qt_sekunden(2026, 11, 3, 8, 15))
        for name, inhalt in (("null.mov", video(mvhd=0)), ("ohne.mov", video()), ("leer.mov", b""),
                             ("abgeschnitten.mov", kaputt[:-40]), ("text.mp4", b"kein film" * 10),
                             ("riesig.mov", struct.pack(">I", 1) + b"mdat" + struct.pack(">Q", 10 ** 12))):
            with self.subTest(name=name):
                self.assertIsNone(ordnung.video_datum(self.datei("Pictures", name, inhalt)))

    def test_live_photo_bleibt_zusammen(self):
        self.datei("Pictures", "IMG_0007.HEIC", b"heic")
        self.datei("Pictures", "IMG_0007.MOV", video(mvhd=0))
        self.datei("Pictures", "IMG_0007.AAE", b"<plist/>")
        self.datei("Pictures", "IMG_0008.MOV", video(apple="2026-11-04T10:00:00+0100"))
        self.spotlight({"IMG_0007.HEIC": "2026-11-03 07:30:00 +0000"})
        e = self.aktion("ordnen", ordner="bilder", art="fotos_nach_datum")
        vorschau = self.sp.freigabe(e["freigabe_id"])["vorschau"]
        self.assertIn("→ Sortiert/2026/2026-11-03/ (3)", vorschau)
        self.assertIn("IMG_0007.AAE  (Aufnahme laut IMG_0007.HEIC 03.11.2026)", vorschau)
        self.assertIn("IMG_0008.MOV  (Aufnahme 04.11.2026)", vorschau)
        self.freigeben(e)
        for name in ("IMG_0007.HEIC", "IMG_0007.MOV", "IMG_0007.AAE"):
            self.assertTrue(self.da("Pictures", "Sortiert", "2026", "2026-11-03", name), name)

    def test_nur_fotos_teilen_ein_aufnahmedatum(self):
        """Gleicher Name heißt nicht zusammengehörig: das Angebot behält sein eigenes Datum (wichtig für von/bis)."""
        pdf = self.datei("Downloads", "Angebot.pdf", b"%PDF")
        jpg = self.datei("Downloads", "Angebot.jpg", jpeg_mit_datum("2026:01:15 10:00:00"))
        daten = ordnung.daten_bestimmen(ordnung.dateien(os.path.join(self.heim, "Downloads"))[0], fotos=True)
        self.assertEqual(daten[jpg][1], "Aufnahme")
        self.assertEqual(daten[pdf][1], "Dateidatum")
        self.assertNotEqual(daten[pdf][0].date(), daten[jpg][0].date())

    def test_offene_dokumente_und_laufende_downloads_bleiben_liegen(self):
        self.datei("Downloads", "~$Angebot Berger.docx")
        self.datei("Downloads", "Plan.pdf", b"")
        self.datei("Downloads", "Plan.pdf.part", b"teil")
        self.datei("Downloads", "Rechnung.pdf")
        text = self.aktion("ordner_ansehen", ordner="downloads")["text"]
        self.assertIn("~$Angebot Berger.docx (Sperrdatei - das Dokument ist gerade geöffnet)", text)
        self.assertIn("Plan.pdf (Download läuft noch)", text)
        vorschau = self.sp.freigabe(self.aktion("ordnen", ordner="downloads", art="nach_art")["freigabe_id"])["vorschau"]
        self.assertIn("Rechnung.pdf", vorschau)
        self.assertNotIn("   Plan.pdf", vorschau)

    def test_gleiche_namen_wie_der_mac_sie_sieht(self):
        """Der Mac unterscheidet weder Groß/klein noch zwei Schreibweisen desselben Umlauts - Linux schon."""
        self.datei("Downloads", "Foto.JPG", b"eins")
        self.datei("Downloads", "foto.jpg", b"zwei")
        self.datei("Downloads", unicodedata.normalize("NFC", "Müller.pdf"), b"drei")
        self.datei("Downloads", unicodedata.normalize("NFD", "Müller.pdf"), b"vier")
        plan = ordnung.ordnen_planen(self.konfig, "downloads", "nach_art")
        ziele = [unicodedata.normalize("NFC", os.path.basename(s["nach"])).casefold() for s in plan["schritte"]]
        self.assertEqual(len(set(ziele)), 4, ziele)
        vorher = self.bestand("Downloads")
        self.freigeben(self.aktion("ordnen", ordner="downloads", art="nach_art"))
        self.assertEqual(self.bestand("Downloads"), vorher)  # nichts verloren, nichts verändert

    def test_ziel_kurz_belegt_neuer_versuch_statt_fehler(self):
        self.datei("Downloads", "a.pdf", b"meine")
        e = self.aktion("ordnen", ordner="downloads", art="nach_art")
        echt, versuche = ordnung._verschieben_ohne_ueberschreiben, []

        def einmal_belegt(von, nach):
            versuche.append(nach)
            if len(versuche) == 1:
                raise FileExistsError(nach)
            return echt(von, nach)

        with mock.patch.object(ordnung, "_verschieben_ohne_ueberschreiben", einmal_belegt):
            self.freigeben(e)
        self.assertEqual(len(versuche), 2)
        self.assertTrue(self.da("Downloads", "Sortiert", "PDFs", "a.pdf"))
        self.assertFalse(self.da("Downloads", "a.pdf"))


class AnsehenTest(OrdnungBasis):
    def test_uebersicht_und_was_liegen_bleibt(self):
        self.datei("Downloads", "Rechnung_Klein.pdf")
        self.datei("Downloads", "Angebot.docx")
        self.datei("Downloads", "foto.jpg")
        self.datei("Downloads", "film.mp4.crdownload")
        self.datei("Downloads", "neu.pdf", alter=time.time())
        self.datei("Downloads", ".versteckt.pdf")
        os.makedirs(os.path.join(self.heim, "Downloads", "Alt"))
        e = self.aktion("ordner_ansehen", ordner="downloads")
        self.assertEqual(e["status"], "ausgefuehrt", e)
        for teil in ("3 Datei(en)", "1 Unterordner", "PDFs 1", "Rechnung_Klein.pdf", "Unterordner: Alt",
                     "film.mp4.crdownload (Download läuft noch)", "neu.pdf (gerade erst geändert)"):
            self.assertIn(teil, e["text"])
        self.assertNotIn("versteckt", e["text"])

    def test_nur_verwaltete_ordner_und_keine_pakete(self):
        os.makedirs(os.path.join(self.heim, "Pictures", "Photos Library.photoslibrary"))
        self.assertEqual(self.aktion("ordner_ansehen", ordner="bilder", unterordner="Photos Library.photoslibrary")["status"],
                         "fehler")
        self.assertEqual(self.aktion("ordner_ansehen", ordner="bilder", unterordner="../Documents")["status"], "fehler")
        self.konfig.aktualisieren({"verwaltete_ordner": ["downloads"]})
        e = self.aktion("ordner_ansehen", ordner="dokumente")
        self.assertEqual(e["status"], "fehler")
        self.assertIn("verwaltet JARVIS nicht", e["text"])
        self.assertEqual(self.aktion("ordner_ansehen", ordner="systemordner")["status"], "ungueltig")


class OrdnenTest(OrdnungBasis):
    def test_nach_art_erst_freigabe_dann_genau_der_plan(self):
        for name in ("Rechnung.pdf", "Vertrag.pdf", "Liste.xlsx", "Bild.HEIC", "setup.dmg", "notiz"):
            self.datei("Downloads", name, name)
        vorher = self.bestand("Downloads")
        e = self.aktion("ordnen", ordner="downloads", art="nach_art")
        self.assertEqual(e["status"], "freigabe_offen")
        self.assertTrue(self.da("Downloads", "Rechnung.pdf"))  # vor der Freigabe bewegt sich nichts
        vorschau = self.sp.freigabe(e["freigabe_id"])["vorschau"]
        for teil in ("6 Datei(en) werden VERSCHOBEN", "→ Sortiert/PDFs/ (2)", "Rechnung.pdf", "Vertrag.pdf",
                     "→ Sortiert/Tabellen/ (1)", "→ Sortiert/Installationsdateien/ (1)", "→ Sortiert/Sonstiges/ (1)",
                     "Nichts wird gelöscht oder überschrieben", "rückgängig machbar"):
            self.assertIn(teil, vorschau)
        self.assertLess(vorschau.index("Sortiert/Bilder/"), vorschau.index("Sortiert/PDFs/"))  # Zielordner alphabetisch
        antwort = self.freigeben(e)
        self.assertTrue(antwort["ok"])
        self.assertTrue(self.da("Downloads", "Sortiert", "PDFs", "Rechnung.pdf"))
        self.assertTrue(self.da("Downloads", "Sortiert", "Bilder", "Bild.HEIC"))
        self.assertFalse(self.da("Downloads", "Rechnung.pdf"))
        self.assertEqual(self.bestand("Downloads"), vorher)  # keine Datei verloren, keine verändert
        self.assertIn("rueckgaengig", antwort["ergebnis"]["text"])

    def test_nie_ueberschreiben(self):
        self.datei("Downloads", "Sortiert/PDFs/Rechnung.pdf", b"alte Rechnung")
        self.datei("Downloads", "Rechnung.pdf", b"neue Rechnung")
        e = self.aktion("ordnen", ordner="downloads", art="nach_art")
        self.assertIn("Rechnung.pdf → Rechnung (2).pdf", self.sp.freigabe(e["freigabe_id"])["vorschau"])
        self.freigeben(e)
        with open(os.path.join(self.heim, "Downloads", "Sortiert", "PDFs", "Rechnung.pdf"), "rb") as f:
            self.assertEqual(f.read(), b"alte Rechnung")
        with open(os.path.join(self.heim, "Downloads", "Sortiert", "PDFs", "Rechnung (2).pdf"), "rb") as f:
            self.assertEqual(f.read(), b"neue Rechnung")

    def test_ziel_inzwischen_belegt_wird_nicht_ueberschrieben(self):
        self.datei("Downloads", "a.pdf", b"meine")
        e = self.aktion("ordnen", ordner="downloads", art="nach_art")
        self.datei("Downloads", "Sortiert/PDFs/a.pdf", b"dazwischen")  # nach dem Plan, vor der Freigabe
        self.freigeben(e)
        with open(os.path.join(self.heim, "Downloads", "Sortiert", "PDFs", "a.pdf"), "rb") as f:
            self.assertEqual(f.read(), b"dazwischen")
        self.assertTrue(self.da("Downloads", "Sortiert", "PDFs", "a (2).pdf"))

    def test_seit_dem_plan_geaenderte_datei_bleibt_liegen(self):
        self.datei("Downloads", "a.pdf", b"eins")
        self.datei("Downloads", "b.pdf", b"zwei")
        e = self.aktion("ordnen", ordner="downloads", art="nach_art")
        self.datei("Downloads", "b.pdf", "zwei, aber länger")
        antwort = self.freigeben(e)
        self.assertTrue(self.da("Downloads", "Sortiert", "PDFs", "a.pdf"))
        self.assertTrue(self.da("Downloads", "b.pdf"))
        self.assertIn("verändert", antwort["ergebnis"]["text"])

    def test_fotos_nach_aufnahmetag(self):
        self.datei("Pictures", "IMG_1.jpg", jpeg_mit_datum("2026:11:03 09:15:00"))
        self.datei("Pictures", "IMG_2.HEIC", b"heic")
        self.datei("Pictures", "Bericht.pdf")
        self.spotlight({"IMG_2.HEIC": "2026-11-05 07:30:00 +0000"})
        e = self.aktion("ordnen", ordner="bilder", art="fotos_nach_datum", ziel="Fotos nach Datum")
        vorschau = self.sp.freigabe(e["freigabe_id"])["vorschau"]
        self.assertIn("→ Fotos nach Datum/2026/2026-11-03/ (1)", vorschau)
        self.assertIn("Aufnahme 03.11.2026", vorschau)
        self.assertNotIn("Bericht.pdf", vorschau)  # nur Fotos
        self.freigeben(e)
        self.assertTrue(self.da("Pictures", "Fotos nach Datum", "2026", "2026-11-03", "IMG_1.jpg"))
        self.assertTrue(self.da("Pictures", "Fotos nach Datum", "2026", "2026-11-05", "IMG_2.HEIC"))
        self.assertTrue(self.da("Pictures", "Bericht.pdf"))

    def test_zu_viele_dateien_auf_einmal(self):
        for i in range(4):
            self.datei("Downloads", "d%d.pdf" % i)
        alt, ordnung.MAX_PLAN = ordnung.MAX_PLAN, 3
        try:
            e = self.aktion("ordnen", ordner="downloads", art="nach_art")
        finally:
            ordnung.MAX_PLAN = alt
        self.assertEqual(e["status"], "ungueltig")
        self.assertIn("kleiner fassen", e["text"])

    def test_nichts_zu_tun_und_nur_im_gespraech(self):
        self.assertEqual(self.aktion("ordnen", ordner="downloads", art="nach_art")["status"], "ungueltig")
        self.datei("Downloads", "a.pdf")
        auftrag = self.ctx(quelle="auftrag")
        self.assertEqual(self.aktion("ordnen", ordner="downloads", art="nach_art", ctx=auftrag)["status"], "gesperrt")


class VerschiebenUndZurueckTest(OrdnungBasis):
    def setUp(self):
        super().setUp()
        for tag in (2, 3, 4, 6):
            self.datei("Pictures", "IMG_%d.jpg" % tag, jpeg_mit_datum("2026:11:%02d 10:00:00" % tag))

    def test_baustelle_vorher_nach_zeitraum(self):
        e = self.aktion("dateien_verschieben", ordner="bilder", ziel="Baustellen/Berger/1 vorher", von="2026-11-03",
                        bis="4.11.2026")
        vorschau = self.sp.freigabe(e["freigabe_id"])["vorschau"]
        self.assertIn("2 Datei(en)", vorschau)
        self.assertIn("vom 03.11.2026 bis 04.11.2026", vorschau)
        self.freigeben(e)
        self.assertTrue(self.da("Pictures", "Baustellen", "Berger", "1 vorher", "IMG_3.jpg"))
        self.assertTrue(self.da("Pictures", "Baustellen", "Berger", "1 vorher", "IMG_4.jpg"))
        self.assertTrue(self.da("Pictures", "IMG_2.jpg"))
        self.assertTrue(self.da("Pictures", "IMG_6.jpg"))

    def test_muster_und_falsche_angaben(self):
        faelle = [
            ({"ziel": "Berger"}, "Zeitraum"),  # ohne Auswahl wäre es der ganze Ordner
            ({"ziel": "../Documents", "muster": "*"}, ".."),
            ({"ziel": "Photos Library.photoslibrary/x", "muster": "*"}, "Fotos-Mediathek"),
            ({"ziel": ".geheim", "muster": "*"}, "versteckt"),
            ({"ziel": "B", "von": "5.11.2026", "bis": "3.11.2026"}, "von"),
            ({"ziel": "B", "von": "31.02.2026"}, "gibt es nicht"),
        ]
        for roh, erwartet in faelle:
            with self.subTest(roh=roh):
                e = self.aktion("dateien_verschieben", ordner="bilder", **roh)
                self.assertEqual(e["status"], "ungueltig", e)
                self.assertIn(erwartet, e["text"])
        e = self.aktion("dateien_verschieben", ordner="bilder", ziel="Auswahl", muster="img_6*")
        self.assertIn("IMG_6.jpg", self.sp.freigabe(e["freigabe_id"])["vorschau"])

    def test_rueckgaengig_bringt_alles_zurueck(self):
        vorher = self.bestand("Pictures")
        self.freigeben(self.aktion("ordnen", ordner="bilder", art="fotos_nach_datum", ziel="Sortiert"))
        self.assertFalse(self.da("Pictures", "IMG_2.jpg"))
        self.datei("Pictures", "IMG_2.jpg", b"neues Foto mit gleichem Namen")  # der alte Platz ist inzwischen belegt
        e = self.aktion("rueckgaengig")
        self.assertIn("werden ZURÜCKGESCHOBEN", self.sp.freigabe(e["freigabe_id"])["vorschau"])
        self.freigeben(e)
        for tag in (3, 4, 6):
            self.assertTrue(self.da("Pictures", "IMG_%d.jpg" % tag))
        self.assertTrue(self.da("Pictures", "IMG_2 (2).jpg"))  # zurück, ohne das neue Foto zu überschreiben
        nachher = self.bestand("Pictures")
        for h, anzahl in vorher.items():
            self.assertEqual(nachher.get(h), anzahl)  # jedes ursprüngliche Foto ist noch da, unverändert
        self.assertEqual(sum(nachher.values()), sum(vorher.values()) + 1)  # nichts verloren, nur das neue Foto dazu

    def test_rueckgaengig_ohne_vorgeschichte(self):
        e = self.aktion("rueckgaengig")
        self.assertEqual(e["status"], "ungueltig")
        self.assertIn("nichts", e["text"])


class OrdnungImGehirnTest(OrdnungBasis):
    def test_baustein_und_ehrlichkeit(self):
        self.assertIn("ordnung", gehirn.bausteine_waehlen("Räum meine Downloads auf"))
        self.assertIn("ordnung", gehirn.bausteine_waehlen("Sortier die Baustellenfotos nach vorher und nachher"))
        prompt = self.agent.system_prompt(frage="Räum meine Downloads auf")
        self.assertIn("DATEIEN UND FOTOS ORDNEN", prompt)
        self.assertIn("Die Bilder selbst siehst du nicht", prompt.replace("die Bilder selbst siehst du nicht",
                                                                          "Die Bilder selbst siehst du nicht"))
        self.assertEqual(gehirn.ehrlichkeit_pruefen("Ich habe deine Downloads aufgeräumt.", set(), "Räum auf")[1],
                         ["verschieben"])
        self.assertEqual(gehirn.ehrlichkeit_pruefen("Ich habe deine Downloads aufgeräumt.", {"ordnen"}, "Räum auf")[1], [])

    def test_vom_gespraech_bis_zur_freigabe(self):
        self.datei("Downloads", "Rechnung.pdf")
        self.chat_antworten('Ich sehe nach. <aktion werkzeug="ordner_ansehen" ordner="downloads"/>',
                            'Ich schlage vor, nach Art zu sortieren. <aktion werkzeug="ordnen" ordner="downloads" art="nach_art"/>')
        code, antwort = self.agent.chat("Räum meine Downloads auf")
        self.assertEqual(code, 200)
        self.assertEqual(len(antwort["freigaben"]), 1)
        self.assertTrue(self.da("Downloads", "Rechnung.pdf"))  # ohne Ja bewegt sich nichts
        self.assertIn("ordnung", antwort["bausteine"])
