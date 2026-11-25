# -*- coding: utf-8 -*-
"""Lokaler HTTP-Server (nur Python-Standardbibliothek).

Schutz:
1. Standardmäßig nur 127.0.0.1 erreichbar.
2. Host-Prüfung gegen DNS-Rebinding.
3. Zugangsschlüssel (Cookie oder Kopfzeile X-Zugang) für alles unter /api/.
   Der Schlüssel liegt in daten/zugang.txt (nur für den Besitzer lesbar, nie in Git).
4. Bei POST: Herkunftsprüfung (Origin) und nur JSON, Größenlimit.
5. Strikte Content-Security-Policy, keine fremden Skripte.
"""

import datetime
import hmac
import json
import mimetypes
import os
import secrets
import threading
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from . import api, konfig, sicherung

try:  # Vertriebs- und Produkt-Routen (eigenes Modul)
    from . import api_vertrieb  # noqa: F401
except ImportError:
    pass
try:  # Auftrags-Radar: öffentliche Ausschreibungen (eigenes Modul)
    from . import api_auftraege  # noqa: F401
except ImportError:
    pass
try:  # Marktbericht (Research-Agent) und lokales Modell (eigenes Modul)
    from . import api_research  # noqa: F401
except ImportError:
    pass
try:  # Überlebens-Agent: Lage aus echten Zahlen, Geldchancen, feste Kosten (eigenes Modul)
    from . import api_ueberleben  # noqa: F401
except ImportError:
    pass

MAX_KOERPER = 512 * 1024
# Erzeugte Seiten: keine Skripte, kein Netz, keine Formulare, eigene (abgeschottete) Herkunft
PRODUKT_CSP = ("default-src 'none'; style-src 'unsafe-inline'; img-src data:; frame-ancestors 'self'; "
               "sandbox; form-action 'none'; base-uri 'none'")
CSP = ("default-src 'self'; style-src 'self'; script-src 'self'; img-src 'self' data:; connect-src 'self'; "
       "frame-src 'self'; frame-ancestors 'self'; base-uri 'none'; form-action 'none'")


def zugangsschluessel():
    pfad = os.path.join(konfig.datenordner(), "zugang.txt")
    if not os.path.exists(pfad):
        fd = os.open(pfad, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "w") as f:
            f.write(secrets.token_urlsafe(24))
    with open(pfad) as f:
        return f.read().strip()


def _hostnamen():
    namen = {"127.0.0.1", "localhost", "[::1]"}
    extra = os.environ.get("AUTONOMOUS_ERLAUBTE_HOSTS", "")
    # Hostnamen sind nicht groß/klein-sensitiv; verglichen wird immer klein (z. B. „DEIN-MAC.local“).
    namen |= {h.strip().lower() for h in extra.split(",") if h.strip()}
    return namen


def erlaubte_hosts(port):
    namen = _hostnamen()
    return set(namen) | {"%s:%d" % (n, port) for n in namen}


def erlaubte_herkuenfte(port):
    """Exakt erlaubte Herkunft (Origin) für POST: Schema http, erlaubter Host UND genau dieser Port.
    Ohne Port nur, wenn der Server wirklich auf Port 80 läuft (dann lassen Browser den Port weg)."""
    namen = _hostnamen()
    herkuenfte = {"http://%s:%d" % (n, port) for n in namen}
    if port == 80:
        herkuenfte |= {"http://%s" % n for n in namen}
    return herkuenfte


