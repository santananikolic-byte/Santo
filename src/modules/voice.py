#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Sprache - Mikrofon rein, Stimme raus.

Beides ist mehrstufig aufgebaut, damit **ein einziger Schlüssel** genügt:

    Stimme raus:  Fish Audio / ElevenLabs (falls Schlüssel, Reihenfolge nach
                  ``STIMME_ANBIETER``) -> macOS ``say`` (immer da, gratis)
    Sprache rein: faster-whisper lokal (gratis) -> Whisper-API (falls Schlüssel)

Aufgenommen wird bis zur Sprechpause, nicht in festen Blöcken. Feste Blöcke
schneiden entweder mitten im Satz ab oder lassen den Nutzer nach dem letzten
Wort warten - beides fällt im Alltag sofort unangenehm auf.
"""

import http.client
import importlib.util
import json
import os
import re
import shutil
import queue
import subprocess
import tempfile
import threading
import time
import urllib.error
import urllib.request
import wave

import config
from modules.sprechtext import abschnitte_ziffernsicher, sprechstuecke, sprechstuecke_fremd, sprechtext
from modules.stimmanbieter import (PEGEL_ABTASTRATE, anbieter_reihenfolge, elevenlabs_holen,
                                   fish_holen, pcm_als_wav, pegel_aus_wav, say_befehl,
                                   wav_reparieren)

try:
    import numpy as np
except ImportError:
    np = None

try:
    import sounddevice as sd
except (ImportError, OSError):
    sd = None

try:
    from faster_whisper import WhisperModel
except ImportError:
    WhisperModel = None

# Die Spracherkennung schreibt den Namen selten korrekt. Alle diese Formen
# werden als Weckwort akzeptiert.
WECKWOERTER = ["hey jarvis", "hey javis", "hey dscharvis", "hey charvis",
               "hey travis", "hey jervis", "hey dscharvis", "jarvis", "javis"]

# Bevorzugte deutsche Systemstimmen, in dieser Reihenfolge.
WUNSCHSTIMMEN = ["Markus", "Yannick", "Petra", "Anna", "Viktor"]


def beste_deutsche_stimme(liste: str) -> str:
    """Wählt aus der Ausgabe von ``say -v ?`` die natürlichste deutsche Stimme."""
    stimmen = []
    for zeile in (liste or "").splitlines():
        treffer = re.match(r"^(.+?)\s+([a-z]{2}_[A-Z]{2})\s+#", zeile)
        if treffer:
            stimmen.append((treffer.group(1).strip(), treffer.group(2)))
    deutsch = [name for name, sprache in stimmen if sprache in ("de_DE", "de_AT", "de_CH")]
    if not deutsch:
        return ""

    def rang(name):
        klein = name.lower()
        guete = 0 if "premium" in klein else 1 if ("erweitert" in klein or "enhanced" in klein) else 2
        grund = name.split(" (")[0]
        wunsch = WUNSCHSTIMMEN.index(grund) if grund in WUNSCHSTIMMEN else len(WUNSCHSTIMMEN)
        return (guete, wunsch)

    return sorted(deutsch, key=rang)[0]

# Die Systemstimmen je Sprache, einmal aus ``say -v ?`` gelesen.
_SYSTEMSTIMMEN = {}


def stimme_fuer_sprache(code: str, liste: str = None) -> str:
    """Die Mac-Stimme für eine Sprache (``tr``, ``en``, ``hr`` ...) – leer, wenn es keine gibt.

    Gelesen werden die Zeilen von ``say -v ?`` (``Name  xx_YY  # Beispielsatz``). Genommen
    wird die erste Stimme, deren Sprachraum mit dem Kürzel beginnt; hochwertige
    (Premium, Erweitert, Enhanced) kommen vor den einfachen. Das Ergebnis wird
    gemerkt, damit ``say`` nicht bei jedem Satz gefragt wird. ``liste`` ist der
    Text von ``say -v ?`` (für Prüfungen) – dann wird nichts gemerkt.
    """
    code = (code or "").strip().lower().replace("-", "_")[:3]
    if not code:
        return ""
    if liste is None and code in _SYSTEMSTIMMEN:
        return _SYSTEMSTIMMEN[code]
    quelle = liste
    if quelle is None:
        try:
            ergebnis = subprocess.run(["say", "-v", "?"], capture_output=True, text=True,
                                      timeout=10, shell=False)
            quelle = ergebnis.stdout if ergebnis.returncode == 0 else ""
        except (OSError, subprocess.SubprocessError):
            quelle = ""
    kandidaten = []
    for zeile in (quelle or "").splitlines():
        treffer = re.match(r"^(.+?)\s+([A-Za-z]{2,3}[_-][A-Za-z0-9]{2,4})\s+#", zeile)
        if treffer and treffer.group(2).lower().replace("-", "_").split("_")[0] == code:
            name = treffer.group(1).strip()
            klein = name.lower()
            guete = 0 if "premium" in klein else 1 if ("erweitert" in klein or "enhanced" in klein) else 2
            kandidaten.append((guete, len(kandidaten), name))
    name = sorted(kandidaten)[0][2] if kandidaten else ""
    if liste is None:
        _SYSTEMSTIMMEN[code] = name
    return name


# Kurze Signaltöne - der Nutzer hört so, in welchem Zustand Jarvis ist.
SIGNALTOENE = {
    "zuhoeren": "/System/Library/Sounds/Tink.aiff",
    "verstanden": "/System/Library/Sounds/Pop.aiff",
    "fehler": "/System/Library/Sounds/Basso.aiff",
}

# Aufnahmeparameter
ABTASTRATE = 16000
BLOCK_SEKUNDEN = 0.1
STILLE_BIS_ENDE = 1.2
MAX_AUFNAHME = 25.0
MIN_AUFNAHME = 0.4
PEGEL_UNTERGRENZE = 0.004
PEGEL_FAKTOR = 3.5

ELEVENLABS_URL = "https://api.elevenlabs.io/v1"
WHISPER_URL = "https://api.openai.com/v1/audio/transcriptions"


def mikrofon_fehlermeldung() -> str:
    """Sagt genau, was fuer die Aufnahme fehlt - Paket oder Tonbibliothek.

    ``sounddevice`` laesst sich zwar installieren, wirft beim Import aber
    ``OSError``, wenn die Bibliothek PortAudio fehlt. Wer dann liest, das
    Paket fehle, installiert es ein zweites Mal und wundert sich. Deshalb
    wird nachgesehen, ob das Paket da ist, und nur der wirklich fehlende
    Teil genannt.
    """
    if np is None:
        return "Es fehlt das Paket numpy."
    if sd is not None:
        return ""
    try:
        vorhanden = importlib.util.find_spec("sounddevice") is not None
    except (ImportError, ValueError):
        vorhanden = False
    if vorhanden:
        return ("Die Tonbibliothek PortAudio fehlt. Im Terminal eingeben: "
                "brew install portaudio")
    return "Es fehlt das Paket sounddevice."


def text_fuers_sprechen(text: str) -> str:
    """Der Text, so wie ein Mensch ihn sagen würde (siehe ``sprechtext``)."""
    return sprechtext(text)


def weckwort_pruefen(text: str):
    """Prüft auf das Weckwort und schneidet es ab.

    Gibt ``(erkannt, restlicher_befehl)`` zurück.
    """
    if not text:
        return False, ""
    roh = str(text).strip()
    klein = re.sub(r"[^a-zä-ü0-9 ]+", " ", roh.lower())
    klein = re.sub(r"\s+", " ", klein).strip()
    for weckwort in WECKWOERTER:
        if klein == weckwort:
            return True, ""
        if klein.startswith(weckwort + " "):
            rest = klein[len(weckwort):].strip(" ,.")
            # Den Rest aus dem Originaltext holen, damit Groß- und Kleinschreibung bleibt.
            stelle = roh.lower().find(rest[:20].lower()) if rest else -1
            return True, (roh[stelle:].strip(" ,.") if stelle >= 0 else rest)
    return False, ""


class Stimme:
    """Sprachausgabe und Spracheingabe mit jeweils zwei Ebenen."""

    def __init__(self):
        self.macos_stimme = ""
        self._whisper_modell = None
        self._temp = tempfile.mkdtemp(prefix="jarvis_audio_")
        self.letzter_fehler = ""
        # Wer zuletzt einen Abschnitt gesprochen hat: fish, elevenlabs oder say.
        self.letzter_anbieter = ""
        self._stopp = threading.Event()
        self._abspiel_prozess = None
        # Nur die Aufnahme setzt das: Mikrofon fehlt oder lässt sich nicht öffnen.
        self.mikro_fehler = ""
        # Der Anzeige-Speicher (setzt ``Werkzeuge.stimme_setzen``): dorthin geht der Pegel
        # der Stimme für den Orb. Ohne ihn spricht Jarvis wie bisher, nur ohne Pegel.
        self.anzeige = None
        # Das Tonformat der Anbieter: mp3 (Standard) oder wav. Mit Anzeige gilt wav,
        # denn nur aus einer WAV-Datei lässt sich der Pegel berechnen.
        self.audioformat = "mp3"
        # Format und Sprache des laufenden Holens – je Faden, denn Telegram und Stimme
        # können gleichzeitig holen.
        self._lokal = threading.local()
        # Austauschbarer Ausführer für ``say``/``afconvert`` (Prüfungen): (befehl, timeout) -> Rückgabewert.
        self.ausfuehren = None
        if self.ist_macos():
            self.macos_stimme = config.MACOS_STIMME or self.deutsche_stimme_suchen()

    # -- Umgebung -----------------------------------------------------------

    @staticmethod
    def ist_macos() -> bool:
        """Läuft das hier auf einem Mac?"""
        return shutil.which("say") is not None and os.uname().sysname == "Darwin"

    def deutsche_stimme_suchen(self) -> str:
        """Sucht die natürlichste vorhandene deutsche Systemstimme.

        Die Premium- und erweiterten Stimmen (zum Beispiel "Anna (Premium)")
        klingen deutlich menschlicher als die kompakten. Ihre Namen enthalten
        Leerzeichen und Klammern - deshalb wird die Zeile von ``say -v ?`` am
        Sprachkürzel getrennt, nicht am ersten Leerzeichen.
        """
        try:
            ergebnis = subprocess.run(["say", "-v", "?"], capture_output=True,
                                      text=True, timeout=10, shell=False)
        except (OSError, subprocess.SubprocessError):
            return ""
        if ergebnis.returncode != 0:
            return ""
        return beste_deutsche_stimme(ergebnis.stdout)

    def zustand(self) -> dict:
        """Was ist verfügbar, was fehlt - für den Selbsttest."""
        return {
            "macos_say": self.ist_macos(),
            "macos_stimme": self.macos_stimme or "keine deutsche gefunden",
            "elevenlabs": bool(config.ELEVENLABS_API_KEY),
            "fish": bool(config.FISH_API_KEY),
            "anbieter": anbieter_reihenfolge(),
            "mikrofon": sd is not None and np is not None,
            "mikrofon_grund": mikrofon_fehlermeldung(),
            "whisper_lokal": WhisperModel is not None,
            "whisper_api": bool(config.OPENAI_API_KEY),
        }

    # -- Ausgabe ------------------------------------------------------------

    ANBIETER_NAMEN = {"fish": "Fish Audio", "elevenlabs": "ElevenLabs", "say": "Systemstimme"}

    def sprich(self, text: str, sprache: str = "de") -> bool:
        """Spricht einen Text so, wie ein Mensch ihn sagen würde.

        Deutscher Text wird zuerst ins Gesprochene übersetzt (Zahlen, Beträge, Daten
        ausgeschrieben, kein Markdown), anderer nur gesäubert (``sprechstuecke_fremd``),
        dann in Atemabschnitte geteilt. Die Anbieter aus ``STIMME_ANBIETER`` kommen der
        Reihe nach dran; der nächste Abschnitt wird schon geholt, während der vorige
        läuft: kein Warten dazwischen, und jeder Abschnitt kennt den Satz davor und
        danach, damit die Betonung durchläuft. Was kein Anbieter schafft, spricht die
        Systemstimme. Vor jedem Abschnitt geht der Pegel an die Anzeige (der Orb).
        """
        sprache = (sprache or "de").strip().lower() or "de"
        stuecke = sprechstuecke(text) if sprache == "de" else sprechstuecke_fremd(text)
        if not stuecke:
            return False
        print("Jarvis: %s" % " ".join(stuecke))
        self._stopp.clear()
        self._lokal.sprache = sprache
        gesprochen = 0
        try:
            for anbieter in anbieter_reihenfolge():
                gesprochen += self._anbieter_sprechen(stuecke[gesprochen:], anbieter, sprache)
                if gesprochen >= len(stuecke):
                    return True
                if self._stopp.is_set():
                    return True
            # Was die Anbieter nicht geschafft haben, übernimmt die Systemstimme: der
            # Satz, bei dem es abbrach, wird nicht noch einmal von vorn gesprochen.
            return self._systemstimme_sprechen(" ".join(stuecke[gesprochen:]))
        finally:
            self._anzeige_melden({"art": "aus"})

    def stoppen(self):
        """Hält die Sprachausgabe sofort an - etwa wenn der Nutzer dazwischenredet."""
        self._stopp.set()
        prozess = self._abspiel_prozess
        if prozess is not None and prozess.poll() is None:
            try:
                prozess.terminate()
            except OSError:
                pass
        self._anzeige_melden({"art": "aus"})

    def _anzeige_melden(self, daten: dict):
        """Schreibt in den Kanal 'stimme' der Anzeige. Nie eine Ausnahme: der Orb darf
        das Sprechen nicht kaputt machen."""
        try:
            if self.anzeige is not None:
                self.anzeige.melden("stimme", daten)
        except Exception as fehler:
            print("[stimme] Anzeige: %s" % fehler)

    def _sprech_format(self) -> str:
        """Das Format, in dem beim Sprechen geholt wird: wav, wenn ein Pegel gebraucht wird."""
        return "wav" if (self.audioformat == "wav" or self.anzeige is not None) else "mp3"

    def _format_jetzt(self) -> str:
        """Das Format für den Abruf in diesem Faden (sonst der Standard der Stimme)."""
        return getattr(self._lokal, "format", None) or self.audioformat or "mp3"

    def _elevenlabs_holen(self, text: str, vorher: str = "", nachher: str = "", vorige=None):
        """Holt die Sprachdatei für einen Abschnitt. ``None`` bei Fehler.

        ``vorige`` sind die Kennungen der Abschnitte davor (höchstens drei). Damit
        setzt ElevenLabs Tonfall und Tempo nahtlos fort - die Antwort klingt wie
        in einem Atemzug gesprochen statt wie aneinandergereihte Ansagen.
        Das Format (mp3 oder wav) steht in ``audioformat``; bei wav kommen rohe
        Töne vom Dienst und werden hier zur WAV-Datei verpackt. Lehnt der Dienst das
        Format ab, wird einmal als MP3 gefragt: lieber ohne Pegelkurve sprechen als gar nicht.
        """
        self._anfrage_id = None
        wav = self._format_jetzt() == "wav"
        sprache = getattr(self._lokal, "sprache", "") or ""
        daten, kennung, fehler = elevenlabs_holen(
            text, "pcm" if wav else "mp3", vorher, nachher, vorige, sprache=sprache)
        if daten is None and wav and "meldet Fehler" in fehler:
            wav = False
            daten, kennung, fehler = elevenlabs_holen(text, "mp3", vorher, nachher, vorige, sprache=sprache)
        self._anfrage_id = kennung
        if daten is None:
            self.letzter_fehler = fehler
            print("[stimme] %s" % fehler)
            return None
        return pcm_als_wav(daten, PEGEL_ABTASTRATE) if wav else daten

    def _fish_holen(self, text: str, vorher: str = "", nachher: str = "", vorige=None):
        """Holt die Sprachdatei für einen Abschnitt von Fish Audio. ``None`` bei Fehler.

        Fish kennt weder den Satz davor noch Kennungen früherer Abschnitte; die
        Parameter stehen nur da, damit beide Anbieter gleich aufgerufen werden.
        """
        del vorher, nachher, vorige
        wav = self._format_jetzt() == "wav"
        daten, fehler = fish_holen(text, "wav" if wav else "mp3", PEGEL_ABTASTRATE)
        if daten is None and wav and "meldet Fehler" in fehler:
            daten, fehler = fish_holen(text, "mp3", PEGEL_ABTASTRATE)
        if daten is None:
            self.letzter_fehler = fehler
            print("[stimme] %s" % fehler)
            return None
        return wav_reparieren(daten) if wav and daten[:4] == b"RIFF" else daten

    def _say_holen(self, text: str, vorher: str = "", nachher: str = "", vorige=None):
        """Lässt die Systemstimme einen Abschnitt als WAV-Datei sprechen. ``None`` bei Fehler."""
        del vorher, nachher, vorige
        ziel = os.path.join(self._temp, "say_%d_%d.wav" % (int(time.time() * 1000),
                                                              threading.get_ident() % 1000))
        try:
            if not self._say_als_wav(text, ziel):
                return None
            with open(ziel, "rb") as datei:
                return datei.read()
        except OSError:
            return None
        finally:
            for pfad in (ziel, ziel[:-4] + ".aiff"):
                try:
                    os.remove(pfad)
                except OSError:
                    pass

    def _befehl_ausfuehren(self, befehl: list, timeout: int = 120) -> bool:
        """Führt einen Befehl aus (ohne Shell). Prüfungen tauschen ``self.ausfuehren`` aus."""
        try:
            if self.ausfuehren is not None:
                return self.ausfuehren(befehl, timeout) in (0, True, None)
            lauf = subprocess.run(befehl, timeout=timeout, shell=False,
                                  stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return lauf.returncode == 0
        except (OSError, subprocess.SubprocessError):
            return False

    def _mac_stimme(self, sprache: str = "de") -> str:
        """Die Systemstimme für eine Sprache: für Deutsch die gewählte, sonst die erste passende."""
        if sprache == "de":
            return self.macos_stimme
        return stimme_fuer_sprache(sprache)

    def _say_als_wav(self, text: str, ziel_wav: str) -> bool:
        """Legt einen Text mit ``say`` als WAV ab. Erst direkt, sonst über AIFF und afconvert.

        Gibt zurück, ob danach eine WAV-Datei mit Inhalt da ist.
        """
        sprache = getattr(self._lokal, "sprache", "de") or "de"
        stimme = self._mac_stimme(sprache)
        rate = config.SPEECH_RATE

        def da():
            try:
                return os.path.getsize(ziel_wav) > 44
            except OSError:
                return False

        self._befehl_ausfuehren(say_befehl(text, ziel_wav, stimme, rate), 120)
        if da():
            return True
        # Manche Mac-Fassungen schreiben nur AIFF: erst sprechen lassen, dann umwandeln.
        aiff = ziel_wav[:-4] + ".aiff"
        befehl = ["say", "-r", str(int(rate))]
        if stimme:
            befehl += ["-v", stimme]
        befehl += ["-o", aiff, str(text or "").lstrip("- ")]
        if self._befehl_ausfuehren(befehl, 120):
            self._befehl_ausfuehren(["afconvert", "-f", "WAVE", "-d",
                                     "LEI16@%d" % PEGEL_ABTASTRATE, aiff, ziel_wav], 60)
        return da()

    def _anbieter_sprechen(self, stuecke: list, anbieter: str, sprache: str = "de") -> int:
        """Spricht Abschnitt für Abschnitt mit einem Anbieter. Gibt zurück, wie viele gesprochen wurden.

        Ein Faden holt die Dateien (höchstens zwei im Voraus), die Wiedergabe spielt sie
        in der Reihenfolge. Ist die Datei eine WAV, wird ihre Pegelkurve berechnet und
        UNMITTELBAR vor dem Abspielen an die Anzeige gemeldet; ``start_ms`` sagt dem
        Orb, wann der Ton einsetzt. Bei einer MP3 gibt es keine Kurve – der Abschnitt
        wird trotzdem gemeldet (mit leerem Pegel), denn die Anzeige folgt seinem Text.
        """
        name = self.ANBIETER_NAMEN.get(anbieter, anbieter)
        holfunktion = {"fish": self._fish_holen, "say": self._say_holen}.get(
            anbieter, self._elevenlabs_holen)
        fertig = queue.Queue(maxsize=2)
        ende = threading.Event()
        format_ = "wav" if anbieter == "say" else self._sprech_format()

        def ablegen(eintrag):
            while not ende.is_set():
                try:
                    fertig.put(eintrag, timeout=0.2)
                    return
                except queue.Full:
                    continue

        def holer():
            # Was auch passiert: am Ende liegt immer ein Abschluss in der Warteschlange,
            # sonst wartet die Wiedergabe für immer.
            self._lokal.format = format_
            self._lokal.sprache = sprache
            try:
                kennungen = []
                for nummer, stueck in enumerate(stuecke):
                    if ende.is_set() or self._stopp.is_set():
                        break
                    self._anfrage_id = None
                    zusatz = {"vorige": kennungen[-3:]} if (kennungen and anbieter == "elevenlabs") else {}
                    daten = holfunktion(
                        stueck, stuecke[nummer - 1] if nummer else "",
                        stuecke[nummer + 1] if nummer + 1 < len(stuecke) else "", **zusatz)
                    if getattr(self, "_anfrage_id", None):
                        kennungen.append(self._anfrage_id)
                    ablegen((nummer, daten))
                    if daten is None:
                        return
            except Exception as fehler:
                self.letzter_fehler = "%s: %s" % (name, fehler)
                ablegen((-1, None))
                return
            finally:
                ablegen(None)

        faden = threading.Thread(target=holer, daemon=True, name="jarvis-stimme-holen")
        faden.start()
        gesprochen = 0
        try:
            while True:
                try:
                    eintrag = fertig.get(timeout=1)
                except queue.Empty:
                    if not faden.is_alive() and fertig.empty():
                        break
                    if self._stopp.is_set():
                        break
                    continue
                if eintrag is None:
                    break
                nummer, daten = eintrag
                if daten is None or self._stopp.is_set():
                    break
                ist_wav = daten[:4] == b"RIFF"
                pfad = os.path.join(self._temp, "antwort_%d_%d.%s"
                                    % (int(time.time() * 1000), nummer, "wav" if ist_wav else "mp3"))
                try:
                    with open(pfad, "wb") as datei:
                        datei.write(daten)
                except OSError:
                    break
                if self.anzeige is not None:
                    self._anzeige_melden({
                        "art": "pegel",
                        "start_ms": time.time() * 1000 + config.STIMME_VORLAUF_MS,
                        "rahmen_ms": 20,
                        "pegel": pegel_aus_wav(daten) if ist_wav else [],
                        "text": stuecke[nummer], "quelle": anbieter})
                erfolg = self.abspielen(pfad)
                try:
                    os.remove(pfad)
                except OSError:
                    pass
                if not erfolg:
                    break
                gesprochen += 1
                self.letzter_anbieter = anbieter
        finally:
            ende.set()
        return gesprochen

    def _elevenlabs_sprechen(self, stuecke: list) -> int:
        """Spricht Abschnitt für Abschnitt mit ElevenLabs (siehe ``_anbieter_sprechen``)."""
        return self._anbieter_sprechen(stuecke, "elevenlabs", "de")

    def _systemstimme_sprechen(self, text: str) -> bool:
        """Sprachausgabe über das eingebaute ``say`` von macOS – der letzte Rückfall.

        Der Rest wird in Abschnitte geteilt, jeder als WAV gesprochen und über ``afplay``
        abgespielt: so hört das Sprechen sofort auf, wenn jemand dazwischenredet, und der
        Orb bekommt den echten Pegel. Gelingt das nicht (kein ``afplay``, keine WAV),
        spricht das einfache ``say`` den Rest in einem Zug; der Orb bekommt dann
        'aus' und zeigt nur den Zustand.
        """
        if not shutil.which("say"):
            return False
        text = (text or "").strip()
        if not text:
            return True
        sprache = getattr(self._lokal, "sprache", "de") or "de"
        stuecke = abschnitte_ziffernsicher(text) or [text]
        gesprochen = 0
        if shutil.which("afplay"):
            gesprochen = self._anbieter_sprechen(stuecke, "say", sprache)
            if gesprochen >= len(stuecke) or self._stopp.is_set():
                return True
        # Der Orb folgt jetzt nur dem Zustand, nicht mehr einem Pegel.
        self._anzeige_melden({"art": "aus"})
        return self._systemstimme_einfach(" ".join(stuecke[gesprochen:]), sprache)

    def _systemstimme_einfach(self, text: str, sprache: str = "de") -> bool:
        """Das alte, einfache ``say``: ein Aufruf, kein Pegel."""
        befehl = ["say", "-r", str(int(config.SPEECH_RATE))]
        stimme = self._mac_stimme(sprache)
        if stimme:
            befehl += ["-v", stimme]
        befehl.append(text[:6000])
        try:
            subprocess.run(befehl, timeout=180, shell=False,
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return True
        except (OSError, subprocess.SubprocessError) as fehler:
            self.letzter_fehler = "Systemstimme fehlgeschlagen: %s" % fehler
            return False

    def abspielen(self, pfad: str) -> bool:
        """Spielt eine Audiodatei ab: afplay, sonst mpg123, sonst ffplay."""
        if not os.path.exists(pfad):
            return False
        varianten = [["afplay", pfad], ["mpg123", "-q", pfad],
                     ["ffplay", "-nodisp", "-autoexit", "-loglevel", "quiet", pfad]]
        for befehl in varianten:
            if not shutil.which(befehl[0]):
                continue
            try:
                self._abspiel_prozess = subprocess.Popen(
                    befehl, shell=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                rueckgabe = self._abspiel_prozess.wait(timeout=300)
                if rueckgabe == 0 or self._stopp.is_set():
                    return True
            except (OSError, subprocess.SubprocessError):
                continue
            finally:
                self._abspiel_prozess = None
        return False

    def signal(self, name: str):
        """Spielt einen kurzen Signalton - Zustand hörbar machen."""
        pfad = SIGNALTOENE.get(name)
        if not pfad or not os.path.exists(pfad) or not shutil.which("afplay"):
            return
        try:
            subprocess.Popen(["afplay", pfad], shell=False,
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except (OSError, subprocess.SubprocessError):
            pass

    def _anbieter_datei(self, text: str, anbieter: str) -> str:
        """Die ganze Antwort mit einem Anbieter als eine MP3-Datei - Abschnitt für Abschnitt,
        nahtlos verbunden. Leer, wenn es nicht klappt."""
        stuecke = sprechstuecke(text)
        teile, kennungen = [], []
        holfunktion = self._fish_holen if anbieter == "fish" else self._elevenlabs_holen
        alt = getattr(self._lokal, "format", None)
        self._lokal.format = "mp3"  # Telegram nimmt MP3; Pegel braucht hier niemand
        try:
            for nummer, stueck in enumerate(stuecke):
                zusatz = {"vorige": kennungen[-3:]} if (kennungen and anbieter == "elevenlabs") else {}
                daten = holfunktion(
                    stueck, stuecke[nummer - 1] if nummer else "",
                    stuecke[nummer + 1] if nummer + 1 < len(stuecke) else "", **zusatz)
                if not daten:
                    return ""
                teile.append(daten)
                if getattr(self, "_anfrage_id", None):
                    kennungen.append(self._anfrage_id)
        finally:
            self._lokal.format = alt
        if not teile:
            return ""
        ziel = os.path.join(self._temp, "nachricht_%d.mp3" % int(time.time() * 1000))
        try:
            with open(ziel, "wb") as datei:
                datei.write(b"".join(teile))
        except OSError:
            return ""
        return ziel

    def _elevenlabs_datei(self, text: str) -> str:
        """Die ganze Antwort mit ElevenLabs als eine MP3-Datei (siehe ``_anbieter_datei``)."""
        return self._anbieter_datei(text, "elevenlabs")

    def sprachdatei_erzeugen(self, text: str, ziel: str = "") -> str:
        """Erzeugt eine Audiodatei aus Text - für Sprachnachrichten per Telegram.

        Mit Fish Audio oder ElevenLabs (Reihenfolge wie beim Sprechen) klingt auch die
        Sprachnachricht wie ein Mensch (Telegram nimmt MP3 an). Sonst spricht die beste
        deutsche Mac-Stimme.
        """
        if not ziel:
            for anbieter in anbieter_reihenfolge():
                datei = self._anbieter_datei(text, anbieter)
                if datei:
                    return datei
        sauber = text_fuers_sprechen(text)
        if not sauber or not shutil.which("say"):
            return ""
        ziel = ziel or os.path.join(self._temp, "nachricht_%d.m4a" % int(time.time()))
        befehl = ["say", "-r", str(int(config.SPEECH_RATE)), "-o", ziel]
        if self.macos_stimme:
            befehl += ["-v", self.macos_stimme]
        befehl.append(sauber[:4000])
        try:
            subprocess.run(befehl, timeout=180, shell=False,
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except (OSError, subprocess.SubprocessError):
            return ""
        if not os.path.exists(ziel):
            return ""
        # Telegram will für Sprachnachrichten OGG/Opus.
        if shutil.which("ffmpeg"):
            ogg = os.path.splitext(ziel)[0] + ".ogg"
            try:
                subprocess.run(["ffmpeg", "-y", "-i", ziel, "-c:a", "libopus",
                                "-b:a", "32k", ogg], timeout=120, shell=False,
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                if os.path.exists(ogg):
                    return ogg
            except (OSError, subprocess.SubprocessError):
                pass
        return ziel

    # -- Aufnahme -----------------------------------------------------------

    def mikrofon_bereit(self) -> bool:
        """Ist eine Aufnahme technisch möglich?"""
        return sd is not None and np is not None

    def aufnehmen_bis_pause(self, still_signal: bool = False) -> str:
        """Nimmt auf, bis der Nutzer 1,2 Sekunden nichts mehr sagt.

        Der Raumpegel wird zu Beginn gemessen, damit ein lauter Raum nicht
        dauernd als Sprache gilt und ein leiser nicht überhört wird.
        """
        self.mikro_fehler = ""
        if not self.mikrofon_bereit():
            self.letzter_fehler = self.mikro_fehler = "Kein Mikrofonzugriff. %s" % mikrofon_fehlermeldung()
            return ""
        blockgroesse = int(ABTASTRATE * BLOCK_SEKUNDEN)
        gesammelt = []
        raumpegel_proben = []
        spricht = False
        stille_seit = 0.0
        beginn = time.time()

        try:
            strom = sd.InputStream(samplerate=ABTASTRATE, channels=1, dtype="float32",
                                   blocksize=blockgroesse)
        except Exception as fehler:
            self.letzter_fehler = self.mikro_fehler = (
                "Das Mikrofon lässt sich nicht öffnen: %s. In den Systemeinstellungen unter "
                "Datenschutz das Mikrofon für das Terminal freigeben." % fehler)
            return ""

        try:
            with strom:
                if not still_signal:
                    self.signal("zuhoeren")
                while True:
                    if time.time() - beginn > MAX_AUFNAHME + 6:
                        break
                    block, ueberlauf = strom.read(blockgroesse)
                    del ueberlauf
                    pegel = float(np.sqrt(np.mean(np.square(block))))

                    if len(raumpegel_proben) < 8:
                        raumpegel_proben.append(pegel)
                        if len(raumpegel_proben) == 8:
                            grundpegel = float(np.median(raumpegel_proben))
                            self._schwelle = max(grundpegel * PEGEL_FAKTOR,
                                                 PEGEL_UNTERGRENZE)
                        continue

                    if pegel >= self._schwelle:
                        spricht = True
                        stille_seit = 0.0
                        gesammelt.append(block.copy())
                    elif spricht:
                        stille_seit += BLOCK_SEKUNDEN
                        gesammelt.append(block.copy())
                        if stille_seit >= STILLE_BIS_ENDE:
                            break
                    if spricht and (time.time() - beginn) > MAX_AUFNAHME:
                        break
        except Exception as fehler:
            self.letzter_fehler = self.mikro_fehler = "Die Aufnahme ist abgebrochen: %s" % fehler
            return ""

        if not gesammelt:
            return ""
        daten = np.concatenate(gesammelt, axis=0)
        dauer = len(daten) / float(ABTASTRATE)
        if dauer < MIN_AUFNAHME:
            return ""  # Zu kurz - das war ein Geräusch, kein Satz.

        pfad = os.path.join(self._temp, "aufnahme_%d.wav" % int(time.time() * 1000))
        try:
            ganzzahlen = (np.clip(daten, -1.0, 1.0) * 32767).astype("int16")
            with wave.open(pfad, "wb") as datei:
                datei.setnchannels(1)
                datei.setsampwidth(2)
                datei.setframerate(ABTASTRATE)
                datei.writeframes(ganzzahlen.tobytes())
        except (OSError, ValueError) as fehler:
            self.letzter_fehler = "Die Aufnahme ließ sich nicht speichern: %s" % fehler
            return ""
        return pfad

    # -- Erkennung ----------------------------------------------------------

    def transkribieren(self, wav_pfad: str) -> str:
        """Wandelt eine Audiodatei in Text - lokal, sonst über die Whisper-API."""
        if not wav_pfad or not os.path.exists(wav_pfad):
            return ""
        text = self._whisper_lokal(wav_pfad)
        if text:
            return text
        return self._whisper_api(wav_pfad)

    def _whisper_lokal(self, wav_pfad: str) -> str:
        """Spracherkennung mit faster-whisper direkt auf dem Rechner (kostenlos)."""
        if WhisperModel is None:
            return ""
        try:
            if self._whisper_modell is None:
                print("[stimme] Lade das Spracherkennungsmodell, das dauert einmalig ...")
                self._whisper_modell = WhisperModel(
                    config.WHISPER_MODELL, device="cpu", compute_type="int8")
            teile, _ = self._whisper_modell.transcribe(wav_pfad, language="de",
                                                       beam_size=1, vad_filter=True)
            return " ".join(teil.text.strip() for teil in teile).strip()
        except Exception as fehler:
            self.letzter_fehler = "Lokale Spracherkennung fehlgeschlagen: %s" % fehler
            print("[stimme] %s" % self.letzter_fehler)
            return ""

    def _whisper_api(self, wav_pfad: str) -> str:
        """Rückfallebene: Whisper über die OpenAI-Schnittstelle."""
        if not config.OPENAI_API_KEY:
            return ""
        grenze = "----jarvis%d" % int(time.time() * 1000)
        try:
            with open(wav_pfad, "rb") as datei:
                audio = datei.read()
        except OSError:
            return ""
        teile = []
        for name, wert in (("model", "whisper-1"), ("language", "de")):
            teile.append(("--%s\r\nContent-Disposition: form-data; name=\"%s\"\r\n\r\n%s\r\n"
                          % (grenze, name, wert)).encode("utf-8"))
        teile.append(("--%s\r\nContent-Disposition: form-data; name=\"file\"; "
                      "filename=\"audio.wav\"\r\nContent-Type: audio/wav\r\n\r\n"
                      % grenze).encode("utf-8"))
        teile.append(audio)
        teile.append(("\r\n--%s--\r\n" % grenze).encode("utf-8"))

        anfrage = urllib.request.Request(WHISPER_URL, data=b"".join(teile), method="POST",
                                         headers={
                                             "Authorization": "Bearer %s" % config.OPENAI_API_KEY,
                                             "Content-Type":
                                                 "multipart/form-data; boundary=%s" % grenze})
        try:
            with urllib.request.urlopen(anfrage, timeout=90) as antwort:
                return json.loads(antwort.read().decode("utf-8")).get("text", "").strip()
        except (urllib.error.URLError, OSError, ValueError) as fehler:
            self.letzter_fehler = "Whisper-API fehlgeschlagen: %s" % fehler
            return ""

    def zuhoeren(self) -> str:
        """Einmal aufnehmen und in Text wandeln."""
        pfad = self.aufnehmen_bis_pause()
        if not pfad:
            return ""
        try:
            text = self.transkribieren(pfad)
        finally:
            try:
                os.remove(pfad)
            except OSError:
                pass
        if text:
            print("Du: %s" % text)
        return text


def sprechprobe(argumente=None) -> int:
    """``python3 jarvis.py sprechprobe [Satz]``: zeigt, wer spricht, und spricht einen Probesatz.

    Sagt ehrlich, was eingerichtet ist und was fehlt (etwa Fish ohne Stimmen-ID), spricht
    den Satz über die Kette und nennt, wer ihn gesprochen hat und wie lange es gedauert hat.
    Die Probe kostet bei Fish und ElevenLabs ein paar Zeichen Guthaben.
    """
    satz = " ".join(argumente or []).strip() or "Guten Tag, hier ist Jarvis. Das ist die Probe meiner Stimme."
    wahl = (config.STIMME_ANBIETER or "auto").strip().lower()
    print("Stimme: Modus %s" % wahl)
    if config.FISH_API_KEY:
        if wahl == "auto" and not config.FISH_STIMME_ID:
            print("  Fish Audio: Schlüssel da, aber FISH_STIMME_ID fehlt – im Modus auto spricht Fish deshalb nicht.")
        else:
            print("  Fish Audio: eingerichtet (Modell %s, Latenz %s)" % (config.FISH_MODELL, config.FISH_LATENZ))
    else:
        print("  Fish Audio: nicht eingerichtet (python3 jarvis.py zugang fish)")
    print("  ElevenLabs: %s" % ("eingerichtet" if config.ELEVENLABS_API_KEY else "nicht eingerichtet"))
    stimme = Stimme()
    kette = anbieter_reihenfolge()
    print("  Reihenfolge: %s" % (", ".join(stimme.ANBIETER_NAMEN[a] for a in kette + ["say"])
                                 if kette else "nur die Mac-Stimme"))
    if not stimme.ist_macos() and not kette:
        print("Hier ist weder ein Stimmen-Dienst eingerichtet noch läuft das auf einem Mac – es gibt nichts zu sprechen.")
        return 1
    beginn = time.time()
    ok = stimme.sprich(satz)
    dauer = time.time() - beginn
    if ok and stimme.letzter_anbieter:
        print("Gesprochen hat: %s (%.1f Sekunden)." % (stimme.ANBIETER_NAMEN.get(
            stimme.letzter_anbieter, stimme.letzter_anbieter), dauer))
    else:
        print("Es hat nichts gesprochen.%s" % (" " + stimme.letzter_fehler if stimme.letzter_fehler else ""))
    if stimme.letzter_fehler:
        print("Letzte Fehlermeldung: %s" % stimme.letzter_fehler)
    return 0 if ok else 1
