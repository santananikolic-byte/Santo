#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Erholung aus Apple Health, Oura, Whoop oder von Hand.

Jeder Tag bekommt einen Erholungswert von 0 bis 100 - aus der besten Quelle, die
für diesen Tag etwas hat: Oura, dann Whoop, dann Apple Health, dann von Hand
eingetragen. Gerechnet wird nur mit echten Messwerten; wo sie fehlen, sagt
Jarvis das. Es ist Selbstbeobachtung, kein Medizinprodukt.

**Apple Health** kommt als Export (``export.zip`` aus der Health-App, Datei im
Benutzerordner). Der Erholungswert ist eine eigene Schätzung: Herzratenvariabilität
der Nacht und Ruhepuls gegen die eigenen letzten 30 Tage, dazu der Schlaf.

**Oura und Whoop** laufen über OAuth. Die Zugangs-Schlüssel (Refresh-Token) wechseln
bei jedem Abruf und gelten nur einmal. Deshalb gilt:

* Der ``state`` der Anmeldung liegt in der Datenbank, nicht im Speicher - die
  Anmeldung wird im Terminal gestartet und von der Web-App beendet.
* Vor jedem Abruf wird die Einstellungsdatei (.env) neu gelesen und eine Dateisperre genommen,
  damit der Dienst und die Web-App nie denselben Token gleichzeitig verbrauchen.
  Der neue Token wird sofort gespeichert.

