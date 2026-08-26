#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Command Center - erzeugt ``dashboard/dashboard.html`` und ``data.json``.

Der Nutzer soll auf einen Blick sehen, wie sein Betrieb steht: Zahlen des
Monats, Termine, Posteingang, offene Leads, Notizen und - besonders wichtig -
was Jarvis zuletzt getan hat. Jede ausgeführte Aktion steht dort. Ein
Assistent, der handelt, muss nachprüfbar sein.

Die Seite lädt sich alle 60 Sekunden selbst neu und braucht keinen Server.
"""

import html
import json
from datetime import datetime

import config
from modules.memory import heute_datum

# Farben des Cockpits
FARBE_HINTERGRUND = "#08090B"
FARBE_PANEL = "#0F1113"
FARBE_AKZENT = "#E8622C"

WOCHENTAGE = ["Montag", "Dienstag", "Mittwoch", "Donnerstag", "Freitag",
              "Samstag", "Sonntag"]

SEITE = """<!DOCTYPE html>
<html lang="de">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta http-equiv="refresh" content="60">
<title>Jarvis Command Center</title>
<style>
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body {
    background: %(bg)s; color: #E6E8EA; min-height: 100vh;
    font-family: -apple-system, BlinkMacSystemFont, "Helvetica Neue", Arial, sans-serif;
    padding-bottom: 40px;
  }
  .ticker {
    background: linear-gradient(90deg, %(akzent)s22, transparent);
    border-bottom: 1px solid %(akzent)s55; padding: 10px 20px;
    font-size: 13px; letter-spacing: .06em; text-transform: uppercase;
    display: flex; gap: 28px; flex-wrap: wrap; align-items: center;
  }
  .ticker b { color: %(akzent)s; text-shadow: 0 0 12px %(akzent)s88; }
  header { padding: 26px 20px 10px; }
  header h1 {
    font-size: 26px; font-weight: 600; letter-spacing: .02em;
    color: %(akzent)s; text-shadow: 0 0 22px %(akzent)s55;
  }
  header p { color: #8A9096; font-size: 14px; margin-top: 4px; }
  .raster {
    display: grid; gap: 14px; padding: 14px 20px;
    grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
  }
  .panel {
    background: %(panel)s; border: 1px solid #1C1F23; border-radius: 10px;
    padding: 16px 18px;
  }
  .panel h2 {
    font-size: 11px; text-transform: uppercase; letter-spacing: .14em;
    color: #6E767D; margin-bottom: 12px; font-weight: 600;
  }
  .kacheln { display: grid; grid-template-columns: repeat(auto-fit, minmax(120px,1fr)); gap: 10px; }
  .kachel {
    background: #121517; border: 1px solid #1C1F23; border-radius: 8px;
    padding: 12px 14px;
  }
  .kachel .wert { font-size: 22px; font-weight: 600; color: #F2F4F6; }
  .kachel .wert.akzent { color: %(akzent)s; text-shadow: 0 0 16px %(akzent)s66; }
  .kachel .wert.gut { color: #4CC38A; }
  .kachel .wert.schlecht { color: #E5484D; }
  .kachel .name { font-size: 11px; color: #6E767D; text-transform: uppercase;
                  letter-spacing: .08em; margin-top: 4px; }
  ul { list-style: none; }
  li { padding: 8px 0; border-bottom: 1px solid #17191C; font-size: 14px; line-height: 1.45; }
  li:last-child { border-bottom: none; }
  .zeit { color: %(akzent)s; font-variant-numeric: tabular-nums; margin-right: 8px; }
  .grau { color: #6E767D; font-size: 12px; }
  .warnung { color: #E5484D; }
  .ok { color: #4CC38A; }
  .leer { color: #4A5157; font-style: italic; font-size: 13px; }
  .status { display: inline-block; width: 7px; height: 7px; border-radius: 50%%;
            margin-right: 7px; }
  .an { background: #4CC38A; box-shadow: 0 0 8px #4CC38A; }
  .aus { background: #3A4046; }
  footer { padding: 16px 20px; color: #4A5157; font-size: 12px; }
</style>
</head>
<body>
<div class="ticker">%(ticker)s</div>
<header>
  <h1>Jarvis Command Center</h1>
  <p>%(wochentag)s, %(datum)s &middot; Stand %(uhrzeit)s Uhr &middot; %(firma)s</p>
</header>
<div class="raster">
%(panels)s
</div>
<footer>Diese Seite aktualisiert sich alle 60 Sekunden von selbst.
Alle Daten liegen lokal auf diesem Rechner.</footer>
</body>
</html>
"""


def sicher(text) -> str:
    """Macht Text HTML-sicher - Kundennamen dürfen die Seite nicht aufbrechen."""
    return html.escape(str(text if text is not None else ""))


def euro(betrag) -> str:
    """Formatiert einen Betrag deutsch mit Euro-Zeichen."""
    try:
        betrag = float(betrag)
    except (TypeError, ValueError):
        betrag = 0.0
    return "{:,.2f}".format(betrag).replace(",", "#").replace(".", ",").replace("#", ".") + " €"


class Dashboard:
    """Baut das Command Center als einzelne HTML-Datei."""

    def __init__(self, memory=None, bookkeeping=None, call_analysis=None,
                 recall=None, kalender=None, mail=None, routines=None,
                 scheduler=None, mcp=None):
        self.memory = memory
        self.bookkeeping = bookkeeping
        self.call_analysis = call_analysis
        self.recall = recall
        self.kalender = kalender
        self.mail = mail
        self.routines = routines
        self.scheduler = scheduler
        self.mcp = mcp

    # -- Daten sammeln ------------------------------------------------------

    def daten_sammeln(self, mit_netz: bool = False) -> dict:
        """Trägt alles zusammen, was auf die Seite kommt.

        ``mit_netz`` steuert, ob Kalender und Posteingang abgefragt werden -
        beim Bauen im Hintergrund bleibt das aus, damit es schnell bleibt.
        """
        jetzt = datetime.now()
        daten = {"erzeugt": jetzt.strftime("%Y-%m-%d %H:%M:%S"),
                 "wochentag": WOCHENTAGE[jetzt.weekday()],
                 "datum": jetzt.strftime("%d.%m.%Y"),
                 "uhrzeit": jetzt.strftime("%H:%M"),
                 "firma": config.FIRMA, "nutzer": config.NUTZER_NAME}

        if self.bookkeeping is not None:
            try:
                daten["monat"] = self.bookkeeping.auswertung(
                    jetzt.strftime("%Y-%m-01"), heute_datum())
                daten["belege"] = self.bookkeeping.fehlende_belege()
            except Exception as fehler:
                daten["monat_fehler"] = str(fehler)

        if self.call_analysis is not None:
            try:
                daten["leads"] = self.call_analysis.offene_leads()
                daten["muster"] = self.call_analysis.verkaufsmuster()
            except Exception as fehler:
                daten["leads_fehler"] = str(fehler)

        if self.memory is not None:
            try:
                daten["notizen"] = self.memory.notizen_letzte(8)
                daten["punkte"] = self.memory.punkte_offen()
                daten["protokoll"] = self.memory.protokoll(14)
                daten["statistik"] = self.memory.statistik()
            except Exception as fehler:
                daten["memory_fehler"] = str(fehler)

        if self.routines is not None:
            try:
                daten["routinen"] = self.routines.statistik()
            except Exception:
                daten["routinen"] = {}

        if self.scheduler is not None:
            try:
                daten["zeitplan"] = self.scheduler.uebersicht()
            except Exception:
                daten["zeitplan"] = []

        if mit_netz and self.kalender is not None and self.kalender.verfuegbar():
            try:
                daten["kalender"] = self.kalender.termine(3)
            except Exception as fehler:
                daten["kalender"] = {"ok": False, "fehler": str(fehler)}

        if mit_netz and self.mail is not None and self.mail.lesen_moeglich():
            try:
                daten["mail"] = self.mail.ungelesene(10)
            except Exception as fehler:
                daten["mail"] = {"ok": False, "fehler": str(fehler)}

        daten["dienste"] = config.konfig_uebersicht()
        if self.mcp is not None:
            try:
                daten["mcp"] = self.mcp.zustand()
            except Exception:
                daten["mcp"] = {}
        return daten

    # -- Panels -------------------------------------------------------------

    @staticmethod
    def _panel(titel: str, inhalt: str) -> str:
        return '<section class="panel"><h2>%s</h2>%s</section>' % (sicher(titel), inhalt)

    @staticmethod
    def _liste(eintraege: list, leer_text: str) -> str:
        if not eintraege:
            return '<p class="leer">%s</p>' % sicher(leer_text)
        return "<ul>%s</ul>" % "".join("<li>%s</li>" % eintrag for eintrag in eintraege)

    def _panel_zahlen(self, daten: dict) -> str:
        monat = daten.get("monat")
        if not monat:
            return self._panel("Monat", '<p class="leer">Keine Buchhaltungsdaten.</p>')
        ergebnis_klasse = "gut" if monat["ergebnis"] >= 0 else "schlecht"
        kacheln = [
            ("Einnahmen", euro(monat["einnahmen"]), "gut"),
            ("Ausgaben", euro(monat["ausgaben"]), ""),
            ("Ergebnis", euro(monat["ergebnis"]), ergebnis_klasse),
            ("Zahllast", euro(monat["zahllast"]), "akzent"),
            ("Vorsteuer", euro(monat["vorsteuer"]), ""),
            ("Buchungen", str(monat["anzahl"]), ""),
        ]
        inhalt = '<div class="kacheln">%s</div>' % "".join(
            '<div class="kachel"><div class="wert %s">%s</div><div class="name">%s</div></div>'
            % (klasse, sicher(wert), sicher(name)) for name, wert, klasse in kacheln)
        return self._panel("Laufender Monat", inhalt)

    def _panel_belege(self, daten: dict) -> str:
        belege = daten.get("belege")
        if not belege:
            return ""
        if belege["anzahl"] == 0:
            inhalt = '<p class="ok">Zu allen Ausgaben liegt ein Beleg vor.</p>'
        else:
            zeilen = ['<span class="zeit">%s</span>%s <span class="grau">%s</span>'
                      % (sicher(e["datum"]), sicher(e["haendler"] or "unbekannt"),
                         euro(e["betrag"])) for e in belege["buchungen"][:8]]
            inhalt = ('<p class="warnung">%d Ausgaben ohne Beleg, zusammen %s.</p>%s'
                      % (belege["anzahl"], euro(belege["summe"]),
                         self._liste(zeilen, "")))
        return self._panel("Fehlende Belege", inhalt)

    def _panel_termine(self, daten: dict) -> str:
        kalender = daten.get("kalender")
        if not kalender:
            return self._panel("Termine",
                               '<p class="leer">Kein Kalender eingerichtet.</p>')
        if not kalender.get("ok"):
            return self._panel("Termine", '<p class="warnung">%s</p>'
                               % sicher(kalender.get("fehler", "nicht erreichbar")))
        zeilen = ['<span class="zeit">%s %s</span>%s%s'
                  % (sicher(t["tag"]), sicher(t["uhrzeit"]), sicher(t["titel"]),
                     (' <span class="grau">%s</span>' % sicher(t["ort"])) if t["ort"] else "")
                  for t in kalender.get("termine", [])[:10]]
        inhalt = self._liste(zeilen, "Nichts eingetragen.")
        for konflikt in kalender.get("konflikte", [])[:3]:
            inhalt += '<p class="warnung">%s</p>' % sicher(konflikt["text"])
        return self._panel("Termine", inhalt)

    def _panel_mail(self, daten: dict) -> str:
        mail = daten.get("mail")
        if not mail:
            return self._panel("Posteingang",
                               '<p class="leer">Kein Postfach eingerichtet.</p>')
        if not mail.get("ok"):
            return self._panel("Posteingang", '<p class="warnung">%s</p>'
                               % sicher(mail.get("fehler", "nicht erreichbar")))
        zeilen = []
        for eintrag in mail.get("wichtig", [])[:5] + mail.get("spaeter", [])[:5]:
            marke = "warnung" if eintrag["einstufung"] == "wichtig" else "grau"
            zeilen.append('<span class="%s">%s</span> %s<br><span class="grau">%s</span>'
                          % (marke, sicher(eintrag["einstufung"]),
                             sicher(eintrag["betreff"]),
                             sicher(eintrag["absender"][:60])))
        return self._panel("Posteingang (%d ungelesen)" % mail.get("anzahl", 0),
                           self._liste(zeilen, "Nichts Ungelesenes."))

    def _panel_leads(self, daten: dict) -> str:
        leads = daten.get("leads")
        if not leads:
            return ""
        zeilen = ['<span class="zeit">%s</span>%s <span class="grau">%s &middot; %d Punkte</span>'
                  % (sicher(l["datum"]), sicher(l["kunde"] or "ohne Namen"),
                     euro(l["volumen"]), l["punktzahl"])
                  for l in leads.get("leads", [])[:8]]
        inhalt = ('<div class="kacheln"><div class="kachel">'
                  '<div class="wert akzent">%s</div>'
                  '<div class="name">Offenes Volumen</div></div>'
                  '<div class="kachel"><div class="wert">%d</div>'
                  '<div class="name">Offene Leads</div></div></div>'
                  % (euro(leads.get("volumen_offen", 0)), leads.get("anzahl", 0)))
        inhalt += self._liste(zeilen, "Kein Lead offen.")
        muster = daten.get("muster") or {}
        if muster.get("anzahl"):
            inhalt += ('<p class="grau">Abschlussquote %.1f Prozent bei %d Gesprächen.</p>'
                       % (muster.get("abschlussquote", 0), muster["anzahl"]))
            for einwand in muster.get("wiederkehrende_einwaende", [])[:2]:
                inhalt += ('<p class="warnung">Einwand "%s" kam %d mal.</p>'
                           % (sicher(einwand["einwand"]), einwand["anzahl"]))
        return self._panel("Vertrieb", inhalt)

    def _panel_offen(self, daten: dict) -> str:
        punkte = daten.get("punkte") or []
        zeilen = ['%s%s' % (sicher(p["text"]),
                            (' <span class="grau">bis %s</span>' % sicher(p["faellig"]))
                            if p["faellig"] else "")
                  for p in punkte[:12]]
        return self._panel("Noch offen", self._liste(zeilen, "Nichts offen."))

    def _panel_notizen(self, daten: dict) -> str:
        notizen = daten.get("notizen") or []
        zeilen = ['<span class="zeit">%s</span>%s' % (sicher(n["angelegt"][5:10]),
                                                      sicher(n["text"]))
                  for n in notizen]
        return self._panel("Notizen", self._liste(zeilen, "Noch keine Notizen."))

    def _panel_protokoll(self, daten: dict) -> str:
        protokoll = daten.get("protokoll") or []
        zeilen = []
        for eintrag in protokoll:
            klasse = "ok" if eintrag["status"] == "ok" else "warnung"
            zeilen.append('<span class="zeit">%s</span><span class="%s">%s</span> '
                          '<span class="grau">%s</span>'
                          % (sicher(eintrag["zeit"][11:16]), klasse,
                             sicher(eintrag["werkzeug"]),
                             sicher((eintrag["ergebnis"] or "")[:80])))
        return self._panel("Was Jarvis getan hat",
                           self._liste(zeilen, "Noch nichts ausgeführt."))

    def _panel_zeitplan(self, daten: dict) -> str:
        eintraege = daten.get("zeitplan") or []
        zeilen = ['<span class="zeit">%s</span>%s' % (sicher(e["uhrzeit"]),
                                                      sicher(e["beschreibung"]))
                  for e in eintraege]
        routinen = daten.get("routinen") or {}
        inhalt = self._liste(zeilen, "Nichts geplant.")
        if routinen.get("anzahl"):
            inhalt += ('<p class="grau">%d Routinen hinterlegt: %s</p>'
                       % (routinen["anzahl"], sicher(", ".join(routinen.get("namen", [])))))
        return self._panel("Zeitplan", inhalt)

    def _panel_dienste(self, daten: dict) -> str:
        dienste = daten.get("dienste") or {}
        zeilen = ['<span class="status %s"></span>%s'
                  % ("an" if aktiv else "aus", sicher(name))
                  for name, aktiv in dienste.items()]
        mcp = daten.get("mcp") or {}
        for name, angaben in (mcp.get("dienste") or {}).items():
            zeilen.append('<span class="status %s"></span>MCP %s '
                          '<span class="grau">%d Werkzeuge</span>'
                          % ("an" if angaben.get("laeuft") else "aus", sicher(name),
                             angaben.get("werkzeuge", 0)))
        return self._panel("Dienste", self._liste(zeilen, "Nichts eingerichtet."))

    def _ticker(self, daten: dict) -> str:
        teile = []
        monat = daten.get("monat")
        if monat:
            teile.append("Ergebnis Monat <b>%s</b>" % euro(monat["ergebnis"]))
            teile.append("Zahllast <b>%s</b>" % euro(monat["zahllast"]))
        leads = daten.get("leads")
        if leads:
            teile.append("Offene Leads <b>%d</b> über <b>%s</b>"
                         % (leads.get("anzahl", 0), euro(leads.get("volumen_offen", 0))))
        belege = daten.get("belege")
        if belege and belege.get("anzahl"):
            teile.append("Belege fehlen <b>%d</b>" % belege["anzahl"])
        punkte = daten.get("punkte") or []
        teile.append("Offene Punkte <b>%d</b>" % len(punkte))
        if not teile:
            teile.append("Jarvis ist bereit")
        return "".join("<span>%s</span>" % teil for teil in teile)

    # -- Bauen --------------------------------------------------------------

    def bauen(self, mit_netz: bool = False) -> dict:
        """Erzeugt ``dashboard.html`` und ``data.json``."""
        daten = self.daten_sammeln(mit_netz)
        panels = "".join(teil for teil in [
            self._panel_zahlen(daten),
            self._panel_termine(daten),
            self._panel_leads(daten),
            self._panel_offen(daten),
            self._panel_mail(daten),
            self._panel_belege(daten),
            self._panel_notizen(daten),
            self._panel_zeitplan(daten),
            self._panel_protokoll(daten),
            self._panel_dienste(daten),
        ] if teil)

        seite = SEITE % {"bg": FARBE_HINTERGRUND, "panel": FARBE_PANEL,
                         "akzent": FARBE_AKZENT, "ticker": self._ticker(daten),
                         "wochentag": sicher(daten["wochentag"]),
                         "datum": sicher(daten["datum"]),
                         "uhrzeit": sicher(daten["uhrzeit"]),
                         "firma": sicher(daten["firma"]), "panels": panels}
        try:
            config.DASHBOARD_VERZEICHNIS.mkdir(parents=True, exist_ok=True)
            html_pfad = config.DASHBOARD_VERZEICHNIS / "dashboard.html"
            json_pfad = config.DASHBOARD_VERZEICHNIS / "data.json"
            html_pfad.write_text(seite, encoding="utf-8")
            json_pfad.write_text(json.dumps(daten, ensure_ascii=False, indent=2,
                                            default=str), encoding="utf-8")
        except OSError as fehler:
            return {"ok": False,
                    "fehler": "Das Dashboard ließ sich nicht schreiben: %s" % fehler}
        return {"ok": True, "datei": str(html_pfad), "daten": str(json_pfad),
                "text": "Das Command Center ist gebaut: %s" % html_pfad}
