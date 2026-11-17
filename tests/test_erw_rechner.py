# -*- coding: utf-8 -*-
"""Muster-Erweiterung Rechner: exakt rechnen, Reinigungspreis mit Rechenweg, Sofort-Antwort ohne Modell."""

import unittest
from decimal import Decimal

from tests.hilfen import AgentBasis

from jarvis_core.erweiterungen import rechner


class RechnenTest(unittest.TestCase):
    def test_wie_ein_taschenrechner(self):
        faelle = {"17*23": "391", "12,5 * 4 + 19 %": "59,5", "100 + 19 %": "119", "119 - 19 %": "96,39",
                  "200 * 19 %": "38", "(100 + 50) + 10 %": "165", "1.234,5 / 2": "617,25", "10 : 4": "2,5",
                  "3 x 4": "12", "-5 + 2": "-3", "1/3": "0,3333", "0,1 + 0,2": "0,3", "1000000 * 3": "3.000.000"}
        for ausdruck, ergebnis in faelle.items():
            self.assertEqual(rechner.rechne(ausdruck)[1], "%s = %s" % (ausdruck, ergebnis), ausdruck)

    def test_fehler_verstaendlich(self):
        for ausdruck, teil in (("5/0", "Durch 0"), ("(3+", "unvollständig"), ("2**3", "nicht rechnen"),
                               ("abc", "Erlaubt sind"), ("(1+2)%", "Prozentzeichen"), ("1" * 300, "höchstens"),
                               ("__import__('os')", "Erlaubt sind"), ("9" * 20 + "*" + "9" * 20, "unrealistisch")):
            with self.assertRaises(rechner.RechenFehler, msg=ausdruck) as fehler:
                rechner.rechne(ausdruck)
            self.assertIn(teil, str(fehler.exception))

    def test_kalkulation_rechenweg(self):
        zeilen, je, monat = rechner.kalkulation(Decimal(450), Decimal(180), 3250, Decimal(2), 30, Decimal(10))
        # 450 : 180 = 2,5 h; 2,5 × 32,50 = 81,25; Anfahrt 0,5 h = 16,25; (81,25 + 16,25) × 1,1 = 107,25
        self.assertEqual(je, 10725)
        self.assertEqual(monat, 92950)  # 107,25 × 2 × 52/12 = 929,50
        self.assertIn("450 m² : 180 m²/h = 2,5 Stunden", zeilen[0])
        self.assertIn("4,33 Wochen", zeilen[-1])


class RechnerImAgentTest(AgentBasis):
    def test_sofort_ohne_modell(self):
        code, antwort = self.agent.chat("Was ist 17 * 23?")
        self.assertEqual((code, antwort["antwort"]), (200, "17 * 23 = 391 (exakt gerechnet)"))
        self.assertEqual(antwort["bausteine"], ["sofort:rechner"])
        self.assertEqual(self.aufrufe(), [])

    def test_keine_sofort_antwort_bei_normalen_saetzen(self):
        for text in ("Rechne mir ein Angebot für Berger", "3-4", "17.11.2026", "14:30", "Was ist 5?", "Wie geht es dir?"):
            self.assertIsNone(rechner.sofort(self.agent, text, None, "geschaeft"), text)
        self.assertIsNotNone(rechner.sofort(self.agent, "Jarvis, was ist 2 + 2?", None, "geschaeft"))

    def test_werkzeuge(self):
        ergebnis = self.aktion("rechnen", ausdruck="1.250 * 3 + 19 %")
        self.assertEqual((ergebnis["status"], ergebnis["text"]), ("ausgefuehrt", "Gerechnet (exakt): 1.250 * 3 + 19 % = 4.462,5"))
        ergebnis = self.aktion("reinigung_kalkulieren", flaeche="450", leistungswert="180", stundensatz="32,50",
                               je_woche="2")
        self.assertEqual(ergebnis["status"], "ausgefuehrt")
        self.assertIn("Je Reinigung (netto): 81,25 €", ergebnis["text"])
        self.assertIn("kein geprüfter Preis", ergebnis["text"])
        fehlt = self.aktion("reinigung_kalkulieren", flaeche="450", leistungswert="180")
        self.assertEqual(fehlt["status"], "ungueltig")  # Stundensatz fehlt: nie geschätzt
        falsch = self.aktion("reinigung_kalkulieren", flaeche="450", leistungswert="0", stundensatz="30")
        self.assertEqual(falsch["status"], "fehler")

    def test_rechnen_steht_immer_im_katalog_kalkulieren_nur_beim_thema(self):
        system = self.agent.system_prompt(frage="Hallo")
        self.assertIn("- rechnen:", system)
        self.assertNotIn("- reinigung_kalkulieren:", system)
        system = self.agent.system_prompt(frage="Kalkulier mir 450 m² Büro")
        self.assertIn("- reinigung_kalkulieren:", system)
        self.assertIn("RECHNEN UND KALKULIEREN", system)

    def test_anzeige_zaehlt(self):
        self.aktion("rechnen", ausdruck="1+1")
        self.agent.chat("Was ist 2 * 2?")
        eintrag = next(e for e in self.agent.erweiterungen.anzeige("geschaeft")["erweiterungen"] if e["name"] == "rechner")
        self.assertEqual(eintrag["status"], [("Heute gerechnet", "2 Mal")])


if __name__ == "__main__":
    unittest.main()
