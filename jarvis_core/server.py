# -*- coding: utf-8 -*-
"""Der lokale JARVIS-Server - HTTP-Hülle um Agent, Läufer, Zeitplan und Oberfläche.

Erreichbar ist er standardmäßig nur auf 127.0.0.1. Jede Anfrage durchläuft:

1. Host-Prüfung (Schutz vor DNS-Rebinding): der Host-Kopf muss auf diesen Mac zeigen
2. bei POST: Herkunftsprüfung (keine fremden Webseiten)
3. Zugangsschlüssel für alles unter ``/api/`` (Cookie oder Kopfzeile)
4. Ratenbegrenzung
5. Größen- und Formatprüfung

Offen (ohne Schlüssel) sind nur ``/status`` (harmlose Angaben) und die Dateien der
Oberfläche, die selbst keine Daten enthalten. Der Link mit Schlüssel entsteht mit
``./jarvis.sh link``; das Öffnen setzt ein Cookie und entfernt den Schlüssel aus der Adresse.
"""

import datetime
import json
import os
import platform
import signal
import socket
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from . import PHASE, VERSION, umgebung, zeit
from .agent import Agent
from .api import Api
from .auth import Ratenbegrenzer, Zugang
from .laeufer import Laeufer, wiederanlauf
from .planer import Planer
from .provider import ProviderManager
from .speicher import Speicher
from .stimme import Stimme
from .zeitplan import Zeitplan

OBERFLAECHE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "oberflaeche")
STATISCH = {
    "/": ("index.html", "text/html; charset=utf-8"),
    "/stil.css": ("stil.css", "text/css; charset=utf-8"),
    "/kern.js": ("kern.js", "application/javascript; charset=utf-8"),
    "/app.js": ("app.js", "application/javascript; charset=utf-8"),
    "/icon.svg": ("icon.svg", "image/svg+xml"),
}
CSP = ("default-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self'; "
       "frame-ancestors 'none'; base-uri 'none'; form-action 'none'")
MAX_KOERPER = 256 * 1024
LOKALE_NAMEN = ("127.0.0.1", "localhost", "[::1]")
TEUER = ("/api/anfrage", "/api/auftrag")


class PidFehler(Exception):
    pass


def prozess_laeuft(pid):
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def pid_lesen(pid_datei):
    try:
        with open(pid_datei, "r", encoding="utf-8") as f:
            return int(f.read().strip())
    except (OSError, ValueError):
        return None


