#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Kalender über CalDAV - Termine lesen, Konflikte erkennen, anlegen, absagen, verschieben.

Bewusst ohne Fremdpaket: CalDAV ist HTTP mit zwei zusätzlichen Methoden. Das
spart eine Abhängigkeit, die sonst bei jeder Installation schiefgehen kann.

Die Konflikterkennung ist der eigentliche Nutzen: Termine nach Beginn sortieren
und jeden mit dem Ende des vorherigen vergleichen. Überlappt etwas, sagt Jarvis
es von sich aus - bei einem Einzelunternehmer, der selbst zu den Objekten fährt,
ist eine Doppelbuchung ein verlorener Tag.

Worauf es beim Lesen ankommt:

* **Zeiten.** Alles, was nach außen zeigt, ist lokale Zeit (Zeitzone aus
  ``CALDAV_ZEITZONE``, sonst die des Rechners). Der Kalender liefert UTC (``Z``),
  Ortszeit mit ``TZID`` (auch Windows-Namen), schwebende Zeit oder Tage ohne
  Uhrzeit; ``ics_zeit_lesen`` macht daraus immer eine einfache lokale Zeit.
  Geschrieben wird immer UTC mit ``Z`` - das versteht jeder Server gleich.
* **Serien.** Der Server wird gebeten, Serien auszudehnen (``expand``). Tut er
  es nicht, dehnt ``regel_ausdehnen`` die Wiederholungsregel selbst aus (täglich,
  wöchentlich mit Wochentagen, monatlich am Tag oder am n-ten Wochentag,
  jährlich; Intervall, Anzahl, Ende, ausgenommene Tage, einzeln geänderte oder
  abgesagte Termine). Was darüber hinausgeht, wird nicht geraten: Jarvis sagt
  es in einem Hinweis.
* **Kennungen.** Jeder gelesene Termin bekommt eine kurze ``id``. Nur mit einer
  frisch gelesenen ``id`` lässt sich etwas absagen oder verschieben - Jarvis
  soll nie einen Termin ändern, den er nicht gerade gesehen hat.

Absagen ist zurücknehmbar: Der Termin wird vor dem Löschen im Papierkorb
(Tabelle ``kalender_papierkorb``) gesichert. Gelöscht wird nur mit ``If-Match``
auf den Stand, den Jarvis gelesen hat; hat sich der Termin inzwischen geändert,
passiert nichts. Serientermine fasst Jarvis nie an.
"""

import base64
import calendar
import hashlib
import re
import threading
import urllib.error
import urllib.parse
import urllib.request
import uuid
import xml.etree.ElementTree as ET
from datetime import date, datetime, timedelta, timezone

try:
    from zoneinfo import ZoneInfo
except ImportError:  # Python 3.8 oder älter: dann gilt die Zeitzone des Rechners
    ZoneInfo = None

import config
from modules.memory import Memory, db_schema_anlegen

# Mit expand: der Server rechnet Serien selbst in einzelne Termine aus.
CALDAV_ABFRAGE = """<?xml version="1.0" encoding="utf-8" ?>
<C:calendar-query xmlns:D="DAV:" xmlns:C="urn:ietf:params:xml:ns:caldav">
  <D:prop><D:getetag/><C:calendar-data><C:expand start="%s" end="%s"/></C:calendar-data></D:prop>
  <C:filter>
    <C:comp-filter name="VCALENDAR">
      <C:comp-filter name="VEVENT">
        <C:time-range start="%s" end="%s"/>
      </C:comp-filter>
    </C:comp-filter>
  </C:filter>
</C:calendar-query>"""

# Für Server, die expand nicht können: Serien kommen unausgedehnt, Jarvis rechnet selbst.
CALDAV_ABFRAGE_OHNE_EXPAND = """<?xml version="1.0" encoding="utf-8" ?>
<C:calendar-query xmlns:D="DAV:" xmlns:C="urn:ietf:params:xml:ns:caldav">
  <D:prop><D:getetag/><C:calendar-data/></D:prop>
  <C:filter>
    <C:comp-filter name="VCALENDAR">
      <C:comp-filter name="VEVENT">
        <C:time-range start="%s" end="%s"/>
      </C:comp-filter>
    </C:comp-filter>
  </C:filter>
