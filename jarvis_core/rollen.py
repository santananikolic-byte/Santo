# -*- coding: utf-8 -*-
"""Rollen - wer bei einem Auftrag wirklich arbeitet und was er dabei darf.

Das sind keine erfundenen Mitarbeiter, sondern echte Ausführungen: Jeder Schritt
eines Auftrags läuft mit genau einer Rolle. Die Rolle bestimmt, welche
Werkzeuge der Schritt benutzen darf, welches Modell denkt und wie er sich
verhält. Die Oberfläche zeigt nur Rollen, die gerade wirklich einen Schritt
bearbeiten oder bearbeitet haben.

``allgemein`` ist der Orchestrator (Gespräch mit dem Nutzer): alle Werkzeuge im
Rahmen der Berechtigung.
"""

ROLLEN = {
    "allgemein": {
        "name": "Orchestrator",
        "werkzeuge": None,
        "modell": "chat",
        "auftrag": "",
    },
    "recherche": {
        "name": "Recherche",
        "werkzeuge": ("recherche", "dateien_auflisten", "datei_lesen", "datei_schreiben", "merken"),
        "modell": "arbeit",
        "auftrag": "Du bist der Rechercheur. Du findest öffentlich zugängliche Informationen, belegst sie mit Quellen "
                   "und trennst klar zwischen belegt, vermutet und nicht gefunden. Du änderst nichts außer Notizen in der Werkstatt.",
    },
    "vertrieb": {
        "name": "Vertrieb/Akquise",
        "werkzeuge": ("recherche", "dateien_auflisten", "datei_lesen", "datei_schreiben", "merken"),
        "modell": "arbeit",
        "auftrag": "Du bist Vertrieb/Akquise. Du suchst über öffentlich zugängliche Quellen (Ausschreibungsportale, "
                   "Firmenverzeichnisse, Kleinanzeigen) mögliche Kunden und Aufträge, prüfst eine Firma wie bei der "
                   "Anruferprüfung, bevor du sie empfiehlst, und schlägst Treffer mit \"merken\" (art=\"kontakt\") vor - "
                   "mit Quelle und Begründung, nie erfunden. Ein Anschreiben entwirfst du nur als Datei in der Werkstatt; "
                   "du versendest nichts, rufst nicht an und sagst keinen Preis zu - dafür gibt es keine Werkzeuge.",
    },
    "architektur": {
        "name": "Architektur",
        "werkzeuge": ("dateien_auflisten", "datei_lesen", "datei_schreiben", "recherche"),
        "modell": "arbeit",
        "auftrag": "Du bist der Architekt. Du entwirfst Aufbau, Schnittstellen und Abläufe, hältst sie schriftlich in der "
                   "Werkstatt fest und benennst Risiken. Du schreibst keinen Programmcode für die Ausführung.",
    },
    "entwicklung": {
        "name": "Entwicklung",
        "werkzeuge": ("dateien_auflisten", "datei_lesen", "datei_schreiben", "datei_loeschen"),
        "modell": "arbeit",
        "auftrag": "Du bist der Entwickler. Du schreibst und überarbeitest Dateien in der Werkstatt. Du führst nichts "
                   "aus; die Prüfung übernimmt die Prüfschicht und der Nutzer.",
    },
    "sicherheit": {
        "name": "Sicherheit",
        "werkzeuge": ("dateien_auflisten", "datei_lesen"),
        "modell": "arbeit",
        "auftrag": "Du bist der Sicherheitsprüfer. Du liest Dateien in der Werkstatt und benennst konkrete Risiken "
                   "(Zugangsdaten im Klartext, unsichere Eingaben, fehlende Prüfungen). Du änderst nichts.",
    },
    "dokumentation": {
        "name": "Dokumentation",
        "werkzeuge": ("dateien_auflisten", "datei_lesen", "datei_schreiben"),
        "modell": "arbeit",
        "auftrag": "Du bist der Dokumentierer. Du beschreibst verständlich, was vorhanden ist und wie man es benutzt, "
                   "und legst die Texte in der Werkstatt ab. Du erfindest keine Funktionen.",
    },
}


def rolle_pruefen(rolle):
    return rolle if rolle in ROLLEN and rolle != "allgemein" else "allgemein"


def erlaubt(rolle, werkzeug):
    werkzeuge = ROLLEN.get(rolle, ROLLEN["allgemein"])["werkzeuge"]
    return werkzeuge is None or werkzeug in werkzeuge


def auftragsrollen():
    """Die Rollen, die der Planer Schritten zuweisen darf."""
    return [name for name in ROLLEN if name != "allgemein"]
