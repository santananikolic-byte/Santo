# -*- coding: utf-8 -*-
"""Tests Auftrags-Radar: Quellen (auf echten, gespeicherten Antworten), Bewertung, Akquise-Agent,
Bewerbungs-Mappe, Schnittstelle, Zeitplan und sicherer Abrufer. KEIN Netz in diesen Tests."""

import datetime
import json
import os
import re
import urllib.request
from unittest import mock

from autonomous import api, netz
from autonomous import api_auftraege  # noqa: F401  (Routen registrieren)
from autonomous.auftraege import quellen as q
from autonomous.auftraege.bewertung import bewerten
from autonomous.tests.hilfe import KernTest

DATEN = os.path.join(os.path.dirname(os.path.abspath(__file__)), "daten")
STICHTAG = datetime.date(2026, 11, 21)  # Tag, an dem die Testdaten abgerufen wurden


def lesen(name):
    with open(os.path.join(DATEN, name), "rb") as f:
        return f.read()


class Ersatznetz:
    """Liefert die gespeicherten echten Antworten statt eines echten Abrufs."""

    def __init__(self, ausfall=()):
        self.aufrufe = []
        self.ausfall = set(ausfall)

    def __call__(self, url, methode="GET", daten=None, kopf=None, **_):
        self.aufrufe.append((methode, url))
        if url.startswith(q.TED_URL):
            if "ted" in self.ausfall:
                raise netz.NetzFehler("Quelle nicht erreichbar: Testausfall")
            seite = json.loads(daten.decode("utf-8"))["page"]
            roh = lesen("ted_suche.json") if seite == 1 else json.dumps(
                {"notices": [], "totalNoticeCount": 38}).encode()
            return netz.Antwort(200, roh, "utf-8", url, "application/json")
        if url.startswith(q.BUND_BASIS):
            if "service_bund" in self.ausfall:
                raise netz.NetzFehler("Quelle antwortet mit Fehler 503")
            return netz.Antwort(200, lesen("service_bund_reinigung.rss"), "utf-8", url, "text/xml;charset=utf-8")
        if url.startswith(q.EVERGABE_URL):
            if "evergabe_nrw" in self.ausfall:
                raise netz.NetzFehler("Quelle nicht erreichbar: Testausfall")
            return netz.Antwort(200, lesen("evergabe_nrw_start.html"), "cp1252", url, "text/html;charset=ISO-8859-1")
        raise AssertionError("unerwartete Adresse im Test: %s" % url)


class RadarTest(KernTest):
    def setUp(self):
        super().setUp()
        self._heute = mock.patch("autonomous.auftraege.heute", return_value=STICHTAG)
        self._heute.start()
        self.netz = Ersatznetz()
        self._netz = mock.patch("autonomous.netz.abrufen", self.netz)
        self._netz.start()

    def tearDown(self):
        self._netz.stop()
        self._heute.stop()
        super().tearDown()

    def einschalten(self):
        self.kern.einstellungen.setze("internet_recherche_erlaubt", True, "eigentuemer")

    def suchen(self):
        aid = self.kern.aufgaben.anlegen("Suche", "ausschreibungen_suchen", "akquise", "eigentuemer", {})
        self.orch.alle_abarbeiten()
        return self.kern.aufgaben.hole(aid)

    def synthetisch(self, titel, frist_tage, status="neu", punkte=80, quelle="evergabe_nrw", extern_id=None):
        frist = (STICHTAG + datetime.timedelta(days=frist_tage)).isoformat() if frist_tage is not None else None
        aid = "as_test%06d" % (abs(hash((titel, frist_tage, extern_id))) % 1000000)
        z = "2026-11-21T08:00:00+01:00"
        self.kern.db.ausfuehren(
            "INSERT INTO ausschreibungen (id, quelle, extern_id, titel, vergabestelle, region, frist, verfahren, link,"
            " punkte, begruendung, status, gefunden, aktualisiert) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (aid, quelle, extern_id or aid, titel, "Stadt Muster", "NRW", frist, "UVgO – Ausschreibung",
             "https://www.evergabe.nrw.de/VMPCenter/public/company/projectForwarding.do?pid=1", punkte,
             json.dumps(["+35 Test"]), status, z, z))
        return aid


