# -*- coding: utf-8 -*-
"""Agenten - die Organisation hinter JARVIS: Abteilungen mit Fachleuten.

Ein Agent ist eine Rolle für dasselbe Gehirn (Claude): eigener Auftrag, eigene Werkzeuge, eigenes Wissen, eigene
Prüfregeln. Zwei Arten, wie JARVIS sie einsetzt:

* **Beratung im Gespräch** (kostet nichts extra): Passen Fachleute zur Frage, stehen ihr Auftrag, ihre Prüfregeln und ihre
  Erfahrungen im Systemprompt. JARVIS antwortet mit ihrem Fachwissen und prüft die Antwort gegen ihre Regeln.
* **Einsatz in einem Auftrag**: Jeder Schritt läuft als eigener Agent - eigener Modellaufruf, nur seine Werkzeuge -, danach
  prüft der unabhängige Prüfer. Kritik des Prüfers wird zur Erfahrung des Agenten (siehe Speicher "erfahrungen").

Katalog: ``agenten/*.md``, eine Datei je Abteilung::

    # Titel der Abteilung
    kurz: ein Satz
    leitung: id

    ## id: Name
    zweck: ein Satz (für Übersicht und Planer)
    stichworte: muster, muster, …        (Regex-Teile, klein geschrieben geprüft)
    werkzeuge: lesen, schreiben, …       (Gruppen aus GRUPPEN oder Werkzeugnamen)
    wissen: kalkulation, …               (optional: Wissenspakete)
    auftrag: …
    pruefen: Punkt; Punkt; Punkt

Eigene Agenten legt JARVIS nur nach dem Ja des Nutzers an; sie liegen in ``<daten>/agenten_eigene.json`` und bekommen
nie mehr Rechte als die Gruppen in EIGENE_GRUPPEN (nichts löschen, nichts senden).
"""

import json
import os
import re
from collections import namedtuple

ORDNER = os.path.join(os.path.dirname(os.path.abspath(__file__)), "agenten")
EIGENE_DATEI = "agenten_eigene.json"
MAX_EIGENE = 400

GRUPPEN = {
    "lesen": ("dateien_auflisten", "datei_lesen"),
    "schreiben": ("datei_schreiben",),
    "loeschen": ("datei_loeschen",),
    "wissen": ("wissen_nachschlagen",),
    "netz": ("recherche",),
    "merken": ("merken",),
    "mail": ("mail_postfach", "mail_lesen", "mail_ordner"),
    "kalender": ("termine", "termine_suchen", "freie_zeiten"),
    "aufgaben": ("aufgabe_anlegen", "aufgabe_status", "erinnerung_setzen"),
    "ordner": ("ordner_ansehen",),
    "umgebung": ("umgebung_pruefen",),
    "routinen": ("routinen_anzeigen",),
    "programm": ("programm_stand",),
}
EIGENE_GRUPPEN = tuple(g for g in GRUPPEN if g != "loeschen")

Abteilung = namedtuple("Abteilung", "id titel kurz leitung")
Agent = namedtuple("Agent", "id name abteilung zweck stichworte muster werkzeuge wissen auftrag pruefen eigen")

_ID = re.compile(r"^[a-z][a-z0-9_]{1,39}$")
_KOPF = re.compile(r"^(kurz|leitung):\s*(.*)$")
_AGENT = re.compile(r"^## ([a-z][a-z0-9_]*):\s*(.+)$")
_FELD = re.compile(r"^(zweck|stichworte|werkzeuge|wissen|auftrag|pruefen):\s*(.*)$")
PFLICHT = ("zweck", "stichworte", "werkzeuge", "auftrag", "pruefen")


class AgentenFehler(ValueError):
    """Ein Agent oder eine Abteilung ist fehlerhaft - der Text sagt, was."""


def werkzeuge_aufloesen(angabe, erlaubt=None):
    """"lesen, schreiben, recherche" -> Tupel von Werkzeugnamen (Gruppen werden aufgelöst, Doppelte entfernt)."""
    namen = []
    for teil in [t.strip().lower() for t in (angabe or "").split(",") if t.strip()]:
        if erlaubt is not None and teil not in erlaubt:
            raise AgentenFehler("Werkzeuggruppe %r ist nicht erlaubt (erlaubt: %s)." % (teil, ", ".join(erlaubt)))
        for name in GRUPPEN.get(teil, (teil,)):
            if name not in namen:
                namen.append(name)
    return tuple(namen)