**Gesundheitsdaten bleiben lokal**: nur in der Datenbank dieses Rechners, nie in
der Cloud-Spiegelung. ``vergessen`` löscht sie.
"""

import getpass
import json
import math
import os
import re
import secrets
import sqlite3
import string
import subprocess
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import zipfile
import xml.etree.ElementTree as ET
from contextlib import contextmanager
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

try:
    import fcntl
except ImportError:  # kein Unix: dann gilt nur die Sperre innerhalb des Prozesses
    fcntl = None

import config
from modules.memory import Memory, db_schema_anlegen, db_verbindung

# ---------------------------------------------------------------------------
# Tabellen
# ---------------------------------------------------------------------------

SCHEMA_ERHOLUNG = """
CREATE TABLE IF NOT EXISTS erholung_tage (
    tag TEXT NOT NULL,
    quelle TEXT NOT NULL,
    wert REAL,
    hrv REAL,
    ruhepuls REAL,
    schlaf_h REAL,
    roh TEXT DEFAULT '{}',
    geholt TEXT,
    PRIMARY KEY (tag, quelle)
);
CREATE TABLE IF NOT EXISTS erholung_oauth (
    zustand TEXT PRIMARY KEY,
    dienst TEXT NOT NULL,
    redirect TEXT DEFAULT '',
    erstellt REAL NOT NULL,
    benutzt INTEGER DEFAULT 0
);
CREATE TABLE IF NOT EXISTS erholung_abruf (
    dienst TEXT PRIMARY KEY,
    zeit REAL DEFAULT 0,
    warten_bis REAL DEFAULT 0,
    status TEXT DEFAULT ''
);
"""

# ---------------------------------------------------------------------------
# Konstanten
# ---------------------------------------------------------------------------

HK_HRV = "HKQuantityTypeIdentifierHeartRateVariabilitySDNN"
HK_RUHEPULS = "HKQuantityTypeIdentifierRestingHeartRate"
HK_SCHLAF = "HKCategoryTypeIdentifierSleepAnalysis"
# Awake und InBed zählen nicht als Schlaf.
SCHLAF_WERTE = frozenset({
    "HKCategoryValueSleepAnalysisAsleep",
    "HKCategoryValueSleepAnalysisAsleepUnspecified",
    "HKCategoryValueSleepAnalysisAsleepCore",
    "HKCategoryValueSleepAnalysisAsleepDeep",
    "HKCategoryValueSleepAnalysisAsleepREM",
})

QUELLE_OURA = "Oura (Readiness)"
QUELLE_WHOOP = "Whoop (Recovery)"
QUELLE_APPLE = "Apple Health (eigene Schätzung)"
QUELLE_HAND = "von Hand"
QUELLEN_REIHENFOLGE = (QUELLE_OURA, QUELLE_WHOOP, QUELLE_APPLE, QUELLE_HAND)

ERHOLUNG_HINWEIS = "Selbstbeobachtung, kein Medizinprodukt."
BAND_WORTE = {"gruen": "gut erholt", "gelb": "mittel erholt", "rot": "wenig erholt"}
ERHOLUNG_WOCHENTAGE = ("Montag", "Dienstag", "Mittwoch", "Donnerstag", "Freitag", "Samstag", "Sonntag")

# Apple Health: so viele Tage zurück wird gerechnet; dazu kommen 30 Tage Vergleich davor.
IMPORT_RECHENTAGE = 90
IMPORT_BASIS_TAGE = 30
# Ab dieser Größe (Bytes der Datei) liest Jarvis im Hintergrund und meldet sich danach.
IMPORT_HINTERGRUND_BYTES = 300 * 1024 * 1024
# Größer als das (entpackt) ist kein Gesundheitsexport, sondern eine Zip-Bombe.
IMPORT_MAX_ENTPACKT = 24 * 1024 * 1024 * 1024
# Die Anmeldung bei Oura oder Whoop gilt so lange - und nur einmal.
OAUTH_GUELTIG_SEKUNDEN = 600
# Nach einem Abruf wird frühestens nach so vielen Stunden von selbst neu geholt.
ABRUF_MIN_STUNDEN = 3.0

WEARABLE_DIENSTE = {
    "oura": {
        "name": "Oura", "quelle": QUELLE_OURA, "token_name": "OURA_REFRESH_TOKEN",
        "id_name": "OURA_CLIENT_ID", "geheim_name": "OURA_CLIENT_SECRET",
        "autorisieren": "https://cloud.ouraring.com/oauth/authorize",
        "token": "https://api.ouraring.com/oauth/token",
        "scope": "daily heartrate personal", "state_laenge": 24,
        "app_seite": "https://cloud.ouraring.com/oauth/applications",
    },
    "whoop": {
        "name": "Whoop", "quelle": QUELLE_WHOOP, "token_name": "WHOOP_REFRESH_TOKEN",
        "id_name": "WHOOP_CLIENT_ID", "geheim_name": "WHOOP_CLIENT_SECRET",
        "autorisieren": "https://api.prod.whoop.com/oauth/oauth2/auth",
        "token": "https://api.prod.whoop.com/oauth/oauth2/token",
        "scope": "read:recovery read:sleep offline", "state_laenge": 8,
        "app_seite": "https://developer-dashboard.whoop.com/",
    },
}
OURA_DATEN_URL = "https://api.ouraring.com/v2/usercollection/"
WHOOP_RECOVERY_URL = "https://api.prod.whoop.com/developer/v2/recovery"

KEINE_QUELLE_TEXT = ("Es ist keine Erholungsquelle verbunden. Möglich: Apple-Health-Export "
                     "(python3 jarvis.py gesundheit <Datei>), Oura oder Whoop "
                     "(python3 jarvis.py zugang oura), oder du sagst mir den Wert.")

# Werkzeuge, deren Protokolleinträge Gesundheitswerte tragen - "gesundheit vergessen" löscht sie mit.
GESUNDHEITS_WERKZEUGE = ("erholung_lesen", "erholung_eintragen", "erholung_abrufen",
                         "gesundheit_importieren", "leistung_zusammenhang", "belastung_pruefen",
                         "handruhe_verlauf")


# ---------------------------------------------------------------------------
# Kleine Hilfen
# ---------------------------------------------------------------------------

def erholung_tag_text(tag) -> str:
    """``date``, ``datetime`` oder ``JJJJ-MM-TT...`` als ``JJJJ-MM-TT`` - sonst leer."""
    if isinstance(tag, datetime):
        return tag.date().isoformat()
    if isinstance(tag, date):
        return tag.isoformat()
    roh = str(tag or "").strip()[:10]
    if re.match(r"^\d{4}-\d{2}-\d{2}$", roh):
        try:
            return date(int(roh[:4]), int(roh[5:7]), int(roh[8:10])).isoformat()
        except ValueError:
            return ""
    return ""


def erholung_tag_datum(tag):
    """Wie :func:`erholung_tag_text`, aber als ``date`` (oder ``None``)."""
    text = erholung_tag_text(tag)
    return date(int(text[:4]), int(text[5:7]), int(text[8:10])) if text else None


def erholung_datum_text(tag) -> str:
    """``Montag, 5.10.`` - für Sätze, die Jarvis sagt."""
    datum = erholung_tag_datum(tag)
    if datum is None:
        return str(tag or "")
    return "%s, %d.%d." % (ERHOLUNG_WOCHENTAGE[datum.weekday()], datum.day, datum.month)


def erholung_band(wert) -> str:
    """Grün ab 67, gelb von 34 bis 66, rot darunter."""
    if wert >= 67:
        return "gruen"
    if wert >= 34:
        return "gelb"
    return "rot"


def _erh_zahl(wert):
    """Eine echte, endliche Zahl - Texte, Wahrheitswerte und NaN sind keine."""
    if isinstance(wert, bool) or not isinstance(wert, (int, float)):
        return None
    wert = float(wert)
    return wert if math.isfinite(wert) else None


def _erh_klemme(wert, tief=0.0, hoch=100.0):
    return max(tief, min(hoch, wert))


def _erh_mittel(werte):
    return sum(werte) / float(len(werte))


def _erh_streuung(werte):
    """Stichproben-Standardabweichung, von Hand gerechnet (n - 1)."""
    if len(werte) < 2:
        return 0.0
    mittel = _erh_mittel(werte)
    return math.sqrt(sum((w - mittel) ** 2 for w in werte) / float(len(werte) - 1))


def _erh_median(werte):
    ordnung = sorted(werte)
    mitte = len(ordnung) // 2
    if len(ordnung) % 2:
        return ordnung[mitte]
    return (ordnung[mitte - 1] + ordnung[mitte]) / 2.0


def _erh_tage_dict(daten) -> dict:
    """Schlüssel (``date`` oder Text) zu ``JJJJ-MM-TT``; nur echte Zahlen als Werte."""
    ergebnis = {}
    for tag, wert in (daten or {}).items():
        schluessel = erholung_tag_text(tag)
        zahl = _erh_zahl(wert)
        if schluessel and zahl is not None:
            ergebnis[schluessel] = zahl
    return ergebnis


def _erh_iso_lesen(text):
    """ISO-Zeit mit ``Z`` oder Zeitzone als aware ``datetime`` - ``None`` bei Unlesbarem (auch Python 3.9)."""
    roh = str(text or "").strip().replace("Z", "+00:00")
    treffer = re.match(r"^(\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2})(\.\d+)?(.*)$", roh)
    if not treffer:
        return None
    bruch = (treffer.group(2) or "")[1:7].ljust(6, "0") if treffer.group(2) else ""
    rest = treffer.group(3) or ""
    try:
        return datetime.fromisoformat(treffer.group(1).replace(" ", "T") + ("." + bruch if bruch else "") + rest)
    except ValueError:
        return None


# ---------------------------------------------------------------------------
# Apple Health: Export lesen und Erholung schätzen
# ---------------------------------------------------------------------------

def _apple_zeit(text):
    return datetime.strptime(str(text), "%Y-%m-%d %H:%M:%S %z")


def schlaf_stunden(intervalle) -> float:
    """Summe der Schlafintervalle in Stunden - überlappende (Uhr und iPhone) zählen einmal."""
    gueltig = sorted((s, e) for s, e in intervalle if e > s)
    if not gueltig:
        return 0.0
    summe = 0.0
    anfang, ende = gueltig[0]
    for s, e in gueltig[1:]:
        if s <= ende:
            ende = max(ende, e)
        else:
            summe += (ende - anfang).total_seconds()
            anfang, ende = s, e
    summe += (ende - anfang).total_seconds()
    return summe / 3600.0


def _schlaf_tag(ende) -> str:
    """Zu welchem Tag ein Schlafintervall gehört: dem, an dem man aufwacht.

    Schlafphasen, die vor Mitternacht enden, gehören zur Nacht des Folgetages -
    sonst fehlte jeder Nacht ihr Anfang. Ab 18 Uhr gilt als "Abend".
    """
    tag = ende.date()
    if ende.hour >= 18:
        tag = tag + timedelta(days=1)
    return tag.isoformat()


def _export_mitglied(archiv):
    """Das ``export.xml`` in der Zip (die Health-App legt es nach apple_health_export/). ``None``, wenn keines da ist."""
    kandidaten = [i for i in archiv.infolist()
                  if i.filename.lower().endswith(".xml") and not i.is_dir()
                  and not any(w in i.filename.lower() for w in ("cda", "electrocardiogram", "clinical", "workout-routes"))]
    wahl = [i for i in kandidaten if i.filename.lower().rsplit("/", 1)[-1] in ("export.xml", "exportieren.xml")]
    if not wahl and kandidaten:
        wahl = [max(kandidaten, key=lambda i: i.file_size)]
    return wahl[0] if wahl else None


def erholung_export_groesse(pfad) -> int:
    """Wie viele Bytes der Export entpackt hat - bei einer Zip die des ``export.xml``, sonst die Dateigröße."""
    groesse = os.path.getsize(str(pfad))
    if str(pfad).lower().endswith(".zip"):
        try:
            with zipfile.ZipFile(str(pfad)) as archiv:
                info = _export_mitglied(archiv)
                if info is not None:
                    groesse = max(groesse, info.file_size)
        except (zipfile.BadZipFile, OSError):
            pass
    return groesse


@contextmanager
def _export_oeffnen(pfad):
    """Öffnet ``export.xml`` zum Lesen: aus der Zip, ohne sie zu entpacken, oder direkt."""
    pfad = str(pfad)
    if pfad.lower().endswith(".zip"):
        try:
            archiv = zipfile.ZipFile(pfad)
        except zipfile.BadZipFile:
            raise ValueError("Das ist keine lesbare Zip-Datei.")
        with archiv:
            info = _export_mitglied(archiv)
            if info is None:
                raise ValueError("In der Zip-Datei steckt kein export.xml - ist das der Export aus der Health-App?")
            # Ein echter Export schrumpft auf etwa ein Zehntel; ein Vielfaches davon ist eine Zip-Bombe.
            if info.file_size > IMPORT_MAX_ENTPACKT or info.file_size > 100 * max(info.compress_size, 1) + 67108864:
                raise ValueError("Die Datei ist entpackt unglaublich groß - das lese ich nicht.")
            _export_kopf_pruefen(archiv.open(info))
            with archiv.open(info) as datei:
                yield datei
    else:
        with open(pfad, "rb") as kopf:
            _export_kopf_pruefen(kopf)
        with open(pfad, "rb") as datei:
            yield datei


def _export_kopf_pruefen(datei):
    """Ein Apple-Export definiert keine eigenen Entitäten - wer welche mitbringt, will etwas anderes."""
    try:
        kopf = datei.read(262144)
    finally:
        datei.close()
    if b"<!ENTITY" in kopf:
        raise ValueError("Die Datei definiert eigene XML-Entitäten - das ist kein Apple-Health-Export.")


def apple_export_lesen(pfad, ab_tag=None) -> dict:
    """Liest den Apple-Health-Export streamend.

    Gibt ``{tag: {"hrv": [...], "ruhepuls": [...], "schlaf": [(start, ende), ...]}}`` zurück,
    ``tag`` als ``JJJJ-MM-TT``. Nur Daten ab ``ab_tag``. Angenommen wird eine ``.zip``
    (das ``export.xml`` darin wird direkt gelesen) oder eine ``.xml``.

    * HRV zählt nur, wenn die Messung zwischen 0 und 8 Uhr (Ortszeit der Aufzeichnung) beginnt.
    * Ein Tag ist der des ``endDate``; Schlaf gehört zum Tag des Aufwachens.
    * Schlafphasen ``Awake`` und ``InBed`` fehlen.
    """
    ab = erholung_tag_text(ab_tag)
    tage = {}
    schlaf = []
    with _export_oeffnen(pfad) as datei:
        wurzel = None
        for ereignis, element in ET.iterparse(datei, events=("start", "end")):
            if wurzel is None:
                wurzel = element
                continue
            if ereignis != "end" or element.tag != "Record":
                continue
            typ = element.get("type")
            if typ in (HK_HRV, HK_RUHEPULS, HK_SCHLAF):
                try:
                    ende = _apple_zeit(element.get("endDate"))
                    if typ == HK_SCHLAF:
                        if element.get("value") in SCHLAF_WERTE:
                            schlaf.append((_apple_zeit(element.get("startDate")), ende))
                    else:
                        tag = ende.date().isoformat()
                        if tag >= ab:
                            wert = float(element.get("value"))
                            if math.isfinite(wert):
                                eintrag = tage.setdefault(tag, {"hrv": [], "ruhepuls": [], "schlaf": []})
                                if typ == HK_HRV:
                                    if _apple_zeit(element.get("startDate")).hour < 8:
                                        eintrag["hrv"].append(wert)
                                else:
                                    eintrag["ruhepuls"].append(wert)
                except (TypeError, ValueError):
                    pass  # eine kaputte Zeile im Export wirft nicht den ganzen Export weg
            element.clear()
            wurzel.clear()
    for start, ende in schlaf:
        tag = _schlaf_tag(ende)
        if tag >= ab:
            tage.setdefault(tag, {"hrv": [], "ruhepuls": [], "schlaf": []})["schlaf"].append((start, ende))
    for eintrag in tage.values():
        eintrag["schlaf"].sort()
    return tage


def erholung_schaetzen(tag, hrv_tage, puls_tage, schlaf_tage, basis_tage=30, ziel_schlaf=7.5):
    """Schätzt die Erholung eines Tages gegen die eigenen letzten ``basis_tage`` Tage.

    ``hrv_tage``, ``puls_tage``, ``schlaf_tage``: ``{tag: Wert}`` (HRV in ms, Ruhepuls,
    Schlaf in Stunden). Gibt ``None`` zurück, wenn weniger als 14 Vergleichstage mit HRV oder
    mit Ruhepuls da sind oder der Tag selbst keine HRV hat - dann gibt es keine Zahl.

    HRV: z-Wert auf ln(HRV); Ruhepuls: ein höherer Puls als sonst senkt. Jeder Teil ist
    ``50 + 20 * z`` (0 bis 100), der Schlafteil ``100 * Stunden / 7,5``. Gewichte 45/30/25;
    ohne Schlafdaten 60/40. Heuristik, nicht medizinisch geprüft.
    """
    heute = erholung_tag_datum(tag)
    if heute is None:
        return None
    hrv, puls, schlaf = _erh_tage_dict(hrv_tage), _erh_tage_dict(puls_tage), _erh_tage_dict(schlaf_tage)
    heute_text = heute.isoformat()
    basis = [(heute - timedelta(days=i)).isoformat() for i in range(1, int(basis_tage) + 1)]
    log_hrv = [math.log(hrv[t]) for t in basis if t in hrv and hrv[t] > 0]
    ruhe = [puls[t] for t in basis if t in puls]
    if len(log_hrv) < 14 or len(ruhe) < 14 or hrv.get(heute_text, 0) <= 0:
        return None
    # Eine Streuung nahe null (fast gleiche Werte) machte aus jeder Abweichung einen Ausreißer.
    streuung_hrv = max(_erh_streuung(log_hrv), 0.05)
    streuung_puls = max(_erh_streuung(ruhe), 1.0)
    z_hrv = (math.log(hrv[heute_text]) - _erh_mittel(log_hrv)) / streuung_hrv
    puls_heute = puls.get(heute_text, _erh_mittel(ruhe))
    z_puls = -(puls_heute - _erh_mittel(ruhe)) / streuung_puls
    teil_hrv = _erh_klemme(50 + 20 * z_hrv)
    teil_puls = _erh_klemme(50 + 20 * z_puls)
    teil_schlaf = _erh_klemme(100.0 * schlaf[heute_text] / float(ziel_schlaf)) if heute_text in schlaf else None
    if teil_schlaf is None:
        wert = 0.6 * teil_hrv + 0.4 * teil_puls
    else:
        wert = 0.45 * teil_hrv + 0.30 * teil_puls + 0.25 * teil_schlaf
    wert = int(round(wert))
    return {"wert": wert, "band": erholung_band(wert), "hrv": int(round(teil_hrv)),
            "puls": int(round(teil_puls)),
            "schlaf": None if teil_schlaf is None else int(round(teil_schlaf)),
            "basis_hrv": len(log_hrv), "basis_puls": len(ruhe)}


# ---------------------------------------------------------------------------
# Netz und Sperre
# ---------------------------------------------------------------------------

class ErholungOhneWeiterleitung(urllib.request.HTTPRedirectHandler):
    """Folgt keiner Weiterleitung - ein Zugangs-Token darf nie zu einem anderen Rechner wandern."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def erholung_http_holen(methode, url, kopf=None, formular=None, timeout=20):
    """Ein HTTP-Aufruf. Gibt ``(status, text, kopfzeilen)`` zurück, ``status`` 0 bei Netzfehlern.

    Das ist die einspeisbare Stelle: Prüfungen ersetzen sie durch eine Funktion mit
    derselben Form ``holen(methode, url, kopf, formular)``.
    """
    kopfzeilen = {"User-Agent": "Jarvis/1.0", "Accept": "application/json"}
    kopfzeilen.update(kopf or {})
    daten = None
    if formular is not None:
        daten = urllib.parse.urlencode(formular).encode("utf-8")
        kopfzeilen.setdefault("Content-Type", "application/x-www-form-urlencoded")
    anfrage = urllib.request.Request(url, data=daten, headers=kopfzeilen, method=methode)
    oeffner = urllib.request.build_opener(ErholungOhneWeiterleitung)
    try:
        with oeffner.open(anfrage, timeout=timeout) as antwort:
            text = antwort.read(4000000).decode("utf-8", "replace")
            return antwort.status, text, {k.lower(): v for k, v in antwort.headers.items()}
    except urllib.error.HTTPError as fehler:
        try:
            text = fehler.read(200000).decode("utf-8", "replace")
        except Exception:
            text = ""
        return fehler.code, text, {k.lower(): v for k, v in (fehler.headers or {}).items()}
    except (urllib.error.URLError, OSError, ValueError) as fehler:
        return 0, str(getattr(fehler, "reason", fehler)), {}