class TestQuellen(RadarTest):
    def test_ted_auf_echten_daten(self):
        eintraege, gesamt = q.ted_parsen(lesen("ted_suche.json"))
        self.assertEqual(len(eintraege), 20)
        self.assertEqual(gesamt, 38)
        e = eintraege[0]
        self.assertEqual(e["extern_id"], "698163-2026")
        self.assertEqual(e["frist"], "2026-12-01")
        self.assertEqual(e["vergabestelle"], "Emschergenossenschaft (Essen)")
        self.assertIn("Regierungsbezirk Düsseldorf", e["region"])
        self.assertEqual(e["link"], "https://ted.europa.eu/de/notice/-/detail/698163-2026")
        koeln = [x for x in eintraege if "21 Objekten" in x["titel"]][0]
        self.assertIn("Regierungsbezirk Köln", koeln["region"])
        self.assertTrue(all(x["link"].startswith("https://ted.europa.eu/") for x in eintraege))

    def test_ted_anfrage(self):
        url, koerper = q.ted_anfrage(["DEA2", "DEA1"], STICHTAG)
        d = json.loads(koerper)
        self.assertEqual(url, "https://api.ted.europa.eu/v3/notices/search")
        self.assertIn("place-of-performance IN (DEA2 DEA1)", d["query"])
        self.assertIn("deadline-receipt-tender-date-lot>=20261121", d["query"])
        self.assertIn("90911200", d["query"])
        # unzulässige Region wird verworfen, nicht in die Abfrage geschrieben
        self.assertIn("IN (DEA)", json.loads(q.ted_anfrage(["DEA) OR (1=1"], STICHTAG)[1])["query"])

    def test_service_bund_auf_echten_daten(self):
        eintraege = q.bund_parsen(lesen("service_bund_reinigung.rss"))
        self.assertEqual(len(eintraege), 100)
        e = [x for x in eintraege if x["titel"] == "Ortsverwaltung Jesingen Rathaus Reinigung"][0]
        self.assertEqual(e["plz"], "73230")
        self.assertEqual(e["ort"], "Kirchheim unter Teck")
        self.assertEqual(e["frist"], "2026-12-08 09:15")
        self.assertEqual(e["vergabestelle"], "Stadtverwaltung Kirchheim unter Teck")
        self.assertIn("Großröhrsdorf", [x["ort"] for x in eintraege])  # Umlaute heil
        for x in eintraege:
            self.assertNotIn("jsessionid", x["link"].lower())
            self.assertNotIn("#", x["link"])
            self.assertTrue(x["link"].startswith("https://www.service.bund.de/"))

    def test_service_bund_lehnt_dtd_ab(self):
        with self.assertRaises(q.QuellenFehler):
            q.bund_parsen(b'<?xml version="1.0"?><!DOCTYPE r [<!ENTITY a "b">]><rss><channel/></rss>')
        with self.assertRaises(q.QuellenFehler):
            q.bund_parsen(b"kein xml")

    def test_vergabemarktplatz_auf_echten_daten(self):
        eintraege = q.evergabe_parsen(lesen("evergabe_nrw_start.html").decode("cp1252"))
        self.assertEqual(len(eintraege), 13)  # nur offene Ausschreibungen / Teilnahmewettbewerbe
        roetgen = [x for x in eintraege if "Roetgen" in x["titel"]][0]
        self.assertEqual(roetgen["frist"], "2026-12-10 23:59")
        self.assertIn("für 2 Jahre", roetgen["titel"])  # Windows-1252 korrekt gelesen
        self.assertEqual(roetgen["verfahren"], "VgV – Ausschreibung")
        self.assertEqual(roetgen["extern_id"], "pid-1131224")
        self.assertTrue(all(x["link"].startswith("https://www.evergabe.nrw.de/") for x in eintraege))
        self.assertFalse([x for x in eintraege if "Bewerbermanagementsystem" in x["titel"]])  # vergebener Auftrag

    def test_fremde_links_werden_verworfen(self):
        quelltext = ('<table><tr><td><abbr title="20.11.2026 um 10:00 Uhr">x</abbr></td>'
                     '<td><abbr title="10.12.2026 um 10:00 Uhr">x</abbr></td><td>Reinigung Schule</td>'
                     '<td>VgV<br/>Ausschreibung</td><td>Stadt</td>'
                     '<td><a href="https://angreifer.example/projectForwarding.do?pid=5">x</a></td></tr></table>')
        self.assertEqual(q.evergabe_parsen(quelltext), [])


