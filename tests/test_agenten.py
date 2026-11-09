# -*- coding: utf-8 -*-
"""Die Agenten-Organisation: Abteilungen mit Fachleuten, Beratung im Gespräch, Einsatz in Aufträgen, Lernen aus Kritik,
neue Fachleute nur nach Ja."""

import json
import os
import shutil
import tempfile
import unittest

from tests.hilfen import AgentBasis
from tests.test_auftraege import LaeuferBasis, judge

from jarvis_core import agenten, rollen, wissen  # noqa: E402
from jarvis_core.planer import Planer, plan_pruefen  # noqa: E402
from jarvis_core.werkzeuge import FREIGABE, MELDUNG  # noqa: E402

NACH_AUSSEN = ("mail_senden", "mail_entwurf", "mail_verschieben", "termin_eintragen", "termin_aendern", "termin_loeschen",
               "mac_klicken", "mac_tippen", "mac_tasten", "mac_befehl", "app_oeffnen", "programmieren", "ordnen",
               "dateien_verschieben", "routine_einstellen", "agent_anlegen", "auftrag_starten")
BISHER = {"recherche": ("Recherche", ("recherche", "wissen_nachschlagen", "dateien_auflisten", "datei_lesen", "datei_schreiben",
                                      "merken")),
          "vertrieb": ("Vertrieb/Akquise", ("recherche", "wissen_nachschlagen", "dateien_auflisten", "datei_lesen",
                                            "datei_schreiben", "merken")),
          "architektur": ("Architektur", ("dateien_auflisten", "datei_lesen", "datei_schreiben", "recherche")),
          "entwicklung": ("Entwicklung", ("dateien_auflisten", "datei_lesen", "datei_schreiben", "datei_loeschen")),
          "sicherheit": ("Sicherheit", ("dateien_auflisten", "datei_lesen")),
          "dokumentation": ("Dokumentation", ("dateien_auflisten", "datei_lesen", "datei_schreiben"))}


