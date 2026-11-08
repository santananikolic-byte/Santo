# -*- coding: utf-8 -*-
"""Kalender - Termine aus der Kalender-App des Macs lesen, freie Zeiten finden, Termine eintragen.

Gelesen wird alles, was in der Kalender-App eingerichtet ist (iCloud vom iPhone, Google, Exchange …). Kein Passwort in
JARVIS. Der Zugriff läuft über EventKit - dieselbe Schnittstelle, die auch die Kalender-App nutzt -, aufgerufen mit
``osascript -l JavaScript kalender.js`` (aus einer Datei: lange Skripte über ``-e`` wurden auf neuen macOS-Fassungen
abgebrochen). Serientermine kommen einzeln. Nutzertext geht nur als Argument hinein, nie in den Skripttext. Beim
ersten Mal fragt macOS (für das Terminal) nach dem Kalender; nötig ist "Vollzugriff".

Regeln (im Code erzwungen):

* Termine eintragen: nur in einen beschreibbaren Kalender, immer ohne Teilnehmer - JARVIS verschickt nie Einladungen.
* Ändern und Löschen gibt es nicht.
* Kalenderinhalte sind eine Außenquelle (Einladungen enthalten fremden Text): danach braucht auch eine Aktion mit
  Meldung die Freigabe des Nutzers.
* Freie Zeiten sind ein Vorschlag aus dem Kalender. Einem Kunden zugesagt wird nichts - das prüft der Nutzer.
"""

import datetime
import json
import os
import re
import shutil
import subprocess

ANKER = "JARVIS"
MAX_TAGE = 31
MAX_TERMINE = 300
MAX_TITEL = 200
MAX_ORT = 300
MAX_NOTIZ = 2000
SKRIPT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "kalender.js")
_UHRZEIT = re.compile(r"^([01]?\d|2[0-3])[:.]([0-5]\d)$")
_STEUERZEICHEN = re.compile(r"[\x00-\x08\x0b-\x1f\x7f]")
WOCHENTAGE = ("Mo", "Di", "Mi", "Do", "Fr", "Sa", "So")
ISO = "%Y-%m-%dT%H:%M:%S"


class KalenderFehler(Exception):
    """Fehler, den der Nutzer verstehen soll."""


ERKLAERUNG = {
    "zugriff_verweigert": "macOS erlaubt den Zugriff auf den Kalender noch nicht. Systemeinstellungen → Datenschutz & "
                          "Sicherheit → Kalender → beim Terminal „Vollzugriff“ einschalten.",
    "zugriff_offen": "Der Mac hat gerade gefragt, ob JARVIS auf den Kalender zugreifen darf. Bitte erlauben und dann "
                     "noch einmal versuchen.",
    "nur_hinzufuegen": "macOS erlaubt JARVIS beim Kalender nur das Hinzufügen, nicht das Lesen. Systemeinstellungen → "
                       "Datenschutz & Sicherheit → Kalender → beim Terminal auf „Optionen…“ → „Vollzugriff“.",
    "kalender_unbekannt": "Diesen Kalender gibt es in der Kalender-App nicht.",
    "kalender_mehrdeutig": "Mehrere Kalender heißen so (z. B. bei iCloud und Google). Bitte einen davon in der "
                           "Kalender-App umbenennen.",
    "datum": "Diese Zeit gibt es nicht (z. B. 31.02. oder in der Stunde der Zeitumstellung).",
    "aufruf": "Interner Fehler beim Aufruf des Kalenders.",
    "nur_lesen": "In diesen Kalender kann man nichts eintragen (z. B. Feiertage, Geburtstage oder ein abonnierter Kalender).",
    "kein_kalender": "In der Kalender-App ist kein Kalender zum Eintragen eingerichtet.",
    "speichern": "Die Kalender-App hat den Termin nicht gespeichert.",
}


def uhrzeit_pruefen(text):
    """ "9:30", "09.30" -> datetime.time. Wirft KalenderFehler."""
    t = _UHRZEIT.match((text or "").strip())
    if not t:
        raise KalenderFehler("Uhrzeit bitte als HH:MM, z. B. 09:30, nicht %r." % text)
    return datetime.time(int(t.group(1)), int(t.group(2)))


