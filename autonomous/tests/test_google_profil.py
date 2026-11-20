# -*- coding: utf-8 -*-
"""Tests Google-Profil-Paket: Unterlagen (Entwurf, Prüfliste, Übergabe), Qualitätsprüfung, Verkaufsseite
mit Standard-Angebot „google_profil“ und API. Jeder Test hat einen eigenen, leeren Datenordner."""

import json
import os
import re
import tempfile
import unittest
from unittest import mock

os.environ["AUTONOMOUS_DATEN"] = tempfile.mkdtemp(prefix="autonomous-gp-")  # vor dem Import; je Test eigener Ordner

from autonomous import api  # noqa: E402
from autonomous import api_vertrieb  # noqa: E402,F401  (registriert die Routen)
from autonomous.produkte import google_profil, qualitaet, verkaufsseite  # noqa: E402
from autonomous.tests.hilfe import KernTest  # noqa: E402

BEISPIELE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "beispiele")
BETRIEB = {"firma": "Muster Gebäudeservice & Söhne", "branche": "Gebäudereinigung", "ort": "Leverkusen",
           "leistungen": "Büroreinigung, Treppenhausreinigung, Glasreinigung", "telefon": "0214 123456",
           "email": "info@muster.example", "webseite": "https://www.muster.example/kontakt",
           "einzugsgebiet": "Leverkusen und Köln", "oeffnungszeiten": "Mo–Fr 7–17 Uhr; Sa nach Vereinbarung"}
KEIN_BETRAG = re.compile(r"\d\s*(€|EUR|Euro)")


class GoogleProfilTest(KernTest):
    def paket(self, **aenderung):
        eingabe = dict(BETRIEB, **aenderung)
        eingabe = {k: v for k, v in eingabe.items() if v is not None}
        aid = self.api("POST", "/api/produkte/google_profil", eingabe)["aufgabe_id"]
        self.orch.alle_abarbeiten()
        a = self.kern.aufgaben.hole(aid)
        self.assertEqual(a["status"], "abgeschlossen", a["fehler"])
        return a["ergebnis"]

    @staticmethod
    def lesen(pfad):
        with open(pfad, encoding="utf-8") as f:
            return f.read()

    def dateien(self, ergebnis):
        return {os.path.basename(p): self.lesen(p) for p in ergebnis["dateien"]}

    @staticmethod
    def beschreibung(html):
        treffer = re.search(r'<div id="beschreibung-text" class="beschreibung">(.*?)</div>', html, re.S)
        return treffer.group(1) if treffer else None


