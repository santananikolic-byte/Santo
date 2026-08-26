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
