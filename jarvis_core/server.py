# -*- coding: utf-8 -*-
"""Der lokale JARVIS-Server.

Endpunkte:
    GET  /              Statusseite zum Ansehen im Browser
    GET  /status        Status als JSON
    GET  /api/logs      die letzten Log-Einträge (?anzahl=50)
    POST /api/anfrage   eine Anfrage annehmen: {"text": "..."}

In Phase 2 nimmt der Server Anfragen an, prüft und protokolliert sie und
bestätigt sie. Beantwortet werden sie erst ab Phase 3, wenn Claude Code
angebunden ist - das steht so auch in jeder Antwort.

Sicherheit: Der Server hört nur auf 127.0.0.1. Zusätzlich muss der Host-Kopf
auf die eigene Maschine zeigen (schützt vor DNS-Rebinding), und eine Anfrage
aus dem Browser wird nur von der eigenen Statusseite angenommen.
"""

import datetime
import html
import json
import os
import platform
import signal
import threading
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from . import PHASE, VERSION
from .protokoll import letzte_eintraege

MAX_KOERPER = 64 * 1024
MAX_TEXT = 10000
LOKALE_NAMEN = ("127.0.0.1", "localhost", "[::1]")


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


class JarvisServer:
    def __init__(self, konfig, protokoll):
        self.konfig = konfig
        self.log = protokoll
        self.gestartet = None
        self.anfragen = 0
        self._sperre = threading.Lock()
        self._httpd = None

    # ------------------------------------------------------------ Status ---

    def status(self):
        jetzt = time.time()
        return {
            "name": "JARVIS",
            "version": VERSION,
            "phase": PHASE,
            "laeuft": True,
            "seit": datetime.datetime.fromtimestamp(self.gestartet).astimezone().isoformat(timespec="seconds"),
            "laufzeit_sekunden": int(jetzt - self.gestartet),
            "pid": os.getpid(),
            "adresse": self.konfig.adresse,
            "python": platform.python_version(),
            "anfragen": self.anfragen,
            "provider": {"claude_code": "noch nicht angebunden (Phase 3)"},
            "daten_ordner": self.konfig.daten_ordner,
        }

    def anfrage_annehmen(self, text):
        with self._sperre:
            self.anfragen += 1
        kennung = uuid.uuid4().hex[:12]
        self.log.ereignis("anfrage_angenommen", id=kennung, laenge=len(text), anfang=text[:200])
        return {
            "ok": True,
            "id": kennung,
            "status": "angenommen",
            "antwort": None,
            "hinweis": "Die Anfrage ist angekommen und protokolliert. Beantwortet wird sie ab Phase 3, "
                       "wenn Claude Code angebunden ist.",
        }

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

    def starten(self, signale=True):
        """Startet den Server und blockiert, bis er gestoppt wird."""
        self._pid_schreiben()
        try:
            self._httpd = ThreadingHTTPServer((self.konfig.host, self.konfig.port), _handler_fuer(self))
        except OSError as fehler:
            self._pid_entfernen()
            self.log.ereignis("start_fehlgeschlagen", "ERROR", grund=str(fehler), port=self.konfig.port)
            raise
        self._httpd.daemon_threads = True
        self.gestartet = time.time()
        if signale:
            signal.signal(signal.SIGTERM, self._signal)
            signal.signal(signal.SIGINT, self._signal)
        self.log.ereignis("server_gestartet", adresse=self.konfig.adresse, pid=os.getpid(),
                          version=VERSION, python=platform.python_version())
        try:
            self._httpd.serve_forever(poll_interval=0.5)
        finally:
            self._httpd.server_close()
            self._pid_entfernen()
            self.log.ereignis("server_gestoppt", laufzeit_sekunden=int(time.time() - self.gestartet),
                              anfragen=self.anfragen)

    def _signal(self, nummer, _rahmen):
        self.log.ereignis("stopp_signal", signal=nummer)
        # shutdown() wartet auf serve_forever - deshalb aus einem eigenen Faden.
        threading.Thread(target=self.stoppen, daemon=True).start()

    def stoppen(self):
        if self._httpd:
            self._httpd.shutdown()

    def bereit(self):
        return self.gestartet is not None


