#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Web-App - Jarvis im Browser statt im Terminal.

Ein kleiner Server aus der Python-Standardbibliothek, kein Fremdpaket. Er
liefert eine Seite aus, die im Browser läuft: dort spricht der Nutzer, dort
antwortet Jarvis, dort steht sein Stand, und dort erteilt er Freigaben.

**Warum das Mikrofon im Browser besser ist:** Der Browser darf auf das Mikrofon
zugreifen, sobald der Nutzer einmal erlaubt hat - ohne PortAudio, ohne
Systemrechte fürs Terminal, und auch vom Handy aus. Die Spracherkennung von
Safari und Chrome ist für Deutsch gut genug und kostet nichts.

**Sicherheit.** Der Server hört standardmäßig nur auf 127.0.0.1, also nur auf
diesem Rechner. Wer ihn ins WLAN stellt, um vom Handy zuzugreifen, braucht
zwingend einen Schlüssel in der Adresse - denn dieser Server darf Mails lesen,
Skripte ausführen und Geld verbuchen. Ein offener Port ohne Schlüssel wäre
fahrlässig. Zusätzlich wird der Host-Kopf geprüft, damit keine fremde Webseite
über den Namen des Rechners hereinredet.
"""

import json
import mimetypes
import os
import secrets
import threading
import time
import uuid
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

import config
from modules.memory import zeitstempel
from modules.freier_dienst import DIENST_VORGABEN, freier_dienst_pruefen
from modules.lokal import STANDARD_MODELL, ollama_pruefen
from modules.setup_wizard import schluessel_online_testen
from modules.webseite import AUTOPILOT_HTML, PROTOKOLL_HTML, SEITE_HTML

STANDARD_PORT = 8765
MAX_KOERPER = 6 * 1024 * 1024  # ein Kamerabild passt hinein

# Ohne eigenes Symbol fragt jeder Browser nach /favicon.ico und bekommt einen
# Fehler in die Konsole. Ein kleines SVG kostet nichts und räumt das weg.
SYMBOL_SVG = (
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64">'
    '<rect width="64" height="64" rx="14" fill="#03080F"/>'
    '<circle cx="32" cy="32" r="21" fill="none" stroke="#3AD1FF" stroke-width="2" '
    'stroke-dasharray="10 4"/>'
    '<circle cx="32" cy="32" r="14" fill="none" stroke="#3AD1FF" stroke-width="4"/>'
    '<circle cx="32" cy="32" r="6" fill="#A6ECFF"/></svg>')


def _fuer_skript(wert: str) -> str:
    """Macht einen Text sicher für die Einbettung in ein <script> der Seite."""
    return (json.dumps(wert).replace("<", "\\u003c").replace(">", "\\u003e")
            .replace("&", "\\u0026"))


class WebFreigabe:
    """Freigaben über den Browser statt über Telegram oder das Terminal.

    Eine Anfrage wird abgelegt und blockiert den Werkzeugaufruf, bis der Nutzer
    im Browser antwortet oder die Zeit abläuft. **Zeitablauf gilt als Nein** -
    wie überall sonst im Programm.
    """

    def __init__(self, timeout: int = None):
        self.timeout = int(timeout if timeout is not None else config.FREIGABE_TIMEOUT)
        self._offen = {}
        self._sperre = threading.Lock()

    def anfordern(self, aktion: str, details: str = "") -> dict:
        """Legt eine Freigabefrage ab und wartet auf die Antwort."""
        kennung = uuid.uuid4().hex[:12]
        ereignis = threading.Event()
        eintrag = {"id": kennung, "aktion": aktion, "details": details,
                   "gestellt": zeitstempel(), "ereignis": ereignis,
                   "antwort": None,
                   "laeuft_ab": time.time() + self.timeout}
        with self._sperre:
            self._offen[kennung] = eintrag

        erhalten = ereignis.wait(timeout=self.timeout)
        with self._sperre:
            self._offen.pop(kennung, None)

        if not erhalten or eintrag["antwort"] is not True:
            grund = ("abgelehnt" if erhalten
                     else "keine Antwort innerhalb von %d Sekunden" % self.timeout)
            return {"erlaubt": False, "kanal": "web", "grund": grund}
        return {"erlaubt": True, "kanal": "web", "grund": "Freigabe erteilt"}

    def offene(self) -> list:
        """Alle wartenden Freigabefragen - die holt sich der Browser ab."""
        jetzt = time.time()
        with self._sperre:
            return [{"id": e["id"], "aktion": e["aktion"], "details": e["details"],
                     "gestellt": e["gestellt"],
                     "rest": max(0, int(e["laeuft_ab"] - jetzt))}
                    for e in self._offen.values()]

    def beantworten(self, kennung: str, ja: bool) -> bool:
        """Beantwortet eine Freigabefrage."""
        with self._sperre:
            eintrag = self._offen.get(kennung)
            if eintrag is None:
                return False
            eintrag["antwort"] = bool(ja)
        eintrag["ereignis"].set()
        return True


class JarvisWeb:
    """Der Webserver. Startet den Agenten im Browser."""

    def __init__(self, agent, host: str = "127.0.0.1", port: int = STANDARD_PORT,
                 offen: bool = False, token: str = ""):
        self.agent = agent
        self.offen = bool(offen)
        self.host = "0.0.0.0" if self.offen else (host or "127.0.0.1")
        self.port = int(port or STANDARD_PORT)
        # Im WLAN ist ein Schlüssel Pflicht - dieser Server darf zu viel.
        self.token = token or (secrets.token_urlsafe(18) if self.offen else "")
        self.freigabe = WebFreigabe()
        # Was Jarvis von sich aus sagt - Briefings, Routinen, Zeitplan. Der
        # Browser holt es ab, liest es vor und zeigt es im Gespraech.
        self.meldungen = []
        self._meldesperre = threading.Lock()
        self.server = None
        self._denkt = threading.Lock()
        agent.tools.freigabe_kanal_setzen(self.freigabe)

    def melden(self, text: str):
        """Nimmt eine Meldung des Zeitplans auf.

        Sie wird zusaetzlich in den Gespraechsverlauf geschrieben. Ist der
        Browser gerade zu, geht das Morgenbriefing sonst verloren - und ein
        Briefing, das niemand hoert, ist keines.
        """
        text = (text or "").strip()
        if not text:
            return
        print("[jarvis] %s" % text)
        try:
            self.agent.memory.verlauf_anhaengen("assistant", text)
        except Exception:
            pass
        with self._meldesperre:
            self.meldungen.append({"text": text, "zeit": zeitstempel()})
            # Mehr als zwanzig ungelesene Meldungen sind ohnehin unlesbar.
            del self.meldungen[:-20]

    def meldungen_abholen(self) -> list:
        """Gibt die offenen Meldungen zurueck und leert die Liste."""
        with self._meldesperre:
            offen = list(self.meldungen)
            self.meldungen = []
        return offen

    # -- Adressen -----------------------------------------------------------

    def adresse(self) -> str:
        """Die Adresse, die der Nutzer im Browser öffnet."""
        gastgeber = "localhost" if not self.offen else self._eigene_ip()
        ziel = "http://%s:%d/" % (gastgeber, self.port)
        return ziel + ("?schluessel=%s" % self.token if self.token else "")

    @staticmethod
    def _eigene_ip() -> str:
        """Die IP dieses Rechners im eigenen Netz."""
        import socket
        verbindung = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            verbindung.connect(("192.168.1.1", 1))
            return verbindung.getsockname()[0]
        except OSError:
            return "127.0.0.1"
        finally:
            verbindung.close()

    # -- Betrieb ------------------------------------------------------------

    def starten(self, blockierend: bool = True):
        """Startet den Server."""
        anwendung = self

        class Behandler(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"
            server_version = "Jarvis"

            def log_message(self, format, *args):
                del format, args   # Die Konsole gehört Jarvis, nicht dem Server.

            def do_GET(self):
                anwendung._behandeln(self, "GET")

            def do_POST(self):
                anwendung._behandeln(self, "POST")

        self.server = ThreadingHTTPServer((self.host, self.port), Behandler)
        self.server.daemon_threads = True
        if blockierend:
            try:
                self.server.serve_forever()
            except KeyboardInterrupt:
                pass
            finally:
                self.stoppen()
        else:
            threading.Thread(target=self.server.serve_forever, daemon=True,
                             name="jarvis-web").start()
        return self.server

    def stoppen(self):
        """Hält den Server an."""
        if self.server is not None:
            try:
                self.server.shutdown()
            except Exception:
                pass
            try:
                self.server.server_close()
            except Exception:
                pass
            self.server = None

    # -- Anfragen -----------------------------------------------------------

    def _erlaubt(self, behandler) -> bool:
        """Prüft Schlüssel und Host-Kopf.

        Der Host-Kopf muss auf diesen Rechner zeigen. Sonst könnte eine fremde
        Webseite den Browser des Nutzers dazu bringen, hier anzuklopfen - der
        Browser schickt die Anfrage brav mit, und der Server hielte sie für
        echt.
        """
        kopf = (behandler.headers.get("Host") or "").split(":")[0].lower()
        erlaubte = {"localhost", "127.0.0.1", "::1", ""}
        if self.offen:
            erlaubte.add(self._eigene_ip())
            erlaubte.add("0.0.0.0")
        if kopf not in erlaubte:
            return False
        if not self.token:
            return True
        gefragt = parse_qs(urlparse(behandler.path).query).get("schluessel", [""])[0]
        kopfschluessel = behandler.headers.get("X-Jarvis-Schluessel", "")
        return secrets.compare_digest(gefragt or kopfschluessel, self.token)

    @staticmethod
    def _von_fremder_seite(behandler) -> bool:
        """Schickt eine fremde Webseite im Browser des Nutzers diesen Auftrag?

        Ohne Schlüssel (nur auf diesem Rechner) prüft der Host-Kopf nicht, wer
        anklopft: Jede offene Webseite könnte per fetch() an localhost:8765
        posten - etwa /api/werkzeug mit "buchung_eintragen". Deshalb müssen
        Aufträge (POST) von der eigenen Seite kommen: Herkunft gleich Host,
        und als JSON - das kann eine fremde Seite nicht ohne Vorab-Anfrage
        senden, und die beantwortet dieser Server nie.
        """
        seite = (behandler.headers.get("Sec-Fetch-Site") or "").lower()
        if seite in ("cross-site", "same-site"):
            return True
        herkunft = behandler.headers.get("Origin")
        if herkunft is not None:
            host = (behandler.headers.get("Host") or "").lower()
            if herkunft == "null" or urlparse(herkunft).netloc.lower() != host:
                return True
        typ = (behandler.headers.get("Content-Type") or "").split(";")[0].strip().lower()
        return typ != "application/json"

    def _behandeln(self, behandler, methode: str):
        """Verteilt eine Anfrage auf die passende Antwort."""
        pfad = urlparse(behandler.path).path.rstrip("/") or "/"
        if not self._erlaubt(behandler):
            return self._antworten(behandler, 403,
                                   {"fehler": "Kein Zugang. Der Schlüssel fehlt "
                                              "oder stimmt nicht."})
        if methode == "POST" and self._von_fremder_seite(behandler):
            return self._antworten(behandler, 403,
                                   {"fehler": "Abgelehnt: Der Auftrag kam nicht von der "
                                              "Jarvis-Seite."})
        try:
            if methode == "GET":
                return self._get(behandler, pfad)
            return self._post(behandler, pfad)
        except Exception as fehler:
            print("[web] Fehler bei %s: %s" % (pfad, fehler))
            return self._antworten(behandler, 500, {"fehler": str(fehler)})

    def _get(self, behandler, pfad: str):
        werkzeuge = self.agent.tools

        if pfad == "/":
            return self._html(behandler, SEITE_HTML.replace(
                "{{SCHLUESSEL}}", self.token))
        if pfad == "/api/lage":
            return self._antworten(behandler, 200,
                                   werkzeuge.team.lagebericht(werkzeuge))
        if pfad == "/api/zustand":
            return self._antworten(behandler, 200, {
                "ok": True,
                "einsatzbereit": self.agent.einsatzbereit(),
                "nutzer": config.NUTZER_NAME, "firma": config.FIRMA,
                "modell": config.CLAUDE_MODEL,
                "werkzeuge": len(werkzeuge.namen()),
                "aufgaben": werkzeuge.autopilot.offen_anzahl(),
                "rollen": [r["rolle"] for r in werkzeuge.team.rollen_liste()],
                "dienste": config.konfig_uebersicht()})
        if pfad == "/api/meldungen":
            return self._antworten(behandler, 200,
                                   {"ok": True, "meldungen": self.meldungen_abholen()})
        if pfad == "/api/freigaben":
            return self._antworten(behandler, 200,
                                   {"ok": True, "offen": self.freigabe.offene()})
        if pfad == "/api/verlauf":
            zeilen = werkzeuge.memory.verlauf_letzte(30)
            return self._antworten(behandler, 200, {"ok": True, "verlauf": [
                {"rolle": z["rolle"], "text": z["text"], "zeit": z["zeit"]}
                for z in zeilen]})
        if pfad == "/api/protokoll":
            frage = parse_qs(urlparse(behandler.path).query)
            try:
                tage = int((frage.get("tage") or ["1"])[0])
            except ValueError:
                tage = 1
            return self._antworten(behandler, 200, werkzeuge.recall.protokoll(
                (frage.get("tag") or ["heute"])[0],
                (frage.get("thema") or [""])[0], tage))
        if pfad == "/api/autopilot":
            autopilot = werkzeuge.autopilot
            return self._antworten(behandler, 200, {
                "ok": True, "aufgaben": autopilot.aufgaben(),
                "einstellungen": autopilot.einstellungen(),
                "letzter_lauf": autopilot.letzter_lauf(),
                "laeuft": autopilot._laeuft.locked()})
        if pfad == "/autopilot":
            return self._html(behandler, (
                AUTOPILOT_HTML
                .replace("{{SCHLUESSEL_JSON}}", _fuer_skript(self.token or ""))
                .replace("{{NUTZER_JSON}}", _fuer_skript(config.NUTZER_NAME))
                .replace("{{FIRMA_JSON}}", _fuer_skript(config.FIRMA))))
        if pfad == "/protokoll":
            return self._html(behandler, (
                PROTOKOLL_HTML
                .replace("{{SCHLUESSEL_JSON}}", _fuer_skript(self.token or ""))
                .replace("{{NUTZER_JSON}}", _fuer_skript(config.NUTZER_NAME))
                .replace("{{FIRMA_JSON}}", _fuer_skript(config.FIRMA))))
        if pfad == "/api/pipeline":
            return self._antworten(behandler, 200, werkzeuge.akquise.pipeline())
        if pfad == "/api/nachfassen":
            return self._antworten(behandler, 200, werkzeuge.akquise.nachfassliste())
        if pfad == "/api/bedarf":
            return self._antworten(behandler, 200,
                                   werkzeuge.privat.bedarfsrechnung(werkzeuge.akquise))
        if pfad == "/api/kasse":
            return self._antworten(behandler, 200, werkzeuge.bookkeeping.auswertung())
        if pfad == "/api/team":
            return self._antworten(behandler, 200, {
                "ok": True, "rollen": werkzeuge.team.rollen_liste(),
                "auftraege": [dict(z) for z in werkzeuge.team.auftraege_letzte(10)]})
        if pfad in ("/favicon.ico", "/symbol.svg"):
            roh = SYMBOL_SVG.encode("utf-8")
            self._kopf_setzen(behandler, 200, "image/svg+xml", len(roh))
            return behandler.wfile.write(roh)
        if pfad in ("/dashboard", "/sales"):
            werkzeuge.dashboard.bauen()
            datei = config.DASHBOARD_VERZEICHNIS / (
                "dashboard.html" if pfad == "/dashboard" else "sales.html")
            return self._datei(behandler, str(datei))
        return self._antworten(behandler, 404, {"fehler": "Diese Seite gibt es nicht."})

    def _post(self, behandler, pfad: str):
        daten = self._koerper(behandler)
        werkzeuge = self.agent.tools

        if pfad == "/api/reden":
            text = str(daten.get("text") or "").strip()
            if not text:
                return self._antworten(behandler, 400,
                                       {"fehler": "Es kam kein Text an."})
            if not self.agent.einsatzbereit():
                return self._antworten(behandler, 200, {
                    "ok": False,
                    "antwort": "Ich habe noch kein Gehirn. Trag im Startfenster einen "
                               "Gratis-Schlüssel ein, dann denke ich mit."})
            # Nur ein Gedanke gleichzeitig: sonst mischen sich zwei Gespräche
            # im selben Verlauf.
            bild = str(daten.get("bild") or "")
            if bild.startswith("data:"):
                bild = bild.split(",", 1)[-1]
            quelle = "Bildschirm" if daten.get("quelle") == "bildschirm" else "Kamera"
            with self._denkt:
                antwort = self.agent.denken(text, bild_base64=bild[:5_000_000],
                                            bild_quelle=quelle)
            return self._antworten(behandler, 200,
                                   {"ok": True, "antwort": antwort,
                                    "zeit": zeitstempel()})

        if pfad == "/api/freigabe":
            kennung = str(daten.get("id") or "")
            ja = bool(daten.get("ja"))
            erledigt = self.freigabe.beantworten(kennung, ja)
            return self._antworten(behandler, 200, {
                "ok": erledigt,
                "text": ("Freigabe erteilt." if ja else "Abgelehnt.") if erledigt
                        else "Diese Frage ist nicht mehr offen."})

        if pfad == "/api/werkzeug":
            name = str(daten.get("name") or "")
            if name not in werkzeuge.namen():
                return self._antworten(behandler, 400,
                                       {"fehler": "Das Werkzeug gibt es nicht."})
            return self._antworten(behandler, 200,
                                   werkzeuge.run(name, daten.get("argumente") or {}))

        if pfad == "/api/schluessel":
            # Den Schlüssel nie zurückgeben oder protokollieren - er geht nur in
            # die .env auf diesem Rechner.
            schluessel = "".join(str(daten.get("schluessel") or "").split())
            if not schluessel.startswith("sk-") or len(schluessel) < 20:
                return self._antworten(behandler, 200, {
                    "ok": False,
                    "text": "Das sieht nicht nach einem Schlüssel aus. Er beginnt "
                            "mit sk- und ist lang. Bitte vollständig kopieren."})
            probe = schluessel_online_testen(schluessel)
            if probe.get("ok") or probe.get("grund") == "guthaben":
                config.env_setzen("ANTHROPIC_API_KEY", schluessel)
                return self._antworten(behandler, 200, {
                    "ok": True, "einsatzbereit": self.agent.einsatzbereit(),
                    "text": probe["text"] if probe.get("ok") else probe["text"]
                            + " Der Schlüssel ist gespeichert."})
            return self._antworten(behandler, 200,
                                   {"ok": False, "text": probe.get("text", "Fehlgeschlagen.")})

        if pfad == "/api/dienst":
            # Nur bekannte Anbieter: die Adresse kommt aus der Liste, nie aus der Anfrage.
            vorgabe = DIENST_VORGABEN.get(str(daten.get("dienst") or ""))
            schluessel = "".join(str(daten.get("schluessel") or "").split())
            modell = str(daten.get("modell") or "").strip() or (vorgabe or {}).get("modell", "")
            if vorgabe is None:
                return self._antworten(behandler, 200, {
                    "ok": False, "text": "Diesen Dienst kenne ich nicht."})
            if len(schluessel) < 10 or len(modell) > 300 or any(c.isspace() for c in modell):
                return self._antworten(behandler, 200, {
                    "ok": False, "text": "Schlüssel oder Modellname sehen nicht richtig "
                                         "aus. Bitte vollständig kopieren."})
            probe = freier_dienst_pruefen(vorgabe["url"], schluessel, modell)
            if not probe.get("ok"):
                return self._antworten(behandler, 200, {"ok": False, "text": probe["text"]})
            config.env_setzen("FREIER_DIENST_URL", vorgabe["url"])
            config.env_setzen("FREIER_DIENST_MODELL", modell)
            config.env_setzen("FREIER_DIENST_SCHLUESSEL", schluessel)
            return self._antworten(behandler, 200, {
                "ok": True, "einsatzbereit": self.agent.einsatzbereit(),
                "text": probe["text"] + " Gespräche gehen dabei an %s; das Gratis-Kontingent "
                                        "hat Grenzen." % vorgabe["name"]})

        if pfad == "/api/lokal":
            modell = str(daten.get("modell") or STANDARD_MODELL).strip()
            if not modell or len(modell) > 80 or any(c.isspace() for c in modell):
                return self._antworten(behandler, 200, {
                    "ok": False, "text": "Der Modellname sieht nicht richtig aus."})
            probe = ollama_pruefen(modell)
            if not probe.get("ok"):
                return self._antworten(behandler, 200, {"ok": False,
                                                        "text": probe["text"]})
            config.env_setzen("LOKALES_MODELL", probe["modell"])
            return self._antworten(behandler, 200, {
                "ok": True, "einsatzbereit": self.agent.einsatzbereit(),
                "text": probe["text"] + " Es kostet nichts. Antworten dauern "
                        "auf diesem Rechner länger als bei Claude."})

        if pfad == "/api/autopilot/laufen":
            autopilot = werkzeuge.autopilot
            if autopilot._laeuft.locked():
                return self._antworten(behandler, 200, {
                    "ok": False, "text": "Jarvis arbeitet gerade schon."})

            def arbeiten():
                # Im Hintergrund: Die Seite bleibt bedienbar, auch wenn der
                # Gratis-Dienst langsam ist.
                ergebnis = autopilot.laufen(self.agent)
                self.melden(ergebnis.get("text", ""))
            threading.Thread(target=arbeiten, daemon=True).start()
            return self._antworten(behandler, 200, {
                "ok": True, "text": "Jarvis arbeitet. Das dauert ein bis drei Minuten."})
        if pfad == "/api/autopilot/aktion":
            text = daten.get("text")
            betreff = daten.get("betreff")
            return self._antworten(behandler, 200, werkzeuge.autopilot.aufgabe_erledigen(
                daten.get("id"), str(daten.get("aktion") or ""),
                None if text is None else str(text),
                None if betreff is None else str(betreff)))
        if pfad == "/api/autopilot/einstellungen":
            branchen = daten.get("branchen")
            return self._antworten(behandler, 200, werkzeuge.autopilot.einstellungen_setzen(
                daten.get("ort"),
                [str(b) for b in branchen] if isinstance(branchen, list) else None,
                None if daten.get("an") is None else bool(daten.get("an")),
                daten.get("name"), daten.get("firma")))

        if pfad == "/api/verlauf/neu":
            self.agent.verlauf_leeren()
            return self._antworten(behandler, 200,
                                   {"ok": True, "text": "Neues Gespräch."})

        return self._antworten(behandler, 404, {"fehler": "Das gibt es nicht."})

    # -- Antworten ----------------------------------------------------------

    @staticmethod
    def _koerper(behandler) -> dict:
        """Liest den JSON-Körper einer Anfrage."""
        try:
            laenge = min(int(behandler.headers.get("Content-Length") or 0), MAX_KOERPER)
        except (TypeError, ValueError):
            laenge = 0
        if laenge <= 0:
            return {}
        try:
            return json.loads(behandler.rfile.read(laenge).decode("utf-8")) or {}
        except (ValueError, UnicodeDecodeError):
            return {}

    @staticmethod
    def _kopf_setzen(behandler, code: int, typ: str, laenge: int):
        behandler.send_response(code)
        behandler.send_header("Content-Type", typ)
        behandler.send_header("Content-Length", str(laenge))
        behandler.send_header("Cache-Control", "no-store")
        behandler.send_header("X-Content-Type-Options", "nosniff")
        behandler.send_header("Referrer-Policy", "no-referrer")
        behandler.end_headers()

    def _antworten(self, behandler, code: int, nutzlast: dict):
        """Schickt eine JSON-Antwort."""
        try:
            roh = json.dumps(nutzlast, ensure_ascii=False, default=str).encode("utf-8")
        except (TypeError, ValueError):
            roh = json.dumps({"fehler": "Antwort nicht darstellbar"}).encode("utf-8")
        self._kopf_setzen(behandler, code, "application/json; charset=utf-8", len(roh))
        behandler.wfile.write(roh)

    def _html(self, behandler, text: str):
        roh = text.encode("utf-8")
        self._kopf_setzen(behandler, 200, "text/html; charset=utf-8", len(roh))
        behandler.wfile.write(roh)

    def _datei(self, behandler, pfad: str):
        """Liefert eine erzeugte Datei aus - nur aus dem Dashboard-Ordner."""
        wurzel = config.DASHBOARD_VERZEICHNIS.resolve()
        try:
            ziel = os.path.realpath(pfad)
            if not ziel.startswith(str(wurzel)):
                return self._antworten(behandler, 403, {"fehler": "Nicht erlaubt."})
            with open(ziel, "rb") as datei:
                roh = datei.read()
        except OSError:
            return self._antworten(behandler, 404,
                                   {"fehler": "Die Seite ist noch nicht gebaut."})
        typ = mimetypes.guess_type(ziel)[0] or "application/octet-stream"
        self._kopf_setzen(behandler, 200, "%s; charset=utf-8" % typ, len(roh))
        behandler.wfile.write(roh)
