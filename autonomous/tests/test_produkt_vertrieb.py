# -*- coding: utf-8 -*-
"""Tests Phase 5: Produkt (Webseiten-Paket, Verkaufsseite, Qualität) und Vertrieb (Kontakte, Angebote,
Nachrichten, Versand nur mit Freigabe). Jeder Test hat einen eigenen, leeren Datenordner."""

import os
import re
import tempfile
import unittest

os.environ["AUTONOMOUS_DATEN"] = tempfile.mkdtemp(prefix="autonomous-pv-")  # vor dem Import; je Test eigener Ordner (KernTest)

from autonomous import api  # noqa: E402
from autonomous import api_vertrieb  # noqa: E402,F401  (registriert die Routen)
from autonomous.produkte import qualitaet, verkaufsseite, webseite  # noqa: E402
from autonomous.produkte import datei_schreiben, produkt_hole, sicherer_pfad  # noqa: E402
from autonomous.tests.hilfe import KernTest  # noqa: E402

BEISPIELE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "beispiele")
BETRIEB = {"firma": "Muster Bau & Söhne", "branche": "Gebäudereinigung", "ort": "Leverkusen",
           "leistungen": "Büroreinigung, Treppenhausreinigung, Glasreinigung", "telefon": "0214 123456",
           "email": "info@muster.example", "einzugsgebiet": "Leverkusen und Köln",
           "oeffnungszeiten": "Mo–Fr 7–17 Uhr; Sa nach Vereinbarung"}


class VertriebTest(KernTest):
    def abarbeiten(self):
        return self.orch.alle_abarbeiten()

    def aufgabe(self, aid):
        return self.kern.aufgaben.hole(aid)

    def webseite_erzeugen(self, **aenderung):
        aid = self.api("POST", "/api/produkte/webseite", dict(BETRIEB, **aenderung))["aufgabe_id"]
        self.abarbeiten()
        a = self.aufgabe(aid)
        self.assertEqual(a["status"], "abgeschlossen", a["fehler"])
        return a["ergebnis"]

    def html_von(self, ergebnis, index=0):
        with open(ergebnis["dateien"][index], encoding="utf-8") as f:
            return f.read()

    def kontakt(self, **felder):
        daten = {"firma": "Test GmbH", "quelle": "eigenes Netzwerk", "ort": "Köln", "ansprechpartner": "Alex Beispiel"}
        daten.update(felder)
        return self.api("POST", "/api/kontakte", daten)["id"]

    def angebot(self, **felder):
        daten = {"betrag": "890"}
        daten.update(felder)
        aid = self.api("POST", "/api/angebote", daten)["aufgabe_id"]
        self.abarbeiten()
        a = self.aufgabe(aid)
        self.assertEqual(a["status"], "abgeschlossen", a["fehler"])
        return a["ergebnis"]["angebot_id"]


