# -*- coding: utf-8 -*-
"""Einrichtung mit einer Zeile und Dauerbetrieb wie auf dem Mac – mit SIMULIERTEM launchctl.

Hier läuft Linux: launchctl/launchd gibt es nicht. Ein kleines Ersatzprogramm (unten) spielt launchd nach: es liest
die echte plist mit plistlib, startet ProgramArguments im WorkingDirectory mit Umask und Umgebung und leitet die
Ausgabe in StandardOutPath. Geprüft werden damit die echten Skripte (Einrichtung, starten, stoppen, Autostart aus),
der echte Download-/Entpack-Weg (ZIP über HTTP auf 127.0.0.1) und der echte Server. Ob macOS die plist genauso
behandelt (Neustart nach Absturz, Start bei der Anmeldung), bleibt NICHT VERIFIZIERT.

Nie auf einem echten Mac ausführen (dort würde launchctl echt sein) – darum dort übersprungen.
"""

import functools
import http.server
import json
import os
import plistlib
import shutil
import socket
import stat
import subprocess
import sys
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.request
import zipfile

PROJEKT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
LABEL = "de.autonomous.server"
OEFFNER = urllib.request.build_opener(urllib.request.ProxyHandler({}))

ERSATZ_LAUNCHCTL = r'''#!%(python)s
# SIMULATION von launchctl für Tests unter Linux – kein echtes launchd.
import json, os, plistlib, signal, subprocess, sys, time
ordner = os.environ["FAKE_LAUNCHD"]
os.makedirs(ordner, exist_ok=True)
with open(os.path.join(ordner, "aufrufe.log"), "a") as f:
    f.write(" ".join(sys.argv[1:]) + "\n")
def datei(label):
    return os.path.join(ordner, label + ".json")
def laeuft(pid):
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    try:
        with open("/proc/%%d/stat" %% pid) as f:
            return f.read().split(")")[-1].split()[0] != "Z"
    except OSError:
        return True
def starten(p):
    umask = p.get("Umask", 0o022)
    alt = os.umask(umask)
    log = os.open(p["StandardOutPath"], os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o666)
    os.umask(alt)
    umgebung = dict(os.environ)
    umgebung.update(p.get("EnvironmentVariables", {}))
    return subprocess.Popen(p["ProgramArguments"], cwd=p["WorkingDirectory"], env=umgebung,
                            stdin=subprocess.DEVNULL, stdout=log, stderr=log, start_new_session=True,
                            preexec_fn=lambda: os.umask(umask)).pid
a = sys.argv[1:]
domaene = "gui/%%d" %% os.getuid()
if a[:1] == ["bootstrap"] and len(a) == 3 and a[1] == domaene:
    with open(a[2], "rb") as f:
        p = plistlib.load(f)
    if os.path.exists(datei(p["Label"])):
        print("Bootstrap failed: 5: Input/output error", file=sys.stderr)
        sys.exit(5)
    pid = starten(p) if p.get("RunAtLoad") else None
    with open(datei(p["Label"]), "w") as f:
        json.dump({"pid": pid, "plist": a[2], "daten": p}, f)
    sys.exit(0)
if a[:1] == ["kickstart"] and len(a) == 2 and a[1].startswith(domaene + "/"):
    label = a[1].split("/")[-1]
    if not os.path.exists(datei(label)):
        sys.exit(113)
    with open(datei(label)) as f:
        z = json.load(f)
    if not (z["pid"] and laeuft(z["pid"])):
        z["pid"] = starten(z["daten"])
        with open(datei(label), "w") as f:
            json.dump(z, f)
    sys.exit(0)
if a[:1] == ["bootout"] and len(a) == 2 and a[1].startswith(domaene + "/"):
    label = a[1].split("/")[-1]
    if not os.path.exists(datei(label)):
        print("Boot-out failed: 3: No such process", file=sys.stderr)
        sys.exit(3)
    with open(datei(label)) as f:
        pid = json.load(f)["pid"]
    if pid and laeuft(pid):
        os.kill(pid, signal.SIGTERM)
        for _ in range(200):
            if not laeuft(pid):
                break
            time.sleep(0.1)
        else:
            os.kill(pid, signal.SIGKILL)
    os.remove(datei(label))
    sys.exit(0)
if a[:1] == ["print"] and len(a) == 2:
    sys.exit(0 if os.path.exists(datei(a[1].split("/")[-1])) else 113)
print("Ersatz-launchctl: unbekannter Aufruf", a, file=sys.stderr)
sys.exit(64)
'''

