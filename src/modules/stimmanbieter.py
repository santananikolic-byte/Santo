#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Die Anbieterkette der Sprachausgabe – mit Pegelkurve für den Orb.

Wer spricht, entscheidet ``STIMME_ANBIETER``:

    auto        Fish Audio (nur mit Schlüssel UND Stimmen-ID), dann ElevenLabs
    fish        nur Fish Audio (die Stimmen-ID ist dann freiwillig)
    elevenlabs  nur ElevenLabs
    mac         keiner dieser Dienste – es spricht die Systemstimme

Die Mac-Stimme ist immer der letzte Rückfall und steht deshalb nicht in der Liste
(:func:`anbieter_reihenfolge`); sie gehört zu ``voice.Stimme``.

Alle Netzaufrufe haben eine einspeisbare ``holen``-Funktion (Prüfungen laufen ohne
Netz). Sie hat die Form von ``urllib.request.urlopen``: ``holen(anfrage, timeout)``
liefert etwas mit ``read()`` und ``headers``.

Die **Pegelkurve** ist die Lautstärke der gesprochenen Datei in Schritten von 20
Millisekunden, 0 bis 255 (:func:`pegel_aus_wav`). Der Orb liest daraus, wie laut
Jarvis gerade ist – echt, nicht nachempfunden. Nur Standardbibliothek.
"""

import array
import io
import json
import math
import os
import sys
import urllib.error
import urllib.request
import wave
from operator import mul

import config

FISH_URL = "https://api.fish.audio/v1/tts"
ELEVENLABS_TTS = "https://api.elevenlabs.io/v1/text-to-speech/%s"

# Die Abtastrate, in der Jarvis Sprache für Pegel und Wiedergabe holt.
PEGEL_ABTASTRATE = 22050
# Mehr als 9000 Werte (drei Minuten) trägt der Anzeige-Speicher nicht.
PEGEL_MAX_WERTE = 9000
# Wie lange ein Anbieter für einen Abschnitt höchstens braucht.
ANBIETER_TIMEOUT = 45

FORMAT_TYPEN = {"mp3": "audio/mpeg", "wav": "audio/wav"}


def anbieter_reihenfolge() -> list:
    """Welche Dienste sprechen dürfen, in der Reihenfolge, in der sie es versuchen.

    ``auto``: Fish nur, wenn Schlüssel UND Stimmen-ID da sind – ohne ID spräche
    Fish mit einer Standardstimme, die kaum Deutsch kann. Dann ElevenLabs.
    ``fish`` / ``elevenlabs``: nur der gewählte, wenn sein Schlüssel da ist.
    ``mac`` (und alles Unbekannte außer ``auto``): leer – es spricht die Systemstimme.
    """
    wahl = (config.STIMME_ANBIETER or "auto").strip().lower()
    fish = bool(config.FISH_API_KEY)
    eleven = bool(config.ELEVENLABS_API_KEY)
    if wahl == "fish":
        return ["fish"] if fish else []
    if wahl == "elevenlabs":
        return ["elevenlabs"] if eleven else []
    if wahl != "auto":
        return []
    reihe = []
    if fish and config.FISH_STIMME_ID:
        reihe.append("fish")
    if eleven:
        reihe.append("elevenlabs")
    return reihe


def _oeffnen(anfrage, timeout=ANBIETER_TIMEOUT):
    """Der echte Netzaufruf. Wird erst beim Aufruf nachgeschlagen, damit
    Prüfungen ``urllib.request.urlopen`` austauschen können."""
    return urllib.request.urlopen(anfrage, timeout=timeout)


def pcm_als_wav(pcm: bytes, rate: int = PEGEL_ABTASTRATE) -> bytes:
    """Verpackt rohe 16-Bit-Töne (ein Kanal, little endian) als WAV-Datei."""
    puffer = io.BytesIO()
    with wave.open(puffer, "wb") as datei:
        datei.setnchannels(1)
        datei.setsampwidth(2)
        datei.setframerate(int(rate))
        datei.writeframes(pcm or b"")
    return puffer.getvalue()


# -- Fish Audio ------------------------------------------------------------------------------

def fish_holen(text: str, format: str = "mp3", rate: int = PEGEL_ABTASTRATE, holen=None) -> tuple:
    """Holt einen Text als Sprache von Fish Audio. Gibt ``(bytes oder None, fehler)`` zurück.

    Das Modell steht im Kopf der Anfrage (``model``), nicht im Körper. ``normalize``
    bleibt aus: Fish normalisiert nur Englisch und Chinesisch, und Jarvis schreibt
    Zahlen und Beträge selbst aus (``sprechtext``). Für wav und pcm gehört die
    Abtastrate in den Körper.
    """
    if not config.FISH_API_KEY:
        return None, "Für Fish Audio ist kein Schlüssel hinterlegt."
    inhalt = {"text": str(text or "")[:2500], "format": format,
              "latency": config.FISH_LATENZ or "balanced", "normalize": False}
    if config.FISH_STIMME_ID:
        inhalt["reference_id"] = config.FISH_STIMME_ID
    if format in ("wav", "pcm"):
        inhalt["sample_rate"] = int(rate)
    anfrage = urllib.request.Request(
        FISH_URL, data=json.dumps(inhalt).encode("utf-8"), method="POST", headers={
            "Authorization": "Bearer %s" % config.FISH_API_KEY,
            "Content-Type": "application/json",
            "model": config.FISH_MODELL or "s2.1-pro",
        })
    try:
        with (holen or _oeffnen)(anfrage, ANBIETER_TIMEOUT) as antwort:
            daten = antwort.read()
    except urllib.error.HTTPError as fehler:
        meldungen = {401: "Fish Audio lehnt den Schlüssel ab.",
                     402: "Bei Fish Audio ist kein Guthaben mehr.",
                     503: "Fish Audio ist gerade überlastet."}
        return None, meldungen.get(fehler.code, "Fish Audio meldet Fehler %d." % fehler.code)
    except (urllib.error.URLError, OSError, ValueError) as fehler:
        return None, "Fish Audio nicht erreichbar: %s" % fehler
    except Exception as fehler:  # http.client.HTTPException und Verwandte
        return None, "Fish Audio nicht erreichbar: %s" % fehler
    if not daten:
        return None, "Fish Audio hat keinen Ton geschickt."
    return daten, ""


# -- ElevenLabs ------------------------------------------------------------------------------

def elevenlabs_holen(text: str, format: str = "mp3", vorher: str = "", nachher: str = "",
                     vorige=None, sprache: str = "", holen=None) -> tuple:
    """Holt einen Text als Sprache von ElevenLabs. Gibt ``(bytes oder None, anfrage_id, fehler)`` zurück.

    ``format`` ``pcm`` liefert rohe 16-Bit-Töne bei 22,05 kHz (daraus macht
    :func:`pcm_als_wav` eine WAV-Datei), ``mp3`` die gewohnte MP3. ``vorher`` und
    ``nachher`` sind die Sätze davor und danach, ``vorige`` die Kennungen der
    Abschnitte davor – so klingt eine Antwort in Stücken wie ein Atemzug.
    ``sprache`` wirkt nur bei den schnellen Modellen (flash, turbo).
    """
    if not config.ELEVENLABS_API_KEY:
        return None, None, "Für ElevenLabs ist kein Schlüssel hinterlegt."
    ziel = ELEVENLABS_TTS % config.ELEVENLABS_VOICE_ID
    kopf = {"xi-api-key": config.ELEVENLABS_API_KEY, "Content-Type": "application/json"}
    if format == "pcm":
        ziel += "?output_format=pcm_%d" % PEGEL_ABTASTRATE
    else:
        kopf["Accept"] = "audio/mpeg"
    modell = config.ELEVENLABS_MODEL
    inhalt = {
        "text": str(text or "")[:2500],
        "model_id": modell,
        "voice_settings": {
            "stability": config.ELEVENLABS_STABILITY,
            "similarity_boost": config.ELEVENLABS_SIMILARITY,
            "style": config.ELEVENLABS_STYLE,
            "use_speaker_boost": True,
        },
    }
    if vorher:
        inhalt["previous_text"] = vorher[-300:]
    if nachher:
        inhalt["next_text"] = nachher[:300]
    if vorige:
        inhalt["previous_request_ids"] = list(vorige)[-3:]
    if sprache and ("flash" in modell or "turbo" in modell):
        inhalt["language_code"] = sprache
    anfrage = urllib.request.Request(
        ziel, data=json.dumps(inhalt).encode("utf-8"), method="POST", headers=kopf)
    try:
        with (holen or _oeffnen)(anfrage, ANBIETER_TIMEOUT) as antwort:
            daten = antwort.read()
            kennung = antwort.headers.get("request-id") or None
    except urllib.error.HTTPError as fehler:
        meldungen = {401: "ElevenLabs lehnt den Schlüssel ab.",
                     402: "Bei ElevenLabs ist das Guthaben aufgebraucht.",
                     429: "ElevenLabs ist gerade überlastet."}
        return None, None, meldungen.get(fehler.code, "ElevenLabs meldet Fehler %d." % fehler.code)
    except Exception as fehler:
        return None, None, "ElevenLabs nicht erreichbar: %s" % fehler
    if not daten:
        return None, kennung, "ElevenLabs hat keinen Ton geschickt."
    return daten, kennung, ""


# -- Die ganze Kette ---------------------------------------------------------------------------

def sprachaudio(text: str, format: str = "mp3", sprache: str = "de", holen=None) -> dict:
    """Spricht einen Text über die Kette der Anbieter und gibt die Datei zurück.

    ``format`` ist ``mp3`` oder ``wav``. Ergebnis:
    ``{"ok", "daten", "typ", "anbieter", "fehler"}``. Ohne eingerichteten Anbieter
    (oder wenn alle scheitern) ist ``ok`` falsch und ``fehler`` sagt warum; die
    Systemstimme gehört nicht in diese Kette, sie liefert keine Datei an den Browser.
    """
    format = "wav" if format == "wav" else "mp3"
    typ = FORMAT_TYPEN[format]
    fehler = ""
    for anbieter in anbieter_reihenfolge():
        if anbieter == "fish":
            daten, grund = fish_holen(text, format, PEGEL_ABTASTRATE, holen)
        else:
            if format == "wav":
                daten, _, grund = elevenlabs_holen(text, "pcm", sprache=sprache, holen=holen)
                if daten:
                    daten = pcm_als_wav(daten)
            else:
                daten, _, grund = elevenlabs_holen(text, "mp3", sprache=sprache, holen=holen)
        if daten:
            return {"ok": True, "daten": daten, "typ": typ, "anbieter": anbieter, "fehler": ""}
        fehler = grund or fehler
    return {"ok": False, "daten": None, "typ": typ, "anbieter": "",
            "fehler": fehler or "Keine Sprachausgabe eingerichtet."}


# -- Pegel ------------------------------------------------------------------------------------

def pegel_aus_wav(quelle, rahmen_ms: int = 20) -> list:
    """Die Lautstärke einer WAV-Datei als Hüllkurve: ein Wert von 0 bis 255 je Rahmen.

    ``quelle`` sind WAV-Bytes, ein Dateipfad oder ein geöffnetes Dateiobjekt.
    Je Rahmen: Effektivwert, daraus dBFS, dann ``(dB + 50) / 50 * 255`` auf 0 bis 255
    begrenzt – also Stille ab minus 50 dB, Vollaussteuerung bei 0 dB. Gelesen werden
    nur 16-Bit-Töne (mehrere Kanäle werden gemittelt). Alles andere – eine MP3, ein
    abgeschnittener Kopf, 8 oder 24 Bit – ergibt eine leere Liste, nie eine
    Ausnahme: ohne Kurve spielt Jarvis trotzdem, nur der Orb bleibt dann beim Zustand.
    """
    geoeffnet = None
    try:
        if isinstance(quelle, (bytes, bytearray, memoryview)):
            quelle = io.BytesIO(bytes(quelle))
        elif isinstance(quelle, (str, os.PathLike)):
            quelle = geoeffnet = open(quelle, "rb")
        with wave.open(quelle, "rb") as datei:
            kanaele = datei.getnchannels()
            breite = datei.getsampwidth()
            rate = datei.getframerate()
            if breite != 2 or kanaele < 1 or rate <= 0:
                return []
            rohdaten = datei.readframes(datei.getnframes())
    except (wave.Error, EOFError, OSError, ValueError, TypeError, AttributeError):
        return []
    finally:
        if geoeffnet is not None:
            geoeffnet.close()
    try:
        toene = array.array("h")
        toene.frombytes(rohdaten[:len(rohdaten) - (len(rohdaten) % 2)])
        if sys.byteorder == "big":
            toene.byteswap()
        if kanaele > 1:
            toene = array.array("h", (int(sum(toene[i:i + kanaele]) / kanaele)
                                      for i in range(0, len(toene) - kanaele + 1, kanaele)))
        rahmen = max(1, int(rate * max(1, int(rahmen_ms)) / 1000.0))
        werte = []
        for start in range(0, len(toene), rahmen):
            stueck = toene[start:start + rahmen]
            if not stueck:
                break
            effektiv = math.sqrt(sum(map(mul, stueck, stueck)) / float(len(stueck)))
            if effektiv <= 0:
                werte.append(0)
                continue
            dezibel = 20.0 * math.log10(effektiv / 32768.0)
            werte.append(int(max(0.0, min(255.0, (dezibel + 50.0) / 50.0 * 255.0))))
            if len(werte) >= PEGEL_MAX_WERTE:
                break
        return werte
    except (ValueError, OverflowError, MemoryError):
        return []


# -- Mac-Stimme ---------------------------------------------------------------------------------

def say_befehl(text: str, ziel_wav: str, stimme: str, rate) -> list:
    """Der Befehl, der einen Text mit ``say`` als WAV-Datei (16 Bit, 22,05 kHz) ablegt.

    Ohne ``stimme`` entfällt ``-v`` – dann spricht die Systemstimme der Einstellungen.
    Ein Text, der mit einem Strich beginnt, würde ``say`` für eine Option halten;
    führende Striche und Leerzeichen fallen deshalb weg.
    """
    befehl = ["say", "-r", str(int(rate))]
    if stimme:
        befehl += ["-v", stimme]
    befehl += ["-o", ziel_wav, "--data-format=LEI16@%d" % PEGEL_ABTASTRATE,
               str(text or "").lstrip("- ")]
    return befehl
