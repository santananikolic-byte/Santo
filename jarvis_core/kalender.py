# -*- coding: utf-8 -*-
"""Kalender - Termine der Kalender-App des Macs: ansehen, suchen, freie Zeiten finden, eintragen (auch als Serie und
mit Erinnerung), ändern, verschieben, löschen und wiederherstellen.

Gelesen wird alles, was in der Kalender-App eingerichtet ist (iCloud vom iPhone, Google, Exchange …). Kein Passwort in
JARVIS. Der Zugriff läuft über EventKit - dieselbe Schnittstelle, die auch die Kalender-App nutzt -, aufgerufen mit
``osascript -l JavaScript kalender.js`` (aus einer Datei: lange Skripte über ``-e`` wurden auf neuen macOS-Fassungen
abgebrochen). Serientermine kommen einzeln. Nutzertext geht nur als Argument hinein, nie in den Skripttext. Beim
ersten Mal fragt macOS (für das Terminal) nach dem Kalender; nötig ist "Vollzugriff".

Regeln (im Code erzwungen):

* Nur in beschreibbare Kalender, immer ohne Teilnehmer (EventKit kann niemanden einladen - eine Bestätigung an den Kunden
  geht als E-Mail, und die nur nach Freigabe).
* Ändern, Verschieben und Löschen nur nach der Freigabe des Nutzers für genau diesen Termin. Vor dem Löschen sichert JARVIS
  den Termin (Papierkorb im Datenordner), er lässt sich wiederherstellen.
* Ein Termin wird über eine kurze Nummer angesprochen (aus der Kennung und dem Beginn), die JARVIS bei jeder Anzeige
  vergibt - so trifft eine Änderung genau den gemeinten Termin, auch innerhalb einer Serie.
* Kalenderinhalte sind eine Außenquelle (Einladungen enthalten fremden Text): danach braucht auch eine Aktion mit
  Meldung die Freigabe des Nutzers.
* Freie Zeiten sind ein Vorschlag aus dem Kalender. Einem Kunden zugesagt wird nichts - das prüft der Nutzer.
"""

import datetime
import hashlib
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
MAX_NUMMERN = 1000
WIEDERHOLEN = {"taeglich": ("taeglich", 1, "täglich"), "woechentlich": ("woechentlich", 1, "jede Woche"),
               "alle_2_wochen": ("woechentlich", 2, "alle 2 Wochen"), "monatlich": ("monatlich", 1, "jeden Monat"),
               "jaehrlich": ("jaehrlich", 1, "jedes Jahr")}
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
    "nicht_gefunden": "Diesen Termin gibt es so nicht mehr (vielleicht schon geändert oder gelöscht). Bitte die Termine "
                      "neu anzeigen lassen.",
    "loeschen": "Die Kalender-App hat den Termin nicht gelöscht.",
    "wiederholen": "Diese Wiederholung kennt der Kalender nicht.",
    "suchwort": "Das Suchwort ist zu kurz (mindestens 2 Zeichen).",
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
        kennung = str(t.get("id") or "")[:300]
        termine.append({"titel": str(t.get("titel") or "(ohne Titel)")[:MAX_TITEL], "beginn": beginn,
                        "ende": max(ende, beginn), "ganztag": bool(t.get("ganztag")),
                        "ort": str(t.get("ort") or "")[:MAX_ORT], "kalender": str(t.get("kalender") or "")[:100],
                        "id": kennung, "serie": bool(t.get("serie")), "notiz": str(t.get("notiz") or "")[:MAX_NOTIZ],
                        "nr": nummer(kennung, beginn) if kennung else ""})
    termine.sort(key=lambda t: (t["beginn"], not t["ganztag"], t["titel"]))
    return termine[:MAX_TERMINE]


def nummer(kennung, beginn):
    """Kurze, stabile Nummer für genau diesen Termin (auch innerhalb einer Serie): aus Kennung und Beginn."""
    return hashlib.sha1(("%s|%s" % (kennung, beginn.strftime(ISO))).encode("utf-8")).hexdigest()[:6]  # noqa: S324


