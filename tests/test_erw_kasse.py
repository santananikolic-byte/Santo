# -*- coding: utf-8 -*-
"""Erweiterung Kasse: Beträge in Cent, Monatsfilter, Vormonat, Rechnungsbuchungen, Löschen mit Freigabe, CSV."""

import csv
import datetime
import io
import os
import unittest
from unittest import mock

from tests.hilfen import AgentBasis

from jarvis_core import betrieb
from jarvis_core.erweiterungen import kasse


def buchen(sp, datum, art, cent, kategorie=None, text=None, **felder):
    return betrieb.BUCHUNGEN.anlegen(sp, datum=datum, art=art, betrag_cent=cent, kategorie=kategorie, text=text, **felder)


class CsvTest(unittest.TestCase):
    def test_zellen_gegen_injection_gesichert(self):
        for gefaehrlich in ("=1+1", "+49 123", "-2+3", "@SUMME(A1)", "  =HYPERLINK(\"x\")", "\t=1", "\r=1"):
            zelle = kasse.csv_zelle(gefaehrlich)
            self.assertTrue(zelle.lstrip('"').startswith("'"), gefaehrlich)
        self.assertEqual(kasse.csv_zelle("Diesel"), "Diesel")
        self.assertEqual(kasse.csv_zelle("a;b"), '"a;b"')
        self.assertEqual(kasse.csv_zelle('sagt "hallo"'), '"sagt ""hallo"""')
        self.assertEqual(kasse.csv_zelle(None), "")
        self.assertEqual(kasse.csv_zelle(12), "12")

    def test_monat_und_kategorie(self):
        self.assertEqual(kasse._monat("2026-3"), "2026-03")
        self.assertEqual(kasse._monat("11.2026"), "2026-11")
        self.assertEqual(kasse._vormonat("2026-01"), "2025-12")
        for falsch in ("2026-13", "november", "2026-00", "26-11"):
            with self.assertRaises(kasse.WerkzeugFehler, msg=falsch):
                kasse._monat(falsch)
        self.assertEqual(kasse._kategorie("ausgabe", "buero"), "Büro")
        with self.assertRaises(kasse.WerkzeugFehler):
            kasse._kategorie("ausgabe", "Rechnung")  # Rechnung gibt es nur bei Einnahmen
        with self.assertRaises(kasse.WerkzeugFehler):
            kasse._kategorie("einnahme", "Material")


