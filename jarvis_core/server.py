# -*- coding: utf-8 -*-
"""Der lokale JARVIS-Server.

Endpunkte:
    GET  /                      Statusseite mit Eingabefeld
    GET  /status                Status als JSON (inklusive Anbieter)
    GET  /api/logs              die letzten Log-Einträge (?anzahl=50)
    POST /api/anfrage           {"text": "...", "gespraech": "<optional>"} -> Antwort von Claude Code
    POST /api/provider/pruefen  Anbieter neu prüfen (verbraucht kein Kontingent)

Ein Gespräch wird über seine Kennung fortgesetzt: Die Antwort enthält
"gespraech", und wer sie bei der nächsten Anfrage mitschickt, setzt das
Gespräch fort. Die Zuordnung zur Claude-Code-Sitzung liegt in
gespraeche.json im Datenordner und übersteht einen Neustart.

Sicherheit: Der Server hört nur auf 127.0.0.1. Zusätzlich muss der Host-Kopf
auf die eigene Maschine zeigen (schützt vor DNS-Rebinding), und eine Anfrage
aus dem Browser wird nur von der eigenen Statusseite angenommen.
"""

import datetime
import html
import json
import os
import platform
import re
import signal
import threading
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from . import PHASE, VERSION, wissen
from .protokoll import letzte_eintraege
from .provider import ProviderFehler, ProviderManager

MAX_KOERPER = 64 * 1024
MAX_TEXT = 10000
LOKALE_NAMEN = ("127.0.0.1", "localhost", "[::1]")
GESPRAECH_MUSTER = re.compile(r"^[0-9a-f]{8,32}$")
# Welcher HTTP-Code zu welchem Anbieterfehler gehört.
FEHLER_CODES = {"nicht_installiert": 503, "nicht_angemeldet": 503, "nicht_erlaubt": 503, "kein_provider": 503,
                "limit": 429, "beschaeftigt": 429, "zeitueberschreitung": 504, "fehler": 502}


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
        self.provider = ProviderManager(konfig, protokoll)
        self.system, self.wissen = wissen.system_prompt()
        self._gespraeche_datei = os.path.join(konfig.daten_ordner, "gespraeche.json")
        self._gespraeche = self._gespraeche_laden()

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
            "provider": self.provider.status(),
            "wissen": self.wissen,
            "daten_ordner": self.konfig.daten_ordner,
        }

    # -------------------------------------------------------- Gespräche ---

    def _gespraeche_laden(self):
        try:
            with open(self._gespraeche_datei, "r", encoding="utf-8") as f:
                daten = json.load(f)
            return daten if isinstance(daten, dict) else {}
        except (OSError, ValueError):
            return {}

    def _gespraech_merken(self, gespraech, sitzung):
        with self._sperre:
            self._gespraeche[gespraech] = {"sitzung": sitzung,
                                           "geaendert": datetime.datetime.now().isoformat(timespec="seconds")}
            zwischen = self._gespraeche_datei + ".neu"
            with open(zwischen, "w", encoding="utf-8") as f:
                json.dump(self._gespraeche, f, indent=2)
            os.replace(zwischen, self._gespraeche_datei)

    # --------------------------------------------------------- Anfragen ---

    def anfrage_bearbeiten(self, text, gespraech=None):
        """Gibt (HTTP-Code, Antwort) zurück."""
        with self._sperre:
            self.anfragen += 1
        kennung = uuid.uuid4().hex[:12]
        if gespraech is not None and (not isinstance(gespraech, str) or not GESPRAECH_MUSTER.match(gespraech)):
            return 400, {"ok": False, "id": kennung, "fehler": "Ungültige Gesprächskennung."}
        gespraech = gespraech or uuid.uuid4().hex[:16]
        sitzung = self._gespraeche.get(gespraech, {}).get("sitzung")
        self.log.ereignis("anfrage_angenommen", id=kennung, gespraech=gespraech, fortsetzung=bool(sitzung),
                          laenge=len(text), anfang=text[:200])
        try:
            ergebnis = self.provider.fragen(text, self.system, sitzung)
        except ProviderFehler as fehler:
            self.log.ereignis("anfrage_fehlgeschlagen", "WARNING", id=kennung, art=fehler.art, grund=str(fehler))
            return FEHLER_CODES.get(fehler.art, 502), {"ok": False, "id": kennung, "gespraech": gespraech,
                                                       "art": fehler.art, "fehler": str(fehler)}
        if ergebnis.get("sitzung"):
            self._gespraech_merken(gespraech, ergebnis["sitzung"])
        self.log.ereignis("anfrage_beantwortet", id=kennung, provider=ergebnis["provider"],
                          dauer_ms=ergebnis.get("dauer_ms"), laenge=len(ergebnis["antwort"]))
        return 200, {"ok": True, "id": kennung, "gespraech": gespraech, "antwort": ergebnis["antwort"],
                     "provider": ergebnis["provider"], "dauer_ms": ergebnis.get("dauer_ms")}

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
                          version=VERSION, python=platform.python_version(), wissen=self.wissen)
        # Anbieter im Hintergrund prüfen, damit der Start nicht wartet.
        threading.Thread(target=self.provider.pruefen, daemon=True).start()
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
            pfad = urlparse(self.path).path
            if pfad == "/api/provider/pruefen":
                return self._senden(200, {"ok": True, "provider": server.provider.pruefen()})
            if pfad != "/api/anfrage":
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
            try:
                code, antwort = server.anfrage_bearbeiten(text.strip(), daten.get("gespraech"))
            except Exception as fehler:  # noqa: BLE001 - nie ohne Antwort abbrechen
                server.log.ereignis("interner_fehler", "ERROR", grund=repr(fehler))
                return self._fehler(500, "Interner Fehler – Details im Log.")
            return self._senden(code, antwort)

    return Handler


