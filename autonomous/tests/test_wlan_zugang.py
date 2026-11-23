# -*- coding: utf-8 -*-
"""iPhone im eigenen WLAN: Zugriff ein-/ausschalten, nur private Adressen, QR-Code mit dem Anmeldelink.

Die Netztests nutzen eine echte private Adresse dieses Rechners (sonst werden sie übersprungen)."""

import json
import os
import threading
import unittest
import urllib.error
import urllib.request
from unittest import mock

from autonomous import wlan
from autonomous.tests.hilfe import KernTest


class _OhneWeiterleitung(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *a, **k):
        return None


def _oeffner():
    return urllib.request.build_opener(urllib.request.ProxyHandler({}), _OhneWeiterleitung())


class TestAdressen(unittest.TestCase):
    def test_nur_private_nutzbare_adressen(self):
        for adresse, erwartet in (("192.168.178.20", True), ("10.0.0.5", True), ("172.16.3.4", True),
                                  ("8.8.8.8", False), ("127.0.0.1", False), ("169.254.3.3", False),
                                  ("100.64.1.2", False), ("fe80::1", False), ("kein-ip", False)):
            self.assertEqual(wlan.ist_nutzbar(adresse), erwartet, adresse)

    def test_vorgabe_wird_gefiltert(self):
        with mock.patch.dict(os.environ, {"AUTONOMOUS_WLAN_ADRESSE": "8.8.8.8, 192.168.178.20,127.0.0.1"}):
            self.assertEqual(wlan.private_adressen(), ["192.168.178.20"])

    def test_lokaler_name(self):
        for roh, erwartet in (("Santanas-MacBook-Air.local", "santanas-macbook-air.local"),
                              ("MacBook-Air.fritz.box", "macbook-air.local"), ("", None), ("böse name", None)):
            with mock.patch("socket.gethostname", return_value=roh):
                self.assertEqual(wlan.lokaler_name(), erwartet, roh)


class TestQrCode(unittest.TestCase):
    LINK = "http://192.168.178.20:8770/?k=Ab-c_123"

    def test_struktur(self):
        q = wlan.qr_daten(self.LINK)
        n = q["groesse"]
        self.assertGreaterEqual(n, 21)
        self.assertEqual((n - 17) % 4, 0)                       # gültige QR-Größe (Version 1–40)
        self.assertTrue(q["pfad"].startswith("M"))
        self.assertEqual(q["rand"], 4)
        self.assertEqual(wlan.qr_daten(self.LINK), q)            # gleich bei gleichem Inhalt

    @unittest.skipUnless(all(__import__("importlib").util.find_spec(m) for m in ("zxingcpp", "PIL")),
                         "zxing-cpp/Pillow nur in der Entwicklungsumgebung")
    def test_gelesener_inhalt_ist_der_link(self):
        """Echte Gegenprobe: QR in ein Bild zeichnen und mit einem unabhängigen Leser (ZXing) dekodieren."""
        import zxingcpp
        from PIL import Image
        q = wlan.qr_daten(self.LINK)
        punkte = wlan.qr_matrix(self.LINK)
        n, rand, skala = q["groesse"], q["rand"], 8
        bild = Image.new("L", ((n + 2 * rand) * skala,) * 2, 255)
        for y, zeile in enumerate(punkte):
            for x, dunkel in enumerate(zeile):
                if dunkel:
                    for dy in range(skala):
                        for dx in range(skala):
                            bild.putpixel(((x + rand) * skala + dx, (y + rand) * skala + dy), 0)
        gelesen = zxingcpp.read_barcodes(bild)
        self.assertEqual([g.text for g in gelesen], [self.LINK])


def _private_adresse_hier():
    adressen = wlan.private_adressen()
    return adressen[0] if adressen else None