class Handler(BaseHTTPRequestHandler):
    server_version = "AUTONOMOUS"
    sys_version = ""
    timeout = 20  # Sekunden je Verbindung: halboffene Anfragen können den Server nicht blockieren
    kern = None
    schluessel = ""
    hosts = set()
    herkuenfte = set()

    def log_message(self, fmt, *args):  # keine Zugriffe mit Schlüsseln ins Terminal
        pass

    # ---- Antworten ----
    def _senden(self, status, daten, typ="application/json; charset=utf-8", extra=None, csp=CSP):
        if isinstance(daten, (dict, list)):
            daten = json.dumps(daten, ensure_ascii=False, default=str).encode("utf-8")
        elif isinstance(daten, str):
            daten = daten.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", typ)
        self.send_header("Content-Length", str(len(daten)))
        self.send_header("Content-Security-Policy", csp)
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("X-Frame-Options", "SAMEORIGIN")
        self.send_header("Cache-Control", "no-store")
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(daten)

    def _fehler(self, status, meldung):
        self._senden(status, {"fehler": meldung})

    # ---- Prüfungen ----
    def _host_ok(self):
        return (self.headers.get("Host") or "").lower() in self.hosts

    def _schluessel_passt(self, wert):
        # compare_digest vergleicht zeitkonstant, wirft aber bei Nicht-ASCII-Text – darum vorher prüfen
        return bool(wert) and wert.isascii() and hmac.compare_digest(wert, self.schluessel)

    def _zugang_ok(self):
        kopf = self.headers.get("X-Zugang", "")
        cookie = ""
        for teil in (self.headers.get("Cookie") or "").split(";"):
            name, _, wert = teil.strip().partition("=")
            if name == "autonomous_zugang":
                cookie = wert
        return any(self._schluessel_passt(w) for w in (kopf, cookie))

    def _herkunft_ok(self):
        herkunft = self.headers.get("Origin")
        if not herkunft:
            return True  # z. B. Kommandozeile mit Schlüssel
        return herkunft.strip().lower() in self.herkuenfte

    # ---- Methoden ----
    def do_HEAD(self):
        self.do_GET()

    def do_GET(self):
        self._verarbeiten("GET")

    def do_POST(self):
        self._verarbeiten("POST")

    def _verarbeiten(self, methode):
        if not self._host_ok():
            return self._fehler(421, "Unbekannter Host")
        url = urlparse(self.path)
        pfad = url.path
        query = {k: v[0] for k, v in parse_qs(url.query).items()}

        if pfad == "/status":
            s = self.kern.status()
            return self._senden(200, {"system": s["system"], "version": s["version"], "betrieb": s["betrieb"]})

        if not pfad.startswith("/api/"):
            if methode != "GET":
                return self._fehler(405, "Methode nicht erlaubt")
            # Anmeldung über Link mit ?k=SCHLUESSEL: Cookie setzen, Schlüssel aus der Adresse entfernen
            if "k" in query:
                if self._schluessel_passt(query["k"]):
                    return self._senden(303, b"", extra={
                        "Location": "/", "Set-Cookie": "autonomous_zugang=%s; Path=/; HttpOnly; SameSite=Strict; "
                                                       "Max-Age=31536000" % self.schluessel})
                return self._fehler(403, "Falscher Zugangsschlüssel")
            if pfad.startswith("/produkte/"):
                return self._produktdatei(pfad)
            return self._statisch(pfad)

        if not self._zugang_ok():
            return self._fehler(401, "Zugang fehlt – bitte über den Startlink öffnen")
        body = {}
        if methode == "POST":
            if not self._herkunft_ok():
                return self._fehler(403, "Fremde Herkunft")
            if self.headers.get_content_type() != "application/json":
                return self._fehler(415, "Nur JSON")
            angabe = self.headers.get("Content-Length")
            try:
                laenge = int(angabe) if angabe is not None else 0
            except ValueError:
                return self._fehler(400, "Ungültige Längenangabe")
            if laenge < 0 or laenge > MAX_KOERPER:
                return self._fehler(413, "Anfrage zu groß")
            try:
                body = json.loads(self.rfile.read(laenge).decode("utf-8") or "{}") if laenge else {}
            except (ValueError, UnicodeDecodeError, RecursionError):
                return self._fehler(400, "Ungültiges JSON")
            if not isinstance(body, dict):
                return self._fehler(400, "JSON-Objekt erwartet")
        try:
            funktion, parameter = api.finden(methode, pfad)
            ergebnis = funktion(self.kern, {"pfad": pfad, "parameter": parameter, "query": query, "body": body})
            return self._senden(200, ergebnis)
        except api.ApiFehler as f:
            return self._fehler(f.status, f.meldung)
        except PermissionError as f:
            return self._fehler(403, str(f))
        except KeyError as f:
            return self._fehler(404, str(f).strip("'\""))
        except ValueError as f:
            return self._fehler(400, str(f))
        except Exception:
            self.kern.protokoll.fehler("server", "Interner Fehler", {"pfad": pfad, "fehler": traceback.format_exc()})
            return self._fehler(500, "Interner Fehler – steht im Protokoll")

    def _statisch(self, pfad):
        if pfad in ("", "/"):
            pfad = "/index.html"
        name = os.path.normpath(pfad.lstrip("/"))
        if name.startswith("..") or os.path.isabs(name):
            return self._fehler(404, "Nicht gefunden")
        datei = os.path.join(konfig.UI, name)
        if not os.path.realpath(datei).startswith(os.path.realpath(konfig.UI) + os.sep) or not os.path.isfile(datei):
            return self._fehler(404, "Nicht gefunden")
        typ = mimetypes.guess_type(datei)[0] or "application/octet-stream"
        if typ.startswith("text/") or typ in ("application/javascript", "application/json", "image/svg+xml"):
            typ += "; charset=utf-8"
        with open(datei, "rb") as f:
            return self._senden(200, f.read(), typ)

    def _produktdatei(self, pfad):
        """Erzeugte Produkte (Webseiten, Angebote) ansehen – nur mit Zugang, nur aus dem Produktordner."""
        if not self._zugang_ok():
            return self._fehler(401, "Zugang fehlt")
        wurzel = os.path.realpath(konfig.unterordner("produkte"))
        datei = os.path.realpath(os.path.join(wurzel, os.path.normpath(pfad[len("/produkte/"):])))
        if not datei.startswith(wurzel + os.sep) or not os.path.isfile(datei):
            return self._fehler(404, "Nicht gefunden")
        typ = mimetypes.guess_type(datei)[0] or "application/octet-stream"
        if typ.startswith("text/"):
            typ += "; charset=utf-8"
        with open(datei, "rb") as f:
            # Erzeugte Seiten laufen ohne Skripte und ohne Netz – nur eingebettete Stile und Bilder
            return self._senden(200, f.read(), typ, csp=PRODUKT_CSP)


