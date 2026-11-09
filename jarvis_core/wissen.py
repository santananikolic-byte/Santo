# -*- coding: utf-8 -*-
"""Wissen - geprüfte Fakten mit Quelle und Stand, für die Fragen des Betriebs.

Jedes Paket ist eine Markdown-Datei in ``wissenspakete/``:

    # Titel
    stichworte: muster1, muster2, …     (Regex-Teile, klein geschrieben geprüft)
    rollen: vertrieb                    (optional: Rollen, die das Paket immer bekommen)
    stand: 2026-11-09                   (wann geprüft)
    pruefen_ab: 2027-01-01              (ab da können sich Zahlen geändert haben, z. B. neue Löhne)

    ## Abschnitte mit Punkten …
    ## Quellen
    [1] Herausgeber: Titel – https://…

Regel: Jede Zeile mit einem Betrag (€, Euro) oder einem Prozentsatz trägt einen Quellenverweis [n] - das prüfen die
Tests. Passt ein Paket zur Frage, steht es im Systemprompt; ist ``pruefen_ab`` erreicht, steht ein deutlicher Hinweis
dabei, und JARVIS nennt die Zahlen nur mit diesem Hinweis.
"""

import datetime
import os
import re
from collections import namedtuple

ORDNER = os.path.join(os.path.dirname(os.path.abspath(__file__)), "wissenspakete")
Paket = namedtuple("Paket", "name titel muster rollen stand pruefen_ab text quellen")

_KOPF = re.compile(r"^(stichworte|rollen|stand|pruefen_ab):\s*(.*)$")
_QUELLE = re.compile(r"^\[(\d+)\]\s+(.+?)\s+[–-]\s+(https://\S+)\s*$")
_VERWEIS = re.compile(r"\[(\d+)\]")
BETRAG = re.compile(r"\d[\d.,]*\s*(€|euro\b|prozent\b|%)", re.IGNORECASE)


class WissenFehler(ValueError):
    """Ein Wissenspaket ist fehlerhaft aufgebaut - der Text sagt, was."""


def _datum(text, feld, name):
    try:
        return datetime.date.fromisoformat(text.strip())
    except ValueError:
        raise WissenFehler("%s: %s bitte als JJJJ-MM-TT, nicht %r." % (name, feld, text)) from None


def lesen(pfad):
    """Ein Paket lesen. Wirft WissenFehler bei fehlenden Angaben."""
    name = os.path.splitext(os.path.basename(pfad))[0]
    with open(pfad, encoding="utf-8") as f:
        zeilen = f.read().split("\n")
    if not zeilen or not zeilen[0].startswith("# "):
        raise WissenFehler("%s: Die erste Zeile muss der Titel sein (# …)." % name)
    titel = zeilen[0][2:].strip()
    kopf, i = {}, 1
    while i < len(zeilen) and _KOPF.match(zeilen[i]):
        feld, wert = _KOPF.match(zeilen[i]).groups()
        kopf[feld] = wert.strip()
        i += 1
    for feld in ("stichworte", "stand", "pruefen_ab"):
        if not kopf.get(feld):
            raise WissenFehler("%s: Angabe %r fehlt." % (name, feld))
    teile = [t.strip() for t in kopf["stichworte"].split(",") if t.strip()]
    try:
        muster = re.compile("|".join(teile))
    except re.error as fehler:
        raise WissenFehler("%s: Stichworte sind kein gültiges Muster (%s)." % (name, fehler)) from None
    rest = "\n".join(zeilen[i:]).strip()
    if "\n## Quellen" not in "\n" + rest:
        raise WissenFehler("%s: Abschnitt '## Quellen' fehlt." % name)
    text, quellen_teil = ("\n" + rest).split("\n## Quellen", 1)
    quellen = {}
    for zeile in quellen_teil.strip().split("\n"):
        if not zeile.strip():
            continue
        treffer = _QUELLE.match(zeile.strip())
        if not treffer:
            raise WissenFehler("%s: Quelle nicht lesbar: %r (Form: [1] Titel – https://…)." % (name, zeile[:80]))
        quellen[int(treffer.group(1))] = (treffer.group(2), treffer.group(3))
    if not quellen:
        raise WissenFehler("%s: keine Quelle angegeben." % name)
    return Paket(name, titel, muster, tuple(r.strip() for r in kopf.get("rollen", "").split(",") if r.strip()),
                 _datum(kopf["stand"], "stand", name), _datum(kopf["pruefen_ab"], "pruefen_ab", name), text.strip(),
                 quellen)