class TestWebseite(VertriebTest):
    def test_webseite_ueber_orchestrator_mit_qualitaetspruefung(self):
        e = self.webseite_erzeugen()
        p = produkt_hole(self.kern, e["produkt_id"])
        self.assertEqual(p["status"], "qualitaet_ok")
        self.assertEqual(p["typ"], "webseite")
        self.assertEqual(p["dateien"], ["index.html"])
        self.assertTrue(p["qualitaet"]["bestanden"])
        self.assertTrue(e["dateien"][0].startswith(os.path.realpath(os.environ["AUTONOMOUS_DATEN"])) or
                        e["dateien"][0].startswith(os.environ["AUTONOMOUS_DATEN"]))
        html = self.html_von(e)
        self.assertIn("Muster Bau &amp; Söhne", html)
        self.assertIn('href="tel:0214123456"', html)
        self.assertIn('href="mailto:info@muster.example"', html)
        self.assertIn("Treppenhausreinigung", html)
        self.assertIn("Leverkusen und Köln", html)
        self.assertIn("PLATZHALTER – Vom Inhaber auszufüllen – keine Rechtsberatung", html)
        offen = " ".join(e["qualitaet"]["offene_punkte"])
        self.assertIn("Impressum", offen)
        self.assertIn("Datenschutz", offen)
        self.assertTrue(any("Platzhalter" in x for x in e["einschraenkungen"]))

    def test_eingaben_werden_escaped(self):
        e = self.webseite_erzeugen(firma="<script>alert(1)</script>",
                                   leistungen=["<img src=x onerror=alert(1)>", "Fenster & Glas"],
                                   slogan='Sauber "und" <b>gründlich</b>')
        html = self.html_von(e)
        self.assertIn("&lt;script&gt;alert(1)&lt;/script&gt;", html)
        self.assertNotIn("<script", html)
        self.assertNotIn("<img", html)
        self.assertNotIn("<b>", html)
        self.assertIn("Fenster &amp; Glas", html)
        self.assertIn("Sauber &quot;und&quot;", html)
        self.assertTrue(e["qualitaet"]["bestanden"], e["qualitaet"])

    def test_keine_externen_ressourcen_und_kein_javascript(self):
        html = self.html_von(self.webseite_erzeugen())
        for attribut, wert in re.findall(r'\s(src|href|action)="([^"]*)"', html):
            self.assertTrue(wert.startswith(("#", "tel:", "mailto:")), (attribut, wert))
        self.assertNotIn("http://", html)
        self.assertNotIn("https://", html)
        self.assertNotIn("@import", html)
        self.assertNotIn("url(", html)
        self.assertNotRegex(html, r"(?i)<script|\son\w+=|javascript:")

    def test_ohne_kontaktweg_ist_qualitaet_mangelhaft(self):
        e = self.webseite_erzeugen(telefon="", email="")
        self.assertEqual(produkt_hole(self.kern, e["produkt_id"])["status"], "qualitaet_mangel")
        self.assertIn("Kontaktweg vorhanden (Telefon oder E-Mail)", e["qualitaet"]["maengel"])

    def test_pflichtfelder_und_ungueltige_eingaben(self):
        for falsch in ({"firma": ""}, {"leistungen": ""}, {"telefon": "abc"}, {"email": "keine-mail"},
                       {"firma": ["Liste"]}, {"firma": "x" * 81}, {"leistungen": ["y" * 81]},
                       {"leistungen": ["L%d" % i for i in range(13)]}):
            with self.assertRaises((api.ApiFehler, ValueError), msg=str(falsch)):
                self.api("POST", "/api/produkte/webseite", dict(BETRIEB, **falsch))
        # Direkt als Aufgabe angelegt: fachlicher Fehler → fehlgeschlagen ohne sinnlose Wiederholung
        aid = self.kern.aufgaben.anlegen("x", "webseite_erstellen", "product", "eigentuemer", {"firma": "A"})
        self.abarbeiten()
        a = self.aufgabe(aid)
        self.assertEqual(a["status"], "fehlgeschlagen")
        self.assertEqual(a["versuche"], 1)

    def test_qualitaetspruefung_erkennt_eingeschleustes_script_und_fremde_ressource(self):
        e = self.webseite_erzeugen()
        with open(e["dateien"][0], "a", encoding="utf-8") as f:
            f.write('<script>alert(1)</script><img src="https://tracker.example/x.gif">')
        aid = self.api("POST", "/api/produkte/%s/pruefen" % e["produkt_id"])["aufgabe_id"]
        self.abarbeiten()
        a = self.aufgabe(aid)
        self.assertEqual(a["status"], "abgeschlossen", a["fehler"])
        self.assertFalse(a["ergebnis"]["bestanden"])
        falsch = {p["name"] for p in a["ergebnis"]["pruefungen"] if not p["ok"]}
        self.assertIn("Kein JavaScript", falsch)
        self.assertIn("Keine externen Ressourcen", falsch)
        self.assertIn("Nur erwartete HTML-Elemente", falsch)
        self.assertEqual(produkt_hole(self.kern, e["produkt_id"])["status"], "qualitaet_mangel")

    def test_qualitaetspruefung_direkt(self):
        schlecht = "<html><body><h2>x</h2><a href=\"//fremd.example/a.css\">a</a>" \
                   "<div onclick=\"x()\">y</div><p style=\"background:url(http://x.example/a.png)\">z</p></body></html>"
        e = qualitaet.pruefen(schlecht)
        falsch = {p["name"] for p in e["pruefungen"] if not p["ok"]}
        for name in ("Kein JavaScript", "Keine externen Ressourcen", "Mobil-Ansicht (viewport)",
                     'Sprache Deutsch (lang="de")', "Seitentitel", "Genau eine Hauptüberschrift (h1)",
                     "Impressum-Abschnitt vorhanden", "Datenschutz-Abschnitt vorhanden",
                     "Kontaktweg vorhanden (Telefon oder E-Mail)"):
            self.assertIn(name, falsch)
        self.assertFalse(e["bestanden"])
        # Nicht escapte Eingabe wird erkannt
        e = qualitaet.pruefen("<p><b>fett</b></p>", eingaben={"firma": "<b>fett</b>"}, kontakt_pflicht=False)
        self.assertIn("Eingaben sicher eingebaut (escaped)", {p["name"] for p in e["pruefungen"] if not p["ok"]})
        # Zu groß
        e = qualitaet.pruefen("<p>x</p>", groesse=300 * 1024)
        self.assertIn("Dateigröße unter 200 KB", {p["name"] for p in e["pruefungen"] if not p["ok"]})