class KasseTest(AgentBasis):
    def monat(self, versatz=0):
        tag = datetime.date.today().replace(day=15)
        for _ in range(abs(versatz)):
            tag = (tag.replace(day=1) - datetime.timedelta(days=1)).replace(day=15)
        return tag

    def test_erfassen_in_cent(self):
        ergebnis = self.aktion("buchung_erfassen", art="ausgabe", betrag="1.234,56", kategorie="material",
                               text="Farbe", datum="2026-11-03")
        self.assertEqual(ergebnis["status"], "ausgefuehrt", ergebnis)
        zeile = betrieb.BUCHUNGEN.liste(self.sp)[0]
        self.assertEqual((zeile["betrag_cent"], zeile["art"], zeile["kategorie"], zeile["datum"]),
                         (123456, "ausgabe", "Material", "2026-11-03"))
        self.assertIn("1.234,56 €", ergebnis["text"])
        self.assertIn("keine Buchhaltung", ergebnis["text"])
        self.assertIn("GoBD", ergebnis["text"])
        ohne = self.aktion("buchung_erfassen", art="einnahme", betrag="100")
        self.assertIn("daher Sonstiges", ohne["text"])
        self.assertEqual(betrieb.BUCHUNGEN.liste(self.sp)[0]["datum"], datetime.date.today().isoformat())

    def test_falsche_eingaben(self):
        for roh, status in (({"art": "einnahme"}, "ungueltig"), ({"betrag": "5"}, "ungueltig"),
                            ({"art": "spende", "betrag": "5"}, "ungueltig"),
                            ({"art": "ausgabe", "betrag": "abc"}, "fehler"), ({"art": "ausgabe", "betrag": "0"}, "fehler"),
                            ({"art": "ausgabe", "betrag": "-5"}, "fehler"),
                            ({"art": "ausgabe", "betrag": "5", "kategorie": "Urlaub"}, "fehler"),
                            ({"art": "einnahme", "betrag": "5", "kategorie": "Material"}, "fehler"),
                            ({"art": "ausgabe", "betrag": "5", "datum": "31.02.2026"}, "ungueltig"),
                            ({"art": "ausgabe", "betrag": "5", "kundenauftrag": "99"}, "fehler"),
                            ({"art": "ausgabe", "betrag": "5", "beleg": "../geheim.pdf"}, "fehler"),
                            ({"art": "ausgabe", "betrag": "5", "beleg": "gibtesnicht:x.pdf"}, "fehler")):
            self.assertEqual(self.aktion("buchung_erfassen", **roh)["status"], status, roh)
        self.assertEqual(betrieb.BUCHUNGEN.zaehlen(self.sp), 0)

    def test_beleg_und_kundenauftrag_nur_verweis(self):
        self.werkstatt_datei("belege/tanken.pdf", "x")
        auftrag = betrieb.AUFTRAEGE.anlegen(self.sp, titel="Treppenhaus Berger")
        ergebnis = self.aktion("buchung_erfassen", art="ausgabe", betrag="60", kategorie="Fahrzeug",
                               beleg="belege/tanken.pdf", kundenauftrag=str(auftrag))
        self.assertEqual(ergebnis["status"], "ausgefuehrt", ergebnis)
        zeile = betrieb.BUCHUNGEN.liste(self.sp)[0]
        self.assertEqual((zeile["beleg"], zeile["auftrag_id"]), ("belege/tanken.pdf", auftrag))
        fehlt = self.aktion("buchung_erfassen", art="ausgabe", betrag="6", beleg="belege/nichts.pdf")
        self.assertIn("gibt es (noch) nicht", fehlt["text"])
        downloads = os.path.join(self.ordner, "dl")
        os.makedirs(downloads)
        self.konfig.ordner["downloads"] = {"pfad": downloads, "schreiben": False}
        self.assertEqual(self.aktion("buchung_erfassen", art="ausgabe", betrag="7", beleg="downloads:q.pdf")["status"],
                         "ausgefuehrt")

    def test_monatsfilter_summen_und_vormonat(self):
        dieser, vor = self.monat(), self.monat(1)
        buchen(self.sp, dieser.isoformat(), "einnahme", 100000, "Reinigung")
        buchen(self.sp, dieser.isoformat(), "ausgabe", 30000, "Material", "Farbe")
        buchen(self.sp, dieser.isoformat(), "ausgabe", 5050, "Material")
        buchen(self.sp, dieser.isoformat(), "ausgabe", 20000, "Fahrzeug")
        buchen(self.sp, vor.isoformat(), "einnahme", 50000, "Bau")
        buchen(self.sp, vor.isoformat(), "ausgabe", 10000, "Miete")
        ergebnis = self.aktion("buchungen_anzeigen")
        text = ergebnis["text"]
        self.assertEqual(ergebnis["status"], "ausgefuehrt")
        self.assertIn("Einnahmen: 1.000,00 € (1 Buchungen)", text)
        self.assertIn("Ausgaben: 550,50 € (3 Buchungen)", text)
        self.assertIn("- Material: 350,50 € (2)", text)
        self.assertIn("Saldo: 449,50 €", text)
        self.assertIn("Einnahmen 500,00 €, Ausgaben 100,00 €, Saldo 400,00 €", text)  # Vormonat
        self.assertIn("Saldo-Unterschied: 49,50 €", text)
        self.assertNotIn("Miete", text.split("Vormonat")[0])
        self.assertIn("kein GoBD-konformes Kassenbuch", text)
        nur = self.aktion("buchungen_anzeigen", monat=vor.strftime("%Y-%m"), kategorie="Miete")["text"]
        self.assertIn("Ausgaben: 100,00 € (1 Buchungen)", nur)
        self.assertIn("Einnahmen: 0,00 € (0 Buchungen)", nur)
        self.assertNotIn("Bau:", nur)
        leer = self.aktion("buchungen_anzeigen", monat="2019-05")["text"]
        self.assertIn("keine Buchungen", leer)
        self.assertEqual(self.aktion("buchungen_anzeigen", monat="2019-13")["status"], "fehler")
        self.assertEqual(self.aktion("buchungen_anzeigen", kategorie="Urlaub")["status"], "fehler")

    def test_vormonat_ohne_buchungen_wird_nicht_erfunden(self):
        buchen(self.sp, self.monat().isoformat(), "einnahme", 1000, "Bau")
        self.assertIn("kein Vergleich möglich", self.aktion("buchungen_anzeigen")["text"])

    def test_monatsgrenzen(self):
        buchen(self.sp, "2026-10-31", "ausgabe", 100, "Büro")
        buchen(self.sp, "2026-11-01", "ausgabe", 200, "Büro")
        buchen(self.sp, "2026-11-30", "ausgabe", 400, "Büro")
        buchen(self.sp, "2026-12-01", "ausgabe", 800, "Büro")
        text = self.aktion("buchungen_anzeigen", monat="2026-11")["text"]
        self.assertIn("Ausgaben: 6,00 € (2 Buchungen)", text)
        self.assertIn("Vormonat (Oktober 2026): Einnahmen 0,00 €, Ausgaben 1,00 €", text)

    def test_rechnungsbuchungen_zaehlen_mit_und_nicht_doppelt(self):
        tag = self.monat().isoformat()
        rechnung = betrieb.RECHNUNGEN.anlegen(self.sp, nummer="R-2026-0001", titel="Treppenhaus", brutto_cent=59500,
                                              status="bezahlt", bezahlt_cent=59500)
        buchen(self.sp, tag, "einnahme", 59500, "Rechnung", "Zahlung R-2026-0001", rechnung_id=rechnung)
        buchen(self.sp, tag, "einnahme", 20000, None, None, rechnung_id=rechnung)  # ohne Kategorie, aber aus Rechnung
        text = self.aktion("buchungen_anzeigen")["text"]
        self.assertIn("Einnahmen: 795,00 € (2 Buchungen)", text)
        self.assertIn("- Rechnung: 795,00 € (2)", text)
        self.assertIn("Davon aus bezahlten Rechnungen: 795,00 €", text)
        # Von Hand dieselbe Zahlung buchen: wird gebucht (MELDUNG), aber mit deutlichem Hinweis
        hand = self.aktion("buchung_erfassen", art="einnahme", betrag="595", kategorie="Rechnung", datum=tag)
        self.assertEqual(hand["status"], "ausgefuehrt")
        self.assertIn("ACHTUNG", hand["text"])
        self.assertIn("R-2026-0001", hand["text"])
        self.assertIn("doppelt", hand["text"])
        # anderer Betrag oder anderes Datum: kein Hinweis
        for betrag, datum in (("596", tag), ("595", "2020-01-01")):
            ok = self.aktion("buchung_erfassen", art="einnahme", betrag=betrag, kategorie="Rechnung", datum=datum)
            self.assertNotIn("ACHTUNG", ok["text"])
        # Die Kasse legt von sich aus nie Buchungen mit rechnung_id an
        self.assertEqual(betrieb.BUCHUNGEN.zaehlen(self.sp, "rechnung_id IS NOT NULL"), 2)
        self.assertNotIn("rechnung_id", [p.name for w in kasse.werkzeuge() for p in w.parameter])

    def test_gleiche_handbuchung_wird_gemeldet(self):
        self.aktion("buchung_erfassen", art="ausgabe", betrag="12,50", text="Diesel", datum="2026-11-02")
        zweite = self.aktion("buchung_erfassen", art="ausgabe", betrag="12,50", text="Diesel", datum="2026-11-02")
        self.assertIn("gleiche Buchung", zweite["text"])

    def test_loeschen_nur_mit_freigabe(self):
        nr = buchen(self.sp, "2026-11-02", "ausgabe", 1250, "Material", "Pinsel")
        ergebnis = self.aktion("buchung_loeschen", id=str(nr))
        self.assertEqual(ergebnis["status"], "freigabe_offen")
        self.assertEqual(betrieb.BUCHUNGEN.zaehlen(self.sp), 1)  # noch da
        vorschau = self.agent.speicher.freigabe(ergebnis["freigabe_id"])["vorschau"]
        self.assertIn("Pinsel", vorschau)
        self.assertIn("12,50 €", vorschau)
        self.assertIn("kann nicht zurückgeholt werden", vorschau)
        self.agent.freigabe_beantworten(ergebnis["freigabe_id"], False)
        self.assertEqual(betrieb.BUCHUNGEN.zaehlen(self.sp), 1)  # abgelehnt: bleibt
        zweite = self.aktion("buchung_loeschen", id=str(nr))
        code, antwort = self.agent.freigabe_beantworten(zweite["freigabe_id"], True)
        self.assertEqual(code, 200)
        self.assertEqual(antwort["ergebnis"]["status"], "ausgefuehrt")
        self.assertEqual(betrieb.BUCHUNGEN.zaehlen(self.sp), 0)
        self.assertEqual(self.aktion("buchung_loeschen", id=str(nr))["status"], "ungueltig")  # gibt es nicht mehr
        self.assertEqual(self.aktion("buchung_loeschen", id="abc")["status"], "ungueltig")

    def test_loeschen_hinweis_bei_rechnungsbuchung(self):
        nr = buchen(self.sp, "2026-11-02", "einnahme", 1000, "Rechnung", rechnung_id=7)
        freigabe = self.aktion("buchung_loeschen", id=str(nr))
        self.assertIn("aus einer bezahlten Rechnung", self.agent.speicher.freigabe(freigabe["freigabe_id"])["vorschau"])

    def test_export_csv(self):
        buchen(self.sp, "2026-11-03", "einnahme", 123456, "Reinigung", "Büro Müller; Monat \"November\"")
        buchen(self.sp, "2026-11-04", "ausgabe", 5, "Material", "=HYPERLINK(\"http://böse\")", beleg="-evil.pdf")
        buchen(self.sp, "2026-11-05", "ausgabe", 700, "Büro", "@SUM(1)")
        buchen(self.sp, "2026-10-05", "ausgabe", 999, "Büro", "Oktober")
        ergebnis = self.aktion("kassen_export", monat="2026-11")
        self.assertEqual(ergebnis["status"], "ausgefuehrt", ergebnis)
        self.assertIn("export/Einnahmen-Ausgaben 2026-11.csv", ergebnis["text"])
        self.assertIn("3 Buchungen", ergebnis["text"])
        self.assertIn("verschickt wurde nichts", ergebnis["text"])
        with open(os.path.join(self.werkstatt, "export", "Einnahmen-Ausgaben 2026-11.csv"), "rb") as f:
            roh = f.read()
        self.assertTrue(roh.startswith(b"\xef\xbb\xbf"), "UTF-8 mit BOM")
        zeilen = list(csv.reader(io.StringIO(roh.decode("utf-8-sig"), newline=""), delimiter=";"))
        self.assertIn("keine Buchhaltung", zeilen[0][1])
        self.assertEqual(zeilen[1], list(kasse.KOPF_EXPORT))
        daten = zeilen[2:5]
        self.assertEqual(daten[0][1:6], ["03.11.2026", "Einnahme", "Reinigung", "1234,56", "Büro Müller; Monat \"November\""])
        self.assertEqual(daten[1][5], "'=HYPERLINK(\"http://böse\")")
        self.assertEqual(daten[1][6], "'-evil.pdf")
        self.assertEqual(daten[2][5], "'@SUM(1)")
        for zeile in zeilen[1:]:
            for zelle in zeile:
                self.assertNotIn(zelle[:1], ("=", "+", "-", "@", "\t"), zelle)
        self.assertNotIn("Oktober", roh.decode("utf-8"))
        self.assertTrue(any(z[2:5] == ["Summe Einnahmen", "", "1234,56"] for z in zeilen if len(z) > 4))
        self.assertTrue(any(z[2:5] == ["Summe Ausgaben", "", "7,05"] for z in zeilen if len(z) > 4))
        # Zweiter Export überschreibt nichts
        zweiter = self.aktion("kassen_export", monat="2026-11")
        self.assertIn("2026-11-2.csv", zweiter["text"])

    def test_export_leerer_monat(self):
        self.assertEqual(self.aktion("kassen_export", monat="2019-01")["status"], "fehler")
        self.assertFalse(os.path.exists(os.path.join(self.werkstatt, "export")))

    def test_bereich_privat(self):
        privat = self.ctx("privat")
        buchen(self.sp, "2026-11-03", "ausgabe", 100, "Büro")
        for name, roh in (("buchung_erfassen", {"art": "ausgabe", "betrag": "5"}), ("buchungen_anzeigen", {}),
                          ("kassen_export", {"monat": "2026-11"}), ("buchung_loeschen", {"id": "1"})):
            ergebnis = self.aktion(name, ctx=privat, **roh)
            self.assertIn(ergebnis["status"], ("fehler", "ungueltig"), name)
            self.assertIn("Geschäftsbereich", ergebnis["text"], name)
        self.assertEqual(betrieb.BUCHUNGEN.zaehlen(self.sp), 1)
        self.assertIsNone(kasse.anzeige(self.agent, "privat"))

    def test_stufen_und_agenten(self):
        stufen = {w.name: w.stufe for w in kasse.werkzeuge()}
        self.assertEqual(stufen, {"buchung_erfassen": kasse.MELDUNG, "buchungen_anzeigen": kasse.FREI,
                                  "buchung_loeschen": kasse.FREIGABE, "kassen_export": kasse.MELDUNG})
        self.assertEqual(kasse.FUER_AGENTEN, {"buchungen_anzeigen": ("finanzleiter", "kosten", "liquiditaet",
                                                                     "steuerberater_vorbereitung")})

    def test_baustein_und_katalog(self):
        system = self.agent.system_prompt(frage="Ich habe eine Tankquittung über 60 Euro, bitte als Ausgabe buchen")
        self.assertIn("KASSE", system)
        self.assertIn("- buchung_erfassen:", system)
        self.assertNotIn("- buchung_erfassen:", self.agent.system_prompt(frage="Wie wird das Wetter?"))

    def test_notstopp(self):
        self.agent.gesperrt.set()
        self.assertEqual(self.aktion("buchung_erfassen", art="ausgabe", betrag="5")["status"], "gesperrt")
        self.assertEqual(betrieb.BUCHUNGEN.zaehlen(self.sp), 0)


