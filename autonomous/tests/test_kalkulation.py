# -*- coding: utf-8 -*-
"""Tests Weg 1: Reinigungs-Kalkulation (Finance), Angebot für Daueraufträge und Anschreiben „reinigung“ (Sales).

Grundsätze, die hier geprüft werden: nachrechenbar, kein erfundener Stundensatz, Mindestlohn-Warnung mit Quelle,
Dauerauftrag getrennt von Einmalpreisen, nichts wird versendet."""

import datetime
import os
import re
import unittest

from autonomous import api
from autonomous.produkte import angebot, kalkulation
from autonomous.tests.hilfe import KernTest

BEISPIELE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "beispiele")
HEUTE = datetime.date(2026, 11, 21)
RECHENBEISPIEL = {
    "positionen": [{"bezeichnung": "Treppenhaus", "flaeche_m2": 400, "leistungswert_m2_h": 200,
                    "reinigungen_pro_monat": 4}],
    "stundensatz": "35,00", "material_prozent": "5", "zuschlag_prozent": 10,
    "anfahrten_pro_monat": 4, "anfahrt_minuten": 30,
}


class KalkTest(KernTest):
    def abarbeiten(self):
        return self.orch.alle_abarbeiten()

    def aufgabe(self, aid):
        return self.kern.aufgaben.hole(aid)

    def fehler_status(self, methode, pfad, body):
        with self.assertRaises(api.ApiFehler) as ctx:
            self.api(methode, pfad, body)
        return ctx.exception.status, ctx.exception.meldung

    def kalkulieren(self, body):
        aid = self.api("POST", "/api/kalkulation/reinigung", body)["aufgabe_id"]
        self.abarbeiten()
        a = self.aufgabe(aid)
        self.assertEqual(a["status"], "abgeschlossen", a["fehler"])
        self.assertEqual(a["verantwortlich"], "finance")
        return aid, a["ergebnis"]

    def kontakt(self, **felder):
        daten = {"firma": "Beispiel Hausverwaltung GmbH", "quelle": "persönliches Gespräch", "ort": "Köln",
                 "ansprechpartner": "Alex Beispiel"}
        daten.update(felder)
        return self.api("POST", "/api/kontakte", daten)["id"]

    def angebot_anlegen(self, body):
        aid = self.api("POST", "/api/angebote", body)["aufgabe_id"]
        self.abarbeiten()
        a = self.aufgabe(aid)
        self.assertEqual(a["status"], "abgeschlossen", a["fehler"])
        return a["ergebnis"]

    def datei(self, ergebnis):
        with open(ergebnis["dateien"][0], encoding="utf-8") as f:
            return f.read()

    def tearDown(self):
        # Nichts davon darf je eine Freigabe für Versand oder Kontakt auslösen
        self.assertEqual(self.kern.supervisor.liste(), [])
        super().tearDown()


