# -*- coding: utf-8 -*-
"""Schnittstelle für Marktbericht (Research-Agent) und lokales Modell. Wird von server.py automatisch geladen.

POST /api/research/marktbericht {zeitraum_tage?}  → {aufgabe_id}
GET  /api/research/marktberichte                  → {berichte:[...], in_arbeit:[...]}
GET  /api/modell/status                           → {anbieter, modell, erreichbar, modell_vorhanden, ...}
POST /api/modell/testen                           → kurzer Probeaufruf (nur wenn ein Modell eingestellt ist)
POST /api/modell/pruefstand {modelle?}            → {aufgabe_id} – Prüfstand als Aufgabe des Research-Agenten
GET  /api/modell/pruefstand                       → {laeufe:[...], in_arbeit:[...], letzter_fehler: {…}|null}
"""

import json
import time

from .agenten.research import zeitraum_pruefen
from .api import EIGENTUEMER, ApiFehler, route
from .ki import modelfile, pruefstand, vorlagen
from .modell import ModellNichtVerfuegbar

RECHERCHE_AUS = ("Internet-Recherche ist ausgeschaltet – in den Einstellungen unter „Auftragssuche“ einmal "
                 "einschalten. Dann liest der Research-Agent nur die freigegebenen öffentlichen Quellen.")


@route("POST", "/api/research/marktbericht")
def r_marktbericht(kern, a):
    if not kern.einstellungen.hole("internet_recherche_erlaubt"):
        raise ApiFehler(400, RECHERCHE_AUS)
    try:
        tage = zeitraum_pruefen(a["body"].get("zeitraum_tage"))
    except ValueError as f:
        raise ApiFehler(400, str(f))
    aid = kern.aufgaben.anlegen("Marktbericht (%d Tage)" % tage, "marktbericht", "research", EIGENTUEMER,
                                {"zeitraum_tage": tage}, 2)
    return {"aufgabe_id": aid}


@route("GET", "/api/research/marktberichte")
def r_marktberichte(kern, a):
    berichte = []
    for z in kern.db.alle("SELECT id, beendet, ergebnis FROM aufgaben WHERE typ='marktbericht' AND "
                          "status='abgeschlossen' ORDER BY beendet DESC LIMIT 50"):
        try:
            e = json.loads(z["ergebnis"] or "{}")
        except ValueError:
            continue
        berichte.append({"aufgabe_id": z["id"], "erstellt": z["beendet"], "zeitraum_tage": e.get("zeitraum_tage"),
                         "kennzahlen": e.get("kennzahlen") or {}, "bericht_url": e.get("bericht_url"),
                         "ki_zusammenfassung_vorhanden": bool(e.get("ki_zusammenfassung"))})
    in_arbeit = kern.db.alle("SELECT id AS aufgabe_id, status, erstellt, fehler FROM aufgaben WHERE typ='marktbericht' "
                             "AND status IN ('geplant','bereit','laufend','wartet_auf_freigabe') ORDER BY erstellt DESC")
    return {"berichte": berichte, "in_arbeit": in_arbeit}


@route("GET", "/api/modell/status")
def r_modell_status(kern, a):
    return kern.modell.pruefen()


@route("POST", "/api/modell/testen")
def r_modell_testen(kern, a):
    if not kern.modell.verfuegbar():
        raise ApiFehler(400, "Kein Modell eingestellt – zuerst in den Einstellungen „ollama“ wählen.")
    beginn = time.monotonic()
    try:
        antwort = kern.modell.frage_gekennzeichnet(*vorlagen.modelltest(), agent="einstellungen-test",
                                                   max_zeichen=200, zeitlimit=60)
    except ModellNichtVerfuegbar as f:
        return {"ok": False, "meldung": str(f)}
    return {"ok": True, "antwort": antwort, "dauer_ms": int((time.monotonic() - beginn) * 1000)}


@route("POST", "/api/modell/pruefstand")
def r_modell_pruefstand(kern, a):
    if not kern.modell.verfuegbar():
        raise ApiFehler(400, "Kein Modell eingestellt – zuerst in den Einstellungen „ollama“ wählen.")
    modelle = a["body"].get("modelle")
    if modelle is not None and not (
            isinstance(modelle, list) and 1 <= len(modelle) <= pruefstand.MAX_MODELLE
            and all(modelfile.modellname_ok(m) for m in modelle) and len(set(modelle)) == len(modelle)):
        raise ApiFehler(400, "modelle: Liste mit 1 bis %d verschiedenen Modellnamen, z. B. [\"gemma3:1b\", "
                             "\"autonomous\"]." % pruefstand.MAX_MODELLE)
    aid = kern.aufgaben.anlegen("KI-Prüfstand", "ki_pruefstand", "research", EIGENTUEMER,
                                {"modelle": modelle} if modelle else {}, 3)
    return {"aufgabe_id": aid,
            "hinweis": "Der Prüfstand läuft im Hintergrund (je Modell einige Minuten). Ergebnis: Aufgabe „KI-Prüfstand“ "
                       "und als Vorschlag im Gedächtnis. Umgeschaltet wird nie automatisch."}


@route("GET", "/api/modell/pruefstand")
def r_modell_pruefstaende(kern, a):
    laeufe = []
    for z in kern.db.alle("SELECT id, beendet, ergebnis FROM aufgaben WHERE typ='ki_pruefstand' AND "
                          "status='abgeschlossen' ORDER BY beendet DESC LIMIT 20"):
        try:
            e = json.loads(z["ergebnis"] or "{}")
        except ValueError:
            continue
        laeufe.append({"aufgabe_id": z["id"], "erstellt": z["beendet"], "bestes_modell": e.get("bestes_modell"),
                       "empfehlung": e.get("empfehlung"), "faelle_anzahl": e.get("faelle_anzahl"),
                       "modelle": [{s: m.get(s) for s in ("modell", "punkte", "max", "prozent", "kritisch", "fehler",
                                                         "dauer_s")}
                                   for m in e.get("modelle") or [] if isinstance(m, dict)]})
    in_arbeit = kern.db.alle("SELECT id AS aufgabe_id, status, erstellt, fehler FROM aufgaben WHERE typ='ki_pruefstand' "
                             "AND status IN ('geplant','bereit','laufend','wartet_auf_freigabe') ORDER BY erstellt DESC")
    # Ist der jüngste beendete Lauf gescheitert, steht der Grund in der Übersicht (sonst bliebe die Karte leer)
    z = kern.db.eins("SELECT id, status, aktualisiert, fehler FROM aufgaben WHERE typ='ki_pruefstand' AND "
                     "status IN ('abgeschlossen','fehlgeschlagen') ORDER BY erstellt DESC, rowid DESC LIMIT 1")
    letzter_fehler = ({"aufgabe_id": z["id"], "zeit": z["aktualisiert"], "fehler": z["fehler"] or "unbekannt"}
                      if z and z["status"] == "fehlgeschlagen" else None)
    return {"laeufe": laeufe, "in_arbeit": in_arbeit, "letzter_fehler": letzter_fehler}