class KasseHooksTest(AgentBasis):
    def heute_mit(self, tag):
        return mock.patch.object(kasse, "heute", return_value=tag)

    def test_bericht(self):
        self.assertIsNone(kasse.bericht(self.agent, datetime.date(2026, 11, 1), datetime.date(2026, 11, 30)))
        buchen(self.sp, "2026-11-03", "einnahme", 200000, "Bau")
        buchen(self.sp, "2026-11-04", "ausgabe", 30000, "Material")
        buchen(self.sp, "2026-11-05", "ausgabe", 10000, "Büro")
        buchen(self.sp, "2026-12-05", "ausgabe", 99999, "Büro")
        b = kasse.bericht(self.agent, datetime.date(2026, 11, 1), datetime.date(2026, 11, 30))
        self.assertIn("Einnahmen 2.000,00 €, Ausgaben 400,00 €, Saldo 1.600,00 €", b["zeilen"][0])
        self.assertIn("Größte Ausgabenkategorie: Material mit 300,00 € (75 % der Ausgaben)", b["zeilen"][1])
        self.assertEqual(b["kennzahlen"], [("Einnahmen", "2.000,00 €"), ("Ausgaben", "400,00 €"), ("Saldo", "1.600,00 €")])
        text = kasse.bericht(self.agent, "2026-11-01", "2026-11-30")
        self.assertEqual(text["kennzahlen"], b["kennzahlen"])
        ueber = self.agent.erweiterungen.bericht(datetime.date(2026, 11, 1), datetime.date(2026, 11, 30))
        self.assertIn("kasse", [t["erweiterung"] for t in ueber])

    def test_anzeige(self):
        buchen(self.sp, "2026-11-03", "einnahme", 200000, "Bau")
        buchen(self.sp, "2026-11-04", "ausgabe", 30000, "Material", "Farbe")
        with self.heute_mit(datetime.date(2026, 11, 18)):
            daten = kasse.anzeige(self.agent, "geschaeft")
        self.assertEqual(daten["status"][1:], [("Einnahmen", "2.000,00 €"), ("Ausgaben", "300,00 €"), ("Saldo", "1.700,00 €")])
        self.assertEqual(daten["tabellen"][0]["zeilen"], [["Bau", "2.000,00 €", "0,00 €"], ["Material", "0,00 €", "300,00 €"],
                                                          ["Summe", "2.000,00 €", "300,00 €"]])
        self.assertEqual(len(daten["tabellen"][1]["zeilen"]), 2)
        self.assertIn("GoBD", daten["tabellen"][0]["hinweis"])
        eintrag = next(e for e in self.agent.erweiterungen.anzeige("geschaeft")["erweiterungen"] if e["name"] == "kasse")
        self.assertTrue(eintrag["aktiv"], eintrag)

    def test_lage_nur_bei_auffaelligem(self):
        with self.heute_mit(datetime.date(2026, 11, 18)):
            self.assertEqual(kasse.lage(self.agent), [])  # nichts gebucht: nichts melden
            buchen(self.sp, "2026-11-03", "einnahme", 200000, "Bau")
            buchen(self.sp, "2026-11-04", "ausgabe", 30000, "Material")
            self.assertEqual(kasse.lage(self.agent), [])  # Plus: nichts melden
            buchen(self.sp, "2026-11-05", "ausgabe", 190000, "Personal")
            zeilen = kasse.lage(self.agent)
        self.assertEqual(len(zeilen), 1)
        self.assertIn("mehr Ausgaben (2.200,00 €) als Einnahmen (2.000,00 €)", zeilen[0])
        self.assertIn("-200,00 €", zeilen[0])


if __name__ == "__main__":
    unittest.main()
