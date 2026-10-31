# -*- coding: utf-8 -*-
"""Kleine Hilfe: das erste JSON-Objekt aus einer Modellantwort holen (auch mit Text drumherum)."""

import json


def json_finden(text):
    """Gibt das erste gültige JSON-Objekt (dict) im Text zurück, sonst None."""
    decoder = json.JSONDecoder()
    text = text or ""
    for i, zeichen in enumerate(text):
        if zeichen == "{":
            try:
                objekt, _ = decoder.raw_decode(text[i:])
            except ValueError:
                continue
            if isinstance(objekt, dict):
                return objekt
    return None
