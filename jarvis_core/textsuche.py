# -*- coding: utf-8 -*-
"""Textsuche ohne Zusatzpakete - Relevanz und Duplikaterkennung für das Gedächtnis.

Die Wörter werden klein geschrieben, Füllwörter fallen weg, und jedes Wort wird
auf seine ersten sechs Buchstaben gekürzt ("Geschäft", "geschäftlich" und
"Geschäfte" treffen sich so). Das reicht für ein persönliches Gedächtnis mit
einigen hundert Einträgen und braucht weder Datenbankerweiterung noch Internet.
"""

import math
import re

FUELLWOERTER = frozenset("""
der die das den dem des ein eine einen einem einer eines und oder aber auch als bei aus nach von vom zum zur
mit für auf im in an am ist sind war waren wird werden wurde hat haben hatte habe hast kann soll muss will
nicht noch nur sehr wie was wer wo wann warum dass wenn dann doch schon mal mein meine meinen meiner meinem
mir mich dich dir uns euch ihm ihn ihr sie wir ich du er es man dieser diese dieses jede jeder jedes
""".split())

_WORT = re.compile(r"[a-zäöüß0-9]{3,}")
_TEXT = re.compile(r"[a-zäöüß0-9]+")
GRENZE_DUPLIKAT = 0.85


def woerter(text):
    return [w[:6] for w in _WORT.findall((text or "").lower()) if w not in FUELLWOERTER]


def normalisiert(text):
    return " ".join(_TEXT.findall((text or "").lower()))


def aehnlichkeit(a, b):
    """0.0 bis 1.0 - wie viele (gekürzte) Wörter beide Texte teilen."""
    if normalisiert(a) == normalisiert(b):
        return 1.0
    wa, wb = set(woerter(a)), set(woerter(b))
    if not wa or not wb:
        return 0.0
    return len(wa & wb) / len(wa | wb)


def ist_duplikat(a, b):
    return aehnlichkeit(a, b) >= GRENZE_DUPLIKAT


def relevanz(frage_woerter, text):
    """Wie gut passt ``text`` zur Frage? 0.0 = gar nicht. ``frage_woerter`` ist ein set aus ``woerter()``."""
    wt = set(woerter(text))
    if not wt or not frage_woerter:
        return 0.0
    gemeinsam = len(frage_woerter & wt)
    return gemeinsam / math.sqrt(len(wt)) if gemeinsam else 0.0