class TestBewertung(RadarTest):
    def alle(self):
        return (q.ted_parsen(lesen("ted_suche.json"))[0] + q.bund_parsen(lesen("service_bund_reinigung.rss"))
                + q.evergabe_parsen(lesen("evergabe_nrw_start.html").decode("cp1252")))

    def punkte(self, teil):
        e = [x for x in self.alle() if teil in x["titel"]][0]
        return bewerten(e, self.kern.einstellungen.alle(), STICHTAG)

    def test_passende_und_unpassende(self):
        p, gruende, passend = self.punkte("Gemeinde Roetgen")
        self.assertTrue(passend, gruende)
        self.assertTrue(self.punkte("Gebäudereinigung Village Jülich")[2])
        for teil, grenze in (("Straßenreinigung und Straßenkehrdienste", 10),       # Ausschluss
                             ("Ortsverwaltung Jesingen", 30),                       # außerhalb (PLZ 73…)
                             ("Hauptsammler", 59),                                  # Kanal, keine Gebäude
                             ("Reinigung von Aufzugsanlagen", 59),                  # Technik
                             ("Beschaffung von Reinigungs- und Hygieneartikel", 59),  # Warenlieferung
                             ("Universität der Künste Berlin", 59)):                # Berlin ohne PLZ
            p, gruende, passend = self.punkte(teil)
            self.assertLessEqual(p, grenze, (teil, gruende))
            self.assertFalse(passend, teil)

    def test_begruendung_nachvollziehbar_und_keine_werte_erfunden(self):
        p, gruende, _ = self.punkte("21 Objekten")
        self.assertEqual(p, sum(int(re.match(r"([+−-]?\d+)", g).group(1).replace("−", "-")) for g in gruende))
        self.assertTrue(any("großer Auftrag" in g for g in gruende))
        self.assertFalse(any("€" in g for g in gruende))

    def test_frist_knapp_wird_gewarnt(self):
        e = {"quelle": "evergabe_nrw", "titel": "Unterhaltsreinigung Rathaus",
             "frist": (STICHTAG + datetime.timedelta(days=3)).isoformat(), "cpv": []}
        p, gruende, _ = bewerten(e, self.kern.einstellungen.alle(), STICHTAG)
        self.assertTrue(any("sehr knapp" in g for g in gruende))


