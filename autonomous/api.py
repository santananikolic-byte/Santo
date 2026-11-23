# -*- coding: utf-8 -*-
"""JSON-Schnittstelle. Routen registrieren sich über @route; weitere Module (api_vertrieb.py)
können eigene Routen ergänzen.

Jede Route bekommt (kern, anfrage) und gibt ein JSON-fähiges Objekt zurück.
anfrage: dict mit 'pfad', 'parameter' (aus dem Muster), 'query' (dict), 'body' (dict).
Alle Aktionen aus der Oberfläche handeln als 'eigentuemer' – die Oberfläche ist nur mit
dem lokalen Zugangsschlüssel erreichbar.
"""

import re

from . import sicherung
from .berechtigungen import AKTIONEN
from .modell import ANBIETER

ROUTEN = []
EIGENTUEMER = "eigentuemer"


class ApiFehler(Exception):
    def __init__(self, status, meldung):
        super().__init__(meldung)
        self.status = status
        self.meldung = meldung


def route(methode, muster):
    regex = re.compile("^" + re.sub(r"\{(\w+)\}", r"(?P<\1>[A-Za-z0-9_.\-]+)", muster) + "$")

    def deko(funktion):
        ROUTEN.append((methode, regex, funktion))
        return funktion
    return deko


def finden(methode, pfad):
    passt_pfad = False
    for m, regex, funktion in ROUTEN:
        treffer = regex.match(pfad)
        if treffer:
            passt_pfad = True
            if m == methode:
                return funktion, treffer.groupdict()
    if passt_pfad:
        raise ApiFehler(405, "Methode nicht erlaubt")
    raise ApiFehler(404, "Nicht gefunden")


def text(body, name, pflicht=True, laenge=2000):
    wert = body.get(name)
    if wert is None or (isinstance(wert, str) and not wert.strip()):
        if pflicht:
            raise ApiFehler(400, "Feld fehlt: %s" % name)
        return None
    if not isinstance(wert, (str, int, float)) or isinstance(wert, bool):
        raise ApiFehler(400, "Ungültiges Feld: %s" % name)
    wert = str(wert).strip()
    if len(wert) > laenge:
        raise ApiFehler(400, "Feld zu lang: %s" % name)
    return wert


def ganzzahl(body, name, standard, minimum, maximum):
    wert = body.get(name, standard)
    try:
        wert = int(wert)
    except (TypeError, ValueError):
        raise ApiFehler(400, "Ungültige Zahl: %s" % name)
    if not minimum <= wert <= maximum:
        raise ApiFehler(400, "%s muss zwischen %d und %d liegen" % (name, minimum, maximum))
    return wert


# ---------------- Status & Dashboard ----------------
@route("GET", "/api/status")
def status(kern, a):
    return kern.status()


@route("GET", "/api/dashboard")
def dashboard(kern, a):
    return {
        "status": kern.status(),
        "aktive_aufgaben": kern.aufgaben.liste("laufend", grenze=20) + kern.aufgaben.liste("bereit", grenze=20),
        "offene_freigaben": kern.supervisor.liste("offen"),
        "warnungen_protokoll": kern.protokoll.liste("warnung", 10) + kern.protokoll.liste("fehler", 10),
        "wallet": kern.wallet.uebersicht(),
        "finanzen": kern.finanzen.uebersicht(),
    }


# ---------------- Aufgaben ----------------
@route("GET", "/api/aufgaben")
def aufgaben_liste(kern, a):
    status = a["query"].get("status")
    return {"aufgaben": kern.aufgaben.liste(status or None, a["query"].get("rolle") or None),
            "zahlen": kern.aufgaben.zaehlen()}


@route("GET", "/api/aufgaben/{id}")
def aufgabe_detail(kern, a):
    x = kern.aufgaben.hole(a["parameter"]["id"])
    if not x:
        raise ApiFehler(404, "Aufgabe nicht gefunden")
    x["verlauf"] = kern.aufgaben.verlauf(x["id"])
    return x