ERSATZ_OPEN = '''#!/bin/sh
echo "$1" >> "$FAKE_LAUNCHD/open.log"
'''


def _freier_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


KI_SKRIPT = "autonomous-ki-einrichten.sh"
ERSATZ_KI = """#!/bin/bash
# Ersatz für die KI-Einrichtung (nur Test): Aufruf und Ordner merken
echo "KI-Einrichtung aufgerufen in $(pwd)" > "$HOME/ki-aufgerufen.txt"
"""


def _zip_wie_github(ziel_zip, ki_skript=None):
    """ZIP wie von GitHub (codeload): ein Oberordner, darin der Stand dieses Arbeitsordners – ohne Daten.
    Die echte KI-Einrichtung kommt nie hinein (sie könnte Modelle laden); auf Wunsch ein harmloser Ersatz."""
    oben = "Santo-claude-elegant-meitner-ho9kqz/"
    with zipfile.ZipFile(ziel_zip, "w", zipfile.ZIP_DEFLATED) as z:
        for name in os.listdir(PROJEKT):
            if name.endswith((".command", ".sh")) and name != KI_SKRIPT:
                z.write(os.path.join(PROJEKT, name), oben + name)
        if ki_skript:
            info = zipfile.ZipInfo(oben + KI_SKRIPT)
            info.external_attr = 0o755 << 16
            z.writestr(info, ki_skript)
        for wurzel, ordner, dateien in os.walk(os.path.join(PROJEKT, "autonomous")):
            ordner[:] = [o for o in ordner if o not in ("daten", "__pycache__")]
            for d in dateien:
                if not d.endswith(".pyc"):
                    pfad = os.path.join(wurzel, d)
                    z.write(pfad, oben + os.path.relpath(pfad, PROJEKT))


class _StillerHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *a):
        pass