class TestAkquiseAgent(RadarTest):
    def test_ausgeschaltet_klar_blockiert_ohne_wiederholung(self):
        a = self.suchen()
        self.assertEqual(a["status"], "abgebrochen")
        self.assertEqual(a["versuche"], 1)
        self.assertIn("ausgeschaltet", self.kern.aufgaben.verlauf(a["id"])[-1]["notiz"])
        self.assertEqual(self.netz.aufrufe, [])
        with self.assertRaises(api.ApiFehler) as f:
            self.api("POST", "/api/ausschreibungen/suchen")
        self.assertEqual(f.exception.status, 400)

    def test_suche_ende_zu_ende(self):
        self.einschalten()
        a = self.suchen()
        self.assertEqual(a["status"], "abgeschlossen", a["fehler"])
        e = a["ergebnis"]
        self.assertEqual(e["fehlende_quellen"], [])
        self.assertEqual(e["quellen"]["TED (EU-Amtsblatt)"]["gefunden"], 20)
        self.assertEqual(e["quellen"]["service.bund.de"]["gefunden"], 100)
        self.assertEqual(e["quellen"]["Vergabemarktplatz NRW"]["gefunden"], 13)
        self.assertEqual(self.kern.db.wert("SELECT COUNT(*) FROM ausschreibungen"), 133)
        self.assertTrue(e["neu_passend"])
        self.assertTrue(all(x["punkte"] >= 60 for x in e["neu_passend"]))
        self.assertEqual(self.kern.db.wert("SELECT COUNT(*) FROM suchlaeufe WHERE ergebnis='ok'"), 3)
        self.assertEqual(self.kern.gedaechtnis.liste("vorschlag")[0]["thema"], "Neue passende Ausschreibungen")
        # TED nur mit POST, die anderen nur mit GET; service.bund.de höchstens 3 Suchbegriffe
        self.assertTrue(all(m == "POST" for m, u in self.netz.aufrufe if u.startswith(q.TED_URL)))
        self.assertLessEqual(len([u for m, u in self.netz.aufrufe if u.startswith(q.BUND_BASIS)]), 3)

    def test_quelle_faellt_aus_andere_laufen(self):
        self.einschalten()
        self.netz.ausfall = {"ted"}
        a = self.suchen()
        self.assertEqual(a["status"], "abgeschlossen")
        self.assertEqual(a["ergebnis"]["fehlende_quellen"], ["TED (EU-Amtsblatt)"])
        self.assertIn("Nicht erreichbar", a["ergebnis"]["hinweis"])
        self.assertEqual(self.kern.db.wert("SELECT ergebnis FROM suchlaeufe WHERE quelle='ted'"), "fehler")
        self.assertEqual(self.kern.db.wert("SELECT COUNT(*) FROM ausschreibungen WHERE quelle='ted'"), 0)
        self.assertEqual(self.kern.db.wert("SELECT COUNT(*) FROM ausschreibungen"), 113)

    def test_kein_doppelter_eintrag_und_status_des_eigentuemers_bleibt(self):
        self.einschalten()
        self.suchen()
        roetgen = self.kern.db.eins("SELECT id FROM ausschreibungen WHERE titel LIKE '%Roetgen%'")["id"]
        self.api("POST", "/api/ausschreibungen/%s/status" % roetgen, {"status": "interessant", "notiz": "ansehen"})
        a2 = self.suchen()
        self.assertEqual(a2["status"], "abgeschlossen")
        self.assertEqual(self.kern.db.wert("SELECT COUNT(*) FROM ausschreibungen"), 133)
        z = self.kern.db.eins("SELECT status, notiz FROM ausschreibungen WHERE id=?", (roetgen,))
        self.assertEqual((z["status"], z["notiz"]), ("interessant", "ansehen"))
        self.assertEqual(a2["ergebnis"]["neu_passend"], [])

    def test_supervisor_prueft_jede_adresse(self):
        self.einschalten()
        with mock.patch.object(q, "EVERGABE_URL", "https://angreifer.example/welcome.do"):
            a = self.suchen()
        self.assertEqual(a["status"], "abgeschlossen")
        self.assertIn("Vergabemarktplatz NRW", a["ergebnis"]["fehlende_quellen"])
        self.assertEqual(self.kern.db.wert("SELECT ergebnis FROM suchlaeufe WHERE quelle='evergabe_nrw'"), "gesperrt")
        self.assertFalse([u for m, u in self.netz.aufrufe if "angreifer" in u])

    def test_bewerbungs_mappe(self):
        aid = self.synthetisch("<script>alert(1)</script> Unterhaltsreinigung Grundschule", 10)
        auftrag = self.api("POST", "/api/ausschreibungen/%s/vorbereiten" % aid)["aufgabe_id"]
        self.orch.alle_abarbeiten()
        a = self.kern.aufgaben.hole(auftrag)
        self.assertEqual(a["status"], "abgeschlossen", a["fehler"])
        pfad = a["ergebnis"]["dateien"][0]
        self.assertTrue(pfad.startswith(os.environ["AUTONOMOUS_DATEN"]))
        with open(pfad, encoding="utf-8") as f:
            seite = f.read()
        self.assertNotRegex(seite, r"(?i)<script|\son\w+=|javascript:")
        self.assertIn("&lt;script&gt;", seite)
        self.assertIn("verbindlich sind nur die Vergabeunterlagen", seite)
        self.assertIn("OFFEN – bitte in den Einstellungen festlegen", seite)  # Stundensatz nicht erfunden
        self.assertIn("15,00 €", seite)
        self.assertIn("läuft am 01.01.2027", seite)
        self.assertIn("NICHTS abgegeben", seite)
        self.assertNotRegex(seite, r"(?i)(src|href)=\"http://")
        z = self.kern.db.eins("SELECT status, unterlagen FROM ausschreibungen WHERE id=?", (aid,))
        self.assertEqual(z["status"], "vorbereitet")
        liste = self.api("GET", "/api/ausschreibungen")["ausschreibungen"]
        self.assertEqual([x["unterlagen_url"] for x in liste if x["id"] == aid],
                         ["/produkte/ausschreibungen/%s/mappe.html" % aid])
        with self.assertRaises(api.ApiFehler) as f:
            self.api("POST", "/api/ausschreibungen/%s/vorbereiten" % aid)
        self.assertEqual(f.exception.status, 409)

    def test_mappe_mit_stundensatz(self):
        self.kern.einstellungen.setze("stundensatz_cent", 3850, "eigentuemer")
        aid = self.synthetisch("Glasreinigung Rathaus", 20)
        self.kern.aufgaben.anlegen("M", "ausschreibung_vorbereiten", "akquise", "eigentuemer",
                                   {"ausschreibung_id": aid})
        self.orch.alle_abarbeiten()
        z = self.kern.db.eins("SELECT unterlagen FROM ausschreibungen WHERE id=?", (aid,))
        with open(os.path.join(os.environ["AUTONOMOUS_DATEN"], "produkte", z["unterlagen"]), encoding="utf-8") as f:
            self.assertIn("38,50 €", f.read())

    def test_auswertung(self):
        self.synthetisch("Unterhaltsreinigung Kita", 5, status="interessant")
        self.synthetisch("Alte Reinigung", -5, extern_id="alt")
        aid = self.kern.aufgaben.anlegen("A", "auswertung", "akquise", "eigentuemer")
        self.orch.alle_abarbeiten()
        e = self.kern.aufgaben.hole(aid)["ergebnis"]
        self.assertEqual(e["nach_status"]["interessant"], 1)
        self.assertEqual([f["titel"] for f in e["naechste_fristen"]], ["Unterhaltsreinigung Kita"])


