# -*- coding: utf-8 -*-
"""Gedächtnis - was JARVIS vor einer Antwort aus dem Speicher holt.

Zwei Regeln stehen im Mittelpunkt:

1. **Bereiche bleiben getrennt.** Ein Gespräch gehört zu genau einem Bereich
   (zum Beispiel ``geschaeft`` oder ``privat``). Ins Modell gelangen nur Einträge
   dieses Bereichs plus ``allgemein`` (Regeln, Vorlieben) und ``technik``. Das
   ist im Code erzwungen, nicht nur im Prompt versprochen.
2. **Relevantes zuerst.** Ist das Gedächtnis klein, kommt alles mit. Wird es
   größer, kommen Regeln, als wichtig markierte Einträge und die zur Frage
   passendsten (siehe ``textsuche.py``).

Dazu der **Fokus**: was jetzt ansteht (fällige Aufgaben, laufende Aufträge,
wartende Freigaben, Erinnerungen) - für das Modell und für die Oberfläche.
"""

import os
import re

from . import textsuche, zeit

KERN_ARTEN = ("regel", "praeferenz")
VOLLSTAENDIG_BIS = 24
MAX_KONTEXT = 16

# Zuordnung der Einträge aus BRAIN.md (Kürzel -> Bereich). Alles andere gehört zum ersten Bereich (Geschäft).
PRIVAT = {"C5", "C6", "C8", "P6", "D1"}
ALLGEMEIN = {"C9", "C15", "C16", "C17", "C18"}
TECHNIK = {"P10", "P11", "P12", "P13", "P14"}
WICHTIG = {"C1", "C2", "C3", "C4", "C13", "C14"}


def bereich_pruefen(konfig, bereich):
    """Gibt einen gültigen Bereich zurück (unbekannt -> der erste konfigurierte)."""
    return bereich if bereich in konfig.bereiche else konfig.bereiche[0]


# ------------------------------------------------------------------ Suche ---

def kontext_fakten(speicher, bereich, frage="", limit=MAX_KONTEXT):
    """Bestätigte Einträge für ``bereich`` (plus allgemein/technik), nach Relevanz zur ``frage`` gewählt."""
    kandidaten = speicher.fakten(status="bestaetigt", bereiche=[bereich, "allgemein", "technik"])
    if len(kandidaten) <= VOLLSTAENDIG_BIS:
        return kandidaten
    fest = [f for f in kandidaten if f["art"] in KERN_ARTEN or f["wichtig"]]
    rest = [f for f in kandidaten if f not in fest]
    suchwoerter = set(textsuche.woerter(frage))
    bewertet = sorted(((textsuche.relevanz(suchwoerter, f["text"]), f["id"], f) for f in rest), key=lambda t: (-t[0], t[1]))
    platz = max(0, limit - len(fest))
    treffer = [f for punkte, _, f in bewertet[:platz] if punkte > 0]
    return fest + treffer


def suchen(speicher, bereich, frage, limit=10):
    """Für die Oberfläche: Treffer mit Bewertung, nur aus dem gewählten Bereich."""
    suchwoerter = set(textsuche.woerter(frage))
    zeilen = speicher.fakten(status=["bestaetigt", "vorschlag"], bereiche=[bereich, "allgemein", "technik"])
    bewertet = sorted(((textsuche.relevanz(suchwoerter, f["text"]), f) for f in zeilen), key=lambda t: -t[0])
    return [dict(f, punkte=round(p, 3)) for p, f in bewertet[:limit] if p > 0]


# ------------------------------------------------------------------ Fokus ---

def fokus(speicher, bereich, jetzt=None):
    """Was jetzt ansteht - sortiert nach Dringlichkeit und Wichtigkeit."""
    jetzt = jetzt or zeit.jetzt()
    todos = [t for t in speicher.todos(bereich=bereich, status="offen")]

    def rang(t):
        ueberfaellig = 0 if (t["faellig"] and t["faellig"] < jetzt) else 1
        prio = {"hoch": 0, "normal": 1}.get(t["prioritaet"], 2)
        return (ueberfaellig, prio, t["faellig"] or "9999", t["id"])

    todos.sort(key=rang)
    auftraege = speicher.auftraege(bereich=bereich, stati=("laeuft", "wartend", "wartet_auf_freigabe", "unterbrochen",
                                                          "pausiert", "geplant", "entwurf", "rueckfrage"), limit=10)
    freigaben = [f for f in speicher.freigaben("offen") if f["bereich"] == bereich]
    erinnerungen = speicher.erinnerungen(bereich=bereich)[:6]
    return {"todos": todos[:8], "auftraege": auftraege[:6], "freigaben": freigaben[:6], "erinnerungen": erinnerungen}


def kontext_text(speicher, konfig, bereich, frage=""):
    """Der Kontextblock, der jeder Modellanfrage vorangestellt wird."""
    bereich = bereich_pruefen(konfig, bereich)
    zeilen = ["[HEUTE] %s (Ortszeit)" % zeit.utc_zu_lokal_text(zeit.jetzt()),
              "[BEREICH] %s. Du siehst in diesem Gespräch nur Daten dieses Bereichs und allgemeine Regeln. "
              "Daten der anderen Bereiche kennst du hier nicht und darfst sie nicht erraten." % bereich]
    fakten = kontext_fakten(speicher, bereich, frage)
    if fakten:
        zeilen.append("[BESTÄTIGTES WISSEN]")
        zeilen += ["- (%s) %s" % (f["art"], f["text"]) for f in fakten]
    else:
        zeilen.append("[BESTÄTIGTES WISSEN] noch nichts gespeichert")
    f = fokus(speicher, bereich)
    if f["todos"]:
        zeilen.append("[OFFENE AUFGABEN DES NUTZERS]")
        for t in f["todos"]:
            faellig = " fällig %s" % zeit.utc_zu_lokal_text(t["faellig"]) if t["faellig"] else ""
            zeilen.append("- #%d [%s] %s%s" % (t["id"], t["prioritaet"], t["titel"], faellig))
    if f["auftraege"]:
        zeilen.append("[AUFTRÄGE AN JARVIS]")
        zeilen += ["- #%d %s (%s)" % (a["id"], a["titel"], a["status"]) for a in f["auftraege"]]
    if f["freigaben"]:
        zeilen.append("[WARTENDE FREIGABEN]")
        zeilen += ["- #%d %s" % (x["id"], x["werkzeug"]) for x in f["freigaben"]]
    if f["erinnerungen"]:
        zeilen.append("[ERINNERUNGEN]")
        zeilen += ["- %s: %s" % (zeit.utc_zu_lokal_text(e["faellig"]), e["text"]) for e in f["erinnerungen"]]
    return "\n".join(zeilen)


