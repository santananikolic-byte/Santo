# -*- coding: utf-8 -*-
"""Protokoll: Fehler und kritische Aktionen nachvollziehbar speichern – ohne Geheimnisse."""

import json
import re

from .db import jetzt

_GEHEIM = [
    re.compile(r"(?i)(passwort|password|passwd|token|api[_-]?key|secret|geheim|seed|private[_ -]?key)"
               r"(\s*[:=]\s*|\"\s*:\s*\")([^\s\",}]+)"),
    re.compile(r"\bsk-[A-Za-z0-9_\-]{10,}"),
    re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,}"),
    re.compile(r"\b(?:[a-z]+\s){11,23}[a-z]+\b"),  # mögliche Seed-Phrase (12–24 Wörter klein)
    re.compile(r"\b[A-Z]{2}\d{2}(?:\s?[A-Z0-9]{4}){3,7}\b"),  # IBAN
]


def schwaerzen(text):
    if text is None:
        return None
    text = str(text)
    text = _GEHEIM[0].sub(lambda m: m.group(1) + m.group(2) + "***", text)
    for muster in _GEHEIM[1:]:
        if muster.pattern.startswith(r"\b(?:[a-z]+\s)"):
            continue  # Seed-Erkennung nur für ausdrückliche Prüfung, sonst zu viele Fehltreffer
        text = muster.sub("***", text)
    return text


def sieht_nach_geheimnis_aus(text):
    text = str(text or "")
    return any(m.search(text) for m in _GEHEIM[:3]) or bool(re.search(
        r"(?i)\b(seed|mnemonic|wiederherstellungs?phrase)\b", text))


class Protokoll:
    def __init__(self, db):
        self.db = db

    def schreibe(self, ebene, quelle, ereignis, details=None):
        if details is not None and not isinstance(details, str):
            details = json.dumps(details, ensure_ascii=False, default=str)
        self.db.ausfuehren(
            "INSERT INTO protokoll (zeit, ebene, quelle, ereignis, details) VALUES (?,?,?,?,?)",
            (jetzt(), ebene, quelle, schwaerzen(ereignis)[:500], schwaerzen(details)[:4000] if details else None))

    def info(self, quelle, ereignis, details=None):
        self.schreibe("info", quelle, ereignis, details)

    def warnung(self, quelle, ereignis, details=None):
        self.schreibe("warnung", quelle, ereignis, details)

    def fehler(self, quelle, ereignis, details=None):
        self.schreibe("fehler", quelle, ereignis, details)

    def audit(self, quelle, ereignis, details=None):
        self.schreibe("audit", quelle, ereignis, details)

    def liste(self, ebene=None, grenze=200):
        if ebene:
            return self.db.alle("SELECT * FROM protokoll WHERE ebene=? ORDER BY id DESC LIMIT ?",
                                (ebene, grenze))
        return self.db.alle("SELECT * FROM protokoll ORDER BY id DESC LIMIT ?", (grenze,))
