#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Baut die Landmaske für den Globus der Zentrale - einmal, dann eingecheckt.

Aufruf::

    python3 tools/landmaske_bauen.py                 # lädt land-50m.json von jsDelivr
    python3 tools/landmaske_bauen.py land-110m.json  # oder eine schon geladene Datei

Liest die Landflächen von Natural Earth (1:50 Mio., gemeinfrei) im
TopoJSON-Format des Pakets ``world-atlas@2`` und rastert sie auf ein Gitter von
0,25 Grad: 1440 Spalten von West nach Ost, 720 Zeilen von Nord nach Süd. Jede
Zelle ist Land oder Wasser, je nachdem, ob ihr Mittelpunkt in einer Landfläche
liegt (gerade-ungerade-Regel über alle Ringe, so werden Binnenmeere zu Löchern).

Geschrieben wird ``src/modules/weltkarte.py``: die Maske als Lauflängen. Je
Zeile abwechselnd Wasser- und Landlängen zur Basis 36, mit Komma getrennt, und
immer mit Wasser beginnend; die Zeilen mit Semikolon verbunden. Die Seite der
Zentrale entpackt das einmal und baut daraus ihre Punktraster.

Warum 1:50 Mio. statt 1:110 Mio.: Der Globus zoomt bis auf das Sechsfache. Dort
sind die groben Umrisse von 1:110 Mio. eckig, Inseln wie Mallorca, Rhodos oder
die dänischen Inseln fehlen. Das Raster von 0,25 Grad bleibt gleich, die Datei
wächst nur von etwa 26 auf 32 KB.

