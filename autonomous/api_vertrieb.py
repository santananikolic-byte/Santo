# -*- coding: utf-8 -*-
"""Schnittstelle für Produkte und Vertrieb (Phase 5). Wird von server.py automatisch geladen.

Alle Aufrufe kommen aus der Oberfläche und handeln als Eigentümer. Erzeugt wird nichts direkt hier:
die Routen legen Aufgaben für Product- oder Sales-Agent an; der Orchestrator arbeitet sie ab.
Ausnahme: Statusänderungen, die der Eigentümer selbst entscheidet (Kontaktstatus, Angebotsstatus).
"""

import json

from .api import EIGENTUEMER, ApiFehler, ganzzahl, route, text
from .db import jetzt, neue_id
from .produkte import datei_schreiben, produkt_hole, produkte_liste, sicherer_pfad
from .produkte import angebot as angebot_vorlage
from .produkte import verkaufsseite, webseite
from .wallet import euro

STUFEN = ["neu", "kontaktiert", "interessiert", "angebot", "gewonnen", "verloren"]
# Vom Eigentümer setzbare Angebotsstatus und erlaubte Wechsel
ANGEBOT_WECHSEL = {
    "entwurf": {"geprueft", "abgelehnt"},
    "geprueft": {"versendet", "abgelehnt"},
    "versendet": {"angenommen", "abgelehnt"},
    "angenommen": set(),
    "abgelehnt": set(),
}
KEINE_EINNAHME = ("Ein angenommenes Angebot ist keine Einnahme. Lege im Bereich Finanzen eine Forderung an; "
                  "als Einnahme zählt erst der verifizierte Zahlungseingang.")


def _felder(body, namen):
    return {n: body[n] for n in namen if n in body and body[n] is not None}


# ---------------------------------------------------------------- Produkte
@route("GET", "/api/produkte")
def r_produkte(kern, a):
    return {"produkte": produkte_liste(kern)}


@route("GET", "/api/produkte/{id}")
def r_produkt(kern, a):
    p = produkt_hole(kern, a["parameter"]["id"])
    if not p:
        raise ApiFehler(404, "Produkt nicht gefunden")
    return p


@route("POST", "/api/produkte/webseite")
def r_webseite(kern, a):
    eingabe = _felder(a["body"], webseite.FELDER)
    d = webseite.eingabe_pruefen(eingabe)  # Fehler sofort melden (400), nicht erst in der Aufgabe
    aid = kern.aufgaben.anlegen("Webseite erstellen: %s" % d["firma"], "webseite_erstellen", "product", EIGENTUEMER,
                                eingabe, ganzzahl(a["body"], "prioritaet", 2, 1, 5))
    return {"aufgabe_id": aid}


@route("POST", "/api/produkte/verkaufsseite")
def r_verkaufsseite(kern, a):
    eingabe = _felder(a["body"], ("preis", "lieferzeit", "preis_hinweis", "anbieter", "region", "telefon", "email"))
    verkaufsseite.eingabe_pruefen(eingabe)
    aid = kern.aufgaben.anlegen("Verkaufsseite erstellen", "verkaufsseite_erstellen", "product", EIGENTUEMER, eingabe,
                                ganzzahl(a["body"], "prioritaet", 2, 1, 5))
    return {"aufgabe_id": aid}


@route("POST", "/api/produkte/{id}/pruefen")
def r_produkt_pruefen(kern, a):
    p = produkt_hole(kern, a["parameter"]["id"])
    if not p:
        raise ApiFehler(404, "Produkt nicht gefunden")
    aid = kern.aufgaben.anlegen("Qualität prüfen: %s" % p["name"], "qualitaetspruefung", "product", EIGENTUEMER,
                                {"produkt_id": p["id"]}, 2)
    return {"aufgabe_id": aid}


# ---------------------------------------------------------------- Kontakte
@route("GET", "/api/kontakte")
def r_kontakte(kern, a):
    reihenfolge = " ".join("WHEN '%s' THEN %d" % (s, i) for i, s in enumerate(STUFEN))
    return {"kontakte": kern.db.alle("SELECT * FROM kontakte ORDER BY CASE status %s END, aktualisiert DESC"
                                     % reihenfolge),
            "stufen": list(STUFEN)}


