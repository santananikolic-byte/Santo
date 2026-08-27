#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Command Center - erzeugt ``dashboard/dashboard.html`` und ``data.json``.

Der Nutzer soll auf einen Blick sehen, wie sein Betrieb steht: Zahlen des
Monats, Verlauf, Termine, Posteingang, offene Leads, Notizen und - besonders
wichtig - was Jarvis zuletzt getan hat. Jede ausgeführte Aktion steht dort.
Ein Assistent, der handelt, muss nachprüfbar sein.

**Es wird nur gezeigt, was wirklich in der Datenbank steht.** Ein Bereich ohne
Daten bleibt sichtbar leer und sagt das auch. Eine Kennzahl, die nach etwas
aussieht, aber auf nichts beruht, wäre schlimmer als eine leere Fläche - der
Nutzer trifft danach Entscheidungen.

Die Seite lädt sich alle 60 Sekunden selbst neu und braucht keinen Server.
"""

import json
from datetime import datetime

import config
from modules.dashboard_teile import (FARBE_AKZENT, FARBE_GRAU, FARBE_GUT,
                                     FARBE_SCHLECHT, FARBE_WARNUNG, WOCHENTAGE,
                                     ampelfarbe, balken, euro, euro_kurz, prozent,
                                     ring, saeulen, seite_bauen, sicher, sparkline)
from modules.memory import heute_datum
from modules.sales_view import Verkaufsansicht


class Dashboard:
    """Baut das Command Center als einzelne HTML-Datei."""

    def __init__(self, memory=None, bookkeeping=None, call_analysis=None,
                 recall=None, kalender=None, mail=None, routines=None,
                 scheduler=None, mcp=None, akquise=None, team=None,
                 privat=None):
        self.memory = memory
        self.bookkeeping = bookkeeping
        self.call_analysis = call_analysis
        self.recall = recall
        self.kalender = kalender
        self.mail = mail
        self.routines = routines
        self.scheduler = scheduler
        self.mcp = mcp
        self.akquise = akquise
        self.team = team
        self.privat = privat
        # Die Sales-Analyse ist eine eigene Seite, wird aber immer mitgebaut -
        # sonst zeigt der Verweis im Kopf auf eine Datei, die es nicht gibt.
        self.verkaufsansicht = Verkaufsansicht(call_analysis, memory)

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
                daten["belegquote"] = self.bookkeeping.belegquote(
                    jetzt.strftime("%Y-%m-01"), heute_datum())
                daten["verlauf"] = self.bookkeeping.tagesverlauf(30)
                daten["monate"] = self.bookkeeping.monatsverlauf(6)
            except Exception as fehler:
                daten["monat_fehler"] = str(fehler)

        if self.call_analysis is not None:
            try:
                daten["leads"] = self.call_analysis.offene_leads()
                daten["muster"] = self.call_analysis.verkaufsmuster()
                daten["dimensionen"] = self.call_analysis.dimensionen_schnitt()
            except Exception as fehler:
                daten["leads_fehler"] = str(fehler)

        if self.akquise is not None:
            try:
                daten["pipeline"] = self.akquise.pipeline()
                daten["nachfassen"] = self.akquise.nachfassliste()
                daten["cashflow"] = self.akquise.cashflow_prognose(
                    6, self.bookkeeping)
            except Exception as fehler:
                daten["pipeline_fehler"] = str(fehler)

        if self.privat is not None:
            try:
                daten["bedarf"] = self.privat.bedarfsrechnung(self.akquise)
                daten["fixkosten"] = self.privat.fixkosten()
                daten["erinnerungen"] = self.privat.erinnerungen_faellig(21)
            except Exception as fehler:
                daten["bedarf_fehler"] = str(fehler)

        if self.team is not None:
            try:
                daten["auftraege"] = [dict(z) for z in self.team.auftraege_letzte(8)]
            except Exception:
                daten["auftraege"] = []

        if self.memory is not None:
            try:
                daten["notizen"] = self.memory.notizen_letzte(8)
                daten["punkte"] = self.memory.punkte_offen()
                daten["protokoll"] = self.memory.protokoll(16)
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

    # -- Bausteine ----------------------------------------------------------

    @staticmethod
    def _panel(titel: str, inhalt: str, breite: str = "", zusatz: str = "") -> str:
        """Ein Kasten mit Überschrift."""
        klasse = ("panel " + breite).strip()
        kopf = sicher(titel)
        if zusatz:
            kopf += "<em>%s</em>" % sicher(zusatz)
        return '<section class="%s"><h2>%s</h2>%s</section>' % (klasse, kopf, inhalt)

    @staticmethod
    def _liste(eintraege: list, leer_text: str) -> str:
        """Eine Aufzählung, oder ein ehrlicher Hinweis, dass nichts da ist."""
        if not eintraege:
            return '<p class="leer">%s</p>' % sicher(leer_text)
        return "<ul>%s</ul>" % "".join("<li>%s</li>" % eintrag for eintrag in eintraege)

    @staticmethod
    def _kacheln(eintraege: list) -> str:
        """Ein Raster aus Kennzahlen-Kacheln."""
        return '<div class="kacheln">%s</div>' % "".join(
            '<div class="kachel"><div class="wert %s">%s</div>'
            '<div class="name">%s</div></div>'
            % (klasse, sicher(wert), sicher(name)) for name, wert, klasse in eintraege)

    # -- Panels -------------------------------------------------------------

    def _panel_belegquote(self, daten: dict) -> str:
        """Die wichtigste einzelne Zahl: Wie viel Geld ist belegt?"""
        quote = (daten.get("belegquote") or {})
        wert = quote.get("quote")
        farbe = ampelfarbe(wert if wert is not None else 0, 90, 60)
        if wert is None:
            text = ('<div class="klein">Noch keine Ausgaben erfasst. Sobald du '
                    'Belege buchst, siehst du hier, wie viel davon belegt ist.</div>')
        else:
            text = ('<div class="gross">%s</div>'
                    '<div class="klein">von %s Ausgaben sind belegt.<br>'
                    'Genau das fehlt sonst beim Steuerberater.</div>'
                    % (euro(quote.get("belegt", 0)), euro(quote.get("gesamt", 0))))
        inhalt = ('<div class="ringfeld">%s<div class="ringtext">%s</div></div>'
                  % (ring(wert, "belegt", 132, farbe), text))
        return self._panel("Belegquote", inhalt, "", "laufender Monat")

    def _panel_zahlen(self, daten: dict) -> str:
        """Die Zahlen des laufenden Monats."""
        monat = daten.get("monat")
        if not monat:
            return self._panel("Laufender Monat",
                               '<p class="leer">Keine Buchhaltungsdaten.</p>', "breit")
        leads = daten.get("leads") or {}
        kacheln = [
            ("Einnahmen", euro(monat["einnahmen"]), "gut"),
            ("Ausgaben", euro(monat["ausgaben"]), ""),
            ("Ergebnis", euro(monat["ergebnis"]),
             "gut" if monat["ergebnis"] >= 0 else "schlecht"),
            ("Zahllast", euro(monat["zahllast"]), "akzent"),
            ("Vorsteuer", euro(monat["vorsteuer"]), ""),
            ("Umsatzsteuer", euro(monat["umsatzsteuer"]), ""),
            ("Buchungen", str(monat["anzahl"]), ""),
            ("Offenes Volumen", euro_kurz(leads.get("volumen_offen", 0)), "akzent"),
        ]
        return self._panel("Laufender Monat", self._kacheln(kacheln), "breit",
                           "%s bis %s" % (monat["von"], monat["bis"]))

    def _panel_verlauf(self, daten: dict) -> str:
        """Sparklines der letzten 30 Tage und die Monatsbilanz."""
        verlauf = daten.get("verlauf") or {}
        monate = daten.get("monate") or {}
        einnahmen = verlauf.get("einnahmen") or []
        ausgaben = verlauf.get("ausgaben") or []

        if not any(einnahmen) and not any(ausgaben):
            inhalt = ('<p class="leer">In den letzten 30 Tagen ist noch nichts '
                      'gebucht worden.</p>')
        else:
            inhalt = (
                '<div class="verlauf">'
                '<div class="verlaufblock"><div class="verlaufkopf">'
                '<span>Einnahmen 30 Tage</span><b>%s</b></div>%s</div>'
                '<div class="verlaufblock"><div class="verlaufkopf">'
                '<span>Ausgaben 30 Tage</span><b>%s</b></div>%s</div>'
                '</div>'
                % (euro(verlauf.get("summe_einnahmen", 0)),
                   sparkline(einnahmen, farbe=FARBE_GUT),
                   euro(verlauf.get("summe_ausgaben", 0)),
                   sparkline(ausgaben, farbe=FARBE_AKZENT)))

        if monate.get("ergebnis"):
            inhalt += ('<div style="margin-top:14px"><div class="verlaufkopf">'
                       '<span>Ergebnis je Monat</span><b>%s</b></div>%s</div>'
                       % (euro(monate["ergebnis"][-1]),
                          saeulen(monate["ergebnis"], monate.get("monate"))))
        return self._panel("Verlauf", inhalt, "breit")

    def _panel_vertrieb(self, daten: dict) -> str:
        """Abschlussquote und die eigene schwächste Stelle im Gespräch."""
        muster = daten.get("muster") or {}
        dimensionen = daten.get("dimensionen") or {}
        if not muster.get("anzahl"):
            return self._panel(
                "Vertrieb",
                '<p class="leer">Noch kein Gespräch festgehalten. Erzähl Jarvis von '
                'einem Kundentermin, dann bewertet er ihn.</p>')

        quote = muster.get("abschlussquote", 0)
        inhalt = ('<div class="ringfeld">%s<div class="ringtext">'
                  '<div class="gross">%s</div>'
                  '<div class="klein">%d Gespräche, Durchschnitt %s Punkte.<br>'
                  '%d gewonnen, %d verloren, %d offen.</div></div></div>'
                  % (ring(quote, "Abschluss", 116, ampelfarbe(quote, 50, 25)),
                     euro_kurz((daten.get("leads") or {}).get("volumen_offen", 0)),
                     muster["anzahl"], muster.get("durchschnitt", 0),
                     muster.get("gewonnen", 0), muster.get("verloren", 0),
                     muster.get("offen", 0)))

        zeilen = [e for e in (dimensionen.get("dimensionen") or [])
                  if e["wert"] is not None]
        if zeilen:
            inhalt += '<div style="margin-top:14px">'
            for eintrag in zeilen:
                inhalt += balken(eintrag["name"], eintrag["wert"], 10,
                                 "%.1f / 10" % eintrag["wert"],
                                 ampelfarbe(eintrag["wert"] * 10, 70, 40))
            inhalt += '</div>'
            schwach = dimensionen.get("schwaechste")
            if schwach:
                inhalt += ('<p class="achtung" style="font-size:12px;margin-top:6px">'
                           'Schwächste Stelle: %s mit %.1f von 10.</p>'
                           % (sicher(schwach["name"]), schwach["wert"]))
        for einwand in muster.get("wiederkehrende_einwaende", [])[:2]:
            inhalt += ('<p class="warnung" style="font-size:12px;margin-top:6px">'
                       'Einwand "%s" kam %d mal.</p>'
                       % (sicher(einwand["einwand"]), einwand["anzahl"]))
        return self._panel("Vertrieb", inhalt, "", "letzte 90 Tage")

    def _panel_kategorien(self, daten: dict) -> str:
        """Wohin das Geld fließt - Ausgaben je Kategorie."""
        monat = daten.get("monat") or {}
        nach_kategorie = monat.get("nach_kategorie") or {}
        if not nach_kategorie:
            return self._panel("Ausgaben je Kategorie",
                               '<p class="leer">Noch keine Ausgaben gebucht.</p>')
        groesster = max(nach_kategorie.values())
        inhalt = "".join(
            balken(name, betrag, groesster, euro(betrag))
            for name, betrag in list(nach_kategorie.items())[:8])
        return self._panel("Ausgaben je Kategorie", inhalt)

    def _panel_bedarf(self, daten: dict) -> str:
        """Was der Betrieb abwerfen muss, damit privat alles gedeckt ist.

        Das ist der Gehaltszettel eines Einzelunternehmers - er hat keinen.
        """
        bedarf = daten.get("bedarf")
        if not bedarf or not bedarf.get("berechenbar"):
            return self._panel(
                "Was der Betrieb tragen muss",
                '<p class="leer">Fixkosten sind noch nicht erfasst. Sag Jarvis, '
                'was monatlich fix rausgeht, dann steht hier, was der Betrieb '
                'abwerfen muss.</p>', "breit")

        noetig = bedarf["noetiger_umsatz"]
        gesichert = bedarf.get("gesichert")
        deckung = prozent(gesichert, noetig) if gesichert is not None else None
        farbe = ampelfarbe(deckung if deckung is not None else 0, 100, 60)

        if gesichert is None:
            beschreibung = ("<div class=\"klein\">Noch keine Auftragslage erfasst.</div>")
        elif bedarf["luecke"] > 0:
            beschreibung = ('<div class="gross" style="color:%s">%s fehlen</div>'
                            '<div class="klein">Gesichert laufen %s von %s.<br>'
                            'Das sind %s im Jahr, die noch hereinkommen müssen.</div>'
                            % (FARBE_SCHLECHT, euro(bedarf["luecke"]),
                               euro(gesichert), euro(noetig),
                               euro(bedarf["luecke"] * 12)))
        else:
            beschreibung = ('<div class="gross" style="color:%s">%s darüber</div>'
                            '<div class="klein">Gesichert laufen %s, nötig sind %s.'
                            '</div>'
                            % (FARBE_GUT, euro(-bedarf["luecke"]),
                               euro(gesichert), euro(noetig)))

        inhalt = ('<div class="ringfeld">%s<div class="ringtext">%s</div></div>'
                  % (ring(deckung, "gedeckt", 132, farbe), beschreibung))
        inhalt += self._kacheln([
            ("Nötig je Monat", euro(noetig), "akzent"),
            ("Privat fix", euro(bedarf["privat_je_monat"]), ""),
            ("Firma fix", euro(bedarf["firma_je_monat"]), ""),
            ("Steuerrücklage", euro(bedarf["steuerruecklage"]), "warn"),
        ])
        return self._panel("Was der Betrieb tragen muss", inhalt, "breit",
                           "%g Prozent Rücklage" % bedarf["steuersatz"])

    def _panel_erinnerungen(self, daten: dict) -> str:
        """Was in den nächsten Wochen ansteht - privat wie betrieblich."""
        anstehend = daten.get("erinnerungen")
        if not anstehend or not anstehend.get("anzahl"):
            return self._panel("Steht an",
                               '<p class="leer">In den nächsten drei Wochen '
                               'steht nichts an.</p>')
        zeilen = []
        for eintrag in anstehend["eintraege"][:8]:
            wann = ("heute" if eintrag["in_tagen"] == 0
                    else "morgen" if eintrag["in_tagen"] == 1
                    else "in %d Tagen" % eintrag["in_tagen"])
            klasse = "warnung" if eintrag["in_tagen"] <= 3 else "grau"
            zeilen.append('<span class="zeit">%s</span>%s '
                          '<span class="%s">%s</span> '
                          '<span class="grau">%s</span>'
                          % (sicher(eintrag["datum"][5:]), sicher(eintrag["was"]),
                             klasse, wann, sicher(eintrag["bereich"])))
        return self._panel("Steht an", self._liste(zeilen, ""), "",
                           "%d Termine" % anstehend["anzahl"])

    def _panel_fixkosten(self, daten: dict) -> str:
        """Die laufenden Verpflichtungen, größte zuerst."""
        kosten = daten.get("fixkosten")
        if not kosten or not kosten.get("anzahl"):
            return ""
        groesster = max([e["je_monat"] for e in kosten["eintraege"]] or [1])
        inhalt = ""
        for eintrag in kosten["eintraege"][:9]:
            inhalt += balken(
                "%s%s" % (eintrag["name"],
                          " (Firma)" if eintrag["bereich"] == "firma" else ""),
                eintrag["je_monat"], groesster, euro(eintrag["je_monat"]),
                FARBE_AKZENT if eintrag["bereich"] == "firma" else FARBE_WARNUNG)
        return self._panel("Fixkosten je Monat", inhalt, "",
                           euro(kosten["gesamt_je_monat"]))

    def _panel_pipeline(self, daten: dict) -> str:
        """Die Auftragspipeline nach Stufen - wo Geld auf der Straße liegt."""
        pipeline = daten.get("pipeline")
        if not pipeline or not pipeline.get("ok"):
            return self._panel("Auftragspipeline",
                               '<p class="leer">Noch kein Interessent erfasst.</p>')
        stufen = pipeline.get("stufen") or {}
        offene = [(name, angaben) for name, angaben in stufen.items()
                  if name not in ("gewonnen", "verloren") and angaben["anzahl"]]
        if not offene and not stufen.get("gewonnen", {}).get("anzahl"):
            return self._panel("Auftragspipeline",
                               '<p class="leer">Noch kein Interessent erfasst.</p>')

        groesster = max([a["wert_monat"] for _, a in offene] or [1])
        inhalt = self._kacheln([
            ("Gesichert je Monat", euro(pipeline["laufender_umsatz_monat"]), "gut"),
            ("Offen je Monat", euro(pipeline["offener_wert_monat"]), ""),
            ("Realistisch", euro(pipeline["gewichteter_wert_monat"]), "akzent"),
            ("Interessenten", str(pipeline["offen"]), ""),
        ])
        if offene:
            inhalt += '<div style="margin-top:13px">'
            for name, angaben in offene:
                inhalt += balken("%s (%d)" % (name.capitalize(), angaben["anzahl"]),
                                 angaben["wert_monat"], groesster,
                                 euro(angaben["wert_monat"]))
            inhalt += '</div>'
        return self._panel("Auftragspipeline", inhalt, "breit")

    def _panel_nachfassen(self, daten: dict) -> str:
        """Wer heute drankommt. Die wichtigste Liste des Tages."""
        nachfassen = daten.get("nachfassen")
        if not nachfassen or not nachfassen.get("anzahl"):
            return self._panel("Heute nachfassen",
                               '<p class="leer">Heute ist niemand fällig.</p>')
        zeilen = []
        for eintrag in nachfassen["eintraege"][:8]:
            spaet = ('<span class="warnung">%d Tage überfällig</span>'
                     % eintrag["seit_tagen"]) if eintrag["seit_tagen"] > 0 else ""
            zeilen.append('%s <span class="grau">%s · %s</span><br>'
                          '<span class="grau">%s</span> %s'
                          % (sicher(eintrag["firma"]), sicher(eintrag["stufe"]),
                             euro(eintrag["wert_monat"]),
                             sicher(eintrag["schritt"]), spaet))
        return self._panel("Heute nachfassen", self._liste(zeilen, ""), "",
                           "%d fällig" % nachfassen["anzahl"])

    def _panel_cashflow(self, daten: dict) -> str:
        """Was in den nächsten Monaten hereinkommt."""
        cashflow = daten.get("cashflow")
        if not cashflow or not cashflow.get("monate"):
            return ""
        reihe = cashflow["monate"]
        inhalt = ('<div class="verlaufkopf"><span>Erwartete Einnahmen</span>'
                  '<b>%s je Monat gesichert</b></div>%s'
                  % (euro(cashflow["gesichert_monat"]),
                     saeulen([m["einnahmen"] for m in reihe],
                             [m["monat"][5:] for m in reihe], 62, FARBE_GUT)))
        inhalt += ('<p class="grau" style="margin-top:10px">Aus der Pipeline kommen '
                   'gewichtet %s dazu. Kosten %s je Monat (%s).</p>'
                   % (euro(cashflow["pipeline_gewichtet"]),
                      euro(cashflow["kosten_monat"]), sicher(cashflow["kostenquelle"])))
        return self._panel("Cashflow-Vorschau", inhalt, "breit", "6 Monate")

    def _panel_team(self, daten: dict) -> str:
        """Was die Fachkräfte zuletzt gemacht haben."""
        auftraege = daten.get("auftraege") or []
        zeilen = ['<span class="zeit">%s</span>%s <span class="grau">%s</span>'
                  % (sicher(a["angelegt"][11:16]), sicher(a["rolle"]),
                     sicher((a["auftrag"] or "")[:70]))
                  for a in auftraege]
        return self._panel("Was das Team gemacht hat",
                           self._liste(zeilen, "Noch kein Auftrag ans Team."))

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
                  for t in kalender.get("termine", [])[:9]]
        inhalt = self._liste(zeilen, "Nichts eingetragen.")
        for konflikt in kalender.get("konflikte", [])[:3]:
            inhalt += '<p class="warnung">%s</p>' % sicher(konflikt["text"])
        return self._panel("Termine", inhalt, "", "nächste 3 Tage")

    def _panel_mail(self, daten: dict) -> str:
        mail = daten.get("mail")
        if not mail:
            return self._panel("Posteingang",
                               '<p class="leer">Kein Postfach eingerichtet.</p>')
        if not mail.get("ok"):
            return self._panel("Posteingang", '<p class="warnung">%s</p>'
                               % sicher(mail.get("fehler", "nicht erreichbar")))
        zeilen = []
        for eintrag in mail.get("wichtig", [])[:5] + mail.get("spaeter", [])[:4]:
            marke = "warnung" if eintrag["einstufung"] == "wichtig" else "grau"
            zeilen.append('<span class="%s">%s</span> %s<br>'
                          '<span class="grau">%s</span>'
                          % (marke, sicher(eintrag["einstufung"]),
                             sicher(eintrag["betreff"]),
                             sicher(eintrag["absender"][:60])))
        return self._panel("Posteingang", self._liste(zeilen, "Nichts Ungelesenes."),
                           "", "%d ungelesen" % mail.get("anzahl", 0))

    def _panel_offen(self, daten: dict) -> str:
        punkte = daten.get("punkte") or []
        zeilen = ['%s%s' % (sicher(p["text"]),
                            (' <span class="grau">bis %s</span>' % sicher(p["faellig"]))
                            if p["faellig"] else "")
                  for p in punkte[:12]]
        return self._panel("Noch offen", self._liste(zeilen, "Nichts offen."), "",
                           "%d" % len(punkte) if punkte else "")

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
            inhalt = ('<p class="warnung" style="margin-bottom:8px">%d Ausgaben ohne '
                      'Beleg, zusammen %s.</p>%s'
                      % (belege["anzahl"], euro(belege["summe"]),
                         self._liste(zeilen, "")))
        return self._panel("Fehlende Belege", inhalt)

    def _panel_leads(self, daten: dict) -> str:
        leads = daten.get("leads")
        if not leads or not leads.get("leads"):
            return self._panel("Offene Leads",
                               '<p class="leer">Kein Lead offen.</p>')
        zeilen = ['<span class="zeit">%s</span>%s <span class="grau">%s · %d Punkte</span>'
                  '<br><span class="grau">%s</span>'
                  % (sicher(l["datum"]), sicher(l["kunde"] or "ohne Namen"),
                     euro(l["volumen"]), l["punktzahl"],
                     sicher(l["naechster_schritt"] or "kein nächster Schritt vereinbart"))
                  for l in leads["leads"][:6]]
        return self._panel("Offene Leads", self._liste(zeilen, ""), "",
                           euro_kurz(leads.get("volumen_offen", 0)))

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
            klasse = {"ok": "ok", "abgelehnt": "achtung"}.get(eintrag["status"], "warnung")
            zeilen.append('<span class="zeit">%s</span><span class="%s">%s</span> '
                          '<span class="grau">%s</span>'
                          % (sicher(eintrag["zeit"][11:16]), klasse,
                             sicher(eintrag["werkzeug"]),
                             sicher((eintrag["ergebnis"] or "")[:90])))
        return self._panel("Was Jarvis getan hat",
                           self._liste(zeilen, "Noch nichts ausgeführt."), "breit")

    def _panel_zeitplan(self, daten: dict) -> str:
        eintraege = daten.get("zeitplan") or []
        zeilen = ['<span class="zeit">%s</span>%s' % (sicher(e["uhrzeit"]),
                                                      sicher(e["beschreibung"]))
                  for e in eintraege]
        routinen = daten.get("routinen") or {}
        inhalt = self._liste(zeilen, "Nichts geplant.")
        if routinen.get("anzahl"):
            inhalt += ('<p class="grau" style="margin-top:8px">%d Routinen: %s</p>'
                       % (routinen["anzahl"],
                          sicher(", ".join(routinen.get("namen", [])))))
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

    # -- Kopfleiste ---------------------------------------------------------

    def _ticker(self, daten: dict) -> str:
        """Die Laufleiste ganz oben - nur echte Zahlen."""
        teile = []
        monat = daten.get("monat")
        if monat:
            teile.append("Ergebnis Monat <b>%s</b>" % euro(monat["ergebnis"]))
            teile.append("Zahllast <b>%s</b>" % euro(monat["zahllast"]))
        quote = (daten.get("belegquote") or {}).get("quote")
        if quote is not None:
            marke = "b" if quote >= 90 else "b class=\"rot\""
            teile.append("Belegquote <%s>%d%%</b>" % (marke, round(quote)))
        bedarf = daten.get("bedarf")
        if bedarf and bedarf.get("berechenbar"):
            if bedarf.get("luecke") is not None and bedarf["luecke"] > 0:
                teile.append('Es fehlen <b class="rot">%s</b> je Monat'
                             % euro(bedarf["luecke"]))
            else:
                teile.append("Nötig <b>%s</b> je Monat"
                             % euro(bedarf["noetiger_umsatz"]))
        pipeline = daten.get("pipeline")
        if pipeline and pipeline.get("ok") and pipeline.get("offen"):
            teile.append("Gesichert <b>%s</b> je Monat"
                         % euro(pipeline["laufender_umsatz_monat"]))
            teile.append("Pipeline <b>%s</b> realistisch"
                         % euro(pipeline["gewichteter_wert_monat"]))
        nachfassen = daten.get("nachfassen")
        if nachfassen and nachfassen.get("anzahl"):
            teile.append('Nachfassen <b class="rot">%d</b>' % nachfassen["anzahl"])
        leads = daten.get("leads")
        if leads and leads.get("anzahl"):
            teile.append("Offene Leads <b>%d</b> über <b>%s</b>"
                         % (leads["anzahl"], euro(leads.get("volumen_offen", 0))))
        belege = daten.get("belege")
        if belege and belege.get("anzahl"):
            teile.append('Belege fehlen <b class="rot">%d</b>' % belege["anzahl"])
        punkte = daten.get("punkte") or []
        teile.append("Offene Punkte <b>%d</b>" % len(punkte))
        if not teile:
            teile.append("Jarvis ist bereit")
        return "".join("<span>%s</span>" % teil for teil in teile)

    def _kopf(self, daten: dict, seite: str = "cockpit") -> tuple:
        """Überschrift links, Navigation rechts."""
        links = ('<div><h1>Jarvis <span>// Command Center</span></h1>'
                 '<p>%s, %s &middot; Stand %s Uhr &middot; %s</p></div>'
                 % (sicher(daten["wochentag"]), sicher(daten["datum"]),
                    sicher(daten["uhrzeit"]), sicher(daten["firma"])))
        rechts = ('<nav><a class="%s" href="dashboard.html">Cockpit</a>'
                  '<a class="%s" href="sales.html">Sales-Analyse</a></nav>'
                  % ("aktiv" if seite == "cockpit" else "",
                     "aktiv" if seite == "sales" else ""))
        return links, rechts

    # -- Bauen --------------------------------------------------------------

    def bauen(self, mit_netz: bool = False) -> dict:
        """Erzeugt ``dashboard.html`` und ``data.json``."""
        daten = self.daten_sammeln(mit_netz)
        panels = "".join(teil for teil in [
            self._panel_belegquote(daten),
            self._panel_zahlen(daten),
            self._panel_bedarf(daten),
            self._panel_erinnerungen(daten),
            self._panel_verlauf(daten),
            self._panel_vertrieb(daten),
            self._panel_pipeline(daten),
            self._panel_nachfassen(daten),
            self._panel_cashflow(daten),
            self._panel_leads(daten),
            self._panel_termine(daten),
            self._panel_offen(daten),
            self._panel_belege(daten),
            self._panel_kategorien(daten),
            self._panel_fixkosten(daten),
            self._panel_mail(daten),
            self._panel_notizen(daten),
            self._panel_protokoll(daten),
            self._panel_team(daten),
            self._panel_zeitplan(daten),
            self._panel_dienste(daten),
        ] if teil)

        links, rechts = self._kopf(daten, "cockpit")
        seite = seite_bauen(
            "Jarvis Command Center", self._ticker(daten), links, rechts,
            '<div class="raster">%s</div>' % panels,
            "Diese Seite aktualisiert sich alle 60 Sekunden von selbst. "
            "Gezeigt wird ausschließlich, was wirklich erfasst ist - "
            "leere Bereiche sind leer, nicht geschätzt.<br>"
            "Alle Daten liegen lokal auf diesem Rechner.")

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
        sales = self.verkaufsansicht.bauen()
        if not sales.get("ok"):
            print("[dashboard] Sales-Analyse: %s" % sales.get("fehler"))

        return {"ok": True, "datei": str(html_pfad), "daten": str(json_pfad),
                "sales": sales.get("datei", ""),
                "text": "Das Command Center ist gebaut: %s%s"
                        % (html_pfad,
                           ("  Sales-Analyse: %s" % sales["datei"])
                           if sales.get("ok") else "")}
