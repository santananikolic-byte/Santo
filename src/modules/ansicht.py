#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Die Anzeige - das zweite Gehirn und die Kommandozentrale.

Zwei Seiten für zwei Bildschirme, nur zum Ansehen, ohne Eingabefeld:

* ``/gehirn``: Jarvis' Gedächtnis als leuchtendes Gehirn. Jede Notiz, jeder
  Kontakt, jeder Interessent, jede Aufgabe, jedes Gespräch und jedes Ergebnis
  des Autopiloten sitzt als Knoten darin, verwandte sind verbunden. Es pulsiert
  schneller, wenn Jarvis zuhört, denkt oder spricht, und blitzt auf, wenn er
  etwas tut.
* ``/zentrale``: der Stand des Betriebs auf einen Blick, mit Globus, Kennzahlen,
  Verlauf, Pipeline, dem, was Jarvis zuletzt getan hat, und den Orten der
  Kunden.

**Es wird nur gezeigt, was wirklich in der Datenbank steht.** Wie überall im
Programm: ein leerer Bereich bleibt leer. Auf Wunsch (``ANZEIGE_DISKRET``)
bleiben die Texte der Knoten und die Namen weg, damit ein Besucher im Raum
nichts mitliest.

Die Weltkarte des Globus ist **gezeichnet, nicht vermessen**: grobe Umrisse als
Punktraster. Sie zeigt, wo etwa etwas liegt, und taugt nicht zur Navigation.
"""

import json
import re
import threading
import time
from pathlib import Path

import config

# -- Orte ----------------------------------------------------------------------------

ORTE = {
    "wien": (48.21, 16.37), "graz": (47.07, 15.44), "linz": (48.31, 14.29),
    "salzburg": (47.81, 13.04), "innsbruck": (47.27, 11.39), "klagenfurt": (46.62, 14.31),
    "villach": (46.61, 13.85), "st. poelten": (48.2, 15.63), "sankt poelten": (48.2, 15.63),
    "bregenz": (47.5, 9.75), "eisenstadt": (47.85, 16.52), "dornbirn": (47.41, 9.74),
    "wels": (48.16, 14.03), "berlin": (52.52, 13.4), "hamburg": (53.55, 9.99),
    "muenchen": (48.14, 11.58), "koeln": (50.94, 6.96), "frankfurt": (50.11, 8.68),
    "stuttgart": (48.78, 9.18), "duesseldorf": (51.23, 6.78), "dresden": (51.05, 13.74),
    "leipzig": (51.34, 12.37), "nuernberg": (49.45, 11.08), "hannover": (52.37, 9.73),
    "zuerich": (47.37, 8.54), "bern": (46.95, 7.45), "basel": (47.56, 7.59),
    "genf": (46.2, 6.14), "budapest": (47.5, 19.04), "prag": (50.08, 14.44),
    "bratislava": (48.15, 17.11), "ljubljana": (46.06, 14.51), "zagreb": (45.81, 15.98),
    "rom": (41.9, 12.5), "mailand": (45.46, 9.19), "bozen": (46.5, 11.35), "paris": (48.86, 2.35),
    "london": (51.51, -0.13), "madrid": (40.42, -3.7), "barcelona": (41.39, 2.17),
    "amsterdam": (52.37, 4.9), "bruessel": (50.85, 4.35), "warschau": (52.23, 21.01),
    "stockholm": (59.33, 18.07), "oslo": (59.91, 10.75), "kopenhagen": (55.68, 12.57),
    "helsinki": (60.17, 24.94), "athen": (37.98, 23.73), "istanbul": (41.01, 28.98),
    "moskau": (55.76, 37.62), "kiew": (50.45, 30.52), "lissabon": (38.72, -9.14),
    "dublin": (53.35, -6.26), "bukarest": (44.43, 26.1), "belgrad": (44.79, 20.45),
    "sofia": (42.7, 23.32), "reykjavik": (64.15, -21.94), "dubai": (25.2, 55.27),
    "kairo": (30.04, 31.24), "lagos": (6.52, 3.38), "johannesburg": (-26.2, 28.05),
    "nairobi": (-1.29, 36.82), "casablanca": (33.57, -7.59), "addis abeba": (9.03, 38.74),
    "delhi": (28.61, 77.21), "mumbai": (19.08, 72.88), "karachi": (24.86, 67.0),
    "dhaka": (23.81, 90.41), "peking": (39.9, 116.4), "shanghai": (31.23, 121.47),
    "hongkong": (22.32, 114.17), "tokio": (35.68, 139.69), "seoul": (37.57, 126.98),
    "singapur": (1.35, 103.82), "bangkok": (13.75, 100.5), "jakarta": (-6.2, 106.85),
    "manila": (14.6, 120.98), "taipeh": (25.03, 121.57), "teheran": (35.69, 51.39),
    "riad": (24.71, 46.68), "sydney": (-33.87, 151.21), "wellington": (-41.29, 174.78),
    "new york": (40.71, -74.01), "los angeles": (34.05, -118.24), "chicago": (41.88, -87.63),
    "toronto": (43.65, -79.38), "mexiko-stadt": (19.43, -99.13), "miami": (25.76, -80.19),
    "san francisco": (37.77, -122.42), "sao paulo": (-23.55, -46.63),
    "buenos aires": (-34.6, -58.38), "lima": (-12.05, -77.04), "bogota": (4.71, -74.07),
}
# Hell leuchtende Großstädte für das Nachtbild. Die Wörter bleiben so, wie die Orte oben.
LICHTER = ["new york", "los angeles", "chicago", "toronto", "mexiko-stadt", "miami",
           "san francisco", "sao paulo", "buenos aires", "lima", "bogota", "london", "paris",
           "madrid", "rom", "mailand", "berlin", "moskau", "istanbul", "kairo", "lagos",
           "johannesburg", "nairobi", "dubai", "teheran", "delhi", "mumbai", "karachi", "dhaka",
           "peking", "shanghai", "hongkong", "tokio", "seoul", "singapur", "bangkok", "jakarta",
           "manila", "sydney", "wien", "amsterdam", "warschau", "stockholm", "kiew", "athen",
           "casablanca", "riad", "taipeh"]


def ort_schluessel(name: str) -> str:
    roh = (name or "").strip().lower()
    for alt, neu in (("ä", "ae"), ("ö", "oe"), ("ü", "ue"), ("ß", "ss"), ("é", "e"), ("ã", "a")):
        roh = roh.replace(alt, neu)
    return re.sub(r"\s+", " ", roh)


_LAENDER = {"oesterreich", "austria", "deutschland", "germany", "schweiz", "switzerland",
            "italien", "italia", "liechtenstein", "at", "de", "ch"}
_STRASSE = re.compile(r"(strasse|gasse|weg|platz|allee|ring|gürtel|guertel|kai)\b|str\.|\d")


def ort_aus_adresse(adresse: str) -> str:
    """Der Ortsname aus einer Anschrift: "Hauptstr. 5, 1010 Wien" -> "Wien".

    Der Ort steht neben der Postleitzahl - egal ob vorn, hinten, mit "A-" davor
    oder mit dem Land dahinter. Ohne Postleitzahl zählt der letzte Teil, der
    weder Land noch Straße ist.
    """
    text = str(adresse or "")
    plz = re.search(r"(?:\b[A-Z]{1,2}-)?\b\d{4,5}\s+([^\d,]+)", text)
    if plz:
        return plz.group(1).strip(" -/")[:60]
    for teil in reversed([t.strip() for t in text.split(",") if t.strip()]):
        schluessel = ort_schluessel(teil)
        if schluessel and schluessel not in _LAENDER and not _STRASSE.search(schluessel):
            return teil[:60]
    return ""


# Mehrere Abrufe der Zentrale gleichzeitig dürfen den Zwischenspeicher nicht zerschießen.
_ORTE_SPERRE = threading.Lock()
_ORTE_IN_ARBEIT = set()


def _orte_cache(cache_datei=None):
    datei = Path(cache_datei or (config.LOG_VERZEICHNIS / "orte.json"))
    try:
        return datei, json.loads(datei.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return datei, {}


def ort_gespeichert(name: str, cache_datei=None):
    """``(bekannt, punkt)`` ohne Netz: aus der eingebauten Liste oder dem Zwischenspeicher."""
    schluessel = ort_schluessel(name)
    if not schluessel:
        return True, None
    for versuch in (schluessel, re.split(r"[-/ ]", schluessel)[0]):
        if versuch in ORTE:
            return True, ORTE[versuch]
    _, cache = _orte_cache(cache_datei)
    if schluessel in cache:
        return True, tuple(cache[schluessel]) if cache[schluessel] else None
    return False, None


def ort_finden(name: str, tools=None, cache_datei=None, online_erlaubt: bool = True):
    """Koordinaten eines Ortes: erst die eingebaute Liste, dann der Zwischenspeicher, dann das Netz.

    Gespeichert wird nur eine echte Antwort des Dienstes - auch "gibt es nicht".
    Ein Netzfehler wird nicht gespeichert, sonst bliebe der Ort für immer unbekannt.
    """
    bekannt, punkt = ort_gespeichert(name, cache_datei)
    if bekannt or not online_erlaubt or tools is None:
        return punkt
    try:
        treffer, fehler = tools.welt.ort_finden(name)
    except Exception as ausnahme:
        treffer, fehler = None, "Fehler: %s" % ausnahme
    if treffer and treffer.get("breite") is not None:
        wert = (treffer["breite"], treffer["laenge"])
    elif "finde ich nicht" in str(fehler or ""):
        wert = None
    else:
        return None  # Netz oder Dienst gestört: später noch einmal versuchen
    with _ORTE_SPERRE:
        datei, cache = _orte_cache(cache_datei)
        cache[ort_schluessel(name)] = list(wert) if wert else None
        try:
            datei.parent.mkdir(parents=True, exist_ok=True)
            datei.write_text(json.dumps(cache, ensure_ascii=False), encoding="utf-8")
        except OSError:
            pass
    return wert


def ort_im_hintergrund(name: str, tools, cache_datei=None) -> bool:
    """Sucht einen unbekannten Ort, ohne die Anzeige warten zu lassen.

    Die Zentrale zeigt ihn beim nächsten Nachladen. Pro Ort läuft höchstens eine Suche.
    """
    schluessel = ort_schluessel(name)
    with _ORTE_SPERRE:
        if not schluessel or schluessel in _ORTE_IN_ARBEIT:
            return False
        _ORTE_IN_ARBEIT.add(schluessel)

    def suchen():
        try:
            ort_finden(name, tools, cache_datei, online_erlaubt=True)
        finally:
            with _ORTE_SPERRE:
                _ORTE_IN_ARBEIT.discard(schluessel)

    threading.Thread(target=suchen, daemon=True, name="jarvis-ortssuche").start()
    return True


def orte_der_kunden(tools, maximal: int = 12) -> list:
    """Wo der Betrieb ist und wo seine Kunden und Interessenten sitzen."""
    orte, gesehen, neue_abfragen = [], set(), [0]

    def aufnehmen(name, art):
        schluessel = ort_schluessel(name)
        if not schluessel or schluessel in gesehen or len(orte) >= maximal:
            return
        gesehen.add(schluessel)
        bekannt, punkt = ort_gespeichert(name)
        if not bekannt:
            # Nie im Abruf der Zentrale warten: im Hintergrund suchen, beim nächsten Mal zeigen.
            if neue_abfragen[0] < 3 and ort_im_hintergrund(name, tools):
                neue_abfragen[0] += 1
            return
        if punkt is None:
            return
        orte.append({"name": name if not config.ANZEIGE_DISKRET else ("Ort" if art == "kunde" else name),
                     "lat": punkt[0], "lon": punkt[1], "art": art})

    aufnehmen(config.WETTER_ORT, "zuhause")
    try:
        for zeile in tools.memory._lesen("SELECT adresse FROM leads WHERE adresse<>'' ORDER BY id DESC LIMIT 40"):
            aufnehmen(ort_aus_adresse(zeile["adresse"]), "kunde")
        for zeile in tools.memory._lesen("SELECT adresse FROM kontakte WHERE adresse<>'' ORDER BY id DESC LIMIT 40"):
            aufnehmen(ort_aus_adresse(zeile["adresse"]), "kunde")
    except Exception:
        pass
    return orte


# -- Gehirn --------------------------------------------------------------------------

STOPPWOERTER = set("""
dass nicht eine einen einem einer eines auch noch aber oder sich sind wird werden haben
hatte mehr mein meine meinen wenn dann damit dieser diese dieses über unter nach bei
für mit von vom zum zur aus auf der die das den dem des und ist war wie was wer wann
""".split())


def _wortmenge(text: str) -> set:
    woerter = re.findall(r"[a-zäöüß]{5,}", (text or "").lower())
    return {w for w in woerter if w not in STOPPWOERTER}


def _kurz(text: str, n: int = 70) -> str:
    text = re.sub(r"\s+", " ", str(text or "")).strip()
    return text if len(text) <= n else text[:n - 1].rstrip() + "…"


def gehirn_daten(tools, agent=None) -> dict:
    """Alles, woraus die Seite das Gehirn baut: Knoten, Verbindungen, Zähler, Zustand."""
    m = tools.memory
    diskret = bool(config.ANZEIGE_DISKRET)
    knoten = []

    def lesen(sql, art, bauen):
        try:
            for zeile in m._lesen(sql):
                text, zeit = bauen(zeile)
                knoten.append({"id": "%s%d" % (art[0], zeile["id"]), "art": art,
                               "text": "" if diskret else _kurz(text), "zeit": zeit or "",
                               "_woerter": _wortmenge(text)})
        except Exception:
            pass

    lesen("SELECT id,text,angelegt FROM notizen ORDER BY id DESC LIMIT 90", "notiz",
          lambda z: (z["text"], z["angelegt"]))
    lesen("SELECT id,name,firma,notiz,angelegt FROM kontakte ORDER BY id DESC LIMIT 50", "kontakt",
          lambda z: ("%s %s %s" % (z["name"], z["firma"], z["notiz"]), z["angelegt"]))
    lesen("SELECT id,firma,ansprechpartner,notiz,naechster_schritt,angelegt FROM leads ORDER BY id DESC LIMIT 50",
          "lead", lambda z: ("%s %s %s %s" % (z["firma"], z["ansprechpartner"], z["notiz"], z["naechster_schritt"]),
                             z["angelegt"]))
    lesen("SELECT id,text,angelegt FROM offene_punkte WHERE erledigt=0 ORDER BY id DESC LIMIT 40", "aufgabe",
          lambda z: (z["text"], z["angelegt"]))
    lesen("SELECT id,text,zeit FROM verlauf WHERE rolle='user' ORDER BY id DESC LIMIT 40", "gespraech",
          lambda z: (z["text"], z["zeit"]))
    lesen("SELECT id,titel,ergebnis,angelegt FROM autopilot WHERE status IN ('fertig','fehler') "
          "ORDER BY id DESC LIMIT 25", "autopilot", lambda z: ("%s %s" % (z["titel"], z["ergebnis"]), z["angelegt"]))

    # Verbindungen: gemeinsame Wörter, und Interessent und Kontakt mit demselben Firmennamen.
    nach_wort = {}
    for i, k in enumerate(knoten):
        for w in k["_woerter"]:
            nach_wort.setdefault(w, []).append(i)
    kanten, vorhanden = [], set()
    for wort, liste in sorted(nach_wort.items(), key=lambda p: len(p[1])):
        if len(liste) < 2 or len(liste) > 8:
            continue  # ein Wort, das überall steht, verbindet nichts
        for a in range(len(liste) - 1):
            paar = (liste[a], liste[a + 1])
            if paar not in vorhanden:
                vorhanden.add(paar)
                kanten.append(list(paar))
            if len(kanten) >= 260:
                break
        if len(kanten) >= 260:
            break
    for k in knoten:
        del k["_woerter"]

    try:
        stat = m.statistik()
    except Exception:
        stat = {}
    # Gezählt wird mit denselben Bedingungen wie die Knoten - sonst passt die Zahl nicht zum Bild.
    zaehler = {"notiz": stat.get("notizen", 0), "kontakt": stat.get("kontakte", 0)}
    for art, sql in (("aufgabe", "SELECT count(*) AS n FROM offene_punkte WHERE erledigt=0"),
                     ("gespraech", "SELECT count(*) AS n FROM verlauf WHERE rolle='user'"),
                     ("lead", "SELECT count(*) AS n FROM leads"),
                     ("autopilot", "SELECT count(*) AS n FROM autopilot WHERE status IN ('fertig','fehler')")):
        try:
            zaehler[art] = m._lesen(sql)[0]["n"]
        except Exception:
            zaehler[art] = 0
    return {"ok": True, "knoten": knoten, "kanten": kanten, "zaehler": zaehler,
            "diskret": diskret, "status": status_daten(tools, agent)}


def status_daten(tools, agent=None) -> dict:
    """Zustand von Jarvis und seine letzten Handlungen - billig genug für jede Sekunde."""
    status = dict(getattr(agent, "status", None) or {"zustand": "bereit", "seit": time.time()})
    status["jetzt"] = time.time()
    try:
        aktionen = tools.memory._lesen("SELECT id,werkzeug,status,zeit FROM aktionen ORDER BY id DESC LIMIT 8")
    except Exception:
        aktionen = []
    try:
        # Welche Ansicht die Zentrale zeigt und welche Kanäle sich geändert haben.
        anzeige = tools.anzeige.kurz() if getattr(tools, "anzeige", None) else {}
    except Exception:
        anzeige = {}
    return {"zustand": status.get("zustand", "bereit"), "satz": status.get("satz", ""),
            "seit": status.get("seit", 0), "jetzt": status["jetzt"],
            "aktionen": [{"id": a["id"], "werkzeug": a["werkzeug"], "status": a["status"], "zeit": a["zeit"]}
                         for a in aktionen],
            "anzeige": anzeige}


# -- Zentrale --------------------------------------------------------------------------

def zentrale_daten(tools, agent=None) -> dict:
    """Der Stand des Betriebs für die große Anzeige."""
    d = tools.dashboard.daten_sammeln(False)
    diskret = bool(config.ANZEIGE_DISKRET)
    bedarf = d.get("bedarf") or {}
    pipeline = d.get("pipeline") or {}
    nachfassen = (d.get("nachfassen") or {}).get("eintraege") or []
    erinnerungen = (d.get("erinnerungen") or {}).get("eintraege") or []
    try:
        ap = tools.autopilot.zustand()
    except Exception:
        ap = {"an": False, "postfach": [], "warteschlange": [], "gesperrt": "", "arbeitet_an": ""}
    try:
        protokoll = tools.memory._lesen("SELECT id,werkzeug,status,zeit FROM aktionen ORDER BY id DESC LIMIT 10")
    except Exception:
        protokoll = []
    briefing = []
    monat = d.get("monat") or {}
    if monat.get("ok"):
        briefing.append("Kasse im Monat: %s Euro Ergebnis" % _euro(monat.get("ergebnis")))
    if nachfassen:
        briefing.append("%d Interessenten zum Nachfassen" % len(nachfassen))
    if erinnerungen:
        briefing.append("%d Termine in den nächsten Tagen" % len(erinnerungen))
    if ap.get("postfach"):
        briefing.append("%d Ergebnisse im Postfach des Autopiloten" % len(ap["postfach"]))
    if not briefing:
        briefing.append("Heute liegt nichts Dringendes an")
    return {
        "ok": True, "datum": d.get("datum"), "wochentag": d.get("wochentag"),
        "nutzer": "" if diskret else d.get("nutzer"), "firma": "" if diskret else d.get("firma"),
        "ort": config.WETTER_ORT, "diskret": diskret,
        "monat": {k: monat.get(k) for k in ("von", "bis", "einnahmen", "ausgaben", "ergebnis", "zahllast")},
        "belegquote": (d.get("belegquote") or {}).get("quote"),
        "verlauf": {k: (d.get("verlauf") or {}).get(k) for k in ("tage", "einnahmen", "ausgaben")},
        "monate": {k: (d.get("monate") or {}).get(k) for k in ("monate", "ergebnis", "einnahmen")},
        "pipeline": {"offen": pipeline.get("offen", 0), "offen_wert": pipeline.get("offener_wert_monat", 0),
                     "gewichtet": pipeline.get("gewichteter_wert_monat", 0),
                     "gesichert": pipeline.get("laufender_umsatz_monat", 0),
                     "stufen": pipeline.get("stufen", {})},
        "bedarf": {"berechenbar": bool(bedarf.get("berechenbar")),
                   "noetig": bedarf.get("noetiger_umsatz"), "gewinn": bedarf.get("gewinn"),
                   "text": bedarf.get("text", "")},
        "gehirne": d.get("gehirne") or {},
        "limit": config.MONATSLIMIT_EURO,
        "nachfassen": [{"firma": "Kunde" if diskret else e["firma"], "tage": e.get("seit_tagen", 0),
                        "wert": e.get("wert_monat", 0)} for e in nachfassen[:6]],
        "erinnerungen": [{"was": "Termin" if diskret else e["was"], "in_tagen": e.get("in_tagen", 0)}
                         for e in erinnerungen[:5]],
        "autopilot": {"an": ap.get("an"), "arbeitet_an": "" if diskret else ap.get("arbeitet_an"),
                      "gesperrt": ap.get("gesperrt"), "postfach": len(ap.get("postfach") or []),
                      "wartet": len(ap.get("warteschlange") or []),
                      "letzte": [] if diskret else [{"titel": e["titel"], "rolle": e["rolle"], "status": e["status"],
                                                     "zeit": e.get("beendet") or e.get("angelegt")}
                                                    for e in (ap.get("postfach") or [])[:5]]},
        "protokoll": [{"werkzeug": p["werkzeug"], "status": p["status"], "zeit": p["zeit"]} for p in protokoll],
        "statistik": d.get("statistik") or {},
        "briefing": briefing, "orte": orte_der_kunden(tools),
        "status": status_daten(tools, agent),
    }


def _euro(wert) -> str:
    try:
        return ("%.2f" % float(wert)).replace(".", ",")
    except (TypeError, ValueError):
        return "0,00"


def _echte_zahl(wert) -> bool:
    """Nur eine echte, endliche Zahl - kein None, kein Wahrheitswert, kein Text."""
    return (isinstance(wert, (int, float)) and not isinstance(wert, bool)
            and wert == wert and wert not in (float("inf"), float("-inf")))


def _prozent_text(anteil: float) -> str:
    return "%d %%" % round(anteil * 100)


def kennzahlen_kacheln(tools) -> list:
    """Die Kacheln der Kennzahlen-Ansicht: Kasse, Bedarf, Pipeline, Belegquote.

    Eine Kachel kommt nur dazu, wenn ihr Wert eine echte Zahl ist - fehlt eine
    Rechnung (keine Buchungen, keine Fixkosten), fehlt die Kachel, statt eine
    Null zu zeigen. Gelesen wird wie bei der Zentrale, nur ohne Orte und ohne
    Netz. ``anteil`` (0..1, optional) füllt den Ring, wenn die Kachel ein Ziel hat.
    """
    try:
        d = tools.dashboard.daten_sammeln(False)
    except Exception as fehler:
        print("[anzeige] Kennzahlen nicht lesbar: %s" % fehler)
        return []
    monat = d.get("monat") or {}
    # Ohne eine einzige Buchung im Monat wäre jede Kassenzahl eine bloße Null.
    if not monat.get("ok", True) or not monat.get("anzahl"):
        monat = {}
    bedarf = d.get("bedarf") or {}
    berechenbar = bool(bedarf.get("berechenbar"))
    pipeline = d.get("pipeline") or {}
    # Ebenso ohne einen einzigen Interessenten keine Pipeline-Kacheln.
    stufen = pipeline.get("stufen") or {}
    if not pipeline.get("ok", True) or not sum(
            (s.get("anzahl") or 0) if isinstance(s, dict) else 0 for s in stufen.values()):
        pipeline = {}
    quote = (d.get("belegquote") or {}).get("quote")
    kacheln = []

    def kachel(name, wert, einheit="€", ziel=None, text="", farbe="neutral", anteil=None):
        if not _echte_zahl(wert):
            return
        eintrag = {"name": name, "wert": round(float(wert), 2), "einheit": einheit,
                   "ziel": round(float(ziel), 2) if _echte_zahl(ziel) and ziel else None,
                   "text": text, "farbe": farbe}
        if _echte_zahl(anteil):
            eintrag["anteil"] = round(max(0.0, float(anteil)), 4)
        kacheln.append(eintrag)

    ergebnis, zahllast = monat.get("ergebnis"), monat.get("zahllast")
    gewinn = bedarf.get("gewinn") if berechenbar else None
    if _echte_zahl(ergebnis):
        if _echte_zahl(gewinn) and gewinn > 0:
            # Wie der Ring der Zentrale: Gewinn nach Umsatzsteuer gegen den nötigen Gewinn.
            netto = ergebnis - (zahllast if _echte_zahl(zahllast) else 0.0)
            anteil = netto / gewinn
            kachel("Ergebnis Monat", ergebnis, "€", gewinn,
                   "%s vom Bedarf" % _prozent_text(anteil),
                   "gut" if ergebnis >= 0 else "schlecht", anteil)
        else:
            kachel("Ergebnis Monat", ergebnis, "€", None, "Einnahmen minus Ausgaben",
                   "gut" if ergebnis >= 0 else "schlecht")
    kachel("Einnahmen Monat", monat.get("einnahmen"), "€", None, "brutto")
    kachel("Ausgaben Monat", monat.get("ausgaben"), "€", None, "brutto")
    kachel("Zahllast", zahllast, "€", None, "Umsatzsteuer minus Vorsteuer")
    if _echte_zahl(quote):
        kachel("Belegquote", quote, "%", 100, "der Ausgaben belegt",
               "gut" if quote >= 90 else ("schlecht" if quote < 50 else "neutral"), quote / 100.0)
    gewichtet = pipeline.get("gewichteter_wert_monat")
    offen = pipeline.get("offener_wert_monat")
    kachel("Pipeline gewichtet", gewichtet, "€", None,
           ("von %s € offen" % _euro(offen).replace(",00", "")) if _echte_zahl(offen) and offen else
           "nach Wahrscheinlichkeit")
    gesichert = pipeline.get("laufender_umsatz_monat")
    noetig = bedarf.get("noetiger_umsatz") if berechenbar else None
    if _echte_zahl(gesichert) and _echte_zahl(noetig) and noetig > 0:
        kachel("Gesichert je Monat", gesichert, "€", noetig,
               "%s vom nötigen Umsatz" % _prozent_text(gesichert / noetig),
               "gut" if gesichert >= noetig else "schlecht", gesichert / noetig)
    else:
        kachel("Gesichert je Monat", gesichert, "€", None, "aus gewonnenen Aufträgen")
    if _echte_zahl(noetig):
        kachel("Nötiger Umsatz", noetig, "€", None, "je Monat, damit das Private gedeckt ist")
    return kacheln[:8]


# -- Gemeinsames für beide Seiten ---------------------------------------------------------

BASIS_STIL = r"""
:root{--grund:#070403;--tief:#0d0705;--linie:rgba(255,120,48,.22);--orange:#ff6a1f;--glut:#ff9a52;
 --hell:#ffd9b8;--text:#f1e6dc;--leise:#9a8678;--gruen:#7fd6a0;--rot:#ff5a4d;
 --mono:ui-monospace,"SF Mono",Menlo,Consolas,monospace;--sans:-apple-system,BlinkMacSystemFont,"Helvetica Neue",Arial,sans-serif}