@route("POST", "/api/kontakte")
def r_kontakt_anlegen(kern, a):
    b = a["body"]
    firma = text(b, "firma", laenge=120)
    quelle = text(b, "quelle", laenge=200)
    einwilligung = text(b, "einwilligung", False, 10) or "keine"
    if einwilligung not in ("keine", "ja"):
        raise ApiFehler(400, "einwilligung muss 'keine' oder 'ja' sein")
    nachweis = text(b, "einwilligung_nachweis", False, 300)
    if einwilligung == "ja" and not nachweis:
        raise ApiFehler(400, "Bei Einwilligung 'ja' ist ein Nachweis Pflicht (wann, wie, von wem).")
    ort = text(b, "ort", False, 80)
    doppelt = kern.db.eins("SELECT id FROM kontakte WHERE lower(firma)=lower(?) AND lower(COALESCE(ort,''))="
                           "lower(COALESCE(?,''))", (firma, ort))
    if doppelt:
        raise ApiFehler(409, "Kontakt mit gleicher Firma und gleichem Ort gibt es schon (%s)" % doppelt["id"])
    kid = neue_id("k_")
    z = jetzt()
    kern.db.ausfuehren(
        "INSERT INTO kontakte (id, firma, ansprechpartner, branche, ort, quelle, einwilligung, einwilligung_nachweis,"
        " status, naechster_schritt, notizen, erstellt, aktualisiert) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (kid, firma, text(b, "ansprechpartner", False, 120), text(b, "branche", False, 80), ort, quelle,
         einwilligung, nachweis if einwilligung == "ja" else None, "neu", text(b, "naechster_schritt", False, 300),
         text(b, "notizen", False, 2000), z, z))
    kern.protokoll.audit("vertrieb", "Kontakt angelegt", {"id": kid, "einwilligung": einwilligung})
    return {"id": kid}


@route("POST", "/api/kontakte/{id}/status")
def r_kontakt_status(kern, a):
    b = a["body"]
    status = text(b, "status", laenge=20)
    if status not in STUFEN:
        raise ApiFehler(400, "Unbekannter Status – erlaubt: %s" % ", ".join(STUFEN))
    kid = a["parameter"]["id"]
    if not kern.db.eins("SELECT id FROM kontakte WHERE id=?", (kid,)):
        raise ApiFehler(404, "Kontakt nicht gefunden")
    if "naechster_schritt" in b:
        kern.db.ausfuehren("UPDATE kontakte SET status=?, naechster_schritt=?, aktualisiert=? WHERE id=?",
                           (status, text(b, "naechster_schritt", False, 300), jetzt(), kid))
    else:
        kern.db.ausfuehren("UPDATE kontakte SET status=?, aktualisiert=? WHERE id=?", (status, jetzt(), kid))
    kern.protokoll.audit("vertrieb", "Kontaktstatus geändert", {"id": kid, "status": status})
    return {"ok": True}


# ---------------------------------------------------------------- Angebote
def _angebot_aufbereiten(z):
    z = dict(z)
    try:
        z["inhalt"] = json.loads(z.get("inhalt") or "{}")
    except ValueError:
        z["inhalt"] = {}
    z["betrag"] = euro(z["betrag_cent"])
    z["ansehen_url"] = "/produkte/" + z["datei"] if z.get("datei") else None
    return z


@route("GET", "/api/angebote")
def r_angebote(kern, a):
    zeilen = kern.db.alle("SELECT a.*, k.firma AS kontakt_firma FROM angebote a LEFT JOIN kontakte k "
                          "ON k.id=a.kontakt_id ORDER BY a.erstellt DESC LIMIT 300")
    return {"angebote": [_angebot_aufbereiten(z) for z in zeilen]}


@route("POST", "/api/angebote")
def r_angebot_anlegen(kern, a):
    b = a["body"]
    eingabe = _felder(b, ("kontakt_id", "produkt_id", "titel", "betrag", "leistungen", "lieferzeit", "gueltig_bis",
                          "preis_hinweis", "anbieter", "anbieter_anschrift", "anbieter_kontakt"))
    d = angebot_vorlage.eingabe_pruefen(eingabe)
    if d["kontakt_id"] and not kern.db.eins("SELECT id FROM kontakte WHERE id=?", (d["kontakt_id"],)):
        raise ApiFehler(404, "Kontakt nicht gefunden")
    if d["produkt_id"] and not produkt_hole(kern, d["produkt_id"]):
        raise ApiFehler(404, "Produkt nicht gefunden")
    aid = kern.aufgaben.anlegen("Angebot entwerfen (%s)" % euro(d["betrag_cent"]), "angebot_entwurf", "sales",
                                EIGENTUEMER, eingabe, ganzzahl(b, "prioritaet", 2, 1, 5))
    return {"aufgabe_id": aid}


