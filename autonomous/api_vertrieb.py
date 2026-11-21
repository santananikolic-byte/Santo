# -*- coding: utf-8 -*-
"""Schnittstelle für Produkte und Vertrieb (Phase 5). Wird von server.py automatisch geladen.

Alle Aufrufe kommen aus der Oberfläche und handeln als Eigentümer. Erzeugt wird nichts direkt hier:
die Routen legen Aufgaben für Product- oder Sales-Agent an; der Orchestrator arbeitet sie ab.
Ausnahme: Statusänderungen, die der Eigentümer selbst entscheidet (Kontaktstatus, Angebotsstatus).
"""

import json
import re

from .agenten.learning import ANGEBOT_ARTEN as RM_ARTEN
from .agenten.learning import GRUENDE as RM_GRUENDE
from .agenten.learning import GRUND_BEI as RM_GRUND_BEI
from .agenten.learning import KANAELE as RM_KANAELE
from .agenten.learning import REAKTIONEN as RM_REAKTIONEN
from .api import EIGENTUEMER, ApiFehler, ganzzahl, route, text
from .db import jetzt, neue_id
from .produkte import datei_schreiben, produkt_hole, produkte_liste, sicherer_pfad
from .produkte import angebot as angebot_vorlage
from .produkte import google_profil, verkaufsseite, webseite
from .produkte import kalkulation as kalkulation_modul
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


@route("POST", "/api/produkte/google_profil")
def r_google_profil(kern, a):
    eingabe = _felder(a["body"], google_profil.FELDER)
    d = google_profil.eingabe_pruefen(eingabe)  # Fehler sofort melden (400), nicht erst in der Aufgabe
    aid = kern.aufgaben.anlegen("Google-Profil-Paket: %s" % d["firma"], "google_profil_paket", "product", EIGENTUEMER,
                                eingabe, ganzzahl(a["body"], "prioritaet", 2, 1, 5))
    return {"aufgabe_id": aid}


@route("POST", "/api/produkte/verkaufsseite")
def r_verkaufsseite(kern, a):
    eingabe = _felder(a["body"], ("angebot", "preis", "lieferzeit", "preis_hinweis", "anbieter", "region", "telefon",
                                  "email"))
    d = verkaufsseite.eingabe_pruefen(eingabe)
    titel = "Verkaufsseite erstellen (%s)" % ("Google-Profil-Paket" if d["angebot"] == "google_profil"
                                              else "Webseiten-Paket")
    aid = kern.aufgaben.anlegen(titel, "verkaufsseite_erstellen", "product", EIGENTUEMER, eingabe,
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
    z["art"] = (z["inhalt"] or {}).get("art") or "einmalig"
    z["abrechnung"] = "monatlich" if z["art"] == "reinigung_dauerauftrag" else "einmalig"
    z["betrag"] = euro(z["betrag_cent"]) + (" pro Monat (netto)" if z["abrechnung"] == "monatlich" else "")
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
                          "preis_hinweis", "anbieter", "anbieter_anschrift", "anbieter_kontakt", "art", "positionen",
                          "kalkulation_aufgabe_id", "objekt", "vertragsbeginn", "laufzeit", "kuendigungsfrist"))
    kalk = None
    if eingabe.get("kalkulation_aufgabe_id") not in (None, ""):
        kid = eingabe["kalkulation_aufgabe_id"]
        if not isinstance(kid, str) or len(kid) > 64:
            raise ApiFehler(400, "kalkulation_aufgabe_id ungültig")
        try:
            kalk = kalkulation_modul.aus_aufgabe(kern.aufgaben.hole(kid))
        except KeyError:
            raise ApiFehler(404, "Kalkulation nicht gefunden")
        except ValueError as fehler:
            raise ApiFehler(400, str(fehler))
    try:
        d = angebot_vorlage.eingabe_pruefen(eingabe, kalk)
    except ValueError as fehler:
        raise ApiFehler(400, str(fehler))
    if d["kontakt_id"] and not kern.db.eins("SELECT id FROM kontakte WHERE id=?", (d["kontakt_id"],)):
        raise ApiFehler(404, "Kontakt nicht gefunden")
    if d["produkt_id"] and not produkt_hole(kern, d["produkt_id"]):
        raise ApiFehler(404, "Produkt nicht gefunden")
    titel = ("Angebot entwerfen (%s pro Monat, Dauerauftrag)" % euro(d["betrag_cent"])
             if d["art"] == "reinigung_dauerauftrag" else "Angebot entwerfen (%s)" % euro(d["betrag_cent"]))
    aid = kern.aufgaben.anlegen(titel, "angebot_entwurf", "sales", EIGENTUEMER, eingabe,
                                ganzzahl(b, "prioritaet", 2, 1, 5))
    return {"aufgabe_id": aid}


# ---------------------------------------------------------------- Kalkulation
@route("POST", "/api/kalkulation/reinigung")
def r_kalkulation_reinigung(kern, a):
    """Monatspreis für einen Reinigungs-Dauerauftrag rechnen (Finance-Agent). Ohne Stundensatz bleibt er OFFEN."""
    eingabe = _felder(a["body"], ("positionen", "stundensatz", "material_prozent", "anfahrten_pro_monat",
                                  "anfahrt_minuten", "zuschlag_prozent"))
    try:
        d = kalkulation_modul.eingabe_pruefen(eingabe)  # Fehler sofort melden (400)
    except ValueError as fehler:
        raise ApiFehler(400, str(fehler))
    titel = "Reinigung kalkulieren: %s" % ", ".join(p["bezeichnung"] for p in d["positionen"][:3])
    if len(d["positionen"]) > 3:
        titel += " …"
    aid = kern.aufgaben.anlegen(titel[:200], "kalkulation_reinigung", "finance", EIGENTUEMER, eingabe,
                                ganzzahl(a["body"], "prioritaet", 2, 1, 5))
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
    angebot = text(b, "angebot", False, 20) or "google_profil"
    if angebot not in ("google_profil", "webseite", "reinigung"):
        raise ApiFehler(400, "angebot muss google_profil, webseite oder reinigung sein")
    aid = kern.aufgaben.anlegen("Nachricht entwerfen: %s" % kontakt["firma"], "nachricht_entwurf", "sales",
                                EIGENTUEMER, {"kontakt_id": kid, "anlass": text(b, "anlass", False, 200) or "Erstkontakt",
                                              "angebot": angebot}, 2)
    return {"aufgabe_id": aid}