def _statusseite(status):
    z = {k: html.escape(str(v)) for k, v in status.items() if not isinstance(v, (dict, list))}
    zeilen = []
    for p in status["provider"].values():
        farbe = "ok" if p.get("nutzbar") else "aus"
        zeilen.append('<tr><td>%s</td><td><span class="%s">●</span> %s</td></tr>'
                      % (html.escape(p.get("anzeige", p["name"])), farbe, html.escape(p.get("hinweis", ""))))
    wissen_text = html.escape(", ".join(status["wissen"]) or "keine Wissensdateien gefunden")
    return """<!DOCTYPE html>
<html lang="de"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>JARVIS</title>
<style>
  :root{--bg:#05070a;--fl:#11161d;--li:rgba(0,229,255,.25);--tx:#f2f6fa;--mu:#9aa8b6;--cy:#00e5ff;--gr:#35e0a1;--rt:#ff5c7a}
  *{box-sizing:border-box}
  body{margin:0;background:var(--bg);color:var(--tx);font:16px/1.5 -apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif}
  main{max-width:720px;margin:0 auto;padding:24px 16px 40px}
  h1{letter-spacing:.2em;margin:0}
  h2{font-size:13px;letter-spacing:.14em;text-transform:uppercase;color:var(--cy);margin:28px 0 8px}
  .ok{color:var(--gr)} .aus{color:var(--rt)}
  table{width:100%%;border-collapse:collapse;background:var(--fl);border:1px solid var(--li);border-radius:12px;overflow:hidden}
  td{padding:9px 14px;border-bottom:1px solid var(--li);vertical-align:top}
  td:first-child{color:var(--mu);width:34%%}
  textarea{width:100%%;min-height:90px;font:inherit;color:var(--tx);background:var(--fl);border:1px solid var(--li);border-radius:12px;padding:12px}
  button{font:inherit;border:0;border-radius:10px;padding:10px 16px;background:var(--cy);color:var(--bg);font-weight:600;cursor:pointer;margin-top:8px}
  button.zweit{background:transparent;color:var(--cy);border:1px solid var(--li)}
  button:disabled{opacity:.5}
  #verlauf div{margin:10px 0;padding:10px 14px;border-radius:12px;white-space:pre-wrap}
  .du{background:rgba(61,123,255,.18)} .jarvis{background:var(--fl);border:1px solid var(--li)} .fehler{border:1px solid var(--rt)}
  p{color:var(--mu);font-size:14px}
</style></head><body><main>
<h1>JARVIS</h1>
<div class="ok">● Server läuft</div>

<h2>Frag Jarvis</h2>
<div id="verlauf"></div>
<textarea id="text" placeholder="Was soll Jarvis tun? (Strg+Enter sendet)"></textarea>
<button id="senden">Senden</button> <button id="neu" class="zweit">Neues Gespräch</button>

<h2>Anbieter</h2>
<table>%(provider_zeilen)s</table>
<button id="pruefen" class="zweit">Anbieter neu prüfen</button>

<h2>Status</h2>
<table>
<tr><td>Adresse</td><td>%(adresse)s</td></tr>
<tr><td>Läuft seit</td><td>%(seit)s</td></tr>
<tr><td>Anfragen</td><td>%(anfragen)s</td></tr>
<tr><td>Wissen geladen</td><td>%(wissen)s</td></tr>
<tr><td>Version</td><td>%(version)s (Phase %(phase)s), Python %(python)s, Prozess %(pid)s</td></tr>
<tr><td>Daten</td><td>%(daten_ordner)s</td></tr>
</table>
<p>Nur auf diesem Mac erreichbar. Jarvis hat noch keine Werkzeuge: Er antwortet, sucht aber nicht im Internet
und führt nichts aus. Stoppen: <code>./jarvis.sh stopp</code></p>
<script>
(function(){
  var gespraech = null;
  try { gespraech = sessionStorage.getItem("jarvis.gespraech"); } catch (e) {}
  var feld = document.getElementById("text"), knopf = document.getElementById("senden"), verlauf = document.getElementById("verlauf");
  function zeile(klasse, text){ var d = document.createElement("div"); d.className = klasse; d.textContent = text; verlauf.appendChild(d); return d; }
  function senden(){
    var text = feld.value.trim(); if (!text) return;
    zeile("du", text); feld.value = ""; knopf.disabled = true;
    var warte = zeile("jarvis", "denkt nach …");
    var koerper = {text: text}; if (gespraech) koerper.gespraech = gespraech;
    fetch("/api/anfrage", {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify(koerper)})
      .then(function(r){ return r.json(); })
      .then(function(a){
        if (a.gespraech) { gespraech = a.gespraech; try { sessionStorage.setItem("jarvis.gespraech", gespraech); } catch (e) {} }
        warte.textContent = a.ok ? a.antwort : ("Fehler: " + a.fehler);
        if (!a.ok) warte.className = "jarvis fehler";
      })
      .catch(function(){ warte.textContent = "Keine Verbindung zum Server."; warte.className = "jarvis fehler"; })
      .then(function(){ knopf.disabled = false; feld.focus(); });
  }
  knopf.onclick = senden;
  feld.onkeydown = function(e){ if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) senden(); };
  document.getElementById("neu").onclick = function(){ gespraech = null; try { sessionStorage.removeItem("jarvis.gespraech"); } catch (e) {} verlauf.innerHTML = ""; };
  document.getElementById("pruefen").onclick = function(){
    this.disabled = true;
    fetch("/api/provider/pruefen", {method: "POST"}).then(function(){ location.reload(); });
  };
})();
</script>
</main></body></html>
""" % dict(z, provider_zeilen="".join(zeilen), wissen=wissen_text)
