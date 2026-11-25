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
    "ollama_adresse": "http://127.0.0.1:11434",  # nur lokal (127.0.0.1, localhost, [::1]) – geprüft
    "modell_max_aufrufe_tag": 50,
    "kostenpflichtig_erlaubt": False,     # bezahlte Dienste grundsätzlich gesperrt
    "max_parallel": 2,                    # begrenzte Parallelität der Agenten
    "wallet_warnschwelle_cent": 300,      # Warnung, wenn simuliertes Guthaben darunter fällt
    "sicherung_behalten": 14,
    # Auftragssuche (Weg 1): Agenten lesen öffentliche Ausschreibungen – nur nach einmaligem Einschalten
    "internet_recherche_erlaubt": False,  # Eigentümer schaltet die Recherche einmal bewusst ein
    "auftragssuche_taeglich": False,      # Agenten suchen dann selbstständig einmal am Tag
    # Region: Postleitzahl-Bereiche (2-stellig) als Näherung für „ca. 100 km um Leverkusen“ – ANNAHME, änderbar
    "region_plz": ["40", "41", "42", "44", "45", "46", "47", "50", "51", "52", "53", "57", "58", "59"],
    # Region für EU-Ausschreibungen (NUTS-Codes; DEA = Nordrhein-Westfalen)
    "region_nuts": ["DEA"],
    "suchbegriffe": ["reinigung", "gebäudereinigung", "unterhaltsreinigung", "glasreinigung", "fensterreinigung",
                     "treppenhaus", "grundreinigung", "bauendreinigung", "baureinigung", "sonderreinigung"],
    "ausschlussbegriffe": ["straßenreinigung", "straßenkehr", "kanal", "biotonne", "behälter", "tank", "abwasser",
                           "entwässerung", "fahrzeug", "kehrmaschine"],
    "stundensatz_cent": 0,                # 0 = OFFEN (noch nicht festgelegt) – wird nie erfunden
    "wlan_zugriff": False,                # iPhone im eigenen WLAN – standardmäßig AUS, schaltet nur der Eigentümer
    # Überlebens-Agent: einmal am Tag selbstständig ein Plan aus echten Zahlen – stößt nur interne Aufgaben an
    # (Suche nur bei erlaubter Internet-Recherche, Bewerbungs-Mappen, Nachfass-ENTWÜRFE). Sendet/bezahlt nichts.
    "ueberlebensplan_taeglich": True,
}

# Öffentliche Quellen, die Agenten lesen dürfen (nur lesen, nur https, nur diese Hosts)
ERLAUBTE_QUELLEN_HOSTS = ("api.ted.europa.eu", "ted.europa.eu", "www.service.bund.de", "www.evergabe.nrw.de")