class TestKalkulation(KalkTest):
    def test_rechenbeispiel_exakt_nachgerechnet(self):
        _, e = self.kalkulieren(RECHENBEISPIEL)
        # 400 m² ÷ 200 m²/h × 4 = 8 h; Anfahrt 4 × 30 min = 2 h
        self.assertEqual(e["positionen"][0]["stunden_monat"], 8.0)
        self.assertEqual(e["anfahrt"]["stunden_monat"], 2.0)
        self.assertEqual(e["stunden_gesamt_monat"], 10.0)
        # 8 h × 35 € = 280,00; Material 5 % = 14,00; Anfahrt 2 h × 35 € = 70,00; Zwischensumme 364,00;
        # Zuschlag 10 % = 36,40; Monat 400,40; Jahr 4.804,80
        self.assertEqual(e["reinigungskosten_cent"], 28000)
        self.assertEqual(e["material_cent"], 1400)
        self.assertEqual(e["anfahrtskosten_cent"], 7000)
        self.assertEqual(e["zwischensumme_cent"], 36400)
        self.assertEqual(e["zuschlag_cent"], 3640)
        self.assertEqual(e["preis_monat_cent"], 40040)
        self.assertEqual(e["preis_jahr_cent"], 480480)
        self.assertEqual(e["preis_monat"], "400,40 €")
        self.assertEqual(e["preis_jahr"], "4.804,80 €")
        self.assertEqual(e["stundensatz_quelle"], "Eingabe")
        self.assertIn("Treppenhaus: 400 m² ÷ 200 m²/h × 4 = 8,00 h/Monat", e["rechenweg"])
        self.assertIn("Preis pro Monat (netto): 364,00 € + 36,40 € = 400,40 €", e["rechenweg"])
        self.assertTrue(e["netto"])
        self.assertTrue(any("§ 13b" in h for h in e["hinweise"]))

    def test_woche_wird_nachvollziehbar_in_monat_umgerechnet(self):
        d = kalkulation.eingabe_pruefen({"positionen": [{"bezeichnung": "Büro", "flaeche_m2": "150",
                                                         "leistungswert_m2_h": "150", "reinigungen_pro_woche": "1"}],
                                         "stundensatz": "30"})
        e = kalkulation.berechnen(d, 0, HEUTE)
        # 150 ÷ 150 × (1 × 52 ÷ 12) = 4,333… h → 130,00 € (4,333… × 30 € = 130,00 €)
        self.assertEqual(e["positionen"][0]["stunden_monat"], 4.33)
        self.assertEqual(e["positionen"][0]["turnus"], "1× pro Woche")
        self.assertEqual(e["preis_monat_cent"], 13000)
        self.assertIn("(= 1 × 52 ÷ 12)", e["rechenweg"][0])

    def test_ohne_stundensatz_bleibt_preis_offen_stunden_stimmen(self):
        self.assertEqual(self.kern.einstellungen.hole("stundensatz_cent"), 0)
        body = dict(RECHENBEISPIEL)
        body.pop("stundensatz")
        _, e = self.kalkulieren(body)
        self.assertEqual(e["stunden_gesamt_monat"], 10.0)
        self.assertIsNone(e["preis_monat_cent"])
        self.assertIsNone(e["preis_jahr_cent"])
        self.assertEqual(e["preis_monat"], "OFFEN – Stundensatz festlegen")
        self.assertEqual(e["stundensatz"], "OFFEN – Stundensatz festlegen")
        self.assertEqual(e["stundensatz_quelle"], "offen")
        self.assertTrue(any("Kein Stundensatz festgelegt" in w for w in e["warnungen"]))
        # „0“ als Eingabe heißt ebenfalls: nicht festgelegt – nie wird ein Satz angenommen
        body["stundensatz"] = "0"
        _, e = self.kalkulieren(body)
        self.assertIsNone(e["preis_monat_cent"])

    def test_stundensatz_aus_den_einstellungen(self):
        self.kern.einstellungen.setze("stundensatz_cent", 4000, "eigentuemer")
        body = dict(RECHENBEISPIEL, material_prozent=0, zuschlag_prozent=0, anfahrten_pro_monat=0)
        body.pop("stundensatz")
        _, e = self.kalkulieren(body)
        self.assertEqual(e["stundensatz_quelle"], "Einstellungen")
        self.assertEqual(e["preis_monat_cent"], 8 * 4000)

    def test_warnung_unter_branchen_mindestlohn_mit_quelle(self):
        d = kalkulation.eingabe_pruefen(dict(RECHENBEISPIEL, stundensatz="14,50"))
        e = kalkulation.berechnen(d, 0, HEUTE)
        warnung = [w for w in e["warnungen"] if "Mindestlohn" in w]
        self.assertEqual(len(warnung), 1)
        self.assertIn("15,00 €/h", warnung[0])
        self.assertIn("gesetze-im-internet.de/tvmindestlohngeb_ude_2024", warnung[0])
        self.assertIn("Stand 09.11.2026", warnung[0])
        self.assertTrue(any("nur die Untergrenze für den LOHN" in h for h in e["hinweise"]))
        self.assertTrue(any("läuft am 01.01.2027 aus" in h for h in e["hinweise"]))
        # Glas-/Fensterreinigung: Lohngruppe 6 (18,40 €/h)
        glas = {"positionen": [{"bezeichnung": "Fensterreinigung", "flaeche_m2": 50, "leistungswert_m2_h": 25,
                                "reinigungen_pro_monat": 1}], "stundensatz": "16"}
        e = kalkulation.berechnen(kalkulation.eingabe_pruefen(glas), 0, HEUTE)
        self.assertTrue(any("18,40 €/h" in w for w in e["warnungen"]))
        # ausreichender Satz: keine Lohnwarnung
        e = kalkulation.berechnen(kalkulation.eingabe_pruefen(dict(glas, stundensatz="40")), 0, HEUTE)
        self.assertFalse([w for w in e["warnungen"] if "Mindestlohn" in w])

    def test_nach_ablauf_der_verordnung_deutlicher_hinweis(self):
        d = kalkulation.eingabe_pruefen(dict(RECHENBEISPIEL, stundensatz="14,50"))
        e = kalkulation.berechnen(d, 0, datetime.date(2027, 1, 2))
        self.assertTrue(any("ausgelaufen" in w for w in e["warnungen"]))
        self.assertFalse([w for w in e["warnungen"] if "liegt unter dem Branchen-Mindestlohn" in w])

    def test_unrealistischer_leistungswert_nur_warnung(self):
        d = kalkulation.eingabe_pruefen({"positionen": [{"bezeichnung": "Halle", "flaeche_m2": 5000,
                                                         "leistungswert_m2_h": 2500, "reinigungen_pro_monat": 1}],
                                         "stundensatz": "40"})
        e = kalkulation.berechnen(d, 0, HEUTE)
        self.assertTrue(any("ungewöhnlich hoch" in w for w in e["warnungen"]))
        self.assertEqual(e["stunden_gesamt_monat"], 2.0)

    def test_ungueltige_eingaben_sofort_400(self):
        gut = {"bezeichnung": "Treppenhaus", "flaeche_m2": 100, "leistungswert_m2_h": 100,
               "reinigungen_pro_monat": 4}
        falsch = [
            {},
            {"positionen": []},
            {"positionen": "Treppenhaus"},
            {"positionen": [dict(gut, leistungswert_m2_h=0)]},
            {"positionen": [dict(gut, leistungswert_m2_h="abc")]},
            {"positionen": [dict(gut, leistungswert_m2_h=None)]},
            {"positionen": [dict(gut, flaeche_m2=-5)]},
            {"positionen": [dict(gut, reinigungen_pro_woche=2)]},           # Monat UND Woche
            {"positionen": [{k: v for k, v in gut.items() if k != "reinigungen_pro_monat"}]},
            {"positionen": [dict(gut, bezeichnung="")]},
            {"positionen": [dict(gut, bezeichnung="x" * 81)]},
            {"positionen": [gut] * 31},
            {"positionen": [gut], "material_prozent": 150},
            {"positionen": [gut], "zuschlag_prozent": -1},
            {"positionen": [gut], "stundensatz": "abc"},
            {"positionen": [gut], "stundensatz": True},
            {"positionen": [gut], "anfahrt_minuten": 301},
        ]
        for body in falsch:
            status, _ = self.fehler_status("POST", "/api/kalkulation/reinigung", body)
            self.assertEqual(status, 400, body)
        self.assertEqual(self.kern.aufgaben.liste(), [])  # keine halbe Aufgabe angelegt

    def test_escaping_in_positionsbezeichnung(self):
        body = dict(RECHENBEISPIEL, positionen=[dict(RECHENBEISPIEL["positionen"][0],
                                                     bezeichnung="<script>alert(1)</script>")])
        kid, _ = self.kalkulieren(body)
        e = self.angebot_anlegen({"kalkulation_aufgabe_id": kid})
        html = self.datei(e)
        self.assertIn("&lt;script&gt;alert(1)&lt;/script&gt;", html)
        self.assertNotRegex(html, r"(?i)<script|\son\w+=")