Nicht in der Bauliste - dieses Werkzeug gehört nicht zu Jarvis, nur sein
Ergebnis. Nur Standardbibliothek.
"""

import json
import math
import os
import sys
import urllib.request

QUELLE_URL = "https://cdn.jsdelivr.net/npm/world-atlas@2/land-50m.json"
# Wie die Quelle in weltkarte.py heißt - je nach Auflösung der gelesenen Datei.
QUELLE_NAMEN = {"50m": "Natural Earth 50m (world-atlas@2 land-50m.json, gemeinfrei)",
                "110m": "Natural Earth 110m (world-atlas@2 land-110m.json, gemeinfrei)",
                "10m": "Natural Earth 10m (world-atlas@2 land-10m.json, gemeinfrei)"}
BREITE = 1440
HOEHE = 720
SCHRITT = 360.0 / BREITE
WURZEL = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ZIEL = os.path.join(WURZEL, "src", "modules", "weltkarte.py")


def laden(quelle: str) -> dict:
    """Liest die TopoJSON-Datei - aus dem Netz oder von der Platte."""
    if quelle.startswith("https://"):
        anfrage = urllib.request.Request(quelle, headers={"User-Agent": "Jarvis-Landmaske/1.0"})
        with urllib.request.urlopen(anfrage, timeout=60) as antwort:
            return json.loads(antwort.read().decode("utf-8"))
    with open(quelle, encoding="utf-8") as datei:
        return json.load(datei)


def boegen_entpacken(topo: dict) -> list:
    """Die Bögen als Listen von (Länge, Breite) - Deltas aufaddiert, Raster umgerechnet."""
    umrechnung = topo.get("transform")
    boegen = []
    for bogen in topo["arcs"]:
        punkte = []
        if umrechnung:
            sx, sy = umrechnung["scale"]
            tx, ty = umrechnung["translate"]
            x = y = 0
            for dx, dy in (p[:2] for p in bogen):
                x += dx
                y += dy
                punkte.append((x * sx + tx, y * sy + ty))
        else:
            punkte = [(float(p[0]), float(p[1])) for p in bogen]
        boegen.append(punkte)
    return boegen


def ring_bauen(indizes: list, boegen: list) -> list:
    """Setzt einen Ring aus Bögen zusammen. ``~i`` heißt: Bogen i rückwärts."""
    ring = []
    for index in indizes:
        if index < 0:
            teil = list(reversed(boegen[~index]))
        else:
            teil = list(boegen[index])
        # Aufeinanderfolgende Bögen teilen sich ihren Endpunkt - nur einmal nehmen.
        if ring and teil:
            teil = teil[1:]
        ring.extend(teil)
    return ring


def ringe_sammeln(geometrie: dict, boegen: list) -> list:
    """Alle Ringe einer Geometrie (Polygon, MultiPolygon oder Sammlung)."""
    art = geometrie.get("type")
    if art == "GeometryCollection":
        ringe = []
        for teil in geometrie.get("geometries") or []:
            ringe.extend(ringe_sammeln(teil, boegen))
        return ringe
    if art == "Polygon":
        return [ring_bauen(r, boegen) for r in geometrie.get("arcs") or []]
    if art == "MultiPolygon":
        return [ring_bauen(r, boegen) for polygon in geometrie.get("arcs") or [] for r in polygon]
    return []


def ring_abwickeln(ring: list) -> list:
    """Macht die Längen eines Rings stetig - über die Datumsgrenze hinweg.

    Natural Earth schneidet an ±180 Grad, ``world-atlas`` aber nicht immer:
    Tschukotka, die Wrangelinsel und Fidschi springen von +179,9 auf -179,9.
    In der Ebene wäre das eine Kante quer über die ganze Karte - jede Zeile auf
    dieser Breite bekäme einen falschen Streifen. Abgewickelt läuft der Ring über
    180 hinaus weiter und wird erst beim Rastern zurückgefaltet.

    Ein Ring, der danach nicht mehr bei seiner Anfangslänge ankommt, umläuft einen
    Pol (die Antarktis). Er wird über den Pol geschlossen, sonst fehlte das Land
    südlich der letzten Küstenlinie.
    """
    if not ring:
        return []
    punkte = [ring[0]]
    versatz = 0.0
    for i in range(1, len(ring)):
        sprung = ring[i][0] - ring[i - 1][0]
        if sprung > 180:
            versatz -= 360.0
        elif sprung < -180:
            versatz += 360.0
        punkte.append((ring[i][0] + versatz, ring[i][1]))
    if abs(punkte[-1][0] - punkte[0][0]) > 180:
        pol = -90.0 if sum(p[1] for p in punkte) < 0 else 90.0
        punkte.append((punkte[-1][0], pol))
        punkte.append((punkte[0][0], pol))
    if punkte[0] != punkte[-1]:
        punkte.append(punkte[0])
    return punkte


def _zellen_umschalten(reihe: bytearray, von: float, bis: float):
    """Schaltet alle Zellen um, deren Mitte in [von, bis) liegt - auch über ±180 hinweg."""
    if bis - von >= 360.0:
        for j in range(BREITE):
            reihe[j] ^= 1
        return
    # In den Bereich ab -180 falten; was über +180 hinausragt, beginnt wieder bei -180.
    verschiebung = math.floor((von + 180.0) / 360.0) * 360.0
    von, bis = von - verschiebung, bis - verschiebung
    stuecke = [(von, min(bis, 180.0))]
    if bis > 180.0:
        stuecke.append((-180.0, bis - 360.0))
    for a, b in stuecke:
        # Zelle j hat ihre Mitte bei -180 + (j + 0.5) * SCHRITT.
        erste = max(0, int(math.ceil((a + 180.0) / SCHRITT - 0.5)))
        letzte = min(BREITE - 1, int(math.ceil((b + 180.0) / SCHRITT - 0.5)) - 1)
        for j in range(erste, letzte + 1):
            reihe[j] ^= 1


def rastern(ringe: list) -> list:
    """Gerade-ungerade-Regel an den Zellmitten, Ring für Ring umgeschaltet.

    Jeder Ring schaltet die Zellen um, die er einschließt. Ein Loch (Kaspisches
    Meer) ist ein eigener Ring und schaltet sein Wasser so wieder zurück.
    Gibt Zeilen aus 0/1 zurück.
    """
    # Kanten einmal vorbereiten: (y_min, y_max, ring, x1, y1, x2, y2)
    kanten = []
    for nummer, ring in enumerate(ringe):
        punkte = ring_abwickeln(ring)
        for i in range(len(punkte) - 1):
            (x1, y1), (x2, y2) = punkte[i], punkte[i + 1]
            if y1 != y2:
                kanten.append((min(y1, y2), max(y1, y2), nummer, x1, y1, x2, y2))
    kanten.sort()
    zeilen = []
    for zeile in range(HOEHE):
        breite = 90.0 - (zeile + 0.5) * SCHRITT
        schnitte = {}
        for y_min, y_max, nummer, x1, y1, x2, y2 in kanten:
            if y_min > breite:
                break
            if (y1 > breite) != (y2 > breite):
                schnitte.setdefault(nummer, []).append(
                    x1 + (breite - y1) * (x2 - x1) / (y2 - y1))
        reihe = bytearray(BREITE)
        for liste in schnitte.values():
            liste.sort()
            for k in range(0, len(liste) - 1, 2):
                _zellen_umschalten(reihe, liste[k], liste[k + 1])
        zeilen.append(list(reihe))
    return zeilen


def basis36(zahl: int) -> str:
    ziffern = "0123456789abcdefghijklmnopqrstuvwxyz"
    if zahl == 0:
        return "0"
    text = ""
    while zahl:
        zahl, rest = divmod(zahl, 36)
        text = ziffern[rest] + text
    return text


def lauflaengen(zeilen: list) -> str:
    """Jede Zeile: Wasser, Land, Wasser, ... als Längen zur Basis 36."""
    teile = []
    for reihe in zeilen:
        laengen, aktuell, anzahl = [], 0, 0
        for zelle in reihe:
            if zelle == aktuell:
                anzahl += 1
            else:
                laengen.append(anzahl)
                aktuell, anzahl = zelle, 1
        laengen.append(anzahl)
        teile.append(",".join(basis36(n) for n in laengen))
    return ";".join(teile)


MODUL_VORLAGE = '''#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Landmaske der Erde für den Globus der Zentrale.

Erzeugt von ``tools/landmaske_bauen.py`` - nicht von Hand ändern, sondern neu
bauen. Quelle: %(quelle)s.

Ein Raster von 0,25 Grad: %(breite)d Spalten von West nach Ost (Spalte j hat
ihre Mitte bei Länge -180 + (j + 0,5) * 0,25), %(hoehe)d Zeilen von Nord nach Süd
(Zeile i hat ihre Mitte bei Breite 90 - (i + 0,5) * 0,25). Je Zeile stehen die
Lauflängen zur Basis 36, mit Komma getrennt und immer mit Wasser beginnend; die
Zeilen sind mit Semikolon verbunden. Die Zentrale holt das über
``/api/weltkarte`` einmal ab und zeichnet daraus echte Küsten.

Die Karte zeigt, wo etwas liegt. Sie taugt nicht zur Navigation.
"""