class TestSchnittstelle(RadarTest):
    def test_vertrag_und_abgelaufene_ausblenden(self):
        aktuell = self.synthetisch("Unterhaltsreinigung Schule", 12)
        alt = self.synthetisch("Abgelaufene Reinigung", -1, extern_id="alt")
        d = self.api("GET", "/api/ausschreibungen")
        self.assertEqual(set(d), {"ausschreibungen", "stufen", "letzte_suche", "einstellungen"})
        self.assertEqual(d["einstellungen"], {"internet_recherche_erlaubt": False, "auftragssuche_taeglich": False})
        self.assertEqual([x["id"] for x in d["ausschreibungen"]], [aktuell])
        x = d["ausschreibungen"][0]
        for feld in ("id", "quelle", "extern_id", "titel", "vergabestelle", "ort", "plz", "region", "frist",
                     "tage_bis_frist", "veroeffentlicht", "verfahren", "link", "cpv", "punkte", "begruendung",
                     "status", "notiz", "unterlagen_url", "gefunden"):
            self.assertIn(feld, x)
        self.assertEqual(x["tage_bis_frist"], 12)
        self.assertIsInstance(x["begruendung"], list)
        alle = self.api("GET", "/api/ausschreibungen", query={"alle": "1"})["ausschreibungen"]
        self.assertIn(alt, [x["id"] for x in alle])
        self.assertEqual(self.api("GET", "/api/ausschreibungen", query={"min_punkte": "90"})["ausschreibungen"], [])

    def test_status_aendern(self):
        aid = self.synthetisch("Unterhaltsreinigung Schule", 12)
        antwort = self.api("POST", "/api/ausschreibungen/%s/status" % aid, {"status": "gewonnen"})
        self.assertIn("keine Einnahme", antwort["hinweis"])
        for falsch in ({"status": "versendet"}, {}):
            with self.assertRaises(api.ApiFehler):
                self.api("POST", "/api/ausschreibungen/%s/status" % aid, falsch)
        with self.assertRaises(api.ApiFehler) as f:
            self.api("POST", "/api/ausschreibungen/gibtsnicht/status", {"status": "neu"})
        self.assertEqual(f.exception.status, 404)

    def test_suchen_legt_aufgabe_an_und_keine_doppelte(self):
        self.einschalten()
        a1 = self.api("POST", "/api/ausschreibungen/suchen")["aufgabe_id"]
        a2 = self.api("POST", "/api/ausschreibungen/suchen")
        self.assertEqual(a2["aufgabe_id"], a1)
        self.assertIn("läuft bereits", a2["hinweis"])


