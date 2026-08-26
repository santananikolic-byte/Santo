#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""MCP - fertige Dienste einbinden, statt jede Anbindung selbst zu programmieren.

Ein MCP-Server ist ein eigener Prozess, der über stdin und stdout JSON-RPC
spricht. Der Ablauf ist immer derselbe::

    initialize -> notifications/initialized -> tools/list -> tools/call

Seine Werkzeuge landen als ``mcp__<server>__<werkzeug>`` im Katalog, damit
Claude sie neben den eigenen sieht.

**Freigabe umgekehrt als bei den eigenen Werkzeugen:** MCP-Werkzeuge brauchen
*standardmäßig* eine Freigabe. Nur was ausdrücklich unter ``ohne_rueckfrage``
steht (lesen, suchen, auflisten), läuft durch. Andersherum könnte ein frisch
angesteckter Server beim allerersten Aufruf löschen oder versenden, ohne dass je
gefragt wurde.
"""

import json
import os
import queue
import shutil
import subprocess
import threading
import time

import config

MCP_PROTOKOLL_VERSION = "2024-11-05"
MCP_START_TIMEOUT = 25
MCP_AUFRUF_TIMEOUT = 90

# Vorlage mit acht gängigen Diensten. Alle stehen bewusst auf "aus": true -
# der Nutzer schaltet frei, was er wirklich will.
VORLAGE_MCP = {
    "_hinweis": ("Ein Dienst wird benutzt, sobald 'aus' auf false steht. "
                 "Werkzeuge unter 'ohne_rueckfrage' laufen ohne Nachfrage, "
                 "alle anderen fragen vorher per Telegram nach."),
    "server": {
        "dateien": {
            "aus": True,
            "befehl": "npx",
            "argumente": ["-y", "@modelcontextprotocol/server-filesystem",
                          str(config.BASIS)],
            "umgebung": {},
            "ohne_rueckfrage": ["list_directory", "read_file", "read_text_file",
                                "search_files", "get_file_info", "directory_tree"],
        },
        "notion": {
            "aus": True,
            "befehl": "npx",
            "argumente": ["-y", "@notionhq/notion-mcp-server"],
            "umgebung": {"NOTION_TOKEN": "HIER_DEIN_NOTION_TOKEN"},
            "ohne_rueckfrage": ["search", "retrieve_page", "retrieve_database",
                                "query_database"],
        },
        "github": {
            "aus": True,
            "befehl": "npx",
            "argumente": ["-y", "@modelcontextprotocol/server-github"],
            "umgebung": {"GITHUB_PERSONAL_ACCESS_TOKEN": "HIER_DEIN_GITHUB_TOKEN"},
            "ohne_rueckfrage": ["search_repositories", "get_file_contents",
                                "list_issues", "search_code"],
        },
        "slack": {
            "aus": True,
            "befehl": "npx",
            "argumente": ["-y", "@modelcontextprotocol/server-slack"],
            "umgebung": {"SLACK_BOT_TOKEN": "HIER_DEIN_SLACK_TOKEN",
                         "SLACK_TEAM_ID": "HIER_DEINE_TEAM_ID"},
            "ohne_rueckfrage": ["slack_list_channels", "slack_get_channel_history",
                                "slack_get_users"],
        },
        "postgres": {
            "aus": True,
            "befehl": "npx",
            "argumente": ["-y", "@modelcontextprotocol/server-postgres",
                          "postgresql://benutzer:passwort@localhost/datenbank"],
            "umgebung": {},
            "ohne_rueckfrage": ["query"],
        },
        "suche": {
            "aus": True,
            "befehl": "npx",
            "argumente": ["-y", "@modelcontextprotocol/server-brave-search"],
            "umgebung": {"BRAVE_API_KEY": "HIER_DEIN_BRAVE_KEY"},
            "ohne_rueckfrage": ["brave_web_search", "brave_local_search"],
        },
        "google_drive": {
            "aus": True,
            "befehl": "npx",
            "argumente": ["-y", "@modelcontextprotocol/server-gdrive"],
            "umgebung": {"GDRIVE_CREDENTIALS_PATH": "HIER_PFAD_ZU_credentials.json"},
            "ohne_rueckfrage": ["gdrive_search", "gdrive_read_file"],
        },
        "whatsapp": {
            "aus": True,
            "befehl": "npx",
            "argumente": ["-y", "@modelcontextprotocol/server-whatsapp"],
            "umgebung": {},
            "ohne_rueckfrage": ["list_chats", "search_contacts", "get_messages"],
        },
    },
}


def vorlage_schreiben(pfad=None) -> str:
    """Legt ``config/mcp_servers.json`` an, falls sie noch fehlt."""
    ziel = str(pfad or config.MCP_DATEI)
    if os.path.exists(ziel):
        return ziel
    try:
        os.makedirs(os.path.dirname(ziel), exist_ok=True)
        with open(ziel, "w", encoding="utf-8") as datei:
            json.dump(VORLAGE_MCP, datei, ensure_ascii=False, indent=2)
    except OSError as fehler:
        print("[mcp] Vorlage nicht schreibbar: %s" % fehler)
    return ziel


class MCPServer:
    """Ein einzelner MCP-Server als Unterprozess."""

    def __init__(self, name: str, konfig: dict):
        self.name = name
        self.konfig = konfig or {}
        self.prozess = None
        self.werkzeugliste = []
        self.fehler = ""
        self._zaehler = 0
        self._antworten = queue.Queue()
        self._leser = None
        self._sperre = threading.Lock()

    # -- Start und Ende -----------------------------------------------------

    def starten(self) -> bool:
        """Startet den Prozess und führt den MCP-Handschlag durch."""
        befehl = self.konfig.get("befehl")
        if not befehl:
            self.fehler = "Für %s ist kein Befehl eingetragen." % self.name
            return False
        if not shutil.which(befehl):
            self.fehler = ("Das Programm '%s' ist nicht installiert - der Dienst %s "
                           "bleibt aus." % (befehl, self.name))
            return False

        umgebung = dict(os.environ)
        for schluessel, wert in (self.konfig.get("umgebung") or {}).items():
            umgebung[str(schluessel)] = str(wert)

        argumente = [str(teil) for teil in (self.konfig.get("argumente") or [])]
        try:
            self.prozess = subprocess.Popen(
                [befehl] + argumente, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL, env=umgebung, text=True, bufsize=1,
                shell=False)
        except (OSError, subprocess.SubprocessError) as fehler:
            self.fehler = "Der Dienst %s ließ sich nicht starten: %s" % (self.name, fehler)
            return False

        self._leser = threading.Thread(target=self._mitlesen, daemon=True,
                                       name="mcp-%s" % self.name)
        self._leser.start()

        antwort = self._senden("initialize", {
            "protocolVersion": MCP_PROTOKOLL_VERSION,
            "capabilities": {"tools": {}},
            "clientInfo": {"name": "jarvis", "version": "1.0"},
        }, timeout=MCP_START_TIMEOUT)
        if antwort is None or "error" in (antwort or {}):
            self.fehler = ("Der Dienst %s hat den Handschlag nicht beantwortet." % self.name)
            self.stoppen()
            return False

        self._benachrichtigen("notifications/initialized", {})
        self.werkzeuge_laden()
        return True

    def stoppen(self):
        """Beendet den Unterprozess."""
        if self.prozess is None:
            return
        try:
            if self.prozess.stdin:
                self.prozess.stdin.close()
        except OSError:
            pass
        try:
            self.prozess.terminate()
            self.prozess.wait(timeout=5)
        except (OSError, subprocess.SubprocessError):
            try:
                self.prozess.kill()
            except OSError:
                pass
        self.prozess = None

    def laeuft(self) -> bool:
        """Läuft der Unterprozess noch?"""
        return self.prozess is not None and self.prozess.poll() is None

    # -- JSON-RPC -----------------------------------------------------------

    def _mitlesen(self):
        """Liest den stdout des Servers Zeile für Zeile mit."""
        strom = self.prozess.stdout if self.prozess else None
        if strom is None:
            return
        try:
            for zeile in strom:
                zeile = (zeile or "").strip()
                if not zeile:
                    continue
                try:
                    self._antworten.put(json.loads(zeile))
                except ValueError:
                    continue  # Zeilen ohne JSON sind Logausgaben des Servers.
        except (OSError, ValueError):
            pass

    def _benachrichtigen(self, methode: str, parameter: dict):
        """Schickt eine Benachrichtigung ohne Antwort."""
        self._schreiben({"jsonrpc": "2.0", "method": methode, "params": parameter or {}})

    def _schreiben(self, nachricht: dict) -> bool:
        """Schreibt eine JSON-RPC-Nachricht auf stdin des Servers."""
        if not self.laeuft() or not self.prozess.stdin:
            return False
        try:
            self.prozess.stdin.write(json.dumps(nachricht) + "\n")
            self.prozess.stdin.flush()
            return True
        except (OSError, ValueError, BrokenPipeError):
            return False

    def _senden(self, methode: str, parameter: dict, timeout: int = MCP_AUFRUF_TIMEOUT):
        """Schickt eine Anfrage und wartet auf die passende Antwort."""
        with self._sperre:
            self._zaehler += 1
            kennung = self._zaehler
            if not self._schreiben({"jsonrpc": "2.0", "id": kennung,
                                    "method": methode, "params": parameter or {}}):
                return None
            ende = time.time() + timeout
            zurueckgelegt = []
            antwort = None
            while time.time() < ende:
                try:
                    nachricht = self._antworten.get(timeout=0.5)
                except queue.Empty:
                    if not self.laeuft():
                        break
                    continue
                if nachricht.get("id") == kennung:
                    antwort = nachricht
                    break
                zurueckgelegt.append(nachricht)
            for nachricht in zurueckgelegt:
                self._antworten.put(nachricht)
            return antwort

    # -- Werkzeuge ----------------------------------------------------------

    def werkzeuge_laden(self) -> list:
        """Fragt den Server nach seinen Werkzeugen."""
        antwort = self._senden("tools/list", {}, timeout=MCP_START_TIMEOUT)
        if not antwort or "result" not in antwort:
            self.werkzeugliste = []
            return []
        self.werkzeugliste = (antwort["result"] or {}).get("tools", []) or []
        return self.werkzeugliste

    def aufrufen(self, werkzeug: str, argumente: dict) -> dict:
        """Ruft ein Werkzeug des Servers auf."""
        if not self.laeuft():
            return {"ok": False, "fehler": "Der Dienst %s läuft nicht." % self.name}
        antwort = self._senden("tools/call",
                               {"name": werkzeug, "arguments": argumente or {}})
        if antwort is None:
            return {"ok": False,
                    "fehler": "Der Dienst %s hat nicht geantwortet." % self.name}
        if "error" in antwort:
            meldung = (antwort["error"] or {}).get("message", "unbekannter Fehler")
            return {"ok": False, "fehler": "%s meldet: %s" % (self.name, meldung)}
        ergebnis = antwort.get("result") or {}
        teile = []
        for eintrag in ergebnis.get("content", []) or []:
            if isinstance(eintrag, dict) and eintrag.get("type") == "text":
                teile.append(str(eintrag.get("text", "")))
            else:
                teile.append(json.dumps(eintrag, ensure_ascii=False))
        text = "\n".join(teile) if teile else json.dumps(ergebnis, ensure_ascii=False)
        if ergebnis.get("isError"):
            return {"ok": False, "fehler": text}
        return {"ok": True, "text": text}


class MCPClient:
    """Verwaltet alle eingeschalteten MCP-Server."""

    def __init__(self, konfig_pfad=None):
        self.konfig_pfad = str(konfig_pfad or config.MCP_DATEI)
        self.server = {}
        self.konfig = {}
        self.meldungen = []

    def konfiguration_lesen(self) -> dict:
        """Liest ``config/mcp_servers.json`` und legt sie an, falls sie fehlt."""
        vorlage_schreiben(self.konfig_pfad)
        try:
            with open(self.konfig_pfad, "r", encoding="utf-8") as datei:
                self.konfig = json.load(datei) or {}
        except (OSError, ValueError) as fehler:
            self.meldungen.append("Die MCP-Konfiguration ist fehlerhaft: %s" % fehler)
            self.konfig = {}
        return self.konfig

    def starten(self) -> dict:
        """Startet alle Dienste, die nicht auf 'aus' stehen."""
        self.konfiguration_lesen()
        gestartet, uebersprungen, fehlgeschlagen = [], [], []
        for name, eintrag in (self.konfig.get("server") or {}).items():
            if not isinstance(eintrag, dict):
                continue
            if eintrag.get("aus", True):
                uebersprungen.append(name)
                continue
            server = MCPServer(name, eintrag)
            if server.starten():
                self.server[name] = server
                gestartet.append(name)
            else:
                fehlgeschlagen.append("%s (%s)" % (name, server.fehler))
                self.meldungen.append(server.fehler)
        return {"gestartet": gestartet, "aus": uebersprungen,
                "fehlgeschlagen": fehlgeschlagen}

    def server_hinzufuegen(self, name: str, server: MCPServer):
        """Hängt einen bereits gestarteten Server ein - vor allem für Tests."""
        self.server[name] = server

    def stoppen(self):
        """Beendet alle Dienste."""
        for server in list(self.server.values()):
            server.stoppen()
        self.server.clear()

    # -- Katalog ------------------------------------------------------------

    def alle_werkzeuge(self) -> list:
        """Alle MCP-Werkzeuge im Format, das die Claude-Schnittstelle erwartet."""
        katalog = []
        for name, server in self.server.items():
            for werkzeug in server.werkzeugliste:
                if not isinstance(werkzeug, dict) or not werkzeug.get("name"):
                    continue
                katalog.append({
                    "name": "mcp__%s__%s" % (name, werkzeug["name"]),
                    "description": ("[%s] %s" % (name, werkzeug.get("description", "")))[:900],
                    "input_schema": werkzeug.get("inputSchema")
                                    or {"type": "object", "properties": {}},
                })
        return katalog

    def ist_mcp_werkzeug(self, name: str) -> bool:
        """Gehört dieser Werkzeugname zu einem MCP-Server?"""
        return str(name or "").startswith("mcp__")

    def zerlegen(self, voller_name: str):
        """Zerlegt ``mcp__server__werkzeug`` in seine beiden Teile."""
        if not self.ist_mcp_werkzeug(voller_name):
            return None, None
        rest = voller_name[len("mcp__"):]
        server, _, werkzeug = rest.partition("__")
        return server, werkzeug

    def braucht_freigabe(self, voller_name: str) -> bool:
        """Standardmäßig ja - nur ausdrücklich freigegebene Werkzeuge laufen durch."""
        server_name, werkzeug = self.zerlegen(voller_name)
        if not server_name:
            return True
        eintrag = (self.konfig.get("server") or {}).get(server_name) or {}
        ohne = eintrag.get("ohne_rueckfrage") or []
        return werkzeug not in [str(w) for w in ohne]

    def aufrufen(self, voller_name: str, argumente: dict) -> dict:
        """Ruft ein MCP-Werkzeug auf. Die Freigabe prüft der Werkzeugkatalog davor."""
        server_name, werkzeug = self.zerlegen(voller_name)
        if not server_name:
            return {"ok": False, "fehler": "'%s' ist kein MCP-Werkzeug." % voller_name}
        server = self.server.get(server_name)
        if server is None:
            return {"ok": False,
                    "fehler": "Der Dienst %s ist nicht eingeschaltet." % server_name}
        return server.aufrufen(werkzeug, argumente)

    def zustand(self) -> dict:
        """Was läuft, was ist aus - für Selbsttest und Dashboard."""
        return {"dienste": {name: {"laeuft": server.laeuft(),
                                   "werkzeuge": len(server.werkzeugliste)}
                            for name, server in self.server.items()},
                "anzahl_werkzeuge": len(self.alle_werkzeuge()),
                "konfiguration": self.konfig_pfad,
                "meldungen": self.meldungen[-5:]}