@route("POST", "/api/aufgaben")
def aufgabe_anlegen(kern, a):
    b = a["body"]
    rolle = text(b, "rolle", laenge=60)
    typ = text(b, "typ", laenge=60)
    agent = kern.register.hole(rolle)
    if agent is None:
        raise ApiFehler(400, "Unbekannte Rolle")
    if typ not in agent.aufgabentypen:
        raise ApiFehler(400, "Rolle %s kennt den Typ %s nicht" % (rolle, typ))
    eingabe = b.get("eingabe") or {}
    if not isinstance(eingabe, dict):
        raise ApiFehler(400, "eingabe muss ein Objekt sein")
    aid = kern.aufgaben.anlegen(text(b, "titel", False, 200) or agent.aufgabentypen[typ], typ, rolle, EIGENTUEMER,
                                eingabe, ganzzahl(b, "prioritaet", 3, 1, 5),
                                sofort_bereit=bool(b.get("sofort", True)))
    return {"id": aid}


@route("POST", "/api/aufgaben/{id}/abbrechen")
def aufgabe_abbrechen(kern, a):
    kern.aufgaben.abbrechen(a["parameter"]["id"], EIGENTUEMER, text(a["body"], "grund", False, 500) or "")
    return {"ok": True}


@route("POST", "/api/aufgaben/{id}/freigeben")
def aufgabe_freigeben(kern, a):
    kern.aufgaben.freigeben(a["parameter"]["id"], EIGENTUEMER)
    return {"ok": True}


# ---------------- Freigaben ----------------
@route("GET", "/api/freigaben")
def freigaben(kern, a):
    return {"freigaben": kern.supervisor.liste(a["query"].get("status") or None)}


@route("POST", "/api/freigaben/{id}/entscheiden")
def freigabe_entscheiden(kern, a):
    entscheidung = a["body"].get("entscheidung")
    if entscheidung not in ("ja", "nein"):
        raise ApiFehler(400, "entscheidung muss 'ja' oder 'nein' sein")
    neu = kern.supervisor.entscheiden(a["parameter"]["id"], entscheidung == "ja", EIGENTUEMER,
                                      text(a["body"], "notiz", False, 500) or "")
    kern.aufgaben.freigabe_entschieden(a["parameter"]["id"], neu == "erteilt")
    return {"status": neu}


# ---------------- Agenten ----------------
@route("GET", "/api/agenten")
def agenten(kern, a):
    ergebnis = []
    for ag in kern.register.alle():
        letzte = kern.db.alle("SELECT id, titel, status, aktualisiert FROM aufgaben WHERE verantwortlich=? "
                              "ORDER BY aktualisiert DESC LIMIT 5", (ag.rolle,))
        zahlen = {z["status"]: z["n"] for z in kern.db.alle(
            "SELECT status, COUNT(*) n FROM aufgaben WHERE verantwortlich=? GROUP BY status", (ag.rolle,))}
        ergebnis.append({"rolle": ag.rolle, "name": ag.name, "beschreibung": ag.beschreibung,
                         "rechte": sorted(ag.rechte), "aufgabentypen": ag.aufgabentypen,
                         "status": "beschaeftigt" if zahlen.get("laufend") else "bereit",
                         "zahlen": zahlen, "letzte_aufgaben": letzte})
    ergebnis.append({"rolle": "supervisor", "name": "Supervisor", "beschreibung":
                     "Prüft Berechtigungen, Kosten, externe Aktionen und Ergebnisse; blockiert Unzulässiges.",
                     "rechte": [], "aufgabentypen": {}, "status": "aktiv (prüft jede Aktion)",
                     "zahlen": {}, "letzte_aufgaben": [],
                     "entscheidungen": kern.db.alle("SELECT zeit, ereignis FROM protokoll WHERE quelle='supervisor'"
                                                    " ORDER BY id DESC LIMIT 10")})
    return {"agenten": ergebnis, "max_rollen": 500}


