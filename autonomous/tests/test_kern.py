# -*- coding: utf-8 -*-
"""Abnahmetests für Kern, Aufgaben, Neustart, Agenten (Abschnitt 13)."""

import sqlite3
import time

from autonomous.tests.hilfe import KernTest


class TestAufgaben(KernTest):
    def test_aufgabe_bleibt_nach_neustart_erhalten(self):
        aid = self.kern.aufgaben.anlegen("Plan", "tagesplan", "ceo", "eigentuemer", sofort_bereit=False)
        self.neu_starten()
        a = self.kern.aufgaben.hole(aid)
        self.assertEqual(a["status"], "geplant")
        self.assertEqual(a["titel"], "Plan")

    def test_unterbrochene_aufgabe_wird_nach_neustart_wieder_bereit(self):
        aid = self.kern.aufgaben.anlegen("KZ", "kennzahlen", "ceo", "eigentuemer")
        self.kern.aufgaben.naechste_beanspruchen(["ceo"])  # läuft ...
        self.assertEqual(self.kern.aufgaben.hole(aid)["status"], "laufend")
        self.neu_starten()  # ... und der Rechner geht aus
        self.assertEqual(self.kern.aufgaben.hole(aid)["status"], "bereit")
        self.assertEqual(self.orch.alle_abarbeiten(), 1)
        self.assertEqual(self.kern.aufgaben.hole(aid)["status"], "abgeschlossen")

    def test_unterbrochen_ohne_versuche_wird_fehlgeschlagen(self):
        aid = self.kern.aufgaben.anlegen("KZ", "kennzahlen", "ceo", "eigentuemer", max_versuche=1)
        self.kern.aufgaben.naechste_beanspruchen(["ceo"])
        self.neu_starten()
        self.assertEqual(self.kern.aufgaben.hole(aid)["status"], "fehlgeschlagen")

    def test_agent_nimmt_an_bearbeitet_und_speichert(self):
        aid = self.kern.aufgaben.anlegen("KZ", "kennzahlen", "ceo", "eigentuemer")
        self.orch.alle_abarbeiten()
        a = self.kern.aufgaben.hole(aid)
        self.assertEqual(a["status"], "abgeschlossen")
        self.assertIn("aufgaben", a["ergebnis"])
        verlauf = [v["nach_status"] for v in self.kern.aufgaben.verlauf(aid)]
        self.assertEqual(verlauf, ["bereit", "laufend", "abgeschlossen"])

    def test_aufgabenuebergabe_ceo_an_research(self):
        self.kern.aufgaben.anlegen("Verteilen", "auftrag_verteilen", "ceo", "eigentuemer",
                                   {"rolle": "finance", "typ": "finanzbericht"})
        self.orch.alle_abarbeiten()
        kinder = [a for a in self.kern.aufgaben.liste() if a["verantwortlich"] == "finance"]
        self.assertEqual(len(kinder), 1)
        self.assertEqual(kinder[0]["status"], "abgeschlossen")
        self.assertIsNotNone(kinder[0]["eltern_id"])

    def test_fehler_sichtbar_und_keine_endlosschleife(self):
        aid = self.kern.aufgaben.anlegen("Kaputt", "wirtschaftlichkeit", "finance", "eigentuemer", {})
        self.orch.alle_abarbeiten()
        a = self.kern.aufgaben.hole(aid)
        self.assertEqual(a["status"], "fehlgeschlagen")
        self.assertIn("Preis fehlt", a["fehler"])
        self.assertEqual(a["versuche"], 1)  # fachlicher Fehler: kein sinnloses Wiederholen
        self.assertTrue(self.kern.protokoll.liste("fehler"))

    def test_technischer_fehler_wird_begrenzt_wiederholt(self):
        agent = self.kern.register.hole("ceo")
        original = agent.aufgabe_kennzahlen
        agent.aufgabe_kennzahlen = lambda a, k: (_ for _ in ()).throw(RuntimeError("Absturz"))
        try:
            aid = self.kern.aufgaben.anlegen("KZ", "kennzahlen", "ceo", "eigentuemer", max_versuche=3)
            for _ in range(10):
                self.kern.db.ausfuehren("UPDATE aufgaben SET naechster_versuch=NULL WHERE id=?", (aid,))
                self.orch.alle_abarbeiten()
            a = self.kern.aufgaben.hole(aid)
            self.assertEqual(a["status"], "fehlgeschlagen")
            self.assertEqual(a["versuche"], 3)
        finally:
            agent.aufgabe_kennzahlen = original

    def test_unerlaubter_statuswechsel(self):
        aid = self.kern.aufgaben.anlegen("KZ", "kennzahlen", "ceo", "eigentuemer")
        self.orch.alle_abarbeiten()
        with self.assertRaises(ValueError):
            self.kern.aufgaben.abbrechen(aid, "eigentuemer")

    def test_folgeaufgaben_begrenzt_und_nur_bekannte_rollen(self):
        agent = self.kern.register.hole("ceo")
        original = agent.aufgabe_kennzahlen
        agent.aufgabe_kennzahlen = lambda a, k: {"folgeaufgaben": [
            {"titel": "x", "typ": "kennzahlen", "verantwortlich": "ceo"}] * 50 + [
            {"titel": "y", "typ": "x", "verantwortlich": "gibtsnicht"}]}
        try:
            self.kern.aufgaben.anlegen("KZ", "kennzahlen", "ceo", "eigentuemer")
            self.orch.einmal()
        finally:
            agent.aufgabe_kennzahlen = original
        self.assertEqual(len(self.kern.aufgaben.liste()), 11)

    def test_parallele_arbeiter_beanspruchen_nie_doppelt(self):
        for i in range(20):
            self.kern.aufgaben.anlegen("KZ %d" % i, "kennzahlen", "ceo", "eigentuemer")
        self.orch.starten()
        ende = time.time() + 20
        while time.time() < ende and self.kern.aufgaben.zaehlen()["abgeschlossen"] < 20:
            time.sleep(0.1)
        self.orch.stoppen()
        self.assertEqual(self.kern.aufgaben.zaehlen()["abgeschlossen"], 20)
        doppelt = self.kern.db.alle("SELECT aufgabe_id, COUNT(*) n FROM aufgaben_verlauf WHERE nach_status='laufend' "
                                    "GROUP BY aufgabe_id HAVING n>1")
        self.assertEqual(doppelt, [])


