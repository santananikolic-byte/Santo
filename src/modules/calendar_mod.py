#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Kalender über CalDAV - Termine lesen, Konflikte erkennen, Termine anlegen.

Bewusst ohne Fremdpaket: CalDAV ist HTTP mit zwei zusätzlichen Methoden. Das
spart eine Abhängigkeit, die sonst bei jeder Installation schiefgehen kann.

Die Konflikterkennung ist der eigentliche Nutzen: Termine nach Beginn sortieren
und jeden mit dem Ende des vorherigen vergleichen. Überlappt etwas, sagt Jarvis
es von sich aus - bei einem Einzelunternehmer, der selbst zu den Objekten fährt,
ist eine Doppelbuchung ein verlorener Tag.
"""

import base64
import re
import urllib.error
import urllib.request
import uuid
from datetime import datetime, timedelta

import config

CALDAV_ABFRAGE = """<?xml version="1.0" encoding="utf-8" ?>
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


def ics_zeit_lesen(wert: str):
    """Liest eine ICS-Zeitangabe wie ``20260826T090000Z`` oder ``20260826``."""
    if not wert:
        return None
    roh = wert.strip()
    if roh.endswith("Z"):
        roh = roh[:-1]
    for muster in ("%Y%m%dT%H%M%S", "%Y%m%d"):
        try:
            return datetime.strptime(roh, muster)
        except ValueError:
            continue
    return None


def ics_zeit_schreiben(zeitpunkt: datetime) -> str:
    """Schreibt einen Zeitpunkt im ICS-Format."""
    return zeitpunkt.strftime("%Y%m%dT%H%M%S")


def ics_entfalten(rohtext: str) -> list:
    """Setzt umgebrochene ICS-Zeilen wieder zusammen (Fortsetzung beginnt mit Leerzeichen)."""
    zeilen = []
    for zeile in (rohtext or "").replace("\r\n", "\n").split("\n"):
        if zeile[:1] in (" ", "\t") and zeilen:
            zeilen[-1] += zeile[1:]
        else:
            zeilen.append(zeile)
    return zeilen


def ics_termine_lesen(rohtext: str) -> list:
    """Zieht alle VEVENT-Blöcke aus einem ICS-Text."""
    termine = []
    aktuell = None
    for zeile in ics_entfalten(rohtext):
        blank = zeile.strip()
        if blank == "BEGIN:VEVENT":
            aktuell = {"titel": "", "ort": "", "beginn": None, "ende": None,
                       "beschreibung": "", "uid": ""}
            continue
        if blank == "END:VEVENT":
            if aktuell and aktuell["beginn"]:
                termine.append(aktuell)
            aktuell = None
            continue
        if aktuell is None or ":" not in blank:
            continue
        name, _, wert = blank.partition(":")
        schluessel = name.split(";")[0].upper()
        wert = wert.replace("\\,", ",").replace("\\n", " ").replace("\;", ";")
        if schluessel == "SUMMARY":
            aktuell["titel"] = wert
        elif schluessel == "LOCATION":
            aktuell["ort"] = wert
        elif schluessel == "DESCRIPTION":
            aktuell["beschreibung"] = wert
        elif schluessel == "UID":
            aktuell["uid"] = wert
        elif schluessel == "DTSTART":
            aktuell["beginn"] = ics_zeit_lesen(wert)
        elif schluessel == "DTEND":
            aktuell["ende"] = ics_zeit_lesen(wert)
    for termin in termine:
        if not termin["ende"]:
            termin["ende"] = termin["beginn"] + timedelta(hours=1)
    return sorted(termine, key=lambda t: t["beginn"])


