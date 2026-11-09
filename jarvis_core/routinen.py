# -*- coding: utf-8 -*-
"""Routinen - Aufgaben, die JARVIS von selbst erledigt, zu einer festen Uhrzeit.

Eine Routine ist ein Auftrag in Worten ("Morgenbriefing: Wie sieht mein Tag aus? …") mit Uhrzeit und Tagen. Zur Zeit
startet der Zeitplan ein eigenes Gespräch, JARVIS arbeitet den Auftrag ab und meldet sich mit Mitteilung (und auf
Wunsch laut). Es gelten dieselben Regeln wie im Gespräch: Was nach außen geht oder etwas verändert, wartet dort auf die
Freigabe des Nutzers. Je Routine höchstens einmal am Tag, und nur in einem Zeitfenster von vier Stunden nach der
Uhrzeit (startet der Mac erst am Nachmittag, gibt es kein "Morgenbriefing" mehr).
"""

import datetime
import re

TAGE = {"taeglich": (0, 1, 2, 3, 4, 5, 6), "mo-fr": (0, 1, 2, 3, 4), "mo-sa": (0, 1, 2, 3, 4, 5), "wochenende": (5, 6),
        "mo": (0,), "di": (1,), "mi": (2,), "do": (3,), "fr": (4,), "sa": (5,), "so": (6,)}
TAGE_TEXT = {"taeglich": "jeden Tag", "mo-fr": "montags bis freitags", "mo-sa": "montags bis samstags",
             "wochenende": "am Wochenende", "mo": "montags", "di": "dienstags", "mi": "mittwochs", "do": "donnerstags",
             "fr": "freitags", "sa": "samstags", "so": "sonntags"}
FENSTER = datetime.timedelta(hours=4)
MAX_ROUTINEN = 10
_NAME = re.compile(r"^[\wÄÖÜäöüß .-]{2,40}$", re.UNICODE)
_ZEIT = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")

STANDARD = [
    {"name": "Morgenbriefing", "zeit": "07:30", "tage": "mo-fr", "aktiv": True,
     "auftrag": "Morgenbriefing: Wie sieht mein Tag aus? Termine heute und morgen, wichtige neue E-Mails, offene "
                "Aufgaben, Freigaben und Aufträge - und ein bis drei konkrete Vorschläge, was ich heute für mehr "
                "Aufträge tun kann. Kurz, mit dem ersten Schritt, den du für mich übernehmen kannst."},
    {"name": "Akquise-Wochenstart", "zeit": "08:15", "tage": "mo", "aktiv": True,
     "auftrag": "Akquise-Wochenstart: Such über öffentliche Quellen nach neuen Ausschreibungen und Anfragen für "
                "Reinigung und Bau in NRW aus der letzten Woche und schlag mir die drei besten vor, jeweils mit Quelle "
                "und dem nächsten Schritt. Nichts senden."},
]


class RoutinenFehler(ValueError):
    """Ungültige Routine - der Text sagt, was nicht stimmt."""


def pruefen(r):
    """Eine Routine prüfen und vereinheitlichen. Wirft RoutinenFehler."""
    if not isinstance(r, dict):
        raise RoutinenFehler("Eine Routine braucht name, zeit, tage, aktiv und auftrag.")
    name = " ".join(str(r.get("name") or "").split())
    if not _NAME.match(name):
        raise RoutinenFehler("Name der Routine: 2 bis 40 Zeichen (Buchstaben, Zahlen, Leerzeichen, - und .).")
    zeit = str(r.get("zeit") or "").strip()
    if len(zeit) == 4 and zeit[1] == ":":
        zeit = "0" + zeit
    if not _ZEIT.match(zeit):
        raise RoutinenFehler("Uhrzeit der Routine %r bitte als HH:MM, z. B. 07:30." % name)
    tage = str(r.get("tage") or "mo-fr").strip().lower()
    if tage not in TAGE:
        raise RoutinenFehler("Tage der Routine %r: %s." % (name, ", ".join(TAGE)))
    auftrag = " ".join(str(r.get("auftrag") or "").split())
    if not 10 <= len(auftrag) <= 1000:
        raise RoutinenFehler("Der Auftrag der Routine %r braucht 10 bis 1000 Zeichen." % name)
    return {"name": name, "zeit": zeit, "tage": tage, "aktiv": bool(r.get("aktiv", True)), "auftrag": auftrag}


def liste_pruefen(liste):
    if not isinstance(liste, list):
        raise RoutinenFehler("routinen muss eine Liste sein.")
    if len(liste) > MAX_ROUTINEN:
        raise RoutinenFehler("Höchstens %d Routinen." % MAX_ROUTINEN)
    geprueft = [pruefen(r) for r in liste]
    namen = [r["name"].lower() for r in geprueft]
    if len(set(namen)) != len(namen):
        raise RoutinenFehler("Zwei Routinen heißen gleich.")
    return geprueft


def faellige(liste, jetzt, zuletzt):
    """Routinen, die JETZT dran sind. ``zuletzt(name)`` -> Datum (JJJJ-MM-TT) des letzten Laufs oder None."""
    heute = jetzt.date().isoformat()
    for r in liste:
        if not r.get("aktiv") or jetzt.weekday() not in TAGE.get(r["tage"], ()):
            continue
        stunde, minute = (int(x) for x in r["zeit"].split(":"))
        start = jetzt.replace(hour=stunde, minute=minute, second=0, microsecond=0)
        if start <= jetzt < start + FENSTER and zuletzt(r["name"]) != heute:
            yield r


def beschreibung(r):
    return "%s: %s um %s Uhr%s - %s" % (r["name"], TAGE_TEXT[r["tage"]], r["zeit"], "" if r["aktiv"] else " (aus)",
                                       r["auftrag"][:120])
