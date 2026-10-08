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
from modules.sprechtext import sprechstuecke
from modules.anzeige import anzeige_nach_lesen
from modules.freigabe import freigabe_lesen, lesbarer_name
from modules.ansicht import (SEITE_GEHIRN, SEITE_ZENTRALE, gehirn_daten, lichter_liste,
                             status_daten, zentrale_daten)
from modules.autopilot import SEITE_AUTOPILOT
from modules.lernpfad import SEITE_PFAD, lernpfad_stand
from modules.webseite import SEITE_HTML
# Importe der Pakete.
# [P1 Bühne] Anfang
# [P1 Bühne] Ende
# [P2 Weltlage] Anfang
# [P2 Weltlage] Ende
# [P3 Telefon] Anfang
# [P3 Telefon] Ende
# [P4 Büro] Anfang
from modules.freigabe import GESTE_GESPERRT
# [P4 Büro] Ende
# [P5 Sicht] Anfang
# [P5 Sicht] Ende
# [P6 Stimme] Anfang
# [P6 Stimme] Ende
# [P7 Start] Anfang
# [P7 Start] Ende

STANDARD_PORT = 8765
MAX_KOERPER = 512 * 1024

# Ohne eigenes Symbol fragt jeder Browser nach /favicon.ico und bekommt einen
# Fehler in die Konsole. Ein kleines SVG kostet nichts und räumt das weg.
SYMBOL_SVG = (
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64">'
    '<rect width="64" height="64" rx="14" fill="#0F1113"/>'
    '<circle cx="32" cy="32" r="17" fill="none" stroke="#E8622C" stroke-width="5"/>'
    '<circle cx="32" cy="32" r="6" fill="#E8622C"/></svg>')


# Wie eine Antwort im Browser zustande kam: Klick, gesprochenes Ja/Nein oder Geste.
FREIGABE_WEGE = ("klick", "sprache", "geste")