class TestPaket(GoogleProfilTest):
    def test_drei_unterlagen_ueber_orchestrator_mit_qualitaetspruefung(self):
        e = self.paket()
        d = self.dateien(e)
        self.assertEqual(sorted(d), ["profil-entwurf.html", "pruefliste.html", "uebergabe-anleitung.html"])
        self.assertEqual(e["status"], "qualitaet_ok", e["qualitaet"])
        offen = " ".join(e["qualitaet"]["offene_punkte"])
        self.assertIn("Hauptkategorie in der Google-Auswahlliste auswählen (vor Ort)", offen)
        self.assertIn("Übergabe-Anleitung vor der Übergabe prüfen (Inhaber)", offen)
        self.assertIn("Ansprechpartner und Telefonnummer des Anbieters eintragen", offen)
        produkt = self.api("GET", "/api/produkte")["produkte"][0]
        self.assertEqual(produkt["typ"], "google_profil_paket")
        self.assertEqual(produkt["ansehen_url"], "/produkte/%s/profil-entwurf.html" % e["produkt_id"])
        self.assertEqual(produkt["dateien"], ["profil-entwurf.html", "pruefliste.html", "uebergabe-anleitung.html"])
        for name, html in d.items():
            self.assertNotIn("<script", html.lower(), name)
            self.assertIsNone(re.search(r'(src|href)="(https?:)?//', html), name)
            self.assertIn('lang="de"', html)
        # Ehrlich: nichts ist bei Google eingetragen
        self.assertIn("Nichts davon ist bei Google eingetragen", d["profil-entwurf.html"])
        self.assertTrue(any("trägt nichts bei Google ein" in g for g in e["einschraenkungen"]))

    def test_inhalte_des_entwurfs(self):
        html = self.dateien(self.paket())["profil-entwurf.html"]
        self.assertIn("VORSCHLAG – bitte in der Google-Auswahlliste prüfen.", html)
        self.assertIn("Muster Gebäudeservice &amp; Söhne", html)
        self.assertIn("von höchstens 750 Zeichen", html)
        for leistung in ("Büroreinigung", "Treppenhausreinigung", "Glasreinigung"):
            self.assertIn(leistung, html)
        self.assertIn("nur mit Einwilligung jeder abgebildeten Person", html)
        self.assertIn("Kfz-Kennzeichen", html)
        pruefliste = self.dateien(self.paket(firma="Zweite Firma"))["pruefliste.html"]
        self.assertIn("Wir nehmen keine Passwörter an", pruefliste)
        self.assertIn("nicht gezielt nur zufriedene Kunden", pruefliste)
        self.assertIn("keine Dauer zusagen", pruefliste)

    def test_uebergabe_anleitung(self):
        d = self.dateien(self.paket(anbieter="Familienbetrieb Beispiel", anbieter_kontakt="0214 999999"))
        html = d["uebergabe-anleitung.html"]
        self.assertIn("gehört Ihnen", html)
        self.assertIn("jederzeit entfernen", html)
        self.assertIn("Google ändert seine Oberfläche gelegentlich", html)
        self.assertIn("allen, nicht nur den zufriedenen", html)
        self.assertIn("Familienbetrieb Beispiel", html)
        self.assertNotIn("Ansprechpartner und Telefonnummer des Anbieters eintragen", html)
        self.assertIn("nur-bildschirm", html)  # Prüfhinweis erscheint nicht im Ausdruck

    def test_nichts_erfunden_bei_minimaler_eingabe(self):
        e = self.paket(telefon=None, email=None, webseite=None, einzugsgebiet=None, oeffnungszeiten=None)
        html = self.dateien(e)["profil-entwurf.html"]
        text = self.beschreibung(html)
        self.assertEqual(text, "Muster Gebäudeservice &amp; Söhne – Gebäudereinigung aus Leverkusen. "
                               "Leistungen: Büroreinigung, Treppenhausreinigung, Glasreinigung.")
        self.assertIsNone(re.search(r"\d", text), "keine erfundenen Zahlen")
        self.assertIn("nicht angegeben – nur eintragen, wenn sicher bekannt", html)
        self.assertIn("Öffnungszeiten: offen – vom Inhaber festzulegen.", html)
        offen = " ".join(e["qualitaet"]["offene_punkte"])
        for punkt in ("Öffnungszeiten festlegen (Inhaber)", "Kontaktweg klären (Telefon oder E-Mail)",
                      "Adresse oder Servicegebiet klären (vor Ort)"):
            self.assertIn(punkt, offen)
        for wort in ("Sterne", "Bewertungen von", "zertifiziert", "Jahre Erfahrung", "Kunden vertrauen"):
            self.assertNotIn(wort, html)

    def test_eingaben_werden_escaped(self):
        e = self.paket(firma='<script>alert(1)</script> "Bau"', leistungen=['<img src=x onerror=alert(1)>'],
                       besonderheiten="<b>fett</b>")
        for name, html in self.dateien(e).items():
            self.assertNotIn("<script>alert", html, name)
            self.assertNotIn("<img", html, name)
            self.assertNotIn("<b>fett", html, name)
        self.assertIn("&lt;script&gt;alert(1)&lt;/script&gt;", self.dateien(e)["profil-entwurf.html"])
        maengel = e["qualitaet"]["maengel"]
        self.assertFalse([m for m in maengel if "JavaScript" in m or "escaped" in m], maengel)

    def test_beschreibung_hoechstens_750_auch_bei_sehr_vielen_leistungen(self):
        leistungen = ["Leistung Nummer %02d mit einer recht ausführlichen Beschreibung des Angebots" % i
                      for i in range(20)]
        e = self.paket(leistungen=leistungen)
        html = self.dateien(e)["profil-entwurf.html"]
        text = self.beschreibung(html)
        self.assertLessEqual(len(text), 750)
        self.assertTrue(e["beschreibung_gekuerzt"])
        self.assertIn("und weitere.", text)
        self.assertIn("Gekürzt: Nicht alle Leistungen passen in 750 Zeichen.", html)
        self.assertIn("Beschreibung wurde gekürzt", " ".join(e["qualitaet"]["offene_punkte"]))
        self.assertNotIn("Beschreibung höchstens 750 Zeichen", " ".join(e["qualitaet"]["maengel"]))
        for leistung in leistungen:  # die vollständige Liste steht trotzdem im Entwurf
            self.assertIn(leistung, html)
        # Auch sehr lange Zusatzangaben werden am Wortende gekürzt statt abgelehnt
        d = google_profil.eingabe_pruefen(dict(BETRIEB, leistungen=leistungen, besonderheiten="Sehr " * 79 + "lang",
                                               einzugsgebiet="Gebiet " * 28))
        text, gekuerzt = google_profil.beschreibung_bauen(d)
        self.assertLessEqual(len(text), 750)
        self.assertTrue(gekuerzt)
        self.assertTrue(text.endswith("…"))

    def test_keine_url_und_keine_telefonnummer_in_der_beschreibung(self):
        e = self.paket()
        html = self.dateien(e)["profil-entwurf.html"]
        text = self.beschreibung(html)
        self.assertNotIn("muster.example", text)
        self.assertNotIn("http", text)
        self.assertNotIn("0214", text)
        self.assertIn("Anfragen gern telefonisch oder per E-Mail.", text)
        self.assertIn("https://www.muster.example/kontakt", html)  # steht im Feld „Webseite“ …
        self.assertNotIn('href="https://www.muster.example', html)  # … aber nur als Text, nicht als Link
        # Links oder Telefonnummern in Feldern, die in die Beschreibung fließen, werden abgelehnt
        for feld, wert in (("besonderheiten", "Mehr unter www.muster.de"), ("leistungen", "Notdienst 0214 123456"),
                           ("einzugsgebiet", "siehe https://muster.example/gebiet")):
            with self.assertRaises(ValueError, msg=feld):
                self.api("POST", "/api/produkte/google_profil", dict(BETRIEB, **{feld: wert}))
        # Jahreszahlen, Normen und Postleitzahlen sind keine Telefonnummern
        google_profil.eingabe_pruefen(dict(BETRIEB, leistungen="Abdichtung nach DIN 18533-1",
                                           einzugsgebiet="51373 Leverkusen und Umgebung", gruendungsjahr=1998))

    def test_gruendungsjahr_nur_wenn_angegeben(self):
        text = self.beschreibung(self.dateien(self.paket(gruendungsjahr="1998"))["profil-entwurf.html"])
        self.assertIn("Gegründet 1998.", text)
        text = self.beschreibung(self.dateien(self.paket(firma="Andere Firma"))["profil-entwurf.html"])
        self.assertNotIn("Gegründet", text)
        for falsch in ("abc", "98", 3000, True):
            with self.assertRaises(ValueError, msg=str(falsch)):
                google_profil.eingabe_pruefen(dict(BETRIEB, gruendungsjahr=falsch))

    def test_pflichtfelder_und_ungueltige_eingaben(self):
        for feld in ("firma", "branche", "ort", "leistungen"):
            with self.assertRaises(ValueError, msg=feld):
                self.api("POST", "/api/produkte/google_profil", dict(BETRIEB, **{feld: ""}))
        for feld, wert in (("telefon", "abc"), ("email", "keine-mail"), ("webseite", "javascript:alert(1)"),
                           ("firma", "x" * 81)):
            with self.assertRaises(ValueError, msg=feld):
                google_profil.eingabe_pruefen(dict(BETRIEB, **{feld: wert}))
        self.assertEqual(self.kern.aufgaben.zaehlen()["bereit"], 0)  # ungültig → keine Aufgabe angelegt


