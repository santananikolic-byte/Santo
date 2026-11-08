# -*- coding: utf-8 -*-
"""Präsentationen - eine Datei zum Doppelklicken: öffnet im Browser, läuft ohne Internet, auch auf dem Handy.

Blättern mit Pfeiltasten, Leertaste, Wischen oder Tippen; F = Vollbild. Zum Verschicken: im Browser drucken ->
"Als PDF sichern" (eine Seite pro Folie).

Eingabe (vom Modell geschrieben, vom Nutzer jederzeit änderbar)::

    # Titel der Präsentation
    Untertitel (optional)

    ## Folientitel
    - Punkt
    Ein Satz als Absatz.
    Bild: bilder:Baustellen/Berger/1 vorher/IMG_3.jpg | Vorher

Sicherheit: Jeder Text wird maskiert (kein HTML/Skript aus dem Inhalt). Bilder nur aus der Werkstatt und den
verwalteten Mac-Ordnern, nur Bilddateien, nie aus Paketen wie der Fotos-Mediathek. HEIC wird mit ``sips``
(auf jedem Mac vorhanden) in JPEG umgewandelt und, wenn größer, verkleinert (nie vergrößert); ohne sips werden nur
JPEG/PNG/GIF/WebP eingebettet.

Datenschutz: Handyfotos tragen den Aufnahmeort (GPS) in sich - auch nach dem Umwandeln. Vor dem Einbetten wird er aus
jedem JPEG entfernt (GPS-Angaben genullt, XMP-Blöcke weggelassen); Ausrichtung und Aufnahmedatum bleiben. So verrät
eine Präsentation für Kunden nicht, wo andere Baustellen oder Wohnungen liegen.
"""

import base64
import html
import os
import re
import shutil
import subprocess
import tempfile

from . import ordnung

BILDARTEN = {"jpg": "image/jpeg", "jpeg": "image/jpeg", "png": "image/png", "gif": "image/gif", "webp": "image/webp"}
UMWANDELBAR = ("heic", "heif", "tif", "tiff", "bmp", "jpg", "jpeg", "png", "webp", "gif")
DIREKT = ("jpg", "jpeg", "png", "gif")  # ohne sips nur, was sich sicher von Metadaten befreien lässt (kein WebP)
MAX_BILDER = 30
MAX_BILD_QUELLE = 40 * 1024 * 1024  # größer liest JARVIS ein Bild gar nicht erst
MAX_BILD_DIREKT = 4 * 1024 * 1024  # ohne sips: nur kleinere Bilder direkt einbetten
MAX_GESAMT = 40 * 1024 * 1024
MAX_FOLIEN = 60
FARBE = re.compile(r"^#[0-9a-fA-F]{6}$")


class PraesentationFehler(Exception):
    """Fehler, den der Nutzer verstehen soll."""


# ------------------------------------------------------------------ Lesen ---

def lesen(text, titel=""):
    """Text -> {"titel", "untertitel", "folien": [{"titel", "punkte", "absaetze", "bilder": [(angabe, beschriftung)]}]}."""
    ergebnis = {"titel": titel.strip(), "untertitel": "", "folien": []}
    folie = None
    for zeile in (text or "").replace("\r\n", "\n").split("\n"):
        z = zeile.strip()
        if not z:
            continue
        if z.startswith("## "):
            folie = {"titel": z[3:].strip(), "punkte": [], "absaetze": [], "bilder": []}
            ergebnis["folien"].append(folie)
        elif z.startswith("# ") and not ergebnis["folien"]:
            ergebnis["titel"] = ergebnis["titel"] or z[2:].strip()
        elif folie is None:
            ergebnis["untertitel"] = (ergebnis["untertitel"] + " " + z).strip() if ergebnis["untertitel"] else z
        elif re.match(r"^bild\s*:", z, re.I):
            angabe, _, beschriftung = z.split(":", 1)[1].partition("|")
            folie["bilder"].append((angabe.strip(), beschriftung.strip()))
        elif z.startswith(("- ", "* ", "• ")):
            folie["punkte"].append(z[2:].strip())
        else:
            folie["absaetze"].append(z)
    if not ergebnis["titel"]:
        raise PraesentationFehler("Es fehlt ein Titel (erste Zeile \"# Titel\").")
    if not ergebnis["folien"]:
        raise PraesentationFehler("Es fehlen Folien (jede beginnt mit \"## Folientitel\").")
    if len(ergebnis["folien"]) > MAX_FOLIEN:
        raise PraesentationFehler("Höchstens %d Folien." % MAX_FOLIEN)
    return ergebnis


