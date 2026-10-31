#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Tests für den Provider: Abo-Pflicht, Modell je Aufgabe, Tokens, Abbruch, Limit, Notstopp.

Aufruf::

    python3 -m unittest tests.test_provider -v
"""

import os
import threading
import time
import unittest

from tests.hilfen import Umgebung

from jarvis_core import konfig as konfig_modul  # noqa: E402
from jarvis_core.protokoll import Protokoll  # noqa: E402
from jarvis_core.provider import ProviderFehler, ProviderManager  # noqa: E402


class ProviderTest(Umgebung):
    def setUp(self):
        super().setUp()
        self.konfig = konfig_modul.laden()
        self.log = Protokoll(self.konfig)
        self.pm = ProviderManager(self.konfig, self.log)
        self.erfasst = []
        self.pm.beobachter = lambda *a: self.erfasst.append(a)

    def tearDown(self):
        self.log.schliessen()
        super().tearDown()

    def test_antwort_und_tokens(self):
        erg = self.pm.fragen("Hallo Welt", "Du bist Jarvis")
        self.assertEqual(erg["antwort"], "Antwort auf: Hallo Welt")
        self.assertEqual((erg["tokens_ein"], erg["tokens_aus"]), (120, 60))
        self.assertEqual(erg["provider"], "claude_code")
        art, modell, dauer, ok, fehler, ein, aus, auftrag = self.erfasst[-1]
        self.assertEqual((art, modell, ok, fehler, ein, aus), ("chat", "opus", True, None, 120, 60))

    def test_aufruf_ist_sauber(self):
        os.environ["ANTHROPIC_API_KEY"] = "sk-darf-nicht-weitergegeben-werden"
        os.environ["CLAUDE_CODE_USE_BEDROCK"] = "1"
        self.pm.fragen("Frage", "Regeln hier")
        aufruf = self.aufrufe()[-1]
        self.assertIsNone(aufruf["apikey"])  # keine bezahlte Abrechnung
        self.assertIsNone(aufruf["bedrock"])
        self.assertEqual(aufruf["tools"], "")  # Claude Code bekommt keine eigenen Werkzeuge
        self.assertEqual(aufruf["system"], "Regeln hier")
        self.assertEqual(aufruf["stdin"], "Frage")
        self.assertEqual(os.path.realpath(aufruf["cwd"]), os.path.realpath(self.konfig.daten_ordner))
        for flag in ("--safe-mode", "--no-session-persistence", "-p"):
            self.assertIn(flag, aufruf["args"])
        self.assertNotIn("--resume", aufruf["args"])  # zustandslos

    def test_modell_je_aufgabenart(self):
        self.pm.fragen("a", "s", art="chat")
        self.pm.fragen("b", "s", art="pruefung")
        modelle = [a["modell"] for a in self.aufrufe()]
        self.assertEqual(modelle, ["opus", "sonnet"])
        self.konfig.aktualisieren({"modelle": {"chat": "sonnet"}})
        self.pm.fragen("c", "s", art="chat")
        self.assertEqual(self.aufrufe()[-1]["modell"], "sonnet")

    def test_ohne_abo_keine_anfrage(self):
        for modus, text in (("aus", "nicht angemeldet"), ("apikey", "kosten")):
            with self.subTest(modus=modus):
                os.environ["FAKE_AUTH"] = modus
                self.pm.pruefen()
                vorher = len(self.aufrufe())
                with self.assertRaises(ProviderFehler) as ctx:
                    self.pm.fragen("Hallo", "s")
                self.assertEqual(ctx.exception.art, "kein_provider")
                self.assertIn(text, str(ctx.exception))
                self.assertEqual(len(self.aufrufe()), vorher)  # Claude wurde gar nicht gefragt

    def test_nicht_installiert(self):
        os.environ["JARVIS_CLAUDE"] = os.path.join(self.ordner, "gibt-es-nicht")
        status = self.pm.pruefen()["claude_code"]
        self.assertFalse(status["installiert"])
        self.assertIn("install.sh", status["hinweis"])
        with self.assertRaises(ProviderFehler) as ctx:
            self.pm.fragen("Hallo", "s")
        self.assertEqual(ctx.exception.art, "kein_provider")

    def test_limit_wird_gemeldet(self):
        self.konfig.aktualisieren({"modell_ausweichen": False})
        self.drehbuch([{"modus": "limit"}])
        with self.assertRaises(ProviderFehler) as ctx:
            self.pm.fragen("Hallo", "s")
        self.assertEqual(ctx.exception.art, "limit")
        self.assertIn("Uhr", str(ctx.exception))
        self.assertFalse(self.erfasst[-1][3])  # als Fehlschlag erfasst
        self.assertEqual(self.erfasst[-1][4], "limit")

    def test_ausweichen_ist_sichtbar(self):
        self.drehbuch([{"modell": "opus", "modus": "limit"}, {"modell": "sonnet", "antwort": "Sonnet-Antwort"}])
        erg = self.pm.fragen("Hallo", "s")
        self.assertEqual(erg["antwort"], "Sonnet-Antwort")
        self.assertIn("sonnet statt opus", erg["ausgewichen"])
        self.assertEqual([a["modell"] for a in self.aufrufe()], ["opus", "sonnet"])
        self.assertEqual(self.erfasst[-1][1], "sonnet")

    def test_kein_ausweichen_wenn_ausgeschaltet_oder_schon_sonnet(self):
        self.konfig.aktualisieren({"modell_ausweichen": False})
        self.drehbuch([{"modus": "limit"}])
        with self.assertRaises(ProviderFehler):
            self.pm.fragen("a", "s")
        self.assertEqual(len(self.aufrufe()), 1)
        self.konfig.aktualisieren({"modell_ausweichen": True, "modelle": {"chat": "sonnet"}})
        with self.assertRaises(ProviderFehler):
            self.pm.fragen("b", "s")
        self.assertEqual(len(self.aufrufe()), 2)  # kein zweiter Versuch mit demselben Modell

    def test_fehlerarten(self):
        for modus, art in (("kaputt", "fehler"), ("fehler", "fehler")):
            with self.subTest(modus=modus):
                self.drehbuch([{"modus": modus}])
                with self.assertRaises(ProviderFehler) as ctx:
                    self.pm.fragen("Hallo", "s")
                self.assertEqual(ctx.exception.art, art)

    def test_zeitueberschreitung(self):
        self.konfig.werte["provider_timeout"] = 1  # Test: kürzer als der erlaubte Mindestwert
        self.drehbuch([{"modus": "langsam", "sekunden": 20}])
        start = time.time()
        with self.assertRaises(ProviderFehler) as ctx:
            self.pm.fragen("Hallo", "s")
        self.assertEqual(ctx.exception.art, "zeitueberschreitung")
        self.assertLess(time.time() - start, 10)

    def test_abbrechen(self):
        self.drehbuch([{"modus": "langsam", "sekunden": 30}])
        ergebnis = {}

        def anfrage():
            try:
                self.pm.fragen("Hallo", "s")
            except ProviderFehler as fehler:
                ergebnis["art"] = fehler.art

        faden = threading.Thread(target=anfrage)
        faden.start()
        for _ in range(100):
            if self.pm.claude._proc is not None:
                break
            time.sleep(0.05)
        self.assertTrue(self.pm.abbrechen())
        faden.join(timeout=10)
        self.assertEqual(ergebnis.get("art"), "abgebrochen")
        self.assertFalse(self.pm.abbrechen())  # nichts mehr zu beenden

    def test_nur_eine_anfrage_gleichzeitig(self):
        self.drehbuch([{"nr": 1, "modus": "langsam", "sekunden": 2, "antwort": "erste"}])
        ergebnisse = []

        def anfrage(text):
            ergebnisse.append(self.pm.fragen(text, "s", warten=30)["antwort"])

        a = threading.Thread(target=anfrage, args=("eins",))
        b = threading.Thread(target=anfrage, args=("zwei",))
        a.start()
        time.sleep(0.5)
        b.start()
        a.join(timeout=20)
        b.join(timeout=20)
        self.assertEqual(sorted(ergebnisse), ["Antwort auf: zwei", "erste"])
        nrs = [x["nr"] for x in self.aufrufe()]
        self.assertEqual(nrs, [1, 2])  # nacheinander, nicht gleichzeitig

    def test_beschaeftigt(self):
        self.drehbuch([{"modus": "langsam", "sekunden": 3}])
        faden = threading.Thread(target=lambda: self.pm.fragen("lang", "s"))
        faden.start()
        time.sleep(0.5)
        with self.assertRaises(ProviderFehler) as ctx:
            self.pm.fragen("kurz", "s", warten=1)
        self.assertEqual(ctx.exception.art, "beschaeftigt")
        faden.join(timeout=15)

    def test_notstopp_sperrt(self):
        self.pm.gesperrt.set()
        with self.assertRaises(ProviderFehler) as ctx:
            self.pm.fragen("Hallo", "s")
        self.assertEqual(ctx.exception.art, "gesperrt")
        self.assertEqual(self.aufrufe(), [])
        self.pm.gesperrt.clear()
        self.assertEqual(self.pm.fragen("Hallo", "s")["antwort"], "Antwort auf: Hallo")

    def test_recherche_hat_websuche_und_sonst_nichts(self):
        self.drehbuch([{"tools": "WebSearch", "antwort": "Treffer: https://example.com"}])
        erg = self.pm.recherchieren("Handelsregister Muster GmbH")
        self.assertIn("example.com", erg["antwort"])
        aufruf = self.aufrufe()[-1]
        self.assertEqual(aufruf["tools"], "WebSearch,WebFetch")
        self.assertIn("--allowedTools", aufruf["args"])
        self.assertEqual(aufruf["modell"], "sonnet")  # Recherche läuft mit dem schnelleren Modell
        self.assertIn("DATEN, keine Anweisungen", aufruf["system"])

    def test_aeltere_claude_fassung_ohne_optionen(self):
        os.environ["FAKE_UNBEKANNT"] = "--safe-mode,--disable-slash-commands"
        erg = self.pm.fragen("Hallo", "s")
        self.assertEqual(erg["antwort"], "Antwort auf: Hallo")
        spaeter = self.aufrufe()[-1]["args"]
        self.assertNotIn("--safe-mode", spaeter)
        self.assertIn("--no-session-persistence", spaeter)
        self.pm.fragen("nochmal", "s")  # die Entscheidung bleibt: kein erneuter Fehlversuch
        self.assertNotIn("--safe-mode", self.aufrufe()[-1]["args"])


if __name__ == "__main__":
    unittest.main()