def text_pruefen(text, feld, maximal, pflicht=False):
    text = _STEUERZEICHEN.sub(" ", (text or "")).strip()
    if pflicht and not text:
        raise KalenderFehler("%s fehlt." % feld)
    if len(text) > maximal:
        raise KalenderFehler("%s ist zu lang (höchstens %d Zeichen)." % (feld, maximal))
    return text


def _zeit(text):
    try:
        return datetime.datetime.strptime((text or "")[:19], ISO)
    except ValueError:
        return None


def termine_lesen(roh):
    """Antwort des Skripts -> saubere Termine (beginn/ende als datetime). Unvollständige werden übergangen."""
    termine = []
    for t in roh if isinstance(roh, list) else []:
        if not isinstance(t, dict):
            continue
        beginn, ende = _zeit(t.get("beginn")), _zeit(t.get("ende"))
        if beginn is None or ende is None:
            continue
        termine.append({"titel": str(t.get("titel") or "(ohne Titel)")[:MAX_TITEL], "beginn": beginn,
                        "ende": max(ende, beginn), "ganztag": bool(t.get("ganztag")),
                        "ort": str(t.get("ort") or "")[:MAX_ORT], "kalender": str(t.get("kalender") or "")[:100]})
    termine.sort(key=lambda t: (t["beginn"], not t["ganztag"], t["titel"]))
    return termine[:MAX_TERMINE]


def tag_text(tag):
    return "%s %s" % (WOCHENTAGE[tag.weekday()], tag.strftime("%d.%m.%Y"))


def termin_zeile(t):
    if t["ganztag"]:
        zeit = "ganztägig"
    else:
        zeit = "%s–%s" % (t["beginn"].strftime("%H:%M"), t["ende"].strftime("%H:%M") if t["ende"].date() == t["beginn"].date()
                          else t["ende"].strftime("%d.%m. %H:%M"))
    return "%s · %s%s%s" % (zeit, t["titel"], " · " + t["ort"] if t["ort"] else "",
                            " [%s]" % t["kalender"] if t["kalender"] else "")


def am_tag(t, tag):
    """Liegt der Termin (auch mehrtägig) an diesem Tag? Das Ende zählt ausschließlich: ganztägig bis 00:00 des
    Folgetags oder bis 23:59:59 - beides ergibt denselben letzten Tag."""
    letzter = max(t["beginn"].date(), (t["ende"] - datetime.timedelta(seconds=1)).date())
    return t["beginn"].date() <= tag <= letzter


def uebersicht(termine, von, bis):
    """Termine nach Tagen; jeder Tag des Zeitraums erscheint, auch die freien."""
    zeilen = []
    tag = von
    while tag < bis:
        heute = [t for t in termine if am_tag(t, tag)]
        zeilen.append("%s:%s" % (tag_text(tag), "" if heute else " nichts eingetragen"))
        zeilen += ["   " + termin_zeile(t) for t in heute]
        tag += datetime.timedelta(days=1)
    return zeilen


def ueberschneidungen(termine, beginn, ende):
    """Termine mit Uhrzeit, die sich mit [beginn, ende) überschneiden."""
    return [t for t in termine if not t["ganztag"] and t["beginn"] < ende and t["ende"] > beginn]


def freie_zeiten(termine, von, tage, dauer, tag_von=datetime.time(7, 0), tag_bis=datetime.time(18, 0), puffer=30,
                 wochenende=False, jetzt=None, max_treffer=10):
    """Freie Zeitfenster von mindestens ``dauer`` Minuten, mit ``puffer`` Minuten Abstand (Anfahrt) zu anderen
    Terminen, nur in der Arbeitszeit. Ganztägige Termine blockieren nicht (oft Geburtstage, Feiertage), werden aber
    je Tag als Hinweis genannt. Gibt ([(beginn, ende)], {tag: [ganztägige Titel]}) zurück."""
    jetzt = jetzt or datetime.datetime.now()
    dauer_d, puffer_d = datetime.timedelta(minutes=dauer), datetime.timedelta(minutes=puffer)
    belegt = sorted((t["beginn"] - puffer_d, t["ende"] + puffer_d) for t in termine if not t["ganztag"])
    treffer, hinweise = [], {}
    for n in range(tage):
        tag = von + datetime.timedelta(days=n)
        if tag.weekday() >= 5 and not wochenende:
            continue
        ganz = [t["titel"] for t in termine if t["ganztag"] and am_tag(t, tag)]
        if ganz:
            hinweise[tag] = ganz
        frei_ab = datetime.datetime.combine(tag, tag_von)
        schluss = datetime.datetime.combine(tag, tag_bis)
        if frei_ab < jetzt:  # heute: erst ab jetzt, auf die nächste Viertelstunde gerundet
            frei_ab = jetzt.replace(second=0, microsecond=0) + datetime.timedelta(minutes=(15 - jetzt.minute % 15) % 15)
        for b_von, b_bis in belegt:
            if b_bis <= frei_ab or b_von >= schluss:
                continue
            if b_von - frei_ab >= dauer_d:
                treffer.append((frei_ab, b_von))
            frei_ab = max(frei_ab, b_bis)
        if schluss - frei_ab >= dauer_d:
            treffer.append((frei_ab, schluss))
        if len(treffer) >= max_treffer:
            break
    return treffer[:max_treffer], hinweise