</C:calendar-query>"""

SCHEMA_KALENDER = """
CREATE TABLE IF NOT EXISTS kalender_papierkorb (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    href TEXT NOT NULL,
    ics TEXT NOT NULL,
    titel TEXT DEFAULT '',
    beginn TEXT DEFAULT '',
    geloescht_am TEXT NOT NULL,
    wiederhergestellt_am TEXT DEFAULT ''
);
"""

# So lange gilt eine gelesene Termin-id.
KALENDER_ID_MINUTEN = 30
KALENDER_MAX_ABSAGEN = 10

KALENDER_ERST_LESEN = ("Ich muss die Termine erst lesen – frag mich nach den Terminen, "
                       "dann sage ich dir, welche ich absagen würde.")
KALENDER_SERIE_ABGELEHNT = ("Das ist ein Serientermin. Einzelne Termine einer Serie sage ich "
                            "nicht ab – das machst du bitte im Kalender.")
KALENDER_SERIE_VERSCHIEBEN = ("Das ist ein Serientermin. Einzelne Termine einer Serie verschiebe ich "
                              "nicht – das machst du bitte im Kalender.")
KALENDER_GEAENDERT = ("Der Termin wurde inzwischen geändert – ich lösche ihn nicht. "
                      "Lies die Termine neu.")
KALENDER_GEAENDERT_VERSCHIEBEN = ("Der Termin wurde inzwischen geändert – ich verschiebe ihn nicht. "
                                  "Lies die Termine neu.")

# Windows-Namen der Zeitzonen (Outlook, Exchange) auf die Namen der Zeitzonen-Datenbank.
WINDOWS_ZEITZONEN = {
    "W. Europe Standard Time": "Europe/Berlin",
    "Central Europe Standard Time": "Europe/Budapest",
    "Central European Standard Time": "Europe/Warsaw",
    "Romance Standard Time": "Europe/Paris",
    "GMT Standard Time": "Europe/London",
    "Greenwich Standard Time": "Atlantic/Reykjavik",
    "GTB Standard Time": "Europe/Bucharest",
    "FLE Standard Time": "Europe/Kiev",
    "E. Europe Standard Time": "Europe/Chisinau",
    "Turkey Standard Time": "Europe/Istanbul",
    "Russian Standard Time": "Europe/Moscow",
    "UTC": "UTC",
    "Eastern Standard Time": "America/New_York",
    "Central Standard Time": "America/Chicago",
    "Mountain Standard Time": "America/Denver",
    "Pacific Standard Time": "America/Los_Angeles",
}

_KAL_WOCHENTAGE = {"MO": 0, "TU": 1, "WE": 2, "TH": 3, "FR": 4, "SA": 5, "SU": 6}
_KAL_TAGESNAMEN = ("Montag", "Dienstag", "Mittwoch", "Donnerstag", "Freitag", "Samstag", "Sonntag")
_KAL_REGEL_TEILE = {"FREQ", "INTERVAL", "COUNT", "UNTIL", "BYDAY", "BYMONTHDAY", "BYMONTH", "WKST"}
_kal_zonen = {}


# ---------------------------------------------------------------------------
# Zeitzonen
# ---------------------------------------------------------------------------

def kalender_zone_laden(name):
    """Die Zeitzone zu einem Namen der Zeitzonen-Datenbank oder einem Windows-Namen.

    Gibt ``None`` zurück, wenn der Name unbekannt ist - dann gilt die Zeit als lokal.
    """
    roh = str(name or "").strip().strip('"')
    if not roh:
        return None
    if roh in _kal_zonen:
        return _kal_zonen[roh]
    zone = None
    if roh.upper() in ("UTC", "GMT", "Z", "ETC/UTC"):
        zone = timezone.utc
    elif ZoneInfo is not None:
        kandidaten = [WINDOWS_ZEITZONEN.get(roh, roh)]
        if "/" in roh:  # etwa "/mozilla.org/20050126_1/Europe/Berlin"
            teile = roh.split("/")
            kandidaten += ["/".join(teile[-2:]), teile[-1]]
        for kandidat in kandidaten:
            try:
                zone = ZoneInfo(kandidat)
                break
            except Exception:
                zone = None
    _kal_zonen[roh] = zone
    return zone


def kalender_lokale_zone():
    """Die eingestellte Zeitzone - ``None`` heißt: die des Rechners."""
    name = str(config.CALDAV_ZEITZONE or "").strip()
    return kalender_zone_laden(name) if name else None


def _kal_aware_zu_lokal(zeit):
    """Eine Zeit mit Zeitzone als einfache lokale Zeit."""
    zone = kalender_lokale_zone()
    umgerechnet = zeit.astimezone(zone) if zone is not None else zeit.astimezone()
    return umgerechnet.replace(tzinfo=None)


def kalender_lokal_zu_utc(zeit):
    """Eine einfache lokale Zeit als Zeit in UTC (mit Zeitzone)."""
    zone = kalender_lokale_zone()
    if zone is not None:
        mit_zone = zeit.replace(tzinfo=zone)
    else:
        mit_zone = zeit.astimezone()  # eine einfache Zeit gilt hier als Zeit des Rechners
    return mit_zone.astimezone(timezone.utc)


def _kal_wand_zu_lokal(wand, zone):
    """Wanduhrzeit in der Zeitzone einer Serie als einfache lokale Zeit."""
    if zone is None:
        return wand
    return _kal_aware_zu_lokal(wand.replace(tzinfo=zone))


def _kal_zeit_parsen(wert, tzid=None, nur_datum=False):
    """Zerlegt eine ICS-Zeit. Gibt ``(zeit, art, zone)`` zurück.

    ``art``: ``utc``, ``zone`` (mit TZID), ``schwebend`` oder ``datum``. Bei ``utc``
    und ``zone`` trägt ``zeit`` die Zeitzone, sonst ist sie einfach.
    """
    roh = str(wert or "").strip()
    if not roh:
        return None, "", None
    utc = roh[-1:] in ("Z", "z")
    if utc:
        roh = roh[:-1]
    zeit = None
    for muster in ("%Y%m%dT%H%M%S", "%Y%m%dT%H%M", "%Y%m%d"):
        try:
            zeit = datetime.strptime(roh, muster)
            break
        except ValueError:
            continue
    if zeit is None:
        return None, "", None
    if nur_datum or len(roh) == 8:
        return zeit.replace(hour=0, minute=0, second=0), "datum", None
    if utc:
        return zeit.replace(tzinfo=timezone.utc), "utc", timezone.utc
    zone = kalender_zone_laden(tzid) if tzid else None
    if zone is not None:
        return zeit.replace(tzinfo=zone), "zone", zone
    return zeit, "schwebend", None


def ics_zeit_lesen(wert, tzid=None, nur_datum=False):
    """Liest eine ICS-Zeitangabe als einfache lokale Zeit.

    ``20261009T173000Z`` ist UTC und wird umgerechnet, ``TZID`` (auch Windows-Namen)
    ebenso; ohne beides gilt die Zeit als lokal. Ein Tag ohne Uhrzeit
    (``VALUE=DATE`` oder acht Ziffern) wird Mitternacht.
    """
    zeit, art, _ = _kal_zeit_parsen(wert, tzid, nur_datum)
    if zeit is None:
        return None
    if art in ("utc", "zone"):
        return _kal_aware_zu_lokal(zeit)
    return zeit


def ics_zeit_schreiben(zeitpunkt: datetime) -> str:
    """Schreibt einen Zeitpunkt im ICS-Format (ohne Zeitzone)."""
    return zeitpunkt.strftime("%Y%m%dT%H%M%S")


def ics_zeit_utc_schreiben(lokal: datetime) -> str:
    """Schreibt eine lokale Zeit als UTC mit ``Z``, wie sie jeder Server gleich versteht."""
    return kalender_lokal_zu_utc(lokal).strftime("%Y%m%dT%H%M%SZ")


def _kal_jetzt_utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def kalender_wann(beginn, ganztaegig=False) -> str:
    """Tag und Uhrzeit zum Vorlesen: ``Freitag, 09.10.2026 um 10:00 Uhr``."""
    tag = "%s, %s" % (_KAL_TAGESNAMEN[beginn.weekday()], beginn.strftime("%d.%m.%Y"))
    if ganztaegig:
        return "%s (ganztägig)" % tag
    return "%s um %s Uhr" % (tag, beginn.strftime("%H:%M"))


# ---------------------------------------------------------------------------
# Zeiten aus Text (Nutzereingaben)
# ---------------------------------------------------------------------------

def _kal_zeit_text_lesen(text):
    """``(zeit, mit_uhrzeit)`` aus einer Eingabe; ``(None, False)``, wenn unverständlich.

    Eine Eingabe mit Zeitzone (``Z`` oder ``+02:00``) wird in lokale Zeit umgerechnet.
    """
    roh = " ".join(str(text or "").split())
    if not roh:
        return None, False
    for muster in ("%Y-%m-%d %H:%M", "%Y-%m-%dT%H:%M", "%d.%m.%Y %H:%M", "%Y-%m-%d %H:%M:%S",
                   "%Y-%m-%dT%H:%M:%S", "%d.%m.%Y %H.%M"):
        try:
            return datetime.strptime(roh, muster), True
        except ValueError:
            continue
    for muster in ("%Y-%m-%d", "%d.%m.%Y"):
        try:
            return datetime.strptime(roh, muster), False
        except ValueError:
            continue
    try:
        zeit = datetime.fromisoformat(roh.replace("Z", "+00:00").replace("z", "+00:00"))
    except ValueError:
        return None, False
    if zeit.tzinfo is not None:
        zeit = _kal_aware_zu_lokal(zeit)
    return zeit, True


def kalender_zeit_verstehen(text):
    """Eine Zeitangabe mit Uhrzeit als einfache lokale Zeit - sonst ``None``."""
    zeit, mit_uhrzeit = _kal_zeit_text_lesen(text)
    return zeit if mit_uhrzeit else None


def kalender_tag_verstehen(text, jetzt=None):
    """``heute``, ``morgen``, ``übermorgen``, ``2026-10-09``, ``09.10.2026`` oder ``09.10.`` als Datum."""
    roh = " ".join(str(text or "").lower().split())
    heute = (jetzt or datetime.now()).date()
    if roh in ("", "heute"):
        return heute
    if roh == "morgen":
        return heute + timedelta(days=1)
    if roh in ("übermorgen", "uebermorgen"):
        return heute + timedelta(days=2)
    zeit, _ = _kal_zeit_text_lesen(roh)
    if zeit is not None:
        return zeit.date()
    treffer = re.match(r"^(\d{1,2})\.(\d{1,2})\.?$", roh)
    if treffer:
        try:
            return date(heute.year, int(treffer.group(2)), int(treffer.group(1)))
        except ValueError:
            return None
    return None


def _kal_uhrzeit_minuten(text, standard):
    """``8``, ``8:30`` oder ``08.30`` als Minuten seit Mitternacht (24:00 gilt als Tagesende)."""
    roh = str(text if text not in (None, "") else standard).strip()
    treffer = re.match(r"^(\d{1,2})(?:[:.](\d{2}))?(?:\s*uhr)?$", roh.lower())
    if not treffer:
        return None
    stunden, minuten = int(treffer.group(1)), int(treffer.group(2) or 0)
    if minuten > 59 or stunden > 24 or (stunden == 24 and minuten):
        return None
    return stunden * 60 + minuten


# ---------------------------------------------------------------------------
# ICS lesen
# ---------------------------------------------------------------------------

def ics_entfalten(rohtext: str) -> list:
    """Setzt umgebrochene ICS-Zeilen wieder zusammen (Fortsetzung beginnt mit Leerzeichen)."""
    zeilen = []
    for zeile in (rohtext or "").replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        if zeile[:1] in (" ", "\t") and zeilen:
            zeilen[-1] += zeile[1:]
        else:
            zeilen.append(zeile)
    return zeilen


def _kal_ics_text(wert: str) -> str:
    """Hebt die ICS-Maskierung auf: ``\\,`` ``\\;`` ``\\\\`` und ``\\n`` (wird ein Leerzeichen)."""
    return re.sub(r"\\(.)", lambda t: " " if t.group(1) in ("n", "N") else t.group(1),
                  wert, flags=re.S)


def _kal_ics_maskieren(wert) -> str:
    return (str(wert or "").replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,")
            .replace("\r\n", "\n").replace("\r", "\n").replace("\n", "\\n"))


def _kal_falten(zeile: str) -> str:
    """Bricht eine ICS-Zeile nach 75 Bytes um, ohne ein Zeichen zu zerschneiden."""
    if len(zeile.encode("utf-8")) <= 75:
        return zeile
    stuecke, aktuell, laenge = [], "", 0
    for zeichen in zeile:
        breite = len(zeichen.encode("utf-8"))
        if laenge + breite > 75:
            stuecke.append(aktuell)
            aktuell, laenge = " ", 1
        aktuell += zeichen
        laenge += breite
    stuecke.append(aktuell)
    return "\r\n".join(stuecke)


def _kal_teilen(text: str, trenner: str) -> list:
    """Teilt an einem Zeichen, das nicht in Anführungszeichen steht."""
    teile, aktuell, innen = [], "", False
    for zeichen in text:
        if zeichen == '"':
            innen = not innen
        if zeichen == trenner and not innen:
            teile.append(aktuell)
            aktuell = ""
        else:
            aktuell += zeichen
    teile.append(aktuell)
    return teile


def _kal_zeile_zerlegen(zeile: str):
    """``DTSTART;TZID=Europe/Vienna:20261009T093000`` wird ``(name, parameter, wert)``."""
    innen, trenn = False, -1
    for stelle, zeichen in enumerate(zeile):
        if zeichen == '"':
            innen = not innen
        elif zeichen == ":" and not innen:
            trenn = stelle
            break
    if trenn < 0:
        return None
    teile = _kal_teilen(zeile[:trenn], ";")
    parameter = {}
    for teil in teile[1:]:
        if "=" in teil:
            schluessel, _, wert = teil.partition("=")
            parameter[schluessel.strip().upper()] = wert.strip().strip('"')
    return teile[0].strip().upper(), parameter, zeile[trenn + 1:]


def _kal_dauer_lesen(wert: str):
    """Liest eine ICS-Dauer wie ``PT1H30M`` oder ``P1D``."""
    treffer = re.match(r"^([+-])?P(?:(\d+)W)?(?:(\d+)D)?(?:T(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?)?$",
                       str(wert or "").strip().upper())
    if not treffer:
        return None
    vorzeichen, wochen, tage, stunden, minuten, sekunden = treffer.groups()
    dauer = timedelta(weeks=int(wochen or 0), days=int(tage or 0), hours=int(stunden or 0),
                      minutes=int(minuten or 0), seconds=int(sekunden or 0))
    return -dauer if vorzeichen == "-" else dauer


def _kal_neuer_termin() -> dict:
    return {"titel": "", "ort": "", "beginn": None, "ende": None, "beschreibung": "", "uid": "",
            "ganztaegig": False, "serie": False, "rrule": "", "ausnahmen": [],
            "wiederholung_von": None, "status": "", "frei": False,
            "href": "", "etag": "", "id": "",
            "_zone": None, "_beginn_wand": None, "_beginn_roh": None, "_ende_roh": None,
            "_dauer": None, "_ausnahmen_roh": [], "_rid_roh": None}


def _kal_in_wand(zeit, art, zone, uhrzeit=None):
    """Eine gelesene Zeit als Wanduhrzeit in der Zeitzone einer Serie.

    Ein Tag ohne Uhrzeit (``EXDATE;VALUE=DATE``) meint bei einer Serie mit Uhrzeit
    den Termin dieses Tages: ``uhrzeit`` ist die Uhrzeit der Serie.
    """
    if art == "datum" and uhrzeit is not None:
        return datetime.combine(zeit.date(), uhrzeit)
    if art in ("utc", "zone"):
        if zone is not None:
            return zeit.astimezone(zone).replace(tzinfo=None)
        return _kal_aware_zu_lokal(zeit)
    return zeit


def _kal_termin_abschliessen(termin: dict):
    """Rechnet die gelesenen Rohwerte eines Termins in lokale Zeit um."""
    zeit, art, zone = termin["_beginn_roh"]
    termin["_zone"] = zone if art in ("utc", "zone") else None
    termin["_beginn_wand"] = zeit.replace(tzinfo=None)
    termin["beginn"] = _kal_aware_zu_lokal(zeit) if art in ("utc", "zone") else zeit
    termin["ganztaegig"] = art == "datum"
    ende = None
    if termin["_ende_roh"] is not None:
        ende_zeit, ende_art, _ = termin["_ende_roh"]
        ende = _kal_aware_zu_lokal(ende_zeit) if ende_art in ("utc", "zone") else ende_zeit
    elif termin["_dauer"] is not None:
        ende = termin["beginn"] + termin["_dauer"]
    if ende is None or ende < termin["beginn"]:
        ende = termin["beginn"] + (timedelta(days=1) if termin["ganztaegig"] else timedelta(hours=1))
    termin["ende"] = ende
    uhrzeit = None if termin["ganztaegig"] else termin["_beginn_wand"].time()
    for roh_zeit, roh_art in termin["_ausnahmen_roh"]:
        termin["ausnahmen"].append(_kal_in_wand(roh_zeit, roh_art, termin["_zone"], uhrzeit))
    termin["serie"] = bool(termin["rrule"]) or termin["_rid_roh"] is not None


def ics_termine_lesen(rohtext: str, von=None, bis=None) -> list:
    """Zieht alle VEVENT-Blöcke aus einem ICS-Text.

    Zeiten kommen als einfache lokale Zeit. Abgesagte Termine (``STATUS:CANCELLED``)
    fehlen; ein abgesagter oder einzeln geänderter Termin einer Serie nimmt diesen
    Tag aus der Serie heraus. Mit ``von`` und ``bis`` (lokale Zeit) werden Serien,
    die der Server nicht ausgedehnt hat, selbst ausgedehnt; ohne bleibt die Serie
    ein einzelner Termin (der erste).
    """
    termine, ausgenommen = [], []  # ausgenommen: (uid, rohzeit, art) abgesagter oder geänderter Tage
    aktuell, tiefe = None, 0
    for zeile in ics_entfalten(rohtext):
        blank = zeile.strip()
        oben = blank.upper()
        if aktuell is None:
            if oben == "BEGIN:VEVENT":
                aktuell, tiefe = _kal_neuer_termin(), 0
            continue
        if oben.startswith("BEGIN:"):  # etwa ein VALARM: dessen Zeilen gehören nicht dem Termin
            tiefe += 1
            continue
        if oben == "END:VEVENT" and tiefe == 0:
            fertig, aktuell = aktuell, None
            if fertig["_beginn_roh"] is None:
                continue
            if fertig["_rid_roh"] is not None:
                ausgenommen.append((fertig["uid"], fertig["_rid_roh"]))
            if fertig["status"] == "CANCELLED":
                continue
            _kal_termin_abschliessen(fertig)
            termine.append(fertig)
            continue
        if oben.startswith("END:"):
            tiefe -= 1
            continue
        if tiefe > 0 or ":" not in blank:
            continue
        zerlegt = _kal_zeile_zerlegen(blank)
        if zerlegt is None:
            continue
        name, parameter, wert = zerlegt
        tzid = parameter.get("TZID")
        nur_datum = parameter.get("VALUE", "").upper() == "DATE"
        if name == "SUMMARY":
            aktuell["titel"] = _kal_ics_text(wert)
        elif name == "LOCATION":
            aktuell["ort"] = _kal_ics_text(wert)
        elif name == "DESCRIPTION":
            aktuell["beschreibung"] = _kal_ics_text(wert)
        elif name == "UID":
            aktuell["uid"] = wert.strip()
        elif name == "STATUS":
            aktuell["status"] = wert.strip().upper()
        elif name == "TRANSP":
            aktuell["frei"] = wert.strip().upper() == "TRANSPARENT"
        elif name == "RRULE":
            aktuell["rrule"] = wert.strip()
        elif name == "DTSTART":
            gelesen = _kal_zeit_parsen(wert, tzid, nur_datum)
            if gelesen[0] is not None:
                aktuell["_beginn_roh"] = gelesen
        elif name == "DTEND":
            gelesen = _kal_zeit_parsen(wert, tzid, nur_datum)
            if gelesen[0] is not None:
                aktuell["_ende_roh"] = gelesen
        elif name == "DURATION":
            aktuell["_dauer"] = _kal_dauer_lesen(wert)
        elif name == "RECURRENCE-ID":
            gelesen = _kal_zeit_parsen(wert, tzid, nur_datum)
            if gelesen[0] is not None:
                aktuell["_rid_roh"] = (gelesen[0], gelesen[1])
        elif name == "EXDATE":
            for einzel in wert.split(","):
                gelesen = _kal_zeit_parsen(einzel, tzid, nur_datum)
                if gelesen[0] is not None:
                    aktuell["_ausnahmen_roh"].append((gelesen[0], gelesen[1]))

    # Geänderte und abgesagte Tage einer Serie: gehören nicht mehr zur Regel.
    for termin in termine:
        if termin["rrule"] and termin["_rid_roh"] is None:
            for uid, (roh_zeit, roh_art) in ausgenommen:
                if uid and uid == termin["uid"]:
                    uhrzeit = None if termin["ganztaegig"] else termin["_beginn_wand"].time()
                    termin["ausnahmen"].append(_kal_in_wand(roh_zeit, roh_art, termin["_zone"], uhrzeit))

    if von is not None and bis is not None:
        ausgedehnt = []
        for termin in termine:
            if termin["rrule"] and termin["_rid_roh"] is None:
                ausgedehnt.extend(kalender_serie_ausdehnen(termin, von, bis))
            else:
                ausgedehnt.append(termin)
        termine = ausgedehnt
    return sorted(termine, key=lambda t: (t["beginn"], t["titel"]))


# ---------------------------------------------------------------------------
# Wiederholungsregeln (RRULE)
# ---------------------------------------------------------------------------

def _kal_regel_lesen(rrule) -> dict:
    teile = {}
    for stueck in str(rrule or "").strip().split(";"):
        if "=" in stueck:
            schluessel, _, wert = stueck.partition("=")
            teile[schluessel.strip().upper()] = wert.strip()
    return teile


def _kal_byday_lesen(wert):
    """``MO,WE`` oder ``2TU,-1FR`` als Liste von ``(Nummer oder None, Wochentag)``; ``None`` bei Unsinn."""
    ergebnis = []
    for stueck in str(wert or "").upper().split(","):
        treffer = re.match(r"^([+-]?\d{1,2})?(MO|TU|WE|TH|FR|SA|SU)$", stueck.strip())
        if not treffer:
            return None
        nummer = int(treffer.group(1)) if treffer.group(1) else None
        ergebnis.append((nummer, _KAL_WOCHENTAGE[treffer.group(2)]))
    return ergebnis


def _kal_zahlen_lesen(wert, kleinste, groesste):
    ergebnis = []
    for stueck in str(wert or "").split(","):
        try:
            zahl = int(stueck.strip())
        except ValueError:
            return None
        if zahl == 0 or abs(zahl) > groesste or zahl < kleinste:
            return None
        ergebnis.append(zahl)
    return ergebnis


def regel_pruefen(rrule):
    """Kann ``regel_ausdehnen`` diese Regel? Gibt ``(ja, hinweis)`` zurück."""
    regel = _kal_regel_lesen(rrule)
    frei = regel.get("FREQ", "").upper()
    if frei not in ("DAILY", "WEEKLY", "MONTHLY", "YEARLY"):
        return False, "eine Wiederholung (%s), die ich nicht ausrechnen kann" % (frei or "ohne Angabe")
    fremd = sorted(k for k in regel if k not in _KAL_REGEL_TEILE)
    if fremd:
        return False, "eine Wiederholung mit %s, die ich nicht ausrechnen kann" % ", ".join(fremd)
    for name in ("INTERVAL", "COUNT"):
        if name in regel and not re.match(r"^\d+$", regel[name]):
            return False, "eine Wiederholung mit unklarem %s" % name
    byday = None
    if "BYDAY" in regel:
        byday = _kal_byday_lesen(regel["BYDAY"])
        if byday is None:
            return False, "eine Wiederholung mit unklarem BYDAY"
        if any(n is not None for n, _ in byday) and frei not in ("MONTHLY", "YEARLY"):
            return False, "eine Wiederholung mit Wochentag-Nummer, die ich nicht ausrechnen kann"
        if frei == "YEARLY" and "BYMONTH" not in regel and any(n is not None for n, _ in byday):
            return False, "eine jährliche Wiederholung am n-ten Wochentag des Jahres"
    if "BYMONTHDAY" in regel:
        if frei in ("WEEKLY",) or _kal_zahlen_lesen(regel["BYMONTHDAY"], -31, 31) is None:
            return False, "eine Wiederholung mit BYMONTHDAY, die ich nicht ausrechnen kann"
    if "BYMONTH" in regel and _kal_zahlen_lesen(regel["BYMONTH"], 1, 12) is None:
        return False, "eine Wiederholung mit unklarem BYMONTH"
    if "WKST" in regel and regel["WKST"].upper() not in _KAL_WOCHENTAGE:
        return False, "eine Wiederholung mit unklarem WKST"
    return True, ""


def _kal_tage_im_monat(jahr, monat, monatstage, wochentage):
    """Die gemeinten Tage eines Monats: nach Monatstag, nach (n-tem) Wochentag oder beides zugleich."""
    letzter = calendar.monthrange(jahr, monat)[1]
    nach_monatstag = None
    if monatstage:
        nach_monatstag = set()
        for tag in monatstage:
            nummer = tag if tag > 0 else letzter + tag + 1
            if 1 <= nummer <= letzter:
                nach_monatstag.add(nummer)
    nach_wochentag = None
    if wochentage:
        nach_wochentag = set()
        for nummer, wochentag in wochentage:
            passende = [t for t in range(1, letzter + 1)
                        if date(jahr, monat, t).weekday() == wochentag]
            if nummer is None:
                nach_wochentag.update(passende)
            elif nummer > 0 and nummer <= len(passende):
                nach_wochentag.add(passende[nummer - 1])
            elif nummer < 0 and -nummer <= len(passende):
                nach_wochentag.add(passende[nummer])
    if nach_monatstag is not None and nach_wochentag is not None:
        tage = nach_monatstag & nach_wochentag
    else:
        tage = nach_monatstag if nach_monatstag is not None else (nach_wochentag or set())
    return [date(jahr, monat, t) for t in sorted(tage)]


def _kal_periode_tage(frei, start, periode, takt, wochentage, monatstage, monate, wochenanfang):
    """Alle Tage, die die Regel in der ``periode``-ten Runde trifft (sortiert)."""
    if frei == "DAILY":
        tag = start + timedelta(days=periode * takt)
        if wochentage and tag.weekday() not in {w for _, w in wochentage}:
            return []
        if monatstage:
            letzter = calendar.monthrange(tag.year, tag.month)[1]
            if tag.day not in monatstage and tag.day - letzter - 1 not in monatstage:
                return []
        if monate and tag.month not in monate:
            return []
        return [tag]
    if frei == "WEEKLY":
        woche = start - timedelta(days=(start.weekday() - wochenanfang) % 7) \
            + timedelta(weeks=periode * takt)
        tage_der_woche = sorted({w for _, w in wochentage}) if wochentage else [start.weekday()]
        tage = [woche + timedelta(days=(w - wochenanfang) % 7) for w in tage_der_woche]
        if monate:
            tage = [t for t in tage if t.month in monate]
        return sorted(tage)
    if frei == "MONTHLY":
        jahr, monat0 = divmod(start.year * 12 + (start.month - 1) + periode * takt, 12)
        monat = monat0 + 1
        if monate and monat not in monate:
            return []
        if not wochentage and not monatstage:
            return _kal_tage_im_monat(jahr, monat, [start.day], None)
        return _kal_tage_im_monat(jahr, monat, monatstage, wochentage)
    # YEARLY
    jahr = start.year + periode * takt
    tage = []
    for monat in (monate or [start.month]):
        if wochentage:
            tage += _kal_tage_im_monat(jahr, monat, monatstage, wochentage)
        else:
            tage += _kal_tage_im_monat(jahr, monat, monatstage or [start.day], None)
    return sorted(tage)


def regel_ausdehnen(beginn, rrule, exdates=None, von=None, bis=None, umrechnen=None, maximal=1000):
    """Rechnet eine Wiederholungsregel in einzelne Beginnzeiten aus.

    ``beginn``: Wanduhrzeit des ersten Termins (einfach). ``exdates``: ausgenommene
    Beginnzeiten in derselben Wanduhrzeit. ``von`` und ``bis``: Fenster in lokaler
    Zeit (``von`` eingeschlossen, ``bis`` ausgeschlossen). ``umrechnen``: macht aus
    der Wanduhrzeit der Serie eine lokale Zeit (nur nötig, wenn die Serie in einer
    anderen Zeitzone läuft). Gibt lokale Beginnzeiten zurück.

    Unterstützt: DAILY, WEEKLY (BYDAY), MONTHLY (BYMONTHDAY oder n-ter Wochentag),
    YEARLY, dazu INTERVAL, COUNT, UNTIL, BYMONTH. Bei allem anderen (BYSETPOS,
    BYWEEKNO ...) kommt nur der erste Termin zurück - ``regel_pruefen`` sagt vorher,
    ob das der Fall ist.
    """
    umr = umrechnen or (lambda wand: wand)
    ja, _ = regel_pruefen(rrule)
    if not ja:
        return [umr(beginn)]
    regel = _kal_regel_lesen(rrule)
    frei = regel["FREQ"].upper()
    takt = max(1, int(regel.get("INTERVAL") or 1))
    anzahl = int(regel["COUNT"]) if regel.get("COUNT") and int(regel["COUNT"]) > 0 else None
    wochentage = _kal_byday_lesen(regel["BYDAY"]) if regel.get("BYDAY") else None
    monatstage = _kal_zahlen_lesen(regel["BYMONTHDAY"], -31, 31) if regel.get("BYMONTHDAY") else None
    monate = _kal_zahlen_lesen(regel["BYMONTH"], 1, 12) if regel.get("BYMONTH") else None
    wochenanfang = _KAL_WOCHENTAGE.get(regel.get("WKST", "MO").upper(), 0)

    ende_regel, ende_einschliesslich = None, True
    if regel.get("UNTIL"):
        zeit, art, _ = _kal_zeit_parsen(regel["UNTIL"])
        if zeit is not None:
            if art == "datum":  # "bis zu diesem Tag" gilt bis Tagesende
                ende_regel, ende_einschliesslich = zeit + timedelta(days=1), False
            else:
                ende_regel = _kal_aware_zu_lokal(zeit) if art in ("utc", "zone") else zeit
    obergrenze = bis + timedelta(days=2) if bis is not None else None
    ausnahmen = set(exdates or [])
    uhrzeit = beginn.time()
    start = beginn.date()
    ergebnis, gezaehlt = [], 0
    for periode in range(20000):
        try:
            tage = _kal_periode_tage(frei, start, periode, takt, wochentage, monatstage, monate,
                                     wochenanfang)
        except (OverflowError, ValueError):
            break
        if periode == 0 and start not in tage:
            tage = sorted(tage + [start])  # der erste Termin gehört immer dazu
        for tag in tage:
            wand = datetime.combine(tag, uhrzeit)
            if wand < beginn:
                continue
            gezaehlt += 1
            if anzahl is not None and gezaehlt > anzahl:
                return ergebnis
            lokal = umr(wand)
            if ende_regel is not None and (lokal > ende_regel if ende_einschliesslich
                                           else lokal >= ende_regel):
                return ergebnis
            if obergrenze is not None and wand > obergrenze:
                return ergebnis
            if wand in ausnahmen:
                continue
            if (von is None or lokal >= von) and (bis is None or lokal < bis):
                ergebnis.append(lokal)
                if len(ergebnis) >= maximal:
                    return ergebnis
    return ergebnis


def kalender_serie_ausdehnen(termin: dict, von, bis, hinweise=None) -> list:
    """Macht aus einer Serie die Einzeltermine, die ins Fenster ``[von, bis)`` fallen.

    Kann die Regel nicht ausgerechnet werden, kommt nur der erste Termin (wenn er im
    Fenster liegt) und ``hinweise`` (eine Liste, falls übergeben) bekommt einen Satz dazu.
    """
    dauer = termin["ende"] - termin["beginn"]
    zone = termin.get("_zone")
    ja, grund = regel_pruefen(termin["rrule"])
    if ja:
        starts = regel_ausdehnen(termin["_beginn_wand"], termin["rrule"], termin["ausnahmen"],
                                 von - dauer, bis, lambda wand: _kal_wand_zu_lokal(wand, zone))
    else:
        starts = [termin["beginn"]]
        if hinweise is not None:
            hinweise.append("Die Serie „%s“ hat %s. Gezeigt ist nur der erste Termin, "
                            "bitte schau im Kalender nach." % (termin["titel"] or "ohne Titel", grund))
    ergebnis = []
    for beginn in starts:
        if beginn + dauer <= von and not (dauer == timedelta(0) and beginn == von):
            continue
        if beginn >= bis:
            continue
        einzel = dict(termin)
        einzel["ausnahmen"] = []
        einzel["beginn"], einzel["ende"] = beginn, beginn + dauer
        einzel["serie"] = True
        einzel["wiederholung_von"] = beginn
        ergebnis.append(einzel)
    return ergebnis


# ---------------------------------------------------------------------------
# Antwort des Servers (Multistatus)
# ---------------------------------------------------------------------------

def multistatus_lesen(inhalt: str) -> list:
    """Liest eine CalDAV-Antwort. Gibt ``[{"href", "etag", "ics"}]`` zurück."""
    text = inhalt or ""
    eintraege = []
    try:
        wurzel = ET.fromstring(text)
    except (ET.ParseError, ValueError):
        wurzel = None
    if wurzel is None:
        # Kein sauberes XML: wenigstens die Kalenderblöcke retten (ohne Adresse und Stand).
        for block in re.findall(r"BEGIN:VCALENDAR.*?END:VCALENDAR", text, re.S):
            entschaerft = block.replace("&#13;", "").replace("&lt;", "<").replace("&gt;", ">") \
                               .replace("&amp;", "&")
            eintraege.append({"href": "", "etag": "", "ics": entschaerft})
        return eintraege
    dav, caldav = "{DAV:}", "{urn:ietf:params:xml:ns:caldav}"
    for antwort in wurzel.iter(dav + "response"):
        href = (antwort.findtext(dav + "href") or "").strip()
        etag, ics = "", ""
        for eigenschaften in antwort.iter(dav + "propstat"):
            status = eigenschaften.findtext(dav + "status") or ""
            if status and " 200" not in status:
                continue
            etag = etag or (eigenschaften.findtext(".//" + dav + "getetag") or "").strip()
            ics = ics or (eigenschaften.findtext(".//" + caldav + "calendar-data") or "").strip()
        if ics and "BEGIN:VCALENDAR" in ics:
            eintraege.append({"href": href, "etag": etag, "ics": ics})
    return eintraege


def _kal_etag(etag):
    """Der Stand so, wie ihn ``If-Match`` braucht: in Anführungszeichen, nie schwach."""
    roh = str(etag or "").strip()
    if roh.startswith(("W/", "w/")):
        roh = roh[2:]
    if not roh:
        return ""
    return roh if roh.startswith('"') else '"%s"' % roh


def konflikte_finden(termine: list) -> list:
    """Findet Überschneidungen: nach Beginn sortieren, mit dem vorigen Ende vergleichen.

    Ganztägige Termine (Feiertag, Geburtstag) und solche, die als frei eingetragen
    sind, blockieren nichts und zählen nicht mit.
    """
    sortiert = sorted([t for t in termine if t.get("beginn") and t.get("ende")
                       and not t.get("ganztaegig") and not t.get("frei")],
                      key=lambda t: t["beginn"])
    konflikte = []
    for index in range(1, len(sortiert)):
        vorher = sortiert[index - 1]
        jetzt = sortiert[index]
        if jetzt["beginn"] < vorher["ende"]:
            ueberlappung = (min(vorher["ende"], jetzt["ende"]) - jetzt["beginn"])
            konflikte.append({
                "erster": vorher["titel"], "zweiter": jetzt["titel"],
                "beginn": jetzt["beginn"].strftime("%d.%m. %H:%M"),
                "minuten": int(ueberlappung.total_seconds() // 60),
                "text": "%s und %s überschneiden sich am %s um %d Minuten."
                        % (vorher["titel"] or "Ein Termin", jetzt["titel"] or "ein Termin",
                           jetzt["beginn"].strftime("%d.%m. um %H:%M"),
                           int(ueberlappung.total_seconds() // 60))})
    return konflikte


def kalender_freie_luecken(belegt: list, fenster_von, fenster_bis, mindestens_minuten: int = 60) -> list:
    """Die Lücken zwischen belegten Zeiten, mindestens so lang wie verlangt.

    ``belegt``: Liste von ``(beginn, ende)``; Überlappendes und Aneinanderstoßendes
    wird zusammengelegt. Gibt ``[(von, bis)]`` zurück.
    """
    zusammen = []
    for beginn, ende in sorted((max(b, fenster_von), min(e, fenster_bis)) for b, e in belegt):
        if ende <= beginn:
            continue
        if zusammen and beginn <= zusammen[-1][1]:
            zusammen[-1] = (zusammen[-1][0], max(zusammen[-1][1], ende))
        else:
            zusammen.append((beginn, ende))
    luecken, cursor = [], fenster_von
    for beginn, ende in zusammen + [(fenster_bis, fenster_bis)]:
        if beginn - cursor >= timedelta(minutes=max(1, mindestens_minuten)):
            luecken.append((cursor, beginn))
        cursor = max(cursor, ende)
    return luecken


def ics_zeit_ersetzen(rohtext: str, beginn, ende, ganztaegig: bool = False):
    """Ersetzt Beginn und Ende des Termins in einem ICS-Text, alles andere bleibt.

    ``beginn`` und ``ende`` sind lokale Zeit; geschrieben wird UTC mit ``Z`` (bei
    ganztägigen Terminen der Tag). Eine Dauer-Angabe fällt weg, ``SEQUENCE`` zählt
    hoch. Gibt den neuen Text zurück.
    """
    if ganztaegig:
        neu_beginn = "DTSTART;VALUE=DATE:%s" % beginn.strftime("%Y%m%d")
        neu_ende = "DTEND;VALUE=DATE:%s" % ende.strftime("%Y%m%d")
    else:
        neu_beginn = "DTSTART:%s" % ics_zeit_utc_schreiben(beginn)
        neu_ende = "DTEND:%s" % ics_zeit_utc_schreiben(ende)
    ausgabe, im_termin, tiefe = [], False, 0
    eingefuegt = sequenz_gesehen = False
    for zeile in ics_entfalten(rohtext):
        if not zeile.strip():
            continue
        oben = zeile.strip().upper()
        if not im_termin:
            ausgabe.append(zeile)
            if oben == "BEGIN:VEVENT":
                im_termin, tiefe = True, 0
            continue
        if oben.startswith("BEGIN:"):
            tiefe += 1
            ausgabe.append(zeile)
            continue
        if oben == "END:VEVENT" and tiefe == 0:
            if not eingefuegt:
                ausgabe.extend([neu_beginn, neu_ende])
            if not sequenz_gesehen:
                ausgabe.append("SEQUENCE:1")
            ausgabe.append(zeile)
            im_termin = False
            continue
        if oben.startswith("END:"):
            tiefe -= 1
            ausgabe.append(zeile)
            continue
        if tiefe > 0:
            ausgabe.append(zeile)
            continue
        name = oben.split(":", 1)[0].split(";", 1)[0]
        if name == "DTSTART":
            if not eingefuegt:
                ausgabe.extend([neu_beginn, neu_ende])
                eingefuegt = True
            continue
        if name in ("DTEND", "DURATION"):
            continue
        if name == "SEQUENCE":
            sequenz_gesehen = True
            try:
                zahl = int(zeile.split(":", 1)[1].strip()) + 1
            except (IndexError, ValueError):
                zahl = 1
            ausgabe.append("SEQUENCE:%d" % zahl)
            continue
        if name == "DTSTAMP":
            ausgabe.append("DTSTAMP:%s" % _kal_jetzt_utc())
            continue
        ausgabe.append(zeile)
    return "\r\n".join(_kal_falten(z) for z in ausgabe) + "\r\n"


# ---------------------------------------------------------------------------
# Der Kalender
# ---------------------------------------------------------------------------

class Kalender:
    """CalDAV-Zugriff: Termine lesen, anlegen, absagen, verschieben, wiederherstellen.

    ``memory``: das Gedächtnis (darin liegt der Papierkorb); ohne wird bei Bedarf eines
    angelegt. ``anfrage``: Ersatz für den HTTP-Aufruf ``(methode, url, koerper, zusatz)``
    -> ``(status, text)`` oder ``(status, text, kopfzeilen)`` - für Prüfungen ohne Netz.
    ``uhr``: liefert die lokale Zeit (``datetime``) - ebenfalls für Prüfungen.
    """

    def __init__(self, memory=None, anfrage=None, uhr=None):
        self.letzter_fehler = ""
        self.memory = memory
        self._uhr = uhr or datetime.now
        if anfrage is not None:
            self._anfrage = anfrage
        self._sperre = threading.Lock()
        self._ids = {}
        self._schema_pfad = None

    def verfuegbar(self) -> bool:
        """Ist ein Kalender hinterlegt?"""
        return bool(config.CALDAV_URL and config.CALDAV_USER)

    def zustand(self) -> dict:
        """Kurzer Überblick für den Selbsttest."""
        return {"eingerichtet": self.verfuegbar(),
                "url": config.CALDAV_URL or "nicht gesetzt",
                "kalender": config.CALDAV_KALENDER or "",
                "zeitzone": config.CALDAV_ZEITZONE or "Zeitzone des Rechners"}

    def kalender_url(self) -> str:
        """Die Adresse des Kalenders, aus dem gelesen und in den geschrieben wird.

        ``CALDAV_KALENDER`` kann eine ganze Adresse sein (beginnt mit http) oder
        der Name des Kalenders unterhalb von ``CALDAV_URL``.
        """
        basis = (config.CALDAV_URL or "").strip()
        name = (config.CALDAV_KALENDER or "").strip()
        if not name:
            return basis
        if name.lower().startswith("http"):
            return name
        return basis.rstrip("/") + "/" + urllib.parse.quote(name) + "/"

    def _url_zu(self, href: str) -> str:
        """Macht aus der Adresse eines Termins (oft nur ein Pfad) eine vollständige."""
        return urllib.parse.urljoin(self.kalender_url(), href or "")

    def _kopfzeilen(self, zusatz: dict = None) -> dict:
        """Basic-Auth und Standardköpfe."""
        zugang = base64.b64encode(
            ("%s:%s" % (config.CALDAV_USER, config.CALDAV_PASSWORT)).encode("utf-8")
        ).decode("ascii")
        kopf = {"Authorization": "Basic %s" % zugang, "User-Agent": "Jarvis/1.0"}
        kopf.update(zusatz or {})
        return kopf

    @staticmethod
    def _gleicher_dienst(alt: str, neu: str) -> bool:
        """Darf eine Weiterleitung die Zugangsdaten mitnehmen? Nur innerhalb derselben Adresse."""
        a, n = urllib.parse.urlsplit(alt), urllib.parse.urlsplit(neu)
        if n.scheme != "https" and n.scheme != a.scheme:
            return False
        host_a, host_n = (a.hostname or "").lower(), (n.hostname or "").lower()
        if not host_a or not host_n:
            return False
        if host_a == host_n:
            return True
        if not re.search(r"[a-z]", host_a + host_n):  # Zahlenadressen nur, wenn sie gleich sind
            return False
        return host_a.split(".")[-2:] == host_n.split(".")[-2:]

    def _anfrage(self, methode: str, url: str, koerper: str = "", zusatz: dict = None):
        """Führt eine HTTP-Anfrage mit beliebiger Methode aus (auch REPORT).

        Gibt ``(status, text, kopfzeilen)`` zurück; die Kopfzeilen sind klein geschrieben.
        """
        for _ in range(4):
            anfrage = urllib.request.Request(
                url, data=(koerper or "").encode("utf-8") if koerper else None,
                method=methode, headers=self._kopfzeilen(zusatz))
            try:
                with urllib.request.urlopen(anfrage, timeout=30) as antwort:
                    kopf = {k.lower(): v for k, v in antwort.headers.items()}
                    return antwort.status, antwort.read().decode("utf-8", errors="replace"), kopf
            except urllib.error.HTTPError as fehler:
                kopf = {k.lower(): v for k, v in (fehler.headers or {}).items()}
                ziel = urllib.parse.urljoin(url, kopf.get("location", "")) if kopf.get("location") else ""
                if fehler.code in (301, 302, 307, 308) and ziel and self._gleicher_dienst(url, ziel):
                    fehler.close()
                    url = ziel
                    continue
                return fehler.code, fehler.read().decode("utf-8", errors="replace"), kopf
            except (urllib.error.URLError, OSError) as fehler:
                self.letzter_fehler = str(fehler)
                return 0, str(fehler), {}
        return 0, "Zu viele Weiterleitungen.", {}

    def _senden(self, methode: str, url: str, koerper: str = "", zusatz: dict = None):
        """Ruft ``_anfrage`` auf und gibt immer ``(status, text, kopfzeilen)`` zurück."""
        try:
            antwort = self._anfrage(methode, url, koerper, zusatz)
        except Exception as fehler:
            self.letzter_fehler = str(fehler)
            return 0, str(fehler), {}
        status = antwort[0] if antwort else 0
        text = antwort[1] if len(antwort) > 1 else ""
        kopf = antwort[2] if len(antwort) > 2 and isinstance(antwort[2], dict) else {}
        return status, str(text or ""), {str(k).lower(): v for k, v in kopf.items()}

    # -- Lesen --------------------------------------------------------------

    def _termine_holen(self, von, bis):
        """Liest die Termine, die das Fenster ``[von, bis)`` (lokale Zeit) berühren.

        Gibt ``(termine, fehler, hinweise)`` zurück; bei einem Fehler ist ``termine`` ``None``.
        """
        start = ics_zeit_utc_schreiben(von)
        ende = ics_zeit_utc_schreiben(bis)
        kopf = {"Depth": "1", "Content-Type": "application/xml; charset=utf-8"}
        status, inhalt, _ = self._senden("REPORT", self.kalender_url(),
                                         CALDAV_ABFRAGE % (start, ende, start, ende), kopf)
        if status in (400, 415, 422, 500, 501):  # dieser Server kann expand nicht
            status, inhalt, _ = self._senden("REPORT", self.kalender_url(),
                                             CALDAV_ABFRAGE_OHNE_EXPAND % (start, ende), kopf)
        if status == 0:
            return None, "Der Kalender ist nicht erreichbar: %s" % inhalt, []
        if status == 401:
            return None, "Der Kalender lehnt Benutzer oder Passwort ab.", []
        if status == 404:
            return None, ("Der Kalender wurde unter dieser Adresse nicht gefunden (Fehler 404). "
                          "Bitte CALDAV_URL und CALDAV_KALENDER prüfen."), []
        if status >= 400:
            return None, "Der Kalender antwortet mit Fehler %d." % status, []

        hinweise, alle = [], []
        for eintrag in multistatus_lesen(inhalt):
            for termin in ics_termine_lesen(eintrag["ics"]):
                if termin["rrule"] and termin["_rid_roh"] is None:
                    treffer = kalender_serie_ausdehnen(termin, von, bis, hinweise)
                else:
                    treffer = [termin] if (termin["ende"] > von or termin["beginn"] >= von) \
                        and termin["beginn"] < bis else []
                for einzel in treffer:
                    einzel["href"], einzel["etag"] = eintrag["href"], eintrag["etag"]
                    alle.append(einzel)
        gesehen, eindeutig = set(), []
        for termin in sorted(alle, key=lambda t: (t["beginn"], t["titel"])):
            schluessel = (termin["href"], termin["uid"], termin["beginn"])
            if schluessel in gesehen:
                continue
            gesehen.add(schluessel)
            eindeutig.append(termin)
        return eindeutig, "", list(dict.fromkeys(hinweise))

    def _id_zu(self, termin: dict) -> str:
        """Die kurze Kennung eines gelesenen Termins: Anfang von sha1(Adresse + Beginn)."""
        grundlage = "%s%s" % (termin.get("href") or termin.get("uid") or "",
                              termin["beginn"].strftime("%Y%m%dT%H%M%S"))
        return hashlib.sha1(grundlage.encode("utf-8")).hexdigest()[:8]

    def _ids_merken(self, termine: list):
        jetzt = self._uhr()
        with self._sperre:
            for kennung, eintrag in list(self._ids.items()):
                if jetzt - eintrag["gelesen"] > timedelta(minutes=KALENDER_ID_MINUTEN):
                    del self._ids[kennung]
            for termin in termine:
                termin["id"] = self._id_zu(termin)
                self._ids[termin["id"]] = {"termin": termin, "gelesen": jetzt}

    def _termin_zur_id(self, kennung):
        """Der Termin zu einer frisch gelesenen Kennung - sonst ``None``."""
        jetzt = self._uhr()
        with self._sperre:
            eintrag = self._ids.get(str(kennung or "").strip())
            if eintrag is None:
                return None
            if jetzt - eintrag["gelesen"] > timedelta(minutes=KALENDER_ID_MINUTEN):
                del self._ids[str(kennung).strip()]
                return None
            return eintrag["termin"]

    def _id_vergessen(self, kennung):
        with self._sperre:
            self._ids.pop(str(kennung or "").strip(), None)

    def termine(self, tage: int = 7, ab: datetime = None) -> dict:
        """Alle Termine der nächsten Tage (ab Mitternacht lokaler Zeit), samt Konflikten.

        Jeder Termin trägt eine ``id``, mit der er sich später absagen oder verschieben lässt.
        """
        if not self.verfuegbar():
            return {"ok": False,
                    "fehler": "Es ist kein Kalender eingerichtet. In der Einrichtung "
                              "die CalDAV-Adresse hinterlegen."}
        try:
            tage = max(1, min(60, int(tage)))
        except (TypeError, ValueError):
            tage = 7
        beginn = (ab or self._uhr()).replace(hour=0, minute=0, second=0, microsecond=0)
        ende = beginn + timedelta(days=tage)
        termine, fehler, hinweise = self._termine_holen(beginn, ende)
        if termine is None:
            return {"ok": False, "fehler": fehler}
        self._ids_merken(termine)

        ergebnis = {"ok": True, "anzahl": len(termine),
                    "termine": [self._als_text(t) for t in termine],
                    "konflikte": konflikte_finden(termine)}
        if hinweise:
            ergebnis["hinweis"] = " ".join(hinweise)
        # Ein Werkzeugergebnis soll klein bleiben: lieber weniger Termine als ein abgeschnittenes Ergebnis.
        weg = 0
        while len(str(ergebnis)) > 5000 and len(ergebnis["termine"]) > 1:
            ergebnis["termine"].pop()
            weg += 1
        if weg:
            ergebnis["gekuerzt"] = ("Es sind noch %d spätere Termine da - frag mit weniger Tagen nach."
                                    % weg)
            ergebnis["konflikte"] = ergebnis["konflikte"][:5]
        return ergebnis

    @staticmethod
    def _als_text(termin: dict) -> dict:
        """Formt einen Termin in schlichte Textfelder um."""
        ganz = bool(termin.get("ganztaegig"))
        text = {"id": termin.get("id", ""),
                "titel": termin["titel"] or "(ohne Titel)",
                "ort": termin["ort"],
                "beginn": termin["beginn"].strftime("%Y-%m-%d %H:%M"),
                "ende": termin["ende"].strftime("%Y-%m-%d %H:%M"),
                "tag": termin["beginn"].strftime("%d.%m.%Y"),
                "uhrzeit": "ganztägig" if ganz else termin["beginn"].strftime("%H:%M")}
        if ganz:
            text["ganztaegig"] = True
        if termin.get("serie"):
            text["serie"] = True
        return text

    def heute(self) -> dict:
        """Nur die heutigen Termine."""
        return self.termine(tage=1)

    def zusammenfassung(self, tage: int = 1) -> str:
        """Ein gesprochener Satz über die anstehenden Termine."""
        ergebnis = self.termine(tage)
        if not ergebnis.get("ok"):
            return ergebnis.get("fehler", "Der Kalender ist nicht erreichbar.")
        if ergebnis["anzahl"] == 0:
            return "Im Kalender steht nichts an."
        teile = []
        for termin in ergebnis["termine"][:6]:
            ort = (" in %s" % termin["ort"]) if termin["ort"] else ""
            if termin.get("ganztaegig"):
                teile.append("ganztägig %s%s" % (termin["titel"], ort))
            else:
                teile.append("%s Uhr %s%s" % (termin["uhrzeit"], termin["titel"], ort))
        satz = "Anstehend: " + ", ".join(teile) + "."
        for konflikt in ergebnis["konflikte"][:2]:
            satz += " Achtung: %s" % konflikt["text"]
        if ergebnis.get("hinweis"):
            satz += " " + ergebnis["hinweis"]
        return satz

    # -- Freie Zeiten -------------------------------------------------------

    def freie_zeiten(self, tag="heute", von="08:00", bis="18:00", mindestens=60) -> dict:
        """Die freien Zeitfenster eines Tages zwischen ``von`` und ``bis``.

        Belegte Zeiten werden zusammengelegt; ganztägige und als frei eingetragene
        Termine blockieren nichts. Es zählen nur Lücken von mindestens ``mindestens`` Minuten.
        """
        if not self.verfuegbar():
            return {"ok": False, "fehler": "Es ist kein Kalender eingerichtet."}
        datum = kalender_tag_verstehen(tag, self._uhr())
        if datum is None:
            return {"ok": False, "fehler": "Den Tag '%s' verstehe ich nicht. Bitte als 2026-10-09, "
                                           "heute oder morgen angeben." % tag}
        minuten_von = _kal_uhrzeit_minuten(von, "08:00")
        minuten_bis = _kal_uhrzeit_minuten(bis, "18:00")
        if minuten_von is None or minuten_bis is None or minuten_bis <= minuten_von:
            return {"ok": False, "fehler": "Von und bis verstehe ich nicht. Bitte als 08:00 und "
                                           "18:00 angeben, bis nach von."}
        try:
            laenge = max(5, int(mindestens if mindestens not in (None, "") else 60))
        except (TypeError, ValueError):
            laenge = 60
        mitternacht = datetime.combine(datum, datetime.min.time())
        fenster_von = mitternacht + timedelta(minutes=minuten_von)
        fenster_bis = mitternacht + timedelta(minutes=minuten_bis)

        termine, fehler, hinweise = self._termine_holen(fenster_von, fenster_bis)
        if termine is None:
            return {"ok": False, "fehler": fehler}
        belegt = [(t["beginn"], t["ende"]) for t in termine
                  if not t.get("ganztaegig") and not t.get("frei")]
        ganztags = len([t for t in termine if t.get("ganztaegig")])
        luecken = kalender_freie_luecken(belegt, fenster_von, fenster_bis, laenge)

        liste = [{"von": a.strftime("%H:%M"), "bis": b.strftime("%H:%M"),
                  "minuten": int((b - a).total_seconds() // 60)} for a, b in luecken]
        wann = "%s, %s" % (_KAL_TAGESNAMEN[datum.weekday()], datum.strftime("%d.%m.%Y"))
        rahmen = "von %s bis %s Uhr" % (fenster_von.strftime("%H:%M"), fenster_bis.strftime("%H:%M"))
        if liste:
            text = "Frei am %s (%s, mindestens %d Minuten am Stück): %s." % (
                wann, rahmen, laenge, ", ".join("%s bis %s" % (z["von"], z["bis"]) for z in liste))
        else:
            text = "Am %s ist %s nichts frei, das mindestens %d Minuten am Stück dauert." % (
                wann, rahmen, laenge)
        ergebnis = {"ok": True, "tag": datum.strftime("%Y-%m-%d"), "von": fenster_von.strftime("%H:%M"),
                    "bis": fenster_bis.strftime("%H:%M"), "mindestens_minuten": laenge,
                    "freie_zeiten": liste, "text": text}
        zusatz = list(hinweise)
        if ganztags:
            zusatz.append("%s an dem Tag habe ich nicht eingerechnet."
                          % ("Einen ganztägigen Termin" if ganztags == 1 else "%d ganztägige Termine" % ganztags))
        if zusatz:
            ergebnis["hinweis"] = " ".join(zusatz)
        return ergebnis

    # -- Anlegen ------------------------------------------------------------

    def termin_anlegen(self, titel: str, beginn: str, dauer_minuten: int = 60,
                       ort: str = "", beschreibung: str = "") -> dict:
        """Legt einen Termin als iCal-Datei im Kalender ab.

        Die Freigabe holt der Werkzeugkatalog ein, bevor diese Methode läuft.
        Beginn und Ende werden in UTC geschrieben (mit ``Z``).
        """
        if not self.verfuegbar():
            return {"ok": False, "fehler": "Es ist kein Kalender eingerichtet."}
        startzeit = kalender_zeit_verstehen(beginn)
        if startzeit is None:
            return {"ok": False,
                    "fehler": "Den Zeitpunkt '%s' verstehe ich nicht. Bitte im Format "
                              "2026-08-27 09:00 angeben." % beginn}
        try:
            dauer = max(5, int(dauer_minuten))
        except (TypeError, ValueError):
            dauer = 60
        endzeit = startzeit + timedelta(minutes=dauer)

        kennung = "%s@jarvis" % uuid.uuid4()
        ics = "\r\n".join(_kal_falten(z) for z in [
            "BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//Jarvis//DE",
            "BEGIN:VEVENT",
            "UID:%s" % kennung,
            "DTSTAMP:%s" % _kal_jetzt_utc(),
            "DTSTART:%s" % ics_zeit_utc_schreiben(startzeit),
            "DTEND:%s" % ics_zeit_utc_schreiben(endzeit),
            "SUMMARY:%s" % _kal_ics_maskieren(titel),
            "LOCATION:%s" % _kal_ics_maskieren(ort),
            "DESCRIPTION:%s" % _kal_ics_maskieren(beschreibung),
            "END:VEVENT", "END:VCALENDAR"]) + "\r\n"

        ziel = "%s/%s.ics" % (self.kalender_url().rstrip("/"), kennung)
        status, inhalt, _ = self._senden("PUT", ziel, ics,
                                         {"Content-Type": "text/calendar; charset=utf-8",
                                          "If-None-Match": "*"})
        if status in (200, 201, 204):
            return {"ok": True, "uid": kennung,
                    "text": "Termin %s am %s um %s Uhr ist eingetragen."
                            % (titel, startzeit.strftime("%d.%m.%Y"),
                               startzeit.strftime("%H:%M"))}
        if status == 0:
            return {"ok": False, "fehler": "Der Kalender ist nicht erreichbar: %s" % inhalt}
        return {"ok": False,
                "fehler": "Der Kalender hat den Termin abgelehnt (Fehler %d)." % status}

    # -- Absagen, Verschieben, Wiederherstellen ------------------------------

    @staticmethod
    def _ids_normalisieren(ids) -> list:
        if isinstance(ids, str):
            ids = [teil for teil in re.split(r"[\s,;]+", ids) if teil]
        if not isinstance(ids, (list, tuple)):
            return []
        sauber = []
        for kennung in ids:
            text = str(kennung or "").strip()
            if text and text not in sauber:
                sauber.append(text)
        return sauber

    def _papierkorb_db(self):
        if self.memory is None:
            self.memory = Memory()
        if self._schema_pfad != self.memory.db_pfad:
            db_schema_anlegen(SCHEMA_KALENDER, self.memory.db_pfad)
            self._schema_pfad = self.memory.db_pfad
        return self.memory

    def _papierkorb_zeile(self, nummer):
        try:
            zeilen = self._papierkorb_db()._lesen(
                "SELECT * FROM kalender_papierkorb WHERE id=?", (int(nummer),))
        except (TypeError, ValueError):
            return None
        return zeilen[0] if zeilen else None

    def _unveraendert(self, termin: dict, ics: str):
        """Ist der Termin im Kalender noch derselbe wie beim Lesen? Gibt ``(ja, grund)`` zurück."""
        gelesen = ics_termine_lesen(ics)
        if len(gelesen) != 1:
            return False, "serie" if len(gelesen) > 1 else "weg"
        aktuell = gelesen[0]
        if aktuell["serie"]:
            return False, "serie"
        if (aktuell["beginn"] != termin["beginn"] or aktuell["titel"] != termin["titel"]
                or aktuell["ende"] != termin["ende"]):
            return False, "geaendert"
        return True, ""

    def termine_absagen(self, ids, begruendung: str = "") -> dict:
        """Sagt Termine ab: sichert sie im Papierkorb und löscht sie im Kalender.

        Nur Termine, die gerade gelesen wurden (``ids`` aus ``termine``), und nie
        Serien. Gelöscht wird mit ``If-Match`` auf den gelesenen Stand. Gibt
        ``erledigt`` und ``abgelehnt`` zurück.
        """
        if not self.verfuegbar():
            return {"ok": False, "fehler": "Es ist kein Kalender eingerichtet."}
        kennungen = self._ids_normalisieren(ids)
        if not kennungen:
            return {"ok": False, "fehler": KALENDER_ERST_LESEN}
        if len(kennungen) > KALENDER_MAX_ABSAGEN:
            return {"ok": False, "fehler": "Ich sage höchstens %d Termine auf einmal ab."
                                           % KALENDER_MAX_ABSAGEN}
        erledigt, abgelehnt = [], []
        for kennung in kennungen:
            termin = self._termin_zur_id(kennung)
            if termin is None:
                abgelehnt.append({"id": kennung, "grund": KALENDER_ERST_LESEN})
                continue
            titel = termin["titel"] or "(ohne Titel)"
            if termin.get("serie"):
                abgelehnt.append({"id": kennung, "titel": titel, "grund": KALENDER_SERIE_ABGELEHNT})
                continue
            ergebnis = self._einen_absagen(kennung, termin)
            (erledigt if ergebnis.get("ok") else abgelehnt).append(ergebnis["eintrag"])

        ergebnis = {"ok": bool(erledigt), "erledigt": erledigt, "abgelehnt": abgelehnt}
        teile = []
        if erledigt:
            nummern = ", ".join(str(e["papierkorb_id"]) for e in erledigt)
            teile.append("%s abgesagt: %s. Sie liegen im Papierkorb (Nr. %s) - termin_wiederherstellen "
                         "holt sie zurück." % (
                             "Ein Termin" if len(erledigt) == 1 else "%d Termine" % len(erledigt),
                             "; ".join("„%s“ (%s)" % (e["titel"], e["wann"]) for e in erledigt),
                             nummern))
        for eintrag in abgelehnt:
            teile.append("%s%s" % (("„%s“: " % eintrag["titel"]) if eintrag.get("titel") else "",
                                   eintrag["grund"]))
        ergebnis["text"] = " ".join(teile)
        if not erledigt:
            ergebnis["fehler"] = ergebnis["text"]
        return ergebnis

    def _einen_absagen(self, kennung: str, termin: dict) -> dict:
        """Sagt einen einzelnen Termin ab. Gibt ``{"ok", "eintrag"}`` zurück."""
        titel = termin["titel"] or "(ohne Titel)"
        wann = kalender_wann(termin["beginn"], termin.get("ganztaegig"))

        def nein(grund):
            return {"ok": False, "eintrag": {"id": kennung, "titel": titel, "grund": grund}}
        if not termin.get("href"):
            return nein("Zu diesem Termin kenne ich keine Adresse im Kalender - ich lösche ihn nicht.")
        url = self._url_zu(termin["href"])
        status, ics, kopf = self._senden("GET", url)
        if status in (404, 410):
            return nein("Der Termin ist im Kalender nicht mehr da.")
        if status != 200 or "BEGIN:VCALENDAR" not in ics:
            return nein("Ich konnte den Termin nicht sichern, deshalb lösche ich ihn nicht.")
        unveraendert, grund = self._unveraendert(termin, ics)
        if not unveraendert:
            return nein(KALENDER_SERIE_ABGELEHNT if grund == "serie" else KALENDER_GEAENDERT)
        try:
            nummer = self._papierkorb_db()._schreiben(
                "INSERT INTO kalender_papierkorb (href, ics, titel, beginn, geloescht_am) "
                "VALUES (?,?,?,?,?)",
                (url, ics, titel, termin["beginn"].strftime("%Y-%m-%d %H:%M"),
                 self._uhr().strftime("%Y-%m-%d %H:%M:%S")))
        except Exception as fehler:
            return nein("Der Papierkorb ließ sich nicht beschreiben (%s) - ich lösche nichts." % fehler)
        etag = _kal_etag(termin.get("etag") or kopf.get("etag"))
        status, inhalt, _ = self._senden("DELETE", url, "", {"If-Match": etag} if etag else None)
        if status in (200, 202, 204):
            self._id_vergessen(kennung)
            return {"ok": True, "eintrag": {"id": kennung, "titel": titel, "wann": wann,
                                            "papierkorb_id": nummer}}
        self._papierkorb_db()._schreiben("DELETE FROM kalender_papierkorb WHERE id=?", (nummer,))
        if status == 412:
            return nein(KALENDER_GEAENDERT)
        if status in (404, 410):
            self._id_vergessen(kennung)
            return nein("Der Termin ist im Kalender nicht mehr da.")
        if status == 0:
            return nein("Der Kalender ist nicht erreichbar: %s" % inhalt)
        return nein("Der Kalender hat das Löschen abgelehnt (Fehler %d)." % status)

    def termin_verschieben(self, id, neuer_beginn, dauer_minuten=None) -> dict:  # noqa: A002
        """Verschiebt einen eben gelesenen Termin auf einen neuen Beginn.

        Die Dauer bleibt, wenn keine neue genannt wird. Serien nie. Geschrieben wird
        mit ``If-Match`` auf den gelesenen Stand, die Zeiten in UTC.
        """
        if not self.verfuegbar():
            return {"ok": False, "fehler": "Es ist kein Kalender eingerichtet."}
        termin = self._termin_zur_id(id)
        if termin is None:
            return {"ok": False, "fehler": KALENDER_ERST_LESEN}
        if termin.get("serie"):
            return {"ok": False, "fehler": KALENDER_SERIE_VERSCHIEBEN}
        ganz = bool(termin.get("ganztaegig"))
        neu, mit_uhrzeit = _kal_zeit_text_lesen(neuer_beginn)
        if neu is None or (not mit_uhrzeit and not ganz):
            return {"ok": False,
                    "fehler": "Den neuen Beginn '%s' verstehe ich nicht. Bitte im Format "
                              "2026-08-27 09:00 angeben." % neuer_beginn}
        if ganz:
            neu = neu.replace(hour=0, minute=0)
            ende = neu + (termin["ende"] - termin["beginn"])
        else:
            if dauer_minuten not in (None, ""):
                try:
                    dauer = timedelta(minutes=max(5, int(dauer_minuten)))
                except (TypeError, ValueError):
                    dauer = termin["ende"] - termin["beginn"]
            else:
                dauer = termin["ende"] - termin["beginn"]
            ende = neu + dauer
        if not termin.get("href"):
            return {"ok": False, "fehler": "Zu diesem Termin kenne ich keine Adresse im Kalender."}
        url = self._url_zu(termin["href"])
        status, ics, kopf = self._senden("GET", url)
        if status in (404, 410):
            return {"ok": False, "fehler": "Der Termin ist im Kalender nicht mehr da."}
        if status != 200 or "BEGIN:VCALENDAR" not in ics:
            return {"ok": False, "fehler": "Ich konnte den Termin nicht lesen, deshalb verschiebe ich ihn nicht."}
        unveraendert, grund = self._unveraendert(termin, ics)
        if not unveraendert:
            return {"ok": False, "fehler": KALENDER_SERIE_VERSCHIEBEN if grund == "serie"
                    else KALENDER_GEAENDERT_VERSCHIEBEN}
        geaendert = ics_zeit_ersetzen(ics, neu, ende, ganz)
        gelesen = ics_termine_lesen(geaendert)
        if len(gelesen) != 1 or gelesen[0]["beginn"] != neu or gelesen[0]["ende"] != ende:
            return {"ok": False, "fehler": "Die Änderung ließ sich nicht sauber vorbereiten - "
                                           "ich verschiebe nichts."}
        etag = _kal_etag(termin.get("etag") or kopf.get("etag"))
        zusatz = {"Content-Type": "text/calendar; charset=utf-8"}
        if etag:
            zusatz["If-Match"] = etag
        status, inhalt, _ = self._senden("PUT", url, geaendert, zusatz)
        titel = termin["titel"] or "(ohne Titel)"
        if status in (200, 201, 204):
            self._id_vergessen(id)
            return {"ok": True, "titel": titel,
                    "vorher": kalender_wann(termin["beginn"], ganz), "nachher": kalender_wann(neu, ganz),
                    "text": "„%s“ ist verschoben: von %s auf %s. Lies die Termine neu, wenn er noch "
                            "einmal geändert werden soll."
                            % (titel, kalender_wann(termin["beginn"], ganz), kalender_wann(neu, ganz))}
        if status == 412:
            return {"ok": False, "fehler": KALENDER_GEAENDERT_VERSCHIEBEN}
        if status == 0:
            return {"ok": False, "fehler": "Der Kalender ist nicht erreichbar: %s" % inhalt}
        return {"ok": False, "fehler": "Der Kalender hat die Änderung abgelehnt (Fehler %d)." % status}

    def termin_wiederherstellen(self, papierkorb_id) -> dict:
        """Legt einen abgesagten Termin aus dem Papierkorb wieder an - ohne etwas zu überschreiben."""
        if not self.verfuegbar():
            return {"ok": False, "fehler": "Es ist kein Kalender eingerichtet."}
        zeile = self._papierkorb_zeile(papierkorb_id)
        if zeile is None:
            return {"ok": False, "fehler": "Im Papierkorb gibt es keinen Termin mit der Nummer %s."
                                           % papierkorb_id}
        status, inhalt, _ = self._senden(
            "PUT", zeile["href"], zeile["ics"],
            {"Content-Type": "text/calendar; charset=utf-8", "If-None-Match": "*"})
        if status in (200, 201, 204):
            self._papierkorb_db()._schreiben(
                "UPDATE kalender_papierkorb SET wiederhergestellt_am=? WHERE id=?",
                (self._uhr().strftime("%Y-%m-%d %H:%M:%S"), zeile["id"]))
            return {"ok": True, "titel": zeile["titel"],
                    "text": "Der Termin „%s“ (%s) steht wieder im Kalender."
                            % (zeile["titel"], zeile["beginn"])}
        if status == 412:
            return {"ok": False, "fehler": "Dieser Termin liegt schon im Kalender, oder an seiner Stelle "
                                           "steht inzwischen etwas anderes. Ich überschreibe nichts."}
        if status == 0:
            return {"ok": False, "fehler": "Der Kalender ist nicht erreichbar: %s" % inhalt}
        return {"ok": False, "fehler": "Der Kalender hat den Termin abgelehnt (Fehler %d)." % status}

    # -- Für die Freigabefrage: lesbar machen, was hinter den Kennungen steckt ---

    def freigabe_termine(self, ids) -> list:
        """Zu jeder Kennung eine Zeile für die Freigabe: Titel, Tag und Uhrzeit.

        Gibt ``[{"id", "titel", "wann", "serie", "bekannt"}]`` zurück; unbekannte Kennungen
        stehen mit ``bekannt: False`` da.
        """
        zeilen = []
        for kennung in self._ids_normalisieren(ids):
            termin = self._termin_zur_id(kennung)
            if termin is None:
                zeilen.append({"id": kennung, "titel": "", "wann": "", "serie": False, "bekannt": False})
            else:
                zeilen.append({"id": kennung, "titel": termin["titel"] or "(ohne Titel)",
                               "wann": kalender_wann(termin["beginn"], termin.get("ganztaegig")),
                               "serie": bool(termin.get("serie")), "bekannt": True})
        return zeilen

    def freigabe_verschieben(self, kennung, neuer_beginn, dauer_minuten=None) -> dict:
        """Titel, alte und neue Zeit eines Verschiebens für die Freigabe - ``{}``, wenn unbekannt."""
        termin = self._termin_zur_id(kennung)
        if termin is None:
            return {}
        ganz = bool(termin.get("ganztaegig"))
        neu, mit_uhrzeit = _kal_zeit_text_lesen(neuer_beginn)
        if neu is not None and not mit_uhrzeit and not ganz:
            neu = None
        dauer = termin["ende"] - termin["beginn"]
        if dauer_minuten not in (None, "") and not ganz:
            try:
                dauer = timedelta(minutes=max(5, int(dauer_minuten)))
            except (TypeError, ValueError):
                pass
        return {"titel": termin["titel"] or "(ohne Titel)",
                "alt": kalender_wann(termin["beginn"], ganz),
                "neu": kalender_wann(neu, ganz) if neu is not None else "",
                "dauer_minuten": int(dauer.total_seconds() // 60),
                "serie": bool(termin.get("serie"))}

    def freigabe_wiederherstellen(self, papierkorb_id) -> dict:
        """Titel und Zeit eines Papierkorb-Termins für die Freigabe - ``{}``, wenn unbekannt."""
        zeile = self._papierkorb_zeile(papierkorb_id)
        if zeile is None:
            return {}
        zeit, _ = _kal_zeit_text_lesen(zeile["beginn"])
        return {"titel": zeile["titel"] or "(ohne Titel)",
                "wann": kalender_wann(zeit) if zeit is not None else zeile["beginn"]}
