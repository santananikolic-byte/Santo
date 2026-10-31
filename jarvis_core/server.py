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
from .konfig import speichern_werte
from .protokoll import letzte_eintraege
from .provider import ProviderFehler, ProviderManager
from .stimme import Stimme

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
        self.stimme = Stimme(konfig)
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
            "stimme": self.stimme.status(),
            "wissen": self.wissen,
            "daten_ordner": self.konfig.daten_ordner,
        }

    # ---------------------------------------------------------- Stimme ---

    def einstellungen_aendern(self, neu):
        """Ändert Stimme, Tempo und Vorlesen und speichert sie dauerhaft."""
        werte = {}
        if "stimme" in neu:
            werte["stimme"] = str(neu["stimme"] or "").strip()
        if "tempo" in neu:
            try:
                werte["tempo"] = max(80, min(400, int(neu["tempo"])))
            except (TypeError, ValueError):
                return False, "tempo muss eine Zahl sein."
        if "vorlesen" in neu:
            werte["vorlesen"] = bool(neu["vorlesen"])
        with self._sperre:
            self.konfig.werte.update(werte)
            speichern_werte(self.konfig)
        self.log.ereignis("einstellungen_geaendert", **werte)
        return True, self.stimme.status()

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

        def _json_koerper(self):
            try:
                laenge = int(self.headers.get("Content-Length") or 0)
            except ValueError:
                return None
            if laenge <= 0 or laenge > MAX_KOERPER:
                return None
            if "application/json" not in (self.headers.get("Content-Type") or ""):
                return None
            try:
                return json.loads(self.rfile.read(laenge).decode("utf-8"))
            except (ValueError, UnicodeDecodeError):
                return None

        # --------------------------------------------------------- GET ---

        def do_GET(self):
            if not self._host_erlaubt():
                server.log.ereignis("zugriff_abgelehnt", "WARNING", grund="host", host=self.headers.get("Host"))
                return self._fehler(403, "Nur von dieser Maschine aus erreichbar.")
            teile = urlparse(self.path)
            if teile.path == "/status":
                return self._senden(200, server.status())
            if teile.path == "/api/stimmen":
                return self._senden(200, {"ok": True, "stimme": server.stimme.status()})
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
            if pfad == "/api/still":
                server.stimme.stopp()
                return self._senden(200, {"ok": True})
            if pfad in ("/api/sprich", "/api/einstellungen"):
                daten = self._json_koerper()
                if daten is None:
                    return self._fehler(400, "Kein gültiges JSON.")
                if pfad == "/api/sprich":
                    text = daten.get("text") if isinstance(daten, dict) else None
                    if not isinstance(text, str) or not text.strip():
                        return self._fehler(400, "Feld \"text\" fehlt.")
                    ging = server.stimme.sprich(text[:MAX_TEXT])
                    return self._senden(200, {"ok": True, "gesprochen": ging})
                ok, ergebnis = server.einstellungen_aendern(daten if isinstance(daten, dict) else {})
                return self._senden(200 if ok else 400, {"ok": ok, "stimme": ergebnis} if ok
                                    else {"ok": False, "fehler": ergebnis})
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
    # Status als Datenblock für die Seite - json.dumps vermeidet jedes Escaping-Problem.
    daten = json.dumps(status, ensure_ascii=False).replace("<", "\\u003c")
    return _SEITE.replace("__STATUS__", daten)