class TestStatusUndAgenten(KernTest):
    def test_status_zeigt_echten_backendzustand(self):
        s = self.kern.status()
        self.assertEqual(s["betrieb"], "laeuft")
        self.assertTrue(s["datenbank"]["ok"])
        self.assertEqual(s["aufgaben"]["bereit"], 0)
        self.kern.aufgaben.anlegen("KZ", "kennzahlen", "ceo", "eigentuemer")
        self.assertEqual(self.kern.status()["aufgaben"]["bereit"], 1)

    def test_erste_rollen_vorhanden(self):
        for rolle in ("ceo", "research", "product", "sales", "finance", "learning"):
            self.assertIsNotNone(self.kern.register.hole(rolle), rolle)

    def test_register_grenze_500(self):
        from autonomous.agenten import Agent, Register
        r = Register()
        for i in range(500):
            klasse = type("A%d" % i, (Agent,), {"rolle": "r%d" % i})
            r.registrieren(klasse())
        with self.assertRaises(ValueError):
            r.registrieren(type("Zuviel", (Agent,), {"rolle": "r500"})())

    def test_tagesplan_aus_echten_daten(self):
        self.kern.ziele.anlegen("Mehr Aufträge gewinnen", prioritaet=1)
        aid = self.kern.aufgaben.anlegen("Plan", "tagesplan", "ceo", "eigentuemer")
        self.orch.alle_abarbeiten()
        plan = self.kern.aufgaben.hole(aid)["ergebnis"]
        self.assertIn("Mehr Aufträge gewinnen", [p["text"] for p in plan["punkte"]])
        self.assertEqual(self.kern.gedaechtnis.liste("vorschlag")[0]["thema"][:9], "Tagesplan")

    def test_wirtschaftlichkeit_ohne_stundensatz_erfindet_nichts(self):
        aid = self.kern.aufgaben.anlegen("W", "wirtschaftlichkeit", "finance", "eigentuemer",
                                         {"preis": "500", "kosten": "20", "stunden": 8})
        self.orch.alle_abarbeiten()
        e = self.kern.aufgaben.hole(aid)["ergebnis"]
        self.assertEqual(e["deckungsbeitrag"], "480,00 €")
        self.assertIn("OFFEN", e["stundensatz"])
        self.assertNotIn("lohnt_sich", e)

    def test_learning_aendert_keine_regeln(self):
        vorher = self.kern.einstellungen.alle()
        self.kern.aufgaben.anlegen("L", "auswertung", "learning", "eigentuemer")
        self.orch.alle_abarbeiten()
        self.assertEqual(self.kern.einstellungen.alle(), vorher)

    def test_ohne_modell_laufen_kernfunktionen(self):
        self.assertFalse(self.kern.modell.verfuegbar())
        for rolle, typ in (("ceo", "tagesplan"), ("ceo", "kennzahlen"), ("finance", "finanzbericht"),
                           ("learning", "auswertung")):
            self.kern.aufgaben.anlegen(typ, typ, rolle, "eigentuemer")
        self.orch.alle_abarbeiten()
        self.assertEqual(self.kern.aufgaben.zaehlen()["abgeschlossen"], 4)

    def test_modell_limit_und_protokoll(self):
        from autonomous.modell import ModellNichtVerfuegbar
        with self.assertRaises(ModellNichtVerfuegbar):
            self.kern.modell.frage("hallo", "ceo")
        self.kern.einstellungen.setze("modell_anbieter", "ollama", "eigentuemer")
        self.kern.einstellungen.setze("modell_max_aufrufe_tag", 0, "eigentuemer")
        with self.assertRaises(ModellNichtVerfuegbar):
            self.kern.modell.frage("hallo", "ceo")
        self.assertEqual(self.kern.modell.protokoll_liste()[0]["ergebnis"], "limit")