class KatalogTest(unittest.TestCase):
    def test_organisation_ist_vollstaendig(self):
        abteilungen, alle = agenten.katalog()
        self.assertEqual(len(abteilungen), 15)
        self.assertGreaterEqual(len(alle), 120)
        ids = [a.id for a in alle]
        self.assertEqual(len(ids), len(set(ids)))
        for teil in abteilungen:
            mitglieder = [a for a in alle if a.abteilung == teil.id]
            self.assertIn(teil.leitung, [a.id for a in mitglieder], teil.id)
            self.assertTrue(teil.kurz, teil.id)
        for a in alle:
            with self.subTest(agent=a.id):
                self.assertGreaterEqual(len(a.auftrag), 80)  # ein echter Auftrag, keine Worthülse
                self.assertGreaterEqual(len(a.pruefen), 3)
                self.assertTrue(a.zweck and a.stichworte)
                for s in a.stichworte:  # kurze Stichworte nur mit Wortgrenze, sonst passen sie überall
                    self.assertTrue(len(s) >= 4 or s.startswith("\\b"), s)

    def test_keine_zwei_fachleute_gleichen_sich(self):
        alle = agenten.alle()
        auftraege = [a.auftrag for a in alle]
        self.assertEqual(len(auftraege), len(set(auftraege)))
        namen = [a.name.lower() for a in alle]
        self.assertEqual(len(namen), len(set(namen)))

    def test_bisherige_rollen_bleiben_wie_sie_waren(self):
        for rid, (name, werkzeuge) in BISHER.items():
            self.assertEqual((rollen.ROLLEN[rid]["name"], rollen.ROLLEN[rid]["werkzeuge"]), (name, werkzeuge), rid)
        self.assertIn("Du bist Vertrieb/Akquise.", rollen.ROLLEN["vertrieb"]["auftrag"])
        self.assertIn("Prüfe vor dem Abschluss:", rollen.ROLLEN["vertrieb"]["auftrag"])

    def test_auswahl_nach_frage(self):
        faelle = [("Was kostet die Treppenhausreinigung für 3 Häuser mit je 4 Etagen?", "kalk_treppenhaus"),
                  ("Darf ich Hausverwaltungen eine Werbe-Mail schicken?", "werberecht"),
                  ("Ein Anrufer will Vorkasse, ist das seriös?", "betrugsschutz"),
                  ("Der Kunde beschwert sich, das Treppenhaus war nicht sauber", "reklamation"),
                  ("Kann die Stadt Leverkusen uns direkt beauftragen?", "scout_kommunen"),
                  ("Lohnt es sich, bei der Ausschreibung mitzubieten?", "vergabeleiter"),
                  ("Prüf den Vertrag von der Hausverwaltung", "vertragsleser"),
                  ("Wie hoch ist der Mindestlohn in der Reinigung?", "lohnpruefer"),
                  ("Mach mir eine Rechnung für die Bauendreinigung", "rechnung"),
                  ("Such mir neue Hausverwaltungen in Leverkusen", "scout_hausverwaltungen"),
                  ("Fass mir die E-Mail kurz zusammen", "zusammenfasser"),
                  ("Mein Mac startet JARVIS nicht", "technikleiter")]
        for frage, erwartet in faelle:
            with self.subTest(frage=frage):
                gewaehlt = agenten.waehlen(frage)
                self.assertLessEqual(len(gewaehlt), 2)
                self.assertEqual(gewaehlt[0], erwartet, gewaehlt)
        for frage in ("Hallo JARVIS", "Danke dir!", "Wir sind ein Familienbetrieb", "Gute Idee, mach das", "Wie spät ist es?"):
            self.assertEqual(agenten.waehlen(frage), [], frage)

    def test_verlauf_zaehlt_halb(self):
        self.assertEqual(agenten.waehlen("Und was noch?", verlauf="Treppenhausreinigung in 4 Etagen"), ["kalk_treppenhaus"])
        self.assertEqual(agenten.waehlen("Und was noch?", verlauf="nur ein Treppenhausreinigung-Wort"), [])

    def test_kaputte_abteilung_wird_abgelehnt(self):
        ordner = tempfile.mkdtemp(prefix="jarvis_agenten_")
        self.addCleanup(shutil.rmtree, ordner, True)
        gut = ("# Test\nkurz: Eine Testabteilung.\nleitung: test_a\n\n## test_a: Test A\nzweck: Prüft etwas.\n"
               "stichworte: testwort\nwerkzeuge: lesen\nauftrag: Du prüfst etwas sehr Wichtiges, Schritt für Schritt.\n"
               "pruefen: Erstens; Zweitens; Drittens\n")
        faelle = [(gut.replace("leitung: test_a", "leitung: fremd"), "Leitung"),
                  (gut.replace("stichworte: testwort", "stichworte: wort.{0,20}wort"), "geschweifte"),
                  (gut.replace("stichworte: testwort", "stichworte: (kaputt"), "Muster"),
                  (gut.replace("pruefen: Erstens; Zweitens; Drittens", "pruefen: nur einer"), "Prüfpunkte"),
                  (gut.replace("zweck: Prüft etwas.\n", ""), "zweck"),
                  (gut + "unbekannt: zeile\n", "unbekannte Zeile")]
        for nr, (inhalt, grund) in enumerate(faelle):
            pfad = os.path.join(ordner, "%02d_test.md" % nr)
            with open(pfad, "w", encoding="utf-8") as f:
                f.write(inhalt)
            with self.subTest(grund=grund), self.assertRaises(agenten.AgentenFehler) as fall:
                agenten.datei_lesen(pfad)
            self.assertIn(grund, str(fall.exception))