_SEITE = r"""<!DOCTYPE html>
<html lang="de"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<meta name="theme-color" content="#05070a">
<title>JARVIS</title>
<style>
  :root{--bg:#05070a;--fl:rgba(22,27,34,.72);--li:rgba(0,229,255,.2);--tx:#f2f6fa;--mu:#9aa8b6;--cy:#00e5ff;--bl:#3d7bff;--gr:#35e0a1;--rt:#ff5c7a}
  *{box-sizing:border-box}
  html,body{height:100%;margin:0}
  body{background:var(--bg);color:var(--tx);font:16px/1.55 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif;
    display:flex;flex-direction:column;overflow:hidden;
    background-image:radial-gradient(900px 500px at 80% -10%,rgba(61,123,255,.16),transparent 60%),
      radial-gradient(700px 450px at -10% 30%,rgba(0,229,255,.08),transparent 60%);}
  button{font:inherit;color:inherit;cursor:pointer}
  header{flex:none;display:flex;align-items:center;gap:10px;padding:12px 16px;padding-top:max(12px,env(safe-area-inset-top));border-bottom:1px solid var(--li)}
  .brand{font-weight:800;letter-spacing:.24em;font-size:18px}
  .zustand{font:12px ui-monospace,Menlo,monospace;color:var(--mu);flex:1}
  .ibtn{width:40px;height:40px;border-radius:12px;border:1px solid var(--li);background:rgba(17,22,29,.8);display:grid;place-items:center}
  .stage{flex:none;display:flex;flex-direction:column;align-items:center;padding:16px}
  .core{width:104px;height:104px;border-radius:50%;position:relative;border:1px solid var(--li);
    background:radial-gradient(circle,rgba(0,229,255,.95) 0 9%,rgba(0,229,255,.22) 10% 27%,transparent 28%);
    box-shadow:0 0 36px rgba(0,229,255,.28),inset 0 0 26px rgba(0,229,255,.2);transition:box-shadow .3s,transform .3s}
  .core::before,.core::after{content:"";position:absolute;border-radius:50%}
  .core::before{inset:9px;border:2px dashed rgba(0,229,255,.55);animation:spin 20s linear infinite}
  .core::after{inset:24px;border:2px solid transparent;border-top-color:var(--bl);border-bottom-color:var(--bl);animation:spin 7s linear infinite reverse}
  @keyframes spin{to{transform:rotate(360deg)}}
  body.hoert .core{box-shadow:0 0 60px rgba(255,92,122,.45);border-color:rgba(255,92,122,.7)}
  body.denkt .core::before{animation-duration:1.4s} body.denkt .core::after{animation-duration:.9s}
  body.spricht .core{animation:puls 1.1s ease-in-out infinite}
  @keyframes puls{50%{transform:scale(1.06);box-shadow:0 0 70px rgba(0,229,255,.55)}}
  .live{min-height:20px;margin-top:10px;font-size:14px;color:var(--mu);text-align:center}
  main{flex:1;min-height:0;overflow-y:auto;padding:4px 0 10px}
  .wrap{max-width:720px;margin:0 auto;padding:0 16px}
  .leer{color:var(--mu);text-align:center;padding:20px 8px}
  .msg{margin:10px 0;display:flex} .msg.du{justify-content:flex-end}
  .bub{max-width:88%;padding:11px 14px;border-radius:16px;white-space:pre-wrap;overflow-wrap:anywhere}
  .du .bub{background:rgba(61,123,255,.18);border:1px solid rgba(61,123,255,.35);border-bottom-right-radius:5px}
  .jv .bub{background:var(--fl);border:1px solid var(--li);border-bottom-left-radius:5px}
  .fehler .bub{background:rgba(255,92,122,.08);border:1px solid var(--rt)}
  .dock{flex:none;border-top:1px solid var(--li);background:rgba(5,7,10,.82);padding:10px 0;padding-bottom:max(10px,env(safe-area-inset-bottom))}
  .bar{display:flex;gap:8px;align-items:flex-end}
  textarea{flex:1;resize:none;font:inherit;font-size:16px;color:var(--tx);background:rgba(17,22,29,.9);border:1px solid var(--li);border-radius:14px;padding:11px 14px;max-height:120px;outline:none}
  textarea:focus{border-color:var(--cy)}
  .rund{width:52px;height:52px;border-radius:50%;flex:none;display:grid;place-items:center;border:1px solid var(--li);background:rgba(0,229,255,.1);color:var(--cy)}
  .rund svg{width:24px;height:24px}
  body.hoert .mic{background:var(--rt);border-color:var(--rt);color:#fff}
  .send{background:var(--cy);color:var(--bg);border:0} .send:disabled{opacity:.4}
  .chips{display:flex;gap:6px;overflow-x:auto;padding-bottom:8px}
  .chip{flex:none;font-size:13px;padding:6px 11px;border-radius:999px;border:1px solid var(--li);background:rgba(17,22,29,.8);color:var(--mu)}
  .chip.an{color:var(--bg);background:var(--cy);border-color:var(--cy)}
  .sheet{position:fixed;inset:0;z-index:30;display:none;background:rgba(0,0,0,.6)}
  .sheet.auf{display:flex;justify-content:flex-end}
  .panel{width:min(460px,100%);height:100%;overflow-y:auto;background:#0b0f14;border-left:1px solid var(--li);padding:18px 16px 40px;padding-top:max(18px,env(safe-area-inset-top))}
  .panel h2{margin:0 0 10px;letter-spacing:.14em;text-transform:uppercase;font-size:15px}
  .panel h3{font:12px ui-monospace,Menlo,monospace;letter-spacing:.14em;text-transform:uppercase;color:var(--cy);margin:22px 0 8px}
  label{display:block;font-size:14px;margin:12px 0 5px}
  select,input[type=range]{width:100%}
  select{font:inherit;color:var(--tx);background:rgba(17,22,29,.9);border:1px solid var(--li);border-radius:10px;padding:9px}
  .zeile{display:flex;align-items:center;justify-content:space-between;gap:12px;padding:10px 0;border-bottom:1px solid var(--li);font-size:15px}
  .zeile input{width:22px;height:22px;accent-color:var(--cy)}
  table{width:100%;border-collapse:collapse;background:var(--fl);border:1px solid var(--li);border-radius:12px;overflow:hidden;margin-top:6px}
  td{padding:9px 12px;border-bottom:1px solid var(--li);vertical-align:top;font-size:14px} td:first-child{color:var(--mu);width:38%}
  .ok{color:var(--gr)} .aus{color:var(--rt)}
  .x{border:0;background:none;color:var(--mu);font-size:20px} .btn{border:1px solid var(--li);background:transparent;color:var(--cy);border-radius:10px;padding:8px 12px;font-size:14px}
</style></head><body class="ruht">
<header>
  <span class="brand">JARVIS</span><span class="zustand" id="zustand">bereit</span>
  <button class="ibtn" id="auf" aria-label="Einstellungen">⚙︎</button>
</header>
<div class="stage"><div class="core"></div><div class="live" id="live"></div></div>
<main><div class="wrap" id="verlauf"><div class="leer" id="leer">Tippe unten, oder tippe das Mikrofon an und sprich.</div></div></main>
<div class="dock"><div class="wrap">
  <div class="chips">
    <button class="chip" id="freihand" type="button">🎧 Hey Jarvis</button>
    <button class="chip" id="still" type="button">■ Still</button>
  </div>
  <div class="bar">
    <button class="rund mic" id="mic" aria-label="Sprechen"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="9" y="3" width="6" height="11" rx="3"/><path d="M5 11a7 7 0 0 0 14 0M12 18v3"/></svg></button>
    <textarea id="text" rows="1" placeholder="Schreib Jarvis …"></textarea>
    <button class="rund send" id="send" aria-label="Senden"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2"><path d="M5 12h14M13 6l6 6-6 6"/></svg></button>
  </div>
</div></div>
<div class="sheet" id="sheet"><div class="panel">
  <div style="display:flex;justify-content:space-between"><h2>Einstellungen</h2><button class="x" id="zu">✕</button></div>
  <h3>Stimme</h3>
  <div class="zeile"><div>Antworten vorlesen</div><input type="checkbox" id="vorlesen"></div>
  <label>Stimme</label><select id="stimme"></select>
  <label>Tempo <span id="tempoWert"></span></label><input type="range" id="tempo" min="120" max="300" step="5">
  <p id="stimmeHinweis" style="color:var(--mu);font-size:13px"></p>
  <h3>Anbieter</h3><table id="provider"></table>
  <h3>Status</h3><table id="status"></table>
  <p style="color:var(--mu);font-size:13px">Nur auf diesem Mac. Jarvis hat noch keine Werkzeuge: Er antwortet, sucht aber nicht im Netz und führt nichts aus.</p>
</div></div>
<script>
(function(){
  var S = __STATUS__;
  var $ = function(id){ return document.getElementById(id); };
  var body = document.body, verlauf = $("verlauf"), feld = $("text");
  var gespraech = null; try { gespraech = sessionStorage.getItem("jv.g"); } catch(e){}
  var vorlesen = S.stimme && S.stimme.vorlesen, freihand = false, busy = false;

  function zustand(z, text){ body.className = z; $("zustand").textContent = text || z; }
  function leerWeg(){ var l = $("leer"); if (l) l.remove(); }
  function blase(klasse, text){ leerWeg(); var r=document.createElement("div"); r.className="msg "+klasse;
    var b=document.createElement("div"); b.className="bub"; b.textContent=text; r.appendChild(b); verlauf.appendChild(r);
    r.scrollIntoView({block:"end"}); return b; }

  // ---- Stimme (der Mac spricht über den Server) ----
  function sprich(text){ if(!vorlesen || !S.stimme || !S.stimme.verfuegbar) return;
    zustand("spricht","spricht"); fetch("/api/sprich",{method:"POST",headers:{"Content-Type":"application/json"},
      body:JSON.stringify({text:text})}).catch(function(){});
    setTimeout(function(){ if(body.className==="spricht") zustand("ruht","bereit"); }, Math.min(16000, 1500+text.length*55)); }
  function still(){ fetch("/api/still",{method:"POST"}).catch(function(){}); if(body.className==="spricht") zustand("ruht","bereit"); }

  // ---- Senden ----
  function senden(text){ text=(text||"").trim(); if(!text||busy) return; still();
    blase("du",text); feld.value=""; feld.style.height="auto"; busy=true; $("send").disabled=true;
    var warte=blase("jv","…"); zustand("denkt","denkt nach");
    var k={text:text}; if(gespraech) k.gespraech=gespraech;
    fetch("/api/anfrage",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(k)})
      .then(function(r){return r.json();}).then(function(a){
        if(a.gespraech){ gespraech=a.gespraech; try{ sessionStorage.setItem("jv.g",gespraech); }catch(e){} }
        warte.textContent = a.ok ? a.antwort : ("Fehler: "+a.fehler);
        if(!a.ok){ warte.parentNode.className="msg jv fehler"; zustand("ruht","bereit"); }
        else sprich(a.antwort);
      }).catch(function(){ warte.textContent="Keine Verbindung zum Server."; warte.parentNode.className="msg jv fehler"; zustand("ruht","bereit"); })
      .then(function(){ busy=false; $("send").disabled=false; if(body.className==="denkt") zustand("ruht","bereit"); });
  }
  $("send").onclick=function(){ senden(feld.value); };
  feld.addEventListener("input",function(){ feld.style.height="auto"; feld.style.height=Math.min(feld.scrollHeight,120)+"px"; });
  feld.addEventListener("keydown",function(e){ if(e.key==="Enter"&&!e.shiftKey){ e.preventDefault(); senden(feld.value); } });
  $("still").onclick=function(){ still(); if(rec){ stopHoeren(); } };

  // ---- Zuhören (Browser-Spracherkennung) ----
  var Erk = window.SpeechRecognition || window.webkitSpeechRecognition, rec=null, laeuft=false, einmal=false;
  var WECK=["hey jarvis","hey javis","hey charvis","hey travis","jarvis","javis"];
  function weck(t){ t=t.toLowerCase(); for(var i=0;i<WECK.length;i++){ var p=t.indexOf(WECK[i]); if(p!==-1) return t.slice(p+WECK[i].length).replace(/^[\s,.!?]+/,"").trim(); } return null; }
  function baue(){ var r=new Erk(); r.lang="de-DE"; r.interimResults=true; r.continuous=!einmal;
    r.onstart=function(){ laeuft=true; if(einmal||freihand) zustand("hoert","hört zu"); };
    r.onresult=function(ev){ var zwi="",fin=""; for(var i=ev.resultIndex;i<ev.results.length;i++){ if(ev.results[i].isFinal) fin+=ev.results[i][0].transcript; else zwi+=ev.results[i][0].transcript; }
      if(zwi) $("live").textContent=zwi;
      if(!fin) return; fin=fin.trim();
      if(einmal){ $("live").textContent=""; stopHoeren(); senden(fin); return; }
      var b=weck(fin); if(b===null){ $("live").textContent=""; return; }
      if(b.length>1){ $("live").textContent=""; stopHoeren(); senden(b); } };
    r.onerror=function(ev){ if(ev.error==="not-allowed"){ freihand=false; $("freihand").classList.remove("an"); blase("jv fehler","Das Mikrofon ist im Browser nicht erlaubt. Bitte oben in der Adresszeile freigeben."); } };
    r.onend=function(){ laeuft=false; if(body.className==="hoert") zustand("ruht","bereit"); if(einmal){ einmal=false; return; } if(freihand) setTimeout(starte,400); };
    return r; }
  function starte(){ if(!Erk||laeuft) return; rec=baue(); try{ rec.start(); }catch(e){} }
  function stopHoeren(){ if(rec&&laeuft){ try{ rec.stop(); }catch(e){} } }
  $("mic").onclick=function(){ if(!Erk){ blase("jv fehler","Dieser Browser kann keine Sprache erkennen. Nimm Safari oder Chrome, oder tippe."); return; }
    still(); if(laeuft){ stopHoeren(); return; } einmal=!freihand; starte(); };
  $("freihand").onclick=function(){ if(!Erk){ $("mic").onclick(); return; } freihand=!freihand; this.classList.toggle("an",freihand);
    if(freihand){ einmal=false; starte(); } else { stopHoeren(); } };

  // ---- Einstellungen ----
  function fuellen(){
    var st=S.stimme||{}; vorlesen=!!st.vorlesen; $("vorlesen").checked=vorlesen;
    var sel=$("stimme"); sel.innerHTML="";
    var auto=document.createElement("option"); auto.value=""; auto.textContent="Automatisch (beste Stimme)"; sel.appendChild(auto);
    (st.auswahl||[]).forEach(function(n){ var o=document.createElement("option"); o.value=n; o.textContent=n; if(n===st.gewuenscht) o.selected=true; sel.appendChild(o); });
    if(!st.gewuenscht) auto.selected=true;
    $("tempo").value=st.tempo||185; $("tempoWert").textContent=(st.tempo||185)+" WpM";
    $("stimmeHinweis").textContent = st.verfuegbar ? ("Aktiv: "+(st.stimme||"Systemstimme")+". Schönere Stimmen gratis: Systemeinstellungen → Bedienungshilfen → Gesprochene Inhalte → Stimmen verwalten.") : "Auf diesem Rechner ist keine Sprachausgabe verfügbar.";
    var pr=$("provider"); pr.innerHTML=""; Object.keys(S.provider).forEach(function(k){ var p=S.provider[k];
      pr.innerHTML+='<tr><td>'+(p.anzeige||k)+'</td><td><span class="'+(p.nutzbar?"ok":"aus")+'">●</span> '+(p.hinweis||"")+'</td></tr>'; });
    var ta=$("status");
    ta.innerHTML='<tr><td>Adresse</td><td>'+S.adresse+'</td></tr><tr><td>Anfragen</td><td>'+S.anfragen+'</td></tr>'+
      '<tr><td>Wissen</td><td>'+((S.wissen||[]).join(", ")||"–")+'</td></tr>'+
      '<tr><td>Version</td><td>'+S.version+' (Phase '+S.phase+'), Python '+S.python+'</td></tr><tr><td>Daten</td><td>'+S.daten_ordner+'</td></tr>';
  }
  function einstellen(neu){ fetch("/api/einstellungen",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(neu)})
    .then(function(r){return r.json();}).then(function(a){ if(a.ok){ S.stimme=a.stimme; fuellen(); } }); }
  $("vorlesen").onchange=function(){ vorlesen=this.checked; einstellen({vorlesen:vorlesen}); if(!vorlesen) still(); };
  $("stimme").onchange=function(){ einstellen({stimme:this.value}); };
  $("tempo").oninput=function(){ $("tempoWert").textContent=this.value+" WpM"; };
  $("tempo").onchange=function(){ einstellen({tempo:parseInt(this.value,10)}); };
  $("auf").onclick=function(){ $("sheet").classList.add("auf"); fuellen(); };
  $("zu").onclick=function(){ $("sheet").classList.remove("auf"); };
  $("sheet").onclick=function(e){ if(e.target===$("sheet")) $("sheet").classList.remove("auf"); };
  fuellen();
})();
</script>
</body></html>
"""
