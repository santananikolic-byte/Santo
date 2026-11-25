# -*- coding: utf-8 -*-
"""Schnittstelle für den Überlebens-Agenten und die festen Kosten. Wird von server.py geladen.

GET  /api/ueberleben                    → {druck, begruendung, reichweite_monate, einnahmen_30_tage, ausgaben_30_tage,
                                           saldo, offene_forderungen, fixkosten_monat, geldchancen[], letzter_plan, …}
POST /api/ueberleben/plan               → {aufgabe_id} (ist schon ein Plan offen, dessen ID und ein Hinweis)
GET  /api/fixkosten                     → {fixkosten[], summe_monat, summe_monat_cent, entfernt[], hinweis}
POST /api/fixkosten {bezeichnung, betrag, intervall = monat|jahr, seit?}  → {id}
POST /api/fixkosten/{id}/entfernen      → {ok}

Alle Aufrufe kommen aus der Oberfläche und handeln als Eigentümer. Gesendet, bezahlt oder abgegeben wird nichts:
der Plan läuft als Aufgabe des Überlebens-Agenten, der nur interne Folgeaufgaben anstößt.
"""

from . import ueberleben
from .api import EIGENTUEMER, ApiFehler, route, text

GELDCHANCEN_ANZEIGE = 25


@route("GET", "/api/ueberleben")
def r_ueberleben(kern, a):
    tag = ueberleben.heute()
    chancen = ueberleben.geldchancen(kern, tag)
    return dict(ueberleben.lage(kern, tag), geldchancen=chancen[:GELDCHANCEN_ANZEIGE],
                geldchancen_gesamt=len(chancen), letzter_plan=ueberleben.letzter_plan(kern),
                plan_in_arbeit=ueberleben.plan_in_arbeit(kern))


@route("POST", "/api/ueberleben/plan")
def r_plan(kern, a):
    aid, neu = ueberleben.plan_anlegen(kern, EIGENTUEMER)
    antwort = {"aufgabe_id": aid}
    if not neu:
        antwort["hinweis"] = "Ein Überlebensplan ist schon in Arbeit."
    return antwort


@route("GET", "/api/fixkosten")
def r_fixkosten(kern, a):
    return ueberleben.fixkosten_uebersicht(kern)


@route("POST", "/api/fixkosten")
def r_fixkosten_anlegen(kern, a):
    b = a["body"]
    try:
        fid = ueberleben.fixkosten_anlegen(kern, text(b, "bezeichnung", laenge=120), text(b, "betrag", laenge=20),
                                           text(b, "intervall", laenge=10), EIGENTUEMER, text(b, "seit", False, 10))
    except ValueError as fehler:
        raise ApiFehler(400, str(fehler))
    return {"id": fid}


@route("POST", "/api/fixkosten/{id}/entfernen")
def r_fixkosten_entfernen(kern, a):
    try:
        ueberleben.fixkosten_entfernen(kern, a["parameter"]["id"], EIGENTUEMER)
    except KeyError:
        raise ApiFehler(404, "Eintrag nicht gefunden oder schon entfernt")
    return {"ok": True}