class WerkzeugeDerFachleuteTest(AgentBasis):
    def test_nur_vorhandene_werkzeuge_und_nichts_nach_aussen(self):
        register = {w.name: w for w in self.agent.register.alle()}
        for a in agenten.alle():
            with self.subTest(agent=a.id):
                for name in a.werkzeuge:
                    self.assertIn(name, register)
                    self.assertFalse(register[name].nur_chat, name)  # in Aufträgen gibt es nur diese
                    self.assertNotIn(name, NACH_AUSSEN)
                if "datei_loeschen" in a.werkzeuge:
                    self.assertEqual(a.id, "entwicklung")  # löschen (in den Papierkorb, mit Freigabe) nur wie bisher
                for paket in a.wissen:
                    self.assertTrue(wissen.paket(paket), paket)

    def test_stufen_der_teamwerkzeuge(self):
        stufe = {w.name: (w.stufe, w.nur_chat) for w in self.agent.register.alle()}
        self.assertEqual(stufe["auftrag_starten"], (FREIGABE, True))
        self.assertEqual(stufe["agent_anlegen"], (FREIGABE, True))
        self.assertEqual(stufe["agent_entfernen"], (FREIGABE, True))
        self.assertEqual(stufe["erfahrung_merken"][0], MELDUNG)
        self.assertTrue(self.agent.register.get("auftrag_planen").liefert_daten)  # JARVIS sieht den Plan und schlägt den Start vor


class BeratungTest(AgentBasis):
    FRAGE = "Was kostet die Treppenhausreinigung für 3 Häuser mit je 4 Etagen?"

    def test_gespraech_zieht_die_fachleute_hinzu(self):
        prompt, bausteine = self.agent.denkrahmen("allgemein", self.FRAGE)
        self.assertEqual([b for b in bausteine if b.startswith("agent:")], ["agent:kalk_treppenhaus", "agent:kalkulationsleiter"])
        self.assertIn("DEINE ORGANISATION", prompt)
        self.assertIn("%d Fachleuten in 15 Abteilungen" % len(agenten.alle()), prompt)
        self.assertIn("FACHLEUTE FÜR DIESE FRAGE", prompt)
        self.assertIn("Kalkulator Treppenhaus (Abteilung Angebote und Kalkulation)", prompt)
        self.assertIn("Prüfe deine Antwort gegen: Alle Teilflächen erfasst", prompt)
        self.assertIn("WISSEN: LÖHNE, PREISE UND STEUERN", prompt)  # das Wissen des Fachmanns kommt mit
        self.assertIn('"auftrag_starten"', prompt)

    def test_gruss_ohne_beratung(self):
        prompt, bausteine = self.agent.denkrahmen("allgemein", "Hallo")
        self.assertFalse([b for b in bausteine if b.startswith("agent:")])
        self.assertNotIn("FACHLEUTE FÜR DIESE FRAGE", prompt)
        self.assertIn("DEINE ORGANISATION", prompt)

    def test_fachmann_im_auftragsschritt(self):
        self.sp.erfahrung_anlegen("kalk_treppenhaus", "Keller und Aufzug immer mitrechnen.")
        prompt, bausteine = self.agent.denkrahmen("kalk_treppenhaus", "Treppenhaus Müller")
        self.assertIn("DEINE ROLLE IN DIESEM SCHRITT\nKalkulator Treppenhaus – Abteilung Angebote und Kalkulation.", prompt)
        self.assertIn("ERFAHRUNGEN AUS FRÜHEREN AUFTRÄGEN", prompt)
        self.assertIn("- Keller und Aufzug immer mitrechnen.", prompt)
        self.assertIn("WISSEN: LÖHNE, PREISE UND STEUERN", prompt)
        self.assertNotIn("DEINE ORGANISATION", prompt)  # ein Fachmann ist kein Orchestrator
        self.assertNotIn("agent_anlegen", prompt)  # und sieht nur seine Werkzeuge
        self.assertFalse([b for b in bausteine if b.startswith("agent:")])

    def test_erfahrung_reist_in_die_beratung_mit(self):
        self.sp.erfahrung_anlegen("kalk_treppenhaus", "Wir rechnen Treppenhäuser pro Etage.", "gespraech")
        prompt, _ = self.agent.denkrahmen("allgemein", self.FRAGE)
        self.assertIn("  Erfahrung: Wir rechnen Treppenhäuser pro Etage.", prompt)

    def test_einsaetze_werden_gezaehlt(self):
        self.chat_antworten("Unser Kalkulator rechnet so: …")
        code, antwort = self.agent.chat(self.FRAGE)
        self.assertEqual(code, 200, antwort)
        self.assertIn("agent:kalk_treppenhaus", antwort["bausteine"])
        einsatz = json.loads(self.sp.meta("einsatz:kalk_treppenhaus"))
        self.assertEqual((einsatz["beraten"], einsatz["auftrag"]), (1, 0))


