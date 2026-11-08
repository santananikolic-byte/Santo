# -*- coding: utf-8 -*-
"""Kalender - Termine aus der Kalender-App des Macs lesen, freie Zeiten finden, Termine eintragen.

Gelesen wird alles, was in der Kalender-App eingerichtet ist (iCloud vom iPhone, Google, Exchange …). Kein Passwort in
JARVIS. Der Zugriff läuft über ``osascript``; Nutzertext geht nur als Argument hinein, nie in den Skripttext.

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
    "kalender_unbekannt": "Diesen Kalender gibt es in der Kalender-App nicht.",
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

    def __init__(self, timeout=60):
        self.timeout = timeout

    @staticmethod
    def programm():
        fest = os.environ.get("JARVIS_OSASCRIPT")  # nur für Tests
        if fest:
            return fest if os.path.isfile(fest) and os.access(fest, os.X_OK) else None
        return shutil.which("osascript")

    def verfuegbar(self):
        return self.programm() is not None

    def _lauf(self, skript, *argumente):
        programm = self.programm()
        if not programm:
            raise KalenderFehler("Der Kalender ist nur auf dem Mac erreichbar (osascript fehlt hier).")
        befehl = [programm, "-l", "JavaScript", "-e", skript, ANKER] + [str(a) for a in argumente]
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
            raise KalenderFehler(ERKLAERUNG.get(daten["fehler"], "Kalenderfehler: %s" % daten["fehler"]))
        return daten

    def termine(self, von, bis, mit_kalendern=False):
        """Termine (auch die einzelnen Termine einer Serie) zwischen zwei Tagen (bis ausschließlich). Mit
        ``mit_kalendern`` zusätzlich die Kalenderliste [{"name", "schreibbar"}] und der Standardkalender."""
        daten = self._lauf(SKRIPT_TERMINE, datetime.datetime.combine(von, datetime.time()).strftime(ISO),
                           datetime.datetime.combine(bis, datetime.time()).strftime(ISO))
        termine = termine_lesen(daten.get("termine"))
        if not mit_kalendern:
            return termine
        liste = [{"name": str(k.get("name", ""))[:100], "schreibbar": bool(k.get("schreibbar"))}
                 for k in daten.get("kalender") or [] if isinstance(k, dict)]
        return termine, liste, str(daten.get("standard") or "")

    def eintragen(self, titel, beginn, ende, ganztag=False, ort="", notiz="", kalender=""):
        """Legt einen Termin ohne Teilnehmer an. Gibt den Namen des Kalenders zurück, in dem er gelandet ist."""
        daten = self._lauf(SKRIPT_EINTRAGEN, titel, beginn.strftime(ISO), ende.strftime(ISO), "1" if ganztag else "0",
                           ort, notiz, kalender)
        if not daten.get("ok"):
            raise KalenderFehler(ERKLAERUNG["speichern"])
        return str(daten.get("kalender") or kalender)


# Die Skripte laufen als JavaScript (JXA) mit EventKit - derselben Schnittstelle, die auch die Kalender-App nutzt:
# Serientermine kommen einzeln, alle Konten der Kalender-App sind dabei, die Antwort ist JSON. Nutzertext kommt nur über
# argv (erstes Argument immer "JARVIS"). Beim ersten Mal fragt macOS nach der Erlaubnis für den Kalender.
GEMEINSAM = r"""
ObjC.import("EventKit");
function text(wert) { var t = ObjC.unwrap(wert); return (t === undefined || t === null) ? "" : String(t); }
function format() {
  var f = $.NSDateFormatter.alloc.init;
  f.locale = $.NSLocale.localeWithLocaleIdentifier("en_US_POSIX");
  f.timeZone = $.NSTimeZone.localTimeZone;
  f.dateFormat = "yyyy-MM-dd'T'HH:mm:ss";
  return f;
}
function speicher() {
  var store = $.EKEventStore.alloc.init;
  var status = Number($.EKEventStore.authorizationStatusForEntityType($.EKEntityTypeEvent));
  if (status === 3) return {store: store};
  if (status !== 0) return {fehler: "zugriff_verweigert"};
  var fertig = false, erlaubt = false;
  var ende = function (ok, fehler) { erlaubt = !!ok; fertig = true; };
  if (store.respondsToSelector("requestFullAccessToEventsWithCompletion:")) {
    store.requestFullAccessToEventsWithCompletion(ende);
  } else {
    store.requestAccessToEntityTypeCompletion($.EKEntityTypeEvent, ende);
  }
  var frist = $.NSDate.dateWithTimeIntervalSinceNow(120);
  while (!fertig && Number($.NSDate.date.compare(frist)) < 0) {
    $.NSRunLoop.currentRunLoop.runUntilDate($.NSDate.dateWithTimeIntervalSinceNow(0.2));
  }
  if (!fertig) return {fehler: "zugriff_offen"};
  if (!erlaubt) return {fehler: "zugriff_verweigert"};
  return {store: $.EKEventStore.alloc.init};
}
function kalenderliste(store) {
  var alle = store.calendarsForEntityType($.EKEntityTypeEvent), liste = [];
  for (var i = 0; i < Number(alle.count); i++) {
    var k = alle.objectAtIndex(i);
    liste.push({name: text(k.title), schreibbar: !!k.allowsContentModifications, k: k});
  }
  return liste;
}
"""

SKRIPT_TERMINE = "// JARVIS:termine\n" + GEMEINSAM + r"""
function run(argv) {
  if (argv[0] !== "JARVIS") return JSON.stringify({fehler: "aufruf"});
  var s = speicher();
  if (s.fehler) return JSON.stringify({fehler: s.fehler});
  var store = s.store, f = format();
  var von = f.dateFromString(argv[1]), bis = f.dateFromString(argv[2]);
  var liste = kalenderliste(store), alle = store.calendarsForEntityType($.EKEntityTypeEvent);
  var treffer = store.eventsMatchingPredicate(store.predicateForEventsWithStartDateEndDateCalendars(von, bis, alle));
  var termine = [];
  for (var i = 0; i < Number(treffer.count) && termine.length < 300; i++) {
    var e = treffer.objectAtIndex(i);
    termine.push({titel: text(e.title), beginn: text(f.stringFromDate(e.startDate)),
                  ende: text(f.stringFromDate(e.endDate)), ganztag: !!e.allDay, ort: text(e.location),
                  kalender: text(e.calendar.title)});
  }
  var standard = store.defaultCalendarForNewEvents;
  return JSON.stringify({termine: termine, standard: standard ? text(standard.title) : "",
                         kalender: liste.map(function (k) { return {name: k.name, schreibbar: k.schreibbar}; })});
}
"""

SKRIPT_EINTRAGEN = "// JARVIS:eintragen\n" + GEMEINSAM + r"""
function run(argv) {
  if (argv[0] !== "JARVIS") return JSON.stringify({fehler: "aufruf"});
  var s = speicher();
  if (s.fehler) return JSON.stringify({fehler: s.fehler});
  var store = s.store, f = format(), ziel = null;
  var name = argv[7] || "";
  if (name) {
    var liste = kalenderliste(store);
    for (var i = 0; i < liste.length; i++) { if (liste[i].name === name) { ziel = liste[i]; break; } }
    if (!ziel) return JSON.stringify({fehler: "kalender_unbekannt"});
    if (!ziel.schreibbar) return JSON.stringify({fehler: "nur_lesen"});
    ziel = ziel.k;
  } else {
    ziel = store.defaultCalendarForNewEvents;
    if (!ziel) return JSON.stringify({fehler: "kein_kalender"});
    if (!ziel.allowsContentModifications) return JSON.stringify({fehler: "nur_lesen"});
  }
  var e = $.EKEvent.eventWithEventStore(store);
  e.title = $(argv[1]);
  e.startDate = f.dateFromString(argv[2]);
  e.endDate = f.dateFromString(argv[3]);
  e.allDay = (argv[4] === "1");
  if (argv[5]) e.location = $(argv[5]);
  if (argv[6]) e.notes = $(argv[6]);
  e.calendar = ziel;
  var fehler = Ref();
  var ok = store.saveEventSpanCommitError(e, $.EKSpanThisEvent, true, fehler);
  if (!ok) return JSON.stringify({fehler: "speichern"});
  return JSON.stringify({ok: true, kalender: text(ziel.title)});
}
"""