class TestQualitaet(GoogleProfilTest):
    def test_ortszusatz_im_namen_ist_eine_warnung(self):
        e = self.paket(firma="Muster Reinigung – Leverkusen")
        self.assertEqual(e["status"], "qualitaet_mangel")
        produkt = self.api("GET", "/api/produkte/%s" % e["produkt_id"])
        name = "Firmenname ohne angehängte Orte oder Suchbegriffe"
        pruefung = [p for p in produkt["qualitaet"]["pruefungen"] if p["name"] == name][0]
        self.assertFalse(pruefung["ok"])
        self.assertTrue(pruefung["hinweis"].startswith("Warnung"))
        self.assertIn("leverkusen", pruefung["hinweis"])
        # Echte Namen ohne Zusatz bleiben unbeanstandet
        eingaben = google_profil.eingabe_pruefen(BETRIEB)
        for gut in ("Schmidt Gebäudereinigung GmbH", "Müller-Lüdenscheidt Bau", "Muster GmbH & Co. KG"):
            self.assertEqual(qualitaet.name_zusaetze(gut, eingaben), [], gut)
        for schlecht in ("Muster | Treppenhausreinigung", "Muster GmbH in Leverkusen", "Muster GmbH - Glasreinigung"):
            self.assertTrue(qualitaet.name_zusaetze(schlecht, eingaben), schlecht)

    def test_nachpruefung_erkennt_eingeschleustes_script_und_fehlende_datei(self):
        e = self.paket()
        ordner = os.path.dirname(e["dateien"][0])
        with open(os.path.join(ordner, "pruefliste.html"), "a", encoding="utf-8") as f:
            f.write('<script>alert(1)</script><img src="https://tracker.example/x.gif">')
        os.remove(os.path.join(ordner, "uebergabe-anleitung.html"))
        aid = self.api("POST", "/api/produkte/%s/pruefen" % e["produkt_id"])["aufgabe_id"]
        self.orch.alle_abarbeiten()
        r = self.kern.aufgaben.hole(aid)["ergebnis"]
        self.assertEqual(r["status"], "qualitaet_mangel")
        fehler = {(p["datei"], p["name"]) for p in r["pruefungen"] if not p["ok"]}
        self.assertIn(("pruefliste.html", "Kein JavaScript"), fehler)
        self.assertIn(("pruefliste.html", "Keine externen Ressourcen"), fehler)
        self.assertIn(("uebergabe-anleitung.html", "Datei vorhanden"), fehler)
        self.assertIn(("profil-entwurf.html", "Paket vollständig (3 Unterlagen)"), fehler)
        self.assertEqual(self.api("GET", "/api/produkte/%s" % e["produkt_id"])["status"], "qualitaet_mangel")

    def test_zu_lange_beschreibung_link_und_telefon_werden_erkannt(self):
        html = ('<div id="beschreibung-text" class="beschreibung">%s</div><p id="firmenname">Muster GmbH</p>'
                % ("Wort " * 160 + "Mehr unter www.muster.de oder 0214 123456"))
        pruefungen = {p["name"]: p for p in qualitaet.profil_entwurf_pruefen(html)}
        self.assertFalse(pruefungen["Beschreibung höchstens 750 Zeichen"]["ok"])
        self.assertFalse(pruefungen["Beschreibung ohne Links"]["ok"])
        self.assertFalse(pruefungen["Beschreibung ohne Telefonnummern"]["ok"])
        self.assertTrue(pruefungen["Firmenname ohne angehängte Orte oder Suchbegriffe"]["ok"])


