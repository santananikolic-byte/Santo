#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Tests für Präsentationen (jarvis_core/praesentation.py) und die Werkzeuge praesentation_erstellen, datei_oeffnen.

    python3 -m unittest tests.test_praesentation -v
"""

import base64
import os
import re
import struct

from tests.hilfen import WURZEL, ausfuehrbar
from tests.test_ordnung import GPS_BREITE, OrdnungBasis, jpeg_mit_datum, jpeg_mit_gps

from jarvis_core import gehirn, praesentation  # noqa: E402

ERSATZ_SIPS = os.path.join(WURZEL, "tests", "ersatz_sips.py")

TEXT = """# Firmenvorstellung Bau & Reinigung
Zuverlässig in Leverkusen und ganz NRW

## Ihr Bedarf
- Saubere Treppenhäuser, jede Woche
- Ein fester Ansprechpartner

## Referenz: Treppenhaus Berger
Bild: bilder:Baustellen/Berger/vorher.jpg | Vorher
Bild: bilder:Baustellen/Berger/nachher.HEIC | Nachher

## Kontakt
[Telefon] · [E-Mail]
"""


class PraesentationBasis(OrdnungBasis):
    def setUp(self):
        super().setUp()
        os.chmod(ERSATZ_SIPS, 0o755)  # noqa: S103 - Ersatzprogramm muss ausführbar sein
        os.environ["JARVIS_SIPS"] = ERSATZ_SIPS
        self.datei("Pictures", "Baustellen/Berger/vorher.jpg", jpeg_mit_datum("2026:11:03 09:00:00"))
        self.datei("Pictures", "Baustellen/Berger/nachher.HEIC", b"heic-daten")
        self.oeffnen_log = os.path.join(self.ordner, "open.log")
        self.open_ersatz = os.path.join(self.ordner, "open-ersatz")
        ausfuehrbar(self.open_ersatz, "#!/bin/sh\necho \"$@\" >> '%s'\n" % self.oeffnen_log)

    def geoeffnet(self):
        try:
            with open(self.oeffnen_log, encoding="utf-8") as f:
                return f.read()
        except OSError:
            return ""


class LesenUndBauenTest(PraesentationBasis):
    def test_lesen(self):
        d = praesentation.lesen(TEXT)
        self.assertEqual(d["titel"], "Firmenvorstellung Bau & Reinigung")
        self.assertEqual(d["untertitel"], "Zuverlässig in Leverkusen und ganz NRW")
        self.assertEqual([f["titel"] for f in d["folien"]], ["Ihr Bedarf", "Referenz: Treppenhaus Berger", "Kontakt"])
        self.assertEqual(d["folien"][0]["punkte"], ["Saubere Treppenhäuser, jede Woche", "Ein fester Ansprechpartner"])
        self.assertEqual(d["folien"][1]["bilder"][1], ("bilder:Baustellen/Berger/nachher.HEIC", "Nachher"))
        for kaputt, erwartet in (("## Nur Folie", "Titel"), ("# Nur Titel", "Folien"),
                                 ("# T\n" + "## F\n" * (praesentation.MAX_FOLIEN + 1), "Höchstens")):
            with self.subTest(kaputt=kaputt[:20]), self.assertRaises(praesentation.PraesentationFehler) as ctx:
                praesentation.lesen(kaputt)
            self.assertIn(erwartet, str(ctx.exception))

    def test_html_offline_maskiert_druckbar(self):
        seite, folien, bilder, hinweise = praesentation.bauen(
            self.konfig, TEXT + "\n## Böse\n- <script>alert(1)</script> & \"x\"", fusszeile="Firma <b>X</b>")
        self.assertEqual(folien, 5)  # Titelfolie + 4
        self.assertEqual(len(re.findall(r'<section class="folie', seite)), 5)
        self.assertIn("&lt;script&gt;alert(1)&lt;/script&gt; &amp; &quot;x&quot;", seite)
        self.assertNotIn("<script>alert", seite)
        self.assertIn("Firma &lt;b&gt;X&lt;/b&gt;", seite)
        self.assertNotRegex(seite, r"https?://")  # läuft ohne Internet
        self.assertIn("@media print", seite)
        self.assertIn("ArrowRight", seite)
        self.assertIn("hashchange", seite)  # Sprung über die Adresse (#3) - beim Sichtprüfen als Fehler aufgefallen
        self.assertIn("<title>Firmenvorstellung Bau &amp; Reinigung</title>", seite)
        self.assertEqual((bilder, hinweise), (2, []))

    def test_bilder_eingebettet_heic_umgewandelt(self):
        seite, _, bilder, _ = praesentation.bauen(self.konfig, TEXT)
        self.assertEqual(bilder, 2)
        daten = [base64.b64decode(b) for b in re.findall(r"data:image/jpeg;base64,([A-Za-z0-9+/=]+)", seite)]
        self.assertTrue(any(b"UMGEWANDELT:nachher.HEIC" in d for d in daten))  # HEIC über sips
        self.assertIn("<figcaption>Vorher</figcaption>", seite)

    def test_ohne_sips_heic_mit_ehrlichem_hinweis(self):
        os.environ["JARVIS_SIPS"] = os.path.join(self.ordner, "gibtsnicht")
        _, _, bilder, hinweise = praesentation.bauen(self.konfig, TEXT)
        self.assertEqual(bilder, 1)  # das JPEG geht direkt
        self.assertTrue(any("nur auf dem Mac" in h for h in hinweise))

    def test_unsichere_oder_falsche_bilder_werden_weggelassen(self):
        self.datei("Documents", "geheim.jpg", jpeg_mit_datum("2026:11:03 09:00:00"))
        self.datei("Pictures", "liste.pdf", b"%PDF")
        os.makedirs(os.path.join(self.heim, "Pictures", "Photos Library.photoslibrary"))
        self.datei("Pictures", "Photos Library.photoslibrary/x.jpg", b"\xff\xd8\xff\xd9")
        text = ("# T\n## F\nBild: bilder:../Documents/geheim.jpg\nBild: bilder:liste.pdf\n"
                "## G\nBild: bilder:Photos Library.photoslibrary/x.jpg\nBild: /etc/passwd\n"
                "## H\nBild: bilder:Baustellen/Berger/vorher.jpg\nBild: bilder:Baustellen/Berger/vorher.jpg\n"
                "Bild: bilder:Baustellen/Berger/vorher.jpg\n")
        seite, _, bilder, hinweise = praesentation.bauen(self.konfig, text)
        self.assertEqual(bilder, 2)  # nur die zwei erlaubten auf Folie H
        alles = " ".join(hinweise)
        for teil in ("..", "kein Bild", "Fotos-Mediathek", "höchstens 2 Bilder"):
            self.assertIn(teil, alles)
        self.assertEqual(len(hinweise), 5)
        self.assertNotIn("root:", seite)

    def test_farbe_und_dateiname(self):
        with self.assertRaises(praesentation.PraesentationFehler):
            praesentation.bauen(self.konfig, TEXT, akzent="red;}body{display:none")
        self.assertEqual(praesentation.dateiname("Firmenvorstellung Müller & Söhne!"), "Firmenvorstellung-Mueller-Soehne")
        self.assertEqual(praesentation.dateiname("???"), "Praesentation")


class StandortTest(PraesentationBasis):
    """Handyfotos verraten den Aufnahmeort. In einer Präsentation für Kunden hat er nichts zu suchen."""

    def test_gps_genullt_xmp_weg_datum_und_ausrichtung_bleiben(self):
        for reihenfolge in ("II", "MM"):
            with self.subTest(reihenfolge=reihenfolge):
                e = "<" if reihenfolge == "II" else ">"
                foto = jpeg_mit_gps(reihenfolge=reihenfolge)
                self.assertIn(GPS_BREITE(e), foto)
                neu, entfernt = praesentation.ohne_standort(foto)
                self.assertTrue(entfernt)
                self.assertNotIn(GPS_BREITE(e), neu)
                self.assertNotIn(b"N\x00\x00\x00", neu[neu.index(b"Exif"):])  # Nord/Süd-Angabe weg
                self.assertNotIn(b"GPSLatitude", neu)  # XMP-Block weg
                self.assertIn(struct.pack(e + "HHI", 0x0112, 3, 1) + struct.pack(e + "HH", 6, 0), neu)  # Ausrichtung
                self.assertEqual(ordnung_datum(neu), "2026-11-03 09:15")
                self.assertTrue(neu.endswith(b"\xff\xda\x00\x02BILDDATEN\xff\xd9"))  # Bilddaten unverändert
                self.assertEqual(praesentation.ohne_standort(neu), (neu, False))  # zweimal ändert nichts mehr

    def test_ohne_ort_bleibt_alles_wie_es_ist(self):
        for daten in (jpeg_mit_datum("2026:11:03 09:00:00"), b"\x89PNG\r\n\x1a\n", b"", b"\xff\xd8\xff\xe1\xff\xff"):
            with self.subTest(daten=daten[:8]):
                self.assertEqual(praesentation.ohne_standort(daten), (daten, False))

    def test_praesentation_enthaelt_keinen_ort(self):
        self.datei("Pictures", "Baustellen/Berger/vorher.jpg", jpeg_mit_gps())
        for sips in (True, False):  # umgewandelt über sips (behält GPS!) und direkt eingebettet
            with self.subTest(sips=sips):
                if not sips:
                    os.environ["JARVIS_SIPS"] = os.path.join(self.ordner, "gibtsnicht")
                seite, _, bilder, hinweise = praesentation.bauen(self.konfig, TEXT)
                daten = [base64.b64decode(b) for b in re.findall(r"data:image/jpeg;base64,([A-Za-z0-9+/=]+)", seite)]
                self.assertTrue(daten)
                for bild in daten:
                    self.assertNotIn(GPS_BREITE("<"), bild)
                    self.assertNotIn(b"GPSLatitude", bild)
                self.assertTrue(any("Aufnahmeort (GPS) entfernt" in h for h in hinweise), hinweise)

    def test_kleine_bilder_werden_nicht_vergroessert(self):
        pfad, endung = praesentation.bild_pfad(self.konfig, "bilder:Baustellen/Berger/nachher.HEIC")
        self.assertIn(b":verkleinert", praesentation.bild_daten(pfad, endung)[1])  # Handyfoto 4032 x 3024
        os.environ["FAKE_SIPS_MASSE"] = "800x600"
        self.assertIn(b":originalgroesse", praesentation.bild_daten(pfad, endung)[1])


def ordnung_datum(jpeg):
    from jarvis_core import ordnung
    return ordnung._tiff_datum(ordnung._exif_block(jpeg)).strftime("%Y-%m-%d %H:%M")


class WerkzeugTest(PraesentationBasis):
    def test_erstellen_ohne_freigabe_und_nie_ueberschreiben(self):
        e = self.aktion("praesentation_erstellen", koerper=TEXT)
        self.assertEqual(e["status"], "ausgefuehrt", e)
        self.assertIn("Firmenvorstellung-Bau-Reinigung.html", e["text"])
        self.assertIn("4 Folien, 2 Bilder", e["text"])
        pfad = os.path.join(self.werkstatt, "praesentationen", "Firmenvorstellung-Bau-Reinigung.html")
        self.assertTrue(os.path.isfile(pfad))
        zweite = self.aktion("praesentation_erstellen", koerper=TEXT)
        self.assertIn("Firmenvorstellung-Bau-Reinigung (2).html", zweite["text"])

    def test_nach_aussenquelle_mit_freigabe(self):
        ctx = self.ctx()
        self.aktion("ordner_ansehen", ordner="bilder", ctx=ctx)  # Dateinamen sind Außenquelle
        e = self.aktion("praesentation_erstellen", koerper=TEXT, ctx=ctx)
        self.assertEqual(e["status"], "freigabe_offen")
        self.assertIn("Referenz: Treppenhaus Berger", self.sp.freigabe(e["freigabe_id"])["vorschau"])

    def test_oeffnen_nur_dokumente_und_eigene_webseiten(self):
        os.environ["JARVIS_OPEN"] = self.open_ersatz
        self.aktion("praesentation_erstellen", koerper=TEXT)
        self.assertEqual(self.aktion("datei_oeffnen", pfad="praesentationen/Firmenvorstellung-Bau-Reinigung.html")["status"],
                         "ausgefuehrt")
        self.assertIn("Firmenvorstellung-Bau-Reinigung.html", self.geoeffnet())
        self.datei("Downloads", "Rechnung.pdf")
        self.datei("Downloads", "seite.html")
        self.datei("Downloads", "start.command", "#!/bin/sh\nrm -rf ~\n")
        self.assertEqual(self.aktion("datei_oeffnen", pfad="downloads:Rechnung.pdf")["status"], "ausgefuehrt")
        for verboten in ("downloads:seite.html", "downloads:start.command", "downloads:../Documents/x.pdf"):
            with self.subTest(verboten=verboten):
                self.assertEqual(self.aktion("datei_oeffnen", pfad=verboten)["status"], "fehler")
        self.assertNotIn("start.command", self.geoeffnet())
        self.assertNotIn("seite.html", self.geoeffnet())

    def test_oeffnen_ohne_mac_ehrlich(self):
        os.environ.pop("JARVIS_OPEN", None)
        self.datei("Downloads", "Rechnung.pdf")
        e = self.aktion("datei_oeffnen", pfad="downloads:Rechnung.pdf")
        if os.uname().sysname != "Darwin":
            self.assertEqual(e["status"], "fehler")
            self.assertIn("nur auf dem Mac", e["text"])

    def test_im_gespraech(self):
        self.chat_antworten("Ich baue die Präsentation. <aktion werkzeug=\"praesentation_erstellen\">%s</aktion>" % TEXT)
        code, antwort = self.agent.chat("Erstell mir eine Firmenvorstellung mit den Berger-Fotos")
        self.assertEqual(code, 200)
        self.assertIn("praesentation", antwort["bausteine"])
        self.assertEqual(antwort["aktionen"][0]["status"], "ausgefuehrt")
        self.assertIn("PRÄSENTATIONEN", self.aufrufe()[-1]["system"])
        self.assertIn("Nur echte Angaben", gehirn.baustein_text("praesentation"))