*{box-sizing:border-box;margin:0;padding:0}
html,body{height:100%;background:var(--grund);color:var(--text);font-family:var(--sans);overflow:hidden;
 -webkit-font-smoothing:antialiased;cursor:default}
"""

FEHLERFANG = r"""
window.addEventListener('error',function(e){document.documentElement.setAttribute('data-fehler',String(e.message||e).slice(0,200))});
"""

# -- Seite: Gehirn --------------------------------------------------------------------------

SEITE_GEHIRN = r"""<!DOCTYPE html>
<html lang="de"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<link rel="icon" href="/symbol.svg" type="image/svg+xml">
<title>Jarvis – Zweites Gehirn</title>
<style>
""" + BASIS_STIL + r"""
canvas{position:fixed;inset:0;width:100%;height:100%;display:block}
.kopf{position:fixed;left:28px;top:24px;z-index:2;pointer-events:none}
.kopf h1{font:600 13px var(--mono);letter-spacing:.42em;color:var(--glut);text-transform:uppercase}
.zustand{margin-top:10px;display:flex;align-items:center;gap:10px;font:500 12px var(--mono);letter-spacing:.28em;
 color:var(--hell);text-transform:uppercase}
.zustand i{width:9px;height:9px;border-radius:50%;background:var(--orange);box-shadow:0 0 14px var(--orange);
 animation:atmen 2.4s ease-in-out infinite}
