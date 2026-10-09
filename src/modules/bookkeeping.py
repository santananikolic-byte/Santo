#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Buchhaltung - Belege per Foto, Buchungen, Auswertung, Export.

Wichtig: Jarvis führt die Buchhaltung nur vor. Die fachliche Prüfung macht der
Steuerberater. Deshalb wird lieber nachgefragt als geschätzt - ein geratener
Betrag ist in der Buchhaltung schlimmer als gar kein Eintrag.
"""

import base64
import csv
import json
import os
from datetime import datetime, timedelta

import config
from modules.memory import Memory, db_schema_anlegen, heute_datum, zeitstempel

SCHEMA_BUCHHALTUNG = """
CREATE TABLE IF NOT EXISTS buchungen (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    art TEXT NOT NULL,
    datum TEXT NOT NULL,
    betrag_brutto REAL NOT NULL,
    mwst_satz REAL DEFAULT 0,
    mwst_betrag REAL DEFAULT 0,
    netto REAL DEFAULT 0,
    haendler TEXT DEFAULT '',
    kategorie TEXT DEFAULT 'Sonstiges',
    zahlungsart TEXT DEFAULT '',
    positionen TEXT DEFAULT '',
    beleg_pfad TEXT DEFAULT '',
    notiz TEXT DEFAULT '',
    angelegt TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_buchungen_datum ON buchungen(datum);
"""

# Kategorien, wie sie in der Gebäudereinigung tatsächlich anfallen.
MONATSKUERZEL = ["Jan", "Feb", "Mär", "Apr", "Mai", "Jun",
                 "Jul", "Aug", "Sep", "Okt", "Nov", "Dez"]

KATEGORIEN = [
    "Reinigungsmittel", "Arbeitsmaterial", "Fahrzeug", "Kraftstoff",
    "Versicherung", "Miete", "Telefon und Internet", "Werbung", "Fortbildung",
    "Bürobedarf", "Gebühren", "Sonstiges",
]

BELEG_PROMPT = """Du liest einen Beleg für die Buchhaltung eines Gebäudereinigers.

Gib ausschließlich JSON zurück, ohne Fließtext, mit genau diesen Schlüsseln:
  haendler        Name des Geschäfts, Text
  datum           JJJJ-MM-TT
  brutto          Bruttobetrag als Zahl
  mwst_satz       Steuersatz in Prozent als Zahl (z.B. 20)
  mwst_betrag     ausgewiesener Steuerbetrag als Zahl, sonst null
  netto           Nettobetrag als Zahl, sonst null
  kategorie       eine aus: %s
  zahlungsart     bar, Karte, Überweisung oder unbekannt
  positionen      Liste von Objekten mit bezeichnung und betrag
  sicher          true nur wenn Händler, Datum und Bruttobetrag zweifelsfrei lesbar sind
  hinweis         wenn sicher false ist: was genau fehlt oder unleserlich ist

Rate nie einen Betrag. Ist etwas unleserlich, setze sicher auf false und
schreibe in hinweis, was du nicht erkennen konntest.""" % ", ".join(KATEGORIEN)


def mwst_aus_brutto(brutto: float, satz: float) -> float:
    """Rechnet die enthaltene Mehrwertsteuer aus einem Bruttobetrag heraus."""
    try:
        brutto = float(brutto)
        satz = float(satz)
    except (TypeError, ValueError):
        return 0.0
    if satz <= 0:
        return 0.0
    return round(brutto - brutto / (1.0 + satz / 100.0), 2)


def geld(betrag) -> str:
    """Formatiert einen Betrag deutsch: 1.234,56 Euro."""
    try:
        betrag = float(betrag)
    except (TypeError, ValueError):
        return "0,00 Euro"
    text = "{:,.2f}".format(betrag).replace(",", "#").replace(".", ",").replace("#", ".")
    return "%s Euro" % text


class Bookkeeping:
    """Führt Einnahmen und Ausgaben, wertet aus und exportiert für den Steuerberater."""

    def __init__(self, memory: Memory = None):
        self.memory = memory or Memory()
        db_schema_anlegen(SCHEMA_BUCHHALTUNG, self.memory.db_pfad)

    # -- Buchen -------------------------------------------------------------

    def buchung_eintragen(self, art: str, datum: str, betrag: float, haendler: str = "",
                          kategorie: str = "Sonstiges", mwst_satz: float = None,
                          mwst_betrag: float = None, zahlungsart: str = "",
                          positionen=None, beleg_pfad: str = "", notiz: str = "") -> dict:
        """Trägt eine Einnahme oder Ausgabe ein und rechnet die Steuer sauber aus."""
        art = (art or "").strip().lower()
        if art not in ("einnahme", "ausgabe"):
            return {"ok": False, "fehler": "Die Art muss einnahme oder ausgabe sein."}
        try:
            brutto = round(float(betrag), 2)
        except (TypeError, ValueError):
            return {"ok": False, "fehler": "Der Betrag ist keine gültige Zahl."}
        if brutto <= 0:
            return {"ok": False, "fehler": "Der Betrag muss größer als null sein."}

        datum = (datum or heute_datum()).strip()
        try:
            datetime.strptime(datum, "%Y-%m-%d")
        except ValueError:
            return {"ok": False,
                    "fehler": "Das Datum muss im Format JJJJ-MM-TT stehen, bekommen habe ich '%s'." % datum}

        satz = config.STANDARD_MWST if mwst_satz is None else mwst_satz
        try:
            satz = float(satz)
        except (TypeError, ValueError):
            satz = float(config.STANDARD_MWST)

        if mwst_betrag is None or str(mwst_betrag).strip() == "":
            steuer = mwst_aus_brutto(brutto, satz)
        else:
            try:
                steuer = round(float(mwst_betrag), 2)
            except (TypeError, ValueError):
                steuer = mwst_aus_brutto(brutto, satz)
        netto = round(brutto - steuer, 2)

        if kategorie not in KATEGORIEN:
            kategorie = kategorie if kategorie else "Sonstiges"

        try:
            positionen_text = json.dumps(positionen or [], ensure_ascii=False)
        except (TypeError, ValueError):
            positionen_text = "[]"

        nummer = self.memory._schreiben(
            "INSERT INTO buchungen (art, datum, betrag_brutto, mwst_satz, mwst_betrag, netto, "
            "haendler, kategorie, zahlungsart, positionen, beleg_pfad, notiz, angelegt) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (art, datum, brutto, satz, steuer, netto, haendler, kategorie, zahlungsart,
             positionen_text, beleg_pfad, notiz, zeitstempel()))

        return {"ok": True, "id": nummer, "art": art, "datum": datum, "brutto": brutto,
                "mwst_satz": satz, "mwst_betrag": steuer, "netto": netto,
                "haendler": haendler, "kategorie": kategorie,
                "text": "%s über %s bei %s am %s eingetragen, davon %s Steuer."
                        % (art.capitalize(), geld(brutto), haendler or "unbekannt", datum,
                           geld(steuer))}

    def buchung_loeschen(self, nummer: int) -> bool:
        """Löscht eine Buchung anhand ihrer Nummer."""
        if not self.memory._lesen("SELECT id FROM buchungen WHERE id=?", (nummer,)):
            return False
        self.memory._schreiben("DELETE FROM buchungen WHERE id=?", (nummer,))
        return True

    def buchungen(self, von: str = "", bis: str = "", art: str = "", limit: int = 200) -> list:
        """Listet Buchungen in einem Zeitraum."""
        bedingungen, werte = [], []
        if von:
            bedingungen.append("datum>=?")
            werte.append(von)
        if bis:
            bedingungen.append("datum<=?")
            werte.append(bis)
        if art:
            bedingungen.append("art=?")
            werte.append(art)
        wo = ("WHERE " + " AND ".join(bedingungen)) if bedingungen else ""
        werte.append(limit)
        return self.memory._lesen(
            "SELECT * FROM buchungen %s ORDER BY datum DESC, id DESC LIMIT ?" % wo, tuple(werte))

    # -- Beleg per Foto -----------------------------------------------------

    def beleg_erfassen(self, bildpfad: str, agent=None) -> dict:
        """Liest einen Beleg vom Foto und trägt ihn ein - aber nur, wenn er sicher ist."""
        if not bildpfad or not os.path.exists(bildpfad):
            return {"ok": False,
                    "fehler": "Ich finde die Bilddatei nicht: %s" % bildpfad}
        if agent is None or not getattr(agent, "einsatzbereit", lambda: False)():
            return {"ok": False,
                    "fehler": "Ohne eingerichtetes Gehirn kann ich keinen Beleg lesen. "
                              "Bitte zuerst die Einrichtung durchlaufen."}
        try:
            with open(bildpfad, "rb") as datei:
                rohbild = base64.b64encode(datei.read()).decode("ascii")
        except OSError as fehler:
            return {"ok": False, "fehler": "Die Bilddatei ist nicht lesbar: %s" % fehler}

        endung = os.path.splitext(bildpfad)[1].lower()
        medientyp = {".png": "image/png", ".gif": "image/gif",
                     ".webp": "image/webp"}.get(endung, "image/jpeg")

        antwort = agent.json_anfrage(BELEG_PROMPT, bild_base64=rohbild, bild_typ=medientyp)
        if not antwort.get("ok"):
            return {"ok": False, "fehler": antwort.get("fehler", "Der Beleg war nicht lesbar.")}

        daten = antwort["daten"]
        if not daten.get("sicher"):
            hinweis = daten.get("hinweis") or "Ich konnte den Beleg nicht zweifelsfrei lesen."
            return {"ok": False, "eingetragen": False, "sicher": False, "hinweis": hinweis,
                    "rohdaten": daten,
                    "text": "Ich trage nichts ein. %s Sag mir die fehlenden Angaben, "
                            "dann buche ich es." % hinweis}

        ergebnis = self.buchung_eintragen(
            art="ausgabe",
            datum=str(daten.get("datum") or heute_datum()),
            betrag=daten.get("brutto"),
            haendler=str(daten.get("haendler") or ""),
            kategorie=str(daten.get("kategorie") or "Sonstiges"),
            mwst_satz=daten.get("mwst_satz"),
            mwst_betrag=daten.get("mwst_betrag"),
            zahlungsart=str(daten.get("zahlungsart") or ""),
            positionen=daten.get("positionen"),
            beleg_pfad=bildpfad)
        ergebnis["sicher"] = True
        return ergebnis

    # -- Auswertung ---------------------------------------------------------

    def auswertung(self, von: str = "", bis: str = "") -> dict:
        """Einnahmen, Ausgaben, Ergebnis, Vorsteuer, Umsatzsteuer und Zahllast."""
        if not von and not bis:
            von = datetime.now().strftime("%Y-%m-01")
            bis = heute_datum()
        zeilen = self.buchungen(von, bis, limit=100000)

        einnahmen = sum(z["betrag_brutto"] for z in zeilen if z["art"] == "einnahme")
        ausgaben = sum(z["betrag_brutto"] for z in zeilen if z["art"] == "ausgabe")
        umsatzsteuer = sum(z["mwst_betrag"] for z in zeilen if z["art"] == "einnahme")
        vorsteuer = sum(z["mwst_betrag"] for z in zeilen if z["art"] == "ausgabe")

        nach_kategorie = {}
        for zeile in zeilen:
            if zeile["art"] != "ausgabe":
                continue
            nach_kategorie.setdefault(zeile["kategorie"], 0.0)
            nach_kategorie[zeile["kategorie"]] += zeile["betrag_brutto"]
        nach_kategorie = {k: round(v, 2) for k, v in
                          sorted(nach_kategorie.items(), key=lambda p: -p[1])}

        ergebnis = {
            "ok": True,
            "von": von, "bis": bis, "anzahl": len(zeilen),
            "einnahmen": round(einnahmen, 2),
            "ausgaben": round(ausgaben, 2),
            "ergebnis": round(einnahmen - ausgaben, 2),
            "umsatzsteuer": round(umsatzsteuer, 2),
            "vorsteuer": round(vorsteuer, 2),
            "zahllast": round(umsatzsteuer - vorsteuer, 2),
            "nach_kategorie": nach_kategorie,
        }
        ergebnis["text"] = (
            "Vom %s bis %s: Einnahmen %s, Ausgaben %s, Ergebnis %s. "
            "Umsatzsteuer %s, Vorsteuer %s, Zahllast %s."
            % (von, bis, geld(ergebnis["einnahmen"]), geld(ergebnis["ausgaben"]),
               geld(ergebnis["ergebnis"]), geld(ergebnis["umsatzsteuer"]),
               geld(ergebnis["vorsteuer"]), geld(ergebnis["zahllast"])))
        return ergebnis

    def fehlende_belege(self, von: str = "", bis: str = "") -> dict:
        """Ausgaben ohne hinterlegtes Belegfoto - genau die fehlen beim Steuerberater."""
        zeilen = self.buchungen(von, bis, art="ausgabe", limit=100000)
        ohne = []
        for zeile in zeilen:
            pfad = (zeile["beleg_pfad"] or "").strip()
            if not pfad or not os.path.exists(pfad):
                ohne.append({"id": zeile["id"], "datum": zeile["datum"],
                             "haendler": zeile["haendler"], "betrag": zeile["betrag_brutto"],
                             "kategorie": zeile["kategorie"],
                             "grund": "kein Foto hinterlegt" if not pfad
                                      else "Datei nicht mehr vorhanden"})
        summe = round(sum(e["betrag"] for e in ohne), 2)
        if not ohne:
            text = "Zu allen Ausgaben liegt ein Beleg vor."
        else:
            text = ("%d Ausgaben ohne Beleg, zusammen %s. Die größte: %s bei %s am %s."
                    % (len(ohne), geld(summe),
                       geld(max(ohne, key=lambda e: e["betrag"])["betrag"]),
                       max(ohne, key=lambda e: e["betrag"])["haendler"] or "unbekannt",
                       max(ohne, key=lambda e: e["betrag"])["datum"]))
        return {"ok": True, "anzahl": len(ohne), "summe": summe, "buchungen": ohne,
                "text": text}

    def tagesverlauf(self, tage: int = 30, bis: str = "") -> dict:
        """Einnahmen und Ausgaben je Tag - die Datenreihe hinter den Sparklines.

        Tage ohne Buchung werden als null geführt, nicht ausgelassen. Sonst
        würde eine Lücke im Verlauf wie ein Anstieg aussehen.
        """
        endtag = datetime.strptime(bis, "%Y-%m-%d") if bis else datetime.now()
        starttag = endtag - timedelta(days=max(1, int(tage)) - 1)
        zeilen = self.buchungen(starttag.strftime("%Y-%m-%d"),
                                endtag.strftime("%Y-%m-%d"), limit=100000)
        einnahmen, ausgaben = {}, {}
        for zeile in zeilen:
            ziel = einnahmen if zeile["art"] == "einnahme" else ausgaben
            ziel[zeile["datum"]] = ziel.get(zeile["datum"], 0.0) + zeile["betrag_brutto"]
        tagesliste, reihe_ein, reihe_aus = [], [], []
        for versatz in range(max(1, int(tage))):
            tag = (starttag + timedelta(days=versatz)).strftime("%Y-%m-%d")
            tagesliste.append(tag)
            reihe_ein.append(round(einnahmen.get(tag, 0.0), 2))
            reihe_aus.append(round(ausgaben.get(tag, 0.0), 2))
        return {"ok": True,
                "tage": tagesliste, "einnahmen": reihe_ein, "ausgaben": reihe_aus,
                "summe_einnahmen": round(sum(reihe_ein), 2),
                "summe_ausgaben": round(sum(reihe_aus), 2)}

    def monatsverlauf(self, monate: int = 6) -> dict:
        """Ergebnis je Monat - für den Balkenvergleich."""
        jetzt = datetime.now()
        namen, werte, umsaetze = [], [], []
        for rueckwaerts in range(max(1, int(monate)) - 1, -1, -1):
            jahr = jetzt.year
            monat = jetzt.month - rueckwaerts
            while monat <= 0:
                monat += 12
                jahr -= 1
            erster = "%04d-%02d-01" % (jahr, monat)
            if monat == 12:
                letzter = "%04d-12-31" % jahr
            else:
                letzter = (datetime(jahr, monat + 1, 1) -
                           timedelta(days=1)).strftime("%Y-%m-%d")
            zeilen = self.buchungen(erster, letzter, limit=100000)
            ein = sum(z["betrag_brutto"] for z in zeilen if z["art"] == "einnahme")
            aus = sum(z["betrag_brutto"] for z in zeilen if z["art"] == "ausgabe")
            namen.append(MONATSKUERZEL[monat - 1])
            werte.append(round(ein - aus, 2))
            umsaetze.append(round(ein, 2))
        return {"ok": True, "monate": namen, "ergebnis": werte,
                "einnahmen": umsaetze}

    def belegquote(self, von: str = "", bis: str = "") -> dict:
        """Anteil der Ausgaben, zu denen ein Belegfoto vorliegt.

        Das ist die Zahl, die beim Steuerberater zählt - nicht die Anzahl der
        Buchungen, sondern wie viel Geld belegt ist.
        """
        zeilen = self.buchungen(von, bis, art="ausgabe", limit=100000)
        if not zeilen:
            return {"ok": True, "quote": None, "belegt": 0.0, "gesamt": 0.0,
                    "anzahl": 0,
                    "text": "Noch keine Ausgaben erfasst."}
        gesamt = sum(z["betrag_brutto"] for z in zeilen)
        belegt = sum(z["betrag_brutto"] for z in zeilen
                     if (z["beleg_pfad"] or "").strip()
                     and os.path.exists(z["beleg_pfad"]))
        quote = (100.0 * belegt / gesamt) if gesamt else 0.0
        return {"ok": True, "quote": round(quote, 1), "belegt": round(belegt, 2),
                "gesamt": round(gesamt, 2), "anzahl": len(zeilen),
                "text": "%.0f Prozent der Ausgaben sind belegt." % quote}

    # -- Export -------------------------------------------------------------

    def csv_export(self, von: str = "", bis: str = "", ziel: str = "") -> dict:
        """Schreibt eine CSV-Datei, die Excel auf Anhieb richtig öffnet.

        Semikolon als Trenner und ``utf-8-sig`` - sonst zerlegt Excel die Umlaute.
        """
        zeilen = self.buchungen(von, bis, limit=100000)
        try:
            config.EXPORT_VERZEICHNIS.mkdir(parents=True, exist_ok=True)
        except OSError:
            pass
        if not ziel:
            ziel = str(config.EXPORT_VERZEICHNIS /
                       ("buchhaltung_%s.csv" % datetime.now().strftime("%Y%m%d_%H%M%S")))
        kopf = ["Nummer", "Art", "Datum", "Händler", "Kategorie", "Brutto", "MwSt-Satz",
                "MwSt-Betrag", "Netto", "Zahlungsart", "Beleg vorhanden", "Notiz"]
        try:
            with open(ziel, "w", encoding="utf-8-sig", newline="") as datei:
                schreiber = csv.writer(datei, delimiter=";")
                schreiber.writerow(kopf)
                for zeile in zeilen:
                    beleg = "ja" if (zeile["beleg_pfad"] and
                                     os.path.exists(zeile["beleg_pfad"])) else "nein"
                    schreiber.writerow([
                        zeile["id"], zeile["art"], zeile["datum"], zeile["haendler"],
                        zeile["kategorie"],
                        ("%.2f" % zeile["betrag_brutto"]).replace(".", ","),
                        ("%.2f" % zeile["mwst_satz"]).replace(".", ","),
                        ("%.2f" % zeile["mwst_betrag"]).replace(".", ","),
                        ("%.2f" % zeile["netto"]).replace(".", ","),
                        zeile["zahlungsart"], beleg, zeile["notiz"]])
        except OSError as fehler:
            return {"ok": False, "fehler": "Die CSV-Datei ließ sich nicht schreiben: %s" % fehler}
        return {"ok": True, "datei": ziel, "zeilen": len(zeilen),
                "text": "%d Buchungen nach %s exportiert." % (len(zeilen), ziel)}
