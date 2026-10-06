#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Der Dienst - Jarvis läuft dauerhaft auf dem iMac, nur mit Stimme.

Das ist der Gegenentwurf zur Oberfläche: kein Fenster, kein Textfeld. Der
iMac ist der Kopf. Er startet beim Anmelden von selbst, bleibt wach, hört
zu, antwortet laut, arbeitet im Hintergrund weiter (Zeitplan, Autopilot) und
startet sich selbst neu, wenn er abstürzt oder hängt.

Drei Dinge machen das aus:

* **Der Dienst bei macOS** (``launchd``): ein Anmeldeobjekt, das Jarvis
  startet, wach hält (``caffeinate``) und nach einem Absturz neu startet. Nach
  einem gewollten Beenden ("Jarvis, schalte dich ab") bleibt er aus.
* **Freigaben per Stimme**: Ohne Fenster kann niemand auf "Ja" klicken. Jarvis
  sagt, was er tun will, und hört auf Ja oder Nein. Keine klare Antwort ist ein
  Nein, genau wie überall.
* **Der Ansager**: Meldungen von Zeitplan und Autopilot werden gesagt, wenn
  gerade nicht gesprochen wird - und die des Autopiloten nicht nachts.

Ein eigenes Betriebssystem schreibt Jarvis nicht, und das wäre auch das
falsche Mittel. Wer die Trennung will, legt am iMac einen eigenen Benutzer für
Jarvis an: eigener Ordner, eigener Schlüsselbund, eigene Rechte. Siehe
``docs/IMAC.md``.
"""

import json
import os
import plistlib
import re
import shutil
import subprocess
import sys
import threading
import time
from datetime import datetime
from pathlib import Path

import config
from modules.autopilot import in_ruhezeit

LABEL = "at.jarvis.imac"
HERZSCHLAG_GRENZE = 1800  # Sekunden ohne Lebenszeichen, dann Neustart

# Bewusst knapp: Wörter wie "bitte" (kann "Wie bitte?" heißen) oder "genau" zählen nicht als Ja.
JA_WOERTER = {"ja", "jo", "jawohl", "jep", "klar", "okay", "ok", "gerne", "gern",
              "einverstanden", "freigegeben", "genehmigt", "mach", "machs"}
NEIN_WOERTER = {"nein", "nee", "nö", "noe", "nicht", "stopp", "stop", "abbrechen",
                "lass", "lassen", "kein", "keine", "niemals", "nie", "halt", "warte",
                "falsch", "doch-nicht", "bloß", "bloss", "moment"}


def ja_nein(text: str):
    """``True`` für ein klares Ja, ``False`` für Nein oder Zweifel, ``None`` für nichts Verwertbares.

    Sicherheit vor Bequemlichkeit: Steht in der Antwort irgendein Nein-Wort,
    ist es ein Nein, auch wenn "ja" davor steht ("ja, aber nicht jetzt").
    """
    woerter = re.findall(r"[a-zäöüß]+", (text or "").lower())
    if not woerter:
        return None
    if any(w in NEIN_WOERTER for w in woerter):
        return False
    if any(w in JA_WOERTER for w in woerter):
        return True
    return None


def freigabe_ansage(aktion: str, details: str = "") -> str:
    """Was Jarvis vor einer Freigabe laut sagt. Nie der ganze Code, immer der Kern."""
    daten = None
    try:
        daten = json.loads(details) if details and details.lstrip().startswith("{") else None
    except ValueError:
        daten = None
    d = daten if isinstance(daten, dict) else {}

    if aktion == "mail_senden":
        return "Ich soll eine Mail an %s schicken, Betreff: %s." % (
            d.get("an", "jemanden"), d.get("betreff", "ohne Betreff"))
    if aktion == "termin_anlegen":
        return "Ich soll einen Termin anlegen: %s." % (d.get("titel") or d.get("betreff") or "ohne Titel")
    if aktion in ("anrufen", "sms_senden"):
        wer = d.get("name") or d.get("nummer") or "jemanden"
        if aktion == "anrufen":
            return "Ich soll %s anrufen." % wer
        return "Ich soll %s eine SMS schicken." % wer
    if aktion == "nachricht_senden":
        return "Ich soll eine Nachricht schicken."
    if aktion == "datei_schreiben":
        return "Ich soll die Datei %s anlegen." % (d.get("pfad", "an einem Ort"))
    if aktion == "skript_ausfuehren":
        # Der Kopf der Freigabefrage: "Skript x ausführen. Es will ins Netz." - der Code bleibt weg.
        kopf = (details or "").split("\n\n")[0].strip()
        return "%s Den Code kann ich dir nicht vorlesen, schau ihn dir in der Werkstatt an." % kopf
    if aktion == "bildschirm_bedienen":
        return "Ich soll den Bildschirm bedienen."
    if aktion in ("browser_auftrag", "browser_schritt"):
        return "Im Browser: %s" % (details or "ich soll etwas ausführen.")[:200]
    if aktion == "autopilot_schalten":
        return "Ich soll den Autopiloten %s." % ("einschalten" if d.get("an") else "ausschalten")
    return "Ich soll %s ausführen." % aktion.replace("_", " ")


class SprachFreigabe:
    """Freigaben ohne Fenster: Jarvis fragt laut, der Nutzer antwortet laut."""

    def __init__(self, stimme, profil=None, versuche: int = 2):
        self.stimme = stimme
        self.profil = profil
        self.versuche = versuche
        self.protokoll = []

    def _antwort_hoeren(self) -> str:
        pfad = self.stimme.aufnehmen_bis_pause(still_signal=False)
        if not pfad:
            return ""
        try:
            if self.profil is not None:
                pruefung = self.profil.ist_der_nutzer(pfad)
                if not pruefung.get("erkannt"):
                    return ""  # Eine fremde Stimme gibt nichts frei.
            return self.stimme.transkribieren(pfad)
        finally:
            try:
                os.remove(pfad)
            except OSError:
                pass

    def anfordern(self, aktion: str, details: str = "") -> dict:
        """Gleiche Schnittstelle wie Telegram und Browser: ``{"erlaubt": bool, "grund": str}``."""
        frage = freigabe_ansage(aktion, details) + " Soll ich? Sag ja oder nein."
        for versuch in range(max(1, self.versuche)):
            self.stimme.sprich(frage if versuch == 0 else "Das war nicht klar. Ja oder nein?")
            antwort = self._antwort_hoeren()
            urteil = ja_nein(antwort)
            if urteil is True:
                self.protokoll.append((aktion, True))
                return {"erlaubt": True, "grund": "Per Sprache freigegeben."}
            if urteil is False:
                self.protokoll.append((aktion, False))
                self.stimme.sprich("Gut, ich lasse es.")
                return {"erlaubt": False, "grund": "Per Sprache abgelehnt."}
        self.protokoll.append((aktion, False))
        self.stimme.sprich("Ich habe keine klare Antwort. Ich lasse es.")
        return {"erlaubt": False, "grund": "Keine klare Antwort - nichts ausgeführt."}


class Ansager:
    """Sammelt Meldungen und sagt sie, wenn gerade nicht gesprochen wird.

    Meldungen vom Autopiloten sind ``leise``: Nachts und außerhalb der
    Arbeitszeit bleiben sie liegen und kommen am nächsten Morgen. Ein
    Briefing um 6:45 dagegen wurde ausdrücklich bestellt und kommt sofort.
    """

    def __init__(self, stimme):
        self.stimme = stimme
        self._offen = []
        self._sperre = threading.Lock()

    def sagen(self, text: str):
        """Meldung, die sofort dran ist (beim nächsten ruhigen Moment)."""
        if text and str(text).strip():
            with self._sperre:
                self._offen.append((str(text).strip(), False))

    def leise(self, text: str):
        """Meldung, die nur zur Arbeitszeit gesagt wird."""
        if text and str(text).strip():
            with self._sperre:
                self._offen.append((str(text).strip(), True))

    def ausliefern(self, jetzt: datetime = None) -> int:
        """Sagt, was dran ist. Gibt die Zahl gesprochener Meldungen zurück."""
        jetzt = jetzt or datetime.now()
        with self._sperre:
            bereit = [m for m in self._offen if not (m[1] and in_ruhezeit(jetzt))]
            self._offen = [m for m in self._offen if m not in bereit]
        for text, _ in bereit:
            self.stimme.sprich(text)
        return len(bereit)

    def wartend(self) -> int:
        with self._sperre:
            return len(self._offen)


# -- Herzschlag --------------------------------------------------------------------

def herzschlag_abgelaufen(letzter: float, jetzt: float, grenze: int = HERZSCHLAG_GRENZE) -> bool:
    """Hat sich die Hauptschleife zu lange nicht gemeldet?"""
    return (jetzt - letzter) > grenze


class Herzschlag:
    """Schreibt Lebenszeichen und beendet den Prozess, wenn er hängt.

    ``launchd`` startet einen beendeten Prozess neu. Ein hängender (zum
    Beispiel in der Tonbibliothek) wäre dagegen für immer still.
    """

    def __init__(self, datei=None, grenze: int = HERZSCHLAG_GRENZE, beenden=None):
        self.datei = Path(datei or (config.LOG_VERZEICHNIS / "herzschlag"))
        self.grenze = grenze
        self.letzter = time.time()
        self._beenden = beenden or (lambda: os._exit(3))
        self._laeuft = False

    def schlagen(self):
        self.letzter = time.time()
        try:
            self.datei.parent.mkdir(parents=True, exist_ok=True)
            self.datei.write_text(str(int(self.letzter)), encoding="utf-8")
        except OSError:
            pass

    def pruefen(self, jetzt: float = None) -> bool:
        """Beendet bei Stillstand. Gibt ``True`` zurück, wenn es beendet hat."""
        if herzschlag_abgelaufen(self.letzter, jetzt if jetzt is not None else time.time(), self.grenze):
            print("[dienst] Kein Lebenszeichen seit %d Sekunden - ich starte neu." % self.grenze)
            self._beenden()
            return True
        return False

    def _wache(self):
        while self._laeuft:
            time.sleep(30)
            if self._laeuft and self.pruefen():
                return

    def start(self):
        self._laeuft = True
        self.schlagen()
        threading.Thread(target=self._wache, daemon=True, name="jarvis-herzschlag").start()

    def stop(self):
        self._laeuft = False


def logdatei_drehen(pfad, grenze: int = 5 * 1024 * 1024) -> bool:
    """Eine zu große Logdatei beiseitelegen, damit der Rechner nicht vollläuft."""
    pfad = Path(pfad)
    try:
        if pfad.exists() and pfad.stat().st_size > grenze:
            ziel = pfad.with_suffix(pfad.suffix + ".1")
            if ziel.exists():
                ziel.unlink()
            pfad.rename(ziel)
            return True
    except OSError:
        pass
    return False


# -- Anmeldeobjekt (macOS) --------------------------------------------------------------

def plist_pfad() -> Path:
    return Path.home() / "Library" / "LaunchAgents" / (LABEL + ".plist")


def programm_skript() -> Path:
    """Die Datei, die den Dienst startet: die Einzeldatei, sonst ``src/run.py``."""
    einzel = config.BASIS / "jarvis.py"
    return einzel if einzel.exists() else config.BASIS / "src" / "run.py"


def plist_bauen(python: str = "", skript=None, arbeitsordner=None, logordner=None) -> dict:
    """Der Inhalt des Anmeldeobjekts als Wörterbuch."""
    python = python or sys.executable
    skript = Path(skript or programm_skript())
    arbeitsordner = Path(arbeitsordner or config.BASIS)
    logordner = Path(logordner or config.LOG_VERZEICHNIS)
    if skript.name == "run.py":
        # Ohne Einzeldatei (Entwicklung): das Programm aus src/ direkt aufrufen.
        start = [python, "-c", "import sys; sys.path.insert(0, %r); import run; "
                 "sys.exit(run.hauptprogramm(['daemon']))" % str(skript.parent)]
    else:
        start = [python, str(skript), "daemon"]
    # Wach bleiben, solange Jarvis läuft (der Bildschirm darf trotzdem ausgehen).
    if Path("/usr/bin/caffeinate").exists():
        start = ["/usr/bin/caffeinate", "-i"] + start
    return {
        "Label": LABEL,
        "ProgramArguments": start,
        "WorkingDirectory": str(arbeitsordner),
        "RunAtLoad": True,
        # Neustart nach Absturz, nicht nach gewolltem Beenden (Exit-Code 0).
        "KeepAlive": {"SuccessfulExit": False},
        "ThrottleInterval": 10,
        "ProcessType": "Interactive",
        "LimitLoadToSessionType": "Aqua",
        "StandardOutPath": str(logordner / "dienst.log"),
        "StandardErrorPath": str(logordner / "dienst.log"),
        "EnvironmentVariables": {
            "PATH": "/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin",
            "PYTHONUNBUFFERED": "1",
        },
    }


def _launchctl(*argumente) -> subprocess.CompletedProcess:
    return subprocess.run(["launchctl"] + list(argumente), capture_output=True, text=True,
                          timeout=30, shell=False)


def _ist_mac() -> bool:
    return sys.platform == "darwin" and shutil.which("launchctl") is not None


def installieren(trocken: bool = False) -> dict:
    """Legt das Anmeldeobjekt an und startet es. ``trocken`` zeigt nur, was passieren würde."""
    inhalt = plist_bauen()
    ziel = plist_pfad()
    befehle = [["launchctl", "bootout", "gui/%d/%s" % (os.getuid(), LABEL)],
               ["launchctl", "bootstrap", "gui/%d" % os.getuid(), str(ziel)]]
    if trocken:
        return {"ok": True, "trocken": True, "plist": inhalt, "ziel": str(ziel), "befehle": befehle,
                "text": "Trockenlauf: %s würde angelegt und gestartet." % ziel}
    if not _ist_mac():
        return {"ok": False, "fehler": "Den Dienst gibt es nur auf dem Mac. Hier läuft er nicht."}
    try:
        Path(inhalt["StandardOutPath"]).parent.mkdir(parents=True, exist_ok=True)
        ziel.parent.mkdir(parents=True, exist_ok=True)
        with open(ziel, "wb") as datei:
            plistlib.dump(inhalt, datei)
        os.chmod(str(ziel), 0o644)
        _launchctl("bootout", "gui/%d/%s" % (os.getuid(), LABEL))  # war vielleicht schon geladen
        ergebnis = _launchctl("bootstrap", "gui/%d" % os.getuid(), str(ziel))
    except (OSError, subprocess.SubprocessError) as fehler:
        return {"ok": False, "fehler": "Der Dienst ließ sich nicht einrichten: %s" % fehler}
    if ergebnis.returncode != 0:
        return {"ok": False, "fehler": "launchctl meldet: %s" % (ergebnis.stderr or ergebnis.stdout).strip()[:300]}
    return {"ok": True, "ziel": str(ziel),
            "text": "Der Dienst ist eingerichtet. Jarvis startet jetzt bei jeder Anmeldung von selbst "
                    "und startet sich nach einem Absturz neu."}


def entfernen(trocken: bool = False) -> dict:
    ziel = plist_pfad()
    if trocken:
        return {"ok": True, "trocken": True, "ziel": str(ziel),
                "text": "Trockenlauf: %s würde entfernt." % ziel}
    if not _ist_mac():
        return {"ok": False, "fehler": "Den Dienst gibt es nur auf dem Mac."}
    try:
        _launchctl("bootout", "gui/%d/%s" % (os.getuid(), LABEL))
        if ziel.exists():
            ziel.unlink()
    except (OSError, subprocess.SubprocessError) as fehler:
        return {"ok": False, "fehler": "Entfernen fehlgeschlagen: %s" % fehler}
    return {"ok": True, "text": "Der Dienst ist entfernt. Jarvis startet nicht mehr von selbst."}


def neustarten() -> dict:
    if not _ist_mac():
        return {"ok": False, "fehler": "Den Dienst gibt es nur auf dem Mac."}
    try:
        ergebnis = _launchctl("kickstart", "-k", "gui/%d/%s" % (os.getuid(), LABEL))
    except (OSError, subprocess.SubprocessError) as fehler:
        return {"ok": False, "fehler": str(fehler)}
    return {"ok": ergebnis.returncode == 0,
            "text": "Neu gestartet." if ergebnis.returncode == 0
            else "Neustart fehlgeschlagen: %s" % ergebnis.stderr.strip()[:200]}


def dienst_status() -> dict:
    """Ist der Dienst eingerichtet, läuft er, und wann hat er sich zuletzt gemeldet?"""
    angelegt = plist_pfad().exists()
    laeuft = False
    if _ist_mac() and angelegt:
        try:
            laeuft = _launchctl("print", "gui/%d/%s" % (os.getuid(), LABEL)).returncode == 0
        except (OSError, subprocess.SubprocessError):
            laeuft = False
    alter = None
    try:
        alter = int(time.time() - int((config.LOG_VERZEICHNIS / "herzschlag").read_text().strip()))
    except (OSError, ValueError):
        pass
    if not angelegt:
        text = "Der Dienst ist nicht eingerichtet. Einrichten mit: python3 jarvis.py dienst installieren"
    elif not laeuft:
        text = "Der Dienst ist eingerichtet, läuft aber gerade nicht."
    elif alter is not None:
        text = "Der Dienst läuft. Letztes Lebenszeichen vor %d Sekunden." % alter
    else:
        text = "Der Dienst läuft."
    return {"ok": True, "eingerichtet": angelegt, "laeuft": laeuft, "herzschlag_alter": alter, "text": text}


HINWEISE = """So bleibt der iMac wach und Jarvis sein Kopf:

1. Systemeinstellungen, Energie: "Ruhezustand bei ausgeschaltetem Display verhindern" einschalten und
   "Nach einem Stromausfall automatisch starten".
2. Systemeinstellungen, Benutzer: automatische Anmeldung für den Benutzer, unter dem Jarvis läuft.
   (Bei eingeschalteter FileVault-Verschlüsselung geht das nicht. Dann muss nach einem Neustart
   einmal jemand das Passwort eingeben.)
3. Einmal im Terminal "python3 jarvis.py daemon" starten und die Fragen von macOS bestätigen:
   Mikrofon, Bedienungshilfen, Bildschirmaufnahme und, wenn Jarvis überall lesen soll,
   Festplattenvollzugriff. Das kann kein Programm für dich tun, das muss ein Mensch bestätigen.
4. Danach "python3 jarvis.py dienst installieren". Ab jetzt läuft er von selbst.

Für die Trennung vom privaten Mac: einen eigenen Benutzer für Jarvis anlegen (siehe docs/IMAC.md).
"""
