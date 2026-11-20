# -*- coding: utf-8 -*-
"""Reale Geschäftsfinanzen – strikt getrennt vom Simulations-Wallet (Abschnitt 6.2, 7).

- Eigene Tabelle real_buchungen (Datenbank erzwingt simulation=0), Wallet-Tabelle erzwingt simulation=1.
  Eine Buchung kann also technisch nicht in beiden Bereichen landen.
- Einnahme nur mit Zahlungsnachweis UND Angabe, wer ihn geprüft hat (Datenbank-CHECK).
- Rechnungen/Angebote/erwartete Verkäufe sind Forderungen, keine Einnahmen.
- Agenten dürfen hier nichts buchen – nur der Eigentümer (über die Oberfläche).
- Keine Geldbewegung: Dieses Modul dokumentiert nur, es zahlt nichts aus.
"""

import datetime

from .db import jetzt, neue_id
from .wallet import betrag_in_cent, euro


def _datum(text):
    if not text:
        return datetime.date.today().isoformat()
    return datetime.date.fromisoformat(str(text)[:10]).isoformat()


class Finanzen:
    def __init__(self, db, protokoll):
        self.db = db
        self.protokoll = protokoll

    @staticmethod
    def _nur_eigentuemer(akteur):
        if akteur != "eigentuemer":
            raise PermissionError("Reale Finanzen bucht nur der Eigentümer.")

    def _buche(self, art, cent, kategorie, gegenpartei, begruendung, akteur, datum=None, beleg=None,
               zahlungsnachweis=None, verifiziert_von=None, forderung_id=None, gegenbuchung_zu=None):
        bid = neue_id("r_")
        with self.db.transaktion() as con:
            nr = con.execute("SELECT COALESCE(MAX(nr),0)+1 FROM real_buchungen").fetchone()[0]
            con.execute(
                "INSERT INTO real_buchungen (id, nr, zeit, datum, art, betrag_cent, kategorie, gegenpartei, beleg,"
                " zahlungsnachweis, verifiziert_von, forderung_id, gegenbuchung_zu, begruendung, akteur)"
                " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (bid, nr, jetzt(), _datum(datum), art, cent, kategorie[:60], gegenpartei[:200], beleg,
                 zahlungsnachweis, verifiziert_von, forderung_id, gegenbuchung_zu, begruendung[:500], akteur))
            if forderung_id:
                n = con.execute("UPDATE forderungen SET status='bezahlt', buchung_id=? WHERE id=? AND status='offen'",
                                (bid, forderung_id)).rowcount
                if n != 1:
                    raise ValueError("Forderung nicht offen oder nicht gefunden.")
        self.protokoll.audit("finanzen", "Reale Buchung", {"id": bid, "art": art, "betrag_cent": cent})
        return bid

    def ausgabe(self, betrag, kategorie, gegenpartei, begruendung, akteur, datum=None, beleg=None):
        self._nur_eigentuemer(akteur)
        _pflicht(kategorie=kategorie, gegenpartei=gegenpartei, begruendung=begruendung)
        return self._buche("ausgabe", -betrag_in_cent(betrag), kategorie, gegenpartei, begruendung, akteur,
                           datum, beleg)

    def einnahme(self, betrag, kategorie, gegenpartei, begruendung, akteur, zahlungsnachweis, verifiziert_von,
                 datum=None, beleg=None, forderung_id=None):
        """Nur tatsächlich eingegangene und geprüfte Zahlungen (z. B. Kontoauszug-Referenz)."""
        self._nur_eigentuemer(akteur)
        _pflicht(kategorie=kategorie, gegenpartei=gegenpartei, begruendung=begruendung,
                 zahlungsnachweis=zahlungsnachweis, verifiziert_von=verifiziert_von)
        return self._buche("einnahme", betrag_in_cent(betrag), kategorie, gegenpartei, begruendung, akteur,
                           datum, beleg, zahlungsnachweis.strip(), verifiziert_von.strip(), forderung_id)

    def gegenbuchung(self, buchung_id, begruendung, akteur):
        self._nur_eigentuemer(akteur)
        _pflicht(begruendung=begruendung)
        alt = self.db.eins("SELECT * FROM real_buchungen WHERE id=?", (buchung_id,))
        if not alt:
            raise KeyError("Buchung nicht gefunden.")
        if alt["art"] == "gegenbuchung" or self.db.eins(
                "SELECT id FROM real_buchungen WHERE gegenbuchung_zu=?", (buchung_id,)):
            raise ValueError("Bereits gegengebucht oder selbst eine Gegenbuchung.")
        return self._buche("gegenbuchung", -alt["betrag_cent"], alt["kategorie"], alt["gegenpartei"], begruendung,
                           akteur, gegenbuchung_zu=buchung_id)

    # ---- Forderungen (offen ≠ Einnahme) --------------------------------
    def forderung_anlegen(self, kunde, betrag, akteur, faellig=None, rechnung_ref=None, notiz=None):
        self._nur_eigentuemer(akteur)
        _pflicht(kunde=kunde)
        fid = neue_id("fo_")
        self.db.ausfuehren("INSERT INTO forderungen VALUES (?,?,?,?,?,?,?,?,?)",
                           (fid, jetzt(), kunde[:200], betrag_in_cent(betrag), _datum(faellig) if faellig else None,
                            rechnung_ref, "offen", None, notiz))
        self.protokoll.audit("finanzen", "Forderung angelegt (keine Einnahme)", {"id": fid})
        return fid

    def forderung_stornieren(self, fid, akteur):
        self._nur_eigentuemer(akteur)
        if not self.db.ausfuehren("UPDATE forderungen SET status='storniert' WHERE id=? AND status='offen'", (fid,)):
            raise ValueError("Forderung nicht offen oder nicht gefunden.")

    def forderung_bezahlt(self, fid, zahlungsnachweis, verifiziert_von, akteur, datum=None):
        f = self.db.eins("SELECT * FROM forderungen WHERE id=?", (fid,))
        if not f or f["status"] != "offen":
            raise ValueError("Forderung nicht offen oder nicht gefunden.")
        return self.einnahme(f["betrag_cent"] / 100, "forderung", f["kunde"], "Zahlung zu Forderung %s" % fid,
                             akteur, zahlungsnachweis, verifiziert_von, datum, f["rechnung_ref"], forderung_id=fid)

    # ---- Übersichten ---------------------------------------------------
    def uebersicht(self):
        summe = lambda sql: int(self.db.wert(sql) or 0)
        einnahmen = summe("SELECT COALESCE(SUM(betrag_cent),0) FROM real_buchungen WHERE art='einnahme'")
        ausgaben = -summe("SELECT COALESCE(SUM(betrag_cent),0) FROM real_buchungen WHERE art='ausgabe'")
        korrekturen = summe("SELECT COALESCE(SUM(betrag_cent),0) FROM real_buchungen WHERE art='gegenbuchung'")
        offen = summe("SELECT COALESCE(SUM(betrag_cent),0) FROM forderungen WHERE status='offen'")
        saldo = summe("SELECT COALESCE(SUM(betrag_cent),0) FROM real_buchungen")
        return {
            "kennzeichen": "REAL",
            "hinweis": "Nur tatsächlich eingegangene und geprüfte Zahlungen zählen als Einnahme. "
                       "Offene Forderungen sind kein Geld. Simulationswerte sind hier nie enthalten.",
            "einnahmen_verifiziert_cent": einnahmen,
            "ausgaben_cent": ausgaben,
            "korrekturen_cent": korrekturen,
            "saldo_cent": saldo,
            "saldo": euro(saldo),
            "offene_forderungen_cent": offen,
            "offene_forderungen": euro(offen),
            "budgets": self.budget_stand("real"),
        }

    def buchungen(self, grenze=500):
        return self.db.alle("SELECT * FROM real_buchungen ORDER BY nr DESC LIMIT ?", (grenze,))

    def forderungen(self):
        return self.db.alle("SELECT * FROM forderungen ORDER BY status='offen' DESC, erstellt DESC")

    # ---- Budgets (beide Bereiche, getrennt geführt) ---------------------
    def budget_setzen(self, bereich, kategorie, limit, zeitraum, akteur):
        self._nur_eigentuemer(akteur)
        if bereich not in ("wallet", "real") or zeitraum not in ("monat", "gesamt"):
            raise ValueError("Ungültiger Bereich oder Zeitraum.")
        _pflicht(kategorie=kategorie)
        cent = 0 if str(limit).strip() in ("0", "0,00", "0.00") else betrag_in_cent(limit)
        self.db.ausfuehren("INSERT INTO budgets VALUES (?,?,?,?,?,?) ON CONFLICT(bereich, kategorie, zeitraum) "
                           "DO UPDATE SET limit_cent=excluded.limit_cent",
                           (neue_id("b_"), bereich, kategorie.strip()[:60], cent, zeitraum, jetzt()))

    def budget_stand(self, bereich="real"):
        ergebnis = []
        for b in self.db.alle("SELECT * FROM budgets WHERE bereich=?", (bereich,)):
            if bereich != "real":
                continue
            sql = "SELECT COALESCE(-SUM(betrag_cent),0) FROM real_buchungen WHERE art='ausgabe'"
            p = []
            if b["kategorie"] != "*":
                sql += " AND kategorie=?"
                p.append(b["kategorie"])
            if b["zeitraum"] == "monat":
                sql += " AND substr(datum,1,7)=?"
                p.append(datetime.date.today().isoformat()[:7])
            verbraucht = int(self.db.wert(sql, p))
            ergebnis.append(dict(b, verbraucht_cent=verbraucht, ueberschritten=verbraucht > b["limit_cent"]))
        return ergebnis

    def liquiditaet(self, tage=30):
        """Einfache Vorschau: Saldo + offene Forderungen, die im Zeitraum fällig sind (als ERWARTET markiert)."""
        bis = (datetime.date.today() + datetime.timedelta(days=tage)).isoformat()
        erwartet = int(self.db.wert("SELECT COALESCE(SUM(betrag_cent),0) FROM forderungen WHERE status='offen' "
                                    "AND (faellig IS NULL OR faellig<=?)", (bis,)) or 0)
        saldo = int(self.db.wert("SELECT COALESCE(SUM(betrag_cent),0) FROM real_buchungen") or 0)
        return {"saldo_real_cent": saldo, "erwartet_aus_forderungen_cent": erwartet,
                "status_erwartet": "ERWARTET – nicht bestätigt", "zeitraum_tage": tage}


def _pflicht(**felder):
    for name, wert in felder.items():
        if wert is None or not str(wert).strip():
            raise ValueError("Pflichtfeld fehlt: %s" % name)