# ---------------- Ziele & Gedächtnis ----------------
@route("GET", "/api/ziele")
def ziele(kern, a):
    return {"ziele": kern.ziele.liste()}


@route("POST", "/api/ziele")
def ziel_anlegen(kern, a):
    b = a["body"]
    return {"id": kern.ziele.anlegen(text(b, "titel", laenge=200), text(b, "beschreibung", False) or "",
                                     ganzzahl(b, "prioritaet", 3, 1, 5), EIGENTUEMER)}


@route("POST", "/api/ziele/{id}/status")
def ziel_status(kern, a):
    kern.ziele.status_setzen(a["parameter"]["id"], text(a["body"], "status", laenge=20), EIGENTUEMER)
    return {"ok": True}


@route("GET", "/api/gedaechtnis")
def gedaechtnis(kern, a):
    return {"eintraege": kern.gedaechtnis.liste(a["query"].get("art") or None, a["query"].get("thema") or None)}


@route("POST", "/api/gedaechtnis")
def gedaechtnis_anlegen(kern, a):
    b = a["body"]
    art = text(b, "art", laenge=20)
    return {"id": kern.gedaechtnis.merken(art, text(b, "thema", laenge=200), text(b, "inhalt", laenge=20000),
                                          text(b, "quelle", False, 500) or "Eigentümer", EIGENTUEMER)}


# ---------------- Wallet (SIMULATION) ----------------
@route("GET", "/api/wallet")
def wallet(kern, a):
    return dict(kern.wallet.uebersicht(), historie=kern.wallet.historie())


@route("POST", "/api/wallet/buchung")
def wallet_buchung(kern, a):
    b = a["body"]
    return kern.wallet.buchen(text(b, "art", laenge=30), text(b, "betrag", laenge=20), text(b, "kategorie", laenge=60),
                              text(b, "begruendung", laenge=500), EIGENTUEMER)


@route("POST", "/api/wallet/{id}/gegenbuchung")
def wallet_gegenbuchung(kern, a):
    return kern.wallet.gegenbuchung(a["parameter"]["id"], text(a["body"], "begruendung", laenge=500), EIGENTUEMER)


# ---------------- Reale Finanzen ----------------
@route("GET", "/api/finanzen")
def finanzen(kern, a):
    f = kern.finanzen
    return dict(f.uebersicht(), buchungen=f.buchungen(), forderungen=f.forderungen(), liquiditaet=f.liquiditaet(30))


@route("POST", "/api/finanzen/ausgabe")
def finanzen_ausgabe(kern, a):
    b = a["body"]
    return {"id": kern.finanzen.ausgabe(text(b, "betrag", laenge=20), text(b, "kategorie", laenge=60),
                                        text(b, "gegenpartei", laenge=200), text(b, "begruendung", laenge=500),
                                        EIGENTUEMER, text(b, "datum", False, 10), text(b, "beleg", False, 200))}


@route("POST", "/api/finanzen/einnahme")
def finanzen_einnahme(kern, a):
    b = a["body"]
    return {"id": kern.finanzen.einnahme(text(b, "betrag", laenge=20), text(b, "kategorie", laenge=60),
                                         text(b, "gegenpartei", laenge=200), text(b, "begruendung", laenge=500),
                                         EIGENTUEMER, text(b, "zahlungsnachweis", laenge=200),
                                         text(b, "verifiziert_von", laenge=100), text(b, "datum", False, 10),
                                         text(b, "beleg", False, 200))}


@route("POST", "/api/finanzen/{id}/gegenbuchung")
def finanzen_gegenbuchung(kern, a):
    return {"id": kern.finanzen.gegenbuchung(a["parameter"]["id"], text(a["body"], "begruendung", laenge=500),
                                             EIGENTUEMER)}


@route("POST", "/api/forderungen")
def forderung_anlegen(kern, a):
    b = a["body"]
    return {"id": kern.finanzen.forderung_anlegen(text(b, "kunde", laenge=200), text(b, "betrag", laenge=20),
                                                  EIGENTUEMER, text(b, "faellig", False, 10),
                                                  text(b, "rechnung_ref", False, 100), text(b, "notiz", False, 500))}


