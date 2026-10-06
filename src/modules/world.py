#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Welt - echtes Wetter und Recherche.

Das Wetter kommt von Open-Meteo: kostenlos, ohne Schlüssel, ohne Anmeldung.
Zuerst wird der Ortsname in Koordinaten übersetzt, dann die Vorhersage geholt.

Recherche und Flugsuche laufen über einen Such-MCP (Brave). **Flüge werden
gefunden und genannt, nie gebucht.** Das Buchen läuft danach über die
Bildschirmsteuerung mit ausdrücklicher Freigabe - niemals heimlich.
"""

import json
import time
import urllib.error
import urllib.parse
import urllib.request

import config

GEO_URL = "https://geocoding-api.open-meteo.com/v1/search"
# OpenStreetMap über Overpass: frei, ohne Schlüssel. Zwei Server, falls einer voll ist.
OVERPASS_URLS = ("https://overpass-api.de/api/interpreter",
                 "https://overpass.kumi.systems/api/interpreter")

# Welche Betriebe eine Gebäudereinigung brauchen - als OpenStreetMap-Merkmale.
OSM_BRANCHEN = {
    "arzt": [("amenity", "doctors"), ("amenity", "dentist"), ("amenity", "clinic"), ("healthcare", "")],
    "praxis": [("amenity", "doctors"), ("amenity", "dentist"), ("healthcare", "")],
    "zahnarzt": [("amenity", "dentist")],
    "tierarzt": [("amenity", "veterinary")],
    "klinik": [("amenity", "clinic"), ("amenity", "hospital")],
    "apothek": [("amenity", "pharmacy")],
    "pflege": [("amenity", "nursing_home"), ("social_facility", "nursing_home")],
    "physio": [("healthcare", "physiotherapist")],
    "steuer": [("office", "tax_advisor"), ("office", "accountant")],
    "kanzlei": [("office", "lawyer"), ("office", "notary")],
    "anwalt": [("office", "lawyer")],
    "notar": [("office", "notary")],
    "büro": [("office", "")],
    "buero": [("office", "")],
    "firma": [("office", "company")],
    "hausverwaltung": [("office", "property_management"), ("office", "estate_agent")],
    "immobil": [("office", "estate_agent"), ("office", "property_management")],
    "versicherung": [("office", "insurance")],
    "bank": [("amenity", "bank")],
    "hotel": [("tourism", "hotel"), ("tourism", "guest_house")],
    "pension": [("tourism", "guest_house")],
    "restaurant": [("amenity", "restaurant")],
    "gastro": [("amenity", "restaurant"), ("amenity", "cafe")],
    "café": [("amenity", "cafe")],
    "cafe": [("amenity", "cafe")],
    "bäcker": [("shop", "bakery")],
    "friseur": [("shop", "hairdresser")],
    "kosmetik": [("shop", "beauty")],
    "architekt": [("office", "architect")],
    "baufirm": [("craft", "builder"), ("office", "construction_company")],
    "bauunternehm": [("craft", "builder"), ("office", "construction_company")],
    "baumeister": [("craft", "builder"), ("office", "construction_company")],
    "autohaus": [("shop", "car")],
    "fitness": [("leisure", "fitness_centre")],
    "kindergarten": [("amenity", "kindergarten")],
    "schule": [("amenity", "school")],
    "supermarkt": [("shop", "supermarket")],
    "geschäft": [("shop", "")],
}
# Allgemeine Wörter ohne eigene Branche - dafür gilt die Standardmischung.
OSM_ALLGEMEIN = ("betrieb", "firmen", "unternehm", "gewerbe", "kunde", "alle", "egal",
                 "irgend", "reinigung")
# Ohne Angabe: die Betriebe, die am häufigsten eine Reinigung vergeben.
OSM_STANDARD = ["arzt", "steuer", "kanzlei", "hausverwaltung", "versicherung", "autohaus",
                "fitness", "hotel", "firma"]
OSM_NAMEN = {"doctors": "Arztpraxis", "dentist": "Zahnarzt", "clinic": "Klinik",
             "tax_advisor": "Steuerberatung", "accountant": "Buchhaltung", "lawyer": "Kanzlei",
             "notary": "Notariat", "property_management": "Hausverwaltung",
             "estate_agent": "Immobilienbüro", "insurance": "Versicherung", "company": "Firma",
             "hotel": "Hotel", "guest_house": "Pension", "car": "Autohaus",
             "fitness_centre": "Fitnessstudio", "kindergarten": "Kindergarten", "school": "Schule",
             "supermarket": "Supermarkt", "bank": "Bank", "restaurant": "Restaurant",
             "physiotherapist": "Physiotherapie"}


def _flach(text: str) -> str:
    """Kleinschreibung ohne Umlaute - so findet "Ärzte" den Stamm "arzt"."""
    return ((text or "").lower().replace("ä", "a").replace("ö", "o").replace("ü", "u")
            .replace("ß", "ss"))


def osm_schluessel(branche: str):
    """Welche Kartenbranchen gemeint sind - ``None``, wenn die Branche unbekannt ist.

    Mehrzahl und Umlaute ("Zahnärzte", "Autohäuser") finden den Stamm. Passt ein
    längerer Stamm ("tierarzt"), fällt der kürzere darin ("arzt") weg. Ohne
    Branche oder mit einem allgemeinen Wort ("Firmen") gilt die Standardmischung.
    """
    text = _flach(branche)
    if not text.strip():
        return list(OSM_STANDARD)
    treffer = [k for k in OSM_BRANCHEN if _flach(k) in text]
    treffer = [k for k in treffer
               if not any(k != l and _flach(k) in _flach(l) for l in treffer)]
    if treffer:
        return treffer
    if any(wort in text for wort in OSM_ALLGEMEIN):
        return list(OSM_STANDARD)
    return None


def overpass_abfrage(breite: float, laenge: float, merkmale: list, radius: int = 3000,
                     anzahl: int = 60) -> str:
    """Baut die Overpass-Abfrage: alle Betriebe mit diesen Merkmalen im Umkreis."""
    teile = []
    for schluessel, wert in merkmale:
        filter_ = '["%s"="%s"]' % (schluessel, wert) if wert else '["%s"]' % schluessel
        teile.append('nwr%s["name"](around:%d,%.5f,%.5f);' % (filter_, int(radius), breite, laenge))
    return "[out:json][timeout:25];(%s);out center tags %d;" % ("".join(teile), int(anzahl))


def osm_betriebe_lesen(daten: dict) -> list:
    """Macht aus der Overpass-Antwort eine Liste von Betrieben mit Adresse und Telefon."""
    betriebe, gesehen = [], set()
    for element in (daten or {}).get("elements", []):
        tags = element.get("tags") or {}
        name = (tags.get("name") or "").strip()
        if not name or name.lower() in gesehen:
            continue
        gesehen.add(name.lower())
        art = ""
        for schluessel in ("amenity", "office", "healthcare", "tourism", "shop", "leisure"):
            if tags.get(schluessel):
                art = OSM_NAMEN.get(tags[schluessel], tags[schluessel].replace("_", " "))
                break
        strasse = " ".join(x for x in (tags.get("addr:street", ""), tags.get("addr:housenumber", "")) if x)
        ort = " ".join(x for x in (tags.get("addr:postcode", ""), tags.get("addr:city", "")) if x)
        betriebe.append({
            "firma": name[:120], "branche": art,
            "adresse": ", ".join(x for x in (strasse, ort) if x),
            "telefon": (tags.get("phone") or tags.get("contact:phone") or "").strip()[:40],
            "web": (tags.get("website") or tags.get("contact:website") or "").strip()[:200],
            "mail": (tags.get("email") or tags.get("contact:email") or "").strip()[:120],
        })
    return betriebe
WETTER_URL = "https://api.open-meteo.com/v1/forecast"

# WMO-Wettercodes in verständliches Deutsch.
WETTERLAGE = {
    0: "klar", 1: "überwiegend klar", 2: "teilweise bewölkt", 3: "bedeckt",
    45: "neblig", 48: "Nebel mit Reifbildung",
    51: "leichter Nieselregen", 53: "Nieselregen", 55: "starker Nieselregen",
    56: "gefrierender Nieselregen", 57: "starker gefrierender Nieselregen",
    61: "leichter Regen", 63: "Regen", 65: "starker Regen",
    66: "gefrierender Regen", 67: "starker gefrierender Regen",
    71: "leichter Schneefall", 73: "Schneefall", 75: "starker Schneefall",
    77: "Schneekörner", 80: "leichte Regenschauer", 81: "Regenschauer",
    82: "heftige Regenschauer", 85: "Schneeschauer", 86: "starke Schneeschauer",
    95: "Gewitter", 96: "Gewitter mit Hagel", 99: "schweres Gewitter mit Hagel",
}


def _holen(url: str, parameter: dict, timeout: int = 20, versuche: int = 3):
    """Holt JSON von einer Adresse.

    Ein einzelner Verbindungsabbruch - unterwegs im Auto oder im WLAN eines
    Kunden keine Seltenheit - soll nicht gleich als "kein Wetter" beim Nutzer
    ankommen. Deshalb wird mit wachsendem Abstand nachgefasst.
    """
    ziel = "%s?%s" % (url, urllib.parse.urlencode(parameter))
    letzter_fehler = "unbekannt"
    for versuch in range(max(1, versuche)):
        try:
            anfrage = urllib.request.Request(ziel, headers={"User-Agent": "Jarvis/1.0"})
            with urllib.request.urlopen(anfrage, timeout=timeout) as antwort:
                return json.loads(antwort.read().decode("utf-8")), ""
        except urllib.error.HTTPError as fehler:
            return None, "Der Wetterdienst antwortet mit Fehler %d." % fehler.code
        except (urllib.error.URLError, OSError, ValueError) as fehler:
            letzter_fehler = str(fehler)
            if versuch + 1 < max(1, versuche):
                time.sleep(1.5 * (versuch + 1))
    return None, "Der Wetterdienst ist nicht erreichbar: %s" % letzter_fehler


class Welt:
    """Wetter, Recherche und Flugsuche."""

    def __init__(self, mcp=None):
        self.mcp = mcp

    # -- Wetter -------------------------------------------------------------

    def ort_finden(self, ort: str):
        """Übersetzt einen Ortsnamen in Koordinaten."""
        daten, fehler = _holen(GEO_URL, {"name": ort, "count": 1,
                                         "language": "de", "format": "json"})
        if daten is None:
            return None, fehler
        treffer = (daten or {}).get("results") or []
        if not treffer:
            return None, "Den Ort '%s' finde ich nicht." % ort
        erster = treffer[0]
        return {"name": erster.get("name", ort),
                "land": erster.get("country", ""),
                "breite": erster.get("latitude"),
                "laenge": erster.get("longitude")}, ""

    def wetter(self, ort: str = "") -> dict:
        """Aktuelles Wetter und die nächsten zwei Tage - als gesprochener Satz."""
        ort = (ort or config.WETTER_ORT or "Wien").strip()
        koordinaten, fehler = self.ort_finden(ort)
        if koordinaten is None:
            return {"ok": False, "fehler": fehler}

        daten, fehler = _holen(WETTER_URL, {
            "latitude": koordinaten["breite"], "longitude": koordinaten["laenge"],
            "current": "temperature_2m,weather_code,wind_speed_10m,relative_humidity_2m",
            "daily": "temperature_2m_max,temperature_2m_min,weather_code,"
                     "precipitation_probability_max",
            "timezone": "auto", "forecast_days": 3})
        if daten is None:
            return {"ok": False, "fehler": fehler}

        jetzt = daten.get("current") or {}
        taeglich = daten.get("daily") or {}
        lage = WETTERLAGE.get(int(jetzt.get("weather_code") or 0), "wechselhaft")
        temperatur = jetzt.get("temperature_2m")
        wind = jetzt.get("wind_speed_10m")

        satz = ("In %s ist es gerade %s bei %.0f Grad, Wind %.0f Kilometer pro Stunde."
                % (koordinaten["name"], lage, float(temperatur or 0), float(wind or 0)))

        tage = []
        namen = ["Heute", "Morgen", "Übermorgen"]
        for index in range(min(3, len(taeglich.get("time", []) or []))):
            hoch = (taeglich.get("temperature_2m_max") or [None])[index]
            tief = (taeglich.get("temperature_2m_min") or [None])[index]
            code = (taeglich.get("weather_code") or [0])[index]
            regen = (taeglich.get("precipitation_probability_max") or [0])[index]
            tage.append({"tag": namen[index] if index < 3 else taeglich["time"][index],
                         "hoch": hoch, "tief": tief,
                         "lage": WETTERLAGE.get(int(code or 0), "wechselhaft"),
                         "regenwahrscheinlichkeit": regen})
            if index <= 1:
                satz += (" %s %s, %.0f bis %.0f Grad, Regenwahrscheinlichkeit %d Prozent."
                         % (namen[index], WETTERLAGE.get(int(code or 0), "wechselhaft"),
                            float(tief or 0), float(hoch or 0), int(regen or 0)))

        # Für einen Gebäudereiniger ist Regen kein Nebenthema: Fensterreinigung
        # und Außenflächen fallen dann aus.
        regen_heute = (taeglich.get("precipitation_probability_max") or [0])[0]
        if regen_heute and int(regen_heute) >= 60:
            satz += " Bei der Regenwahrscheinlichkeit würde ich Fensterarbeiten verschieben."

        return {"ok": True, "ort": koordinaten["name"], "aktuell": jetzt,
                "tage": tage, "text": satz}

    # -- Betriebe finden (OpenStreetMap) ----------------------------------

    def _overpass_holen(self, abfrage: str):
        letzter = "unbekannt"
        for url in OVERPASS_URLS:
            try:
                anfrage = urllib.request.Request(
                    url, data=urllib.parse.urlencode({"data": abfrage}).encode("utf-8"),
                    method="POST", headers={"User-Agent": "Jarvis/1.0 (Gebaeudereinigung)"})
                with urllib.request.urlopen(anfrage, timeout=40) as antwort:
                    return json.loads(antwort.read().decode("utf-8")), ""
            except (urllib.error.URLError, OSError, ValueError) as fehler:
                letzter = str(fehler)
        return None, "Die Karte (OpenStreetMap) ist gerade nicht erreichbar: %s" % letzter

    def betriebe_suchen(self, ort: str, branche: str = "", anzahl: int = 15,
                        radius: int = 3000, holen=None) -> dict:
        """Sucht Betriebe in einem Ort auf OpenStreetMap - ohne Schlüssel, mit echter Adresse.

        Gefunden wird, was dort eingetragen ist: Name, Art, Adresse und oft Telefon
        und Webseite. Nichts davon wird erfunden.
        """
        ort = (ort or "").strip()
        if not ort:
            return {"ok": False, "fehler": "In welchem Ort soll ich suchen?"}
        schluessel = osm_schluessel(branche)
        if schluessel is None:
            return {"ok": False, "unbekannt": True,
                    "fehler": "Die Branche '%s' kenne ich auf der Karte nicht." % branche.strip()}
        punkt, fehler = self.ort_finden(ort)
        if punkt is None:
            return {"ok": False, "fehler": (fehler or "").replace("Der Wetterdienst", "Die Ortssuche")}
        merkmale = []
        for k in schluessel:
            for m in OSM_BRANCHEN[k]:
                if m not in merkmale:
                    merkmale.append(m)
        abfrage = overpass_abfrage(punkt["breite"], punkt["laenge"], merkmale, radius,
                                   max(20, int(anzahl or 15) * 4))
        daten, fehler = (holen or self._overpass_holen)(abfrage)
        if daten is None:
            return {"ok": False, "fehler": fehler}
        # Alles zurück, nicht nur "anzahl": Was schon in der Liste steht, überspringt
        # der Aufrufer - sonst liefert derselbe Ort immer dieselben ersten Treffer.
        betriebe = osm_betriebe_lesen(daten)
        return {"ok": True, "ort": punkt.get("name") or ort, "anzahl": len(betriebe),
                "betriebe": betriebe, "quelle": "OpenStreetMap"}

    # -- Recherche ----------------------------------------------------------

    def _such_werkzeug(self):
        """Sucht das passende Werkzeug des Such-MCP-Servers."""
        if self.mcp is None:
            return ""
        for werkzeug in self.mcp.alle_werkzeuge():
            name = werkzeug.get("name", "")
            if "search" in name.lower() and "local" not in name.lower():
                return name
        return ""

    def recherche(self, frage: str) -> dict:
        """Sucht im Web über den Such-MCP."""
        frage = (frage or "").strip()
        if not frage:
            return {"ok": False, "fehler": "Sag mir, wonach ich suchen soll."}
        werkzeug = self._such_werkzeug()
        if not werkzeug:
            return {"ok": False,
                    "fehler": "Für die Recherche fehlt der Such-Dienst. In "
                              "config/mcp_servers.json den Eintrag 'suche' auf "
                              "\"aus\": false stellen und einen Brave-Schlüssel eintragen."}
        ergebnis = self.mcp.aufrufen(werkzeug, {"query": frage, "count": 6})
        if not ergebnis.get("ok"):
            return ergebnis
        return {"ok": True, "frage": frage, "text": ergebnis["text"][:4000]}

    def flug_suchen(self, von: str, nach: str, wann: str = "") -> dict:
        """Sucht Flugverbindungen und nennt sie. Gebucht wird hier nichts."""
        von, nach = (von or "").strip(), (nach or "").strip()
        if not von or not nach:
            return {"ok": False, "fehler": "Ich brauche Abflugort und Ziel."}
        anfrage = "Flug von %s nach %s%s Preise Fluggesellschaft Abflugzeit" % (
            von, nach, (" am %s" % wann) if wann else "")
        ergebnis = self.recherche(anfrage)
        if not ergebnis.get("ok"):
            return ergebnis
        return {"ok": True, "von": von, "nach": nach, "wann": wann,
                "gebucht": False,
                "text": ("Das habe ich zu Flügen von %s nach %s gefunden:\n%s\n\n"
                         "Gebucht ist nichts. Wenn du willst, buche ich über die "
                         "Bildschirmsteuerung - dafür fragst du mich noch einmal und "
                         "bestätigst jeden Schritt."
                         % (von, nach, ergebnis["text"][:2500]))}
