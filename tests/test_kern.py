#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Tests für den Server als Ganzes: Zugang, Schutz, Gespräch, Freigaben, Notstopp, WLAN, Neustart, Skript, Abhängigkeiten.

Claude Code und ``say`` sind durch Ersatzprogramme ersetzt (tests/ersatz_claude.py, tests/hilfen.py).

Aufruf::

    python3 -m unittest tests.test_kern -v
"""

import ast
import importlib.util
import json
import os
import socket
import sqlite3
import subprocess
import sys
import sysconfig
import threading
import time
import unittest
from unittest import mock
from urllib.parse import quote

from tests.hilfen import WURZEL, Umgebung

from jarvis_core import auth, werkzeuge  # noqa: E402
from jarvis_core import konfig as konfig_modul  # noqa: E402
from jarvis_core.protokoll import Protokoll, letzte_eintraege  # noqa: E402
from jarvis_core.server import JarvisServer, PidFehler  # noqa: E402

JUDGE = "unabhängige Prüfer"
PLAN = json.dumps({"titel": "Notiz", "schritte": [
    {"rolle": "dokumentation", "titel": "Schreiben", "anweisung": "Schreibe die Notiz.", "kriterium": "Datei da",
     "datei": "notiz.md", "abhaengig_von": []}]})
STATUS_FELDER = {"name", "version", "laeuft", "seit", "laufzeit_sekunden", "pid", "adresse", "python", "anfragen",
                 "gesperrt", "lan"}


class ServerBasis(Umgebung):
    """Startet einen echten JARVIS-Server in einem Faden (ohne Signale) und bietet Hilfen für Aufrufe."""

    def setUp(self):
        super().setUp()
        self.konfig = konfig_modul.laden()
        self.log = Protokoll(self.konfig)
        self.token = auth.token_holen(self.konfig)
        self.server = None
        self.faden = None

    def starten(self):
        self.server = JarvisServer(self.konfig, self.log)
        self.faden = threading.Thread(target=self.server.starten, kwargs={"signale": False}, daemon=True)
        self.faden.start()
        ende = time.time() + 15
        while time.time() < ende:
            if not self.faden.is_alive():
                self.fail("Der Server ist beim Start abgestürzt (siehe Log).")
            if self.server.bereit() and self.server.zeitplan.is_alive():
                return self.server
            time.sleep(0.02)
        self.fail("Der Server wurde nicht rechtzeitig bereit.")

    def stoppen(self):
        if self.server:
            self.server.stoppen()
            self.faden.join(timeout=15)
            self.server = None

    def tearDown(self):
        self.stoppen()
        self.log.schliessen()
        super().tearDown()

    def api(self, methode, pfad, koerper=None, kopf=None, token=True):
        kopfzeilen = dict(kopf or {})
        if token:
            kopfzeilen.setdefault(auth.KOPFZEILE, self.token)
        code, antwort, _ = self.http(methode, pfad, koerper, kopfzeilen)
        return code, antwort

    def zustand(self, abfrage=""):
        code, z = self.api("GET", "/api/zustand" + abfrage)
        self.assertEqual(code, 200, z)
        return z

    def warte(self, bedingung, timeout=25, text="Bedingung"):
        ende = time.time() + timeout
        while time.time() < ende:
            wert = bedingung()
            if wert:
                return wert
            time.sleep(0.1)
        self.fail("%s wurde nicht erreicht." % text)


class ZugangTest(ServerBasis):
    def setUp(self):
        super().setUp()
        self.starten()

    def test_status_ist_offen_und_harmlos(self):
        code, s, _ = self.http("GET", "/status")
        self.assertEqual(code, 200)
        self.assertEqual(set(s), STATUS_FELDER)  # nur diese harmlosen Angaben - nichts Persönliches, kein Schlüssel
        self.assertEqual((s["name"], s["laeuft"], s["gesperrt"], s["lan"]), ("JARVIS", True, False, False))
        self.assertEqual(s["adresse"], "http://127.0.0.1:%d" % self.port)

    def test_api_verlangt_den_schluessel(self):
        for pfad in ("/api/zustand", "/api/logs", "/api/export", "/api/audit", "/api/stimmen", "/api/suche?q=x", "/api/auftrag?id=1"):
            with self.subTest(pfad=pfad):
                self.assertEqual(self.http("GET", pfad)[0], 401)
                self.assertEqual(self.http("GET", pfad, kopf={auth.KOPFZEILE: "falsch"})[0], 401)
        for pfad in ("/api/anfrage", "/api/notstopp", "/api/entsperren", "/api/freigabe", "/api/alles-loeschen", "/api/werkzeug",
                     "/api/einstellungen", "/api/auftrag", "/api/fakt"):
            with self.subTest(pfad=pfad):
                self.assertEqual(self.http("POST", pfad, {"text": "x"})[0], 401)
        cookie = "%s=%s" % (auth.COOKIE, self.token)
        self.assertEqual(self.http("GET", "/api/zustand", kopf={"Cookie": cookie})[0], 200)
        self.assertEqual(self.http("GET", "/api/zustand", kopf={"Cookie": "%s=falsch" % auth.COOKIE})[0], 401)
        self.assertEqual(self.http("GET", "/api/zustand", kopf={"Cookie": "kaputt;;;=="})[0], 401)
        self.assertEqual(self.http("GET", "/api/zustand", kopf={auth.KOPFZEILE: self.token})[0], 200)
        abgelehnt = [e for e in letzte_eintraege(self.konfig.log_datei, 200) if e["ereignis"] == "zugriff_abgelehnt"]
        self.assertTrue(abgelehnt and all(e["stufe"] == "WARNING" for e in abgelehnt))
        self.assertIn("zugang", {e["grund"] for e in abgelehnt})
        self.assertNotIn(self.token, json.dumps(abgelehnt))  # der Schlüssel landet nie im Log

    def test_link_setzt_ein_geschuetztes_cookie(self):
        code, _, kopf = self.http("GET", "/?t=%s" % self.token)
        self.assertEqual(code, 302)
        self.assertEqual(kopf["Location"], "/")  # der Schlüssel verschwindet aus der Adresse
        for teil in ("HttpOnly", "SameSite=Strict", "Path=/", "%s=%s" % (auth.COOKIE, self.token)):
            self.assertIn(teil, kopf["Set-Cookie"])
        code, _, kopf = self.http("GET", "/?t=falsch")
        self.assertEqual(code, 401)
        self.assertNotIn("Set-Cookie", kopf)

    def test_schluesseldatei_ist_nur_fuer_den_benutzer(self):
        self.assertEqual(os.stat(self.konfig.token_datei).st_mode & 0o777, 0o600)
        self.assertEqual(os.stat(self.konfig.daten_ordner).st_mode & 0o777, 0o700)  # der ganze Datenordner ist privat
        self.assertEqual(auth.token_holen(self.konfig), self.token)  # bleibt stabil
        self.assertGreaterEqual(len(self.token), 40)

    def test_fremder_host_wird_abgelehnt(self):
        for pfad in ("/status", "/api/zustand", "/"):
            with self.subTest(pfad=pfad):
                self.assertEqual(self.http("GET", pfad, kopf={"Host": "angreifer.example:%d" % self.port})[0], 403)
        self.assertEqual(self.http("POST", "/api/anfrage", {"text": "x"}, kopf={"Host": "angreifer.example"})[0], 403)
        self.assertEqual(self.http("GET", "/status", kopf={"Host": "localhost:%d" % self.port})[0], 200)
        self.assertEqual(self.http("GET", "/status", kopf={"Host": "[::1]:%d" % self.port})[0], 200)

    def test_fremde_webseiten_werden_abgelehnt(self):
        for kopf in ({"Origin": "https://boese.example"}, {"Sec-Fetch-Site": "cross-site"}, {"Sec-Fetch-Site": "same-site"}):
            with self.subTest(kopf=kopf):
                self.assertEqual(self.api("POST", "/api/notstopp", {}, kopf=kopf)[0], 403)
        self.assertFalse(self.server.agent.gesperrt.is_set())
        self.assertEqual(self.api("POST", "/api/still", {}, kopf={"Origin": "http://127.0.0.1:%d" % self.port})[0], 200)
        self.assertEqual(self.api("POST", "/api/still", {}, kopf={"Sec-Fetch-Site": "same-origin"})[0], 200)

    def test_formatpruefung(self):
        form = {"Content-Type": "application/x-www-form-urlencoded"}
        self.assertEqual(self.api("POST", "/api/anfrage", b"text=x", kopf=form)[0], 415)
        self.assertEqual(self.api("POST", "/api/anfrage", b"{kaputt")[0], 400)
        self.assertEqual(self.api("POST", "/api/anfrage", ["liste"])[0], 400)
        self.assertEqual(self.api("POST", "/api/anfrage", {"text": "   "})[0], 400)
        self.assertEqual(self.api("POST", "/api/anfrage", {"etwas": "anderes"})[0], 400)
        self.assertEqual(self.api("POST", "/api/anfrage", {"text": "x" * 10001})[0], 413)
        self.assertEqual(self.api("POST", "/api/anfrage", {"text": "x", "gespraech": 5})[0], 400)
        self.assertEqual(self.api("POST", "/api/anfrage", {"text": "x", "gespraech": "gibtsnicht"})[0], 404)
        self.assertEqual(self.api("POST", "/api/gibtsnicht", {"a": 1})[0], 404)
        self.assertEqual(self.api("GET", "/api/gibtsnicht")[0], 404)
        self.assertEqual(self.api("GET", "/api/logs?anzahl=abc")[0], 400)
        self.assertEqual(self.http("POST", "/status", {"a": 1})[0], 404)
        self.assertEqual(self.http("GET", "/gibtsnicht")[0], 404)
        self.assertEqual(self.aufrufe(), [])  # keine dieser Anfragen hat das Modell erreicht

    def test_ratenbegrenzung(self):
        self.konfig.aktualisieren({"anfragen_pro_minute": 3})
        codes = [self.api("POST", "/api/anfrage", {"text": "Hallo %d" % i})[0] for i in range(5)]
        self.assertEqual(codes, [200, 200, 200, 429, 429])
        code, _, kopf = self.http("POST", "/api/anfrage", {"text": "noch eine"}, {auth.KOPFZEILE: self.token})
        self.assertEqual(code, 429)
        self.assertIn("Retry-After", kopf)
        self.assertEqual(len(self.aufrufe()), 3)  # abgewiesene Anfragen kosten kein Kontingent
        self.assertEqual(self.api("GET", "/api/zustand")[0], 200)  # Lesen bleibt möglich

    def test_oberflaeche_wird_mit_schutzkopfzeilen_ausgeliefert(self):
        code, seite, kopf = self.http("GET", "/")
        self.assertEqual(code, 200)
        self.assertIn("JARVIS", seite)
        self.assertIn("default-src 'self'", kopf["Content-Security-Policy"])
        self.assertEqual(kopf["Cache-Control"], "no-store")
        self.assertEqual(kopf["X-Frame-Options"], "DENY")
        self.assertEqual(kopf["X-Content-Type-Options"], "nosniff")
        self.assertNotIn(self.token, seite)  # die Oberfläche selbst enthält keinen Schlüssel


class GespraechTest(ServerBasis):
    def setUp(self):
        super().setUp()
        self.starten()

    def test_anfrage_und_zustand(self):
        self.drehbuch([{"nr": 1, "antwort": "Hallo, ich bin Jarvis."}, {"nr": 2, "antwort": "Gern."}])
        code, a = self.api("POST", "/api/anfrage", {"text": "Hallo"})
        self.assertEqual((code, a["antwort"], a["bereich"]), (200, "Hallo, ich bin Jarvis.", "geschaeft"))
        code, b = self.api("POST", "/api/anfrage", {"text": "Danke", "gespraech": a["gespraech"]})
        self.assertEqual((code, b["gespraech"], b["antwort"]), (200, a["gespraech"], "Gern."))
        z = self.zustand()
        self.assertEqual(z["gespraech"], a["gespraech"])
        self.assertEqual([n["rolle"] for n in z["nachrichten"]], ["nutzer", "jarvis", "nutzer", "jarvis"])
        self.assertEqual(z["status"]["anfragen"], 2)
        self.assertEqual(sum(h["anzahl"] for h in z["diagramme"]["stunden"]), 2)
        self.assertEqual(len(z["diagramme"]["stunden"]), 24)
        self.assertEqual(len(z["diagramme"]["antwortzeiten"]), 2)
        self.assertEqual((z["system"]["verbrauch"]["tokens_ein"], z["system"]["verbrauch"]["tokens_aus"]), (240, 120))
        for schluessel in ("system", "zaehler", "todos", "auftraege", "freigaben", "fakten", "erinnerungen", "fokus", "agenten", "log"):
            self.assertIn(schluessel, z)

    def test_bereiche_in_der_oberflaeche(self):
        def texte(z):
            return " ".join(f["text"] for f in z["fakten"])
        geschaeft, privat, alle = self.zustand("?bereich=geschaeft"), self.zustand("?bereich=privat"), self.zustand("?alle=1")
        self.assertIn("Familienbetrieb", texte(geschaeft))
        self.assertNotIn("500.000", texte(geschaeft))  # private Ziele bleiben aus dem Geschäftsbereich draußen
        self.assertIn("500.000", texte(privat))
        self.assertNotIn("Familienbetrieb", texte(privat))
        self.assertIn("Familienbetrieb", texte(alle))  # der Nutzer selbst darf alles sehen
        self.assertIn("500.000", texte(alle))
        self.assertEqual(self.zustand("?bereich=geheim")["bereich"], "geschaeft")

    def test_gespraeche_getrennt_nach_bereich(self):
        self.drehbuch([{"nr": 1, "antwort": "Geschäftlich."}, {"nr": 2, "antwort": "Privat."}, {"nr": 3, "antwort": "Weiter."}])
        a = self.api("POST", "/api/anfrage", {"text": "Frage", "bereich": "geschaeft"})[1]
        b = self.api("POST", "/api/anfrage", {"text": "Frage", "bereich": "privat"})[1]
        self.assertNotEqual(a["gespraech"], b["gespraech"])
        self.assertEqual(self.zustand("?bereich=geschaeft")["nachrichten"][-1]["text"], "Geschäftlich.")
        self.assertEqual(self.zustand("?bereich=privat")["nachrichten"][-1]["text"], "Privat.")
        # Ein Gespräch gehört fest zu seinem Bereich - er lässt sich nicht nachträglich wechseln
        c = self.api("POST", "/api/anfrage", {"text": "Weiter", "gespraech": a["gespraech"], "bereich": "privat"})[1]
        self.assertEqual((c["bereich"], c["gespraech"]), ("geschaeft", a["gespraech"]))
        # Im privaten Gespräch sieht das Modell keine Geschäftsdaten
        self.assertNotIn("Familienbetrieb", self.aufrufe()[1]["stdin"])
        self.assertNotIn("500.000", self.aufrufe()[0]["stdin"])

    def test_freigabe_ueber_die_oberflaeche(self):
        os.makedirs(self.werkstatt, exist_ok=True)
        with open(os.path.join(self.werkstatt, "a.md"), "w", encoding="utf-8") as f:
            f.write("alt")
        self.drehbuch([{"nr": 1, "antwort": 'Ich überschreibe.\n<aktion werkzeug="datei_schreiben" pfad="a.md">neu</aktion>'}])
        a = self.api("POST", "/api/anfrage", {"text": "Aktualisiere a.md"})[1]
        self.assertEqual(len(a["freigaben"]), 1)
        freigabe_id = a["freigaben"][0]
        z = self.zustand()
        self.assertEqual(z["freigaben"][0]["werkzeug"], "datei_schreiben")
        self.assertIn("ÜBERSCHRIEBEN", z["freigaben"][0]["vorschau"])
        with open(os.path.join(self.werkstatt, "a.md"), encoding="utf-8") as f:
            self.assertEqual(f.read(), "alt")  # vor dem Ja ist nichts passiert
        self.assertEqual(self.api("POST", "/api/freigabe", {"id": freigabe_id})[0], 400)
        self.assertEqual(self.api("POST", "/api/freigabe", {"id": freigabe_id, "entscheidung": "vielleicht"})[0], 400)
        code, f = self.api("POST", "/api/freigabe", {"id": freigabe_id, "entscheidung": "ja"})
        self.assertEqual((code, f["ok"]), (200, True))
        with open(os.path.join(self.werkstatt, "a.md"), encoding="utf-8") as fl:
            self.assertEqual(fl.read(), "neu")
        self.assertEqual(self.api("POST", "/api/freigabe", {"id": freigabe_id, "entscheidung": "ja"})[0], 409)  # nur einmal gültig
        self.assertEqual(self.zustand()["freigaben"], [])
        audit = self.api("GET", "/api/audit?art=freigabe_erteilt")[1]["eintraege"]
        self.assertEqual(audit[0]["werkzeug"], "datei_schreiben")

    def test_freigabe_ablehnen(self):
        os.makedirs(self.werkstatt, exist_ok=True)
        with open(os.path.join(self.werkstatt, "b.md"), "w", encoding="utf-8") as f:
            f.write("bleibt")
        self.drehbuch([{"nr": 1, "antwort": 'Ich ersetze.\n<aktion werkzeug="datei_schreiben" pfad="b.md">weg damit</aktion>'}])
        a = self.api("POST", "/api/anfrage", {"text": "Ersetze b.md"})[1]
        code, f = self.api("POST", "/api/freigabe", {"id": a["freigaben"][0], "entscheidung": "nein"})
        self.assertEqual((code, f["status"]), (200, "abgelehnt"))
        with open(os.path.join(self.werkstatt, "b.md"), encoding="utf-8") as fl:
            self.assertEqual(fl.read(), "bleibt")
        self.assertEqual(self.api("POST", "/api/freigabe", {"id": a["freigaben"][0], "entscheidung": "ja"})[0], 409)

    def test_notstopp_ueber_die_oberflaeche(self):
        self.assertEqual(self.api("POST", "/api/notstopp", {})[0], 200)
        self.assertTrue(self.http("GET", "/status")[1]["gesperrt"])
        code, a = self.api("POST", "/api/anfrage", {"text": "Hallo"})
        self.assertEqual((code, a["art"]), (423, "gesperrt"))
        self.assertEqual(self.api("POST", "/api/sprich", {"text": "Hallo"})[0], 423)
        self.assertEqual(self.api("POST", "/api/auftrag", {"aktion": "starten", "id": 1})[0], 409)
        self.assertEqual(self.aufrufe(), [])
        self.assertTrue(self.zustand()["system"]["gesperrt"])
        self.assertEqual(self.api("POST", "/api/entsperren", {})[0], 200)
        self.assertFalse(self.http("GET", "/status")[1]["gesperrt"])
        self.assertEqual(self.api("POST", "/api/anfrage", {"text": "Hallo"})[0], 200)

    def test_werkzeuge_sperren_und_freigeben(self):
        code, a = self.api("POST", "/api/werkzeug", {"name": "datei_schreiben", "gesperrt": True})
        self.assertEqual((code, a["gesperrt"]), (200, ["datei_schreiben"]))
        liste = {w["name"]: w for w in self.zustand()["system"]["werkzeuge"]}
        self.assertTrue(liste["datei_schreiben"]["gesperrt"])
        self.assertFalse(liste["datei_lesen"]["gesperrt"])
        self.assertEqual(liste["datei_loeschen"]["stufe"], werkzeuge.STUFEN[werkzeuge.FREIGABE])
        self.assertEqual(self.api("POST", "/api/werkzeug", {"name": "gibtsnicht", "gesperrt": True})[0], 404)
        self.assertEqual(self.api("POST", "/api/werkzeug", {"name": "datei_schreiben", "gesperrt": "ja"})[0], 400)
        self.api("POST", "/api/werkzeug", {"name": "datei_schreiben", "gesperrt": False})
        self.assertEqual(self.konfig.deaktivierte_werkzeuge, [])

    def test_einstellungen(self):
        code, _ = self.api("POST", "/api/einstellungen", {"tempo": 220, "vorlesen": False, "modelle": {"chat": "sonnet"}})
        self.assertEqual(code, 200)
        self.assertEqual((self.konfig.tempo, self.konfig.vorlesen, self.konfig.modell_fuer("chat")), (220, False, "sonnet"))
        self.assertEqual(konfig_modul.laden().tempo, 220)  # bleibt gespeichert
        self.assertEqual(self.api("POST", "/api/einstellungen", {"tempo": "schnell"})[0], 400)
        self.assertEqual(self.api("POST", "/api/einstellungen", {"port": 9999})[0], 400)  # nicht änderbar
        self.assertEqual(self.api("POST", "/api/einstellungen", {"lan": True})[0], 400)  # WLAN nur per Kommandozeile
        self.assertFalse(self.konfig.lan)

    def test_gedaechtnis_bearbeiten(self):
        a = self.api("POST", "/api/fakt", {"aktion": "hinzufuegen", "text": "Neuer Eintrag", "bereich": "geschaeft"})[1]
        self.assertTrue(a["neu"])
        self.assertFalse(self.api("POST", "/api/fakt", {"aktion": "hinzufuegen", "text": "neuer eintrag!", "bereich": "geschaeft"})[1]["neu"])
        self.assertEqual(self.api("POST", "/api/fakt", {"aktion": "hinzufuegen", "text": "X", "bereich": "geheim"})[0], 400)
        self.assertEqual(self.api("POST", "/api/fakt", {"aktion": "hinzufuegen", "text": "  "})[0], 400)
        self.assertEqual(self.api("POST", "/api/fakt", {"aktion": "tanzen", "id": a["id"]})[0], 400)
        self.assertEqual(self.api("POST", "/api/fakt", {"aktion": "aendern", "id": a["id"], "text": "Geändert", "bereich": "privat"})[0], 200)
        fakt = self.server.speicher.fakt(a["id"])
        self.assertEqual((fakt["text"], fakt["bereich"], fakt["quelle"]), ("Geändert", "privat", "nutzer"))
        vorschlag, _ = self.server.speicher.fakt_hinzufuegen("Vorschlag von Jarvis", bereich="geschaeft", status="vorschlag", quelle="jarvis")
        self.assertEqual(self.api("POST", "/api/fakt", {"aktion": "bestaetigen", "id": vorschlag})[0], 200)
        self.assertEqual(self.server.speicher.fakt(vorschlag)["status"], "bestaetigt")
        self.assertEqual(self.api("POST", "/api/fakt", {"aktion": "loeschen", "id": vorschlag})[0], 200)
        self.assertIsNone(self.server.speicher.fakt(vorschlag))
        self.assertEqual(self.api("POST", "/api/fakt", {"aktion": "loeschen", "id": 99999})[0], 404)
        treffer = self.api("GET", "/api/suche?q=%s&bereich=privat" % quote("Geändert"))[1]["treffer"]
        self.assertEqual(treffer[0]["text"], "Geändert")
        self.assertEqual(self.api("GET", "/api/suche")[0], 400)

    def test_aufgaben_und_erinnerungen(self):
        a = self.api("POST", "/api/todo", {"aktion": "anlegen", "titel": "Angebot", "prioritaet": "hoch", "faellig": "2026-11-02 09:00"})[1]
        self.assertEqual(self.zustand()["todos"][0]["titel"], "Angebot")
        self.assertEqual(self.api("POST", "/api/todo", {"aktion": "status", "id": a["id"], "status": "erledigt"})[0], 200)
        self.assertEqual(self.zustand()["zaehler"]["todos_erledigt"], 1)
        self.assertEqual(self.api("POST", "/api/todo", {"aktion": "anlegen", "titel": ""})[0], 400)
        self.assertEqual(self.api("POST", "/api/todo", {"aktion": "anlegen", "titel": "X", "faellig": "irgendwann"})[0], 400)
        self.assertEqual(self.api("POST", "/api/todo", {"aktion": "status", "id": 999, "status": "offen"})[0], 404)
        self.assertEqual(self.api("POST", "/api/todo", {"aktion": "loeschen", "id": a["id"]})[0], 200)
        self.assertEqual(self.api("POST", "/api/erinnerung", {"aktion": "anlegen", "text": "Anrufen", "faellig": "2999-01-01 09:00"})[0], 200)
        self.assertEqual(self.api("POST", "/api/erinnerung", {"aktion": "anlegen", "text": "Anrufen", "faellig": "bald"})[0], 400)
        self.assertEqual(len(self.zustand()["erinnerungen"]), 1)

    def test_export_und_loeschen(self):
        self.api("POST", "/api/fakt", {"aktion": "hinzufuegen", "text": "Exportierbar"})
        daten = self.api("GET", "/api/export")[1]["daten"]
        self.assertIn("Exportierbar", [f["text"] for f in daten["fakten"]])
        self.assertEqual(self.api("POST", "/api/alles-loeschen", {})[0], 400)
        self.assertEqual(self.api("POST", "/api/alles-loeschen", {"bestaetigung": "ja"})[0], 400)
        self.assertGreater(len(self.server.speicher.fakten()), 0)  # ohne die genaue Bestätigung bleibt alles da
        self.assertEqual(self.api("POST", "/api/alles-loeschen", {"bestaetigung": "ALLES LÖSCHEN"})[0], 200)
        self.assertEqual(self.server.speicher.fakten(status=None), [])

    def test_auftrag_ueber_die_oberflaeche(self):
        self.drehbuch([{"system": JUDGE, "antwort": json.dumps({"erfuellt": True, "begruendung": "ok"})},
                       {"stdin": "[SCHRITT 1 von 1", "antwort": '<aktion werkzeug="datei_schreiben" pfad="notiz.md">Text</aktion>'},
                       {"system": "Planer von JARVIS", "antwort": PLAN}])
        a = self.api("POST", "/api/auftrag", {"aktion": "planen", "ziel": "Schreibe eine Notiz"})[1]
        self.assertEqual(a["status"], "entwurf")
        auftrag_id = a["auftrag_id"]
        self.assertEqual(self.zustand()["auftraege"][0]["schritte"][0]["rolle"], "dokumentation")
        self.assertEqual(self.api("POST", "/api/auftrag", {"aktion": "planen", "ziel": ""})[0], 400)
        self.assertEqual(self.api("POST", "/api/auftrag", {"aktion": "tanzen", "id": auftrag_id})[0], 409)
        self.assertEqual(self.api("POST", "/api/auftrag", {"aktion": "starten", "id": auftrag_id, "start_um": "2000-01-01 09:00"})[0], 400)
        self.assertEqual(self.api("POST", "/api/auftrag", {"aktion": "starten", "id": auftrag_id, "start_um": "bald"})[0], 400)
        code, s = self.api("POST", "/api/auftrag", {"aktion": "starten", "id": auftrag_id})
        self.assertEqual(code, 200, s)
        self.warte(lambda: self.zustand()["auftraege"][0]["status"] == "fertig", text="Auftrag fertig")
        details = self.api("GET", "/api/auftrag?id=%d" % auftrag_id)[1]["auftrag"]
        self.assertEqual(details["schritte"][0]["status"], "fertig")
        with open(os.path.join(self.werkstatt, "notiz.md"), encoding="utf-8") as f:
            self.assertEqual(f.read(), "Text")
        self.assertEqual(self.zustand()["agenten"]["zuletzt"][0]["rolle_name"], "Dokumentation")
        self.assertEqual(self.api("GET", "/api/auftrag?id=999")[0], 404)
        self.assertEqual(self.api("POST", "/api/auftrag", {"aktion": "loeschen", "id": auftrag_id})[0], 200)
        self.assertEqual(self.zustand()["auftraege"], [])

    def test_abbrechen_der_laufenden_anfrage(self):
        self.drehbuch([{"modus": "langsam", "sekunden": 30}])
        ergebnis = {}
        faden = threading.Thread(target=lambda: ergebnis.update(r=self.api("POST", "/api/anfrage", {"text": "lang"})))
        faden.start()
        self.warte(lambda: self.zustand()["system"]["beschaeftigt"], text="Anfrage läuft")
        self.assertTrue(self.api("POST", "/api/abbrechen", {})[1]["abgebrochen"])
        faden.join(timeout=15)
        self.assertEqual(ergebnis["r"][1]["art"], "abgebrochen")
        self.assertFalse(self.api("POST", "/api/abbrechen", {})[1]["abgebrochen"])

    def test_sprachausgabe(self):
        code, a = self.api("POST", "/api/sprich", {"text": "Hallo, ich bin Jarvis."})
        self.assertEqual((code, a["gesprochen"]), (200, True))
        self.warte(lambda: os.path.exists(self.say_log) and os.path.getsize(self.say_log) > 0, text="say wurde aufgerufen")
        with open(self.say_log, encoding="utf-8") as f:
            inhalt = f.read()
        self.assertIn("Markus (Premium)", inhalt)  # die beste deutsche Stimme wird automatisch gewählt
        self.assertIn("Hallo, ich bin Jarvis.", inhalt)
        self.assertEqual(self.api("POST", "/api/sprich", {"text": "  "})[0], 400)
        self.assertEqual(self.api("POST", "/api/still", {})[0], 200)
        self.assertEqual(self.zustand()["system"]["stimme"]["stimme"], "Markus (Premium)")

    def test_sprechanzeige_ist_echt(self):
        os.environ["SAY_DAUER"] = "20"  # der Ersatz-say "spricht" 20 Sekunden
        self.assertFalse(self.zustand()["system"]["stimme"]["spricht"])
        self.api("POST", "/api/sprich", {"text": "Ein langer Satz."})
        self.warte(lambda: self.api("GET", "/api/stimmen")[1]["stimme"]["spricht"], text="Sprechanzeige an")
        self.assertTrue(self.zustand()["system"]["stimme"]["spricht"])
        self.api("POST", "/api/still", {})
        self.warte(lambda: not self.api("GET", "/api/stimmen")[1]["stimme"]["spricht"], text="Sprechanzeige aus")

    def test_zustand_enthaelt_angaben_fuer_die_oberflaeche(self):
        z = self.zustand()
        self.assertEqual(z["system"]["freigabe_minuten"], self.konfig.freigabe_minuten)
        self.assertEqual((z["system"]["lan"], z["system"]["erinnerungen_sprechen"]), (False, True))
        rollen_ids = [r["id"] for r in z["agenten"]["rollen"]]
        self.assertEqual(rollen_ids, ["recherche", "architektur", "entwicklung", "sicherheit", "dokumentation"])
        self.assertTrue(all(r["modell"] for r in z["agenten"]["rollen"]))  # echtes Modell, nicht leer
        self.assertEqual(z["agenten"]["aktiv"], [])  # ohne laufenden Auftrag arbeitet kein Schritt

    def test_provider_sicherung_umgebung_und_profil(self):
        self.assertTrue(self.api("POST", "/api/provider/pruefen", {})[1]["provider"]["claude_code"]["nutzbar"])
        sicherung = self.api("POST", "/api/sicherung", {})[1]["datei"]
        self.assertTrue(os.path.isfile(sicherung))
        self.assertTrue(self.zustand()["system"]["letzte_sicherung"])
        antwort = self.api("POST", "/api/umgebung", {})[1]
        self.assertTrue(antwort["ok"])
        self.assertIn("Rechner:", antwort["text"])
        vorher = [f for f in self.zustand("?alle=1")["fakten"] if f["quelle"] == "BRAIN.md"]
        profil = self.api("POST", "/api/profil/einlesen", {})[1]
        self.assertTrue(profil["ok"])
        nachher = [f for f in self.zustand("?alle=1")["fakten"] if f["quelle"] == "BRAIN.md"]
        self.assertEqual((len(nachher), profil["gefunden"]), (len(vorher), len(vorher)))  # ersetzt, nichts doppelt


class StartTest(ServerBasis):
    def test_erster_start_importiert_das_profil_einmalig(self):
        self.starten()
        brain = [f for f in self.zustand("?alle=1")["fakten"] if f["quelle"] == "BRAIN.md"]
        self.assertGreater(len(brain), 20)
        self.warte(lambda: any(f["quelle"] == "umgebung" for f in self.zustand("?alle=1")["fakten"]), text="Umgebung gemerkt")
        self.server.speicher.fakt_loeschen(brain[0]["id"])
        self.stoppen()
        self.starten()  # zweiter Start: nicht erneut importieren - Gelöschtes bleibt gelöscht
        wieder = [f for f in self.zustand("?alle=1")["fakten"] if f["quelle"] == "BRAIN.md"]
        self.assertEqual(len(wieder), len(brain) - 1)

    def test_alles_ueberlebt_einen_neustart(self):
        self.starten()
        self.drehbuch([{"antwort": "Erste Antwort."}])
        a = self.api("POST", "/api/anfrage", {"text": "Hallo"})[1]
        self.api("POST", "/api/todo", {"aktion": "anlegen", "titel": "Bleibt bestehen"})
        auftrag = self.server.speicher.auftrag_anlegen("Lief gerade", "Ziel", "geschaeft", status="laeuft")
        freigabe = self.server.speicher.freigabe_anlegen("datei_loeschen", {}, "x", "", 3, "geschaeft", auftrag_id=auftrag)
        self.stoppen()
        self.starten()
        z = self.zustand()
        self.assertEqual(z["gespraech"], a["gespraech"])
        self.assertEqual([n["text"] for n in z["nachrichten"]], ["Hallo", "Erste Antwort."])
        self.assertEqual(z["todos"][0]["titel"], "Bleibt bestehen")
        unterbrochen = next(x for x in z["auftraege"] if x["id"] == auftrag)
        self.assertEqual(unterbrochen["status"], "unterbrochen")  # nichts läuft heimlich weiter
        self.assertEqual(self.server.speicher.freigabe(freigabe)["status"], "abgelehnt")
        gestartet = [e for e in letzte_eintraege(self.konfig.log_datei, 300) if e["ereignis"] == "server_gestartet"]
        self.assertEqual(gestartet[-1]["unterbrochene_auftraege"], [auftrag])

    def test_notstopp_bleibt_nach_neustart_bestehen(self):
        self.starten()
        self.api("POST", "/api/notstopp", {})
        self.stoppen()
        self.starten()
        self.assertTrue(self.http("GET", "/status")[1]["gesperrt"])
        self.assertEqual(self.api("POST", "/api/anfrage", {"text": "Hallo"})[0], 423)
        self.assertEqual(self.aufrufe(), [])

    def test_zweiter_start_wird_verhindert(self):
        self.starten()
        zweiter = JarvisServer(self.konfig, self.log)
        try:
            with open(self.konfig.pid_datei, "w", encoding="utf-8") as f:
                f.write(str(os.getppid()))  # ein anderer Prozess, der sicher läuft
            with self.assertRaises(PidFehler):
                zweiter.starten(signale=False)
        finally:
            zweiter.speicher.schliessen()

    def test_wlan_modus_laesst_nur_die_eigene_adresse_zu(self):
        self.konfig.aktualisieren({"lan": True})
        with mock.patch("jarvis_core.server.primaere_ip", return_value="192.168.1.20"):
            self.starten()
            eigene = {"Host": "192.168.1.20:%d" % self.port}
            self.assertEqual(self.server._httpd.server_address[0], "0.0.0.0")  # noqa: S104
            self.assertTrue(self.http("GET", "/status")[1]["lan"])
            self.assertEqual(self.http("GET", "/status", kopf=eigene)[0], 200)
            self.assertEqual(self.http("GET", "/status", kopf={"Host": "angreifer.example"})[0], 403)
            self.assertEqual(self.http("GET", "/status", kopf={"Host": "192.168.1.99:%d" % self.port})[0], 403)  # fremde Adresse
            self.assertEqual(self.api("GET", "/api/zustand", kopf=eigene)[0], 200)
            self.assertEqual(self.http("GET", "/api/zustand", kopf=eigene)[0], 401)  # auch im WLAN: nur mit Schlüssel
            self.assertEqual(self.api("POST", "/api/still", {}, kopf={"Origin": "http://192.168.1.20:%d" % self.port})[0], 200)
            self.assertEqual(self.api("POST", "/api/still", {}, kopf={"Origin": "http://192.168.1.99:%d" % self.port})[0], 403)

    def test_ohne_wlan_modus_nur_lokal(self):
        self.starten()
        self.assertEqual(self.server._httpd.server_address[0], "127.0.0.1")

    def test_belegter_port(self):
        with socket.socket() as belegt:
            belegt.bind(("127.0.0.1", self.port))
            belegt.listen(1)
            server = JarvisServer(self.konfig, self.log)
            try:
                with self.assertRaises(OSError):
                    server.starten(signale=False)
            finally:
                server.speicher.schliessen()
        self.assertFalse(os.path.exists(self.konfig.pid_datei))  # keine verwaiste PID-Datei


class SkriptTest(Umgebung):
    """Start und Stopp über ./jarvis.sh als echter Hintergrundprozess, und die Kommandozeile."""

    def skript(self, *args, eingabe=None):
        umgebung = dict(os.environ, JARVIS_PYTHON=sys.executable)
        return subprocess.run([os.path.join(WURZEL, "jarvis.sh")] + list(args), capture_output=True, text=True, timeout=90,
                              env=umgebung, input=eingabe)

    def test_start_status_frage_stopp(self):
        self.drehbuch([{"antwort": "Hallo, hier ist JARVIS."}])
        try:
            lauf = self.skript("start")
            self.assertEqual(lauf.returncode, 0, lauf.stdout + lauf.stderr)
            self.assertIn("JARVIS läuft", lauf.stdout)
            self.assertIn("läuft schon", self.skript("start").stdout)
            status = self.skript("status")
            self.assertEqual(status.returncode, 0)
            self.assertIn("Claude Code", status.stdout)
            self.assertIn("Offen", status.stdout)
            self.assertIn("Hallo, hier ist JARVIS.", self.skript("frage", "Hallo", "Welt").stdout)
            self.assertIn("server_gestartet", self.skript("logs", "30").stdout)
            link = self.skript("link").stdout.strip()
            self.assertTrue(link.startswith("http://127.0.0.1:%d/?t=" % self.port), link)
            self.assertIn("NOTSTOPP aktiv", self.skript("notstopp").stdout)
            self.assertIn("NOTSTOPP", self.skript("status").stdout)
            self.assertIn("Entsperrt", self.skript("entsperren").stdout)
            self.assertIn("Gesichert:", self.skript("backup").stdout)
        finally:
            stopp = self.skript("stopp")
        self.assertIn("gestoppt", stopp.stdout)
        self.assertEqual(self.skript("status").returncode, 1)
        self.assertFalse(os.path.exists(os.path.join(os.environ["JARVIS_DATEN"], "jarvis.pid")))
        self.assertIn("server_gestoppt", self.skript("logs", "30").stdout)

    def test_stopp_ohne_server_und_veraltete_pid(self):
        self.assertIn("läuft nicht", self.skript("stopp").stdout)
        fremd = subprocess.Popen(["sleep", "30"])
        try:
            os.makedirs(os.environ["JARVIS_DATEN"], exist_ok=True)
            pid_datei = os.path.join(os.environ["JARVIS_DATEN"], "jarvis.pid")
            with open(pid_datei, "w", encoding="utf-8") as f:
                f.write(str(fremd.pid))
            self.assertIn("läuft nicht", self.skript("stopp").stdout)
            self.assertIsNone(fremd.poll(), "ein fremdes Programm wurde beendet")
            self.assertFalse(os.path.exists(pid_datei))  # die veraltete Datei wird aufgeräumt
        finally:
            fremd.kill()
            fremd.wait()

    def test_belegter_port_haengt_nicht(self):
        with socket.socket() as belegt:
            belegt.bind(("127.0.0.1", self.port))
            belegt.listen(1)
            lauf = self.skript("start")
        self.assertEqual(lauf.returncode, 1)
        self.assertIn("nicht gestartet", lauf.stdout)

    def test_wlan_nur_nach_bestaetigung(self):
        nein = self.skript("lan", "an", eingabe="nein\n")
        self.assertEqual(nein.returncode, 1)
        self.assertIn("NICHT verschlüsselt", nein.stdout)
        self.assertIn("Nichts wurde geändert", nein.stdout)
        self.assertFalse(konfig_modul.laden().lan)
        self.assertEqual(self.skript("lan", "an", eingabe="ja\n").returncode, 0)
        self.assertTrue(konfig_modul.laden().lan)
        self.assertEqual(self.skript("lan", "aus").returncode, 0)
        self.assertFalse(konfig_modul.laden().lan)
        self.assertEqual(self.skript("lan", "vielleicht").returncode, 2)

    def test_sicherung_export_und_wiederherstellung(self):
        daten = os.environ["JARVIS_DATEN"]
        self.assertEqual(self.skript("start").returncode, 0)
        self.skript("frage", "Etwas, das gesichert werden soll")
        self.assertEqual(self.skript("stopp").returncode, 0)
        sicherung = self.skript("backup").stdout
        datei = sicherung.split("Gesichert: ")[1].split(" (")[0]
        self.assertTrue(os.path.isfile(datei))
        self.assertIn("(Prüfung: ok)", sicherung)
        ziel = os.path.join(self.ordner, "export.json")
        self.assertIn("Exportiert", self.skript("export", ziel).stdout)
        self.assertEqual(os.stat(ziel).st_mode & 0o777, 0o600)  # persönliche Daten: nur für den Benutzer lesbar
        with open(ziel, encoding="utf-8") as f:
            self.assertTrue(json.load(f)["nachrichten"])
        # Daten kaputt machen, dann aus der Sicherung zurückholen
        verbindung = sqlite3.connect(os.path.join(daten, "jarvis.db"))
        verbindung.execute("DELETE FROM nachrichten")
        verbindung.commit()
        verbindung.close()
        wieder = self.skript("wiederherstellen", datei)
        self.assertEqual(wieder.returncode, 0, wieder.stdout)
        self.assertIn("Der bisherige Stand liegt sicher in", wieder.stdout)
        verbindung = sqlite3.connect(os.path.join(daten, "jarvis.db"))
        self.assertGreater(verbindung.execute("SELECT COUNT(*) FROM nachrichten").fetchone()[0], 0)
        verbindung.close()
        kaputt = os.path.join(self.ordner, "kaputt.db")
        with open(kaputt, "w", encoding="utf-8") as f:
            f.write("keine datenbank")
        self.assertEqual(self.skript("wiederherstellen", kaputt).returncode, 1)
        self.assertEqual(self.skript("wiederherstellen", os.path.join(self.ordner, "gibtsnicht.db")).returncode, 1)

    def test_wiederherstellen_nicht_bei_laufendem_server(self):
        try:
            self.assertEqual(self.skript("start").returncode, 0)
            lauf = self.skript("wiederherstellen", os.path.join(self.ordner, "egal.db"))
            self.assertEqual(lauf.returncode, 1)
            self.assertIn("läuft noch", lauf.stdout)
        finally:
            self.skript("stopp")

    def test_befehle_ohne_server(self):
        self.assertEqual(self.skript("notstopp").returncode, 1)
        self.assertEqual(self.skript("frage", "Hallo").returncode, 1)
        self.assertEqual(self.skript("frage").returncode, 2)
        self.assertEqual(self.skript("umgebung").returncode, 0)
        self.assertEqual(self.skript("gibtsnicht").returncode, 2)


def ist_standardbibliothek(name):
    if name in sys.builtin_module_names:
        return True
    spezifikation = importlib.util.find_spec(name)
    if spezifikation is None:
        return False
    if spezifikation.origin in ("built-in", "frozen"):
        return True
    pfade = [spezifikation.origin] if spezifikation.origin else list(spezifikation.submodule_search_locations or [])
    stdlib = [os.path.realpath(sysconfig.get_path(art)) for art in ("stdlib", "platstdlib")]
    for pfad in pfade:
        echt = os.path.realpath(pfad)
        if "site-packages" in echt or "dist-packages" in echt:
            return False
        if not any(echt.startswith(s + os.sep) for s in stdlib):
            return False
    return True


class AbhaengigkeitenTest(unittest.TestCase):
    """Abhängigkeitsprüfung: JARVIS braucht nur Python-Bordmittel - keine Pakete, die sich einschleichen oder veralten."""

    def dateien(self, endungen):
        for ordner, _, namen in os.walk(os.path.join(WURZEL, "jarvis_core")):
            for name in sorted(namen):
                if name.endswith(endungen):
                    yield os.path.join(ordner, name)

    def test_nur_standardbibliothek(self):
        gefunden = {}
        for pfad in self.dateien((".py",)):
            with open(pfad, encoding="utf-8") as f:
                baum = ast.parse(f.read())
            for knoten in ast.walk(baum):
                if isinstance(knoten, ast.Import):
                    namen = [a.name.split(".")[0] for a in knoten.names]
                elif isinstance(knoten, ast.ImportFrom) and knoten.level == 0 and knoten.module:
                    namen = [knoten.module.split(".")[0]]
                else:
                    continue
                for n in namen:
                    gefunden.setdefault(n, os.path.basename(pfad))
        self.assertGreater(len(gefunden), 15)  # die Prüfung hat wirklich etwas gesehen
        fremd = {n: d for n, d in gefunden.items() if not ist_standardbibliothek(n)}
        self.assertEqual(fremd, {}, "Nicht zur Standardbibliothek gehörende Importe: %r" % fremd)

    def test_keine_zugangsdaten_im_code(self):
        for pfad in self.dateien((".py", ".js", ".html", ".css", ".svg")):
            with open(pfad, encoding="utf-8") as f:
                text = f.read()
            for muster in ("sk-ant-", "BEGIN PRIVATE KEY", "api_key=", "password="):
                self.assertNotIn(muster, text, "%s enthält %r" % (pfad, muster))


if __name__ == "__main__":
    unittest.main()