def _handler_fuer(server):
    erlaubte_herkunft = {"http://%s:%d" % (name, server.konfig.port) for name in LOKALE_NAMEN}

    class Handler(BaseHTTPRequestHandler):
        server_version = "JARVIS/" + VERSION
        sys_version = ""

        def log_message(self, format, *args):
            pass  # eigene, strukturierte Logs statt der Standardausgabe

        # -------------------------------------------------------- Helfer ---

        def _host_erlaubt(self):
            host = (self.headers.get("Host") or "").strip().lower()
            if host.startswith("["):
                name = host.split("]")[0] + "]"
            else:
                name = host.split(":")[0]
            return name in LOKALE_NAMEN

        def _senden(self, code, daten, art="application/json; charset=utf-8"):
            koerper = daten if isinstance(daten, bytes) else json.dumps(daten, ensure_ascii=False).encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", art)
            self.send_header("Content-Length", str(len(koerper)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("X-Frame-Options", "DENY")
            self.end_headers()
            self.wfile.write(koerper)

        def _fehler(self, code, meldung):
            self._senden(code, {"ok": False, "fehler": meldung})

        # --------------------------------------------------------- GET ---

        def do_GET(self):
            if not self._host_erlaubt():
                server.log.ereignis("zugriff_abgelehnt", "WARNING", grund="host", host=self.headers.get("Host"))
                return self._fehler(403, "Nur von dieser Maschine aus erreichbar.")
            teile = urlparse(self.path)
            if teile.path == "/status":
                return self._senden(200, server.status())
            if teile.path == "/api/logs":
                try:
                    anzahl = int(parse_qs(teile.query).get("anzahl", ["50"])[0])
                except ValueError:
                    return self._fehler(400, "anzahl muss eine Zahl sein.")
                anzahl = max(1, min(anzahl, 500))
                return self._senden(200, {"ok": True, "eintraege": letzte_eintraege(server.log.datei, anzahl)})
            if teile.path == "/":
                return self._senden(200, _statusseite(server.status()).encode("utf-8"), "text/html; charset=utf-8")
            return self._fehler(404, "Unbekannter Pfad.")

        # -------------------------------------------------------- POST ---

        def do_POST(self):
            if not self._host_erlaubt():
                server.log.ereignis("zugriff_abgelehnt", "WARNING", grund="host", host=self.headers.get("Host"))
                return self._fehler(403, "Nur von dieser Maschine aus erreichbar.")
            herkunft = self.headers.get("Origin")
            if herkunft and herkunft not in erlaubte_herkunft:
                server.log.ereignis("zugriff_abgelehnt", "WARNING", grund="origin", origin=herkunft)
                return self._fehler(403, "Anfragen von fremden Webseiten werden abgelehnt.")
            if urlparse(self.path).path != "/api/anfrage":
                return self._fehler(404, "Unbekannter Pfad.")
            if "application/json" not in (self.headers.get("Content-Type") or ""):
                return self._fehler(415, "Bitte JSON senden (Content-Type: application/json).")
            try:
                laenge = int(self.headers.get("Content-Length") or 0)
            except ValueError:
                return self._fehler(400, "Ungültige Länge.")
            if laenge <= 0:
                return self._fehler(400, "Die Anfrage ist leer.")
            if laenge > MAX_KOERPER:
                return self._fehler(413, "Die Anfrage ist zu groß.")
            try:
                daten = json.loads(self.rfile.read(laenge).decode("utf-8"))
            except (ValueError, UnicodeDecodeError):
                return self._fehler(400, "Kein gültiges JSON.")
            text = daten.get("text") if isinstance(daten, dict) else None
            if not isinstance(text, str) or not text.strip():
                return self._fehler(400, "Feld \"text\" fehlt oder ist leer.")
            if len(text) > MAX_TEXT:
                return self._fehler(413, "Der Text ist länger als %d Zeichen." % MAX_TEXT)
            return self._senden(200, server.anfrage_annehmen(text.strip()))

    return Handler


def _statusseite(status):
    z = {k: html.escape(str(v)) for k, v in status.items() if not isinstance(v, dict)}
    provider = html.escape(status["provider"]["claude_code"])
    return """<!DOCTYPE html>
<html lang="de"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta http-equiv="refresh" content="10">
<title>JARVIS Status</title>
<style>
  :root{--bg:#05070a;--fl:#11161d;--li:rgba(0,229,255,.25);--tx:#f2f6fa;--mu:#9aa8b6;--cy:#00e5ff;--gr:#35e0a1}
  body{margin:0;background:var(--bg);color:var(--tx);font:16px/1.5 -apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif}
  main{max-width:640px;margin:0 auto;padding:24px 16px}
  h1{letter-spacing:.2em;margin:0 0 4px}
  .ok{color:var(--gr);font-weight:600}
  table{width:100%%;border-collapse:collapse;margin-top:16px;background:var(--fl);border:1px solid var(--li);border-radius:12px;overflow:hidden}
  td{padding:10px 14px;border-bottom:1px solid var(--li)}
  td:first-child{color:var(--mu);width:40%%}
  p{color:var(--mu);font-size:14px}
</style></head><body><main>
<h1>JARVIS</h1>
<div class="ok">● läuft</div>
<table>
<tr><td>Adresse</td><td>%(adresse)s</td></tr>
<tr><td>Läuft seit</td><td>%(seit)s</td></tr>
<tr><td>Laufzeit</td><td>%(laufzeit_sekunden)s Sekunden</td></tr>
<tr><td>Anfragen</td><td>%(anfragen)s</td></tr>
<tr><td>Claude Code</td><td>%(provider)s</td></tr>
<tr><td>Version</td><td>%(version)s (Phase %(phase)s)</td></tr>
<tr><td>Python</td><td>%(python)s</td></tr>
<tr><td>Prozess</td><td>%(pid)s</td></tr>
<tr><td>Daten</td><td>%(daten_ordner)s</td></tr>
</table>
<p>Nur auf diesem Mac erreichbar. Die Seite aktualisiert sich alle 10 Sekunden.
Stoppen: <code>./jarvis.sh stopp</code></p>
</main></body></html>
""" % dict(z, provider=provider)
