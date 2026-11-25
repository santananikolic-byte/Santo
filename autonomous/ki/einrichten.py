# -*- coding: utf-8 -*-
"""Helfer für autonomous-ki-einrichten.sh (Kommandozeile, nur Python-Standardbibliothek).

    python3 -m autonomous.ki.einrichten basis --ram-mib 8192        → Basismodell nach Arbeitsspeicher
    python3 -m autonomous.ki.einrichten groesse --basis gemma3:4b   → Download-Größe in MiB (0 = unbekannt)
    python3 -m autonomous.ki.einrichten modelfile --basis gemma3:4b → Modelfile für „ollama create“
    python3 -m autonomous.ki.einrichten adresse                     → Ollama-Adresse aus den AUTONOMOUS-Einstellungen
    python3 -m autonomous.ki.einrichten einstellen --modell autonomous

„einstellen“ prüft das Modell zuerst ECHT (Probeaufruf). Erst danach setzt es die Einstellungen – über die
Einstellungs-Schnittstelle des Projekts als Eigentümer, nie per SQL von Hand. Stimmen sie schon, ändert es nichts.
Rückgabewert: 0 = fertig, 2 = falscher Aufruf, 3 = Modell nicht nutzbar (Einstellungen unverändert)."""

import argparse
import sys

from . import modelfile

NICHT_NUTZBAR = 3


def _modellname(wert):
    if not modelfile.modellname_ok(wert):
        raise argparse.ArgumentTypeError("ungültiger Modellname: %r" % wert)
    return wert


def _einstellungen():
    from ..db import Datenbank
    from ..einstellungen import Einstellungen
    from ..protokoll import Protokoll
    db = Datenbank()
    return db, Einstellungen(db, Protokoll(db))


def adresse():
    db, e = _einstellungen()
    try:
        print(e.hole("ollama_adresse"))
    finally:
        db.schliessen()
    return 0


def einstellen(modell):
    from . import anbieter, ausgabe, vorlagen
    db, e = _einstellungen()
    try:
        werte = e.alle()
        try:
            a = anbieter.OllamaAnbieter(werte["ollama_adresse"], modell)
        except anbieter.AnbieterFehler as f:
            print("Nicht eingestellt: %s" % f)
            return NICHT_NUTZBAR
        st = a.status()
        if not st["erreichbar"] or not st["modell_vorhanden"]:
            print("Nicht eingestellt: %s" % st["hinweis"])
            return NICHT_NUTZBAR
        try:
            antwort = ausgabe.saeubern(a.erzeugen(*vorlagen.modelltest(), max_zeichen=200, zeitlimit=180), 60)
        except anbieter.AnbieterFehler as f:
            print("Nicht eingestellt: Probeaufruf fehlgeschlagen (%s)." % f)
            return NICHT_NUTZBAR
        if not antwort:
            print("Nicht eingestellt: Das Modell hat auf den Probeaufruf nichts geantwortet.")
            return NICHT_NUTZBAR
        print("Probeaufruf ok – das Modell %s antwortet („%s“)." % (modell, antwort))
        geaendert = []
        # erst das Modell, dann der Anbieter: AUTONOMOUS nutzt nie kurz ein falsches Modell
        for schluessel, wert in (("ollama_modell", modell), ("modell_anbieter", "ollama")):
            if werte[schluessel] != wert:
                e.setze(schluessel, wert, "eigentuemer")
                geaendert.append(schluessel)
        if geaendert:
            print("AUTONOMOUS-Einstellungen gesetzt: Anbieter „ollama“, Modell „%s“." % modell)
        else:
            print("AUTONOMOUS-Einstellungen stimmen schon (Anbieter „ollama“, Modell „%s“) – nichts geändert." % modell)
        return 0
    finally:
        db.schliessen()


def main(argv=None):
    p = argparse.ArgumentParser(prog="python3 -m autonomous.ki.einrichten",
                                description="Helfer für die Einrichtung des lokalen KI-Modells „autonomous“.")
    befehle = p.add_subparsers(dest="befehl", required=True)
    befehle.add_parser("basis", help="Basismodell nach Arbeitsspeicher").add_argument("--ram-mib", type=int,
                                                                                    required=True)
    befehle.add_parser("groesse", help="Download-Größe des Basismodells in MiB").add_argument(
        "--basis", type=_modellname, required=True)
    befehle.add_parser("modelfile", help="Modelfile ausgeben").add_argument("--basis", type=_modellname, required=True)
    befehle.add_parser("adresse", help="Ollama-Adresse aus den Einstellungen")
    befehle.add_parser("einstellen", help="Modell echt prüfen, dann Einstellungen setzen").add_argument(
        "--modell", type=_modellname, default=modelfile.MODELLNAME)
    a = p.parse_args(argv)
    if a.befehl == "basis":
        try:
            print(modelfile.basis_fuer_ram(a.ram_mib))
        except ValueError as f:
            p.error(str(f))
        return 0
    if a.befehl == "groesse":
        print(modelfile.GROESSE_MIB.get(a.basis, 0))
        return 0
    if a.befehl == "modelfile":
        sys.stdout.write(modelfile.modelfile_text(a.basis))
        return 0
    if a.befehl == "adresse":
        return adresse()
    return einstellen(a.modell)


if __name__ == "__main__":
    sys.exit(main())
