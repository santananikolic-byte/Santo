#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Sprache - Mikrofon rein, Stimme raus.

Beides ist mehrstufig aufgebaut, damit **ein einziger Schlüssel** genügt:

    Stimme raus:  ElevenLabs (falls Schlüssel) -> macOS ``say`` (immer da, gratis)
    Sprache rein: faster-whisper lokal (gratis) -> Whisper-API (falls Schlüssel)

Aufgenommen wird bis zur Sprechpause, nicht in festen Blöcken. Feste Blöcke
schneiden entweder mitten im Satz ab oder lassen den Nutzer nach dem letzten
Wort warten - beides fällt im Alltag sofort unangenehm auf.
"""

import importlib.util
import json
import os
import re
import shutil
import subprocess
import tempfile
import time
import urllib.error
import urllib.request
import wave

import config

try:
    import numpy as np
except ImportError:
    np = None

try:
    import sounddevice as sd
except (ImportError, OSError):
    sd = None



def _whisper_klasse():
    """Lädt faster-whisper erst, wenn die lokale Spracherkennung gebraucht wird.

    Das Paket zieht beim ersten Import einen großen Rattenschwanz nach (av,
    ffmpeg-Bibliotheken); auf dem Mac prüft das System jede dieser Dateien
    einmal, das dauert Minuten. Die Web-App erkennt Sprache im Browser und
    braucht das alles nicht - sie soll deshalb nicht daran hängen.
    """
    try:
        from faster_whisper import WhisperModel
        return WhisperModel
    except Exception:
        return None


def whisper_vorhanden() -> bool:
    """Ist faster-whisper installiert? Prüft nur, lädt aber nichts."""
    import importlib.util
    try:
        return importlib.util.find_spec("faster_whisper") is not None
    except (ImportError, ValueError):
        return False

# Die Spracherkennung schreibt den Namen selten korrekt. Alle diese Formen
# werden als Weckwort akzeptiert.
WECKWOERTER = ["hey jarvis", "hey javis", "hey dscharvis", "hey charvis",
               "hey travis", "hey jervis", "hey dscharvis", "jarvis", "javis"]

# Bevorzugte deutsche Systemstimmen, in dieser Reihenfolge.
WUNSCHSTIMMEN = ["Markus", "Yannick", "Petra", "Anna", "Viktor"]

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
    """Entfernt alles, was vorgelesen albern klingt: Sternchen, Striche, Überschriften."""
    if not text:
        return ""
    sauber = str(text)
    sauber = re.sub(r"```.*?```", " ", sauber, flags=re.S)
    sauber = re.sub(r"[*_`#>]+", " ", sauber)
    sauber = re.sub(r"^\s*[-•·]\s*", "", sauber, flags=re.M)
    sauber = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", sauber)
    sauber = re.sub(r"\s+", " ", sauber)
    return sauber.strip()


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
        if self.ist_macos():
            self.macos_stimme = config.MACOS_STIMME or self.deutsche_stimme_suchen()

    # -- Umgebung -----------------------------------------------------------

    @staticmethod
    def ist_macos() -> bool:
        """Läuft das hier auf einem Mac?"""
        return shutil.which("say") is not None and os.uname().sysname == "Darwin"

    def deutsche_stimme_suchen(self) -> str:
        """Sucht die beste vorhandene deutsche Systemstimme."""
        try:
            ergebnis = subprocess.run(["say", "-v", "?"], capture_output=True,
                                      text=True, timeout=10, shell=False)
        except (OSError, subprocess.SubprocessError):
            return ""
        if ergebnis.returncode != 0:
            return ""
        stimmen = []
        for zeile in ergebnis.stdout.splitlines():
            teile = zeile.split()
            if len(teile) >= 2:
                stimmen.append((teile[0], teile[1]))
        vorhandene = {name for name, _ in stimmen}
        for wunsch in WUNSCHSTIMMEN:
            if wunsch in vorhandene:
                return wunsch
        for name, sprache in stimmen:
            if sprache in ("de_DE", "de_AT", "de_CH"):
                return name
        return ""

    def zustand(self) -> dict:
        """Was ist verfügbar, was fehlt - für den Selbsttest."""
        return {
            "macos_say": self.ist_macos(),
            "macos_stimme": self.macos_stimme or "keine deutsche gefunden",
            "elevenlabs": bool(config.ELEVENLABS_API_KEY),
            "mikrofon": sd is not None and np is not None,
            "mikrofon_grund": mikrofon_fehlermeldung(),
            "whisper_lokal": whisper_vorhanden(),
            "whisper_api": bool(config.OPENAI_API_KEY),
        }

    # -- Ausgabe ------------------------------------------------------------

    def sprich(self, text: str) -> bool:
        """Spricht einen Text. ElevenLabs zuerst, sonst die Systemstimme."""
        sauber = text_fuers_sprechen(text)
        if not sauber:
            return False
        print("Jarvis: %s" % sauber)
        if config.ELEVENLABS_API_KEY:
            if self._elevenlabs_sprechen(sauber):
                return True
        return self._systemstimme_sprechen(sauber)

    def _elevenlabs_sprechen(self, text: str) -> bool:
        """Sprachausgabe über ElevenLabs. Scheitert sie, übernimmt ``say``."""
        ziel = "%s/text-to-speech/%s" % (ELEVENLABS_URL, config.ELEVENLABS_VOICE_ID)
        # Die Klangwerte standen bisher fest im Code und waren die
        # Voreinstellung von ElevenLabs - damit klingt jede Stimme gleich
        # brav. Jetzt kommen sie aus der Konfiguration: ruhig, nah am
        # Original, ohne Theatralik.
        koerper = json.dumps({
            "text": text[:4000],
            "model_id": config.ELEVENLABS_MODEL,
            "voice_settings": {
                "stability": config.ELEVENLABS_STABILITY,
                "similarity_boost": config.ELEVENLABS_SIMILARITY,
                "style": config.ELEVENLABS_STYLE,
                "use_speaker_boost": True,
            },
        }).encode("utf-8")
        anfrage = urllib.request.Request(ziel, data=koerper, method="POST", headers={
            "xi-api-key": config.ELEVENLABS_API_KEY,
            "Content-Type": "application/json",
            "Accept": "audio/mpeg",
        })
        try:
            with urllib.request.urlopen(anfrage, timeout=45) as antwort:
                daten = antwort.read()
        except (urllib.error.URLError, OSError) as fehler:
            self.letzter_fehler = "ElevenLabs nicht erreichbar: %s" % fehler
            print("[stimme] %s - ich nehme die Systemstimme." % self.letzter_fehler)
            return False
        pfad = os.path.join(self._temp, "antwort_%d.mp3" % int(time.time() * 1000))
        try:
            with open(pfad, "wb") as datei:
                datei.write(daten)
        except OSError:
            return False
        erfolg = self.abspielen(pfad)
        try:
            os.remove(pfad)
        except OSError:
            pass
        return erfolg

    def _systemstimme_sprechen(self, text: str) -> bool:
        """Sprachausgabe über das eingebaute ``say`` von macOS."""
        if not shutil.which("say"):
            return False
        befehl = ["say", "-r", str(int(config.SPEECH_RATE))]
        if self.macos_stimme:
            befehl += ["-v", self.macos_stimme]
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
                ergebnis = subprocess.run(befehl, timeout=300, shell=False,
                                          stdout=subprocess.DEVNULL,
                                          stderr=subprocess.DEVNULL)
                if ergebnis.returncode == 0:
                    return True
            except (OSError, subprocess.SubprocessError):
                continue
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

    def sprachdatei_erzeugen(self, text: str, ziel: str = "") -> str:
        """Erzeugt eine Audiodatei aus Text - für Sprachnachrichten per Telegram."""
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
        if not self.mikrofon_bereit():
            self.letzter_fehler = "Kein Mikrofonzugriff. %s" % mikrofon_fehlermeldung()
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
            self.letzter_fehler = ("Das Mikrofon lässt sich nicht öffnen: %s. In den "
                                   "Systemeinstellungen unter Datenschutz das Mikrofon "
                                   "für das Terminal freigeben." % fehler)
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
            self.letzter_fehler = "Die Aufnahme ist abgebrochen: %s" % fehler
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
        modell_klasse = _whisper_klasse() if self._whisper_modell is None else True
        if modell_klasse is None:
            return ""
        try:
            if self._whisper_modell is None:
                print("[stimme] Lade das Spracherkennungsmodell, das dauert einmalig ...")
                self._whisper_modell = modell_klasse(
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
