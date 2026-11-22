# -*- coding: utf-8 -*-
"""Dubletten-Erkennung: dieselbe Ausschreibung aus zwei Quellen (z. B. TED und service.bund.de).

Grundsatz: KONSERVATIV – lieber eine Dublette übersehen als zwei verschiedene Ausschreibungen zusammenwerfen.
Getestet mit echten Einträgen eines Live-Suchlaufs (unverändert übernommen), den gespeicherten echten
Testdaten (dort darf keine falsche Gruppe entstehen) und konstruierten Grenzfällen."""

import datetime
import json
import os

from autonomous import api_auftraege  # noqa: F401  (Routen registrieren)
from autonomous.auftraege import dubletten
from autonomous.auftraege import quellen as q
from autonomous.tests.hilfe import KernTest

DATEN = os.path.join(os.path.dirname(os.path.abspath(__file__)), "daten")

# Echte Einträge aus einem Live-Suchlauf am 22.11.2026 (TED-API und service.bund.de), unverändert übernommen.
ECHT = {
    'emscher': [
        {'quelle': 'service_bund', 'extern_id': 'asp/2026/10/198758', 'titel': 'Glas- und Unterhaltsreinigung', 'vergabestelle': 'Emschergenossenschaft', 'ort': 'Essen', 'plz': '45128', 'region': 'PLZ-Bereich 45', 'frist': '2026-12-01 10:10', 'link': 'https://www.service.bund.de/IMPORTE/Ausschreibungen/asp/2026/10/198758.html'},
        {'quelle': 'ted', 'extern_id': '698163-2026', 'titel': 'Deutschland – Wohnungs-, Gebäude- und Fensterreinigung – Glas- und Unterhaltsreinigung', 'vergabestelle': 'Emschergenossenschaft (Essen)', 'ort': None, 'plz': None, 'region': 'NRW: Regierungsbezirk Düsseldorf (DEA13)', 'frist': '2026-12-01', 'link': 'https://ted.europa.eu/de/notice/-/detail/698163-2026'},
        {'quelle': 'ted', 'extern_id': '714583-2026', 'titel': 'Deutschland – Wohnungs-, Gebäude- und Fensterreinigung – Glas- und Unterhaltsreinigung', 'vergabestelle': 'Emschergenossenschaft (Essen)', 'ort': None, 'plz': None, 'region': 'NRW: Regierungsbezirk Düsseldorf (DEA13)', 'frist': '2026-12-01', 'link': 'https://ted.europa.eu/de/notice/-/detail/714583-2026'},
    ],
    'warendorf': [
        {'quelle': 'service_bund', 'extern_id': 'eVergabe/901861', 'titel': 'Vertrag über die Unterhaltsreinigung in der Liegenschaft der Bundeswehr in Warendorf und Milte', 'vergabestelle': 'Bundeswehrverwaltung', 'ort': 'Warendorf (Warendorf)', 'plz': '48231', 'region': 'PLZ-Bereich 48', 'frist': '2026-11-26 13:00', 'link': 'https://www.service.bund.de/IMPORTE/Ausschreibungen/eVergabe/901861.html'},
        {'quelle': 'ted', 'extern_id': '744433-2026', 'titel': 'Deutschland – Gebäudereinigung – Vertrag über die Unterhaltsreinigung in der Liegenschaft der Bundeswehr in Warendorf und Milte', 'vergabestelle': 'Bundeswehr-Dienstleistungszentrum Münster (Münster)', 'ort': None, 'plz': None, 'region': 'NRW: Regierungsbezirk Münster (DEA38)', 'frist': '2026-11-26', 'link': 'https://ted.europa.eu/de/notice/-/detail/744433-2026'},
        {'quelle': 'ted', 'extern_id': '751455-2026', 'titel': 'Deutschland – Gebäudereinigung – Vertrag über die Unterhaltsreinigung in der Liegenschaft der Bundeswehr in Warendorf und Milte', 'vergabestelle': 'Bundeswehr-Dienstleistungszentrum Münster (Münster)', 'ort': None, 'plz': None, 'region': 'NRW: Regierungsbezirk Münster (DEA38)', 'frist': '2026-11-26', 'link': 'https://ted.europa.eu/de/notice/-/detail/751455-2026'},
    ],
    'unna': [
        {'quelle': 'service_bund', 'extern_id': 'eVergabe/902762', 'titel': '6003141213-Unterhaltsreinigung Glückauf-Kaserne Unna', 'vergabestelle': 'Bundeswehrverwaltung', 'ort': 'Unna (Unna)', 'plz': '59425', 'region': 'PLZ-Bereich 59', 'frist': '2026-11-30 13:00', 'link': 'https://www.service.bund.de/IMPORTE/Ausschreibungen/eVergabe/902762.html'},
        {'quelle': 'ted', 'extern_id': '750531-2026', 'titel': 'Deutschland – Gebäudereinigung – 6003141213-Unterhaltsreinigung Glückauf-Kaserne Unna', 'vergabestelle': 'Bundeswehr-Dienstleistungszentrum Münster (Münster)', 'ort': None, 'plz': None, 'region': 'NRW: Regierungsbezirk Arnsberg (DEA5C)', 'frist': '2026-11-30', 'link': 'https://ted.europa.eu/de/notice/-/detail/750531-2026'},
    ],
    'bzst': [
        {'quelle': 'service_bund', 'extern_id': 'eVergabe/901588', 'titel': 'Offenes Verfahren (EU-weit) zur Vergabe von Gebäudereinigungsleistungen (Unterhaltsreinigung) für das Bundeszentralamt für Steuern in Bonn (Vergabenummer VOEK 320-26)', 'vergabestelle': 'Bundesanstalt für Immobilienaufgaben Verdingungsstelle', 'ort': 'Bonn (Bonn, Kreisfreie Stadt)', 'plz': '53225', 'region': 'PLZ-Bereich 53', 'frist': '2026-12-15 09:00', 'link': 'https://www.service.bund.de/IMPORTE/Ausschreibungen/eVergabe/901588.html'},
        {'quelle': 'ted', 'extern_id': '752562-2026', 'titel': 'Deutschland – Gebäudereinigung – Offenes Verfahren (EU-weit) zur Vergabe von Gebäudereinigungsleistungen (Unterhaltsreinigung) für das Bundeszentralamt für Steuern in Bonn (Vergabenummer VOEK 320-26)', 'vergabestelle': 'Bundesanstalt für Immobilienaufgaben (Bonn)', 'ort': None, 'plz': None, 'region': 'NRW: Regierungsbezirk Köln (DEA22)', 'frist': '2026-12-15', 'link': 'https://ted.europa.eu/de/notice/-/detail/752562-2026'},
    ],
    'koeln_paket34': [
        {'quelle': 'service_bund', 'extern_id': 'ai-ag-prod/2026/10/54321-Tender-1a11a9c7c2d-7214fab3dea725d0', 'titel': 'Az 25667 Paket 34 Gebäudereinigung in 21 Objekten', 'vergabestelle': 'Stadt Köln - Amt für Recht, Vergabe und Versicherungen', 'ort': 'Köln', 'plz': None, 'region': None, 'frist': '2026-11-30 14:00', 'link': 'https://www.service.bund.de/IMPORTE/Ausschreibungen/ai-ag-prod/2026/10/54321-Tender-1a11a9c7c2d-7214fab3dea725d0.html'},
        {'quelle': 'ted', 'extern_id': '753620-2026', 'titel': 'Deutschland – Gebäudereinigung – Az 25667 Paket 34 Gebäudereinigung in 21 Objekten', 'vergabestelle': 'Amt für Recht, Vergabe und Versicherungen (Köln)', 'ort': None, 'plz': None, 'region': 'NRW: Regierungsbezirk Köln (DEA23)', 'frist': '2026-11-30', 'link': 'https://ted.europa.eu/de/notice/-/detail/753620-2026'},
    ],
    'blb': [
        {'quelle': 'service_bund', 'extern_id': 'vmp-blb/2026/10/71862', 'titel': 'BLB /Z /NL Düsseldorf/Infrastrukturelle Gebäudedienstleistungen/Unterhaltsreinigung_100-26-00159', 'vergabestelle': 'Bau- und Liegenschaftsbetrieb NRW Zentrale', 'ort': 'Düsseldorf (Großraum)', 'plz': '40470', 'region': 'PLZ-Bereich 40', 'frist': '2026-12-15 11:00', 'link': 'https://www.service.bund.de/IMPORTE/Ausschreibungen/vmp-blb/2026/10/71862.html'},
        {'quelle': 'ted', 'extern_id': '758334-2026', 'titel': 'Deutschland – Gebäudereinigung – BLB /Z /NL Düsseldorf/Infrastrukturelle Gebäudedienstleistungen/Unterhaltsreinigung_100-26-00159', 'vergabestelle': 'Bau- und Liegenschaftsbetrieb NRW Zentrale (Düsseldorf)', 'ort': None, 'plz': None, 'region': 'NRW: Regierungsbezirk Düsseldorf (DEA11); Regierungsbezirk Düsseldorf (DEA1C); Regierungsbezirk Düsseldorf (DEA18); Regi', 'frist': '2026-12-15', 'link': 'https://ted.europa.eu/de/notice/-/detail/758334-2026'},
    ],
    'lohmar': [
        {'quelle': 'service_bund', 'extern_id': 'vmp-nrw/2026/11/229785', 'titel': 'Gebäudereinigung - ZUE Lohmar', 'vergabestelle': 'Bezirksregierung Köln', 'ort': 'Lohmar', 'plz': '53797', 'region': 'PLZ-Bereich 53', 'frist': '2026-12-08 12:00', 'link': 'https://www.service.bund.de/IMPORTE/Ausschreibungen/vmp-nrw/2026/11/229785.html'},
        {'quelle': 'ted', 'extern_id': '764604-2026', 'titel': 'Deutschland – Reinigung von Unterkünften – Gebäudereinigung - ZUE Lohmar', 'vergabestelle': 'Bezirksregierung Köln (Köln)', 'ort': None, 'plz': None, 'region': 'NRW: Regierungsbezirk Köln (DEA2C)', 'frist': '2026-12-08', 'link': 'https://ted.europa.eu/de/notice/-/detail/764604-2026'},
    ],
    'bruehl': [
        {'quelle': 'service_bund', 'extern_id': 'vmp-nrw/2026/11/230002', 'titel': 'Durchführung der Unterhaltsreinigung', 'vergabestelle': 'UNESCO-Welterbestätte Schlösser Augustusburg und Falkenlust in Brühl', 'ort': 'Brühl', 'plz': '50321', 'region': 'PLZ-Bereich 50', 'frist': '2026-12-11 10:00', 'link': 'https://www.service.bund.de/IMPORTE/Ausschreibungen/vmp-nrw/2026/11/230002.html'},
        {'quelle': 'ted', 'extern_id': '784860-2026', 'titel': 'Deutschland – Gebäudereinigung – Durchführung der Unterhaltsreinigung', 'vergabestelle': 'UNESCO-Welterbestätte Schlösser Augustusburg und Falkenlust in Brühl (Brühl)', 'ort': None, 'plz': None, 'region': 'NRW: Regierungsbezirk Köln (DEA27)', 'frist': '2026-12-11', 'link': 'https://ted.europa.eu/de/notice/-/detail/784860-2026'},
    ],
    'lwk': [
        {'quelle': 'service_bund', 'extern_id': 'vmp-nrw/2026/11/230093', 'titel': 'Unterhaltsreinigung für die Landwirtschaftskammer Nordrhein-Westfalen für das Fachzentrum Köln - Auweiler', 'vergabestelle': 'Landwirtschaftskammer Nordrhein-Westfalen', 'ort': 'Köln', 'plz': '50765', 'region': 'PLZ-Bereich 50', 'frist': '2026-12-15 10:00', 'link': 'https://www.service.bund.de/IMPORTE/Ausschreibungen/vmp-nrw/2026/11/230093.html'},
        {'quelle': 'ted', 'extern_id': '790269-2026', 'titel': 'Deutschland – Gebäudereinigung – Unterhaltsreinigung für die Landwirtschaftskammer Nordrhein-Westfalen für das Fachzentrum Köln - Auweiler', 'vergabestelle': 'Landwirtschaftskammer Nordrhein-Westfalen (Münster)', 'ort': None, 'plz': None, 'region': 'NRW: Regierungsbezirk Köln (DEA23)', 'frist': '2026-12-15', 'link': 'https://ted.europa.eu/de/notice/-/detail/790269-2026'},
    ],
    'falsch_bima_kiel': [
        {'quelle': 'service_bund', 'extern_id': 'eVergabe/901911', 'titel': 'Offenes Verfahren (EU-weit) zur Vergabe von Gebäudereinigungsleistungen (Unterhaltsreinigung) für eine Dienstliegenschaft in Kiel - VOEK 430-26', 'vergabestelle': 'Bundesanstalt für Immobilienaufgaben Verdingungsstelle', 'ort': 'Kiel (Kiel, Kreisfreie Stadt)', 'plz': '24116', 'region': 'PLZ-Bereich 24', 'frist': '2026-12-21 09:00', 'link': 'https://www.service.bund.de/IMPORTE/Ausschreibungen/eVergabe/901911.html'},
        {'quelle': 'ted', 'extern_id': '741901-2026', 'titel': 'Deutschland – Gebäudereinigung – Offenes Verfahren (EU-weit) zur Vergabe von Gebäudereinigungsleistungen (Unterhaltsreinigungsleistungen) für diverse Liegenschaften in Nordrhein-Westfalen, Bundesanstalt für Immobilienaufgaben, Direktion Dortmund VOEK 213-26', 'vergabestelle': 'Bundesanstalt für Immobilienaufgaben (Bonn)', 'ort': None, 'plz': None, 'region': 'NRW: Regierungsbezirk Arnsberg (DEA51); Regierungsbezirk Münster (DEA32); Regierungsbezirk Arnsberg (DEA5C); Regierungsb', 'frist': '2026-12-21', 'link': 'https://ted.europa.eu/de/notice/-/detail/741901-2026'},
        {'quelle': 'ted', 'extern_id': '756514-2026', 'titel': 'Deutschland – Gebäudereinigung – Offenes Verfahren (EU-weit) zur Vergabe von Gebäudereinigungsleistungen (Unterhalts- und Glasreinigungsleistungen) für diverse Liegenschaften in Nordrhein-Westfalen, VOEK 208-26', 'vergabestelle': 'Bundesanstalt für Immobilienaufgaben (Bonn)', 'ort': None, 'plz': None, 'region': 'NRW: Regierungsbezirk Detmold (DEA47); Regierungsbezirk Arnsberg (DEA5B); Regierungsbezirk Detmold (DEA41)', 'frist': '2026-12-21', 'link': 'https://ted.europa.eu/de/notice/-/detail/756514-2026'},
    ],
    'falsch_sbk_unikoeln': [
        {'quelle': 'service_bund', 'extern_id': 'vmp-nrw/2026/11/230102', 'titel': 'Universität zu Köln - Wartung, Inspektion, Prüfbegleitung und Reinigung von Aufzugsanlagen im Bereich Chemie - Physik', 'vergabestelle': 'Universität zu Köln, Abteilung 64 - Einkauf', 'ort': 'Köln', 'plz': '50923', 'region': 'PLZ-Bereich 50', 'frist': '2026-12-07 14:57', 'link': 'https://www.service.bund.de/IMPORTE/Ausschreibungen/vmp-nrw/2026/11/230102.html'},
        {'quelle': 'ted', 'extern_id': '771022-2026', 'titel': 'Deutschland – Gebäudereinigung – Vergabe Unterhaltsreinigung Sozial-Betriebe Köln gGmbH', 'vergabestelle': 'SBK Sozial-Betriebe Köln gemeinnützige GmbH (Köln)', 'ort': None, 'plz': None, 'region': 'NRW: Regierungsbezirk Köln (DEA23)', 'frist': '2026-12-07', 'link': 'https://ted.europa.eu/de/notice/-/detail/771022-2026'},
    ],
    'falsch_rhede_ilvesheim': [
        {'quelle': 'service_bund', 'extern_id': 'ai-ag-prod/2026/10/54321-Tender-1a12064c5c8-3b634fc4c6ac269', 'titel': 'Reinigungsdienstleistungen für die Gemeinde Ilvesheim', 'vergabestelle': 'Gemeinde Ilvesheim', 'ort': 'k.A.', 'plz': None, 'region': None, 'frist': '2026-11-24 10:00', 'link': 'https://www.service.bund.de/IMPORTE/Ausschreibungen/ai-ag-prod/2026/10/54321-Tender-1a12064c5c8-3b634fc4c6ac269.html'},
        {'quelle': 'ted', 'extern_id': '739418-2026', 'titel': 'Deutschland – Reinigungsdienste – Gebäude und Turnhallen der Stadt Rhede: Reinigungsdienstleistungen', 'vergabestelle': 'Stadt Bocholt (Bocholt)', 'ort': None, 'plz': None, 'region': 'NRW: Regierungsbezirk Münster (DEA34)', 'frist': '2026-11-24', 'link': 'https://ted.europa.eu/de/notice/-/detail/739418-2026'},
    ],
}


