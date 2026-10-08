#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Anzeige-Speicher - was die großen Bildschirme gerade zeigen sollen.

Ein einziger Speicher je Prozess (``Werkzeuge.anzeige``). Werkzeuge, Stimme
und Telefon schreiben hinein, die Seiten (Zentrale, Gehirn, Hauptseite) holen
es per Long-Poll ab: ``GET /api/anzeige?nach=buehne:7,stimme:31&warten=20``
kommt zurück, sobald sich einer der genannten Kanäle geändert hat.

**Kanäle.** Jeder Kanal hat eine Versionsnummer, die nur wächst. Der Kanal
``buehne`` sagt, welche Ansicht die Zentrale gerade zeigt (``modus``), die
anderen tragen laufende Inhalte: ``stimme`` den Pegel der Sprachausgabe,
``anruf`` das Telefonat, ``sicht`` Handruhe und Erholung, ``untertitel`` den
Dolmetscher, ``hochfahren`` den Start.

**Nie im Weg.** Wer schreibt, fängt jede Ausnahme ab - eine kaputte Anzeige
darf kein Werkzeug kaputt machen. Ungültiges wird mit ``-1`` abgewiesen und
nur auf der Konsole gemeldet.

**Diskret.** Mit ``ANZEIGE_DISKRET`` verschwinden Nummern, Namen und Texte,
bevor etwas den Speicher verlässt - damit im Raum niemand mitliest.