# ------------------------------------------------------------------ Bilder ---

def bild_pfad(konfig, angabe):
    """ "bilder:Baustellen/Berger/IMG_3.jpg" oder "praesentationen/logo.png" (Werkstatt) -> (Pfad, Endung)."""
    try:
        _, pfad, endung = ordnung.datei_aufloesen(konfig, angabe)
    except ordnung.OrdnungFehler as fehler:
        raise PraesentationFehler(str(fehler)) from None
    if endung not in BILDARTEN and endung not in UMWANDELBAR:
        raise PraesentationFehler("%r ist kein Bild (JPG, PNG, HEIC …)." % angabe)
    return pfad, endung


def _sips():
    fest = os.environ.get("JARVIS_SIPS")  # nur für Tests
    if fest:
        return fest if os.path.isfile(fest) and os.access(fest, os.X_OK) else None
    return shutil.which("sips")


MAX_KANTE = 1600
GROESSE = {1: 1, 2: 1, 3: 2, 4: 4, 5: 8, 6: 1, 7: 1, 8: 2, 9: 4, 10: 8, 11: 4, 12: 8}  # Bytes je TIFF-Wert nach Typ
XMP = (b"http://ns.adobe.com/xap/1.0/\x00", b"http://ns.adobe.com/xmp/extension/\x00")


def _gps_nullen(segment):
    """GPS-Angaben eines EXIF-Blocks (APP1) mit Nullen überschreiben. ``segment``: bytearray ab dem Marker.
    Gibt True zurück, wenn es GPS-Angaben gab."""
    basis = 10  # FF E1, Länge (2), "Exif\0\0" - alle Versätze zählen ab dem TIFF-Kopf
    tiff = segment[basis:]
    if len(tiff) < 8 or tiff[:2] not in (b"II", b"MM"):
        return False
    reihe = "little" if tiff[:2] == b"II" else "big"

    def zahl(stelle, laenge):
        return int.from_bytes(tiff[stelle:stelle + laenge], reihe) if 0 <= stelle and stelle + laenge <= len(tiff) else -1

    ifd0 = zahl(4, 4)
    gps = -1
    for k in range(max(min(zahl(ifd0, 2), 300), 0)):
        p = ifd0 + 2 + 12 * k
        if zahl(p, 2) == 0x8825:
            gps = zahl(p + 8, 4)
            break
    anzahl = zahl(gps, 2) if gps > 0 else -1
    if anzahl <= 0:
        return False
    anzahl = min(anzahl, 100)
    for k in range(anzahl):
        p = gps + 2 + 12 * k
        typ, menge = zahl(p + 2, 2), zahl(p + 4, 4)
        laenge = GROESSE.get(typ, 1) * max(menge, 0)
        if laenge > 4:
            stelle = zahl(p + 8, 4)
            if 0 <= stelle and stelle + laenge <= len(tiff):
                segment[basis + stelle:basis + stelle + laenge] = bytes(laenge)
    ende = min(gps + 2 + 12 * anzahl + 4, len(tiff))
    segment[basis + gps:basis + ende] = bytes(ende - gps)  # Anzahl 0, Einträge weg, kein Folgeverzeichnis
    return True