# ------------------------------------------------------------------ Mac ---

class MacKalender:
    """Dünne Schicht über die Kalender-App. Jede Methode ist ein osascript-Aufruf, die Antwort ist JSON."""

    def __init__(self, timeout=150):  # beim ersten Mal wartet das Skript bis zu 90 s auf die Erlaubnis
        self.timeout = timeout

    @staticmethod
    def programm():
        fest = os.environ.get("JARVIS_OSASCRIPT")  # nur für Tests
        if fest:
            return fest if os.path.isfile(fest) and os.access(fest, os.X_OK) else None
        return shutil.which("osascript")

    def verfuegbar(self):
        return self.programm() is not None

    def _lauf(self, befehl_name, *argumente):
        programm = self.programm()
        if not programm:
            raise KalenderFehler("Der Kalender ist nur auf dem Mac erreichbar (osascript fehlt hier).")
        befehl = [programm, "-l", "JavaScript", SKRIPT, ANKER, befehl_name] + [str(a) for a in argumente]
        try:
            lauf = subprocess.run(befehl, capture_output=True, text=True, encoding="utf-8", errors="replace",  # noqa: S603
                                  timeout=self.timeout)
        except subprocess.TimeoutExpired:
            raise KalenderFehler("Die Kalender-App hat nicht rechtzeitig geantwortet. Bitte später noch einmal.") from None
        except OSError as fehler:
            raise KalenderFehler("osascript ließ sich nicht starten: %s" % fehler) from None
        try:
            daten = json.loads(lauf.stdout.strip().splitlines()[-1]) if lauf.stdout.strip() else None
        except ValueError:
            daten = None
        if not isinstance(daten, dict):
            raise KalenderFehler("Der Kalender hat unerwartet geantwortet: %s" % (lauf.stderr or lauf.stdout).strip()[-300:])
        if daten.get("fehler"):
            raise KalenderFehler(ERKLAERUNG.get(daten["fehler"], "Kalenderfehler: %s %s" % (
                daten["fehler"], str(daten.get("text") or "")[:200])).strip())
        return daten

    def termine(self, von, bis, mit_kalendern=False):
        """Termine (auch die einzelnen Termine einer Serie) zwischen zwei Tagen (bis ausschließlich). Mit
        ``mit_kalendern`` zusätzlich die Kalenderliste [{"name", "schreibbar"}] und der Standardkalender."""
        daten = self._lauf("termine", datetime.datetime.combine(von, datetime.time()).strftime(ISO),
                           datetime.datetime.combine(bis, datetime.time()).strftime(ISO))
        termine = termine_lesen(daten.get("termine"))
        if not mit_kalendern:
            return termine
        liste = [{"name": str(k.get("name", ""))[:100], "schreibbar": bool(k.get("schreibbar"))}
                 for k in daten.get("kalender") or [] if isinstance(k, dict)]
        return termine, liste, str(daten.get("standard") or "")

    def eintragen(self, titel, beginn, ende, ganztag=False, ort="", notiz="", kalender=""):
        """Legt einen Termin ohne Teilnehmer an. Gibt den Namen des Kalenders zurück, in dem er gelandet ist."""
        daten = self._lauf("eintragen", titel, beginn.strftime(ISO), ende.strftime(ISO), "1" if ganztag else "0",
                           ort, notiz, kalender)
        if not daten.get("ok"):
            raise KalenderFehler(ERKLAERUNG["speichern"])
        return str(daten.get("kalender") or kalender)
