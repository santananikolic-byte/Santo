#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Der Mac als Kopf - suchen, lesen und ablegen auf dem ganzen Rechner.

Jarvis soll an alles herankommen, womit der Betrieb arbeitet: Angebote in
Ordnern, Tabellen, Verträge, Notizen. Dafür drei Werkzeuge:

* **suchen** (Spotlight) - lesend, ohne Freigabe
* **lesen** - lesend, ohne Freigabe, nur Textdateien
* **schreiben** - mit Freigabe, nur im eigenen Benutzerordner, nie über
  vorhandenes, nie in Startobjekte oder in Jarvis' eigenen Programmordner

Gesperrt bleibt, was Zugang zu anderen Dingen gibt: Schlüsselbund, SSH- und
Cloud-Schlüssel, Browser-Profile (Anmeldungen), Passwortdateien, ``.env``.
Das ist keine Misstrauenserklärung an den Nutzer, sondern an den Text, der in
einer Datei oder Mail stehen kann: Wer Jarvis über eine Datei etwas
einflüstern will, soll keine Schlüssel abgreifen können. Die Sperrliste
wirkt auch über Verknüpfungen hinweg, weil der echte Pfad geprüft wird.
"""

import os
import shutil
import subprocess
from pathlib import Path

import config

MAX_LESEN = 20000
MAX_DATEIGROESSE = 8 * 1024 * 1024
MAX_SCHREIBEN = 200000
MAX_TREFFER = 25

# Teile des (kleingeschriebenen) echten Pfades, die nie gelesen werden.
GESPERRT_TEILE = (
    "/.ssh/", "/.gnupg/", "/.aws/", "/.kube/", "/.docker/", "/.config/gh/",
    "/.netrc", "/.npmrc", "/.pypirc", "/.git-credentials", "/.gitconfig-credentials",
    "/library/keychains", "/library/cookies", "/library/safari",
    "/library/application support/google/chrome",
    "/library/application support/firefox",
    "/library/application support/microsoft edge",
    "/library/application support/com.apple.sharedfilelist",
    "/library/containers/com.apple.safari",
    "/library/group containers/group.com.apple.notes",  # Notizen laufen über eigene Wege
    "/id_rsa", "/id_ed25519", "/id_ecdsa", "/id_dsa",
)
GESPERRT_ENDUNGEN = (".pem", ".key", ".p12", ".pfx", ".keychain", ".keychain-db",
                     ".kdbx", ".ovpn", ".env")
GESPERRT_NAMEN = (".env", "mcp_servers.json")

# Hier wird nie geschrieben (relativ zum Benutzerordner, kleingeschrieben).
SCHREIBEN_GESPERRT = (
    "library/launchagents", "library/launchdaemons", "library/preferences",
    ".zshrc", ".zprofile", ".zshenv", ".bashrc", ".bash_profile", ".profile",
    ".ssh", ".gnupg", ".aws", ".config", "library/keychains", "library/application support",
)


class MacZugriff:
    """Lesender und schreibender Zugriff mit Sperrliste."""

    def __init__(self, benutzerordner=None, programmordner=None):
        self.home = Path(benutzerordner or Path.home()).resolve()
        self.programm = Path(programmordner or config.BASIS).resolve()

    # -- Prüfung ------------------------------------------------------------

    def _aufloesen(self, pfad: str):
        roh = os.path.expanduser(str(pfad or "").strip())
        if not roh:
            return None
        if not os.path.isabs(roh):
            roh = str(self.home / roh)
        try:
            return Path(roh).resolve()
        except (OSError, RuntimeError):
            return None

    def gesperrt(self, ziel: Path) -> str:
        """Warum ein Pfad nicht gelesen wird - leer, wenn er erlaubt ist."""
        text = str(ziel).lower() + ("/" if ziel.is_dir() else "")
        if "/" + ziel.name.lower() in text and ziel.name.lower() in GESPERRT_NAMEN:
            return "Diese Datei enthält Zugangsdaten."
        for teil in GESPERRT_TEILE:
            if teil in text or text.endswith(teil):
                return "Dieser Bereich enthält Schlüssel oder Anmeldungen und bleibt gesperrt."
        if ziel.suffix.lower() in GESPERRT_ENDUNGEN:
            return "Dateien dieser Art enthalten Schlüssel oder Passwörter und bleiben gesperrt."
        try:
            ziel.relative_to(self.programm / "config")
            return "Die Konfiguration von Jarvis enthält Schlüssel und bleibt gesperrt."
        except ValueError:
            pass
        return ""

    # -- Lesen --------------------------------------------------------------

    def lesen(self, pfad: str) -> dict:
        ziel = self._aufloesen(pfad)
        if ziel is None:
            return {"ok": False, "fehler": "Sag mir, welche Datei."}
        grund = self.gesperrt(ziel)
        if grund:
            return {"ok": False, "fehler": grund}
        if not ziel.is_file():
            return {"ok": False, "fehler": "Die Datei '%s' gibt es nicht." % pfad}
        try:
            groesse = ziel.stat().st_size
            if groesse > MAX_DATEIGROESSE:
                return {"ok": False, "fehler": "Die Datei ist mit %d Megabyte zu groß zum Lesen."
                                               % (groesse // (1024 * 1024))}
            with open(ziel, "rb") as datei:
                roh = datei.read(MAX_LESEN * 4)
        except OSError as fehler:
            return {"ok": False, "fehler": "Nicht lesbar: %s" % fehler}
        if b"\x00" in roh[:4000]:
            return {"ok": False, "fehler": "Das ist keine Textdatei (%s). Ich lese nur Text."
                                           % (ziel.suffix or "ohne Endung")}
        text = roh.decode("utf-8", errors="replace")
        return {"ok": True, "pfad": str(ziel), "inhalt": text[:MAX_LESEN],
                "gekuerzt": len(text) > MAX_LESEN or groesse > len(roh), "groesse": groesse}

    # -- Suchen -------------------------------------------------------------

    def suchen(self, begriff: str, ordner: str = "", im_inhalt: bool = False) -> dict:
        begriff = (begriff or "").strip()
        if len(begriff) < 2:
            return {"ok": False, "fehler": "Nach was soll ich suchen?"}
        wurzel = self._aufloesen(ordner) if ordner else self.home
        if wurzel is None or not wurzel.is_dir():
            return {"ok": False, "fehler": "Den Ordner '%s' gibt es nicht." % ordner}
        pfade = []
        if shutil.which("mdfind"):
            befehl = ["mdfind", "-onlyin", str(wurzel)]
            befehl += [begriff] if im_inhalt else ["-name", begriff]
            try:
                ausgabe = subprocess.run(befehl, capture_output=True, text=True, timeout=25,
                                         shell=False).stdout
                pfade = [z for z in ausgabe.splitlines() if z.strip()]
            except (OSError, subprocess.SubprocessError):
                pfade = []
        else:
            pfade = self._durchsuchen(wurzel, begriff.lower(), im_inhalt)
        treffer = []
        for roh in pfade:
            ziel = self._aufloesen(roh)
            if ziel is None or self.gesperrt(ziel):
                continue
            if wurzel in ziel.parents and any(
                    t.startswith(".") for t in ziel.relative_to(wurzel).parts):
                continue
            try:
                info = ziel.stat()
            except OSError:
                continue
            treffer.append({"pfad": str(ziel), "ordner": ziel.is_dir(),
                            "groesse": info.st_size, "geaendert": int(info.st_mtime)})
            if len(treffer) >= MAX_TREFFER:
                break
        text = ("%d Treffer, zum Beispiel %s." % (len(treffer), treffer[0]["pfad"])
                if treffer else "Dazu habe ich nichts gefunden.")
        return {"ok": True, "treffer": treffer, "text": text}

    def _durchsuchen(self, wurzel: Path, begriff: str, im_inhalt: bool) -> list:
        """Notlösung ohne Spotlight: begrenzt und ohne versteckte Ordner."""
        gefunden, besucht = [], 0
        for ordner, unterordner, dateien in os.walk(wurzel):
            unterordner[:] = [u for u in unterordner if not u.startswith(".")]
            for name in dateien + unterordner:
                besucht += 1
                if besucht > 20000:
                    return gefunden
                voll = os.path.join(ordner, name)
                if begriff in name.lower():
                    gefunden.append(voll)
                elif im_inhalt and name in dateien:
                    try:
                        if os.path.getsize(voll) < 200000 and begriff in open(
                                voll, "rb").read().decode("utf-8", "ignore").lower():
                            gefunden.append(voll)
                    except OSError:
                        pass
                if len(gefunden) >= MAX_TREFFER * 3:
                    return gefunden
        return gefunden

    # -- Schreiben ----------------------------------------------------------

    def schreiben_pruefen(self, pfad: str, ueberschreiben: bool = False) -> dict:
        """Prüft, ob dort geschrieben werden dürfte - ohne etwas zu tun."""
        ziel = self._aufloesen(pfad)
        if ziel is None:
            return {"ok": False, "fehler": "Sag mir, wohin."}
        if self.home not in ziel.parents:
            return {"ok": False, "fehler": "Geschrieben wird nur im Benutzerordner."}
        relativ = str(ziel.relative_to(self.home)).lower()
        for teil in SCHREIBEN_GESPERRT:
            if relativ == teil or relativ.startswith(teil + "/"):
                return {"ok": False, "fehler": "In diesen Bereich schreibe ich nicht: "
                                               "Dort liegen Startobjekte, Schlüssel oder Einstellungen."}
        if self.gesperrt(ziel):
            return {"ok": False, "fehler": self.gesperrt(ziel)}
        for geschuetzt in ("src", "config", "tests"):
            try:
                ziel.relative_to(self.programm / geschuetzt)
                return {"ok": False, "fehler": "Jarvis ändert sein eigenes Programm nicht."}
            except ValueError:
                pass
        if ziel == self.programm / "jarvis.py":
            return {"ok": False, "fehler": "Jarvis ändert sein eigenes Programm nicht."}
        if ziel.exists() and not ueberschreiben:
            return {"ok": False, "fehler": "Die Datei gibt es schon. Soll sie ersetzt werden, "
                                           "sag das ausdrücklich."}
        if ziel.is_dir():
            return {"ok": False, "fehler": "Das ist ein Ordner."}
        if not ziel.parent.is_dir():
            return {"ok": False, "fehler": "Der Ordner %s gibt es nicht. Ich lege keine neuen an."
                                           % ziel.parent}
        return {"ok": True, "ziel": ziel}

    def schreiben(self, pfad: str, inhalt: str, ueberschreiben: bool = False) -> dict:
        inhalt = inhalt if inhalt is not None else ""
        if not str(inhalt).strip():
            return {"ok": False, "fehler": "Der Inhalt ist leer."}
        if len(inhalt) > MAX_SCHREIBEN:
            return {"ok": False, "fehler": "Der Text ist zu lang."}
        pruefung = self.schreiben_pruefen(pfad, ueberschreiben)
        if not pruefung["ok"]:
            return pruefung
        ziel = pruefung["ziel"]
        try:
            ziel.write_text(inhalt, encoding="utf-8")
        except OSError as fehler:
            return {"ok": False, "fehler": "Nicht schreibbar: %s" % fehler}
        return {"ok": True, "pfad": str(ziel), "zeichen": len(inhalt),
                "text": "Gespeichert: %s." % ziel}