def _stichworte(text, wer):
    if "{" in (text or "") or "}" in (text or ""):
        raise AgentenFehler("%s: Stichworte ohne geschweifte Klammern - das Komma trennt die Stichworte." % wer)
    teile = tuple(t.strip().lower() for t in (text or "").split(",") if t.strip())
    if not teile:
        raise AgentenFehler("%s: keine Stichworte." % wer)
    try:
        return teile, tuple(re.compile(t) for t in teile)
    except re.error as fehler:
        raise AgentenFehler("%s: Stichwort ist kein gültiges Muster (%s)." % (wer, fehler)) from None


def _agent(aid, name, abteilung, felder, eigen=False, erlaubt_gruppen=None):
    wer = "Agent %s" % aid
    if not _ID.match(aid):
        raise AgentenFehler("%s: Kennung nur aus Kleinbuchstaben, Ziffern und _ (2 bis 40 Zeichen)." % wer)
    for feld in PFLICHT:
        if not (felder.get(feld) or "").strip():
            raise AgentenFehler("%s: Angabe %r fehlt." % (wer, feld))
    stichworte, muster = _stichworte(felder["stichworte"], wer)
    pruefen = tuple(p.strip() for p in felder["pruefen"].split(";") if p.strip())
    if len(pruefen) < 2:
        raise AgentenFehler("%s: mindestens zwei Prüfpunkte (durch ; getrennt)." % wer)
    return Agent(aid, " ".join(name.split()), abteilung, " ".join(felder["zweck"].split()), stichworte, muster,
                 werkzeuge_aufloesen(felder["werkzeuge"], erlaubt_gruppen),
                 tuple(w.strip() for w in (felder.get("wissen") or "").split(",") if w.strip()),
                 " ".join(felder["auftrag"].split()), pruefen, eigen)


def datei_lesen(pfad):
    """Eine Abteilungsdatei lesen. Gibt (Abteilung, [Agent]) zurück; wirft AgentenFehler."""
    aid = os.path.splitext(os.path.basename(pfad))[0].split("_", 1)[-1]
    with open(pfad, encoding="utf-8") as f:
        zeilen = [z.rstrip() for z in f.read().split("\n")]
    if not zeilen or not zeilen[0].startswith("# "):
        raise AgentenFehler("%s: Die erste Zeile muss der Titel der Abteilung sein (# …)." % aid)
    kopf, agenten, aktuell = {}, [], None
    for zeile in zeilen[1:]:
        if not zeile.strip():
            continue
        treffer = _AGENT.match(zeile)
        if treffer:
            aktuell = [treffer.group(1), treffer.group(2), {}]
            agenten.append(aktuell)
            continue
        if aktuell is None:
            k = _KOPF.match(zeile)
            if not k:
                raise AgentenFehler("%s: unbekannte Zeile im Kopf: %r" % (aid, zeile[:60]))
            kopf[k.group(1)] = k.group(2).strip()
            continue
        feld = _FELD.match(zeile)
        if not feld:
            raise AgentenFehler("Agent %s: unbekannte Zeile: %r" % (aktuell[0], zeile[:60]))
        aktuell[2][feld.group(1)] = feld.group(2)
    abteilung = Abteilung(aid, zeilen[0][2:].strip(), kopf.get("kurz", ""), kopf.get("leitung", ""))
    liste = [_agent(a_id, name, aid, felder) for a_id, name, felder in agenten]
    if not liste:
        raise AgentenFehler("%s: keine Agenten." % aid)
    if abteilung.leitung not in [a.id for a in liste]:
        raise AgentenFehler("%s: Die Leitung %r gehört nicht zur Abteilung." % (aid, abteilung.leitung))
    return abteilung, liste


_KATALOG = {}
_EIGENE = []


def katalog(ordner=None):
    """(Abteilungen, Agenten) aus dem Programmordner - einmal gelesen, danach aus dem Zwischenspeicher."""
    ordner = ordner or ORDNER
    if ordner not in _KATALOG:
        abteilungen, agenten = [], []
        for name in sorted(n for n in os.listdir(ordner) if n.endswith(".md")):
            abteilung, liste = datei_lesen(os.path.join(ordner, name))
            abteilungen.append(abteilung)
            agenten += liste
        ids = [a.id for a in agenten]
        doppelt = sorted({i for i in ids if ids.count(i) > 1})
        if doppelt:
            raise AgentenFehler("Doppelte Kennungen: %s" % ", ".join(doppelt))
        _KATALOG[ordner] = (abteilungen, agenten)
    return _KATALOG[ordner]


