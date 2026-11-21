# -*- coding: utf-8 -*-
"""Härtung nach der unabhängigen Sicherheitsprüfung (Befunde 1–8 und Zusatzhinweise).

Jeder Test schlägt mit dem Stand vor der Korrektur fehl (Commit 06ccbc4) und läuft danach grün.
"""

import http.client
import json
import os
import shutil
import signal
import socket
import sqlite3
import stat
import subprocess
import sys
import tempfile
import threading
import time
import unittest
import urllib.request

from autonomous.agenten import Agent
from autonomous.tests.hilfe import KernTest

PROJEKT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class Versender(Agent):
    rolle = "haertung_versender"
    name = "Test"
    rechte = frozenset({"externe_nachricht"})
    aufgabentypen = {}


def _langsam_bei(db, merkmal, pause=0.05):
    """Verlangsamt Lesezugriffe, deren SQL `merkmal` enthält – erzwingt die Verschränkung zweier Threads
    genau zwischen Prüfen und Schreiben (macht den früheren Wettlauf zuverlässig sichtbar)."""
    original = db.eins

    def eins(sql, parameter=()):
        zeile = original(sql, parameter)
        if merkmal in sql:
            time.sleep(pause)
        return zeile
    db.eins = eins
    return original


def _gleichzeitig(*aufrufe):
    """Startet alle Aufrufe exakt gleichzeitig; liefert je Aufruf ('ok', wert) oder ('fehler', ausnahme)."""
    start = threading.Barrier(len(aufrufe))
    ergebnisse = [None] * len(aufrufe)

    def lauf(i, f):
        start.wait()
        try:
            ergebnisse[i] = ("ok", f())
        except Exception as e:  # noqa: BLE001 – im Test bewusst alles einsammeln
            ergebnisse[i] = ("fehler", e)
    faeden = [threading.Thread(target=lauf, args=(i, f)) for i, f in enumerate(aufrufe)]
    for t in faeden:
        t.start()
    for t in faeden:
        t.join(10)
    return ergebnisse


# ---------------------------------------------------------------- Befund 1
class TestFreigabeAtomar(KernTest):
    def setUp(self):
        super().setUp()
        self.kern.register.registrieren(Versender())

    def _offene_freigabe(self, nr):
        e = self.kern.supervisor.pruefe("haertung_versender", "externe_nachricht", "kunde-%d" % nr)
        self.assertEqual(e.ergebnis, "freigabe_noetig")
        return e.freigabe_id

    def test_ja_und_nein_gleichzeitig_genau_eine_entscheidung(self):
        _langsam_bei(self.kern.db, "FROM freigaben WHERE id=")
        for nr in range(5):
            fid = self._offene_freigabe(nr)
            sup = self.kern.supervisor
            ja, nein = _gleichzeitig(lambda sup=sup, fid=fid: sup.entscheiden(fid, True, "eigentuemer"),
                                     lambda sup=sup, fid=fid: sup.entscheiden(fid, False, "eigentuemer"))
            erfolge = [e for e in (ja, nein) if e[0] == "ok"]
            fehler = [e for e in (ja, nein) if e[0] == "fehler"]
            self.assertEqual(len(erfolge), 1, (ja, nein))
            self.assertEqual(len(fehler), 1, (ja, nein))
            self.assertIsInstance(fehler[0][1], ValueError)
            self.assertIn("bereits entschieden", str(fehler[0][1]))
            gespeichert = self.kern.db.wert("SELECT status FROM freigaben WHERE id=?", (fid,))
            self.assertEqual(gespeichert, erfolge[0][1], "bestätigter und gespeicherter Status müssen gleich sein")

    def test_zweite_entscheidung_ueber_api_ist_400(self):
        from autonomous import api
        fid = self._offene_freigabe(99)
        self.api("POST", "/api/freigaben/%s/entscheiden" % fid, {"entscheidung": "nein"})
        with self.assertRaises((ValueError, api.ApiFehler)):
            self.api("POST", "/api/freigaben/%s/entscheiden" % fid, {"entscheidung": "ja"})
        self.assertEqual(self.kern.db.wert("SELECT status FROM freigaben WHERE id=?", (fid,)), "abgelehnt")


