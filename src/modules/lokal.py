#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Lokales Modell - Jarvis denkt auf diesem Rechner statt bei Anthropic.

Kostet nichts, hat kein Limit und schickt nichts ins Netz. Dafür ist ein
kleines lokales Modell deutlich schwächer als Claude und auf einem älteren Mac
langsam. Gedacht als Weg ohne Schlüssel und ohne laufende Kosten.

Gesprochen wird mit Ollama (https://ollama.com), das auf dem Rechner läuft. Der
Rest von Jarvis spricht weiter das Format der Claude-Schnittstelle; dieses
Modul übersetzt hin und zurück, damit Schleifen und Werkzeuge unverändert
bleiben.

**Werkzeugauswahl.** Alle gut sechzig Werkzeuge mitzuschicken würde eine
Anfrage auf einem Intel-Mac um Minuten verlängern und kleine Modelle
verwirren. Deshalb gehen nur die Werkzeuge mit, die zur Frage passen, plus ein
kleiner Grundstock.
"""

import json
import re
import urllib.error
import urllib.request

import config
from modules.recall import schluesselwoerter

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
    return bool((config.LOKALES_MODELL or "").strip())


def _adresse(pfad: str) -> str:
    return config.OLLAMA_URL.rstrip("/") + pfad


def ollama_pruefen(modell: str = "") -> dict:
    """Läuft Ollama, und ist das Modell geladen? Sagt auf Deutsch, was fehlt."""
    modell = (modell or config.LOKALES_MODELL or STANDARD_MODELL).strip()
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


def _text_aus(inhalt) -> str:
    if isinstance(inhalt, str):
        return inhalt
    return "\n".join(b.get("text", "") for b in inhalt or []
                     if isinstance(b, dict) and b.get("type") == "text")


def nachrichten_umwandeln(system: str, nachrichten: list) -> list:
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
            eintrag = {"role": "assistant", "content": _text_aus(inhalt)}
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
                                     "content": _text_aus(block.get("content"))})
                elif block.get("type") == "image":
                    bilder.append((block.get("source") or {}).get("data", ""))
            text = _text_aus(inhalt)
            if text or bilder:
                eintrag = {"role": "user", "content": text}
                if bilder:
                    eintrag["images"] = [b for b in bilder if b]
                ergebnis.append(eintrag)
        else:
            ergebnis.append({"role": "user", "content": inhalt or ""})
    return ergebnis


def antwort_umwandeln(daten: dict) -> list:
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
            text = _text_aus(nachricht.get("content"))
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
        "model": config.LOKALES_MODELL,
        "messages": nachrichten_umwandeln(koerper.get("system", ""), nachrichten),
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
            bloecke = antwort_umwandeln(daten)
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
                        % (config.LOKALES_MODELL, config.LOKALES_MODELL)}
            return {"ok": False, "fehler": "Das lokale Modell meldet einen Fehler (%d): %s"
                    % (fehler.code, meldung[:300])}
        except (urllib.error.URLError, OSError):
            return {"ok": False, "fehler": "Ollama antwortet nicht. Ist die Ollama-App "
                    "geöffnet?"}
        except ValueError as fehler:
            return {"ok": False, "fehler": "Die Antwort war unlesbar: %s" % fehler}
    return {"ok": False, "fehler": "Das lokale Modell hat nicht geantwortet."}