def _erh_json(text):
    try:
        daten = json.loads(text)
    except (TypeError, ValueError):
        return None
    return daten if isinstance(daten, dict) else None


def _erh_env_datei_wert(name) -> str:
    """Liest einen Wert frisch aus ``config/.env`` - ohne das Wörterbuch der Konfiguration anzufassen."""
    try:
        for zeile in config.ENV_DATEI.read_text(encoding="utf-8").splitlines():
            zeile = zeile.strip()
            if not zeile or zeile.startswith("#") or "=" not in zeile:
                continue
            schluessel, _, wert = zeile.partition("=")
            if schluessel.strip() == name:
                wert = wert.strip()
                if len(wert) >= 2 and wert[0] == wert[-1] and wert[0] in "\"'":
                    wert = wert[1:-1]
                return wert
    except OSError:
        pass
    return ""


def _erh_config_wert(name) -> str:
    """Der Wert, mit dem dieser Prozess gestartet ist (``config.NAME``)."""
    werte = {"OURA_CLIENT_ID": config.OURA_CLIENT_ID, "OURA_CLIENT_SECRET": config.OURA_CLIENT_SECRET,
             "OURA_REFRESH_TOKEN": config.OURA_REFRESH_TOKEN,
             "WHOOP_CLIENT_ID": config.WHOOP_CLIENT_ID, "WHOOP_CLIENT_SECRET": config.WHOOP_CLIENT_SECRET,
             "WHOOP_REFRESH_TOKEN": config.WHOOP_REFRESH_TOKEN}
    return str(werte.get(name) or "")


# ---------------------------------------------------------------------------
# Erholung
# ---------------------------------------------------------------------------

