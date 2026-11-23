# -*- coding: utf-8 -*-
"""Dauerbetrieb auf dem Mac: der LaunchAgent (plist) wird vollständig, gültig und nur für den eigenen Benutzer
lesbar geschrieben. Ob macOS (launchd) ihn so lädt, lässt sich hier nicht prüfen – das bleibt NICHT VERIFIZIERT."""

import os
import plistlib
import stat
import subprocess
import sys
import tempfile
import unittest

from autonomous import autostart

PROJEKT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class TestPlist(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.ziel = PROJEKT  # ein echter Installationsordner (enthält autonomous/__main__.py)
        self.python = sys.executable

    def tearDown(self):
        self.tmp.cleanup()

    def test_inhalt(self):
        p = autostart.plist_daten(self.python, self.ziel)
        log = os.path.join(self.ziel, "autonomous", "daten", "server.log")
        self.assertEqual(p["Label"], "de.autonomous.server")
        self.assertEqual(p["ProgramArguments"], [self.python, "-m", "autonomous", "start"])
        self.assertEqual(p["WorkingDirectory"], self.ziel)
        self.assertIs(p["RunAtLoad"], True)
        self.assertEqual(p["KeepAlive"], {"SuccessfulExit": False})   # nur nach Absturz neu starten
        self.assertEqual((p["StandardOutPath"], p["StandardErrorPath"]), (log, log))
        self.assertEqual(p["Umask"], 0o077)
        self.assertEqual(p["EnvironmentVariables"]["PYTHONIOENCODING"], "utf-8")
        self.assertNotIn("AUTONOMOUS_PORT", p["EnvironmentVariables"])

    def test_port_nur_wenn_angegeben_und_gueltig(self):
        self.assertEqual(autostart.plist_daten(self.python, self.ziel, 8771)["EnvironmentVariables"]["AUTONOMOUS_PORT"],
                         "8771")
        for falsch in (0, 70000, "abc"):
            with self.assertRaises(ValueError):
                autostart.plist_daten(self.python, self.ziel, falsch)

    def test_nur_absolute_pfade_und_echter_installationsordner(self):
        with self.assertRaises(ValueError):
            autostart.plist_daten("python3", self.ziel)
        with self.assertRaises(ValueError):
            autostart.plist_daten(self.python, "AUTONOMOUS")
        with self.assertRaises(ValueError):
            autostart.plist_daten(self.python, self.tmp.name)                  # kein AUTONOMOUS darin
        with self.assertRaises(ValueError):
            autostart.plist_daten(os.path.join(self.tmp.name, "gibtsnicht"), self.ziel)

    def test_schreiben_gueltig_und_nur_fuer_mich(self):
        pfad = os.path.join(self.tmp.name, "Library", "LaunchAgents", "de.autonomous.server.plist")
        autostart.schreiben(pfad, self.python, self.ziel)
        with open(pfad, "rb") as f:
            roh = f.read()
        self.assertIn(b"<!DOCTYPE plist", roh)
        self.assertEqual(plistlib.loads(roh), autostart.plist_daten(self.python, self.ziel))
        self.assertEqual(stat.S_IMODE(os.stat(pfad).st_mode) & 0o077, 0)
        autostart.schreiben(pfad, self.python, self.ziel, 8771)              # überschreiben (Aktualisierung)
        with open(pfad, "rb") as f:
            self.assertEqual(plistlib.load(f)["EnvironmentVariables"]["AUTONOMOUS_PORT"], "8771")
        self.assertEqual(os.listdir(os.path.dirname(pfad)), ["de.autonomous.server.plist"])  # keine Reste

    def test_kommandozeile(self):
        pfad = os.path.join(self.tmp.name, "agent.plist")
        umgebung = dict(os.environ, AUTONOMOUS_PORT="8772")
        r = subprocess.run([sys.executable, "-m", "autonomous.autostart", "schreiben", self.python, self.ziel, pfad],
                           cwd=PROJEKT, env=umgebung, capture_output=True, text=True, timeout=60)
        self.assertEqual(r.returncode, 0, r.stderr)
        with open(pfad, "rb") as f:
            p = plistlib.load(f)
        self.assertEqual(p["EnvironmentVariables"]["AUTONOMOUS_PORT"], "8772")
        self.assertEqual(p["WorkingDirectory"], self.ziel)
        falsch = subprocess.run([sys.executable, "-m", "autonomous.autostart", "schreiben", "python3", self.ziel, pfad],
                                cwd=PROJEKT, capture_output=True, text=True, timeout=60)
        self.assertNotEqual(falsch.returncode, 0)
        self.assertIn("absolut", falsch.stdout + falsch.stderr)


if __name__ == "__main__":
    unittest.main()