@route("POST", "/api/vertrieb/auswertung")
def r_auswertung(kern, a):
    aid = kern.aufgaben.anlegen("Vertriebs-Pipeline auswerten", "pipeline_auswertung", "sales", EIGENTUEMER, {}, 3)
    return {"aufgabe_id": aid}



# ---------------------------------------------------------------- Rückmeldungen (PDF 2.3: Reaktionen messen)
_EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
_TELEFON = re.compile(r"(?<![\w.])(?:\+|0)\d[\d /()\-]{5,}\d")


def _personendaten_in_notiz(notiz):
    """Datensparsamkeit: E-Mail-Adressen und Telefonnummern gehören in den Kontakt, nicht in die Notiz."""
    if _EMAIL.search(notiz):
        return True
    return any(len(re.sub(r"\D", "", t)) >= 7 for t in _TELEFON.findall(notiz))


@route("GET", "/api/rueckmeldungen")
def r_rueckmeldungen(kern, a):
    zeilen = kern.db.alle(
        "SELECT r.*, k.firma AS kontakt_firma, an.titel AS angebot_titel FROM rueckmeldungen r "
        "LEFT JOIN kontakte k ON k.id = r.kontakt_id LEFT JOIN angebote an ON an.id = r.angebot_id "
        "ORDER BY r.zeit DESC, r.rowid DESC LIMIT 500")
    return {"rueckmeldungen": zeilen, "reaktionen": list(RM_REAKTIONEN), "gruende": list(RM_GRUENDE),
            "kanaele": list(RM_KANAELE), "angebot_arten": list(RM_ARTEN)}


@route("POST", "/api/rueckmeldungen")
def r_rueckmeldung_anlegen(kern, a):
    """Erfasst eine echte Rückmeldung. Nur der Eigentümer erfasst – Agenten erfinden keine Rückmeldungen."""
    b = a["body"]
    art = text(b, "angebot_art", laenge=20)
    kanal = text(b, "kanal", laenge=20)
    reaktion = text(b, "reaktion", laenge=20)
    if art not in RM_ARTEN:
        raise ApiFehler(400, "angebot_art muss eines von %s sein" % ", ".join(RM_ARTEN))
    if kanal not in RM_KANAELE:
        raise ApiFehler(400, "kanal muss eines von %s sein" % ", ".join(RM_KANAELE))
    if reaktion not in RM_REAKTIONEN:
        raise ApiFehler(400, "reaktion muss eines von %s sein" % ", ".join(RM_REAKTIONEN))
    grund = text(b, "grund", False, 20)
    if grund is not None:
        if grund not in RM_GRUENDE:
            raise ApiFehler(400, "grund muss eines von %s sein" % ", ".join(RM_GRUENDE))
        if reaktion not in RM_GRUND_BEI:
            raise ApiFehler(400, "Ein Grund passt nur zu den Reaktionen abgelehnt oder neutral.")
    notiz = text(b, "notiz", False, 2000)
    if notiz and _personendaten_in_notiz(notiz):
        raise ApiFehler(400, "Bitte keine E-Mail-Adressen oder Telefonnummern in die Notiz schreiben – die gehören "
                             "in den Kontakt (Datensparsamkeit).")
    kontakt_id = text(b, "kontakt_id", False, 64)
    angebot_id = text(b, "angebot_id", False, 64)
    if kontakt_id and not kern.db.eins("SELECT id FROM kontakte WHERE id=?", (kontakt_id,)):
        raise ApiFehler(404, "Kontakt nicht gefunden")
    if angebot_id:
        ang = kern.db.eins("SELECT id, kontakt_id FROM angebote WHERE id=?", (angebot_id,))
        if not ang:
            raise ApiFehler(404, "Angebot nicht gefunden")
        if kontakt_id and ang["kontakt_id"] and ang["kontakt_id"] != kontakt_id:
            raise ApiFehler(400, "Das Angebot gehört zu einem anderen Kontakt.")
        kontakt_id = kontakt_id or ang["kontakt_id"]
    rid = neue_id("rm_")
    kern.db.ausfuehren("INSERT INTO rueckmeldungen (id, zeit, kontakt_id, angebot_id, angebot_art, kanal, reaktion, "
                       "grund, notiz, erfasst_von) VALUES (?,?,?,?,?,?,?,?,?,?)",
                       (rid, jetzt(), kontakt_id, angebot_id, art, kanal, reaktion, grund, notiz, EIGENTUEMER))
    # Protokoll ohne Notiztext (Datensparsamkeit)
    kern.protokoll.audit("vertrieb", "Rückmeldung erfasst", {"id": rid, "angebot_art": art, "reaktion": reaktion})
    return {"id": rid}


@route("POST", "/api/rueckmeldungen/auswerten")
def r_rueckmeldungen_auswerten(kern, a):
    aid = kern.aufgaben.anlegen("Rückmeldungen auswerten", "rueckmeldungen_auswerten", "learning", EIGENTUEMER, {}, 3)
    return {"aufgabe_id": aid}
