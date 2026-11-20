# -*- coding: utf-8 -*-
"""Wallet (SIMULATION) und reale Finanzen – strikt getrennt (Abschnitte 6, 7, 13)."""

import sqlite3

from autonomous.tests.hilfe import KernTest


class TestWallet(KernTest):
    def test_startwert_15_euro_als_simulation(self):
        u = self.kern.wallet.uebersicht()
        self.assertEqual(u["stand_cent"], 1500)
        self.assertEqual(u["kennzeichen"], "SIMULATION")
        b = self.kern.wallet.historie()[0]
        self.assertEqual(b["simulation"], 1)
        self.assertEqual(b["art"], "startwert")

    def test_startwert_nur_einmal(self):
        self.neu_starten()
        self.kern.wallet.einrichten()
        self.assertEqual(self.kern.wallet.stand_cent(), 1500)

    def test_buchung_hat_alle_pflichtangaben(self):
        r = self.kern.wallet.buchen("ausgabe", "2,50", "test", "Testkauf", "eigentuemer")
        b = self.kern.db.eins("SELECT * FROM wallet_buchungen WHERE id=?", (r["id"],))
        for feld in ("id", "zeit", "betrag_cent", "waehrung", "kategorie", "status", "begruendung"):
            self.assertTrue(b[feld] not in (None, ""), feld)
        self.assertEqual(b["betrag_cent"], -250)
        self.assertEqual(self.kern.wallet.stand_cent(), 1250)

    def test_historie_unveraenderbar(self):
        r = self.kern.wallet.buchen("ausgabe", "1", "test", "x", "eigentuemer")
        with self.assertRaises(sqlite3.DatabaseError):
            self.kern.db.ausfuehren("UPDATE wallet_buchungen SET betrag_cent=0 WHERE id=?", (r["id"],))
        with self.assertRaises(sqlite3.DatabaseError):
            self.kern.db.ausfuehren("DELETE FROM wallet_buchungen WHERE id=?", (r["id"],))

    def test_korrektur_per_gegenbuchung(self):
        r = self.kern.wallet.buchen("ausgabe", "5", "test", "Tippfehler", "eigentuemer")
        self.kern.wallet.gegenbuchung(r["id"], "Korrektur", "eigentuemer")
        self.assertEqual(self.kern.wallet.stand_cent(), 1500)
        with self.assertRaises(ValueError):
            self.kern.wallet.gegenbuchung(r["id"], "nochmal", "eigentuemer")
        self.assertEqual(len(self.kern.wallet.historie()), 3)

    def test_budgetwarnung(self):
        self.kern.finanzen.budget_setzen("wallet", "werkzeuge", "3", "monat", "eigentuemer")
        r1 = self.kern.wallet.buchen("ausgabe", "2", "werkzeuge", "a", "eigentuemer")
        self.assertFalse([w for w in r1["warnungen"] if "Budget" in w])
        r2 = self.kern.wallet.buchen("ausgabe", "2", "werkzeuge", "b", "eigentuemer")
        self.assertTrue([w for w in r2["warnungen"] if "Budget überschritten" in w])

    def test_deutsche_betragsschreibweise(self):
        from autonomous.wallet import betrag_in_cent, euro
        self.assertEqual(euro(125050), "1.250,50 €")
        self.assertEqual(euro(-123456789), "-1.234.567,89 €")
        self.assertEqual(euro(5), "0,05 €")
        for eingabe, cent in (("12,50", 1250), ("1.000", 100000), ("1.234,56", 123456), ("12.5", 1250),
                              ("7", 700), ("3 €", 300), (2.5, 250)):
            self.assertEqual(betrag_in_cent(eingabe), cent, eingabe)
        for falsch in ("1,2,3", "12a", "1e5", "--1", ""):
            with self.assertRaises(ValueError, msg=falsch):
                betrag_in_cent(falsch)

    def test_ungueltige_betraege(self):
        for wert in ("0", "-5", "abc", True, "99999999"):
            with self.assertRaises(ValueError, msg=str(wert)):
                self.kern.wallet.buchen("ausgabe", wert, "x", "y", "eigentuemer")

    def test_null_guthaben_stoppt_keine_kernfunktionen(self):
        self.kern.wallet.buchen("ausgabe", "15", "test", "alles weg", "eigentuemer")
        self.kern.wallet.buchen("ausgabe", "10", "test", "ins Minus", "eigentuemer")
        self.assertEqual(self.kern.wallet.stand_cent(), -1000)
        self.assertEqual(self.kern.status()["betrieb"], "laeuft")
        for rolle, typ in (("ceo", "tagesplan"), ("ceo", "kennzahlen"), ("finance", "finanzbericht"),
                           ("learning", "auswertung")):
            self.kern.aufgaben.anlegen(typ, typ, rolle, "eigentuemer")
        self.orch.alle_abarbeiten()
        self.assertEqual(self.kern.aufgaben.zaehlen()["abgeschlossen"], 4)
        self.assertEqual(self.kern.aufgaben.zaehlen()["fehlgeschlagen"], 0)

    def test_finance_agent_bucht_nur_simulation(self):
        self.kern.aufgaben.anlegen("Sim", "simulation_buchen", "finance", "eigentuemer",
                                   {"art": "ausgabe", "betrag": "1,00", "kategorie": "test", "begruendung": "Probe"})
        self.orch.alle_abarbeiten()
        self.assertEqual(self.kern.wallet.stand_cent(), 1400)
        self.assertEqual(self.kern.db.wert("SELECT COUNT(*) FROM real_buchungen"), 0)