# ---------------------------------------------------------------- Befund 7
class TestGegenbuchungNurEinmal(KernTest):
    def test_reale_gegenbuchung_gleichzeitig_nur_einmal(self):
        f = self.kern.finanzen
        _langsam_bei(self.kern.db, "gegenbuchung_zu")
        for _ in range(3):
            bid = f.ausgabe("20", "material", "Baumarkt", "Kauf", "eigentuemer")
            a, b = _gleichzeitig(lambda bid=bid: f.gegenbuchung(bid, "Korrektur A", "eigentuemer"),
                                 lambda bid=bid: f.gegenbuchung(bid, "Korrektur B", "eigentuemer"))
            self.assertEqual(sorted(x[0] for x in (a, b)), ["fehler", "ok"], (a, b))
            self.assertEqual(self.kern.db.wert("SELECT COUNT(*) FROM real_buchungen WHERE gegenbuchung_zu=?",
                                               (bid,)), 1)

    def test_wallet_gegenbuchung_gleichzeitig_nur_einmal(self):
        w = self.kern.wallet
        _langsam_bei(self.kern.db, "gegenbuchung_zu")
        for _ in range(3):
            bid = w.buchen("ausgabe", "1", "test", "Kauf", "eigentuemer")["id"]
            a, b = _gleichzeitig(lambda bid=bid: w.gegenbuchung(bid, "Korrektur A", "eigentuemer"),
                                 lambda bid=bid: w.gegenbuchung(bid, "Korrektur B", "eigentuemer"))
            self.assertEqual(sorted(x[0] for x in (a, b)), ["fehler", "ok"], (a, b))
            self.assertEqual(self.kern.db.wert("SELECT COUNT(*) FROM wallet_buchungen WHERE gegenbuchung_zu=?",
                                               (bid,)), 1)

    def test_datenbank_erzwingt_einmalige_gegenbuchung(self):
        indizes = {z["name"] for z in self.kern.db.alle("SELECT name FROM sqlite_master WHERE type='index'")}
        self.assertIn("real_gegen_einmal", indizes)
        self.assertIn("wallet_gegen_einmal", indizes)
        bid = self.kern.wallet.buchen("ausgabe", "1", "test", "x", "eigentuemer")["id"]
        self.kern.wallet.gegenbuchung(bid, "Korrektur", "eigentuemer")
        with self.assertRaises(sqlite3.IntegrityError):  # auch direkt in der Datenbank nicht ein zweites Mal
            self.kern.db.ausfuehren("INSERT INTO wallet_buchungen (id, nr, zeit, betrag_cent, kategorie, art, "
                                    "begruendung, gegenbuchung_zu, akteur) VALUES ('x', 999, 't', 1, 'k', "
                                    "'gegenbuchung', 'b', ?, 'a')", (bid,))

    def test_migration_bricht_bei_alten_dubletten_nicht_ab(self):
        """Eine ältere Datenbank, in der der frühere Wettlauf schon Dubletten erzeugt hat: Migration 4 darf den
        Start nicht verhindern, meldet die Dubletten im Protokoll und der Code verhindert weitere."""
        from autonomous import db as dbmodul
        pfad = os.path.join(tempfile.mkdtemp(prefix="haertung-db-"), "alt.db")
        self.addCleanup(shutil.rmtree, os.path.dirname(pfad), True)
        alle = dbmodul.MIGRATIONEN
        dbmodul.MIGRATIONEN = alle[:3]
        try:
            alt = dbmodul.Datenbank(pfad)
            for i in (1, 2):
                alt.ausfuehren("INSERT INTO wallet_buchungen (id, nr, zeit, betrag_cent, kategorie, art, begruendung,"
                               " gegenbuchung_zu, akteur) VALUES (?, ?, 't', 1, 'k', 'gegenbuchung', 'b', 'w_doppelt',"
                               " 'a')", ("w_g%d" % i, i))
            alt.schliessen()
        finally:
            dbmodul.MIGRATIONEN = alle
        neu = dbmodul.Datenbank(pfad)  # darf nicht abbrechen
        self.addCleanup(neu.schliessen)
        self.assertEqual(neu.schema_version(), len(alle))
        indizes = {z["name"] for z in neu.alle("SELECT name FROM sqlite_master WHERE type='index'")}
        self.assertNotIn("wallet_gegen_einmal", indizes)   # mit Dubletten nicht anlegbar
        self.assertIn("real_gegen_einmal", indizes)        # die reale Tabelle hat keine Dubletten
        meldung = neu.eins("SELECT * FROM protokoll WHERE quelle='migration' AND ebene='warnung'")
        self.assertIsNotNone(meldung)
        self.assertIn("w_doppelt", meldung["details"])


