#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Ersatz für das Programm ``claude`` - nur für Tests, verbraucht kein Abo-Limit.

Gesteuert über Umgebungsvariablen:

    FAKE_DREHBUCH    JSON-Datei mit Regeln (siehe unten)
    FAKE_STAND       JSON-Datei, in der der Ersatz Aufrufzähler führt
    FAKE_PROTOKOLL   Datei, in die jeder Aufruf als JSON-Zeile geschrieben wird
    FAKE_AUTH        abo (Standard) | apikey | aus
    FAKE_UNBEKANNT   Kommagetrennte Optionen, die "unknown option" auslösen

Eine Regel im Drehbuch:

    {"stdin": "Text in der Eingabe", "system": "Text im Systemprompt", "nicht_stdin": "...",
     "modell": "opus", "tools": "WebSearch", "nr": 3, "max": 1,
     "antwort": "Text der Antwort", "modus": "limit|kaputt|langsam|fehler", "sekunden": 30}

Die erste passende Regel gewinnt. Ohne passende Regel antwortet der Ersatz mit "Antwort auf: <Eingabe>".
"""

import json
import os
import sys
import time


def _laden(pfad, standard):
    try:
        with open(pfad, "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError, TypeError):
        return standard


def _wert(args, name):
    return args[args.index(name) + 1] if name in args and args.index(name) + 1 < len(args) else ""


def main():
    args = sys.argv[1:]
    if args[:1] == ["--version"]:
        print("2.1.316 (Claude Code)")
        return 0
    if args[:2] == ["auth", "status"]:
        modus = os.environ.get("FAKE_AUTH", "abo")
        if modus == "aus":
            print(json.dumps({"loggedIn": False}))
            return 1
        print(json.dumps({"loggedIn": True, "authMethod": "api_key" if modus == "apikey" else "claude.ai",
                          "subscriptionType": "pro"}))
        return 0

    for flag in (os.environ.get("FAKE_UNBEKANNT") or "").split(","):
        if flag and flag in args:
            sys.stderr.write("error: unknown option '%s'\n" % flag)
            return 1

    eingabe = sys.stdin.read()
    system, modell, tools = _wert(args, "--system-prompt"), _wert(args, "--model"), _wert(args, "--tools")
    stand_datei = os.environ.get("FAKE_STAND")
    stand = _laden(stand_datei, {}) if stand_datei else {}
    stand["aufrufe"] = stand.get("aufrufe", 0) + 1
    nr = stand["aufrufe"]
    protokoll = os.environ.get("FAKE_PROTOKOLL")
    if protokoll:
        with open(protokoll, "a", encoding="utf-8") as f:
            f.write(json.dumps({"nr": nr, "args": args, "stdin": eingabe, "system": system, "modell": modell,
                                "tools": tools, "cwd": os.getcwd(), "apikey": os.environ.get("ANTHROPIC_API_KEY"),
                                "bedrock": os.environ.get("CLAUDE_CODE_USE_BEDROCK")}, ensure_ascii=False) + "\n")

    antwort, modus, sekunden = "Antwort auf: " + eingabe.strip()[-200:], None, 0
    drehbuch = _laden(os.environ.get("FAKE_DREHBUCH"), [])
    genutzt = stand.setdefault("regeln", {})
    for i, regel in enumerate(drehbuch):
        if "stdin" in regel and regel["stdin"] not in eingabe:
            continue
        if "nicht_stdin" in regel and regel["nicht_stdin"] in eingabe:
            continue
        if "system" in regel and regel["system"] not in system:
            continue
        if "modell" in regel and regel["modell"] != modell:
            continue
        if "tools" in regel and regel["tools"] not in tools:
            continue
        if "nr" in regel and regel["nr"] != nr:
            continue
        if "max" in regel and genutzt.get(str(i), 0) >= regel["max"]:
            continue
        genutzt[str(i)] = genutzt.get(str(i), 0) + 1
        antwort = regel.get("antwort", antwort)
        modus, sekunden = regel.get("modus"), regel.get("sekunden", 30)
        break
    if stand_datei:
        with open(stand_datei, "w", encoding="utf-8") as f:
            json.dump(stand, f)

    if modus == "limit":
        print(json.dumps({"type": "result", "is_error": True, "result": "Claude AI usage limit reached|1761930000"}))
        return 1
    if modus == "kaputt":
        print("das ist kein json")
        return 1
    if modus == "fehler":
        print(json.dumps({"type": "result", "is_error": True, "result": "Irgendetwas ist schiefgegangen"}))
        return 1
    if modus == "langsam":
        time.sleep(sekunden)
    print(json.dumps({"type": "result", "subtype": "success", "is_error": False, "session_id": "ersatz",
                      "result": antwort, "duration_ms": 10, "usage": {"input_tokens": 120, "output_tokens": 60}}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