class TestAngebotDauerauftrag(KalkTest):
    def test_angebot_uebernimmt_positionen_und_preis_aus_kalkulation(self):
        kid, kalk = self.kalkulieren(RECHENBEISPIEL)
        kontakt = self.kontakt()
        e = self.angebot_anlegen({"kalkulation_aufgabe_id": kid, "kontakt_id": kontakt,
                                  "objekt": "Musterweg 5, Köln"})
        self.assertEqual(e["art"], "reinigung_dauerauftrag")
        self.assertEqual(e["betrag"], "400,40 € pro Monat (netto)")
        self.assertIn(kid, e["preis_quelle"])
        zeile = self.kern.db.eins("SELECT * FROM angebote WHERE id=?", (e["angebot_id"],))
        self.assertEqual(zeile["betrag_cent"], kalk["preis_monat_cent"])
        self.assertEqual(zeile["status"], "entwurf")
        html = self.datei(e)
        for erwartet in ("ENTWURF – vor Versand prüfen", "Leistungsverzeichnis", "Treppenhaus", "400&nbsp;m²",
                         "4× pro Monat", "Monatliche Pauschale (netto)", "400,40 €", "4.804,80 €",
                         "Musterweg 5, Köln", "[Kündigungsfrist – vom Inhaber festzulegen]",
                         "[Laufzeit – vom Inhaber festzulegen]", "Preisanpassung bei Änderung von Tarif- oder Mindestlohn",
                         "Ein Angebot ist keine Einnahme", "Guten Tag Alex Beispiel,"):
            self.assertIn(erwartet, html)
        # Interna (Stundensatz, Herkunft des Preises) stehen nur im Bildschirmhinweis, nie im Ausdruck für den Kunden
        ohne_hinweis = re.sub(r'<p class="nur-bildschirm">.*?</p>', "", html.split("</style>")[1], flags=re.S)
        self.assertNotIn("Stundensatz", ohne_hinweis)
        self.assertNotIn("Kalkulation", ohne_hinweis)
        liste = self.api("GET", "/api/angebote")["angebote"]
        self.assertEqual(liste[0]["art"], "reinigung_dauerauftrag")
        self.assertEqual(liste[0]["abrechnung"], "monatlich")
        self.assertEqual(liste[0]["betrag"], "400,40 € pro Monat (netto)")

    def test_offener_preis_wird_verweigert_ausser_inhaber_gibt_betrag(self):
        body = dict(RECHENBEISPIEL)
        body.pop("stundensatz")
        kid, _ = self.kalkulieren(body)
        status, meldung = self.fehler_status("POST", "/api/angebote", {"kalkulation_aufgabe_id": kid})
        self.assertEqual(status, 400)
        self.assertIn("erst den Stundensatz festlegen", meldung)
        # auch direkt als Aufgabe: fachlicher Fehler, kein Angebot, keine Wiederholungen
        aid = self.kern.aufgaben.anlegen("A", "angebot_entwurf", "sales", "eigentuemer",
                                         {"kalkulation_aufgabe_id": kid})
        self.abarbeiten()
        a = self.aufgabe(aid)
        self.assertEqual(a["status"], "fehlgeschlagen")
        self.assertIn("OFFEN", a["fehler"])
        self.assertEqual(a["versuche"], 1)
        self.assertEqual(self.kern.db.wert("SELECT COUNT(*) FROM angebote"), 0)
        # Inhaber legt den Monatspreis selbst fest → Angebot möglich, Herkunft dokumentiert
        e = self.angebot_anlegen({"kalkulation_aufgabe_id": kid, "betrag": "420"})
        self.assertEqual(e["betrag"], "420,00 € pro Monat (netto)")
        self.assertIn("Kalkulation hatte keinen Preis", e["preis_quelle"])

    def test_kalkulation_muss_passen(self):
        status, _ = self.fehler_status("POST", "/api/angebote", {"kalkulation_aufgabe_id": "a_gibtsnicht"})
        self.assertEqual(status, 404)
        andere = self.kern.aufgaben.anlegen("KZ", "kennzahlen", "ceo", "eigentuemer")
        self.abarbeiten()
        status, meldung = self.fehler_status("POST", "/api/angebote", {"kalkulation_aufgabe_id": andere})
        self.assertEqual(status, 400)
        self.assertIn("keine Reinigungs-Kalkulation", meldung)
        wartend = self.kern.aufgaben.anlegen("K", "kalkulation_reinigung", "finance", "eigentuemer", RECHENBEISPIEL,
                                             sofort_bereit=False)
        status, meldung = self.fehler_status("POST", "/api/angebote", {"kalkulation_aufgabe_id": wartend})
        self.assertEqual(status, 400)
        self.assertIn("noch nicht abgeschlossen", meldung)
        kid, _ = self.kalkulieren(RECHENBEISPIEL)
        status, _ = self.fehler_status("POST", "/api/angebote", {"kalkulation_aufgabe_id": kid, "art": "einmalig",
                                                                 "betrag": "100"})
        self.assertEqual(status, 400)

    def test_dauerauftrag_von_hand(self):
        e = self.angebot_anlegen({"art": "reinigung_dauerauftrag", "betrag": "450",
                                  "positionen": ["Treppenhaus", {"bezeichnung": "Büro", "flaeche_m2": "120,5",
                                                                 "turnus": "2× pro Woche"}],
                                  "laufzeit": "12 Monate"})
        html = self.datei(e)
        for erwartet in ("120,5&nbsp;m²", "2× pro Woche", "[Turnus festlegen]", "450,00 €", "5.400,00 €",
                         "12 Monate", "vom Inhaber angegeben"):
            self.assertIn(erwartet, html)
        status, meldung = self.fehler_status("POST", "/api/angebote", {"art": "reinigung_dauerauftrag",
                                                                       "positionen": ["Treppenhaus"]})
        self.assertEqual(status, 400)
        self.assertIn("betrag", meldung)
        status, _ = self.fehler_status("POST", "/api/angebote", {"art": "reinigung_dauerauftrag", "betrag": "450"})
        self.assertEqual(status, 400)  # ohne Leistungsverzeichnis kein Dauerauftrag
        status, _ = self.fehler_status("POST", "/api/angebote", {"art": "abo", "betrag": "450"})
        self.assertEqual(status, 400)

    def test_einmaliges_angebot_unveraendert(self):
        e = self.angebot_anlegen({"betrag": "890"})
        self.assertEqual(e["art"], "einmalig")
        self.assertEqual(e["betrag"], "890,00 €")
        html = self.datei(e)
        self.assertIn("Gesamtpreis", html)
        self.assertIn("890,00 €", html)
        self.assertNotIn("Leistungsverzeichnis", html)
        self.assertNotIn("pro Monat", html)
        self.assertEqual(self.api("GET", "/api/angebote")["angebote"][0]["abrechnung"], "einmalig")

    def test_gepruefte_fassung_ohne_entwurf(self):
        kid, _ = self.kalkulieren(RECHENBEISPIEL)
        e = self.angebot_anlegen({"kalkulation_aufgabe_id": kid})
        antwort = self.api("POST", "/api/angebote/%s/status" % e["angebot_id"], {"status": "geprueft"})
        pfad = os.path.join(os.environ["AUTONOMOUS_DATEN"], "produkte", antwort["ansehen_url"][len("/produkte/"):])
        with open(pfad, encoding="utf-8") as f:
            html = f.read()
        self.assertNotIn("ENTWURF – vor Versand prüfen", html)
        self.assertIn("Leistungsverzeichnis", html)
        self.assertIn("400,40 €", html)

    def test_pipeline_trennt_monatlich_und_einmalig(self):
        kid, _ = self.kalkulieren(RECHENBEISPIEL)
        self.angebot_anlegen({"kalkulation_aufgabe_id": kid})
        self.angebot_anlegen({"betrag": "500"})
        aid = self.api("POST", "/api/vertrieb/auswertung")["aufgabe_id"]
        self.abarbeiten()
        e = self.aufgabe(aid)["ergebnis"]
        self.assertEqual(e["angebote_nach_status"]["entwurf"]["anzahl"], 2)
        self.assertTrue(e["angebote_offen_summe"].startswith("500,00 €"))
        self.assertTrue(e["angebote_offen_monatlich"].startswith("400,40 € pro Monat"))
        self.assertIn("keine Einnahme", e["angebote_offen_monatlich"])


