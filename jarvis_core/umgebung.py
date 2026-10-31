# -*- coding: utf-8 -*-
"""Umgebung - was JARVIS über den Mac weiß, den er benutzt (technisches Gedächtnis).

Gelesen werden nur harmlose Systemangaben: Betriebssystem, Rechnermodell,
Speicher, installierte Programme und deren Versionen. Keine Umgebungsvariablen,
keine Dateien, keine Zugangsdaten.
"""

import os
import platform
import shutil
import subprocess

# Nur diese Programme werden nach ihrer Version gefragt.
PROGRAMME = ("claude", "git", "node", "npm", "brew", "swiftc", "python3")


def _lauf(argumente, timeout=5):
    try:
        ausgabe = subprocess.run(argumente, capture_output=True, text=True, timeout=timeout,  # noqa: S603
                                 env={"PATH": os.environ.get("PATH", ""), "LANG": "C"}).stdout
        return (ausgabe or "").strip()
    except (OSError, subprocess.SubprocessError):
        return ""


def sammeln(konfig):
    info = {"system": platform.system(), "version": platform.mac_ver()[0] or platform.release(),
            "rechner": platform.machine(), "python": platform.python_version()}
    if platform.system() == "Darwin" and shutil.which("sysctl"):
        info["modell"] = _lauf(["sysctl", "-n", "hw.model"]) or None
        speicher = _lauf(["sysctl", "-n", "hw.memsize"])
        info["arbeitsspeicher_gb"] = round(int(speicher) / 1024 ** 3) if speicher.isdigit() else None
    try:
        platz = shutil.disk_usage(os.path.expanduser("~"))
        info["speicher_frei_gb"] = round(platz.free / 1024 ** 3)
        info["speicher_gesamt_gb"] = round(platz.total / 1024 ** 3)
    except OSError:
        pass
    programme = {}
    for name in PROGRAMME:
        pfad = shutil.which(name)
        programme[name] = ((_lauf([pfad, "--version"]).splitlines() or ["vorhanden"])[0][:60]) if pfad else None
    info["programme"] = programme
    say = shutil.which("say")
    if say:
        stimmen = [z for z in _lauf([say, "-v", "?"]).splitlines() if " de_" in z]
        info["stimmen_deutsch"] = len(stimmen)
        info["stimmen_hochwertig"] = len([z for z in stimmen if any(m in z for m in ("Premium", "Enhanced", "Siri"))])
    wurzeln = konfig.wurzeln()
    info["werkstatt"] = {"pfad": wurzeln["werkstatt"][0], "vorhanden": os.path.isdir(wurzeln["werkstatt"][0])}
    info["freigegebene_ordner"] = sorted(name for name in wurzeln if name != "werkstatt")
    return info


def zeilen(info):
    """Kurze Sätze für Anzeige und Gedächtnis."""
    mac = "Rechner: %s %s, %s" % (info["system"], info["version"], info["rechner"])
    if info.get("modell"):
        mac += ", Modell %s" % info["modell"]
    if info.get("arbeitsspeicher_gb"):
        mac += ", %d GB Arbeitsspeicher" % info["arbeitsspeicher_gb"]
    ergebnis = [mac]
    if "speicher_frei_gb" in info:
        ergebnis.append("Festplatte: %d von %d GB frei" % (info["speicher_frei_gb"], info["speicher_gesamt_gb"]))
    vorhanden = ["%s (%s)" % (n, v) for n, v in info["programme"].items() if v]
    fehlt = [n for n, v in info["programme"].items() if not v]
    ergebnis.append("Programme vorhanden: %s. Fehlen: %s" % (", ".join(vorhanden) or "keine", ", ".join(fehlt) or "keine"))
    if "stimmen_deutsch" in info:
        ergebnis.append("Deutsche Stimmen: %d, davon hochwertig: %d" % (info["stimmen_deutsch"], info["stimmen_hochwertig"]))
    ergebnis.append("Werkstatt: %s (%s)" % (info["werkstatt"]["pfad"], "vorhanden" if info["werkstatt"]["vorhanden"] else "wird beim ersten Gebrauch angelegt"))
    return ergebnis