class TestVerkaufsseite(VertriebTest):
    def test_ohne_preis_steht_platzhalter_und_kein_betrag_auf_der_seite(self):
        aid = self.api("POST", "/api/produkte/verkaufsseite", {})["aufgabe_id"]
        self.abarbeiten()
        a = self.aufgabe(aid)
        self.assertEqual(a["status"], "abgeschlossen", a["fehler"])
        e = a["ergebnis"]
        html = self.html_von(e)
        self.assertIn("Preis: wird vom Inhaber festgelegt.", html)
        self.assertIn("Lieferzeit: wird vom Inhaber festgelegt.", html)
        self.assertIsNone(re.search(r"\d\s*(€|EUR|Euro)", html), "Kein Betrag ohne Vorgabe des Inhabers")
        self.assertIn("Preis festlegen (Inhaber)", " ".join(e["qualitaet"]["offene_punkte"]))
        self.assertTrue(os.path.isfile(e["dateien"][1]))  # Beispielseite liegt daneben
        self.assertIn('href="beispiel.html"', html)
        self.assertIn("BEISPIEL – fiktive Musterfirma", self.html_von(e, 1))
        # Ohne Kontakt des Anbieters kann die Seite nicht live gehen → ehrlich als Mangel
        self.assertEqual(e["status"], "qualitaet_mangel")
        vorschlag = e.get("preis_vorschlag_recherche")
        if vorschlag and "min_eur" in vorschlag:  # nur wenn die Recherche das Webseiten-Feld empfiehlt
            self.assertIn("nicht freigegeben", vorschlag["status"])

    def test_preisvorschlag_nur_fuer_das_passende_geschaeftsfeld(self):
        import json
        from unittest import mock
        from autonomous.agenten import product
        pfad = os.path.join(os.environ["AUTONOMOUS_DATEN"], "vorlagen")
        os.makedirs(pfad)
        with mock.patch.object(product.konfig, "VORLAGEN", pfad):
            self.assertIsNone(product._preisvorschlag_recherche())
            for feld, erwartet in (("webseiten", "min_eur"), ("digitale_dienstleistungen", "abweichende_empfehlung")):
                with open(os.path.join(pfad, "marktbewertung.json"), "w", encoding="utf-8") as f:
                    json.dump({"empfehlung": {"feld_id": feld, "angebot": "Paket X",
                                              "preis_vorschlag_eur": {"min": 100, "max": 200}}}, f)
                v = product._preisvorschlag_recherche()
                self.assertIn(erwartet, v)
                if feld != "webseiten":
                    self.assertNotIn("min_eur", v)  # fremder Preis wird dem Webseiten-Paket nie zugeordnet
            with open(os.path.join(pfad, "marktbewertung.json"), "w", encoding="utf-8") as f:
                f.write("{kaputt")
            self.assertEqual(product._preisvorschlag_recherche()["hinweis"], "Marktbewertung nicht lesbar.")

    def test_mit_preis_und_kontakt_des_inhabers(self):
        aid = self.api("POST", "/api/produkte/verkaufsseite",
                       {"preis": "490", "lieferzeit": "10 Werktage", "telefon": "0214 99999",
                        "anbieter": "Familienbetrieb (Name folgt)"})["aufgabe_id"]
        self.abarbeiten()
        e = self.aufgabe(aid)["ergebnis"]
        html = self.html_von(e)
        self.assertIn("490,00 €", html)
        self.assertIn("10 Werktage", html)
        self.assertNotIn("Preis: wird vom Inhaber festgelegt", html)
        self.assertIn("Umsatzsteuer-Hinweis zum Preis ergänzen (Inhaber)", " ".join(e["qualitaet"]["offene_punkte"]))
        self.assertEqual(e["status"], "qualitaet_ok", e["qualitaet"])
        self.assertNotIn("preis_vorschlag_recherche", e)
        with self.assertRaises(ValueError):
            self.api("POST", "/api/produkte/verkaufsseite", {"preis": "0"})


