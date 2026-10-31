# -*- coding: utf-8 -*-
"""Gemeinsame Test-Hilfen: eigener Datenordner, freier Port, Ersatz für ``claude`` und ``say``."""

import http.client
import json
import os
import shutil
import socket
import sys
import tempfile
import unittest

WURZEL = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, WURZEL)

ERSATZ_CLAUDE = os.path.join(WURZEL, "tests", "ersatz_claude.py")

ERSATZ_SAY = r"""#!%(python)s
import os, sys
if sys.argv[1:3] == ["-v", "?"]:
    print("Anna                de_DE    # Hallo")
    print("Markus (Premium)    de_DE    # Hallo")
    print("Daniel              en_GB    # Hello")
    sys.exit(0)
log = os.environ.get("SAY_LOG")
daten = sys.stdin.buffer.read().decode("utf-8") if "-f" in sys.argv else ""
if log:
    with open(log, "a") as f:
        f.write(repr(sys.argv[1:]) + "\t" + daten + "\n")
"""

ENV_NAMEN = ("JARVIS_DATEN", "JARVIS_PORT", "JARVIS_LOGSTUFE", "JARVIS_CLAUDE", "JARVIS_MODELL", "JARVIS_SAY",
             "JARVIS_WERKSTATT", "SAY_LOG", "FAKE_DREHBUCH", "FAKE_STAND", "FAKE_PROTOKOLL", "FAKE_AUTH",
             "FAKE_UNBEKANNT", "ANTHROPIC_API_KEY", "CLAUDE_CODE_USE_BEDROCK")


def freier_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def ausfuehrbar(pfad, inhalt):
    with open(pfad, "w", encoding="utf-8") as f:
        f.write(inhalt)
    os.chmod(pfad, 0o755)  # noqa: S103 - Ersatzprogramm muss ausführbar sein


class Umgebung(unittest.TestCase):
    """Jeder Test arbeitet in einem eigenen Ordner mit Ersatz-Claude, Ersatz-say und eigener Werkstatt."""

    def setUp(self):
        self.ordner = tempfile.mkdtemp(prefix="jarvis_t_")
        self.port = freier_port()
        self._alt = {k: os.environ.get(k) for k in ENV_NAMEN}
        for k in ENV_NAMEN:
            os.environ.pop(k, None)
        self.werkstatt = os.path.join(self.ordner, "werkstatt")
        self.aufrufe_datei = os.path.join(self.ordner, "aufrufe.jsonl")
        self.drehbuch_datei = os.path.join(self.ordner, "drehbuch.json")
        self.say = os.path.join(self.ordner, "say-ersatz")
        self.say_log = os.path.join(self.ordner, "say.log")
        ausfuehrbar(self.say, ERSATZ_SAY % {"python": sys.executable})
        os.environ.update({
            "JARVIS_DATEN": os.path.join(self.ordner, "daten"),
            "JARVIS_PORT": str(self.port),
            "JARVIS_CLAUDE": ERSATZ_CLAUDE,
            "JARVIS_SAY": self.say,
            "JARVIS_WERKSTATT": self.werkstatt,
            "SAY_LOG": self.say_log,
            "FAKE_DREHBUCH": self.drehbuch_datei,
            "FAKE_STAND": os.path.join(self.ordner, "stand.json"),
            "FAKE_PROTOKOLL": self.aufrufe_datei,
        })
        os.chmod(ERSATZ_CLAUDE, 0o755)  # noqa: S103 - Ersatzprogramm muss ausführbar sein
        self.drehbuch([])

    def tearDown(self):
        for k, v in self._alt.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        shutil.rmtree(self.ordner, ignore_errors=True)

    def drehbuch(self, regeln):
        with open(self.drehbuch_datei, "w", encoding="utf-8") as f:
            json.dump(regeln, f, ensure_ascii=False)

    def aufrufe(self):
        """Alle bisherigen Aufrufe des Ersatz-Claude (nur echte Anfragen, ohne --version/auth)."""
        try:
            with open(self.aufrufe_datei, "r", encoding="utf-8") as f:
                return [json.loads(z) for z in f]
        except OSError:
            return []

    def http(self, methode, pfad, koerper=None, kopf=None, port=None):
        verbindung = http.client.HTTPConnection("127.0.0.1", port or self.port, timeout=30)
        kopf = dict(kopf or {})
        daten = None
        if koerper is not None:
            daten = koerper if isinstance(koerper, bytes) else json.dumps(koerper).encode("utf-8")
            kopf.setdefault("Content-Type", "application/json")
        verbindung.request(methode, pfad, body=daten, headers=kopf)
        antwort = verbindung.getresponse()
        inhalt = antwort.read()
        kopfzeilen = dict(antwort.getheaders())
        verbindung.close()
        try:
            return antwort.status, json.loads(inhalt.decode("utf-8")), kopfzeilen
        except ValueError:
            return antwort.status, inhalt.decode("utf-8", "replace"), kopfzeilen
