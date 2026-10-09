#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Claude Code als Gehirn - Jarvis denkt über das Abo statt über einen API-Schlüssel.

Wer Claude Code auf dem Rechner hat und mit seinem Abo angemeldet ist, braucht
keinen Schlüssel und kein Guthaben: Jarvis ruft das Programm ``claude`` im
Druckmodus (``claude -p``) auf, so wie es für Skripte gedacht ist.

**Was das nicht ist:** unbegrenzt. Die Nutzung läuft über die Grenzen des Abos,
und eine Anfrage dauert länger als über die Schnittstelle, weil jedes Mal ein
Programm startet.

**Wichtig:** ``ANTHROPIC_API_KEY`` wird dem Programm nie mitgegeben. Sonst würde
es über den Schlüssel abrechnen statt über das Abo.

Claude Code kennt die Werkzeuge von Jarvis nicht. Deshalb steht die Liste im
Auftrag, und die Antwort kommt als JSON: entweder ein Werkzeugaufruf oder die
fertige Antwort. Dieses Modul übersetzt das ins Format der Claude-Schnittstelle,
damit die Denkschleife unverändert bleibt.
"""

import json
import os
import shutil
import subprocess
import tempfile

import config

SUCHPFADE = (
    "~/.local/bin/claude", "~/.claude/local/claude", "~/.npm-global/bin/claude",
    "/usr/local/bin/claude", "/opt/homebrew/bin/claude",
)
MAX_NACHRICHTEN = 30
MAX_ZEICHEN = 3000


def claude_code_finden() -> str:
    """Pfad zum Programm ``claude`` oder ein leerer Text."""
    gefunden = shutil.which("claude")
    if gefunden:
        return gefunden
    for pfad in SUCHPFADE:
        pfad = os.path.expanduser(pfad)
        if os.path.isfile(pfad) and os.access(pfad, os.X_OK):
            return pfad
    return ""


def claude_code_aktiv() -> bool:
    """Ist Claude Code als Gehirn eingeschaltet?"""
    return bool(config.CLAUDE_CODE_NUTZEN)


def _umgebung() -> dict:
    umgebung = dict(os.environ)
    umgebung.pop("ANTHROPIC_API_KEY", None)  # sonst zählt der Schlüssel statt des Abos
    umgebung.pop("ANTHROPIC_AUTH_TOKEN", None)
    return umgebung


def _ausfuehren(auftrag: str, timeout: int) -> dict:
    """Startet ``claude -p`` und gibt den Antworttext zurück."""
    programm = claude_code_finden()
    if not programm:
        return {"ok": False, "grund": "fehlt",
                "text": "Claude Code ist auf diesem Rechner nicht installiert. "
                        "Anleitung: docs.claude.com/de/docs/claude-code"}
    befehl = [programm, "-p", "--output-format", "json"]
    if config.CLAUDE_CODE_MODELL:
        befehl += ["--model", config.CLAUDE_CODE_MODELL]
    arbeitsordner = tempfile.mkdtemp(prefix="jarvis_cc_")  # leer: nichts zum Lesen
    try:
        lauf = subprocess.run(befehl, input=auftrag, capture_output=True, text=True,
                              timeout=timeout, cwd=arbeitsordner, env=_umgebung())
    except subprocess.TimeoutExpired:
        return {"ok": False, "grund": "zeit",
                "text": "Claude Code hat nicht rechtzeitig geantwortet."}
    except OSError as fehler:
        return {"ok": False, "grund": "start",
                "text": "Claude Code ließ sich nicht starten: %s" % fehler}
    finally:
        shutil.rmtree(arbeitsordner, ignore_errors=True)

    roh = (lauf.stdout or "").strip()
    text, fehlerhaft = roh, lauf.returncode != 0
    try:
        daten = json.loads(roh)
        if isinstance(daten, dict):
            text = str(daten.get("result", "") or "")
            fehlerhaft = fehlerhaft or bool(daten.get("is_error"))
    except ValueError:
        pass
    if fehlerhaft or not text.strip():
        meldung = (text or lauf.stderr or "").strip()
        klein = meldung.lower()
        if "limit" in klein or "usage" in klein:
            return {"ok": False, "grund": "limit",
                    "text": "Das Nutzungslimit deines Abos ist erreicht. Es setzt sich "
                            "nach einiger Zeit zurück. " + meldung[:200]}
        if any(w in klein for w in ("login", "log in", "authenticat", "api key", "oauth")):
            return {"ok": False, "grund": "anmeldung",
                    "text": "Claude Code ist nicht angemeldet. Gib im Terminal "
                            "claude ein und melde dich mit deinem Abo an."}
        return {"ok": False, "grund": "fehler",
                "text": "Claude Code meldet einen Fehler: %s" % (meldung[:300] or "keine Antwort")}
    return {"ok": True, "text": text.strip()}


def claude_code_pruefen() -> dict:
    """Ist Claude Code da und angemeldet? Ein winziger Probelauf zeigt es."""
    if not claude_code_finden():
        return _ausfuehren("", 5)
    probe = _ausfuehren("Antworte nur mit dem Wort: ok", 120)
    if probe["ok"]:
        return {"ok": True, "text": "Claude Code ist bereit. Jarvis nutzt dein Abo."}
    return probe


def _kurz(werkzeug: dict) -> str:
    schema = werkzeug.get("input_schema") or {}
    pflicht = set(schema.get("required") or [])
    teile = []
    for name, beschr in (schema.get("properties") or {}).items():
        art = beschr.get("type", "text") if isinstance(beschr, dict) else "text"
        teile.append("%s%s:%s" % (name, "*" if name in pflicht else "", art))
    erster_satz = (werkzeug.get("description", "") or "").split(". ")[0][:140]
    return "- %s(%s): %s" % (werkzeug.get("name", ""), ", ".join(teile), erster_satz)


def _abschnitt(text) -> str:
    if isinstance(text, str):
        return text[:MAX_ZEICHEN]
    return json.dumps(text, ensure_ascii=False, default=str)[:MAX_ZEICHEN]


def verlauf_als_text(nachrichten: list) -> str:
    """Das bisherige Gespräch als lesbarer Text."""
    namen, zeilen = {}, []
    for nachricht in nachrichten[-MAX_NACHRICHTEN:]:
        rolle, inhalt = nachricht.get("role"), nachricht.get("content")
        if isinstance(inhalt, str):
            zeilen.append("%s: %s" % ("Nutzer" if rolle == "user" else "Jarvis",
                                      _abschnitt(inhalt)))
            continue
        for block in inhalt or []:
            if not isinstance(block, dict):
                continue
            art = block.get("type")
            if art == "text":
                zeilen.append("%s: %s" % ("Nutzer" if rolle == "user" else "Jarvis",
                                          _abschnitt(block.get("text", ""))))
            elif art == "tool_use":
                namen[block.get("id")] = block.get("name", "")
                zeilen.append("Jarvis ruft auf: %s %s" % (
                    block.get("name", ""),
                    json.dumps(block.get("input") or {}, ensure_ascii=False)))
            elif art == "tool_result":
                zeilen.append("Ergebnis von %s: %s" % (
                    namen.get(block.get("tool_use_id"), "Werkzeug"),
                    _abschnitt(block.get("content", ""))))
    return "\n".join(zeilen)


def auftrag_bauen(koerper: dict) -> str:
    """Setzt Systemtext, Werkzeugliste und Gespräch zu einem Auftrag zusammen."""
    werkzeuge = "\n".join(_kurz(w) for w in koerper.get("tools") or [])
    regeln = (
        "Du bist kein Programmier-Assistent und benutzt keine eigenen Werkzeuge. "
        "Du bist Jarvis. Antworte mit GENAU EINEM JSON-Objekt, ohne Text davor oder "
        "danach und ohne Codeblock:\n"
        '  Werkzeug aufrufen:  {"werkzeug": "name", "argumente": {"param": wert}}\n'
        '  Mehrere nacheinander: {"aufrufe": [{"werkzeug": "...", "argumente": {...}}]}\n'
        '  Fertig antworten:   {"antwort": "gesprochener Text"}\n'
        "Ein * hinter dem Parameter heißt: Pflicht. Erfinde keine Werkzeuge und keine "
        "Ergebnisse. Ist ein Ergebnis da, antworte damit.")
    teile = [koerper.get("system", ""), regeln]
    if werkzeuge:
        teile.append("Werkzeuge:\n" + werkzeuge)
    teile.append("Gespräch bisher:\n" + verlauf_als_text(koerper.get("messages") or []))
    teile.append("Deine Antwort als JSON:")
    return "\n\n".join(t for t in teile if t)


def _json_aus(text: str):
    anfang, ende = text.find("{"), text.rfind("}")
    if anfang < 0 or ende <= anfang:
        return None
    try:
        daten = json.loads(text[anfang:ende + 1])
    except ValueError:
        return None
    return daten if isinstance(daten, dict) else None


def antwort_umwandeln(text: str) -> list:
    """Die Antwort von Claude Code als Inhaltsblöcke im Claude-Format."""
    daten = _json_aus(text)
    if daten is None:  # kein JSON: dann ist es einfach die Antwort
        return [{"type": "text", "text": text.strip()}]
    aufrufe = daten.get("aufrufe")
    if not isinstance(aufrufe, list):
        aufrufe = [daten] if daten.get("werkzeug") else []
    bloecke = []
    for nr, aufruf in enumerate(aufrufe):
        if not isinstance(aufruf, dict) or not aufruf.get("werkzeug"):
            continue
        argumente = aufruf.get("argumente")
        bloecke.append({"type": "tool_use", "id": "cc_%d_%d" % (id(aufruf) % 100000, nr),
                        "name": str(aufruf["werkzeug"]),
                        "input": argumente if isinstance(argumente, dict) else {}})
    if bloecke:
        return bloecke
    antwort = daten.get("antwort")
    return [{"type": "text", "text": str(antwort if antwort is not None else text).strip()}]


def claude_code_anfragen(koerper: dict, timeout: int = 300) -> dict:
    """Beantwortet eine Anfrage im Claude-Format über das Abo."""
    lauf = _ausfuehren(auftrag_bauen(koerper), timeout)
    if not lauf["ok"]:
        return {"ok": False, "fehler": lauf["text"]}
    return {"ok": True, "daten": {"content": antwort_umwandeln(lauf["text"])}}