def probleme(paket):
    """Was an einem Paket nicht stimmt: Beträge ohne Quelle, Verweise ins Leere, ungenutzte Quellen."""
    fehler, genutzt = [], set()
    for zeile in paket.text.split("\n"):
        verweise = {int(n) for n in _VERWEIS.findall(zeile)}
        genutzt |= verweise
        if BETRAG.search(zeile) and not verweise:
            fehler.append("Betrag ohne Quelle: %s" % zeile.strip()[:100])
        for n in sorted(verweise - set(paket.quellen)):
            fehler.append("Verweis [%d] ohne Quelle" % n)
    for n in sorted(set(paket.quellen) - genutzt):
        fehler.append("Quelle [%d] wird nirgends genutzt" % n)
    if paket.pruefen_ab <= paket.stand:
        fehler.append("pruefen_ab liegt nicht nach dem Stand")
    return fehler


_CACHE = {}


def pakete(ordner=None):
    """Alle Pakete (einmal gelesen, danach aus dem Zwischenspeicher)."""
    ordner = ordner or ORDNER
    if ordner not in _CACHE:
        namen = sorted(n for n in os.listdir(ordner) if n.endswith(".md")) if os.path.isdir(ordner) else []
        _CACHE[ordner] = [lesen(os.path.join(ordner, n)) for n in namen]
    return _CACHE[ordner]


def paket(name, ordner=None):
    return next((p for p in pakete(ordner) if p.name == name), None)


def waehlen(frage="", verlauf="", rolle="allgemein", ordner=None):
    """Welche Pakete passen? Feste Pakete der Rolle plus Stichworte in Frage und jüngstem Verlauf."""
    text = ("%s\n%s" % (frage or "", verlauf or "")).lower()
    return [p.name for p in pakete(ordner) if rolle in p.rollen or p.muster.search(text)]


def _de(datum):
    return datum.strftime("%d.%m.%Y")


def veraltet(p, heute=None):
    return (heute or datetime.date.today()) >= p.pruefen_ab


def prompt_text(p, heute=None):
    """Das Paket so, wie es im Systemprompt steht: Überschrift mit Stand, ggf. Warnhinweis, Inhalt, Quellen."""
    zeilen = ["WISSEN: %s (Stand %s - nenne Zahlen nur mit Quelle und Stand)" % (p.titel.upper(), _de(p.stand))]
    if veraltet(p, heute):
        zeilen.append("ACHTUNG: Dieses Wissen ist vom %s. Seit %s können sich Zahlen geändert haben (z. B. neue Löhne). "
                      "Sag das dazu, wenn du eine Zahl daraus nennst, und biete an, sie mit \"recherche\" zu prüfen."
                      % (_de(p.stand), _de(p.pruefen_ab)))
    zeilen.append(p.text)
    zeilen.append("Quellen: " + " ".join("[%d] %s (%s)" % (n, titel, url) for n, (titel, url) in sorted(p.quellen.items())))
    return "\n".join(zeilen)


def uebersicht(heute=None, ordner=None):
    """Eine Zeile je Paket - für das Werkzeug und den Selbsttest."""
    return ["%s: %s (Stand %s%s)" % (p.name, p.titel, _de(p.stand), ", bitte prüfen - Zahlen können veraltet sein"
                                     if veraltet(p, heute) else "") for p in pakete(ordner)]