class TestKontakteUndAngebote(VertriebTest):
    def test_kontakte_api(self):
        kid = self.kontakt()
        daten = self.api("GET", "/api/kontakte")
        self.assertEqual(daten["stufen"], ["neu", "kontaktiert", "interessiert", "angebot", "gewonnen", "verloren"])
        self.assertEqual(daten["kontakte"][0]["id"], kid)
        self.assertEqual(daten["kontakte"][0]["einwilligung"], "keine")
        with self.assertRaises(api.ApiFehler):
            self.api("POST", "/api/kontakte", {"firma": "X", "quelle": "Messe", "einwilligung": "ja"})
        with self.assertRaises(api.ApiFehler):
            self.kontakt()  # doppelt
        with self.assertRaises(api.ApiFehler):
            self.api("POST", "/api/kontakte/%s/status" % kid, {"status": "erfunden"})
        self.assertEqual(self.api("POST", "/api/kontakte/%s/status" % kid,
                                  {"status": "kontaktiert", "naechster_schritt": "Brief senden"}), {"ok": True})
        k = self.api("GET", "/api/kontakte")["kontakte"][0]
        self.assertEqual((k["status"], k["naechster_schritt"]), ("kontaktiert", "Brief senden"))
        with self.assertRaises(api.ApiFehler):
            self.api("POST", "/api/kontakte/k_gibtsnicht/status", {"status": "neu"})

    def test_angebot_entwurf_und_statuswechsel(self):
        kid = self.kontakt()
        with self.assertRaises((api.ApiFehler, ValueError)):
            self.api("POST", "/api/angebote", {"kontakt_id": kid})  # Betrag fehlt
        with self.assertRaises(api.ApiFehler):
            self.api("POST", "/api/angebote", {"kontakt_id": "k_gibtsnicht", "betrag": "100"})
        an = self.angebot(kontakt_id=kid, betrag="1.200,50")
        liste = self.api("GET", "/api/angebote")["angebote"]
        self.assertEqual(liste[0]["id"], an)
        self.assertEqual(liste[0]["status"], "entwurf")
        self.assertEqual(liste[0]["kontakt_firma"], "Test GmbH")
        pfad = os.path.join(os.environ["AUTONOMOUS_DATEN"], "produkte", "angebote", an, "angebot-entwurf.html")
        with open(pfad, encoding="utf-8") as f:
            html = f.read()
        self.assertIn("ENTWURF – vor Versand prüfen", html)
        self.assertIn("1.200,50 €", html)  # deutsche Schreibweise mit Tausenderpunkt
        self.assertIn("Guten Tag Alex Beispiel,", html)
        self.assertNotRegex(html, r"(?i)<script|\son\w+=")
        # Erst prüfen, dann (selbst) versenden
        with self.assertRaises(api.ApiFehler):
            self.api("POST", "/api/angebote/%s/status" % an, {"status": "versendet"})
        r = self.api("POST", "/api/angebote/%s/status" % an, {"status": "geprueft"})
        self.assertTrue(r["ansehen_url"].endswith("angebot-geprueft.html"))
        with open(os.path.join(os.path.dirname(pfad), "angebot-geprueft.html"), encoding="utf-8") as f:
            self.assertNotIn("ENTWURF – vor Versand prüfen", f.read())
        self.assertTrue(os.path.isfile(pfad))  # Entwurf bleibt erhalten
        self.api("POST", "/api/angebote/%s/status" % an, {"status": "versendet"})
        r = self.api("POST", "/api/angebote/%s/status" % an, {"status": "angenommen"})
        self.assertIn("keine Einnahme", r["hinweis"])
        self.assertEqual(self.kern.finanzen.uebersicht()["einnahmen_verifiziert_cent"], 0)
        with self.assertRaises(api.ApiFehler):
            self.api("POST", "/api/angebote/%s/status" % an, {"status": "abgelehnt"})

    def test_versand_nur_mit_freigabe_und_ja_sendet_trotzdem_nichts(self):
        an = self.angebot(kontakt_id=self.kontakt())
        with self.assertRaises(api.ApiFehler):  # Entwurf darf nicht in den Versand
            self.api("POST", "/api/angebote/%s/versenden" % an)
        self.api("POST", "/api/angebote/%s/status" % an, {"status": "geprueft"})
        aid = self.api("POST", "/api/angebote/%s/versenden" % an)["aufgabe_id"]
        self.abarbeiten()
        a = self.aufgabe(aid)
        self.assertEqual(a["status"], "wartet_auf_freigabe")
        f = self.api("GET", "/api/freigaben", query={"status": "offen"})["freigaben"]
        self.assertEqual(len(f), 1)
        self.assertEqual((f[0]["aktion"], f[0]["ziel"]), ("kundenkontakt", "angebot:" + an))
        self.assertIn("Test GmbH", f[0]["datenumfang"])
        self.assertEqual(self.api("POST", "/api/freigaben/%s/entscheiden" % f[0]["id"], {"entscheidung": "ja"}),
                         {"status": "erteilt"})
        self.abarbeiten()
        a = self.aufgabe(aid)
        self.assertEqual(a["status"], "abgeschlossen", a["fehler"])
        self.assertIs(a["ergebnis"]["versendet"], False)
        self.assertIn("Kein Versandkanal", a["ergebnis"]["grund"])
        self.assertEqual(self.api("GET", "/api/angebote")["angebote"][0]["status"], "geprueft")

    def test_nein_ist_bindend_erneute_anfrage_sofort_blockiert(self):
        an = self.angebot(kontakt_id=self.kontakt())
        self.api("POST", "/api/angebote/%s/status" % an, {"status": "geprueft"})
        aid = self.api("POST", "/api/angebote/%s/versenden" % an)["aufgabe_id"]
        self.abarbeiten()
        fid = self.aufgabe(aid)["freigabe_id"]
        self.api("POST", "/api/freigaben/%s/entscheiden" % fid, {"entscheidung": "nein"})
        self.assertEqual(self.aufgabe(aid)["status"], "abgebrochen")
        zweite = self.api("POST", "/api/angebote/%s/versenden" % an)["aufgabe_id"]
        self.abarbeiten()
        self.assertEqual(self.aufgabe(zweite)["status"], "abgebrochen")
        self.assertIn("Blockiert", self.kern.aufgaben.verlauf(zweite)[-1]["notiz"])
        self.assertEqual(len(self.api("GET", "/api/freigaben")["freigaben"]), 1, "keine neue Rückfrage")

    def test_nachricht_ohne_einwilligung_empfiehlt_brief(self):
        kid = self.kontakt(branche="Malerbetrieb")
        aid = self.api("POST", "/api/vertrieb/nachricht", {"kontakt_id": kid, "anlass": "Erstkontakt"})["aufgabe_id"]
        self.abarbeiten()
        e = self.aufgabe(aid)["ergebnis"]
        self.assertEqual(e["kanal_empfehlung"], "brief")
        self.assertIs(e["sendefertig"], False)
        self.assertIn("§ 7 UWG", e["hinweis_recht"])
        self.assertIn("Brief", e["hinweis_recht"])
        self.assertIn("[Straße, Hausnummer]", e["text"])
        self.assertEqual(self.api("GET", "/api/freigaben")["freigaben"], [])  # nichts angefragt, nichts gesendet
        # Nachfassen ohne versendetes Angebot → ehrlich Erstkontakt
        aid = self.api("POST", "/api/vertrieb/nachricht", {"kontakt_id": kid, "anlass": "Angebot nachfassen"})[
            "aufgabe_id"]
        self.abarbeiten()
        e = self.aufgabe(aid)["ergebnis"]
        self.assertEqual(e["vorlage"], "erstkontakt")
        self.assertIn("kein versendetes Angebot", e["hinweis"])

    def test_nachricht_mit_dokumentierter_einwilligung_als_email_entwurf(self):
        kid = self.kontakt(einwilligung="ja", einwilligung_nachweis="Visitenkarte und Zusage am 12.11., Messe Köln")
        aid = self.api("POST", "/api/vertrieb/nachricht", {"kontakt_id": kid})["aufgabe_id"]
        self.abarbeiten()
        e = self.aufgabe(aid)["ergebnis"]
        self.assertEqual(e["kanal_empfehlung"], "email")
        self.assertIs(e["sendefertig"], False)
        self.assertIn("Eine kurze Antwort genügt", e["text"])
        self.assertEqual(e["status"], "ENTWURF – nicht versendet")

    def test_nachricht_standard_ist_google_profil_ohne_versprechen(self):
        kid = self.kontakt()
        aid = self.api("POST", "/api/vertrieb/nachricht", {"kontakt_id": kid})["aufgabe_id"]
        self.abarbeiten()
        e = self.aufgabe(aid)["ergebnis"]
        self.assertEqual(e["angebot"], "google_profil")
        self.assertIn("Google-Unternehmensprofil", e["text"])
        self.assertIn("Inhaber", e["text"])
        for versprechen in ("garantiert", "Platz 1", "ganz oben", "mehr Kunden"):
            self.assertNotIn(versprechen, e["text"])
        # Webseiten-Variante bleibt über die Eingabe erreichbar
        aid = self.kern.aufgaben.anlegen("N", "nachricht_entwurf", "sales", "eigentuemer",
                                         {"kontakt_id": kid, "angebot": "webseite"})
        self.abarbeiten()
        self.assertIn("Webseite", self.aufgabe(aid)["ergebnis"]["text"])

    def test_pipeline_auswertung(self):
        kid = self.kontakt()
        self.angebot(kontakt_id=kid, betrag="500")
        aid = self.api("POST", "/api/vertrieb/auswertung")["aufgabe_id"]
        self.abarbeiten()
        e = self.aufgabe(aid)["ergebnis"]
        self.assertEqual(e["kontakte_nach_status"]["neu"], 1)
        self.assertEqual(e["angebote_nach_status"]["entwurf"]["anzahl"], 1)
        self.assertIn("keine Einnahme", e["angebote_offen_summe"])
        self.assertIsNone(e["abschlussquote_kontakte_prozent"])