class TestRealeFinanzen(KernTest):
    def test_einnahme_nur_mit_zahlungsnachweis(self):
        with self.assertRaises(ValueError):
            self.kern.finanzen.einnahme("100", "webseite", "Kunde", "Zahlung", "eigentuemer", "", "Vater")
        with self.assertRaises(ValueError):
            self.kern.finanzen.einnahme("100", "webseite", "Kunde", "Zahlung", "eigentuemer", "Kontoauszug 3/11", "")
        # auch direkt in der Datenbank nicht möglich
        with self.assertRaises(sqlite3.IntegrityError):
            self.kern.db.ausfuehren("INSERT INTO real_buchungen (id, nr, zeit, datum, art, betrag_cent, kategorie,"
                                    " gegenpartei, begruendung, akteur) VALUES ('x',1,'t','2026-11-20','einnahme',"
                                    "100,'k','g','b','a')")

    def test_agent_darf_nicht_real_buchen(self):
        with self.assertRaises(PermissionError):
            self.kern.finanzen.ausgabe("10", "x", "y", "z", "finance")
        with self.assertRaises(PermissionError):
            self.kern.finanzen.einnahme("10", "x", "y", "z", "sales", "Beleg", "ich")

    def test_forderung_ist_keine_einnahme(self):
        fid = self.kern.finanzen.forderung_anlegen("Muster GmbH", "499", "eigentuemer")
        u = self.kern.finanzen.uebersicht()
        self.assertEqual(u["einnahmen_verifiziert_cent"], 0)
        self.assertEqual(u["offene_forderungen_cent"], 49900)
        self.kern.finanzen.forderung_bezahlt(fid, "Kontoauszug Nr. 12", "Vater", "eigentuemer")
        u = self.kern.finanzen.uebersicht()
        self.assertEqual(u["einnahmen_verifiziert_cent"], 49900)
        self.assertEqual(u["offene_forderungen_cent"], 0)
        with self.assertRaises(ValueError):
            self.kern.finanzen.forderung_bezahlt(fid, "nochmal", "Vater", "eigentuemer")

    def test_keine_vermischung(self):
        self.kern.wallet.buchen("einnahme", "100", "test", "simuliert", "eigentuemer")
        self.assertEqual(self.kern.finanzen.uebersicht()["einnahmen_verifiziert_cent"], 0)
        self.kern.finanzen.ausgabe("20", "material", "Baumarkt", "Kauf", "eigentuemer")
        self.assertEqual(self.kern.wallet.stand_cent(), 11500)
        # Simulation kann nicht in die reale Tabelle, Realität nicht ins Wallet
        with self.assertRaises(sqlite3.IntegrityError):
            self.kern.db.ausfuehren("INSERT INTO wallet_buchungen (id, nr, zeit, betrag_cent, kategorie, art,"
                                    " begruendung, simulation, akteur) VALUES ('x',99,'t',1,'k','einnahme','b',0,'a')")
        with self.assertRaises(sqlite3.IntegrityError):
            self.kern.db.ausfuehren("INSERT INTO real_buchungen (id, nr, zeit, datum, art, betrag_cent, kategorie,"
                                    " gegenpartei, begruendung, akteur, simulation) VALUES ('y',99,'t','2026-11-20',"
                                    "'ausgabe',-1,'k','g','b','a',1)")

    def test_reale_buchungen_unveraenderbar_und_gegenbuchung(self):
        bid = self.kern.finanzen.ausgabe("20", "material", "Baumarkt", "Kauf", "eigentuemer")
        with self.assertRaises(sqlite3.DatabaseError):
            self.kern.db.ausfuehren("DELETE FROM real_buchungen WHERE id=?", (bid,))
        self.kern.finanzen.gegenbuchung(bid, "falsch erfasst", "eigentuemer")
        self.assertEqual(self.kern.finanzen.uebersicht()["saldo_cent"], 0)

    def test_realbudget(self):
        self.kern.finanzen.budget_setzen("real", "material", "10", "monat", "eigentuemer")
        self.kern.finanzen.ausgabe("20", "material", "Baumarkt", "Kauf", "eigentuemer")
        b = self.kern.finanzen.uebersicht()["budgets"][0]
        self.assertTrue(b["ueberschritten"])
