# -*- coding: utf-8 -*-
"""Eigenes KI-Modell „autonomous“ – ehrlich gesagt: ANGEPASST, nicht neu trainiert.

Ein Ollama-Modelfile nimmt ein vorhandenes, frei nutzbares Basismodell (Gemma 3) und baut fest ein:
- die Arbeitsregeln aus CLAUDE.md (Deutsch, einfach, nichts erfinden, keine Zusagen an Kunden, Entwürfe kennzeichnen),
- knappes Firmenwissen – nur Geschäftliches, nichts Privates, keine Zahlen,
- eine niedrige Temperatur (wenig „Fantasie“).
Die Gewichte des Basismodells bleiben unverändert. Erstellt wird das Modell mit `ollama create autonomous -f …`
(siehe autonomous-ki-einrichten.sh).

Wichtig (gemessen mit Ollama 0.40.17): Schickt eine Anfrage selbst eine System-Nachricht, ERSETZT sie den hier
eingebauten SYSTEM-Text. Darum lässt ki/anbieter.py beim eigenen Modell die allgemeinen Grundregeln weg – der
SYSTEM-Text unten enthält sie wörtlich (Test: test_ki_modell.py)."""

from . import vorlagen

MODELLNAME = "autonomous"
FASSUNG = 1
KENNUNG = "AUTONOMOUS-Regeln (Fassung %d)" % FASSUNG

# Basismodell nach Arbeitsspeicher (MiB): unter 6 GB → 1b, 6 bis unter 14 GB → 4b, ab 14 GB → 12b
BASIS_STUFEN = ((6 * 1024, "gemma3:1b"), (14 * 1024, "gemma3:4b"), (None, "gemma3:12b"))
# Download-Größe in MiB (Summe der Schichten laut registry.ollama.ai, abgerufen am 23.11.2026)
GROESSE_MIB = {"gemma3:1b": 769, "gemma3:4b": 3195, "gemma3:12b": 7786}
PARAMETER = (("temperature", "0.2"), ("top_p", "0.9"))

ZUSATZREGELN = (
    "Zusätzliche Arbeitsregeln:\n"
    "- Schreibe kurz, freundlich und direkt. Keine Fachsprache, keine Emojis.\n"
    "- Wenn etwas nicht in den Daten steht, schreibe ehrlich: „Das weiß ich nicht.“ und sage, was fehlt.\n"
    "- Erfinde nie Preise, Stundensätze, Umsätze, Kunden, Referenzen, Erfahrungsjahre, Termine, Telefonnummern, "
    "E-Mail-Adressen oder Internetadressen.\n"
    "- Fehlende Angaben schreibst du als Platzhalter in eckigen Klammern, zum Beispiel [Telefon] oder [Preis].\n"
    "- Sage Kunden keine Preise, Termine oder Leistungen zu. Schreibe stattdessen, dass die Inhaber es prüfen und "
    "sich melden.\n"
    "- Texte für Kunden sind Entwürfe: Die Inhaber prüfen sie und senden sie selbst.\n"
    "- Kennzeichne Vermutungen als Vermutung.\n"
    "- Frage nie nach Passwörtern, Zugangsdaten oder Zahlungsdaten.\n"
    "- Wollen unbekannte Firmen oder Anrufer Geld oder Daten: zuerst prüfen (Handelsregister, Impressum, "
    "E-Mail-Adresse), nur über die offizielle Nummer zurückrufen, nichts vorab bezahlen.")

FIRMENWISSEN = (
    "Was du über den Betrieb weißt (nur Geschäftliches):\n"
    "- Familienbetrieb für Bau und Reinigung: Bauarbeiten sowie Gebäude-, Büro- und Treppenhausreinigung.\n"
    "- Sitz in Leverkusen bei Köln, Einsatz in ganz Nordrhein-Westfalen.\n"
    "- Wenige Mitarbeiter, das Team soll wachsen.\n"
    "- Firmenname, Rechtsform und Stundensatz sind noch nicht festgelegt – nenne sie nie, nutze Platzhalter.\n"
    "- Ziel: mehr Aufträge, vor allem feste Daueraufträge, zum Beispiel von Hausverwaltungen und Firmen.\n"
    "- Über Geld, Aufträge und Projekte entscheiden die Inhaber gemeinsam.\n"
    "- Dieses Wissen gilt nur für diesen Betrieb – übertrage es nie auf andere Firmen. Über andere Firmen weißt du "
    "nichts, außer es steht in den Daten.")


def basis_fuer_ram(ram_mib):
    """Basismodell für einen Rechner mit ram_mib MiB Arbeitsspeicher."""
    if isinstance(ram_mib, bool) or not isinstance(ram_mib, int) or ram_mib <= 0:
        raise ValueError("Arbeitsspeicher muss eine positive ganze Zahl (MiB) sein.")
    for grenze, modell in BASIS_STUFEN:
        if grenze is None or ram_mib < grenze:
            return modell
    raise AssertionError("unerreichbar")


def modellname_ok(name):
    """Dieselbe Regel wie für die Einstellung ollama_modell – kein Leerzeichen, kein Zeilenumbruch, keine Anführung."""
    return (isinstance(name, str) and 0 < len(name) <= 60
            and all(c.isascii() and (c.isalnum() or c in ":.-_") for c in name) and ".." not in name)


def ist_eigenes_modell(name):
    return isinstance(name, str) and (name == MODELLNAME or name.startswith(MODELLNAME + ":"))


def system_text():
    return "%s\n%s\n\n%s\n\n%s" % (KENNUNG, vorlagen.GRUNDREGELN, ZUSATZREGELN, FIRMENWISSEN)


def modelfile_text(basis):
    if not modellname_ok(basis):
        raise ValueError("Ungültiger Name für das Basismodell.")
    system = system_text()
    if '"""' in system:  # würde den SYSTEM-Block beenden
        raise ValueError("Systemtext darf keine dreifachen Anführungszeichen enthalten.")
    teile = ["# AUTONOMOUS – eigenes KI-Modell „%s“" % MODELLNAME,
             "# Angepasst, NICHT neu trainiert: Basismodell %s (dessen Lizenz gilt weiter) mit fest eingebauten" % basis,
             "# Arbeitsregeln, Firmenwissen (nur Geschäftliches) und niedriger Temperatur.",
             "# Erzeugt von autonomous/ki/modelfile.py – nicht von Hand ändern: autonomous-ki-einrichten.sh erneut "
             "ausführen.",
             "FROM %s" % basis]
    teile += ["PARAMETER %s %s" % p for p in PARAMETER]
    teile.append('SYSTEM """%s"""' % system)
    return "\n".join(teile) + "\n"
