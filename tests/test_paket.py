#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Tests für das Mac-Paket (jarvis-mac.zip): Inhalt, Rechte, kein Schlüssel, und der Doppelklick selbst.

Das Paket wird in einen leeren Ordner gebaut und entpackt, dann laufen JARVIS.command,
EXTRAS.command und JARVIS-BEENDEN.command wie auf dem Mac - mit Ersatz-Claude. Aufruf::

    python3 -m unittest tests.test_paket -v
"""

import importlib.util
import os
import stat
import subprocess
import sys
import unittest
import zipfile

from tests.hilfen import WURZEL, Umgebung, ausfuehrbar

PFLICHT = ("ANLEITUNG.txt", "README.md", "JARVIS.command", "JARVIS-BEENDEN.command", "EXTRAS.command",
           "RECHTE_SETZEN.command", "Preisrechner.html", "BRAIN.md", "config/LIES-MICH.txt", "docs/STATUS.md",
           "jarvis.sh", "VERSION.txt", "jarvis_core/__main__.py", "jarvis_core/oberflaeche/index.html")


def _bauen_modul():
    spec = importlib.util.spec_from_file_location("paket_bauen", os.path.join(WURZEL, "mac-paket", "bauen.py"))
    modul = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modul)
    return modul


class PaketTest(Umgebung):
    def setUp(self):
        super().setUp()
        self.bauen = _bauen_modul()
        self.zip = os.path.join(self.ordner, "jarvis-mac.zip")
        self.bauen.bauen(self.zip)
        with zipfile.ZipFile(self.zip) as z:
            z.extractall(os.path.join(self.ordner, "entpackt"))
            for info in z.infolist():  # zipfile setzt die Rechte nicht selbst - so wie das Archivprogramm des Macs
                os.chmod(os.path.join(self.ordner, "entpackt", info.filename), (info.external_attr >> 16) & 0o777)
        self.paket = os.path.join(self.ordner, "entpackt", "jarvis-mac")
        # Ein Ersatz für curl: merkt sich jeden Aufruf. So sieht der Test, ob ohne Ja etwas installiert würde.
        self.bin = os.path.join(self.ordner, "bin")
        os.makedirs(self.bin)
        self.curl_spur = os.path.join(self.ordner, "curl-aufgerufen")
        ausfuehrbar(os.path.join(self.bin, "curl"), "#!/bin/sh\ntouch '%s'\nexit 1\n" % self.curl_spur)
        os.environ["JARVIS_OHNE_PAUSE"] = "1"

    def tearDown(self):
        self.lauf("JARVIS-BEENDEN.command")
        for name in ("JARVIS_OHNE_PAUSE", "JARVIS_PYTHON", "JARVIS_PAKET"):
            os.environ.pop(name, None)
        super().tearDown()

    def lauf(self, datei, eingabe="", **zusatz):
        umgebung = dict(os.environ, PATH=self.bin + os.pathsep + os.environ.get("PATH", ""), JARVIS_PYTHON=sys.executable)
        umgebung.update(zusatz)
        return subprocess.run([os.path.join(self.paket, datei)], capture_output=True, text=True, timeout=120,  # noqa: S603 - eigene Paketdatei
                              env=umgebung, input=eingabe, cwd=self.ordner)

    # ------------------------------------------------------------ Inhalt ---

    def test_inhalt_rechte_und_nichts_geheimes(self):
        with zipfile.ZipFile(self.zip) as z:
            namen = z.namelist()
        self.assertTrue(all(n.startswith("jarvis-mac/") for n in namen))  # ein Ordner, nichts verstreut
        for datei in PFLICHT:
            self.assertIn("jarvis-mac/" + datei, namen)
        for n in namen:
            self.assertNotIn("__pycache__", n)
            self.assertFalse(n.endswith((".pyc", ".db", ".env")), n)
            self.assertNotIn("jarvis.py", os.path.basename(n))  # die alte Fassung mit API-Schlüssel kommt nicht mit
        for datei in ("JARVIS.command", "EXTRAS.command", "JARVIS-BEENDEN.command", "RECHTE_SETZEN.command", "jarvis.sh"):
            self.assertTrue(os.stat(os.path.join(self.paket, datei)).st_mode & stat.S_IXUSR, datei)
        with open(os.path.join(self.paket, "ANLEITUNG.txt"), "rb") as f:
            self.assertTrue(f.read().startswith(b"\xef\xbb\xbf"))  # TextEdit liest die Umlaute sicher
        with open(os.path.join(self.paket, "README.md"), encoding="utf-8") as f:
            self.assertNotIn("sk-ant-", f.read())

    def test_bauen_bricht_bei_schluessel_oder_datenbank_ab(self):
        with self.assertRaises(self.bauen.BauFehler):
            self.bauen._pruefen("notiz.txt", b"ANTHROPIC_API_KEY=sk-ant-" + b"a" * 40)
        with self.assertRaises(self.bauen.BauFehler):
            self.bauen._pruefen("jarvis.db", b"")

    # -------------------------------------------------------- Doppelklick ---

    def test_doppelklick_startet_und_beendet(self):
        start = self.lauf("JARVIS.command")
        self.assertEqual(start.returncode, 0, start.stdout + start.stderr)
        self.assertIn("Gehirn: Claude über dein Abo", start.stdout)
        self.assertIn("Fertig. Der Leitstand ist im Browser offen.", start.stdout)
        self.assertNotIn("./jarvis.sh oeffnen", start.stdout)  # im Paket keine Terminal-Befehle als Hinweis
        code, status, _ = self.http("GET", "/status")
        self.assertEqual((code, status["laeuft"]), (200, True))
        nochmal = self.lauf("JARVIS.command")
        self.assertIn("läuft schon", nochmal.stdout)
        check = self.lauf("EXTRAS.command", eingabe="2\n")
        self.assertIn("Systemcheck", check.stdout)
        self.assertIn("Alles bereit", check.stdout)
        notstopp = self.lauf("EXTRAS.command", eingabe="9\n")
        self.assertIn("EXTRAS.command → 0", notstopp.stdout)
        self.lauf("EXTRAS.command", eingabe="0\n")
        ende = self.lauf("JARVIS-BEENDEN.command")
        self.assertIn("gestoppt", ende.stdout)
        self.assertFalse(os.path.exists(self.curl_spur))

    def test_ohne_claude_kein_installieren_ohne_ja_und_ehrliche_meldung(self):
        lauf = self.lauf("JARVIS.command", eingabe="n\n", JARVIS_CLAUDE=os.path.join(self.ordner, "gibtsnicht"))
        self.assertEqual(lauf.returncode, 0, lauf.stdout + lauf.stderr)
        self.assertFalse(os.path.exists(self.curl_spur), "ohne Ja darf nichts installiert werden")
        self.assertIn("Claude Code fehlt noch", lauf.stdout)
        self.assertIn("kein API-Schlüssel", lauf.stdout)
        self.assertIn("claude.ai/install.sh", lauf.stdout)  # die Lösung steht dabei
        self.assertIn("kann noch nicht alles", lauf.stdout)
        self.assertNotIn("Fertig.", lauf.stdout)  # nicht geschönt
        self.assertIn("EXTRAS.command → 2", lauf.stdout)

    def test_mit_ja_wird_die_offizielle_installation_versucht(self):
        lauf = self.lauf("JARVIS.command", eingabe="\n", JARVIS_CLAUDE=os.path.join(self.ordner, "gibtsnicht"))
        self.assertTrue(os.path.exists(self.curl_spur))  # Enter = ja: erst dann wird installiert
        self.assertEqual(lauf.returncode, 0, lauf.stdout + lauf.stderr)

    def test_nicht_angemeldet_fragt_und_zeigt_den_weg(self):
        lauf = self.lauf("JARVIS.command", eingabe="n\n", FAKE_AUTH="aus")
        self.assertIn("noch nicht mit deinem Claude-Abo verbunden", lauf.stdout)
        self.assertIn("EXTRAS.command → 3", lauf.stdout)
        self.assertIn("claude auth login --claudeai", lauf.stdout)

    def test_ohne_python_klarer_hinweis(self):
        lauf = self.lauf("JARVIS.command", JARVIS_PYTHON=os.path.join(self.ordner, "kein-python"))
        self.assertEqual(lauf.returncode, 0)
        self.assertIn("Python fehlt noch", lauf.stdout)
        self.assertIn("NICHT die große Xcode-App", lauf.stdout)


if __name__ == "__main__":
    unittest.main()
