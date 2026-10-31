# -*- coding: utf-8 -*-
"""Strukturierte Logs - eine JSON-Zeile pro Ereignis in ``logs/jarvis.jsonl``.

Jede Zeile hat mindestens ``zeit``, ``stufe`` und ``ereignis``. Die Datei wird
ab einer festen Größe rotiert, damit sie nicht unbegrenzt wächst.
"""

import datetime
import json
import logging
import logging.handlers
import os
import threading


class _JsonFormat(logging.Formatter):
    def format(self, record):
        eintrag = {
            "zeit": datetime.datetime.now().astimezone().isoformat(timespec="seconds"),
            "stufe": record.levelname,
            "ereignis": record.getMessage(),
        }
        for name, wert in getattr(record, "felder", {}).items():
            eintrag[name if name not in ("zeit", "stufe", "ereignis") else "feld_" + name] = wert
        return json.dumps(eintrag, ensure_ascii=False)


class Protokoll:
    def __init__(self, konfig):
        os.makedirs(konfig.log_ordner, exist_ok=True)
        self.datei = konfig.log_datei
        self._logger = logging.getLogger("jarvis.%s" % self.datei)
        self._logger.setLevel(konfig.logstufe)
        self._logger.propagate = False
        if not self._logger.handlers:
            handler = logging.handlers.RotatingFileHandler(
                self.datei, maxBytes=konfig.log_max_bytes, backupCount=konfig.log_dateien, encoding="utf-8")
            handler.setFormatter(_JsonFormat())
            self._logger.addHandler(handler)
        self._sperre = threading.Lock()

    def ereignis(self, name, niveau="INFO", **felder):
        """Schreibt ein Ereignis. ``niveau`` ist die Log-Stufe (INFO, WARNING, ERROR); alles andere sind Felder."""
        with self._sperre:
            self._logger.log(getattr(logging, niveau), name, extra={"felder": felder})

    def schliessen(self):
        for handler in list(self._logger.handlers):
            handler.close()
            self._logger.removeHandler(handler)


def letzte_eintraege(datei, anzahl=50):
    """Die letzten ``anzahl`` Einträge als Liste von dicts (defekte Zeilen werden übersprungen)."""
    try:
        with open(datei, "r", encoding="utf-8") as f:
            zeilen = f.readlines()[-max(1, anzahl):]
    except OSError:
        return []
    eintraege = []
    for zeile in zeilen:
        try:
            eintraege.append(json.loads(zeile))
        except ValueError:
            continue
    return eintraege