ECHTE_GRUPPEN = ("emscher", "warendorf", "unna", "bzst", "koeln_paket34", "blb", "lohmar", "bruehl", "lwk")
ECHTE_FALSCHE = ("falsch_bima_kiel", "falsch_sbk_unikoeln", "falsch_rhede_ilvesheim")


def mit_id(eintraege, status="neu", punkte=80):
    """IDs wie im echten Betrieb: einfache Kennungen (in Adress-Pfaden erlaubt)."""
    return [dict(e, id="dub_%s_%s" % (e["quelle"], "".join(c for c in e["extern_id"] if c.isalnum())[-16:]),
                 status=status, punkte=punkte) for e in eintraege]


class TestRegelAufEchtenDaten(KernTest):
    def test_echte_dubletten_werden_erkannt(self):
        for name in ECHTE_GRUPPEN:
            with self.subTest(name):
                gruppen = dubletten.gruppen(mit_id(ECHT[name]))
                self.assertEqual(len(gruppen), 1, name)
                self.assertEqual(len(gruppen[0]), len(ECHT[name]), name)

    def test_echte_falsche_kandidaten_bleiben_getrennt(self):
        for name in ECHTE_FALSCHE:
            with self.subTest(name):
                self.assertEqual(dubletten.gruppen(mit_id(ECHT[name])), [], name)

    def test_alle_echten_eintraege_zusammen_genau_die_neun_gruppen(self):
        alle = mit_id([e for liste in ECHT.values() for e in liste])
        gruppen = dubletten.gruppen(alle)
        self.assertEqual(len(gruppen), len(ECHTE_GRUPPEN))
        self.assertEqual(sum(len(g) for g in gruppen), sum(len(ECHT[n]) for n in ECHTE_GRUPPEN))

    def test_gespeicherte_echte_testdaten_ergeben_keine_falsche_gruppe(self):
        def lesen(name):
            with open(os.path.join(DATEN, name), "rb") as f:
                return f.read()
        ted, _ = q.ted_parsen(lesen("ted_suche.json"))
        bund = q.bund_parsen(lesen("service_bund_reinigung.rss"))
        bund = bund[0] if isinstance(bund, tuple) else bund
        ev = q.evergabe_parsen(lesen("evergabe_nrw_start.html").decode("cp1252"))
        ev = ev[0] if isinstance(ev, tuple) else ev
        alle = mit_id(ted + bund + ev)
        self.assertGreater(len(alle), 100)
        self.assertEqual(dubletten.gruppen(alle), [])