@unittest.skipUnless(_private_adresse_hier(), "kein privates Netz auf diesem Rechner")
class TestWlanZugriffImServer(KernTest):
    def setUp(self):
        super().setUp()
        from autonomous import server
        self.server_modul = server
        self.adresse = _private_adresse_hier()
        self.server = server.starten(self.kern, "127.0.0.1", 0)
        self.port = self.server.server_address[1]
        self.schluessel = server.zugangsschluessel()
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def tearDown(self):
        if getattr(self.kern, "wlan", None):
            self.kern.wlan.aus()
        self.server.shutdown()
        self.server.server_close()
        super().tearDown()

    def lokal(self, pfad, daten=None, kopf=None):
        k = {"Host": "127.0.0.1:%d" % self.port, "X-Zugang": self.schluessel}
        k.update(kopf or {})
        if daten is not None:
            k["Content-Type"] = "application/json"
            daten = json.dumps(daten).encode()
        r = urllib.request.Request("http://127.0.0.1:%d%s" % (self.port, pfad), data=daten, headers=k)
        try:
            with _oeffner().open(r, timeout=5) as a:
                return a.status, json.loads(a.read() or b"{}")
        except urllib.error.HTTPError as f:
            return f.code, json.loads(f.read() or b"{}")

    def wlan_anfrage(self, pfad, daten=None, kopf=None, host=None):
        """Echte Verbindung über die WLAN-Adresse (nicht über 127.0.0.1)."""
        k = {"Host": host or "%s:%d" % (self.adresse, self.port)}
        k.update(kopf or {})
        if daten is not None:
            k["Content-Type"] = "application/json"
            daten = json.dumps(daten).encode()
        r = urllib.request.Request("http://%s:%d%s" % (self.adresse, self.port, pfad), data=daten, headers=k)
        try:
            with _oeffner().open(r, timeout=5) as a:
                return a.status, a.headers
        except urllib.error.HTTPError as f:  # 303/403/421 sind hier erwartete Antworten, kein Verbindungsfehler
            return f.code, f.headers

    def wlan_code(self, *a, **k):
        return self.wlan_anfrage(*a, **k)[0]

    def test_standard_aus_und_nicht_erreichbar(self):
        code, d = self.lokal("/api/iphone")
        self.assertEqual(code, 200)
        self.assertIs(d["erlaubt"], False)
        self.assertIs(d["aktiv"], False)
        self.assertNotIn("link", d)
        with self.assertRaises(urllib.error.URLError):
            self.wlan_anfrage("/status")

    def test_einschalten_link_qr_und_echter_zugriff(self):
        code, d = self.lokal("/api/iphone", {"erlaubt": True})
        self.assertEqual(code, 200, d)
        self.assertIs(d["aktiv"], True)
        self.assertIn(self.adresse, d["adressen"])
        self.assertEqual(d["link"], "http://%s:%d/?k=%s" % (self.adresse, self.port, self.schluessel))
        self.assertEqual(d["qr"], wlan.qr_daten(d["link"]))
        self.assertIs(self.kern.einstellungen.hole("wlan_zugriff"), True)
        # echte Verbindung über die WLAN-Adresse
        self.assertEqual(self.wlan_anfrage("/status")[0], 200)
        code, kopf = self.wlan_anfrage("/?k=" + self.schluessel)
        self.assertEqual(code, 303)
        self.assertIn("autonomous_zugang=", kopf["Set-Cookie"])
        herkunft = "http://%s:%d" % (self.adresse, self.port)
        z = {"X-Zugang": self.schluessel}
        self.assertEqual(self.wlan_code("/api/ziele", {"titel": "vom iPhone"}, dict(z, Origin=herkunft)), 200)
        self.assertEqual(self.wlan_code("/api/ziele", {"titel": "x"}, dict(z, Origin="http://angreifer.example")),
                         403)
        self.assertEqual(self.wlan_code("/status", host="angreifer.example:%d" % self.port), 421)

    def test_ausschalten_macht_unerreichbar(self):
        self.lokal("/api/iphone", {"erlaubt": True})
        self.assertEqual(self.wlan_anfrage("/status")[0], 200)
        code, d = self.lokal("/api/iphone", {"erlaubt": False})
        self.assertEqual(code, 200)
        self.assertIs(d["aktiv"], False)
        self.assertIs(self.kern.einstellungen.hole("wlan_zugriff"), False)
        with self.assertRaises(urllib.error.URLError):
            self.wlan_anfrage("/status")
        # auch über den Rechner selbst ist die WLAN-Adresse als Host nicht mehr erlaubt
        self.assertEqual(self.lokal("/status", kopf={"Host": "%s:%d" % (self.adresse, self.port)})[0], 421)

    def test_bleibt_nach_neustart_an(self):
        self.lokal("/api/iphone", {"erlaubt": True})
        self.kern.wlan.aus()
        self.server.shutdown()
        self.server.server_close()
        self.server = self.server_modul.starten(self.kern, "127.0.0.1", 0)  # Einstellung steht noch auf „an“
        self.port = self.server.server_address[1]
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.assertIs(self.kern.wlan.status()["aktiv"], True)
        self.assertEqual(self.wlan_anfrage("/status")[0], 200)

    def test_ohne_privates_netz_klare_meldung(self):
        with mock.patch.dict(os.environ, {"AUTONOMOUS_WLAN_ADRESSE": "8.8.8.8"}):
            code, d = self.lokal("/api/iphone", {"erlaubt": True})
        self.assertEqual(code, 400)
        self.assertIn("WLAN", d["fehler"])
        self.assertIs(self.kern.einstellungen.hole("wlan_zugriff"), False)

    def test_allgemeine_einstellung_schaltet_genauso(self):
        code, _ = self.lokal("/api/einstellungen", {"schluessel": "wlan_zugriff", "wert": True})
        self.assertEqual(code, 200)
        self.assertIs(self.kern.wlan.status()["aktiv"], True)
        self.assertEqual(self.wlan_anfrage("/status")[0], 200)
        self.lokal("/api/einstellungen", {"schluessel": "wlan_zugriff", "wert": False})
        with self.assertRaises(urllib.error.URLError):
            self.wlan_anfrage("/status")


if __name__ == "__main__":
    unittest.main()
