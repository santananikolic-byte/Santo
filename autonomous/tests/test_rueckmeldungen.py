# -*- coding: utf-8 -*-
"""Rückmeldungen echter Interessenten (PDF 2.3: „Miss Reaktionen und verbessere das Angebot anhand realer
Rückmeldungen“) – Erfassen, Prüfen, Auswerten, Migration 2 → 3."""

import json
import os
import sqlite3

from autonomous import api, db as db_modul
from autonomous.db import jetzt
from autonomous.tests.hilfe import KernTest


class RmTest(KernTest):
    def kontakt(self, firma="Muster Hausverwaltung"):
        return self.api("POST", "/api/kontakte", {"firma": firma, "quelle": "persönliches Gespräch"})["id"]

    def angebot(self, kontakt_id=None):
        aid = "an_test%06d" % len(self.kern.db.alle("SELECT id FROM angebote"))
        z = jetzt()
        self.kern.db.ausfuehren("INSERT INTO angebote (id, kontakt_id, produkt_id, titel, betrag_cent, status, inhalt,"
                                " datei, erstellt, aktualisiert) VALUES (?,?,?,?,?,?,?,?,?,?)",
                                (aid, kontakt_id, None, "Google-Profil-Paket", 24900, "entwurf", "{}", None, z, z))
        return aid

    def erfassen(self, **felder):
        daten = {"angebot_art": "google_profil", "kanal": "gespraech", "reaktion": "interessiert"}
        daten.update(felder)
        daten = {k: v for k, v in daten.items() if v is not None}
        return self.api("POST", "/api/rueckmeldungen", daten)["id"]

    def fehler(self, **felder):
        with self.assertRaises(api.ApiFehler) as f:
            self.erfassen(**felder)
        return f.exception.status

    def auswerten(self):
        aid = self.api("POST", "/api/rueckmeldungen/auswerten")["aufgabe_id"]
        self.orch.alle_abarbeiten()
        a = self.kern.aufgaben.hole(aid)
        self.assertEqual(a["status"], "abgeschlossen", a["fehler"])
        return a["ergebnis"]


class TestErfassen(RmTest):
    def test_erfassen_und_liste(self):
        kid = self.kontakt()
        rid = self.erfassen(kontakt_id=kid, reaktion="abgelehnt", grund="preis", notiz="Zu teuer für zwei Objekte")
        liste = self.api("GET", "/api/rueckmeldungen")
        self.assertEqual(liste["rueckmeldungen"][0]["id"], rid)
        self.assertEqual(liste["rueckmeldungen"][0]["kontakt_firma"], "Muster Hausverwaltung")
        self.assertEqual(liste["rueckmeldungen"][0]["erfasst_von"], "eigentuemer")
        self.assertEqual(liste["reaktionen"], ["interessiert", "neutral", "abgelehnt", "keine_antwort"])
        self.assertEqual(liste["gruende"], ["preis", "kein_bedarf", "spaeter", "hat_anbieter", "vertrauen",
                                            "leistung_unklar", "sonstiges"])
        self.assertEqual(liste["kanaele"], ["gespraech", "telefon", "brief", "email", "vor_ort", "sonstiges"])
        self.assertEqual(liste["angebot_arten"], ["google_profil", "webseite", "reinigung", "sonstiges"])

    def test_ohne_kontakt_und_angebot_erlaubt(self):
        rid = self.erfassen(kanal="vor_ort", reaktion="keine_antwort")
        self.assertIsNone(self.kern.db.eins("SELECT kontakt_id FROM rueckmeldungen WHERE id=?", (rid,))["kontakt_id"])

    def test_validierung(self):
        self.assertEqual(self.fehler(angebot_art=None), 400)
        self.assertEqual(self.fehler(angebot_art="auto"), 400)
        self.assertEqual(self.fehler(kanal="fax"), 400)
        self.assertEqual(self.fehler(reaktion="begeistert"), 400)
        self.assertEqual(self.fehler(reaktion="abgelehnt", grund="wetter"), 400)
        # Ein Grund passt nur zu „abgelehnt“ oder „neutral“ – Entscheidung: 400 statt still ignorieren
        self.assertEqual(self.fehler(reaktion="interessiert", grund="preis"), 400)
        self.assertEqual(self.fehler(reaktion="keine_antwort", grund="spaeter"), 400)
        self.assertEqual(self.fehler(notiz="x" * 2001), 400)
        self.assertEqual(self.kern.db.wert("SELECT COUNT(*) FROM rueckmeldungen"), 0)
        # leerer Grund zählt als „kein Grund“
        self.erfassen(reaktion="interessiert", grund="")
        self.erfassen(reaktion="neutral", grund="spaeter")

    def test_datensparsamkeit_in_notiz(self):
        self.assertEqual(self.fehler(notiz="Bitte an max@example.org schreiben"), 400)
        self.assertEqual(self.fehler(notiz="Rückruf unter 0214 1234567"), 400)
        self.assertEqual(self.fehler(notiz="Handy +49 171 2345678"), 400)
        # Daten, Preise und kurze Zahlen sind erlaubt
        self.erfassen(notiz="Termin am 01.12.2026, Angebot 2026-12-01, Preis 1.250,50 €, Objekt Nr. 0815")

    def test_unbekannter_kontakt_oder_angebot(self):
        self.assertEqual(self.fehler(kontakt_id="k_gibtsnicht"), 404)
        self.assertEqual(self.fehler(angebot_id="an_gibtsnicht"), 404)

    def test_angebot_bringt_kontakt_mit_und_fremder_kontakt_abgelehnt(self):
        kid = self.kontakt()
        anderer = self.kontakt("Andere GmbH")
        an = self.angebot(kid)
        rid = self.erfassen(angebot_id=an)
        self.assertEqual(self.kern.db.wert("SELECT kontakt_id FROM rueckmeldungen WHERE id=?", (rid,)), kid)
        self.assertEqual(self.fehler(angebot_id=an, kontakt_id=anderer), 400)

    def test_datenbank_erzwingt_regeln(self):
        sql = ("INSERT INTO rueckmeldungen (id, zeit, angebot_art, kanal, reaktion, grund, erfasst_von) "
               "VALUES (?,?,?,?,?,?,?)")
        for werte in (("a", jetzt(), "google_profil", "brief", "interessiert", "preis", "eigentuemer"),
                      ("b", jetzt(), "google_profil", "brief", "begeistert", None, "eigentuemer"),
                      ("c", jetzt(), "auto", "brief", "neutral", None, "eigentuemer")):
            with self.assertRaises(sqlite3.IntegrityError, msg=werte[0]):
                self.kern.db.ausfuehren(sql, werte)

    def test_protokoll_ohne_notiztext(self):
        self.erfassen(notiz="Geheimer Grund: Chef mag keine Änderungen")
        eintrag = [e for e in self.kern.protokoll.liste("audit") if e["ereignis"] == "Rückmeldung erfasst"][0]
        self.assertNotIn("Chef mag", eintrag["details"] or "")


