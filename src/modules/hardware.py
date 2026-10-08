#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Bericht über den Rechner und das Hochfahren von Jarvis.

**Messen, nicht raten.** ``hardware_bericht`` fragt den Mac mit eingebauten
Programmen (``sysctl``, ``vm_stat``, ``pmset`` ...), jede Messung in einem
eigenen Faden mit Zeitlimit. Was nicht zu messen ist, steht als Lücke da -
"nicht messbar (Zeitüberschreitung)" oder "ohne Administratorrechte nicht
messbar" -, nie als erfundener Wert. Die Temperatur in Grad gibt es ohne
Administratorrechte nicht; Jarvis meldet stattdessen die Wärmestufe des
Systems. Auf einem anderen System als dem Mac melden alle Mac-Messungen
"Nur auf dem Mac messbar".

**Einspeisbar.** Jede Messung läuft über ``ausfuehren(befehl, timeout)``, das
``(Rückgabecode, Ausgabe)`` zurückgibt (oder mit dem Fehlertext als drittem
Wert). Prüfungen speisen eigene Antworten ein; ohne Angabe laufen die echten
Programme, immer ohne Shell.

**Hochfahren.** ``hochfahren`` prüft den Rechner, begrüßt mit dem Tag (nur aus
echten Quellen, Erfundenes gibt es nicht) und schreibt die Schritte auf die
Anzeige. Die Begrüßung mit dem Tag kommt einmal je Tag; startet Jarvis am selben
Tag noch einmal (Absturz, Neustart des Dienstes), sagt er nur, dass er wieder da
ist, und nennt Auffälliges.
"""

import json
import os
import platform
import re
import shutil
import socket
import subprocess
import sys
import threading
import time
from datetime import date, datetime
from pathlib import Path

import config
from modules.sprechtext import sprechstuecke

NUR_MAC_TEXT = "Nur auf dem Mac messbar"
NICHT_MESSBAR_TEXT = "nicht messbar"
# Wohin die Netzprüfung klopft: nur ein Verbindungsaufbau, es wird nichts gesendet.
NETZ_PRUEFHOST = ("api.anthropic.com", 443)
WLAN_CACHE_SEKUNDEN = 600
GERAETE_CACHE_SEKUNDEN = 3600

# Der Stand der langsamen Abfragen (system_profiler) - nur mit dem echten Ausführer.
_WLAN_CACHE = {"zeit": 0.0, "text": None}
_GERAETE_CACHE = {"zeit": 0.0, "daten": None}
_CACHE_SPERRE = threading.Lock()
# Zwei Fenster, die gleichzeitig hochfahren, begrüßen nicht doppelt.
_HOCHFAHREN_SPERRE = threading.Lock()


# ---------------------------------------------------------------------------
# Systembefehle
# ---------------------------------------------------------------------------

def systembefehl(befehl, timeout=5.0, eingabe=None):
    """Führt einen festen Befehl aus - ohne Shell. Gibt ``(Code, Ausgabe, Fehlertext)`` zurück.

    Fehlendes Programm: Code 127. Zeitüberschreitung: Code 124. Ohne ``eingabe``
    bekommt das Programm keine Tastatur (sonst könnte es auf eine Eingabe warten).
    """
    befehl = [str(teil) for teil in befehl]
    optionen = {"capture_output": True, "text": True, "errors": "replace",
                "timeout": timeout, "shell": False}
    if eingabe is None:
        optionen["stdin"] = subprocess.DEVNULL
    else:
        optionen["input"] = eingabe
    try:
        lauf = subprocess.run(befehl, **optionen)
    except FileNotFoundError:
        return 127, "", "Das Programm %s gibt es hier nicht." % befehl[0]
    except subprocess.TimeoutExpired:
        return 124, "", "Zeitüberschreitung"
    except (OSError, subprocess.SubprocessError) as fehler:
        return 126, "", str(fehler)
    return (getattr(lauf, "returncode", 0), str(getattr(lauf, "stdout", "") or ""),
            str(getattr(lauf, "stderr", "") or ""))


def befehl_antwort(antwort) -> tuple:
    """Macht aus der Antwort eines (eingespeisten) Ausführers ``(Code, Ausgabe, Fehlertext)``.

    Erlaubt sind ``(Code, Ausgabe)``, ``(Code, Ausgabe, Fehler)`` und Objekte mit
    ``returncode``/``stdout``/``stderr``.
    """
    if isinstance(antwort, (tuple, list)):
        code = antwort[0] if antwort else 0
        ausgabe = antwort[1] if len(antwort) > 1 else ""
        fehler = antwort[2] if len(antwort) > 2 else ""
    elif hasattr(antwort, "returncode"):
        code = antwort.returncode
        ausgabe = getattr(antwort, "stdout", "")
        fehler = getattr(antwort, "stderr", "")
    else:
        code, ausgabe, fehler = 0, antwort, ""
    return (code if isinstance(code, int) else 0), str(ausgabe or ""), str(fehler or "")


def befehl_lauf(ausfuehren, befehl, timeout=5.0, eingabe=None) -> tuple:
    """Ruft den Ausführer auf und gibt immer ``(Code, Ausgabe, Fehlertext)`` zurück.

    Ein fehlendes Programm und eine Zeitüberschreitung sind Antworten, keine
    Ausnahmen. Alles andere wirft weiter - der Aufrufer entscheidet.
    """
    try:
        if eingabe is None:
            antwort = ausfuehren(befehl, timeout)
        else:
            antwort = ausfuehren(befehl, timeout, eingabe=eingabe)
    except FileNotFoundError:
        return 127, "", "Das Programm %s gibt es hier nicht." % befehl[0]
    except subprocess.TimeoutExpired:
        return 124, "", "Zeitüberschreitung"
    return befehl_antwort(antwort)


# ---------------------------------------------------------------------------
# Kleine Helfer
# ---------------------------------------------------------------------------

def hardware_kachel(name, wert, einheit, status, text, kurz="") -> dict:
    """Eine Messung. ``kurz`` ist die Kurzform für den Satz "was auffällt" (intern)."""
    kachel = {"name": name, "wert": wert, "einheit": einheit, "status": status, "text": text}
    if kurz:
        kachel["_kurz"] = kurz
    return kachel


def _dezimal(zahl, stellen=1) -> str:
    """Eine Zahl auf Deutsch: Komma, und ohne überflüssige Nachkommastelle."""
    try:
        text = ("%." + str(stellen) + "f") % float(zahl)
    except (TypeError, ValueError):
        return "?"
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text.replace(".", ",")


def _mehrzahl(zahl, eins, viele) -> str:
    return "%d %s" % (zahl, eins if zahl == 1 else viele)


def _dauer_text(sekunden) -> str:
    """Eine Dauer, wie man sie sagt: "3 Tage 4 Stunden", "5 Stunden 12 Minuten"."""
    minuten = int(max(0, sekunden) // 60)
    stunden, minuten = divmod(minuten, 60)
    tage, stunden = divmod(stunden, 24)
    if tage:
        return "%s %s" % (_mehrzahl(tage, "Tag", "Tage"), _mehrzahl(stunden, "Stunde", "Stunden"))
    if stunden:
        return "%s %s" % (_mehrzahl(stunden, "Stunde", "Stunden"), _mehrzahl(minuten, "Minute", "Minuten"))
    return _mehrzahl(minuten, "Minute", "Minuten")


def _fehlt(name, grund) -> dict:
    return hardware_kachel(name, None, "", "fehlt", "%s (%s)" % (NICHT_MESSBAR_TEXT, grund))


# ---------------------------------------------------------------------------
# WLAN
# ---------------------------------------------------------------------------

def wlan_geraet_lesen(text: str) -> str:
    """Das Gerät des WLANs aus ``networksetup -listallhardwareports`` ("en1"), sonst leer."""
    ist_wlan = False
    for zeile in str(text or "").splitlines():
        zeile = zeile.strip()
        if zeile.startswith("Hardware Port:"):
            ist_wlan = zeile.split(":", 1)[1].strip().lower() in ("wi-fi", "airport", "wlan")
        elif ist_wlan and zeile.startswith("Device:"):
            return zeile.split(":", 1)[1].strip()
    return ""


def wlan_netz_lesen(text: str, geraet: str = "") -> tuple:
    """Liest ``system_profiler SPAirPortDataType``. Gibt ``(verbunden, Netzname)`` zurück.

    ``verbunden`` ist ``True``, ``False`` oder ``None`` (aus der Ausgabe nicht zu
    sehen). Der Name steht unter "Current Network Information:"; ab macOS 14 steht
    dort ohne Ortungserlaubnis "<redacted>" - das gilt als nicht lesbar.
    """
    zeilen = str(text or "").splitlines()
    schnittstelle = ""
    stati, namen = {}, {}
    for nummer, zeile in enumerate(zeilen):
        treffer = re.match(r"^\s+((?:en|awdl|llw|ap|p2p|bridge)\d+):\s*$", zeile)
        if treffer:
            schnittstelle = treffer.group(1)
            continue
        kurz = zeile.strip()
        if kurz.startswith("Status:") and schnittstelle:
            stati.setdefault(schnittstelle, kurz.split(":", 1)[1].strip().lower())
        elif kurz == "Current Network Information:" and schnittstelle:
            for folgezeile in zeilen[nummer + 1:nummer + 4]:
                if folgezeile.strip():
                    namen.setdefault(schnittstelle, folgezeile.strip().rstrip(":").strip())
                    break
    auswahl = geraet if geraet in namen or geraet in stati else ""
    if not auswahl:
        auswahl = next(iter(namen), "") or next((k for k in stati if k.startswith("en")), "")
    name = namen.get(auswahl, "")
    if name.lower() in ("<redacted>", "redacted", "<hidden>"):
        name = ""
    status = stati.get(auswahl, "")
    if name:
        return True, name
    if status:
        return status.startswith("connected"), ""
    return None, ""


def wlan_bericht(ausfuehren=None, plattform=None) -> dict:
    """Das WLAN: Gerät, verbunden, Netzname. Gibt eine Messung wie in ``hardware_bericht`` zurück.

    ``networksetup -getairportnetwork`` wird nie benutzt: Es meldet ab macOS 15
    "nicht verbunden", auch wenn man verbunden ist. Das Gerät kommt aus
    ``networksetup -listallhardwareports`` (auf einem iMac ist ``en0`` nicht
    verlässlich das WLAN), der Name aus ``system_profiler`` (langsam, deshalb
    zehn Minuten gemerkt - nur mit den echten Programmen).
    """
    if (plattform or sys.platform) != "darwin":
        return hardware_kachel("WLAN", None, "", "fehlt", NUR_MAC_TEXT)
    echt = ausfuehren is None
    ausfuehren = ausfuehren or systembefehl
    code, ausgabe, _ = befehl_lauf(ausfuehren, ["networksetup", "-listallhardwareports"], 5)
    if code != 0:
        return _fehlt("WLAN", "networksetup antwortet nicht")
    geraet = wlan_geraet_lesen(ausgabe)
    if not geraet:
        return hardware_kachel("WLAN", None, "", "ok", "kein WLAN-Gerät")
    roh = None
    if echt:
        with _CACHE_SPERRE:
            if _WLAN_CACHE["text"] is not None and time.monotonic() - _WLAN_CACHE["zeit"] < WLAN_CACHE_SEKUNDEN:
                roh = _WLAN_CACHE["text"]
    if roh is None:
        code, ausgabe, _ = befehl_lauf(ausfuehren, ["system_profiler", "SPAirPortDataType"], 15)
        roh = ausgabe if code == 0 else ""
        if echt and roh:
            with _CACHE_SPERRE:
                _WLAN_CACHE["text"], _WLAN_CACHE["zeit"] = roh, time.monotonic()
    verbunden, name = wlan_netz_lesen(roh, geraet)
    if verbunden is None:
        # Aus der Ausgabe nicht zu sehen: hat das Gerät eine Adresse, ist es verbunden.
        code, adresse, _ = befehl_lauf(ausfuehren, ["ipconfig", "getifaddr", geraet], 4)
        verbunden = bool(code == 0 and adresse.strip())
    kachel = hardware_kachel("WLAN", name or None, "", "ok",
                             ("verbunden mit %s" % name) if name
                             else ("verbunden (Name nicht lesbar)" if verbunden else "nicht verbunden"))
    kachel["geraet"] = geraet
    kachel["verbunden"] = bool(verbunden)
    return kachel


# ---------------------------------------------------------------------------
# Die Messungen
# ---------------------------------------------------------------------------

class HardwareMessung:
    """Alle Messungen eines Berichts. Jede Methode gibt eine Liste von Messungen zurück."""

    def __init__(self, ausfuehren=None, plattform=None, netz=None, last=None, platte=None,
                 jetzt=None, stimme=None, tools=None):
        self.echt = ausfuehren is None
        self.ausfuehren = ausfuehren or systembefehl
        self.plattform = plattform or sys.platform
        self.ist_mac = self.plattform == "darwin"
        self.netz = netz
        self.last = last
        self.platte = platte
        self.jetzt = jetzt or time.time
        self.stimme = stimme
        self.tools = tools
        self.netzbetrieb = False

    def _text(self, befehl, timeout=5.0) -> str:
        code, ausgabe, _ = befehl_lauf(self.ausfuehren, befehl, timeout)
        return ausgabe.strip() if code == 0 else ""

    def rechner(self):
        modell = self._text(["sysctl", "-n", "hw.model"])
        chip = self._text(["sysctl", "-n", "machdep.cpu.brand_string"])
        version = platform.mac_ver()[0]
        teile = [t for t in (modell, chip, ("macOS %s" % version) if version else "") if t]
        if not (modell or chip):
            return [_fehlt("Rechner", "sysctl antwortet nicht")]
        return [hardware_kachel("Rechner", modell or chip, "", "ok", ", ".join(teile))]

    def last_messen(self):
        if self.last is not None:
            eins, kerne = self.last()
        else:
            eins, kerne = os.getloadavg()[0], os.cpu_count() or 1
        je_kern = float(eins) / max(1, int(kerne))
        angabe = "Auslastung %s je Kern" % _dezimal(je_kern, 2)
        if je_kern < 0.7:
            return [hardware_kachel("Last", round(je_kern, 2), "je Kern", "ok", "normal (%s)" % angabe)]
        if je_kern < 1.5:
            return [hardware_kachel("Last", round(je_kern, 2), "je Kern", "warnung", "hoch (%s)" % angabe,
                                    "Last hoch")]
        return [hardware_kachel("Last", round(je_kern, 2), "je Kern", "warnung", "sehr hoch (%s)" % angabe,
                                "Last sehr hoch")]

    def arbeitsspeicher(self):
        gesamt_roh = self._text(["sysctl", "-n", "hw.memsize"])
        code, vm, _ = befehl_lauf(self.ausfuehren, ["vm_stat"], 5)
        if not gesamt_roh.isdigit() or code != 0:
            return [_fehlt("Arbeitsspeicher", "sysctl oder vm_stat antwortet nicht")]
        gesamt = int(gesamt_roh) / float(1024 ** 3)
        seite = re.search(r"page size of (\d+) bytes", vm)

        def seiten(titel):
            treffer = re.search(r"^%s:\s+(\d+)" % re.escape(titel), vm, re.MULTILINE)
            return int(treffer.group(1)) if treffer else None
        aktiv, fest = seiten("Pages active"), seiten("Pages wired down")
        if not seite or aktiv is None or fest is None:
            return [hardware_kachel("Arbeitsspeicher", None, "GB", "fehlt",
                                    "%s GB eingebaut, Belegung nicht lesbar" % _dezimal(gesamt))]
        belegt = (aktiv + fest + (seiten("Pages occupied by compressor") or 0)) * int(seite.group(1))
        belegt_gb = belegt / float(1024 ** 3)
        return [hardware_kachel("Arbeitsspeicher", round(belegt_gb, 1), "GB", "ok",
                                "%s von %s GB belegt" % (_dezimal(belegt_gb), _dezimal(gesamt)))]

    def speicherdruck(self):
        code, ausgabe, _ = befehl_lauf(self.ausfuehren, ["memory_pressure"], 5)
        frei = re.findall(r"free percentage:\s*(\d+)\s*%", ausgabe)
        if code != 0 or not frei:
            return [_fehlt("Speicherdruck", "memory_pressure antwortet nicht")]
        prozent = int(frei[-1])
        if prozent < 20:
            return [hardware_kachel("Speicherdruck", prozent, "% frei", "warnung",
                                    "nur noch %d %% frei" % prozent, "Speicher %d %% frei" % prozent)]
        return [hardware_kachel("Speicherdruck", prozent, "% frei", "ok", "%d %% frei" % prozent)]

    def festplatte(self):
        try:
            if self.platte is not None:
                gesamt, _, frei = self.platte()
            else:
                gesamt, _, frei = shutil.disk_usage(os.path.expanduser("~"))
        except OSError as fehler:
            return [_fehlt("Festplatte", str(fehler)[:50])]
        prozent = int(round(100.0 * frei / gesamt)) if gesamt else 0
        text = "%s GB frei von %s GB (%d %%)" % (_dezimal(frei / 1e9, 0), _dezimal(gesamt / 1e9, 0), prozent)
        if prozent < 10:
            return [hardware_kachel("Festplatte", round(frei / 1e9), "GB frei", "warnung", text,
                                    "Festplatte nur %d %% frei" % prozent)]
        return [hardware_kachel("Festplatte", round(frei / 1e9), "GB frei", "ok", text)]

    def internet(self):
        beginn = time.monotonic()
        try:
            if self.netz is not None:
                self.netz(NETZ_PRUEFHOST[0], NETZ_PRUEFHOST[1], 3)
            else:
                socket.create_connection(NETZ_PRUEFHOST, 3).close()
        except OSError:
            return [hardware_kachel("Internet", None, "", "fehlt", "kein Internet", "kein Internet")]
        millis = int(round((time.monotonic() - beginn) * 1000))
        return [hardware_kachel("Internet", millis, "ms", "ok", "erreichbar (%d ms)" % millis)]

    def wlan(self):
        kachel = wlan_bericht(self.ausfuehren if not self.echt else None, self.plattform)
        return [kachel]

    def waerme(self):
        code, ausgabe, _ = befehl_lauf(self.ausfuehren,
                                       ["notifyutil", "-g", "com.apple.system.thermalpressurelevel"], 5)
        stufe = re.search(r"(\d+)\s*$", ausgabe.strip())
        grad = hardware_kachel("Temperatur", None, "", "fehlt", "ohne Administratorrechte nicht messbar")
        if code != 0 or not stufe:
            return [_fehlt("Wärme", "notifyutil antwortet nicht"), grad]
        stufe = int(stufe.group(1))
        if stufe <= 0:
            kachel = hardware_kachel("Wärme", stufe, "Stufe", "ok", "normal")
        elif stufe == 1:
            kachel = hardware_kachel("Wärme", stufe, "Stufe", "ok", "erhöht", "Wärme erhöht")
        elif stufe == 2:
            kachel = hardware_kachel("Wärme", stufe, "Stufe", "warnung", "stark", "Wärme stark")
        else:
            kachel = hardware_kachel("Wärme", stufe, "Stufe", "warnung", "kritisch", "Wärme kritisch")
        return [kachel, grad]

    def laufzeit(self):
        code, ausgabe, _ = befehl_lauf(self.ausfuehren, ["sysctl", "-n", "kern.boottime"], 5)
        treffer = re.search(r"sec = (\d+)", ausgabe)
        if code != 0 or not treffer:
            return [_fehlt("Laufzeit", "kern.boottime nicht lesbar")]
        sekunden = self.jetzt() - int(treffer.group(1))
        if sekunden < 0:
            return [_fehlt("Laufzeit", "Uhr und Startzeit passen nicht zusammen")]
        return [hardware_kachel("Laufzeit", int(sekunden), "s", "ok", _dauer_text(sekunden))]

    def batterie(self):
        code, ausgabe, _ = befehl_lauf(self.ausfuehren, ["pmset", "-g", "batt"], 5)
        if code != 0:
            return [_fehlt("Batterie", "pmset antwortet nicht")]
        if "InternalBattery" not in ausgabe:
            self.netzbetrieb = True
            return []
        treffer = re.search(r"InternalBattery[^\n]*?(\d+)%;\s*([^;\n]+)", ausgabe)
        if not treffer:
            return [_fehlt("Batterie", "Stand nicht lesbar")]
        prozent, zustand = int(treffer.group(1)), treffer.group(2).strip().lower()
        wort = {"charging": "lädt", "discharging": "entlädt", "charged": "voll geladen",
                "finishing charge": "wird voll", "ac attached": "am Netz"}.get(zustand, zustand)
        if prozent < 20 and zustand.startswith("discharging"):
            return [hardware_kachel("Batterie", prozent, "%", "warnung", "%d %%, %s" % (prozent, wort),
                                    "Akku %d %%" % prozent)]
        return [hardware_kachel("Batterie", prozent, "%", "ok", "%d %%, %s" % (prozent, wort))]

    def _geraeteliste(self):
        """Die Geräte aus ``system_profiler -json`` (Kamera, Audio, Bildschirme) oder ``None``."""
        if self.echt:
            with _CACHE_SPERRE:
                if _GERAETE_CACHE["daten"] is not None \
                        and time.monotonic() - _GERAETE_CACHE["zeit"] < GERAETE_CACHE_SEKUNDEN:
                    return _GERAETE_CACHE["daten"]
        code, ausgabe, _ = befehl_lauf(
            self.ausfuehren, ["system_profiler", "SPCameraDataType", "SPAudioDataType",
                              "SPDisplaysDataType", "-json"], 15)
        if code != 0:
            return None
        try:
            daten = json.loads(ausgabe)
        except ValueError:
            return None
        if not isinstance(daten, dict):
            return None
        if self.echt:
            with _CACHE_SPERRE:
                _GERAETE_CACHE["daten"], _GERAETE_CACHE["zeit"] = daten, time.monotonic()
        return daten

    def geraete(self):
        daten = self._geraeteliste()
        if daten is None:
            return [_fehlt("Kamera", "system_profiler antwortet nicht"),
                    _fehlt("Mikrofon", "system_profiler antwortet nicht"),
                    _fehlt("Bildschirme", "system_profiler antwortet nicht")]
        kameras = len(daten.get("SPCameraDataType") or [])
        mikrofone = 0
        for gruppe in daten.get("SPAudioDataType") or []:
            for geraet in (gruppe.get("_items") or []) if isinstance(gruppe, dict) else []:
                eingang = geraet.get("coreaudio_device_input") if isinstance(geraet, dict) else None
                if eingang:
                    mikrofone += 1
        bildschirme = 0
        for grafik in daten.get("SPDisplaysDataType") or []:
            if isinstance(grafik, dict):
                bildschirme += len(grafik.get("spdisplays_ndrvs") or [])

        def kachel(name, anzahl, eins, viele):
            return hardware_kachel(name, anzahl, "", "ok",
                                   _mehrzahl(anzahl, eins, viele) if anzahl else "keine gefunden")
        return [kachel("Kamera", kameras, "Kamera", "Kameras"),
                kachel("Mikrofon", mikrofone, "Mikrofon", "Mikrofone"),
                kachel("Bildschirme", bildschirme, "Bildschirm", "Bildschirme")]

    def dienste(self):
        def sicher(frage):
            try:
                return bool(frage())
            except Exception:
                return False
        claude = bool(config.ANTHROPIC_API_KEY)
        teile = ["Claude %s" % ("ja" if claude else "nein"),
                 "Gemini %s" % ("ja" if config.GEMINI_API_KEY else "nein")]
        if self.stimme is not None:
            try:
                zustand = self.stimme.zustand() or {}
            except Exception:
                zustand = {}
            if zustand.get("elevenlabs"):
                stimme = "ElevenLabs"
            elif zustand.get("fish"):
                stimme = "Fish"
            elif zustand.get("macos_say"):
                stimme = "Systemstimme"
            else:
                stimme = "keine"
            teile.append("Stimme %s" % stimme)
            teile.append("Mikrofon-Zugriff %s" % ("ja" if zustand.get("mikrofon") else "nein"))
        else:
            teile.append("Stimme im Browser")
        if self.tools is not None:
            teile.append("Kalender %s" % ("ja" if sicher(self.tools.kalender.verfuegbar) else "nein"))
            teile.append("Post %s" % ("ja" if sicher(self.tools.mail.lesen_moeglich) else "nein"))
            teile.append("Telegram %s" % ("ja" if sicher(self.tools.telegram.verfuegbar) else "nein"))
        if claude:
            return [hardware_kachel("Dienste", None, "", "ok", ", ".join(teile))]
        return [hardware_kachel("Dienste", None, "", "warnung", ", ".join(teile), "Claude-Schlüssel fehlt")]


# (Messungen, Methode, nur auf dem Mac, langsam, Messung auch ohne Mac anlegen)
HARDWARE_PROBEN = (
    (("Rechner",), "rechner", True, False, True),
    (("Last",), "last_messen", False, False, True),
    (("Arbeitsspeicher",), "arbeitsspeicher", True, False, True),
    (("Speicherdruck",), "speicherdruck", True, False, True),
    (("Festplatte",), "festplatte", False, False, True),
    (("Internet",), "internet", False, False, True),
    (("WLAN",), "wlan", True, True, True),
    (("Wärme", "Temperatur"), "waerme", True, False, True),
    (("Laufzeit",), "laufzeit", True, False, True),
    (("Batterie",), "batterie", True, False, False),
    (("Kamera", "Mikrofon", "Bildschirme"), "geraete", True, True, True),
    (("Dienste",), "dienste", False, False, True),
)


def hardware_bericht(ausfuehren=None, zeitlimit=2.0, stimme=None, tools=None, plattform=None,
                     netz=None, last=None, platte=None, jetzt=None, zeitlimit_langsam=None) -> dict:
    """Prüft den Rechner. Gibt ``{"zeit", "werte", "kurz", "auffaellig"}`` zurück.

    ``werte`` ist eine Liste von ``{"name", "wert", "einheit", "status", "text"}``;
    ``status`` ist ``ok``, ``warnung`` oder ``fehlt``. ``kurz`` ist ein Satz, der nur
    nennt, was auffällt ("Speicher 18 % frei, Wärme erhöht, sonst alles in Ordnung.").

    Jede Messung läuft in einem eigenen Faden und bekommt ``zeitlimit`` Sekunden;
    die beiden langsamen Abfragen (WLAN-Name, Geräte über ``system_profiler``)
    bekommen ``zeitlimit_langsam`` (Standard: das Dreifache). Wer nicht fertig
    wird, steht als "nicht messbar (Zeitüberschreitung)" im Bericht. Die
    übrigen Angaben sind für Prüfungen: ``ausfuehren(befehl, timeout)``, ``plattform``
    (Standard ``sys.platform``), ``netz(host, port, timeout)``, ``last()`` ->
    ``(Last, Kerne)``, ``platte()`` -> ``(gesamt, belegt, frei)``, ``jetzt()``.
    """
    try:
        zeitlimit = float(zeitlimit)
    except (TypeError, ValueError):
        zeitlimit = 2.0
    zeitlimit = zeitlimit if zeitlimit > 0 else 2.0
    langsam = float(zeitlimit_langsam) if zeitlimit_langsam else zeitlimit * 3
    messung = HardwareMessung(ausfuehren, plattform, netz, last, platte, jetzt, stimme, tools)

    laeufe = []
    for namen, methode, nur_mac, ist_langsam, immer in HARDWARE_PROBEN:
        halter = {"kacheln": None, "fehler": ""}
        faden = None
        if nur_mac and not messung.ist_mac:
            halter["kacheln"] = ([hardware_kachel(n, None, "", "fehlt", NUR_MAC_TEXT) for n in namen]
                                 if immer else [])
        else:
            def laufen(halter=halter, methode=methode):
                try:
                    halter["kacheln"] = list(getattr(messung, methode)() or [])
                except Exception as fehler:
                    halter["fehler"] = "Fehler: %s" % str(fehler)[:50]
            faden = threading.Thread(target=laufen, daemon=True, name="hardware-" + methode)
        laeufe.append((namen, methode, halter, faden, ist_langsam))

    beginn = time.monotonic()
    for _, _, _, faden, _ in laeufe:
        if faden is not None:
            faden.start()
    werte = []
    for namen, methode, halter, faden, ist_langsam in laeufe:
        if faden is not None:
            frist = beginn + (langsam if ist_langsam else zeitlimit) - time.monotonic()
            faden.join(max(0.0, frist))
            if faden.is_alive():
                if methode == "internet":
                    halter["kacheln"] = [hardware_kachel("Internet", None, "", "fehlt",
                                                         "kein Internet (keine Antwort)", "kein Internet")]
                else:
                    halter["kacheln"] = [_fehlt(n, "Zeitüberschreitung") for n in namen]
            elif halter["kacheln"] is None:
                halter["kacheln"] = [_fehlt(n, halter["fehler"] or "keine Antwort") for n in namen]
        werte.extend(halter["kacheln"] or [])

    if messung.netzbetrieb:
        for kachel in werte:
            if kachel["name"] == "Rechner" and kachel["status"] == "ok":
                kachel["text"] += ", Netzbetrieb"
    auffaellig = [k.pop("_kurz") for k in werte if "_kurz" in k]
    luecken = sum(1 for k in werte if k["status"] == "fehlt" and k["text"].startswith(NICHT_MESSBAR_TEXT))
    teile = list(auffaellig)
    if not messung.ist_mac:
        teile.insert(0, "kein Mac, die Mac-Messungen entfallen")
    if luecken:
        teile.append("%s nicht messbar" % _mehrzahl(luecken, "Messung", "Messungen"))
    kurz = (", ".join(teile) + ", sonst alles in Ordnung.") if teile else "Alles in Ordnung."
    kurz = kurz[0].upper() + kurz[1:]
    zeit = datetime.fromtimestamp(messung.jetzt()).strftime("%Y-%m-%dT%H:%M:%S")
    return {"zeit": zeit, "werte": werte, "kurz": kurz, "auffaellig": auffaellig}


def hardware_text(bericht: dict) -> str:
    """Der Bericht als Text für das Terminal (``python3 jarvis.py hardware``)."""
    marken = {"ok": "[ok]", "warnung": "[!!]", "fehlt": "[--]"}
    zeilen = ["%s %-16s %s" % (marken.get(k.get("status"), "[??]"), k.get("name", ""), k.get("text", ""))
              for k in bericht.get("werte") or []]
    zeilen += ["", str(bericht.get("kurz") or "")]
    return "\n".join(zeilen)


# ---------------------------------------------------------------------------
# Hochfahren
# ---------------------------------------------------------------------------

def _schritte_aus(bericht: dict) -> list:
    """Die Messungen als Zeilen für die Anzeige: ``ok`` ist ``True``, ``False`` oder ``None`` (Lücke)."""
    zustand = {"ok": True, "warnung": False}
    return [{"name": str(k.get("name", "")), "ok": zustand.get(k.get("status")),
             "text": str(k.get("text", ""))} for k in (bericht.get("werte") or [])[:16]]


def _auffaelliges_sagen(bericht: dict) -> str:
    """Ein Satz mit dem, was auffällt - leer, wenn nichts."""
    liste = bericht.get("auffaellig") or []
    return ("Auffällig: %s." % ", ".join(liste)) if liste else ""


def _hochfahren_zeigen(anzeige, schritte: list, begruessung: str, fertig: bool):
    """Schreibt den Start auf die Anzeige. Sie darf nie etwas kaputt machen."""
    if anzeige is None:
        return
    try:
        anzeige.melden("hochfahren", {"schritte": schritte, "begruessung": begruessung,
                                      "fertig": bool(fertig)})
        anzeige.zeigen("hochfahren", {}, 60, "hochfahren")
    except Exception as fehler:
        print("[hochfahren] Anzeige nicht erreichbar: %s" % fehler)


def hochfahren(agent, stimme=None, anzeige=None, **messen) -> dict:
    """Prüft den Mac, begrüßt mit dem Tag und zeigt es auf der Anzeige.

    Gibt ``{"ok", "neu", "schritte", "begruessung", "sprechstuecke"}`` zurück.
    ``neu`` ist ``True``, wenn es heute das erste Hochfahren ist (Marke
    ``hochgefahren.txt`` im Log-Ordner). Nur dann kommt die Begrüßung mit dem Tag;
    sonst heißt es "Ich bin wieder da." und Auffälliges. ``anzeige`` braucht
    ``melden`` und ``zeigen`` (Standard: die Werkzeuge des Agenten); ``messen`` geht
    an ``hardware_bericht`` (für Prüfungen).
    """
    heute = date.today().isoformat()
    marke = Path(config.LOG_VERZEICHNIS) / "hochgefahren.txt"
    with _HOCHFAHREN_SPERRE:
        try:
            gelesen = marke.read_text(encoding="utf-8").strip()
        except OSError:
            gelesen = ""
        neu = gelesen != heute
        if neu:
            try:
                marke.parent.mkdir(parents=True, exist_ok=True)
                marke.write_text(heute + "\n", encoding="utf-8")
            except OSError as fehler:
                print("[hochfahren] Die Tagesmarke ließ sich nicht schreiben: %s" % fehler)
    werkzeuge = getattr(agent, "tools", None)
    stimme = stimme if stimme is not None else getattr(agent, "stimme", None)
    anzeige = anzeige if anzeige is not None else werkzeuge

    try:
        bericht = hardware_bericht(stimme=stimme, tools=werkzeuge, **messen)
    except Exception as fehler:
        print("[hochfahren] Der Rechnerbericht ließ sich nicht erstellen: %s" % fehler)
        bericht = {"zeit": "", "werte": [], "auffaellig": [],
                   "kurz": "Der Rechnerbericht ließ sich nicht erstellen."}
    schritte = _schritte_aus(bericht)
    # Die Zeilen laufen schon über die Anzeige, während die Begrüßung noch entsteht.
    _hochfahren_zeigen(anzeige, schritte, "", False)

    if neu and config.BEGRUESSUNG_AN:
        try:
            begruessung = str(agent.begruessung(bericht) or "").strip()
        except Exception as fehler:
            print("[hochfahren] Die Begrüßung ließ sich nicht bauen: %s" % fehler)
            begruessung = ""
        if not begruessung:
            begruessung = "Hallo. Ich bin da. %s" % bericht["kurz"]
    elif neu:
        begruessung = " ".join(t for t in ("Ich bin da.", _auffaelliges_sagen(bericht)) if t)
    else:
        begruessung = " ".join(t for t in ("Ich bin wieder da.", _auffaelliges_sagen(bericht)) if t)

    _hochfahren_zeigen(anzeige, schritte, begruessung, True)
    return {"ok": True, "neu": neu, "schritte": schritte, "begruessung": begruessung,
            "sprechstuecke": sprechstuecke(begruessung)}