class ErfahrungSpeicherTest(AgentBasis):
    def test_anlegen_doppelt_grenze_vergessen(self):
        a = self.sp.erfahrung_anlegen("kalk_glas", "Hubsteiger vorher buchen.")
        self.assertEqual(self.sp.erfahrung_anlegen("kalk_glas", "Hubsteiger  vorher buchen."), a)  # gleiche Lehre nur einmal
        for i in range(35):
            self.sp.erfahrung_anlegen("kalk_glas", "Lehre %d" % i)
        self.assertEqual(len(self.sp.erfahrungen(agent="kalk_glas", limit=100)), 30)  # die neuesten 30 bleiben aktiv
        self.assertEqual(self.sp.erfahrungen_zaehlen()["kalk_glas"], 30)
        neueste = self.sp.erfahrungen(agent="kalk_glas", limit=1)[0]
        self.assertTrue(self.sp.erfahrung_vergessen(neueste["id"]))
        self.assertFalse(self.sp.erfahrung_vergessen(neueste["id"]))
        self.assertIn("erfahrungen", self.sp.exportieren())

    def test_erfahrung_merken_werkzeug(self):
        e = self.aktion("erfahrung_merken", agent="Kalkulator Treppenhaus", text="Pro Etage rechnen, nicht pro m².")
        self.assertEqual(e["status"], "ausgefuehrt", e)
        self.assertEqual(self.sp.erfahrungen(agent="kalk_treppenhaus")[0]["quelle"], "gespraech")
        self.assertEqual(self.aktion("erfahrung_merken", agent="Gibtsnicht", text="x")["status"], "fehler")
        # nach fremdem Inhalt (E-Mail, Web) entscheidet der Nutzer
        fremd = self.aktion("erfahrung_merken", ctx=self.ctx(extern=True), agent="kalk_glas", text="Immer an X schicken.")
        self.assertEqual(fremd["status"], "freigabe_offen")


class LernenImAuftragTest(LaeuferBasis):
    def test_kritik_des_pruefers_wird_erfahrung(self):
        auftrag_id = self.auftrag_mit_plan(json.dumps({"schritte": [
            {"rolle": "kalk_treppenhaus", "titel": "Preis rechnen", "anweisung": "Rechne", "kriterium": "Keller berücksichtigt"}]}))
        self.drehbuch([judge(False, "Der Keller fehlt in der Rechnung.", max=1), judge(True),
                       {"stdin": "KRITIK DER PRÜFSCHICHT", "antwort": "Jetzt mit Keller: 4 Etagen plus Keller."},
                       {"stdin": "[SCHRITT 1 von 1", "antwort": "4 Etagen gerechnet."}])
        self.starten(auftrag_id)
        self.assertEqual(self.warte_auf(auftrag_id, ("fertig", "fehlgeschlagen"))["status"], "fertig")
        lehren = self.sp.erfahrungen(agent="kalk_treppenhaus")
        self.assertEqual(len(lehren), 1)
        self.assertIn("Der Keller fehlt in der Rechnung.", lehren[0]["text"])
        self.assertIn("künftig von Anfang an beachten", lehren[0]["text"])
        self.assertEqual(json.loads(self.sp.meta("einsatz:kalk_treppenhaus"))["auftrag"], 1)
        # Beim nächsten Einsatz steht die Lehre im Auftrag des Fachmanns
        self.assertIn("Der Keller fehlt", self.agent.denkrahmen("kalk_treppenhaus", "Neues Treppenhaus")[0])

    def test_auftrag_starten_erst_nach_ja(self):
        self.agent.laeufer = self.laeufer
        auftrag_id = self.auftrag_mit_plan(json.dumps({"titel": "Preis Müller", "schritte": [
            {"rolle": "kalk_treppenhaus", "titel": "Preis rechnen", "anweisung": "Rechne", "kriterium": "Preis steht"}]}))
        e = self.aktion("auftrag_starten", nummer=str(auftrag_id))
        self.assertEqual(e["status"], "freigabe_offen", e)
        vorschau = self.sp.freigabe(e["freigabe_id"])["vorschau"]
        self.assertIn("1. Kalkulator Treppenhaus: Preis rechnen", vorschau)
        self.assertIn("Abo-Limit", vorschau)
        self.assertEqual(self.sp.auftrag(auftrag_id)["status"], "entwurf")  # ohne Ja läuft nichts
        self.drehbuch([judge(True), {"stdin": "[SCHRITT 1 von 1", "antwort": "Preis: siehe Rechnung."}])
        code, antwort = self.agent.freigabe_beantworten(e["freigabe_id"], True)
        self.assertEqual(code, 200, antwort)
        self.assertEqual(self.warte_auf(auftrag_id, ("fertig", "fehlgeschlagen"))["status"], "fertig")
        # einen laufenden oder fertigen Auftrag startet man nicht noch einmal
        abgelehnt = ("fehler", "ungueltig")  # schon vor der Freigabe abgewiesen
        self.assertIn(self.aktion("auftrag_starten", nummer=str(auftrag_id))["status"], abgelehnt)
        self.assertIn(self.aktion("auftrag_starten", nummer="999")["status"], abgelehnt)
        privat = self.aktion("auftrag_starten", ctx=self.ctx("privat"), nummer=str(auftrag_id))
        self.assertIn(privat["status"], abgelehnt)  # fremder Bereich
        self.assertEqual(self.sp.freigaben("offen"), [])


