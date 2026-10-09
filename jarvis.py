#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Jarvis - persönlicher Sprachassistent für die Gebäudereinigung.

Diese Datei ist erzeugt. Bearbeite die Module unter src/ und baue neu mit:

    python3 build_single.py

Betriebsarten:

    python3 jarvis.py             Web-App im Browser - der Normalfall
    python3 jarvis.py web --offen auch vom Handy im eigenen WLAN
    python3 jarvis.py hoeren      im Terminal zuhören, ohne Browser
    python3 jarvis.py chat        tippen statt sprechen
    python3 jarvis.py telegram    vom Handy aus
    python3 jarvis.py status      voller Stand des Betriebs
    python3 jarvis.py briefing    Briefing sofort
    python3 jarvis.py abend       Abendrückblick sofort
    python3 jarvis.py dashboard   Dashboard bauen
    python3 jarvis.py export      Buchhaltung als CSV
    python3 jarvis.py stimme      Stimmprofil einlernen
    python3 jarvis.py stimmen     ElevenLabs-Stimme aussuchen
    python3 jarvis.py test        Selbsttest
    python3 jarvis.py einrichten  geführte Ersteinrichtung

Alle Daten bleiben lokal auf diesem Rechner.
"""


import ast
import base64
import csv
import email
import email.header
import email.utils
import html
import imaplib
import importlib.util
import io
import ipaddress
import json
import math
import mimetypes
import os
import queue
import re
import secrets
import select
import shutil
import smtplib
import socket
import sqlite3
import ssl
import subprocess
import sys
import tempfile
import threading
import time
import traceback
import urllib.error
import urllib.parse
import urllib.request
import uuid
import wave
import xml.sax.saxutils
from base64 import b64encode
from datetime import datetime, timedelta
from email.message import EmailMessage
from html.parser import HTMLParser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse



# ---------------------------------------------------------------------------
# Optionale Abhängigkeiten. Fehlt eine, fällt nur das
# betroffene Werkzeug aus - nie das ganze Programm.
# ---------------------------------------------------------------------------

try:
    import numpy as np
except ImportError:
    np = None

try:
    import sounddevice as sd
except (ImportError, OSError):
    sd = None

try:
    from resemblyzer import VoiceEncoder, preprocess_wav
except ImportError:
    VoiceEncoder = None
    preprocess_wav = None

try:
    from playwright.sync_api import sync_playwright
except Exception:
    # Ohne installiertes Playwright wirft schon der Import.
    sync_playwright = None

try:
    import pyautogui
except Exception:
    # Ohne Bildschirm (etwa auf einem Server) wirft pyautogui beim Import.
    pyautogui = None

try:
    from PIL import Image
except ImportError:
    Image = None




# =========================================================================
# config  -  Konfiguration - liest ``config/.env`` und stellt alle Einstellungen bereit.
# 
# Alle Einstellungen liegen als Modul-Globals vor. Die anderen Module lesen sie
# über ``config.NAME``. Beim Zusammenführen zur Einzeldatei ersetzt
# ``build_single.py`` das Präfix ``config.`` durch den blanken Namen, damit in
# ``jarvis.py`` weiterhin ``NAME`` gelesen wird. Deshalb müssen alle Namen in
# diesem Modul projektweit eindeutig sein.
# =========================================================================

#!/usr/bin/env python3
# -*- coding: utf-8 -*-



def _basis_ermitteln() -> Path:
    """Findet die Projektwurzel - sowohl aus ``src/`` als auch aus ``jarvis.py``."""
    hier = Path(__file__).resolve().parent
    if hier.name == "src":
        return hier.parent
    if hier.name == "modules":
        return hier.parent.parent
    return hier


BASIS = _basis_ermitteln()
CONFIG_VERZEICHNIS = BASIS / "config"
ENV_DATEI = CONFIG_VERZEICHNIS / ".env"
MCP_DATEI = CONFIG_VERZEICHNIS / "mcp_servers.json"
DASHBOARD_VERZEICHNIS = BASIS / "dashboard"
BELEGE_VERZEICHNIS = BASIS / "belege"
PROFIL_VERZEICHNIS = BASIS / "profil"
EXPORT_VERZEICHNIS = BASIS / "export"
DB_PFAD = str(BASIS / "jarvis_memory.db")

# ---------------------------------------------------------------------------
# .env einlesen
# ---------------------------------------------------------------------------

_ROHWERTE = {}


def env_neu_laden():
    """Liest ``config/.env`` neu ein. Fehlt die Datei, bleibt alles leer."""
    _ROHWERTE.clear()
    try:
        if ENV_DATEI.exists():
            for zeile in ENV_DATEI.read_text(encoding="utf-8").splitlines():
                zeile = zeile.strip()
                if not zeile or zeile.startswith("#") or "=" not in zeile:
                    continue
                schluessel, _, wert = zeile.partition("=")
                wert = wert.strip()
                if len(wert) >= 2 and wert[0] == wert[-1] and wert[0] in "\"'":
                    wert = wert[1:-1]
                _ROHWERTE[schluessel.strip()] = wert
    except OSError as fehler:
        print("[konfig] .env konnte nicht gelesen werden: %s" % fehler)
    return dict(_ROHWERTE)


def _text(name, standard=""):
    wert = _ROHWERTE.get(name)
    if wert is None or wert == "":
        wert = os.environ.get(name, standard)
    return (wert or "").strip()


def _zahl(name, standard):
    try:
        roh = _text(name, "")
        return float(roh) if roh else float(standard)
    except (TypeError, ValueError):
        return float(standard)


def _ganzzahl(name, standard):
    try:
        roh = _text(name, "")
        return int(float(roh)) if roh else int(standard)
    except (TypeError, ValueError):
        return int(standard)


def _wahrheit(name, standard=False):
    roh = _text(name, "").lower()
    if roh in ("1", "ja", "true", "yes", "an", "on"):
        return True
    if roh in ("0", "nein", "false", "no", "aus", "off"):
        return False
    return bool(standard)


env_neu_laden()

# ---------------------------------------------------------------------------
# Einstellungen
# ---------------------------------------------------------------------------

# Claude
ANTHROPIC_API_KEY = _text("ANTHROPIC_API_KEY")
CLAUDE_MODEL = _text("CLAUDE_MODEL", "claude-sonnet-4-6")
CLAUDE_MAX_TOKENS = _ganzzahl("CLAUDE_MAX_TOKENS", 2000)

# Lokales Modell (Ollama): kostenlos, ohne Schlüssel, läuft auf diesem Rechner.
# Wird nur benutzt, wenn kein Anthropic-Schlüssel hinterlegt ist.
# Kostenloser Online-Dienst (Groq, Gemini, OpenRouter): Gratis-Schlüssel statt Anthropic.
FREIER_DIENST_URL = _text("FREIER_DIENST_URL")
FREIER_DIENST_SCHLUESSEL = _text("FREIER_DIENST_SCHLUESSEL")
FREIER_DIENST_MODELL = _text("FREIER_DIENST_MODELL")
LOKALES_MODELL = _text("LOKALES_MODELL")

# Autopilot: arbeitet von selbst und legt alles unter "Heute zu tun" ab.
AUTOPILOT_AN = _wahrheit("AUTOPILOT_AN", True)
AUTOPILOT_ORT = _text("AUTOPILOT_ORT")
AUTOPILOT_BRANCHEN = _text("AUTOPILOT_BRANCHEN",
                           "Arztpraxen,Steuerberater,Kanzleien,Autohäuser,Fitnessstudios")
AUTOPILOT_UHRZEITEN = _text("AUTOPILOT_UHRZEITEN", "08:30,13:30")
AUTOPILOT_NEUE_LEADS = _ganzzahl("AUTOPILOT_NEUE_LEADS", 5)
OLLAMA_URL = _text("OLLAMA_URL", "http://127.0.0.1:11434")

# Nutzer
NUTZER_NAME = _text("NUTZER_NAME", "Chef")
FIRMA = _text("FIRMA", "Gebäudereinigung")

# Sprachausgabe
ELEVENLABS_API_KEY = _text("ELEVENLABS_API_KEY")
# Voreingestellt ist eine maennliche, trockene Stimme. Die frueher hier
# stehende Kennung war eine weibliche - genau der Grund, warum Jarvis nicht
# so klang, wie er sollte.
ELEVENLABS_VOICE_ID = _text("ELEVENLABS_VOICE_ID", "JBFqnCBsd6RMkjVDRZzb")
ELEVENLABS_MODEL = _text("ELEVENLABS_MODEL", "eleven_multilingual_v2")

# Klangprofil: ruhig und gleichmaessig (Stability), nah am Original
# (Similarity), ohne Theatralik (Style). Als Zahlen einstellbar, damit sich
# das ohne Codeaenderung nachjustieren laesst.
ELEVENLABS_STABILITY = _zahl("ELEVENLABS_STABILITY", 0.65)
ELEVENLABS_SIMILARITY = _zahl("ELEVENLABS_SIMILARITY", 0.85)
ELEVENLABS_STYLE = _zahl("ELEVENLABS_STYLE", 0.10)
SPEECH_RATE = _ganzzahl("SPEECH_RATE", 185)
MACOS_STIMME = _text("MACOS_STIMME", "")

# Spracherkennung
OPENAI_API_KEY = _text("OPENAI_API_KEY")
WHISPER_MODELL = _text("WHISPER_MODELL", "base")
STIMM_SCHWELLE = _zahl("STIMM_SCHWELLE", 0.75)
STIMMPRUEFUNG_AN = _wahrheit("STIMMPRUEFUNG_AN", False)

# Telegram
TELEGRAM_BOT_TOKEN = _text("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = _text("TELEGRAM_CHAT_ID")
FREIGABE_TIMEOUT = _ganzzahl("FREIGABE_TIMEOUT", 120)

# E-Mail
IMAP_HOST = _text("IMAP_HOST")
IMAP_PORT = _ganzzahl("IMAP_PORT", 993)
IMAP_USER = _text("IMAP_USER")
IMAP_PASSWORT = _text("IMAP_PASSWORT")
SMTP_HOST = _text("SMTP_HOST")
SMTP_PORT = _ganzzahl("SMTP_PORT", 587)
SMTP_USER = _text("SMTP_USER")
SMTP_PASSWORT = _text("SMTP_PASSWORT")
SMTP_ABSENDER = _text("SMTP_ABSENDER") or _text("SMTP_USER")

# Kalender
CALDAV_URL = _text("CALDAV_URL")
CALDAV_USER = _text("CALDAV_USER")
CALDAV_PASSWORT = _text("CALDAV_PASSWORT")
CALDAV_KALENDER = _text("CALDAV_KALENDER")

# Briefings
BRIEFING_MORGENS = _text("BRIEFING_MORGENS", "06:45")
BRIEFING_ABENDS = _text("BRIEFING_ABENDS", "19:30")

# Buchhaltung
STANDARD_MWST = _zahl("STANDARD_MWST", 20.0)
# Rücklage für Einkommensteuer und Sozialversicherung zusammen. Grob, aber
# besser als keine Rücklage - der Steuerberater nennt den genauen Satz.
STEUER_RUECKLAGE = _zahl("STEUER_RUECKLAGE", 30.0)
WAEHRUNG = _text("WAEHRUNG", "EUR")

# Telefon (Twilio)
TWILIO_SID = _text("TWILIO_SID")
TWILIO_TOKEN = _text("TWILIO_TOKEN")
TWILIO_NUMMER = _text("TWILIO_NUMMER")
LANDESVORWAHL = _text("LANDESVORWAHL", "+43")
BROWSER_PROGRAMM = _text("BROWSER_PROGRAMM")

# Welt
WETTER_ORT = _text("WETTER_ORT", "Wien")

# Supabase (optional, nur Spiegelung - die Wahrheit liegt immer lokal)
SUPABASE_URL = _text("SUPABASE_URL")
SUPABASE_KEY = _text("SUPABASE_KEY")

# Ersteinrichtung abgeschlossen?
EINRICHTUNG_FERTIG = _wahrheit("EINRICHTUNG_FERTIG", False)


def env_setzen(schluessel: str, wert) -> bool:
    """Schreibt einen Wert nach ``config/.env`` und aktualisiert ihn sofort."""
    schluessel = str(schluessel).strip()
    if not schluessel:
        return False
    _ROHWERTE[schluessel] = "" if wert is None else str(wert)
    ok = env_schreiben()
    # Live-Wert im laufenden Prozess nachziehen
    globalraum = globals()
    if schluessel in globalraum:
        alt = globalraum[schluessel]
        try:
            if isinstance(alt, bool):
                globalraum[schluessel] = _wahrheit(schluessel, alt)
            elif isinstance(alt, int):
                globalraum[schluessel] = _ganzzahl(schluessel, alt)
            elif isinstance(alt, float):
                globalraum[schluessel] = _zahl(schluessel, alt)
            else:
                globalraum[schluessel] = _text(schluessel, "")
        except Exception:
            globalraum[schluessel] = _text(schluessel, "")
    else:
        globalraum[schluessel] = _text(schluessel, "")
    return ok


def env_schreiben() -> bool:
    """Speichert alle bekannten Werte in ``config/.env`` (nur für den Nutzer lesbar)."""
    try:
        CONFIG_VERZEICHNIS.mkdir(parents=True, exist_ok=True)
        zeilen = ["# Jarvis - Einstellungen. Eine Zeile pro Wert: NAME=wert", ""]
        for name in sorted(_ROHWERTE):
            zeilen.append("%s=%s" % (name, _ROHWERTE[name]))
        ENV_DATEI.write_text("\n".join(zeilen) + "\n", encoding="utf-8")
        try:
            os.chmod(str(ENV_DATEI), 0o600)
        except OSError:
            pass
        return True
    except OSError as fehler:
        print("[konfig] .env konnte nicht geschrieben werden: %s" % fehler)
        return False


def verzeichnisse_anlegen():
    """Legt alle Arbeitsverzeichnisse an, falls sie fehlen."""
    for pfad in (CONFIG_VERZEICHNIS, DASHBOARD_VERZEICHNIS, BELEGE_VERZEICHNIS,
                 PROFIL_VERZEICHNIS, EXPORT_VERZEICHNIS):
        try:
            pfad.mkdir(parents=True, exist_ok=True)
        except OSError as fehler:
            print("[konfig] Verzeichnis %s nicht anlegbar: %s" % (pfad, fehler))


def konfig_uebersicht() -> dict:
    """Zeigt an, welche Dienste eingerichtet sind - ohne Geheimnisse preiszugeben."""
    return {
        "Claude": bool(ANTHROPIC_API_KEY),
        "Gratis-Dienst": bool(FREIER_DIENST_SCHLUESSEL),
        "Lokales Modell": bool(LOKALES_MODELL),
        "ElevenLabs": bool(ELEVENLABS_API_KEY),
        "Whisper-API": bool(OPENAI_API_KEY),
        "Telegram": bool(TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID),
        "E-Mail lesen": bool(IMAP_HOST and IMAP_USER),
        "E-Mail senden": bool(SMTP_HOST and SMTP_USER),
        "Kalender": bool(CALDAV_URL),
        "Supabase": bool(SUPABASE_URL and SUPABASE_KEY),
        "Telefon": bool(TWILIO_SID and TWILIO_TOKEN and TWILIO_NUMMER),
    }


verzeichnisse_anlegen()


# =========================================================================
# memory  -  Gedächtnis, Ebene 0 - Notizen, Kontakte, Kennzahlen, offene Punkte, Protokoll.
# 
# Alles liegt lokal in einer SQLite-Datei. Supabase wird, falls konfiguriert,
# nur zusätzlich gespiegelt: Die Wahrheit steht immer auf dem Rechner des Nutzers.
# =========================================================================

#!/usr/bin/env python3
# -*- coding: utf-8 -*-



_DB_SPERRE = threading.Lock()

SCHEMA_MEMORY = """
CREATE TABLE IF NOT EXISTS notizen (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    text TEXT NOT NULL,
    kategorie TEXT DEFAULT 'allgemein',
    angelegt TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS kontakte (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    firma TEXT DEFAULT '',
    telefon TEXT DEFAULT '',
    email TEXT DEFAULT '',
    adresse TEXT DEFAULT '',
    notiz TEXT DEFAULT '',
    angelegt TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS kennzahlen (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    wert REAL NOT NULL,
    einheit TEXT DEFAULT '',
    datum TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS offene_punkte (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    text TEXT NOT NULL,
    faellig TEXT DEFAULT '',
    erledigt INTEGER DEFAULT 0,
    angelegt TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS aktionen (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    werkzeug TEXT NOT NULL,
    argumente TEXT DEFAULT '',
    ergebnis TEXT DEFAULT '',
    status TEXT DEFAULT 'ok',
    zeit TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS verlauf (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    rolle TEXT NOT NULL,
    text TEXT NOT NULL,
    zeit TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_notizen_text ON notizen(text);
CREATE INDEX IF NOT EXISTS idx_verlauf_zeit ON verlauf(zeit);
"""


def zeitstempel() -> str:
    """Aktuelle Zeit als ``JJJJ-MM-TT HH:MM:SS``."""
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def heute_datum() -> str:
    """Heutiges Datum als ``JJJJ-MM-TT``."""
    return datetime.now().strftime("%Y-%m-%d")


def db_verbindung(pfad: str = None) -> sqlite3.Connection:
    """Öffnet eine SQLite-Verbindung mit Zeilen-Zugriff über Spaltennamen."""
    verbindung = sqlite3.connect(pfad or DB_PFAD, timeout=15,
                                 check_same_thread=False)
    verbindung.row_factory = sqlite3.Row
    verbindung.execute("PRAGMA journal_mode=WAL")
    return verbindung


def db_schema_anlegen(schema: str, pfad: str = None):
    """Legt die Tabellen eines Moduls an, falls sie noch fehlen."""
    with _DB_SPERRE:
        verbindung = db_verbindung(pfad)
        try:
            verbindung.executescript(schema)
            verbindung.commit()
        finally:
            verbindung.close()


def zeilen_zu_liste(zeilen) -> list:
    """Wandelt SQLite-Zeilen in gewöhnliche Wörterbücher um."""
    return [dict(zeile) for zeile in zeilen]


class Memory:
    """Das Kurzzeit- und Sachgedächtnis: Notizen, Kontakte, Zahlen, Protokoll."""

    def __init__(self, db_pfad: str = None):
        self.db_pfad = db_pfad or DB_PFAD
        db_schema_anlegen(SCHEMA_MEMORY, self.db_pfad)

    # -- Grundlagen ---------------------------------------------------------

    def _schreiben(self, sql: str, werte: tuple = ()) -> int:
        with _DB_SPERRE:
            verbindung = db_verbindung(self.db_pfad)
            try:
                zeiger = verbindung.execute(sql, werte)
                verbindung.commit()
                return zeiger.lastrowid
            finally:
                verbindung.close()

    def _lesen(self, sql: str, werte: tuple = ()) -> list:
        verbindung = db_verbindung(self.db_pfad)
        try:
            return zeilen_zu_liste(verbindung.execute(sql, werte).fetchall())
        finally:
            verbindung.close()

    # -- Notizen ------------------------------------------------------------

    def notiz_speichern(self, text: str, kategorie: str = "allgemein") -> dict:
        """Hält eine Notiz fest und gibt sie mit ihrer Nummer zurück."""
        text = (text or "").strip()
        if not text:
            return {"ok": False, "fehler": "Die Notiz ist leer."}
        nummer = self._schreiben(
            "INSERT INTO notizen (text, kategorie, angelegt) VALUES (?,?,?)",
            (text, kategorie or "allgemein", zeitstempel()))
        self._spiegeln("notizen", {"text": text, "kategorie": kategorie})
        return {"ok": True, "id": nummer, "text": text, "kategorie": kategorie}

    def notizen_suchen(self, begriff: str, limit: int = 20) -> list:
        """Sucht Notizen, deren Text den Begriff enthält."""
        begriff = (begriff or "").strip()
        if not begriff:
            return self.notizen_letzte(limit)
        return self._lesen(
            "SELECT * FROM notizen WHERE text LIKE ? OR kategorie LIKE ? "
            "ORDER BY id DESC LIMIT ?",
            ("%%%s%%" % begriff, "%%%s%%" % begriff, limit))

    def notizen_letzte(self, limit: int = 10) -> list:
        """Die zuletzt angelegten Notizen."""
        return self._lesen("SELECT * FROM notizen ORDER BY id DESC LIMIT ?", (limit,))

    def notiz_loeschen(self, nummer: int) -> bool:
        """Löscht eine Notiz anhand ihrer Nummer."""
        vorher = self._lesen("SELECT id FROM notizen WHERE id=?", (nummer,))
        if not vorher:
            return False
        self._schreiben("DELETE FROM notizen WHERE id=?", (nummer,))
        return True

    # -- Kontakte -----------------------------------------------------------

    def kontakt_anlegen(self, name: str, firma: str = "", telefon: str = "",
                        email: str = "", adresse: str = "", notiz: str = "") -> dict:
        """Legt einen Kontakt an oder ergänzt einen bereits vorhandenen."""
        name = (name or "").strip()
        if not name:
            return {"ok": False, "fehler": "Ohne Namen kann ich keinen Kontakt anlegen."}
        vorhanden = self._lesen(
            "SELECT * FROM kontakte WHERE lower(name)=lower(?) LIMIT 1", (name,))
        if vorhanden:
            alt = vorhanden[0]
            neu = {
                "firma": firma or alt["firma"],
                "telefon": telefon or alt["telefon"],
                "email": email or alt["email"],
                "adresse": adresse or alt["adresse"],
                "notiz": (alt["notiz"] + " | " + notiz).strip(" |") if notiz else alt["notiz"],
            }
            self._schreiben(
                "UPDATE kontakte SET firma=?, telefon=?, email=?, adresse=?, notiz=? "
                "WHERE id=?",
                (neu["firma"], neu["telefon"], neu["email"], neu["adresse"],
                 neu["notiz"], alt["id"]))
            return {"ok": True, "id": alt["id"], "name": name, "aktualisiert": True}
        nummer = self._schreiben(
            "INSERT INTO kontakte (name, firma, telefon, email, adresse, notiz, angelegt) "
            "VALUES (?,?,?,?,?,?,?)",
            (name, firma, telefon, email, adresse, notiz, zeitstempel()))
        self._spiegeln("kontakte", {"name": name, "firma": firma})
        return {"ok": True, "id": nummer, "name": name, "aktualisiert": False}

    def kontakt_suchen(self, begriff: str, limit: int = 20) -> list:
        """Sucht Kontakte über Name, Firma, Telefon, E-Mail oder Notiz."""
        begriff = (begriff or "").strip()
        if not begriff:
            return self._lesen("SELECT * FROM kontakte ORDER BY name LIMIT ?", (limit,))
        muster = "%%%s%%" % begriff
        return self._lesen(
            "SELECT * FROM kontakte WHERE name LIKE ? OR firma LIKE ? OR telefon LIKE ? "
            "OR email LIKE ? OR notiz LIKE ? ORDER BY name LIMIT ?",
            (muster, muster, muster, muster, muster, limit))

    def kontakte_alle(self) -> list:
        """Alle Kontakte, alphabetisch."""
        return self._lesen("SELECT * FROM kontakte ORDER BY name")

    # -- Kennzahlen ---------------------------------------------------------

    def kennzahl_setzen(self, name: str, wert: float, einheit: str = "") -> dict:
        """Hält eine Kennzahl mit Datum fest (Verlauf bleibt erhalten)."""
        try:
            wert = float(wert)
        except (TypeError, ValueError):
            return {"ok": False, "fehler": "Der Wert ist keine Zahl."}
        nummer = self._schreiben(
            "INSERT INTO kennzahlen (name, wert, einheit, datum) VALUES (?,?,?,?)",
            (name, wert, einheit, heute_datum()))
        return {"ok": True, "id": nummer, "name": name, "wert": wert, "einheit": einheit}

    def kennzahlen(self, limit: int = 30) -> list:
        """Der jeweils jüngste Stand jeder Kennzahl."""
        return self._lesen(
            "SELECT name, wert, einheit, datum FROM kennzahlen k WHERE id = "
            "(SELECT max(id) FROM kennzahlen WHERE name = k.name) "
            "ORDER BY name LIMIT ?", (limit,))

    # -- Offene Punkte ------------------------------------------------------

    def punkt_anlegen(self, text: str, faellig: str = "") -> dict:
        """Merkt sich etwas, das noch zu erledigen ist."""
        text = (text or "").strip()
        if not text:
            return {"ok": False, "fehler": "Der offene Punkt ist leer."}
        nummer = self._schreiben(
            "INSERT INTO offene_punkte (text, faellig, erledigt, angelegt) VALUES (?,?,0,?)",
            (text, faellig, zeitstempel()))
        return {"ok": True, "id": nummer, "text": text, "faellig": faellig}

    def punkte_offen(self, tage: int = 14, limit: int = 25) -> list:
        """Offene Punkte der letzten ``tage`` Tage."""
        grenze = (datetime.now() - timedelta(days=tage)).strftime("%Y-%m-%d 00:00:00")
        return self._lesen(
            "SELECT * FROM offene_punkte WHERE erledigt=0 AND angelegt>=? "
            "ORDER BY id DESC LIMIT ?", (grenze, limit))

    def punkt_erledigen(self, nummer: int) -> bool:
        """Hakt einen offenen Punkt ab."""
        vorher = self._lesen("SELECT id FROM offene_punkte WHERE id=? AND erledigt=0",
                             (nummer,))
        if not vorher:
            return False
        self._schreiben("UPDATE offene_punkte SET erledigt=1 WHERE id=?", (nummer,))
        return True

    # -- Protokoll ----------------------------------------------------------

    def aktion_protokollieren(self, werkzeug: str, argumente=None, ergebnis: str = "",
                              status: str = "ok") -> int:
        """Schreibt jede ausgeführte Aktion mit - Grundlage für das Dashboard."""
        try:
            argument_text = json.dumps(argumente, ensure_ascii=False)[:2000]
        except (TypeError, ValueError):
            argument_text = str(argumente)[:2000]
        return self._schreiben(
            "INSERT INTO aktionen (werkzeug, argumente, ergebnis, status, zeit) "
            "VALUES (?,?,?,?,?)",
            (werkzeug, argument_text, str(ergebnis)[:2000], status, zeitstempel()))

    def protokoll(self, limit: int = 30) -> list:
        """Die zuletzt ausgeführten Aktionen."""
        return self._lesen("SELECT * FROM aktionen ORDER BY id DESC LIMIT ?", (limit,))

    # -- Gesprächsverlauf ---------------------------------------------------

    def verlauf_anhaengen(self, rolle: str, text: str) -> int:
        """Hängt eine Äußerung an den dauerhaften Verlauf an."""
        return self._schreiben(
            "INSERT INTO verlauf (rolle, text, zeit) VALUES (?,?,?)",
            (rolle, (text or "")[:8000], zeitstempel()))

    def verlauf_letzte(self, limit: int = 20) -> list:
        """Die letzten Äußerungen, in zeitlicher Reihenfolge."""
        zeilen = self._lesen("SELECT * FROM verlauf ORDER BY id DESC LIMIT ?", (limit,))
        return list(reversed(zeilen))

    def verlauf_zeitraum(self, von: str, bis: str, begriff: str = "",
                         limit: int = 500) -> list:
        """Äußerungen zwischen zwei Zeitstempeln, in zeitlicher Reihenfolge.

        Mit ``begriff`` kommen nur Zeilen, in denen der Begriff vorkommt - egal,
        wer gesprochen hat.
        """
        sql = "SELECT * FROM verlauf WHERE zeit BETWEEN ? AND ?"
        werte = [von, bis]
        begriff = (begriff or "").strip()
        if begriff:
            sql += " AND text LIKE ?"
            werte.append("%%%s%%" % begriff)
        sql += " ORDER BY id DESC LIMIT ?"
        werte.append(int(limit))
        return list(reversed(self._lesen(sql, tuple(werte))))

    def aktionen_zeitraum(self, von: str, bis: str, limit: int = 500) -> list:
        """Ausgeführte Aktionen zwischen zwei Zeitstempeln, in zeitlicher Reihenfolge."""
        zeilen = self._lesen(
            "SELECT * FROM aktionen WHERE zeit BETWEEN ? AND ? ORDER BY id DESC LIMIT ?",
            (von, bis, int(limit)))
        return list(reversed(zeilen))

    def aeusserungen_suchen(self, begriff: str, limit: int = 8) -> list:
        """Sucht in früheren Äußerungen des Nutzers."""
        begriff = (begriff or "").strip()
        if not begriff:
            return []
        return self._lesen(
            "SELECT * FROM verlauf WHERE rolle='user' AND text LIKE ? "
            "ORDER BY id DESC LIMIT ?", ("%%%s%%" % begriff, limit))

    # -- Übersicht ----------------------------------------------------------

    def statistik(self) -> dict:
        """Zählt, was im Gedächtnis liegt."""
        ergebnis = {}
        for tabelle in ("notizen", "kontakte", "kennzahlen", "aktionen", "verlauf"):
            try:
                zeilen = self._lesen("SELECT count(*) AS n FROM %s" % tabelle)
                ergebnis[tabelle] = zeilen[0]["n"] if zeilen else 0
            except sqlite3.Error:
                ergebnis[tabelle] = 0
        ergebnis["offene_punkte"] = len(self.punkte_offen())
        return ergebnis

    # -- Optionale Spiegelung ----------------------------------------------

    def _spiegeln(self, tabelle: str, daten: dict):
        """Spiegelt einen Datensatz nach Supabase - scheitert lautlos, nie blockierend."""
        if not (SUPABASE_URL and SUPABASE_KEY):
            return
        try:
            ziel = "%s/rest/v1/%s" % (SUPABASE_URL.rstrip("/"), tabelle)
            anfrage = urllib.request.Request(
                ziel, data=json.dumps(daten).encode("utf-8"), method="POST",
                headers={
                    "apikey": SUPABASE_KEY,
                    "Authorization": "Bearer %s" % SUPABASE_KEY,
                    "Content-Type": "application/json",
                    "Prefer": "return=minimal",
                })
            urllib.request.urlopen(anfrage, timeout=5).read()
        except (urllib.error.URLError, OSError, ValueError):
            pass


# =========================================================================
# recall  -  Gedächtnis, Ebene 1 und 2 - Tagesberichte und gezieltes Nachschlagen.
# 
# Warum zwei Ebenen? Ein Verlauf von Monaten passt in kein Kontextfenster und
# macht jede Antwort langsam und teuer. Deshalb:
# 
# * Ebene 1: Abends fasst Jarvis den Tag in wenigen Sätzen zusammen. Viele
#   solcher Berichte passen gleichzeitig in den Systemprompt.
# * Ebene 2: Vor jeder Antwort werden die tragenden Wörter der Frage in Notizen,
#   Kontakten, Tagesberichten und früheren Äußerungen nachgeschlagen. Nur die
#   Treffer werden beigelegt.
# =========================================================================

#!/usr/bin/env python3
# -*- coding: utf-8 -*-



SCHEMA_RECALL = """
CREATE TABLE IF NOT EXISTS tagesberichte (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    datum TEXT NOT NULL,
    zusammenfassung TEXT NOT NULL,
    entscheidungen TEXT DEFAULT '',
    offen TEXT DEFAULT '',
    angelegt TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_berichte_datum ON tagesberichte(datum);
"""

# Wörter, die in fast jedem Satz vorkommen und deshalb nichts einengen.
STOPPWOERTER = {
    "aber", "alle", "allem", "allen", "aller", "alles", "also", "andere", "auch",
    "auf", "aus", "bei", "beim", "bin", "bis", "bist", "dann", "dass", "dein",
    "deine", "dem", "den", "denn", "der", "des", "dich", "die", "dies", "diese",
    "diesem", "diesen", "dieser", "dieses", "dir", "doch", "dort", "durch",
    "ein", "eine", "einem", "einen", "einer", "eines", "einfach", "etwas",
    "euch", "euer", "eure", "für", "fuer", "gegen", "gewesen", "hab", "habe",
    "haben", "hat", "hatte", "hatten", "hier", "hin", "ich", "ihm", "ihn",
    "ihnen", "ihr", "ihre", "immer", "ist", "jede", "jedem", "jeden", "jeder",
    "jetzt", "kann", "kannst", "können", "koennen", "machen", "mehr", "mein",
    "meine", "mich", "mir", "mit", "muss", "musst", "müssen", "muessen", "nach",
    "nicht", "noch", "nun", "nur", "oben", "oder", "ohne", "schon", "sehr",
    "sein", "seine", "seit", "sich", "sie", "sind", "soll", "sollen", "sondern",
    "sonst", "über", "ueber", "und", "uns", "unser", "unter", "vom", "von",
    "vor", "war", "waren", "warum", "was", "weg", "weil", "weiter", "welche",
    "wenn", "werde", "werden", "wie", "wieder", "will", "wir", "wird", "wirst",
    "wo", "wollen", "wurde", "wurden", "zum", "zur", "zwar", "zwischen",
    "steht", "gibt", "geht", "mach", "sage", "sagen", "bitte", "danke", "jarvis",
}


def schluesselwoerter(text: str, mindestlaenge: int = 4) -> list:
    """Zerlegt einen Satz in seine tragenden Wörter (ab 4 Zeichen, ohne Stoppwörter)."""
    if not text:
        return []
    roh = re.findall(r"[0-9A-Za-zÄÖÜäöüß_-]+", str(text).lower())
    treffer = []
    for wort in roh:
        if len(wort) < mindestlaenge:
            continue
        if wort in STOPPWOERTER:
            continue
        if wort not in treffer:
            treffer.append(wort)
    return treffer[:12]


class Recall:
    """Langzeitgedächtnis: schreibt Tagesberichte und schlägt gezielt nach."""

    def __init__(self, memory: Memory = None):
        self.memory = memory or Memory()
        db_schema_anlegen(SCHEMA_RECALL, self.memory.db_pfad)

    # -- Ebene 1: Tagesberichte --------------------------------------------

    def tagesbericht_speichern(self, zusammenfassung: str, entscheidungen: str = "",
                               offen: str = "", datum: str = "") -> dict:
        """Legt den Bericht eines Tages ab (ein Bericht pro Datum)."""
        zusammenfassung = (zusammenfassung or "").strip()
        if not zusammenfassung:
            return {"ok": False, "fehler": "Der Tagesbericht ist leer."}
        datum = (datum or heute_datum()).strip()
        vorhanden = self.memory._lesen(
            "SELECT id FROM tagesberichte WHERE datum=? LIMIT 1", (datum,))
        if vorhanden:
            self.memory._schreiben(
                "UPDATE tagesberichte SET zusammenfassung=?, entscheidungen=?, offen=?, "
                "angelegt=? WHERE id=?",
                (zusammenfassung, entscheidungen, offen, zeitstempel(), vorhanden[0]["id"]))
            return {"ok": True, "id": vorhanden[0]["id"], "datum": datum, "ersetzt": True}
        nummer = self.memory._schreiben(
            "INSERT INTO tagesberichte (datum, zusammenfassung, entscheidungen, offen, angelegt) "
            "VALUES (?,?,?,?,?)",
            (datum, zusammenfassung, entscheidungen, offen, zeitstempel()))
        return {"ok": True, "id": nummer, "datum": datum, "ersetzt": False}

    def tagesberichte_letzte(self, anzahl: int = 7) -> list:
        """Die jüngsten Tagesberichte, neuester zuerst."""
        return self.memory._lesen(
            "SELECT * FROM tagesberichte ORDER BY datum DESC, id DESC LIMIT ?", (anzahl,))

    def tagesberichte_suchen(self, begriff: str, limit: int = 6) -> list:
        """Sucht in Tagesberichten nach einem Begriff."""
        begriff = (begriff or "").strip()
        if not begriff:
            return []
        muster = "%%%s%%" % begriff
        return self.memory._lesen(
            "SELECT * FROM tagesberichte WHERE zusammenfassung LIKE ? OR entscheidungen LIKE ? "
            "OR offen LIKE ? ORDER BY datum DESC LIMIT ?", (muster, muster, muster, limit))

    # -- Ebene 2: Nachschlagen ---------------------------------------------

    def nachschlagen(self, frage: str, pro_quelle: int = 4) -> dict:
        """Sucht die tragenden Wörter einer Frage in allen Gedächtnisquellen."""
        woerter = schluesselwoerter(frage)
        gefunden = {"woerter": woerter, "notizen": [], "kontakte": [],
                    "berichte": [], "aeusserungen": []}
        if not woerter:
            return gefunden
        gesehen = {"notizen": set(), "kontakte": set(), "berichte": set(),
                   "aeusserungen": set()}
        for wort in woerter:
            for notiz in self.memory.notizen_suchen(wort, pro_quelle):
                if notiz["id"] not in gesehen["notizen"]:
                    gesehen["notizen"].add(notiz["id"])
                    gefunden["notizen"].append(notiz)
            for kontakt in self.memory.kontakt_suchen(wort, pro_quelle):
                if kontakt["id"] not in gesehen["kontakte"]:
                    gesehen["kontakte"].add(kontakt["id"])
                    gefunden["kontakte"].append(kontakt)
            for bericht in self.tagesberichte_suchen(wort, pro_quelle):
                if bericht["id"] not in gesehen["berichte"]:
                    gesehen["berichte"].add(bericht["id"])
                    gefunden["berichte"].append(bericht)
            for zeile in self.memory.aeusserungen_suchen(wort, pro_quelle):
                if zeile["id"] not in gesehen["aeusserungen"]:
                    gesehen["aeusserungen"].add(zeile["id"])
                    gefunden["aeusserungen"].append(zeile)
        for schluessel in ("notizen", "kontakte", "berichte", "aeusserungen"):
            gefunden[schluessel] = gefunden[schluessel][:8]
        return gefunden

    def gedaechtnis_block(self, frage: str = "") -> str:
        """Baut den Gedächtnisteil des Systemprompts.

        Enthält immer die offenen Punkte der letzten 14 Tage und die letzten
        Tagesberichte, dazu die zur Frage passenden Treffer.
        """
        teile = []

        punkte = self.memory.punkte_offen(tage=14)
        if punkte:
            zeilen = ["Offene Punkte der letzten 14 Tage:"]
            for punkt in punkte[:12]:
                faellig = (" (fällig %s)" % punkt["faellig"]) if punkt["faellig"] else ""
                zeilen.append("- [%d] %s%s" % (punkt["id"], punkt["text"], faellig))
            teile.append("\n".join(zeilen))

        berichte = self.tagesberichte_letzte(7)
        if berichte:
            zeilen = ["Was an den letzten Tagen war:"]
            for bericht in berichte:
                satz = "- %s: %s" % (bericht["datum"], bericht["zusammenfassung"])
                if bericht["offen"]:
                    satz += " Noch offen: %s" % bericht["offen"]
                zeilen.append(satz)
            teile.append("\n".join(zeilen))

        if frage:
            treffer = self.nachschlagen(frage)
            zeilen = []
            for notiz in treffer["notizen"]:
                zeilen.append("- Notiz vom %s: %s" % (notiz["angelegt"][:10], notiz["text"]))
            for kontakt in treffer["kontakte"]:
                beschreibung = ", ".join(
                    [t for t in (kontakt["firma"], kontakt["telefon"], kontakt["email"],
                                 kontakt["notiz"]) if t])
                zeilen.append("- Kontakt %s: %s" % (kontakt["name"], beschreibung or "keine Details"))
            for bericht in treffer["berichte"]:
                zeilen.append("- Tagesbericht %s: %s" % (bericht["datum"],
                                                         bericht["zusammenfassung"]))
            for zeile in treffer["aeusserungen"]:
                zeilen.append("- Er sagte am %s: %s" % (zeile["zeit"][:10], zeile["text"][:200]))
            if zeilen:
                teile.append("Passend zur aktuellen Frage:\n" + "\n".join(zeilen[:14]))

        if not teile:
            return ""
        return "Das weißt du aus früheren Tagen:\n\n" + "\n\n".join(teile)

    # -- Tag zusammenfassen -------------------------------------------------

    def tag_zusammenfassen(self, agent=None, datum: str = "") -> dict:
        """Fasst den heutigen Tag zusammen - mit Claude, sonst mechanisch."""
        datum = datum or heute_datum()
        beginn = "%s 00:00:00" % datum
        ende = "%s 23:59:59" % datum

        aeusserungen = self.memory._lesen(
            "SELECT rolle, text, zeit FROM verlauf WHERE zeit BETWEEN ? AND ? ORDER BY id",
            (beginn, ende))
        aktionen = self.memory._lesen(
            "SELECT werkzeug, status, zeit FROM aktionen WHERE zeit BETWEEN ? AND ? ORDER BY id",
            (beginn, ende))
        punkte = self.memory.punkte_offen(tage=1)

        if not aeusserungen and not aktionen:
            bericht = "An diesem Tag ist nichts festgehalten worden."
            self.tagesbericht_speichern(bericht, "", "", datum)
            return {"ok": True, "datum": datum, "zusammenfassung": bericht, "quelle": "leer"}

        rohtext = []
        for zeile in aeusserungen[-60:]:
            rohtext.append("%s: %s" % ("Er" if zeile["rolle"] == "user" else "Jarvis",
                                       zeile["text"][:400]))
        werkzeugliste = ", ".join(sorted({a["werkzeug"] for a in aktionen})) or "keine"

        if agent is not None and getattr(agent, "einsatzbereit", lambda: False)():
            auftrag = (
                "Fasse diesen Arbeitstag für dein eigenes Gedächtnis zusammen. "
                "Antworte als JSON mit den Schlüsseln zusammenfassung, entscheidungen, offen. "
                "zusammenfassung: drei bis fünf Sätze, worum es ging. "
                "entscheidungen: was entschieden wurde, ein Satz oder leer. "
                "offen: was offen blieb, ein Satz oder leer.\n\n"
                "Gespräche des Tages:\n%s\n\nBenutzte Werkzeuge: %s"
                % ("\n".join(rohtext) or "keine", werkzeugliste))
            antwort = agent.json_anfrage(auftrag)
            if antwort.get("ok"):
                daten = antwort["daten"]
                self.tagesbericht_speichern(
                    str(daten.get("zusammenfassung", "")).strip(),
                    str(daten.get("entscheidungen", "")).strip(),
                    str(daten.get("offen", "")).strip(), datum)
                return {"ok": True, "datum": datum, "quelle": "claude",
                        "zusammenfassung": daten.get("zusammenfassung", ""),
                        "entscheidungen": daten.get("entscheidungen", ""),
                        "offen": daten.get("offen", "")}

        # Rückfallebene ohne Claude: mechanisch, aber ehrlich.
        themen = []
        for zeile in aeusserungen:
            if zeile["rolle"] != "user":
                continue
            for wort in schluesselwoerter(zeile["text"])[:3]:
                if wort not in themen:
                    themen.append(wort)
        zusammenfassung = ("%d Gespräche, %d Aktionen. Themen: %s."
                           % (len([z for z in aeusserungen if z["rolle"] == "user"]),
                              len(aktionen), ", ".join(themen[:10]) or "keine erkennbaren"))
        offen_text = "; ".join(p["text"] for p in punkte[:5])
        self.tagesbericht_speichern(zusammenfassung, "", offen_text, datum)
        return {"ok": True, "datum": datum, "quelle": "mechanisch",
                "zusammenfassung": zusammenfassung, "entscheidungen": "", "offen": offen_text}

    def rueckblick(self, tage: int = 7) -> str:
        """Ein zusammenhängender Text über die letzten Tage - für den Wochenrückblick."""
        grenze = (datetime.now() - timedelta(days=tage)).strftime("%Y-%m-%d")
        berichte = self.memory._lesen(
            "SELECT * FROM tagesberichte WHERE datum>=? ORDER BY datum", (grenze,))
        if not berichte:
            return "Für die letzten %d Tage liegen noch keine Tagesberichte vor." % tage
        zeilen = []
        for bericht in berichte:
            zeilen.append("%s: %s" % (bericht["datum"], bericht["zusammenfassung"]))
            if bericht["entscheidungen"]:
                zeilen.append("   Entschieden: %s" % bericht["entscheidungen"])
            if bericht["offen"]:
                zeilen.append("   Offen: %s" % bericht["offen"])
        return "\n".join(zeilen)

    # -- Protokoll ----------------------------------------------------------

    @staticmethod
    def tag_aufloesen(text: str = "") -> str:
        """Macht aus 'heute', 'gestern', '07.10.' oder '2026-10-07' ein Datum.

        Gibt einen leeren Text zurück, wenn der Tag nicht zu lesen ist - der
        Aufrufer sagt das dann, statt still den falschen Tag zu zeigen.
        """
        roh = (text or "").strip().lower()
        heute = datetime.now()
        if roh in ("", "heute"):
            return heute.strftime("%Y-%m-%d")
        if roh == "gestern":
            return (heute - timedelta(days=1)).strftime("%Y-%m-%d")
        if roh == "vorgestern":
            return (heute - timedelta(days=2)).strftime("%Y-%m-%d")
        for muster in ("%Y-%m-%d", "%d.%m.%Y", "%d.%m.%y"):
            try:
                return datetime.strptime(roh, muster).strftime("%Y-%m-%d")
            except ValueError:
                pass
        try:  # '07.10.' ohne Jahr: das laufende Jahr
            tag = datetime.strptime(roh.rstrip(".") + ".%d" % heute.year, "%d.%m.%Y")
            return tag.strftime("%Y-%m-%d")
        except ValueError:
            return ""

    def protokoll(self, tag: str = "heute", thema: str = "", tage: int = 1) -> dict:
        """Das Protokoll eines Tages: Gespräche, Aktionen, Tagesbericht, Offenes.

        ``tage`` > 1 nimmt die davorliegenden Tage dazu (Wochenprotokoll).
        ``thema`` engt die Gespräche auf Zeilen mit diesem Begriff ein.
        """
        datum = self.tag_aufloesen(tag)
        if not datum:
            return {"ok": False, "text": "Den Tag '%s' kann ich nicht lesen. "
                                         "Sag heute, gestern oder ein Datum." % tag}
        tage = max(1, min(int(tage or 1), 31))
        erster = (datetime.strptime(datum, "%Y-%m-%d")
                  - timedelta(days=tage - 1)).strftime("%Y-%m-%d")
        von, bis = "%s 00:00:00" % erster, "%s 23:59:59" % datum
        thema = (thema or "").strip()

        gespraeche = [{"rolle": z["rolle"], "text": z["text"], "zeit": z["zeit"]}
                      for z in self.memory.verlauf_zeitraum(von, bis, thema)]
        aktionen = [{"werkzeug": a["werkzeug"], "status": a["status"],
                     "ergebnis": (a["ergebnis"] or "")[:200], "zeit": a["zeit"]}
                    for a in self.memory.aktionen_zeitraum(von, bis)]
        berichte = self.memory._lesen(
            "SELECT * FROM tagesberichte WHERE datum BETWEEN ? AND ? ORDER BY datum, id",
            (erster, datum))
        berichte = [{"datum": b["datum"], "zusammenfassung": b["zusammenfassung"],
                     "entscheidungen": b["entscheidungen"], "offen": b["offen"]}
                    for b in berichte]
        punkte = [{"id": p["id"], "text": p["text"], "faellig": p["faellig"]}
                  for p in self.memory.punkte_offen()]

        von_ihm = len([g for g in gespraeche if g["rolle"] == "user"])
        saetze = []
        zeitraum = datum if tage == 1 else "%s bis %s" % (erster, datum)
        if not gespraeche and not aktionen:
            saetze.append("Für %s ist nichts protokolliert%s." % (
                zeitraum, (" zum Thema %s" % thema) if thema else ""))
        else:
            saetze.append("%s: %d Äußerungen von dir, %d Aktionen%s." % (
                zeitraum, von_ihm, len(aktionen),
                (" zum Thema %s" % thema) if thema else ""))
            if berichte:
                saetze.append(berichte[-1]["zusammenfassung"])
            letzte = [g for g in gespraeche if g["rolle"] == "user"][-3:]
            if letzte:
                saetze.append("Zuletzt hast du gesagt: %s" % " / ".join(
                    g["text"][:120] for g in letzte))
            werkzeuge = sorted({a["werkzeug"] for a in aktionen})
            if werkzeuge:
                saetze.append("Benutzt: %s." % ", ".join(werkzeuge[:8]))
        if punkte:
            saetze.append("Offen: %s." % "; ".join(p["text"] for p in punkte[:4]))

        return {"ok": True, "datum": datum, "von": erster, "tage": tage,
                "thema": thema, "gespraeche": gespraeche, "aktionen": aktionen,
                "berichte": berichte, "offene_punkte": punkte,
                "text": " ".join(saetze)}


# =========================================================================
# lokal  -  Lokales Modell - Jarvis denkt auf diesem Rechner statt bei Anthropic.
# 
# Kostet nichts, hat kein Limit und schickt nichts ins Netz. Dafür ist ein
# kleines lokales Modell deutlich schwächer als Claude und auf einem älteren Mac
# langsam. Gedacht als Weg ohne Schlüssel und ohne laufende Kosten.
# 
# Gesprochen wird mit Ollama (https://ollama.com), das auf dem Rechner läuft. Der
# Rest von Jarvis spricht weiter das Format der Claude-Schnittstelle; dieses
# Modul übersetzt hin und zurück, damit Schleifen und Werkzeuge unverändert
# bleiben.
# 
# **Werkzeugauswahl.** Alle gut sechzig Werkzeuge mitzuschicken würde eine
# Anfrage auf einem Intel-Mac um Minuten verlängern und kleine Modelle
# verwirren. Deshalb gehen nur die Werkzeuge mit, die zur Frage passen, plus ein
# kleiner Grundstock.
# =========================================================================

#!/usr/bin/env python3
# -*- coding: utf-8 -*-



STANDARD_MODELL = "qwen2.5:3b"
GRUNDSTOCK = ("notiz_speichern", "gedaechtnis_durchsuchen", "protokoll", "punkte_offen")
MAX_WERKZEUGE = 10
ADRESSE_IM_TEXT = re.compile(r"https?://|www\.|\b[\w-]+\.(at|de|com|ch|eu|net|org|info)\b", re.I)

# Werkzeuge, die etwas abschließen oder streichen. Kleine Modelle rufen sie
# gern "vorsorglich" mit auf (offenen Punkt anlegen -> nebenbei Punkt 1
# abhaken). Deshalb gibt es sie nur, wenn die Frage es selbst verlangt.
VORSICHT = {
    "punkt_erledigen": ("erledig", "abhak", "fertig", "geschafft", "streich", "erlédig"),
    "erinnerung_erledigen": ("erledig", "abhak", "fertig", "geschafft", "streich"),
    "fixkosten_streichen": ("streich", "kündig", "lösch", "entfern", "nicht mehr"),
}


def lokales_modell_aktiv() -> bool:
    """Ist ein lokales Modell eingestellt?"""
    return bool((LOKALES_MODELL or "").strip())


def _adresse(pfad: str) -> str:
    return OLLAMA_URL.rstrip("/") + pfad


def ollama_pruefen(modell: str = "") -> dict:
    """Läuft Ollama, und ist das Modell geladen? Sagt auf Deutsch, was fehlt."""
    modell = (modell or LOKALES_MODELL or STANDARD_MODELL).strip()
    try:
        with urllib.request.urlopen(_adresse("/api/tags"), timeout=5) as antwort:
            daten = json.loads(antwort.read().decode("utf-8"))
    except (urllib.error.URLError, OSError, ValueError):
        return {"ok": False, "grund": "ollama",
                "text": "Ollama läuft nicht. Lade es auf ollama.com/download, "
                        "installiere es und öffne es einmal. Dann sag Bescheid."}
    vorhanden = [m.get("name", "") for m in daten.get("models", [])]
    gleich = [n for n in vorhanden if n == modell or n == modell + ":latest"
              or (":" not in modell and n.split(":")[0] == modell)]
    if not gleich:
        return {"ok": False, "grund": "modell", "vorhanden": vorhanden,
                "text": "Das Modell %s ist noch nicht geladen. Gib im Terminal ein: "
                        "ollama pull %s" % (modell, modell)}
    return {"ok": True, "modell": gleich[0],
            "text": "Das lokale Modell %s ist bereit." % gleich[0]}


def werkzeuge_auswaehlen(katalog: list, frage: str, anzahl: int = MAX_WERKZEUGE,
                         benutzt: tuple = ()) -> list:
    """Wählt die zur Frage passenden Werkzeuge aus dem Katalog."""
    woerter = [w[:5] for w in schluesselwoerter(frage or "")]
    bewertet = []
    for nr, werkzeug in enumerate(katalog):
        name = werkzeug.get("name", "")
        if name in VORSICHT and not any(w in (frage or "").lower() for w in VORSICHT[name]):
            continue
        text = (name + " " + werkzeug.get("description", "")).lower()
        punkte = sum(2 if w in name.lower() else 1 for w in woerter if w in text)
        if name in benutzt:
            punkte += 3
        if name == "webseite_lesen" and ADRESSE_IM_TEXT.search(frage or ""):
            punkte += 10  # eine Adresse im Satz heißt: Seite lesen
        if name in GRUNDSTOCK:
            punkte += 1
        bewertet.append((punkte, -nr, werkzeug))
    bewertet.sort(key=lambda t: (t[0], t[1]), reverse=True)
    gewaehlt = [w for p, _, w in bewertet if p > 0][:anzahl]
    for werkzeug in katalog:  # der Grundstock fehlt nie ganz
        if werkzeug.get("name") in GRUNDSTOCK and werkzeug not in gewaehlt:
            gewaehlt.append(werkzeug)
    return gewaehlt[:anzahl + len(GRUNDSTOCK)]


def _text_aus_lokal(inhalt) -> str:
    if isinstance(inhalt, str):
        return inhalt
    return "\n".join(b.get("text", "") for b in inhalt or []
                     if isinstance(b, dict) and b.get("type") == "text")


def nachrichten_umwandeln_lokal(system: str, nachrichten: list) -> list:
    """Claude-Nachrichten in das Format von Ollama übersetzen."""
    ergebnis = []
    if system:
        ergebnis.append({"role": "system", "content": system})
    namen = {}  # tool_use_id -> Werkzeugname
    for nachricht in nachrichten:
        rolle, inhalt = nachricht.get("role"), nachricht.get("content")
        if rolle == "assistant":
            aufrufe = []
            for block in inhalt if isinstance(inhalt, list) else []:
                if isinstance(block, dict) and block.get("type") == "tool_use":
                    namen[block.get("id")] = block.get("name", "")
                    aufrufe.append({"function": {"name": block.get("name", ""),
                                                 "arguments": block.get("input") or {}}})
            eintrag = {"role": "assistant", "content": _text_aus_lokal(inhalt)}
            if aufrufe:
                eintrag["tool_calls"] = aufrufe
            ergebnis.append(eintrag)
        elif isinstance(inhalt, list):
            bilder = []
            for block in inhalt:
                if not isinstance(block, dict):
                    continue
                if block.get("type") == "tool_result":
                    ergebnis.append({"role": "tool",
                                     "tool_name": namen.get(block.get("tool_use_id"), ""),
                                     "content": _text_aus_lokal(block.get("content"))})
                elif block.get("type") == "image":
                    bilder.append((block.get("source") or {}).get("data", ""))
            text = _text_aus_lokal(inhalt)
            if text or bilder:
                eintrag = {"role": "user", "content": text}
                if bilder:
                    eintrag["images"] = [b for b in bilder if b]
                ergebnis.append(eintrag)
        else:
            ergebnis.append({"role": "user", "content": inhalt or ""})
    return ergebnis


def antwort_umwandeln_lokal(daten: dict) -> list:
    """Die Antwort von Ollama als Inhaltsblöcke im Claude-Format."""
    nachricht = daten.get("message") or {}
    bloecke = []
    text = (nachricht.get("content") or "").strip()
    if text:
        bloecke.append({"type": "text", "text": text})
    for nr, aufruf in enumerate(nachricht.get("tool_calls") or []):
        funktion = aufruf.get("function") or {}
        argumente = funktion.get("arguments") or {}
        if isinstance(argumente, str):
            try:
                argumente = json.loads(argumente)
            except ValueError:
                argumente = {}
        if not isinstance(argumente, dict):
            argumente = {}
        bloecke.append({"type": "tool_use", "id": "lokal_%d_%d" % (id(aufruf) % 100000, nr),
                        "name": funktion.get("name", ""), "input": argumente})
    return bloecke


def _letzte_frage(nachrichten: list) -> str:
    for nachricht in reversed(nachrichten):
        if nachricht.get("role") == "user":
            text = _text_aus_lokal(nachricht.get("content"))
            if text:
                return text
    return ""


def lokal_anfragen(koerper: dict, timeout: int = 900) -> dict:
    """Beantwortet eine Anfrage im Claude-Format mit dem lokalen Modell."""
    nachrichten = koerper.get("messages") or []
    benutzt = tuple(b.get("name", "") for n in nachrichten
                    if isinstance(n.get("content"), list) for b in n["content"]
                    if isinstance(b, dict) and b.get("type") == "tool_use")
    katalog = koerper.get("tools") or []
    gewaehlt = werkzeuge_auswaehlen(katalog, _letzte_frage(nachrichten), benutzt=benutzt) \
        if katalog else []
    nutzlast = {
        "model": LOKALES_MODELL,
        "messages": nachrichten_umwandeln_lokal(koerper.get("system", ""), nachrichten),
        "stream": False,
        "keep_alive": "30m",
        "options": {"num_predict": int(koerper.get("max_tokens") or 1000),
                    "temperature": 0.3},
    }
    if gewaehlt:
        nutzlast["tools"] = [{"type": "function", "function": {
            "name": w["name"], "description": w.get("description", ""),
            "parameters": w.get("input_schema") or {"type": "object", "properties": {}}}}
            for w in gewaehlt]

    for versuch in range(2):
        anfrage = urllib.request.Request(
            _adresse("/api/chat"), data=json.dumps(nutzlast).encode("utf-8"),
            method="POST", headers={"content-type": "application/json"})
        try:
            with urllib.request.urlopen(anfrage, timeout=timeout) as antwort:
                daten = json.loads(antwort.read().decode("utf-8"))
            bloecke = antwort_umwandeln_lokal(daten)
            if not bloecke:
                bloecke = [{"type": "text", "text": ""}]
            return {"ok": True, "daten": {"content": bloecke}}
        except urllib.error.HTTPError as fehler:
            try:
                meldung = json.loads(fehler.read().decode("utf-8")).get("error", "")
            except (ValueError, OSError):
                meldung = str(fehler)
            if "tools" in meldung.lower() and "tools" in nutzlast and versuch == 0:
                nutzlast.pop("tools")  # Modell kann keine Werkzeuge: dann ohne
                continue
            if fehler.code == 404:
                return {"ok": False, "fehler": "Das lokale Modell %s ist nicht geladen. "
                        "Gib im Terminal ein: ollama pull %s"
                        % (LOKALES_MODELL, LOKALES_MODELL)}
            return {"ok": False, "fehler": "Das lokale Modell meldet einen Fehler (%d): %s"
                    % (fehler.code, meldung[:300])}
        except (urllib.error.URLError, OSError):
            return {"ok": False, "fehler": "Ollama antwortet nicht. Ist die Ollama-App "
                    "geöffnet?"}
        except ValueError as fehler:
            return {"ok": False, "fehler": "Die Antwort war unlesbar: %s" % fehler}
    return {"ok": False, "fehler": "Das lokale Modell hat nicht geantwortet."}


# =========================================================================
# freier_dienst  -  Kostenloser Online-Dienst - Jarvis denkt über einen Gratis-Zugang statt über Anthropic.
# 
# Mehrere Anbieter bieten ein kostenloses Kontingent an und sprechen dieselbe
# "OpenAI-kompatible" Schnittstelle. Wer dort einen Schlüssel holt (ohne
# Guthaben, ohne Karte), kann Jarvis damit betreiben.
# 
# **Was man wissen muss, bevor man das benutzt:**
# 
# * Gratis-Kontingente haben Grenzen pro Minute und pro Tag. Sind sie erreicht,
#   muss man warten. Die Bedingungen ändern die Anbieter von sich aus.
# * Das Gespräch geht an diesen Anbieter - samt allem, was Jarvis dafür aus Mails,
#   Kunden oder Buchhaltung nachschlägt. Bei manchen Gratis-Tarifen dürfen
#   Anbieter Eingaben auch zur Verbesserung ihrer Modelle nutzen. Wer das nicht
#   will, nimmt das lokale Modell.
# * Die Modellnamen wechseln. Deshalb lässt sich das Modell im Fenster ändern.
# 
# Wie beim lokalen Modell gehen nur die zur Frage passenden Werkzeuge mit - das
# spart Kontingent, denn alle sechzig zu schicken kostet jedes Mal Tausende
# Token.
# =========================================================================

#!/usr/bin/env python3
# -*- coding: utf-8 -*-



DIENST_VORGABEN = {
    "groq": {"name": "Groq", "url": "https://api.groq.com/openai/v1",
             "modell": "llama-3.3-70b-versatile",
             "seite": "console.groq.com/keys"},
    "gemini": {"name": "Google Gemini",
               "url": "https://generativelanguage.googleapis.com/v1beta/openai",
               # Mehrere Namen: Jeder hat bei Google sein eigenes Gratis-Kontingent.
               # Die Lite-Modelle zuerst: Sie antworten in etwa einer Sekunde, die
               # großen denken vorher nach und brauchen 4 bis 25 Sekunden.
               "modell": "gemini-flash-lite-latest,gemini-3.5-flash-lite,gemini-3.1-flash-lite,gemini-flash-latest,gemini-3.8-flash",
               "seite": "aistudio.google.com/apikey"},
    "openrouter": {"name": "OpenRouter", "url": "https://openrouter.ai/api/v1",
                   "modell": "meta-llama/llama-3.3-70b-instruct:free",
                   "seite": "openrouter.ai/keys"},
}
DIENST_WERKZEUGE = 12

# Kleine, schnelle Modelle behaupten manchmal, etwas getan zu haben, ohne das
# Werkzeug aufzurufen ("Habe ich notiert" - und nichts ist gespeichert). Daran
# erkennt Jarvis eine solche Behauptung und schickt das Modell einmal zurück.
BEHAUPTUNG = re.compile(
    r"\b(notiert|gespeichert|vermerkt|angelegt|eingetragen|hinterlegt|gesendet|"
    r"verschickt|abgeschickt|erledigt|abgehakt|gebucht|erstellt|aufgenommen|gestartet)\b",
    re.IGNORECASE)
# Nur wenn der Nutzer etwas tun lassen will, ist "erledigt" ohne Werkzeug eine
# Lüge. Beschreibt das Modell ein Bild oder erzählt, darf es diese Wörter benutzen.
AUFTRAG = re.compile(
    r"\b(merk|notier|speicher|leg\w* .{0,40}an\b|anlegen|trag\w* .{0,40}ein|eintragen|"
    r"schick|send|buch|erinner|start|erledig|hak|lösch|streich|ruf\w* .{0,30}an\b|"
    r"anrufen|vermerk|nimm .{0,30}auf|aufnehmen)", re.IGNORECASE)
WERKZEUG_PFLICHT = (
    "Regel ohne Ausnahme: Sollst du etwas speichern, anlegen, eintragen, senden, buchen, "
    "starten oder nachschlagen, rufst du dafür das passende Werkzeug auf. Behaupte nie, "
    "etwas getan zu haben, ohne dass ein Werkzeug es getan hat. Ist der Auftrag klar, "
    "handle sofort ohne Rückfrage. Antworte in höchstens zwei Sätzen.")
_PAUSE = {}  # Modellname -> Zeitpunkt (monotonic), bis zu dem es pausiert wird
_FEHLSCHLAEGE = {}  # Modellname -> wie oft hintereinander "Kontingent leer"

# Frühere Voreinstellungen, die schon in .env-Dateien stehen: Sie hatten die
# langsamen Modelle vorn. Sie werden beim Lesen auf die schnelle Reihenfolge
# umgestellt - niemand muss dafür etwas neu eintragen.
ALTE_VORGABEN = {
    "gemini-flash-latest": "gemini-flash-lite-latest,gemini-3.5-flash-lite,gemini-3.1-flash-lite,gemini-flash-latest,gemini-3.8-flash",
    "gemini-flash-latest,gemini-flash-lite-latest,gemini-3.8-flash,gemini-3.5-flash,gemini-3.1-flash-lite": "gemini-flash-lite-latest,gemini-3.5-flash-lite,gemini-3.1-flash-lite,gemini-flash-latest,gemini-3.8-flash",
}


def modelle_liste(text: str) -> list:
    """Die Modellnamen aus dem Eintrag, durch Komma getrennt."""
    text = ALTE_VORGABEN.get((text or "").replace(" ", ""), text)
    return [m.strip() for m in (text or "").split(",") if m.strip()]


def freier_dienst_aktiv() -> bool:
    """Ist ein kostenloser Online-Dienst eingestellt?"""
    return bool(FREIER_DIENST_URL and FREIER_DIENST_SCHLUESSEL
                and FREIER_DIENST_MODELL)


def _text_aus_freier_dienst(inhalt) -> str:
    if isinstance(inhalt, str):
        return inhalt
    return "\n".join(b.get("text", "") for b in inhalt or []
                     if isinstance(b, dict) and b.get("type") == "text")


def nachrichten_umwandeln_freier_dienst(system: str, nachrichten: list) -> list:
    """Claude-Nachrichten in das Format der OpenAI-kompatiblen Schnittstelle."""
    ergebnis = []
    if system:
        ergebnis.append({"role": "system", "content": system})
    for nachricht in nachrichten:
        rolle, inhalt = nachricht.get("role"), nachricht.get("content")
        if rolle == "assistant":
            aufrufe = []
            for block in inhalt if isinstance(inhalt, list) else []:
                if isinstance(block, dict) and block.get("type") == "tool_use":
                    aufruf = {"id": block.get("id"), "type": "function",
                              "function": {"name": block.get("name", ""),
                                           "arguments": json.dumps(
                                               block.get("input") or {},
                                               ensure_ascii=False)}}
                    # Gemini 3 verlangt seine "Gedanken-Signatur" unverändert zurück,
                    # sonst lehnt es den nächsten Schritt mit 400 ab.
                    if block.get("extra_content"):
                        aufruf["extra_content"] = block["extra_content"]
                    aufrufe.append(aufruf)
            eintrag = {"role": "assistant", "content": _text_aus_freier_dienst(inhalt) or None}
            if aufrufe:
                eintrag["tool_calls"] = aufrufe
            ergebnis.append(eintrag)
        elif isinstance(inhalt, list):
            bilder = []
            for block in inhalt:
                if not isinstance(block, dict):
                    continue
                if block.get("type") == "tool_result":
                    ergebnis.append({"role": "tool", "tool_call_id": block.get("tool_use_id"),
                                     "content": _text_aus_freier_dienst(block.get("content"))
                                     if not isinstance(block.get("content"), str)
                                     else block.get("content")})
                elif block.get("type") == "image":
                    quelle = block.get("source") or {}
                    bilder.append("data:%s;base64,%s" % (quelle.get("media_type", "image/jpeg"),
                                                         quelle.get("data", "")))
            text = _text_aus_freier_dienst(inhalt)
            if bilder:
                teile = [{"type": "text", "text": text or "Was siehst du?"}]
                teile += [{"type": "image_url", "image_url": {"url": b}} for b in bilder]
                ergebnis.append({"role": "user", "content": teile})
            elif text:
                ergebnis.append({"role": "user", "content": text})
        else:
            ergebnis.append({"role": "user", "content": inhalt or ""})
    return ergebnis


def antwort_umwandeln_freier_dienst(daten: dict) -> list:
    """Die Antwort als Inhaltsblöcke im Claude-Format."""
    wahl = (daten.get("choices") or [{}])[0]
    nachricht = wahl.get("message") or {}
    bloecke = []
    text = (nachricht.get("content") or "").strip()
    if text:
        bloecke.append({"type": "text", "text": text})
    for nr, aufruf in enumerate(nachricht.get("tool_calls") or []):
        funktion = aufruf.get("function") or {}
        argumente = funktion.get("arguments") or {}
        if isinstance(argumente, str):
            try:
                argumente = json.loads(argumente) if argumente.strip() else {}
            except ValueError:
                argumente = {}
        if not isinstance(argumente, dict):
            argumente = {}
        block = {"type": "tool_use", "id": aufruf.get("id") or "dienst_%d" % nr,
                 "name": funktion.get("name", ""), "input": argumente}
        if aufruf.get("extra_content"):
            block["extra_content"] = aufruf["extra_content"]
        bloecke.append(block)
    return bloecke


def _senden(url: str, schluessel: str, nutzlast: dict, timeout: int) -> dict:
    anfrage = urllib.request.Request(
        url.rstrip("/") + "/chat/completions", data=json.dumps(nutzlast).encode("utf-8"),
        method="POST", headers={
            "Authorization": "Bearer %s" % schluessel,
            "Content-Type": "application/json",
            # Manche Anbieter sperren die Standardkennung von Python.
            "User-Agent": "Jarvis/1.0"})
    try:
        with urllib.request.urlopen(anfrage, timeout=timeout) as antwort:
            return {"ok": True, "daten": json.loads(antwort.read().decode("utf-8"))}
    except urllib.error.HTTPError as fehler:
        try:
            roh = json.loads(fehler.read().decode("utf-8"))
            if isinstance(roh, list) and roh:  # Google schickt den Fehler als Liste
                roh = roh[0]
            meldung = roh.get("error", roh)
            meldung = meldung.get("message", str(meldung)) if isinstance(meldung, dict) \
                else str(meldung)
        except (ValueError, OSError, AttributeError):
            meldung = str(fehler)
        if fehler.code in (401, 403):
            return {"ok": False, "code": fehler.code,
                    "fehler": "Der Dienst lehnt den Schlüssel ab. Bitte neu kopieren "
                              "oder einen neuen holen."}
        if fehler.code == 429:
            return {"ok": False, "code": 429,
                    "fehler": "Das kostenlose Kontingent ist gerade aufgebraucht. "
                              "Bitte in einer Minute noch einmal, oder morgen, wenn es "
                              "das Tageslimit war."}
        if fehler.code == 404:
            return {"ok": False, "code": 404,
                    "fehler": "Das Modell %s kennt der Dienst nicht (mehr). Trage im "
                              "Fenster ein anderes ein." % nutzlast.get("model")}
        return {"ok": False, "code": fehler.code,
                "fehler": "Der Dienst meldet einen Fehler (%d): %s"
                          % (fehler.code, meldung[:300]), "meldung": meldung}
    except (urllib.error.URLError, OSError) as fehler:
        return {"ok": False, "code": 0,
                "fehler": "Keine Verbindung zum Dienst: %s. Ist das Internet da?" % fehler}
    except ValueError as fehler:
        return {"ok": False, "code": 0, "fehler": "Die Antwort war unlesbar: %s" % fehler}


def freier_dienst_pruefen(url: str, schluessel: str, modell: str) -> dict:
    """Probelauf mit einem winzigen Auftrag.

    Ein 429 ("Kontingent aufgebraucht") heißt: der Schlüssel wurde erkannt. Das
    zählt als gültig - sonst bliebe ein richtiger Schlüssel ungespeichert, nur
    weil das Gratis-Kontingent gerade leer ist.
    """
    erstes = (modelle_liste(modell) or [""])[0]
    antwort = _senden(url, schluessel, {
        "model": erstes, "max_tokens": 8,
        "messages": [{"role": "user", "content": "Sag nur: ok"}]}, 60)
    if antwort["ok"]:
        return {"ok": True, "text": "Der Dienst antwortet. Jarvis nutzt ihn."}
    if antwort.get("code") == 429:
        return {"ok": True, "kontingent": True,
                "text": "Der Schlüssel ist gültig. Das Gratis-Kontingent ist gerade "
                        "aufgebraucht; Jarvis antwortet wieder, sobald es sich "
                        "zurücksetzt."}
    return {"ok": False, "text": antwort["fehler"]}


def _behauptung_pruefen(bloecke: list, nutzlast: dict, timeout: int) -> list:
    """Behauptet das Modell eine Tat ohne Werkzeugaufruf, muss es nachbessern.

    Nur in der ersten Runde einer Frage (vorher kein Werkzeugergebnis) und nur
    einmal - eine zweite Nachfrage würde die Antwort spürbar verzögern.
    """
    if "tools" not in nutzlast or any(b.get("type") == "tool_use" for b in bloecke):
        return bloecke
    letzte_frage = max((i for i, m in enumerate(nutzlast["messages"])
                        if m.get("role") == "user"), default=-1)
    if any(m.get("role") == "tool" for m in nutzlast["messages"][letzte_frage + 1:]):
        return bloecke  # in dieser Runde hat schon ein Werkzeug gearbeitet
    text = " ".join(b.get("text", "") for b in bloecke if b.get("type") == "text")
    if not BEHAUPTUNG.search(text):
        return bloecke
    frage = nutzlast["messages"][letzte_frage] if letzte_frage >= 0 else {}
    inhalt = frage.get("content")
    if isinstance(inhalt, list):  # mit Bild: Es wird beschrieben, nicht gehandelt
        return bloecke
    if not AUFTRAG.search(str(inhalt or "")):
        return bloecke
    nachfrage = dict(nutzlast)
    nachfrage["messages"] = nutzlast["messages"] + [
        {"role": "assistant", "content": text},
        {"role": "user", "content": "Du hast dafür kein Werkzeug aufgerufen, also ist nichts "
                                    "passiert. Ruf jetzt das passende Werkzeug auf."}]
    zweite = _senden(FREIER_DIENST_URL, FREIER_DIENST_SCHLUESSEL,
                     nachfrage, timeout)
    if zweite["ok"]:
        neu = antwort_umwandeln_freier_dienst(zweite["daten"])
        if any(b.get("type") == "tool_use" for b in neu):
            return neu
    # Kein Werkzeug auch beim zweiten Mal: dann wenigstens nicht lügen.
    return [{"type": "text", "text": "Das habe ich noch nicht erledigt - sag es mir bitte "
                                     "noch einmal etwas genauer."}]


def freier_dienst_anfragen(koerper: dict, timeout: int = 45) -> dict:
    """Beantwortet eine Anfrage im Claude-Format über den kostenlosen Dienst."""
    nachrichten = koerper.get("messages") or []
    katalog = koerper.get("tools") or []
    letzte = ""
    for nachricht in reversed(nachrichten):
        if nachricht.get("role") == "user" and _text_aus_freier_dienst(nachricht.get("content")):
            letzte = _text_aus_freier_dienst(nachricht.get("content"))
            break
    benutzt = tuple(b.get("name", "") for n in nachrichten
                    if isinstance(n.get("content"), list) for b in n["content"]
                    if isinstance(b, dict) and b.get("type") == "tool_use")
    gewaehlt = werkzeuge_auswaehlen(katalog, letzte, DIENST_WERKZEUGE, benutzt) \
        if katalog else []
    nutzlast = {
        "model": FREIER_DIENST_MODELL,
        "messages": nachrichten_umwandeln_freier_dienst(koerper.get("system", ""), nachrichten),
        # Denkende Modelle verbrauchen einen Teil davon für Gedanken - zu wenig
        # Platz ergibt eine leere Antwort.
        "max_tokens": max(int(koerper.get("max_tokens") or 1000), 4096),
        "temperature": 0.3,
    }
    if gewaehlt:
        nutzlast["messages"].append({"role": "system", "content": WERKZEUG_PFLICHT})
        nutzlast["tools"] = [{"type": "function", "function": {
            "name": w["name"], "description": w.get("description", ""),
            "parameters": w.get("input_schema") or {"type": "object", "properties": {}}}}
            for w in gewaehlt]
    modelle = modelle_liste(FREIER_DIENST_MODELL)
    jetzt = time.monotonic()
    frei = [m for m in modelle if _PAUSE.get(m, 0) <= jetzt]
    letzte = {"ok": False, "fehler": "Der Dienst hat nicht geantwortet.", "code": 0}
    alle_voll = True
    for modell in frei or modelle:  # sind alle pausiert, trotzdem alle versuchen
        nutzlast["model"] = modell
        mit_werkzeugen = "tools" in nutzlast
        antwort = _senden(FREIER_DIENST_URL, FREIER_DIENST_SCHLUESSEL,
                          nutzlast, timeout)
        if not antwort["ok"] and antwort.get("code") == 400 and mit_werkzeugen:
            ohne = dict(nutzlast)
            ohne.pop("tools")  # Modell kann keine Werkzeuge: dann ohne
            antwort = _senden(FREIER_DIENST_URL, FREIER_DIENST_SCHLUESSEL,
                              ohne, timeout)
        if antwort["ok"]:
            _FEHLSCHLAEGE.pop(modell, None)
            bloecke = antwort_umwandeln_freier_dienst(antwort["daten"]) or [{"type": "text", "text": ""}]
            bloecke = _behauptung_pruefen(bloecke, nutzlast, timeout)
            return {"ok": True, "daten": {"content": bloecke}}
        letzte = antwort
        code = antwort.get("code")
        if code == 429:
            # Erst eine Minute (Minutenlimit), wiederholt länger (Tageslimit) -
            # sonst kostet ein leeres Modell bei jeder Frage einen Umweg.
            _FEHLSCHLAEGE[modell] = _FEHLSCHLAEGE.get(modell, 0) + 1
            _PAUSE[modell] = time.monotonic() + min(60 * 4 ** (_FEHLSCHLAEGE[modell] - 1), 3600)
            print("[dienst] %s ist gerade ausgelastet, nehme das nächste" % modell)
            continue
        alle_voll = False
        if code == 404:
            _PAUSE[modell] = time.monotonic() + 3600
            print("[dienst] %s gibt es nicht mehr, nehme das nächste" % modell)
            continue
        if code in (500, 502, 503, 504):
            _PAUSE[modell] = time.monotonic() + 30
            continue
        break  # Schlüssel abgelehnt, kaputte Anfrage, kein Netz: ein anderes Modell hilft nicht
    if letzte.get("code") == 429 and alle_voll:
        return {"ok": False, "fehler": "Das Gratis-Kontingent ist bei allen eingetragenen "
                "Modellen gerade aufgebraucht. Es setzt sich nach einer Minute (Minutenlimit) "
                "oder über Nacht (Tageslimit) zurück."}
    return {"ok": False, "fehler": letzte["fehler"]}


# =========================================================================
# voice  -  Sprache - Mikrofon rein, Stimme raus.
# 
# Beides ist mehrstufig aufgebaut, damit **ein einziger Schlüssel** genügt:
# 
#     Stimme raus:  ElevenLabs (falls Schlüssel) -> macOS ``say`` (immer da, gratis)
#     Sprache rein: faster-whisper lokal (gratis) -> Whisper-API (falls Schlüssel)
# 
# Aufgenommen wird bis zur Sprechpause, nicht in festen Blöcken. Feste Blöcke
# schneiden entweder mitten im Satz ab oder lassen den Nutzer nach dem letzten
# Wort warten - beides fällt im Alltag sofort unangenehm auf.
# =========================================================================

#!/usr/bin/env python3
# -*- coding: utf-8 -*-







def _whisper_klasse():
    """Lädt faster-whisper erst, wenn die lokale Spracherkennung gebraucht wird.

    Das Paket zieht beim ersten Import einen großen Rattenschwanz nach (av,
    ffmpeg-Bibliotheken); auf dem Mac prüft das System jede dieser Dateien
    einmal, das dauert Minuten. Die Web-App erkennt Sprache im Browser und
    braucht das alles nicht - sie soll deshalb nicht daran hängen.
    """
    try:
        from faster_whisper import WhisperModel
        return WhisperModel
    except Exception:
        return None


def whisper_vorhanden() -> bool:
    """Ist faster-whisper installiert? Prüft nur, lädt aber nichts."""
    import importlib.util
    try:
        return importlib.util.find_spec("faster_whisper") is not None
    except (ImportError, ValueError):
        return False

# Die Spracherkennung schreibt den Namen selten korrekt. Alle diese Formen
# werden als Weckwort akzeptiert.
WECKWOERTER = ["hey jarvis", "hey javis", "hey dscharvis", "hey charvis",
               "hey travis", "hey jervis", "hey dscharvis", "jarvis", "javis"]

# Bevorzugte deutsche Systemstimmen, in dieser Reihenfolge.
WUNSCHSTIMMEN = ["Markus", "Yannick", "Petra", "Anna", "Viktor"]

# Kurze Signaltöne - der Nutzer hört so, in welchem Zustand Jarvis ist.
SIGNALTOENE = {
    "zuhoeren": "/System/Library/Sounds/Tink.aiff",
    "verstanden": "/System/Library/Sounds/Pop.aiff",
    "fehler": "/System/Library/Sounds/Basso.aiff",
}

# Aufnahmeparameter
ABTASTRATE = 16000
BLOCK_SEKUNDEN = 0.1
STILLE_BIS_ENDE = 1.2
MAX_AUFNAHME = 25.0
MIN_AUFNAHME = 0.4
PEGEL_UNTERGRENZE = 0.004
PEGEL_FAKTOR = 3.5

ELEVENLABS_URL = "https://api.elevenlabs.io/v1"
WHISPER_URL = "https://api.openai.com/v1/audio/transcriptions"


def mikrofon_fehlermeldung() -> str:
    """Sagt genau, was fuer die Aufnahme fehlt - Paket oder Tonbibliothek.

    ``sounddevice`` laesst sich zwar installieren, wirft beim Import aber
    ``OSError``, wenn die Bibliothek PortAudio fehlt. Wer dann liest, das
    Paket fehle, installiert es ein zweites Mal und wundert sich. Deshalb
    wird nachgesehen, ob das Paket da ist, und nur der wirklich fehlende
    Teil genannt.
    """
    if np is None:
        return "Es fehlt das Paket numpy."
    if sd is not None:
        return ""
    try:
        vorhanden = importlib.util.find_spec("sounddevice") is not None
    except (ImportError, ValueError):
        vorhanden = False
    if vorhanden:
        return ("Die Tonbibliothek PortAudio fehlt. Im Terminal eingeben: "
                "brew install portaudio")
    return "Es fehlt das Paket sounddevice."


def text_fuers_sprechen(text: str) -> str:
    """Entfernt alles, was vorgelesen albern klingt: Sternchen, Striche, Überschriften."""
    if not text:
        return ""
    sauber = str(text)
    sauber = re.sub(r"```.*?```", " ", sauber, flags=re.S)
    sauber = re.sub(r"[*_`#>]+", " ", sauber)
    sauber = re.sub(r"^\s*[-•·]\s*", "", sauber, flags=re.M)
    sauber = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", sauber)
    sauber = re.sub(r"\s+", " ", sauber)
    return sauber.strip()


def weckwort_pruefen(text: str):
    """Prüft auf das Weckwort und schneidet es ab.

    Gibt ``(erkannt, restlicher_befehl)`` zurück.
    """
    if not text:
        return False, ""
    roh = str(text).strip()
    klein = re.sub(r"[^a-zä-ü0-9 ]+", " ", roh.lower())
    klein = re.sub(r"\s+", " ", klein).strip()
    for weckwort in WECKWOERTER:
        if klein == weckwort:
            return True, ""
        if klein.startswith(weckwort + " "):
            rest = klein[len(weckwort):].strip(" ,.")
            # Den Rest aus dem Originaltext holen, damit Groß- und Kleinschreibung bleibt.
            stelle = roh.lower().find(rest[:20].lower()) if rest else -1
            return True, (roh[stelle:].strip(" ,.") if stelle >= 0 else rest)
    return False, ""


class Stimme:
    """Sprachausgabe und Spracheingabe mit jeweils zwei Ebenen."""

    def __init__(self):
        self.macos_stimme = ""
        self._whisper_modell = None
        self._temp = tempfile.mkdtemp(prefix="jarvis_audio_")
        self.letzter_fehler = ""
        if self.ist_macos():
            self.macos_stimme = MACOS_STIMME or self.deutsche_stimme_suchen()

    # -- Umgebung -----------------------------------------------------------

    @staticmethod
    def ist_macos() -> bool:
        """Läuft das hier auf einem Mac?"""
        return shutil.which("say") is not None and os.uname().sysname == "Darwin"

    def deutsche_stimme_suchen(self) -> str:
        """Sucht die beste vorhandene deutsche Systemstimme."""
        try:
            ergebnis = subprocess.run(["say", "-v", "?"], capture_output=True,
                                      text=True, timeout=10, shell=False)
        except (OSError, subprocess.SubprocessError):
            return ""
        if ergebnis.returncode != 0:
            return ""
        stimmen = []
        for zeile in ergebnis.stdout.splitlines():
            teile = zeile.split()
            if len(teile) >= 2:
                stimmen.append((teile[0], teile[1]))
        vorhandene = {name for name, _ in stimmen}
        for wunsch in WUNSCHSTIMMEN:
            if wunsch in vorhandene:
                return wunsch
        for name, sprache in stimmen:
            if sprache in ("de_DE", "de_AT", "de_CH"):
                return name
        return ""

    def zustand(self) -> dict:
        """Was ist verfügbar, was fehlt - für den Selbsttest."""
        return {
            "macos_say": self.ist_macos(),
            "macos_stimme": self.macos_stimme or "keine deutsche gefunden",
            "elevenlabs": bool(ELEVENLABS_API_KEY),
            "mikrofon": sd is not None and np is not None,
            "mikrofon_grund": mikrofon_fehlermeldung(),
            "whisper_lokal": whisper_vorhanden(),
            "whisper_api": bool(OPENAI_API_KEY),
        }

    # -- Ausgabe ------------------------------------------------------------

    def sprich(self, text: str) -> bool:
        """Spricht einen Text. ElevenLabs zuerst, sonst die Systemstimme."""
        sauber = text_fuers_sprechen(text)
        if not sauber:
            return False
        print("Jarvis: %s" % sauber)
        if ELEVENLABS_API_KEY:
            if self._elevenlabs_sprechen(sauber):
                return True
        return self._systemstimme_sprechen(sauber)

    def _elevenlabs_sprechen(self, text: str) -> bool:
        """Sprachausgabe über ElevenLabs. Scheitert sie, übernimmt ``say``."""
        ziel = "%s/text-to-speech/%s" % (ELEVENLABS_URL, ELEVENLABS_VOICE_ID)
        # Die Klangwerte standen bisher fest im Code und waren die
        # Voreinstellung von ElevenLabs - damit klingt jede Stimme gleich
        # brav. Jetzt kommen sie aus der Konfiguration: ruhig, nah am
        # Original, ohne Theatralik.
        koerper = json.dumps({
            "text": text[:4000],
            "model_id": ELEVENLABS_MODEL,
            "voice_settings": {
                "stability": ELEVENLABS_STABILITY,
                "similarity_boost": ELEVENLABS_SIMILARITY,
                "style": ELEVENLABS_STYLE,
                "use_speaker_boost": True,
            },
        }).encode("utf-8")
        anfrage = urllib.request.Request(ziel, data=koerper, method="POST", headers={
            "xi-api-key": ELEVENLABS_API_KEY,
            "Content-Type": "application/json",
            "Accept": "audio/mpeg",
        })
        try:
            with urllib.request.urlopen(anfrage, timeout=45) as antwort:
                daten = antwort.read()
        except (urllib.error.URLError, OSError) as fehler:
            self.letzter_fehler = "ElevenLabs nicht erreichbar: %s" % fehler
            print("[stimme] %s - ich nehme die Systemstimme." % self.letzter_fehler)
            return False
        pfad = os.path.join(self._temp, "antwort_%d.mp3" % int(time.time() * 1000))
        try:
            with open(pfad, "wb") as datei:
                datei.write(daten)
        except OSError:
            return False
        erfolg = self.abspielen(pfad)
        try:
            os.remove(pfad)
        except OSError:
            pass
        return erfolg

    def _systemstimme_sprechen(self, text: str) -> bool:
        """Sprachausgabe über das eingebaute ``say`` von macOS."""
        if not shutil.which("say"):
            return False
        befehl = ["say", "-r", str(int(SPEECH_RATE))]
        if self.macos_stimme:
            befehl += ["-v", self.macos_stimme]
        befehl.append(text[:6000])
        try:
            subprocess.run(befehl, timeout=180, shell=False,
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return True
        except (OSError, subprocess.SubprocessError) as fehler:
            self.letzter_fehler = "Systemstimme fehlgeschlagen: %s" % fehler
            return False

    def abspielen(self, pfad: str) -> bool:
        """Spielt eine Audiodatei ab: afplay, sonst mpg123, sonst ffplay."""
        if not os.path.exists(pfad):
            return False
        varianten = [["afplay", pfad], ["mpg123", "-q", pfad],
                     ["ffplay", "-nodisp", "-autoexit", "-loglevel", "quiet", pfad]]
        for befehl in varianten:
            if not shutil.which(befehl[0]):
                continue
            try:
                ergebnis = subprocess.run(befehl, timeout=300, shell=False,
                                          stdout=subprocess.DEVNULL,
                                          stderr=subprocess.DEVNULL)
                if ergebnis.returncode == 0:
                    return True
            except (OSError, subprocess.SubprocessError):
                continue
        return False

    def signal(self, name: str):
        """Spielt einen kurzen Signalton - Zustand hörbar machen."""
        pfad = SIGNALTOENE.get(name)
        if not pfad or not os.path.exists(pfad) or not shutil.which("afplay"):
            return
        try:
            subprocess.Popen(["afplay", pfad], shell=False,
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except (OSError, subprocess.SubprocessError):
            pass

    def sprachdatei_erzeugen(self, text: str, ziel: str = "") -> str:
        """Erzeugt eine Audiodatei aus Text - für Sprachnachrichten per Telegram."""
        sauber = text_fuers_sprechen(text)
        if not sauber or not shutil.which("say"):
            return ""
        ziel = ziel or os.path.join(self._temp, "nachricht_%d.m4a" % int(time.time()))
        befehl = ["say", "-r", str(int(SPEECH_RATE)), "-o", ziel]
        if self.macos_stimme:
            befehl += ["-v", self.macos_stimme]
        befehl.append(sauber[:4000])
        try:
            subprocess.run(befehl, timeout=180, shell=False,
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except (OSError, subprocess.SubprocessError):
            return ""
        if not os.path.exists(ziel):
            return ""
        # Telegram will für Sprachnachrichten OGG/Opus.
        if shutil.which("ffmpeg"):
            ogg = os.path.splitext(ziel)[0] + ".ogg"
            try:
                subprocess.run(["ffmpeg", "-y", "-i", ziel, "-c:a", "libopus",
                                "-b:a", "32k", ogg], timeout=120, shell=False,
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                if os.path.exists(ogg):
                    return ogg
            except (OSError, subprocess.SubprocessError):
                pass
        return ziel

    # -- Aufnahme -----------------------------------------------------------

    def mikrofon_bereit(self) -> bool:
        """Ist eine Aufnahme technisch möglich?"""
        return sd is not None and np is not None

    def aufnehmen_bis_pause(self, still_signal: bool = False) -> str:
        """Nimmt auf, bis der Nutzer 1,2 Sekunden nichts mehr sagt.

        Der Raumpegel wird zu Beginn gemessen, damit ein lauter Raum nicht
        dauernd als Sprache gilt und ein leiser nicht überhört wird.
        """
        if not self.mikrofon_bereit():
            self.letzter_fehler = "Kein Mikrofonzugriff. %s" % mikrofon_fehlermeldung()
            return ""
        blockgroesse = int(ABTASTRATE * BLOCK_SEKUNDEN)
        gesammelt = []
        raumpegel_proben = []
        spricht = False
        stille_seit = 0.0
        beginn = time.time()

        try:
            strom = sd.InputStream(samplerate=ABTASTRATE, channels=1, dtype="float32",
                                   blocksize=blockgroesse)
        except Exception as fehler:
            self.letzter_fehler = ("Das Mikrofon lässt sich nicht öffnen: %s. In den "
                                   "Systemeinstellungen unter Datenschutz das Mikrofon "
                                   "für das Terminal freigeben." % fehler)
            return ""

        try:
            with strom:
                if not still_signal:
                    self.signal("zuhoeren")
                while True:
                    if time.time() - beginn > MAX_AUFNAHME + 6:
                        break
                    block, ueberlauf = strom.read(blockgroesse)
                    del ueberlauf
                    pegel = float(np.sqrt(np.mean(np.square(block))))

                    if len(raumpegel_proben) < 8:
                        raumpegel_proben.append(pegel)
                        if len(raumpegel_proben) == 8:
                            grundpegel = float(np.median(raumpegel_proben))
                            self._schwelle = max(grundpegel * PEGEL_FAKTOR,
                                                 PEGEL_UNTERGRENZE)
                        continue

                    if pegel >= self._schwelle:
                        spricht = True
                        stille_seit = 0.0
                        gesammelt.append(block.copy())
                    elif spricht:
                        stille_seit += BLOCK_SEKUNDEN
                        gesammelt.append(block.copy())
                        if stille_seit >= STILLE_BIS_ENDE:
                            break
                    if spricht and (time.time() - beginn) > MAX_AUFNAHME:
                        break
        except Exception as fehler:
            self.letzter_fehler = "Die Aufnahme ist abgebrochen: %s" % fehler
            return ""

        if not gesammelt:
            return ""
        daten = np.concatenate(gesammelt, axis=0)
        dauer = len(daten) / float(ABTASTRATE)
        if dauer < MIN_AUFNAHME:
            return ""  # Zu kurz - das war ein Geräusch, kein Satz.

        pfad = os.path.join(self._temp, "aufnahme_%d.wav" % int(time.time() * 1000))
        try:
            ganzzahlen = (np.clip(daten, -1.0, 1.0) * 32767).astype("int16")
            with wave.open(pfad, "wb") as datei:
                datei.setnchannels(1)
                datei.setsampwidth(2)
                datei.setframerate(ABTASTRATE)
                datei.writeframes(ganzzahlen.tobytes())
        except (OSError, ValueError) as fehler:
            self.letzter_fehler = "Die Aufnahme ließ sich nicht speichern: %s" % fehler
            return ""
        return pfad

    # -- Erkennung ----------------------------------------------------------

    def transkribieren(self, wav_pfad: str) -> str:
        """Wandelt eine Audiodatei in Text - lokal, sonst über die Whisper-API."""
        if not wav_pfad or not os.path.exists(wav_pfad):
            return ""
        text = self._whisper_lokal(wav_pfad)
        if text:
            return text
        return self._whisper_api(wav_pfad)

    def _whisper_lokal(self, wav_pfad: str) -> str:
        """Spracherkennung mit faster-whisper direkt auf dem Rechner (kostenlos)."""
        modell_klasse = _whisper_klasse() if self._whisper_modell is None else True
        if modell_klasse is None:
            return ""
        try:
            if self._whisper_modell is None:
                print("[stimme] Lade das Spracherkennungsmodell, das dauert einmalig ...")
                self._whisper_modell = modell_klasse(
                    WHISPER_MODELL, device="cpu", compute_type="int8")
            teile, _ = self._whisper_modell.transcribe(wav_pfad, language="de",
                                                       beam_size=1, vad_filter=True)
            return " ".join(teil.text.strip() for teil in teile).strip()
        except Exception as fehler:
            self.letzter_fehler = "Lokale Spracherkennung fehlgeschlagen: %s" % fehler
            print("[stimme] %s" % self.letzter_fehler)
            return ""

    def _whisper_api(self, wav_pfad: str) -> str:
        """Rückfallebene: Whisper über die OpenAI-Schnittstelle."""
        if not OPENAI_API_KEY:
            return ""
        grenze = "----jarvis%d" % int(time.time() * 1000)
        try:
            with open(wav_pfad, "rb") as datei:
                audio = datei.read()
        except OSError:
            return ""
        teile = []
        for name, wert in (("model", "whisper-1"), ("language", "de")):
            teile.append(("--%s\r\nContent-Disposition: form-data; name=\"%s\"\r\n\r\n%s\r\n"
                          % (grenze, name, wert)).encode("utf-8"))
        teile.append(("--%s\r\nContent-Disposition: form-data; name=\"file\"; "
                      "filename=\"audio.wav\"\r\nContent-Type: audio/wav\r\n\r\n"
                      % grenze).encode("utf-8"))
        teile.append(audio)
        teile.append(("\r\n--%s--\r\n" % grenze).encode("utf-8"))

        anfrage = urllib.request.Request(WHISPER_URL, data=b"".join(teile), method="POST",
                                         headers={
                                             "Authorization": "Bearer %s" % OPENAI_API_KEY,
                                             "Content-Type":
                                                 "multipart/form-data; boundary=%s" % grenze})
        try:
            with urllib.request.urlopen(anfrage, timeout=90) as antwort:
                return json.loads(antwort.read().decode("utf-8")).get("text", "").strip()
        except (urllib.error.URLError, OSError, ValueError) as fehler:
            self.letzter_fehler = "Whisper-API fehlgeschlagen: %s" % fehler
            return ""

    def zuhoeren(self) -> str:
        """Einmal aufnehmen und in Text wandeln."""
        pfad = self.aufnehmen_bis_pause()
        if not pfad:
            return ""
        try:
            text = self.transkribieren(pfad)
        finally:
            try:
                os.remove(pfad)
            except OSError:
                pass
        if text:
            print("Du: %s" % text)
        return text


# =========================================================================
# speaker  -  Stimmprofil - erkennt, ob gerade der Nutzer spricht.
# 
# **Ehrliche Einordnung, die auch so in der Anleitung steht:** Das unterscheidet
# Sprecher im Alltag zuverlässig, ist aber *kein* Schutz gegen eine abgespielte
# Aufnahme. Wer eine Sprachaufnahme des Nutzers besitzt, kommt hier durch.
# 
# Deshalb gilt im ganzen Programm: Die Stimme entscheidet nur, **ob Jarvis
# zuhört**. Sie gibt niemals eine Mail, eine Buchung oder eine Bildschirmaktion
# frei - dafür ist ausschließlich die ausdrückliche Freigabe zuständig.
# =========================================================================

#!/usr/bin/env python3
# -*- coding: utf-8 -*-





PROFIL_DATEI = "stimmprofil.json"
PROBEN_ANZAHL = 5

# Sätze, die der Nutzer beim Einlernen nachspricht - unterschiedlich lang und
# klanglich verschieden, das macht das Profil stabiler.
LERNSAETZE = [
    "Hey Jarvis, wie sieht mein Tag aus?",
    "Ich war heute bei einem Kunden und wir haben über den Preis gesprochen.",
    "Erfass bitte die Quittung von der Tankstelle.",
    "Was ist diese Woche noch offen bei mir?",
    "Feierabend, mach den Abendrückblick.",
]


class Sprecherprofil:
    """Legt ein Stimmprofil an und vergleicht spätere Aufnahmen damit."""

    def __init__(self, verzeichnis=None):
        self.verzeichnis = str(verzeichnis or PROFIL_VERZEICHNIS)
        self.pfad = os.path.join(self.verzeichnis, PROFIL_DATEI)
        self._encoder = None
        self.profil = self._profil_laden()

    # -- Verfügbarkeit ------------------------------------------------------

    def verfuegbar(self) -> bool:
        """Ist die Stimmerkennung technisch nutzbar?"""
        return VoiceEncoder is not None and np is not None

    def eingelernt(self) -> bool:
        """Liegt bereits ein Profil vor?"""
        return bool(self.profil)

    def zustand(self) -> dict:
        """Kurzer Überblick für den Selbsttest."""
        return {"paket_da": self.verfuegbar(), "profil_da": self.eingelernt(),
                "schwelle": STIMM_SCHWELLE, "pfad": self.pfad,
                "aktiv": bool(STIMMPRUEFUNG_AN)}

    # -- Profil laden und speichern ----------------------------------------

    def _profil_laden(self):
        """Liest ein vorhandenes Profil von der Platte."""
        try:
            if os.path.exists(self.pfad):
                with open(self.pfad, "r", encoding="utf-8") as datei:
                    daten = json.load(datei)
                vektor = daten.get("vektor")
                if vektor and np is not None:
                    return np.array(vektor, dtype="float32")
                return vektor
        except (OSError, ValueError) as fehler:
            print("[stimme] Stimmprofil nicht lesbar: %s" % fehler)
        return None

    def _profil_speichern(self, vektor) -> bool:
        """Schreibt das Profil auf die Platte."""
        try:
            os.makedirs(self.verzeichnis, exist_ok=True)
            with open(self.pfad, "w", encoding="utf-8") as datei:
                json.dump({"vektor": [float(wert) for wert in vektor],
                           "angelegt": time.strftime("%Y-%m-%d %H:%M:%S")},
                          datei)
            return True
        except (OSError, ValueError) as fehler:
            print("[stimme] Stimmprofil nicht speicherbar: %s" % fehler)
            return False

    def profil_loeschen(self) -> bool:
        """Verwirft das Stimmprofil."""
        self.profil = None
        try:
            if os.path.exists(self.pfad):
                os.remove(self.pfad)
            return True
        except OSError:
            return False

    # -- Einlernen ----------------------------------------------------------

    def _encoder_holen(self):
        """Lädt das Sprechermodell einmalig."""
        if self._encoder is None and VoiceEncoder is not None:
            self._encoder = VoiceEncoder()
        return self._encoder

    def vektor_aus_datei(self, wav_pfad: str):
        """Rechnet eine Aufnahme in einen Stimmvektor um."""
        if not self.verfuegbar() or not wav_pfad or not os.path.exists(wav_pfad):
            return None
        try:
            welle = preprocess_wav(wav_pfad)
            return self._encoder_holen().embed_utterance(welle)
        except Exception as fehler:
            print("[stimme] Aufnahme nicht auswertbar: %s" % fehler)
            return None

    def einlernen(self, stimme=None) -> dict:
        """Nimmt fünf Proben auf, mittelt die Vektoren und legt das Profil ab."""
        if not self.verfuegbar():
            return {"ok": False,
                    "fehler": "Für die Stimmerkennung fehlt das Paket resemblyzer. "
                              "Ohne sie funktioniert alles andere weiter."}
        if stimme is None:
            return {"ok": False, "fehler": "Zum Einlernen brauche ich das Mikrofon."}
        if not stimme.mikrofon_bereit():
            return {"ok": False,
                    "fehler": "Das Mikrofon ist nicht verfügbar. Bitte in den "
                              "Systemeinstellungen unter Datenschutz freigeben."}

        vektoren = []
        stimme.sprich("Ich lerne jetzt deine Stimme. Sprich mir bitte fünf Sätze nach.")
        for nummer in range(PROBEN_ANZAHL):
            satz = LERNSAETZE[nummer % len(LERNSAETZE)]
            stimme.sprich("Satz %d von %d. %s" % (nummer + 1, PROBEN_ANZAHL, satz))
            pfad = stimme.aufnehmen_bis_pause()
            if not pfad:
                stimme.sprich("Da war nichts zu hören. Ich versuche es noch einmal.")
                pfad = stimme.aufnehmen_bis_pause()
            vektor = self.vektor_aus_datei(pfad) if pfad else None
            if pfad:
                try:
                    os.remove(pfad)
                except OSError:
                    pass
            if vektor is None:
                stimme.sprich("Diese Probe war unbrauchbar, ich überspringe sie.")
                continue
            vektoren.append(vektor)

        if len(vektoren) < 3:
            return {"ok": False,
                    "fehler": "Ich habe nur %d brauchbare Proben bekommen. Bitte in "
                              "einer ruhigeren Umgebung noch einmal versuchen."
                              % len(vektoren)}

        gemittelt = np.mean(np.stack(vektoren), axis=0)
        gemittelt = gemittelt / (np.linalg.norm(gemittelt) + 1e-9)
        self.profil = gemittelt
        gespeichert = self._profil_speichern(gemittelt)
        return {"ok": gespeichert, "proben": len(vektoren),
                "text": "Stimmprofil aus %d Proben angelegt. Ab jetzt reagiere ich "
                        "bevorzugt auf deine Stimme." % len(vektoren)}

    # -- Prüfen -------------------------------------------------------------

    def aehnlichkeit(self, wav_pfad: str):
        """Kosinus-Ähnlichkeit einer Aufnahme zum Profil, oder ``None``."""
        if self.profil is None or not self.verfuegbar():
            return None
        vektor = self.vektor_aus_datei(wav_pfad)
        if vektor is None:
            return None
        try:
            a = np.asarray(vektor, dtype="float32")
            b = np.asarray(self.profil, dtype="float32")
            wert = float(np.dot(a, b) / ((np.linalg.norm(a) * np.linalg.norm(b)) + 1e-9))
            return wert
        except Exception:
            return None

    def ist_der_nutzer(self, wav_pfad: str) -> dict:
        """Entscheidet, ob die Aufnahme vom Nutzer stammt.

        Ohne Profil oder ohne Paket lautet die Antwort immer ja - die Prüfung
        darf niemand aussperren, den sie gar nicht beurteilen kann.
        """
        if not STIMMPRUEFUNG_AN or self.profil is None or not self.verfuegbar():
            return {"erkannt": True, "wert": None, "grund": "Stimmprüfung ist nicht aktiv."}
        wert = self.aehnlichkeit(wav_pfad)
        if wert is None:
            return {"erkannt": True, "wert": None,
                    "grund": "Die Aufnahme war nicht auswertbar - ich höre trotzdem zu."}
        erkannt = wert >= float(STIMM_SCHWELLE)
        return {"erkannt": erkannt, "wert": round(wert, 3),
                "grund": ("Stimme passt (%.2f)" % wert) if erkannt
                         else ("Fremde Stimme (%.2f unter Schwelle %.2f)"
                               % (wert, STIMM_SCHWELLE))}


# =========================================================================
# mail  -  E-Mail - ungelesene Nachrichten holen, vorsortieren und antworten.
# 
# Die Vorsortierung hier ist grob und arbeitet nur mit Wortlisten. Das ist
# Absicht: Sie läuft ohne Netz und ohne Kosten und schafft die Vorauswahl. Die
# feine Bewertung übernimmt Claude im Briefing, wo er den Zusammenhang kennt.
# =========================================================================

#!/usr/bin/env python3
# -*- coding: utf-8 -*-



# Grobe Wortlisten für die Vorsortierung.
WICHTIG_WOERTER = ["dringend", "frist", "mahnung", "rechnung", "angebot", "auftrag",
                   "kündigung", "kuendigung", "vertrag", "termin", "zahlung",
                   "überfällig", "ueberfaellig", "reklamation", "beschwerde",
                   "anfrage", "auftragsbestätigung", "letzte erinnerung"]
RAUSCHEN_WOERTER = ["newsletter", "unsubscribe", "abmelden", "no-reply", "noreply",
                    "werbung", "rabatt", "gewinnspiel", "webinar", "sale",
                    "black friday", "prospekt", "marketing", "digest"]


def kopf_dekodieren(roh) -> str:
    """Macht aus einem kodierten Mail-Kopf lesbaren Text."""
    if not roh:
        return ""
    try:
        teile = email.header.decode_header(roh)
    except (ValueError, TypeError):
        return str(roh)
    ergebnis = []
    for inhalt, kodierung in teile:
        if isinstance(inhalt, bytes):
            try:
                ergebnis.append(inhalt.decode(kodierung or "utf-8", errors="replace"))
            except (LookupError, UnicodeDecodeError):
                ergebnis.append(inhalt.decode("utf-8", errors="replace"))
        else:
            ergebnis.append(str(inhalt))
    return "".join(ergebnis).strip()


def klartext_aus_mail(nachricht) -> str:
    """Holt den lesbaren Text aus einer Mail, notfalls aus dem HTML-Teil."""
    if nachricht.is_multipart():
        for teil in nachricht.walk():
            if teil.get_content_type() == "text/plain" and \
                    "attachment" not in str(teil.get("Content-Disposition", "")):
                try:
                    return teil.get_payload(decode=True).decode(
                        teil.get_content_charset() or "utf-8", errors="replace")
                except (AttributeError, LookupError, UnicodeDecodeError):
                    continue
        for teil in nachricht.walk():
            if teil.get_content_type() == "text/html":
                try:
                    roh = teil.get_payload(decode=True).decode(
                        teil.get_content_charset() or "utf-8", errors="replace")
                except (AttributeError, LookupError, UnicodeDecodeError):
                    continue
                import re as _re_html
                return _re_html.sub(r"<[^>]+>", " ", roh)
    else:
        try:
            return nachricht.get_payload(decode=True).decode(
                nachricht.get_content_charset() or "utf-8", errors="replace")
        except (AttributeError, LookupError, UnicodeDecodeError):
            return str(nachricht.get_payload())
    return ""


def triage(betreff: str, absender: str, text: str) -> str:
    """Sortiert eine Mail grob in wichtig, spaeter oder rauschen ein."""
    zusammen = ("%s %s %s" % (betreff or "", absender or "", (text or "")[:800])).lower()
    for wort in RAUSCHEN_WOERTER:
        if wort in zusammen:
            return "rauschen"
    for wort in WICHTIG_WOERTER:
        if wort in zusammen:
            return "wichtig"
    return "spaeter"


class Mail:
    """Liest über IMAP und versendet über SMTP."""

    def __init__(self):
        self.letzter_fehler = ""

    # -- Verfügbarkeit ------------------------------------------------------

    def lesen_moeglich(self) -> bool:
        """Ist der Posteingang eingerichtet?"""
        return bool(IMAP_HOST and IMAP_USER and IMAP_PASSWORT)

    def senden_moeglich(self) -> bool:
        """Ist der Versand eingerichtet?"""
        return bool(SMTP_HOST and SMTP_USER and SMTP_PASSWORT)

    def zustand(self) -> dict:
        """Kurzer Überblick für den Selbsttest."""
        return {"lesen": self.lesen_moeglich(), "senden": self.senden_moeglich(),
                "imap": IMAP_HOST or "nicht gesetzt",
                "smtp": SMTP_HOST or "nicht gesetzt"}

    # -- Lesen --------------------------------------------------------------

    def ungelesene(self, limit: int = 15) -> dict:
        """Holt ungelesene Mails und sortiert sie vor - ohne sie als gelesen zu markieren."""
        if not self.lesen_moeglich():
            return {"ok": False,
                    "fehler": "Der Posteingang ist nicht eingerichtet. In der Einrichtung "
                              "IMAP-Server, Benutzer und Passwort hinterlegen."}
        verbindung = None
        try:
            kontext = ssl.create_default_context()
            verbindung = imaplib.IMAP4_SSL(IMAP_HOST, IMAP_PORT,
                                           ssl_context=kontext)
            verbindung.login(IMAP_USER, IMAP_PASSWORT)
            verbindung.select("INBOX")
            status, daten = verbindung.search(None, "UNSEEN")
            if status != "OK":
                return {"ok": False, "fehler": "Der Posteingang antwortet nicht wie erwartet."}
            nummern = daten[0].split()[-limit:] if daten and daten[0] else []
            mails = []
            for nummer in reversed(nummern):
                # BODY.PEEK lässt die Mail ungelesen - er soll sie selbst noch sehen.
                status, teil = verbindung.fetch(nummer, "(BODY.PEEK[])")
                if status != "OK" or not teil or not teil[0]:
                    continue
                nachricht = email.message_from_bytes(teil[0][1])
                betreff = kopf_dekodieren(nachricht.get("Subject"))
                absender = kopf_dekodieren(nachricht.get("From"))
                text = klartext_aus_mail(nachricht)
                mails.append({
                    "id": nummer.decode("ascii", errors="replace"),
                    "betreff": betreff or "(ohne Betreff)",
                    "absender": absender,
                    "datum": kopf_dekodieren(nachricht.get("Date")),
                    "auszug": " ".join((text or "").split())[:400],
                    "einstufung": triage(betreff, absender, text),
                })
            return {"ok": True, "anzahl": len(mails), "mails": mails,
                    "wichtig": [m for m in mails if m["einstufung"] == "wichtig"],
                    "spaeter": [m for m in mails if m["einstufung"] == "spaeter"],
                    "rauschen": [m for m in mails if m["einstufung"] == "rauschen"]}
        except (imaplib.IMAP4.error, ssl.SSLError, OSError) as fehler:
            self.letzter_fehler = str(fehler)
            return {"ok": False,
                    "fehler": "Der Posteingang ist nicht erreichbar: %s" % fehler}
        finally:
            if verbindung is not None:
                try:
                    verbindung.close()
                except (imaplib.IMAP4.error, OSError):
                    pass
                try:
                    verbindung.logout()
                except (imaplib.IMAP4.error, OSError):
                    pass

    def zusammenfassung(self, limit: int = 15) -> str:
        """Ein gesprochener Satz über den Posteingang."""
        ergebnis = self.ungelesene(limit)
        if not ergebnis.get("ok"):
            return ergebnis.get("fehler", "Der Posteingang ist nicht erreichbar.")
        if ergebnis["anzahl"] == 0:
            return "Im Posteingang ist nichts Ungelesenes."
        teile = ["%d ungelesene Mails, davon %d wichtig."
                 % (ergebnis["anzahl"], len(ergebnis["wichtig"]))]
        for mail in ergebnis["wichtig"][:4]:
            teile.append("Von %s: %s." % (mail["absender"].split("<")[0].strip(),
                                          mail["betreff"]))
        return " ".join(teile)

    # -- Senden -------------------------------------------------------------

    def senden(self, an: str, betreff: str, text: str) -> dict:
        """Verschickt eine Mail über SMTP mit STARTTLS.

        Achtung: Die Freigabe wird **nicht** hier eingeholt, sondern im
        Werkzeugkatalog, bevor diese Methode überhaupt aufgerufen wird.
        """
        if not self.senden_moeglich():
            return {"ok": False,
                    "fehler": "Der Mailversand ist nicht eingerichtet. In der Einrichtung "
                              "SMTP-Server, Benutzer und Passwort hinterlegen."}
        an = (an or "").strip()
        if "@" not in an:
            return {"ok": False, "fehler": "'%s' ist keine gültige Mailadresse." % an}

        nachricht = EmailMessage()
        nachricht["From"] = SMTP_ABSENDER or SMTP_USER
        nachricht["To"] = an
        nachricht["Subject"] = betreff or "(ohne Betreff)"
        nachricht["Date"] = email.utils.formatdate(localtime=True)
        nachricht["Message-ID"] = email.utils.make_msgid()
        nachricht.set_content(text or "")

        try:
            kontext = ssl.create_default_context()
            if int(SMTP_PORT) == 465:
                server = smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT,
                                          context=kontext, timeout=30)
            else:
                server = smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=30)
                server.starttls(context=kontext)
            with server:
                server.login(SMTP_USER, SMTP_PASSWORT)
                server.send_message(nachricht)
        except smtplib.SMTPAuthenticationError:
            return {"ok": False,
                    "fehler": "Der Mailserver lehnt Benutzer oder Passwort ab. Bei Gmail "
                              "und ähnlichen Anbietern braucht es ein App-Passwort."}
        except (smtplib.SMTPException, ssl.SSLError, OSError) as fehler:
            return {"ok": False, "fehler": "Die Mail ging nicht raus: %s" % fehler}
        return {"ok": True, "text": "Mail an %s ist raus." % an}


# =========================================================================
# calendar_mod  -  Kalender über CalDAV - Termine lesen, Konflikte erkennen, Termine anlegen.
# 
# Bewusst ohne Fremdpaket: CalDAV ist HTTP mit zwei zusätzlichen Methoden. Das
# spart eine Abhängigkeit, die sonst bei jeder Installation schiefgehen kann.
# 
# Die Konflikterkennung ist der eigentliche Nutzen: Termine nach Beginn sortieren
# und jeden mit dem Ende des vorherigen vergleichen. Überlappt etwas, sagt Jarvis
# es von sich aus - bei einem Einzelunternehmer, der selbst zu den Objekten fährt,
# ist eine Doppelbuchung ein verlorener Tag.
# =========================================================================

#!/usr/bin/env python3
# -*- coding: utf-8 -*-



CALDAV_ABFRAGE = """<?xml version="1.0" encoding="utf-8" ?>
<C:calendar-query xmlns:D="DAV:" xmlns:C="urn:ietf:params:xml:ns:caldav">
  <D:prop><D:getetag/><C:calendar-data/></D:prop>
  <C:filter>
    <C:comp-filter name="VCALENDAR">
      <C:comp-filter name="VEVENT">
        <C:time-range start="%s" end="%s"/>
      </C:comp-filter>
    </C:comp-filter>
  </C:filter>
</C:calendar-query>"""


def ics_zeit_lesen(wert: str):
    """Liest eine ICS-Zeitangabe wie ``20260826T090000Z`` oder ``20260826``."""
    if not wert:
        return None
    roh = wert.strip()
    if roh.endswith("Z"):
        roh = roh[:-1]
    for muster in ("%Y%m%dT%H%M%S", "%Y%m%d"):
        try:
            return datetime.strptime(roh, muster)
        except ValueError:
            continue
    return None


def ics_zeit_schreiben(zeitpunkt: datetime) -> str:
    """Schreibt einen Zeitpunkt im ICS-Format."""
    return zeitpunkt.strftime("%Y%m%dT%H%M%S")


def ics_entfalten(rohtext: str) -> list:
    """Setzt umgebrochene ICS-Zeilen wieder zusammen (Fortsetzung beginnt mit Leerzeichen)."""
    zeilen = []
    for zeile in (rohtext or "").replace("\r\n", "\n").split("\n"):
        if zeile[:1] in (" ", "\t") and zeilen:
            zeilen[-1] += zeile[1:]
        else:
            zeilen.append(zeile)
    return zeilen


def ics_termine_lesen(rohtext: str) -> list:
    """Zieht alle VEVENT-Blöcke aus einem ICS-Text."""
    termine = []
    aktuell = None
    for zeile in ics_entfalten(rohtext):
        blank = zeile.strip()
        if blank == "BEGIN:VEVENT":
            aktuell = {"titel": "", "ort": "", "beginn": None, "ende": None,
                       "beschreibung": "", "uid": ""}
            continue
        if blank == "END:VEVENT":
            if aktuell and aktuell["beginn"]:
                termine.append(aktuell)
            aktuell = None
            continue
        if aktuell is None or ":" not in blank:
            continue
        name, _, wert = blank.partition(":")
        schluessel = name.split(";")[0].upper()
        wert = wert.replace("\\,", ",").replace("\\n", " ").replace("\;", ";")
        if schluessel == "SUMMARY":
            aktuell["titel"] = wert
        elif schluessel == "LOCATION":
            aktuell["ort"] = wert
        elif schluessel == "DESCRIPTION":
            aktuell["beschreibung"] = wert
        elif schluessel == "UID":
            aktuell["uid"] = wert
        elif schluessel == "DTSTART":
            aktuell["beginn"] = ics_zeit_lesen(wert)
        elif schluessel == "DTEND":
            aktuell["ende"] = ics_zeit_lesen(wert)
    for termin in termine:
        if not termin["ende"]:
            termin["ende"] = termin["beginn"] + timedelta(hours=1)
    return sorted(termine, key=lambda t: t["beginn"])


def konflikte_finden(termine: list) -> list:
    """Findet Überschneidungen: nach Beginn sortieren, mit dem vorigen Ende vergleichen."""
    sortiert = sorted([t for t in termine if t.get("beginn") and t.get("ende")],
                      key=lambda t: t["beginn"])
    konflikte = []
    for index in range(1, len(sortiert)):
        vorher = sortiert[index - 1]
        jetzt = sortiert[index]
        if jetzt["beginn"] < vorher["ende"]:
            ueberlappung = (min(vorher["ende"], jetzt["ende"]) - jetzt["beginn"])
            konflikte.append({
                "erster": vorher["titel"], "zweiter": jetzt["titel"],
                "beginn": jetzt["beginn"].strftime("%d.%m. %H:%M"),
                "minuten": int(ueberlappung.total_seconds() // 60),
                "text": "%s und %s überschneiden sich am %s um %d Minuten."
                        % (vorher["titel"] or "Ein Termin", jetzt["titel"] or "ein Termin",
                           jetzt["beginn"].strftime("%d.%m. um %H:%M"),
                           int(ueberlappung.total_seconds() // 60))})
    return konflikte


class Kalender:
    """CalDAV-Zugriff: Termine lesen und anlegen."""

    def __init__(self):
        self.letzter_fehler = ""

    def verfuegbar(self) -> bool:
        """Ist ein Kalender hinterlegt?"""
        return bool(CALDAV_URL and CALDAV_USER)

    def zustand(self) -> dict:
        """Kurzer Überblick für den Selbsttest."""
        return {"eingerichtet": self.verfuegbar(),
                "url": CALDAV_URL or "nicht gesetzt"}

    def _kopfzeilen(self, zusatz: dict = None) -> dict:
        """Basic-Auth und Standardköpfe."""
        zugang = base64.b64encode(
            ("%s:%s" % (CALDAV_USER, CALDAV_PASSWORT)).encode("utf-8")
        ).decode("ascii")
        kopf = {"Authorization": "Basic %s" % zugang, "User-Agent": "Jarvis/1.0"}
        kopf.update(zusatz or {})
        return kopf

    def _anfrage(self, methode: str, url: str, koerper: str = "", zusatz: dict = None):
        """Führt eine HTTP-Anfrage mit beliebiger Methode aus (auch REPORT)."""
        anfrage = urllib.request.Request(
            url, data=(koerper or "").encode("utf-8") if koerper else None,
            method=methode, headers=self._kopfzeilen(zusatz))
        try:
            with urllib.request.urlopen(anfrage, timeout=30) as antwort:
                return antwort.status, antwort.read().decode("utf-8", errors="replace")
        except urllib.error.HTTPError as fehler:
            return fehler.code, fehler.read().decode("utf-8", errors="replace")
        except (urllib.error.URLError, OSError) as fehler:
            self.letzter_fehler = str(fehler)
            return 0, str(fehler)

    # -- Lesen --------------------------------------------------------------

    def termine(self, tage: int = 7, ab: datetime = None) -> dict:
        """Alle Termine der nächsten Tage, samt Konflikten."""
        if not self.verfuegbar():
            return {"ok": False,
                    "fehler": "Es ist kein Kalender eingerichtet. In der Einrichtung "
                              "die CalDAV-Adresse hinterlegen."}
        beginn = (ab or datetime.now()).replace(hour=0, minute=0, second=0, microsecond=0)
        ende = beginn + timedelta(days=max(1, int(tage)))
        koerper = CALDAV_ABFRAGE % (beginn.strftime("%Y%m%dT000000Z"),
                                    ende.strftime("%Y%m%dT235959Z"))
        status, inhalt = self._anfrage(
            "REPORT", CALDAV_URL, koerper,
            {"Depth": "1", "Content-Type": "application/xml; charset=utf-8"})
        if status == 0:
            return {"ok": False, "fehler": "Der Kalender ist nicht erreichbar: %s" % inhalt}
        if status == 401:
            return {"ok": False,
                    "fehler": "Der Kalender lehnt Benutzer oder Passwort ab."}
        if status >= 400:
            return {"ok": False,
                    "fehler": "Der Kalender antwortet mit Fehler %d." % status}

        termine = []
        for block in re.findall(r"BEGIN:VCALENDAR.*?END:VCALENDAR", inhalt, re.S):
            entschaerft = block.replace("&#13;", "").replace("&lt;", "<").replace("&gt;", ">")
            termine.extend(ics_termine_lesen(entschaerft))

        gesehen, eindeutig = set(), []
        for termin in sorted(termine, key=lambda t: t["beginn"]):
            schluessel = (termin["uid"], termin["beginn"])
            if schluessel in gesehen:
                continue
            gesehen.add(schluessel)
            eindeutig.append(termin)

        return {"ok": True, "anzahl": len(eindeutig),
                "termine": [self._als_text(t) for t in eindeutig],
                "konflikte": konflikte_finden(eindeutig)}

    @staticmethod
    def _als_text(termin: dict) -> dict:
        """Formt einen Termin in schlichte Textfelder um."""
        return {"titel": termin["titel"] or "(ohne Titel)",
                "ort": termin["ort"],
                "beginn": termin["beginn"].strftime("%Y-%m-%d %H:%M"),
                "ende": termin["ende"].strftime("%Y-%m-%d %H:%M"),
                "tag": termin["beginn"].strftime("%d.%m.%Y"),
                "uhrzeit": termin["beginn"].strftime("%H:%M")}

    def heute(self) -> dict:
        """Nur die heutigen Termine."""
        return self.termine(tage=1)

    def zusammenfassung(self, tage: int = 1) -> str:
        """Ein gesprochener Satz über die anstehenden Termine."""
        ergebnis = self.termine(tage)
        if not ergebnis.get("ok"):
            return ergebnis.get("fehler", "Der Kalender ist nicht erreichbar.")
        if ergebnis["anzahl"] == 0:
            return "Im Kalender steht nichts an."
        teile = []
        for termin in ergebnis["termine"][:6]:
            ort = (" in %s" % termin["ort"]) if termin["ort"] else ""
            teile.append("%s Uhr %s%s" % (termin["uhrzeit"], termin["titel"], ort))
        satz = "Anstehend: " + ", ".join(teile) + "."
        for konflikt in ergebnis["konflikte"][:2]:
            satz += " Achtung: %s" % konflikt["text"]
        return satz

    # -- Anlegen ------------------------------------------------------------

    def termin_anlegen(self, titel: str, beginn: str, dauer_minuten: int = 60,
                       ort: str = "", beschreibung: str = "") -> dict:
        """Legt einen Termin als iCal-Datei im Kalender ab.

        Die Freigabe holt der Werkzeugkatalog ein, bevor diese Methode läuft.
        """
        if not self.verfuegbar():
            return {"ok": False, "fehler": "Es ist kein Kalender eingerichtet."}
        startzeit = None
        for muster in ("%Y-%m-%d %H:%M", "%Y-%m-%dT%H:%M", "%d.%m.%Y %H:%M",
                       "%Y-%m-%d %H:%M:%S"):
            try:
                startzeit = datetime.strptime(beginn.strip(), muster)
                break
            except (ValueError, AttributeError):
                continue
        if startzeit is None:
            return {"ok": False,
                    "fehler": "Den Zeitpunkt '%s' verstehe ich nicht. Bitte im Format "
                              "2026-08-27 09:00 angeben." % beginn}
        try:
            dauer = max(5, int(dauer_minuten))
        except (TypeError, ValueError):
            dauer = 60
        endzeit = startzeit + timedelta(minutes=dauer)

        kennung = "%s@jarvis" % uuid.uuid4()
        def escape(wert):
            return str(wert or "").replace("\\", "\\\\").replace(",", "\\,") \
                                  .replace(";", "\;").replace("\n", "\\n")
        ics = "\r\n".join([
            "BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//Jarvis//DE",
            "BEGIN:VEVENT",
            "UID:%s" % kennung,
            "DTSTAMP:%sZ" % ics_zeit_schreiben(datetime.utcnow()),
            "DTSTART:%s" % ics_zeit_schreiben(startzeit),
            "DTEND:%s" % ics_zeit_schreiben(endzeit),
            "SUMMARY:%s" % escape(titel),
            "LOCATION:%s" % escape(ort),
            "DESCRIPTION:%s" % escape(beschreibung),
            "END:VEVENT", "END:VCALENDAR", ""])

        ziel = "%s/%s.ics" % (CALDAV_URL.rstrip("/"), kennung)
        status, inhalt = self._anfrage("PUT", ziel, ics,
                                       {"Content-Type": "text/calendar; charset=utf-8"})
        if status in (200, 201, 204):
            return {"ok": True, "uid": kennung,
                    "text": "Termin %s am %s um %s Uhr ist eingetragen."
                            % (titel, startzeit.strftime("%d.%m.%Y"),
                               startzeit.strftime("%H:%M"))}
        if status == 0:
            return {"ok": False, "fehler": "Der Kalender ist nicht erreichbar: %s" % inhalt}
        return {"ok": False,
                "fehler": "Der Kalender hat den Termin abgelehnt (Fehler %d)." % status}


# =========================================================================
# telegram_mod  -  Telegram - senden, empfangen und Freigaben einholen.
# 
# Der wichtigste Teil ist :meth:`Telegram.freigabe_einholen`. Dort gilt eine
# Regel ohne Ausnahme: **Timeout, Netzwerkfehler oder ausbleibende Antwort
# gelten als Ablehnung.** Nie als Zustimmung. Wer sich nicht meldet, hat nicht
# zugestimmt - sonst würde ein Ausfall der Verbindung zum Freibrief.
# =========================================================================

#!/usr/bin/env python3
# -*- coding: utf-8 -*-



TELEGRAM_BASIS = "https://api.telegram.org"

JA_WOERTER = {"ja", "j", "ok", "okay", "yes", "y", "passt", "mach", "machen",
              "los", "freigabe", "erlaubt", "einverstanden", "jo", "jup", "sicher"}
NEIN_WOERTER = {"nein", "n", "no", "stop", "stopp", "abbrechen", "abbruch",
                "nicht", "lass", "niemals", "nope"}


class Telegram:
    """Anbindung an einen Telegram-Bot. Ohne Token meldet sich alles sauber ab."""

    def __init__(self, token: str = None, chat_id: str = None):
        self.token = (token if token is not None else TELEGRAM_BOT_TOKEN) or ""
        self.chat_id = (chat_id if chat_id is not None else TELEGRAM_CHAT_ID) or ""
        self._letzte_update_id = 0

    def verfuegbar(self) -> bool:
        """Ist Telegram überhaupt eingerichtet?"""
        return bool(self.token and self.chat_id)

    # -- HTTP-Grundlage -----------------------------------------------------

    def _aufruf(self, methode: str, daten: dict = None, timeout: int = 20) -> dict:
        """Ruft eine Bot-API-Methode auf. Fehler werden als Wörterbuch gemeldet."""
        if not self.token:
            return {"ok": False, "fehler": "Kein Telegram-Token hinterlegt."}
        ziel = "%s/bot%s/%s" % (TELEGRAM_BASIS, self.token, methode)
        koerper = json.dumps(daten or {}).encode("utf-8")
        anfrage = urllib.request.Request(
            ziel, data=koerper, method="POST",
            headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(anfrage, timeout=timeout) as antwort:
                return json.loads(antwort.read().decode("utf-8"))
        except urllib.error.HTTPError as fehler:
            try:
                inhalt = json.loads(fehler.read().decode("utf-8"))
                text = inhalt.get("description", str(fehler))
            except (ValueError, OSError):
                text = str(fehler)
            return {"ok": False, "fehler": "Telegram meldet: %s" % text}
        except (urllib.error.URLError, OSError, ValueError) as fehler:
            return {"ok": False, "fehler": "Telegram nicht erreichbar: %s" % fehler}

    # -- Senden -------------------------------------------------------------

    def senden(self, text: str, chat_id: str = "") -> dict:
        """Schickt eine Textnachricht."""
        ziel_chat = chat_id or self.chat_id
        if not self.verfuegbar() and not chat_id:
            return {"ok": False, "fehler": "Telegram ist nicht eingerichtet."}
        antwort = self._aufruf("sendMessage",
                               {"chat_id": ziel_chat, "text": (text or "")[:4000]})
        if antwort.get("ok"):
            return {"ok": True, "text": "Nachricht ist raus."}
        return {"ok": False, "fehler": antwort.get("fehler", "Senden fehlgeschlagen.")}

    def datei_senden(self, pfad: str, methode: str = "sendVoice",
                     feld: str = "voice", chat_id: str = "") -> dict:
        """Schickt eine Datei (Sprachnachricht, Bild, Dokument) als multipart."""
        ziel_chat = chat_id or self.chat_id
        if not self.token or not ziel_chat:
            return {"ok": False, "fehler": "Telegram ist nicht eingerichtet."}
        if not os.path.exists(pfad):
            return {"ok": False, "fehler": "Die Datei %s gibt es nicht." % pfad}
        grenze = "----jarvis%d" % int(time.time() * 1000)
        try:
            with open(pfad, "rb") as datei:
                inhalt = datei.read()
        except OSError as fehler:
            return {"ok": False, "fehler": "Datei nicht lesbar: %s" % fehler}

        teile = []
        teile.append(("--%s\r\nContent-Disposition: form-data; name=\"chat_id\"\r\n\r\n%s\r\n"
                      % (grenze, ziel_chat)).encode("utf-8"))
        teile.append(("--%s\r\nContent-Disposition: form-data; name=\"%s\"; filename=\"%s\"\r\n"
                      "Content-Type: application/octet-stream\r\n\r\n"
                      % (grenze, feld, os.path.basename(pfad))).encode("utf-8"))
        teile.append(inhalt)
        teile.append(("\r\n--%s--\r\n" % grenze).encode("utf-8"))
        koerper = b"".join(teile)

        anfrage = urllib.request.Request(
            "%s/bot%s/%s" % (TELEGRAM_BASIS, self.token, methode), data=koerper,
            method="POST",
            headers={"Content-Type": "multipart/form-data; boundary=%s" % grenze})
        try:
            with urllib.request.urlopen(anfrage, timeout=60) as antwort:
                ergebnis = json.loads(antwort.read().decode("utf-8"))
            if ergebnis.get("ok"):
                return {"ok": True, "text": "Datei ist raus."}
            return {"ok": False, "fehler": str(ergebnis.get("description", "unbekannt"))}
        except (urllib.error.URLError, OSError, ValueError) as fehler:
            return {"ok": False, "fehler": "Senden fehlgeschlagen: %s" % fehler}

    # -- Empfangen ----------------------------------------------------------

    def nachrichten_holen(self, timeout: int = 25, ziel_verzeichnis: str = "") -> list:
        """Holt neue Nachrichten. Sprachnachrichten werden heruntergeladen."""
        if not self.verfuegbar():
            return []
        antwort = self._aufruf("getUpdates",
                               {"offset": self._letzte_update_id + 1,
                                "timeout": timeout, "allowed_updates": ["message"]},
                               timeout=timeout + 10)
        if not antwort.get("ok"):
            return []
        gesammelt = []
        for eintrag in antwort.get("result", []):
            self._letzte_update_id = max(self._letzte_update_id, eintrag.get("update_id", 0))
            nachricht = eintrag.get("message") or {}
            if not nachricht:
                continue
            chat = str((nachricht.get("chat") or {}).get("id", ""))
            if self.chat_id and chat != str(self.chat_id):
                continue  # Fremde Chats werden ignoriert.
            datensatz = {"update_id": eintrag.get("update_id"), "chat_id": chat,
                         "text": nachricht.get("text", ""), "sprachdatei": ""}
            sprache = nachricht.get("voice") or nachricht.get("audio")
            if sprache and sprache.get("file_id"):
                datensatz["sprachdatei"] = self.datei_herunterladen(
                    sprache["file_id"], ziel_verzeichnis)
            gesammelt.append(datensatz)
        return gesammelt

    def datei_herunterladen(self, file_id: str, ziel_verzeichnis: str = "") -> str:
        """Lädt eine Telegram-Datei herunter und gibt den lokalen Pfad zurück."""
        antwort = self._aufruf("getFile", {"file_id": file_id})
        if not antwort.get("ok"):
            return ""
        pfad = (antwort.get("result") or {}).get("file_path", "")
        if not pfad:
            return ""
        verzeichnis = ziel_verzeichnis or str(BASIS / "sprachnachrichten")
        try:
            os.makedirs(verzeichnis, exist_ok=True)
            ziel = os.path.join(verzeichnis, os.path.basename(pfad))
            quelle = "%s/file/bot%s/%s" % (TELEGRAM_BASIS, self.token, pfad)
            with urllib.request.urlopen(quelle, timeout=60) as antwort_datei:
                with open(ziel, "wb") as datei:
                    datei.write(antwort_datei.read())
            return ziel
        except (urllib.error.URLError, OSError) as fehler:
            print("[telegram] Download fehlgeschlagen: %s" % fehler)
            return ""

    # -- Freigaben ----------------------------------------------------------

    def freigabe_einholen(self, aktion: str, details: str = "", timeout: int = None) -> dict:
        """Fragt vor einer Aktion mit Außenwirkung nach ausdrücklicher Zustimmung.

        Rückgabe enthält ``erlaubt``. Ohne klares Ja ist ``erlaubt`` False -
        auch bei Timeout, Netzwerkfehler oder unverständlicher Antwort.
        """
        timeout = int(timeout if timeout is not None else FREIGABE_TIMEOUT)
        frage = ("Jarvis fragt um Freigabe.\n\nAktion: %s\n%s\n\n"
                 "Antworte mit JA oder NEIN. Ohne Antwort in %d Sekunden "
                 "führe ich nichts aus." % (aktion, details or "", timeout))

        if self.verfuegbar():
            ergebnis = self._freigabe_ueber_telegram(frage, timeout)
            if ergebnis is not None:
                return ergebnis
            # Telegram ausgefallen - das Terminal übernimmt, statt einfach
            # durchzuwinken.
            print("[freigabe] Telegram nicht erreichbar, ich frage im Terminal.")

        return self._freigabe_im_terminal(aktion, details, timeout)

    def _freigabe_ueber_telegram(self, frage: str, timeout: int):
        """Freigabe per Telegram. ``None`` heißt: Kanal fällt aus, bitte Terminal."""
        gesendet = self.senden(frage)
        if not gesendet.get("ok"):
            return None

        ende = time.time() + timeout
        while time.time() < ende:
            rest = max(1, min(20, int(ende - time.time())))
            antwort = self._aufruf(
                "getUpdates",
                {"offset": self._letzte_update_id + 1, "timeout": rest,
                 "allowed_updates": ["message"]},
                timeout=rest + 10)
            if not antwort.get("ok"):
                time.sleep(1)
                continue
            for eintrag in antwort.get("result", []):
                self._letzte_update_id = max(self._letzte_update_id,
                                             eintrag.get("update_id", 0))
                nachricht = eintrag.get("message") or {}
                chat = str((nachricht.get("chat") or {}).get("id", ""))
                if self.chat_id and chat != str(self.chat_id):
                    continue
                wort = (nachricht.get("text") or "").strip().lower().strip(".!? ")
                if wort in JA_WOERTER:
                    self.senden("Verstanden, ich mache es.")
                    return {"erlaubt": True, "kanal": "telegram", "grund": "Freigabe erteilt"}
                if wort in NEIN_WOERTER:
                    self.senden("Alles klar, ich lasse es.")
                    return {"erlaubt": False, "kanal": "telegram", "grund": "abgelehnt"}
                if wort:
                    self.senden("Bitte nur JA oder NEIN.")
        self.senden("Keine Antwort bekommen - ich habe nichts ausgeführt.")
        return {"erlaubt": False, "kanal": "telegram",
                "grund": "keine Antwort innerhalb von %d Sekunden" % timeout}

    def _freigabe_im_terminal(self, aktion: str, details: str, timeout: int) -> dict:
        """Rückfallebene: Nachfrage im Terminal, ebenfalls mit Zeitgrenze."""
        if not sys.stdin or not sys.stdin.isatty():
            return {"erlaubt": False, "kanal": "keiner",
                    "grund": "Kein Freigabekanal verfügbar - deshalb nicht ausgeführt."}
        print("\n--- FREIGABE NÖTIG ---")
        print("Aktion : %s" % aktion)
        if details:
            print("Details: %s" % details)
        print("Mit ja bestätigen, alles andere bricht ab (%d Sekunden Zeit)." % timeout)
        sys.stdout.write("> ")
        sys.stdout.flush()
        try:
            bereit, _, _ = select.select([sys.stdin], [], [], timeout)
        except (OSError, ValueError):
            bereit = []
        if not bereit:
            print("\nKeine Antwort - ich führe nichts aus.")
            return {"erlaubt": False, "kanal": "terminal",
                    "grund": "keine Antwort innerhalb von %d Sekunden" % timeout}
        eingabe = sys.stdin.readline().strip().lower().strip(".!? ")
        if eingabe in JA_WOERTER:
            return {"erlaubt": True, "kanal": "terminal", "grund": "Freigabe erteilt"}
        return {"erlaubt": False, "kanal": "terminal", "grund": "abgelehnt"}


# =========================================================================
# telefon  -  Telefon - anrufen und SMS schicken über Twilio.
# 
# Bewusst ohne das Paket ``twilio``: Die Schnittstelle ist gewöhnliches HTTP mit
# Basic-Auth. Ein Paket weniger, das bei der Installation schiefgehen kann.
# 
# Was hier geht und was nicht, ehrlich:
# 
# * **Anrufen und etwas ansagen** geht. Jarvis ruft eine Nummer an und spricht
#   einen Text - etwa eine Terminerinnerung an einen Kunden.
# * **Ein Gespräch führen** geht damit noch nicht. Dafür müsste Twilio den
#   Rechner von außen erreichen können, und der steht hinter dem Router. Das
#   braucht eine öffentliche Adresse; solange die fehlt, sagt das Modul das,
#   statt so zu tun.
# * **SMS** geht.
# 
# Jeder Anruf und jede SMS ist eine Wirkung nach außen und braucht deshalb eine
# Freigabe. Die holt der Werkzeugkatalog ein, bevor hier etwas passiert.
# =========================================================================

#!/usr/bin/env python3
# -*- coding: utf-8 -*-



TWILIO_BASIS = "https://api.twilio.com/2010-04-01"

SCHEMA_TELEFON = """
CREATE TABLE IF NOT EXISTS anrufe (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    richtung TEXT DEFAULT 'raus',
    nummer TEXT NOT NULL,
    art TEXT DEFAULT 'anruf',
    text TEXT DEFAULT '',
    kennung TEXT DEFAULT '',
    status TEXT DEFAULT '',
    angelegt TEXT NOT NULL
);
"""


def nummer_pruefen(nummer: str):
    """Prüft eine Telefonnummer und bringt sie in die internationale Form.

    Twilio nimmt nur E.164, also ``+43664...``. Eine Nummer mit 0 vorne wird
    sonst kommentarlos abgelehnt - deshalb wird hier übersetzt, solange die
    Landesvorwahl bekannt ist.
    """
    eingabe = str(nummer or "").strip()
    if not eingabe:
        return None, "Es fehlt die Telefonnummer."
    roh = "".join(z for z in eingabe if z.isdigit() or z == "+")
    if not roh:
        return None, ("In '%s' steckt keine einzige Ziffer - das ist keine "
                      "Telefonnummer." % eingabe[:60])
    if roh.startswith("+"):
        ziffern = roh[1:]
        if not (8 <= len(ziffern) <= 15):
            return None, "Die Nummer %s hat keine plausible Länge." % nummer
        return "+" + ziffern, ""
    if roh.startswith("00"):
        return nummer_pruefen("+" + roh[2:])
    if roh.startswith("0"):
        vorwahl = (LANDESVORWAHL or "").strip()
        if not vorwahl:
            return None, ("Die Nummer %s beginnt mit null. Ich brauche die "
                          "Landesvorwahl - trag LANDESVORWAHL in die "
                          "Einstellungen ein, zum Beispiel +43." % nummer)
        return nummer_pruefen(vorwahl + roh[1:])
    return None, ("Die Nummer %s verstehe ich nicht. Schreib sie international, "
                  "zum Beispiel +43664123456." % nummer)


class Telefon:
    """Ruft an und schickt SMS. Ohne Zugangsdaten meldet sich alles sauber ab."""

    def __init__(self, memory: Memory = None):
        self.memory = memory or Memory()
        db_schema_anlegen(SCHEMA_TELEFON, self.memory.db_pfad)

    # -- Verfügbarkeit ------------------------------------------------------

    def verfuegbar(self) -> bool:
        """Ist Twilio eingerichtet?"""
        return bool(TWILIO_SID and TWILIO_TOKEN
                    and TWILIO_NUMMER)

    def zustand(self) -> dict:
        """Kurzer Überblick für den Selbsttest."""
        return {"eingerichtet": self.verfuegbar(),
                "eigene_nummer": TWILIO_NUMMER or "nicht gesetzt",
                "gespraech_moeglich": False,
                "hinweis": "Ansagen und SMS gehen. Für ein echtes Gespräch "
                           "bräuchte Twilio eine öffentliche Adresse zu diesem "
                           "Rechner."}

    # -- Schnittstelle ------------------------------------------------------

    def _aufruf(self, pfad: str, felder: dict) -> dict:
        """Ruft die Twilio-Schnittstelle auf."""
        if not self.verfuegbar():
            return {"ok": False,
                    "fehler": "Das Telefon ist nicht eingerichtet. In den "
                              "Einstellungen TWILIO_SID, TWILIO_TOKEN und "
                              "TWILIO_NUMMER eintragen."}
        ziel = "%s/Accounts/%s/%s" % (TWILIO_BASIS, TWILIO_SID, pfad)
        zugang = b64encode(("%s:%s" % (TWILIO_SID, TWILIO_TOKEN))
                           .encode("utf-8")).decode("ascii")
        anfrage = urllib.request.Request(
            ziel, data=urllib.parse.urlencode(felder).encode("utf-8"),
            method="POST",
            headers={"Authorization": "Basic %s" % zugang,
                     "Content-Type": "application/x-www-form-urlencoded"})
        try:
            with urllib.request.urlopen(anfrage, timeout=30) as antwort:
                return {"ok": True, "daten": json.loads(antwort.read().decode("utf-8"))}
        except urllib.error.HTTPError as fehler:
            try:
                inhalt = json.loads(fehler.read().decode("utf-8"))
                meldung = inhalt.get("message", str(fehler))
                code = inhalt.get("code")
            except (ValueError, OSError):
                meldung, code = str(fehler), None
            if fehler.code == 401:
                return {"ok": False,
                        "fehler": "Twilio lehnt die Zugangsdaten ab. Bitte SID und "
                                  "Token neu kopieren."}
            if code == 21608:
                return {"ok": False,
                        "fehler": "Dein Twilio-Konto ist noch ein Testkonto. Es darf "
                                  "nur an Nummern anrufen, die du dort bestätigt hast."}
            if code == 21211:
                return {"ok": False,
                        "fehler": "Twilio hält die Nummer für ungültig."}
            return {"ok": False, "fehler": "Twilio meldet: %s" % meldung[:200]}
        except (urllib.error.URLError, OSError, ValueError) as fehler:
            return {"ok": False, "fehler": "Twilio ist nicht erreichbar: %s" % fehler}

    # -- Anrufen ------------------------------------------------------------

    def anrufen(self, nummer: str, ansage: str) -> dict:
        """Ruft eine Nummer an und sagt einen Text an.

        Die Freigabe holt der Werkzeugkatalog ein, bevor diese Methode läuft.
        """
        ansage = (ansage or "").strip()
        if not ansage:
            return {"ok": False, "fehler": "Was soll ich am Telefon sagen?"}
        ziel, fehler = nummer_pruefen(nummer)
        if ziel is None:
            return {"ok": False, "fehler": fehler}

        # Der Text wird als XML übergeben - er muss maskiert werden, sonst
        # zerlegt ein Kundenname mit Ampersand die ganze Ansage.
        sicher = xml.sax.saxutils.escape(ansage[:1500])
        twiml = ('<?xml version="1.0" encoding="UTF-8"?><Response>'
                 '<Pause length="1"/>'
                 '<Say language="de-DE" voice="Polly.Vicki">%s</Say>'
                 '<Pause length="1"/>'
                 '<Say language="de-DE" voice="Polly.Vicki">%s</Say>'
                 '</Response>' % (sicher, sicher))

        ergebnis = self._aufruf("Calls.json", {
            "To": ziel, "From": TWILIO_NUMMER, "Twiml": twiml})
        if not ergebnis.get("ok"):
            self._merken("raus", ziel, "anruf", ansage, "", "fehlgeschlagen")
            return ergebnis

        kennung = (ergebnis["daten"] or {}).get("sid", "")
        self._merken("raus", ziel, "anruf", ansage, kennung,
                     (ergebnis["daten"] or {}).get("status", "gestartet"))
        return {"ok": True, "nummer": ziel, "kennung": kennung,
                "text": "Ich rufe %s an und sage die Nachricht zweimal an." % ziel}

    def sms_senden(self, nummer: str, text: str) -> dict:
        """Schickt eine SMS."""
        text = (text or "").strip()
        if not text:
            return {"ok": False, "fehler": "Die SMS ist leer."}
        ziel, fehler = nummer_pruefen(nummer)
        if ziel is None:
            return {"ok": False, "fehler": fehler}

        ergebnis = self._aufruf("Messages.json", {
            "To": ziel, "From": TWILIO_NUMMER, "Body": text[:1500]})
        if not ergebnis.get("ok"):
            self._merken("raus", ziel, "sms", text, "", "fehlgeschlagen")
            return ergebnis
        kennung = (ergebnis["daten"] or {}).get("sid", "")
        self._merken("raus", ziel, "sms", text, kennung, "gesendet")
        return {"ok": True, "nummer": ziel, "kennung": kennung,
                "text": "SMS an %s ist raus." % ziel}

    def anrufliste(self, limit: int = 20) -> dict:
        """Was zuletzt telefoniert wurde."""
        zeilen = self.memory._lesen(
            "SELECT * FROM anrufe ORDER BY id DESC LIMIT ?", (limit,))
        return {"ok": True, "anzahl": len(zeilen),
                "anrufe": [{"nummer": z["nummer"], "art": z["art"],
                            "status": z["status"], "zeit": z["angelegt"],
                            "text": (z["text"] or "")[:120]} for z in zeilen],
                "text": ("Zuletzt: %s" % ", ".join(
                    "%s an %s" % (z["art"], z["nummer"]) for z in zeilen[:4]))
                        if zeilen else "Es wurde noch nicht telefoniert."}

    def _merken(self, richtung, nummer, art, text, kennung, status):
        """Schreibt einen Anruf ins Protokoll."""
        self.memory._schreiben(
            "INSERT INTO anrufe (richtung, nummer, art, text, kennung, status, "
            "angelegt) VALUES (?,?,?,?,?,?,?)",
            (richtung, nummer, art, (text or "")[:2000], kennung, status,
             zeitstempel()))


# =========================================================================
# bookkeeping  -  Buchhaltung - Belege per Foto, Buchungen, Auswertung, Export.
# 
# Wichtig: Jarvis führt die Buchhaltung nur vor. Die fachliche Prüfung macht der
# Steuerberater. Deshalb wird lieber nachgefragt als geschätzt - ein geratener
# Betrag ist in der Buchhaltung schlimmer als gar kein Eintrag.
# =========================================================================

#!/usr/bin/env python3
# -*- coding: utf-8 -*-



SCHEMA_BUCHHALTUNG = """
CREATE TABLE IF NOT EXISTS buchungen (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    art TEXT NOT NULL,
    datum TEXT NOT NULL,
    betrag_brutto REAL NOT NULL,
    mwst_satz REAL DEFAULT 0,
    mwst_betrag REAL DEFAULT 0,
    netto REAL DEFAULT 0,
    haendler TEXT DEFAULT '',
    kategorie TEXT DEFAULT 'Sonstiges',
    zahlungsart TEXT DEFAULT '',
    positionen TEXT DEFAULT '',
    beleg_pfad TEXT DEFAULT '',
    notiz TEXT DEFAULT '',
    angelegt TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_buchungen_datum ON buchungen(datum);
"""

# Kategorien, wie sie in der Gebäudereinigung tatsächlich anfallen.
MONATSKUERZEL = ["Jan", "Feb", "Mär", "Apr", "Mai", "Jun",
                 "Jul", "Aug", "Sep", "Okt", "Nov", "Dez"]

KATEGORIEN = [
    "Reinigungsmittel", "Arbeitsmaterial", "Fahrzeug", "Kraftstoff",
    "Versicherung", "Miete", "Telefon und Internet", "Werbung", "Fortbildung",
    "Bürobedarf", "Gebühren", "Sonstiges",
]

BELEG_PROMPT = """Du liest einen Beleg für die Buchhaltung eines Gebäudereinigers.

Gib ausschließlich JSON zurück, ohne Fließtext, mit genau diesen Schlüsseln:
  haendler        Name des Geschäfts, Text
  datum           JJJJ-MM-TT
  brutto          Bruttobetrag als Zahl
  mwst_satz       Steuersatz in Prozent als Zahl (z.B. 20)
  mwst_betrag     ausgewiesener Steuerbetrag als Zahl, sonst null
  netto           Nettobetrag als Zahl, sonst null
  kategorie       eine aus: %s
  zahlungsart     bar, Karte, Überweisung oder unbekannt
  positionen      Liste von Objekten mit bezeichnung und betrag
  sicher          true nur wenn Händler, Datum und Bruttobetrag zweifelsfrei lesbar sind
  hinweis         wenn sicher false ist: was genau fehlt oder unleserlich ist

Rate nie einen Betrag. Ist etwas unleserlich, setze sicher auf false und
schreibe in hinweis, was du nicht erkennen konntest.""" % ", ".join(KATEGORIEN)


def mwst_aus_brutto(brutto: float, satz: float) -> float:
    """Rechnet die enthaltene Mehrwertsteuer aus einem Bruttobetrag heraus."""
    try:
        brutto = float(brutto)
        satz = float(satz)
    except (TypeError, ValueError):
        return 0.0
    if satz <= 0:
        return 0.0
    return round(brutto - brutto / (1.0 + satz / 100.0), 2)


def geld_bookkeeping(betrag) -> str:
    """Formatiert einen Betrag deutsch: 1.234,56 Euro."""
    try:
        betrag = float(betrag)
    except (TypeError, ValueError):
        return "0,00 Euro"
    text = "{:,.2f}".format(betrag).replace(",", "#").replace(".", ",").replace("#", ".")
    return "%s Euro" % text


class Bookkeeping:
    """Führt Einnahmen und Ausgaben, wertet aus und exportiert für den Steuerberater."""

    def __init__(self, memory: Memory = None):
        self.memory = memory or Memory()
        db_schema_anlegen(SCHEMA_BUCHHALTUNG, self.memory.db_pfad)

    # -- Buchen -------------------------------------------------------------

    def buchung_eintragen(self, art: str, datum: str, betrag: float, haendler: str = "",
                          kategorie: str = "Sonstiges", mwst_satz: float = None,
                          mwst_betrag: float = None, zahlungsart: str = "",
                          positionen=None, beleg_pfad: str = "", notiz: str = "") -> dict:
        """Trägt eine Einnahme oder Ausgabe ein und rechnet die Steuer sauber aus."""
        art = (art or "").strip().lower()
        if art not in ("einnahme", "ausgabe"):
            return {"ok": False, "fehler": "Die Art muss einnahme oder ausgabe sein."}
        try:
            brutto = round(float(betrag), 2)
        except (TypeError, ValueError):
            return {"ok": False, "fehler": "Der Betrag ist keine gültige Zahl."}
        if brutto <= 0:
            return {"ok": False, "fehler": "Der Betrag muss größer als null sein."}

        datum = (datum or heute_datum()).strip()
        try:
            datetime.strptime(datum, "%Y-%m-%d")
        except ValueError:
            return {"ok": False,
                    "fehler": "Das Datum muss im Format JJJJ-MM-TT stehen, bekommen habe ich '%s'." % datum}

        satz = STANDARD_MWST if mwst_satz is None else mwst_satz
        try:
            satz = float(satz)
        except (TypeError, ValueError):
            satz = float(STANDARD_MWST)

        if mwst_betrag is None or str(mwst_betrag).strip() == "":
            steuer = mwst_aus_brutto(brutto, satz)
        else:
            try:
                steuer = round(float(mwst_betrag), 2)
            except (TypeError, ValueError):
                steuer = mwst_aus_brutto(brutto, satz)
        netto = round(brutto - steuer, 2)

        if kategorie not in KATEGORIEN:
            kategorie = kategorie if kategorie else "Sonstiges"

        try:
            positionen_text = json.dumps(positionen or [], ensure_ascii=False)
        except (TypeError, ValueError):
            positionen_text = "[]"

        nummer = self.memory._schreiben(
            "INSERT INTO buchungen (art, datum, betrag_brutto, mwst_satz, mwst_betrag, netto, "
            "haendler, kategorie, zahlungsart, positionen, beleg_pfad, notiz, angelegt) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (art, datum, brutto, satz, steuer, netto, haendler, kategorie, zahlungsart,
             positionen_text, beleg_pfad, notiz, zeitstempel()))

        return {"ok": True, "id": nummer, "art": art, "datum": datum, "brutto": brutto,
                "mwst_satz": satz, "mwst_betrag": steuer, "netto": netto,
                "haendler": haendler, "kategorie": kategorie,
                "text": "%s über %s bei %s am %s eingetragen, davon %s Steuer."
                        % (art.capitalize(), geld_bookkeeping(brutto), haendler or "unbekannt", datum,
                           geld_bookkeeping(steuer))}

    def buchung_loeschen(self, nummer: int) -> bool:
        """Löscht eine Buchung anhand ihrer Nummer."""
        if not self.memory._lesen("SELECT id FROM buchungen WHERE id=?", (nummer,)):
            return False
        self.memory._schreiben("DELETE FROM buchungen WHERE id=?", (nummer,))
        return True

    def buchungen(self, von: str = "", bis: str = "", art: str = "", limit: int = 200) -> list:
        """Listet Buchungen in einem Zeitraum."""
        bedingungen, werte = [], []
        if von:
            bedingungen.append("datum>=?")
            werte.append(von)
        if bis:
            bedingungen.append("datum<=?")
            werte.append(bis)
        if art:
            bedingungen.append("art=?")
            werte.append(art)
        wo = ("WHERE " + " AND ".join(bedingungen)) if bedingungen else ""
        werte.append(limit)
        return self.memory._lesen(
            "SELECT * FROM buchungen %s ORDER BY datum DESC, id DESC LIMIT ?" % wo, tuple(werte))

    # -- Beleg per Foto -----------------------------------------------------

    def beleg_erfassen(self, bildpfad: str, agent=None) -> dict:
        """Liest einen Beleg vom Foto und trägt ihn ein - aber nur, wenn er sicher ist."""
        if not bildpfad or not os.path.exists(bildpfad):
            return {"ok": False,
                    "fehler": "Ich finde die Bilddatei nicht: %s" % bildpfad}
        if agent is None or not getattr(agent, "einsatzbereit", lambda: False)():
            return {"ok": False,
                    "fehler": "Ohne eingerichtetes Gehirn kann ich keinen Beleg lesen. "
                              "Bitte zuerst die Einrichtung durchlaufen."}
        try:
            with open(bildpfad, "rb") as datei:
                rohbild = base64.b64encode(datei.read()).decode("ascii")
        except OSError as fehler:
            return {"ok": False, "fehler": "Die Bilddatei ist nicht lesbar: %s" % fehler}

        endung = os.path.splitext(bildpfad)[1].lower()
        medientyp = {".png": "image/png", ".gif": "image/gif",
                     ".webp": "image/webp"}.get(endung, "image/jpeg")

        antwort = agent.json_anfrage(BELEG_PROMPT, bild_base64=rohbild, bild_typ=medientyp)
        if not antwort.get("ok"):
            return {"ok": False, "fehler": antwort.get("fehler", "Der Beleg war nicht lesbar.")}

        daten = antwort["daten"]
        if not daten.get("sicher"):
            hinweis = daten.get("hinweis") or "Ich konnte den Beleg nicht zweifelsfrei lesen."
            return {"ok": False, "eingetragen": False, "sicher": False, "hinweis": hinweis,
                    "rohdaten": daten,
                    "text": "Ich trage nichts ein. %s Sag mir die fehlenden Angaben, "
                            "dann buche ich es." % hinweis}

        ergebnis = self.buchung_eintragen(
            art="ausgabe",
            datum=str(daten.get("datum") or heute_datum()),
            betrag=daten.get("brutto"),
            haendler=str(daten.get("haendler") or ""),
            kategorie=str(daten.get("kategorie") or "Sonstiges"),
            mwst_satz=daten.get("mwst_satz"),
            mwst_betrag=daten.get("mwst_betrag"),
            zahlungsart=str(daten.get("zahlungsart") or ""),
            positionen=daten.get("positionen"),
            beleg_pfad=bildpfad)
        ergebnis["sicher"] = True
        return ergebnis

    # -- Auswertung ---------------------------------------------------------

    def auswertung(self, von: str = "", bis: str = "") -> dict:
        """Einnahmen, Ausgaben, Ergebnis, Vorsteuer, Umsatzsteuer und Zahllast."""
        if not von and not bis:
            von = datetime.now().strftime("%Y-%m-01")
            bis = heute_datum()
        zeilen = self.buchungen(von, bis, limit=100000)

        einnahmen = sum(z["betrag_brutto"] for z in zeilen if z["art"] == "einnahme")
        ausgaben = sum(z["betrag_brutto"] for z in zeilen if z["art"] == "ausgabe")
        umsatzsteuer = sum(z["mwst_betrag"] for z in zeilen if z["art"] == "einnahme")
        vorsteuer = sum(z["mwst_betrag"] for z in zeilen if z["art"] == "ausgabe")

        nach_kategorie = {}
        for zeile in zeilen:
            if zeile["art"] != "ausgabe":
                continue
            nach_kategorie.setdefault(zeile["kategorie"], 0.0)
            nach_kategorie[zeile["kategorie"]] += zeile["betrag_brutto"]
        nach_kategorie = {k: round(v, 2) for k, v in
                          sorted(nach_kategorie.items(), key=lambda p: -p[1])}

        ergebnis = {
            "ok": True,
            "von": von, "bis": bis, "anzahl": len(zeilen),
            "einnahmen": round(einnahmen, 2),
            "ausgaben": round(ausgaben, 2),
            "ergebnis": round(einnahmen - ausgaben, 2),
            "umsatzsteuer": round(umsatzsteuer, 2),
            "vorsteuer": round(vorsteuer, 2),
            "zahllast": round(umsatzsteuer - vorsteuer, 2),
            "nach_kategorie": nach_kategorie,
        }
        ergebnis["text"] = (
            "Vom %s bis %s: Einnahmen %s, Ausgaben %s, Ergebnis %s. "
            "Umsatzsteuer %s, Vorsteuer %s, Zahllast %s."
            % (von, bis, geld_bookkeeping(ergebnis["einnahmen"]), geld_bookkeeping(ergebnis["ausgaben"]),
               geld_bookkeeping(ergebnis["ergebnis"]), geld_bookkeeping(ergebnis["umsatzsteuer"]),
               geld_bookkeeping(ergebnis["vorsteuer"]), geld_bookkeeping(ergebnis["zahllast"])))
        return ergebnis

    def fehlende_belege(self, von: str = "", bis: str = "") -> dict:
        """Ausgaben ohne hinterlegtes Belegfoto - genau die fehlen beim Steuerberater."""
        zeilen = self.buchungen(von, bis, art="ausgabe", limit=100000)
        ohne = []
        for zeile in zeilen:
            pfad = (zeile["beleg_pfad"] or "").strip()
            if not pfad or not os.path.exists(pfad):
                ohne.append({"id": zeile["id"], "datum": zeile["datum"],
                             "haendler": zeile["haendler"], "betrag": zeile["betrag_brutto"],
                             "kategorie": zeile["kategorie"],
                             "grund": "kein Foto hinterlegt" if not pfad
                                      else "Datei nicht mehr vorhanden"})
        summe = round(sum(e["betrag"] for e in ohne), 2)
        if not ohne:
            text = "Zu allen Ausgaben liegt ein Beleg vor."
        else:
            text = ("%d Ausgaben ohne Beleg, zusammen %s. Die größte: %s bei %s am %s."
                    % (len(ohne), geld_bookkeeping(summe),
                       geld_bookkeeping(max(ohne, key=lambda e: e["betrag"])["betrag"]),
                       max(ohne, key=lambda e: e["betrag"])["haendler"] or "unbekannt",
                       max(ohne, key=lambda e: e["betrag"])["datum"]))
        return {"ok": True, "anzahl": len(ohne), "summe": summe, "buchungen": ohne,
                "text": text}

    def tagesverlauf(self, tage: int = 30, bis: str = "") -> dict:
        """Einnahmen und Ausgaben je Tag - die Datenreihe hinter den Sparklines.

        Tage ohne Buchung werden als null geführt, nicht ausgelassen. Sonst
        würde eine Lücke im Verlauf wie ein Anstieg aussehen.
        """
        endtag = datetime.strptime(bis, "%Y-%m-%d") if bis else datetime.now()
        starttag = endtag - timedelta(days=max(1, int(tage)) - 1)
        zeilen = self.buchungen(starttag.strftime("%Y-%m-%d"),
                                endtag.strftime("%Y-%m-%d"), limit=100000)
        einnahmen, ausgaben = {}, {}
        for zeile in zeilen:
            ziel = einnahmen if zeile["art"] == "einnahme" else ausgaben
            ziel[zeile["datum"]] = ziel.get(zeile["datum"], 0.0) + zeile["betrag_brutto"]
        tagesliste, reihe_ein, reihe_aus = [], [], []
        for versatz in range(max(1, int(tage))):
            tag = (starttag + timedelta(days=versatz)).strftime("%Y-%m-%d")
            tagesliste.append(tag)
            reihe_ein.append(round(einnahmen.get(tag, 0.0), 2))
            reihe_aus.append(round(ausgaben.get(tag, 0.0), 2))
        return {"ok": True,
                "tage": tagesliste, "einnahmen": reihe_ein, "ausgaben": reihe_aus,
                "summe_einnahmen": round(sum(reihe_ein), 2),
                "summe_ausgaben": round(sum(reihe_aus), 2)}

    def monatsverlauf(self, monate: int = 6) -> dict:
        """Ergebnis je Monat - für den Balkenvergleich."""
        jetzt = datetime.now()
        namen, werte, umsaetze = [], [], []
        for rueckwaerts in range(max(1, int(monate)) - 1, -1, -1):
            jahr = jetzt.year
            monat = jetzt.month - rueckwaerts
            while monat <= 0:
                monat += 12
                jahr -= 1
            erster = "%04d-%02d-01" % (jahr, monat)
            if monat == 12:
                letzter = "%04d-12-31" % jahr
            else:
                letzter = (datetime(jahr, monat + 1, 1) -
                           timedelta(days=1)).strftime("%Y-%m-%d")
            zeilen = self.buchungen(erster, letzter, limit=100000)
            ein = sum(z["betrag_brutto"] for z in zeilen if z["art"] == "einnahme")
            aus = sum(z["betrag_brutto"] for z in zeilen if z["art"] == "ausgabe")
            namen.append(MONATSKUERZEL[monat - 1])
            werte.append(round(ein - aus, 2))
            umsaetze.append(round(ein, 2))
        return {"ok": True, "monate": namen, "ergebnis": werte,
                "einnahmen": umsaetze}

    def belegquote(self, von: str = "", bis: str = "") -> dict:
        """Anteil der Ausgaben, zu denen ein Belegfoto vorliegt.

        Das ist die Zahl, die beim Steuerberater zählt - nicht die Anzahl der
        Buchungen, sondern wie viel Geld belegt ist.
        """
        zeilen = self.buchungen(von, bis, art="ausgabe", limit=100000)
        if not zeilen:
            return {"ok": True, "quote": None, "belegt": 0.0, "gesamt": 0.0,
                    "anzahl": 0,
                    "text": "Noch keine Ausgaben erfasst."}
        gesamt = sum(z["betrag_brutto"] for z in zeilen)
        belegt = sum(z["betrag_brutto"] for z in zeilen
                     if (z["beleg_pfad"] or "").strip()
                     and os.path.exists(z["beleg_pfad"]))
        quote = (100.0 * belegt / gesamt) if gesamt else 0.0
        return {"ok": True, "quote": round(quote, 1), "belegt": round(belegt, 2),
                "gesamt": round(gesamt, 2), "anzahl": len(zeilen),
                "text": "%.0f Prozent der Ausgaben sind belegt." % quote}

    # -- Export -------------------------------------------------------------

    def csv_export(self, von: str = "", bis: str = "", ziel: str = "") -> dict:
        """Schreibt eine CSV-Datei, die Excel auf Anhieb richtig öffnet.

        Semikolon als Trenner und ``utf-8-sig`` - sonst zerlegt Excel die Umlaute.
        """
        zeilen = self.buchungen(von, bis, limit=100000)
        try:
            EXPORT_VERZEICHNIS.mkdir(parents=True, exist_ok=True)
        except OSError:
            pass
        if not ziel:
            ziel = str(EXPORT_VERZEICHNIS /
                       ("buchhaltung_%s.csv" % datetime.now().strftime("%Y%m%d_%H%M%S")))
        kopf = ["Nummer", "Art", "Datum", "Händler", "Kategorie", "Brutto", "MwSt-Satz",
                "MwSt-Betrag", "Netto", "Zahlungsart", "Beleg vorhanden", "Notiz"]
        try:
            with open(ziel, "w", encoding="utf-8-sig", newline="") as datei:
                schreiber = csv.writer(datei, delimiter=";")
                schreiber.writerow(kopf)
                for zeile in zeilen:
                    beleg = "ja" if (zeile["beleg_pfad"] and
                                     os.path.exists(zeile["beleg_pfad"])) else "nein"
                    schreiber.writerow([
                        zeile["id"], zeile["art"], zeile["datum"], zeile["haendler"],
                        zeile["kategorie"],
                        ("%.2f" % zeile["betrag_brutto"]).replace(".", ","),
                        ("%.2f" % zeile["mwst_satz"]).replace(".", ","),
                        ("%.2f" % zeile["mwst_betrag"]).replace(".", ","),
                        ("%.2f" % zeile["netto"]).replace(".", ","),
                        zeile["zahlungsart"], beleg, zeile["notiz"]])
        except OSError as fehler:
            return {"ok": False, "fehler": "Die CSV-Datei ließ sich nicht schreiben: %s" % fehler}
        return {"ok": True, "datei": ziel, "zeilen": len(zeilen),
                "text": "%d Buchungen nach %s exportiert." % (len(zeilen), ziel)}


# =========================================================================
# call_analysis  -  Kundengespräche bewerten - ehrlich, nicht schmeichelnd.
# 
# Ein freundliches Gespräch ohne Ergebnis ist kein gutes Gespräch. Die Bewertung
# sagt das auch. Schwächen werden konkret benannt, nicht allgemein.
# =========================================================================

#!/usr/bin/env python3
# -*- coding: utf-8 -*-



SCHEMA_GESPRAECHE = """
CREATE TABLE IF NOT EXISTS gespraeche (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    kunde TEXT DEFAULT '',
    datum TEXT NOT NULL,
    punktzahl INTEGER DEFAULT 0,
    ergebnis TEXT DEFAULT 'unklar',
    volumen REAL DEFAULT 0,
    staerken TEXT DEFAULT '',
    schwaechen TEXT DEFAULT '',
    einwaende TEXT DEFAULT '',
    offene_einwaende TEXT DEFAULT '',
    naechster_schritt TEXT DEFAULT '',
    bewertung TEXT DEFAULT '',
    rohtext TEXT DEFAULT '',
    angelegt TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_gespraeche_datum ON gespraeche(datum);
"""

ERGEBNIS_WERTE = ("gewonnen", "offen", "verloren", "unklar")

GESPRAECH_PROMPT = """Du bewertest ein Kundengespräch eines Gebäudereinigers.
Sei streng. Ein nettes Gespräch ohne Abschluss oder konkreten nächsten Termin
ist kein gutes Gespräch - das sagst du dann auch deutlich.

Worauf es in dieser Branche ankommt:
- Quadratmeter, Anzahl der Räume, Bodenbeläge erfasst?
- Reinigungsintervall geklärt (täglich, zweimal die Woche, monatlich)?
- Zugang, Schlüsselübergabe, Zeitfenster besprochen?
- Sonderleistungen angesprochen (Fensterreinigung, Grundreinigung, Teppich)?
- Preisbildung nachvollziehbar begründet, pro Quadratmeter oder pro Stunde?
- Probereinigung angeboten?
- Konkreter nächster Termin mit Datum vereinbart?

Gib ausschließlich JSON zurück, ohne Fließtext, mit genau diesen Schlüsseln:
  kunde              Name des Kunden oder Objekts, Text
  punktzahl          0 bis 100, ganze Zahl
  ergebnis           gewonnen, offen, verloren oder unklar
  volumen            geschätztes Auftragsvolumen pro Jahr in Euro als Zahl, sonst 0
  staerken           Liste konkreter Sätze, was gut lief
  schwaechen         Liste konkreter Sätze. Nicht "hätte mehr fragen sollen",
                     sondern "Bodenbelag und Quadratmeter nie erfasst - ohne die
                     ist kein Preis kalkulierbar"
  einwaende          Liste der Einwände, die der Kunde gebracht hat
  offene_einwaende   Liste der Einwände, die unbeantwortet geblieben sind
  naechster_schritt  ein konkreter Satz, was jetzt zu tun ist
  bewertung          Objekt mit den Schlüsseln bedarf_erfasst, objekt_verstanden,
                     preis_begruendet, einwaende_behandelt, abschluss_gesucht -
                     jeweils eine Zahl von 0 bis 10

Das Gespräch, wie er es erzählt hat:
"""


def _liste_zu_text(wert) -> str:
    """Macht aus einer Liste oder einem Text eine Zeile mit Strichpunkten."""
    if wert is None:
        return ""
    if isinstance(wert, (list, tuple)):
        return "; ".join(str(teil).strip() for teil in wert if str(teil).strip())
    return str(wert).strip()


def _text_zu_liste(wert: str) -> list:
    """Umkehrung von :func:`_liste_zu_text`."""
    if not wert:
        return []
    return [teil.strip() for teil in str(wert).split(";") if teil.strip()]


class CallAnalysis:
    """Bewertet Kundengespräche und erkennt Muster über viele Gespräche hinweg."""

    def __init__(self, memory: Memory = None):
        self.memory = memory or Memory()
        db_schema_anlegen(SCHEMA_GESPRAECHE, self.memory.db_pfad)

    # -- Erfassen -----------------------------------------------------------

    def gespraech_festhalten(self, bericht: str, agent=None, kunde: str = "",
                             datum: str = "") -> dict:
        """Lässt Claude das Gespräch bewerten und legt es ab."""
        bericht = (bericht or "").strip()
        if not bericht:
            return {"ok": False, "fehler": "Du hast mir noch nicht erzählt, wie es lief."}
        datum = datum or heute_datum()

        if agent is None or not getattr(agent, "einsatzbereit", lambda: False)():
            # Ohne Claude wird nichts erfunden - der Bericht wird roh abgelegt.
            nummer = self._ablegen({"kunde": kunde, "datum": datum, "punktzahl": 0,
                                    "ergebnis": "unklar", "volumen": 0}, bericht, {})
            return {"ok": True, "id": nummer, "bewertet": False,
                    "text": "Ich habe das Gespräch festgehalten, konnte es ohne "
                            "Anthropic-Schlüssel aber nicht bewerten."}

        antwort = agent.json_anfrage(GESPRAECH_PROMPT + bericht)
        if not antwort.get("ok"):
            nummer = self._ablegen({"kunde": kunde, "datum": datum}, bericht, {})
            return {"ok": True, "id": nummer, "bewertet": False,
                    "text": "Festgehalten. Die Bewertung ist fehlgeschlagen: %s"
                            % antwort.get("fehler", "unbekannter Fehler")}

        daten = antwort["daten"]
        if kunde:
            daten["kunde"] = kunde
        daten["datum"] = datum
        nummer = self._ablegen(daten, bericht, daten.get("bewertung") or {})

        punkte = int(daten.get("punktzahl") or 0)
        ergebnis = str(daten.get("ergebnis") or "unklar").lower()
        if ergebnis not in ERGEBNIS_WERTE:
            ergebnis = "unklar"
        schwaechen = daten.get("schwaechen") or []
        erste_schwaeche = _liste_zu_text(schwaechen[:1]) if isinstance(schwaechen, list) \
            else _liste_zu_text(schwaechen)

        text = ("%s: %d von 100, Ergebnis %s." %
                (daten.get("kunde") or "Das Gespräch", punkte, ergebnis))
        if erste_schwaeche:
            text += " Größte Lücke: %s" % erste_schwaeche
        if daten.get("naechster_schritt"):
            text += " Nächster Schritt: %s" % daten["naechster_schritt"]

        return {"ok": True, "id": nummer, "bewertet": True, "punktzahl": punkte,
                "ergebnis": ergebnis, "daten": daten, "text": text}

    def _ablegen(self, daten: dict, rohtext: str, bewertung: dict) -> int:
        """Schreibt eine Gesprächsbewertung in die Datenbank."""
        try:
            volumen = float(daten.get("volumen") or 0)
        except (TypeError, ValueError):
            volumen = 0.0
        try:
            punktzahl = int(daten.get("punktzahl") or 0)
        except (TypeError, ValueError):
            punktzahl = 0
        ergebnis = str(daten.get("ergebnis") or "unklar").lower()
        if ergebnis not in ERGEBNIS_WERTE:
            ergebnis = "unklar"
        try:
            bewertung_text = json.dumps(bewertung or {}, ensure_ascii=False)
        except (TypeError, ValueError):
            bewertung_text = "{}"
        return self.memory._schreiben(
            "INSERT INTO gespraeche (kunde, datum, punktzahl, ergebnis, volumen, staerken, "
            "schwaechen, einwaende, offene_einwaende, naechster_schritt, bewertung, rohtext, "
            "angelegt) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (str(daten.get("kunde") or ""), str(daten.get("datum") or heute_datum()),
             punktzahl, ergebnis, volumen,
             _liste_zu_text(daten.get("staerken")),
             _liste_zu_text(daten.get("schwaechen")),
             _liste_zu_text(daten.get("einwaende")),
             _liste_zu_text(daten.get("offene_einwaende")),
             str(daten.get("naechster_schritt") or ""),
             bewertung_text, rohtext[:6000], zeitstempel()))

    # -- Auswerten ----------------------------------------------------------

    def gespraeche(self, limit: int = 50) -> list:
        """Die zuletzt festgehaltenen Gespräche."""
        return self.memory._lesen(
            "SELECT * FROM gespraeche ORDER BY datum DESC, id DESC LIMIT ?", (limit,))

    def offene_leads(self) -> dict:
        """Alle Gespräche mit Ergebnis 'offen', samt Summe des offenen Volumens."""
        zeilen = self.memory._lesen(
            "SELECT * FROM gespraeche WHERE ergebnis='offen' ORDER BY volumen DESC, datum DESC")
        summe = round(sum(z["volumen"] or 0 for z in zeilen), 2)
        leads = [{"id": z["id"], "kunde": z["kunde"], "datum": z["datum"],
                  "volumen": z["volumen"], "punktzahl": z["punktzahl"],
                  "naechster_schritt": z["naechster_schritt"]} for z in zeilen]
        if not leads:
            text = "Es ist gerade kein Lead offen."
        else:
            groesster = leads[0]
            text = ("%d offene Leads über zusammen %.0f Euro. Der größte ist %s mit "
                    "%.0f Euro. Nächster Schritt dort: %s"
                    % (len(leads), summe, groesster["kunde"] or "ein Kunde ohne Namen",
                       groesster["volumen"],
                       groesster["naechster_schritt"] or "steht noch nicht fest"))
        return {"ok": True, "anzahl": len(leads), "volumen_offen": summe,
                "leads": leads, "text": text}

    DIMENSIONEN = [("bedarf_erfasst", "Bedarf erfasst"),
                   ("objekt_verstanden", "Objekt verstanden"),
                   ("preis_begruendet", "Preis begründet"),
                   ("einwaende_behandelt", "Einwände behandelt"),
                   ("abschluss_gesucht", "Abschluss gesucht")]

    def bewertung_lesen(self, zeile) -> dict:
        """Holt die Einzelbewertung eines Gesprächs aus der Datenbank."""
        try:
            daten = json.loads(zeile["bewertung"] or "{}")
        except (ValueError, TypeError):
            return {}
        ergebnis = {}
        for schluessel, beschriftung in self.DIMENSIONEN:
            if schluessel in daten:
                try:
                    ergebnis[schluessel] = max(0.0, min(10.0, float(daten[schluessel])))
                except (TypeError, ValueError):
                    continue
        del beschriftung
        return ergebnis

    def dimensionen_schnitt(self, tage: int = 90) -> dict:
        """Durchschnitt je Bewertungsdimension - zeigt die eigene schwächste Stelle."""
        grenze = (datetime.now() - timedelta(days=tage)).strftime("%Y-%m-%d")
        zeilen = self.memory._lesen(
            "SELECT * FROM gespraeche WHERE datum>=?", (grenze,))
        gesammelt = {}
        for zeile in zeilen:
            for schluessel, wert in self.bewertung_lesen(zeile).items():
                gesammelt.setdefault(schluessel, []).append(wert)
        schnitt = []
        for schluessel, beschriftung in self.DIMENSIONEN:
            werte = gesammelt.get(schluessel) or []
            schnitt.append({"schluessel": schluessel, "name": beschriftung,
                            "wert": round(sum(werte) / len(werte), 1) if werte else None,
                            "anzahl": len(werte)})
        vorhanden = [e for e in schnitt if e["wert"] is not None]
        schwaechste = min(vorhanden, key=lambda e: e["wert"]) if vorhanden else None
        return {"dimensionen": schnitt, "schwaechste": schwaechste,
                "bewertete_gespraeche": len([z for z in zeilen
                                             if self.bewertung_lesen(z)])}

    def verkaufsmuster(self, tage: int = 90) -> dict:
        """Abschlussquote, Durchschnittspunktzahl und wiederkehrende Einwände.

        Kommt derselbe Einwand dreimal, ist das kein Zufall, sondern eine Lücke
        im Angebot.
        """
        grenze = (datetime.now() - timedelta(days=tage)).strftime("%Y-%m-%d")
        zeilen = self.memory._lesen(
            "SELECT * FROM gespraeche WHERE datum>=? ORDER BY datum", (grenze,))
        if not zeilen:
            return {"ok": True, "anzahl": 0,
                    "text": "In den letzten %d Tagen ist kein Gespräch festgehalten worden."
                            % tage}

        gewonnen = len([z for z in zeilen if z["ergebnis"] == "gewonnen"])
        verloren = len([z for z in zeilen if z["ergebnis"] == "verloren"])
        offen = len([z for z in zeilen if z["ergebnis"] == "offen"])
        entschieden = gewonnen + verloren
        quote = round(100.0 * gewonnen / entschieden, 1) if entschieden else 0.0
        schnitt = round(sum(z["punktzahl"] for z in zeilen) / float(len(zeilen)), 1)

        haeufigkeit = {}
        for zeile in zeilen:
            for einwand in _text_zu_liste(zeile["einwaende"]) + \
                           _text_zu_liste(zeile["offene_einwaende"]):
                schluessel = einwand.lower()[:80]
                haeufigkeit[schluessel] = haeufigkeit.get(schluessel, 0) + 1
        wiederkehrend = sorted([(anzahl, text) for text, anzahl in haeufigkeit.items()
                                if anzahl >= 2], reverse=True)[:6]

        schwaechen = {}
        for zeile in zeilen:
            for schwaeche in _text_zu_liste(zeile["schwaechen"]):
                schluessel = schwaeche.lower()[:80]
                schwaechen[schluessel] = schwaechen.get(schluessel, 0) + 1
        haeufige_schwaechen = sorted([(a, t) for t, a in schwaechen.items() if a >= 2],
                                     reverse=True)[:5]

        text = ("%d Gespräche in %d Tagen. Abschlussquote %.1f Prozent, "
                "Durchschnitt %.1f Punkte. %d gewonnen, %d verloren, %d offen."
                % (len(zeilen), tage, quote, schnitt, gewonnen, verloren, offen))
        if wiederkehrend:
            anzahl, einwand = wiederkehrend[0]
            text += (" Der Einwand '%s' kam %d mal - das ist kein Zufall, "
                     "sondern eine Lücke im Angebot." % (einwand, anzahl))

        return {"ok": True, "anzahl": len(zeilen), "gewonnen": gewonnen,
                "verloren": verloren, "offen": offen, "abschlussquote": quote,
                "durchschnitt": schnitt,
                "wiederkehrende_einwaende": [{"einwand": t, "anzahl": a}
                                             for a, t in wiederkehrend],
                "haeufige_schwaechen": [{"schwaeche": t, "anzahl": a}
                                        for a, t in haeufige_schwaechen],
                "text": text}


# =========================================================================
# akquise  -  Akquise - Aufträge hereinholen und den Cashflow daraus vorhersagen.
# 
# Das ist der Teil, der Geld bringt. Bewertung allein hilft nicht: Es braucht
# eine Pipeline, die weiß, wer wann wieder angerufen werden muss, eine
# Kalkulation, die aus Quadratmetern einen belastbaren Monatspreis macht, und
# eine Vorhersage, die sagt, was in drei Monaten auf dem Konto ist.
# 
# Die Kalkulation rechnet, wie in der Branche wirklich gerechnet wird: über
# Leistungswerte. Ein Reiniger schafft je nach Bodenbelag eine bestimmte Fläche
# pro Stunde. Daraus ergeben sich Stunden, daraus der Preis. Wer stattdessen
# einen Quadratmeterpreis rät, verkalkuliert sich beim ersten Sonderfall.
# =========================================================================

#!/usr/bin/env python3
# -*- coding: utf-8 -*-



SCHEMA_AKQUISE = """
CREATE TABLE IF NOT EXISTS leads (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    firma TEXT NOT NULL,
    ansprechpartner TEXT DEFAULT '',
    telefon TEXT DEFAULT '',
    email TEXT DEFAULT '',
    adresse TEXT DEFAULT '',
    quelle TEXT DEFAULT '',
    objekt_qm REAL DEFAULT 0,
    bodenbelag TEXT DEFAULT '',
    intervall_pro_woche REAL DEFAULT 0,
    sonderleistungen TEXT DEFAULT '',
    stufe TEXT DEFAULT 'neu',
    wert_monat REAL DEFAULT 0,
    naechster_schritt TEXT DEFAULT '',
    naechster_kontakt TEXT DEFAULT '',
    notiz TEXT DEFAULT '',
    angelegt TEXT NOT NULL,
    geaendert TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS angebote (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    lead_id INTEGER,
    datum TEXT NOT NULL,
    qm REAL DEFAULT 0,
    bodenbelag TEXT DEFAULT '',
    intervall_pro_woche REAL DEFAULT 0,
    stundensatz REAL DEFAULT 0,
    stunden_monat REAL DEFAULT 0,
    netto_monat REAL DEFAULT 0,
    brutto_monat REAL DEFAULT 0,
    posten TEXT DEFAULT '',
    status TEXT DEFAULT 'entwurf',
    notiz TEXT DEFAULT '',
    angelegt TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_leads_stufe ON leads(stufe);
CREATE INDEX IF NOT EXISTS idx_leads_kontakt ON leads(naechster_kontakt);
"""

# Die Stufen, die ein Interessent durchläuft. Reihenfolge ist bewusst:
# sie bestimmt auch, wie wahrscheinlich ein Abschluss ist.
STUFEN = ["neu", "kontaktiert", "besichtigt", "angebot", "nachfassen",
          "gewonnen", "verloren"]

# Erfahrungswerte, wie sicher eine Stufe zum Auftrag führt. Bewusst
# zurückhaltend: eine zu optimistische Pipeline führt zu Fehlplanung.
WAHRSCHEINLICHKEIT = {"neu": 0.10, "kontaktiert": 0.20, "besichtigt": 0.40,
                      "angebot": 0.60, "nachfassen": 0.45, "gewonnen": 1.0,
                      "verloren": 0.0}

# Wie viele Tage nach dem letzten Schritt nachgefasst werden sollte.
NACHFASS_TAGE = {"neu": 2, "kontaktiert": 3, "besichtigt": 2, "angebot": 5,
                 "nachfassen": 7}

# Leistungswerte in Quadratmetern je Stunde. So rechnet die Branche.
LEISTUNGSWERTE = {
    "teppich": 350.0,
    "hartboden": 300.0,
    "linoleum": 300.0,
    "pvc": 300.0,
    "fliesen": 280.0,
    "naturstein": 250.0,
    "beton": 250.0,
    "parkett": 260.0,
    "treppenhaus": 150.0,
    "sanitaer": 80.0,
    "sanitär": 80.0,
    "kueche": 120.0,
    "küche": 120.0,
    "halle": 500.0,
    "industrie": 500.0,
}
LEISTUNG_STANDARD = 280.0

# Sonderleistungen, die getrennt berechnet werden. Wert ist Euro je Einheit.
SONDERLEISTUNGEN = {
    "fensterreinigung": ("je Fensterflügel", 3.50),
    "grundreinigung": ("je Quadratmeter", 2.80),
    "teppichreinigung": ("je Quadratmeter", 2.20),
    "bauschlussreinigung": ("je Quadratmeter", 4.50),
}

WOCHEN_PRO_MONAT = 4.33
MATERIALZUSCHLAG = 0.04   # Reinigungsmittel, Tücher, Verbrauch
STUNDENSATZ_STANDARD = 32.0


def leistungswert(bodenbelag: str) -> float:
    """Quadratmeter je Stunde für einen Bodenbelag."""
    schluessel = (bodenbelag or "").strip().lower()
    for name, wert in LEISTUNGSWERTE.items():
        if name in schluessel:
            return wert
    return LEISTUNG_STANDARD


def geld_akquise(betrag) -> str:
    """Deutscher Betrag mit Euro-Zeichen."""
    try:
        betrag = float(betrag)
    except (TypeError, ValueError):
        betrag = 0.0
    return ("{:,.2f}".format(betrag).replace(",", "#").replace(".", ",")
            .replace("#", ".")) + " €"


class Akquise:
    """Führt die Pipeline, kalkuliert Angebote und sagt den Cashflow vorher."""

    def __init__(self, memory: Memory = None, mwst_satz: float = 20.0):
        self.memory = memory or Memory()
        self.mwst_satz = float(mwst_satz)
        db_schema_anlegen(SCHEMA_AKQUISE, self.memory.db_pfad)

    # -- Kalkulation --------------------------------------------------------

    def angebot_kalkulieren(self, qm: float, bodenbelag: str = "",
                            intervall_pro_woche: float = 1.0,
                            stundensatz: float = None,
                            sonderleistungen: dict = None) -> dict:
        """Rechnet aus Fläche, Belag und Intervall einen Monatspreis.

        Der Weg: Fläche geteilt durch Leistungswert ergibt Stunden je
        Reinigung. Mal Reinigungen im Monat ergibt Monatsstunden. Mal
        Stundensatz ergibt den Preis. Sonderleistungen kommen getrennt dazu,
        weil sie nicht im Intervall stecken.
        """
        try:
            qm = float(qm)
        except (TypeError, ValueError):
            return {"ok": False, "fehler": "Die Quadratmeter sind keine Zahl."}
        if qm <= 0:
            return {"ok": False,
                    "fehler": "Ohne Quadratmeter kann ich nicht kalkulieren. "
                              "Frag beim Objekt nach der Fläche."}
        try:
            intervall = float(intervall_pro_woche)
        except (TypeError, ValueError):
            intervall = 1.0
        if intervall <= 0:
            return {"ok": False,
                    "fehler": "Wie oft pro Woche soll gereinigt werden? Ohne das "
                              "gibt es keinen Monatspreis."}
        satz = float(stundensatz) if stundensatz else STUNDENSATZ_STANDARD

        leistung = leistungswert(bodenbelag)
        stunden_je_reinigung = qm / leistung
        reinigungen_monat = intervall * WOCHEN_PRO_MONAT
        stunden_monat = stunden_je_reinigung * reinigungen_monat
        lohn = stunden_monat * satz
        material = lohn * MATERIALZUSCHLAG

        posten = [
            {"bezeichnung": "Unterhaltsreinigung %.0f m² bei %s, %gx pro Woche"
                            % (qm, bodenbelag or "Standardbelag", intervall),
             "menge": round(stunden_monat, 2), "einheit": "Stunden",
             "einzelpreis": satz, "betrag": round(lohn, 2)},
            {"bezeichnung": "Reinigungsmittel und Verbrauchsmaterial",
             "menge": 1, "einheit": "pauschal",
             "einzelpreis": round(material, 2), "betrag": round(material, 2)},
        ]

        einmalig = 0.0
        for name, menge in (sonderleistungen or {}).items():
            schluessel = str(name).strip().lower()
            if schluessel not in SONDERLEISTUNGEN:
                continue
            einheit, preis = SONDERLEISTUNGEN[schluessel]
            try:
                menge = float(menge)
            except (TypeError, ValueError):
                continue
            if menge <= 0:
                continue
            betrag = menge * preis
            einmalig += betrag
            posten.append({"bezeichnung": "%s (%s)" % (name.capitalize(), einheit),
                           "menge": menge, "einheit": einheit,
                           "einzelpreis": preis, "betrag": round(betrag, 2)})

        netto_monat = round(lohn + material, 2)
        mwst_monat = round(netto_monat * self.mwst_satz / 100.0, 2)
        brutto_monat = round(netto_monat + mwst_monat, 2)
        netto_einmalig = round(einmalig, 2)

        return {
            "ok": True,
            "qm": qm, "bodenbelag": bodenbelag or "Standardbelag",
            "leistungswert": leistung,
            "intervall_pro_woche": intervall,
            "stundensatz": satz,
            "stunden_je_reinigung": round(stunden_je_reinigung, 2),
            "reinigungen_monat": round(reinigungen_monat, 1),
            "stunden_monat": round(stunden_monat, 2),
            "netto_monat": netto_monat,
            "mwst_monat": mwst_monat,
            "brutto_monat": brutto_monat,
            "einmalig_netto": netto_einmalig,
            "jahreswert_netto": round(netto_monat * 12 + netto_einmalig, 2),
            "qm_preis_monat": round(netto_monat / qm, 3),
            "posten": posten,
            "text": ("%.0f Quadratmeter %s, %gmal die Woche: das sind %.1f Stunden "
                     "im Monat. Bei %s Stundensatz macht das %s netto im Monat, "
                     "%s brutto. Im Jahr %s netto.%s"
                     % (qm, bodenbelag or "Standardbelag", intervall, stunden_monat,
                        geld_akquise(satz), geld_akquise(netto_monat), geld_akquise(brutto_monat),
                        geld_akquise(netto_monat * 12),
                        (" Dazu einmalig %s für Sonderleistungen."
                         % geld_akquise(netto_einmalig)) if netto_einmalig else "")),
        }

    def angebotstext(self, kalkulation: dict, firma: str = "",
                     ansprechpartner: str = "") -> str:
        """Formt aus der Kalkulation ein Angebot, das man verschicken kann."""
        if not kalkulation.get("ok"):
            return kalkulation.get("fehler", "Die Kalkulation fehlt.")
        zeilen = []
        anrede = ("Sehr geehrte Damen und Herren," if not ansprechpartner
                  else "Sehr geehrte/r %s," % ansprechpartner)
        zeilen.append(anrede)
        zeilen.append("")
        zeilen.append("vielen Dank für Ihr Interesse. Für die Reinigung Ihres "
                      "Objekts%s unterbreite ich Ihnen folgendes Angebot:"
                      % (" (%s)" % firma if firma else ""))
        zeilen.append("")
        for posten in kalkulation["posten"]:
            zeilen.append("  %-52s %12s"
                          % (posten["bezeichnung"][:52], geld_akquise(posten["betrag"])))
        zeilen.append("")
        zeilen.append("  %-52s %12s" % ("Monatlich netto", geld_akquise(kalkulation["netto_monat"])))
        zeilen.append("  %-52s %12s" % ("Mehrwertsteuer %g Prozent" % self.mwst_satz,
                                        geld_akquise(kalkulation["mwst_monat"])))
        zeilen.append("  %-52s %12s" % ("Monatlich brutto",
                                        geld_akquise(kalkulation["brutto_monat"])))
        if kalkulation["einmalig_netto"]:
            zeilen.append("  %-52s %12s" % ("Einmalige Sonderleistungen netto",
                                            geld_akquise(kalkulation["einmalig_netto"])))
        zeilen.append("")
        zeilen.append("Der Preis beruht auf %.1f Arbeitsstunden im Monat "
                      "(%.0f m² bei %gmaliger Reinigung pro Woche)."
                      % (kalkulation["stunden_monat"], kalkulation["qm"],
                         kalkulation["intervall_pro_woche"]))
        zeilen.append("Gerne führe ich vorab eine kostenlose Probereinigung durch, "
                      "damit Sie die Qualität beurteilen können.")
        zeilen.append("")
        zeilen.append("Mit freundlichen Grüßen")
        return "\n".join(zeilen)

    # -- Pipeline -----------------------------------------------------------

    def lead_anlegen(self, firma: str, ansprechpartner: str = "", telefon: str = "",
                     email: str = "", adresse: str = "", quelle: str = "",
                     objekt_qm: float = 0, bodenbelag: str = "",
                     intervall_pro_woche: float = 0, notiz: str = "",
                     naechster_schritt: str = "") -> dict:
        """Nimmt einen Interessenten auf."""
        firma = (firma or "").strip()
        if not firma:
            return {"ok": False, "fehler": "Der Interessent braucht einen Namen."}
        vorhanden = self.memory._lesen(
            "SELECT id FROM leads WHERE lower(firma)=lower(?) LIMIT 1", (firma,))
        if vorhanden:
            return {"ok": False, "id": vorhanden[0]["id"],
                    "fehler": "%s steht schon in der Liste." % firma}
        try:
            qm = float(objekt_qm or 0)
        except (TypeError, ValueError):
            qm = 0.0
        try:
            intervall = float(intervall_pro_woche or 0)
        except (TypeError, ValueError):
            intervall = 0.0

        wert = 0.0
        if qm > 0 and intervall > 0:
            kalkulation = self.angebot_kalkulieren(qm, bodenbelag, intervall)
            if kalkulation.get("ok"):
                wert = kalkulation["netto_monat"]

        faellig = (datetime.now() + timedelta(days=NACHFASS_TAGE["neu"])
                   ).strftime("%Y-%m-%d")
        nummer = self.memory._schreiben(
            "INSERT INTO leads (firma, ansprechpartner, telefon, email, adresse, "
            "quelle, objekt_qm, bodenbelag, intervall_pro_woche, sonderleistungen, "
            "stufe, wert_monat, naechster_schritt, naechster_kontakt, notiz, "
            "angelegt, geaendert) VALUES (?,?,?,?,?,?,?,?,?,'','neu',?,?,?,?,?,?)",
            (firma, ansprechpartner, telefon, email, adresse, quelle, qm, bodenbelag,
             intervall, wert, naechster_schritt or "anrufen und Termin vereinbaren",
             faellig, notiz, zeitstempel(), zeitstempel()))
        return {"ok": True, "id": nummer, "firma": firma, "wert_monat": wert,
                "text": "%s ist aufgenommen.%s Nächster Schritt bis %s: %s"
                        % (firma,
                           (" Geschätzter Wert %s im Monat." % geld_akquise(wert)) if wert else "",
                           faellig, naechster_schritt or "anrufen und Termin vereinbaren")}

    def lead_finden(self, name: str):
        """Sucht einen Interessenten - auch bei ungenauem Namen."""
        name = (name or "").strip()
        if not name:
            return None
        genau = self.memory._lesen(
            "SELECT * FROM leads WHERE lower(firma)=lower(?) LIMIT 1", (name,))
        if genau:
            return genau[0]
        teil = self.memory._lesen(
            "SELECT * FROM leads WHERE firma LIKE ? OR ansprechpartner LIKE ? "
            "ORDER BY geaendert DESC LIMIT 1",
            ("%%%s%%" % name, "%%%s%%" % name))
        return teil[0] if teil else None

    def lead_weiterstufen(self, name: str, stufe: str, notiz: str = "",
                          naechster_schritt: str = "",
                          wert_monat: float = None) -> dict:
        """Setzt einen Interessenten auf die nächste Stufe."""
        stufe = (stufe or "").strip().lower()
        if stufe not in STUFEN:
            return {"ok": False,
                    "fehler": "'%s' ist keine Stufe. Möglich: %s."
                              % (stufe, ", ".join(STUFEN))}
        lead = self.lead_finden(name)
        if lead is None:
            return {"ok": False, "fehler": "'%s' steht nicht in der Liste." % name}

        tage = NACHFASS_TAGE.get(stufe, 0)
        faellig = ((datetime.now() + timedelta(days=tage)).strftime("%Y-%m-%d")
                   if tage else "")
        neuer_wert = lead["wert_monat"] if wert_monat is None else float(wert_monat)
        neue_notiz = ("%s | %s" % (lead["notiz"], notiz)).strip(" |") if notiz \
            else lead["notiz"]

        self.memory._schreiben(
            "UPDATE leads SET stufe=?, notiz=?, naechster_schritt=?, "
            "naechster_kontakt=?, wert_monat=?, geaendert=? WHERE id=?",
            (stufe, neue_notiz, naechster_schritt or lead["naechster_schritt"],
             faellig, neuer_wert, zeitstempel(), lead["id"]))

        if stufe == "gewonnen":
            text = ("%s ist gewonnen. %s im Monat, das sind %s im Jahr."
                    % (lead["firma"], geld_akquise(neuer_wert), geld_akquise(neuer_wert * 12)))
        elif stufe == "verloren":
            text = "%s ist verloren. %s" % (lead["firma"], notiz or "")
        else:
            text = ("%s steht jetzt auf %s.%s"
                    % (lead["firma"], stufe,
                       (" Wieder melden bis %s: %s" % (faellig, naechster_schritt))
                       if faellig and naechster_schritt else ""))
        return {"ok": True, "id": lead["id"], "stufe": stufe, "text": text}

    def pipeline(self) -> dict:
        """Alle Interessenten nach Stufen, mit Werten."""
        zeilen = self.memory._lesen("SELECT * FROM leads ORDER BY wert_monat DESC")
        nach_stufe = {stufe: [] for stufe in STUFEN}
        for zeile in zeilen:
            nach_stufe.setdefault(zeile["stufe"], []).append(zeile)

        offen = [z for z in zeilen if z["stufe"] not in ("gewonnen", "verloren")]
        gewichtet = sum(z["wert_monat"] * WAHRSCHEINLICHKEIT.get(z["stufe"], 0)
                        for z in offen)
        gewonnen = [z for z in zeilen if z["stufe"] == "gewonnen"]
        laufend = sum(z["wert_monat"] for z in gewonnen)

        uebersicht = {}
        for stufe in STUFEN:
            eintraege = nach_stufe.get(stufe, [])
            uebersicht[stufe] = {
                "anzahl": len(eintraege),
                "wert_monat": round(sum(e["wert_monat"] for e in eintraege), 2),
                "firmen": [e["firma"] for e in eintraege[:6]]}

        return {"ok": True, "stufen": uebersicht,
                "offen": len(offen),
                "offener_wert_monat": round(sum(z["wert_monat"] for z in offen), 2),
                "gewichteter_wert_monat": round(gewichtet, 2),
                "laufender_umsatz_monat": round(laufend, 2),
                "text": ("%d Interessenten offen über %s im Monat. Realistisch "
                         "gewichtet sind das %s. Laufend gesichert: %s im Monat "
                         "aus %d Aufträgen."
                         % (len(offen), geld_akquise(sum(z["wert_monat"] for z in offen)),
                            geld_akquise(gewichtet), geld_akquise(laufend), len(gewonnen)))}

    def nachfassliste(self, bis: str = "") -> dict:
        """Wer heute dran ist - und warum.

        Das ist die Liste, die morgens zählt. Ein Interessent, bei dem niemand
        nachfasst, ist verloren, ohne dass es jemand merkt.
        """
        grenze = bis or heute_datum()
        zeilen = self.memory._lesen(
            "SELECT * FROM leads WHERE stufe NOT IN ('gewonnen','verloren') "
            "AND naechster_kontakt<>'' AND naechster_kontakt<=? "
            "ORDER BY wert_monat DESC", (grenze,))
        eintraege = []
        for zeile in zeilen:
            try:
                faellig_seit = (datetime.strptime(grenze, "%Y-%m-%d") -
                                datetime.strptime(zeile["naechster_kontakt"],
                                                  "%Y-%m-%d")).days
            except ValueError:
                faellig_seit = 0
            eintraege.append({
                "id": zeile["id"], "firma": zeile["firma"],
                "ansprechpartner": zeile["ansprechpartner"],
                "telefon": zeile["telefon"], "stufe": zeile["stufe"],
                "wert_monat": zeile["wert_monat"],
                "seit_tagen": faellig_seit,
                "schritt": zeile["naechster_schritt"]})

        if not eintraege:
            text = "Heute ist niemand zum Nachfassen fällig."
        else:
            erster = eintraege[0]
            text = ("%d Interessenten sind fällig, zusammen %s im Monat. "
                    "Fang mit %s an: %s%s"
                    % (len(eintraege),
                       geld_akquise(sum(e["wert_monat"] for e in eintraege)),
                       erster["firma"], erster["schritt"],
                       (" Der Termin ist seit %d Tagen überfällig."
                        % erster["seit_tagen"]) if erster["seit_tagen"] > 0 else ""))
        return {"ok": True, "anzahl": len(eintraege), "eintraege": eintraege,
                "text": text}

    # -- Neue Interessenten finden -----------------------------------------

    def leads_finden(self, ort: str, branche: str = "", anzahl: int = 8,
                     welt=None, agent=None) -> dict:
        """Sucht Betriebe in einem Ort, die Reinigung brauchen könnten.

        Der Weg: über den Such-Dienst nach Betrieben suchen, die Trefferliste
        von Claude in Name, Adresse und Telefon zerlegen lassen und daraus
        Interessenten anlegen. Was schon in der Liste steht, wird übersprungen.

        **Was das ist und was nicht:** Das sind Betriebe, die es gibt - keine
        Interessenten. Ob sie überhaupt Bedarf haben, weiß niemand, bis
        angerufen wurde. Deshalb landen sie auf der Stufe 'neu' mit dem
        nächsten Schritt "anrufen", und ihr Wert steht auf null, bis die
        Quadratmeter bekannt sind. Eine Pipeline mit geschätzten Werten für
        Betriebe, mit denen nie jemand gesprochen hat, wäre eine Lüge.
        """
        ort = (ort or "").strip()
        if not ort:
            return {"ok": False, "fehler": "In welchem Ort soll ich suchen?"}
        if welt is None:
            return {"ok": False, "fehler": "Die Suche ist nicht verfügbar."}
        if agent is None or not getattr(agent, "einsatzbereit", lambda: False)():
            return {"ok": False,
                    "fehler": "Ohne eingerichtetes Gehirn kann ich die Treffer nicht "
                              "auswerten."}

        branchen = branche.strip() if branche else \
            "Arztpraxen, Steuerberater, Kanzleien, Autohäuser, Fitnessstudios"
        anfrage = ("%s in %s mit Adresse und Telefonnummer" % (branchen, ort))
        gefunden = welt.recherche(anfrage)
        if not gefunden.get("ok"):
            return {"ok": False,
                    "fehler": "Für die Suche fehlt der Such-Dienst. In "
                              "config/mcp_servers.json den Eintrag 'suche' auf "
                              "\"aus\": false stellen und einen Brave-Schlüssel "
                              "eintragen. (%s)" % gefunden.get("fehler", "")[:80]}

        auftrag = (
            "Aus dieser Trefferliste sollen Betriebe für die Kaltakquise einer "
            "Gebäudereinigung herausgezogen werden.\n\n"
            "Gib ausschließlich JSON zurück: {\"betriebe\": [{\"firma\": ..., "
            "\"branche\": ..., \"adresse\": ..., \"telefon\": ...}]}\n\n"
            "Nimm höchstens %d Betriebe. Nimm nur echte, benannte Betriebe mit "
            "Ortsbezug - keine Verzeichnisse, keine Portale, keine "
            "Sammelseiten. Fehlt eine Telefonnummer oder Adresse, lass das Feld "
            "leer, statt etwas zu erfinden.\n\nTrefferliste:\n%s"
            % (int(anzahl or 8), gefunden.get("text", "")[:6000]))
        antwort = agent.json_anfrage(auftrag)
        if not antwort.get("ok"):
            return {"ok": False,
                    "fehler": "Die Trefferliste war nicht auswertbar: %s"
                              % antwort.get("fehler", "")}

        betriebe = (antwort["daten"] or {}).get("betriebe") or []
        neu, bekannt = [], []
        for eintrag in betriebe[:int(anzahl or 8)]:
            firma = str(eintrag.get("firma") or "").strip()
            if not firma:
                continue
            ergebnis = self.lead_anlegen(
                firma, telefon=str(eintrag.get("telefon") or ""),
                adresse=str(eintrag.get("adresse") or ""),
                quelle="Recherche %s" % ort,
                notiz=str(eintrag.get("branche") or ""),
                naechster_schritt="anrufen und fragen, wer die Reinigung macht")
            if ergebnis.get("ok"):
                neu.append(firma)
            else:
                bekannt.append(firma)

        if not neu:
            text = ("Ich habe %d Betriebe gefunden, aber keiner ist neu%s."
                    % (len(betriebe), " - alle stehen schon in der Liste"
                       if bekannt else ""))
        else:
            text = ("%d neue Betriebe in %s aufgenommen: %s. Sie stehen auf 'neu' "
                    "mit Wert null - was sie wert sind, weißt du erst nach dem "
                    "Anruf.%s"
                    % (len(neu), ort, ", ".join(neu[:5]),
                       (" %d kanntest du schon." % len(bekannt)) if bekannt else ""))
        return {"ok": True, "neu": neu, "bekannt": bekannt,
                "gefunden": len(betriebe), "text": text}

    # -- Cashflow -----------------------------------------------------------

    def cashflow_prognose(self, monate: int = 6, bookkeeping=None) -> dict:
        """Was in den nächsten Monaten hereinkommt.

        Gesichert sind die gewonnenen Aufträge - die laufen weiter. Dazu kommt
        die Pipeline, aber nur gewichtet nach Stufe. Ein Angebot ist kein Geld,
        und so wird es hier auch behandelt.
        """
        monate = max(1, min(24, int(monate or 6)))
        gewonnen = self.memory._lesen(
            "SELECT * FROM leads WHERE stufe='gewonnen'")
        offen = self.memory._lesen(
            "SELECT * FROM leads WHERE stufe NOT IN ('gewonnen','verloren')")

        gesichert = sum(z["wert_monat"] for z in gewonnen)
        gewichtet = sum(z["wert_monat"] * WAHRSCHEINLICHKEIT.get(z["stufe"], 0)
                        for z in offen)

        # Laufende Kosten aus der Buchhaltung, sofern vorhanden.
        kosten_monat = 0.0
        kostenquelle = "keine Buchhaltungsdaten"
        if bookkeeping is not None:
            try:
                verlauf = bookkeeping.monatsverlauf(3)
                ausgaben = [a for a in verlauf.get("einnahmen", [])]
                del ausgaben
                gesamt = bookkeeping.auswertung(
                    (datetime.now() - timedelta(days=90)).strftime("%Y-%m-%d"),
                    heute_datum())
                if gesamt.get("anzahl"):
                    kosten_monat = round(gesamt["ausgaben"] / 3.0, 2)
                    kostenquelle = "Durchschnitt der letzten 3 Monate"
            except Exception:
                kosten_monat = 0.0

        reihe = []
        jetzt = datetime.now()
        for versatz in range(monate):
            jahr, monat = jetzt.year, jetzt.month + versatz
            while monat > 12:
                monat -= 12
                jahr += 1
            # Neue Abschlüsse brauchen Anlaufzeit: im ersten Monat wirkt die
            # Pipeline noch nicht, danach steigt sie langsam ein.
            anteil = 0.0 if versatz == 0 else min(1.0, versatz / 3.0)
            erwartet = gesichert + gewichtet * anteil
            reihe.append({
                "monat": "%04d-%02d" % (jahr, monat),
                "gesichert": round(gesichert, 2),
                "aus_pipeline": round(gewichtet * anteil, 2),
                "einnahmen": round(erwartet, 2),
                "kosten": kosten_monat,
                "ergebnis": round(erwartet - kosten_monat, 2)})

        return {"ok": True, "monate": reihe,
                "gesichert_monat": round(gesichert, 2),
                "pipeline_gewichtet": round(gewichtet, 2),
                "kosten_monat": kosten_monat, "kostenquelle": kostenquelle,
                "text": ("Gesichert laufen %s im Monat herein. Aus der Pipeline "
                         "kommen realistisch %s dazu, aber erst über zwei bis drei "
                         "Monate. Bei Kosten von %s im Monat (%s) bleiben in %d "
                         "Monaten etwa %s übrig."
                         % (geld_akquise(gesichert), geld_akquise(gewichtet), geld_akquise(kosten_monat),
                            kostenquelle, monate,
                            geld_akquise(sum(m["ergebnis"] for m in reihe))))}

    def angebot_ablegen(self, lead_name: str, kalkulation: dict,
                        notiz: str = "") -> dict:
        """Legt ein kalkuliertes Angebot zum Interessenten ab."""
        if not kalkulation.get("ok"):
            return {"ok": False, "fehler": "Die Kalkulation ist nicht gültig."}
        lead = self.lead_finden(lead_name)
        nummer = self.memory._schreiben(
            "INSERT INTO angebote (lead_id, datum, qm, bodenbelag, "
            "intervall_pro_woche, stundensatz, stunden_monat, netto_monat, "
            "brutto_monat, posten, status, notiz, angelegt) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,'entwurf',?,?)",
            (lead["id"] if lead else None, heute_datum(), kalkulation["qm"],
             kalkulation["bodenbelag"], kalkulation["intervall_pro_woche"],
             kalkulation["stundensatz"], kalkulation["stunden_monat"],
             kalkulation["netto_monat"], kalkulation["brutto_monat"],
             json.dumps(kalkulation["posten"], ensure_ascii=False), notiz,
             zeitstempel()))
        if lead is not None:
            self.lead_weiterstufen(lead["firma"], "angebot",
                                   naechster_schritt="Angebot nachfassen",
                                   wert_monat=kalkulation["netto_monat"])
        return {"ok": True, "id": nummer,
                "text": "Angebot über %s im Monat abgelegt%s."
                        % (geld_akquise(kalkulation["netto_monat"]),
                           (" für %s" % lead["firma"]) if lead else "")}


# =========================================================================
# privat  -  Privat - das Leben neben der Firma, und wie beides zusammenhängt.
# 
# Ein Einzelunternehmer hat kein Gehalt. Er hat Umsatz, davon gehen Kosten und
# Steuern ab, und was übrig bleibt, muss die Miete zahlen. Genau diese Rechnung
# macht kaum jemand - und deshalb weiß kaum jemand, wie viel der Betrieb
# eigentlich abwerfen **muss**.
# 
# Das ist die Aufgabe dieses Moduls:
# 
# * Private Fixkosten und Firmenfixkosten getrennt führen, denn beim
#   Steuerberater dürfen sie sich nicht vermischen.
# * Daraus den **nötigen Monatsumsatz** ausrechnen: was hereinkommen muss, damit
#   nach Kosten und Steuerrücklage das Private gedeckt ist.
# * Erinnerungen an das, was einmal im Jahr kommt und trotzdem jedes Jahr
#   überrascht: Versicherung, Pickerl, Geburtstage, Vorauszahlung.
# =========================================================================

#!/usr/bin/env python3
# -*- coding: utf-8 -*-



SCHEMA_PRIVAT = """
CREATE TABLE IF NOT EXISTS fixkosten (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    betrag REAL NOT NULL,
    rhythmus TEXT DEFAULT 'monatlich',
    bereich TEXT DEFAULT 'privat',
    kategorie TEXT DEFAULT '',
    faellig_am TEXT DEFAULT '',
    aktiv INTEGER DEFAULT 1,
    notiz TEXT DEFAULT '',
    angelegt TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS erinnerungen (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    was TEXT NOT NULL,
    datum TEXT NOT NULL,
    wiederholung TEXT DEFAULT 'einmalig',
    bereich TEXT DEFAULT 'privat',
    notiz TEXT DEFAULT '',
    erledigt INTEGER DEFAULT 0,
    angelegt TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_erinnerungen_datum ON erinnerungen(datum);
"""

# Wie oft etwas anfällt, umgerechnet auf einen Monat.
RHYTHMEN = {
    "woechentlich": 4.333, "wöchentlich": 4.333,
    "monatlich": 1.0,
    "zweimonatlich": 0.5,
    "quartalsweise": 1 / 3.0, "vierteljaehrlich": 1 / 3.0, "vierteljährlich": 1 / 3.0,
    "halbjaehrlich": 1 / 6.0, "halbjährlich": 1 / 6.0,
    "jaehrlich": 1 / 12.0, "jährlich": 1 / 12.0,
}
BEREICHE = ("privat", "firma")
WIEDERHOLUNGEN = ("einmalig", "monatlich", "jaehrlich")


def monatsanteil(betrag: float, rhythmus: str) -> float:
    """Rechnet einen Betrag auf den Monat um."""
    try:
        betrag = float(betrag)
    except (TypeError, ValueError):
        return 0.0
    faktor = RHYTHMEN.get((rhythmus or "monatlich").strip().lower(), 1.0)
    return round(betrag * faktor, 2)


def euro_privat(betrag) -> str:
    """Deutscher Betrag mit Euro-Zeichen."""
    try:
        betrag = float(betrag)
    except (TypeError, ValueError):
        betrag = 0.0
    return ("{:,.2f}".format(betrag).replace(",", "#").replace(".", ",")
            .replace("#", ".")) + " €"


class Privat:
    """Fixkosten, Erinnerungen und die Brücke zwischen Firma und Privatleben."""

    def __init__(self, memory: Memory = None, steuersatz: float = None):
        self.memory = memory or Memory()
        # Rücklage für Einkommensteuer und Sozialversicherung zusammen.
        self.steuersatz = float(steuersatz if steuersatz is not None
                                else STEUER_RUECKLAGE)
        db_schema_anlegen(SCHEMA_PRIVAT, self.memory.db_pfad)

    # -- Fixkosten ----------------------------------------------------------

    def fixkosten_anlegen(self, name: str, betrag: float,
                          rhythmus: str = "monatlich", bereich: str = "privat",
                          kategorie: str = "", faellig_am: str = "",
                          notiz: str = "") -> dict:
        """Trägt eine wiederkehrende Verpflichtung ein."""
        name = (name or "").strip()
        if not name:
            return {"ok": False, "fehler": "Die Fixkosten brauchen einen Namen."}
        try:
            betrag = round(float(betrag), 2)
        except (TypeError, ValueError):
            return {"ok": False, "fehler": "Der Betrag ist keine Zahl."}
        if betrag <= 0:
            return {"ok": False, "fehler": "Der Betrag muss größer als null sein."}
        rhythmus = (rhythmus or "monatlich").strip().lower()
        if rhythmus not in RHYTHMEN:
            return {"ok": False,
                    "fehler": "Den Rhythmus '%s' kenne ich nicht. Möglich: %s."
                              % (rhythmus, ", ".join(sorted(set(RHYTHMEN))))}
        bereich = (bereich or "privat").strip().lower()
        if bereich not in BEREICHE:
            return {"ok": False,
                    "fehler": "Der Bereich muss privat oder firma sein."}

        vorhanden = self.memory._lesen(
            "SELECT id FROM fixkosten WHERE lower(name)=lower(?) AND bereich=? "
            "AND aktiv=1 LIMIT 1", (name, bereich))
        if vorhanden:
            self.memory._schreiben(
                "UPDATE fixkosten SET betrag=?, rhythmus=?, kategorie=?, "
                "faellig_am=?, notiz=? WHERE id=?",
                (betrag, rhythmus, kategorie, faellig_am, notiz, vorhanden[0]["id"]))
            nummer, geaendert = vorhanden[0]["id"], True
        else:
            nummer = self.memory._schreiben(
                "INSERT INTO fixkosten (name, betrag, rhythmus, bereich, kategorie, "
                "faellig_am, aktiv, notiz, angelegt) VALUES (?,?,?,?,?,?,1,?,?)",
                (name, betrag, rhythmus, bereich, kategorie, faellig_am, notiz,
                 zeitstempel()))
            geaendert = False

        je_monat = monatsanteil(betrag, rhythmus)
        return {"ok": True, "id": nummer, "je_monat": je_monat,
                "text": "%s %s: %s %s, das sind %s im Monat."
                        % ("Geändert" if geaendert else "Eingetragen",
                           name, euro_privat(betrag), rhythmus,
                           euro_privat(je_monat))}

    def fixkosten_streichen(self, name: str, bereich: str = "") -> dict:
        """Setzt eine Verpflichtung auf inaktiv."""
        bedingung = "lower(name)=lower(?) AND aktiv=1"
        werte = [name]
        if bereich:
            bedingung += " AND bereich=?"
            werte.append(bereich.lower())
        zeilen = self.memory._lesen(
            "SELECT * FROM fixkosten WHERE %s" % bedingung, tuple(werte))
        if not zeilen:
            return {"ok": False, "fehler": "'%s' steht nicht in den Fixkosten." % name}
        for zeile in zeilen:
            self.memory._schreiben("UPDATE fixkosten SET aktiv=0 WHERE id=?",
                                   (zeile["id"],))
        return {"ok": True,
                "text": "%s ist gestrichen. Das spart %s im Monat."
                        % (zeilen[0]["name"],
                           euro_privat(sum(monatsanteil(z["betrag"], z["rhythmus"])
                                           for z in zeilen)))}

    def fixkosten(self, bereich: str = "") -> dict:
        """Alle laufenden Verpflichtungen, auf den Monat gerechnet."""
        if bereich:
            zeilen = self.memory._lesen(
                "SELECT * FROM fixkosten WHERE aktiv=1 AND bereich=? ORDER BY betrag DESC",
                (bereich.lower(),))
        else:
            zeilen = self.memory._lesen(
                "SELECT * FROM fixkosten WHERE aktiv=1 ORDER BY bereich, betrag DESC")

        eintraege, privat_summe, firma_summe = [], 0.0, 0.0
        for zeile in zeilen:
            je_monat = monatsanteil(zeile["betrag"], zeile["rhythmus"])
            eintraege.append({"id": zeile["id"], "name": zeile["name"],
                              "betrag": zeile["betrag"], "rhythmus": zeile["rhythmus"],
                              "bereich": zeile["bereich"], "je_monat": je_monat,
                              "faellig_am": zeile["faellig_am"]})
            if zeile["bereich"] == "firma":
                firma_summe += je_monat
            else:
                privat_summe += je_monat

        return {"ok": True, "eintraege": eintraege, "anzahl": len(eintraege),
                "privat_je_monat": round(privat_summe, 2),
                "firma_je_monat": round(firma_summe, 2),
                "gesamt_je_monat": round(privat_summe + firma_summe, 2),
                "text": ("Privat %s im Monat, Firma %s, zusammen %s."
                         % (euro_privat(privat_summe), euro_privat(firma_summe),
                            euro_privat(privat_summe + firma_summe))) if eintraege
                        else "Es sind noch keine Fixkosten erfasst."}

    # -- Die entscheidende Rechnung ----------------------------------------

    def bedarfsrechnung(self, akquise=None) -> dict:
        """Wie viel Umsatz der Betrieb monatlich braucht, damit privat alles gedeckt ist.

        Der Weg rückwärts vom Privatleben zum Umsatz::

            Umsatz netto - Firmenkosten           = Gewinn
            Gewinn - Steuerrücklage               = was entnommen werden kann
            das muss mindestens die Privatkosten decken

        Aufgelöst nach Umsatz::

            Umsatz = Firmenkosten + Privatkosten / (1 - Steuersatz)

        Das ist die Zahl, die ein Einzelunternehmer eigentlich täglich kennen
        müsste und fast nie kennt.
        """
        kosten = self.fixkosten()
        privat = kosten["privat_je_monat"]
        firma = kosten["firma_je_monat"]
        anteil = max(0.0, min(0.9, self.steuersatz / 100.0))

        if privat <= 0 and firma <= 0:
            return {"ok": True, "berechenbar": False,
                    "text": "Ich kenne deine Fixkosten noch nicht. Sag mir, was "
                            "monatlich fix rausgeht - Miete, Versicherungen, Auto, "
                            "Telefon - dann rechne ich aus, was der Betrieb "
                            "abwerfen muss."}

        noetiger_umsatz = firma + (privat / (1.0 - anteil) if anteil < 1 else privat)
        noetiger_umsatz = round(noetiger_umsatz, 2)
        gewinn = round(noetiger_umsatz - firma, 2)
        steuer = round(gewinn * anteil, 2)

        gesichert = None
        luecke = None
        if akquise is not None:
            try:
                pipeline = akquise.pipeline()
                gesichert = pipeline["laufender_umsatz_monat"]
                luecke = round(noetiger_umsatz - gesichert, 2)
            except Exception:
                gesichert = None

        text = ("Damit privat alles gedeckt ist, muss der Betrieb %s netto im Monat "
                "machen. Davon gehen %s Firmenkosten ab, bleiben %s Gewinn, davon "
                "%s Steuerrücklage bei %g Prozent - übrig bleiben die %s, die du "
                "privat brauchst."
                % (euro_privat(noetiger_umsatz), euro_privat(firma),
                   euro_privat(gewinn), euro_privat(steuer), self.steuersatz,
                   euro_privat(privat)))
        if gesichert is not None:
            if luecke > 0:
                text += (" Gesichert laufen %s. Dir fehlen %s im Monat - das sind "
                         "etwa %s im Jahr."
                         % (euro_privat(gesichert), euro_privat(luecke),
                            euro_privat(luecke * 12)))
            else:
                text += (" Gesichert laufen %s, du liegst %s darüber."
                         % (euro_privat(gesichert), euro_privat(-luecke)))

        return {"ok": True, "berechenbar": True,
                "privat_je_monat": privat, "firma_je_monat": firma,
                "steuersatz": self.steuersatz,
                "noetiger_umsatz": noetiger_umsatz,
                "gewinn": gewinn, "steuerruecklage": steuer,
                "gesichert": gesichert, "luecke": luecke,
                "text": text}

    # -- Erinnerungen -------------------------------------------------------

    def erinnerung_anlegen(self, was: str, datum: str,
                           wiederholung: str = "einmalig",
                           bereich: str = "privat", notiz: str = "") -> dict:
        """Merkt sich etwas mit Datum - auch jährlich wiederkehrend."""
        was = (was or "").strip()
        if not was:
            return {"ok": False, "fehler": "Woran soll ich erinnern?"}
        datum = (datum or "").strip()
        try:
            datetime.strptime(datum, "%Y-%m-%d")
        except ValueError:
            return {"ok": False,
                    "fehler": "Das Datum muss als JJJJ-MM-TT kommen, bekommen habe "
                              "ich '%s'." % datum}
        wiederholung = (wiederholung or "einmalig").strip().lower()
        if wiederholung not in WIEDERHOLUNGEN:
            return {"ok": False,
                    "fehler": "Die Wiederholung muss %s sein."
                              % " oder ".join(WIEDERHOLUNGEN)}
        nummer = self.memory._schreiben(
            "INSERT INTO erinnerungen (was, datum, wiederholung, bereich, notiz, "
            "erledigt, angelegt) VALUES (?,?,?,?,?,0,?)",
            (was, datum, wiederholung, (bereich or "privat").lower(), notiz,
             zeitstempel()))
        return {"ok": True, "id": nummer,
                "text": "Gemerkt: %s am %s%s." % (was, datum,
                        (", %s" % wiederholung) if wiederholung != "einmalig" else "")}

    def _naechster_termin(self, zeile, ab: datetime):
        """Wann eine Erinnerung das nächste Mal fällig ist."""
        try:
            datum = datetime.strptime(zeile["datum"], "%Y-%m-%d")
        except (ValueError, TypeError):
            return None
        if zeile["wiederholung"] == "jaehrlich":
            kandidat = datum.replace(year=ab.year)
            if kandidat.date() < ab.date():
                kandidat = datum.replace(year=ab.year + 1)
            return kandidat
        if zeile["wiederholung"] == "monatlich":
            kandidat = datum
            while kandidat.date() < ab.date():
                jahr = kandidat.year + (1 if kandidat.month == 12 else 0)
                monat = 1 if kandidat.month == 12 else kandidat.month + 1
                tag = min(kandidat.day, 28)
                kandidat = kandidat.replace(year=jahr, month=monat, day=tag)
            return kandidat
        return datum

    def erinnerungen_faellig(self, tage: int = 14, ab: str = "") -> dict:
        """Was in den nächsten Tagen ansteht."""
        heute = datetime.strptime(ab, "%Y-%m-%d") if ab else datetime.now()
        grenze = heute + timedelta(days=max(1, int(tage or 14)))
        zeilen = self.memory._lesen("SELECT * FROM erinnerungen WHERE erledigt=0")

        faellig = []
        for zeile in zeilen:
            termin = self._naechster_termin(zeile, heute)
            if termin is None:
                continue
            if termin.date() > grenze.date():
                continue
            tage_hin = (termin.date() - heute.date()).days
            faellig.append({"id": zeile["id"], "was": zeile["was"],
                            "datum": termin.strftime("%Y-%m-%d"),
                            "in_tagen": tage_hin, "bereich": zeile["bereich"],
                            "wiederholung": zeile["wiederholung"],
                            "notiz": zeile["notiz"]})
        faellig.sort(key=lambda e: e["in_tagen"])

        if not faellig:
            text = "In den nächsten %d Tagen steht nichts an." % tage
        else:
            erste = faellig[0]
            wann = ("heute" if erste["in_tagen"] == 0
                    else "morgen" if erste["in_tagen"] == 1
                    else "in %d Tagen" % erste["in_tagen"]
                    if erste["in_tagen"] > 0 else "seit %d Tagen überfällig"
                    % abs(erste["in_tagen"]))
            text = ("%d Termine in den nächsten %d Tagen. Als nächstes: %s %s."
                    % (len(faellig), tage, erste["was"], wann))
        return {"ok": True, "anzahl": len(faellig), "eintraege": faellig,
                "text": text}

    def erinnerung_erledigen(self, nummer: int) -> dict:
        """Hakt eine einmalige Erinnerung ab."""
        zeilen = self.memory._lesen(
            "SELECT * FROM erinnerungen WHERE id=? AND erledigt=0", (nummer,))
        if not zeilen:
            return {"ok": False, "fehler": "Diese Erinnerung gibt es nicht."}
        if zeilen[0]["wiederholung"] != "einmalig":
            return {"ok": True,
                    "text": "%s wiederholt sich %s - ich lasse sie stehen."
                            % (zeilen[0]["was"], zeilen[0]["wiederholung"])}
        self.memory._schreiben("UPDATE erinnerungen SET erledigt=1 WHERE id=?",
                               (nummer,))
        return {"ok": True, "text": "%s ist abgehakt." % zeilen[0]["was"]}

    def uebersicht(self, akquise=None) -> dict:
        """Alles Private auf einen Blick."""
        kosten = self.fixkosten()
        bedarf = self.bedarfsrechnung(akquise)
        anstehend = self.erinnerungen_faellig(21)
        teile = [t for t in (kosten.get("text"), bedarf.get("text"),
                             anstehend.get("text")) if t]
        return {"ok": True, "fixkosten": kosten, "bedarf": bedarf,
                "erinnerungen": anstehend, "text": " ".join(teile)}


# =========================================================================
# routines  -  Routinen - gespeicherte Abläufe, die der Nutzer per Sprache anlegt.
# 
# Eine Routine ist kein starres Skript, sondern eine Anweisung an Claude selbst.
# Er liest sie und entscheidet mit seinen Werkzeugen, wie er sie umsetzt. Das ist
# robuster als eine feste Schrittfolge: ändert sich etwas, passt Claude sich an.
# 
# Namen trifft die Spracherkennung selten wortgenau. Deshalb wird dreistufig
# gesucht: exakt, dann Teiltreffer, dann einzelne Wörter.
# =========================================================================

#!/usr/bin/env python3
# -*- coding: utf-8 -*-



SCHEMA_ROUTINEN = """
CREATE TABLE IF NOT EXISTS routinen (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    anweisung TEXT NOT NULL,
    uhrzeit TEXT DEFAULT '',
    tage TEXT DEFAULT 'taeglich',
    aktiv INTEGER DEFAULT 1,
    zuletzt TEXT DEFAULT '',
    laeufe INTEGER DEFAULT 0,
    angelegt TEXT NOT NULL
);
"""

UHRZEIT_MUSTER = re.compile(r"^([01]?\d|2[0-3])[:.]?([0-5]\d)?$")


def name_normalisieren(name: str) -> str:
    """Kleinschreibung, Umlaute ausgeschrieben, Sonderzeichen weg."""
    text = (name or "").strip().lower()
    for alt, neu in (("ä", "ae"), ("ö", "oe"), ("ü", "ue"), ("ß", "ss")):
        text = text.replace(alt, neu)
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9 ]+", " ", text)).strip()


def name_kompakt(name: str) -> str:
    """Wie :func:`name_normalisieren`, aber ohne jedes Leerzeichen."""
    return name_normalisieren(name).replace(" ", "")


def uhrzeit_normalisieren(uhrzeit: str) -> str:
    """Macht aus '18', '18 Uhr', '1800' oder '18:00' ein sauberes 'HH:MM'."""
    roh = (uhrzeit or "").strip().lower()
    if not roh:
        return ""
    roh = roh.replace("uhr", "").strip()
    roh = re.sub(r"[^0-9:.]", "", roh)
    if not roh:
        return ""
    if ":" in roh or "." in roh:
        teile = re.split(r"[:.]", roh)
        stunde = teile[0]
        minute = teile[1] if len(teile) > 1 and teile[1] else "00"
    elif len(roh) == 4:
        stunde, minute = roh[:2], roh[2:]
    else:
        stunde, minute = roh, "00"
    try:
        stunde_zahl, minute_zahl = int(stunde), int(minute)
    except ValueError:
        return ""
    if not (0 <= stunde_zahl <= 23 and 0 <= minute_zahl <= 59):
        return ""
    return "%02d:%02d" % (stunde_zahl, minute_zahl)


class Routines:
    """Verwaltet gespeicherte Abläufe und findet sie auch bei ungenauem Namen."""

    def __init__(self, memory: Memory = None):
        self.memory = memory or Memory()
        db_schema_anlegen(SCHEMA_ROUTINEN, self.memory.db_pfad)

    # -- Anlegen und pflegen ------------------------------------------------

    def routine_anlegen(self, name: str, anweisung: str, uhrzeit: str = "",
                        tage: str = "taeglich") -> dict:
        """Legt eine Routine an oder überschreibt eine gleichnamige."""
        name = (name or "").strip()
        anweisung = (anweisung or "").strip()
        if not name:
            return {"ok": False, "fehler": "Die Routine braucht einen Namen."}
        if not anweisung:
            return {"ok": False,
                    "fehler": "Sag mir, was die Routine tun soll, dann lege ich sie an."}
        zeit = uhrzeit_normalisieren(uhrzeit)
        if uhrzeit and not zeit:
            return {"ok": False,
                    "fehler": "Die Uhrzeit '%s' verstehe ich nicht. Sag sie zum Beispiel "
                              "als 18 Uhr oder 18:30." % uhrzeit}

        vorhanden = self._exakt(name)
        if vorhanden:
            self.memory._schreiben(
                "UPDATE routinen SET anweisung=?, uhrzeit=?, tage=?, aktiv=1 WHERE id=?",
                (anweisung, zeit, tage, vorhanden["id"]))
            return {"ok": True, "id": vorhanden["id"], "name": name, "uhrzeit": zeit,
                    "ersetzt": True,
                    "text": "Die Routine %s ist aktualisiert.%s"
                            % (name, (" Sie läuft künftig um %s." % zeit) if zeit else "")}

        nummer = self.memory._schreiben(
            "INSERT INTO routinen (name, anweisung, uhrzeit, tage, aktiv, zuletzt, laeufe, "
            "angelegt) VALUES (?,?,?,?,1,'',0,?)",
            (name, anweisung, zeit, tage, zeitstempel()))
        return {"ok": True, "id": nummer, "name": name, "uhrzeit": zeit, "ersetzt": False,
                "text": "Routine %s angelegt.%s"
                        % (name, (" Sie läuft täglich um %s." % zeit) if zeit
                           else " Sag einfach ihren Namen, dann führe ich sie aus.")}

    def routine_loeschen(self, name: str) -> dict:
        """Löscht eine Routine - auch bei ungenauem Namen."""
        treffer = self.routine_finden(name)
        if not treffer:
            return {"ok": False, "fehler": "Eine Routine namens '%s' kenne ich nicht." % name}
        self.memory._schreiben("DELETE FROM routinen WHERE id=?", (treffer["id"],))
        return {"ok": True, "text": "Die Routine %s ist gelöscht." % treffer["name"]}

    def routinen_liste(self, nur_aktive: bool = True) -> list:
        """Alle Routinen."""
        wo = "WHERE aktiv=1" if nur_aktive else ""
        return self.memory._lesen("SELECT * FROM routinen %s ORDER BY name" % wo)

    def geplante_routinen(self) -> list:
        """Routinen mit Uhrzeit - genau die hängen sich in den Zeitplan."""
        return self.memory._lesen(
            "SELECT * FROM routinen WHERE aktiv=1 AND uhrzeit<>'' ORDER BY uhrzeit")

    # -- Suchen -------------------------------------------------------------

    def _exakt(self, name: str):
        """Stufe 1: der normalisierte Name stimmt genau überein."""
        gesucht = name_normalisieren(name)
        for zeile in self.memory._lesen("SELECT * FROM routinen"):
            if name_normalisieren(zeile["name"]) == gesucht:
                return zeile
        return None

    def routine_finden(self, name: str):
        """Findet eine Routine dreistufig: exakt, Teiltreffer, einzelne Wörter.

        Damit findet 'den Tages Bericht' die Routine 'tagesbericht'.
        """
        if not name or not str(name).strip():
            return None
        alle = self.memory._lesen("SELECT * FROM routinen WHERE aktiv=1")
        if not alle:
            return None

        gesucht = name_normalisieren(name)
        gesucht_kompakt = name_kompakt(name)

        # Stufe 1: exakt
        for zeile in alle:
            if name_normalisieren(zeile["name"]) == gesucht:
                return zeile

        # Stufe 2: Teiltreffer, auch ohne Leerzeichen ("dentagesbericht" enthält
        # "tagesbericht")
        beste, bestwert = None, 0
        for zeile in alle:
            kompakt = name_kompakt(zeile["name"])
            if not kompakt:
                continue
            if kompakt in gesucht_kompakt or gesucht_kompakt in kompakt:
                wert = len(kompakt)
                if wert > bestwert:
                    beste, bestwert = zeile, wert
        if beste is not None:
            return beste

        # Stufe 3: einzelne Wörter ab 4 Zeichen
        woerter = [w for w in gesucht.split() if len(w) >= 4]
        if not woerter:
            return None
        beste, bestwert = None, 0
        for zeile in alle:
            kompakt = name_kompakt(zeile["name"])
            treffer = sum(1 for wort in woerter if wort in kompakt)
            if treffer > bestwert:
                beste, bestwert = zeile, treffer
        return beste if bestwert > 0 else None

    # -- Ausführen ----------------------------------------------------------

    def routine_ausfuehren(self, name: str, agent=None) -> dict:
        """Übergibt die Anweisung der Routine an Claude - er entscheidet das Wie."""
        treffer = self.routine_finden(name)
        if not treffer:
            vorhandene = ", ".join(z["name"] for z in self.routinen_liste()) or "keine"
            return {"ok": False,
                    "fehler": "Eine Routine namens '%s' kenne ich nicht. Ich habe: %s."
                              % (name, vorhandene)}

        self.memory._schreiben(
            "UPDATE routinen SET zuletzt=?, laeufe=laeufe+1 WHERE id=?",
            (zeitstempel(), treffer["id"]))

        if agent is None or not getattr(agent, "einsatzbereit", lambda: False)():
            return {"ok": False, "name": treffer["name"], "anweisung": treffer["anweisung"],
                    "fehler": "Ohne eingerichtetes Gehirn kann ich die Routine %s nicht "
                              "ausführen." % treffer["name"]}

        auftrag = ("Führe jetzt die gespeicherte Routine '%s' aus. Das ist die Anweisung:\n\n%s\n\n"
                   "Nutze dafür deine Werkzeuge und melde am Ende kurz, was du getan hast."
                   % (treffer["name"], treffer["anweisung"]))
        antwort = agent.denken(auftrag, protokollieren=False)
        return {"ok": True, "name": treffer["name"], "text": antwort}

    def statistik(self) -> dict:
        """Wie viele Routinen es gibt und welche geplant sind."""
        alle = self.routinen_liste()
        geplant = self.geplante_routinen()
        return {"anzahl": len(alle), "geplant": len(geplant),
                "namen": [z["name"] for z in alle],
                "zeiten": {z["name"]: z["uhrzeit"] for z in geplant}}


# =========================================================================
# camera  -  Kamera - ein Einzelbild aufnehmen und von Claude beschreiben lassen.
# 
# Damit sieht Jarvis den Nutzer, einen vorgehaltenen Beleg oder ein Objekt.
# 
# **Ehrliche Grenze:** Das ist ein Einzelbild auf Zuruf. Kein Dauervideo, keine
# Überwachung, keine Aufzeichnung im Hintergrund. Das Bild wird nach der
# Auswertung gelöscht, außer der Nutzer will es ausdrücklich behalten.
# 
# Das Kamera-Recht muss dem Terminal unter Systemeinstellungen, Datenschutz,
# Kamera erteilt sein. Die Ersteinrichtung weist darauf hin.
# =========================================================================

#!/usr/bin/env python3
# -*- coding: utf-8 -*-




class Kamera:
    """Nimmt Einzelbilder auf und lässt sie von Claude beschreiben."""

    def __init__(self):
        self.letzter_fehler = ""

    # -- Verfügbarkeit ------------------------------------------------------

    @staticmethod
    def werkzeug_vorhanden() -> str:
        """Welches Aufnahmeprogramm ist da? ``imagesnap``, ``ffmpeg`` oder nichts."""
        if shutil.which("imagesnap"):
            return "imagesnap"
        if shutil.which("ffmpeg"):
            return "ffmpeg"
        return ""

    def verfuegbar(self) -> bool:
        """Kann überhaupt ein Bild aufgenommen werden?"""
        return bool(self.werkzeug_vorhanden())

    def zustand(self) -> dict:
        """Kurzer Überblick für den Selbsttest."""
        return {"programm": self.werkzeug_vorhanden() or "keines",
                "verfuegbar": self.verfuegbar()}

    # -- Aufnahme -----------------------------------------------------------

    def bild_aufnehmen(self, ziel: str = "") -> dict:
        """Nimmt ein Einzelbild der eingebauten Kamera auf."""
        programm = self.werkzeug_vorhanden()
        if not programm:
            self.letzter_fehler = (
                "Ich sehe über die Kamera im Browser: Sag einfach 'schau mal' oder "
                "'was siehst du' im Jarvis-Fenster, dann mache ich ein Bild.")
            return {"ok": False, "fehler": self.letzter_fehler}

        try:
            BELEGE_VERZEICHNIS.mkdir(parents=True, exist_ok=True)
        except OSError:
            pass
        ziel = ziel or str(BELEGE_VERZEICHNIS /
                           ("kamera_%d.jpg" % int(time.time())))

        if programm == "imagesnap":
            # -w wartet kurz, damit sich die Kamera an das Licht anpassen kann.
            befehl = ["imagesnap", "-q", "-w", "1", ziel]
        else:
            befehl = ["ffmpeg", "-y", "-f", "avfoundation", "-framerate", "30",
                      "-video_size", "1280x720", "-i", "0", "-frames:v", "1", ziel]

        try:
            ergebnis = subprocess.run(befehl, capture_output=True, timeout=30, shell=False)
        except subprocess.TimeoutExpired:
            self.letzter_fehler = "Die Kamera hat nicht rechtzeitig geantwortet."
            return {"ok": False, "fehler": self.letzter_fehler}
        except (OSError, subprocess.SubprocessError) as fehler:
            self.letzter_fehler = "Die Aufnahme ist fehlgeschlagen: %s" % fehler
            return {"ok": False, "fehler": self.letzter_fehler}

        if not os.path.exists(ziel) or os.path.getsize(ziel) < 1000:
            fehlertext = (ergebnis.stderr or b"").decode("utf-8", errors="replace")[-300:]
            self.letzter_fehler = (
                "Es ist kein Bild entstanden. Meist fehlt das Kamera-Recht: "
                "Systemeinstellungen, Datenschutz und Sicherheit, Kamera - dort das "
                "Terminal erlauben und das Terminal neu starten. %s" % fehlertext)
            return {"ok": False, "fehler": self.letzter_fehler}
        return {"ok": True, "pfad": ziel}

    # -- Umschauen ----------------------------------------------------------

    def umschauen(self, frage: str = "", agent=None, behalten: bool = False) -> dict:
        """Nimmt ein Bild auf und beschreibt, was darauf zu sehen ist."""
        aufnahme = self.bild_aufnehmen()
        if not aufnahme.get("ok"):
            return aufnahme
        pfad = aufnahme["pfad"]

        if agent is None or not getattr(agent, "einsatzbereit", lambda: False)():
            if not behalten:
                self._aufraeumen(pfad)
            return {"ok": False,
                    "fehler": "Ich habe ein Bild gemacht, kann es ohne Anthropic-Schlüssel "
                              "aber nicht auswerten."}

        try:
            with open(pfad, "rb") as datei:
                rohbild = base64.b64encode(datei.read()).decode("ascii")
        except OSError as fehler:
            self._aufraeumen(pfad)
            return {"ok": False, "fehler": "Das Bild ist nicht lesbar: %s" % fehler}

        auftrag = (frage or "Was ist auf diesem Bild zu sehen?").strip()
        auftrag += ("\n\nAntworte in zwei bis vier Sätzen, gesprochen, ohne Aufzählungen. "
                    "Beschreibe nur, was wirklich zu sehen ist. Bist du dir bei etwas "
                    "nicht sicher, sag das.")
        antwort = agent.text_anfrage(auftrag, bild_base64=rohbild, bild_typ="image/jpeg")

        if not behalten:
            self._aufraeumen(pfad)
        if not antwort.get("ok"):
            return {"ok": False, "fehler": antwort.get("fehler", "Auswertung fehlgeschlagen.")}
        return {"ok": True, "text": antwort["text"],
                "bild": pfad if behalten else "", "behalten": behalten}

    @staticmethod
    def _aufraeumen(pfad: str):
        """Löscht das Bild nach der Auswertung."""
        try:
            if pfad and os.path.exists(pfad):
                os.remove(pfad)
        except OSError:
            pass


# =========================================================================
# mcp_client  -  MCP - fertige Dienste einbinden, statt jede Anbindung selbst zu programmieren.
# 
# Ein MCP-Server ist ein eigener Prozess, der über stdin und stdout JSON-RPC
# spricht. Der Ablauf ist immer derselbe::
# 
#     initialize -> notifications/initialized -> tools/list -> tools/call
# 
# Seine Werkzeuge landen als ``mcp__<server>__<werkzeug>`` im Katalog, damit
# Claude sie neben den eigenen sieht.
# 
# **Freigabe umgekehrt als bei den eigenen Werkzeugen:** MCP-Werkzeuge brauchen
# *standardmäßig* eine Freigabe. Nur was ausdrücklich unter ``ohne_rueckfrage``
# steht (lesen, suchen, auflisten), läuft durch. Andersherum könnte ein frisch
# angesteckter Server beim allerersten Aufruf löschen oder versenden, ohne dass je
# gefragt wurde.
# =========================================================================

#!/usr/bin/env python3
# -*- coding: utf-8 -*-



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
                          str(BASIS)],
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
    ziel = str(pfad or MCP_DATEI)
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
        self.konfig_pfad = str(konfig_pfad or MCP_DATEI)
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


# =========================================================================
# netz  -  Netz - Webseiten lesen und im Web suchen, ohne Zusatzprogramme.
# 
# Bisher konnte Jarvis Seiten nur über Playwright samt eigenem Chromium lesen
# und nur mit einem Brave-Schlüssel suchen. Fehlt beides - und auf einem
# normalen Mac fehlt es -, konnte er gar nichts lesen. Dieses Modul braucht nur
# Python:
# 
# * **Seite lesen**: Die Seite wird geholt und in Klartext zerlegt - Titel,
#   Überschriften, Absätze, dazu Links, Mailadressen und Telefonnummern.
#   Skripte, Menüs und Fußzeilen fliegen raus.
# * **Suchen**: der Reihe nach über den Such-Dienst (falls eingerichtet), die
#   Google-Suche des Gemini-Schlüssels (falls Kontingent da ist), DuckDuckGo und
#   Mojeek. Der erste Weg, der Ergebnisse liefert, gewinnt.
# 
# **Sicherheit.** Gelesen wird nur http und https, nie eine Adresse im eigenen
# Netz (127.0.0.1, 192.168.x.x ...). Sonst könnte eine fremde Seite Jarvis
# anweisen, die eigene Schnittstelle oder den Router abzufragen. Sehr lange
# Adressen werden abgelehnt: Über die Adresse ließen sich sonst Daten nach
# draußen schmuggeln ("lies https://fremd.example/?d=<Inhalt einer Datei>").
# =========================================================================

#!/usr/bin/env python3
# -*- coding: utf-8 -*-



BROWSER_KENNUNG = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 "
                   "(KHTML, like Gecko) Version/17.0 Safari/605.1.15")
MAX_ADRESSE = 400
MAX_BYTES = 2 * 1024 * 1024
MAX_SEITENTEXT = 6000

UEBERSPRINGEN = {"script", "style", "noscript", "svg", "template", "iframe", "canvas",
                 "nav", "footer", "form", "button", "select", "option"}
BLOCK = {"p", "div", "section", "article", "main", "li", "tr", "td", "th", "br",
         "h1", "h2", "h3", "h4", "h5", "h6", "dd", "dt", "blockquote", "pre",
         "address", "figcaption", "header", "table", "ul", "ol"}

MAIL_MUSTER = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
TELEFON_MUSTER = re.compile(r"(?:\+|00)\d{2}[\d\s/().-]{6,}\d|\b0\d{2,4}[\s/-]?\d[\d\s/-]{4,}\d")


class _Zerleger(HTMLParser):
    """Zerlegt HTML in lesbaren Text, Links und Kontaktdaten."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.titel = ""
        self.beschreibung = ""
        self.teile = []
        self.links = []
        self.mails = set()
        self.telefone = set()
        self._tiefe_aus = 0
        self._im_titel = False
        self._link = None

    def handle_starttag(self, tag, attrs):
        werte = dict(attrs)
        if tag in UEBERSPRINGEN:
            self._tiefe_aus += 1
            return
        if tag == "title":
            self._im_titel = True
        elif tag == "meta" and (werte.get("name") or werte.get("property") or "").lower() in (
                "description", "og:description"):
            self.beschreibung = self.beschreibung or (werte.get("content") or "").strip()
        elif tag == "a":
            ziel = (werte.get("href") or "").strip()
            if ziel.lower().startswith("mailto:"):
                self.mails.add(ziel[7:].split("?")[0])
            elif ziel.lower().startswith("tel:"):
                self.telefone.add(urllib.parse.unquote(ziel[4:]).strip())
            elif ziel and not ziel.startswith(("#", "javascript:")):
                self._link = [ziel, ""]
        if tag in BLOCK:
            self.teile.append("\n")
        if tag in ("h1", "h2", "h3"):
            self.teile.append("## ")

    def handle_endtag(self, tag):
        if tag in UEBERSPRINGEN:
            self._tiefe_aus = max(0, self._tiefe_aus - 1)
            return
        if tag == "title":
            self._im_titel = False
        elif tag == "a" and self._link is not None:
            if self._link[1].strip():
                self.links.append((self._link[0], " ".join(self._link[1].split())[:80]))
            self._link = None
        if tag in BLOCK:
            self.teile.append("\n")

    def handle_data(self, daten):
        if self._im_titel:
            self.titel += daten
            return
        if self._tiefe_aus:
            return
        self.teile.append(daten)
        if self._link is not None:
            self._link[1] += daten

    def text(self) -> str:
        roh = "".join(self.teile)
        zeilen = []
        for zeile in roh.split("\n"):
            zeile = " ".join(zeile.split())
            if len(zeile) > 1 and (not zeilen or zeilen[-1] != zeile):
                zeilen.append(zeile)
        return "\n".join(zeilen)


def adresse_pruefen_netz(adresse: str):
    """Gibt ``(adresse, fehler)`` zurück. Nur http/https, nichts im eigenen Netz."""
    roh = (adresse or "").strip()
    if not roh:
        return None, "Es fehlt die Adresse."
    if len(roh) > MAX_ADRESSE:
        return None, "Die Adresse ist ungewöhnlich lang - das öffne ich nicht."
    if not re.match(r"^[a-z][a-z0-9+.-]*://", roh, re.I):
        roh = "https://" + roh.lstrip("/")
    teile = urllib.parse.urlsplit(roh)
    if teile.scheme.lower() not in ("http", "https") or not teile.hostname:
        return None, "Ich lese nur Web-Adressen mit http oder https."
    host = teile.hostname.lower()
    # Umlaute in Pfad und Domain: so umschreiben, wie Browser es tun.
    try:
        netzort = host.encode("idna").decode("ascii")
    except UnicodeError:
        return None, "Die Adresse %s ergibt keinen Sinn." % host
    if teile.port:
        netzort += ":%d" % teile.port
    roh = urllib.parse.urlunsplit((
        teile.scheme.lower(), netzort,
        urllib.parse.quote(teile.path, safe="/%:@!$&'()*+,;=-._~"),
        urllib.parse.quote(teile.query, safe="/%:@!$&'()*+,;=-._~?"), ""))
    if host in ("localhost",) or host.endswith((".local", ".localhost", ".internal")):
        return None, "Adressen im eigenen Netz lese ich nicht."
    try:
        for eintrag in socket.getaddrinfo(host, None):
            ip = ipaddress.ip_address(eintrag[4][0])
            if (ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved
                    or ip.is_multicast or ip.is_unspecified):
                return None, "Adressen im eigenen Netz lese ich nicht."
    except (socket.gaierror, ValueError, OSError):
        return None, "Die Adresse %s gibt es nicht (oder kein Internet)." % host
    return roh, ""


class _GepruefteWeiterleitung(urllib.request.HTTPRedirectHandler):
    """Prüft jedes Weiterleitungsziel - sonst lenkt eine Seite auf 127.0.0.1 um."""

    def redirect_request(self, anfrage, datei, code, meldung, koepfe, neue_adresse):
        _, fehler = adresse_pruefen_netz(neue_adresse)
        if fehler:
            raise urllib.error.URLError("Weiterleitung abgelehnt: %s" % fehler)
        return super().redirect_request(anfrage, datei, code, meldung, koepfe, neue_adresse)


_OEFFNER = urllib.request.build_opener(_GepruefteWeiterleitung)


def _holen_netz(adresse: str, timeout: int = 20) -> dict:
    anfrage = urllib.request.Request(adresse, headers={
        "User-Agent": BROWSER_KENNUNG, "Accept-Language": "de-AT,de;q=0.9,en;q=0.6",
        "Accept": "text/html,application/xhtml+xml,text/plain;q=0.9,*/*;q=0.5"})
    try:
        with _OEFFNER.open(anfrage, timeout=timeout) as antwort:
            typ = antwort.headers.get("Content-Type", "")
            roh = antwort.read(MAX_BYTES)
            ziel = antwort.geturl()
    except urllib.error.HTTPError as fehler:
        return {"ok": False, "code": fehler.code,
                "fehler": "Die Seite antwortet mit Fehler %d%s." % (
                    fehler.code, " - sie lässt automatische Besucher nicht herein"
                    if fehler.code in (401, 403, 429) else "")}
    except (urllib.error.URLError, OSError, ValueError) as fehler:
        return {"ok": False, "code": 0, "fehler": "Die Seite ist nicht erreichbar: %s" % fehler}
    zeichensatz = "utf-8"
    treffer = re.search(r"charset=([\w-]+)", typ, re.I) or \
        re.search(rb'<meta[^>]+charset=["\']?([\w-]+)', roh[:4000], re.I)
    if treffer:
        gefunden = treffer.group(1)
        zeichensatz = gefunden.decode("ascii", "ignore") if isinstance(gefunden, bytes) \
            else gefunden
    try:
        text = roh.decode(zeichensatz, errors="replace")
    except LookupError:
        text = roh.decode("utf-8", errors="replace")
    return {"ok": True, "typ": typ.lower(), "inhalt": text, "adresse": ziel}


def seite_zerlegen(quelltext: str, basis: str = "") -> dict:
    """Macht aus HTML lesbaren Text samt Links und Kontaktdaten."""
    zerleger = _Zerleger()
    try:
        zerleger.feed(quelltext)
        zerleger.close()
    except Exception:
        pass
    text = zerleger.text()
    mails = set(zerleger.mails) | set(MAIL_MUSTER.findall(text))
    mails = sorted(m for m in mails if not m.lower().endswith((".png", ".jpg", ".gif",
                                                                ".webp", ".svg")))
    telefone = set(zerleger.telefone)
    for treffer in TELEFON_MUSTER.findall(text):
        if 8 <= len(re.sub(r"\D", "", treffer)) <= 15:
            telefone.add(" ".join(treffer.split()))
    links, gesehen = [], set()
    for ziel, beschriftung in zerleger.links:
        absolut = urllib.parse.urljoin(basis, ziel) if basis else ziel
        if absolut.startswith("http") and absolut not in gesehen:
            gesehen.add(absolut)
            links.append({"text": beschriftung, "adresse": absolut})
    return {"titel": " ".join(zerleger.titel.split()), "beschreibung": zerleger.beschreibung,
            "text": text, "links": links, "mails": mails[:10], "telefone": sorted(telefone)[:10]}


def webseite_lesen(adresse: str, frage: str = "") -> dict:
    """Liest eine Webseite und gibt ihren Inhalt als Text zurück."""
    adresse, fehler = adresse_pruefen_netz(adresse)
    if fehler:
        return {"ok": False, "fehler": fehler}
    geholt = _holen_netz(adresse)
    if not geholt["ok"]:
        return {"ok": False, "fehler": geholt["fehler"]}
    if "pdf" in geholt["typ"]:
        return {"ok": False, "fehler": "Das ist ein PDF. PDFs aus dem Netz lese ich noch nicht."}
    if "html" in geholt["typ"] or "<html" in geholt["inhalt"][:2000].lower():
        teile = seite_zerlegen(geholt["inhalt"], geholt["adresse"])
    else:
        teile = {"titel": "", "beschreibung": "", "text": geholt["inhalt"], "links": [],
                 "mails": sorted(set(MAIL_MUSTER.findall(geholt["inhalt"])))[:10],
                 "telefone": []}
    text = teile["text"]
    frage = (frage or "").strip().lower()
    if frage and len(text) > MAX_SEITENTEXT:
        # Bei langen Seiten zuerst die Absätze, in denen die Frage vorkommt.
        woerter = [w for w in re.findall(r"\w{4,}", frage)]
        absaetze = text.split("\n")
        passend = [a for a in absaetze if any(w in a.lower() for w in woerter)]
        text = "\n".join(passend[:40]) + "\n---\n" + text
    gekuerzt = len(text) > MAX_SEITENTEXT
    text = text[:MAX_SEITENTEXT]
    if not text.strip() and not teile["beschreibung"]:
        return {"ok": False, "fehler": "Die Seite liefert keinen lesbaren Text - sie baut "
                                       "sich vermutlich erst im Browser zusammen."}
    return {"ok": True, "adresse": geholt["adresse"], "titel": teile["titel"],
            "beschreibung": teile["beschreibung"][:300], "inhalt": text,
            "gekuerzt": gekuerzt, "mails": teile["mails"], "telefone": teile["telefone"],
            "links": teile["links"][:25],
            "text": "Seite gelesen: %s%s" % (teile["titel"] or geholt["adresse"],
                                             " (gekürzt)" if gekuerzt else "")}


# -- Suche ---------------------------------------------------------------------

def _ddg_zerlegen(quelltext: str) -> list:
    """Treffer aus der HTML-Ansicht von DuckDuckGo."""
    treffer = []
    for block in re.findall(r'<div class="result[^"]*results_links.*?</div>\s*</div>',
                            quelltext, re.S)[:12] or [quelltext]:
        for ziel, titel in re.findall(r'class="result__a"[^>]*href="([^"]+)"[^>]*>(.*?)</a>',
                                      block, re.S):
            auszug = re.search(r'class="result__snippet"[^>]*>(.*?)</a>', block, re.S)
            if "uddg=" in ziel:
                ziel = urllib.parse.unquote(re.search(r"uddg=([^&]+)", ziel).group(1))
            treffer.append({"titel": _ohne_tags(titel), "adresse": html.unescape(ziel),
                            "auszug": _ohne_tags(auszug.group(1)) if auszug else ""})
    eindeutig, gesehen = [], set()
    for eintrag in treffer:
        if eintrag["adresse"] not in gesehen and eintrag["adresse"].startswith("http"):
            gesehen.add(eintrag["adresse"])
            eindeutig.append(eintrag)
    return eindeutig


def _mojeek_zerlegen(quelltext: str) -> list:
    treffer = []
    for ziel, titel in re.findall(r'<a class="title" href="([^"]+)"[^>]*>(.*?)</a>',
                                  quelltext, re.S):
        treffer.append({"titel": _ohne_tags(titel), "adresse": html.unescape(ziel), "auszug": ""})
    auszuege = re.findall(r'<p class="s">(.*?)</p>', quelltext, re.S)
    for eintrag, auszug in zip(treffer, auszuege):
        eintrag["auszug"] = _ohne_tags(auszug)
    return treffer


def _ohne_tags(text: str) -> str:
    return " ".join(html.unescape(re.sub(r"<[^>]+>", " ", text or "")).split())


def _gemini_suche(frage: str) -> dict:
    """Google-Suche über den Gemini-Schlüssel, falls einer eingerichtet ist."""
    if "generativelanguage.googleapis.com" not in (FREIER_DIENST_URL or "") \
            or not FREIER_DIENST_SCHLUESSEL:
        return {"ok": False, "fehler": "kein Gemini-Schlüssel"}
    modell = (FREIER_DIENST_MODELL or "gemini-flash-lite-latest").split(",")[0].strip()
    nutzlast = {"contents": [{"parts": [{"text": frage + "\nAntworte knapp auf Deutsch, "
                                                     "mit Namen, Adressen und Nummern, "
                                                     "soweit gefunden."}]}],
                "tools": [{"google_search": {}}]}
    anfrage = urllib.request.Request(
        "https://generativelanguage.googleapis.com/v1beta/models/%s:generateContent" % modell,
        data=json.dumps(nutzlast).encode("utf-8"), method="POST",
        headers={"x-goog-api-key": FREIER_DIENST_SCHLUESSEL,
                 "Content-Type": "application/json", "User-Agent": "Jarvis/1.0"})
    try:
        with urllib.request.urlopen(anfrage, timeout=40) as antwort:
            daten = json.loads(antwort.read().decode("utf-8"))
    except (urllib.error.URLError, OSError, ValueError) as fehler:
        return {"ok": False, "fehler": "Google-Suche: %s" % fehler}
    if isinstance(daten, list):
        daten = daten[0] if daten else {}
    kandidat = (daten.get("candidates") or [{}])[0]
    text = "".join(t.get("text", "") for t in (kandidat.get("content") or {}).get("parts", []))
    quellen = [{"titel": (c.get("web") or {}).get("title", ""),
                "adresse": (c.get("web") or {}).get("uri", ""), "auszug": ""}
               for c in (kandidat.get("groundingMetadata") or {}).get("groundingChunks", [])]
    if not text.strip():
        return {"ok": False, "fehler": "Google-Suche ohne Ergebnis"}
    return {"ok": True, "weg": "Google (Gemini)", "zusammenfassung": text.strip(),
            "treffer": quellen[:8]}


def websuche(frage: str, anzahl: int = 6, such_mcp=None) -> dict:
    """Sucht im Web - der erste Weg, der Ergebnisse liefert, gewinnt."""
    frage = (frage or "").strip()
    if not frage:
        return {"ok": False, "fehler": "Sag mir, wonach ich suchen soll."}
    gruende = []
    if such_mcp is not None:
        ergebnis = such_mcp(frage)
        if ergebnis.get("ok"):
            return {"ok": True, "weg": "Such-Dienst", "zusammenfassung": ergebnis["text"],
                    "treffer": []}
        gruende.append("Such-Dienst: %s" % ergebnis.get("fehler", "")[:60])

    ergebnis = _gemini_suche(frage)
    if ergebnis.get("ok"):
        return ergebnis
    gruende.append(ergebnis.get("fehler", "")[:60])

    for name, adresse, zerlegen in (
            ("DuckDuckGo", "https://html.duckduckgo.com/html/?q=%s", _ddg_zerlegen),
            ("Mojeek", "https://www.mojeek.com/search?q=%s", _mojeek_zerlegen)):
        geholt = _holen_netz(adresse % urllib.parse.quote_plus(frage), timeout=15)
        if not geholt["ok"]:
            gruende.append("%s: %s" % (name, geholt["fehler"][:50]))
            continue
        treffer = zerlegen(geholt["inhalt"])
        if treffer:
            return {"ok": True, "weg": name, "zusammenfassung": "", "treffer": treffer[:anzahl]}
        gruende.append("%s: keine Treffer (vielleicht gesperrt)" % name)
    return {"ok": False, "fehler": "Die Suche hat gerade keinen Weg gefunden. " +
                                   "; ".join(g for g in gruende if g)}


def suche_als_text(ergebnis: dict) -> str:
    """Macht aus einem Suchergebnis einen Text für das Gehirn."""
    zeilen = []
    if ergebnis.get("zusammenfassung"):
        zeilen.append(ergebnis["zusammenfassung"][:3000])
    for nummer, eintrag in enumerate(ergebnis.get("treffer") or [], 1):
        zeilen.append("%d. %s - %s%s" % (nummer, eintrag["titel"], eintrag["adresse"],
                                         ("\n   " + eintrag["auszug"][:240])
                                         if eintrag.get("auszug") else ""))
    return "\n".join(zeilen)


# =========================================================================
# world  -  Welt - echtes Wetter und Recherche.
# 
# Das Wetter kommt von Open-Meteo: kostenlos, ohne Schlüssel, ohne Anmeldung.
# Zuerst wird der Ortsname in Koordinaten übersetzt, dann die Vorhersage geholt.
# 
# Recherche und Flugsuche laufen über einen Such-MCP (Brave). **Flüge werden
# gefunden und genannt, nie gebucht.** Das Buchen läuft danach über die
# Bildschirmsteuerung mit ausdrücklicher Freigabe - niemals heimlich.
# =========================================================================

#!/usr/bin/env python3
# -*- coding: utf-8 -*-



GEO_URL = "https://geocoding-api.open-meteo.com/v1/search"
WETTER_URL = "https://api.open-meteo.com/v1/forecast"

# WMO-Wettercodes in verständliches Deutsch.
WETTERLAGE = {
    0: "klar", 1: "überwiegend klar", 2: "teilweise bewölkt", 3: "bedeckt",
    45: "neblig", 48: "Nebel mit Reifbildung",
    51: "leichter Nieselregen", 53: "Nieselregen", 55: "starker Nieselregen",
    56: "gefrierender Nieselregen", 57: "starker gefrierender Nieselregen",
    61: "leichter Regen", 63: "Regen", 65: "starker Regen",
    66: "gefrierender Regen", 67: "starker gefrierender Regen",
    71: "leichter Schneefall", 73: "Schneefall", 75: "starker Schneefall",
    77: "Schneekörner", 80: "leichte Regenschauer", 81: "Regenschauer",
    82: "heftige Regenschauer", 85: "Schneeschauer", 86: "starke Schneeschauer",
    95: "Gewitter", 96: "Gewitter mit Hagel", 99: "schweres Gewitter mit Hagel",
}


def _holen_world(url: str, parameter: dict, timeout: int = 20, versuche: int = 3):
    """Holt JSON von einer Adresse.

    Ein einzelner Verbindungsabbruch - unterwegs im Auto oder im WLAN eines
    Kunden keine Seltenheit - soll nicht gleich als "kein Wetter" beim Nutzer
    ankommen. Deshalb wird mit wachsendem Abstand nachgefasst.
    """
    ziel = "%s?%s" % (url, urllib.parse.urlencode(parameter))
    letzter_fehler = "unbekannt"
    for versuch in range(max(1, versuche)):
        try:
            anfrage = urllib.request.Request(ziel, headers={"User-Agent": "Jarvis/1.0"})
            with urllib.request.urlopen(anfrage, timeout=timeout) as antwort:
                return json.loads(antwort.read().decode("utf-8")), ""
        except urllib.error.HTTPError as fehler:
            return None, "Der Wetterdienst antwortet mit Fehler %d." % fehler.code
        except (urllib.error.URLError, OSError, ValueError) as fehler:
            letzter_fehler = str(fehler)
            if versuch + 1 < max(1, versuche):
                time.sleep(1.5 * (versuch + 1))
    return None, "Der Wetterdienst ist nicht erreichbar: %s" % letzter_fehler


class Welt:
    """Wetter, Recherche und Flugsuche."""

    def __init__(self, mcp=None):
        self.mcp = mcp

    # -- Wetter -------------------------------------------------------------

    def ort_finden(self, ort: str):
        """Übersetzt einen Ortsnamen in Koordinaten."""
        daten, fehler = _holen_world(GEO_URL, {"name": ort, "count": 1,
                                         "language": "de", "format": "json"})
        if daten is None:
            return None, fehler
        treffer = (daten or {}).get("results") or []
        if not treffer:
            return None, "Den Ort '%s' finde ich nicht." % ort
        erster = treffer[0]
        return {"name": erster.get("name", ort),
                "land": erster.get("country", ""),
                "breite": erster.get("latitude"),
                "laenge": erster.get("longitude")}, ""

    def wetter(self, ort: str = "") -> dict:
        """Aktuelles Wetter und die nächsten zwei Tage - als gesprochener Satz."""
        ort = (ort or WETTER_ORT or "Wien").strip()
        koordinaten, fehler = self.ort_finden(ort)
        if koordinaten is None:
            return {"ok": False, "fehler": fehler}

        daten, fehler = _holen_world(WETTER_URL, {
            "latitude": koordinaten["breite"], "longitude": koordinaten["laenge"],
            "current": "temperature_2m,weather_code,wind_speed_10m,relative_humidity_2m",
            "daily": "temperature_2m_max,temperature_2m_min,weather_code,"
                     "precipitation_probability_max",
            "timezone": "auto", "forecast_days": 3})
        if daten is None:
            return {"ok": False, "fehler": fehler}

        jetzt = daten.get("current") or {}
        taeglich = daten.get("daily") or {}
        lage = WETTERLAGE.get(int(jetzt.get("weather_code") or 0), "wechselhaft")
        temperatur = jetzt.get("temperature_2m")
        wind = jetzt.get("wind_speed_10m")

        satz = ("In %s ist es gerade %s bei %.0f Grad, Wind %.0f Kilometer pro Stunde."
                % (koordinaten["name"], lage, float(temperatur or 0), float(wind or 0)))

        tage = []
        namen = ["Heute", "Morgen", "Übermorgen"]
        for index in range(min(3, len(taeglich.get("time", []) or []))):
            hoch = (taeglich.get("temperature_2m_max") or [None])[index]
            tief = (taeglich.get("temperature_2m_min") or [None])[index]
            code = (taeglich.get("weather_code") or [0])[index]
            regen = (taeglich.get("precipitation_probability_max") or [0])[index]
            tage.append({"tag": namen[index] if index < 3 else taeglich["time"][index],
                         "hoch": hoch, "tief": tief,
                         "lage": WETTERLAGE.get(int(code or 0), "wechselhaft"),
                         "regenwahrscheinlichkeit": regen})
            if index <= 1:
                satz += (" %s %s, %.0f bis %.0f Grad, Regenwahrscheinlichkeit %d Prozent."
                         % (namen[index], WETTERLAGE.get(int(code or 0), "wechselhaft"),
                            float(tief or 0), float(hoch or 0), int(regen or 0)))

        # Für einen Gebäudereiniger ist Regen kein Nebenthema: Fensterreinigung
        # und Außenflächen fallen dann aus.
        regen_heute = (taeglich.get("precipitation_probability_max") or [0])[0]
        if regen_heute and int(regen_heute) >= 60:
            satz += " Bei der Regenwahrscheinlichkeit würde ich Fensterarbeiten verschieben."

        return {"ok": True, "ort": koordinaten["name"], "aktuell": jetzt,
                "tage": tage, "text": satz}

    # -- Recherche ----------------------------------------------------------

    def _such_werkzeug(self):
        """Sucht das passende Werkzeug des Such-MCP-Servers."""
        if self.mcp is None:
            return ""
        for werkzeug in self.mcp.alle_werkzeuge():
            name = werkzeug.get("name", "")
            if "search" in name.lower() and "local" not in name.lower():
                return name
        return ""

    def recherche(self, frage: str) -> dict:
        """Sucht im Web: Such-Dienst, Google über Gemini, DuckDuckGo, Mojeek.

        Früher ging das nur mit Brave-Schlüssel. Jetzt ist der Such-Dienst nur
        noch der erste von mehreren Wegen.
        """
        frage = (frage or "").strip()
        if not frage:
            return {"ok": False, "fehler": "Sag mir, wonach ich suchen soll."}
        such_mcp = None
        werkzeug = self._such_werkzeug()
        if werkzeug:
            def such_mcp(f):
                return self.mcp.aufrufen(werkzeug, {"query": f, "count": 6})
        ergebnis = websuche(frage, 6, such_mcp)
        if not ergebnis.get("ok"):
            return ergebnis
        return {"ok": True, "frage": frage, "weg": ergebnis["weg"],
                "treffer": ergebnis.get("treffer", []),
                "text": suche_als_text(ergebnis)[:4000]}

    def flug_suchen(self, von: str, nach: str, wann: str = "") -> dict:
        """Sucht Flugverbindungen und nennt sie. Gebucht wird hier nichts."""
        von, nach = (von or "").strip(), (nach or "").strip()
        if not von or not nach:
            return {"ok": False, "fehler": "Ich brauche Abflugort und Ziel."}
        anfrage = "Flug von %s nach %s%s Preise Fluggesellschaft Abflugzeit" % (
            von, nach, (" am %s" % wann) if wann else "")
        ergebnis = self.recherche(anfrage)
        if not ergebnis.get("ok"):
            return ergebnis
        return {"ok": True, "von": von, "nach": nach, "wann": wann,
                "gebucht": False,
                "text": ("Das habe ich zu Flügen von %s nach %s gefunden:\n%s\n\n"
                         "Gebucht ist nichts. Wenn du willst, buche ich über die "
                         "Bildschirmsteuerung - dafür fragst du mich noch einmal und "
                         "bestätigst jeden Schritt."
                         % (von, nach, ergebnis["text"][:2500]))}


# =========================================================================
# browser  -  Browser-Steuerung über das echte Seitengerüst.
# 
# Die Bildschirmsteuerung in ``computer_use`` klickt auf Pixel. Das geht bei
# einer Webseite regelmäßig daneben: ein Banner rutscht nach, die Seite lädt
# noch, das Fenster ist anders breit - und der Klick landet neben dem Knopf.
# 
# Hier wird stattdessen die Seite selbst gelesen. Jeder Knopf, jedes Feld und
# jeder Link hat eine Beschriftung, und geklickt wird auf die Beschriftung, nicht
# auf eine Koordinate. Das ist der Unterschied zwischen "klick bei 840, 512" und
# "klick auf 'Weiter zur Buchung'".
# 
# Playwright ist ein zusätzliches Paket. Fehlt es, sagt das Modul das im Klartext
# und alles andere läuft weiter.
# =========================================================================

#!/usr/bin/env python3
# -*- coding: utf-8 -*-




# Mehr Schritte braucht kein sinnvoller Vorgang, und die Bremse verhindert,
# dass sich der Agent in einer Seite verläuft und Geld verbrennt.
MAX_SCHRITTE_browser = 15

# Länge des Seitentexts, der an Claude geht. Ein vollständiges Portal hat
# schnell 200.000 Zeichen - davon sind die ersten paar tausend die, in denen
# der gesuchte Knopf steht.
MAX_TEXT = 4000
MAX_ELEMENTE = 60

# Nach diesen Beschriftungen wird nicht weitergeklickt, sondern gefragt.
HALTEPUNKTE = ["bezahlen", "kostenpflichtig", "kaufen", "jetzt buchen",
               "zahlungspflichtig", "abo abschliessen", "abo abschließen",
               "bestellung abschicken", "endgültig löschen", "konto löschen"]

# Beides - das Lesen und das Anfassen - muss exakt dieselbe Liste erzeugen,
# sonst zeigt Nummer 7 beim Klicken auf ein anderes Element als beim Lesen.
# Deshalb steht die Auswahl genau einmal hier und wird in beide Skripte
# eingesetzt, statt zweimal abgeschrieben zu werden.
SAMMEL_JS = """
  const sichtbar = (e) => {
    const r = e.getBoundingClientRect();
    if (r.width < 2 || r.height < 2) return false;
    const s = getComputedStyle(e);
    return s.visibility !== 'hidden' && s.display !== 'none' && s.opacity !== '0';
  };
  const beschriften = (e) => (
    e.getAttribute('aria-label') || e.getAttribute('placeholder') ||
    e.getAttribute('name') || e.getAttribute('title') ||
    e.getAttribute('value') || (e.innerText || '').trim() || ''
  ).replace(/\\s+/g, ' ').slice(0, 90);
  const artVon = (e) => {
    const tag = e.tagName.toLowerCase();
    const typ = (e.getAttribute('type') || '').toLowerCase();
    if (tag === 'a') return 'link';
    if (tag === 'select') return 'auswahl';
    if (tag === 'textarea') return 'feld';
    if (tag === 'input') {
      if (typ === 'submit' || typ === 'button') return 'knopf';
      if (typ === 'checkbox' || typ === 'radio') return 'haken';
      return 'feld';
    }
    return 'knopf';
  };
  const sammeln = () => {
    const auswahl = 'a[href], button, input, textarea, select, [role=button], [onclick]';
    const treffer = [];
    document.querySelectorAll(auswahl).forEach((e) => {
      if (!sichtbar(e) || e.disabled) return;
      if ((e.getAttribute('type') || '').toLowerCase() === 'hidden') return;
      if (!beschriften(e) && artVon(e) !== 'feld') return;
      treffer.push(e);
    });
    return treffer;
  };
"""

STEUER_PROMPT_browser = """Du bedienst eine Webseite. Du bekommst den Seitentext und eine
nummerierte Liste aller anklickbaren Elemente und Eingabefelder.

Antworte ausschließlich als JSON, ohne Fließtext:
{"gedanke": "was du siehst und warum", "aktion": "klicken", "ziel": 7, "text": ""}

Erlaubte Aktionen:
- "klicken"  - ziel ist die Nummer aus der Liste
- "tippen"   - ziel ist die Nummer eines Eingabefelds, text ist der Inhalt
- "auswaehlen" - ziel ist die Nummer einer Auswahlliste, text ist der Wert
- "oeffnen"  - text ist eine vollständige Adresse mit https://
- "warten"   - die Seite lädt noch
- "fertig"   - text ist das Ergebnis in einem Satz für den Nutzer
- "abbruch"  - text sagt, warum es nicht weitergeht

Regeln:
Du gibst nie ein Passwort ein und legst nie ein Konto an. Triffst du eine
Anmeldemaske, brichst du ab und sagst, dass der Nutzer sich selbst anmelden
muss.
Du schließt nie einen Kauf ab. Bis zur Übersicht vor dem Bezahlen darfst du
gehen, dann ist Schluss.
Du erfindest keine Daten. Fehlt dir eine Angabe, brichst du ab und fragst.
Ein Suchergebnis ist noch keine Buchung - sag klar, was du wirklich erreicht
hast."""


def adresse_pruefen_browser(adresse: str):
    """Prüft eine Adresse. Gibt ``(adresse, fehler)`` zurück."""
    roh = (adresse or "").strip()
    if not roh:
        return None, "Es fehlt die Adresse."
    schema = re.match(r"^([a-z][a-z0-9+.-]*):", roh, re.I)
    if schema and schema.group(1).lower() not in ("http", "https"):
        # file:// oder javascript: würde den Browser irgendwohin schicken, nur
        # nicht ins Netz. Ein fehlendes Schema wird ergänzt, ein falsches nicht
        # stillschweigend umgebogen.
        return None, ("'%s' ist keine Web-Adresse. Ich öffne nur http und https."
                      % (adresse or "")[:60])
    if not schema:
        roh = "https://" + roh.lstrip("/")
    if not re.match(r"^https?://[^\s/:]+(:\d+)?([/?#]|$)", roh, re.I):
        return None, "Die Adresse '%s' ergibt keinen Sinn." % (adresse or "")[:60]
    return roh, ""


def haltepunkt(beschriftung: str) -> str:
    """Nennt den Haltebegriff, wenn eine Beschriftung einen enthält."""
    text = (beschriftung or "").lower()
    for begriff in HALTEPUNKTE:
        if begriff in text:
            return begriff
    return ""


class Browser:
    """Ein echter Browser, der das Seitengerüst liest statt Pixel zu raten."""

    def __init__(self, agent=None, sichtbar: bool = True):
        self.agent = agent
        # Sichtbar ist Absicht: der Nutzer soll mitlesen, was passiert, und sich
        # bei Bedarf selbst anmelden. Unsichtbar läuft nur die Abnahme.
        self.sichtbar = sichtbar
        # Normalerweise nimmt Playwright sein eigenes Chromium. Wer schon einen
        # Chrome auf der Platte hat, trägt den Pfad in BROWSER_PROGRAMM ein.
        self.programm = (BROWSER_PROGRAMM or "").strip()
        self._spiel = None
        self._browser = None
        self._seite = None
        self.profil = BASIS / "browserprofil"

    # -- Zustand ------------------------------------------------------------

    @staticmethod
    def verfuegbar() -> bool:
        return sync_playwright is not None

    def zustand(self) -> dict:
        return {"verfuegbar": self.verfuegbar(),
                "offen": self._seite is not None,
                "adresse": self.adresse(),
                "hinweis": ("bereit" if self.verfuegbar() else
                            "Playwright fehlt: pip3 install playwright "
                            "und danach python3 -m playwright install chromium")}

    def adresse(self) -> str:
        try:
            return self._seite.url if self._seite is not None else ""
        except Exception:
            return ""

    def _fehlt(self) -> dict:
        return {"ok": False,
                "fehler": "Für die Browser-Steuerung fehlt das Paket playwright. "
                          "Im Terminal: pip3 install playwright, danach "
                          "python3 -m playwright install chromium."}

    # -- Start und Ende -----------------------------------------------------

    def _starten(self):
        """Startet den Browser beim ersten Bedarf.

        Das Profil bleibt auf der Platte, damit eine Anmeldung, die der Nutzer
        selbst vorgenommen hat, beim nächsten Mal noch steht. Sonst müsste er
        sich bei jedem Auftrag neu einloggen - und genau das soll er ja nicht.
        """
        if self._seite is not None:
            return None
        if not self.verfuegbar():
            return self._fehlt()
        try:
            self.profil.mkdir(parents=True, exist_ok=True)
            self._spiel = sync_playwright().start()
            self._browser = self._spiel.chromium.launch_persistent_context(
                user_data_dir=str(self.profil), headless=not self.sichtbar,
                viewport={"width": 1280, "height": 900},
                args=["--disable-blink-features=AutomationControlled"],
                **({"executable_path": self.programm} if self.programm else {}))
            self._seite = (self._browser.pages[0] if self._browser.pages
                           else self._browser.new_page())
            self._seite.set_default_timeout(15000)
            return None
        except Exception as fehler:
            self.schliessen()
            return {"ok": False,
                    "fehler": "Der Browser startet nicht: %s. Fehlt vielleicht "
                              "Chromium? Dann: python3 -m playwright install "
                              "chromium." % str(fehler)[:200]}

    def schliessen(self) -> dict:
        """Macht den Browser zu. Fehler dabei sind egal - Hauptsache zu."""
        for gegenstand, name in ((self._browser, "_browser"), (self._spiel, "_spiel")):
            if gegenstand is None:
                continue
            try:
                (gegenstand.close if name == "_browser" else gegenstand.stop)()
            except Exception:
                pass
        self._spiel = self._browser = self._seite = None
        return {"ok": True, "text": "Der Browser ist zu."}

    # -- Lesen --------------------------------------------------------------

    def oeffnen(self, adresse: str) -> dict:
        """Öffnet eine Adresse und liest die Seite."""
        ziel, fehler = adresse_pruefen_browser(adresse)
        if ziel is None:
            return {"ok": False, "fehler": fehler}
        problem = self._starten()
        if problem:
            return problem
        try:
            self._seite.goto(ziel, wait_until="domcontentloaded", timeout=30000)
        except Exception as fehler:
            return {"ok": False,
                    "fehler": "Die Seite %s lädt nicht: %s" % (ziel, str(fehler)[:200])}
        return self.seite_lesen()

    def seite_lesen(self) -> dict:
        """Liest Titel, Text und alle bedienbaren Elemente der offenen Seite."""
        if self._seite is None:
            return {"ok": False, "fehler": "Es ist keine Seite offen."}
        try:
            titel = self._seite.title()
            text = self._seite.inner_text("body")
            elemente = self._elemente_sammeln()
        except Exception as fehler:
            return {"ok": False,
                    "fehler": "Die Seite lässt sich nicht lesen: %s" % str(fehler)[:200]}
        gekuerzt = re.sub(r"\n{3,}", "\n\n", text or "").strip()
        return {"ok": True, "titel": titel, "adresse": self.adresse(),
                "text": gekuerzt[:MAX_TEXT],
                "gekuerzt": len(gekuerzt) > MAX_TEXT,
                "elemente": elemente,
                "anzahl_elemente": len(elemente)}

    def _elemente_sammeln(self) -> list:
        """Sammelt anklickbare Elemente und Eingabefelder mit Beschriftung.

        Die Auswertung läuft im Browser selbst - ein Aufruf statt hunderter
        einzelner Abfragen über die Prozessgrenze. Sonst dauert allein das
        Lesen einer normalen Seite mehrere Sekunden.
        """
        skript = """() => {
          %s
          return sammeln().map((e) => ({
            art: artVon(e), typ: (e.getAttribute('type') || '').toLowerCase(),
            name: beschriften(e), inhalt: (e.value || '').slice(0, 60)}));
        }""" % SAMMEL_JS
        rohe = self._seite.evaluate(skript) or []
        elemente = []
        for nummer, eintrag in enumerate(rohe[:MAX_ELEMENTE], start=1):
            eintrag["nummer"] = nummer
            elemente.append(eintrag)
        return elemente

    def _handhabe(self, nummer: int):
        """Holt das Element mit dieser Nummer aus der Seite.

        Die Nummerierung muss dieselbe Reihenfolge treffen wie beim Lesen -
        deshalb steht dieselbe Auswahl hier noch einmal, und es wird direkt
        das Element zurückgegeben statt eines Namens, der doppelt vorkommen
        könnte.
        """
        skript = """(n) => {
          %s
          return sammeln()[n - 1] || null;
        }""" % SAMMEL_JS
        return self._seite.evaluate_handle(skript, nummer).as_element()

    # -- Bedienen -----------------------------------------------------------

    def klicken(self, nummer: int) -> dict:
        """Klickt das Element mit dieser Nummer."""
        return self._bedienen(nummer, "klicken", "")

    def tippen(self, nummer: int, text: str) -> dict:
        """Schreibt Text in das Feld mit dieser Nummer."""
        return self._bedienen(nummer, "tippen", text)

    def _bedienen(self, nummer, aktion: str, text: str) -> dict:
        if self._seite is None:
            return {"ok": False, "fehler": "Es ist keine Seite offen."}
        try:
            nummer = int(nummer)
        except (TypeError, ValueError):
            return {"ok": False, "fehler": "'%s' ist keine Elementnummer." % nummer}
        if nummer < 1 or nummer > MAX_ELEMENTE:
            return {"ok": False, "fehler": "Element %d gibt es auf dieser Seite nicht."
                                           % nummer}
        try:
            element = self._handhabe(nummer)
            if element is None:
                return {"ok": False,
                        "fehler": "Element %d ist nicht mehr da - die Seite hat sich "
                                  "geändert. Ich lese sie neu." % nummer}
            if aktion == "klicken":
                element.scroll_into_view_if_needed(timeout=5000)
                element.click(timeout=10000)
            elif aktion == "auswaehlen":
                element.select_option(label=text, timeout=10000)
            else:
                element.fill("", timeout=5000)
                element.type(text, delay=25, timeout=15000)
            # Nach einem Klick lädt die Seite oft nach. Ohne die kurze Pause
            # liest der nächste Schritt noch die alte Seite.
            time.sleep(1.2)
            try:
                self._seite.wait_for_load_state("domcontentloaded", timeout=8000)
            except Exception:
                pass
        except Exception as fehler:
            return {"ok": False,
                    "fehler": "Element %d reagiert nicht: %s" % (nummer, str(fehler)[:180])}
        ergebnis = self.seite_lesen()
        ergebnis["getan"] = aktion
        return ergebnis

    def auswaehlen(self, nummer: int, wert: str) -> dict:
        """Wählt einen Eintrag in einer Auswahlliste."""
        return self._bedienen(nummer, "auswaehlen", wert)

    def bildschirmfoto(self, pfad: str = "") -> dict:
        """Legt ein Bild der Seite ab - für den Nachweis, was passiert ist."""
        if self._seite is None:
            return {"ok": False, "fehler": "Es ist keine Seite offen."}
        ziel = pfad or str(BASIS / "browser_aufnahme.png")
        try:
            self._seite.screenshot(path=ziel, full_page=False)
        except Exception as fehler:
            return {"ok": False, "fehler": "Kein Bild möglich: %s" % str(fehler)[:150]}
        return {"ok": True, "pfad": ziel, "text": "Bild liegt unter %s." % ziel}

    # -- Auftrag ------------------------------------------------------------

    def erledigen(self, ziel: str, start: str = "", schritte_max: int = MAX_SCHRITTE_browser,
                  bestaetigen=None) -> dict:
        """Arbeitet einen Auftrag im Browser ab, Schritt für Schritt.

        Vor jedem Schritt sagt der Agent, was er tun will. Bei einem
        Haltepunkt - Bezahlen, Löschen - wird gefragt, egal wie sicher er ist.
        """
        if not self.verfuegbar():
            return self._fehlt()
        if self.agent is None or not getattr(self.agent, "einsatzbereit",
                                             lambda: False)():
            return {"ok": False, "fehler": "Ohne Verbindung zu Claude geht das nicht."}
        auftrag = (ziel or "").strip()
        if not auftrag:
            return {"ok": False, "fehler": "Was soll ich im Browser erledigen?"}

        protokoll = []
        seite = self.oeffnen(start) if start else self.seite_lesen()
        if not seite.get("ok"):
            # Auch der Fehlschlag beim Öffnen kommt in derselben Form zurück -
            # der Aufrufer soll nicht zwei Antwortformen auseinanderhalten müssen.
            return {"ok": False, "fehler": seite.get("fehler", ""), "schritte": protokoll}
        for runde in range(1, max(1, int(schritte_max or MAX_SCHRITTE_browser)) + 1):
            schritt = self._naechster_schritt(auftrag, seite, protokoll)
            if not schritt.get("ok"):
                return {"ok": False, "fehler": schritt.get("fehler", ""),
                        "schritte": protokoll}
            plan = schritt["plan"]
            aktion = (plan.get("aktion") or "").lower()
            gedanke = plan.get("gedanke", "")
            text = plan.get("text", "")

            if aktion == "fertig":
                protokoll.append("fertig: %s" % text)
                return {"ok": True, "text": text or "Erledigt.",
                        "adresse": self.adresse(), "schritte": protokoll,
                        "runden": runde}
            if aktion == "abbruch":
                protokoll.append("abbruch: %s" % text)
                return {"ok": False,
                        "fehler": text or "Der Vorgang wurde abgebrochen.",
                        "schritte": protokoll, "runden": runde}

            beschriftung = self._beschriftung(seite, plan.get("ziel"))
            gefahr = haltepunkt("%s %s %s" % (gedanke, text, beschriftung))
            if gefahr and callable(bestaetigen):
                frage = ("Im Browser: %s (%s). Es geht um '%s'. Weiter?"
                         % (gedanke or aktion, beschriftung or text, gefahr))
                if not bestaetigen(frage):
                    protokoll.append("gestoppt bei '%s'" % gefahr)
                    return {"ok": False,
                            "fehler": "Bei '%s' abgebrochen - ohne dein Ja gehe ich "
                                      "da nicht weiter." % gefahr,
                            "schritte": protokoll}
            elif gefahr:
                protokoll.append("gestoppt bei '%s'" % gefahr)
                return {"ok": False,
                        "fehler": "Hier geht es um '%s'. Das mache ich nicht ohne "
                                  "deine ausdrückliche Freigabe." % gefahr,
                        "schritte": protokoll}

            if aktion == "warten":
                time.sleep(2.0)
                seite = self.seite_lesen()
                protokoll.append("gewartet")
                continue
            if aktion == "oeffnen":
                seite = self.oeffnen(text)
            elif aktion == "klicken":
                seite = self.klicken(plan.get("ziel"))
            elif aktion == "tippen":
                seite = self.tippen(plan.get("ziel"), text)
            elif aktion == "auswaehlen":
                seite = self.auswaehlen(plan.get("ziel"), text)
            else:
                return {"ok": False,
                        "fehler": "'%s' ist keine Aktion, die ich kenne." % aktion,
                        "schritte": protokoll}

            protokoll.append("%s %s%s" % (aktion, beschriftung or text,
                                          "" if seite.get("ok")
                                          else " -> %s" % seite.get("fehler", "")))
            if not seite.get("ok"):
                # Ein einzelner Fehlschlag beendet nichts: die Seite wird neu
                # gelesen, der Agent sieht den Stand und entscheidet neu.
                neu = self.seite_lesen()
                if not neu.get("ok"):
                    return {"ok": False, "fehler": seite.get("fehler", ""),
                            "schritte": protokoll}
                neu["letzter_fehler"] = seite.get("fehler", "")
                seite = neu

        return {"ok": False,
                "fehler": "Nach %d Schritten bin ich nicht fertig geworden. Stand: %s"
                          % (schritte_max, self.adresse()),
                "schritte": protokoll}

    @staticmethod
    def _beschriftung(seite: dict, nummer) -> str:
        """Nennt die Beschriftung zu einer Elementnummer - für Protokoll und Frage."""
        try:
            nummer = int(nummer)
        except (TypeError, ValueError):
            return ""
        for element in seite.get("elemente", []):
            if element.get("nummer") == nummer:
                return element.get("name", "")
        return ""

    def _naechster_schritt(self, auftrag: str, seite: dict, protokoll: list) -> dict:
        """Fragt Claude nach genau einem nächsten Schritt."""
        liste = "\n".join(
            "%d. [%s] %s%s" % (e["nummer"], e["art"], e["name"] or "(ohne Beschriftung)",
                               (" = %s" % e["inhalt"]) if e.get("inhalt") else "")
            for e in seite.get("elemente", []))
        bisher = "\n".join("- %s" % z for z in protokoll[-8:]) or "- noch nichts"
        anfrage = ("Auftrag: %s\n\nBisher:\n%s\n\nAdresse: %s\nTitel: %s\n\n"
                   "Seitentext:\n%s\n\nBedienbare Elemente:\n%s\n\n"
                   "Nenne den nächsten Schritt."
                   % (auftrag, bisher, seite.get("adresse", ""), seite.get("titel", ""),
                      seite.get("text", "")[:MAX_TEXT], liste or "(keine gefunden)"))
        if seite.get("letzter_fehler"):
            anfrage += ("\n\nDer letzte Schritt ist fehlgeschlagen: %s"
                        % seite["letzter_fehler"])
        plan = self.agent.json_anfrage(STEUER_PROMPT_browser, anfrage)
        if not isinstance(plan, dict) or not plan.get("aktion"):
            return {"ok": False,
                    "fehler": "Ich bekomme keinen brauchbaren nächsten Schritt zurück."}
        return {"ok": True, "plan": plan}


# =========================================================================
# messenger  -  Versand - echte Nachrichten über vier Wege.
# 
#     telegram   Text oder Sprachnachricht
#     mail       über SMTP
#     imessage   Nachrichten-App per AppleScript (auch SMS)
#     whatsapp   über einen MCP-Server
# 
# Beim AppleScript werden Nummer und Text **als Argumente übergeben**, nicht in
# den Skripttext eingebaut. Ein Text mit Anführungszeichen würde sonst das Skript
# aufbrechen - und wer den Text bestimmt, bestimmte dann das Skript.
# 
# Jeder Versand nach außen braucht eine Freigabe. Die holt der Werkzeugkatalog
# ein, bevor eine Methode dieses Moduls überhaupt aufgerufen wird.
# =========================================================================

#!/usr/bin/env python3
# -*- coding: utf-8 -*-



# Nummer und Text kommen über argv herein, nicht über Textersetzung.
IMESSAGE_SKRIPT = """on run argv
    set zielAdresse to item 1 of argv
    set nachrichtText to item 2 of argv
    tell application "Messages"
        try
            set zielDienst to 1st service whose service type = iMessage
            set zielPerson to buddy zielAdresse of zielDienst
            send nachrichtText to zielPerson
            return "iMessage"
        on error
            set smsDienst to 1st service whose service type = SMS
            set smsPerson to buddy zielAdresse of smsDienst
            send nachrichtText to smsPerson
            return "SMS"
        end try
    end tell
end run"""

KANAELE = ("telegram", "mail", "imessage", "whatsapp")


class Messenger:
    """Verschickt Nachrichten über den jeweils passenden Weg."""

    def __init__(self, telegram=None, mail=None, mcp=None, stimme=None):
        self.telegram = telegram
        self.mail = mail
        self.mcp = mcp
        self.stimme = stimme

    def zustand(self) -> dict:
        """Welche Wege stehen offen?"""
        return {
            "telegram": bool(self.telegram and self.telegram.verfuegbar()),
            "mail": bool(self.mail and self.mail.senden_moeglich()),
            "imessage": bool(shutil.which("osascript")),
            "whatsapp": bool(self._whatsapp_werkzeug()),
        }

    # -- Hauptzugang --------------------------------------------------------

    def nachricht_senden(self, kanal: str, an: str, text: str,
                         als_sprache: bool = False, betreff: str = "") -> dict:
        """Verschickt eine Nachricht über den gewählten Kanal."""
        kanal = (kanal or "").strip().lower()
        text = (text or "").strip()
        if not text:
            return {"ok": False, "fehler": "Die Nachricht ist leer."}
        if kanal in ("sms", "nachrichten"):
            kanal = "imessage"
        if kanal in ("email", "e-mail"):
            kanal = "mail"
        if kanal not in KANAELE:
            return {"ok": False,
                    "fehler": "Den Kanal '%s' kenne ich nicht. Möglich sind: %s."
                              % (kanal, ", ".join(KANAELE))}

        if kanal == "telegram":
            return self._telegram(an, text, als_sprache)
        if kanal == "mail":
            return self._mail(an, betreff, text)
        if kanal == "imessage":
            return self._imessage(an, text)
        return self._whatsapp(an, text)

    # -- Die einzelnen Wege -------------------------------------------------

    def _telegram(self, an: str, text: str, als_sprache: bool) -> dict:
        """Telegram, wahlweise als Sprachnachricht."""
        if self.telegram is None or not self.telegram.verfuegbar():
            return {"ok": False, "fehler": "Telegram ist nicht eingerichtet."}
        if als_sprache and self.stimme is not None:
            pfad = self.stimme.sprachdatei_erzeugen(text)
            if pfad:
                ergebnis = self.telegram.datei_senden(pfad, "sendVoice", "voice", an or "")
                try:
                    os.remove(pfad)
                except OSError:
                    pass
                if ergebnis.get("ok"):
                    return {"ok": True, "kanal": "telegram",
                            "text": "Sprachnachricht ist raus."}
                # Klappt die Sprachnachricht nicht, geht wenigstens der Text raus.
                print("[versand] Sprachnachricht fehlgeschlagen: %s"
                      % ergebnis.get("fehler"))
        ergebnis = self.telegram.senden(text, an or "")
        if ergebnis.get("ok"):
            return {"ok": True, "kanal": "telegram", "text": "Nachricht ist raus."}
        return ergebnis

    def _mail(self, an: str, betreff: str, text: str) -> dict:
        """E-Mail über SMTP."""
        if self.mail is None or not self.mail.senden_moeglich():
            return {"ok": False, "fehler": "Der Mailversand ist nicht eingerichtet."}
        if not an:
            return {"ok": False, "fehler": "Ich brauche eine Empfängeradresse."}
        ergebnis = self.mail.senden(an, betreff or "Nachricht von %s" % NUTZER_NAME,
                                    text)
        if ergebnis.get("ok"):
            ergebnis["kanal"] = "mail"
        return ergebnis

    def _imessage(self, an: str, text: str) -> dict:
        """iMessage oder SMS über die Nachrichten-App."""
        if not shutil.which("osascript"):
            return {"ok": False,
                    "fehler": "iMessage gibt es nur auf einem Mac mit der Nachrichten-App."}
        if not an:
            return {"ok": False,
                    "fehler": "Ich brauche eine Telefonnummer oder Apple-ID."}
        try:
            # Das Skript kommt über stdin, Nummer und Text als eigene Argumente.
            ergebnis = subprocess.run(
                ["osascript", "-", str(an), str(text)],
                input=IMESSAGE_SKRIPT, capture_output=True, text=True,
                timeout=45, shell=False)
        except (OSError, subprocess.SubprocessError) as fehler:
            return {"ok": False, "fehler": "Die Nachrichten-App antwortet nicht: %s" % fehler}
        if ergebnis.returncode != 0:
            meldung = (ergebnis.stderr or "").strip()[:300]
            if "not allowed" in meldung.lower() or "1743" in meldung:
                return {"ok": False,
                        "fehler": "Die Nachrichten-App verweigert den Zugriff. In den "
                                  "Systemeinstellungen unter Datenschutz, Automation dem "
                                  "Terminal die Steuerung von Nachrichten erlauben."}
            return {"ok": False, "fehler": "Die Nachricht ging nicht raus: %s" % meldung}
        weg = (ergebnis.stdout or "iMessage").strip() or "iMessage"
        return {"ok": True, "kanal": "imessage",
                "text": "Nachricht an %s über %s ist raus." % (an, weg)}

    def _whatsapp_werkzeug(self) -> str:
        """Sucht ein Sende-Werkzeug beim WhatsApp-MCP-Server."""
        if self.mcp is None:
            return ""
        for werkzeug in self.mcp.alle_werkzeuge():
            name = werkzeug.get("name", "")
            if name.startswith("mcp__whatsapp__") and "send" in name.lower():
                return name
        return ""

    def _whatsapp(self, an: str, text: str) -> dict:
        """WhatsApp über den MCP-Server."""
        werkzeug = self._whatsapp_werkzeug()
        if not werkzeug:
            return {"ok": False,
                    "fehler": "WhatsApp läuft über einen MCP-Dienst. In "
                              "config/mcp_servers.json den Eintrag 'whatsapp' auf "
                              "\"aus\": false stellen."}
        if not an:
            return {"ok": False, "fehler": "Ich brauche eine Telefonnummer."}
        ergebnis = self.mcp.aufrufen(werkzeug, {"recipient": an, "message": text})
        if ergebnis.get("ok"):
            return {"ok": True, "kanal": "whatsapp",
                    "text": "WhatsApp-Nachricht an %s ist raus." % an}
        return ergebnis


# =========================================================================
# computer_use  -  Bildschirmsteuerung - sehen, klicken, tippen.
# 
# Vier Dinge, an denen die üblichen Anleitungen auf dem Mac scheitern:
# 
# 1. **Retina-Skalierung.** Ein MacBook-Screenshot hat die doppelte Pixelzahl der
#    logischen Bildschirmgröße. Ohne Umrechnung landet jeder Klick bei der Hälfte
#    der Koordinate, also im linken oberen Viertel. Das ist der häufigste Grund,
#    warum solche Skripte auf dem Mac scheinbar grundlos danebenklicken. Der
#    Faktor wird gemessen (``bild.width / pyautogui.size().width``), nicht geraten.
# 2. **Bestätigung vor jedem Schritt.** Ein frei klickender Agent verschickt sonst
#    etwas, bevor der Nutzer überhaupt reagieren kann.
# 3. **Kostenbremse.** Der Screenshot wird vor dem Senden auf 1400 Pixel Breite
#    verkleinert. Ein Vollbild in Originalgröße kostet ein Vielfaches, ohne dass
#    der Agent mehr erkennt. Ein Screenshot pro Schritt, nicht mehrere.
# 4. **Selbstabbruch.** Sieht der Agent eine Login-Maske, einen Bezahlvorgang oder
#    eine Warnung, hält er an, statt weiterzuklicken.
# =========================================================================

#!/usr/bin/env python3
# -*- coding: utf-8 -*-




MAX_BREITE = 1400
MAX_SCHRITTE_computer_use = 12

ERLAUBTE_AKTIONEN = ("click", "doubleclick", "type", "press", "hotkey",
                     "scroll", "wait", "done", "abbruch")

# Begriffe, bei denen der Agent von sich aus stehen bleibt.
STOPP_BEGRIFFE = ["passwort", "password", "anmelden", "login", "sign in",
                  "kreditkarte", "credit card", "bezahlen", "zahlung", "checkout",
                  "cvv", "iban", "zwei-faktor", "verifizierungscode", "warnung",
                  "endgültig löschen", "unwiderruflich"]

STEUER_PROMPT_computer_use = """Du steuerst einen Mac über Screenshots. Du siehst das Bild und
gibst genau einen nächsten Schritt zurück.

Antworte ausschließlich als JSON, ohne Fließtext:
{"gedanke": "was du siehst und warum dieser Schritt", "aktion": "click",
 "x": 100, "y": 200, "text": "", "tasten": [], "richtung": 0}

Mögliche Aktionen:
  click        x und y setzen
  doubleclick  x und y setzen
  type         text setzen
  press        text ist der Tastenname, etwa enter oder tab
  hotkey       tasten als Liste, etwa ["command","s"]
  scroll       richtung negativ für nach unten
  wait         kurz warten
  done         Ziel erreicht, text enthält das Ergebnis
  abbruch      du kommst nicht weiter oder es wird heikel, text enthält den Grund

Koordinaten beziehen sich auf das Bild, das du gerade siehst.

Halte sofort mit abbruch an, wenn du eine Login-Maske, eine Passwortabfrage,
einen Bezahlvorgang oder eine Warnung vor unwiderruflichen Änderungen siehst.
Klicke niemals darüber hinweg.

Das Ziel: %s
"""


class Bildschirm:
    """Steuert den Mac über Screenshots - Schritt für Schritt, jeder bestätigt."""

    def __init__(self, agent=None):
        self.agent = agent
        self.letzter_fehler = ""
        if pyautogui is not None:
            # Maus in eine Bildschirmecke bricht alles ab - die Notbremse.
            pyautogui.FAILSAFE = True
            pyautogui.PAUSE = 0.3

    # -- Verfügbarkeit ------------------------------------------------------

    def verfuegbar(self) -> bool:
        """Ist die Bildschirmsteuerung technisch nutzbar?"""
        return pyautogui is not None and Image is not None

    def zustand(self) -> dict:
        """Kurzer Überblick für den Selbsttest."""
        zustand = {"pyautogui": pyautogui is not None, "pillow": Image is not None,
                   "skalierung": None, "bildschirm": None}
        if self.verfuegbar():
            try:
                groesse = pyautogui.size()
                zustand["bildschirm"] = "%dx%d" % (groesse.width, groesse.height)
                zustand["skalierung"] = self.skalierung_messen()
            except Exception as fehler:
                zustand["fehler"] = str(fehler)
        return zustand

    def skalierung_messen(self) -> float:
        """Misst den Retina-Faktor: Screenshot-Pixel geteilt durch logische Breite."""
        if not self.verfuegbar():
            return 1.0
        try:
            bild = pyautogui.screenshot()
            logisch = pyautogui.size()
            if not logisch.width:
                return 1.0
            return float(bild.width) / float(logisch.width)
        except Exception:
            return 1.0

    # -- Screenshot ---------------------------------------------------------

    def screenshot(self):
        """Nimmt einen Screenshot auf und verkleinert ihn auf 1400 Pixel Breite.

        Gibt ``(base64, faktor_bild_zu_logisch)`` zurück. Der Faktor rechnet
        Koordinaten aus dem gesendeten Bild direkt in Bildschirmkoordinaten um -
        Retina-Skalierung und Verkleinerung stecken beide darin.
        """
        if not self.verfuegbar():
            return None, 1.0
        try:
            bild = pyautogui.screenshot()
            logisch = pyautogui.size()
        except Exception as fehler:
            self.letzter_fehler = (
                "Ich kann keinen Screenshot machen: %s. In den Systemeinstellungen "
                "unter Datenschutz die Bildschirmaufnahme für das Terminal "
                "freigeben." % fehler)
            return None, 1.0

        original_breite = bild.width
        if original_breite > MAX_BREITE:
            neue_hoehe = int(bild.height * MAX_BREITE / float(original_breite))
            bild = bild.resize((MAX_BREITE, neue_hoehe), Image.LANCZOS)

        # Vom gesendeten Bild direkt auf die logische Bildschirmbreite.
        faktor = float(logisch.width) / float(bild.width)

        puffer = io.BytesIO()
        bild.convert("RGB").save(puffer, format="PNG", optimize=True)
        return base64.b64encode(puffer.getvalue()).decode("ascii"), faktor

    # -- Einzelaktionen -----------------------------------------------------

    def _aktion_ausfuehren(self, schritt: dict, faktor: float) -> str:
        """Führt genau einen Schritt aus und beschreibt, was passiert ist."""
        aktion = str(schritt.get("aktion", "")).strip().lower()
        if aktion not in ERLAUBTE_AKTIONEN:
            return "Die Aktion '%s' kenne ich nicht." % aktion

        def logisch(wert):
            """Bildkoordinate in Bildschirmkoordinate umrechnen."""
            try:
                return int(round(float(wert) * faktor))
            except (TypeError, ValueError):
                return 0

        try:
            if aktion in ("click", "doubleclick"):
                x, y = logisch(schritt.get("x")), logisch(schritt.get("y"))
                if aktion == "click":
                    pyautogui.click(x, y)
                else:
                    pyautogui.doubleClick(x, y)
                return "Auf %d, %d geklickt." % (x, y)
            if aktion == "type":
                pyautogui.typewrite(str(schritt.get("text", "")), interval=0.02)
                return "Text getippt."
            if aktion == "press":
                taste = str(schritt.get("text", "enter")).strip().lower()
                pyautogui.press(taste)
                return "Taste %s gedrückt." % taste
            if aktion == "hotkey":
                tasten = [str(t).strip().lower() for t in (schritt.get("tasten") or []) if t]
                if not tasten:
                    return "Für hotkey fehlen die Tasten."
                pyautogui.hotkey(*tasten)
                return "Tastenkombination %s ausgelöst." % "+".join(tasten)
            if aktion == "scroll":
                try:
                    richtung = int(schritt.get("richtung") or -3)
                except (TypeError, ValueError):
                    richtung = -3
                pyautogui.scroll(richtung * 100)
                return "Gescrollt."
            if aktion == "wait":
                time.sleep(1.5)
                return "Kurz gewartet."
        except Exception as fehler:
            return "Der Schritt ist fehlgeschlagen: %s" % fehler
        return ""

    @staticmethod
    def _heikel(schritt: dict) -> str:
        """Erkennt heikle Lagen im Gedanken des Agenten."""
        gedanke = ("%s %s" % (schritt.get("gedanke", ""), schritt.get("text", ""))).lower()
        for begriff in STOPP_BEGRIFFE:
            if begriff in gedanke:
                return begriff
        return ""

    # -- Hauptschleife ------------------------------------------------------

    def bedienen(self, ziel: str, schritte_max: int = MAX_SCHRITTE_computer_use,
                 bestaetigen: bool = True) -> dict:
        """Arbeitet ein Ziel Schritt für Schritt ab.

        Vor jedem Schritt wird angezeigt, was geschehen soll, und auf Enter
        gewartet. Die Freigabe für den ganzen Vorgang holt der Werkzeugkatalog
        vorher ein.
        """
        if not self.verfuegbar():
            return {"ok": False,
                    "fehler": "Für die Bildschirmsteuerung fehlen die Pakete pyautogui "
                              "und pillow. Ohne sie läuft alles andere weiter."}
        if self.agent is None or not getattr(self.agent, "einsatzbereit", lambda: False)():
            return {"ok": False,
                    "fehler": "Ohne eingerichtetes Gehirn kann ich den Bildschirm nicht sehen."}

        verlauf = []
        for nummer in range(1, max(1, int(schritte_max)) + 1):
            bild, faktor = self.screenshot()
            if bild is None:
                return {"ok": False, "fehler": self.letzter_fehler,
                        "schritte": verlauf}

            auftrag = STEUER_PROMPT_computer_use % ziel
            if verlauf:
                auftrag += "\nWas bisher geschah:\n" + "\n".join(verlauf[-6:])

            antwort = self.agent.json_anfrage(auftrag, bild_base64=bild,
                                              bild_typ="image/png")
            if not antwort.get("ok"):
                return {"ok": False,
                        "fehler": "Der Bildschirmagent hat nicht sauber geantwortet: %s"
                                  % antwort.get("fehler", ""), "schritte": verlauf}

            schritt = antwort["daten"]
            aktion = str(schritt.get("aktion", "")).lower()
            gedanke = str(schritt.get("gedanke", ""))[:300]

            if aktion == "abbruch":
                grund = schritt.get("text") or gedanke or "kein Grund genannt"
                return {"ok": False, "abgebrochen": True, "schritte": verlauf,
                        "text": "Ich habe abgebrochen: %s" % grund}
            if aktion == "done":
                ergebnis = schritt.get("text") or "Fertig."
                verlauf.append("Schritt %d: fertig." % nummer)
                return {"ok": True, "schritte": verlauf, "text": ergebnis}

            heikel = self._heikel(schritt)
            if heikel:
                return {"ok": False, "abgebrochen": True, "schritte": verlauf,
                        "text": "Ich halte an: Auf dem Bildschirm geht es um '%s'. "
                                "Das machst du bitte selbst." % heikel}

            beschreibung = "Schritt %d: %s (%s)" % (nummer, aktion, gedanke)
            print("\n%s" % beschreibung)
            if bestaetigen:
                if not sys.stdin or not sys.stdin.isatty():
                    return {"ok": False, "schritte": verlauf,
                            "fehler": "Ich kann den Schritt nicht bestätigen lassen und "
                                      "führe deshalb nichts aus."}
                try:
                    eingabe = input("Enter führt aus, alles andere bricht ab: ").strip()
                except (EOFError, KeyboardInterrupt):
                    eingabe = "abbruch"
                if eingabe:
                    return {"ok": False, "abgebrochen": True, "schritte": verlauf,
                            "text": "Abgebrochen."}

            ergebnis = self._aktion_ausfuehren(schritt, faktor)
            verlauf.append("%s -> %s" % (beschreibung, ergebnis))
            time.sleep(0.6)

        return {"ok": False, "schritte": verlauf,
                "text": "Nach %d Schritten bin ich nicht fertig geworden und höre auf."
                        % schritte_max}


# =========================================================================
# werkstatt  -  Werkstatt - der Programmierer schreibt kleine Programme und führt sie aus.
# 
# Hier gilt bewusst eine andere Regel als beim Rest des Programms. Überall sonst
# läuft nur, was auf einer Allowlist steht. Ein Programmierer, der nur
# registrierte Befehle ausführen darf, ist aber kein Programmierer.
# 
# **Deshalb ist hier der Mensch das Tor, nicht die Liste.** Ein Skript wird
# geschrieben und abgelegt, ohne dass etwas passiert. Ausgeführt wird es erst
# nach ausdrücklicher Freigabe - und die Freigabefrage zeigt vorher den
# vollständigen Code und was er anfassen will.
# 
# Was diese Prüfung leistet und was nicht, ehrlich gesagt: Sie **erkennt**, ob
# ein Skript ins Netz will, Dateien außerhalb der Werkstatt anfasst oder weitere
# Programme startet, und schreibt das in die Freigabefrage. Sie **verhindert**
# das nicht - wer Freigabe erteilt, führt aus, was dasteht. Die Prüfung ist eine
# Lesehilfe für die Entscheidung, keine Mauer. Wer Code ausführt, entscheidet.
# =========================================================================

#!/usr/bin/env python3
# -*- coding: utf-8 -*-



SCHEMA_WERKSTATT = """
CREATE TABLE IF NOT EXISTS skripte (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    zweck TEXT DEFAULT '',
    laeufe INTEGER DEFAULT 0,
    zuletzt TEXT DEFAULT '',
    angelegt TEXT NOT NULL,
    geaendert TEXT NOT NULL
);
"""

MAX_ZEICHEN = 20000
LAUFZEIT_GRENZE = 60

# Module, deren Verwendung in der Freigabefrage genannt wird. Das ist eine
# Lesehilfe fuer die Entscheidung, keine Sperre.
AUFFAELLIGE_MODULE = {
    "socket": "will ins Netz",
    "urllib": "will ins Netz",
    "http": "will ins Netz",
    "requests": "will ins Netz",
    "ftplib": "will ins Netz",
    "smtplib": "will Mails verschicken",
    "subprocess": "will weitere Programme starten",
    "multiprocessing": "will weitere Prozesse starten",
    "shutil": "will Dateien verschieben oder löschen",
    "os": "greift auf das Dateisystem zu",
    "pathlib": "greift auf das Dateisystem zu",
    "sqlite3": "will eine Datenbank öffnen",
    "ctypes": "greift tief ins System",
}


def name_saeubern(name: str) -> str:
    """Macht aus einem Wunschnamen einen sicheren Dateinamen.

    Nur Buchstaben, Ziffern, Strich und Unterstrich bleiben übrig. Damit sind
    Pfadangriffe wie ``../../etwas`` von vornherein nicht darstellbar.
    """
    roh = (name or "").strip().lower()
    for alt, neu in (("ä", "ae"), ("ö", "oe"), ("ü", "ue"), ("ß", "ss")):
        roh = roh.replace(alt, neu)
    roh = re.sub(r"\.py$", "", roh)
    roh = re.sub(r"[^a-z0-9_-]+", "_", roh).strip("_-")
    return (roh or "skript")[:60] + ".py"


class Werkstatt:
    """Legt Skripte ab, zeigt sie und führt sie nach Freigabe aus."""

    def __init__(self, memory: Memory = None, python: str = ""):
        self.memory = memory or Memory()
        self.verzeichnis = BASIS / "werkstatt"
        # Das Python der eigenen Umgebung, damit die installierten Pakete da sind.
        self.python = python or sys.executable
        db_schema_anlegen(SCHEMA_WERKSTATT, self.memory.db_pfad)
        try:
            self.verzeichnis.mkdir(parents=True, exist_ok=True)
        except OSError as fehler:
            print("[werkstatt] Verzeichnis nicht anlegbar: %s" % fehler)

    # -- Pfade --------------------------------------------------------------

    def _pfad(self, name: str):
        """Voller Pfad eines Skripts, garantiert innerhalb der Werkstatt."""
        datei = (self.verzeichnis / name_saeubern(name)).resolve()
        wurzel = self.verzeichnis.resolve()
        # Doppelt geprüft: auch wenn die Säuberung je umgangen würde, bleibt
        # alles unterhalb der Werkstatt.
        if wurzel not in datei.parents and datei != wurzel:
            return None
        return datei

    # -- Schreiben ----------------------------------------------------------

    def skript_schreiben(self, name: str, code: str, zweck: str = "") -> dict:
        """Legt ein Skript ab. Ausgeführt wird dabei nichts."""
        code = code or ""
        if not code.strip():
            return {"ok": False, "fehler": "Das Skript ist leer."}
        if len(code) > MAX_ZEICHEN:
            return {"ok": False,
                    "fehler": "Das Skript ist zu lang (%d Zeichen, erlaubt sind %d)."
                              % (len(code), MAX_ZEICHEN)}
        try:
            ast.parse(code)
        except SyntaxError as fehler:
            return {"ok": False,
                    "fehler": "Das Skript hat einen Syntaxfehler in Zeile %s: %s"
                              % (fehler.lineno, fehler.msg)}

        datei = self._pfad(name)
        if datei is None:
            return {"ok": False, "fehler": "Der Name '%s' ist nicht zulässig." % name}
        try:
            datei.write_text(code, encoding="utf-8")
        except OSError as fehler:
            return {"ok": False, "fehler": "Nicht schreibbar: %s" % fehler}

        vorhanden = self.memory._lesen(
            "SELECT id FROM skripte WHERE name=? LIMIT 1", (datei.name,))
        if vorhanden:
            self.memory._schreiben(
                "UPDATE skripte SET zweck=?, geaendert=? WHERE id=?",
                (zweck, zeitstempel(), vorhanden[0]["id"]))
        else:
            self.memory._schreiben(
                "INSERT INTO skripte (name, zweck, laeufe, zuletzt, angelegt, "
                "geaendert) VALUES (?,?,0,'',?,?)",
                (datei.name, zweck, zeitstempel(), zeitstempel()))

        befunde = self.pruefen(code)
        return {"ok": True, "name": datei.name, "pfad": str(datei),
                "zeilen": code.count("\n") + 1, "auffaelligkeiten": befunde,
                "text": "%s ist abgelegt (%d Zeilen). Ausgeführt ist noch nichts.%s"
                        % (datei.name, code.count("\n") + 1,
                           (" Achtung: %s." % ", ".join(befunde)) if befunde else "")}

    # -- Lesen --------------------------------------------------------------

    def skript_zeigen(self, name: str) -> dict:
        """Gibt den Code eines Skripts zurück."""
        datei = self._pfad(name)
        if datei is None or not datei.exists():
            return {"ok": False, "fehler": "Das Skript '%s' gibt es nicht." % name}
        try:
            code = datei.read_text(encoding="utf-8")
        except OSError as fehler:
            return {"ok": False, "fehler": "Nicht lesbar: %s" % fehler}
        return {"ok": True, "name": datei.name, "code": code,
                "auffaelligkeiten": self.pruefen(code), "text": code[:4000]}

    def werkstatt_liste(self) -> dict:
        """Alle abgelegten Skripte."""
        zeilen = self.memory._lesen("SELECT * FROM skripte ORDER BY geaendert DESC")
        eintraege = []
        for zeile in zeilen:
            datei = self._pfad(zeile["name"])
            eintraege.append({"name": zeile["name"], "zweck": zeile["zweck"],
                              "laeufe": zeile["laeufe"], "zuletzt": zeile["zuletzt"],
                              "vorhanden": bool(datei and datei.exists())})
        return {"ok": True, "anzahl": len(eintraege), "skripte": eintraege,
                "verzeichnis": str(self.verzeichnis),
                "text": ("In der Werkstatt liegen: %s."
                         % ", ".join(e["name"] for e in eintraege)) if eintraege
                        else "In der Werkstatt liegt noch kein Skript."}

    # -- Prüfen -------------------------------------------------------------

    @staticmethod
    def pruefen(code: str) -> list:
        """Nennt, was das Skript vorhat - als Lesehilfe für die Freigabe.

        Das ist ausdrücklich keine Sicherheitsprüfung. Sie liest die Importe
        über den Syntaxbaum und benennt, was auffällt, damit in der
        Freigabefrage nicht nur nackter Code steht.
        """
        befunde = []
        try:
            baum = ast.parse(code or "")
        except SyntaxError:
            return ["Code ist syntaktisch fehlerhaft"]
        module = set()
        for knoten in ast.walk(baum):
            if isinstance(knoten, ast.Import):
                for teil in knoten.names:
                    module.add(teil.name.split(".")[0])
            elif isinstance(knoten, ast.ImportFrom) and knoten.module:
                module.add(knoten.module.split(".")[0])
        for name in sorted(module):
            if name in AUFFAELLIGE_MODULE:
                hinweis = AUFFAELLIGE_MODULE[name]
                if hinweis not in befunde:
                    befunde.append(hinweis)
        if re.search(r"\b(eval|exec|compile)\s*\(", code or ""):
            befunde.append("führt Code zur Laufzeit aus")
        return befunde

    def freigabetext(self, name: str) -> str:
        """Was in der Freigabefrage stehen soll: Zweck, Befunde und der Code."""
        angaben = self.skript_zeigen(name)
        if not angaben.get("ok"):
            return angaben.get("fehler", "")
        befunde = angaben["auffaelligkeiten"]
        kopf = "Skript %s ausführen." % angaben["name"]
        if befunde:
            kopf += " Es %s." % " und ".join(befunde)
        else:
            kopf += " Es benutzt nur Standardfunktionen."
        return "%s\n\n%s" % (kopf, angaben["code"][:1500])

    # -- Ausführen ----------------------------------------------------------

    def skript_ausfuehren(self, name: str, argumente: list = None) -> dict:
        """Führt ein abgelegtes Skript aus.

        Die Freigabe holt der Werkzeugkatalog ein, bevor diese Methode
        überhaupt aufgerufen wird. Hier gilt: eigene Shell nie, Arbeitsordner
        ist die Werkstatt, und nach 60 Sekunden ist Schluss.
        """
        datei = self._pfad(name)
        if datei is None or not datei.exists():
            return {"ok": False, "fehler": "Das Skript '%s' gibt es nicht." % name}

        befehl = [self.python, str(datei)]
        for teil in (argumente or []):
            befehl.append(str(teil))

        beginn = datetime.now()
        try:
            ergebnis = subprocess.run(befehl, capture_output=True, text=True,
                                      timeout=LAUFZEIT_GRENZE, shell=False,
                                      cwd=str(self.verzeichnis))
        except subprocess.TimeoutExpired:
            return {"ok": False,
                    "fehler": "Das Skript lief länger als %d Sekunden und wurde "
                              "abgebrochen." % LAUFZEIT_GRENZE}
        except (OSError, subprocess.SubprocessError) as fehler:
            return {"ok": False, "fehler": "Der Start ist fehlgeschlagen: %s" % fehler}
        dauer = (datetime.now() - beginn).total_seconds()

        self.memory._schreiben(
            "UPDATE skripte SET laeufe=laeufe+1, zuletzt=? WHERE name=?",
            (zeitstempel(), datei.name))

        ausgabe = (ergebnis.stdout or "").strip()
        fehlertext = (ergebnis.stderr or "").strip()

        if ergebnis.returncode != 0:
            letzte = fehlertext.splitlines()[-1] if fehlertext else "ohne Meldung"
            return {"ok": False, "name": datei.name, "rueckgabe": ergebnis.returncode,
                    "ausgabe": ausgabe[:3000], "fehlertext": fehlertext[-2000:],
                    "fehler": "%s ist mit Fehler abgebrochen: %s"
                              % (datei.name, letzte)}
        return {"ok": True, "name": datei.name, "rueckgabe": 0,
                "dauer": round(dauer, 2), "ausgabe": ausgabe[:3000],
                "text": ("%s lief durch (%.1f Sekunden). Ausgabe: %s"
                         % (datei.name, dauer,
                            ausgabe[:900] if ausgabe else "keine"))}

    def skript_loeschen(self, name: str) -> dict:
        """Entfernt ein Skript aus der Werkstatt."""
        datei = self._pfad(name)
        if datei is None or not datei.exists():
            return {"ok": False, "fehler": "Das Skript '%s' gibt es nicht." % name}
        try:
            os.remove(str(datei))
        except OSError as fehler:
            return {"ok": False, "fehler": "Nicht löschbar: %s" % fehler}
        self.memory._schreiben("DELETE FROM skripte WHERE name=?", (datei.name,))
        return {"ok": True, "text": "%s ist gelöscht." % datei.name}


# =========================================================================
# team  -  Das Team - Spezialisten statt eines Alleskönners.
# 
# Ein einzelner Assistent mit vierzig Werkzeugen ist ein Alleskönner, und
# Alleskönner sind mittelmäßig. Ein Buchhalter, der Beträge schätzt, ist ein
# schlechter Buchhalter; ein Verkäufer, der nicht nachfasst, ein schlechter
# Verkäufer. Deshalb gibt es hier Rollen: Jede hat einen eigenen Auftrag, eigene
# Maßstäbe und **nur die Werkzeuge, die zu ihr gehören**.
# 
# Das ist nicht bloß Kosmetik. Die Einschränkung der Werkzeuge ist echte
# Aufgabentrennung: Der Rechercheur kann keine Buchung anlegen, der Buchhalter
# keine Mail verschicken. Wer alles darf, macht irgendwann alles - auch das
# Falsche.
# 
# Der Chef bleibt der Nutzer. Jede Wirkung nach außen braucht weiterhin seine
# Freigabe, egal welche Rolle sie auslöst.
# =========================================================================

#!/usr/bin/env python3
# -*- coding: utf-8 -*-



SCHEMA_TEAM = """
CREATE TABLE IF NOT EXISTS auftraege (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    rolle TEXT NOT NULL,
    auftrag TEXT NOT NULL,
    bericht TEXT DEFAULT '',
    status TEXT DEFAULT 'offen',
    dauer_sekunden REAL DEFAULT 0,
    angelegt TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_auftraege_rolle ON auftraege(rolle);
"""

# Gemeinsame Haltung aller Rollen. Steht vor jedem Rollenprompt.
GRUNDHALTUNG = """Du bist {rolle} im Betrieb von {name}, einer Gebäudereinigung
mit einem Inhaber. Du arbeitest diesen einen Auftrag ab und meldest zurück.

So arbeitest du:
- Du nutzt deine Werkzeuge selbstständig. Du fragst nicht um Erlaubnis für das,
  was du ohnehin darfst.
- Du erfindest nichts. Fehlt dir eine Angabe, sagst du welche und warum sie
  nötig ist, statt zu schätzen.
- Ging etwas schief, steht das in deinem Bericht. Du beschönigst nicht.
- Dein Bericht ist kurz und gesprochen: zwei bis fünf Sätze, keine
  Aufzählungszeichen, keine Sternchen. Er wird vorgelesen.
- Du nennst Zahlen konkret, nicht ungefähr.

Heute ist {wochentag}, der {datum}.

{fachliches}"""

WOCHENTAGE_TEAM = ["Montag", "Dienstag", "Mittwoch", "Donnerstag", "Freitag",
                   "Samstag", "Sonntag"]

# Die Mannschaft. Je Rolle: Anzeigename, fachliche Maßstäbe, erlaubte Werkzeuge.
ROLLEN = {
    "buchhalter": {
        "name": "der Buchhalter",
        "fachliches": """Deine Aufgabe ist die Buchhaltung.

Dein wichtigster Maßstab: Du schätzt niemals einen Betrag. Ist ein Beleg
unleserlich oder fehlt eine Angabe, trägst du nichts ein und sagst genau, was
fehlt. Ein geratener Betrag ist in der Buchhaltung schlimmer als kein Eintrag,
weil er später niemandem auffällt.

Du trennst Vorsteuer und Umsatzsteuer sauber. Du weist auf fehlende Belege hin,
denn genau die fehlen am Jahresende beim Steuerberater. Du führst die
Buchhaltung vor - die fachliche Prüfung macht der Steuerberater.""",
        "werkzeuge": ["buchung_eintragen", "beleg_erfassen", "auswertung",
                      "fehlende_belege", "csv_export", "kennzahl_setzen",
                      "notiz_speichern", "gedaechtnis_durchsuchen"],
    },
    "akquisiteur": {
        "name": "der Verkäufer",
        "fachliches": """Deine Aufgabe ist es, Aufträge hereinzuholen.

Du führst die Pipeline: Wer ist neu, wer wurde besichtigt, wer hat ein Angebot,
bei wem muss nachgefasst werden. Ein Interessent, bei dem niemand nachfasst,
ist verloren, ohne dass es jemand merkt - deshalb ist die Nachfassliste dein
wichtigstes Werkzeug.

Beim Kalkulieren rätst du nie einen Quadratmeterpreis. Du rechnest über
Leistungswerte: Fläche geteilt durch Quadratmeter pro Stunde ergibt Stunden,
mal Stundensatz ergibt den Preis. Fehlen dir Fläche, Bodenbelag oder Intervall,
fragst du danach, statt zu kalkulieren.

Du bist ehrlich über Chancen. Ein Angebot ist kein Auftrag.""",
        "werkzeuge": ["lead_anlegen", "lead_weiterstufen", "angebot_kalkulieren",
                      "angebot_ablegen", "nachfassliste", "pipeline",
                      "kontakt_anlegen", "kontakt_suchen", "notiz_speichern",
                      "punkt_anlegen", "gedaechtnis_durchsuchen",
                      "anrufen", "sms_senden", "anrufliste"],
    },
    "terminplaner": {
        "name": "der Terminplaner",
        "fachliches": """Deine Aufgabe sind Termine und der Tagesablauf.

Du achtest auf Überschneidungen. Bei einem Einzelunternehmer, der selbst zu den
Objekten fährt, ist eine Doppelbuchung ein verlorener Tag - du sagst es sofort.

Du denkst an die Fahrzeit zwischen zwei Objekten mit. Liegen zwei Termine
räumlich weit auseinander und zeitlich eng, weist du darauf hin.""",
        "werkzeuge": ["termine_lesen", "termin_anlegen", "punkt_anlegen",
                      "punkte_offen", "punkt_erledigen", "kontakt_suchen",
                      "gedaechtnis_durchsuchen", "sms_senden", "anrufen"],
    },
    "postmeister": {
        "name": "der Postbearbeiter",
        "fachliches": """Deine Aufgabe ist der Posteingang.

Du sortierst nach Dringlichkeit, nicht nach Eingangszeit. Mahnungen, Fristen
und Auftragsanfragen kommen zuerst, Newsletter zuletzt. Du löschst niemals
etwas.

Antworten formulierst du vor, verschickst sie aber nur nach ausdrücklicher
Freigabe. Aus einer Anfrage, die nach Auftrag riecht, machst du einen Hinweis
an den Verkäufer.""",
        "werkzeuge": ["mails_lesen", "mail_senden", "notiz_speichern",
                      "punkt_anlegen", "kontakt_suchen", "kontakt_anlegen",
                      "gedaechtnis_durchsuchen"],
    },
    "kundenberater": {
        "name": "der Kundenberater",
        "fachliches": """Deine Aufgabe ist es, Kundengespräche zu bewerten.

Du bewertest streng. Ein freundliches Gespräch ohne Ergebnis ist kein gutes
Gespräch, und das sagst du auch. Schwächen benennst du konkret: nicht "hätte
mehr fragen sollen", sondern "Bodenbelag und Quadratmeter nie erfasst - ohne
die ist kein Preis kalkulierbar".

Kommt derselbe Einwand dreimal, ist das kein Zufall, sondern eine Lücke im
Angebot. Darauf weist du hin.""",
        "werkzeuge": ["gespraech_festhalten", "offene_leads", "verkaufsmuster",
                      "anrufliste",
                      "kontakt_suchen", "kontakt_anlegen", "notiz_speichern",
                      "gedaechtnis_durchsuchen"],
    },
    "rechercheur": {
        "name": "der Rechercheur",
        "fachliches": """Deine Aufgabe ist es, Dinge herauszufinden.

Du nennst, woher eine Angabe stammt. Findest du etwas nicht, sagst du das,
statt eine plausible Zahl zu nennen. Bei Preisen und Wetter nennst du Datum
und Quelle mit.""",
        "werkzeuge": ["recherche", "wetter", "flug_suchen", "notiz_speichern",
                      "browser_oeffnen", "browser_lesen", "browser_auftrag",
                      "gedaechtnis_durchsuchen"],
    },
    "controller": {
        "name": "der Controller",
        "fachliches": """Deine Aufgabe sind die Zahlen des Betriebs.

Du siehst nach, ob der Laden trägt: Was kommt herein, was geht hinaus, was
bleibt. Du rechnest die Vorschau ehrlich - ein Angebot ist kein Geld, deshalb
wird die Pipeline gewichtet und nicht voll angesetzt.

Wenn die Zahlen schlecht aussehen, sagst du das zuerst und nennst den größten
Hebel.""",
        "werkzeuge": ["auswertung", "cashflow_prognose", "pipeline",
                      "fehlende_belege", "kennzahl_setzen", "dashboard_bauen",
                      "verkaufsmuster", "gedaechtnis_durchsuchen"],
    },
    "privatsekretaer": {
        "name": "der Privatsekretär",
        "fachliches": """Deine Aufgabe ist das Leben neben der Firma.

Du führst die privaten Fixkosten getrennt von den betrieblichen. Beim
Steuerberater dürfen sich die beiden nicht vermischen - deshalb fragst du im
Zweifel nach, ob etwas privat oder betrieblich ist, statt es zuzuordnen.

Deine wichtigste Rechnung ist die Bedarfsrechnung: wie viel der Betrieb im
Monat abwerfen muss, damit nach Kosten und Steuerrücklage das Private gedeckt
ist. Ein Einzelunternehmer hat kein Gehalt - diese Zahl ist sein Gehaltszettel.

Du erinnerst an das, was einmal im Jahr kommt und trotzdem jedes Jahr
überrascht: Versicherung, Pickerl, Vorauszahlung, Geburtstage.""",
        "werkzeuge": ["fixkosten_anlegen", "fixkosten_liste",
                      "fixkosten_streichen", "bedarfsrechnung",
                      "erinnerung_anlegen", "erinnerungen_faellig",
                      "notiz_speichern", "punkt_anlegen",
                      "gedaechtnis_durchsuchen"],
    },
    "programmierer": {
        "name": "der Programmierer",
        "fachliches": """Deine Aufgabe sind kleine Programme und Auswertungen.

Du schreibst kurze, lesbare Python-Skripte, die genau eine Sache tun. Du
kommentierst auf Deutsch. Vor dem Ausführen zeigst du, was das Skript tut -
ausgeführt wird nur mit ausdrücklicher Freigabe.

Du schreibst nichts, was Dateien außerhalb der Werkstatt verändert, etwas
verschickt oder aus dem Netz nachlädt. Brauchst du so etwas, sagst du es,
statt es zu umgehen.""",
        "werkzeuge": ["skript_schreiben", "skript_ausfuehren", "skript_zeigen",
                      "werkstatt_liste", "notiz_speichern"],
    },
}


class Team:
    """Verteilt Aufträge an Rollen und hält den Gesamtstand."""

    def __init__(self, agent=None, memory: Memory = None):
        self.agent = agent
        self.memory = memory or (agent.memory if agent is not None else Memory())
        db_schema_anlegen(SCHEMA_TEAM, self.memory.db_pfad)

    # -- Rollen -------------------------------------------------------------

    @staticmethod
    def rollen_liste() -> list:
        """Alle Rollen mit ihrem Anzeigenamen."""
        return [{"rolle": schluessel, "name": angaben["name"],
                 "werkzeuge": len(angaben["werkzeuge"])}
                for schluessel, angaben in ROLLEN.items()]

    @staticmethod
    def rolle_finden(name: str) -> str:
        """Findet eine Rolle - auch wenn der Nutzer sie umgangssprachlich nennt."""
        gesucht = (name or "").strip().lower()
        if not gesucht:
            return ""
        if gesucht in ROLLEN:
            return gesucht
        # Umgangssprache auf die Rolle abbilden.
        abbildung = {
            "buchhaltung": "buchhalter", "steuer": "buchhalter",
            "belege": "buchhalter", "kasse": "buchhalter",
            "verkauf": "akquisiteur", "vertrieb": "akquisiteur",
            "akquise": "akquisiteur", "verkäufer": "akquisiteur",
            "verkaeufer": "akquisiteur", "angebot": "akquisiteur",
            "kunden": "kundenberater", "gespräch": "kundenberater",
            "gespraech": "kundenberater", "beratung": "kundenberater",
            "termine": "terminplaner", "kalender": "terminplaner",
            "planer": "terminplaner",
            "post": "postmeister", "mail": "postmeister",
            "email": "postmeister", "e-mail": "postmeister",
            "zahlen": "controller", "cashflow": "controller",
            "finanzen": "controller", "auswertung": "controller",
            "suche": "rechercheur", "recherche": "rechercheur",
            "programm": "programmierer", "skript": "programmierer",
            "code": "programmierer", "entwickler": "programmierer",
        }
        for stichwort, rolle in abbildung.items():
            if stichwort in gesucht:
                return rolle
        for rolle in ROLLEN:
            if rolle.startswith(gesucht[:5]):
                return rolle
        return ""

    def systemprompt(self, rolle: str, mit_gedaechtnis: str = "") -> str:
        """Baut den Systemprompt einer Rolle."""
        angaben = ROLLEN[rolle]
        jetzt = datetime.now()
        text = GRUNDHALTUNG.format(
            rolle=angaben["name"], name=NUTZER_NAME,
            wochentag=WOCHENTAGE_TEAM[jetzt.weekday()],
            datum=jetzt.strftime("%d.%m.%Y"),
            fachliches=angaben["fachliches"])
        if mit_gedaechtnis:
            text += "\n\n" + mit_gedaechtnis
        return text

    # -- Beauftragen --------------------------------------------------------

    def beauftragen(self, rolle: str, auftrag: str, max_runden: int = 6) -> dict:
        """Gibt einen Auftrag an eine Rolle und holt ihren Bericht."""
        schluessel = self.rolle_finden(rolle)
        if not schluessel:
            return {"ok": False,
                    "fehler": "Die Rolle '%s' kenne ich nicht. Ich habe: %s."
                              % (rolle, ", ".join(ROLLEN))}
        auftrag = (auftrag or "").strip()
        if not auftrag:
            return {"ok": False,
                    "fehler": "Sag mir, was %s tun soll."
                              % ROLLEN[schluessel]["name"]}
        if self.agent is None or not getattr(self.agent, "einsatzbereit",
                                             lambda: False)():
            return {"ok": False,
                    "fehler": "Ohne eingerichtetes Gehirn kann %s nicht arbeiten."
                              % ROLLEN[schluessel]["name"]}

        gedaechtnis = ""
        try:
            gedaechtnis = self.agent.recall.gedaechtnis_block(auftrag)
        except Exception:
            gedaechtnis = ""

        beginn = datetime.now()
        bericht = self.agent.arbeiten(
            self.systemprompt(schluessel, gedaechtnis), auftrag,
            werkzeugnamen=ROLLEN[schluessel]["werkzeuge"], max_runden=max_runden)
        dauer = (datetime.now() - beginn).total_seconds()

        self.memory._schreiben(
            "INSERT INTO auftraege (rolle, auftrag, bericht, status, "
            "dauer_sekunden, angelegt) VALUES (?,?,?,?,?,?)",
            (schluessel, auftrag[:2000], (bericht or "")[:4000], "fertig",
             round(dauer, 1), zeitstempel()))

        return {"ok": True, "rolle": schluessel,
                "name": ROLLEN[schluessel]["name"],
                "dauer": round(dauer, 1), "text": bericht}

    def auftraege_letzte(self, limit: int = 12) -> list:
        """Was das Team zuletzt gemacht hat."""
        return self.memory._lesen(
            "SELECT * FROM auftraege ORDER BY id DESC LIMIT ?", (limit,))

    # -- Lagebericht --------------------------------------------------------

    def lagebericht(self, werkzeuge=None) -> dict:
        """Der permanente Stand: Kasse, Aufträge, Termine, Post, Offenes.

        Das ist kein Bericht, den jemand schreibt, sondern der Stand, wie er
        gerade wirklich ist. Jeder Bereich, der nicht abrufbar ist, sagt das -
        statt eine Null zu zeigen, die nach Ordnung aussieht.
        """
        werkzeuge = werkzeuge or (self.agent.tools if self.agent is not None else None)
        stand = {"zeitpunkt": zeitstempel(), "datum": heute_datum(), "bereiche": {}}
        if werkzeuge is None:
            return {"ok": False, "fehler": "Ohne Werkzeuge kein Lagebericht."}

        def bereich(name, funktion):
            try:
                stand["bereiche"][name] = funktion()
            except Exception as fehler:
                stand["bereiche"][name] = {"ok": False, "fehler": str(fehler)}

        bereich("kasse", lambda: werkzeuge.bookkeeping.auswertung())
        bereich("belege", lambda: werkzeuge.bookkeeping.fehlende_belege())
        bereich("pipeline", lambda: werkzeuge.akquise.pipeline())
        bereich("nachfassen", lambda: werkzeuge.akquise.nachfassliste())
        bereich("cashflow", lambda: werkzeuge.akquise.cashflow_prognose(
            3, werkzeuge.bookkeeping))
        bereich("gespraeche", lambda: werkzeuge.call_analysis.verkaufsmuster(30))
        bereich("bedarf", lambda: werkzeuge.privat.bedarfsrechnung(werkzeuge.akquise))
        bereich("anstehend", lambda: werkzeuge.privat.erinnerungen_faellig(14))
        bereich("offene_punkte", lambda: {
            "ok": True,
            "punkte": [p["text"] for p in werkzeuge.memory.punkte_offen()]})

        if werkzeuge.kalender.verfuegbar():
            bereich("termine", lambda: werkzeuge.kalender.termine(2))
        if werkzeuge.mail.lesen_moeglich():
            bereich("post", lambda: werkzeuge.mail.ungelesene(10))

        # Gesprochene Kurzfassung - das, was er hören will.
        teile = []
        kasse = stand["bereiche"].get("kasse") or {}
        if kasse.get("ok"):
            teile.append("Diesen Monat %s Einnahmen, %s Ausgaben, Ergebnis %s."
                         % (_euro(kasse["einnahmen"]), _euro(kasse["ausgaben"]),
                            _euro(kasse["ergebnis"])))
        pipeline = stand["bereiche"].get("pipeline") or {}
        if pipeline.get("ok"):
            teile.append("Laufend gesichert %s im Monat, %d Interessenten offen."
                         % (_euro(pipeline["laufender_umsatz_monat"]),
                            pipeline["offen"]))
        bedarf = stand["bereiche"].get("bedarf") or {}
        if bedarf.get("berechenbar") and bedarf.get("luecke") is not None:
            if bedarf["luecke"] > 0:
                teile.append("Zum Decken deiner Fixkosten fehlen %s im Monat."
                             % _euro(bedarf["luecke"]))
            else:
                teile.append("Deine Fixkosten sind gedeckt, %s darüber."
                             % _euro(-bedarf["luecke"]))
        anstehend = stand["bereiche"].get("anstehend") or {}
        if anstehend.get("anzahl"):
            teile.append(anstehend["text"])
        nachfassen = stand["bereiche"].get("nachfassen") or {}
        if nachfassen.get("anzahl"):
            teile.append("Heute sind %d Interessenten zum Nachfassen fällig."
                         % nachfassen["anzahl"])
        belege = stand["bereiche"].get("belege") or {}
        if belege.get("anzahl"):
            teile.append("%d Ausgaben ohne Beleg." % belege["anzahl"])
        punkte = (stand["bereiche"].get("offene_punkte") or {}).get("punkte") or []
        if punkte:
            teile.append("%d Punkte offen, zuerst: %s" % (len(punkte), punkte[0]))
        termine = stand["bereiche"].get("termine") or {}
        if termine.get("ok") and termine.get("anzahl"):
            teile.append("%d Termine in den nächsten zwei Tagen."
                         % termine["anzahl"])
            for konflikt in termine.get("konflikte", [])[:1]:
                teile.append("Achtung: %s" % konflikt["text"])
        post = stand["bereiche"].get("post") or {}
        if post.get("ok") and post.get("anzahl"):
            teile.append("%d ungelesene Mails, davon %d wichtig."
                         % (post["anzahl"], len(post.get("wichtig", []))))

        stand["ok"] = True
        stand["text"] = (" ".join(teile) if teile
                         else "Es ist noch nichts erfasst, worüber ich berichten könnte.")
        return stand


def _euro(betrag) -> str:
    """Deutscher Betrag."""
    try:
        betrag = float(betrag)
    except (TypeError, ValueError):
        betrag = 0.0
    return ("{:,.2f}".format(betrag).replace(",", "#").replace(".", ",")
            .replace("#", ".")) + " €"


# =========================================================================
# webseite  -  Die Oberfläche - Sprache, sonst nichts.
# 
# Kein Textfeld als Hauptweg, kein Knopf zum Drücken. Die Seite hört dauerhaft
# zu, wartet auf das Weckwort und antwortet laut. Tippen geht nur als Notweg,
# wenn das Mikrofon streikt.
# 
# Die Spracherkennung läuft im Browser. Wichtig dabei: Während Jarvis spricht,
# wird die Erkennung angehalten - sonst hört er sich selbst zu und antwortet
# auf seine eigene Stimme.
# =========================================================================

#!/usr/bin/env python3
# -*- coding: utf-8 -*-

SEITE_HTML = r"""<!DOCTYPE html>
<html lang="de">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<meta name="theme-color" content="#03080F">
<link rel="icon" href="/symbol.svg" type="image/svg+xml">
<title>Jarvis</title>
<style>
:root{
  --grund:#03080F; --tief:#050D16; --panel:#071420; --rand:#0E2A3C;
  --rand-hell:#16425C; --akzent:#3AD1FF; --kupfer:#A6ECFF; --text:#E4F7FF;
  --gedaempft:#8DB4C6; --grau:#5D8799; --gruen:#4CC38A; --rot:#E5484D;
  --sans:-apple-system,BlinkMacSystemFont,"Helvetica Neue",Arial,sans-serif;
  --mono:ui-monospace,"SF Mono",Menlo,monospace;
}
*{box-sizing:border-box;margin:0;padding:0}
html,body{height:100%;overflow:hidden}
body{
  background:
    radial-gradient(ellipse 70% 55% at 50% 45%,rgba(58,209,255,.10) 0%,transparent 70%),
    repeating-linear-gradient(0deg,rgba(58,209,255,.035) 0 1px,transparent 1px 44px),
    repeating-linear-gradient(90deg,rgba(58,209,255,.035) 0 1px,transparent 1px 44px),
    radial-gradient(ellipse 120% 80% at 50% 120%,#062238 0%,var(--grund) 62%);
  color:var(--text);font-family:var(--sans);-webkit-font-smoothing:antialiased;
  display:flex;flex-direction:column;user-select:none;
}
button{font-family:inherit;cursor:pointer;border:none;background:none;color:inherit}
:focus-visible{outline:2px solid var(--akzent);outline-offset:3px;border-radius:6px}

/* ---- Ticker ---- */
.ticker{
  flex:none;display:flex;gap:22px;flex-wrap:wrap;align-items:center;
  padding:10px 20px;font-size:11px;letter-spacing:.11em;text-transform:uppercase;
  color:var(--grau);border-bottom:1px solid var(--rand);
  background:linear-gradient(90deg,rgba(58,209,255,.13),transparent 68%);
}
.ticker b{color:var(--akzent);font-weight:600}
.ticker b.rot{color:var(--rot)}
.ticker .pkt{width:7px;height:7px;border-radius:50%;background:var(--grau);
             box-shadow:0 0 8px transparent}
.ticker .pkt.an{background:var(--gruen);box-shadow:0 0 9px var(--gruen)}
.ticker .pkt.aus{background:var(--rot);box-shadow:0 0 9px var(--rot)}
.ticker .rechts{margin-left:auto;display:flex;gap:14px;align-items:center}
.ticker a,.ticker .mini{color:var(--grau);text-decoration:none;font-size:10px;
                        letter-spacing:.12em}
.ticker a:hover,.ticker .mini:hover{color:var(--kupfer)}
.ticker .mini.aktiv{color:var(--akzent);text-shadow:0 0 8px rgba(58,209,255,.6)}
.blitz{position:fixed;inset:0;background:rgba(166,236,255,.18);pointer-events:none;
       opacity:0;transition:opacity .25s;z-index:50}
.blitz.an{opacity:1}

/* ---- Bühne ---- */
main{flex:1;display:flex;flex-direction:column;align-items:center;
     justify-content:center;gap:26px;padding:20px;min-height:0;position:relative}

.kugel{position:relative;width:min(46vmin,260px);height:min(46vmin,260px);
       flex:none;display:grid;place-items:center;cursor:pointer}
.kugel .ring{position:absolute;inset:0;border-radius:50%;
             border:1px solid var(--rand-hell);transition:border-color .4s}
.kugel .ring2{inset:9%;opacity:.6}
.kugel .ring3{inset:19%;opacity:.35}
.kugel .kern{
  width:42%;height:42%;border-radius:50%;
  background:radial-gradient(circle,#F4FDFF 0%,#A6ECFF 20%,#3AD1FF 42%,#0B6E99 62%,
             rgba(6,40,64,.9) 70%);
  border:2px solid rgba(166,236,255,.55);
  box-shadow:0 0 40px -2px rgba(58,209,255,.65),inset 0 0 22px rgba(255,255,255,.35);
  transition:transform .35s,box-shadow .35s;
}
.kugel .welle{position:absolute;inset:0;border-radius:50%;border:1px solid var(--akzent);
              opacity:0;pointer-events:none}

/* Zustände */
body[data-zustand="schlaeft"] .kugel .kern{transform:scale(.82);
  box-shadow:0 0 26px -10px rgba(58,209,255,.4);filter:saturate(.55)}
body[data-zustand="wach"] .ring{border-color:rgba(58,209,255,.55)}
body[data-zustand="wach"] .kugel .kern{transform:scale(1.08);
  box-shadow:0 0 70px -4px rgba(58,209,255,.75)}
body[data-zustand="wach"] .welle{animation:welle 1.7s ease-out infinite}
body[data-zustand="wach"] .welle.w2{animation-delay:.55s}
body[data-zustand="wach"] .welle.w3{animation-delay:1.1s}
@keyframes welle{0%{opacity:.55;transform:scale(.55)}100%{opacity:0;transform:scale(1.05)}}
body[data-zustand="denkt"] .ring{border-color:rgba(58,209,255,.45);
  border-top-color:var(--akzent);animation:dreh 1.1s linear infinite}
body[data-zustand="denkt"] .ring2{animation:dreh 1.6s linear infinite reverse}
body[data-zustand="denkt"] .ring3{animation:dreh 2.2s linear infinite}
@keyframes dreh{to{transform:rotate(360deg)}}
body[data-zustand="spricht"] .kugel .kern{animation:reden .5s ease-in-out infinite alternate}
@keyframes reden{from{transform:scale(1)}to{transform:scale(1.16)}}
body[data-zustand="aus"] .kugel .kern{filter:grayscale(.85) saturate(.3);transform:scale(.75)}

/* HUD: drehende Ringe um den Kern */
.kugel .hud{position:absolute;inset:-9%;width:118%;height:118%;color:var(--akzent);
            pointer-events:none;filter:drop-shadow(0 0 6px rgba(58,209,255,.45))}
.kugel .hud1{animation:dreh 60s linear infinite}
.kugel .hud2{animation:dreh 34s linear infinite reverse}
body[data-zustand="denkt"] .kugel .hud1{animation-duration:5s}
body[data-zustand="denkt"] .kugel .hud2{animation-duration:3.4s}
body[data-zustand="aus"] .kugel .hud{opacity:.35;filter:none}
.ring{border-style:dashed}
.hud-ecke{position:absolute;top:22px;font-family:var(--mono);color:var(--gedaempft);
          text-transform:uppercase;letter-spacing:.16em;font-size:10px;line-height:1.7}
.hud-ecke.links{left:26px}
.hud-ecke.rechts{right:26px;text-align:right}
.hud-ecke .hud-wert{font-size:30px;letter-spacing:.04em;color:var(--akzent);
                    text-shadow:0 0 14px rgba(58,209,255,.55);font-weight:300}
.hud-ecke::before{content:"";display:block;width:42px;height:1px;background:var(--akzent);
                  margin-bottom:8px;box-shadow:0 0 8px var(--akzent)}
.hud-ecke.rechts::before{margin-left:auto}
.hud-ecke a{color:inherit;text-decoration:none}
.hud-ecke a:hover{color:var(--kupfer)}
.zustandstext{font-size:12px;letter-spacing:.22em;text-transform:uppercase;
              color:var(--grau);text-align:center;min-height:16px}
body[data-zustand="wach"] .zustandstext{color:var(--akzent)}

/* ---- Text ---- */
.buehne{width:min(100%,780px);text-align:center;display:flex;flex-direction:column;
        gap:14px;min-height:0}
.gesagt{font-size:clamp(15px,2.1vw,19px);color:var(--gedaempft);min-height:26px;
        font-style:italic}
.gesagt.vorlaeufig{opacity:.55}
.antwort{font-size:clamp(19px,3.1vw,30px);line-height:1.42;font-weight:500;
         letter-spacing:-.01em;max-height:38vh;overflow-y:auto;padding:0 4px}
.antwort.fehler{color:#F3B0B2}
.antwort::-webkit-scrollbar{width:5px}
.antwort::-webkit-scrollbar-thumb{background:var(--rand-hell);border-radius:3px}

.hinweis{font-size:13px;color:var(--grau);line-height:1.6;max-width:440px;
         margin:0 auto}
.hinweis b{color:var(--kupfer);font-weight:600}

/* ---- Zahlenleiste unten ---- */
.zahlen{flex:none;display:flex;gap:1px;background:var(--rand);
        border-top:1px solid var(--rand)}
.zahl{flex:1;background:var(--panel);padding:11px 14px;min-width:0}
.zahl .wert{font-size:17px;font-weight:700;font-variant-numeric:tabular-nums;
            white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.zahl .wert.gut{color:var(--gruen)} .zahl .wert.schlecht{color:var(--rot)}
.zahl .wert.akzent{color:var(--akzent)}
.zahl .name{font-size:9.5px;letter-spacing:.12em;text-transform:uppercase;
            color:var(--grau);margin-top:3px;white-space:nowrap;overflow:hidden;
            text-overflow:ellipsis}

/* ---- Notweg Tippen ---- */
.tippen{position:fixed;left:50%;transform:translateX(-50%);bottom:88px;
        width:min(92vw,620px);display:none;gap:9px}
.tippen.zeigen{display:flex}
.tippen input{flex:1;background:var(--panel);border:1px solid var(--rand-hell);
              border-radius:11px;padding:12px 15px;color:var(--text);
              font-family:inherit;font-size:15px}
.tippen button{background:var(--akzent);color:#02121C;border-radius:11px;
               padding:12px 20px;font-weight:700}

/* ---- Freigabe ---- */
.schleier{position:fixed;inset:0;background:rgba(4,5,6,.9);display:none;
          place-items:center;padding:20px;z-index:60;backdrop-filter:blur(4px)}
.schleier.zeigen{display:grid}
.frage{background:var(--panel);border:1px solid var(--akzent);border-radius:16px;
       max-width:620px;width:100%;overflow:hidden;
       box-shadow:0 30px 90px -24px rgba(58,209,255,.5)}
.frage .kopf{display:flex;align-items:center;gap:12px;padding:13px 20px;
             background:rgba(58,209,255,.12);border-bottom:1px solid var(--rand)}
.frage .kopf h2{font-size:12px;letter-spacing:.18em;text-transform:uppercase;
                color:var(--akzent);font-weight:700}
.frage .rest{margin-left:auto;font-family:var(--mono);font-size:12px;color:var(--grau)}
.frage .inhalt{padding:20px}
.frage .aktion{font-size:24px;font-weight:700;margin-bottom:12px}
.frage pre{background:var(--tief);border:1px solid var(--rand);border-radius:9px;
           padding:13px 15px;font-family:var(--mono);font-size:12.5px;line-height:1.65;
           color:var(--kupfer);max-height:230px;overflow:auto;white-space:pre-wrap;
           word-break:break-word}
.frage .sagen{padding:0 20px 8px;font-size:14px;color:var(--gedaempft);text-align:center}
.frage .sagen b{color:var(--akzent)}
.frage .knoepfe{display:flex;gap:11px;padding:12px 20px 20px}
.frage .knoepfe button{flex:1;padding:15px;border-radius:10px;font-weight:700;font-size:16px}
.frage .ja{background:var(--akzent);color:#02121C}
.frage .nein{background:var(--tief);border:1px solid var(--rand-hell);color:var(--text)}
.frage{max-height:92vh;overflow-y:auto}
.frage input{width:100%;padding:13px 14px;border-radius:9px;font:14px var(--mono);
  background:var(--tief);border:1px solid var(--rand-hell);color:var(--text);
  user-select:text;-webkit-user-select:text}
.frage .meldung{padding:0 20px 4px;font-size:13px;min-height:20px;color:var(--gedaempft)}
.frage .meldung.fehler{color:var(--rot)}

@media(max-width:640px){
  .hud-ecke{display:none}
  .ticker{gap:12px;padding:8px 12px;font-size:10px}
  .ticker .rechts{width:100%;margin-left:0;justify-content:flex-start}
  .zahl{padding:9px 10px}.zahl .wert{font-size:15px}
  main{gap:18px;padding:14px}
}
</style>
</head>
<body data-zustand="aus">
<div class="blitz" id="blitz"></div>

<div class="ticker">
  <span class="pkt" id="pkt"></span>
  <span id="lage">Stand wird geholt …</span>
  <span class="rechts">
    <button class="mini" id="kameraKnopf" title="Bei 'schau mal' macht Jarvis ein Foto mit der Kamera">Kamera an</button>
    <button class="mini" id="schirmKnopf" title="Jarvis sieht deinen Bildschirm, solange du teilst">Bildschirm teilen</button>
    <button class="mini" id="tippenAn" title="Notweg, falls das Mikrofon streikt">Tippen</button>
    <a href="/autopilot" data-seite target="_blank" rel="noopener" id="zuTunLink">Heute zu tun</a>
    <a href="/protokoll" data-seite target="_blank" rel="noopener">Protokoll</a>
    <a href="/dashboard" data-seite target="_blank" rel="noopener">Cockpit</a>
    <a href="/sales" data-seite target="_blank" rel="noopener">Sales</a>
  </span>
</div>

<main>
  <div class="hud-ecke links">
    <div class="hud-wert" id="uhr">--:--</div>
    <div id="datum"></div>
    <div id="hudGehirn"></div>
  </div>
  <div class="hud-ecke rechts">
    <div class="hud-wert"><a href="/autopilot" data-seite target="_blank" rel="noopener"
         id="hudAufgaben">–</a></div>
    <div>Heute zu tun</div>
    <div id="hudSystem">Online</div>
  </div>
  <div class="kugel" id="kugel" role="button" tabindex="0"
       title="Antippen weckt Jarvis auch ohne Weckwort">
    <span class="ring"></span><span class="ring ring2"></span><span class="ring ring3"></span>
    <span class="welle"></span><span class="welle w2"></span><span class="welle w3"></span>
    <svg class="hud hud1" viewBox="0 0 200 200" aria-hidden="true">
      <circle cx="100" cy="100" r="97" fill="none" stroke="currentColor" stroke-width="1"
              stroke-dasharray="1 5"/>
      <circle cx="100" cy="100" r="90" fill="none" stroke="currentColor" stroke-width="3"
              stroke-dasharray="46 14" opacity=".55"/>
    </svg>
    <svg class="hud hud2" viewBox="0 0 200 200" aria-hidden="true">
      <circle cx="100" cy="100" r="81" fill="none" stroke="currentColor" stroke-width="1.6"
              stroke-dasharray="120 40 20 40" opacity=".75"/>
      <circle cx="100" cy="100" r="73" fill="none" stroke="currentColor" stroke-width=".8"
              stroke-dasharray="2 3" opacity=".5"/>
    </svg>
    <span class="kern"></span>
  </div>
  <div class="zustandstext" id="zustandstext">Mikrofon wird gefragt …</div>

  <div class="buehne">
    <div class="gesagt" id="gesagt"></div>
    <div class="antwort" id="antwort"></div>
    <div class="hinweis" id="hinweis">
      Sag <b>„Hey Jarvis“</b> und dann, was du brauchst.
    </div>
  </div>
</main>

<div class="tippen" id="tippen">
  <input id="feld" placeholder="Notweg: hier tippen und Enter" autocomplete="off">
  <button id="senden">Senden</button>
</div>

<div class="zahlen">
  <div class="zahl"><div class="wert" id="z1">–</div><div class="name" id="n1">Kasse</div></div>
  <div class="zahl"><div class="wert" id="z2">–</div><div class="name" id="n2">Fehlt je Monat</div></div>
  <div class="zahl"><div class="wert" id="z3">–</div><div class="name" id="n3">Nachfassen</div></div>
  <div class="zahl"><div class="wert" id="z4">–</div><div class="name" id="n4">Gesichert</div></div>
</div>

<div class="schleier" id="schleier">
  <div class="frage">
    <div class="kopf"><h2>Freigabe</h2><span class="rest" id="rest"></span></div>
    <div class="inhalt">
      <div class="aktion" id="fAktion"></div>
      <pre id="fDetails"></pre>
    </div>
    <p class="sagen">Sag <b>ja</b> oder <b>nein</b>.</p>
    <div class="knoepfe">
      <button class="nein" id="fNein">Nein</button>
      <button class="ja" id="fJa">Ja, mach</button>
    </div>
  </div>
</div>

<div class="schleier" id="schluesselDialog">
  <div class="frage">
    <div class="kopf"><h2>Womit soll Jarvis denken?</h2></div>
    <div class="inhalt">
      <div class="aktion">Kostenlos mit einem Gratis-Schlüssel</div>
      <p class="sagen" style="padding:0 0 10px;text-align:left">
        Der schnellste Weg ohne Kosten und ohne Anthropic: Hol dir bei einem
        Dienst mit Gratis-Kontingent einen Schlüssel (ohne Karte, ohne Guthaben).
        <b>Groq:</b> console.groq.com/keys &middot; <b>Google:</b>
        aistudio.google.com/apikey. Grenzen pro Minute und Tag gelten, und das
        Gespräch geht an diesen Anbieter.</p>
      <select id="dienstWahl" style="width:100%;padding:11px;margin-bottom:8px;
        border-radius:9px;background:var(--tief);border:1px solid var(--rand-hell);
        color:var(--text);font-size:14px">
        <option value="groq" data-modell="llama-3.3-70b-versatile">Groq</option>
        <option value="gemini" data-modell="gemini-flash-lite-latest,gemini-3.5-flash-lite,gemini-3.1-flash-lite,gemini-flash-latest,gemini-3.8-flash">Google Gemini</option>
        <option value="openrouter" data-modell="meta-llama/llama-3.3-70b-instruct:free">OpenRouter</option>
      </select>
      <input id="dienstModell" type="text" value="llama-3.3-70b-versatile"
             autocomplete="off" spellcheck="false" style="margin-bottom:8px"
             title="Modellnamen, durch Komma getrennt. Ist eines aufgebraucht, nimmt Jarvis das nächste.">
      <input id="dienstSchluessel" type="password" placeholder="Schlüssel einfügen"
             autocomplete="off" spellcheck="false">
    </div>
    <p class="meldung" id="dienstMeldung"></p>
    <div class="knoepfe">
      <button class="ja" id="dienstSpeichern">Gratis-Dienst nutzen</button>
    </div>
    <div class="inhalt" style="border-top:1px solid var(--rand)">
      <div class="aktion">Oder auf diesem Rechner (Ollama)</div>
      <p class="sagen" style="padding:0 0 10px;text-align:left">
        Jarvis denkt mit einem Modell, das auf diesem Rechner läuft (Ollama,
        <b>ollama.com</b>). Kein Konto, kein Guthaben, kein Limit. Dafür ist es
        langsamer und schwächer als Claude. Ollama muss installiert und
        geöffnet sein.</p>
      <input id="lokalFeld" type="text" value="qwen2.5:3b" autocomplete="off"
             spellcheck="false">
    </div>
    <p class="meldung" id="lokalMeldung"></p>
    <div class="knoepfe">
      <button class="nein" id="lokalSpeichern">Lokales Modell nutzen</button>
    </div>
    <div class="inhalt" style="border-top:1px solid var(--rand)">
      <p class="sagen" style="padding:0 0 10px;text-align:left">
        <b>Nur wenn du willst:</b> Mit einem Anthropic-Schlüssel antwortet
        Claude, schneller und klüger. Das kostet Guthaben auf
        console.anthropic.com. Das brauchst du für den Weg oben nicht.</p>
      <input id="schluesselFeld" type="password" placeholder="sk-ant-…"
             autocomplete="off" spellcheck="false">
    </div>
    <p class="meldung" id="schluesselMeldung"></p>
    <div class="knoepfe">
      <button class="nein" id="schluesselSpeichern">Schlüssel speichern</button>
    </div>
  </div>
</div>

<script>
(function () {
  "use strict";
  var SCHLUESSEL = "{{SCHLUESSEL}}";
  var WECKWOERTER = ["hey jarvis","hey javis","hey dscharvis","hey charvis",
                     "hey travis","hey jervis","hey service","hey chavis",
                     "jarvis","javis"];
  var JA = ["ja","jo","jup","okay","ok","passt","mach","machen","los","sicher",
            "einverstanden","erlaubt","freigabe","yes"];
  var NEIN = ["nein","ne","nee","no","stop","stopp","abbrechen","abbruch",
              "lass","nicht","niemals","nope"];

  var el = function (id) { return document.getElementById(id); };
  var zustand = "aus", wachBis = 0, laeuft = false;
  var freigabe = null, sprichtGerade = false;

  function setzeZustand(neu, text) {
    zustand = neu;
    document.body.dataset.zustand = neu;
    el("zustandstext").textContent = text || {
      aus: "Mikrofon aus", schlaeft: "Sag Hey Jarvis",
      wach: "Ich höre", denkt: "Ich arbeite", spricht: "…"
    }[neu];
  }

  /* ---------- Netz ---------- */
  function url(p) {
    return p + (SCHLUESSEL ? (p.indexOf("?") < 0 ? "?" : "&") +
      "schluessel=" + encodeURIComponent(SCHLUESSEL) : "");
  }
  /* Seitenlinks tragen den Schlüssel mit, sonst sperrt der Server sie aus. */
  Array.prototype.forEach.call(document.querySelectorAll("a[data-seite]"),
    function (a) { a.setAttribute("href", url(a.getAttribute("href"))); });
  function holen(p, k) {
    var o = { headers: { "Content-Type": "application/json" } };
    if (k !== undefined) { o.method = "POST"; o.body = JSON.stringify(k); }
    return fetch(url(p), o).then(function (a) { return a.json(); });
  }
  function euro(n) {
    if (typeof n !== "number") { return "–"; }
    return n.toLocaleString("de-DE", { minimumFractionDigits: 0,
      maximumFractionDigits: 0 }) + " €";
  }

  /* ---------- Sprechen ---------- */
  var stimmen = [];
  function stimmenLaden() {
    stimmen = window.speechSynthesis ? window.speechSynthesis.getVoices() : [];
  }
  if (window.speechSynthesis) {
    stimmenLaden();
    window.speechSynthesis.onvoiceschanged = stimmenLaden;
  }
  function sprich(text, danach) {
    if (!window.speechSynthesis || !text) { if (danach) { danach(); } return; }
    // Erkennung anhalten, sonst hört Jarvis sich selbst zu.
    hoerenPause();
    sprichtGerade = true;
    setzeZustand("spricht");
    window.speechSynthesis.cancel();
    var satz = new SpeechSynthesisUtterance(text);
    satz.lang = "de-DE"; satz.rate = 1.06;
    var de = stimmen.filter(function (s) { return /^de/i.test(s.lang); });
    var gut = de.filter(function (s) {
      return /markus|yannick|petra|anna|viktor|google/i.test(s.name); });
    if (gut.length) { satz.voice = gut[0]; } else if (de.length) { satz.voice = de[0]; }
    satz.onend = satz.onerror = function () {
      sprichtGerade = false;
      hoerenWeiter();
      if (danach) { danach(); }
    };
    window.speechSynthesis.speak(satz);
    // Sicherheitsnetz: manche Browser feuern onend nicht.
    setTimeout(function () {
      if (sprichtGerade) { sprichtGerade = false; hoerenWeiter(); }
    }, Math.min(45000, 2500 + text.length * 90));
  }

  /* ---------- Sehen: Kamera und Bildschirm über den Browser ---------- */
  // Kein Homebrew, kein Zusatzprogramm: Der Browser darf an Kamera und
  // Bildschirm, und das Gehirn bekommt das Bild direkt mit der Frage.
  var SEHEN = /(schau|sieh |siehst|guck|kamera|vor mir|in der hand|erkennst|was ist das|lies das|lies vor|foto|diesen beleg|den beleg hier|die rechnung hier)/i;
  var ADRESSE = /(https?:|www\.|\.(at|de|com|ch|eu|net|org)\b)/i;
  var SCHIRM = /(bildschirm|monitor|display|fenster|auf dem schirm|was ist offen|was hab ich offen)/i;
  var kameraAn = true, schirmStrom = null;
  try { kameraAn = localStorage.getItem("jarvis-kamera") !== "aus"; } catch (e) {}

  function knoepfeZeigen() {
    el("kameraKnopf").textContent = kameraAn ? "Kamera an" : "Kamera aus";
    el("kameraKnopf").classList.toggle("aktiv", kameraAn);
    el("schirmKnopf").textContent = schirmStrom ? "Bildschirm geteilt" : "Bildschirm teilen";
    el("schirmKnopf").classList.toggle("aktiv", !!schirmStrom);
  }
  function bildAus(strom) {
    return new Promise(function (fertig, fehler) {
      var v = document.createElement("video");
      v.muted = true; v.playsInline = true; v.srcObject = strom;
      v.onloadeddata = function () {
        setTimeout(function () {
          var breite = Math.min(1280, v.videoWidth || 1280);
          var hoehe = Math.round(breite * (v.videoHeight || 720) / (v.videoWidth || 1280));
          var c = document.createElement("canvas"); c.width = breite; c.height = hoehe;
          c.getContext("2d").drawImage(v, 0, 0, breite, hoehe);
          fertig(c.toDataURL("image/jpeg", 0.72).split(",")[1]);
        }, 350);  // kurz warten: die Kamera regelt erst die Helligkeit nach
      };
      v.onerror = fehler;
      v.play().catch(function () {});
    });
  }
  function blitzen() {
    el("blitz").classList.add("an");
    setTimeout(function () { el("blitz").classList.remove("an"); }, 260);
  }
  function kameraBild() {
    return navigator.mediaDevices.getUserMedia({ video: { width: 1280 } }).then(function (strom) {
      return bildAus(strom).then(function (b) {
        strom.getTracks().forEach(function (t) { t.stop(); });  // Kamera sofort wieder aus
        blitzen(); return { daten: b, quelle: "kamera" };
      });
    });
  }
  function bildFuer(text) {
    if (schirmStrom && SCHIRM.test(text)) {
      return bildAus(schirmStrom).then(function (b) { return { daten: b, quelle: "bildschirm" }; });
    }
    if (kameraAn && SEHEN.test(text) && !ADRESSE.test(text) && navigator.mediaDevices) {
      return kameraBild().catch(function () {
        el("hinweis").style.display = "block";
        el("hinweis").textContent = "Die Kamera ist im Browser nicht erlaubt - erlaube sie " +
          "über das Symbol in der Adressleiste.";
        return null;
      });
    }
    return Promise.resolve(null);
  }
  el("kameraKnopf").addEventListener("click", function () {
    kameraAn = !kameraAn;
    try { localStorage.setItem("jarvis-kamera", kameraAn ? "an" : "aus"); } catch (e) {}
    knoepfeZeigen();
  });
  el("schirmKnopf").addEventListener("click", function () {
    if (schirmStrom) {
      schirmStrom.getTracks().forEach(function (t) { t.stop(); });
      schirmStrom = null; knoepfeZeigen(); return;
    }
    if (!navigator.mediaDevices || !navigator.mediaDevices.getDisplayMedia) { return; }
    navigator.mediaDevices.getDisplayMedia({ video: true }).then(function (strom) {
      schirmStrom = strom;
      strom.getVideoTracks()[0].addEventListener("ended", function () {
        schirmStrom = null; knoepfeZeigen();
      });
      knoepfeZeigen();
    }).catch(function () {});
  });
  knoepfeZeigen();

  /* ---------- Reden ---------- */
  function fragen(text) {
    text = (text || "").trim();
    if (!text || laeuft) { return; }
    laeuft = true;
    wachBis = 0;
    el("gesagt").textContent = "„" + text + "“";
    el("gesagt").className = "gesagt";
    el("hinweis").style.display = "none";
    setzeZustand("denkt");
    bildFuer(text).then(function (bild) {
      var k = { text: text };
      if (bild && bild.daten) { k.bild = bild.daten; k.quelle = bild.quelle; }
      return holen("/api/reden", k);
    }).then(function (a) {
      var antwort = a.antwort || a.fehler || "Ich habe keine Antwort bekommen.";
      el("antwort").textContent = antwort;
      el("antwort").className = "antwort" + (a.ok ? "" : " fehler");
      laeuft = false;
      sprich(antwort, function () { setzeZustand("schlaeft"); });
      lageHolen(); zahlenHolen();
    }).catch(function (f) {
      el("antwort").textContent = "Ich erreiche den Server nicht: " + f.message;
      el("antwort").className = "antwort fehler";
      laeuft = false;
      setzeZustand("schlaeft");
    });
  }

  /* ---------- Zuhören ---------- */
  var Erk = window.SpeechRecognition || window.webkitSpeechRecognition;
  var erk = null, laeuftErk = false, willHoeren = false;

  function hoerenStart() {
    if (!erk || laeuftErk || !willHoeren || sprichtGerade) { return; }
    try { erk.start(); laeuftErk = true; } catch (f) { laeuftErk = false; }
  }
  function hoerenPause() {
    willHoeren = false;
    if (erk && laeuftErk) { try { erk.stop(); } catch (f) {} }
  }
  function hoerenWeiter() {
    willHoeren = true;
    setTimeout(hoerenStart, 320);
    if (zustand === "spricht") { setzeZustand("schlaeft"); }
  }

  function saeubern(t) {
    return (t || "").toLowerCase().replace(/[^a-zäöüß0-9 ]+/g, " ")
      .replace(/\s+/g, " ").trim();
  }
  function weckwortAb(text) {
    var k = saeubern(text);
    for (var i = 0; i < WECKWOERTER.length; i++) {
      var w = WECKWOERTER[i];
      if (k === w) { return { wach: true, rest: "" }; }
      if (k.indexOf(w + " ") === 0) {
        return { wach: true, rest: text.substr(text.length - (k.length - w.length - 1)).trim() };
      }
    }
    return { wach: false, rest: "" };
  }

  if (!Erk) {
    setzeZustand("aus", "Browser ohne Spracherkennung");
    el("hinweis").innerHTML = "Dieser Browser kann keine Spracherkennung. " +
      "Nimm <b>Safari</b> oder <b>Chrome</b> — oder tipp oben rechts.";
    el("tippen").classList.add("zeigen");
  } else {
    erk = new Erk();
    erk.lang = "de-DE";
    erk.continuous = true;
    erk.interimResults = true;

    erk.onstart = function () {
      laeuftErk = true;
      if (zustand === "aus") { setzeZustand("schlaeft"); }
    };
    erk.onend = function () {
      laeuftErk = false;
      if (willHoeren) { setTimeout(hoerenStart, 300); }
    };
    erk.onerror = function (e) {
      laeuftErk = false;
      if (e.error === "not-allowed" || e.error === "service-not-allowed") {
        willHoeren = false;
        setzeZustand("aus", "Mikrofon nicht erlaubt");
        el("hinweis").innerHTML = "Der Browser lässt mich nicht ans Mikrofon. " +
          "Erlaub es in der Adressleiste und lad die Seite neu.";
        el("hinweis").style.display = "";
        el("tippen").classList.add("zeigen");
      }
    };

    erk.onresult = function (e) {
      var fertig = "", vorlaeufig = "";
      for (var i = e.resultIndex; i < e.results.length; i++) {
        if (e.results[i].isFinal) { fertig += e.results[i][0].transcript; }
        else { vorlaeufig += e.results[i][0].transcript; }
      }

      if (vorlaeufig && !laeuft) {
        el("gesagt").textContent = vorlaeufig;
        el("gesagt").className = "gesagt vorlaeufig";
      }
      if (!fertig) { return; }
      var text = fertig.trim();
      var k = saeubern(text);
      if (!k) { return; }

      // Bei offener Freigabe zählt nur ja oder nein.
      if (freigabe) {
        var wort = k.split(" ").filter(function (w) {
          return JA.indexOf(w) >= 0 || NEIN.indexOf(w) >= 0; })[0];
        if (wort) { antworten(JA.indexOf(wort) >= 0); }
        return;
      }
      if (laeuft || sprichtGerade) { return; }

      var probe = weckwortAb(text);
      if (probe.wach) {
        if (probe.rest) { fragen(probe.rest); }
        else {
          wachBis = Date.now() + 9000;
          setzeZustand("wach");
          el("gesagt").textContent = "";
        }
        return;
      }
      if (Date.now() < wachBis) { fragen(text); }
    };

    willHoeren = true;
    hoerenStart();
    setzeZustand("schlaeft");

    // Wach werden ohne Weckwort: Kugel antippen.
    el("kugel").addEventListener("click", function () {
      if (laeuft || freigabe) { return; }
      if (window.speechSynthesis) { window.speechSynthesis.cancel(); }
      wachBis = Date.now() + 9000;
      setzeZustand("wach");
      hoerenWeiter();
    });
    el("kugel").addEventListener("keydown", function (e) {
      if (e.key === "Enter" || e.key === " ") { e.preventDefault(); this.click(); }
    });

    // Wachfenster läuft ab
    setInterval(function () {
      if (zustand === "wach" && wachBis && Date.now() > wachBis) {
        wachBis = 0;
        setzeZustand("schlaeft");
      }
    }, 500);
  }

  /* ---------- Notweg Tippen ---------- */
  el("tippenAn").addEventListener("click", function () {
    el("tippen").classList.toggle("zeigen");
    if (el("tippen").classList.contains("zeigen")) { el("feld").focus(); }
  });
  el("senden").addEventListener("click", function () {
    fragen(el("feld").value); el("feld").value = "";
  });
  el("feld").addEventListener("keydown", function (e) {
    if (e.key === "Enter") { fragen(this.value); this.value = ""; }
  });

  /* ---------- Freigaben ---------- */
  function freigabenHolen() {
    holen("/api/freigaben").then(function (a) {
      var offen = (a.offen || [])[0];
      if (!offen) { if (freigabe) { schliessen(); } return; }
      if (freigabe && freigabe.id === offen.id) {
        el("rest").textContent = offen.rest + " s"; return;
      }
      freigabe = offen;
      el("fAktion").textContent = offen.aktion;
      el("fDetails").textContent = offen.details || "(ohne Angaben)";
      el("rest").textContent = offen.rest + " s";
      el("schleier").classList.add("zeigen");
      sprich("Ich brauche eine Freigabe für " + offen.aktion + ". Ja oder nein?");
    }).catch(function () {});
  }
  function schliessen() {
    freigabe = null;
    el("schleier").classList.remove("zeigen");
  }
  function antworten(ja) {
    if (!freigabe) { return; }
    var id = freigabe.id;
    schliessen();
    if (window.speechSynthesis) { window.speechSynthesis.cancel(); }
    sprichtGerade = false; hoerenWeiter();
    holen("/api/freigabe", { id: id, ja: ja }).then(function () { lageHolen(); });
  }
  el("fJa").addEventListener("click", function () { antworten(true); });
  el("fNein").addEventListener("click", function () { antworten(false); });
  document.addEventListener("keydown", function (e) {
    if (freigabe && e.key === "Escape") { antworten(false); }
  });

  /* ---------- Was Jarvis von selbst sagt ---------- */
  function meldungenHolen() {
    if (laeuft || sprichtGerade || freigabe) { return; }
    holen("/api/meldungen").then(function (a) {
      var m = (a.meldungen || [])[0];
      if (!m) { return; }
      el("gesagt").textContent = "";
      el("antwort").textContent = m.text;
      el("antwort").className = "antwort";
      el("hinweis").style.display = "none";
      sprich(m.text, function () { setzeZustand("schlaeft"); });
      lageHolen(); zahlenHolen();
    }).catch(function () {});
  }

  /* ---------- Stand ---------- */
  function lageHolen() {
    holen("/api/lage").then(function (a) {
      el("lage").textContent = a.text || "Kein Stand abrufbar.";
    }).catch(function () { el("lage").textContent = "Server antwortet nicht."; });
  }
  function uhrStellen() {
    var jetzt = new Date();
    el("uhr").textContent = ("0" + jetzt.getHours()).slice(-2) + ":" +
                            ("0" + jetzt.getMinutes()).slice(-2);
    el("datum").textContent = jetzt.toLocaleDateString("de-AT", {
      weekday: "long", day: "numeric", month: "long"});
  }
  uhrStellen();
  setInterval(uhrStellen, 15000);

  function zustandHolen() {
    holen("/api/zustand").then(function (a) {
      el("pkt").className = "pkt " + (a.einsatzbereit ? "an" : "aus");
      if (a.aufgaben) { el("zuTunLink").textContent = "Heute zu tun (" + a.aufgaben + ")"; }
      el("hudAufgaben").textContent = String(a.aufgaben || 0);
      var gehirn = Object.keys(a.dienste || {}).filter(function (k) {
        return a.dienste[k] && ["Claude", "Gratis-Dienst", "Lokales Modell"].indexOf(k) >= 0;
      })[0];
      el("hudGehirn").textContent = "Gehirn: " + (gehirn || "fehlt");
      el("pkt").title = a.einsatzbereit ? a.werkzeuge + " Werkzeuge bereit"
                                        : "Kein Anthropic-Schlüssel";
      if (!a.einsatzbereit) {
        el("schluesselDialog").classList.add("zeigen");
        el("antwort").textContent = "Ich habe noch kein Gehirn. Trag im Fenster einen Gratis-Schlüssel ein, " +
          "dann denke ich mit.";
        el("antwort").className = "antwort fehler";
      }
    }).catch(function () {});
  }
  function schluesselSpeichern() {
    var feld = el("schluesselFeld"), meldung = el("schluesselMeldung");
    if (!feld.value.trim()) { return; }
    meldung.className = "meldung"; meldung.textContent = "Ich probiere den Schlüssel aus …";
    el("schluesselSpeichern").disabled = true;
    holen("/api/schluessel", { schluessel: feld.value }).then(function (a) {
      el("schluesselSpeichern").disabled = false;
      meldung.textContent = a.text || "";
      if (a.ok) {
        feld.value = "";
        el("schluesselDialog").classList.remove("zeigen");
        el("antwort").textContent = ""; el("antwort").className = "antwort";
        zustandHolen();
      } else { meldung.className = "meldung fehler"; }
    }).catch(function () {
      el("schluesselSpeichern").disabled = false;
      meldung.className = "meldung fehler";
      meldung.textContent = "Der Server antwortet nicht.";
    });
  }
  function lokalSpeichern() {
    var meldung = el("lokalMeldung");
    meldung.className = "meldung"; meldung.textContent = "Ich schaue nach Ollama …";
    el("lokalSpeichern").disabled = true;
    holen("/api/lokal", { modell: el("lokalFeld").value }).then(function (a) {
      el("lokalSpeichern").disabled = false;
      meldung.textContent = a.text || "";
      if (a.ok) {
        el("schluesselDialog").classList.remove("zeigen");
        el("antwort").textContent = ""; el("antwort").className = "antwort";
        zustandHolen();
      } else { meldung.className = "meldung fehler"; }
    }).catch(function () {
      el("lokalSpeichern").disabled = false;
      meldung.className = "meldung fehler";
      meldung.textContent = "Der Server antwortet nicht.";
    });
  }
  function dienstSpeichern() {
    var meldung = el("dienstMeldung");
    if (!el("dienstSchluessel").value.trim()) { return; }
    meldung.className = "meldung"; meldung.textContent = "Ich probiere den Dienst aus …";
    el("dienstSpeichern").disabled = true;
    holen("/api/dienst", { dienst: el("dienstWahl").value,
                           modell: el("dienstModell").value,
                           schluessel: el("dienstSchluessel").value }).then(function (a) {
      el("dienstSpeichern").disabled = false;
      meldung.textContent = a.text || "";
      if (a.ok) {
        el("dienstSchluessel").value = "";
        el("schluesselDialog").classList.remove("zeigen");
        el("antwort").textContent = ""; el("antwort").className = "antwort";
        zustandHolen();
      } else { meldung.className = "meldung fehler"; }
    }).catch(function () {
      el("dienstSpeichern").disabled = false;
      meldung.className = "meldung fehler";
      meldung.textContent = "Der Server antwortet nicht.";
    });
  }
  el("dienstSpeichern").addEventListener("click", dienstSpeichern);
  el("dienstWahl").addEventListener("change", function () {
    var o = el("dienstWahl").options[el("dienstWahl").selectedIndex];
    el("dienstModell").value = o.getAttribute("data-modell") || "";
  });
  el("lokalSpeichern").addEventListener("click", lokalSpeichern);
  el("schluesselSpeichern").addEventListener("click", schluesselSpeichern);
  el("schluesselFeld").addEventListener("keydown", function (e) {
    if (e.key === "Enter") { schluesselSpeichern(); }
  });
  function setzeZahl(nr, wert, name, klasse) {
    el("z" + nr).textContent = wert;
    el("z" + nr).className = "wert" + (klasse ? " " + klasse : "");
    el("n" + nr).textContent = name;
  }
  function zahlenHolen() {
    holen("/api/kasse").then(function (a) {
      setzeZahl(1, euro(a.ergebnis), "Ergebnis Monat",
                a.ergebnis >= 0 ? "gut" : "schlecht");
    }).catch(function () {});
    holen("/api/bedarf").then(function (a) {
      if (a.berechenbar && typeof a.luecke === "number" && a.luecke > 0) {
        setzeZahl(2, euro(a.luecke), "fehlt je Monat", "schlecht");
      } else if (a.berechenbar) {
        setzeZahl(2, euro(a.noetiger_umsatz), "nötig je Monat", "gut");
      } else { setzeZahl(2, "–", "Fixkosten fehlen"); }
    }).catch(function () {});
    holen("/api/nachfassen").then(function (a) {
      setzeZahl(3, String(a.anzahl || 0), a.anzahl ? "heute nachfassen" : "nichts fällig",
                a.anzahl ? "akzent" : "");
    }).catch(function () {});
    holen("/api/pipeline").then(function (a) {
      setzeZahl(4, euro(a.laufender_umsatz_monat), "gesichert je Monat", "gut");
    }).catch(function () {});
  }

  zustandHolen(); lageHolen(); zahlenHolen();
  setInterval(freigabenHolen, 1200);
  setInterval(meldungenHolen, 4000);
  setInterval(lageHolen, 45000);
  setInterval(zahlenHolen, 60000);
})();
</script>
</body>
</html>
"""


PROTOKOLL_HTML = r"""<!DOCTYPE html>
<html lang="de">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<meta name="theme-color" content="#03080F">
<link rel="icon" href="/symbol.svg" type="image/svg+xml">
<title>Jarvis Protokoll</title>
<style>
:root{--grund:#03080F;--panel:#071420;--rand:#0E2A3C;--akzent:#3AD1FF;
  --kupfer:#A6ECFF;--text:#E4F7FF;--gedaempft:#8DB4C6;--grau:#5D8799;
  --gruen:#4CC38A;--rot:#E5484D;
  --sans:-apple-system,BlinkMacSystemFont,"Helvetica Neue",Arial,sans-serif;
  --mono:ui-monospace,"SF Mono",Menlo,monospace}
*{box-sizing:border-box;margin:0;padding:0}
body{background:var(--grund);color:var(--text);font-family:var(--sans);
  -webkit-font-smoothing:antialiased;padding:0 0 60px}
header{padding:18px 20px;border-bottom:1px solid var(--rand);
  background:linear-gradient(90deg,rgba(58,209,255,.13),transparent 68%)}
header h1{font-size:18px;font-weight:600}
header p{font-size:12px;color:var(--grau);margin-top:4px;letter-spacing:.06em}
.leiste{display:flex;gap:8px;flex-wrap:wrap;padding:14px 20px;align-items:center}
.leiste button,.leiste input{font:inherit;font-size:13px;color:var(--text);
  background:var(--panel);border:1px solid var(--rand);border-radius:8px;
  padding:8px 12px}
.leiste button{cursor:pointer}
.leiste button.an{border-color:var(--akzent);color:var(--kupfer)}
.leiste input{min-width:0;flex:1 1 160px}
:focus-visible{outline:2px solid var(--akzent);outline-offset:2px}
main{max-width:860px;margin:0 auto;padding:0 20px}
.fazit{background:var(--panel);border:1px solid var(--rand);border-left:3px solid var(--akzent);
  border-radius:8px;padding:14px 16px;font-size:14px;line-height:1.5;margin-bottom:18px}
h2{font-size:11px;letter-spacing:.14em;text-transform:uppercase;color:var(--grau);
  margin:22px 0 8px;font-weight:600}
.zeile{display:flex;gap:12px;padding:9px 0;border-bottom:1px solid var(--rand);
  font-size:14px;line-height:1.45}
.zeit{flex:none;width:62px;font:11px var(--mono);color:var(--grau);padding-top:3px}
.wer{flex:none;width:54px;font-size:11px;letter-spacing:.08em;text-transform:uppercase;
  padding-top:3px;color:var(--grau)}
.wer.user{color:var(--kupfer)}
.text{flex:1;min-width:0;white-space:pre-wrap;word-wrap:break-word}
.fehler{color:var(--rot)}
.leer{color:var(--grau);font-size:13px;padding:10px 0}
</style>
</head>
<body>
<header>
  <h1 id="titel"></h1>
  <p id="unter"></p>
</header>
<div class="leiste">
  <button data-tag="heute" class="an">Heute</button>
  <button data-tag="gestern">Gestern</button>
  <button data-tag="vorgestern">Vorgestern</button>
  <button data-tage="7">7 Tage</button>
  <input id="thema" type="search" placeholder="Thema filtern" autocomplete="off">
</div>
<main>
  <div class="fazit" id="fazit">Wird geholt …</div>
  <h2>Gespräche</h2><div id="gespraeche"></div>
  <h2>Aktionen</h2><div id="aktionen"></div>
  <h2>Offen</h2><div id="offen"></div>
</main>
<script>
(function () {
  "use strict";
  var SCHLUESSEL = {{SCHLUESSEL_JSON}};
  var NUTZER = {{NUTZER_JSON}}, FIRMA = {{FIRMA_JSON}};
  var tag = "heute", tage = 1, wartet = null;
  var el = function (id) { return document.getElementById(id); };

  document.getElementById("titel").textContent = "Protokoll von " + NUTZER;
  document.getElementById("unter").textContent =
    FIRMA + " · läuft auf deinem iMac, nur für dich";

  function zeile(links, mitte, text, klasse) {
    var z = document.createElement("div"); z.className = "zeile";
    var a = document.createElement("div"); a.className = "zeit"; a.textContent = links;
    var b = document.createElement("div"); b.className = "wer " + (klasse || "");
    b.textContent = mitte;
    var c = document.createElement("div"); c.className = "text"; c.textContent = text;
    z.appendChild(a); z.appendChild(b); z.appendChild(c);
    return z;
  }
  function fuellen(id, zeilen, leerText) {
    var k = el(id); k.textContent = "";
    if (!zeilen.length) {
      var l = document.createElement("div"); l.className = "leer"; l.textContent = leerText;
      k.appendChild(l); return;
    }
    zeilen.forEach(function (z) { k.appendChild(z); });
  }
  function uhr(zeit) { return (zeit || "").slice(tage > 1 ? 5 : 11, 16); }

  function holen() {
    var q = "tag=" + encodeURIComponent(tag) + "&tage=" + tage +
      "&thema=" + encodeURIComponent(el("thema").value.trim());
    if (SCHLUESSEL) q += "&schluessel=" + encodeURIComponent(SCHLUESSEL);
    fetch("/api/protokoll?" + q).then(function (r) { return r.json(); }).then(function (d) {
      var f = el("fazit"); f.textContent = d.text || d.fehler || "Keine Antwort.";
      f.classList.toggle("fehler", !d.ok);
      if (!d.ok) return;
      fuellen("gespraeche", d.gespraeche.map(function (g) {
        return zeile(uhr(g.zeit), g.rolle === "user" ? NUTZER : "Jarvis", g.text, g.rolle);
      }), "Keine Gespräche.");
      fuellen("aktionen", d.aktionen.map(function (a) {
        return zeile(uhr(a.zeit), a.status, a.werkzeug + (a.ergebnis ? " – " + a.ergebnis : ""));
      }), "Keine Aktionen.");
      fuellen("offen", d.offene_punkte.map(function (p) {
        return zeile(p.faellig || "", "#" + p.id, p.text);
      }), "Nichts offen.");
    }).catch(function () {
      var f = el("fazit"); f.textContent = "Der iMac antwortet nicht."; f.classList.add("fehler");
    });
  }

  Array.prototype.forEach.call(document.querySelectorAll(".leiste button"), function (b) {
    b.addEventListener("click", function () {
      Array.prototype.forEach.call(document.querySelectorAll(".leiste button"),
        function (x) { x.classList.remove("an"); });
      b.classList.add("an");
      tag = b.dataset.tag || "heute"; tage = parseInt(b.dataset.tage || "1", 10);
      holen();
    });
  });
  el("thema").addEventListener("input", function () {
    clearTimeout(wartet); wartet = setTimeout(holen, 300);
  });
  holen();
})();
</script>
</body>
</html>
"""


AUTOPILOT_HTML = r"""<!DOCTYPE html>
<html lang="de">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<meta name="theme-color" content="#03080F">
<link rel="icon" href="/symbol.svg" type="image/svg+xml">
<title>Heute zu tun</title>
<style>
:root{--grund:#03080F;--panel:#071420;--tief:#050D16;--rand:#0E2A3C;--rand-hell:#16425C;
  --akzent:#3AD1FF;--kupfer:#A6ECFF;--text:#E4F7FF;--gedaempft:#8DB4C6;--grau:#5D8799;
  --gruen:#4CC38A;--rot:#E5484D;
  --sans:-apple-system,BlinkMacSystemFont,"Helvetica Neue",Arial,sans-serif;
  --mono:ui-monospace,"SF Mono",Menlo,monospace}
*{box-sizing:border-box;margin:0;padding:0}
body{background:var(--grund);color:var(--text);font-family:var(--sans);
  -webkit-font-smoothing:antialiased;padding:0 0 60px}
header{padding:18px 20px;border-bottom:1px solid var(--rand);
  background:linear-gradient(90deg,rgba(58,209,255,.13),transparent 68%)}
header h1{font-size:18px;font-weight:600}
header p{font-size:12px;color:var(--grau);margin-top:4px;letter-spacing:.04em}
main{max-width:860px;margin:0 auto;padding:16px 20px}
.karte{background:var(--panel);border:1px solid var(--rand);border-radius:10px;
  padding:14px 16px;margin-bottom:12px}
.karte.lauf{border-left:3px solid var(--akzent)}
h2{font-size:11px;letter-spacing:.14em;text-transform:uppercase;color:var(--grau);
  margin:20px 0 8px;font-weight:600}
label{font-size:13px;color:var(--gedaempft)}
input[type=text],textarea{width:100%;font:14px var(--sans);color:var(--text);
  background:var(--tief);border:1px solid var(--rand-hell);border-radius:8px;padding:9px 11px}
textarea{font:13px/1.5 var(--sans);min-height:120px;resize:vertical;margin-top:8px}
.branchen{display:flex;flex-wrap:wrap;gap:6px 14px;margin:10px 0}
.branchen label{display:flex;gap:6px;align-items:center}
button,.knopf{font:inherit;font-size:13px;cursor:pointer;border-radius:8px;padding:8px 14px;
  border:1px solid var(--rand-hell);background:var(--tief);color:var(--text);
  text-decoration:none;display:inline-block}
button.haupt{background:var(--akzent);border-color:var(--akzent);color:#02121C;font-weight:700}
button:disabled{opacity:.5;cursor:default}
.reihe{display:flex;gap:8px;flex-wrap:wrap;margin-top:10px;align-items:center}
.art{font-size:10px;letter-spacing:.12em;text-transform:uppercase;color:var(--kupfer)}
.titel{font-size:16px;font-weight:600;margin:3px 0}
.grund{font-size:12px;color:var(--grau)}
.meldung{font-size:13px;color:var(--gedaempft);min-height:18px;margin-top:8px}
.meldung.fehler{color:var(--rot)}
.leer{color:var(--grau);font-size:14px;padding:8px 0}
:focus-visible{outline:2px solid var(--akzent);outline-offset:2px}
</style>
</head>
<body>
<header>
  <h1 id="titel">Heute zu tun</h1>
  <p id="unter"></p>
</header>
<main>
  <div class="karte lauf">
    <div id="laufText">Wird geholt …</div>
    <div class="reihe">
      <button class="haupt" id="jetzt">Jetzt arbeiten</button>
      <span class="meldung" id="laufMeldung"></span>
    </div>
  </div>

  <h2>Aufgaben</h2>
  <div id="liste"></div>

  <h2>Einstellungen</h2>
  <div class="karte">
    <label for="name">Dein Name (so stellt Jarvis dich in Skripten vor)</label>
    <input id="name" type="text" autocomplete="off" style="margin-bottom:10px">
    <label for="firma">Name deiner Firma</label>
    <input id="firma" type="text" autocomplete="off" style="margin-bottom:10px">
    <label for="ort">In welchem Ort oder Bezirk suchst du Kunden?</label>
    <input id="ort" type="text" placeholder="zum Beispiel Linz oder Wien" autocomplete="off">
    <div class="branchen" id="branchen"></div>
    <label><input type="checkbox" id="an"> Von selbst arbeiten (<span id="uhrzeiten"></span>)</label>
    <div class="reihe">
      <button id="speichern">Speichern</button>
      <span class="meldung" id="einstMeldung"></span>
    </div>
  </div>
  <p class="grund" style="margin-top:14px">
    Jarvis schickt Mails nie von selbst: Gesendet wird erst, wenn du auf
    „Senden“ klickst. Neue Betriebe bekommen ein Anruf-Skript statt einer Mail,
    weil Werbemails ohne Einwilligung in der Regel nicht erlaubt sind.
  </p>
</main>
<script>
(function () {
  "use strict";
  var SCHLUESSEL = {{SCHLUESSEL_JSON}};
  var NUTZER = {{NUTZER_JSON}}, FIRMA = {{FIRMA_JSON}};
  var ARTEN = {anruf: "Anrufen", nachfassen: "Nachfassen", antwort: "Mail beantworten",
               hinweis: "Hinweis"};
  var el = function (id) { return document.getElementById(id); };
  var warten = null;

  el("titel").textContent = "Heute zu tun · " + NUTZER;
  el("unter").textContent = FIRMA + " · Jarvis arbeitet auf deinem iMac und legt hier alles ab";

  function url(p) {
    return p + (SCHLUESSEL ? (p.indexOf("?") < 0 ? "?" : "&") +
      "schluessel=" + encodeURIComponent(SCHLUESSEL) : "");
  }
  function holen(p, k) {
    var o = { headers: { "Content-Type": "application/json" } };
    if (k !== undefined) { o.method = "POST"; o.body = JSON.stringify(k); }
    return fetch(url(p), o).then(function (a) { return a.json(); });
  }
  function knopf(text, klasse, aktion) {
    var b = document.createElement("button");
    b.textContent = text; if (klasse) { b.className = klasse; }
    b.addEventListener("click", aktion); return b;
  }

  function karte(a) {
    var k = document.createElement("div"); k.className = "karte";
    var art = document.createElement("div"); art.className = "art";
    art.textContent = ARTEN[a.art] || a.art;
    var titel = document.createElement("div"); titel.className = "titel"; titel.textContent = a.titel;
    var grund = document.createElement("div"); grund.className = "grund"; grund.textContent = a.grund || "";
    k.appendChild(art); k.appendChild(titel); k.appendChild(grund);
    var betreff = null;
    if (a.art === "antwort") {
      betreff = document.createElement("input"); betreff.type = "text";
      betreff.value = a.betreff || ""; betreff.style.marginTop = "8px";
      k.appendChild(betreff);
    }
    var text = document.createElement("textarea"); text.value = a.text || "";
    k.appendChild(text);
    var meldung = document.createElement("div"); meldung.className = "meldung";
    var reihe = document.createElement("div"); reihe.className = "reihe";
    function machen(aktion) {
      return function () {
        meldung.className = "meldung"; meldung.textContent = "…";
        holen("/api/autopilot/aktion", {id: a.id, aktion: aktion, text: text.value,
                                        betreff: betreff ? betreff.value : undefined})
          .then(function (r) {
            meldung.textContent = r.text || "";
            if (r.ok) { k.style.opacity = ".45"; setTimeout(laden, 700); }
            else { meldung.className = "meldung fehler"; }
          }).catch(function () { meldung.className = "meldung fehler";
                                 meldung.textContent = "Der iMac antwortet nicht."; });
      };
    }
    if (a.art === "antwort") {
      reihe.appendChild(knopf("Senden an " + a.an, "haupt", machen("senden")));
    }
    if ((a.art === "anruf" || a.art === "nachfassen") && a.an) {
      var tel = document.createElement("a"); tel.className = "knopf";
      tel.href = "tel:" + a.an.replace(/[^+0-9]/g, ""); tel.textContent = "Anrufen " + a.an;
      reihe.appendChild(tel);
    }
    if (a.art !== "antwort") { reihe.appendChild(knopf("Erledigt", "", machen("erledigt"))); }
    reihe.appendChild(knopf("Verwerfen", "", machen("verwerfen")));
    k.appendChild(reihe); k.appendChild(meldung);
    return k;
  }

  function laden() {
    holen("/api/autopilot").then(function (d) {
      var liste = el("liste"); liste.textContent = "";
      if (!d.aufgaben.length) {
        var l = document.createElement("div"); l.className = "leer";
        l.textContent = "Nichts offen. Klick auf „Jetzt arbeiten“, dann sucht Jarvis neue Arbeit.";
        liste.appendChild(l);
      }
      d.aufgaben.forEach(function (a) { liste.appendChild(karte(a)); });
      var e = d.einstellungen;
      ["ort", "name", "firma"].forEach(function (f) {
        if (document.activeElement !== el(f)) { el(f).value = e[f] || ""; }
      });
      el("an").checked = !!e.an; el("uhrzeiten").textContent = e.uhrzeiten;
      var kasten = el("branchen");
      if (!kasten.childNodes.length) {
        e.alle_branchen.forEach(function (b) {
          var lab = document.createElement("label"); var c = document.createElement("input");
          c.type = "checkbox"; c.value = b; c.checked = e.branchen.indexOf(b) >= 0;
          lab.appendChild(c); lab.appendChild(document.createTextNode(b)); kasten.appendChild(lab);
        });
      }
      var lauf = d.letzter_lauf || {};
      el("laufText").textContent = d.laeuft ? "Jarvis arbeitet gerade …" :
        (lauf.ergebnis ? "Zuletzt (" + (lauf.ende || lauf.start || "").slice(0, 16) + "): " +
         lauf.ergebnis : "Jarvis hat noch nicht gearbeitet.");
      el("jetzt").disabled = !!d.laeuft;
      clearTimeout(warten);
      if (d.laeuft) { warten = setTimeout(laden, 4000); }
    }).catch(function () { el("laufText").textContent = "Der iMac antwortet nicht."; });
  }

  el("jetzt").addEventListener("click", function () {
    el("jetzt").disabled = true;
    holen("/api/autopilot/laufen", {}).then(function (r) {
      el("laufMeldung").textContent = r.text || ""; setTimeout(laden, 1500);
    });
  });
  el("speichern").addEventListener("click", function () {
    var gewaehlt = Array.prototype.filter.call(
      document.querySelectorAll("#branchen input"), function (c) { return c.checked; })
      .map(function (c) { return c.value; });
    holen("/api/autopilot/einstellungen", {ort: el("ort").value, branchen: gewaehlt,
                                           an: el("an").checked, name: el("name").value,
                                           firma: el("firma").value}).then(function (r) {
      el("einstMeldung").textContent = r.text || ""; laden();
    });
  });
  laden();
})();
</script>
</body>
</html>
"""


# =========================================================================
# dashboard_teile  -  Bausteine für die Oberflächen - Farben, Zahlenformate und SVG-Grafiken.
# 
# Hier liegt alles, was Command Center und Sales-Ansicht gemeinsam benutzen.
# Die Grafiken sind handgeschriebenes SVG: keine Fremdbibliothek, kein
# Nachladen aus dem Netz. Die Seiten funktionieren dadurch auch offline und
# öffnen sich mit einem Doppelklick, ohne dass ein Server läuft.
# =========================================================================

#!/usr/bin/env python3
# -*- coding: utf-8 -*-


# Farben des Cockpits
FARBE_HINTERGRUND = "#08090B"
FARBE_PANEL = "#0F1113"
FARBE_KACHEL = "#121517"
FARBE_RAND = "#1C1F23"
FARBE_AKZENT = "#E8622C"
FARBE_TEXT = "#E6E8EA"
FARBE_GRAU = "#6E767D"
FARBE_GUT = "#4CC38A"
FARBE_WARNUNG = "#E8A33C"
FARBE_SCHLECHT = "#E5484D"

WOCHENTAGE = ["Montag", "Dienstag", "Mittwoch", "Donnerstag", "Freitag",
              "Samstag", "Sonntag"]

# Ein einziges Stylesheet für beide Seiten. Bewusst als schlichter Text und
# nicht als Formatvorlage - sonst müsste jedes Prozentzeichen in CSS verdoppelt
# werden, und genau das wird beim Bearbeiten irgendwann vergessen.
CSS = """
* { box-sizing: border-box; margin: 0; padding: 0; }
body {
  background: #08090B; color: #E6E8EA; min-height: 100vh; padding-bottom: 48px;
  font-family: -apple-system, BlinkMacSystemFont, "Helvetica Neue", Arial, sans-serif;
  -webkit-font-smoothing: antialiased;
}
a { color: #E8622C; text-decoration: none; }
a:hover { text-decoration: underline; }

.ticker {
  background: linear-gradient(90deg, rgba(232,98,44,.16), rgba(232,98,44,.02) 60%, transparent);
  border-bottom: 1px solid rgba(232,98,44,.34);
  padding: 9px 20px; font-size: 11px; letter-spacing: .1em; text-transform: uppercase;
  display: flex; gap: 26px; flex-wrap: wrap; align-items: center; color: #8A9096;
}
.ticker b { color: #E8622C; text-shadow: 0 0 12px rgba(232,98,44,.55); font-weight: 600; }
.ticker .rot { color: #E5484D; text-shadow: 0 0 12px rgba(229,72,77,.5); }

header { padding: 26px 20px 6px; display: flex; justify-content: space-between;
         align-items: flex-end; flex-wrap: wrap; gap: 12px; }
header h1 { font-size: 15px; font-weight: 600; letter-spacing: .22em;
            text-transform: uppercase; color: #E6E8EA; }
header h1 span { color: #E8622C; }
header p { color: #6E767D; font-size: 13px; margin-top: 5px; }
nav { display: flex; gap: 8px; }
nav a { font-size: 11px; letter-spacing: .12em; text-transform: uppercase;
        border: 1px solid #1C1F23; border-radius: 6px; padding: 7px 13px;
        color: #8A9096; }
nav a.aktiv { border-color: rgba(232,98,44,.5); color: #E8622C;
              background: rgba(232,98,44,.07); }
nav a:hover { text-decoration: none; border-color: rgba(232,98,44,.5); color: #E8622C; }

.raster { display: grid; gap: 13px; padding: 14px 20px;
          grid-template-columns: repeat(12, 1fr); align-items: start; }
.panel { background: #0F1113; border: 1px solid #1C1F23; border-radius: 10px;
         padding: 15px 17px; grid-column: span 4; min-width: 0; }
.panel.breit { grid-column: span 8; }
.panel.voll { grid-column: span 12; }
.panel.schmal { grid-column: span 3; }
@media (max-width: 1100px) { .panel, .panel.breit, .panel.schmal { grid-column: span 6; } }
@media (max-width: 700px)  { .panel, .panel.breit, .panel.schmal, .panel.voll { grid-column: span 12; } }

.panel h2 { font-size: 10px; text-transform: uppercase; letter-spacing: .16em;
            color: #6E767D; margin-bottom: 12px; font-weight: 600;
            display: flex; justify-content: space-between; align-items: center; }
.panel h2 em { font-style: normal; color: #3E454B; letter-spacing: .08em; }

.kacheln { display: grid; grid-template-columns: repeat(auto-fit, minmax(118px, 1fr));
           gap: 9px; }
.kachel { background: #121517; border: 1px solid #1C1F23; border-radius: 8px;
          padding: 11px 13px; }
.kachel .wert { font-size: 21px; font-weight: 600; color: #F2F4F6;
                font-variant-numeric: tabular-nums; letter-spacing: -.01em; }
.kachel .wert.akzent { color: #E8622C; text-shadow: 0 0 16px rgba(232,98,44,.4); }
.kachel .wert.gut { color: #4CC38A; }
.kachel .wert.warn { color: #E8A33C; }
.kachel .wert.schlecht { color: #E5484D; }
.kachel .name { font-size: 9.5px; color: #6E767D; text-transform: uppercase;
                letter-spacing: .1em; margin-top: 5px; }

ul { list-style: none; }
li { padding: 7px 0; border-bottom: 1px solid #17191C; font-size: 13px; line-height: 1.5; }
li:last-child { border-bottom: none; }
.zeit { color: #E8622C; font-variant-numeric: tabular-nums; margin-right: 8px;
        font-size: 12px; }
.grau { color: #6E767D; font-size: 12px; }
.warnung { color: #E5484D; }
.achtung { color: #E8A33C; }
.ok { color: #4CC38A; }
.leer { color: #3E454B; font-style: italic; font-size: 12.5px; padding: 6px 0; }

.status { display: inline-block; width: 7px; height: 7px; border-radius: 50%;
          margin-right: 8px; vertical-align: middle; }
.an { background: #4CC38A; box-shadow: 0 0 8px #4CC38A; }
.aus { background: #2A3036; }

.balkenzeile { margin-bottom: 9px; }
.balkenkopf { display: flex; justify-content: space-between; font-size: 12px;
              margin-bottom: 4px; }
.balkenkopf span:last-child { color: #6E767D; font-variant-numeric: tabular-nums; }
.balken { height: 5px; background: #17191C; border-radius: 3px; overflow: hidden; }
.balken i { display: block; height: 100%; border-radius: 3px; }

.ringfeld { display: flex; align-items: center; gap: 16px; flex-wrap: wrap; }
.ringtext { flex: 1; min-width: 130px; }
.ringtext .gross { font-size: 26px; font-weight: 600; color: #F2F4F6;
                   font-variant-numeric: tabular-nums; }
.ringtext .klein { font-size: 12px; color: #6E767D; line-height: 1.5; margin-top: 5px; }

.verlauf { display: flex; align-items: flex-end; gap: 14px; flex-wrap: wrap; }
.verlaufblock { flex: 1; min-width: 150px; }
.verlaufkopf { font-size: 10px; text-transform: uppercase; letter-spacing: .1em;
               color: #6E767D; margin-bottom: 6px; display: flex;
               justify-content: space-between; }
.verlaufkopf b { color: #E6E8EA; font-variant-numeric: tabular-nums; }

footer { padding: 18px 20px; color: #3E454B; font-size: 11.5px; line-height: 1.7; }
"""


def sicher(text) -> str:
    """Macht Text HTML-sicher - ein Kundenname darf die Seite nicht aufbrechen."""
    return html.escape(str(text if text is not None else ""))


def euro(betrag) -> str:
    """Formatiert einen Betrag deutsch: 1.234,56 Euro-Zeichen."""
    try:
        betrag = float(betrag)
    except (TypeError, ValueError):
        betrag = 0.0
    text = "{:,.2f}".format(betrag).replace(",", "#").replace(".", ",").replace("#", ".")
    return text + " €"


def euro_kurz(betrag) -> str:
    """Kurzform für enge Kacheln: 71,3k statt 71.300,00."""
    try:
        betrag = float(betrag)
    except (TypeError, ValueError):
        betrag = 0.0
    if abs(betrag) >= 10000:
        return ("%.1fk" % (betrag / 1000.0)).replace(".", ",") + " €"
    return euro(betrag)


def prozent(teil, ganzes) -> float:
    """Anteil in Prozent, ohne Division durch null."""
    try:
        ganzes = float(ganzes)
        if ganzes <= 0:
            return 0.0
        return max(0.0, min(100.0, 100.0 * float(teil) / ganzes))
    except (TypeError, ValueError):
        return 0.0


def ampelfarbe(wert: float, gut_ab: float = 70, mittel_ab: float = 40) -> str:
    """Grün, Gelb oder Rot - je nachdem, wie gut der Wert ist."""
    if wert >= gut_ab:
        return FARBE_GUT
    if wert >= mittel_ab:
        return FARBE_WARNUNG
    return FARBE_SCHLECHT


# ---------------------------------------------------------------------------
# Grafiken
# ---------------------------------------------------------------------------

def ring(anteil, beschriftung: str = "", groesse: int = 132,
         farbe: str = FARBE_AKZENT, dicke: int = 9) -> str:
    """Runde Fortschrittsanzeige als SVG.

    ``anteil`` ist ein Prozentwert. ``None`` heißt: es gibt noch keine Daten -
    dann wird ein leerer Ring mit einem Strich gezeigt, keine erfundene Null.
    """
    radius = (groesse / 2.0) - dicke - 3
    umfang = 2 * math.pi * radius
    mitte = groesse / 2.0
    hat_daten = anteil is not None
    wert = max(0.0, min(100.0, float(anteil))) if hat_daten else 0.0
    gefuellt = umfang * wert / 100.0
    anzeige = ("%d%%" % round(wert)) if hat_daten else "–"

    return "".join([
        '<svg viewBox="0 0 %d %d" width="%d" height="%d" role="img">' % (
            groesse, groesse, groesse, groesse),
        '<defs><filter id="gl%d" x="-50%%" y="-50%%" width="200%%" height="200%%">'
        '<feGaussianBlur stdDeviation="3.5" result="b"/>'
        '<feMerge><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge>'
        '</filter></defs>' % groesse,
        '<circle cx="%.1f" cy="%.1f" r="%.1f" fill="none" stroke="%s" '
        'stroke-width="%d"/>' % (mitte, mitte, radius, FARBE_RAND, dicke),
        ('<circle cx="%.1f" cy="%.1f" r="%.1f" fill="none" stroke="%s" '
         'stroke-width="%d" stroke-linecap="round" stroke-dasharray="%.2f %.2f" '
         'transform="rotate(-90 %.1f %.1f)" filter="url(#gl%d)"/>'
         % (mitte, mitte, radius, farbe, dicke, gefuellt, umfang - gefuellt,
            mitte, mitte, groesse)) if hat_daten and wert > 0 else "",
        '<text x="%.1f" y="%.1f" text-anchor="middle" fill="%s" '
        'font-size="%d" font-weight="600" font-family="inherit">%s</text>'
        % (mitte, mitte + 3, FARBE_TEXT if hat_daten else FARBE_GRAU,
           int(groesse * 0.23), anzeige),
        ('<text x="%.1f" y="%.1f" text-anchor="middle" fill="%s" font-size="%d" '
         'letter-spacing="1.4" font-family="inherit">%s</text>'
         % (mitte, mitte + int(groesse * 0.19), FARBE_GRAU, int(groesse * 0.085),
            sicher(beschriftung.upper()))) if beschriftung else "",
        '</svg>'])


def sparkline(werte: list, breite: int = 240, hoehe: int = 44,
              farbe: str = FARBE_AKZENT, fuellen: bool = True) -> str:
    """Kleiner Verlaufsgraph als SVG.

    Weniger als zwei Werte ergeben keinen Verlauf - dann kommt ein Hinweis
    statt einer Linie, die etwas vortäuscht.
    """
    zahlen = []
    for wert in werte or []:
        try:
            zahlen.append(float(wert))
        except (TypeError, ValueError):
            zahlen.append(0.0)
    if len(zahlen) < 2:
        return ('<div class="leer" style="height:%dpx;display:flex;'
                'align-items:center">noch kein Verlauf</div>' % hoehe)

    kleinster, groesster = min(zahlen), max(zahlen)
    spanne = (groesster - kleinster) or 1.0
    rand = 3
    schritt = breite / float(len(zahlen) - 1)
    punkte = []
    for index, zahl in enumerate(zahlen):
        x = index * schritt
        y = hoehe - rand - ((zahl - kleinster) / spanne) * (hoehe - 2 * rand)
        punkte.append("%.1f,%.1f" % (x, y))

    kennung = abs(hash((tuple(zahlen[:6]), farbe, breite))) % 100000
    flaeche = ""
    if fuellen:
        flaeche = ('<polygon points="0,%d %s %d,%d" fill="url(#fl%d)"/>'
                   % (hoehe, " ".join(punkte), breite, hoehe, kennung))
    return "".join([
        '<svg viewBox="0 0 %d %d" width="100%%" height="%d" '
        'preserveAspectRatio="none" role="img">' % (breite, hoehe, hoehe),
        '<defs><linearGradient id="fl%d" x1="0" y1="0" x2="0" y2="1">' % kennung,
        '<stop offset="0%%" stop-color="%s" stop-opacity=".30"/>' % farbe,
        '<stop offset="100%%" stop-color="%s" stop-opacity="0"/>' % farbe,
        '</linearGradient></defs>',
        flaeche,
        '<polyline points="%s" fill="none" stroke="%s" stroke-width="1.6" '
        'stroke-linejoin="round" stroke-linecap="round" '
        'vector-effect="non-scaling-stroke"/>' % (" ".join(punkte), farbe),
        '</svg>'])


def saeulen(werte: list, beschriftungen: list = None, hoehe: int = 60,
            farbe: str = FARBE_AKZENT) -> str:
    """Balkenreihe für Monatsvergleiche. Negative Werte werden rot."""
    zahlen = []
    for wert in werte or []:
        try:
            zahlen.append(float(wert))
        except (TypeError, ValueError):
            zahlen.append(0.0)
    if not zahlen:
        return '<div class="leer">noch keine Monate erfasst</div>'
    groesster = max([abs(z) for z in zahlen]) or 1.0
    stuecke = []
    for index, zahl in enumerate(zahlen):
        anteil = abs(zahl) / groesster
        # Ein Monat ohne Buchung bekommt einen matten Strich, keinen farbigen
        # Balken - sonst sieht die Nulllinie aus wie ein kleiner Umsatz.
        farbe_balken = (FARBE_RAND if zahl == 0
                        else (farbe if zahl > 0 else FARBE_SCHLECHT))
        beschriftung = ""
        if beschriftungen and index < len(beschriftungen):
            beschriftung = ('<div style="font-size:9px;color:%s;text-align:center;'
                            'margin-top:4px">%s</div>'
                            % (FARBE_GRAU, sicher(beschriftungen[index])))
        stuecke.append(
            '<div style="flex:1;display:flex;flex-direction:column;'
            'justify-content:flex-end;align-items:center">'
            '<div style="width:100%%;height:%dpx;display:flex;align-items:flex-end">'
            '<div title="%s" style="width:100%%;height:%.1f%%;background:%s;'
            'border-radius:2px 2px 0 0;min-height:2px"></div></div>%s</div>'
            % (hoehe, sicher(euro(zahl)), max(2.0, anteil * 100),
               farbe_balken, beschriftung))
    return ('<div style="display:flex;gap:4px;align-items:flex-end">%s</div>'
            % "".join(stuecke))


def balken(name: str, wert: float, maximum: float, zusatz: str = "",
           farbe: str = FARBE_AKZENT) -> str:
    """Waagrechter Fortschrittsbalken mit Beschriftung."""
    anteil = prozent(wert, maximum)
    return ('<div class="balkenzeile"><div class="balkenkopf">'
            '<span>%s</span><span>%s</span></div>'
            '<div class="balken"><i style="width:%.1f%%;background:%s"></i></div></div>'
            % (sicher(name), sicher(zusatz), anteil, farbe))


def seite_bauen(titel: str, ticker: str, kopf_links: str, kopf_rechts: str,
                inhalt: str, fusszeile: str) -> str:
    """Setzt eine vollständige HTML-Seite zusammen."""
    return "".join([
        '<!DOCTYPE html>\n<html lang="de">\n<head>\n',
        '<meta charset="utf-8">\n',
        '<meta name="viewport" content="width=device-width, initial-scale=1">\n',
        '<meta http-equiv="refresh" content="60">\n',
        '<title>%s</title>\n<style>%s</style>\n</head>\n<body>\n' % (sicher(titel), CSS),
        '<div class="ticker">%s</div>\n' % ticker,
        '<header>%s%s</header>\n' % (kopf_links, kopf_rechts),
        inhalt,
        '<footer>%s</footer>\n</body>\n</html>\n' % fusszeile])


# =========================================================================
# dashboard  -  Command Center - erzeugt ``dashboard/dashboard.html`` und ``data.json``.
# 
# Der Nutzer soll auf einen Blick sehen, wie sein Betrieb steht: Zahlen des
# Monats, Verlauf, Termine, Posteingang, offene Leads, Notizen und - besonders
# wichtig - was Jarvis zuletzt getan hat. Jede ausgeführte Aktion steht dort.
# Ein Assistent, der handelt, muss nachprüfbar sein.
# 
# **Es wird nur gezeigt, was wirklich in der Datenbank steht.** Ein Bereich ohne
# Daten bleibt sichtbar leer und sagt das auch. Eine Kennzahl, die nach etwas
# aussieht, aber auf nichts beruht, wäre schlimmer als eine leere Fläche - der
# Nutzer trifft danach Entscheidungen.
# 
# Die Seite lädt sich alle 60 Sekunden selbst neu und braucht keinen Server.
# =========================================================================

#!/usr/bin/env python3
# -*- coding: utf-8 -*-




class Dashboard:
    """Baut das Command Center als einzelne HTML-Datei."""

    def __init__(self, memory=None, bookkeeping=None, call_analysis=None,
                 recall=None, kalender=None, mail=None, routines=None,
                 scheduler=None, mcp=None, akquise=None, team=None,
                 privat=None):
        self.memory = memory
        self.bookkeeping = bookkeeping
        self.call_analysis = call_analysis
        self.recall = recall
        self.kalender = kalender
        self.mail = mail
        self.routines = routines
        self.scheduler = scheduler
        self.mcp = mcp
        self.akquise = akquise
        self.team = team
        self.privat = privat
        # Die Sales-Analyse ist eine eigene Seite, wird aber immer mitgebaut -
        # sonst zeigt der Verweis im Kopf auf eine Datei, die es nicht gibt.
        self.verkaufsansicht = Verkaufsansicht(call_analysis, memory)

    # -- Daten sammeln ------------------------------------------------------

    def daten_sammeln(self, mit_netz: bool = False) -> dict:
        """Trägt alles zusammen, was auf die Seite kommt.

        ``mit_netz`` steuert, ob Kalender und Posteingang abgefragt werden -
        beim Bauen im Hintergrund bleibt das aus, damit es schnell bleibt.
        """
        jetzt = datetime.now()
        daten = {"erzeugt": jetzt.strftime("%Y-%m-%d %H:%M:%S"),
                 "wochentag": WOCHENTAGE[jetzt.weekday()],
                 "datum": jetzt.strftime("%d.%m.%Y"),
                 "uhrzeit": jetzt.strftime("%H:%M"),
                 "firma": FIRMA, "nutzer": NUTZER_NAME}

        if self.bookkeeping is not None:
            try:
                daten["monat"] = self.bookkeeping.auswertung(
                    jetzt.strftime("%Y-%m-01"), heute_datum())
                daten["belege"] = self.bookkeeping.fehlende_belege()
                daten["belegquote"] = self.bookkeeping.belegquote(
                    jetzt.strftime("%Y-%m-01"), heute_datum())
                daten["verlauf"] = self.bookkeeping.tagesverlauf(30)
                daten["monate"] = self.bookkeeping.monatsverlauf(6)
            except Exception as fehler:
                daten["monat_fehler"] = str(fehler)

        if self.call_analysis is not None:
            try:
                daten["leads"] = self.call_analysis.offene_leads()
                daten["muster"] = self.call_analysis.verkaufsmuster()
                daten["dimensionen"] = self.call_analysis.dimensionen_schnitt()
            except Exception as fehler:
                daten["leads_fehler"] = str(fehler)

        if self.akquise is not None:
            try:
                daten["pipeline"] = self.akquise.pipeline()
                daten["nachfassen"] = self.akquise.nachfassliste()
                daten["cashflow"] = self.akquise.cashflow_prognose(
                    6, self.bookkeeping)
            except Exception as fehler:
                daten["pipeline_fehler"] = str(fehler)

        if self.privat is not None:
            try:
                daten["bedarf"] = self.privat.bedarfsrechnung(self.akquise)
                daten["fixkosten"] = self.privat.fixkosten()
                daten["erinnerungen"] = self.privat.erinnerungen_faellig(21)
            except Exception as fehler:
                daten["bedarf_fehler"] = str(fehler)

        if self.team is not None:
            try:
                daten["auftraege"] = [dict(z) for z in self.team.auftraege_letzte(8)]
            except Exception:
                daten["auftraege"] = []

        if self.memory is not None:
            try:
                daten["notizen"] = self.memory.notizen_letzte(8)
                daten["punkte"] = self.memory.punkte_offen()
                daten["protokoll"] = self.memory.protokoll(16)
                daten["statistik"] = self.memory.statistik()
            except Exception as fehler:
                daten["memory_fehler"] = str(fehler)

        if self.routines is not None:
            try:
                daten["routinen"] = self.routines.statistik()
            except Exception:
                daten["routinen"] = {}

        if self.scheduler is not None:
            try:
                daten["zeitplan"] = self.scheduler.uebersicht()
            except Exception:
                daten["zeitplan"] = []

        if mit_netz and self.kalender is not None and self.kalender.verfuegbar():
            try:
                daten["kalender"] = self.kalender.termine(3)
            except Exception as fehler:
                daten["kalender"] = {"ok": False, "fehler": str(fehler)}

        if mit_netz and self.mail is not None and self.mail.lesen_moeglich():
            try:
                daten["mail"] = self.mail.ungelesene(10)
            except Exception as fehler:
                daten["mail"] = {"ok": False, "fehler": str(fehler)}

        daten["dienste"] = konfig_uebersicht()
        if self.mcp is not None:
            try:
                daten["mcp"] = self.mcp.zustand()
            except Exception:
                daten["mcp"] = {}
        return daten

    # -- Bausteine ----------------------------------------------------------

    @staticmethod
    def _panel(titel: str, inhalt: str, breite: str = "", zusatz: str = "") -> str:
        """Ein Kasten mit Überschrift."""
        klasse = ("panel " + breite).strip()
        kopf = sicher(titel)
        if zusatz:
            kopf += "<em>%s</em>" % sicher(zusatz)
        return '<section class="%s"><h2>%s</h2>%s</section>' % (klasse, kopf, inhalt)

    @staticmethod
    def _liste(eintraege: list, leer_text: str) -> str:
        """Eine Aufzählung, oder ein ehrlicher Hinweis, dass nichts da ist."""
        if not eintraege:
            return '<p class="leer">%s</p>' % sicher(leer_text)
        return "<ul>%s</ul>" % "".join("<li>%s</li>" % eintrag for eintrag in eintraege)

    @staticmethod
    def _kacheln(eintraege: list) -> str:
        """Ein Raster aus Kennzahlen-Kacheln."""
        return '<div class="kacheln">%s</div>' % "".join(
            '<div class="kachel"><div class="wert %s">%s</div>'
            '<div class="name">%s</div></div>'
            % (klasse, sicher(wert), sicher(name)) for name, wert, klasse in eintraege)

    # -- Panels -------------------------------------------------------------

    def _panel_belegquote(self, daten: dict) -> str:
        """Die wichtigste einzelne Zahl: Wie viel Geld ist belegt?"""
        quote = (daten.get("belegquote") or {})
        wert = quote.get("quote")
        farbe = ampelfarbe(wert if wert is not None else 0, 90, 60)
        if wert is None:
            text = ('<div class="klein">Noch keine Ausgaben erfasst. Sobald du '
                    'Belege buchst, siehst du hier, wie viel davon belegt ist.</div>')
        else:
            text = ('<div class="gross">%s</div>'
                    '<div class="klein">von %s Ausgaben sind belegt.<br>'
                    'Genau das fehlt sonst beim Steuerberater.</div>'
                    % (euro(quote.get("belegt", 0)), euro(quote.get("gesamt", 0))))
        inhalt = ('<div class="ringfeld">%s<div class="ringtext">%s</div></div>'
                  % (ring(wert, "belegt", 132, farbe), text))
        return self._panel("Belegquote", inhalt, "", "laufender Monat")

    def _panel_zahlen(self, daten: dict) -> str:
        """Die Zahlen des laufenden Monats."""
        monat = daten.get("monat")
        if not monat:
            return self._panel("Laufender Monat",
                               '<p class="leer">Keine Buchhaltungsdaten.</p>', "breit")
        leads = daten.get("leads") or {}
        kacheln = [
            ("Einnahmen", euro(monat["einnahmen"]), "gut"),
            ("Ausgaben", euro(monat["ausgaben"]), ""),
            ("Ergebnis", euro(monat["ergebnis"]),
             "gut" if monat["ergebnis"] >= 0 else "schlecht"),
            ("Zahllast", euro(monat["zahllast"]), "akzent"),
            ("Vorsteuer", euro(monat["vorsteuer"]), ""),
            ("Umsatzsteuer", euro(monat["umsatzsteuer"]), ""),
            ("Buchungen", str(monat["anzahl"]), ""),
            ("Offenes Volumen", euro_kurz(leads.get("volumen_offen", 0)), "akzent"),
        ]
        return self._panel("Laufender Monat", self._kacheln(kacheln), "breit",
                           "%s bis %s" % (monat["von"], monat["bis"]))

    def _panel_verlauf(self, daten: dict) -> str:
        """Sparklines der letzten 30 Tage und die Monatsbilanz."""
        verlauf = daten.get("verlauf") or {}
        monate = daten.get("monate") or {}
        einnahmen = verlauf.get("einnahmen") or []
        ausgaben = verlauf.get("ausgaben") or []

        if not any(einnahmen) and not any(ausgaben):
            inhalt = ('<p class="leer">In den letzten 30 Tagen ist noch nichts '
                      'gebucht worden.</p>')
        else:
            inhalt = (
                '<div class="verlauf">'
                '<div class="verlaufblock"><div class="verlaufkopf">'
                '<span>Einnahmen 30 Tage</span><b>%s</b></div>%s</div>'
                '<div class="verlaufblock"><div class="verlaufkopf">'
                '<span>Ausgaben 30 Tage</span><b>%s</b></div>%s</div>'
                '</div>'
                % (euro(verlauf.get("summe_einnahmen", 0)),
                   sparkline(einnahmen, farbe=FARBE_GUT),
                   euro(verlauf.get("summe_ausgaben", 0)),
                   sparkline(ausgaben, farbe=FARBE_AKZENT)))

        if monate.get("ergebnis"):
            inhalt += ('<div style="margin-top:14px"><div class="verlaufkopf">'
                       '<span>Ergebnis je Monat</span><b>%s</b></div>%s</div>'
                       % (euro(monate["ergebnis"][-1]),
                          saeulen(monate["ergebnis"], monate.get("monate"))))
        return self._panel("Verlauf", inhalt, "breit")

    def _panel_vertrieb(self, daten: dict) -> str:
        """Abschlussquote und die eigene schwächste Stelle im Gespräch."""
        muster = daten.get("muster") or {}
        dimensionen = daten.get("dimensionen") or {}
        if not muster.get("anzahl"):
            return self._panel(
                "Vertrieb",
                '<p class="leer">Noch kein Gespräch festgehalten. Erzähl Jarvis von '
                'einem Kundentermin, dann bewertet er ihn.</p>')

        quote = muster.get("abschlussquote", 0)
        inhalt = ('<div class="ringfeld">%s<div class="ringtext">'
                  '<div class="gross">%s</div>'
                  '<div class="klein">%d Gespräche, Durchschnitt %s Punkte.<br>'
                  '%d gewonnen, %d verloren, %d offen.</div></div></div>'
                  % (ring(quote, "Abschluss", 116, ampelfarbe(quote, 50, 25)),
                     euro_kurz((daten.get("leads") or {}).get("volumen_offen", 0)),
                     muster["anzahl"], muster.get("durchschnitt", 0),
                     muster.get("gewonnen", 0), muster.get("verloren", 0),
                     muster.get("offen", 0)))

        zeilen = [e for e in (dimensionen.get("dimensionen") or [])
                  if e["wert"] is not None]
        if zeilen:
            inhalt += '<div style="margin-top:14px">'
            for eintrag in zeilen:
                inhalt += balken(eintrag["name"], eintrag["wert"], 10,
                                 "%.1f / 10" % eintrag["wert"],
                                 ampelfarbe(eintrag["wert"] * 10, 70, 40))
            inhalt += '</div>'
            schwach = dimensionen.get("schwaechste")
            if schwach:
                inhalt += ('<p class="achtung" style="font-size:12px;margin-top:6px">'
                           'Schwächste Stelle: %s mit %.1f von 10.</p>'
                           % (sicher(schwach["name"]), schwach["wert"]))
        for einwand in muster.get("wiederkehrende_einwaende", [])[:2]:
            inhalt += ('<p class="warnung" style="font-size:12px;margin-top:6px">'
                       'Einwand "%s" kam %d mal.</p>'
                       % (sicher(einwand["einwand"]), einwand["anzahl"]))
        return self._panel("Vertrieb", inhalt, "", "letzte 90 Tage")

    def _panel_kategorien(self, daten: dict) -> str:
        """Wohin das Geld fließt - Ausgaben je Kategorie."""
        monat = daten.get("monat") or {}
        nach_kategorie = monat.get("nach_kategorie") or {}
        if not nach_kategorie:
            return self._panel("Ausgaben je Kategorie",
                               '<p class="leer">Noch keine Ausgaben gebucht.</p>')
        groesster = max(nach_kategorie.values())
        inhalt = "".join(
            balken(name, betrag, groesster, euro(betrag))
            for name, betrag in list(nach_kategorie.items())[:8])
        return self._panel("Ausgaben je Kategorie", inhalt)

    def _panel_bedarf(self, daten: dict) -> str:
        """Was der Betrieb abwerfen muss, damit privat alles gedeckt ist.

        Das ist der Gehaltszettel eines Einzelunternehmers - er hat keinen.
        """
        bedarf = daten.get("bedarf")
        if not bedarf or not bedarf.get("berechenbar"):
            return self._panel(
                "Was der Betrieb tragen muss",
                '<p class="leer">Fixkosten sind noch nicht erfasst. Sag Jarvis, '
                'was monatlich fix rausgeht, dann steht hier, was der Betrieb '
                'abwerfen muss.</p>', "breit")

        noetig = bedarf["noetiger_umsatz"]
        gesichert = bedarf.get("gesichert")
        deckung = prozent(gesichert, noetig) if gesichert is not None else None
        farbe = ampelfarbe(deckung if deckung is not None else 0, 100, 60)

        if gesichert is None:
            beschreibung = ("<div class=\"klein\">Noch keine Auftragslage erfasst.</div>")
        elif bedarf["luecke"] > 0:
            beschreibung = ('<div class="gross" style="color:%s">%s fehlen</div>'
                            '<div class="klein">Gesichert laufen %s von %s.<br>'
                            'Das sind %s im Jahr, die noch hereinkommen müssen.</div>'
                            % (FARBE_SCHLECHT, euro(bedarf["luecke"]),
                               euro(gesichert), euro(noetig),
                               euro(bedarf["luecke"] * 12)))
        else:
            beschreibung = ('<div class="gross" style="color:%s">%s darüber</div>'
                            '<div class="klein">Gesichert laufen %s, nötig sind %s.'
                            '</div>'
                            % (FARBE_GUT, euro(-bedarf["luecke"]),
                               euro(gesichert), euro(noetig)))

        inhalt = ('<div class="ringfeld">%s<div class="ringtext">%s</div></div>'
                  % (ring(deckung, "gedeckt", 132, farbe), beschreibung))
        inhalt += self._kacheln([
            ("Nötig je Monat", euro(noetig), "akzent"),
            ("Privat fix", euro(bedarf["privat_je_monat"]), ""),
            ("Firma fix", euro(bedarf["firma_je_monat"]), ""),
            ("Steuerrücklage", euro(bedarf["steuerruecklage"]), "warn"),
        ])
        return self._panel("Was der Betrieb tragen muss", inhalt, "breit",
                           "%g Prozent Rücklage" % bedarf["steuersatz"])

    def _panel_erinnerungen(self, daten: dict) -> str:
        """Was in den nächsten Wochen ansteht - privat wie betrieblich."""
        anstehend = daten.get("erinnerungen")
        if not anstehend or not anstehend.get("anzahl"):
            return self._panel("Steht an",
                               '<p class="leer">In den nächsten drei Wochen '
                               'steht nichts an.</p>')
        zeilen = []
        for eintrag in anstehend["eintraege"][:8]:
            wann = ("heute" if eintrag["in_tagen"] == 0
                    else "morgen" if eintrag["in_tagen"] == 1
                    else "in %d Tagen" % eintrag["in_tagen"])
            klasse = "warnung" if eintrag["in_tagen"] <= 3 else "grau"
            zeilen.append('<span class="zeit">%s</span>%s '
                          '<span class="%s">%s</span> '
                          '<span class="grau">%s</span>'
                          % (sicher(eintrag["datum"][5:]), sicher(eintrag["was"]),
                             klasse, wann, sicher(eintrag["bereich"])))
        return self._panel("Steht an", self._liste(zeilen, ""), "",
                           "%d Termine" % anstehend["anzahl"])

    def _panel_fixkosten(self, daten: dict) -> str:
        """Die laufenden Verpflichtungen, größte zuerst."""
        kosten = daten.get("fixkosten")
        if not kosten or not kosten.get("anzahl"):
            return ""
        groesster = max([e["je_monat"] for e in kosten["eintraege"]] or [1])
        inhalt = ""
        for eintrag in kosten["eintraege"][:9]:
            inhalt += balken(
                "%s%s" % (eintrag["name"],
                          " (Firma)" if eintrag["bereich"] == "firma" else ""),
                eintrag["je_monat"], groesster, euro(eintrag["je_monat"]),
                FARBE_AKZENT if eintrag["bereich"] == "firma" else FARBE_WARNUNG)
        return self._panel("Fixkosten je Monat", inhalt, "",
                           euro(kosten["gesamt_je_monat"]))

    def _panel_pipeline(self, daten: dict) -> str:
        """Die Auftragspipeline nach Stufen - wo Geld auf der Straße liegt."""
        pipeline = daten.get("pipeline")
        if not pipeline or not pipeline.get("ok"):
            return self._panel("Auftragspipeline",
                               '<p class="leer">Noch kein Interessent erfasst.</p>')
        stufen = pipeline.get("stufen") or {}
        offene = [(name, angaben) for name, angaben in stufen.items()
                  if name not in ("gewonnen", "verloren") and angaben["anzahl"]]
        if not offene and not stufen.get("gewonnen", {}).get("anzahl"):
            return self._panel("Auftragspipeline",
                               '<p class="leer">Noch kein Interessent erfasst.</p>')

        groesster = max([a["wert_monat"] for _, a in offene] or [1])
        inhalt = self._kacheln([
            ("Gesichert je Monat", euro(pipeline["laufender_umsatz_monat"]), "gut"),
            ("Offen je Monat", euro(pipeline["offener_wert_monat"]), ""),
            ("Realistisch", euro(pipeline["gewichteter_wert_monat"]), "akzent"),
            ("Interessenten", str(pipeline["offen"]), ""),
        ])
        if offene:
            inhalt += '<div style="margin-top:13px">'
            for name, angaben in offene:
                inhalt += balken("%s (%d)" % (name.capitalize(), angaben["anzahl"]),
                                 angaben["wert_monat"], groesster,
                                 euro(angaben["wert_monat"]))
            inhalt += '</div>'
        return self._panel("Auftragspipeline", inhalt, "breit")

    def _panel_nachfassen(self, daten: dict) -> str:
        """Wer heute drankommt. Die wichtigste Liste des Tages."""
        nachfassen = daten.get("nachfassen")
        if not nachfassen or not nachfassen.get("anzahl"):
            return self._panel("Heute nachfassen",
                               '<p class="leer">Heute ist niemand fällig.</p>')
        zeilen = []
        for eintrag in nachfassen["eintraege"][:8]:
            spaet = ('<span class="warnung">%d Tage überfällig</span>'
                     % eintrag["seit_tagen"]) if eintrag["seit_tagen"] > 0 else ""
            zeilen.append('%s <span class="grau">%s · %s</span><br>'
                          '<span class="grau">%s</span> %s'
                          % (sicher(eintrag["firma"]), sicher(eintrag["stufe"]),
                             euro(eintrag["wert_monat"]),
                             sicher(eintrag["schritt"]), spaet))
        return self._panel("Heute nachfassen", self._liste(zeilen, ""), "",
                           "%d fällig" % nachfassen["anzahl"])

    def _panel_cashflow(self, daten: dict) -> str:
        """Was in den nächsten Monaten hereinkommt."""
        cashflow = daten.get("cashflow")
        if not cashflow or not cashflow.get("monate"):
            return ""
        reihe = cashflow["monate"]
        inhalt = ('<div class="verlaufkopf"><span>Erwartete Einnahmen</span>'
                  '<b>%s je Monat gesichert</b></div>%s'
                  % (euro(cashflow["gesichert_monat"]),
                     saeulen([m["einnahmen"] for m in reihe],
                             [m["monat"][5:] for m in reihe], 62, FARBE_GUT)))
        inhalt += ('<p class="grau" style="margin-top:10px">Aus der Pipeline kommen '
                   'gewichtet %s dazu. Kosten %s je Monat (%s).</p>'
                   % (euro(cashflow["pipeline_gewichtet"]),
                      euro(cashflow["kosten_monat"]), sicher(cashflow["kostenquelle"])))
        return self._panel("Cashflow-Vorschau", inhalt, "breit", "6 Monate")

    def _panel_team(self, daten: dict) -> str:
        """Was die Fachkräfte zuletzt gemacht haben."""
        auftraege = daten.get("auftraege") or []
        zeilen = ['<span class="zeit">%s</span>%s <span class="grau">%s</span>'
                  % (sicher(a["angelegt"][11:16]), sicher(a["rolle"]),
                     sicher((a["auftrag"] or "")[:70]))
                  for a in auftraege]
        return self._panel("Was das Team gemacht hat",
                           self._liste(zeilen, "Noch kein Auftrag ans Team."))

    def _panel_termine(self, daten: dict) -> str:
        kalender = daten.get("kalender")
        if not kalender:
            return self._panel("Termine",
                               '<p class="leer">Kein Kalender eingerichtet.</p>')
        if not kalender.get("ok"):
            return self._panel("Termine", '<p class="warnung">%s</p>'
                               % sicher(kalender.get("fehler", "nicht erreichbar")))
        zeilen = ['<span class="zeit">%s %s</span>%s%s'
                  % (sicher(t["tag"]), sicher(t["uhrzeit"]), sicher(t["titel"]),
                     (' <span class="grau">%s</span>' % sicher(t["ort"])) if t["ort"] else "")
                  for t in kalender.get("termine", [])[:9]]
        inhalt = self._liste(zeilen, "Nichts eingetragen.")
        for konflikt in kalender.get("konflikte", [])[:3]:
            inhalt += '<p class="warnung">%s</p>' % sicher(konflikt["text"])
        return self._panel("Termine", inhalt, "", "nächste 3 Tage")

    def _panel_mail(self, daten: dict) -> str:
        mail = daten.get("mail")
        if not mail:
            return self._panel("Posteingang",
                               '<p class="leer">Kein Postfach eingerichtet.</p>')
        if not mail.get("ok"):
            return self._panel("Posteingang", '<p class="warnung">%s</p>'
                               % sicher(mail.get("fehler", "nicht erreichbar")))
        zeilen = []
        for eintrag in mail.get("wichtig", [])[:5] + mail.get("spaeter", [])[:4]:
            marke = "warnung" if eintrag["einstufung"] == "wichtig" else "grau"
            zeilen.append('<span class="%s">%s</span> %s<br>'
                          '<span class="grau">%s</span>'
                          % (marke, sicher(eintrag["einstufung"]),
                             sicher(eintrag["betreff"]),
                             sicher(eintrag["absender"][:60])))
        return self._panel("Posteingang", self._liste(zeilen, "Nichts Ungelesenes."),
                           "", "%d ungelesen" % mail.get("anzahl", 0))

    def _panel_offen(self, daten: dict) -> str:
        punkte = daten.get("punkte") or []
        zeilen = ['%s%s' % (sicher(p["text"]),
                            (' <span class="grau">bis %s</span>' % sicher(p["faellig"]))
                            if p["faellig"] else "")
                  for p in punkte[:12]]
        return self._panel("Noch offen", self._liste(zeilen, "Nichts offen."), "",
                           "%d" % len(punkte) if punkte else "")

    def _panel_belege(self, daten: dict) -> str:
        belege = daten.get("belege")
        if not belege:
            return ""
        if belege["anzahl"] == 0:
            inhalt = '<p class="ok">Zu allen Ausgaben liegt ein Beleg vor.</p>'
        else:
            zeilen = ['<span class="zeit">%s</span>%s <span class="grau">%s</span>'
                      % (sicher(e["datum"]), sicher(e["haendler"] or "unbekannt"),
                         euro(e["betrag"])) for e in belege["buchungen"][:8]]
            inhalt = ('<p class="warnung" style="margin-bottom:8px">%d Ausgaben ohne '
                      'Beleg, zusammen %s.</p>%s'
                      % (belege["anzahl"], euro(belege["summe"]),
                         self._liste(zeilen, "")))
        return self._panel("Fehlende Belege", inhalt)

    def _panel_leads(self, daten: dict) -> str:
        leads = daten.get("leads")
        if not leads or not leads.get("leads"):
            return self._panel("Offene Leads",
                               '<p class="leer">Kein Lead offen.</p>')
        zeilen = ['<span class="zeit">%s</span>%s <span class="grau">%s · %d Punkte</span>'
                  '<br><span class="grau">%s</span>'
                  % (sicher(l["datum"]), sicher(l["kunde"] or "ohne Namen"),
                     euro(l["volumen"]), l["punktzahl"],
                     sicher(l["naechster_schritt"] or "kein nächster Schritt vereinbart"))
                  for l in leads["leads"][:6]]
        return self._panel("Offene Leads", self._liste(zeilen, ""), "",
                           euro_kurz(leads.get("volumen_offen", 0)))

    def _panel_notizen(self, daten: dict) -> str:
        notizen = daten.get("notizen") or []
        zeilen = ['<span class="zeit">%s</span>%s' % (sicher(n["angelegt"][5:10]),
                                                      sicher(n["text"]))
                  for n in notizen]
        return self._panel("Notizen", self._liste(zeilen, "Noch keine Notizen."))

    def _panel_protokoll(self, daten: dict) -> str:
        protokoll = daten.get("protokoll") or []
        zeilen = []
        for eintrag in protokoll:
            klasse = {"ok": "ok", "abgelehnt": "achtung"}.get(eintrag["status"], "warnung")
            zeilen.append('<span class="zeit">%s</span><span class="%s">%s</span> '
                          '<span class="grau">%s</span>'
                          % (sicher(eintrag["zeit"][11:16]), klasse,
                             sicher(eintrag["werkzeug"]),
                             sicher((eintrag["ergebnis"] or "")[:90])))
        return self._panel("Was Jarvis getan hat",
                           self._liste(zeilen, "Noch nichts ausgeführt."), "breit")

    def _panel_zeitplan(self, daten: dict) -> str:
        eintraege = daten.get("zeitplan") or []
        zeilen = ['<span class="zeit">%s</span>%s' % (sicher(e["uhrzeit"]),
                                                      sicher(e["beschreibung"]))
                  for e in eintraege]
        routinen = daten.get("routinen") or {}
        inhalt = self._liste(zeilen, "Nichts geplant.")
        if routinen.get("anzahl"):
            inhalt += ('<p class="grau" style="margin-top:8px">%d Routinen: %s</p>'
                       % (routinen["anzahl"],
                          sicher(", ".join(routinen.get("namen", [])))))
        return self._panel("Zeitplan", inhalt)

    def _panel_dienste(self, daten: dict) -> str:
        dienste = daten.get("dienste") or {}
        zeilen = ['<span class="status %s"></span>%s'
                  % ("an" if aktiv else "aus", sicher(name))
                  for name, aktiv in dienste.items()]
        mcp = daten.get("mcp") or {}
        for name, angaben in (mcp.get("dienste") or {}).items():
            zeilen.append('<span class="status %s"></span>MCP %s '
                          '<span class="grau">%d Werkzeuge</span>'
                          % ("an" if angaben.get("laeuft") else "aus", sicher(name),
                             angaben.get("werkzeuge", 0)))
        return self._panel("Dienste", self._liste(zeilen, "Nichts eingerichtet."))

    # -- Kopfleiste ---------------------------------------------------------

    def _ticker(self, daten: dict) -> str:
        """Die Laufleiste ganz oben - nur echte Zahlen."""
        teile = []
        monat = daten.get("monat")
        if monat:
            teile.append("Ergebnis Monat <b>%s</b>" % euro(monat["ergebnis"]))
            teile.append("Zahllast <b>%s</b>" % euro(monat["zahllast"]))
        quote = (daten.get("belegquote") or {}).get("quote")
        if quote is not None:
            marke = "b" if quote >= 90 else "b class=\"rot\""
            teile.append("Belegquote <%s>%d%%</b>" % (marke, round(quote)))
        bedarf = daten.get("bedarf")
        if bedarf and bedarf.get("berechenbar"):
            if bedarf.get("luecke") is not None and bedarf["luecke"] > 0:
                teile.append('Es fehlen <b class="rot">%s</b> je Monat'
                             % euro(bedarf["luecke"]))
            else:
                teile.append("Nötig <b>%s</b> je Monat"
                             % euro(bedarf["noetiger_umsatz"]))
        pipeline = daten.get("pipeline")
        if pipeline and pipeline.get("ok") and pipeline.get("offen"):
            teile.append("Gesichert <b>%s</b> je Monat"
                         % euro(pipeline["laufender_umsatz_monat"]))
            teile.append("Pipeline <b>%s</b> realistisch"
                         % euro(pipeline["gewichteter_wert_monat"]))
        nachfassen = daten.get("nachfassen")
        if nachfassen and nachfassen.get("anzahl"):
            teile.append('Nachfassen <b class="rot">%d</b>' % nachfassen["anzahl"])
        leads = daten.get("leads")
        if leads and leads.get("anzahl"):
            teile.append("Offene Leads <b>%d</b> über <b>%s</b>"
                         % (leads["anzahl"], euro(leads.get("volumen_offen", 0))))
        belege = daten.get("belege")
        if belege and belege.get("anzahl"):
            teile.append('Belege fehlen <b class="rot">%d</b>' % belege["anzahl"])
        punkte = daten.get("punkte") or []
        teile.append("Offene Punkte <b>%d</b>" % len(punkte))
        if not teile:
            teile.append("Jarvis ist bereit")
        return "".join("<span>%s</span>" % teil for teil in teile)

    def _kopf(self, daten: dict, seite: str = "cockpit") -> tuple:
        """Überschrift links, Navigation rechts."""
        links = ('<div><h1>Jarvis <span>// Command Center</span></h1>'
                 '<p>%s, %s &middot; Stand %s Uhr &middot; %s</p></div>'
                 % (sicher(daten["wochentag"]), sicher(daten["datum"]),
                    sicher(daten["uhrzeit"]), sicher(daten["firma"])))
        rechts = ('<nav><a class="%s" href="dashboard.html">Cockpit</a>'
                  '<a class="%s" href="sales.html">Sales-Analyse</a></nav>'
                  % ("aktiv" if seite == "cockpit" else "",
                     "aktiv" if seite == "sales" else ""))
        return links, rechts

    # -- Bauen --------------------------------------------------------------

    def bauen(self, mit_netz: bool = False) -> dict:
        """Erzeugt ``dashboard.html`` und ``data.json``."""
        daten = self.daten_sammeln(mit_netz)
        panels = "".join(teil for teil in [
            self._panel_belegquote(daten),
            self._panel_zahlen(daten),
            self._panel_bedarf(daten),
            self._panel_erinnerungen(daten),
            self._panel_verlauf(daten),
            self._panel_vertrieb(daten),
            self._panel_pipeline(daten),
            self._panel_nachfassen(daten),
            self._panel_cashflow(daten),
            self._panel_leads(daten),
            self._panel_termine(daten),
            self._panel_offen(daten),
            self._panel_belege(daten),
            self._panel_kategorien(daten),
            self._panel_fixkosten(daten),
            self._panel_mail(daten),
            self._panel_notizen(daten),
            self._panel_protokoll(daten),
            self._panel_team(daten),
            self._panel_zeitplan(daten),
            self._panel_dienste(daten),
        ] if teil)

        links, rechts = self._kopf(daten, "cockpit")
        seite = seite_bauen(
            "Jarvis Command Center", self._ticker(daten), links, rechts,
            '<div class="raster">%s</div>' % panels,
            "Diese Seite aktualisiert sich alle 60 Sekunden von selbst. "
            "Gezeigt wird ausschließlich, was wirklich erfasst ist - "
            "leere Bereiche sind leer, nicht geschätzt.<br>"
            "Alle Daten liegen lokal auf diesem Rechner.")

        try:
            DASHBOARD_VERZEICHNIS.mkdir(parents=True, exist_ok=True)
            html_pfad = DASHBOARD_VERZEICHNIS / "dashboard.html"
            json_pfad = DASHBOARD_VERZEICHNIS / "data.json"
            html_pfad.write_text(seite, encoding="utf-8")
            json_pfad.write_text(json.dumps(daten, ensure_ascii=False, indent=2,
                                            default=str), encoding="utf-8")
        except OSError as fehler:
            return {"ok": False,
                    "fehler": "Das Dashboard ließ sich nicht schreiben: %s" % fehler}
        sales = self.verkaufsansicht.bauen()
        if not sales.get("ok"):
            print("[dashboard] Sales-Analyse: %s" % sales.get("fehler"))

        return {"ok": True, "datei": str(html_pfad), "daten": str(json_pfad),
                "sales": sales.get("datei", ""),
                "text": "Das Command Center ist gebaut: %s%s"
                        % (html_pfad,
                           ("  Sales-Analyse: %s" % sales["datei"])
                           if sales.get("ok") else "")}


# =========================================================================
# sales_view  -  Sales-Analyse - erzeugt ``dashboard/sales.html``.
# 
# Eine Seite je Kundengespräch: Punktzahl, die fünf Einzelbewertungen als
# Balken, Einwände, Stärken, Schwächen und der nächste Schritt. Links die Liste
# aller Gespräche, rechts das ausgewählte.
# 
# Die Seite kommt ohne Server aus. Umgeschaltet wird mit ein paar Zeilen
# JavaScript, die nur Sichtbarkeiten umschalten - alle Gespräche stecken schon
# in der Datei. Damit funktioniert sie auch offline und per Doppelklick.
# 
# **Es wird nichts geschätzt.** Ein Gespräch ohne Einzelbewertung zeigt seine
# Balken nicht, sondern sagt, dass es ohne Bewertung abgelegt wurde.
# =========================================================================

#!/usr/bin/env python3
# -*- coding: utf-8 -*-



# Wie ein Ergebnis eingefärbt wird.
ERGEBNIS_FARBE = {"gewonnen": FARBE_GUT, "verloren": FARBE_SCHLECHT,
                  "offen": FARBE_WARNUNG, "unklar": FARBE_AKZENT}

UMSCHALTER = """
function zeigeGespraech(kennung) {
  var alle = document.querySelectorAll('.gespraech');
  for (var i = 0; i < alle.length; i++) {
    alle[i].style.display = (alle[i].id === 'g' + kennung) ? 'block' : 'none';
  }
  var knoepfe = document.querySelectorAll('.gwahl');
  for (var j = 0; j < knoepfe.length; j++) {
    knoepfe[j].className = 'gwahl' +
      (knoepfe[j].getAttribute('data-id') === String(kennung) ? ' gewaehlt' : '');
  }
}
"""

ZUSATZ_CSS = """
.gwahl { display: block; width: 100%; text-align: left; cursor: pointer;
         background: #121517; border: 1px solid #1C1F23; border-radius: 8px;
         padding: 10px 12px; margin-bottom: 7px; color: #E6E8EA;
         font-family: inherit; font-size: 13px; }
.gwahl:hover { border-color: rgba(232,98,44,.45); }
.gwahl.gewaehlt { border-color: #E8622C; background: rgba(232,98,44,.09); }
.gwahl .kopf { display: flex; justify-content: space-between; align-items: baseline;
               gap: 8px; }
.gwahl .punkte { font-variant-numeric: tabular-nums; font-weight: 600; }
.gwahl .unten { font-size: 11px; color: #6E767D; margin-top: 3px;
                display: flex; justify-content: space-between; }
.marke { font-size: 9.5px; text-transform: uppercase; letter-spacing: .1em;
         border-radius: 4px; padding: 2px 7px; border: 1px solid; }
.zitat { background: #121517; border-left: 2px solid #1C1F23; border-radius: 0 6px 6px 0;
         padding: 10px 13px; font-size: 12.5px; color: #8A9096; line-height: 1.65;
         white-space: pre-wrap; max-height: 220px; overflow-y: auto; }
.spalten { display: grid; grid-template-columns: 1fr 1fr; gap: 13px; }
@media (max-width: 760px) { .spalten { grid-template-columns: 1fr; } }
"""


class Verkaufsansicht:
    """Baut die Sales-Analyse als einzelne HTML-Datei."""

    def __init__(self, call_analysis=None, memory=None):
        self.call_analysis = call_analysis
        self.memory = memory

    # -- Bausteine ----------------------------------------------------------

    @staticmethod
    def _marke(ergebnis: str) -> str:
        """Farbige Markierung für gewonnen, verloren, offen, unklar."""
        farbe = ERGEBNIS_FARBE.get(ergebnis, FARBE_AKZENT)
        return ('<span class="marke" style="color:%s;border-color:%s">%s</span>'
                % (farbe, farbe, sicher(ergebnis)))

    def _wahlknopf(self, zeile, gewaehlt: bool) -> str:
        """Ein Eintrag in der Gesprächsliste links."""
        return ('<button class="gwahl%s" data-id="%d" onclick="zeigeGespraech(%d)">'
                '<div class="kopf"><span>%s</span>'
                '<span class="punkte" style="color:%s">%d</span></div>'
                '<div class="unten"><span>%s</span><span>%s</span></div></button>'
                % (" gewaehlt" if gewaehlt else "", zeile["id"], zeile["id"],
                   sicher(zeile["kunde"] or "ohne Namen"),
                   ampelfarbe(zeile["punktzahl"], 70, 45), zeile["punktzahl"],
                   sicher(zeile["datum"]),
                   euro_kurz(zeile["volumen"]) if zeile["volumen"] else "–"))

    @staticmethod
    def _liste(titel: str, eintraege: list, farbe: str, leer: str) -> str:
        """Eine beschriftete Aufzählung, oder ein Hinweis, dass nichts erfasst ist."""
        if not eintraege:
            inhalt = '<p class="leer">%s</p>' % sicher(leer)
        else:
            inhalt = "<ul>%s</ul>" % "".join(
                '<li><span style="color:%s">▸</span> %s</li>' % (farbe, sicher(e))
                for e in eintraege)
        return ('<section class="panel"><h2>%s</h2>%s</section>'
                % (sicher(titel), inhalt))

    def _detail(self, zeile, sichtbar: bool) -> str:
        """Die ausführliche Ansicht eines Gesprächs."""
        bewertung = {}
        if self.call_analysis is not None:
            bewertung = self.call_analysis.bewertung_lesen(zeile)

        einwaende = _text_zu_liste(zeile["einwaende"])
        offene = _text_zu_liste(zeile["offene_einwaende"])
        staerken = _text_zu_liste(zeile["staerken"])
        schwaechen = _text_zu_liste(zeile["schwaechen"])

        kacheln = [
            ("Punktzahl", "%d / 100" % zeile["punktzahl"], ""),
            ("Volumen", euro(zeile["volumen"]) if zeile["volumen"] else "nicht beziffert",
             "akzent" if zeile["volumen"] else ""),
            ("Einwände", str(len(einwaende)), ""),
            ("davon offen", str(len(offene)),
             "schlecht" if offene else "gut"),
        ]
        kachelblock = '<div class="kacheln">%s</div>' % "".join(
            '<div class="kachel"><div class="wert %s">%s</div>'
            '<div class="name">%s</div></div>' % (k, sicher(w), sicher(n))
            for n, w, k in kacheln)

        # Ring und Einzelbewertungen
        if bewertung and self.call_analysis is not None:
            balkenblock = ""
            for schluessel, beschriftung in self.call_analysis.DIMENSIONEN:
                if schluessel not in bewertung:
                    continue
                wert = bewertung[schluessel]
                balkenblock += balken(beschriftung, wert, 10, "%.0f / 10" % wert,
                                      ampelfarbe(wert * 10, 70, 40))
        else:
            balkenblock = ('<p class="leer">Dieses Gespräch wurde ohne '
                           'Einzelbewertung abgelegt - dazu gibt es keine Balken.</p>')

        kopfteil = (
            '<section class="panel breit"><h2>%s<em>%s</em></h2>'
            '<div class="ringfeld">%s<div class="ringtext">'
            '<div class="gross">%s %s</div>'
            '<div class="klein">%s</div></div></div>'
            '<div style="margin-top:14px">%s</div></section>'
            % (sicher(zeile["kunde"] or "Gespräch ohne Namen"), sicher(zeile["datum"]),
               ring(zeile["punktzahl"], "Punkte", 132,
                    ampelfarbe(zeile["punktzahl"], 70, 45)),
               self._marke(zeile["ergebnis"]),
               euro_kurz(zeile["volumen"]) if zeile["volumen"] else "",
               sicher(zeile["naechster_schritt"] or
                      "Es ist kein nächster Schritt vereinbart worden."),
               kachelblock))

        bewertungsteil = ('<section class="panel"><h2>Einzelbewertung</h2>%s</section>'
                          % balkenblock)

        teile = [kopfteil, bewertungsteil,
                 self._liste("Das lief gut", staerken, FARBE_GUT,
                             "Nichts als Stärke festgehalten."),
                 self._liste("Das fehlte", schwaechen, FARBE_SCHLECHT,
                             "Keine Schwächen festgehalten."),
                 self._liste("Einwände", einwaende, FARBE_WARNUNG,
                             "Es kamen keine Einwände."),
                 self._liste("Unbeantwortet geblieben", offene, FARBE_SCHLECHT,
                             "Alle Einwände wurden behandelt.")]

        if (zeile["rohtext"] or "").strip():
            teile.append('<section class="panel voll"><h2>So hat er es erzählt</h2>'
                         '<div class="zitat">%s</div></section>'
                         % sicher(zeile["rohtext"]))

        return ('<div class="gespraech" id="g%d" style="display:%s">'
                '<div class="raster" style="padding:0">%s</div></div>'
                % (zeile["id"], "block" if sichtbar else "none", "".join(teile)))

    # -- Bauen --------------------------------------------------------------

    def bauen(self, ziel=None, grenze: int = 40) -> dict:
        """Erzeugt ``sales.html``."""
        jetzt = datetime.now()
        zeilen = []
        if self.call_analysis is not None:
            try:
                zeilen = self.call_analysis.gespraeche(grenze)
            except Exception as fehler:
                return {"ok": False,
                        "fehler": "Die Gespräche ließen sich nicht lesen: %s" % fehler}

        muster = {}
        if self.call_analysis is not None and zeilen:
            try:
                muster = self.call_analysis.verkaufsmuster()
            except Exception:
                muster = {}

        if not zeilen:
            inhalt = ('<div class="raster"><section class="panel voll">'
                      '<h2>Sales-Analyse</h2>'
                      '<p class="leer">Es ist noch kein Kundengespräch festgehalten. '
                      'Erzähl Jarvis, wie ein Termin gelaufen ist - er bewertet ihn '
                      'und legt ihn hier ab.</p></section></div>')
            ticker = "<span>Noch keine Gespräche erfasst</span>"
        else:
            liste = "".join(self._wahlknopf(z, index == 0)
                            for index, z in enumerate(zeilen))
            details = "".join(self._detail(z, index == 0)
                              for index, z in enumerate(zeilen))
            inhalt = ('<div class="raster">'
                      '<section class="panel schmal"><h2>Gespräche<em>%d</em></h2>%s</section>'
                      '<div style="grid-column:span 9;min-width:0">%s</div>'
                      '</div>' % (len(zeilen), liste, details))

            teile = ["Gespräche <b>%d</b>" % len(zeilen)]
            if muster.get("anzahl"):
                teile.append("Abschlussquote <b>%.0f%%</b>"
                             % muster.get("abschlussquote", 0))
                teile.append("Durchschnitt <b>%.1f</b> Punkte"
                             % muster.get("durchschnitt", 0))
                for einwand in muster.get("wiederkehrende_einwaende", [])[:1]:
                    teile.append('Einwand "%s" <b class="rot">%dx</b>'
                                 % (sicher(einwand["einwand"]), einwand["anzahl"]))
            ticker = "".join("<span>%s</span>" % t for t in teile)

        links = ('<div><h1>Jarvis <span>// Sales-Analyse</span></h1>'
                 '<p>%s, %s &middot; Stand %s Uhr &middot; %s</p></div>'
                 % (WOCHENTAGE[jetzt.weekday()], jetzt.strftime("%d.%m.%Y"),
                    jetzt.strftime("%H:%M"), sicher(FIRMA)))
        rechts = ('<nav><a href="dashboard.html">Cockpit</a>'
                  '<a class="aktiv" href="sales.html">Sales-Analyse</a></nav>')

        seite = seite_bauen("Jarvis Sales-Analyse", ticker, links, rechts, inhalt,
                            "Streng bewertet: ein freundliches Gespräch ohne Ergebnis "
                            "ist kein gutes Gespräch.<br>"
                            "Gezeigt wird nur, was wirklich erfasst wurde.")
        seite = seite.replace("</style>", ZUSATZ_CSS + "</style>")
        seite = seite.replace("</body>", "<script>%s</script>\n</body>" % UMSCHALTER)

        try:
            DASHBOARD_VERZEICHNIS.mkdir(parents=True, exist_ok=True)
            pfad = ziel or (DASHBOARD_VERZEICHNIS / "sales.html")
            with open(str(pfad), "w", encoding="utf-8") as datei:
                datei.write(seite)
        except OSError as fehler:
            return {"ok": False,
                    "fehler": "Die Sales-Analyse ließ sich nicht schreiben: %s" % fehler}
        return {"ok": True, "datei": str(pfad), "anzahl": len(zeilen),
                "text": "Die Sales-Analyse ist gebaut: %s" % pfad}


# =========================================================================
# scheduler  -  Zeitplan - automatische Briefings und geplante Routinen.
# 
# Bewusst ein Hintergrund-Thread statt cron: cron müsste eingerichtet werden, kennt
# die laufende Sitzung nicht und hinterlässt beim Deinstallieren Reste.
# 
# Zwei Entscheidungen, die den Alltag betreffen:
# 
# * **Vergangenes wird nicht nachgeholt.** Liegt ein Zeitpunkt mehr als 120 Minuten
#   zurück, wird der Job übersprungen. Ein Morgenbriefing um 15 Uhr hilft niemandem.
# * **Beim Start gilt alles Heutige als erledigt**, was schon vorbei ist. Sonst
#   würde jeder Neustart am Abend das Morgenbriefing nachschieben.
# =========================================================================

#!/usr/bin/env python3
# -*- coding: utf-8 -*-



# Wie lange ein Job nach seiner Zeit noch nachgeholt werden darf.
MAX_VERSPAETUNG_MINUTEN = 120
# Wie oft der Zeitplan nachsieht.
PRUEF_ABSTAND_SEKUNDEN = 30


def minuten_seit(uhrzeit: str, jetzt: datetime = None):
    """Minuten seit dem heutigen Zeitpunkt ``uhrzeit``. Negativ heißt: noch nicht."""
    jetzt = jetzt or datetime.now()
    try:
        stunde, minute = [int(teil) for teil in str(uhrzeit).split(":")[:2]]
    except (ValueError, TypeError):
        return None
    zeitpunkt = jetzt.replace(hour=stunde, minute=minute, second=0, microsecond=0)
    return (jetzt - zeitpunkt).total_seconds() / 60.0


def ist_faellig(uhrzeit: str, jetzt: datetime = None) -> bool:
    """Ist der Zeitpunkt erreicht und noch nicht zu lange her?

    9:00-Job um 9:30 abgefragt: ja. Um 8:00: nein, noch nicht.
    Um 14:00: nein, zu spät - das wird nicht nachgeholt.
    """
    versaeumt = minuten_seit(uhrzeit, jetzt)
    if versaeumt is None:
        return False
    return 0 <= versaeumt <= MAX_VERSPAETUNG_MINUTEN


class Scheduler:
    """Führt Briefings und zeitgesteuerte Routinen im Hintergrund aus."""

    def __init__(self, agent=None, routines=None, ausgabe=None):
        self.agent = agent
        self.routines = routines
        # ``ausgabe`` bekommt jeden erzeugten Text - im Dauerbetrieb die Stimme.
        self.ausgabe = ausgabe or (lambda text: print("[zeitplan] %s" % text))
        self.jobs = {}
        self._laeuft = False
        self._thread = None
        self._sperre = threading.Lock()

    # -- Jobs verwalten -----------------------------------------------------

    def job_anlegen(self, name: str, uhrzeit: str, aufgabe, beschreibung: str = "") -> bool:
        """Trägt einen Job ein. ``aufgabe`` ist eine Funktion ohne Argumente."""
        if not uhrzeit or not callable(aufgabe):
            return False
        with self._sperre:
            self.jobs[name] = {"uhrzeit": uhrzeit, "aufgabe": aufgabe,
                               "beschreibung": beschreibung or name, "zuletzt": ""}
        return True

    def job_entfernen(self, name: str) -> bool:
        """Nimmt einen Job wieder heraus."""
        with self._sperre:
            return self.jobs.pop(name, None) is not None

    def standardjobs_anlegen(self):
        """Legt Morgen- und Abendbriefing aus der Konfiguration an."""
        if BRIEFING_MORGENS:
            self.job_anlegen("morgenbriefing", BRIEFING_MORGENS,
                             self._morgenbriefing, "Morgenbriefing")
        if BRIEFING_ABENDS:
            self.job_anlegen("abendrueckblick", BRIEFING_ABENDS,
                             self._abendrueckblick, "Abendrückblick")
        if AUTOPILOT_AN:
            for uhrzeit in [u.strip() for u in AUTOPILOT_UHRZEITEN.split(",") if u.strip()]:
                self.job_anlegen("autopilot:%s" % uhrzeit, uhrzeit, self._autopilot,
                                 "Autopilot")

    def routinen_einhaengen(self):
        """Hängt alle Routinen mit Uhrzeit in den Zeitplan."""
        if self.routines is None:
            return 0
        anzahl = 0
        for zeile in self.routines.geplante_routinen():
            name = "routine:%s" % zeile["name"]
            if self.job_anlegen(name, zeile["uhrzeit"],
                                self._routine_starter(zeile["name"]),
                                "Routine %s" % zeile["name"]):
                anzahl += 1
        return anzahl

    def _routine_starter(self, routinen_name: str):
        """Baut die Funktion, die eine bestimmte Routine startet."""
        def starten():
            ergebnis = self.routines.routine_ausfuehren(routinen_name, self.agent)
            return ergebnis.get("text") or ergebnis.get("fehler", "")
        return starten

    # -- Ablauf -------------------------------------------------------------

    def vergangenes_abhaken(self, jetzt: datetime = None):
        """Markiert alles, was heute schon vorbei ist, als erledigt."""
        jetzt = jetzt or datetime.now()
        heute = jetzt.strftime("%Y-%m-%d")
        with self._sperre:
            for job in self.jobs.values():
                versaeumt = minuten_seit(job["uhrzeit"], jetzt)
                if versaeumt is not None and versaeumt > 0:
                    job["zuletzt"] = heute

    def faellige_jobs(self, jetzt: datetime = None) -> list:
        """Namen aller Jobs, die jetzt laufen müssten und heute noch nicht liefen."""
        jetzt = jetzt or datetime.now()
        heute = jetzt.strftime("%Y-%m-%d")
        faellig = []
        with self._sperre:
            for name, job in self.jobs.items():
                if job["zuletzt"] == heute:
                    continue
                if ist_faellig(job["uhrzeit"], jetzt):
                    faellig.append(name)
        return faellig

    def job_ausfuehren(self, name: str) -> str:
        """Führt einen Job aus und merkt sich das Datum."""
        with self._sperre:
            job = self.jobs.get(name)
        if not job:
            return ""
        try:
            ergebnis = job["aufgabe"]()
        except Exception as fehler:  # Ein kaputter Job darf den Zeitplan nicht stoppen.
            ergebnis = "Der Job %s ist fehlgeschlagen: %s" % (job["beschreibung"], fehler)
            print("[zeitplan] %s\n%s" % (ergebnis, traceback.format_exc()))
        with self._sperre:
            job["zuletzt"] = heute_datum()
        text = str(ergebnis or "").strip()
        if text:
            try:
                self.ausgabe(text)
            except Exception as fehler:
                print("[zeitplan] Ausgabe fehlgeschlagen: %s" % fehler)
        return text

    def einmal_pruefen(self, jetzt: datetime = None) -> list:
        """Ein Durchlauf: alles Fällige ausführen. Gibt die Jobnamen zurück."""
        gelaufen = []
        for name in self.faellige_jobs(jetzt):
            self.job_ausfuehren(name)
            gelaufen.append(name)
        return gelaufen

    def _schleife(self):
        """Die Hintergrundschleife - alle 30 Sekunden nachsehen."""
        while self._laeuft:
            try:
                self.einmal_pruefen()
            except Exception as fehler:
                print("[zeitplan] Fehler in der Schleife: %s" % fehler)
            for _ in range(PRUEF_ABSTAND_SEKUNDEN):
                if not self._laeuft:
                    break
                time.sleep(1)

    def start(self) -> bool:
        """Startet den Zeitplan im Hintergrund."""
        if self._laeuft:
            return False
        self.standardjobs_anlegen()
        self.routinen_einhaengen()
        self.vergangenes_abhaken()
        self._laeuft = True
        self._thread = threading.Thread(target=self._schleife, daemon=True,
                                        name="jarvis-zeitplan")
        self._thread.start()
        return True

    def stop(self):
        """Hält den Zeitplan an."""
        self._laeuft = False
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=3)

    def uebersicht(self) -> list:
        """Was wann geplant ist - für Dashboard und Selbsttest."""
        with self._sperre:
            return [{"name": name, "uhrzeit": job["uhrzeit"],
                     "beschreibung": job["beschreibung"], "zuletzt": job["zuletzt"]}
                    for name, job in sorted(self.jobs.items(),
                                            key=lambda p: p[1]["uhrzeit"])]

    # -- Die beiden Briefings ----------------------------------------------

    def _morgenbriefing(self) -> str:
        """Der Text, den Jarvis morgens von sich aus sagt."""
        if self.agent is None:
            return "Guten Morgen. Ich bin da, aber noch nicht eingerichtet."
        return self.agent.briefing_morgens()

    def _autopilot(self) -> str:
        """Der Autopilot arbeitet von selbst und meldet, was er vorbereitet hat."""
        if self.agent is None or not AUTOPILOT_AN:
            return ""
        return self.agent.tools.autopilot.laufen(self.agent).get("text", "")

    def _abendrueckblick(self) -> str:
        """Der Text, den Jarvis abends von sich aus sagt."""
        if self.agent is None:
            return "Feierabend. Eingerichtet bin ich noch nicht."
        return self.agent.briefing_abends()


# =========================================================================
# webapp  -  Web-App - Jarvis im Browser statt im Terminal.
# 
# Ein kleiner Server aus der Python-Standardbibliothek, kein Fremdpaket. Er
# liefert eine Seite aus, die im Browser läuft: dort spricht der Nutzer, dort
# antwortet Jarvis, dort steht sein Stand, und dort erteilt er Freigaben.
# 
# **Warum das Mikrofon im Browser besser ist:** Der Browser darf auf das Mikrofon
# zugreifen, sobald der Nutzer einmal erlaubt hat - ohne PortAudio, ohne
# Systemrechte fürs Terminal, und auch vom Handy aus. Die Spracherkennung von
# Safari und Chrome ist für Deutsch gut genug und kostet nichts.
# 
# **Sicherheit.** Der Server hört standardmäßig nur auf 127.0.0.1, also nur auf
# diesem Rechner. Wer ihn ins WLAN stellt, um vom Handy zuzugreifen, braucht
# zwingend einen Schlüssel in der Adresse - denn dieser Server darf Mails lesen,
# Skripte ausführen und Geld verbuchen. Ein offener Port ohne Schlüssel wäre
# fahrlässig. Zusätzlich wird der Host-Kopf geprüft, damit keine fremde Webseite
# über den Namen des Rechners hereinredet.
# =========================================================================

#!/usr/bin/env python3
# -*- coding: utf-8 -*-



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
        self.timeout = int(timeout if timeout is not None else FREIGABE_TIMEOUT)
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

    def _behandeln(self, behandler, methode: str):
        """Verteilt eine Anfrage auf die passende Antwort."""
        pfad = urlparse(behandler.path).path.rstrip("/") or "/"
        if not self._erlaubt(behandler):
            return self._antworten(behandler, 403,
                                   {"fehler": "Kein Zugang. Der Schlüssel fehlt "
                                              "oder stimmt nicht."})
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
                "nutzer": NUTZER_NAME, "firma": FIRMA,
                "modell": CLAUDE_MODEL,
                "werkzeuge": len(werkzeuge.namen()),
                "aufgaben": werkzeuge.autopilot.offen_anzahl(),
                "rollen": [r["rolle"] for r in werkzeuge.team.rollen_liste()],
                "dienste": konfig_uebersicht()})
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
                .replace("{{NUTZER_JSON}}", _fuer_skript(NUTZER_NAME))
                .replace("{{FIRMA_JSON}}", _fuer_skript(FIRMA))))
        if pfad == "/protokoll":
            return self._html(behandler, (
                PROTOKOLL_HTML
                .replace("{{SCHLUESSEL_JSON}}", _fuer_skript(self.token or ""))
                .replace("{{NUTZER_JSON}}", _fuer_skript(NUTZER_NAME))
                .replace("{{FIRMA_JSON}}", _fuer_skript(FIRMA))))
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
            datei = DASHBOARD_VERZEICHNIS / (
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
                env_setzen("ANTHROPIC_API_KEY", schluessel)
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
            env_setzen("FREIER_DIENST_URL", vorgabe["url"])
            env_setzen("FREIER_DIENST_MODELL", modell)
            env_setzen("FREIER_DIENST_SCHLUESSEL", schluessel)
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
            env_setzen("LOKALES_MODELL", probe["modell"])
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
        wurzel = DASHBOARD_VERZEICHNIS.resolve()
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


# =========================================================================
# setup_wizard  -  Ersteinrichtung - geführt, gesprochen, ohne Suchen.
# 
# Der Nutzer ist kein Entwickler. Er soll nichts nachschlagen müssen. Deshalb:
# 
# * Jeder Schritt wird **vorgelesen**, damit er nicht mitlesen muss.
# * Seiten und Systemeinstellungen werden **geöffnet**, nicht beschrieben.
# * Der Anthropic-Schlüssel wird **sofort mit einem echten Mini-Aufruf getestet**.
#   Ein Schlüssel, der erst beim ersten Gespräch auffällt, hilft niemandem.
# * Die drei Rechte werden **einzeln geprüft**, und nur die fehlenden werden
#   geöffnet. Wer schon alles erlaubt hat, soll nicht drei Fenster wegklicken.
# =========================================================================

#!/usr/bin/env python3
# -*- coding: utf-8 -*-



ANTHROPIC_SEITE = "https://console.anthropic.com/settings/keys"

# Direktlinks in die Systemeinstellungen - beschreiben hilft ihm nicht.
EINSTELLUNG_MIKROFON = ("x-apple.systempreferences:com.apple.preference.security"
                        "?Privacy_Microphone")
EINSTELLUNG_BILDSCHIRM = ("x-apple.systempreferences:com.apple.preference.security"
                          "?Privacy_ScreenCapture")
EINSTELLUNG_BEDIENHILFEN = ("x-apple.systempreferences:com.apple.preference.security"
                            "?Privacy_Accessibility")
EINSTELLUNG_KAMERA = ("x-apple.systempreferences:com.apple.preference.security"
                      "?Privacy_Camera")
EINSTELLUNG_SPRACHE = "x-apple.systempreferences:com.apple.preference.speech"

# Kein Einzelunternehmer kennt seinen IMAP-Servernamen. Er tippt seine
# Mailadresse ein, den Rest wissen wir selbst.
MAIL_ANBIETER = {
    "gmail.com": ("imap.gmail.com", 993, "smtp.gmail.com", 587, True),
    "googlemail.com": ("imap.gmail.com", 993, "smtp.gmail.com", 587, True),
    "gmx.at": ("imap.gmx.net", 993, "mail.gmx.net", 587, False),
    "gmx.de": ("imap.gmx.net", 993, "mail.gmx.net", 587, False),
    "gmx.net": ("imap.gmx.net", 993, "mail.gmx.net", 587, False),
    "web.de": ("imap.web.de", 993, "smtp.web.de", 587, False),
    "outlook.com": ("outlook.office365.com", 993, "smtp-mail.outlook.com", 587, True),
    "hotmail.com": ("outlook.office365.com", 993, "smtp-mail.outlook.com", 587, True),
    "live.com": ("outlook.office365.com", 993, "smtp-mail.outlook.com", 587, True),
    "live.at": ("outlook.office365.com", 993, "smtp-mail.outlook.com", 587, True),
    "icloud.com": ("imap.mail.me.com", 993, "smtp.mail.me.com", 587, True),
    "me.com": ("imap.mail.me.com", 993, "smtp.mail.me.com", 587, True),
    "t-online.de": ("secureimap.t-online.de", 993, "securesmtp.t-online.de", 587, False),
    "yahoo.com": ("imap.mail.yahoo.com", 993, "smtp.mail.yahoo.com", 587, True),
    "yahoo.de": ("imap.mail.yahoo.com", 993, "smtp.mail.yahoo.com", 587, True),
    "a1.net": ("imap.a1.net", 993, "smtp.a1.net", 587, False),
    "aon.at": ("imap.a1.net", 993, "smtp.a1.net", 587, False),
}

# Drei Routinen, die von Anfang an da sind.
STARTROUTINEN = [
    ("Wochenrückblick",
     "Fasse die letzte Woche zusammen: Zahlen des Monats, gewonnene und verlorene "
     "Gespräche, offene Leads mit Volumen, fehlende Belege und was liegen geblieben "
     "ist. Nenne konkret, was diese Woche zuerst drankommt.", ""),
    ("Belege prüfen",
     "Sieh nach, zu welchen Ausgaben noch kein Beleg hinterlegt ist. Nenne Betrag, "
     "Händler und Datum der größten fehlenden Belege und erinnere daran, sie zu "
     "fotografieren.", ""),
    ("Nachfassen",
     "Zeige alle offenen Leads. Für jeden: wie lange er schon offen ist, welches "
     "Volumen dahinter steht und welcher nächste Schritt vereinbart war. Sag mir, "
     "bei wem ich heute anrufen sollte und warum.", ""),
]


def schluessel_online_testen(schluessel: str) -> dict:
    """Prüft einen Schlüssel mit einem echten, winzigen Aufruf."""
    koerper = json.dumps({
        "model": CLAUDE_MODEL, "max_tokens": 8,
        "messages": [{"role": "user", "content": "Sag nur: ok"}],
    }).encode("utf-8")
    anfrage = urllib.request.Request(
        "https://api.anthropic.com/v1/messages", data=koerper, method="POST",
        headers={"x-api-key": schluessel, "anthropic-version": "2023-06-01",
                 "content-type": "application/json"})
    try:
        with urllib.request.urlopen(anfrage, timeout=45) as antwort:
            antwort.read()
        return {"ok": True, "text": "Der Schlüssel funktioniert."}
    except urllib.error.HTTPError as fehler:
        try:
            inhalt = fehler.read().decode("utf-8")
            meldung = (json.loads(inhalt).get("error") or {}).get("message", inhalt)
        except (ValueError, OSError):
            meldung = str(fehler)
        if fehler.code == 401:
            return {"ok": False, "grund": "schluessel",
                    "text": "Der Schlüssel wird abgelehnt. Vermutlich ist beim "
                            "Kopieren etwas verloren gegangen. Bitte noch einmal "
                            "vollständig kopieren."}
        if fehler.code == 400 and "credit" in meldung.lower():
            return {"ok": False, "grund": "guthaben",
                    "text": "Der Schlüssel stimmt, aber auf dem Konto ist kein "
                            "Guthaben. Bitte auf der Anthropic-Seite unter Billing "
                            "etwas aufladen."}
        if fehler.code == 429:
            return {"ok": False, "grund": "zuviel",
                    "text": "Zu viele Anfragen auf einmal. Ich warte kurz und "
                            "versuche es noch einmal."}
        if fehler.code == 404:
            return {"ok": False, "grund": "modell",
                    "text": "Das eingestellte Modell %s kennt die Schnittstelle "
                            "nicht." % CLAUDE_MODEL}
        return {"ok": False, "grund": "sonstiges",
                "text": "Die Prüfung ist fehlgeschlagen: %s" % meldung[:200]}
    except (urllib.error.URLError, OSError) as fehler:
        return {"ok": False, "grund": "netz",
                "text": "Keine Verbindung zu Anthropic. Ist das Internet da? (%s)"
                        % fehler}


class Einrichtung:
    """Führt den Nutzer Schritt für Schritt durch die Ersteinrichtung."""

    def __init__(self, stimme=None):
        self.stimme = stimme
        self.ergebnisse = {}

    # -- Ausgabe ------------------------------------------------------------

    def sagen(self, text: str):
        """Schreibt und spricht einen Satz."""
        print("\n%s" % text)
        if self.stimme is not None:
            self.stimme.sprich(text)
        elif shutil.which("say"):
            try:
                subprocess.run(["say", "-r", str(int(SPEECH_RATE)), text[:2000]],
                               timeout=120, shell=False,
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            except (OSError, subprocess.SubprocessError):
                pass

    @staticmethod
    def fragen(frage: str) -> str:
        """Liest eine Eingabe vom Terminal."""
        try:
            return input("%s " % frage).strip()
        except (EOFError, KeyboardInterrupt):
            return ""

    @staticmethod
    def oeffnen(ziel: str) -> bool:
        """Öffnet eine Seite oder eine Systemeinstellung."""
        if not shutil.which("open"):
            print("Bitte von Hand öffnen: %s" % ziel)
            return False
        try:
            subprocess.run(["open", ziel], timeout=20, shell=False,
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return True
        except (OSError, subprocess.SubprocessError):
            return False

    # -- Schritt 1: Stimme --------------------------------------------------

    def schritt_stimme(self) -> bool:
        """Sucht eine deutsche Systemstimme, sonst öffnet sich die Einstellung."""
        if not shutil.which("say"):
            self.ergebnisse["stimme"] = "kein say - kein Mac?"
            print("[--] Die Sprachausgabe 'say' gibt es nur auf einem Mac.")
            return False
        gefunden = ""
        try:
            ergebnis = subprocess.run(["say", "-v", "?"], capture_output=True,
                                      text=True, timeout=10, shell=False)
            for zeile in ergebnis.stdout.splitlines():
                teile = zeile.split()
                if len(teile) >= 2 and teile[1] in ("de_DE", "de_AT", "de_CH"):
                    gefunden = teile[0]
                    if teile[0] in ("Markus", "Yannick", "Petra", "Anna", "Viktor"):
                        break
        except (OSError, subprocess.SubprocessError):
            pass

        if gefunden:
            env_setzen("MACOS_STIMME", gefunden)
            self.ergebnisse["stimme"] = gefunden
            self.sagen("Ich habe die deutsche Stimme %s gefunden und benutze sie." % gefunden)
            return True

        self.ergebnisse["stimme"] = "keine"
        self.sagen("Auf diesem Mac ist keine deutsche Stimme installiert. Ich öffne die "
                   "Einstellung. Lade dort bitte eine deutsche Stimme herunter, zum "
                   "Beispiel Markus oder Anna.")
        self.oeffnen(EINSTELLUNG_SPRACHE)
        self.fragen("Drücke Enter, wenn du fertig bist:")
        return False

    # -- Schritt 2: Anthropic-Schlüssel ------------------------------------

    def schluessel_testen(self, schluessel: str) -> dict:
        """Prüft einen Schlüssel mit einem echten, winzigen Aufruf."""
        return schluessel_online_testen(schluessel)

    def schritt_schluessel(self) -> bool:
        """Holt den Schlüssel und prüft ihn - bis zu vier Versuche."""
        if ANTHROPIC_API_KEY:
            self.sagen("Ich prüfe den hinterlegten Schlüssel.")
            probe = self.schluessel_testen(ANTHROPIC_API_KEY)
            if probe.get("ok"):
                self.ergebnisse["schluessel"] = "vorhanden und geprüft"
                self.sagen("Der hinterlegte Schlüssel funktioniert.")
                return True
            self.sagen(probe["text"])

        self.sagen("Jetzt brauche ich deinen Anthropic-Schlüssel. Ich öffne die Seite. "
                   "Melde dich an, drücke auf Create Key, kopiere den Schlüssel und "
                   "füge ihn hier ein.")
        self.oeffnen(ANTHROPIC_SEITE)

        for versuch in range(1, 5):
            schluessel = self.fragen("Schlüssel hier einfügen und Enter drücken:")
            if not schluessel:
                self.sagen("Ich habe nichts bekommen. Versuch %d von 4." % versuch)
                continue
            if not schluessel.startswith("sk-"):
                self.sagen("Das sieht nicht nach einem Anthropic-Schlüssel aus - die "
                           "beginnen mit s k Bindestrich. Bitte noch einmal.")
                continue
            self.sagen("Ich probiere den Schlüssel aus.")
            probe = self.schluessel_testen(schluessel)
            if probe.get("ok"):
                env_setzen("ANTHROPIC_API_KEY", schluessel)
                self.ergebnisse["schluessel"] = "geprüft"
                self.sagen("Der Schlüssel funktioniert. Damit kann ich denken.")
                return True
            self.sagen(probe["text"])
            if probe.get("grund") == "guthaben":
                env_setzen("ANTHROPIC_API_KEY", schluessel)
                self.ergebnisse["schluessel"] = "gespeichert, kein Guthaben"
                self.oeffnen("https://console.anthropic.com/settings/billing")
                return False
            if probe.get("grund") == "zuviel":
                time.sleep(8)
            if probe.get("grund") == "netz":
                return False

        self.ergebnisse["schluessel"] = "fehlgeschlagen"
        self.sagen("Der Schlüssel hat nach vier Versuchen nicht funktioniert. Alles "
                   "andere richte ich trotzdem ein. Du kannst ihn später eintragen mit: "
                   "python3 jarvis.py einrichten")
        return False

    # -- Schritt 3: Die drei Rechte ----------------------------------------

    def recht_mikrofon(self) -> bool:
        """Prüft das Mikrofon, indem wirklich ein Eingabestrom geöffnet wird."""
        try:
            import sounddevice
        except (ImportError, OSError):
            self.ergebnisse["mikrofon"] = "Paket sounddevice fehlt"
            return False
        try:
            strom = sounddevice.InputStream(samplerate=16000, channels=1)
            strom.start()
            strom.stop()
            strom.close()
            self.ergebnisse["mikrofon"] = "erlaubt"
            return True
        except Exception:
            self.ergebnisse["mikrofon"] = "nicht erlaubt"
            return False

    def recht_bildschirm(self) -> bool:
        """Prüft die Bildschirmaufnahme.

        Ohne dieses Recht liefert macOS ein schwarzes Bild statt einer Fehlermeldung.
        Deshalb wird gezählt, wie viele verschiedene Farben darin vorkommen: mehr
        als drei bedeutet, dass wirklich der Bildschirm zu sehen ist.
        """
        try:
            import pyautogui
        except Exception:
            self.ergebnisse["bildschirm"] = "Paket pyautogui fehlt"
            return False
        try:
            bild = pyautogui.screenshot()
            klein = bild.convert("RGB").resize((80, 50))
            farben = {klein.getpixel((x, y)) for x in range(0, 80, 2)
                      for y in range(0, 50, 2)}
            if len(farben) > 3:
                self.ergebnisse["bildschirm"] = "erlaubt"
                return True
            self.ergebnisse["bildschirm"] = "nicht erlaubt (schwarzes Bild)"
            return False
        except Exception as fehler:
            self.ergebnisse["bildschirm"] = "nicht prüfbar: %s" % fehler
            return False

    def recht_bedienhilfen(self) -> bool:
        """Prüft die Bedienungshilfen über einen echten AppleScript-Aufruf."""
        if not shutil.which("osascript"):
            self.ergebnisse["bedienhilfen"] = "kein osascript"
            return False
        skript = ('tell application "System Events" to return count of processes')
        try:
            ergebnis = subprocess.run(["osascript", "-e", skript], capture_output=True,
                                      text=True, timeout=20, shell=False)
        except (OSError, subprocess.SubprocessError):
            self.ergebnisse["bedienhilfen"] = "nicht prüfbar"
            return False
        if ergebnis.returncode == 0 and (ergebnis.stdout or "").strip().isdigit():
            self.ergebnisse["bedienhilfen"] = "erlaubt"
            return True
        self.ergebnisse["bedienhilfen"] = "nicht erlaubt"
        return False

    def recht_kamera(self) -> bool:
        """Prüft die Kamera, indem wirklich ein Bild aufgenommen wird.

        Ein Test ist ehrlicher als ein Hinweis: Fehlt das Recht, liefert macOS
        keine Fehlermeldung, sondern eine unbrauchbare Datei.
        """
        kamera = Kamera()
        if not kamera.verfuegbar():
            self.ergebnisse["kamera"] = "kein Aufnahmeprogramm"
            return False
        ergebnis = kamera.bild_aufnehmen()
        if ergebnis.get("ok"):
            try:
                os.remove(ergebnis["pfad"])
            except OSError:
                pass
            self.ergebnisse["kamera"] = "erlaubt"
            return True
        self.ergebnisse["kamera"] = "nicht erlaubt"
        return False

    def schritt_rechte(self):
        """Prüft alle drei Rechte einzeln und öffnet nur die fehlenden."""
        self.sagen("Jetzt prüfe ich die drei Rechte, die ich brauche.")

        fehlend = []
        if self.recht_mikrofon():
            print("[ok] Mikrofon")
        else:
            print("[!!] Mikrofon: %s" % self.ergebnisse["mikrofon"])
            fehlend.append(("Mikrofon", EINSTELLUNG_MIKROFON,
                            "damit ich dich hören kann"))
        if self.recht_bildschirm():
            print("[ok] Bildschirmaufnahme")
        else:
            print("[!!] Bildschirmaufnahme: %s" % self.ergebnisse["bildschirm"])
            fehlend.append(("Bildschirmaufnahme", EINSTELLUNG_BILDSCHIRM,
                            "damit ich den Bildschirm sehen kann"))
        if self.recht_bedienhilfen():
            print("[ok] Bedienungshilfen")
        else:
            print("[!!] Bedienungshilfen: %s" % self.ergebnisse["bedienhilfen"])
            fehlend.append(("Bedienungshilfen", EINSTELLUNG_BEDIENHILFEN,
                            "damit ich klicken und tippen kann"))

        # Die Kamera ist ein eigenes Recht - ohne sie kann ich mich nicht umsehen.
        if self.recht_kamera():
            print("[ok] Kamera")
        elif self.ergebnisse["kamera"] == "kein Aufnahmeprogramm":
            print("[--] Kamera: es fehlt das Programm imagesnap")
            self.sagen("Zum Fotografieren fehlt noch ein kleines Programm. Führe "
                       "später im Terminal brew install imagesnap aus, dann kann "
                       "ich mich für dich umsehen.")
        else:
            print("[!!] Kamera: %s" % self.ergebnisse["kamera"])
            fehlend.append(("Kamera", EINSTELLUNG_KAMERA,
                            "damit ich einen Beleg oder ein Objekt ansehen kann"))

        if not fehlend:
            self.sagen("Alle drei Rechte sind bereits erteilt.")
            return

        self.sagen("Es fehlen %d Rechte. Ich öffne die Einstellungen einzeln. Setze dort "
                   "jeweils den Haken beim Terminal." % len(fehlend))
        for name, ziel, zweck in fehlend:
            self.sagen("Jetzt %s, %s." % (name, zweck))
            self.oeffnen(ziel)
            self.fragen("Enter, wenn der Haken gesetzt ist:")

    # -- Schritt 4: Angaben zur Person -------------------------------------

    def schritt_person(self):
        """Fragt Name, Firma und Ort ab."""
        name = self.fragen("Wie soll ich dich nennen? (Enter für '%s')"
                           % NUTZER_NAME)
        if name:
            env_setzen("NUTZER_NAME", name)
        firma = self.fragen("Wie heißt deine Firma? (Enter zum Überspringen)")
        if firma:
            env_setzen("FIRMA", firma)
        ort = self.fragen("In welchem Ort arbeitest du? (Enter für '%s')"
                          % WETTER_ORT)
        if ort:
            env_setzen("WETTER_ORT", ort)
        mwst = self.fragen("Welcher Mehrwertsteuersatz gilt bei dir? (Enter für %g)"
                           % STANDARD_MWST)
        if mwst:
            try:
                env_setzen("STANDARD_MWST", float(mwst.replace(",", ".")))
            except ValueError:
                print("Das war keine Zahl - ich bleibe bei %g." % STANDARD_MWST)
        self.ergebnisse["person"] = NUTZER_NAME

    # -- Schritt 5: Telegram ------------------------------------------------

    def schritt_telegram(self):
        """Richtet Telegram ein - der Weg für Freigaben unterwegs."""
        self.sagen("Telegram ist der Weg, über den ich dich um Freigaben bitte, wenn du "
                   "nicht am Rechner sitzt. Das ist freiwillig. Ohne Telegram frage ich "
                   "im Terminal.")
        antwort = self.fragen("Telegram jetzt einrichten? (ja/nein)").lower()
        if antwort not in ("ja", "j", "yes", "y"):
            self.ergebnisse["telegram"] = "übersprungen"
            return
        self.sagen("Öffne Telegram, suche den BotFather, schicke ihm slash newbot und "
                   "folge den Anweisungen. Am Ende bekommst du einen Token.")
        token = self.fragen("Bot-Token hier einfügen:")
        if not token:
            self.ergebnisse["telegram"] = "kein Token"
            return
        env_setzen("TELEGRAM_BOT_TOKEN", token)
        self.sagen("Schreibe deinem neuen Bot jetzt irgendeine Nachricht in Telegram, "
                   "dann drücke hier Enter.")
        self.fragen("Enter, wenn du dem Bot geschrieben hast:")
        chat_id = self._chat_id_holen(token)
        if chat_id:
            env_setzen("TELEGRAM_CHAT_ID", chat_id)
            self.ergebnisse["telegram"] = "eingerichtet"
            self.sagen("Telegram ist eingerichtet. Ich schicke dir eine Testnachricht.")
            self._telegram_test(token, chat_id)
        else:
            self.ergebnisse["telegram"] = "keine Nachricht gefunden"
            self.sagen("Ich habe keine Nachricht gefunden. Du kannst das später "
                       "nachholen.")

    # -- Schritt 5b: Telefon ------------------------------------------------

    def schritt_telefon(self):
        """Richtet das Telefon ein - Anrufe und SMS über Twilio."""
        self.sagen("Wenn du willst, kann ich für dich anrufen und SMS schicken - zum "
                   "Beispiel eine Terminbestätigung an einen Kunden. Das läuft über "
                   "einen Dienst namens Twilio und kostet ein paar Cent pro Anruf. "
                   "Freiwillig. Ohne das funktioniert alles andere genauso.")
        antwort = self.fragen("Telefon jetzt einrichten? (ja/nein)").lower()
        if antwort not in ("ja", "j", "yes", "y"):
            self.ergebnisse["telefon"] = "übersprungen"
            return
        self.sagen("Geh auf twilio Punkt com, melde dich an und kauf dir dort eine "
                   "Telefonnummer. Auf der Startseite stehen dann zwei Werte: Account "
                   "SID und Auth Token.")
        sid = self.fragen("Account SID (beginnt mit AC):")
        if not sid.startswith("AC"):
            self.ergebnisse["telefon"] = "SID sieht nicht richtig aus"
            self.sagen("Die SID beginnt normalerweise mit A C. Ich lasse das Telefon "
                       "erst mal aus, du kannst es später nachholen.")
            return
        token = self.fragen("Auth Token:")
        if not token:
            self.ergebnisse["telefon"] = "kein Token"
            return
        nummer = self.fragen("Deine gekaufte Twilio-Nummer (international, z.B. +43...):")
        geprueft, fehler = nummer_pruefen(nummer)
        if geprueft is None:
            self.ergebnisse["telefon"] = "Nummer unklar"
            self.sagen(fehler)
            return
        env_setzen("TWILIO_SID", sid)
        env_setzen("TWILIO_TOKEN", token)
        env_setzen("TWILIO_NUMMER", geprueft)
        TWILIO_SID, TWILIO_TOKEN, TWILIO_NUMMER = sid, token, geprueft
        self.ergebnisse["telefon"] = "eingerichtet"
        self.sagen("Das Telefon ist eingerichtet. Ich frage dich vor jedem Anruf und "
                   "vor jeder SMS um Erlaubnis.")

    @staticmethod
    def _chat_id_holen(token: str) -> str:
        """Liest die Chat-Nummer aus der ersten Nachricht an den Bot."""
        try:
            ziel = "https://api.telegram.org/bot%s/getUpdates" % token
            with urllib.request.urlopen(ziel, timeout=25) as antwort:
                daten = json.loads(antwort.read().decode("utf-8"))
            for eintrag in reversed(daten.get("result", []) or []):
                chat = ((eintrag.get("message") or {}).get("chat") or {})
                if chat.get("id"):
                    return str(chat["id"])
        except (urllib.error.URLError, OSError, ValueError):
            pass
        return ""

    @staticmethod
    def _telegram_test(token: str, chat_id: str):
        """Schickt eine Testnachricht."""
        try:
            koerper = json.dumps({"chat_id": chat_id,
                                  "text": "Jarvis ist eingerichtet. Über diesen Chat "
                                          "frage ich dich künftig um Freigaben."}
                                 ).encode("utf-8")
            anfrage = urllib.request.Request(
                "https://api.telegram.org/bot%s/sendMessage" % token, data=koerper,
                method="POST", headers={"Content-Type": "application/json"})
            urllib.request.urlopen(anfrage, timeout=20).read()
        except (urllib.error.URLError, OSError, ValueError):
            pass

    # -- Schritt 5b: E-Mail -------------------------------------------------

    def mail_testen(self, host: str, port: int, benutzer: str, passwort: str) -> dict:
        """Meldet sich wirklich am Posteingang an, statt es nur zu hoffen."""
        try:
            verbindung = imaplib.IMAP4_SSL(host, int(port),
                                           ssl_context=ssl.create_default_context())
            try:
                verbindung.login(benutzer, passwort)
                verbindung.select("INBOX")
                status, daten = verbindung.search(None, "UNSEEN")
                anzahl = len(daten[0].split()) if status == "OK" and daten[0] else 0
            finally:
                try:
                    verbindung.logout()
                except (imaplib.IMAP4.error, OSError):
                    pass
            return {"ok": True, "ungelesen": anzahl}
        except imaplib.IMAP4.error as fehler:
            meldung = str(fehler).lower()
            if "credential" in meldung or "auth" in meldung or "login" in meldung:
                return {"ok": False, "grund": "zugang",
                        "text": "Der Mailserver lehnt Benutzer oder Passwort ab."}
            return {"ok": False, "grund": "sonstiges",
                    "text": "Der Posteingang antwortet nicht wie erwartet: %s"
                            % str(fehler)[:150]}
        except (ssl.SSLError, OSError) as fehler:
            return {"ok": False, "grund": "netz",
                    "text": "Der Server %s ist nicht erreichbar: %s" % (host, fehler)}

    def schritt_mail(self):
        """Richtet Posteingang und Versand ein - mit Servererkennung aus der Adresse."""
        self.sagen("Jetzt dein Postfach. Damit lese ich morgens deine Mails und "
                   "sortiere sie vor. Das ist freiwillig.")
        antwort = self.fragen("E-Mail jetzt einrichten? (ja/nein)").lower()
        if antwort not in ("ja", "j", "yes", "y"):
            self.ergebnisse["email"] = "übersprungen"
            return

        for versuch in range(1, 4):
            adresse = self.fragen("Deine E-Mail-Adresse:")
            if "@" not in adresse:
                self.sagen("Das sieht nicht nach einer Mailadresse aus.")
                continue
            domain = adresse.split("@")[-1].strip().lower()
            bekannt = MAIL_ANBIETER.get(domain)

            if bekannt:
                imap_host, imap_port, smtp_host, smtp_port, app_passwort = bekannt
                self.sagen("Deinen Anbieter kenne ich, die Servernamen trage ich "
                           "selbst ein.")
            else:
                app_passwort = False
                self.sagen("Deinen Anbieter kenne ich nicht. Die beiden Servernamen "
                           "stehen bei deinem Anbieter unter Mail-Einstellungen.")
                imap_host = self.fragen("Posteingangs-Server (IMAP), z.B. imap.firma.at:")
                smtp_host = self.fragen("Postausgangs-Server (SMTP), z.B. smtp.firma.at:")
                imap_port, smtp_port = 993, 587
                if not imap_host or not smtp_host:
                    self.ergebnisse["email"] = "keine Server angegeben"
                    return

            if app_passwort:
                self.sagen("Wichtig bei diesem Anbieter: Das normale Passwort "
                           "funktioniert nicht. Du brauchst ein sogenanntes "
                           "App-Passwort. Ich öffne die Seite, auf der du es "
                           "erzeugst.")
                self.oeffnen({"gmail.com": "https://myaccount.google.com/apppasswords",
                              "googlemail.com": "https://myaccount.google.com/apppasswords",
                              "icloud.com": "https://account.apple.com/account/manage",
                              "me.com": "https://account.apple.com/account/manage",
                              }.get(domain, "https://account.live.com/proofs/manage"))

            passwort = self.fragen("Passwort (oder App-Passwort):")
            if not passwort:
                self.sagen("Ohne Passwort geht es nicht.")
                continue

            self.sagen("Ich melde mich einmal an, um zu sehen, ob es stimmt.")
            probe = self.mail_testen(imap_host, imap_port, adresse, passwort)
            if probe.get("ok"):
                env_setzen("IMAP_HOST", imap_host)
                env_setzen("IMAP_PORT", imap_port)
                env_setzen("IMAP_USER", adresse)
                env_setzen("IMAP_PASSWORT", passwort)
                env_setzen("SMTP_HOST", smtp_host)
                env_setzen("SMTP_PORT", smtp_port)
                env_setzen("SMTP_USER", adresse)
                env_setzen("SMTP_PASSWORT", passwort)
                env_setzen("SMTP_ABSENDER", adresse)
                self.ergebnisse["email"] = "eingerichtet"
                self.sagen("Das Postfach ist verbunden. Gerade liegen dort %d "
                           "ungelesene Mails." % probe["ungelesen"])
                return
            self.sagen(probe["text"])
            if probe.get("grund") == "zugang" and app_passwort:
                self.sagen("Bei diesem Anbieter ist das fast immer das normale "
                           "Passwort statt des App-Passworts. Versuch %d von 3."
                           % versuch)

        self.ergebnisse["email"] = "fehlgeschlagen"
        self.sagen("Das Postfach hat nicht funktioniert. Alles andere richte ich "
                   "trotzdem ein. Du kannst es später nachholen.")

    # -- Schritt 6: Startroutinen ------------------------------------------

    def schritt_routinen(self):
        """Legt die drei Startroutinen an."""
        routinen = Routines(Memory())
        angelegt = []
        for name, anweisung, uhrzeit in STARTROUTINEN:
            ergebnis = routinen.routine_anlegen(name, anweisung, uhrzeit)
            if ergebnis.get("ok"):
                angelegt.append(name)
        self.ergebnisse["routinen"] = angelegt
        self.sagen("Ich habe drei Routinen für dich angelegt: %s. Du rufst sie auf, "
                   "indem du einfach ihren Namen sagst." % ", ".join(angelegt))

    # -- Schritt 7: Stimmprofil --------------------------------------------

    def schritt_stimmprofil(self):
        """Bietet an, die Stimme einzulernen."""
        self.sagen("Zum Schluss kann ich deine Stimme einlernen. Dann reagiere ich "
                   "bevorzugt auf dich. Wichtig zu wissen: Das unterscheidet Sprecher "
                   "im Alltag zuverlässig, ist aber kein Schutz gegen eine abgespielte "
                   "Aufnahme. Deshalb gibt die Stimme allein nie eine Mail oder eine "
                   "Buchung frei. Sie entscheidet nur, ob ich zuhöre.")
        antwort = self.fragen("Stimme jetzt einlernen? (ja/nein)").lower()
        if antwort not in ("ja", "j", "yes", "y"):
            self.ergebnisse["stimmprofil"] = "übersprungen"
            return
        profil = Sprecherprofil()
        ergebnis = profil.einlernen(self.stimme or Stimme())
        if ergebnis.get("ok"):
            env_setzen("STIMMPRUEFUNG_AN", "ja")
            self.ergebnisse["stimmprofil"] = "angelegt"
            self.sagen(ergebnis.get("text", "Stimmprofil angelegt."))
        else:
            self.ergebnisse["stimmprofil"] = ergebnis.get("fehler", "fehlgeschlagen")
            self.sagen(ergebnis.get("fehler", "Das Einlernen hat nicht geklappt."))

    # -- Ablauf -------------------------------------------------------------

    def durchlaufen(self) -> dict:
        """Führt die ganze Einrichtung durch."""
        verzeichnisse_anlegen()
        vorlage_schreiben()

        self.sagen("Hallo. Ich bin Jarvis und richte mich jetzt einmalig ein. Das "
                   "dauert ein paar Minuten. Ich lese dir alles vor, du musst nichts "
                   "mitlesen.")

        self.schritt_stimme()
        self.schritt_person()
        self.schritt_schluessel()
        self.schritt_rechte()
        self.schritt_telegram()
        self.schritt_telefon()
        self.schritt_mail()
        self.schritt_routinen()
        self.schritt_stimmprofil()

        env_setzen("EINRICHTUNG_FERTIG", "ja")

        print("\n" + "=" * 60)
        print("EINRICHTUNG ABGESCHLOSSEN")
        print("=" * 60)
        for name, wert in self.ergebnisse.items():
            print("  %-14s %s" % (name + ":", wert))
        print("=" * 60)

        self.sagen("Fertig. Eine Sache noch, und die ist wichtig: Du musst das Terminal "
                   "jetzt einmal komplett schließen und neu öffnen. Sonst greifen die "
                   "erteilten Rechte nicht. Danach startest du mich einfach wieder über "
                   "JARVIS Punkt command. Dann sag: Hey Jarvis, wie sieht mein Tag aus.")
        return self.ergebnisse


def einrichtung_starten(stimme=None) -> dict:
    """Startet die geführte Ersteinrichtung."""
    return Einrichtung(stimme).durchlaufen()


# =========================================================================
# autopilot  -  Autopilot - Jarvis arbeitet von selbst, ohne dass man ihn anstößt.
# 
# Zweimal am Tag (und auf Knopfdruck) macht er die Vorarbeit, die sonst liegen
# bleibt, und legt das Ergebnis auf die Seite "Heute zu tun":
# 
# 1. **Neue Betriebe** aus OpenStreetMap - kostenlos, ohne Schlüssel - für den
#    eigenen Ort und die gewählten Branchen. Zu jedem schreibt er ein kurzes
#    Anruf-Skript.
# 2. **Nachfassen**: Wer laut Pipeline heute dran ist.
# 3. **Posteingang**: Zu wichtigen Mails entwirft er eine Antwort.
# 4. **Cashflow**: Läuft ein Monat ins Minus, sagt er es.
# 
# **Was er bewusst nicht tut: von selbst Mails an fremde Firmen schicken.**
# Werbemails ohne Einwilligung sind in Österreich und Deutschland in der Regel
# unzulässig, und ein Postfach, das Kaltmails verschickt, wird schnell gesperrt.
# Gesendet wird erst, wenn der Nutzer auf der Seite klickt - der Klick ist die
# Freigabe. Neue Betriebe bekommen deshalb ein Anruf-Skript, keine Mail.
# 
# **Robust ohne Gehirn:** Ist der Gratis-Dienst gerade ausgelastet, nimmt er
# Vorlagen statt selbst geschriebener Texte. Die Arbeit bleibt nicht liegen, nur
# weil ein Kontingent leer ist.
# =========================================================================

#!/usr/bin/env python3
# -*- coding: utf-8 -*-



SCHEMA_AUTOPILOT = """
CREATE TABLE IF NOT EXISTS autopilot_aufgaben (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    schluessel TEXT NOT NULL,
    art TEXT NOT NULL,
    titel TEXT NOT NULL,
    firma TEXT DEFAULT '',
    an TEXT DEFAULT '',
    betreff TEXT DEFAULT '',
    text TEXT DEFAULT '',
    grund TEXT DEFAULT '',
    lead_id INTEGER DEFAULT 0,
    status TEXT DEFAULT 'offen',
    angelegt TEXT NOT NULL,
    erledigt_am TEXT DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_autopilot_status ON autopilot_aufgaben(status);
CREATE INDEX IF NOT EXISTS idx_autopilot_schluessel ON autopilot_aufgaben(schluessel);
CREATE TABLE IF NOT EXISTS autopilot_laeufe (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    start TEXT NOT NULL,
    ende TEXT DEFAULT '',
    ergebnis TEXT DEFAULT ''
);
"""

OVERPASS_URL = "https://overpass-api.de/api/interpreter"

# Welche OpenStreetMap-Merkmale zu welcher Branche gehören.
BRANCHEN_OSM = {
    "Arztpraxen": [("amenity", "doctors"), ("amenity", "dentist")],
    "Physiotherapie": [("healthcare", "physiotherapist")],
    "Apotheken": [("amenity", "pharmacy")],
    "Steuerberater": [("office", "tax_advisor"), ("office", "accountant")],
    "Kanzleien": [("office", "lawyer"), ("office", "notary")],
    "Versicherungen": [("office", "insurance")],
    "Immobilien": [("office", "estate_agent")],
    "Autohäuser": [("shop", "car")],
    "Fitnessstudios": [("leisure", "fitness_centre")],
    "Hotels": [("tourism", "hotel")],
    "Kindergärten": [("amenity", "kindergarten")],
    "Restaurants": [("amenity", "restaurant")],
}
STANDARD_BRANCHEN = "Arztpraxen,Steuerberater,Kanzleien,Autohäuser,Fitnessstudios"

# Worauf es der jeweiligen Branche bei der Reinigung ankommt - für Skript und Vorlage.
BRANCHEN_PUNKT = {
    "Arztpraxen": "Hygiene und Desinfektion nach Plan, auch außerhalb der Sprechzeiten",
    "Physiotherapie": "saubere Behandlungsräume und Desinfektion der Liegen",
    "Apotheken": "gepflegte Verkaufsräume, gereinigt vor Öffnung",
    "Steuerberater": "diskrete Büroreinigung nach Feierabend",
    "Kanzleien": "diskrete Reinigung, Akten bleiben unberührt",
    "Versicherungen": "gepflegte Büros und Besprechungsräume",
    "Immobilien": "gepflegtes Büro und Endreinigung von Objekten",
    "Autohäuser": "glänzender Schauraum und saubere Glasflächen",
    "Fitnessstudios": "Hygiene in Duschen, Umkleiden und an den Geräten",
    "Hotels": "Unterstützung bei Zimmern und öffentlichen Bereichen",
    "Kindergärten": "gründliche Reinigung mit kindgerechten Mitteln",
    "Restaurants": "Gastraum und Sanitär, gereinigt vor Öffnung",
}

ARTEN = {"anruf": "Anrufen", "nachfassen": "Nachfassen", "antwort": "Mail beantworten",
         "hinweis": "Hinweis"}


def _sauber(text: str) -> str:
    """Entfernt Zeichen, die eine Overpass-Abfrage aufbrechen könnten."""
    return "".join(z for z in (text or "") if z not in '"\\;[](){}').strip()


def osm_abfrage(ort: str, branchen: list, anzahl: int = 40) -> str:
    """Baut die Overpass-Abfrage für die Branchen in einem Ort."""
    teile = []
    for branche in branchen:
        for schluessel, wert in BRANCHEN_OSM.get(branche, []):
            teile.append('nwr["%s"="%s"]["name"](area.a);' % (schluessel, wert))
    return ('[out:json][timeout:50];'
            'area["name"="%s"]["boundary"="administrative"]->.a;'
            '(%s);out tags center %d;' % (_sauber(ort), "".join(teile), int(anzahl)))


def _branche_von(tags: dict) -> str:
    for branche, merkmale in BRANCHEN_OSM.items():
        for schluessel, wert in merkmale:
            if tags.get(schluessel) == wert:
                return branche
    return ""


def osm_betriebe(ort: str, branchen: list, anzahl: int = 40, url: str = None) -> dict:
    """Holt Betriebe aus OpenStreetMap. Kostenlos, ohne Schlüssel."""
    ort = _sauber(ort)
    branchen = [b for b in branchen if b in BRANCHEN_OSM]
    if not ort:
        return {"ok": False, "fehler": "Es ist kein Ort eingestellt."}
    if not branchen:
        return {"ok": False, "fehler": "Es ist keine bekannte Branche gewählt."}
    daten = urllib.parse.urlencode({"data": osm_abfrage(ort, branchen, anzahl)}).encode()
    anfrage = urllib.request.Request(
        url or OVERPASS_URL, data=daten, method="POST",
        headers={"User-Agent": "Jarvis-Gebaeudereinigung/1.0",
                 "Content-Type": "application/x-www-form-urlencoded"})
    try:
        with urllib.request.urlopen(anfrage, timeout=70) as antwort:
            roh = json.loads(antwort.read().decode("utf-8"))
    except urllib.error.HTTPError as fehler:
        return {"ok": False, "fehler": "OpenStreetMap antwortet mit Fehler %d. "
                "Das passiert, wenn der Dienst ausgelastet ist; beim nächsten "
                "Lauf klappt es meist." % fehler.code}
    except (urllib.error.URLError, OSError, ValueError) as fehler:
        return {"ok": False, "fehler": "OpenStreetMap ist nicht erreichbar: %s" % fehler}

    betriebe = []
    for element in roh.get("elements", []):
        tags = element.get("tags") or {}
        name = (tags.get("name") or "").strip()
        if not name:
            continue
        strasse = " ".join(t for t in (tags.get("addr:street", ""),
                                       tags.get("addr:housenumber", "")) if t)
        ortsteil = " ".join(t for t in (tags.get("addr:postcode", ""),
                                        tags.get("addr:city", "")) if t)
        betriebe.append({
            "firma": name, "branche": _branche_von(tags),
            "adresse": ", ".join(t for t in (strasse, ortsteil) if t),
            "telefon": tags.get("phone") or tags.get("contact:phone") or "",
            "email": tags.get("email") or tags.get("contact:email") or "",
            "webseite": tags.get("website") or tags.get("contact:website") or "",
        })
    # Wer eine Telefonnummer hat, kommt zuerst - angerufen wird zuerst.
    betriebe.sort(key=lambda b: (not b["telefon"], not b["email"]))
    return {"ok": True, "betriebe": betriebe}


def anruf_vorlage(betrieb: dict, ort: str = "") -> str:
    """Ein Anruf-Skript ohne Gehirn - damit nie etwas liegen bleibt."""
    punkt = BRANCHEN_PUNKT.get(betrieb.get("branche", ""), "zuverlässige Reinigung")
    return (
        "Guten Tag, hier spricht %s von %s. Wir reinigen Betriebe hier%s. "
        "Darf ich kurz fragen, wer bei Ihnen die Reinigung macht und ob Sie "
        "damit zufrieden sind?\n\n"
        "Falls Interesse: Bei %s kommt es vor allem auf %s an. Ich schaue mir die "
        "Räume gern kostenlos an und schicke Ihnen danach ein festes Angebot. "
        "Wann passt es Ihnen diese Woche?\n\n"
        "Falls kein Interesse: Darf ich mich in ein paar Monaten noch einmal melden?"
        % (NUTZER_NAME, FIRMA, (" in %s" % ort) if ort else "",
           betrieb.get("firma", "Ihnen"), punkt))


class Autopilot:
    """Arbeitet die Vorarbeit von selbst ab und legt sie zur Freigabe vor."""

    def __init__(self, memory, akquise=None, mail=None, bookkeeping=None):
        self.memory = memory
        self.akquise = akquise
        self.mail = mail
        self.bookkeeping = bookkeeping
        self._laeuft = threading.Lock()
        self.osm_url = None  # für Tests umstellbar
        db_schema_anlegen(SCHEMA_AUTOPILOT, memory.db_pfad)

    # -- Einstellungen -------------------------------------------------------

    @staticmethod
    def einstellungen() -> dict:
        branchen = [b.strip() for b in (AUTOPILOT_BRANCHEN or STANDARD_BRANCHEN)
                    .split(",") if b.strip() in BRANCHEN_OSM]
        return {"an": bool(AUTOPILOT_AN), "ort": AUTOPILOT_ORT,
                "name": NUTZER_NAME, "firma": FIRMA,
                "branchen": branchen, "alle_branchen": list(BRANCHEN_OSM),
                "uhrzeiten": AUTOPILOT_UHRZEITEN,
                "neue_pro_lauf": int(AUTOPILOT_NEUE_LEADS)}

    @staticmethod
    def einstellungen_setzen(ort=None, branchen=None, an=None, name=None,
                             firma=None) -> dict:
        if name is not None and _sauber(str(name)):
            env_setzen("NUTZER_NAME", _sauber(str(name))[:60])
        if firma is not None and _sauber(str(firma)):
            env_setzen("FIRMA", _sauber(str(firma))[:80])
        if ort is not None:
            env_setzen("AUTOPILOT_ORT", _sauber(str(ort))[:80])
        if branchen is not None:
            gueltig = [b for b in branchen if b in BRANCHEN_OSM]
            env_setzen("AUTOPILOT_BRANCHEN", ",".join(gueltig) or STANDARD_BRANCHEN)
        if an is not None:
            env_setzen("AUTOPILOT_AN", "ja" if an else "nein")
        return {"ok": True, "text": "Gespeichert.", "einstellungen": Autopilot.einstellungen()}

    # -- Aufgaben ------------------------------------------------------------

    def aufgabe_anlegen(self, schluessel: str, art: str, titel: str, text: str = "",
                        firma: str = "", an: str = "", betreff: str = "", grund: str = "",
                        lead_id: int = 0) -> int:
        """Legt eine Aufgabe an - aber nie zweimal dieselbe."""
        if self.memory._lesen("SELECT id FROM autopilot_aufgaben WHERE schluessel=? LIMIT 1",
                              (schluessel,)):
            return 0
        return self.memory._schreiben(
            "INSERT INTO autopilot_aufgaben (schluessel, art, titel, firma, an, betreff, "
            "text, grund, lead_id, status, angelegt) VALUES (?,?,?,?,?,?,?,?,?,'offen',?)",
            (schluessel, art, titel[:200], firma, an, betreff[:200], text[:6000],
             grund[:500], int(lead_id or 0), zeitstempel()))

    def aufgaben(self, status: str = "offen", limit: int = 100) -> list:
        zeilen = self.memory._lesen(
            "SELECT * FROM autopilot_aufgaben WHERE status=? ORDER BY "
            "CASE art WHEN 'antwort' THEN 0 WHEN 'nachfassen' THEN 1 WHEN 'anruf' THEN 2 "
            "ELSE 3 END, id DESC LIMIT ?", (status, int(limit)))
        return [dict(z) for z in zeilen]

    def offen_anzahl(self) -> int:
        zeilen = self.memory._lesen(
            "SELECT count(*) AS n FROM autopilot_aufgaben WHERE status='offen'")
        return zeilen[0]["n"] if zeilen else 0

    def aufgabe_erledigen(self, nummer: int, aktion: str, text: str = None,
                          betreff: str = None) -> dict:
        """Senden, Erledigt oder Verwerfen - der Klick des Nutzers ist die Freigabe."""
        zeilen = self.memory._lesen("SELECT * FROM autopilot_aufgaben WHERE id=?",
                                    (int(nummer or 0),))
        if not zeilen:
            return {"ok": False, "text": "Diese Aufgabe gibt es nicht."}
        aufgabe = dict(zeilen[0])
        if aufgabe["status"] != "offen":
            return {"ok": False, "text": "Diese Aufgabe ist schon erledigt."}
        text = aufgabe["text"] if text is None else str(text)
        betreff = aufgabe["betreff"] if betreff is None else str(betreff)

        if aktion == "senden":
            if aufgabe["art"] != "antwort":
                return {"ok": False, "text": "Senden gibt es nur für Antworten auf Mails."}
            if self.mail is None or not self.mail.senden_moeglich():
                return {"ok": False, "text": "Der Mailversand ist nicht eingerichtet."}
            ergebnis = self.mail.senden(aufgabe["an"], betreff, text)
            if not ergebnis.get("ok"):
                return {"ok": False, "text": ergebnis.get("fehler", "Senden fehlgeschlagen.")}
            status = "gesendet"
        elif aktion == "erledigt":
            status = "erledigt"
            if aufgabe["art"] == "anruf" and aufgabe["lead_id"] and self.akquise is not None:
                # Angerufen: der Betrieb ist jetzt kontaktiert, Nachfassen läuft an.
                self.akquise.lead_weiterstufen(aufgabe["firma"], "kontaktiert",
                                               "angerufen (Autopilot)")
        elif aktion == "verwerfen":
            status = "verworfen"
        else:
            return {"ok": False, "text": "Unbekannte Aktion."}

        self.memory._schreiben(
            "UPDATE autopilot_aufgaben SET status=?, text=?, betreff=?, erledigt_am=? "
            "WHERE id=?", (status, text, betreff, zeitstempel(), aufgabe["id"]))
        self.memory.aktion_protokollieren("autopilot_%s" % aktion,
                                          {"aufgabe": aufgabe["titel"]}, status)
        return {"ok": True, "status": status,
                "text": {"gesendet": "Gesendet.", "erledigt": "Erledigt.",
                         "verworfen": "Verworfen."}[status]}

    # -- Ein Lauf --------------------------------------------------------------

    def laufen(self, agent=None) -> dict:
        """Ein kompletter Arbeitsdurchgang. Läuft nie zweimal gleichzeitig."""
        if not self._laeuft.acquire(blocking=False):
            return {"ok": False, "text": "Der Autopilot arbeitet gerade schon."}
        lauf = self.memory._schreiben("INSERT INTO autopilot_laeufe (start) VALUES (?)",
                                      (zeitstempel(),))
        zaehler, hinweise = {}, []
        try:
            for name, schritt in (("anruf", self._neue_betriebe),
                                  ("nachfassen", self._nachfassen),
                                  ("antwort", self._posteingang),
                                  ("hinweis", self._cashflow)):
                try:
                    anzahl, hinweis = schritt(agent)
                except Exception as fehler:  # ein Schritt darf die anderen nicht stoppen
                    anzahl, hinweis = 0, "%s: %s" % (ARTEN[name], fehler)
                zaehler[name] = anzahl
                if hinweis:
                    hinweise.append(hinweis)
            neu = sum(zaehler.values())
            teile = []
            if zaehler.get("anruf"):
                teile.append("%d neue Betriebe zum Anrufen" % zaehler["anruf"])
            if zaehler.get("nachfassen"):
                teile.append("%d zum Nachfassen" % zaehler["nachfassen"])
            if zaehler.get("antwort"):
                teile.append("%d Mails zu beantworten" % zaehler["antwort"])
            if zaehler.get("hinweis"):
                teile.append("%d Hinweise zum Geld" % zaehler["hinweis"])
            text = ("Autopilot: %s. Alles liegt unter 'Heute zu tun'." % ", ".join(teile)
                    if teile else "Autopilot: Nichts Neues. Offen sind %d Aufgaben."
                    % self.offen_anzahl())
            if hinweise:
                text += " Hinweis: " + " | ".join(hinweise)
            self.memory._schreiben("UPDATE autopilot_laeufe SET ende=?, ergebnis=? WHERE id=?",
                                   (zeitstempel(), text, lauf))
            self.memory.aktion_protokollieren("autopilot", zaehler, text)
            return {"ok": True, "neu": neu, "zaehler": zaehler, "hinweise": hinweise,
                    "offen": self.offen_anzahl(), "text": text}
        finally:
            self._laeuft.release()

    def letzter_lauf(self) -> dict:
        zeilen = self.memory._lesen("SELECT * FROM autopilot_laeufe ORDER BY id DESC LIMIT 1")
        return dict(zeilen[0]) if zeilen else {}

    # -- Die Schritte -------------------------------------------------------------

    def _neue_betriebe(self, agent):
        einstellungen = self.einstellungen()
        if not einstellungen["ort"]:
            return 0, "Kein Ort eingestellt - trag ihn auf der Seite 'Heute zu tun' ein."
        if self.akquise is None:
            return 0, ""
        gefunden = osm_betriebe(einstellungen["ort"], einstellungen["branchen"],
                                url=self.osm_url)
        if not gefunden.get("ok"):
            return 0, gefunden.get("fehler", "")
        neue = []
        for betrieb in gefunden["betriebe"]:
            if len(neue) >= einstellungen["neue_pro_lauf"]:
                break
            if not betrieb["telefon"] and not betrieb["email"]:
                continue  # niemand erreichbar - nutzlos
            ergebnis = self.akquise.lead_anlegen(
                betrieb["firma"], telefon=betrieb["telefon"], email=betrieb["email"],
                adresse=betrieb["adresse"], quelle="OpenStreetMap %s" % einstellungen["ort"],
                notiz=" ".join(t for t in (betrieb["branche"], betrieb["webseite"]) if t),
                naechster_schritt="anrufen und fragen, wer die Reinigung macht")
            if ergebnis.get("ok"):
                betrieb["lead_id"] = ergebnis["id"]
                neue.append(betrieb)
        if not neue:
            return 0, ("Keine neuen Betriebe mit Telefon in %s gefunden."
                       % einstellungen["ort"]) if not gefunden["betriebe"] else ""

        skripte = self._skripte(agent, neue, einstellungen["ort"])
        for betrieb in neue:
            skript = skripte.get(betrieb["firma"]) or anruf_vorlage(betrieb, einstellungen["ort"])
            details = ["Telefon: %s" % (betrieb["telefon"] or "keins eingetragen")]
            if betrieb["adresse"]:
                details.append("Adresse: %s" % betrieb["adresse"])
            if betrieb["webseite"]:
                details.append("Webseite: %s" % betrieb["webseite"])
            if betrieb["email"]:
                details.append("E-Mail: %s (anschreiben erst nach Einwilligung, "
                               "zum Beispiel wenn sie am Telefon Ja sagen)" % betrieb["email"])
            self.aufgabe_anlegen(
                "lead:%d" % betrieb["lead_id"], "anruf",
                "%s anrufen" % betrieb["firma"], skript + "\n\n" + "\n".join(details),
                firma=betrieb["firma"], an=betrieb["telefon"],
                grund="Neu aus OpenStreetMap, %s" % (betrieb["branche"] or "Betrieb"),
                lead_id=betrieb["lead_id"])
        return len(neue), ""

    @staticmethod
    def _skripte(agent, betriebe: list, ort: str) -> dict:
        """Lässt die Skripte vom Gehirn schreiben - eine Anfrage für alle."""
        if agent is None or not getattr(agent, "einsatzbereit", lambda: False)():
            return {}
        liste = "\n".join("- %s (%s)" % (b["firma"], b["branche"] or "Betrieb")
                          for b in betriebe)
        auftrag = (
            "Schreib Anruf-Skripte für eine Gebäudereinigung. Der Anrufer heißt %s, die "
            "Firma heißt %s, sie arbeitet in %s. Benutze genau diese Namen, keine "
            "Platzhalter in eckigen Klammern.\n"
            "Für jeden Betrieb: drei bis fünf gesprochene Sätze, per Sie, freundlich, "
            "konkret für die Branche. Ziel ist ein kostenloser Besichtigungstermin.\n"
            "Wichtig: Sprich neutral an ('Guten Tag'), rate keine Namen, Titel oder "
            "Anrede. Behaupte nichts über die eigene Firma (keine Spezialisierung, keine "
            "Zertifikate, keine Preise), was hier nicht steht.\n\n"
            "Betriebe:\n%s\n\nAntworte nur als JSON: "
            '{"skripte": [{"firma": "...", "skript": "..."}]}'
            % (NUTZER_NAME, FIRMA, ort, liste))
        try:
            antwort = agent.json_anfrage(auftrag, max_tokens=3000)
        except Exception:
            return {}
        if not antwort.get("ok"):
            return {}
        ergebnis = {}
        for eintrag in (antwort.get("daten") or {}).get("skripte") or []:
            if isinstance(eintrag, dict) and eintrag.get("firma") and eintrag.get("skript"):
                ergebnis[str(eintrag["firma"])] = str(eintrag["skript"]).strip()
        return ergebnis

    def _nachfassen(self, agent):
        if self.akquise is None:
            return 0, ""
        liste = self.akquise.nachfassliste()
        anzahl = 0
        for eintrag in (liste.get("eintraege") or [])[:15]:
            text = "Nächster Schritt: %s\nTelefon: %s%s" % (
                eintrag.get("schritt") or "melden", eintrag.get("telefon") or "unbekannt",
                ("\nSeit %d Tagen überfällig." % eintrag["seit_tagen"])
                if eintrag.get("seit_tagen") else "")
            if self.aufgabe_anlegen("nachfassen:%d:%s" % (eintrag["id"], heute_datum()),
                                    "nachfassen", "%s nachfassen" % eintrag["firma"], text,
                                    firma=eintrag["firma"], an=eintrag.get("telefon", ""),
                                    grund="Stufe: %s" % eintrag.get("stufe", ""),
                                    lead_id=eintrag["id"]):
                anzahl += 1
        return anzahl, ""

    def _posteingang(self, agent):
        if self.mail is None or not self.mail.lesen_moeglich():
            return 0, ""
        post = self.mail.ungelesene(15)
        if not post.get("ok"):
            return 0, post.get("fehler", "")
        anzahl = 0
        for mail in (post.get("wichtig") or [])[:3]:
            adresse = email.utils.parseaddr(mail.get("absender", ""))[1]
            schluessel = "mail:%s:%s" % (adresse, mail.get("betreff", ""))
            if self.memory._lesen("SELECT id FROM autopilot_aufgaben WHERE schluessel=?",
                                  (schluessel,)):
                continue
            entwurf = ""
            if agent is not None and getattr(agent, "einsatzbereit", lambda: False)():
                antwort = agent.text_anfrage(
                    "Schreib eine kurze, höfliche Antwort auf diese Mail im Namen von %s, "
                    "%s (Gebäudereinigung). Per Sie, sachlich. Versprich nichts, was nicht "
                    "in der Mail steht; Termine nur vorschlagen. Nur den Mailtext, ohne "
                    "Betreff.\n\nVon: %s\nBetreff: %s\nText: %s"
                    % (NUTZER_NAME, FIRMA, mail.get("absender", ""),
                       mail.get("betreff", ""), mail.get("auszug", "")), max_tokens=1500)
                if antwort.get("ok"):
                    entwurf = antwort.get("text", "")
            betreff = mail.get("betreff", "")
            if not betreff.lower().startswith("re:"):
                betreff = "Re: " + betreff
            if self.aufgabe_anlegen(
                    schluessel, "antwort" if (entwurf and "@" in adresse) else "hinweis",
                    "Antwort an %s" % (mail.get("absender") or adresse),
                    entwurf or "Diese Mail wartet auf eine Antwort:\n%s" % mail.get("auszug", ""),
                    an=adresse, betreff=betreff,
                    grund="Wichtige Mail: %s" % mail.get("betreff", "")):
                anzahl += 1
        return anzahl, ""

    def _cashflow(self, agent):
        if self.akquise is None:
            return 0, ""
        prognose = self.akquise.cashflow_prognose(3, self.bookkeeping)
        anzahl = 0
        for monat in prognose.get("monate") or []:
            if monat["ergebnis"] < 0:
                if self.aufgabe_anlegen(
                        "cash:%s" % monat["monat"], "hinweis",
                        "Im %s fehlen etwa %.0f Euro" % (monat["monat"], -monat["ergebnis"]),
                        "Erwartete Einnahmen %.0f Euro, Kosten %.0f Euro. Jeder gewonnene "
                        "Auftrag schließt die Lücke - deshalb heute die Anrufe."
                        % (monat["einnahmen"], monat["kosten"]),
                        grund="Cashflow-Prognose"):
                    anzahl += 1
        return anzahl, ""


# =========================================================================
# tools  -  Werkzeugkatalog - alles, was Claude tatsächlich tun kann.
# 
# Zwei Sicherheitsentscheidungen stecken in diesem Modul, und sie sind nicht
# verhandelbar.
# 
# **Keine freie Kommandozeile.** Eine Blockliste gefährlicher Befehle wäre
# wertlos: ``rm -rf`` lässt sich als ``rm  -rf`` oder ``rm -fr`` schreiben und
# rutscht durch. Stattdessen gibt es eine *Allowlist* registrierter Aktionen mit
# festen Argumenten. Was nicht registriert ist, läuft nicht. Jeder Aufruf geht über
# ``subprocess.run([...])`` mit abgeschalteter Shell - eine Shell wird im ganzen
# Projekt an keiner Stelle eingeschaltet.
# 
# **Kein Vollzug ohne klares Ja.** Alles mit Wirkung nach außen fragt vorher nach.
# Timeout oder ausbleibende Antwort gelten als Ablehnung.
# =========================================================================

#!/usr/bin/env python3
# -*- coding: utf-8 -*-



# Zeichen, die in eingesetzten Parametern nichts zu suchen haben. Weil überall
# ``shell=False`` gilt, wären sie ohnehin harmlos - abgelehnt werden sie
# trotzdem, damit ein späterer Umbau nicht plötzlich eine Lücke aufreißt.
GEFAEHRLICHE_ZEICHEN = set(";|&$`\n<>")

# Registrierte Aktionen ohne Parameter. Der Name ist der einzige Schlüssel -
# alles andere steht fest im Code.
SYSTEM_AKTIONEN = {
    "datum": (["date", "+%A, %d.%m.%Y, %H:%M"], "Datum und Uhrzeit"),
    "speicherplatz": (["df", "-h", "/"], "freier Speicherplatz"),
    "rechnername": (["hostname"], "Name des Rechners"),
    "laufzeit": (["uptime"], "wie lange der Rechner läuft"),
    "arbeitsspeicher": (["vm_stat"], "Arbeitsspeicher"),
    "batterie": (["pmset", "-g", "batt"], "Ladezustand des Akkus"),
    "netzwerk": (["ifconfig", "en0"], "Netzwerkverbindung"),
    "wlan": (["networksetup", "-getairportnetwork", "en0"], "verbundenes WLAN"),
    "programme": (["ps", "-A", "-o", "comm"], "laufende Programme"),
    "lautstaerke": (["osascript", "-e", "output volume of (get volume settings)"],
                    "Lautstärke"),
}

# Registrierte Aktionen mit genau einem geprüften Parameter.
PARAMETER_AKTIONEN = {
    "ordner_zeigen": (["ls", "-la", "{pfad}"], "pfad", "Inhalt eines Ordners"),
    "programm_oeffnen": (["open", "-a", "{programm}"], "programm", "Programm starten"),
    "datei_oeffnen": (["open", "{pfad}"], "pfad", "Datei öffnen"),
}

# Alles hier drin fragt vor der Ausführung nach einer Freigabe.
# Termine im eigenen Kalender fragen nicht mehr nach: Sie lassen sich jederzeit
# löschen, und ständiges Nachfragen machte Jarvis zäh.
FREIGABE_PFLICHTIG = {"mail_senden", "bildschirm_bedienen",
                      "nachricht_senden", "skript_ausfuehren", "anrufen",
                      "sms_senden", "browser_auftrag"}


def parameter_pruefen(wert: str):
    """Prüft einen eingesetzten Parameter. Gibt ``(ok, meldung)`` zurück."""
    text = str(wert if wert is not None else "")
    if not text.strip():
        return False, "Der Wert ist leer."
    if len(text) > 500:
        return False, "Der Wert ist zu lang."
    treffer = sorted({z for z in text if z in GEFAEHRLICHE_ZEICHEN})
    if treffer:
        sichtbar = ", ".join(repr(z) for z in treffer)
        return False, ("Der Wert enthält die Zeichen %s. Solche Werte führe ich "
                       "grundsätzlich nicht aus." % sichtbar)
    return True, ""


class Werkzeuge:
    """Der Katalog: Beschreibungen für Claude und die Ausführung dahinter."""

    def __init__(self, agent=None, db_pfad: str = None):
        self.agent = agent
        self.memory = Memory(db_pfad)
        self.recall = Recall(self.memory)
        self.bookkeeping = Bookkeeping(self.memory)
        self.call_analysis = CallAnalysis(self.memory)
        self.akquise = Akquise(self.memory, STANDARD_MWST)
        self.werkstatt = Werkstatt(self.memory)
        self.privat = Privat(self.memory, STEUER_RUECKLAGE)
        self.routines = Routines(self.memory)
        self.mail = Mail()
        self.kalender = Kalender()
        self.telegram = Telegram()
        self.kamera = Kamera()
        self.telefon = Telefon(self.memory)
        self.mcp = MCPClient()
        self.welt = Welt(self.mcp)
        self.autopilot = Autopilot(self.memory, self.akquise, self.mail, self.bookkeeping)
        self.bildschirm = Bildschirm(agent)
        self.browser = Browser(agent)
        self.messenger = Messenger(self.telegram, self.mail, self.mcp, None)
        self.team = Team(agent, self.memory)
        self.dashboard = Dashboard(memory=self.memory, bookkeeping=self.bookkeeping,
                                   call_analysis=self.call_analysis, recall=self.recall,
                                   kalender=self.kalender, mail=self.mail,
                                   routines=self.routines, mcp=self.mcp,
                                   akquise=self.akquise, team=self.team,
                                   privat=self.privat)
        self.stimme = None
        # Ein anderer Weg, Freigaben einzuholen - die Web-App setzt sich hier ein.
        self.freigabe_kanal = None

    def freigabe_kanal_setzen(self, kanal):
        """Setzt einen anderen Freigabeweg, etwa den Browser.

        Der Kanal braucht nur eine Methode ``anfordern(aktion, details)``, die
        ein Wörterbuch mit ``erlaubt`` zurückgibt. Ohne Kanal bleibt es bei
        Telegram beziehungsweise dem Terminal.
        """
        self.freigabe_kanal = kanal

    def stimme_setzen(self, stimme):
        """Reicht die Sprachausgabe durch - für Sprachnachrichten."""
        self.stimme = stimme
        self.messenger.stimme = stimme

    def agent_setzen(self, agent):
        """Verknüpft den Katalog mit dem Agenten, damit Werkzeuge Claude nutzen können."""
        self.agent = agent
        self.bildschirm.agent = agent
        self.team.agent = agent

    # -- Katalog für Claude -------------------------------------------------

    def katalog(self) -> list:
        """Alle Werkzeuge im Format der Claude-Schnittstelle."""
        def werkzeug(name, beschreibung, eigenschaften=None, pflicht=None):
            return {"name": name, "description": beschreibung,
                    "input_schema": {"type": "object",
                                     "properties": eigenschaften or {},
                                     "required": pflicht or []}}

        text = {"type": "string"}
        zahl = {"type": "number"}
        ganz = {"type": "integer"}
        wahr = {"type": "boolean"}

        eigene = [
            # -- Gedächtnis --
            werkzeug("notiz_speichern",
                     "Hält etwas Wichtiges fest, das er nebenbei erwähnt: eine "
                     "Kundeninformation, eine Entscheidung, eine Zahl.",
                     {"text": text, "kategorie": text}, ["text"]),
            werkzeug("notizen_suchen", "Sucht in gespeicherten Notizen.",
                     {"begriff": text}, ["begriff"]),
            werkzeug("kontakt_anlegen",
                     "Legt einen Kunden oder Lieferanten an oder ergänzt ihn.",
                     {"name": text, "firma": text, "telefon": text, "email": text,
                      "adresse": text, "notiz": text}, ["name"]),
            werkzeug("kontakt_suchen", "Sucht einen Kontakt.",
                     {"begriff": text}, ["begriff"]),
            werkzeug("punkt_anlegen",
                     "Merkt sich etwas, das noch zu erledigen ist.",
                     {"text": text, "faellig": text}, ["text"]),
            werkzeug("punkte_offen", "Zeigt, was noch offen ist.", {}),
            werkzeug("punkt_erledigen", "Hakt einen offenen Punkt ab.",
                     {"id": ganz}, ["id"]),
            werkzeug("kennzahl_setzen", "Hält eine Kennzahl mit Datum fest.",
                     {"name": text, "wert": zahl, "einheit": text}, ["name", "wert"]),
            werkzeug("gedaechtnis_durchsuchen",
                     "Sucht in Notizen, Kontakten, Tagesberichten und früheren "
                     "Gesprächen nach einem Thema.",
                     {"frage": text}, ["frage"]),
            werkzeug("tagesbericht_speichern",
                     "Legt die Zusammenfassung eines Tages ab.",
                     {"zusammenfassung": text, "entscheidungen": text, "offen": text,
                      "datum": text}, ["zusammenfassung"]),
            werkzeug("rueckblick", "Gibt die Tagesberichte der letzten Tage zurück.",
                     {"tage": ganz}),
            werkzeug("webseite_lesen",
                     "Liest eine Webseite und gibt ihren Text, Mailadressen, Telefonnummern "
                     "und Links zurück. Für jede Frage zu einer Adresse oder Seite.",
                     {"adresse": text, "frage": text}, ["adresse"]),
            werkzeug("autopilot_starten",
                     "Startet den Autopilot jetzt: neue Betriebe finden und Anruf-Skripte "
                     "schreiben, Nachfassen, Antworten auf wichtige Mails entwerfen, "
                     "Cashflow prüfen. Alles landet unter 'Heute zu tun'.", {}),
            werkzeug("heute_zu_tun",
                     "Liest vor, was auf der Liste 'Heute zu tun' offen ist.", {}),
            werkzeug("protokoll",
                     "Zeigt das Protokoll eines Tages aus dem Gesprächsverlauf: was "
                     "gesagt und getan wurde, was offen ist. Tag: heute, gestern oder "
                     "ein Datum. Mit 'thema' nur Gespräche dazu, mit 'tage' mehrere Tage.",
                     {"tag": text, "thema": text, "tage": ganz}),

            # -- Buchhaltung --
            werkzeug("buchung_eintragen",
                     "Trägt eine Einnahme oder Ausgabe ein. Beträge nie schätzen - "
                     "ist etwas unklar, vorher nachfragen.",
                     {"art": {"type": "string", "enum": ["einnahme", "ausgabe"]},
                      "datum": text, "betrag": zahl, "haendler": text,
                      "kategorie": {"type": "string", "enum": KATEGORIEN},
                      "mwst_satz": zahl, "mwst_betrag": zahl, "zahlungsart": text,
                      "notiz": text},
                     ["art", "datum", "betrag"]),
            werkzeug("beleg_erfassen",
                     "Liest einen Beleg von einem Foto und trägt ihn ein.",
                     {"bildpfad": text}, ["bildpfad"]),
            werkzeug("auswertung",
                     "Einnahmen, Ausgaben, Ergebnis, Vorsteuer, Umsatzsteuer und "
                     "Zahllast für einen Zeitraum.",
                     {"von": text, "bis": text}),
            werkzeug("fehlende_belege",
                     "Zeigt Ausgaben ohne hinterlegtes Belegfoto - genau die fehlen "
                     "beim Steuerberater.", {"von": text, "bis": text}),
            werkzeug("csv_export", "Exportiert die Buchungen als CSV für den Steuerberater.",
                     {"von": text, "bis": text}),

            # -- Kundengespräche --
            werkzeug("gespraech_festhalten",
                     "Bewertet ein Kundengespräch und legt es ab. Nutze das immer "
                     "ungefragt, wenn er von einem Kundentermin erzählt.",
                     {"bericht": text, "kunde": text}, ["bericht"]),
            werkzeug("offene_leads", "Zeigt offene Leads samt offenem Volumen.", {}),
            werkzeug("verkaufsmuster",
                     "Abschlussquote, Durchschnittspunktzahl und wiederkehrende Einwände.",
                     {"tage": ganz}),

            # -- Routinen --
            werkzeug("routine_anlegen",
                     "Legt einen gespeicherten Ablauf an. Mit Uhrzeit läuft er täglich "
                     "von selbst.",
                     {"name": text, "anweisung": text, "uhrzeit": text},
                     ["name", "anweisung"]),
            werkzeug("routine_ausfuehren", "Führt eine gespeicherte Routine aus.",
                     {"name": text}, ["name"]),
            werkzeug("routinen_liste", "Zeigt alle gespeicherten Routinen.", {}),

            # -- Akquise --
            werkzeug("lead_anlegen",
                     "Nimmt einen Interessenten in die Pipeline auf.",
                     {"firma": text, "ansprechpartner": text, "telefon": text,
                      "email": text, "adresse": text, "quelle": text,
                      "objekt_qm": zahl, "bodenbelag": text,
                      "intervall_pro_woche": zahl, "notiz": text,
                      "naechster_schritt": text}, ["firma"]),
            werkzeug("lead_weiterstufen",
                     "Setzt einen Interessenten auf eine neue Stufe.",
                     {"name": text,
                      "stufe": {"type": "string", "enum": STUFEN},
                      "notiz": text, "naechster_schritt": text,
                      "wert_monat": zahl}, ["name", "stufe"]),
            werkzeug("angebot_kalkulieren",
                     "Rechnet aus Fläche, Bodenbelag und Reinigungsintervall einen "
                     "Monatspreis über Leistungswerte. Ohne Quadratmeter und "
                     "Intervall wird nichts gerechnet - dann nachfragen.",
                     {"qm": zahl, "bodenbelag": text, "intervall_pro_woche": zahl,
                      "stundensatz": zahl,
                      "sonderleistungen": {
                          "type": "object",
                          "description": "Mengen je Leistung: %s"
                                         % ", ".join(SONDERLEISTUNGEN)}},
                     ["qm", "intervall_pro_woche"]),
            werkzeug("angebot_ablegen",
                     "Legt ein kalkuliertes Angebot beim Interessenten ab und "
                     "setzt ihn auf die Stufe Angebot.",
                     {"name": text, "qm": zahl, "bodenbelag": text,
                      "intervall_pro_woche": zahl, "stundensatz": zahl,
                      "notiz": text}, ["name", "qm", "intervall_pro_woche"]),
            werkzeug("nachfassliste",
                     "Wer heute zum Nachfassen fällig ist und warum.", {}),
            werkzeug("pipeline",
                     "Alle Interessenten nach Stufen, mit Werten.", {}),
            werkzeug("cashflow_prognose",
                     "Was in den nächsten Monaten hereinkommt: gesichert aus "
                     "Aufträgen, gewichtet aus der Pipeline, abzüglich Kosten.",
                     {"monate": ganz}),

            werkzeug("leads_finden",
                     "Sucht über den Such-Dienst Betriebe in einem Ort, die "
                     "Reinigung brauchen könnten, und nimmt sie als neue "
                     "Interessenten auf. Sie stehen auf Wert null, bis "
                     "angerufen wurde.",
                     {"ort": text, "branche": text, "anzahl": ganz}, ["ort"]),

            # -- Privat --
            werkzeug("fixkosten_anlegen",
                     "Trägt eine wiederkehrende Verpflichtung ein - privat oder "
                     "betrieblich. Im Zweifel nachfragen, welches von beiden.",
                     {"name": text, "betrag": zahl,
                      "rhythmus": {"type": "string",
                                   "enum": sorted(set(RHYTHMEN))},
                      "bereich": {"type": "string", "enum": list(BEREICHE)},
                      "kategorie": text, "faellig_am": text, "notiz": text},
                     ["name", "betrag"]),
            werkzeug("fixkosten_liste",
                     "Alle laufenden Verpflichtungen, auf den Monat gerechnet.",
                     {"bereich": {"type": "string", "enum": list(BEREICHE)}}),
            werkzeug("fixkosten_streichen", "Setzt eine Verpflichtung auf inaktiv.",
                     {"name": text,
                      "bereich": {"type": "string", "enum": list(BEREICHE)}},
                     ["name"]),
            werkzeug("bedarfsrechnung",
                     "Wie viel Umsatz der Betrieb im Monat braucht, damit nach "
                     "Kosten und Steuerrücklage das Private gedeckt ist. Die "
                     "wichtigste Zahl für einen Einzelunternehmer.", {}),
            werkzeug("erinnerung_anlegen",
                     "Merkt sich etwas mit Datum, auch jährlich wiederkehrend.",
                     {"was": text, "datum": text,
                      "wiederholung": {"type": "string",
                                       "enum": list(WIEDERHOLUNGEN)},
                      "bereich": {"type": "string", "enum": list(BEREICHE)},
                      "notiz": text}, ["was", "datum"]),
            werkzeug("erinnerungen_faellig",
                     "Was in den nächsten Tagen ansteht.", {"tage": ganz}),
            werkzeug("erinnerung_erledigen", "Hakt eine Erinnerung ab.",
                     {"id": ganz}, ["id"]),

            # -- Team --
            werkzeug("mitarbeiter_beauftragen",
                     "Gibt einen mehrschrittigen Auftrag an eine Fachkraft: %s. "
                     "Sie arbeitet ihn mit ihren eigenen Werkzeugen ab und "
                     "berichtet zurück." % ", ".join(ROLLEN),
                     {"rolle": {"type": "string", "enum": sorted(ROLLEN)},
                      "auftrag": text}, ["rolle", "auftrag"]),
            werkzeug("team_liste", "Zeigt, welche Fachkräfte es gibt.", {}),
            werkzeug("lagebericht",
                     "Der vollständige aktuelle Stand des Betriebs: Kasse, "
                     "Aufträge, Cashflow, Termine, Post, Offenes.", {}),

            # -- Werkstatt --
            werkzeug("skript_schreiben",
                     "Schreibt ein Python-Skript in die Werkstatt. Ausgeführt "
                     "wird dabei nichts.",
                     {"name": text, "code": text, "zweck": text},
                     ["name", "code"]),
            werkzeug("skript_zeigen", "Zeigt den Code eines abgelegten Skripts.",
                     {"name": text}, ["name"]),
            werkzeug("skript_ausfuehren",
                     "Führt ein Skript aus der Werkstatt aus. Braucht eine "
                     "Freigabe, und der Code wird dabei vollständig angezeigt.",
                     {"name": text, "argumente": {"type": "array",
                                                  "items": {"type": "string"}}},
                     ["name"]),
            werkzeug("werkstatt_liste", "Zeigt alle abgelegten Skripte.", {}),

            # -- Kommunikation --
            werkzeug("mails_lesen",
                     "Holt ungelesene Mails und sortiert sie vor.", {"limit": ganz}),
            werkzeug("mail_senden",
                     "Verschickt eine E-Mail. Braucht eine Freigabe.",
                     {"an": text, "betreff": text, "text": text},
                     ["an", "betreff", "text"]),
            werkzeug("nachricht_senden",
                     "Verschickt eine Nachricht über telegram, mail, imessage oder "
                     "whatsapp. Braucht eine Freigabe.",
                     {"kanal": {"type": "string",
                                "enum": ["telegram", "mail", "imessage", "whatsapp"]},
                      "an": text, "text": text, "als_sprache": wahr, "betreff": text},
                     ["kanal", "text"]),

            # -- Kalender --
            werkzeug("termine_lesen",
                     "Termine der nächsten Tage samt Überschneidungen.", {"tage": ganz}),
            werkzeug("termin_anlegen",
                     "Trägt einen Termin ein. Braucht eine Freigabe.",
                     {"titel": text, "beginn": text, "dauer_minuten": ganz,
                      "ort": text, "beschreibung": text}, ["titel", "beginn"]),

            # -- Welt --
            werkzeug("wetter", "Aktuelles Wetter und Vorhersage für einen Ort.",
                     {"ort": text}),
            werkzeug("recherche", "Sucht etwas im Internet.", {"frage": text}, ["frage"]),
            werkzeug("flug_suchen",
                     "Sucht Flugverbindungen und nennt sie. Bucht nichts.",
                     {"von": text, "nach": text, "wann": text}, ["von", "nach"]),
            werkzeug("umschauen",
                     "Nimmt ein Einzelbild der Kamera auf und beschreibt, was zu sehen "
                     "ist. Kein Dauervideo.",
                     {"frage": text, "behalten": wahr}),

            # -- Browser --
            werkzeug("browser_oeffnen",
                     "Öffnet eine Webseite im Browser und liest, was darauf steht - "
                     "samt aller Knöpfe und Felder mit ihren Nummern.",
                     {"adresse": text}, ["adresse"]),
            werkzeug("browser_lesen",
                     "Liest die gerade offene Seite noch einmal.", {}),
            werkzeug("browser_auftrag",
                     "Erledigt etwas im Browser: sucht, füllt Formulare aus, klickt "
                     "sich durch. Klickt auf Beschriftungen, nicht auf Bildpunkte. "
                     "Meldet sich nirgends an und schließt keinen Kauf ab. Braucht "
                     "eine Freigabe.",
                     {"ziel": text, "start": text, "schritte_max": ganz}, ["ziel"]),
            werkzeug("browser_schliessen", "Macht den Browser zu.", {}),

            # -- Telefon --
            werkzeug("anrufen",
                     "Ruft eine Nummer an und sagt dort einen Satz an - zum Beispiel "
                     "eine Terminbestätigung oder einen Rückruf. Braucht eine Freigabe.",
                     {"nummer": text, "ansage": text}, ["nummer", "ansage"]),
            werkzeug("sms_senden",
                     "Schickt eine SMS an eine Nummer. Braucht eine Freigabe.",
                     {"nummer": text, "text": text}, ["nummer", "text"]),
            werkzeug("anrufliste",
                     "Zeigt die letzten Anrufe und SMS mit Nummer, Zeitpunkt und Status.",
                     {"limit": ganz}),

            # -- Bildschirm --
            werkzeug("bildschirm_bedienen",
                     "Bedient den Mac über Screenshots, Schritt für Schritt. Braucht "
                     "eine Freigabe und bestätigt jeden Schritt einzeln.",
                     {"ziel": text}, ["ziel"]),

            # -- System --
            werkzeug("systeminfo",
                     "Fragt eine registrierte Systeminformation ab. Erlaubt sind "
                     "ausschließlich: %s." % ", ".join(sorted(SYSTEM_AKTIONEN)),
                     {"was": {"type": "string", "enum": sorted(SYSTEM_AKTIONEN)}},
                     ["was"]),
            werkzeug("ordner_zeigen", "Listet den Inhalt eines Ordners auf.",
                     {"pfad": text}, ["pfad"]),
            werkzeug("programm_oeffnen", "Startet ein Programm auf dem Mac.",
                     {"programm": text}, ["programm"]),
            werkzeug("dashboard_bauen", "Baut das Command Center neu.", {}),
        ]
        return eigene + self.mcp.alle_werkzeuge()

    def namen(self) -> list:
        """Alle Werkzeugnamen."""
        return [w["name"] for w in self.katalog()]

    # -- Freigabe -----------------------------------------------------------

    def braucht_freigabe(self, name: str, argumente: dict = None) -> bool:
        """Muss vor diesem Werkzeug gefragt werden?"""
        if self.mcp.ist_mcp_werkzeug(name):
            return self.mcp.braucht_freigabe(name)
        return name in FREIGABE_PFLICHTIG

    def _freigabe(self, name: str, argumente: dict) -> dict:
        """Holt die Freigabe ein. Ohne klares Ja wird nichts ausgeführt."""
        if name == "skript_ausfuehren":
            # Beim Ausführen von Code muss der Code selbst in der Frage stehen.
            # Über einen blossen Dateinamen kann niemand entscheiden.
            details = self.werkstatt.freigabetext(argumente.get("name", ""))
        else:
            try:
                details = json.dumps(argumente or {}, ensure_ascii=False)[:600]
            except (TypeError, ValueError):
                details = str(argumente)[:600]
        if self.freigabe_kanal is not None:
            return self.freigabe_kanal.anfordern(name, details)
        return self.telegram.freigabe_einholen(name, details)

    def _zwischenfrage(self, frage: str) -> bool:
        """Fragt mitten in einem laufenden Vorgang nach - etwa vor dem Bezahlen.

        Wie überall gilt: nur ein klares Ja zählt. Ein Fehler auf dem Weg zur
        Frage ist ein Nein.
        """
        try:
            if self.freigabe_kanal is not None:
                entscheidung = self.freigabe_kanal.anfordern("browser_schritt", frage)
            else:
                entscheidung = self.telegram.freigabe_einholen("browser_schritt", frage)
        except Exception:
            return False
        return bool(entscheidung.get("erlaubt"))

    # -- Ausführung ---------------------------------------------------------

    def run(self, name: str, argumente: dict = None) -> dict:
        """Führt ein Werkzeug aus - mit Freigabeprüfung und Protokoll."""
        argumente = argumente or {}
        if name not in self.namen():
            ergebnis = {"ok": False,
                        "fehler": "Das Werkzeug '%s' gibt es nicht." % name}
            self.memory.aktion_protokollieren(name, argumente, ergebnis["fehler"],
                                              "unbekannt")
            return ergebnis

        if self.braucht_freigabe(name, argumente):
            entscheidung = self._freigabe(name, argumente)
            if not entscheidung.get("erlaubt"):
                ergebnis = {"ok": False, "abgebrochen": True,
                            "text": "Abgebrochen. %s" % entscheidung.get("grund", "")}
                self.memory.aktion_protokollieren(
                    name, argumente, "Abgebrochen: %s" % entscheidung.get("grund", ""),
                    "abgelehnt")
                return ergebnis

        try:
            ergebnis = self._ausfuehren(name, argumente)
        except Exception as fehler:
            ergebnis = {"ok": False,
                        "fehler": "Das Werkzeug %s ist fehlgeschlagen: %s" % (name, fehler)}

        if not isinstance(ergebnis, dict):
            ergebnis = {"ok": True, "text": str(ergebnis)}
        kurz = str(ergebnis.get("text") or ergebnis.get("fehler") or "")[:400]
        self.memory.aktion_protokollieren(
            name, argumente, kurz, "ok" if ergebnis.get("ok") else "fehler")
        return ergebnis

    def _ausfuehren(self, name: str, a: dict) -> dict:
        """Die eigentliche Zuordnung von Namen zu Funktionen."""
        if self.mcp.ist_mcp_werkzeug(name):
            return self.mcp.aufrufen(name, a)

        # -- Gedächtnis --
        if name == "notiz_speichern":
            return self.memory.notiz_speichern(a.get("text"), a.get("kategorie", "allgemein"))
        if name == "notizen_suchen":
            treffer = self.memory.notizen_suchen(a.get("begriff"))
            return {"ok": True, "anzahl": len(treffer),
                    "notizen": [{"id": n["id"], "text": n["text"],
                                 "datum": n["angelegt"][:10]} for n in treffer],
                    "text": ("%d Notizen gefunden." % len(treffer)) if treffer
                            else "Dazu habe ich nichts gespeichert."}
        if name == "kontakt_anlegen":
            return self.memory.kontakt_anlegen(
                a.get("name"), a.get("firma", ""), a.get("telefon", ""),
                a.get("email", ""), a.get("adresse", ""), a.get("notiz", ""))
        if name == "kontakt_suchen":
            treffer = self.memory.kontakt_suchen(a.get("begriff"))
            return {"ok": True, "anzahl": len(treffer),
                    "kontakte": [{k: z[k] for k in ("id", "name", "firma", "telefon",
                                                    "email", "notiz")} for z in treffer],
                    "text": ("%d Kontakte gefunden." % len(treffer)) if treffer
                            else "Den Kontakt kenne ich nicht."}
        if name == "punkt_anlegen":
            return self.memory.punkt_anlegen(a.get("text"), a.get("faellig", ""))
        if name == "punkte_offen":
            punkte = self.memory.punkte_offen()
            return {"ok": True, "anzahl": len(punkte),
                    "punkte": [{"id": p["id"], "text": p["text"],
                                "faellig": p["faellig"]} for p in punkte],
                    "text": ("%d Punkte offen." % len(punkte)) if punkte
                            else "Es ist nichts offen."}
        if name == "punkt_erledigen":
            erledigt = self.memory.punkt_erledigen(a.get("id"))
            return {"ok": erledigt,
                    "text": "Erledigt." if erledigt
                            else "Einen offenen Punkt mit dieser Nummer gibt es nicht."}
        if name == "kennzahl_setzen":
            return self.memory.kennzahl_setzen(a.get("name"), a.get("wert"),
                                               a.get("einheit", ""))
        if name == "gedaechtnis_durchsuchen":
            treffer = self.recall.nachschlagen(a.get("frage", ""))
            anzahl = sum(len(treffer[s]) for s in
                         ("notizen", "kontakte", "berichte", "aeusserungen"))
            return {"ok": True, "treffer": {
                        "notizen": [n["text"] for n in treffer["notizen"]],
                        "kontakte": [k["name"] for k in treffer["kontakte"]],
                        "berichte": [("%s: %s" % (b["datum"], b["zusammenfassung"]))
                                     for b in treffer["berichte"]],
                        "aeusserungen": [z["text"][:200] for z in treffer["aeusserungen"]]},
                    "text": ("%d Treffer im Gedächtnis." % anzahl) if anzahl
                            else "Dazu finde ich nichts."}
        if name == "tagesbericht_speichern":
            return self.recall.tagesbericht_speichern(
                a.get("zusammenfassung"), a.get("entscheidungen", ""),
                a.get("offen", ""), a.get("datum", ""))
        if name == "rueckblick":
            return {"ok": True, "text": self.recall.rueckblick(int(a.get("tage") or 7))}
        if name == "webseite_lesen":
            return webseite_lesen(a.get("adresse", ""), a.get("frage", ""))
        if name == "autopilot_starten":
            return self.autopilot.laufen(self.agent)
        if name == "heute_zu_tun":
            offen = self.autopilot.aufgaben()
            if not offen:
                return {"ok": True, "anzahl": 0, "text": "Auf der Liste ist nichts offen."}
            return {"ok": True, "anzahl": len(offen),
                    "aufgaben": [{"id": z["id"], "titel": z["titel"], "art": z["art"]}
                                 for z in offen[:15]],
                    "text": "%d Aufgaben offen. Zuerst: %s." % (
                        len(offen), "; ".join(z["titel"] for z in offen[:3]))}
        if name == "protokoll":
            return self.recall.protokoll(a.get("tag") or "heute", a.get("thema", ""),
                                         int(a.get("tage") or 1))

        # -- Buchhaltung --
        if name == "buchung_eintragen":
            return self.bookkeeping.buchung_eintragen(
                a.get("art"), a.get("datum"), a.get("betrag"), a.get("haendler", ""),
                a.get("kategorie", "Sonstiges"), a.get("mwst_satz"),
                a.get("mwst_betrag"), a.get("zahlungsart", ""), None, "",
                a.get("notiz", ""))
        if name == "beleg_erfassen":
            return self.bookkeeping.beleg_erfassen(a.get("bildpfad"), self.agent)
        if name == "auswertung":
            return self.bookkeeping.auswertung(a.get("von", ""), a.get("bis", ""))
        if name == "fehlende_belege":
            return self.bookkeeping.fehlende_belege(a.get("von", ""), a.get("bis", ""))
        if name == "csv_export":
            return self.bookkeeping.csv_export(a.get("von", ""), a.get("bis", ""))

        # -- Kundengespräche --
        if name == "gespraech_festhalten":
            return self.call_analysis.gespraech_festhalten(
                a.get("bericht"), self.agent, a.get("kunde", ""))
        if name == "offene_leads":
            return self.call_analysis.offene_leads()
        if name == "verkaufsmuster":
            return self.call_analysis.verkaufsmuster(int(a.get("tage") or 90))

        # -- Routinen --
        if name == "routine_anlegen":
            return self.routines.routine_anlegen(a.get("name"), a.get("anweisung"),
                                                 a.get("uhrzeit", ""))
        if name == "routine_ausfuehren":
            return self.routines.routine_ausfuehren(a.get("name"), self.agent)
        if name == "routinen_liste":
            liste = self.routines.routinen_liste()
            return {"ok": True, "anzahl": len(liste),
                    "routinen": [{"name": z["name"], "uhrzeit": z["uhrzeit"],
                                  "anweisung": z["anweisung"][:200]} for z in liste],
                    "text": ("Gespeicherte Routinen: %s."
                             % ", ".join(z["name"] for z in liste)) if liste
                            else "Es ist noch keine Routine angelegt."}

        # -- Akquise --
        if name == "lead_anlegen":
            return self.akquise.lead_anlegen(
                a.get("firma"), a.get("ansprechpartner", ""), a.get("telefon", ""),
                a.get("email", ""), a.get("adresse", ""), a.get("quelle", ""),
                a.get("objekt_qm", 0), a.get("bodenbelag", ""),
                a.get("intervall_pro_woche", 0), a.get("notiz", ""),
                a.get("naechster_schritt", ""))
        if name == "lead_weiterstufen":
            return self.akquise.lead_weiterstufen(
                a.get("name"), a.get("stufe"), a.get("notiz", ""),
                a.get("naechster_schritt", ""), a.get("wert_monat"))
        if name == "angebot_kalkulieren":
            return self.akquise.angebot_kalkulieren(
                a.get("qm"), a.get("bodenbelag", ""), a.get("intervall_pro_woche"),
                a.get("stundensatz"), a.get("sonderleistungen"))
        if name == "angebot_ablegen":
            kalkulation = self.akquise.angebot_kalkulieren(
                a.get("qm"), a.get("bodenbelag", ""), a.get("intervall_pro_woche"),
                a.get("stundensatz"))
            if not kalkulation.get("ok"):
                return kalkulation
            ergebnis = self.akquise.angebot_ablegen(a.get("name"), kalkulation,
                                                    a.get("notiz", ""))
            ergebnis["angebotstext"] = self.akquise.angebotstext(
                kalkulation, a.get("name", ""))
            return ergebnis
        if name == "nachfassliste":
            return self.akquise.nachfassliste()
        if name == "pipeline":
            return self.akquise.pipeline()
        if name == "cashflow_prognose":
            return self.akquise.cashflow_prognose(int(a.get("monate") or 6),
                                                  self.bookkeeping)

        if name == "leads_finden":
            return self.akquise.leads_finden(
                a.get("ort"), a.get("branche", ""), int(a.get("anzahl") or 8),
                self.welt, self.agent)

        # -- Privat --
        if name == "fixkosten_anlegen":
            return self.privat.fixkosten_anlegen(
                a.get("name"), a.get("betrag"), a.get("rhythmus", "monatlich"),
                a.get("bereich", "privat"), a.get("kategorie", ""),
                a.get("faellig_am", ""), a.get("notiz", ""))
        if name == "fixkosten_liste":
            return self.privat.fixkosten(a.get("bereich", ""))
        if name == "fixkosten_streichen":
            return self.privat.fixkosten_streichen(a.get("name"),
                                                   a.get("bereich", ""))
        if name == "bedarfsrechnung":
            return self.privat.bedarfsrechnung(self.akquise)
        if name == "erinnerung_anlegen":
            return self.privat.erinnerung_anlegen(
                a.get("was"), a.get("datum"), a.get("wiederholung", "einmalig"),
                a.get("bereich", "privat"), a.get("notiz", ""))
        if name == "erinnerungen_faellig":
            return self.privat.erinnerungen_faellig(int(a.get("tage") or 14))
        if name == "erinnerung_erledigen":
            return self.privat.erinnerung_erledigen(a.get("id"))

        # -- Team --
        if name == "mitarbeiter_beauftragen":
            return self.team.beauftragen(a.get("rolle"), a.get("auftrag"))
        if name == "team_liste":
            liste = self.team.rollen_liste()
            return {"ok": True, "team": liste,
                    "text": "Im Team sind: %s."
                            % ", ".join("%s (%s)" % (e["name"], e["rolle"])
                                        for e in liste)}
        if name == "lagebericht":
            return self.team.lagebericht(self)

        # -- Werkstatt --
        if name == "skript_schreiben":
            return self.werkstatt.skript_schreiben(a.get("name"), a.get("code"),
                                                   a.get("zweck", ""))
        if name == "skript_zeigen":
            return self.werkstatt.skript_zeigen(a.get("name"))
        if name == "skript_ausfuehren":
            return self.werkstatt.skript_ausfuehren(a.get("name"),
                                                    a.get("argumente"))
        if name == "werkstatt_liste":
            return self.werkstatt.werkstatt_liste()

        # -- Kommunikation --
        if name == "mails_lesen":
            return self.mail.ungelesene(int(a.get("limit") or 15))
        if name == "mail_senden":
            return self.mail.senden(a.get("an"), a.get("betreff"), a.get("text"))
        if name == "nachricht_senden":
            return self.messenger.nachricht_senden(
                a.get("kanal"), a.get("an", ""), a.get("text"),
                bool(a.get("als_sprache")), a.get("betreff", ""))

        # -- Kalender --
        if name == "termine_lesen":
            return self.kalender.termine(int(a.get("tage") or 7))
        if name == "termin_anlegen":
            return self.kalender.termin_anlegen(
                a.get("titel"), a.get("beginn"), int(a.get("dauer_minuten") or 60),
                a.get("ort", ""), a.get("beschreibung", ""))

        # -- Welt --
        if name == "wetter":
            return self.welt.wetter(a.get("ort", ""))
        if name == "recherche":
            return self.welt.recherche(a.get("frage"))
        if name == "flug_suchen":
            return self.welt.flug_suchen(a.get("von"), a.get("nach"), a.get("wann", ""))
        if name == "umschauen":
            return self.kamera.umschauen(a.get("frage", ""), self.agent,
                                         bool(a.get("behalten")))

        # -- Browser --
        if name == "browser_oeffnen":
            return self.browser.oeffnen(a.get("adresse"))
        if name == "browser_lesen":
            return self.browser.seite_lesen()
        if name == "browser_auftrag":
            # Haltepunkte wie ein Bezahlvorgang gehen über denselben Weg wie
            # jede andere Freigabe - Telegram, Terminal oder Browserfenster.
            return self.browser.erledigen(
                a.get("ziel", ""), a.get("start", ""),
                int(a.get("schritte_max") or 15),
                bestaetigen=self._zwischenfrage)
        if name == "browser_schliessen":
            return self.browser.schliessen()

        # -- Telefon --
        if name == "anrufen":
            return self.telefon.anrufen(a.get("nummer"), a.get("ansage"))
        if name == "sms_senden":
            return self.telefon.sms_senden(a.get("nummer"), a.get("text"))
        if name == "anrufliste":
            return self.telefon.anrufliste(int(a.get("limit") or 20))

        # -- Bildschirm --
        if name == "bildschirm_bedienen":
            return self.bildschirm.bedienen(a.get("ziel", ""))

        # -- System --
        if name == "systeminfo":
            return self.systeminfo(a.get("was", ""))
        if name in PARAMETER_AKTIONEN:
            return self.parameter_aktion(name, a)
        if name == "dashboard_bauen":
            return self.dashboard.bauen(mit_netz=True)

        return {"ok": False, "fehler": "Für '%s' fehlt die Umsetzung." % name}

    # -- Die Allowlist ------------------------------------------------------

    def systeminfo(self, was: str) -> dict:
        """Führt eine registrierte Systemabfrage aus.

        Nur die Namen aus :data:`SYSTEM_AKTIONEN` sind zulässig. Ein übergebener
        Befehlstext wird nie ausgeführt - er ist schlicht kein gültiger Name.
        """
        schluessel = str(was or "").strip().lower()
        if schluessel not in SYSTEM_AKTIONEN:
            return {"ok": False,
                    "fehler": "'%s' ist keine registrierte Abfrage. Ich führe nur "
                              "diese aus: %s." % (was, ", ".join(sorted(SYSTEM_AKTIONEN)))}
        befehl, beschreibung = SYSTEM_AKTIONEN[schluessel]
        return self._befehl_ausfuehren(befehl, beschreibung)

    def parameter_aktion(self, name: str, argumente: dict) -> dict:
        """Führt eine registrierte Aktion mit genau einem geprüften Parameter aus."""
        vorlage, parametername, beschreibung = PARAMETER_AKTIONEN[name]
        wert = argumente.get(parametername, "")
        ok, meldung = parameter_pruefen(wert)
        if not ok:
            return {"ok": False,
                    "fehler": "Der Wert für %s ist nicht zulässig. %s"
                              % (parametername, meldung)}
        if parametername == "pfad":
            wert = os.path.expanduser(str(wert))
        befehl = [teil.replace("{%s}" % parametername, str(wert)) for teil in vorlage]
        return self._befehl_ausfuehren(befehl, beschreibung)

    @staticmethod
    def _befehl_ausfuehren(befehl: list, beschreibung: str) -> dict:
        """Führt einen fest registrierten Befehl aus - immer ohne Shell."""
        try:
            ergebnis = subprocess.run(befehl, capture_output=True, text=True,
                                      timeout=25, shell=False)
        except FileNotFoundError:
            return {"ok": False,
                    "fehler": "Das Programm '%s' gibt es auf diesem Rechner nicht. "
                              "Diese Abfrage funktioniert nur auf einem Mac." % befehl[0]}
        except (OSError, subprocess.SubprocessError) as fehler:
            return {"ok": False, "fehler": "Die Abfrage ist fehlgeschlagen: %s" % fehler}
        ausgabe = (ergebnis.stdout or ergebnis.stderr or "").strip()
        if ergebnis.returncode != 0 and not ergebnis.stdout:
            return {"ok": False,
                    "fehler": "Die Abfrage '%s' hat nicht funktioniert: %s"
                              % (beschreibung, ausgabe[:300])}
        return {"ok": True, "was": beschreibung, "text": ausgabe[:3000]}

    # -- Übersicht ----------------------------------------------------------

    def zustand(self) -> dict:
        """Was ist einsatzbereit - für den Selbsttest und das Dashboard."""
        return {
            "werkzeuge": len(self.namen()),
            "mcp_werkzeuge": len(self.mcp.alle_werkzeuge()),
            "freigabepflichtig": sorted(FREIGABE_PFLICHTIG),
            "systemaktionen": sorted(SYSTEM_AKTIONEN),
            "mail": self.mail.zustand(),
            "kalender": self.kalender.zustand(),
            "telegram": self.telegram.verfuegbar(),
            "kamera": self.kamera.zustand(),
            "telefon": self.telefon.zustand(),
            "bildschirm": self.bildschirm.zustand(),
            "browser": self.browser.zustand(),
            "versand": self.messenger.zustand(),
        }


# =========================================================================
# agent  -  Der Kern - Claude denkt, die Werkzeuge handeln.
# 
# Ablauf pro Eingabe:
# 
# 1. Erinnerung nachschlagen und dem Systemprompt beilegen
# 2. Anfrage an die Claude-Schnittstelle mit dem gesamten Werkzeugkatalog
#    (eigene Werkzeuge **plus** alle von MCP-Servern)
# 3. Fordert Claude ein Werkzeug an: ausführen, Ergebnis zurückgeben, wiederholen
# 4. Höchstens acht Runden, dann Abbruch mit klarer Meldung
# =========================================================================

#!/usr/bin/env python3
# -*- coding: utf-8 -*-



API_URL = "https://api.anthropic.com/v1/messages"
API_VERSION = "2023-06-01"
MAX_RUNDEN = 8
MAX_VERLAUF = 24

WOCHENTAGE_DE = ["Montag", "Dienstag", "Mittwoch", "Donnerstag", "Freitag",
                 "Samstag", "Sonntag"]
MONATE_DE = ["Januar", "Februar", "März", "April", "Mai", "Juni", "Juli",
             "August", "September", "Oktober", "November", "Dezember"]

SYSTEMPROMPT = """Du bist Jarvis, der persönliche Assistent von {name}.
{name} führt eine Gebäudereinigungsfirma als Einzelunternehmer.

So sprichst du:
- Kurz und gesprochen. Deine Antworten werden vorgelesen — keine
  Aufzählungszeichen, keine Sternchen, keine Überschriften. Ganze Sätze.
- Zwei bis vier Sätze reichen fast immer.
- Du duzt ihn. Sachlich und ruhig, nicht kumpelhaft.

So arbeitest du:
- Du nutzt deine Werkzeuge selbstständig, ohne zu fragen, wenn die Absicht klar ist.
- Du hast ein Team: Buchhalter, Verkäufer, Terminplaner, Postbearbeiter,
  Kundenberater, Rechercheur, Controller und Programmierer. Für eine Aufgabe,
  die klar zu einem von ihnen gehört und mehrere Schritte braucht, beauftragst
  du ihn mit mitarbeiter_beauftragen und gibst danach seinen Bericht weiter.
  Kleine Handgriffe machst du selbst - dafür brauchst du niemanden.
- Erzählt er von einem Kundentermin, bewertest du ihn und hältst ihn fest —
  ungefragt. Ehrlich, nicht schmeichelnd: ein nettes Gespräch ohne Abschluss
  war kein gutes Gespräch, und das sagst du auch.
- Nennt er nebenbei etwas Wichtiges über einen Kunden oder eine Entscheidung,
  merkst du es dir.
- Bei Geld bist du genau. Beträge schätzt du nie. Ist etwas unklar, fragst du nach.
- Du hast ein Gedächtnis über frühere Tage. Nutze es beiläufig, ohne es
  anzukündigen. Sag nie "laut meinem Gedächtnis".
- Ging etwas schief, sagst du es. Du erfindest keine Ergebnisse.

Die Buchhaltung führst du vor — die fachliche Prüfung macht sein Steuerberater.

Heute ist {wochentag}, der {datum}.

{gedaechtnis}"""


def datum_deutsch(zeitpunkt: datetime = None) -> tuple:
    """Gibt Wochentag und ausgeschriebenes Datum auf Deutsch zurück."""
    zeitpunkt = zeitpunkt or datetime.now()
    return (WOCHENTAGE_DE[zeitpunkt.weekday()],
            "%d. %s %d" % (zeitpunkt.day, MONATE_DE[zeitpunkt.month - 1], zeitpunkt.year))


def json_aus_text(rohtext: str):
    """Holt ein JSON-Objekt aus einer Antwort, auch wenn Code-Zäune drumherum stehen."""
    if not rohtext:
        return None
    text = str(rohtext).strip()
    if text.startswith("```"):
        text = text.split("```")[1] if "```" in text[3:] else text[3:]
        if text.lstrip().lower().startswith("json"):
            text = text.lstrip()[4:]
    text = text.strip().strip("`").strip()
    try:
        return json.loads(text)
    except ValueError:
        pass
    # Notfalls das äußerste geschweifte Klammerpaar herausschneiden.
    beginn, ende = text.find("{"), text.rfind("}")
    if beginn >= 0 and ende > beginn:
        try:
            return json.loads(text[beginn:ende + 1])
        except ValueError:
            return None
    return None


# Werkzeuge, deren eigene Meldung als Antwort genügt ("Notiz gespeichert.").
# Alles, was gelesen und zusammengefasst werden muss, gehört nicht hierher.
DIREKT_ANTWORT = {
    "notiz_speichern", "punkt_anlegen", "punkt_erledigen", "kontakt_anlegen",
    "erinnerung_anlegen", "erinnerung_erledigen", "kennzahl_setzen", "lead_anlegen",
    "lead_weiterstufen", "buchung_eintragen", "termin_anlegen", "programm_oeffnen",
    "autopilot_starten", "heute_zu_tun", "punkte_offen", "mail_senden",
    "nachricht_senden", "sms_senden", "anrufen", "tagesbericht_speichern",
    "fixkosten_anlegen", "routine_anlegen",
}


# Werkzeuge, die als Meldung nur den Inhalt zurückgeben ("Berger anrufen"),
# bekommen für die Direktantwort einen ganzen Satz.
DIREKT_SAETZE = {
    "notiz_speichern": "Notiert: {text}",
    "punkt_anlegen": "Offener Punkt angelegt: {text}",
    "kontakt_anlegen": "Kontakt {name} ist angelegt.",
    "kennzahl_setzen": "{name} ist festgehalten.",
    "tagesbericht_speichern": "Der Tagesbericht ist gespeichert.",
}


def direkt_satz(name: str, argumente: dict, ergebnis: dict) -> str:
    """Der Satz, mit dem Jarvis eine einfache Aktion selbst bestätigt - oder ''."""
    if name not in DIREKT_ANTWORT or not ergebnis.get("ok"):
        return ""
    vorlage = DIREKT_SAETZE.get(name)
    if vorlage:
        satz = vorlage
        for feld in ("text", "name"):
            satz = satz.replace("{%s}" % feld, str((argumente or {}).get(feld, "")).strip())
        if name == "punkt_anlegen" and (argumente or {}).get("faellig"):
            satz += " (fällig %s)" % str(argumente["faellig"]).strip()
        return satz if satz.endswith((".", "!", "?", ")")) else satz + "."
    return str(ergebnis.get("text") or "").strip()


class JarvisAgent:
    """Die Denkschleife: fragt Claude, führt Werkzeuge aus, antwortet gesprochen."""

    def __init__(self, db_pfad: str = None, stimme=None):
        self.tools = Werkzeuge(agent=None, db_pfad=db_pfad)
        self.tools.agent_setzen(self)
        self.memory = self.tools.memory
        self.recall = self.tools.recall
        self.stimme = stimme
        if stimme is not None:
            self.tools.stimme_setzen(stimme)
        self.verlauf = []
        self.letzter_fehler = ""

    # -- Grundlagen ---------------------------------------------------------

    def einsatzbereit(self) -> bool:
        """Ist ein Anthropic-Schlüssel oder ein lokales Modell eingestellt?"""
        return (bool(ANTHROPIC_API_KEY) or freier_dienst_aktiv()
                or lokales_modell_aktiv())

    def stimme_setzen(self, stimme):
        """Hängt die Sprachausgabe ein."""
        self.stimme = stimme
        self.tools.stimme_setzen(stimme)

    def dienste_starten(self) -> dict:
        """Startet die eingeschalteten MCP-Dienste."""
        return self.tools.mcp.starten()

    def systemprompt(self, frage: str = "") -> str:
        """Baut den Systemprompt samt passendem Gedächtnisauszug."""
        wochentag, datum = datum_deutsch()
        try:
            gedaechtnis = self.recall.gedaechtnis_block(frage)
        except Exception as fehler:
            gedaechtnis = ""
            print("[agent] Gedächtnis nicht lesbar: %s" % fehler)
        return SYSTEMPROMPT.format(name=NUTZER_NAME, wochentag=wochentag,
                                   datum=datum, gedaechtnis=gedaechtnis)

    # -- Schnittstelle ------------------------------------------------------

    def _anfrage(self, koerper: dict, timeout: int = 120) -> dict:
        """Schickt eine Anfrage an die Claude-Schnittstelle.

        Fehler kommen auf Deutsch zurück und benennen den nächsten Schritt.
        """
        if not self.einsatzbereit():
            return {"ok": False,
                    "fehler": "Es ist noch kein Gehirn eingerichtet. Trag im Browser "
                              "einen Gratis-Schlüssel ein (localhost:8765)."}
        if not ANTHROPIC_API_KEY:
            if freier_dienst_aktiv():
                return freier_dienst_anfragen(koerper)
            return lokal_anfragen(koerper)
        daten = json.dumps(koerper).encode("utf-8")
        anfrage = urllib.request.Request(API_URL, data=daten, method="POST", headers={
            "x-api-key": ANTHROPIC_API_KEY,
            "anthropic-version": API_VERSION,
            "content-type": "application/json",
        })
        for versuch in range(3):
            try:
                with urllib.request.urlopen(anfrage, timeout=timeout) as antwort:
                    return {"ok": True,
                            "daten": json.loads(antwort.read().decode("utf-8"))}
            except urllib.error.HTTPError as fehler:
                try:
                    inhalt = fehler.read().decode("utf-8")
                    meldung = (json.loads(inhalt).get("error") or {}).get("message", inhalt)
                except (ValueError, OSError):
                    meldung = str(fehler)
                if fehler.code == 401:
                    return {"ok": False,
                            "fehler": "Der Schlüssel wird abgelehnt - bitte neu kopieren "
                                      "und die Einrichtung noch einmal starten."}
                if fehler.code == 400 and "credit" in meldung.lower():
                    return {"ok": False,
                            "fehler": "Auf dem Anthropic-Konto ist kein Guthaben mehr. "
                                      "Bitte unter console.anthropic.com aufladen."}
                if fehler.code in (429, 529) and versuch < 2:
                    time.sleep(3 * (versuch + 1))
                    continue
                if fehler.code == 429:
                    return {"ok": False,
                            "fehler": "Zu viele Anfragen in kurzer Zeit. Bitte in einer "
                                      "Minute noch einmal."}
                return {"ok": False,
                        "fehler": "Claude meldet einen Fehler (%d): %s"
                                  % (fehler.code, meldung[:300])}
            except (urllib.error.URLError, OSError) as fehler:
                if versuch < 2:
                    time.sleep(2 * (versuch + 1))
                    continue
                return {"ok": False,
                        "fehler": "Keine Verbindung zu Claude: %s. Ist das Internet da?"
                                  % fehler}
            except ValueError as fehler:
                return {"ok": False, "fehler": "Die Antwort war unlesbar: %s" % fehler}
        return {"ok": False, "fehler": "Claude hat nicht geantwortet."}

    @staticmethod
    def _inhalt_bauen(auftrag: str, bild_base64: str = "", bild_typ: str = "image/jpeg"):
        """Baut den Inhaltsblock einer Nachricht, wahlweise mit Bild."""
        if not bild_base64:
            return auftrag
        return [
            {"type": "image", "source": {"type": "base64", "media_type": bild_typ,
                                         "data": bild_base64}},
            {"type": "text", "text": auftrag},
        ]

    def text_anfrage(self, auftrag: str, bild_base64: str = "",
                     bild_typ: str = "image/jpeg", max_tokens: int = 1200) -> dict:
        """Eine einzelne Anfrage ohne Werkzeuge - gibt reinen Text zurück."""
        antwort = self._anfrage({
            "model": CLAUDE_MODEL,
            "max_tokens": max_tokens,
            "messages": [{"role": "user",
                          "content": self._inhalt_bauen(auftrag, bild_base64, bild_typ)}],
        })
        if not antwort.get("ok"):
            return antwort
        teile = [block.get("text", "") for block in antwort["daten"].get("content", [])
                 if block.get("type") == "text"]
        return {"ok": True, "text": "\n".join(teile).strip()}

    def json_anfrage(self, auftrag: str, bild_base64: str = "",
                     bild_typ: str = "image/jpeg", max_tokens: int = 2000) -> dict:
        """Eine Anfrage, deren Antwort als JSON erwartet wird."""
        antwort = self.text_anfrage(auftrag, bild_base64, bild_typ, max_tokens)
        if not antwort.get("ok"):
            return antwort
        daten = json_aus_text(antwort["text"])
        if daten is None:
            return {"ok": False,
                    "fehler": "Die Antwort war kein auswertbares JSON.",
                    "rohtext": antwort["text"][:500]}
        return {"ok": True, "daten": daten}

    # -- Verlauf ------------------------------------------------------------

    def _verlauf_kuerzen(self):
        """Kürzt den Verlauf auf 24 Nachrichten - immer beginnend bei einer Nutzerfrage.

        Beginnt der Verlauf mit einer Antwort oder einem Werkzeugergebnis, weist
        die Schnittstelle die ganze Anfrage ab. Deshalb wird vorne so lange
        abgeschnitten, bis eine echte Nutzernachricht am Anfang steht.
        """
        if len(self.verlauf) <= MAX_VERLAUF:
            return
        rest = self.verlauf[-MAX_VERLAUF:]
        while rest and not self._ist_echte_nutzerfrage(rest[0]):
            rest.pop(0)
        self.verlauf = rest

    @staticmethod
    def _ist_echte_nutzerfrage(nachricht: dict) -> bool:
        """Ist das eine Nutzernachricht, die nicht bloß ein Werkzeugergebnis ist?"""
        if nachricht.get("role") != "user":
            return False
        inhalt = nachricht.get("content")
        if isinstance(inhalt, str):
            return True
        for block in inhalt or []:
            if isinstance(block, dict) and block.get("type") == "tool_result":
                return False
        return True

    def verlauf_leeren(self):
        """Beginnt ein neues Gespräch."""
        self.verlauf = []

    # -- Denkschleife -------------------------------------------------------

    def denken(self, eingabe: str, protokollieren: bool = True, bild_base64: str = "",
               bild_typ: str = "image/jpeg", bild_quelle: str = "Kamera") -> str:
        """Die Hauptschleife: fragen, Werkzeuge ausführen, antworten.

        Mit ``bild_base64`` liegt der Frage ein Bild bei - von der Kamera oder
        dem geteilten Bildschirm im Browser. Es geht nur in dieser einen Runde
        mit; danach steht im Verlauf nur noch ein Vermerk, sonst würde jede
        weitere Frage das Bild erneut mitschleppen.
        """
        if not bild_base64:
            return self._denken(eingabe, protokollieren)
        try:
            return self._denken(eingabe, protokollieren,
                                bild=(bild_base64, bild_typ, bild_quelle))
        finally:
            for nachricht in self.verlauf:
                inhalt = nachricht.get("content")
                if isinstance(inhalt, list):
                    nachricht["content"] = [
                        {"type": "text", "text": "[Bild: %s]" % bild_quelle}
                        if isinstance(b, dict) and b.get("type") == "image" else b
                        for b in inhalt]

    def _denken(self, eingabe: str, protokollieren: bool = True, bild=None) -> str:
        """Die eigentliche Schleife - siehe ``denken``."""
        eingabe = (eingabe or "").strip()
        if not eingabe:
            return ""
        if not self.einsatzbereit():
            return ("Es ist noch kein Gehirn eingerichtet. Trag im Browser einen "
                    "Gratis-Schlüssel ein, dann kann ich dir antworten.")

        if protokollieren:
            self.memory.verlauf_anhaengen("user", eingabe)
        if bild:
            daten, typ, quelle = bild
            inhalt = self._inhalt_bauen(
                "[Dazu ein Bild von meiner %s - schau es dir direkt an, dafür brauchst du "
                "kein Werkzeug.]\n%s" % (quelle, eingabe), daten, typ)
        else:
            inhalt = eingabe
        self.verlauf.append({"role": "user", "content": inhalt})
        self._verlauf_kuerzen()

        systemtext = self.systemprompt(eingabe)
        katalog = self.tools.katalog()

        for runde in range(MAX_RUNDEN):
            antwort = self._anfrage({
                "model": CLAUDE_MODEL,
                "max_tokens": CLAUDE_MAX_TOKENS,
                "system": systemtext,
                "tools": katalog,
                "messages": self.verlauf,
            })
            if not antwort.get("ok"):
                self.letzter_fehler = antwort.get("fehler", "")
                return self.letzter_fehler

            nachricht = antwort["daten"]
            inhalt = nachricht.get("content", [])
            self.verlauf.append({"role": "assistant", "content": inhalt})

            werkzeugaufrufe = [b for b in inhalt if b.get("type") == "tool_use"]
            if not werkzeugaufrufe:
                text = "\n".join(b.get("text", "") for b in inhalt
                                 if b.get("type") == "text").strip()
                if protokollieren and text:
                    self.memory.verlauf_anhaengen("assistant", text)
                return text or "Dazu habe ich nichts zu sagen."

            ergebnisse = []
            direkt = []
            for aufruf in werkzeugaufrufe:
                name = aufruf.get("name", "")
                argumente = aufruf.get("input") or {}
                print("[werkzeug] %s %s" % (name, json.dumps(argumente,
                                                             ensure_ascii=False)[:200]))
                ergebnis = self.tools.run(name, argumente)
                satz = direkt_satz(name, argumente, ergebnis) if direkt is not None else ""
                if satz:
                    direkt.append(satz)
                else:
                    direkt = None
                try:
                    text = json.dumps(ergebnis, ensure_ascii=False, default=str)[:6000]
                except (TypeError, ValueError):
                    text = str(ergebnis)[:6000]
                ergebnisse.append({"type": "tool_result", "tool_use_id": aufruf.get("id"),
                                   "content": text,
                                   "is_error": not bool(ergebnis.get("ok"))})
            self.verlauf.append({"role": "user", "content": ergebnisse})
            self._verlauf_kuerzen()

            # Einfache Aktionen sagen selbst, was passiert ist. Bei den langsamen
            # Gratis-Gehirnen spart das die zweite Runde - Jarvis handelt, statt
            # das Ergebnis noch einmal umformulieren zu lassen.
            if direkt and not ANTHROPIC_API_KEY and len(" ".join(direkt)) <= 400:
                text = " ".join(direkt)
                self.verlauf.append({"role": "assistant",
                                     "content": [{"type": "text", "text": text}]})
                if protokollieren:
                    self.memory.verlauf_anhaengen("assistant", text)
                return text

        return ("Ich habe es %d Mal versucht und komme nicht weiter. Sag mir bitte "
                "genauer, was du brauchst." % MAX_RUNDEN)

    def arbeiten(self, systemtext: str, auftrag: str, werkzeugnamen: list = None,
                 max_runden: int = 6) -> str:
        """Eine abgeschlossene Arbeitsschleife ohne eigenen Gesprächsverlauf.

        Damit arbeitet eine Fachkraft ihren Auftrag ab: eigener Systemprompt,
        eigener Werkzeugsatz, eigenes Ende. Der Verlauf des Hauptgesprächs
        bleibt davon unberührt - sonst würde jeder Zwischenschritt einer
        Fachkraft den Kontext des Chefs zumüllen.
        """
        if not self.einsatzbereit():
            return ("Es ist noch kein Gehirn eingerichtet.")

        katalog = self.tools.katalog()
        if werkzeugnamen:
            erlaubt = set(werkzeugnamen)
            katalog = [w for w in katalog if w["name"] in erlaubt]
            if not katalog:
                return "Für diesen Auftrag stehen keine Werkzeuge bereit."

        nachrichten = [{"role": "user", "content": auftrag}]
        for _ in range(max(1, int(max_runden))):
            antwort = self._anfrage({
                "model": CLAUDE_MODEL,
                "max_tokens": CLAUDE_MAX_TOKENS,
                "system": systemtext,
                "tools": katalog,
                "messages": nachrichten,
            })
            if not antwort.get("ok"):
                return antwort.get("fehler", "Der Auftrag ist fehlgeschlagen.")

            inhalt = antwort["daten"].get("content", [])
            nachrichten.append({"role": "assistant", "content": inhalt})
            aufrufe = [b for b in inhalt if b.get("type") == "tool_use"]
            if not aufrufe:
                return "\n".join(b.get("text", "") for b in inhalt
                                  if b.get("type") == "text").strip()

            ergebnisse = []
            for aufruf in aufrufe:
                name = aufruf.get("name", "")
                print("[fachkraft] %s" % name)
                ergebnis = self.tools.run(name, aufruf.get("input") or {})
                try:
                    text = json.dumps(ergebnis, ensure_ascii=False,
                                      default=str)[:6000]
                except (TypeError, ValueError):
                    text = str(ergebnis)[:6000]
                ergebnisse.append({"type": "tool_result",
                                   "tool_use_id": aufruf.get("id"),
                                   "content": text,
                                   "is_error": not bool(ergebnis.get("ok"))})
            nachrichten.append({"role": "user", "content": ergebnisse})

        return ("Ich bin nach %d Schritten nicht fertig geworden und höre auf."
                % max_runden)

    def antworten(self, eingabe: str) -> str:
        """Denken und die Antwort aussprechen."""
        antwort = self.denken(eingabe)
        if antwort and self.stimme is not None:
            self.stimme.sprich(antwort)
        elif antwort:
            print("Jarvis: %s" % antwort)
        return antwort

    # -- Briefings ----------------------------------------------------------

    def briefing_morgens(self) -> str:
        """Das Morgenbriefing - Termine, Post, Offenes, Wetter."""
        bausteine = self._bausteine_sammeln(morgens=True)
        if not self.einsatzbereit():
            return self._briefing_ohne_claude(bausteine, morgens=True)
        auftrag = ("Sprich jetzt dein Morgenbriefing. Vier bis sechs Sätze, gesprochen, "
                   "ohne Aufzählungen. Beginne mit einer kurzen Begrüßung. Nenne die "
                   "Termine, das Wichtigste aus der Post und was offen ist. Wenn etwas "
                   "davon nicht abrufbar war, sag es kurz und erfinde nichts.\n\n"
                   "Das sind die Daten:\n%s" % bausteine)
        antwort = self.denken(auftrag, protokollieren=False)
        return antwort

    def briefing_abends(self) -> str:
        """Der Abendrückblick - Zahlen, Leads, offene Punkte, Tagesbericht."""
        try:
            self.recall.tag_zusammenfassen(self)
        except Exception as fehler:
            print("[agent] Tagesbericht fehlgeschlagen: %s" % fehler)
        bausteine = self._bausteine_sammeln(morgens=False)
        if not self.einsatzbereit():
            return self._briefing_ohne_claude(bausteine, morgens=False)
        auftrag = ("Sprich jetzt deinen Abendrückblick. Vier bis sechs Sätze, gesprochen, "
                   "ohne Aufzählungen. Wie der Tag lief, was er morgen anpacken sollte, "
                   "und wenn ein Lead liegen bleibt, sag das deutlich.\n\n"
                   "Das sind die Daten:\n%s" % bausteine)
        return self.denken(auftrag, protokollieren=False)

    def _bausteine_sammeln(self, morgens: bool) -> str:
        """Sammelt die Fakten für ein Briefing - jeder Fehler bleibt sichtbar."""
        teile = []

        if morgens and self.tools.kalender.verfuegbar():
            teile.append("Kalender: %s" % self.tools.kalender.zusammenfassung(1))
        if morgens and self.tools.mail.lesen_moeglich():
            teile.append("Posteingang: %s" % self.tools.mail.zusammenfassung(10))
        if morgens and WETTER_ORT:
            wetter = self.tools.welt.wetter(WETTER_ORT)
            teile.append("Wetter: %s" % (wetter.get("text") or wetter.get("fehler")))

        punkte = self.memory.punkte_offen()
        teile.append("Offene Punkte: %s"
                     % ("; ".join(p["text"] for p in punkte[:8]) if punkte else "keine"))

        leads = self.tools.call_analysis.offene_leads()
        teile.append("Leads: %s" % leads.get("text", ""))

        if not morgens:
            auswertung = self.tools.bookkeeping.auswertung()
            teile.append("Zahlen des Monats: %s" % auswertung.get("text", ""))
            belege = self.tools.bookkeeping.fehlende_belege()
            teile.append("Belege: %s" % belege.get("text", ""))
            muster = self.tools.call_analysis.verkaufsmuster(30)
            teile.append("Vertrieb: %s" % muster.get("text", ""))

        return "\n".join(teile)

    @staticmethod
    def _briefing_ohne_claude(bausteine: str, morgens: bool) -> str:
        """Rückfallebene ohne Schlüssel: die nackten Fakten, nichts Erfundenes."""
        kopf = ("Guten Morgen. Ohne eingerichtetes Gehirn kann ich nur die nackten Zahlen "
                "vorlesen." if morgens else
                "Feierabend. Ohne eingerichtetes Gehirn kann ich nur die nackten Zahlen "
                "vorlesen.")
        return "%s\n%s" % (kopf, bausteine)

    # -- Übersicht ----------------------------------------------------------

    def zustand(self) -> dict:
        """Was ist bereit - für den Selbsttest."""
        return {"schluessel": self.einsatzbereit(), "modell": CLAUDE_MODEL,
                "verlauf": len(self.verlauf), "werkzeuge": len(self.tools.namen()),
                "gedaechtnis": self.memory.statistik()}


# =========================================================================
# run  -  Betriebsarten - was passiert, wenn Jarvis gestartet wird.
# 
# Ohne Angabe startet die Web-App: Jarvis läuft dann im Browser, das Mikrofon
# kommt vom Browser, und vom Handy im selben WLAN geht es auch. Wer lieber im
# Terminal spricht, nimmt ``hoeren``.
# 
#     python3 jarvis.py             Web-App im Browser - der Normalfall
#     python3 jarvis.py web --offen auch vom Handy im eigenen WLAN
#     python3 jarvis.py hoeren      im Terminal zuhören, ohne Browser
#     python3 jarvis.py chat        tippen statt sprechen
#     python3 jarvis.py telegram    vom Handy aus
#     python3 jarvis.py status      voller Stand des Betriebs
#     python3 jarvis.py briefing    Briefing sofort
#     python3 jarvis.py abend       Abendrückblick sofort
#     python3 jarvis.py dashboard   Dashboard bauen
#     python3 jarvis.py export      Buchhaltung als CSV
#     python3 jarvis.py stimme      Stimmprofil einlernen
#     python3 jarvis.py stimmen     ElevenLabs-Stimme aussuchen
#     python3 jarvis.py test        Selbsttest
#     python3 jarvis.py einrichten  geführte Ersteinrichtung
# =========================================================================

#!/usr/bin/env python3
# -*- coding: utf-8 -*-



BANNER = r"""
   _   _   ___  _   _ ___ ___
  | | /_\ | _ \| | | |_ _/ __|   Persönlicher Assistent
  | |/ _ \|   /| |_| || |\__ \   Gebäudereinigung
 _/ /_/ \_\_|_\ \___/|___|___/   alles lokal auf diesem Rechner
|__/
"""


def agent_aufbauen(mit_stimme: bool = True):
    """Baut Agent, Sprachausgabe und startet die MCP-Dienste."""
    stimme = Stimme() if mit_stimme else None
    agent = JarvisAgent(stimme=stimme)
    bericht = agent.dienste_starten()
    if bericht.get("gestartet"):
        print("[mcp] gestartet: %s" % ", ".join(bericht["gestartet"]))
    if bericht.get("fehlgeschlagen"):
        for eintrag in bericht["fehlgeschlagen"]:
            print("[mcp] nicht gestartet: %s" % eintrag)
    return agent, stimme


# ---------------------------------------------------------------------------
# Dauerbetrieb
# ---------------------------------------------------------------------------

def dauerbetrieb():
    """Hört auf das Weckwort und meldet sich zu den eingestellten Zeiten."""
    print(BANNER)
    agent, stimme = agent_aufbauen()
    profil = Sprecherprofil()

    zeitplan = Scheduler(agent=agent, routines=agent.tools.routines,
                         ausgabe=stimme.sprich)
    zeitplan.start()
    print("[zeitplan] Morgens %s, abends %s." % (BRIEFING_MORGENS,
                                                 BRIEFING_ABENDS))
    for eintrag in zeitplan.uebersicht():
        print("           %s  %s" % (eintrag["uhrzeit"], eintrag["beschreibung"]))

    if not stimme.mikrofon_bereit():
        print("\n[!] Kein Mikrofonzugriff. Ich wechsle in den Tippbetrieb.")
        stimme.sprich("Ich komme nicht an das Mikrofon. Wir tippen erst einmal.")
        zeitplan.stop()
        return chatbetrieb(agent, stimme)

    if not agent.einsatzbereit():
        stimme.sprich("Es ist noch kein Gehirn eingerichtet. Öffne Jarvis im Browser "
                      "und trag einen Gratis-Schlüssel ein.")
        print("Starte die Einrichtung mit: python3 jarvis.py einrichten")

    stimme.sprich("Ich bin da. Sag Hey Jarvis, wenn du etwas brauchst.")
    print("\nIch höre zu. Abbrechen mit Strg und C.\n")

    try:
        while True:
            pfad = stimme.aufnehmen_bis_pause(still_signal=True)
            if not pfad:
                continue
            try:
                text = stimme.transkribieren(pfad)
                if not text:
                    continue
                erkannt, befehl = weckwort_pruefen(text)
                if not erkannt:
                    continue

                pruefung = profil.ist_der_nutzer(pfad)
                if not pruefung["erkannt"]:
                    print("[stimme] %s - ich reagiere nicht." % pruefung["grund"])
                    continue
            finally:
                try:
                    os.remove(pfad)
                except OSError:
                    pass

            stimme.signal("verstanden")
            if not befehl:
                stimme.sprich("Ja?")
                nachtrag = stimme.zuhoeren()
                if not nachtrag:
                    continue
                befehl = nachtrag

            print("Du: %s" % befehl)
            try:
                agent.antworten(befehl)
            except Exception as fehler:
                stimme.signal("fehler")
                print("[fehler] %s" % fehler)
                stimme.sprich("Da ist etwas schiefgegangen: %s" % fehler)
    except KeyboardInterrupt:
        print("\nBis später.")
        stimme.sprich("Bis später.")
    finally:
        zeitplan.stop()
        agent.tools.mcp.stoppen()


# ---------------------------------------------------------------------------
# Tippbetrieb
# ---------------------------------------------------------------------------

def chatbetrieb(agent=None, stimme=None):
    """Tippen statt sprechen - der Notfallweg, wenn das Mikrofon streikt."""
    if agent is None:
        print(BANNER)
        agent, stimme = agent_aufbauen(mit_stimme=True)
    print("Tippbetrieb. 'ende' beendet, 'neu' beginnt ein neues Gespräch.\n")
    try:
        while True:
            try:
                eingabe = input("Du: ").strip()
            except (EOFError, KeyboardInterrupt):
                break
            if not eingabe:
                continue
            if eingabe.lower() in ("ende", "exit", "quit", "schluss", "feierabend jarvis"):
                break
            if eingabe.lower() == "neu":
                agent.verlauf_leeren()
                print("Jarvis: Neues Gespräch.")
                continue
            antwort = agent.denken(eingabe)
            print("Jarvis: %s\n" % antwort)
            if stimme is not None:
                stimme.sprich(antwort)
    finally:
        agent.tools.mcp.stoppen()
    print("Bis später.")


# ---------------------------------------------------------------------------
# Telegram-Betrieb
# ---------------------------------------------------------------------------

def telegrambetrieb():
    """Jarvis vom Handy aus bedienen."""
    print(BANNER)
    agent, stimme = agent_aufbauen()
    telegram = agent.tools.telegram
    if not telegram.verfuegbar():
        print("Telegram ist nicht eingerichtet. Starte: python3 jarvis.py einrichten")
        return
    telegram.senden("Ich bin da. Schreib oder sprich einfach.")
    print("Telegram-Betrieb läuft. Abbrechen mit Strg und C.\n")

    zeitplan = Scheduler(agent=agent, routines=agent.tools.routines,
                         ausgabe=lambda text: telegram.senden(text))
    zeitplan.start()
    try:
        while True:
            for nachricht in telegram.nachrichten_holen(timeout=25):
                text = (nachricht.get("text") or "").strip()
                if not text and nachricht.get("sprachdatei"):
                    text = stimme.transkribieren(nachricht["sprachdatei"])
                    try:
                        os.remove(nachricht["sprachdatei"])
                    except OSError:
                        pass
                if not text:
                    continue
                erkannt, befehl = weckwort_pruefen(text)
                befehl = befehl if erkannt and befehl else text
                print("Du: %s" % befehl)
                antwort = agent.denken(befehl)
                telegram.senden(antwort)
                print("Jarvis: %s\n" % antwort)
    except KeyboardInterrupt:
        print("\nBeendet.")
    finally:
        zeitplan.stop()
        agent.tools.mcp.stoppen()


# ---------------------------------------------------------------------------
# Einzelaufgaben
# ---------------------------------------------------------------------------

def briefing_sofort(abends: bool = False):
    """Spricht sofort das Morgen- oder Abendbriefing."""
    agent, stimme = agent_aufbauen()
    try:
        text = agent.briefing_abends() if abends else agent.briefing_morgens()
        stimme.sprich(text)
        print("\n%s" % text)
    finally:
        agent.tools.mcp.stoppen()


def dashboard_bauen():
    """Baut das Command Center."""
    agent, _ = agent_aufbauen(mit_stimme=False)
    try:
        ergebnis = agent.tools.dashboard.bauen(mit_netz=True)
        print(ergebnis.get("text") or ergebnis.get("fehler"))
        if ergebnis.get("ok"):
            import subprocess
            import shutil as _shutil
            if _shutil.which("open"):
                subprocess.run(["open", ergebnis["datei"]], shell=False,
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    finally:
        agent.tools.mcp.stoppen()


# Was Jarvis kann - nach Bereichen, für die Übersicht im Terminal.
FAEHIGKEITEN = [
    ("Gedächtnis", ("notiz", "kontakt_", "punkt", "kennzahl", "gedaechtnis", "tagesbericht",
                    "rueckblick", "protokoll", "erinnerung")),
    ("Verkauf", ("lead", "angebot", "nachfass", "pipeline", "verkauf", "gespraech",
                 "autopilot", "heute_zu_tun", "anrufliste", "offene_leads")),
    ("Geld", ("buchung", "beleg", "auswertung", "csv", "cashflow", "fixkosten", "bedarf",
              "fehlende_belege")),
    ("Kommunikation", ("mail", "nachricht", "anrufen", "sms", "termin")),
    ("Web und Wissen", ("webseite", "recherche", "wetter", "flug", "browser")),
    ("Sehen und Mac", ("umschauen", "bildschirm", "systeminfo", "ordner", "programm",
                       "skript", "werkstatt")),
    ("Team und Abläufe", ("mitarbeiter", "team", "lagebericht", "routine", "dashboard")),
]
CYAN, HELL, AUS = "\033[36m", "\033[96m", "\033[0m"


def faehigkeiten_text(namen: list, bereit: bool = True) -> str:
    """Die Übersicht aller Fähigkeiten, nach Bereichen."""
    farbe = sys.stdout.isatty() if sys.stdout is not None else False
    c, h, a = (CYAN, HELL, AUS) if farbe else ("", "", "")
    zeilen = ["", "  %s%d FÄHIGKEITEN BEREIT%s%s" % (h, len(namen), a,
                                                    "" if bereit else
                                                    "  (noch ohne Gehirn - im Browser einrichten)")]
    vergeben = set()
    for bereich, anfaenge in FAEHIGKEITEN:
        treffer = [n for n in namen if n not in vergeben and n.startswith(anfaenge)]
        vergeben.update(treffer)
        if treffer:
            zeilen.append("  %s%-17s%s %s" % (c, bereich, a, ", ".join(treffer)))
    rest = [n for n in namen if n not in vergeben]
    if rest:
        zeilen.append("  %s%-17s%s %s" % (c, "Weitere", a, ", ".join(rest)))
    zeilen.append("")
    zeilen.append("  Sprich im Browser mit mir - oder schreib mir hier im Terminal.")
    zeilen.append("  'hilfe' zeigt diese Liste, 'beenden' oder Strg+C hört auf.")
    return "\n".join(zeilen)


def terminal_gespraech(agent, web):
    """Jarvis im Terminal: Aufträge tippen, während der Browser weiterläuft."""
    farbe = sys.stdout.isatty()
    c, h, a = (CYAN, HELL, AUS) if farbe else ("", "", "")
    while True:
        try:
            eingabe = input("\n  %sDu ›%s " % (h, a)).strip()
        except EOFError:
            return
        if not eingabe:
            continue
        if eingabe.lower() in ("beenden", "exit", "quit", "tschüss", "ende"):
            return
        if eingabe.lower() in ("hilfe", "?", "help"):
            print(faehigkeiten_text(agent.tools.namen(), agent.einsatzbereit()))
            continue
        beginn = time.time()
        with web._denkt:  # nie gleichzeitig mit dem Browser im selben Verlauf
            antwort = agent.denken(eingabe)
        print("  %sJarvis ›%s %s  %s(%.1f s)%s" % (c, a, antwort, c, time.time() - beginn, a))


def webbetrieb(argumente=None):
    """Startet Jarvis als Web-App im Browser."""
    argumente = argumente or []
    offen = "--offen" in argumente or "offen" in argumente
    port = STANDARD_PORT
    for teil in argumente:
        if teil.isdigit():
            port = int(teil)

    print(BANNER)
    agent, stimme = agent_aufbauen(mit_stimme=False)
    del stimme
    web = JarvisWeb(agent, port=port, offen=offen)

    # Der Zeitplan meldet in die Web-App, nicht ins Terminal - dort schaut
    # um 6:45 niemand hin.
    zeitplan = Scheduler(agent=agent, routines=agent.tools.routines,
                         ausgabe=web.melden)
    zeitplan.start()
    print("  Briefings: morgens %s, abends %s"
          % (BRIEFING_MORGENS, BRIEFING_ABENDS))

    adresse = web.adresse()
    print("  Jarvis läuft jetzt im Browser:")
    print("     %s" % adresse)
    if offen:
        print("\n  Der Zugang ist offen im WLAN - deshalb steht ein Schlüssel in")
        print("  der Adresse. Ohne ihn kommt niemand herein. Gib die Adresse nur")
        print("  weiter, wenn du willst, dass jemand alles darf, was du darfst.")
    else:
        print("     (nur auf diesem Rechner erreichbar)")
    import shutil as _shutil
    import subprocess as _subprocess
    import threading as _threading
    if _shutil.which("open") and os.environ.get("JARVIS_KEIN_BROWSER") != "1":
        try:
            _subprocess.run(["open", adresse], shell=False, timeout=15,
                            stdout=_subprocess.DEVNULL, stderr=_subprocess.DEVNULL)
        except (OSError, _subprocess.SubprocessError):
            pass

    print(faehigkeiten_text(agent.tools.namen(), agent.einsatzbereit()))
    web.starten(blockierend=False)
    try:
        if sys.stdin is not None and sys.stdin.isatty():
            terminal_gespraech(agent, web)
        else:
            # Ohne Tastatur (etwa als Hintergrunddienst): einfach weiterlaufen.
            _threading.Event().wait()
    except KeyboardInterrupt:
        pass
    finally:
        zeitplan.stop()
        web.stoppen()
        agent.tools.mcp.stoppen()
    print("\nBeendet.")
    return 0


def lage_sagen():
    """Sagt den vollständigen aktuellen Stand des Betriebs."""
    agent, stimme = agent_aufbauen()
    try:
        lage = agent.tools.team.lagebericht(agent.tools)
        text = lage.get("text") or lage.get("fehler", "Kein Stand abrufbar.")
        print("\n%s\n" % text)
        for name, bereich in (lage.get("bereiche") or {}).items():
            if isinstance(bereich, dict) and bereich.get("text"):
                print("  %-14s %s" % (name + ":", bereich["text"][:100]))
            elif isinstance(bereich, dict) and not bereich.get("ok", True):
                print("  %-14s nicht abrufbar: %s"
                      % (name + ":", bereich.get("fehler", "")[:70]))
        stimme.sprich(text)
        return 0
    finally:
        agent.tools.mcp.stoppen()


def buchhaltung_exportieren(argumente=None):
    """Schreibt die Buchungen als CSV für den Steuerberater."""
    argumente = argumente or []
    von = argumente[0] if len(argumente) > 0 else ""
    bis = argumente[1] if len(argumente) > 1 else ""
    agent, _ = agent_aufbauen(mit_stimme=False)
    try:
        ergebnis = agent.tools.bookkeeping.csv_export(von, bis)
        print(ergebnis.get("text") or ergebnis.get("fehler"))
        return 0 if ergebnis.get("ok") else 1
    finally:
        agent.tools.mcp.stoppen()


def stimmprofil_einlernen():
    """Lernt die Stimme des Nutzers ein."""
    stimme = Stimme()
    profil = Sprecherprofil()
    ergebnis = profil.einlernen(stimme)
    print(ergebnis.get("text") or ergebnis.get("fehler"))
    if ergebnis.get("ok"):
        env_setzen("STIMMPRUEFUNG_AN", "ja")
        stimme.sprich(ergebnis["text"])
    else:
        stimme.sprich(ergebnis.get("fehler", "Das hat nicht geklappt."))


def stimme_aussuchen():
    """Listet die ElevenLabs-Stimmen auf und speichert die gewählte."""
    if not ELEVENLABS_API_KEY:
        print("Für ElevenLabs ist kein Schlüssel hinterlegt. Ich benutze die "
              "Systemstimme von macOS - die kostet nichts und ist immer da.")
        stimme = Stimme()
        print("Aktuelle Systemstimme: %s" % (stimme.macos_stimme or "keine deutsche"))
        return
    try:
        anfrage = urllib.request.Request(
            "https://api.elevenlabs.io/v1/voices",
            headers={"xi-api-key": ELEVENLABS_API_KEY})
        with urllib.request.urlopen(anfrage, timeout=30) as antwort:
            daten = json.loads(antwort.read().decode("utf-8"))
    except (urllib.error.URLError, OSError, ValueError) as fehler:
        print("Die Stimmenliste ist nicht erreichbar: %s" % fehler)
        return

    stimmen = daten.get("voices", []) or []
    if not stimmen:
        print("Es sind keine Stimmen hinterlegt.")
        return
    for nummer, eintrag in enumerate(stimmen, 1):
        marken = eintrag.get("labels") or {}
        print("%2d. %-22s %s" % (nummer, eintrag.get("name", "?"),
                                 ", ".join("%s: %s" % (k, v) for k, v in marken.items())))
    try:
        wahl = input("\nNummer der Stimme (Enter bricht ab): ").strip()
    except (EOFError, KeyboardInterrupt):
        return
    if not wahl.isdigit() or not (1 <= int(wahl) <= len(stimmen)):
        print("Nichts geändert.")
        return
    gewaehlt = stimmen[int(wahl) - 1]
    env_setzen("ELEVENLABS_VOICE_ID", gewaehlt.get("voice_id", ""))
    print("Gespeichert: %s" % gewaehlt.get("name"))
    Stimme().sprich("So klinge ich jetzt.")


# ---------------------------------------------------------------------------
# Selbsttest
# ---------------------------------------------------------------------------

def _marke(zustand: str) -> str:
    return {"ok": "[ok]", "fehlt": "[--]", "fehler": "[!!]"}.get(zustand, "[??]")


def selbsttest() -> int:
    """Geht jeden Baustein durch.

    ``[ok]`` läuft, ``[--]`` läuft ohne diese Funktion weiter, ``[!!]`` ist kaputt.
    """
    print(BANNER)
    print("SELBSTTEST\n" + "=" * 62)
    fehler_gesamt = 0

    def melden(name, zustand, hinweis=""):
        nonlocal fehler_gesamt
        if zustand == "fehler":
            fehler_gesamt += 1
        print("%s %-26s %s" % (_marke(zustand), name, hinweis))

    # -- Konfiguration --
    print("\nGrundlage")
    melden("Konfiguration", "ok", "Basis: %s" % BASIS)
    melden("Anthropic-Schlüssel", "ok" if ANTHROPIC_API_KEY else "fehlt",
           CLAUDE_MODEL if ANTHROPIC_API_KEY
           else "ohne ihn kann Jarvis nicht denken")

    # -- Agent und Gedächtnis --
    print("\nGedächtnis")
    try:
        agent = JarvisAgent()
        melden("Agent gestartet", "ok", "%d Werkzeuge" % len(agent.tools.namen()))
    except Exception as fehler:
        melden("Agent gestartet", "fehler", str(fehler))
        return 1

    memory = agent.memory
    try:
        notiz = memory.notiz_speichern("Selbsttest: Kunde Meier will Fensterreinigung",
                                       "test")
        gefunden = memory.notizen_suchen("Selbsttest")
        melden("Notiz speichern und finden", "ok" if gefunden else "fehler",
               "%d Treffer" % len(gefunden))
        memory.notiz_loeschen(notiz.get("id"))
    except Exception as fehler:
        melden("Notiz speichern und finden", "fehler", str(fehler))

    try:
        memory.kontakt_anlegen("Selbsttest Berger", "Berger GmbH")
        treffer = memory.kontakt_suchen("Selbsttest Berger")
        melden("Kontakt anlegen und suchen", "ok" if treffer else "fehler",
               "%d Treffer" % len(treffer))
    except Exception as fehler:
        melden("Kontakt anlegen und suchen", "fehler", str(fehler))

    try:
        block = agent.recall.gedaechtnis_block("Angebot Meier")
        melden("Gedächtnis nachschlagen", "ok", "%d Zeichen Kontext" % len(block))
    except Exception as fehler:
        melden("Gedächtnis nachschlagen", "fehler", str(fehler))

    # -- Buchhaltung --
    print("\nBuchhaltung")
    try:
        vorsteuer = mwst_aus_brutto(130.40, 20)
        melden("MwSt-Rechnung 130,40 bei 20%", "ok" if vorsteuer == 21.73 else "fehler",
               "%.2f Euro (erwartet 21,73)" % vorsteuer)
    except Exception as fehler:
        melden("MwSt-Rechnung", "fehler", str(fehler))

    try:
        auswertung = agent.tools.bookkeeping.auswertung()
        melden("Auswertung", "ok", auswertung["text"][:70])
        belege = agent.tools.bookkeeping.fehlende_belege()
        melden("Fehlende Belege", "ok", belege["text"][:70])
    except Exception as fehler:
        melden("Auswertung", "fehler", str(fehler))

    # -- Vertrieb --
    print("\nVertrieb")
    try:
        leads = agent.tools.call_analysis.offene_leads()
        melden("Offene Leads", "ok", leads["text"][:70])
        muster = agent.tools.call_analysis.verkaufsmuster()
        melden("Verkaufsmuster", "ok", muster["text"][:70])
    except Exception as fehler:
        melden("Vertrieb", "fehler", str(fehler))

    # -- Routinen --
    print("\nRoutinen")
    try:
        routinen = agent.tools.routines
        routinen.routine_anlegen("Selbsttest Tagesbericht", "Zahlen zusammenfassen",
                                 "18 Uhr")
        treffer = routinen.routine_finden("den Selbsttest Tages Bericht")
        melden("Routine mit ungenauem Namen finden",
               "ok" if treffer else "fehler",
               treffer["name"] if treffer else "nicht gefunden")
        geplant = routinen.geplante_routinen()
        melden("Routine im Zeitplan", "ok" if geplant else "fehler",
               "%d mit Uhrzeit" % len(geplant))
        routinen.routine_loeschen("Selbsttest Tagesbericht")
    except Exception as fehler:
        melden("Routinen", "fehler", str(fehler))

    # -- Zeitplan --
    print("\nZeitplan")
    try:
        from datetime import datetime as _dt
        pruefungen = [
            (_dt(2026, 1, 1, 9, 30), True, "9:30 bei 9:00-Job"),
            (_dt(2026, 1, 1, 8, 0), False, "8:00 bei 9:00-Job"),
            (_dt(2026, 1, 1, 14, 0), False, "14:00 bei 9:00-Job (zu spät)"),
        ]
        alle_ok = True
        for zeitpunkt, erwartet, name in pruefungen:
            tatsaechlich = ist_faellig("09:00", zeitpunkt)
            if tatsaechlich != erwartet:
                alle_ok = False
            melden(name, "ok" if tatsaechlich == erwartet else "fehler",
                   "%s (erwartet %s)" % (tatsaechlich, erwartet))
        del alle_ok
    except Exception as fehler:
        melden("Zeitplan", "fehler", str(fehler))

    # -- Sicherheit --
    print("\nSicherheit")
    try:
        abgewiesen = agent.tools.run("systeminfo", {"was": "rm -rf /"})
        melden("systeminfo mit 'rm -rf /' abgewiesen",
               "ok" if not abgewiesen.get("ok") else "fehler",
               abgewiesen.get("fehler", "")[:60])
        abgewiesen = agent.tools.run("ordner_zeigen", {"pfad": ".;rm -rf /"})
        melden("ordner_zeigen mit ';' abgewiesen",
               "ok" if not abgewiesen.get("ok") else "fehler",
               abgewiesen.get("fehler", "")[:60])
        unbekannt = agent.tools.run("beliebiger_befehl", {})
        melden("Unbekanntes Werkzeug abgewiesen",
               "ok" if not unbekannt.get("ok") else "fehler", "")
        pflichtig = sorted(n for n in agent.tools.namen()
                           if agent.tools.braucht_freigabe(n))
        melden("Freigabepflichtige Werkzeuge", "ok", ", ".join(pflichtig))
    except Exception as fehler:
        melden("Sicherheit", "fehler", str(fehler))

    # -- MCP --
    print("\nMCP")
    try:
        vorlage_schreiben()
        client = MCPClient()
        client.konfiguration_lesen()
        eingeschaltet = [name for name, eintrag in
                         (client.konfig.get("server") or {}).items()
                         if isinstance(eintrag, dict) and not eintrag.get("aus", True)]
        melden("Konfiguration", "ok",
               "%d Dienste hinterlegt, %d eingeschaltet"
               % (len(client.konfig.get("server") or {}), len(eingeschaltet)))
        testserver = os.path.join(str(BASIS), "tests", "mcp_testserver.py")
        if os.path.exists(testserver):
            probe = MCPClient()
            probe.konfig = {"server": {"test": {
                "aus": False, "befehl": sys.executable, "argumente": [testserver],
                "ohne_rueckfrage": ["liste_lesen"]}}}
            server = MCPServer("test", probe.konfig["server"]["test"])
            if server.starten():
                probe.server_hinzufuegen("test", server)
                werkzeuge = [w["name"] for w in probe.alle_werkzeuge()]
                melden("Testserver Werkzeuge", "ok" if len(werkzeuge) == 2 else "fehler",
                       ", ".join(werkzeuge))
                frei = probe.braucht_freigabe("mcp__test__liste_lesen")
                pflicht = probe.braucht_freigabe("mcp__test__datei_loeschen")
                melden("ohne_rueckfrage läuft durch",
                       "ok" if frei is False else "fehler", "")
                melden("Rest fragt nach", "ok" if pflicht is True else "fehler", "")
                ergebnis = probe.aufrufen("mcp__test__liste_lesen", {"was": "test"})
                melden("Testaufruf", "ok" if ergebnis.get("ok") else "fehler",
                       ergebnis.get("text", ergebnis.get("fehler", ""))[:50])
                server.stoppen()
            else:
                melden("Testserver", "fehler", server.fehler)
        else:
            melden("Testserver", "fehlt", "tests/mcp_testserver.py nicht gefunden")
    except Exception as fehler:
        melden("MCP", "fehler", str(fehler))

    # -- Sprache --
    print("\nSprache")
    try:
        stimme = Stimme()
        zustand = stimme.zustand()
        melden("Sprachausgabe macOS", "ok" if zustand["macos_say"] else "fehlt",
               zustand["macos_stimme"])
        melden("ElevenLabs", "ok" if zustand["elevenlabs"] else "fehlt",
               "optional, die Systemstimme reicht")
        melden("Mikrofon", "ok" if zustand["mikrofon"] else "fehlt",
               zustand.get("mikrofon_grund", ""))
        melden("Spracherkennung lokal", "ok" if zustand["whisper_lokal"] else "fehlt",
               "" if zustand["whisper_lokal"] else "Paket faster-whisper fehlt")
        melden("Spracherkennung API", "ok" if zustand["whisper_api"] else "fehlt",
               "optional")
        erkannt, rest = weckwort_pruefen("Hey Javis, wie sieht mein Tag aus?")
        melden("Weckwort erkennen", "ok" if erkannt else "fehler", "Rest: %s" % rest)
        profil = Sprecherprofil()
        melden("Stimmprofil", "ok" if profil.eingelernt() else "fehlt",
               "entscheidet nur, ob Jarvis zuhört - gibt nie etwas frei")
    except Exception as fehler:
        melden("Sprache", "fehler", str(fehler))

    # -- Außenwelt --
    print("\nAußenwelt")
    try:
        melden("E-Mail lesen", "ok" if agent.tools.mail.lesen_moeglich() else "fehlt", "")
        melden("E-Mail senden", "ok" if agent.tools.mail.senden_moeglich() else "fehlt", "")
        melden("Kalender", "ok" if agent.tools.kalender.verfuegbar() else "fehlt", "")
        melden("Telegram", "ok" if agent.tools.telegram.verfuegbar() else "fehlt",
               "ohne ihn fragt Jarvis im Terminal nach Freigaben")
        kamera = agent.tools.kamera.zustand()
        melden("Kamera", "ok" if kamera["verfuegbar"] else "fehlt",
               kamera["programm"] if kamera["verfuegbar"] else "brew install imagesnap")
        bildschirm = agent.tools.bildschirm.zustand()
        melden("Bildschirmsteuerung",
               "ok" if bildschirm.get("pyautogui") and bildschirm.get("pillow") else "fehlt",
               "Skalierung %s" % bildschirm.get("skalierung"))
        telefon = agent.tools.telefon.zustand()
        melden("Telefon", "ok" if telefon["eingerichtet"] else "fehlt",
               ("eigene Nummer %s" % telefon["eigene_nummer"])
               if telefon["eingerichtet"]
               else "fuer Anrufe und SMS: TWILIO_SID, TWILIO_TOKEN, TWILIO_NUMMER")
        browser = agent.tools.browser.zustand()
        melden("Browser-Steuerung", "ok" if browser["verfuegbar"] else "fehlt",
               browser["hinweis"])
        wetter = agent.tools.welt.wetter(WETTER_ORT)
        melden("Wetter", "ok" if wetter.get("ok") else "fehlt",
               (wetter.get("text") or wetter.get("fehler", ""))[:60])
    except Exception as fehler:
        melden("Außenwelt", "fehler", str(fehler))

    # -- Dashboard --
    print("\nDashboard")
    try:
        ergebnis = agent.tools.dashboard.bauen()
        melden("Command Center bauen", "ok" if ergebnis.get("ok") else "fehler",
               ergebnis.get("datei", ergebnis.get("fehler", "")))
    except Exception as fehler:
        melden("Command Center bauen", "fehler", str(fehler))

    agent.tools.mcp.stoppen()

    print("\n" + "=" * 62)
    if fehler_gesamt == 0:
        print("Alles, was eingerichtet ist, funktioniert. [--] heißt nicht kaputt,")
        print("sondern: läuft ohne diese Funktion weiter.")
    else:
        print("%d Prüfungen sind fehlgeschlagen. Details stehen oben bei [!!]."
              % fehler_gesamt)
    print("=" * 62)
    return 0 if fehler_gesamt == 0 else 1


# ---------------------------------------------------------------------------
# Einstieg
# ---------------------------------------------------------------------------

def hauptprogramm(argumente=None) -> int:
    """Wählt die Betriebsart anhand des ersten Arguments."""
    argumente = argumente if argumente is not None else sys.argv[1:]
    modus = (argumente[0].strip().lower() if argumente else "")

    verzeichnisse_anlegen()
    vorlage_schreiben()

    if modus in ("", "start", "web", "browser", "app"):
        # Auch ohne Schlüssel startet der Webserver: den Schlüssel trägt man im
        # Browser ein. Eine Einrichtung im Terminal, die den Server gar nicht
        # erst startet, lässt den Nutzer vor einer toten Adresse stehen.
        if not ANTHROPIC_API_KEY:
            print("Noch kein Gehirn eingerichtet - das machst du gleich im "
                  "Browser.")
        return webbetrieb(argumente[1:] if argumente else [])
    elif modus in ("hoeren", "hören", "dauerbetrieb", "sprechen"):
        if not EINRICHTUNG_FERTIG and not ANTHROPIC_API_KEY:
            print("Jarvis ist noch nicht eingerichtet. Ich starte die Einrichtung.")
            einrichtung_starten()
            return 0
        dauerbetrieb()
    elif modus == "chat":
        chatbetrieb()
    elif modus == "telegram":
        telegrambetrieb()
    elif modus == "briefing":
        briefing_sofort(abends=False)
    elif modus in ("abend", "abendrueckblick", "feierabend"):
        briefing_sofort(abends=True)
    elif modus == "dashboard":
        dashboard_bauen()
    elif modus == "export":
        return buchhaltung_exportieren(argumente[1:])
    elif modus in ("status", "lage"):
        return lage_sagen()
    elif modus == "stimme":
        stimmprofil_einlernen()
    elif modus == "stimmen":
        stimme_aussuchen()
    elif modus == "test":
        return selbsttest()
    elif modus in ("einrichten", "setup"):
        einrichtung_starten()
    elif modus in ("hilfe", "--help", "-h", "help"):
        print(__doc__)
    else:
        print("Die Betriebsart '%s' kenne ich nicht.\n" % modus)
        print(__doc__)
        return 2
    return 0


# ===========================================================================
# Einstieg
# ===========================================================================

if __name__ == "__main__":
    try:
        sys.exit(hauptprogramm())
    except KeyboardInterrupt:
        print("\nAbgebrochen.")
        sys.exit(130)