class WebFreigabe:
    """Freigaben über den Browser statt über Telegram oder das Terminal.

    Eine Anfrage wird abgelegt und blockiert den Werkzeugaufruf, bis der Nutzer
    im Browser antwortet oder die Zeit abläuft. **Zeitablauf gilt als Nein** -
    wie überall sonst im Programm.

    Der Browser bekommt Was, Warum und Wie lesbar, dazu die Argumente als
    eingerücktes JSON.

    **Gesten.** Ein Klick und ein gesprochenes Ja zählen immer. Eine Geste (Daumen
    hoch vor der Kamera) ist unschärfer und zählt nur, wenn alles zusammenpasst:

    * ``GESTEN_FREIGABE`` ist eingeschaltet (voreingestellt aus),
    * es ist genau eine Frage offen - sonst weiß niemand, welche gemeint ist,
    * die Aktion steht nicht in ``GESTE_GESPERRT`` (Skripte, Bildschirm, Dateien …),
    * die Frage ist mindestens zwei Sekunden alt: Wer sie gerade erst vor sich hat,
      hat sie noch nicht gelesen, und ein noch erhobener Daumen soll nichts
      Neues freigeben.

    Jede Antwort wird mit dem Weg protokolliert, auch eine abgewiesene.
    ``uhr`` liefert die Zeit in Sekunden (für Prüfungen austauschbar).
    """

    # So alt muss eine Frage sein, bevor eine Geste sie beantworten darf.
    GESTE_MINDESTALTER = 2.0
    # Wie der Weg im Protokoll heißt.
    WEG_NAMEN = {"klick": "Klick", "sprache": "Sprache", "geste": "Geste"}

    def __init__(self, timeout: int = None, uhr=None, memory=None):
        self.timeout = int(timeout if timeout is not None else config.FREIGABE_TIMEOUT)
        self._uhr = uhr or time.time
        self.memory = memory
        self._offen = {}
        self._sperre = threading.Lock()
        # Warum die letzte Antwort nicht angenommen wurde - für die Rückmeldung im Browser.
        self.letzter_grund = ""

    @staticmethod
    def _gesten_an() -> bool:
        """Ist die Gesten-Freigabe eingeschaltet? Fehlt der Schlüssel: nein."""
        try:
            return bool(config.GESTEN_FREIGABE)
        except (AttributeError, NameError):
            return False

    def anfordern(self, aktion: str, details: str = "") -> dict:
        """Legt eine Freigabefrage ab und wartet auf die Antwort."""
        kennung = uuid.uuid4().hex[:12]
        ereignis = threading.Event()
        lesbar = freigabe_lesen(details)
        if lesbar is not None:
            was, warum, wie = lesbar["was"], lesbar["warum"], lesbar["wie"]
            try:
                anzeigen = json.dumps(lesbar["argumente"], ensure_ascii=False, indent=2,
                                      default=str)
            except (TypeError, ValueError):
                anzeigen = str(lesbar["argumente"])
        else:
            # Alter Freitext (etwa der Code eines Skripts) bleibt, wie er ist.
            was, warum, wie, anzeigen = lesbarer_name(aktion), "", "", details
        jetzt = self._uhr()
        eintrag = {"id": kennung, "aktion": aktion, "details": anzeigen,
                   "was": was, "warum": warum, "wie": wie,
                   "gestellt": zeitstempel(), "gestellt_epoch": jetzt,
                   "ereignis": ereignis, "antwort": None, "weg": "",
                   "laeuft_ab": jetzt + self.timeout}
        with self._sperre:
            self._offen[kennung] = eintrag

        erhalten = ereignis.wait(timeout=self.timeout)
        with self._sperre:
            self._offen.pop(kennung, None)

        if not erhalten or eintrag["antwort"] is not True:
            grund = ("abgelehnt" if erhalten
                     else "keine Antwort innerhalb von %d Sekunden" % self.timeout)
            return {"erlaubt": False, "kanal": "web", "weg": eintrag["weg"], "grund": grund}
        return {"erlaubt": True, "kanal": "web", "weg": eintrag["weg"], "grund": "Freigabe erteilt"}

    def _unbeantwortete(self) -> list:
        """Die Fragen, auf die noch niemand geantwortet hat. Nur mit der Sperre aufrufen."""
        return [e for e in self._offen.values() if e["antwort"] is None]

    def offene(self) -> list:
        """Alle wartenden Freigabefragen - die holt sich der Browser ab.

        ``geste_erlaubt`` sagt dem Browser, ob eine Geste diese Frage überhaupt
        beantworten dürfte (ob sie alt genug ist, prüft erst die Antwort).
        """
        jetzt = self._uhr()
        gesten = self._gesten_an()
        with self._sperre:
            offen = self._unbeantwortete()
            einzige = len(offen) == 1
            return [{"id": e["id"], "aktion": e["aktion"], "was": e["was"],
                     "warum": e["warum"], "wie": e["wie"], "details": e["details"],
                     "gestellt": e["gestellt"],
                     "rest": max(0, int(e["laeuft_ab"] - jetzt)),
                     "geste_erlaubt": bool(gesten and einzige
                                           and e["aktion"] not in GESTE_GESPERRT)}
                    for e in offen]

    def beantworten(self, kennung: str, ja: bool, kanal: str = "klick") -> bool:
        """Beantwortet eine Freigabefrage. ``kanal``: klick, sprache oder geste.

        Ist die Antwort nicht angenommen, steht der Grund in ``letzter_grund``
        (für mehrere gleichzeitige Anfragen: :meth:`beantworten_mit_grund`).
        """
        return self.beantworten_mit_grund(kennung, ja, kanal)[0]

    def _geste_grund(self, eintrag: dict) -> str:
        """Warum eine Geste diese Frage nicht beantworten darf - leer, wenn sie darf.

        Nur mit der Sperre aufrufen. Die Reihenfolge ist die der Regeln oben.
        """
        vorn = "Die Geste zählt hier nicht: "
        if not self._gesten_an():
            return vorn + "Gesten-Freigabe ist ausgeschaltet."
        if len(self._unbeantwortete()) != 1:
            return vorn + "mehrere Fragen offen."
        if eintrag["aktion"] in GESTE_GESPERRT:
            return vorn + "diese Aktion gibt nur ein Klick oder die Stimme frei."
        if self._uhr() - eintrag["gestellt_epoch"] < self.GESTE_MINDESTALTER:
            return vorn + ("die Frage ist erst gerade gestellt. Lies sie in Ruhe und "
                           "zeige die Geste dann noch einmal.")
        return ""

    def beantworten_mit_grund(self, kennung: str, ja: bool, kanal: str = "klick") -> tuple:
        """Wie :meth:`beantworten`, gibt aber ``(angenommen, grund)`` zurück.

        Eine schon beantwortete Frage bleibt beantwortet - ein zweiter Klick
        dreht ein Nein nicht in ein Ja.
        """
        kanal = str(kanal or "klick").strip().lower()
        if kanal not in FREIGABE_WEGE:
            kanal = "unbekannt"
        with self._sperre:
            eintrag = self._offen.get(kennung)
            if kanal == "unbekannt":
                grund = "Diesen Freigabeweg kenne ich nicht."
            elif eintrag is None:
                grund = "Diese Frage ist nicht mehr offen."
            elif eintrag["antwort"] is not None:
                grund = "Diese Frage ist schon beantwortet."
            elif kanal == "geste":
                grund = self._geste_grund(eintrag)
            else:
                grund = ""
            if not grund and eintrag is not None:
                eintrag["antwort"] = bool(ja)
                eintrag["weg"] = kanal
            self.letzter_grund = grund
        self._protokollieren(eintrag, kanal, ja, grund)
        if grund:
            return False, grund
        eintrag["ereignis"].set()
        return True, ""

    def _protokollieren(self, eintrag, kanal: str, ja: bool, grund: str):
        """Hält fest, auf welchem Weg geantwortet wurde - auch eine abgewiesene Antwort."""
        if eintrag is None:
            return
        text = grund or ("per %s %s" % (self.WEG_NAMEN.get(kanal, kanal), "ja" if ja else "nein"))
        print("[freigabe] %s: %s" % (eintrag["aktion"], text))
        if self.memory is None:
            return
        try:
            self.memory.aktion_protokollieren(
                "freigabe", {"aktion": eintrag["aktion"], "kanal": kanal, "ja": bool(ja)},
                text, "abgelehnt" if grund else "ok")
        except Exception:
            pass