def _json_lesen(pfad, standard):
    try:
        with open(pfad, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return standard


def _json_schreiben(pfad, daten):
    os.makedirs(os.path.dirname(pfad), mode=0o700, exist_ok=True)
    hilfe = pfad + ".tmp"
    with open(hilfe, "w", encoding="utf-8") as f:
        json.dump(daten, f, ensure_ascii=False, indent=1)
        f.flush()
        os.fsync(f.fileno())
    os.replace(hilfe, pfad)


def nummern_merken(ordner, termine):
    """Merkt sich die Nummern der zuletzt gezeigten Termine (höchstens 1000), damit "ändern Nr. a3f9c1" eindeutig ist."""
    pfad = os.path.join(ordner, "kalender_nummern.json")
    karte = _json_lesen(pfad, {})
    if not isinstance(karte, dict):
        karte = {}
    jetzt = datetime.datetime.now().strftime(ISO)
    for t in termine:
        if t.get("nr"):
            karte[t["nr"]] = {"id": t["id"], "beginn": t["beginn"].strftime(ISO), "titel": t["titel"],
                              "ganztag": t["ganztag"], "gemerkt": jetzt}
    if len(karte) > MAX_NUMMERN:
        karte = dict(sorted(karte.items(), key=lambda e: str(e[1].get("gemerkt")))[-MAX_NUMMERN:])
    _json_schreiben(pfad, karte)


def nummer_aufloesen(ordner, nr):
    """Nr. -> {"id", "beginn" (datetime), "titel", "ganztag"}. Wirft KalenderFehler."""
    nr = (nr or "").strip().lower().lstrip("#").replace("nr.", "").strip()
    eintrag = _json_lesen(os.path.join(ordner, "kalender_nummern.json"), {}).get(nr) if re.match(r"^[0-9a-f]{6}$", nr) else None
    if not isinstance(eintrag, dict) or _zeit(eintrag.get("beginn")) is None:
        raise KalenderFehler("Die Termin-Nummer %r kenne ich nicht. Bitte erst die Termine anzeigen lassen (termine oder "
                             "termine_suchen) und die Nummer von dort nehmen." % nr)
    return dict(eintrag, beginn=_zeit(eintrag["beginn"]))


def papierkorb(ordner):
    liste = _json_lesen(os.path.join(ordner, "kalender_papierkorb.json"), [])
    return liste if isinstance(liste, list) else []


def papierkorb_ablegen(ordner, termin):
    """Sichert einen Termin VOR dem Löschen. Gibt die Nummer im Papierkorb zurück."""
    liste = papierkorb(ordner)
    nr = max([e.get("nr", 0) for e in liste if isinstance(e, dict)] + [0]) + 1
    liste.append(dict(termin, nr=nr, geloescht=datetime.datetime.now().strftime(ISO)))
    _json_schreiben(os.path.join(ordner, "kalender_papierkorb.json"), liste[-200:])
    return nr


def papierkorb_entfernen(ordner, nr):
    liste = [e for e in papierkorb(ordner) if not (isinstance(e, dict) and e.get("nr") == nr)]
    _json_schreiben(os.path.join(ordner, "kalender_papierkorb.json"), liste)


def serie_termine(beginn, wiederholen, bis=None, anzahl=None, hoechstens=8):
    """Die ersten Termine einer Serie - für die Vorschau und die Prüfung auf Überschneidungen."""
    art, intervall, _ = WIEDERHOLEN[wiederholen]
    liste, aktuell = [], beginn
    while len(liste) < hoechstens and (not anzahl or len(liste) < anzahl) and (not bis or aktuell.date() <= bis):
        liste.append(aktuell)
        if art == "taeglich":
            aktuell = aktuell + datetime.timedelta(days=intervall)
        elif art == "woechentlich":
            aktuell = aktuell + datetime.timedelta(weeks=intervall)
        else:
            monate = intervall if art == "monatlich" else 12 * intervall
            m = aktuell.month - 1 + monate
            jahr, monat = aktuell.year + m // 12, m % 12 + 1
            while True:  # z. B. der 31.: Monate ohne diesen Tag übergeht auch der Kalender
                try:
                    aktuell = aktuell.replace(year=jahr, month=monat)
                    break
                except ValueError:
                    m += monate
                    jahr, monat = aktuell.year + m // 12, m % 12 + 1
    return liste


def tag_text(tag):
    return "%s %s" % (WOCHENTAGE[tag.weekday()], tag.strftime("%d.%m.%Y"))


def termin_zeile(t):
    if t["ganztag"]:
        zeit = "ganztägig"
    else:
        zeit = "%s–%s" % (t["beginn"].strftime("%H:%M"), t["ende"].strftime("%H:%M") if t["ende"].date() == t["beginn"].date()
                          else t["ende"].strftime("%d.%m. %H:%M"))
    return "%s · %s%s%s%s%s" % (zeit, t["titel"], " · " + t["ort"] if t["ort"] else "",
                                " [%s]" % t["kalender"] if t["kalender"] else "", " · Serie" if t.get("serie") else "",
                                " · Nr. %s" % t["nr"] if t.get("nr") else "")


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

    def suchen(self, wort, von, bis):
        daten = self._lauf("suchen", datetime.datetime.combine(von, datetime.time()).strftime(ISO),
                           datetime.datetime.combine(bis, datetime.time()).strftime(ISO), wort)
        return termine_lesen(daten.get("termine"))

    def eintragen(self, titel, beginn, ende, ganztag=False, ort="", notiz="", kalender="", erinnerung=None,
                  wiederholen="", bis=None, anzahl=None):
        """Legt einen Termin ohne Teilnehmer an, auf Wunsch als Serie und mit Erinnerung (Minuten vorher). Gibt den
        Namen des Kalenders zurück, in dem er gelandet ist."""
        extras = {}
        if erinnerung is not None:
            extras["erinnerung"] = int(erinnerung)
        if wiederholen:
            art, intervall, _ = WIEDERHOLEN[wiederholen]
            extras.update({"wiederholen": art, "intervall": intervall})
            if bis:
                extras["bis"] = datetime.datetime.combine(bis, datetime.time(23, 59, 59)).strftime(ISO)
            elif anzahl:
                extras["anzahl"] = int(anzahl)
        daten = self._lauf("eintragen", titel, beginn.strftime(ISO), ende.strftime(ISO), "1" if ganztag else "0",
                           ort, notiz, kalender, json.dumps(extras))
        if not daten.get("ok"):
            raise KalenderFehler(ERKLAERUNG["speichern"])
        return str(daten.get("kalender") or kalender)

    def details(self, kennung, beginn):
        """Alles zu einem Termin (auch Notiz, Erinnerungen, Wiederholung) - für Vorschau und Sicherung."""
        t = self._lauf("details", kennung, beginn.strftime(ISO)).get("termin")
        if not isinstance(t, dict):
            raise KalenderFehler(ERKLAERUNG["nicht_gefunden"])
        termin = termine_lesen([t])
        if not termin:
            raise KalenderFehler(ERKLAERUNG["nicht_gefunden"])
        termin = termin[0]
        termin["regel"] = t.get("regel") if isinstance(t.get("regel"), dict) else None
        termin["erinnerungen"] = [int(m) for m in t.get("erinnerungen") or [] if isinstance(m, (int, float))]
        termin["schreibbar"] = bool(t.get("schreibbar", True))
        return termin

    def aendern(self, kennung, beginn, aenderungen, alle_folgenden=False):
        """Ändert einen Termin (nur nach Freigabe). ``aenderungen``: titel, beginn/ende (datetime), ganztag, ort, notiz,
        kalender, erinnerung. Gibt (vorher, nachher) zurück."""
        werte = {}
        for k, v in aenderungen.items():
            werte[k] = v.strftime(ISO) if isinstance(v, datetime.datetime) else v
        daten = self._lauf("aendern", kennung, beginn.strftime(ISO), "1" if alle_folgenden else "0", json.dumps(werte))
        vorher, nachher = termine_lesen([daten.get("vorher")]), termine_lesen([daten.get("nachher")])
        if not daten.get("ok") or not nachher:
            raise KalenderFehler(ERKLAERUNG["speichern"])
        return (vorher[0] if vorher else None), nachher[0]

    def loeschen(self, kennung, beginn, alle_folgenden=False):
        """Löscht einen Termin (nur nach Freigabe; vorher sichern!)."""
        daten = self._lauf("loeschen", kennung, beginn.strftime(ISO), "1" if alle_folgenden else "0")
        if not daten.get("ok"):
            raise KalenderFehler(ERKLAERUNG["loeschen"])