# ---------------------------------------------------------------- Befund 8
class TestBundLeser(unittest.TestCase):
    FEED = ('<?xml version="1.0" encoding="UTF-16"?>\n<!DOCTYPE rss [<!ENTITY x "EINGESCHLEUST">]>\n'
            '<rss version="2.0"><channel><item><title>&x;</title>'
            '<link>https://www.service.bund.de/IMPORTE/Ausschreibungen/a/1.html</link>'
            '<description>Erf&#252;llungsort: &lt;strong&gt;51373 Leverkusen&lt;/strong&gt;</description>'
            '</item></channel></rss>')

    def test_utf16_mit_entity_wird_abgelehnt(self):
        from autonomous.auftraege.quellen import QuellenFehler, bund_parsen
        for kodierung in ("utf-16", "utf-16-le", "utf-16-be"):
            with self.assertRaises(QuellenFehler, msg=kodierung):
                bund_parsen(self.FEED.encode(kodierung))

    def test_ungueltiges_utf8_wird_abgelehnt(self):
        from autonomous.auftraege.quellen import QuellenFehler, bund_parsen
        with self.assertRaises(QuellenFehler):
            bund_parsen(b'<?xml version="1.0"?><rss><channel><item><title>\xff\xfe</title></item></channel></rss>')

    def test_dtd_klein_geschrieben_wird_abgelehnt(self):
        from autonomous.auftraege.quellen import QuellenFehler, bund_parsen
        with self.assertRaises(QuellenFehler):
            bund_parsen(self.FEED.replace("UTF-16", "UTF-8").replace("DOCTYPE", "doctype").encode("utf-8"))

    def test_echte_testdaten_bleiben_lesbar(self):
        from autonomous.auftraege.quellen import bund_parsen
        with open(os.path.join(PROJEKT, "autonomous", "tests", "daten", "service_bund_reinigung.rss"), "rb") as f:
            eintraege = bund_parsen(f.read())
        self.assertGreater(len(eintraege), 50)
        self.assertTrue(any("ü" in (e.get("ort") or "") + (e.get("titel") or "") for e in eintraege))


