#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Kundengespräche bewerten - ehrlich, nicht schmeichelnd.

Ein freundliches Gespräch ohne Ergebnis ist kein gutes Gespräch. Die Bewertung
sagt das auch. Schwächen werden konkret benannt, nicht allgemein.
"""

import json
from datetime import datetime, timedelta

from modules.memory import Memory, db_schema_anlegen, heute_datum, zeitstempel

SCHEMA_GESPRAECHE = """
CREATE TABLE IF NOT EXISTS gespraeche (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    kunde TEXT DEFAULT '',
    datum TEXT NOT NULL,
    punktzahl INTEGER DEFAULT 0,
    ergebnis TEXT DEFAULT 'unklar',
    volumen REAL DEFAULT 0,
    staerken TEXT DEFAULT '',
    schwaechen TEXT DEFAULT '',
    einwaende TEXT DEFAULT '',
    offene_einwaende TEXT DEFAULT '',
    naechster_schritt TEXT DEFAULT '',
    bewertung TEXT DEFAULT '',
    rohtext TEXT DEFAULT '',
    angelegt TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_gespraeche_datum ON gespraeche(datum);
"""

ERGEBNIS_WERTE = ("gewonnen", "offen", "verloren", "unklar")

GESPRAECH_PROMPT = """Du bewertest ein Kundengespräch eines Gebäudereinigers.
Sei streng. Ein nettes Gespräch ohne Abschluss oder konkreten nächsten Termin
ist kein gutes Gespräch - das sagst du dann auch deutlich.

Worauf es in dieser Branche ankommt:
- Quadratmeter, Anzahl der Räume, Bodenbeläge erfasst?
- Reinigungsintervall geklärt (täglich, zweimal die Woche, monatlich)?
- Zugang, Schlüsselübergabe, Zeitfenster besprochen?
- Sonderleistungen angesprochen (Fensterreinigung, Grundreinigung, Teppich)?
- Preisbildung nachvollziehbar begründet, pro Quadratmeter oder pro Stunde?
- Probereinigung angeboten?
- Konkreter nächster Termin mit Datum vereinbart?

Gib ausschließlich JSON zurück, ohne Fließtext, mit genau diesen Schlüsseln:
  kunde              Name des Kunden oder Objekts, Text
  punktzahl          0 bis 100, ganze Zahl
  ergebnis           gewonnen, offen, verloren oder unklar
  volumen            geschätztes Auftragsvolumen pro Jahr in Euro als Zahl, sonst 0
  staerken           Liste konkreter Sätze, was gut lief
  schwaechen         Liste konkreter Sätze. Nicht "hätte mehr fragen sollen",
                     sondern "Bodenbelag und Quadratmeter nie erfasst - ohne die
                     ist kein Preis kalkulierbar"
  einwaende          Liste der Einwände, die der Kunde gebracht hat
  offene_einwaende   Liste der Einwände, die unbeantwortet geblieben sind
  naechster_schritt  ein konkreter Satz, was jetzt zu tun ist
  bewertung          Objekt mit den Schlüsseln bedarf_erfasst, objekt_verstanden,
                     preis_begruendet, einwaende_behandelt, abschluss_gesucht -
                     jeweils eine Zahl von 0 bis 10

Das Gespräch, wie er es erzählt hat:
"""


def _liste_zu_text(wert) -> str:
    """Macht aus einer Liste oder einem Text eine Zeile mit Strichpunkten."""
    if wert is None:
        return ""
    if isinstance(wert, (list, tuple)):
        return "; ".join(str(teil).strip() for teil in wert if str(teil).strip())
    return str(wert).strip()


def _text_zu_liste(wert: str) -> list:
    """Umkehrung von :func:`_liste_zu_text`."""
    if not wert:
        return []
    return [teil.strip() for teil in str(wert).split(";") if teil.strip()]


class CallAnalysis:
    """Bewertet Kundengespräche und erkennt Muster über viele Gespräche hinweg."""

    def __init__(self, memory: Memory = None):
        self.memory = memory or Memory()
        db_schema_anlegen(SCHEMA_GESPRAECHE, self.memory.db_pfad)

    # -- Erfassen -----------------------------------------------------------

    def gespraech_festhalten(self, bericht: str, agent=None, kunde: str = "",
                             datum: str = "") -> dict:
        """Lässt Claude das Gespräch bewerten und legt es ab."""
        bericht = (bericht or "").strip()
        if not bericht:
            return {"ok": False, "fehler": "Du hast mir noch nicht erzählt, wie es lief."}
        datum = datum or heute_datum()

        if agent is None or not getattr(agent, "einsatzbereit", lambda: False)():
            # Ohne Claude wird nichts erfunden - der Bericht wird roh abgelegt.
            nummer = self._ablegen({"kunde": kunde, "datum": datum, "punktzahl": 0,
                                    "ergebnis": "unklar", "volumen": 0}, bericht, {})
            return {"ok": True, "id": nummer, "bewertet": False,
                    "text": "Ich habe das Gespräch festgehalten, konnte es ohne "
                            "Anthropic-Schlüssel aber nicht bewerten."}

        antwort = agent.json_anfrage(GESPRAECH_PROMPT + bericht)
        if not antwort.get("ok"):
            nummer = self._ablegen({"kunde": kunde, "datum": datum}, bericht, {})
            return {"ok": True, "id": nummer, "bewertet": False,
                    "text": "Festgehalten. Die Bewertung ist fehlgeschlagen: %s"
                            % antwort.get("fehler", "unbekannter Fehler")}

        daten = antwort["daten"]
        if kunde:
            daten["kunde"] = kunde
        daten["datum"] = datum
        nummer = self._ablegen(daten, bericht, daten.get("bewertung") or {})

        punkte = int(daten.get("punktzahl") or 0)
        ergebnis = str(daten.get("ergebnis") or "unklar").lower()
        if ergebnis not in ERGEBNIS_WERTE:
            ergebnis = "unklar"
        schwaechen = daten.get("schwaechen") or []
        erste_schwaeche = _liste_zu_text(schwaechen[:1]) if isinstance(schwaechen, list) \
            else _liste_zu_text(schwaechen)

        text = ("%s: %d von 100, Ergebnis %s." %
                (daten.get("kunde") or "Das Gespräch", punkte, ergebnis))
        if erste_schwaeche:
            text += " Größte Lücke: %s" % erste_schwaeche
        if daten.get("naechster_schritt"):
            text += " Nächster Schritt: %s" % daten["naechster_schritt"]

        return {"ok": True, "id": nummer, "bewertet": True, "punktzahl": punkte,
                "ergebnis": ergebnis, "daten": daten, "text": text}

    def _ablegen(self, daten: dict, rohtext: str, bewertung: dict) -> int:
        """Schreibt eine Gesprächsbewertung in die Datenbank."""
        try:
            volumen = float(daten.get("volumen") or 0)
        except (TypeError, ValueError):
            volumen = 0.0
        try:
            punktzahl = int(daten.get("punktzahl") or 0)
        except (TypeError, ValueError):
            punktzahl = 0
        ergebnis = str(daten.get("ergebnis") or "unklar").lower()
        if ergebnis not in ERGEBNIS_WERTE:
            ergebnis = "unklar"
        try:
            bewertung_text = json.dumps(bewertung or {}, ensure_ascii=False)
        except (TypeError, ValueError):
            bewertung_text = "{}"
        return self.memory._schreiben(
            "INSERT INTO gespraeche (kunde, datum, punktzahl, ergebnis, volumen, staerken, "
            "schwaechen, einwaende, offene_einwaende, naechster_schritt, bewertung, rohtext, "
            "angelegt) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (str(daten.get("kunde") or ""), str(daten.get("datum") or heute_datum()),
             punktzahl, ergebnis, volumen,
             _liste_zu_text(daten.get("staerken")),
             _liste_zu_text(daten.get("schwaechen")),
             _liste_zu_text(daten.get("einwaende")),
             _liste_zu_text(daten.get("offene_einwaende")),
             str(daten.get("naechster_schritt") or ""),
             bewertung_text, rohtext[:6000], zeitstempel()))

    # -- Auswerten ----------------------------------------------------------

    def gespraeche(self, limit: int = 50) -> list:
        """Die zuletzt festgehaltenen Gespräche."""
        return self.memory._lesen(
            "SELECT * FROM gespraeche ORDER BY datum DESC, id DESC LIMIT ?", (limit,))

    def offene_leads(self) -> dict:
        """Alle Gespräche mit Ergebnis 'offen', samt Summe des offenen Volumens."""
        zeilen = self.memory._lesen(
            "SELECT * FROM gespraeche WHERE ergebnis='offen' ORDER BY volumen DESC, datum DESC")
        summe = round(sum(z["volumen"] or 0 for z in zeilen), 2)
        leads = [{"id": z["id"], "kunde": z["kunde"], "datum": z["datum"],
                  "volumen": z["volumen"], "punktzahl": z["punktzahl"],
                  "naechster_schritt": z["naechster_schritt"]} for z in zeilen]
        if not leads:
            text = "Es ist gerade kein Lead offen."
        else:
            groesster = leads[0]
            text = ("%d offene Leads über zusammen %.0f Euro. Der größte ist %s mit "
                    "%.0f Euro. Nächster Schritt dort: %s"
                    % (len(leads), summe, groesster["kunde"] or "ein Kunde ohne Namen",
                       groesster["volumen"],
                       groesster["naechster_schritt"] or "steht noch nicht fest"))
        return {"ok": True, "anzahl": len(leads), "volumen_offen": summe,
                "leads": leads, "text": text}

    def verkaufsmuster(self, tage: int = 90) -> dict:
        """Abschlussquote, Durchschnittspunktzahl und wiederkehrende Einwände.

        Kommt derselbe Einwand dreimal, ist das kein Zufall, sondern eine Lücke
        im Angebot.
        """
        grenze = (datetime.now() - timedelta(days=tage)).strftime("%Y-%m-%d")
        zeilen = self.memory._lesen(
            "SELECT * FROM gespraeche WHERE datum>=? ORDER BY datum", (grenze,))
        if not zeilen:
            return {"ok": True, "anzahl": 0,
                    "text": "In den letzten %d Tagen ist kein Gespräch festgehalten worden."
                            % tage}

        gewonnen = len([z for z in zeilen if z["ergebnis"] == "gewonnen"])
        verloren = len([z for z in zeilen if z["ergebnis"] == "verloren"])
        offen = len([z for z in zeilen if z["ergebnis"] == "offen"])
        entschieden = gewonnen + verloren
        quote = round(100.0 * gewonnen / entschieden, 1) if entschieden else 0.0
        schnitt = round(sum(z["punktzahl"] for z in zeilen) / float(len(zeilen)), 1)

        haeufigkeit = {}
        for zeile in zeilen:
            for einwand in _text_zu_liste(zeile["einwaende"]) + \
                           _text_zu_liste(zeile["offene_einwaende"]):
                schluessel = einwand.lower()[:80]
                haeufigkeit[schluessel] = haeufigkeit.get(schluessel, 0) + 1
        wiederkehrend = sorted([(anzahl, text) for text, anzahl in haeufigkeit.items()
                                if anzahl >= 2], reverse=True)[:6]

        schwaechen = {}
        for zeile in zeilen:
            for schwaeche in _text_zu_liste(zeile["schwaechen"]):
                schluessel = schwaeche.lower()[:80]
                schwaechen[schluessel] = schwaechen.get(schluessel, 0) + 1
        haeufige_schwaechen = sorted([(a, t) for t, a in schwaechen.items() if a >= 2],
                                     reverse=True)[:5]

        text = ("%d Gespräche in %d Tagen. Abschlussquote %.1f Prozent, "
                "Durchschnitt %.1f Punkte. %d gewonnen, %d verloren, %d offen."
                % (len(zeilen), tage, quote, schnitt, gewonnen, verloren, offen))
        if wiederkehrend:
            anzahl, einwand = wiederkehrend[0]
            text += (" Der Einwand '%s' kam %d mal - das ist kein Zufall, "
                     "sondern eine Lücke im Angebot." % (einwand, anzahl))

        return {"ok": True, "anzahl": len(zeilen), "gewonnen": gewonnen,
                "verloren": verloren, "offen": offen, "abschlussquote": quote,
                "durchschnitt": schnitt,
                "wiederkehrende_einwaende": [{"einwand": t, "anzahl": a}
                                             for a, t in wiederkehrend],
                "haeufige_schwaechen": [{"schwaeche": t, "anzahl": a}
                                        for a, t in haeufige_schwaechen],
                "text": text}
