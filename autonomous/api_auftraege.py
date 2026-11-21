# -*- coding: utf-8 -*-
"""Schnittstelle für das Auftrags-Radar (öffentliche Ausschreibungen). Wird von server.py geladen.

Alle Aufrufe kommen aus der Oberfläche und handeln als Eigentümer. Suchen und Vorbereiten laufen als
Aufgaben des Akquise-Agenten über den Orchestrator. Abgegeben wird nie etwas.
"""

import json

from .api import EIGENTUEMER, ApiFehler, ganzzahl, route, text
from . import auftraege
from .auftraege import QUELLEN_NAMEN, STUFEN, tage_bis
from .agenten.akquise import mappe_vorhanden
from .db import jetzt

GEWONNEN_HINWEIS = ("Gewonnen ist noch keine Einnahme: Rechnung stellen und im Bereich Finanzen eine Forderung "
                    "anlegen – als Einnahme zählt erst der geprüfte Zahlungseingang.")


def _aufbereiten(z):
    z = dict(z)
    for feld, standard in (("cpv", []), ("begruendung", [])):
        try:
            z[feld] = json.loads(z.get(feld) or "[]")
        except ValueError:
            z[feld] = standard
    z["tage_bis_frist"] = tage_bis(z.get("frist"))
    z["quelle_name"] = QUELLEN_NAMEN.get(z["quelle"], z["quelle"])
    z["unterlagen_url"] = "/produkte/" + z["unterlagen"] if mappe_vorhanden(z.get("unterlagen")) else None
    return z


@route("GET", "/api/ausschreibungen")
def r_liste(kern, a):
    q = a["query"]
    sql, p = "SELECT * FROM ausschreibungen WHERE 1=1", []
    status = q.get("status")
    if status:
        if status not in STUFEN:
            raise ApiFehler(400, "Unbekannter Status – erlaubt: %s" % ", ".join(STUFEN))
        sql += " AND status=?"
        p.append(status)
    if q.get("min_punkte"):
        sql += " AND punkte >= ?"
        p.append(ganzzahl(q, "min_punkte", 0, 0, 100))
    if q.get("alle") != "1":
        sql += " AND (frist IS NULL OR substr(frist,1,10) >= ?)"
        p.append(auftraege.heute().isoformat())
    sql += " ORDER BY punkte DESC, CASE WHEN frist IS NULL THEN 1 ELSE 0 END, frist LIMIT 500"
    letzte = kern.db.alle("SELECT quelle, zeit, ergebnis, gefunden, neu, passend, meldung FROM suchlaeufe s WHERE "
                          "id = (SELECT MAX(id) FROM suchlaeufe WHERE quelle = s.quelle) ORDER BY quelle")
    for z in letzte:
        z["quelle_name"] = QUELLEN_NAMEN.get(z["quelle"], z["quelle"])
    e = kern.einstellungen.alle()
    return {"ausschreibungen": [_aufbereiten(z) for z in kern.db.alle(sql, p)],
            "stufen": list(STUFEN),
            "letzte_suche": letzte,
            "einstellungen": {"internet_recherche_erlaubt": e["internet_recherche_erlaubt"],
                              "auftragssuche_taeglich": e["auftragssuche_taeglich"]}}


@route("POST", "/api/ausschreibungen/suchen")
def r_suchen(kern, a):
    if not kern.einstellungen.hole("internet_recherche_erlaubt"):
        raise ApiFehler(400, "Die Internet-Recherche ist ausgeschaltet. Bitte unter Einstellungen einmal einschalten – "
                             "dann dürfen die Agenten öffentliche Ausschreibungsseiten lesen (nur lesen).")
    offen = kern.db.eins("SELECT id FROM aufgaben WHERE typ='ausschreibungen_suchen' AND status IN "
                         "('geplant','bereit','laufend')")
    if offen:
        return {"aufgabe_id": offen["id"], "hinweis": "Eine Suche läuft bereits."}
    aid = kern.aufgaben.anlegen("Ausschreibungen suchen", "ausschreibungen_suchen", "akquise", EIGENTUEMER, {}, 2,
                                max_versuche=2)
    return {"aufgabe_id": aid}


@route("POST", "/api/ausschreibungen/{id}/status")
def r_status(kern, a):
    b = a["body"]
    status = text(b, "status", laenge=20)
    if status not in STUFEN:
        raise ApiFehler(400, "Unbekannter Status – erlaubt: %s" % ", ".join(STUFEN))
    aid = a["parameter"]["id"]
    if not kern.db.eins("SELECT id FROM ausschreibungen WHERE id=?", (aid,)):
        raise ApiFehler(404, "Ausschreibung nicht gefunden")
    if "notiz" in b:
        kern.db.ausfuehren("UPDATE ausschreibungen SET status=?, notiz=?, aktualisiert=? WHERE id=?",
                           (status, text(b, "notiz", False, 1000), jetzt(), aid))
    else:
        kern.db.ausfuehren("UPDATE ausschreibungen SET status=?, aktualisiert=? WHERE id=?", (status, jetzt(), aid))
    kern.protokoll.audit("akquise", "Ausschreibungsstatus geändert", {"id": aid, "status": status})
    antwort = {"ok": True}
    if status == "gewonnen":
        antwort["hinweis"] = GEWONNEN_HINWEIS
    return antwort


@route("POST", "/api/ausschreibungen/{id}/vorbereiten")
def r_vorbereiten(kern, a):
    aid = a["parameter"]["id"]
    zeile = kern.db.eins("SELECT id, titel, status, unterlagen FROM ausschreibungen WHERE id=?", (aid,))
    if not zeile:
        raise ApiFehler(404, "Ausschreibung nicht gefunden")
    if mappe_vorhanden(zeile["unterlagen"]):
        raise ApiFehler(409, "Für diese Ausschreibung gibt es schon eine Mappe: /produkte/%s" % zeile["unterlagen"])
    if zeile["status"] in ("abgelehnt", "gewonnen", "verloren"):
        raise ApiFehler(400, "Ausschreibung hat den Status „%s“ – keine Mappe nötig." % zeile["status"])
    neu = kern.aufgaben.anlegen("Bewerbungs-Mappe: %s" % zeile["titel"][:120], "ausschreibung_vorbereiten",
                                "akquise", EIGENTUEMER, {"ausschreibung_id": aid}, 2)
    return {"aufgabe_id": neu}
