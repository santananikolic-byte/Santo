# -*- coding: utf-8 -*-
"""Internes Simulations-Wallet (Abschnitt 6).

- KEIN Geld, keine Bank, keine Krypto-Wallet. Jede Buchung trägt simulation=1 (Datenbank erzwingt das).
- Startwert 15,00 € als SIMULATION.
- Unveränderbare Historie: Korrektur nur durch Gegenbuchung.
- Budgets und Warnungen. Ein Stand von null schaltet NICHTS ab – das Wallet hat keinen
  Einfluss auf den Systemstatus (Abschnitt 6.3).
"""

import re

from .db import jetzt, neue_id

KENNZEICHEN = "SIMULATION"
STARTWERT_CENT = 1500
ARTEN_VORZEICHEN = {
    "einnahme": 1, "reservierung_aufloesen": 1,
    "ausgabe": -1, "reservierung": -1, "gebuehr": -1,
}


def euro(cent):
    vorzeichen = "-" if cent < 0 else ""
    cent = abs(int(cent))
    euro_teil = "{:,}".format(cent // 100).replace(",", ".")   # 1250 → 1.250 (deutsche Schreibweise)
    return "%s%s,%02d €" % (vorzeichen, euro_teil, cent % 100)


def betrag_in_cent(wert):
    """Akzeptiert 12.5, '12,50', 1250 (int = Cent nur mit cent=True im Aufrufer)."""
    if isinstance(wert, bool):
        raise ValueError("Ungültiger Betrag")
    if isinstance(wert, (int, float)):
        cent = round(float(wert) * 100)
    else:
        text = str(wert).strip().replace("€", "").replace(" ", "").replace("\u00a0", "")
        if "," in text:
            text = text.replace(".", "").replace(",", ".")      # 1.234,50 → 1234.50
        elif re.fullmatch(r"\d{1,3}(\.\d{3})+", text):
            text = text.replace(".", "")                        # 1.000 → 1000 (deutsche Tausenderpunkte)
        if not re.fullmatch(r"\d+(\.\d+)?", text):
            raise ValueError("Ungültiger Betrag – bitte z. B. 12,50 eingeben")
        cent = round(float(text) * 100)
    if cent <= 0 or cent > 100_000_000:
        raise ValueError("Betrag muss zwischen 0,01 € und 1.000.000 € liegen")
    return int(cent)


class Wallet:
    def __init__(self, db, protokoll, einstellungen):
        self.db = db
        self.protokoll = protokoll
        self.einstellungen = einstellungen

    def einrichten(self):
        if self.db.wert("SELECT COUNT(*) FROM wallet_buchungen") == 0:
            self._buche(STARTWERT_CENT, "start", "startwert", "Virtueller Teststartwert (SIMULATION)", "system")

    def _buche(self, betrag_cent, kategorie, art, begruendung, akteur, gegenbuchung_zu=None):
        bid = neue_id("w_")
        with self.db.transaktion() as con:
            nr = (con.execute("SELECT COALESCE(MAX(nr),0)+1 FROM wallet_buchungen").fetchone()[0])
            con.execute("INSERT INTO wallet_buchungen (id, nr, zeit, betrag_cent, kategorie, art, begruendung,"
                        " gegenbuchung_zu, akteur) VALUES (?,?,?,?,?,?,?,?,?)",
                        (bid, nr, jetzt(), int(betrag_cent), kategorie[:60], art, begruendung[:500],
                         gegenbuchung_zu, akteur))
        self.protokoll.audit("wallet", "Simulierte Buchung", {"id": bid, "art": art, "betrag_cent": betrag_cent,
                                                               "akteur": akteur, "kennzeichen": KENNZEICHEN})
        return bid

    def buchen(self, art, betrag, kategorie, begruendung, akteur):
        if art not in ARTEN_VORZEICHEN:
            raise ValueError("Ungültige Buchungsart: %s" % art)
        if not str(begruendung).strip():
            raise ValueError("Begründung ist Pflicht.")
        if not str(kategorie).strip():
            raise ValueError("Kategorie ist Pflicht.")
        cent = betrag_in_cent(betrag) * ARTEN_VORZEICHEN[art]
        warnungen = []
        if cent < 0:
            warnungen = self._budget_warnungen(kategorie.strip(), -cent)
        bid = self._buche(cent, kategorie.strip(), art, begruendung.strip(), akteur)
        stand = self.stand_cent()
        if stand < self.einstellungen.hole("wallet_warnschwelle_cent"):
            warnungen.append("Simuliertes Guthaben niedrig: %s (nur Simulation – Kernfunktionen laufen weiter)"
                             % euro(stand))
        for w in warnungen:
            self.protokoll.warnung("wallet", w)
        return {"id": bid, "stand_cent": stand, "warnungen": warnungen, "kennzeichen": KENNZEICHEN}

    def gegenbuchung(self, buchung_id, begruendung, akteur):
        alt = self.db.eins("SELECT * FROM wallet_buchungen WHERE id=?", (buchung_id,))
        if not alt:
            raise KeyError("Buchung nicht gefunden.")
        if alt["art"] == "gegenbuchung":
            raise ValueError("Eine Gegenbuchung kann nicht erneut gegengebucht werden.")
        if self.db.eins("SELECT id FROM wallet_buchungen WHERE gegenbuchung_zu=?", (buchung_id,)):
            raise ValueError("Diese Buchung wurde bereits gegengebucht.")
        if not str(begruendung).strip():
            raise ValueError("Begründung ist Pflicht.")
        bid = self._buche(-alt["betrag_cent"], alt["kategorie"], "gegenbuchung", begruendung.strip(), akteur,
                          gegenbuchung_zu=buchung_id)
        return {"id": bid, "stand_cent": self.stand_cent(), "kennzeichen": KENNZEICHEN}

    def stand_cent(self):
        return int(self.db.wert("SELECT COALESCE(SUM(betrag_cent),0) FROM wallet_buchungen"))

    def reserviert_cent(self):
        return -int(self.db.wert("SELECT COALESCE(SUM(betrag_cent),0) FROM wallet_buchungen "
                                 "WHERE art IN ('reservierung','reservierung_aufloesen')"))

    def historie(self, grenze=500):
        return self.db.alle("SELECT * FROM wallet_buchungen ORDER BY nr DESC LIMIT ?", (grenze,))

    def _verbrauch(self, kategorie, nur_monat):
        """Summe der Ausgaben (inkl. Reservierungen, abzüglich Gegenbuchungen dazu) – positiv in Cent."""
        sql = ("SELECT COALESCE(-SUM(b.betrag_cent),0) FROM wallet_buchungen b "
               "LEFT JOIN wallet_buchungen o ON o.id=b.gegenbuchung_zu "
               "WHERE (b.art IN ('ausgabe','gebuehr','reservierung','reservierung_aufloesen') "
               "   OR (b.art='gegenbuchung' AND o.art IN ('ausgabe','gebuehr','reservierung')))")
        p = []
        if kategorie != "*":
            sql += " AND b.kategorie=?"
            p.append(kategorie)
        if nur_monat:
            sql += " AND substr(b.zeit,1,7)=?"
            p.append(jetzt()[:7])
        return int(self.db.wert(sql, p))

    def _budget_warnungen(self, kategorie, neu_cent):
        warnungen = []
        for b in self.db.alle("SELECT * FROM budgets WHERE bereich='wallet' AND kategorie IN (?, '*')",
                              (kategorie,)):
            bisher = self._verbrauch(b["kategorie"], b["zeitraum"] == "monat")
            if bisher + neu_cent > b["limit_cent"]:
                warnungen.append("Budget überschritten (SIMULATION): %s/%s – %s von %s"
                                 % (b["kategorie"], b["zeitraum"], euro(bisher + neu_cent), euro(b["limit_cent"])))
        return warnungen

    def budget_stand(self):
        return [dict(b, verbraucht_cent=self._verbrauch(b["kategorie"], b["zeitraum"] == "monat"))
                for b in self.db.alle("SELECT * FROM budgets WHERE bereich='wallet'")]

    def uebersicht(self):
        return {
            "kennzeichen": KENNZEICHEN,
            "hinweis": "Internes Simulationsguthaben – kein echtes Geld, keine Bank, keine Krypto-Wallet. "
                       "Hat keinen Einfluss auf den Systembetrieb.",
            "stand_cent": self.stand_cent(),
            "stand": euro(self.stand_cent()),
            "reserviert_cent": self.reserviert_cent(),
            "buchungen": self.db.wert("SELECT COUNT(*) FROM wallet_buchungen"),
            "budgets": self.budget_stand(),
        }