.zustand[data-z="hoert"] i{animation-duration:.9s;background:var(--gruen);box-shadow:0 0 14px var(--gruen)}
.zustand[data-z="denkt"] i{animation-duration:.5s;background:#fff;box-shadow:0 0 18px #fff}
.zustand[data-z="spricht"] i{animation-duration:.7s}
@keyframes atmen{50%{transform:scale(1.7);opacity:.45}}
.zaehler{position:fixed;left:28px;bottom:26px;z-index:2;display:flex;gap:26px;flex-wrap:wrap;pointer-events:none}
.zaehler div{font:500 10px var(--mono);letter-spacing:.24em;color:var(--leise);text-transform:uppercase}
.zaehler b{display:block;font:300 30px var(--sans);letter-spacing:0;color:var(--hell);margin-bottom:2px;font-variant-numeric:tabular-nums}
.letzte{position:fixed;right:28px;bottom:26px;z-index:2;text-align:right;font:500 11px var(--mono);letter-spacing:.16em;
 color:var(--leise);text-transform:uppercase;pointer-events:none;max-width:46vw}
.letzte b{color:var(--glut);font-weight:600}
.titel{position:fixed;right:28px;top:24px;z-index:2;font:500 11px var(--mono);letter-spacing:.3em;color:var(--leise);
 text-transform:uppercase;pointer-events:none}
.etikett{position:fixed;z-index:3;pointer-events:none;font:500 11px var(--mono);letter-spacing:.08em;color:var(--hell);
 background:rgba(13,7,5,.78);border:1px solid var(--linie);padding:4px 8px;border-radius:4px;max-width:260px;display:none}
@media (max-width:700px){.zaehler b{font-size:22px}.zaehler{gap:14px;left:16px;bottom:16px}.kopf{left:16px;top:16px}.titel{display:none}}
/* Eingebettet in die Gesprächsseite: nur das Gehirn, ohne Hintergrund und Beschriftung. */
html.eingebettet,html.eingebettet body{background:transparent}
html.eingebettet .kopf,html.eingebettet .zaehler,html.eingebettet .letzte,html.eingebettet .titel{display:none}
@media (prefers-reduced-motion:reduce){.zustand i{animation:none}}
</style></head><body>
<canvas id="c" aria-label="Das Gedächtnis von Jarvis als leuchtendes Gehirn"></canvas>
<div class="kopf"><h1>Zweites Gehirn</h1><div class="zustand" id="zustand" data-z="bereit"><i></i><span id="zustandtext">bereit</span></div></div>
<div class="titel" id="titel"></div>
<div class="zaehler" id="zaehler"></div>
<div class="letzte" id="letzte"></div>
<div class="etikett" id="etikett"></div>
<script>
""" + FEHLERFANG + r"""
const SCHLUESSEL="{{SCHLUESSEL}}";
const ANHANG=SCHLUESSEL?"?schluessel="+encodeURIComponent(SCHLUESSEL):"";
const EINGEBETTET=new URLSearchParams(location.search).get("eingebettet")==="1";
if(EINGEBETTET)document.documentElement.classList.add("eingebettet");
// Die Gesprächsseite sagt, ob sie gerade hört oder spricht - das weiß der Server nicht.
let LOKAL=null,LOKAL_ZEIT=0;
addEventListener("message",e=>{if(e.origin!==location.origin)return;const z=e.data&&e.data.zustand;
 if(typeof z==="string"&&/^(bereit|hoert|denkt|spricht)$/.test(z)){LOKAL=z;LOKAL_ZEIT=Date.now()}});
const $=s=>document.querySelector(s);
const ARTEN={notiz:{name:"Notizen",x:-0.45,y:0.3,z:0.05},kontakt:{name:"Kontakte",x:0.62,y:-0.1,z:0.25},
 lead:{name:"Interessenten",x:0.45,y:0.35,z:-0.3},aufgabe:{name:"Aufgaben",x:0.0,y:0.5,z:0.1},
 gespraech:{name:"Gespräche",x:-0.1,y:0.25,z:0.72},autopilot:{name:"Autopilot",x:0.0,y:0.2,z:-0.72}};
const ZUSTAND={bereit:"bereit",hoert:"hört zu",denkt:"denkt nach",spricht:"spricht"};
const REDUZIERT=matchMedia("(prefers-reduced-motion: reduce)").matches;
const cv=$("#c"),g=cv.getContext("2d");let W=0,H=0,DPR=1;
function groesse(){DPR=Math.min(2,devicePixelRatio||1);W=innerWidth;H=innerHeight;cv.width=W*DPR;cv.height=H*DPR;g.setTransform(DPR,0,0,DPR,0,0)}
addEventListener("resize",groesse);groesse();
function zufall(a){return function(){a|=0;a=a+0x6D2B79F5|0;let t=Math.imul(a^a>>>15,1|a);t=t+Math.imul(t^t>>>7,61|t)^t;return((t^t>>>14)>>>0)/4294967296}}
const R=zufall(7);
// --- Das Gehirn: zwei Hälften aus Punkten, mit Furchen, und feinen Fasern dazwischen
const P=[];
function hirnpunkt(seite){
 // Eine Hälfte von oben gesehen wie ein "D": außen rund, zur Mitte hin flach, vorn und hinten
 // stumpf (Stirn- und Hinterhauptlappen), hinten etwas breiter, mit Furchen und Schläfenlappen.
 let th,ph;
 do{th=Math.acos(2*R()-1);ph=R()*Math.PI*2}
 while(Math.sin(th)*Math.cos(ph)*seite<0&&R()<0.7);          // die flache Innenseite nicht überfüllen
 const stumpf=v=>Math.sign(v)*Math.pow(Math.abs(v),0.8);
 const ex=stumpf(Math.sin(th)*Math.cos(ph)),ey=stumpf(Math.cos(th)),ez=stumpf(Math.sin(th)*Math.sin(ph));
 const furche=Math.sin(9*ex+3*ey+1.3*ez)*Math.sin(6*ey+4*ez+2*ex)*Math.sin(5*ez+2*ex-3*ey);
 const r=1+0.085*furche,tiefe=R()<0.5?0.8+0.2*R():1;
 const breite=0.92-0.12*ez;                                  // hinten (z<0) breiter, vorn schmaler
 const lx=ex*seite<0?ex*0.26:ex;                             // flache Innenseite am Spalt
 let px=seite*0.17+lx*0.5*breite*r*tiefe,py=ey*0.5*r*tiefe,pz=ez*0.84*r*tiefe;
 if(py<-0.1)py=-0.1+(py+0.1)*0.55;                           // flache Unterseite
 const schlaefe=Math.exp(-(Math.pow(Math.abs(px)-0.58,2)*16+Math.pow(py+0.18,2)*20+Math.pow(pz-0.12,2)*7));
 py-=0.14*schlaefe;px+=0.05*seite*schlaefe;
 return [px,py,pz];
}
for(let i=0,n=EINGEBETTET?3200:5200;i<n;i++)P.push(hirnpunkt(i%2?1:-1));
const KANTEN=[];
(function(){const zelle=0.085,tab=new Map();
 const key=(x,y,z)=>Math.floor(x/zelle)+","+Math.floor(y/zelle)+","+Math.floor(z/zelle);
 P.forEach((p,i)=>{const k=key(p[0],p[1],p[2]);(tab.get(k)||tab.set(k,[]).get(k)).push(i)});
 P.forEach((p,i)=>{let best=[];const cx=Math.floor(p[0]/zelle),cy=Math.floor(p[1]/zelle),cz=Math.floor(p[2]/zelle);
  for(let dx=-1;dx<=1;dx++)for(let dy=-1;dy<=1;dy++)for(let dz=-1;dz<=1;dz++){
   const l=tab.get((cx+dx)+","+(cy+dy)+","+(cz+dz));if(!l)continue;
   for(const j of l){if(j<=i)continue;const q=P[j];const d=(p[0]-q[0])**2+(p[1]-q[1])**2+(p[2]-q[2])**2;
    if(d<0.0072)best.push([d,j])}}
  best.sort((a,b)=>a[0]-b[0]);for(let n=0;n<Math.min(3,best.length);n++)KANTEN.push([i,best[n][1]])});
})();
// --- Wissen: Knoten sitzen in ihrer Region des Gehirns
let DATEN={knoten:[],kanten:[],zaehler:{},status:{zustand:"bereit",aktionen:[]}};let KN=[];
function nahe(ziel){let b=0,bd=9;for(let i=0;i<P.length;i++){const p=P[i];const d=(p[0]-ziel.x)**2+(p[1]-ziel.y)**2+(p[2]-ziel.z)**2;if(d<bd){bd=d;b=i}}return b}
function aufbauen(d){
 DATEN=d;const jeArt={};KN=[];const belegt=new Set();
 d.knoten.forEach((k,i)=>{const reg=ARTEN[k.art]||{x:0,y:0.2,z:0};const r=zufall(i*977+k.art.length*31);
  for(let t=0;t<12;t++){const ziel={x:reg.x+(r()-.5)*0.55,y:reg.y+(r()-.5)*0.4,z:reg.z+(r()-.5)*0.6};const n=nahe(ziel);
   if(!belegt.has(n)||t==11){belegt.add(n);KN.push({k,p:n,art:k.art,alter:i,flash:0});break}}});
 const wege=[];(d.kanten||[]).forEach(e=>{if(KN[e[0]]&&KN[e[1]])wege.push(e)});KN.wege=wege;
 const z=d.zaehler||{};$("#zaehler").replaceChildren(...Object.keys(ARTEN).map(a=>{const div=document.createElement("div");
  const b=document.createElement("b");b.textContent=z[a]||0;div.append(b,ARTEN[a].name);return div}));
}
// --- Puls und Aufblitzen
const PULSE=[];let letzteAktion=0,ripples=[];
function spawn(){if(!KN.length)return;const w=KN.wege&&KN.wege.length?KN.wege[Math.floor(Math.random()*KN.wege.length)]:null;
 if(w)PULSE.push({a:KN[w[0]],b:KN[w[1]],t:0,v:0.6+Math.random()*0.8})}
function aktion(name){const m=name.toLowerCase();let art="autopilot";
 if(/notiz|gedaechtnis/.test(m))art="notiz";else if(/kontakt/.test(m))art="kontakt";else if(/lead|angebot|pipeline|nachfass/.test(m))art="lead";
 else if(/punkt|erinnerung|termin/.test(m))art="aufgabe";else if(/mail|anruf|sms|nachricht|wetter|recherche/.test(m))art="gespraech";
 const reg=ARTEN[art];ripples.push({x:reg.x,y:reg.y,z:reg.z,t:0});KN.forEach(n=>{if(n.art===art)n.flash=1})}
// --- Zeichnen
let ay=0,ax=0.0,zielAy=0,ziehen=false,mx=0;const t0=performance.now();let proj=new Float32Array(P.length*4);
addEventListener("pointerdown",e=>{ziehen=true;mx=e.clientX});addEventListener("pointerup",()=>ziehen=false);
addEventListener("pointermove",e=>{if(ziehen){zielAy+=(e.clientX-mx)*0.005;mx=e.clientX}});
function drehen(p,ay,ax){const ca=Math.cos(ay),sa=Math.sin(ay),cx=Math.cos(ax),sx=Math.sin(ax);
 let x=p[0]*ca+p[2]*sa,z=-p[0]*sa+p[2]*ca,y=p[1];const y2=y*cx-z*sx,z2=y*sx+z*cx;return[x,y2,z2]}
function abbilden(x,y,z,s){const f=1/(1-z*0.32);return[W*0.5+x*s*f,H*0.5+y*s*f,z,f]}
const glutBild=(function(){const c=document.createElement("canvas");c.width=c.height=64;const q=c.getContext("2d");
 const gr=q.createRadialGradient(32,32,0,32,32,32);gr.addColorStop(0,"rgba(255,245,230,1)");gr.addColorStop(.18,"rgba(255,170,90,.85)");
 gr.addColorStop(.5,"rgba(255,100,30,.22)");gr.addColorStop(1,"rgba(255,80,20,0)");q.fillStyle=gr;q.fillRect(0,0,64,64);return c})();
function rahmen(jetzt){
 const server=(DATEN.status&&DATEN.status.zustand)||"bereit";
 const sek=(jetzt-t0)/1000,st=(LOKAL&&LOKAL!=="bereit"&&Date.now()-LOKAL_ZEIT<120000)?LOKAL:server;
 const tempo={bereit:0.5,hoert:1.4,denkt:5,spricht:3}[st]||0.5;
 if(!REDUZIERT){zielAy+=0.0002*Math.sin(sek*0.05);ay+=(Math.sin(sek*0.13)*0.22+zielAy-ay)*0.04;ax=0.74+Math.sin(sek*0.09)*0.06}
 else{ay=zielAy;ax=0.74}
 g.globalCompositeOperation="source-over";if(EINGEBETTET)g.clearRect(0,0,W,H);else{g.fillStyle="#070403";g.fillRect(0,0,W,H)}
 const mitte=g.createRadialGradient(W/2,H/2,0,W/2,H/2,Math.min(W,H)*0.7);mitte.addColorStop(0,"rgba(120,40,10,.30)");mitte.addColorStop(1,"rgba(7,4,3,0)");
 g.fillStyle=mitte;g.fillRect(0,0,W,H);
 const s=Math.min(W*0.40,H*0.5);g.globalCompositeOperation="lighter";
 const pr=proj;for(let i=0;i<P.length;i++){const r=drehen(P[i],ay,ax),a=abbilden(r[0],r[1],r[2],s);pr[i*4]=a[0];pr[i*4+1]=a[1];pr[i*4+2]=r[2];pr[i*4+3]=a[3]}
 g.lineWidth=0.7;g.strokeStyle="rgba(255,105,35,.13)";g.beginPath();
 for(const e of KANTEN){g.moveTo(pr[e[0]*4],pr[e[0]*4+1]);g.lineTo(pr[e[1]*4],pr[e[1]*4+1])}g.stroke();
 for(let b=0;b<4;b++){const lo=-1+b*.5,hi=lo+.5;g.fillStyle="rgba(255,"+(95+b*45)+","+(35+b*45)+","+(0.20+b*0.2)+")";
  g.beginPath();for(let i=0;i<P.length;i++){const z=pr[i*4+2];if(z>=lo&&z<hi){const f=pr[i*4+3];g.rect(pr[i*4]-0.9*f,pr[i*4+1]-0.9*f,1.8*f,1.8*f)}}g.fill()}
 // Verbindungen des Wissens
 g.lineWidth=1;g.strokeStyle="rgba(255,200,150,.22)";g.beginPath();
 (KN.wege||[]).forEach(e=>{const a=KN[e[0]].p,b=KN[e[1]].p;
  if((P[a][0]-P[b][0])**2+(P[a][1]-P[b][1])**2+(P[a][2]-P[b][2])**2>0.22)return;   // weit entfernte Verbindungen zeigt nur der Puls
  g.moveTo(pr[a*4],pr[a*4+1]);g.lineTo(pr[b*4],pr[b*4+1])});g.stroke();
 // Pulse laufen entlang der Verbindungen
 if(!REDUZIERT&&Math.random()<tempo*0.016)spawn();
 for(let i=PULSE.length-1;i>=0;i--){const p=PULSE[i];p.t+=p.v*0.016;if(p.t>=1){PULSE.splice(i,1);p.b.flash=Math.max(p.b.flash,.7);continue}
  const ax_=pr[p.a.p*4],ay_=pr[p.a.p*4+1],bx=pr[p.b.p*4],by=pr[p.b.p*4+1];const x=ax_+(bx-ax_)*p.t,y=ay_+(by-ay_)*p.t;
  g.drawImage(glutBild,x-14,y-14,28,28)}
 // Knoten
 for(const n of KN){n.flash*=0.965;const x=pr[n.p*4],y=pr[n.p*4+1],f=pr[n.p*4+3],neu=Math.max(0,1-n.alter/30);
  const gr=(9+neu*6+n.flash*14)*f;g.globalAlpha=Math.min(1,0.5+neu*0.4+n.flash);g.drawImage(glutBild,x-gr,y-gr,gr*2,gr*2);g.globalAlpha=1}
 // Ringe bei Aktionen
 for(let i=ripples.length-1;i>=0;i--){const r=ripples[i];r.t+=0.012;if(r.t>1){ripples.splice(i,1);continue}
  const q=drehen([r.x,r.y,r.z],ay,ax),a=abbilden(q[0],q[1],q[2],s);g.strokeStyle="rgba(255,170,100,"+(1-r.t)*0.7+")";g.lineWidth=1.5;
  g.beginPath();g.arc(a[0],a[1],20+r.t*130*a[3],0,7);g.stroke()}
 requestAnimationFrame(rahmen)}
// --- Daten
function alter(sek){return sek<90?"vor "+Math.round(sek)+" s":sek<5400?"vor "+Math.round(sek/60)+" min":"vor "+Math.round(sek/3600)+" h"}
function zeigStatus(s){
 const z=s.zustand||"bereit";$("#zustand").dataset.z=z;$("#zustandtext").textContent=ZUSTAND[z]||z;
 const a=(s.aktionen||[])[0];if(a){const sek=Math.max(0,Date.now()/1000-new Date(a.zeit.replace(" ","T")).getTime()/1000);
  const l=$("#letzte");l.replaceChildren();const b=document.createElement("b");b.textContent=a.werkzeug.replace(/_/g," ");l.append("Zuletzt ",b," · "+alter(sek));
  if(a.id>letzteAktion){if(letzteAktion)aktion(a.werkzeug);letzteAktion=a.id}}}
async function holen(pfad){const r=await fetch(pfad+ANHANG);return r.json()}
async function gesamt(){try{const d=await holen("/api/gehirn");if(d.ok){aufbauen(d);zeigStatus(d.status);
 $("#titel").textContent=d.knoten.length+" Erinnerungen im Blick"}}catch(e){}}
async function status(){try{const s=await holen("/api/status");zeigStatus(s)}catch(e){}}
gesamt();setInterval(gesamt,30000);setInterval(status,1500);requestAnimationFrame(rahmen);
</script></body></html>
"""

# -- Seite: Zentrale --------------------------------------------------------------------------

SEITE_ZENTRALE = r"""<!DOCTYPE html>
<html lang="de"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<link rel="icon" href="/symbol.svg" type="image/svg+xml">
<title>Jarvis – Zentrale</title>
<style>
""" + BASIS_STIL + r"""
:root{--gelb:#ffd36b;--kuehl:#9fe7ff}
body{display:grid;grid-template-rows:auto minmax(0,1fr) auto;gap:10px;padding:12px 14px;
 background:radial-gradient(ellipse 90% 70% at 50% 40%,#1a0b05 0%,var(--grund) 70%)}
.kopf{display:flex;align-items:center;gap:18px;border-bottom:1px solid var(--linie);padding-bottom:8px}
.kopf h1{font:600 13px var(--mono);letter-spacing:.4em;color:var(--glut);text-transform:uppercase}
.kopf .platz{flex:1}.kopf .uhr{font:300 26px var(--sans);letter-spacing:.06em;color:var(--hell);font-variant-numeric:tabular-nums}
.kopf .datum{font:500 11px var(--mono);letter-spacing:.2em;color:var(--leise);text-transform:uppercase}
.chip{display:inline-flex;align-items:center;gap:8px;font:500 11px var(--mono);letter-spacing:.22em;color:var(--hell);
 text-transform:uppercase;border:1px solid var(--linie);padding:4px 10px;border-radius:3px}
.chip i{width:8px;height:8px;border-radius:50%;background:var(--orange);box-shadow:0 0 10px var(--orange)}
.chip[data-z="denkt"] i{background:#fff;box-shadow:0 0 12px #fff}.chip[data-z="hoert"] i{background:var(--gruen);box-shadow:0 0 12px var(--gruen)}
.chip.aus i{background:var(--leise);box-shadow:none}
main{position:relative;display:grid;grid-template-columns:minmax(260px,24%) minmax(0,1fr) minmax(280px,27%);gap:12px;min-height:0;
 transition:grid-template-columns .5s ease,column-gap .5s ease}
main[data-modus]:not([data-modus="uebersicht"]){grid-template-columns:minmax(0px,0px) minmax(0,1fr) minmax(0px,0px);column-gap:0}
.spalte{display:flex;flex-direction:column;gap:12px;min-height:0;overflow:hidden;transition:opacity .4s ease}
main[data-modus]:not([data-modus="uebersicht"]) .spalte{opacity:0;pointer-events:none}
.feld{border:1px solid var(--linie);background:linear-gradient(180deg,rgba(255,106,31,.05),rgba(255,106,31,0) 60%);
 border-radius:4px;padding:10px 12px;min-height:0;position:relative}
.feld h2{font:600 10px var(--mono);letter-spacing:.3em;color:var(--leise);text-transform:uppercase;margin-bottom:8px;
 display:flex;justify-content:space-between}
.feld h2 span{color:var(--glut)}
.ringe{display:grid;grid-template-columns:1fr 1fr;gap:8px}
.ring{text-align:center}.ring svg{width:100%;max-width:120px;height:auto}
.ring b{display:block;font:300 22px var(--sans);color:var(--hell);margin-top:-4px;font-variant-numeric:tabular-nums}
.ring small{font:500 9px var(--mono);letter-spacing:.2em;color:var(--leise);text-transform:uppercase}
.balken{margin-bottom:8px}.balken div:first-child{display:flex;justify-content:space-between;font:500 10px var(--mono);
 letter-spacing:.14em;color:var(--leise);text-transform:uppercase;margin-bottom:3px}
.balken div:first-child b{color:var(--hell);font-weight:500}
.balken .s{height:5px;background:rgba(255,140,70,.12);border-radius:3px;overflow:hidden}
.balken .s i{display:block;height:100%;background:linear-gradient(90deg,var(--orange),var(--glut));border-radius:3px}
.mitte{display:flex;flex-direction:column;gap:12px;min-height:0;min-width:0}
/* Die Bühne: der Globus liegt immer darunter, die Ansichten (lage) blenden darüber ein und aus. */
.buehne{position:relative;flex:1;min-height:0;border:1px solid var(--linie);border-radius:4px;overflow:hidden;background:#05080d}
.globus{position:absolute;inset:0}
.globus canvas{position:absolute;inset:0;width:100%;height:100%;transition:opacity .4s ease}
.buehne:not([data-modus="uebersicht"]):not([data-modus="globus"]) .globus canvas{opacity:.25}
.briefing{position:absolute;left:14px;top:12px;z-index:2;max-width:46%;transition:opacity .4s ease}
.buehne:not([data-modus="uebersicht"]) .briefing{opacity:0;pointer-events:none}
.briefing h2{font:600 10px var(--mono);letter-spacing:.3em;color:var(--glut);text-transform:uppercase;margin-bottom:6px}
.briefing p{font:500 12px var(--sans);color:var(--text);margin-bottom:4px;text-shadow:0 1px 6px #000}
.briefing p::before{content:"▸ ";color:var(--orange)}
.ghud{position:absolute;inset:0;pointer-events:none;opacity:0;transition:opacity .4s ease;z-index:2}
.buehne[data-modus="globus"] .ghud{opacity:1}
.gtitel{position:absolute;left:34px;top:30px;max-width:44%;font:600 12px var(--mono);letter-spacing:.3em;color:var(--glut);
 text-transform:uppercase;background:rgba(5,10,16,.7);padding:6px 12px;border-left:2px solid var(--glut)}
.gtitel:empty,.gstand:empty{display:none}
.gstand{position:absolute;left:34px;bottom:30px;max-width:40%;font:500 10px/1.5 var(--mono);letter-spacing:.12em;color:var(--hell);
 background:rgba(5,10,16,.7);padding:5px 10px}
.gliste{position:absolute;right:32px;top:28px;width:min(340px,32%);list-style:none;display:flex;flex-direction:column;gap:3px}
.gliste li{padding:6px 10px;background:rgba(5,10,16,.72);border-left:2px solid var(--kuehl);font:500 12px/1.35 var(--sans);color:var(--text);
 display:-webkit-box;-webkit-line-clamp:3;-webkit-box-orient:vertical;overflow:hidden}
.gliste li .z,.gliste li .q{font:500 10px var(--mono);letter-spacing:.1em;color:var(--kuehl);text-transform:uppercase}
.gliste li .q{color:var(--leise)}
.debug{position:absolute;right:10px;bottom:6px;z-index:5;font:500 10px var(--mono);color:var(--kuehl);display:none}
.folgepunkte{position:absolute;left:50%;bottom:12px;transform:translateX(-50%);z-index:6;display:none;gap:8px;align-items:center;
 font:500 10px var(--mono);letter-spacing:.2em;color:var(--leise);text-transform:uppercase}
.folgepunkte.an{display:flex}
.folgepunkte i{width:7px;height:7px;border-radius:50%;background:rgba(255,140,70,.25);transition:background .3s,box-shadow .3s}
.folgepunkte i.dran{background:var(--orange);box-shadow:0 0 10px var(--orange)}
.folgepunkte i.fertig{background:rgba(255,140,70,.6)}
/* Ansichten (Ebenen) */
.lage{position:absolute;inset:0;z-index:3;display:flex;flex-direction:column;gap:.9em;padding:1.2em 1.5em;font-size:clamp(13px,.85vw,18px);
 opacity:0;visibility:hidden;pointer-events:none;transition:opacity .4s ease,visibility 0s linear .4s;min-height:0}
.lage.aktiv{opacity:1;visibility:visible;transition:opacity .4s ease,visibility 0s}
.lkopf{display:flex;align-items:center;justify-content:space-between;gap:1em;border-bottom:1px solid var(--linie);padding-bottom:.6em}
.lkopf h2{font:600 .9em var(--mono);letter-spacing:.32em;color:var(--glut);text-transform:uppercase}
.lchip{font:500 .75em var(--mono);letter-spacing:.2em;color:var(--hell);border:1px solid var(--linie);padding:.25em .8em;border-radius:3px;text-transform:uppercase}
.lchip:empty{display:none}
.lfuss{font:500 .72em/1.5 var(--mono);letter-spacing:.12em;color:var(--leise)}
.lleer{font:500 .95em var(--mono);letter-spacing:.1em;color:var(--leise);margin:auto;text-align:center}
.lnotiz{font:500 .78em/1.5 var(--mono);color:var(--leise);letter-spacing:.06em}
/* Märkte */
.mk-gitter{display:grid;grid-template-columns:repeat(auto-fill,minmax(200px,1fr));grid-auto-rows:minmax(9em,15em);gap:.9em;align-content:start;flex:1;min-height:0;overflow:hidden}
.mk-gitter .lleer{grid-column:1/-1;padding:3em 0}
.mk-karte{border:1px solid var(--linie);border-radius:4px;padding:.8em 1em;display:flex;flex-direction:column;gap:.25em;min-width:0;
 background:linear-gradient(180deg,rgba(255,106,31,.07),rgba(255,106,31,0) 70%)}
.mk-name{font:600 .75em var(--mono);letter-spacing:.2em;color:var(--leise);text-transform:uppercase;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.mk-wert{font:300 2.4em/1.1 var(--sans);color:var(--hell);font-variant-numeric:tabular-nums;white-space:nowrap}
.mk-wert small{font:500 .36em var(--mono);color:var(--leise);margin-left:.5em;letter-spacing:.1em}
.mk-chg{font:600 .95em var(--mono);font-variant-numeric:tabular-nums}
.mk-chg.gut{color:var(--gruen)}.mk-chg.schlecht{color:var(--rot)}.mk-chg.leise{color:var(--leise)}
.mk-spark{width:100%;flex:1;min-height:2.8em;display:block;margin-top:.2em}
.mk-zeit{font:500 .7em var(--mono);color:var(--leise);letter-spacing:.1em}
/* Kennzahlen */
.kz-gitter{display:grid;grid-template-columns:repeat(auto-fit,minmax(210px,1fr));gap:1em;flex:1;min-height:0;align-content:center;overflow:hidden}
.kz-kachel{--kf:var(--hell);border:1px solid var(--linie);border-radius:4px;padding:1em;display:flex;flex-direction:column;align-items:center;gap:.4em;
 text-align:center;background:linear-gradient(180deg,rgba(255,106,31,.06),rgba(255,106,31,0) 70%);min-width:0}
.kz-kachel[data-farbe="gut"]{--kf:var(--gruen)}.kz-kachel[data-farbe="schlecht"]{--kf:var(--rot)}
.kz-name{font:600 .75em var(--mono);letter-spacing:.22em;color:var(--leise);text-transform:uppercase}
.kz-ring{position:relative;width:min(100%,10em);aspect-ratio:1}
.kz-ring svg{width:100%;height:100%;display:block}
.kz-ring b{position:absolute;inset:0;display:grid;place-items:center;font:300 1.7em var(--sans);color:var(--hell);font-variant-numeric:tabular-nums}
.kz-zahl{font:300 3.2em/1.15 var(--sans);color:var(--kf);font-variant-numeric:tabular-nums;padding:.2em 0}
.kz-text{font:500 .72em/1.4 var(--mono);color:var(--leise);letter-spacing:.06em}
/* Anruf */
.an-wurzel{flex:1;min-height:0;display:grid;grid-template-columns:minmax(200px,36%) minmax(0,1fr);gap:1.6em}
.an-links{display:flex;flex-direction:column;align-items:center;justify-content:center;gap:.6em;text-align:center;min-width:0}
.an-sym{--af:var(--leise);position:relative;width:15em;height:15em;display:grid;place-items:center}
.an-sym[data-phase="waehlt"],.an-sym[data-phase="klingelt"]{--af:var(--glut)}
.an-sym[data-phase="verbunden"]{--af:var(--gruen)}
.an-sym[data-phase="beendet"],.an-sym[data-phase="fehler"]{--af:#8b8b8b}
.an-sym .kern{position:absolute;inset:22%;border-radius:50%;border:1.5px solid var(--af);background:rgba(255,255,255,.03);
 box-shadow:0 0 1.4em -.2em var(--af)}
.an-sym[data-phase="beendet"] .kern,.an-sym[data-phase="fehler"] .kern{box-shadow:none}
.an-sym svg{position:relative;width:24%;height:24%;fill:var(--af)}
.an-sym i{position:absolute;inset:22%;border-radius:50%;border:1.5px solid var(--af);opacity:0}
.an-sym[data-phase="waehlt"] i{animation:anring 2.4s ease-out infinite}
.an-sym[data-phase="waehlt"] i:nth-of-type(2){animation-delay:.8s}.an-sym[data-phase="waehlt"] i:nth-of-type(3){animation-delay:1.6s}
.an-sym[data-phase="klingelt"] i:nth-of-type(1){animation:anring 1s ease-out infinite}
.an-sym[data-phase="klingelt"] .kern{animation:anpuls 1s ease-in-out infinite}
@keyframes anring{0%{transform:scale(1);opacity:.75}100%{transform:scale(1.75);opacity:0}}
@keyframes anpuls{50%{transform:scale(1.1)}}
.an-ziel{font:300 2em/1.15 var(--sans);color:var(--hell);max-width:100%;overflow-wrap:anywhere}
.an-nummer{font:500 .95em var(--mono);letter-spacing:.14em;color:var(--leise)}
.an-phase{display:inline-flex;align-items:center;gap:.6em;font:600 .8em var(--mono);letter-spacing:.24em;color:var(--hell);text-transform:uppercase;
 border:1px solid var(--linie);padding:.35em .9em;border-radius:3px}
.an-phase i{width:.7em;height:.7em;border-radius:50%;background:var(--leise)}
.an-phase[data-phase="waehlt"] i,.an-phase[data-phase="klingelt"] i{background:var(--glut);box-shadow:0 0 .8em var(--glut)}
.an-phase[data-phase="verbunden"] i{background:var(--gruen);box-shadow:0 0 .8em var(--gruen)}
.an-phase[data-phase="fehler"] i,.an-phase[data-phase="beendet"] i{background:#8b8b8b}
.an-zeit{font:300 2.6em/1 var(--mono);color:var(--hell);font-variant-numeric:tabular-nums;min-height:1em}
.an-rechts{display:flex;flex-direction:column;gap:.6em;min-height:0;min-width:0}
.an-rechts h3{font:600 .72em var(--mono);letter-spacing:.3em;color:var(--leise);text-transform:uppercase}
.an-blasen{flex:1;min-height:0;display:flex;flex-direction:column;gap:.55em;overflow-y:auto;scrollbar-width:none}
.an-blasen::-webkit-scrollbar{display:none}
.an-blasen>:first-child{margin-top:auto}
.blase{max-width:80%;padding:.55em .85em;border-radius:.9em;font:500 1em/1.38 var(--sans);overflow-wrap:anywhere}
.blase small{display:block;font:500 .66em var(--mono);letter-spacing:.14em;margin-bottom:.15em;opacity:.7}
.blase.jarvis{align-self:flex-end;background:rgba(255,106,31,.17);border:1px solid rgba(255,106,31,.55);color:var(--hell);border-bottom-right-radius:.25em}
.blase.gegenueber{align-self:flex-start;background:rgba(255,255,255,.09);border:1px solid rgba(255,255,255,.42);color:#fff;border-bottom-left-radius:.25em}
.blase.vorlaeufig{opacity:.6}
.blase.neu{animation:blaseein .35s ease-out}
@keyframes blaseein{from{opacity:0;transform:translateY(.5em)}to{opacity:1;transform:none}}
.an-ergebnis{border:1px solid var(--linie);border-radius:4px;padding:.7em 1em;display:none;flex-direction:column;gap:.3em;
 background:linear-gradient(180deg,rgba(255,255,255,.04),rgba(255,255,255,0))}
.an-ergebnis.da{display:flex}
.an-ergebnis .kopfzeile{font:600 1.15em/1.3 var(--sans);color:var(--hell)}
.an-ergebnis.ja .kopfzeile{color:var(--gruen)}.an-ergebnis.nein .kopfzeile{color:var(--rot)}
.an-ergebnis .unter{font:500 .85em/1.4 var(--sans);color:var(--text)}
.an-ergebnis .klein{font:500 .72em var(--mono);letter-spacing:.08em;color:var(--leise)}
/* Sicht */
.si-wurzel{flex:1;min-height:0;display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:1em}
.si-feld{border:1px solid var(--linie);border-radius:4px;padding:1em;display:flex;flex-direction:column;gap:.6em;min-height:0;min-width:0;
 background:linear-gradient(180deg,rgba(255,106,31,.05),rgba(255,106,31,0) 60%)}
.si-feld h3{font:600 .72em var(--mono);letter-spacing:.3em;color:var(--leise);text-transform:uppercase}
.si-mitte{flex:1;display:flex;flex-direction:column;align-items:center;justify-content:center;gap:.5em;text-align:center;min-height:0}
.si-ring{position:relative;width:min(100%,11em);aspect-ratio:1}
.si-ring svg{width:100%;height:100%;display:block}
.si-ring b{position:absolute;inset:0;display:grid;place-items:center;font:300 2.2em var(--sans);color:var(--hell);font-variant-numeric:tabular-nums}
.si-gross{font:300 3.4em/1.1 var(--sans);color:var(--hell);font-variant-numeric:tabular-nums}
.si-gross small{font:500 .3em var(--mono);color:var(--leise);margin-left:.4em;letter-spacing:.1em}
.si-tabelle{width:100%;border-collapse:collapse;font:500 .9em var(--sans);color:var(--text)}
.si-tabelle th{font:600 .68em var(--mono);letter-spacing:.16em;color:var(--leise);text-transform:uppercase;text-align:right;padding:.3em .4em;border-bottom:1px solid var(--linie)}
.si-tabelle th:first-child,.si-tabelle td:first-child{text-align:left}
.si-tabelle td{text-align:right;padding:.45em .4em;border-top:1px solid rgba(255,120,48,.12);font-variant-numeric:tabular-nums}
.si-punkt{display:inline-block;width:.7em;height:.7em;border-radius:50%;margin-right:.5em;vertical-align:baseline}
.si-punkt.gruen{background:var(--gruen)}.si-punkt.gelb{background:var(--gelb)}.si-punkt.rot{background:var(--rot)}
/* Untertitel */
.ut-liste{flex:1;min-height:0;display:flex;flex-direction:column;justify-content:flex-end;gap:1.3em;overflow:hidden}
.ut-eintrag{border-left:3px solid var(--glut);padding:.2em 0 .2em 1em;opacity:.28;transition:opacity .4s ease}
.ut-eintrag.ich{border-left-color:var(--glut)}
.ut-eintrag.gast{border-left-color:#fff;align-self:flex-end;border-left:0;border-right:3px solid #fff;padding:.2em 1em .2em 0;text-align:right}
.ut-eintrag:nth-last-child(1){opacity:1}.ut-eintrag:nth-last-child(2){opacity:.6}.ut-eintrag:nth-last-child(3){opacity:.4}
.ut-orig{font:500 1em/1.35 var(--sans);color:var(--leise)}
.ut-orig b,.ut-neu b{font:600 .7em var(--mono);letter-spacing:.2em;color:var(--glut);margin-right:.7em}
.ut-neu b{font-size:.26em;vertical-align:.45em}
.ut-neu{font:300 clamp(1.8em,3.4vw,3.6em)/1.2 var(--sans);color:var(--hell);margin-top:.15em;overflow-wrap:anywhere}
.ut-eintrag.gast .ut-neu{color:#fff}.ut-eintrag.gast .ut-neu b{color:#fff}
/* Hochfahren */
.hf-wurzel{flex:1;min-height:0;display:grid;grid-template-columns:minmax(160px,30%) minmax(0,1fr);gap:1.6em;align-items:center}
.hf-ring{position:relative;width:min(100%,14em);aspect-ratio:1;justify-self:center}
.hf-ring svg{width:100%;height:100%;display:block}
.hf-ring b{position:absolute;inset:0;display:grid;place-items:center;font:300 2.4em var(--sans);color:var(--hell);font-variant-numeric:tabular-nums}
.hf-rechts{display:flex;flex-direction:column;gap:1em;min-width:0}
.hf-schritte{list-style:none;display:flex;flex-direction:column;gap:.35em;font:500 1.15em/1.4 var(--mono);color:var(--text)}
.hf-schritte li{display:flex;gap:.8em;align-items:baseline}
.hf-schritte li span:first-child{width:1.2em;text-align:center}
.hf-schritte li.ok span:first-child{color:var(--gruen)}.hf-schritte li.nein span:first-child{color:var(--rot)}.hf-schritte li.offen span:first-child{color:var(--leise)}
.hf-schritte li small{color:var(--leise);font-size:.85em}
.hf-gruss{font:300 clamp(1.5em,2.6vw,2.6em)/1.25 var(--sans);color:var(--hell);min-height:1.3em;overflow-wrap:anywhere}
.hf-gruss::after{content:"▍";color:var(--orange);margin-left:.1em;animation:blink 1s steps(2) infinite}
.hf-gruss:empty::after{content:""}
.hf-gruss.fertig::after{content:""}
@keyframes blink{50%{opacity:0}}
/* Recherche */
.re-wurzel{flex:1;min-height:0;display:grid;grid-template-columns:minmax(0,1fr);gap:1.2em;overflow:hidden;align-content:start}
.re-wurzel.zwei{grid-template-columns:minmax(0,1.1fr) minmax(0,1fr)}
.re-absaetze{display:flex;flex-direction:column;gap:.8em;min-width:0;overflow:hidden}
.re-absaetze p{font:400 1.05em/1.55 var(--sans);color:var(--text)}
.re-liste{list-style:none;display:flex;flex-direction:column;gap:.55em;min-width:0;overflow:hidden}
.re-liste li{border:1px solid var(--linie);border-radius:4px;padding:.55em .8em;background:linear-gradient(180deg,rgba(255,106,31,.05),rgba(255,106,31,0) 70%)}
.re-liste li b{display:block;font:600 .95em/1.3 var(--sans);color:var(--hell)}
.re-liste li span{display:block;font:500 .82em/1.4 var(--sans);color:var(--leise);margin-top:.15em}
.re-quellen{font:500 .75em/1.6 var(--mono);color:var(--leise);letter-spacing:.06em}
.re-quellen b{color:var(--glut);font-weight:600;letter-spacing:.2em;text-transform:uppercase;margin-right:.8em}
/* Inhalte */
.in-tabelle{width:100%;border-collapse:collapse;font:500 1em var(--sans);color:var(--text)}
.in-tabelle th{font:600 .7em var(--mono);letter-spacing:.2em;color:var(--leise);text-transform:uppercase;text-align:left;padding:.4em .6em;border-bottom:1px solid var(--linie)}
.in-tabelle td{padding:.6em .6em;border-top:1px solid rgba(255,120,48,.12);vertical-align:baseline}
.in-tabelle td:first-child{font:500 .9em var(--mono);color:var(--glut);white-space:nowrap}
.in-status{font:600 .72em var(--mono);letter-spacing:.14em;text-transform:uppercase;border:1px solid var(--linie);padding:.2em .6em;border-radius:3px;color:var(--hell);white-space:nowrap}
.in-status.geplant,.in-status.bereit{color:var(--gruen);border-color:rgba(127,214,160,.5)}
.in-status.entwurf{color:var(--leise)}
.mitte .zeilen{overflow:hidden}
.liste{list-style:none;display:flex;flex-direction:column;gap:6px;overflow:hidden}
.liste li{display:flex;justify-content:space-between;gap:10px;font:500 12px var(--sans);color:var(--text);
 padding:5px 0;border-top:1px solid rgba(255,120,48,.12)}
.liste li:first-child{border-top:0}.liste li span:last-child{color:var(--leise);font:500 10px var(--mono);white-space:nowrap}
.liste li .a{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.leer{font:500 11px var(--mono);color:var(--leise);letter-spacing:.1em}
.diagramm{width:100%;height:120px;display:block}
.ticker{border-top:1px solid var(--linie);padding-top:6px;overflow:hidden;white-space:nowrap}
.ticker div{display:inline-block;padding-left:100%;animation:lauf 60s linear infinite;font:500 11px var(--mono);
 letter-spacing:.16em;color:var(--glut);text-transform:uppercase}
@keyframes lauf{to{transform:translateX(-100%)}}
@media (max-width:1000px){body{overflow:auto}main,main[data-modus]:not([data-modus="uebersicht"]){grid-template-columns:1fr}
 main[data-modus]:not([data-modus="uebersicht"]) .spalte{display:none}.buehne{min-height:420px}html,body{overflow:auto;height:auto}
 .an-wurzel,.si-wurzel,.hf-wurzel,.re-wurzel.zwei{grid-template-columns:1fr}}
@media (prefers-reduced-motion:reduce){.ticker div{animation:none;padding-left:0}
 main,.spalte,.globus canvas,.briefing,.ghud,.lage,.lage.aktiv,.ut-eintrag,.folgepunkte i{transition:none}
 .an-sym i,.an-sym .kern,.blase.neu,.hf-gruss::after{animation:none}}
</style></head><body>
<header class="kopf"><h1>Jarvis · Zentrale</h1><span class="chip" id="chip" data-z="bereit"><i></i><span id="chiptext">bereit</span></span>
<span class="chip aus" id="apchip"><i></i><span id="aptext">Autopilot aus</span></span><span class="platz"></span>
<span class="datum" id="datum"></span><span class="uhr" id="uhr">--:--</span></header>
<main id="haupt" data-modus="uebersicht">
 <section class="spalte">
  <div class="feld"><h2>Betrieb <span id="monatname"></span></h2><div class="ringe" id="ringe"></div></div>
  <div class="feld"><h2>Denken <span id="denkensumme"></span></h2><div id="denken"></div></div>
  <div class="feld" style="flex:1"><h2>Nachfassen <span id="nachzahl"></span></h2><ul class="liste" id="nachfassen"></ul></div>
 </section>
 <section class="mitte">
  <div class="buehne" id="buehne" data-modus="uebersicht">
   <div class="globus" id="globusfeld"><canvas id="globus"></canvas>
    <div class="briefing"><h2>Briefing</h2><div id="briefing"></div></div>
    <div class="ghud"><div class="gtitel" id="gtitel"></div><div class="gstand" id="gstand"></div><ol class="gliste" id="gliste"></ol></div>
    <div class="debug" id="debug"></div></div>
   <section class="lage" data-lage="maerkte" aria-label="Märkte">
    <header class="lkopf"><h2 id="mk-titel">Märkte</h2><span class="lchip" id="mk-zeitraum">Heute</span></header>
    <div class="mk-gitter" id="mk-gitter"></div><footer class="lfuss" id="mk-fuss"></footer></section>
   <section class="lage" data-lage="kennzahlen" aria-label="Kennzahlen">
    <header class="lkopf"><h2 id="kz-titel">Kennzahlen</h2><span class="lchip" id="kz-chip"></span></header>
    <div class="kz-gitter" id="kz-gitter"></div><footer class="lfuss" id="kz-fuss"></footer></section>
   <section class="lage" data-lage="anruf" aria-label="Anruf">
    <header class="lkopf"><h2 id="an-titel">Anruf</h2><span class="lchip" id="an-chip"></span></header>
    <div class="an-wurzel"><div class="an-links">
      <div class="an-sym" id="an-sym" data-phase="vorbereitet"><i></i><i></i><i></i><span class="kern"></span>
       <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M6.6 10.8c1.4 2.8 3.8 5.1 6.6 6.6l2.2-2.2c.3-.3.7-.4 1-.2 1.1.4 2.3.6 3.6.6.6 0 1 .4 1 1V20c0 .6-.4 1-1 1C9.6 21 3 14.4 3 6c0-.6.4-1 1-1h3.5c.6 0 1 .4 1 1 0 1.3.2 2.5.6 3.6.1.3 0 .7-.2 1l-2.3 2.2z"/></svg></div>
      <div class="an-ziel" id="an-ziel"></div><div class="an-nummer" id="an-nummer"></div>
      <span class="an-phase" id="an-phase" data-phase="vorbereitet"><i></i><span id="an-phasetext">bereit</span></span>
      <div class="an-zeit" id="an-zeit"></div></div>
     <div class="an-rechts"><h3 id="an-kopf">Mitschrift</h3><div class="lnotiz" id="an-notiz"></div>
      <div class="an-blasen" id="an-blasen"></div><div class="an-ergebnis" id="an-ergebnis"></div></div></div></section>
   <section class="lage" data-lage="sicht" aria-label="Sicht und Erholung">
    <header class="lkopf"><h2 id="si-titel">Sicht · Erholung</h2><span class="lchip" id="si-chip"></span></header>
    <div class="si-wurzel"><div class="si-feld"><h3>Erholung</h3><div class="si-mitte" id="si-erholung"></div></div>
     <div class="si-feld"><h3>Handruhe</h3><div class="si-mitte" id="si-handruhe"></div></div>
     <div class="si-feld"><h3>Zusammenhang</h3><div class="si-mitte" id="si-zusammenhang"></div></div></div>
    <footer class="lfuss" id="si-fuss"></footer></section>
   <section class="lage" data-lage="untertitel" aria-label="Untertitel">
    <header class="lkopf"><h2 id="ut-titel">Untertitel</h2><span class="lchip" id="ut-chip"></span></header>
    <div class="ut-liste" id="ut-liste"></div></section>
   <section class="lage" data-lage="hochfahren" aria-label="Hochfahren">
    <header class="lkopf"><h2 id="hf-titel">Hochfahren</h2><span class="lchip" id="hf-chip"></span></header>
    <div class="hf-wurzel"><div class="hf-ring" id="hf-ring"></div>
     <div class="hf-rechts"><ul class="hf-schritte" id="hf-schritte"></ul><div class="hf-gruss" id="hf-gruss"></div></div></div></section>
   <section class="lage" data-lage="recherche" aria-label="Recherche">
    <header class="lkopf"><h2 id="re-titel">Recherche</h2><span class="lchip" id="re-chip"></span></header>
    <div class="re-wurzel" id="re-wurzel"><div class="re-absaetze" id="re-absaetze"></div><ul class="re-liste" id="re-liste"></ul></div>
    <footer class="re-quellen" id="re-quellen"></footer><footer class="lfuss" id="re-fuss"></footer></section>
   <section class="lage" data-lage="inhalte" aria-label="Inhalte">
    <header class="lkopf"><h2 id="in-titel">Inhalte</h2><span class="lchip" id="in-chip"></span></header>
    <div style="flex:1;min-height:0;overflow:hidden" id="in-box"></div><footer class="lfuss" id="in-fuss"></footer></section>
   <div class="folgepunkte" id="folgepunkte"></div>
  </div>
 </section>
 <section class="spalte">
  <div class="feld"><h2>Einnahmen und Ausgaben <span>30 Tage</span></h2><svg class="diagramm" id="verlauf" viewBox="0 0 300 120" preserveAspectRatio="none" role="img" aria-label="Verlauf der letzten dreißig Tage"></svg></div>
  <div class="feld"><h2>Pipeline <span id="pipewert"></span></h2><div id="pipeline"></div></div>
  <div class="feld" style="flex:1"><h2>Was Jarvis getan hat <span id="aktzahl"></span></h2><ul class="liste" id="feed"></ul></div>
 </section>
</main>
<div class="ticker"><div id="ticker">Jarvis ist da</div></div>
<script>
""" + FEHLERFANG + r"""
const SCHLUESSEL="{{SCHLUESSEL}}";const ANHANG=SCHLUESSEL?"?schluessel="+encodeURIComponent(SCHLUESSEL):"";
const $=s=>document.querySelector(s);const ZUSTAND={bereit:"bereit",hoert:"hört zu",denkt:"denkt nach",spricht:"spricht"};
const DEBUG=new URLSearchParams(location.search).get("debug")==="1";
let REDUZIERT=matchMedia("(prefers-reduced-motion: reduce)").matches;
try{matchMedia("(prefers-reduced-motion: reduce)").addEventListener("change",e=>{REDUZIERT=e.matches})}catch(e){}
function h(t,p,...k){const e=document.createElement(t);for(const a in(p||{})){if(a==="class")e.className=p[a];else e.setAttribute(a,p[a])}
 k.flat().forEach(x=>{if(x!=null)e.append(x.nodeType?x:document.createTextNode(String(x)))});return e}
const euro=n=>(typeof n==="number"?n:0).toLocaleString("de-DE",{maximumFractionDigits:0})+" €";
const NS="http://www.w3.org/2000/svg";function s(t,a){const e=document.createElementNS(NS,t);for(const k in a)e.setAttribute(k,a[k]);return e}
const istZahl=x=>typeof x==="number"&&isFinite(x);
const zahl=(n,k)=>n.toLocaleString("de-DE",{minimumFractionDigits:k,maximumFractionDigits:k});
const klemme=(x,a,b)=>Math.max(a,Math.min(b,x));
function kuerzen(t,n){t=String(t==null?"":t).replace(/\s+/g," ").trim();return t.length>n?t.slice(0,n-1).trimEnd()+"…":t}
function hhmm(z){if(!z)return"";const d=new Date(String(z).replace(" ","T"));return isNaN(d)?"":d.toLocaleTimeString("de-DE",{hour:"2-digit",minute:"2-digit"})}
const WTAG=["So","Mo","Di","Mi","Do","Fr","Sa"];
function datumKurz(t){const m=/^(\d{4})-(\d\d)-(\d\d)/.exec(String(t||""));if(!m)return String(t||"");
 return WTAG[new Date(Date.UTC(+m[1],+m[2]-1,+m[3])).getUTCDay()]+", "+m[3]+"."+m[2]+"."}
function hostname(u){try{return new URL(String(u)).hostname.replace(/^www\./,"")}catch(e){return""}}
function mmss(sek){sek=Math.max(0,Math.floor(sek));return String(Math.floor(sek/60)).padStart(2,"0")+":"+String(sek%60).padStart(2,"0")}
// --- Uhr
function uhr(){const d=new Date();$("#uhr").textContent=d.toLocaleTimeString("de-DE",{hour:"2-digit",minute:"2-digit"})}uhr();setInterval(uhr,10000);
// --- Ringe
function ringSvg(wert,farbe){const r=40,u=2*Math.PI*r,f=Math.max(0,Math.min(1,wert||0));
 const v=s("svg",{viewBox:"0 0 100 100"});v.append(s("circle",{cx:50,cy:50,r:r,fill:"none",stroke:"rgba(255,140,70,.14)","stroke-width":7}));
 const c=s("circle",{cx:50,cy:50,r:r,fill:"none",stroke:farbe||"#ff6a1f","stroke-width":7,"stroke-linecap":"round",
  "stroke-dasharray":(u*f).toFixed(1)+" "+(u).toFixed(1),transform:"rotate(-90 50 50)"});v.append(c);
 for(let i=0;i<40;i++){const w=i/40*Math.PI*2,x1=50+46*Math.cos(w),y1=50+46*Math.sin(w),x2=50+(i%5?48:50)*Math.cos(w),y2=50+(i%5?48:50)*Math.sin(w);
  v.append(s("line",{x1:x1,y1:y1,x2:x2,y2:y2,stroke:"rgba(255,140,70,.35)","stroke-width":.6}))}
 return v}
function ring(wert,name,text,farbe){return h("div",{class:"ring"},ringSvg(wert,farbe),h("b",{},text),h("small",{},name))}
function balken(name,wert,max,text){const f=max>0?Math.max(0,Math.min(1,wert/max)):0;
 return h("div",{class:"balken"},h("div",{},h("span",{},name),h("b",{},text)),h("div",{class:"s"},h("i",{style:"width:"+(f*100).toFixed(1)+"%"})))}
function liste(box,zeilen,leer){box.replaceChildren(...(zeilen.length?zeilen:[h("li",{},h("span",{class:"leer"},leer))]))}
function zeile(links,rechts){return h("li",{},h("span",{class:"a"},links),h("span",{},rechts))}
function alter(z){if(!z)return"";const sek=Math.max(0,(Date.now()-new Date(String(z).replace(" ","T")).getTime())/1000);
 return sek<90?"vor "+Math.round(sek)+" s":sek<5400?"vor "+Math.round(sek/60)+" min":sek<172800?"vor "+Math.round(sek/3600)+" h":"vor "+Math.round(sek/86400)+" d"}
// --- Verlauf
function verlauf(v){const box=$("#verlauf");box.replaceChildren();const ein=(v&&v.einnahmen)||[],aus=(v&&v.ausgaben)||[];
 if(!ein.length){box.append(s("text",{x:150,y:64,"text-anchor":"middle",fill:"#9a8678","font-size":10},"Noch keine Buchungen"));return}
 const max=Math.max(1,...ein,...aus);const n=ein.length;
 for(let i=0;i<=3;i++){const y=8+i*34;box.append(s("line",{x1:0,x2:300,y1:y,y2:y,stroke:"rgba(255,140,70,.12)","stroke-width":.5}))}
 const pfad=(a,f)=>{let d="";a.forEach((w,i)=>{const x=i/(n-1||1)*300,y=110-w/max*100;d+=(i?"L":"M")+x.toFixed(1)+" "+y.toFixed(1)});return d};
 box.append(s("path",{d:pfad(ein)+"L300 110L0 110Z",fill:"rgba(255,106,31,.22)",stroke:"none"}));
 box.append(s("path",{d:pfad(ein),fill:"none",stroke:"#ff9a52","stroke-width":1.6,"vector-effect":"non-scaling-stroke"}));
 box.append(s("path",{d:pfad(aus),fill:"none",stroke:"#7fd6a0","stroke-width":1.2,"stroke-dasharray":"3 3","vector-effect":"non-scaling-stroke"}));
 const x=300,y=110-ein[n-1]/max*100;box.append(s("circle",{cx:x-1,cy:y,r:2.6,fill:"#fff"}))}
// --- Rechnen: reine Funktionen ohne Seitenbezug (die Prüfung führt genau diesen Block mit node aus)
// <rechnen-zentrale>
function zahlOder(x,d){x=Number(x);return isFinite(x)?x:d}
// Vorzeichenbehafteter kürzester Längenunterschied von a nach b, in (-180, 180].
function lonWeg(a,b){var d=((zahlOder(b,0)-zahlOder(a,0))%360+360)%360;return d>180?d-360:d}
// Sanfter Verlauf 0..1 (kubisch): langsam los, schnell in der Mitte, langsam an.
function easeInOut(p){p=Math.max(0,Math.min(1,zahlOder(p,0)));return p<0.5?4*p*p*p:1-Math.pow(-2*p+2,3)/2}
// Zoom beim Flug: logarithmisch zwischen den Zoomstufen, bei weiten Flügen mittendrin herausgezogen (Überblick über den Bogen).
function flugZoom(z0,z1,winkelGrad,p){
 var a=Math.log2(Math.max(1,zahlOder(z0,1))),b=Math.log2(Math.max(1,zahlOder(z1,1)));p=Math.max(0,Math.min(1,zahlOder(p,0)));
 var w=Math.min(1,Math.max(0,zahlOder(winkelGrad,0))/90);
 var z=Math.pow(2,a+(b-a)*p-0.9*Math.sin(Math.PI*p)*w);
 return Math.max(1,Math.min(6,z))}
function kugelPunkt(a){return Array.isArray(a)?[zahlOder(a[0],0),zahlOder(a[1],0)]:[zahlOder(a&&a.lat,0),zahlOder(a&&a.lon,0)]}
// Winkelabstand zweier Punkte [lat, lon] auf der Kugel, in Grad.
function kugelWinkel(a,b){
 var A=kugelPunkt(a),B=kugelPunkt(b),r=Math.PI/180,p1=A[0]*r,p2=B[0]*r,dl=(B[1]-A[1])*r;
 return Math.acos(Math.max(-1,Math.min(1,Math.sin(p1)*Math.sin(p2)+Math.cos(p1)*Math.cos(p2)*Math.cos(dl))))/r}
// Punkt auf dem Großkreis zwischen a und b (je [lat, lon] oder {lat, lon}); p 0..1. Gibt [lat, lon] zurück.
function kugelLerp(a,b,p){
 var A=kugelPunkt(a),B=kugelPunkt(b),r=Math.PI/180,g=180/Math.PI;p=Math.max(0,Math.min(1,zahlOder(p,0)));
 var la=A[0]*r,oa=A[1]*r,lb=B[0]*r,ob=B[1]*r;
 var ax=Math.cos(la)*Math.cos(oa),ay=Math.cos(la)*Math.sin(oa),az=Math.sin(la);
 var bx=Math.cos(lb)*Math.cos(ob),by=Math.cos(lb)*Math.sin(ob),bz=Math.sin(lb);
 var om=Math.acos(Math.max(-1,Math.min(1,ax*bx+ay*by+az*bz)));
 if(om<1e-9)return[A[0],A[1]];
 if(Math.PI-om<1e-6)return[A[0]+(B[0]-A[0])*p,A[1]+lonWeg(A[1],B[1])*p];
 var so=Math.sin(om),sa=Math.sin((1-p)*om)/so,sb=Math.sin(p*om)/so;
 var x=sa*ax+sb*bx,y=sa*ay+sb*by,z=sa*az+sb*bz;
 return[Math.asin(Math.max(-1,Math.min(1,z)))*g,Math.atan2(y,x)*g]}
// Stichwörter der Themenfolge: beide Seiten falten gleich (klein, ä→ae, ö→oe, ü→ue, ß→ss, Satzzeichen weg).
function faltenText(t){return String(t==null?"":t).toLowerCase().replace(/ä/g,"ae").replace(/ö/g,"oe").replace(/ü/g,"ue").replace(/ß/g,"ss")
 .replace(/[^\p{L}\p{N}_]+/gu," ").trim()}
// Ein Stichwort zählt nur als ganzes Wort (oder ganze Wortfolge).
function stichwortTrifft(text,stichwort){var k=faltenText(stichwort);if(!k)return false;return(" "+faltenText(text)+" ").indexOf(" "+k+" ")>=0}
// Die Landmaske: Lauflängen zur Basis 36, Zeilen mit ";", jede Zeile beginnt mit Wasser. Gibt Uint8Array (1 Land) oder null zurück.
function rleDekodieren(rle,breite,hoehe){
 if(!rle||!(breite>0)||!(hoehe>0))return null;
 var zeilen=String(rle).split(";");if(zeilen.length!==hoehe)return null;
 var m=new Uint8Array(breite*hoehe),i,k;
 for(i=0;i<hoehe;i++){var teile=zeilen[i].split(","),pos=i*breite,land=0,summe=0;
  for(k=0;k<teile.length;k++){var n=parseInt(teile[k],36);if(!(n>=0)||summe+n>breite)return null;
   if(land&&n)m.fill(1,pos+summe,pos+summe+n);summe+=n;land=1-land}
  if(summe!==breite)return null}
 return m}
// Punktsatz einer Landmaske in Schritten von "schritt" Zellen: Mehrheit je Block, Küstenpunkte getrennt.
// Je Zeile stehen so viele Punkte, wie bei dieser Breite in gleichem Abstand auf die Kugel passen (zu den Polen hin
// weniger, jede zweite Zeile um einen halben Abstand versetzt); jeder Punkt fragt den Block unter sich. Alle Punkte als
// [sinBreite, cosBreite, Längenbogen], zeilenweise von Nord nach Süd, mit Zeilenanfängen.
function punktMengeBauen(maske,breite,hoehe,schritt){
 var bb=Math.floor(breite/schritt),bh=Math.floor(hoehe/schritt),dz=schritt*360/breite,i,j,x,y,o,n;
 var blk=new Uint8Array(bb*bh),halb=schritt*schritt/2;
 for(i=0;i<bh;i++)for(j=0;j<bb;j++){
  n=0;for(y=0;y<schritt;y++){o=(i*schritt+y)*breite+j*schritt;for(x=0;x<schritt;x++)n+=maske[o+x]}
  blk[i*bb+j]=(n>0&&n>=halb)?1:0}
 var rl=new Uint32Array(bh+1),rk=new Uint32Array(bh+1),al=[],ak=[];
 for(i=0;i<bh;i++){var lat=(90-(i+0.5)*dz)*Math.PI/180,sb=Math.sin(lat),cb=Math.cos(lat);
  var anz=Math.max(1,Math.min(bb,Math.round(360*cb/dz))),off=(i&1)?0.5:0.25;
  for(var g=0;g<anz;g++){var lonGrad=-180+(g+off)*360/anz;j=Math.min(bb-1,Math.floor((lonGrad+180)/dz));
   if(!blk[i*bb+j])continue;
   var kueste=!blk[i*bb+(j+1)%bb]||!blk[i*bb+(j+bb-1)%bb]||(i>0&&!blk[(i-1)*bb+j])||(i<bh-1&&!blk[(i+1)*bb+j]);
   (kueste?ak:al).push(sb,cb,lonGrad*Math.PI/180)}
  rl[i+1]=al.length/3;rk[i+1]=ak.length/3}
 return{schritt:schritt,zeilen:bh,lat0:90-dz/2,dz:dz,faktor:schritt*0.55,minD:1.2,anzahl:(al.length+ak.length)/3,
  land:{pts:new Float32Array(al),start:rl},kueste:{pts:new Float32Array(ak),start:rk}}}
// </rechnen-zentrale>
// --- Globus: echte Küsten aus /api/weltkarte, Umrisse als Ersatz
const LAND=[
[[-9.5,37],[-9,43],[-1.8,43.5],[-4.5,48.5],[2,51],[5,53.5],[8.2,55],[8.2,57.2],[10.5,57.8],[11,58.5],[8,58],[5.5,58.5],[5,61],[8,63.5],[13,67],[16,69],[20,70],[26,71],[31,70.2],[33,69.4],[41,66.8],[44,68.5],[60,69],[68,69],[73,72.5],[80,73.5],[95,76],[105,77.5],[113,74],[130,71.5],[140,72.5],[160,70],[170,70],[180,68.5],[180,65],[165,60],[155,58],[156,51],[143,59],[140,54],[135,48],[131,42.5],[129,40],[129,35],[126.5,34.5],[126,38],[121.5,40],[118,38.5],[121,36.5],[122,31],[120,27],[116,22.5],[110,21],[108,21.5],[106,19],[109,12],[105,8.5],[103,10.5],[100.5,13],[100,7],[103.5,1.5],[101,3],[98.5,8],[98,16],[94.5,16.5],[92,22],[89,22],[86,20],[80,15.5],[80,10],[77.5,8],[75,12],[72.8,20],[70,21.5],[67,24.5],[62,25],[57,25.5],[56.5,27],[51,28],[48.5,30],[50,26.5],[51,24.5],[56.5,26],[59.5,22.5],[55,17],[52,16],[45,12.7],[43,13.5],[39,21],[35,28],[34.5,29.5],[35,32],[36,36.5],[30,36.5],[27,37],[26,40],[24,40],[23,38],[21,38],[23,36.5],[20,40],[19.5,41.5],[15,44.2],[13.7,45.6],[12.3,44.5],[14,42.5],[16,41.5],[18.5,40],[17,39],[15.5,38],[16,38],[15,40],[12,42],[10.5,43],[8,43.8],[4.5,43.3],[3,42],[0,38.5],[-2,36.8],[-5.5,36]],
[[-17,21],[-16.5,16],[-17.5,14.7],[-15,11],[-13,8],[-10,6],[-7.5,4.4],[-2,4.8],[1,6],[4.5,6.3],[8,4.5],[9.8,3.5],[9.5,0],[12,-5],[13.5,-11],[12,-17],[14.5,-22.5],[15,-27],[18,-32.5],[20,-35],[25,-34],[30,-31],[32.5,-27],[35,-24],[35.5,-20],[40,-15],[40.5,-10.5],[39,-6],[41,-1.5],[45,2],[51,11.8],[43.5,11.7],[39,17],[37,21],[34,27.5],[32.5,30],[30,31.5],[25,31.5],[20,32],[15,32.5],[11,33.5],[10,37],[5,36.8],[0,35.8],[-5.5,35.8],[-9.5,32],[-10,29],[-13,27.5]],
[[-168,66],[-156,71.3],[-141,69.5],[-125,70],[-110,68],[-95,69],[-90,68.5],[-82,69],[-81,66],[-78,64],[-72,62],[-65,60],[-62,57],[-56,52.5],[-60,50],[-66,50],[-64,47],[-60,46],[-66,44],[-70,43.5],[-70,41.5],[-74,40.5],[-76,37],[-76,35],[-81,31.5],[-80,26],[-81,25.2],[-82.5,28],[-84,30],[-89,30],[-90,29],[-94,29.5],[-97,27.5],[-97.5,22],[-95.5,18.5],[-92,18.5],[-90.5,21],[-87,21.5],[-88,16],[-84,15.8],[-83.5,11],[-80,9],[-77.5,8.5],[-75,11],[-71.5,12],[-68,10.5],[-62,10.7],[-60,8.5],[-57,6],[-52,5],[-50,1.5],[-48,-1],[-44,-2.5],[-39,-3.5],[-35,-5.5],[-35,-9],[-39,-14],[-39,-18],[-41,-22],[-45,-23.5],[-48,-26],[-48.5,-28.5],[-53,-34],[-57,-34.8],[-57,-37],[-62,-39],[-65,-41],[-64,-43],[-67,-46],[-66,-48],[-69,-51],[-68.5,-53],[-72,-54],[-74.5,-50],[-75.5,-47],[-73.5,-43],[-73.5,-37],[-71.5,-30],[-70.3,-18],[-76,-14],[-81,-6],[-80.5,-2],[-79,2],[-77.5,6],[-80,7],[-84,9],[-86,11],[-88,13],[-92,14.5],[-96,15.7],[-105,19.5],[-106,23],[-112,29],[-114.5,31.5],[-110,23],[-112,25],[-115,29.5],[-117,32.5],[-120.5,34.5],[-124,40],[-124.5,46],[-123,48.5],[-128,51],[-131,54.5],[-137,58.5],[-145,60.5],[-152,59],[-158,56.5],[-164,54.5],[-158,58],[-162,59.5],[-165,62]],
[[113,-22],[114,-26],[115,-34],[118,-35],[123,-34],[129,-31.5],[135,-34.5],[138,-35],[140,-38],[146,-39],[150,-37],[153,-31],[153.5,-25],[150,-22],[146,-19],[145.5,-15],[143,-11],[142,-11],[141.5,-17],[136,-15],[137,-12],[132,-11.5],[129,-15],[126,-14],[122,-17.5],[117,-20]],
[[-73,78],[-60,82],[-30,83.5],[-20,81],[-18,76],[-22,70],[-32,68],[-40,65],[-43,60],[-48,61],[-53,65],[-55,70],[-60,76]],
[[-5.5,50],[1.5,51],[1.7,53],[-0.5,54.5],[-2,56],[-2,57.7],[-3.5,58.6],[-5.5,58.5],[-6,56],[-5,55],[-3.2,54.5],[-3,53.4],[-4.7,52],[-5,51.5]],
[[-10,52],[-6,52],[-6,54.5],[-8,55],[-10,54]],[[-24,65.5],[-18,66.5],[-13.5,65],[-15,64],[-21,63.5],[-23,64.5]],
[[130.8,33.8],[135,34],[139.5,35],[141,38.5],[141.5,41],[140,41],[139.5,38],[136.5,36.8],[132,35.5]],[[140,42],[141.5,45.4],[145.5,43.3],[143,42]],
[[95,5.5],[98,4],[104,-1],[106,-3],[105.5,-5.8],[101,-3],[97,2]],[[105.5,-6.5],[114,-7.5],[114,-8.7],[106,-7.5]],
[[109,1.5],[111,2],[115,5],[118,5],[119,1],[117,-1],[116,-3.8],[112,-3.5],[110,-2.5],[109,0]],
[[131,-1],[135,-3],[141,-2.5],[147,-6],[150.5,-10.5],[147,-10],[143,-9],[138,-8],[137,-5],[133,-4]],
[[120,18],[122,18.2],[121.5,14],[124,12.5],[120.5,14.5]],[[49,-12],[50.5,-15.5],[47,-25],[44,-24.5],[44,-17],[47,-14]],
[[173,-35],[175,-37],[178,-37.7],[175.5,-41.5],[173,-39],[174,-37]],[[172,-41],[174,-41.5],[171,-44.5],[169,-46.5],[166.5,-46],[168,-44],[170.5,-42.5]],
[[-85,22],[-81,23],[-74,20],[-77.5,20],[-80,21.5]],[[-180,-72],[180,-72],[180,-90],[-180,-90]]];
const MEER=[[[28,41.5],[28,44.5],[30,46.5],[33,45.5],[36.5,45.2],[40,43.5],[41.5,41.5],[35,42],[31,41.2]],
[[47,45],[50,46.5],[53,45.5],[53,40],[54,37.5],[50,37],[49,40],[47.5,43]],
[[10.5,54],[13,54.5],[19,54.5],[21,56],[21,57.5],[24,57.5],[24,59.5],[30,60],[23,59.7],[21,60.5],[19,59],[17,57.5],[16.5,56],[13,55.5],[11,56]],
[[17,61],[18,63],[21,65],[25,65.5],[24,63],[21.5,61]],
[[-95,59],[-93,61.5],[-88,64],[-82,62.5],[-78,62],[-77,58],[-79,55],[-82,52.5],[-85,55],[-90,57]]];
function innen(pt,poly){let c=false;for(let i=0,j=poly.length-1;i<poly.length;j=i++){const a=poly[i],b=poly[j];
 if(((a[1]>pt[1])!==(b[1]>pt[1]))&&(pt[0]<(b[0]-a[0])*(pt[1]-a[1])/(b[1]-a[1])+a[0]))c=!c}return c}
const gl=$("#globus");let gg=gl.getContext("2d");const HAUPT=gg;let GW=1,GH=1,GD=1;
function gresize(){const b=gl.parentElement.getBoundingClientRect();GW=Math.max(1,b.width);GH=Math.max(1,b.height);
 GD=Math.min(2,devicePixelRatio||1);while(GW*GH*GD*GD>7e6&&GD>1)GD=Math.max(1,GD-0.25);
 gl.width=Math.round(GW*GD);gl.height=Math.round(GH*GD);gg.setTransform(GD,0,0,GD,0,0)}
gresize();if(window.ResizeObserver)new ResizeObserver(gresize).observe(gl.parentElement);addEventListener("resize",gresize);
const rad=Math.PI/180;const T0=performance.now();
function proj(lat,lon,R,cx,cy,l0,t){const p=lat*rad,l=(lon-l0)*rad,cp=Math.cos(t),sp=Math.sin(t);
 const x=Math.cos(p)*Math.sin(l),y=cp*Math.sin(p)-sp*Math.cos(p)*Math.cos(l),sicht=sp*Math.sin(p)+cp*Math.cos(p)*Math.cos(l);
 return[cx+R*x,cy-R*y,sicht]}
const winkel=kugelWinkel;
let ORTE=[],LICHTER=[],ZENTRALE=null,MARKER_UEB=[];
// Die Landpunkte: drei Auflösungen aus der Maske (1°, 0,5°, 0,25°), je nach Zoom. Ohne Maske die alten Umrisse.
let MASKE=null,MASKE_ZUSTAND="laden",MBREITE=1440,MHOEHE=720;const MENGEN={};let FALLBACK=null;
function fallbackMenge(){
 if(FALLBACK)return FALLBACK;
 const dz=0.95,zeilen=[];
 for(let lat=82;lat>=-80;lat-=dz){const schritt=dz/Math.max(0.25,Math.cos(lat*rad)),reihe=[];
  for(let lon=-180;lon<180;lon+=schritt){const pt=[lon,lat];
   if(LAND.some(p=>innen(pt,p))&&!MEER.some(p=>innen(pt,p))){const pr=lat*rad;reihe.push(Math.sin(pr),Math.cos(pr),lon*rad)}}
  zeilen.push(reihe)}
 const start=new Uint32Array(zeilen.length+1);zeilen.forEach((r,i)=>{start[i+1]=start[i]+r.length/3});
 const pts=new Float32Array(start[zeilen.length]*3);let o=0;zeilen.forEach(r=>{pts.set(r,o);o+=r.length});
 FALLBACK={schritt:1,zeilen:zeilen.length,lat0:82,dz:dz,faktor:1,minD:1.7,anzahl:start[zeilen.length],land:{pts:pts,start:start},
  kueste:{pts:new Float32Array(0),start:new Uint32Array(zeilen.length+1)}};
 return FALLBACK}
function mengeFuer(schritt){
 if(MASKE_ZUSTAND==="fehlt")return fallbackMenge();
 if(!MASKE)return null;
 return MENGEN[schritt]||(MENGEN[schritt]=punktMengeBauen(MASKE,MBREITE,MHOEHE,schritt))}
fetch("/api/weltkarte"+ANHANG).then(r=>r.json()).then(k=>{
 const m=k&&k.ok&&k.rle?rleDekodieren(k.rle,k.breite,k.hoehe):null;
 if(m){MASKE=m;MBREITE=k.breite;MHOEHE=k.hoehe;MASKE_ZUSTAND="da";mengeFuer(4);setTimeout(()=>mengeFuer(2),400);setTimeout(()=>mengeFuer(1),1400)}
 else MASKE_ZUSTAND="fehlt"}).catch(()=>{MASKE_ZUSTAND="fehlt"});
// --- Kamera: Flug zum Fokus (1,8 s), ohne Bewegung springt sie
const KAM={lat:24,lon:15,zoom:1};let FLUG=null,KAM_ART="";
let GMODUS="uebersicht",FOKUS=null,FOKUSNR=0,MARKER=[],BOEGEN=[],LISTE_BREITE=0,HUD=0,CXV=0,BM="uebersicht";
function uebersichtsZiel(sek){
 // Der Blick liegt auf dem Betrieb, so nah, dass seine Kunden sichtbar werden; ohne Orte dreht sich die Erde.
 const heim=ORTE.find(o=>o.art==="zuhause")||ORTE[0];
 if(heim){const w=Math.max(0,...ORTE.map(o=>winkel([heim.lat,heim.lon],[o.lat,o.lon])));
  const zoom=w<12?1.55:w<30?1.35:w<60?1.15:1;
  return{lat:heim.lat,lon:heim.lon+(REDUZIERT?0:Math.sin(sek*0.17)*7),zoom:zoom,art:"heim:"+heim.lat+","+heim.lon+","+zoom}}
 return{lat:24,lon:15+(REDUZIERT?0:sek*3.5),zoom:1,art:"welt"}}
function zielBestimmen(sek){
 if(GMODUS==="globus"){
  if(FOKUS)return{lat:FOKUS.lat,lon:FOKUS.lon,zoom:FOKUS.zoom,art:"fokus:"+FOKUS.nr};
  return{lat:22,lon:15+(REDUZIERT?0:sek*3.5),zoom:1,art:"welt"}}
 return uebersichtsZiel(sek)}
function kameraNachfuehren(jetzt,sek){
 const z=zielBestimmen(sek);
 if(KAM_ART===""){KAM.lat=z.lat;KAM.lon=z.lon;KAM.zoom=z.zoom;KAM_ART=z.art}
 else if(z.art!==KAM_ART){KAM_ART=z.art;
  const w=kugelWinkel([KAM.lat,KAM.lon],[z.lat,z.lon]);
  if(!REDUZIERT&&(w>0.4||Math.abs(Math.log2(z.zoom/KAM.zoom))>0.03))
   FLUG={von:{lat:KAM.lat,lon:KAM.lon,zoom:KAM.zoom},t0:jetzt,dauer:1800,winkel:w};
  else FLUG=null}
 if(FLUG){const p=Math.min(1,(jetzt-FLUG.t0)/FLUG.dauer),e=easeInOut(p);
  const q=kugelLerp([FLUG.von.lat,FLUG.von.lon],[z.lat,z.lon],e);
  KAM.lat=q[0];KAM.lon=q[1];KAM.zoom=flugZoom(FLUG.von.zoom,z.zoom,FLUG.winkel,e);
  if(p>=1)FLUG=null}
 else{KAM.lat=z.lat;KAM.lon=z.lon;KAM.zoom=z.zoom}}
// --- Marker und Bögen aus den Daten der Bühne
function markerBauen(liste,versatz){
 return liste.map((m,i)=>({lat:m.lat,lon:m.lon,sb:Math.sin(m.lat*rad),cb:Math.cos(m.lat*rad),lr:m.lon*rad,art:m.art||"ort",
  label:m.label,t0:versatz===null?-1e9:performance.now()+versatz*i}))}
function koordText(){const lat=KAM.lat,lon=lonWeg(0,KAM.lon);
 return zahl(Math.abs(lat),1)+"° "+(lat>=0?"N":"S")+" · "+zahl(Math.abs(lon),1)+"° "+(lon>=0?"O":"W")+" · ZOOM "+zahl(KAM.zoom,1)+"×"}
function globusSetzen(d){
 if(!d){GMODUS="uebersicht";MARKER=[];BOEGEN=[];LISTE_BREITE=0;return}
 GMODUS="globus";
 const f=d.fokus;
 FOKUS=f&&istZahl(f.lat)&&istZahl(f.lon)?{lat:klemme(f.lat,-85,85),lon:f.lon,zoom:klemme(istZahl(f.zoom)?f.zoom:2,1,6),name:String(f.name||""),nr:++FOKUSNR}:null;
 MARKER=markerBauen((Array.isArray(d.marker)?d.marker:[]).filter(m=>m&&istZahl(m.lat)&&istZahl(m.lon)).slice(0,12)
  .map(m=>({lat:klemme(m.lat,-90,90),lon:m.lon,art:m.art,label:kuerzen(m.titel||"",42)})),140);
 BOEGEN=(Array.isArray(d.boegen)?d.boegen:[]).slice(0,6).filter(b=>b&&Array.isArray(b.von)&&Array.isArray(b.nach)
  &&istZahl(b.von[0])&&istZahl(b.von[1])&&istZahl(b.nach[0])&&istZahl(b.nach[1])).map(b=>{
   const pts=[];for(let i=0;i<=32;i++){const q=kugelLerp(b.von,b.nach,i/32);pts.push([Math.sin(q[0]*rad),Math.cos(q[0]*rad),q[1]*rad])}
   return{pts:pts,von:b.von,nach:b.nach}});
 $("#gtitel").textContent=kuerzen(d.titel||"",80);
 $("#gstand").textContent=kuerzen(d.stand||"",160);
 const eintraege=(Array.isArray(d.liste)?d.liste:[]).filter(x=>x&&x.titel).slice(0,8);
 $("#gliste").replaceChildren(...eintraege.map(x=>{const z=hhmm(x.zeit);
  return h("li",{},z?h("span",{class:"z"},z):"",z?" · ":"",x.quelle?h("span",{class:"q"},String(x.quelle)):"",x.quelle?" · ":"",kuerzen(x.titel,120))}));
 LISTE_BREITE=eintraege.length?Math.min(340,GW*0.32)+40:0}
// Punktsatz zum Zoom: unter 1,6 ein Grad, unter 3 ein halbes, sonst ein Viertelgrad.
function punkteZeichnen(m,teil,fl,w,K,d,farbe){
 const pts=teil.pts,st=teil.start;
 const b0=klemme(Math.floor((m.lat0-(fl+w))/m.dz),0,m.zeilen-1),b1=klemme(Math.ceil((m.lat0-(fl-w))/m.dz),0,m.zeilen-1);
 gg.fillStyle=farbe;let n=0;
 for(let i=st[b0]*3,ende=st[b1+1]*3;i<ende;i+=3){
  const dl=pts[i+2]-K.l0,cl=Math.cos(dl),sicht=K.sp*pts[i]+K.cp*pts[i+1]*cl;if(sicht<0.02)continue;
  const x=K.cx+K.R*pts[i+1]*Math.sin(dl),y=K.cy-K.R*(K.cp*pts[i]-K.sp*pts[i+1]*cl);
  if(x<-8||x>GW+8||y<-8||y>GH+8)continue;
  const e=d*(0.55+sicht*.55);gg.fillRect(x-e/2,y-e/2,e,e);n++}
 return n}
function markerZeichnen(liste,K){
 const belegt=[],rechts=GW-8-(BM==="globus"?LISTE_BREITE:0),sicht=[];
 for(const m of liste){const dl=m.lr-K.l0,cl=Math.cos(dl),sv=K.sp*m.sb+K.cp*m.cb*cl;if(sv<=0.05)continue;
  const x=K.cx+K.R*m.cb*Math.sin(dl),y=K.cy-K.R*(K.cp*m.sb-K.sp*m.cb*cl);if(x<-20||x>GW+20||y<-20||y>GH+20)continue;sicht.push({m:m,x:x,y:y})}
 const rang=a=>a==="zuhause"?0:a==="nachricht"?1:2;sicht.sort((a,b)=>rang(a.m.art)-rang(b.m.art));
 gg.font="600 11px ui-monospace,Menlo,monospace";gg.textBaseline="alphabetic";
 sicht.forEach((p,idx)=>{
  const m=p.m,x=p.x,y=p.y,nachricht=m.art==="nachricht";
  let ein=REDUZIERT?1:klemme((K.jetzt-m.t0)/450,0,1);if(ein<=0)return;ein=ein*ein*(3-2*ein);
  const phase=(K.sek*0.8+idx*0.37)%1;
  if(nachricht){
   const r=5.5*ein;
   gg.lineWidth=1.4;
   for(let k=0;k<2;k++){const ph=REDUZIERT?0.45:(phase+k*0.5)%1;gg.strokeStyle="rgba(159,231,255,"+((1-ph)*0.85*ein).toFixed(3)+")";
    gg.beginPath();gg.arc(x,y,6+ph*18,0,7);gg.stroke()}
   gg.fillStyle="#9fe7ff";gg.beginPath();gg.moveTo(x,y-r);gg.lineTo(x+r,y);gg.lineTo(x,y+r);gg.lineTo(x-r,y);gg.closePath();gg.fill();
   gg.strokeStyle="rgba(5,10,16,.8)";gg.lineWidth=1;gg.stroke()}
  else{const heimat=m.art==="zuhause",lokal=m.art==="lokal",puls=REDUZIERT?0.5:(Math.sin(K.sek*2.4+m.lat)+1)/2;
   gg.strokeStyle=heimat?"rgba(255,255,255,.9)":lokal?"rgba(127,214,160,.9)":"rgba(255,140,60,.9)";gg.lineWidth=1.5;
   gg.beginPath();gg.arc(x,y,(5+puls*7)*ein,0,7);gg.stroke();
   gg.fillStyle=heimat?"#fff":lokal?"#7fd6a0":"#ff8a3d";gg.beginPath();gg.arc(x,y,3*ein,0,7);gg.fill()}
  belegt.push({x0:x-9,y0:y-9,x1:x+9,y1:y+9});
  if(!m.label||ein<0.6)return;
  if(m.lw===undefined)m.lw=gg.measureText(m.label).width;const w=m.lw,pl=nachricht?6:1,kand=[[x+13,y+4],[x-13-w,y+4],[x+13,y-13],[x-13-w,y-13],[x+13,y+21],[x-13-w,y+21]];
  for(const k of kand){const r={x0:k[0]-pl,y0:k[1]-12,x1:k[0]+w+pl,y1:k[1]+(nachricht?5:3)};
   if(r.x0<6||r.x1>rechts||r.y0<4||r.y1>GH-4)continue;
   if(belegt.some(b=>r.x0<b.x1&&r.x1>b.x0&&r.y0<b.y1&&r.y1>b.y0))continue;
   belegt.push(r);
   if(nachricht){gg.fillStyle="rgba(5,10,16,.78)";gg.fillRect(r.x0,r.y0,r.x1-r.x0,r.y1-r.y0);
    gg.strokeStyle="rgba(159,231,255,.4)";gg.lineWidth=1;gg.strokeRect(r.x0+.5,r.y0+.5,r.x1-r.x0-1,r.y1-r.y0-1);gg.fillStyle="#dff6ff"}
   else gg.fillStyle="rgba(241,230,220,.95)";
   gg.fillText(m.label,k[0],k[1]);break}})}
function boegenZeichnen(K){
 gg.save();gg.lineWidth=1.5;gg.strokeStyle="rgba(255,176,110,.9)";gg.setLineDash([7,5]);gg.lineDashOffset=-(REDUZIERT?0:K.sek*26);
 for(const b of BOEGEN){gg.beginPath();let an=false;
  for(const p of b.pts){const dl=p[2]-K.l0,cl=Math.cos(dl);
   if(K.sp*p[0]+K.cp*p[1]*cl<0.02){an=false;continue}
   const x=K.cx+K.R*p[1]*Math.sin(dl),y=K.cy-K.R*(K.cp*p[0]-K.sp*p[1]*cl);an?gg.lineTo(x,y):gg.moveTo(x,y);an=true}
  gg.stroke()}
 gg.restore();gg.setLineDash([])}
function hudZeichnen(K,a,sek){
 if(a<0.01)return;
 gg.save();gg.globalAlpha=a;
 // Eckklammern der Bühne
 const e=16,l=30;gg.strokeStyle="rgba(255,150,80,.75)";gg.lineWidth=1.6;gg.beginPath();
 gg.moveTo(e,e+l);gg.lineTo(e,e);gg.lineTo(e+l,e);gg.moveTo(GW-e-l,e);gg.lineTo(GW-e,e);gg.lineTo(GW-e,e+l);
 gg.moveTo(e,GH-e-l);gg.lineTo(e,GH-e);gg.lineTo(e+l,GH-e);gg.moveTo(GW-e-l,GH-e);gg.lineTo(GW-e,GH-e);gg.lineTo(GW-e,GH-e-l);gg.stroke();
 // Fadenkreuz im Fokus
 const cx=K.cx,cy=K.cy;gg.strokeStyle="rgba(159,231,255,.95)";gg.lineWidth=1.6;gg.beginPath();
 for(let k=0;k<4;k++){const w=k*Math.PI/2,c=Math.cos(w),s_=Math.sin(w);gg.moveTo(cx+c*10,cy+s_*10);gg.lineTo(cx+c*34,cy+s_*34)}gg.stroke();gg.lineWidth=1.2;
 gg.setLineDash([3,6]);gg.lineDashOffset=-(REDUZIERT?0:sek*8);gg.beginPath();gg.arc(cx,cy,20,0,7);gg.stroke();gg.setLineDash([]);
 gg.fillStyle="rgba(159,231,255,.95)";gg.fillRect(cx-1,cy-1,2,2);
 // Koordinatenzeile
 gg.font="500 12px ui-monospace,Menlo,monospace";gg.textAlign="right";gg.fillStyle="rgba(159,231,255,.95)";
 gg.fillText(koordText(),GW-32,GH-44);gg.textAlign="left";
 gg.restore()}
let RNR=0,FPS=0,FPSN=0,FPST=performance.now(),PUNKTZAHL=0;
// Die Welt (Kugel, Gradnetz, Land, Lichter) ändert sich nur, wenn die Kamera sich bewegt: steht sie, wird sie einmal in einen
// Zwischenspeicher gemalt und nur noch eingeblendet - Marker, Bögen und Kreuz laufen darüber weiter.
const ZWISCHEN=document.createElement("canvas"),zg=ZWISCHEN.getContext("2d");let ZW_SCHLUESSEL="",ZW_STABIL=0,ZW_FERTIG=false;
function weltZeichnen(K){
 const R=K.R,cx=K.cx,cy=K.cy,t=K.t;
 gg.clearRect(0,0,GW,GH);gg.fillStyle="#04070b";gg.fillRect(0,0,GW,GH);
 gg.save();gg.beginPath();gg.rect(0,0,GW,GH);gg.clip();
 const hg=gg.createRadialGradient(cx,cy,R*0.92,cx,cy,R*1.12);hg.addColorStop(0,"rgba(255,120,50,"+(0.22-0.12*HUD).toFixed(3)+")");hg.addColorStop(1,"rgba(255,120,50,0)");
 gg.fillStyle=hg;gg.fillRect(0,0,GW,GH);
 if(HUD>0.02){const cg=gg.createRadialGradient(cx,cy,R*0.95,cx,cy,R*1.1);cg.addColorStop(0,"rgba(120,200,255,"+(0.16*HUD).toFixed(3)+")");cg.addColorStop(1,"rgba(120,200,255,0)");gg.fillStyle=cg;gg.fillRect(0,0,GW,GH)}
 const kg=gg.createRadialGradient(cx,cy,R*.1,cx,cy,R);kg.addColorStop(0,"#0c1a26");kg.addColorStop(1,"#05090e");
 gg.fillStyle=kg;gg.beginPath();gg.arc(cx,cy,R,0,7);gg.fill();gg.strokeStyle="rgba(255,140,70,.35)";gg.lineWidth=1;gg.stroke();
 // Gradnetz, bei Nahsicht dichter
 const gradAbstand=KAM.zoom<2.5?10:KAM.zoom<4.5?5:2.5,schritt=KAM.zoom<2.5?4:2;
 gg.strokeStyle="rgba(120,160,200,"+(KAM.zoom<2.5?0.08:0.07)+")";gg.lineWidth=.6;
 for(let lat=-80;lat<=80;lat+=gradAbstand){if(KAM.zoom>=2.5&&Math.abs(lat-KAM.lat)>50)continue;
  gg.beginPath();let an=false;for(let lo=-180;lo<=180;lo+=schritt){const q=proj(lat,lo,R,cx,cy,KAM.lon,t);if(q[2]>0){an?gg.lineTo(q[0],q[1]):gg.moveTo(q[0],q[1]);an=true}else an=false}gg.stroke()}
 for(let lo=-180;lo<180;lo+=gradAbstand){gg.beginPath();let an=false;for(let lat=-80;lat<=80;lat+=schritt){const q=proj(lat,lo,R,cx,cy,KAM.lon,t);if(q[2]>0){an?gg.lineTo(q[0],q[1]):gg.moveTo(q[0],q[1]);an=true}else an=false}gg.stroke()}
 // Land: nur die Zeilen, die ins Bild reichen
 const stufe=KAM.zoom<1.6?4:KAM.zoom<3?2:1,m=mengeFuer(stufe)||mengeFuer(4)||mengeFuer(2)||mengeFuer(1);
 if(m){const w=Math.min(90,Math.asin(Math.min(1,Math.hypot(GW+2*Math.abs(CXV),GH)/(2*R)))/rad+3);
  const d=klemme(R/300*m.faktor,m.minD,3.6);
  PUNKTZAHL=punkteZeichnen(m,m.land,KAM.lat,w,K,d,"rgba(135,175,215,.7)")+punkteZeichnen(m,m.kueste,KAM.lat,w,K,d*1.05,"rgba(190,228,255,.95)")}
 gg.globalCompositeOperation="lighter";
 for(const c of LICHTER){const q=proj(c[0],c[1],R,cx,cy,KAM.lon,t);if(q[2]>0.05){const r=Math.max(5,Math.min(R*0.016,15))*(0.5+q[2]*.5);const w=gg.createRadialGradient(q[0],q[1],0,q[0],q[1],r);
  w.addColorStop(0,"rgba(255,225,160,.95)");w.addColorStop(.35,"rgba(255,170,70,.35)");w.addColorStop(1,"rgba(255,120,30,0)");gg.fillStyle=w;gg.fillRect(q[0]-r,q[1]-r,r*2,r*2)}}
 gg.globalCompositeOperation="source-over";
 gg.restore()}
function globusRahmen(jetzt){
 requestAnimationFrame(globusRahmen);
 RNR++;
 const gedimmt=BM!=="uebersicht"&&BM!=="globus";
 if(gedimmt&&(RNR&1))return;
 FPSN++;if(jetzt-FPST>=500){FPS=FPSN*1000/(jetzt-FPST);FPSN=0;FPST=jetzt;
  if(DEBUG)$("#debug").textContent="fps "+FPS.toFixed(0)+" · punkte "+PUNKTZAHL+" · zoom "+KAM.zoom.toFixed(2)+" · "+(MASKE_ZUSTAND==="da"?"karte":"umriss")+(ZW_FERTIG?" · ruhend":"")}
 const sek=(jetzt-T0)/1000;
 kameraNachfuehren(jetzt,sek);
 HUD+=((BM==="globus"?1:0)-HUD)*(REDUZIERT?1:0.12);if(Math.abs(HUD)<0.004)HUD=BM==="globus"?HUD:0;
 const cxZiel=BM==="globus"?-LISTE_BREITE/2:0;CXV+=(cxZiel-CXV)*(REDUZIERT?1:0.1);if(Math.abs(CXV-cxZiel)<0.2)CXV=cxZiel;
 const t=KAM.lat*rad,cx=GW/2+CXV,cy=GH/2,R=Math.min(GW*0.46,GH*0.47)*KAM.zoom;
 const K={R:R,cx:cx,cy:cy,t:t,l0:KAM.lon*rad,sp:Math.sin(t),cp:Math.cos(t),sek:sek,jetzt:jetzt};
 const schluessel=[GW,GH,GD,KAM.lat.toFixed(3),KAM.lon.toFixed(3),KAM.zoom.toFixed(3),CXV.toFixed(1),HUD.toFixed(2),LICHTER.length,MASKE_ZUSTAND,Object.keys(MENGEN).length].join("|");
 if(schluessel===ZW_SCHLUESSEL)ZW_STABIL++;else{ZW_SCHLUESSEL=schluessel;ZW_STABIL=0;ZW_FERTIG=false}
 if(ZW_STABIL>=2){
  if(!ZW_FERTIG){if(ZWISCHEN.width!==gl.width||ZWISCHEN.height!==gl.height){ZWISCHEN.width=gl.width;ZWISCHEN.height=gl.height}
   zg.setTransform(GD,0,0,GD,0,0);gg=zg;try{weltZeichnen(K)}finally{gg=HAUPT}ZW_FERTIG=true}
  gg.clearRect(0,0,GW,GH);gg.drawImage(ZWISCHEN,0,0,GW,GH)}
 else weltZeichnen(K);
 gg.save();gg.beginPath();gg.rect(0,0,GW,GH);gg.clip();
 if(GMODUS==="globus"){gg.globalAlpha=BM==="globus"?1:HUD;if(gg.globalAlpha>0.01){boegenZeichnen(K);markerZeichnen(MARKER,K)}gg.globalAlpha=1}
 else if(BM==="uebersicht")markerZeichnen(MARKER_UEB,K);
 hudZeichnen(K,HUD,sek);
 gg.restore()}
// --- Ansichten: Märkte
function sparkSvg(werte,farbe){
 const v=s("svg",{viewBox:"0 0 120 40",preserveAspectRatio:"none",class:"mk-spark"});
 const a=(werte||[]).filter(istZahl);if(a.length<2)return v;
 const mn=Math.min(...a),sp=(Math.max(...a)-mn)||1;
 const pkt=(w,i)=>[i/(a.length-1)*120,36-(w-mn)/sp*32];let d="";
 a.forEach((w,i)=>{const q=pkt(w,i);d+=(i?"L":"M")+q[0].toFixed(1)+" "+q[1].toFixed(1)});
 v.append(s("path",{d:d+"L120 40L0 40Z",fill:farbe,"fill-opacity":.18,stroke:"none"}));
 v.append(s("path",{d:d,fill:"none",stroke:farbe,"stroke-width":1.6,"vector-effect":"non-scaling-stroke","stroke-linejoin":"round"}));
 return v}
function markKarte(k){
 const dez=k.schluessel==="eurusd"?4:(Math.abs(k.wert)>=1000?0:2);
 const a=k.aenderung_prozent,hat=istZahl(a);
 const verl=(Array.isArray(k.verlauf)?k.verlauf:[]).filter(istZahl);
 const steigt=hat?a>=0:(verl.length>1?verl[verl.length-1]>=verl[0]:true);
 const farbe=hat?(steigt?"#7fd6a0":"#ff5a4d"):"#9a8678";
 return h("div",{class:"mk-karte"},h("div",{class:"mk-name"},k.name||k.symbol||""),
  h("div",{class:"mk-wert"},zahl(k.wert,dez),k.einheit?h("small",{},k.einheit):""),
  h("div",{class:"mk-chg "+(hat?(a>=0?"gut":"schlecht"):"leise")},hat?(a>=0?"+":"")+zahl(a,2)+" %":"–"),
  sparkSvg(verl,farbe),h("div",{class:"mk-zeit"},hhmm(k.zeit)))}
function maerkteZeichnen(d){
 $("#mk-titel").textContent=d.titel||"Märkte";$("#mk-zeitraum").textContent=d.zeitraum==="monat"?"Monat":"Heute";
 const kurse=(Array.isArray(d.kurse)?d.kurse:[]).filter(k=>k&&istZahl(k.wert)).slice(0,12);
 $("#mk-gitter").replaceChildren(...(kurse.length?kurse.map(markKarte):[h("div",{class:"lleer"},"Kursdaten gerade nicht verfügbar")]));
 const fuss=[];if(d.stand)fuss.push(d.stand);
 if(Array.isArray(d.fehlend)&&d.fehlend.length)fuss.push("Nicht abrufbar: "+d.fehlend.join(", "));
 $("#mk-fuss").textContent=fuss.join("  ·  ")}
// --- Ansichten: Kennzahlen
function kachelnAusZentrale(z){
 // Wie auf dem Server: ohne eine einzige Buchung oder einen Interessenten wäre jede Zahl eine bloße Null - dann fehlt die Kachel.
 const m=z.monat||{},b=z.bedarf||{},p=z.pipeline||{},k=[];
 const neu=(name,wert,einheit,ziel,text,farbe)=>{if(istZahl(wert))k.push({name:name,wert:wert,einheit:einheit,ziel:istZahl(ziel)&&ziel>0?ziel:null,text:text||"",farbe:farbe||"neutral"})};
 const kasse=[m.einnahmen,m.ausgaben,m.ergebnis,m.zahllast].some(x=>istZahl(x)&&x!==0);
 const stufen=Object.values(p.stufen&&typeof p.stufen==="object"?p.stufen:{}).reduce((s_,x)=>s_+(typeof x==="number"?x:(x&&x.anzahl)||0),0);
 const kunden=stufen>0||[p.gewichtet,p.gesichert,p.offen_wert].some(x=>istZahl(x)&&x!==0);
 const gewinn=b.berechenbar&&istZahl(b.gewinn)&&b.gewinn>0?b.gewinn:null;
 if(kasse){
  if(istZahl(m.ergebnis)){const netto=m.ergebnis-(istZahl(m.zahllast)?m.zahllast:0);
   neu("Ergebnis Monat",m.ergebnis,"€",gewinn,gewinn?Math.round(netto/gewinn*100)+" % vom Bedarf":"Einnahmen minus Ausgaben",m.ergebnis>=0?"gut":"schlecht")}
  neu("Einnahmen Monat",m.einnahmen,"€",null,"brutto");neu("Ausgaben Monat",m.ausgaben,"€",null,"brutto");
  neu("Zahllast",m.zahllast,"€",null,"Umsatzsteuer minus Vorsteuer")}
 if(istZahl(z.belegquote))neu("Belegquote",z.belegquote,"%",100,"der Ausgaben belegt",z.belegquote>=90?"gut":z.belegquote<50?"schlecht":"neutral");
 const noetig=b.berechenbar&&istZahl(b.noetig)&&b.noetig>0?b.noetig:null;
 if(kunden){
  neu("Pipeline gewichtet",p.gewichtet,"€",null,"nach Wahrscheinlichkeit");
  neu("Gesichert je Monat",p.gesichert,"€",noetig,noetig&&istZahl(p.gesichert)?Math.round(p.gesichert/noetig*100)+" % vom nötigen Umsatz":"aus gewonnenen Aufträgen",
   noetig&&istZahl(p.gesichert)?(p.gesichert>=noetig?"gut":"schlecht"):"neutral")}
 neu("Nötiger Umsatz",noetig,"€",null,"je Monat, damit das Private gedeckt ist");
 return k.slice(0,8)}
function kzWert(k){
 if(k.einheit==="€")return zahl(k.wert,Math.abs(k.wert)>=1000?0:2)+" €";
 if(k.einheit==="%")return zahl(k.wert,0)+" %";
 return zahl(k.wert,Number.isInteger(k.wert)?0:1)+(k.einheit?" "+k.einheit:"")}
function kzKachel(k){
 const farbe=k.farbe==="gut"?"gut":k.farbe==="schlecht"?"schlecht":"neutral",kf={gut:"#7fd6a0",schlecht:"#ff5a4d",neutral:"#ff9a52"}[farbe];
 const mitRing=istZahl(k.ziel)&&k.ziel>0;
 const mitte=mitRing?h("div",{class:"kz-ring"},ringSvg(klemme(istZahl(k.anteil)?k.anteil:k.wert/k.ziel,0,1),kf),h("b",{},kzWert(k)))
  :h("div",{class:"kz-zahl"},kzWert(k));
 return h("div",{class:"kz-kachel","data-farbe":farbe},h("div",{class:"kz-name"},k.name||""),mitte,h("div",{class:"kz-text"},k.text||""))}
function kennzahlenZeichnen(d){
 $("#kz-titel").textContent=d.titel||"Kennzahlen";
 let kacheln=Array.isArray(d.kacheln)?d.kacheln:(ZENTRALE?kachelnAusZentrale(ZENTRALE):null);
 kacheln=(kacheln||[]).filter(k=>k&&istZahl(k.wert)).slice(0,8);
 const spalten=kacheln.length<=3?Math.max(1,kacheln.length):kacheln.length<=6?3:4;
 $("#kz-gitter").style.gridTemplateColumns="repeat("+spalten+",minmax(0,1fr))";
 $("#kz-gitter").replaceChildren(...(kacheln.length?kacheln.map(kzKachel):[h("div",{class:"lleer"},ZENTRALE||Array.isArray(d.kacheln)?"Noch keine Kennzahlen":"Kennzahlen werden geladen …")]));
 $("#kz-fuss").textContent=d.stand||""}
// --- Ansichten: Anruf (Telefon)
const PHASEN={vorbereitet:"Vorbereitet",waehlt:"Wählt …",klingelt:"Klingelt",verbunden:"Verbunden",beendet:"Beendet",fehler:"Fehlgeschlagen"};
let KAN={buehne:{},stimme:{},anruf:{},sicht:{},untertitel:{},hochfahren:{}};
function jetztServer(){return(Date.now()+OFFSET)/1000}
function anrufZeit(){
 const d=KAN.anruf||{};let t="";
 if(d.phase==="verbunden"&&istZahl(d.beginn))t=mmss(jetztServer()-d.beginn);
 else if((d.phase==="beendet"||d.phase==="fehler")&&istZahl(d.beginn)&&istZahl(d.ende))t=mmss(d.ende-d.beginn);
 $("#an-zeit").textContent=t}
function anrufErgebnis(d){
 const box=$("#an-ergebnis"),ende=d.phase==="beendet"||d.phase==="fehler",e=d.ergebnis;
 box.className="an-ergebnis";box.replaceChildren();
 if(!ende&&!e)return;
 const kopf=h("div",{class:"kopfzeile"}),zeilen=[];
 if(e&&typeof e==="object"){
  if(e.reserviert){const teile=[];if(e.datum)teile.push(datumKurz(e.datum));if(e.uhrzeit)teile.push(String(e.uhrzeit));
   if(istZahl(e.personen))teile.push(e.personen+(e.personen===1?" Person":" Personen"));
   if(e.name_der_reservierung)teile.push("auf "+e.name_der_reservierung);
   kopf.textContent="✓ Reserviert"+(teile.length?": "+teile.join(" · "):"");box.classList.add("ja")}
  else{kopf.textContent="✕ Nicht reserviert";box.classList.add("nein");
   if(e.gegenvorschlag)zeilen.push(h("div",{class:"unter"},"Gegenvorschlag: "+e.gegenvorschlag))}
  if(e.hinweise)zeilen.push(h("div",{class:"unter"},String(e.hinweise)))}
 else{kopf.textContent=d.phase==="fehler"?"✕ Anruf fehlgeschlagen":"Gespräch beendet";if(d.phase==="fehler")box.classList.add("nein")}
 const klein=[];if(d.grund_ende)klein.push(String(d.grund_ende));if(istZahl(d.kosten_usd))klein.push("≈ "+zahl(d.kosten_usd,2)+" $");
 box.classList.add("da");box.append(kopf,...zeilen);if(klein.length)box.append(h("div",{class:"klein"},klein.join("  ·  ")))}
function anrufZeichnen(){
 const d=KAN.anruf||{},phase=PHASEN[d.phase]?d.phase:"vorbereitet",leer=!d.phase;
 $("#an-sym").dataset.phase=phase;$("#an-phase").dataset.phase=phase;
 $("#an-phasetext").textContent=leer?"Kein Anruf":PHASEN[phase];
 $("#an-chip").textContent=d.anbieter?String(d.anbieter):"";
 $("#an-ziel").textContent=d.ziel&&!leer?String(d.ziel):"";$("#an-nummer").textContent=d.nummer?String(d.nummer):"";
 const ende=phase==="beendet"||phase==="fehler",live=d.mitschrift_live!==false;
 $("#an-kopf").textContent=ende&&!live?"Mitschrift nach Gesprächsende":"Mitschrift";
 $("#an-notiz").textContent=(!live&&phase==="verbunden")?"Die Mitschrift kommt bei diesem Anbieter erst nach dem Gespräch.":"";
 const zeilen=(Array.isArray(d.mitschrift)?d.mitschrift:[]).filter(x=>x&&x.text).slice(-60),box=$("#an-blasen");
 while(box.children.length>zeilen.length)box.lastChild.remove();
 zeilen.forEach((x,i)=>{const klasse="blase "+(x.wer==="jarvis"?"jarvis":"gegenueber")+(x.endgueltig===false?" vorlaeufig":"");
  const kopf=istZahl(x.t)?mmss(x.t):"",text=(x.endgueltig===false?"… ":"")+String(x.text);
  let el=box.children[i];
  if(!el){el=h("div",{class:klasse+(REDUZIERT?"":" neu")},h("small",{},kopf),h("span",{},text));box.append(el)}
  else{el.className=klasse;el.firstChild.textContent=kopf;el.lastChild.textContent=text}});
 box.scrollTop=box.scrollHeight;
 anrufErgebnis(d);anrufZeit()}
// --- Ansichten: Sicht (Erholung, Handruhe, Zusammenhang)
const BAND={gruen:"#7fd6a0",gelb:"#ffd36b",rot:"#ff5a4d"},STUFE={gruen:"Grün",gelb:"Gelb",rot:"Rot"};
function keineDaten(){return h("div",{class:"lleer"},"Noch keine Daten")}
function sichtZeichnen(){
 const d=KAN.sicht||{},obj=x=>x&&typeof x==="object"&&!Array.isArray(x)?x:null,e=obj(d.erholung),hr=obj(d.handruhe),z=obj(d.zusammenhang);
 $("#si-titel").textContent=(BUEHNE_DATEN.modus==="sicht"&&BUEHNE_DATEN.titel)||"Sicht · Erholung";
 const be=$("#si-erholung");
 if(e&&istZahl(e.wert)){be.replaceChildren(h("div",{class:"si-ring"},ringSvg(klemme(e.wert/100,0,1),BAND[e.band]||"#ff9a52"),h("b",{},Math.round(e.wert))),
  h("div",{class:"lnotiz"},[e.quelle,e.tag].filter(Boolean).join(" · ")))}
 else be.replaceChildren(keineDaten());
 const bh=$("#si-handruhe");
 if(hr&&istZahl(hr.mm)){const klein=[];if(istZahl(hr.rauschen_mm))klein.push("Rauschen "+zahl(hr.rauschen_mm,2)+" mm");if(istZahl(hr.fps))klein.push(Math.round(hr.fps)+" fps");
  if(istZahl(hr.rhythmus_hz))klein.push("Rhythmus "+zahl(hr.rhythmus_hz,1)+" Hz");
  bh.replaceChildren(h("div",{class:"si-gross"},zahl(hr.mm,1),h("small",{},"mm")),hr.vergleich?h("div",{class:"lnotiz"},String(hr.vergleich)):"",
   klein.length?h("div",{class:"lnotiz"},klein.join(" · ")):"",hr.tag?h("div",{class:"lnotiz"},String(hr.tag)):"")}
 else bh.replaceChildren(keineDaten());
 const bz=$("#si-zusammenhang"),tab=z&&Array.isArray(z.tabelle)?z.tabelle.filter(r=>r&&typeof r==="object"):[];
 if(z&&tab.length){const q=x=>istZahl(x)?Math.round(x<=1?x*100:x)+" %":"–",n=x=>istZahl(x)?zahl(x,Number.isInteger(x)?0:1):"–";
  bz.replaceChildren(h("table",{class:"si-tabelle"},h("thead",{},h("tr",{},["Stufe","Tage","Termine","Abschluss"].map(t=>h("th",{},t)))),
   h("tbody",{},tab.slice(0,5).map(r=>h("tr",{},h("td",{},h("span",{class:"si-punkt "+(STUFE[r.stufe]?r.stufe:"")}),STUFE[r.stufe]||String(r.stufe||"")),
    h("td",{},n(r.tage)),h("td",{},n(r.termine)),h("td",{},q(r.abschlussquote)))))),
   istZahl(z.n)?h("div",{class:"lnotiz"},"n = "+z.n):"",z.text?h("div",{class:"lnotiz"},String(z.text)):"")}
 else bz.replaceChildren(keineDaten());
 $("#si-fuss").textContent=d.hinweis||"";$("#si-chip").textContent=""}
// --- Ansichten: Untertitel (die letzten vier)
let UT=[];
function untertitelAnwenden(st){
 const d=st.daten||{};if(!d.original&&!d.uebersetzung)return;
 if(st.seit&&jetztServer()-st.seit>600)return;
 UT.push(d);UT=UT.slice(-4);untertitelZeichnen()}
function untertitelZeichnen(){
 const kurz=c=>String(c||"").toUpperCase();
 $("#ut-liste").replaceChildren(...(UT.length?UT.map(d=>h("div",{class:"ut-eintrag "+(d.sprecher==="gast"?"gast":"ich")},
  h("div",{class:"ut-orig"},d.von?h("b",{},kurz(d.von)):"",String(d.original||"")),
  h("div",{class:"ut-neu"},d.nach?h("b",{},kurz(d.nach)):"",String(d.uebersetzung||"")))):[h("div",{class:"lleer"},"Noch kein Untertitel")]));
 const l=UT[UT.length-1];$("#ut-chip").textContent=l&&l.von&&l.nach?kurz(l.von)+" → "+kurz(l.nach):""}
// --- Ansichten: Hochfahren (Schritte im Viertelsekundentakt, Gruß mit 30 Zeichen pro Sekunde)
const HF={n:0,kennung:"",gruss:"",tippAb:0,takt:null,naechster:0};
function hochfahrenAnwenden(d){
 const schritte=(Array.isArray(d.schritte)?d.schritte:[]).filter(x=>x&&x.name).slice(0,16),kennung=schritte.map(x=>x.name).join("|");
 if(schritte.length<HF.n||(HF.kennung&&!kennung.startsWith(HF.kennung))){HF.n=0;HF.tippAb=0}
 HF.kennung=kennung;
 if(String(d.begruessung||"")!==HF.gruss){HF.gruss=String(d.begruessung||"");HF.tippAb=0}
 if(REDUZIERT){HF.n=schritte.length;HF.tippAb=1}
 hochfahrenZeichnen();
 if(!HF.takt)HF.takt=setInterval(hochfahrenTakt,33)}
function hochfahrenTakt(){
 const d=KAN.hochfahren||{},alle=(Array.isArray(d.schritte)?d.schritte:[]).filter(x=>x&&x.name).slice(0,16),jetzt=Date.now();
 let neu=false;
 if(HF.n<alle.length&&jetzt>=HF.naechster){HF.n++;HF.naechster=jetzt+250;neu=true}
 if(HF.n>=alle.length&&HF.gruss&&!HF.tippAb)HF.tippAb=jetzt;
 const fertig=HF.n>=alle.length&&(!HF.gruss||(HF.tippAb&&getippt()>=HF.gruss.length));
 if(neu||HF.n<alle.length||!fertig)hochfahrenZeichnen();
 if(fertig&&HF.takt){hochfahrenZeichnen();clearInterval(HF.takt);HF.takt=null}}
function getippt(){if(!HF.tippAb)return 0;if(REDUZIERT||HF.tippAb===1)return HF.gruss.length;return Math.min(HF.gruss.length,Math.floor((Date.now()-HF.tippAb)/1000*30))}
function hochfahrenZeichnen(){
 const d=KAN.hochfahren||{},alle=(Array.isArray(d.schritte)?d.schritte:[]).filter(x=>x&&x.name).slice(0,16);
 const gezeigt=alle.slice(0,Math.min(HF.n,alle.length));
 $("#hf-schritte").replaceChildren(...gezeigt.map(x=>h("li",{class:x.ok===true?"ok":x.ok===false?"nein":"offen"},
  h("span",{},x.ok===true?"✓":x.ok===false?"✕":"–"),h("span",{},String(x.name),x.text?h("small",{}," · "+kuerzen(x.text,90)):""))));
 const anteil=alle.length?gezeigt.length/alle.length:0,fertig=!!d.fertig&&gezeigt.length>=alle.length;
 $("#hf-ring").replaceChildren(ringSvg(fertig?1:anteil,"#ff9a52"),h("b",{},alle.length?Math.round((fertig?1:anteil)*100)+" %":"–"));
 const text=HF.gruss?HF.gruss.slice(0,getippt()):"";
 const g=$("#hf-gruss");g.textContent=text;g.classList.toggle("fertig",!!HF.gruss&&text.length>=HF.gruss.length);
 $("#hf-chip").textContent=fertig?"bereit":(alle.length?"läuft":"")}
// --- Ansichten: Recherche (nur Text, nie als Seite eingesetzt)
function rechercheZeichnen(d){
 $("#re-titel").textContent=d.titel||"Recherche";
 const abs=(Array.isArray(d.absaetze)?d.absaetze:[]).slice(0,6).map(t=>kuerzen(t,400)).filter(Boolean);
 const lst=(Array.isArray(d.liste)?d.liste:[]).slice(0,10).filter(x=>x&&(x.titel||x.text));
 const leer=!abs.length&&!lst.length;
 $("#re-absaetze").replaceChildren(...(leer?[h("div",{class:"lleer"},"Keine Inhalte")]:abs.map(t=>h("p",{},t))));
 $("#re-liste").replaceChildren(...lst.map(x=>h("li",{},x.titel?h("b",{},kuerzen(x.titel,120)):"",x.text?h("span",{},kuerzen(x.text,300)):"")));
 $("#re-wurzel").classList.toggle("zwei",abs.length>0&&lst.length>0);
 $("#re-absaetze").style.display=(abs.length||leer)?"":"none";$("#re-liste").style.display=lst.length?"":"none";
 const q=(Array.isArray(d.quellen)?d.quellen:[]).slice(0,5).filter(x=>x&&(x.titel||x.url));
 $("#re-quellen").replaceChildren(...(q.length?[h("b",{},"Quellen"),...q.map((x,i)=>(i?"  ·  ":"")+[kuerzen(x.titel||"",60),hostname(x.url)].filter(Boolean).join(" – "))]:[]));
 $("#re-fuss").textContent=d.stand||""}
// --- Ansichten: Inhalte (Redaktionsplan)
function inhalteZeichnen(d){
 $("#in-titel").textContent=d.titel||"Inhalte";
 const e=(Array.isArray(d.eintraege)?d.eintraege:[]).slice(0,20).filter(x=>x&&typeof x==="object");
 $("#in-box").replaceChildren(e.length?h("table",{class:"in-tabelle"},h("thead",{},h("tr",{},["Datum","Plattform","Titel","Status"].map(t=>h("th",{},t)))),
  h("tbody",{},e.map(x=>h("tr",{},h("td",{},datumKurz(x.datum)),h("td",{},String(x.plattform||"")),h("td",{},kuerzen(x.titel||"",90)),
   h("td",{},h("span",{class:"in-status "+String(x.status||"").replace(/[^a-z]/gi,"").toLowerCase()},String(x.status||"")))))))
  :h("div",{class:"lleer"},"Noch nichts geplant"));
 $("#in-fuss").textContent=d.stand||""}
// --- Die Bühne: welche Ansicht gilt, Überblendung, Themenfolge, Ablauf
const EBENEN=["maerkte","kennzahlen","anruf","sicht","untertitel","hochfahren","recherche","inhalte"];
const BUEHNE_MODI=["uebersicht","globus"].concat(EBENEN);
let BUEHNE_DATEN={modus:"uebersicht"},FOLGE=null,ABLAUF=null,FOLGETAKT=null;
const ZEICHNER={maerkte:maerkteZeichnen,kennzahlen:kennzahlenZeichnen,recherche:rechercheZeichnen,inhalte:inhalteZeichnen,
 anruf:()=>anrufZeichnen(),sicht:()=>sichtZeichnen(),untertitel:()=>untertitelZeichnen(),hochfahren:()=>hochfahrenZeichnen()};
function ansichtZeigen(d){
 d=d&&typeof d==="object"?d:{};
 const modus=BUEHNE_MODI.includes(d.modus)?d.modus:"uebersicht";
 BUEHNE_DATEN=Object.assign({},d,{modus:modus});BM=modus;
 $("#buehne").dataset.modus=modus;$("#haupt").dataset.modus=modus;
 document.querySelectorAll(".lage").forEach(l=>l.classList.toggle("aktiv",l.dataset.lage===modus));
 if(ZEICHNER[modus]){try{ZEICHNER[modus](BUEHNE_DATEN)}catch(e){console.error(e)}}
 if(modus==="globus")globusSetzen(d);else if(modus==="uebersicht")globusSetzen(null)}
function folgePunkte(){
 const box=$("#folgepunkte");
 if(!FOLGE){box.classList.remove("an");box.replaceChildren();return}
 box.classList.add("an");
 box.replaceChildren(...FOLGE.schritte.map((x,i)=>h("i",{class:i===FOLGE.i?"dran":i<FOLGE.i?"fertig":""})),h("span",{},(FOLGE.i+1)+" / "+FOLGE.schritte.length))}
function folgeSchritt(i){FOLGE.i=i;FOLGE.ab=Date.now();ansichtZeigen(FOLGE.schritte[i].ansicht);folgePunkte()}
function folgeTakt(){
 const f=FOLGE;if(!f||f.i>=f.schritte.length-1)return;const jetzt=Date.now();
 // Vor dem ersten neuen Stimme-Ereignis hält Schritt 1 (höchstens 90 s), danach läuft der Zeitgeber je Schritt.
 if(!f.laeuft){if(jetzt>=f.halteBis){f.laeuft=true;folgeSchritt(f.i+1)}return}
 if(jetzt-f.ab>=f.max*1000)folgeSchritt(f.i+1)}
function folgeStarten(d,st){
 const schritte=(Array.isArray(d.schritte)?d.schritte:[]).filter(x=>x&&typeof x==="object"&&x.ansicht&&typeof x.ansicht==="object"&&x.ansicht.modus!=="folge").slice(0,8);
 if(!schritte.length){ansichtZeigen({modus:"uebersicht"});return}
 FOLGE={schritte:schritte,max:klemme(Number(d.max_s_je_schritt)||30,10,60),i:0,seit:istZahl(st.seit)?st.seit:0,laeuft:false,ab:Date.now(),halteBis:Date.now()+90000};
 folgeSchritt(0);FOLGETAKT=setInterval(folgeTakt,500)}
function stimmeAnwenden(st){
 const d=st.daten||{},f=FOLGE;
 if(!f||(d.art!=="pegel"&&d.art!=="satz")||!(st.seit>=f.seit))return;
 if(!f.laeuft){f.laeuft=true;f.ab=Date.now()}
 if(f.i<f.schritte.length-1&&stichwortTrifft(d.text,f.schritte[f.i+1].stichwort))folgeSchritt(f.i+1)}
function zurUebersicht(){FOLGE=null;if(FOLGETAKT){clearInterval(FOLGETAKT);FOLGETAKT=null}folgePunkte();ansichtZeigen({modus:"uebersicht"})}
function buehneAnwenden(st){
 clearTimeout(ABLAUF);ABLAUF=null;
 if(FOLGETAKT){clearInterval(FOLGETAKT);FOLGETAKT=null}
 FOLGE=null;folgePunkte();
 const d=st.daten||{};
 if(st.bis>0){const rest=st.bis*1000-(Date.now()+OFFSET);
  if(rest<=0){zurUebersicht();return}
  ABLAUF=setTimeout(zurUebersicht,Math.min(rest,2000000000))}
 if(d.modus==="folge"&&Array.isArray(d.schritte))folgeStarten(d,st);else ansichtZeigen(d)}
// --- Die eine Langabfrage für alle sechs Kanäle
const KANAELE=["buehne","stimme","anruf","sicht","untertitel","hochfahren"];
const VERSION={};KANAELE.forEach(k=>VERSION[k]=-1);let START=null,OFFSET=0,LAUSCHT=false;
function kanalAnwenden(k,st){
 const d=st.daten||{};
 if(k==="buehne")buehneAnwenden(st);
 else if(k==="stimme")stimmeAnwenden(st);
 else{KAN[k]=d;
  if(k==="untertitel")untertitelAnwenden(st);
  else if(k==="anruf")anrufZeichnen();
  else if(k==="sicht")sichtZeichnen();
  else if(k==="hochfahren")hochfahrenAnwenden(d)}}
async function lauschen(){
 if(LAUSCHT)return;LAUSCHT=true;
 for(;;){
  try{
   const nach=KANAELE.map(k=>k+":"+VERSION[k]).join(","),abbruch=new AbortController(),uhr_=setTimeout(()=>abbruch.abort(),35000);
   let antwort;
   try{antwort=await fetch("/api/anzeige?nach="+encodeURIComponent(nach)+"&warten=20"+(SCHLUESSEL?"&schluessel="+encodeURIComponent(SCHLUESSEL):""),
    {cache:"no-store",signal:abbruch.signal})}finally{clearTimeout(uhr_)}
   if(!antwort.ok)throw new Error("HTTP "+antwort.status);
   const d=await antwort.json();if(!d||!d.ok)throw new Error("Antwort");
   if(istZahl(d.jetzt))OFFSET=d.jetzt*1000-Date.now();
   // Neustart des Servers: alle Zähler fangen von vorn an, die Versionen auch.
   if(START!==null&&d.start!==START){START=d.start;KANAELE.forEach(k=>VERSION[k]=-1);continue}
   START=d.start;
   const kan=d.kanaele||{};
   for(const k of KANAELE){const st=kan[k];if(!st)continue;VERSION[k]=st.version;
    try{kanalAnwenden(k,st)}catch(e){console.error(e)}}
  }catch(e){await new Promise(f=>setTimeout(f,3000))}}}
setInterval(anrufZeit,500);
// --- Daten der Übersicht
function anzeigen(d){
 ZENTRALE=d;
 $("#datum").textContent=(d.wochentag||"")+" "+(d.datum||"")+(d.ort?" · "+d.ort:"");
 const z=(d.status&&d.status.zustand)||"bereit";$("#chip").dataset.z=z;$("#chiptext").textContent=ZUSTAND[z]||z;
 const ap=d.autopilot||{};$("#apchip").className="chip"+(ap.an?"":" aus");
 $("#aptext").textContent=ap.an?(ap.arbeitet_an?"Autopilot: "+ap.arbeitet_an.slice(0,40):"Autopilot an · "+ap.postfach+" im Postfach"):"Autopilot aus";
 const m=d.monat||{},mm=(m.von||"").slice(0,7);$("#monatname").textContent=mm;
 // Gewinn gegen den nötigen Gewinn - nicht gegen den nötigen Umsatz, sonst zählen die Firmenkosten doppelt.
 const bedarf=d.bedarf&&d.bedarf.berechenbar&&d.bedarf.gewinn>0?d.bedarf.gewinn:0;
 $("#ringe").replaceChildren(
  ring(bedarf?((m.ergebnis||0)-(m.zahllast||0))/bedarf:(m.einnahmen?Math.max(0,(m.ergebnis||0)/m.einnahmen):0),bedarf?"vom Bedarf":"Marge",euro(m.ergebnis||0)),
  ring((d.belegquote||0)/100,"Belege",d.belegquote==null?"–":Math.round(d.belegquote)+" %","#7fd6a0"),
  ring((d.pipeline&&d.pipeline.offen_wert)?(d.pipeline.gewichtet/d.pipeline.offen_wert):0,"Chance",euro(d.pipeline?d.pipeline.gewichtet:0)),
  ring(Math.min(1,(ap.postfach||0)/10),"Postfach",String(ap.postfach||0),"#ffd9b8"));
 const g=d.gehirne||{},lim=d.limit||0;
 $("#denkensumme").textContent=(g.anfragen||0)+" Anfragen";
 $("#denken").replaceChildren(balken("Gemini · schnell",g.gemini||0,Math.max(g.gemini||0,g.claude||0,1),String(g.gemini||0)),
  balken("Claude · gründlich",g.claude||0,Math.max(g.gemini||0,g.claude||0,1),String(g.claude||0)),
  ...(lim>0?[balken("Kosten vom Limit",g.kosten||0,lim,(g.kosten||0).toFixed(2).replace(".",",")+" €")]:[]));
 const n=d.nachfassen||[];$("#nachzahl").textContent=n.length||"";
 liste($("#nachfassen"),n.map(e=>zeile(e.firma,(e.tage>0?e.tage+" T überfällig":"heute")+" · "+euro(e.wert))),"Heute ist niemand fällig");
 verlauf(d.verlauf);
 const p=d.pipeline||{};$("#pipewert").textContent=euro(p.offen_wert||0);
 const st=p.stufen||{};const namen=Object.keys(st);const mx=Math.max(1,...namen.map(k=>typeof st[k]==="number"?st[k]:(st[k]&&st[k].anzahl)||0));
 $("#pipeline").replaceChildren(...(namen.length?namen.map(k=>{const a=typeof st[k]==="number"?st[k]:(st[k]&&st[k].anzahl)||0;return balken(k,a,mx,String(a))}):[h("span",{class:"leer"},"Noch keine Interessenten")]));
 const feed=[];(ap.letzte||[]).forEach(e=>feed.push(zeile((e.status==="fehler"?"✕ ":"✓ ")+e.titel,alter(e.zeit))));
 (d.protokoll||[]).forEach(a=>feed.push(zeile(a.werkzeug.replace(/_/g," ")+(a.status&&a.status!=="ok"?" ("+a.status+")":""),alter(a.zeit))));
 $("#aktzahl").textContent=(d.statistik&&d.statistik.aktionen)||"";liste($("#feed"),feed.slice(0,9),"Noch nichts getan");
 $("#briefing").replaceChildren(...(d.briefing||[]).map(t=>h("p",{},t)));
 const neueOrte=d.orte||[],kennung=JSON.stringify(neueOrte);
 if(kennung!==anzeigen.orte){anzeigen.orte=kennung;ORTE=neueOrte;
  MARKER_UEB=markerBauen(ORTE.map(o=>({lat:o.lat,lon:o.lon,art:o.art,label:String(o.name||"").toUpperCase()})),null)}
 const lagen=[];lagen.push((d.nutzer?d.nutzer+" · ":"")+(d.firma||"Betrieb"));
 if(m.einnahmen!=null)lagen.push("Einnahmen "+euro(m.einnahmen)+" · Ausgaben "+euro(m.ausgaben)+" · Zahllast "+euro(m.zahllast));
 (d.briefing||[]).forEach(t=>lagen.push(t));lagen.push("Jarvis ist da");
 $("#ticker").textContent=lagen.join("   ◆   ");
 // Die Kennzahlen ohne eigene Kacheln bauen sich aus diesem Stand.
 if(BM==="kennzahlen"&&!Array.isArray(BUEHNE_DATEN.kacheln))kennzahlenZeichnen(BUEHNE_DATEN);
}
async function holen(p){const r=await fetch(p+ANHANG);return r.json()}
async function lade(){try{anzeigen(await holen("/api/zentrale"))}catch(e){$("#ticker").textContent="Der Stand ist gerade nicht erreichbar"}}
async function status(){try{const s=await holen("/api/status");const z=s.zustand||"bereit";$("#chip").dataset.z=z;$("#chiptext").textContent=ZUSTAND[z]||z}catch(e){}}
fetch("/api/lichter"+ANHANG).then(r=>r.json()).then(l=>{LICHTER=l.lichter||[]}).catch(()=>{});
if(DEBUG)$("#debug").style.display="block";
untertitelZeichnen();
lade();setInterval(lade,15000);setInterval(status,2000);requestAnimationFrame(globusRahmen);lauschen();
</script></body></html>
"""


def lichter_liste() -> list:
    """Die leuchtenden Großstädte für das Nachtbild des Globus."""
    return [list(ORTE[o]) for o in LICHTER if o in ORTE]
