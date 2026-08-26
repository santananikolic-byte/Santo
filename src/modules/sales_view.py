#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Sales-Analyse - erzeugt ``dashboard/sales.html``.

Eine Seite je Kundengespräch: Punktzahl, die fünf Einzelbewertungen als
Balken, Einwände, Stärken, Schwächen und der nächste Schritt. Links die Liste
aller Gespräche, rechts das ausgewählte.

Die Seite kommt ohne Server aus. Umgeschaltet wird mit ein paar Zeilen
JavaScript, die nur Sichtbarkeiten umschalten - alle Gespräche stecken schon
in der Datei. Damit funktioniert sie auch offline und per Doppelklick.

**Es wird nichts geschätzt.** Ein Gespräch ohne Einzelbewertung zeigt seine
Balken nicht, sondern sagt, dass es ohne Bewertung abgelegt wurde.
"""

from datetime import datetime

import config
from modules.call_analysis import _text_zu_liste
from modules.dashboard_teile import (FARBE_AKZENT, FARBE_GUT, FARBE_SCHLECHT,
                                     FARBE_WARNUNG, WOCHENTAGE, ampelfarbe, balken,
                                     euro, euro_kurz, ring, seite_bauen, sicher)

# Wie ein Ergebnis eingefärbt wird.
ERGEBNIS_FARBE = {"gewonnen": FARBE_GUT, "verloren": FARBE_SCHLECHT,
                  "offen": FARBE_WARNUNG, "unklar": FARBE_AKZENT}

UMSCHALTER = """
function zeigeGespraech(kennung) {
  var alle = document.querySelectorAll('.gespraech');
  for (var i = 0; i < alle.length; i++) {
    alle[i].style.display = (alle[i].id === 'g' + kennung) ? 'block' : 'none';
  }
  var knoepfe = document.querySelectorAll('.gwahl');
  for (var j = 0; j < knoepfe.length; j++) {
    knoepfe[j].className = 'gwahl' +
      (knoepfe[j].getAttribute('data-id') === String(kennung) ? ' gewaehlt' : '');
  }
}
"""

ZUSATZ_CSS = """
.gwahl { display: block; width: 100%; text-align: left; cursor: pointer;
         background: #121517; border: 1px solid #1C1F23; border-radius: 8px;
         padding: 10px 12px; margin-bottom: 7px; color: #E6E8EA;
         font-family: inherit; font-size: 13px; }
