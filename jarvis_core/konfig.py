# -*- coding: utf-8 -*-
"""Konfiguration - Datei ``~/.jarvis/config.json``, Umgebungsvariablen gehen vor.

Umgebungsvariablen:
    JARVIS_DATEN     Datenordner (Standard ~/.jarvis)
    JARVIS_PORT      Port (Standard 8770 - der alte Jarvis nutzt 8765)
    JARVIS_LOGSTUFE  DEBUG, INFO, WARNING oder ERROR (Standard INFO)
    JARVIS_MODELL    Claude-Modell, z. B. opus (Standard) oder sonnet
    JARVIS_SAY       Pfad zu einem Ersatz für macOS ``say`` (nur für Tests)

Der Server hört ausschließlich auf der eigenen Maschine. Eine andere Adresse
in der Konfiguration wird abgelehnt - Fernzugriff ist bewusst noch nicht
vorgesehen (siehe JARVIS-SERVER.md).
"""

import json
import os
import re

STANDARD = {
    "host": "127.0.0.1",
    "port": 8770,
    "logstufe": "INFO",
    "log_max_bytes": 1000000,
    "log_dateien": 5,
    "provider_timeout": 300,
    "modell": "opus",
    "stimme": "",
    "tempo": 185,
    "vorlesen": True,
}

ERLAUBTE_HOSTS = ("127.0.0.1", "localhost")
LOGSTUFEN = ("DEBUG", "INFO", "WARNING", "ERROR")


class KonfigFehler(Exception):
    pass


class Konfig:
    def __init__(self, werte, daten_ordner):
        self.werte = werte
        self.daten_ordner = daten_ordner

    def __getattr__(self, name):
        try:
            return self.__dict__["werte"][name]
        except KeyError:
            raise AttributeError(name) from None

    @property
    def datei(self):
        return os.path.join(self.daten_ordner, "config.json")

    @property
    def log_ordner(self):
        return os.path.join(self.daten_ordner, "logs")

    @property
    def log_datei(self):
        return os.path.join(self.log_ordner, "jarvis.jsonl")

    @property
    def pid_datei(self):
        return os.path.join(self.daten_ordner, "jarvis.pid")

    @property
    def adresse(self):
        return "http://%s:%d" % (self.host, self.port)


def daten_ordner_ermitteln():
    return os.path.expanduser(os.environ.get("JARVIS_DATEN") or "~/.jarvis")


def laden(daten_ordner=None):
    """Liest die Konfiguration. Fehlt die Datei, wird sie mit Standardwerten angelegt."""
    ordner = daten_ordner or daten_ordner_ermitteln()
    os.makedirs(ordner, exist_ok=True)
    datei = os.path.join(ordner, "config.json")
    werte = dict(STANDARD)
    if os.path.exists(datei):
        try:
            with open(datei, "r", encoding="utf-8") as f:
                gelesen = json.load(f)
        except (OSError, ValueError) as fehler:
            raise KonfigFehler("Die Konfiguration %s ist nicht lesbar: %s" % (datei, fehler)) from None
        if not isinstance(gelesen, dict):
            raise KonfigFehler("Die Konfiguration %s muss ein JSON-Objekt sein." % datei)
        werte.update({k: v for k, v in gelesen.items() if k in STANDARD})
    else:
        with open(datei, "w", encoding="utf-8") as f:
            json.dump(STANDARD, f, indent=2)
            f.write("\n")

    if os.environ.get("JARVIS_PORT"):
        werte["port"] = os.environ["JARVIS_PORT"]
    if os.environ.get("JARVIS_LOGSTUFE"):
        werte["logstufe"] = os.environ["JARVIS_LOGSTUFE"]
    if os.environ.get("JARVIS_MODELL") is not None:
        werte["modell"] = os.environ["JARVIS_MODELL"]

    try:
        werte["port"] = int(werte["port"])
    except (TypeError, ValueError):
        raise KonfigFehler("Der Port muss eine Zahl sein, nicht %r." % (werte["port"],)) from None
    if not 1024 <= werte["port"] <= 65535:
        raise KonfigFehler("Der Port muss zwischen 1024 und 65535 liegen, nicht %d." % werte["port"])
    try:
        werte["provider_timeout"] = max(10, int(werte["provider_timeout"]))
    except (TypeError, ValueError):
        raise KonfigFehler("provider_timeout muss eine Zahl (Sekunden) sein.") from None
    werte["modell"] = str(werte["modell"] or "").strip()
    if werte["modell"] and not re.match(r"^[a-z0-9][a-z0-9.\-]*$", werte["modell"]):
        raise KonfigFehler("Unbekanntes Modell %r. Zum Beispiel \"opus\" oder \"sonnet\"." % (werte["modell"],))
    werte["stimme"] = str(werte["stimme"] or "").strip()
    try:
        werte["tempo"] = max(80, min(400, int(werte["tempo"])))
    except (TypeError, ValueError):
        raise KonfigFehler("tempo muss eine Zahl sein (Wörter pro Minute, z. B. 185).") from None
    werte["vorlesen"] = bool(werte["vorlesen"])
    werte["logstufe"] = str(werte["logstufe"]).upper()
    if werte["logstufe"] not in LOGSTUFEN:
        raise KonfigFehler("Unbekannte Logstufe %r. Erlaubt: %s." % (werte["logstufe"], ", ".join(LOGSTUFEN)))
    if werte["host"] not in ERLAUBTE_HOSTS:
        raise KonfigFehler("Der Server darf nur auf dieser Maschine laufen (127.0.0.1). "
                           "Die Adresse %r wird abgelehnt." % (werte["host"],))
    return Konfig(werte, ordner)


def speichern_werte(konfig):
    """Schreibt die aktuellen Werte zurück in die config.json."""
    nur_bekannte = {k: konfig.werte[k] for k in STANDARD if k in konfig.werte}
    zwischen = konfig.datei + ".neu"
    with open(zwischen, "w", encoding="utf-8") as f:
        json.dump(nur_bekannte, f, indent=2, ensure_ascii=False)
        f.write("\n")
    os.replace(zwischen, konfig.datei)