class NeuerFachmannTest(AgentBasis):
    DATEN = {"name": "Fassaden-Scout", "abteilung": "vertrieb", "zweck": "Findet Fassadensanierungen in der Region.",
             "stichworte": "fassadensanierung, fassadenprojekt", "werkzeuge": "lesen, schreiben, netz",
             "pruefen": "Quelle je Treffer; Firma geprüft; Nichts gesendet"}
    AUFTRAG = "Du suchst über öffentliche Quellen Fassadensanierungen in der Region und schlägst passende Kontakte vor."

    def tearDown(self):
        rollen.eigene_setzen([])
        super().tearDown()

    def anlegen(self, **anders):
        daten = dict(self.DATEN, **anders)
        return self.agent.aktion_ausfuehren(self.ctx(), {"name": "agent_anlegen", "roh": daten, "koerper": self.AUFTRAG})

    def test_einstellen_nur_nach_ja_und_dauerhaft(self):
        vorher = len(agenten.alle())
        e = self.anlegen()
        self.assertEqual(e["status"], "freigabe_offen", e)
        vorschau = self.sp.freigabe(e["freigabe_id"])["vorschau"]
        self.assertIn("Neuer Fachmann für die Abteilung Vertrieb und Akquise: Fassaden-Scout (eigen_fassaden_scout)", vorschau)
        self.assertIn("keine neuen Rechte", vorschau)
        self.assertEqual(len(agenten.alle()), vorher)  # noch nicht eingestellt
        code, antwort = self.agent.freigabe_beantworten(e["freigabe_id"], True)
        self.assertEqual(code, 200, antwort)
        self.assertEqual(len(agenten.alle()), vorher + 1)
        self.assertEqual(rollen.ROLLEN["eigen_fassaden_scout"]["werkzeuge"],
                         ("dateien_auflisten", "datei_lesen", "datei_schreiben", "recherche"))
        self.assertEqual(agenten.waehlen("Gibt es eine Fassadensanierung in Köln?")[0], "eigen_fassaden_scout")
        # beim nächsten Start ist er wieder da
        rollen.eigene_setzen([])
        from jarvis_core.agent import Agent
        Agent(self.konfig, self.log, self.sp, self.pm)
        self.assertIn("eigen_fassaden_scout", rollen.ROLLEN)
        # und lässt sich wieder entfernen - auch das nur nach Ja
        weg = self.agent.aktion_ausfuehren(self.ctx(), {"name": "agent_entfernen", "roh": {"agent": "Fassaden-Scout"},
                                                        "koerper": None})
        self.assertEqual(weg["status"], "freigabe_offen", weg)
        self.agent.freigabe_beantworten(weg["freigabe_id"], True)
        self.assertNotIn("eigen_fassaden_scout", rollen.ROLLEN)
        with open(os.path.join(self.konfig.daten_ordner, agenten.EIGENE_DATEI), encoding="utf-8") as f:
            self.assertEqual(json.load(f), [])

    def test_keine_neuen_rechte_und_keine_dubletten(self):
        faelle = [({"werkzeuge": "lesen, loeschen"}, "nicht erlaubt"), ({"werkzeuge": "mail_senden"}, "nicht erlaubt"),
                  ({"name": "Stabschef"}, "gibt es schon"), ({"stichworte": "abc"}, "zu kurz"),
                  ({"abteilung": "gibtsnicht"}, "erlaubt sind"), ({"wissen": "gibtsnicht"}, "Wissenspaket")]
        for anders, grund in faelle:
            with self.subTest(anders=anders):
                e = self.anlegen(**anders)
                self.assertIn(e["status"], ("fehler", "ungueltig"), e)
                self.assertIn(grund, e["text"])
        self.assertEqual(self.sp.freigaben("offen"), [])
        katalogmann = self.agent.aktion_ausfuehren(self.ctx(), {"name": "agent_entfernen", "roh": {"agent": "Stabschef"},
                                                                "koerper": None})
        self.assertIn(katalogmann["status"], ("fehler", "ungueltig"))
        self.assertIn("nur eigene Agenten", katalogmann["text"])

    def test_kaputte_datei_bremst_den_start_nicht(self):
        with open(os.path.join(self.konfig.daten_ordner, agenten.EIGENE_DATEI), "w", encoding="utf-8") as f:
            json.dump([{"name": "x"}, dict(self.DATEN, auftrag=self.AUFTRAG)], f)
        from jarvis_core.agent import Agent
        Agent(self.konfig, self.log, self.sp, self.pm)
        self.assertIn("eigen_fassaden_scout", rollen.ROLLEN)
        self.assertEqual(len(agenten.eigene()), 1)


