# -*- coding: utf-8 -*-
"""Sicherer Abrufer für öffentliche Ausschreibungsquellen.

- Nur Adressen, die ``berechtigungen.url_erlaubt`` zulässt (https, freigegebene Hosts, Standard-Port).
- Nur GET und POST, Zeitlimit 20 s, höchstens 3 MB je Antwort.
- Weiterleitungen werden einzeln geprüft: führt eine auf einen fremden Host, wird abgebrochen.
- Ehrliche, neutrale Kennung – ohne Namen oder E-Mail des Nutzers.
- Höflich: höchstens ein Abruf je Host alle 10 Sekunden.
- Proxys aus der Umgebung werden genutzt (urllib-Standard); die TLS-Prüfung wird NIE abgeschaltet.

Der Inhalt jeder Antwort ist NICHT vertrauenswürdig und wird nur als Daten behandelt.
"""

import codecs
import os
import re
import ssl
import threading
import time
import urllib.error
import urllib.request
from urllib.parse import urlsplit

from .berechtigungen import url_erlaubt

KENNUNG = "AUTONOMOUS/1.0 (lokales Werkzeug zur Ausschreibungssuche)"
ZEITLIMIT = 20
MAX_BYTES = 3 * 1024 * 1024
ABSTAND_SEKUNDEN = 10          # je Host; Tests setzen das auf 0
MAX_WEITERLEITUNGEN = 5

_letzter_abruf = {}
_sperre = threading.Lock()


class NetzFehler(Exception):
    pass


class Antwort:
    def __init__(self, status, daten, kodierung, url, inhaltsart):
        self.status = status
        self.daten = daten
        self.kodierung = kodierung
        self.url = url
        self.inhaltsart = inhaltsart

    def text(self):
        return self.daten.decode(self.kodierung, errors="replace")


class _PruefendeWeiterleitung(urllib.request.HTTPRedirectHandler):
    max_redirections = MAX_WEITERLEITUNGEN

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if not url_erlaubt(newurl):
            raise NetzFehler("Weiterleitung auf eine nicht freigegebene Adresse abgelehnt (%s)"
                             % (urlsplit(newurl).hostname or "unbekannt"))
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def _tls_kontext():
    kontext = ssl.create_default_context()  # prüft Zertifikat und Hostnamen
    try:
        ohne_ca = kontext.cert_store_stats().get("x509_ca", 0) == 0
    except (AttributeError, ssl.SSLError):
        ohne_ca = False
    # macOS: Python von python.org bringt ohne „Install Certificates“ keine Stammzertifikate mit.
    # Dann die Systemzertifikate nutzen – die Prüfung bleibt dabei vollständig eingeschaltet.
    if ohne_ca and os.path.isfile("/etc/ssl/cert.pem"):
        kontext.load_verify_locations("/etc/ssl/cert.pem")
    return kontext


def _warten(host):
    with _sperre:
        jetzt = time.monotonic()
        frei_ab = _letzter_abruf.get(host, -1e9) + ABSTAND_SEKUNDEN
        warte = max(0.0, frei_ab - jetzt)
        _letzter_abruf[host] = jetzt + warte
    if warte > 0:
        time.sleep(warte)


def _kodierung(inhaltsart, daten):
    m = re.search(r"charset=([\w\-]+)", inhaltsart or "", re.I)
    if not m:
        m = re.search(rb"charset=[\"']?([\w\-]+)", daten[:4096], re.I)
        name = m.group(1).decode("ascii", "replace") if m else "utf-8"
    else:
        name = m.group(1)
    name = name.lower()
    # Browser-Regel (WHATWG): ISO-8859-1 wird als Windows-1252 gelesen
    if name in ("iso-8859-1", "latin-1", "latin1", "us-ascii", "ascii"):
        return "cp1252"
    try:
        codecs.lookup(name)
    except LookupError:
        return "utf-8"
    return name


def abrufen(url, methode="GET", daten=None, kopf=None, zeitlimit=ZEITLIMIT, max_bytes=MAX_BYTES):
    """Ruft eine freigegebene öffentliche Adresse ab. Wirft NetzFehler bei jedem Problem."""
    if methode not in ("GET", "POST"):
        raise NetzFehler("Nur GET und POST sind erlaubt.")
    if not url_erlaubt(url):
        raise NetzFehler("Adresse ist keine freigegebene öffentliche Quelle.")
    if methode == "GET" and daten is not None:
        raise NetzFehler("GET ohne Daten.")
    host = urlsplit(url).hostname.lower()
    _warten(host)
    k = {"User-Agent": KENNUNG, "Accept": "application/json, application/rss+xml, text/xml, text/html;q=0.9, */*;q=0.1",
         "Accept-Language": "de-DE,de;q=0.9"}
    k.update(kopf or {})
    anfrage = urllib.request.Request(url, data=daten, headers=k, method=methode)
    oeffner = urllib.request.build_opener(_PruefendeWeiterleitung(),
                                          urllib.request.HTTPSHandler(context=_tls_kontext()))
    try:
        with oeffner.open(anfrage, timeout=zeitlimit) as a:
            ende_url = a.geturl()
            if not url_erlaubt(ende_url):
                raise NetzFehler("Antwort kam von einer nicht freigegebenen Adresse.")
            roh = a.read(max_bytes + 1)
            if len(roh) > max_bytes:
                raise NetzFehler("Antwort zu groß (über %d MB)." % (max_bytes // (1024 * 1024)))
            inhaltsart = a.headers.get("Content-Type", "")
            return Antwort(a.status, roh, _kodierung(inhaltsart, roh), ende_url, inhaltsart)
    except NetzFehler:
        raise
    except urllib.error.HTTPError as f:
        raise NetzFehler("Quelle antwortet mit Fehler %s" % f.code)
    except (urllib.error.URLError, OSError, ValueError) as f:
        grund = getattr(f, "reason", f)
        if isinstance(f, ssl.SSLCertVerificationError) or isinstance(grund, ssl.SSLCertVerificationError):
            raise NetzFehler("Zertifikat der Quelle konnte nicht geprüft werden. Auf dem Mac mit Python von "
                             "python.org: einmal „Install Certificates.command“ im Ordner Programme/Python "
                             "ausführen. (Die Prüfung wird bewusst nicht abgeschaltet.)")
        raise NetzFehler("Quelle nicht erreichbar: %s" % grund)
