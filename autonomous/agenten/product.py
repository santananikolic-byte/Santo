# -*- coding: utf-8 -*-
"""Product-Agent – Platzhalter, wird im Arbeitspaket Produkt/Vertrieb ausgebaut."""

from . import Agent


class ProductAgent(Agent):
    rolle = "product"
    name = "Product-Agent"
    beschreibung = "Erstellt digitale Produkte, Webseiten und Vorlagen; prüft Qualität."
    rechte = frozenset({"datei_erstellen", "test_ausfuehren", "interne_auswertung", "gedaechtnis_vorschlag"})
    aufgabentypen = {}
