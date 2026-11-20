# -*- coding: utf-8 -*-
"""Pfade und Grundeinstellungen. Geheimnisse stehen nie hier, sondern nur in daten/ (nicht in Git)."""

import os

PAKET = os.path.dirname(os.path.abspath(__file__))
PROJEKT = os.path.dirname(PAKET)


def datenordner():
    """Ordner für Datenbank, Sicherungen, Protokolle und erzeugte Produkte.

    Über AUTONOMOUS_DATEN änderbar (z. B. für Tests)."""
    pfad = os.environ.get("AUTONOMOUS_DATEN") or os.path.join(PAKET, "daten")
    os.makedirs(pfad, exist_ok=True)
    return os.path.abspath(pfad)


def unterordner(name):
    pfad = os.path.join(datenordner(), name)
    os.makedirs(pfad, exist_ok=True)
    return pfad


def db_pfad():
    return os.path.join(datenordner(), "autonomous.db")


VORLAGEN = os.path.join(PAKET, "daten_vorlagen")
UI = os.path.join(PAKET, "ui")

HOST = os.environ.get("AUTONOMOUS_HOST", "127.0.0.1")
PORT = int(os.environ.get("AUTONOMOUS_PORT", "8770"))

# Standardwerte der Einstellungen (veränderbar nur durch den Eigentümer über die Oberfläche)
STANDARD_EINSTELLUNGEN = {
    "modell_anbieter": "keiner",          # keiner | ollama (lokal, kostenlos)
    "ollama_modell": "gemma3:4b",
    "modell_max_aufrufe_tag": 50,
    "kostenpflichtig_erlaubt": False,     # bezahlte Dienste grundsätzlich gesperrt
    "max_parallel": 2,                    # begrenzte Parallelität der Agenten
    "wallet_warnschwelle_cent": 300,      # Warnung, wenn simuliertes Guthaben darunter fällt
    "sicherung_behalten": 14,
}