def ohne_standort(daten):
    """JPEG ohne Aufnahmeort: GPS im EXIF genullt, XMP (kann den Ort ebenfalls enthalten) weggelassen.
    Gibt (Bytes, ob etwas entfernt wurde) zurück. Keine JPEG-Datei: unverändert."""
    if daten[:2] != b"\xff\xd8":
        return daten, False
    teile, i, entfernt = [daten[:2]], 2, False
    while i + 4 <= len(daten):
        if daten[i] != 0xFF:  # Fremdbytes zwischen Blöcken: überspringen wie ein JPEG-Leser, nicht aufhören
            weiter = daten.find(b"\xff", i)
            if weiter < 0:
                break
            i = weiter
            continue
        marker = daten[i + 1]
        if marker == 0xFF:
            teile.append(daten[i:i + 1])
            i += 1
            continue
        if marker in (0xD9, 0xDA) or 0xD0 <= marker <= 0xD7 or marker == 0x01:
            break  # ab hier Bilddaten - Metadaten stehen nur davor
        laenge = int.from_bytes(daten[i + 2:i + 4], "big")
        if laenge < 2 or i + 2 + laenge > len(daten):
            break
        segment = daten[i:i + 2 + laenge]
        if marker == 0xE1 and segment[4:].startswith(XMP):
            entfernt = True
        elif marker == 0xE1 and segment[4:10] == b"Exif\x00\x00":
            neu = bytearray(segment)
            if _gps_nullen(neu):
                segment, entfernt = bytes(neu), True
            teile.append(segment)
        else:
            teile.append(segment)
        i += 2 + laenge
    rest = daten[i:]
    ende = rest.find(b"\xff\xd9")  # im Bilddatenstrom kommt FF D9 nur als Bildende vor
    if ende >= 0 and len(rest) > ende + 2:
        rest, entfernt = rest[:ende + 2], True  # angehängte Zweitbilder (MPF, HDR-Gainmap) tragen eigene Metadaten
    teile.append(rest)
    return b"".join(teile), entfernt


PNG_KOPF = b"\x89PNG\r\n\x1a\n"
PNG_WEG = (b"eXIf", b"iTXt", b"tEXt", b"zTXt", b"tIME")  # Metadaten (EXIF, XMP, Texte) - für die Anzeige unnötig


def png_ohne_metadaten(daten):
    """PNG ohne EXIF/XMP/Text-Blöcke. Gibt (Bytes, ob etwas entfernt wurde) zurück; kaputte Dateien: (None, False)."""
    if not daten.startswith(PNG_KOPF):
        return daten, False
    teile, i, entfernt = [PNG_KOPF], len(PNG_KOPF), False
    while i + 12 <= len(daten):
        laenge = int.from_bytes(daten[i:i + 4], "big")
        typ = daten[i + 4:i + 8]
        ende = i + 12 + laenge
        if ende > len(daten):
            return None, False
        if typ in PNG_WEG:
            entfernt = True
        else:
            teile.append(daten[i:ende])
        i = ende
        if typ == b"IEND":
            break
    return b"".join(teile), entfernt


def _masse(programm, pfad):
    """(Breite, Höhe) laut sips - oder None."""
    try:
        lauf = subprocess.run([programm, "-g", "pixelWidth", "-g", "pixelHeight", pfad],  # noqa: S603
                              capture_output=True, timeout=30)
    except (OSError, subprocess.SubprocessError):
        return None
    text = lauf.stdout.decode("utf-8", "replace")
    breite, hoehe = re.search(r"pixelWidth:\s*(\d+)", text), re.search(r"pixelHeight:\s*(\d+)", text)
    return (int(breite.group(1)), int(hoehe.group(1))) if breite and hoehe else None