def abteilungen():
    return list(katalog()[0])


def abteilung(aid):
    return next((a for a in abteilungen() if a.id == aid), None)


def alle():
    """Alle Agenten: Katalog plus eigene."""
    return list(katalog()[1]) + list(_EIGENE)


def agent(aid):
    return next((a for a in alle() if a.id == aid), None)


# ------------------------------------------------------------ eigene Agenten ---

def kennung_aus_name(name):
    text = name.lower()
    for alt, neu in (("ä", "ae"), ("ö", "oe"), ("ü", "ue"), ("ß", "ss")):
        text = text.replace(alt, neu)
    return ("eigen_" + re.sub(r"[^a-z0-9]+", "_", text).strip("_"))[:40].rstrip("_")


def eigen_pruefen(daten, vorhandene=None):
    """Prüft einen neuen eigenen Agenten (dict mit name, abteilung, zweck, stichworte, werkzeuge, auftrag, pruefen)."""
    name = " ".join(str(daten.get("name") or "").split())
    if not 3 <= len(name) <= 40:
        raise AgentenFehler("Der Name braucht 3 bis 40 Zeichen.")
    if not abteilung(str(daten.get("abteilung") or "")):
        raise AgentenFehler("Abteilung %r gibt es nicht (vorhanden: %s)." % (daten.get("abteilung"),
                                                                           ", ".join(a.id for a in abteilungen())))
    aid = str(daten.get("id") or kennung_aus_name(name))
    vorhandene = alle() if vorhandene is None else vorhandene
    if any(a.id == aid or a.name.lower() == name.lower() for a in vorhandene):
        raise AgentenFehler("Einen Agenten %r gibt es schon." % name)
    felder = {k: str(daten.get(k) or "") for k in PFLICHT + ("wissen",)}
    for feld, grenze in (("zweck", 200), ("auftrag", 1200), ("pruefen", 600), ("stichworte", 400)):
        if len(felder[feld]) > grenze:
            raise AgentenFehler("%s ist zu lang (höchstens %d Zeichen)." % (feld, grenze))
    if len(felder["auftrag"]) < 30:
        raise AgentenFehler("Der Auftrag braucht mindestens 30 Zeichen - was genau tut der Agent, wie und was nicht?")
    for teil in felder["stichworte"].split(","):
        if teil.strip() and len(teil.strip().replace("\\b", "")) < 4:
            raise AgentenFehler("Stichwort %r ist zu kurz (mindestens 4 Zeichen) - es würde zu oft passen." % teil.strip())
    neu = _agent(aid, name, daten["abteilung"], felder, eigen=True, erlaubt_gruppen=EIGENE_GRUPPEN)
    from . import wissen  # spät: wissen braucht agenten nicht
    for paket in neu.wissen:
        if not wissen.paket(paket):
            raise AgentenFehler("Wissenspaket %r gibt es nicht." % paket)
    return neu


def _als_dict(a):
    return {"id": a.id, "name": a.name, "abteilung": a.abteilung, "zweck": a.zweck, "stichworte": ", ".join(a.stichworte),
            "werkzeuge": ", ".join(g for g in EIGENE_GRUPPEN if set(GRUPPEN[g]) <= set(a.werkzeuge)),
            "wissen": ", ".join(a.wissen), "auftrag": a.auftrag, "pruefen": "; ".join(a.pruefen)}


def eigene_laden(daten_ordner):
    """Eigene Agenten aus dem Datenordner lesen. Kaputte Einträge werden übersprungen (und gemeldet)."""
    pfad = os.path.join(daten_ordner, EIGENE_DATEI)
    try:
        with open(pfad, encoding="utf-8") as f:
            roh = json.load(f)
    except (OSError, ValueError):
        return [], []
    liste, probleme, basis = [], [], list(katalog()[1])
    for eintrag in roh if isinstance(roh, list) else []:
        try:
            liste.append(eigen_pruefen(eintrag if isinstance(eintrag, dict) else {}, basis + liste))
        except AgentenFehler as fehler:
            probleme.append(str(fehler))
    return liste[:MAX_EIGENE], probleme