class TestVerkaufsseite(GoogleProfilTest):
    def verkaufsseite(self, body):
        aid = self.api("POST", "/api/produkte/verkaufsseite", body)["aufgabe_id"]
        self.orch.alle_abarbeiten()
        a = self.kern.aufgaben.hole(aid)
        self.assertEqual(a["status"], "abgeschlossen", a["fehler"])
        return a["ergebnis"]

    def test_standard_ist_google_profil_ohne_preis_mit_platzhalter(self):
        vorlagen = os.path.join(os.environ["AUTONOMOUS_DATEN"], "vorlagen")
        os.makedirs(vorlagen)
        with open(os.path.join(vorlagen, "marktbewertung.json"), "w", encoding="utf-8") as f:
            json.dump({"empfehlung": {"feld_id": "digitale_dienstleistungen", "angebot": "Google-Profil-Paket",
                                      "preis_vorschlag_eur": {"min": 199, "max": 349, "einheit": "netto",
                                                              "nachpruefung": "UNSICHER: nicht bestätigt"}}}, f)
        from autonomous.agenten import product
        with mock.patch.object(product.konfig, "VORLAGEN", vorlagen):
            e = self.verkaufsseite({})
        self.assertEqual(e["angebot"], "google_profil")
        self.assertEqual(e["name"], "Verkaufsseite: Google-Profil-Paket")
        html = self.lesen(e["dateien"][0])
        self.assertIn("Google-Profil-Paket", html)
        self.assertIn("Preis: wird vom Inhaber festgelegt.", html)
        self.assertIn("Lieferzeit: wird vom Inhaber festgelegt.", html)
        self.assertIsNone(KEIN_BETRAG.search(html))
        self.assertNotIn("199", html)
        self.assertNotIn("349", html)
        self.assertIn("Keine Garantie für eine bestimmte Platzierung bei Google", html)
        self.assertIn("Keine Bewertungen – weder gekauft noch selbst geschrieben", html)
        self.assertIn("Keine Werbung bei Google (Anzeigen)", html)
        for schritt in ("Anfrage", "Kurzes Gespräch", "Termin vor Ort", "Profil fertig", "Übergabe"):
            self.assertIn("<h3>%s</h3>" % schritt, html)
        self.assertIn('href="beispiel.html"', html)
        self.assertIn('href="beispiel-uebergabe.html"', html)
        namen = [os.path.basename(p) for p in e["dateien"]]
        self.assertEqual(namen, ["index.html", "beispiel.html", "beispiel-pruefliste.html", "beispiel-uebergabe.html"])
        self.assertIn("BEISPIEL – fiktive Musterfirma", self.lesen(e["dateien"][1]))
        vorschlag = e["preis_vorschlag_recherche"]
        self.assertEqual((vorschlag["min_eur"], vorschlag["max_eur"]), (199, 349))
        self.assertIn("nicht freigegeben", vorschlag["status"])
        self.assertIn("UNSICHER", vorschlag["status"])
        # ohne Kontaktdaten des Anbieters ehrlich ein Mangel; Beispiele selbst sind fehlerfrei
        self.assertEqual(e["status"], "qualitaet_mangel")
        maengel = e["qualitaet"]["maengel"]
        self.assertEqual(maengel, ["index.html: Kontaktweg vorhanden (Telefon oder E-Mail)"])

    def test_mit_preis_und_kontakt_ist_qualitaet_ok(self):
        e = self.verkaufsseite({"preis": "249", "lieferzeit": "1–3 Wochen (Bestätigung durch Google nicht "
                                                           "eingerechnet)", "telefon": "0214 99999"})
        html = self.lesen(e["dateien"][0])
        self.assertIn("249,00 €", html)
        self.assertEqual(e["status"], "qualitaet_ok", e["qualitaet"])
        self.assertNotIn("preis_vorschlag_recherche", e)

    def test_webseiten_variante_bleibt_verfuegbar(self):
        e = self.verkaufsseite({"angebot": "webseite"})
        self.assertEqual(e["name"], "Verkaufsseite: Webseiten-Paket")
        self.assertEqual([os.path.basename(p) for p in e["dateien"]], ["index.html", "beispiel.html"])
        html = self.lesen(e["dateien"][0])
        self.assertIn("Webseiten-Paket", html)
        self.assertNotIn("Google-Profil-Paket", html)
        # erneute Prüfung eines vorhandenen Produkts funktioniert für beide Varianten
        for produkt_id in (e["produkt_id"], self.verkaufsseite({})["produkt_id"]):
            aid = self.api("POST", "/api/produkte/%s/pruefen" % produkt_id)["aufgabe_id"]
            self.orch.alle_abarbeiten()
            self.assertEqual(self.kern.aufgaben.hole(aid)["status"], "abgeschlossen")

    def test_ungueltiges_angebot(self):
        for falsch in ("krypto", 1, ["google_profil"]):
            with self.assertRaises(ValueError, msg=str(falsch)):
                self.api("POST", "/api/produkte/verkaufsseite", {"angebot": falsch})


