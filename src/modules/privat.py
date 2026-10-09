#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Privat - das Leben neben der Firma, und wie beides zusammenhängt.

Ein Einzelunternehmer hat kein Gehalt. Er hat Umsatz, davon gehen Kosten und
Steuern ab, und was übrig bleibt, muss die Miete zahlen. Genau diese Rechnung
macht kaum jemand - und deshalb weiß kaum jemand, wie viel der Betrieb
eigentlich abwerfen **muss**.

Das ist die Aufgabe dieses Moduls:

* Private Fixkosten und Firmenfixkosten getrennt führen, denn beim
  Steuerberater dürfen sie sich nicht vermischen.
* Daraus den **nötigen Monatsumsatz** ausrechnen: was hereinkommen muss, damit
  nach Kosten und Steuerrücklage das Private gedeckt ist.
* Erinnerungen an das, was einmal im Jahr kommt und trotzdem jedes Jahr
  überrascht: Versicherung, Pickerl, Geburtstage, Vorauszahlung.
"""

from datetime import datetime, timedelta

import config
from modules.memory import (Memory, datum_sprechen, datum_verstehen, db_schema_anlegen,
                            heute_datum, zeitstempel)

SCHEMA_PRIVAT = """
CREATE TABLE IF NOT EXISTS fixkosten (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    betrag REAL NOT NULL,
    rhythmus TEXT DEFAULT 'monatlich',
    bereich TEXT DEFAULT 'privat',
    kategorie TEXT DEFAULT '',
    faellig_am TEXT DEFAULT '',
    aktiv INTEGER DEFAULT 1,
    notiz TEXT DEFAULT '',
    angelegt TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS erinnerungen (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    was TEXT NOT NULL,
    datum TEXT NOT NULL,
    wiederholung TEXT DEFAULT 'einmalig',
    bereich TEXT DEFAULT 'privat',
    notiz TEXT DEFAULT '',
    erledigt INTEGER DEFAULT 0,
    angelegt TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_erinnerungen_datum ON erinnerungen(datum);
"""

# Wie oft etwas anfällt, umgerechnet auf einen Monat.
RHYTHMEN = {
    "woechentlich": 4.333, "wöchentlich": 4.333,
    "monatlich": 1.0,
    "zweimonatlich": 0.5,
    "quartalsweise": 1 / 3.0, "vierteljaehrlich": 1 / 3.0, "vierteljährlich": 1 / 3.0,
    "halbjaehrlich": 1 / 6.0, "halbjährlich": 1 / 6.0,
    "jaehrlich": 1 / 12.0, "jährlich": 1 / 12.0,
}
BEREICHE = ("privat", "firma")
WIEDERHOLUNGEN = ("einmalig", "monatlich", "jaehrlich")


def monatsanteil(betrag: float, rhythmus: str) -> float:
    """Rechnet einen Betrag auf den Monat um."""
    try:
        betrag = float(betrag)
    except (TypeError, ValueError):
        return 0.0
    faktor = RHYTHMEN.get((rhythmus or "monatlich").strip().lower(), 1.0)
    return round(betrag * faktor, 2)


def euro_privat(betrag) -> str:
    """Deutscher Betrag mit Euro-Zeichen."""
    try:
        betrag = float(betrag)
    except (TypeError, ValueError):
        betrag = 0.0
    return ("{:,.2f}".format(betrag).replace(",", "#").replace(".", ",")
            .replace("#", ".")) + " €"


class Privat:
    """Fixkosten, Erinnerungen und die Brücke zwischen Firma und Privatleben."""

    def __init__(self, memory: Memory = None, steuersatz: float = None):
        self.memory = memory or Memory()
        # Rücklage für Einkommensteuer und Sozialversicherung zusammen.
        self.steuersatz = float(steuersatz if steuersatz is not None
                                else config.STEUER_RUECKLAGE)
        db_schema_anlegen(SCHEMA_PRIVAT, self.memory.db_pfad)

    # -- Fixkosten ----------------------------------------------------------

    def fixkosten_anlegen(self, name: str, betrag: float,
                          rhythmus: str = "monatlich", bereich: str = "privat",
                          kategorie: str = "", faellig_am: str = "",
                          notiz: str = "") -> dict:
        """Trägt eine wiederkehrende Verpflichtung ein."""
        name = (name or "").strip()
        if not name:
            return {"ok": False, "fehler": "Die Fixkosten brauchen einen Namen."}
        try:
            betrag = round(float(betrag), 2)
        except (TypeError, ValueError):
            return {"ok": False, "fehler": "Der Betrag ist keine Zahl."}
        if betrag <= 0:
            return {"ok": False, "fehler": "Der Betrag muss größer als null sein."}
        rhythmus = (rhythmus or "monatlich").strip().lower()
        if rhythmus not in RHYTHMEN:
            return {"ok": False,
                    "fehler": "Den Rhythmus '%s' kenne ich nicht. Möglich: %s."
                              % (rhythmus, ", ".join(sorted(set(RHYTHMEN))))}
        bereich = (bereich or "privat").strip().lower()
        if bereich not in BEREICHE:
            return {"ok": False,
                    "fehler": "Der Bereich muss privat oder firma sein."}

        vorhanden = self.memory._lesen(
            "SELECT id FROM fixkosten WHERE lower(name)=lower(?) AND bereich=? "
            "AND aktiv=1 LIMIT 1", (name, bereich))
        if vorhanden:
            self.memory._schreiben(
                "UPDATE fixkosten SET betrag=?, rhythmus=?, kategorie=?, "
                "faellig_am=?, notiz=? WHERE id=?",
                (betrag, rhythmus, kategorie, faellig_am, notiz, vorhanden[0]["id"]))
            nummer, geaendert = vorhanden[0]["id"], True
        else:
            nummer = self.memory._schreiben(
                "INSERT INTO fixkosten (name, betrag, rhythmus, bereich, kategorie, "
                "faellig_am, aktiv, notiz, angelegt) VALUES (?,?,?,?,?,?,1,?,?)",
                (name, betrag, rhythmus, bereich, kategorie, faellig_am, notiz,
                 zeitstempel()))
            geaendert = False

        je_monat = monatsanteil(betrag, rhythmus)
        return {"ok": True, "id": nummer, "je_monat": je_monat,
                "text": "%s %s: %s %s, das sind %s im Monat."
                        % ("Geändert" if geaendert else "Eingetragen",
                           name, euro_privat(betrag), rhythmus,
                           euro_privat(je_monat))}

    def fixkosten_streichen(self, name: str, bereich: str = "") -> dict:
        """Setzt eine Verpflichtung auf inaktiv."""
        bedingung = "lower(name)=lower(?) AND aktiv=1"
        werte = [name]
        if bereich:
            bedingung += " AND bereich=?"
            werte.append(bereich.lower())
        zeilen = self.memory._lesen(
            "SELECT * FROM fixkosten WHERE %s" % bedingung, tuple(werte))
        if not zeilen:
            return {"ok": False, "fehler": "'%s' steht nicht in den Fixkosten." % name}
        for zeile in zeilen:
            self.memory._schreiben("UPDATE fixkosten SET aktiv=0 WHERE id=?",
                                   (zeile["id"],))
        return {"ok": True,
                "text": "%s ist gestrichen. Das spart %s im Monat."
                        % (zeilen[0]["name"],
                           euro_privat(sum(monatsanteil(z["betrag"], z["rhythmus"])
                                           for z in zeilen)))}

    def fixkosten(self, bereich: str = "") -> dict:
        """Alle laufenden Verpflichtungen, auf den Monat gerechnet."""
        if bereich:
            zeilen = self.memory._lesen(
                "SELECT * FROM fixkosten WHERE aktiv=1 AND bereich=? ORDER BY betrag DESC",
                (bereich.lower(),))
        else:
            zeilen = self.memory._lesen(
                "SELECT * FROM fixkosten WHERE aktiv=1 ORDER BY bereich, betrag DESC")

        eintraege, privat_summe, firma_summe = [], 0.0, 0.0
        for zeile in zeilen:
            je_monat = monatsanteil(zeile["betrag"], zeile["rhythmus"])
            eintraege.append({"id": zeile["id"], "name": zeile["name"],
                              "betrag": zeile["betrag"], "rhythmus": zeile["rhythmus"],
                              "bereich": zeile["bereich"], "je_monat": je_monat,
                              "faellig_am": zeile["faellig_am"]})
            if zeile["bereich"] == "firma":
                firma_summe += je_monat
            else:
                privat_summe += je_monat

        return {"ok": True, "eintraege": eintraege, "anzahl": len(eintraege),
                "privat_je_monat": round(privat_summe, 2),
                "firma_je_monat": round(firma_summe, 2),
                "gesamt_je_monat": round(privat_summe + firma_summe, 2),
                "text": ("Privat %s im Monat, Firma %s, zusammen %s."
                         % (euro_privat(privat_summe), euro_privat(firma_summe),
                            euro_privat(privat_summe + firma_summe))) if eintraege
                        else "Es sind noch keine Fixkosten erfasst."}

    # -- Die entscheidende Rechnung ----------------------------------------

    def bedarfsrechnung(self, akquise=None) -> dict:
        """Wie viel Umsatz der Betrieb monatlich braucht, damit privat alles gedeckt ist.

        Der Weg rückwärts vom Privatleben zum Umsatz::

            Umsatz netto - Firmenkosten           = Gewinn
            Gewinn - Steuerrücklage               = was entnommen werden kann
            das muss mindestens die Privatkosten decken

        Aufgelöst nach Umsatz::

            Umsatz = Firmenkosten + Privatkosten / (1 - Steuersatz)

        Das ist die Zahl, die ein Einzelunternehmer eigentlich täglich kennen
        müsste und fast nie kennt.
        """
        kosten = self.fixkosten()
        privat = kosten["privat_je_monat"]
        firma = kosten["firma_je_monat"]
        anteil = max(0.0, min(0.9, self.steuersatz / 100.0))

        if privat <= 0 and firma <= 0:
            return {"ok": True, "berechenbar": False,
                    "text": "Ich kenne deine Fixkosten noch nicht. Sag mir, was "
                            "monatlich fix rausgeht - Miete, Versicherungen, Auto, "
                            "Telefon - dann rechne ich aus, was der Betrieb "
                            "abwerfen muss."}

        noetiger_umsatz = firma + (privat / (1.0 - anteil) if anteil < 1 else privat)
        noetiger_umsatz = round(noetiger_umsatz, 2)
        gewinn = round(noetiger_umsatz - firma, 2)
        steuer = round(gewinn * anteil, 2)

        gesichert = None
        luecke = None
        if akquise is not None:
            try:
                pipeline = akquise.pipeline()
                gesichert = pipeline["laufender_umsatz_monat"]
                luecke = round(noetiger_umsatz - gesichert, 2)
            except Exception:
                gesichert = None

        text = ("Damit privat alles gedeckt ist, muss der Betrieb %s netto im Monat "
                "machen. Davon gehen %s Firmenkosten ab, bleiben %s Gewinn, davon "
                "%s Steuerrücklage bei %g Prozent - übrig bleiben die %s, die du "
                "privat brauchst."
                % (euro_privat(noetiger_umsatz), euro_privat(firma),
                   euro_privat(gewinn), euro_privat(steuer), self.steuersatz,
                   euro_privat(privat)))
        if gesichert is not None:
            if luecke > 0:
                text += (" Gesichert laufen %s. Dir fehlen %s im Monat - das sind "
                         "etwa %s im Jahr."
                         % (euro_privat(gesichert), euro_privat(luecke),
                            euro_privat(luecke * 12)))
            else:
                text += (" Gesichert laufen %s, du liegst %s darüber."
                         % (euro_privat(gesichert), euro_privat(-luecke)))

        return {"ok": True, "berechenbar": True,
                "privat_je_monat": privat, "firma_je_monat": firma,
                "steuersatz": self.steuersatz,
                "noetiger_umsatz": noetiger_umsatz,
                "gewinn": gewinn, "steuerruecklage": steuer,
                "gesichert": gesichert, "luecke": luecke,
                "text": text}

    # -- Erinnerungen -------------------------------------------------------

    def erinnerung_anlegen(self, was: str, datum: str,
                           wiederholung: str = "einmalig",
                           bereich: str = "privat", notiz: str = "") -> dict:
        """Merkt sich etwas mit Datum - auch jährlich wiederkehrend."""
        was = (was or "").strip()
        if not was:
            return {"ok": False, "fehler": "Woran soll ich erinnern?"}
        datum = datum_verstehen(datum)  # "morgen", "Freitag", "12.10." gehen auch
        try:
            datetime.strptime(datum, "%Y-%m-%d")
        except ValueError:
            return {"ok": False,
                    "fehler": "Das Datum muss als JJJJ-MM-TT kommen, bekommen habe "
                              "ich '%s'." % datum}
        wiederholung = (wiederholung or "einmalig").strip().lower()
        if wiederholung not in WIEDERHOLUNGEN:
            return {"ok": False,
                    "fehler": "Die Wiederholung muss %s sein."
                              % " oder ".join(WIEDERHOLUNGEN)}
        nummer = self.memory._schreiben(
            "INSERT INTO erinnerungen (was, datum, wiederholung, bereich, notiz, "
            "erledigt, angelegt) VALUES (?,?,?,?,?,0,?)",
            (was, datum, wiederholung, (bereich or "privat").lower(), notiz,
             zeitstempel()))
        return {"ok": True, "id": nummer,
                "text": ("Gemerkt: %s %s%s" % (was, datum_sprechen(datum),
                         (", %s" % {"jaehrlich": "jedes Jahr", "monatlich": "jeden Monat",
                                    "woechentlich": "jede Woche"}.get(wiederholung, wiederholung))
                         if wiederholung != "einmalig" else "")).rstrip(".") + "."}

    def _naechster_termin(self, zeile, ab: datetime):
        """Wann eine Erinnerung das nächste Mal fällig ist."""
        try:
            datum = datetime.strptime(zeile["datum"], "%Y-%m-%d")
        except (ValueError, TypeError):
            return None
        if zeile["wiederholung"] == "jaehrlich":
            kandidat = datum.replace(year=ab.year)
            if kandidat.date() < ab.date():
                kandidat = datum.replace(year=ab.year + 1)
            return kandidat
        if zeile["wiederholung"] == "monatlich":
            kandidat = datum
            while kandidat.date() < ab.date():
                jahr = kandidat.year + (1 if kandidat.month == 12 else 0)
                monat = 1 if kandidat.month == 12 else kandidat.month + 1
                tag = min(kandidat.day, 28)
                kandidat = kandidat.replace(year=jahr, month=monat, day=tag)
            return kandidat
        return datum

    def erinnerungen_faellig(self, tage: int = 14, ab: str = "") -> dict:
        """Was in den nächsten Tagen ansteht."""
        heute = datetime.strptime(ab, "%Y-%m-%d") if ab else datetime.now()
        grenze = heute + timedelta(days=max(1, int(tage or 14)))
        zeilen = self.memory._lesen("SELECT * FROM erinnerungen WHERE erledigt=0")

        faellig = []
        for zeile in zeilen:
            termin = self._naechster_termin(zeile, heute)
            if termin is None:
                continue
            if termin.date() > grenze.date():
                continue
            tage_hin = (termin.date() - heute.date()).days
            faellig.append({"id": zeile["id"], "was": zeile["was"],
                            "datum": termin.strftime("%Y-%m-%d"),
                            "in_tagen": tage_hin, "bereich": zeile["bereich"],
                            "wiederholung": zeile["wiederholung"],
                            "notiz": zeile["notiz"]})
        faellig.sort(key=lambda e: e["in_tagen"])

        if not faellig:
            text = "In den nächsten %d Tagen steht nichts an." % tage
        else:
            erste = faellig[0]
            wann = ("heute" if erste["in_tagen"] == 0
                    else "morgen" if erste["in_tagen"] == 1
                    else "in %d Tagen" % erste["in_tagen"]
                    if erste["in_tagen"] > 0 else "seit %d Tagen überfällig"
                    % abs(erste["in_tagen"]))
            text = ("%d Termine in den nächsten %d Tagen. Als nächstes: %s %s."
                    % (len(faellig), tage, erste["was"], wann))
        return {"ok": True, "anzahl": len(faellig), "eintraege": faellig,
                "text": text}

    def erinnerung_erledigen(self, nummer: int) -> dict:
        """Hakt eine einmalige Erinnerung ab."""
        zeilen = self.memory._lesen(
            "SELECT * FROM erinnerungen WHERE id=? AND erledigt=0", (nummer,))
        if not zeilen:
            return {"ok": False, "fehler": "Diese Erinnerung gibt es nicht."}
        if zeilen[0]["wiederholung"] != "einmalig":
            return {"ok": True,
                    "text": "%s wiederholt sich %s - ich lasse sie stehen."
                            % (zeilen[0]["was"], zeilen[0]["wiederholung"])}
        self.memory._schreiben("UPDATE erinnerungen SET erledigt=1 WHERE id=?",
                               (nummer,))
        return {"ok": True, "text": "%s ist abgehakt." % zeilen[0]["was"]}

    def uebersicht(self, akquise=None) -> dict:
        """Alles Private auf einen Blick."""
        kosten = self.fixkosten()
        bedarf = self.bedarfsrechnung(akquise)
        anstehend = self.erinnerungen_faellig(21)
        teile = [t for t in (kosten.get("text"), bedarf.get("text"),
                             anstehend.get("text")) if t]
        return {"ok": True, "fixkosten": kosten, "bedarf": bedarf,
                "erinnerungen": anstehend, "text": " ".join(teile)}