LANDMASKE_BREITE = %(breite)d
LANDMASKE_HOEHE = %(hoehe)d
LANDMASKE_QUELLE = %(quelle_repr)s

LANDMASKE_RLE = (
%(rle_zeilen)s
)


def landmaske_dekodieren(rle: str) -> bytearray:
    """Entpackt die Lauflängen zu einer Maske: 1 Land, 0 Wasser, Zeile für Zeile.

    Ein leerer Text gibt eine leere Maske. Passt eine Zeile nicht zur Breite,
    ist die Maske kaputt - dann lieber ein Fehler als ein verschobener Globus.
    """
    maske = bytearray()
    if not rle:
        return maske
    zeilen = rle.split(";")
    if len(zeilen) != LANDMASKE_HOEHE:
        raise ValueError("Die Landmaske hat %%d statt %%d Zeilen." %% (len(zeilen), LANDMASKE_HOEHE))
    for nummer, zeile in enumerate(zeilen):
        land = 0
        laenge = 0
        for teil in zeile.split(","):
            anzahl = int(teil, 36)
            maske.extend(bytes([land]) * anzahl)
            laenge += anzahl
            land = 1 - land
        if laenge != LANDMASKE_BREITE:
            raise ValueError("Zeile %%d der Landmaske ist %%d statt %%d breit."
                             %% (nummer, laenge, LANDMASKE_BREITE))
    return maske
