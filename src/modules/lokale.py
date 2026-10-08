#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Lokale in der Nähe - Restaurants aus OpenStreetMap, mit Telefon und Öffnungszeiten.

Gesucht wird auf der freien Karte (Overpass, ODbL): ohne Schlüssel, ohne
Anmeldung. Zuerst wird der Ort in Koordinaten übersetzt, dann holt die Abfrage
alle Restaurants mit Namen im Umkreis, gefiltert nach der Küche. Gefunden wird
nur, was auf der Karte eingetragen ist: Telefonnummer und Öffnungszeiten sind
Angaben von Mitwirkenden und können veraltet sein. Nichts davon wird erfunden
oder ergänzt - fehlt etwas, bleibt das Feld leer, und der Text sagt es.

Das Modul legt **keine Interessenten** an und liest weder Kontakte noch
Kalender. Die Texte aus der Karte sind fremde Inhalte (jeder kann sie
bearbeiten): Steuerzeichen fallen weg, alles wird gekürzt, und niemand führt
etwas daraus aus.

Das Ergebnis dient als Vorbereitung für den Telefonassistenten: ``telefon`` ist
schon in der internationalen Form (``+43...``), wie sie ``nummer_pruefen``
verlangt.
"""

import json
import math
import re
import time

import config
from modules.telefon import nummer_pruefen

# Küche -> regulärer Ausdruck für das Merkmal "cuisine" (Teiltreffer, Groß/Klein egal).
# OpenStreetMap trennt mehrere Küchen mit ";" (etwa "chinese;thai"), darum genügt ein Teiltreffer.
KUECHEN = {
    "asiatisch": "asian|chinese|japanese|thai|vietnamese|sushi|korean|ramen|indonesian|"
                 "malaysian|taiwanese|cantonese|sichuan|nepalese|indian",
    "chinesisch": "chinese|cantonese|sichuan",
    "japanisch": "japanese|sushi|ramen",
    "thai": "thai",
    "vietnamesisch": "vietnamese",
    "indisch": "indian|nepalese",
    "italienisch": "italian|pizza",
    "oesterreichisch": "austrian|regional",
    "griechisch": "greek",
    "tuerkisch": "turkish|kebab",
    "egal": "",
}

# Wie die Küche im Satz klingt: (Mehrzahl, Einzahl).
LOKALE_KUECHE_WORT = {
    "asiatisch": ("asiatische Lokale", "asiatisches Lokal"),
    "chinesisch": ("chinesische Lokale", "chinesisches Lokal"),
    "japanisch": ("japanische Lokale", "japanisches Lokal"),
    "thai": ("Thai-Lokale", "Thai-Lokal"),
    "vietnamesisch": ("vietnamesische Lokale", "vietnamesisches Lokal"),
    "indisch": ("indische Lokale", "indisches Lokal"),
    "italienisch": ("italienische Lokale", "italienisches Lokal"),
    "oesterreichisch": ("österreichische Lokale", "österreichisches Lokal"),
    "griechisch": ("griechische Lokale", "griechisches Lokal"),
    "tuerkisch": ("türkische Lokale", "türkisches Lokal"),
    "egal": ("Lokale", "Lokal"),
}

# Gängige andere Schreibweisen, falls das Modell nicht den Aufzählungswert nennt.
LOKALE_KUECHE_ALIAS = {
    "asian": "asiatisch", "chinese": "chinesisch", "japanese": "japanisch",
    "sushi": "japanisch", "vietnamese": "vietnamesisch", "indian": "indisch",
    "italian": "italienisch", "pizza": "italienisch", "austrian": "oesterreichisch",
    "greek": "griechisch", "turkish": "tuerkisch", "kebab": "tuerkisch",
    "alle": "egal", "beliebig": "egal", "any": "egal", "jede": "egal",
}

LOKALE_QUELLE = "OpenStreetMap (ODbL)"
LOKALE_MAX = 10             # so viele Lokale kommen höchstens zurück
LOKALE_ABFRAGE_ANZAHL = 150  # so viele holt die Karte: "out N" liefert NICHT die nächsten zuerst
LOKALE_ERGEBNIS_GRENZE = 5200  # Werkzeugergebnisse bleiben unter 5500 Zeichen JSON
LOKALE_DOPPELT_M = 20       # gleicher Name näher als das = derselbe Laden (Punkt + Gebäude)

# Landesvorwahl je Land, nur wo die führende 0 einer Inlandsnummer wegfällt.
# Der Ort der Suche bestimmt, wie eine Nummer ohne "+" zu lesen ist - nicht die
# Einstellung des Nutzers: Wer in München sucht, bekommt keine österreichische Vorwahl.
LOKALE_VORWAHLEN = {
    "österreich": "+43", "austria": "+43", "deutschland": "+49", "germany": "+49",
    "schweiz": "+41", "switzerland": "+41", "frankreich": "+33", "france": "+33",
    "niederlande": "+31", "netherlands": "+31", "belgien": "+32", "belgium": "+32",
    "slowakei": "+421", "slovakia": "+421", "slowenien": "+386", "slovenia": "+386",
    "kroatien": "+385", "croatia": "+385", "vereinigtes königreich": "+44",
    "united kingdom": "+44", "großbritannien": "+44",
}
# Bekanntes Land, aber ohne sichere Regel: Inlandsnummern ohne "+" bleiben draußen.
LOKALE_VORWAHL_UNSICHER = "-"


# -- Kleine Helfer ------------------------------------------------------------

def _lokale_text(wert, grenze: int = 200) -> str:
    """Macht aus einem Karten-Wert einen kurzen, sauberen Satz-Baustein."""
    if wert is None:
        return ""
    text = re.sub(r"[\x00-\x1f\x7f]+", " ", str(wert))
    text = " ".join(text.split())
    if len(text) > grenze:
        text = text[:max(1, grenze - 1)].rstrip() + "…"
    return text


def _lokale_zahl(wert):
    """Eine endliche Zahl oder ``None`` (Karten-Daten können alles enthalten)."""
    try:
        zahl = float(wert)
    except (TypeError, ValueError):
        return None
    return zahl if math.isfinite(zahl) else None


def _lokale_abstand_m(b1: float, l1: float, b2: float, l2: float) -> float:
    """Luftlinie in Metern (Haversine)."""
    r = 6371000.0
    p1, p2 = math.radians(b1), math.radians(b2)
    db, dl = p2 - p1, math.radians(l2 - l1)
    a = math.sin(db / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(min(1.0, math.sqrt(a)))


def _lokale_kueche(wert):
    """Küche als Schlüssel aus ``KUECHEN`` oder ``None``, wenn wir sie nicht kennen."""
    text = str(wert or "").strip().lower()
    if not text:
        return "asiatisch"
    for alt, neu in (("ä", "ae"), ("ö", "oe"), ("ü", "ue"), ("ß", "ss")):
        text = text.replace(alt, neu)
    text = LOKALE_KUECHE_ALIAS.get(text, text)
    return text if text in KUECHEN else None


def _lokale_vorwahl(land) -> str:
    """Landesvorwahl für Inlandsnummern am Ort der Suche.

    Leer = Einstellung ``LANDESVORWAHL`` (``nummer_pruefen`` entscheidet).
    """
    name = str(land or "").strip().lower()
    if not name:
        return ""
    return LOKALE_VORWAHLEN.get(name, LOKALE_VORWAHL_UNSICHER)


def _lokale_telefon(roh, vorwahl: str = ""):
    """Erste brauchbare Nummer aus dem Karten-Eintrag: ``(+43..., Anzeigeform)``.

    Mehrere Nummern trennt die Karte mit ";". Jede wird über ``nummer_pruefen``
    in die internationale Form gebracht; was nicht eindeutig lesbar ist, zählt
    nicht - lieber keine Nummer als eine falsche. Ergebnis ``("", "")``, wenn keine passt.
    """
    for teil in re.split(r"[;,]", str(roh or "")):
        # "+43 (0) 1 234" - die Null in Klammern gehört nicht zur Nummer
        teil = re.sub(r"\(\s*0\s*\)", "", teil).strip()
        ziffern = re.sub(r"[^\d+]", "", teil)
        if not ziffern or "+" in ziffern[1:]:
            continue
        if ziffern.startswith("0") and not ziffern.startswith("00"):
            if vorwahl == LOKALE_VORWAHL_UNSICHER:
                continue
            if vorwahl:
                ziffern = vorwahl + ziffern[1:]
        nummer, _fehler = nummer_pruefen(ziffern)
        if nummer and re.match(r"^\+\d{8,15}$", nummer):
            # Die Schreibweise der Karte bleibt fürs Vorlesen erhalten, wenn sie nur aus
            # Ziffern und Trennzeichen besteht und schon international ist.
            anzeige = teil if re.match(r"^\+[\d ()\-./]*$", teil) else nummer
            return nummer, _lokale_text(anzeige, 40)
    return "", ""


# -- Abfrage und Antwort ------------------------------------------------------

def lokale_abfrage(breite: float, laenge: float, regex: str, radius: int = 2500,
                   anzahl: int = 40) -> str:
    """Overpass-Abfrage: Restaurants mit Namen im Umkreis, gefiltert nach Küche.

    Ohne ``regex`` fällt der Küchen-Filter weg.
    """
    # Anführungszeichen und Rückstriche könnten die Abfrage aufbrechen.
    regex = re.sub(r'["\\\r\n]', "", str(regex or ""))
    kueche = '["cuisine"~"%s",i]' % regex if regex else ""
    return ('[out:json][timeout:25];'
            'nwr["amenity"="restaurant"]%s["name"](around:%d,%.5f,%.5f);'
            'out center tags %d;' % (kueche, int(radius), float(breite), float(laenge),
                                     int(anzahl)))


def lokale_lesen(daten, breite: float, laenge: float, vorwahl: str = "") -> list:
    """Overpass-Antwort -> Liste der Lokale, das nächste zuerst.

    Einträge ohne Namen (oder ohne Position) fallen weg. ``telefon`` ist
    international (``+43...``) oder leer. ``vorwahl`` (etwa ``+49``) sagt, wie
    eine Inlandsnummer ohne "+" zu lesen ist; leer = Einstellung des Nutzers.
    """
    elemente = daten.get("elements") if isinstance(daten, dict) else None
    liste = []
    for el in elemente if isinstance(elemente, list) else []:
        if not isinstance(el, dict) or not isinstance(el.get("tags"), dict):
            continue
        tags = el["tags"]
        name = _lokale_text(tags.get("name"), 80)
        if not name:
            continue
        # Punkte tragen lat/lon selbst, Flächen (Gebäude) einen "center".
        mitte = el.get("center") if isinstance(el.get("center"), dict) else {}
        lat, lon = _lokale_zahl(el.get("lat")), _lokale_zahl(el.get("lon"))
        if lat is None or lon is None:
            lat, lon = _lokale_zahl(mitte.get("lat")), _lokale_zahl(mitte.get("lon"))
        if lat is None or lon is None or abs(lat) > 90 or abs(lon) > 180:
            continue
        kuechen = [_lokale_text(k, 30) for k in str(tags.get("cuisine") or "").split(";")]
        strasse = " ".join(x for x in (_lokale_text(tags.get("addr:street"), 60),
                                       _lokale_text(tags.get("addr:housenumber"), 12)) if x)
        ort = " ".join(x for x in (_lokale_text(tags.get("addr:postcode"), 10),
                                   _lokale_text(tags.get("addr:city"), 40)) if x)
        adresse = ", ".join(x for x in (strasse, ort) if x) \
            or _lokale_text(tags.get("addr:full"), 100)
        telefon, anzeige = "", ""
        for schluessel in ("phone", "contact:phone"):  # erst phone, sonst contact:phone
            telefon, anzeige = _lokale_telefon(tags.get(schluessel), vorwahl)
            if telefon:
                break
        liste.append({
            "name": name,
            "kueche": _lokale_text(", ".join(k for k in kuechen if k), 60),
            "adresse": adresse,
            "telefon": telefon,
            "telefon_anzeige": anzeige,
            "oeffnungszeiten": _lokale_text(tags.get("opening_hours"), 200),
            "web": _lokale_text(tags.get("website") or tags.get("contact:website"), 100),
            "lat": lat,
            "lon": lon,
            "abstand_m": int(round(_lokale_abstand_m(float(breite), float(laenge), lat, lon))),
            "osm": "%s/%s" % (_lokale_text(el.get("type"), 10), _lokale_text(el.get("id"), 20)),
        })
    return sorted(liste, key=lambda x: (x["abstand_m"], x["name"].lower()))


# -- Texte --------------------------------------------------------------------

def _lokale_entfernung_text(meter: int) -> str:
    """Für die Stimme: "350 Meter" oder "1,2 Kilometer"."""
    if meter >= 1000:
        return ("%.1f Kilometer" % (meter / 1000.0)).replace(".", ",")
    schritt = 5 if meter < 100 else 10
    return "%d Meter" % (int(round(meter / float(schritt))) * schritt)


def _lokale_entfernung_kurz(meter: int) -> str:
    """Für die Liste auf dem Bildschirm: "350 m" oder "1,2 km"."""
    if meter >= 1000:
        return ("%.1f km" % (meter / 1000.0)).replace(".", ",")
    return "%d m" % meter


# -- Die Suche ----------------------------------------------------------------

class Lokale:
    """Findet Lokale in der Nähe. Braucht das Netz nur über ``welt`` und ``holen``.

    ``holen(abfrage) -> (daten, fehler)`` ist einspeisbar (Prüfungen); ohne sie
    fragt ``welt._overpass_holen`` - mit dem Ausweichserver. ``anzeige`` ist der
    Anzeige-Speicher (``Werkzeuge.anzeige``); ohne ihn bleibt der Bildschirm unberührt.
    """

    def __init__(self, welt, holen=None, anzeige=None):
        self.welt = welt
        self.holen = holen
        self.anzeige = anzeige

    def suchen(self, ort: str = "", kueche: str = "asiatisch", radius: int = 2500,
               nur_mit_telefon: bool = True) -> dict:
        """Lokale nach Küche im Umkreis eines Ortes, das nächste zuerst (höchstens 10).

        Legt nie einen Interessenten an. Der Ort ist ``WETTER_ORT``, wenn keiner
        genannt wird.
        """
        ort = _lokale_text(ort or config.WETTER_ORT or "", 80)
        if not ort:
            return {"ok": False, "fehler": "In welchem Ort soll ich suchen?"}
        schluessel = _lokale_kueche(kueche)
        if schluessel is None:
            return {"ok": False,
                    "fehler": "Die Küche '%s' kenne ich nicht. Möglich sind: %s."
                              % (_lokale_text(kueche, 40), ", ".join(sorted(KUECHEN)))}
        try:
            radius = int(float(radius))
        except (TypeError, ValueError):
            radius = 2500
        if radius <= 0:
            radius = 2500
        radius = max(100, min(10000, radius))

        # 1. Ort -> Koordinaten
        try:
            punkt, fehler = self.welt.ort_finden(ort)
        except Exception as ausnahme:  # nichts darf hier ungefangen hinausgehen
            punkt, fehler = None, "Die Ortssuche ging schief: %s" % ausnahme
        if not isinstance(punkt, dict):
            return {"ok": False,
                    "fehler": (fehler or "Den Ort '%s' finde ich nicht." % ort)
                    .replace("Der Wetterdienst", "Die Ortssuche")}
        breite, laenge = _lokale_zahl(punkt.get("breite")), _lokale_zahl(punkt.get("laenge"))
        if breite is None or laenge is None:
            return {"ok": False,
                    "fehler": "Für '%s' habe ich keine Koordinaten bekommen." % ort}
        ortsname = _lokale_text(punkt.get("name") or ort, 60)

        # 2. Karte fragen
        holen = self.holen or getattr(self.welt, "_overpass_holen", None)
        if holen is None:
            return {"ok": False, "fehler": "Die Karte (OpenStreetMap) ist nicht angebunden."}
        abfrage = lokale_abfrage(breite, laenge, KUECHEN[schluessel], radius,
                                 LOKALE_ABFRAGE_ANZAHL)
        try:
            antwort = holen(abfrage)
        except Exception as ausnahme:
            return {"ok": False,
                    "fehler": "Die Karte (OpenStreetMap) ist gerade nicht erreichbar: %s"
                              % _lokale_text(ausnahme, 120)}
        if isinstance(antwort, tuple) and len(antwort) == 2:
            daten, fehler = antwort
        elif isinstance(antwort, dict):
            daten, fehler = antwort, ""
        else:
            daten, fehler = None, ""
        if not isinstance(daten, dict):
            return {"ok": False,
                    "fehler": _lokale_text(fehler, 200)
                    or "Die Karte (OpenStreetMap) hat nichts Lesbares geantwortet."}
        elemente = daten.get("elements") if isinstance(daten.get("elements"), list) else []
        bemerkung = _lokale_text(daten.get("remark"), 160)
        abgebrochen = bool(re.search(r"runtime error|timed out|out of memory", bemerkung, re.I))
        if abgebrochen and not elemente:
            # Sonst sähe ein Zeitüberschreiten wie "keine Lokale" aus.
            return {"ok": False,
                    "fehler": "Die Karte (OpenStreetMap) hat die Abfrage nicht rechtzeitig "
                              "beantwortet. Versuch es gleich noch einmal, am besten mit "
                              "kleinerem Umkreis."}

        # 3. Lesen, Doppelte zusammenführen, nach Telefon filtern
        alle = self._doppelte_zusammenfuehren(
            lokale_lesen(daten, breite, laenge, _lokale_vorwahl(punkt.get("land"))))
        mit_telefon = [x for x in alle if x["telefon"]]
        ohne_telefon = len(alle) - len(mit_telefon)
        auswahl = mit_telefon if nur_mit_telefon else alle
        hinweise = []
        if abgebrochen:
            hinweise.append("Die Karte hat nur einen Teil der Treffer geliefert.")
        elif len(elemente) >= LOKALE_ABFRAGE_ANZAHL:
            hinweise.append("Die Karte hat sehr viele Treffer; ein kleinerer Umkreis zeigt "
                            "die nächsten sicher.")

        if not auswahl:
            text = ("In %s finde ich auf der Karte kein passendes Lokal mit Telefonnummer."
                    if nur_mit_telefon else
                    "In %s finde ich auf der Karte kein passendes Lokal.") % ortsname
            if nur_mit_telefon and ohne_telefon:
                hinweise.append("Auf der Karte stehen %d passende Lokale ohne Telefonnummer."
                                % ohne_telefon)
            ergebnis = {"ok": True, "ort": ortsname, "anzahl": 0, "text": text}
            if hinweise:
                ergebnis["hinweis"] = " ".join(hinweise)
            ergebnis["lokale"] = []
            ergebnis["quelle"] = LOKALE_QUELLE
            return ergebnis

        lokale = auswahl[:LOKALE_MAX]
        ergebnis = {"ok": True, "ort": ortsname, "anzahl": len(lokale),
                    "text": self._satz(schluessel, ortsname, len(auswahl), lokale)}
        if hinweise:
            ergebnis["hinweis"] = " ".join(hinweise)
        ergebnis["lokale"] = lokale
        ergebnis["quelle"] = LOKALE_QUELLE
        ergebnis = self._kuerzen(ergebnis)
        self._anzeigen(ortsname, ergebnis["lokale"])
        return ergebnis

    # -- Bausteine ------------------------------------------------------------

    @staticmethod
    def _doppelte_zusammenfuehren(liste: list) -> list:
        """Derselbe Laden als Punkt und als Gebäude steht nur einmal drin.

        Gleicher Name und weniger als ``LOKALE_DOPPELT_M`` Abstand. Fehlende Angaben
        des ersten ergänzt der zweite.
        """
        behalten = []
        for x in liste:
            gleich = None
            for y in behalten:
                if (y["name"].lower() == x["name"].lower()
                        and _lokale_abstand_m(y["lat"], y["lon"], x["lat"], x["lon"])
                        < LOKALE_DOPPELT_M):
                    gleich = y
                    break
            if gleich is None:
                behalten.append(x)
                continue
            if not gleich["telefon"] and x["telefon"]:
                gleich["telefon"], gleich["telefon_anzeige"] = x["telefon"], x["telefon_anzeige"]
            for feld in ("kueche", "adresse", "oeffnungszeiten", "web"):
                if not gleich[feld] and x[feld]:
                    gleich[feld] = x[feld]
        return behalten

    @staticmethod
    def _satz(schluessel: str, ortsname: str, gefunden: int, lokale: list) -> str:
        """Der gesprochene Satz: wie viele, und das nächste mit Telefon und Zeiten."""
        mehrzahl, einzahl = LOKALE_KUECHE_WORT[schluessel]
        text = "Ich habe %d %s in der Nähe von %s gefunden" % (
            gefunden, einzahl if gefunden == 1 else mehrzahl, ortsname)
        if gefunden > len(lokale):
            text += "; die nächsten %d stehen in der Liste" % len(lokale)
        erstes = lokale[0]
        teile = [erstes["name"], _lokale_entfernung_text(erstes["abstand_m"])]
        if erstes["telefon"]:
            teile.append("Telefon " + (erstes["telefon_anzeige"] or erstes["telefon"]))
        else:
            teile.append("keine Telefonnummer auf der Karte")
        nah = "Am nächsten: " + ", ".join(teile)
        if erstes["oeffnungszeiten"]:
            nah += ", Öffnungszeiten laut Karte: " + _lokale_text(erstes["oeffnungszeiten"], 100)
        return "%s. %s." % (text, nah.rstrip(". "))

    @staticmethod
    def _kuerzen(ergebnis: dict) -> dict:
        """Hält das Ergebnis unter der Grenze: erst Nebensächliches weglassen, dann Einträge."""
        def groesse():
            return len(json.dumps(ergebnis, ensure_ascii=False))

        for feld, grenze in (("web", 0), ("oeffnungszeiten", 60), ("telefon_anzeige", 0),
                             ("adresse", 0), ("kueche", 30)):
            if groesse() <= LOKALE_ERGEBNIS_GRENZE:
                break
            for x in ergebnis["lokale"]:
                x[feld] = x[feld][:grenze] if grenze else ""
        gekuerzt = False
        while groesse() > LOKALE_ERGEBNIS_GRENZE and len(ergebnis["lokale"]) > 1:
            ergebnis["lokale"].pop()
            gekuerzt = True
        if gekuerzt:
            ergebnis["anzahl"] = len(ergebnis["lokale"])
            ergebnis["hinweis"] = (ergebnis.get("hinweis", "") + " Die Liste ist wegen der "
                                   "Länge gekürzt.").strip()
        return ergebnis

    def _anzeigen(self, ortsname: str, lokale: list) -> None:
        """Zeigt die Liste auf der Bühne ('recherche'). Eine Störung hier bricht nichts ab."""
        anzeige = self.anzeige
        if anzeige is None:
            return
        try:
            liste = []
            for x in lokale[:LOKALE_MAX]:
                text = " · ".join(t for t in (x["kueche"], x["telefon_anzeige"] or x["telefon"],
                                              x["oeffnungszeiten"]) if t)
                liste.append({"titel": "%s · %s" % (x["name"], _lokale_entfernung_kurz(
                                  x["abstand_m"])),
                              "text": text[:300]})
            anzeige.zeigen("recherche", {
                "titel": "Lokale in der Nähe",
                "stand": _lokale_text("OpenStreetMap, %s, abgefragt am %s"
                                      % (ortsname, time.strftime("%d.%m.%Y %H:%M")), 160),
                "liste": liste,
                "quellen": [{"titel": "OpenStreetMap", "url": "https://www.openstreetmap.org"}],
            })
        except Exception:  # die Anzeige darf nie ein Werkzeug kaputt machen
            pass