# ---------------------------------------------------------------- Befunde 3–6 und CSP (laufender Server)
class TestServerHaertung(KernTest):
    def setUp(self):
        super().setUp()
        from autonomous import server
        self.servermodul = server
        self.server = server.starten(self.kern, "127.0.0.1", 0)
        self.port = self.server.server_address[1]
        server.Handler.hosts = server.erlaubte_hosts(self.port)
        server.Handler.herkuenfte = server.erlaubte_herkuenfte(self.port)
        self.schluessel = server.zugangsschluessel()
        self.fehler_im_handler = []
        self.server.handle_error = lambda anfrage, adresse: self.fehler_im_handler.append(sys.exc_info()[1])
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        super().tearDown()

    def _post(self, pfad, koerper=b"{}", kopf=None):
        verbindung = http.client.HTTPConnection("127.0.0.1", self.port, timeout=10)
        k = {"Host": "127.0.0.1:%d" % self.port, "X-Zugang": self.schluessel, "Content-Type": "application/json"}
        k.update(kopf or {})
        verbindung.request("POST", pfad, body=koerper, headers=k)
        antwort = verbindung.getresponse()
        return antwort.status, antwort.read()

    def _roh(self, daten, schliessen_nach_senden=True, warten=10):
        """Schickt rohe Bytes; liefert die Statuszeile oder '' (Verbindung ohne Antwort beendet)."""
        s = socket.create_connection(("127.0.0.1", self.port), timeout=warten)
        try:
            s.sendall(daten)
            if schliessen_nach_senden:
                s.shutdown(socket.SHUT_WR)
            antwort = b""
            while True:
                try:
                    teil = s.recv(65536)
                except socket.timeout:
                    break
                if not teil:
                    break
                antwort += teil
            return antwort.split(b"\r\n", 1)[0].decode("latin-1")
        finally:
            s.close()

    def _kopfzeilen(self, methode, pfad, extra=""):
        return ("%s %s HTTP/1.1\r\nHost: 127.0.0.1:%d\r\nX-Zugang: %s\r\n%s" % (
            methode, pfad, self.port, self.schluessel, extra)).encode("latin-1")

    def test_herkunft_wird_exakt_geprueft(self):
        ziel = "/api/ziele"
        p = self.port
        for herkunft, erwartet in (("http://127.0.0.1:%d" % p, 200), ("http://localhost:%d" % p, 200),
                                   ("http://127.0.0.1", 403), ("http://localhost", 403),
                                   ("https://127.0.0.1:%d" % p, 403), ("http://127.0.0.1:%d" % (p + 1), 403),
                                   ("null", 403), ("http://angreifer.example", 403)):
            status, _ = self._post(ziel, json.dumps({"titel": "Ziel %s" % herkunft}).encode(),
                                   {"Origin": herkunft})
            self.assertEqual(status, erwartet, herkunft)

    def test_nur_echtes_json_als_inhaltsart(self):
        status, _ = self._post("/api/ziele", b'{"titel": "x"}', {"Content-Type": "text/plain; x=application/json"})
        self.assertEqual(status, 415)
        status, _ = self._post("/api/ziele", b'{"titel": "x"}', {"Content-Type": "application/json; charset=utf-8"})
        self.assertEqual(status, 200)

    def test_inhaltslaenge_wird_streng_geprueft(self):
        koerper = b'{"titel": "' + b"a" * 600000 + b'"}'
        self.assertIn(" 413 ", self._roh(self._kopfzeilen("POST", "/api/ziele",
                      "Content-Type: application/json\r\nContent-Length: -1\r\n\r\n") + koerper) + " ")
        self.assertIn(" 400 ", self._roh(self._kopfzeilen("POST", "/api/ziele",
                      "Content-Type: application/json\r\nContent-Length: abc\r\n\r\n{}")) + " ")
        tief = b"[" * 200000 + b"]" * 200000
        self.assertIn(" 400 ", self._roh(self._kopfzeilen("POST", "/api/ziele",
                      "Content-Type: application/json\r\nContent-Length: %d\r\n\r\n" % len(tief)) + tief) + " ")
        self.assertEqual(self.fehler_im_handler, [])

    def test_halboffene_verbindungen_werden_beendet(self):
        self.assertEqual(self.servermodul.Handler.timeout, 20)
        alt = self.servermodul.Handler.timeout
        self.servermodul.Handler.timeout = 0.5
        try:
            s = socket.create_connection(("127.0.0.1", self.port), timeout=5)
            s.sendall(b"GET /status HTTP/1.1\r\nHost: 127.0.0.1\r\n")  # Kopfzeilen nie abgeschlossen
            start = time.time()
            self.assertEqual(s.recv(1024), b"")                         # Server schließt die Verbindung
            self.assertLess(time.time() - start, 4)
            s.close()
        finally:
            self.servermodul.Handler.timeout = alt
        with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(urllib.request.Request(
                "http://127.0.0.1:%d/status" % self.port, headers={"Host": "127.0.0.1:%d" % self.port}),
                timeout=5) as a:
            self.assertEqual(a.status, 200)

    def test_nicht_ascii_im_schluessel_ohne_ausnahme(self):
        for kopf in (b"X-Zugang: \xe4\xf6\xfc\r\n", b"Cookie: autonomous_zugang=\xe4\r\n"):
            anfrage = (b"GET /api/status HTTP/1.1\r\nHost: 127.0.0.1:" + str(self.port).encode() + b"\r\n" + kopf +
                       b"Connection: close\r\n\r\n")
            self.assertIn(" 401 ", self._roh(anfrage) + " ")
        anfrage = ("GET /?k=%%C3%%A4 HTTP/1.1\r\nHost: 127.0.0.1:%d\r\nConnection: close\r\n\r\n" % self.port)
        self.assertIn(" 403 ", self._roh(anfrage.encode()) + " ")
        self.assertEqual(self.fehler_im_handler, [])

    def test_produktseiten_ohne_skripte_formulare_und_basis(self):
        from autonomous import konfig
        ordner = konfig.unterordner("produkte")
        with open(os.path.join(ordner, "probe.html"), "w", encoding="utf-8") as f:
            f.write("<p>Probe</p>")
        r = urllib.request.Request("http://127.0.0.1:%d/produkte/probe.html" % self.port,
                                   headers={"Host": "127.0.0.1:%d" % self.port, "X-Zugang": self.schluessel})
        with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(r, timeout=5) as a:
            csp = a.headers["Content-Security-Policy"]
        for teil in ("default-src 'none'", "sandbox", "form-action 'none'", "base-uri 'none'"):
            self.assertIn(teil, csp)


