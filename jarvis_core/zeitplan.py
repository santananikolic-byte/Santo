# -*- coding: utf-8 -*-
"""Zeitplan - Hintergrundarbeit, die nach der Uhr läuft.

Alle 15 Sekunden: offene Freigaben verfallen lassen, fällige Erinnerungen melden
(laut und als Mitteilung), geplante Aufträge in die Warteschlange stellen. Täglich
eine Sicherung der Datenbank (die letzten ``backup_aufbewahren`` bleiben).
"""

import datetime
import os
import threading

from . import routinen, selbst, zeit


class Zeitplan(threading.Thread):
    def __init__(self, agent, laeufer, intervall=15.0):
        super().__init__(daemon=True, name="jarvis-zeitplan")
        self.agent = agent
        self.laeufer = laeufer
        self.intervall = intervall
        self._stopp = threading.Event()

    def beenden(self):
        self._stopp.set()

    def run(self):
        while not self._stopp.is_set():
            try:
                self.tick()
            except Exception as fehler:  # noqa: BLE001 - der Zeitplan darf nie sterben
                self.agent.log.ereignis("zeitplan_fehler", "ERROR", grund=repr(fehler))
            self._stopp.wait(self.intervall)

    def tick(self):
        a = self.agent
        sp = a.speicher
        jetzt = zeit.jetzt()
        a.berechtigung.ablaufen_lassen()
        if not a.gesperrt.is_set():
            for erinnerung in sp.erinnerungen_faellig_markieren(jetzt):
                sp.audit_schreiben("erinnerung_faellig", bereich=erinnerung["bereich"], ergebnis=erinnerung["text"])
                a.log.ereignis("erinnerung_faellig", erinnerung=erinnerung["id"])
                a.benachrichtigen("Erinnerung", erinnerung["text"], sprechen=a.konfig.erinnerungen_sprechen)
            if sp.geplante_auftraege_faellig(jetzt):
                self.laeufer.wecken()
            self.routinen_pruefen()
            self.rueckblick_pruefen()
            a.erweiterungen.takt()  # jede Erweiterung einzeln abgesichert
        self.sicherung_falls_faellig()

    def routinen_pruefen(self, jetzt=None, warten=False):
        """Startet fällige Routinen (je höchstens einmal am Tag) - jede in einem eigenen Faden, damit der Zeitplan nicht
        auf das Denken wartet. Gibt die gestarteten Routinen zurück."""
        a = self.agent
        if a.gesperrt.is_set():
            return []
        jetzt = jetzt or datetime.datetime.now()
        gestartet = list(routinen.faellige(a.konfig.routinen, jetzt, lambda name: a.speicher.meta("routine:" + name)))
        faeden = []
        for r in gestartet:
            a.speicher.meta_setzen("routine:" + r["name"], jetzt.date().isoformat())  # zuerst merken: nie doppelt
            faden = threading.Thread(target=a.routine_ausfuehren, args=(r, jetzt), daemon=True, name="jarvis-routine")
            faden.start()
            faeden.append(faden)
        if warten:
            for faden in faeden:
                faden.join(120)
        return gestartet

    def rueckblick_pruefen(self, jetzt=None, warten=False):
        """Einmal am Tag (nur wenn etwas los war): Die Fakten des Tages kommen gezählt ins Tagebuch, danach sieht
        JARVIS in einem eigenen Gespräch auf seinen Tag zurück. Gibt True zurück, wenn der Rückblick gestartet ist."""
        a = self.agent
        if a.gesperrt.is_set():
            return False
        jetzt = jetzt or datetime.datetime.now()
        if not selbst.rueckblick_faellig(a.konfig, a.speicher, jetzt):
            return False
        a.speicher.meta_setzen("rueckblick", jetzt.date().isoformat())  # zuerst merken: nie doppelt
        fakten = selbst.tagesfakten(a.speicher)
        a.speicher.tagebuch_schreiben(selbst.fakten_eintrag(fakten, jetzt), art="fakten", tag=jetzt.date().isoformat())
        faden = threading.Thread(target=a.routine_ausfuehren, daemon=True, name="jarvis-rueckblick",
                                 args=({"name": "Tagesrückblick", "auftrag": selbst.rueckblick_auftrag(fakten)}, jetzt))
        faden.start()
        if warten:
            faden.join(120)
        return True

    def sicherung_falls_faellig(self):
        a = self.agent
        letzte = a.speicher.meta("letzte_sicherung")
        if letzte and letzte > zeit.vor_stunden(24):
            return None
        return self.sicherung_machen()

    def sicherung_machen(self):
        a = self.agent
        ziel = os.path.join(a.konfig.backup_ordner, "jarvis-%s.db" % datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%d-%H%M%S"))
        a.speicher.sichern(ziel)
        a.speicher.meta_setzen("letzte_sicherung", zeit.jetzt())
        dateien = sorted(f for f in os.listdir(a.konfig.backup_ordner) if f.startswith("jarvis-") and f.endswith(".db"))
        for alt in dateien[:-a.konfig.backup_aufbewahren]:
            try:
                os.remove(os.path.join(a.konfig.backup_ordner, alt))
            except OSError:
                pass
        a.speicher.audit_schreiben("sicherung", ergebnis=os.path.basename(ziel))
        a.log.ereignis("sicherung", datei=os.path.basename(ziel))
        return ziel
