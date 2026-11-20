# -*- coding: utf-8 -*-
"""Der Kern: verbindet Datenbank, Protokoll, Supervisor, Aufgaben, Wallet, Finanzen, Agenten.

Wichtig (Abschnitt 6.3): Der Systemstatus hängt NICHT vom Wallet ab. Ein Wallet-Stand von null
oder darunter ändert nichts an der Lauffähigkeit.
"""

import datetime
import os
import platform
import time

from . import VERSION, konfig
from .agenten import standard_register
from .aufgaben import Aufgaben
from .berechtigungen import Supervisor
from .db import Datenbank, jetzt
from .einstellungen import Einstellungen
from .finanzen import Finanzen
from .gedaechtnis import Gedaechtnis, Ziele
from .modell import Modellschicht
from .protokoll import Protokoll
from .wallet import Wallet


class Kern:
    def __init__(self, db_pfad=None):
        self.start_zeit = time.time()
        self.db = Datenbank(db_pfad)
        self.protokoll = Protokoll(self.db)
        self.einstellungen = Einstellungen(self.db, self.protokoll)
        self.register = standard_register()
        self.register.in_db_spiegeln(self.db)
        self.supervisor = Supervisor(self.db, self.protokoll, self.einstellungen, self.register.rechte)
        self.aufgaben = Aufgaben(self.db, self.protokoll)
        self.gedaechtnis = Gedaechtnis(self.db, self.protokoll)
        self.ziele = Ziele(self.db, self.protokoll)
        self.wallet = Wallet(self.db, self.protokoll, self.einstellungen)
        self.wallet.einrichten()
        self.finanzen = Finanzen(self.db, self.protokoll)
        self.modell = Modellschicht(self.db, self.protokoll, self.einstellungen)
        self.orchestrator = None
        wieder = self.aufgaben.wiederherstellen()
        self.protokoll.info("kern", "System gestartet", {"version": VERSION, "wiederherstellung": wieder})

    def status(self):
        """Echter Systemstatus – bewusst unabhängig vom Wallet."""
        zahlen = self.aufgaben.zaehlen()
        warnungen = []
        db_ok = self.db.integritaet()
        if not db_ok:
            warnungen.append("Datenbank-Integritätsprüfung fehlgeschlagen")
        offene_freigaben = self.db.wert("SELECT COUNT(*) FROM freigaben WHERE status='offen'")
        if offene_freigaben:
            warnungen.append("%d Freigabe(n) warten auf deine Entscheidung" % offene_freigaben)
        if zahlen["fehlgeschlagen"]:
            warnungen.append("%d Aufgabe(n) fehlgeschlagen" % zahlen["fehlgeschlagen"])
        grenze = (datetime.datetime.now().astimezone() - datetime.timedelta(days=1)).isoformat(timespec="seconds")
        fehler_24h = self.db.wert("SELECT COUNT(*) FROM protokoll WHERE ebene IN ('fehler','kritisch') "
                                  "AND zeit >= ?", (grenze,))
        letzte_sicherung = self._letzte_sicherung()
        if not letzte_sicherung:
            warnungen.append("Noch keine Sicherung vorhanden")
        orch = self.orchestrator.status() if self.orchestrator else {"laeuft": False}
        abgeschlossen = zahlen["abgeschlossen"]
        gesamt_aktiv = sum(zahlen.values()) - zahlen["abgebrochen"]
        return {
            "system": "AUTONOMOUS",
            "version": VERSION,
            "zeit": jetzt(),
            "betrieb": "laeuft" if db_ok else "gestoert",
            "laufzeit_sekunden": int(time.time() - self.start_zeit),
            "python": platform.python_version(),
            "datenbank": {"ok": db_ok, "schema_version": self.db.schema_version(),
                          "pfad": os.path.basename(self.db.pfad)},
            "orchestrator": orch,
            "aufgaben": zahlen,
            "fortschritt_prozent": round(100 * abgeschlossen / gesamt_aktiv) if gesamt_aktiv else 0,
            "offene_freigaben": offene_freigaben,
            "fehler_24h": fehler_24h,
            "modell": self.modell.status(),
            "agenten": len(self.register.rollen()),
            "letzte_sicherung": letzte_sicherung,
            "warnungen": warnungen,
            "wallet_hinweis": "Simulations-Wallet beeinflusst den Betrieb nicht.",
        }

    def _letzte_sicherung(self):
        ordner = konfig.unterordner("sicherungen")
        dateien = sorted(f for f in os.listdir(ordner) if f.endswith(".db"))
        return dateien[-1] if dateien else None

    def schliessen(self):
        if self.orchestrator:
            self.orchestrator.stoppen()
        self.protokoll.info("kern", "System beendet")
        self.db.schliessen()