class TestHaupteintrag(KernTest):
    def test_service_bund_vor_ted_und_felder(self):
        liste = dubletten.anreichern(mit_id(ECHT["lohmar"]))
        haupt = [e for e in liste if e["vermutlich_gleich_wie"] is None]
        neben = [e for e in liste if e["vermutlich_gleich_wie"] is not None]
        self.assertEqual(len(haupt), 1)
        self.assertEqual(haupt[0]["quelle"], "service_bund")
        self.assertEqual(neben[0]["vermutlich_gleich_wie"], haupt[0]["id"])
        bei = haupt[0]["auch_gefunden_bei"]
        self.assertEqual([(b["quelle"], b["id"]) for b in bei], [("ted", neben[0]["id"])])
        self.assertTrue(bei[0]["link"].startswith("https://ted.europa.eu/"))
        self.assertEqual(bei[0]["quelle_name"], "TED (EU-Amtsblatt)")

    def test_eintrag_mit_status_des_eigentuemers_wird_haupteintrag(self):
        eintraege = mit_id(ECHT["lohmar"])
        ted = [e for e in eintraege if e["quelle"] == "ted"][0]
        ted["status"] = "interessant"
        liste = dubletten.anreichern(eintraege)
        haupt = [e for e in liste if e["vermutlich_gleich_wie"] is None][0]
        self.assertEqual(haupt["quelle"], "ted")
        self.assertEqual(haupt["status"], "interessant")  # Status bleibt, wie er ist


