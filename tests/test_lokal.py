#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Tests für das lokale Gehirn (Ollama) und die Gehirn-Weiche im ProviderManager.

Ein winziger Ersatz-Ollama antwortet auf ``/api/tags`` und ``/api/chat``, damit nichts
Echtes installiert sein muss. Aufruf::

    python3 -m unittest tests.test_lokal -v
"""

import json
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from tests.hilfen import Umgebung, freier_port

from jarvis_core import konfig as konfig_modul  # noqa: E402
from jarvis_core.konfig import KonfigFehler  # noqa: E402
from jarvis_core.protokoll import Protokoll  # noqa: E402
from jarvis_core.provider import ProviderFehler, ProviderManager  # noqa: E402


class OllamaHandler(BaseHTTPRequestHandler):
    """Antwortet wie Ollama - die vorgegebenen Werte stehen am Server."""

    def log_message(self, *a):  # keine Ausgabe im Test
        pass

    def _json(self, obj):
        roh = json.dumps(obj).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(roh)))
        self.end_headers()
        self.wfile.write(roh)

    def do_GET(self):
        if self.path == "/api/tags":
            self._json({"models": [{"name": n} for n in self.server.modelle]})
        else:
            self.send_error(404)

    def do_POST(self):
        laenge = int(self.headers.get("Content-Length") or 0)
        koerper = json.loads(self.rfile.read(laenge).decode("utf-8")) if laenge else {}
        self.server.letzte = koerper
        self._json({"model": koerper.get("model"),
                    "message": {"role": "assistant", "content": self.server.antwort},
                    "prompt_eval_count": 11, "eval_count": 7, "done": True})


class LokalTest(Umgebung):
    def setUp(self):
        super().setUp()
        self.konfig = konfig_modul.laden()
        self.log = Protokoll(self.konfig)
        self.pm = ProviderManager(self.konfig, self.log)
        self._server = None

    def tearDown(self):
        if self._server is not None:
            self._server.shutdown()
            self._server.server_close()
        self.log.schliessen()
        super().tearDown()

    def start_ollama(self, modelle=("testmodell:latest",), antwort="Hallo vom lokalen Modell"):
        port = freier_port()
        server = ThreadingHTTPServer(("127.0.0.1", port), OllamaHandler)
        server.modelle = list(modelle)
        server.antwort = antwort
        server.letzte = None
        threading.Thread(target=server.serve_forever, daemon=True).start()
        self._server = server
        return "http://127.0.0.1:%d" % port

    # --------------------------------------------------------------- Weiche ---

    def test_standard_ist_claude(self):
        self.assertEqual(self.pm._anbieter_fuer("chat").name, "claude_code")
        self.assertEqual(self.konfig.gehirn, "claude")

    def test_lokales_gehirn_umschalten_recherche_bleibt_claude(self):
        self.konfig.aktualisieren({"gehirn": "lokal", "lokales_modell": "testmodell"})
        self.assertEqual(self.pm._anbieter_fuer("chat").name, "lokal")
        self.assertEqual(self.pm._anbieter_fuer("arbeit").name, "lokal")
        self.assertEqual(self.pm._anbieter_fuer("recherche").name, "claude_code")  # Websuche braucht Claude

    # ------------------------------------------------------------- Anfragen ---

    def test_lokales_modell_antwortet_und_bleibt_auf_dem_geraet(self):
        adresse = self.start_ollama()
        self.konfig.aktualisieren({"gehirn": "lokal", "lokales_modell": "testmodell", "ollama_adresse": adresse})
        status = self.pm.pruefen()["lokal"]
        self.assertTrue(status["nutzbar"], status["hinweis"])
        erfasst = []
        self.pm.beobachter = lambda *a: erfasst.append(a)
        erg = self.pm.fragen("Was kostet eine Treppenhausreinigung?", "Du bist JARVIS")
        self.assertEqual(erg["antwort"], "Hallo vom lokalen Modell")
        self.assertEqual(erg["provider"], "lokal")
        self.assertEqual((erg["tokens_ein"], erg["tokens_aus"]), (11, 7))
        self.assertEqual(erfasst[-1][1], "testmodell")  # unter diesem Modellnamen erfasst
        gesendet = self._server.letzte
        self.assertEqual(gesendet["model"], "testmodell")
        self.assertEqual([m["role"] for m in gesendet["messages"]], ["system", "user"])
        self.assertIn("Treppenhausreinigung", gesendet["messages"][1]["content"])

    def test_modell_ohne_tag_passt_auf_geladenes_mit_tag(self):
        adresse = self.start_ollama(modelle=("llama3.1:latest",))
        self.konfig.aktualisieren({"gehirn": "lokal", "lokales_modell": "llama3.1", "ollama_adresse": adresse})
        self.assertTrue(self.pm.pruefen()["lokal"]["nutzbar"])

    def test_fehlendes_modell_gibt_klaren_hinweis(self):
        adresse = self.start_ollama(modelle=("ganz_anderes:latest",))
        self.konfig.aktualisieren({"gehirn": "lokal", "lokales_modell": "testmodell", "ollama_adresse": adresse})
        status = self.pm.pruefen()["lokal"]
        self.assertFalse(status["nutzbar"])
        self.assertIn("ollama pull testmodell", status["hinweis"])

    def test_ollama_nicht_erreichbar_klarer_fehler_statt_absturz(self):
        self.konfig.aktualisieren({"gehirn": "lokal", "lokales_modell": "testmodell",
                                   "ollama_adresse": "http://127.0.0.1:%d" % freier_port()})
        status = self.pm.pruefen()["lokal"]
        self.assertFalse(status["nutzbar"])
        self.assertIn("Ollama", status["hinweis"])
        with self.assertRaises(ProviderFehler) as ctx:
            self.pm.fragen("Hallo", "s")
        self.assertEqual(ctx.exception.art, "kein_provider")

    def test_recherche_laeuft_auch_mit_lokalem_gehirn_ueber_claude(self):
        self.konfig.aktualisieren({"gehirn": "lokal", "lokales_modell": "testmodell"})
        self.drehbuch([{"tools": "WebSearch", "antwort": "Treffer: https://example.com"}])
        erg = self.pm.recherchieren("Handelsregister Muster GmbH")
        self.assertEqual(erg["provider"], "claude_code")
        self.assertIn("example.com", erg["antwort"])

    # ---------------------------------------------------------- Sicherheit ---

    def test_ollama_adresse_muss_lokal_sein(self):
        for adresse in ("http://example.com:11434", "https://127.0.0.1:11434", "http://10.0.0.5:11434"):
            with self.subTest(adresse=adresse), self.assertRaises(KonfigFehler):
                self.konfig.aktualisieren({"ollama_adresse": adresse})

    def test_unbekanntes_gehirn_wird_abgelehnt(self):
        with self.assertRaises(KonfigFehler):
            self.konfig.aktualisieren({"gehirn": "superhirn"})

    def test_notstopp_sperrt_auch_das_lokale_gehirn(self):
        adresse = self.start_ollama()
        self.konfig.aktualisieren({"gehirn": "lokal", "lokales_modell": "testmodell", "ollama_adresse": adresse})
        self.pm.pruefen()
        self.pm.gesperrt.set()
        with self.assertRaises(ProviderFehler) as ctx:
            self.pm.fragen("Hallo", "s")
        self.assertEqual(ctx.exception.art, "gesperrt")


if __name__ == "__main__":
    unittest.main()