**Die Uhr.** Die eingespeiste Uhr (für Prüfungen) gilt nur für ``seit``,
``bis`` und ``start``. Wie lange ``warten`` wartet, misst immer die
Monotonuhr - sonst stünde eine angehaltene Prüf-Uhr für immer still.
"""

import copy
import json
import threading
import time

import config

# Die Kanäle der Anzeige. Der Name ist bewusst nicht "KANAELE" - so heißt
# schon die Liste der Versandwege im Messenger.
ANZEIGE_KANAELE = ("buehne", "stimme", "anruf", "sicht", "untertitel", "hochfahren")

# Die Ansichten der Bühne (Kanal "buehne", Feld "modus").
ANZEIGE_MODI = ("uebersicht", "globus", "folge", "maerkte", "kennzahlen", "anruf", "sicht",
                "untertitel", "hochfahren", "recherche", "inhalte")

# Mehr als 64 KB JSON je Eintrag braucht keine Ansicht - und jeder Long-Poll
# trägt es zu jeder Seite.
MAX_NUTZLAST = 65536


def anzeige_nach_lesen(text: str) -> dict:
    """Liest ``"buehne:7,anruf:2"`` als ``{"buehne": 7, "anruf": 2}``.

    Unbekannte Kanäle fallen weg, unlesbare Zahlen werden ``-1`` - dann gilt
    der Kanal als geändert und kommt sofort zurück.
    """
    ergebnis = {}
    for teil in str(text or "").split(","):
        name, _, wert = teil.partition(":")
        name = name.strip()
        if name not in ANZEIGE_KANAELE:
            continue
        try:
            ergebnis[name] = int(wert.strip())
        except ValueError:
            ergebnis[name] = -1
    return ergebnis


def _sicht_leeren(wert, schluessel: str = ""):
    """Gesundheitswerte im Diskretmodus: Zahlen und Texte weg, nur die Quelle bleibt."""
    if schluessel == "quelle":
        return wert
    if isinstance(wert, dict):
        return {k: _sicht_leeren(v, k) for k, v in wert.items()}
    if isinstance(wert, list):
        return [_sicht_leeren(v) for v in wert]
    if isinstance(wert, bool) or wert is None:
        return wert
    if isinstance(wert, (int, float)):
        return None
    if isinstance(wert, str):
        return ""
    return wert


def diskret_filtern(kanal: str, daten: dict) -> dict:
    """Entfernt, was im Raum niemand mitlesen soll. Gibt eine Kopie zurück.

    anruf: Nummer und Ziel weg, Mitschrift leer. untertitel: beide Texte leer.
    sicht: alle Zahlen und Texte leer, nur die Quelle bleibt. hochfahren: keine
    Begrüßung, Schritte nur mit ihrem Namen. Auf der Bühne verlieren Beiträge
    (inhalte) ihren Titel. Kennzahlen, Globus und Recherche bleiben - das sind
    Zahlen oder öffentliche Quellen. Die Stimme wird nie gefiltert, ihr Text
    wird nirgends angezeigt.
    """
    daten = copy.deepcopy(daten) if isinstance(daten, dict) else {}
    if kanal == "anruf":
        if "nummer" in daten:
            daten["nummer"] = ""
        if "ziel" in daten:
            daten["ziel"] = "Anruf"
        for zeile in daten.get("mitschrift") or []:
            if isinstance(zeile, dict):
                zeile["text"] = ""
        # Das Ergebnis nennt Namen und Wünsche - im Raum bleibt nur, ob es geklappt hat.
        ergebnis = daten.get("ergebnis")
        if isinstance(ergebnis, dict):
            daten["ergebnis"] = {k: v for k, v in ergebnis.items()
                                 if k in ("reserviert", "datum", "uhrzeit", "personen")}
        for feld in ("hinweise", "gegenvorschlag", "grund_ende", "auftrag"):
            if feld in daten:
                daten[feld] = ""
    elif kanal == "untertitel":
        for feld in ("original", "uebersetzung"):
            if feld in daten:
                daten[feld] = ""
    elif kanal == "sicht":
        daten = _sicht_leeren(daten)
    elif kanal == "hochfahren":
        if "begruessung" in daten:
            daten["begruessung"] = ""
        for schritt in daten.get("schritte") or []:
            if isinstance(schritt, dict):
                schritt["text"] = str(schritt.get("name") or "")
    elif kanal == "buehne":
        daten = _buehne_diskret(daten)
    return daten


# Auf diesen Ansichten können Titel und Standzeile Namen tragen (Anruf bei ...,
# Erholung von ...). Globus, Märkte, Kennzahlen und Recherche sind öffentlich oder Zahlen.
BUEHNE_PRIVAT = ("anruf", "sicht", "untertitel", "inhalte", "hochfahren")


def _buehne_diskret(daten: dict) -> dict:
    """Bühne im Diskretmodus: Beiträge ohne Titel, private Ansichten ohne Titelzeile."""
    if daten.get("modus") in BUEHNE_PRIVAT:
        for feld in ("titel", "stand"):
            if feld in daten:
                daten[feld] = ""
    if daten.get("modus") == "inhalte":
        for eintrag in daten.get("eintraege") or []:
            if isinstance(eintrag, dict) and "titel" in eintrag:
                eintrag["titel"] = "Beitrag"
    elif daten.get("modus") == "folge":
        for schritt in daten.get("schritte") or []:
            if isinstance(schritt, dict) and isinstance(schritt.get("ansicht"), dict):
                schritt["ansicht"] = _buehne_diskret(schritt["ansicht"])
    return daten


class Anzeige:
    """Der Speicher hinter den Bildschirmen - threadsicher, mit Warten auf Änderungen."""

    def __init__(self, uhr=None):
        self._uhr = uhr or time.time
        self._bed = threading.Condition()
        self._k = {k: {"version": 0, "daten": {}, "seit": 0.0, "bis": 0.0}
                   for k in ANZEIGE_KANAELE}
        self._letzte = {}
        # Ändert sich beim Neustart - die Seiten setzen dann alle Versionen zurück.
        self.start = self._uhr()

    # -- Schreiben ----------------------------------------------------------

    @staticmethod
    def _pruefen(kanal: str, daten) -> tuple:
        """Gibt ``(roh, fehler)`` zurück: das JSON oder warum es abgewiesen wird."""
        if kanal not in ANZEIGE_KANAELE:
            return None, "Den Anzeige-Kanal '%s' gibt es nicht." % kanal
        if not isinstance(daten, dict):
            return None, "Die Anzeige-Daten müssen ein Wörterbuch sein."
        try:
            # NaN und Unendlich sind kein JSON - der Browser könnte die Antwort nicht lesen.
            # Ohne default=str: Datum, Menge oder Bytes sind kein Anzeige-Inhalt.
            roh = json.dumps(daten, ensure_ascii=False, allow_nan=False)
        except (TypeError, ValueError, RecursionError) as fehler:
            return None, "Die Anzeige-Daten sind kein gültiges JSON (%s)." % fehler
        if len(roh.encode("utf-8")) > MAX_NUTZLAST:
            return None, "Die Anzeige-Daten sind zu groß."
        return roh, ""

    @staticmethod
    def _dauer(dauer_s) -> float:
        try:
            dauer = float(dauer_s or 0)
        except (TypeError, ValueError):
            return 0.0
        return dauer if dauer > 0 and dauer != float("inf") else 0.0

    def _ablegen(self, kanal: str, roh: str, dauer: float, modus: str = "") -> int:
        """Legt geprüfte Daten ab und weckt alle Wartenden. Gibt die neue Version zurück."""
        with self._bed:
            eintrag = self._k[kanal]
            jetzt = self._uhr()
            eintrag["version"] += 1
            eintrag["daten"] = json.loads(roh)
            eintrag["seit"] = jetzt
            eintrag["bis"] = jetzt + dauer if dauer > 0 else 0.0
            if modus:
                self._letzte[modus] = json.loads(roh)
            self._bed.notify_all()
            return eintrag["version"]

    def melden(self, kanal: str, daten: dict, dauer_s: float = 0.0) -> int:
        """Schreibt einen Kanal. Gibt die neue Version zurück oder ``-1``.

        ``dauer_s`` 0 heißt: gilt, bis etwas Neues kommt.
        """
        roh, fehler = self._pruefen(kanal, daten)
        if roh is None:
            print("[anzeige] %s" % fehler)
            return -1
        return self._ablegen(kanal, roh, self._dauer(dauer_s))

    def zeigen(self, modus: str, daten: dict = None, dauer_s: float = None,
               quelle: str = "") -> dict:
        """Schaltet die Bühne auf eine Ansicht.

        ``dauer_s`` ``None`` nimmt ``ANZEIGE_DAUER``, ``0`` hält die Ansicht,
        bis etwas Neues kommt. Danach kehrt die Zentrale zur Übersicht zurück.
        """
        modus = str(modus or "").strip()
        if modus not in ANZEIGE_MODI:
            return {"ok": False,
                    "fehler": "Diese Ansicht gibt es nicht: %s. Möglich sind: %s."
                              % (modus or "(leer)", ", ".join(ANZEIGE_MODI))}
        if daten is None:
            daten = {}
        if not isinstance(daten, dict):
            return {"ok": False, "fehler": "Die Anzeige-Daten müssen ein Wörterbuch sein."}
        nutzlast = dict(daten, modus=modus, quelle=str(quelle or ""))
        roh, fehler = self._pruefen("buehne", nutzlast)
        if roh is None:
            print("[anzeige] %s" % fehler)
            return {"ok": False, "fehler": fehler}
        dauer = config.ANZEIGE_DAUER if dauer_s is None else dauer_s
        version = self._ablegen("buehne", roh, self._dauer(dauer), modus)
        return {"ok": True, "modus": modus, "version": version}

    # -- Lesen --------------------------------------------------------------

    def letzte(self, modus: str):
        """Was zuletzt in dieser Ansicht gezeigt wurde - ``None``, wenn noch nichts.

        Nur für den Programmcode (zum erneuten Zeigen über :meth:`zeigen`): ungefiltert,
        nie direkt an eine Seite geben.
        """
        with self._bed:
            gespeichert = self._letzte.get(modus)
            return copy.deepcopy(gespeichert) if gespeichert is not None else None

    def _stand(self, kanal: str) -> dict:
        """Stand eines Kanals, schon gefiltert. Nur unter der Sperre aufrufen."""
        eintrag = self._k[kanal]
        daten = copy.deepcopy(eintrag["daten"])
        if config.ANZEIGE_DISKRET and kanal != "stimme":
            daten = diskret_filtern(kanal, daten)
        return {"version": eintrag["version"], "daten": daten,
                "seit": eintrag["seit"], "bis": eintrag["bis"]}

    def stand(self, kanal: str):
        """``{"version", "daten", "seit", "bis"}`` eines Kanals - ``None``, wenn es ihn
        nicht gibt."""
        if kanal not in self._k:
            return None
        with self._bed:
            return self._stand(kanal)

    def warten(self, nach: dict, timeout: float) -> dict:
        """Wartet, bis einer der Kanäle eine andere Version hat als in ``nach``.

        Gibt ``{kanal: stand}`` der geänderten Kanäle zurück, nach Ablauf
        ``{}``. Verglichen wird mit ``!=``, nicht ``>``: So fällt auch ein
        neu gestarteter Server auf, dessen Zähler wieder klein sind.
        """
        try:
            frist = min(3600.0, max(0.0, float(timeout or 0)))
        except (TypeError, ValueError):
            frist = 0.0
        if frist != frist:  # NaN
            frist = 0.0
        ende = time.monotonic() + frist
        gefragt = {k: v for k, v in (nach or {}).items() if k in self._k}
        with self._bed:
            while True:
                geaendert = {k: self._stand(k) for k, v in gefragt.items()
                             if self._k[k]["version"] != v}
                rest = ende - time.monotonic()
                if geaendert or rest <= 0:
                    return geaendert
                self._bed.wait(rest)

    def kurz(self) -> dict:
        """Kurzstand für ``/api/status``: Ansicht, Versionen, Ablauf, Start."""
        with self._bed:
            buehne = self._k["buehne"]
            modus = buehne["daten"].get("modus") or "uebersicht"
            if buehne["bis"] and self._uhr() >= buehne["bis"]:
                modus = "uebersicht"
            return {"modus": modus,
                    "versionen": {k: e["version"] for k, e in self._k.items()},
                    "bis": buehne["bis"], "start": self.start}
