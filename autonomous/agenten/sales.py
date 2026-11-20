# -*- coding: utf-8 -*-
"""Sales-Agent – Platzhalter, wird im Arbeitspaket Produkt/Vertrieb ausgebaut."""

from . import Agent


class SalesAgent(Agent):
    rolle = "sales"
    name = "Sales-Agent"
    beschreibung = "Bereitet Angebote und Kundenkommunikation vor; versendet nichts ohne Freigabe."
    rechte = frozenset({"entwurf_erstellen", "interne_auswertung", "gedaechtnis_vorschlag", "kundenkontakt",
                        "externe_nachricht"})
    aufgabentypen = {}
