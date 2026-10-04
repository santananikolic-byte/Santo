#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Der Router - welches Gehirn antwortet, und was es gekostet hat.

Zwei Gehirne: **Gemini** ist schnell und im Free Tier gratis, **Claude** kann
die Werkzeuge bedienen (Buchhaltung, Kalender, Post, Telefon ...) und denkt
gründlicher. Der Router entscheidet pro Frage mit festen, nachvollziehbaren
Regeln - kein Modell raten lassen, was ein Modell kosten darf.

**Im Zweifel Claude.** Gemini bekommt hier keine Werkzeuge. Eine Frage, hinter
der eine Handlung oder ein Datenzugriff stecken könnte, geht deshalb immer an
Claude. Gemini bekommt nur kurzes Gespräch und einfache Wissensfragen.

Jede Runde landet im **Gedankenlog** (``logs/gedankenlog.jsonl``): Frage,
Gehirn, Dauer, Tokens, geschätzte Kosten. Daraus rechnet sich der
Monatsverbrauch, an dem das Limit hängt.
"""

import json
import time
import urllib.error
import urllib.request
from datetime import datetime

import config

GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/models/%s:generateContent"
LOG_DATEI_NAME = "gedankenlog.jsonl"

# Wortstämme, hinter denen eine Handlung oder ein Datenzugriff stecken kann.
# Gemini kann das nicht ausführen - also geht es an Claude.
HANDLUNGSSTAEMME = (
    "termin", "kalender", "mail", "post", "nachricht", "sms", "anruf", "ruf ",
    "telefon", "telegram", "buch", "rechnung", "beleg", "quittung", "umsatz",
    "kasse", "steuer", "euro", "kunde", "kunden", "lead", "angebot", "auftrag",
    "aufgabe", "notiz", "merk", "vergiss", "speicher", "erinner", "lösch",
    "send", "schick", "schreib", "öffne", "browser", "such", "flug", "wetter",
    "bild", "kamera", "datei", "ordner", "dashboard", "briefing", "heute",
    "morgen", "woche", "offen", "mitarbeiter", "team",
)
# Wörter, die auf echte Denkarbeit hindeuten.
DENKSTAEMME = (
    "plane", "planen", "analysier", "rechne", "berechne", "strategie",
    "vergleich", "kalkulier", "begründ", "warum", "denk gründlich",
    "denk gruendlich", "gründlich", "gruendlich",
)


def gehirn_waehlen(frage: str, gemini_da: bool = None) -> tuple:
    """Gibt ``(gehirn, grund)`` zurück: ``"gemini"`` oder ``"claude"``."""
    if gemini_da is None:
        gemini_da = bool(config.GEMINI_API_KEY)
    text = (frage or "").strip().lower()
    if not gemini_da:
        return "claude", "kein Gemini-Schlüssel"
    if not text:
        return "claude", "leere Frage"
    if len(text.split()) > config.ROUTER_MAX_WOERTER:
        return "claude", "lange Frage"
    for stamm in DENKSTAEMME:
        if stamm in text:
            return "claude", "Denkarbeit (%s)" % stamm.strip()
    for stamm in HANDLUNGSSTAEMME:
        if stamm in text:
            return "claude", "braucht Werkzeuge (%s)" % stamm.strip()
    return "gemini", "kurze, einfache Frage"


# -- Gemini -----------------------------------------------------------------

def gemini_fragen(frage: str, systemtext: str, verlauf: list = None,
                  timeout: int = 30) -> dict:
    """Fragt Gemini. Rückgabe: ``{"ok", "text", "tokens_ein", "tokens_aus"}``.

    Der Verlauf ist die Claude-Liste; nur reine Textrunden werden übernommen,
    Werkzeugaufrufe bleiben draußen.
    """
    if not config.GEMINI_API_KEY:
        return {"ok": False, "fehler": "Kein Gemini-Schlüssel hinterlegt."}
    inhalte = []
    for nachricht in (verlauf or [])[-10:]:
        text = nachricht.get("content")
        if isinstance(text, str) and text.strip():
            rolle = "user" if nachricht.get("role") == "user" else "model"
            if inhalte and inhalte[-1]["role"] == rolle:
                inhalte[-1]["parts"][0]["text"] += "\n" + text
            else:
                inhalte.append({"role": rolle, "parts": [{"text": text}]})
    if inhalte and inhalte[-1]["role"] == "user":
        inhalte.pop()  # die aktuelle Frage kommt gleich noch einmal
    inhalte.append({"role": "user", "parts": [{"text": frage}]})
    while inhalte and inhalte[0]["role"] != "user":
        inhalte.pop(0)

    koerper = {"systemInstruction": {"parts": [{"text": systemtext}]},
               "contents": inhalte,
               "generationConfig": {"maxOutputTokens": config.GEMINI_MAX_TOKENS}}
    anfrage = urllib.request.Request(
        GEMINI_URL % config.GEMINI_MODELL, data=json.dumps(koerper).encode("utf-8"),
        method="POST", headers={"x-goog-api-key": config.GEMINI_API_KEY,
                                "content-type": "application/json"})
    try:
        with urllib.request.urlopen(anfrage, timeout=timeout) as antwort:
            daten = json.loads(antwort.read().decode("utf-8"))
    except urllib.error.HTTPError as fehler:
        return {"ok": False, "limit": fehler.code == 429,
                "fehler": "Gemini meldet Fehler %d." % fehler.code}
    except (urllib.error.URLError, OSError, ValueError) as fehler:
        return {"ok": False, "fehler": "Gemini nicht erreichbar: %s" % fehler}

    kandidaten = daten.get("candidates") or []
    teile = ((kandidaten[0].get("content") or {}).get("parts") or []) if kandidaten else []
    text = "".join(t.get("text", "") for t in teile).strip()
    if not text:
        return {"ok": False, "fehler": "Gemini hat nichts geantwortet."}
    nutzung = daten.get("usageMetadata") or {}
    return {"ok": True, "text": text,
            "tokens_ein": int(nutzung.get("promptTokenCount", 0)),
            "tokens_aus": int(nutzung.get("candidatesTokenCount", 0))}


def gemini_testen(schluessel: str) -> dict:
    """Prüft einen Gemini-Schlüssel mit einem echten Mini-Aufruf."""
    alt = config.GEMINI_API_KEY
    config.GEMINI_API_KEY = schluessel
    try:
        antwort = gemini_fragen("Sag nur: ok", "Antworte mit einem Wort.", timeout=30)
    finally:
        config.GEMINI_API_KEY = alt
    if antwort.get("ok"):
        return {"ok": True, "text": "Der Gemini-Schlüssel funktioniert."}
    fehler = antwort.get("fehler", "")
    if "400" in fehler or "403" in fehler:
        text = "Der Schlüssel wird abgelehnt. Bitte noch einmal vollständig kopieren."
    elif "404" in fehler:
        text = ("Das Modell %s kennt Google nicht (mehr). Trag in der Konfiguration "
                "ein anderes ein: GEMINI_MODELL." % config.GEMINI_MODELL)
    elif antwort.get("limit"):
        text = "Der Schlüssel stimmt, Google meldet aber gerade das Limit."
    else:
        text = fehler or "Die Prüfung ist fehlgeschlagen."
    return {"ok": False, "limit": bool(antwort.get("limit")), "text": text}


# -- Gedankenlog ------------------------------------------------------------

def claude_kosten(tokens_ein: int, tokens_aus: int) -> float:
    """Geschätzte Kosten einer Claude-Anfrage in Euro."""
    dollar = (tokens_ein * config.CLAUDE_PREIS_EIN
              + tokens_aus * config.CLAUDE_PREIS_AUS) / 1_000_000
    return round(dollar * config.DOLLAR_IN_EURO, 6)


class Gedankenlog:
    """Protokoll jeder Runde - und Quelle für Monatsverbrauch und Limit."""

    def __init__(self, datei=None):
        self.datei = datei or (config.LOG_VERZEICHNIS / LOG_DATEI_NAME)

    def eintragen(self, frage: str, gehirn: str, grund: str, dauer: float,
                  tokens_ein: int = 0, tokens_aus: int = 0, kosten: float = 0.0,
                  ausgewichen: bool = False) -> None:
        zeile = {"zeit": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                 "frage": (frage or "")[:120], "gehirn": gehirn, "grund": grund,
                 "dauer": round(dauer, 2), "tokens_ein": tokens_ein,
                 "tokens_aus": tokens_aus, "kosten": round(kosten, 6),
                 "ausgewichen": ausgewichen}
        try:
            self.datei.parent.mkdir(parents=True, exist_ok=True)
            with open(self.datei, "a", encoding="utf-8") as datei:
                datei.write(json.dumps(zeile, ensure_ascii=False) + "\n")
        except OSError as fehler:
            print("[gedankenlog] nicht schreibbar: %s" % fehler)

    def zeilen(self, monat: str = "") -> list:
        """Alle Einträge, auf Wunsch nur die eines Monats (``2026-10``)."""
        ergebnis = []
        try:
            with open(self.datei, encoding="utf-8") as datei:
                for rohzeile in datei:
                    try:
                        zeile = json.loads(rohzeile)
                    except ValueError:
                        continue
                    if not monat or str(zeile.get("zeit", "")).startswith(monat):
                        ergebnis.append(zeile)
        except OSError:
            pass
        return ergebnis

    def monatsbilanz(self, monat: str = "") -> dict:
        """Anfragen und Kosten je Gehirn im Monat (Standard: der laufende)."""
        monat = monat or datetime.now().strftime("%Y-%m")
        bilanz = {"monat": monat, "kosten": 0.0, "anfragen": 0,
                  "gemini": 0, "claude": 0, "ausgewichen": 0}
        for zeile in self.zeilen(monat):
            bilanz["anfragen"] += 1
            gehirn = zeile.get("gehirn")
            if gehirn in ("gemini", "claude"):
                bilanz[gehirn] += 1
            bilanz["kosten"] += float(zeile.get("kosten", 0) or 0)
            bilanz["ausgewichen"] += 1 if zeile.get("ausgewichen") else 0
        bilanz["kosten"] = round(bilanz["kosten"], 4)
        return bilanz

    def limit_erreicht(self) -> bool:
        """Hat Claude das Monatslimit aufgebraucht?"""
        if config.MONATSLIMIT_EURO <= 0:
            return False
        return self.monatsbilanz()["kosten"] >= config.MONATSLIMIT_EURO
