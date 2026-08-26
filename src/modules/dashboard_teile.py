#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Bausteine für die Oberflächen - Farben, Zahlenformate und SVG-Grafiken.

Hier liegt alles, was Command Center und Sales-Ansicht gemeinsam benutzen.
Die Grafiken sind handgeschriebenes SVG: keine Fremdbibliothek, kein
Nachladen aus dem Netz. Die Seiten funktionieren dadurch auch offline und
öffnen sich mit einem Doppelklick, ohne dass ein Server läuft.
"""

import html
import math

# Farben des Cockpits
FARBE_HINTERGRUND = "#08090B"
FARBE_PANEL = "#0F1113"
FARBE_KACHEL = "#121517"
FARBE_RAND = "#1C1F23"
FARBE_AKZENT = "#E8622C"
FARBE_TEXT = "#E6E8EA"
FARBE_GRAU = "#6E767D"
FARBE_GUT = "#4CC38A"
FARBE_WARNUNG = "#E8A33C"
FARBE_SCHLECHT = "#E5484D"

WOCHENTAGE = ["Montag", "Dienstag", "Mittwoch", "Donnerstag", "Freitag",
              "Samstag", "Sonntag"]

# Ein einziges Stylesheet für beide Seiten. Bewusst als schlichter Text und
# nicht als Formatvorlage - sonst müsste jedes Prozentzeichen in CSS verdoppelt
# werden, und genau das wird beim Bearbeiten irgendwann vergessen.
CSS = """
* { box-sizing: border-box; margin: 0; padding: 0; }
body {
  background: #08090B; color: #E6E8EA; min-height: 100vh; padding-bottom: 48px;
  font-family: -apple-system, BlinkMacSystemFont, "Helvetica Neue", Arial, sans-serif;
  -webkit-font-smoothing: antialiased;
}
a { color: #E8622C; text-decoration: none; }
a:hover { text-decoration: underline; }

.ticker {
  background: linear-gradient(90deg, rgba(232,98,44,.16), rgba(232,98,44,.02) 60%, transparent);
  border-bottom: 1px solid rgba(232,98,44,.34);
  padding: 9px 20px; font-size: 11px; letter-spacing: .1em; text-transform: uppercase;
  display: flex; gap: 26px; flex-wrap: wrap; align-items: center; color: #8A9096;
}
.ticker b { color: #E8622C; text-shadow: 0 0 12px rgba(232,98,44,.55); font-weight: 600; }
.ticker .rot { color: #E5484D; text-shadow: 0 0 12px rgba(229,72,77,.5); }

header { padding: 26px 20px 6px; display: flex; justify-content: space-between;
         align-items: flex-end; flex-wrap: wrap; gap: 12px; }
header h1 { font-size: 15px; font-weight: 600; letter-spacing: .22em;
            text-transform: uppercase; color: #E6E8EA; }
header h1 span { color: #E8622C; }
header p { color: #6E767D; font-size: 13px; margin-top: 5px; }
nav { display: flex; gap: 8px; }
nav a { font-size: 11px; letter-spacing: .12em; text-transform: uppercase;
        border: 1px solid #1C1F23; border-radius: 6px; padding: 7px 13px;
        color: #8A9096; }
nav a.aktiv { border-color: rgba(232,98,44,.5); color: #E8622C;
              background: rgba(232,98,44,.07); }
nav a:hover { text-decoration: none; border-color: rgba(232,98,44,.5); color: #E8622C; }

.raster { display: grid; gap: 13px; padding: 14px 20px;
          grid-template-columns: repeat(12, 1fr); align-items: start; }
.panel { background: #0F1113; border: 1px solid #1C1F23; border-radius: 10px;
         padding: 15px 17px; grid-column: span 4; min-width: 0; }
.panel.breit { grid-column: span 8; }
.panel.voll { grid-column: span 12; }
.panel.schmal { grid-column: span 3; }
@media (max-width: 1100px) { .panel, .panel.breit, .panel.schmal { grid-column: span 6; } }
@media (max-width: 700px)  { .panel, .panel.breit, .panel.schmal, .panel.voll { grid-column: span 12; } }

.panel h2 { font-size: 10px; text-transform: uppercase; letter-spacing: .16em;
            color: #6E767D; margin-bottom: 12px; font-weight: 600;
            display: flex; justify-content: space-between; align-items: center; }
.panel h2 em { font-style: normal; color: #3E454B; letter-spacing: .08em; }

.kacheln { display: grid; grid-template-columns: repeat(auto-fit, minmax(118px, 1fr));
           gap: 9px; }
.kachel { background: #121517; border: 1px solid #1C1F23; border-radius: 8px;
          padding: 11px 13px; }
.kachel .wert { font-size: 21px; font-weight: 600; color: #F2F4F6;
                font-variant-numeric: tabular-nums; letter-spacing: -.01em; }
.kachel .wert.akzent { color: #E8622C; text-shadow: 0 0 16px rgba(232,98,44,.4); }
.kachel .wert.gut { color: #4CC38A; }
.kachel .wert.warn { color: #E8A33C; }
.kachel .wert.schlecht { color: #E5484D; }
.kachel .name { font-size: 9.5px; color: #6E767D; text-transform: uppercase;
                letter-spacing: .1em; margin-top: 5px; }

ul { list-style: none; }
li { padding: 7px 0; border-bottom: 1px solid #17191C; font-size: 13px; line-height: 1.5; }
li:last-child { border-bottom: none; }
.zeit { color: #E8622C; font-variant-numeric: tabular-nums; margin-right: 8px;
        font-size: 12px; }
.grau { color: #6E767D; font-size: 12px; }
.warnung { color: #E5484D; }
.achtung { color: #E8A33C; }
.ok { color: #4CC38A; }
.leer { color: #3E454B; font-style: italic; font-size: 12.5px; padding: 6px 0; }

.status { display: inline-block; width: 7px; height: 7px; border-radius: 50%;
          margin-right: 8px; vertical-align: middle; }
.an { background: #4CC38A; box-shadow: 0 0 8px #4CC38A; }
.aus { background: #2A3036; }

.balkenzeile { margin-bottom: 9px; }
.balkenkopf { display: flex; justify-content: space-between; font-size: 12px;
              margin-bottom: 4px; }
.balkenkopf span:last-child { color: #6E767D; font-variant-numeric: tabular-nums; }
.balken { height: 5px; background: #17191C; border-radius: 3px; overflow: hidden; }
.balken i { display: block; height: 100%; border-radius: 3px; }

.ringfeld { display: flex; align-items: center; gap: 16px; flex-wrap: wrap; }
.ringtext { flex: 1; min-width: 130px; }
.ringtext .gross { font-size: 26px; font-weight: 600; color: #F2F4F6;
                   font-variant-numeric: tabular-nums; }
.ringtext .klein { font-size: 12px; color: #6E767D; line-height: 1.5; margin-top: 5px; }

.verlauf { display: flex; align-items: flex-end; gap: 14px; flex-wrap: wrap; }
.verlaufblock { flex: 1; min-width: 150px; }
.verlaufkopf { font-size: 10px; text-transform: uppercase; letter-spacing: .1em;
               color: #6E767D; margin-bottom: 6px; display: flex;
               justify-content: space-between; }
.verlaufkopf b { color: #E6E8EA; font-variant-numeric: tabular-nums; }

footer { padding: 18px 20px; color: #3E454B; font-size: 11.5px; line-height: 1.7; }
"""


def sicher(text) -> str:
    """Macht Text HTML-sicher - ein Kundenname darf die Seite nicht aufbrechen."""
    return html.escape(str(text if text is not None else ""))


def euro(betrag) -> str:
    """Formatiert einen Betrag deutsch: 1.234,56 Euro-Zeichen."""
    try:
        betrag = float(betrag)
    except (TypeError, ValueError):
        betrag = 0.0
    text = "{:,.2f}".format(betrag).replace(",", "#").replace(".", ",").replace("#", ".")
    return text + " €"


def euro_kurz(betrag) -> str:
    """Kurzform für enge Kacheln: 71,3k statt 71.300,00."""
    try:
        betrag = float(betrag)
    except (TypeError, ValueError):
        betrag = 0.0
    if abs(betrag) >= 10000:
        return ("%.1fk" % (betrag / 1000.0)).replace(".", ",") + " €"
    return euro(betrag)


def prozent(teil, ganzes) -> float:
    """Anteil in Prozent, ohne Division durch null."""
    try:
        ganzes = float(ganzes)
        if ganzes <= 0:
            return 0.0
        return max(0.0, min(100.0, 100.0 * float(teil) / ganzes))
    except (TypeError, ValueError):
        return 0.0


def ampelfarbe(wert: float, gut_ab: float = 70, mittel_ab: float = 40) -> str:
    """Grün, Gelb oder Rot - je nachdem, wie gut der Wert ist."""
    if wert >= gut_ab:
        return FARBE_GUT
    if wert >= mittel_ab:
        return FARBE_WARNUNG
    return FARBE_SCHLECHT


# ---------------------------------------------------------------------------
# Grafiken
# ---------------------------------------------------------------------------

def ring(anteil, beschriftung: str = "", groesse: int = 132,
         farbe: str = FARBE_AKZENT, dicke: int = 9) -> str:
    """Runde Fortschrittsanzeige als SVG.

    ``anteil`` ist ein Prozentwert. ``None`` heißt: es gibt noch keine Daten -
    dann wird ein leerer Ring mit einem Strich gezeigt, keine erfundene Null.
    """
    radius = (groesse / 2.0) - dicke - 3
    umfang = 2 * math.pi * radius
    mitte = groesse / 2.0
    hat_daten = anteil is not None
    wert = max(0.0, min(100.0, float(anteil))) if hat_daten else 0.0
    gefuellt = umfang * wert / 100.0
    anzeige = ("%d%%" % round(wert)) if hat_daten else "–"

    return "".join([
        '<svg viewBox="0 0 %d %d" width="%d" height="%d" role="img">' % (
            groesse, groesse, groesse, groesse),
        '<defs><filter id="gl%d" x="-50%%" y="-50%%" width="200%%" height="200%%">'
        '<feGaussianBlur stdDeviation="3.5" result="b"/>'
        '<feMerge><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge>'
        '</filter></defs>' % groesse,
        '<circle cx="%.1f" cy="%.1f" r="%.1f" fill="none" stroke="%s" '
        'stroke-width="%d"/>' % (mitte, mitte, radius, FARBE_RAND, dicke),
        ('<circle cx="%.1f" cy="%.1f" r="%.1f" fill="none" stroke="%s" '
         'stroke-width="%d" stroke-linecap="round" stroke-dasharray="%.2f %.2f" '
         'transform="rotate(-90 %.1f %.1f)" filter="url(#gl%d)"/>'
         % (mitte, mitte, radius, farbe, dicke, gefuellt, umfang - gefuellt,
            mitte, mitte, groesse)) if hat_daten and wert > 0 else "",
        '<text x="%.1f" y="%.1f" text-anchor="middle" fill="%s" '
        'font-size="%d" font-weight="600" font-family="inherit">%s</text>'
        % (mitte, mitte + 3, FARBE_TEXT if hat_daten else FARBE_GRAU,
           int(groesse * 0.23), anzeige),
        ('<text x="%.1f" y="%.1f" text-anchor="middle" fill="%s" font-size="%d" '
         'letter-spacing="1.4" font-family="inherit">%s</text>'
         % (mitte, mitte + int(groesse * 0.19), FARBE_GRAU, int(groesse * 0.085),
            sicher(beschriftung.upper()))) if beschriftung else "",
        '</svg>'])


def sparkline(werte: list, breite: int = 240, hoehe: int = 44,
              farbe: str = FARBE_AKZENT, fuellen: bool = True) -> str:
    """Kleiner Verlaufsgraph als SVG.

    Weniger als zwei Werte ergeben keinen Verlauf - dann kommt ein Hinweis
    statt einer Linie, die etwas vortäuscht.
    """
    zahlen = []
    for wert in werte or []:
        try:
            zahlen.append(float(wert))
        except (TypeError, ValueError):
            zahlen.append(0.0)
    if len(zahlen) < 2:
        return ('<div class="leer" style="height:%dpx;display:flex;'
                'align-items:center">noch kein Verlauf</div>' % hoehe)

    kleinster, groesster = min(zahlen), max(zahlen)
    spanne = (groesster - kleinster) or 1.0
    rand = 3
    schritt = breite / float(len(zahlen) - 1)
    punkte = []
    for index, zahl in enumerate(zahlen):
        x = index * schritt
        y = hoehe - rand - ((zahl - kleinster) / spanne) * (hoehe - 2 * rand)
        punkte.append("%.1f,%.1f" % (x, y))

    kennung = abs(hash((tuple(zahlen[:6]), farbe, breite))) % 100000
    flaeche = ""
    if fuellen:
        flaeche = ('<polygon points="0,%d %s %d,%d" fill="url(#fl%d)"/>'
                   % (hoehe, " ".join(punkte), breite, hoehe, kennung))
    return "".join([
        '<svg viewBox="0 0 %d %d" width="100%%" height="%d" '
        'preserveAspectRatio="none" role="img">' % (breite, hoehe, hoehe),
        '<defs><linearGradient id="fl%d" x1="0" y1="0" x2="0" y2="1">' % kennung,
        '<stop offset="0%%" stop-color="%s" stop-opacity=".30"/>' % farbe,
        '<stop offset="100%%" stop-color="%s" stop-opacity="0"/>' % farbe,
        '</linearGradient></defs>',
        flaeche,
        '<polyline points="%s" fill="none" stroke="%s" stroke-width="1.6" '
        'stroke-linejoin="round" stroke-linecap="round" '
        'vector-effect="non-scaling-stroke"/>' % (" ".join(punkte), farbe),
        '</svg>'])


def saeulen(werte: list, beschriftungen: list = None, hoehe: int = 60,
            farbe: str = FARBE_AKZENT) -> str:
    """Balkenreihe für Monatsvergleiche. Negative Werte werden rot."""
    zahlen = []
    for wert in werte or []:
        try:
            zahlen.append(float(wert))
        except (TypeError, ValueError):
            zahlen.append(0.0)
    if not zahlen:
        return '<div class="leer">noch keine Monate erfasst</div>'
    groesster = max([abs(z) for z in zahlen]) or 1.0
    stuecke = []
    for index, zahl in enumerate(zahlen):
        anteil = abs(zahl) / groesster
        # Ein Monat ohne Buchung bekommt einen matten Strich, keinen farbigen
        # Balken - sonst sieht die Nulllinie aus wie ein kleiner Umsatz.
        farbe_balken = (FARBE_RAND if zahl == 0
                        else (farbe if zahl > 0 else FARBE_SCHLECHT))
        beschriftung = ""
        if beschriftungen and index < len(beschriftungen):
            beschriftung = ('<div style="font-size:9px;color:%s;text-align:center;'
                            'margin-top:4px">%s</div>'
                            % (FARBE_GRAU, sicher(beschriftungen[index])))
        stuecke.append(
            '<div style="flex:1;display:flex;flex-direction:column;'
            'justify-content:flex-end;align-items:center">'
            '<div style="width:100%%;height:%dpx;display:flex;align-items:flex-end">'
            '<div title="%s" style="width:100%%;height:%.1f%%;background:%s;'
            'border-radius:2px 2px 0 0;min-height:2px"></div></div>%s</div>'
            % (hoehe, sicher(euro(zahl)), max(2.0, anteil * 100),
               farbe_balken, beschriftung))
    return ('<div style="display:flex;gap:4px;align-items:flex-end">%s</div>'
            % "".join(stuecke))


def balken(name: str, wert: float, maximum: float, zusatz: str = "",
           farbe: str = FARBE_AKZENT) -> str:
    """Waagrechter Fortschrittsbalken mit Beschriftung."""
    anteil = prozent(wert, maximum)
    return ('<div class="balkenzeile"><div class="balkenkopf">'
            '<span>%s</span><span>%s</span></div>'
            '<div class="balken"><i style="width:%.1f%%;background:%s"></i></div></div>'
            % (sicher(name), sicher(zusatz), anteil, farbe))


def seite_bauen(titel: str, ticker: str, kopf_links: str, kopf_rechts: str,
                inhalt: str, fusszeile: str) -> str:
    """Setzt eine vollständige HTML-Seite zusammen."""
    return "".join([
        '<!DOCTYPE html>\n<html lang="de">\n<head>\n',
        '<meta charset="utf-8">\n',
        '<meta name="viewport" content="width=device-width, initial-scale=1">\n',
        '<meta http-equiv="refresh" content="60">\n',
        '<title>%s</title>\n<style>%s</style>\n</head>\n<body>\n' % (sicher(titel), CSS),
        '<div class="ticker">%s</div>\n' % ticker,
        '<header>%s%s</header>\n' % (kopf_links, kopf_rechts),
        inhalt,
        '<footer>%s</footer>\n</body>\n</html>\n' % fusszeile])
