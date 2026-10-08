#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Der Mac als Kopf - suchen, lesen und ablegen auf dem ganzen Rechner.

Jarvis soll an alles herankommen, womit der Betrieb arbeitet: Angebote in
Ordnern, Tabellen, Verträge, Notizen. Dafür diese Werkzeuge:

* **suchen** (Spotlight) - lesend, ohne Freigabe
* **lesen** - lesend, ohne Freigabe, nur Textdateien
* **schreiben** - mit Freigabe, nur in Dokumente, Schreibtisch und Downloads
  (oder Ordnern, die der Nutzer ausdrücklich nennt), nie über Vorhandenes
* **oeffnen** - eine Datei mit dem passenden Programm öffnen. Es gilt eine
  POSITIVLISTE (Dokumente, Bilder, Medien) und nie eine Sperrliste: Programme,
  Skripte, Installationspakete und alles Unbekannte bleiben zu.
* **ordnen** - Dateien eines Ordners (nur oberste Ebene) in Unterordner
  sortieren: erst ein Plan (``ordnen_planen``, verschiebt nichts), dann mit
  Freigabe ausführen (``ordnen_ausfuehren``), jederzeit rückgängig
  (``ordnen_rueckgaengig``). Es wird nur verschoben - nie gelöscht und nie
  etwas überschrieben. Plan und Protokoll liegen in der Datenbank.