.gwahl:hover { border-color: rgba(232,98,44,.45); }
.gwahl.gewaehlt { border-color: #E8622C; background: rgba(232,98,44,.09); }
.gwahl .kopf { display: flex; justify-content: space-between; align-items: baseline;
               gap: 8px; }
.gwahl .punkte { font-variant-numeric: tabular-nums; font-weight: 600; }
.gwahl .unten { font-size: 11px; color: #6E767D; margin-top: 3px;
                display: flex; justify-content: space-between; }
.marke { font-size: 9.5px; text-transform: uppercase; letter-spacing: .1em;
         border-radius: 4px; padding: 2px 7px; border: 1px solid; }
.zitat { background: #121517; border-left: 2px solid #1C1F23; border-radius: 0 6px 6px 0;
         padding: 10px 13px; font-size: 12.5px; color: #8A9096; line-height: 1.65;
         white-space: pre-wrap; max-height: 220px; overflow-y: auto; }
.spalten { display: grid; grid-template-columns: 1fr 1fr; gap: 13px; }
@media (max-width: 760px) { .spalten { grid-template-columns: 1fr; } }
"""


class Verkaufsansicht:
    """Baut die Sales-Analyse als einzelne HTML-Datei."""

    def __init__(self, call_analysis=None, memory=None):
        self.call_analysis = call_analysis
        self.memory = memory

    # -- Bausteine ----------------------------------------------------------

    @staticmethod
    def _marke(ergebnis: str) -> str:
        """Farbige Markierung für gewonnen, verloren, offen, unklar."""
        farbe = ERGEBNIS_FARBE.get(ergebnis, FARBE_AKZENT)
        return ('<span class="marke" style="color:%s;border-color:%s">%s</span>'
                % (farbe, farbe, sicher(ergebnis)))

    def _wahlknopf(self, zeile, gewaehlt: bool) -> str:
        """Ein Eintrag in der Gesprächsliste links."""
        return ('<button class="gwahl%s" data-id="%d" onclick="zeigeGespraech(%d)">'
                '<div class="kopf"><span>%s</span>'
                '<span class="punkte" style="color:%s">%d</span></div>'
                '<div class="unten"><span>%s</span><span>%s</span></div></button>'
                % (" gewaehlt" if gewaehlt else "", zeile["id"], zeile["id"],
                   sicher(zeile["kunde"] or "ohne Namen"),
                   ampelfarbe(zeile["punktzahl"], 70, 45), zeile["punktzahl"],
                   sicher(zeile["datum"]),
                   euro_kurz(zeile["volumen"]) if zeile["volumen"] else "–"))

    @staticmethod
    def _liste(titel: str, eintraege: list, farbe: str, leer: str) -> str:
        """Eine beschriftete Aufzählung, oder ein Hinweis, dass nichts erfasst ist."""
        if not eintraege:
            inhalt = '<p class="leer">%s</p>' % sicher(leer)
        else:
            inhalt = "<ul>%s</ul>" % "".join(
                '<li><span style="color:%s">▸</span> %s</li>' % (farbe, sicher(e))
                for e in eintraege)
        return ('<section class="panel"><h2>%s</h2>%s</section>'
                % (sicher(titel), inhalt))

    def _detail(self, zeile, sichtbar: bool) -> str:
        """Die ausführliche Ansicht eines Gesprächs."""
        bewertung = {}
        if self.call_analysis is not None:
            bewertung = self.call_analysis.bewertung_lesen(zeile)

        einwaende = _text_zu_liste(zeile["einwaende"])
        offene = _text_zu_liste(zeile["offene_einwaende"])
        staerken = _text_zu_liste(zeile["staerken"])
        schwaechen = _text_zu_liste(zeile["schwaechen"])

        kacheln = [
            ("Punktzahl", "%d / 100" % zeile["punktzahl"], ""),
            ("Volumen", euro(zeile["volumen"]) if zeile["volumen"] else "nicht beziffert",
             "akzent" if zeile["volumen"] else ""),
            ("Einwände", str(len(einwaende)), ""),
            ("davon offen", str(len(offene)),
             "schlecht" if offene else "gut"),
        ]
        kachelblock = '<div class="kacheln">%s</div>' % "".join(
            '<div class="kachel"><div class="wert %s">%s</div>'
            '<div class="name">%s</div></div>' % (k, sicher(w), sicher(n))
            for n, w, k in kacheln)

        # Ring und Einzelbewertungen
        if bewertung and self.call_analysis is not None:
            balkenblock = ""
            for schluessel, beschriftung in self.call_analysis.DIMENSIONEN:
                if schluessel not in bewertung:
                    continue
                wert = bewertung[schluessel]
                balkenblock += balken(beschriftung, wert, 10, "%.0f / 10" % wert,
                                      ampelfarbe(wert * 10, 70, 40))
        else:
            balkenblock = ('<p class="leer">Dieses Gespräch wurde ohne '
                           'Einzelbewertung abgelegt - dazu gibt es keine Balken.</p>')

        kopfteil = (
            '<section class="panel breit"><h2>%s<em>%s</em></h2>'
            '<div class="ringfeld">%s<div class="ringtext">'
            '<div class="gross">%s %s</div>'
            '<div class="klein">%s</div></div></div>'
            '<div style="margin-top:14px">%s</div></section>'
            % (sicher(zeile["kunde"] or "Gespräch ohne Namen"), sicher(zeile["datum"]),
               ring(zeile["punktzahl"], "Punkte", 132,
                    ampelfarbe(zeile["punktzahl"], 70, 45)),
               self._marke(zeile["ergebnis"]),
               euro_kurz(zeile["volumen"]) if zeile["volumen"] else "",
               sicher(zeile["naechster_schritt"] or
                      "Es ist kein nächster Schritt vereinbart worden."),
               kachelblock))

        bewertungsteil = ('<section class="panel"><h2>Einzelbewertung</h2>%s</section>'
                          % balkenblock)

        teile = [kopfteil, bewertungsteil,
                 self._liste("Das lief gut", staerken, FARBE_GUT,
                             "Nichts als Stärke festgehalten."),
                 self._liste("Das fehlte", schwaechen, FARBE_SCHLECHT,
                             "Keine Schwächen festgehalten."),
                 self._liste("Einwände", einwaende, FARBE_WARNUNG,
                             "Es kamen keine Einwände."),
                 self._liste("Unbeantwortet geblieben", offene, FARBE_SCHLECHT,
                             "Alle Einwände wurden behandelt.")]

        if (zeile["rohtext"] or "").strip():
            teile.append('<section class="panel voll"><h2>So hat er es erzählt</h2>'
                         '<div class="zitat">%s</div></section>'
                         % sicher(zeile["rohtext"]))

        return ('<div class="gespraech" id="g%d" style="display:%s">'
                '<div class="raster" style="padding:0">%s</div></div>'
                % (zeile["id"], "block" if sichtbar else "none", "".join(teile)))

    # -- Bauen --------------------------------------------------------------

    def bauen(self, ziel=None, grenze: int = 40) -> dict:
        """Erzeugt ``sales.html``."""
        jetzt = datetime.now()
        zeilen = []
        if self.call_analysis is not None:
            try:
                zeilen = self.call_analysis.gespraeche(grenze)
            except Exception as fehler:
                return {"ok": False,
                        "fehler": "Die Gespräche ließen sich nicht lesen: %s" % fehler}

        muster = {}
        if self.call_analysis is not None and zeilen:
            try:
                muster = self.call_analysis.verkaufsmuster()
            except Exception:
                muster = {}

        if not zeilen:
            inhalt = ('<div class="raster"><section class="panel voll">'
                      '<h2>Sales-Analyse</h2>'
                      '<p class="leer">Es ist noch kein Kundengespräch festgehalten. '
                      'Erzähl Jarvis, wie ein Termin gelaufen ist - er bewertet ihn '
                      'und legt ihn hier ab.</p></section></div>')
            ticker = "<span>Noch keine Gespräche erfasst</span>"
        else:
            liste = "".join(self._wahlknopf(z, index == 0)
                            for index, z in enumerate(zeilen))
            details = "".join(self._detail(z, index == 0)
                              for index, z in enumerate(zeilen))
            inhalt = ('<div class="raster">'
                      '<section class="panel schmal"><h2>Gespräche<em>%d</em></h2>%s</section>'
                      '<div style="grid-column:span 9;min-width:0">%s</div>'
                      '</div>' % (len(zeilen), liste, details))

            teile = ["Gespräche <b>%d</b>" % len(zeilen)]
            if muster.get("anzahl"):
                teile.append("Abschlussquote <b>%.0f%%</b>"
                             % muster.get("abschlussquote", 0))
                teile.append("Durchschnitt <b>%.1f</b> Punkte"
                             % muster.get("durchschnitt", 0))
                for einwand in muster.get("wiederkehrende_einwaende", [])[:1]:
                    teile.append('Einwand "%s" <b class="rot">%dx</b>'
                                 % (sicher(einwand["einwand"]), einwand["anzahl"]))
            ticker = "".join("<span>%s</span>" % t for t in teile)

        links = ('<div><h1>Jarvis <span>// Sales-Analyse</span></h1>'
                 '<p>%s, %s &middot; Stand %s Uhr &middot; %s</p></div>'
                 % (WOCHENTAGE[jetzt.weekday()], jetzt.strftime("%d.%m.%Y"),
                    jetzt.strftime("%H:%M"), sicher(config.FIRMA)))
        rechts = ('<nav><a href="dashboard.html">Cockpit</a>'
                  '<a class="aktiv" href="sales.html">Sales-Analyse</a></nav>')

        seite = seite_bauen("Jarvis Sales-Analyse", ticker, links, rechts, inhalt,
                            "Streng bewertet: ein freundliches Gespräch ohne Ergebnis "
                            "ist kein gutes Gespräch.<br>"
                            "Gezeigt wird nur, was wirklich erfasst wurde.")
        seite = seite.replace("</style>", ZUSATZ_CSS + "</style>")
        seite = seite.replace("</body>", "<script>%s</script>\n</body>" % UMSCHALTER)

        try:
            config.DASHBOARD_VERZEICHNIS.mkdir(parents=True, exist_ok=True)
            pfad = ziel or (config.DASHBOARD_VERZEICHNIS / "sales.html")
            with open(str(pfad), "w", encoding="utf-8") as datei:
                datei.write(seite)
        except OSError as fehler:
            return {"ok": False,
                    "fehler": "Die Sales-Analyse ließ sich nicht schreiben: %s" % fehler}
        return {"ok": True, "datei": str(pfad), "anzahl": len(zeilen),
                "text": "Die Sales-Analyse ist gebaut: %s" % pfad}