'''


def modul_schreiben(rle: str, quelle_name: str, ziel: str = ZIEL) -> int:
    """Schreibt weltkarte.py. Gibt die Größe in Bytes zurück."""
    stuecke = [rle[i:i + 92] for i in range(0, len(rle), 92)]
    rle_zeilen = "\n".join("    %s" % json.dumps(s) for s in stuecke) or '    ""'
    text = MODUL_VORLAGE % {"quelle": quelle_name, "quelle_repr": repr(quelle_name),
                            "breite": BREITE, "hoehe": HOEHE, "rle_zeilen": rle_zeilen}
    with open(ziel, "w", encoding="utf-8") as datei:
        datei.write(text)
    return len(text.encode("utf-8"))


def stichprobe(zeilen: list, breite: float, laenge: float) -> int:
    zeile = min(HOEHE - 1, max(0, int((90.0 - breite) / SCHRITT)))
    spalte = min(BREITE - 1, max(0, int((laenge + 180.0) / SCHRITT)))
    return zeilen[zeile][spalte]


def main(argumente: list) -> int:
    quelle = argumente[0] if argumente else QUELLE_URL
    print("Lese %s" % quelle)
    topo = laden(quelle)
    if topo.get("type") != "Topology" or "land" not in (topo.get("objects") or {}):
        print("Das ist keine TopoJSON-Datei mit 'land'.")
        return 1
    boegen = boegen_entpacken(topo)
    ringe = ringe_sammeln(topo["objects"]["land"], boegen)
    print("%d Bögen, %d Ringe" % (len(boegen), len(ringe)))
    zeilen = rastern(ringe)
    land = sum(sum(r) for r in zeilen)
    print("%d von %d Zellen sind Land (%.1f %%)" % (land, BREITE * HOEHE, 100.0 * land / (BREITE * HOEHE)))
    proben = {"Wien": (48.2, 16.37, 1), "Moskau": (55.76, 37.62, 1), "Atlantik": (40.0, -30.0, 0),
              "Pazifik": (0.0, -150.0, 0), "Sydney": (-33.9, 150.9, 1), "Kaspisches Meer": (42.0, 51.0, 0),
              # Die Datumsgrenze und die Pole - dort entstehen sonst falsche Streifen.
              "Nordmeer": (70.0, 0.0, 0), "Tschukotka": (66.0, 175.0, 1), "Beringmeer": (60.0, -175.0, 0),
              "Südpol": (-89.9, 0.0, 1), "Antarktis innen": (-86.0, 120.0, 1), "Nordpol": (89.9, 0.0, 0)}
    falsch = [name for name, (b, l, soll) in proben.items() if stichprobe(zeilen, b, l) != soll]
    if falsch:
        print("Stichproben falsch: %s" % ", ".join(falsch))
        return 1
    rle = lauflaengen(zeilen)
    name = next((n for k, n in QUELLE_NAMEN.items() if "land-%s" % k in quelle),
                "Natural Earth (%s, gemeinfrei)" % os.path.basename(quelle))
    groesse = modul_schreiben(rle, name)
    print("Geschrieben: %s (%d Bytes, Lauflängen %d Zeichen)" % (ZIEL, groesse, len(rle)))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