class WlanZugang:
    """iPhone im eigenen WLAN: lauscht ZUSÄTZLICH auf den privaten Adressen dieses Rechners (kein Neustart).

    Ausgeschaltet (Standard) ist AUTONOMOUS nur über 127.0.0.1 erreichbar. Eingeschaltet werden genau die
    eigenen privaten Adressen und der Bonjour-Name (…​.local) als Host und Herkunft erlaubt – sonst nichts.
    Schalten darf nur der Eigentümer (über die Oberfläche bzw. die API mit Zugangsschlüssel)."""

    def __init__(self, kern, port):
        self.kern = kern
        self.port = port
        self._server = []
        self.adressen = []
        self.name = None
        self._sperre = threading.Lock()

    @property
    def aktiv(self):
        return bool(self._server)

    def an(self):
        from . import wlan
        with self._sperre:
            if self._server:
                return
            adressen = wlan.private_adressen()
            if not adressen:
                raise ValueError("Kein eigenes WLAN erkannt (keine private Adresse wie 192.168.x.x). "
                                 "Bitte den Mac mit dem WLAN verbinden und erneut versuchen.")
            gestartet = []
            try:
                for adresse in adressen:
                    srv = ThreadingHTTPServer((adresse, self.port), Handler)
                    srv.daemon_threads = True
                    threading.Thread(target=srv.serve_forever, name="wlan-%s" % adresse, daemon=True).start()
                    gestartet.append(srv)
            except OSError as fehler:
                for srv in gestartet:
                    srv.shutdown()
                    srv.server_close()
                raise ValueError("WLAN-Zugriff konnte nicht gestartet werden: %s" % fehler)
            self._server, self.adressen, self.name = gestartet, adressen, wlan.lokaler_name()
            namen = list(adressen) + ([self.name] if self.name else [])
            # neue Mengen zuweisen (nicht verändern) – laufende Anfragen sehen immer einen vollständigen Stand
            Handler.hosts = set(Handler.hosts) | {"%s:%d" % (n, self.port) for n in namen}
            Handler.herkuenfte = set(Handler.herkuenfte) | {"http://%s:%d" % (n, self.port) for n in namen}
            self.kern.protokoll.audit("wlan", "WLAN-Zugriff eingeschaltet", {"adressen": adressen})

    def aus(self):
        with self._sperre:
            server, self._server = self._server, []
            Handler.hosts = erlaubte_hosts(self.port)
            Handler.herkuenfte = erlaubte_herkuenfte(self.port)
            for srv in server:
                srv.shutdown()
                srv.server_close()
            if server:
                self.kern.protokoll.audit("wlan", "WLAN-Zugriff ausgeschaltet")

    def status(self):
        from . import wlan
        ergebnis = {"erlaubt": bool(self.kern.einstellungen.hole("wlan_zugriff")), "aktiv": self.aktiv,
                    "port": self.port}
        if self.aktiv:
            link = "http://%s:%d/?k=%s" % (self.adressen[0], self.port, Handler.schluessel)
            ergebnis.update({"adressen": list(self.adressen), "name": self.name, "link": link,
                             "qr": wlan.qr_daten(link)})
        else:
            ergebnis["moegliche_adressen"] = wlan.private_adressen()
        return ergebnis


