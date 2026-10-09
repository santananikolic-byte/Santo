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
import re
import time
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
    r"\b(merk|notier|notiz|speicher|leg\w* .{0,40}an\b|anlegen|trag\w* .{0,40}ein|eintragen|"
    r"schick|send|schreib|mail an|buch|erinner|start|erledig|hak|lösch|streich|"
    r"ruf\w* .{0,30}an\b|anrufen|vermerk|nimm .{0,30}auf|aufnehmen|erstell|halt\w* .{0,30}fest|"
    r"festhalten|füg|hinzu|öffne|plan|neue[rnm]? (lead|termin|punkt|kontakt|kunde|notiz)|"
    r"setz|stell .{0,30}ein|abschick)", re.IGNORECASE)
# "Ja", "mach", "ok" nach einer Rückfrage ("Soll ich den Termin eintragen?")
BESTAETIGUNG = re.compile(r"^\W*(ja|jo|jep|ok|okay|mach|bitte|gern|gerne|passt|los|klar)\b",
                          re.IGNORECASE)
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
    if isinstance(inhalt, list):  # mit Bild: nur der Text zählt, nicht das Bild
        inhalt = " ".join(t.get("text", "") for t in inhalt
                          if isinstance(t, dict) and t.get("type") == "text")
    inhalt = str(inhalt or "")
    if not (AUFTRAG.search(inhalt) or (len(inhalt.split()) <= 4
                                       and BESTAETIGUNG.search(inhalt))):
        return bloecke
    nachfrage = dict(nutzlast)
    nachfrage["messages"] = nutzlast["messages"] + [
        {"role": "assistant", "content": text},
        {"role": "user", "content": "Du hast dafür kein Werkzeug aufgerufen, also ist nichts "
                                    "passiert. Ruf jetzt das passende Werkzeug auf."}]
    zweite = _senden(config.FREIER_DIENST_URL, config.FREIER_DIENST_SCHLUESSEL,
                     nachfrage, timeout)
    if zweite["ok"]:
        neu = antwort_umwandeln(zweite["daten"])
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
        nutzlast["messages"].append({"role": "system", "content": WERKZEUG_PFLICHT})
        nutzlast["tools"] = [{"type": "function", "function": {
            "name": w["name"], "description": w.get("description", ""),
            "parameters": w.get("input_schema") or {"type": "object", "properties": {}}}}
            for w in gewaehlt]
    modelle = modelle_liste(config.FREIER_DIENST_MODELL)
    jetzt = time.monotonic()
    frei = [m for m in modelle if _PAUSE.get(m, 0) <= jetzt]
    letzte = {"ok": False, "fehler": "Der Dienst hat nicht geantwortet.", "code": 0}
    alle_voll = True
    for modell in frei or modelle:  # sind alle pausiert, trotzdem alle versuchen
        nutzlast["model"] = modell
        mit_werkzeugen = "tools" in nutzlast
        antwort = _senden(config.FREIER_DIENST_URL, config.FREIER_DIENST_SCHLUESSEL,
                          nutzlast, timeout)
        if not antwort["ok"] and antwort.get("code") == 400 and mit_werkzeugen:
            ohne = dict(nutzlast)
            ohne.pop("tools")  # Modell kann keine Werkzeuge: dann ohne
            antwort = _senden(config.FREIER_DIENST_URL, config.FREIER_DIENST_SCHLUESSEL,
                              ohne, timeout)
        if antwort["ok"]:
            _FEHLSCHLAEGE.pop(modell, None)
            bloecke = antwort_umwandeln(antwort["daten"]) or [{"type": "text", "text": ""}]
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