class TestErlaubteHosts(unittest.TestCase):
    def test_hosts_aus_umgebung_werden_klein_verglichen(self):
        from autonomous import server
        alt = os.environ.get("AUTONOMOUS_ERLAUBTE_HOSTS")
        os.environ["AUTONOMOUS_ERLAUBTE_HOSTS"] = " DEIN-MAC.local ,Buero-Mac.LOCAL"
        try:
            hosts = server.erlaubte_hosts(8770)
            herkuenfte = server.erlaubte_herkuenfte(8770)
        finally:
            if alt is None:
                os.environ.pop("AUTONOMOUS_ERLAUBTE_HOSTS", None)
            else:
                os.environ["AUTONOMOUS_ERLAUBTE_HOSTS"] = alt
        self.assertIn("dein-mac.local:8770", hosts)
        self.assertIn("buero-mac.local:8770", hosts)
        self.assertIn("http://dein-mac.local:8770", herkuenfte)
        self.assertNotIn("http://dein-mac.local", herkuenfte)


# ---------------------------------------------------------------- Befund 2 (echter Start als eigener Prozess)
class TestStartOhneSchluesselAusgabe(unittest.TestCase):
    def test_start_gibt_schluessel_nicht_aus_und_dateien_sind_privat(self):
        basis = tempfile.mkdtemp(prefix="haertung-start-")
        self.addCleanup(shutil.rmtree, basis, True)
        daten = os.path.join(basis, "daten")  # existiert noch nicht → wird vom Start angelegt
        with socket.socket() as s:
            s.bind(("127.0.0.1", 0))
            port = s.getsockname()[1]
        umgebung = dict(os.environ, AUTONOMOUS_DATEN=daten, AUTONOMOUS_PORT=str(port), PYTHONUNBUFFERED="1")
        prozess = subprocess.Popen([sys.executable, "-m", "autonomous", "start"], cwd=PROJEKT, env=umgebung,
                                   stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        try:
            ende = time.time() + 20
            while time.time() < ende:
                try:
                    with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(urllib.request.Request(
                            "http://127.0.0.1:%d/status" % port, headers={"Host": "127.0.0.1:%d" % port}),
                            timeout=1) as a:
                        if a.status == 200:
                            break
                except OSError:
                    time.sleep(0.2)
        finally:
            prozess.send_signal(signal.SIGTERM)
            ausgabe = prozess.communicate(timeout=20)[0].decode("utf-8", "replace")
        with open(os.path.join(daten, "zugang.txt")) as f:
            schluessel = f.read().strip()
        self.assertTrue(schluessel)
        self.assertNotIn(schluessel, ausgabe)
        self.assertIn("autonomous link", ausgabe)
        self.assertEqual(stat.S_IMODE(os.stat(daten).st_mode) & 0o077, 0, "Datenordner")
        for name in ("autonomous.db", "zugang.txt"):
            self.assertEqual(stat.S_IMODE(os.stat(os.path.join(daten, name)).st_mode) & 0o077, 0, name)


# ---------------------------------------------------------------- Zusatz: Stopp-Skript
class TestStoppSkript(unittest.TestCase):
    def _skript_in(self, ordner):
        ziel = os.path.join(ordner, "AUTONOMOUS-stoppen.command")
        shutil.copy(os.path.join(PROJEKT, "AUTONOMOUS-stoppen.command"), ziel)
        os.chmod(ziel, 0o700)
        os.makedirs(os.path.join(ordner, "autonomous", "daten"))
        return ziel

    def _pid_eintragen(self, ordner, pid):
        with open(os.path.join(ordner, "autonomous", "daten", "autonomous.pid"), "w") as f:
            f.write(str(pid))

    def test_fremder_prozess_wird_nicht_beendet(self):
        ordner = tempfile.mkdtemp(prefix="haertung-stopp-")
        self.addCleanup(shutil.rmtree, ordner, True)
        skript = self._skript_in(ordner)
        fremd = subprocess.Popen(["sleep", "30"])
        self.addCleanup(fremd.kill)
        self._pid_eintragen(ordner, fremd.pid)
        subprocess.run(["bash", skript], capture_output=True, timeout=30)
        self.assertIsNone(fremd.poll(), "fremder Prozess darf nicht beendet werden")
        self.assertFalse(os.path.exists(os.path.join(ordner, "autonomous", "daten", "autonomous.pid")))

    def test_eigener_prozess_wird_beendet(self):
        ordner = tempfile.mkdtemp(prefix="haertung-stopp-")
        self.addCleanup(shutil.rmtree, ordner, True)
        skript = self._skript_in(ordner)
        eigen = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)", "-m", "autonomous"])
        self.addCleanup(eigen.kill)
        self._pid_eintragen(ordner, eigen.pid)
        subprocess.run(["bash", skript], capture_output=True, timeout=30)
        self.assertIsNotNone(eigen.wait(timeout=10))


if __name__ == "__main__":
    unittest.main()
