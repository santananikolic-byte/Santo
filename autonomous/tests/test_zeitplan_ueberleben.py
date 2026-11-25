# -*- coding: utf-8 -*-
"""Täglicher Überlebensplan im Server-Zeitplan: Standard an, abschaltbar nur durch den Eigentümer,
höchstens ein Plan je Tag, Fehler im Zeitplan legen den Server nicht lahm."""

import threading

from autonomous import konfig, server
from autonomous.tests.hilfe import KernTest


class TestUeberlebensplanZeitplan(KernTest):
    def plaene(self):
        return self.kern.db.alle("SELECT id, ersteller FROM aufgaben WHERE typ='ueberlebensplan'")

    def test_standard_ist_an(self):
        self.assertIs(konfig.STANDARD_EINSTELLUNGEN["ueberlebensplan_taeglich"], True)
        self.assertIs(self.kern.einstellungen.hole("ueberlebensplan_taeglich"), True)

    def test_hoechstens_ein_plan_je_tag(self):
        aid = server.ueberlebensplan_anstossen(self.kern)
        self.assertIsNotNone(aid)
        self.assertEqual(self.kern.aufgaben.hole(aid)["ersteller"], "zeitplan")
        self.assertIsNone(server.ueberlebensplan_anstossen(self.kern))  # noch offen
        self.orch.alle_abarbeiten()
        self.assertEqual(self.kern.aufgaben.hole(aid)["status"], "abgeschlossen")
        self.assertIsNone(server.ueberlebensplan_anstossen(self.kern))  # heute schon einer
        self.assertEqual(len(self.plaene()), 1)

    def test_ausgeschaltet_kein_plan(self):
        self.kern.einstellungen.setze("ueberlebensplan_taeglich", False, "eigentuemer")
        self.assertIsNone(server.ueberlebensplan_anstossen(self.kern))
        self.assertEqual(self.plaene(), [])
        self.kern.einstellungen.setze("ueberlebensplan_taeglich", True, "eigentuemer")
        self.assertIsNotNone(server.ueberlebensplan_anstossen(self.kern))

    def test_nur_wahr_oder_falsch_erlaubt(self):
        for falsch in ("ja", 1, None, "true"):
            with self.assertRaises((ValueError, PermissionError)):
                self.kern.einstellungen.setze("ueberlebensplan_taeglich", falsch, "eigentuemer")
        self.assertIs(self.kern.einstellungen.hole("ueberlebensplan_taeglich"), True)

    def test_agenten_duerfen_nicht_umschalten(self):
        with self.assertRaises((ValueError, PermissionError)):
            self.kern.einstellungen.setze("ueberlebensplan_taeglich", False, "ueberleben")
        self.assertIs(self.kern.einstellungen.hole("ueberlebensplan_taeglich"), True)

    def test_hintergrund_legt_plan_an_und_haelt_an(self):
        stopp = threading.Event()
        faden = threading.Thread(target=server.taeglicher_ueberlebensplan, args=(self.kern, stopp), daemon=True)
        faden.start()
        try:
            for _ in range(50):
                if self.plaene():
                    break
                stopp.wait(0.1)
        finally:
            stopp.set()
            faden.join(5)
        self.assertFalse(faden.is_alive())
        self.assertEqual(len(self.plaene()), 1)

    def test_fehler_im_zeitplan_wird_protokolliert_nicht_geworfen(self):
        stopp = threading.Event()
        alt = server.ueberlebensplan_anstossen

        def kaputt(kern):
            stopp.set()
            raise RuntimeError("Testfehler im Zeitplan")
        server.ueberlebensplan_anstossen = kaputt
        try:
            server.taeglicher_ueberlebensplan(self.kern, stopp)  # darf nicht werfen und hält bei stopp an
        finally:
            server.ueberlebensplan_anstossen = alt
        eintrag = self.kern.db.eins("SELECT * FROM protokoll WHERE ereignis LIKE 'Überlebensplan konnte%'")
        self.assertIsNotNone(eintrag)
