# -*- coding: utf-8 -*-
"""Die gemeinsamen Geschäftsdaten: Geld in Cent, Datum, Nummern, Kunden, Firmendaten, Kennzahlen."""

import datetime
import unittest

from tests.hilfen import AgentBasis

from jarvis_core import betrieb
from jarvis_core.werkzeuge import WerkzeugFehler


class GeldTest(unittest.TestCase):
    def test_euro_zu_cent(self):
        faelle = {"1.234,56 €": 123456, "1234,56": 123456, "1234.56": 123456, "12,5": 1250, "12.5": 1250, "1.234": 123400,
                  "1.234.567": 123456700, "1,234.56": 123456, "0,005": 1, "0,004": 0, "-5": -500, "  7 EUR ": 700,
                  "19 Euro": 1900, 12: 1200, 12.34: 1234, " 1 000,00": 100000}
        for eingabe, cent in faelle.items():
            self.assertEqual(betrieb.euro_zu_cent(eingabe), cent, eingabe)
        for falsch in ("", "abc", "1,2,3", "12 Äpfel", None, True, "1" * 12):
            with self.assertRaises(WerkzeugFehler, msg=repr(falsch)):
                betrieb.euro_zu_cent(falsch)

    def test_euro_format(self):
        self.assertEqual(betrieb.euro(123456), "1.234,56 €")
        self.assertEqual(betrieb.euro(-5), "-0,05 €")
        self.assertEqual(betrieb.euro(100000000, zeichen=False), "1.000.000,00")
        self.assertEqual(betrieb.euro(None), "0,00 €")

    def test_mwst_kaufmaennisch_gerundet(self):
        self.assertEqual(betrieb.mwst(10000, 19), (1900, 11900))
        self.assertEqual(betrieb.mwst(5, 19), (1, 6))  # 0,95 Cent -> 1 Cent
        self.assertEqual(betrieb.mwst(1001, 7), (70, 1071))
        self.assertEqual(betrieb.mwst(1000, 0), (0, 1000))
        with self.assertRaises(WerkzeugFehler):
            betrieb.mwst(1000, 16)

    def test_positionen_mit_rechenweg(self):
        positionen, netto = betrieb.positionen_rechnen([
            {"text": "Unterhaltsreinigung  Büro", "menge": "12,5", "einheit": "h", "einzel_cent": 3250},
            {"text": "Material", "menge": 1, "einzel_cent": 1999}])
        self.assertEqual([p["summe_cent"] for p in positionen], [40625, 1999])
        self.assertEqual(netto, 42624)
        self.assertEqual((positionen[0]["menge"], positionen[0]["text"]), ("12,5", "Unterhaltsreinigung Büro"))
        self.assertEqual(betrieb.summen(netto), {"netto_cent": 42624, "mwst_satz": 19, "mwst_cent": 8099,
                                                 "brutto_cent": 50723})
        for falsch in ([], [{"text": "", "menge": 1, "einzel_cent": 1}], [{"text": "a", "menge": "0", "einzel_cent": 1}],
                       [{"text": "a", "menge": "x", "einzel_cent": 1}], [{"text": "a", "menge": "nan", "einzel_cent": 1}]):
            with self.assertRaises(WerkzeugFehler, msg=repr(falsch)):
                betrieb.positionen_rechnen(falsch)


class DatumTest(unittest.TestCase):
    def test_datum(self):
        heute = datetime.date(2026, 11, 17)
        faelle = {"2026-11-20": "2026-11-20", "20.11.2026": "2026-11-20", "1.2.27": "2027-02-01", "24.12.": "2026-12-24",
                  "heute": "2026-11-17", "morgen": "2026-11-18", "Gestern": "2026-11-16", "übermorgen": "2026-11-19"}
        for eingabe, iso in faelle.items():
            self.assertEqual(betrieb.datum(eingabe, heute), iso, eingabe)
        for falsch in ("31.02.2026", "2026-13-01", "nächste Woche", ""):
            with self.assertRaises(WerkzeugFehler):
                betrieb.datum(falsch, heute)
        self.assertEqual(betrieb.datum_text("2026-11-20"), "20.11.2026")
        self.assertEqual(betrieb.datum_text(None), "")


