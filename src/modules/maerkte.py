#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Börsen- und Rohstoffkurse für die Märkte-Ansicht - verzögert, mit Quelle und Uhrzeit.

Alles ohne Schlüssel. Die Quellen und ihre Bedingungen:

* **Yahoo Finance** (inoffizielle Schnittstelle ``v8/finance``): nirgends
  dokumentiert, nur für den persönlichen Gebrauch, kann jederzeit ausfallen.
  Antwortet nur mit dem Kennzeichen ``User-Agent: Mozilla/5.0`` - mit dem von
  urllib, curl oder einem vollen Chrome-Kennzeichen kommt Fehler 429. Die Kurse
  sind etwa 15 Minuten verzögert. Jede Antwort wird eine Minute vorgehalten.
* **CoinGecko** (``simple/price``): Ersatz für Bitcoin und Ethereum, ohne
  Schlüssel mit geteilter Begrenzung; ein freiwilliger Demo-Schlüssel
  (``COINGECKO_SCHLUESSEL``) geht im Kopf ``x-cg-demo-api-key`` mit.
* **EZB** (Referenzkurs Euro/Dollar): Ersatz für den Wechselkurs, amtlich,
  nur an Werktagen, einmal am Tag um 14:15 Uhr.

Genannt werden nur Zahlen - keine Anlageberatung. Was nicht abrufbar war,
steht unter "fehlend" und wird nie geschätzt.
"""

import copy
import csv
import io
import json
import math
import re
import threading
import time
import urllib.parse
from datetime import datetime

import config
from modules.nachrichten import netz_fehlertext, netz_holen, zeit_sprechbar

YAHOO_SPARK = "https://query1.finance.yahoo.com/v8/finance/spark"
YAHOO_CHART = "https://query1.finance.yahoo.com/v8/finance/chart/%s?range=5d&interval=1d"
COINGECKO_PREIS = ("https://api.coingecko.com/api/v3/simple/price?ids=bitcoin,ethereum"
                   "&vs_currencies=eur&include_24hr_change=true&include_last_updated_at=true")
EZB_KURS = ("https://data-api.ecb.europa.eu/service/data/EXR/D.USD.EUR.SP00.A"
            "?format=csvdata&lastNObservations=30")
# Genau so - jedes andere Kennzeichen bekommt von Yahoo Fehler 429.
YAHOO_KOPF = {"User-Agent": "Mozilla/5.0"}
MARKT_UA = "Jarvis/1.0 (persoenlicher Assistent)"
MARKT_TIMEOUT = 12.0
MARKT_ZWISCHENSPEICHER_S = 60
MARKT_VERLAUF_PUNKTE = 60
MARKT_HOECHSTENS = 12

# Schlüssel -> (Yahoo-Symbol, Name, Einheit)
SYMBOLE = {
    "dax": ("^GDAXI", "DAX", "Punkte"),
    "atx": ("^ATX", "ATX", "Punkte"),
    "eurostoxx": ("^STOXX50E", "Euro Stoxx 50", "Punkte"),
    "sp500": ("^GSPC", "S&P 500", "Punkte"),
    "nasdaq": ("^IXIC", "Nasdaq Composite", "Punkte"),
    "nasdaq100": ("^NDX", "Nasdaq 100", "Punkte"),
    "vix": ("^VIX", "VIX", "Punkte"),
    "brent": ("BZ=F", "Brent-Öl", "Dollar je Barrel"),
    "wti": ("CL=F", "WTI-Öl", "Dollar je Barrel"),
    "gold": ("GC=F", "Gold", "Dollar je Unze"),
    "eurusd": ("EURUSD=X", "Euro in Dollar", ""),
    "bitcoin": ("BTC-EUR", "Bitcoin", "Euro"),
    "ethereum": ("ETH-EUR", "Ethereum", "Euro"),
}
MARKT_STANDARD = ["dax", "sp500", "nasdaq", "eurostoxx", "brent", "gold", "eurusd", "bitcoin"]
QUELLE_YAHOO = "Yahoo Finance"
QUELLE_COINGECKO = "CoinGecko"
QUELLE_EZB = "EZB-Referenzkurs"
WAEHRUNGEN = {"EUR": "Euro", "USD": "Dollar", "CHF": "Franken", "GBP": "Pfund",
              "GBp": "Pence", "JPY": "Yen", "CNY": "Yuan", "SEK": "Kronen", "NOK": "Kronen",
              "DKK": "Kronen", "PLN": "Złoty", "CZK": "Kronen", "HKD": "Hongkong-Dollar",
              "CAD": "Kanadische Dollar", "AUD": "Australische Dollar"}
AKTIEN_MUSTER = re.compile(r"^[A-Z0-9][A-Z0-9.\-=^]{0,14}$")
HINWEIS_KURSE = "Verzögerte Kurse – nur Zahlen nennen, keine Anlageberatung."


# ---------------------------------------------------------------------------
# Zahlen und Texte
# ---------------------------------------------------------------------------

def zahl_de(wert, stellen: int = 2) -> str:
    """Eine Zahl auf Deutsch: 25153.5 → "25.154", 102.014 → "102,01"."""
    text = "{:,.{}f}".format(float(wert), max(0, int(stellen)))
    return text.replace(",", "\x00").replace(".", ",").replace("\x00", ".")


def markt_stellen(schluessel: str, wert) -> int:
    """Nachkommastellen wie auf der Zentrale: Euro-Dollar 4, ab 1000 keine, sonst 2."""
    if schluessel == "eurusd":
        return 4
    return 0 if abs(float(wert)) >= 1000 else 2


def aenderung_text(prozent) -> str:
    """"plus 1,4 Prozent", "minus 1,2 Prozent" oder "unverändert"."""
    if prozent is None:
        return ""
    if abs(prozent) < 0.05:
        return "unverändert"
    return "%s %s Prozent" % ("plus" if prozent > 0 else "minus", zahl_de(abs(prozent), 1))


def verlauf_kuerzen(werte: list, hoechstens: int = MARKT_VERLAUF_PUNKTE) -> list:
    """Höchstens ``hoechstens`` Punkte, gleichmäßig verteilt, der letzte immer dabei."""
    werte = list(werte or [])
    if len(werte) <= hoechstens:
        return werte
    schritt = (len(werte) - 1) / float(hoechstens - 1)
    return [werte[int(round(i * schritt))] for i in range(hoechstens)]


def _markt_runden(wert: float) -> float:
    return round(wert, 4) if abs(wert) < 10 else round(wert, 2)


def _gueltig(wert) -> bool:
    return isinstance(wert, (int, float)) and not isinstance(wert, bool) and math.isfinite(wert)


def _zeit_aus_epoche(sekunden) -> str:
    try:
        return datetime.fromtimestamp(float(sekunden)).astimezone().isoformat(timespec="minutes")
    except (TypeError, ValueError, OverflowError, OSError):
        return ""


def _prozent(neu, alt):
    if _gueltig(neu) and _gueltig(alt) and alt:
        return round((float(neu) / float(alt) - 1) * 100, 2)
    return None


# ---------------------------------------------------------------------------
# Leser der Quellen
# ---------------------------------------------------------------------------

def _json(obj):
    if isinstance(obj, bytes):
        return json.loads(obj.decode("utf-8"))
    if isinstance(obj, str):
        return json.loads(obj)
    return obj


def spark_lesen(obj, zeitraum: str = "heute") -> dict:
    """Liest Yahoos ``spark``-Antwort: ``{symbol: {wert, aenderung_prozent, verlauf, zeit}}``.

    Fehlende Schlusskurse (``None``) fallen weg. Die Änderung ist für "heute"
    die zum Vortagesschluss, für "monat" die des letzten Tages.
    """
    obj = _json(obj)
    eintraege = []
    if isinstance(obj, dict) and isinstance(obj.get("spark"), dict):
        # Ältere Form: {"spark": {"result": [{"symbol", "response": [{meta, timestamp, indicators}]}]}}
        for teil in obj["spark"].get("result") or []:
            antwort = (teil.get("response") or [{}])[0] or {}
            meta = antwort.get("meta") or {}
            schluss = (((antwort.get("indicators") or {}).get("quote") or [{}])[0] or {}).get("close")
            eintraege.append((teil.get("symbol") or meta.get("symbol"),
                              {"timestamp": antwort.get("timestamp") or [], "close": schluss or [],
                               "previousClose": meta.get("previousClose"),
                               "chartPreviousClose": meta.get("chartPreviousClose")}))
    elif isinstance(obj, dict):
        for symbol, teil in obj.items():
            if isinstance(teil, dict):
                eintraege.append((teil.get("symbol") or symbol, teil))
    ergebnis = {}
    for symbol, teil in eintraege:
        if not symbol:
            continue
        zeiten = list(teil.get("timestamp") or [])
        schluss = list(teil.get("close") or [])
        if len(zeiten) != len(schluss):
            zeiten = [None] * len(schluss)
        paare = [(t, float(c)) for t, c in zip(zeiten, schluss) if _gueltig(c)]
        if not paare:
            continue
        werte = [c for _, c in paare]
        wert = werte[-1]
        if zeitraum == "monat":
            aenderung = _prozent(werte[-1], werte[-2]) if len(werte) >= 2 else None
        else:
            aenderung = _prozent(wert, teil.get("previousClose") or teil.get("chartPreviousClose"))
        if aenderung is None and _gueltig(teil.get("fulldayChangePercent")):
            aenderung = round(float(teil["fulldayChangePercent"]), 2)
        ergebnis[symbol] = {"wert": _markt_runden(wert), "aenderung_prozent": aenderung,
                            "verlauf": [_markt_runden(v) for v in verlauf_kuerzen(werte)],
                            "zeit": _zeit_aus_epoche(paare[-1][0]) if paare[-1][0] else ""}
    return ergebnis


def yahoo_chart_lesen(obj):
    """Liest ``v8/finance/chart`` für ein Symbol. Gibt ``None`` zurück, wenn kein Kurs drin ist."""
    obj = _json(obj)
    ergebnisse = ((obj or {}).get("chart") or {}).get("result") or []
    if not ergebnisse:
        return None
    teil = ergebnisse[0] or {}
    meta = teil.get("meta") or {}
    zeiten = list(teil.get("timestamp") or [])
    schluss = list((((teil.get("indicators") or {}).get("quote") or [{}])[0] or {}).get("close") or [])
    if len(zeiten) != len(schluss):
        zeiten = [None] * len(schluss)
    paare = [(t, float(c)) for t, c in zip(zeiten, schluss) if _gueltig(c)]
    preis = meta.get("regularMarketPrice")
    if not _gueltig(preis):
        preis = paare[-1][1] if paare else None
    if preis is None:
        return None
    aenderung = meta.get("regularMarketChangePercent")
    aenderung = round(float(aenderung), 2) if _gueltig(aenderung) else None
    if aenderung is None:
        vorher = meta.get("previousClose")
        markt_zeit = meta.get("regularMarketTime")
        if not _gueltig(vorher) and paare and _gueltig(markt_zeit):
            # chartPreviousClose ist der Schluss vor dem ganzen Zeitraum - unbrauchbar.
            tag = datetime.fromtimestamp(markt_zeit).date()
            frueher = [c for t, c in paare if t and datetime.fromtimestamp(t).date() < tag]
            vorher = frueher[-1] if frueher else None
        aenderung = _prozent(preis, vorher)
    name = " ".join(str(meta.get("longName") or meta.get("shortName") or meta.get("symbol") or "").split())
    return {"wert": _markt_runden(float(preis)), "aenderung_prozent": aenderung,
            "verlauf": [_markt_runden(c) for _, c in paare],
            "zeit": _zeit_aus_epoche(meta.get("regularMarketTime") or (paare[-1][0] if paare else None)),
            "name": name, "waehrung": str(meta.get("currency") or "")}


def coingecko_lesen(obj) -> dict:
    """Liest CoinGeckos ``simple/price``: ``{bitcoin: {...}, ethereum: {...}}`` in Euro."""
    obj = _json(obj)
    ergebnis = {}
    for schluessel in ("bitcoin", "ethereum"):
        teil = (obj or {}).get(schluessel) if isinstance(obj, dict) else None
        if not isinstance(teil, dict) or not _gueltig(teil.get("eur")):
            continue
        aenderung = teil.get("eur_24h_change")
        ergebnis[schluessel] = {"wert": _markt_runden(float(teil["eur"])),
                                "aenderung_prozent": round(float(aenderung), 2)
                                if _gueltig(aenderung) else None,
                                "verlauf": [], "zeit": _zeit_aus_epoche(teil.get("last_updated_at"))}
    return ergebnis


def ezb_lesen(text):
    """Liest den EZB-Referenzkurs (CSV). Gibt ``{wert, aenderung_prozent, verlauf, zeit, datum}``
    oder ``None`` zurück."""
    if isinstance(text, bytes):
        text = text.decode("utf-8-sig", errors="replace")
    punkte = []
    for zeile in csv.DictReader(io.StringIO(str(text or ""))):
        try:
            datum = str(zeile["TIME_PERIOD"]).strip()
            wert = float(zeile["OBS_VALUE"])
        except (KeyError, TypeError, ValueError):
            continue
        if re.match(r"^\d{4}-\d\d-\d\d$", datum) and _gueltig(wert):
            punkte.append((datum, wert))
    if not punkte:
        return None
    punkte.sort()
    werte = [w for _, w in punkte]
    datum = punkte[-1][0]
    # Der Referenzkurs wird um 14:15 Uhr in Frankfurt festgestellt.
    zeit = datetime.strptime(datum, "%Y-%m-%d").replace(hour=14, minute=15).astimezone()
    return {"wert": round(werte[-1], 4),
            "aenderung_prozent": _prozent(werte[-1], werte[-2]) if len(werte) >= 2 else None,
            "verlauf": [round(w, 4) for w in verlauf_kuerzen(werte)],
            "zeit": zeit.isoformat(timespec="minutes"), "datum": datum}


def freigabe_aktienkurs(a: dict) -> tuple:
    """Was und Wie für die Freigabefrage (nur nach fremdem Inhalt nötig)."""
    return ("den Kurs von %s bei Yahoo Finance abfragen" % " ".join(str(a.get("symbol") or "?").split()),
            "Das Kürzel geht an Yahoo Finance. Gefragt wird, weil vorher fremder Text gelesen wurde.")


# ---------------------------------------------------------------------------
# Märkte
# ---------------------------------------------------------------------------

class Maerkte:
    """Kurse der Beobachtungsliste und einzelner Aktien."""

    def __init__(self, anzeige=None, holen=None, uhr=None):
        # "anzeige" braucht nur zeigen(modus, daten, dauer_s=, quelle=) - in Jarvis
        # sind das die Werkzeuge, die im Hintergrund nichts umschalten.
        self.anzeige = anzeige
        self._holen = holen or netz_holen
        self._uhr = uhr or time.time
        self._sperre = threading.Lock()
        self._zwischenspeicher = {}

    # -- Hilfen -------------------------------------------------------------

    @staticmethod
    def auswahl_lesen(auswahl=None) -> tuple:
        """Welche Kurse gemeint sind. Gibt ``(schlüssel, unbekannt)`` zurück.

        Ohne Auswahl gilt die Beobachtungsliste ``MARKT_BEOBACHTUNG``.
        """
        if isinstance(auswahl, str):
            auswahl = auswahl.split(",")
        roh = [str(x).strip().lower() for x in (auswahl or []) if str(x).strip()]
        if not roh:
            roh = [x.strip().lower() for x in str(config.MARKT_BEOBACHTUNG or "").split(",") if x.strip()]
        schluessel, unbekannt = [], []
        for eintrag in roh:
            if eintrag in SYMBOLE:
                if eintrag not in schluessel:
                    schluessel.append(eintrag)
            else:
                unbekannt.append(eintrag[:20])
        if not schluessel:
            schluessel = list(MARKT_STANDARD)
        return schluessel[:MARKT_HOECHSTENS], unbekannt

    def _abrufen(self, url: str, kopf: dict) -> tuple:
        """Wie ``holen``, aber nie mit einer Ausnahme. Gibt ``(status, daten, fehler)``."""
        try:
            status, daten, fehler = self._holen(url, kopf, MARKT_TIMEOUT)
        except Exception as ausnahme:
            return 0, b"", netz_fehlertext(ausnahme)
        if not fehler and status != 200:
            fehler = "Fehler %d" % status
        return status, daten, fehler

    def _zeigen(self, daten: dict, quelle: str):
        if self.anzeige is None:
            return None
        try:
            return self.anzeige.zeigen("maerkte", daten, dauer_s=None, quelle=quelle)
        except Exception as fehler:
            print("[maerkte] Anzeige: %s" % fehler)
            return None

    def _stand_text(self, kurse: list) -> str:
        """Der jüngste Zeitpunkt aller Kurse, sprechbar ("15:45", "gestern 22:10")."""
        zeiten = [k["zeit"] for k in kurse if k.get("zeit") and k.get("quelle") != QUELLE_EZB] \
            or [k["zeit"] for k in kurse if k.get("zeit")]
        return zeit_sprechbar(max(zeiten), self._uhr()) if zeiten else \
            datetime.fromtimestamp(self._uhr()).strftime("%H:%M")

    @staticmethod
    def _quellen_text(quellen: list) -> str:
        return ", ".join("%s (verzögert)" % q if q == QUELLE_YAHOO else q for q in quellen)

    @staticmethod
    def _satz(kurs: dict) -> str:
        satz = "%s %s%s" % (kurs["name"], zahl_de(kurs["wert"], markt_stellen(kurs["schluessel"], kurs["wert"])),
                            (" " + kurs["einheit"]) if kurs.get("einheit") else "")
        if kurs.get("aenderung_prozent") is not None:
            satz += ", " + aenderung_text(kurs["aenderung_prozent"])
            if kurs.get("quelle") == QUELLE_COINGECKO:
                satz += " in 24 Stunden"
        if kurs.get("quelle") == QUELLE_EZB and kurs.get("datum"):
            satz += " (EZB-Referenzkurs vom %s)" % datetime.strptime(kurs["datum"], "%Y-%m-%d").strftime("%d.%m.")
        return satz + "."

    # -- Kurse --------------------------------------------------------------

    def kurse(self, auswahl=None, zeitraum: str = "heute", zeigen: bool = True) -> dict:
        """Kurse der Auswahl (sonst der Beobachtungsliste), als Kurven auf der Zentrale."""
        ergebnis, daten = self.kurse_mit_anzeige(auswahl, zeitraum)
        if ergebnis.get("ok") and zeigen and daten:
            self._zeigen(daten, "maerkte")
        return ergebnis

    def kurse_mit_anzeige(self, auswahl=None, zeitraum: str = "heute") -> tuple:
        """Wie :meth:`kurse`, ohne zu zeigen. Gibt ``(ergebnis, anzeige_daten)`` zurück."""
        zeitraum = zeitraum if zeitraum in ("heute", "monat") else "heute"
        schluessel, unbekannt = self.auswahl_lesen(auswahl)
        merker = (tuple(sorted(schluessel)), zeitraum)
        jetzt = self._uhr()
        with self._sperre:
            eintrag = self._zwischenspeicher.get(merker)
            if eintrag and jetzt - eintrag[0] < MARKT_ZWISCHENSPEICHER_S:
                return copy.deepcopy(eintrag[1]), copy.deepcopy(eintrag[2])

        gefunden, fehler = {}, {}
        # 1. Yahoo: alles in einer Anfrage.
        symbole = [SYMBOLE[k][0] for k in schluessel]
        url = "%s?symbols=%s&%s" % (YAHOO_SPARK, ",".join(urllib.parse.quote(s, safe="") for s in symbole),
                                    "range=1d&interval=5m" if zeitraum == "heute" else "range=1mo&interval=1d")
        status, daten, yahoo_fehler = self._abrufen(url, dict(YAHOO_KOPF))
        if not yahoo_fehler:
            try:
                gelesen = spark_lesen(daten, zeitraum)
            except (ValueError, TypeError, AttributeError) as ausnahme:
                print("[maerkte] Yahoo nicht lesbar: %s" % ausnahme)
                gelesen, yahoo_fehler = {}, "Antwort nicht lesbar"
            for k in schluessel:
                if SYMBOLE[k][0] in gelesen:
                    gefunden[k] = dict(gelesen[SYMBOLE[k][0]], quelle=QUELLE_YAHOO)
            # Fehlt einzelnes, fragt er die Einzelabfrage - höchstens dreimal.
            nachholen = [k for k in schluessel if k not in gefunden
                         and k not in ("bitcoin", "ethereum", "eurusd")][:3]
            for k in nachholen:
                _s, roh, f = self._abrufen(YAHOO_CHART % urllib.parse.quote(SYMBOLE[k][0], safe=""),
                                           dict(YAHOO_KOPF))
                if f:
                    continue
                try:
                    einzeln = yahoo_chart_lesen(roh)
                except (ValueError, TypeError, AttributeError):
                    einzeln = None
                if einzeln:
                    gefunden[k] = {"wert": einzeln["wert"], "aenderung_prozent": einzeln["aenderung_prozent"],
                                   "verlauf": verlauf_kuerzen(einzeln["verlauf"]), "zeit": einzeln["zeit"],
                                   "quelle": QUELLE_YAHOO}
        if yahoo_fehler:
            fehler["Yahoo"] = yahoo_fehler

        # 2. CoinGecko für Bitcoin und Ethereum.
        krypto = [k for k in schluessel if k in ("bitcoin", "ethereum") and k not in gefunden]
        if krypto:
            kopf = {"User-Agent": MARKT_UA, "Accept": "application/json"}
            if config.COINGECKO_SCHLUESSEL:
                kopf["x-cg-demo-api-key"] = config.COINGECKO_SCHLUESSEL
            _s, daten, f = self._abrufen(COINGECKO_PREIS, kopf)
            if f:
                fehler["CoinGecko"] = f
            else:
                try:
                    gelesen = coingecko_lesen(daten)
                except (ValueError, TypeError, AttributeError):
                    gelesen, fehler["CoinGecko"] = {}, "Antwort nicht lesbar"
                for k in krypto:
                    if k in gelesen:
                        gefunden[k] = dict(gelesen[k], quelle=QUELLE_COINGECKO)

        # 3. EZB für Euro-Dollar.
        if "eurusd" in schluessel and "eurusd" not in gefunden:
            _s, daten, f = self._abrufen(EZB_KURS, {"User-Agent": MARKT_UA})
            gelesen = None
            if not f:
                try:
                    gelesen = ezb_lesen(daten)
                except (ValueError, TypeError):
                    gelesen = None
                if gelesen is None:
                    f = "Antwort nicht lesbar"
            if f:
                fehler["EZB"] = f
            else:
                gefunden["eurusd"] = dict(gelesen, quelle=QUELLE_EZB)

        if not gefunden:
            return {"ok": False, "fehler": "Kursdaten gerade nicht verfügbar (%s)."
                    % "; ".join("%s: %s" % (q, f) for q, f in fehler.items())}, None

        kurse = []
        for k in schluessel:
            if k not in gefunden:
                continue
            symbol, name, einheit = SYMBOLE[k]
            kurse.append(dict(gefunden[k], schluessel=k, symbol=symbol, name=name, einheit=einheit))
        fehlend = [SYMBOLE[k][1] for k in schluessel if k not in gefunden]
        quellen = []
        for kurs in kurse:
            if kurs["quelle"] not in quellen:
                quellen.append(kurs["quelle"])
        stand = self._stand_text(kurse)
        text = " ".join(self._satz(k) for k in kurse)
        text += " Stand %s, Quelle %s." % (stand, self._quellen_text(quellen))
        if fehlend:
            text += " Nicht abrufbar: %s." % ", ".join(fehlend)
        text += " Keine Anlageberatung."
        ergebnis = {"hinweis": HINWEIS_KURSE, "ok": True, "zeitraum": zeitraum, "stand": stand,
                    "kurse": [{"name": k["name"], "wert": k["wert"], "einheit": k["einheit"],
                               "aenderung_prozent": k["aenderung_prozent"],
                               "zeit": zeit_sprechbar(k["zeit"], self._uhr()), "quelle": k["quelle"]}
                              for k in kurse],
                    "fehlend": fehlend, "quellen": quellen, "text": text}
        if unbekannt:
            ergebnis["unbekannt"] = unbekannt
        anzeige = {"titel": "Märkte", "zeitraum": zeitraum, "fehlend": fehlend,
                   "kurse": [{"schluessel": k["schluessel"], "symbol": k["symbol"], "name": k["name"],
                              "wert": k["wert"], "einheit": k["einheit"],
                              "aenderung_prozent": k["aenderung_prozent"],
                              "verlauf": list(k.get("verlauf") or [])[:MARKT_VERLAUF_PUNKTE],
                              "zeit": k.get("zeit") or ""} for k in kurse],
                   "stand": "Quelle: %s · Stand %s" % (self._quellen_text(
                       ["EZB" if q == QUELLE_EZB else q for q in quellen]), stand)}
        with self._sperre:
            self._zwischenspeicher[merker] = (jetzt, copy.deepcopy(ergebnis), copy.deepcopy(anzeige))
        return ergebnis, anzeige

    # -- Einzelne Aktie -----------------------------------------------------

    def aktie(self, symbol: str, zeigen: bool = True) -> dict:
        """Kurs einer Aktie nach Börsenkürzel (SAP.DE, AAPL), verzögert."""
        kuerzel = str(symbol or "").strip().upper()
        if not AKTIEN_MUSTER.match(kuerzel):
            return {"ok": False, "fehler": "Das Kürzel '%s' verstehe ich nicht – zum Beispiel "
                                           "SAP.DE oder AAPL." % str(symbol or "")[:30]}
        jetzt = self._uhr()
        merker = ("aktie", kuerzel)
        with self._sperre:
            eintrag = self._zwischenspeicher.get(merker)
        if eintrag and jetzt - eintrag[0] < MARKT_ZWISCHENSPEICHER_S:
            ergebnis, anzeige = copy.deepcopy(eintrag[1]), copy.deepcopy(eintrag[2])
        else:
            status, daten, fehler = self._abrufen(YAHOO_CHART % urllib.parse.quote(kuerzel, safe=""),
                                                  dict(YAHOO_KOPF))
            if status == 404:
                return {"ok": False, "fehler": "Zum Kürzel %s finde ich bei Yahoo Finance keinen Kurs. "
                                               "Deutsche Werte enden auf .DE, Wiener auf .VI." % kuerzel}
            if fehler:
                return {"ok": False, "fehler": "Der Kurs ist gerade nicht abrufbar (Yahoo: %s)." % fehler}
            try:
                gelesen = yahoo_chart_lesen(daten)
            except (ValueError, TypeError, AttributeError):
                gelesen = None
            if not gelesen:
                return {"ok": False, "fehler": "Zum Kürzel %s liefert Yahoo Finance gerade keinen Kurs."
                                               % kuerzel}
            name = gelesen["name"] or kuerzel
            einheit = WAEHRUNGEN.get(gelesen["waehrung"], gelesen["waehrung"])
            kurs = {"schluessel": kuerzel.lower(), "symbol": kuerzel, "name": name,
                    "wert": gelesen["wert"], "einheit": einheit,
                    "aenderung_prozent": gelesen["aenderung_prozent"],
                    "verlauf": verlauf_kuerzen(gelesen["verlauf"]), "zeit": gelesen["zeit"],
                    "quelle": QUELLE_YAHOO}
            stand = self._stand_text([kurs])
            text = "%s Stand %s, Quelle Yahoo Finance (verzögert). Keine Anlageberatung." % (
                self._satz(kurs), stand)
            ergebnis = {"hinweis": HINWEIS_KURSE, "ok": True, "symbol": kuerzel, "name": name,
                        "wert": kurs["wert"], "waehrung": gelesen["waehrung"],
                        "aenderung_prozent": kurs["aenderung_prozent"], "stand": stand,
                        "quelle": QUELLE_YAHOO, "text": text}
            anzeige = {"titel": text_titel(name), "zeitraum": "monat", "fehlend": [],
                       "kurse": [{k: kurs[k] for k in ("schluessel", "symbol", "name", "wert", "einheit",
                                                       "aenderung_prozent", "verlauf", "zeit")}],
                       "stand": "Quelle: Yahoo Finance (verzögert) · Stand %s" % stand}
            with self._sperre:
                self._zwischenspeicher[merker] = (jetzt, copy.deepcopy(ergebnis), copy.deepcopy(anzeige))
        if zeigen:
            self._zeigen(anzeige, "aktienkurs")
        return ergebnis


def text_titel(name: str) -> str:
    """Ein Anzeigetitel, höchstens 80 Zeichen."""
    name = " ".join(str(name or "").split())
    return name if len(name) <= 80 else name[:79] + "…"