def bild_daten(pfad, endung):
    """(MIME-Typ, Bytes, Ort entfernt?) zum Einbetten - über sips umgewandelt, sonst direkt. Wirft PraesentationFehler."""
    if os.path.getsize(pfad) > MAX_BILD_QUELLE:
        raise PraesentationFehler("zu groß")
    programm = _sips()
    mime, roh = None, None
    if programm and endung in UMWANDELBAR:
        masse = _masse(programm, pfad)
        verkleinern = ["-Z", str(MAX_KANTE)] if not masse or max(masse) > MAX_KANTE else []  # sips vergrößert sonst
        with tempfile.TemporaryDirectory(prefix="jarvis_bild_") as ordner:
            ziel = os.path.join(ordner, "bild.jpg")
            try:
                lauf = subprocess.run([programm, "-s", "format", "jpeg", "-s", "formatOptions", "82"] + verkleinern +  # noqa: S603
                                      [pfad, "--out", ziel], capture_output=True, timeout=60)
            except (OSError, subprocess.SubprocessError):
                lauf = None
            # sips meldet nicht jeden Fehler über den Rückgabewert: es zählt eine lesbare, nicht leere Datei
            if lauf is not None and lauf.returncode == 0 and os.path.isfile(ziel) and os.path.getsize(ziel) > 0:
                with open(ziel, "rb") as f:
                    mime, roh = "image/jpeg", f.read()
    if roh is None and endung in DIREKT and os.path.getsize(pfad) <= MAX_BILD_DIREKT:
        with open(pfad, "rb") as f:
            mime, roh = BILDARTEN[endung], f.read()
    if roh is None:
        if endung in DIREKT:
            raise PraesentationFehler("zu groß zum direkten Einbetten (ohne sips nur bis 4 MB)")
        raise PraesentationFehler("%s lässt sich nur auf dem Mac umwandeln (sips fehlt)" % endung.upper())
    entfernt = False
    if mime == "image/jpeg":
        roh, entfernt = ohne_standort(roh)
    elif mime == "image/png":
        roh, entfernt = png_ohne_metadaten(roh)
        if roh is None:
            raise PraesentationFehler("die PNG-Datei ist beschädigt")
    return mime, roh, entfernt


# ---------------------------------------------------------------- Bauen ---

STIL = """
:root { --akzent: %(akzent)s; --text: #1d2733; --leise: #5d6b7a; --grund: #ffffff; --flaeche: #f3f5f8; }
* { box-sizing: border-box; }
html, body { margin: 0; height: 100%%; background: #0e1116; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; }
.buehne { position: fixed; inset: 0; display: flex; align-items: center; justify-content: center; }
.folie { display: none; width: min(100vw, 177.78vh); height: min(56.25vw, 100vh); background: var(--grund); color: var(--text);
         padding: 5%% 6%% 6%%; position: relative; overflow: hidden; flex-direction: column; }
.folie.aktiv { display: flex; }
.folie h1 { font-size: clamp(28px, 5.4vmin, 64px); margin: 0 0 2%%; line-height: 1.1; }
.folie h2 { font-size: clamp(22px, 4.2vmin, 48px); margin: 0 0 3%%; padding-bottom: 1.2%%; border-bottom: 4px solid var(--akzent); line-height: 1.15; }
.folie ul { margin: 0; padding-left: 1.2em; font-size: clamp(16px, 3vmin, 34px); line-height: 1.45; }
.folie li { margin-bottom: 0.5em; }
.folie li::marker { color: var(--akzent); }
.folie p { font-size: clamp(15px, 2.7vmin, 30px); line-height: 1.45; margin: 0 0 0.7em; color: var(--text); }
.titelfolie { justify-content: center; background: linear-gradient(135deg, var(--grund) 60%%, var(--flaeche)); }
.titelfolie .linie { width: 18%%; height: 8px; background: var(--akzent); margin-bottom: 4%%; border-radius: 4px; }
.titelfolie .unter { font-size: clamp(18px, 3.2vmin, 36px); color: var(--leise); margin: 0; }
.bilder { display: flex; gap: 3%%; flex: 1; min-height: 0; margin-top: 2%%; }
.bilder figure { margin: 0; flex: 1; display: flex; flex-direction: column; min-width: 0; min-height: 0; }
.bilder img { width: 100%%; height: 100%%; object-fit: contain; min-height: 0; flex: 1; background: var(--flaeche); border-radius: 8px; }
.bilder figcaption { text-align: center; color: var(--leise); font-size: clamp(13px, 2.2vmin, 24px); margin-top: 1%%; font-weight: 600; }
.fuss { position: absolute; left: 6%%; right: 6%%; bottom: 2.4%%; display: flex; justify-content: space-between;
        color: var(--leise); font-size: clamp(11px, 1.8vmin, 18px); }
.knopf { position: fixed; top: 10px; right: 10px; background: rgba(29,39,51,0.6); color: #fff; border: 0; border-radius: 8px;
         padding: 7px 11px; font-size: 13px; cursor: pointer; opacity: 0.35; transition: opacity .2s; z-index: 2; }
.knopf:hover, .knopf:focus { opacity: 1; }
:fullscreen .knopf { display: none; }
@media print {
  @page { size: landscape; margin: 0; }
  html, body { background: #fff; height: auto; }
  .buehne { position: static; display: block; }
  .folie { display: flex !important; width: 100vw; height: 100vh; page-break-after: always; break-after: page; }
  .knopf { display: none; }
}
"""