def starten(kern, host=None, port=None):
    host = host or konfig.HOST
    port = konfig.PORT if port is None else port
    Handler.kern = kern
    Handler.schluessel = zugangsschluessel()
    server = ThreadingHTTPServer((host, port), Handler)
    server.daemon_threads = True
    port = server.server_address[1]  # bei Port 0 erst nach dem Binden bekannt
    Handler.hosts = erlaubte_hosts(port)
    Handler.herkuenfte = erlaubte_herkuenfte(port)
    kern.wlan = WlanZugang(kern, port)
    if kern.einstellungen.hole("wlan_zugriff"):
        try:
            kern.wlan.an()
        except ValueError as fehler:  # z. B. Mac gerade nicht im WLAN – AUTONOMOUS läuft trotzdem lokal
            kern.protokoll.warnung("wlan", "WLAN-Zugriff beim Start nicht möglich", str(fehler))
    return server


def taegliche_sicherung(kern, stopp):
    """Einmal pro Tag eine Sicherung, solange das System läuft."""
    while not stopp.is_set():
        letzte = kern._letzte_sicherung()
        heute = __import__("datetime").date.today().strftime("%Y%m%d")
        if not letzte or heute not in letzte:
            try:
                sicherung.sichern(kern, "täglich")
            except Exception as fehler:
                kern.protokoll.fehler("sicherung", "Tägliche Sicherung fehlgeschlagen", str(fehler))
        stopp.wait(3600)


AUFTRAGSSUCHE_ABSTAND_STUNDEN = 20


def auftragssuche_anstossen(kern):
    """Legt höchstens alle 20 Stunden eine Suche nach Ausschreibungen an – nur wenn der Eigentümer
    die Internet-Recherche UND die tägliche Suche eingeschaltet hat. Gibt die Aufgaben-ID oder None zurück."""
    e = kern.einstellungen.alle()
    if not (e.get("internet_recherche_erlaubt") and e.get("auftragssuche_taeglich")):
        return None
    if kern.register.hole("akquise") is None:
        return None
    grenze = (datetime.datetime.now().astimezone()
              - datetime.timedelta(hours=AUFTRAGSSUCHE_ABSTAND_STUNDEN)).isoformat(timespec="seconds")
    if kern.db.eins("SELECT id FROM aufgaben WHERE typ='ausschreibungen_suchen' AND "
                    "(erstellt >= ? OR status IN ('geplant','bereit','laufend'))", (grenze,)):
        return None
    if kern.db.eins("SELECT id FROM suchlaeufe WHERE zeit >= ?", (grenze,)):
        return None
    aid = kern.aufgaben.anlegen("Tägliche Suche nach Ausschreibungen", "ausschreibungen_suchen", "akquise",
                                "zeitplan", {}, 3, max_versuche=2)
    kern.protokoll.info("zeitplan", "Tägliche Ausschreibungssuche angelegt", {"aufgabe": aid})
    return aid


def taegliche_auftragssuche(kern, stopp):
    """Prüft einmal pro Stunde, ob die tägliche Ausschreibungssuche fällig ist."""
    while not stopp.is_set():
        try:
            auftragssuche_anstossen(kern)
        except Exception as fehler:
            kern.protokoll.fehler("zeitplan", "Ausschreibungssuche konnte nicht angelegt werden", str(fehler))
        stopp.wait(3600)


def ueberlebensplan_anstossen(kern):
    """Legt höchstens einen Überlebensplan je Tag an – nur wenn der Eigentümer ihn nicht ausgeschaltet hat
    (Einstellung „ueberlebensplan_taeglich“, Standard: an). Gibt die Aufgaben-ID oder None zurück.
    Der Plan liest nur echte Zahlen und stößt nur interne Folgeaufgaben an – er sendet und bezahlt nichts."""
    if not kern.einstellungen.hole("ueberlebensplan_taeglich"):
        return None
    try:
        from . import ueberleben
    except ImportError:  # Modul nicht vorhanden – der Rest läuft weiter
        return None
    return ueberleben.zeitplan_pruefen(kern)


def taeglicher_ueberlebensplan(kern, stopp):
    """Prüft einmal pro Stunde, ob der tägliche Überlebensplan fällig ist."""
    while not stopp.is_set():
        try:
            ueberlebensplan_anstossen(kern)
        except Exception as fehler:
            kern.protokoll.fehler("zeitplan", "Überlebensplan konnte nicht angelegt werden", str(fehler))
        stopp.wait(3600)


def hintergrund(kern):
    stopp = threading.Event()
    for ziel in (taegliche_sicherung, taegliche_auftragssuche, taeglicher_ueberlebensplan):
        threading.Thread(target=ziel, args=(kern, stopp), daemon=True).start()
    return stopp