class TeamAnsichtTest(AgentBasis):
    def test_agenten_anzeigen(self):
        alle = self.aktion("agenten_anzeigen")
        self.assertEqual(alle["status"], "ausgefuehrt", alle)
        self.assertIn("%d Fachleute in 15 Abteilungen" % len(agenten.alle()), alle["text"])
        teil = self.aktion("agenten_anzeigen", abteilung="kalkulation")
        self.assertIn("Kalkulator Treppenhaus (kalk_treppenhaus)", teil["text"])
        self.assertIn("Kalkulationsleiter (kalkulationsleiter) – Leitung", teil["text"])
        einer = self.aktion("agenten_anzeigen", agent="Kalkulator Treppenhaus")
        self.assertIn("Prüft: Alle Teilflächen erfasst", einer["text"])
        self.assertIn("Erfahrungen: noch keine", einer["text"])
        self.assertEqual(self.aktion("agenten_anzeigen", agent="Gibtsnicht")["status"], "fehler")

    def test_planer_sieht_die_passenden_fachleute(self):
        text = Planer._rollen_text("Angebot für die Treppenhausreinigung bei einer Hausverwaltung mit 4 Etagen")
        self.assertIn("- kalk_treppenhaus (Kalkulator Treppenhaus, kalkulation):", text)
        for teil in agenten.abteilungen():
            self.assertIn("- %s (" % teil.leitung, text)
        self.assertLess(len(text.split("\n")), 30)  # nicht alle 100+, damit der Planer den richtigen findet
        plan = plan_pruefen({"titel": "Preis", "schritte": [{"rolle": "kalk_treppenhaus", "titel": "Rechnen",
                                                             "anweisung": "Rechne", "kriterium": "Preis steht"}]}, 6, self.konfig)
        self.assertEqual(plan["schritte"][0]["rolle"], "kalk_treppenhaus")


if __name__ == "__main__":
    unittest.main()
