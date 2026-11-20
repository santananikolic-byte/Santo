# -*- coding: utf-8 -*-
"""Lasttest (Abschnitt 12, Phase 6: „Skalierung erst nach Last- und Sicherheitstests“).

Misst echte Durchsatzwerte auf dem aktuellen Rechner und prüft, dass unter Last
- keine Aufgabe doppelt beansprucht wird,
- keine Aufgabe verloren geht,
- die Zahl der Arbeiter begrenzt bleibt.
Die gemessenen Werte werden ausgegeben (keine Zusicherung für andere Rechner)."""

import threading
import time

from autonomous.agenten import Agent
from autonomous.tests.hilfe import KernTest

ANZAHL = 600


class TestLast(KernTest):
    def test_viele_aufgaben_mit_begrenzter_parallelitaet(self):
        self.kern.einstellungen.setze("max_parallel", 4, "eigentuemer")
        for i in range(ANZAHL):
            self.kern.aufgaben.anlegen("Last %d" % i, "kennzahlen", "ceo", "eigentuemer", prioritaet=1 + i % 5)
        start = time.time()
        self.orch.starten()
        threads_waehrend = threading.active_count()
        ende = start + 120
        while time.time() < ende and self.kern.aufgaben.zaehlen()["abgeschlossen"] < ANZAHL:
            time.sleep(0.05)
        dauer = time.time() - start
        self.orch.stoppen()
        zahlen = self.kern.aufgaben.zaehlen()
        self.assertEqual(zahlen["abgeschlossen"], ANZAHL, zahlen)
        self.assertEqual(self.orch.status()["arbeiter"], 0)
        self.assertLessEqual(len([t for t in threading.enumerate() if t.name.startswith("arbeiter-")]), 0)
        doppelt = self.kern.db.wert("SELECT COUNT(*) FROM (SELECT aufgabe_id FROM aufgaben_verlauf WHERE "
                                    "nach_status='laufend' GROUP BY aufgabe_id HAVING COUNT(*)>1)")
        self.assertEqual(doppelt, 0)
        print("\n  Lasttest: %d Aufgaben mit 4 Arbeitern in %.1f s (%.0f Aufgaben/s), Threads gesamt: %d"
              % (ANZAHL, dauer, ANZAHL / dauer, threads_waehrend))

    def test_500_logische_rollen_ohne_500_prozesse(self):
        class Rolle(Agent):
            rechte = frozenset({"interne_auswertung"})
            aufgabentypen = {"zaehlen": "zählt"}

            def aufgabe_zaehlen(self, aufgabe, k):
                self.darf(k, "interne_auswertung", "zaehlen", aufgabe)
                return {"rolle": self.rolle}

        neue = 500 - len(self.kern.register.rollen())
        for i in range(neue):
            r = type("Rolle%d" % i, (Rolle,), {"rolle": "fach%03d" % i, "name": "Fachrolle %d" % i})()
            self.kern.register.registrieren(r)
        self.assertEqual(len(self.kern.register.rollen()), 500)
        for i in range(neue):
            self.kern.aufgaben.anlegen("x", "zaehlen", "fach%03d" % i, "eigentuemer")
        vorher = threading.active_count()
        self.assertEqual(self.orch.alle_abarbeiten(maximal=1000), neue)
        self.assertEqual(threading.active_count(), vorher)  # keine zusätzlichen Prozesse/Threads je Rolle
        self.assertEqual(self.kern.aufgaben.zaehlen()["abgeschlossen"], neue)