Gesperrt bleibt, was Zugang zu anderen Dingen gibt: Schlüsselbund, SSH- und
Cloud-Schlüssel, Browser-Profile (Anmeldungen), Passwortdateien, ``.env``.
Das ist keine Misstrauenserklärung an den Nutzer, sondern an den Text, der in
einer Datei oder Mail stehen kann: Wer Jarvis über eine Datei etwas
einflüstern will, soll keine Schlüssel abgreifen können. Die Sperrliste
wirkt auch über Verknüpfungen hinweg, weil der echte Pfad geprüft wird.
"""

import json
import os
import re
import shutil
import sqlite3
import subprocess
import threading
import unicodedata
from datetime import datetime
from pathlib import Path

import config
from modules.memory import db_schema_anlegen, db_verbindung, zeitstempel

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
    "/.config/", "/.local/share/", "/browserprofil/", "/library/messages/",
    "/library/mail/", "/library/application support/addressbook",
    "/.zsh_history", "/.bash_history", "/.python_history", "/.node_repl_history",
    "/.psql_history", "/.mysql_history", "/.lesshst", "/.zsh_sessions/",
)
GESPERRT_ENDUNGEN = (".pem", ".key", ".p12", ".pfx", ".keychain", ".keychain-db",
                     ".kdbx", ".ovpn", ".env")
GESPERRT_NAMEN = (".env", "mcp_servers.json", ".zshrc", ".zprofile", ".zshenv", ".zlogin",
                  ".zlogout", ".bashrc", ".bash_profile", ".bash_login", ".bash_logout",
                  ".profile")
# Wörter im Dateinamen, die auf Zugangsdaten deuten.
GESPERRT_WORTE = ("credential", "secret", "token", "passw", "kennw", "zugangsdaten",
                  "kennung", "pin-", "tan-liste", "recovery", "wiederherstellung")

# Nur hier wird geschrieben (relativ zum Benutzerordner). Weitere Ordner nennt der
# Nutzer selbst in MAC_SCHREIBORDNER - eine Positivliste ist sicherer als jede Sperrliste.
SCHREIB_ORDNER = ("documents", "desktop", "downloads")

# Hier wird nie geschrieben, auch nicht über MAC_SCHREIBORDNER (kleingeschrieben).
SCHREIBEN_GESPERRT = (
    "library/launchagents", "library/launchdaemons", "library/preferences",
    ".zshrc", ".zprofile", ".zshenv", ".bashrc", ".bash_profile", ".profile",
    ".ssh", ".gnupg", ".aws", ".config", "library/keychains", "library/application support",
    ".zlogin", ".zlogout", ".bash_login", ".bash_logout", "library",
)


# -- Datei öffnen: POSITIVLISTE ---------------------------------------------
# Erlaubt ist nur, was ein Dokument, ein Bild oder ein Medium ist. Alles andere
# (Programme, Skripte, Pakete, Kurzbefehle, Profile, unbekannte Endungen) bleibt zu -
# eine Sperrliste vergisst immer etwas (.shortcut, .mobileconfig, .scptd, .zsh ...).
OEFFNEN_DOKUMENTE = (".pdf", ".txt", ".md", ".rtf", ".doc", ".docx", ".odt", ".pages",
                     ".xls", ".xlsx", ".ods", ".numbers", ".csv",
                     ".ppt", ".pptx", ".key", ".odp")
OEFFNEN_BILDER = (".jpg", ".jpeg", ".png", ".gif", ".heic", ".webp", ".tiff", ".bmp")
OEFFNEN_MEDIEN = (".mp3", ".m4a", ".wav", ".mp4", ".mov")
OEFFNEN_ERLAUBT = frozenset(OEFFNEN_DOKUMENTE + OEFFNEN_BILDER + OEFFNEN_MEDIEN)
OEFFNEN_ABLEHNUNG = ("Programme, Skripte und Installationspakete öffne ich nicht – nur Dokumente, "
                     "Bilder und Medien (zum Beispiel PDF, Word, Excel, Fotos, Musik, Video).")
# Nur dieser Teil der Library darf geöffnet werden: iCloud Drive.
OEFFNEN_LIBRARY_FREI = "library/mobile documents/"

# -- Ordnen ------------------------------------------------------------------
ORDNEN_REGELN = ("nach_typ", "nach_monat", "nach_kunde")
ORDNEN_MAX_ZUEGE = 200
ORDNEN_MAX_ANZEIGE = 20       # so viele Züge nennt eine Liste, dann "und N weitere"
ORDNEN_MAX_EINTRAEGE = 20000  # so viele Einträge eines Ordners werden höchstens gelesen
ORDNEN_TYP_ENDUNGEN = {
    "PDF": (".pdf",),
    "Bilder": (".jpg", ".jpeg", ".png", ".gif", ".heic", ".heif", ".webp", ".tif", ".tiff",
              ".bmp", ".svg"),
    "Tabellen": (".xls", ".xlsx", ".xlsm", ".ods", ".numbers", ".csv", ".tsv"),
    "Texte": (".txt", ".md", ".rtf", ".doc", ".docx", ".odt", ".pages"),
    "Archive": (".zip", ".rar", ".7z", ".tar", ".gz", ".tgz", ".bz2", ".xz"),
}
ORDNEN_SONSTIGES = "Sonstiges"
# Angefangene Downloads und Sperrdateien von Office werden nicht angefasst.
ORDNEN_UNFERTIG = (".crdownload", ".part", ".download", ".opdownload", ".tmp", ".partial")

SCHEMA_ORDNEN = """
CREATE TABLE IF NOT EXISTS ordnungsplaene (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ordner TEXT NOT NULL,
    regel TEXT NOT NULL,
    zuege_json TEXT NOT NULL,
    angelegt TEXT NOT NULL,
    status TEXT DEFAULT 'geplant'
);
CREATE TABLE IF NOT EXISTS ordnungs_protokoll (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    plan_id INTEGER NOT NULL,
    von TEXT NOT NULL,
    nach TEXT NOT NULL,
    zeit TEXT NOT NULL,
    zurueck TEXT DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_ordnungs_protokoll_plan ON ordnungs_protokoll(plan_id);
"""

# Ein Plan wird nie von zwei Fäden gleichzeitig ausgeführt oder zurückgenommen.
_ORDNEN_SPERRE = threading.Lock()


def _ordnen_normal(text) -> str:
    """Name zum Vergleichen: zusammengesetzte Zeichen (der Mac liefert oft getrennte Umlaute),
    klein, alles außer Buchstaben und Ziffern wird zu einem Leerzeichen."""
    roh = unicodedata.normalize("NFC", str(text or "")).casefold()
    return " ".join(re.sub(r"[\W_]+", " ", roh).split())


def _ordnen_ordnername(text) -> str:
    """Ein Firmenname als Ordnername: ohne Pfadzeichen, nicht versteckt, höchstens 60 Zeichen."""
    name = unicodedata.normalize("NFC", str(text or ""))
    name = re.sub(r"[\x00-\x1f\x7f/\\:*?\"<>|]+", " ", name)
    name = " ".join(name.split()).lstrip(". ").rstrip(". ")
    return name[:60].rstrip(". ")


def _ordnen_ebene(wurzel: Path, pfad: Path):
    """Wie viele Namen ``pfad`` unter ``wurzel`` liegt (1 = direkt darin) - ``None``, wenn nicht darunter."""
    try:
        return len(Path(pfad).relative_to(wurzel).parts)
    except ValueError:
        return None


def _ordnen_plan_nummer(plan_id):
    """Die Nummer eines Plans als ganze Zahl - ``None``, wenn das keine Nummer ist."""
    if isinstance(plan_id, bool) or plan_id is None:
        return None
    try:
        nummer = int(str(plan_id).strip())
    except (TypeError, ValueError):
        return None
    return nummer if nummer > 0 else None


def _ordnen_zeile(zug: dict, wurzel) -> str:
    """Ein Zug als lesbare Zeile: ``Rechnung.pdf → PDF/``."""
    von, nach = Path(str(zug.get("von", ""))), Path(str(zug.get("nach", "")))
    try:
        unter = nach.parent.relative_to(wurzel)
        return "%s → %s/" % (von.name, unter)
    except ValueError:
        return "%s → %s" % (von.name, nach)


def _ordnen_standard_oeffner(befehl: list):
    """Startet ``open`` ohne Shell. Gibt ``(Rückgabecode, Fehlertext)`` zurück."""
    lauf = subprocess.run(befehl, capture_output=True, text=True, timeout=20, shell=False)
    return getattr(lauf, "returncode", 0), str(getattr(lauf, "stderr", "") or "").strip()


def _ordnen_oeffner_antwort(antwort) -> tuple:
    """Macht aus der Antwort eines (eingespeisten) Öffners ``(Code, Text)``."""
    if antwort is None or antwort is True:
        return 0, ""
    if antwort is False:
        return 1, ""
    if isinstance(antwort, int):
        return antwort, ""
    if isinstance(antwort, (tuple, list)):
        code = antwort[0] if antwort else 0
        text = antwort[1] if len(antwort) > 1 else ""
        return (code if isinstance(code, int) else 0), str(text or "").strip()
    return getattr(antwort, "returncode", 0) or 0, str(getattr(antwort, "stderr", "") or "").strip()


def _unter(pfad: Path, basis: Path) -> bool:
    """Liegt ``pfad`` in ``basis`` (oder ist es)? Ohne Rücksicht auf Groß- und Kleinschreibung,
    denn das Dateisystem des Macs unterscheidet sie normalerweise nicht."""
    a, b = str(pfad).lower().rstrip("/"), str(basis).lower().rstrip("/")
    return a == b or a.startswith(b + "/")


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
        name = ziel.name.lower()
        if name in GESPERRT_NAMEN or name.startswith(".env") or ".env." in name:
            return "Diese Datei enthält Zugangsdaten."
        if any(wort in name for wort in GESPERRT_WORTE):
            return "Der Name deutet auf Zugangsdaten. Diese Datei bleibt gesperrt."
        for teil in GESPERRT_TEILE:
            if teil in text or text.endswith(teil):
                return "Dieser Bereich enthält Schlüssel oder Anmeldungen und bleibt gesperrt."
        if ziel.suffix.lower() in GESPERRT_ENDUNGEN:
            return "Dateien dieser Art enthalten Schlüssel oder Passwörter und bleiben gesperrt."
        if _unter(ziel, self.programm / "config"):
            return "Die Konfiguration von Jarvis enthält Schlüssel und bleibt gesperrt."
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

    def schreib_ordner(self) -> list:
        """Die Ordner, in die geschrieben werden darf."""
        namen = list(SCHREIB_ORDNER)
        for extra in str(config.MAC_SCHREIBORDNER or "").split(","):
            extra = extra.strip().strip("/")
            if extra and ".." not in extra:
                namen.append(extra.lower())
        return [self.home / n for n in namen]

    def schreiben_pruefen(self, pfad: str, ueberschreiben: bool = False) -> dict:
        """Prüft, ob dort geschrieben werden dürfte - ohne etwas zu tun."""
        ziel = self._aufloesen(pfad)
        if ziel is None:
            return {"ok": False, "fehler": "Sag mir, wohin."}
        if _unter(ziel, self.programm):
            return {"ok": False, "fehler": "Jarvis ändert nichts in seinem eigenen Programmordner."}
        if not any(_unter(ziel, ordner) and not _unter(ordner, ziel) for ordner in self.schreib_ordner()):
            return {"ok": False, "fehler": "Ich schreibe nur in Dokumente, Schreibtisch und Downloads. "
                                           "Weitere Ordner kannst du in MAC_SCHREIBORDNER freigeben."}
        relativ = str(ziel).lower()[len(str(self.home).lower()):].lstrip("/")
        for teil in SCHREIBEN_GESPERRT:
            if relativ == teil or relativ.startswith(teil + "/"):
                return {"ok": False, "fehler": "In diesen Bereich schreibe ich nicht: "
                                               "Dort liegen Startobjekte, Schlüssel oder Einstellungen."}
        if self.gesperrt(ziel):
            return {"ok": False, "fehler": self.gesperrt(ziel)}
        if ziel.exists() and not ueberschreiben:
            return {"ok": False, "fehler": "Die Datei gibt es schon. Soll sie ersetzt werden, "
                                           "sag das ausdrücklich."}
        if ziel.is_dir():
            return {"ok": False, "fehler": "Das ist ein Ordner."}
        if not ziel.parent.is_dir():
            return {"ok": False, "fehler": "Den Ordner %s gibt es nicht. Ich lege keine neuen an."
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