@route("POST", "/api/forderungen/{id}/bezahlt")
def forderung_bezahlt(kern, a):
    b = a["body"]
    return {"id": kern.finanzen.forderung_bezahlt(a["parameter"]["id"], text(b, "zahlungsnachweis", laenge=200),
                                                  text(b, "verifiziert_von", laenge=100), EIGENTUEMER,
                                                  text(b, "datum", False, 10))}


@route("POST", "/api/forderungen/{id}/stornieren")
def forderung_stornieren(kern, a):
    kern.finanzen.forderung_stornieren(a["parameter"]["id"], EIGENTUEMER)
    return {"ok": True}


@route("POST", "/api/budgets")
def budget(kern, a):
    b = a["body"]
    kern.finanzen.budget_setzen(text(b, "bereich", laenge=10), text(b, "kategorie", laenge=60),
                                text(b, "limit", laenge=20), text(b, "zeitraum", laenge=10), EIGENTUEMER)
    return {"ok": True}


# ---------------- Einstellungen, Protokoll, Sicherung ----------------
@route("GET", "/api/einstellungen")
def einstellungen(kern, a):
    return {"werte": kern.einstellungen.alle(), "modell": kern.modell.status(), "anbieter": ANBIETER,
            "aktionen": {k: {"klasse": v[0], "beschreibung": v[1]} for k, v in AKTIONEN.items()},
            "modellaufrufe": kern.modell.protokoll_liste(30), "sicherungen": sicherung.liste()}


def _wlan_schalten(kern, erlaubt):
    """Einziger Weg, den WLAN-Zugriff zu schalten – Einstellung und Lauschen bleiben immer gleich."""
    if not isinstance(erlaubt, bool):
        raise ApiFehler(400, "erlaubt muss true oder false sein")
    zugang = getattr(kern, "wlan", None)
    if zugang is None:
        raise ApiFehler(409, "Der Server läuft nicht – WLAN-Zugriff kann nur bei laufendem AUTONOMOUS geschaltet werden")
    if erlaubt:
        try:
            zugang.an()
        except ValueError as fehler:
            raise ApiFehler(400, str(fehler))
        kern.einstellungen.setze("wlan_zugriff", True, EIGENTUEMER)
    else:
        kern.einstellungen.setze("wlan_zugriff", False, EIGENTUEMER)
        zugang.aus()
    return zugang.status()


@route("GET", "/api/iphone")
def iphone_status(kern, a):
    zugang = getattr(kern, "wlan", None)
    if zugang is None:
        return {"erlaubt": bool(kern.einstellungen.hole("wlan_zugriff")), "aktiv": False,
                "hinweis": "Der Server läuft nicht."}
    return zugang.status()


@route("POST", "/api/iphone")
def iphone_schalten(kern, a):
    return _wlan_schalten(kern, a["body"].get("erlaubt"))


@route("POST", "/api/einstellungen")
def einstellung_setzen(kern, a):
    b = a["body"]
    schluessel = text(b, "schluessel", laenge=60)
    if "wert" not in b:
        raise ApiFehler(400, "Feld fehlt: wert")
    if schluessel == "wlan_zugriff":
        _wlan_schalten(kern, b["wert"])
        return {"ok": True, "werte": kern.einstellungen.alle()}
    kern.einstellungen.setze(schluessel, b["wert"], EIGENTUEMER)
    return {"ok": True, "werte": kern.einstellungen.alle()}


@route("GET", "/api/protokoll")
def protokoll(kern, a):
    return {"eintraege": kern.protokoll.liste(a["query"].get("ebene") or None, 300)}


@route("POST", "/api/sicherung")
def sicherung_erstellen(kern, a):
    import os
    return {"datei": os.path.basename(sicherung.sichern(kern))}


@route("POST", "/api/export")
def export(kern, a):
    import os
    return {"datei": os.path.basename(sicherung.exportieren(kern))}
