# -*- coding: utf-8 -*-
"""Sicherer Abrufer (netz.py): Größenbegrenzung und Endadresse – ohne echtes Netz."""

import unittest
from unittest import mock

from autonomous import netz

ERLAUBT = "https://api.ted.europa.eu/v3/notices/search"


class _Antwort:
    def __init__(self, inhalt, url=ERLAUBT):
        self._inhalt = inhalt
        self._url = url
        self.status = 200
        self.headers = {"Content-Type": "application/json; charset=utf-8"}
        self.gelesen_angefordert = None

    def geturl(self):
        return self._url

    def read(self, n=-1):
        self.gelesen_angefordert = n
        return self._inhalt if n < 0 else self._inhalt[:n]

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


class _Oeffner:
    def __init__(self, antwort):
        self.antwort = antwort

    def open(self, anfrage, timeout=None):
        return self.antwort


class TestAbrufer(unittest.TestCase):
    def setUp(self):
        self._warten = mock.patch.object(netz, "_warten", lambda host: None)
        self._warten.start()

    def tearDown(self):
        self._warten.stop()

    def _mit(self, antwort):
        return mock.patch.object(netz.urllib.request, "build_opener", lambda *a, **k: _Oeffner(antwort))

    def test_antwort_ueber_grenze_wird_abgelehnt(self):
        antwort = _Antwort(b"x" * 2000)
        with self._mit(antwort):
            with self.assertRaises(netz.NetzFehler) as f:
                netz.abrufen(ERLAUBT, max_bytes=1000)
        self.assertIn("zu groß", str(f.exception))
        self.assertEqual(antwort.gelesen_angefordert, 1001)  # liest nie mehr als Grenze + 1 Byte

    def test_antwort_genau_an_der_grenze_ist_erlaubt(self):
        with self._mit(_Antwort(b"x" * 1000)):
            a = netz.abrufen(ERLAUBT, max_bytes=1000)
        self.assertEqual(len(a.daten), 1000)

    def test_standardgrenze_ist_3_mb(self):
        self.assertEqual(netz.MAX_BYTES, 3 * 1024 * 1024)

    def test_endadresse_auf_fremdem_host_wird_verworfen(self):
        with self._mit(_Antwort(b"{}", url="https://angreifer.example/")):
            with self.assertRaises(netz.NetzFehler):
                netz.abrufen(ERLAUBT)

    def test_nicht_freigegebene_adresse_wird_gar_nicht_abgerufen(self):
        aufgerufen = []
        with mock.patch.object(netz.urllib.request, "build_opener", lambda *a, **k: aufgerufen.append(1)):
            with self.assertRaises(netz.NetzFehler):
                netz.abrufen("https://angreifer.example/")
        self.assertEqual(aufgerufen, [])