SKRIPT = """
(function () {
  var folien = Array.prototype.slice.call(document.querySelectorAll(".folie"));
  var nr = Math.min(Math.max(parseInt((location.hash || "#1").slice(1), 10) || 1, 1), folien.length) - 1;
  function zeigen(i) {
    nr = Math.min(Math.max(i, 0), folien.length - 1);
    folien.forEach(function (f, k) { f.classList.toggle("aktiv", k === nr); });
    history.replaceState(null, "", "#" + (nr + 1));
  }
  document.addEventListener("keydown", function (e) {
    if (["ArrowRight", "ArrowDown", "PageDown", " ", "Enter"].indexOf(e.key) >= 0) { zeigen(nr + 1); e.preventDefault(); }
    else if (["ArrowLeft", "ArrowUp", "PageUp", "Backspace"].indexOf(e.key) >= 0) { zeigen(nr - 1); e.preventDefault(); }
    else if (e.key === "Home") { zeigen(0); } else if (e.key === "End") { zeigen(folien.length - 1); }
    else if (e.key === "f" || e.key === "F") { vollbild(); }
  });
  document.querySelector(".buehne").addEventListener("click", function (e) {
    zeigen(e.clientX > window.innerWidth / 2 ? nr + 1 : nr - 1);
  });
  var start = null;
  document.addEventListener("touchstart", function (e) { start = e.touches[0].clientX; }, { passive: true });
  document.addEventListener("touchend", function (e) {
    if (start === null) return;
    var weg = e.changedTouches[0].clientX - start;
    if (Math.abs(weg) > 40) zeigen(weg < 0 ? nr + 1 : nr - 1);
    start = null;
  }, { passive: true });
  function vollbild() {
    var el = document.documentElement;
    if (!document.fullscreenElement && el.requestFullscreen) el.requestFullscreen();
    else if (document.exitFullscreen) document.exitFullscreen();
  }
  document.querySelector(".knopf").addEventListener("click", function (e) { e.stopPropagation(); vollbild(); });
  window.addEventListener("hashchange", function () {
    var ziel = parseInt((location.hash || "#1").slice(1), 10);
    if (ziel && ziel - 1 !== nr) zeigen(ziel - 1);
  });
  zeigen(nr);
})();
"""