class BetriebImAgentTest(AgentBasis):
    def test_tabellen_gibt_es_immer(self):
        for t in betrieb.TABELLEN:
            self.assertIn(t.name, self.sp.zusatz_tabellen)
            self.assertEqual(t.zaehlen(self.sp), 0)

    def test_nummern_fortlaufend_je_jahr_und_art(self):
        self.assertEqual(betrieb.naechste_nummer(self.sp, "R", 2026), "R-2026-0001")
        self.assertEqual(betrieb.naechste_nummer(self.sp, "R", 2026), "R-2026-0002")
        self.assertEqual(betrieb.naechste_nummer(self.sp, "A", 2026), "A-2026-0001")
        self.assertEqual(betrieb.naechste_nummer(self.sp, "R", 2027), "R-2027-0001")
        with self.assertRaises(ValueError):
            betrieb.naechste_nummer(self.sp, "r'; --")

    def test_kunden_finden(self):
        a = betrieb.kunde_anlegen(self.sp, "Hausverwaltung Berger GmbH", art="verwaltung", ort="Leverkusen")
        betrieb.kunde_anlegen(self.sp, "Berger & Söhne")
        betrieb.kunde_anlegen(self.sp, "Praxis 100%_Zahn")
        self.assertEqual(betrieb.kunde_finden(self.sp, "#%d" % a)["name"], "Hausverwaltung Berger GmbH")
        self.assertEqual(betrieb.kunde_finden(self.sp, "hausverwaltung berger gmbh")["id"], a)
        with self.assertRaises(WerkzeugFehler) as fehler:
            betrieb.kunde_finden(self.sp, "Berger")
        self.assertIn("Mehrere Kunden passen", str(fehler.exception))
        self.assertIsNone(betrieb.kunde_finden(self.sp, "Müller"))
        self.assertEqual(betrieb.kunde_finden(self.sp, "100%_")["name"], "Praxis 100%_Zahn")
        # % ist im Suchtext ein normales Zeichen, kein Platzhalter für „alles“ (sonst passten alle drei)
        self.assertEqual(betrieb.kunde_finden(self.sp, "%")["name"], "Praxis 100%_Zahn")
        kunde, neu = betrieb.kunde_oder_neu(self.sp, "Kita Sonnenschein")
        self.assertTrue(neu)
        self.assertEqual(betrieb.kunde_oder_neu(self.sp, "Kita Sonnenschein"), (kunde, False))
        with self.assertRaises(WerkzeugFehler):
            betrieb.kunde_oder_neu(self.sp, "#999")
        with self.assertRaises(WerkzeugFehler):
            betrieb.kunde_anlegen(self.sp, "X", art="unbekannt")
        self.assertEqual(betrieb.kunde_name(self.sp, a), "Hausverwaltung Berger GmbH")

    def test_firmendaten_ohne_bankdaten(self):
        self.assertEqual(betrieb.firma_text(self.sp, "name", "Firmenname"), "[Firmenname – bitte eintragen]")
        betrieb.firma_setzen(self.sp, name="  Muster   Bau und Reinigung ", ort="Leverkusen")
        self.assertEqual(betrieb.firma(self.sp)["name"], "Muster Bau und Reinigung")
        self.assertIsNone(betrieb.firma(self.sp)["steuernummer"])
        with self.assertRaises(WerkzeugFehler):
            betrieb.firma_setzen(self.sp, webseite="DE89 3704 0044 0532 0130 00")
        with self.assertRaises(WerkzeugFehler):
            betrieb.firma_setzen(self.sp, iban="DE89370400440532013000")

    def test_kennzahlen_nur_gezaehlt(self):
        heute = datetime.date(2026, 11, 17)
        k = betrieb.kunde_anlegen(self.sp, "Kunde")
        betrieb.AUFTRAEGE.anlegen(self.sp, kunde_id=k, titel="Treppenhaus", status="beauftragt", rhythmus="woechentlich",
                                  monatlich_cent=48000)
        betrieb.AUFTRAEGE.anlegen(self.sp, kunde_id=k, titel="Anfrage", status="anfrage")
        betrieb.RECHNUNGEN.anlegen(self.sp, nummer="R-1", kunde_id=k, status="gestellt", brutto_cent=11900,
                                   bezahlt_cent=1900, faellig="2026-11-01")
        betrieb.RECHNUNGEN.anlegen(self.sp, nummer="R-2", kunde_id=k, status="gestellt", brutto_cent=5000,
                                   faellig="2026-12-01")
        betrieb.RECHNUNGEN.anlegen(self.sp, nummer="R-3", kunde_id=k, status="entwurf", brutto_cent=99999)
        betrieb.BUCHUNGEN.anlegen(self.sp, datum="2026-11-03", art="einnahme", betrag_cent=1900)
        betrieb.BUCHUNGEN.anlegen(self.sp, datum="2026-10-30", art="ausgabe", betrag_cent=700)
        z = betrieb.kennzahlen(self.sp, heute)
        self.assertEqual((z["auftraege_offen"], z["auftraege_laufend"], z["dauerauftraege"]), (1, 1, 1))
        self.assertEqual(z["dauerauftraege_monatlich_cent"], 48000)
        self.assertEqual((z["rechnungen_offen"], z["forderungen_cent"]), (2, 15000))
        self.assertEqual((z["ueberfaellig"], z["ueberfaellig_cent"]), (1, 10000))
        self.assertEqual((z["einnahmen_monat_cent"], z["ausgaben_monat_cent"]), (1900, 0))

    def test_nur_im_geschaeftsbereich(self):
        betrieb.nur_geschaeft(self.ctx("geschaeft"))
        with self.assertRaises(WerkzeugFehler):
            betrieb.nur_geschaeft(self.ctx("privat"))
        self.assertEqual(betrieb.bereich(self.konfig), "geschaeft")


if __name__ == "__main__":
    unittest.main()