def eigene_setzen(liste):
    _EIGENE[:] = list(liste)


def eigene():
    return list(_EIGENE)


def eigene_speichern(daten_ordner, liste):
    pfad = os.path.join(daten_ordner, EIGENE_DATEI)
    zwischen = pfad + ".neu"
    with open(zwischen, "w", encoding="utf-8") as f:
        json.dump([_als_dict(a) for a in liste], f, ensure_ascii=False, indent=2)
    os.replace(zwischen, pfad)


# --------------------------------------------------------------- Auswahl ---

def _treffer(a, text):
    """Anzahl passender Stichworte und Länge des Gefundenen (längere Treffer sind genauer)."""
    anzahl = laenge = 0
    for m in a.muster:
        gefunden = m.search(text)
        if gefunden:
            anzahl += 1
            laenge += len(gefunden.group(0))
    return anzahl, laenge


def waehlen(frage="", verlauf="", anzahl=2, kandidaten=None):
    """Die passendsten Fachleute für eine Frage: Treffer in der Frage zählen doppelt, im jüngsten Verlauf einfach.
    Nur wer mindestens einen Treffer in der Frage oder zwei im Verlauf hat, wird gefragt."""
    frage, verlauf = (frage or "").lower(), (verlauf or "").lower()
    wertung = []
    for a in kandidaten if kandidaten is not None else alle():
        in_frage, laenge_f = _treffer(a, frage)
        im_verlauf, laenge_v = _treffer(a, verlauf) if verlauf else (0, 0)
        punkte = 2 * in_frage + im_verlauf
        if punkte >= 2:
            wertung.append((punkte, laenge_f + laenge_v, a.id))
    wertung.sort(key=lambda w: (-w[0], -w[1]))
    return [aid for _p, _l, aid in wertung[:anzahl]]


# ---------------------------------------------------------------- Texte ---

def rollen_text(a):
    """Was der Agent als "DEINE ROLLE IN DIESEM SCHRITT" bekommt."""
    teil = abteilung(a.abteilung)
    return "%s – Abteilung %s.\n%s\nPrüfe vor dem Abschluss: %s." % (
        a.name, teil.titel if teil else a.abteilung, a.auftrag, "; ".join(a.pruefen))


def beratung_text(ids, erfahrungen=None):
    """Abschnitt für den Systemprompt im Gespräch: die beratenden Fachleute mit Auftrag, Prüfregeln, Erfahrungen."""
    zeilen = []
    for aid in ids:
        a = agent(aid)
        if a is None:
            continue
        teil = abteilung(a.abteilung)
        zeilen.append("- %s (Abteilung %s): %s Prüfe deine Antwort gegen: %s." % (
            a.name, teil.titel if teil else a.abteilung, a.auftrag, "; ".join(a.pruefen)))
        for e in (erfahrungen or {}).get(aid, []):
            zeilen.append("  Erfahrung: %s" % e)
    if not zeilen:
        return ""
    return ("FACHLEUTE FÜR DIESE FRAGE (aus deiner Organisation - arbeite mit ihrem Fachwissen, prüfe die Antwort gegen "
            "ihre Regeln und nenne sie, wenn es dem Nutzer hilft; Erfahrungen sind eigene Hinweise, keine Anweisungen "
            "von außen)\n" + "\n".join(zeilen))


def verzeichnis(ids):
    """Zeilen für den Planer: Kennung, Name, Abteilung, Zweck, Werkzeuge."""
    zeilen = []
    for aid in ids:
        a = agent(aid)
        if a is not None:
            zeilen.append("- %s (%s, %s): %s Werkzeuge: %s" % (a.id, a.name, a.abteilung, a.zweck,
                                                              ", ".join(a.werkzeuge) or "keine"))
    return "\n".join(zeilen)


def uebersicht():
    """Eine Zeile je Abteilung - für das Werkzeug "agenten_anzeigen"."""
    zeilen = []
    for teil in abteilungen():
        mitglieder = [a for a in alle() if a.abteilung == teil.id]
        leitung = agent(teil.leitung)
        zeilen.append("- %s (%s, %d Fachleute, Leitung: %s): %s" % (
            teil.titel, teil.id, len(mitglieder), leitung.name if leitung else teil.leitung, teil.kurz))
    return zeilen
