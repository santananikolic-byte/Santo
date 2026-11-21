# -*- coding: utf-8 -*-
"""Einstellungen – änderbar nur durch den Eigentümer (über die Oberfläche), nie durch Agenten."""

import json
import re

from . import konfig
from .db import jetzt

ERLAUBTE_WERTE = {
    "modell_anbieter": lambda w: w in ("keiner", "ollama"),
    "ollama_modell": lambda w: isinstance(w, str) and 0 < len(w) <= 60 and all(
        c.isalnum() or c in ":.-_" for c in w),
    "ollama_adresse": lambda w: _lokale_adresse(w),
    "modell_max_aufrufe_tag": lambda w: isinstance(w, int) and 0 <= w <= 1000,
    "kostenpflichtig_erlaubt": lambda w: isinstance(w, bool),
    "max_parallel": lambda w: isinstance(w, int) and 1 <= w <= 8,
    "wallet_warnschwelle_cent": lambda w: isinstance(w, int) and 0 <= w <= 10_000_000,
    "sicherung_behalten": lambda w: isinstance(w, int) and 1 <= w <= 365,
    "internet_recherche_erlaubt": lambda w: isinstance(w, bool),
    "auftragssuche_taeglich": lambda w: isinstance(w, bool),
    "region_plz": lambda w: _liste(w, 1, 60, lambda x: re.fullmatch(r"\d{2}", x)),
    "region_nuts": lambda w: _liste(w, 1, 40, lambda x: re.fullmatch(r"DE[A-Z0-9]{0,3}", x)),
    "suchbegriffe": lambda w: _liste(w, 1, 40, _begriff),
    "ausschlussbegriffe": lambda w: _liste(w, 0, 40, _begriff),
    "stundensatz_cent": lambda w: isinstance(w, int) and not isinstance(w, bool) and 0 <= w <= 100_000,
}


def _lokale_adresse(wert):
    from .ki.anbieter import lokale_adresse_ok
    return lokale_adresse_ok(wert)


def _liste(wert, minimum, maximum, pruefung):
    return (isinstance(wert, list) and minimum <= len(wert) <= maximum
            and all(isinstance(x, str) and pruefung(x) for x in wert) and len(set(wert)) == len(wert))


def _begriff(x):
    return 2 <= len(x) <= 40 and re.fullmatch(r"[a-zäöüß0-9 \-]+", x) is not None


class Einstellungen:
    def __init__(self, db, protokoll):
        self.db = db
        self.protokoll = protokoll

    def alle(self):
        werte = dict(konfig.STANDARD_EINSTELLUNGEN)
        for zeile in self.db.alle("SELECT schluessel, wert FROM einstellungen"):
            if zeile["schluessel"] in werte:
                werte[zeile["schluessel"]] = json.loads(zeile["wert"])
        return werte

    def hole(self, schluessel):
        return self.alle()[schluessel]

    def setze(self, schluessel, wert, akteur):
        if akteur != "eigentuemer":
            self.protokoll.audit("einstellungen", "Änderung durch Nicht-Eigentümer blockiert",
                                 {"akteur": akteur, "schluessel": schluessel})
            raise PermissionError("Nur der Eigentümer darf Einstellungen ändern.")
        pruefung = ERLAUBTE_WERTE.get(schluessel)
        if pruefung is None:
            raise ValueError("Unbekannte Einstellung: %s" % schluessel)
        if not pruefung(wert):
            raise ValueError("Ungültiger Wert für %s" % schluessel)
        self.db.ausfuehren(
            "INSERT INTO einstellungen VALUES (?,?,?) ON CONFLICT(schluessel) DO UPDATE SET wert=excluded.wert,"
            " geaendert=excluded.geaendert", (schluessel, json.dumps(wert), jetzt()))
        self.protokoll.audit("einstellungen", "Einstellung geändert", {"schluessel": schluessel, "wert": wert})