@route("POST", "/api/angebote/{id}/status")
def r_angebot_status(kern, a):
    neu = text(a["body"], "status", laenge=20)
    if neu not in ("geprueft", "versendet", "angenommen", "abgelehnt"):
        raise ApiFehler(400, "Status muss geprueft, versendet, angenommen oder abgelehnt sein")
    ang = kern.db.eins("SELECT * FROM angebote WHERE id=?", (a["parameter"]["id"],))
    if not ang:
        raise ApiFehler(404, "Angebot nicht gefunden")
    if neu not in ANGEBOT_WECHSEL[ang["status"]]:
        raise ApiFehler(400, "Wechsel %s → %s nicht erlaubt%s" % (
            ang["status"], neu, " (erst prüfen, dann selbst versenden)" if neu == "versendet" else ""))
    datei = ang["datei"]
    if neu == "geprueft":
        # Geprüfte Fassung ohne ENTWURF-Hinweis als neue Datei; der Entwurf bleibt erhalten
        inhalt = json.loads(ang["inhalt"] or "{}")
        pfad = sicherer_pfad("angebote", ang["id"], "angebot-geprueft.html")
        try:
            datei_schreiben(pfad, angebot_vorlage.erzeugen(inhalt, entwurf=False))
        except FileExistsError:
            raise ApiFehler(409, "Geprüfte Fassung existiert bereits")
        datei = "angebote/%s/angebot-geprueft.html" % ang["id"]
    n = kern.db.ausfuehren("UPDATE angebote SET status=?, datei=?, aktualisiert=? WHERE id=? AND status=?",
                           (neu, datei, jetzt(), ang["id"], ang["status"]))
    if n != 1:
        raise ApiFehler(409, "Angebot wurde parallel geändert")
    kern.protokoll.audit("vertrieb", "Angebotsstatus geändert", {"id": ang["id"], "von": ang["status"], "nach": neu})
    antwort = {"ok": True, "status": neu, "ansehen_url": "/produkte/" + datei if datei else None}
    if neu == "angenommen":
        antwort["hinweis"] = KEINE_EINNAHME
    return antwort


@route("POST", "/api/angebote/{id}/versenden")
def r_angebot_versenden(kern, a):
    ang = kern.db.eins("SELECT id, status, titel FROM angebote WHERE id=?", (a["parameter"]["id"],))
    if not ang:
        raise ApiFehler(404, "Angebot nicht gefunden")
    if ang["status"] != "geprueft":
        raise ApiFehler(400, "Nur geprüfte Angebote können versendet werden – bitte zuerst prüfen.")
    aid = kern.aufgaben.anlegen("Angebot versenden: %s" % ang["titel"], "angebot_versenden", "sales", EIGENTUEMER,
                                {"angebot_id": ang["id"]}, 2)
    return {"aufgabe_id": aid}


# ---------------------------------------------------------------- Nachrichten
@route("POST", "/api/vertrieb/nachricht")
def r_nachricht(kern, a):
    b = a["body"]
    kid = text(b, "kontakt_id", laenge=64)
    kontakt = kern.db.eins("SELECT id, firma FROM kontakte WHERE id=?", (kid,))
    if not kontakt:
        raise ApiFehler(404, "Kontakt nicht gefunden")
    aid = kern.aufgaben.anlegen("Nachricht entwerfen: %s" % kontakt["firma"], "nachricht_entwurf", "sales",
                                EIGENTUEMER, {"kontakt_id": kid, "anlass": text(b, "anlass", False, 200) or "Erstkontakt"},
                                2)
    return {"aufgabe_id": aid}


@route("POST", "/api/vertrieb/auswertung")
def r_auswertung(kern, a):
    aid = kern.aufgaben.anlegen("Vertriebs-Pipeline auswerten", "pipeline_auswertung", "sales", EIGENTUEMER, {}, 3)
    return {"aufgabe_id": aid}

