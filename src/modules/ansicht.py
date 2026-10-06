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
    return {"zustand": status.get("zustand", "bereit"), "satz": status.get("satz", ""),
            "seit": status.get("seit", 0), "jetzt": status["jetzt"],
            "aktionen": [{"id": a["id"], "werkzeug": a["werkzeug"], "status": a["status"], "zeit": a["zeit"]}
                         for a in aktionen]}


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
main{display:grid;grid-template-columns:minmax(260px,24%) minmax(0,1fr) minmax(280px,27%);gap:12px;min-height:0}
.spalte{display:flex;flex-direction:column;gap:12px;min-height:0;overflow:hidden}
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
.mitte{display:flex;flex-direction:column;gap:12px;min-height:0}
.globus{position:relative;flex:1;min-height:0;border:1px solid var(--linie);border-radius:4px;overflow:hidden;background:#05080d}
.globus canvas{position:absolute;inset:0;width:100%;height:100%}
.briefing{position:absolute;left:14px;top:12px;z-index:2;max-width:46%}
.briefing h2{font:600 10px var(--mono);letter-spacing:.3em;color:var(--glut);text-transform:uppercase;margin-bottom:6px}
.briefing p{font:500 12px var(--sans);color:var(--text);margin-bottom:4px;text-shadow:0 1px 6px #000}
.briefing p::before{content:"▸ ";color:var(--orange)}
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
@media (max-width:1000px){body{overflow:auto}main{grid-template-columns:1fr}.globus{min-height:340px}html,body{overflow:auto;height:auto}}
@media (prefers-reduced-motion:reduce){.ticker div{animation:none;padding-left:0}}
</style></head><body>
<header class="kopf"><h1>Jarvis · Zentrale</h1><span class="chip" id="chip" data-z="bereit"><i></i><span id="chiptext">bereit</span></span>
<span class="chip aus" id="apchip"><i></i><span id="aptext">Autopilot aus</span></span><span class="platz"></span>
<span class="datum" id="datum"></span><span class="uhr" id="uhr">--:--</span></header>
<main>
 <section class="spalte">
  <div class="feld"><h2>Betrieb <span id="monatname"></span></h2><div class="ringe" id="ringe"></div></div>
  <div class="feld"><h2>Denken <span id="denkensumme"></span></h2><div id="denken"></div></div>
  <div class="feld" style="flex:1"><h2>Nachfassen <span id="nachzahl"></span></h2><ul class="liste" id="nachfassen"></ul></div>
 </section>
 <section class="mitte">
  <div class="globus"><canvas id="globus"></canvas>
   <div class="briefing"><h2>Briefing</h2><div id="briefing"></div></div></div>
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
function h(t,p,...k){const e=document.createElement(t);for(const a in(p||{})){if(a==="class")e.className=p[a];else e.setAttribute(a,p[a])}
 k.flat().forEach(x=>{if(x!=null)e.append(x.nodeType?x:document.createTextNode(String(x)))});return e}
const euro=n=>(typeof n==="number"?n:0).toLocaleString("de-DE",{maximumFractionDigits:0})+" €";
const NS="http://www.w3.org/2000/svg";function s(t,a){const e=document.createElementNS(NS,t);for(const k in a)e.setAttribute(k,a[k]);return e}
// --- Uhr
function uhr(){const d=new Date();$("#uhr").textContent=d.toLocaleTimeString("de-DE",{hour:"2-digit",minute:"2-digit"})}uhr();setInterval(uhr,10000);
// --- Ringe
function ring(wert,name,text,farbe){const r=40,u=2*Math.PI*r,f=Math.max(0,Math.min(1,wert||0));
 const v=s("svg",{viewBox:"0 0 100 100"});v.append(s("circle",{cx:50,cy:50,r:r,fill:"none",stroke:"rgba(255,140,70,.14)","stroke-width":7}));
 const c=s("circle",{cx:50,cy:50,r:r,fill:"none",stroke:farbe||"#ff6a1f","stroke-width":7,"stroke-linecap":"round",
  "stroke-dasharray":(u*f).toFixed(1)+" "+(u).toFixed(1),transform:"rotate(-90 50 50)"});v.append(c);
 for(let i=0;i<40;i++){const w=i/40*Math.PI*2,x1=50+46*Math.cos(w),y1=50+46*Math.sin(w),x2=50+(i%5?48:50)*Math.cos(w),y2=50+(i%5?48:50)*Math.sin(w);
  v.append(s("line",{x1:x1,y1:y1,x2:x2,y2:y2,stroke:"rgba(255,140,70,.35)","stroke-width":.6}))}
 return h("div",{class:"ring"},v,h("b",{},text),h("small",{},name))}
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
// --- Globus: gezeichnete Umrisse als Punktraster
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
const PUNKTE=[];(function(){for(let lat=-80;lat<=82;lat+=0.95){const schritt=0.95/Math.max(0.25,Math.cos(lat*Math.PI/180));
 for(let lon=-180;lon<180;lon+=schritt){const pt=[lon,lat];if(LAND.some(p=>innen(pt,p))&&!MEER.some(p=>innen(pt,p))){const pr=lat*Math.PI/180;PUNKTE.push([Math.sin(pr),Math.cos(pr),lon*Math.PI/180])}}}})();
let ORTE=[],LICHTER=[];const gl=$("#globus"),gg=gl.getContext("2d");let GW=0,GH=0,GD=1;
function gresize(){const b=gl.parentElement.getBoundingClientRect();GD=Math.min(2,devicePixelRatio||1);GW=b.width;GH=b.height;gl.width=GW*GD;gl.height=GH*GD;gg.setTransform(GD,0,0,GD,0,0)}
addEventListener("resize",gresize);gresize();
const rad=Math.PI/180;let lon0=15,gz=0;const T0=performance.now();
function proj(lat,lon,R,cx,cy,l0,t){const p=lat*rad,l=(lon-l0)*rad,cp=Math.cos(t),sp=Math.sin(t);
 const x=Math.cos(p)*Math.sin(l),y=cp*Math.sin(p)-sp*Math.cos(p)*Math.cos(l),sicht=sp*Math.sin(p)+cp*Math.cos(p)*Math.cos(l);
 return[cx+R*x,cy-R*y,sicht]}
function winkel(a,b){const p1=a[0]*rad,p2=b[0]*rad,dl=(b[1]-a[1])*rad;return Math.acos(Math.max(-1,Math.min(1,Math.sin(p1)*Math.sin(p2)+Math.cos(p1)*Math.cos(p2)*Math.cos(dl))))/rad}
function globus(jetzt){const sek=(jetzt-T0)/1000,ruhig=window.matchMedia("(prefers-reduced-motion: reduce)").matches;
 // Der Blick liegt auf dem Betrieb, so nah, dass seine Kunden sichtbar werden; ohne Orte dreht sich die Erde.
 const heim=ORTE.find(o=>o.art==="zuhause")||ORTE[0];let fokusLat=24,fokusLon=15+(ruhig?0:sek*3.5),zoom=1;
 if(heim){const w=Math.max(0,...ORTE.map(o=>winkel([heim.lat,heim.lon],[o.lat,o.lon])));
  fokusLat=heim.lat;fokusLon=heim.lon+(ruhig?0:Math.sin(sek*0.17)*7);zoom=w<12?1.55:w<30?1.35:w<60?1.15:1}
 const t=fokusLat*rad,cx=GW/2,cy=GH/2,R=Math.min(GW*0.46,GH*0.47)*zoom;gg.clearRect(0,0,GW,GH);
 gg.fillStyle="#04070b";gg.fillRect(0,0,GW,GH);
 gg.save();gg.beginPath();gg.rect(0,0,GW,GH);gg.clip();
 const hg=gg.createRadialGradient(cx,cy,R*0.92,cx,cy,R*1.12);hg.addColorStop(0,"rgba(255,120,50,.22)");hg.addColorStop(1,"rgba(255,120,50,0)");gg.fillStyle=hg;gg.fillRect(0,0,GW,GH);
 const kg=gg.createRadialGradient(cx,cy,R*.1,cx,cy,R);kg.addColorStop(0,"#0c1a26");kg.addColorStop(1,"#05090e");
 gg.fillStyle=kg;gg.beginPath();gg.arc(cx,cy,R,0,7);gg.fill();gg.strokeStyle="rgba(255,140,70,.35)";gg.lineWidth=1;gg.stroke();
 gg.strokeStyle="rgba(120,160,200,.08)";gg.lineWidth=.6;
 for(let lat=-60;lat<=80;lat+=10){gg.beginPath();let an=false;for(let lo=-180;lo<=180;lo+=4){const q=proj(lat,lo,R,cx,cy,fokusLon,t);if(q[2]>0){an?gg.lineTo(q[0],q[1]):gg.moveTo(q[0],q[1]);an=true}else an=false}gg.stroke()}
 for(let lo=-180;lo<180;lo+=10){gg.beginPath();let an=false;for(let lat=-80;lat<=80;lat+=4){const q=proj(lat,lo,R,cx,cy,fokusLon,t);if(q[2]>0){an?gg.lineTo(q[0],q[1]):gg.moveTo(q[0],q[1]);an=true}else an=false}gg.stroke()}
 const d=Math.min(3.6,Math.max(1.7,R/300)),l0=fokusLon*rad,cp=Math.cos(t),sp=Math.sin(t);gg.fillStyle="rgba(135,175,215,.7)";gg.beginPath();
 for(const p of PUNKTE){const dl=p[2]-l0,cl=Math.cos(dl),sicht=sp*p[0]+cp*p[1]*cl;if(sicht<0.02)continue;
  const x=cx+R*p[1]*Math.sin(dl),y=cy-R*(cp*p[0]-sp*p[1]*cl);if(x<-8||x>GW+8||y<-8||y>GH+8)continue;const e=d*(0.55+sicht*.55);gg.rect(x-e/2,y-e/2,e,e)}gg.fill();
 gg.globalCompositeOperation="lighter";
 for(const c of LICHTER){const q=proj(c[0],c[1],R,cx,cy,fokusLon,t);if(q[2]>0.05){const r=Math.max(5,R*0.016)*(0.5+q[2]*.5);const w=gg.createRadialGradient(q[0],q[1],0,q[0],q[1],r);
  w.addColorStop(0,"rgba(255,225,160,.95)");w.addColorStop(.35,"rgba(255,170,70,.35)");w.addColorStop(1,"rgba(255,120,30,0)");gg.fillStyle=w;gg.fillRect(q[0]-r,q[1]-r,r*2,r*2)}}
 gg.globalCompositeOperation="source-over";
 const belegt=[];ORTE.slice().sort((a,b)=>(a.art==="zuhause"?0:1)-(b.art==="zuhause"?0:1)).forEach(o=>{
  const q=proj(o.lat,o.lon,R,cx,cy,fokusLon,t);if(q[2]<=0.05)return;const puls=(Math.sin(sek*2.4+o.lat)+1)/2,heimat=o.art==="zuhause";
  gg.strokeStyle=heimat?"rgba(255,255,255,.9)":"rgba(255,140,60,.9)";gg.lineWidth=1.5;gg.beginPath();gg.arc(q[0],q[1],5+puls*7,0,7);gg.stroke();
  gg.fillStyle=heimat?"#fff":"#ff8a3d";gg.beginPath();gg.arc(q[0],q[1],3,0,7);gg.fill();
  if(!belegt.some(b=>Math.abs(b[0]-q[0])<80&&Math.abs(b[1]-q[1])<16)){belegt.push([q[0],q[1]]);
   gg.fillStyle="rgba(241,230,220,.95)";gg.font="600 11px ui-monospace,Menlo,monospace";gg.fillText(o.name.toUpperCase(),q[0]+11,q[1]+4)}});
 gg.restore();requestAnimationFrame(globus)}
// --- Daten
function anzeigen(d){
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
 ORTE=d.orte||[];
 const lagen=[];lagen.push((d.nutzer?d.nutzer+" · ":"")+(d.firma||"Betrieb"));
 if(m.einnahmen!=null)lagen.push("Einnahmen "+euro(m.einnahmen)+" · Ausgaben "+euro(m.ausgaben)+" · Zahllast "+euro(m.zahllast));
 (d.briefing||[]).forEach(t=>lagen.push(t));lagen.push("Jarvis ist da");
 $("#ticker").textContent=lagen.join("   ◆   ");
}
async function holen(p){const r=await fetch(p+ANHANG);return r.json()}
async function lade(){try{anzeigen(await holen("/api/zentrale"))}catch(e){$("#ticker").textContent="Der Stand ist gerade nicht erreichbar"}}
async function status(){try{const s=await holen("/api/status");const z=s.zustand||"bereit";$("#chip").dataset.z=z;$("#chiptext").textContent=ZUSTAND[z]||z}catch(e){}}
fetch("/api/lichter"+ANHANG).then(r=>r.json()).then(l=>{LICHTER=l.lichter||[]}).catch(()=>{});
lade();setInterval(lade,15000);setInterval(status,2000);requestAnimationFrame(globus);
</script></body></html>
"""


def lichter_liste() -> list:
    """Die leuchtenden Großstädte für das Nachtbild des Globus."""
    return [list(ORTE[o]) for o in LICHTER if o in ORTE]