class TestZeitplanUndTagesplan(RadarTest):
    def test_taegliche_suche_hoechstens_alle_20_stunden(self):
        from autonomous import server
        self.assertIsNone(server.auftragssuche_anstossen(self.kern))  # ausgeschaltet
        self.einschalten()
        self.assertIsNone(server.auftragssuche_anstossen(self.kern))  # tägliche Suche noch aus
        self.kern.einstellungen.setze("auftragssuche_taeglich", True, "eigentuemer")
        aid = server.auftragssuche_anstossen(self.kern)
        self.assertIsNotNone(aid)
        self.assertEqual(self.kern.aufgaben.hole(aid)["ersteller"], "zeitplan")
        self.assertIsNone(server.auftragssuche_anstossen(self.kern))  # schon angelegt
        self.orch.alle_abarbeiten()
        self.assertIsNone(server.auftragssuche_anstossen(self.kern))  # Lauf liegt < 20 h zurück
        self.kern.db.ausfuehren("UPDATE aufgaben SET erstellt='2020-01-01T00:00:00+01:00'")
        self.kern.db.ausfuehren("UPDATE suchlaeufe SET zeit='2020-01-01T00:00:00+01:00'")
        self.assertIsNotNone(server.auftragssuche_anstossen(self.kern))

    def test_tagesplan_nennt_fristen(self):
        heute = datetime.date.today()
        with mock.patch("autonomous.auftraege.heute", return_value=heute):
            bald = self.synthetisch("Unterhaltsreinigung Grundschule", (heute - STICHTAG).days + 2,
                                    status="interessant", extern_id="bald")
            self.synthetisch("Spaeter", (heute - STICHTAG).days + 30, status="vorbereitet", extern_id="spaeter")
            aid = self.kern.aufgaben.anlegen("Plan", "tagesplan", "ceo", "eigentuemer")
            self.orch.alle_abarbeiten()
        plan = self.kern.aufgaben.hole(aid)["ergebnis"]["punkte"]
        fristen = [p for p in plan if p["art"] == "Ausschreibung" and p["bezug"]]
        self.assertEqual([p["bezug"] for p in fristen], [bald])
        self.assertEqual(fristen[0]["prio"], 1)
        self.assertIn("Frist in 2 Tag(en)", fristen[0]["text"])


class TestNetz(KernTest):
    def test_fremde_und_unsichere_adressen_ohne_abruf_abgelehnt(self):
        with mock.patch("urllib.request.OpenerDirector.open") as offen:
            for url in ("https://example.org/", "http://www.service.bund.de/", "file:///etc/passwd",
                        "https://www.service.bund.de.angreifer.example/x"):
                with self.assertRaises(netz.NetzFehler):
                    netz.abrufen(url)
            with self.assertRaises(netz.NetzFehler):
                netz.abrufen("https://www.service.bund.de/", methode="DELETE")
            offen.assert_not_called()

    def test_weiterleitung_auf_fremden_host_abgebrochen(self):
        h = netz._PruefendeWeiterleitung()
        anfrage = urllib.request.Request("https://www.evergabe.nrw.de/")
        with self.assertRaises(netz.NetzFehler):
            h.redirect_request(anfrage, None, 302, "Found", {}, "https://angreifer.example/")
        with self.assertRaises(netz.NetzFehler):
            h.redirect_request(anfrage, None, 302, "Found", {}, "http://www.evergabe.nrw.de/")
        neu = h.redirect_request(anfrage, None, 302, "Found", {},
                                 "https://www.evergabe.nrw.de/VMPCenter/company/welcome.do")
        self.assertEqual(neu.full_url, "https://www.evergabe.nrw.de/VMPCenter/company/welcome.do")

    def test_hoeflicher_abstand_je_host(self):
        uhr = [100.0]
        schlaf = []
        with mock.patch.object(netz.time, "monotonic", side_effect=lambda: uhr[0]), \
                mock.patch.object(netz.time, "sleep", side_effect=schlaf.append), \
                mock.patch.dict(netz._letzter_abruf, {}, clear=True):
            netz._warten("www.service.bund.de")
            netz._warten("www.service.bund.de")
            netz._warten("api.ted.europa.eu")
        self.assertEqual(schlaf, [netz.ABSTAND_SEKUNDEN])

    def test_kodierung(self):
        self.assertEqual(netz._kodierung("text/html;charset=ISO-8859-1", b""), "cp1252")
        self.assertEqual(netz._kodierung("", b'<meta charset="utf-8">'), "utf-8")
        self.assertEqual(netz._kodierung("text/html; charset=gibtsnicht", b""), "utf-8")
        self.assertIn("AUTONOMOUS", netz.KENNUNG)
        self.assertNotRegex(netz.KENNUNG, r"@|santana")
