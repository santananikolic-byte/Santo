#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Kostenloser Online-Dienst - Jarvis denkt über einen Gratis-Zugang statt über Anthropic.

Mehrere Anbieter bieten ein kostenloses Kontingent an und sprechen dieselbe
"OpenAI-kompatible" Schnittstelle. Wer dort einen Schlüssel holt (ohne
Guthaben, ohne Karte), kann Jarvis damit betreiben.

**Was man wissen muss, bevor man das benutzt:**

* Gratis-Kontingente haben Grenzen pro Minute und pro Tag. Sind sie erreicht,
  muss man warten. Die Bedingungen ändern die Anbieter von sich aus.
* Das Gespräch geht an diesen Anbieter - samt allem, was Jarvis dafür aus Mails,
  Kunden oder Buchhaltung nachschlägt. Bei manchen Gratis-Tarifen dürfen
  Anbieter Eingaben auch zur Verbesserung ihrer Modelle nutzen. Wer das nicht
  will, nimmt das lokale Modell.
* Die Modellnamen wechseln. Deshalb lässt sich das Modell im Fenster ändern.

Wie beim lokalen Modell gehen nur die zur Frage passenden Werkzeuge mit - das
spart Kontingent, denn alle sechzig zu schicken kostet jedes Mal Tausende
Token.
"""

import json
import urllib.error
import urllib.request

import config
from modules.lokal import werkzeuge_auswaehlen

DIENST_VORGABEN = {
    "groq": {"name": "Groq", "url": "https://api.groq.com/openai/v1",
             "modell": "llama-3.3-70b-versatile",
             "seite": "console.groq.com/keys"},
    "gemini": {"name": "Google Gemini",
               "url": "https://generativelanguage.googleapis.com/v1beta/openai",
               "modell": "gemini-flash-latest",
               "seite": "aistudio.google.com/apikey"},
    "openrouter": {"name": "OpenRouter", "url": "https://openrouter.ai/api/v1",
                   "modell": "meta-llama/llama-3.3-70b-instruct:free",
                   "seite": "openrouter.ai/keys"},
}
DIENST_WERKZEUGE = 12


def freier_dienst_aktiv() -> bool:
    """Ist ein kostenloser Online-Dienst eingestellt?"""
    return bool(config.FREIER_DIENST_URL and config.FREIER_DIENST_SCHLUESSEL
                and config.FREIER_DIENST_MODELL)


def _text_aus(inhalt) -> str:
    if isinstance(inhalt, str):
        return inhalt
    return "\n".join(b.get("text", "") for b in inhalt or []
                     if isinstance(b, dict) and b.get("type") == "text")


def nachrichten_umwandeln(system: str, nachrichten: list) -> list:
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
            eintrag = {"role": "assistant", "content": _text_aus(inhalt) or None}
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
                                     "content": _text_aus(block.get("content"))
                                     if not isinstance(block.get("content"), str)
                                     else block.get("content")})
                elif block.get("type") == "image":
                    quelle = block.get("source") or {}
                    bilder.append("data:%s;base64,%s" % (quelle.get("media_type", "image/jpeg"),
                                                         quelle.get("data", "")))
            text = _text_aus(inhalt)
            if bilder:
                teile = [{"type": "text", "text": text or "Was siehst du?"}]
                teile += [{"type": "image_url", "image_url": {"url": b}} for b in bilder]
                ergebnis.append({"role": "user", "content": teile})
            elif text:
                ergebnis.append({"role": "user", "content": text})
        else:
            ergebnis.append({"role": "user", "content": inhalt or ""})
    return ergebnis


def antwort_umwandeln(daten: dict) -> list:
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
    """Probelauf mit einem winzigen Auftrag."""
    antwort = _senden(url, schluessel, {
        "model": modell, "max_tokens": 8,
        "messages": [{"role": "user", "content": "Sag nur: ok"}]}, 60)
    if antwort["ok"]:
        return {"ok": True, "text": "Der Dienst antwortet. Jarvis nutzt ihn."}
    return {"ok": False, "text": antwort["fehler"]}


def freier_dienst_anfragen(koerper: dict, timeout: int = 120) -> dict:
    """Beantwortet eine Anfrage im Claude-Format über den kostenlosen Dienst."""
    nachrichten = koerper.get("messages") or []
    katalog = koerper.get("tools") or []
    letzte = ""
    for nachricht in reversed(nachrichten):
        if nachricht.get("role") == "user" and _text_aus(nachricht.get("content")):
            letzte = _text_aus(nachricht.get("content"))
            break
    benutzt = tuple(b.get("name", "") for n in nachrichten
                    if isinstance(n.get("content"), list) for b in n["content"]
                    if isinstance(b, dict) and b.get("type") == "tool_use")
    gewaehlt = werkzeuge_auswaehlen(katalog, letzte, DIENST_WERKZEUGE, benutzt) \
        if katalog else []
    nutzlast = {
        "model": config.FREIER_DIENST_MODELL,
        "messages": nachrichten_umwandeln(koerper.get("system", ""), nachrichten),
        # Denkende Modelle verbrauchen einen Teil davon für Gedanken - zu wenig
        # Platz ergibt eine leere Antwort.
        "max_tokens": max(int(koerper.get("max_tokens") or 1000), 4096),
        "temperature": 0.3,
    }
    if gewaehlt:
        nutzlast["tools"] = [{"type": "function", "function": {
            "name": w["name"], "description": w.get("description", ""),
            "parameters": w.get("input_schema") or {"type": "object", "properties": {}}}}
            for w in gewaehlt]
    antwort = _senden(config.FREIER_DIENST_URL, config.FREIER_DIENST_SCHLUESSEL,
                      nutzlast, timeout)
    if not antwort["ok"] and antwort.get("code") == 400 and "tools" in nutzlast:
        nutzlast.pop("tools")  # Modell kann keine Werkzeuge: dann ohne
        antwort = _senden(config.FREIER_DIENST_URL, config.FREIER_DIENST_SCHLUESSEL,
                          nutzlast, timeout)
    if not antwort["ok"]:
        return {"ok": False, "fehler": antwort["fehler"]}
    bloecke = antwort_umwandeln(antwort["daten"]) or [{"type": "text", "text": ""}]
    return {"ok": True, "daten": {"content": bloecke}}
