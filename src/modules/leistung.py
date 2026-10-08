#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Zusammenhang zwischen Erholung und Arbeit - und die tägliche Belastungsprüfung.

Zwei Dinge, beide ehrlich:

* **Zusammenhang.** Wie viele Gespräche an Tagen mit niedriger, mittlerer und guter Erholung
  gewonnen wurden. Die Abschlussquote ist wie bei ``verkaufsmuster`` gewonnen geteilt durch
  (gewonnen + verloren) - offene und unklare Gespräche zählen nicht. Die Fallzahl steht immer
  dabei, bei zu wenig Tagen sagt Jarvis nur das. Es ist ein Zusammenhang, keine Ursache.
* **Belastungsprüfung.** Ist die Erholung heute niedrig, der morgige Tag voll, und hat sich bei
  dir niedrige Erholung bisher wirklich in schlechteren Abschlüssen gezeigt, macht Jarvis einen
  Vorschlag ("Soll ich morgen zwei Termine verschieben?"). Er schlägt nur vor: Termine ändert
  er nie selbst, absagen und verschieben fragen einzeln nach Freigabe.
"""

import math
from datetime import datetime, timedelta

import config
from modules.erholung import erholung_band, erholung_tag_datum, erholung_tag_text, sicht_teil_schreiben

# So viele Tage braucht ein Vergleich mindestens - sonst sagt Jarvis nur, dass es zu wenig ist.
ZUSAMMENHANG_MIN_TAGE = 10
ZUSAMMENHANG_MIN_STUFE = 3
# Für einen Vorschlag müssen niedrige und gute Erholungstage je so oft vorgekommen sein ...
BELASTUNG_MIN_STUFE = 5
# ... und die Abschlussquote an niedrigen Tagen mindestens so weit (als Anteil) darunter liegen.
BELASTUNG_MIN_ABSTAND = 0.15
# Die Kalender-Abfrage in Stücken dieser Größe (Tage) - ein langer Zeitraum würde gekürzt.
KALENDER_STUECK_TAGE = 14

STUFEN_NAMEN = (("rot", "niedrig"), ("gelb", "mittel"), ("gruen", "gut"))


def pearson(xs, ys):
    """Korrelationskoeffizient nach Pearson, von Hand. ``None`` bei weniger als drei Paaren oder ohne Streuung."""
    if len(xs) != len(ys) or len(xs) < 3:
        return None
    n = float(len(xs))
    mx, my = sum(xs) / n, sum(ys) / n
    sxx = sum((x - mx) ** 2 for x in xs)
    syy = sum((y - my) ** 2 for y in ys)
    if sxx < 1e-12 or syy < 1e-12:
        return None
    sxy = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    return max(-1.0, min(1.0, sxy / math.sqrt(sxx * syy)))


def verkaufstermin(titel, stichwoerter, firmen) -> bool:
    """Ist das ein Verkaufstermin? Ein Stichwort steht im Titel, oder der Titel nennt einen Interessenten."""
    text = str(titel or "").lower()
    if not text:
        return False
    for wort in stichwoerter or []:
        wort = str(wort or "").strip().lower()
        if wort and wort in text:
            return True
    for firma in firmen or []:
        firma = str(firma or "").strip().lower()
        if len(firma) >= 4 and firma in text:
            return True
    return False


def _leis_prozent(anteil) -> str:
    return "%d Prozent" % int(round(anteil * 100))


class Leistung:
    """Verbindet Erholung, Kalender und Gespräche.

    ``vorschlaege``: der Vorschlags-Speicher; ``vorschlaege_suche``: Funktion, die ihn erst zur Laufzeit
    liefert (er wird beim Aufbau der Werkzeuge nach diesem Objekt angelegt). ``anzeige``: wohin der Zusammenhang
    auf die Zentrale geht. ``uhr``: liefert die lokale Zeit als ``datetime``.
    """

    def __init__(self, memory, kalender, erholung, call_analysis, vorschlaege=None, anzeige=None, uhr=None):
        self.memory = memory
        self.kalender = kalender
        self.erholung = erholung
        self.call_analysis = call_analysis
        self.vorschlaege = vorschlaege
        self.vorschlaege_suche = None
        self.anzeige = anzeige
        self._uhr = uhr or datetime.now
        # Warum die letzte Prüfung nichts vorgeschlagen hat - für das Werkzeug, damit es ehrlich antwortet.
        self.letzter_grund = ""

    # -- Hilfen ---------------------------------------------------------------

    def _heute(self):
        return self._uhr().date()

    def _vorschlaege_holen(self):
        if self.vorschlaege is not None:
            return self.vorschlaege
        suche = self.vorschlaege_suche
        if callable(suche):
            try:
                return suche()
            except Exception:
                return None
        return None

    @staticmethod
    def _stichwoerter() -> list:
        return [w.strip().lower() for w in str(config.VERKAUFS_STICHWOERTER or "").split(",") if w.strip()]

    def _firmen(self) -> list:
        """Namen der Interessenten (Akquise) - ein Termin mit ihnen im Titel ist ein Verkaufstermin."""
        try:
            return [z["firma"] for z in self.memory._lesen("SELECT firma FROM leads WHERE firma != ''")]
        except Exception:
            return []

    # -- Kalender -------------------------------------------------------------

    def _kalender_stueck(self, ab, tage: int):
        """Termine ab ``ab`` für ``tage`` Tage. Wird ein Ergebnis gekürzt, halbiert sich das Stück."""
        ergebnis = self.kalender.termine(tage, ab=datetime(ab.year, ab.month, ab.day))
        if not ergebnis.get("ok"):
            return None, ergebnis.get("fehler") or "Der Kalender antwortet nicht."
        if ergebnis.get("gekuerzt") and tage > 1:
            halb = tage // 2
            erste, fehler = self._kalender_stueck(ab, halb)
            zweite, fehler2 = self._kalender_stueck(ab + timedelta(days=halb), tage - halb)
            if erste is None or zweite is None:
                return None, fehler or fehler2
            return erste + zweite, ""
        return list(ergebnis.get("termine") or []), ""

    def _kalender_termine(self, ab, tage: int):
        """Alle Termine von ``ab`` an für ``tage`` Tage. ``(Liste, Fehler)``; ohne Kalender ``(None, Grund)``."""
        verfuegbar = getattr(self.kalender, "verfuegbar", None)
        if callable(verfuegbar) and not verfuegbar():
            return None, "Es ist kein Kalender eingerichtet."
        alle, rest, start = [], tage, ab
        while rest > 0:
            stueck = min(KALENDER_STUECK_TAGE, rest)
            termine, fehler = self._kalender_stueck(start, stueck)
            if termine is None:
                return None, fehler
            alle += termine
            start += timedelta(days=stueck)
            rest -= stueck
        return alle, ""

    def _tageslast(self, termine) -> dict:
        """``{tag: (Termine, Verkaufstermine)}`` - ganztägige Einträge zählen nicht als Termin."""
        stichwoerter, firmen = self._stichwoerter(), self._firmen()
        last = {}
        for termin in termine or []:
            if termin.get("ganztaegig"):
                continue
            tag = erholung_tag_text(termin.get("beginn"))
            if not tag:
                continue
            anzahl, verkauf = last.get(tag, (0, 0))
            last[tag] = (anzahl + 1, verkauf + (1 if verkaufstermin(termin.get("titel"), stichwoerter, firmen) else 0))
        return last

    # -- Zusammenstellen ------------------------------------------------------

    def tage_zusammenstellen(self, tage: int = 60) -> list:
        """Eine Zeile je Tag der letzten ``tage`` Tage (bis heute): Erholung, Termine, Gespräche, Quote.

        ``erholung`` und ``termine`` sind ``None``, wo es keine Daten gibt - nie eine erfundene Null.
        ``quote`` ist gewonnen geteilt durch (gewonnen + verloren), ``None`` ohne entschiedenes Gespräch.
        ``gespraeche`` zählt alle Gespräche des Tages, ``entschieden`` nur gewonnene und verlorene.
        """
        try:
            tage = max(1, min(90, int(tage)))
        except (TypeError, ValueError):
            tage = 60
        heute = self._heute()
        ab = heute - timedelta(days=tage)
        termine, _fehler = self._kalender_termine(ab, tage + 1)
        last = self._tageslast(termine) if termine is not None else None
        erholung = {e["tag"]: e["wert"] for e in self.erholung.verlauf(tage + 1)}
        gespraeche = {}
        for zeile in self.memory._lesen("SELECT datum, ergebnis FROM gespraeche WHERE datum>=? AND datum<=?",
                                        (ab.isoformat(), heute.isoformat())):
            tag = erholung_tag_text(zeile["datum"])
            eintrag = gespraeche.setdefault(tag, {"alle": 0, "gewonnen": 0, "verloren": 0})
            eintrag["alle"] += 1
            if zeile["ergebnis"] in ("gewonnen", "verloren"):
                eintrag[zeile["ergebnis"]] += 1
        liste = []
        for i in range(tage + 1):
            tag = (ab + timedelta(days=i)).isoformat()
            g = gespraeche.get(tag, {"alle": 0, "gewonnen": 0, "verloren": 0})
            entschieden = g["gewonnen"] + g["verloren"]
            wert = erholung.get(tag)
            liste.append({
                "tag": tag,
                "erholung": wert,
                "band": erholung_band(wert) if wert is not None else None,
                "termine": last.get(tag, (0, 0))[0] if last is not None else None,
                "verkaufstermine": last.get(tag, (0, 0))[1] if last is not None else None,
                "gespraeche": g["alle"], "gewonnen": g["gewonnen"], "verloren": g["verloren"],
                "entschieden": entschieden,
                "quote": (g["gewonnen"] / float(entschieden)) if entschieden else None})
        return liste

    # -- Zusammenhang ---------------------------------------------------------

    @staticmethod
    def _stufe_rechnen(tage: list) -> dict:
        entschieden = sum(t["entschieden"] for t in tage)
        gewonnen = sum(t["gewonnen"] for t in tage)
        termine = [t["termine"] for t in tage if t["termine"] is not None]
        verkauf = [t["verkaufstermine"] for t in tage if t["verkaufstermine"] is not None]
        genug = len(tage) >= ZUSAMMENHANG_MIN_STUFE
        return {"tage": len(tage),
                "termine": round(sum(termine) / float(len(termine)), 1) if termine else None,
                "verkaufstermine": round(sum(verkauf) / float(len(verkauf)), 1) if verkauf else None,
                "gespraeche": entschieden, "gewonnen": gewonnen,
                "abschlussquote": round(gewonnen / float(entschieden), 3) if entschieden and genug else None,
                "zu_wenig": not genug}

    def zusammenhang(self, tage: int = 60, anzeigen: bool = False) -> dict:
        """Wie Erholung und Abschlussquote zusammenhängen - mit Fallzahlen, nie mit einer Ursache.

        ``anzeigen`` schreibt das Ergebnis auf die Zentrale (nur wenn ein Mensch gefragt hat).
        """
        liste = self.tage_zusammenstellen(tage)
        mit_erholung = [t for t in liste if t["erholung"] is not None]
        paare = [t for t in mit_erholung if t["quote"] is not None]
        n = len(paare)
        eimer = {"rot": [], "gelb": [], "gruen": []}
        for t in paare:
            eimer[t["band"]].append(t)
        stufen = {name: self._stufe_rechnen(eimer[name]) for name in eimer}
        tabelle = [dict(stufe=name, tage=s["tage"], termine=s["termine"], gespraeche=s["gespraeche"],
                        abschlussquote=s["abschlussquote"]) for name, s in stufen.items()]
        gesamt_g = sum(t["gewonnen"] for t in liste)
        gesamt_v = sum(t["verloren"] for t in liste)
        gesamt = {"gewonnen": gesamt_g, "verloren": gesamt_v,
                  "abschlussquote": round(gesamt_g / float(gesamt_g + gesamt_v), 3) if gesamt_g + gesamt_v else None}
        r = pearson([t["erholung"] for t in paare], [t["quote"] for t in paare]) if n >= ZUSAMMENHANG_MIN_TAGE else None
        rot, gruen = stufen["rot"], stufen["gruen"]
        genug = False
        if not mit_erholung:
            text = ("Für diese Tage habe ich noch keine Erholungswerte - zu wenig für eine Aussage. Möglich: "
                    "Apple-Health-Export, Oura oder Whoop verbinden.")
        elif n < ZUSAMMENHANG_MIN_TAGE:
            text = "%d Tage mit Erholungswert und entschiedenem Gespräch - zu wenig für eine Aussage." % n
        elif rot["zu_wenig"] or gruen["zu_wenig"]:
            text = ("%d Tage, davon %d mit niedriger und %d mit guter Erholung - zu wenig für eine Aussage "
                    "(je Gruppe mindestens %d Tage nötig)." % (n, rot["tage"], gruen["tage"], ZUSAMMENHANG_MIN_STUFE))
        else:
            genug = True
            text = ("An %d Tagen mit niedriger Erholung hast du %d von %d entschiedenen Gesprächen gewonnen, "
                    "an %d Tagen mit guter Erholung %d von %d (%d Tage insgesamt)."
                    % (rot["tage"], rot["gewonnen"], rot["gespraeche"], gruen["tage"], gruen["gewonnen"],
                       gruen["gespraeche"], n))
            if r is not None:
                text += " Korrelation r = %s." % ("%.2f" % r).replace(".", ",")
            text += " Zusammenhang, keine Ursache."
        ergebnis = {"ok": True, "n": n, "tage_mit_erholung": len(mit_erholung), "ausreichend": genug,
                    "stufen": stufen, "tabelle": tabelle, "r": None if r is None else round(r, 2),
                    "gesamt": gesamt, "text": text, "hinweis": "Zusammenhang, keine Ursache."}
        if anzeigen:
            sicht_teil_schreiben(self.anzeige, {"zusammenhang": {"text": text, "n": n, "tabelle": tabelle}})
        return ergebnis

    # -- Belastung ------------------------------------------------------------

    def belastung_pruefen(self, heute=None) -> str:
        """Prüft, ob der morgige Tag bei der heutigen Erholung zu voll ist. Gibt einen Vorschlag zurück - oder ``''``.

        Vorgeschlagen wird nur, wenn alles zutrifft: Die Erholung von heute liegt unter ``BELASTUNG_SCHWELLE``,
        morgen stehen mindestens ``BELASTUNG_MIN_TERMINE`` Termine an, und deine Zahlen zeigen einen Unterschied
        (an mindestens fünf niedrigen und fünf guten Tagen, Abschlussquote niedrig mindestens 15 Punkte darunter).
        Der Vorschlag geht über ``vorschlaege.einbringen`` - einmal je Tag. Geändert wird nichts.
        ``letzter_grund`` sagt, warum nichts kam.
        """
        self.letzter_grund = ""
        if not config.VORSCHLAEGE_AN:
            self.letzter_grund = "Vorschläge sind ausgeschaltet (VORSCHLAEGE_AN)."
            return ""
        vorschlaege = self._vorschlaege_holen()
        if vorschlaege is None:
            self.letzter_grund = "Es gibt keinen Vorschlags-Speicher."
            return ""
        heute_datum = erholung_tag_datum(heute) or self._heute()
        tag = heute_datum.isoformat()
        # Frische Werte von Oura oder Whoop, wenn die letzten länger her sind - Fehler bleiben ohne Folgen.
        aktualisieren = getattr(self.erholung, "aktualisieren", None)
        if callable(aktualisieren):
            try:
                aktualisieren()
            except Exception as fehler:
                print("[leistung] Abruf nicht möglich: %s" % fehler)
        erholung = self.erholung.heute()
        if not erholung.get("ok") or erholung.get("tag") != tag:
            self.letzter_grund = "Ich kenne die Erholung von heute nicht."
            return ""
        wert = erholung["wert"]
        if wert >= config.BELASTUNG_SCHWELLE:
            self.letzter_grund = ("Die Erholung liegt heute bei %d von 100 - nicht unter der Schwelle von %d."
                                  % (wert, config.BELASTUNG_SCHWELLE))
            return ""
        morgen = heute_datum + timedelta(days=1)
        termine, fehler = self._kalender_termine(morgen, 1)
        if termine is None:
            self.letzter_grund = "Den Kalender von morgen kann ich nicht lesen: %s" % fehler
            return ""
        last = self._tageslast(termine).get(morgen.isoformat(), (0, 0))
        anzahl, verkauf = last
        if anzahl < config.BELASTUNG_MIN_TERMINE:
            self.letzter_grund = "Morgen stehen nur %d Termine an (ab %d wird geprüft)." % (anzahl, config.BELASTUNG_MIN_TERMINE)
            return ""
        zusammenhang = self.zusammenhang(60)
        stufen = zusammenhang.get("stufen") or {}
        rot, gruen = stufen.get("rot") or {}, stufen.get("gruen") or {}
        if (rot.get("tage", 0) < BELASTUNG_MIN_STUFE or gruen.get("tage", 0) < BELASTUNG_MIN_STUFE
                or rot.get("abschlussquote") is None or gruen.get("abschlussquote") is None):
            self.letzter_grund = ("Meine Zahlen reichen noch nicht: %d Tage mit niedriger und %d mit guter Erholung "
                                  "(je mindestens %d nötig)." % (rot.get("tage", 0), gruen.get("tage", 0), BELASTUNG_MIN_STUFE))
            return ""
        if gruen["abschlussquote"] - rot["abschlussquote"] < BELASTUNG_MIN_ABSTAND:
            self.letzter_grund = "An erholten Tagen schließt du nicht deutlich besser ab als an müden."
            return ""
        zahl = "zwei Termine" if anzahl >= 4 else "einen Termin"
        text = ("Deine Erholung liegt heute bei %d von 100. Morgen hast du %d Termine%s. An Tagen mit so niedriger "
                "Erholung hast du bisher %d von %d entschiedenen Gesprächen gewonnen, an guten Tagen %d von %d. "
                "Soll ich morgen %s verschieben oder absagen? Welche, sage ich dir vorher."
                % (wert, anzahl, (", davon %d Verkaufstermine" % verkauf) if verkauf else "",
                   rot["gewonnen"], rot["gespraeche"], gruen["gewonnen"], gruen["gespraeche"], zahl))
        ergebnis = vorschlaege.einbringen("belastung:" + tag, text, "erholung")
        if not ergebnis.get("ok"):
            self.letzter_grund = ("Vorschläge sind ausgeschaltet." if ergebnis.get("aus")
                                  else ergebnis.get("fehler", "Der Vorschlag ließ sich nicht festhalten."))
            return ""
        if ergebnis.get("doppelt"):
            self.letzter_grund = "Den Vorschlag für heute habe ich schon gemacht."
            return ""
        return text

    def belastung_job(self) -> str:
        """Für den Zeitplan: wie ``belastung_pruefen``, aber leer, wenn der Vorschlag schon laut gesagt wurde.

        Hat der Vorschlags-Speicher eine eigene Ausgabe, sagt ``einbringen`` den Text selbst - dann bliebe er
        sonst doppelt.
        """
        text = self.belastung_pruefen()
        if text and getattr(self._vorschlaege_holen(), "ausgabe", None) is not None:
            return ""
        return text