class Erholung:
    """Erholungswerte aus allen Quellen - speichern, zusammenführen, abrufen.

    ``memory``: das Gedächtnis (die Tabellen liegen in dessen Datenbank).
    ``holen``: Ersatz für den HTTP-Aufruf ``(methode, url, kopf, formular) -> (status, text, kopfzeilen)``.
    ``uhr``: liefert die lokale Zeit als ``datetime`` - für Prüfungen.
    ``zugriff``: der Dateizugriff (``MacZugriff``) für den Import: nur Benutzerordner, nichts Gesperrtes.
    ``anzeige``: wohin Werte auf die Zentrale gehen (``zeigen``/``melden``), ``ausgabe``: Funktion für
    Meldungen, die später kommen (ein langer Import im Hintergrund).
    ``env_lesen`` / ``env_setzen`` / ``sperrdatei``: für Prüfungen austauschbar.
    """

    def __init__(self, memory, holen=None, uhr=None, zugriff=None, anzeige=None, sperrdatei=None,
                 env_lesen=None, env_setzen=None, sperr_wartezeit=5.0):
        self.memory = memory
        self._holen = holen or erholung_http_holen
        self._uhr = uhr or datetime.now
        self.zugriff = zugriff
        self.anzeige = anzeige
        self.ausgabe = None
        self.sperrdatei = sperrdatei
        self.sperr_wartezeit = sperr_wartezeit
        self._env_lesen_fn = env_lesen
        self._env_setzen_fn = env_setzen
        self._fadensperre = threading.Lock()
        self._import_sperre = threading.Lock()
        self._import_faden = None
        self.letzter_import = None
        db_schema_anlegen(SCHEMA_ERHOLUNG, self.memory.db_pfad)

    # -- Hilfen ---------------------------------------------------------------

    def _heute_text(self) -> str:
        return self._uhr().date().isoformat()

    def _jetzt_s(self) -> float:
        return self._uhr().timestamp()

    def _aendern(self, sql: str, werte: tuple = ()) -> int:
        """Schreibt und gibt die Zahl der betroffenen Zeilen zurück (die Datenbank selbst serialisiert)."""
        verbindung = db_verbindung(self.memory.db_pfad)
        try:
            zeiger = verbindung.execute(sql, werte)
            verbindung.commit()
            return zeiger.rowcount
        finally:
            verbindung.close()

    def _viele(self, sql: str, zeilen: list):
        verbindung = db_verbindung(self.memory.db_pfad)
        try:
            verbindung.executemany(sql, zeilen)
            verbindung.commit()
        finally:
            verbindung.close()

    def _tage_speichern(self, quelle: str, zeilen: list):
        """``zeilen``: ``[(tag, wert, hrv, ruhepuls, schlaf_h, roh_dict), ...]`` - ersetzt gleiche Tage."""
        geholt = self._uhr().strftime("%Y-%m-%d %H:%M:%S")
        daten = []
        for tag, wert, hrv, puls, schlaf, roh in zeilen:
            daten.append((tag, quelle, wert, hrv, puls, schlaf, json.dumps(roh or {}, ensure_ascii=False), geholt))
        if daten:
            self._viele("INSERT OR REPLACE INTO erholung_tage "
                        "(tag, quelle, wert, hrv, ruhepuls, schlaf_h, roh, geholt) VALUES (?,?,?,?,?,?,?,?)", daten)

    def _beste_pro_tag(self, ab_tag: str) -> dict:
        """``{tag: Zeile}`` - je Tag die Quelle, die in der Reihenfolge Oura, Whoop, Apple, Hand zuerst kommt."""
        zeilen = self.memory._lesen(
            "SELECT * FROM erholung_tage WHERE tag>=? AND wert IS NOT NULL ORDER BY tag", (ab_tag,))
        beste = {}
        for zeile in zeilen:
            rang = QUELLEN_REIHENFOLGE.index(zeile["quelle"]) if zeile["quelle"] in QUELLEN_REIHENFOLGE else 99
            if zeile["tag"] not in beste or rang < beste[zeile["tag"]][0]:
                beste[zeile["tag"]] = (rang, zeile)
        return {tag: zeile for tag, (rang, zeile) in beste.items()}

    @staticmethod
    def _eintrag(zeile: dict) -> dict:
        wert = int(round(zeile["wert"]))
        eintrag = {"tag": zeile["tag"], "wert": wert, "band": erholung_band(wert), "quelle": zeile["quelle"]}
        for feld, name in (("hrv", "hrv"), ("ruhepuls", "ruhepuls"), ("schlaf_h", "schlaf_h")):
            if zeile.get(feld) is not None:
                eintrag[name] = round(zeile[feld], 1)
        return eintrag

    # -- Lesen ------------------------------------------------------------------

    def verlauf(self, tage: int = 14) -> list:
        """Die Erholungswerte der letzten ``tage`` Tage (einer je Tag, älteste zuerst)."""
        try:
            tage = max(1, min(120, int(tage)))
        except (TypeError, ValueError):
            tage = 14
        heute = self._uhr().date()
        ab = (heute - timedelta(days=tage - 1)).isoformat()
        beste = self._beste_pro_tag(ab)
        return [self._eintrag(beste[t]) for t in sorted(beste) if t <= heute.isoformat()]

    def werte_je_tag(self, tage: int = 60) -> dict:
        """``{tag: Wert}`` der letzten ``tage`` Tage - für den Zusammenhang mit der Arbeit."""
        return {e["tag"]: e["wert"] for e in self.verlauf(tage)}

    def verbunden(self) -> dict:
        """Welche Wearables einen Zugangsschlüssel haben (ohne Netz, ohne den Schlüssel zu zeigen)."""
        return {dienst: bool(self._einstellung(info["token_name"])) for dienst, info in WEARABLE_DIENSTE.items()}

    def heute(self, abrufen: bool = False) -> dict:
        """Der Erholungswert von heute: ``{"ok", "tag", "wert", "band", "quelle", "text"}``.

        Gibt es für heute keinen, ist ``ok`` falsch und ``fehler`` sagt ehrlich, warum - und was
        der letzte bekannte Wert war. ``abrufen`` holt vorher (höchstens alle paar Stunden) neue
        Werte von Oura und Whoop; Fehler dabei bleiben ohne Folgen.
        """
        if abrufen:
            try:
                self.aktualisieren()
            except Exception as fehler:
                print("[erholung] Abruf nicht möglich: %s" % fehler)
        tag = self._heute_text()
        zeile = self._beste_pro_tag(tag).get(tag)
        if zeile is not None:
            eintrag = self._eintrag(zeile)
            eintrag["ok"] = True
            eintrag["text"] = self._satz(eintrag, "heute")
            return eintrag
        return self._ohne_wert(tag)

    def _satz(self, eintrag: dict, wann: str) -> str:
        text = "Erholung %s: %d von 100, %s (Quelle: %s)." % (
            wann, eintrag["wert"], BAND_WORTE[eintrag["band"]], eintrag["quelle"])
        if eintrag["quelle"] == QUELLE_APPLE:
            text += " Das ist eine eigene Schätzung aus Apple Health, kein Medizinprodukt."
        return text

    def _ohne_wert(self, tag: str) -> dict:
        verbunden = [WEARABLE_DIENSTE[d]["name"] for d, ja in self.verbunden().items() if ja]
        letzte = self.memory._lesen("SELECT * FROM erholung_tage WHERE wert IS NOT NULL AND tag<=? "
                                    "ORDER BY tag DESC LIMIT 1", (tag,))
        if not letzte and not verbunden:
            return {"ok": False, "fehler": KEINE_QUELLE_TEXT}
        if letzte:
            eintrag = self._beste_pro_tag(letzte[0]["tag"])[letzte[0]["tag"]]
            eintrag = self._eintrag(eintrag)
            fehler = ("Für heute habe ich noch keinen Erholungswert. Der letzte ist von %s: %d von 100 (%s)."
                      % (erholung_datum_text(eintrag["tag"]), eintrag["wert"], eintrag["quelle"]))
            letzter = eintrag
        else:
            fehler = "%s ist verbunden, aber es liegen noch keine Werte vor." % " und ".join(verbunden)
            letzter = None
        if verbunden:
            fehler += " Neue Werte holt erholung_abrufen."
        return {"ok": False, "fehler": fehler, "letzter": letzter}

    def status(self) -> dict:
        """Wie viele Tage aus welcher Quelle da sind - für ``jarvis.py gesundheit``."""
        zeilen = self.memory._lesen("SELECT quelle, COUNT(*) AS n, MIN(tag) AS von, MAX(tag) AS bis "
                                    "FROM erholung_tage GROUP BY quelle")
        return {"quellen": zeilen, "verbunden": self.verbunden()}

    # -- Anzeige ----------------------------------------------------------------

    def anzeigen(self, eintrag: dict = None, dauer_s: float = 120):
        """Zeigt einen Erholungswert (Standard: den von heute) auf der Zentrale - Kanal ``sicht`` und Ansicht ``sicht``."""
        eintrag = eintrag or self.heute()
        if "wert" not in eintrag:
            return  # nichts da, nichts gezeigt (auch ein älterer Wert mit seinem Tag darf erscheinen)
        sicht_teil_schreiben(self.anzeige, {"erholung": {
            "wert": eintrag["wert"], "band": eintrag["band"], "quelle": eintrag["quelle"], "tag": eintrag["tag"]}},
            dauer_s)

    # -- Von Hand ---------------------------------------------------------------

    def manuell(self, tag, wert) -> dict:
        """Trägt einen Erholungswert (0 bis 100) von Hand ein - etwa aus der Oura- oder Whoop-App."""
        zahl = _erh_zahl(wert)
        if zahl is None and isinstance(wert, str):
            try:
                zahl = _erh_zahl(float(wert.strip().replace(",", ".")))
            except ValueError:
                zahl = None
        if zahl is None or not 0 <= zahl <= 100:
            return {"ok": False, "fehler": "Der Erholungswert muss eine Zahl von 0 bis 100 sein."}
        text = erholung_tag_text(tag) if tag else self._heute_text()
        if not text:
            return {"ok": False, "fehler": "Das Datum verstehe ich nicht. Gebraucht wird JJJJ-MM-TT."}
        if text > self._heute_text():
            return {"ok": False, "fehler": "Für die Zukunft trage ich keine Erholung ein."}
        self._tage_speichern(QUELLE_HAND, [(text, float(zahl), None, None, None, {})])
        eintrag = {"tag": text, "wert": int(round(zahl)), "band": erholung_band(int(round(zahl))),
                   "quelle": QUELLE_HAND}
        return {"ok": True, "tag": text, "wert": eintrag["wert"], "band": eintrag["band"],
                "text": "Eingetragen: Erholung %s %d von 100." % (erholung_datum_text(text), eintrag["wert"])}

    # -- Apple Health -----------------------------------------------------------

    def _import_pfad(self, pfad):
        """Prüft den Pfad: im Benutzerordner, ``.zip`` oder ``.xml``, nichts Gesperrtes. ``(Pfad, Fehler)``."""
        roh = os.path.expanduser(str(pfad or "").strip())
        nein = "Diese Datei lese ich nicht."
        if not roh:
            return None, "Sag mir, wo der Apple-Health-Export liegt (export.zip)."
        home = Path(getattr(self.zugriff, "home", None) or Path.home())
        try:
            home = home.resolve()
            ziel = Path(roh if os.path.isabs(roh) else str(home / roh)).resolve()
        except (OSError, RuntimeError):
            return None, nein
        if ziel.suffix.lower() not in (".zip", ".xml"):
            return None, "%s Gebraucht wird die export.zip (oder export.xml) aus der Health-App." % nein
        if not str(ziel).lower().startswith(str(home).lower().rstrip(os.sep) + os.sep):
            return None, ("%s Lege den Export in deinen Benutzerordner, zum Beispiel nach Downloads." % nein)
        gesperrt = getattr(self.zugriff, "gesperrt", None)
        if callable(gesperrt):
            grund = gesperrt(ziel)
            if grund:
                return None, "%s %s" % (nein, grund)
        if not ziel.is_file():
            return None, "Die Datei '%s' gibt es nicht." % ziel.name
        return ziel, ""

    def importieren(self, pfad, hintergrund: bool = True) -> dict:
        """Liest einen Apple-Health-Export und rechnet die Erholung je Tag.

        Große Exporte (entpackt über 300 MB) liest ein Hintergrundfaden; das Ergebnis kommt dann über
        ``ausgabe`` und steht in ``letzter_import``.
        """
        ziel, fehler = self._import_pfad(pfad)
        if fehler:
            return {"ok": False, "fehler": fehler}
        groesse = erholung_export_groesse(ziel)
        if hintergrund and groesse > IMPORT_HINTERGRUND_BYTES:
            if not self._import_sperre.acquire(False):
                return {"ok": False, "fehler": "Ein Export wird gerade gelesen. Ich melde mich, wenn er fertig ist."}
            faden = threading.Thread(target=self._import_im_hintergrund, args=(ziel,), daemon=True,
                                     name="jarvis-gesundheit")
            self._import_faden = faden
            faden.start()
            return {"ok": True, "hintergrund": True,
                    "text": "Der Export ist groß (%d MB). Ich lese ihn im Hintergrund und melde mich, "
                            "wenn ich fertig bin." % (groesse // (1024 * 1024))}
        return self._import_ausfuehren(ziel)

    def _import_im_hintergrund(self, ziel):
        try:
            ergebnis = self._import_ausfuehren(ziel)
        finally:
            self._import_sperre.release()
        self.letzter_import = ergebnis
        if self.ausgabe is not None:
            try:
                self.ausgabe(ergebnis.get("text") or ergebnis.get("fehler") or "")
            except Exception as fehler:
                print("[erholung] Ausgabe fehlgeschlagen: %s" % fehler)

    def _import_ausfuehren(self, ziel) -> dict:
        heute = self._uhr().date()
        ab = (heute - timedelta(days=IMPORT_RECHENTAGE + IMPORT_BASIS_TAGE + 5)).isoformat()
        try:
            daten = apple_export_lesen(str(ziel), ab)
        except zipfile.BadZipFile:
            return {"ok": False, "fehler": "Das ist keine lesbare Zip-Datei."}
        except ET.ParseError as fehler:
            return {"ok": False, "fehler": "Der Export lässt sich nicht lesen (XML-Fehler: %s)." % fehler}
        except (OSError, ValueError) as fehler:
            return {"ok": False, "fehler": "Der Export lässt sich nicht lesen: %s" % fehler}
        hrv = {t: _erh_median(d["hrv"]) for t, d in daten.items() if d["hrv"]}
        puls = {t: _erh_median(d["ruhepuls"]) for t, d in daten.items() if d["ruhepuls"]}
        schlaf = {t: schlaf_stunden(d["schlaf"]) for t, d in daten.items() if d["schlaf"]}
        if not hrv:
            return {"ok": False, "tage": 0,
                    "fehler": "Im Export stehen keine HRV-Messungen aus den Nächten (0 bis 8 Uhr). "
                              "Ohne sie rechne ich keine Erholung."}
        ende = max(hrv)
        rechenende = erholung_tag_datum(ende)
        zeilen = []
        for i in range(IMPORT_RECHENTAGE):
            tag = (rechenende - timedelta(days=i)).isoformat()
            if tag not in hrv:
                continue
            schaetzung = erholung_schaetzen(tag, hrv, puls, schlaf)
            if schaetzung is None:
                continue
            zeilen.append((tag, float(schaetzung["wert"]), hrv[tag], puls.get(tag), schlaf.get(tag),
                           {"teile": {"hrv": schaetzung["hrv"], "puls": schaetzung["puls"],
                                      "schlaf": schaetzung["schlaf"]},
                            "basis": {"hrv": schaetzung["basis_hrv"], "puls": schaetzung["basis_puls"]}}))
        if not zeilen:
            return {"ok": False, "tage": 0, "tage_hrv": len(hrv), "tage_puls": len(puls),
                    "fehler": "Aus dem Export lässt sich noch keine Erholung berechnen: Es braucht mindestens "
                              "14 Tage mit HRV und 14 mit Ruhepuls vor dem Tag, ich habe %d Tage mit HRV und %d "
                              "mit Ruhepuls." % (len(hrv), len(puls))}
        self._tage_speichern(QUELLE_APPLE, zeilen)
        zeilen.sort()
        letzter = zeilen[-1]
        wert = int(round(letzter[1]))
        text = ("Apple Health gelesen: %d Tage mit Erholungswert, der letzte von %s: %d von 100. "
                "Das ist eine eigene Schätzung, kein Medizinprodukt." % (
                    len(zeilen), erholung_datum_text(letzter[0]), wert))
        if letzter[0] < heute.isoformat():
            text += " Für heute gilt er nicht - der Export endet am %s." % erholung_datum_text(ende)
        return {"ok": True, "tage": len(zeilen), "letzter_tag": letzter[0], "wert": wert,
                "band": erholung_band(wert), "text": text}

    # -- Zugang zu Oura und Whoop -----------------------------------------------

    @staticmethod
    def _dienst(dienst):
        name = str(dienst or "").strip().lower()
        return (name, WEARABLE_DIENSTE[name]) if name in WEARABLE_DIENSTE else (None, None)

    def _einstellung(self, name: str) -> str:
        """Ein Wert aus ``config/.env`` (frisch gelesen) oder, wenn dort nichts steht, aus dem Start."""
        wert = self._env_lesen_fn(name) if self._env_lesen_fn is not None else _erh_env_datei_wert(name)
        return str(wert or _erh_config_wert(name) or "").strip()

    def _einstellung_speichern(self, name: str, wert: str) -> bool:
        """Schreibt einen Wert nach ``config/.env`` (``env_setzen``); nie eine Ausnahme."""
        try:
            if self._env_setzen_fn is not None:
                return bool(self._env_setzen_fn(name, wert))
            # env_setzen schreibt den ganzen Stand dieses Prozesses zurück. Der kann Stunden alt sein - hat
            # ein anderer Prozess inzwischen etwas eingetragen (Token, Client-ID), ginge es verloren.
            config.env_neu_laden()
            return bool(config.env_setzen(name, wert))
        except Exception as fehler:
            print("[erholung] %s ließ sich nicht speichern: %s" % (name, fehler))
            return False

    def _token_speichern(self, dienst: str, wert: str) -> bool:
        """Schreibt den neuen Refresh-Token sofort nach ``config/.env``."""
        return self._einstellung_speichern(WEARABLE_DIENSTE[dienst]["token_name"], wert)

    @contextmanager
    def _sperre_nehmen(self):
        """Die Dateisperre über alle Jarvis-Prozesse. Liefert ``True``, wenn sie genommen wurde, sonst ``False``."""
        ende = time.monotonic() + max(0.0, float(self.sperr_wartezeit))
        while not self._fadensperre.acquire(False):
            if time.monotonic() >= ende:
                yield False
                return
            time.sleep(0.05)
        datei = None
        try:
            if fcntl is not None:
                pfad = Path(self.sperrdatei or (config.LOG_VERZEICHNIS / "erholung.lock"))
                try:
                    pfad.parent.mkdir(parents=True, exist_ok=True)
                    datei = open(str(pfad), "a")
                except OSError:
                    datei = None
                if datei is not None:
                    while True:
                        try:
                            fcntl.flock(datei.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                            break
                        except (BlockingIOError, OSError):
                            if time.monotonic() >= ende:
                                datei.close()
                                datei = None
                                yield False
                                return
                            time.sleep(0.05)
            yield True
        finally:
            if datei is not None:
                try:
                    fcntl.flock(datei.fileno(), fcntl.LOCK_UN)
                except OSError:
                    pass
                datei.close()
            self._fadensperre.release()

    # -- Abruf ------------------------------------------------------------------

    def _abruf_stempel(self, dienst: str) -> dict:
        zeilen = self.memory._lesen("SELECT * FROM erholung_abruf WHERE dienst=?", (dienst,))
        return zeilen[0] if zeilen else {"dienst": dienst, "zeit": 0.0, "warten_bis": 0.0, "status": ""}

    def _abruf_vermerken(self, dienst: str, gelungen: bool, warten_s: float = 0.0, status: str = ""):
        alt = self._abruf_stempel(dienst)
        jetzt = self._jetzt_s()
        self._aendern("INSERT OR REPLACE INTO erholung_abruf (dienst, zeit, warten_bis, status) VALUES (?,?,?,?)",
                      (dienst, jetzt if gelungen else alt["zeit"], jetzt + warten_s if warten_s else 0.0,
                       status[:200]))

    def _http_fehler(self, dienst: str, status: int, text: str, kopf: dict, token: bool = False) -> dict:
        """Aus einem fehlgeschlagenen Aufruf eine ehrliche Meldung machen (nie mit Schlüsseln darin).

        ``token``: der Aufruf ging an den Token-Dienst - dort heißt 400 "Schlüssel ungültig".
        """
        info = WEARABLE_DIENSTE[dienst]
        name = info["name"]
        if status == 0:
            return {"ok": False, "fehler": "%s ist gerade nicht erreichbar (%s)." % (name, str(text)[:80])}
        if status == 429:
            try:
                warten = max(60, min(86400, int(float((kopf or {}).get("retry-after", "3600")))))
            except (TypeError, ValueError):
                warten = 3600
            return {"ok": False, "warten_s": warten,
                    "fehler": "%s bittet um Geduld (zu viele Anfragen). Ich versuche es später wieder." % name}
        if status in (401, 403) or (token and status == 400):
            return {"ok": False, "neu_verbinden": True,
                    "fehler": "Der Zugang zu %s wird abgelehnt - er ist abgelaufen oder wurde widerrufen. "
                              "Bitte neu verbinden: python3 jarvis.py zugang %s" % (name, dienst)}
        return {"ok": False, "fehler": "%s antwortet mit Fehler %d." % (name, status)}

    def _token_holen(self, dienst: str, formular: dict) -> dict:
        """Ruft den Token-Dienst auf. ``{"ok", "access", "refresh"}`` oder ein Fehler."""
        info = WEARABLE_DIENSTE[dienst]
        status, text, kopf = self._holen("POST", info["token"], {}, formular)
        if status != 200:
            return self._http_fehler(dienst, status, text, kopf, token=True)
        antwort = _erh_json(text)
        if not antwort or not antwort.get("access_token"):
            return {"ok": False, "fehler": "%s hat keinen Zugangsschlüssel geliefert." % info["name"]}
        return {"ok": True, "access": str(antwort["access_token"]), "refresh": str(antwort.get("refresh_token") or "")}

    def abrufen(self, dienst, tage: int = 14, max_alter_h=None) -> dict:
        """Holt die neuesten Werte von Oura oder Whoop.

        Nimmt die Dateisperre, liest die .env neu, tauscht den Refresh-Token (er gilt nur
        einmal) und speichert den neuen sofort. Läuft der Abruf schon in einem anderen Jarvis-Fenster,
        oder bittet der Dienst um Geduld, wird sanft aufgegeben. ``max_alter_h``: nichts tun, wenn
        schon vor weniger Stunden geholt wurde.
        """
        dienst, info = self._dienst(dienst)
        if dienst is None:
            return {"ok": False, "fehler": "Das kenne ich nicht. Möglich sind oura und whoop."}
        kennung, geheim = self._einstellung(info["id_name"]), self._einstellung(info["geheim_name"])
        if not (kennung and geheim and self._einstellung(info["token_name"])):
            return {"ok": False, "fehler": "%s ist nicht verbunden. Einmalig: python3 jarvis.py zugang %s"
                                           % (info["name"], dienst)}
        stempel = self._abruf_stempel(dienst)
        if stempel["warten_bis"] > self._jetzt_s():
            return {"ok": False, "warten_s": int(stempel["warten_bis"] - self._jetzt_s()),
                    "fehler": "%s bittet um Geduld. Ich versuche es später wieder." % info["name"]}
        with self._sperre_nehmen() as bekommen:
            if not bekommen:
                return {"ok": False, "gesperrt": True,
                        "fehler": "%s wird gerade in einem anderen Jarvis-Fenster abgerufen. Ich warte nicht darauf."
                                  % info["name"]}
            if max_alter_h is not None:
                zuletzt = self._abruf_stempel(dienst)["zeit"]
                if zuletzt and self._jetzt_s() - zuletzt < float(max_alter_h) * 3600:
                    return {"ok": True, "uebersprungen": True, "text": "%s ist aktuell." % info["name"]}
            return self._abrufen_gesperrt(dienst, tage)

    def _abrufen_gesperrt(self, dienst: str, tage: int, zugang: str = None) -> dict:
        """Der Abruf selbst - nur unter der Sperre aufrufen."""
        info = WEARABLE_DIENSTE[dienst]
        warnung = ""
        if zugang is None:
            if self._env_lesen_fn is None:
                try:
                    config.env_neu_laden()  # nur hier, unter der Sperre: ein anderer Prozess hat evtl. rotiert
                except Exception as fehler:
                    print("[erholung] .env nicht neu gelesen: %s" % fehler)
            refresh = self._einstellung(info["token_name"])
            if not refresh:
                return {"ok": False, "fehler": "%s ist nicht verbunden. python3 jarvis.py zugang %s"
                                               % (info["name"], dienst)}
            formular = {"grant_type": "refresh_token", "refresh_token": refresh,
                        "client_id": self._einstellung(info["id_name"]),
                        "client_secret": self._einstellung(info["geheim_name"])}
            if dienst == "whoop":
                formular["scope"] = "offline"  # laut Whoop-Beschreibung beim Erneuern; zu prüfen
            antwort = self._token_holen(dienst, formular)
            if not antwort.get("ok"):
                self._abruf_vermerken(dienst, False, antwort.get("warten_s") or 0, antwort.get("fehler", ""))
                return antwort
            if antwort["refresh"] and antwort["refresh"] != refresh:
                if not self._token_speichern(dienst, antwort["refresh"]):
                    warnung = ("Der neue Zugangsschlüssel für %s ließ sich nicht speichern - beim nächsten Mal "
                               "muss ich neu verbunden werden: python3 jarvis.py zugang %s" % (info["name"], dienst))
            zugang = antwort["access"]
        try:
            ergebnis = self._oura_holen(zugang, tage) if dienst == "oura" else self._whoop_holen(zugang, tage)
        except Exception as fehler:  # eine unerwartete Antwort darf den Abruf nicht sprengen
            ergebnis = {"ok": False, "fehler": "%s: die Antwort ließ sich nicht lesen (%s)." % (info["name"], fehler)}
        self._abruf_vermerken(dienst, bool(ergebnis.get("ok")), ergebnis.get("warten_s") or 0,
                              "" if ergebnis.get("ok") else ergebnis.get("fehler", ""))
        if warnung:
            ergebnis["warnung"] = warnung
            if ergebnis.get("ok"):
                ergebnis["text"] = ergebnis.get("text", "") + " " + warnung
        return ergebnis

    def oura_holen(self, tage: int = 14) -> dict:
        """Die Readiness-Werte der letzten Tage von Oura."""
        return self.abrufen("oura", tage)

    def whoop_holen(self, tage: int = 14) -> dict:
        """Die Recovery-Werte der letzten Tage von Whoop."""
        return self.abrufen("whoop", tage)

    def aktualisieren(self, max_alter_h: float = ABRUF_MIN_STUNDEN) -> list:
        """Holt von jedem verbundenen Wearable, wenn der letzte Abruf länger her ist. Ergebnisse als Liste."""
        ergebnisse = []
        for dienst, verbunden in self.verbunden().items():
            if verbunden:
                ergebnisse.append(dict(self.abrufen(dienst, 14, max_alter_h=max_alter_h), dienst=dienst))
        return ergebnisse

    def _oura_seiten(self, pfad: str, von: str, bis: str, kopf: dict):
        """Alle Seiten einer Oura-Liste. ``(Liste, Fehler)``."""
        eintraege, nach = [], None
        for _seite in range(6):
            adresse = OURA_DATEN_URL + pfad + "?" + urllib.parse.urlencode(
                dict({"start_date": von, "end_date": bis}, **({"next_token": nach} if nach else {})))
            status, text, antwortkopf = self._holen("GET", adresse, kopf, None)
            if status != 200:
                return None, self._http_fehler("oura", status, text, antwortkopf)
            antwort = _erh_json(text)
            if antwort is None or not isinstance(antwort.get("data"), list):
                return None, {"ok": False, "fehler": "Oura: die Antwort ließ sich nicht lesen."}
            eintraege += [e for e in antwort["data"] if isinstance(e, dict)]
            nach = antwort.get("next_token")
            if not nach:
                break
        return eintraege, None

    def _oura_holen(self, zugang: str, tage: int) -> dict:
        heute = self._uhr().date()
        von = (heute - timedelta(days=max(1, int(tage)))).isoformat()
        bis = (heute + timedelta(days=1)).isoformat()  # ob end_date einschließt, ist zu prüfen
        kopf = {"Authorization": "Bearer " + zugang}
        bereitschaft, fehler = self._oura_seiten("daily_readiness", von, bis, kopf)
        if fehler:
            return fehler
        schlaf_wert, _ = self._oura_seiten("daily_sleep", von, bis, kopf)
        perioden, _ = self._oura_seiten("sleep", von, bis, kopf)  # beides darf fehlen, Readiness reicht
        je_tag = {}
        for periode in perioden or []:
            tag = erholung_tag_text(periode.get("day"))
            if not tag:
                continue
            dauer = _erh_zahl(periode.get("total_sleep_duration"))
            neu = {"lang": periode.get("type") == "long_sleep", "dauer": dauer,
                   "hrv": _erh_zahl(periode.get("average_hrv")), "puls": _erh_zahl(periode.get("lowest_heart_rate"))}
            alt = je_tag.get(tag)
            # Die lange Nachtschlafperiode zählt; unter mehreren gleichen die längste.
            if alt is None or (neu["lang"], dauer or 0) > (alt["lang"], alt["dauer"] or 0):
                je_tag[tag] = neu
        schlafwerte = {erholung_tag_text(e.get("day")): _erh_zahl(e.get("score")) for e in schlaf_wert or []}
        zeilen = []
        for eintrag in bereitschaft:
            tag = erholung_tag_text(eintrag.get("day"))
            wert = _erh_zahl(eintrag.get("score"))
            if not tag or wert is None or not 0 <= wert <= 100:
                continue
            periode = je_tag.get(tag) or {}
            schlaf_h = periode["dauer"] / 3600.0 if periode.get("dauer") else None
            zeilen.append((tag, wert, periode.get("hrv"), periode.get("puls"), schlaf_h,
                           {"schlafwert": schlafwerte.get(tag)}))
        return self._abruf_ergebnis("oura", zeilen)

    def _whoop_holen(self, zugang: str, tage: int) -> dict:
        jetzt = self._uhr().astimezone(timezone.utc).replace(tzinfo=None)
        von = (jetzt - timedelta(days=max(1, int(tage)))).strftime("%Y-%m-%dT%H:%M:%S.000Z")
        bis = (jetzt + timedelta(days=1)).strftime("%Y-%m-%dT%H:%M:%S.000Z")
        kopf = {"Authorization": "Bearer " + zugang}
        eintraege, nach = [], None
        for _seite in range(5):  # Seitenaufbau (records, next_token) ist zu prüfen
            parameter = {"start": von, "end": bis, "limit": 25}
            if nach:
                parameter["nextToken"] = nach
            status, text, antwortkopf = self._holen("GET", WHOOP_RECOVERY_URL + "?" + urllib.parse.urlencode(parameter),
                                                    kopf, None)
            if status != 200:
                return self._http_fehler("whoop", status, text, antwortkopf)
            antwort = _erh_json(text)
            if antwort is None or not isinstance(antwort.get("records"), list):
                return {"ok": False, "fehler": "Whoop: die Antwort ließ sich nicht lesen."}
            eintraege += [e for e in antwort["records"] if isinstance(e, dict)]
            nach = antwort.get("next_token")
            if not nach:
                break
        zeilen = {}
        for eintrag in eintraege:
            punkte = eintrag.get("score") if isinstance(eintrag.get("score"), dict) else {}
            wert = _erh_zahl(punkte.get("recovery_score"))
            if str(eintrag.get("score_state") or "SCORED").upper() != "SCORED" or wert is None or not 0 <= wert <= 100:
                continue
            zeit = _erh_iso_lesen(eintrag.get("created_at") or eintrag.get("updated_at"))
            if zeit is None:
                continue
            tag = (zeit.astimezone() if zeit.tzinfo else zeit).date().isoformat()
            zeilen[tag] = (tag, wert, _erh_zahl(punkte.get("hrv_rmssd_milli")),
                           _erh_zahl(punkte.get("resting_heart_rate")), None, {"hrv_art": "RMSSD"})
        return self._abruf_ergebnis("whoop", list(zeilen.values()))

    def _abruf_ergebnis(self, dienst: str, zeilen: list) -> dict:
        info = WEARABLE_DIENSTE[dienst]
        if not zeilen:
            return {"ok": True, "tage": 0, "text": "%s hat für diese Tage keine Erholungswerte geliefert." % info["name"]}
        self._tage_speichern(info["quelle"], zeilen)
        letzter = sorted(zeilen)[-1]
        wert = int(round(letzter[1]))
        return {"ok": True, "tage": len(zeilen), "letzter_tag": letzter[0], "wert": wert,
                "text": "%s: %d Tage geholt, der letzte (%s) mit %d von 100." % (
                    info["name"], len(zeilen), erholung_datum_text(letzter[0]), wert)}

    # -- Anmeldung (OAuth) ------------------------------------------------------

    def oauth_start(self, dienst, port: int = 8765) -> dict:
        """Beginnt die Anmeldung. Gibt ``{"ok", "url", "zustand", "redirect"}`` zurück.

        Der ``state`` (bei Oura 24 Zeichen, bei Whoop genau 8) steht in der Datenbank, gilt zehn
        Minuten und genau einmal - egal, in welchem Prozess die Anmeldung endet.
        """
        dienst, info = self._dienst(dienst)
        if dienst is None:
            return {"ok": False, "fehler": "Das kenne ich nicht. Möglich sind oura und whoop."}
        kennung = self._einstellung(info["id_name"])
        if not kennung:
            return {"ok": False, "fehler": "Es fehlt die Client-ID von %s (%s). python3 jarvis.py zugang %s"
                                           % (info["name"], info["id_name"], dienst)}
        alphabet = string.ascii_letters + string.digits
        zustand = "".join(secrets.choice(alphabet) for _ in range(info["state_laenge"]))
        redirect = "http://localhost:%d/%s/rueckruf" % (int(port), dienst)
        jetzt = self._jetzt_s()
        self._aendern("DELETE FROM erholung_oauth WHERE erstellt<?", (jetzt - 86400,))
        self._aendern("INSERT INTO erholung_oauth (zustand, dienst, redirect, erstellt, benutzt) VALUES (?,?,?,?,0)",
                      (zustand, dienst, redirect, jetzt))
        url = "%s?response_type=code&client_id=%s&redirect_uri=%s&scope=%s&state=%s" % (
            info["autorisieren"], urllib.parse.quote(kennung, safe=""), urllib.parse.quote(redirect, safe=""),
            urllib.parse.quote(info["scope"], safe=":"), zustand)
        return {"ok": True, "url": url, "zustand": zustand, "redirect": redirect}

    def oauth_abschluss(self, dienst, code, zustand) -> dict:
        """Beendet die Anmeldung: prüft den ``state``, tauscht den Code gegen die Schlüssel, holt erste Werte.

        Die Web-Adresse ``/oura/rueckruf`` und ``/whoop/rueckruf`` ruft das auf. Ein falscher,
        schon benutzter oder abgelaufener ``state`` wird abgewiesen.
        """
        dienst, info = self._dienst(dienst)
        passt_nicht = {"ok": False, "fehler": "Die Anmeldung passt nicht zu der, die ich gestartet habe. "
                                              "Bitte noch einmal: python3 jarvis.py zugang %s" % (dienst or "oura")}
        code, zustand = str(code or "").strip(), str(zustand or "").strip()
        if dienst is None or not code or not zustand or len(zustand) > 64 or len(code) > 2000:
            return passt_nicht
        zeilen = self.memory._lesen("SELECT * FROM erholung_oauth WHERE zustand=? AND dienst=?", (zustand, dienst))
        if not zeilen:
            return passt_nicht
        # Einmalig und befristet: nur wer die Zeile von "ungenutzt" auf "benutzt" setzt, darf weiter.
        genommen = self._aendern("UPDATE erholung_oauth SET benutzt=1 WHERE zustand=? AND dienst=? "
                                 "AND benutzt=0 AND erstellt>=?",
                                 (zustand, dienst, self._jetzt_s() - OAUTH_GUELTIG_SEKUNDEN))
        if genommen != 1:
            return passt_nicht
        kennung, geheim = self._einstellung(info["id_name"]), self._einstellung(info["geheim_name"])
        if not (kennung and geheim):
            return {"ok": False, "fehler": "Client-ID oder Client-Secret von %s fehlen. python3 jarvis.py zugang %s"
                                           % (info["name"], dienst)}
        with self._sperre_nehmen() as bekommen:
            if not bekommen:
                return {"ok": False, "fehler": "%s wird gerade in einem anderen Jarvis-Fenster bearbeitet. "
                                               "Bitte gleich noch einmal." % info["name"]}
            antwort = self._token_holen(dienst, {
                "grant_type": "authorization_code", "code": code, "redirect_uri": zeilen[0]["redirect"],
                "client_id": kennung, "client_secret": geheim})
            if not antwort.get("ok"):
                return antwort
            if not antwort["refresh"]:
                return {"ok": False, "fehler": "%s hat keinen dauerhaften Zugang geliefert. Bei Whoop muss der "
                                               "Bereich 'offline' freigegeben sein." % info["name"]}
            if not self._token_speichern(dienst, antwort["refresh"]):
                return {"ok": False, "fehler": "Der Zugangsschlüssel für %s ließ sich nicht in config/.env speichern."
                                               % info["name"]}
            ersten = self._abrufen_gesperrt(dienst, 14, zugang=antwort["access"])
        text = "%s ist verbunden. Du kannst dieses Fenster schließen." % info["name"]
        if ersten.get("ok") and ersten.get("text"):
            text += " " + ersten["text"]
        elif ersten.get("fehler"):
            text += " Die ersten Werte konnte ich noch nicht holen: %s" % ersten["fehler"]
        return {"ok": True, "dienst": dienst, "text": text}

    def oauth_im_terminal(self, dienst, fragen=None, fragen_geheim=None, ausgabe=None, oeffnen=None, port: int = 8765) -> bool:
        """Verbindet Oura oder Whoop im Terminal: ``python3 jarvis.py zugang oura``.

        Fragt, was fehlt (Client-ID, Client-Secret), druckt die Anmeldeadresse und liest die Adresse
        zurück, auf der der Browser gelandet ist - der Ausweg, wenn der Dienst eine localhost-Weiterleitung
        ablehnt oder die Web-App gerade nicht läuft.
        """
        fragen = fragen or input
        fragen_geheim = fragen_geheim or getpass.getpass
        sagen = ausgabe or print
        dienst, info = self._dienst(dienst)
        if dienst is None:
            sagen("Das kenne ich nicht. Möglich sind oura und whoop.")
            return False
        sagen("%s verbinden. Dafür brauchst du einmalig eine eigene App im Entwicklerbereich von %s:\n"
              "  %s\n"
              "Als Weiterleitungsadresse (Redirect URI) trägst du dort genau ein:\n"
              "  http://localhost:%d/%s/rueckruf" % (info["name"], info["name"], info["app_seite"], port, dienst))
        kennung = self._einstellung(info["id_name"])
        if not kennung:
            kennung = str(fragen("Client-ID: ")).strip()
            if not kennung:
                sagen("Ohne Client-ID geht es nicht. Es wurde nichts geändert.")
                return False
            self._einstellung_speichern(info["id_name"], kennung)
        if not self._einstellung(info["geheim_name"]):
            geheim = str(fragen_geheim("Client-Secret (wird nicht angezeigt): ")).strip()
            if not geheim:
                sagen("Ohne Client-Secret geht es nicht. Es wurde nichts geändert.")
                return False
            self._einstellung_speichern(info["geheim_name"], geheim)
        vorher = self._einstellung(info["token_name"])
        start = self.oauth_start(dienst, port)
        if not start.get("ok"):
            sagen(start["fehler"])
            return False
        sagen("\nÖffne diese Adresse im Browser, melde dich an und erlaube den Zugriff:\n\n  %s\n" % start["url"])
        if oeffnen is not None:
            oeffnen(start["url"])
        sagen("Läuft Jarvis gerade in der Web-App und der Browser zeigt '%s ist verbunden', dann drück hier nur "
              "Enter. Sonst zeigt der Browser einen Fehler, weil unter localhost nichts antwortet - kopiere dann "
              "die ganze Adresse aus der Adresszeile (sie beginnt mit http://localhost:%d/%s/rueckruf?code=...) "
              "und füge sie hier ein." % (info["name"], port, dienst))
        eingabe = str(fragen("Adresse (oder nur Enter): ")).strip()
        if not eingabe:
            nachher = self._einstellung(info["token_name"])
            if nachher and nachher != vorher:
                sagen("%s ist verbunden." % info["name"])
                return True
            sagen("Es ist noch nichts angekommen. Starte noch einmal: python3 jarvis.py zugang %s" % dienst)
            return False
        abfrage = urllib.parse.parse_qs(urllib.parse.urlsplit(eingabe).query)
        code, zustand = (abfrage.get("code") or [""])[0], (abfrage.get("state") or [""])[0]
        if not code or not zustand:
            sagen("In der Adresse fehlen code und state. Ich brauche die ganze Adresse aus dem Browser.")
            return False
        ergebnis = self.oauth_abschluss(dienst, code, zustand)
        sagen(ergebnis.get("text") or ergebnis.get("fehler") or "")
        return bool(ergebnis.get("ok"))

    # -- Vergessen --------------------------------------------------------------

    def vergessen(self) -> dict:
        """Löscht alle Erholungs- und Handruhe-Werte (und was sonst davon im Protokoll steht)."""
        geloescht = {}
        for tabelle in ("erholung_tage", "handruhe", "erholung_oauth", "erholung_abruf"):
            try:
                geloescht[tabelle] = self._aendern("DELETE FROM %s" % tabelle)
            except sqlite3.Error:
                pass  # die Tabelle gibt es (noch) nicht
        platz = ",".join("?" for _ in GESUNDHEITS_WERKZEUGE)
        for sql, werte in (("DELETE FROM aktionen WHERE werkzeug IN (%s)" % platz, GESUNDHEITS_WERKZEUGE),
                           ("DELETE FROM kennzahlen WHERE name=?", ("handruhe_mm",))):
            try:
                self._aendern(sql, tuple(werte))
            except sqlite3.Error:
                pass
        if self.anzeige is not None:
            try:
                self.anzeige.melden("sicht", {})
            except Exception as fehler:
                print("[erholung] Anzeige nicht geleert: %s" % fehler)
        tage = geloescht.get("erholung_tage", 0) or 0
        return {"ok": True, "geloescht": geloescht,
                "text": "Gelöscht: %d Erholungstage und alle Handruhe-Messungen. Die Verbindung zu Oura oder "
                        "Whoop bleibt; getrennt wird sie, indem du die Schlüssel aus config/.env entfernst. "
                        "Was wir im Gespräch darüber besprochen haben, steht im Gesprächsverlauf." % tage}


# ---------------------------------------------------------------------------
# Anzeige: der Kanal "sicht" gehört mehreren (Erholung, Handruhe, Zusammenhang)
# ---------------------------------------------------------------------------

def sicht_teil_schreiben(anzeige, teil: dict, dauer_s: float = 120):
    """Ergänzt den Kanal ``sicht`` um ``teil`` (``erholung`` oder ``zusammenhang``) und zeigt die Ansicht.

    Der Kanal wird als Ganzes ersetzt, deshalb wird erst gelesen, was schon drinsteht - die
    Handruhe-Werte bleiben also stehen. Im Diskretmodus liest das nichts zurück (der Speicher
    gäbe nur Leeres her). ``anzeige`` braucht ``melden`` und ``zeigen``; ohne Anzeige tut das nichts.
    """
    if anzeige is None:
        return
    try:
        aktuell = {}
        speicher = getattr(anzeige, "anzeige", None) or anzeige
        lesen = getattr(speicher, "stand", None)
        if callable(lesen) and not config.ANZEIGE_DISKRET:
            stand = lesen("sicht") or {}
            if isinstance(stand.get("daten"), dict):
                aktuell = dict(stand["daten"])
        aktuell.update(teil)
        aktuell["hinweis"] = ERHOLUNG_HINWEIS
        anzeige.melden("sicht", aktuell)
        anzeige.zeigen("sicht", {}, dauer_s, "erholung")
    except Exception as fehler:  # die Anzeige darf nie etwas kaputt machen
        print("[erholung] Anzeige: %s" % fehler)


# ---------------------------------------------------------------------------
# Terminal: python3 jarvis.py gesundheit ... und zugang oura|whoop
# ---------------------------------------------------------------------------

def gesundheit_im_terminal(argumente=None, memory=None, fragen=None, ausgabe=None) -> int:
    """``jarvis.py gesundheit [Datei | vergessen]`` - Export einlesen, Stand zeigen oder alles löschen."""
    sagen = ausgabe or print
    fragen = fragen or input
    erholung = Erholung(memory or Memory())
    argumente = [a for a in (argumente or []) if str(a).strip()]
    if argumente and argumente[0].strip().lower() == "vergessen":
        antwort = str(fragen("Alle Erholungs- und Handruhe-Werte löschen? (ja/nein) ")).strip().lower()
        if antwort not in ("ja", "j"):
            sagen("Nichts gelöscht.")
            return 1
        sagen(erholung.vergessen()["text"])
        return 0
    if argumente:
        ergebnis = erholung.importieren(" ".join(argumente), hintergrund=False)
        sagen(ergebnis.get("text") or ergebnis.get("fehler") or "")
        return 0 if ergebnis.get("ok") else 1
    stand = erholung.status()
    sagen("Gesundheit und Erholung (%s)" % ERHOLUNG_HINWEIS)
    if stand["quellen"]:
        for zeile in stand["quellen"]:
            sagen("  %s: %d Tage, %s bis %s" % (zeile["quelle"], zeile["n"], zeile["von"], zeile["bis"]))
    else:
        sagen("  Noch keine Erholungswerte gespeichert.")
    for dienst, ja in stand["verbunden"].items():
        sagen("  %s: %s" % (WEARABLE_DIENSTE[dienst]["name"],
                            "verbunden" if ja else "nicht verbunden (python3 jarvis.py zugang %s)" % dienst))
    sagen("\nExport einlesen:  python3 jarvis.py gesundheit ~/Downloads/export.zip\n"
          "Alles löschen:    python3 jarvis.py gesundheit vergessen")
    return 0


def wearable_zugang_im_terminal(dienst: str) -> int:
    """``jarvis.py zugang oura|whoop`` - die Anmeldung im Terminal."""
    erholung = Erholung(Memory())

    def browser_oeffnen(adresse):
        try:
            subprocess.run(["open", adresse], shell=False, timeout=15,
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except (OSError, subprocess.SubprocessError):
            pass

    return 0 if erholung.oauth_im_terminal(dienst, oeffnen=browser_oeffnen) else 1