# Was die Anzeige im Dienst braucht - nur ansehen, nichts auslösen.
ANZEIGE_PFADE = {"/gehirn", "/zentrale", "/api/gehirn", "/api/zentrale", "/api/status",
                 "/api/lichter", "/favicon.ico", "/symbol.svg", "/api/anzeige"}
# Die Pakete ergänzen hier, etwa ANZEIGE_PFADE |= {"/api/weltkarte"}.
# [P1 Bühne] Anfang
# [P1 Bühne] Ende
# [P2 Weltlage] Anfang
# [P2 Weltlage] Ende
# [P3 Telefon] Anfang
# [P3 Telefon] Ende
# [P4 Büro] Anfang
# [P4 Büro] Ende
# [P5 Sicht] Anfang
# [P5 Sicht] Ende
# [P6 Stimme] Anfang
# [P6 Stimme] Ende
# [P7 Start] Anfang
# [P7 Start] Ende


class JarvisWeb:
    """Der Webserver. Startet den Agenten im Browser."""

    def __init__(self, agent, host: str = "127.0.0.1", port: int = STANDARD_PORT,
                 offen: bool = False, token: str = "", nur_anzeige: bool = False):
        self.agent = agent
        # Im Dienst läuft nur die Anzeige mit. Reden, Werkzeuge, Freigaben und der
        # Autopilot gehen dort ausschließlich über die Stimme - mit Weckwort und
        # Stimmprüfung -, nicht über einen offenen Port auf dem Rechner.
        self.nur_anzeige = bool(nur_anzeige)
        self.offen = bool(offen)
        self.host = "0.0.0.0" if self.offen else (host or "127.0.0.1")
        self.port = int(port or STANDARD_PORT)
        # Im WLAN ist ein Schlüssel Pflicht - dieser Server darf zu viel.
        self.token = token or (secrets.token_urlsafe(18) if self.offen else "")
        self.freigabe = WebFreigabe(memory=getattr(agent, "memory", None))
        # Was Jarvis von sich aus sagt - Briefings, Routinen, Zeitplan. Der
        # Browser holt es ab, liest es vor und zeigt es im Gespraech.
        self.meldungen = []
        self._meldesperre = threading.Lock()
        self.server = None
        self._denkt = threading.Lock()
        if not self.nur_anzeige:
            agent.tools.freigabe_kanal_setzen(self.freigabe)
        # [P1 Bühne] Anfang
        # [P1 Bühne] Ende
        # [P2 Weltlage] Anfang
        # [P2 Weltlage] Ende
        # [P3 Telefon] Anfang
        # [P3 Telefon] Ende
        # [P4 Büro] Anfang
        # [P4 Büro] Ende
        # [P5 Sicht] Anfang
        # [P5 Sicht] Ende
        # [P6 Stimme] Anfang
        # [P6 Stimme] Ende
        # [P7 Start] Anfang
        # [P7 Start] Ende

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
            self.meldungen.append({"text": text, "sprechstuecke": sprechstuecke(text),
                                   "zeit": zeitstempel()})
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
    def _herkunft_ok(behandler) -> bool:
        """Schreibende Anfragen müssen von dieser Seite selbst kommen.

        Der Browser setzt bei jeder seitenübergreifenden POST-Anfrage den
        Herkunftskopf. Passt er nicht zum Host, hat eine fremde Webseite den
        Browser dazu gebracht, hier etwas auszulösen - ohne Schlüssel würde
        das sonst durchgehen.
        """
        herkunft = behandler.headers.get("Origin")
        if not herkunft:
            return True
        host = (behandler.headers.get("Host") or "").lower()
        try:
            return urlparse(herkunft).netloc.lower() == host
        except ValueError:
            return False

    def _behandeln(self, behandler, methode: str):
        """Verteilt eine Anfrage auf die passende Antwort."""
        pfad = urlparse(behandler.path).path.rstrip("/") or "/"
        if not self._erlaubt(behandler):
            return self._antworten(behandler, 403,
                                   {"fehler": "Kein Zugang. Der Schlüssel fehlt "
                                              "oder stimmt nicht."})
        if self.nur_anzeige and (methode != "GET" or pfad not in ANZEIGE_PFADE):
            return self._antworten(behandler, 404,
                                   {"fehler": "Hier läuft nur die Anzeige. Sprich mit Jarvis."})
        if methode == "POST" and not self._herkunft_ok(behandler):
            return self._antworten(behandler, 403,
                                   {"fehler": "Anfrage von einer fremden Seite abgelehnt."})
        try:
            if methode == "GET":
                return self._get(behandler, pfad)
            return self._post(behandler, pfad)
        except Exception as fehler:
            print("[web] Fehler bei %s: %s" % (pfad, fehler))
            return self._antworten(behandler, 500, {"fehler": str(fehler)})

    def _get(self, behandler, pfad: str):
        werkzeuge = self.agent.tools
        frage = parse_qs(urlparse(behandler.path).query)

        if pfad == "/":
            return self._html(behandler, SEITE_HTML.replace(
                "{{SCHLUESSEL}}", self.token))
        if pfad == "/pfad":
            return self._html(behandler, SEITE_PFAD.replace(
                "{{SCHLUESSEL}}", self.token))
        if pfad == "/api/pfad":
            return self._antworten(behandler, 200, lernpfad_stand(werkzeuge))
        if pfad == "/gehirn":
            return self._html(behandler, SEITE_GEHIRN.replace("{{SCHLUESSEL}}", self.token))
        if pfad == "/zentrale":
            return self._html(behandler, SEITE_ZENTRALE.replace("{{SCHLUESSEL}}", self.token))
        if pfad == "/api/gehirn":
            return self._antworten(behandler, 200, gehirn_daten(werkzeuge, self.agent))
        if pfad == "/api/zentrale":
            return self._antworten(behandler, 200, zentrale_daten(werkzeuge, self.agent))
        if pfad == "/api/status":
            return self._antworten(behandler, 200, status_daten(werkzeuge, self.agent))
        if pfad == "/api/lichter":
            return self._antworten(behandler, 200, {"ok": True, "lichter": lichter_liste()})
        if pfad == "/api/anzeige":
            # Long-Poll: kommt zurück, sobald sich einer der genannten Kanäle ändert.
            try:
                warten = min(25.0, max(0.0, float(frage.get("warten", ["20"])[0])))
            except ValueError:
                warten = 20.0
            kanaele = werkzeuge.anzeige.warten(anzeige_nach_lesen(frage.get("nach", [""])[0]),
                                               warten)
            return self._antworten(behandler, 200, {
                "ok": True, "jetzt": time.time(), "start": werkzeuge.anzeige.start,
                "kanaele": kanaele})
        if pfad == "/autopilot":
            return self._html(behandler, SEITE_AUTOPILOT.replace(
                "{{SCHLUESSEL}}", self.token))
        if pfad == "/api/autopilot":
            return self._antworten(behandler, 200, werkzeuge.autopilot.zustand())
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
        # [P1 Bühne] Anfang
        # [P1 Bühne] Ende
        # [P2 Weltlage] Anfang
        # [P2 Weltlage] Ende
        # [P3 Telefon] Anfang
        # [P3 Telefon] Ende
        # [P4 Büro] Anfang
        # [P4 Büro] Ende
        # [P5 Sicht] Anfang
        # [P5 Sicht] Ende
        # [P6 Stimme] Anfang
        # [P6 Stimme] Ende
        # [P7 Start] Anfang
        # [P7 Start] Ende
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
                    "antwort": "Es ist kein Anthropic-Schlüssel hinterlegt. "
                               "Ohne ihn kann ich nicht denken."})
            # Nur ein Gedanke gleichzeitig: sonst mischen sich zwei Gespräche
            # im selben Verlauf.
            with self._denkt:
                antwort = self.agent.denken(text)
            return self._antworten(behandler, 200,
                                   {"ok": True, "antwort": antwort,
                                    "sprechstuecke": sprechstuecke(antwort),
                                    "zeit": zeitstempel()})

        if pfad == "/api/autopilot":
            ap = werkzeuge.autopilot
            aktion = str(daten.get("aktion") or "")
            if aktion == "schalten":
                return self._antworten(behandler, 200, ap.schalten(bool(daten.get("an"))))
            if aktion == "auftrag":
                return self._antworten(behandler, 200, ap.auftrag_anlegen(
                    str(daten.get("titel") or ""), str(daten.get("auftrag") or ""),
                    str(daten.get("rolle") or ""), daten.get("prioritaet") or 2))
            if aktion == "gesehen":
                return self._antworten(behandler, 200, ap.gesehen_setzen(daten.get("id")))
            if aktion == "jetzt":
                if ap.gesperrt():
                    return self._antworten(behandler, 200, {
                        "ok": False, "fehler": "Gerade nicht möglich: %s." % ap.gesperrt()})
                threading.Thread(target=ap.tick, daemon=True, name="autopilot-jetzt").start()
                return self._antworten(behandler, 200, {"ok": True, "text": "Läuft."})
            return self._antworten(behandler, 400, {"fehler": "Diese Aktion kenne ich nicht."})

        if pfad == "/api/freigabe":
            kennung = str(daten.get("id") or "")
            # Nur ein echtes true ist ein Ja - "false", "nein" oder 1 sind es nicht.
            ja = daten.get("ja") is True
            # klick, sprache oder geste - eine Geste gibt in dieser Stufe nichts frei.
            kanal = str(daten.get("kanal") or "klick")[:20]
            erledigt, grund = self.freigabe.beantworten_mit_grund(kennung, ja, kanal)
            return self._antworten(behandler, 200, {
                "ok": erledigt,
                "text": ("Freigabe erteilt." if ja else "Abgelehnt.") if erledigt
                        else (grund or "Diese Frage ist nicht mehr offen.")})

        if pfad == "/api/anzeige/satz":
            # Der Satz, den der Browser gerade vorliest - für den Pegel der Anzeige.
            text = str(daten.get("text") or "").strip()[:400]
            if not text:
                return self._antworten(behandler, 400,
                                       {"ok": False, "fehler": "Es kam kein Text an."})
            werkzeuge.melden("stimme", {"art": "satz", "text": text,
                                        "start_ms": time.time() * 1000, "quelle": "browser"})
            return self._antworten(behandler, 200, {"ok": True})

        if pfad == "/api/werkzeug":
            name = str(daten.get("name") or "")
            if name not in werkzeuge.namen():
                return self._antworten(behandler, 400,
                                       {"fehler": "Das Werkzeug gibt es nicht."})
            return self._antworten(behandler, 200,
                                   werkzeuge.run(name, daten.get("argumente") or {}))

        if pfad == "/api/verlauf/neu":
            self.agent.verlauf_leeren()
            return self._antworten(behandler, 200,
                                   {"ok": True, "text": "Neues Gespräch."})

        # [P1 Bühne] Anfang
        # [P1 Bühne] Ende
        # [P2 Weltlage] Anfang
        # [P2 Weltlage] Ende
        # [P3 Telefon] Anfang
        # [P3 Telefon] Ende
        # [P4 Büro] Anfang
        # [P4 Büro] Ende
        # [P5 Sicht] Anfang
        # [P5 Sicht] Ende
        # [P6 Stimme] Anfang
        # [P6 Stimme] Ende
        # [P7 Start] Anfang
        # [P7 Start] Ende
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
    def _kopf_setzen(behandler, code: int, typ: str, laenge: int, zusatz: dict = None):
        """Setzt die Antwortköpfe. ``zusatz`` ersetzt Cache-Control oder fügt Köpfe
        hinzu - etwa eine eigene Content-Security-Policy für eine Seite."""
        zusatz = dict(zusatz or {})
        cache = "no-store"
        for name in list(zusatz):
            if name.lower() == "cache-control":
                cache = zusatz.pop(name)
        behandler.send_response(code)
        behandler.send_header("Content-Type", typ)
        behandler.send_header("Content-Length", str(laenge))
        behandler.send_header("Cache-Control", cache)
        behandler.send_header("X-Content-Type-Options", "nosniff")
        behandler.send_header("Referrer-Policy", "no-referrer")
        for name, wert in zusatz.items():
            behandler.send_header(name, wert)
        behandler.end_headers()

    def _antworten(self, behandler, code: int, nutzlast: dict, zusatz: dict = None):
        """Schickt eine JSON-Antwort."""
        try:
            roh = json.dumps(nutzlast, ensure_ascii=False, default=str).encode("utf-8")
        except (TypeError, ValueError):
            roh = json.dumps({"fehler": "Antwort nicht darstellbar"}).encode("utf-8")
        self._kopf_setzen(behandler, code, "application/json; charset=utf-8", len(roh), zusatz)
        behandler.wfile.write(roh)

    def _html(self, behandler, text: str, zusatz: dict = None):
        roh = text.encode("utf-8")
        self._kopf_setzen(behandler, 200, "text/html; charset=utf-8", len(roh), zusatz)
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