class TestAnschreibenReinigung(KalkTest):
    def test_ohne_einwilligung_brief_und_uwg_hinweis(self):
        kid = self.kontakt()
        aid = self.api("POST", "/api/vertrieb/nachricht", {"kontakt_id": kid, "angebot": "reinigung"})["aufgabe_id"]
        self.abarbeiten()
        e = self.aufgabe(aid)["ergebnis"]
        self.assertEqual(e["angebot"], "reinigung")
        self.assertEqual(e["kanal_empfehlung"], "brief")
        self.assertIs(e["sendefertig"], False)
        self.assertEqual(e["status"], "ENTWURF – nicht versendet")
        self.assertIn("§ 7 UWG", e["hinweis_recht"])
        self.assertIn("in Köln und Umgebung", e["text"])
        self.assertIn("Leistungsverzeichnis", e["text"])
        self.assertIn("[Kurz vorstellen, wer wir sind – vom Inhaber ergänzen]", e["text"])
        self.assertIn("[Straße, Hausnummer]", e["text"])
        # nichts erfunden: keine Referenzen, keine Zahlen über den Betrieb, keine Eigenlob-Behauptungen
        for verboten in ("Referenz", "zuverlässig", "erfahren", "seit ", "Kunden vertrauen", "zufriedene"):
            self.assertNotIn(verboten, e["text"])
        kern_text = e["text"].split("Betreff:")[1]
        self.assertIsNone(re.search(r"\d", kern_text.replace("§ 7", "")), "keine Zahlen im Anschreiben")

    def test_ort_nur_aus_kontakt_sonst_platzhalter(self):
        kid = self.kontakt(firma="Ohne Ort GmbH", ort="")
        aid = self.api("POST", "/api/vertrieb/nachricht", {"kontakt_id": kid, "angebot": "reinigung"})["aufgabe_id"]
        self.abarbeiten()
        self.assertIn("[Einsatzgebiet – vom Inhaber ergänzen]", self.aufgabe(aid)["ergebnis"]["text"])

    def test_mit_einwilligung_email_entwurf_aber_nicht_gesendet(self):
        kid = self.kontakt(einwilligung="ja", einwilligung_nachweis="Anfrage per Telefon am 18.11., Rückruf erbeten")
        aid = self.api("POST", "/api/vertrieb/nachricht", {"kontakt_id": kid, "angebot": "reinigung"})["aufgabe_id"]
        self.abarbeiten()
        e = self.aufgabe(aid)["ergebnis"]
        self.assertEqual(e["kanal_empfehlung"], "email")
        self.assertIs(e["sendefertig"], False)

    def test_unbekanntes_angebot_400_und_standard_bleibt_google_profil(self):
        kid = self.kontakt()
        status, _ = self.fehler_status("POST", "/api/vertrieb/nachricht", {"kontakt_id": kid, "angebot": "abo"})
        self.assertEqual(status, 400)
        aid = self.api("POST", "/api/vertrieb/nachricht", {"kontakt_id": kid})["aufgabe_id"]
        self.abarbeiten()
        self.assertEqual(self.aufgabe(aid)["ergebnis"]["angebot"], "google_profil")


class TestBeispiel(unittest.TestCase):
    def test_committetes_beispiel_ist_aktuell(self):
        erwartet = angebot.beispiel_dauerauftrag()
        with open(os.path.join(BEISPIELE, angebot.BEISPIEL_DATEI), encoding="utf-8") as f:
            self.assertEqual(f.read(), erwartet, "Beispiel veraltet – neu erzeugen mit: python3 -c \"from "
                             "autonomous.produkte.angebot import beispiel_schreiben; "
                             "beispiel_schreiben('autonomous/beispiele')\"")
        self.assertIn("Beispielwert, kein Vorschlag", erwartet)
        self.assertIn("fiktive Musterfirma", erwartet)
        self.assertIn("318,14 €", erwartet)       # 6,6 h × 35 € + Material + Anfahrt + Zuschlag (nachgerechnet)
        self.assertNotRegex(erwartet, r"(?i)<script|\son\w+=|(src|href)=\"https?:")


if __name__ == "__main__":
    unittest.main()
