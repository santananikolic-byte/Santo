#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Tests für den JARVIS-Kern: Konfiguration, Logs, Server, Start/Stopp, Claude Code.

Claude Code wird durch ein kleines Ersatzprogramm simuliert (FAKE_MODUS), damit
die Tests kein Abo-Kontingent verbrauchen und jeden Fehlerfall gezielt prüfen.

Aufruf::

    python3 -m unittest tests.test_kern -v

Jeder Test arbeitet in einem eigenen temporären Datenordner und auf einem
freien Port - echte Daten in ~/.jarvis bleiben unangetastet.
"""

import http.client
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import time
import unittest

WURZEL = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, WURZEL)

from jarvis_core import konfig  # noqa: E402
from jarvis_core.protokoll import Protokoll, letzte_eintraege  # noqa: E402
from jarvis_core.server import JarvisServer, PidFehler  # noqa: E402


ERSATZ_CLAUDE = r'''#!/usr/bin/env python3
import json, os, sys, time
modus = os.environ.get("FAKE_MODUS", "ok")
protokoll = os.environ.get("FAKE_PROTOKOLL")
args = sys.argv[1:]
eingabe = "" if args[:1] == ["--version"] or args[:2] == ["auth", "status"] else sys.stdin.read()
if protokoll:
    with open(protokoll, "a") as f:
        f.write(json.dumps({"args": args, "eingabe": eingabe, "cwd": os.getcwd(),
                            "apikey": os.environ.get("ANTHROPIC_API_KEY"),
                            "bedrock": os.environ.get("CLAUDE_CODE_USE_BEDROCK")}) + "\n")
if args[:1] == ["--version"]:
    print("2.1.316 (Claude Code)"); sys.exit(0)
if args[:2] == ["auth", "status"]:
    if modus == "nicht_angemeldet":
        print(json.dumps({"loggedIn": False})); sys.exit(1)
    art = "api_key" if modus == "apikey" else "claude.ai"
    print(json.dumps({"loggedIn": True, "authMethod": art, "subscriptionType": "pro"})); sys.exit(0)
if modus == "limit":
    print(json.dumps({"type": "result", "is_error": True, "result": "Claude AI usage limit reached|1761930000"}))
    sys.exit(1)
if modus == "langsam":
    time.sleep(30)
if modus == "kaputt":
    print("das ist kein json"); sys.exit(1)
sitzung = args[args.index("--resume") + 1] if "--resume" in args else "sitzung-neu"
print(json.dumps({"type": "result", "is_error": False, "session_id": sitzung,
                  "result": "Antwort auf: " + eingabe.strip(), "duration_ms": 1234}))
'''


def freier_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class Grundlage(unittest.TestCase):
    def setUp(self):
        self.ordner = tempfile.mkdtemp(prefix="jarvis_test_")
        self.port = freier_port()
        self._alt = {k: os.environ.get(k) for k in ("JARVIS_DATEN", "JARVIS_PORT", "JARVIS_LOGSTUFE", "JARVIS_CLAUDE", "JARVIS_MODELL",
                                                    "FAKE_MODUS", "FAKE_PROTOKOLL", "ANTHROPIC_API_KEY",
                                                    "CLAUDE_CODE_USE_BEDROCK")}
        os.environ["JARVIS_DATEN"] = self.ordner
        os.environ["JARVIS_PORT"] = str(self.port)
        os.environ.pop("JARVIS_LOGSTUFE", None)
        self.ersatz = os.path.join(self.ordner, "claude-ersatz")
        with open(self.ersatz, "w") as f:
            f.write(ERSATZ_CLAUDE.replace("#!/usr/bin/env python3", "#!" + sys.executable, 1))
        os.chmod(self.ersatz, 0o755)  # noqa: S103 - Ersatzprogramm muss ausführbar sein
        self.aufrufe = os.path.join(self.ordner, "aufrufe.jsonl")
        os.environ["JARVIS_CLAUDE"] = self.ersatz
        os.environ["FAKE_PROTOKOLL"] = self.aufrufe
        os.environ["FAKE_MODUS"] = "ok"
        os.environ.pop("JARVIS_MODELL", None)

    def tearDown(self):
        for k, v in self._alt.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        shutil.rmtree(self.ordner, ignore_errors=True)


class KonfigTest(Grundlage):
    def test_legt_standarddatei_an(self):
        k = konfig.laden()
        self.assertTrue(os.path.exists(k.datei))
        self.assertEqual(k.host, "127.0.0.1")
        self.assertEqual(k.port, self.port)  # Umgebungsvariable geht vor

    def test_fremde_adresse_wird_abgelehnt(self):
        with open(os.path.join(self.ordner, "config.json"), "w") as f:
            json.dump({"host": "0.0.0.0"}, f)
        with self.assertRaises(konfig.KonfigFehler):
            konfig.laden()

    def test_ungueltiger_port(self):
        os.environ["JARVIS_PORT"] = "abc"
        with self.assertRaises(konfig.KonfigFehler):
            konfig.laden()
        os.environ["JARVIS_PORT"] = "80"
        with self.assertRaises(konfig.KonfigFehler):
            konfig.laden()

    def test_kaputte_datei(self):
        with open(os.path.join(self.ordner, "config.json"), "w") as f:
            f.write("{kein json")
        with self.assertRaises(konfig.KonfigFehler):
            konfig.laden()

    def test_unbekannte_logstufe(self):
        os.environ["JARVIS_LOGSTUFE"] = "laut"
        with self.assertRaises(konfig.KonfigFehler):
            konfig.laden()

    def test_modell_einstellbar(self):
        os.environ["JARVIS_MODELL"] = "sonnet"
        self.assertEqual(konfig.laden().modell, "sonnet")
        os.environ["JARVIS_MODELL"] = ""  # leer = Claude-Code-Standard
        self.assertEqual(konfig.laden().modell, "")
        os.environ["JARVIS_MODELL"] = "böse; rm -rf"
        with self.assertRaises(konfig.KonfigFehler):
            konfig.laden()


class ProtokollTest(Grundlage):
    def test_json_zeilen(self):
        k = konfig.laden()
        log = Protokoll(k)
        log.ereignis("test_ereignis", wert=42, text="Grüße")
        log.schliessen()
        eintraege = letzte_eintraege(k.log_datei)
        self.assertEqual(eintraege[-1]["ereignis"], "test_ereignis")
        self.assertEqual(eintraege[-1]["wert"], 42)
        self.assertEqual(eintraege[-1]["text"], "Grüße")
        self.assertIn("zeit", eintraege[-1])
        self.assertEqual(eintraege[-1]["stufe"], "INFO")

    def test_defekte_zeilen_werden_uebersprungen(self):
        k = konfig.laden()
        os.makedirs(k.log_ordner, exist_ok=True)
        with open(k.log_datei, "w", encoding="utf-8") as f:
            f.write('{"ereignis": "a"}\nkaputt\n{"ereignis": "b"}\n')
        self.assertEqual([e["ereignis"] for e in letzte_eintraege(k.log_datei)], ["a", "b"])


class ServerTest(Grundlage):
    def setUp(self):
        super().setUp()
        self.k = konfig.laden()
        self.log = Protokoll(self.k)
        self.server = JarvisServer(self.k, self.log)
        self.faden = threading.Thread(target=self.server.starten, kwargs={"signale": False}, daemon=True)
        self.faden.start()
        for _ in range(100):
            if self.server.bereit():
                break
            time.sleep(0.02)

    def tearDown(self):
        self.server.stoppen()
        self.faden.join(timeout=5)
        self.log.schliessen()
        super().tearDown()

    def anfrage(self, methode, pfad, koerper=None, kopf=None):
        verbindung = http.client.HTTPConnection("127.0.0.1", self.port, timeout=5)
        kopf = dict(kopf or {})
        daten = None
        if koerper is not None:
            daten = koerper if isinstance(koerper, bytes) else json.dumps(koerper).encode("utf-8")
            kopf.setdefault("Content-Type", "application/json")
        verbindung.request(methode, pfad, body=daten, headers=kopf)
        antwort = verbindung.getresponse()
        inhalt = antwort.read()
        verbindung.close()
        try:
            return antwort.status, json.loads(inhalt.decode("utf-8"))
        except ValueError:
            return antwort.status, inhalt.decode("utf-8")

    def test_status(self):
        code, s = self.anfrage("GET", "/status")
        self.assertEqual(code, 200)
        self.assertTrue(s["laeuft"])
        self.assertEqual(s["adresse"], "http://127.0.0.1:%d" % self.port)
        self.assertEqual(s["phase"], 3)
        self.assertIn("claude_code", s["provider"])
        self.assertIn("BRAIN.md", s["wissen"])

    def test_statusseite(self):
        code, seite = self.anfrage("GET", "/")
        self.assertEqual(code, 200)
        self.assertIn("JARVIS", seite)
        self.assertIn("läuft", seite)

    def aufrufe_lesen(self):
        with open(self.aufrufe) as f:
            return [json.loads(z) for z in f]

    def test_anfrage_wird_beantwortet_und_protokolliert(self):
        os.environ["ANTHROPIC_API_KEY"] = "sk-darf-nicht-weitergegeben-werden"
        os.environ["CLAUDE_CODE_USE_BEDROCK"] = "1"
        code, a = self.anfrage("POST", "/api/anfrage", {"text": "Prüfe die Muster GmbH"})
        self.assertEqual(code, 200, a)
        self.assertTrue(a["ok"])
        self.assertEqual(a["antwort"], "Antwort auf: Prüfe die Muster GmbH")
        self.assertEqual(a["provider"], "claude_code")
        _, s = self.anfrage("GET", "/status")
        self.assertEqual(s["anfragen"], 1)
        eintraege = letzte_eintraege(self.k.log_datei)
        self.assertTrue(any(e["ereignis"] == "anfrage_beantwortet" and e["id"] == a["id"] for e in eintraege))
        frage = [x for x in self.aufrufe_lesen() if "-p" in x["args"]][-1]
        # Keine bezahlte Abrechnung, keine Werkzeuge, eigener Arbeitsordner, Wissen im Systemprompt.
        self.assertIsNone(frage["apikey"])
        self.assertIsNone(frage["bedrock"])
        self.assertEqual(frage["args"][frage["args"].index("--tools") + 1], "")
        self.assertEqual(os.path.realpath(frage["cwd"]), os.path.realpath(self.ordner))
        system = frage["args"][frage["args"].index("--system-prompt") + 1]
        self.assertIn("Du bist JARVIS", system)
        self.assertIn("===== BRAIN.md =====", system)
        self.assertEqual(frage["eingabe"], "Prüfe die Muster GmbH")

    def test_gespraech_wird_fortgesetzt(self):
        _, a = self.anfrage("POST", "/api/anfrage", {"text": "Hallo"})
        self.assertNotIn("--resume", [x for x in self.aufrufe_lesen() if "-p" in x["args"]][-1]["args"])
        _, b = self.anfrage("POST", "/api/anfrage", {"text": "Und weiter?", "gespraech": a["gespraech"]})
        self.assertEqual(b["gespraech"], a["gespraech"])
        letzte = [x for x in self.aufrufe_lesen() if "-p" in x["args"]][-1]["args"]
        self.assertEqual(letzte[letzte.index("--resume") + 1], "sitzung-neu")
        with open(os.path.join(self.ordner, "gespraeche.json")) as f:
            self.assertIn(a["gespraech"], json.load(f))
        self.assertEqual(self.anfrage("POST", "/api/anfrage", {"text": "x", "gespraech": "../boese"})[0], 400)

    def test_fehlerfaelle_von_claude(self):
        faelle = [("nicht_angemeldet", 503, "nicht angemeldet"), ("apikey", 503, "kosten"),
                  ("limit", 429, "Limit"), ("kaputt", 502, "Claude Code meldet")]
        for modus, code_soll, text_soll in faelle:
            with self.subTest(modus=modus):
                os.environ["FAKE_MODUS"] = modus
                self.server.provider.pruefen()
                fragen_vorher = len([x for x in self.aufrufe_lesen() if "-p" in x["args"]])
                code, a = self.anfrage("POST", "/api/anfrage", {"text": "Hallo"})
                self.assertEqual(code, code_soll, a)
                self.assertFalse(a["ok"])
                self.assertIn(text_soll, a["fehler"])
                fragen_nachher = len([x for x in self.aufrufe_lesen() if "-p" in x["args"]])
                if modus in ("nicht_angemeldet", "apikey"):
                    # Ohne Abo-Anmeldung wird Claude gar nicht erst gefragt - es entstehen keine Kosten.
                    self.assertEqual(fragen_nachher, fragen_vorher)

    def test_nicht_installiert(self):
        os.environ["JARVIS_CLAUDE"] = os.path.join(self.ordner, "gibt-es-nicht")
        status = self.server.provider.pruefen()
        self.assertFalse(status["claude_code"]["installiert"])
        self.assertIn("install.sh", status["claude_code"]["hinweis"])
        code, a = self.anfrage("POST", "/api/anfrage", {"text": "Hallo"})
        self.assertEqual(code, 503)
        self.assertIn("nicht installiert", a["fehler"])

    def test_zeitueberschreitung(self):
        self.server.provider.claude.timeout = 1
        os.environ["FAKE_MODUS"] = "langsam"
        start = time.time()
        code, a = self.anfrage("POST", "/api/anfrage", {"text": "Hallo"})
        self.assertEqual(code, 504, a)
        self.assertLess(time.time() - start, 10)

    def test_nur_claude_code(self):
        status = self.server.provider.pruefen()
        self.assertEqual(list(status.keys()), ["claude_code"])

    def test_modell_wird_mitgegeben(self):
        os.environ["JARVIS_MODELL"] = "opus"
        self.server.provider.claude.modell = "opus"
        self.anfrage("POST", "/api/anfrage", {"text": "Hallo"})
        args = [x for x in self.aufrufe_lesen() if "-p" in x["args"]][-1]["args"]
        self.assertEqual(args[args.index("--model") + 1], "opus")

    def test_fehlerhafte_eingaben(self):
        self.assertEqual(self.anfrage("POST", "/api/anfrage", {"text": "   "})[0], 400)
        self.assertEqual(self.anfrage("POST", "/api/anfrage", {"etwas": "anderes"})[0], 400)
        self.assertEqual(self.anfrage("POST", "/api/anfrage", ["liste"])[0], 400)
        self.assertEqual(self.anfrage("POST", "/api/anfrage", b"{kaputt")[0], 400)
        self.assertEqual(self.anfrage("POST", "/api/anfrage", {"text": "x" * 10001})[0], 413)
        self.assertEqual(self.anfrage("POST", "/api/anfrage", b"text=x",
                                      {"Content-Type": "application/x-www-form-urlencoded"})[0], 415)
        self.assertEqual(self.anfrage("POST", "/api/unbekannt", {"text": "x"})[0], 404)
        self.assertEqual(self.anfrage("GET", "/gibtsnicht")[0], 404)
        self.assertEqual(self.anfrage("GET", "/api/logs?anzahl=abc")[0], 400)

    def test_fremder_host_wird_abgelehnt(self):
        code, a = self.anfrage("GET", "/status", kopf={"Host": "angreifer.example:%d" % self.port})
        self.assertEqual(code, 403)
        code, _ = self.anfrage("POST", "/api/anfrage", {"text": "x"}, kopf={"Host": "angreifer.example"})
        self.assertEqual(code, 403)

    def test_fremde_webseite_wird_abgelehnt(self):
        code, _ = self.anfrage("POST", "/api/anfrage", {"text": "x"}, kopf={"Origin": "https://boese.example"})
        self.assertEqual(code, 403)
        code, _ = self.anfrage("POST", "/api/anfrage", {"text": "x"},
                               kopf={"Origin": "http://127.0.0.1:%d" % self.port})
        self.assertEqual(code, 200)
        code, _ = self.anfrage("POST", "/api/provider/pruefen", kopf={"Origin": "https://boese.example"})
        self.assertEqual(code, 403)

    def test_logs_endpunkt(self):
        code, a = self.anfrage("GET", "/api/logs?anzahl=5")
        self.assertEqual(code, 200)
        self.assertTrue(any(e["ereignis"] == "server_gestartet" for e in a["eintraege"]))

    def test_zweiter_start_wird_verhindert(self):
        zweiter = JarvisServer(self.k, self.log)
        with open(self.k.pid_datei, "w") as f:
            f.write(str(os.getppid()))  # ein Prozess, der sicher läuft
        with self.assertRaises(PidFehler):
            zweiter.starten(signale=False)


class SkriptTest(Grundlage):
    """Start und Stopp über ./jarvis.sh - als echter Hintergrundprozess."""

    def skript(self, *args):
        umgebung = dict(os.environ, JARVIS_PYTHON=sys.executable)
        return subprocess.run([os.path.join(WURZEL, "jarvis.sh")] + list(args), capture_output=True,
                              text=True, timeout=30, env=umgebung)

    def test_start_status_stopp(self):
        try:
            lauf = self.skript("start")
            self.assertEqual(lauf.returncode, 0, lauf.stdout + lauf.stderr)
            self.assertIn("JARVIS läuft", lauf.stdout)
            self.assertIn("JARVIS läuft schon", self.skript("start").stdout)
            status = self.skript("status")
            self.assertEqual(status.returncode, 0)
            self.assertIn("Anfragen", status.stdout)
            self.assertIn("server_gestartet", self.skript("logs", "5").stdout)
        finally:
            stopp = self.skript("stopp")
        self.assertIn("gestoppt", stopp.stdout)
        self.assertEqual(self.skript("status").returncode, 1)
        self.assertFalse(os.path.exists(os.path.join(self.ordner, "jarvis.pid")))
        self.assertIn("server_gestoppt", self.skript("logs", "5").stdout)

    def test_stopp_ohne_server(self):
        self.assertIn("läuft nicht", self.skript("stopp").stdout)

    def test_veraltete_pid_datei_beendet_keinen_fremden_prozess(self):
        fremd = subprocess.Popen(["sleep", "30"])
        try:
            with open(os.path.join(self.ordner, "jarvis.pid"), "w") as f:
                f.write(str(fremd.pid))
            self.assertIn("läuft nicht", self.skript("stopp").stdout)
            self.assertIsNone(fremd.poll(), "fremder Prozess wurde beendet")
            self.assertFalse(os.path.exists(os.path.join(self.ordner, "jarvis.pid")))
        finally:
            fremd.kill()
            fremd.wait()

    def test_fremdes_programm_auf_dem_port(self):
        import http.server

        class Fremd(http.server.BaseHTTPRequestHandler):
            def do_GET(self):
                koerper = b'{"name": "etwas anderes"}'
                self.send_response(200)
                self.send_header("Content-Length", str(len(koerper)))
                self.end_headers()
                self.wfile.write(koerper)

            def log_message(self, *args):
                pass

        fremd = http.server.HTTPServer(("127.0.0.1", self.port), Fremd)
        threading.Thread(target=fremd.serve_forever, daemon=True).start()
        try:
            status = self.skript("status")
            self.assertEqual(status.returncode, 1)
            self.assertIn("läuft nicht", status.stdout)
            self.assertNotIn("Traceback", status.stderr)
            lauf = self.skript("start")
            self.assertEqual(lauf.returncode, 1)
            self.assertIn("nicht gestartet", lauf.stdout)
        finally:
            fremd.shutdown()
            fremd.server_close()

    def test_belegter_port(self):
        with socket.socket() as belegt:
            belegt.bind(("127.0.0.1", self.port))
            belegt.listen(1)
            lauf = self.skript("start")
        self.assertEqual(lauf.returncode, 1)
        self.assertIn("nicht gestartet", lauf.stdout)
        self.assertFalse(os.path.exists(os.path.join(self.ordner, "jarvis.pid")))


if __name__ == "__main__":
    unittest.main()