class TestApiUndDateien(VertriebTest):
    def test_produkte_liste_vertrag(self):
        e = self.webseite_erzeugen()
        p = self.api("GET", "/api/produkte")["produkte"][0]
        for feld in ("id", "name", "typ", "status", "ordner", "dateien", "qualitaet", "einschraenkungen", "erstellt",
                     "ansehen_url"):
            self.assertIn(feld, p)
        self.assertEqual(p["ansehen_url"], "/produkte/%s/index.html" % e["produkt_id"])
        self.assertIsInstance(p["qualitaet"], dict)
        self.assertIsInstance(p["einschraenkungen"], list)
        self.assertEqual(self.api("GET", "/api/produkte/%s" % e["produkt_id"])["id"], e["produkt_id"])
        with self.assertRaises(api.ApiFehler):
            self.api("POST", "/api/produkte/p_gibtsnicht/pruefen")

    def test_dateien_nie_ueberschreiben_und_nie_ausserhalb(self):
        pfad = sicherer_pfad("p_test", "index.html")
        datei_schreiben(pfad, "eins")
        with self.assertRaises(FileExistsError):
            datei_schreiben(pfad, "zwei")
        with open(pfad, encoding="utf-8") as f:
            self.assertEqual(f.read(), "eins")
        with self.assertRaises(PermissionError):
            datei_schreiben(os.path.join(tempfile.gettempdir(), "autonomous-ausserhalb.html"), "x")
        for falsch in ("..", "../x", "a/b", ""):
            with self.assertRaises(ValueError):
                sicherer_pfad(falsch)

    def test_rollen_und_rechte_des_product_und_sales_agenten(self):
        product = self.kern.register.hole("product")
        sales = self.kern.register.hole("sales")
        self.assertNotIn("kundenkontakt", product.rechte)
        self.assertNotIn("echte_zahlung", sales.rechte)
        self.assertNotIn("veroeffentlichung", product.rechte | sales.rechte)
        for typ in ("webseite_erstellen", "verkaufsseite_erstellen", "qualitaetspruefung"):
            self.assertIn(typ, product.aufgabentypen)
        for typ in ("angebot_entwurf", "nachricht_entwurf", "pipeline_auswertung", "angebot_versenden"):
            self.assertIn(typ, sales.aufgabentypen)


class TestBeispiele(unittest.TestCase):
    def test_committete_beispiele_sind_aktuell_und_fehlerfrei(self):
        # Alle committeten Beispiele (Webseite, Verkaufsseiten beider Angebote, Google-Profil-Unterlagen)
        erwartet = verkaufsseite.beispiele_inhalte()
        for name, inhalt in erwartet.items():
            with open(os.path.join(BEISPIELE, name), encoding="utf-8") as f:
                self.assertEqual(f.read(), inhalt, "%s veraltet – neu erzeugen mit: python3 -c \"from "
                                 "autonomous.produkte.verkaufsseite import beispiele_schreiben; "
                                 "beispiele_schreiben('autonomous/beispiele')\"" % name)
        e = qualitaet.pruefen(erwartet["beispiel-webseite.html"],
                              webseite.eingabe_pruefen(webseite.BEISPIEL_DATEN))
        self.assertTrue(e["bestanden"], e)
        self.assertIn("fiktive Musterfirma", erwartet["beispiel-webseite.html"])
        self.assertIn(".example", erwartet["beispiel-webseite.html"])  # reservierte, nie vergebene Endung


if __name__ == "__main__":
    unittest.main()