# ----------------------------------------------------------------- Import ---

def _sauber(text):
    text = text.replace("\\|", "|").replace("**", "").replace("`", "")
    return " ".join(text.split())


def _abschnitte(text):
    abschnitte, name = {}, None
    for zeile in text.splitlines():
        if zeile.startswith("## "):
            name = zeile[3:].strip().upper()
            abschnitte[name] = []
        elif name:
            abschnitte[name].append(zeile)
    return abschnitte


def _punkte(zeilen):
    punkte, aktuell = [], None
    for z in zeilen:
        if z.startswith("- "):
            if aktuell is not None:
                punkte.append(aktuell)
            aktuell = z[2:].strip()
        elif z.startswith("  ") and aktuell is not None and z.strip():
            aktuell += " " + z.strip()
        elif aktuell is not None:
            punkte.append(aktuell)
            aktuell = None
    if aktuell is not None:
        punkte.append(aktuell)
    return punkte


def _tabellenzeilen(zeilen):
    for z in zeilen:
        if not z.startswith("|"):
            continue
        geschuetzt = z.replace("\\|", "\u0001")
        zellen = [c.strip().replace("\u0001", "|") for c in geschuetzt.strip().strip("|").split("|")]
        if not zellen or zellen[0] in ("#", "") or set(zellen[0]) <= set("-: "):
            continue
        yield zellen


def _abschnitt(abschnitte, anfang):
    for name, zeilen in abschnitte.items():
        if name.startswith(anfang):
            return zeilen
    return []


def profil_parsen(text):
    """Liest BRAIN.md und gibt Einträge zurück: [{kuerzel, art, bereich, wichtig, text}]."""
    teile = _abschnitte(text)
    eintraege = []

    def neu(kuerzel, art, inhalt, standard_bereich="geschaeft", wichtig=False):
        if kuerzel in PRIVAT:
            bereich = "privat"
        elif kuerzel in TECHNIK:
            bereich = "technik"
        elif kuerzel in ALLGEMEIN:
            bereich = "allgemein"
        else:
            bereich = standard_bereich
        eintraege.append({"kuerzel": kuerzel, "art": art, "bereich": bereich,
                          "wichtig": wichtig or kuerzel in WICHTIG, "text": _sauber(inhalt)})

    for punkt in _punkte(_abschnitt(teile, "CORE PROFILE")):
        m = re.match(r"^\*\*(C\d+)\*\*\s+(.*)$", punkt)
        if m:
            neu(m.group(1), "praeferenz" if m.group(1) in ALLGEMEIN else "profil", m.group(2))
    for zellen in _tabellenzeilen(_abschnitt(teile, "PROJECT BRAIN")):
        if len(zellen) >= 3 and re.match(r"^P\d+$", zellen[0]):
            neu(zellen[0], "projekt", "%s: %s" % (_sauber(zellen[1]), zellen[2]))
    for zellen in _tabellenzeilen(_abschnitt(teile, "DECISION LOG")):
        if len(zellen) >= 3 and re.match(r"^D\d+$", zellen[0]):
            neu(zellen[0], "entscheidung", "%s (festgelegt am %s)" % (zellen[2], zellen[1]))
    for punkt in _punkte(_abschnitt(teile, "RULES")):
        neu("R", "regel", punkt, standard_bereich="allgemein", wichtig=True)
    for punkt in _punkte(_abschnitt(teile, "LEARNINGS")):
        neu("L", "praeferenz", punkt, standard_bereich="allgemein")
    for punkt in _punkte(_abschnitt(teile, "NACHTR")):
        neu("N", "fakt", "Noch offen: " + punkt)
    return eintraege


def profil_importieren(speicher, konfig, pfad, ersetzen=True):
    """Übernimmt BRAIN.md als bestätigtes Wissen. Vom Nutzer bearbeitete Einträge bleiben unangetastet."""
    try:
        with open(pfad, "r", encoding="utf-8") as f:
            text = f.read()
    except OSError as fehler:
        return {"ok": False, "fehler": "BRAIN.md nicht lesbar: %s" % fehler}
    eintraege = profil_parsen(text)
    if ersetzen:
        speicher.fakten_loeschen_quelle("BRAIN.md")
    erlaubt = set(konfig.alle_bereiche())
    neu = 0
    for e in eintraege:
        bereich = e["bereich"] if e["bereich"] in erlaubt else konfig.bereiche[0]
        _, ist_neu = speicher.fakt_hinzufuegen(e["text"], bereich=bereich, art=e["art"], quelle="BRAIN.md",
                                               wichtig=e["wichtig"])
        neu += 1 if ist_neu else 0
    speicher.meta_setzen("profil_importiert", zeit.jetzt())
    return {"ok": True, "gefunden": len(eintraege), "neu": neu, "datei": os.path.basename(pfad)}
