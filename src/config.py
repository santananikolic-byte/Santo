#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Konfiguration - liest ``config/.env`` und stellt alle Einstellungen bereit.

Alle Einstellungen liegen als Modul-Globals vor. Die anderen Module lesen sie
über ``config.NAME``. Beim Zusammenführen zur Einzeldatei ersetzt
``build_single.py`` das Präfix ``config.`` durch den blanken Namen, damit in
``jarvis.py`` weiterhin ``NAME`` gelesen wird. Deshalb müssen alle Namen in
diesem Modul projektweit eindeutig sein.
"""

import os
from pathlib import Path


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
RECHNUNGEN_VERZEICHNIS = BASIS / "rechnungen"
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
# Firmendaten für Rechnungen und Angebote (österreichische Pflichtangaben)
FIRMA_ADRESSE = _text("FIRMA_ADRESSE")
FIRMA_UID = _text("FIRMA_UID")
FIRMA_IBAN = _text("FIRMA_IBAN")
FIRMA_BIC = _text("FIRMA_BIC")
FIRMA_TELEFON = _text("FIRMA_TELEFON")
FIRMA_EMAIL = _text("FIRMA_EMAIL")
KLEINUNTERNEHMER = _wahrheit("KLEINUNTERNEHMER", False)
# Wer schon Rechnungen aus einem anderen Programm hat: nächste Nummer, z.B. 2026-046
RECHNUNG_START = _text("RECHNUNG_START")

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
                 PROFIL_VERZEICHNIS, EXPORT_VERZEICHNIS, RECHNUNGEN_VERZEICHNIS):
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
