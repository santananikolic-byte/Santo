# -*- coding: utf-8 -*-
"""Stimme - JARVIS spricht über macOS ``say``.

Der Server läuft auf demselben Mac wie der Browser, deshalb spielt ``say`` den
Ton direkt über die Mac-Lautsprecher ab, die der Nutzer hört. Es wird die beste
deutsche Stimme auf dem Mac gewählt (Premium/Enhanced/Siri), sonst die
Systemstimme.

Auf einem Rechner ohne ``say`` (etwa in der Testumgebung) ist die Stimme
einfach nicht verfügbar - der Server läuft trotzdem, nur ohne Ton.
``JARVIS_SAY`` kann auf ein Ersatzprogramm zeigen (für Tests).
"""

import os
import re
import shutil
import subprocess
import threading

WUNSCHSTIMMEN = ("Markus", "Yannick", "Viktor", "Martin", "Petra", "Anna", "Helena")


def _say_programm():
    return os.environ.get("JARVIS_SAY") or shutil.which("say")


class Stimme:
    def __init__(self, konfig):
        self.konfig = konfig
        self._prozess = None
        self._sperre = threading.Lock()
        self.programm = _say_programm()

    def verfuegbar(self):
        return bool(self.programm)

    def deutsche_stimmen(self):
        if not self.programm:
            return []
        try:
            ausgabe = subprocess.run([self.programm, "-v", "?"], capture_output=True, text=True, timeout=10).stdout
        except (OSError, subprocess.SubprocessError):
            return []
        namen = []
        for zeile in ausgabe.splitlines():
            treffer = re.match(r"^(.+?)\s+(de_[A-Z]{2})\s+#", zeile)
            if treffer:
                namen.append(treffer.group(1).strip())
        return namen

    def gute_stimmen(self):
        gut = [s for s in self.deutsche_stimmen() if re.search(r"Premium|Enhanced|Erweitert|Siri", s)]
        rang = {name: i for i, name in enumerate(WUNSCHSTIMMEN)}
        return sorted(gut, key=lambda s: rang.get(s.split(" (")[0], len(rang)))

    def gewaehlt(self):
        """Selbst gewählte Stimme, sonst die beste gute Stimme, sonst "" (Systemstimme)."""
        wunsch = (self.konfig.stimme or "").strip()
        if wunsch and wunsch in self.deutsche_stimmen():
            return wunsch
        gut = self.gute_stimmen()
        return gut[0] if gut else ""

    @staticmethod
    def _fuer_sprache(text):
        text = re.sub(r"https?://\S+", "", text)
        text = re.sub(r"[*_#`>|]", "", text)
        text = re.sub(r"[\U0001F000-\U0001FAFF☀-➿]", "", text)
        return re.sub(r"\s+", " ", text).strip()

    def stopp(self):
        with self._sperre:
            if self._prozess and self._prozess.poll() is None:
                self._prozess.terminate()
            self._prozess = None

    def sprich(self, text):
        """Spricht den Text. Gibt True zurück, wenn es wirklich losging."""
        if not self.programm:
            return False
        sauber = self._fuer_sprache(text)
        if not sauber:
            return False
        self.stopp()
        befehl = [self.programm, "-r", str(int(self.konfig.tempo or 185)), "-f", "-"]
        stimme = self.gewaehlt()
        if stimme:
            befehl[1:1] = ["-v", stimme]
        try:
            with self._sperre:
                self._prozess = subprocess.Popen(befehl, stdin=subprocess.PIPE,
                                                 stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                self._prozess.stdin.write(sauber.encode("utf-8"))
                self._prozess.stdin.close()
        except OSError:
            self._prozess = None
            return False
        return True

    def status(self):
        return {"verfuegbar": self.verfuegbar(), "stimme": self.gewaehlt() or None,
                "gewuenscht": (self.konfig.stimme or "") or None, "tempo": self.konfig.tempo,
                "vorlesen": bool(self.konfig.vorlesen), "auswahl": self.deutsche_stimmen()}