class TestGedaechtnis(KernTest):
    def test_arten_getrennt_und_rechte(self):
        g = self.kern.gedaechtnis
        g.merken("entscheidung", "Preis", "Stundensatz wird später festgelegt", "Gespräch", "eigentuemer")
        g.merken("hypothese", "Markt", "Handwerker brauchen Webseiten", "Annahme", "research")
        with self.assertRaises(PermissionError):
            g.merken("entscheidung", "x", "y", "z", "ceo")
        with self.assertRaises(PermissionError):
            g.merken("fakt", "x", "y", "Bauchgefühl", "research")
        g.merken("fakt", "x", "y", "https://www.gesetze-im-internet.de/ddg/__5.html", "research")
        self.assertEqual(len(g.liste("entscheidung")), 1)
        self.assertEqual(len(g.liste("fakt")), 1)


class TestSicherung(KernTest):
    def test_sicherung_und_wiederherstellung(self):
        from autonomous import sicherung
        aid = self.kern.aufgaben.anlegen("Bleibt", "kennzahlen", "ceo", "eigentuemer", sofort_bereit=False)
        datei = sicherung.sichern(self.kern)
        self.assertTrue(sicherung.pruefen(datei))
        self.kern.aufgaben.anlegen("Später", "kennzahlen", "ceo", "eigentuemer", sofort_bereit=False)
        self.kern.db.schliessen()
        sicherung.wiederherstellen(datei)
        self.neu_starten_ohne_schliessen()
        titel = [a["titel"] for a in self.kern.aufgaben.liste()]
        self.assertEqual(titel, ["Bleibt"])
        self.assertEqual(self.kern.aufgaben.hole(aid)["status"], "geplant")

    def neu_starten_ohne_schliessen(self):
        from autonomous.kern import Kern
        from autonomous.orchestrator import Orchestrator
        self.kern = Kern()
        self.orch = Orchestrator(self.kern)

    def test_beschaedigte_sicherung_wird_abgelehnt(self):
        import os
        from autonomous import konfig, sicherung
        kaputt = os.path.join(konfig.unterordner("sicherungen"), "autonomous-kaputt.db")
        with open(kaputt, "wb") as f:
            f.write(b"kein sqlite")
        with self.assertRaises(ValueError):
            sicherung.wiederherstellen("autonomous-kaputt.db")
        with self.assertRaises(ValueError):
            sicherung.wiederherstellen("../../etc/passwd")

    def test_export_enthaelt_kennzeichnung(self):
        import json
        from autonomous import sicherung
        with open(sicherung.exportieren(self.kern), encoding="utf-8") as f:
            daten = json.load(f)
        self.assertIn("SIMULATION", daten["hinweis"])
        self.assertEqual(len(daten["wallet_buchungen"]), 1)

    def test_migration_idempotent(self):
        from autonomous.db import Datenbank
        db2 = Datenbank(self.kern.db.pfad)
        self.assertEqual(db2.schema_version(), self.kern.db.schema_version())
        db2.schliessen()

    def test_db_integritaet(self):
        self.assertTrue(self.kern.db.integritaet())
        con = sqlite3.connect(self.kern.db.pfad)
        self.assertEqual(con.execute("PRAGMA journal_mode").fetchone()[0], "wal")
        con.close()
