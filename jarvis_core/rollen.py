# -*- coding: utf-8 -*-
"""Rollen - wer bei einem Auftrag wirklich arbeitet und was er dabei darf.

Das sind keine erfundenen Mitarbeiter, sondern echte Ausführungen: Jeder Schritt
eines Auftrags läuft mit genau einer Rolle. Die Rolle bestimmt, welche
Werkzeuge der Schritt benutzen darf, welches Modell denkt und wie er sich
verhält. Die Rollen kommen aus der Agenten-Organisation (``agenten.py``,
``agenten/*.md``: Abteilungen mit Fachleuten) plus den eigenen Agenten, die der
Nutzer per Ja angelegt hat.

``allgemein`` ist der Orchestrator (Gespräch mit dem Nutzer): alle Werkzeuge im
Rahmen der Berechtigung.
"""

from . import agenten

ROLLEN = {
    "allgemein": {
        "name": "Orchestrator",
        "werkzeuge": None,
        "modell": "chat",
        "auftrag": "",
        "abteilung": "",
        "zweck": "Spricht mit dir, zieht die passenden Fachleute hinzu und setzt das Team ein.",
        "eigen": False,
    },
}


def _eintrag(a):
    return {"name": a.name, "werkzeuge": a.werkzeuge, "modell": "arbeit", "auftrag": agenten.rollen_text(a),
            "abteilung": a.abteilung, "zweck": a.zweck, "eigen": a.eigen}


for _a in agenten.katalog()[1]:
    ROLLEN[_a.id] = _eintrag(_a)


def eigene_setzen(liste):
    """Ersetzt die eigenen Agenten (aus dem Datenordner) - die Katalog-Rollen bleiben unberührt."""
    for rid in [rid for rid, r in ROLLEN.items() if r.get("eigen")]:
        del ROLLEN[rid]
    agenten.eigene_setzen(liste)
    for a in liste:
        if a.id not in ROLLEN:
            ROLLEN[a.id] = _eintrag(a)


def rolle_pruefen(rolle):
    return rolle if rolle in ROLLEN and rolle != "allgemein" else "allgemein"


def erlaubt(rolle, werkzeug):
    werkzeuge = ROLLEN.get(rolle, ROLLEN["allgemein"])["werkzeuge"]
    return werkzeuge is None or werkzeug in werkzeuge


def auftragsrollen():
    """Die Rollen, die der Planer Schritten zuweisen darf."""
    return [name for name in ROLLEN if name != "allgemein"]