@unittest.skipIf(sys.platform == "darwin", "auf einem echten Mac nicht mit Ersatz-launchctl prüfen")
@unittest.skipUnless(shutil.which("bash") and shutil.which("curl"), "bash und curl nötig")
class TestMacEinrichtung(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp(prefix="autonomous-mac-")
        web = os.path.join(cls.tmp, "web")
        os.makedirs(web)
        _zip_wie_github(os.path.join(web, "autonomous.zip"))
        _zip_wie_github(os.path.join(web, "mit-ki.zip"), ERSATZ_KI)
        handler = functools.partial(_StillerHandler, directory=web)
        cls.web = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
        threading.Thread(target=cls.web.serve_forever, daemon=True).start()
        with open(os.path.join(PROJEKT, "autonomous-einrichten.sh"), encoding="utf-8") as f:
            skript = f.read()
        zeile = [z for z in skript.splitlines() if z.strip().startswith("ZIP_URL=")]
        assert len(zeile) == 1, "ZIP_URL-Zeile nicht gefunden"
        for attr, zip_name in (("einrichten", "autonomous.zip"), ("einrichten_ki", "mit-ki.zip")):
            pfad = os.path.join(cls.tmp, attr + ".sh")
            with open(pfad, "w", encoding="utf-8") as f:
                f.write(skript.replace(zeile[0], '    ZIP_URL="http://127.0.0.1:%d/%s"' % (cls.web.server_address[1], zip_name)))
            setattr(cls, attr, pfad)

    @classmethod
    def tearDownClass(cls):
        cls.web.shutdown()
        cls.web.server_close()
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def neue_umgebung(self, name, mit_launchctl):
        basis = os.path.join(self.tmp, name)
        home, fake, ersatz = (os.path.join(basis, x) for x in ("home", "launchd", "bin"))
        for o in (os.path.join(home, "Desktop"), fake, ersatz):
            os.makedirs(o)
        os.symlink(sys.executable, os.path.join(ersatz, "python3"))
        dateien = {"open": ERSATZ_OPEN}
        if mit_launchctl:
            dateien["launchctl"] = ERSATZ_LAUNCHCTL % {"python": sys.executable}
        for name_, inhalt in dateien.items():
            with open(os.path.join(ersatz, name_), "w") as f:
                f.write(inhalt)
            os.chmod(os.path.join(ersatz, name_), 0o755)
        self.home, self.fake, self.ziel = home, fake, os.path.join(home, "AUTONOMOUS")
        self.port = _freier_port()
        self.env = {k: v for k, v in os.environ.items() if not k.startswith("AUTONOMOUS_")}
        self.env.update(HOME=home, PATH=ersatz + ":/usr/bin:/bin", FAKE_LAUNCHD=fake, AUTONOMOUS_PORT=str(self.port))
        self.addCleanup(self.aufraeumen)

    def aufraeumen(self):
        """Was auch immer noch läuft: beenden (auch wenn ein Schritt fehlschlug)."""
        for json_datei in [d for d in os.listdir(self.fake) if d.endswith(".json")]:
            with open(os.path.join(self.fake, json_datei)) as f:
                pid = json.load(f).get("pid")
            if pid:
                try:
                    os.kill(pid, 15)
                except OSError:
                    pass
        pid_datei = os.path.join(self.ziel, "autonomous", "daten", "autonomous.pid")
        if os.path.exists(pid_datei):
            try:
                with open(pid_datei) as f:
                    os.kill(int(f.read().strip()), 15)
            except (OSError, ValueError):
                pass
        time.sleep(0.5)

    def lauf(self, *befehl):
        r = subprocess.run(list(befehl), env=self.env, stdin=subprocess.DEVNULL, capture_output=True, text=True,
                           timeout=180)
        return r.returncode, r.stdout + r.stderr

    def symbol(self, name):
        return os.path.join(self.home, "Desktop", name + ".command")

    def aufrufe(self):
        pfad = os.path.join(self.fake, "aufrufe.log")
        if not os.path.exists(pfad):
            return []
        with open(pfad) as f:
            return f.read().splitlines()

    def geoeffnet(self):
        pfad = os.path.join(self.fake, "open.log")
        if not os.path.exists(pfad):
            return []
        with open(pfad) as f:
            return f.read().splitlines()

    def status(self):
        try:
            with OEFFNER.open("http://127.0.0.1:%d/status" % self.port, timeout=2) as a:
                return json.loads(a.read())
        except (OSError, ValueError):
            return None

    def schluessel(self):
        with open(os.path.join(self.ziel, "autonomous", "daten", "zugang.txt")) as f:
            return f.read().strip()

    def api(self, pfad, daten=None):
        k = {"X-Zugang": self.schluessel(), "Content-Type": "application/json"}
        r = urllib.request.Request("http://127.0.0.1:%d%s" % (self.port, pfad), headers=k,
                                   data=None if daten is None else json.dumps(daten).encode())
        with OEFFNER.open(r, timeout=5) as a:
            return json.loads(a.read())

    def geladen(self):
        return os.path.exists(os.path.join(self.fake, LABEL + ".json"))

    def pid_im_dienst(self):
        with open(os.path.join(self.fake, LABEL + ".json")) as f:
            return json.load(f)["pid"]

    def test_dauerbetrieb_mit_launchagent(self):
        self.neue_umgebung("mac", mit_launchctl=True)
        plist = os.path.join(self.home, "Library", "LaunchAgents", LABEL + ".plist")
        uid = os.getuid()

        # 1) Erste Einrichtung: LaunchAgent geschrieben und geladen, Server läuft über den Dienst
        code, aus = self.lauf("bash", self.einrichten)
        self.assertEqual(code, 0, aus)
        with open(plist, "rb") as f:
            p = plistlib.load(f)
        self.assertEqual(p["ProgramArguments"][1:], ["-m", "autonomous", "start"])
        self.assertTrue(os.path.isabs(p["ProgramArguments"][0]))
        self.assertEqual(p["WorkingDirectory"], self.ziel)
        self.assertIs(p["RunAtLoad"], True)
        self.assertEqual(p["KeepAlive"], {"SuccessfulExit": False})
        self.assertEqual(p["Umask"], 0o077)
        self.assertEqual(p["StandardOutPath"], os.path.join(self.ziel, "autonomous", "daten", "server.log"))
        self.assertEqual(p["EnvironmentVariables"].get("AUTONOMOUS_PORT"), str(self.port))
        self.assertIn("bootstrap gui/%d %s" % (uid, plist), self.aufrufe())
        self.assertTrue(self.geladen())
        self.assertEqual((self.status() or {}).get("system"), "AUTONOMOUS", aus)
        pid1 = self.pid_im_dienst()
        self.assertEqual(os.readlink("/proc/%d/cwd" % pid1), self.ziel)
        log = os.path.join(self.ziel, "autonomous", "daten", "server.log")
        self.assertEqual(stat.S_IMODE(os.stat(log).st_mode) & 0o077, 0)
        for name in ("AUTONOMOUS starten", "AUTONOMOUS stoppen", "AUTONOMOUS Autostart aus"):
            self.assertTrue(os.access(self.symbol(name), os.X_OK), name)
        self.assertTrue(any("?k=" in z for z in self.geoeffnet()), "Browser nicht geöffnet")
        self.assertNotIn("ki-einrichten", aus)                                  # fehlt → still übersprungen
        self.assertFalse(os.path.exists(os.path.join(self.home, "ki-aufgerufen.txt")))
        ziel_id = self.api("/api/ziele", {"titel": "Bleibt nach Aktualisierung"})["id"]
        schluessel = self.schluessel()

        # 2) Aktualisierung: Dienst wird neu geladen, Ziel und Schlüssel bleiben
        anzahl = len(self.aufrufe())
        code, aus = self.lauf("bash", self.einrichten)
        self.assertEqual(code, 0, aus)
        neu = self.aufrufe()[anzahl:]
        self.assertIn("bootout gui/%d/%s" % (uid, LABEL), neu)
        self.assertIn("bootstrap gui/%d %s" % (uid, plist), neu)
        self.assertLess(neu.index("bootout gui/%d/%s" % (uid, LABEL)), neu.index("bootstrap gui/%d %s" % (uid, plist)))
        self.assertEqual((self.status() or {}).get("system"), "AUTONOMOUS", aus)
        self.assertNotEqual(self.pid_im_dienst(), pid1)
        self.assertEqual(self.schluessel(), schluessel)
        self.assertIn(ziel_id, [z["id"] for z in self.api("/api/ziele")["ziele"]])

        # 3) „AUTONOMOUS stoppen“: Dienst sauber beendet (bootout), Autostart bleibt für die nächste Anmeldung
        code, aus = self.lauf(self.symbol("AUTONOMOUS stoppen"))
        self.assertEqual(code, 0, aus)
        self.assertIn("beendet", aus)
        self.assertIn("Autostart", aus)
        self.assertFalse(self.geladen())
        self.assertIsNone(self.status())
        self.assertTrue(os.path.exists(plist))
        with open(log, encoding="utf-8") as f:
            self.assertIn("sauber beendet", f.read())                         # SIGTERM → sauberes Ende

        # 4) „AUTONOMOUS starten“: lädt den Dienst wieder; läuft er schon, nur Browser öffnen
        code, aus = self.lauf(self.symbol("AUTONOMOUS starten"))
        self.assertEqual(code, 0, aus)
        self.assertTrue(self.geladen())
        self.assertEqual((self.status() or {}).get("system"), "AUTONOMOUS", aus)
        anzahl, geoeffnet = len(self.aufrufe()), len(self.geoeffnet())
        code, aus = self.lauf(self.symbol("AUTONOMOUS starten"))
        self.assertEqual(code, 0, aus)
        self.assertFalse([z for z in self.aufrufe()[anzahl:] if z.startswith("bootstrap")], "zweimal gestartet")
        self.assertEqual(len(self.geoeffnet()), geoeffnet + 1)

        # 5) „AUTONOMOUS Autostart aus“: Dienst beendet, plist entfernt – startet nicht mehr von selbst
        code, aus = self.lauf(self.symbol("AUTONOMOUS Autostart aus"))
        self.assertEqual(code, 0, aus)
        self.assertFalse(os.path.exists(plist))
        self.assertFalse(self.geladen())
        self.assertIsNone(self.status())

        # 6) Danach startet „AUTONOMOUS starten“ wie früher ohne Dienst – und „stoppen“ beendet es
        anzahl = len(self.aufrufe())
        code, aus = self.lauf(self.symbol("AUTONOMOUS starten"))
        self.assertEqual(code, 0, aus)
        self.assertEqual((self.status() or {}).get("system"), "AUTONOMOUS", aus)
        self.assertFalse([z for z in self.aufrufe()[anzahl:] if z.startswith("bootstrap")])
        code, aus = self.lauf(self.symbol("AUTONOMOUS stoppen"))
        self.assertEqual(code, 0, aus)
        self.assertIsNone(self.status())
        self.assertTrue(os.path.exists(os.path.join(self.ziel, "autonomous", "daten", "autonomous.db")))

    def test_ohne_launchctl_wie_bisher(self):
        self.neue_umgebung("linux", mit_launchctl=False)
        code, aus = self.lauf("bash", self.einrichten)
        self.assertEqual(code, 0, aus)
        self.assertFalse(os.path.exists(os.path.join(self.home, "Library")))
        self.assertTrue(os.access(self.symbol("AUTONOMOUS starten"), os.X_OK))
        self.assertTrue(os.access(self.symbol("AUTONOMOUS stoppen"), os.X_OK))
        self.assertFalse(os.path.exists(self.symbol("AUTONOMOUS Autostart aus")))
        self.assertEqual((self.status() or {}).get("system"), "AUTONOMOUS", aus)
        code, aus = self.lauf(self.symbol("AUTONOMOUS stoppen"))
        self.assertEqual(code, 0, aus)
        self.assertIn("beendet", aus)
        self.assertIsNone(self.status())

    def test_ki_einrichtung_wird_aufgerufen_wenn_vorhanden(self):
        """Genau eine Zeile am Ende: autonomous-ki-einrichten.sh aus dem Installationsordner – falls vorhanden."""
        with open(self.einrichten, encoding="utf-8") as f:
            zeilen = [z for z in f.read().splitlines() if KI_SKRIPT in z and not z.lstrip().startswith("#")]
        self.assertEqual(len(zeilen), 1, zeilen)
        self.neue_umgebung("ki", mit_launchctl=False)
        code, aus = self.lauf("bash", self.einrichten_ki)
        self.assertEqual(code, 0, aus)
        with open(os.path.join(self.home, "ki-aufgerufen.txt")) as f:
            self.assertIn("KI-Einrichtung aufgerufen", f.read())
        self.lauf(self.symbol("AUTONOMOUS stoppen"))


if __name__ == "__main__":
    unittest.main()