def primaere_ip():
    """Die Adresse des Macs im WLAN (es wird nichts gesendet)."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("10.255.255.255", 1))
        return s.getsockname()[0]
    except OSError:
        return None
    finally:
        s.close()


class JarvisServer:
    def __init__(self, konfig, protokoll):
        self.konfig = konfig
        self.log = protokoll
        self.speicher = Speicher(konfig.db_datei)
        self.provider = ProviderManager(konfig, protokoll)
        self.stimme = Stimme(konfig)
        self.agent = Agent(konfig, protokoll, self.speicher, self.provider, stimme=self.stimme)
        self.agent.planer = Planer(self.agent)
        self.laeufer = Laeufer(self.agent)
        self.zeitplan = Zeitplan(self.agent, self.laeufer)
        self.zugang = Zugang(konfig)
        self.raten = Ratenbegrenzer()
        self.api = Api(self)
        self.gestartet = None
        self.anfragen = 0
        self.zaehlsperre = threading.Lock()
        self._httpd = None

    # ------------------------------------------------------------ Status ---

    def status(self):
        """Harmlose Angaben, auch ohne Zugangsschlüssel abrufbar."""
        return {
            "name": "JARVIS", "version": VERSION, "phase": PHASE, "laeuft": True,
            "seit": datetime.datetime.fromtimestamp(self.gestartet).astimezone().isoformat(timespec="seconds"),
            "laufzeit_sekunden": int(time.time() - self.gestartet), "pid": os.getpid(), "adresse": self.konfig.adresse,
            "python": platform.python_version(), "anfragen": self.anfragen,
            "gesperrt": self.agent.gesperrt.is_set(), "lan": bool(self.konfig.lan),
        }

    def lokale_namen(self):
        """Hostnamen, unter denen der Server angesprochen werden darf (nur dieser Mac, im WLAN-Modus auch dessen Adresse)."""
        namen = set(LOKALE_NAMEN)
        if self.konfig.lan:
            rechner = socket.gethostname().lower()
            namen.update({rechner, rechner if rechner.endswith(".local") else rechner + ".local"})
            ip = primaere_ip()
            if ip:
                namen.add(ip)
        return namen

    # ----------------------------------------------------------- Ablauf ---

    def _pid_schreiben(self):
        alt = pid_lesen(self.konfig.pid_datei)
        if alt and alt != os.getpid() and prozess_laeuft(alt):
            raise PidFehler("JARVIS läuft schon (Prozess %d)." % alt)
        with open(self.konfig.pid_datei, "w", encoding="utf-8") as f:
            f.write(str(os.getpid()))

    def _pid_entfernen(self):
        if pid_lesen(self.konfig.pid_datei) == os.getpid():
            try:
                os.remove(self.konfig.pid_datei)
            except OSError:
                pass

    def _hintergrund(self):
        """Nach dem Start: Anbieter prüfen, Umgebung auffrischen (höchstens einmal am Tag)."""
        try:
            self.provider.pruefen()
            letzte = self.speicher.meta("umgebung_geprueft")
            if not letzte or letzte < zeit.vor_stunden(24):
                self.agent.umgebung_merken(umgebung.sammeln(self.konfig))
                self.speicher.meta_setzen("umgebung_geprueft", zeit.jetzt())
        except Exception as fehler:  # noqa: BLE001 - Hintergrundprüfung darf den Start nie stören
            self.log.ereignis("hintergrund_fehler", "WARNING", grund=repr(fehler))

    def starten(self, signale=True):
        """Startet den Server und blockiert, bis er gestoppt wird."""
        self._pid_schreiben()
        try:
            self._httpd = ThreadingHTTPServer((self.konfig.bind_adresse, self.konfig.port), _handler_fuer(self))
        except OSError as fehler:
            self._pid_entfernen()
            self.log.ereignis("start_fehlgeschlagen", "ERROR", grund=str(fehler), port=self.konfig.port)
            raise
        self._httpd.daemon_threads = True
        self.gestartet = time.time()
        if signale:
            signal.signal(signal.SIGTERM, self._signal)
            signal.signal(signal.SIGINT, self._signal)
        unterbrochen = wiederanlauf(self.agent)
        if self.speicher.meta("profil_importiert") is None:
            ergebnis = self.agent.profil_einlesen()
            self.log.ereignis("profil_import", **{k: v for k, v in ergebnis.items() if k != "ok"})
        self.laeufer.start()
        self.zeitplan.start()
        threading.Thread(target=self._hintergrund, daemon=True, name="jarvis-hintergrund").start()
        self.log.ereignis("server_gestartet", adresse=self.konfig.adresse, bindung=self.konfig.bind_adresse, pid=os.getpid(),
                          version=VERSION, python=platform.python_version(), unterbrochene_auftraege=unterbrochen,
                          gesperrt=self.agent.gesperrt.is_set())
        try:
            self._httpd.serve_forever(poll_interval=0.5)
        finally:
            self.laeufer.beenden()
            self.zeitplan.beenden()
            self.provider.abbrechen()
            self.stimme.stopp()
            self._httpd.server_close()
            self.laeufer.join(timeout=5)
            self.log.ereignis("server_gestoppt", laufzeit_sekunden=int(time.time() - self.gestartet), anfragen=self.anfragen)
            self.speicher.schliessen()
            self._pid_entfernen()

    def _signal(self, nummer, _rahmen):
        self.log.ereignis("stopp_signal", signal=nummer)
        threading.Thread(target=self.stoppen, daemon=True).start()  # shutdown() wartet auf serve_forever

    def stoppen(self):
        if self._httpd:
            self._httpd.shutdown()

    def bereit(self):
        return self.gestartet is not None


def _handler_fuer(server):
    namen = server.lokale_namen()
    herkuenfte = {"http://%s:%d" % (n, server.konfig.port) for n in namen}

    class Handler(BaseHTTPRequestHandler):
        server_version = "JARVIS/" + VERSION
        sys_version = ""
        timeout = 60  # Sekunden ohne Daten vom Gegenüber: Verbindung beenden (Schutz vor hängenden Verbindungen)

        def log_message(self, format, *args):
            pass  # eigene, strukturierte Logs statt der Standardausgabe

        # ---------------------------------------------------------- Helfer ---

        def _host_erlaubt(self):
            host = (self.headers.get("Host") or "").strip().lower()
            name = host.split("]")[0] + "]" if host.startswith("[") else host.split(":")[0]
            return name in namen

        def _senden(self, code, daten, art="application/json; charset=utf-8", extra=None):
            koerper = daten if isinstance(daten, bytes) else json.dumps(daten, ensure_ascii=False).encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", art)
            self.send_header("Content-Length", str(len(koerper)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("X-Frame-Options", "DENY")
            self.send_header("Referrer-Policy", "no-referrer")
            if art.startswith("text/html"):
                self.send_header("Content-Security-Policy", CSP)
            for name, wert in (extra or {}).items():
                self.send_header(name, wert)
            self.end_headers()
            self.wfile.write(koerper)

        def _fehler(self, code, meldung, art=None, extra=None):
            self._senden(code, {"ok": False, "art": art, "fehler": meldung}, extra=extra)

        def _abgelehnt(self, grund, **felder):
            server.log.ereignis("zugriff_abgelehnt", "WARNING", grund=grund, **felder)

        def _pruefen_basis(self):
            """Host und (bei POST) Herkunft. Gibt True zurück, wenn es weitergehen darf."""
            if not self._host_erlaubt():
                self._abgelehnt("host", host=self.headers.get("Host"))
                self._fehler(403, "Nur von diesem Mac aus erreichbar.", "host")
                return False
            if self.command == "POST":
                herkunft = self.headers.get("Origin")
                if herkunft and herkunft not in herkuenfte:
                    self._abgelehnt("origin", origin=herkunft)
                    self._fehler(403, "Anfragen von fremden Webseiten werden abgelehnt.", "origin")
                    return False
                if self.headers.get("Sec-Fetch-Site") not in (None, "same-origin", "none"):
                    self._abgelehnt("fetch_site", site=self.headers.get("Sec-Fetch-Site"))
                    self._fehler(403, "Anfragen von fremden Webseiten werden abgelehnt.", "origin")
                    return False
            return True

        def _pruefen_api(self, pfad):
            if not server.zugang.pruefen(self.headers):
                self._abgelehnt("zugang", pfad=pfad)
                self._fehler(401, "Zugang nur mit dem Link von ./jarvis.sh link.", "zugang")
                return False
            if self.command == "GET":
                gruppe, maximum = "lesen", 900
            elif pfad in TEUER:
                gruppe, maximum = "teuer", server.konfig.anfragen_pro_minute
            else:
                gruppe, maximum = "schreiben", max(120, server.konfig.anfragen_pro_minute * 6)
            erlaubt, warten = server.raten.erlauben(gruppe, maximum)
            if not erlaubt:
                self._abgelehnt("rate", gruppe=gruppe)
                self._fehler(429, "Zu viele Anfragen. Bitte in %d Sekunden nochmal." % warten, "rate",
                             extra={"Retry-After": str(warten)})
                return False
            return True

        def _koerper(self):
            """Liest den JSON-Körper. Gibt (dict, None) oder (None, (Code, Meldung)) zurück."""
            if "application/json" not in (self.headers.get("Content-Type") or ""):
                return None, (415, "Bitte JSON senden (Content-Type: application/json).")
            try:
                laenge = int(self.headers.get("Content-Length") or 0)
            except ValueError:
                return None, (400, "Ungültige Länge.")
            if laenge <= 0:
                return None, (400, "Die Anfrage ist leer.")
            if laenge > MAX_KOERPER:
                return None, (413, "Die Anfrage ist zu groß.")
            try:
                daten = json.loads(self.rfile.read(laenge).decode("utf-8"))
            except (ValueError, UnicodeDecodeError):
                return None, (400, "Kein gültiges JSON.")
            if not isinstance(daten, dict):
                return None, (400, "Erwartet wird ein JSON-Objekt.")
            return daten, None

        def _antwort_aus_api(self, ergebnis):
            if ergebnis is None:
                return self._fehler(404, "Unbekannter Pfad.")
            code, antwort = ergebnis
            return self._senden(code, antwort)

        # ------------------------------------------------------------- GET ---

        def do_GET(self):
            if not self._pruefen_basis():
                return None
            teile = urlparse(self.path)
            pfad = teile.path
            query = {k: v[0] for k, v in parse_qs(teile.query).items()}
            if pfad == "/status":
                return self._senden(200, server.status())
            if pfad.startswith("/api/"):
                if not self._pruefen_api(pfad):
                    return None
                try:
                    return self._antwort_aus_api(server.api.get(pfad, query))
                except Exception as fehler:  # noqa: BLE001 - nie ohne Antwort abbrechen
                    server.log.ereignis("interner_fehler", "ERROR", pfad=pfad, grund=repr(fehler))
                    return self._fehler(500, "Interner Fehler – Details im Log.")
            if pfad == "/" and "t" in query:
                if server.zugang.passt(query["t"]):
                    return self._senden(302, b"", "text/plain", {"Location": "/", "Set-Cookie": server.zugang.cookie_kopf()})
                self._abgelehnt("zugang", pfad="/")
                return self._fehler(401, "Dieser Zugangslink stimmt nicht. Neuen holen: ./jarvis.sh link", "zugang")
            if pfad in STATISCH:
                datei, art = STATISCH[pfad]
                try:
                    with open(os.path.join(OBERFLAECHE, datei), "rb") as f:
                        return self._senden(200, f.read(), art)
                except OSError:
                    return self._fehler(404, "Die Oberfläche fehlt (%s)." % datei)
            return self._fehler(404, "Unbekannter Pfad.")

        # ------------------------------------------------------------ POST ---

        def do_POST(self):
            if not self._pruefen_basis():
                return None
            pfad = urlparse(self.path).path
            if not pfad.startswith("/api/"):
                return self._fehler(404, "Unbekannter Pfad.")
            if not self._pruefen_api(pfad):
                return None
            daten, problem = self._koerper()
            if problem:
                return self._fehler(problem[0], problem[1])
            try:
                return self._antwort_aus_api(server.api.post(pfad, daten))
            except Exception as fehler:  # noqa: BLE001 - nie ohne Antwort abbrechen
                server.log.ereignis("interner_fehler", "ERROR", pfad=pfad, grund=repr(fehler))
                return self._fehler(500, "Interner Fehler – Details im Log.")

    return Handler
