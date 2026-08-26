#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Zeitplan - automatische Briefings und geplante Routinen.

Bewusst ein Hintergrund-Thread statt cron: cron müsste eingerichtet werden, kennt
die laufende Sitzung nicht und hinterlässt beim Deinstallieren Reste.

Zwei Entscheidungen, die den Alltag betreffen:

* **Vergangenes wird nicht nachgeholt.** Liegt ein Zeitpunkt mehr als 120 Minuten
  zurück, wird der Job übersprungen. Ein Morgenbriefing um 15 Uhr hilft niemandem.
* **Beim Start gilt alles Heutige als erledigt**, was schon vorbei ist. Sonst
  würde jeder Neustart am Abend das Morgenbriefing nachschieben.
"""

import threading
import time
import traceback
from datetime import datetime

import config
from modules.memory import heute_datum

# Wie lange ein Job nach seiner Zeit noch nachgeholt werden darf.
MAX_VERSPAETUNG_MINUTEN = 120
# Wie oft der Zeitplan nachsieht.
PRUEF_ABSTAND_SEKUNDEN = 30


def minuten_seit(uhrzeit: str, jetzt: datetime = None):
    """Minuten seit dem heutigen Zeitpunkt ``uhrzeit``. Negativ heißt: noch nicht."""
    jetzt = jetzt or datetime.now()
    try:
        stunde, minute = [int(teil) for teil in str(uhrzeit).split(":")[:2]]
    except (ValueError, TypeError):
        return None
    zeitpunkt = jetzt.replace(hour=stunde, minute=minute, second=0, microsecond=0)
    return (jetzt - zeitpunkt).total_seconds() / 60.0


def ist_faellig(uhrzeit: str, jetzt: datetime = None) -> bool:
    """Ist der Zeitpunkt erreicht und noch nicht zu lange her?

    9:00-Job um 9:30 abgefragt: ja. Um 8:00: nein, noch nicht.
    Um 14:00: nein, zu spät - das wird nicht nachgeholt.
    """
    versaeumt = minuten_seit(uhrzeit, jetzt)
    if versaeumt is None:
        return False
    return 0 <= versaeumt <= MAX_VERSPAETUNG_MINUTEN


class Scheduler:
    """Führt Briefings und zeitgesteuerte Routinen im Hintergrund aus."""

    def __init__(self, agent=None, routines=None, ausgabe=None):
        self.agent = agent
        self.routines = routines
        # ``ausgabe`` bekommt jeden erzeugten Text - im Dauerbetrieb die Stimme.
        self.ausgabe = ausgabe or (lambda text: print("[zeitplan] %s" % text))
        self.jobs = {}
        self._laeuft = False
        self._thread = None
        self._sperre = threading.Lock()

    # -- Jobs verwalten -----------------------------------------------------

    def job_anlegen(self, name: str, uhrzeit: str, aufgabe, beschreibung: str = "") -> bool:
        """Trägt einen Job ein. ``aufgabe`` ist eine Funktion ohne Argumente."""
        if not uhrzeit or not callable(aufgabe):
            return False
        with self._sperre:
            self.jobs[name] = {"uhrzeit": uhrzeit, "aufgabe": aufgabe,
                               "beschreibung": beschreibung or name, "zuletzt": ""}
        return True

    def job_entfernen(self, name: str) -> bool:
        """Nimmt einen Job wieder heraus."""
        with self._sperre:
            return self.jobs.pop(name, None) is not None

    def standardjobs_anlegen(self):
        """Legt Morgen- und Abendbriefing aus der Konfiguration an."""
        if config.BRIEFING_MORGENS:
            self.job_anlegen("morgenbriefing", config.BRIEFING_MORGENS,
                             self._morgenbriefing, "Morgenbriefing")
        if config.BRIEFING_ABENDS:
            self.job_anlegen("abendrueckblick", config.BRIEFING_ABENDS,
                             self._abendrueckblick, "Abendrückblick")

    def routinen_einhaengen(self):
        """Hängt alle Routinen mit Uhrzeit in den Zeitplan."""
        if self.routines is None:
            return 0
        anzahl = 0
        for zeile in self.routines.geplante_routinen():
            name = "routine:%s" % zeile["name"]
            if self.job_anlegen(name, zeile["uhrzeit"],
                                self._routine_starter(zeile["name"]),
                                "Routine %s" % zeile["name"]):
                anzahl += 1
        return anzahl

    def _routine_starter(self, routinen_name: str):
        """Baut die Funktion, die eine bestimmte Routine startet."""
        def starten():
            ergebnis = self.routines.routine_ausfuehren(routinen_name, self.agent)
            return ergebnis.get("text") or ergebnis.get("fehler", "")
        return starten

    # -- Ablauf -------------------------------------------------------------

    def vergangenes_abhaken(self, jetzt: datetime = None):
        """Markiert alles, was heute schon vorbei ist, als erledigt."""
        jetzt = jetzt or datetime.now()
        heute = jetzt.strftime("%Y-%m-%d")
        with self._sperre:
            for job in self.jobs.values():
                versaeumt = minuten_seit(job["uhrzeit"], jetzt)
                if versaeumt is not None and versaeumt > 0:
                    job["zuletzt"] = heute

    def faellige_jobs(self, jetzt: datetime = None) -> list:
        """Namen aller Jobs, die jetzt laufen müssten und heute noch nicht liefen."""
        jetzt = jetzt or datetime.now()
        heute = jetzt.strftime("%Y-%m-%d")
        faellig = []
        with self._sperre:
            for name, job in self.jobs.items():
                if job["zuletzt"] == heute:
                    continue
                if ist_faellig(job["uhrzeit"], jetzt):
                    faellig.append(name)
        return faellig

    def job_ausfuehren(self, name: str) -> str:
        """Führt einen Job aus und merkt sich das Datum."""
        with self._sperre:
            job = self.jobs.get(name)
        if not job:
            return ""
        try:
            ergebnis = job["aufgabe"]()
        except Exception as fehler:  # Ein kaputter Job darf den Zeitplan nicht stoppen.
            ergebnis = "Der Job %s ist fehlgeschlagen: %s" % (job["beschreibung"], fehler)
            print("[zeitplan] %s\n%s" % (ergebnis, traceback.format_exc()))
        with self._sperre:
            job["zuletzt"] = heute_datum()
        text = str(ergebnis or "").strip()
        if text:
            try:
                self.ausgabe(text)
            except Exception as fehler:
                print("[zeitplan] Ausgabe fehlgeschlagen: %s" % fehler)
        return text

    def einmal_pruefen(self, jetzt: datetime = None) -> list:
        """Ein Durchlauf: alles Fällige ausführen. Gibt die Jobnamen zurück."""
        gelaufen = []
        for name in self.faellige_jobs(jetzt):
            self.job_ausfuehren(name)
            gelaufen.append(name)
        return gelaufen

    def _schleife(self):
        """Die Hintergrundschleife - alle 30 Sekunden nachsehen."""
        while self._laeuft:
            try:
                self.einmal_pruefen()
            except Exception as fehler:
                print("[zeitplan] Fehler in der Schleife: %s" % fehler)
            for _ in range(PRUEF_ABSTAND_SEKUNDEN):
                if not self._laeuft:
                    break
                time.sleep(1)

    def start(self) -> bool:
        """Startet den Zeitplan im Hintergrund."""
        if self._laeuft:
            return False
        self.standardjobs_anlegen()
        self.routinen_einhaengen()
        self.vergangenes_abhaken()
        self._laeuft = True
        self._thread = threading.Thread(target=self._schleife, daemon=True,
                                        name="jarvis-zeitplan")
        self._thread.start()
        return True

    def stop(self):
        """Hält den Zeitplan an."""
        self._laeuft = False
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=3)

    def uebersicht(self) -> list:
        """Was wann geplant ist - für Dashboard und Selbsttest."""
        with self._sperre:
            return [{"name": name, "uhrzeit": job["uhrzeit"],
                     "beschreibung": job["beschreibung"], "zuletzt": job["zuletzt"]}
                    for name, job in sorted(self.jobs.items(),
                                            key=lambda p: p[1]["uhrzeit"])]

    # -- Die beiden Briefings ----------------------------------------------

    def _morgenbriefing(self) -> str:
        """Der Text, den Jarvis morgens von sich aus sagt."""
        if self.agent is None:
            return "Guten Morgen. Ich bin da, aber noch nicht eingerichtet."
        return self.agent.briefing_morgens()

    def _abendrueckblick(self) -> str:
        """Der Text, den Jarvis abends von sich aus sagt."""
        if self.agent is None:
            return "Feierabend. Eingerichtet bin ich noch nicht."
        return self.agent.briefing_abends()