class TestAuswertung(RmTest):
    def test_ohne_daten_ehrlich(self):
        e = self.auswerten()
        self.assertEqual(e["gesamt"], 0)
        self.assertEqual(e["vorschlaege"], [])
        self.assertIn("Keine Rückmeldungen erfasst", e["hinweis"])
        self.assertEqual(self.kern.gedaechtnis.liste("vorschlag"), [])

    def test_zahlen_exakt(self):
        for reaktion, grund in (("interessiert", None), ("interessiert", None), ("abgelehnt", "preis"),
                                ("abgelehnt", "preis"), ("abgelehnt", "kein_bedarf"), ("keine_antwort", None)):
            self.erfassen(reaktion=reaktion, grund=grund)
        # Webseite: unter der Schwelle – trotz zweimal „leistung_unklar“ kein Vorschlag
        self.erfassen(angebot_art="webseite", reaktion="neutral", grund="leistung_unklar")
        self.erfassen(angebot_art="webseite", reaktion="abgelehnt", grund="leistung_unklar")
        e = self.auswerten()
        self.assertEqual(e["gesamt"], 8)
        g = e["je_angebot"]["google_profil"]
        self.assertEqual(g["anzahl"], 6)
        self.assertEqual(g["reaktionen"], {"interessiert": 2, "neutral": 0, "abgelehnt": 3, "keine_antwort": 1})
        self.assertEqual(g["quote_interessiert_prozent"], 33)
        self.assertEqual(g["gruende"], [["preis", 2], ["kein_bedarf", 1]])
        self.assertTrue(g["aussagekraeftig"])
        w = e["je_angebot"]["webseite"]
        self.assertFalse(w["aussagekraeftig"])
        self.assertIn("noch nicht aussagekräftig", w["hinweis"])
        self.assertEqual(len(e["vorschlaege"]), 1)
        self.assertIn("Google-Profil-Paket: häufigster Grund „preis“ (2 von 6 Rückmeldungen)", e["vorschlaege"][0])
        self.assertIn("Entscheidung Inhaber", e["vorschlaege"][0])
        gespeichert = self.kern.gedaechtnis.liste("vorschlag")
        self.assertEqual(len(gespeichert), 1)
        self.assertEqual(gespeichert[0]["thema"], "Rückmeldungen")
        self.assertEqual(gespeichert[0]["autor"], "learning")

    def test_vorschlag_erst_ab_schwelle(self):
        for _ in range(4):
            self.erfassen(reaktion="abgelehnt", grund="preis")
        self.assertEqual(self.auswerten()["vorschlaege"], [])
        self.erfassen(reaktion="abgelehnt", grund="preis")
        vorschlaege = self.auswerten()["vorschlaege"]
        self.assertEqual(len(vorschlaege), 1)
        self.assertIn("(5 von 5 Rückmeldungen)", vorschlaege[0])

    def test_leistung_unklar_und_keine_antwort(self):
        for reaktion, grund in (("neutral", "leistung_unklar"), ("abgelehnt", "leistung_unklar"),
                                ("keine_antwort", None), ("keine_antwort", None), ("keine_antwort", None)):
            self.erfassen(angebot_art="reinigung", kanal="brief", reaktion=reaktion, grund=grund)
        vorschlaege = self.auswerten()["vorschlaege"]
        self.assertEqual(len(vorschlaege), 2)
        self.assertIn("Leistungsbeschreibung und Verkaufsseite verständlicher machen", vorschlaege[0])
        self.assertIn("3 von 5 ohne Antwort", vorschlaege[1])

    def test_aendert_nichts_selbst(self):
        kid = self.kontakt()
        self.angebot(kid)
        for _ in range(6):
            self.erfassen(kontakt_id=kid, reaktion="abgelehnt", grund="preis")
        vorher = (self.kern.einstellungen.alle(), self.kern.db.alle("SELECT * FROM angebote"),
                  self.kern.db.alle("SELECT * FROM kontakte"), self.kern.db.alle("SELECT * FROM rueckmeldungen"),
                  self.kern.db.alle("SELECT * FROM ziele"))
        self.assertTrue(self.auswerten()["vorschlaege"])
        nachher = (self.kern.einstellungen.alle(), self.kern.db.alle("SELECT * FROM angebote"),
                   self.kern.db.alle("SELECT * FROM kontakte"), self.kern.db.alle("SELECT * FROM rueckmeldungen"),
                   self.kern.db.alle("SELECT * FROM ziele"))
        self.assertEqual(vorher, nachher)

    def test_agent_kann_keine_rueckmeldung_erfinden(self):
        # Rückmeldungen legt im gesamten Code nur die Eigentümer-Route in api_vertrieb.py an – kein Agent
        from autonomous import konfig
        fundstellen = []
        for wurzel, _, dateien in os.walk(konfig.PAKET):
            if os.sep + "tests" in wurzel:
                continue
            for d in dateien:
                if d.endswith(".py"):
                    with open(os.path.join(wurzel, d), encoding="utf-8") as f:
                        if "INSERT INTO rueckmeldungen" in f.read():
                            fundstellen.append(d)
        self.assertEqual(fundstellen, ["api_vertrieb.py"])
        agent = self.kern.register.hole("learning")
        self.assertEqual(agent.rechte, frozenset({"interne_auswertung", "gedaechtnis_vorschlag"}))


