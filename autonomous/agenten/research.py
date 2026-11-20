# -*- coding: utf-8 -*-
"""Research-Agent: bewertet Geschäftsfelder anhand nachvollziehbarer Kriterien und Quellen.

Version 1 arbeitet mit der lokal abgelegten, recherchierten Marktbewertung
(daten_vorlagen/marktbewertung.json, Quellen mit Abrufdatum). Diese Datei gilt als NICHT
vertrauenswürdige Eingabe: sie wird nur als Daten gelesen und gegen ein Schema geprüft.
Eigenes Abrufen von Webseiten ist freigabepflichtig und in Version 1 nicht eingebaut."""

import datetime
import json
import os
from urllib.parse import urlparse

from . import Agent
from .. import konfig

STANDARD_GEWICHTE = {"nachfrage": 2, "kundenproblem": 2, "erreichbarkeit": 3, "wettbewerb": 1,
                     "differenzierung": 1, "entwicklungsaufwand": 2, "direkte_kosten": 1, "verkaufspreis": 2,
                     "lieferzeit": 1, "rechtliche_risiken": 2}


def _zahl(w):
    if isinstance(w, bool) or not isinstance(w, (int, float)):
        return None
    return w if 0 <= w <= 5 else None


def quelle_bewerten(q, heute=None):
    heute = heute or datetime.date.today()
    url = str(q.get("url", ""))
    teile = urlparse(url)
    bewertung = {"url": url[:300], "titel": str(q.get("titel", ""))[:200], "punkte": 0, "hinweise": []}
    if teile.scheme == "https":
        bewertung["punkte"] += 1
    else:
        bewertung["hinweise"].append("keine https-Adresse")
    host = (teile.hostname or "").lower()
    if host.endswith((".bund.de", ".nrw.de", "gesetze-im-internet.de", "ihk.de", ".gov", "destatis.de",
                      "europa.eu", "bundesregierung.de", "bmwk.de", "bmj.de")) or ".ihk." in host:
        bewertung["punkte"] += 2
        bewertung["hinweise"].append("amtliche/öffentliche Stelle")
    elif host:
        bewertung["punkte"] += 1
    try:
        abgerufen = datetime.date.fromisoformat(str(q.get("abgerufen", ""))[:10])
        alter = (heute - abgerufen).days
        bewertung["alter_tage"] = alter
        if alter <= 180:
            bewertung["punkte"] += 1
        else:
            bewertung["hinweise"].append("Abruf älter als 180 Tage – neu prüfen")
    except ValueError:
        bewertung["hinweise"].append("kein gültiges Abrufdatum")
    bewertung["stufe"] = ("gut" if bewertung["punkte"] >= 3 else "mittel" if bewertung["punkte"] == 2
                          else "schwach")
    return bewertung


class ResearchAgent(Agent):
    rolle = "research"
    name = "Research-Agent"
    beschreibung = "Untersucht Märkte, Wettbewerber und Zielgruppen; trennt Belege von Annahmen."
    rechte = frozenset({"lokale_recherche", "interne_auswertung", "gedaechtnis_vorschlag", "lokales_modell"})
    aufgabentypen = {
        "marktbewertung": "Geschäftsfelder nach Kriterien gewichten und ranken (Eingabe optional: gewichte)",
        "quellen_pruefen": "Aktualität und Qualität von Quellen bewerten (Eingabe: quellen[])",
    }

    def _laden(self):
        pfad = os.path.join(konfig.VORLAGEN, "marktbewertung.json")
        if not os.path.exists(pfad):
            raise ValueError("Keine Marktbewertung vorhanden (daten_vorlagen/marktbewertung.json fehlt).")
        with open(pfad, encoding="utf-8") as f:
            daten = json.load(f)
        if not isinstance(daten, dict) or not isinstance(daten.get("felder"), list):
            raise ValueError("Marktbewertung hat ein ungültiges Format.")
        return daten, pfad

    def aufgabe_marktbewertung(self, aufgabe, k):
        self.darf(k, "lokale_recherche", "marktbewertung", aufgabe)
        daten, pfad = self._laden()
        gewichte = dict(STANDARD_GEWICHTE)
        for name, w in (aufgabe["eingabe"].get("gewichte") or {}).items():
            if name in gewichte and _zahl(w) is not None:
                gewichte[name] = w
        rangliste = []
        for feld in daten["felder"][:50]:
            if not isinstance(feld, dict):
                continue
            punkte = feld.get("punkte") or {}
            summe = gewicht = 0
            fehlend = []
            for krit, g in gewichte.items():
                p = _zahl(punkte.get(krit))
                if p is None:
                    fehlend.append(krit)
                    continue
                summe += p * g
                gewicht += g
            quellen = [quelle_bewerten(q) for q in (feld.get("quellen") or [])[:20] if isinstance(q, dict)]
            rangliste.append({
                "id": str(feld.get("id", ""))[:60], "name": str(feld.get("name", ""))[:200],
                "wert": round(summe / gewicht, 2) if gewicht else None,
                "fehlende_kriterien": fehlend,
                "belegstatus": str(feld.get("belegstatus", "unbekannt"))[:30],
                "quellen": quellen,
                "quellen_gut": sum(1 for q in quellen if q["stufe"] == "gut"),
            })
        rangliste.sort(key=lambda r: (r["wert"] is None, -(r["wert"] or 0)))
        empfehlung = daten.get("empfehlung") or {}
        ergebnis = {
            "stand": daten.get("stand"), "gewichte": gewichte, "rangliste": rangliste,
            "empfehlung_aus_recherche": {k2: empfehlung.get(k2) for k2 in ("feld_id", "angebot",
                                                                         "preis_vorschlag_eur", "begruendung")},
            "spitze_nach_gewichtung": rangliste[0]["id"] if rangliste else None,
            "quelle": "datei:" + os.path.relpath(pfad, konfig.PROJEKT),
            "einordnung": "Punktwerte sind begründete Einschätzungen der Recherche, keine Messwerte. "
                          "Preise sind VORSCHLÄGE – Entscheidung beim Inhaber.",
        }
        if rangliste:
            self.darf(k, "gedaechtnis_vorschlag", "marktbewertung", aufgabe)
            k.gedaechtnis.merken("vorschlag", "Erstes Angebot", "Nach Gewichtung vorne: %s (Wert %s). Empfehlung "
                                 "der Recherche: %s" % (rangliste[0]["name"], rangliste[0]["wert"],
                                                        empfehlung.get("angebot")),
                                 ergebnis["quelle"], self.rolle, aufgabe["id"])
        return ergebnis

    def aufgabe_quellen_pruefen(self, aufgabe, k):
        self.darf(k, "lokale_recherche", "quellen_pruefen", aufgabe)
        quellen = aufgabe["eingabe"].get("quellen") or []
        if not isinstance(quellen, list) or not quellen:
            raise ValueError("Eingabe 'quellen' (Liste) fehlt.")
        return {"bewertungen": [quelle_bewerten(q) for q in quellen[:50] if isinstance(q, dict)]}