class TestGrenzfaelle(KernTest):
    def basis(self, **aenderung):
        e = {"quelle": "service_bund", "extern_id": "x1", "titel": "Unterhaltsreinigung Grundschule Am Park",
             "vergabestelle": "Stadt Musterstadt", "ort": "Musterstadt", "plz": "51373", "region": None,
             "frist": "2026-12-10 10:00", "link": "https://www.service.bund.de/x1.html"}
        e.update(aenderung)
        return e

    def ted(self, **aenderung):
        e = {"quelle": "ted", "extern_id": "t1", "titel": "Deutschland – Gebäudereinigung – Unterhaltsreinigung Grundschule Am Park",
             "vergabestelle": "Stadt Musterstadt (Musterstadt)", "ort": None, "plz": None, "region": "DEA24",
             "frist": "2026-12-10", "link": "https://ted.europa.eu/de/notice/-/detail/t1"}
        e.update(aenderung)
        return e

    def test_kontrolle_gleiche_ausschreibung(self):
        self.assertTrue(dubletten.ist_dublette(self.ted(), self.basis()))

    def test_gleicher_ort_andere_frist_keine_dublette(self):
        self.assertFalse(dubletten.ist_dublette(self.ted(frist="2026-12-11"), self.basis()))

    def test_gleiche_frist_anderer_ort_keine_dublette(self):
        # gleicher allgemeiner Titel, gleiche Art Vergabestelle – aber anderer Ort
        a = self.ted(titel="Deutschland – Gebäudereinigung – Gebäudereinigung", vergabestelle="Bundesanstalt für Immobilienaufgaben (Bonn)")
        b = self.basis(titel="Gebäudereinigung", vergabestelle="Bundesanstalt für Immobilienaufgaben Verdingungsstelle", ort="Kiel")
        self.assertFalse(dubletten.ist_dublette(a, b))

    def test_titel_nur_allerweltswoerter_keine_dublette(self):
        a = self.ted(titel="Deutschland – Gebäudereinigung – Unterhaltsreinigung und Glasreinigung", vergabestelle="Stadt Aachen (Aachen)")
        b = self.basis(titel="Unterhaltsreinigung und Glasreinigung", vergabestelle="Gemeinde Roetgen", ort="Roetgen")
        self.assertFalse(dubletten.ist_dublette(a, b))

    def test_gleiche_quelle_wird_nie_zusammengelegt(self):
        self.assertFalse(dubletten.ist_dublette(self.basis(), self.basis(extern_id="x2")))