def bauen(konfig, inhalt, titel="", untertitel="", fusszeile="", akzent="#c8561b"):
    """Baut die HTML-Datei. Gibt (HTML, Folienzahl, eingebettete Bilder, Hinweise) zurück."""
    daten = lesen(inhalt, titel)
    if untertitel:
        daten["untertitel"] = untertitel.strip()
    if not FARBE.match(akzent or ""):
        raise PraesentationFehler("Die Farbe bitte als #RRGGBB, z. B. #c8561b.")
    e = html.escape
    hinweise, bilder_gesamt, groesse, ohne_ort = [], 0, 0, 0
    folien_html = []
    gesamt = len(daten["folien"]) + 1
    def fuss(nummer):  # einmal formatieren: ein "%" in der Fußzeile ("100% zuverlässig") darf nichts kaputt machen
        return '<div class="fuss"><span>%s</span><span>%d / %d</span></div>' % (e(fusszeile), nummer, gesamt)
    folien_html.append('<section class="folie titelfolie"><div class="linie"></div><h1>%s</h1>%s%s</section>' % (
        e(daten["titel"]), '<p class="unter">%s</p>' % e(daten["untertitel"]) if daten["untertitel"] else "", fuss(1)))
    for nummer, folie in enumerate(daten["folien"], start=2):
        teile = ["<h2>%s</h2>" % e(folie["titel"])]
        teile += ["<p>%s</p>" % e(a) for a in folie["absaetze"]]
        if folie["punkte"]:
            teile.append("<ul>%s</ul>" % "".join("<li>%s</li>" % e(p) for p in folie["punkte"]))
        figuren = []
        for angabe, beschriftung in folie["bilder"][:2]:
            if bilder_gesamt >= MAX_BILDER:
                hinweise.append("Mehr als %d Bilder: %s weggelassen." % (MAX_BILDER, angabe))
                continue
            try:
                pfad, endung = bild_pfad(konfig, angabe)
                mime, roh, ort_entfernt = bild_daten(pfad, endung)
            except PraesentationFehler as fehler:
                hinweise.append("Bild %s weggelassen: %s" % (angabe, str(fehler).replace("Bild %r: " % angabe, "")))
                continue
            if groesse + len(roh) > MAX_GESAMT:
                hinweise.append("Bild %s weggelassen: die Datei würde zu groß." % angabe)
                continue
            groesse += len(roh)
            bilder_gesamt += 1
            ohne_ort += ort_entfernt
            figuren.append('<figure><img alt="%s" src="data:%s;base64,%s">%s</figure>' % (
                e(beschriftung or os.path.basename(pfad)), mime, base64.b64encode(roh).decode("ascii"),
                "<figcaption>%s</figcaption>" % e(beschriftung) if beschriftung else ""))
        if len(folie["bilder"]) > 2:
            hinweise.append("Folie „%s“: höchstens 2 Bilder pro Folie, der Rest ist weggelassen." % folie["titel"])
        if figuren:
            teile.append('<div class="bilder">%s</div>' % "".join(figuren))
        folien_html.append('<section class="folie">%s%s</section>' % ("".join(teile), fuss(nummer)))
    if ohne_ort:
        hinweise.append("Aus %d Bild(ern) sind Aufnahmeort (GPS) und andere Metadaten entfernt - die Präsentation "
                        "verrät nicht, wo die Fotos aufgenommen wurden." % ohne_ort)
    seite = ("<!doctype html>\n<html lang=\"de\"><head><meta charset=\"utf-8\">"
             "<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">"
             "<title>%s</title><style>%s</style></head><body>"
             "<div class=\"buehne\">%s</div>"
             "<button class=\"knopf\" type=\"button\" title=\"Vollbild (Taste F)\">Vollbild</button>"
             "<script>%s</script></body></html>\n") % (e(daten["titel"]), STIL % {"akzent": akzent}, "".join(folien_html), SKRIPT)
    return seite, gesamt, bilder_gesamt, hinweise


def dateiname(titel):
    """Aus dem Titel ein sicherer Dateiname: "Firmenvorstellung Müller" -> "Firmenvorstellung-Mueller"."""
    ersatz = {"ä": "ae", "ö": "oe", "ü": "ue", "Ä": "Ae", "Ö": "Oe", "Ü": "Ue", "ß": "ss"}
    name = "".join(ersatz.get(z, z) for z in titel)
    name = re.sub(r"[^A-Za-z0-9_-]+", "-", name).strip("-")[:60]
    return name or "Praesentation"