class TestRollenUndBeispiele(GoogleProfilTest):
    def test_rolle_und_rechte(self):
        product = self.kern.register.hole("product")
        self.assertIn("google_profil_paket", product.aufgabentypen)
        self.assertNotIn("kundenkontakt", product.rechte)
        self.assertNotIn("veroeffentlichung", product.rechte)
        self.assertNotIn("web_abruf", product.rechte)  # das Paket greift nie auf Google zu

    def test_committete_beispiele_sind_fehlerfrei_und_ohne_offene_punkte(self):
        namen = google_profil.BEISPIEL_COMMITTET
        pfade = {n: os.path.join(BEISPIELE, n) for n in namen.values()}
        e = qualitaet.google_profil_pruefen(pfade, google_profil.eingabe_pruefen(google_profil.BEISPIEL_DATEN), namen)
        self.assertTrue(e["bestanden"], [p for p in e["pruefungen"] if not p["ok"]])
        self.assertEqual(e["offene_punkte"], [])  # Beispiele erzeugen keine Aufgaben für den Inhaber
        for pfad in pfade.values():
            self.assertIn("BEISPIEL – fiktive Musterfirma", self.lesen(pfad))
        self.assertIn("kontakt@musterfirma.example", self.lesen(pfade[namen["entwurf"]]))
        verkauf = self.lesen(os.path.join(BEISPIELE, "verkaufsseite.html"))
        self.assertIn("Google-Profil-Paket", verkauf)
        self.assertIn('href="google-profil-entwurf.html"', verkauf)
        self.assertIn('href="google-profil-uebergabe.html"', verkauf)
        self.assertIn("Webseiten-Paket", self.lesen(os.path.join(BEISPIELE, "verkaufsseite-webseiten.html")))
        self.assertEqual(verkaufsseite.beispiele_inhalte()["verkaufsseite.html"], verkauf)


if __name__ == "__main__":
    unittest.main()
