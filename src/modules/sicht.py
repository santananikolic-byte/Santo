#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Dateien der Handerkennung und gespeicherte Handruhe-Messungen.

Die Seite ``/sehen`` erkennt die Hand im Browser (MediaPipe, 21 Punkte). Dieses
Modul hat zwei Aufgaben:

**1. Die Dateien der Handerkennung.** MediaPipe besteht aus sechs Dateien (ein
JavaScript-Bündel, zwei WASM-Lader mit ihren Binärdateien, das Handmodell). Sie
werden **einmal** geladen (``python3 jarvis.py sicht laden``) und danach von
Jarvis selbst ausgeliefert - die Seite fragt nie bei jsDelivr oder Google an,
und ihr Sicherheitskopf erlaubt gar keine fremde Adresse.

* **Feste Prüfsummen.** Für jede Datei steht ihre sha256-Summe fest im Code
  (``SICHT_DATEIEN``). Eine abweichende Datei wird verworfen, nichts bleibt
  liegen. Die Summen der fünf jsDelivr-Dateien stimmen mit denen überein, die
  das npm-Paket selbst ausweist; das Handmodell hat nur Google - seine Summe ist
  die der Datei, die beim Einrichten geprüft wurde. Das Bündel trägt zusätzlich
  die sha384-Summe, die jsDelivr als Teilressourcen-Prüfsumme (SRI) nennt.
* **Die Version steht im Pfad** (``/sicht/dateien/0.10.35/...``). Damit darf der
  Browser die Dateien ein Jahr behalten, und nach einer neuen Version passen
  JavaScript und WASM nie aus Versehen aus zwei Fassungen zusammen.
* **Ausgeliefert werden nur diese sechs Namen.** Kein Pfad, kein ``..``.

**2. Handruhe-Messungen.** Die Seite misst im Browser, wie ruhig die Hand ist,
und schickt nur Zahlen - nie ein Bild. Hier werden sie streng geprüft,
gespeichert und mit den eigenen letzten 14 Tagen verglichen.

