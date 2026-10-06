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
from modules.sprechtext import sprechstuecke, sprechtext

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
        self._stopp = threading.Event()
        self._abspiel_prozess = None
        # Nur die Aufnahme setzt das: Mikrofon fehlt oder lässt sich nicht öffnen.
        self.mikro_fehler = ""
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
            "mikrofon": sd is not None and np is not None,
            "mikrofon_grund": mikrofon_fehlermeldung(),
            "whisper_lokal": WhisperModel is not None,
            "whisper_api": bool(config.OPENAI_API_KEY),
        }

    # -- Ausgabe ------------------------------------------------------------

    def sprich(self, text: str) -> bool:
        """Spricht einen Text so, wie ein Mensch ihn sagen würde.

        Der Text wird zuerst ins Gesprochene übersetzt (Zahlen, Beträge, Daten
        ausgeschrieben, kein Markdown) und in Atemabschnitte geteilt. Mit
        ElevenLabs wird der nächste Abschnitt schon geholt, während der
        vorige läuft: kein Warten dazwischen, und jeder Abschnitt kennt den
        Satz davor und danach, damit die Betonung durchläuft. Ohne ElevenLabs
        spricht die Systemstimme.
        """
        stuecke = sprechstuecke(text)
        if not stuecke:
            return False
        print("Jarvis: %s" % " ".join(stuecke))
        self._stopp.clear()
        gesprochen = 0
        if config.ELEVENLABS_API_KEY:
            gesprochen = self._elevenlabs_sprechen(stuecke)
            if gesprochen >= len(stuecke):
                return True
            if self._stopp.is_set():
                return True
        # Was ElevenLabs nicht geschafft hat, übernimmt die Systemstimme: der
        # Satz, bei dem es abbrach, wird nicht noch einmal von vorn gesprochen.
        return self._systemstimme_sprechen(" ".join(stuecke[gesprochen:]))

    def stoppen(self):
        """Hält die Sprachausgabe sofort an - etwa wenn der Nutzer dazwischenredet."""
        self._stopp.set()
        prozess = self._abspiel_prozess
        if prozess is not None and prozess.poll() is None:
            try:
                prozess.terminate()
            except OSError:
                pass

    def _elevenlabs_holen(self, text: str, vorher: str = "", nachher: str = "", vorige=None):
        """Holt die Sprachdatei für einen Abschnitt. ``None`` bei Fehler.

        ``vorige`` sind die Kennungen der Abschnitte davor (höchstens drei). Damit
        setzt ElevenLabs Tonfall und Tempo nahtlos fort - die Antwort klingt wie
        in einem Atemzug gesprochen statt wie aneinandergereihte Ansagen.
        """
        self._anfrage_id = None
        ziel = "%s/text-to-speech/%s" % (ELEVENLABS_URL, config.ELEVENLABS_VOICE_ID)
        inhalt = {
            "text": text[:2500],
            "model_id": config.ELEVENLABS_MODEL,
            "voice_settings": {
                "stability": config.ELEVENLABS_STABILITY,
                "similarity_boost": config.ELEVENLABS_SIMILARITY,
                "style": config.ELEVENLABS_STYLE,
                "use_speaker_boost": True,
            },
        }
        # Der Satz davor und danach: so wird eine Stimme, die in Stücken
        # spricht, nicht zu lauter einzelnen Ansagen.
        if vorher:
            inhalt["previous_text"] = vorher[-300:]
        if nachher:
            inhalt["next_text"] = nachher[:300]
        if vorige:
            inhalt["previous_request_ids"] = list(vorige)[-3:]
        anfrage = urllib.request.Request(
            ziel, data=json.dumps(inhalt).encode("utf-8"), method="POST", headers={
                "xi-api-key": config.ELEVENLABS_API_KEY,
                "Content-Type": "application/json",
                "Accept": "audio/mpeg",
            })
        try:
            with urllib.request.urlopen(anfrage, timeout=45) as antwort:
                daten = antwort.read()
                self._anfrage_id = antwort.headers.get("request-id") or None
                return daten
        except (urllib.error.URLError, OSError, http.client.HTTPException, ValueError) as fehler:
            self.letzter_fehler = "ElevenLabs nicht erreichbar: %s" % fehler
            print("[stimme] %s - ich nehme die Systemstimme." % self.letzter_fehler)
            return None

    def _elevenlabs_sprechen(self, stuecke: list) -> int:
        """Spricht Abschnitt für Abschnitt. Gibt zurück, wie viele gesprochen wurden."""
        fertig = queue.Queue(maxsize=2)
        ende = threading.Event()

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
            try:
                kennungen = []
                for nummer, stueck in enumerate(stuecke):
                    if ende.is_set() or self._stopp.is_set():
                        break
                    self._anfrage_id = None
                    zusatz = {"vorige": kennungen[-3:]} if kennungen else {}
                    daten = self._elevenlabs_holen(
                        stueck, stuecke[nummer - 1] if nummer else "",
                        stuecke[nummer + 1] if nummer + 1 < len(stuecke) else "", **zusatz)
                    if getattr(self, "_anfrage_id", None):
                        kennungen.append(self._anfrage_id)
                    ablegen((nummer, daten))
                    if daten is None:
                        return
            except Exception as fehler:
                self.letzter_fehler = "ElevenLabs: %s" % fehler
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
                pfad = os.path.join(self._temp, "antwort_%d_%d.mp3"
                                    % (int(time.time() * 1000), nummer))
                try:
                    with open(pfad, "wb") as datei:
                        datei.write(daten)
                except OSError:
                    break
                erfolg = self.abspielen(pfad)
                try:
                    os.remove(pfad)
                except OSError:
                    pass
                if not erfolg:
                    break
                gesprochen += 1
        finally:
            ende.set()
        return gesprochen

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

    def _elevenlabs_datei(self, text: str) -> str:
        """Die ganze Antwort mit ElevenLabs als eine MP3-Datei - Abschnitt für Abschnitt,
        nahtlos verbunden. Leer, wenn es nicht klappt."""
        stuecke = sprechstuecke(text)
        teile, kennungen = [], []
        for nummer, stueck in enumerate(stuecke):
            zusatz = {"vorige": kennungen[-3:]} if kennungen else {}
            daten = self._elevenlabs_holen(
                stueck, stuecke[nummer - 1] if nummer else "",
                stuecke[nummer + 1] if nummer + 1 < len(stuecke) else "", **zusatz)
            if not daten:
                return ""
            teile.append(daten)
            if getattr(self, "_anfrage_id", None):
                kennungen.append(self._anfrage_id)
        if not teile:
            return ""
        ziel = os.path.join(self._temp, "nachricht_%d.mp3" % int(time.time() * 1000))
        try:
            with open(ziel, "wb") as datei:
                datei.write(b"".join(teile))
        except OSError:
            return ""
        return ziel

    def sprachdatei_erzeugen(self, text: str, ziel: str = "") -> str:
        """Erzeugt eine Audiodatei aus Text - für Sprachnachrichten per Telegram.

        Mit ElevenLabs klingt auch die Sprachnachricht wie ein Mensch (Telegram
        nimmt MP3 an). Sonst spricht die beste deutsche Mac-Stimme.
        """
        if config.ELEVENLABS_API_KEY and not ziel:
            datei = self._elevenlabs_datei(text)
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
