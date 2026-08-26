#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Kleiner MCP-Testserver - prüft die Freigabelogik wirklich.

Zwei Werkzeuge: ``liste_lesen`` steht in ``ohne_rueckfrage`` und muss
durchlaufen, ``datei_loeschen`` steht nicht darin und muss nachfragen.
"""
import json
import sys

WERKZEUGE = [
    {"name": "liste_lesen", "description": "Liest eine Liste. Harmlos.",
     "inputSchema": {"type": "object", "properties": {"was": {"type": "string"}}}},
    {"name": "datei_loeschen", "description": "Löscht etwas. Braucht Freigabe.",
     "inputSchema": {"type": "object", "properties": {"pfad": {"type": "string"}}}},
]


def antworten(kennung, ergebnis):
    sys.stdout.write(json.dumps({"jsonrpc": "2.0", "id": kennung, "result": ergebnis}) + "\n")
    sys.stdout.flush()


for zeile in sys.stdin:
    zeile = zeile.strip()
    if not zeile:
        continue
    try:
        nachricht = json.loads(zeile)
    except ValueError:
        continue
    methode, kennung = nachricht.get("method"), nachricht.get("id")
    if methode == "initialize":
        antworten(kennung, {"protocolVersion": "2024-11-05", "capabilities": {"tools": {}},
                            "serverInfo": {"name": "testserver", "version": "1.0"}})
    elif methode == "tools/list":
        antworten(kennung, {"tools": WERKZEUGE})
    elif methode == "tools/call":
        parameter = nachricht.get("params") or {}
        antworten(kennung, {"content": [{"type": "text", "text": "%s ausgeführt mit %s"
                                         % (parameter.get("name"),
                                            json.dumps(parameter.get("arguments") or {}))}]})
    elif kennung is not None:
        antworten(kennung, {})