class TestMigration(KernTest):
    def test_bestehende_datenbank_2_auf_3_ohne_datenverlust(self):
        pfad = os.path.join(os.environ["AUTONOMOUS_DATEN"], "alt.db")
        voll = db_modul.MIGRATIONEN
        try:
            db_modul.MIGRATIONEN = voll[:2]
            alt = db_modul.Datenbank(pfad)
            self.assertEqual(alt.schema_version(), 2)
            z = jetzt()
            alt.ausfuehren("INSERT INTO kontakte (id, firma, quelle, erstellt, aktualisiert) VALUES (?,?,?,?,?)",
                           ("k_alt", "Bestandskunde GmbH", "Altdaten", z, z))
            alt.ausfuehren("INSERT INTO ziele VALUES (?,?,?,?,?,?,?)", ("z_alt", "Altes Ziel", "", 2, "aktiv", z, z))
            self.assertIsNone(alt.wert("SELECT name FROM sqlite_master WHERE name='rueckmeldungen'"))
            alt.schliessen()
        finally:
            db_modul.MIGRATIONEN = voll
        neu = db_modul.Datenbank(pfad)
        try:
            self.assertEqual(neu.schema_version(), 3)
            self.assertEqual(neu.wert("SELECT firma FROM kontakte WHERE id='k_alt'"), "Bestandskunde GmbH")
            self.assertEqual(neu.wert("SELECT titel FROM ziele WHERE id='z_alt'"), "Altes Ziel")
            neu.ausfuehren("INSERT INTO rueckmeldungen (id, zeit, kontakt_id, angebot_art, kanal, reaktion, "
                           "erfasst_von) VALUES ('r1', ?, 'k_alt', 'reinigung', 'brief', 'interessiert', 'eigentuemer')",
                           (jetzt(),))
            self.assertTrue(neu.integritaet())
            self.assertEqual(json.loads(json.dumps(neu.alle("SELECT id FROM rueckmeldungen"))), [{"id": "r1"}])
        finally:
            neu.schliessen()