class TestSchnittstelle(KernTest):
    def einfuegen(self, eintraege, verschiebung=10):
        frist = (datetime.date.today() + datetime.timedelta(days=verschiebung)).isoformat()
        jetzt = "2026-11-22T10:00:00+01:00"
        for e in eintraege:
            f = frist + (e["frist"][10:] if e.get("frist") else "")
            self.kern.db.ausfuehren(
                "INSERT INTO ausschreibungen (id, quelle, extern_id, titel, vergabestelle, ort, plz, region, frist, link,"
                " punkte, begruendung, status, gefunden, aktualisiert) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (e["id"], e["quelle"], e["extern_id"], e["titel"], e["vergabestelle"], e["ort"], e["plz"], e["region"],
                 f, e["link"], e["punkte"], json.dumps([]), e["status"], jetzt, jetzt))

    def test_dubletten_standardmaessig_ausgeblendet_und_abrufbar(self):
        eintraege = mit_id(ECHT["lohmar"]) + mit_id(ECHT["falsch_rhede_ilvesheim"])
        self.einfuegen(eintraege)
        standard = self.api("GET", "/api/ausschreibungen")["ausschreibungen"]
        self.assertEqual(len(standard), 3)  # Lohmar einmal + Rhede + Ilvesheim
        lohmar = [a for a in standard if "Lohmar" in a["titel"]][0]
        self.assertEqual(lohmar["quelle"], "service_bund")
        self.assertEqual([b["quelle"] for b in lohmar["auch_gefunden_bei"]], ["ted"])
        self.assertIsNone(lohmar["vermutlich_gleich_wie"])
        alle = self.api("GET", "/api/ausschreibungen", query={"dubletten": "1"})["ausschreibungen"]
        self.assertEqual(len(alle), 4)
        ted = [a for a in alle if a["quelle"] == "ted" and "Lohmar" in a["titel"]][0]
        self.assertEqual(ted["vermutlich_gleich_wie"], lohmar["id"])
        self.assertEqual(ted["status"], "neu")  # Status bleibt unangetastet

    def test_dublette_steht_direkt_nach_ihrem_haupteintrag(self):
        # Die TED-Fassung hat mehr Punkte als der Haupteintrag (service.bund.de) – sie soll trotzdem nicht
        # irgendwo weiter oben stehen, sondern direkt unter ihrem Haupteintrag.
        lohmar = mit_id(ECHT["lohmar"])
        andere = mit_id(ECHT["falsch_rhede_ilvesheim"])
        for e, punkte in ((lohmar[0], 80), (lohmar[1], 95), (andere[0], 85), (andere[1], 88)):
            e["punkte"] = punkte
        self.einfuegen(lohmar + andere)
        alle = [a["id"] for a in self.api("GET", "/api/ausschreibungen", query={"dubletten": "1"})["ausschreibungen"]]
        self.assertEqual(alle, [andere[1]["id"], andere[0]["id"], lohmar[0]["id"], lohmar[1]["id"]])
        standard = [a["id"] for a in self.api("GET", "/api/ausschreibungen")["ausschreibungen"]]
        self.assertEqual(standard, [andere[1]["id"], andere[0]["id"], lohmar[0]["id"]])

    def test_bearbeitete_dublette_bleibt_sichtbar(self):
        eintraege = mit_id(ECHT["warendorf"])
        self.einfuegen(eintraege)
        ted_id = [e for e in eintraege if e["quelle"] == "ted"][0]["id"]
        self.api("POST", "/api/ausschreibungen/%s/status" % ted_id, {"status": "abgelehnt"})
        sichtbar = [a["id"] for a in self.api("GET", "/api/ausschreibungen")["ausschreibungen"]]
        self.assertIn(ted_id, sichtbar)

    def test_dublette_bleibt_sichtbar_wenn_haupteintrag_herausgefiltert(self):
        eintraege = mit_id(ECHT["lohmar"])
        for e in eintraege:
            e["punkte"] = 40 if e["quelle"] == "service_bund" else 90
        self.einfuegen(eintraege)
        gefiltert = self.api("GET", "/api/ausschreibungen", query={"min_punkte": "60"})["ausschreibungen"]
        self.assertEqual([a["quelle"] for a in gefiltert], ["ted"])
