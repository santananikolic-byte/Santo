#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Tests für Konfiguration, Speicher, Textsuche und Gedächtnis.

Aufruf::

    python3 -m unittest tests.test_speicher -v
"""

import json
import os
import shutil
import sqlite3
import sys
import tempfile
import threading
import unittest

WURZEL = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, WURZEL)

from jarvis_core import gedaechtnis, konfig, textsuche, zeit  # noqa: E402
from jarvis_core.speicher import Speicher  # noqa: E402


class Grundlage(unittest.TestCase):
    def setUp(self):
        self.ordner = tempfile.mkdtemp(prefix="jarvis_sp_")
        self._alt = {k: os.environ.get(k) for k in ("JARVIS_DATEN", "JARVIS_PORT", "JARVIS_MODELL", "JARVIS_WERKSTATT",
                                                    "JARVIS_LOGSTUFE")}
        for k in self._alt:
            os.environ.pop(k, None)
        os.environ["JARVIS_DATEN"] = self.ordner
        self.konfig = konfig.laden()
        self.sp = Speicher(self.konfig.db_datei)

    def tearDown(self):
        self.sp.schliessen()
        for k, v in self._alt.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        shutil.rmtree(self.ordner, ignore_errors=True)


class KonfigTest(Grundlage):
    def test_standard_und_datei(self):
        self.assertTrue(os.path.exists(self.konfig.datei))
        self.assertEqual(self.konfig.bereiche, ["geschaeft", "privat"])
        self.assertEqual(self.konfig.modell_fuer("chat"), "opus")
        self.assertEqual(self.konfig.modell_fuer("pruefung"), "sonnet")
        self.assertFalse(self.konfig.lan)
        self.assertEqual(self.konfig.bind_adresse, "127.0.0.1")

    def test_lan_oeffnet_nur_mit_schalter(self):
        self.konfig.aktualisieren({"lan": True})
        self.assertEqual(self.konfig.bind_adresse, "0.0.0.0")
        self.assertEqual(konfig.laden().bind_adresse, "0.0.0.0")  # bleibt gespeichert
        with self.assertRaises(konfig.KonfigFehler):
            self.konfig.aktualisieren({"host": "0.0.0.0"})  # die Adresse selbst bleibt lokal

    def test_modelle_pruefen_und_env(self):
        with self.assertRaises(konfig.KonfigFehler):
            self.konfig.aktualisieren({"modelle": {"chat": "böse; rm -rf"}})
        os.environ["JARVIS_MODELL"] = "sonnet"
        k = konfig.laden()
        self.assertTrue(all(k.modell_fuer(a) == "sonnet" for a in konfig.MODELL_ARTEN))
        os.environ["JARVIS_MODELL"] = ""
        self.assertEqual(konfig.laden().modell_fuer("chat"), "")

    def test_altform_modell_wird_uebernommen(self):
        with open(self.konfig.datei, "w") as f:
            json.dump({"modell": "sonnet"}, f)
        k = konfig.laden()
        self.assertEqual(k.modell_fuer("chat"), "sonnet")
        self.assertEqual(k.modell_fuer("pruefung"), "sonnet")

    def test_bereiche(self):
        for schlecht in ([], ["allgemein"], ["alle"], ["x"], ["a b"], "geschaeft"):
            with self.subTest(schlecht=schlecht), self.assertRaises(konfig.KonfigFehler):
                self.konfig.aktualisieren({"bereiche": schlecht})
        self.konfig.aktualisieren({"bereiche": ["Firma_A", "firma_b", "privat", "PRIVAT"]})
        self.assertEqual(self.konfig.bereiche, ["firma_a", "firma_b", "privat"])  # klein geschrieben, ohne Doppelte
        self.assertIn("technik", self.konfig.alle_bereiche())

    def test_zusaetzliche_ordner_sind_streng(self):
        heim = os.path.expanduser("~")
        schlecht = [
            {"x": {"pfad": "/"}},
            {"x": {"pfad": heim}},
            {"x": {"pfad": os.path.join(heim, "Library", "Mail")}},
            {"x": {"pfad": os.path.join(heim, ".ssh")}},
            {"x": {"pfad": self.ordner}},
            {"x": {"pfad": os.path.dirname(self.ordner)}},  # enthält den Datenordner
            {"werkstatt": {"pfad": os.path.join(heim, "Dokumente")}},
            {"X": {"pfad": os.path.join(heim, "Dokumente")}},
            {"x": {}},
        ]
        for eintrag in schlecht:
            with self.subTest(eintrag=eintrag), self.assertRaises(konfig.KonfigFehler):
                self.konfig.aktualisieren({"ordner": eintrag})
        self.konfig.aktualisieren({"ordner": {"angebote": {"pfad": os.path.join(heim, "Dokumente", "Angebote")}}})
        pfad, schreiben = self.konfig.wurzeln()["angebote"]
        self.assertTrue(pfad.endswith("Angebote"))
        self.assertFalse(schreiben)  # standardmäßig nur lesend
        self.assertTrue(self.konfig.wurzeln()["werkstatt"][1])

    def test_grenzen(self):
        for name, wert in (("port", 80), ("max_schritte", 0), ("max_versuche", 9), ("skript_timeout", 1),
                           ("tempo", "schnell"), ("freigabe_minuten", 0)):
            with self.subTest(name=name), self.assertRaises(konfig.KonfigFehler):
                self.konfig.aktualisieren({name: wert})
        self.assertEqual(self.konfig.port, 8770)  # Fehlschlag ändert nichts

    def test_domains_und_werkzeugsperren(self):
        with self.assertRaises(konfig.KonfigFehler):
            self.konfig.aktualisieren({"api_domains": ["localhost"]})
        self.konfig.aktualisieren({"api_domains": ["Api.Example.com"], "deaktivierte_werkzeuge": ["skript_ausfuehren", "x y"]})
        self.assertEqual(self.konfig.api_domains, ["api.example.com"])
        self.assertEqual(self.konfig.deaktivierte_werkzeuge, ["skript_ausfuehren"])


class TextsucheTest(unittest.TestCase):
    def test_duplikate(self):
        self.assertTrue(textsuche.ist_duplikat("Sitz in Leverkusen bei Köln", "sitz in leverkusen bei köln!"))
        self.assertTrue(textsuche.ist_duplikat("Wir arbeiten in Leverkusen und Köln", "Wir arbeiten in Köln und Leverkusen"))
        self.assertFalse(textsuche.ist_duplikat("Sitz in Leverkusen", "Preise nach Leistungswerten kalkulieren"))

    def test_relevanz(self):
        frage = set(textsuche.woerter("Wie kalkuliere ich den Preis für die Treppenhausreinigung?"))
        gut = textsuche.relevanz(frage, "Preise: feste Kalkulation mit Stundensatz und Leistungswerten")
        schlecht = textsuche.relevanz(frage, "Führerschein machen")
        self.assertGreater(gut, schlecht)
        self.assertEqual(schlecht, 0.0)
        self.assertEqual(textsuche.relevanz(set(), "irgendwas"), 0.0)


class SpeicherTest(Grundlage):
    def test_fakten_duplikate_und_bereiche(self):
        a, neu = self.sp.fakt_hinzufuegen("Sitz in Leverkusen bei Köln", bereich="geschaeft")
        self.assertTrue(neu)
        b, neu = self.sp.fakt_hinzufuegen("sitz in Leverkusen bei Köln.", bereich="geschaeft")
        self.assertFalse(neu)
        self.assertEqual(a, b)
        _, neu = self.sp.fakt_hinzufuegen("Sitz in Leverkusen bei Köln", bereich="privat")  # anderer Bereich
        self.assertTrue(neu)
        self.assertEqual(len(self.sp.fakten()), 2)
        with self.assertRaises(ValueError):
            self.sp.fakt_hinzufuegen("   ")

    def test_verworfenes_bleibt_verworfen_bis_der_nutzer_es_will(self):
        fid, _ = self.sp.fakt_hinzufuegen("Nutzt Jarvis für Firmenprüfungen", status="vorschlag", quelle="jarvis")
        self.sp.fakt_setzen(fid, status="verworfen")
        _, neu = self.sp.fakt_hinzufuegen("Nutzt Jarvis für Firmenprüfungen", status="vorschlag", quelle="jarvis")
        self.assertFalse(neu)  # Jarvis fragt nicht ständig dasselbe
        self.assertEqual(self.sp.fakten(status="vorschlag"), [])
        again, neu = self.sp.fakt_hinzufuegen("Nutzt Jarvis für Firmenprüfungen", status="bestaetigt")
        self.assertTrue(neu)
        self.assertEqual(again, fid)
        self.assertEqual(self.sp.fakt(fid)["status"], "bestaetigt")

    def test_bearbeiten_markiert_als_nutzereintrag(self):
        fid, _ = self.sp.fakt_hinzufuegen("alter Text", quelle="BRAIN.md")
        self.sp.fakt_setzen(fid, text="neuer Text")
        self.assertEqual(self.sp.fakt(fid)["quelle"], "nutzer")
        self.assertEqual(self.sp.fakten_loeschen_quelle("BRAIN.md"), 0)  # ein Neuimport fasst ihn nicht an
        with self.assertRaises(ValueError):
            self.sp.fakt_setzen(fid, id=99)  # unbekanntes Feld

    def test_todos_sortierung(self):
        a = self.sp.todo_anlegen("später", "geschaeft", prioritaet="niedrig")
        b = self.sp.todo_anlegen("dringend", "geschaeft", prioritaet="hoch")
        c = self.sp.todo_anlegen("normal", "geschaeft")
        d = self.sp.todo_anlegen("privat", "privat")
        self.sp.todo_setzen(c, status="erledigt")
        titel = [t["titel"] for t in self.sp.todos(bereich="geschaeft")]
        self.assertEqual(titel, ["dringend", "später", "normal"])  # Erledigtes ans Ende
        self.assertEqual([t["titel"] for t in self.sp.todos(bereich="privat")], ["privat"])
        self.assertTrue(self.sp.todo_loeschen(a))
        self.assertIsNone(self.sp.todo(a))
        self.assertIsNotNone(self.sp.todo(b))
        self.assertIsNotNone(self.sp.todo(d))

    def test_erinnerungen_werden_nur_einmal_faellig(self):
        self.sp.erinnerung_anlegen("Berger anrufen", "2000-01-01T08:00:00Z", "geschaeft")
        self.sp.erinnerung_anlegen("später", "2999-01-01T08:00:00Z", "geschaeft")
        erste = self.sp.erinnerungen_faellig_markieren(zeit.jetzt())
        self.assertEqual([e["text"] for e in erste], ["Berger anrufen"])
        self.assertEqual(self.sp.erinnerungen_faellig_markieren(zeit.jetzt()), [])
        self.assertEqual(self.sp.zaehler()["erinnerungen_faellig"], 1)

    def test_zeit_umrechnung(self):
        utc = zeit.lokal_zu_utc("2026-11-02 09:00")
        self.assertTrue(utc.endswith("Z") and len(utc) == 20)
        self.assertEqual(zeit.lokal_zu_utc("2026-11-02"), zeit.lokal_zu_utc("2026-11-02 09:00"))
        with self.assertRaises(ValueError):
            zeit.lokal_zu_utc("übermorgen")
        self.assertIn("2026", zeit.utc_zu_lokal_text("2026-11-02T08:00:00Z"))

    def test_gespraeche_und_nachrichten(self):
        g = self.sp.gespraech_anlegen("geschaeft")
        for i in range(5):
            self.sp.nachricht_hinzufuegen(g, "nutzer" if i % 2 == 0 else "jarvis", "Text %d" % i,
                                          meta={"n": i} if i == 3 else None)
        letzte = self.sp.nachrichten(g, limit=3)
        self.assertEqual([n["text"] for n in letzte], ["Text 2", "Text 3", "Text 4"])
        self.assertEqual(letzte[1]["meta"], {"n": 3})
        self.assertEqual(self.sp.letztes_gespraech("geschaeft")["kennung"], g)
        self.assertIsNone(self.sp.letztes_gespraech("privat"))

    def test_anfragen_statistik(self):
        self.sp.anfrage_erfassen("chat", "opus", 1200, True, tokens_ein=100, tokens_aus=40)
        self.sp.anfrage_erfassen("chat", "opus", 800, True, tokens_ein=50, tokens_aus=10)
        self.sp.anfrage_erfassen("chat", "opus", None, False, fehler_art="limit")
        stunden = self.sp.anfragen_stunden(24)
        self.assertEqual(len(stunden), 24)
        self.assertEqual(stunden[-1]["anzahl"], 3)
        self.assertEqual(stunden[-1]["fehler"], 1)
        self.assertEqual(self.sp.antwortzeiten(), [1200, 800])
        v = self.sp.verbrauch_heute()
        self.assertEqual((v["anfragen"], v["tokens_ein"], v["tokens_aus"], v["fehler"]), (3, 150, 50, 1))

    def test_auftraege_zustandsmaschine(self):
        a = self.sp.auftrag_anlegen("Plan", "Ziel", "geschaeft", status="wartend")
        b = self.sp.auftrag_anlegen("Zweiter", "Ziel", "geschaeft", status="wartend")
        s = self.sp.schritt_anlegen(a, 1, "recherche", "Suchen", "tu es", "Quellen da", abhaengig_von=[])
        self.assertEqual(self.sp.auftrag_uebernehmen(), a)  # ältester zuerst
        self.assertEqual(self.sp.auftrag(a)["status"], "laeuft")
        self.assertEqual(self.sp.auftrag_uebernehmen(), b)
        self.assertIsNone(self.sp.auftrag_uebernehmen())
        self.sp.schritt_setzen(s, status="laeuft")
        self.assertEqual(len(self.sp.schritte_aktiv()), 1)
        self.assertEqual(sorted(self.sp.auftraege_unterbrechen()), [a, b])  # Neustart
        self.assertEqual(self.sp.auftrag(a)["status"], "unterbrochen")
        self.assertEqual(self.sp.schritte(a)[0]["status"], "offen")
        self.assertEqual(self.sp.auftrag_aufruf_zaehlen(a), 1)
        self.assertEqual(self.sp.auftrag_aufruf_zaehlen(a), 2)
        c = self.sp.auftrag_anlegen("Geplant", "Ziel", "geschaeft", status="geplant", geplant_fuer="2000-01-01T00:00:00Z")
        self.assertEqual(self.sp.geplante_auftraege_faellig(zeit.jetzt()), [c])
        self.assertEqual(self.sp.auftrag(c)["status"], "wartend")
        self.assertTrue(self.sp.auftrag_loeschen(a))
        self.assertEqual(self.sp.schritte(a), [])

    def test_freigabe_nur_einmal_entscheidbar(self):
        f = self.sp.freigabe_anlegen("skript_ausfuehren", {"pfad": "a.py"}, "print(1)", "Risiko", 3, "geschaeft")
        self.assertEqual(self.sp.freigabe(f)["parameter"], {"pfad": "a.py"})
        self.assertTrue(self.sp.freigabe_entscheiden(f, "erteilt", "ok"))
        self.assertFalse(self.sp.freigabe_entscheiden(f, "abgelehnt"))  # zu spät
        self.assertEqual(self.sp.freigabe(f)["status"], "erteilt")

    def test_freigaben_laufen_ab(self):
        f = self.sp.freigabe_anlegen("datei_loeschen", {}, "x", "", 3, "geschaeft")
        self.assertEqual(self.sp.freigaben_ablaufen("2000-01-01T00:00:00Z"), [])
        self.assertEqual(self.sp.freigaben_ablaufen("2999-01-01T00:00:00Z"), [f])
        self.assertEqual(self.sp.freigabe(f)["status"], "abgelaufen")
        self.assertFalse(self.sp.freigabe_entscheiden(f, "erteilt"))  # Abgelaufenes lässt sich nicht mehr erteilen

    def test_audit(self):
        self.sp.audit_schreiben("werkzeug", werkzeug="datei_lesen", stufe=1, bereich="geschaeft",
                                details={"pfad": "a.txt"}, ergebnis="ok")
        eintrag = self.sp.audit_liste()[0]
        self.assertEqual(eintrag["details"], {"pfad": "a.txt"})
        self.assertEqual(self.sp.audit_liste(art="freigabe"), [])

    def test_export_und_loeschen(self):
        self.sp.fakt_hinzufuegen("Etwas Wichtiges")
        self.sp.todo_anlegen("Aufgabe", "geschaeft")
        daten = self.sp.exportieren()
        self.assertEqual(len(daten["fakten"]), 1)
        self.assertEqual(daten["aufgaben"][0]["titel"], "Aufgabe")
        json.dumps(daten)  # exportierbar
        self.sp.meta_setzen("gesperrt", "1")
        self.sp.alles_loeschen()
        self.assertEqual(self.sp.exportieren()["fakten"], [])
        self.assertIsNone(self.sp.meta("gesperrt"))
        self.assertEqual(self.sp.meta("schema_version"), "1")
        self.sp.fakt_hinzufuegen("Danach weiter nutzbar")  # Datenbank bleibt benutzbar

    def test_sicherung_und_neustart(self):
        self.sp.fakt_hinzufuegen("Überlebt Neustart und Sicherung")
        kopie = os.path.join(self.ordner, "backups", "kopie.db")
        self.sp.sichern(kopie)
        self.assertEqual(self.sp.integritaet(), "ok")
        self.sp.schliessen()
        zweiter = Speicher(self.konfig.db_datei)  # "Neustart"
        self.assertEqual([f["text"] for f in zweiter.fakten()], ["Überlebt Neustart und Sicherung"])
        zweiter.schliessen()
        verbindung = sqlite3.connect(kopie)
        self.assertEqual(verbindung.execute("SELECT text FROM fakten").fetchone()[0], "Überlebt Neustart und Sicherung")
        verbindung.close()
        self.sp = Speicher(self.konfig.db_datei)

    def test_gleichzeitiger_zugriff(self):
        fehler = []

        def arbeit(n):
            try:
                for i in range(20):
                    self.sp.fakt_hinzufuegen("Eintrag %d Nummer %d" % (n, i * 1000 + n), bereich="geschaeft")
                    self.sp.todo_anlegen("T %d %d" % (n, i), "geschaeft")
                    self.sp.todos()
            except Exception as e:  # noqa: BLE001 - Test sammelt alle Fehler
                fehler.append(repr(e))

        faeden = [threading.Thread(target=arbeit, args=(n,)) for n in range(6)]
        for f in faeden:
            f.start()
        for f in faeden:
            f.join()
        self.assertEqual(fehler, [])
        self.assertEqual(self.sp.zaehler()["todos_offen"], 120)


class GedaechtnisTest(Grundlage):
    def test_bereiche_bleiben_getrennt(self):
        self.sp.fakt_hinzufuegen("Familienbetrieb für Bau und Reinigung", bereich="geschaeft")
        self.sp.fakt_hinzufuegen("Führerschein machen und Haus bauen", bereich="privat")
        self.sp.fakt_hinzufuegen("Deutsch und kurz antworten", bereich="allgemein", art="regel")
        self.sp.fakt_hinzufuegen("Mac ist ein iMac von 2017", bereich="technik")
        text = gedaechtnis.kontext_text(self.sp, self.konfig, "geschaeft", "Was machen wir?")
        self.assertIn("Familienbetrieb", text)
        self.assertIn("Deutsch und kurz", text)
        self.assertIn("iMac von 2017", text)
        self.assertNotIn("Führerschein", text)  # Privates erreicht das Modell im Geschäftsgespräch nicht
        privat = gedaechtnis.kontext_text(self.sp, self.konfig, "privat", "Was machen wir?")
        self.assertIn("Führerschein", privat)
        self.assertNotIn("Familienbetrieb", privat)
        self.assertIn("[BEREICH] privat", privat)

    def test_unbekannter_bereich_faellt_auf_ersten_zurueck(self):
        self.assertEqual(gedaechtnis.bereich_pruefen(self.konfig, "geheim"), "geschaeft")
        self.assertEqual(gedaechtnis.bereich_pruefen(self.konfig, "privat"), "privat")

    def test_vorschlaege_und_verworfenes_sind_nicht_im_kontext(self):
        self.sp.fakt_hinzufuegen("Bestätigte Tatsache", bereich="geschaeft")
        self.sp.fakt_hinzufuegen("Unbestätigter Vorschlag", bereich="geschaeft", status="vorschlag", quelle="jarvis")
        fid, _ = self.sp.fakt_hinzufuegen("Verworfene Sache", bereich="geschaeft")
        self.sp.fakt_setzen(fid, status="verworfen")
        text = gedaechtnis.kontext_text(self.sp, self.konfig, "geschaeft")
        self.assertIn("Bestätigte Tatsache", text)
        self.assertNotIn("Unbestätigter Vorschlag", text)
        self.assertNotIn("Verworfene Sache", text)

    def test_relevanz_bei_grossem_gedaechtnis(self):
        for i in range(40):
            self.sp.fakt_hinzufuegen("Nebensächliche Notiz Nummer %d zu Thema%d" % (i, i), bereich="geschaeft")
        self.sp.fakt_hinzufuegen("Preise werden über Stundensatz und Leistungswerte kalkuliert", bereich="geschaeft")
        self.sp.fakt_hinzufuegen("Immer auf Deutsch antworten", bereich="allgemein", art="regel")
        fakten = gedaechtnis.kontext_fakten(self.sp, "geschaeft", "Wie kalkuliere ich den Preis?")
        texte = [f["text"] for f in fakten]
        self.assertTrue(any("Stundensatz" in t for t in texte))  # passt zur Frage
        self.assertTrue(any("Deutsch" in t for t in texte))  # Regeln sind immer dabei
        self.assertLess(len(fakten), 20)  # nicht alles auf einmal
        suche = gedaechtnis.suchen(self.sp, "geschaeft", "Stundensatz kalkulieren")
        self.assertIn("Stundensatz", suche[0]["text"])
        self.assertGreater(suche[0]["punkte"], 0)

    def test_fokus_sortiert_nach_dringlichkeit(self):
        self.sp.todo_anlegen("normal ohne Datum", "geschaeft")
        self.sp.todo_anlegen("hoch", "geschaeft", prioritaet="hoch")
        self.sp.todo_anlegen("überfällig", "geschaeft", faellig="2000-01-01T09:00:00Z")
        self.sp.todo_anlegen("privat", "privat")
        self.sp.freigabe_anlegen("datei_loeschen", {}, "x", "", 3, "geschaeft")
        self.sp.freigabe_anlegen("datei_loeschen", {}, "x", "", 3, "privat")
        f = gedaechtnis.fokus(self.sp, "geschaeft")
        self.assertEqual([t["titel"] for t in f["todos"]], ["überfällig", "hoch", "normal ohne Datum"])
        self.assertEqual(len(f["freigaben"]), 1)

    def test_profil_import_aus_dem_echten_brain(self):
        pfad = os.path.join(WURZEL, "BRAIN.md")
        with open(pfad, encoding="utf-8") as f:
            eintraege = gedaechtnis.profil_parsen(f.read())
        kuerzel = {e["kuerzel"] for e in eintraege}
        for k in ("C1", "C6", "C18", "P1", "P7", "P13", "D1", "D9"):
            self.assertIn(k, kuerzel)
        je = {e["kuerzel"]: e for e in eintraege}
        self.assertEqual(je["C6"]["bereich"], "privat")  # Finanzziele sind privat
        self.assertEqual(je["C1"]["bereich"], "geschaeft")
        self.assertEqual(je["C16"]["bereich"], "allgemein")
        self.assertEqual(je["P13"]["bereich"], "technik")
        self.assertNotIn("**", je["C1"]["text"])
        self.assertIn("|", je["P13"]["text"])  # maskierter senkrechter Strich bleibt Teil des Textes
        regeln = [e for e in eintraege if e["art"] == "regel"]
        self.assertTrue(any("ausdrückliches Ja" in e["text"] for e in regeln))

        ergebnis = gedaechtnis.profil_importieren(self.sp, self.konfig, pfad)
        self.assertTrue(ergebnis["ok"])
        self.assertGreater(ergebnis["neu"], 20)
        # Die Finanzziele erscheinen nur im privaten Kontext
        geschaeft = gedaechtnis.kontext_text(self.sp, self.konfig, "geschaeft", "Aufträge finden")
        privat = gedaechtnis.kontext_text(self.sp, self.konfig, "privat", "Ziele")
        self.assertNotIn("Mio.", geschaeft)
        self.assertIn("Mio.", privat)
        self.assertIn("Bau und Reinigung", geschaeft)

    def test_import_ist_wiederholbar_und_schont_bearbeitetes(self):
        pfad = os.path.join(WURZEL, "BRAIN.md")
        gedaechtnis.profil_importieren(self.sp, self.konfig, pfad)
        anzahl = len(self.sp.fakten(status=None))
        erstes = next(f for f in self.sp.fakten(status=None) if f["quelle"] == "BRAIN.md")
        self.sp.fakt_setzen(erstes["id"], text="Von mir korrigiert")
        gedaechtnis.profil_importieren(self.sp, self.konfig, pfad)
        alle = self.sp.fakten(status=None)
        self.assertIn("Von mir korrigiert", [f["text"] for f in alle])
        self.assertGreaterEqual(len(alle), anzahl)
        self.assertLessEqual(len(alle), anzahl + 1)  # kein Dopplungsfeuerwerk
        self.assertFalse(gedaechtnis.profil_importieren(self.sp, self.konfig, "/gibt/es/nicht.md")["ok"])


if __name__ == "__main__":
    unittest.main()