def konflikte_finden(termine: list) -> list:
    """Findet Überschneidungen: nach Beginn sortieren, mit dem vorigen Ende vergleichen."""
    sortiert = sorted([t for t in termine if t.get("beginn") and t.get("ende")],
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


class Kalender:
    """CalDAV-Zugriff: Termine lesen und anlegen."""

    def __init__(self):
        self.letzter_fehler = ""

    def verfuegbar(self) -> bool:
        """Ist ein Kalender hinterlegt?"""
        return bool(config.CALDAV_URL and config.CALDAV_USER)

    def zustand(self) -> dict:
        """Kurzer Überblick für den Selbsttest."""
        return {"eingerichtet": self.verfuegbar(),
                "url": config.CALDAV_URL or "nicht gesetzt"}

    def _kopfzeilen(self, zusatz: dict = None) -> dict:
        """Basic-Auth und Standardköpfe."""
        zugang = base64.b64encode(
            ("%s:%s" % (config.CALDAV_USER, config.CALDAV_PASSWORT)).encode("utf-8")
        ).decode("ascii")
        kopf = {"Authorization": "Basic %s" % zugang, "User-Agent": "Jarvis/1.0"}
        kopf.update(zusatz or {})
        return kopf

    def _anfrage(self, methode: str, url: str, koerper: str = "", zusatz: dict = None):
        """Führt eine HTTP-Anfrage mit beliebiger Methode aus (auch REPORT)."""
        anfrage = urllib.request.Request(
            url, data=(koerper or "").encode("utf-8") if koerper else None,
            method=methode, headers=self._kopfzeilen(zusatz))
        try:
            with urllib.request.urlopen(anfrage, timeout=30) as antwort:
                return antwort.status, antwort.read().decode("utf-8", errors="replace")
        except urllib.error.HTTPError as fehler:
            return fehler.code, fehler.read().decode("utf-8", errors="replace")
        except (urllib.error.URLError, OSError) as fehler:
            self.letzter_fehler = str(fehler)
            return 0, str(fehler)

    # -- Lesen --------------------------------------------------------------

    def termine(self, tage: int = 7, ab: datetime = None) -> dict:
        """Alle Termine der nächsten Tage, samt Konflikten."""
        if not self.verfuegbar():
            return {"ok": False,
                    "fehler": "Es ist kein Kalender eingerichtet. In der Einrichtung "
                              "die CalDAV-Adresse hinterlegen."}
        beginn = (ab or datetime.now()).replace(hour=0, minute=0, second=0, microsecond=0)
        ende = beginn + timedelta(days=max(1, int(tage)))
        koerper = CALDAV_ABFRAGE % (beginn.strftime("%Y%m%dT000000Z"),
                                    ende.strftime("%Y%m%dT235959Z"))
        status, inhalt = self._anfrage(
            "REPORT", config.CALDAV_URL, koerper,
            {"Depth": "1", "Content-Type": "application/xml; charset=utf-8"})
        if status == 0:
            return {"ok": False, "fehler": "Der Kalender ist nicht erreichbar: %s" % inhalt}
        if status == 401:
            return {"ok": False,
                    "fehler": "Der Kalender lehnt Benutzer oder Passwort ab."}
        if status >= 400:
            return {"ok": False,
                    "fehler": "Der Kalender antwortet mit Fehler %d." % status}

        termine = []
        for block in re.findall(r"BEGIN:VCALENDAR.*?END:VCALENDAR", inhalt, re.S):
            entschaerft = block.replace("&#13;", "").replace("&lt;", "<").replace("&gt;", ">")
            termine.extend(ics_termine_lesen(entschaerft))

        gesehen, eindeutig = set(), []
        for termin in sorted(termine, key=lambda t: t["beginn"]):
            schluessel = (termin["uid"], termin["beginn"])
            if schluessel in gesehen:
                continue
            gesehen.add(schluessel)
            eindeutig.append(termin)

        return {"ok": True, "anzahl": len(eindeutig),
                "termine": [self._als_text(t) for t in eindeutig],
                "konflikte": konflikte_finden(eindeutig)}

    @staticmethod
    def _als_text(termin: dict) -> dict:
        """Formt einen Termin in schlichte Textfelder um."""
        return {"titel": termin["titel"] or "(ohne Titel)",
                "ort": termin["ort"],
                "beginn": termin["beginn"].strftime("%Y-%m-%d %H:%M"),
                "ende": termin["ende"].strftime("%Y-%m-%d %H:%M"),
                "tag": termin["beginn"].strftime("%d.%m.%Y"),
                "uhrzeit": termin["beginn"].strftime("%H:%M")}

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
            teile.append("%s Uhr %s%s" % (termin["uhrzeit"], termin["titel"], ort))
        satz = "Anstehend: " + ", ".join(teile) + "."
        for konflikt in ergebnis["konflikte"][:2]:
            satz += " Achtung: %s" % konflikt["text"]
        return satz

    # -- Anlegen ------------------------------------------------------------

    def termin_anlegen(self, titel: str, beginn: str, dauer_minuten: int = 60,
                       ort: str = "", beschreibung: str = "") -> dict:
        """Legt einen Termin als iCal-Datei im Kalender ab.

        Die Freigabe holt der Werkzeugkatalog ein, bevor diese Methode läuft.
        """
        if not self.verfuegbar():
            return {"ok": False, "fehler": "Es ist kein Kalender eingerichtet."}
        startzeit = None
        for muster in ("%Y-%m-%d %H:%M", "%Y-%m-%dT%H:%M", "%d.%m.%Y %H:%M",
                       "%Y-%m-%d %H:%M:%S"):
            try:
                startzeit = datetime.strptime(beginn.strip(), muster)
                break
            except (ValueError, AttributeError):
                continue
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
        def escape(wert):
            return str(wert or "").replace("\\", "\\\\").replace(",", "\\,") \
                                  .replace(";", "\;").replace("\n", "\\n")
        ics = "\r\n".join([
            "BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//Jarvis//DE",
            "BEGIN:VEVENT",
            "UID:%s" % kennung,
            "DTSTAMP:%sZ" % ics_zeit_schreiben(datetime.utcnow()),
            "DTSTART:%s" % ics_zeit_schreiben(startzeit),
            "DTEND:%s" % ics_zeit_schreiben(endzeit),
            "SUMMARY:%s" % escape(titel),
            "LOCATION:%s" % escape(ort),
            "DESCRIPTION:%s" % escape(beschreibung),
            "END:VEVENT", "END:VCALENDAR", ""])

        ziel = "%s/%s.ics" % (config.CALDAV_URL.rstrip("/"), kennung)
        status, inhalt = self._anfrage("PUT", ziel, ics,
                                       {"Content-Type": "text/calendar; charset=utf-8"})
        if status in (200, 201, 204):
            return {"ok": True, "uid": kennung,
                    "text": "Termin %s am %s um %s Uhr ist eingetragen."
                            % (titel, startzeit.strftime("%d.%m.%Y"),
                               startzeit.strftime("%H:%M"))}
        if status == 0:
            return {"ok": False, "fehler": "Der Kalender ist nicht erreichbar: %s" % inhalt}
        return {"ok": False,
                "fehler": "Der Kalender hat den Termin abgelehnt (Fehler %d)." % status}