**Ehrliche Grenze.** Eine Webcam sieht Bewegungen ab etwa einem halben
Millimeter. Das ist "Handruhe" im Vergleich zu den eigenen Werten - Selbst-
beobachtung, kein Medizinprodukt, und keine Aussage über irgendeine Ursache.
"""

import base64
import hashlib
import hmac
import json
import math
import os
import tempfile
import threading
import time
import urllib.request
from datetime import datetime, timedelta
from pathlib import Path

import config
from modules.memory import db_schema_anlegen

# ---------------------------------------------------------------------------
# Die Dateien der Handerkennung
# ---------------------------------------------------------------------------

SICHT_VERSION = "0.10.35"

# Wohin im Netz der Browser die Dateien holt: nirgends. Ausgeliefert werden sie von hier.
SICHT_DATEIEN_PRAEFIX = "/sicht/dateien/"

_SICHT_NPM = "https://cdn.jsdelivr.net/npm/@mediapipe/tasks-vision@" + SICHT_VERSION
_SICHT_MODELL = ("https://storage.googleapis.com/mediapipe-models/gesture_recognizer/"
                 "gesture_recognizer/float16/1/gesture_recognizer.task")

# Name -> (Adresse, feste Prüfsumme, Inhaltstyp).
# Die Prüfsumme ist "sha256-<hex>" oder "sha384-<base64>" (so schreibt sie jsDelivr als SRI);
# mehrere gelten alle zugleich. ``None`` heißt: beim ersten Laden merken (pruefsummen.json).
SICHT_DATEIEN = {
    "vision_bundle.mjs": (
        _SICHT_NPM + "/vision_bundle.mjs",
        ("sha256-55d7ab624fbb70dcc5adc4ae6d7ea9cfcb569139d3dbfbf2b1deafcb966bc0fe",
         "sha384-Ll1OFMb+0geb9fpvYvxFbnpB/UjqBeQ2iVta6EtAGmIW2s0Oed/AhFDe+32PXnKs"),
        "text/javascript"),
    "vision_wasm_internal.js": (
        _SICHT_NPM + "/wasm/vision_wasm_internal.js",
        "sha256-e7fd9858e8e8f221d9b96eddc11f8e077f263e0b7bbd79d3cbe882b134274f8c",
        "text/javascript"),
    "vision_wasm_internal.wasm": (
        _SICHT_NPM + "/wasm/vision_wasm_internal.wasm",
        "sha256-6a5c64584c2ab61c763b6e204afbdbc7ce1caf7f5216187322bca8df94f646bc",
        "application/wasm"),
    "vision_wasm_nosimd_internal.js": (
        _SICHT_NPM + "/wasm/vision_wasm_nosimd_internal.js",
        "sha256-438d1fe8ff7f4d946025bc211c291543c037d8a3785ed4eee60f1f521b236296",
        "text/javascript"),
    "vision_wasm_nosimd_internal.wasm": (
        _SICHT_NPM + "/wasm/vision_wasm_nosimd_internal.wasm",
        "sha256-8a3092d34c79d3f57e6ba8592105e8a90f6b07c27891ffecd14cca428bfd3e31",
        "application/wasm"),
    "gesture_recognizer.task": (
        _SICHT_MODELL,
        "sha256-97952348cf6a6a4915c2ea1496b4b37ebabc50cbbf80571435643c455f2b0482",
        "application/octet-stream"),
}

SICHT_MAX_BYTES = 40 * 1024 * 1024      # keine Datei ist größer; mehr ist ein Fehler
SICHT_TIMEOUT = 120                      # Sekunden je Datei
SICHT_NICHT_GELADEN = ("Die Handerkennung ist noch nicht geladen. "
                       "Im Terminal: python3 jarvis.py sicht laden")
SICHT_HINWEIS = ("Selbstbeobachtung, kein Medizinprodukt. "
                 "Eine Webcam sieht nur Bewegungen ab etwa einem halben Millimeter.")

_SICHT_PRUEFSUMMEN = "pruefsummen.json"
# Datei -> (Pfad, Änderungszeit, Größe, Sollwerte), die in diesem Prozess schon geprüft wurde.
_SICHT_GEPRUEFT = {}
_SICHT_SPERRE = threading.Lock()


def sicht_ordner() -> Path:
    """Wo die Dateien liegen: ``modelle/sicht-<Version>`` (der Ordner ist nicht im Repository)."""
    return Path(config.MODELL_VERZEICHNIS) / ("sicht-" + SICHT_VERSION)


def sicht_an() -> bool:
    """Ist die Live-Kamera eingeschaltet? Ohne ``SICHT_AN`` bleibt die Seite zu."""
    return bool(config.SICHT_AN)


def _sicht_soll(eintrag) -> tuple:
    """Die festen Prüfsummen eines Eintrags als Tupel (leer: keine)."""
    soll = eintrag[1] if isinstance(eintrag, (tuple, list)) and len(eintrag) > 1 else None
    if not soll:
        return ()
    if isinstance(soll, str):
        return (soll,)
    return tuple(s for s in soll if isinstance(s, str) and s)


def sicht_pruefsumme_stimmt(daten: bytes, soll: str) -> bool:
    """Passt die Datei zu ``sha256-<hex>`` oder ``sha384-<base64>``? Andere Formen: nein."""
    art, _, wert = str(soll or "").strip().partition("-")
    if not wert:
        return False
    if art == "sha256":
        return hmac.compare_digest(hashlib.sha256(daten).hexdigest(), wert.lower())
    if art == "sha384":
        return hmac.compare_digest(base64.b64encode(hashlib.sha384(daten).digest()).decode("ascii"),
                                   wert)
    return False


def _sicht_pruefsummen_lesen(ordner: Path) -> dict:
    """Was beim Laden notiert wurde: Name -> sha256 (hex). Fehlt die Datei: leer."""
    try:
        roh = json.loads((ordner / _SICHT_PRUEFSUMMEN).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return {str(k): str(v) for k, v in roh.items()} if isinstance(roh, dict) else {}


def _sicht_pruefsummen_schreiben(ordner: Path, summen: dict):
    ziel = ordner / _SICHT_PRUEFSUMMEN
    temp = ziel.with_name(ziel.name + ".tmp")
    temp.write_text(json.dumps(summen, indent=2, sort_keys=True), encoding="utf-8")
    os.replace(str(temp), str(ziel))


def _sicht_abweichung(name: str, daten: bytes, eintrag, summen: dict) -> str:
    """Leer, wenn die Datei stimmt - sonst der Satz, warum nicht.

    Mit fester Prüfsumme zählt nur sie (alle genannten). Ohne feste Prüfsumme gilt
    die beim ersten Laden notierte; gibt es noch keine, ist die Datei neu und wird
    notiert (aufrufender Code).
    """
    falsch = ("Die Datei %s stimmt nicht mit der erwarteten Prüfsumme überein – "
              "nichts gespeichert." % name)
    fest = _sicht_soll(eintrag)
    if fest:
        return "" if all(sicht_pruefsumme_stimmt(daten, s) for s in fest) else falsch
    notiert = summen.get(name)
    if notiert and not sicht_pruefsumme_stimmt(daten, "sha256-" + notiert):
        return falsch
    return ""


def _sicht_holen(url: str) -> bytes:
    """Lädt eine Adresse, höchstens ``SICHT_MAX_BYTES`` und ``SICHT_TIMEOUT`` Sekunden lang."""
    anfrage = urllib.request.Request(
        url, headers={"User-Agent": "Jarvis/1.0 (Handerkennung laden)"})
    ende = time.monotonic() + SICHT_TIMEOUT
    teile, gesamt = [], 0
    with urllib.request.urlopen(anfrage, timeout=SICHT_TIMEOUT) as antwort:
        try:
            angekuendigt = int(antwort.headers.get("Content-Length") or 0)
        except (TypeError, ValueError):
            angekuendigt = 0
        if angekuendigt > SICHT_MAX_BYTES:
            raise ValueError("die Datei ist größer als erlaubt")
        while True:
            stueck = antwort.read(1 << 16)
            if not stueck:
                break
            gesamt += len(stueck)
            if gesamt > SICHT_MAX_BYTES:
                raise ValueError("die Datei ist größer als erlaubt")
            if time.monotonic() > ende:
                raise TimeoutError("das Laden dauert zu lange")
            teile.append(stueck)
    return b"".join(teile)


def _sicht_mb(byte: int) -> str:
    return ("%.1f" % (byte / 1e6)).replace(".", ",")


def sicht_laden(holen=None, melden=print, neu: bool = False) -> dict:
    """Lädt die Dateien der Handerkennung, prüft sie und legt sie ab.

    ``holen(url) -> bytes`` ist austauschbar (Prüfungen). Eine Datei wird nur
    behalten, wenn sie zu ihrer festen Prüfsumme passt - sonst bleibt nichts
    liegen. Was schon da ist und stimmt, wird nicht noch einmal geladen
    (``neu=True`` erzwingt es). Gibt ``{"ok", "dateien", "text"}`` zurück.
    """
    holen = holen or _sicht_holen
    melden = melden or (lambda text: None)
    ordner = sicht_ordner()
    try:
        ordner.mkdir(parents=True, exist_ok=True)
    except OSError as fehler:
        return {"ok": False, "dateien": [],
                "text": "Ich kann den Ordner %s nicht anlegen (%s)." % (ordner, fehler)}
    summen = _sicht_pruefsummen_lesen(ordner)
    dateien, fehler_liste, gesamt = [], [], 0

    for name, eintrag in list(SICHT_DATEIEN.items()):
        url = eintrag[0]
        ziel = ordner / name
        if not neu and ziel.is_file():
            try:
                vorhanden = ziel.read_bytes()
            except OSError:
                vorhanden = b""
            fest = _sicht_soll(eintrag)
            if vorhanden and (fest or name in summen) \
                    and not _sicht_abweichung(name, vorhanden, eintrag, summen):
                melden("%s ist schon da und stimmt." % name)
                dateien.append({"name": name, "bytes": len(vorhanden), "neu": False})
                gesamt += len(vorhanden)
                summen[name] = hashlib.sha256(vorhanden).hexdigest()
                continue
        melden("Lade %s ..." % name)
        try:
            roh = holen(url)
        except Exception as fehler:
            text = "%s konnte ich nicht laden (%s)." % (name, str(fehler)[:120] or type(fehler).__name__)
            melden(text)
            fehler_liste.append(text)
            continue
        if not isinstance(roh, (bytes, bytearray)) or not roh:
            text = "%s kam leer an." % name
            melden(text)
            fehler_liste.append(text)
            continue
        roh = bytes(roh)
        if len(roh) > SICHT_MAX_BYTES:
            text = "%s ist größer als erlaubt – nichts gespeichert." % name
            melden(text)
            fehler_liste.append(text)
            continue
        abweichung = _sicht_abweichung(name, roh, eintrag, summen)
        if abweichung:
            melden(abweichung)
            fehler_liste.append(abweichung)
            continue
        try:
            handle, temp = tempfile.mkstemp(prefix=name + ".", suffix=".tmp", dir=str(ordner))
            try:
                with os.fdopen(handle, "wb") as datei:
                    datei.write(roh)
                os.replace(temp, str(ziel))
            except BaseException:
                try:
                    os.unlink(temp)
                except OSError:
                    pass
                raise
        except OSError as fehler:
            text = "%s konnte ich nicht speichern (%s)." % (name, fehler)
            melden(text)
            fehler_liste.append(text)
            continue
        summen[name] = hashlib.sha256(roh).hexdigest()
        dateien.append({"name": name, "bytes": len(roh), "neu": True})
        gesamt += len(roh)
        melden("  %s MB, Prüfsumme stimmt." % _sicht_mb(len(roh)))

    try:
        _sicht_pruefsummen_schreiben(ordner, summen)
    except OSError as fehler:
        fehler_liste.append("Die Prüfsummen konnte ich nicht notieren (%s)." % fehler)
    with _SICHT_SPERRE:
        _SICHT_GEPRUEFT.clear()
    if fehler_liste:
        return {"ok": False, "dateien": dateien,
                "text": "Die Handerkennung ist nicht vollständig geladen. " + " ".join(fehler_liste)}
    return {"ok": True, "dateien": dateien,
            "text": "Die Handerkennung ist geladen (%s MB)." % _sicht_mb(gesamt)}


def _sicht_pruefen(name: str, eintrag, roh: bytes) -> str:
    """Prüft eine gelesene Datei gegen ihre Sollwerte - einmal je Prozess und Dateistand.

    Leer, wenn sie stimmt, sonst der Satz, warum nicht.
    """
    pfad = sicht_ordner() / name
    try:
        stat = pfad.stat()
    except OSError:
        return SICHT_NICHT_GELADEN
    fest = _sicht_soll(eintrag)
    schluessel = (str(pfad), stat.st_mtime_ns, stat.st_size, fest)
    with _SICHT_SPERRE:
        if _SICHT_GEPRUEFT.get(name) == schluessel:
            return ""
    summen = {} if fest else _sicht_pruefsummen_lesen(pfad.parent)
    if not fest and name not in summen:
        return ("Zu %s fehlt die Prüfsumme. Bitte neu laden: python3 jarvis.py sicht laden" % name)
    if _sicht_abweichung(name, roh, eintrag, summen):
        return ("Die Datei %s stimmt nicht mit der erwarteten Prüfsumme überein. "
                "Bitte neu laden: python3 jarvis.py sicht laden" % name)
    with _SICHT_SPERRE:
        _SICHT_GEPRUEFT[name] = schluessel
    return ""


def sicht_datei(name) -> tuple:
    """Eine Datei der Handerkennung: ``(bytes, inhaltstyp)`` oder ``(None, fehlertext)``.

    Es gibt nur die Namen aus ``SICHT_DATEIEN`` - kein Pfad, kein ``..``. Die
    Prüfsumme wird einmal je Prozess geprüft (und neu, wenn sich die Datei ändert).
    """
    eintrag = SICHT_DATEIEN.get(name) if isinstance(name, str) else None
    if eintrag is None:
        return None, "Diese Datei gibt es nicht."
    try:
        roh = (sicht_ordner() / name).read_bytes()
    except OSError:
        return None, SICHT_NICHT_GELADEN
    if not roh:
        return None, SICHT_NICHT_GELADEN
    fehler = _sicht_pruefen(name, eintrag, roh)
    if fehler:
        return None, fehler
    return roh, eintrag[2]


def sicht_bereit() -> bool:
    """Sind alle Dateien da und unverändert? (Gelesen wird nur, was noch nicht geprüft ist.)"""
    for name, eintrag in list(SICHT_DATEIEN.items()):
        try:
            stat = (sicht_ordner() / name).stat()
        except OSError:
            return False
        schluessel = (str(sicht_ordner() / name), stat.st_mtime_ns, stat.st_size, _sicht_soll(eintrag))
        with _SICHT_SPERRE:
            if _SICHT_GEPRUEFT.get(name) == schluessel:
                continue
        if sicht_datei(name)[0] is None:
            return False
    return True


def _sicht_pfad_lesen(pfad: str):
    """``/sicht/dateien/<Version>/<Name>`` -> ``(version, name)``, sonst ``None``."""
    pfad = str(pfad or "")
    if not pfad.startswith(SICHT_DATEIEN_PRAEFIX):
        return None
    teile = pfad[len(SICHT_DATEIEN_PRAEFIX):].split("/")
    if len(teile) != 2 or not teile[0] or not teile[1]:
        return None
    return teile[0], teile[1]


def sicht_pfad_oeffentlich(pfad: str) -> bool:
    """Ist das einer der Dateipfade, die ohne Schlüssel ausgeliefert werden?

    Nur die Version dieser Fassung und die sechs weißgelisteten Namen. Es sind
    öffentliche Bibliotheken, keine Daten; die Seite lädt sie per ``import`` und
    über MediaPipe selbst - dabei lässt sich kein Schlüssel anhängen. Die
    Prüfung des Host-Kopfes bleibt bestehen.
    """
    teile = _sicht_pfad_lesen(pfad)
    return bool(teile) and teile[0] == SICHT_VERSION and teile[1] in SICHT_DATEIEN


def sicht_ausliefern(pfad: str) -> tuple:
    """Antwort für ``GET /sicht/dateien/<Version>/<Name>``: ``(code, inhalt, typ_oder_fehler)``."""
    teile = _sicht_pfad_lesen(pfad)
    if teile is None:
        return 404, None, "Diese Datei gibt es nicht."
    version, name = teile
    if version != SICHT_VERSION:
        return 404, None, "Diese Version gibt es nicht. Hier liegt %s." % SICHT_VERSION
    roh, typ = sicht_datei(name)
    if roh is None:
        return 404, None, typ
    return 200, roh, typ


# ---------------------------------------------------------------------------
# Handruhe
# ---------------------------------------------------------------------------

SCHEMA_HANDRUHE = """
CREATE TABLE IF NOT EXISTS handruhe (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tag TEXT,
    zeit TEXT,
    art TEXT,
    mm REAL,
    rauschen_mm REAL,
    rhythmus_hz REAL,
    spitze REAL,
    fps REAL,
    dauer_s REAL,
    bilder INTEGER,
    handlaenge_mm REAL
);
CREATE INDEX IF NOT EXISTS idx_handruhe_tag ON handruhe(tag, art);
"""

HANDRUHE_ARTEN = ("ruhe", "halten")
# Mehr Messungen als das am Tag sind ein Fehler der Seite, keine Selbstbeobachtung.
HANDRUHE_MAX_TAG = 100
# Ab so vielen früheren Haltemessungen vergleiche ich.
HANDRUHE_VERGLEICH_AB = 5
HANDRUHE_VERGLEICHSTAGE = 14
HANDRUHE_MIN_FPS = 25

# Name -> (kleinster Wert, größter Wert, darf fehlen)
_HANDRUHE_ZAHLEN = (
    ("mm", 0.0, 20.0, False),
    ("rauschen_mm", 0.0, 20.0, True),
    ("rhythmus_hz", 3.0, 14.0, True),
    ("spitze_verhaeltnis", 0.0, 1e6, True),
    ("fps", 10.0, 120.0, False),
    ("dauer_s", 4.0, 30.0, False),
)


def _sicht_echte_zahl(wert) -> bool:
    """Eine endliche Zahl - kein Text, kein Ja/Nein, kein NaN."""
    return (isinstance(wert, (int, float)) and not isinstance(wert, bool)
            and math.isfinite(wert))


def _sicht_komma(wert, stellen: int = 1) -> str:
    return ("%.*f" % (stellen, wert)).replace(".", ",")


def messung_pruefen(daten) -> tuple:
    """Prüft eine Messung der Seite streng: ``(sauberes Wörterbuch, "")`` oder ``(None, Fehler)``.

    Gelesen werden nur die Felder des Vertrags. Zahlen müssen endlich und echte
    Zahlen sein (kein Text, kein Ja/Nein, kein NaN) und im erlaubten Bereich liegen.
    Unter 25 Bildern pro Sekunde sieht die Kamera ein 10-Hz-Zittern nicht richtig
    (es faltet sich auf eine falsche Frequenz) - dann kommt "Mehr Licht, bitte".
    """
    if not isinstance(daten, dict):
        return None, "Die Messung ist kein gültiges Wörterbuch."
    art = daten.get("art")
    if not isinstance(art, str) or art not in HANDRUHE_ARTEN:
        return None, "Die Art der Messung fehlt (ruhe oder halten)."
    sauber = {"art": art}
    for name, klein, gross, darf_fehlen in _HANDRUHE_ZAHLEN:
        wert = daten.get(name)
        if wert is None and darf_fehlen:
            sauber[name] = None
            continue
        if not _sicht_echte_zahl(wert):
            return None, "Der Wert '%s' fehlt oder ist keine Zahl." % name
        if wert < klein or wert > gross:
            return None, "Der Wert '%s' liegt außerhalb von %g bis %g." % (name, klein, gross)
        sauber[name] = float(wert)
    bilder = daten.get("bilder")
    if isinstance(bilder, float) and bilder.is_integer():
        bilder = int(bilder)
    if not isinstance(bilder, int) or isinstance(bilder, bool):
        return None, "Der Wert 'bilder' fehlt oder ist keine ganze Zahl."
    if bilder < 40 or bilder > 4000:
        return None, "Der Wert 'bilder' liegt außerhalb von 40 bis 4000."
    sauber["bilder"] = bilder
    laenge = daten.get("handlaenge_mm")
    if laenge is None:
        laenge = config.HANDLAENGE_MM
    if not _sicht_echte_zahl(laenge):
        return None, "Der Wert 'handlaenge_mm' ist keine Zahl."
    if laenge < 60 or laenge > 130:
        return None, "Der Wert 'handlaenge_mm' liegt außerhalb von 60 bis 130."
    sauber["handlaenge_mm"] = float(laenge)
    if sauber["fps"] < HANDRUHE_MIN_FPS:
        return None, ("Mehr Licht, bitte – die Messung braucht mindestens %d Bilder pro Sekunde."
                      % HANDRUHE_MIN_FPS)
    return sauber, ""


def sicht_kanal_schreiben(anzeige, teile: dict, dauer_s: float = 120):
    """Schreibt Teile in den Anzeige-Kanal ``sicht`` und lässt die anderen Teile stehen.

    Der Kanal trägt ``handruhe``, ``erholung`` und ``zusammenhang`` - jedes Modul
    liefert nur seinen Teil. Ein einfaches ``melden`` würde die anderen löschen,
    darum wird mit dem bisherigen Stand gemischt. ``anzeige`` ist der Speicher oder
    die Werkzeuge (die ihn ``anzeige`` nennen). Schluckt jeden Fehler: die Anzeige
    darf nie etwas kaputt machen. Gibt die neue Version zurück oder ``None``.
    """
    if anzeige is None:
        return None
    try:
        speicher = getattr(anzeige, "anzeige", anzeige)
        bisher = {}
        lesen = getattr(speicher, "stand", None)
        if callable(lesen):
            stand = lesen("sicht")
            if isinstance(stand, dict) and isinstance(stand.get("daten"), dict):
                bisher = stand["daten"]
        neu = dict(bisher)
        neu.update(teile)
        neu.setdefault("hinweis", "Selbstbeobachtung, kein Medizinprodukt.")
        version = anzeige.melden("sicht", neu)
        anzeige.zeigen("sicht", {}, dauer_s)
        return version
    except Exception as fehler:
        print("[sicht] Anzeige: %s" % fehler)
        return None


class Handruhe:
    """Speichert die Handruhe-Messungen der Seite ``/sehen`` und vergleicht sie.

    ``anzeige`` ist der Anzeige-Speicher oder die Werkzeuge (beide haben ``melden``
    und ``zeigen``). ``uhr`` liefert ein ``datetime`` (für Prüfungen austauschbar).
    """

    def __init__(self, memory, anzeige=None, uhr=None):
        self.memory = memory
        self.anzeige = anzeige
        self._uhr = uhr or datetime.now
        self._sperre = threading.Lock()
        db_schema_anlegen(SCHEMA_HANDRUHE, self.memory.db_pfad)

    # -- Hilfen ---------------------------------------------------------------

    def _tag(self, vor_tagen: int = 0) -> str:
        return (self._uhr() - timedelta(days=vor_tagen)).strftime("%Y-%m-%d")

    @staticmethod
    def _zeile(z: dict) -> dict:
        return {"id": z["id"], "tag": z["tag"], "zeit": z["zeit"], "art": z["art"],
                "mm": z["mm"], "rauschen_mm": z["rauschen_mm"], "rhythmus_hz": z["rhythmus_hz"],
                "spitze_verhaeltnis": z["spitze"], "fps": z["fps"], "dauer_s": z["dauer_s"],
                "bilder": z["bilder"], "handlaenge_mm": z["handlaenge_mm"]}

    def _frueher(self, art: str) -> list:
        """mm-Werte der bisherigen Messungen dieser Art aus den letzten 14 Tagen."""
        zeilen = self.memory._lesen(
            "SELECT mm FROM handruhe WHERE art=? AND tag>? ORDER BY id",
            (art, self._tag(HANDRUHE_VERGLEICHSTAGE)))
        return [z["mm"] for z in zeilen if z["mm"] is not None]

    # -- Speichern --------------------------------------------------------------

    def speichern(self, daten) -> dict:
        """Prüft und speichert eine Messung und gibt den Text zurück, der gesagt wird.

        ``{"ok", "text", "vergleich", ...}``; bei Ungültigem ``{"ok": False, "fehler"}``.
        """
        m, fehler = messung_pruefen(daten)
        if m is None:
            return {"ok": False, "fehler": fehler}
        jetzt = self._uhr()
        tag = jetzt.strftime("%Y-%m-%d")
        with self._sperre:
            heute_n = self.memory._lesen("SELECT count(*) AS n FROM handruhe WHERE tag=?", (tag,))
            if heute_n and heute_n[0]["n"] >= HANDRUHE_MAX_TAG:
                return {"ok": False, "fehler": "Für heute sind genug Messungen gespeichert."}
            frueher = self._frueher(m["art"])
            ruhe_heute = self.memory._lesen(
                "SELECT mm FROM handruhe WHERE art='ruhe' AND tag=? ORDER BY id DESC LIMIT 1", (tag,))
            nummer = self.memory._schreiben(
                "INSERT INTO handruhe (tag, zeit, art, mm, rauschen_mm, rhythmus_hz, spitze, fps, "
                "dauer_s, bilder, handlaenge_mm) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                (tag, jetzt.strftime("%Y-%m-%d %H:%M:%S"), m["art"], m["mm"], m["rauschen_mm"],
                 m["rhythmus_hz"], m["spitze_verhaeltnis"], m["fps"], m["dauer_s"], m["bilder"],
                 m["handlaenge_mm"]))
        ruhe_mm = ruhe_heute[0]["mm"] if ruhe_heute else m["rauschen_mm"]
        text, vergleich = self._text(m, frueher, ruhe_mm)
        sicht_kanal_schreiben(self.anzeige, {"handruhe": {
            "mm": round(m["mm"], 2),
            "rauschen_mm": round(ruhe_mm, 2) if _sicht_echte_zahl(ruhe_mm) else None,
            "rhythmus_hz": round(m["rhythmus_hz"], 2) if m["rhythmus_hz"] is not None else None,
            "fps": round(m["fps"], 1), "vergleich": vergleich, "tag": tag}})
        return {"ok": True, "id": nummer, "text": text, "vergleich": vergleich}

    @staticmethod
    def _text(m: dict, frueher: list, ruhe_mm) -> tuple:
        """Der Satz zur Messung und das Wort für den Vergleich ("unruhiger", "ruhiger", "ähnlich")."""
        mm = _sicht_komma(m["mm"])
        vergleich = ""
        if m["art"] == "ruhe":
            teile = ["Ruhemessung heute: %s mm (Schätzung) – das ist das Grundrauschen von "
                     "Kamera und Licht." % mm]
        elif len(frueher) >= HANDRUHE_VERGLEICH_AB:
            mittel = sum(frueher) / len(frueher)
            if m["mm"] > mittel * 1.15:
                vergleich = "unruhiger"
            elif m["mm"] < mittel * 0.85:
                vergleich = "ruhiger"
            else:
                vergleich = "ähnlich"
            wie = {"unruhiger": "unruhiger als", "ruhiger": "ruhiger als", "ähnlich": "ähnlich wie"}
            teile = ["Handruhe heute: %s mm (Schätzung) – %s dein 14-Tage-Mittel von %s mm."
                     % (mm, wie[vergleich], _sicht_komma(mittel))]
        else:
            teile = ["Handruhe heute: %s mm (Schätzung). Für einen Vergleich brauche ich noch "
                     "ein paar Messungen." % mm]
        if m["rhythmus_hz"] is not None:
            teile.append("Rhythmus um %s Hz." % _sicht_komma(m["rhythmus_hz"]))
        else:
            teile.append("Kein deutlicher Rhythmus.")
        if m["art"] == "halten" and _sicht_echte_zahl(ruhe_mm) and ruhe_mm > 0:
            verhaeltnis = m["mm"] / ruhe_mm
            teile.append("Verhältnis zur Ruhemessung %s." % _sicht_komma(verhaeltnis))
            if verhaeltnis < 1.3:
                teile.append("Das liegt nahe am Grundrauschen der Kamera.")
        teile.append("Selbstbeobachtung, kein Medizinprodukt.")
        return " ".join(teile), vergleich

    # -- Lesen ------------------------------------------------------------------

    def letzte(self):
        """Die jüngste Messung oder ``None``."""
        zeilen = self.memory._lesen("SELECT * FROM handruhe ORDER BY id DESC LIMIT 1")
        return self._zeile(zeilen[0]) if zeilen else None

    def verlauf(self, tage=14) -> dict:
        """Die Messungen der letzten ``tage`` Tage (alt zuerst) und je Tag der letzte Wert."""
        try:
            tage = max(1, min(90, int(tage)))
        except (TypeError, ValueError):
            tage = 14
        zeilen = self.memory._lesen(
            "SELECT * FROM handruhe WHERE tag>? ORDER BY id", (self._tag(tage),))
        messungen = [self._zeile(z) for z in zeilen]
        je_tag = {}
        for z in messungen:
            tageswerte = je_tag.setdefault(z["tag"], {"tag": z["tag"], "halten_mm": None,
                                                     "ruhe_mm": None, "anzahl": 0})
            tageswerte["halten_mm" if z["art"] == "halten" else "ruhe_mm"] = z["mm"]
            tageswerte["anzahl"] += 1
        return {"ok": True, "tage": tage, "messungen": messungen,
                "tageswerte": [je_tag[t] for t in sorted(je_tag)]}

    def stand(self, erholung=None, schreiben: bool = True, diskret: bool = False,
              vorschlag=None) -> dict:
        """Der Stand für ``GET /api/sicht/stand`` (und das Werkzeug ``sicht_stand``).

        ``erholung``: das Erholungsmodul (oder ``None``), ``schreiben``: ob hier
        gespeichert werden darf (Web-App, nicht die Anzeige des Dienstes),
        ``diskret``: dann gibt es keine Gesundheitswerte. ``vorschlag``:
        ``{"id", "text"}`` des Vorschlags, auf den eine Geste antworten dürfte.
        """
        letzte, erholung_stand = None, None
        if not diskret:
            letzte = self.letzte()
            heute = getattr(erholung, "heute", None)
            if callable(heute):
                try:
                    antwort = heute()
                except Exception as fehler:
                    print("[sicht] Erholung: %s" % fehler)
                    antwort = None
                if isinstance(antwort, dict) and antwort.get("ok"):
                    erholung_stand = {"wert": antwort.get("wert"), "band": antwort.get("band"),
                                      "quelle": antwort.get("quelle"), "tag": antwort.get("tag")}
        try:
            laenge = float(config.HANDLAENGE_MM)
        except (TypeError, ValueError):
            laenge = 95.0
        return {"ok": True, "an": sicht_an(), "dateien_da": sicht_bereit(),
                "geste": bool(config.GESTEN_FREIGABE),
                "handlaenge_mm": laenge, "schreiben": bool(schreiben), "diskret": bool(diskret),
                "erholung": erholung_stand, "handruhe_letzte": letzte,
                "vorschlag": vorschlag if (schreiben and not diskret) else None,
                "hinweis": SICHT_HINWEIS}


def sicht_stand_bauen(werkzeuge, schreiben: bool = True, diskret: bool = False) -> dict:
    """Der Stand der Sicht aus den Werkzeugen heraus - für die Route und das Werkzeug.

    Erholung und Vorschläge (Pakete P5 und P4) werden erst jetzt gesucht, nicht beim Import.
    """
    vorschlag = None
    vorschlaege = getattr(werkzeuge, "vorschlaege", None)
    if schreiben and not diskret and config.GESTEN_FREIGABE \
            and callable(getattr(vorschlaege, "letzter_offener", None)):
        try:
            letzter = vorschlaege.letzter_offener()
        except Exception as fehler:
            print("[sicht] Vorschlag: %s" % fehler)
            letzter = None
        if isinstance(letzter, dict) and letzter.get("id") is not None:
            vorschlag = {"id": letzter["id"], "text": str(letzter.get("text") or "")[:400]}
    return werkzeuge.handruhe.stand(erholung=getattr(werkzeuge, "erholung", None),
                                    schreiben=schreiben, diskret=diskret, vorschlag=vorschlag)


def sicht_stand_text(stand: dict) -> str:
    """Der Stand in zwei, drei Sätzen für das Werkzeug ``sicht_stand``."""
    if not stand.get("an"):
        teile = ["Die Live-Kamera ist ausgeschaltet (Einschalten: python3 jarvis.py sicht an)."]
    else:
        teile = ["Die Live-Kamera ist eingeschaltet - das Bild bleibt im Browser auf der Seite Sicht."]
    teile.append("Die Handerkennung ist geladen." if stand.get("dateien_da")
                 else "Die Handerkennung ist noch nicht geladen (python3 jarvis.py sicht laden).")
    letzte = stand.get("handruhe_letzte")
    if letzte:
        teile.append("Letzte Handruhe-Messung: %s mm (Schätzung) am %s." % (_sicht_komma(letzte["mm"]), letzte["tag"]))
    elif not stand.get("diskret"):
        teile.append("Es gibt noch keine Handruhe-Messung.")
    teile.append("Selbstbeobachtung, kein Medizinprodukt.")
    return " ".join(teile)


# ---------------------------------------------------------------------------
# Daumen hoch beantwortet einen Vorschlag
# ---------------------------------------------------------------------------

# So alt muss ein Vorschlag sein, bevor eine Geste ihn beantworten darf (wie bei Freigaben).
VORSCHLAG_GESTE_MINDESTALTER = 2.0


def _sicht_vorschlag_antworten(web, ja: bool):
    """Im eigenen Faden: Claude sagen, was der Daumen bedeutet, und die Antwort melden."""
    satz = "Ja, mach das." if ja else "Nein, lass das."
    try:
        agent = web.agent
        if not agent.einsatzbereit():
            web.melden("Vermerkt. Ohne Anthropic-Schlüssel kann ich dazu nichts weiter tun.")
            return
        agent.memory.verlauf_anhaengen("user", satz + " (per Daumen)")
        with web._denkt:
            antwort = agent.denken(satz, protokollieren=False)
        if antwort:
            web.melden(antwort)
    except Exception as fehler:
        print("[sicht] Antwort auf die Geste: %s" % fehler)


def vorschlag_per_geste(web, daten) -> tuple:
    """``POST /api/vorschlag/geste {id, ja}``: Daumen hoch (oder runter) zu einem Vorschlag.

    Gilt nur in der Web-App, nur mit ``GESTEN_FREIGABE``, nur für den jüngsten
    offenen Vorschlag (höchstens 15 Minuten alt, mindestens 2 Sekunden) und nur,
    wenn keine Freigabefrage offen ist - dann gehört der Daumen der Freigabe. Ein
    "Ja" nimmt den Vorschlag nur an; alles, was danach nach außen wirkt, fragt
    einzeln nach Freigabe. Der Herkunftskopf ist schon von der Web-App geprüft.
    Gibt ``(Statuscode, Antwort)`` zurück.
    """
    if not config.GESTEN_FREIGABE:
        return 403, {"ok": False, "text": "Die Gesten-Freigabe ist ausgeschaltet."}
    vorschlaege = getattr(web.agent.tools, "vorschlaege", None)
    if not callable(getattr(vorschlaege, "letzter_offener", None)):
        return 404, {"ok": False, "text": "Vorschläge gibt es hier nicht."}
    daten = daten if isinstance(daten, dict) else {}
    kennung = daten.get("id")
    if isinstance(kennung, bool) or not isinstance(kennung, int):
        return 400, {"ok": False, "text": "Mir fehlt die Nummer des Vorschlags."}
    if not isinstance(daten.get("ja"), bool):
        return 400, {"ok": False, "text": "Mir fehlt, ob Ja oder Nein gemeint ist."}
    ja = daten["ja"]
    try:
        if web.freigabe.offene():
            return 409, {"ok": False, "text": "Die Geste zählt hier nicht: Es ist eine "
                                             "Freigabefrage offen, und die geht zuerst."}
        letzter = vorschlaege.letzter_offener()
    except Exception as fehler:
        print("[sicht] Vorschlag: %s" % fehler)
        return 500, {"ok": False, "text": "Das konnte ich gerade nicht prüfen."}
    if not isinstance(letzter, dict) or letzter.get("id") != kennung:
        return 409, {"ok": False, "text": "Dieser Vorschlag ist nicht mehr der jüngste offene."}
    try:
        alter = (datetime.now() - datetime.strptime(str(letzter.get("angelegt")), "%Y-%m-%d %H:%M:%S")
                 ).total_seconds()
    except (TypeError, ValueError):
        alter = None
    if alter is not None and alter < VORSCHLAG_GESTE_MINDESTALTER:
        return 409, {"ok": False, "text": "Die Geste zählt hier nicht: Der Vorschlag ist erst "
                                         "gerade gemacht. Lies ihn in Ruhe und zeige die Geste "
                                         "dann noch einmal."}
    ergebnis = vorschlaege.beantworten(kennung, ja)
    if not isinstance(ergebnis, dict) or not ergebnis.get("ok"):
        fehler = (ergebnis or {}).get("fehler") if isinstance(ergebnis, dict) else ""
        return 409, {"ok": False, "text": fehler or "Der Vorschlag ist nicht mehr offen."}
    threading.Thread(target=_sicht_vorschlag_antworten, args=(web, ja), daemon=True,
                     name="sicht-geste").start()
    return 200, {"ok": True, "text": ("Angenommen. Ich kümmere mich darum und frage bei allem "
                                      "Weiteren einzeln nach." if ja else "Abgelehnt.")}


# ---------------------------------------------------------------------------
# Terminal: python3 jarvis.py sicht laden | an | aus
# ---------------------------------------------------------------------------

def sicht_befehl(argumente) -> int:
    """``python3 jarvis.py sicht laden|an|aus`` - ohne Angabe der Stand. Gibt den Exit-Code zurück."""
    was = (argumente[0] if argumente else "").strip().lower()
    if was == "laden":
        ergebnis = sicht_laden()
        print(ergebnis["text"])
        return 0 if ergebnis["ok"] else 1
    if was in ("an", "ein"):
        config.env_setzen("SICHT_AN", "ja")
        print("Die Live-Kamera ist eingeschaltet (SICHT_AN=ja). Jarvis einmal neu starten, "
              "dann geht die Seite Sicht (/sehen) auf.")
        print("Das Bild bleibt im Browser; gespeichert werden nur Messzahlen, nie ein Bild.")
        if not sicht_bereit():
            print("Die Handerkennung fehlt noch: python3 jarvis.py sicht laden")
        return 0
    if was in ("aus", "ab"):
        config.env_setzen("SICHT_AN", "nein")
        print("Die Live-Kamera ist ausgeschaltet. Jarvis einmal neu starten, damit die Seite zugeht.")
        return 0
    if was in ("", "status"):
        print("Live-Kamera: %s" % ("an" if sicht_an() else "aus (python3 jarvis.py sicht an)"))
        print("Handerkennung: %s" % ("geladen" if sicht_bereit()
                                     else "nicht geladen (python3 jarvis.py sicht laden)"))
        return 0
    print("Das kenne ich nicht: sicht %s. Möglich sind: laden, an, aus." % was)
    return 2
